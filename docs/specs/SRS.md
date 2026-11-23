# Software Requirements Specification

- **Project:** Offline PCB Component Inspection
- **Author:** Indraneel Chatterjee
- **Assignment:** Task B, “Which Part Is Missing?”
- **Version:** 1.0 — 20 November 2026
- **Status:** Design baseline; Steps 3–6 record partial implementation and measured results. Full application acceptance remains pending.

Related documents: [Software Design Document](SDD.md) · [Data Flow Diagrams](DFD.md).

Implementation update: [Step 3 commands](../steps/STEP3.md) and [measured results](../steps/STEP3_RESULTS.md)
record the executed landmark training/evaluation. Its four-point accuracy failed
readiness. [Step 4](../steps/STEP4.md) implements alignment and review overlays from reviewed
Step 2 labels. [Step 5](../steps/STEP5.md) implements provisional component-region scoring,
local Needs review coverage/parallax handling and optional symmetric sharpening;
failed alignment skips classification. The wider application requirements below
remain the design baseline, including pending global quality/acceptance policy.
[Step 6](../steps/STEP6.md) implements the local React/FastAPI upload-to-results workflow,
including requested Manual landmark correction and explicit Automatic failure handling.

## 1. Purpose and source basis

Specify a local tool that compares a photograph of a PCB with a known-good photograph of the **same PCB layout**, checks operator-marked components, and highlights expected locations of components that appear to be missing. The intended user is a factory inspection operator; this is an internship take-home demonstration, not a claim of production inspection performance.

