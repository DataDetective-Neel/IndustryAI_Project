# Human–AI collaboration

I used AI to help turn an offline PCB inspection idea into an implementation: architecture and dataset planning, Python and React implementation, research, debugging, test planning, and documentation. I supplied requirements, tried the application, reported failures, and narrowed the scope when a proposed fix did not address the real problem. The account below is grounded in the recovered project conversations and current source. It does not imply that every historical AI claim has been independently reproduced in this final documentation pass.

The available [conversation index](docs/ai_history/README.md) contains genuine local Codex messages and original pasted requests. Earlier ChatGPT history is still pending. These decisions are first-person descriptions of documented choices, not invented quotations.

## Decision 1: Align the board before judging its components

**AI suggested:** Implement an alignment module that accepts ordered pixel coordinates, converts dataset labels using decoded image dimensions, and returns a warp and validity mask. The Step 4 conversation records this implementation proposal.

**I decided:** Keep YOLO26 Pose for the four physical landmarks and use geometric registration before comparing components. I explicitly asked to preserve landmark identities through rotation and reject unusable geometry.

**Why:** Finding four reference points establishes geometry; it does not establish whether a resistor or chip is present. Comparing corresponding component regions requires the inspection image to be in reference coordinates first.

**Evidence:** [Step 4/5 conversation](docs/ai_history/codex/2026-11-20T17-36-00-01a1f8d9-69c5-77d0-9bdd-f3eb631afb05.md), [alignment implementation](pcb_landmarks/align.py), [landmark inference](pcb_landmarks/infer.py), and [alignment tests](tests/test_align.py). Current registration also includes a verified feature-based path; landmark detection alone is not the sole alignment gate.

## Decision 2: Separate component localization from defect classification

**AI suggested:** Use Sobel-gradient normalized correlation on aligned reference regions, enforce valid coverage, and retain review results for unreliable regions. Later implementation discussions added detector correspondence as supporting evidence.

**I decided:** Require comparison with a known-good reference rather than treating a detector's missing box as sufficient proof of a missing physical part. Later, I explicitly requested reuse of the existing ParsaVictor component detector for automatic localization; this was a change from the earlier manually configured region workflow.

**Why:** A component locator can miss an intact part. Reference comparison, registration quality, nearby matching, and absence evidence provide different information. Keeping those responsibilities separate makes the decision inspectable.

**Evidence:** [Step 5 discussion](docs/ai_history/codex/2026-11-20T17-36-00-01a1f8d9-69c5-77d0-9bdd-f3eb631afb05.md), [November 23 detector integration request](docs/ai_history/codex/2026-11-23T11-26-07-01a206f9-da9f-7f92-8c46-d9478b16e9f6.md), [comparison](pcb_landmarks/compare.py), [correspondence](pcb_landmarks/correspondence.py), and [component model configuration](configs/component_model.json). The current application genuinely contains this component detector; describing it as never used would misrepresent the project.

## Decision 3: Keep manual reference correction and reuse the reference

**AI suggested:** Match each inspection to the supplied reference using distributed visual features and geometric verification when the specialized mounting-hole detector cannot generalize.

**I decided:** Ask for reference-based landmark reuse: let me confirm or correct the reference points once, retain them in original-image coordinates, and automatically register subsequent views when the visual evidence supports it.

**Why:** Repeated manual placement introduces error and slows inspection. Confirmed reference geometry is useful without pretending that manual corrections retrain YOLO26. Feature registration still needs overlap and sufficient texture.

**Evidence:** Chat Excerpt #1; [reference registration discussion](docs/ai_history/codex/2026-11-21T18-13-54-01a1fe22-7896-7a93-b109-cf154c72f037.md), [registration code](pcb_landmarks/registration.py), and [reuse tests](tests/test_reference_reuse.py).

## Decision 4: Treat generalization as an open requirement

**AI suggested:** Following my concern about overfitting, AI identified the tiny fine-tuning set and stored calibrated layouts as insufficient evidence of unseen-board performance, and proposed pairwise reference registration.

