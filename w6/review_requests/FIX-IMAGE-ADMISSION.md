# FIX-IMAGE-ADMISSION — D-MAIN-IMAGE-ADMISSION, review b18-a A-1, and the Batch 17 merge

- **Branch:** `eng/vis-gallery`.
- **Tested SHA:** **aa663b533c59a2c0250417f0ba8f9fd0a9097b3f**. This file and its BUILD_STATE pointer are the only later commit.
- **Merges:** ordinary merges only, nothing force-pushed.
  - `eng/colourwork` @ b098fcce (production Batch 17).
  - The concurrent push to this branch (`3ab2441` Batch 17 merge, `46c1b0c` A-1 fix). Its conflict resolutions matched mine, so the final tree differs from 46c1b0c only by this fix.
- **Restrictions kept:** no PR was opened, no Railway variable or secret was read, and no paid provider was called.

## D-MAIN-IMAGE-ADMISSION (recorded in DECISION_LOG)

**Allow-list.** `release_gates.PUBLISH_TIME_AREAS = frozenset({"gauge_and_size_claims", "etsy_remote_state"})`.

**How the area is read.** `eligibility.product_publication` now puts the first-customer `area` on each FIRST_CUSTOMER_BLOCKING reason. `release_gates.publish_time_reasons(verdict)` reads that structured area, never the text. A reason with no area, or an area not on the list, is not publish-time.

**Package tag.** `listing_package.assemble` tags such a blocker `publish_time: <area>`. The package stays BLOCKED.

**Admission.** `image_production.sale_admission` accepts a blocker only if one of these holds:
- it is `image: True`;
- it comes from `release_gates.for_publish` and its `publish_time` is on the allow-list. The allow-list is checked again here.

Everything else is non-image, including unattributable blockers, other first-customer areas such as `listing_claims` and `imagery`, and a forged tag from another source. Any of these prevents admission.

**Admitted result.** It names the publish-time gates that still block publishing.

**Publish path.** Unchanged: both reasons remain in `for_publish`, and `store.publish` still refuses.

### Tests (`test_vis_gallery_e2e`)

| # | requirement | test |
|---|---|---|
| 1 | blocked only by gauge + etsy + image reasons → admitted | `test_10`: the real key-basket chain. Its real blockers are SAMPLE_PHOTO_REQUIRED (image) and the two gates. The real `listing.package` admits it and enqueues exactly one FLUX job for this release. |
| 2 | the same release plus any other non-image blocker → not admitted | `test_11`: 9 kinds of extra blocker on the real package (a doubled read, labelled `test_double`), none admitted. `test_9` now adds a **real** LISTING_PRICE_NOT_PLAN gate to the same chain and still proves 0 paid calls and a parked, unspent run. |
| 3 | the publish path still refuses on both gates | `test_12`: `for_publish` blocks and lists both reasons. `store.publish` runs with the real Launch-0 scope gate, refuses with both `FIRST_CUSTOMER_BLOCKING: <area>:` reasons, and makes 0 Etsy requests. |
| 4 | removing the allow-list fails a test | `test_13`, plus these mutants run in throwaway worktrees, all killed: (a) `PUBLISH_TIME_AREAS = frozenset()` killed by tests 10, 11, 12 and 13; (b) the admission-side `area in PUBLISH_TIME_AREAS` check replaced by `bool(area)` killed by tests 11 and 13; (c) the reason-side area check removed killed by test 13. |

## Review b18-a §A-1

**Status: fixed.** `test_certify_assets_seo_grant_publish...` runs on `housewarming-key-basket` (FULL_SLUG / FULL_CATEGORY). The 6-frame blanket is asserted still blocked (`gallery incomplete`, no Etsy request).

**Two equivalent fixes.** My fix and the concurrent commit 46c1b0c were equivalent, and I kept 46c1b0c's version because it drives the blanket through `store.publish`. `CAMPAIGN_MIN_FRAMES` is unchanged and no test was skipped.

## Batch 17 merge

- **Conflicts:** all additive, resolved as the union of both sides:
  - `BUILD_STATE.md` and `DECISION_LOG.md`;
  - `ops/retention.py` KNOWN_READ_ACTIONS: the 3 gallery rows plus the 6 ENG-DAILY windowed rows.
- **`autonomy_map.json`:** regenerated with `python -m brambleloop.autonomy.map --write src/brambleloop/autonomy/autonomy_map.json`. It now has 149 cadences, 181 handlers and 95 follow-on edges.

## Suites

**Command:** `PY=<venv from requirements.txt + httpx> JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`.

**Run:** 20261120T162439Z-21362, at aa663b53, on a clean tree, 440 s.

**TOTAL PASSING: 235; suites failing: 0** (16 suites)

**The review's 13 A suites:**
- vis_gallery_e2e 13/13
- vis_gallery_gates 14/14
- visual_campaign_standard 4
- visual_factory_e2e 6
- visual_pipeline_evidence 6
- v2_gallery_consistency 5
- v6_gallery_e2e 10
- w4_close5_rows 8
- w4_f852_amend 8
- w4_ownerimg 35/35
- w4_readback_evidence 23. It ran here: `httpx` was installed in the venv. b18-a's ENV note about adding it to requirements.txt is still open.
- model_spend_paths 12
- cost_governance_wave2 39

**Required:** test_vacuity 8/8, test_w4_resume_runner 40/40, test_search_hero_publish 4/4.

**An earlier run at c88f5aba** was 234 passing with 1 failing: test_vacuity flagged the new loop in test_11. That is fixed by `assert extras`.

## Not run here

The `area` key on eligibility reasons and the `publish_time` key on package blockers are additive. I did not run the other suites that read those structures, so an integrator full run should cover them:
- test_eligibility
- test_launch0_listing_truth
- test_opus2_listing_package
- test_w6_listing_chain_e2e
- test_w4_listready
- test_motif_backlog
- test_owner_gallery_complete

## Honest status / owner-visible consequence

- Production still has **0** generated galleries.
- With this change, once `image_generation` is activated, a Launch-0 release is admitted for paid FLUX images if its only blockers are images plus the physical-sample and Etsy-verification gates. That is spend that was previously impossible.
- It stays bounded by the unchanged spend_plan guard, the paid-provider gate, the agent's daily ceiling and the company's monthly budget.
- Nothing publishes until both gates pass.
- b18-a A-2 is still open: admitted releases are not yet ordered by expected value.
