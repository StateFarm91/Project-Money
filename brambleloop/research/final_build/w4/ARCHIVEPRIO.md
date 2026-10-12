# W4-ARCHIVEPRIO: the continuity proof and the offsite archive cannot be starved (#51)

Branch `claude/w4-ARCHIVEPRIO`, based on `origin/claude/w4-INTEG2` 534f27a. No production change.

## Defect (production, 2026-10-12)

`ops.offsite_archive` job 12678 was enqueued at about 00:01Z and still had not run at 08:20Z.
`/api/offsite` `last_archive` still showed 2026-10-11.

The cause has three parts:

1. **Band.** Both `ops.offsite_archive` and `ops.continuity` sat in `housekeeping`, the lowest
   band (95).
2. **Backlog.** The pool had a single worker, with about 66 older exploration and
   new-opportunity jobs (`creative.tournament` etc.) ahead of the archive.
3. **Aging.** Bounded aging (`queue/durable.py`, `AGING_CAP` 200) gives every waiting job
   credit for its wait. An older low-band backlog therefore keeps out-ranking a fresh daily job
   for as long as the backlog exists. A job enqueued daily never becomes the oldest, so it
   never runs.

## Fix (root, not a production tweak)

`swarm/orchestrate.py` `JOB_BANDS` now puts `ops.offsite_archive` and `ops.continuity` in the
protected `truth_defect` band. These two jobs are the system's own claim that its state survives
losing the database or the provider: `ops/assurance` reads them as `offsite_backup` and
`rollback_baseline.restore_proof`.

That is the same reason liveness checks (`ops.health`, `ops.heartbeat`) and probes
(`model.probe`, `ops.capability_probes`) are in this band. `JobQueue.claim` orders the
protected tiers before all ordinary work, whatever the stored priority or age.

Customer work (`customer_incident`) still comes first. Job 12678, already queued with priority
95, is claimed first after the deploy, because the tier comes from the job type.

`etsy.probe` was left in `benchmark_change`. Its band is a recorded decision ("a read never
claims ahead of a customer or a truth defect"). The model/vision probes are already protected.

## Acceptance evidence (tests through the shared slot)

**`tests/test_w4_archive_priority.py`: 4/4.** The tests:

- A fresh archive and a continuity proof, enqueued the way the scheduler does, are claimed
  before a 66-job backlog that is 30 h old.
- An archive left at the old stored priority 95 is still claimed first.
- Customer work still comes before the archive.
- The band membership is as stated.

**The test is not vacuous.** Run against the unchanged INTEG2 `src` (85ec5d0), all 4 fail. The
backlog's `creative.tournament` jobs are claimed first, which reproduces production.

**Regression:**

| test | result |
|---|---|
| `test_protected_bands` | 7/7 |
| `test_cert_residue` | 6/6 |
| `test_v11_wiring` | 15/15 |
| `test_cert_growth_ops` | 14/14 |
| `test_cert_improve_wave` | 24/24 |
| `test_cert_orders` | 24/24 |
| `test_w3_laura_core_wiring` | 7/7 |
| `test_vacuity` | 8/8 |

## Rows

- **Build 2 #51** (offsite storage): its archive now runs within its daily window once this is
  deployed. It closes when production `/api/offsite` shows a same-day `last_archive`.
- **F-628 / F-697** (continuity): advanced, through the same daily archive.

Remaining for those rows: the owner `offsite_storage` gate, where it still applies.
