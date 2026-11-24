# Documentation index

Specifications, per-step implementation records, subsystem write-ups and audit evidence for the
offline PCB inspection demo. Start with the [project README](../README.md) for
setup and launch; the documents below cover requirements, design and measured results.

## `specs/` — submission requirements and implemented design

- [SRS.md](specs/SRS.md) — retained requirement IDs and acceptance goals, actual result vocabulary, and source/test traceability with partial/planned status.
- [SDD.md](specs/SDD.md) — current modules, local file/SQLite storage, reference registration, comparison rules, platform/API contracts and known limits.
- [DFD.md](specs/DFD.md) — current reference, batch, camera/queue, inspection and review data flows.

The specifications were revised from source on 24 November 2026. They distinguish implemented behavior from unfulfilled baseline obligations. This documentation revision does not claim a new application test run or broad real-defect accuracy. Runtime behavior is defined by the current source; historical records below retain their original fixture/checkpoint/date scope. In particular, Step 3 failed readiness and later mounting-hole tuning concern different configurations.

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

## `audits/` — repair, recovery and acceptance records

Dated records from the AOI recovery and repair work, newest last.

- [RECOVERY_AUDIT.md](audits/RECOVERY_AUDIT.md) — AOI functional recovery audit.
- [ACCEPTANCE_RESULTS.md](audits/ACCEPTANCE_RESULTS.md) — functional recovery acceptance results.
- [PCB_REPAIR_AUDIT.md](audits/PCB_REPAIR_AUDIT.md) — PCB repair audit, 23 November 2026.
- [PCB_REPAIR_RESULTS.md](audits/PCB_REPAIR_RESULTS.md) — PCB repair results, 23 November 2026.
- [TARGETED_REPAIR_RESULTS.md](audits/TARGETED_REPAIR_RESULTS.md) — targeted AOI changes, 23 November 2026.
- [OPERATOR_FEEDBACK_FIXES.md](audits/OPERATOR_FEEDBACK_FIXES.md) — operator feedback fixes, 23 November 2026.
- [FINAL_STABILIZATION.md](audits/FINAL_STABILIZATION.md) — backend stabilization, 23 November 2026.

For the actual result contract (including `defect`, `DIFFERENT_BOARD`, component misalignment and blocked scoring), see [SRS Section 3](specs/SRS.md#3-terms-and-result-rules). For every FR/NFR implementation and existing test pointer, see [SRS traceability](specs/SRS.md#41-source-audited-traceability). Baseline acceptance cases remain planned obligations unless a scoped record explicitly demonstrates them.

## Evidence and fixtures

- `results/` — JSON and image evidence produced by the comparison, calibration and reliability runs.
- `diagnosis/` — CPU trace and offline diagnosis output; written by `pcb_landmarks.diagnose`.
- `samples/` — sample photographs referenced by the guides above.
