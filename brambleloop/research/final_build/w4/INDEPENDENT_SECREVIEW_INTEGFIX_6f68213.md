# Independent security & integrity review — release-integrator changes on `claude/w4-INTEG8-next` @ 6f68213b

Reviewer: independent (Claude Code), 2026-10-31 UTC. Scope: only the integrator's own commits
bcbe391b, f259afe4, 282e47ce, 210aa9f8, the conflict resolutions in 98904d86 and 0b88aebc,
and f4c3899b. The merged branches themselves were reviewed elsewhere and are not re-reviewed.

## Verdict: **SHIP**

No Critical, High or Medium findings. Three Low findings (one is pre-existing and outside the
reviewed commits) and two informational notes. None blocks the release.

## Tests run

Each suite was run on its own with `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`.
Dependencies were installed into a scratch venv from `requirements.lock` + `requirements-test.lock` (hash-pinned).

| Suite | Result |
|---|---|
| test_w4_readback_evidence | 23/23 OK (12 s) |
| test_w4_fmbatch1_retention_guard | all OK (30 s) |
| test_w4_retfix_retention_keys | all OK (1 s) |
| test_w4_owner_queue_race, run 1 / 2 / 3 | all OK (47 s / 44 s / 47 s) |
RESULTS_PENDING

**Discrimination checks** (separate worktree, fix removed):
- f4c3899b with the `_serialise_owner_queue(s, db)` line removed: the new forced-interleaving test
  **fails** twice in a row (`etsy_surface:info_and_appearance_setup: 2, payment_settings_setup: 2, …`).
  With the fix it passes 3/3. The test discriminates.
- bcbe391b with the two source files reverted to `bcbe391^`: the four new L1–L4 tests **fail**
  (19/23). With the fix, 23/23 pass.

## Review by item

### 1. bcbe391b — READBACK L1–L4 fixes: correct
- **L1.** `_known_exception_names()` walks `BaseException.__subclasses__()`. In my probe
  `"JaneDoe: refund requested"`, `"Error: Jane"` → `unclassified`. `ValueError: x` → `ValueError`.
  The walk de-duplicates by `__name__`, not by class. A subclass that is reachable only under a
  second class with the same name would be skipped. In this process the walk found every one of
  the 78 loaded classes. Even if a class were missed, it fails safe (`unclassified`).
  Cost is about 22 µs per call. The result depends on what is loaded: `sqlalchemy.exc.*` names
  classify only once SQLAlchemy is imported, which it always is in the server. Acceptable.
- **L2.** `truth_sweep_systemic` is now the reading only when it is a real `bool`, otherwise
  `None`. The judge requires `is False`. Correct.
- **L3.** Both named judges now refuse `age < -0.1 h`. See **LOW-1** for a third age check that
  has the same gap.
- **L4.** End-to-end probe with two local HTTP servers, where A answers 302 → B:
  - with a token, `_fetch` returns 302 and B received **no request**;
  - without a token, the redirect is followed (B saw `Authorization: None`);
  - `_token_url_ok` rejects `http://localhost.evil.com`, `http://127.0.0.1.nip.io` and `http://[::1]`
    (IPv6 loopback refused, which is the strict direction).
  
  The `SystemExit` is raised before any socket opens. Correct. The unit test exercises
  `_NoRedirect` directly and not through `_fetch`'s opener; my end-to-end probe covers that path.

### 2. f259afe4 + `listing.adopted_manual` — retention classes: all correct
I checked each reader against the retention rules in `ops/retention.py`. A `latest` action
always keeps its newest row (rule 2). The horizon is 90 days, far beyond any 7-day window.

| Action | Class | Every reader in src/ | Verdict |
|---|---|---|---|
| chain.rebuild_completed | windowed | production_evidence.stale_rebuilds `at >= now-7d` (only reader) | correct |
| chain.rebuild_unbound | windowed | same, 7 d (only reader) | correct |
| ops.rebuild_propagated | latest | production_evidence `order_by id desc limit 1` (only reader) | correct |
| ops.truth.sweep | latest | production_evidence.publishing_halt newest row (only reader) | correct |
| etsy.taxonomy_refreshed | latest | production_evidence.taxonomy newest row (via `REFRESHED_ACTION`, only reader) | correct |
| paid_call.replayed | windowed | production_evidence.paid_calls `at >= now-24h` (via `REPLAY_ACTION`, only reader) | correct |
| listing.adopted_manual | lifetime_total | commerce.orders_ingest scans every row to match orders to adopted listings | correct and protected; pruning would un-adopt old listings |

No gate can lose evidence it needs. Every windowed reader reads at most 7 days, and every latest
reader keeps its newest row.

### 3. 282e47ce, 210aa9f8 — `suite_final_segment.txt`
Four entries were added: launchfix, owner_queue_race, readback_evidence, adopt_manual_listing.
All four files exist and there are no duplicate lines. Fine.

