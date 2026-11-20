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
