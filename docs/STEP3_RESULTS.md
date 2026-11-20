# Step 3 measured results

## Dataset and hardware

Dataset unchanged: 19 train (A/B/H/M), 5 validation (E), 8 held-out (F/K).
All pairs, 17-value class-0 pose rows, box/point ranges, visibility values,
manifest dimensions and layout/family separation passed the automated audit.
128 visible points; zero exact file/decoded-image duplicates across splits.
All 32 contact-sheet views passed physical landmark ordering review. This is
visual review of initial annotations, not independent metrology-quality labels.

Dataset content fingerprint (YAML plus ordered relative image paths, image and
label bytes): `9fbd4a497e6f714d30a975153a3d4f80750fcc4f42e792edabad77d622abc3c6`.

Windows, CPython 3.10.11, NVIDIA GeForce RTX 3050 6GB Laptop GPU, driver 621.14,
PyTorch 2.9.1+cu128, torchvision 0.24.1+cu128, CUDA runtime 12.8 available.
Ultralytics 8.4.39. See requirements-lock.txt for dependency versions.

## Milestone 1 smoke test

Executed `python -m pcb_landmarks.train --imgsz 320 --epochs 2 --batch 2
--device auto --seed 42 --name smoke_verified` using the project venv.
Both training epochs and validation on all 5 E images completed on CUDA:0.
`runs/landmarks/smoke_verified/weights/best.pt` and `last.pt` were written.
The wrapper exited successfully and wrote `summary.json`.

| Smoke validation metric | Actual value |
|---|---:|
| Pose precision | 0.592720 |
| Pose recall | 0.600000 |
| Pose mAP50 | 0.448333 |
| Pose mAP50–95 | 0.066686 |
| Box mAP50 | 0.030026 |
| Box mAP50–95 | 0.004953 |

These two-epoch metrics only prove execution, not model readiness. The first
attempt trained/validated and wrote weights, but the wrapper reported failure
because Ultralytics resolved its relative output project under `runs/pose`.
Passing an absolute project path fixed that root cause; a regression test and
the fresh `smoke_verified` run verified the correction. Original failed-run
artifacts remain ignored locally for traceability.

Repeated with `--name smoke_clean` after disabling global site-package access
and installing the locked dependencies into the venv: exit 0, identical metrics,
both checkpoints and summary written. `pip check`: no broken requirements.
Three milestone-1 unit tests passed (label contract, split leakage/pairing,
requested checkpoint output location).

Full training, threshold selection, held-out evaluation and offline inference
have not yet been recorded in this milestone-1 checkpoint.
