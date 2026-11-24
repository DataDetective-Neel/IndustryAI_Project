# Software Design Document

- **Project:** Offline PCB Component Inspection — Task B, “Which Part Is Missing?”
- **Author:** Indraneel Chatterjee
- **Version:** 2.0 — 24 November 2026
- **Status:** Source-audited implementation description. Provisional inspection performance; no new test execution claimed by this revision.

Related documents: [Software Requirements Specification](SRS.md) · [Data Flow Diagrams](DFD.md) · [documentation index](../README.md).

## 1. Design basis and boundary

The application compares an operator-approved golden PCB with images of the same layout and board side. It reports visual presence, apparent absence, local displacement/rotation and uncertainty within configured component rectangles. It is a local demonstration, not production-certified AOI. Same-design registration is required before component scoring. An exact four-point fit alone is not independent verification.

The implementation extends the original upload-only design with a platform dashboard, golden library, review decisions, role-based platform actions, imported frame queues, software line simulation and browser camera frame inspection. Physical conveyor/PLC integration, electrical inspection, universal PCB recognition and verified production defect accuracy remain outside the demonstrated boundary. No new detectors, runtime changes or PCB workarounds are introduced by this document.

## 2. Architecture and responsibilities

| Source | Responsibility |
| --- | --- |
| `frontend/src/main.jsx`, `Landmarks.jsx`, `Comparison.jsx` | Inspection lab: upload, reference/outline correction, component annotation/proposals, batches and paired evidence |
| `frontend/src/PlatformApp.jsx`, `pages/`, `platformApi.js` | Dashboard, golden library, live inspection, accounts and access management |
| `pcb_landmarks/web.py::create_app` | FastAPI routes, validation, per-photo orchestration, assets and evidence serving |
| `infer.py`, `configs/landmarks.json` | Local pose model and mounting-hole refinement/configuration |
| `registration.py` | PCB surface proposals, reference SIFT cache inputs, pose-transform verification, fallback registration, manual refinement |
| `align.py` | Ordered-point validation, inspection-to-reference homography, warp and full-source-support mask |
| `compatibility.py`, `configs/board_designs.json` | Supported-layout catalog evidence plus active-reference compatibility checks |
| `component_detection.py`, `component_model.py`, `parsa_tiling.py` | Existing local component proposals and explicit map import; proposals do not establish presence by themselves |
| `correspondence.py` | Transform all box corners and assign observed detections to expected components without duplicate assignment |
| `compare.py`, `configs/comparison.json` | Bounded structural matching, corroborated absence, shift/rotation and review decisions |
| `platform_store.py` | Transactional SQLite users/sessions, preferences, golden configurations/library, inspection summaries and review decisions |
| `simulator.py` | Queued local image simulation using the inspection pipeline |
| `train.py`, `evaluate.py`, `data.py` | Offline training, evaluation, labels and image loading |

React/Vite assets are built before offline use; FastAPI serves `frontend/dist`. CPU inference uses local model files. Default app storage is `runs/web`; `PCB_WEB_STORAGE` overrides it and `PCB_CHECKPOINT` overrides the configured pose path. The backend does not require a cloud inference service.

## 3. Data model and local storage

| Store | Implemented content |
| --- | --- |
| `runs/web/photos/<uuid>/image.png` and `photo.json` | Decoded RGB photo and sanitized display filename, dimensions, error/image URL |
| `photos/<uuid>/reference.json` | Confirmed ordered points, 3–12 point convex board polygon, reference/source/geometry metadata; temporary JSON is atomically replaced |
| `photos/<uuid>/landmarks.json`, `component-proposals.json` | Local diagnostics/proposals where generated |
| `runs/web/batches/<uuid>/report.json` | Captured request annotations, mode, sharpening, provisional comparison config and every per-photo result |
| `batches/<uuid>/<index>/` | Available `alignment.png`, `components.png`, `difference.png` evidence |
| `runs/web/aoi.db` | SQLite platform records: inspections, decisions, users, sessions, golden configurations, library, settings |
| `configs/` and local `models/` | Thresholds, landmark schema/checkpoint metadata and existing detector assets |

