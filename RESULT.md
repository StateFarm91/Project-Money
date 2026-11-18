# Certification result — 1883167c25e47b2a72f8643f8c84b30b272d761a

```
TOTAL PASSING: 11408 ; suites failing: 8
ENVIRONMENT FAILURES: 0 of the 8 failing suites (ENOSPC/permission/network/provider; F-150)
RUN FINISHED: 2026-11-18T22:25:52Z
DURATION: 10387s
GIT SHA: 1883167c25e47b2a72f8643f8c84b30b272d761a (tree clean at start)
RUN RECORD: artifacts/suite_runs/20261118T193245Z-1912.json (failed)
```

Failing suites (8): tests/test_cert_spend_hosts.py, tests/test_deliverable_qa.py, tests/test_seasonal_cycle.py, tests/test_vacuity.py, tests/test_w3_spend_attribution.py, tests/test_w3_tmp_hygiene.py, tests/test_w4_close5_rows3.py, tests/test_w4_resume_runner.py

## tests/test_cert_spend_hosts.py

FAIL lines:
```
   FAIL test_every_file_addressing_a_paid_provider_is_declared AssertionError("undeclared paid-provider callers: ['brambleloop/gateway/openai_chat.py']")
   FAIL: 1 failing
```
First 40 lines of traceback/assertion output:
```
   FAIL test_every_file_addressing_a_paid_provider_is_declared AssertionError("undeclared paid-provider callers: ['brambleloop/gateway/openai_chat.py']")
   FAIL: 1 failing
```

## tests/test_deliverable_qa.py

FAIL lines:
```
   FAIL test_a_childrens_document_missing_a_statement_is_refused_rather_than_shipped AssertionError("cloudline-baby-blanket: the existing children's assignment does not bind this exact design and version. Held pending an explicit authorized decision.")
   FAIL test_the_greyscale_warning_names_the_colours_that_merge ChildrensDecisionRequired("cloudline-baby-blanket: the existing children's assignment does not bind this exact design and version. Held pending an explicit authorized decision.")
```
First 40 lines of traceback/assertion output:
```
   FAIL test_a_childrens_document_missing_a_statement_is_refused_rather_than_shipped AssertionError("cloudline-baby-blanket: the existing children's assignment does not bind this exact design and version. Held pending an explicit authorized decision.")
   FAIL test_the_greyscale_warning_names_the_colours_that_merge ChildrensDecisionRequired("cloudline-baby-blanket: the existing children's assignment does not bind this exact design and version. Held pending an explicit authorized decision.")
```

## tests/test_seasonal_cycle.py

FAIL lines:
```
   FAIL test_a_cycle_that_completes_says_so_only_when_the_buyer_arithmetic_holds AssertionError(['certify'])
   FAIL test_a_gated_step_is_named_and_never_simulated AssertionError({})
   FAIL test_a_model_frames_floors_are_reported_as_themselves StopIteration()
   FAIL test_an_asset_maker_closes_the_link_and_the_endpoint_never_gets_one StopIteration()
   FAIL test_our_own_unfinished_work_fails_the_cycle_instead_of_gating_it StopIteration()
   FAIL test_the_assets_step_evidences_this_cycles_product_and_never_another StopIteration()
   FAIL test_the_cycle_runs_every_link_it_can_and_names_the_ones_it_cannot AssertionError({'observe': 'ran', 'classify': 'ran', 'choose_event': 'ran', 'launch_date': 'ran', 'generate': 'ran', 'engineer': 'ran', 'certify': 'failed'})
   FAIL test_the_makers_own_refusal_outranks_the_structural_guess StopIteration()
```
First 40 lines of traceback/assertion output:
```
   FAIL test_a_cycle_that_completes_says_so_only_when_the_buyer_arithmetic_holds AssertionError(['certify'])
   FAIL test_a_gated_step_is_named_and_never_simulated AssertionError({})
   FAIL test_a_model_frames_floors_are_reported_as_themselves StopIteration()
   FAIL test_an_asset_maker_closes_the_link_and_the_endpoint_never_gets_one StopIteration()
   FAIL test_our_own_unfinished_work_fails_the_cycle_instead_of_gating_it StopIteration()
   FAIL test_the_assets_step_evidences_this_cycles_product_and_never_another StopIteration()
   FAIL test_the_cycle_runs_every_link_it_can_and_names_the_ones_it_cannot AssertionError({'observe': 'ran', 'classify': 'ran', 'choose_event': 'ran', 'launch_date': 'ran', 'generate': 'ran', 'engineer': 'ran', 'certify': 'failed'})
   FAIL test_the_makers_own_refusal_outranks_the_structural_guess StopIteration()
```

## tests/test_vacuity.py

FAIL lines:
```
   FAIL test_no_new_vacuous_risk_loop_anywhere_in_the_suite AssertionError('loops that assert over a possibly empty iterable (add a non-emptiness assertion, or `# vacuity-ok: <reason>` if emptiness is the behaviour):\n  test_r5_research_4.py:100 in test_m1_a_relisted_and_changed_listing_keeps_its_withdrawal_history: for ... in rows.values()\n  test_s1_product_truth.py:115 in test_every_template_and_title_route_writes_the_size_its_twin_has_and_reverse_compiles: for ... in titles\n  test_s2_openai_provider.py:184 in test_failures_are_classified_declined_or_uncertain: for ... in cases')
