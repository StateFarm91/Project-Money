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

SUITES_PLACEHOLDER

## Final SHA

See the final message / `git log -1 eng/a9-u6-fix` (this file is committed in the final commit).