The project requirements supplied for this documentation task are the requirements baseline. They describe a fixed factory camera and leave the PCB type open. No official assignment brief was present in the repository, and no verifiable public copy was located during preparation. Assignment compliance beyond the supplied requirements remains pending verification against that brief. No third-party assignment copy is cited as authoritative. Public technical sources support the proposed mechanisms, not measured project results; see [SDD sources](SDD.md#10-public-technical-sources).

## 2. Scope, actor, and workflow

The operator uploads one sharp, complete reference image, confirms four detected landmarks, draws and names component rectangles, and saves the setup. The operator then uploads **one to three inspection photos per batch**, reviews independent per-photo results, and selects parts to compare reference and inspection crops side by side. A failed photo must not remove successful results from the batch.

For example, a reference may contain rectangles named `C12` and `J1 connector`. If only C12 is absent, the C12 rectangle is highlighted as missing and J1 remains present. If both are confidently present and the photo passes inspection gates, the interface displays green `OK`.

In scope: still-photo upload, reference annotation and persistence, landmark detection, planar alignment, image quality checks, optional sharpening, crop comparison, and local evidence display. Out of scope: live camera acquisition, conveyor or PLC integration, electrical testing, solder quality inspection, automatic component naming, arbitrary layout matching, cloud inference, and production certification. A Siamese comparison model is a future experiment, not the initial solution.

### 2.1 Assumptions and constraints

- Each photo shows one full board of the active reference layout and orientation that can be resolved from distinguishable landmarks. The operator is responsible for choosing the correct layout; the app must reject detectable inconsistencies and must not claim universal layout recognition.
- The board is approximately planar. Four repeatable landmarks are spread across it, have fixed identities, and remain visible when inspected parts are missing. Tall components, glare, occlusion, and large viewpoint changes can invalidate comparison even after a planar warp.
- The reference is known to be complete and sharp; software quality checks cannot establish that it contains every required physical component.
- The demo runs on a Windows laptop with Python installed. Dependency installation and preparation may use the internet once. Inspection and restart must work with Wi-Fi off, using local weights and a prebuilt frontend.
- Proposed stack: React and Vite, FastAPI, Python, YOLO26n Pose fine-tuned for four PCB landmarks, and OpenCV. Streamlit is a possible frontend alternative, not a second required implementation.
- Supported demo inputs are proposed as JPEG and PNG. Upload byte limits, decoded image dimensions, minimum crop size, supported Python/package versions, dataset sizes, numerical thresholds, latency, and accuracy are **TBD** until implementation or measurement.

## 3. Terms and result rules

**Reference coordinates:** original decoded, orientation-normalized reference-image pixels, with origin at top left, x to the right, and y downward. Stored rectangles are integer, half-open bounds `[x1, y1, x2, y2]`; crops use rows `y1:y2` and columns `x1:x2`. Browser zoom never changes these stored coordinates.

**Component states:** `present`, `missing`, or `uncertain` after valid comparison. `not_evaluated` records that inspection did not reach classification; it is not a fourth classifier outcome.

**Per-photo outcomes** follow this precedence, shared with the [SDD result contract](SDD.md#65-result-assembly-and-evidence):

| Condition | Outcome | Required display |
| --- | --- | --- |
| File cannot be processed or a runtime error prevents inspection | `error` | Reason and corrective action; no OK or fabricated findings |
| Detectable layout mismatch, unreliable alignment, incomplete required coverage, or severe blur | `retake` | Retake/re-upload reason; affected inspection has no valid component verdicts |
| Gates pass and one or more components are missing | `missing` | All confirmed missing names and rectangles; also list uncertain parts and set `review_required` if any |
| Gates pass, no missing components, and one or more uncertain components | `review` | Ambiguous parts and crop evidence; no OK |
| Gates pass and every saved component is confidently present | `ok` | Green `OK` plus text; `review_required=false` |

The saved setup must contain at least one component: an empty set must never produce an OK by default. An uncertain part must not hide a confirmed missing finding on the same usable photo. If a global quality gate fails, even a promising difference is not a confirmed missing finding.

## 4. Functional requirements

Each “shall” is a proposed acceptance obligation, not a statement of existing implementation.

| ID | Requirement |
| --- | --- |
| FR-01 | The system shall accept exactly one known-good reference photo per setup, validate it, and show its full board before saving. Invalid or severely blurred references shall not become active. |
| FR-02 | The system shall detect four ordered board landmarks, display their identities and confidence, and require operator confirmation before saving. Unreliable detections shall block saving and request a suitable reference. |
| FR-03 | The operator shall be able to zoom, draw, move, resize, rename, and delete component rectangles before saving. Names shall be nonempty and unique within a setup. Rectangles shall be nonempty, within the reference image and board, and the saved set shall contain at least one component. |
| FR-04 | The system shall save and reload the reference image, original dimensions, confirmed ordered landmarks, and named rectangles together in reference coordinates. A failed save shall preserve the prior valid setup. |
| FR-05 | A batch shall contain one to three inspection photos and identify one saved reference setup. Each photo shall be processed independently against the same captured setup and sharpening setting; edits shall not change an in-flight batch. |
| FR-06 | The system shall validate file type and successful decoding, resource limits, full-board suitability, and apparent agreement with the active layout. Invalid files shall receive explicit per-photo errors. Detectable layout disagreement shall prevent OK. |
| FR-07 | The system shall detect the same four landmark identities in each inspection photo, align it into reference coordinates, and check confidence, point geometry, transform validity, and coverage of all marked regions. Where available, independent stable board features shall check alignment agreement. |
| FR-08 | The system shall check image quality before sharpening. Severe blur or unusable alignment shall produce `retake` with a reason. Local ambiguity on an otherwise usable photo shall produce `uncertain` for that component. |
| FR-09 | For every valid marked rectangle, the system shall extract equal-position, equal-size reference and aligned inspection crops and convert both to grayscale without changing the stored rectangle. |
| FR-10 | The system shall offer a configurable sharpening enabled/disabled setting, captured per batch. Enabled shall apply the same mild unsharp mask to both grayscale crops after alignment and extraction, before comparison. Disabled shall send grayscale crops directly to comparison. Neither path shall change crop coordinates or dimensions. |
| FR-11 | The initial comparator shall use normalized correlation of edges or gradients with development-tuned thresholds to classify each crop pair as `present`, `missing`, or `uncertain`. Invalid or uninformative scores shall not imply presence or absence. |
| FR-12 | The system shall assemble outcomes exactly as in Section 3, retain confirmed missing findings when other parts are uncertain, and show green OK only after reliable alignment, acceptable quality, and confident presence of every marked part. |
| FR-13 | Results shall include per-photo identity, component names, reference-coordinate rectangles, statuses, reasons, and an aligned overlay when available. Selecting a component shall show its reference and aligned inspection crops side by side, including uncertain evidence. |
| FR-14 | A failed photo shall have its own actionable error/retake result. Other photos shall continue, and their results shall remain viewable. A shared missing-model or invalid-reference failure shall be explicit rather than reported as board OK. |
| FR-15 | Following preparation, uploading, inference, annotation, saved-reference reload, results, and a full application restart shall work offline on localhost without downloading weights or web assets. |
| FR-16 | Before the demo, a YOLO26n Pose model shall be fine-tuned on PCB images labeled with a board bounding box and four ordered, stable landmarks. Its PCB-specific weights and landmark schema shall be packaged locally; generic human-pose weights shall not be treated as a trained PCB model. |
| FR-17 | Alignment gates and comparison thresholds shall be tuned on labeled development photos. Evaluation shall include a layout held out from both model training and threshold tuning, and a paired sharpening-on/off comparison on the same labeled photos. Missed parts, false alarms, reviews, and retakes shall be reported separately. |
| FR-18 | A proposed `setup.bat` shall create a project-local `.venv` and install `requirements.txt` while online. The demo package shall include prebuilt Vite assets and trained local weights, and FastAPI shall serve the interface and API on localhost. |

## 5. Nonfunctional requirements

| ID | Requirement and verification |
| --- | --- |
| NFR-01 | Image data, annotations, inference, and evidence shall remain on the laptop during use; no external network service shall be required. Verify offline restart and absence of external asset/model requests. |
| NFR-02 | The packaged demo shall run on the target Windows laptop using a local Python environment and CPU inference without requiring a GPU or Node.js at demo runtime. Exact OS/Python/package versions and hardware shall be recorded when tested; presently TBD. |
| NFR-03 | The backend shall enforce input/count/decoded-size limits, reject invalid coordinates and unknown IDs, and use server-generated local paths. Filenames shall not permit path traversal or overwrite arbitrary files. Numeric resource limits are TBD, to be fixed and tested before demo acceptance. |
| NFR-04 | The interface shall label controls and show text alongside status colors. Zoom and editing shall retain rectangle positions. Processing and per-photo failures shall be visible without clearing completed results. Verify by workflow inspection and coordinate round trip. |
| NFR-05 | Reference saves shall be atomic, and batch results shall record the setup identity, model/configuration versions, and sharpening setting sufficient to reproduce a run. Failed writes and process restart shall not corrupt the last saved setup. |
| NFR-06 | Measure startup, per-photo and three-photo batch latency, and peak memory on the target laptop. Latency/memory budgets and observed values are TBD; no real-time or accuracy guarantee is asserted before measurement. |
| NFR-07 | Decisions shall expose component names, locations, evidence, and reasons for uncertainty/retake. Scores shall be described as similarity values, not calibrated probabilities. Measured accuracy and review/retake rates are TBD. |

## 6. Acceptance cases

These are **planned tests**, not executed tests. Use labeled images and a frozen setup/model/threshold configuration. Geometric tolerances, quality thresholds, dataset counts, and statistical release targets remain TBD. A case passes only against agreed labels and tolerances; no current performance result is claimed.

| ID | Given / action | Expected acceptance result | Requirements |
| --- | --- | --- | --- |
| AC-01 | Save a sharp complete reference with distinguishable landmarks and rectangles `C12` and `J1 connector`; inspect a suitable complete photo of that layout. | Both parts present, no missing or uncertain parts, reliable gates, green `OK`. | FR-01, FR-02, FR-09, FR-11, FR-12 |
| AC-02 | Inspect a labeled suitable photo with only C12 absent. | C12 missing at its saved rectangle; J1 present and unflagged; outcome `missing`. | FR-07, FR-11, FR-12, FR-13 |
| AC-03 | Inspect a suitable photo with several marked parts absent. | Every labeled missing part appears by name and location; other confidently present parts stay present. | FR-09, FR-11, FR-12, FR-13 |
| AC-04 | Inspect an otherwise usable photo with one ambiguous part; repeat with another part clearly missing. | First: `review`, no OK. Second: `missing` with `review_required=true`; confirmed missing and uncertain findings both remain visible. | FR-08, FR-11, FR-12, FR-13 |
| AC-05 | Inspect suitable same-layout images with modest in-plane rotation, translation, scale, and viewpoint changes within the calibrated range. | Warp and independent checks, when available, pass; overlays and crops agree within the agreed pixel tolerance; verdicts match labels. Unsupported viewpoints request retake. | FR-07, FR-09, FR-13 |
| AC-06 | Supply collinear/incorrect-order/low-confidence landmarks, a partially cropped board, and a severely blurred image as separate fixtures. | Each unsuitable photo returns `retake` with a specific reason, no OK, and no valid missing/present findings. | FR-06, FR-07, FR-08, FR-12, FR-14 |
| AC-07 | Submit three files: one suitable complete board, one corrupt image, and one suitable photo with a missing part. | Three identifiable results: `ok`, `error`, and `missing`; valid results survive the corrupt file. Test batches of one and two succeed; zero/four files are rejected before processing. | FR-05, FR-06, FR-14, NFR-04 |
| AC-08 | After online preparation, save a reference, stop the application, turn Wi-Fi off, restart, reload the setup, and inspect an image. | Interface/assets/weights load locally, setup reloads, and inspection/evidence work without external requests or Node.js at runtime. Record target environment and timings. | FR-04, FR-15, FR-18, NFR-01, NFR-02, NFR-06 |
| AC-09 | Run the same valid images and rectangles with sharpening disabled, then enabled, while tracing preprocessing/comparator inputs. | Both paths reach comparison once per component; disabled inputs equal grayscale crops, enabled inputs use identical unsharp parameters on both crops. Rectangles and crop sizes are identical across settings. Scores/verdicts may differ and are recorded. | FR-09, FR-10, FR-17, NFR-05 |
| AC-10 | Zoom, move, resize, rename and delete rectangles, then save/reload; attempt empty/duplicate names, zero components, and out-of-bounds boxes. | Valid edits round-trip in original reference coordinates; invalid annotations cannot be saved; rendered boxes remain registered at different zoom levels. | FR-03, FR-04, NFR-03, NFR-04 |
| AC-11 | Upload a wrong-layout image, unsupported file type, oversized/decode-limit fixture, and an invalid reference setup. | Explicit rejection or retake, no OK; a bad reference never replaces the active valid setup. Same-layout responsibility and recognition limits are visible. | FR-01, FR-02, FR-06, NFR-03 |
| AC-12 | Prepare training labels, fine-tune, package, and evaluate on the held-out layout; run paired sharpening ablation on the same labeled photos. | Verify ordered four-keypoint schema and local PCB weights; report counts, splits, missed parts, false alarms, reviews, retakes, timing and both settings. Choose the default from measured errors. No test-layout data tunes weights or thresholds. | FR-16, FR-17, NFR-06, NFR-07 |
| AC-13 | Interrupt a reference save; change the active setup or UI sharpening setting during a batch; restart. | Prior valid setup survives a failed save; in-flight results retain their captured setup/configuration; persisted setup remains readable after restart. | FR-04, FR-05, NFR-05 |
| AC-14 | Remove/corrupt local model weights, force one per-photo processing error, and inspect status text and selected-part evidence. | Startup/readiness reports missing model; processing errors never yield OK; other photos complete where possible. Names, reasons, text statuses, overlay availability and paired crops are clear. | FR-12, FR-13, FR-14, FR-15, NFR-04, NFR-07 |
| AC-15 | Submit filenames containing path traversal, unknown reference IDs, malformed coordinates, and invalid option values. | Backend rejects invalid requests and writes no file outside its data directory; failures preserve valid data. | FR-03, FR-06, NFR-03, NFR-05 |
| AC-16 | Compare a flat/low-texture crop pair or a pair with local glare/occlusion after otherwise successful global gates. | Uninformative/nonfinite correlation or local unreliability yields `uncertain` with a reason and evidence; never automatic OK or confirmed absence. | FR-08, FR-11, FR-12, NFR-07 |

## 7. Open items and completion evidence

The [SDD open decisions](SDD.md#9-open-decisions-and-known-limits) track the absent official brief, data collection and landmark identities, calibration, quality checks, sharpening default, limits, versions, persistence policy, latency, and accuracy. An acceptance report must later record fixture IDs, labels, versions, threshold values, observations, and pass/fail for AC-01 through AC-16. Writing these documents does not complete application acceptance.
