# Certification result — 7a0bc63b

```
TOTAL PASSING: 11556 ; suites failing: 5
ENVIRONMENT FAILURES: 0 of the 5 failing suites (ENOSPC/permission/network/provider; F-150)
RUN FINISHED: 2026-11-19T03:17:57Z
DURATION: 10595s
GIT SHA: 7a0bc63beee2c07a90dba73281a84ee4898b8740
RUN RECORD PATH: brambleloop/artifacts/suite_runs/20261119T002122Z-238.json (failed)
```

Note: the first launch (run 20261118T232417Z-1721, started 2026-11-18T23:24:17Z) was killed ~57 min in by a container restart (uptime 0 min at 2026-11-19T00:21Z); this is the single relaunch (run 20261119T002122Z-238), which ran uninterrupted to completion. Tree clean at start and end; same SHA at end.

## Failing suites (5)

### tests/test_cost_governance_wave2.py

FAIL lines:
```
   FAIL test_only_dead_letters_that_are_refusals_working_are_ever_removed RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   FAIL test_retention_keeps_the_newest_rows_of_every_action_whatever_the_horizon RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   FAIL test_retention_never_touches_the_rows_every_ceiling_is_computed_from RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   FAIL test_retention_refuses_to_run_when_the_code_reads_an_action_it_has_no_decision_about AssertionError('an audit action is read by name in `src/` with no retention decision recorded. Add it to `retention.KNOWN_READ_ACTIONS` with how it is read')
```

First 40 lines of traceback/assertion output:
```
   FAIL test_only_dead_letters_that_are_refusals_working_are_ever_removed RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   OK   test_purge_dead_skips_a_dead_letter_that_evidence_points_at
   OK   test_release_returns_the_money_and_records_what_the_call_actually_cost
   OK   test_retention_cannot_take_the_completed_job_count_below_the_gate_that_reads_it
   OK   test_retention_keeps_every_audit_action_a_gate_counts_over_all_time
   OK   test_retention_keeps_the_newest_jobs_of_every_type_so_the_history_of_types_survives
   FAIL test_retention_keeps_the_newest_rows_of_every_action_whatever_the_horizon RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   FAIL test_retention_never_touches_the_rows_every_ceiling_is_computed_from RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   FAIL test_retention_refuses_to_run_when_the_code_reads_an_action_it_has_no_decision_about AssertionError('an audit action is read by name in `src/` with no retention decision recorded. Add it to `retention.KNOWN_READ_ACTIONS` with how it is read')
   OK   test_retention_will_not_delete_a_job_that_evidence_points_at
   OK   test_the_agent_refusal_says_the_month_still_has_room_because_it_does
   OK   test_the_batch_and_the_guard_are_sized_on_the_same_arithmetic
   OK   test_the_batch_never_exceeds_the_months_remaining_headroom
   OK   test_the_batch_shrinks_when_the_agents_other_cadences_have_spent_the_day
   OK   test_the_benchmark_owns_the_directory_its_renders_land_in
   OK   test_the_gallery_batch_is_computed_from_the_ceiling_and_fits_inside_it
   OK   test_the_job_horizon_clears_the_longest_cadence_period
   OK   test_the_monthly_ceiling_is_checked_first_because_it_is_the_budget
   OK   test_the_period_is_read_from_the_schedule_that_fires_it
   OK   test_the_permission_and_the_month_are_asked_about_the_same_day
   OK   test_the_reservation_is_what_refuses_the_second_of_two_concurrent_callers
   OK   test_the_retention_cadence_and_its_permission_exist_together
   OK   test_the_spend_signal_can_see_money_that_is_reserved_and_not_yet_billed
   OK   test_the_sweep_closes_abandoned_reservations_and_says_they_were_abandoned
   OK   test_there_is_no_images_per_run_constant_left_to_drift
```

### tests/test_etsy_oauth_callback.py

FAIL lines:
```
   FAIL test_retention_never_prunes_the_credential_and_never_prunes_a_live_handshake: RetentionRefused: these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent
   FAIL test_retention_still_knows_every_audit_action_the_source_reads_by_name: AssertionError: an audit action is read by name in `src/` with no retention decision recorded
```

