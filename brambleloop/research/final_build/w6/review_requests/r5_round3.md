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
- Renewal churn: up to **two** renewals per approved watchlist concept per day (the
  intake job's last-chance renewal within 12 h of expiry, then the comparison's renewal from
  the new reading). Each is a real answer from fresh observations. The test pins 5..10
  renewals over 5 days (counted in the audit log since round 4; only `RENEWAL_KEEP` = 2
  renewal task rows are kept per concept).
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
Second batch (every other suite that calls concept intake, the comparison or withdrawal):
test_cert_orchestration test_chaos test_creators test_k8_listing_estate
test_operating_cost_basis test_r2_autonomy_scheduler_blocks test_rehearsal_stall
test_search_truth test_w4_c12_dashboard_registers test_w4_c12_lifecycle
test_w4_close5_vision_timeout test_w4_launchfix test_w4_listready: **210 passing**, 1 suite
failing: `test_w4_launchfix` cannot import (`fastapi.testclient` needs `httpx2`, not
installed). This is the same environmental failure as above; no test in that suite ran.

---

# Round 4 (review of 5f8c02aa) — code commit `14e1dffc`

## Findings → fix → test

| Finding | Fix | Regression test (fails on 5f8c02aa, passes here) |
|---|---|---|
| **M1** a shop that relists listings it withdrew never counts again: `observe.scan` updated `last_seen` on an unchanged listing but left `audit_state == "withdrawn"`, so `compare()` kept them in the stale-or-withdrawn majority → arena UNKNOWN forever, never re-proposed | `intel/observe.py`: a withdrawn row seen live again is **revived** — unchanged: `audit_state` back to `audited` (gallery already read) or `queued`; changed: the normal re-read (`queued`). The withdrawal is not erased: `_revival` moves `withdrawn_first_noticed` into `detail.withdrawal_history` (entries `{withdrawn_first_noticed, relisted_at}`, last 20 kept); the changed-listing rebuild of `detail` carries the history over. The scan report lists them (`relisted_since_last_scan`, change "listed again after a withdrawal") | `test_r5_research_4.test_m1_a_relisted_listing_counts_again_and_keeps_its_withdrawal_history` (real scans + compare: drop 2 of 3 → UNKNOWN; relist identical → rows live, history recorded, arena validated with 3 live listings per shop); `test_m1_a_relisted_and_changed_listing_keeps_its_withdrawal_history`; `test_m1_withdraw_then_relist_is_re_proposed_through_the_daily_cycle` (production cadence: approved → shop drops 2 of 3 → concept withdrawn → identical listings return → a second proposal on a new source is APPROVED; on 5f8c02aa it stays withdrawn, nothing re-proposed) |
| **LOW** renewal tasks per approved concept per day kept forever (chain unbounded) | `watchlist_research.renew_support`: `renewed_support.chain` keeps the last `RENEWAL_KEEP` (2) renewal ids; the superseded head is set EXPIRED (`superseded_by`, so `research.expire_due` never re-opens it as a new OPEN task); older renewal tasks are deleted (`renewed_support.pruned` counts them). Every renewal stays in the audit log (`research.support_renewed`: task, refs, previous) | `test_low_renewal_tasks_are_bounded_per_approved_concept` (8 days: ≤ 2 renewal rows, exactly one ANSWERED = the head, renewed evidence ok each day, ≥ 8 renewals in the audit log, nothing OPEN) |
| **LOW** an OPEN renewal task lingers after a withdrawal | `watchlist_research.close_renewals`, called from every intake withdrawal of a research concept (`withdraw_unsupported`, the hand-off withdrawal, the refused-revision withdrawal) via `intake._close_renewals`: OPEN tasks with trigger `watchlist_gap:<gap>#…` are EXPIRED with `detail.closed` (why, at, concept task) and audited `research.renewal_closed` — not while another APPROVED concept rests on the same gap. Fresh evidence later opens a new question as before | `test_low_an_open_renewal_task_is_closed_with_the_withdrawal` (on 5f8c02aa: `watchlist_gap:3#renew:7` stays OPEN); `test_low_close_renewals_spares_a_gap_another_approved_concept_rests_on` |

Proof on 5f8c02aa (worktree, `test_r5_research_4.py` copied in): **0 passed / 6 failed**, each
on the asserted behaviour (rows stay `withdrawn`; no history; concept stays WITHDRAWN; no
bound; the OPEN renewal task lingers; no `close_renewals`).

## Changed expectations (stated, not weakened)
`test_r5_research_2.test_low_one_open_task_per_gap_refreshed_not_duplicated` and
`test_r5_research_3.test_h3_an_approved_concept_stays_approved_while_evidence_stays_fresh`
counted renewal task rows (3, and 5..10). Rows are now pruned by design, so the same counts
are asserted on the audit log (3 distinct renewals; 5..10), **plus** the new row bound
(exactly `RENEWAL_KEEP` rows, exactly one ANSWERED, the kept rows are the last renewals).

## Suites run (round 4)
`JOBS=4 SUITE_REGISTRY=0 PY=/tmp/venv/bin/python bash run_tests.sh` with SUITES =
test_r5_research_4 test_r5_research_3 test_r5_research_2 test_ws2_research_m2
test_w5_concept_intake test_w4_launchfix test_cert_mjs test_ws2_r3_source_timestamp
test_ws2_r4_kept_scan_facts test_ws2_r6_r7_watchlist_env_dedupe test_opus2_scan_evidence
test_radar: **12 of 12 suites passed, 181 tests passing, 0 failing**
(run record `artifacts/suite_runs/20261118T162050Z-3336.json`). Per suite:
r5_research_4 6, r5_research_3 7, r5_research_2 10, ws2_research_m2 7, w5_concept_intake 39,
w4_launchfix 32, cert_mjs 19, ws2_r3_source_timestamp 6, ws2_r4_kept_scan_facts 7,
ws2_r6_r7_watchlist_env_dedupe 5, opus2_scan_evidence 11, radar 32. With the venv from
`requirements.lock` + `requirements-test.lock`, `test_w4_launchfix` and the `test_cert_mjs`
veto-route test now run and pass (round 3's `httpx2` failure was that session's venv).