Reference geometry and component annotations are separate persistence operations: reference JSON stores geometry; golden configurations in SQLite hold selected reference/component configuration. Reports and images are not a single transactional package. Configuration is captured in batch reports, but complete immutable per-run hashes of all model and catalog assets are not guaranteed. Automatic retention/deletion policy is not a production lifecycle design.

## 4. Coordinate and annotation contract

Images use decoded original-resolution RGB pixels: origin at top left, x right, y down. Non-normalized EXIF orientation is rejected; upload does not silently rotate coordinates. Saved component boxes are integer, half-open `[x1,y1,x2,y2]`. NumPy crops are `[y1:y2,x1:x2]`. Minimum valid crop side is 5 pixels. Component IDs and names must be nonempty and unique; reference dimensions must match decoded dimensions. The comparison layer makes invalid boxes uncertain, while invalid region metadata rejects the request.

Four landmarks have fixed board-relative clockwise correspondence. `align._points` rejects nonfinite, out-of-bounds, duplicate, concave, crossed, mirrored and nearly collinear point geometry. The mounting-hole configuration names are `upper_left_mount`, `upper_right_mount`, `lower_right_mount`, `lower_left_mount`. Automatic reference proposals can use mounting centers or board corners; source and landmark kind identify the distinction. Outline geometry is separate from landmarks. Browser preview scaling never changes stored coordinates. Existing imported component maps are explicit operator inputs, not an automatic substitute for image-based inventory.

## 5. Training and reference workflows

### 5.1 Train and package the landmark model

Training/evaluation are offline preparation steps, separate from runtime. `configs/landmarks.json` selects `models/pcb-mounting-holes-yolo26n-pose.pt`, input size 640, board confidence 0.75 and point confidence 0.85, and records checkpoint/dataset hashes and narrow mounting-hole tuning provenance. `PCB_CHECKPOINT` can select another local checkpoint. The current configuration also enables existing mounting-hole refinement/calibration, whose scope is recorded in the configuration and [mount calibration guide](../guides/MOUNT_CALIBRATION.md).

[Step 3 results](../steps/STEP3_RESULTS.md) document an earlier model's failed readiness; [fine-tuning evidence](../guides/LANDMARK_FINE_TUNING.md) concerns the later limited mounting-hole experiment. Neither constitutes general accuracy on arbitrary PCB layouts. Training, validation, synthetic image edits and real defective-board evaluation must remain distinguishable.

### 5.2 Save a reference setup

Upload creates a UUID photo record. Reference setup can be proposed automatically or manually corrected. `surface_mask` validates a convex 3–12 point PCB outline and erodes its edge to exclude background. Reference points and outline are saved with atomic JSON replacement and cache invalidation. Component proposals are reviewable; manual rectangles remain authoritative. Saving a golden configuration requires reference setup and validated annotations, and rejects unresolved `UNKNOWN` proposals. The UI can reload the golden configuration and library after restart.

## 6. Inference pipeline

### 6.1 Batch intake and image validation

`InspectionRequest` accepts one reference ID, mode `manual` or `automatic`, 1–15 inspection IDs, 1–1000 components and strict boolean `sharpen`, `synthetic`, `simulated` flags. Default sharpening is off. Each photo upload is JPEG/PNG, at most 12 MiB, with decoded dimensions at least 2×2 and at most 20 million pixels. Upload records retain corrupt-image errors so later batches can isolate failures. IDs resolve only through server-generated local paths. Local-origin/host and request-length middleware provides additional loopback request checks.

The request supplies the component snapshot; reference/configuration is loaded for the batch. A per-photo exception handler preserves sibling results. A shared malformed request/reference can reject the whole request before per-photo processing. There is no claim that every endpoint is an authenticated production service: role checks apply to the platform operations that invoke them.

### 6.2 Landmark detection, alignment, and quality gates

The backend identifies supported catalog layouts first. Positive different-layout evidence blocks component inspection. Unknown catalog identity can still pass active-reference verification; this is not universal layout classification.

