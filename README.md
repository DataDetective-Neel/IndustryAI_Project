# Offline PCB inspection demo

Compare a known-good PCB photo with up to 15 same-layout inspection photos.
The local React frontend and FastAPI backend share the alignment/comparison CLI
functions. **Thresholds are provisional; real missing-part validation is pending.**
Synthetic erasures are review fixtures, not verified real missing-component evidence.
The current one-board demo reports PRESENT or REVIEW; MISSING is withheld until an
absence exemplar is verified. See [November 21 evidence](docs/guides/DEMO_RELIABILITY.md).

Before component scoring, a [board compatibility check](docs/guides/BOARD_COMPATIBILITY.md)
uses distributed connector, mounting-region and silkscreen features. Positively
recognized mismatched layouts return `DIFFERENT_BOARD` and skip component decisions.
Blur, cropping, unknown layouts and uncertain alignment remain `REVIEW`.

[Mounting-hole correction evidence](docs/guides/MOUNT_CALIBRATION.md) covers the pictured
Pi and Mega2560 layouts, direct-versus-uploaded inference, and remaining REVIEW cases.

## Windows prerequisites

- 64-bit CPython **3.10**, installed with the Windows `py` launcher (`py -3.10`).
  The pinned Python environment is supported/tested on this minor version.
- **Node.js 24 or newer and npm 10 or newer**, available on PATH. Reopen the
  terminal after installation. Node/npm are needed for setup, not offline launch.
- Disk space for Python/PyTorch dependencies and the frontend build. Initial
  setup needs internet unless all dependencies are already locally available.
  Cached packages alone do not guarantee that every required wheel is available.

## Setup once, launch repeatedly

From PowerShell, including from another working directory:

```powershell
& 'A:\IndustryAI_Project\setup.bat'
& 'A:\IndustryAI_Project\launch.bat'
```

Scripts resolve their own directory, including paths with spaces. Setup creates
or reuses `.venv`, validates its Python version, installs `requirements-web.txt`,
runs `npm ci` against `frontend/package-lock.json`, then builds `frontend/dist`.
It stops at the first failed step and returns exit 1; fix the printed problem
and rerun it. A mismatched existing virtual environment must be moved aside and
recreated with supported Python; setup does not silently delete environments.

