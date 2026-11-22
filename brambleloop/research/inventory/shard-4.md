# Inventory: shard 4 of 4 (`SHARD=3/4`)

Inventory only. This is not a release record: checkpointed and sharded runs are never release-eligible (D-W4-OWNER-RESUME-POLICY).

- Run ID: `20261122T105118Z-507`
- Git SHA: `74b749f864f246b1bc402d2f266b120ad3a0f022` (tree clean at start; HEAD at end `74b749f864f246b1bc402d2f266b120ad3a0f022`)
- Started 2026-11-22T10:51:20Z, finished 2026-11-22T11:57:58Z, duration 4000s, JOBS=4
- Command: `CHECKPOINT=1 SHARD=3/4 JOBS=$(nproc) bash run_tests.sh`
- Note: the requested `SHARD=4/4` is rejected by `scripts/suite_checkpoint.py` (shards are 0-indexed, `0 <= i < n`; nothing ran), so shard 4 of 4 was run as `SHARD=3/4`.
- Interpreter: `.venv` built from `requirements.lock` + `requirements-test.lock` (`--require-hashes`), Python 3.13.

## Counts

- Suites in this shard: 291 (of 1103 total)
- Passing suites: 282
- Failing suites: 9
- Tests passing (OK markers): 3359; FAIL markers reported: 21
- Failures the environment caused (classify_failure.py): 0

## Failing suites

### `tests/test_deploy_guard.py` (exit 1)

```
FAIL test_a_candidate_that_is_not_a_descendant_of_production_is_refused_as_a_rollback AssertionError({'ok': False, 'reasons': ['no release-eligible local suite run record for 786ae4a790b4']})
FAIL test_a_green_full_clean_run_on_a_descendant_of_production_is_allowed AssertionError('CHECKPOINT/RESUME/SHARD need scripts/suite_checkpoint.py, which is missing; nothing was run\n')
FAIL test_a_missing_or_red_suite_record_is_refused AssertionError()
FAIL test_a_record_whose_log_contradicts_it_or_is_gone_is_refused AssertionError({'ok': False, 'reasons': ['no release-eligible local suite run record for 786ae4a790b4']})
FAIL test_latest_suite_is_a_file_query_and_the_cli_exit_code_is_the_verdict TypeError("'NoneType' object is not iterable")
OK   test_the_guard_contains_no_deploy_path
OK   test_unknown_or_foreign_deployed_commit_is_refused_not_assumed
```

### `tests/test_persistence.py` (exit 1)

```
OK   test_a_cadence_that_ran_but_did_nothing_is_re_driven_like_one_that_said_so
OK   test_a_cadence_that_wrongly_said_nothing_is_retried_by_the_next_deploy
OK   test_a_deploy_re_drives_what_it_fixed_exactly_once
OK   test_a_run_that_completed_having_done_nothing_counts_as_a_no_op
OK   test_a_workers_capability_refusal_is_never_redriven_and_never_pruned_as_a_defect
OK   test_an_unknown_commit_does_not_re_drive_anything
FAIL test_pipeline_resumes_across_a_worker_restart_mid_flight AssertionError('heirloom-cable-blanket')
OK   test_scheduler_does_not_duplicate_cadences_across_restarts
OK   test_sigkilled_worker_loses_no_work_and_another_finishes_it
OK   test_state_survives_a_full_process_restart_on_disk
OK   test_unfinished_jobs_are_visible_for_recovery_after_restart
```

### `tests/test_v11_autonomy_timeline.py` (exit 1)

```
OK   test_providers_never_raise_on_an_empty_database_and_say_unknown
OK   test_summary_reports_every_department_with_wake_and_blockers
OK   test_timeline_records_and_merges_sources_newest_first
OK   test_memory_and_timeline_writes_are_idempotent_on_their_key
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_v11_autonomy_timeline.py", line 160, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_v11_autonomy_timeline.py", line 135, in test_the_autonomy_map_is_generated_from_live_wiring
    assert d["never_woken_job_types"] == [], (d["department"], d["never_woken_job_types"])
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ('store_commerce', ['sale.pipeline'])
FAIL test_the_autonomy_map_is_generated_from_live_wiring AssertionError(('store_commerce', ['sale.pipeline']))
OK   test_the_committed_map_matches_the_generator

FAIL: 1 failing
```

### `tests/test_v11_cc_views.py` (exit 1)

```
  File "/home/user/project-money/brambleloop/tests/test_v11_cc_views.py", line 227, in test_money_is_unknown_when_the_accounting_source_disconnects
    assert "ConnectionError" in m["sections"]["accounting"]["reason"]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
FAIL test_money_is_unknown_when_the_accounting_source_disconnects AssertionError: 
OK   test_provider_output_passes_through_with_provenance
OK   test_home_and_morning_brief_come_from_real_database_state
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_v11_cc_views.py", line 574, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_v11_cc_views.py", line 329, in test_f884_home_carries_every_element_the_brief_names
    assert open1 == open0 + 1, (open0, open1)
           ^^^^^^^^^^^^^^^^^^
AssertionError: (0, 0)
FAIL test_f884_home_carries_every_element_the_brief_names AssertionError: (0, 0)
OK   test_approval_cards_carry_the_f885_fields
OK   test_notifications_suppress_routine_noise_and_surface_real_incidents
OK   test_security_notification_counts_attacks_not_expired_tabs
OK   test_ask_why_is_a_product_blocked_is_grounded_in_gate_records
OK   test_ask_answers_unknown_rather_than_inventing
OK   test_timeline_and_drill_down_carry_provenance
OK   test_every_tab_answers_and_carries_status_envelopes
OK   test_no_fixture_or_demo_data_in_production_paths
12/14 passed in 17s
```

