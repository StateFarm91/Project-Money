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


# ---- batch 3: rows built by W4 lanes that never wrote their mapping back (W4-FAILMEM,
# W4-RESEARCH, W4-IMPROVEMETRICS; all merged and deployed in b931d17), the LC rows F-535 /
# F-542 whose code was already deployed, and F-878 (the packet generated by the deployed tree) --
FAILMEM = "tests/test_w4_failmem.py::"
RES = "tests/test_w4_research.py::"
IMP = "tests/test_w4_improvemetrics.py::"
R3 = "tests/test_w4_close5_rows3.py::"
DT = f"deployed-tree run {DEPLOYED_TESTS}"
FM_EDITS.update({
    ("s5", "F-378"): {
        "coverage": "FULL", "missing_part": None, "defect": None,
        "producer": "src/brambleloop/improve/failure_memory.py::check; "
                    "improve/failure_memory.py::record",
        "consumer": "src/brambleloop/improve/cells.py::propose (refuses a repeat of a measured "
                    "failure inside its scope unless new evidence or a changed premise is cited)",
        "durable_state": "failure_memory; improvements",
        "next_action": "none -- W4-FAILMEM built it; deployed in b931d17",
        "evidence+": [f"{TAG}: failures are fingerprinted (cell, normalised claim, touches, "
                      "premise digest) with the evidence ids that rejected them; cells.propose "
                      "refuses the repeat (audited improve.repeat_refused) and reopens on new "
                      "evidence or a changed premise; DECISION_LOG dead ends are seeded; the "
                      f"recorded defect (stop_doing advisory, propose did not consult it) is "
                      f"fixed by that guard; {DT}", REACH],
        "tests+": [FAILMEM + "test_the_same_failed_improvement_months_later_is_refused",
                   FAILMEM + "test_new_evidence_or_a_changed_premise_reopens_the_question",
                   FAILMEM + "test_decision_log_dead_ends_are_seeded_and_enforced",
                   FAILMEM + "test_digits_are_kept_so_new_measurements_are_a_new_claim"],
    },
    ("s5", "F-427"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/improve/failure_memory.py::record",
        "consumer": "src/brambleloop/improve/cells.py::propose",
        "durable_state": "failure_memory",
        "next_action": "none -- W4-FAILMEM built it; deployed in b931d17",
        "evidence+": [f"{TAG}: a measured failure or a recorded finding with evidence and scope is "
                      "durable (failure_memory, NON_REDERIVABLE in continuity); a refusal, a "
                      "first measurement or a withdrawal is not a failure, so absence of success "
                      f"never retires an idea; {DT}"],
        "tests+": [FAILMEM + "test_a_refusal_or_first_measurement_is_not_a_failure",
                   FAILMEM + "test_a_reverted_promotion_is_remembered",
                   FAILMEM + "test_records_need_evidence_and_scope",
                   FAILMEM + "test_failure_memory_is_a_non_rederivable_record"],
    },
    ("s5", "F-428"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/improve/failure_memory.py::check; "
                    "improve/failure_memory.py::generalise",
        "consumer": "src/brambleloop/improve/cells.py::propose",
        "next_action": "none -- W4-FAILMEM built it; deployed in b931d17",
        "evidence+": [f"{TAG}: a failure blocks only proposals inside its method, class and "
                      "conditions; widening a scope needs new evidence, narrowing needs none; "
                      f"{DT}"],
        "tests+": [FAILMEM + "test_scope_blocks_only_inside_the_observed_conditions",
                   FAILMEM + "test_generalisation_beyond_scope_needs_new_evidence"],
    },
    ("s8", "F-706"): {
        "coverage": "FULL", "missing_part": None, "defect": None,
        "consumer": "src/brambleloop/improve/failure_memory.py::check (consulted by propose); "
                    "src/brambleloop/improve/profiles.py::self_review",
        "next_action": "none -- the repeat guard (W4-FAILMEM) is deployed in b931d17",
        "evidence+": [f"{TAG}: the recorded defect (no guard against repeating a known failed "
                      "experiment) is fixed: the identical failed improvement proposed months "
                      "later is refused and the refusal is audited; experiments, evidence, cost, "
                      f"result and decision persist as before; {DT}"],
        "tests+": [FAILMEM + "test_the_same_failed_improvement_months_later_is_refused",
                   FAILMEM + "test_a_reverted_promotion_is_remembered"],
    },
    ("s5", "F-403"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/intel/research.py::detect_unknowns",
        "consumer": "src/brambleloop/learn/runtime.py learn.scan handler (hourly) -> "
                    "research_tasks",
        "durable_state": "research_tasks",
        "next_action": "none -- W4-RESEARCH built it; deployed in b931d17",
        "evidence+": [f"{TAG}: unknowns on decision paths (unobserved learning domains, "
                      "children's-safety sources never fetched) open a research question once, "
                      "from the hourly learn.scan; stale answers re-open on expiry; UNKNOWN / "
                      f"UNMEASURED readings stay explicit everywhere else; {DT}", REACH],
        "tests+": [RES + "test_unknowns_on_decision_paths_open_research_questions_once",
                   RES + "test_an_observed_domain_is_no_longer_an_unknown",
                   RES + "test_learn_scan_routes_unknowns"],
    },
    ("s5", "F-409"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/intel/research.py::add_finding; intel/learning.py::record",
        "next_action": "none -- W4-RESEARCH built it; deployed in b931d17",
        "evidence+": [f"{TAG}: findings and observations carry claim_class fact | source_claim | "
                      "inference | hypothesis | unresolved; a fact needs a fetched/repository/"
                      "rendered/internal source, a search summary supports only a source claim, "
                      "claims and guesses cannot close a task; pre-existing rows read "
                      f"'unresolved', never an assigned class; {DT}"],
        "tests+": [RES + "test_claim_classes_are_enforced",
                   RES + "test_claims_and_guesses_cannot_close_a_task",
                   RES + "test_learning_observations_carry_class_terms_and_decision"],
    },
    ("s5", "F-424"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/intel/learning.py::record; intel/research.py",
        "consumer": "src/brambleloop/intel/learning.py::observations",
        "next_action": "none -- W4-RESEARCH built it; deployed in b931d17",
        "evidence+": [f"{TAG}: observations and research tasks record query_terms and "
                      "decision_ref beside source, citation and date; tasks record sources with "
                      f"retrieval class and read date; {DT}"],
        "tests+": [RES + "test_learning_observations_carry_class_terms_and_decision",
                   RES + "test_internal_evidence_is_searched_first"],
    },
    ("s5", "F-433"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/intel/research.py::expire_due; improve/freshness.py::sweep",
        "consumer": "src/brambleloop/learn/runtime.py learn.scan handler (expire_due)",
        "next_action": "none -- W4-RESEARCH built it; deployed in b931d17",
        "evidence+": [f"{TAG}: a research answer's expires_on comes from its domain (marketplace "
                      "policy 21 d, techniques 365 d, market 3 d); a mathematical finding never "
                      "expires on a date; an unknown domain is refused (no default expiry); an "
                      f"expired answer re-opens its question; {DT}"],
        "tests+": [RES + "test_answers_expire_by_their_domain_and_mathematical_never_does"],
    },
    ("s5", "F-399"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/improve/cells.py::retrospective; "
                    "improve/director.py::experiments",
        "next_action": "none -- W4-IMPROVEMETRICS built it; deployed in b931d17",
        "evidence+": [f"{TAG}: retrospective learning_health reports adoption and rejection "
                      "rates (None until a verdict), regressions caught, repeated failures "
                      "avoided (improve.repeat_refused rows) and cost per adopted change (only "
                      f"when every adopted change has attributed spend); {DT}"],
        "tests+": [IMP + "test_learning_health_rates_are_none_until_a_verdict",
                   IMP + "test_learning_health_measures_adoption_rejection_regressions_and_cost"],
    },
    ("s7", "F-605"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/improve/bus.py::withdraw; improve/bus.py::publish",
        "next_action": "none -- W4-IMPROVEMETRICS built it; deployed in b931d17",
        "evidence+": [f"{TAG}: a lesson is withdrawn only with a reason and an evidence ref "
                      "(audited lesson.withdrawn), stays on file, and is no longer matched by "
                      f"consume.matching; {DT}"],
        "tests+": [IMP + "test_a_withdrawn_lesson_is_kept_but_no_longer_matched"],
    },
    ("s6", "F-535"): {
        "coverage": "FULL", "missing_part": None, "gate": TR_OPEN,
        "next_action": "none -- deployed; a real refund is data",
        "evidence+": [f"{TAG}: every refund, cancellation and support case gets a reason code "
                      "and an owner; a repeated cause opens one investigation incident naming "
                      "the area (listing, deliverable, ...) and resolves when the cause goes; "
                      f"refund reasons are captured at ingest; {DT}"],
        "tests+": ["tests/test_k8_shop_cx.py::test_every_refund_and_case_gets_a_code_and_owner_and_repetition_opens_an_investigation",
                   "tests/test_k8_shop_cx.py::test_refund_reasons_are_captured_at_ingest"],
    },
    ("s6", "F-542"): {
        "coverage": "FULL", "missing_part": None,
        "gate": {"kind": "none", "key": None,
                 "detail": "etsy_api OPEN in production b931d17; the read-back is in the deployed "
                           "publish, activate and rollback paths"},
        "producer": "src/brambleloop/runtime/pipeline.py::_publish_and_read_back; "
                    "src/brambleloop/integrations/etsy_verify.py::verify",
        "consumer": "src/brambleloop/runtime/pipeline.py::handle_store_activate; "
                    "src/brambleloop/commerce/listing_rollback.py::execute",
        "next_action": "none -- the mapping's 'publish path performs no read-back' is stale",
        "evidence+": [f"{TAG}: publish reads the draft, files, images and alt text back "
                      "(etsy_ops.read_back) and a draft whose read-back fails is "
                      "incomplete_on_etsy; activation reads the state back and a 2xx that left "
                      "the listing inactive is store.activate_incomplete with an incident; a "
                      "rollback reads its fields back and reports what still differs; every "
                      "mutation call site in src/ is checked by rule (draft-only sites listed "
                      f"with reasons); {DT}"],
        "tests+": [R3 + "test_f542_every_customer_affecting_etsy_mutation_is_followed_by_a_readback",
                   R3 + "test_f542_an_activation_etsy_accepted_but_did_not_apply_is_not_recorded_live",
                   R3 + "test_f542_a_rollback_etsy_accepted_but_did_not_apply_is_not_recorded_restored",
                   "tests/test_etsy_readback_observe.py::test_a_write_etsy_silently_changed_is_caught_by_read_back_and_halts_the_product",
                   "tests/test_etsy_transport.py::test_a_write_the_server_ignored_returns_200_and_fails_read_back"],
    },
    ("s9", "F-878"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/launch/packet.py::build",
        "consumer": "src/brambleloop/app/command_center/launch_packet.py (GET /api/cc/launch/packet, "
                    "owner session); scripts/launch_packet.py",
        "next_action": "none in code -- reading /api/cc/launch/packet with the owner credential "
                       "in production remains a confirmation the owner can make",
        "evidence+": [f"{TAG}: {EV5}/launch_packet_b931d17a738d_20261020T053641Z.json -- generated "
                      "by the deployed tree's scripts/launch_packet.py (clean worktree of "
                      "b931d17, scratch DB, shadow): candidate SHA, recorded_suite PASS bound to "
                      "release/RELEASE_324927f1... by tree digest + ancestor, the closure "
                      "summary, per-product visual/parity, listing, policy, search, rollback and "
                      "economics sections, owner queue, spend limits, rollback path and "
                      "activation steps; verdict UNKNOWN on a scratch DB, as it must be"],
        "tests+": ["tests/test_fb4_launch.py::test_launch_packet_on_a_fresh_shadow_db_with_launch0_certified_is_honest",
                   "tests/test_fb4_launch.py::test_launch_packet_script_writes_json_and_markdown",
                   "tests/test_w4_packetrel.py::test_record_only_commit_cites_its_release_record_by_tree_digest",
                   "tests/test_w4_packetrel.py::test_a_tampered_or_ineligible_record_is_fail_with_its_problems"],
    },
})


