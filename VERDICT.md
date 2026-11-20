# Review b18-a: vis-gallery (re-review) and demand-supply onto Batch 17 b098fcce

Reviewed 2026-11-20 (UTC). No paid provider was called, no Railway variable or secret was read,
and no PR was opened.

| unit | head | verdict |
|---|---|---|
| (A) eng/vis-gallery | 9bd3caab | **BLOCK**: one red suite (A-1, a one-line fixture fix); all b17-c Unit A findings are fixed |
| (B) eng/demand-supply | 2a85f4f3 | **SHIP**, with B-1 and B-2 as follow-ups |

## Merges onto b098fcce

b098fcce is not an ancestor of either head. Every conflict was additive. I resolved each as the
union of both sides, and the JSON timestamp kept the base side.

- **A:** BUILD_STATE.md, DECISION_LOG.md, `ops/retention.py` and `autonomy/autonomy_map.json`.
  - In `ops/retention.py`, the KNOWN_READ_ACTIONS entries do not overlap: the base's
    ENG-DAILY windowed rows plus A's three gallery rows. Keep both.
  - In `autonomy_map.json`, only `generated_at` conflicts.
  - Note: a two-dot diff from the base appears to delete `ops.daily_ledger` and similar code.
    That is base-side history the branch never had. The merged tree keeps all of it; I checked
    `handle_daily_ledger` is present.
- **B:** `autonomy/autonomy_map.json`, `generated_at` only.
- Regenerate `autonomy_map.json` at integration.

## Suites, run on the merged trees

The runs used `PY=<venv> JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`. The venv was
built from requirements.txt.

**A: 21 suites, 335 tests passing, 2 suites failing.**

- **Passing:** vis_gallery_e2e (9/9, including the new test_9), vis_gallery_gates,
  owner_gallery_complete, visual_campaign_standard, visual_factory_e2e, v6_gallery_e2e,
  disclosed_certified_upload, launch0_listing_truth, motif_backlog, w4_close5_rows,
  w4_disclosedqa, w4_f852_amend, w4_ownerimg, etsy_readback_observe, opus2_photo_asset_review,
  model_spend_paths, cost_governance_wave2, **vacuity** and w4_resume_runner.
- **`test_search_hero_publish`: 3/4. This is a real defect (A-1).** It also fails on 9bd3caab
  alone.
- **`test_w4_readback_evidence`: an environment failure.** `starlette.testclient` needs the
  `httpx2` package, which is not in requirements.txt. The suite dies on import before any test
  runs, and it fails the same way on B. I did not install the unpinned package in this
  container. Not verified here.

**B: 6 suites, 178 tests passing, 1 suite failing.**

- **Passing:** eng_demand_supply, research_flow, **v11_pwa_static** (87/87; the static files and
  sw v44 changed), vacuity and w4_resume_runner.
- **`test_w4_readback_evidence`:** the same environment import failure as on A. B edits this
  suite to add the `engine_demand` row, so it needs a run in the real CI venv before
  integration.

## Mutation testing (one key line per unit)

Both mutants were killed.

| unit | mutant | result |
|---|---|---|
| A | `image_production.sale_admission`: `if other:` changed to `if False and other:`, so non-image blockers are ignored and the paid FLUX route is admitted | KILLED: test_vis_gallery_e2e `test_9_a_release_with_a_failing_non_image_gate_makes_no_paid_call` (admitted True with a failing non-image gate) |
| B | `demand._score`: `... if value is not None else PRIOR` changed to `else 0.0`, so UNKNOWN reads 0 | KILLED: test_eng_demand_supply fails 2 (`test_unknown_is_never_zero_and_never_scores_high`, `test_a_missing_signal_lowers_confidence_while_a_measured_zero_lowers_the_value`) |

## (A) b17-c Unit A findings: re-check