### 4. Merge conflict resolutions
- **0b88aebc `approvals.py`.** Checked with the AST against both parents (9712b57, 194c602):
  - ACTIONS: none lost, none duplicated, none invented.
  - Every `elif action ==` / `startswith` branch from both parents is present.
  - Every ACTIONS key has a handler. The six publication/activation actions are dispatched
    through `action in (...)`.
  - Audit result-key tuple: exactly the union of both parents, no duplicates.
- **0b88aebc `retention.py`, `CONTRACT_CHANGES.md`.** Both sides' rows were kept. Additive only.
- **98904d86 `DECISION_LOG.md`.** D-W4-OWNER-RESUME-POLICY (ours) and D-W4-OWNER-BASKET-IDENTITY
  (theirs) are both kept. The regenerated `decision_index.json` is validated by
  test_w3_decision_index (see the table above).

### 5. f4c3899b — owner-queue seeding lock
- **Postgres:** `pg_advisory_xact_lock(734543617)` runs inside the same `db.session()`
  transaction as the read and the inserts. It is released at commit or rollback. Correct.
- **SQLite:** `BEGIN IMMEDIATE` is the first statement of the session. It takes the write lock
  before the read. This is the same mechanism `launch.readiness` already relies on. Correct.
- **Deadlock:** none. In `handle_launch_readiness` the locked `with ctx.db.session()` block
  (release.py ~4209) closes before `etsy_ops.seed_owner_queue(...)` is called at function level
  (~4312). The two locks are taken one after the other in separate transactions and are never
  nested. No other caller of `seed_owner_queue` in src/ holds a session.
- **Test:** discriminates (see above). It runs on SQLite only, so the Postgres branch is
  exercised by the existing source-text assertion, not by a live race (see INFO-1).

## Findings

### LOW-1 — the weekly judge still treats a future-dated `finished_at` as fresh (residual L3)
`production_evidence.weekly_jobs`: `completing = done_at is not None and now - done_at <= WEEKLY_GRACE`.
A negative delta passes, so a job row dated in the future keeps `judge_weekly` true for ever.
`judge_stale_rebuilds`' `stuck <= 48h` also accepts a negative age, though that only matters
after the sentinel check has already passed. L3 named two judges, and the fix covered exactly
those two.

**Exposure:** `Job.finished_at` is written by the runner's own clock, so only clock skew or a
manual DB write can trigger this. Anonymous callers cannot write it.

**Repro:** seed a DONE `improve.weekly` job with `finished_at = now + 365 d`. Call
`judge_weekly(weekly_jobs(db, now=now))`: it returns True.

**Fix:** use `timedelta(hours=-_SKEW_H) <= now - done_at <= WEEKLY_GRACE`.

### LOW-2 — L1 de-duplicates by class name, not by class (fails safe)
`seen` holds `__name__`. When two distinct classes share a name (several libraries define
`Error`), the second one's subtree is not walked. Its unique subclass names would then classify
as `unclassified`. That is a fail-safe loss of diagnostic detail, not a leak.

**Fix:** track visited classes by identity, and collect names separately.

### LOW-3 (pre-existing, outside the reviewed commits) — other owner-queue writers keep the same read-then-insert race
`OwnerAction.requirement_key` has no unique constraint, and only `launch.readiness` and now
`seed_owner_queue` take `OWNER_QUEUE_LOCK`. One other writer is reachable concurrently with the
same key: `etsy_ops.record_auth_needs_owner` (etsy_ops.py ~263–282). It reads "no open
`AUTH_KEY` row" and then inserts, in an unlocked session. It is called from
`etsy.credential_health`, `etsy.shop_snapshot`, `etsy.listing_census`, `store.publish` and
`store.activate`. Those are different job types, so two workers that hit the same expired grant
can each queue a "Re-authorise the Etsy app" card.

`_queue_openapi_review` and `store_readiness.sync_owner_actions` follow the same pattern. Their
callers are single cadence jobs, so they are lower risk. This is a duplicate owner card (an
annoyance), not an integrity or safety break.

**Repro:** apply the barrier technique from `test_two_concurrent_surface_seedings…` to
`record_auth_needs_owner` with an open `AUTH_INCIDENT` absent. Expect two `AUTH_KEY` rows.

**Fix:** take `_serialise_owner_queue(s, db)` at the top of each such session, or add a partial
unique index on `requirement_key WHERE done = false AND requirement_key <> ''`.

### INFO-1 — the Postgres lock path has no live concurrency test
The forced-interleaving test runs only on SQLite. Consider running it under the Postgres CI
service if one exists.

### INFO-2 — the L4 unit test does not go through `_fetch`'s opener
It calls `_NoRedirect().redirect_request` directly. My two-server probe confirms the wiring is
correct. A local-server test like that would be a stronger regression guard.
