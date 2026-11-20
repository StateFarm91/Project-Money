CERT: FAIL b098fccea62b9f2647b9356a24c99c5df1fe3534

Run 20261120T135054Z-24957: 1016 suites, 35 failing, 12184 tests passing, 68 tests failing. JOBS=8, tree clean, duration 18223s. Venv created from requirements.lock + requirements-test.lock; no code changed.

## Failing suites

- `tests/test_cert_design.py`: FAIL test_every_fresh_concept_compiles_writes_reverses_and_certifies  -- AssertionError: [('acorn-drop', 'certify', ['ERROR CHILD_SAFETY_JOINS_VALIDATED: a sewn join does not say it is sewn through both loops with the tail buried'])]
- `tests/test_cert_parity_copy.py`: FAIL test_listing_seo_applies_the_query_portfolio_to_its_tags AssertionError()
- `tests/test_cert_rebuild_chain.py`: AssertionError: {'ready': False, 'questions': {'ready': False, 'answers': {'findable': {'question': 'Can buyers find it?', 'pass': True, 'checked': ['catalogue_depth', 'launch_calendar', 'analytics_baseline'], 'failing': [], 'blocked_by': []}, 'clickable': {'question': 'Will they click?', 'pass': Fa
- `tests/test_cert_wiring.py`: FAIL test_every_target_is_scheduled_handled_and_permitted_statically AssertionError: queue did not drain: 231 jobs in 1528s
- `tests/test_eng_catalogue_perf.py`: FAIL test_cold_catalogue_read_at_production_scale_is_not_quadratic AssertionError('2.7s cold read: per-product scans of all jobs/audits')
- `tests/test_fastlane.py`: FAIL test_the_canonical_stage_list_matches_what_the_chain_actually_runs: ['child_safety']
- `tests/test_final_closure_matrix.py`: FAIL test_basis_names_the_actual_mapping_commits AssertionError('0417f3516f30bb7c52926187fc475a0f46536e86')
- `tests/test_opus2_size_claims.py`: FAIL test_a_graded_release_size_chart_is_reference_but_its_listing_may_not_promise_sizes AssertionError(['size-claim truth: the customer PDF promises 9 sizes (9 sizes) but this release delivers 1 size of instructions; name only the size it delivers, or sell each size as its own certified release'])
- `tests/test_physfix.py`: FAIL test_both_kits_rebuild_byte_identical_from_the_one_builder AssertionError('basket_small')
- `tests/test_platform.py`: FAIL test_every_scheduled_cadence_survives_actually_being_run AssertionError(['ops.continuity: OperationalError: (sqlite3.OperationalError) no such table: radar_concepts\n[SQL: SELECT radar_concepts.id, radar_concepts.at, radar_concepts.slug, radar_concepts.state, radar_concepts.source, radar_co'])
- `tests/test_provenance_write_path.py`: FAIL test_moving_the_stored_design_turns_the_whole_chain_stale_and_blocks_the_slug AssertionError()
- `tests/test_r2_autonomy_useful_work.py`: AssertionError: ['improve.self_tune']
- `tests/test_r5_research_2.py`: FAIL test_h1_the_real_cadence_takes_a_new_arena_to_an_approved_concept
- `tests/test_r5_research_3.py`: FAIL test_h3_an_approved_concept_stays_approved_while_evidence_stays_fresh
- `tests/test_r5_research_4.py`: FAIL test_m1_withdraw_then_relist_is_re_proposed_through_the_daily_cycle
- `tests/test_s1_fix_size_families.py`: FAIL test_main_h2_examples_are_drafted_at_the_asked_size_or_refused AssertionError(('Large Tapestry 100 x 150 cm', {'family': 'refused', 'needs': "an end-to-end colourwork proof for 'wall_decor'", 'why': 'no end-to-end proof for a charted wall hanging yet', 'colourwork': 'colourwork_tapestry'}))
- `tests/test_s1_product_truth_2.py`: FAIL test_m1_relative_size_words_follow_one_rule AssertionError(('Large Tapestry 100 x 150 cm', {'family': 'refused', 'needs': "an end-to-end colourwork proof for 'wall_decor'", 'why': 'no end-to-end proof for a charted wall hanging yet', 'colourwork': 'colourwork_tapestry'}))
- `tests/test_shadow.py`: FAIL test_a_product_that_stops_certifying_has_its_listing_withdrawn AssertionError('draft')
- `tests/test_swarm_runtime.py`: FAIL test_every_runnable_job_type_has_a_band_decided_rather_than_defaulted AssertionError("['improve.self_tune'] would be enqueued at a band nobody decided")
- `tests/test_v11_cc_views.py`: AssertionError: ('/api/cc/autonomy', 'learning')
- `tests/test_w3_decision_index.py`: FAIL test_the_index_matches_the_log AssertionError('src/brambleloop/core/decision_index.json is stale: run `PYTHONPATH=src python -m brambleloop.core.decision_index`')
- `tests/test_w3_tmp_hygiene.py`: FAIL test_every_test_file_that_creates_temp_files_installs_the_sandbox_first AssertionError('these test files create temporary files without `import _tmp; _tmp.install()` at the top (tests/_tmp.py): test_eng_improve_readback.py:24')
- `tests/test_w4_close6_timeline.py`: AssertionError: ['orchestrator supply.admit', 'cloudline-baby-blanket 1.2.0: validator compiled the pattern → quality_director certified the release → listing wrote the title, tags and description → store_operator tried to publish to Etsy']
- `tests/test_w4_contracts.py`: FAIL test_a_version_bump_must_be_declared_and_regenerated AssertionError()
- `tests/test_w4_fmbatch1_adoptions.py`: AssertionError
- `tests/test_w4_fmbatch1_contracts.py`: AssertionError: the CIR contract changed (6c88ab1543d4c5eb -> c336ab900d391017). Declare it: add a dated row to ops/CONTRACT_CHANGES.md naming the change and how dependants pin or migrate, then update PINNED_CIR in this file in the same commit
- `tests/test_w4_fmbatch1_drift.py`: AssertionError: ['hexagon-coaster-set', 'market-basket-small', 'cloudline-baby-blanket', 'nordic-star-ornaments', 'winter-village-graphghan', 'nordic-forest-mosaic-throw-baby']
- `tests/test_w4_fmbatch1_licenses.py`: AssertionError: ['package flatbuffers is locked with no licence row', 'package onnxruntime is locked with no licence row', 'package packaging is locked with no licence row', 'package protobuf is locked with no licence row']
- `tests/test_w4_wire1_routes.py`: FAIL test_the_route_contract_pin_moved_with_a_declaration AssertionError('48d0a4f03ed96fca')
- `tests/test_w5_a9_package_event.py`: FAIL test_a_redelivered_or_second_event_creates_no_duplicate AssertionError()
- `tests/test_w6_listing_chain_e2e.py`: FAIL test_a_every_stage_ran_from_the_job_its_predecessor_enqueued AssertionError(('cir.draft', [(1, <JobStatus.DONE: 'done'>), (17, <JobStatus.DONE: 'done'>), (33, <JobStatus.DONE: 'done'>), (49, <JobStatus.DONE: 'done'>), (69, <JobStatus.DONE: 'done'>), (88, <JobStatus.DONE: 'done'>), (108, <JobSta
- `tests/test_ws2_r5_proposal_writer.py`: FAIL test_the_proposal_passes_intake_end_to_end_through_the_real_handler
- `tests/test_ws2_research_m2.py`: FAIL test_three_days_of_corroboration_reach_an_approved_concept_unattended
- `tests/test_ws4_7_postgres.py`: FAIL test_the_worker_role_never_creates_a_table_it_should_not_own AssertionError({'rc': 3})
- `tests/test_ws4_stage_a_withdrawal.py`: FAIL test_a_withdrawal_needs_lineage_a_stopped_policy_a_rate_and_an_active_read_back TypeError("argument of type 'NoneType' is not iterable")
