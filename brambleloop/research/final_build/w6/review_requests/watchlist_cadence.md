# Review request — eng/watchlist-cadence

Branch `eng/watchlist-cadence` from `origin/claude/w6-INTEG1` (e4c442c). Nothing deployed;
no Railway, production, secrets, Etsy or spend touched. Final SHA: see the end of this file.

## Production fact

Build ea3aacc7. Etsy refused the app key from 2026-10-07 until the owner fixed it at
2026-11-18T13:39Z (`etsy.probe` OK since). The anchor (`mjs.scan`, 2-hourly) resumed. The
seven other mandatory watchlist shops (`intel.watchlist_scan`, 6-hourly, market_radar)
were last attempted at 2026-11-17T20:03Z and were still `credential_refused` at 15:10Z.
`scan_all` writes `last_attempt_at` on every run, so the job had not run at all.

## Root cause (from the code, reproduced in a test)

1. **Free-poll backoff (primary).** `swarm.orchestrate._free_poll_backoff` (run by the
   hourly `ops.thrash` sweep) backs off any cadence whose last three DONE outputs are
   identical. The scan's refused branch returned exactly the same outputs every run:
   `{"ran": False, "observed": 0, "outages": 0, "network_calls": None, "work_done": 0}`.
   Its audit row was identical too, so it never counted as new evidence. Each new identical
   run doubled the factor, capped at 32: 32 × 6 h = 8 days. The backoff lifts only when a
   run shows progress, and the scheduler would not enqueue one. Nothing about the owner's
   fix (a successful `etsy.probe`) reached it.
   `mjs.scan` escaped because its refusal text embeds the probe's `at`, so its "state"
   changed every probe. That explains why only the anchor recovered.
2. **Per-shop backoff (secondary).** `watchlist.scan_member` defers a shop in
   `credential_refused` with `consecutive_failures > 0` for `backoff_for(fails)` (up to
   7 days). That interval is measured from `last_attempt_at`, which the refused branch keeps
   refreshing. After the fix, shops whose own reads had been refused (before the probe
   caught the refusal) would still have waited up to 7 days.
3. **Ruled out.** Department block: `mjs.scan` (same department, market_radar) ran, so
   market_radar was not blocked. Idempotency: `cadence_key` is per 6 h window, and a
   `DuplicateJob` only means the window already ran. `_legacy_ran_recently` applies to
   periods ≥ 24 h only. The SUSPENDED breaker reads DEAD or paid jobs only, and the scan is
   CA$0 and never raises. Lane admission does not explain a job that was never *enqueued*.
   `last_attempt_at` is written before any lane decision would matter.

## Fix

`swarm/orchestrate.py`
- `gated_noop(outputs)`: outputs carrying `credential_refused` (the existing convention
  across observe/serp/taxonomy/shop_sync) mark a CA$0 no-op that waits for its probe.
  `_progress` does not observe it at all (it is counted as `gated_runs`), so it can never
  build an identical tail.
- Suspensions now record `since` and their gate (`gated_on`, `gate_refused`).
  `gate_lifted` / `gate_changed_since`: a BACKOFF or SUSPENDED of a credential-gated job
  type (`CREDENTIAL_GATED_JOB_TYPES`) lifts once the probe that was in force when it was
  recorded was refused and the newest probe succeeded after it. Production's standing
  backoff predates the fix and has no gate recorded; it is judged by the probe in force at
  the incident's `at`.
- The breaker is kept for real spend loops. A suspension recorded while the gate was open
  (`gate_refused: False`) never lifts on a probe. Test
  `test_a_paid_loop_on_a_gated_job_type_still_trips_and_stays_suspended` checks this.
- The sweep does not re-arm a lifted backoff from observations that predate the input
  change (`input_changed_since` in `_free_poll_backoff`). It neither bumps the level nor
  writes a fresh one; the next real run resolves it.
- Task 4: `UPSTREAM_INPUTS` covers `radar.concept_intake` (research.investigate,
  intel.opportunity_review, intel.watchlist_scan) and `intel.watchlist_compare`
  (intel.watchlist_scan, mjs.scan). A BACKOFF lifts once an upstream job made progress
  (`made_progress`: not gated, not deferred, `work_done > 0` or `ran is True`) after the
  backoff. `intel.watchlist_compare` is deliberately *not* an intake input, because it
  reports `work_done=1` on every run.

`intel/watchlist.py`, `runtime/intel_ops.py`
- The refused branch returns `credential_refused: True, gated_on: "etsy.probe"`, and the
  handler propagates both.
