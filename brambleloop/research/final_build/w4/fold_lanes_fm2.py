"""Lane claims merged into claude/visual-investigation, folded by W4-FM2 (integrator directive
2026-10-07): SPEND (K5b), SPENDA (K5a), K9, F-416 (Dockerfile pin). F-914 (CC money period) is a v1.1 row: folded in v11_map.py.

Each entry: the lane's handoff claim re-read against this head (the producer function named
exists and is called from the host module named; the cited tests exist), the corrected mapping
fields, and the tests. `close_fm2.py` imports LANE_ROWS and adjudicates them exactly like its
own rows (aggregate.cap/completion; every cited test file green in this lane's sequential run).
Producers that live in a new module not yet in module_reachability.json are named by the
reached host module that calls them (e.g. gates/certificate.py::certify -> cir/topology).
"""
S = "src/brambleloop/"
PD = "tests/test_w4_spend_paid_discipline.py::"
KA = "tests/test_w4_spenda_k5a.py::"
SA = "tests/test_w4_spend_attribution.py::"
PC = "tests/test_w3_spend_paid_calls.py::"
K9G = "tests/test_k9_graded_truth.py::"
K9R = "tests/test_k9_rows.py::"
NONE = {"kind": "none", "key": "none", "detail": "no external/owner/data gate on the remaining step"}
BILLING = {"kind": "owner", "key": "provider_usage_api",
           "detail": "read-only provider usage/cost admin keys (ANTHROPIC_ADMIN_KEY / "
                     "OPENAI_ADMIN_KEY) in Railway; without them settlement is OWNER_GATED and "
                     "nothing is fetched"}


def _done(lane, producer, consumer, tests, checked, **extra):
    s = dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
             producer=producer, consumer=consumer, gate=dict(NONE), next_action="none")
    s.update(extra)
    return dict(checked=f"{lane}: {checked}", set=s, tests=tests)


def _gated(lane, producer, consumer, tests, checked, gate, missing, nxt):
    return dict(checked=f"{lane}: {checked}",
                set=dict(coverage="PARTIAL", defect=None, maturity="INTEGRATED",
                         producer=producer, consumer=consumer, gate=gate,
                         missing_part=missing, next_action=nxt),
                tests=tests)


