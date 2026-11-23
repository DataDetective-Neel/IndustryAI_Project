# Documentation index

Specifications, per-step implementation records and verification evidence for the
offline PCB inspection demo. Start with the [project README](../README.md) for
setup and launch; the documents below cover requirements, design and measured results.

## `specs/` — baseline requirements and design

- [SRS.md](specs/SRS.md) — software requirements specification, terms, result rules and acceptance cases.
- [SDD.md](specs/SDD.md) — software design document: pipeline, contracts, open decisions.
- [DFD.md](specs/DFD.md) — data flow diagrams for the inspection pipeline.

## `steps/` — implementation record, step by step

Each step carries an implementation document plus, where applicable, its plan and measured results.

- [STEP3.md](steps/STEP3.md) — four-landmark YOLO26n pose training and evaluation; [plan](steps/STEP3_PLAN.md), [results](steps/STEP3_RESULTS.md).
- [STEP4.md](steps/STEP4.md) — four-point alignment, validity mask and overlay; [plan](steps/STEP4_PLAN.md).
- [STEP5.md](steps/STEP5.md) — component comparison and review report; [plan](steps/STEP5_PLAN.md).
- [STEP6.md](steps/STEP6.md) — local React / FastAPI inspection app; [plan](steps/STEP6_PLAN.md).
- [STEP7.md](steps/STEP7.md) — verification record for the Windows setup and launch scripts.

## `guides/` — subsystem and evidence write-ups

- [BOARD_COMPATIBILITY.md](guides/BOARD_COMPATIBILITY.md) — layout check that runs before component decisions.
- [reference-registration.md](guides/reference-registration.md) — reference-based landmark reuse.
- [MOUNT_CALIBRATION.md](guides/MOUNT_CALIBRATION.md) — mounting-hole correction for the pictured layouts.
- [LANDMARK_FINE_TUNING.md](guides/LANDMARK_FINE_TUNING.md) — mounting-hole fine-tuning evidence, 21 November 2026.
- [DEMO_RELIABILITY.md](guides/DEMO_RELIABILITY.md) — one-board inspection evidence, 21 November 2026.
- [FRONTEND_REDESIGN.md](guides/FRONTEND_REDESIGN.md) — frontend verification notes.
- [DATASET_EXPANSION.md](guides/DATASET_EXPANSION.md) — landmark collection and split plan; row format in [expanded_manifest.template.csv](expanded_manifest.template.csv).

## Evidence and fixtures

- `results/` — JSON and image evidence produced by the comparison, calibration and reliability runs.
- `diagnosis/` — CPU trace and offline diagnosis output; written by `pcb_landmarks.diagnose`.
- `samples/` — sample photographs referenced by the guides above.
