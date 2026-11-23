# Step 3 execution plan

Scope: implement SRS FR-02/FR-16 and the landmark-service portion of SDD
sections 4–5.1 and 6.2. The existing Step 2 dataset is authoritative: one `pcb`
class and four physical mounting holes in its declared order. No homography,
overlay alignment, component comparison or application UI is included.

Use the official Ultralytics Python API, with small Python command modules for
dataset audit, training, evaluation and local inference. Reuse the YAML and
manifest without changing annotations or split membership. Resolve dataset
paths explicitly for Ultralytics. Keep weights, caches, audit previews and bulk
runs local; publish only aggregate results and attributed, license-cleared
examples. Missing/ambiguous/low-confidence four-point detections must fail.

1. Audit image/label pairing, schema, ranges, visibility, decoded-image hashes,
   layout/family separation and all annotated views. Add focused automated
   checks for invalid labels and split leakage. Pin the actual Python runtime
   dependencies; prepare isolated CUDA PyTorch without modifying global packages.
2. Add configurable training using `yolo26n-pose.pt`, automatic CUDA selection,
   deterministic seed, no flips, and explicit run configuration. Execute a short
   train/validation smoke run and verify its checkpoint. Review, explicitly
   stage, commit and normally push milestone 1 on the current tracking branch.
3. Train the full run. Select `best.pt` using validation fitness only. Freeze
   confidence thresholds using validation results only before evaluating F/K.
   Report standard pose metrics plus matched per-landmark pixel error, complete
   usable detections and failures. Keep localization accuracy and confidence
   acceptance separate; confidence is not proof of correct physical identity.
4. Verify a local-path-only model loader and JSON inference on real local images,
   plus failures (missing/incompatible weights, incomplete/nonfinite/out-of-range
   points and ambiguous boards). Block sockets during an inference self-check.
   Record checkpoint hash, versions, exact commands, validation and held-out
   results; review and commit/push milestone 2 only after actual verification.

Publication: Step 2 README/manifest identify Adam Byerly's micro-PCB images as
CC BY 4.0. Include that attribution and disclose added annotations on examples.
Do not add raw photographs or labels in this step. Existing tracked dataset and
graph files are preserved. Reproduction obtains the checkpoint by rerunning
training; no public weight download is claimed unless actually published.

Risks to verify: tiny validation set, projected-label accuracy, generic pose
weights accidentally loaded, offline auto-downloads, physical landmark order,
leakage through layout families, overconfident inaccurate predictions, and
personal filesystem paths in generated run metadata.
