# Research and solution selection

## 1. Problem definition

PCB automated optical inspection compares the assembled board with an expected configuration to identify visible assembly problems. This project addresses missing and displaced/rotated components using a known-good reference image. It does not inspect electrical connectivity or hidden solder joints.

Camera rotation, perspective and framing move every component in the image. Registration must therefore precede local comparison. Lighting changes affect color and edges; tall parts create parallax that a single planar homography cannot remove. Blur, reflections, clipping and limited texture can make an apparent defect ambiguous. Previously unseen reference designs need their own reference geometry and component inventory; an inspection of an entirely different design should be rejected rather than scored as many missing parts.

False-positive reduction is central: weak registration, an unmatched detector box, or a low similarity score alone should not establish a missing component.

## 2. Existing tools and investigation provenance

Historical investigation is evidenced by the recovered [Codex conversations](docs/ai_history/README.md), [Step 3 results](docs/steps/STEP3_RESULTS.md), [Step 4 record](docs/steps/STEP4.md), [Step 5 record](docs/steps/STEP5.md), and [reference registration guide](docs/guides/reference-registration.md). These records document implementation choices and failed attempts; they do not establish that every alternative below was experimentally benchmarked.

- **Ultralytics YOLO26 Pose:** the retained landmark implementation predicts an ordered set of four keypoints. The project uses a local fine-tuned checkpoint, not the official generic pose weights as if they already knew PCB mounting holes. Official model and pose-task documentation support the task/output formats, not this project's accuracy. [YOLO26](https://docs.ultralytics.com/models/yolo26/), [pose tasks](https://docs.ultralytics.com/tasks/pose/).
- **OpenCV registration:** the code uses four-point perspective transforms and a feature-registration path with SIFT matching, robust homography estimation and independent quality checks. OpenCV documents feature matching plus RANSAC homography; the project's additional masking and validation rules are application-specific. [Official tutorial](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html).
- **Reference-region comparison:** historical Step 5 work selected Sobel-gradient normalized correlation and local template search. Current classification adds edge/body loss, exposed substrate, color differences and component correspondence. This is reference-based inspection, not a trained end-to-end defect classifier. [OpenCV template matching](https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html).
- **Existing ParsaVictor component locator:** later development explicitly integrated an existing local YOLO26 component detector, tiled inference and duplicate suppression. Its local provenance is recorded in [configuration](configs/component_model.json), [adapted tiling code](pcb_landmarks/parsa_tiling.py) and [MIT attribution](pcb_landmarks/PARSA_LICENSE.txt). The recovered request names the local source repository; this document does not invent a public repository URL. It proposes inventory regions and supplies correspondence evidence; absence of a detection alone is not a defect decision. The existing checkpoint is bundled at `models/pcb-components-yolo26s.pt` (20,373,061 bytes, approximately 20 MB); it is not a missing external model file.
- **Open-AOI — unresolved identity:** no recovered project material establishes which exact project this name refers to or supplies a genuine repository URL. It is not listed as an implemented dependency or a verified historical comparison. An original project research link/export is required before adding an attribution.

The official documentation links were checked during final documentation preparation. That check is **supplementary current research**, not evidence that the same pages were read before implementation.

## 3. Approaches compared

“Historical” below means supported by project conversations/source records. “Supplementary” means a documentation-time comparison; it does not imply an experiment was run.

| Approach | Advantages | Limitations | Decision | Reason |
|---|---|---|---|---|
| Full component object detection | Automatic localization; reusable inventory proposals | Missed detections and domain shift; boxes alone cannot prove absence | Historical: retain existing locator as supporting evidence | Current system genuinely includes it, alongside reference comparison; no new detector is introduced here |
| Direct unaligned image comparison | Simple baseline | Camera movement changes every crop | Historical: not the general inspection path | Registration is required before component decisions; identical decoded images are a narrow special case |
| Four-landmark registration | Explicit correspondence and operator-correctable geometry | Four fit points alone provide no independent transform validation | Historical: retained | YOLO26 remains the landmark model, with quality checks and manual correction |
| Feature-based registration | Can register views when landmark detection fails | Repetition, backgrounds, low texture and clipping can produce unreliable matches | Historical: implemented SIFT-based reference reuse | Masks, distributed support and held-out checks reduce unsupported alignment |
| Reference component regions | Inspect known expected positions without training a defect classifier | Reference inventory and visibility must be correct | Historical: core inspection representation | User corrections and stored reference coordinates make results reviewable |
| Local template matching | Measures nearby displacement and bounded rotation hypotheses | Symmetric parts, lighting and parallax can remain ambiguous | Historical: implemented | Searches nearby before confusing a shifted component with absence |
| Structural similarity (SSIM) | Useful whole-image quality measure | Global score can hide small local defects | Historical records mention dataset validation; supplementary as a runtime alternative | Production `compare.py` uses gradient correlation, not SSIM as its primary defect score |
| Manual landmark fallback | Enables correction without new training | Operator effort and clicking error | Historical: retained | A reliable reference can be reused; no online weight update is claimed |

## 4. Model and algorithm selection