LANE_ROWS = {
    # ---- SPEND (K5b) ------------------------------------------------------------------
    "F-312": _done("SPEND", S + "gateway/model_gateway.py::ModelGateway (deterministic-question "
                   "registry)", S + "visual/parity.py::assess; every paid call site",
                   [PD + "test_every_deterministic_question_names_code_that_exists_and_never_reaches_a_provider"],
                   "every deterministic question names the code that answers it and never reaches a provider"),
    "F-313": _done("SPEND", S + "gateway/routing.py::effective_route", S + "gateway/failover.py::decide "
                   "(ModelGateway routing)",
                   [PD + "test_a_cheaper_route_needs_recorded_equivalence_and_a_regression_reverses_it"],
                   "a cheaper route needs recorded quality equivalence; a regression reverses it"),
    "F-314": _done("SPEND", S + "gateway/routing.py::escalation_tier", S + "gateway/model_gateway.py::ModelGateway",
                   [PD + "test_an_unsure_cheap_answer_is_asked_once_more_one_tier_up_and_a_sure_one_is_not",
                    PD + "test_an_escalation_the_ceiling_refuses_returns_the_answer_marked_unsure"],
                   "an unsure cheap answer escalates once, one tier up, under the ceiling"),
    "F-316": _done("SPEND", S + "gateway/routing.py (closed schemas + sized output budgets)",
                   S + "gateway/model_gateway.py::ModelGateway",
                   [PD + "test_every_prompt_and_task_has_a_closed_schema_and_a_sized_output_budget",
                    PD + "test_truncated_output_is_rejected_and_billed_not_passed_on"],
                   "closed schemas and output budgets; truncated output rejected and billed"),
    "F-317": _done("SPEND", S + "gateway/model_gateway.py::ModelGateway (batch isolation)",
                   S + "gateway/model_gateway.py callers",
                   [PD + "test_a_batch_isolates_each_item_and_stops_whole_at_the_ceiling"],
                   "batches isolate items and stop whole at the ceiling"),
    "F-472": _done("SPEND", S + "gateway/model_gateway.py::ModelGateway._durably_down",
                   S + "gateway/failover.py::health (shared across workers)",
                   [PD + "test_a_second_worker_does_not_pay_to_rediscover_an_outage_the_first_recorded"],
                   "a recorded outage is read by every worker before paying"),
    "F-328": _done("SPEND", S + "gateway/anthropic.py::check_budget_cad (question required)",
                   "every production reserving call site",
                   [PD + "test_a_paid_call_naming_no_question_is_refused_and_recorded",
                    PD + "test_every_production_reserving_call_site_names_its_question"],
                   "a paid call naming no question is refused and recorded"),
    "F-309": _done("SPEND", S + "gateway/anthropic.py::check_budget_cad (finance/systematic breaker)",
                   "every paid path through check_budget_cad",
                   [PD + "test_a_floor_that_never_passes_stops_every_paid_call_for_that_method_until_it_changes",
                    PD + "test_gallery_vision_feeds_the_breaker_and_reports_pending_before"],
                   "the systematic-failure breaker is shared by every paid path"),
    "F-318": _done("SPEND", S + "finance/spend_hygiene.py::flat_backlogs", S + "finance/spend_hygiene.py "
                   "sweep (P1 incident)",
                   [PD + "test_a_paid_backlog_that_does_not_fall_is_a_financial_integrity_incident"],
                   "a paid backlog that does not fall opens a P1 incident"),
    # ---- SPENDA (K5a) -----------------------------------------------------------------
    "F-070": _done("SPENDA", S + "intel/purchase_selection.py::information_value",
                   S + "intel/purchase_selection.py::select -> /api/benchmark-selection",
                   [KA + "test_each_purchased_benchmark_reports_what_it_taught_and_unknown_price_is_not_zero",
                    KA + "test_the_selection_the_owner_reads_carries_the_post_purchase_value"],
                   "post-purchase information value per benchmark, unknown price never 0"),
    "F-304": _done("SPENDA", S + "finance/spend_report.py::record (CostEntry columns + cost_attribution sidecar)",
                   S + "finance/spend_report.py::governance; finance/governor.py::report",
                   [KA + "test_every_billed_row_carries_listing_images_observed_and_evidence_beside_it",
                    KA + "test_an_observed_cost_must_name_its_source_and_the_governor_reads_the_sidecar",
                    KA + "test_the_f304_dimensions_are_columns_on_the_ledger_row_too",
                    KA + "test_a_database_made_before_the_columns_upgrades_additively"],
                   "listing id, image count, observed cost and evidence ref on every billed row; UNKNOWN is NULL"),
    "F-319": _done("SPEND/SPENDA", S + "finance/governor.py::spend_to_progress",
                   S + "finance/governor.py::report (/api/governor)",
                   [SA + "test_spend_to_progress_divides_product_spend_by_new_milestones_and_names_waste",
                    SA + "test_no_progress_is_no_ratio_rather_than_zero",
                    KA + "test_spend_to_progress_names_cost_per_milestone_and_spend_that_advanced_nothing"],
                   "cost per milestone advanced; no progress is no ratio"),
    "F-322": _done("SPEND/SPENDA", S + "visual/reliability.py::assess (render + judging)",
                   S + "publish/model_photography.py::what_to_do_next",
                   [SA + "test_cost_per_usable_gallery_includes_judging_and_unknown_judging_is_a_floor",
                    SA + "test_judging_cost_is_read_from_the_ledger_and_unknown_without_a_sequence"],
                   "cost per usable gallery includes judging; unknown judging is a floor"),
    "F-629": _done("SPENDA", S + "finance/spend_report.py::governance (credits wallet, finance/credits)",
                   S + "finance/spend_report.py::governance -> /api/spend-governance",
                   [KA + "test_credits_are_kept_apart_from_cash_and_never_raise_a_ceiling"],
                   "credits kept apart from cash and never raise a ceiling; department shares are an "
                   "owner decision (empty = no cap)"),
    "F-311": _done("SPENDA", S + "gateway/routing.py::cached_analysis (gateway/evidence_key helper)",
                   S + "gateway/failover.py::decide",
                   [KA + "test_every_evidence_reuse_path_keys_through_one_helper_with_unchanged_keys",
                    "tests/test_model_access.py::test_unchanged_evidence_is_never_paid_for_twice"],
                   "every evidence-reuse path keys through one helper; the routing cache has a runtime caller"),
    "F-325": _gated("SPEND/SPENDA", S + "finance/sustainability.py::forecast",
                    "finance/sustainability.py::verdict -> launch/readiness.py::assess",
                    [SA + "test_observation_cadence_is_its_own_forecast_term_and_not_counted_twice"],
                    "observation cadence is its own forecast term; the forecast computes from "
                    "product-tagged spend (F-304)",
                    {"kind": "data", "key": "live_listings",
                     "detail": "the steady-state forecast leaves INSUFFICIENT_DATA only on real "
                               "listing history"},
                    "the forecast on real data (live listings)",
                    "data gate live_listings: re-read once listings have history"),
    "F-106": _gated("SPENDA", S + "ops/provider_accounts.py::settle_all (fetch_provider_costs + settle)",
                    S + "finance/governor.py::enforce; ops/provider_accounts.reconcile -> /api/funding",
                    [KA + "test_provider_cost_reports_parse_in_cents_and_per_day",
                     KA + "test_without_an_admin_key_billing_is_owner_gated_and_nothing_is_fetched",
                     KA + "test_settlement_against_the_provider_bill_writes_observed_and_opens_an_incident",
                     KA + "test_the_governor_pass_records_the_settlement_state"],
                    "provider billing is fetched read-only and settled day x model; a material gap "
                    "opens a P2 incident (the owner-typed-figures defect is gone)",
                    BILLING, "settlement against the provider's own bill needs the admin usage keys",
                    "owner: set ANTHROPIC_ADMIN_KEY / OPENAI_ADMIN_KEY (read-only)"),
    "F-103": _gated("SPENDA", S + "ops/provider_accounts.py::settle (+ spend_report.estimate_drift)",
                    S + "finance/spend_report.py::governance; /api/verify estimate_drift (CC)",
                    [KA + "test_a_bucket_of_several_calls_is_settled_without_inventing_per_call_actuals",
                     KA + "test_settlement_against_the_provider_bill_writes_observed_and_opens_an_incident",
                     "tests/test_w4_cc_company.py::test_estimate_drift_on_verify_and_money_labelled_settlement_owner_gated"],
                    "post-call settlement against provider billing (single-call buckets observed, "
                    "multi-call never apportioned); drift on /api/verify",
                    BILLING, "provider-billing settlement runs only with the admin usage keys",
                    "owner: set ANTHROPIC_ADMIN_KEY / OPENAI_ADMIN_KEY (read-only)"),
    # ---- integrator / CC ------------------------------------------------------------------
    "F-416": _done("integrator", "scripts/supply_chain.py::verify --strict (over requirements.lock + "
                   "Dockerfile: digest-pinned base, versioned apt font, pip --require-hashes)",
                   "Docker image build (railway.json builder DOCKERFILE); ops/dependencies.DEPENDENCIES "
                   "(external services with recovery)",
                   ["tests/test_w3_supply_chain.py::test_the_cli_verify_exits_zero_on_the_repo_and_strict_fails_on_open_pins",
                    "tests/test_w3_supply_chain.py::test_an_install_path_that_bypasses_the_hash_checked_lock_is_refused"],
                   "base image pinned by digest, apt font versioned, strict verification passes with "
                   "no findings; external services are recorded with failure impact and recovery in "
                   "ops/dependencies", maturity="INTEGRATED"),
}

