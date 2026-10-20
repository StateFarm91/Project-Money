"""W4-CLOSE5 (2026-10-20): close Final Master rows whose criterion is met by code in the deployed
production commit b931d17, or by code built on claude/w4-CLOSE5 (dev-proven, awaiting deploy).

Same discipline as close_board.py:
  * every row keeps its acceptance criterion;
  * the corrected mapping fields name the tests that assert the criterion and the evidence
    that meets it;
  * rows whose code is in the deployed tree unchanged are listed under mapping/remap_b931d17/
    (aggregate.py REMAP_SHAS, a closure-only remap) and in BOARD_CLOSURES.json with the
    production readings and the deployed-tree test run (evidence_CLOSE5/);
  * rows whose code this branch changed are corrected in the mapping only, so the board
    counts them dev-proven, not deployed.
aggregate.py, build2_ledger.py, completion_board_final.py and prelaunch_scope.py are re-run
afterwards. Nothing here edits a test or a criterion.

  cd brambleloop && python3 research/final_build/w4/close5.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
BL = FB.parents[1]
EVB = "research/final_build/w4/evidence_BOARD"
EV5 = "research/final_build/w4/evidence_CLOSE5"
TS = "20261020T0416Z"
DEPLOYED = "b931d17a738d6a5bcd96580f620069b669ca5f57"
HEALTH = f"{EVB}/prod_health_{TS}.json"
DEPLOYED_TESTS = f"{EV5}/deployed_tree_tests_b931d17.json"
TAG = "w4-CLOSE5 on deployed b931d17"

T = "tests/test_w4_close5_rows.py::"

# (slice, uid) -> mapping corrections. "x+" appends to list x.
FM_EDITS: dict[tuple[str, str], dict] = {
    ("s2", "F-152"): {
        "coverage": "FULL",
        "missing_part": None,
        "gate": {"kind": "none", "key": None,
                 "detail": "offsite_storage OPEN in production b931d17 (/api/build gates, "
                           f"{EVB}/prod_api_build_{TS}.json); the off-provider copy exists"},
        "next_action": "none -- every scratch site is classified with its durable home "
                       "(tests/test_w4_close5_rows.py SCRATCH); a new site fails the test "
                       "until classified",
        "evidence+": [
            f"{TAG}: {EVB}/prod_api_offsite_{TS}.json -- last_archive ok, encrypted, uploaded "
            "off-provider, read back, decrypted and restored; the restore proof is an "
            "audit_log row and the archive bytes are continuity_exports rows, neither in "
            "scratch",
            f"{TAG}: rule test -- every function in src/ that creates a scratch directory "
            "(core.workspace.work_dir, TemporaryDirectory, mkdtemp; 31 sites) is classified "
            "with where its evidence becomes durable (audit row / DB row / caller that audits "
            "/ copy of DB state / CLI output path outside scratch / recomputed reading), and "
            "each durable home is checked to contain the write",
            f"{TAG}: behavioural -- the continuity proof and the offsite archive are read and "
            "restored from the database / remote store after their scratch directory is "
            f"deleted; deployed-tree run {DEPLOYED_TESTS}",
        ],
        "tests+": [T + "test_f152_every_scratch_site_is_classified",
                   T + "test_f152_each_classified_home_really_writes_or_hands_over_the_evidence",
                   T + "test_f152_continuity_evidence_outlives_its_scratch_directory",
                   T + "test_f152_offsite_evidence_outlives_its_scratch_directory"],
    },
    ("s4", "F-299"): {
        "coverage": "FULL",
        "missing_part": None,
        "producer": "src/brambleloop/core/phase.py::record_transition; "
                    "src/brambleloop/core/phase.py::effective",
        "consumer": "src/brambleloop/runtime/worker.py::protected_phase (re-resolved at every "
                    "publish / activate / ad-spend effect boundary: runtime/pipeline.py "
                    "_revalidate_publish_effect, runtime/growth_ops.py handle_ads_campaign)",
        "durable_state": "audit_log owner.phase.transition (sealed, hash-chained)",
        "gate": {"kind": "none", "key": None,
                 "detail": "the mechanism is complete; moving up is the owner's own sealed "
                           "transition (POST /api/owner/phase/transition), an action, not a gate "
                           "on this row"},
        "next_action": "none -- PhaseTransition exists (core/phase.py, W3/rc1-AUTH): owner "
                       "credential, one step at a time (shadow -> staging -> limited_production "
                       "-> production), readiness + rollback evidence refs resolved to real rows, "
                       "readiness verdict sealed at transition time, rollback down with a reason",
        "evidence+": [
            f"{TAG}: {EVB}/prod_api_verify_{TS}.json phase_is_shadow ok -- effective_phase "
            "shadow, BRAMBLELOOP_PHASE shadow, recorded_phase shadow, agree true; "
            "publication_was_actually_attempted_and_refused (186 refusals); no_paid_advertising "
            "(ad_spend_cad 0.0)",
            f"{TAG}: the mapping's 'add a PhaseTransition record' is stale -- core/phase.py "
            "record_transition/resolve/effective and app/phase_api.py are in the deployed tree; "
            f"deployed-tree run {DEPLOYED_TESTS}",
        ],
        "tests+": ["tests/test_fb4_launch.py::test_env_alone_saying_limited_production_runs_as_shadow_with_an_incident",
                   "tests/test_fb4_launch.py::test_recorded_transitions_and_env_agree_then_that_phase_applies_and_rows_are_audited",
                   "tests/test_fb4_launch.py::test_a_forged_or_edited_transition_row_is_not_authority",
                   "tests/test_fb4_launch.py::test_store_publish_refuses_when_env_says_production_but_nothing_is_recorded",
                   "tests/test_rc1_auth.py::test_A1_owner_rollback_recorded_after_boot_stops_store_activate",
                   "tests/test_w3_k4_launch_verdict.py::test_F300_rollback_to_shadow_never_requires_readiness",
                   T + "test_f299_ad_spend_follows_the_recorded_owner_transition_not_the_environment",
                   T + "test_f299_the_staging_step_cannot_be_skipped_and_needs_the_owner"],
    },
    ("s8", "F-718"): {
        "coverage": "FULL",
        "missing_part": None,
        "producer": "src/brambleloop/core/db.py; "
                    "src/brambleloop/visual/approval_record.py::compare",
        "consumer": "src/brambleloop/app/main.py::api_model_identity (approval_record state); "
                    "src/brambleloop/runtime/worker.py",
        "next_action": "none -- the approval record is a repository object (W4-PROVENANCE) "
                       "and production reads MATCH; the runtime reads no dev-lane state",
        "evidence+": [
            f"{TAG}: {EVB}/prod_api_model_identity_{TS}.json approval_record.state MATCH, "
            "database_audit_id 5693, mismatched_fields [] -- the repository record "
            "visual/approval_record.json and production's model.frozen row agree on every "
            f"pinned field ({EVB}/prod_api_audit_model_frozen_{TS}.json)",
            f"{TAG}: the 'dev-lane state depends on ops/registry records' gap -- "
            "ops/registry.py (ops/JOBS.json) is operator tooling for build sessions, outside the "
            "deployed tree; no runtime module imports it, opens its file or reads its variable "
            "(test), and each lane's outcome is committed (branch + research/final_build/w4/"
            "<NAME>.md, WORKER_RULES). Judgment call recorded in w4/CLOSE5.md for the owner",
        ],
        "tests+": ["tests/test_w4_provenance.py::test_a_matching_database_row_is_match",
                   "tests/test_w4_provenance.py::test_the_model_identity_route_serves_the_comparison",
                   T + "test_f718_the_owner_approval_is_a_repository_object_matching_the_database",
                   T + "test_f718_the_runtime_reads_no_dev_lane_or_session_state"],
    },
    ("s4", "F-283"): {
        "coverage": "FULL",
        "missing_part": None,
        "consumer": "finance/sources.py::table; growth/loops/order_readings via SOURCE_TO_LOOP "
                    "(unknown has no loop); POST /api/orders/attribution (operator) -> "
                    "sources.attribute + record_first_sale",
        "gate": {"kind": "none", "key": None,
                 "detail": "transactions_r OPEN in production b931d17; the criterion is the "
                           "honest recording rule, which needs no sale to verify"},
        "next_action": "none -- W4-FMCLOSE built the evidence route (deployed in b931d17); the "
                       "first real sale is data, not a step",
        "evidence+": [
            f"{TAG}: POST /api/orders/attribution (app/main.py, deployed) requires the operator "
            "credential and evidence, and refreshes the first-sale record; the table always "
            "shows etsy_organic, etsy_ads, offsite_ads, owned_direct and unattributed, and the "
            "first-sale record carries 'One sale proves possibility, not scale'; deployed-tree "
            f"run {DEPLOYED_TESTS}",
        ],
        "tests+": ["tests/test_w4_fmclose_etsy.py::test_f283_the_owner_attributes_an_order_with_evidence_and_the_first_sale_follows",
                   "tests/test_money_truth.py::test_the_traffic_table_shows_every_channel_and_an_explicit_unattributed_bucket",
                   "tests/test_money_truth.py::test_the_first_sale_is_recorded_once_with_source_evidence_and_the_scale_caveat",
                   "tests/test_money_truth.py::test_an_acquisition_source_without_evidence_is_refused"],
    },
}

# ---- batch 2: the W4-FMCLOSE Etsy rows (built 2026-10-12, deployed in b931d17, never written
# back to the mapping because module_reachability.json predated their modules) ----------------
FM = "tests/test_w4_fmclose_etsy.py::"
R2 = "tests/test_w4_close5_rows2.py::"
TR_OPEN = {"kind": "none", "key": None,
           "detail": "transactions_r OPEN in production b931d17 (/api/build gates, "
                     f"{EVB}/prod_api_build_{TS}.json); no owner step remains on this row"}
REACH = (f"{TAG}: module_reachability regenerated on the deployed tree "
         f"({EV5}/module_reachability_b931d17.json, 697 modules, 604 reached, none lost vs "
         "0417f35) -- the module is reached from a live root")
FM_EDITS.update({
    ("s8", "F-682"): {
        "coverage": "FULL", "missing_part": None, "gate": TR_OPEN,
        "producer": "src/brambleloop/finance/accounting/activity.py::activity",
        "consumer": "src/brambleloop/finance/accounting/dashboard.py::summary (owner Money "
                    "view, activity block)",
        "next_action": "none -- W4-FMCLOSE built it; deployed in b931d17",
        "evidence+": [f"{TAG}: activity() shows last reconciliation (NEVER_RUN before the "
                      "first), the open fee mismatch with booked vs statement evidence, close "
                      "status (locked periods) and tax/threshold alerts (UNKNOWN is never 0); a "
                      "second controller cycle leaves the discrepancy open, never zeroed; "
                      f"deployed-tree run {DEPLOYED_TESTS}", REACH],
        "tests+": [FM + "test_f682_activity_shows_reconciliation_discrepancies_close_and_alerts_never_zeroed",
                   FM + "test_f682_threshold_alert_approaches_and_crosses"],
    },
    ("s7", "F-558"): {
        "coverage": "FULL", "missing_part": None, "gate": TR_OPEN,
        "producer": "src/brambleloop/commerce/order_ledger.py::ledger; "
                    "src/brambleloop/commerce/orders_ingest.py::ingest",
        "consumer": "src/brambleloop/app/main.py::api_orders_ledger (GET /api/orders/ledger, "
                    "operator credential)",
        "next_action": "none -- W4-FMCLOSE built it; deployed in b931d17; a real receipt is data",
        "evidence+": [f"{TAG}: per order -- payment state, item (listing id, product, version "
                      "and how the version was known), digital delivery state (UNKNOWN when the "
                      "line does not say), buyer cases, refund/cancellation state with reasons, "
                      "and the sale ledger row; any disagreement is a named problem; deployed-tree "
                      f"run {DEPLOYED_TESTS}", REACH],
        "tests+": [FM + "test_f558_every_order_reconciles_six_parts_and_names_what_does_not",
                   R2 + "test_f558_item_version_is_named_with_its_basis_and_a_cancellation_reaches_the_row",
                   R2 + "test_f558_an_unknown_version_is_a_problem_never_a_pass"],
    },
    ("s7", "F-570"): {
        "coverage": "FULL", "missing_part": None, "gate": TR_OPEN,
        "defect": None,
        "producer": "src/brambleloop/commerce/paid_media.py::offsite_share; "
                    "commerce/paid_media.py::offsite_ads_forecast",
        "consumer": "src/brambleloop/runtime/growth_ops.py::ads_plan (ads.adjust)",
        "next_action": "none -- W4-FMCLOSE fixed unread-as-0% and built the fee/margin read",
        "evidence+": [f"{TAG}: attribution is tri-state (unread is UNMEASURED, never a 0% "
                      "share); an offsite_ads_fee ledger line sets attribution and the fee, and "
                      "contribution is recomputed with it; the 15% rate, 30-day window and "
                      "365-day participation threshold are reported; deployed-tree run "
                      f"{DEPLOYED_TESTS}",
                      f"{TAG}: the recorded defect ('_record_line never sets "
                      "offsite_ad_attributed, so the share would read as a measured 0%') is "
                      "fixed: the column default is no longer read as a measurement -- "
                      "paid_media.offsite_attribution reads the ledger fee line, and an unread "
                      "order is UNMEASURED (test_f570_unread_attribution_is_unmeasured_never_a_"
                      "zero_share asserts both the default and the UNMEASURED share)"],
        "tests+": [FM + "test_f570_unread_attribution_is_unmeasured_never_a_zero_share",
                   FM + "test_f570_ledger_read_measures_attribution_fee_and_recomputed_margin",
                   FM + "test_f570_ads_plan_reports_unknown_attribution_and_the_threshold_status"],
    },
    ("s7", "F-574"): {
        "coverage": "FULL", "missing_part": None, "gate": TR_OPEN,
        "defect": None,
        "producer": "src/brambleloop/finance/channel_comparison.py::compare",
        "consumer": "src/brambleloop/runtime/growth_ops.py::ads_plan",
        "next_action": "none -- W4-FMCLOSE built it; data accrues with sales",
        "evidence+": [f"{TAG}: organic search, Etsy Ads, Offsite Ads, social and Share & Save "
                      "compared per listing and per product family; one credit per order, a "
                      "flag/source disagreement is a named conflict, unknown stays unattributed; "
                      f"deployed-tree run {DEPLOYED_TESTS}", REACH,
                      f"{TAG}: the recorded defect (channel fields defaulting to organic-looking "
                      "values) is fixed: orders_ingest writes acquisition_source='unknown' "
                      "(orders_ingest.py:956,963) and finance.sources maps the legacy 'etsy' to "
                      "unattributed; the test asserts an unknown order stays unattributed"],
        "tests+": [FM + "test_f574_channels_compared_per_listing_and_family_one_credit_per_order",
                   "tests/test_money_truth.py::test_ingest_writes_unknown_source_and_a_modelled_fee_never_presented_as_charged"],
    },
    ("s8", "F-657"): {
        "coverage": "FULL", "missing_part": None, "gate": TR_OPEN,
        "producer": "src/brambleloop/autonomy/event_wakes.py::scan",
        "consumer": "src/brambleloop/autonomy/handlers.py::handle_orchestrate (autonomy.orchestrate "
                    "tick runs the scan; each wake enqueues its team's job once)",
        "next_action": "none -- W4-FMCLOSE built it; deployed in b931d17",
        "evidence+": [f"{TAG}: orders, refunds, reviews, messages, policy changes, incidents, "
                      "spend anomalies, research signals and owner decisions each wake their team "
                      "once (idempotency wake:<kind>:<marker>); Etsy events wake from the webhook "
                      "receiver; schedules are the Scheduler's cadences; deployed-tree run "
                      f"{DEPLOYED_TESTS}", REACH],
        "tests+": [FM + "test_f657_each_business_event_wakes_its_team_once",
                   FM + "test_f657_the_orchestrate_tick_runs_the_event_scan"],
    },
    # dev-proven, awaiting deploy: integrations/etsy_webhooks.py changed on this branch (R1)
    ("s6", "F-512"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "gate": {"kind": "none", "key": None,
                 "detail": "the receiver is built; registering the endpoint in Etsy's portal and "
                           "setting ETSY_WEBHOOK_SECRET is the owner's step for live deliveries, "
                           "not part of this criterion"},
        "producer": "src/brambleloop/integrations/etsy_webhooks.py::receive",
        "consumer": "src/brambleloop/app/main.py::api_etsy_webhook (POST /api/etsy/webhook); "
                    "GET /api/etsy webhooks summary",
        "durable_state": "etsy_webhook_deliveries; etsy_webhook_refusals",
        "next_action": "none in code -- dev-proven on claude/w4-CLOSE5 (R1 gate), awaiting deploy",
        "evidence+": [f"w4-CLOSE5: validation (HMAC, skew, headers, event, shop), idempotent "
                      "storage, duplicate guard, 5xx so Etsy retries, observability (summary, "
                      "refusal counters, R1 admission-gate counters); R1 adds a private admission "
                      "gate (tests/test_w4_close5_r1.py) -- dev-proven, awaiting deploy", REACH],
        "tests+": [FM + "test_f512_validation_refuses_every_unprovable_delivery_before_writing",
                   FM + "test_f512_idempotent_storage_duplicate_protection_and_observability",
                   FM + "test_f512_a_storage_failure_answers_5xx_so_etsy_retries",
                   FM + "test_f512_route_is_public_signed_and_reported_on_api_etsy",
                   "tests/test_w4_close5_r1.py::test_r1_the_route_answers_503_with_no_db_work_when_saturated_then_recovers"],
    },
    ("s6", "F-501"): {
        "coverage": "FULL", "missing_part": None, "gate": TR_OPEN,
        "producer": "src/brambleloop/integrations/etsy_webhooks.py::receive; "
                    "src/brambleloop/commerce/orders_ingest.py::ingest",
        "consumer": "src/brambleloop/runtime/orders.py::handle_order_readings",
        "next_action": "none in code -- dev-proven on claude/w4-CLOSE5 (etsy_webhooks R1 edit), "
                       "awaiting deploy",
        "evidence+": [f"w4-CLOSE5: a verified Etsy event is stored once and enqueues one "
                      "authenticated receipt read keyed etsy.webhook:<id>; two events about one "
                      "receipt make one order (etsy:<receipt>:<transaction> unique); "
                      f"transactions_r OPEN on b931d17 ({EVB}/prod_api_build_{TS}.json)", REACH],
        "tests+": [FM + "test_f501_verified_events_feed_the_idempotent_order_layer"],
    },
})


# Rows whose code is in the deployed tree unchanged: closed on production readings of b931d17
# plus the deployed-tree test run.
PRODUCTION_CLOSED = {
    "F-152": [f"{EVB}/prod_api_offsite_{TS}.json", f"{EVB}/prod_api_build_{TS}.json",
              DEPLOYED_TESTS],
    "F-299": [f"{EVB}/prod_api_verify_{TS}.json", DEPLOYED_TESTS],
    "F-718": [f"{EVB}/prod_api_model_identity_{TS}.json",
              f"{EVB}/prod_api_audit_model_frozen_{TS}.json", DEPLOYED_TESTS],
    "F-283": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS],
    "F-682": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS,
              f"{EV5}/module_reachability_b931d17.json"],
    "F-558": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS,
              f"{EV5}/module_reachability_b931d17.json"],
    "F-570": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS],
    "F-574": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS,
              f"{EV5}/module_reachability_b931d17.json"],
    "F-657": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS,
              f"{EV5}/module_reachability_b931d17.json"],
}
READING = {
    "F-152": "offsite last_archive ok on b931d17 (encrypted, off-provider, read back, restored); "
             "scratch-site rule + scratch-deletion tests pass on the deployed tree",
    "F-299": "verify phase_is_shadow: env shadow == recorded shadow, agree; 186 publication "
             "refusals; ad spend 0.0; phase transition tests pass on the deployed tree",
    "F-718": "model-identity approval_record MATCH (audit 5693) on b931d17; runtime reads no "
             "dev-lane state (test on the deployed tree)",
    "F-283": "attribution route + channel table + first-sale caveat tests pass on the deployed "
             "tree; transactions_r gate OPEN on b931d17",
    "F-682": "accountant activity tests pass on the deployed tree; module reached on b931d17; "
             "transactions_r OPEN",
    "F-558": "order ledger tests (six parts, item/version, cancellation) pass on the deployed "
             "tree; module reached on b931d17; transactions_r OPEN",
    "F-570": "offsite-ads attribution/fee/margin tests pass on the deployed tree; transactions_r OPEN",
    "F-574": "channel comparison tests pass on the deployed tree; module reached on b931d17",
    "F-657": "event wake tests pass on the deployed tree; module reached on b931d17",
}


# ---- spot audit of 20 more verified rows (random.seed(20261020) over the verified_complete
# rows not already in BOARD_AUDIT.json, on the board regenerated against b931d17) ------------
A = "tests/test_w4_close5_audit.py::"
RECLOSE = {"at": "2026-10-20", "by": "W4-CLOSE5",
           "what": "the missing clause is now asserted by the named test(s); code unchanged "
                   "(behaviour already in the deployed b931d17)"}
AUDIT5 = [
    ("final_master", "F-784", "PASS",
     "all five named dimensions are compared and material overlap escalates: wording "
     "(hashes), unusual numeric runs, construction, distinctive features, presentation",
     ["tests/test_k9_rows.py::test_presentation_is_a_similarity_dimension_read_from_the_library",
      "tests/test_originality.py::test_a_relabelled_benchmark_1_is_escalated_for_redesign",
      "tests/test_originality.py::test_a_light_derivative_of_benchmark_2_is_escalated_for_redesign",
      "tests/test_originality.py::test_an_unusual_numeric_run_in_the_text_escalates_but_an_arithmetic_one_does_not",
      "tests/test_originality.py::test_wording_overlap_is_measured_from_hashes_and_escalates"],
     "ledger cites 2 of the 5 dimensions; the other three are asserted in tests/test_originality.py",
     None),
    ("final_master", "F-251", "DOWNGRADE",
     "criterion: 'Titles/tags follow shop-language rules; translations are deliberate and not "
     "used as impression bait'",
     ["tests/test_search_truth.py::test_a_non_english_tag_is_refused_without_a_translation_record",
      "tests/test_w3_k1_search.py::test_ascii_foreign_words_are_caught_and_bait_translations_refused"],
     "both cited tests put the foreign words in a TAG; no test asserts a foreign-language TITLE "
     "is refused (seo.check_search_copy does scan the title, untested)",
     [A + "test_f251_a_foreign_language_title_is_refused_unless_a_deliberate_translation"]),
    ("final_master", "F-073", "DOWNGRADE",
     "criterion names fitted garments, complex grading, closed 3-D forms, novel assemblies, "
     "high-yardage claims and new construction primitives",
     ["tests/test_risk_matrix.py::test_a_closed_stuffed_form_is_class_c_and_a_declared_c_is_never_lowered",
      "tests/test_risk_matrix.py::test_graded_garments_are_at_least_class_b",
      "tests/test_risk_matrix.py::test_launch0_tiers_are_derived_from_features_not_typed"],
     "no test asserts the multi_seam_assembly (novel assembly) or uncalibrated_primitive "
     "(new primitive) features raise the matrix class; both exist in gates/risk_matrix.features",
     [A + "test_f073_a_novel_assembly_raises_the_class_and_a_short_one_does_not",
      A + "test_f073_a_new_construction_primitive_raises_the_class_until_calibrated"]),
    ("final_master", "F-835", "PASS",
     "revalidation at the effect boundary on publish (halting incident, moved upstream), "
     "withholding through every rebuild path, a revoked grant before draft creation and a "
     "revoke/mutation during a reservation",
     ["tests/test_cert_publish_gates.py::test_a_halting_incident_blocks_store_publish_before_any_upload",
      "tests/test_draft_intent_precreate_refusal.py::PreCreateRefusal.test_revoked_grant_is_refused",
      "tests/test_operating_cost_basis.py::test_revoke_or_mutate_during_reservation_refuses_external_effect"],
     None, None),
    ("build2", 194, "PASS",
     "every named domain is required in a complete cycle; add/merge/retire/revise-metric moves "
     "are validated; the roadmap carries completeness forward",
     ["tests/test_weekly.py::test_every_domain_the_requirement_names_is_present",
      "tests/test_weekly.py::test_three_of_the_four_moves_are_not_additions",
      "tests/test_weekly.py::test_a_valid_revision_preserves_the_old_metrics_history",
      "tests/test_weekly.py::test_the_roadmap_carries_the_cycles_completeness_forward"],
     None, None),
    ("final_master", "F-860", "PASS",
     "with the visual gate closed, unrelated READY work is next and claimable",
     ["tests/test_w3_final_master_gate.py::test_executor_reports_parked_work_split_by_kind_and_the_final_master"],
     None, None),
    ("build2", 219, "DOWNGRADE",
     "criterion: 'a changing elite panel including other category leaders and purchased "
     "Benchmark Library products'",
     ["tests/test_cert_intel_wave.py::test_panel_discovery_registers_and_scans_a_second_elite_seller_in_a_second_market"],
     "the test adds a second observed seller; nothing asserts that a purchased Benchmark "
     "Library product (BenchmarkProduct) puts its seller on the panel, though "
     "mission_runtime.panel_members reads them",
     [A + "test_b2_219_a_purchased_library_product_puts_its_seller_on_the_panel"]),
    ("build2", 57, "PASS",
     "four purpose classes exist and a chart cannot be the hero by rendering",
     ["tests/test_eligibility.py::test_every_purpose_the_requirement_names_exists",
      "tests/test_eligibility.py::test_a_chart_cannot_become_the_hero_by_rendering_successfully"],
     "the ledger cites no test; the criterion is asserted in tests/test_eligibility.py", None),
    ("build2", 139, "PASS",
     "a catchphrase is declared a slogan token and refused in copy; direct use needs a recorded "
     "basis; without one the original-language lane is taken",
     ["tests/test_cert_intel_wave2.py::test_a_catchphrase_topic_declares_a_slogan_token_the_copy_screen_refuses",
      "tests/test_cert_parity_copy.py::test_a_declared_catchphrase_in_the_copy_blocks_listing_seo_unless_cleared",
      "tests/test_culture.py"],
     "the ledger cites only test_cert_intel_wave2; clearance and the original lane are in "
     "test_cert_parity_copy and test_culture", None),
    ("final_master", "F-277", "PASS",
     "concentration on one query is measured and listing.seo moves slots off shared phrases",
     ["tests/test_portfolio.py::test_a_catalogue_all_reaching_for_one_term_is_concentrated_and_cannibalising",
      "tests/test_cert_parity_copy.py::test_diversify_moves_slots_off_shared_phrases_when_alternatives_exist"],
     None, None),
    ("final_master", "F-891", "PASS",
     "declared-tier routing never degrades a deep task; every department charter carries an "
     "evidence requirement and an escalation rule; idle work is evidence-backed",
     ["tests/test_v11_reliability_gateway.py::test_deep_task_with_its_model_down_parks_rather_than_degrading",
      "tests/test_v11_reliability_gateway.py::test_fallbacks_only_go_up_and_deep_has_none",
      "tests/test_v11_autonomy_orchestrator.py::test_every_charter_has_kpis_with_guardrails_and_a_generator"],
     "the charter test (escalation + evidence requirement per department) is not in the "
     "ledger's citation", None),
    ("final_master", "F-057", "DOWNGRADE",
     "criterion: 'Capture buyer-relevant crochet technique/material differentiators truthfully'",
     ["tests/test_commerce.py::test_a_technique_the_pattern_does_not_use_is_never_tagged"],
     "only technique truth is asserted; no test refuses a MATERIAL the pattern does not use "
     "(seo.truth refuses it and seo.strategy blocks the family phrase, untested)",
     [A + "test_f057_a_material_the_pattern_does_not_use_is_refused_and_the_strategy_blocks_it"]),
    ("build2", 200, "PASS",
     "the owner selects once; a second selection is a redesign; the pack is versioned, "
     "persisted, pinned by hash, and drift blocks",
     ["tests/test_model_identity.py::test_the_owner_selects_one_and_a_second_selection_is_a_redesign",
      "tests/test_model_identity.py::test_a_matching_face_passes_and_a_drifted_one_blocks",
      "tests/test_model_freeze.py::test_nothing_freezes_without_the_owner_and_nothing_freezes_twice",
      "tests/test_model_freeze.py::test_the_freeze_pins_every_reference_by_hash"],
     "the ledger cites no test; the criterion is asserted in test_model_identity/test_model_freeze",
     None),
    ("final_master", "F-133", "PASS",
     "a partial with no named gate or check is refused by both the adjudicator and the runtime",
     ["tests/test_w3_final_master_gate.py::test_an_orphaned_partial_is_named_by_both_the_adjudicator_and_the_runtime"],
     None, None),
    ("final_master", "F-700", "PASS",
     "each per-action clause blocks and fails closed; every clause names an importable enforcer",
     ["tests/test_w3_k11_authority.py::test_f700_evaluate_blocks_each_per_action_clause_and_fails_closed",
      "tests/test_w3_k11_authority.py::test_f700_every_clause_names_an_importable_enforcer"],
     None, None),
    ("build2", 233, "PASS",
     "the ladder's rungs, gaps, tier movement (unmeasurable, not zero), lifetime value and the "
     "discount rules are asserted",
     ["tests/test_ladder.py::test_a_complete_ladder_is_climbable",
      "tests/test_ladder.py::test_tier_movement_is_unmeasurable_rather_than_zero",
      "tests/test_ladder.py::test_lifetime_value_needs_a_lifetime",
      "tests/test_ladder.py::test_the_flagship_is_never_routinely_discounted"],
     "the ledger cites only test_cert_orders.py; the ladder is asserted in tests/test_ladder.py",
     None),
    ("final_master", "F-101", "PASS",
     "every spend path is ceiling-checked (scan); a non-llm kind closes the month and an "
     "unknown kind counts inside the ceiling",
     ["tests/test_model_spend_paths.py::test_no_model_spend_path_reaches_a_provider_without_the_ceiling_check",
      "tests/test_rc1_spend.py::test_b2_image_spend_closes_the_monthly_ceiling"],
     "the alias half is asserted by test_rc1_spend (not cited by the ledger)", None),
    ("final_master", "F-918", "PASS",
     "every department has up-KPIs with guardrails; a refused job and duplicate/no-op output "
     "void or cannot farm the KPI",
     ["tests/test_v11_autonomy_orchestrator.py::test_every_charter_has_kpis_with_guardrails_and_a_generator",
      "tests/test_v11_autonomy_kpis.py::test_a_refused_job_voids_every_kpi_of_its_department",
      "tests/test_v11_autonomy_kpis.py::test_duplicate_and_noop_outputs_cannot_farm_the_useful_count"],
     "the 'each department has KPIs plus guardrails' test is not in the ledger's citation", None),
    ("final_master", "F-074", "PASS",
     "a new primitive starts uncalibrated and restricts the certificate until a passed sample "
     "calibrates it",
     ["tests/test_gates.py::test_a_pattern_using_an_uncalibrated_primitive_is_restricted_until_evidence",
      "tests/test_gates.py::test_every_primitive_carries_a_calibration_status_and_new_ones_start_uncalibrated"],
     None, None),
    ("build2", 63, "PASS",
     "the six-stage flow runs in order in assets.build; invented content is blocked in every "
     "category (motif, dimension, texture, construction, deliverable) and sent back to the brief",
     ["tests/test_cert_parity_copy.py::test_assets_build_walks_the_evidence_to_creative_flow",
      "tests/test_cert_parity_copy.py::test_creative_that_invents_a_stitch_is_blocked_and_sent_back_to_the_brief",
      "tests/test_brief.py::test_invention_is_caught_in_each_category_not_only_motifs",
      "tests/test_brief.py::test_a_deliverable_nobody_ships_is_the_expensive_one"],
     "the category-by-category invention test is in tests/test_brief.py (not cited)", None),
]


def apply_audit5() -> dict:
    path = HERE / "BOARD_AUDIT.json"
    audit = json.loads(path.read_text())
    have = {(r["source"], r["id"]) for r in audit["rows"]}
    audit["sample"]["close5_random"] = ("20 rows, random.seed(20261020) over the "
                                        "verified_complete rows not already audited, on the "
                                        "board regenerated against production b931d17 "
                                        "(W4-CLOSE5 2026-10-20)")
    added = 0
    for src, rid, verdict, basis, evidence, finding, reclose in AUDIT5:
        if (src, rid) in have:
            continue
        row = {"source": src, "id": rid, "sample": "close5_random", "verdict": verdict,
               "basis": basis, "evidence": evidence, "production_reading": None}
        if verdict == "DOWNGRADE":
            row["downgrade_reason"] = finding
            row["reclosed"] = {"tests": reclose, **RECLOSE}
        elif finding:
            row["citation_finding"] = finding
        audit["rows"].append(row)
        added += 1
    path.write_text(json.dumps(audit, indent=1, ensure_ascii=False) + "\n")
    return {"added": added,
            "downgraded": [f"{s}:{i}" for s, i, v, *_ in AUDIT5 if v == "DOWNGRADE"]}


def main() -> int:
    remap = []
    for (sl, uid), ed in FM_EDITS.items():
        path = FB / "mapping" / f"{sl}.json"
        rows = json.loads(path.read_text())
        hit = False
        for r in rows:
            if r["uid"] != uid:
                continue
            hit = True
            for k, v in ed.items():
                if k.endswith("+"):
                    key = k[:-1]
                    r[key] = list(r.get(key) or []) + [x for x in v if x not in (r.get(key) or [])]
                else:
                    r[k] = v
            r["searched"] = (str(r.get("searched") or "") + " | " + TAG).strip(" |")
            if uid in PRODUCTION_CLOSED:
                remap.append(r)
        assert hit, (sl, uid)
        path.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    out = FB / "mapping" / "remap_b931d17"
    out.mkdir(exist_ok=True)
    (out / "remap_w4_close5.json").write_text(json.dumps(remap, indent=1, ensure_ascii=False)
                                               + "\n")

    cl_path = HERE / "BOARD_CLOSURES.json"
    cl = json.loads(cl_path.read_text())
    have = {(c["source"], c["id"]) for c in cl["rows"]}
    import sys
    sys.path.insert(0, str(FB))
    import aggregate

    reg = aggregate.load_registry()
    for uid, files in PRODUCTION_CLOSED.items():
        if ("final_master", uid) in have:
            continue
        sl = next(s for (s, u) in FM_EDITS if u == uid)
        req = reg.get(uid) or {}
        cl["rows"].append({
            "source": "final_master", "id": uid,
            "criterion": str(req.get("full_text") or req.get("title") or uid),
            "evidence_files": files, "health_file": HEALTH, "reading": READING[uid],
            "tests": FM_EDITS[(sl, uid)]["tests+"], "worker": "W4-CLOSE5 2026-10-20",
            "deployed_commit": DEPLOYED})
    cl_path.write_text(json.dumps(cl, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"fm": [u for _s, u in FM_EDITS], "production_closed": list(PRODUCTION_CLOSED),
                      "audit": apply_audit5()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
