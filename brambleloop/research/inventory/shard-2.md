# Test inventory: shard 2 of 4

This is an inventory only. It is not a release record, and nothing here was fixed.

- Run ID: `20261122T105143Z-584`
- Commit: `74b749f864f246b1bc402d2f266b120ad3a0f022` (tree clean at start, HEAD unchanged at end)
- Command: `CHECKPOINT=1 SHARD=2/4 JOBS=4 bash run_tests.sh` (python /usr/bin/python3.11, venv from `requirements.lock` + `requirements-test.lock`)
- Started 2026-11-22T10:51:44Z, finished 2026-11-22T12:27:45Z, duration 5762s
- Release eligible: False. shard run: a checkpointed, resumed or sharded run never certifies a release (owner decision D-W4-OWNER-RESUME-POLICY; W4-RESUMEFIX F1)

## Counts

| | Suites |
|---|---|
| In shard 2/4 | 284 |
| Passing | 273 |
| Failing | 11 |

Individual tests: 3533 passing, 13 reported failing, 2 reported skipped. The runner classed 0 of the failing suites as environment failures (ENOSPC, permission, network or provider).

## Failing suites

### `tests/test_cert_wiring.py`

Exit code: 1. Last 25 lines of output:

```
   FAIL test_every_target_is_scheduled_handled_and_permitted_statically AssertionError: queue did not drain: 307 jobs in 1570s
    drain made 2 deferred job(s) due: ['launch.plan', 'sale.pipeline']
   OK   test_each_target_was_enqueued_by_its_cadence_and_executed_to_done
   OK   test_no_job_in_the_drain_died_except_by_deliberate_refusal
   OK   test_scheduler_tick_calls_priority_for_and_bands_every_cadence_job
   OK   test_follow_on_work_is_enqueued_at_its_band_too
   FAIL test_swarm_handlers_reach_their_runtime_functions AssertionError: agent_quality was never called by its handler
   FAIL test_weekly_cycle_calls_retirement_review_autopsy_memory_and_director AssertionError: retirement_review not reached from improve.weekly
   OK   test_retrospective_reaches_cells_and_reports_the_new_sections
   OK   test_listing_draft_actually_runs_the_disclosure_check
   OK   test_growth_experiments_calls_launch_pack_for_every_drafted_listing
   OK   test_mjs_scan_consults_the_adaptive_interval_before_any_request
   OK   test_store_publish_walks_the_escalation_ladder_on_a_failed_parity_dimension
   OK   test_record_order_writes_the_bought_version
   /home/user/project-money/brambleloop/.venv/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
 from starlette.testclient import TestClient as TestClient  # noqa
   OK   test_api_paths_reach_radar_memory_and_the_stress_test
   FAIL test_radar_memory_is_read_by_some_agent_at_runtime AssertionError: culture.radar.memory() was not called by any job in a full drain (culture.sweep calls route_findings, not memory/sweep); its only caller is GET /api/culture
     registry status of the 17 wiring rows: {41: 'partial', 42: 'covered', 81: 'covered', 85: 'covered', 91: 'covered', 100: 'covered', 144: 'covered', 174: 'covered', 175: 'covered', 176: 'covered', 186: 'covered', 187: 'covered', 192: 'covered', 241: 'partial', 265: 'partial', 270: 'partial', 313: 'covered'}
   FAIL test_no_row_whose_wiring_failed_here_is_still_claimed_covered AssertionError: claimed covered but not wired at runtime: {144: 'covered'}
   11/16 passed in 1758s
```

### `tests/test_etsy_publish_e2e.py`

Exit code: 1. Last 25 lines of output:

```
   [               PASS] taxonomy[simulated]: {'refresh_job': {'id': 9, 'status': 'done', 'last_error': ''}, 'seo_job': {'id': 10, 'status': 'done', 'last_error': ''}, 'category': {'status': 'CHOSEN', 'taxo
   [               PASS] owner_phase_transition: {'recorded': [{'to': 'staging', 'transition_id': 38, 'effective_now': 'staging'}, {'to': 'limited_production', 'transition_id': 39, 'effective_now': 'limited_pr
   Traceback (most recent call last):
 File "/home/user/project-money/brambleloop/tests/test_etsy_publish_e2e.py", line 426, in <module>
   fn()
 File "/home/user/project-money/brambleloop/tests/test_etsy_publish_e2e.py", line 228, in test_package_to_draft_rollback_adoption_and_refusals
   first_id = str(job["outputs"]["etsy_listing_id"])
                  ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
   KeyError: 'etsy_listing_id'
   FAIL test_package_to_draft_rollback_adoption_and_refusals KeyError('etsy_listing_id')
   OK   test_two_matching_drafts_or_a_live_one_escalate_and_nothing_is_created
   OK   test_the_fee_budget_refuses_above_one_fee_per_listing_and_beyond_six_dollars
```

