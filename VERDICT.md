# Review b17-c: vis-gallery, vis-identity, wardrobe-scenes onto claude/w6-INTEG6 @ dde3ea62

Reviewed 2026-11-20 (UTC). No paid provider was called, no Railway variable or secret was read,
and no PR was opened.

| unit | head | verdict |
|---|---|---|
| (A) eng/vis-gallery | 2c253c07 | **BLOCK** |
| (B) eng/vis-identity | 4965dda2 | **SHIP** |
| (C) eng/wardrobe-scenes | b974a6d1 | **SHIP** (with a follow-up, C1) |

## Merges onto dde3ea62

dde3ea62 is not an ancestor of any of the three heads, so every unit needed a real merge.
All conflicts were additive. I resolved them as the union of both sides, and the JSON
timestamp kept the base (HEAD) side.

- **A:** BUILD_STATE.md, DECISION_LOG.md, scripts/suite_final_segment.txt, ops/health.py
  (scratch prefix lists: `motif-backlog-` and `motif-frame-`, keep both) and
  tests/test_w4_close5_rows.py (dict entries for motif_backlog and candidate_gates, keep both).
- **B:** BUILD_STATE.md, DECISION_LOG.md, suite_final_segment.txt, autonomy/autonomy_map.json
  (`generated_at` only; regenerate the map at integration).
- **C:** BUILD_STATE.md, DECISION_LOG.md.

## Suites, run on the merged trees

All runs used `PY=python3 JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`.

- **A:** 13 of 15 suites pass, 218 tests passing. The two failures:
  - `test_vis_gallery_e2e` fails 7 of 8 on the merge, but passes 8 of 8 on 2c253c07 alone.
    This is a merge regression (A1).
  - `test_vacuity` also fails on 2c253c07 alone. This is a branch defect (A2).
  - Passing: vis_gallery_gates, visual_campaign_standard, visual_factory_e2e,
    visual_pipeline_evidence, v2_gallery_consistency, v6_gallery_e2e, w4_close5_rows,
    w4_f852_amend, w4_ownerimg, w4_readback_evidence, model_spend_paths,
    cost_governance_wave2 and w4_resume_runner.
- **B:** 12 of 12 suites pass, 257 tests passing.
  - eng_vis_identity, v3_identity_qualification, cert_claude_independence, model_photography,
    model_identity, cert_identity, w3_b2_canonical_assets, visual_campaign_standard,
    v2_gallery_consistency, model_spend_paths, vacuity and w4_resume_runner.
  - These ran without face models installed.
- **C:** 5 of 5 suites pass, 91 tests passing.
  - wardrobe_scenes, visual_campaign_standard, v2_gallery_consistency, vacuity and
    w4_resume_runner.

## Mutation testing (one key line per unit)

Every mutant was killed.

| unit | mutant | result |
|---|---|---|
| A | `shot_plans.campaign_standard`: `len(roles) < CAMPAIGN_MIN_FRAMES` changed to `< CAMPAIGN_MIN_FRAMES - 1`, so a six-frame plan passes | KILLED: test_visual_campaign_standard fails 2 (`test_a_plan_below_seven_..._is_refused`, `test_readiness_is_never_gallery_ready_below_the_standard`) |
| B | `outfits.settle`: `keep = min(used, ...)` changed to `keep = mine[0]`, so the race winner ignores uses | KILLED: test_eng_vis_identity fails 2 (`test_interleaved_claim_whose_loser_already_has_uses_...`, `..._both_outfits_have_uses_retire_the_later_one`) |
| C | `gallery_planner.check_gallery`: `> 1` outfits changed to `> 2` | KILLED: test_wardrobe_scenes fails 2 (`test_check_gallery_refuses_two_outfits_...`, `test_each_rule_mutation_is_caught`) |

## Critical checks

- **Laura laura-r2-a42aeac7: OK in all three units.**
  - No canonical asset, `CURRENT_REFERENCE_HASHES` or `IDENTITY_ID` appears in any diff.
  - A's `image_production.laura_refs()` re-hashes all three references and raises
    `ConditioningRefused` unless 3 of 3 validate.
  - `identity_gate` makes all three mandatory, and that also applies to recovered frames,
    because recovery re-runs `candidate_gates.evaluate`.
- **Gallery of at least 7, with an identical product.**
  - A enforces seven on the plan (`campaign_standard`, folded into `gallery_view`).
  - The certified-frame-count check of D-OWNER-GALLERY-COMPLETE
    (`etsy_ops.certified_frames` "gallery incomplete") is NOT on A. It lives on
    eng/gallery-complete.
  - C's `check_gallery` refuses fewer than 7 frames and a changing product digest.
- **One outfit per listing.**
  - C plans one outfit per listing and refuses a second.
  - B's `settle` leaves exactly one outfit after a race, which F3 needed.
  - There is a residual cross-listing race in `reserve` (B1/C1).
- **Paid calls go through reservation and the ceilings.** A's FLUX route goes through
  `spend_plan.guard`, using the lower of the code cap and the owner's cap.
  `gallery_budget` refuses a cap above the code maximum and refuses non-owner actors.
- **Nothing is spent on a product that is not for sale: FAILS on A** (A3).
- **Labels.** Stubs are test_double, and test doubles are counted separately in the
  production evidence. C's contents frame is `disclosed_render` / PATTERN_PREVIEW.
- **UNKNOWN never counts as PASS: OK.**
  - The exception route refuses UNMEASURED, and the A1 regression itself fails safe.
  - B maps a non-PASS consumer verdict to UNKNOWN.
  - C's colour harmony reads UNKNOWN, not PASS, when the colours cannot be measured.

## (B) F1–F5 from review-results/vis-identity-96f5b294