**I decided:** Reject fixes based only on my generated test images or adding each failed board to a catalog. I wanted an evaluator to be able to supply a new reference PCB and inspect matching boards against it.

**Why:** New-reference support and comparing entirely different designs are different requirements. A good warp does not prove design identity, and success on generated derivatives does not prove physical-world generalization.

**Evidence:** Chat Excerpt #1; [fine-tuning configuration](configs/landmarks.json), [historical dataset/diagnosis record](docs/diagnosis/README.md), and [reference reuse tests](tests/test_reference_reuse.py). Legacy calibrated board data still exists in the source/configuration; I cannot claim that every historical specialization has been removed or that universal PCB compatibility is established.

## Decision 5: Challenge the identical-image fix

**AI suggested:** Bypass landmark warping when decoded images are pixel-for-pixel identical. It initially described the successful duplicate-image result too broadly.

**I decided:** Question whether that change made the system reliable or only forced my example to pass. I then required independent alignment checks and conservative handling of uncertain results.

**Why:** An identity-image shortcut can avoid distortion from inconsistent clicks, but it does not validate different-photo inspection. Low similarity after a bad warp must not become a confident missing decision.

**Evidence:** Chat Excerpt #2; [original failure and correction](docs/ai_history/codex/2026-11-20T17-36-00-01a1f8d9-69c5-77d0-9bdd-f3eb631afb05.md), [subsequent reliability work](docs/guides/DEMO_RELIABILITY.md), and [operator regressions](tests/test_operator_regressions.py).

## Decision 6: Distinguish different boards from uncertain alignment

**AI suggested:** Add a board-level check using stable layout evidence across several regions and test the wrong-board pair alongside same-design controls and a localized removal.

**I decided:** Explicitly request `DIFFERENT_BOARD` only when layout mismatch is supported, with component scoring skipped. Blur, cropping, or ambiguous alignment should remain `REVIEW`.

**Why:** Four points can warp unrelated boards onto each other. Conversely, one missing component should not make the entire design incompatible.

**Evidence:** [November 21 compatibility request and response](docs/ai_history/codex/2026-11-21T10-12-09-01a1fc69-6bbe-74c2-b211-2068d7e80477.md), [compatibility implementation](pcb_landmarks/compatibility.py), and [board compatibility tests](tests/test_board_compatibility.py). Historical catalog-based checks and current reference registration should not be confused with a universal board recognizer.

## Decision 7: Improve explicit missing decisions without relabeling uncertainty

**AI suggested:** Combine component absence, exposed-board evidence, and appearance change after registration; search nearby before declaring a component missing, and keep review when evidence conflicts.

**I decided:** Authorize a narrow rule-based change to the scoring layer and ask that everything else stay unchanged. I wanted fewer unexplained review cases, but not an automatic conversion of every review into a defect.

**Why:** Empty solder pads can retain strong edges. Missing-body, substrate, color, detector and local-template evidence need to be considered together. Detection confidence is not a calibrated probability that a defect exists.

**Evidence:** Chat Excerpt #3; [rule discussion](docs/ai_history/codex/2026-11-23T22-30-05-01a20959-b9a1-7c31-b871-d05e54460e25.md), [implementation follow-up](docs/ai_history/codex/2026-11-24T13-59-30-01a20959-b9a1-7c31-b871-d05e54460e25_01a20cac-a2c8-72a1-b30c-cf9bd9cce164.md), and [comparison tests](tests/test_compare.py). Historical small-dataset figures in those chats are not production accuracy claims or fresh results from this documentation task.

## Decision 8: Preserve the frontend while stabilizing inspection

**AI suggested:** In the final narrow patch, change missing-component rules at the scoring layer and compare results against the baseline while leaving the rest of the application unchanged.

**I decided:** Preserve the existing frontend design and avoid another architecture redesign or new training cycle during stabilization. Earlier UI work remains part of the history, but the later backend work had a deliberately smaller scope.

**Why:** The remaining practical problem was trustworthy inspection. Reworking an already usable interface would introduce additional regression risk without resolving registration or missing-part classification.

