# IndustryAI — local PCB optical inspection

ForgeSight compares a known-good PCB photo with photos of the same board layout and side. Landmark geometry and verified image registration align each inspection before expected component regions are compared. This helps an operator investigate missing or displaced components without treating every image difference as a defect.

This is a CPU-capable local engineering demonstration for students, evaluators and inspection operators. Thresholds are provisional. Controlled and selected real-photo regressions do not establish production accuracy or universal PCB compatibility.

## Implemented features

- Reference upload, automatic landmark proposals, manual four-point correction and confirmed reference reuse.
- YOLO26 pose landmarks with existing mounting-hole verification; independently verified SIFT/RANSAC registration can provide a fallback.
- Editable expected component regions, existing local component proposals and explicit component-map import.
- Up to 15 inspection images per batch, with per-photo failure isolation, geometric/coverage checks and board compatibility checks.
- Reference-region structural comparison, corroborated missing-part decisions and local shift/rotation evidence. Uncertain evidence remains Needs review.
- Paired overlays, JSON reports, dashboard/review decisions, saved golden library and role-based platform controls.
- Live browser camera frames and local image-queue simulation through the same pipeline. Physical camera/conveyor operation is not certified.
- Offline inference after dependencies, frontend assets and weights are installed locally.

The repository already contains a ParsaVictor YOLO26 component locator alongside the landmark model. It proposes regions and contributes correspondence evidence; an unmatched detection alone does not establish absence. This submission preserves that existing feature and introduces no new detector. Manual region inspection remains available. Existing catalog/calibration assets target a limited group of boards; arbitrary-board generalization is unproven.

## Stack and requirements

| Item | Actual configuration |
| --- | --- |
| Supported launch workflow | Windows, 64-bit CPython 3.10 with `py -3.10` |
| Frontend | React 19, Vite 8; Node.js >=24, npm >=10 during setup/development |
| Backend | FastAPI/Uvicorn; NumPy, Pillow, OpenCV; local SQLite platform store |
| Models | PyTorch/Ultralytics YOLO26; local hash-checked pose and component checkpoints |
| Tests | Python unittest, Node test runner, Playwright |
| Inference hardware | Web inference uses CPU; GPU is not required. Training device is separately configurable. |
| Network | Initial package/browser installation needs internet; normal built application uses local assets and loopback only. |
| Resources | No validated minimum RAM, install-space or latency specification. Python/PyTorch installation needs additional disk space beyond repository assets. |

Other operating systems may support manual commands, but `.bat` launch/setup and this validation target Windows. See [actual validation](docs/VALIDATION_REPORT.md) for environment and executed checks.

## Quick start — Windows

Clone the existing repository, then open a terminal in its root:

```bat
git clone https://github.com/DataDetective-Neel/IndustryAI_Project.git
cd IndustryAI_Project
setup.bat
```

Setup resolves its own directory, checks Python/Node/npm, creates or reuses `.venv`, installs the pinned Python requirements and frontend lockfile, validates model hashes, creates runtime directories and builds the frontend. It stops on a critical error. Rerunning it is supported; it does not retrain models or delete an incompatible environment.

Before the **first** launch, choose administrator credentials in PowerShell:

```powershell
$env:PCB_ADMIN_USERNAME = 'admin'
$env:PCB_ADMIN_PASSWORD = Read-Host 'Choose an administrator password (at least 10 characters)'
.\launch.bat
```

For later launches, run:

```bat
launch.bat
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Launch runs one foreground backend serving both API and built frontend; it needs no Vite or Node process. Keep its terminal open and stop with Ctrl+C (confirm Y if cmd asks). Occupied port 8000 stops launch without killing another process. Browser opening is manual.

Accounts persist in ignored `runs/web/aoi.db`; setting a new environment password does not reset an existing account. Account Settings exposes user management to administrators. Do not commit actual passwords or runtime databases.

## Manual installation

From the cloned repository root on Windows:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
Push-Location frontend
npm ci
npm run build
Pop-Location
# Set first-run administrator credentials as above, then:
.\.venv\Scripts\python.exe -m uvicorn pcb_landmarks.web:app --host 127.0.0.1 --port 8000
```

The two execution checkpoints are included under `models/`:

| File | SHA-256 |
| --- | --- |
| `pcb-mounting-holes-yolo26n-pose.pt` | `a3035f835ff92d57b452f7c43edf566cf83e50b9752623b00e044e4ee6d773a3` |
| `pcb-components-yolo26s.pt` | `1065cdb4a32d65799b6308dc267ec9c66a1a0d261293738417bff316697725ec` |

They total approximately 26.3 MB (decimal); neither requires Git LFS. `configs/landmarks.json` and `configs/component_model.json` define paths and hashes. `PCB_CHECKPOINT` and `PCB_COMPONENT_CHECKPOINT` can point to equivalent local files; configured hashes must still match. There is no automatic download. Landmark schema metadata in `PCB_Dataset_Pilot/dataset.yaml` must remain available. Parsa attribution is preserved in [PARSA_LICENSE.txt](pcb_landmarks/PARSA_LICENSE.txt); dependencies have their own licenses.

