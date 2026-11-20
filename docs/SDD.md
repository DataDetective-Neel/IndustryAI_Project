# Software Design Document

- **Project:** Offline PCB Component Inspection — Task B, “Which Part Is Missing?”
- **Author:** Indraneel Chatterjee
- **Version:** 1.0 — 20 November 2026
- **Status:** Proposed design. At preparation the repository contained no application, model, dataset, setup script, or dependency manifest. Names, paths, modules, and API contracts below are proposals, not existing interfaces.

Related documents: [Software Requirements Specification](SRS.md) · [Data Flow Diagrams](DFD.md).

Implementation update: the landmark-only training and local inference commands
are documented in [Step 3](STEP3.md), with [actual results](STEP3_RESULTS.md).
The trained pilot is not ready for alignment. [Step 4](STEP4.md) now implements
four-point alignment and overlays using reviewed Step 2 labels; remaining modules
and full quality/acceptance gates below are proposed. [Step 5](STEP5.md) now adds
provisional region correlation, per-region review gates, symmetric optional
sharpening and a local annotated report; this is not full-app acceptance.

## 1. Design basis and boundary

Implement the supplied operator workflow with a single local application: one complete reference photo, confirmed four-landmark geometry, named component rectangles, and batches of **one to three inspection photos** of the same PCB layout. Fixed-camera factory use motivates stable views; the Windows demo accepts uploaded still photos. The official assignment brief was unavailable locally and no verifiable public copy was found; assignment-specific claims are based on the supplied requirements and must be checked against the brief when obtained.

The system checks only marked regions for apparent component absence. It does not prove electrical correctness or identify arbitrary board layouts. All application capabilities described here remain proposed. Training and packaging precede the demo; normal inspection needs no network.

## 2. Architecture and responsibilities

Use one FastAPI process for the API, inspection orchestration, and serving the prebuilt React/Vite frontend on loopback. Keep inference and crop processing in Python modules called by that process; an external worker service or database server is unnecessary for a three-image demo batch.

| Proposed module | Responsibility | Inputs → outputs |
| --- | --- | --- |
| Operator UI | Reference upload, landmark confirmation, zoomable rectangle editor, batch submission, per-photo status, overlay and paired crop viewer | Files/edits → API requests; results → named visual findings |
| API and validation | Multipart intake, typed metadata validation, reference/asset lookup, readiness, consistent error envelopes | Requests → validated local inputs or actionable errors |
| Reference service / repository | Detect and stage reference; validate annotations; atomically save an immutable setup; reload by ID | Reference + confirmed landmarks + rectangles → saved setup |
| Batch orchestrator | Capture setup/configuration, enforce one to three files, process sequentially with per-photo exception boundaries | Batch + setup + options → one result per input in input order |
| Landmark service | Load local PCB-specific YOLO26n Pose weights once; return one board box and four identified keypoints with confidence | Decoded image → ordered landmark detection or failure |
| Alignment / quality | Geometry, blur, layout-consistency checks, perspective warp, region coverage, independent stable-feature checks where available | Images + landmarks + rectangles → aligned image, validity mask and quality report or retake |
| Crop / preprocessing | Paired rectangle extraction, grayscale conversion; optional symmetric unsharp mask | Valid aligned pair + rectangles + option → comparison-ready crop pairs |
| Comparator | Edge/gradient normalized correlation, informativeness checks, calibrated classification | Crop pairs + frozen thresholds → scores, component states and reasons |
| Result assembler / evidence | Apply outcome precedence, preserve missing plus uncertain findings, build overlay and local crop assets | Findings + gates + images → per-photo result and evidence |
| Offline setup / packaging | Project `.venv`, installed dependencies, prebuilt frontend, model and calibrated configuration | Online preparation → self-contained demo runtime |

React supports a component-based UI [T1]; the proposed frontend is built using Vite's production build [T2]. FastAPI supports uploaded files [T3] and mounting static assets [T4]. [Streamlit](https://docs.streamlit.io/) is a possible alternative if UI implementation constraints require it; choosing it would require revising the frontend/package contracts. It is not an additional service in this design.

## 3. Data model and local storage

Proposed storage is local files plus JSON metadata. There is no implemented database. Use server-generated IDs for directories and asset URLs; display original filenames only as labels. Never derive filesystem paths directly from user filenames.