With a saved automatic reference, `register_inspection` obtains reciprocal ratio-filtered SIFT matches strictly on PCB surfaces. It checks pose landmark transforms, considering cyclic identity shifts against independent matches. If pose detection/transform is unusable, it estimates an inspection-to-reference RANSAC homography from reference features, holding every third correspondence out of fitting. Thus unavailable pose weights need not force failure when reference registration is independently verified. Projected landmarks are labeled as projected rather than raw detections.

`verify_alignment` requires at least 25 geometric inliers, at least 8 held-out inliers, 45% inlier fractions, spatial coverage of at least 20% of the reference surface, six occupied grid cells, 85% board overlap and agreement in at least five stable edge regions spanning rows and columns. Tolerances are scale dependent. Manual alignment can be refined when feature evidence improves it, then still passes compatibility/verification gates. Four-point-only paths use catalog/aligned evidence and can attempt distributed verification before accepting `SAME_DESIGN`.

`align_images` rejects ill-conditioned/nonfinite transforms, projective horizons and invalid point fits; returns warped RGB in the reference grid plus a 0/255 mask requiring full bilinear source support. The exact-raster case returns an identity grid after point validation. These gates are implemented checks, not a calibrated global guarantee against blur, glare, parallax or clipping in all scenes.

### 6.3 Crop extraction and optional sharpening

Stored reference rectangles stay fixed. Evidence crops use the reference grid; comparison searches bounded local neighborhoods rather than requiring every score to use exactly the same inspection pixels. Raw grayscale standard deviation below 2 or Sobel magnitude standard deviation below 1 yields review before sharpening. Enabled sharpening applies the same clipped unsharp operation to both inputs: `gray + 0.5 * (gray - GaussianBlur(gray, (7,7), 1))`. Disabled sharpening bypasses this operation. Coordinates and dimensions remain unchanged.

### 6.4 Crop scoring and classification

`compare_regions` uses Sobel magnitude (`ksize=3`, trimmed one-pixel border) and `TM_CCOEFF_NORMED`. Translation search is bounded to at most 24 pixels; rotation hypotheses span −30° to +30° in 3° steps. Weak broad searches fall back to a narrower footprint search. Full component mask coverage is required; explicit operator review regions remain uncertain.

Current provisional thresholds are `present_min=0.5`, `missing_max=0.25`. Low correlation alone cannot establish absence. Missing decisions require edge loss or corroborated component-body loss/substrate replacement plus changed appearance. Detector correspondence may support an absence rule or turn conflicting evidence into review; a detection alone does not prove presence. One observed component cannot satisfy multiple expected components.

A convincing rotated match (default minimum 8°) is `misaligned`. Translation deviation is judged after board registration, using component size, registration residual and consensus where available (default floor 2.5 pixels and size fraction 0.05). Overlay/coverage reliability checks can downgrade all rows to uncertainty. All numerical policies remain provisional; see the exact checked-in configuration and source for full rule conjunctions.

### 6.5 Result assembly and evidence

The actual serialized outcomes are `ok`, `defect`, `review`, `error`, `DIFFERENT_BOARD`. Component states are `present`, `missing`, `misaligned`, `uncertain`, `not_evaluated`. Reports additionally expose `alignment_state`, `classification`, per-component `classification` and `decision`, offsets/rotation/absence evidence, compatibility, reasons and available overlay URLs. `GOOD`, `MISSING_COMPONENT`, `MISALIGNED_COMPONENT`, `NEEDS_REVIEW` and `BOARD_MISMATCH` are photo classifications. Misalignment takes priority in the single classification field when both defect types exist; all rows remain visible.

Any missing/misaligned row yields `defect` with `review_required=true`; uncertainty alone yields `review`; all present yields `ok`. Blocked identity/alignment yields review or different-board, without valid component scoring. Decode/runtime errors retain explicit reasons. `retake` and `missing` photo outcomes from the original design are not current API values. The UI shows side-by-side selected crops and overlay modes. Operator confirmation/false-alarm decisions are separate persisted review records. Synthetic/simulated inputs are flagged and do not become evidence of real missing-part accuracy.

## 7. Implemented API contracts and failures

