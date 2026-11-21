# PCB inspection frontend verification

Verified on November 21, 2026. The redesign changes the React frontend only;
the inspection request payload and existing API endpoints are preserved.

## Retained workflow

- One known-good reference and up to 15 inspection photos, including incremental
  uploads and partial upload failures.
- Automatic mounting-hole detection, rejected-point diagnostics, switching to
  Manual, click/drag correction, numeric coordinates, and preview resizing.
- Exact-reference component presets; drawing, adding, naming, editing, flagging,
  and removing component boxes.
- Optional sharpening, synthetic demonstration labels, per-photo processing
  failures, original API evidence links, and the JSON report.
- Photo replacement resets that photo's landmarks; reference replacement reloads
  its presets. Reference removal clears its component annotations and keeps the
  inspection batch available for a new reference.

## Comparison behavior

Side by side shows the original photos. Overlay applies the API's
inspection-to-reference homography in the browser, clips to the reference bounds,
and exposes inspection opacity. It is disabled without a valid finite, nonsingular
homography and both decoded images. The API's original evidence assets remain linked.
Selecting a finding highlights its valid reference-pixel box. All prior measurement
fields are retained in expandable details, including offset and expected box, which
were previously missing from table cells. Missing is red; uncertain/review is amber.
Different board requires an explicit backend outcome or compatibility status.

## Checks

- `npm --prefix frontend test`: 4 passed (coordinates, homography, finding bounds).
- `npm --prefix frontend run build`: passed.
- `git diff --check`: passed. No lint script is configured.
- `npm run test:browser` from `frontend`: final run **10 passed, 1 failed**.
  Passing cases cover 15-photo batches, upload recovery, photo replacement/removal,
  empty state, manual controls, automatic accepted landmarks, findings, opacity,
  returned outcomes, synthetic review, sharpening, and local-only assets.
- Browser/layout checks at 1440, 768, and 375 pixels; desktop and narrow screens
  were visually inspected, including the empty state, editor, side by side,
  aligned overlay, and selected region. No horizontal page overflow was found.
- Same image twice: ECCC5 returned `ok`, 8 Present components, alignment 1.0000.
- Perspective and crop demo fixtures passed their expected Present/Review outcomes.
- The separately added, untracked board-compatibility browser test passed on the
  updated backend: different layouts, four same-board angle controls, simulated
  processor absence, and blur. That backend work is outside these frontend commits.

## Reproduced pipeline limitations

The original real-manual workflow/CLI-parity test passed before the concurrent
backend compatibility edits and restarts. On the final running backend it fails
at `workflow.spec.js:258`: ECCC5 reference versus ECCB5 inspection returns zero
component decisions instead of eight. The returned compatibility/alignment warning
says alignment is uncertain and requests corrected landmarks or a retake. The UI
renders that returned warning and skips scoring; it does not label this pair as a
different board. No backend changes or weaker test expectations were introduced
to hide this failure. Full parity on that fixture remains unresolved.

Automatic mode still rejects some one-board demo images; accepted Raspberry Pi
mounting-hole detection passed. Synthetic erasure remains Needs review. Real
missing-component accuracy has no verified absence fixture; its red UI state was
checked using a controlled API response, not claimed as validated detector behavior.