| Record | Proposed fields and invariants |
| --- | --- |
| Reference draft | `draft_id`, decoded orientation-normalized reference image, `width`, `height`, board box, ordered detected landmarks and confidence, validation report. Drafts are not inspectable setups. |
| Reference setup | `schema_version`, `reference_id`, image asset/hash, original decoded `width`/`height`, board box, `landmark_schema_version`, four `{id,x,y,confidence}` entries, operator confirmation, nonempty `components`, model/configuration provenance. Saved records are immutable; editing creates a new setup ID. |
| Component annotation | `component_id`, unique nonempty `name`, integer `rect=[x1,y1,x2,y2]` in reference coordinates. Validate `0 <= x1 < x2 <= width`, `0 <= y1 < y2 <= height`, board containment and calibrated minimum usable crop size (TBD). |
| Inspection configuration | `config_version`, landmark confidence/geometry and quality limits, independent-check policy, crop feature settings, correlation thresholds, `sharpening_enabled`, unsharp parameters, numeric resource limits. Unmeasured values/default selection remain TBD. |
| Batch snapshot | `batch_id`, immutable `reference_id`, input IDs/order, `sharpening_enabled`, model hash/version, configuration version and captured parameter values. Later UI edits do not alter this snapshot. |
| Per-photo result | `photo_id`, display filename, `reference_id`, outcome, `review_required`, quality/alignment reasons and diagnostics, component results, nullable evidence assets, captured provenance and timings. |
| Component result | `component_id`, `name`, `rect`, state `present/missing/uncertain/not_evaluated`, nullable similarity score, reason, nullable reference/inspection crop asset IDs. `not_evaluated` has no classifier score. |

**Proposed paths:** `data/references/<reference_id>/` holds the canonical image and `setup.json`; `data/drafts/<draft_id>/` stages a reference; `data/results/<batch_id>/` holds result metadata and available overlays/crops. `models/pcb-landmarks.pt` holds the trained checkpoint and a manifest of schema, hash, and training provenance. These paths and files do not currently exist.

Build a complete reference in a temporary directory, validate it, then publish it with a same-volume atomic rename. Keep the last valid setup on any write failure. Results are written per photo so one failure does not discard siblings; restart recovery of an interrupted batch is out of scope, but saved references must reload. Result retention and cleanup policy remain open; evidence must survive at least the current review session, and no cleanup may remove the active reference or viewed result.

## 4. Coordinate and annotation contract

1. Decode and normalize image orientation before landmark detection or annotation. “Original reference pixels” means this full-resolution, canonical decoded raster, before browser display scaling; store its dimensions. Reject unsupported orientation/decoding cases rather than mixing coordinate frames.
2. Use top-left origin, x right, y down. Persist reference landmarks as pixel floats. Maintain four semantic IDs `L0`, `L1`, `L2`, `L3` in the same documented cyclic order on every training, reference, and inspection image. Where corners are suitable, choose identifiable board-relative corners. Do not reorder by the current image's top-left position after rotation.
3. The UI converts pointer coordinates through the inverse of its image display transform, including zoom, pan, and image offset. On save, round top/left down and bottom/right up once to integer half-open bounds `[x1,y1,x2,y2]`; validate bounds without silently accepting invalid rectangles. Crops are `image[y1:y2, x1:x2]`.
4. Store no CSS-space coordinates. Re-render rectangles using the forward display transform. Named rectangles, landmarks, overlays, and aligned crops all refer to the same saved reference frame.
5. Detect inspection landmarks in that image's full decoded pixel frame. Any model input resize/letterbox mapping must be undone before computing alignment. Never mix normalized training labels with inference pixel coordinates.
6. Compute `H_inspection_to_reference` from source inspection points to destination reference points; warp into `(reference_width, reference_height)`. Rectangles are not transformed or resized after the warp. The optional sharpening step changes intensity only and cannot change this frame.

## 5. Training and reference workflows

### 5.1 Train and package the landmark model

Collect PCB photographs spanning expected lighting, orientations, modest viewpoints, and missing-component states. Label one board bounding box and four repeatable, distinguishable landmarks distributed over the board plane; prefer stable board features that remain when inspected parts are missing. Define the identity order before annotation and keep it in a dataset manifest. The exact landmarks depend on collected boards and are TBD.

