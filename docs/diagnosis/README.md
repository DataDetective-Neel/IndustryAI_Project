# PCB landmark failure investigation — CPU baseline

Baseline report, weights and configs/landmarks.json are unchanged. Reproduce:
`python -m pcb_landmarks.diagnose` from the repository root using the project venv.
The trace JSON contains every returned candidate's class, box score, four named
pixel coordinates/confidences, ordered label errors and best permutation.
Images remain local under runs/diagnosis/overlays; no raw images are committed.

| Image | Top PCB score | First rejection | Ordered landmark errors, pixels |
|---|---:|---|---|
| EBCC5 | .8820 | no_confident_board | 320.09,451.86,220.11,256.44 |
| ECCB5 | .9229 | no_confident_board | 169.26,258.29,211.34,245.71 |
| ECCC5 | .9204 | no_confident_board | 229.75,306.40,251.68,250.23 |
| ECDC5 | .9181 | no_confident_board | 206.02,275.86,246.49,261.00 |
| EDCC5 | .9118 | no_confident_board | 239.40,174.39,198.40,218.57 |

All five have candidates, class 0 (pcb). All top scores are below .95. The CLI
therefore returns failure with empty landmarks before testing point confidence.
At the .001 diagnostic cutoff multiple low-score proposals can also appear;
they are not silently treated as accepted boards. Normal CLI behavior is intact.

## Evidence-based disposition

All five locally inspected overlays show misplaced points, not correctly located
low-confidence holes. The best of all 24 identity permutations is the original
order for every top candidate: swapping identities cannot repair these errors.
Direct JPEG-path prediction and the application's decoded RGB PIL prediction
agree within .01 in returned keypoint values on every image. The installed
Ultralytics 8.4.39 returns full-image pixel coordinates and visibility scores;
we do not renormalize them. Raw diagnostic candidates are post-Ultralytics
letterboxing/postprocessing and before application filtering, not neural logits.
No preprocessing or coordinate conversion defect was demonstrated.

The immediate rejection cause is the .95 board gate; the substantive readiness
failure is inaccurate, low-confidence learned pose on unseen layout E. This is
not evidence of a particular training-library defect. The ultimate learning
failure has not been isolated beyond the inadequate pilot support/generalization.
Training has only 19 images across four layouts A/B/H/M; E's black BeagleBone-style
board and mounting-hole/connector arrangement are absent from training. The five E
views vary modestly and do not cover broad rotations, glare or occluded holes.
Existing manually placed/projected labels need independent close-up review of
hole centers, especially near connectors; no specific incorrect label was proven,
so no labels were changed speculatively. Collect independently annotated E-like
boards for development/training, wider pose/lighting/scale variation and hard
connector-versus-hole examples, plus visibility-labeled occlusion/cropping cases.
Do not relabel targets toward these model predictions. Retrain only once reviewed
new examples or confirmed label corrections address these measured errors.

Evaluation's all_four_usable counts assess(status=ok), including geometry and all
confidence gates. Failed detection is its complement, including threshold
rejections even when boxes exist. Ground-truth localization is separately matched
at .001 confidence and IoU .5. CLI raw prediction uses the operating board cutoff;
evaluation/diagnostics retain lower-score candidates. Both assess the same frozen
cutoffs, image size and identities; standard AP uses a separate metric curve.
Historical evaluation used GPU while this trace uses CPU; small pixel differences
from the historical report are retained rather than replacing baseline results.

| Development policy (board / point) | Accepted | Accurate | Inaccurate accepted | Rejected |
|---|---:|---:|---:|---:|
| Baseline .95 / .99 | 0 | 0 | 0 | 5 |
| Diagnostic .5 / .05 | 1 | 0 | 1 | 4 |
| Diagnostic .5 / .01 | 5 | 0 | 5 | 0 |

Accuracy remains all four errors within 1% of image diagonal. The full 45-policy
comparison is in cpu_trace.json. Threshold relaxation recovers zero valid results.
There is no verified inference correction that makes this checkpoint usable.
Baseline weights, annotations, original report and frozen configuration remain
unchanged; no retraining was performed.

Fresh final evaluation: unavailable. Reserve newly collected layouts outside
A/B/H/M/E/F/K and acquisition families; never move their images into development.
Freeze a candidate checkpoint hash, schema, size and thresholds before opening
that set. Final readiness is pending. F/K remain historical baseline only and
were not run in this investigation.

Verification: ten unit tests pass. A fresh CPU process repeated ECCC5 inference
with DNS/socket connections blocked: zero attempts, explicit failure, no landmarks.
The offline record is offline.json. Step 4 remains paused; no homography,
alignment overlay or component comparison is implemented. Diagnostic overlays
are local only.
