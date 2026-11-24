# Repository validation — 24 November 2026

Validation uses the existing Windows checkout and installed dependencies. It does not establish performance on new PCB designs or field defect accuracy. Existing dataset changes, UI, model weights and runtime records are preserved.

## Environment

- Windows; PowerShell; Python 3.10.11 in `.venv`; Node.js 26.7.0; npm 11.19.0.
- Local production frontend built using Vite 8.3.8; browser checks use Playwright 1.65.1.
- External operator fixtures are available at `A:/IndustryAI_Dataset_Worktree/dataset_generation`. These are optional external test inputs, not a portable repository dependency.

## Initial results

| Command | Observed result |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest discover -s tests -v` | 112 tests in 269.706s; 111 passed, 1 stale-contract assertion failed |
| `cd frontend; npm test` | 4 passed |
| `cd frontend; npm run build` | Passed; generated `frontend/dist` |
| `cd frontend; npx playwright test` | 18 passed, 3 failed in 8.3m |
| `cd frontend; npx playwright test --config reference-reuse.config.js` | 1 passed in 18.3s |
| `cd frontend; npx playwright test --config repair.config.js` | 2 passed in 42.7s |

Initial logs: `runs/final-backend-validation.log`, `runs/final-browser-validation.log`, `runs/final-reference-validation.log`, `runs/final-repair-validation.log`. Initial backend and browser checks ran concurrently; no timing claim is made from their durations.

## Initial failures and diagnosis

- `tests/test_live_golden.py:27` expects 404 before a live reference is selected; the current endpoint deliberately returns HTTP 200 with JSON null. The test stops before its later live rotation/replacement assertions.
- `aoi-walkthrough.spec.js` cannot find its newly imported review records. The fixed persistent test storage already contained 105 pending reviews, exceeding the displayed queue. Clean storage is required for repeatable validation.
- `crash-fixes.spec.js` clicks the removed navigation label `Access Management`; the current navigation is `Account Settings`.
- `workflow.spec.js` counts Present findings while the current default findings filter shows only issues. It must select `All` before asserting all present rows.

## Scenario evidence

| Scenario | Executed evidence and limits |
| --- | --- |
| Identical image | Alignment identical-raster regression passed; production demo browser passed; identical reference shortcut is tested. |
| Missing part | Synthetic comparison/CLI and real photograph missing-capacitor regressions passed; manual missing-board scoring recovery passed. These fixtures do not establish population accuracy. |
| Misaligned part | Real operator image repair browser passed: U2 misaligned, 33 parts present, 34 persisted decisions; rotation/shift comparison regressions passed. |
| Different PCB design | Board compatibility backend and production browser passed; component scoring is skipped for positively identified different boards. |
| Corrupt image | API corrupt-upload and mixed-sibling isolation passed; browser invalid reference replacement passed. |
| Multiple input images | API 15-image results/overlays and browser 15-upload workflow passed; live multiple-import checks passed. |
| Multiple simultaneous defects | Controlled generated-photo API check matched U4 missing and C1 misaligned, with 32 present; see recheck evidence below. |
| Missing checkpoint | Explicit failure/fallback backend checks and browser reference-reuse suite passed. |
| Model loading | Actual model inference/scoring regression and calibrated landmark tests passed; repaired operator browser asserts inference ran. |

Model SHA-256 checks observed: mounting-hole checkpoint `a3035f835ff92d57b452f7c43edf566cf83e50b9752623b00e044e4ee6d773a3` matches `configs/landmarks.json`; component weights `1065cdb4a32d65799b6308dc267ec9c66a1a0d261293738417bff316697725ec`; base pose weights `eb3bb8268828aeaf515cec23a4bfafd793944a86fe9af94ba7823609c14522a9`.

## Scope and limitations

`setup.bat` and `launch.bat` were inspected. Setup checks Python 3.10/64-bit and Node/npm, installs locked dependencies, and builds; launch checks installed imports, config, and built assets before serving loopback. Fresh installation and OS-level browser camera hardware were not exercised. Browser camera checks use simulated media/denied access. No weight files or datasets were altered by validation. The checked-in generated dataset and third-party external fixtures require separate provenance and generalization review.

## Corrections and focused rechecks

Only test expectations and default Playwright isolation were corrected. The live-reference regression now verifies HTTP 200/null; browser navigation uses Account Settings; the manual findings test selects All and checks present status classes. Default Playwright runs now use a new timestamp/process-specific store and refuse to reuse an existing server, preventing accidental use of stale test data or an unrelated running app.

- Focused live golden regression: 1 passed in 38.641s, including identical/rotated input, rejected corrupt replacement, pause/resume and reference replacement.
- Three previously failing browser tests: 3 passed in 1.1m using clean storage.
- Real generated multiple-defect photograph `multiple_defects_001.png`: HTTP 200; verified alignment; actual landmark inference ran; U4 missing and C1 misaligned; 32 parts present. This matches the two annotated affected IDs. Evidence: `runs/final-multiple-defects.json` and `runs/validate_multiple_defects.py`. This is one generated fixture, not an accuracy benchmark.
- Root agent ran `setup.bat` successfully (exit 0), including dependency installation and frontend production build; evidence `runs/final-setup-validation.log`. Fresh empty-machine installation remains untested.

## Final achieved results

| Validation | Final result |
| --- | --- |
| Full backend unittest rerun | **112 passed**, 331.203s; `runs/final-backend-recheck.log` |
| Full default browser rerun, fresh test storage | **21 passed**, 5.6m; `runs/final-browser-recheck.log` |
| Reference-reuse browser suite | **1 passed**, 18.3s; `runs/final-reference-validation.log` |
| Operator repair browser suite | **2 passed**, 42.7s; `runs/final-repair-validation.log` |
| Frontend unit suite | **4 passed** |
| Frontend production build | **Passed** |
| Setup script on existing local environment | **Passed**, exit 0; `runs/final-setup-validation.log` |
| Multiple simultaneous defect fixture | **Matched annotated affected IDs**, verified registration and real inference |

The final full backend and browser reruns pass after correcting the stale tests and isolating browser storage. No application UI, inspection logic, model weights or dataset contents were changed for these corrections. Initial failures remain documented above for reviewability. Dedicated browser suites ran before these test-only corrections and were already green. The final runs cover identical, missing, misaligned, different-board, corrupt, multiple-input and multiple-defect scenarios with the fixture and generalization limits stated above.


## Windows script execution

- `cmd /c setup.bat`: exit 0 in the existing environment; installed requirements, checked both weight hashes, created runtime directories and built the frontend.
- Repeated setup from another working directory using a temporary path containing spaces: exit 0. The temporary script copy used junctions to the existing dependencies/source/model assets; this proves path handling and repeat execution, not a pristine installation.
- `launch.bat` from that space-containing path and another working directory: API health returned `ok`, configured landmark checkpoint was available, and production frontend returned HTTP 200.
- A second launch returned exit 1 with `Port 8000 is occupied`; the first server remained healthy. No unrelated process was terminated.
- Launch with a missing checkpoint override returned exit 1 with an explicit missing/invalid model error.
- Smoke-test cleanup terminated only its own process tree. Interactive Ctrl+C and physical adapter-off restart were not exercised in this pass.

Evidence remains in ignored `runs/final-script-validation.json`, `runs/final-setup-spaces.log`, `runs/final-launch-smoke.log`, `runs/final-launch-occupied.log` and `runs/final-launch-missing.log`.

## Submission hygiene

Both execution checkpoint hashes match configuration; the existing 20,373,061-byte component checkpoint is now included for portable golden-reference/live workflows. No frontend source, backend inspection logic, model parameters, training data or calibration was changed. No tracked source deletion was justified; historical evidence, training scripts and design specification are preserved. Dependency/build/runtime directories remain local and ignored. Pre-existing pilot dataset work is deliberately excluded from the preparation commit.

Authored relative documentation links and fenced blocks passed checks. Original transcript links may name moved historical local artifacts; their wording is preserved. Original transcript spacing and generated architecture bytes are exempted from whitespace checks through scoped `.gitattributes` entries, preserving evidence/provenance. A high-confidence credential-pattern scan of 638 historical text blobs found no matches; this is not a claim of exhaustive secret detection. Final staged whitespace checks exclude the preserved pre-existing dataset edit.
