# Test inventory — shard 1 of 4

Inventory only. This is **not** a release record: it is a sharded checkpoint run, which the runner marks `release_eligible: false` (D-W4-OWNER-RESUME-POLICY). Nothing was fixed.

| Field | Value |
|---|---|
| Run ID | `20261122T105135Z-594` |
| Command | `CHECKPOINT=1 SHARD=1/4 JOBS=4 bash run_tests.sh` |
| Git SHA | `74b749f864f246b1bc402d2f266b120ad3a0f022` (tree clean, unchanged at end) |
| Started / finished (UTC) | 2026-11-22T10:51:36Z / 2026-11-22T11:42:12Z (3037 s) |
| Interpreter | `.venv/bin/python` (Python 3.13, from `requirements.lock` + `requirements-test.lock`) |
| Suites in shard | 241 |
| **Passing suites** | **231** |
| **Failing suites** | **10** |
| Tests passing / failing (reported) | 2596 / 18 |
| Runner exit code | 10 (= failing suites) |
| Environment failures | 0 of the failing suites (ENOSPC/permission/network/provider) |

## Failing suites

- `tests/test_audit_build_state_current.py` — exit 1
- `tests/test_learn_publish_contract.py` — exit 1
- `tests/test_mc_perf.py` — exit 1
- `tests/test_physfix_photo_first.py` — exit 1
- `tests/test_rehearsal_past_shadow_success.py` — exit 1
- `tests/test_secret_scan.py` — exit 1
- `tests/test_v11_pwa_static.py` — exit 1
- `tests/test_w3_tmp_hygiene.py` — exit 1
- `tests/test_w4_close5_rows3.py` — exit 1
- `tests/test_w4_visnext2.py` — exit 1

### `tests/test_audit_build_state_current.py`

Exit code 1. Last 25 lines of output:

```
FAIL test_build_state_production_block_is_current AssertionError ['production-sha 67efe8ebe863 is 8 deploys behind the newest DEPLOYED_HISTORY entry 83d05dbfcd37; update the block']
OK   test_newest_and_one_behind_pass_two_behind_fails 0.0s
OK   test_release_record_line_must_match_verify_build 0.0s
OK   test_unknown_sha_and_missing_block_fail 0.0s
3/4 passing
```

### `tests/test_learn_publish_contract.py`

Exit code 1. Last 25 lines of output:

```
FAIL test_both_runtime_pdf_render_sites_pass_same_learn_resolver AssertionError no PDF render site checked in release.py
OK   test_approved_links_repeat_exact_bytes_and_changed_approval_trips_hash_gate
/home/user/project-money/brambleloop/.venv/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
OK   test_omitted_revision_serves_only_current_reviewed_spec_never_stale_pdf_target
2/3 passing
```

### `tests/test_mc_perf.py`

Exit code 1. Last 25 lines of output:

```
/home/user/project-money/brambleloop/.venv/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
FAIL test_every_mission_control_route_is_within_budget AssertionError("routes over budget: {'/api/cc/operating-evidence': 571, '/api/cc/store': 32550, '/api/cc/timeline': 808}")
OK   test_snapshotted_pages_answer_a_repeat_click_fast_and_show_their_age
OK   test_an_owner_write_drops_every_snapshot
OK   test_a_refused_write_does_not_drop_snapshots_and_a_get_never_does
OK   test_approvals_and_previews_are_always_live
OK   test_the_snapshot_never_caches_a_failure_and_is_single_flight
     /api/cc/demand median: idle 49 ms, 4 CPU threads 790 ms, 4 yielding CPU threads 253 ms
OK   test_f11_background_work_that_yields_lets_requests_through
6 passed, 1 failed
```

### `tests/test_physfix_photo_first.py`

Exit code 1. Last 25 lines of output:

```
FAIL test_a_completed_upgrade_leads_with_the_photo_and_the_gate_accepts_it AssertionError({'satisfied': False, 'qualifying': [{'photo_id': 1, 'sha256': '9213214062a7f5868e18c7cd47fb7ee81d8cb5bff26631dc8da43578ade5efcc', 'physical_test_id': 1}], 'rejected': [], 'first_frame': {'position': 1, 'sha256': '9213214062a7f5868e18c7cd47fb7ee81d8cb5bff26631dc8da43578ade5efcc'}, 'etsy_sources': ['44297885802647', '115015663347'], 'reasons': ['SAMPLE_PHOTO_REQUIRED: the qualifying p
OK   test_a_photo_not_attested_unedited_does_not_lead_and_does_not_satisfy
OK   test_a_photo_with_no_passed_full_make_behind_it_does_not_lead
FAIL test_owner_attestation_after_planning_moves_the_photo_to_the_front AssertionError()
OK   test_the_dormant_sample_request_asks_for_what_the_intake_requires
OK   test_the_ordering_predicate_is_the_gates_own
OK   test_unedited_at_intake_but_not_owner_attested_is_never_put_first
OK   test_without_a_photo_the_gate_still_refuses
6/8 passed
```

