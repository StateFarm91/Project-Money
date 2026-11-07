# Independent delta review: 677661ec "Clear stale supply stalls on measured recovery"

Scope: `git diff 83fe31d2 677661ec` only (flow_health.py +29/-3, test_w5_a7_supply_stall.py +40,
COORDINATION.json claim, CODEX_A7_SUPPLY_HANDOFF.md). Reviewed read-only in the detached worktree
/home/user/bl-runs/wt-rev-a7d. Nothing was committed or pushed. Mutations were reverted, and
`git status` is clean.

Scripts:
- repro: /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a7d/repro.py
- mutants: /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a7d/mut.py and mut2.py

Run each from `brambleloop/` with /home/user/bl-runs/venv-integ4/bin/python.

## Verdict: SHIP 677661ec

A7-1 is fixed. `concept_supply_stall` now walks the DONE `radar.scan` jobs that finished in
`[reading.at, now]`, newest first. A measured `stalled: False` clears the view. A measured
`stalled: True` re-reports the stall with that scan's counts. Unmeasured, malformed, failed or
dead scans are skipped. Both readers (Command Center `_stalls_loops` at
command_center/production.py:237, and readback `autonomy_loop` at ops/production_evidence.py:494)
go through this one function. No other reader of `radar.supply_stall` exists in `src/`
(grep found none).

The ways a recovery can be falsely claimed, or a stall hidden, all need concurrent scans, clock
skew between hosts, or a back-dated `as_of` that nothing in `src/` enqueues. Each one
self-corrects at the next scan (cadence 6 h, runtime/worker.py:609). None of them is a gate or
verify impact. The main weakness is test coverage: most guards survive mutation. Follow-up tests
are recommended, but they do not block shipping.

## Findings

### D-1 LOW: a recovery is ordered by finish time, not measurement time (concurrent-scan race)
flow_health.py:387-389. The scans are ordered by `Job.finished_at`. Scan A can measure supply
(healthy), then spend longer in `expansion_plan` and the enqueues. Meanwhile drafts land, and
scan B measures a stall, writes the reading and finishes. If A finishes after B, A's stale
healthy measurement wins and the stall is hidden until the next scan.
Repro (repro.py R1): a stall reading from the real handler, then a DONE healthy scan with
`finished_at=utcnow()`. `concept_supply_stall` returns `None`.
Fix idea: put a `measured_at` in `concept_supply` (pipeline.py `_record_supply_stall`), then
order and filter by that.

### D-2 LOW: clock skew between worker hosts can claim or hide a recovery
flow_health.py:389. `reading.at` is the writer's `utcnow`, `finished_at` is the completing
worker's `utcnow` (queue/durable.py:534), and `now` is the reader's clock.
- **False recovery (R2).** A worker running 60 s fast stamps a scan that really finished 30 s
  before the reading as `at+30s`. Read 2 min later, the result is `None`.
- **Hidden stall (R3).** A re-stall stamped in the future by a fast clock is excluded by
  `<= now`. An earlier healthy scan then hides it, and the result is `None` until the reader's
  clock catches up.

This only matters with multiple hosts (Postgres) and scans seconds apart. When the skew goes the
other way, the code is conservative: it keeps showing the stall.

### D-3 LOW / informational: a scan for another period can clear the current period's stall
flow_health.py:387-397. The query does not compare `scan.inputs.as_of` with `row.period_key`.
- R4: a DAY2 stall is cleared by a healthy fixture scan with `as_of=DAY1`.
- R7 uses real handlers. A DAY1 `selection_all_drafted` stall is cleared by a back-dated
  `as_of=2026-03-01` scan, whose seasonal selection contains undrafted concepts.

No `src/` producer enqueues `radar.scan` with `as_of`; only tests do. So this is informational.
That replay does queue radar.score for real undrafted concepts, so it is arguably genuine
supply. There is no tenant dimension in this code base, so the cross-tenant case does not apply.

### D-4 LOW-MEDIUM: most new guards are not protected by the tests
test_w5_a7_supply_stall.py, run with each mutant applied to flow_health.py:

| mutant | result |
|---|---|
| M1 drop `status == DONE` | SURVIVED (near-equivalent: `fail()` never writes outputs) |
| M2 drop `finished_at >= at` | SURVIVED, and it is **not equivalent** (see below) |
| M3 drop `finished_at <= now` | SURVIVED |
| M4 drop `measured is True` | SURVIVED (equivalent today: the error path writes no `stalled`) |
| M5 drop `type(stalled) is bool` | SURVIVED |
| M4+M5 | KILLED, but only by a KeyError crash |
| M8 `at is None` returns the reading | SURVIVED |
| M9 2-day freshness removed | SURVIVED (A7-2 from the prior review is still open) |
| M11 a later stall falls back to the old reading's counts | SURVIVED (the test only asserts `is not None`) |
| M12 accept any falsy `stalled` | SURVIVED |
| M6 ascending order | KILLED |
| M7 always clear | KILLED |
| M10 no scan loop | KILLED |

Why M2 matters (repro.py R8): a healthy scan runs, then a stalling scan writes the reading and
dies before `complete()` (lease lost or crash). With the guard, the stall stays visible
(`True`). With M2, the earlier healthy scan clears it (`False`).

Suggested tests:
- R8 (crash after the reading).
- A DEAD or FAILED scan whose outputs look healthy.
- `stalled: "false"`.
- Freshness older than 48 h.
- Assert the re-stall counts and `at` come from the newest scan.

### D-5 INFO: payload and period from a scan
flow_health.py:400. When a scan has no `as_of`, `period` falls back to the reading's
`period_key`. That is harmless, because a newer date writes a newer reading. `undrafted_pool`
is an int in both branches, so the shape is consistent.

## Not made worse
The refused-draft retention risk is noted in the handoff document. This commit does not touch
retention or draft keys, and it only reads scans from the last 2 days, so it is not worse.

## Checks that hold
- Unmeasured scans (R6, test), malformed `stalled` values (R6) and DEAD scans (R5) never clear
  the stall.
- A scan that finished before the reading is excluded on a single clock (R8).
- A same-day re-stall is re-reported (test).
- The result survives reopening the database (test).
- A missing `at` now returns None instead of a perpetual reading.

## Suites (venv-integ4, run one at a time)

| suite | result |
|---|---|
| test_w5_a7_supply_stall | 6/6 OK |
| test_w4_readback_evidence | 23/23 |
| test_w4_board | exit 0 |