- **A3 fixed (spend before for-sale).**
  - `runtime/release.py` no longer enqueues the FLUX route at build time.
  - `listing.package` calls `image_production.admit_for_sale` after the package is recorded.
  - `sale_admission` admits only when:
    - the lifecycle is not REJECTED, RETIRED or ROLLED_BACK;
    - the package is for exactly this release;
    - every blocker is tagged `image`.
  - Unreadable means not admitted.
  - `publish.release_gates.image_reasons` tags only listing_set, originality, sample_photo,
    search-hero and gallery-size standard reasons. An unattributed reason counts as non-image,
    so unknown never admits.
  - Every stage of a FLUX or paid run re-checks admission. If admission fails, the run moves to
    `waiting_for_sale_admission` without spend, and `_park_for_sale` releases the outfit
    reservation.
  - test_9 covers this, and the mutant above is killed.
- **A1 fixed.** test_vis_gallery_e2e passes on the merged tree (motif_verdict).
- **A2 fixed.** test_vacuity passes.
- **A4 fixed.** eng/gallery-complete is merged:
  - `etsy_ops.certified_frames` reports "gallery incomplete" below `CAMPAIGN_MIN_FRAMES` = 7;
  - `lifecycle.derive` needs a complete certified gallery for LISTING_READY;
  - test_owner_gallery_complete passes.

## Critical checks

**(A) Laura laura-r2-a42aeac7: OK.**
- No canonical asset, `CURRENT_REFERENCE_HASHES`, `IDENTITY_ID` or identity_gate change is in
  the merge diff.
- `laura_refs()` re-hashes every reference in `CURRENT_REFERENCE_HASHES`. A reference with
  different bytes is never substituted, and anything but 3 of 3 raises `ConditioningRefused`.

**(A) A gallery has 7 or more certified frames and the same product: OK.**
- Seven is enforced on the plan (`campaign_standard`), on the certificate consumer
  (`certified_frames`) and on lifecycle.
- The product is held invariant per frame through the product_truth / `visual.fidelity` gate
  against the certified CIR. The gallery checker refuses `product_not_invariant`.

**(A) Paid calls go through reservation and ceilings: OK.**
- Generation goes through `spend_plan.guard` (image_production l.707, l.867) and the
  paid-provider gate (agent daily ceiling and company monthly budget).
- The new admission layer only adds a refusal in front of these.

**(A) Stubs are labelled test_double: OK.**
- Every doubled reading in test_vis_gallery_e2e carries `test_double`.
- `production_evidence` counts `verified_with_test_doubles` separately.

**(B) The demand score is deterministic, from stored evidence, and UNKNOWN is never 0: OK.**
- It reads `benchmark_listings`, `serp_snapshots` and the dated teardown facts. The teardown
  facts are numbers and clusters only, with no competitor title.
- There is no model, network or random call. The result is a pure function of the rows and
  `now`.
- A missing signal lowers confidence. A cluster with no evidence scores PRIOR = 0.20, and
  `engine_demand` falls back to PRIOR.
- An unreadable table adds nothing; it never adds an invented value.

**(B) The core-family boost works: OK, but see B-1.**
- The boost is amigurumi 0.30 > baby 0.26 > pillow 0.22, scaled by confidence (×0.5 to ×1).
- Every core family appears in `families()` even with no observations.
- The flattened-boost mutant is killed by the branch's own tests.

**(B) Admission order and the engine-demand list: OK.**
- `supply.offers` orders by market demand, then research flag, then the producer's score, then
  offer_id.
- Intake evaluates candidates in demand order with a stable sort.
- A concept with no certified engine is recorded once per reading as `supply.engine_demand` and
  stays waiting. It is admitted after its engine certifies; a test covers this.
- `engine_demand()` ranks by top demand, then count, then name.
- The readback row is advisory: WARN or PASS, never a deploy FAIL.

**(B) The 28 originals are original: OK.**
- All 28 are generic subjects with house descriptors, for example "Riverbank Capybara",
  "Pebble Path Baby Cardigan" and "Sleepy Frog Face Cushion".
- None of them is a character, brand or shop name.
- No title or subject phrase appears anywhere else in the repository: I grepped all 28 against
  every file except the unit's own.
- At run time, `ideation.originality_reasons` drops any title that overlaps an observed
  competitor title. Every concept then goes through intake's dedupe, novelty, anti-copy and
  children's gates.
- See B-3 on the capybara and cow subjects.

