# Production cadence diagnosis — 2026-10-12T00:20Z (prod commit 0417f35)

Read-only. No POSTs, redeploys, restarts or variable changes.

## etsy.probe (last run 2026-10-11T12:00Z)
Root cause: #34 thrash-breaker **free-poll backoff**, not the queue or a lease.
- Every probe since 2026-10-10 returned the identical `HTTP 403 ... check ETSY_SHARED_SECRET`
  (`/api/audit?action=etsy.probe`). `_state_of` strips `at`, so 3 identical states → `identical_tail`.
- `/api/incidents`: `thrash:backoff:etsy.probe` opened 2026-10-11T14:04:50Z (level 1, factor 2).
- `/api/audit?action=ops.thrash` (every hourly sweep since): `etsy.probe factor 2 until 2026-10-12T02:04:50Z`,
  listed under `suspended`. `Scheduler.tick` skips `suspended_job_types` → 18:00 and 00:00 windows never enqueued.
- Expected to resume ~02:05Z (00:00–06:00 window). If the 403 persists, next backoff is factor 4 (24 h) … up to 32× (8 days).
- model.probe is not backed off because its outputs change (failed→ok, headroom_cad differs each run).

## ops.offsite_archive (no row tonight)
Not stopped: **enqueued and pending** in a backlog. `/api/queue/cadences`: job 12678 `pending`.
`/api/jobs`: 66 pending (oldest 12634), one worker running `creative.tournament` (funded model since 18:00Z →
creative work now runs). `ops.offsite_archive` is band `housekeeping` (lowest), so it waits; aging will lift it.
On previous nights the creative jobs were parked (model unfunded) so it ran at 00:01. Note: thrash
progress shows offsite `identical_tail: false`, so it is not backed off yet — but it would be after 3 identical failures.
`/api/offsite` now reports `configured: true`; job 12678 will be the first attempt since then.

## 16:25Z worker start
Owner-triggered redeploy of the same commit (deployment 7eb3fc08, created 16:25:07Z, replacing 047a1b44 from 16:06Z).
Logs: clean `Starting Container` / uvicorn startup; no crash. `worker_restarts: 0`.

## Laura
`laura.executive_tick` was backed off by the same mechanism on 2026-10-11 (level 5, factor 32, until 21:41Z),
lifted ~22:00Z. Not in LIVENESS_JOB_TYPES in 5ad94dd, b78f096 or w4-INTEG2.

## Proposed fix (this branch, not deployed)
Add `etsy.probe`, `model.probe`, `ops.capability_probes`, `ops.offsite_archive`, `ops.continuity` to
`swarm.orchestrate.LIVENESS_JOB_TYPES` (free probes whose purpose is to notice a fix; backups must not be skipped).
Regression test: `tests/test_cert_thrash.py::test_probes_and_the_offsite_archive_are_never_backed_off`;
the existing backoff test now uses `intel.gallery_analysis`. Whether `laura.executive_tick` should also be exempt
is a Laura-design decision left open.
Not in any pending candidate (5ad94dd, b78f096).
