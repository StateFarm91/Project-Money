# Review request — `eng/r5-research-2`, round 3 (base a459d73e)

Code commits: `79e9386` (fix), `eafe866` (tests). This file was `REVIEW_REQUEST.md` at the
repository root; it now lives here so it does not merge into the integration tree.
Rounds 1–2 (H1, H2 and their LOWs) are recorded in the a459d73e version of the root file.

## Findings → fix → test

| Finding | Fix | Regression test (fails on a459d73e, passes here) |
|---|---|---|
| **H3** an approved watchlist concept withdrawn the next day (its `market_radar` answer is fresh 1 day); the gap then dead forever because `_blocked_by_prior` and `_decided_by_proposal` blocked on any state but REFUSED | **Support is renewed, not lapsed.** `intel/watchlist_research.renew_support`: for a gap whose proposal is APPROVED, the gap's question is re-asked (new task, trigger `watchlist_gap:N#renew:<head>`, `reopen_because=new_evidence`) and answered by the same `answer()` (fresh per-shop observations in the latest reading, durability). Only once answered is it recorded on the concept's task (`detail.renewed_support` = task, refs, reading_day). Callers: the daily comparison (`record_comparison`, renews unless the support already rests on today's reading) and the 6-hourly `radar.concept_intake` job (`watchlist.renew_approved_support(expiring_within=12 h)`), so a late comparison cannot let the support lapse between intake passes. **Intake follows it:** `intake.renewed_evidence` judges the renewed answer with `research_evidence` (unchanged rules); `withdraw_unsupported` and `_unsupported_research` accept the original OR the renewed answer. Stale/withdrawn/not-durable evidence → no renewal → the answer expires → withdrawn. **Re-eligibility:** `_blocked_by_prior` now blocks on pending (None/PROPOSED) and APPROVED; WITHDRAWN blocks only the same evidence digest; REFUSED unchanged. `_decided_by_proposal` returns (pending-why, approved tasks): pending waits, approved renews, refused/withdrawn/superseded let research continue | `test_r5_research_3.test_h3_an_approved_concept_stays_approved_while_evidence_stays_fresh` (real cadence; still APPROVED and `seed_for(slug)` found on days +1..+5; each day's support rests on that day's reading); `test_h3_stale_evidence_withdraws_and_fresh_evidence_re_proposes` (scans stop → withdrawn, writer writes nothing on stale evidence → scans resume → a new proposal on a new digest is APPROVED and stays approved); `test_h3_withdrawn_blocks_only_its_own_evidence`; `test_h3_the_intake_job_renews_a_support_about_to_expire`. `test_r5_research_2.test_h1_the_real_cadence_…` extended: STILL approved on days +2..+6 (fails on a459d73e: withdrawn on day -2) |
| **LOW** no test fails if the writer's own floor check is removed | — (the check exists) | `test_low_the_writers_own_floor_check_refuses_a_low_answer`: a `low` answered task passes every other writer check. It passes on a459d73e (the check is there); **mutation-proved**: with `if not ev.get("ok")` replaced by `if False` the test fails (a proposal is written) |
| **LOW** anchor figures MEASURED whatever the age of its last good read | `watchlist.compare`: `fresh = state in (ok, rows_present) and observed_fresh` — the anchor's `observed_fresh` is its newest `last_seen` within `STALE_AFTER` | `test_low_the_anchor_is_graded_by_the_age_of_its_last_good_read` (30 days → STALE; 1 h → MEASURED) |
| **LOW** `intake.evaluate` TypeError at intake.py:977 when the approved pool leaves the new row out | `evaluate`: if `approved_concept` is None at hand-off (its research expired by the real clock since `today`), the row is WITHDRAWN with the reason and audited; no `radar.score` is enqueued; the pass continues | `test_low_evaluate_withdraws_instead_of_raising_when_the_pool_leaves_the_row_out` (on a459d73e the real `radar.concept_intake` job FAILS with that TypeError) |

Proof on a459d73e (worktree, new test files copied in): `test_r5_research_3` 1 passed / 6
failed (the 1 is the floor test, mutation-proved above); `test_r5_research_2` 8 / 2 failed
(the extended real-cadence test and the changed LOW expectation below).

## Changed expectation (stated, not weakened)
`test_r5_research_2.test_low_one_open_task_per_gap_refreshed_not_duplicated` asserted "no
new task after approval". H3 requires the opposite (a one-day answer must be renewed). It now
asserts: exactly one original task (answered/expired), exactly one renewal per later day
(3), none left OPEN, all answered on distinct days, and the concept still APPROVED.

## Known limits (honest)
- Renewal churn: up to **two** renewal tasks per approved watchlist concept per day (the
  intake job's last-chance renewal within 12 h of expiry, then the comparison's renewal from
  the new reading). Bounded; each is a real answer from fresh observations. The test pins
  5..10 renewals over 5 days.
- The last-chance renewal may answer from the previous day's reading while its observations
  are still within `STALE_AFTER` (48 h); intake's freshness on that reading's date
  (`market_radar` = 1 day) still applies, so an old reading is never renewed into a fresh one.
- `intake._unsupported_research` still checks expiry against the real clock (unchanged; now
  it also accepts the renewed answer). The hand-off TypeError it caused is fixed.
- After deploy, a concept already WITHDRAWN by the a459d73e behaviour becomes re-eligible
  only when a new durable answer (a new evidence digest) is written; it is never revived.

## Suites run
`JOBS=4 SUITE_REGISTRY=0 PY=/tmp/venv/bin/python bash run_tests.sh` with SUITES =
test_r5_research_3 test_r5_research_2 test_ws2_research_m2 test_ws2_r5_proposal_writer
test_w4_intelrec_watchlist test_ws2_r6_r7_watchlist_env_dedupe test_w4_research_agent
test_w5_concept_intake test_cert_mjs test_opus2_scan_evidence test_w3_hq_independence
test_w4_finhealth test_ws2_r1_competitor_scans test_ws2_r3_source_timestamp
test_ws2_r4_kept_scan_facts test_w4_research test_w4_research_to_product_stall:
**191 passing**, 1 failing — `test_cert_mjs.test_the_veto_route_records_counts_and_feeds_lessons`,
environmental (starlette test client needs `httpx2`), same on a459d73e.
Second batch (callers of intake/comparison): results pending at commit time; see the next commit.