Launch uses only `.venv` and the built frontend, serves on **127.0.0.1:8000**, and
prints [the browser URL](http://127.0.0.1:8000/). It installs nothing and builds
nothing. Missing dependencies/build outputs point you back to `setup.bat`.
Keep the terminal open so server errors remain visible. **Stop with Ctrl+C**;
if cmd asks `Terminate batch job (Y/N)?`, answer Y. No detached server is started.
If another server owns port 8000, stop that server before launching this one.

After setup, disconnect Wi-Fi/Ethernet while retaining normal local loopback
networking, then run `launch.bat`. No CDN, cloud service, Vite server or Node.js
process is required for inspection. Photos, annotations and reports stay under
ignored `runs/web/`. Refreshing the page resets the editor; completed report URLs
and annotation snapshots remain on disk. There is no automatic retention cleanup.

## Reuse a confirmed reference automatically

YOLO proposes the reference landmarks as usual. Correct or mark its four ordered
points, review the separate cyan PCB outline, and click **Confirm reference setup**.
Inspection photos then use verified YOLO candidates or offline reference feature
registration before requesting manual clicks. Projected landmarks are labeled;
component boxes remain in original reference pixels. Replacing the reference
clears its setup and stale inspection points.

See [reference registration and verification](docs/guides/reference-registration.md) for
workflow details, tested designs, rejection cases and remaining limitations.

## Reproducible synthetic demo without dataset or weights

Generate the original shareable fixture locally after setup; use a new output
directory when repeating this command:

```powershell
Set-Location A:\IndustryAI_Project
.\.venv\Scripts\python.exe tests/comparison_fixture.py --output runs/demo
# Print each photo's four original-pixel landmarks, in dataset order:
.\.venv\Scripts\python.exe -c "from pcb_landmarks.data import read_image; from pcb_landmarks.align import label_points; from pathlib import Path; [print(n, label_points(Path('runs/demo/input')/(n+'.txt'), read_image(Path('runs/demo/input')/(n+'.png')).size).tolist()) for n in ['reference','inspection']]"
.\launch.bat
```

No `PCB_Dataset_Pilot` directory or checkpoint is needed for this Manual demo.

1. Upload `runs/demo/input/reference.png` as reference and
   `runs/demo/input/inspection.png` as inspection. Check **Label this run as a
   synthetic demonstration**, and leave **Manual** selected.
2. For each photo, enter the printed x/y pairs into L0–L3, in the displayed order:
   upper-left, upper-right, lower-right, lower-left **physical identities**.
   Reference pairs are (35,30), (285,30), (285,210), (35,210). Points may also be
   marked/corrected by clicking. Preview resizing does not change stored pixels.
3. Select the reference, use **Add box** or draw rectangles, then enter these
   names and integer half-open xyxy bounds in the region editor:

   | Name | x1 | y1 | x2 | y2 |
   | --- | ---: | ---: | ---: | ---: |
   | Retained chip | 60 | 45 | 100 | 85 |
   | Controlled removal | 140 | 100 | 180 | 140 |
   | Coverage control | 0 | 50 | 24 | 90 |

4. Leave sharpening off and choose **Inspect 1 photo**. Expect **Present** for
   the retained chip, **Needs review** for the controlled removal and **Needs review**
   for the partially covered control. Inspect both overlays and the component
   table. The synthetic banner must be visible. Review flags can explicitly
   prevent scoring unreliable regions such as tall connectors with parallax.

Present >= 0.50 after bounded local search and alignment validation; other scores,
low texture, bad crops, incomplete coverage and flagged regions need review.
The legacy missing_max configuration field remains readable for compatibility but
does not classify absence. Low correlation can also
come from glare or misalignment. These pilot decisions do not certify a board.

## One-board submission demo

Upload `PCB_Dataset_Pilot/images/val/ECCC5.jpg` as the known-good reference.
Eight named component boxes load from `configs/components-ECCC5.json` only when
its decoded raster matches exactly. Mark the four mounting holes on both images
in Manual mode. Automatic mode exposes rejected raw keypoints for correction;
these are tentative and must be checked against the physical mounting holes.

Reproduce the real-photo and generated perspective/crop/erasure cases through
FastAPI's real upload, landmark and inspection endpoints:

```powershell
.\.venv\Scripts\python.exe -m pcb_landmarks.demo_check
Set-Location frontend
npm run test:browser
```

The browser demo test uses the fixtures generated by `demo_check`. Saved matrices,
per-image raw diagnostics, reports, overlays and browser screenshots are under
`runs/demo-evidence`. The perspective and erasure photos are explicitly synthetic.
Local search is limited to at most six pixels around each expected box; larger
parallax or appearance changes require review. Zero/invalid overlay evidence with
no convincing local matches cannot yield PRESENT or MISSING.

## Automatic mode: optional local checkpoint

Manual mode works without weights. Automatic uses the checkpoint path, hash and
settings in `configs/landmarks.json`; it never downloads a model or silently
substitutes Manual points. Current checkpoint: `models/pcb-mounting-holes-yolo26n-pose.pt`.
The tuned profile targets the Raspberry Pi board shown in MCCB5, with mandatory
OpenCV verification of visible gold mounting rims and a known-board orientation
pattern stored in `configs/mounting-holes-M.png`. See [fine-tuning evidence](docs/guides/LANDMARK_FINE_TUNING.md).
For another local path, set it before launching in the same PowerShell terminal:

```powershell
$env:PCB_CHECKPOINT = 'A:\Local Models\best.pt'
& 'A:\IndustryAI_Project\launch.bat'
```

That file must match the frozen checkpoint hash/schema. Automatic schema loading
also uses the repository's small `PCB_Dataset_Pilot/dataset.yaml` metadata file;
dataset photographs are not needed. With no checkpoint, the app displays
`checkpoint_unavailable` and offers **Switch to Manual**. The tuned confidence
gates are board >0.75 and keypoints >=0.85, followed by mandatory unique visible
rim verification. Failed visual verification or alignment skips component scoring
for that photo and preserves successful siblings. The earlier BeagleBone saved
regions remain available for the Manual benchmark; they are not applied to the Raspberry Pi.

## Verification and limitations

See [Step 7 actual verification](docs/steps/STEP7.md), [web workflow](docs/steps/STEP6.md),
[alignment](docs/steps/STEP4.md) and [comparison](docs/steps/STEP5.md).

Clean-copy setup, rerun, a spaces/outside-directory invocation, production
synthetic inspection under process-level external-network blocking, missing-weight
Manual mode, failure exits and launcher shutdown were verified on Windows.
**Physical adapter-off testing and a pristine Windows-machine installation remain
pending.** The test machine already had Python/Node and package/browser caches.
Real missing-part accuracy and full production-quality acceptance remain pending.