**Evidence:** [original stabilization request, section 3](docs/ai_history/codex/2026-11-23T16-29-55-01a2080f-fe3c-7ae1-ab2c-cb4b29b197ca-attachment-1.md), [narrow scoring patch conversation](docs/ai_history/codex/2026-11-24T13-59-30-01a20959-b9a1-7c31-b871-d05e54460e25_01a20cac-a2c8-72a1-b30c-cf9bd9cce164.md), and [stabilization report](docs/audits/FINAL_STABILIZATION.md).

## Chat Excerpt #1 — Generalization and reference reuse

These are verbatim messages/fragments from the [November 21 conversation](docs/ai_history/codex/2026-11-21T18-13-54-01a1fe22-7896-7a93-b109-cf154c72f037.md). The developer's complete message and the complete AI response are preserved there.

> Me: When I fed this to boards, first of all the automatic landmark detector was not able to detect the reference points. And the second problem that came is it showed needs review, needs alignment review. So are we just making it learn from the given test cases only? And are we overfitting the model to just these PCBs? Because when the evaluator is going to test, he is not going to test from our images. It's going to bring his own images. So we can't just make it learn from all those test images, okay? These are generated by me, the previous test cases one. So I don't want you to just hard code or make it overfit for those only. I want it to be generalized
>
> AI: I’ll trace how landmark detection and alignment review work, reproduce the failure with these images, and check for assumptions tied to the earlier boards. Any fix needs to work from image geometry and matching evidence, without memorizing these examples.

## Chat Excerpt #2 — Questioning a successful example

Verbatim messages and a labeled response fragment from the [November 20 conversation](docs/ai_history/codex/2026-11-20T17-36-00-01a1f8d9-69c5-77d0-9bdd-f3eb631afb05.md).

> Me: its not working properly even when the same image is fed to the model as refernce and inspection, its marking evertying as missing T_T

After the AI implemented a duplicate-image shortcut, I challenged it:

> Me: What the hell, did you just make it do that or is it really working? Or you are just making it to do forcefully?
>
> AI: **I added a special case, and I overstated what it proved.**

The AI response continued:

> The underlying problem remains: inaccurate alignment can lower similarity, and the app currently interprets that as Missing without independently proving the alignment is accurate. Those cases should be routed to **Needs review**.

## Chat Excerpt #3 — A constrained rule-based change

Verbatim fragments from the [rule discussion](docs/ai_history/codex/2026-11-23T22-30-05-01a20959-b9a1-7c31-b871-d05e54460e25.md), followed by the [next session](docs/ai_history/codex/2026-11-24T13-59-30-01a20959-b9a1-7c31-b871-d05e54460e25_01a20cac-a2c8-72a1-b30c-cf9bd9cce164.md). The session boundary is intentional.

> Me: I am happy with most of the result except the missing identification one, can we somehow increase its accuracy by using some rule based approach
>
> AI: If all three agree, classify it as **missing**. If the evidence conflicts, retain **needs review**. Before declaring it missing, search nearby for a displaced component so a misalignment doesn’t become a false missing alarm.

In the following session:

> Me: go ahead, but dont change anything else
>
> AI: I’ll add the missing-component rules at the scoring layer, keep the rest of the app unchanged, and compare missing detection and false alarms on the development and held-out sets.

## Evidence pending

The recovered Codex records support the eight decisions above. They do not establish that all earlier project chats have been recovered. Original project-only ChatGPT exports or genuine share links, including the earliest problem/research and image-generation discussion, must still be supplied. Open-AOI's intended identity and any historical investigation of it also remain unverified. No missing AI response, date, experiment, or share link has been reconstructed.

## Reflection

AI accelerated code scaffolding, diagnosis, documentation and regression-test ideas. Manual use exposed failures that a passing test suite had not settled: inaccurate landmarks, misleading missing decisions and a narrow identity-image workaround. I retained control by challenging those conclusions, specifying the meaning of incompatible versus uncertain results, and constraining later patches. Future work should use independently captured physical defect photographs, board-level holdouts and documented threshold calibration. The existing generated fixtures are useful regression evidence, but they cannot establish production performance.
