# Targeted AOI changes — November 23, 2026

## Changed files

- `configs/component_model.json`: checkpoint SHA256, native 1024 px tiles, 20% overlap, confidence 0.25, IoU 0.45.
- `pcb_landmarks/component_model.py`: cached, locked pretrained YOLO26 locator inference and decoded-image coordinates.
- `pcb_landmarks/parsa_tiling.py`, `pcb_landmarks/PARSA_LICENSE.txt`: ParsaVictor tiled inference and global NMS, with MIT attribution. Array input avoids temporary image files.
- `pcb_landmarks/component_detection.py`: replace contour-based component proposals; preserve supplied reference maps and optional correction workflow.
- `frontend/src/main.jsx`: remove visible PCB contour while retaining component boxes, reference points, and internal polygon configuration.
- `pcb_landmarks/registration.py`: resolve cyclic landmark identities with independent board-feature reprojection evidence before fitting the final homography.
- `pcb_landmarks/web.py`: live reference upload/selection; reuse existing photo, automatic-reference, component, and inspection functions. Reject positively different layouts before eager reference setup. Allow up to 1,000 components instead of truncating dense-board detections at 100.
- `frontend/src/pages/LiveInspection.jsx`, `frontend/src/platform.css`: golden upload, processing state, preview, replacement and errors within the existing interface.
- `tests/test_component_detection.py`, `tests/test_parsa_tiling.py`, `tests/test_reference_reuse.py`, `tests/test_live_golden.py`, `tests/test_web.py`, `frontend/tests/repair-workflow.spec.js`: model, coordinates, duplicate suppression, cyclic identities, reference replacement, and browser regressions. Synthetic rectangles no longer serve as component-detector positives; empty detections explicitly require correction.
- This results file.

## Test results

- Component tests: 5 passed. Actual Parsa locator detects 61 on-board components in the supplied golden ELEGOO photograph. Visual output is `runs/targeted-repair/components.png`; raw detections are in `components.json` alongside it.
- Tiling regression: passed. A 1500×1300 image covers all four final 1024 px tiles; offsets map to original coordinates. Overlapping duplicate boxes are suppressed.
- Reference reuse: 9 passed, including rotated cyclic predictions and feature fallback. Existing calibrated mounting tests: 5 passed. Inference tests: 4 passed. Landmark checkpoint and preprocessing remain unchanged.
- Board compatibility: 6 passed after moving automatic setup behind positive mismatch rejection. Different boards do not reach component comparison.
- Live reference API test: passed using real pretrained weights. PNG golden upload, JPEG replacement, four saved reference points, original/rotated registration, zero missing detections on the identical image, failed-upload preservation, and reference replacement between live frames were exercised.
- Dedicated browser checks: 2 passed. They cover golden upload, map import, no contour polygon in the editor, comparison tabs, saved reports, live preview, live frame use, and replacing the reference without restarting.
- Existing browser checks: 5 passed for component proposals, crash recovery, and live image queues.
- Frontend build and 4 JavaScript unit tests passed.

Final full backend regression: **97 tests passed** in 170.683 seconds. The initial run exposed the obsolete synthetic-positive detector test; replacing it with a real PCB image and adding explicit no-detection handling produced this clean rerun.

## Commits

1. `3e6bc24`: component model integration and contour removal; pushed and remote SHA verified.
2. `052cf77`: cyclic landmark correspondence and alignment verification; pushed and remote SHA verified.
3. Live golden upload and final regression tests: final commit hash is reported in the response.

## Unresolved issues and deployment inputs

- Component detection is not complete inventory coverage. Some side headers are missed. Against the supplied 34-box golden map, only 12 boxes have a detection with IoU ≥0.5; the model also detects many smaller components absent from that map. This is not a precision/recall score for all visible parts. Manual correction remains available; no perfect localization claim is made.
- The fine-class pretrained model was also inspected: it did not recover the missing side headers. The integrated model is the dedicated `any_best.pt` locator; no model was trained.
- The existing Live Inspection input is a simulated image queue. Real frames traverse the production inspection API, but physical camera hardware was not tested and no camera adapter was added.
- Live-upload selection lasts for the running backend session. Existing saved Lab references remain persisted separately. Each frame captures one reference; replacement affects subsequent frames.
- Pretrained weights are installed locally at `models/pcb-components-yolo26s.pt` and remain Git-ignored, matching the existing landmark-weight policy. On another machine, copy `A:/parsa/pcb-component-detection-yolo26/weights/any_best.pt` there, or set `PCB_COMPONENT_CHECKPOINT`. The configured SHA256 is `1065cdb4a32d65799b6308dc267ec9c66a1a0d261293738417bff316697725ec`.