**(B) No gate is weakened: OK.**
- The engine hold is a new refusal, and the capacity, WIP and diversity checks are unchanged.
- The two test edits are:
  - research_flow excludes the new `demand_originals:` tasks from a single-task selector;
  - readback_evidence adds the 21st row and asserts it is WARN or PASS.
- No assertion is relaxed.

## Findings

1. **A-1 (HIGH, blocking A): `test_search_hero_publish::test_certify_assets_seo_grant_publish_creates_exactly_one_draft_with_no_forced_verdict` fails.**
   - It fails both on 9bd3caab and on the merge.
   - The blanket fixture's disclosed set certifies 6 frames. D-OWNER-GALLERY-COMPLETE now
     correctly blocks publish with "gallery incomplete: ... 6 of the 7".
   - The test still expects `published is True`.
   - The gate is right; the fixture is stale. 6c33484 moved the other fixtures and missed this
     one.
   - The review request's "0 failing suites" did not include this suite.
   - Fix:
     - Drive the test with the complete-gallery product, as `test_visual_factory_e2e` does:
       `path, version, rh = _chain(FULL_SLUG, FULL_CATEGORY)` with that test's constants, and
       the matching `SLUG` in `_profile`, `certified_payload` and the publish inputs.
     - Then add one assertion that the 6-frame blanket stays `blocked` with "gallery
       incomplete".
     - Re-run test_search_hero_publish and visual_factory_e2e.
     - Do not lower `CAMPAIGN_MIN_FRAMES` or skip the test.
2. **A-2 (MEDIUM, follow-up): no expected-value ordering of image spend (D-OWNER-SPEND-ORDER).**
   - `admit_for_sale` enqueues each admitted release as its package lands, so the CA$100/month
     ceiling is spent first-come rather than "ordered by expected value (core families first)".
   - The ceilings still hold, so nothing overspends.
   - Fix, once B is integrated:
     - Give the FLUX `visual.image_production` enqueue a priority from
       `products.demand.index(db).score(title, category)`, or let the listing.package sweep
       admit in descending demand score.
     - Add a test: with budget for one gallery, a core-family release is admitted before a
       décor release with the same gates.
3. **B-1 (MEDIUM, follow-up): garments are boosted and labelled `core` beyond
   D-OWNER-CORE-FAMILIES.**
   - The owner named three permanent core families. `CORE_FAMILIES` adds `GARMENT` (boost
     0.18), and the Demand panel and readback mark garments `core: True`.
   - The ordering of the three owner families is correct, but the label misstates the owner
     directive, and garments outrank unboosted families on equal evidence.
   - Fix, either:
     - (a) drop GARMENT from `CORE_FAMILIES` and `CORE_BOOST`, and update the tests that assert
       four families; or
     - (b) keep a separately named `SECONDARY_BOOST = {GARMENT: ...}` with `core=False`, and
       record the reason in D-ENG-DEMAND-SUPPLY as a routine (non-owner) weighting.
4. **B-2 (LOW): `supply.offers.order` reads a missing market score as 0.0.**
   - The code is `-(float(market) if ... else 0.0)`. `_market_demand` always returns a score
     today, so this is latent, but it contradicts "UNKNOWN is never 0".
   - Fix: use `demand.PRIOR` as the fallback.
5. **B-3 (INFO): capybara and cow subjects.**
   - "Riverbank Capybara" and "Clover Cow" share subjects with the two purchased teardowns
     (MadelineMaeCo capybara, Highland Cow).
   - The subjects are generic and the titles are original. When their engines are built,
     confirm that the CIR is designed fresh and takes only structure lessons from
     `TEARDOWN_*.md`, never the teardown's shapes, counts or charts.
6. **ENV (INFO): add `httpx2` to requirements.txt.**
   - Pin the version that `starlette.testclient` needs, or the suites that use the test client
     cannot run in a fresh venv.
   - Re-run `test_w4_readback_evidence` for both units in CI before integration.

## Not verified

- `test_w4_readback_evidence` on either unit, because of the environment import failure above.
- No live BFL, Etsy or Railway call was made, and face models were not installed.
