# LISTREL (2026-10-26): listings release, certified

Integrator: W-INTEG5. **No deploy was made.** Production is 15800536, the first-sale release whose
source is b997efd; it was read by `ops/deployed_sha.py` at 2026-10-26.

## Certified candidate

| | |
|---|---|
| Candidate (suite SHA) | **`09acd42507d744524206e6cdfa45e37d9eeeed66`** (`claude/w4-LISTREADY` head; frozen as `claude/final-candidate-09acd42`) |
| Deploy head | **`051dbee2`** = 09acd42, then the release record commit 06778183, then the DEPLOYED_HISTORY entry for 15800536. Records only: the deployable tree digest is unchanged. |
| Full suite | run `20261026T084131Z-7491`: venv-integ4, JOBS=3, REQUIRE_CLEAN, 681 suites, 8299 s. **TOTAL PASSING 9112, suites failing 0, `release_eligible: true`** (`evidence_LISTREL/20261026T084131Z-7491.{json,log}`) |
| deploy_guard record | `brambleloop/release/RELEASE_09acd42507d744524206e6cdfa45e37d9eeeed66.json`, tree_sha256 `367671368aa3e6db…` |
| `DRY_RUN=1 sh ops/deploy.sh --deployed 15800536…` | forward **ALLOW**, and its built-in rollback rehearsal **ALLOW** (`evidence_LISTREL/dryrun_09acd42.txt`) |
| Rollback rehearsal | `DRY_RUN=1 ops/deploy.sh --rollback-to 15800536 --deployed 051dbee2` → mode rollback, **ALLOW**, reasons [] (`rollback_09acd42.txt`) |
| Migration | `evidence_LISTREL/pg_migration_output.txt`, PostgreSQL 16:
| | - from 1580053, +2 tables at boot (`launch_review_batches`, `launch_review_calls`), and no existing column changed;
| | - the second boot is a no-op;
| | - 1580053 and b931d17 both boot the upgraded schema cleanly.
| | Schema is unchanged from 8d520ed to 09acd42: no model or table edits. |

## Path to green

| Freeze | Result | Root cause | Fix |
|---|---|---|---|
| 8d520ed | 4 failing | decision_index stale; F-542 scanner false positive on `launch_review.activate`; board F-498 closure names a renamed test; cert_wiring drain limit | regenerate the index; rename to `open_batch`; regenerate the board (LISTREADY) |
| d69a3ec | 1 failing (cert_wiring: 267 jobs in 1237 s; 276 in 1200 s when run alone) | the host ran 1.5-1.8x slower. b931d17 code also failed. The full drain measured 1220 s (`cert_wiring_timing/README.md`) | owner approval 2026-10-25: limit 1525 s for that test only (D-W4-CERTWIRING-LIMIT); no assertion changed |
| 82a3b7a | 4 failing; cert_wiring passed | the calendar: Christmas windows closed on 10-21, and a trailing 30-day window. The same 4 failed on b931d17 code. Production behaves correctly | `tests/pinned_clock.py` pins the 4 files to 2026-10-20T12:00Z with a clock that keeps ticking; no assertion changed |
| **09acd42** | **0 failing** | | |

## Recorded, not fixed

- **The duplicate `visual.rnd.cycle`.** It runs twice: once from the 6-hourly cadence and once from the
  generator acting on `next_work`. `next_work` keeps listing green items that a cycle could not act
  on. This is bounded by date-scoped idempotency keys and costs CA$0, with no network call and no
  paid execution. It is a later fix in `next_work`.
- **DEPLOYED_HISTORY lacked 15800536.** The first-sale deploy never appended it. W-INTEG5 appended it
  from the observed `/api/status` read, noting that the operator holds the deploy evidence. Without
  that entry no rollback to 15800536 could execute.

## Rollback

- **Command:** `ops/deploy.sh --rollback-to 15800536 --reason "<owner's reason>" --deployed <deployed>`.
- **Effect:** it pushes a commit carrying exactly 15800536's tree on top of the deployed commit.
- **Data:** the 2 `launch_review` tables stay. Older code ignores them; the proof is above.
