# Step 4: four-point alignment and overlay

Implemented 20 November 2026 using the reviewed Step 2 labels. The frozen
[Step 3 detector](STEP3_RESULTS.md) still rejects development images; its weights,
thresholds, inference contract, dataset labels and splits are unchanged.
This step produces geometric review assets, without component verdicts.

## Windows reproduction

Use the existing [Step 3 environment](STEP3.md#windows-setup). Run in PowerShell:

```powershell
Set-Location A:\IndustryAI_Project
.\.venv\Scripts\python.exe -m pcb_landmarks.align --reference PCB_Dataset_Pilot/images/val/ECCC5.jpg --inspection PCB_Dataset_Pilot/images/val/ECCB5.jpg --reference-label PCB_Dataset_Pilot/labels/val/ECCC5.txt --inspection-label PCB_Dataset_Pilot/labels/val/ECCB5.txt --output runs/alignment/ECCC5-ECCB5-verified
```

The output directory must be new. This exact command was run successfully;
choose a different `--output` directory when repeating it on this checkout.
All files use **ECCC5's decoded reference grid: width 1174, height 1536**.
Inspection ECCB5 decodes to 1162 x 1536. Outputs are local and ignored by Git:

- `A:\IndustryAI_Project\runs\alignment\ECCC5-ECCB5-verified\aligned.png`
  — RGB inspection warped into reference pixels, black outside source coverage.
- `A:\IndustryAI_Project\runs\alignment\ECCC5-ECCB5-verified\overlay.png`
  — 50/50 reference/aligned blend inside valid overlap; darkened reference with
  **magenta diagonal hatching** outside overlap. Hatching is an invalid-area
  indicator, not a board difference.
- `A:\IndustryAI_Project\runs\alignment\ECCC5-ECCB5-verified\overlap_mask.png`
  — single-channel uint8: **255 valid, 0 exclude from Step 5**.
- `A:\IndustryAI_Project\runs\alignment\ECCC5-ECCB5-verified\alignment.json`
  — status, decoded dimensions, inspection-to-reference H, full-frame valid
  fraction and output paths. The same JSON is printed to stdout.

Success exits 0. Rejected images, labels, geometry, transforms, existing output
directories or write failures print `status: failure` with a reason and exit 2.
Input validation completes before creating the output directory. If a disk/write
failure leaves a partial directory, discard it and rerun into a new directory;
only exit 0 plus `alignment.json` indicates a completed run.

## Coordinate and validation contract

`pcb_landmarks.align.align_images(reference, inspection, reference_points,
inspection_points)` accepts decoded RGB uint8 arrays and two `(4,2)` pixel arrays.
It returns `(aligned_rgb, homography_inspection_to_reference, valid_mask)` and
raises `ValueError` for invalid input/geometry. No confidence/model decision is
made here. A future caller must first require `LandmarkDetector.predict` status
`ok` and matching layout/schema, then pass `[[p['x'], p['y']] for p in
result['landmarks']]` in the returned order. These are already decoded pixels.

The CLI uses the shared `read_image` and `read_label` readers. Dataset labels
contain class 0, normalized box, then four x/y/visibility triples. Only four
visible (visibility 2) reviewed landmarks are accepted here. Each normalized x/y
is multiplied by **that decoded image's width/height**, never manifest sizes,
model input sizes or the other image's dimensions. The shared reader rejects
EXIF orientation other than 1; normalize and annotate in that raster first.
There is no silent rotation that would invalidate annotations.

Identity order is `upper_left_mount`, `upper_right_mount`, `lower_right_mount`,
`lower_left_mount` in the board's canonical orientation. Points are never sorted
by their current screen location, including after rotation. Validate:

- Exactly four finite x/y pairs, `0 <= x < width`, `0 <= y < height`.
- Pairwise distances at least 1 pixel; positive cyclic turns, rejecting crossed,
  concave or mirrored order. Every triangle's minimum altitude must be at least
  `max(1 pixel, 0.001 * image_diagonal)`, rejecting nearly collinear triples.
- Finite OpenCV four-point homography, condition number <= 1e8 after scaling
  source/destination to image-relative coordinates, no projective horizon
  crossing the inspection raster, fitted residual <= 0.1 pixel and nonempty
  valid overlap. These are numerical safeguards, not calibrated quality gates.

OpenCV `getPerspectiveTransform` fits inspection -> reference; `warpPerspective`
uses bilinear interpolation and reference width/height. The mask warps an all-one
source with the same interpolation and accepts only full source support. It also
checks inverse-mapped coordinates against source bounds (1e-7 pixel roundoff
tolerance), excluding fractional exterior pixels even when OpenCV rounds its
sampling location onto an edge. This is more conservative than a nearest-neighbor
mask, which can admit pixels mixed with artificial border values.

Mask validity describes photographed **image coverage**, including background;
it does not identify the board, missing parts, glare or occlusions. Step 5 must
use it to exclude invalid pixels, with separate region/quality policies later.

## Verification actually performed

Environment: Windows, CPython 3.10.11, OpenCV 4.13.0, NumPy 2.1.3, Pillow 11.3.0;
existing local `.venv`, no new dependencies or network/model access for alignment.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**17 tests passed, 0 failures/errors, 3.737 seconds**: all 10 existing tests plus
7 new alignment tests. The initial run failed because alignment was absent.
A subsequent regression caught OpenCV admitting a 0.01-pixel exterior location;
the inverse-bound check fixed it. Cases cover independent controls, raster
agreement, mask exclusion/interior inclusion, blend/invalid appearance, a 180-degree
rotation retaining IDs, count/shape/nonfinite/bounds failures, duplicates and
near-degeneracy, crossed/concave/mirrored geometry, horizon rejection, actual
decoded dimensions, CLI output files/JSON, invisible landmarks, existing output
protection, missing images and EXIF rotation rejection.

### Synthetic perspective proof

The original, publication-safe generator is committed in
`tests/alignment_fixture.py`; it contains no photographs. It builds a 320 x 240
PCB-like reference, a 300 x 280 inspection raster, four landmarks, five independent
chip-center controls and a known reference-to-inspection homography:

```text
 0.92     0.12   -18
-0.08     1.08    18
 0.0005  -0.0004   1
```

The independent controls are `(80,65), (160,120), (255,180), (75,195), (240,55)`;
none is a fitted landmark. The largest recovered control error was
**0.000008201 pixel** (test limit 0.001 pixel). Mean absolute RGB error inside
the valid mask eroded by 2 pixels was **1.778575 / 255** (test limit 8).
Valid coverage was **95.9921875%**; inverse coordinates from the known transform
independently confirmed exterior pixels were excluded. A separate half-pixel and
0.01-pixel translation test excludes interpolation/rounding border contamination.

The synthetic CLI also exited 0; its overlay and border hatching were inspected.
To recreate those local assets with a fresh pair of directory names:

```powershell
.\.venv\Scripts\python.exe tests/alignment_fixture.py --output runs/alignment/synthetic-input
.\.venv\Scripts\python.exe -m pcb_landmarks.align --reference runs/alignment/synthetic-input/reference.png --inspection runs/alignment/synthetic-input/inspection.png --reference-label runs/alignment/synthetic-input/reference.txt --inspection-label runs/alignment/synthetic-input/inspection.txt --output runs/alignment/synthetic
```

### Real development-pair review

**Suitable reviewed pair available; CLI and visual review completed.** The exact
first command above uses validation layout `micropcb_E`: ECCC5 (front-facing,
complete-board reference) and ECCB5 (noticeably oblique view; visible housing sides
and foreshortening). The manifest records manual point placement for ECCC5 and
feature projection with visual review for ECCB5. These are the reviewed initial
Step 2 labels, not independent pixel-level ground truth. No held-out F/K data
was used, no new labels were fitted, and no detector settings were changed.

CLI status was `ok`; final valid full-frame overlap was **99.5421635%**. The final
full overlay was viewed, along with enlarged reference/aligned/blend crops away
from mounting holes. Reference crop bounds and observations:

| Feature | Bounds (x1,y1,x2,y2) | Observed result |
| --- | --- | --- |
| U2 pins/body | (370,430,490,550) | Body/pin rows largely coincide, with small visible edge ghosts. |
| AM335x lower edge | (510,890,755,955) | Main chip edge largely coincides; small residual offset remains in fine pins/traces. |
| Ethernet metal housing | (510,105,780,450) | Clear horizontal double edge at the housing top/sides; tall headers and bottom connector also show displacement. |

The oblique view demonstrates the limit of aligning one PCB plane: elevated
components have parallax, while lighting/metal markings also differ. This pair
is useful visual verification of the warp, **not proof of comparison readiness**.
The CLI's `ok` means assets were generated, not that a quality gate accepted the
photo or that all parts are present. An additional in-plane-rotated development
view, EBCC5 -> ECCC5, also exited 0 (96.2255665% overlap before the final conservative
subpixel refinement); its overlay showed much closer connector/chip-edge agreement.

No real-pair numerical independent-control ground truth or automated parallax,
layout, blur/glare or component-coverage acceptance calibration was performed.
Four fitted points cannot independently verify identities or accuracy. No scoring,
sharpening, UI or production-readiness claim is part of Step 4.

## Publication and checkpoint scope

Only alignment source, tests, the original synthetic generator and documentation
are added. No private photos, generated run images, feature crops, caches, weights
or machine-specific run JSON are published. Existing real inputs were already
tracked and publication-cleared: Adam Byerly (frettapper), **micro-PCB Images**,
Kaggle version 2, CC BY 4.0, per the [Step 2 provenance](../../PCB_Dataset_Pilot/README.md).
The local real overlays blend/warp those sources. Their outputs stay under ignored
`runs/alignment/`. Reproduction uses the existing normal-push branch
`origin/docs/pcb-srs-sdd-dfd`; no history rewrite is required.
