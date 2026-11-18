# Review request — eng/watchlist-cadence, round 2 (review of 77795758)

Branch `eng/watchlist-cadence`. Fix commit **a7293520** (on top of 2fe7f5d). This file is
committed on top of it. Nothing was deployed. No Railway, production, secrets, Etsy or spend
was touched.

## (A) MEDIUM — the breaker's probe-lift did not hold. Fixed.

**Cause (reproduced).** `thrash_sweep` re-observes every DEAD or paid job in its 72 h window
on each hourly sweep. The DEAD `mjs.scan` runs that failed on the refused key kept tripping
the detector. After the OK probe, the sweep rewrote the open incident's suspension with
`since=now` and `gate_refused=False`, and `gate_lifted` then refused the lift for good.

**Fix (`swarm/orchestrate.py`, `thrash_sweep`).** This takes the reviewer's second option:
exclude trips that predate the gate change. A run of a credential-gated job type is no
longer an observation when it ended while the gate was refused and the gate has *genuinely*
changed since (`gate_changed_since(gate, run.finished_at)`). The open incident is then left
untouched: it keeps its original `since` and `gate_refused=True`, so the lift holds. Runs
that end after the fix are still observations. Three identical failures with a working key
trip the breaker, and that suspension (`gate_refused=False`) does not lift on later OK
probes. The lookups are memoised per (gate, time) within a sweep and only touch gated job
types.

**Tests (`tests/test_watchlist_cadence.py`).**
- `test_a_breaker_suspension_lifted_by_the_probe_is_not_rewritten_by_the_next_sweep`: the
  reviewer's repro. Three DEAD `mjs.scan` runs on a refused key trip the breaker. After an OK
  probe the job type is not suspended. Sweeps at +1 h, +2 h and +5 h stay lifted. The
  incident keeps `gate_refused=True` and its original `since`. At +80 h, both the sweep and
  `suspended_job_types` show it lifted.
  On 77795758 it **FAILS** (`suspended: ['mjs.scan']` after the first sweep), on SQLite and on
  PG16. It passes on a7293520.
- `test_the_same_loop_after_the_fix_still_trips_the_breaker` is the control. Three new DEAD
  runs after the OK probe re-suspend the job type, and a routine OK probe afterwards does not
  lift it.

## (B) MEDIUM — the "genuine change only" guard was untested. Tests added.

- `test_only_a_genuine_gate_change_lifts_a_backoff` covers `suspended_job_types` and
  `gate_changed_since`. These must not lift: OK→OK, refused→refused, OK→refused→OK, and no
  probe in force → OK. This must lift: refused→OK. It also covers an out-of-order case: the
  newest-written probe is an OK row stamped *before* the backoff, while a refusal was in
  force at the backoff (a backfilled or clock-skewed write). That must not lift.
- `test_the_sweep_still_backs_off_an_unchanged_poll_across_routine_ok_probes` covers the
  sweep's side. Identical runs that are not gated, with the key working and a routine OK
  probe after them, are still backed off.

**Mutation results.** Each mutant was applied to `orchestrate.py` at a7293520 and the whole
file was run:

| mutant | change | killed by |
|---|---|---|
| M2 | drop `not _probe_refused(then.detail)` (also tried: drop the whole in-force check) | `only_a_genuine_gate_change…`, `sweep_still_backs_off…` |
| M3 | drop `ok_at <= since` | `only_a_genuine_gate_change…` (the out-of-order case; with in-order writes M3 is equivalent) |
| M4 | drop "latest probe is OK" | `a_legacy_backoff…`, `only_a_genuine_gate_change…` |
| M5 | remove the new (A) exclusion | `a_breaker_suspension_lifted…not_rewritten…` |

## LOW — production magnitude

`test_production_magnitude_32x_backoff_driven_by_the_sweep_lifts_and_cadence_resumes` sets
up the old build's unmarked refused runs and its level-4 backoff while the key is refused.
The hourly sweep itself raises the backoff to level 5. The test asserts factor 32
(= `MAX_BACKOFF_FACTOR`) and an `until` of at least 32 × 6 h. The owner then fixes the key.
The scan is enqueued in the next window and reads all 7 shops. For 24 h after that, hourly
ticks and hourly sweeps run the scan in every 6 h window, and the scan is never suspended
again.

This test passes on 77795758 too. The base already handled this magnitude; what was missing
was the evidence at production's size.

## Results

All of these ran at a7293520.

- `tests/test_watchlist_cadence.py`: **14/14 OK** on SQLite and **14/14 OK on PG16**. For
  PG16, a disposable local cluster gave each `_db()` a fresh database through a scratch
  harness; the test file itself was not changed. Against 77795758 (worktree, new test file
  copied in), exactly 1 of 14 fails on both SQLite and PG16: test (A).
- `JOBS=2 SUITE_REGISTRY=0 SUITES="test_shadow test_cert_wiring"`: **26 passing, 0 failing**
  (test_cert_wiring 16/16, test_shadow 10/10). Duration 981 s, run to completion. Run record
  `artifacts/suite_runs/20261118T162911Z-1926.json` (passed).
- Per-tick escalation cost: I re-ran each suite once with `Scheduler.tick` and
  `scheduler_readback.maybe_escalate` timed (runpy wrapper; code unchanged).

  | suite | wall | ticks | escalation calls | escalation time |
  |---|---|---|---|---|
  | test_cert_wiring | 847 s | 4 | 4 | 0.056 s |
  | test_shadow | 987 s | 2 | 2 (1 ran, 1 throttled) | 0.011 s |

  Both passed again under the wrapper. The escalation costs nothing measurable there.
- The branch's own suites and the adjacent ones (watchlist, readback, thrash, mjs,
  competitor scans, research→concept, spend wiring): **18 suites, 202 passing, 0 failing**,
  663 s. Run record `artifacts/suite_runs/20261118T162911Z-1954.json` (passed). The suites
  were: test_watchlist_cadence, test_w4_readback_evidence, test_cert_thrash,
  test_w4_intelrec_watchlist, test_cert_mjs, test_opus2_scan_evidence, test_w4_close5_rows4,
  test_ws2_r1_competitor_scans, test_ws2_r3_source_timestamp, test_ws2_r4_kept_scan_facts,
  test_ws2_r6_r7_watchlist_env_dedupe, test_a4a_low_fixes, test_w5_a4a_research_to_concept,
  test_w4_integ3_defects, test_w4_auto_spend_wiring, test_w4_c10_paid_media,
  test_cert_growth_seasonal, test_cert_claude_independence.

These were targeted runs, not the full suite. I used `JOBS=2` instead of 4 because the two
runs shared a 4-core container.

## Residuals / for the reviewer

- The throttle in `maybe_escalate` is keyed on the caller's `now`. In hourly simulations it
  runs on every tick; in production `Scheduler.tick` is called with wall time. This is
  unchanged from round 1.
- `retry_allowed` (manual or recovery re-drive of a DEAD job) still reads only
  `_hypothesis_changed`, not the gate. A re-drive of a DEAD gated run after the key fix is
  allowed only once the incident is resolved or the handler changes. Cadence enqueueing is
  not affected. Out of scope for this round, so not changed.
- Round 1's `watchlist_cadence.md` still contains its `SUITE_RESULTS_PLACEHOLDER` and
  `FINAL_SHA_PLACEHOLDER`. This file supersedes those for the current head.
