# AOI functional recovery audit

Date: 2026-11-22

## Verified baseline

- React/Vite calls FastAPI directly through `/api/*`; Vite proxies development requests to port 8000.
- `pcb_landmarks.web` owns upload, reference setup, landmark inference, registration, comparison, persistence, review, and simulation routes.
- Existing OpenCV registration and conservative component comparison are exercised by 74 passing backend tests.
- Existing YOLO landmark inference remains optional; saved-reference SIFT registration can remove repeated manual landmark entry.

## Acceptance failures and root causes

1. Automatic component detection is absent. `/api/photos/{id}/regions` only returns `configs/components-ECCC5.json` when an uploaded raster exactly equals one bundled image. Every other board returns 404.
2. Inspection Lab is still the original 950-line vertically stacked editor. New navigation wraps it but does not change its workflow.
3. Live Inspection only accepts a backend directory string. Browser multi-file and folder import are not connected.
4. Browser regression tests stop at the new sign-in page. The suite waits 120 seconds for hidden legacy controls and never tests authenticated pages.
5. Frontend has no error boundary. Any render exception can blank the whole application.
6. Simulator errors are reduced to a string in state. No structured backend log identifies the failing file or stack.
7. Comparison deliberately withholds `MISSING` without verified absence evidence. Current code cannot truthfully pass missing-component acceptance tests.
8. Current dataset contains board/layout variants and synthetic erasures, but no verified real missing or misaligned component ground truth. Accuracy claims are not supported.

## Recovery boundaries

- Keep conservative uncertainty outcomes.
- Mark automatically proposed regions `UNKNOWN` until operator approval.
- Do not use dataset labels as inspection predictions.
- Do not edit `dataset_generation/`.
- Replace each decorative surface only when an end-to-end API path and test exist.
