# Software Requirements Specification

- **Project:** Offline PCB Component Inspection
- **Author:** Indraneel Chatterjee
- **Assignment:** Task B, “Which Part Is Missing?”
- **Version:** 2.0 — 24 November 2026
- **Status:** Submission requirements baseline with source-audited implementation status. Historical acceptance records are linked separately; this revision does not claim a new test run.

Related documents: [Software Design Document](SDD.md) · [Data Flow Diagrams](DFD.md).

The numbered requirements retain the intended assignment obligations. Section 4.1 maps them to the current source and identifies partial or planned work. Runtime contracts in Section 3 describe the implementation rather than the earlier proposed API. Historical Step 3 accuracy results apply to that checkpoint and dataset, not automatically to the currently configured mounting-hole model.

## 1. Purpose and source basis

Specify a local tool that compares a photograph of a PCB with a known-good photograph of the **same PCB layout**, checks operator-marked components, and highlights expected locations of components that appear to be missing. The intended user is a factory inspection operator; this is an internship take-home demonstration, not a claim of production inspection performance.

The project requirements supplied for this documentation task are the requirements baseline. They describe a fixed factory camera and leave the PCB type open. No official assignment brief was present in the repository, and no verifiable public copy was located during preparation. Assignment compliance beyond the supplied requirements remains pending verification against that brief. No third-party assignment copy is cited as authoritative. Public technical sources support the proposed mechanisms, not measured project results; see [SDD sources](SDD.md#10-technical-source-of-truth).

## 2. Scope, actor, and workflow

The implemented React application provides a dashboard, golden library, live inspection, account settings, access management and an inspection lab. The operator uploads a reference, reviews its four landmarks and PCB outline, edits named component rectangles or reviews component proposals, and saves a golden configuration. The lab accepts **one to fifteen inspection photos per API batch**. The original one-to-three requirement remains the baseline in FR-05; larger batches are an implemented extension. Each photo retains its own result. Live inspection can process imported image queues or browser camera frames against a selected golden reference.

For example, a reference may contain rectangles named `C12` and `J1 connector`. If only C12 is absent, the C12 rectangle is highlighted as missing and J1 remains present. If both are confidently present and the photo passes inspection gates, the inspection report can classify the photo as `GOOD` with outcome `ok`; this remains a provisional visual comparison.

In scope: still-photo upload, reference annotation and persistence, landmark detection, planar alignment, image quality checks, optional sharpening, crop comparison, and local evidence display. Browser camera frame submission and a software line simulator are implemented extensions. Out of scope: physical conveyor or PLC integration, electrical testing, solder quality inspection, verified automatic component naming, arbitrary layout recognition, cloud inference, and production certification. A Siamese comparison model is a future experiment, not the initial solution.

### 2.1 Assumptions and constraints

- Each photo shows one full board of the active reference layout and orientation that can be resolved from distinguishable landmarks. The operator is responsible for choosing the correct layout; the app must reject detectable inconsistencies and must not claim universal layout recognition.
- The board is approximately planar. Four repeatable landmarks are spread across it, have fixed identities, and remain visible when inspected parts are missing. Tall components, glare, occlusion, and large viewpoint changes can invalidate comparison even after a planar warp.
- The reference is known to be complete and sharp; software quality checks cannot establish that it contains every required physical component.
- The demo runs on a Windows laptop with Python installed. Dependency installation and preparation may use the internet once. Inspection and restart must work with Wi-Fi off, using local weights and a prebuilt frontend.
- Implemented stack: React/Vite, FastAPI, Python, OpenCV, local YOLO26n pose inference, local component detection, file/JSON evidence and SQLite platform persistence.
- Implemented upload limits: JPEG/PNG, 12 MiB per photo, decoded dimensions at least 2×2 and at most 20 million pixels; inspection batches contain 1–15 photos and 1–1000 component entries. Valid comparison rectangles have integer sides of at least 5 pixels. EXIF orientation must already be normalized; it is rejected rather than silently rotated. Hardware performance and real defect accuracy still require bounded measurement.

## 3. Terms and result rules

**Reference coordinates:** original decoded, orientation-normalized reference-image pixels, with origin at top left, x to the right, and y downward. Stored rectangles are integer, half-open bounds `[x1, y1, x2, y2]`; crops use rows `y1:y2` and columns `x1:x2`. Browser zoom never changes these stored coordinates.

**Implemented component states:** `present`, `missing`, `misaligned`, `uncertain`, and `not_evaluated`. `misaligned` covers a shifted or rotated part after board registration; `not_evaluated` means scoring was blocked. These extend the original three-state comparison baseline.

**Implemented per-photo report contract** (`web.py` and `compare.py`):

| Condition | Outcome / classification | Evidence rule |
| --- | --- | --- |
| Decode/processing error | `error`; unevaluated photos classify `NEEDS_REVIEW` | Reason retained; no valid verdict |
| Positive evidence of another design | `DIFFERENT_BOARD` / `BOARD_MISMATCH` | Component inspection blocked |
| Unverified identity/alignment or ambiguous comparison | `review` / `NEEDS_REVIEW` | No automatic acceptance; available evidence retained |
| At least one missing or misaligned component | `defect` / `MISSING_COMPONENT` or `MISALIGNED_COMPONENT` | All component rows retained; `review_required=true` |
| All marked components present | `ok` / `GOOD` | Subject to implemented compatibility, alignment and comparison gates |

The original `retake` and `missing` photo outcome names are **planned baseline vocabulary**, not current serialized values. Retake advice is carried in review reasons. Missing and misaligned rows coexist with uncertainty; photo classification prioritizes misalignment when both defect types occur. An empty component set is rejected. Operator review decisions (`confirmed_reject` or `false_alarm`) are persisted separately and do not relabel model evidence.

Full-board recognition, general severe-blur rejection and calibrated production quality acceptance are partial. Reference-based registration verifies distributed on-board features; the catalog recognizes only supported layouts. Similarity values are not calibrated probabilities.

## 4. Functional requirements

Each “shall” is a retained acceptance obligation, not proof of completion. Implemented deviations and evidence pointers follow in Section 4.1.

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

### 4.1 Source-audited traceability

Test names below identify existing coverage to inspect or execute; they are **not a claim that tests were run for this revision**. Paths are repository-relative.

| IDs | Implementation and current status | Existing test pointers |
| --- | --- | --- |
| FR-01, FR-06 | Partial: `web.upload`, JPEG/PNG decode/limits/orientation; `compatibility.identify_board` and reference verification. No general certified reference completeness/blur gate. | `tests/test_web.py::test_upload_orientation_and_size_boundaries`; `tests/test_board_compatibility.py::test_blur_crop_unknown_layout_and_bad_alignment_are_review` |
| FR-02, FR-07 | Implemented pilot: `infer.LandmarkDetector`, confirmed `reference.json`, `registration.register_inspection`, independent distributed verification, manual correction. Detection failure can fall back to reference registration. Universal four-point accuracy remains unverified. | `tests/test_reference_reuse.py::test_valid_yolo_candidate_is_independently_verified`, `test_failed_yolo_reuses_reference_for_multiple_views_and_perspective`; `tests/test_align.py` |
| FR-03 | Partial: frontend draw/move/numeric resize/name/delete and `compare._validate_regions`/`_box`; backend uniqueness/minimum dimensions. Invalid comparison boxes become review; not every request rejects them before saving. Board containment is not a universal annotation guarantee. | `frontend/tests/workflow.spec.js`; `tests/test_compare.py::test_invalid_boxes_review_and_invalid_metadata_rejects` |
| FR-04 | Implemented split persistence: atomic reference landmarks/outline JSON replacement; golden configuration/components in SQLite. A single atomic image-plus-annotation package is not the storage model. | `tests/test_reference_reuse.py::test_reference_validation_and_changed_setup`; `tests/test_web.py::test_approved_golden_configuration_persists_annotations` |
| FR-05, FR-14 | Implemented extension: 1–15 images; request captures components/mode/sharpening and per-photo errors are isolated. | `tests/test_web.py::test_fifteen_inspections_keep_all_results_and_overlays`, `test_failed_photo_does_not_suppress_valid_sibling` |
| FR-08 | Partial: raw low-texture checks, coverage, independent registration and review fallback; no universally calibrated global severe-blur/quality policy. | `tests/test_compare.py::test_uninformative_crops_cannot_be_rescued_by_sharpening`; `tests/test_demo_safety.py::test_zero_overlay_and_no_matches_requires_review` |
| FR-09, FR-10 | Implemented: reference-grid evidence crops; comparison searches bounded neighboring pixels/rotation hypotheses. Symmetric optional unsharp mask, default off, retains stored rectangles. | `tests/test_compare.py::test_sharpening_changes_scores_but_not_fixture_decisions_or_inputs`, `test_all_present_with_symmetric_sharpening` |
| FR-11, FR-12 | Partial baseline / extended pilot: Sobel NCC plus bounded local matching, corroborated absence, displacement/rotation and detector correspondence. Actual outcome vocabulary is Section 3. Thresholds remain provisional. | `tests/test_demo_safety.py::test_low_similarity_alone_never_means_missing`; `tests/test_compare.py::test_local_rotation_after_board_registration_is_misaligned_with_evidence`; `tests/test_correspondence.py` |
| FR-13 | Implemented evidence: reports, aligned/component/difference overlays and selected paired crops in `Comparison.jsx`; platform review queue and decisions. | `tests/test_web.py::test_pipeline_matches_cli_functions_and_saves_assets`; `frontend/tests/repair-workflow.spec.js` |
| FR-15, FR-18 | Implemented local preparation/launch paths and local assets/weights. Full target-machine offline restart acceptance remains an evidence obligation. | `pcb_landmarks/verify_offline.py`; [Step 7 record](../steps/STEP7.md) |
| FR-16 | Local trained pose checkpoint configured in `configs/landmarks.json`; mounting-hole schema and limited tuning provenance recorded. Historical Step 3 failure is retained in its own record. | `tests/test_infer.py`; `tests/test_calibrated_mounts.py`; [fine-tuning record](../guides/LANDMARK_FINE_TUNING.md) |
| FR-17 | Partial/planned: configuration and synthetic/regression fixtures exist; verified real defect accuracy, broad unseen-layout evaluation and controlled sharpening ablation remain incomplete. | `tests/test_evaluate.py`; `tests/test_compare.py::test_sharpening_changes_scores_but_not_fixture_decisions_or_inputs`; [Step 3 results](../steps/STEP3_RESULTS.md) |
| NFR-01, NFR-02 | Local CPU architecture and prebuilt frontend; complete hardware/offline acceptance requires the recorded environment and network-isolated run. | `pcb_landmarks/verify_offline.py`; [Step 7](../steps/STEP7.md) |
| NFR-03 | Implemented UUID storage, strict booleans, resource/ID/origin checks; platform roles are enforced on platform routes. Local lab endpoints are not a comprehensive authenticated service boundary. | `tests/test_web.py::test_batch_limits_ids_booleans_and_origin`, `test_annotation_limits_and_nonfinite_metadata_are_rejected`, `test_authenticated_platform_routes_enforce_roles` |
| NFR-04, NFR-07 | Text statuses, original-pixel editing and explainable review evidence implemented; measured defect/review/retake performance remains partial. | `frontend/src/coordinates.test.js`; `frontend/tests/operator-feedback.spec.js`; `tests/test_compare.py` |
| NFR-05 | Partial: atomic reference JSON and transactional SQLite; report captures annotations/config/sharpening. Not every artifact is transactional and per-run complete model/configuration version provenance is not guaranteed. | `tests/test_platform_store.py::test_golden_configuration_round_trip`; `tests/test_reference_reuse.py::test_features_cached_per_reference_and_recomputed_on_replacement` |
| NFR-06 | Planned target-laptop performance acceptance; historical timings are scoped to their recorded runs. | [audit records](../README.md#audits--repair-recovery-and-acceptance-records) |

## 5. Nonfunctional requirements

| ID | Requirement and verification |
| --- | --- |
| NFR-01 | Image data, annotations, inference, and evidence shall remain on the laptop during use; no external network service shall be required. Verify offline restart and absence of external asset/model requests. |
| NFR-02 | The packaged demo shall run on the target Windows laptop using a local Python environment and CPU inference without requiring a GPU or Node.js at demo runtime. Exact OS/Python/package versions and hardware shall be recorded for each target-machine acceptance run. |
| NFR-03 | The backend shall enforce input/count/decoded-size limits, reject invalid coordinates and unknown IDs, and use server-generated local paths. Filenames shall not permit path traversal or overwrite arbitrary files. Current numeric limits are listed in Section 2.1; comprehensive adversarial acceptance remains pending. |
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
| AC-14 | Remove/corrupt local model weights, force one per-photo processing error, and inspect status text and selected-part evidence. | Health exposes checkpoint availability; missing pose weights may use verified classical reference registration. Processing errors never yield OK; other photos complete where possible. Names, reasons, text statuses, overlay availability and paired crops are clear. | FR-12, FR-13, FR-14, FR-15, NFR-04, NFR-07 |
| AC-15 | Submit filenames containing path traversal, unknown reference IDs, malformed coordinates, and invalid option values. | Backend rejects invalid requests and writes no file outside its data directory; failures preserve valid data. | FR-03, FR-06, NFR-03, NFR-05 |
| AC-16 | Compare a flat/low-texture crop pair or a pair with local glare/occlusion after otherwise successful global gates. | Uninformative/nonfinite correlation or local unreliability yields `uncertain` with a reason and evidence; never automatic OK or confirmed absence. | FR-08, FR-11, FR-12, NFR-07 |

## 7. Open items and completion evidence

The [SDD known limits](SDD.md#9-open-decisions-and-known-limits) records remaining calibration, quality, packaging and performance obligations. AC-01–AC-16 above retain the original acceptance goals; their `missing`/`retake` vocabulary and 1–3 batch limits must be reconciled with the actual Section 3 contract before execution. Existing tests and historical audit documents provide scoped evidence, not a blanket pass of these acceptance cases. No runtime, UI, model or detector behavior was changed for this documentation revision.
