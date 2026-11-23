# Step 7 verification record

Test host: Microsoft Windows 11 Home Single Language, version **10.0.26300**;
64-bit CPython 3.10.11; Node 26.7.0, npm 11.19.0. Date: 20 November 2026.

## Checks actually run

- Created `A:\PCB Offline Handoff` from tracked source plus the new scripts,
  explicitly excluding the entire dataset directory and graph artifacts. It
  initially contained no `.venv`, `frontend/node_modules`, `frontend/dist`, weights
  or run outputs. It is a clean **copy**, not a pristine operating-system install.
- Invoked `cmd.exe /c '"A:\PCB Offline Handoff\setup.bat"'` from
  `A:\IndustryAI_Project`, proving both spaces and an outside working directory.
  Exit 0: created a new venv, installed all declared pins, ran npm ci and built
  16 modules successfully. Python wheels included fresh downloads and cache hits;
  the new environment used the normal CPU PyTorch wheels, not the source checkout's
  CUDA installation. No global packages were changed.
- Repeated setup against the existing environment: exit 0; dependencies remained
  satisfied, npm ci and production build completed again.
- Injected a test-only npm.cmd that passed its version check but returned 9 for
  npm ci. Setup reported **Install frontend lockfile dependencies failed**, exited
  1 and did not run build (stub call log contained only `ci`).
- Copied launch.bat alone into an empty directory: exit 1 with setup recovery
  instructions. Scripts run the server in the foreground rather than detaching it.
- Launched the clean copy from outside its directory using launch.bat, with a
  test-only Python `sitecustomize` guard that rejects non-loopback socket connects,
  connect_ex and external DNS resolution. An explicit example.com connection
  failed with `External DNS disabled for offline handoff verification` before
  launch. Loopback remained available. This guard was verification-only and is
  not installed by setup or launch.
- Ran the existing Chromium **production synthetic** browser test from the clean
  copy: **1 passed in 2.0s**. That test blocks non-loopback browser-page requests,
  generates the fixture from the shareable source, uploads the pair, enters Manual
  landmarks/regions, labels it synthetic and runs inspection against port 8000.
  There was no dataset directory, model checkpoint, or dependency on the Vite UI.
  The test harness reused an already-running development server for its general
  configuration, but the tested page and all app asset/API requests used port 8000.
- Health returned checkpoint_available=false. Manual inspection produced:

  | Synthetic component | Sharpen off score | Decision |
  | --- | ---: | --- |
  | Retained chip | 0.9757468700408936 | Present |
  | Controlled removal | 0.2055528163909912 | Missing |
  | Coverage control | null, 54.270833% coverage | Needs review |

  The same browser test exercised sharpening on (removal 0.240785, still Missing)
  and mobile layout. These are synthetic smoke-test results, not real defect recall.
- Sent Ctrl+C to the foreground launcher. Afterwards port 8000 had no listening
  process. No orphaned server remained. The automation host reports interrupted
  processes as exit 1; ordinary failure exits also intentionally remain nonzero.
- Full Python suite after the dataset-independent health change: **36 passed,
  zero failures/errors, 5.466s**. Frontend dependency audit found zero vulnerabilities during npm ci;
  production builds completed on clean setup and repeat setup.

## Scope of offline evidence

External connections were blocked for the Python server and the browser page,
with loopback preserved. The host's physical network adapters were **not disabled**.
Therefore physical Wi-Fi/Ethernet-off testing and a fresh machine without existing
toolchains/caches remain pending. The clean-copy test does prove that no source
venv, node_modules, build, PCB photos or weights were needed to prepare that copy,
and that its prepared production app completed the controlled Manual demo under
the stated external-network blocking.

## Implementation notes

Setup pins Python 3.10 x64 and declares Node >=24 / npm >=10 in the frontend
package metadata and checks the same prerequisites. Every install/build boundary
checks errorlevel and reports its step. The launcher validates local imports,
comparison config and production HTML/JS/CSS outputs, then uses the existing
FastAPI production serving routes. It performs no install, npm operation or build.

Health now reads landmark names from frozen configuration rather than the dataset
YAML, removing the dataset requirement from Manual mode. A regression test covers
health with only configs present. Automatic still validates local trained weights
and schema through the original inference contract. Weight absence is an explicit
Needs review reason, not an application-wide failure or automatic download.

Generated artifacts and verification-only guards/stubs remain local. Thresholds
remain provisional; matched real missing-part validation remains pending.