- `_credential_fixed_since`: a shop's `credential_refused` backoff lifts on a successful
  `etsy.probe` newer than its last attempt. `source_outage` and `not_accessible` keep their
  backoff.

## Visibility and escalation (task 3)

`ops/scheduler_readback.py` (new)
- `scheduler_block`: suspended job types (kind, why, until, factor, incident), blocked
  departments, and per cadence the agent, department, period, `last_enqueued_at`,
  `last_status`, `last_finished_at`, `next_window_at` and `skipped_because`.
- `shop_not_attempted`: the first matching cause, as a fixed code. In order:
  scheduler_backoff/suspended, department_blocked, cadence_not_enqueued,
  enqueued_not_executed, job_failing, credential_refused_waiting_for_probe, shop_backoff,
  adaptive_not_due, attempting.
- `escalate_unattempted`: a mandatory watchlist shop (all 8, anchor included) not
  attempted for more than 2× its cadence gets a **P1** incident,
  `watchlist.not_attempted:<key>`, whose summary names the cause. It is restated while the
  condition holds and resolved, with the reason, once the shop is attempted. An
  `adaptive_not_due` cause is never escalated. A shop that has never been attempted is
  scan_evidence's NEVER state and is not escalated here. Called from `Scheduler.tick`
  (try/except, throttled to 15 min per database per process). Registered in
  `incident_lifecycle.REMEDIATION`.

`ops/production_evidence.py` (`/api/readback/evidence`)
- New `scheduler` section: the block above plus `unattempted_mandatory_shops` (alias,
  hours since, limit, cause).
- Each `competitor_scans` row carries `not_attempted_because` (code, detail, job_type,
  until, incident), or None when the shop was attempted within its cadence.
- Privacy: no shop names (aliases only, asserted by the test), no operator block reasons,
  no incident text.

## Tests

`tests/test_watchlist_cadence.py` (new, 9 tests, standard header, OK lines, no pytest).
Run against the **base tree** (worktree at origin/claude/w6-INTEG1 with the test copied in),
8 of 9 FAIL. The one that passes on base is the guard that the spend-loop breaker is kept.
All 9 pass on the branch.

| test | before | after |
|---|---|---|
| days_of_refused_runs_do_not_silence_the_scan_after_the_key_is_fixed (4 days simulated: hourly ticks, hourly sweeps, 6-hourly refused probes, then fix, next window) | FAIL (backoff stands) | OK (enqueued, ran, observed all 7) |
| a_refused_credential_no_op_is_never_backed_off_as_a_thrashing_poll | FAIL | OK |
| a_legacy_backoff_written_before_the_fix_lifts_on_a_successful_probe | FAIL | OK |
| the_hourly_sweep_does_not_rearm_a_lifted_legacy_backoff_before_the_scan_runs (+ control: still refused → still backs off) | FAIL | OK |
| a_paid_loop_on_a_gated_job_type_still_trips_and_stays_suspended | OK | OK |
| the_readback_names_the_scheduler_hold_and_each_shop_says_why | FAIL | OK |
| a_mandatory_shop_silent_for_twice_its_cadence_raises_a_p1_naming_the_cause (then resolves after the fix) | FAIL | OK |
| concept_intake_and_compare_backoffs_lift_when_their_input_changes | FAIL | OK |
| shop_backoff_from_refused_reads_lifts_once_a_probe_succeeds (outage keeps its backoff) | FAIL | OK |

Suites (targeted; never the full suite), `JOBS=4 SUITE_REGISTRY=0`, `PY=/tmp/venv/bin/python`
(requirements.txt + requirements-test.lock):

SUITE_RESULTS_PLACEHOLDER

## Residuals / for the reviewer

- The backoff lift reads `AuditLog` rows for `etsy.probe` (latest; probe in force at a
  time; ≤ 200 rows of upstream jobs). Each `suspended_job_types` call costs O(open thrash
  incidents) small queries.
- `Scheduler.tick` now also runs the escalation (throttled). Every path is wrapped, so a
  failure there never stops scheduling. The result is on `Scheduler.escalation`.
- `UPSTREAM_INPUTS` is an explicit map for this department's family. `concept_intake`'s
  family-variation inputs (certified catalogue, orders) are not in it, so a backoff there
  lifts on research/opportunity/scan progress or on expiry (≤ 32 × 6 h).
- After deploy, the production backoff `thrash:backoff:intel.watchlist_scan` stays *open*
  but lifted. The first real scan's changed outputs resolve it on the next sweep.

Final SHA: FINAL_SHA_PLACEHOLDER
