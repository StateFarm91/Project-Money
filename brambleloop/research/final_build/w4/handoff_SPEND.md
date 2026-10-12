# W4-SPEND handoff

Branch `claude/w4-SPEND` (worktree `.claude/worktrees/W4-SPEND`). Latest pushed SHA: `git log -1 origin/claude/w4-SPEND`.
Scope after the 2026-10-07 split: **K5b only** (gateway/*, queue/durable.py via wiring, intel/vision.py,
finance/spend_policy.py, F-307/F-339). **K5a moved to lane W4-SPENDA**; this lane no longer edits
finance/spend_report.py, governor.py, unit_cost.py, ops/provider_accounts.py, visual/reliability.py.

## K5a work already finished here (for SPENDA to merge; not edited further by SPEND)

| Row | Status | Evidence |
|---|---|---|
| F-319 spend-to-progress | PROVEN (code) | `finance/governor.spend_to_progress` in `governor.report` (/api/governor); `tests/test_w4_spend_attribution.py::test_spend_to_progress_divides_product_spend_by_new_milestones_and_names_waste`, `::test_no_progress_is_no_ratio_rather_than_zero` |
| F-322 cost per usable gallery incl. judging | PROVEN (code) | `visual/reliability.assess` render+judging, `_judging_cad` from ledger, UNKNOWN named (FLOOR basis); `::test_cost_per_usable_gallery_includes_judging_and_unknown_judging_is_a_floor`, `::test_judging_cost_is_read_from_the_ledger_and_unknown_without_a_sequence` |
| F-325 observation cadence term | PROVEN (code); forecast still DATA-GATED on real history | `finance/sustainability.forecast` observation term + `observation_factor`; `::test_observation_cadence_is_its_own_forecast_term_and_not_counted_twice` |
| F-106 | OWNER-GATED (provider usage API); discrepancy incident already exists | `tests/test_w3_spend_hygiene.py::test_provider_billing_discrepancy_is_an_incident_only_when_current` |
| F-103 | estimate_drift is on /api/spend-report; /api/verify readback = WIRING REQUEST to CC; provider-billing settlement OWNER-GATED | — |
| F-070, F-304, F-629 | NOT STARTED here -> SPENDA | F-304 needs CostEntry columns (integrator, core/models.py) |

## K5b (this lane)

| Row | Status | Evidence (`tests/test_w4_spend_paid_discipline.py`) |
|---|---|---|
| F-312 deterministic before generative | PROVEN | `test_every_deterministic_question_names_code_that_exists_and_never_reaches_a_provider` |
| F-313 quality-proven routing | PROVEN | `test_a_cheaper_route_needs_recorded_equivalence_and_a_regression_reverses_it`; consumer `failover.decide` -> `routing.effective_route` |
| F-314 escalation | PROVEN | `test_an_unsure_cheap_answer_is_asked_once_more_one_tier_up_and_a_sure_one_is_not`, `test_an_escalation_the_ceiling_refuses_returns_the_answer_marked_unsure` |
| F-316 output token discipline | PROVEN | `test_every_prompt_and_task_has_a_closed_schema_and_a_sized_output_budget`, `test_truncated_output_is_rejected_and_billed_not_passed_on` |
| F-317 batching with isolation | PROVEN | `test_a_batch_isolates_each_item_and_stops_whole_at_the_ceiling` |
| F-472 shared breaker across workers | PROVEN | `test_a_second_worker_does_not_pay_to_rediscover_an_outage_the_first_recorded` (`ModelGateway._durably_down` reads `failover.health`) |
| F-328 no spend without a question | PROVEN | `test_a_paid_call_naming_no_question_is_refused_and_recorded`, `test_every_production_reserving_call_site_names_its_question` |
| F-309 shared systematic breaker | PROVEN | `finance/systematic.py` checked in `check_budget_cad`; `test_a_floor_that_never_passes_stops_every_paid_call_for_that_method_until_it_changes`, `test_gallery_vision_feeds_the_breaker_and_reports_pending_before` |
| F-318 backlog must drain | PROVEN | `spend_hygiene.flat_backlogs` + P1 incident; `test_a_paid_backlog_that_does_not_fall_is_a_financial_integrity_incident` |
| F-307 / F-339 no double spend on reclaim | PROVEN (pre-existing) | `tests/test_w3_spend_paid_calls.py::test_a_retried_attempt_replays_the_paid_answer_and_is_not_billed_again`, `::test_a_stale_worker_stops_before_it_pays`, `::test_runtime_sigkill_after_payment_replays_and_completes`, `::test_runtime_sigkill_during_the_call_is_not_blindly_restarted` |
| F-311 cache certified evidence | routing cache now has a runtime caller (`failover.decide` -> `routing.cached_analysis`; `tests/test_model_access.py`); one-helper fingerprint unification OPEN |
| F-098 outage degradation | WIRING REQUEST AUTO-1 |
| F-310 new evidence requirement | WIRING REQUEST AUTO-2 |
| F-659 durable workers checkpoints | WIRING REQUEST AUTO-3 |

## Wiring requests
- AUTO-1 (runtime/worker.py): when `gateway.anthropic.usable()` is false, park (not dead-letter) model-needing jobs, audited `ai.parked`.
- AUTO-2 (swarm/orchestrate.py thrash_sweep): add durable-evidence delta (new audit/observation rows per run) to progress measure.
- AUTO-3 (queue/durable.py): `JobContext.checkpoint(key, state)` persisted on job row; use in model photography / seasonal cycle.
- CC-1 (app/main.py /api/verify): add `spend_report.estimate_drift` as a readback item (F-103).
- INTEGRATOR-1 (core/models.py CostEntry): listing_id, units, observed_cad, evidence_ref columns (F-304).

## Tests run (2026-10-07, all pass)
test_w4_spend_paid_discipline (13), test_w4_spend_attribution (5), test_cert_cost, test_cost_governance_wave2,
test_model_provider, test_spend_governance, test_gateway, test_spend_policy, test_reliability, test_intel,
test_money_truth, test_cert_thrash, test_model_spend_paths, test_w3_spend_paid_calls, test_vacuity,
test_secret_scan, test_reachability, test_w3_tmp_hygiene.

## Next
K5b residuals: F-311 single fingerprint helper (gateway). Otherwise lane is done pending AUTO wiring.
