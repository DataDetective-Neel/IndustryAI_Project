# Data Flow Diagrams

- **Project:** Offline PCB Component Inspection — Task B, “Which Part Is Missing?”
- **Author:** Indraneel Chatterjee
- **Version:** 2.0 — 24 November 2026
- **Status:** Current source-audited flows; performance/acceptance remains provisional. No runtime changes or new test execution.

Related documents: [Software Requirements Specification](SRS.md) · [Software Design Document](SDD.md).

## 1. Notation and shared contract

Mermaid rectangles are external entities, rounded nodes are processes and cylinders are local stores. Arrows name transferred data; process numbers do not prescribe timing. Online installation/training/building occurs outside the runtime boundary. Runtime uses local assets/models and has no cloud inference dependency.

The operator confirms a reference's four ordered points and separate PCB outline, reviews/edits component rectangles and selects a golden configuration. Reference geometry is file-backed; golden components/configuration and platform records are in SQLite. The lab batch API accepts **1–15 photos**, one reference ID, component annotations, mode and sharpening flag. Imported queue chunks also accept 1–15 images; camera frames use the selected reference. Software line simulation and synthetic edits are labeled separately from real defect evidence.

Coordinates are decoded original reference pixels, with integer half-open rectangles. Non-normalized EXIF orientation is rejected. The inspection warp maps into the reference grid; local comparison can search bounded translations/rotation hypotheses without moving saved rectangles. Optional symmetric sharpening defaults off. Actual outcomes are `ok`, `defect`, `review`, `error`, `DIFFERENT_BOARD`; component states include `misaligned` and `not_evaluated`. See [SRS result contract](SRS.md#3-terms-and-result-rules).

## 2. Level 0 — context

```mermaid
flowchart LR
    O["Operator using local browser"]
    C["Browser camera"]
    S("0. Offline PCB inspection application")
    O -->|"reference, outline, points, rectangles and golden selection"| S
    O -->|"batch images, imported queue and mode/sharpening"| S
    O -->|"login, review decisions and line controls"| S
    C -->|"captured image frames for selected golden reference"| S
    S -->|"setup feedback, proposals and saved configurations"| O
    S -->|"per-photo findings, evidence, dashboard and review queue"| O
```

## 3. Level 1 — system decomposition

`web.py` orchestrates these flows. Platform operations apply their route-specific authentication/role checks; the local inspection lab is not described as a fully authenticated production API.

```mermaid
flowchart TB
    O["Operator / local browser camera"]
    P1("1.0 Upload and reference setup")
    P2("2.0 Batch / camera / queue intake")
    P3("3.0 Inspect each photo")
    P4("4.0 Results, platform and review")
    D1[("D1 UUID photo files and reference geometry JSON")]
    D2[("D2 Local weights, schema, catalog and provisional config")]
    D3[("D3 Batch JSON and evidence images")]
    D4[("D4 SQLite golden library, users, inspection summaries and decisions")]
    O -->|"reference, confirmed points/outline, named components"| P1
    D2 -->|"pose/component models and schema"| P1
    P1 -->|"decoded image, metadata and atomic geometry JSON"| D1
    P1 -->|"approved golden components and configuration"| D4
    P1 -->|"validation feedback, proposals and saved reference"| O
    O -->|"inspection images/frames, options and queue controls"| P2
    D1 -->|"reference pixels and confirmed geometry"| P2
    D4 -->|"selected approved reference/components"| P2
    D2 -->|"effective comparison configuration"| P2
    P2 -->|"one photo, captured reference/components and options"| P3
    D2 -->|"local model and supported-layout evidence"| P3
    P3 -->|"report and available alignment/component/difference images"| D3
    P3 -->|"inspection summary and review flags"| D4
    P3 -->|"per-photo result including failures"| P4
    P2 -->|"request errors or queue state"| P4
    O -->|"login, evidence selections and explicit review decision"| P4
    D3 -->|"saved reports and evidence"| P4
    D4 -->|"dashboard, golden library, roles and reviews"| P4
    P4 -->|"operator decision / account changes"| D4
    P4 -->|"results, paired crops, status and summaries"| O
```

D1/D3 default to `runs/web/photos` and `runs/web/batches`; D4 is `runs/web/aoi.db`. `PCB_WEB_STORAGE` changes that root. D2 contains checked-in configuration and prepared local assets; not every configuration is calibrated. Reference setup JSON is atomically replaced, SQLite changes are transactional, and batch reports/images are separate writes. These are implemented stores, not a proposed file-only database design.

## 4. Level 2 — decomposition of P3 inspection

```mermaid
flowchart TB
    P2("2.0 Intake outside P3")
    D2[("D2 Local models, layout catalog and config")]
    subgraph INSPECT["3.0 Per-photo inspection"]
        V("3.1 Decode record and initial layout evidence")
        L("3.2 Pose/manual landmarks and reference registration")
        A("3.3 Warp, independent verification and compatibility")
        C("3.4 Region coverage and raw texture checks")
        U("3.5 Optional symmetric unsharp mask")
        M("3.6 Bounded Sobel matching and defect rules")
        D("3.7 Component proposals and unique correspondence")
        R("3.8 Result assembly")
        V -->|"usable pixels and same/unknown catalog evidence"| L
        V -->|"decode error or positively different design"| R
        L -->|"pose/manual candidate or reciprocal SIFT fallback transform"| A
        L -->|"unusable landmark/feature evidence"| R
        A -->|"verified same-design aligned pixels, reference and mask"| C
        A -->|"unverified alignment or compatibility review"| R
        A -->|"reference/inspection detections transformed into reference grid"| D
        C -->|"raw grayscale crop pair, sharpening disabled"| M
        C -->|"grayscale pair, sharpening enabled"| U
        U -->|"symmetrically sharpened pair, unchanged stored boxes"| M
        C -->|"coverage, invalid/low-texture or explicit review evidence"| M
        D -->|"one-to-one assignments, conflicts and unavailable-detector evidence"| M
        M -->|"present/missing/misaligned/uncertain rows and measurements"| R
        A -->|"alignment state, overlays and verification provenance"| R
        V -->|"photo identity and captured options"| R
    end
    P2 -->|"one photo plus reference geometry/components and options"| V
    D2 -->|"pose model, thresholds and catalog"| V
    D2 -->|"pose inference settings"| L
    D2 -->|"existing component detector assets"| D
    D3[("D3 Report and available evidence")]
    D4[("D4 SQLite inspection/review summary")]
    P4("4.0 Result review outside P3")
    R -->|"per-photo report, overlay URLs and evidence"| D3
    R -->|"persisted inspection summary"| D4
    R -->|"per-photo result including errors"| P4
```

### 4.1 Process notes

- **3.1:** Corrupt uploads retain explicit photo errors. Supported catalog mismatch blocks scoring. Unknown catalog identity does not automatically imply wrong layout; active-reference verification may still succeed.
- **3.2–3.3:** Automatic mode can verify pose candidates against distributed on-board reciprocal SIFT matches, then fall back to reference-feature homography estimation when pose inference fails. Every third correspondence is withheld from fitting in the fallback path. Manual geometry can be refined when independent evidence improves it. The accepted warp has reference-grid pixels and full bilinear-support mask. Independent reprojection, coverage and stable-edge checks qualify registration; four fitted points alone are insufficient evidence.
- **3.4–3.5:** Full region coverage and raw texture checks precede verdicts. Enabled sharpening uses amount 0.5, Gaussian kernel 7×7, sigma 1 on both grayscale inputs; disabled goes directly to matching. Sharpening does not rescue low-texture crops or change stored rectangles.
- **3.6–3.7:** Bounded translation and −30° to +30° rotation hypotheses supplement Sobel normalized correlation. Low similarity requires corroborating absence evidence before `missing`; displacement/rotation can become `misaligned`. Existing detector assignments are corroborating/conflict evidence, not automatic presence or ground truth. Invalid/ambiguous/local unreliable regions remain reviewable.
- **3.8:** Any missing/misaligned part produces `defect` with review required, preserving uncertain rows. Uncertainty produces `review`; all present can yield `ok`. Different-board/error/blocked paths have no valid presence verdicts. Per-photo handling allows other batch photos to continue; malformed shared requests may fail before that loop. Operator decisions are stored separately from machine findings.

### 4.2 Boundary balancing and limits

| Parent flow | Child preservation |
| --- | --- |
| Operator setup and feedback | P1 receives reference geometry/components; D1 and D4 persist their separate portions; feedback returns to operator |
| Batch/camera/queue input | P2 provides a per-photo reference/options snapshot to 3.1 |
| Local model/configuration | D2 supplies schema/catalog/thresholds and existing detectors; no cloud entity is added |
| P3 result and evidence | 3.8 writes D3, persists the summary to D4 and returns the result to P4 |
| Review and account changes | P4 reads stored records and persists explicit authorized platform changes |

The diagrams describe source behavior, not a guarantee of broad-layout recognition, calibrated blur detection, real missing-part accuracy, complete model version provenance or production security. [SRS traceability](SRS.md#41-source-audited-traceability) names existing tests without claiming a fresh run. Historical evidence is indexed in [docs/README](../README.md).
