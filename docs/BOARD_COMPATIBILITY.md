# Board compatibility before component inspection

The API checks layout compatibility before component scoring. A different board
returns `outcome: "DIFFERENT_BOARD"`, the message **“Inspection board does not
match the reference design.”**, `components_evaluated: false`, and an empty
`components` list. This applies in Manual and Automatic modes; a failed YOLO
landmark prediction is not used as evidence that a board is different.

## Positive layout evidence

`configs/board_designs.json` defines stable feature regions for the three existing
demo layouts: the blue Mega2560 board, Raspberry Pi, and BeagleBone. These include
upper mounting-hole/connector regions, separate headers and pin silkscreen, and
lower connector footprints. Main processors are excluded from these identity masks. Feature masks are
intersected with an eroded PCB boundary so surrounding cloth/background cannot
supply layout votes.
Uploaded filenames and board color do not identify a design.

OpenCV SIFT matches these stable regions to each uploaded raster independently.
Recognition requires at least 25 unique geometrically consistent matches, at
least 45% RANSAC inliers, at least five inliers in each of three separated regions,
and a feature hull covering at least 12% of the template board area. Ambiguous
profile matches require review. The result retains the matched regions, counts,
spatial coverage, projected board visibility, and image sharpness.

`DIFFERENT_BOARD` requires **both** images to positively identify different
supported layouts with adequate visibility and detail. A four-point homography,
low overlay score, missing component, or lack of feature matches cannot produce
that outcome by itself. Unrecognized layouts remain `REVIEW` unless there is
strong positive same-design agreement across at least six of nine interior tiles.
This fallback supports existing synthetic/manual demos and never labels a board
different from negative similarity evidence.

For recognized same-design pairs, the existing inspection-to-reference homography
is checked against independent distributed layout controls, including the expected
mount positions and stable-region centers. Excess residual error returns `REVIEW`
and skips component scoring. The feature homography verifies compatibility and
alignment; it does not replace the user's/manual or YOLO component-alignment warp.

Blur or insufficient detail, less than 90% projected board visibility, ambiguous
layout evidence, and uncertain alignment return `REVIEW`. Missing dataset templates
do not disable the existing manual/synthetic workflow; they prevent unsupported
claims that a design is different. Thresholds are provisional demo gates, not a
general PCB classifier or statistical accuracy guarantee.

## Regression evidence

Tests use the real upload-and-inspect API. The production browser regression
checks the displayed message, suppressed component decisions, and valid siblings
in a seven-image batch. All images are processed from pixels, including a test
that uploads both designs under the same filename.

| Case (reference ACCC5) | Board result | Component inspection |
| --- | --- | --- |
| MBCC5, Manual and Automatic | DIFFERENT_BOARD | Not called; no decisions |
| ACCC5 identical | SAME_DESIGN | Processor PRESENT, score 1.0000 |
| ABCC5 angle | SAME_DESIGN | Processor PRESENT, score 0.9828 |
| ACCB5 angle | SAME_DESIGN | Processor PRESENT, score 0.7771 |
| ACDC5 angle | SAME_DESIGN | Processor PRESENT, score 0.8463 |
| ADCC5 angle | SAME_DESIGN | Processor PRESENT, score 0.9742 |
| Aligned ACCC5 with SIMULATED processor erasure | SAME_DESIGN | Reached inspection; REVIEW, score 0.1421 |
| Strongly blurred MBCC5 | REVIEW | Not called |
| Half-cropped MBCC5 | REVIEW | Not called |
| ACDC5 with deliberately shifted alignment points | REVIEW | Not called |
| Unrecognized random texture | REVIEW | Not called |

The reference ACCC5 has 1,710 consistent stable-region features across four regions;
MBCC5 independently matches the Raspberry Pi template with 33 inliers across three
regions. The blue angle controls retain 182–907 inliers in three or four regions.
The processor erasure is a clearly labeled demo fixture, **not a verified real
missing-component photo**. The component layer retains its conservative REVIEW
policy for ambiguous absence evidence.

[API evidence JSON](results/board-compatibility.json) ·
[Production browser report](../runs/board-compatibility/browser-report.json) ·
[Wrong-board screenshot](../runs/board-compatibility/wrong-board.png)

Reproduce with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_board_compatibility.py
Set-Location frontend
npx playwright test tests/board-compatibility.spec.js
```

Blue-board controls use reviewed manual landmarks. This change does not retrain
the existing Raspberry Pi YOLO profile or claim automatic blue-board landmarks.

Final verification: **55 backend tests, 4 frontend unit tests, and 11 browser tests passed**.
The production build and `git diff --check` also passed.
