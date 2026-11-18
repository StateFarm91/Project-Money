# Review request — `eng/r5-research-2` (base f95bd617, `opus2/ws2-r5-research-proposal-writer-fix`)

Code commit: `e85fbeb` (this file is committed on top of it).
Requirement: watchlist gap → research task answered with real facts → proposal →
`radar.concept_intake`, unattended, on real evidence only.

## Findings → fix → test

| Finding | Fix | Regression test (fails on f95bd617, passes here) |
|---|---|---|
| **H1** low day-1 answer proposed, refused (0.35 < 0.40), then `_already_proposed` blocked the gap forever | `radar/proposal_writer.py`: the writer calls `intake.research_evidence` (the function intake judges with) and skips unless it is `ok`. `_already_proposed` is gone; `prior_proposals` + `_blocked_by_prior` key on an evidence digest and quality stamped on the task (`detail.proposal_evidence`). A pending or approved proposal blocks; a refused one blocks only the same digest or quality no higher than it was refused on. `watchlist_research.answer` no longer writes `low` answers: the task stays OPEN until durable | `test_r5_research_2.test_h1_the_real_cadence_takes_a_new_arena_to_an_approved_concept`: the real `CADENCES` (scan and intake every 6 h; compare, sweep and expiry daily), simulated days, real job handlers. On f95bd617 it fails with the refusal `evidence quality 0.35 is below 0.4`. Also `test_h1_a_refused_proposal_is_re_eligible_when_its_evidence_rises` (an old refused low proposal, which a production DB may already hold) and `test_h1_nothing_is_proposed_below_intakes_floor` |
| **H2** facts from stale shops and withdrawn listings; durability counted comparison runs | `intel/watchlist.py` `compare()`: `_arena_support` counts non-withdrawn rows; `_observation` counts a shop as fresh only when its state is `ok` and its last successful read is within `STALE_AFTER` (the anchor uses the newest `last_seen`). `_judge_arenas` → `validated_arenas` (each with `observations`: alias, `observed_at`, live count, listing ids) or `unknown_arenas` (value `UNKNOWN`, with the reason) when stale/withdrawn rows are the majority or fewer than 2 fresh shops remain. Figures of an `ok` read older than `STALE_AFTER` are graded STALE. `intel/watchlist_research.py`: answers only from fresh per-shop observations in the latest reading. Durability = distinct observation dates per shop (the 2nd-highest shop count). The two facts name per-shop timestamps and listing ids, and the observation dates | `test_h2_stale_shops_and_withdrawn_listings_are_never_a_fact` (the reviewer's reproduction), `test_h2_stale_only_shops_are_unknown_even_with_live_rows`, `test_h2_a_withdrawn_majority_is_unknown_even_with_two_fresh_shops`, `test_h2_durability_is_distinct_observations_not_comparison_runs`, `test_h2_facts_name_per_shop_timestamps_and_listing_ids` |
| **LOW** the positive E2E test patched `watchlist.compare` | `test_ws2_research_m2.py` drives real scans and the real `intel.watchlist_compare` job (`tests/_watchlist_sim.py`); `unittest.mock.patch` removed | `test_three_days_of_corroboration_reach_an_approved_concept_unattended` |
| **LOW** a new research task was opened and answered daily for every gap, forever | While not yet durable, one OPEN task is refreshed in place (`detail.watchlist_progress`). `research_agent.due_for_investigation` skips a task the comparison refreshed within 48 h; otherwise the sweep would stop it for lack of internal hits and a new one would open the next day. `record_comparison` does not re-open or answer research for a gap whose proposal is pending or approved | `test_low_one_open_task_per_gap_refreshed_not_duplicated`, `test_the_sweep_leaves_a_task_the_comparison_is_refreshing`, `test_ws2_research_m2.test_the_reopened_daily_question_never_proposes_the_same_gap_twice` |

Changed expectation (stronger, not weaker): `test_one_day_of_corroboration_is_low_confidence_and_proposes_nothing`
became `..._answers_nothing_and_proposes_nothing`. On day 1 there is now no answer, no
proposal and no refused row at all.

## Known limits (honest)
- After a **refused** proposal, the gap is still re-answered once a day after expiry, so
  rising evidence can be detected. The answerer only produces `medium`, so in practice the
  writer then blocks with "evidence quality has not risen". That is daily research churn
  with no new proposals. It only stops if the owner moves the gap to `not_pursuing`.
- `intake._unsupported_research` checks expiry against the real clock, not `as_of`. The
  simulated tests therefore reach durability on the real today. This is unchanged and out of
  scope; noted for the reviewer.
- Readings written before this change carry no `observations`, so they count toward
  nothing. After deploy, an arena needs 3 new observation days before it is answered.

## Suites run
`JOBS=4 SUITE_REGISTRY=0 PY=/tmp/venv/bin/python bash run_tests.sh` with SUITES = test_r5_research_2
test_ws2_research_m2 test_ws2_r5_proposal_writer test_w4_intelrec_watchlist
test_ws2_r6_r7_watchlist_env_dedupe test_w4_research_agent test_w5_concept_intake test_cert_mjs
test_opus2_scan_evidence test_w3_hq_independence test_w4_finhealth test_ws2_r1_competitor_scans
test_ws2_r3_source_timestamp test_ws2_r4_kept_scan_facts test_w4_research
test_w4_research_to_product_stall. Result: **184 passing**, 1 failing test:
`test_cert_mjs.test_the_veto_route_records_counts_and_feeds_lessons`. It is environmental
(starlette's test client needs the `httpx2` package, which is not installed) and fails the
same way on f95bd617. New suite: 10/10. On f95bd617: 0/10.
