# Mounting-hole fine-tuning — November 21, 2026

The production app now uses a fine-tuned YOLO26n Pose checkpoint plus OpenCV
mounting-rim verification for the Raspberry Pi board in the user's screenshot
(`MCCB5.jpg`, 1536×1533). Four ordered keypoint identities are preserved. Manual
correction, review gates, component checks and the 15-image batch limit remain.

## Confirmed findings

- The old deployed checkpoint was loadable and schema-correct but missed the
  screenshot photo's labeled holes by 254–541 pixels. CPU/GPU, square/rectangular
  letterboxing, layer fusion and prediction-head probes did not fix it.
- Small-data fine-tuning exposed a training/evaluation BatchNorm discrepancy:
  a single-photo diagnostic got 0.6–1.6px error with head batch statistics versus
  28–58px with its saved evaluation statistics. This is evidence about that
  diagnostic, not proof that BatchNorm caused the original checkpoint's failure.
- Training pose mAP was too forgiving for screw-center accuracy. Candidate
  checkpoints were therefore selected by direct pixel checks on the fine-tuning
  validation photo, not by the summed box/pose fitness alone.
- On MDCC5 the model emitted two overlapping board proposals. The higher box
  confidence proposal had poorer keypoints. The new verification stage can select
  a fully verified alternative only when every confident box overlaps it by at
  least 0.8 IoU and all independently verified proposals agree on the same holes.
  Distinct board boxes or disagreeing verified hole sets still require REVIEW.

## Training and deployment

- Parent: `runs/landmarks/full/weights/best.pt`; preserved unchanged.
- Bootstrap diagnostic: 100 epochs on MCCB5, YOLO26 pose, 640px, frozen backbone
  and neck (`freeze=23`), AdamW, no geometry/photometric augmentation, pose weight
  100, RLE weight 0. This diagnostic is not a generalization result.
- Final pass: bootstrap `last.pt` → 150 epochs on MBCC5/MCCB5, batch and nominal
  batch 2, 640px, AdamW lr 0.0005, cosine decay, no warm-up, pose 100, kobj 2,
  RLE 0. Backbone/neck frozen; all BatchNorm modules use evaluation statistics
  during training. Mild augmentation: ±5° rotation, translation .02, scale .08,
  shear 1°, perspective .00005; no mosaic or flips.
- Fine-tuning validation: MCDC5. Test: MDCC5. These photos were held out from this
  fine-tuning pass, **but the original parent checkpoint had seen all four M
  photos**. They are not independent new captures. The unlabeled user-added
  MCCBCopy file was not modified or silently added to training.
- Validation selected `raspberry_640/weights/epoch125.pt` (zero-based snapshot
  index), requiring four verified rims within 6px of reviewed validation centers,
  then minimizing raw validation error. Test results did not select the snapshot.
- Deployed stripped copy: `models/pcb-mounting-holes-yolo26n-pose.pt`.
  SHA-256: `a3035f835ff92d57b452f7c43edf566cf83e50b9752623b00e044e4ee6d773a3`.
- `configs/landmarks.json` records the path, hash, training scope and gates.
  The web app reads that path; `PCB_CHECKPOINT` can still override the path,
  provided the bytes match the configured hash/schema.

Exact training scripts, YAMLs, source-photo lists, epoch snapshots, CSVs and
selection records are archived locally in `runs/landmarks/holes_finetune_20261121`.
`train_raspberry_640.py` is the final training invocation; its preceding bootstrap
settings are listed above. Those generated training files are ignored by Git. The selected deployment
checkpoint and the mounting-pattern PNG are committed for a usable GitHub checkout. The tracked JSON below preserves the
selected configuration, validation candidates and measured outputs.

## What places the final markers

The network alone still produces coarse proposals. Final precision comes from
**fine-tuning plus visual refinement**, not a claim that the raw network is perfect.
After board/keypoint confidence gates (>0.75 / ≥0.85), OpenCV finds visible gold
mounting rims, fits their ellipses, and requires one unique rim near each ordered
proposal. All four are mandatory. The raw coordinates and center shifts remain
in diagnostics. A tracked 256×256 board pattern (`configs/mounting-holes-M.png`)
then verifies the interior layout across four cyclic landmark assignments. It
requires gradient correlation ≥0.35 and a ≥0.15 margin over the next assignment.
This corrects landmark identities for the verified 180° case and rejects
unrelated boards even when four gold rings are visible.

This is calibrated to these large gold rims: HSV hue 5–45, saturation ≥50,
value ≥25; ellipse minor/major ratio ≥0.6, contour fill ≥0.8, diameter between
max(18px, 4.5% of the shorter raster side) and 10% of that side. Very bright
centers are excluded. Duplicate inner/outer edges are clustered. Search is bounded
to 15% of the image diagonal around each proposal, below the separation of these
board's mounting holes. This is a broad correction bound; the visual geometry and
uniqueness checks are essential. Different plating, much smaller boards, glare,
occlusion or unsupported orientation may require Manual/REVIEW.

Relevant code: `pcb_landmarks/infer.py` (`refine_mounts`, `assess_mounts`,
`LandmarkDetector.predict`), `pcb_landmarks/web.py` (configured checkpoint loading),
and `pcb_landmarks/train.py` (nominal batch and warm-up correction).

## Results in original-image pixels

| Photo | Raw network maximum error after fine-tuning | Final refined maximum error | Outcome |
| --- | ---: | ---: | --- |
| MCCB5, screenshot photo | 76.94px | **3.40px** | Accepted |
| MBCC5, training view | See JSON | 6.18px | Accepted |
| MCDC5, validation angle | 87.15px | **4.23px** | Accepted |
| MDCC5, test angle | 224.37px | **4.67px** | Accepted after duplicate-proposal verification |
| Mild perspective warp of MCCB5 | See JSON | **3.37px** | Accepted |
| Clipped board | — | — | REVIEW, no scoring |
| 180° rotation of MCCB5 | See JSON | **3.40px**, identities corrected | Accepted |
| Unrelated BeagleBone board | — | — | REVIEW, pattern not verified |
| 90° rotation | — | — | REVIEW, no scoring |

Centers are compared with existing reviewed labels, which themselves have a few
pixels of annotation uncertainty. These figures do not establish perfect placement
or general accuracy across new cameras, designs or arbitrary rotations.

The live production HTTP upload → landmarks → inspect flow was exercised with one
processor control box. Identical, mild warp, MCDC5 and MDCC5 returned PRESENT with
scores 1.0000, 0.9865, 0.8410 and 0.7973 respectively, with zero MISSING alerts.
The 180° case also returned PRESENT (score 1.0000), with corrected landmark
identities. Clipped, unrelated-board and 90° cases returned REVIEW. Direct and live-API accepted points matched
exactly. The production browser test also confirms four accepted screenshot-photo
markers within 4px of the reviewed centers.

[Tracked evidence JSON](results/landmark-finetune.json) ·
[Corrected screenshot-photo overlay](../runs/landmarks/holes_finetune_20261121/MCCB5-verified.png) ·
[Production browser screenshot](../runs/landmarks/holes_finetune_20261121/browser-accepted.png) ·
[Live API evidence](../runs/landmarks/holes_finetune_20261121/live-app-evidence.json)

Regression verification: **49 Python tests, 2 coordinate tests, 7 browser tests,
production build and git diff --check passed**. The tests cover
ring refinement, absent/clipped rims, distant proposals, duplicate versus separate
boards, manual editing, the earlier BeagleBone manual workflow, and 15-photo batches.
Real missing-component accuracy and independent new-photo testing remain unverified.
