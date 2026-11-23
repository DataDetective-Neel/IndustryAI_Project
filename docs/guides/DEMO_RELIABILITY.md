# One-board inspection evidence — November 21, 2026

> Historical baseline: recovery work on November 22 adds provisional multi-evidence
> synthetic `MISSING` and isolated-offset `MISALIGNED` findings. No verified real
> missing-component pair exists, so real-photo accuracy remains unmeasured.

**Historical baseline before mounting-hole fine-tuning.** Current Raspberry Pi automatic-mode results are in [LANDMARK_FINE_TUNING.md](LANDMARK_FINE_TUNING.md).

Target submission: November 24. Scope: micropcb_E, ECCC5 known-good reference, eight named component regions.

## Confirmed findings

1. The automatic failure is already present in the checkpoint output on the exact uploaded raster. No checkpoint, class/keypoint schema, coordinate rescaling, point-order or homography-direction mismatch was found. The frozen confidence gate rejects inaccurate points correctly; relaxing it would not fix localization.
2. The confirmed false-MISSING source was `compare_regions`: a single low correlation at a fixed crop previously became `missing`. Small displacement, parallax or appearance changes could therefore become false absence claims. That rule is removed.
3. Automatic landmark placement remains blocked by the existing checkpoint’s poor localization. No retraining or feature-based alignment was introduced. Manual correction is the viable submission workflow.

## Checkpoint and actual request trace

Resolved checkpoint: `A:\IndustryAI_Project\runs\landmarks\full\weights\best.pt`. Present **yes**, loadable **yes**, runtime architecture `yolo26n-pose.yaml`, scale `n`.

SHA-256: `3a8646d5b36b417764647751ef029a7af824321e750f0492b61e916124ec7b9e` (matches `configs/landmarks.json`).

Frontend `main.jsx` Automatic radio → `useEffect` POST `/api/landmarks/{photo_id}` → `pcb_landmarks.web:app` → `detect` → cached `_detector` → `LandmarkDetector.predict` → Ultralytics pose prediction → `assess`. Inspection POST `/api/inspections` uses the same detector and accepted point order, then `align_images`, then `compare_regions`. Both reference and inspection diagnostics are included even if reference detection fails.

Training and inference agree: class **0 = pcb**, one board row with 17 values (class, normalized box, four x/y/visibility triples), pose shape **[4,3]**. Landmark IDs are keypoint indices, not four object classes: **L0 upper_left_mount, L1 upper_right_mount, L2 lower_right_mount, L3 lower_left_mount**. No spatial sorting or duplicate-ID selection is performed. Multiple confident board detections are rejected; coincident keypoints and invalid cyclic geometry are rejected.

Upload decodes JPEG/PNG to a fixed RGB raster and saves PNG. Non-normal EXIF orientation is explicitly rejected, not silently rotated. Ultralytics handles PIL RGB conversion, resizing and letterboxing; installed `PosePredictor.construct_result` calls `ops.scale_coords` back to original dimensions. The app consumes those pixel coordinates directly, without another resize reversal. Raw diagnostics mean library postprocessed candidates above 0.001, max_det=20, not unfiltered network tensors. Acceptance remains board >0.95 and each keypoint >=0.99.

Direct prediction on each exact app-saved PNG equals the `/api/landmarks` response, including all candidate coordinates. The reference raster also matches **14 existing app uploads** listed in the JSON evidence. No particular user retest/upload ID was specified; the reproducible diagnosis uses these existing E-board images.

## Direct inference versus app

All primary candidates below are rejected by the API as `no_confident_board`; every listed keypoint also fails the 0.99 point gate. Accepted points: **none**. Coordinates are decoded original-image pixels.

| Image | Board confidence | L0–L3 confidence | Landmark error versus reviewed labels (px) |
| --- | ---: | --- | --- |
| reference | 0.9204 | 0.0359, 0.1979, 0.1059, 0.6177 | 229.7, 306.4, 251.7, 250.2 |
| mild_perspective | 0.8806 | 0.0386, 0.1737, 0.1382, 0.5582 | 179.5, 226.6, 276.9, 300.7 |
| real_angle_ECCB5 | 0.9229 | 0.0376, 0.1081, 0.0794, 0.6146 | 169.3, 258.3, 211.3, 245.7 |

The generated mild warp has additional low-confidence board candidates (0.0446 and below), including clipped edge points; all IDs, boxes, coordinates and rejection reasons are retained in JSON. The original ECCC5/ECCB5 primary predictions contain four distinct interior coordinates, but they are hundreds of pixels from the labeled mounting holes. Frozen validation metadata already records `validation_usable=0` and `validation_accurate=0`; confidence alone is not evidence of geometric accuracy.

| Reference ID | Raw (x,y) | Reviewed (x,y) |
| --- | --- | --- |
| L0 | (264.75, 606.49) | (256.73, 376.89) |
| L1 | (960.55, 679.73) | (953.35, 373.42) |
| L2 | (771.78, 1112.59) | (908.95, 1323.61) |
| L3 | (498.51, 1162.68) | (308.07, 1325.00) |

[Reference overlay: green reviewed / red raw](../../runs/demo-evidence/reference-landmarks.png). [Mild perspective overlay](../../runs/demo-evidence/mild_perspective-landmarks.png). [Real angled ECCB5 overlay](../../runs/demo-evidence/real_angle_ECCB5-landmarks.png).

