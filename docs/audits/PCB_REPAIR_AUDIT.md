# PCB repair audit — November 23, 2026

The clean starting branch is `codex/aoi-platform`.

Confirmed control-flow failures:

- `frontend/src/main.jsx` starts in manual mode. Reference setup returns an outline but no points. Classical registration is reachable only after saving four reference points.
- `web.py` rejects an unknown catalog layout before registration when no reference is saved. A new ELEGOO board therefore cannot use the existing independent SIFT registration path.
- YOLO failures have a classical fallback only for saved references. Lowering YOLO confidence does not repair this missing setup path.
- `style.css` defines dark surfaces while `platform.css` globally overrides text to dark ink. The embedded lab inherits both sets, causing dark text on dark panels.
- Coordinates are decoded original pixels; SIFT scales coordinates back before fitting. No resize-coordinate defect was found in this path.

Existing registration checks reciprocal, spatially distributed on-board matches, held-out reprojection, overlap, and stable edge regions. Keep these checks. Local changes must not be used to reject the board before these checks run.

The user subsequently located the dataset at `A:/IndustryAI_Dataset_Worktree/dataset_generation`. The exact sample is now tested through the production inspection API; see `PCB_REPAIR_RESULTS.md`.

Actual ELEGOO diagnostics: YOLO reports `mounting_holes_not_verified`. Its failure is not a reason to lower detection thresholds. The outline contains five vertices, including a chamfer/connector protrusion, so automatic reference setup fits an inset board frame within the observed polygon. Inspection uses reciprocal on-board SIFT matches and independent validation rather than assuming those frame coordinates are visible mounting holes.

The original component search covered only five pixels for the rotated IC. The actual registered displacement is approximately 17 pixels. Expanding bounded translation and rotation hypotheses recovers a convincing match at −18 degrees. A wide search is accepted only when it reaches the configured present threshold; otherwise the original narrow footprint supplies absence evidence. This prevents neighboring traces from hiding removed components.
