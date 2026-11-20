# ENG-VIS-GALLERY-FIX — review b17-c Unit A, fixed and merged onto the production base

- Branch: `eng/vis-gallery`. Fixes tested at **c8d534bb06d4895fade89c62576cae2ece5e865a**. This file and its BUILD_STATE pointer are the only later commit.
- Merged (ordinary merges, no force): `origin/claude/w6-INTEG6` @ dde3ea62 (the production base), then `eng/gallery-complete` @ 20e8183 (for A4).
- Conflicts were additive, and both sides were kept: DECISION_LOG.md, BUILD_STATE.md, suite_final_segment.txt, ops/health.py (`motif-frame-` and `motif-backlog-`), test_w4_close5_rows.py.
- The first merge left conflict markers in BUILD_STATE.md. They are resolved, and the tree has none.
- `autonomy/autonomy_map.json` was regenerated (`python -m brambleloop.autonomy.map --write`). Only `generated_at` changed.
- No PR was opened. No Railway variable or secret was read. No paid provider was called.

## Findings

**A1 (fixed): the e2e failed 7 of 8 on the merged tree.**
- Root cause: ENG-VIS-IDENTITY's `candidate_gates.gate_status` demotes a PASS that carries a `verdict` key unless that verdict is PASS. `motif_reading` filed `verdict="match"`, so motif_fidelity read UNKNOWN on every frame, and the exception route read UNMEASURED.
- Fix: `motif_reading` now files `motif_verdict`. The identity rule is unchanged, and UNKNOWN still never counts as PASS.
- `test_vis_gallery_e2e` now passes 9 of 9: the original 8 plus the new test_9.

**A2 (fixed):**
- Added `assert rows` (test_vis_gallery_e2e), `assert cases` and `assert want` (test_vis_gallery_gates).
- Also added `assert CAMPAIGN_MIN_FRAMES > 0` in test_owner_gallery_complete. That test came in with eng/gallery-complete.

**A3 (fixed): D-OWNER-SPEND-ORDER, recorded as D-ENG-VIS-GALLERY-ADMISSION.**
- The FLUX `trigger` call is removed from `runtime/release.py` (the price chain).
- **The admission point is `listing.package`** (`listing_package_ops._admit_for_sale` → `image_production.admit_for_sale`). A release is admitted only when:
  - the recorded package is for this exact release;
  - every blocker on it is tagged `"image": true` (`release_gates.image_reasons`: listing set, image originality, search hero, sample photo, the gallery_images/video_in_gallery standards, and `certified_frames`);
  - the lifecycle is not REJECTED, RETIRED or ROLLED_BACK.
  - A reason that cannot be attributed counts as non-image, so it never admits.
- Every stage of a paid run re-checks admission first. This covers the FLUX route always, and the campaign route whenever its generator is paid: that route was found spending the same way.
- A release that is not admitted goes to `waiting_for_sale_admission`. It makes 0 calls and spends nothing, and its unused outfit reservation is released. Re-admission resumes it, once per wait.
- Controlled runs and EXPERIMENTs keep their own owner authorisation.
- Test: `test_vis_gallery_e2e::test_9`. With `image_generation` activated (test_double) and a paid generator, a certified release with failing non-image gates gets:
  - no FLUX job from assets.build or listing.package;
  - a parked, unspent run even when a FLUX job is delivered by hand;
  - 0 generator calls;
  - its outfit reservation released.
- The gallery fixture's admission in `run_gallery` is a labelled `test_double`.
- In test_w4_ownerimg, two gate tests now assert both layers: a run that is not admitted parks, and an admitted run still hits the closed gate.

**A4 (fixed by merging eng/gallery-complete):**
- `etsy_ops.certified_frames` refuses fewer than `CAMPAIGN_MIN_FRAMES` frames ("gallery incomplete").
- `test_visual_factory_e2e::test_b0`: a 6-frame certificate leaves the package BLOCKED and nothing reaches Etsy.
- Consequence: the 6-frame photography set in `test_motif_backlog`'s handoff e2e is now correctly BLOCKED as incomplete. The test names that one image blocker explicitly and still requires every other image gate to be clear.

## Invariants
- Laura laura-r2-a42aeac7: no canonical asset, `CURRENT_REFERENCE_HASHES` or `IDENTITY_ID` is in the diff.
- A gallery needs at least 7 certified frames: enforced on the plan (`campaign_standard`) and on the certificate (`certified_frames`).
- Stubs are labelled `test_double`.
- UNKNOWN never counts as PASS.

## Suites
Command: `PY=python3 JOBS=3 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`. Run 20261120T134440Z-206, at c8d534bb, on a clean tree.

**TOTAL PASSING: 371; suites failing: 0** (24 suites)
- The review's 13 A suites: vis_gallery_e2e 9/9, vis_gallery_gates 14/14, visual_campaign_standard, visual_factory_e2e, visual_pipeline_evidence, v2_gallery_consistency, v6_gallery_e2e, w4_close5_rows, w4_f852_amend, w4_ownerimg 35/35, w4_readback_evidence, model_spend_paths, cost_governance_wave2.
- Required: test_vacuity 8/8, test_w4_resume_runner 40/40.
- Added: owner_gallery_complete, v2_capability_redrive, executor, opus2_listing_package, codex_a9_event_release, codex_a9_sweep_isolation, codex_a9_event_scope, eng_vis_flux, motif_backlog 26/26.

## Honest status / owner-visible consequence
- Production still has 0 generated galleries.
- Launch-0 releases carry non-image FIRST_CUSTOMER blockers today:
  - `gauge_and_size_claims`: no physical sample;
  - `etsy_remote_state`: UNVERIFIABLE.
- Under the strict rule they are not admitted for paid images until those pass.
- Treating `etsy_remote_state` as a store-wide integration check instead of a listing gate would be a decision for the owner or main. It was not taken here.