For frontend development only, run `npm run dev` inside `frontend` while the backend runs on 8000. Vite uses [127.0.0.1:5173](http://127.0.0.1:5173/) and proxies `/api` to the backend. Production uses only port 8000.

## Operator workflow

1. Sign in and open **Inspection Lab**. Upload a sharp, complete golden PCB PNG/JPEG.
2. Review proposed reference points. Correct four consistent board-relative landmarks and reference geometry as needed, then **Confirm reference setup**. Manual corrections do not train or update model weights.
3. Review component proposals; accept, edit, remove or draw expected rectangles. Regions use original image pixels and apply only to their reference. Resolve unknown proposals before saving golden configuration.
4. Upload 1–15 inspection photos of the same layout and side. Use Automatic registration or explicitly correct Manual correspondences. Physical landmark identities must remain consistent through rotation.
5. Inspect the batch. Compatibility and verified alignment gate comparison; unreliable geometry produces review/failure rather than fabricated component defects.
6. Review Present, Missing, Misaligned and Needs review evidence, plus different-board rejection and per-photo errors. The default issues filter hides Present rows; select **All** to see every component.
7. Save a golden configuration/library entry for reuse. Live Inspection can use camera frames or imported local photos; stop camera capture before starting an image queue. Review decisions and completed reports persist locally.

Start with tracked examples under `PCB_Dataset_Pilot/images/val/`. `ECCC5.jpg` has a legacy exact-image region preset; it is a demonstration aid, not universal board coordinates. Existing known-board calibration and catalog limits are documented in the SDD.

For a controlled synthetic pair, run `.\.venv\Scripts\python.exe tests/comparison_fixture.py --output runs/demo` into a new directory and inspect the generated input/labels. Mark synthetic runs as demonstrations. [Step 5](docs/steps/STEP5.md) explains the comparison fixture and coordinate workflow.

## Repository map

```text
README.md, AI_COLLAB.md, RESEARCH.md, ARCHITECTURE.md
setup.bat, launch.bat, requirements*.txt
frontend/                 React UI, lockfile, browser/unit tests, DESIGN.md
pcb_landmarks/            API, geometry, registration, comparison, models, training
configs/                  Frozen thresholds, schema and calibration assets
models/                   Required local execution checkpoints
PCB_Dataset_Pilot/        Original landmark dataset, labels and provenance
tests/                    Python regressions and controlled fixture generators
docs/specs/               SRS, SDD and DFD (Markdown)
docs/architecture/        Archify editable source, HTML and static export
docs/ai_history/          Genuine available collaboration history and evidence gaps
docs/VALIDATION_REPORT.md Actual executed validation and remaining limits
```

Generated runtime photos/reports/database live under ignored `runs/`; `.venv`, `frontend/node_modules` and `frontend/dist` are local setup outputs. Historical guides and audits remain evidence, with the current specifications taking precedence over old plans.

## Testing

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Push-Location frontend
npm test
npm run build
# First browser test installation requires internet:
npx playwright install chromium
npm run test:browser
npm run test:reference
Pop-Location
```

Stop app servers before browser tests so the test-owned servers can bind ports 8000/5173. Browser fixtures exercise real and controlled synthetic cases; some repair tests need separately documented external fixtures and are not portable acceptance evidence. See [validation report](docs/VALIDATION_REPORT.md) for exact commands, initial failures, repairs and final results.

For a basic manual check, configure a complete reference, inspect that identical image, confirm reliable regions are Present, then try a different board and a corrupt image. Review overlays and explicit error/review results. This checks workflow, not defect accuracy.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Python/Node/npm missing or wrong version | Install the required versions, reopen terminal and rerun setup. |
| Missing imports, assets or packages | Run `setup.bat`; inspect the first failed step. Do not remove lockfiles to bypass failures. |
| Missing/invalid checkpoint | Restore the tracked model file, check hash/config and any override variable. Direct backend/manual inspection can operate with limited model availability, but launch validates packaged assets. |
| Backend connection failure | Keep backend terminal open; check [health](http://127.0.0.1:8000/api/health). A health response reports availability, not successful model inference. |
| Occupied port | Close the existing server yourself or use manual developer startup on a chosen port; do not terminate unrelated processes. |
| Landmark or alignment failure | Correct reference points/outline, ensure same layout/side, or select Manual. Retake blurry, cropped, reflective or extreme-angle photos. |
| Corrupt/unsupported image | Use valid JPEG/PNG, <=12 MiB and <=20 million pixels; normalize EXIF orientation before upload. |
| Cannot sign in after changing environment | Existing accounts persist. Use the configured account; changing bootstrap credentials does not reset its password. |
| Camera unavailable | Use localhost, grant browser permission, or upload images. Physical camera validation remains separate. |

## Limits and evidence

Lighting, glare, shadows, parallax, repeated textures and severe perspective can invalidate local comparisons. Calibration/catalog recognition covers limited boards. Unknown layouts require a suitable reference and reliable independent registration; unseen-layout accuracy remains unmeasured. Missing components require multiple agreeing image cues. Review is not an automatic defect. No electrical defects, hidden solder-joint faults or production certification are claimed.

Runtime data has no automatic retention policy. Platform role checks do not make every low-level asset/lab endpoint a hardened network service; retain loopback binding. Full original ChatGPT history and some historical research evidence are still pending, explicitly indexed below.

## Documentation

- [AI collaboration decisions](AI_COLLAB.md) and [available original chat history](docs/ai_history/README.md)
- [Research and source selection](RESEARCH.md)
- [Architecture and Archify diagram](ARCHITECTURE.md)
- [SRS](docs/specs/SRS.md), [SDD](docs/specs/SDD.md), [DFD](docs/specs/DFD.md)
- [Validation report](docs/VALIDATION_REPORT.md) and [supporting documentation index](docs/README.md)
