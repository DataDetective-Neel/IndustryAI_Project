# PCB repair results — November 23, 2026

Tested branch: `codex/aoi-platform`. Dataset: `A:/IndustryAI_Dataset_Worktree/dataset_generation`.

## Actual acceptance cases

All predictions below came from the production HTTP inspection pipeline, using the golden component map and decoded images. Per-inspection defect annotations were never supplied to the algorithm. Raw results include all component IDs, scores, reasons, transformations, and registration metrics in `runs/repair-acceptance/report.json`. Alignment, difference, and component overlays are saved alongside it; these generated artifacts are deliberately excluded from Git.

| Case | Registration | Median reprojection error | Board overlap | Actual component predictions / outcome |
|---|---|---:|---:|---|
| A: golden versus itself | Verified | 0 px | 100% | 34 present; GOOD; no false missing defects |
| B: translation (+9, −7 px) | Verified | 0.00034 px | 99.78% | 34 present; GOOD |
| C: whole-board rotation (4°) | Verified | 0.0872 px | 98.82% | 33 present; J2 review because its crop lacks full source coverage |
| D: actual `misaligned_002.png` | Verified | 0.07198 px | 99.66% | U2 MISALIGNED_COMPONENT; other 33 present |
| E: actual `missing_001.png` | Verified | 0.07836 px | 99.68% | U1 MISSING_COMPONENT; other 33 present |
| F: catalog A versus E PCB | Not attempted after positive mismatch evidence | — | — | BOARD_MISMATCH; different positively recognized layouts; scoring skipped |
| G: uniform poor-quality image | Failed safely | — | — | NEEDS_REVIEW; PCB surface cannot be isolated; all 34 components not evaluated |
| H: forced automatic-reference failure, manual save, two inspections | Verified for both reused views | 0.00034 / 0.0872 px | 99.78 / 98.82% | First: 34 present. Second: 33 present, clipped J2 review. No repeat manual point selection |
| I: browser golden upload, map import, save, inspection, tabs, diagnostics, persistence | Verified | 0.07198 px | 99.66% | U2 misaligned; 33 present; stored JSON matches browser response; golden configuration restored after reload |

Case D: 1,218 reciprocal matches, 1,190 inliers, 397 held-out inliers, all nine spatial cells occupied. U2 has −18° local rotation, displacement [13, −11] px, and similarity 0.77399. Case E: similarity 0.09052, edge energy ratio 0.14991, and normalized LAB difference 0.18856 corroborate absence.

The golden map identifies the rotated upper-right IC as **U2** and the removed main IC as **U1**. Some dataset README descriptions use different IDs. The application follows the uploaded golden map; filenames and narrative descriptions are not prediction sources.

## Workflow and verification

Golden upload now automatically saves ordered distributed reference points. Reliable validated YOLO mounting holes are preferred; an independent contour-derived board frame and on-board SIFT registration provide fallback. Manual corrections replace the saved reference and remain reusable. Imported golden-map IDs and boxes are preserved exactly, and operator acceptance remains required before saving component proposals for the live line.

The Inspection Lab uses light surfaces and dark text, with golden and inspection previews, component regions, registered defect boxes, five comparison tabs, and expandable registration metrics. Actual screenshots are in `runs/repair-browser/workspace.png` and `runs/repair-browser/findings.png`.

Validation completed:

- Full Python suite: **92 tests passed**. A subsequent targeted automatic-reference run passed **3 tests**, including preference for reliable YOLO mounting holes.
- Frontend build and **4 JavaScript unit tests passed**.
- Existing browser checks: **5 passed**, covering component proposals, upload recovery, navigation, live queues, and inspection.
- Dedicated exact-sample browser workflow: **1 passed**, exercising persisted reports and golden restoration.

Reproduce API acceptance:

```powershell
.venv/Scripts/python.exe -m pcb_landmarks.repair_check --dataset A:/IndustryAI_Dataset_Worktree/dataset_generation
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

Reproduce browser acceptance from `frontend`:

```powershell
npm run build
npm test
npx playwright test --config repair.config.js
```

Set `PCB_REPAIR_DATASET` to relocate the browser dataset. The acceptance script takes `--dataset` explicitly. Browser tests use a separate storage directory and test account; production database contents are not replaced.

## Limits

This validates these source photos and synthetic transformations, not production accuracy across untested boards. Contour setup can still require manual correction for low saturation boards or clutter. Reference registration requires distributed on-board texture and sufficient overlap. Components outside the supported ±30° / 24 px search can require review. Component thresholds remain provisional, and no calibrated probability is claimed. The 4° test intentionally retains review for the clipped connector instead of fabricating a clean result.
