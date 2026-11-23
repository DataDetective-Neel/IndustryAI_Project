# Reference-based landmark reuse

Upload the known-good reference. YOLO still proposes its usual four ordered
landmarks; the reference editor stays editable even in Automatic mode. If YOLO
fails, use the same picker to mark four stable board details clockwise. They do
not need to be mounting holes or outline corners.

Inspect the cyan PCB surface outline. Correct it with **Mark PCB outline** if it
includes background or misses board details. This outline is independent of the
landmarks. Confirm with **Confirm reference setup**, keep/add component boxes in
original reference pixels, and upload inspection photos. Confirmation selects
Automatic mode. Inspection clicks are unnecessary when registration is verified.

## Implementation

- `GET/POST /api/references/{photo_id}` proposes an outline and persists confirmed
  points/outline under the immutable uploaded photo ID (`reference.json`).
- An app-local, bounded four-entry cache retains SIFT descriptors and the eroded
  surface mask by reference ID and outline. Changing the outline computes a new
  entry; uploading a replacement reference uses a new ID and clears the editor's
  confirmation, components, inspection points and projected landmarks.
- The model and its frozen configuration/catalog are unchanged. Existing manual
  alignment and CLI interfaces remain available. No uploads train a model.
- Automatic inspection of a confirmed reference first checks any YOLO landmark
  transform against on-board matches. If it fails, reciprocal SIFT matching and
  RANSAC estimate inspection-to-reference homography. Its inverse projects the
  saved reference points into inspection pixels. The existing `align_images`
  validates geometry, horizon and bilinear source support.
- Feature centers and descriptor support must stay inside the surface mask.
  Each inspection gets its own surface mask. No background matches are permitted
  to establish alignment. Outline/segmentation failure requests manual review.
- At least 35 unique reciprocal ratio matches are needed. Every third match is
  withheld from fitting. Verification requires 25 consistent matches, 45%
  geometric agreement, eight held-out inliers, 20% reference surface coverage,
  six separated grid cells, 85% board overlap, and agreement of stable edges in
  five grid regions. Reprojection tolerance is max(3 pixels, 0.003 image diagonal).
  These conservative, resolution-relative guards were not fitted to the supplied
  generated pair. They are provisional engineering guards, not calibrated error
  probabilities or a claim of universal PCB recognition.
- Only a verified alignment reaches component comparison. Registration failure
  means **Needs alignment review**, with a reason and **Switch to Manual**.
  Insufficient matching never means **Different board**; that verdict remains
  reserved for positive incompatible layout evidence from the existing checks.
- Reports include `alignment.source`, projected inspection points, verification
  statistics and rejected YOLO candidate reasons. Projected UI landmarks say
  **projected** and are never presented as model detections.

## Verification on 2026-11-21

Final checks: 68 backend tests, 4 frontend unit tests, 12 existing browser tests,
and the dedicated checkpoint-unavailable browser test passed. Production frontend
build and `git diff --check` passed.

Run backend tests from the repository root:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests
```

Run frontend tests from `frontend`:

```powershell
npm test
npm run test:browser
npm run test:reference
```

The dedicated browser test starts an isolated backend on port 8001 with a missing
checkpoint. It exercises real upload, saved-reference and inspection endpoints;
it does not stub registration. It marks the reference once, confirms its separate
outline, inspects normal/tilted photos without inspection clicks, rejects an
unrelated same-outline/same-background board and a blank image, opens manual
fallback, and replaces the reference to verify stale points are cleared.

| Case | Alignment path / result |
| --- | --- |
| Procedural PCB, same view and projective tilt; YOLO fails | Reference registration; projected points checked against the known transform |
| Valid YOLO inspection points | YOLO candidate, independently verified against reference features |
| Incorrect YOLO points | YOLO verification rejects; reference registration succeeds |
| Different procedural board, same outline/background | Manual alignment review; components skipped |
| Blank inspection | Manual alignment review; components skipped |
| Supplied WhatsApp generated pair | Reference registration regression passes with YOLO forced to fail |
| Test-split F: FBCC5, FDCC5 against FCCC5 | Reference registration passes with YOLO forced to fail |
| Test-split F: FCCB5 against FCCC5 (strong tilt) | Stable-detail verification rejects; components skipped |
| Test-split K: KBCC5, KCCB5, KDCC5 against KCCC5 | Reference registration passes with YOLO forced to fail |
| F against K / K against F, shared cloth and similar outline | Rejected; components skipped, no unsupported Different board claim |
| Existing blue-board ABCC5, ACDC5, ADCC5 and local simulated absence | Verified YOLO landmark candidates |
| Existing blue-board ACCB5 angle | YOLO candidate rejected; reference registration succeeds |
| Blue-board reference against positively recognized MBCC5 | Different board; components skipped before alignment |
| Blurred photograph | Alignment review; components skipped |

F and K are existing photographed PCB designs in the project's test split and
are absent from the known-board catalog. They were tested separately from the
user's generated pair, without threshold changes to make individual cases pass.
They are not a newly collected independent evaluator dataset. File-dependent
regressions skip explicitly when source photographs are unavailable.

## Remaining limitations

The automatic surface proposal currently targets colored solder masks with a
mostly convex silhouette. Pale/black boards, colored clutter, severe glare,
clipping and large perspective/parallax changes can require a corrected reference
outline, manual inspection alignment, or a new photograph. The editor's manual
outline tool uses four corners; automatic/API outlines can have 3–12 vertices.
A homography represents the PCB plane, not the tops of tall components. F's
strong-tilt view remains a verified rejection, not a successful automatic case.

A refresh resets the current editor selection; saved photo setups and reports
remain on disk under `runs/web`, but this change does not add a reference-library
browser. Matching is offline; a physical adapter-off run was not performed.
Missing-component classification remains the existing provisional comparator;
passing alignment is not evidence of validated defect-detection accuracy.
