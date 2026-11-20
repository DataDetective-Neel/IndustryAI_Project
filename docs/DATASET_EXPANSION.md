# PCB landmark collection and split plan

Checkpoint 1: collection plan only. No incoming reviewed photos were found in
the workspace on this pass. Do not manufacture an expanded run or change the
pilot to make a new result appear comparable. Step 4 remains paused.

## Current audit

| Role | Layout IDs | Images | Known capture sessions |
|---|---|---:|---|
| Pilot train | A:5, B:5, H:5, M:4 | 19 | Unknown for all 19 |
| Development | E:5 | 5 | Unknown for all 5 |
| Historical test | F:4, K:4 | 8 | Unknown for all 8 |

Source layout IDs are micropcb_A through micropcb_M as present in the manifest;
letters are not camera-session identifiers. The manifest has no session field
or verified acquisition timestamps. Do not infer sessions from filename letters
or file modification times. Treat each source layout's existing views as one
conservative acquisition group until provenance establishes otherwise.

The existing audit passes all 32 image/label pairs, dimensions, numeric pose
labels, visibility and layout/family separation, with no cross-split exact file
or decoded-image duplicates. All 128 points have visibility 2. Session and
perceptual near-duplicate checks are not automated; passing this audit does not
certify those properties. No validator change is justified by an incoming
failure example because no incoming batch is available. Step 2's dataset README,
YAML and manifest plus pcb_landmarks/data.py are the available dataset workflow;
no separate collection/import tooling was found.

Training covers long development boards A/B and Raspberry-style H/M. E's dark
BeagleBone-style PCB, mounting holes beside connector/header structures and
distinct hole spacing are absent from training. The five E views supply only
modest viewpoint variation. Broad in-plane rotations, perspective, scale,
directional glare, low light, blur, clutter, partial boards and obscured holes
are missing or insufficiently documented. There is no measured session-level
coverage. The prior CPU trace shows 169–452 pixel ordered point errors on E;
lowering confidence accepts wrong points, so more bursts of the same easy view
alone do not address the observed gap.

## Capture and annotation guide

1. Assign layout, family, physical board instance and capture session IDs before
   photography. A session is one continuous acquisition setup; record changes
   in camera, lighting, background or acquisition date as new sessions. Keep
   short bursts and transformed copies linked to a common acquisition group.
2. Prioritize E-like boards with mounting holes adjacent to connectors/headers,
   dark substrate and different hole spacings. Capture independent sessions,
   full-board sharp views and intentional changes in rotation, distance,
   perspective, lighting and background. Include hole-like connectors as hard
   distractors. Record conditions rather than claiming an unmeasured coverage
   target. Add blur, glare, cropped-board and occlusion examples as separately
   identified rejection challenges; do not inflate positive counts with them.
3. For each layout/side, choose exactly four stable physical mounting-hole
   centers spread over the board plane that remain when inspected components
   are removed. Save a canonical orientation sketch/photo identifying each hole.
   Do not substitute connector centers, screw highlights or removable parts.
   If four stable identifiable holes cannot be chosen, quarantine that layout
   for a schema decision rather than changing this schema silently.
4. Preserve class 0=`pcb`, kpt_shape=[4,3], and order:
   upper_left_mount, upper_right_mount, lower_right_mount, lower_left_mount.
   These names refer to the canonical board orientation, not screen positions
   after rotation. Label one board box as normalized cx,cy,w,h followed by four
   normalized x,y,visibility triples (17 numbers including class). Decode and
   normalize EXIF orientation before annotation; use the actual stored raster
   dimensions. Keep flipping disabled.
5. Use visibility 2 for a clearly visible center. Use 1 for an occluded point
   only when its physical location is defensibly known from independent evidence
   and separately reviewed; record that evidence. For an unknown/unlabelable or
   outside-frame point use 0 and x=y=0. Never guess an obscured center from the
   candidate model. Ambiguous identities require a retake or quarantine; preserve
   any rejection challenge separately. Four-point positive acceptance requires
   all four usable landmarks; partially labeled examples are not positive
   successes. Review visibility-1 localization separately from visible-only error.
