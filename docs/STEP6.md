# Step 6: local React / FastAPI inspection app

Implemented and verified on 20 November 2026. The app calls the existing Python
inference, alignment and comparison functions; there is no second scoring
implementation. See [Step 4](STEP4.md), [Step 5](STEP5.md) and the [design](SDD.md).
Manual landmarks are the default because the frozen pilot rejects development
photos. Thresholds remain provisional. Windows `.bat` packaging belongs to Step 7.

## Prepare dependencies once online

Use the existing CPython 3.10 environment described in [Step 3](STEP3.md#windows-setup).
From PowerShell:

```powershell
Set-Location A:\IndustryAI_Project
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
Set-Location A:\IndustryAI_Project\frontend
npm ci
```

`requirements-web.txt` includes the core lock plus FastAPI/Uvicorn, multipart
parsing and test-client dependencies. The existing lock's `idna` and
`typing_extensions` pins move to 3.20 and 4.16.0 for the web dependencies; model,
image-processing versions, weights, labels and frozen settings are unchanged.
The npm lock pins React 19.3.1, Vite 8.3.8 and Playwright 1.65.1. No CDN library,
font, image or cloud API is needed during inspection.

## Exact startup commands

Backend, PowerShell terminal 1:

```powershell
Set-Location A:\IndustryAI_Project
.\.venv\Scripts\python.exe -m uvicorn pcb_landmarks.web:app --host 127.0.0.1 --port 8000
```

Frontend, PowerShell terminal 2:

```powershell
Set-Location A:\IndustryAI_Project\frontend
npm run dev
```

Open **http://127.0.0.1:5173/**. Vite binds to loopback port 5173, refuses to
silently choose another port, and proxies `/api` to loopback port 8000. Stop either
terminal with Ctrl+C. Inspection uses local files; keep both terminals running
for this development mode.

For a production frontend served directly by FastAPI, build once:

```powershell
Set-Location A:\IndustryAI_Project\frontend
npm run build
```

Keep the backend command above running and open **http://127.0.0.1:8000/**.
This mode needs no Vite server or Node.js process during inspection. Both modes
were exercised in Chromium. Generated `frontend/dist/` stays local/ignored and
must be built from source on a fresh checkout. No `.bat` launcher is supplied.

## Operator workflow and coordinate contract

1. Upload one complete, sharp, known-good JPEG/PNG reference, then one to three
   inspection photos of the same layout and side. Select each photo's tab to
   annotate it. Corrupt photos retain their own error instead of discarding
   siblings. A rejected upload also leaves other successfully uploaded photos.
2. In **Manual**, select L0–L3 in the panel and click each physical mounting-hole
   center. Order: `upper_left_mount`, `upper_right_mount`, `lower_right_mount`,
   `lower_left_mount`, relative to the board's canonical orientation. Correct a
   point by selecting it and clicking again, dragging while marking, or editing
   its numeric x/y fields. No sorting by current screen position occurs.
3. On the reference, choose **Draw part boxes** and drag around expected parts.
   Select each named component to edit its name or x1/y1/x2/y2, toggle an explicit
   review flag with its reason, or remove it. **Add box** plus numeric fields
   provides a keyboard alternative to drawing. Duplicate/empty names are rejected.
4. Leave sharpening off initially. The app displays the shared provisional
   Missing <= 0.25 / Present >= 0.50 thresholds; intermediate or uninterpretable
   scores need review. A review flag bypasses classification even at full coverage.
5. Choose **Inspect photos**. Each photo receives separate alignment and component
   overlays plus a table of statuses, similarity, coverage and reasons. Click an
   overlay for its full-resolution local asset. Failed alignment has a distinct
   message and Not evaluated rows, never fabricated Missing/Present decisions.
   The JSON report retains the configuration and annotation snapshot.

The SVG uses the decoded image width/height as its viewBox. Pointer coordinates
are mapped through the SVG's *actual displayed rectangle* into that original
pixel grid, including when the viewport constrains the preview-width slider.
Landmarks remain pixel floats. Drawn rectangle minima are floored and maxima
ceiled once, giving half-open integer xyxy bounds. Resizing affects display only.
Both numeric and pointer annotations are sent in original pixels and saved in
the batch report's `annotations`. Changing annotations/mode/sharpening clears stale
displayed results; an inspection uses a captured request and new output directory.

EXIF orientation other than 1 is rejected through the shared reader. Normalize
the raster before annotating; the browser never silently rotates an annotation
frame. The backend serves a canonical decoded PNG for preview and processing.

### Automatic mode

**Automatic** invokes `LandmarkDetector` with `configs/landmarks.json`, CPU device,
image size 640, board confidence 0.95 and point confidence 0.99, validating the
checkpoint SHA-256 and landmark names. The default local checkpoint is
`runs/landmarks/full/weights/best.pt`; an operator can set `PCB_CHECKPOINT` in the
backend terminal before startup to an existing local checkpoint with that same
frozen hash. Missing weights do not block Manual mode or trigger downloads.

Automatic coordinates are read-only. Rejection reasons are shown verbatim, with
**Switch to Manual** as an explicit action. Selecting Automatic does not use
previous Manual points as a fallback. At execution the backend obtains its own
automatic prediction instead of trusting client-supplied automatic coordinates.
A rejected reference prevents alignment of all photos; a rejected inspection
affects only that inspection. There is no claim that this pilot has an accepted
automatic four-point development example.

## Verification actually performed

Environment: Windows, CPython 3.10.11, Node 26.7.0 / npm 11.19.0, FastAPI 0.162.5,
Uvicorn 0.54.0, React 19.3.1, Vite 8.3.8, Playwright 1.65.1 / Chromium 159.0.8154.6.
OpenCV 4.13.0, NumPy 2.1.3 and Pillow 11.3.0 retain their Step 5 versions.

### Real ECCC5 / ECCB5 in the browser

Uploaded the tracked validation-layout E images through the UI. Entered the
reviewed Step 2 landmarks into Manual fields and created the Step 5 component
boxes through the UI (same names, boxes and review reasons as
`configs/components-ECCC5.json`). Original decoded sizes are 1174x1536 and
1162x1536. The exact pixel coordinates used were:

| Identity | ECCC5 reference (x,y) | ECCB5 inspection (x,y) |
| --- | --- | --- |
| L0 upper_left_mount | (256.72576488, 376.88567808) | (245.45068926, 419.2072704) |
| L1 upper_right_mount | (953.35461276, 373.4152704) | (889.75003502, 399.66706176) |
| L2 lower_right_mount | (908.94799232, 1323.61138176) | (849.83026870, 1339.62089472) |
| L3 lower_left_mount | (308.07092490, 1324.99954176) | (294.02438086, 1329.9903744) |

The browser test reads the labels at full floating precision. These rounded display
values identify the same physical points. Component bounds and their visual
selection rationale remain in [Step 5](STEP5.md#reused-region-format-and-selected-features).

| Component | App similarity, sharpening off | App decision | Step 5 CLI agreement |
| --- | ---: | --- | --- |
| U2 chip | 0.5904881954193115 | Present | Exact score and status |
| AM335x processor | 0.5160602927207947 | Present | Exact score and status |
| Ethernet housing | null | Needs review: flagged parallax | Same gated decision |
| USB housing | null | Needs review: flagged parallax | Same gated decision |

All four regions had full coverage. The real-photo outcome was `review`, with
two Present and two uncertain findings. The test ran fresh Step 4 alignment and
the actual Step 5 comparison CLI with the same images/labels/configuration into
new ignored directories, then compared against the app response. UI-created
component IDs are new UUIDs; names/boxes/settings identify the matching regions.
Both overlays and the compact component table were viewed in the browser.

With the actual local trained checkpoint available, Automatic mode returned
**`Reference: no_confident_board`** and the UI showed **Alignment needs review**,
**Component scoring skipped**, and Not evaluated rows with null scores. The
operator explicitly switched back to Manual. No frozen settings were relaxed.

Then a corrupt `broken.png` was added to that same Manual batch. ECCB5 retained
its `review` result and both overlays, while broken.png independently returned
`error` with an image-decode reason and no overlays. A separate API test also
placed a degenerate-point photo beside a valid photo: `error`, `missing`, `retake`
results remained in input order. API tests verify unavailable weights return
`checkpoint_unavailable` and never fall back to otherwise valid Manual points.

Browser annotation checks drew/named/edited/removed a box, kept existing point and
box coordinates unchanged when preview width became 400px and viewport width
became 1000px, and placed a new point and box on that resized canvas. The point
mapped to approximately (117.4,153.6) in ECCC5 pixels; the drawn box matched
[117,153,235,308] within 3 original pixels of pointer quantization. Exact rounding
and inverse scaling also have independent Node unit tests. Layout was checked
at 1440px desktop and 375px mobile; the page did not overflow horizontally, while
the result table intentionally scrolls within its own container on narrow screens.

### Synthetic missing-part result, separately

The committed `tests/comparison_fixture.py` generates the original synthetic PCB
pair and controlled textured chip removal described in Step 5. Both Vite and the
production app served by FastAPI were driven through upload, numeric Manual
annotation, component creation, explicit **synthetic demonstration** flag and
inspection. The synthetic banner was visible above the results.

| Synthetic region | Off score | On score | Both modes |
| --- | ---: | ---: | --- |
| Retained chip | 0.9757468700 | 0.9842783213 | Present |
| Controlled removal | 0.2055528164 | 0.2407850027 | Missing |
| Coverage control (54.270833%) | null | null | Needs review |

The sharpening checkbox was exercised through the UI; the response flag changed
and both sides used the shared symmetric unsharp function. Decisions matched
Step 5 in both modes. Production browser tests blocked all non-loopback requests:
no external asset requests were observed. This is local-runtime browser evidence,
not a physical Wi-Fi-off packaging/restart acceptance test.

**Pending real missing-part validation:** no matched, confirmed real missing-part
photo was available. The successful Missing example above is synthetic and does
not establish real-defect recall or production readiness.

### Commands and actual check results

```powershell
Set-Location A:\IndustryAI_Project
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
Set-Location A:\IndustryAI_Project\frontend
npm test
npm run build
# First browser-test preparation only, if Chromium is not installed locally:
npx playwright install chromium
npm run test:browser
```

- Python: **35 tests passed**, 0 failures/errors, **8.914s**, including all 28
  preexisting tests and 7 API/integration regressions. `pip check`: no broken
  requirements. Dependency-lock dry run found all pinned packages satisfied.
- Frontend coordinate checks: **2 tests passed**; production build succeeded,
  **16 modules**, JS **237.91 kB** / gzip **74.50 kB**, CSS **9.79 kB**.
- Chromium: **4 browser tests passed in 13.7s**: upload rejection isolation
  (simulated 413), real Manual/CLI equality plus Automatic/mixed-batch/coordinate
  checks, synthetic Vite workflow, synthetic production workflow. The synthetic
  tests include sharpening, non-loopback request blocking and mobile layout.
  No page JavaScript errors or external requests were observed in the real run.
  Playwright emits a terminal-only NO_COLOR/FORCE_COLOR warning in this host;
  no application failure results from it.

The browser suite builds the frontend, starts/reuses the two local servers and generates its own
synthetic/CLI assets from tracked inputs. Screenshots and JSON evidence remain
under ignored `runs/web-verification/`; no prior generated alignment output is
needed to run it on a prepared checkout.

The first browser run caught a genuine integration defect: Ultralytics patches
Pillow's global `Image.open` after loading, causing later corrupt uploads to enter
its optional HEIF fallback. A regression failed before the fix. The shared reader
now captures Pillow's decoder before YOLO loads, and upload format checks use that
same decoder. Corrupt JPEG/PNG input remains a photo error without a new format
dependency or auto-install attempt. All reader callers retain orientation handling.

## Local API, persistence and scope

`pcb_landmarks.web:create_app` owns these small local endpoints:

| Endpoint | Behavior |
| --- | --- |
| GET `/api/health` | Landmark names, shared comparison settings, local checkpoint availability |
| POST `/api/photos` | One multipart `image`; return UUID, filename, decoded size, local preview URL or photo-specific decode error |
| POST `/api/landmarks/{photo_id}` | Local frozen inference, ordered pixels or actual failure reason |
| POST `/api/inspections` | Reference ID/points, 1–3 inspection IDs/points, components, Manual/Automatic, sharpening and synthetic flag; independent ordered results |
| GET `/api/photos/{photo_id}/image` | Canonical decoded PNG |
| GET `/api/batches/{batch_id}/report` | Captured batch JSON |
| GET `/api/batches/{batch_id}/{index}/{alignment,components}` | Available per-photo overlays |

Uploads and reports live under `A:\IndustryAI_Project\runs\web\photos\<UUID>`
and `runs\web\batches\<UUID>`. No submitted filename or filesystem path selects
an output path. Known UUID/asset routes constrain file access. Backend/Frontend
bind to loopback, writes reject foreign browser origins, and upload requests
require Content-Length with a 13 MiB total request cap. Individual files are
capped at 12 MiB, decoded images at 20 million pixels, batches at 3, components at
100, IDs at 100 characters, names at 120 and review reasons at 500. Invalid
shared metadata fails before scoring; local crop/coverage gates reuse Step 5.

Browser draft state resets on refresh; completed report URLs and their original
pixel annotation snapshots persist on disk. A saved-reference library/reopen editor
is not added in this workflow slice. There is no automatic retention cleanup.
Full global blur/glare/layout/independent alignment acceptance and dense-region
overlay-label calibration remain outside this provisional pilot.

Only backend/frontend source and lock files, tests and documentation are committed.
Local weights, private photos, uploads, run evidence, browser logs, node_modules
and built dist assets remain ignored. Real test inputs were already tracked and
publication-cleared under the [Step 2 provenance](../PCB_Dataset_Pilot/README.md).