### `tests/test_rehearsal_past_shadow_success.py`

Exit code 1. Last 25 lines of output:

```
[               PASS] taxonomy[simulated]: {'refresh_job': {'id': 9, 'status': 'done', 'last_error': ''}, 'seo_job': {'id': 10, 'status': 'done', 'last_error': ''}, 'category': {'status': 'CHOSEN', 'taxo
[               PASS] owner_phase_transition: {'recorded': [{'to': 'staging', 'transition_id': 38, 'effective_now': 'staging'}, {'to': 'limited_production', 'transition_id': 39, 'effective_now': 'limited_pr
[               PASS] owner_publication_grant: {'approval_id': 40, 'expires_at': '2026-11-23T11:16:22.415020+00:00'}
[             FAILED] store.publish[past-shadow]: {'job': 11, 'status': 'done', 'last_error': '', 'fake_listings': {}, 'create_requests': 0}
[               PASS] network[past-shadow]: {'refused_attempts': 0, 'fake_requests': 3}
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_rehearsal_past_shadow_success.py", line 140, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_rehearsal_past_shadow_success.py", line 115, in test_the_past_shadow_publish_pass_path_creates_exactly_one_draft_under_the_grant
    assert pub["outcome"] == reh.PASS, pub
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: {'step': 'store.publish[past-shadow]', 'outcome': 'FAILED', 'expected': 'exactly one draft created on fake Etsy under the owner grant', 'observed': {'job': 11, 'status': 'done', 'last_error': '', 'fake_listings': {}, 'create_requests': 0}, 'db_proof': {'listings.etsy_listing_id': '', 'store.publish_refused': [], 'store.published': [], 'store.execution_revalidated': []}, 'at': '2026-11-22T11:16:53.978258+00:00'}
FAIL test_the_past_shadow_publish_pass_path_creates_exactly_one_draft_under_the_grant AssertionError({'step': 'store.publish[past-shadow]', 'outcome': 'FAILED', 'expected': 'exactly one draft created on fake Etsy under the owner grant', 'observed': {'job': 11, 'status': 'done', 'last_error': '', 'fake_listings': {}, 'create_requests': 0}, 'db_proof': {'listings.etsy_listing_id': '', 'store.publish_refused': [], 'store.published': [], 'store.execution_revalidated': []}, 'at': '2026-11-22T11:16:53.978258+00:00'})
```

### `tests/test_secret_scan.py`

Exit code 1. Last 25 lines of output:

```
OK   test_a_credential_inside_a_compressed_pdf_stream_is_found
OK   test_a_finding_never_contains_the_matched_value
OK   test_each_credential_family_is_detected_by_its_pattern
OK   test_every_allow_list_entry_still_matches_something_so_the_list_cannot_rot
FAIL test_no_credential_shaped_string_in_tracked_files_evidence_or_generated_artefacts AssertionError('credential-shaped strings found (values withheld):\n  brambleloop/tests/test_b19_security_directive.py:206 db_url_password fp=57231f7290c9\n  brambleloop/tests/test_eng_autocoder.py:476 private_key fp=8bcac7908eb9')
OK   test_placeholders_and_templated_headers_are_not_findings
FAIL test_the_scan_includes_untracked_and_generated_files_not_only_what_git_tracks FileNotFoundError(2, 'No such file or directory')
```

### `tests/test_v11_pwa_static.py`

Exit code 1. Last 25 lines of output:

```
OK structure: view daily exports render
OK structure: view demand exports render
OK structure: view catalogue exports render
OK structure: view completion exports render
OK structure: view policy exports render
OK structure: view operations exports render
OK structure: view learn exports render
OK structure: view insights exports render
OK structure: view notifications exports render
OK structure: view timeline exports render
OK structure: view ask exports render
OK structure: view account exports render
OK structure: view more exports render
OK structure: view drill exports render
OK structure: view emergency exports render
OK structure: relative imports found
OK structure: every relative import resolves
OK structure: no mock/fixture file shipped
OK structure: shipped code never references the mock
FAIL structure: static bundle under 400 KB: 402575
OK money: Unknown wording constant
OK money: formatMoney returns Unknown for unknown values
OK money: contract value_cad null never coerced
OK money: no `value ?? 0` / `amount || 0` coercion anywhere
86 passed, 1 failed
```

### `tests/test_w3_tmp_hygiene.py`

Exit code 1. Last 25 lines of output:

