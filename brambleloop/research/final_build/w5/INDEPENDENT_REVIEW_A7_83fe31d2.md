# Independent review: A7 P0-SUPPLY-STALL at 83fe31d25d1d6f85b6d03a276191642eca4d985d

Branch origin/claude/w5-A7-supply-stall, one commit on base claude/w5-INTEG1 7c42e706 (the merge-base is exactly 7c42e706).
Reviewed read-only in a detached worktree; nothing was pushed, committed or deployed.

## Verdict: DO NOT SHIP (as is)

The core mechanism is correct. It is deterministic, it is deduplicated per period by a DB
unique constraint, it queues nothing, and `draft:<slug>` still refuses a duplicate cir.draft.
The problem is in the visibility path. Once supply comes back, the Command Center and the
readback evidence keep showing "STALLED: no new concept supply" for up to 48 h, because
nothing ever clears the reading (A7-1). That is exactly the "false stall when supply exists
via approved intake" case the brief asks about. The fix is about 10 lines and is described
under A7-1. With it, plus a freshness test, this would be SHIP.

## Findings

### A7-1 MEDIUM: a stale stall reading stays visible after supply returns (false DEGRADED)
`flow_health.concept_supply_stall` returns the newest `radar.supply_stall` reading that is
less than 2 days old, judged by insert time. Readings are written only when a scan stalls.
No "cleared" reading exists, and a later scan that finds supply never updates the existing
row, because the period dedup blocks it. So after any of these:

- the intake approves a concept,
- the A4a ideation produces one and it is approved,
- a draft job is removed or cancelled,

the next scan reports `stalled: False`, yet the Command Center Production `stalls_loops`
stays DEGRADED with "STALLED: no new concept supply (pool_exhausted)" for up to 48 h.
`autonomy_loop.concept_supply_stall` is wrong in the same way.

Repro (script `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a7scripts/repro.py`, R1):
1. Mark the whole pool drafted, then scan DAY1. The reading is written.
2. Delete two `draft:` jobs (supply is back), then scan DAY1 again. The scan returns
   `{'undrafted_selected': 1, 'stalled': False, 'recorded': False}`.
3. `concept_supply_stall(db)` still returns
   `{'reason': 'pool_exhausted', 'drafted': 34, 'undrafted_pool': 0, ...}`.

Impact: only the owner-facing dashboard is wrong. There is no gate or verify impact (see the
next section). Still, it contradicts the honesty non-negotiable.

Fix: have `concept_supply_stall` look at the newest completed `radar.scan`, and return None
unless its `outputs.concept_supply.stalled` is True. Alternatively, record a non-stalled
reading/marker that supersedes the stall. Either way, add a test for the case.

### A7-2 LOW: the 2-day freshness window is untested
Mutant M4 (freshness check disabled) survives the A7 test.

### A7-3 LOW: the audit can be lost on a crash
The reading commit and `ctx.audit("radar.supply_stall")` are separate steps. If the worker
dies or loses its lease between them, the re-run sees the existing reading and returns
`recorded: False`. The period then has 1 reading and 0 audits, which breaks the "one
reading + one audit" claim. A fix is to write the audit row in the same session as the
reading.

### A7-4 LOW / informational: the stall ignores in-flight research proposals
A4a proposals (3dc3e68c, `ideation.investigate` -> `intake.attach_proposal`) count as supply
only once `radar.intake` approves them, because `pool_with_intake` = POOL + approved rows.
So A7 records a stall while an ideation brief or a pending proposal is in flight. That is
correct, since nothing is draftable now, but the payload gives no context. Suggestion: add
open-ideation and pending-proposal counts to the payload. Combined with A7-1, a concept
that A4a produces and that gets approved the same day still shows as stalled for 48 h.

### A7-5 LOW / informational: "drafted" means only `draft:<slug>`
- `redraft:{slug}:{fp}` (release.py:5055) is a recovery of an existing product and never
  new supply, so ignoring it is correct.