# ---- batch 4: W4-SWARMCONTROL / W4-SWARMMETRICS / W4-MJSCOUNT rows (deployed in b931d17).
# swarm/metrics.py is edited on this branch (the /api/departments 500 fix), so F-487, F-655 and
# F-730 are dev-proven, awaiting deploy; F-192's display is in app/main.py (also edited). -------
SC = "tests/test_w4_swarmcontrol.py::"
SM = "tests/test_w4_swarmmetrics.py::"
MJ = "tests/test_w4_mjscount.py::"
R4 = "tests/test_w4_close5_rows4.py::"
SWARM_TS = "20261020T0540Z"
FM_EDITS.update({
    ("s6", "F-473"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/swarm/preempt.py::preemption_wanted",
        "consumer": "src/brambleloop/runtime/worker.py (JobContext.should_yield / yield_now; "
                    "Worker.run_once requeues a preempted job)",
        "durable_state": "job_checkpoints; jobs",
        "next_action": "none -- W4-SWARMCONTROL built it; deployed in b931d17",
        "evidence+": [f"{TAG}: preemption is wanted only when the pool is full, a strictly "
                      "better band or protected tier is waiting and has waited >= 120 s; a "
                      "yielding handler checkpoints, is requeued PENDING with its attempt "
                      "uncounted and audited job.preempted; intel.gallery_analysis yields "
                      f"between images; {DT}", REACH],
        "tests+": [SC + "test_preemption_wanted_only_behind_a_full_pool_for_better_waiting_work",
                   SC + "test_a_yielding_handler_is_requeued_uncounted_with_its_checkpoint",
                   SC + "test_gallery_analysis_yields_between_images"],
    },
    ("s3", "F-191"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/intel/mission.py::snapshot",
        "next_action": "none -- W4-MJSCOUNT built it; deployed in b931d17",
        "evidence+": [f"{TAG}: every MJs counter derives from one BenchmarkListing read "
                      "(known, audited, gallery-audited, by pod, image slots, gap total) with a "
                      "reconciliation row of five identities; a broken identity is reported, "
                      f"never corrected; the backlog no longer saturates at 200; {DT}"],
        "tests+": [MJ + "test_every_counter_comes_from_one_snapshot_and_reconciles",
                   MJ + "test_the_backlog_count_no_longer_saturates_at_a_page",
                   MJ + "test_a_broken_identity_is_reported_not_corrected"],
    },
    ("s3", "F-193"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/intel/vision.py::forecast",
        "consumer": "src/brambleloop/app/main.py::dashboard (_mission row)",
        "next_action": "none -- W4-MJSCOUNT built it; deployed in b931d17",
        "evidence+": [f"{TAG}: measured CA$/image (gallery_observation cost rows / images "
                      "judged; UNKNOWN when either is zero, never 0), remaining images, cost to "
                      "drain, allocation share/spent/allowed, images per run, runs per day and the "
                      f"ETA, shown together on the mission row; {DT}"],
        "tests+": [MJ + "test_forecast_is_measured_or_unknown_never_zero",
                   MJ + "test_dashboard_mission_shows_scan_health_detail_reconciliation_and_forecast"],
    },
    ("s3", "F-192"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/app/main.py::_mission (scan_health state + problem + "
                    "checked_at)",
        "next_action": "none in code -- dev-proven on claude/w4-CLOSE5 (main.py edited by R1), "
                       "awaiting deploy",
        "evidence+": ["w4-CLOSE5: the mission row shows the scan-health state with the "
                      "dimension that is unverified (its problem text) and the check time, or "
                      "'never checked' (W4-MJSCOUNT, deployed in b931d17; the module is edited "
                      "on this branch, so dev-proven)"],
        "tests+": [MJ + "test_dashboard_mission_shows_scan_health_detail_reconciliation_and_forecast"],
    },
    ("s6", "F-487"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/swarm/metrics.py::agents_view",
        "consumer": "src/brambleloop/app/main.py::api_departments (GET /api/departments)",
        "next_action": "none in code -- dev-proven on claude/w4-CLOSE5, awaiting deploy (fixes the "
                       "production 500)",
        "evidence+": [f"w4-CLOSE5: production b931d17 serves GET /api/departments as HTTP 500 "
                      f"({EVB}/prod_api_departments_{SWARM_TS}.json): agents_view indexed "
                      "parked[t]['why'] and a backoff entry has no 'why'. Fixed (_parked_why) and "
                      "the view now carries each agent's last output (newest finished job) -- the "
                      "'output/evidence' clause; tests execute the route against a backoff"],
        "tests+": [R4 + "test_f487_departments_route_serves_a_backed_off_job_type_instead_of_a_500",
                   R4 + "test_f487_every_clause_is_on_each_department_row",
                   SM + "test_agents_view_composes_running_pending_parked_completion_and_spend"],
    },
    ("s8", "F-655"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/swarm/metrics.py::starved_ready",
        "consumer": "src/brambleloop/ops/health.py (starved_ready signal); GET /api/swarm/runtime",
        "next_action": "none in code -- dev-proven (swarm/metrics.py edited on this branch); the "
                       "production reading already holds",
        "evidence+": [f"w4-CLOSE5: production b931d17 {EVB}/prod_api_swarm_runtime_{SWARM_TS}.json "
                      "starved_ready: reading ok, starved 0, late_ready 0, capacity_idle true -- "
                      "'no READY work is past its band SLA'; the ops/health signal is DEGRADED "
                      "when starved"],
        "tests+": [SM + "test_late_ready_work_with_idle_capacity_is_starved",
                   SM + "test_health_reports_starved_ready_as_a_signal"],
    },
    ("s8", "F-730"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/swarm/metrics.py::untouched_opportunities",
        "consumer": "GET /api/swarm/runtime; src/brambleloop/swarm/orchestrate.py::feed_idle",
        "next_action": "none in code -- dev-proven (swarm/metrics.py edited on this branch); the "
                       "production reading already holds",
        "evidence+": [f"w4-CLOSE5: production b931d17 {EVB}/prod_api_swarm_runtime_{SWARM_TS}.json "
                      "untouched_opportunities: reading ok, untouched 0 of 20 discovered gaps "
                      "after 7 days, 'every discovered gap was acted on within the window'; idle "
                      "feeding spends nothing (existing evidence)"],
        "tests+": [SM + "test_untouched_opportunities_are_counted_and_value_weighted"],
    },
})


# ---- batch 5: rows whose code is deployed and whose remaining gap was a test, a consumer
# name or a maturity claim the stale reachability capped ------------------------------------
R5 = "tests/test_w4_close5_rows5.py::"
ES = "tests/test_etsy_surfaces.py::"
EU = "tests/test_w4_etsysurf.py::"
FM_EDITS.update({
    ("s6", "F-491"): {
        "consumer": "src/brambleloop/runtime/worker.py::Worker.run_once (fails only the job "
                    "that raised; JobQueue.fail fenced to its lease)",
        "next_action": "none -- deployed; isolation now asserted around the failing job",
        "evidence+": [f"{TAG}: a dead-lettered job leaves an already-completed job's status, "
                      "outputs, finish time and audit rows untouched, and independent work "
                      f"queued beside it completes; {DT}"],
        "tests+": [R5 + "test_f491_a_dead_letter_neither_rolls_back_nor_blocks_independent_work"],
    },
    ("s7", "F-586"): {
        "maturity": "INTEGRATED",
        "consumer": "src/brambleloop/app/main.py::api_etsy_surfaces (GET /api/etsy/surfaces); "
                    "launch.readiness.etsy_first_sale_surfaces",
        "next_action": "none -- the registry is reached at runtime on b931d17",
        "evidence+": [f"{TAG}: delivery_settings is recorded NOT_APPLICABLE with its reason in "
                      "words and its thirteen shipping-profile operations named, never "
                      "UNSUPPORTED and never a silent gap; intel/etsy_surfaces.py is reached on "
                      f"b931d17 (GET /api/etsy/surfaces, readiness); {DT}", REACH],
        "tests+": [ES + "test_unsupported_and_not_applicable_are_never_the_same_verdict",
                   EU + "test_surfaces_api_exposes_coverage_work_plan_and_the_launch_list"],
    },
    ("s7", "F-591"): {
        "maturity": "INTEGRATED",
        "consumer": "src/brambleloop/commerce/sales_channels.py::inventory (orders_ingest "
                    "receipt_type: a Pattern sale is its own channel, unreadied -> incident); "
                    "GET /api/etsy/surfaces",
        "next_action": "none -- deployed",
        "evidence+": [f"{TAG}: sales_channels is a separate registry decision (NOT_APPLICABLE "
                      "with its reason: no Pattern subscription); a Pattern sale is recorded as "
                      "its own channel with its own listing/inventory/payment/customer-data/"
                      "attribution effects and opens an incident until readied -- nothing "
                      f"about it is assumed from etsy.com; {DT}"],
        "tests+": [ES + "test_the_registry_passes_its_own_invariants",
                   "tests/test_w4_fmclose_etsy.py::test_f590_inventory_names_effects_and_an_unreadied_channel_is_an_incident"],
    },
    ("s9", "F-793"): {
        "maturity": "INTEGRATED",
        "consumer": "src/brambleloop/gates/certificate.py::certify (calls "
                    "specification.refuse_a_benchmark_in_our_clothes)",
        "next_action": "none -- reached at runtime through certification",
        "evidence+": [f"{TAG}: the two-tier identifying match lets standard construction "
                      "through (a plain rectangle of a benchmark's sleeve width is not a match; "
                      "no genuine Brambleloop design is a false positive) and refuses a "
                      "benchmark's identifying piece; cir/specification.py is reached on b931d17 "
                      f"via certification; {DT}", REACH],
        "tests+": ["tests/test_specification.py::test_any_one_identifying_benchmark_piece_is_refused_on_its_own"],
    },
    ("s6", "F-498"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/launch/readiness.py::etsy_first_sale_surfaces; "
                    "intel/etsy_surfaces.py::first_sale_blockers",
        "consumer": "src/brambleloop/launch/readiness.py::assess",
        "next_action": "none -- W4-ETSYSURF built it; deployed in b931d17",
        "evidence+": [f"{TAG}: launch readiness carries the bounded first-sale list (11 surfaces, "
                      "each FRESH / STALE / NO_EVIDENCE / NO_COLLECTOR from its collector's last "
                      "reading) and is ready only when every one is FRESH and every shop check "
                      "passes; the requirement is never 'build', so it cannot grow the build "
                      f"queue; {DT}", REACH],
        "tests+": [EU + "test_an_unobserved_shop_lists_every_first_sale_surface_and_waits_on_the_owner",
                   EU + "test_a_fresh_passing_shop_still_names_what_no_collector_can_observe",
                   EU + "test_the_requirement_is_part_of_readiness_and_never_blocks_on_build"],
    },
})


# ---- batch 6: Command Center / growth / search rows built by W4-CCFM1, W4-CCGROW, W4-CCALL
# and W4-SIZEINTENT (all deployed in b931d17) -------------------------------------------------
C1 = "tests/test_w4_ccfm1.py::"
CG = "tests/test_w4_ccgrow.py::"
SZ = "tests/test_w4_size_shape_intent.py::"
FM_EDITS.update({
    ("s7", "F-619"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/app/command_center/tabs.py::WORKSPACES",
        "consumer": "the Command Center app (/cc/, owner session): every named area is a route "
                    "with a view module, reading an /api/cc/* endpoint",
        "next_action": "none -- W4-CCFM1 built it; deployed in b931d17",
        "evidence+": [f"{TAG}: Today, Month, Finance, Products, Listings, Marketing, Customers, "
                      "Experiments, Departments, Agent Activity, Owner Actions and System Health "
                      "each map to a Command Center route whose view file exists and to an API "
                      "the app serves; the stores stay the source of truth (no new store); "
                      f"{DT}"],
        "tests+": [C1 + "test_every_named_owner_area_has_a_route_and_an_api"],
    },
    ("s8", "F-651"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/app/command_center/tabs.py::WORKSPACES",
        "consumer": "the Command Center app (/cc/)",
        "next_action": "none -- W4-CCFM1 built it; deployed in b931d17",
        "evidence+": [f"{TAG}: the Command Center is the one app holding Command Center, "
                      "Products, Visual (/cc/image-review), Etsy, Marketing, Finance, Customers, "
                      "QA, Research, Reliability, Agents and Owner Inbox, each a served route; "
                      f"{DT}"],
        "tests+": [C1 + "test_every_named_owner_area_has_a_route_and_an_api"],
    },
    ("s6", "F-504"): {
        "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/growth/experiments.py::attribution; "
                    "growth/experiments.py::persist",
        "consumer": "src/brambleloop/growth/experiments.py::conclude_all (writes measured_effect "
                    "and retain_or_rollback); GET /api/experiments",
        "next_action": "none -- W4-CCGROW built it; deployed in b931d17",
        "evidence+": [f"{TAG}: a registered experiment records what changed (design), why "
                      "(hypothesis), owner/department, expected effect (pre-registered lines), "
                      "and now the measured effect against expectation (UNMEASURED with no "
                      "reading) and the retain/rollback decision (retain only on a causal, "
                      f"claimable success; association stays undecided); {DT}"],
        "tests+": [CG + "test_attribution_retains_only_a_causal_success",
                   CG + "test_api_experiments_reports_effect_decision_and_superseded"],
    },
    ("s8", "F-660"): {
        "coverage": "FULL", "missing_part": None,
        "next_action": "none -- verified locally by W4-CCALL; deployed in b931d17",
        "evidence+": [f"{TAG}: with the credit wallet empty and cloud/provider credential "
                      "variables unset, three agents work concurrently through the runtime "
                      "dispatch path, which never reads the credit wallet -- cloud sessions are "
                      f"burst capacity, not a dependency; {DT}"],
        "tests+": ["tests/test_w4_f660_zero_credit.py::test_three_agents_work_concurrently_with_zero_cloud_credit",
                   "tests/test_w4_f660_zero_credit.py::test_the_dispatch_path_does_not_read_the_credit_wallet"],
    },
    ("s1", "F-056"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/commerce/search.py::shape_of; "
                    "commerce/search.py::build_query_set",
        "next_action": "none -- W4-SIZEINTENT built it; deployed in b931d17",
        "evidence+": [f"{TAG}: a measured shape (hexagon/round from the twin) and a graded size "
                      "count add shape and multi-size query families, labelled assumed; no size "
                      "class word is generated; a shape word that contradicts the twin is refused "
                      f"(TAG_SHAPE_UNTRUE); listing.seo passes both; {DT}"],
        "tests+": [SZ + "test_the_shape_is_read_from_the_twin",
                   SZ + "test_the_family_adds_shape_and_graded_size_phrases_only",
                   SZ + "test_a_shape_word_that_contradicts_the_twin_is_refused"],
    },
})
BATCH6 = ("F-619", "F-651", "F-504", "F-660", "F-056")


# ---- batch 6b: F-871 (W4-FUNDING), closed on the production readback the lane named --------
FU = "tests/test_w4_funding.py::"
FM_EDITS.update({
    ("s9", "F-871"): {
        "coverage": "FULL", "missing_part": None,
        "gate": {"kind": "none", "key": None,
                 "detail": "model_provider OPEN in production b931d17; funding itself stays the "
                           "owner's act (setting credit), which the packet prepares"},
        "producer": "src/brambleloop/finance/funding_packet.py::credit_packet; "
                    "src/brambleloop/ops/funding.py",
        "consumer": "GET /api/funding/packets; the owner's 'add credit' action carries the "
                    "packet (ops/funding.note)",
        "next_action": "none -- W4-FUNDING built it; production serves the packet on b931d17",
        "evidence+": [f"{TAG}: {EVB}/prod_api_funding_packets_20261020T0612Z.json -- production "
                      "b931d17 serves the model-credit packet for anthropic: the bounded "
                      "experiment (30-day spend by purpose), max spend (CA$100 monthly ceiling, "
                      "spent CA$64.72, headroom CA$35.28, enforced before every call), the "
                      "measured run rate and outage evidence, approves_itself false; "
                      f"{DT}"],
        "tests+": [FU + "test_the_credit_packet_names_what_the_credit_buys_and_its_bound",
                   FU + "test_the_owner_funding_action_carries_the_prepared_packet",
                   FU + "test_an_empty_ledger_is_unmeasured_never_zero",
                   FU + "test_the_packets_route_is_registered"],
    },
})
BATCH6B = ("F-871",)


# ---- batch 6c: F-240 (built by FB-4, brand/seller_identity.py; deployed) -- the mapping still
# said MISSING ---------------------------------------------------------------------------------
SF = "tests/test_storefront_fb4.py::"
FM_EDITS.update({
    ("s4", "F-240"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/brand/seller_identity.py::check_identity; "
                    "brand/seller_identity.py::compare",
        "consumer": "src/brambleloop/brand/storefront.py::check_storefront (launch.plan -> "
                    "ranking_readiness.shop_quality); launch/readiness.py seller_identity item",
        "durable_state": None,
        "gate": {"kind": "none", "key": None,
                 "detail": "the rule is enforced in code; the account holder's KYC entry of the "
                           "legal values is an owner readiness item (seller_identity), not a gap "
                           "in this row"},
        "next_action": "none in code -- the legal values stay UNKNOWN until the owner confirms "
                       "them at Etsy KYC; readiness blocks until then",
        "evidence+": [f"{TAG}: the mapping's 'nothing models public vs legal identity' is stale: "
                      "brand/seller_identity.py (FB-4) keeps the public and legal presentations "
                      "side by side; every legal value is UNKNOWN until owner-confirmed at KYC and "
                      "is never invented; a difference is PERMITTED only when it cites an Etsy "
                      "rule actually on file in gates.policy_knowledge, otherwise "
                      "IDENTITY_DIFFERENCE_UNSOURCED / IDENTITY_RULE_NOT_ON_FILE; a storefront "
                      "whose shop name drifted from the record is IDENTITY_STALE; reached on "
                      f"b931d17 via launch.plan; {DT}", REACH],
        "tests+": [SF + "test_legal_identity_is_unknown_and_never_invented",
                   SF + "test_an_unsourced_difference_is_refused_and_a_cited_one_must_be_on_file",
                   SF + "test_the_storefront_check_refuses_a_stale_identity"],
    },
})
BATCH6C = ("F-240",)


# ---- batch 7: F-019 (built, deployed; the mapping still said MISSING) and F-046 (no guard
# existed; the guard is a test over deployed code, which needed no change) -----------------
R6 = "tests/test_w4_close5_rows6.py::"
FM_EDITS.update({
    ("s1", "F-019"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/commerce/search.py::_acceptable_tag; "
                    "commerce/search.py::intent_key (_stem_word); "
                    "commerce/search.py::tag_diversity_problems",
        "consumer": "runtime/release.py::handle_listing_seo (choose_tags; "
                    "tag_diversity_problems blocks the release); seo/packages.py; "
                    "seo/proposals.py",
        "durable_state": "listings.tags (the chosen thirteen) + the release gate's findings",
        "gate": {"kind": "none", "key": None, "detail": "software only; nothing external"},
        "next_action": "none -- built and deployed; now asserted",
        "evidence+": [f"{TAG}: the mapping's 'no singular/plural root detection' is stale: "
                      "commerce/search.intent_key folds plurals (_stem_word: -s, -ies->y, never "
                      "-ss), word order and synonyms; _acceptable_tag refuses a phrase whose "
                      "folded key a chosen tag already carries (in both the must-include and "
                      "value passes); a surviving pair is a blocking TAG_SEMANTIC_DUPLICATE in "
                      f"the release gate; reached via listing.seo on b931d17; {DT}", REACH],
        "tests+": [R6 + "test_f019_plural_and_singular_fold_to_one_root_and_ss_is_not_a_plural",
                   R6 + "test_f019_tag_selection_never_spends_two_slots_on_one_root",
                   R6 + "test_f019_a_surviving_plural_pair_blocks_in_the_release_gate"],
    },
    ("s1", "F-046"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/commerce/ranking_readiness.py::profile; "
                    "commerce/search.py::Query.value",
        "consumer": "runtime/release.py::handle_launch_plan (ranking_readiness.profile); "
                    "launch/demand.py organic_readiness (kept beside, never merged with, the "
                    "ads plan)",
        "durable_state": None,
        "gate": {"kind": "none", "key": None,
                 "detail": "Etsy Ads stay disabled until owner authority (F-875); this row is "
                           "the organic model's independence from them, which needs no authority"},
        "next_action": "none -- the guard is a test over deployed code",
        "evidence+": [f"{TAG}: AST scan of the organic ranking modules (commerce/search.py, "
                      "commerce/seo.py, commerce/ranking_readiness.py, seo/*.py) finds no "
                      "import of paid_media/ads_readiness/insights_budget/channel_comparison, "
                      "no Etsy Ads/Offsite Ads/Etsy Plus/ROAS name or string, and no use of "
                      "search_policy's ads thresholds (the scan is self-checked against a "
                      "planted line); recording CA$353 of ads, offsite-ads and Etsy Plus cost "
                      "leaves every ranking dimension, the search certificate and the summary "
                      f"identical; Query.value is demand x (1 - competition) only; {DT}",
                      REACH],
        "tests+": [R6 + "test_f046_no_organic_ranking_module_reads_a_paid_media_input",
                   R6 + "test_f046_ad_and_etsy_plus_spend_leave_every_ranking_dimension_unchanged",
                   "tests/test_ranking_readiness.py::test_an_empty_shop_is_unmeasured_not_passed_and_never_blended"],
    },
})
BATCH7 = ("F-019", "F-046")


# ==== W4-CLOSE6 (branch claude/w4-CLOSE6 from ee244a1) ==========================================
TAG6 = "w4-CLOSE6 on deployed b931d17"
EV6 = "research/final_build/w4/evidence_CLOSE6"
DEPLOYED_TESTS6 = f"{EV6}/deployed_tree_tests_b931d17.json"
DT6 = f"deployed-tree run {DEPLOYED_TESTS6}"
AD6 = "tests/test_w4_close6_ads.py::"
OA6 = f"{EV6}/prod_api_owner_actions_ads_20261020T1119Z.json"

# ---- CLOSE6 batch 1: Etsy Ads eligibility, recheck and Ads-credit accounting -----------------
FM_EDITS.update({
    ("s8", "F-685"): {
        "maturity": "DEPLOYED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/growth/ads_readiness.py::tick; "
                    "growth/ads_readiness.py::locked_row (MarketplaceCapability row)",
        "consumer": "growth/ads_readiness.py::_eligibility_gate (listing_readiness); "
                    "launch/visibility.py etsy_ads; Command Center ads provider",
        "durable_state": "marketplace_capabilities (key etsy_ads: status, eligible_from, "
                         "last_verified_at, evidence_source, detail.date_is_estimate)",
        "gate": {"kind": "none", "key": None, "detail": "software only"},
        "next_action": "none -- deployed; the owner's reading is recorded through F-686's route",
        "evidence+": [f"{TAG6}: the mapping's 'no persisted etsy_ads_status...' is stale: "
                      "growth/ads_readiness.py persists all four fields in "
                      "marketplace_capabilities; the reported 2026-09-25 countdown is seeded as "
                      "WAITING_REPORTED with date_is_estimate true and never gates as eligible; "
                      f"production b931d17 ran the hourly recheck ({OA6}: OwnerAction #32 "
                      "raised for etsy_ads_eligibility_evidence when the countdown came due, "
                      f"status RECHECK_REQUIRED, not ELIGIBLE); {DT6}", REACH],
        "tests+": [AD6 + "test_f685_the_four_fields_are_persisted_and_the_reported_date_is_not_authoritative",
                   "tests/test_v11_ads_readiness.py::test_countdown_never_grants_eligibility_and_dedupes_owner_action",
                   "tests/test_v11_ads_readiness.py::test_eligibility_evidence_expires_and_is_not_authority"],
    },
    ("s8", "F-686"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/growth/ads_readiness.py::tick; "
                    "src/brambleloop/app/main.py::api_ads_eligibility "
                    "(growth/ads_readiness.py::record_evidence)",
        "consumer": "OwnerAction etsy_ads_eligibility_evidence (closed SATISFIED by the "
                    "recorded reading); growth/ads_readiness.py::_eligibility_gate",
        "durable_state": "marketplace_capabilities.detail.evidence_history; owner_actions",
        "gate": {"kind": "none", "key": None,
                 "detail": "no Etsy API exposes Ads eligibility; the reading is the owner's, "
                           "requested automatically and now recordable"},
        "next_action": "deploy W4-CLOSE6 (POST /api/ads/eligibility); then the owner records "
                       "the reading OwnerAction #32 asks for",
        "evidence+": [f"{TAG6}: the recheck half was deployed (hourly marketing.ads_readiness; "
                      f"production raised OwnerAction #32 at the due countdown, {OA6}), but the "
                      "re-verification could never complete: record_evidence had no caller, so "
                      "the owner action was unsatisfiable. W4-CLOSE6 adds the authenticated "
                      "POST /api/ads/eligibility; a stale, future or date-less WAITING reading "
                      "is refused, the reading closes the recheck action, the next due countdown "
                      "asks again, and ELIGIBLE comes only from a reading and authorises no "
                      "spend. Dev-proven, awaiting deploy."],
        "tests+": [AD6 + "test_f686_the_countdown_reaching_zero_raises_a_recheck_and_never_eligible",
                   AD6 + "test_f686_the_owner_reading_completes_the_recheck_through_the_route"],
    },
    ("s8", "F-688"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/finance/credits.py::ads_credit; "
                    "finance/credits.py::record_ads_credit_cycle; "
                    "src/brambleloop/app/main.py::api_ads_credit",
        "consumer": "finance/credits.py::wallet -> finance/spend_report.py::governance "
                    "(dashboard spend governance)",
        "durable_state": "ads_credit_cycles (cycle_start/end, entitlement_usd, displayed_cad, "
                         "used_displayed_cad NULL=UNKNOWN, source, evidence_ref)",
        "gate": {"kind": "none", "key": None,
                 "detail": "software only; the figures are the owner's reading of Shop Manager"},
        "next_action": "deploy W4-CLOSE6; the owner records each cycle as Etsy shows it",
        "evidence+": [f"{TAG6}: finance/credits.ads_credit records per cycle the official "
                      "entitlement (USD), the CAD value Shop Manager displays (beside, never "
                      "replaced by, this system's labelled conversion), the cycle dates, credit "
                      "used (Etsy-reported; UNKNOWN when absent, never 0), expired credit, "
                      "recorded ad spend and the incremental cash beyond the credit; "
                      "ceilings_changed 0 and the ads SpendLimit is untouched. Dev-proven, "
                      "awaiting deploy."],
        "tests+": [AD6 + "test_f688_a_cycle_records_entitlement_displayed_value_use_expiry_and_cash",
                   AD6 + "test_f688_the_route_records_a_cycle_and_the_spend_report_carries_it"],
    },
})
C6_BATCH1_PROD = ("F-685",)
C6_CLOSED: set[str] = set(C6_BATCH1_PROD)


# ---- CLOSE6 batch 2: F-664 Ask Brambleloop, F-666 Overnight Brief (dev-proven) --------------
AK6 = "tests/test_w4_close6_ask.py::"
BR6 = "tests/test_w4_close6_brief.py::"
FM_EDITS.update({
    ("s8", "F-664"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/app/command_center/ask.py::ask (spend_q, agents_q, "
                    "opportunities_q added; overnight, profit, launch_blocked, product_blocked, "
                    "approval_reason, incidents_q existing)",
        "consumer": "POST /api/cc/ask (app/command_center/api.py) -> the Command Center Ask "
                    "view (static/js/views/ask.js)",
        "durable_state": None,
        "gate": {"kind": "none", "key": None, "detail": "software only"},
        "next_action": "deploy W4-CLOSE6",
        "evidence+": [f"{TAG6}: the mapping's 'no command/search bar' is stale: v1.1 F-928/F-929 "
                      "built Ask Company (deterministic retrieval, every fact citing its row; "
                      "UNKNOWN rather than invention) and its Command Center view. It answered "
                      "what changed, profit/revenue and what blocks launch; W4-CLOSE6 adds the "
                      "three named intents it lacked -- what agents are doing (swarm.metrics."
                      "agents_view), spend (finance.spend_report.what_it_bought, cost_entries) "
                      "and opportunities (entered mjs_mission_events + undecided improvements). "
                      "Dev-proven, awaiting deploy."],
        "tests+": [AK6 + "test_every_named_question_routes_to_a_reader",
                   AK6 + "test_spend_agents_and_opportunities_are_answered_from_cited_rows",
                   AK6 + "test_an_empty_company_answers_nothing_recorded_never_an_invention",
                   AK6 + "test_the_surface_is_the_command_center_bar",
                   "tests/test_v11_cc_views.py::test_ask_answers_unknown_rather_than_inventing"],
    },
    ("s8", "F-666"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/app/command_center/brief.py::morning_sections; "
                    "app/command_center/tabs.py::morning_brief",
        "consumer": "GET /api/cc/brief/morning -> HOME 'Overnight handoff' card "
                    "(static/js/views/home.js BRIEF_ORDER)",
        "durable_state": None,
        "gate": {"kind": "none", "key": None, "detail": "software only"},
        "next_action": "deploy W4-CLOSE6",
        "evidence+": [f"{TAG6}: the F-896 overnight handoff already carried what changed, "
                      "completed tasks, money spent by kind (compute vs ads), incidents, "
                      "discoveries, queue and decisions; W4-CLOSE6 adds autonomous hours, "
                      "experiments, products advanced/rejected, image candidates, Etsy findings "
                      "and sales/profit (UNMEASURED, never CA$0), each from its own rows, an "
                      "unreadable source UNKNOWN. Dev-proven, awaiting deploy."],
        "tests+": [BR6 + "test_every_named_item_is_a_section_read_from_its_rows",
                   BR6 + "test_unmeasured_sales_are_never_zero_and_an_unreadable_source_is_unknown",
                   BR6 + "test_the_overnight_handoff_on_home_carries_every_named_item"],
    },
})


# ---- CLOSE6 batch 3: F-144 Production Readback Gate (dev-proven) ----------------------------
RB6 = "tests/test_w4_close6_readback.py::"
FM_EDITS.update({
    ("s2", "F-144"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/ops/smoke.py::smoke_matrix (GET /api/verify/smoke); "
                    "ops/readback.py::run (per-feature MANIFEST: endpoint, field, predicate, rows)",
        "consumer": "ops/deploy.sh (exit 5 when a feature does not read back; writes the "
                    "readback evidence); research/final_build/w4/completion_board_final.py::"
                    "apply_readback (a row a feature names is not verified_complete unless the "
                    "deployed commit's readback passed)",
        "durable_state": "research/final_build/w4/evidence_BOARD/prod_readback_<sha12>_<ts>.json",
        "gate": {"kind": "none", "key": None, "detail": "software only"},
        "next_action": "deploy the next release with ops/deploy.sh; the row is held until that "
                       "commit's readback passes (b931d17 reads FAIL: dead letters, "
                       "/api/departments 500 -- both fixed on the branch)",
        "evidence+": [f"{TAG6}: W4-SMOKE built the gate (ops/readback.py, ops/deploy.sh exit 5, "
                      "ops/smoke.py at /api/verify/smoke); W4-CLOSE6 added the features "
                      "production failed without any readback noticing (GET /api/departments "
                      "500 on b931d17; swarm runtime, funding packet, off-site archive, "
                      "continuity proof, Etsy credential), persisted every deploy's readback as "
                      "evidence, and made the completion board refuse 'done' to a row whose "
                      "feature does not read back on the deployed commit (missing readback = "
                      "UNKNOWN, held). Read-only readback of b931d17 on file: FAIL on 'no "
                      "unexpected dead letters' and 'department health served'. Dev-proven."],
        "tests+": [RB6 + "test_the_manifest_reads_back_the_features_that_failed_unseen",
                   RB6 + "test_a_row_is_not_complete_unless_its_deployed_readback_passed",
                   RB6 + "test_deploy_writes_the_readback_where_the_board_reads_it",
                   RB6 + "test_the_committed_board_applies_the_deployed_readback",
                   "tests/test_w4_smoke.py::test_deploy_sh_exits_5_when_a_feature_does_not_read_back_and_0_when_all_do"],
    },
})


# ---- CLOSE6 batch 4: F-834 consumer receipts, F-662 causal timeline (dev-proven) -------------
PR6 = "tests/test_w4_close6_proof.py::"
TL6 = "tests/test_w4_close6_timeline.py::"
FM_EDITS.update({
    ("s9", "F-834"): {
        "maturity": "TESTED", "coverage": "FULL", "missing_part": None,
        "producer": "scripts/shadow_rehearsal.py::record_edges -> "
                    "scripts/emit_runtime_packets.py::consumer_chain; "
                    "src/brambleloop/build2/final_proof.py::validate",
        "consumer": "src/brambleloop/build2/final_proof.py::validate (refuses a row without "
                    "bound durable_state/consumer/decision/effect/result receipts naming the "
                    "row's own consumer) -> the integrator's release proof",
        "durable_state": "research/final_build/w4/evidence_CLOSE6/shadow_rehearsal_8e4efd3.json "
                         "(chain_edges), runtime_packets_8e4efd3.json, final_proof_8e4efd3.json",
        "gate": {"kind": "none", "key": None,
                 "detail": "the independent review on each packet is the reviewer's, never the "
                           "emitter's (final_proof refuses self-review)"},
        "next_action": "integrator: accept the structural TESTED target proposed in "
                       "w4/OVERRIDES_PROPOSED_CLOSE6.json (producer is a script + the offline "
                       "adjudicator final_proof.py, so INTEGRATED is unreachable by "
                       "construction, as for F-846); per row, an independent reviewer and "
                       "production-producer / failure-test receipts",
        "evidence+": [f"{TAG6}: the consumer is now proven at runtime, not asserted: the shadow "
                      "rehearsal records, from the rows the run wrote, the durable row each "
                      "producer job wrote and that the store.publish job read it (its release "
                      "gates name the same version; its key the same certified release), what "
                      "it decided (refused in SHADOW), the effect row (store.publish_refused) "
                      "and the result (no store.published; no Etsy id); the emitter turns that "
                      "edge into chain receipts only for rows whose producer AND named consumer "
                      "are the edge's handlers. final_proof on the recorded run: the chain "
                      "errors are gone for those rows; they stay BLOCKED on independent review "
                      "(and production-producer / failure-test receipts). Dev-proven."],
        "tests+": [PR6 + "test_a_recorded_edge_gives_every_chain_stage_a_bound_receipt",
                   PR6 + "test_an_unbound_read_claims_nothing_past_the_producer",
                   PR6 + "test_the_recorded_rehearsal_binds_the_edge_on_this_head",
                   "tests/test_final_proof.py::test_each_missing_chain_stage_blocks",
                   "tests/test_final_proof.py::test_disabling_the_consumer_reopens_the_proof"],
    },
    ("s8", "F-662"): {
        "maturity": "INTEGRATED", "coverage": "FULL", "missing_part": None,
        "producer": "src/brambleloop/runtime/lineage.py::record (JobContext.enqueue); "
                    "src/brambleloop/app/command_center/causal.py::stories",
        "consumer": "GET /api/cc/timeline (command_center/tabs.py::timeline 'stories') -> the "
                    "Timeline view (static/js/views/timeline.js 'What the company did')",
        "durable_state": "job_links (parent_id, child_id) + jobs",
        "gate": {"kind": "none", "key": None, "detail": "software only"},
        "next_action": "deploy W4-CLOSE6",
        "evidence+": [f"{TAG6}: the timeline listed audit rows and company events with no cause "
                      "and effect. Every follow-on job now records the job that caused it "
                      "(best effort, never blocking the enqueue); the timeline tells each chain "
                      "as one story across departments in words (who did what, the outcome, "
                      "what caused the first step: scheduled / caused by / 'cause not recorded', "
                      "never guessed) and counts routine checks that caused nothing instead of "
                      "listing them. Dev-proven."],
        "tests+": [TL6 + "test_a_pipeline_run_is_one_causal_story_across_departments",
                   TL6 + "test_an_unrecorded_cause_is_shown_as_such_and_never_blocks_the_work",
                   TL6 + "test_the_timeline_serves_the_stories"],
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
    **{u: [DEPLOYED_TESTS, f"{EV5}/module_reachability_b931d17.json"]
       for u in ("F-378", "F-427", "F-428", "F-706", "F-403", "F-409", "F-424", "F-433",
                 "F-399", "F-605")},
    "F-535": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS],
    "F-542": [f"{EVB}/prod_api_build_{TS}.json", DEPLOYED_TESTS],
    "F-878": [f"{EV5}/launch_packet_b931d17a738d_20261020T053641Z.json", DEPLOYED_TESTS],
    "F-473": [DEPLOYED_TESTS, f"{EV5}/module_reachability_b931d17.json"],
    "F-191": [DEPLOYED_TESTS],
    "F-193": [DEPLOYED_TESTS],
    **{u: [DEPLOYED_TESTS, f"{EV5}/module_reachability_b931d17.json"]
       for u in ("F-491", "F-586", "F-591", "F-793", "F-498")},
    **{u: [DEPLOYED_TESTS, f"{EV5}/module_reachability_b931d17.json"]
       for u in BATCH6},
    "F-871": [f"{EVB}/prod_api_funding_packets_20261020T0612Z.json", DEPLOYED_TESTS],
    **{u: [DEPLOYED_TESTS, f"{EV5}/module_reachability_b931d17.json"]
       for u in BATCH6C},
    **{u: [DEPLOYED_TESTS, f"{EV5}/module_reachability_b931d17.json"]
       for u in BATCH7},
    **{u: [DEPLOYED_TESTS6, OA6, f"{EV5}/module_reachability_b931d17.json"]
       for u in C6_BATCH1_PROD},
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
    **{u: "W4 lane tests for the row pass on the deployed tree; module reached on b931d17"
       for u in ("F-378", "F-427", "F-428", "F-706", "F-403", "F-409", "F-424", "F-433",
                 "F-399", "F-605")},
    "F-535": "root-cause tests pass on the deployed tree; transactions_r OPEN",
    "F-542": "read-back rule + refusal tests pass on the deployed tree; etsy_api OPEN",
    "F-878": "launch packet generated by the deployed tree: recorded_suite PASS, every section",
    "F-473": "preemption tests pass on the deployed tree; swarm/preempt.py reached on b931d17",
    "F-191": "MJs snapshot/reconciliation tests pass on the deployed tree",
    "F-193": "gallery forecast tests pass on the deployed tree",
    **{u: "row tests pass on the deployed tree; producer module reached on b931d17"
       for u in ("F-491", "F-586", "F-591", "F-793", "F-498")},
    **{u: 'W4 lane tests for the row pass on the deployed tree; producer module reached on b931d17' for u in BATCH6},
    **{u: 'production serves the funding packet on b931d17; packet tests pass on the deployed tree' for u in BATCH6B},
    **{u: 'seller-identity tests pass on the deployed tree; module reached on b931d17 via launch.plan' for u in BATCH6C},
    **{u: 'deployed b931d17: commerce/search.py and commerce/ranking_readiness.py unchanged since the deploy; the deployed-tree run of test_w4_close5_rows6 passes' for u in BATCH7},
    **{u: ('deployed b931d17: growth/ads_readiness.py unchanged since the deploy; production raised the recheck OwnerAction #32 (GET /api/owner-actions); the deployed-tree run of the F-685 test passes') for u in C6_BATCH1_PROD},
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
            # idempotent: a re-run on an already-edited mapping does not repeat the tag
            parts = [x for x in str(r.get("searched") or "").split(" | ") if x]
            parts = [x for i, x in enumerate(parts) if x != TAG or TAG not in parts[:i]]
            r["searched"] = " | ".join(parts + ([] if TAG in parts else [TAG]))
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
            "tests": FM_EDITS[(sl, uid)]["tests+"], "worker": ("W4-CLOSE6 2026-10-20" if uid in C6_CLOSED else "W4-CLOSE5 2026-10-20"),
            "deployed_commit": DEPLOYED})
    cl_path.write_text(json.dumps(cl, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"fm": [u for _s, u in FM_EDITS], "production_closed": list(PRODUCTION_CLOSED),
                      "audit": apply_audit5()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
