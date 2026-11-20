# ENG-VIS-FLUX: review request, slice 1

- **Branch:** `eng/vis-flux`.
- **Base:** `origin/claude/w6-INTEG3` @ `39b92619`, with `origin/eng/visual-factory` @ `c774d740` merged (merge commit `439d17e5`).
- **Final SHA:** the commit that adds this file (see the #28 comment).
- **Spend:** no BFL request was made. There is no key in this build, and none was needed.

## Scope (file ownership)

| Owned and changed | Not touched |
|---|---|
| `gateway/flux_contract.py` (new) | `visual/identity_gate.py` (ENG-VIS-IDENTITY) |
| `gateway/flux_qc.py` (new) | `visual/vision_judges.py` (ENG-VIS-IDENTITY) |
| `gateway/flux_provenance.py` (new) | the gallery certificate route (ENG-VIS-GALLERY) |
| `gateway/flux_provider.py` (new) | `publish/motif_backlog.py` (eng/motif-backlog: read, not duplicated) |
| `gateway/images.py` | |
| `gateway/paid_provider_gate.py` (image caps) | |
| `creative/image_stages.py` (renderer context, receipt fields) | |
| `creative/flux3_generator.py` (preflight) | |

The only other change is one retention entry in `ops/retention.py`.

## What changed, and why

1. **The contract was verified and is held as data** (`flux_contract`, audit in `w6/flux_integration_audit.md`).
   - Every fact cites its URL and the access date 2026-11-20.
   - Findings:
     - `BFL3_FIELDS` was stale. It lacked `user`, `width` and `height`, and is now read from the contract.
     - Nothing range-checked the body. `safety_tolerance` 5–7 and exact sizes over 4 MP with references would have been sent and returned 422. `validate_request` now runs on the built body before any reservation.
     - FLUX 3 Image takes **no seed**. The seed is recorded from the result when one is present, and `seed_supported: false` is recorded.
2. **Generation-time check** (`flux_qc`, hooked in `images._finish_render` when `frame_role` is given).
   - The check fires after the ledger row is written. The render therefore stays billed, the reservation is released at its price, the bytes stay on disk, an `image.generation_rejected` audit row is written, and `ImagesRejectedAtGeneration` is raised with `.reasons`.
   - A corrupt download is re-fetched for free, at most `CORRUPT_REFETCHES = 2` times.
   - The deferred path (`poll_render`) now marks a billed failure FAILED_BILLED. A later poll can therefore never bill the same render a second time.
3. **Provenance** (`flux_provenance`). One record per FLUX render, built from measured data:
   - the reference SHAs found in the sent body, in order, with Laura's canonical three marked by fingerprint;
   - the task id;
   - the reserved cost and the ledger row;
   - the output SHA, size and format;
   - the gallery and the disclosure.

   `missing()` makes incompleteness explicit. The stage receipt carries `provenance`, `provenance_missing` and `generation_check`.
4. **Caps** (`paid_provider_gate._image_cap_refusal`). These run inside the budget lock, after every existing check, for the image family only:
   - 60 images per UTC day;
   - 16 images per gallery;
   - CA$2.50 per gallery.

   The per-gallery caps apply only to real gallery keys, not to `shared`, `job:` or `product:` keys. The environment can lower a cap and never raise it. `gallery_spend()` reports cost per gallery.
5. **Readiness and replacement** (`flux_provider`). `Flux3Generator._preflight` runs before reserving and refuses in these cases:
   - with `UNKNOWN [no_bfl_credential]` when `BRAMBLELOOP_IMAGE_KEY_BFL` is not present;
   - with `UNKNOWN [not_activated_by_owner]` (or expired/revoked) when there is no activation;
   - while a rejected render of this gallery re-checks as RECOVERED, or an open `motif_recovery` row exists for the product.

   The preflight is keyed on the transport. It applies to the real BFL renderer, not to stand-ins flagged `paid` to exercise caps.

## Suites

The table lists suites run on this tree. Every suite matching flux, image_generation, model_photography, provider or gateway was run, plus the named ones.

| Suite | Result |
|---|---|
| test_cc_provider_facade.py | PASS: 5 passed, 0 failed |
| test_cert_intel_wave2.py | PASS: 15 passing, 0 failing |
| test_cert_parity_copy.py | FAIL: PRE-EXISTING: same 1 failure on unmodified base 439d17e5 (SEO tag count; unrelated) |
| test_cert_spend_hosts.py | PASS: PASS: 0 failing |
| test_certification.py | PASS: OK   test_the_whole_release_chain_runs_rather_than_being_named |
| test_codex_v1_flux_concurrency.py | PASS: 11 passed, 0 failed |
| test_codex_v1_spend_guard.py | PASS: 62 passed, 0 failed |
| test_compiler.py | PASS: OK   test_unknown_colour_is_rejected |
| test_cost_governance_wave2.py | PASS: 0 FAIL lines after the retention entry (rerun) |
| test_eng_recovery.py | PASS: 0 failed (rerun after FREE_REQUEST_MODULES entry) |
| test_eng_vis_flux.py | PASS: 23/23 passing |
| test_executor.py | PASS: OK   test_the_scheduler_condition_counts_cadences_rather_than_any_audit_row |
| test_final_visual_authority.py | PASS: 10/10 passing |
| test_gallery_escalation.py | PASS: OK   test_without_a_deterministic_render_the_ladder_ends_in_holding_the_listing |
| test_gateway.py | PASS: OK   test_with_no_provider_the_gateway_says_so_instead_of_pretending |
| test_model_identity.py | PASS: OK   test_the_two_floors_are_independent_and_neither_averages_into_the_other |
| test_model_photography.py | PASS: OK   test_without_a_body_reference_the_morphology_floor_is_unverifiable_not_pass |
| test_model_provider.py | PASS: OK   test_the_provider_records_what_it_was_told_rather_than_a_paraphrase |
| test_model_spend_paths.py | PASS: OK   test_the_scan_sees_a_guard_in_a_nested_function |
| test_motif_reservation.py | PASS: 17 passing, 0 failing |
| test_owned_photography.py | PASS: OK   test_the_version_bump_targets_the_check_that_actually_failed |
| test_portrait_repair.py | PASS: OK   test_the_spend_ceiling_stops_it_before_the_attempt_bound_does |
| test_provider_accounts.py | PASS: OK   test_the_three_columns_are_reported_separately |
| test_provider_trial.py | PASS: OK   test_tiling_on_the_challenger_too_is_a_finding_about_crochet_not_about_a_pr |
| test_reliability.py | PASS: OK   test_the_happy_path_reports_a_rate_and_names_the_standard_it_was_judged_aga |
| test_reverse.py | PASS: OK   test_written_output_is_human_readable |
| test_s2_openai_provider.py | PASS: PASS: 0 failing |
| test_seasonal_cycle.py | PASS: OK   test_with_no_generator_the_cycle_stops_and_says_which_capability |
| test_serp.py | PASS: OK   test_top_thumbnails_are_judged_one_per_call_and_stored_as_composition |
| test_twin.py | PASS: OK   test_twin_reports_colours_actually_present |
| test_v11_autonomy_timeline.py | PASS: PASS: 0 failing |
| test_v11_reliability_gateway.py | PASS: OK   test_status_is_unknown_without_attempts |
| test_v2_capability_redrive.py | PASS: 0 failed |
| test_v6_gallery_e2e.py | PASS: 10 passed, 0 failed |
| test_visual_pipeline_evidence.py | PASS: OK   test_the_section_is_served_on_the_evidence_body |
| test_w3_k12_model_photography.py | PASS: 10/10 passing |
| test_w3_laura_cc_providers.py | PASS: 7/7 passed in 3s |
| test_w3_spend_gateway_w8.py | PASS: PASS: 0 failing |
| test_w3_tmp_hygiene.py | PASS: OK   test_tmp_leak_strict_makes_a_passing_but_leaking_suite_fail |
| test_w3_visual_rnd_guard.py | PASS: 6/6 passing |
| test_w4_c07_f441_handlers.py | PASS: OK   test_f464_the_render_handlers_cannot_wait_on_a_provider |
| test_w4_c07_f464.py | PASS: passing (rerun after fixes) |
| test_w4_c2_visual.py | PASS: 0 failed |
| test_w4_close5_rows.py | PASS: PASS: 0 failing of 8 |
| test_w4_controlled_experiments.py | PASS: 10 passed, 0 failed |
| test_w4_departments.py | PASS: 0 failed |
| test_w4_firstsale_retention.py | PASS: 6/6 passed |
| test_w4_flux3generator.py | PASS: 9/9 passing |
| test_w4_fluxapi.py | PASS: 13/13 passing |
| test_w4_fluxstages.py | PASS: 16/16 passing |
| test_w4_fluxtexture.py | PASS: 9/9 passing |
| test_w4_fm_provider_table.py | PASS: OK   test_modules_behind_the_table_are_reached |
| test_w4_fmbatch1_provider_boundary.py | PASS: OK   test_the_dependency_register_no_longer_claims_a_caller_free_swap |
| test_w4_fmbatch1_provider_health.py | PASS: OK   test_review_n6_verify_status_is_ok_only_when_the_smoke_matrix_passes |
| test_w4_fmbatch1_providers.py | PASS: 7 passed, 0 failed |
| test_w4_fmbatch1_retention_guard.py | PASS: OK   test_a_protected_prefix_survives_the_horizon |
| test_w4_fml_checkpoint_adoption.py | PASS: 3/3 passed |
| test_w4_gatesi.py | PASS:   34 passing, 0 failing |
| test_w4_ownerimg.py | PASS: 35 passed, 0 failed |
| test_w4_resume_runner.py | PASS: OK   test_without_the_flags_nothing_changes (0.2s) |
| test_w4_retfix_retention_keys.py | PASS: OK   test_the_scan_catches_a_duplicate |
| test_w4_spend_attribution.py | PASS: PASS: 0 failing |
| test_w4_spenda_k5a.py | PASS: PASS: 0 failing |
| test_w4_visnext2.py | PASS: 12 passed, 0 failed |
| test_w4_wraptest.py | PASS: OK test_w4_wraptest (0 failed) |
| test_w5_v0_paid_provider_gate.py | PASS: 52/52 passed |

## Things to look at hard

- **QC placement.** QC runs only when `frame_role` is given. Unframed renders (benchmarks, probes) are deliberately not checked. Is `image_stages._run` the right and only place that marks listing and intermediate frames? Only the real `flux3_renderer` declares `accepts_generation_context`.
- **A RECOVERED re-check blocks replacement for its gallery indefinitely.** This is the owner's rule taken literally. The gallery orchestrator still needs to pick those bytes up; that is ENG-VIS-GALLERY's to wire.
- **Gallery-cap scope.** `is_gallery_key` excludes `product:` buckets. A product's renders outside an image-production run are bounded by the day cap only.