```
First 40 lines of traceback/assertion output:
```
   FAIL test_no_new_vacuous_risk_loop_anywhere_in_the_suite AssertionError('loops that assert over a possibly empty iterable (add a non-emptiness assertion, or `# vacuity-ok: <reason>` if emptiness is the behaviour):\n  test_r5_research_4.py:100 in test_m1_a_relisted_and_changed_listing_keeps_its_withdrawal_history: for ... in rows.values()\n  test_s1_product_truth.py:115 in test_every_template_and_title_route_writes_the_size_its_twin_has_and_reverse_compiles: for ... in titles\n  test_s2_openai_provider.py:184 in test_failures_are_classified_declined_or_uncertain: for ... in cases')
```

## tests/test_w3_spend_attribution.py

FAIL lines:
```
   FAIL test_binding_ceiling_and_vocabulary_are_in_the_governance_reading AssertionError()
   FAIL: 1 failing
```
First 40 lines of traceback/assertion output:
```
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/r2_autonomy_harness.py", line 34, in run_tests
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_w3_spend_attribution.py", line 95, in test_binding_ceiling_and_vocabulary_are_in_the_governance_reading
       assert len(binding["precedence"]) >= 5 and binding["unset"]["provider_ceilings"] is True
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   AssertionError
   FAIL test_binding_ceiling_and_vocabulary_are_in_the_governance_reading AssertionError()
   FAIL: 1 failing
```

## tests/test_w3_tmp_hygiene.py

FAIL lines:
```
   FAIL test_every_test_file_that_creates_temp_files_installs_the_sandbox_first AssertionError('these test files create temporary files without `import _tmp; _tmp.install()` at the top (tests/_tmp.py): _watchlist_sim.py:92, test_codex_a9_defer_state_pg.py:54')
```
First 40 lines of traceback/assertion output:
```
   FAIL test_every_test_file_that_creates_temp_files_installs_the_sandbox_first AssertionError('these test files create temporary files without `import _tmp; _tmp.install()` at the top (tests/_tmp.py): _watchlist_sim.py:92, test_codex_a9_defer_state_pg.py:54')
```

## tests/test_w4_close5_rows3.py

FAIL lines:
```
   FAIL test_f542_every_customer_affecting_etsy_mutation_is_followed_by_a_readback AssertionError("Etsy writes with no read-back after them in the same function: ['app/command_center/approvals.py::_standing_policy:941 activate']. Read the field back, or record why it cannot affect a customer in DRAFT_ONLY")
   FAIL: 1 failing of 3
```
First 40 lines of traceback/assertion output:
```
   Traceback (most recent call last):
     File "/home/user/Project-Money/brambleloop/tests/test_w4_close5_rows3.py", line 183, in <module>
       fn()
       ~~^^
     File "/home/user/Project-Money/brambleloop/tests/test_w4_close5_rows3.py", line 94, in test_f542_every_customer_affecting_etsy_mutation_is_followed_by_a_readback
       assert not unchecked, ("Etsy writes with no read-back after them in the same function: "
              ^^^^^^^^^^^^^
   AssertionError: Etsy writes with no read-back after them in the same function: ['app/command_center/approvals.py::_standing_policy:941 activate']. Read the field back, or record why it cannot affect a customer in DRAFT_ONLY
   FAIL test_f542_every_customer_affecting_etsy_mutation_is_followed_by_a_readback AssertionError("Etsy writes with no read-back after them in the same function: ['app/command_center/approvals.py::_standing_policy:941 activate']. Read the field back, or record why it cannot affect a customer in DRAFT_ONLY")
   FAIL: 1 failing of 3
```

## tests/test_w4_resume_runner.py

FAIL lines:
```
   FAIL test_f7_the_declared_final_segment_set_covers_every_matching_suite AssertionError("declare these in scripts/suite_final_segment.txt: ['tests/test_a4a_fix_floor_and_reopen.py', 'tests/test_a4a_low_fixes.py', 'tests/test_codex_a9_defer_state_pg.py', 'tests/test_opus2_a9_u6_import_path.py', 'tests/test_s2_fix_ledger.py', 'tests/test_s2_fix_routing.py', 'tests/test_s2_openai_provider.py']")
```
First 40 lines of traceback/assertion output:
```
   FAIL test_f7_the_declared_final_segment_set_covers_every_matching_suite AssertionError("declare these in scripts/suite_final_segment.txt: ['tests/test_a4a_fix_floor_and_reopen.py', 'tests/test_a4a_low_fixes.py', 'tests/test_codex_a9_defer_state_pg.py', 'tests/test_opus2_a9_u6_import_path.py', 'tests/test_s2_fix_ledger.py', 'tests/test_s2_fix_routing.py', 'tests/test_s2_openai_provider.py']")
```

