# Step 3: four-landmark YOLO26n Pose

This implements landmark training and local detection only. The Step 1 SRS/SDD/DFD
remain the wider application design; alignment and component comparison are later
steps. Use the existing branch and normal pushes; do not rewrite earlier commits.

## Windows setup

Run PowerShell from the repository root. Tested Python: CPython 3.10.11, 64-bit.
Initial dependency/official-weight downloads need internet. Inference uses local
files only. A fresh environment is recommended:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
# NVIDIA CUDA build (verified driver must support CUDA 12.8):
.\.venv\Scripts\python.exe -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

For CPU-only machines replace the PyTorch index with
`https://download.pytorch.org/whl/cpu`. `--device auto` selects CUDA device 0 if
available, otherwise CPU; explicit `--device cpu` is also supported. The actual
development environment initially reused installed packages through an isolated
`--system-site-packages` venv, installed CUDA wheels locally, then disabled global
package access and installed the same locked dependency versions locally.
No global package was changed. Direct versions are in `requirements.txt`;
the full Windows dependency inventory is in `requirements-lock.txt`.

## Dataset audit and smoke run

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pcb_landmarks.data --data PCB_Dataset_Pilot/dataset.yaml --previews runs/audit --output runs/audit/report.json
.\.venv\Scripts\python.exe -m pcb_landmarks.train --data PCB_Dataset_Pilot/dataset.yaml --imgsz 320 --epochs 2 --batch 2 --device auto --seed 42 --name smoke_verified
```

The reader checks exactly one class-0 board and four `(x,y,visibility)` triples,
finite normalized ranges, positive in-image boxes, visibility 0/1/2, exact
image/label pairs, manifest dimensions, cross-split layout and family separation,
and duplicate file/decoded-pixel hashes. The manifest must match the configured
images exactly. Generated contact sheets allow checking physical identities;
hash checks do not prove absence of every near-duplicate acquisition.

All 32 annotated views were inspected in contact sheets. Identities remain on
the same four mounting holes across the supplied modest rotations/viewpoints.
Order is `upper_left_mount`, `upper_right_mount`, `lower_right_mount`,
`lower_left_mount`, relative to each layout's canonical orientation. No points
are sorted by their current screen position. These initial manually placed and
feature-projected labels have not been independently re-annotated at pixel level.

The training command resolves the existing dataset YAML root into an ignored
run-local YAML. It preserves splits: train 19 (A/B/H/M), validation 5 (E), test
8 (F/K). Both held-out layouts and their family are absent from train/validation.
All 128 keypoints have visibility 2. There are no cross-split exact duplicates.
Neither dataset annotations nor split assignments are changed.

Training starts with the official `models/yolo26n-pose.pt` checkpoint (downloaded
by Ultralytics on first use). It adapts the pose head to four points. Both flip
augmentations are always zero: no physical-landmark remapping has been verified.
Workers=0 supports Windows. Deterministic mode and seed are set; AMP is disabled.
AdamW uses lr0=0.001/lrf=0.01; other augmentation/loss defaults are those of pinned
Ultralytics. The exact complete arguments are saved in local `args.yaml`.
Run names cannot be reused accidentally. `best.pt` and `last.pt` must both exist
before the command reports success. Check `summary.json` and `results.csv` for
the actual outcome, not merely the process start.

## Full training

```powershell
.\.venv\Scripts\python.exe -m pcb_landmarks.train --data PCB_Dataset_Pilot/dataset.yaml --imgsz 640 --epochs 150 --batch 4 --device auto --seed 42 --patience 30 --name full
```

Choose `runs/landmarks/full/weights/best.pt` using Ultralytics validation fitness
only. Test F/K images must not be used for epoch selection or threshold tuning.
The pilot is too small for production accuracy claims. Full evaluation,
threshold selection and offline inference evidence are recorded in
`STEP3_RESULTS.md` when actually executed.

## Public repository boundary

Weights, run directories, label caches and the venv are ignored. Local generated
metadata may include absolute paths and is not staged. Aggregate results and
attributed examples are explicitly selected for publication. No credentials,
new raw photographs or labels are needed. The pre-existing tracked dataset is
preserved. Obtain trained weights by executing the commands above; a separately
hosted binary is not implied.

Technical references: [official YOLO26 models](https://docs.ultralytics.com/models/yolo26/),
[pose API](https://docs.ultralytics.com/tasks/pose/),
[PyTorch versioned wheel commands](https://pytorch.org/get-started/previous-versions/).
Dataset provenance/license is in `../PCB_Dataset_Pilot/README.md`.