## What changed

- Inference retains below-threshold candidate evidence, resolved checkpoint, schema, thresholds, landmark IDs/confidences/coordinates and rejection reasons. Each app photo saves `landmarks.json`; inspection reports include both detections. UI shows tentative rejected points and raw diagnostics, with Manual correction preserving existing clicks.
- Eight named planar component boxes are stored in `configs/components-ECCC5.json`: U2, AM335x, U14, U13, U12, U11, Y3 and U16. They auto-load only for the exact decoded known-good reference, not a matching filename. A one-pixel-modified same-name image is rejected for preset loading.
- In reference coordinates, each template searches a radius of 8% of its smaller side, bounded to 1–6 pixels. This cannot reach adjacent full components in these saved regions. Every expected region and candidate patch must have full warped valid-pixel support. The output exposes the expected box, search radius, best offset, score, coverage and reason.
- The existing Sobel/OpenCV correlation is reused. No new dependency or SSIM stage. Low texture, clipped support, explicit review flags, ambiguous appearance and unreliable alignment yield REVIEW.
- Alignment validation measures masked/downscaled gradient overlay correlation and consistent local matches: score >=0.35 or >=60% of regions (at least two) matching with offset spread <=3px, plus >=60% valid image coverage. These are provisional demo gates. An invalid/zero overlay with all local checks failing returns REVIEW even when homography fitting reports success.
- **MISSING is deliberately withheld for this board until verified absence evidence exists.** This demo implements PRESENT/REVIEW; neither low similarity nor a synthetic erasure certifies absence. The legacy missing_max field remains readable for config compatibility but does not classify components.
- Pre-existing modifications to `align.py` and `test_align.py` were preserved. Their exact-raster identity shortcut was already present at task start; it is not attributed to this change.

## Runtime results

The normal production React upload-and-inspect UI and FastAPI routes were exercised. Manual entries use existing reviewed landmark labels; generated inspection points are derived from the saved transform, not independent human re-clicks.

| Case | Manual result | Automatic result | Verdict |
| --- | --- | --- | --- |
| Identical real photo pair | 8/8 PRESENT, overlay 1.0000, zero MISSING | REVIEW; no points accepted | Manual PASS; automatic placement FAIL |
| Mild perspective warp of intact ECCC5 | 8/8 PRESENT, overlay 0.998970, zero MISSING | REVIEW; no points accepted | Manual PASS; automatic placement FAIL |
| Badly cropped image (left half removed) | REVIEW; out-of-image landmarks rejected, no scoring/MISSING | REVIEW | PASS safety gate |
| Unrelated/misaligned image, formally successful alignment | REVIEW for all; no MISSING | Not a model acceptance test | PASS regression |
| Zero/invalid overlay and failed local checks | REVIEW for all despite alignment status ok | Not a model acceptance test | PASS regression |
| SIMULATED U2 erasure, separately labeled | 7 PRESENT + U2 REVIEW, zero MISSING | REVIEW | PASS ambiguous-defect review; missing detection NOT demonstrated |
| Existing real ECCC5/ECCB5 angled pair | 6 PRESENT + U11/Y3 REVIEW, zero MISSING | REVIEW | PASS conservative workflow; all-visible-PRESENT target not achieved on this additional real-angle pair |
| Verified real missing-component pair | Unavailable | Unavailable | NOT RUN |

Inspection→reference H is fitted from `ip` to `rp`; the saved `transform.json` records both directions. At eight component centers beyond the four fitted landmarks, transformed-point max error with reviewed/known points is **0.00003278 px**. The rejected raw YOLO point sets would give **49.0–106.7 px** errors at those same features. All eight mild-warp local match offsets are **(0,0)**; scores range **0.9643–0.9874**. The tiny matrix error is a synthetic transform-consistency check, not a claim of that accuracy on independently captured real photos.

[Full runtime JSON](../results/demo-reliability.json), [generated matrix](../../runs/demo-evidence/transform.json), [mild-warp component overlay](../../runs/demo-evidence/mild_perspective-manual-component.png), [browser cases screenshot](../../runs/demo-evidence/browser-three-cases.png), [browser JSON](../../runs/demo-evidence/browser-evidence.json). Generated assets live in ignored runs/; the JSON snapshot here is tracked and the command regenerates assets.

## Verification and reproduction

```powershell
.\.venv\Scripts\python.exe -m pcb_landmarks.demo_check
.\.venv\Scripts\python.exe -m unittest discover -s tests
Set-Location frontend
npm test
npm run test:browser
```

Recorded checks: **43 Python tests**, **2 coordinate tests**, **5 browser tests**, production build and `git diff --check`. Browser coverage includes real UI input, saved regions, manual correction, automatic rejection, CLI parity, upload failures, synthetic labeling, Vite/production rendering and mobile width.

Remaining inputs: no verified same-board absent-component photo/annotation or independent new angle-capture set was supplied. No model replacement, retraining, feature-based alignment, SSIM, general board support or real missing-part accuracy claim. For November 24, use Manual with ECCC5 and the saved eight regions; REVIEW is an explicit demo outcome.