The YOLO26 landmark model preserves the four-keypoint contract and the existing training/inference tooling. [Initial training records](configs/training.json) and [fine-tuning configuration](configs/landmarks.json) describe different checkpoints and datasets; their metrics must not be conflated. The original pilot's high aggregate pose metrics did not guarantee usable four-landmark detections under the application's stricter confidence/geometry gates, as the [diagnosis](docs/diagnosis/README.md) documents.

In [alignment](pcb_landmarks/align.py), ordered inspection coordinates are transformed into reference coordinates and the image is warped with a validity mask. In [registration](pcb_landmarks/registration.py), reciprocal on-board SIFT evidence and held-out geometric/stable-region checks support reference reuse. A homography models a plane; large height differences, occlusion and lens distortion remain limitations. The project does not claim camera calibration merely because it uses a homography. [OpenCV perspective-transform API](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html).

In [comparison](pcb_landmarks/compare.py), grayscale Sobel gradient magnitudes are compared using `TM_CCOEFF_NORMED`. Low-texture or invalid regions remain uncertain. Optional symmetric mild unsharp filtering is off by default; historical tests changed scores without establishing a general benefit. Local template searches consider bounded offsets and rotation. Missing classification requires corroborating appearance/body/substrate evidence and appropriate registration and correspondence conditions; displaced matches should not automatically become missing findings. [Comparison thresholds](configs/comparison.json) remain explicitly provisional.

[Component correspondence](pcb_landmarks/correspondence.py) supplies matched boxes and displacement evidence. Detector confidence and correlation scores have different meanings and neither is a calibrated production defect probability. Failed registration or incompatible-board evidence must be handled before interpreting local component results.

These selections emphasize reuse, local execution and traceable decisions within a small-data project. No claim is made that all alternatives were compared in a controlled benchmark.

## 5. Dataset and data sources

The repository contains several distinct data records:

1. **Original landmark pilot:** [training metadata](configs/training.json) records 19 train, 5 validation and 8 test images, with train layouts A/B/H/M, validation E and test F/K. The source is the [MicroPCB Images dataset](https://www.kaggle.com/datasets/frettapper/micropcb-images), as attributed in [sample provenance](docs/samples/README.md). Labels use class `0=pcb`, a normalized bounding box, and four ordered `(x, y, visibility)` triples, defined by [dataset.yaml](PCB_Dataset_Pilot/dataset.yaml) and validated in [data.py](pcb_landmarks/data.py). These are recorded historical split sizes, not a fresh count of all later added assets.
2. **Later landmark fine-tuning:** [landmarks.json](configs/landmarks.json) records MBCC5/MCCB5 for fine-tuning, MCDC5 for validation and MDCC5 for testing. That tiny single-family adaptation cannot establish unseen-layout performance. Legacy calibrated mounting-hole support also limits broad generalization claims.
3. **Generated inspection fixtures:** the developer explicitly identified earlier example images as generated in the [generalization conversation](docs/ai_history/codex/2026-11-21T18-13-54-01a1fe22-7896-7a93-b109-cf154c72f037.md). Later supplied ELEGOO data uses a photographed golden reference and programmatically generated missing/misaligned derivatives, as recorded in the [stabilization audit](docs/audits/FINAL_STABILIZATION.md). Dataset prose names and component-map IDs can differ; the actual JSON map governs a run. Generated derivatives are controlled regression fixtures, not independent photographs of defective assemblies.

Historical local evaluation counts in conversations describe the dataset and code at that time. A held-out derivative of the same golden photograph is weaker evidence than a fresh physical board/capture/design holdout. Once results inform threshold choices, that set should no longer be described as an untouched final evaluation set. New references, novel layouts, capture conditions and physical defects require independent evaluation.

No new training, dataset collection or research benchmark was performed to write this document. Fresh executed checks and their limits belong in the [validation report](docs/VALIDATION_REPORT.md).

## 6. Final research conclusion

The selected design combines learned landmarks, verified geometric registration and reference-based component inspection. The existing component locator reduces inventory setup effort but does not replace reference comparison or operator review. This is a practical offline-capable demonstrator with explicit uncertainty, not evidence of universal PCB recognition or production-level accuracy. Physical defect data, independent board holdouts and threshold calibration remain the most useful next research steps.

## 7. References

- [Ultralytics YOLO26](https://docs.ultralytics.com/models/yolo26/) and [pose estimation](https://docs.ultralytics.com/tasks/pose/): model family and keypoint task contracts.
- [OpenCV feature matching and homography](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html): feature correspondences and robust transformation estimation.
- [OpenCV geometric transforms](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html): perspective transformation and image warping.
- [OpenCV template matching](https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html): local image matching methods.
- [MicroPCB Images](https://www.kaggle.com/datasets/frettapper/micropcb-images): original landmark-image attribution, also recorded locally.
- [Archify official repository](https://github.com/tt-a1i/archify): architecture documentation tool required for the submission; architecture generation is documented separately in [ARCHITECTURE.md](ARCHITECTURE.md), not presented as an inspection algorithm. Archify tooling for this submission must remain project-local and is not an application runtime dependency.
- [Project history and pending original evidence](docs/ai_history/README.md): provenance for historical decisions and research limits.
