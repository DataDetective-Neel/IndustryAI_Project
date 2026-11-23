# Step 5: component comparison and review report

Implemented on 20 November 2026 after [Step 4](STEP4.md), using its decoded
reference grid, aligned RGB inspection and conservative validity mask. This is
a provisional region comparator, not complete application acceptance. Step 3's
frozen detector remains unchanged; reviewed Step 2 landmarks still supply alignment.

## Exact PowerShell commands

Use the existing [Step 3 environment](STEP3.md#windows-setup). From PowerShell:

```powershell
Set-Location A:\IndustryAI_Project
# Fresh checkout: first generate the Step 4 assets (directory must be new).
.\.venv\Scripts\python.exe -m pcb_landmarks.align --reference PCB_Dataset_Pilot/images/val/ECCC5.jpg --inspection PCB_Dataset_Pilot/images/val/ECCB5.jpg --reference-label PCB_Dataset_Pilot/labels/val/ECCC5.txt --inspection-label PCB_Dataset_Pilot/labels/val/ECCB5.txt --output runs/alignment/ECCC5-ECCB5-verified
# Step 5, sharpening OFF (default):
.\.venv\Scripts\python.exe -m pcb_landmarks.compare --reference PCB_Dataset_Pilot/images/val/ECCC5.jpg --aligned runs/alignment/ECCC5-ECCB5-verified/aligned.png --mask runs/alignment/ECCC5-ECCB5-verified/overlap_mask.png --regions configs/components-ECCC5.json --config configs/comparison.json --output runs/comparison/ECCC5-ECCB5-off
# Identical pair, regions and thresholds, sharpening ON:
.\.venv\Scripts\python.exe -m pcb_landmarks.compare --reference PCB_Dataset_Pilot/images/val/ECCC5.jpg --aligned runs/alignment/ECCC5-ECCB5-verified/aligned.png --mask runs/alignment/ECCC5-ECCB5-verified/overlap_mask.png --regions configs/components-ECCC5.json --config configs/comparison.json --sharpen --output runs/comparison/ECCC5-ECCB5-on
```

These alignment assets already exist on the development checkout; do not rerun
the alignment command there. Comparison commands were executed with the default
`configs/comparison.json` (equivalent to the explicit `--config` above). Each
output directory must be new; choose fresh names when repeating commands.

Each comparison saves `report.json` and `overlay.png` under its output directory:
for the off run, these are
`A:\IndustryAI_Project\runs\comparison\ECCC5-ECCB5-off\report.json` and
`A:\IndustryAI_Project\runs\comparison\ECCC5-ECCB5-off\overlay.png`.
The on run uses `ECCC5-ECCB5-on`. All coordinates and raster dimensions are
**ECCC5 reference pixels, 1174 x 1536**; rectangles are never resized after warp.
The overlay blends raw reference/aligned pixels, shows names plus Present (green),
Missing (red), Needs review (amber), and retains Step 4's magenta invalid-area
hatching. Its title records sharpening; it displays raw evidence in both modes.
Full overlays and enlarged comparison crops were visually inspected locally.

JSON is also printed to stdout. Exit 0 means report/assets were produced, including
reports with Missing or Needs review findings. Exit 2 means error or failed
alignment; inspect `outcome` and `reason`, not just the process status. Existing
output directories are never overwritten. A write failure can leave partial
assets: discard that incomplete directory and repeat with a fresh output name.

## Reused region format and selected features

The existing `PCB_Dataset_Pilot/inspection_controls.json` defines component fields
`id`, `name`, `bbox_xyxy_px`, with `reference_image` and `reference_wh_px` at the
file level. Step 5 uses that format. The existing F-layout controls were **not**
used for threshold development. The new `configs/components-ECCC5.json` contains:

| ID / display name | Half-open reference xyxy | How selected / handling |
| --- | --- | --- |
| U2 / U2 chip | [370,430,490,550] | Low-profile body/pins, inspected in Step 4 and enlarged reference/aligned/blend crops; visually present. Score it. |
| AM335x / AM335x processor | [510,700,755,955] | Extended Step 4's reviewed lower edge to include the processor body and pins. Enlarged crops confirm presence and largely coincident planar edges. Score it. |
| ethernet / Ethernet housing | [510,105,780,450] | Double top/side edges in the oblique ECCB5 overlay, visible side walls. Explicit parallax review. |
| usb / USB housing | [340,1200,565,1430] | Displaced metal edges/slots in original and blended crops. Explicit parallax review. |

The only new optional region field is nonempty text `review_reason`. Its presence
blocks classification and preserves its explanation. Flags in this example were
chosen by visual review of **this pair**, before trusting connector scores; they
are not automatic parallax detection or transferable acceptance calibration.
Region IDs/names must be unique and nonempty, and the component list nonempty.
Dimensions must match the decoded reference. The CLI additionally checks the named
reference's basename. Malformed, out-of-bounds, fractional, empty or smaller-than-5x5
boxes become Needs review with a null score/overlap and null usable box; other
valid components still run. Invalid shared schema/dimensions fail the whole run.

## Alignment and coverage gates

The CLI requires Step 4 metadata. By default it reads `alignment.json` beside
`--aligned`; use `--alignment-report PATH` for an explicit success/failure JSON.
Successful metadata must match decoded reference dimensions and the supplied
aligned/mask output paths. Aligned RGB and binary uint8 mask must match the
reference grid; RGB masks, nonbinary masks, mismatched shapes and unnormalized
EXIF orientation are rejected. No image is silently resized or rotated.

If Step 4 reports `status: failure`, preserve its reason, return `outcome: retake`,
set every component to `not_evaluated`, and save no overlay. Scores and overlaps
are null, classification is skipped, and `review_required` is false (a global
retake, not a classified uncertain component). Aligned/mask images need not exist
on that path. This CLI path was verified with a synthetic failed-alignment report.

For valid alignment, overlap is the fraction of 255-valued pixels in the whole
component rectangle. **100% coverage is required**; any 0 pixel makes that region
Needs review with a null score. Invalid padding is never scored, filled or excluded
from a selectively reduced comparison crop. Per the Step 5 request, partial local
coverage produces a region-level review while covered regions can still be scored;
the full application's global coverage/retake policy remains to be calibrated.
Explicit review flags are then checked before any crop scoring.

Metadata/path/dimension checks prevent common mix-ups; they do not authenticate
the pixels or prove correct layout, identities or alignment. Use the correct
known-good reference and visually reviewed alignment. Automatic independent
alignment, blur/glare and occlusion quality gates are still pending.

## Correlation, provisional thresholds and sharpening

Both same-position crops are converted RGB -> grayscale float32. Before sharpening,
each must have grayscale standard deviation >= 2 intensity units and Sobel-magnitude
standard deviation >= 1. Low texture on either side means Needs review, even if
an apparent absence produced a flat crop; sharpening cannot rescue this gate.
Sobel uses a 3x3 kernel; magnitude maps drop their outermost pixel row/column.
Use `cv2.matchTemplate(..., TM_CCOEFF_NORMED)` on equal-size maps for one zero-mean
normalized correlation at the saved location, with no translation search or crop
resizing. Post-processing degenerate/nonfinite features or uninterpretable scores
also produce Needs review; a score is not a probability of presence.

`configs/comparison.json` supplies **provisional** thresholds:

- `score <= missing_max` (0.25): Missing.
- `score >= present_min` (0.50): Present.
- Between them: Needs review (`uncertain` in machine-readable status).

Require finite `-1 <= missing_max < present_min <= 1`. Thresholds were informed
by E-layout's two visibly present regions (off scores 0.5905 and 0.5161), the
original synthetic retained chip (0.9757), and textured synthetic removal (0.2056).
The pilot uses a small gap above the observed synthetic missing score and below
the lowest known-present real score. This is development fitting on these same
examples, **not held-out validation** or calibrated real-defect accuracy. No F/K
test views tuned these values; no real missing-part pair was available. Low
correlation from unflagged parallax, glare or misalignment can still be a false
Missing finding. Threshold changes require new development evidence.

Sharpening is off by default. `--sharpen` applies exactly the same float32 unsharp
operation after crop extraction to both grayscale crops:
`clip(gray + 0.5 * (gray - GaussianBlur(gray, (7,7), sigma=1)), 0, 255)`.
It changes neither crop dimensions nor coordinates. The report records the full
configuration, gates, feature method, sharpening flag/parameters, input paths,
per-component ID/name/box/overlap/score/status/display status/reason and overlay path.
Missing findings take outcome precedence over uncertainty while preserving
`review_required=true`; otherwise any uncertain region yields `review`, and all
Present yields `ok`. These are pilot comparison outcomes, not full-app quality OK.

## Measured paired results

Same images, regions and thresholds in both modes; all runs exited 0. Dashes mean
classification was gated and the report's score is null.

| Pair / region | Overlap | Sharpen off | Sharpen on | Decision off -> on |
| --- | ---: | ---: | ---: | --- |
| Real ECCC5/ECCB5: U2 | 100% | 0.590488 | 0.583239 | Present -> Present |
| Real ECCC5/ECCB5: AM335x | 100% | 0.516060 | 0.508760 | Present -> Present |
| Real ECCC5/ECCB5: Ethernet | 100% | — | — | Needs review -> Needs review (parallax) |
| Real ECCC5/ECCB5: USB | 100% | — | — | Needs review -> Needs review (parallax) |
| Synthetic: retained chip | 100% | 0.975747 | 0.984278 | Present -> Present |
| Synthetic: removed chip | 100% | 0.205553 | 0.240785 | Missing -> Missing |
| Synthetic: coverage control | 54.270833% | — | — | Needs review -> Needs review (coverage) |

Real photo outcome: `review`, two Present and two uncertain (0 Missing), both
modes. Synthetic outcome: `missing`, one Present, one Missing, one uncertain,
`review_required=true`, both modes. No decisions changed across seven component
rows. All four available scores changed: U2 -0.007249; AM335x -0.007301; retained
synthetic +0.008531; removed synthetic +0.035232. Sharpening moved the removal
closer to the Missing cutoff (only 0.009215 below it) and lowered both real-present
scores. This evidence does not establish a sharpening benefit; default stays off.

**Real missing-part verification gap:** no confirmed real missing-part image
matched to a known-good reference was available in this pilot. The controlled
removal is explicitly synthetic; it does not establish real defect recall.

## Synthetic reproduction and tests

The committed original generator `tests/comparison_fixture.py` reuses the Step 4
synthetic board/known perspective. Before warping, it erases the chip centered at
(160,120), restores green board texture/vertical trace, and leaves the (80,65) chip
intact. It writes raw images, existing-format landmark labels, regions and explicit
synthetic ground truth. Region boxes are [60,45,100,85], [140,100,180,140] and
[0,50,24,90] respectively. No real source photo is edited for this fixture.

```powershell
.\.venv\Scripts\python.exe tests/comparison_fixture.py --output runs/comparison/synthetic-input
.\.venv\Scripts\python.exe -m pcb_landmarks.align --reference runs/comparison/synthetic-input/input/reference.png --inspection runs/comparison/synthetic-input/input/inspection.png --reference-label runs/comparison/synthetic-input/input/reference.txt --inspection-label runs/comparison/synthetic-input/input/inspection.txt --output runs/comparison/synthetic-aligned
.\.venv\Scripts\python.exe -m pcb_landmarks.compare --reference runs/comparison/synthetic-input/input/reference.png --aligned runs/comparison/synthetic-aligned/aligned.png --mask runs/comparison/synthetic-aligned/overlap_mask.png --regions runs/comparison/synthetic-input/regions.json --output runs/comparison/synthetic-off
.\.venv\Scripts\python.exe -m pcb_landmarks.compare --reference runs/comparison/synthetic-input/input/reference.png --aligned runs/comparison/synthetic-aligned/aligned.png --mask runs/comparison/synthetic-aligned/overlap_mask.png --regions runs/comparison/synthetic-input/regions.json --sharpen --output runs/comparison/synthetic-on
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

All four synthetic commands were run and both comparison overlays inspected.
As above, choose new directory names on repetition. The initial standalone fixture
run exposed an import-path error, corrected by keeping the generator independent
of the production package; the commands above then completed successfully.

Actual full suite: **28 tests passed, zero failures/errors, 7.643 seconds**:
all 17 preexisting tests and 11 focused comparison tests. Tests cover the measured
Present/Missing/coverage decisions, missing-plus-review precedence, explicit
parallax review even on identical pixels, invalid crops/shared metadata/masks,
threshold boundaries and intermediate review, flat grayscale/constant-gradient
degeneracy, symmetric sharpening and unmodified input arrays, all-Present outcome,
CLI report/overlay assets, output overwrite protection, malformed metadata errors,
and failed-alignment skip/report behavior. New tests initially failed because the
module was absent; a malformed-reference-metadata regression also failed before
its input validation was added. No new dependency or training is required.

Windows environment: CPython 3.10.11, OpenCV 4.13.0, NumPy 2.1.3, Pillow 11.3.0.
Alignment/comparison run on local files with no model/network service.

## Publication boundary and remaining scope

Only source, configuration, original synthetic generator/tests and documentation
with portable measured numbers are published. All run reports, overlays, diagnostic
crops and photos stay local under ignored `runs/`; no private image is added.
Existing real inputs were already publication-cleared, per [Step 2 provenance](../../PCB_Dataset_Pilot/README.md)
(Adam Byerly / frettapper, micro-PCB Images v2, CC BY 4.0).

Real missing-part validation, automatic local quality/parallax checks and robust
threshold calibration remain unverified. Overlay label placement supports sparse
pilot regions; dense boards/long names will need wrapping/packing. React, FastAPI
and Windows packaging are outside Step 5.