Fine-tune **YOLO26n Pose** for one PCB class and `kpt_shape: [4, 3]`. Use the documented pose label format with normalized box and keypoint coordinates and visibility labels [T6]. The generic `yolo26n-pose.pt` checkpoint is pretrained for human keypoints [T5]; adapting and training the four-landmark head is necessary. It does not already recognize PCB landmarks.

Split by board layout and acquisition grouping before training, keep near-duplicate photos together, and reserve at least one evaluation layout from model training and threshold tuning. Training/development/test counts, epochs, input resolution and numerical quality criteria are TBD. Validate identity consistency, landmark localization, confidence failures, and full pipeline behavior; generalization to the held-out layout is an experiment, not guaranteed.

Export/package the trained PCB checkpoint as a local path with its model hash, landmark schema, package versions, and calibration configuration. Inference loads this file explicitly, verifies availability/schema, and fails readiness if it is absent or incompatible. Do not supply a generic model name that triggers an automatic download during the demo. Ultralytics documents local custom checkpoint loading [T5].

### 5.2 Save a reference setup

Validate and decode one reference image, check full-board visibility and blur, detect one board and four landmarks, and display them with identities/confidence. Multiple candidate boards or unreliable landmarks block saving. The operator confirms the detected identities, zooms and edits named rectangles, and saves only after server-side validation. Manual landmark correction is not required by this proposal; unreliable detections request a better upload. Store the image, confirmed ordered landmarks and annotations as one immutable setup. Return the setup ID to the UI for inspection.

## 6. Inference pipeline

### 6.1 Batch intake and image validation

Capture the immutable reference and selected sharpening setting once per batch. Reject invalid batch counts (outside one to three), unknown reference IDs and malformed options before work begins. Use a simple synchronous batch request with sequential per-photo processing initially; no queue/polling service is required. UI timeout and supported image size must be set after laptop timing measurements.

For each photo, check JPEG/PNG content and decoder success, byte and decoded-dimension limits, one complete board, supported channel/orientation conversion, and gross quality. Exact numeric limits are TBD but must be enforced before demo acceptance. File validation failure produces a per-photo `error`; quality or detectable layout mismatch produces `retake`. Catch errors per input, release temporary resources, and continue. Shared readiness failures are reported explicitly before inspection.

### 6.2 Landmark detection, alignment, and quality gates

Detect the same four semantic landmarks. Require confidence above calibrated thresholds, finite in-image coordinates, distinct well-spread points, a non-self-intersecting convex quadrilateral with consistent order, adequate area, and a numerically usable transform. Reject collinear, near-degenerate, mirrored/identity-inconsistent, or incomplete observations. Numeric cutoffs are TBD.

