# PCB repair audit — November 23, 2026

The clean starting branch is `codex/aoi-platform`.

Confirmed control-flow failures:

- `frontend/src/main.jsx` starts in manual mode. Reference setup returns an outline but no points. Classical registration is reachable only after saving four reference points.
- `web.py` rejects an unknown catalog layout before registration when no reference is saved. A new ELEGOO board therefore cannot use the existing independent SIFT registration path.
- YOLO failures have a classical fallback only for saved references. Lowering YOLO confidence does not repair this missing setup path.
- `style.css` defines dark surfaces while `platform.css` globally overrides text to dark ink. The embedded lab inherits both sets, causing dark text on dark panels.
- Coordinates are decoded original pixels; SIFT scales coordinates back before fitting. No resize-coordinate defect was found in this path.

Existing registration checks reciprocal, spatially distributed on-board matches, held-out reprojection, overlap, and stable edge regions. Keep these checks. Local changes must not be used to reject the board before these checks run.

The requested `misaligned_002.png` was not found in the repository or searched user download locations. Its actual prediction remains unverified until the source image is available. Synthetic tests cannot replace that result.
