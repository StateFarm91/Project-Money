"""Wave-4 lane FM, second pass: close the rows the w4 fold kept OPEN, on verified evidence.

`fold.py` folded 180 rows mechanically from wave-3 claims. The rows it kept (FOLD_REPORT.json
`kept_open`) and the REGATE / REMAP clusters (FM_OPEN_CLUSTERS.json) carried a qualifier or a
recorded defect that only a reading of the current code can settle. Each entry below records
what was read on this head (the `checked` note) and the corrected mapping fields. Nothing here
certifies a row: `aggregate.cap()/completion()` adjudicates the overlay exactly as it
adjudicates the canonical mapping, and a row is written back only when

  (a) the overlay computes COMPLETE or GATED -- or the entry is a `refresh` (an honest update of
      an OPEN row's missing part / next action, which stays OPEN), and
  (b) every cited test exists and its suite was green: in the integrator's full run on cc4a129
      (w4/fold_test_results.json, code-identical to this head outside build2/reachability.py)
      or in this lane's own sequential run on this head (w4/close_test_results.json).

Rules applied while writing the entries (WAVE4_BRIEF): a gate is recorded only when the
remaining step is genuinely owner / data / external (KYC, a credential grant, a deploy, real
customer or marketplace data, a provider capability); executable company work stays OPEN with
the work named. A defect is cleared only when the code on this head no longer has it, and the
entry names the code that fixed it.

Run (from brambleloop/):
  python3 research/final_build/w4/close_fm.py --plan       # verdict per entry, test files
  python3 research/final_build/w4/close_fm.py --run-tests  # runs each cited file NOT green on
                                                           # cc4a129, one at a time
  python3 research/final_build/w4/close_fm.py --apply      # writes mapping + remap + report
  python3 research/final_build/aggregate.py                # re-adjudicate + snapshot
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
ROOT = FB.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FB))
sys.path.insert(0, str(FB / "w3"))
import aggregate as agg  # noqa: E402
import fold  # noqa: E402

HEAD_SHA7 = "8b67414"
RESULTS = HERE / "close_test_results.json"
PY = os.environ.get("BL_PY", "/home/user/Project-Money/brambleloop/.venv/bin/python")

REACH = "runtime consumer per reachability"


def _k_gate(uid):
    import closure_w3
    return dict(closure_w3.T[uid]["gate"])


# --------------------------------------------------------------------------------------------
# REGATE: lane K's audit (f0c2d12, code G) found the defect repaired and the remaining step
# gated. Each defect was re-read on this head; `checked` names the code that repaired it.
# --------------------------------------------------------------------------------------------
REGATE = {
    "F-005": dict(
        checked="runtime/etsy_ops.certified_payload refuses UNKNOWN taxonomy and reads the "
                "certified verdict that search.judge_hero writes back (release.py:1255, "
                "release_gates.py:1005) -- no fixture forces PASS any more",
        tests=["tests/test_search_hero_publish.py::test_certify_assets_seo_grant_publish_creates_exactly_one_draft_with_no_forced_verdict",
               "tests/test_search_hero_publish.py::test_no_certified_listing_set_means_no_hero_pass_and_publish_makes_no_request"],
        coverage="PARTIAL",
        missing_part="the deepest truthful category is chosen from the seller taxonomy snapshot, "
                     "which has never been read (listing.taxonomy_refresh is a no-op behind "
                     "etsy_api); until it is, every category reads UNKNOWN and publish refuses"),
    "F-007": dict(
        checked="runtime/pipeline.py:1844 sends each canonical property through "
                "EtsyClient.set_listing_property (the 'never transmitted' defect is repaired)",
        tests=["tests/test_r2_product_listing_writes.py::test_the_pipeline_passes_the_grant_to_every_post_create_write"]),
    "F-081": dict(
        checked="gates/certificate.certify binds physical evidence (binding['passed'] sets "
                "physical_test_passed), so the gate is no longer fail-closed forever"),
    "F-118": dict(
        checked="gates/first_customer is called from publish/eligibility.py:588 and "
                "runtime/pipeline.py:682 (it had no runtime caller)",
        tests=["tests/test_eligibility.py::test_a_launch0_slug_is_held_to_the_first_customer_gate",
               "tests/test_eligibility.py::test_the_real_first_customer_gate_blocks_launch0_today"]),
    "F-160": dict(
        checked="ops/credential_register.owner_requests is called by runtime/release.py:3679 "
                "(owner queue) -- the rotation card reaches the owner",
        tests=["tests/test_fb4_ops.py::test_the_credential_rotation_card_reaches_the_owner_queue_and_the_dashboard",
               "tests/test_credential_register.py::test_the_chat_exposed_anthropic_key_is_seeded_as_rotation_required"]),
    "F-253": dict(
        checked="generative product redraw is refused in every role (publish/eligibility.py:449, "
                "F-852); Launch-0 uses disclosed renders, so the path is no longer the defect"),
    "F-273": dict(
        checked="finance/reconcile.py:484 and finance/sources.py:100 set offsite_ad_attributed "
                "from ledger evidence; contribution deducts it",
        tests=["tests/test_money_truth.py::test_charged_fees_replace_the_model_and_an_offsite_fee_is_deducted_and_attributed"]),
    "F-321": dict(
        checked="runtime spend writers pass product_slug (gateway/model_gateway.py:229, "
                "gateway/anthropic.py:289/334 -> finance/spend_report.record)",
        tests=["tests/test_w3_spend_attribution.py::test_product_creation_cost_is_split_by_stage"]),
    "F-461": dict(
        checked="ops/hooks/pre-push and ops/deploy.sh run ops/deploy_guard.py on a push to the "
                "production branch; a client hook can be skipped, so server-side enforcement is "
                "the owner's Railway/GitHub setting",
        tests=["tests/test_deploy_path.py::test_a_push_to_production_runs_the_guard_with_the_deployed_commit",
               "tests/test_deploy_path.py::test_the_installed_hook_refuses_an_unproven_push_to_production_and_passes_others"]),
    "F-515@v0.16": dict(
        checked="runtime/etsy_ops.handle_shop_snapshot (daily) feeds intel/etsy_surfaces."
                "assess_shop (etsy_ops.py:894) -- remote verification is wired",
        tests=["tests/test_etsy_readback_observe.py::test_a_complete_shop_is_stored_and_closes_the_owner_actions_it_evidences",
               "tests/test_etsy_readback_observe.py::test_missing_trust_surfaces_cannot_pass_silently"]),
    "F-524": dict(
        checked="store.publish reads etsy_ops.certified_images and sends the certified bytes in "
                "certificate order before anything is created (pipeline.py:1587-1611)",
        tests=["tests/test_etsy_readback_observe.py::test_publish_sends_the_certified_image_bytes_in_certificate_order_and_reads_back",
               "tests/test_etsy_readback_observe.py::test_a_missing_frame_refuses_before_anything_is_created_on_etsy"]),
    "F-540": dict(
        checked="etsy.credential_health is a daily cadence (runtime/worker.py:700) that reads the "
                "OAuth credential, not only the app key",
        tests=["tests/test_etsy_readback_observe.py::test_credential_health_refreshes_rotates_and_persists_and_closes_a_reauth_action",
               "tests/test_etsy_readback_observe.py::test_scope_drift_on_the_stored_credential_is_an_incident"]),
    "F-542": dict(
        checked="store.publish reads the created listing back (pipeline.py:1877 etsy_ops.read_back) "
                "and records store.published only when verified",
        tests=["tests/test_etsy_readback_observe.py::test_a_write_etsy_silently_changed_is_caught_by_read_back_and_halts_the_product"]),
    "F-543": dict(
        checked="store.publish passes the certified image bytes (F-524) and store.activate "
                "re-validates authority at execution",
        tests=["tests/test_etsy_readback_observe.py::test_activation_verifies_the_draft_and_without_a_launch_authorisation_does_not_activate",
               "tests/test_etsy_readback_observe.py::test_with_every_proof_and_authority_present_the_listing_goes_live_and_is_read_back"]),
    "F-556": dict(
        checked="support/response_watch (fb4-OPS) times buyer messages from the owner's "
                "opsauth intake; Etsy exposes no conversation API",
        tests=["tests/test_fb4_ops.py::test_a_buyer_message_unanswered_for_30_hours_is_an_owner_action_and_an_incident",
               "tests/test_fb4_ops.py::test_the_owner_intake_route_requires_the_operator_credential"]),
    "F-577": dict(
        checked="the daily shop snapshot judges is_etsy_payments_onboarded and reopens the owner "
                "action on drift",
        tests=["tests/test_etsy_readback_observe.py::test_payments_going_from_onboarded_to_not_is_an_incident_and_reopens_the_action"]),
    "F-594": dict(
        checked="launch/readiness reads _etsy_exercise_evidence (readiness.py:611-623) instead of "
                "a hard-coded False",
        tests=["tests/test_etsy_readback_observe.py::test_etsy_integration_turns_ready_only_on_a_live_full_round_trip_with_nothing_left"]),
    "F-674": dict(
        checked="the generative-redraw direction is refused in every role (F-852: "
                "publish/eligibility.py:449, visual/product_authority.py); the protected "
                "photoreal stage is R&D (D-FB-7) awaiting provider capability"),
    "F-676": dict(
        checked="generative product redraw refused (F-852); protected-region enhancement waits "
                "on provider fidelity at stitch scale"),
    "F-733": dict(
        checked="visual/freeze.py leaves approved_pack_fingerprint None by design (its only "
                "copy is the production model.frozen audit row) and enforcement_proof compares "
                "it only when known -- recording it is the production approval row"),
    "F-734": dict(
        checked="the product floor is refused for generated product imagery (F-852); a "
                "model-bearing frame clearing every floor needs provider capability"),
    "F-851": dict(
        checked="V1 generative redraw is refused (F-852) on the main line; the B+C photoreal "
                "presentation waits on V2 provider capability (D-FB-7)"),
}

# --------------------------------------------------------------------------------------------
# FOLD rows the fold kept OPEN because the wave-3 claim carried a qualifier. The qualifier was
# re-read against this head.
# --------------------------------------------------------------------------------------------
_K8_ROUTES = ("commerce/estate_api.make_router, mounted in app/main.py:93-95 "
              "(POST /api/etsy/shop-observation, GET /api/etsy/policy-violations, "
              "GET /api/cx/workspace behind the operator credential)")
FOLD_ROWS = {
    "F-568": dict(
        checked="the owner-intake half the claim left to W1 is mounted: " + _K8_ROUTES +
                "; commerce/policy_violations ranks P0/P1/P2, sets deadline, remediation owner, "
                "legal-review owner action and closure proof; census escalates overdue items",
        set=dict(producer="src/brambleloop/commerce/policy_violations.py::apply_observation / "
                          "escalate_overdue",
                 consumer="POST /api/etsy/shop-observation (page=policy_violations) and GET "
                          "/api/etsy/policy-violations (commerce/estate_api, app/main.py); "
                          "runtime/etsy_ops census -> escalate_overdue",
                 durable_state="incidents policy_violation:*; owner_actions",
                 maturity="INTEGRATED", coverage="FULL", missing_part=None, defect=None),
        tests=["tests/test_k8_shop_cx.py::test_policy_violation_items_become_ranked_incidents_with_escalation_and_closure_proof",
               "tests/test_k8_shop_cx.py::test_a_violation_past_its_deadline_is_restated_overdue_with_an_owner_action",
               "tests/test_k8_shop_cx.py::test_routes_guard_customer_content_and_writes_with_the_operator_credential",
               "tests/test_w3_laura_cc_providers.py::test_k8_estate_routes_are_mounted_and_customer_data_is_operator_only"]),
    "F-585": dict(
        checked="commerce/shop_options.evaluate judges 8 controls (value, desired state, "
                "consequence, authority) inside the daily etsy.shop_snapshot and detects DRIFT/"
                "CHANGED/label changes; the browser-only half is the owner's dated observation "
                "through " + _K8_ROUTES,
        set=dict(producer="src/brambleloop/commerce/shop_options.py::evaluate",
                 consumer="runtime/etsy_ops.handle_shop_snapshot (daily cadence) -> incident "
                          "etsy.shop:options_drift; POST /api/etsy/shop-observation",
                 durable_state="operating_readings (shop snapshot); incidents etsy.shop:*",
                 maturity="INTEGRATED", coverage="FULL", missing_part=None, defect=None),
        tests=["tests/test_k8_shop_cx.py::test_options_registry_judges_api_controls_and_reports_browser_only_as_unobserved",
               "tests/test_k8_shop_cx.py::test_an_observation_must_be_dated_complete_and_shaped"]),
    "F-592": dict(
        checked="commerce/shop_security.posture runs inside the daily etsy.credential_health "
                "(runtime/etsy_ops._security_posture): scope drift, credential replaced outside "
                "a refresh, rotation age, callback config; apps and shared-access readings come "
                "from the owner's dated observation through " + _K8_ROUTES + "; never echoes "
                "credentials",
        set=dict(producer="src/brambleloop/commerce/shop_security.py::posture",
                 consumer="runtime/etsy_ops.handle_credential_health (daily cadence) -> incident "
                          "etsy.security:posture; GET /api/etsy/oauth/status",
                 durable_state="oauth_credentials; operating_readings etsy.credential_health",
                 maturity="INTEGRATED", coverage="FULL", missing_part=None, defect=None),
        tests=["tests/test_k8_shop_cx.py::test_security_posture_flags_unexpected_scopes_and_a_credential_replaced_outside_refresh",
               "tests/test_k8_shop_cx.py::test_credential_health_carries_the_posture_and_opens_its_incident",
               "tests/test_k8_shop_cx.py::test_an_empty_apps_reading_closes_its_owner_action_and_a_listed_app_reopens_it"]),
    "F-689": dict(
        checked="support/workspace.workspace joins messages, orders, reviews, refunds, risks and "
                "upstream fixes per buyer; the operator view the claim left to W1 is served at "
                "GET /api/cx/workspace (operator credential, app/main.py:776 CUSTOMER_DATA_ROUTES)"
                "; the recorded defect (unauthenticated /api/support) is repaired "
                "(test_customer_data_auth). Etsy has no messages API, so messages enter through "
                "the owner intake (F-556 gate)",
        set=dict(producer="src/brambleloop/support/workspace.py::workspace",
                 consumer="GET /api/cx/workspace (commerce/estate_api, operator credential); "
                          "support.triage mine_cases -> workspace summary",
                 durable_state="support_cases, orders, customers",
                 maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="Etsy exposes no conversation API: buyer messages reach the "
                              "workspace only through the owner's intake",
                 gate={"kind": "external", "key": "no_messages_api",
                       "detail": "Etsy exposes no conversation API"},
                 next_action="external gate no_messages_api: ingest messages when Etsy exposes "
                             "them; until then the owner intake (F-556) feeds the workspace"),
        tests=["tests/test_k8_shop_cx.py::test_the_workspace_joins_messages_orders_reviews_and_refunds_per_buyer",
               "tests/test_k8_shop_cx.py::test_support_mining_carries_the_workspace_summary",
               "tests/test_w3_laura_cc_providers.py::test_k8_estate_routes_are_mounted_and_customer_data_is_operator_only"]),
    "F-535": dict(
        checked="commerce/cx_root_cause.run (commerce.order_readings cadence) codes every "
                "refund, cancellation, case and complaint with an owner and opens "
                "cx.repeated_cause:<product>:<code> on 3 in 90 days; ingest keeps Etsy's refund "
                "reason. Proven on fake-Etsy rows only: real receipts need transactions_r",
        set=dict(producer="src/brambleloop/commerce/cx_root_cause.py::run",
                 consumer="runtime/orders.handle_order_readings (commerce.order_readings cadence)"
                          " -> commerce/order_readings.read",
                 maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="no real refund/cancellation has been read: receipts need the "
                              "owner's transactions_r grant",
                 gate={"kind": "owner", "key": "transactions_r",
                       "detail": "order/receipt ingestion needs the owner's Etsy re-authorisation"},
                 next_action="owner gate transactions_r: re-authorise Etsy with transactions_r; "
                             "the coding and repetition trigger then run on real receipts"),
        tests=["tests/test_k8_shop_cx.py::test_refund_reasons_are_captured_at_ingest",
               "tests/test_k8_shop_cx.py::test_every_refund_and_case_gets_a_code_and_owner_and_repetition_opens_an_investigation",
               "tests/test_k8_shop_cx.py::test_the_daily_order_readings_carry_the_root_cause_reading"]),
    "F-203": dict(
        checked="the dashboard half the claim left as a wiring request landed (W3-WIRE4 1c): "
                "app/main.py _newest_row_line states query time and newest row for the jobs, "
                "products, incidents and audit tables; CC cards carry observation_window "
                "(providers.validate -> ops/truth.observation_window, mixed_snapshot)",
        set=dict(producer="src/brambleloop/ops/truth.py::observation_window",
                 consumer="app/command_center/providers.validate (every CC card) and "
                          "app/main.py::dashboard (_newest_row_line)",
                 maturity="INTEGRATED", coverage="FULL", missing_part=None, defect=None),
        tests=["tests/test_w3_k7_ops_truth.py::test_vocabulary_rate_and_claims",
               "tests/test_w3_wire4.py::test_k7_dashboard_tables_state_their_newest_row",
               "tests/test_cert_dashboard.py::test_every_block_renders_an_as_of_time"]),
    "F-287": dict(
        checked="the Command Center card the claim left to lane F is wired: "
                "providers.PROVIDERS['visibility'] = launch.visibility.summary; GET "
                "/api/owner/phase/visibility serves the full view (app/phase_api). Impressions, "
                "clicks, conversion and ads read UNMEASURED with their reason until live "
                "listings exist",
        set=dict(producer="src/brambleloop/launch/visibility.py::summary",
                 consumer="app/command_center/providers PROVIDERS['visibility'] and GET "
                          "/api/owner/phase/visibility (app/phase_api.py)",
                 maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="impressions, clicks, conversion, search terms and Offsite Ads "
                              "are UNMEASURED until a live listing and an Etsy Stats export "
                              "exist",
                 gate={"kind": "data", "key": "live_listings",
                       "detail": "no live listing exists (shadow mode)"},
                 next_action="data gate live_listings: the sections fill from ListingOutcome "
                             "periods once a listing is live"),
        tests=["tests/test_w3_k4_launch_verdict.py::test_F289_F287_visibility_provider_contract_and_separate_sources",
               "tests/test_w3_k4_launch_verdict.py::test_routes_are_owner_only_and_registered_operator_gets",
               "tests/test_w3_laura_cc_providers.py::test_visibility_and_search_evidence_tolerate_absence"]),
    "F-176": dict(
        checked="ops/assurance.rollback_baseline binds code SHA, tree digest, schema digest, "
                "config names (never values), coverage map, release-record tests, restore proof "
                "and rollback target, and names each missing component; record_baseline writes "
                "it once per digest on the ops.health sweep (ops/truth.py:353). It reads "
                "recoverable=false locally: code SHA, release-record tests and restore proof "
                "exist only on a deployed build",
        set=dict(producer="src/brambleloop/ops/assurance.py::rollback_baseline / record_baseline",
                 consumer="runtime/release.handle_health_sweep -> ops/truth.sweep "
                          "(ops.health cadence) -> audit_log",
                 maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="the baseline is recoverable only with the deployed candidate's "
                              "code SHA, its release-record suite and a production restore "
                              "proof; locally it reads recoverable=false and names them",
                 gate={"kind": "owner", "key": "production_window",
                       "detail": "deploy the candidate so the baseline is recorded on it"},
                 next_action="owner gate production_window: deploy the frozen candidate; the "
                             "ops.health sweep then records a recoverable baseline"),
        tests=["tests/test_w3_k7_ops_truth.py::test_rollback_baseline_names_missing_components",
               "tests/test_w3_k7_ops_truth.py::test_health_handler_runs_the_truth_sweep"]),
    "F-806": dict(
        checked="learn/technique renders a deterministic diagram per supported stitch and "
                "read_drawing verifies loops, insertion point, post and orientation; GET "
                "/learn/{slug}/technique/{stitch}.svg (learn/api.py:143) re-renders and verifies "
                "before serving (fail-closed 404); lesson assets refuse photos, generic images "
                "and another stitch's diagram. The human attestation remains an additional "
                "floor, no longer the only evidence -- the recorded proxy defect is repaired",
        set=dict(producer="src/brambleloop/learn/technique.py::render / read_drawing",
                 consumer="GET /learn/{slug}/technique/{stitch}.svg (learn/api.py, mounted in "
                          "app/main.py); learn/service.validate_spec asset rules",
                 maturity="INTEGRATED", coverage="FULL", missing_part=None, defect=None),
        tests=["tests/test_w3_k10_learn.py::test_f806_dc_diagram_drawn_as_sc_fails",
               "tests/test_w3_k10_learn.py::test_f806_wrong_insertion_point_wrong_post_and_orientation_fail",
               "tests/test_w3_k10_learn.py::test_f806_every_supported_diagram_verifies_and_is_deterministic",
               "tests/test_w3_k10_learn.py::test_f806_lesson_assets_refuse_photos_generic_images_and_other_stitch_diagrams",
               "tests/test_w3_k10_learn.py::test_f806_public_route_serves_only_verified_declared_diagram",
               "tests/test_w3_k10_learn.py::test_f806_human_visual_attestation_is_still_required"]),
    # Lane TOOLS "(structural)": the operator half the PARTIAL named is closed by
    # run_tests.sh self-enrolment, the EXIT sentinel, attach and the work/observer split
    # (tests/test_w3_suite_job_identity.py); the runtime half was already integrated.
    **{u: dict(
        checked="the operator half of the PARTIAL is closed on this head: run_tests.sh enrols "
                "itself with a durable run id, every terminal path writes the EXIT sentinel "
                "after its record, an attached observer starts nothing and reads the running "
                "run's result, a late observer in a fresh process reads it, and the registry "
                "separates work from observers (tests/test_w3_suite_job_identity.py); the "
                "runtime half (queue/durable job ids, fencing, idempotency) was already tested",
        set=dict(coverage="FULL", missing_part=None, defect=None),
        tests=["tests/test_w3_suite_job_identity.py::" + t for t in tests])
       for u, tests in {
           "F-331": ["test_the_run_enrols_itself_and_a_late_observer_in_a_fresh_process_reads_its_result",
                     "test_every_terminal_path_ends_the_log_with_the_exit_sentinel_matching_the_record"],
           "F-333": ["test_an_attached_observer_starts_nothing_and_takes_the_running_runs_result"],
           "F-335": ["test_every_terminal_path_ends_the_log_with_the_exit_sentinel_matching_the_record",
                     "test_an_interrupted_run_writes_the_130_sentinel_after_its_record"],
           "F-341": ["test_the_run_enrols_itself_and_a_late_observer_in_a_fresh_process_reads_its_result",
                     "test_an_interrupted_run_writes_the_130_sentinel_after_its_record",
                     "test_an_attached_observer_starts_nothing_and_takes_the_running_runs_result"],
       }.items()},
    "F-158": dict(
        checked="ops/deploy_guard record embeds the lock verification, an SBOM and the change "
                "record derived from requirements.lock at the SHA (tests/test_w3_supply_chain.py)"
                "; the Dockerfile installs only the hash-checked lock. The image has never been "
                "built from the lock because no candidate has been deployed",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="the image has never been built from the lock: the Railway build "
                              "of a candidate is the deploy",
                 gate={"kind": "owner", "key": "production_window",
                       "detail": "deploying the frozen candidate builds the image from the lock"},
                 next_action="owner gate production_window: deploy the candidate; deploy_guard "
                             "record then binds the lock verification to the built image"),
        tests=["tests/test_w3_supply_chain.py::test_sbom_and_change_record_are_derived_from_the_lock",
               "tests/test_w3_supply_chain.py::test_release_evidence_is_computed_at_the_sha_and_a_bad_lock_refuses_the_record",
               "tests/test_w3_supply_chain.py::test_an_install_path_that_bypasses_the_hash_checked_lock_is_refused"]),
    "F-159": dict(
        refresh=True,
        checked="tests/test_secret_scan.py now scans inside compressed PDF streams and untracked "
                "generated files; production (Railway) logs are still outside the scan",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="production runtime logs (Railway) are not exported into the scan "
                              "before release",
                 next_action="At release: export the deployed service's log window read-only "
                             "and run the secret-scan patterns over it, recording the verdict "
                             "beside the deploy_guard record"),
        tests=["tests/test_secret_scan.py::test_a_credential_inside_a_compressed_pdf_stream_is_found",
               "tests/test_secret_scan.py::test_the_scan_includes_untracked_and_generated_files_not_only_what_git_tracks"]),
    # Correction of the fee1cfe fold: these rows wait on live-listing exposure (data gate) but
    # the fold wrote coverage FULL, so they read COMPLETE before any customer or listing exists
    # -- exactly what the runtime false-completion guard (ops/owner_queue.data_gates, F-174)
    # refuses (tests/test_w3_k7_owner_queue.py). The logic is built and tested on fixture
    # exposure; deciding on real exposure is the data-gated half.
    **{u: dict(
        checked="the exposure rule is implemented and tested on fixture exposure (wave-3 K3); "
                "the row keeps its data gate live_listings, so it is GATED, not COMPLETE "
                "(F-174 false-completion guard)",
        set=dict(coverage="PARTIAL", defect=None, missing_part=mp,
                 next_action="data gate live_listings: once a listing is live, the same rule "
                             "decides on its real exposure; nothing to build")) for u, mp in {
        "F-260": "no live listing has produced exposure, so no experiment has been concluded "
                 "(or refused) on real data",
        "F-261": "no live listing has produced impressions/clicks/sales, so no real "
                 "underperformer has been diagnosed",
        "F-282": "no live listing has produced exposure, so the zero-sales diagnosis has never "
                 "run on real data",
    }.items()},
    # K14 (lane FM): the drill the PARTIAL names is a production drill after the deploy.
    "F-135": dict(
        checked="lease expiry and fencing are proven by real-process kills (test_persistence "
                "SIGKILL, test_chaos reclaimed-worker fencing, v1.1 sigkilled orchestrator "
                "reclaimed without duplicate effects); the PARTIAL names a drill on the "
                "production worker, which needs the candidate deployed",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="no lease-recovery drill has been recorded against the deployed "
                              "production worker",
                 gate={"kind": "owner", "key": "production_window",
                       "detail": "the drill runs on the deployed candidate"},
                 next_action="owner gate production_window: after the deploy, kill the worker "
                             "mid-job once and record lease reclaim + single completion"),
        tests=["tests/test_v11_autonomy_recovery.py::test_sigkilled_orchestrator_is_reclaimed_without_duplicate_effects",
               "tests/test_v11_autonomy_recovery.py::test_same_named_workers_cannot_complete_each_others_attempt"]),
    # Executable company work remains: refreshed honestly, stays OPEN.
    "F-416": dict(
        refresh=True,
        checked="scripts/supply_chain.py verifies the hash-locked install path, emits the SBOM "
                "and change record into the deploy_guard release record, and names the open "
                "pins (base image tag, apt packages) as findings (tests/test_w3_supply_chain.py)",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="the Dockerfile base image is tag-pinned (python:3.11-slim), not "
                              "digest-pinned, and apt fonts-dejavu-core is unpinned; no "
                              "provenance review record exists for external services and models",
                 next_action="WIRING REQUEST (integrator, Dockerfile): FROM python:3.11-slim@"
                             "sha256:<digest resolved at release> and pin the apt version, then "
                             "run supply_chain.py verify --strict; add a reviewed register of "
                             "external services/models (provider, purpose, review date)"),
        tests=["tests/test_w3_supply_chain.py::test_the_committed_lock_and_dockerfile_verify_and_the_open_pins_are_named"]),
    "F-030": dict(
        refresh=True,
        checked="the frame-job reading is complete (eligibility JOBS gains ANGLE, CONSTRUCTION, "
                "COLOUR_CONTEXT, FIT, LIFESTYLE; gallery_jobs_for/gallery_architecture list "
                "applicable and missing jobs; search_evidence.gallery feeds the "
                "conversion_readiness rung). The frames themselves are missing",
        set=dict(maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="the Launch-0 certified gallery lacks CONTENTS, MATERIALS, "
                              "LIFESTYLE, ANGLE, CONSTRUCTION and COLOUR_CONTEXT frames, so the "
                              "conversion_readiness rung FAILs (FIT stays photograph-only)",
                 gate={"kind": "none", "key": None,
                       "detail": "producing the frames is company work (visual lane)"},
                 next_action="Visual lane: produce disclosed-render frames for each applicable "
                             "missing job on the Launch-0 certified set and re-certify the set")),
    "F-254": dict(
        refresh=True,
        checked="same reading as F-030 (wave-3 K1): the vocabulary is complete, frames missing",
        set=dict(maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="the vocabulary now has alternate angle, construction detail, "
                              "colour context and fit/worn jobs with applicability rules; the "
                              "Launch-0 certified gallery lacks the applicable frames",
                 gate={"kind": "none", "key": None,
                       "detail": "producing the frames is company work (visual lane)"},
                 next_action="Visual lane: produce the applicable ANGLE/CONSTRUCTION/"
                             "COLOUR_CONTEXT/LIFESTYLE frames on the certified set")),
}

# --------------------------------------------------------------------------------------------
# REMAP (lane K code M): rows the v1.1 accounting package may supersede.
# --------------------------------------------------------------------------------------------
REMAP = {
    "F-558": dict(
        checked="commerce/orders_ingest reads Etsy's payment-account ledger (orders_ingest.py:262"
                "-277) so charged fees replace the model and fees_basis says which; cancelled / "
                "refunded receipts are voided not deleted; refund reasons kept; buyer issues "
                "join through support/workspace. The defect (modelled fees stored as charged, "
                "refund boolean) is repaired (fees_basis, VOIDED_STATES, refund_reasons). No real "
                "receipt has been read",
        set=dict(maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="no real receipt, payment or ledger entry has been read: "
                              "ingestion needs the owner's transactions_r grant",
                 gate={"kind": "owner", "key": "transactions_r",
                       "detail": "order/receipt ingestion needs the owner's Etsy re-authorisation"},
                 next_action="owner gate transactions_r: re-authorise Etsy; orders.ingest then "
                             "records payments, charged fees and cancellations from real rows"),
        tests=["tests/test_money_truth.py::test_charged_fees_replace_the_model_and_an_offsite_fee_is_deducted_and_attributed",
               "tests/test_k8_shop_cx.py::test_refund_reasons_are_captured_at_ingest"]),
    "F-608": dict(
        checked="finance/accounting/reconciliation imports bank / Etsy-ledger / processor "
                "statements, matches payouts to deposits, raises unmatched lines and charged-fee "
                "mismatches as exceptions and compares with the books (compare_with_books); the "
                "Accountant cycle runs every 6 h (runtime/worker.py:731 finance.accounting.cycle)"
                ". No real statement feed is connected",
        set=dict(producer="src/brambleloop/finance/accounting/reconciliation.py::match / "
                          "compare_with_books",
                 consumer="finance.accounting.cycle (runtime/worker.py cadence) -> "
                          "finance/accounting/controller",
                 maturity="INTEGRATED", coverage="PARTIAL", defect=None,
                 missing_part="no bank, Etsy payment-ledger or processor statement has been "
                              "imported; reconciliation runs on fixtures only",
                 gate={"kind": "owner", "key": "bank_and_payment_ledger_feed",
                       "detail": "a real bank / Etsy payment-ledger feed needs the owner"},
                 next_action="owner gate bank_and_payment_ledger_feed: connect or export the "
                             "statements; reconciliation then runs on them"),
        tests=["tests/test_v11_accounting_reconciliation.py::test_payout_matches_bank_deposit_and_unmatched_lines_become_exceptions",
               "tests/test_v11_accounting_reconciliation.py::test_charged_fee_that_disagrees_with_the_books_is_a_mismatch",
               "tests/test_v11_accounting_controller.py::test_the_cycle_runs_as_a_worker_job"]),
    "F-609": dict(
        checked="LedgerEntry now carries source, currency, basis and fees_basis (core/models.py "
                "LedgerEntry; modelled fees marked modelled, orders_ingest.py:964); the v1.1 "
                "journal (finance/accounting/models AcctJournalEntry/AcctPosting) carries source "
                "table/id/ref, per-line basis, currency and amount_original, sealed append-only "
                "with reversals; spend and statement lines post into it (posting_rules). The "
                "defect (modelled fees read as charged) is repaired",
        set=dict(producer="src/brambleloop/finance/accounting/posting_rules.py",
                 consumer="finance.accounting.cycle (runtime/worker.py cadence) -> "
                          "finance/accounting/controller",
                 durable_state="acct_journal_entries, acct_postings, ledger",
                 maturity="INTEGRATED", coverage="FULL", missing_part=None, defect=None),
        tests=["tests/test_v11_accounting_ledger.py::test_entries_are_idempotent_by_key_and_balanced_to_the_micro",
               "tests/test_v11_accounting_ledger.py::test_a_correction_is_a_reversal_plus_a_new_version_never_an_edit",
               "tests/test_v11_accounting_ledger.py::test_assumed_fx_is_posted_as_modelled_not_measured",
               "tests/test_v11_accounting_ledger.py::test_raw_sql_tampering_is_detected_by_the_seal"]),
}


def _overlay(uid, base, entry, source):
    ov = json.loads(json.dumps(base))
    if source == "REGATE":
        g = _k_gate(uid)
        ov.update(defect=None, gate=g)
        if entry.get("coverage"):
            ov["coverage"] = entry["coverage"]
        if entry.get("missing_part"):
            ov["missing_part"] = entry["missing_part"]
        elif ov.get("coverage") != "FULL":
            ov["missing_part"] = (str(ov.get("missing_part") or "").strip() or g["detail"])
        ov["next_action"] = f"{g['kind']} gate {g['key']}: {g['detail']}"
    for k, v in (entry.get("set") or {}).items():
        ov[k] = v
    ov["tests"] = sorted(set(ov.get("tests") or []) | set(entry.get("tests") or []))
    note = f"w4-FM close on {HEAD_SHA7} ({source}): {entry['checked']}"
    ov["evidence"] = [e for e in ov.get("evidence") or []
                      if not (isinstance(e, str) and e.startswith(f"w4-FM close on {HEAD_SHA7}"))]
    ov["evidence"].append(note)          # idempotent: a re-run replaces its own note
    return ov


def plan():
    rows, _ = fold._mapping()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    out = []
    for source, table in (("REGATE", REGATE), ("FOLD", FOLD_ROWS), ("REMAP", REMAP)):
        for uid, entry in table.items():
            ov = _overlay(uid, rows[uid], entry, source)
            lvl, notes = agg.cap(dict(ov), reach)
            verdict, reasons = agg.completion(dict(ov, maturity=lvl))
            missing = [t for t in entry.get("tests") or [] if not agg._test_exists(t)]
            files = sorted({t.split("::")[0] for t in ov["tests"] if agg._test_exists(t)})
            out.append({"uid": uid, "source": source, "refresh": bool(entry.get("refresh")),
                        "verdict": verdict, "maturity": lvl, "reasons": notes + reasons,
                        "missing_tests": missing, "test_files": files,
                        "checked": entry["checked"], "row": ov})
    return out


def _cc4a_results():
    return json.loads(fold.RESULTS.read_text())


def _own_results():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {"suites": {}}


def green(ref, cc, own):
    if fold.test_green(ref, cc):
        return True
    m = re.match(r"(tests/[\w/]+\.py)", ref or "")
    if not m or not agg._test_exists(ref):
        return False
    r = own["suites"].get(m.group(1))
    return bool(r) and r["exit"] == 0 and r["ok"] > 0


def run_tests(cands):
    """Runs, one at a time, each cited test file not already green in the cc4a129 run."""
    cc, own = _cc4a_results(), _own_results()
    files = sorted({t.split("::")[0] for c in cands for t in c["row"]["tests"]
                    if agg._test_exists(t) and not fold.test_green(t, cc)})
    env = dict(os.environ, PYTHONPATH="src")
    for f in files:
        t0 = time.time()
        p = subprocess.run([PY, f], cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=900)
        out = p.stdout + p.stderr
        own["suites"][f] = {"exit": p.returncode,
                            "ok": len(re.findall(r"^\s*OK\b", out, re.M)),
                            "fail": len(re.findall(r"^\s*FAIL\b", out, re.M)),
                            "seconds": round(time.time() - t0, 1)}
        print(f, own["suites"][f], flush=True)
    own["_meta"] = {"head": HEAD_SHA7, "runner": "close_fm.py --run-tests (sequential)"}
    RESULTS.write_text(json.dumps(own, indent=1, sort_keys=True) + "\n")


def apply(cands):
    cc, own = _cc4a_results(), _own_results()
    rows, where = fold._mapping()
    written, kept = [], []
    for c in cands:
        why = None
        if c["missing_tests"]:
            why = "cited test missing: " + ", ".join(c["missing_tests"])
        elif c["verdict"] not in ("COMPLETE", "GATED") and not c["refresh"]:
            why = "overlay does not compute COMPLETE/GATED: " + "; ".join(c["reasons"])[:400]
        else:
            bad = [t for t in c["row"]["tests"] if agg._test_exists(t) and not green(t, cc, own)]
            if bad:
                why = "cited test not green: " + ", ".join(bad)[:300]
        if why:
            kept.append({"uid": c["uid"], "source": c["source"], "why": why})
            continue
        row = c["row"]
        tag = f" | w4-FM close on {HEAD_SHA7} ({c['source']})"
        if tag not in str(row.get("searched") or ""):
            row["searched"] = (str(row.get("searched") or "") + tag)[:2000]
        rows[c["uid"]] = row
        written.append({"uid": c["uid"], "source": c["source"], "verdict": c["verdict"],
                        "refresh": c["refresh"], "maturity": c["maturity"],
                        "gate": row.get("gate") if c["verdict"] == "GATED" else None,
                        "checked": c["checked"], "test_files": c["test_files"]})
    by_file: dict[Path, list] = {}
    for uid, f in where.items():
        by_file.setdefault(f, []).append(rows[uid])
    for f, rs in by_file.items():
        old = json.loads(f.read_text())
        new = {r["uid"]: r for r in rs}
        f.write_text(json.dumps([new[r["uid"]] for r in old], indent=1, ensure_ascii=False) + "\n")
    rdir = FB / "mapping" / f"remap_{HEAD_SHA7}"
    rdir.mkdir(exist_ok=True)
    (rdir / "remap_w4_close.json").write_text(json.dumps(
        [rows[x["uid"]] for x in written], indent=1, ensure_ascii=False) + "\n")
    from collections import Counter
    (HERE / "CLOSE_REPORT.json").write_text(json.dumps(
        {"head": HEAD_SHA7, "written": written, "kept_open": kept,
         "counts": {"written": len(written), "kept": len(kept),
                    "by_verdict": dict(Counter(w["verdict"] for w in written))}},
        indent=1) + "\n")
    print(len(written), "written;", len(kept), "kept")


if __name__ == "__main__":
    cands = plan()
    if "--plan" in sys.argv:
        for c in cands:
            print(c["uid"], c["source"], c["verdict"], c["maturity"],
                  "MISSING " + str(c["missing_tests"]) if c["missing_tests"] else "",
                  "" if c["verdict"] in ("COMPLETE", "GATED") else "; ".join(c["reasons"])[:200])
        print(sorted({f for c in cands for f in c["test_files"]}))
    elif "--run-tests" in sys.argv:
        run_tests(cands)
    elif "--apply" in sys.argv:
        apply(cands)
