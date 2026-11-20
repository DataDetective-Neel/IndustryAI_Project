# Step 6 implementation plan

Use React/Vite and a loopback FastAPI app. Reuse `LandmarkDetector`, `align_images`,
`blend_overlay`, `compare_regions` and `annotated_overlay` without changing CLI
settings or mathematical behavior. Manual mode is default; Automatic uses frozen
hash/confidence/schema and never silently falls back. Keep request snapshots and
per-photo exception boundaries. Store local UUID assets only under ignored runs.

Scope: new `pcb_landmarks/web.py`, `frontend/`, API/coordinate/browser tests,
web dependency pins, ignore rules and reproduction/verification documentation.
Existing inference/alignment/comparison exports, labels and configs stay unchanged.
Limit upload bytes, decoded pixels, batch count and annotation count; validate IDs,
same-origin requests and reference coordinates. No user-supplied filesystem paths.

- [x] Add failing API tests for pipeline equivalence, failure isolation, unavailable
  model and input boundaries; coordinate tests for preview scaling and rounding.
- [x] Implement upload, frozen inference, inspection batch and known-asset endpoints.
  Save local report/overlays; serve production frontend from the same backend.
- [x] Implement upload/editor/results workflow, numeric annotation correction and
  draw/remove controls, review flags, explicit landmark modes and sharpening.
- [x] Browser-check real ECCC5/ECCB5 against CLI, synthetic removal, automatic pilot
  rejection, mixed success/failure batch, edit/delete and resized coordinates.
- [x] Run Python tests, frontend coordinate tests and production build. Inspect UI
  and record exact commands and evidence in STEP6.md.

Checkpoint procedure: review/stage explicitly, commit, normal-push current
docs/pcb-srs-sdd-dfd and verify the remote hash in the delivery message.

Visual plan: photo-led inspection bench, large reference-coordinate SVG editor
beside a quiet annotation panel; per-photo result sheets below. Local Segoe UI /
Bahnschrift type; paper #f2f5f8, ink #21384d, teal #16736b, amber #9a6500,
red #b62c3c, white #ffffff. Use borders for grouping and text plus color for status.
The workspace prioritizes mounting-hole identities and crop evidence over dashboard
decoration; no charts, animation, CDN assets, authentication service or database.
Windows .bat packaging and real missing-part validation remain separate work.
