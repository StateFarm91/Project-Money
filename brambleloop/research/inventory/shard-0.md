# Test inventory: shard 0 of 4

This is an inventory only. It is not a release record, and nothing here was fixed.

- Run ID: `20261122T123242Z-414`
- Commit: `9d719b6c00567017b2128598e3fd9134c0f9e30a` (tree clean at start, HEAD unchanged at end). Note: shard 2 ran at `74b749f`; this shard ran at the later `9d719b6`, so the two are not from the same commit.
- Command: `CHECKPOINT=1 SHARD=0/4 JOBS=4 bash run_tests.sh` (python /usr/bin/python3.11, venv from `requirements.lock` + `requirements-test.lock`)
- Started 2026-11-22T12:32:43Z, finished 2026-11-22T13:51:09Z, duration 4706s. Runner exit code 3 (suites failing).
- Release eligible: False. shard run: a checkpointed, resumed or sharded run never certifies a release (owner decision D-W4-OWNER-RESUME-POLICY; W4-RESUMEFIX F1)

## Counts

| | Suites |
|---|---|
| In shard 0/4 | 287 |
| Passing | 284 |
| Failing | 3 |

Individual tests: 3272 passing, 13 reported failing, 0 reported skipped. The runner classed 0 of the failing suites as environment failures (ENOSPC, permission, network or provider).

## Failing suites

### `tests/test_run_tests_script.py`

Exit code: 1. Last 25 lines of output:

```
FAIL test_a_dirty_tree_is_recorded_as_dirty_and_refused_under_require_clean AssertionError()
FAIL test_a_filtered_run_executes_only_the_named_suites_and_an_unknown_name_runs_nothing AssertionError()
FAIL test_a_json_run_record_and_a_full_log_copy_are_written_where_the_log_says AssertionError('')
FAIL test_a_second_identical_run_reports_the_running_one_and_exits_without_running AssertionError('the first run never started its suite')
FAIL test_a_stale_lock_from_a_dead_process_is_taken_over_and_said AssertionError()
FAIL test_an_interrupted_run_is_recorded_as_interrupted_and_releases_its_lock ValueError('not enough values to unpack (expected 1, got 0)')
FAIL test_only_a_full_clean_green_run_on_an_unmoved_head_can_be_release_eligible IndexError('list index out of range')
FAIL test_only_fail_marker_lines_count_as_failing_tests ValueError('not enough values to unpack (expected 1, got 0)')
FAIL test_the_log_opens_and_closes_with_sha_tree_state_utc_times_and_totals AssertionError('CHECKPOINT/RESUME/SHARD need scripts/suite_checkpoint.py, which is missing; nothing was run\n')
FAIL test_then_full_chains_into_the_unfiltered_run_when_the_targeted_suites_pass AssertionError()
FAIL test_then_full_does_not_start_the_full_run_when_the_targeted_suites_fail AssertionError()
```

### `tests/test_w6_listing_chain_e2e.py`

Exit code: 1. Last 25 lines of output:

```
OK   test_a_every_stage_ran_from_the_job_its_predecessor_enqueued
OK   test_a_the_certified_release_flows_through_every_stage_with_its_own_artefacts
OK   test_b_in_shadow_store_publish_is_refused_and_nothing_is_published
OK   test_c_the_package_is_blocked_on_exactly_the_observed_set
FAIL test_d_a_fixture_sample_through_the_real_intake_moves_the_package_to_its_next_state AssertionError([('release_gates.for_publish', 'listing-set certificate (#70)'), ('release_gates.for_publish', 'search certificate (F-004)'), ('release_gates.for_publish', 'FIRST_CUSTOMER_BLOCKING: imagery'), ('release_gates.for_publish', 'FIRST_CUSTOMER_BLOCKING: etsy_remote_state'), ('release_gates.for_publish', 'SAMPLE_PHOTO_REQUIRED'), ('certified_payload', 'listing search profile not certified PASS (REFUSED on the he'), ('certified_frames', 'no valid listing-set certificate for hexagon-coaster-set@1.2.1'), ('pdf_standard', 'premium PDFs are not certified against the PDF standard'), ('pdf_i
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w6_listing_chain_e2e.py", line 496, in <module>
    fn()
  File "/home/user/project-money/brambleloop/tests/test_w6_listing_chain_e2e.py", line 440, in test_d_a_fixture_sample_through_the_real_intake_moves_the_package_to_its_next_state
    assert len(keys) == len(set(keys)) and set(keys) == BLOCKERS_D, keys
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: [('release_gates.for_publish', 'listing-set certificate (#70)'), ('release_gates.for_publish', 'search certificate (F-004)'), ('release_gates.for_publish', 'FIRST_CUSTOMER_BLOCKING: imagery'), ('release_gates.for_publish', 'FIRST_CUSTOMER_BLOCKING: etsy_remote_state'), ('release_gates.for_publish', 'SAMPLE_PHOTO_REQUIRED'), ('certified_payload', 'listing search profile not certified PASS (REFUSED on the he'), ('certified_frames', 'no valid listing-set certificate for hexagon-coaster-set@1.2.1'), ('pdf_standard', 'premium PDFs are not certified against the PDF standard'), ('pdf_illustration', 'PDF_NOT_ILLUSTRATED')]
OK   test_d_the_real_upgrade_job_completes_with_the_frame_provenance_recorded
5/6 passed
```

### `tests/test_ws5_e5_learning_safety.py`

Exit code: 1. Last 25 lines of output:

```
OK   test_internal_and_buyer_lessons_have_separate_caps
OK   test_a_lessons_weight_decays_with_age
OK   test_paid_traffic_never_moves_a_buyer_lesson
FAIL test_the_chain_real_outcome_to_lesson_to_ranking_to_a_different_next_concept
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/_minipytest.py", line 152, in run_module
    fn(**kwargs)
  File "/home/user/project-money/brambleloop/tests/test_ws5_e5_learning_safety.py", line 109, in test_the_chain_real_outcome_to_lesson_to_ranking_to_a_different_next_concept
    assert after == basket, (after, nudges)                      # a different next concept
           ^^^^^^^^^^^^^^^
AssertionError: ('valentine-heart-garland', {'nordic-forest-basket': 0.02, 'valentine-heart-garland': 0.0})
OK   test_the_same_chain_with_synthetic_rows_changes_nothing
OK   test_radar_scan_ranks_with_the_nudge
5 passed, 1 failed
```