K9_ROWS = {
    "F-362": (S + "publish/pdf.py::graded_childrens_assignment; intel/childrens measurements_govern_fit",
              S + "commerce/seo.py::build_description; publish/pdf",
              [K9G + "test_a_childs_graded_garment_says_measurements_not_age_govern_fit"]),
    "F-750": (S + "gates/certificate.py::certify (cir/topology: work direction, construction steps)",
              S + "runtime/pipeline.py::handle_certify",
              [K9G + "test_work_direction_is_written_read_back_and_held_to_the_rows"]),
    "F-761": (S + "publish/pdf.py::package_requirements / build_pattern_pdf",
              S + "runtime/release.py::handle_assets_build",
              [K9G + "test_a_graded_pdf_prints_its_size_chart_fit_care_and_is_complete"]),
    "F-762": (S + "cir/graded.py::GradedDesign.build (CIR.grading size matrix)",
              S + "creative/garment_design.py -> gates/certificate.certify",
              [K9G + "test_every_graded_size_carries_the_whole_size_matrix"]),
    "F-763": (S + "cir/graded.py::FitIntent + gates/policy.py FIT_CLAIMS",
              S + "gates/policy.py::check_listing; publish/pdf fit/ease table",
              [K9G + "test_a_fit_word_must_match_the_stated_ease"]),
    "F-768": (S + "gates/certificate.py::certify (grading_findings)",
              S + "runtime/pipeline.py::handle_certify",
              [K9G + "test_certify_recomputes_the_size_and_rechecks_the_family"]),
    "F-770": (S + "publish/pdf.py support_scope (Terms and support)",
              S + "runtime/release.py::handle_assets_build",
              [K9G + "test_a_graded_pdf_prints_its_size_chart_fit_care_and_is_complete"]),
    "F-777": (S + "gates/policy.py::check_listing (claim_findings)",
              S + "runtime/pipeline.py::handle_certify",
              [K9G + "test_each_untraceable_claim_word_is_refused"]),
    "F-794": (S + "cir/graded.py GradedDesign provenance -> gates/originality ledger",
              S + "gates/originality.py::release_findings",
              [K9G + "test_a_benchmark_informed_graded_garment_needs_its_ledger"]),
    "F-751": (S + "gates/certificate.py::stitch_semantics_findings (cir/stitches.ANATOMY)",
              S + "runtime/pipeline.py::handle_certify",
              [K9R + "test_a_star_stitch_compiles_to_its_eyes_legs_and_bases"]),
    "F-753": (S + "gates/asset_truth.py::check_asset (gates/stitch_scale reading; Component.gauge)",
              S + "runtime/release.py listing assets",
              [K9R + "test_a_generated_image_with_the_wrong_stitch_scale_is_not_certified"]),
    "F-755": (S + "teardown/reader.py::read (size_family all_size_parse / freeze_render_size)",
              S + "teardown intake",
              [K9R + "test_the_whole_size_family_is_parsed_before_one_size_is_frozen",
               K9R + "test_the_teardown_reader_reports_the_size_family"]),
    "F-756": (S + "gates/certificate.py::certify (grading_problems) + teardown/size_family.schematic_cross_check",
              S + "runtime/pipeline.py::handle_certify",
              [K9R + "test_a_schematic_disagreement_is_a_conflict_never_a_choice"]),
    "F-779": (S + "commerce/listing_tests.py::activate_variant / variant_findings",
              S + "commerce/listing_tests.py (listing-test treatments)",
              [K9R + "test_a_listing_variant_may_not_distort_product_truth"]),
    "F-784": (S + "gates/originality.py::similarity_review + presentation_review",
              S + "publish/release_gates.py::originality_gate (store.publish)",
              [K9R + "test_presentation_is_a_similarity_dimension_read_from_the_library"]),
    "F-795": (S + "gates/originality.py::similarity_review + presentation_review",
              S + "publish/release_gates.py::originality_gate; gates/certificate.certify",
              [K9R + "test_presentation_is_a_similarity_dimension_read_from_the_library"]),
    "F-792": (S + "gates/certificate.py::certify (gates/spec_freeze)",
              S + "runtime/pipeline.py::handle_certify",
              [K9R + "test_a_competitor_informed_spec_is_frozen_before_the_writer_runs"]),
}