6. Render label overlays, zoom into each hole at original resolution, and compare
   every view with the canonical sketch. Verify indices 0,1,2,3 follow the same
   physical holes clockwise in image coordinates, including rotated views.
   Require a second reviewer for all incoming hole placements and all projected
   labels. Record reviewer, review date, corrections and accepted/quarantined
   status. Never move labels to fit model predictions.

## Intake manifest and split lock

Keep the pilot manifest and all original weights/reports/configuration unchanged.
Create an expanded dataset only after review, under a new local version directory
(for example PCB_Dataset_Expanded_v1, ignored locally before copying raw photos).
Copy the existing YAML schema and image/label directory structure. Retain all
existing provenance and manifest columns; append these intake columns:

`capture_session_id,board_instance_id,acquisition_group_id,conditions,review_status,reviewer,review_date,publication_clearance`

Use `unknown` for missing historical session provenance. Store burst/near-duplicate
membership in acquisition_group_id; related sessions/groups must share a split.
Keep unknown historical groups together by layout, never pretend they establish
independent-session generalization. Source image paths are dataset-relative;
keep private operator identities and unpublished acquisition metadata local.

| Allocation | Policy |
|---|---|
| Train | Original A/B/H/M plus reviewed new E-like layouts/families distinct from development and final groups |
| Development | Keep the same five E images for paired pilot/candidate comparison; any new development layouts and sessions are assigned before training |
| Historical F/K | Preserve baseline only; exclude from new model/threshold selection and fresh-final claims |
| Fresh final | Reserve a new layout and acquisition family outside A/B/H/M/E/F/K before model work; all instances, sessions, bursts and derivatives stay here |

Do not move new E-layout photos into training while claiming layout-independent E
development accuracy. Similar layouts/families belong together. If new evidence
links groups assigned to different splits, stop intake and resolve the split
before training; record the revision. Reserve final metadata with a custodian
and keep final photos/labels outside training/development YAML access until the
candidate and confidence policy are frozen. No fresh final layout has arrived
or been assigned an actual ID yet; this table is a plan, not a claimed dataset.

For each incoming batch, inspect contact sheets across all proposed splits for
same boards, bursts, crops and lighting variants; compare suspected duplicates
at full resolution and merge their acquisition groups. Then run the existing
checks against the versioned YAML:

```powershell
.\.venv\Scripts\python.exe -m pcb_landmarks.data --data PCB_Dataset_Expanded_v1/dataset.yaml --previews runs/expanded-v1/audit --output runs/expanded-v1/audit.json
```

Run this once a complete versioned dataset and its reserved test directory exist;
the current audit requires nonempty train/val/test directories. A custodian can
audit final split integrity before release without sharing model performance.
Quarantined/unreviewed images stay outside configured directories and manifest.
The numeric checker does not enforce the added session/review columns: manually
verify those columns, group exclusivity, clearance and review sign-off before
declaring the version ready. Save that sign-off with the local version. Do not
add validator behavior without a reproducible demonstrated missed problem.

## Next run gate

After intake approval, snapshot the expanded version, content hashes, group/split
assignments and schema. Use a separate run name and candidate configuration;
retain the epoch-59 pilot and frozen .95/.99 policy. Compare both models on the
same five E development images using the same device, size, matching definition
and localization tolerance. Report ordered per-hole pixel errors, matched-image
denominators, correctly accepted, inaccurately accepted and rejected counts.
Select checkpoint/thresholds on development only. Freeze weights hash, schema,
inference size and thresholds before opening fresh-final images. Repeat blocked
network CPU inference. Publish only cleared samples and sanitized summaries.
Checkpoint 2 requires an actually completed expanded run; readiness remains
pending if a fresh final layout is unavailable.

Still needed: reviewed E-like training layouts with connector-adjacent holes;
independent sessions and the listed capture variations; reviewed visibility and
rejection cases; one untouched final layout/family. No incoming review, expanded
dataset or new training was performed during this documentation checkpoint.