### `tests/test_final_closure_matrix.py`

Exit code: 1. Last 25 lines of output:

```
   OK   test_a_fact_only_tests_write_cannot_hold_integrated
   OK   test_a_worker_claim_above_its_evidence_is_lowered_with_a_reason
   OK   test_all_proxy_evidence_refuses_integrated_but_one_direct_item_does_not
   FAIL test_basis_names_the_actual_mapping_commits AssertionError('019ebf0eeb36789aa62ddf7be9bfb6ba3995853a')
   OK   test_completion_is_computed_per_row_and_the_open_count_is_summarised
   OK   test_every_registry_record_is_mapped_exactly_once_without_problems
   OK   test_every_row_states_protected_action_applicability
   OK   test_exercised_rows_cite_a_committed_production_artefact
   OK   test_integrated_rows_have_a_producer_reached_from_a_live_root
   OK   test_launch_scope_classifies_every_row_and_every_reclassification_has_a_reason
   OK   test_no_row_claims_commercial_evidence_that_does_not_exist
   OK   test_the_committed_matrix_is_exactly_its_adjudication
```

### `tests/test_release_versions.py`

Exit code: 1. Last 25 lines of output:

```
   FAIL test_no_content_change_keeps_a_released_version AssertionError('harbour-drop-shoulder-pullover-2x@1.3.0: content changed (83cc0b73c2f4 -> 2023cd2a5fed) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-3x@1.3.0: content changed (e30eed41d47f -> 31ea804cd6e0) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-4x@1.3.0: content changed (364d0ca51b18 -> 7f7c5bf4a844) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-5x@1.3.0: content changed (7a15e6379539 -> d262fa67b707) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-l@1.3.0: content changed (a852216400d6 -> 71ddc74bb135) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-m@1.3.0: content changed (5bf0678b9d1a -> 6aeb40326d76) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-s@1.3.0: content changed (55527d3be3bb -> 2fb9a42e85bf) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-xl@1.3.0: content changed (baab131a56d9 -> 949d4fe7e77a) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-xs@1.3.0: content changed (bd3c15d8616c -> 33cf9a3309d3) but the version did not -- a released version cannot change content; bump it')
   OK   test_the_check_catches_a_claims_change_under_the_same_version
   FAIL test_the_check_catches_a_content_change_under_the_same_version AssertionError(['chunky-ribbed-scarf: version 1.0.0 -> 1.1.0 but the pinned row was not updated; update version and fingerprint together', 'harbour-drop-shoulder-pullover-2x@1.3.0: content changed (83cc0b73c2f4 -> 2023cd2a5fed) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-3x@1.3.0: content changed (e30eed41d47f -> 31ea804cd6e0) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-4x@1.3.0: content changed (364d0ca51b18 -> 7f7c5bf4a844) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-5x@1.3.0: content changed (7a15e6379539 -> d262fa67b707) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-l@1.3.0: content changed (a852216400d6 -> 71ddc74bb135) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-m@1.3.0: content changed (5bf0678b9d1a -> 6aeb40326d76) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-s@1.3.0: content changed (55527d3be3bb -> 2fb9a42e85bf) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-xl@1.3.0: content changed (baab131a56d9 -> 949d4fe7e77a) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-xs@1.3.0: content changed (bd3c15d8616c -> 33cf9a3309d3) but the version did not -- a released version cannot change content; bump it'])
   OK   test_the_pt_redesigns_carry_a_new_version
```

### `tests/test_v11_pwa_browser.py`

Exit code: 1. Last 25 lines of output:

```
   OK login: labelled passphrase field
   OK login: wrong passphrase refused with message
   FAIL check aborted: page.waitForSelector: Timeout 30000ms exceeded. Call log: [2m  - waiting for locator('.hero') to be visible[22m
   SUMMARY passes=2 failures=1 screenshots=0
```

### `tests/test_w4_autonomy_idle_departments.py`

Exit code: 1. Last 25 lines of output:

```
   OK   test_a_department_with_due_work_is_still_busy
   OK   test_a_long_idempotency_key_is_fitted_deterministically
   OK   test_a_waiting_handoff_consumer_is_not_duplicated
   Traceback (most recent call last):
 File "/home/user/project-money/brambleloop/tests/test_w4_autonomy_idle_departments.py", line 312, in <module>
   fn()
 File "/home/user/project-money/brambleloop/tests/test_w4_autonomy_idle_departments.py", line 221, in test_a_wide_rebuild_fits_the_varchar_200_key_column
   assert len(first["enqueued"]) == len(slugs), first["enqueued"]
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   AssertionError: ['pdf:autumn-oak-mosaic-throw.pdf', 'pdf:cloudline-baby-blanket.pdf', 'pdf:harvest-table-runner.pdf', 'pdf:mosaic-placemat-pair.pdf', 'pdf:nordic-forest-mosaic-throw.pdf', 'pdf:nordic-star-ornaments.pdf', 'pdf:pet-snuggle-mat.pdf', 'pdf:pressed-flower-motifs.pdf', 'pdf:pumpkin-cluster-set.pdf', 'pdf:spooky-garland.pdf', 'pdf:valentine-heart-garland.pdf', 'pdf:winter-village-graphghan.pdf']
```

