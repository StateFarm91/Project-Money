# Independent review b17-a: eng/daily bd44b189, eng/seo-price 110d0507, eng/concepts-100 f6a23e46

Reviewer: independent Claude Code session, 2026-11-20 UTC. Base claude/w6-INTEG6 dde3ea62.
No Railway variables or secrets were read. No PR opened. Fresh venv from `requirements.lock` + `requirements-test.lock`, Python 3.13.
Merges were done in scratch worktrees; each suite run used `JOBS=n SUITE_REGISTRY=0 SUITES="..." bash run_tests.sh`.

| unit | verdict |
|---|---|
| A eng/daily @ bd44b189 | **SHIP** (merge needs the 4 trivial conflict resolutions in finding A1) |
| B eng/seo-price @ 110d0507 | **BLOCK** (B1; small fix) |
| C eng/concepts-100 @ f6a23e46 | **BLOCK** (C1 breaks a suite on the integrated tree; C2 untested originality gate) |

## Merge onto dde3ea62 (all three conflict; none is silent except C1)

- **A:** conflicts in BUILD_STATE.md, DECISION_LOG.md (keep both), autonomy_map.json (generated_at only; regenerate with `python -m brambleloop.autonomy.map --write` -> 149 cadences / 181 handlers) and `tests/test_w4_readback_evidence.py` (the two advisory tuples and the item count must be unioned: base has `motif_backlog_recovery`, daily adds `daily_ledger`, so the count is **20**, not 19). `sw.js` auto-merged to cc-shell-v43.
- **B:** BUILD_STATE.md and autonomy_map.json only (regenerate: 148 / 180, follow_on 94).
- **C:** BUILD_STATE.md, DECISION_LOG.md, autonomy_map.json, `p0_board.py` (SECTIONS: keep `motif_recovery` and `concept_pool`), `sw.js` (branch says v37, base is v42, A takes v43, so C must be **v44**), `swarm/orchestrate.py` (UPSTREAM_INPUTS: keep INTEG's learn/improve entries and add the two `radar.concept_pool` entries). **Silent semantic conflict: see C1.**

## Suites (my resolved merges; clean trees)

| unit | suites | result | run record |
|---|---|---|---|
| A | test_eng_daily, test_vacuity, test_w4_resume_runner, test_w4_readback_evidence, test_v11_pwa_static, test_s4_p0_board | **202 passing, 0 failing** (readback 23/23, pwa 86) | 20261120T122930Z-792 |
| B | test_eng_seoprice, test_vacuity, test_w4_resume_runner, test_w4_readback_evidence, test_v11_autonomy_timeline, test_v11_seo_taxonomy, test_v11_seo_truth, test_w3_seo_constraints, test_w4_cap1_placemat_price, test_w4_placemat_reprice | **130 passing, 0 failing** | 20261120T122946Z-5021 |
| C | test_concepts100, test_vacuity, test_w4_resume_runner, test_w4_readback_evidence, test_s4_p0_board, test_v11_pwa_static, test_research_flow, test_v11_autonomy_timeline | **214 passing, 1 suite failing: test_research_flow** (2 tests) | 20261120T123001Z-8462 |

## Mutations (one key line each, then the unit's own suite; tree restored after)

- **A:** removed the `MIN_HOURS_INTO_DAY` guard in `stage_readings` -> `test_the_first_run_after_midnight_diagnoses_no_stage_and_files_nothing` FAILS. Killed.
- **B:** disabled the band minimum (`if len(rows) < MIN_BAND_OBSERVATIONS ...` -> `if False`) -> 3 tests fail (`test_a_thin_shelf_is_unknown_and_no_price_is_invented`, `test_mutation_band_minimums_are_load_bearing`, one more). Killed. **Survivor:** replacing the trigram-Jaccard term in `overlap()` with `False` leaves 23/23 green (B2).
- **C:** disabled the title-restatement threshold (`_jaccard(...) >= 0.8` -> `if False`) -> `test_copied_titles_are_refused` FAILS. Killed. **Survivor:** replacing `twin = _matches_a_listing(concept, cards) if cards else ""` with `twin = ""` (design-copy check off) leaves `test_concepts100` 14/14 green (C2).

## Unit A: every finding of review-results/motif-daily Unit B

1. **Readback contract: FIXED.** `ops/readback.py` has the `daily_ledger` EVIDENCE_ITEMS row and `_judge_daily` (UNKNOWN when missing or unreadable, WARN on zero-output or unknown stages, PASS only when all stages read). test_w4_readback_evidence 23/23.
2. **Midnight flood: FIXED.** Zero-output needs `hours_into_day >= MIN_HOURS_INTO_DAY`, `expected >= EXPECTED_MIN` and `t <= FAR_BELOW * expected`; otherwise `not_yet_due`. `_file_ecr` dedupes by fingerprint per stage per UTC day, and the fallback checks for an existing same-day `ops.ecr_pending` row. Test present and the mutation above kills it.
3. **concepts_held false 0: FIXED.** UNKNOWN on days with no DONE `radar.scan` and no stall reading; test `test_concepts_held_is_unknown_on_a_day_no_radar_scan_completed`.
4. **Inverted pill: FIXED.** `daily.js` has "invert" and "neutral" row modes (Failures, Dead letters inverted; Spend neutral INFO).
5. **Horizon edge: FIXED.** `dd <= horizon`; test `test_the_retention_horizon_day_itself_is_unknown`.
6. **Review request table: FIXED.** Run table appended to daily_slice1.md.

Also verified: bundle under the 400 KB limit (test_v11_pwa_static 86 passed), sw.js shell version above base's v42, no new route outside the `/api/cc` owner gate in the diff.

### Findings (A)
- **A1. Medium (integration).** Merging onto dde3ea62 conflicts; resolve as listed above. The readback test count must become 20 and the advisory tuple must contain both `motif_backlog_recovery` and `daily_ledger`. *Fix:* the integrator resolves as listed, regenerates the autonomy map, and reruns test_w4_readback_evidence, test_v11_pwa_static and test_eng_daily on the merged tree (all green in my run).

## Unit B: eng/seo-price (BLOCK)

Checked and holding: the price decision keeps `was_price=None` and calls `check_no_fake_discount(price, None, ever_charged=False)`; the price is inside the MEASURED interquartile band (>=MIN_BAND_OBSERVATIONS from >=MIN_BAND_SHOPS shops) or refused with `OUTSIDE_EVIDENCE_BAND`; an UNKNOWN band is recorded as "static category band" and no price claims evidence; sale listings are counted at listed price with the sale share reported; `market_fit.py` makes no network or provider call, so the CA$100 monthly ceiling is untouched; no competitor title text is stored beyond a 140-char excerpt in a refusal record; tags are filtered through product-truth checks.

### Findings (B)
1. **B1. High (UNKNOWN passes as PASS).** `originality()` returns `ok: True` with `checked: 0` when the research shelf has no titles (verified: `originality("Crochet Cat Hat Pattern", [])` -> `{'ok': True, 'checked': 0, ...}`). `release.py` then writes `market_fit={"ok": not mf_blocking, ...}` into the search certificate, so a listing with **no** competitor evidence earns a passing `market_fit` check, and `CATEGORY_UNKNOWN` is not in `mf_blocking` (only `TITLE_` and `FOLD_` prefixes are). *Fix:* in `originality()` return `{"ok": None, "status": "UNKNOWN", ...}` when `checked == 0`; add `TITLE_ORIGINALITY_UNKNOWN` to `problems` in `seo_package` and to the `startswith(("TITLE_","FOLD_"))` tuple, or have `search.certificate` set `checks["market_fit"]["ok"]=False` when `originality` is not True; add `CATEGORY_` to the blocking prefixes. Add a test: empty shelf -> certificate `market_fit.ok is False`.
2. **B2. Medium (untested gate).** The trigram-Jaccard copy test (rearranged or restated competitor titles) has no killing test: mutating it out leaves 23/23 green. *Fix:* add a test with a competitor title and an ours that shares no run longer than MAX_SHARED_RUN but has Jaccard >= `MAX_TRIGRAM_JACCARD`; assert `copied` and `TITLE_COPIES_COMPETITOR`.
3. **B3. Low.** `discount_problems()` (B-376 flagship and a-third-of-days rules) is not called from any live path, only tests. Nothing deceptive reaches a listing because `was_price` is always None, but the guard is shelf-ware. *Fix:* call it from the discount/sale path, or delete it and say the rule is enforced by `was_price=None`.
4. **B4. Low.** `seo_package` falls back to `research_listings(db)` (every pod) for originality when the pod's shelf is empty. That is acceptable for a copy check but should be labelled: record `"scope": "pod"|"all"` in the originality evidence.

## Unit C: eng/concepts-100 (BLOCK)

Checked and holding: concept titles come from our own lane/motif vocabulary (`title_for(lane, motif)`), and the proposal text carries counts and our rationale only (`proposal_from`: no shop names, no competitor text; `test_no_competitor_words_reach_a_concept` passes). Clone refusal runs `nearest()` against the briefed catalogue, the approved intake rows and the pool's already-accepted concepts. Admission goes through `intake.attach_proposal` on an answered research task, capped by `ADMIT_PER_RUN` and `POOL_SHARE_OF_CEILING`; the `radar.concept_pool` cadence and the UPSTREAM_INPUTS wake route concepts into supply with no manual step (`test_admitted_concepts_are_approved_by_intake_on_its_own_checks`).

### Findings (C)
1. **C1. High (breaks the integrated tree).** The branch registers `benchmark_shopping` in `intel/research_flow.sources()` ("it was missing from the registry on INTEG3"), but dde3ea62 already has it (line 362). Git merges cleanly and the registry then holds the id twice: `test_research_flow` fails `test_every_research_cadence_is_in_the_registry_and_every_mandatory_shop_too` (`len(ids) == len(set(ids))`) and `test_the_board_shows_every_source_and_what_each_shop_led_to`. *Fix:* delete the second `_src("benchmark_shopping", ...)` block from `research_flow.py` (keep only `concept_pool`), then rerun test_research_flow, test_concepts100 and test_s4_p0_board. Also bump sw.js to v44 (A is v43) and resolve the other conflicts listed above.
2. **C2. High (originality gate off without a failing test).** The design-copy refusal `_matches_a_listing(concept, cards) if cards else ""` can be removed with `twin = ""` and test_concepts100 stays 14/14. Also, when a pod has **no** benchmark cards the check is skipped and the concept can still be READY (`detail["benchmark_cards"] = 0` is recorded but not judged), so an unverified design is treated as original. *Fix:* in `originality()` add `reasons.append("held: originality against observed listings is UNKNOWN (no benchmark cards for pod)")` when `not cards` and make `classify` return HELD for it (not READY); add a test with a card that matches a generated concept (must be REFUSED) and a test with no cards (must be HELD, not READY).
3. **C3. Medium (lineage is lane-level).** The evidence attached to each concept is the lane's signal (`lane_signal`: refs of up to 8 `benchmark_listing:<id>`), shared by every motif variant in that lane, so "100 evidence-backed concepts" counts variants of fewer demand signals. `evidence_backed()` checks only that refs are present and listings >= 2; it does not re-read that the referenced listings still exist or are fresh at health time. *Fix:* report distinct lanes and distinct evidence refs beside the 100 in `health()` (`counts.distinct_lanes`, `counts.distinct_refs`), and make `evidence_backed()` re-check that at least `MIN_SIGNAL_LISTINGS` of the refs still resolve to fresh BenchmarkListing rows (else STALE).
4. **C4. Low.** Title-restatement threshold (specific-token Jaccard >= 0.8) is permissive for short titles; a 4-token title sharing 3 tokens passes. Consider 0.6 plus the verbatim and shared-run rules from market_fit.overlap.

## Order of integration
A, then B after B1, then C after C1 and C2 (C's sw.js must be v44, C's orchestrate/p0_board resolutions as above).