| Route family | Purpose |
| --- | --- |
| `GET /api/health` | Current schema/configuration, checkpoint availability and limits; HTTP health is not model accuracy acceptance |
| `POST /api/photos`; `GET /api/photos/{id}/image` | Upload/decode record and local image |
| `/api/references/{id}`, `/automatic`; `POST /api/landmarks/{id}` | Confirm/reload/propose geometry and detect/project inspection landmarks |
| `/api/photos/{id}/component-proposals`, `/component-map`, `/regions` | Existing image proposals, explicit map import and available sample region data |
| `POST /api/inspections`; `/api/batches/{id}/report`; `/api/batches/{id}/{index}/{kind}` | Batch request/results and available alignment/component/difference evidence |
| `/api/auth/login`, `/me`, `/api/users`, `/api/account/*` | Local authentication, roles and account preferences/password |
| `/api/dashboard`, `/api/reviews`, `/api/reviews/{inspection_id}/decision` | Persisted summaries, review queue and explicit operator decisions |
| `/api/golden-config`, `/api/golden-library` | Approved active configuration and reference library |
| `/api/simulation/*`, `POST /api/live/frame` | Imported queues, software line controls, selected reference and browser frame processing |

Schemas, HTTP verbs and role checks are defined by `web.py`; this table groups endpoints rather than proposing a replacement API. Unsupported/oversized input, unknown IDs and malformed annotations use request errors or stored per-photo decode errors as appropriate. Missing frontend assets produce a 503 with a build instruction.

### 7.1 Windows setup and offline runtime

Use the root [README](../../README.md) for current launch commands and environment preparation. Setup installs dependencies and builds/prepares local assets while online; runtime serves the built frontend on localhost and loads local weights. [Step 7](../steps/STEP7.md) and `verify_offline.py` record/check bounded packaging concerns. A final full restart with networking disabled on the submission laptop remains a separate acceptance activity; source inspection cannot prove it.

## 8. Validation and SRS traceability

[SRS Section 4.1](SRS.md#41-source-audited-traceability) maps every FR/NFR ID to implementation and existing tests. AC-01–AC-16 retain meaningful baseline acceptance goals; their vocabulary/count assumptions must be reconciled with the implemented contract before execution. Test existence does not mean a pass. This revision audits source and documentation only and does not assert that application tests, browser workflows, model evaluation or offline restart were rerun.

Historical records under [steps](../README.md#steps--implementation-record-step-by-step) and [audits](../README.md#audits--repair-recovery-and-acceptance-records) retain their original dates, fixtures, scope and results. Synthetic removals establish rule wiring, not verified accuracy on real missing components.

## 9. Open decisions and known limits

- The official assignment brief is not included; supplied requirements remain the baseline.
- Real missing-part accuracy, broad unseen-layout acceptance, threshold calibration and paired sharpening evaluation remain incomplete. No production accuracy claim follows from regression fixtures.
- Colored surface segmentation, catalog templates, mounting calibration and trained detector domains have bounded scope; pale/black boards, clutter, repeated patterns and weak texture can require manual review.
- Tall components, glare, occlusion and large perspective changes can violate the planar/local appearance model.
- Comprehensive global severe-blur/reference completeness gates, guaranteed board-contained annotations, artifact-wide transactions, complete per-run model provenance, retention and production authentication remain partial/planned.
- Target-laptop startup/batch latency, memory budgets and full offline restart must be documented with their tested environment.

## 10. Technical source of truth

The repository modules and configurations identified above define current behavior. Framework documentation explains mechanisms, not measured project performance: [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/), [OpenCV perspective transforms](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html), [OpenCV template matching](https://docs.opencv.org/4.x/df/dfb/group__imgproc__object.html), [Ultralytics pose](https://docs.ultralytics.com/tasks/pose/), [Vite production builds](https://vite.dev/guide/build.html). These links are reference pointers; this revision does not claim a fresh external-source verification.

## 11. Documentation verification record

The 24 November revision replaces the obsolete proposed-only architecture with the checked-in pipeline and records unresolved baseline obligations explicitly. Validation performed for this revision is limited to documentation checks reported with the submission; historical application results remain in their original records. No new runtime test pass, diagram render, hardware benchmark or accuracy measurement is asserted here.