### `tests/test_w4_fmbatch1_licenses.py`

Exit code: 1. Last 25 lines of output:

```
   Traceback (most recent call last):
 File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_licenses.py", line 58, in <module>
   fn()
 File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_licenses.py", line 15, in test_register_is_complete
   assert L.check() == [], L.check()
          ^^^^^^^^^^^^^^^
   AssertionError: ['font Lato is bundled with no licence row', 'font NotoSerifDisplay is bundled with no licence row']
```

### `tests/test_w4_fmbatch1_lifecycle.py`

Exit code: 1. Last 25 lines of output:

```
   Traceback (most recent call last):
 File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_lifecycle.py", line 99, in <module>
   fn()
 File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_lifecycle.py", line 58, in test_stages_follow_the_rows
   assert L.derive(db, "x")["stage"] == "LISTING_READY"
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   AssertionError
```

### `tests/test_w4_fmbatch1_provider_boundary.py`

Exit code: 1. Last 25 lines of output:

```
   Traceback (most recent call last):
 File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_provider_boundary.py", line 162, in <module>
   fn()
 File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_provider_boundary.py", line 57, in test_no_new_direct_vendor_importer_and_pending_only_shrinks
   assert not new, f"business modules importing a vendor module directly: {new}"
          ^^^^^^^
   AssertionError: business modules importing a vendor module directly: ['creative/toy_board.py', 'improve/autocoder.py', 'ops/owner_directives.py']
```

### `tests/test_w4_launchfix.py`

Exit code: 1. Last 25 lines of output:

```
   OK IMG passes: a bound, unedited, first sample photo satisfies this gate; copy follows facts
   OK IMG stage: no photo does not block the private draft; it blocks activation
   Traceback (most recent call last):
 File "/home/user/project-money/brambleloop/tests/test_w4_launchfix.py", line 1199, in <module>
   fn()
 File "/home/user/project-money/brambleloop/tests/test_w4_launchfix.py", line 803, in test_img_stage_only_activation_asks_for_the_activation_stage_and_nothing_internal_does
   assert users == ["brambleloop/gates/platform_policy.py",
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   AssertionError: ['brambleloop/gates/platform_policy.py', 'brambleloop/ops/approve_all_directive.py', 'brambleloop/publish/photo_asset_review.py', 'brambleloop/publish/physical_upgrade.py', 'brambleloop/publish/release_gates.py', 'brambleloop/runtime/release.py']
   FAIL test_img_stage_only_activation_asks_for_the_activation_stage_and_nothing_internal_does
   OK F-1: an ops-token first reading is a material change with an owner review card
   OK F-2: unsealed or forged evidence rows and unconfirmed removals never pass
   OK F-3: a sealed live run older than the evidence window does not pass
   OK F-4: a live run that created no draft cannot borrow another run's round trip
   OK F-5: exact Etsy host; an injected transport's run is not evidence
   OK F-6: a change to any sealed fee term (rate, period, reading, CAD fee) is re-asked
   OK F-7: recorded renders/generations, a non-photo first frame and an unattested photo fail
   OK F-8: the brand_clearance request asks for the risk acceptance; filing is optional
   OK CC: session, CSRF, step-up and a fresh nonce are all required; the ops token is not
   OK CC: digest only, same intake row + attestation, baseline then change, duplicate refused
   OK CC refuses: no answers, wrong confirmation, empty text, unknown source, long version, future date, wrong confirmation for a fetched article
   OK CC: Help Center text fetched from Etsy's article API; legal pages must be pasted
   OK CC: #/policy view is in the offline shell, routed, and linked from Approvals/Completion
   
   31 passed, 1 failed
```

### `tests/test_w4_relfix_release_log.py`

Exit code: 1. Last 25 lines of output:

```
   FAIL test_a_tampered_or_missing_full_log_refuses_the_release AssertionError({'ok': False, 'reasons': ['no release-eligible local suite run record for 058c5a2b7d7a']})
   FAIL test_record_writes_a_summary_into_release_and_the_full_log_outside_it AssertionError({'ok': False, 'reasons': ['no release-eligible local suite run record for 058c5a2b7d7a']})
   OK   test_the_shipped_release_directory_holds_only_summaries_with_pinned_full_logs
   OK   test_the_summary_carries_no_session_marker_and_paths_become_repo_relative
```
