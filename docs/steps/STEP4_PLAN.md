# Step 4 implementation plan

Implement the requested four-point alignment slice of SDD sections 4 and 6.2.
Use reviewed Step 2 annotations because frozen Step 3 rejects development views.
OpenCV is already installed; no model, dependency, label or threshold changes.

- [x] Add a deterministic, publication-safe synthetic perspective pair generator
  in `tests/alignment_fixture.py` and failing `tests/test_align.py` checks:
  independent control points, raster agreement, conservative validity mask,
  rotation identities, malformed/degenerate geometry and CLI failures.
- [x] Implement `pcb_landmarks/align.py`: RGB uint8 images and ordered `(4,2)`
  pixel arrays -> aligned RGB raster, inspection-to-reference homography,
  uint8 validity mask. Validate geometry and numerical usability before warp.
  Keep dataset conversion at the CLI boundary using `read_label`/`read_image`.
  Provide a blend with explicit invalid coverage and JSON status/exit 0 or 2.
- [x] Run a reviewed validation-layout pair through the CLI; inspect independent
  connector/chip features and record limitations separately from synthetic proof.
- [x] Run the complete unittest suite, document exact Windows reproduction and
  outputs in `docs/steps/STEP4.md`, and link implemented status from SRS/SDD/DFD.
- [x] Review the alignment source/test diff and publication scope.

Checkpoint procedure: explicitly stage source/tests/docs only, commit and
normal-push existing `docs/pcb-srs-sdd-dfd`; verify origin hash. Keep run outputs
local. Report the verified commit hash in the delivery message.

Scope reaches the new module, CLI tests, synthetic fixture and documentation.
Existing inference callers/exports/configuration require no changes. Never sort
points by screen position. Reject EXIF rotation through the existing reader.
Four correspondences cannot certify identities, layout or alignment away from
the mounting-hole plane; do not turn a successful warp into an inspection verdict.
