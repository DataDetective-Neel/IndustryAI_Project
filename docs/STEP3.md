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
Dataset fingerprints normalize YAML/label CRLF to LF so Windows checkout line
endings do not invalidate otherwise identical data.

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
`STEP3_RESULTS.md`.

## Evaluation and local inference

The measured pilot **did not produce a usable four-landmark detector**. The
frozen configuration rejects all validation/test images. These commands verify
the trained artifact and explicit failures; they do not certify alignment accuracy.

```powershell
# Fresh reproduction: select on validation only, using a NEW config filename.
# The committed config is bound to the measured checkpoint hash.
.\.venv\Scripts\python.exe -m pcb_landmarks.evaluate --checkpoint runs/landmarks/full/weights/best.pt --split val --select --config configs/reproduced-landmarks.json --output runs/evaluation/val.json --device 0
# Only after checkpoint/thresholds are fixed:
.\.venv\Scripts\python.exe -m pcb_landmarks.evaluate --checkpoint runs/landmarks/full/weights/best.pt --split test --config configs/reproduced-landmarks.json --output runs/evaluation/test.json --device 0
# Exact inference command for the measured local checkpoint:
.\.venv\Scripts\python.exe -m pcb_landmarks.infer --checkpoint runs/landmarks/full/weights/best.pt --config configs/landmarks.json --source PCB_Dataset_Pilot/images/val/ECCC5.jpg --device cpu --output runs/evaluation/inference.json
# Fresh-process CPU verification with DNS/socket connections blocked:
.\.venv\Scripts\python.exe -m pcb_landmarks.verify_offline --checkpoint runs/landmarks/full/weights/best.pt --config configs/landmarks.json --sources PCB_Dataset_Pilot/images/val/ECCC5.jpg PCB_Dataset_Pilot/images/test/FCCC5.jpg PCB_Dataset_Pilot/images/train/ACCC5.jpg --generic-checkpoint models/yolo26n-pose.pt --output runs/evaluation/offline.json
```

For CPU evaluation replace `--device 0` with `--device cpu`. Add
`--samples runs/evaluation/samples` to evaluation to create local annotated
examples. Only publication-cleared sources may have samples added to Git.

`LandmarkDetector(checkpoint, data, device='cpu', imgsz=640)` loads once;
`predict(image_path, board_conf, point_conf)` returns `status`, `reason`,
`image_wh`, checkpoint hash, board box/confidence and four `{name,x,y,confidence}`
landmarks in dataset order on success. Coordinates refer to the full decoded
raster, not the 640-pixel model input. No sorting or homography occurs.
The CLI requires a checkpoint-bound JSON config and verifies the hash before
deserializing weights, then checks the schema. Direct API callers can supply
`expected_sha256`; omit it only for a checkpoint they explicitly trust.
Missing, corrupt, generic human-pose or schema-incompatible weights fail; missing,
ambiguous, low-confidence, nonfinite, coincident, out-of-image, edge-clipped,
collinear, crossed or mirrored points return
`status: failure` with `landmarks: []`. CLI exit code is 0 on success and 2 on
failure. A failure JSON is an expected measured outcome for this checkpoint.
No point coordinates are returned as usable on failure.
Board confidence must strictly exceed its threshold (matching Ultralytics' raw
filter); point confidences must meet theirs. Mounting holes are interior features,
so x=0 or y=0 is rejected as potentially clipped. Cyclic turns must all have the
positive sign of the dataset's canonical order; calibrated area/alignment gates
remain a later step.

Ultralytics startup connectivity probing is disabled before import via
`YOLO_OFFLINE=true`; sync is disabled. The loader resolves an existing local
checkpoint before invoking YOLO, so missing paths cannot trigger downloads.
Images with EXIF rotation must be normalized and annotated in that frame first.
The offline check verifies model loading and three inferences with zero DNS/socket
attempts, plus rejection of the local generic 17-human-keypoint checkpoint.
It is not an offline test of the future complete application or a physical
Wi-Fi-off test.

Threshold selection tries board confidence `[0.25,0.5,0.75,0.9,0.95]` and
keypoint confidence `[0.5,0.7,0.85,0.95,0.99]` on validation only. It minimizes
inaccurate accepted images, then maximizes accurately accepted images, then
chooses conservative ties. Accuracy here requires all four visible labels and
each error <= 1% of the decoded image diagonal, plus box IoU >= 0.5. This is an
exploratory localization tolerance, **not** a calibrated alignment requirement.
No candidate achieved an accurately usable validation image. The resulting
0.95/0.99 settings are rejection-only, not a deployment recommendation.

Pixel localization independently matches the highest-confidence prediction with
board IoU >= 0.5 at score >= 0.001, including points rejected by the runtime
gate. It uses visible labeled points (visibility > 0). Complete usable counts
require the runtime gate; `all_four_within_tolerance` adds the ground-truth check.
`failed_detections` counts images returning failure, not just absent boxes.
Denominators and per-image reasons are published in `docs/results/`. Standard
pose metrics use Ultralytics' custom-four-point OKS sigma of 0.25 per point,
which is broad and must not substitute for pixel errors.

The measured checkpoint is local and ignored:
`runs/landmarks/full/weights/best.pt`. Its SHA-256 is in
`configs/landmarks.json`; `configs/training.json` records the initial weight
hash, run settings, selected epoch and aggregate metrics. Rerunning training
obtains a new local checkpoint. Binary hashes can change with serialization
metadata or hardware even with a deterministic seed: select a new validation
configuration for reproduced weights. No binary download or usable production
model is claimed.

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
