# OPUS2 handoff: owner-queue races (P1-OWNER-QUEUE-RACES)

| Field | Value |
|---|---|
| Claim | `OPUS2-OWNER-QUEUE-RACES`, from `P1-OWNER-QUEUE-RACES` (INTEGFIX review LOW-3; offered on PR #3) |
| Branch | `opus2/p1-owner-queue-races`, cut from `claude/w4-INTEG8-next` `276a95a7` |

## The finding

INTEG8 serialised two owner-queue writers: `launch.readiness` and `etsy_ops.seed_owner_queue`.
Both use `release._serialise_owner_queue`. The review counted the others: **47 `OwnerAction`
insert sites across about 30 modules**, almost all of which read the open queue and then insert
what is missing, with no lock. Two concurrent passes both read "absent", and the owner sees the
same decision twice.

## The fix: one guard at the point every insert passes through, not 47 per-site edits

`ops/owner_queue_guard.py` is a SQLAlchemy `before_flush` listener, registered from `core/db`.
When a flush would insert an **open** `OwnerAction` that has a `requirement_key` (the model's own
identity for an action: "the queue de-duplicates on this"):

1. **It takes the same owner-queue lock.** On Postgres that is
   `pg_advisory_xact_lock(release.OWNER_QUEUE_LOCK)`, re-entrant within the transaction. On
   SQLite it is `BEGIN IMMEDIATE`. If the SQLite connection is already in a write transaction,
   it already holds the write lock and is serialised.
2. **Under the lock, it re-reads the open rows for those keys.** It drops a new row whose key is
   already open, whether from a concurrent pass that committed first or earlier in the same
   flush.
3. **Rows that the same flush closes (`done=True`) or deletes are not counted as open.** A writer
   that closes the old action and queues its replacement in one transaction keeps the
   replacement.

**What it leaves alone:** closed rows, rows with an empty key, and every update path. No writer's
decision changes. The two writers that already lock still lock exactly as before, because the
guard re-enters the same lock.

**Why not 47 per-site edits.** The central guard covers every present writer, and every future one
that inserts through the ORM. Per-site locking would need a forced-interleaving test per writer
and would be missed by the next new writer. If the integrator prefers explicit per-site locks,
this guard can stay as the backstop.

## Evidence

`tests/test_opus2_owner_queue_races.py`: 5/5.
- **The harness** holds every racing thread at a barrier right after its first `SELECT` of
  `owner_actions` (a `do_orm_execute` hook). Both threads read "absent" before either writes,
  which is the interleaving that duplicates.
- **A read-then-insert writer** queues **one** row.
- **The control:** the same harness with the guard removed queues **two**. So the harness
  reproduces the race, and the first test is not vacuous.
- **A real unlocked writer**, `etsy_ops.record_auth_needs_owner`, raced: one open `AUTH_KEY` row.
- **Close and replace in one flush:** the replacement is kept.
- **Keyless and closed rows are unaffected.** Two new rows for one key in one flush keep one.
- The suite is declared in `scripts/suite_final_segment.txt`, because it uses threads and
  timeouts (resume_runner F7).

**Regression: 115 suites.** That is every suite mentioning `OwnerAction`, `owner_queue` or
`owner_action`, plus `test_w4_owner_queue_race`, `test_deploy`, shadow and the guards. All exit
0 except three, each identical on the base `276a95a7`:
- `test_risk_matrix`: `KeyError('market-basket-medium')`.
- `test_v11_cc_views`: "mockups" in LAUNCHFIX's `policy_readings.py`.
- `test_w4_fmbatch1_provider_health`: `test_verify_reports_degraded_with_the_provider_named`.

**Not covered here:** a live Postgres concurrency test (INTEGFIX INFO-1). This sandbox has no
Postgres. The Postgres branch is the same advisory lock the two existing writers already take
in production.

## Review OPUS2F fixes (2026-11-01)

| Finding | Fix | Test |
|---|---|---|
| B-1 MED: the loser was expunged, leaving the caller a None id | the newcomer is merged onto the open row (action, reason, cost, minutes, consequence, blocks restated) and takes its id; a keeper inserted in the same flush hands its id over after the flush | `test_review_opus2f_b1_*` |
| B-2 LOW: re-keying a row onto an open key | the re-key is reverted to the previous key | `test_review_opus2f_b2_b3_*` |
| B-3 LOW: reopening a closed row beside an open one | the reopen is reverted (done stays True) | `test_review_opus2f_b2_b3_*` |
| B-4 LOW: Core inserts bypass the guard | stated in the module docstring; no current site uses one | — |
| B-5 recommendation: DB partial unique index | **proposed, not built**: it needs a data migration that first closes existing duplicates, which `core.migrate` deliberately refuses ("they need a human looking at them") | — |
| B-6 LOW: Postgres lock order | stated in the docstring: an inversion is broken by the deadlock detector (one job errors and retries), it does not hang | — |

`tests/test_opus2_owner_queue_races.py` 7/7. Regression on 115 suites: exit 0 except the three
base-owned failures above plus `test_v11_accounting_controller` and `test_w4_b2gate2`, which fail
identically on the base 8ea9e43b (month-end close / Etsy re-read timing on 2026-11-01).
`test_w4_wraptest` and `test_web_security` were cut off by a container restart and pass on rerun.

## Completion state

Implemented: yes. Independently reviewed, integrated, certified, deployed, production verified:
**no**.
