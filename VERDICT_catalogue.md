VERDICT: DO NOT SHIP cafd6917fd2f76a15913a3a6ab9c8bc13d49482f

Delta review of origin/eng/catalogue @ cafd6917 over 5f90f2f9. Base origin/claude/w6-INTEG2 @ cde89a4b. Merged tree built (conflicts only in sw.js, scripts/suite_final_segment.txt; resolved mechanically: both suite lists kept, sw.js taken from the unit).

## Findings

### HIGH
- **H1 `brambleloop/src/brambleloop/app/command_center/catalogue.py:174`**: the new line `if item.get("state") == "published":` (added in `next_action` by the M2 fix) is flagged by the static guard `test_w4_adopt_manual_listing.test_no_code_compares_or_lists_the_published_literal_outside_the_helper`. On the merged tree that suite FAILS: `AssertionError: ['app/command_center/catalogue.py:174: if item.get("state") == "published":']`. The literal is the inventory stage name, not a listing state, so the behaviour is right, but the guard that gates the merge is red. Fix is one line: either compare through a named constant that does not match the guard, or add an allow-list entry beside the existing `reach("published", listing_id=` one with the reason "inventory stage name". The author's own run did not include this suite.

### MEDIUM
- **M1 cold-read target not met**: the stated criterion is "under 1 s uncached" on 600 products / 70k jobs / 150k audits. Measured on the merged tree: cold `catalogue.view` 2.92 s (the test prints it), and the inventory snapshot alone (`production_inventory.snapshot` at products/production_inventory.py:340, load_records + derive) is 3.04 s; `build_index` is 0.02 s. The fix is a real improvement (pre-fix 7.7 s per the test comment) and the quadratic scan is gone, but the test bound was set to 5 s (`tests/test_eng_catalogue_perf.py:58`), so the suite cannot detect a regression to ~4.9 s and the <1 s claim is untested. Either meet 1 s (load_records dominates) or restate the criterion honestly.
- **M2 concurrency 500 is not tested**: `test_eng_catalogue_fix1.py` exercises 4-8 threads. I ran 500 concurrent cold readers on the 600/70k/150k fixture myself: 500/500 status OK, 0 errors, `load_records` called exactly once, 3.86 s wall. So the behaviour is correct, but a 500-way test is not in the suite.

### LOW
- sw.js comment in the unit still says "v33 (above INTEG2's v32)" (stale; the value is v34). See VERSION note.

## Previous findings: truly fixed? (each mutated, each killed)
- M1 distinct product counts / versions / concepts apart / crosscheck equality: FIXED. Mutations `"products": rows_total` -> 2 tests fail; crosscheck `idx_products == distinct_products == products` -> `True` -> `test_the_crosscheck_compares_counts_to_sql_not_just_presence` fails.
- M2 verified draft -> owner activation: FIXED. Mutating the `ACTIVATE_ACTION` return -> `test_a_verified_draft_goes_to_owner_activation_only_a_live_row_to_sales_monitoring` fails. Draft without an etsy_listing_id, or a non-live non-published state, reads UNKNOWN, never monitoring.
- LOW LIKE escaping of `%` and `_`: FIXED. `_like_escape` -> identity -> `test_held_filter_escapes_like_wildcards` and `test_search_and_filters` fail.
- LOW dead-letter resolved by the same job: FIXED. `_same_job` removed from the `later` filter -> `test_a_dead_letter_is_resolved_only_by_a_later_success_of_the_same_job` fails.
- LOW perf: partly fixed (see M1). LOW concurrency 500: behaviour verified (see M2).

## Suites (merged tree, `PY=venv python`, JOBS=2)
`TOTAL PASSING: 481 ; suites failing: 1` (0 environment failures)
- test_eng_catalogue 13/0, test_eng_catalogue_agents 10/0, test_eng_catalogue_fix1 9/0, test_eng_catalogue_perf 2/0, test_v11_pwa_static 85/0, test_s4_p0_board, test_v11_pwa_browser, test_w5_inventory, test_vacuity, test_w3_tmp_hygiene, test_w4_resume_runner, test_w4_c12_wiring, test_v11_autonomy_timeline: pass.
- **test_w4_adopt_manual_listing: FAIL (H1)**.
- autonomy_map.json: no regeneration needed (test_v11_autonomy_timeline passes).

## sw.js VERSION
Unit sets `cc-shell-v34` (base is v33). No collision with the other two units on this base (research-flow v35, families unchanged at v33), but the base's v33 line conflicts textually and both catalogue and research-flow edit it: whichever of the two merges second must be rebumped (v36+ if v34/v35 are both used).