- **F1 fixed.** The test asserts `qualification is None`, a HOLD verdict and biometric
  UNMEASURED.
- **F2 fixed.**
  - `identity-calibration/2` fixes thresholds on the calibration split and reports FAR/FRR
    on the held-out split only, so the floors apply to held-out counts.
  - `audit_split` recomputes the split from the rows and refuses in-sample or forged
    evidence.
  - Held-out FAR is now 2/6, so production correctly stays not ready.
- **F3 fixed for two claims on the same listing.** `settle` keeps the earliest-used outfit
  and retires a loser with uses. Mutant killed.
- **F4 fixed.** The reservation comes from `providers.input_tokens`, with a test that it is
  never below the gate's figure.
- **F5 fixed.** `transports_independent` is removed, and independence rests on distinct
  judge ids.

## Findings

1. **A3 (HIGH, blocking): spend before for-sale (D-OWNER-SPEND-ORDER / D-OWNER-SALE-PIPELINE).**
   - Where: `runtime/release.py` (~l.655).
   - Problem: the FLUX route is triggered at build time, before pricing, listing copy or
     any non-image listing gate has run. Neither `image_production.trigger` nor the
     generation stages check that the product is selected for sale.
   - Effect: it is shadow-safe only while the `image_generation` gate is closed. Once
     generation is activated, every certified release would buy a seven-image gallery,
     including releases later rejected or parked.
   - Fix:
     - Remove the FLUX `trigger` call from the price chain.
     - Enqueue the route only from the for-sale admission point, after every non-image
       listing gate is PASS.
     - In `image_production` (stage `plan`, before `prepare_references`), re-check
       admission. A product that is not eligible goes to a non-spending `waiting` state.
     - Release reservations when a product is rejected or parked.
     - Add a test that a certified release with a failing non-image gate makes 0 paid
       calls once activation is live.
2. **A1 (HIGH, blocking): `test_vis_gallery_e2e` fails 7 of 8 on dde3ea62.**
   - It passes 8 of 8 on 2c253c07 alone.
   - On the merge, every frame reads `motif_fidelity UNMEASURED`, so `exception_route`
     reads UNMEASURED. Tests 2, 3, 4, 6, 7 and 8 then fail.
   - It fails safe (nothing certifies), but no gallery can certify on the integration
     line.
   - Likely cause: A's `candidate_gates.motif_reading` / `motif-frame-` scratch path
     interacts with the motif-backlog and vis-flux changes now in the base
     (3552697, 36a2df0), or with the ENG-VIS-IDENTITY `_CONFIGURED` embedder default in
     `candidate_gates`.
   - Fix: merge dde3ea62 into eng/vis-gallery, find which reading returns UNMEASURED
     (log `checks['motif_fidelity']` in test_2), restore the test-double motif judge path,
     and require `test_vis_gallery_e2e` to pass 8 of 8 on the merged tree.
3. **A2 (MEDIUM, blocking with A): `test_vacuity` fails on the branch itself.**
   - Possibly-empty assert loops at `test_vis_gallery_e2e.py:275` (`rows`),
     `test_vis_gallery_gates.py:76` (`cases.items()`) and `:188` (`want.items()`).
   - Fix: add `assert rows` / `assert cases` / `assert want` before each loop.
4. **A4 (MEDIUM): the certified-frame count is not enforced on this unit.**
   - A gates seven on the plan's roles. The certificate consumer, `etsy_ops.certified_frames`,
     does not yet refuse a certificate with fewer than `CAMPAIGN_MIN_FRAMES` frames.
   - Fix: land eng/gallery-complete's `gallery incomplete` check together with A, or before
     it. Add a test where a certificate with 6 frames leaves the package BLOCKED.
5. **B1/C1 (MEDIUM): `outfits.reserve` is not compare-and-set across listings, and
   `settle` can crash.**
   - `reserve` sets `row.listing = listing` with an ORM write. It has no
     `WHERE listing = ''`, unlike `claim()`.
   - Two listings that reserve the same free outfit can both read it as free, and the last
     commit wins.
   - If the other listing commits between this one's commit and its `settle()`, then
     `settle` sees `mine == []` and raises IndexError at `mine[0]`.
   - Uniqueness is still caught at use time: `check_use` calls `reserve` again, which then
     FAILs. So no image ships with a shared outfit.
   - C's `outfit_library.claim_for_listing` goes through this path (`outfits.reserve`), not
     the CAS `outfits.claim`.
   - Fix:
     - In `reserve`, replace the assignment with
       `update(LauraOutfit).where(id==row.id, listing=='').values(listing=..., reserved_at=...)`
       and FAIL when rowcount != 1.
     - In `settle`, return `(None, [])` when `mine` is empty, and have callers FAIL on it.
     - Add an interleaved two-listing test.
6. **B2 (LOW): impostor identities can leak across the split.**
   - `identity_calibration._unit` splits by sample id before `~`. Two images of the same
     impostor identity with different ids can land on both sides of the split.
   - Fix: carry an `identity` field on impostor rows and split on it. Assert that no
     identity is on both sides.
7. **C2 (INFO): the CONTENTS frame counts toward seven.**
   - For a non-shaped family, C's plan is 6 generated frames plus the deterministic CONTENTS
     frame (disclosed render). A counts the frame the same way.
   - Confirm that D-OWNER-GALLERY-COMPLETE "seven frames" counts the disclosed CONTENTS
     frame as a certified frame. If it should not, add a seventh generated role.
8. **B3 (INFO):** regenerate `autonomy_map.json` at integration, since only its timestamp
   conflicted.

## Not verified

- No live BFL, OpenAI or Railway call was made.
- B was not re-run with the face models installed.
- A1's root cause is localised, not fixed.
