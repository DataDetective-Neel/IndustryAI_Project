# Operator feedback fixes — November 23, 2026

## Causes and changes

The reference-hole contour detector merged the lower-right ELEGOO hole with
neighboring connector/silkscreen pixels. It selected an internal mounting hole
instead. Closed circular-edge recovery now supplements the contour candidates,
with neutral-interior, substrate-ring, size, and texture checks. The four outer
holes are selected geometrically. The photograph regression checks approximately
(188,217), (756,215), (759,934), and (188,973), within 4 px. These coordinates occur
only in tests, never production inference. The custom YOLO model remains in use;
its proposals cannot replace independently verified holes with distant points.

Inspection-upload previews previously requested only raw pose predictions. A
rejected model prediction left no markers even when feature registration would
later succeed. `/api/landmarks/{id}?reference_id=...` now returns independently
verified corresponding reference points. The Lab requests this preview for a
confirmed reference and labels projected points accordingly. Automatic reference
geometry has a version so old automatic configurations are upgraded; manually
confirmed setups remain preserved.

Manual click inaccuracies left approximately 2–4 px of residual registration
error in saved operator runs. Component template offsets were then interpreted
as local shifts. Manual registration can now receive a bounded feature-based
refinement only when independently verified p90 error improves substantially.
Original clicks, maximum correction, and original error remain in diagnostics.
The component tolerance also includes twice p90 error plus a one-pixel margin.
This is a conservative provisional margin, not a calibrated statistical bound.

Exposed solder pads can retain strong edges after component removal. The verifier
now also measures disappearance of a predominantly neutral component surface
into colored substrate. This alternative absence signal requires low structural
similarity, appearance change, sufficient substrate replacement, and accurate
registration relative to the component size. It does not replace the existing
edge-based evidence and remains conservative on unclear fixtures.

The live page defaulted to a mixed pilot-board directory. Saved failed frames
included F/K layouts compared against the ELEGOO reference; visual inspection
confirmed these are different boards. The default directory is now empty and the
UI requires an explicit input selection, explaining that layout and side must
match. Failed feature matching includes the same-layout guidance. No alignment
gate was removed to force incompatible boards through comparison.

Live results now use a large image panel (at least 440 px tall on desktop), show
the annotated result when available, and offer a full-size image link. Camera
previews and camera results use similarly large contained images. Existing
colors, fonts, and navigation remain intact.

## Evaluation evidence

The deterministic sample uses seed 23 for two images per category and seed 24
for four extra good images. All use the original golden photograph and an
automatically detected inventory of 61 components. Inference never consumes
defect annotations. Annotations are read afterward for evaluation context.

- `good_038`, `good_011`, `good_050`, `good_075`, `good_024`, and `good_028`:
  all 61 inventory components present, no confirmed missing/shift/rotation flags.
- `missing_006`: one missing capacitor, 60 present.
- `misaligned_006`: one displaced capacitor, 60 present.
- `multiple_defects_010` and `multiple_defects_003`: each retains two uncertain
  findings, with 59 present. These are not claimed as successful defect diagnoses.
- The C7 edits in `missing_019` and `misaligned_019` target an empty trace area in
  the golden photograph. The former adds a pad graphic there. They cannot serve
  as valid physical-component absence/rotation controls. Original files remain
  untouched; these two images are excluded from the recommended test folder.

Replaying saved manual inspections through the real API:

| Saved case | Previous findings | Updated findings |
| --- | --- | --- |
| First `misaligned_001` run | 33 misaligned, 3 missing, 4 uncertain | 1 rotation, 1 uncertain, 55 present |
| Second `misaligned_001` run | 2 misaligned, 1 uncertain | 1 rotation, 1 uncertain, 55 present |
| `missing_009` | 9 misaligned, 1 missing, 19 uncertain | 0 confirmed defects, 2 uncertain, 55 present |

The last row represents removal of false confirmed shifts, not proof that every
annotated missing component has been diagnosed. Refinement reduced representative
p90 reprojection errors from about 3.3–3.8 px to about 0.17 px. This sample does
not establish accuracy on independent hardware photographs.

Local artifacts are ignored by Git: `runs/operator-feedback/latest-report.json`,
the operator-view screenshot, and `runs/operator-feedback/test-images/`. The test
folder contains a golden reference, six random samples, and two known controls.
Start with `good_038.png`, `missing_006.png`, and `misaligned_006.png`.

## Regression checks

Physical camera hardware and independent real-defect accuracy remain unverified.

Backend regression: 112 tests passed in 377.634 s while the image evaluation and
browser checks were also running. Four JavaScript unit checks, the production
build, Python compilation, and whitespace checks passed. Two dedicated repair
browser checks passed, and the missing-checkpoint reference workflow passed.
The focused mounting-calibration and operator-preview browser checks also passed.

An initial browser calibration failure exposed duplicate raw landmark requests
when reference coordinates changed. Raw requests now share one promise per photo;
transport failures are evicted so a later attempt can retry. Preview registration
remains keyed to the active reference and is not cached across reference changes.
The browser regression verifies one raw request for the uploaded reference.

The final clean main browser run passed all 21 tests in 6.1 minutes, including
the complete manual workflow and production/Vite synthetic cases. Together with
the two dedicated repair checks and one missing-checkpoint workflow, 24 browser
scenarios passed. Implementation commit: `139d8f0`. No generated images, model
weights, original datasets, user reports, or credentials are committed.