for _uid, (_p, _c, _t) in K9_ROWS.items():
    LANE_ROWS[_uid] = _done("K9", _p, _c, _t, "handoff_K9.md row PROVEN; producer wired in the "
                            "host module named")

# F-363: the defect (assessment not fed from the CIR) is fixed by physical_plausibility(cir) in
# the children's render refusal; practical wearability still needs a worked sample.
LANE_ROWS["F-363"] = _gated(
    "K9", S + "intel/childrens.py::physical_plausibility(cir) (seams, closures, openings, "
    "proportion, trim; parts/ties read off the CIR)",
    S + "publish/pdf.py::_refuse_what_the_childrens_assessment_refuses",
    [K9R + "test_a_childs_wearable_is_held_to_physical_plausibility"],
    "children's wearables are held to CIR-derived physical plausibility; a closed-front child "
    "garment is OPENING_UNVERIFIED (UNKNOWN, never a pass)",
    {"kind": "owner", "key": "physical_proof",
     "detail": "practical wearability needs a worked sample"},
    "practical wearability on a worked sample", "owner: physical sample via the tester roster")

# F-416's producer is build tooling (lock + Dockerfile + scripts/supply_chain.py), which no live
# root can reach: TESTED is its ceiling. The code work is done; the completion target needs the
# integrator's override (w4/OVERRIDES_PROPOSED_FM2.json). Written as a refresh meanwhile.
LANE_ROWS["F-416"]["refresh"] = True
LANE_ROWS["F-416"]["set"]["maturity"] = "TESTED"
