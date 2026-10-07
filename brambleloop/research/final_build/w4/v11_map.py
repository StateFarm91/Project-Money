"""Wave-4 lane FM: map the 51 Master v1.1 rows (F-880..F-930) into the canonical closure.

The v1.1 rows were tracked only by lane prose (v1_1/V11_CLOSURE.json, wave-3 CLOSURE_f0c2d12
`v1_1`), so the adjudicator and the runtime launch gate (build2/final_master_closure.json) never
saw them: 51 requirement rows were missing from the launch verdict. This script writes
`mapping/v11.json` in the canonical mapping schema (aggregate.KEYS); aggregate.py reads it beside
the v1.0 slices against `master_registry_v1_1.json` and adjudicates every row with the same
cap()/completion() rules -- nothing here certifies a row.

Each entry was written from the v1.1 lane handoffs (v1_1/handoff_*.md) and then checked on this
head: the producer module is the one `module_reachability.json` reports reached and why, the
consumer is the live path that reaches it, the tests are named functions that exist. Launch
class: every v1.1 row is LAUNCH-CRITICAL (fail safe; §96 makes v1.1 additive to v1.0 and the
§95 acceptance tests are launch acceptance). A gate is recorded only when the remaining step is
genuinely owner / data / external (a deploy of the candidate, a bank or Etsy ledger feed, CASL
review); executable company work stays OPEN with the work named.

Run (from brambleloop/): python3 research/final_build/w4/v11_map.py   (writes mapping/v11.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
sys.path.insert(0, str(FB))
import aggregate as agg  # noqa: E402

HEAD_SHA7 = "8b67414"
S = "src/brambleloop/"
REASON = ("Master v1.1 §94 (additive to v1.0, §96); its §95 acceptance tests are launch "
          "acceptance, so the row is launch-critical (fail safe)")
DEPLOY = {"kind": "owner", "key": "production_window",
          "detail": "the v1.1 candidate has never been deployed; hosted evidence needs the "
                    "owner-approved deploy (§95 24h PC-off soak)"}
FEED = {"kind": "owner", "key": "bank_and_payment_ledger_feed",
        "detail": "no bank / Etsy payment-ledger / processor feed is connected"}

T_VIEWS = "tests/test_v11_cc_views.py::"
T_AUTH = "tests/test_v11_cc_auth.py::"
T_ACT = "tests/test_v11_cc_actions.py::"
T_ORCH = "tests/test_v11_autonomy_orchestrator.py::"
T_TL = "tests/test_v11_autonomy_timeline.py::"
T_KPI = "tests/test_v11_autonomy_kpis.py::"
T_SLO = "tests/test_v11_reliability_slo.py::"
T_GW = "tests/test_v11_reliability_gateway.py::"
T_REC = "tests/test_v11_reliability_recovery.py::"
T_WCC = "tests/test_v11_wiring_cc.py::"
T_WIRE = "tests/test_v11_wiring.py::"
T_CTL = "tests/test_v11_accounting_controller.py::"
T_LED = "tests/test_v11_accounting_ledger.py::"
T_MON = "tests/test_v11_accounting_money.py::"
T_REC2 = "tests/test_v11_accounting_reconciliation.py::"
T_DRL = "tests/test_v11_accounting_drill.py::"
T_LRN = "tests/test_v11_learn_loops.py::"
T_ADS = "tests/test_v11_ads_challenge.py::"
T_PWA = "tests/test_v11_pwa_static.py::"
T_PRV = "tests/test_v11_store_preview.py::"

CC = "app/command_center"
CC_API = "GET/POST /api/cc/* (app/command_center/api.make_router, installed by app/main.py)"
CYCLE = ("finance.accounting.cycle (runtime/worker.py cadence, 6 h) -> finance/accounting/job."
         "handle_accounting_cycle -> controller.run_cycle")
PACK = ("finance.accounting.period_pack (runtime/worker.py cadence) -> autonomy/period_packs."
        "build")
MONEY = "GET /api/cc/money and /api/cc/money/drill (Command Center Money tab, providers.PROVIDERS)"

# uid: producer, consumer, durable_state, tests, and (optional) coverage/missing/gate/next/defect.
ROWS = {
    "F-880": dict(
        producer=S + "runtime/worker.py::Worker.run_once (embedded runner + app/scheduler_entry)",
        consumer="app/scheduler_entry.main (runtime loop) and the app's embedded runner",
        durable_state="jobs, ops_runtime_samples (scheduler/worker heartbeats)",
        tests=[T_SLO + "test_a_full_unattended_soak_passes_except_for_unprobed_availability",
               "tests/test_v11_autonomy_recovery.py::test_sigkilled_orchestrator_is_reclaimed_without_duplicate_effects",
               T_WIRE + "test_scheduler_and_worker_heartbeats_are_durable_rows_the_slo_reads"],
        coverage="PARTIAL", gate=DEPLOY,
        missing="hosted 24/7 operation of the v1.1 candidate is unproven: the §95 24h PC-off soak "
                "needs the candidate deployed (v1_1/CLOUD_HOSTING_PLAN.md)",
        next="owner gate production_window: deploy the candidate, run the 24h soak and grade it "
             "with ops/slo soak grading"),
    "F-881": dict(
        producer=S + "ops/slo.py::record_heartbeat (scheduler heartbeats; soak grading)",
        consumer="app/scheduler_entry.main (runtime loop) -> ops/slo",
        durable_state="ops_runtime_samples",
        tests=[T_SLO + "test_an_owner_or_development_session_driving_work_fails_the_soak",
               "tests/test_v11_autonomy_overnight.py::test_an_unattended_night_produces_useful_work_across_departments"],
        coverage="PARTIAL", gate=DEPLOY,
        missing="nothing in the runtime loop needs a session (tested); that production's "
                "scheduler runs unpoked on the v1.1 candidate is unproven until it is deployed",
        next="owner gate production_window: deploy, then grade a soak in which no development "
             "session drives work"),
    "F-882": dict(
        producer=S + CC + "/api.py::make_router (+ /cc/ static PWA)",
        consumer=CC_API, durable_state=None,
        tests=[T_VIEWS + "test_every_tab_answers_and_carries_status_envelopes",
               T_PWA + "test_structure", T_AUTH + "test_route_enumeration_covers_the_contract"]),
    "F-883": dict(
        producer=S + CC + "/api.py::make_router (/cc/ static mount: manifest + service worker)",
        consumer="/cc/ static PWA served by app/main.py",
        durable_state=None,
        tests=[T_PWA + "test_manifest", T_PWA + "test_service_worker_never_caches_api",
               T_PWA + "test_api_client_security"]),
    "F-884": dict(
        producer=S + CC + "/tabs.py::home / mark_seen",
        consumer="GET /api/cc/home, POST /api/cc/home/seen (Command Center Home)",
        durable_state="cc_kv (owner last view)",
        tests=[T_VIEWS + "test_home_and_morning_brief_come_from_real_database_state"]),
    "F-885": dict(
        producer=S + CC + "/approvals.py::inbox / card",
        consumer="GET /api/cc/approvals (build2.executor.approval_inbox + publication evidence)",
        durable_state="owner_actions",
        tests=[T_VIEWS + "test_approval_cards_carry_the_f885_fields"]),
    "F-886": dict(
        producer=S + CC + "/approvals.py::execute",
        consumer="POST /api/cc/approvals/* (session + CSRF + nonce + step-up)",
        durable_state="owner_actions, publication/activation grants, cc_security_events",
        tests=[T_ACT + "test_activation_grant_via_command_center_then_revoke_before_execution_refuses",
               T_ACT + "test_improvement_approval_routes_through_cells",
               T_ACT + "test_authority_refusals_are_audited"]),
    "F-887": dict(
        producer=S + CC + "/auth.py::verify_owner (session, CSRF, nonce, step-up)",
        consumer="every non-public /api/cc route (app/command_center/api)",
        durable_state="cc_owner_sessions, cc_nonces, cc_security_events",
        tests=[T_AUTH + "test_unauthenticated_high_impact_approval_is_refused_and_audited",
               T_AUTH + "test_mutating_routes_need_csrf_nonce_and_same_origin",
               T_AUTH + "test_replayed_nonce_is_refused",
               T_AUTH + "test_consequential_actions_need_step_up_but_pausing_does_not"]),
    "F-888": dict(
        producer=S + CC + "/tabs.py (account view) + auth.py sessions",
        consumer="GET /api/cc/account; session list/revoke routes",
        durable_state="cc_owner_sessions, cc_nonces, cc_security_events",
        tests=[T_AUTH + "test_cookie_flags_and_session_listing_and_revocation",
               T_VIEWS + "test_every_tab_answers_and_carries_status_envelopes"]),
    "F-889": dict(
        producer=S + CC + "/emergency.py::pause / resume / kill_to_shadow",
        consumer="POST /api/cc/emergency/* -> Agent.enabled, SpendLimit.paused, grant revoke, "
                 "core.phase transition",
        durable_state="agents, spend_limits, phase transitions, audit_log",
        tests=[T_ACT + "test_department_pause_stops_the_worker_authorising_its_jobs_but_not_monitoring",
               T_ACT + "test_spend_pause_refuses_spend_and_resume_leaves_breach_pauses_alone",
               T_ACT + "test_kill_switch_records_shadow_and_pauses_the_company",
               T_ACT + "test_publication_grant_is_revoked_by_the_publishing_pause"]),
    "F-890": dict(
        producer=S + "autonomy/orchestrator.py::tick (11 charters, autonomy/charters.py)",
        consumer="executive_orchestrator cadence (runtime/worker.py, 15 min) -> "
                 "autonomy/handlers",
        durable_state="jobs, company_memory missions",
        tests=[T_ORCH + "test_eleven_charters_are_valid_and_cover_every_wired_job_type",
               T_ORCH + "test_the_orchestrator_is_a_scheduled_cadence_with_a_permitted_agent",
               T_WIRE + "test_every_wired_job_type_has_cadence_handler_permission_band_and_department"]),
    "F-891": dict(
        producer=S + "gateway/failover.py::decide (declared-tier routing) + autonomy/charters.py "
                     "(evidence requirement, escalation)",
        consumer="gateway/failover.job_gateway (every billed release handler) and the "
                 "orchestrator's evidence-backed missions",
        durable_state="audit_log model.attempt, company_memory",
        tests=[T_GW + "test_deep_task_with_its_model_down_parks_rather_than_degrading",
               T_GW + "test_fallbacks_only_go_up_and_deep_has_none",
               T_ORCH + "test_every_idle_department_is_given_evidence_backed_work",
               "tests/test_w3_spend_gateway_w8.py::test_the_four_release_handlers_use_job_gateway"]),
    "F-892": dict(
        producer=S + "autonomy/charters.py::validate (mission, agents, allowlist, forbidden, "
                     "inputs, outputs, KPIs, escalation, evidence, handoffs)",
        consumer="autonomy/orchestrator.tick and the enqueue boundary",
        durable_state=None,
        tests=[T_ORCH + "test_every_charter_has_kpis_with_guardrails_and_a_generator",
               T_ORCH + "test_no_protected_job_type_is_ever_generatable_and_coo_is_structurally_forbidden",
               T_ORCH + "test_the_enqueue_boundary_refuses_protected_and_out_of_charter_work"]),
    "F-893": dict(
        producer=S + "autonomy/orchestrator.py::tick",
        consumer="executive_orchestrator cadence (runtime/worker.py, 15 min)",
        durable_state="jobs, owner_actions, company_memory",
        tests=[T_ORCH + "test_protected_work_becomes_one_owner_approval_never_a_job",
               T_ORCH + "test_handoff_evidence_outranks_routine_work",
               T_ORCH + "test_the_orchestrate_job_runs_through_the_worker_and_permission_layer"]),
    "F-894": dict(
        producer=S + "autonomy/orchestrator.py::tick (blocked departments skipped)",
        consumer="executive_orchestrator cadence; autonomy/memory.block_department via "
                 "/api/cc department block",
        durable_state="company_memory blocks",
        tests=[T_ORCH + "test_blocked_and_failing_departments_do_not_stop_the_others",
               T_WCC + "test_department_block_without_stepup_unblock_with_and_the_orchestrator_obeys"]),
    "F-895": dict(
        producer=S + "autonomy/orchestrator.py::tick (idle_wake, SAFE_GENERATED work)",
        consumer="executive_orchestrator cadence",
        durable_state="jobs, company_memory missions",
        tests=["tests/test_v11_autonomy_overnight.py::test_an_unattended_night_produces_useful_work_across_departments"],
        coverage="PARTIAL", gate=DEPLOY,
        missing="overnight autonomy is proven in simulation only; hosted overnight evidence "
                "needs the candidate deployed",
        next="owner gate production_window: deploy, then read one unattended night's useful "
             "work per department from ops/slo department useful-work"),
    "F-896": dict(
        producer=S + "autonomy/handlers.py::handle_morning_handoff",
        consumer="morning handoff cadence (runtime/worker.py) -> company_memory morning_brief; "
                 "GET /api/cc/brief/morning (Home)",
        durable_state="company_memory kind=morning_brief",
        tests=[T_VIEWS + "test_home_and_morning_brief_come_from_real_database_state"]),
    "F-897": dict(
        producer=S + CC + "/notifications.py::refresh (dedup, severity, quiet hours, digest)",
        consumer="GET /api/cc/notifications; notification refresh on the ops cadence",
        durable_state="cc_notifications",
        tests=[T_VIEWS + "test_notifications_suppress_routine_noise_and_surface_real_incidents",
               T_VIEWS + "test_security_notification_counts_attacks_not_expired_tabs"],
        coverage="PARTIAL",
        gate={"kind": "owner", "key": "casl_notification_authority",
              "detail": "external email/SMS/push needs a CASL review and the owner's authority"},
        missing="notifications are in-app only; an external channel (email/SMS/push) that "
                "reaches the owner away from the page needs CASL review and owner authority",
        next="owner gate casl_notification_authority: approve one external channel; the "
             "deduplicated severity-ranked queue then feeds it"),
    "F-898": dict(
        producer=S + CC + "/readers.py (production tables; UNKNOWN never 0)",
        consumer=CC_API,
        durable_state=None,
        tests=[T_VIEWS + "test_no_fixture_or_demo_data_in_production_paths",
               T_VIEWS + "test_money_is_unknown_not_zero_when_the_accountant_is_absent",
               T_VIEWS + "test_provider_output_passes_through_with_provenance"]),
    "F-899": dict(
        producer=S + CC + "/tabs.py::operations_drill / money_drill (-> finance/accounting/"
                          "dashboard.drill)",
        consumer="GET /api/cc/operations/drill and /api/cc/money/drill",
        durable_state=None,
        tests=[T_VIEWS + "test_timeline_and_drill_down_carry_provenance",
               T_DRL + "test_every_dashboard_metric_drills_and_sums"]),
    "F-900": dict(
        producer=S + "ops/recovery.py::restart_stuck_job / release_stale_lease / "
                     "rerun_department_cycle (+ ops/slo summary)",
        consumer="Command Center operations recovery routes (step-up) and the operations tab",
        durable_state="jobs, audit_log recovery rows",
        tests=[T_REC + "test_restart_stuck_job_is_idempotent_and_audited",
               T_REC + "test_restart_refuses_a_job_on_a_live_lease_and_audits_the_refusal",
               T_WCC + "test_recovery_routes_need_stepup_and_refuse_unsafe_cases"]),
    "F-901": dict(
        producer=S + "finance/accounting/controller.py::run_cycle",
        consumer=CYCLE, durable_state="acct_journal_entries, acct_exceptions, acct_period_locks",
        tests=[T_CTL + "test_controller_cycle_is_idempotent_and_next_work_follows_the_contract",
               T_CTL + "test_the_cycle_runs_as_a_worker_job"]),
    "F-902": dict(
        producer=S + "finance/accounting/health.py (source health) + posting_rules.py",
        consumer=CYCLE + "; " + MONEY,
        durable_state="acct_journal_entries, ledger, cost_entries",
        tests=[T_MON + "test_disconnecting_the_order_source_turns_money_unknown_not_zero",
               T_MON + "test_empty_database_is_unknown_never_zero_and_never_raises",
               T_MON + "test_a_stale_source_is_labelled_stale"]),
    "F-903": dict(
        producer=S + "finance/accounting/ledger.py (balanced, sealed, append-only journal)",
        consumer=CYCLE, durable_state="acct_journal_entries, acct_postings",
        tests=[T_LED + "test_entries_are_idempotent_by_key_and_balanced_to_the_micro",
               T_LED + "test_posted_records_are_immutable_through_the_orm",
               T_LED + "test_a_correction_is_a_reversal_plus_a_new_version_never_an_edit",
               T_LED + "test_locked_period_never_moves_late_changes_book_in_the_next_open_period"]),
    "F-904": dict(
        producer=S + "finance/accounting/reconciliation.py::match / import_statement",
        consumer=CYCLE, durable_state="acct_statement_lines, acct_exceptions",
        tests=[T_REC2 + "test_injected_duplicate_fee_payment_and_refund_are_detected_and_not_double_counted",
               T_REC2 + "test_payout_matches_bank_deposit_and_unmatched_lines_become_exceptions",
               T_REC2 + "test_a_replayed_statement_is_imported_once"],
        coverage="PARTIAL", gate=FEED,
        missing="reconciliation runs on imported statements; no bank, Etsy payment-ledger or "
                "processor statement has ever been imported",
        next="owner gate bank_and_payment_ledger_feed: connect or export a statement feed"),
    "F-905": dict(
        producer=S + "finance/accounting/views.py::accrual / cash",
        consumer=CYCLE + "; " + MONEY, durable_state=None,
        tests=[T_MON + "test_accrual_and_cash_are_separate_bases_and_cash_is_unknown_without_a_bank"]),
    "F-906": dict(
        producer=S + "finance/accounting/profitability.py::by",
        consumer=PACK + "; " + MONEY, durable_state=None,
        tests=[T_DRL + "test_profitability_by_every_dimension_sums_to_the_company_total"]),
    "F-907": dict(
        producer=S + "finance/accounting/attribution.py::report",
        consumer=PACK, durable_state="cost_entries, acct_journal_entries",
        tests=[T_DRL + "test_cost_attribution_by_product_release_department_provider"]),
    "F-908": dict(
        producer=S + "finance/accounting/cash.py::position",
        consumer=MONEY + " (accounting summary)", durable_state=None,
        tests=[T_MON + "test_cash_position_reserves_safe_budget_and_runway"],
        coverage="PARTIAL", gate=FEED,
        missing="cash, expected payout and runway are UNKNOWN until a bank / Etsy ledger feed "
                "exists (obligations, commitments, reserves and safe budget are computed)",
        next="owner gate bank_and_payment_ledger_feed: connect a bank / Etsy ledger feed"),
    "F-909": dict(
        producer=S + "finance/accounting/tax_pack.py::pack",
        consumer=PACK, durable_state=None,
        tests=[T_CTL + "test_tax_pack_is_preparation_only_cad_canada_with_questions"]),
    "F-910": dict(
        producer=S + "finance/accounting/close.py::checklist / lock_period",
        consumer=CYCLE, durable_state="acct_period_locks",
        tests=[T_CTL + "test_month_end_close_checklist_blocks_until_clean_then_locks"]),
    "F-911": dict(
        producer=S + "finance/accounting/anomalies.py::detect",
        consumer=CYCLE, durable_state="acct_exceptions",
        tests=[T_REC2 + "test_anomalies_fee_rate_refunds_deposits_duplicates_and_chain"]),
    "F-912": dict(
        producer=S + "finance/accounting/policy.py::check_spend",
        consumer="growth ads proposals (growth/ads_readiness -> finance_check) and the "
                 "controller cycle",
        durable_state="acct_challenges",
        tests=[T_CTL + "test_growth_spend_violating_margin_and_cash_policy_is_blocked_by_finance",
               T_CTL + "test_budget_availability_is_never_permission",
               T_ADS + "test_s95_real_lane_e_check_spend_blocks_growth_spend_unmocked"]),
    "F-913": dict(
        producer=S + "finance/accounting/forecast.py::forecast",
        consumer=MONEY + " (providers PROVIDERS 'accounting' -> dashboard.summary)",
        durable_state=None,
        tests=[T_MON + "test_forecast_is_a_range_with_assumptions_never_a_booked_point",
               "tests/test_w4_fm_provider_table.py::test_modules_behind_the_table_are_reached"]),
    "F-914": dict(
        producer=S + "finance/accounting/dashboard.py::summary",
        consumer=MONEY, durable_state=None,
        tests=[T_MON + "test_summary_items_label_actual_vs_estimated",
               T_VIEWS + "test_the_real_accountant_passes_through_and_never_shows_unknown_as_zero",
               "tests/test_w4_fm_provider_table.py::test_functions_named_in_the_live_provider_table_are_live"],
        coverage="PARTIAL",
        missing="period controls do not work: the Money tab sends ?period= but GET /api/cc/money "
                "ignores it and providers.call('accounting', db) always asks for the default "
                "30-day window (dashboard.summary accepts window=)",
        next="WIRING REQUEST (lane CC, app/command_center/api.py + tabs.money): accept "
             "period/window on /api/cc/money and pass it to the accounting provider as "
             "summary(db, window=...); test that a 7d request returns the 7d envelope"),
    "F-915": dict(
        producer=S + "finance/accounting/dashboard.py::drill",
        consumer="GET /api/cc/money/drill (providers PROVIDERS 'accounting_drill')",
        durable_state=None,
        tests=[T_DRL + "test_displayed_profit_traces_to_orders_fees_spend_and_corrections",
               T_DRL + "test_every_dashboard_metric_drills_and_sums",
               "tests/test_w4_fm_provider_table.py::test_functions_named_in_the_live_provider_table_are_live"]),
    "F-916": dict(
        producer=S + "finance/accounting/handoff.py::export",
        consumer=PACK, durable_state=None,
        tests=[T_CTL + "test_human_accountant_handoff_export_is_self_describing"]),
    "F-917": dict(
        producer=S + "finance/accounting/controller.py::run_cycle (a package with no "
                     "money-moving, filing, signing or banking capability)",
        consumer=CYCLE, durable_state=None,
        tests=[T_CTL + "test_guardrails_the_package_has_no_money_moving_capability"]),
    "F-918": dict(
        producer=S + "autonomy/kpis.py::compute (guardrail voids) + improve/policy_loops.py::"
                     "guardrail_objections",
        consumer="autonomy department review (orchestrator) and improve.sandbox cadence",
        durable_state="company_memory KPI snapshots, learn_policy_lessons",
        tests=[T_KPI + "test_a_refused_job_voids_every_kpi_of_its_department",
               T_KPI + "test_duplicate_and_noop_outputs_cannot_farm_the_useful_count",
               T_LRN + "test_guardrail_kpi_and_cross_agent_challenge_refuse_a_gamed_win"]),
    "F-919": dict(
        producer=S + "improve/policy_loops.py::challenge + finance/accounting/policy.py::"
                     "check_spend",
        consumer="improve.sandbox cadence (policy loops) and growth ads proposals",
        durable_state="learn_policy_lessons, acct_challenges",
        tests=[T_LRN + "test_guardrail_kpi_and_cross_agent_challenge_refuse_a_gamed_win",
               T_ADS + "test_s95_lane_e_check_spend_block_is_obeyed",
               T_CTL + "test_growth_spend_violating_margin_and_cash_policy_is_blocked_by_finance"]),
    "F-920": dict(
        producer=S + "autonomy/memory.py::remember / recall / record_event",
        consumer="orchestrator, morning handoff, Command Center timeline and Ask",
        durable_state="company_memory, company_timeline",
        tests=[T_TL + "test_memory_and_timeline_writes_are_idempotent_on_their_key",
               T_WIRE + "test_continuity_labels_memory_and_ledger_non_rederivable_and_excludes_live_sessions"]),
    "F-921": dict(
        producer=S + "gateway/failover.py::decide / job_gateway",
        consumer="every billed release handler through job_gateway (W-8 adopted)",
        durable_state="audit_log model.attempt",
        tests=[T_GW + "test_failover_picks_the_healthy_approved_model_when_primary_is_down",
               T_GW + "test_a_total_outage_raises_and_corrupts_nothing",
               T_GW + "test_deep_task_with_its_model_down_parks_rather_than_degrading",
               "tests/test_w3_spend_gateway_w8.py::test_spend_stays_single_path_through_job_gateway"]),
    "F-922": dict(
        producer=S + "gateway/failover.py::decide",
        consumer="every billed release handler through job_gateway (W-8 adopted)",
        durable_state="audit_log model.attempt, cost_entries",
        tests=[T_GW + "test_routing_parks_when_the_month_cannot_afford_the_call",
               T_GW + "test_a_dearer_fallback_is_not_used_when_it_would_cross_the_ceiling",
               T_GW + "test_an_identical_cacheable_request_is_served_without_a_call",
               T_GW + "test_compiler_tasks_are_refused_not_routed"]),
    "F-923": dict(
        producer=S + "ops/slo.py::availability (external probe rows only)",
        consumer="slo_check cadence (runtime/worker.py, 15 min) -> slo.* incidents; "
                 "Command Center operations",
        durable_state="ops_runtime_samples (probe rows)",
        tests=[T_SLO + "test_availability_needs_an_external_probe_not_a_process_heartbeat",
               T_SLO + "test_availability_with_thin_coverage_is_unknown_not_up",
               T_SLO + "test_watchdog_records_probe_heartbeat_and_runs_the_check"],
        coverage="PARTIAL", gate=DEPLOY,
        missing="no availability reading exists: the external probe (watchdog) has never run "
                "against the hosted candidate",
        next="owner gate production_window: deploy the candidate with the watchdog probe"),
    "F-924": dict(
        producer=S + "ops/slo.py::scheduler_freshness / cadence_freshness / queue_latency / "
                     "recovery_time (check raises slo.* incidents)",
        consumer="slo_check cadence (runtime/worker.py, 15 min)",
        durable_state="ops_runtime_samples, incidents slo.*",
        tests=[T_SLO + "test_stale_scheduler_from_cadence_jobs_raises_and_then_resolves_an_incident",
               T_SLO + "test_queue_latency_fraction_and_percentiles",
               T_SLO + "test_department_useful_work_counts_useful_hours_and_alerts_on_breach"],
        coverage="PARTIAL",
        gate={"kind": "owner", "key": "hosted_operating_history",
              "detail": "the SLOs are defined and monitored on a cadence; the error budgets need "
                        "hosted operating history of the deployed candidate"},
        missing="the SLOs have no hosted operating history: the v1.1 candidate is not deployed",
        next="owner gate hosted_operating_history: deploy; the slo_check cadence then measures "
             "real error budgets"),
    "F-925": dict(
        producer=S + CC + "/api.py::make_router (approvals, monitoring, emergency, sessions, "
                          "notifications, incident ack over HTTP)",
        consumer=CC_API, durable_state=None,
        tests=[T_VIEWS + "test_every_tab_answers_and_carries_status_envelopes",
               T_AUTH + "test_route_enumeration_covers_the_contract",
               T_ACT + "test_kill_switch_records_shadow_and_pauses_the_company"]),
    "F-926": dict(
        producer=S + "store_foundation/preview.py::render_preview (+ preview_v2.render_compare)",
        consumer="Command Center store preview route (app/command_center/api.store_preview_"
                 "handler, owner-only, never cached)",
        durable_state=None,
        tests=[T_PRV + "test_preview_shows_every_surface",
               T_PRV + "test_unverified_frame_is_withheld_not_shown",
               T_WCC + "test_store_preview_is_owner_only_and_never_cached_or_indexed",
               # W4-FM2: preview v2 (the owner's v1 rejection notes: generic + technical) is
               # built -- canonical banner/logo exact, product-first fold, no jargon above the
               # fold, Laura labelled internal-preview -- and served beside v1 for comparison.
               "tests/test_w3_store_ux_structure.py::test_v2_has_every_required_surface",
               "tests/test_w3_store_ux_mobile.py::test_no_technical_jargon_above_the_fold",
               "tests/test_w3_store_ux_mobile.py::test_fold_leads_with_product_not_process",
               "tests/test_w3_store_ux_mobile.py::test_compare_page_shows_both_first_screens_and_metrics"],
        coverage="PARTIAL",
        gate={"kind": "owner", "key": "store_preview_v2_review",
              "detail": "the owner rejected v1 on taste; v2 (store_foundation/preview_v2) answers "
                        "the rejection notes and is served beside v1 -- acceptance is the "
                        "owner's judgement; mirroring live settings needs OA-A1 (re-authorise) "
                        "/ OA-OBS (dated observation of the fields no API returns)"},
        missing="owner acceptance of preview v2 (a taste decision only the owner makes) and the "
                "live Etsy settings it mirrors (UNKNOWN until OA-A1/OA-OBS; store_foundation/"
                "live_state reads them when available)",
        next="Owner: review the v2 vs v1 comparison in the Command Center store preview and "
             "accept or annotate; OA-A1/OA-OBS let the preview mirror the live settings"),
    "F-927": dict(
        producer=S + "autonomy/status.py::timeline (+ memory.record_event)",
        consumer="GET /api/cc/timeline (Command Center) and laura.executive_tick",
        durable_state="company_timeline, incidents, owner_actions, cost_entries, audit_log",
        tests=[T_TL + "test_timeline_records_and_merges_sources_newest_first",
               T_VIEWS + "test_timeline_and_drill_down_carry_provenance"]),
    "F-928": dict(
        producer=S + CC + "/ask.py::ask (deterministic, source-linked)",
        consumer="POST /api/cc/ask (Command Center Ask)",
        durable_state=None,
        tests=[T_VIEWS + "test_ask_why_is_a_product_blocked_is_grounded_in_gate_records",
               T_VIEWS + "test_ask_answers_unknown_rather_than_inventing"]),
    "F-929": dict(
        producer=S + "autonomy/orchestrator.py::tick (charter + enqueue-boundary checks) + "
                     "app/command_center/ask.py::ask",
        consumer="executive_orchestrator cadence; POST /api/cc/ask",
        durable_state="jobs, owner_actions",
        tests=[T_ORCH + "test_the_enqueue_boundary_refuses_protected_and_out_of_charter_work",
               T_VIEWS + "test_ask_answers_unknown_rather_than_inventing",
               T_WIRE + "test_a_provider_item_naming_a_protected_or_foreign_job_is_never_queued"]),
    "F-930": dict(
        producer=S + "autonomy/orchestrator.py::tick (SAFE_GENERATED non-spending allowlist)",
        consumer="executive_orchestrator cadence",
        durable_state="jobs",
        tests=[T_ORCH + "test_no_protected_job_type_is_ever_generatable_and_coo_is_structurally_forbidden",
               T_WIRE + "test_the_four_jobs_run_under_the_real_worker_with_zero_spend",
               T_ADS + "test_ceiling_enforced_even_with_owner_authority"]),
}


def build():
    reg = json.loads((FB / "master_registry_v1_1.json").read_text())["requirements"]
    assert len(reg) == len(ROWS) == 51, (len(reg), len(ROWS))
    out, missing = [], []
    for req in reg:
        uid = req["id"]
        e = ROWS[uid]
        for t in e["tests"]:
            if not agg._test_exists(t):
                missing.append(f"{uid}: {t}")
        full = e.get("coverage", "FULL") == "FULL"
        gate = e.get("gate") or {"kind": "none", "key": None,
                                 "detail": "no owner/data/external gate on the remaining step"}
        out.append({
            "uid": uid, "launch_class": "LAUNCH-CRITICAL", "launch_class_reason": REASON,
            "maturity": "INTEGRATED", "coverage": "FULL" if full else "PARTIAL",
            "missing_part": None if full else e["missing"],
            "producer": e["producer"], "durable_state": e.get("durable_state"),
            "consumer": e["consumer"], "protected_effect": None,
            "tests": list(e["tests"]),
            "evidence": [f"w4-FM v1.1 mapping on {HEAD_SHA7}: producer reached per "
                         "module_reachability.json; v1_1/handoff_*.md claims re-read against "
                         "the code"],
            "build2_rows": [], "gate": gate, "defect": e.get("defect"),
            "next_action": "none" if full else e["next"],
            "confidence": "high" if full else "medium",
            "searched": f"w4-FM v11_map.py on {HEAD_SHA7}"})
    if missing:
        raise SystemExit("cited tests missing:\n" + "\n".join(missing))
    (FB / "mapping" / "v11.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(len(out), "v1.1 rows mapped ->", FB / "mapping" / "v11.json")


if __name__ == "__main__":
    build()