```
OK   test_a_child_terminated_by_sigterm_or_interrupted_leaves_nothing
OK   test_a_child_that_fails_an_assertion_and_sys_exits_nonzero_leaves_nothing
OK   test_a_child_that_raises_half_way_leaves_nothing
OK   test_a_child_that_uses_every_temp_api_and_exits_cleanly_leaves_nothing
OK   test_a_forked_child_does_not_remove_its_parents_sandbox
FAIL test_a_run_killed_with_sigkill_is_swept_by_the_next_run AssertionError()
OK   test_code_outside_tests_that_creates_temp_files_has_a_cleanup_path
OK   test_every_test_file_that_creates_temp_files_installs_the_sandbox_first
OK   test_formerly_leaking_test_files_leave_their_tmpdir_empty_when_they_pass
OK   test_install_is_idempotent_and_points_tempfile_and_the_environment_at_the_sandbox
OK   test_scoped_removes_its_directory_when_the_block_raises
OK   test_the_guard_itself_catches_a_bare_mkdtemp_and_a_delete_false_tempfile
FAIL test_the_harness_removes_its_run_tmpdir_when_it_is_terminated AssertionError()
FAIL test_the_harness_reports_each_suites_leak_and_removes_its_run_tmpdir_on_failure AssertionError('')
OK   test_the_production_temp_census_and_the_test_sandbox_agree
FAIL test_tmp_leak_strict_makes_a_passing_but_leaking_suite_fail AssertionError('')
```

### `tests/test_w4_close5_rows3.py`

Exit code 1. Last 25 lines of output:

```
OK   test_f542_a_rollback_etsy_accepted_but_did_not_apply_is_not_recorded_restored
OK   test_f542_an_activation_etsy_accepted_but_did_not_apply_is_not_recorded_live
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_close5_rows3.py", line 186, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_close5_rows3.py", line 97, in test_f542_every_customer_affecting_etsy_mutation_is_followed_by_a_readback
    assert not unchecked, ("Etsy writes with no read-back after them in the same function: "
           ^^^^^^^^^^^^^
AssertionError: Etsy writes with no read-back after them in the same function: ['runtime/pipeline.py::_complete_draft:3012 set_listing_property', 'runtime/pipeline.py::_complete_draft:2980 attach_file', 'runtime/pipeline.py::_complete_draft:3003 upload_image', 'runtime/pipeline.py::_publish_and_read_back:3106 publish', 'runtime/pipeline.py::_publish_and_read_back:3157 set_listing_property', 'runtime/pipeline.py::_publish_and_read_back:3165 attach_file']. Read the field back, or record why it cannot affect a customer in DRAFT_ONLY
FAIL test_f542_every_customer_affecting_etsy_mutation_is_followed_by_a_readback AssertionError("Etsy writes with no read-back after them in the same function: ['runtime/pipeline.py::_complete_draft:3012 set_listing_property', 'runtime/pipeline.py::_complete_draft:2980 attach_file', 'runtime/pipeline.py::_complete_draft:3003 upload_image', 'runtime/pipeline.py::_publish_and_read_back:3106 publish', 'runtime/pipeline.py::_publish_and_read_back:3157 set_listing_property', 'runtime/pipeline.py::_publish_and_read_back:3165 attach_file']. Read the field back, or record why it cannot affect a customer in DRAFT_ONLY")

FAIL: 1 failing of 3
```

### `tests/test_w4_visnext2.py`

Exit code 1. Last 25 lines of output:

```
FAIL test_cloudline_acceptance_dry_run_end_to_end_through_the_experiment_command Refused('definition drift: prompt builder flux3-prompt-builder/2.2.0 is not the frozen flux3-prompt-builder/2.1.1')
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_visnext2.py", line 491, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_visnext2.py", line 412, in test_shared_cap_is_counted_once_across_both_definitions
    C.authorize(db, "exp-2026-10-21-cloudline-acceptance", by="owner", stepped_up=True)
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/project-money/brambleloop/src/brambleloop/experiments/controlled.py", line 319, in authorize
    raise ControlledRefused("the definition's inputs drifted; nothing is authorized: "
                            + "; ".join(v["problems"]))
brambleloop.experiments.controlled.ControlledRefused: the definition's inputs drifted; nothing is authorized: prompt builder flux3-prompt-builder/2.2.0 is not the frozen flux3-prompt-builder/2.1.1
FAIL test_shared_cap_is_counted_once_across_both_definitions ControlledRefused("the definition's inputs drifted; nothing is authorized: prompt builder flux3-prompt-builder/2.2.0 is not the frozen flux3-prompt-builder/2.1.1")
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_visnext2.py", line 491, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_visnext2.py", line 435, in test_pipeline_definition_drift_and_foreign_runs_are_refused_before_spend
    assert v["ok"], v["problems"]                                      # make_db certifies it
           ~^^^^^^
AssertionError: ['prompt builder flux3-prompt-builder/2.2.0 is not the frozen flux3-prompt-builder/2.1.1']
FAIL test_pipeline_definition_drift_and_foreign_runs_are_refused_before_spend AssertionError(['prompt builder flux3-prompt-builder/2.2.0 is not the frozen flux3-prompt-builder/2.1.1'])
OK   test_live_acceptance_refuses_without_keys

9 passed, 3 failed
```
