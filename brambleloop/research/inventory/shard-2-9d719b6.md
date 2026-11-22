# Test inventory — shard 2 of 4 (second run, at 9d719b6)

Run at the checked-out HEAD `9d719b6` (shard 1 ran at `74b749f`), so the two shards are not from the same commit. `shard-2.md` on this branch is the run at `74b749f`; this file is a second run at a later commit, kept alongside it. Difference: this run fails `test_eng_catalogue_perf.py` where that run failed `test_cert_wiring.py`; the other 10 failing suites match.

Inventory only. This is **not** a release record: it is a sharded checkpoint run, which the runner marks `release_eligible: false` (D-W4-OWNER-RESUME-POLICY). Nothing was fixed.

| Field | Value |
|---|---|
| Run ID | `20261122T114639Z-413` |
| Command | `CHECKPOINT=1 SHARD=2/4 JOBS=4 bash run_tests.sh` |
| Git SHA | `9d719b6c00567017b2128598e3fd9134c0f9e30a` (tree clean, unchanged at end) |
| Started / finished (UTC) | 2026-11-22T11:46:40Z / 2026-11-22T13:07:10Z (4831 s) |
| Interpreter | `.venv/bin/python` (Python 3.13, from `requirements.lock` + `requirements-test.lock`) |
| Suites in shard | 284 |
| **Passing suites** | **273** |
| **Failing suites** | **11** |
| Tests passing / failing (reported) | 3537 / 9 |
| Tests skipped (reported) | 2 |
| Runner exit code | 11 (= failing suites) |
| Environment failures | 0 of the failing suites (ENOSPC/permission/network/provider) |

## Failing suites

- `tests/test_eng_catalogue_perf.py` — exit 1
- `tests/test_etsy_publish_e2e.py` — exit 1
- `tests/test_final_closure_matrix.py` — exit 1
- `tests/test_release_versions.py` — exit 1
- `tests/test_v11_pwa_browser.py` — exit 1
- `tests/test_w4_autonomy_idle_departments.py` — exit 1
- `tests/test_w4_fmbatch1_licenses.py` — exit 1
- `tests/test_w4_fmbatch1_lifecycle.py` — exit 1
- `tests/test_w4_fmbatch1_provider_boundary.py` — exit 1
- `tests/test_w4_launchfix.py` — exit 1
- `tests/test_w4_relfix_release_log.py` — exit 1

### `tests/test_eng_catalogue_perf.py`

Exit code 1. Last 25 lines of output:

```
cold catalogue read: 1.14s (600 products, 70000 jobs, 150000 audits)
OK   test_cold_catalogue_read_at_production_scale_is_not_quadratic
500 concurrent cold readers: 2.96s, load_records x1
OK   test_500_concurrent_cold_readers_single_flight_one_load_no_errors
FAIL test_the_per_product_lookups_use_the_grouped_index_not_a_scan AssertionError()
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_eng_catalogue_perf.py", line 172, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_eng_catalogue_perf.py", line 164, in test_the_per_product_lookups_use_the_grouped_index_not_a_scan
    assert time.perf_counter() - t0 < 1.0
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
2 passed, 1 failed
```

### `tests/test_etsy_publish_e2e.py`

Exit code 1. Last 25 lines of output:

```
[               PASS] taxonomy[simulated]: {'refresh_job': {'id': 9, 'status': 'done', 'last_error': ''}, 'seo_job': {'id': 10, 'status': 'done', 'last_error': ''}, 'category': {'status': 'CHOSEN', 'taxo
[               PASS] owner_phase_transition: {'recorded': [{'to': 'staging', 'transition_id': 38, 'effective_now': 'staging'}, {'to': 'limited_production', 'transition_id': 39, 'effective_now': 'limited_pr
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_etsy_publish_e2e.py", line 426, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_etsy_publish_e2e.py", line 228, in test_package_to_draft_rollback_adoption_and_refusals
    first_id = str(job["outputs"]["etsy_listing_id"])
                   ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
KeyError: 'etsy_listing_id'
FAIL test_package_to_draft_rollback_adoption_and_refusals KeyError('etsy_listing_id')
OK   test_two_matching_drafts_or_a_live_one_escalate_and_nothing_is_created
OK   test_the_fee_budget_refuses_above_one_fee_per_listing_and_beyond_six_dollars
```

### `tests/test_final_closure_matrix.py`

Exit code 1. Last 25 lines of output:

```
OK   test_a_fact_only_tests_write_cannot_hold_integrated
OK   test_a_worker_claim_above_its_evidence_is_lowered_with_a_reason
OK   test_all_proxy_evidence_refuses_integrated_but_one_direct_item_does_not
FAIL test_basis_names_the_actual_mapping_commits AssertionError('1b21e81c6d1b228a93f72be44cfdf8193740b61b')
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

Exit code 1. Last 25 lines of output:

```
FAIL test_no_content_change_keeps_a_released_version AssertionError('harbour-drop-shoulder-pullover-2x@1.3.0: content changed (83cc0b73c2f4 -> 2023cd2a5fed) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-3x@1.3.0: content changed (e30eed41d47f -> 31ea804cd6e0) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-4x@1.3.0: content changed (364d0ca51b18 -> 7f7c5bf4a844) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-5x@1.3.0: content changed (7a15e6379539 -> d262fa67b707) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-l@1.3.0: content changed (a852216400d6 -> 71ddc74bb135) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-m@1.3.0: content changed (5bf0678b9d1a -> 6aeb40326d76) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-s@1.3.0: content changed (55527d3be3bb -> 2fb9a42e85bf) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-xl@1.3.0: content changed (baab131a56d9 -> 949d4fe7e77a) but the version did not -- a released version cannot change content; bump it\nharbour-drop-shoulder-pullover-xs@1.3.0: content changed (bd3c15d8616c -> 33cf9a3309d3) but the version did not -- a released version cannot change content; bump it')
OK   test_the_check_catches_a_claims_change_under_the_same_version
FAIL test_the_check_catches_a_content_change_under_the_same_version AssertionError(['chunky-ribbed-scarf: version 1.0.0 -> 1.1.0 but the pinned row was not updated; update version and fingerprint together', 'harbour-drop-shoulder-pullover-2x@1.3.0: content changed (83cc0b73c2f4 -> 2023cd2a5fed) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-3x@1.3.0: content changed (e30eed41d47f -> 31ea804cd6e0) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-4x@1.3.0: content changed (364d0ca51b18 -> 7f7c5bf4a844) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-5x@1.3.0: content changed (7a15e6379539 -> d262fa67b707) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-l@1.3.0: content changed (a852216400d6 -> 71ddc74bb135) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-m@1.3.0: content changed (5bf0678b9d1a -> 6aeb40326d76) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-s@1.3.0: content changed (55527d3be3bb -> 2fb9a42e85bf) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-xl@1.3.0: content changed (baab131a56d9 -> 949d4fe7e77a) but the version did not -- a released version cannot change content; bump it', 'harbour-drop-shoulder-pullover-xs@1.3.0: content changed (bd3c15d8616c -> 33cf9a3309d3) but the version did not -- a released version cannot change content; bump it'])
OK   test_the_pt_redesigns_carry_a_new_version
```

### `tests/test_v11_pwa_browser.py`

Exit code 1. Last 25 lines of output:

```
OK login: labelled passphrase field
OK login: wrong passphrase refused with message
FAIL check aborted: page.waitForSelector: Timeout 30000ms exceeded. Call log: [2m  - waiting for locator('.hero') to be visible[22m
SUMMARY passes=2 failures=1 screenshots=0
```

### `tests/test_w4_autonomy_idle_departments.py`

Exit code 1. Last 25 lines of output:

```
OK   test_a_department_with_due_work_is_still_busy
OK   test_a_long_idempotency_key_is_fitted_deterministically
OK   test_a_waiting_handoff_consumer_is_not_duplicated
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_autonomy_idle_departments.py", line 312, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_autonomy_idle_departments.py", line 221, in test_a_wide_rebuild_fits_the_varchar_200_key_column
    assert len(first["enqueued"]) == len(slugs), first["enqueued"]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ['pdf:autumn-oak-mosaic-throw.pdf', 'pdf:cloudline-baby-blanket.pdf', 'pdf:harvest-table-runner.pdf', 'pdf:mosaic-placemat-pair.pdf', 'pdf:nordic-forest-mosaic-throw.pdf', 'pdf:nordic-star-ornaments.pdf', 'pdf:pet-snuggle-mat.pdf', 'pdf:pressed-flower-motifs.pdf', 'pdf:pumpkin-cluster-set.pdf', 'pdf:spooky-garland.pdf', 'pdf:valentine-heart-garland.pdf', 'pdf:winter-village-graphghan.pdf']
```

### `tests/test_w4_fmbatch1_licenses.py`

Exit code 1. Last 25 lines of output:

```
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_licenses.py", line 58, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_licenses.py", line 15, in test_register_is_complete
    assert L.check() == [], L.check()
           ^^^^^^^^^^^^^^^
AssertionError: ['font Lato is bundled with no licence row', 'font NotoSerifDisplay is bundled with no licence row']
```

### `tests/test_w4_fmbatch1_lifecycle.py`

Exit code 1. Last 25 lines of output:

```
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_lifecycle.py", line 99, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_lifecycle.py", line 58, in test_stages_follow_the_rows
    assert L.derive(db, "x")["stage"] == "LISTING_READY"
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

### `tests/test_w4_fmbatch1_provider_boundary.py`

Exit code 1. Last 25 lines of output:

```
Traceback (most recent call last):
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_provider_boundary.py", line 162, in <module>
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_fmbatch1_provider_boundary.py", line 57, in test_no_new_direct_vendor_importer_and_pending_only_shrinks
    assert not new, f"business modules importing a vendor module directly: {new}"
           ^^^^^^^
AssertionError: business modules importing a vendor module directly: ['creative/toy_board.py', 'improve/autocoder.py', 'ops/owner_directives.py']
```

### `tests/test_w4_launchfix.py`

Exit code 1. Last 25 lines of output:

```
    fn()
    ~~^^
  File "/home/user/project-money/brambleloop/tests/test_w4_launchfix.py", line 803, in test_img_stage_only_activation_asks_for_the_activation_stage_and_nothing_internal_does
    assert users == ["brambleloop/gates/platform_policy.py",
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
                     "brambleloop/runtime/release.py"], users
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
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

Exit code 1. Last 25 lines of output:

```
FAIL test_a_tampered_or_missing_full_log_refuses_the_release AssertionError({'ok': False, 'reasons': ['no release-eligible local suite run record for a630eb9cdf9c']})
FAIL test_record_writes_a_summary_into_release_and_the_full_log_outside_it AssertionError({'ok': False, 'reasons': ['no release-eligible local suite run record for a630eb9cdf9c']})
OK   test_the_shipped_release_directory_holds_only_summaries_with_pinned_full_logs
OK   test_the_summary_carries_no_session_marker_and_paths_become_repo_relative
```