### `tests/test_w3_decision_index.py` (exit 1)

```
OK   test_runtime_readers_fall_back_to_the_index_when_the_log_is_absent
OK   test_the_index_carries_no_session_state
FAIL test_the_index_matches_the_log AssertionError('src/brambleloop/core/decision_index.json is stale: run `PYTHONPATH=src python -m brambleloop.core.decision_index`')
```

### `tests/test_w3_suite_job_identity.py` (exit 1)

```
FAIL test_an_attached_observer_starts_nothing_and_takes_the_running_runs_result ValueError('not enough values to unpack (expected 1, got 0)')
FAIL test_an_interrupted_run_writes_the_130_sentinel_after_its_record ValueError('not enough values to unpack (expected 1, got 0)')
FAIL test_every_terminal_path_ends_the_log_with_the_exit_sentinel_matching_the_record AssertionError('')
FAIL test_registry_opt_out_and_an_unreachable_registry_are_recorded_as_null AssertionError()
OK   test_the_registry_separates_work_from_observers
FAIL test_the_run_enrols_itself_and_a_late_observer_in_a_fresh_process_reads_its_result AssertionError()
```

### `tests/test_w4_close6_hygiene.py` (exit 1)

```
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_close6_hygiene.py", line 113, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_close6_hygiene.py", line 78, in test_f145_a_green_run_removes_its_run_tmpdir
    assert r.returncode == 0, r.stdout[-800:]
           ^^^^^^^^^^^^^^^^^
AssertionError
FAIL test_f145_a_green_run_removes_its_run_tmpdir AssertionError('')
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_close6_hygiene.py", line 113, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_close6_hygiene.py", line 95, in test_f145_an_interrupted_run_removes_its_run_tmpdir
    assert hyg._wait_for(lambda: Path(str(gate) + ".started").exists())
           ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
FAIL test_f145_an_interrupted_run_removes_its_run_tmpdir AssertionError()
OK   test_f146_exactly_one_exit_trap_and_interrupts_only_exit

FAIL: 2 failing of 3
```

### `tests/test_w4_fmbatch1_failclass.py` (exit 1)

```
OK   test_each_environment_class_is_named_and_a_code_failure_is_not
OK   test_review_f6_an_assertion_quoting_an_environment_phrase_is_a_code_failure
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_failclass.py", line 89, in <module>
    t()
    ~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_failclass.py", line 74, in test_run_tests_names_the_environment_failure_and_not_the_assertion
    assert "ENVIRONMENT FAILURE (ENOSPC)" in blocks["tests/test_disk.py"], blocks
                                             ~~~~~~^^^^^^^^^^^^^^^^^^^^^^
KeyError: 'tests/test_disk.py'
FAIL test_run_tests_names_the_environment_failure_and_not_the_assertion 'tests/test_disk.py'
2 passed, 1 failed
```

### `tests/test_w4_resume_runner.py` (exit 1)

```
OK   test_p02a_empty_attempt_json_is_no_result_and_reruns (2.4s)
OK   test_p02b_torn_out_under_a_passed_attempt_is_no_result_and_reruns (2.5s)
OK   test_p02c_lost_out_under_a_passed_attempt_reruns_instead_of_sticking (2.5s)
OK   test_p03a_truncated_attempt_json_reruns (2.6s)
OK   test_p03b_an_edited_out_is_detected_and_rerun (2.6s)
OK   test_p03c_a_failed_to_passed_edit_is_refused_and_the_record_is_self_consistent (2.3s)
OK   test_p03d_a_full_forgery_is_not_counted (2.3s)
OK   test_p04a_tracked_edit_is_refused (1.8s)
OK   test_p04b_untracked_edit_is_refused (1.7s)
OK   test_p04c_ignored_fixture_edit_is_refused (1.8s)
OK   test_p04d_new_commit_is_refused (1.8s)
OK   test_p05a_lockfile_edit_is_refused (2.4s)
OK   test_p05b_installed_package_change_in_the_same_venv_is_refused (7.9s)
OK   test_p05c_pythonpath_change_is_refused (1.8s)
OK   test_p05d_new_environment_flag_is_refused (1.8s)
OK   test_p06a_a_result_copied_from_another_run_is_not_counted (3.5s)
OK   test_p06b_a_checkpoint_directory_copied_to_another_run_id_is_refused (1.3s)
OK   test_p07_a_completed_failed_run_cannot_be_resumed_to_green (1.3s)
OK   test_p08_a_tmp_leak_strict_failure_survives_resume (2.4s)
OK   test_p09_a_finalize_failure_fails_the_run_and_never_fails_open (10.8s)
OK   test_p09_control_resumed_full_run_with_finalize_intact_is_never_eligible (11.7s)
OK   test_p09b_the_deploy_guard_reads_resume_provenance (0.0s)
OK   test_p10_union_of_fresh_and_resumed_results_and_the_leak_census (2.5s)
OK   test_shards_are_deterministic_disjoint_and_never_release_eligible (4.4s)
OK   test_without_the_flags_nothing_changes (0.2s)
```