First 40 lines of traceback/assertion output:
```
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/test_etsy_oauth_callback.py", line 923, in _run_all
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_etsy_oauth_callback.py", line 762, in test_retention_never_prunes_the_credential_and_never_prunes_a_live_handshake
       result = retention.apply(db)
     File "/home/user/Project-Money/brambleloop/src/brambleloop/ops/retention.py", line 1161, in apply
       raise RetentionRefused(
       ...<4 lines>...
           f"mistake this refusal exists to prevent")
   brambleloop.ops.retention.RetentionRefused: these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent
   FAIL test_retention_still_knows_every_audit_action_the_source_reads_by_name: AssertionError: an audit action is read by name in `src/` with no retention decision recorded
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/test_etsy_oauth_callback.py", line 923, in _run_all
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_etsy_oauth_callback.py", line 774, in test_retention_still_knows_every_audit_action_the_source_reads_by_name
       assert retention.unknown_read_actions() == [], (
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   AssertionError: an audit action is read by name in `src/` with no retention decision recorded
   OK   test_sealing_refuses_without_a_key_rather_than_storing_plaintext
   OK   test_the_access_log_cannot_print_an_authorization_code
   OK   test_the_four_refusals_are_four_different_outcomes_end_to_end
   OK   test_the_no_plaintext_check_catches_an_injected_sealing_defect
   OK   test_the_publish_path_reads_the_stored_credential_and_writes_rotations_back
   OK   test_the_redirect_uri_rules_etsy_publishes_are_enforced_before_the_owner_sees_a_browser
   OK   test_the_replay_check_catches_an_injected_single_use_defect
   OK   test_the_start_endpoint_refuses_a_caller_with_no_operator_credential
   OK   test_the_start_endpoint_refuses_when_there_is_nowhere_to_seal_the_verifier
   OK   test_the_start_endpoint_writes_the_handshake_before_it_returns_a_url
   OK   test_the_state_is_never_stored_and_the_verifier_is_never_stored_in_the_clear
   OK   test_the_state_is_unpredictable_and_comes_from_secrets_not_random
   OK   test_the_token_endpoint_host_is_one_named_constant_with_its_source_beside_it
   OK   test_the_verify_endpoint_still_reports_twelve_checks
```

### tests/test_physfix.py

FAIL lines:
```
   FAIL test_the_failed_release_never_publishes_again_after_an_owner_lift RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a
```

First 40 lines of traceback/assertion output:
```
   FAIL test_the_failed_release_never_publishes_again_after_an_owner_lift RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a
   OK   test_the_kit_ceiling_is_checked_from_above_and_no_stale_figure_remains
   OK   test_the_priced_partial_offer_is_a_make_the_intake_accepts
   OK   test_the_texture_builders_never_share_their_gauge
   OK   test_two_coasters_of_four_never_pass_as_the_whole_set
   OK   test_two_coasters_recorded_as_a_component_give_the_true_factor_and_partial_class
   47/48 passed
```

### tests/test_w4_fmbatch1_retention_guard.py

FAIL lines:
```
(no FAIL line printed; see output below)
```

First 40 lines of traceback/assertion output:
```
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/test_w4_fmbatch1_retention_guard.py", line 135, in <module>
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_w4_fmbatch1_retention_guard.py", line 83, in test_every_action_the_real_code_reads_is_classified
       assert retention.unknown_read_actions() == []
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   AssertionError
```

### tests/test_w5_concept_intake.py

FAIL lines:
```
   FAIL test_g2_prune_keeps_a_non_newest_row_that_holds_a_current_fingerprint RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   FAIL test_n10_ops_retention_apply_prunes_the_table RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
```

First 40 lines of traceback/assertion output:
```
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/test_w5_concept_intake.py", line 935, in <module>
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_w5_concept_intake.py", line 831, in test_g2_prune_keeps_a_non_newest_row_that_holds_a_current_fingerprint
       assert retention.apply(db, now=later)["removed"]["radar_concepts"] == 0
              ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^
     File "/home/user/Project-Money/brambleloop/src/brambleloop/ops/retention.py", line 1161, in apply
       raise RetentionRefused(
       ...<4 lines>...
           f"mistake this refusal exists to prevent")
   brambleloop.ops.retention.RetentionRefused: these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent
   FAIL test_g2_prune_keeps_a_non_newest_row_that_holds_a_current_fingerprint RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   OK   test_n8_prune_never_deletes_an_approved_row_even_when_it_is_not_the_newest
   OK   test_n9_prune_keeps_decided_rows_younger_than_the_horizon
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/test_w5_concept_intake.py", line 935, in <module>
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_w5_concept_intake.py", line 871, in test_n10_ops_retention_apply_prunes_the_table
       dry = retention.apply(db, dry_run=True)
     File "/home/user/Project-Money/brambleloop/src/brambleloop/ops/retention.py", line 1161, in apply
       raise RetentionRefused(
       ...<4 lines>...
           f"mistake this refusal exists to prevent")
   brambleloop.ops.retention.RetentionRefused: these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent
   FAIL test_n10_ops_retention_apply_prunes_the_table RetentionRefused("these audit actions are read by name in `src/` and this module has no retention decision about them: ['unresolved:swarm/orchestrate.py::_probe_in_force', 'unresolved:swarm/orchestrate.py::_probe_rows']. Add each to `KNOWN_READ_ACTIONS` with how it is read -- a lifetime count over a pruned table is a different claim from the one it says it is making, and that is the mistake this refusal exists to prevent")
   OK   test_n17_a_family_that_loses_proven_demand_has_its_variation_withdrawn
   OK   test_n18_gate_inputs_strips_judged_brief_fields_from_a_stored_row
   2 failure(s)
```