Use `cv2.getPerspectiveTransform(inspection_points, reference_points)` and `cv2.warpPerspective` to produce a reference-sized image [T7]. Warp an all-valid source mask with the same transform and invalid border. Step 4 conservatively requires full bilinear source support plus inverse-coordinate bounds rather than nearest-neighbor support alone; see its [implemented contract](STEP4.md#coordinate-and-validation-contract). Step 5 requires full coverage of each scored rectangle, routing partial local coverage to Needs review as requested for this pilot. The full application's global coverage/retake policy remains to be calibrated. Padding outside the photographed image must not become comparison evidence.

**Four fitted points cannot independently validate their own alignment:** mapping residual at those same four correspondences can be tiny even for wrong identities. Check transform plausibility and board containment; where available, compare independent stable features such as mounting holes, silkscreen, or board-edge correspondences outside inspected components. The feature method, matching tolerance, minimum evidence, and fallback acceptance gates without independent features are TBD and must be calibrated before demo acceptance. If confidence in the alignment cannot be established, return `retake` rather than OK. Generate a blend overlay for operator verification; visual review supplements automated gates.

Assess blur before sharpening, provisionally using grayscale Laplacian variance plus development-calibrated criteria [T9]. Assess coverage, glare/occlusion and usable texture. Severe blur or unreliable global alignment invalidates the photo (`retake`); a local glare/texture problem on an otherwise usable photo makes only that crop `uncertain`. Reference image quality must also pass before saving. Sharpening must never rescue a photo that failed the original quality checks. Planar alignment cannot remove tall-component parallax.

### 6.3 Crop extraction and optional sharpening

For every rectangle, extract the same integer bounds from the reference and aligned inspection images, then convert both to grayscale. Keep the raw grayscale pair for evidence and quality assessment.

Sharpening is a **separate configurable preprocessing process** after alignment and crop extraction, before feature comparison:

- **Disabled:** pass the grayscale crop pair directly to the comparator, with no sharpen/filter substitute.
- **Enabled:** apply the same mild unsharp mask to both crops: `sharp = clip(gray + amount * (gray - GaussianBlur(gray)))`. Compute with a safe intermediate numeric type, clip to the intended intensity range, and retain exactly the original crop dimensions. OpenCV provides Gaussian filtering [T9] and weighted array operations [T10].

Unsharp amount, blur kernel/sigma and the eventual default are TBD. Use one frozen parameter set for both members of a pair; never move rectangles, resample crops, or choose the setting per observed result. Record the batch setting in results. The default is selected by the paired validation in Section 8, not assumed to improve accuracy.

### 6.4 Crop scoring and classification

Initial design choice: calculate gradient magnitude (provisionally Sobel) from each comparison-ready crop, then use zero-mean normalized correlation, such as `cv2.matchTemplate` with `TM_CCOEFF_NORMED` on equal-size maps. This gives one similarity score at the saved location; it does not search for parts elsewhere. OpenCV documents the normalized correlation modes [T8]. The edge-versus-gradient representation and settings remain subject to labeled development validation.

Check feature energy/variance and finite values **before** trusting a normalized score; flat maps can yield misleading library outputs. For a usable pair, let `t_missing < t_present`:

| Condition | Component classification |
| --- | --- |
| Uninformative texture, local glare/occlusion, or invalid/nonfinite score | `uncertain` with reason |
| `score <= t_missing` | `missing` under the calibrated absence rule |
| `score >= t_present` | `present` |
| Between thresholds | `uncertain` |

Threshold values, whether a single global pair is adequate across component types, and local-quality limits are TBD. Low similarity is not proof of absence: lighting changes, occlusion, parallax and misregistration can also cause it. Use labeled development data to validate the missing rule and route unreliable pairs to uncertainty. A score is not a probability. A Siamese network is an optional future comparison experiment only if sufficient labeled crop pairs exist; it is not needed to implement this baseline.

### 6.5 Result assembly and evidence

Match [SRS Section 3](SRS.md#3-terms-and-result-rules): file/runtime failure → `error`; failed layout/alignment/global quality → `retake`; otherwise any missing → `missing`; otherwise any uncertain → `review`; otherwise all nonempty marked parts present → `ok`. `review_required` is true exactly when a classified component is uncertain. An `error` or `retake` has `review_required=false` and an actionable reason, not an implication that inspection succeeded. Its components are `not_evaluated`, with null scores and no valid missing/present claims.

For usable photos preserve all component findings. A missing C12 and uncertain J1 produce outcome `missing` and `review_required=true`. Show missing rectangles in red, uncertain rectangles in amber, and presence in the component list, with text labels so color is not the sole signal. Only `ok` displays green `OK`.

Create an overlay in reference coordinates from reference and aligned inspection pixels; add named expected rectangles. Selecting a part shows its original reference crop and aligned inspection crop side by side. Indicate whether the scoring path used sharpening; keep raw evidence and optionally the processed pair for diagnosis. A failed warp has no overlay; report `null` and explain why rather than providing a misleading image. Evidence asset IDs resolve only to application-managed local files.

## 7. Proposed API contracts and failures

All endpoints below are **proposed**, same-origin localhost under `/api`. Multipart uploads carry file fields and text fields; metadata in a multipart request is a JSON-encoded form field validated by the backend, not a simultaneous JSON request body [T3]. IDs are opaque server-generated strings. No public network API is intended.

| Method / route | Request | Success response |
| --- | --- | --- |
| `GET /api/health` | None | `200` readiness, model/configuration versions and required asset status; `503` if required runtime assets cannot load |
| `POST /api/reference-drafts` | Multipart `image`: exactly one file | `201` draft ID, canonical image asset, dimensions, detected board box, four ordered landmarks/confidences, validation report; detection/quality rejection is explicit |
| `POST /api/references` | JSON: `draft_id`, `landmarks_confirmed=true`, nonempty `components` with names and integer reference rectangles | `201` immutable reference setup with ID; server uses the draft's validated landmarks and image, never client-substituted detection coordinates |
| `GET /api/references/{reference_id}` | Saved ID | `200` setup, image asset and coordinate metadata for reload/editing |
| `POST /api/inspections` | Multipart `reference_id`, explicit boolean text `sharpening_enabled`, repeated `images` fields (one to three files) | `200` batch ID, captured provenance, ordered per-photo results; mixed `ok/error/retake/missing/review` results are allowed |
| `GET /api/results/{batch_id}` | Batch ID | `200` stored metadata and available asset IDs for completed per-photo results |
| `GET /api/assets/{asset_id}` | Known asset ID | `200` local reference, overlay or crop image; no arbitrary filesystem path accepted |

For editing a saved reference, submit its canonical image as a new draft, confirm landmarks and save a new setup; the UI can initialize the editor with the old named rectangles if dimensions match. This avoids modifying the reference captured by an existing batch. An active reference is the setup ID selected in the UI; startup can list the saved IDs locally in a future implementation, but a reference-list endpoint is not specified here.

Proposed successful batch result shape (field types, not measured values):

```text
batch_id: string
reference_id: string
provenance: {model_hash, config_version, sharpening_enabled, captured_parameters}
photos: [
  {photo_id, filename, outcome, review_required,
   reasons: [{code, message}], alignment: {reliable, diagnostics},
   overlay_asset_id: string | null,
   components: [{component_id, name, rect: [x1,y1,x2,y2],
                 state, score: number | null, reason: string | null,
                 reference_crop_asset_id: string | null,
                 inspection_crop_asset_id: string | null}],
   timings}
]
```

**Error envelope:** `{error: {code, message, field?}}` for request-level failure; the analogous code/message appears in a per-photo result when only that photo fails. Proposed HTTP mapping: `400` malformed metadata/options or invalid batch count; `404` unknown ID; `413` request/file resource limit; `415` unsupported request media; `422` invalid reference/annotation or reference detection/quality rejection; `503` unavailable model/configuration; `500` unexpected shared failure. A corrupt individual image in an accepted inspection batch becomes `error/IMAGE_DECODE_FAILED` in its `200` batch response. Stream/request-level resource rejection can reject the entire request before any file processing; count/framing/size rejection is distinct from per-photo independence after accepted intake.

Suggested retake reason codes include `LANDMARKS_UNRELIABLE`, `GEOMETRY_INVALID`, `REGION_NOT_COVERED`, `ALIGNMENT_UNVERIFIED`, `LAYOUT_MISMATCH`, and `IMAGE_TOO_BLURRED`. Local uncertainties include `LOW_TEXTURE`, `LOCAL_OCCLUSION_OR_GLARE`, and `AMBIGUOUS_SCORE`. Log internal exceptions locally while returning concise actionable messages; never expose host paths or stack traces in UI errors. Validate booleans explicitly, cap decoding/multipart resources, and preserve prior files on write failure. Exact request limits must be set before release.

### 7.1 Windows setup and offline runtime

The proposed `setup.bat` runs from the project directory while online, checks a compatible installed Python version, creates `.venv` via `python -m venv .venv`, and installs pinned/tested dependencies using `.venv\Scripts\python.exe -m pip install -r requirements.txt`. Abort on failure with a useful message. Python documents project virtual environments [T11]. Version pins and `requirements.txt` are future implementation artifacts, not part of this documentation commit.

Prepare `frontend/dist/` through the Vite build on a development machine and ship it with the demo [T2]. Package the trained model and configuration explicitly; setup must verify all required local assets. FastAPI serves the HTML and static files after API routes are registered [T4], binds to `127.0.0.1` (proposed port `8000`), and loads weights from disk once at startup. No Vite development server, Node.js runtime, CDN font/script, cloud API, or first-run model download is required at demo time. Disable optional network telemetry/update checks in packaged libraries and verify actual offline behavior rather than assuming it.

Operator startup instructions will use the project environment to run the FastAPI application; the entry module/launcher is TBD because no application exists yet. Final verification must stop the app, disable Wi-Fi, restart from the packaged files, reload a saved reference, inspect a batch, and review evidence. Repeat on the actual target laptop and record versions/hardware.

## 8. Validation and SRS traceability

First verify coordinate round trips, geometry rejection, validity-mask coverage, classifier edge cases, both preprocessing paths, per-photo isolation, atomic saves, and API validation. Then use the [SRS acceptance cases](SRS.md#6-acceptance-cases) with labeled real images. These checks are planned; only the documentation is being delivered now.

Tune model confidence, alignment/blur gates, crop representation and comparison thresholds on labeled development photos. Freeze them before evaluating a PCB layout excluded from training and threshold tuning. Using a complete reference from that test layout is required for inspection; it must not become labeled tuning data. Keep acquisition groups/near-duplicates out of other splits. Verify that all four landmark identities can actually be detected on that unseen layout.

On the **same labeled photos**, run sharpening disabled and enabled with the same setup, model, gates and comparison configuration for the primary paired ablation. Report any separately retuned comparison as a separate experiment. Count ground-truth missing parts predicted present as missed parts, ground-truth present parts predicted missing as false alarms, and uncertain components and retake photos separately; report denominators and do not drop difficult cases. Include uncertain missing parts and quality-gated photos as unresolved coverage, so routing to review cannot hide poor automatic recall. Record a component confusion matrix, per-photo OK/missing/review/retake/error counts, layout-specific metrics, startup/batch latency and memory.

Choose the proposed default sharpening setting from development missed-part and false-alarm results, with review and retake rates disclosed; then lock it for final held-out evaluation. If evidence is insufficient, leave the default unresolved rather than claiming an improvement. Dataset sizes, numeric thresholds, tolerances, latency, accuracy and release targets are **TBD**.

| SRS ID | Design responsibility / section | Planned acceptance cases |
| --- | --- | --- |
| FR-01 | API/reference service; 5.2, 6.1 | AC-01, AC-11 |
| FR-02 | Landmark/reference service; 4, 5.2 | AC-01, AC-11 |
| FR-03 | UI editor, API validation; 3–4, 5.2 | AC-10, AC-15 |
| FR-04 | Reference repository; 3, 5.2 | AC-08, AC-10, AC-13 |
| FR-05 | Batch orchestrator; 3, 6.1 | AC-07, AC-13 |
| FR-06 | API and quality validation; 6.1–6.2, 7 | AC-06, AC-07, AC-11, AC-15 |
| FR-07 | Landmark/alignment service; 4, 6.2 | AC-02, AC-05, AC-06 |
| FR-08 | Quality gates; 6.2, 6.4 | AC-04, AC-06, AC-16 |
| FR-09 | Crop service; 4, 6.3 | AC-01, AC-03, AC-05, AC-09 |
| FR-10 | Preprocessing/configuration; 6.3 | AC-09 |
| FR-11 | Comparator; 6.4 | AC-01, AC-02, AC-03, AC-04, AC-16 |
| FR-12 | Result assembler/UI; 6.5 | AC-01, AC-02, AC-03, AC-04, AC-06, AC-14, AC-16 |
| FR-13 | Evidence service/UI; 6.5, 7 | AC-02, AC-03, AC-04, AC-05, AC-14 |
| FR-14 | Orchestrator/error handling; 6.1, 7 | AC-06, AC-07, AC-14 |
| FR-15 | Offline packaging/readiness; 5.1, 7.1 | AC-08, AC-14 |
| FR-16 | Training/landmark service; 5.1 | AC-12 |
| FR-17 | Calibration/evaluation; 8 | AC-09, AC-12 |
| FR-18 | Windows setup/static host; 7.1 | AC-08 |
| NFR-01 | Local stores/inference/static host; 2–3, 7.1 | AC-08 |
| NFR-02 | Windows CPU packaging; 7.1 | AC-08 |
| NFR-03 | API/repository input boundaries; 3–4, 6.1, 7 | AC-10, AC-11, AC-15 |
| NFR-04 | UI editor/result viewer; 4, 6.1, 6.5 | AC-07, AC-10, AC-14 |
| NFR-05 | Atomic repository/batch snapshots; 3, 6.1 | AC-09, AC-13, AC-15 |
| NFR-06 | Timing and memory evaluation; 7.1–8 | AC-08, AC-12 |
| NFR-07 | Comparator/evidence/evaluation; 6.4–6.5, 8 | AC-12, AC-14, AC-16 |

## 9. Open decisions and known limits

| Item | Decision or evidence still needed |
| --- | --- |
| Assignment verification | Obtain the official Task B brief and check the supplied scope against it. |
| Data and landmarks | Collect licensed/authorized PCB data; choose distinguishable, persistent four-point identities across target layouts; record split counts and held-out layout. |
| Alignment assurance | Select independent features, numeric geometry/coverage tolerances, acceptable viewpoint range, and gates when independent features are unavailable. Four-point fit alone is insufficient. |
| Quality and comparator | Calibrate blur/glare/texture checks, gradient settings and present/missing thresholds; establish whether global thresholds suffice. |
| Sharpening | Choose mild unsharp parameters and default from paired development evaluation. Neither setting is presumed superior. |
| Runtime constraints | Set byte/dimension/crop limits, request timeout, tested Windows/Python/package versions, hardware and memory/latency targets. |
| Persistence | Finalize metadata schema, evidence retention/cleanup, disk-space behavior and convenient saved-reference selection. File/JSON storage remains the proposed baseline. |
| Delivery | Implement application, `setup.bat`, requirements, frontend build, trained weights, launcher and offline restart test. None is provided by these documents. |
| Performance | Measure missed parts, false alarms, reviews, retakes, latency and accuracy. All unmeasured values remain TBD. |
| Future experiments | Streamlit can replace the frontend if selected; Siamese crop scoring requires enough labeled pairs and separate evaluation. Neither expands current acceptance scope. |

## 10. Public technical sources

Official technical documentation consulted on 20 November 2026. These references establish library capabilities; proposed engineering choices and project requirements are identified in the text. No benchmark from another dataset is presented as PCB performance.

- **T1:** [React Quick Start](https://react.dev/learn) — component and state-based interface construction.
- **T2:** [Vite: Building for Production](https://vite.dev/guide/build.html) — production frontend assets.
- **T3:** [FastAPI: Request Files](https://fastapi.tiangolo.com/tutorial/request-files/) — multipart upload handling.
- **T4:** [FastAPI: Static Files](https://fastapi.tiangolo.com/tutorial/static-files/) — local static asset serving.
- **T5:** [Ultralytics: Pose Estimation](https://docs.ultralytics.com/tasks/pose/) — YOLO26 pose, pretrained keypoints, training and local checkpoint inference.
- **T6:** [Ultralytics: Pose Dataset Format](https://docs.ultralytics.com/datasets/pose/) — bounding boxes, ordered keypoint labels and `kpt_shape`.
- **T7:** [OpenCV: Geometric Image Transformations](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html) — four-point perspective transform and image warp.
- **T8:** [OpenCV: Template Matching Modes](https://docs.opencv.org/4.x/df/dfb/group__imgproc__object.html) — normalized correlation definitions.
- **T9:** [OpenCV: Image Filtering](https://docs.opencv.org/4.x/d4/d86/group__imgproc__filter.html) — Gaussian, Sobel and Laplacian operations; project-specific blur criteria require calibration.
- **T10:** [OpenCV: Array Operations](https://docs.opencv.org/4.x/d2/de8/group__core__array.html) — weighted arithmetic for proposed unsharp masking.
- **T11:** [Python: venv](https://docs.python.org/3/library/venv.html) — local isolated Python environment.

## 11. Documentation verification record

On 20 November 2026, local documentation checks passed for all 15 relative links/anchors, all 25 requirement IDs and their bidirectional mappings to 16 acceptance cases, balanced code fences, and the explicit sharpening bypass. A manual consistency review covered upload limits, coordinate semantics, result precedence and offline operation. All three Mermaid diagrams rendered to SVG and PNG using Mermaid CLI 12.2.0 with local Chrome; the previews were visually inspected. Staged whitespace checks passed. GitHub's hosted preview was not separately inspected.

This record concerns documentation only; application acceptance, model training and Windows offline execution remain pending. The official assignment brief also remains unavailable for verification.
