# Review request — A9 round 2 (`eng/a9-u6-fix`, base a9feb805)

Fixes for the independent review of a9feb805. Every new test FAILS on a9feb805 (verified: the
new test file run against a9feb805's source in a separate worktree → 0 passed, 4 failed) and
passes on this branch. No test was weakened or skipped. The repo-root `REVIEW_REQUEST.md`
(round 1) is deleted; its content is superseded by this file plus git history.

## MEDIUM — a sweep in which every release failed completed DONE, silently

- **Finding:** on the final attempt `runtime/listing_package_ops.py` returned DONE
  (`degraded: true`) even when EVERY release failed. Nothing in `src` read the degraded flag or
  the `listing.package_release_failed` rows; the ops checks read only DEAD jobs. A probe making
  `record` fail for every release (the PostgreSQL period_key truncation class) gave FAILED,
  FAILED, DONE — nothing recorded, no dead letter, every 6 h.
- **Fix:**
  - `listing_package_ops.py`: if no release was recorded (`recorded` = results without
    `retry`), the final attempt raises like the earlier ones, so the queue dead-letters it.
    The exception class raised is a subclass of `ListingPackageNotRecorded` **named after the
    releases' real (most common) error class**, so the worker's `last_error` reads
    `StringDataRightTruncation: listing package sweep: 2 release(s) not recorded:
    a-broken-release@1.0.0 (StringDataRightTruncation), test-bound-release@1.0.0 (...); retry
    the job` and `production_evidence.dead_letters` / `error_class()` report
    `StringDataRightTruncation`, not a wrapper. Names not matching `^[A-Z][A-Za-z0-9_]{1,63}$`
    fall back to `ListingPackageNotRecorded`. Exception text is still never recorded.
  - Partial failure on the final attempt stays DONE `degraded: true` (plus `recorded: n`),
    and is now surfaced:
    - `ops/production_evidence.py`: new section `listing_package_releases` (in `SECTIONS`, so
      in `GET /api/readback/evidence`): `degraded_sweeps`, `degraded_job_ids`,
      `unrecorded_releases`, `final_attempt_failures`, and `by_release` grouped by
      `slug@version` + error class (`failed_attempts`, `final_attempt_failures`, newest time,
      job ids). Release keys are pattern-checked and class names emitted only if they are
      loaded exception classes (the L1 rule), so no free text leaves.
      New `server_judgement.no_unrecorded_listing_releases_in_24h` beside
      `no_unexpected_dead_letters_in_24h`.
    - `app/command_center/readers.py` `queue()` (the operations surface that reads DEAD jobs):
      status DEGRADED with a reason and `unrecorded_listing_releases` when that judgement is
      false.
  - `publish/listing_package.py`: `PackageChangedRepeatedly` is now a real exception class
    (was only a string), so `error_class()` can name it in any process.
  - `ops/retention.py`: `listing.package_release_failed` added to `KNOWN_READ_ACTIONS`
    (windowed, 24 h) for the new reader.
- **Tests** (`tests/test_opus2_a9_u6_sweep_visibility.py`, real `Worker` + `JobQueue`):
  - `test_every_release_failing_dead_letters_with_the_real_class_and_releases` — FAILED,
    FAILED, **DEAD**; `last_error` head names the class and both releases, no exception text;
    `dead_letters` groups it as `listing.package` / `StringDataRightTruncation`; both
    judgements false. (a9feb805: DONE.)
  - `test_partial_failure_completes_degraded_and_is_surfaced_in_production_evidence` — DONE
    degraded, `recorded: 1`; the section lists the release (3 failed attempts, 1 final), the
    judgement is false, dead-letter judgement stays true, Command Center queue is DEGRADED.
  - `test_every_release_recorded_completes_clean` — DONE, no `degraded`, `last_error` None,
    empty section, judgement true, Command Center queue OK.

## LOW — DONE degraded job kept the previous attempt's last_error

- **Fix:** before returning degraded, the handler replaces `last_error` (under its lease
  token) with what happened on this attempt: `<Class>: listing package sweep: N release(s)
  not recorded: …; completed degraded; the next sweep retries them`.
- **Test:** the partial-failure test asserts earlier attempts said "retry the job" and the
  DONE job's `last_error` does not, and starts with the degraded summary.

## LOW — last-attempt check with max_attempts=0

- **Fix:** `final_attempt = max_attempts <= 0 or attempts >= max_attempts`, explicit and
  commented (the queue dead-letters the first failure when `max_attempts <= 0`, so that attempt
  is the last).
- **Test:** `test_max_attempts_zero_is_an_explicit_last_attempt` — partial-fail completes
  degraded on the first attempt; all-fail raises with the real class name; every release-failed
  row has `final_attempt: true`.

## Suites run

`JOBS=4 SUITE_REGISTRY=0 SUITES="<24 suites>" PY=/tmp/venv/bin/python bash run_tests.sh` on a
clean tree at d65c9e6a (run record `artifacts/suite_runs/20261118T152533Z-2639.json`):
**TOTAL PASSING: 186; suites failing: 5**, and all 5 are the environment issue below.

**Green (19 suites):** all 13 A9 suites from round 1 (test_codex_a9_defer_state,
_defer_state_pg, _event_release, _event_scope, _owner_action_fence, _parked_source_change,
_source_binding, _sweep_isolation, test_opus2_a9_u6_child_vocab, _import_path,
_record_reverify, test_opus2_listing_package, test_w5_a9_package_event), the new
**test_opus2_a9_u6_sweep_visibility (4 OK)**, and the suites that read the touched modules:
test_w4_fmbatch1_retention_guard, test_cost_governance_wave2 (both retention guards),
test_w4_board, test_w3_k7_ops_truth, test_w5_a7_supply_stall.

**Not run, environment (NOT a pass):** test_w4_readback_evidence, test_w4_cc_company,
test_v11_cc_actions, test_w4_fmbatch1_master_view, test_w4_fmbatch1_dept_workspace. Each
fails at import with `RuntimeError: The starlette.testclient module requires the httpx2
package to be installed`. `requirements.txt` has `fastapi>=0.115` and no httpx; a fresh venv
resolves starlette 1.10.0 / fastapi 0.164.0, whose TestClient needs `httpx2`. It fails the
same way on a9feb805 (checked: test_w4_readback_evidence in an a9feb805 worktree). Installing
httpx2 was not permitted in this session, so **the reviewer should run these five in an
environment that has the test client**, especially test_w4_readback_evidence (it covers
`production_evidence.evidence()`, which now has a new section and judgement) and
test_w4_cc_company (Command Center readers). The new section and the queue-reader change are
exercised directly, without a TestClient, by test_opus2_a9_u6_sweep_visibility.

Separate finding for the integrator (not fixed here, out of scope): `requirements.txt` does
not pin a TestClient-compatible httpx/starlette, so the API suites cannot run in a fresh venv.

The full suite was not run (per instructions).

## Round-2 review follow-up (e85a1aa1 — fixes on top of fca12ee9)

### MEDIUM — the post-deploy readback never read the new judgement

- **Finding:** `listing_package_releases` / `no_unrecorded_listing_releases_in_24h` were added
  to `ops/production_evidence.py` but not to `EVIDENCE_ITEMS` in the repo-root
  `ops/readback.py`, so `test_readback_evidence_names_the_checks_the_server_serves` failed
  (22/23) and `readback --evidence` (which feeds `rollback_decision`) never reported an
  unrecorded listing release.
- **Fix:** row `("listing-package releases recorded", "listing_package_releases",
  "no_unrecorded_listing_releases_in_24h")` placed after the dead-letter row (the server judges
  them side by side). `_judge_section` gives it a detail: on FAIL, `N degraded sweeps;
  unrecorded: ['slug@version:Class xN']`; on PASS, `every release recorded`. Unreadable /
  missing section / no judgement stay UNKNOWN through the existing generic path.
- **Tests:** `test_readback_evidence_names_the_checks_the_server_serves` now passes (23/23).
  `test_readback_evidence_cli_never_prints_the_token_and_keeps_unknown_apart` hard-coded
  12 items (4 public + 8 evidence); it now says 13 and additionally asserts the new row is
  PASS on its fixture (nothing degraded seeded) — tightened, not weakened. New
  `test_post_deploy_readback_reports_unrecorded_listing_releases` (sweep-visibility suite):
  a real degraded sweep → `readback.run_evidence` row FAIL naming the broken release, overall
  verdict FAIL.

### LOW — one failing query took the whole Command Center jobs reader down

- **Fix:** in `app/command_center/readers.py` `queue()`, the listing-release query is wrapped;
  on any exception `unrecorded_listing_releases` = `{"status": "UNKNOWN", "error_class":
  <class name>, "reason": "listing-package release evidence unreadable"}` (no exception text).
  The reader still serves counts and dead letters. Status: DEGRADED if dead letters or a known
  unrecorded release; otherwise **UNKNOWN** (never OK) while that field is unknown, with the
  reason `listing-package release evidence UNKNOWN (<Class>)`.
- **Test:** `test_queue_reader_degrades_to_unknown_when_the_listing_query_fails` — patched
  query raises → reader returns (status UNKNOWN, items present, the explicit UNKNOWN field, no
  exception text); with a dead letter also present → DEGRADED.

### Suites (environment fixed: venv from `requirements.lock` + `requirements-test.lock`)

`JOBS=4 SUITE_REGISTRY=0 SUITES="<20 suites>" PY=/tmp/venv/bin/python bash run_tests.sh` on a
**clean tree at e85a1aa1** (run record `artifacts/suite_runs/20261118T163219Z-8797.json`):
**TOTAL PASSING: 185; suites failing: 0; environment failures: 0.** The five suites that
were env-blocked in round 2 (missing `httpx2`) now run: the lock files supply a compatible
test client.

| suite | passing |
|---|---|
| test_w4_readback_evidence | 23/23 |
| test_w4_cc_company | 23/23 |
| test_v11_cc_actions | 7/7 |
| test_w4_fmbatch1_master_view | 3 OK, 0 failed |
| test_w4_fmbatch1_dept_workspace | 2 OK, 0 failed |
| test_w3_k7_ops_truth | 16 |
| test_opus2_listing_package | 14 |
| test_w5_a9_package_event | 8 |
| test_codex_a9_defer_state | 4 |
| test_codex_a9_defer_state_pg | 1 (real disposable PostgreSQL) |
| test_codex_a9_event_release | 3 |
| test_codex_a9_event_scope | 16 |
| test_codex_a9_owner_action_fence | 6 |
| test_codex_a9_parked_source_change | 14 |
| test_codex_a9_sweep_isolation | 6 |
| test_codex_a9_source_binding | 11 |
| test_opus2_a9_u6_sweep_visibility | 6 (4 + 2 new) |
| test_opus2_a9_u6_child_vocab | 7 |
| test_opus2_a9_u6_import_path | 1 (0 failures) |
| test_opus2_a9_u6_record_reverify | 14 |

Note for the reviewer: `test_opus2_listing_package` takes ~10 min under JOBS=4 (most of it in
`test_review_opus2g_l51_…`); it is slow, not hung — it completes and passes.

## Final SHA

See the final message / `git log -1 eng/a9-u6-fix` (this file is committed in the final commit;
the code under review is e85a1aa1).
