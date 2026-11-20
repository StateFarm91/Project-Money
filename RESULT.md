CERT: FAIL dde3ea62d84c88f81b366d019600b820b34d87c2

Run 20261120T121636Z-24696: 1008 suites, 29 failing, TOTAL PASSING 11940, duration 14478s, tree clean, 0 environment failures.
Interpreter: system python3.13 via PY override (default .venv/bin/python absent; an earlier run with it failed all 1008 suites instantly and is discarded). Installed requirements.lock + requirements-test.lock.

## Failing suites (first assertion line)

- `tests/test_cert_parity_copy.py` — FAIL test_listing_seo_applies_the_query_portfolio_to_its_tags AssertionError()
- `tests/test_cert_rebuild_chain.py` — FAIL test_launch_readiness_measures_the_launch_package_from_what_the_chain_produced AssertionError({'ready': False, 'questions': {'ready': False, 'answers': {'findable': {'question': 'Can buyers find it?', 'pass': True, 'checked': ['catalogue_depth', 'launch_c
- `tests/test_cert_wiring.py` — FAIL test_every_target_is_scheduled_handled_and_permitted_statically AssertionError: queue did not drain: 268 jobs in 1534s
- `tests/test_codex_v1_blind_comparison.py` — FAIL test_incomplete_description_is_never_an_anchor_comparison_pass
- `tests/test_codex_v1_craft_enum.py` — FAIL test_absent_or_malformed_craft_reading_is_not_an_edit_base
- `tests/test_codex_v1_spend_guard.py` — FAIL test_bad_plan_amounts_are_refused
- `tests/test_deploy.py` — process aborted natively (bad_variant_access thrown in -fno-exceptions mode); no FAIL/assertion line emitted
- `tests/test_eng_catalogue_perf.py` — FAIL test_cold_catalogue_read_at_production_scale_is_not_quadratic AssertionError('2.5s cold read: per-product scans of all jobs/audits')
- `tests/test_provenance_write_path.py` — FAIL test_moving_the_stored_design_turns_the_whole_chain_stale_and_blocks_the_slug AssertionError()
- `tests/test_r2_autonomy_useful_work.py` — FAIL test_every_cadence_and_generatable_type_declares_its_work_keys AssertionError(['improve.self_tune'])
- `tests/test_r5_research_2.py` — FAIL test_h1_the_real_cadence_takes_a_new_arena_to_an_approved_concept
- `tests/test_r5_research_3.py` — FAIL test_h3_an_approved_concept_stays_approved_while_evidence_stays_fresh
- `tests/test_r5_research_4.py` — FAIL test_m1_withdraw_then_relist_is_re_proposed_through_the_daily_cycle
- `tests/test_shadow.py` — FAIL test_a_product_that_stops_certifying_has_its_listing_withdrawn AssertionError('draft')
- `tests/test_swarm_runtime.py` — FAIL test_every_runnable_job_type_has_a_band_decided_rather_than_defaulted AssertionError("['improve.self_tune'] would be enqueued at a band nobody decided")
- `tests/test_v11_cc_views.py` — FAIL test_every_tab_answers_and_carries_status_envelopes AssertionError: ('/api/cc/autonomy', 'learning')
- `tests/test_w3_decision_index.py` — FAIL test_the_index_matches_the_log AssertionError('src/brambleloop/core/decision_index.json is stale: run `PYTHONPATH=src python -m brambleloop.core.decision_index`')
- `tests/test_w3_tmp_hygiene.py` — FAIL test_every_test_file_that_creates_temp_files_installs_the_sandbox_first AssertionError('these test files create temporary files without `import _tmp; _tmp.install()` at the top (tests/_tmp.py): test_eng_improve_readback.py:24')
- `tests/test_w4_close6_timeline.py` — FAIL test_a_pipeline_run_is_one_causal_story_across_departments AssertionError(['orchestrator supply.admit', 'cloudline-baby-blanket 1.2.0: validator compiled the pattern → quality_director certified the release → listing wrote the title, tags and description 
- `tests/test_w4_fmbatch1_contracts.py` — AssertionError: contract(s) changed: {'api_routes': ('750cd12d5d99f93d', '48d0a4f03ed96fca')}. Declare each in ops/CONTRACT_CHANGES.md (what changed, how dependants pin or migrate) and update PINNED in this file in the same commit
- `tests/test_w4_fmbatch1_drift.py` — FAIL test_a_change_elsewhere_in_the_tree_leaves_a_valid_listing_alone AssertionError(['hexagon-coaster-set', 'market-basket-small', 'cloudline-baby-blanket', 'nordic-star-ornaments', 'winter-village-graphghan', 'nordic-forest-mosaic-throw-baby'])
- `tests/test_w4_prodready_deps.py` — FAIL test_every_third_party_import_under_src_is_locked: AssertionError: onnxruntime (distribution ['onnxruntime']) is imported at src/brambleloop/visual/face_embedder.py:149 but is not pinned in requirements.lock
- `tests/test_w4_wire1_routes.py` — FAIL test_the_route_contract_pin_moved_with_a_declaration AssertionError('48d0a4f03ed96fca')
- `tests/test_w5_a9_package_event.py` — FAIL test_a_redelivered_or_second_event_creates_no_duplicate AssertionError()
- `tests/test_w6_listing_chain_e2e.py` — FAIL test_a_every_stage_ran_from_the_job_its_predecessor_enqueued AssertionError(('cir.draft', [(1, <JobStatus.DONE: 'done'>), (17, <JobStatus.DONE: 'done'>), (33, <JobStatus.DONE: 'done'>), (49, <JobStatus.DONE: 'done'>), (69, <JobStatus.DONE: 'done'>), (88, 
- `tests/test_ws2_r5_proposal_writer.py` — FAIL test_the_proposal_passes_intake_end_to_end_through_the_real_handler
- `tests/test_ws2_research_m2.py` — FAIL test_three_days_of_corroboration_reach_an_approved_concept_unattended
- `tests/test_ws4_7_postgres.py` — FAIL test_the_worker_role_never_creates_a_table_it_should_not_own AssertionError({'rc': 3})
- `tests/test_ws4_stage_a_withdrawal.py` — FAIL test_a_withdrawal_needs_lineage_a_stopped_policy_a_rate_and_an_active_read_back TypeError("argument of type 'NoneType' is not iterable")