- creative/intake.py:807 and :1122 use the same `draft:{slug}` key, so they are counted.
- A radar concept already launched under a retired alias (D-W5-7, `launch0.radar_concept_for`)
  without its own `draft:<concept>` key counts as undrafted supply. That is consistent with
  radar.score, which would try to draft it, so this is not an A7 regression.

### A7-6 LOW / informational: other gaps the stall does not cover
- **Scores that never promote.** An undrafted selected concept whose radar.score never
  promotes (gate or score) is "supply" to A7, so a stall made of only non-promoting scores
  goes unreported. This is outside A7's claimed scope.
- **Period date.** The period is `_scan_date` = `date.today()`, which is the process's local
  timezone. This is pre-existing. The host is UTC (verified), so the period equals the UTC
  date. A non-UTC host would shift the boundary.
- **No-op judge.** `did_no_work` still counts a stalled scan as useful work via `selected`.
  This is pre-existing and unchanged.

## Checks that hold

- **Dedup under concurrency.** The existence check is backed by
  `UniqueConstraint(kind, period_key)` (`uq_operating_reading`). The IntegrityError on commit
  is rolled back by `Database.session` and caught.
  - R2: 6 threads hitting `_record_supply_stall` on the same period gave
    `[True, False x5]`, 1 reading and 1 audit.
  - Mutant M1b (existence check removed, constraint kept) survives. That is an equivalent
    mutant because the constraint still guards the period.
- **New period.** A new scan date writes a new reading.
- **No duplicate drafts.** No duplicate cir.draft was queued in the test (all radar.score
  jobs ran; the draft set was unchanged).
- **Approved intake counts as supply.** `steered` is derived from `pool_with_intake`.
- **No gate or verify impact.**
  - `stalls_loops` is consumed only by the `/production` owner view.
  - `autonomy_loop` is a SECTIONS entry, not a check.
  - `CHECK_NAMES` and the `checks()` projection are unchanged; the test asserts this.
  - No publish gate reads any of these.
- **Response shape.** The changes only add keys: `concept_supply` in radar.scan outputs, an
  optional `supply` argument, a `concept_supply_stall` key, and an `operating_readings`
  source when stalled. The consumer suites pass.
- **No test weakened.** The diff touches tests only by adding test_w5_a7_supply_stall.py,
  plus one line in suite_final_segment.txt.

## Suites (venv-integ4, worktree at 83fe31d2, run one at a time)

| suite | result |
|---|---|
| test_w5_a7_supply_stall | PASS 4/4 (includes the final edit the original worker never re-ran) |
| test_w4_readback_evidence | PASS 23/23 |
| test_w5_inventory | PASS (0 failed) |
| test_w4_board | PASS |
| test_radar | PASS |
| test_w5_concept_intake | PASS (0 failures) |
| test_swarm_runtime | PASS |
| test_w3_k11_authority | PASS (0 failing) |
| test_launch0 | PASS |
| test_shadow (last, alone) | SHADOW_RESULT |

## Mutants (each run against test_w5_a7_supply_stall)

| mutant | result |
|---|---|
| M1 remove period dedup (existence check + IntegrityError guard) | KILLED |
| M1b remove the existence check only | SURVIVES; equivalent (the unique constraint still dedups) |
| M2 count all slugs as drafted | KILLED (2 tests) |
| M3 write the reading when supply exists | KILLED (2 tests) |
| M4 ignore the 2-day freshness | SURVIVES (A7-2) |
| M5 Command Center not DEGRADED on stall | KILLED |
| M6 swap the reason labels | KILLED (3 tests) |

## Merge cleanliness

| merge | result |
|---|---|
| vs origin/claude/w5-INTEG1 (7c42e706) | clean; it is the merge-base, so this is a fast-forward |
| vs claude/w5-A5-correction-loop 717c7925 | clean (git merge-tree); the merged pipeline.py parses |
| vs opus2/a4a-research-to-concept 3dc3e68c | CONFLICT, trivial: only in `brambleloop/scripts/suite_final_segment.txt`, where both append one test line. Keep both lines. pipeline.py auto-merges: A7's `_record_supply_stall` call sits before the radar.score loop, and A4a's coverage-handoff enqueue comes after it. |
