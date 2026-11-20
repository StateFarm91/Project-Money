# Handoff: wave-4 lane SPENDA (Final Master cluster K5a: spend attribution & finance reporting)

Branch `claude/w4-SPENDA` (from `claude/visual-investigation` 0d21dbe; merged `claude/w4-SPEND`).
Latest pushed SHA: see `git log origin/claude/w4-SPENDA -1`.
No paid call, no network call, no deploy: provider billing is exercised through an injected
transport; every test writes ledger rows directly or through `spend_report.record`.

## Rows (K5a: F-070, F-103, F-106, F-304, F-319, F-322, F-325, F-629)

| Row | Status | Evidence |
|---|---|---|
| F-304 Per-Operation Cost Attribution | PROVEN | Integrator-authorised additive nullable columns on `CostEntry` (`listing_id`, `image_count`, `observed_cad`, `evidence_ref`; `core.migrate` adds them to an old DB -- `::test_a_database_made_before_the_columns_upgrades_additively`, `::test_the_f304_dimensions_are_columns_on_the_ledger_row_too`), mirrored from `finance/cost_attribution.py` (sidecar `cost_attributions`: listing id + Etsy id + basis, image count + basis, units, observed_cad + basis, evidence_ref), written by the single ledger writer `spend_report.record` in the same transaction. UNKNOWN is NULL, never 0; `observed_cad` refused without a named source. Consumers: `spend_report.governance()["per_operation"]` (/api/spend-governance) and `governor.report()["per_operation"]` (/api/governor). Tests: `test_w4_spenda_k5a::test_every_billed_row_carries_listing_images_observed_and_evidence_beside_it`, `::test_an_observed_cost_must_name_its_source_and_the_governor_reads_the_sidecar`. |
| F-106 Provider Billing Reconciliation | OWNER-GATED (code complete) | `ops/provider_accounts.py`: `fetch_provider_costs` (read-only GET: Anthropic Admin `cost_report`, cents; OpenAI `organization/costs`), `settle` (day x model vs ledger; material gap -> P2 incident `provider-billing-settlement-gap`), `settle_all` run by `governor.enforce` (OWNER_GATED, no network, without an admin key), `reconcile()` now carries `provider_billing` + `reported_vs_ledger` (/api/funding). The owner-reported gap incident already existed (`spend_hygiene.provider_discrepancy`). Gate: OWNER ACTION -- set `ANTHROPIC_ADMIN_KEY` / `OPENAI_ADMIN_KEY` (read-only usage/cost admin keys) in Railway. Tests: `::test_provider_cost_reports_parse_in_cents_and_per_day`, `::test_without_an_admin_key_billing_is_owner_gated_and_nothing_is_fetched`, `::test_settlement_against_the_provider_bill_writes_observed_and_opens_an_incident`, `::test_the_governor_pass_records_the_settlement_state`. |
| F-103 Post-Call Reconciliation | OWNER-GATED (on F-106 key) | Settlement against provider billing implemented (`settle`): a single-call (day, model) bucket gets a provider-observed `observed_cad`; multi-call buckets are settled at bucket level and rows stay unobserved (never apportioned). Drift stays in `spend_report.governance()["drift"]`. WIRING (CC, sent by SPEND): add `estimate_drift` to /api/verify. Test: `::test_a_bucket_of_several_calls_is_settled_without_inventing_per_call_actuals`. |
| F-070 Benchmark Spend Governance | PROVEN | `intel/purchase_selection.information_value` (per purchased benchmark: paid or UNKNOWN, findings, promoted findings, improvements created/promoted/reverted, floors adopted, CA$ per finding/improvement only where price known); carried in `select()` -> /api/benchmark-selection as `post_purchase_information_value`. Tests: `::test_each_purchased_benchmark_reports_what_it_taught_and_unknown_price_is_not_zero`, `::test_the_selection_the_owner_reads_carries_the_post_purchase_value`. |
| F-319 Spend-to-Progress Ratio | PROVEN | SPEND's `governor.spend_to_progress` (in `governor.report`). Test: `::test_spend_to_progress_names_cost_per_milestone_and_spend_that_advanced_nothing` (+ SPEND's `test_w4_spend_attribution`). |
| F-322 Cost Per Usable Asset | PROVEN | SPEND's `reliability.assess` judging_cad / `_judging_cad`. Tests: `::test_cost_per_usable_gallery_includes_judging_and_unknown_judging_is_a_floor`, `::test_judging_cost_is_read_from_the_ledger_and_unknown_without_a_sequence`. |
| F-325 Steady-State Sustainability Forecast | PROVEN (forecast leaves INSUFFICIENT_DATA only on live data: DATA-GATED F-321 live_listings) | SPEND's observation term. Test: `::test_observation_cadence_is_its_own_forecast_term_and_not_counted_twice`. |
| F-629 Department Spend Governance | PROVEN (credits); department shares = owner decision, empty means no cap | `finance/credits.py` (`provider_credits` table, `grant` refuses unknown kind/source, non-positive, no evidence; `wallet` estimates credit absorption, names cash exposure, never changes a ceiling). Consumer: `spend_report.governance()["credits"]`. Test: `::test_credits_are_kept_apart_from_cash_and_never_raise_a_ceiling`. |

| F-311 Cache Certified Evidence (K5b leftover, integrator-assigned) | PROVEN | `gateway/evidence_key.py` (`content` / `material` / `file_bytes`, `REUSE_PATHS` registry). Routing analysis cache, paid-call intent, image-bench rubric + trial, carried-portrait verdict and benchmark observation change detection all key through it with byte-identical outputs (no evidence on file stops matching). `cached_analysis` runtime caller via `failover.decide` (SPEND). Test: `::test_every_evidence_reuse_path_keys_through_one_helper_with_unchanged_keys`. |

## Tests run (all PASS)
`test_w4_spenda_k5a` 14; test_governor 16, test_provider_accounts 7, test_purchase_selection 25,
test_reliability 17, test_money_truth 18, test_cert_cost 19, test_cost_governance_wave2 39,
test_spend_governance 36, test_spend_policy 24, test_w3_spend_attribution 4, test_w3_spend_hygiene 6,
test_w3_spend_paid_calls 8, test_model_spend_paths 12, test_rc1_spend 20, test_dashboard_spend 7,
test_cert_thrash 4, test_intake 20, test_w4_spend_paid_discipline 13, test_image_bench 59,
test_photoreal_calibration 19, test_pods_routing 32, test_gateway 30, test_model_access 13,
test_provenance_backfill 12, test_w3_spend_paid_calls 8, test_w3_spend_gateway_w8 5,
test_w4_spend_attribution, test_platform 22 (the cadence-smoke test takes ~830 s under the
shared-container load, all of it PDF rendering in launch readiness; run per-test), test_vacuity 7,
test_secret_scan 7, test_reachability 11, test_w3_tmp_hygiene 16. Lane file now 17 tests.

## Wiring requests
- integrator: import `brambleloop.finance.cost_attribution` and `brambleloop.finance.credits` in
  `core/db.create_all` (both self-create via `ensure_table`, so this is belt-and-braces).
- CC: /api/verify readback of `spend_report.estimate_drift` (F-103), as SPEND requested.

## In progress / next
- Done: F-304 CostEntry columns; F-311 helper. Remaining: only the external gates above
  (owner admin usage keys for F-106/F-103; live listings for F-325's real-data forecast).
