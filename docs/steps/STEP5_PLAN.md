# Step 5 implementation plan

Scope: implement SDD 6.3–6.5 as an offline region-comparison CLI, using Step 4
assets and the existing Step 2 component schema. No inference, UI, server or
packaging changes; no new dependency. Full application quality gates stay pending.

- [x] Add failing decision tests and an original synthetic missing-part fixture.
- [x] Add `pcb_landmarks/compare.py`: validate shared coordinate frames, nonempty
  unique region identities and configuration; invalid per-region boxes become
  Needs review. Require complete valid-mask coverage. Gate explicit review flags,
  low grayscale/gradient texture and failed alignment before classification.
- [x] Compute zero-mean normalized correlation of equal-position Sobel magnitudes.
  Use provisional configurable missing/present thresholds, with an intermediate
  review band. Optional symmetric unsharp is off by default; raw texture gates
  precede sharpening. Preserve missing findings alongside review findings.
- [x] Reuse `id`, `name`, `bbox_xyxy_px`, `reference_image`, `reference_wh_px` in
  `configs/components-ECCC5.json`; add only optional `review_reason`. Score U2
  and AM335x; flag Ethernet/USB parallax from actual crop/overlay inspection.
- [x] CLI consumes reference/aligned/mask/regions/config and Step 4 sidecar metadata;
  saves JSON and named status overlay in reference pixels. Failed alignment saves
  a retake report with null scores, no overlay and nonzero exit.
- [x] Run same synthetic/real pairs and regions with sharpening off/on; record actual
  scores/decisions, full suite results and lack of real missing-part ground truth
  in `docs/STEP5.md`. Publish source, fixtures and portable measured results only.

Checkpoint procedure: inspect and explicitly stage changes, commit, normal-push
existing `docs/pcb-srs-sdd-dfd`, and verify remote hash. Keep run assets local;
report the verified commit hash in the delivery message.

The existing F-layout present controls are held out; do not use them for pilot
threshold selection. Regions bind to the decoded reference dimensions and named
reference image. Successful warping alone does not certify local comparison.
