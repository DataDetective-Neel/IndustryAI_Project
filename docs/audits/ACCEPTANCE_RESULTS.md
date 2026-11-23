# AOI functional recovery acceptance results

Run date: 2026-11-23. These results describe automated evidence, not industrial
accuracy certification. Real production-line validation remains required.

| Test | Result | Evidence |
| --- | --- | --- |
| A — automatic boxes | PASS | Browser test uploads a golden PCB and observes generated `UNKNOWN` proposals before manual drawing. |
| B — corrected box persists | PASS | Browser/API tests edit annotations, save the golden configuration, and restore the same regions. |
| C — same golden image | PASS | Comparison and browser regression tests return no false missing result for identical reference/inspection content. |
| D — known missing part | PASS, synthetic only | Controlled fixture erasure produces `missing` through the real registration/comparison pipeline. No labelled real-photo missing-part sample was available, so real accuracy is not claimed. |
| E — known misalignment | PASS, synthetic only | Controlled translated component evidence produces `misaligned`. No labelled real-photo misalignment sample was available. |
| F — live multi-image run | PASS | Browser test imports multiple images and waits for the real simulator to process every file. |
| G — dismiss alarm | PASS | A real comparison batch creates a review alarm; the authenticated decision endpoint records `false_alarm`, removes it from pending review, and updates dashboard history. |
| H — confirm defect | PASS | A second alarm records `confirmed_reject`; dashboard rejected count updates and a duplicate decision is rejected with HTTP 409. |
| I — repeated runs | PASS | Fifteen-photo API batch plus repeated production-browser workflows complete with overlays and no application crash. |
| J — invalid/incompatible input | PASS | Invalid bytes, oversize/EXIF-invalid uploads, bad geometry, and incompatible boards return structured error/review responses without crashing. |

## Commands used

```powershell
Set-Location A:\IndustryAI_Project
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Set-Location frontend
npm test -- --run
npm run build
npm run test:browser
```

The browser suite covers production build and Vite paths. Detailed algorithm
limitations and board-specific evidence remain in `DEMO_RELIABILITY.md`,
`BOARD_COMPATIBILITY.md`, and `MOUNT_CALIBRATION.md`.
