# REVIEW_REQUEST — `eng/a9-u6-fix` (base 56f92eb9, opus2/a9-u6-sweep-isolation)

Fixes for the independent review of 56f92eb9. Each finding has a regression test that fails
on 56f92eb9 and passes on this branch (verified by swapping the old source back in).
Commit 61418af0 (period_key widening) was deliberately NOT re-ported: it is already on the
integration tree.

## H2 (HIGH) — A9 test files crashed on import under run_tests.sh

- **Finding:** `run_tests.sh` runs `"$PY" tests/<file>.py` with no PYTHONPATH. Six A9 files
  (`test_codex_a9_defer_state`, `_event_release`, `_event_scope`, `_owner_action_fence`,
  `_parked_source_change`, `_sweep_isolation`) had no `sys.path` header →
  `ModuleNotFoundError: brambleloop`. `test_codex_a9_source_binding` (imported by all six) and
  `test_codex_a9_defer_state_pg` had the same gap.
- **Fix:** the standard header (insert `../src` and the tests dir) in all eight files.
- **Test:** new `tests/test_opus2_a9_u6_import_path.py` loads every `*_a9_*` test module in a
  fresh interpreter, from an unrelated cwd, with PYTHONPATH removed, with sys.path[0] = the
  script's directory (exactly the runner's conditions). On 56f92eb9: 8 files fail with
  `ModuleNotFoundError: brambleloop`. Now: OK.

## M4 (MEDIUM) — one always-failing release dead-lettered the six-hourly sweep

- **Finding:** any per-release retry made the handler raise "listing package changed
  repeatedly" (false for a ValueError), before writing the sweep audit row, naming no
  failing release durably; after max_attempts the whole sweep went DEAD.
- **Fix** (`publish/listing_package.py`, `runtime/listing_package_ops.py`):
  - per-release results carry `error_class` (class name only — exception text is never
    recorded durably, as before); a STALE contention result is `PackageChangedRepeatedly`;
  - the `listing.package` audit row is written on **every** attempt, before any retry, with
    each release's outcome and a `failed` list;
  - each failing release gets a `listing.package_release_failed` audit row (artifact =
    `slug@version`, `error_class`, `attempt`, `final_attempt`);
  - the retry error names the failing releases and classes, e.g.
    `listing package sweep: 1 release(s) not recorded: a-broken-release@1.0.0 (ValueError); retry the job`;
  - on the final attempt the **sweep** completes DONE with `degraded: true` and
    `failed_releases`, every other release recorded; the next sweep retries the bad one.
    A single-release **event** still retries and dead-letters on its own (accurate message).
  - The audit `results` entries now carry `error_class` instead of `error` (the old `error`
    field could hold up to 300 chars of exception text from `_try`).
- **Test:** `test_codex_a9_sweep_isolation::test_m4_one_release_failing_every_attempt_does_not_dead_letter_the_sweep`
  — on 56f92eb9 the job ends DEAD with "changed repeatedly"; now DONE/degraded, the healthy
  release's owner action exists exactly once, one sweep audit row per attempt, one
  release-failed row per attempt with `ValueError`, no exception text anywhere.
  The existing transient-retry test (`..._retries_without_duplicates`) still passes unchanged.

## Also fixed (same class as A3 N1)

- `test_codex_a9_defer_state_pg` printed only SKIP without `BRAMBLELOOP_TEST_POSTGRES_URL`
  (runner: SUITE REPORTED NO PASSES = failing). It now uses the W6 `_disposable_cluster`
  pattern (fresh loopback PG cluster, torn down after). Passes 1 OK on PostgreSQL 16.

## Suites run

(run in progress — counts added in the next commit)

## PostgreSQL

PostgreSQL 16 (`/usr/lib/postgresql/16`) is installed in this container;
`test_codex_a9_defer_state_pg` ran against a disposable cluster: 1 OK.

## Merge note (not merged)

`git merge-tree` vs `origin/claude/w6-INTEG1` conflicts in
`brambleloop/scripts/suite_final_segment.txt` (both sides append lines: keep all) and
`brambleloop/src/brambleloop/autonomy/autonomy_map.json` (generated file: regenerate). Both
conflicts already exist at the base 56f92eb9; this branch does not touch either file.
INTEG1 was not merged into this branch.

## Final SHA

(added in the next commit)
