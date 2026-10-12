# Wave-3 lane K7 — Ops truth, provenance and owner surfaces: handoff

Branch `claude/w3-K7` from `claude/visual-investigation` @ 04b811b. Phase stays shadow: there was no deploy,
no Etsy write, no spend and no paid call.

## Per-row status

| Row | Status | Evidence (test → consumer path) |
|---|---|---|
| F-115 Legacy artefact invalidation | COMPLETE | `test_reengineering_invalidates_legacy_unprovenanced_artefacts` → `ops.artefacts.check` marks un-instrumented artefacts of a superseded version (or a retired `LEGACY_DUPLICATES` slug) as retired. Their state stays `unproven` (never fresh), with `retired`/`invalidated` set on the verdict, and they leave the instrumentation backlog and the coverage denominator. I chose this over a new state so that `test_cert_provenance`'s all-unproven assertion still holds unchanged. Consumers: the `ops.sentinel` handler and `/api/provenance` (estate.invalidated) |
| F-121 Claim-to-evidence contract | COMPLETE | `test_vocabulary_rate_and_claims` → `ops.truth.claim` refuses a positive claim that rests only on configuration, code existence or no errors. `audit_summary` flags an OK status with no sources. It runs over every CC provider in `ops.truth.summary` (`contract_audit`), which is reached from `/api/cc/truth` and the operations tab |
| F-122 Positive-evidence requirement | COMPLETE | same test → `truth.rate` returns UNMEASURED or NOT-YET-OBSERVED when the denominator is 0. The live lint (`audit_summary`) flags a 0 rate printed next to a 0 denominator in any provider output. Provenance coverage of an empty class is `UNMEASURED` |
| F-124 Postcondition verification | COMPLETE | `test_postconditions_read_back`, `test_health_handler_runs_the_truth_sweep` → `ops.assurance.postconditions` reads back restore digest, DONE jobs that have outputs, rebuilds, credentials served, cleanup, and the deployed tree's release record. A VIOLATED result opens a `postcondition:*` incident from the `ops.health` cadence |
| F-127 Unknown is first-class | COMPLETE | same as F-121 → `truth.NON_VALUES`, `normalise` and `is_non_value` form the shared vocabulary that maps existing module spellings |
| F-154 No security theatre | COMPLETE | `test_security_controls_configured_but_unproven_is_unavailable` → functional probes: opsauth accepts a valid token and refuses a wrong one, default-deny on an unregistered route, the CSP middleware on a synthetic response, the owner login refuses a bad credential and a success has been observed, an offsite archive was written, the boot guard ran. A control that is configured but unproven is reported unavailable. Shown in `/api/cc/truth` under security_controls |
| F-161 Provenance coverage metric | COMPLETE | `test_coverage_ratio_and_per_class_graduation_via_sentinel` → `artefacts.coverage` gives numerator and denominator per class. Reported in the `ops.sentinel` audit and in `/api/provenance` (graduation.coverage) |
| F-162 Graduated enforcement | COMPLETE | same test → `declare_graduations` (called by the `ops.sentinel` handler) records `provenance.class_graduated` once a class has artefacts and none of them are unproven. After that, `sweep` blocks release on a missing row in that class only |
| F-167 Legacy provenance backfill | COMPLETE | `test_backfill_reports_launch_relevance_and_retirement` → `backfill.relevance` splits what remains unproven into launch_relevant (Launch-0 scope), retired (invalidated) and other. Recorded in the daily `ops.provenance_backfill` audit |
| F-168 Publication halting scope | COMPLETE | `test_systemic_halt_escalates_and_scopes_back` → `incident_lifecycle.escalate_systemic`, run from the ops.health sweep, opens `systemic-halt:publication` when one failure family halts at least 3 products and at least 50% of the catalogue, or when there is an integrity tamper. `gates.incidents.open_incidents` applies that halt to every slug (`publication_halted`, `release_gates.staleness`). Otherwise halts stay per product, and the halt resolves when the evidence clears |
| F-173 Owner-gate inventory | COMPLETE | `test_packets_and_gate_inventory` → `owner_queue.inventory`, built from the one queue (`executor.approval_inbox`). It covers capability, cost, minutes, requirement kind (credentials/legal/physical/spend/decision) and consequence, plus the Final Master gates by key. Shown in `/api/cc/truth` |
| F-174 Data-gate inventory | COMPLETE | `test_data_gate_inventory_and_false_completion_guard` → `owner_queue.data_gates` lists the executor data gates and the 14 Final Master rows gated on data. A data-gated row labelled COMPLETE while the customers gate is closed sets the status to BLOCKED |
| F-176 Rollback baseline | COMPLETE (record), recoverable=false today | `test_rollback_baseline_names_missing_components` → `assurance.rollback_baseline` holds code SHA, tree digest, schema digest, config names (never values), coverage map, release-record tests, restore proof and rollback target. `record_baseline` writes it to the audit log, once per digest, on the ops.health cadence. Locally `code_sha`, `tests` and `restore_proof` are missing, and they are named |
| F-180 Owner action lifecycle | COMPLETE | `test_lifecycle_states_and_history`, `test_satisfied_leaves_active_queue_parked_listed_apart`, `test_legacy_done_flag_is_closed_unclassified_not_satisfied`, `test_inbox_and_cc_carry_empty_state_and_defer_parks` → adds the OwnerAction columns `state`, `state_at`, `state_reason` and `expires_at`. Supported states: open, satisfied, superseded, withdrawn, parked, expired, plus an honest `closed_unclassified` for a bare `done=True`. The audited `owner_queue.transition` handles moves. The CC `owner_action.defer` now parks the action. `sweep` expires rows (on the ops.health cadence). Ten producers now close with a named state |
| F-195 Incident freshness/actionability | COMPLETE | `test_incident_actionability_and_owner_path` → `incident_lifecycle.actionability` adds last_confirmed, applicability (current, UNCONFIRMED after 48h, or resolved) and remediation owner and path. Policy incidents get an explicit owner path (`POST /api/policy/snapshot`). Unowned families are listed under `needs_owner_path`. Shown in `/api/incidents` (snapshot) and in the CC operations incidents |
| F-197 Tester path in owner UI | COMPLETE | `test_physical_proof_offers_tester_route` → the physical_proof card asks for tester outreach and never asks the owner to crochet. Its `tester_route.tester_status` reads roster status, which is shown in the CC approvals card and at `/api/cc/truth` (tester_roster) |
| F-199 Readiness current-evidence audit | COMPLETE | `test_readiness_reproof_fails_a_stale_ready_verdict` → `assurance.readiness_reproof` re-proves the last `launch.assessed` verdict and the clearance of every product against the current launch standard. It is recorded daily as `launch.reproved` from the ops.health sweep |
| F-203 Data timestamp consistency | COMPLETE for the CC; dashboard part is a WIRING REQUEST | `test_vocabulary_rate_and_claims` → `providers.validate` adds `observation_window` (oldest/newest row time, `mixed_snapshot`) to every CC provider card. Drill gives the `timestamp_basis` (row time vs query time). The legacy `/` dashboard in `app/main.py` is integrator-owned and is covered by the wiring request below |
| F-204 Owner queue empty guard | COMPLETE | `test_empty_queue_proves_nothing_without_fresh_assessment` → `owner_queue.empty_guard` reports PROVEN-EMPTY only when there is a launch.assessed within 26h, the gates were read live, and nothing is withheld. Otherwise it reports UNPROVEN-EMPTY. `closes_anything=False`. The value is in `approval_inbox.empty_state` and the CC approvals inbox. The existing `if requests:` closer guard is unchanged |
| F-337 Expected-duration watchdog | COMPLETE | `test_duration_watchdog_flags_3x_and_diagnoses_without_restarting` → `ops.job_watch.watch` takes the rolling median per job_type (at least 5 samples) and flags a run above 3x it. Signal `job_durations` in `ops.health.read` goes DEGRADED, which leads to the existing persistence escalation |
| F-338 Non-destructive hang diagnosis | COMPLETE | `test_diagnosis_distinguishes_completed_blocked_duplicated` → `job_watch.diagnose` classifies a job as alive, advancing, completed_but_unobserved, blocked_on_dependency or duplicated. It never mutates anything, and outputs are preserved |
| F-343 No false healthy/busy | COMPLETE | `test_activity_never_counts_a_waiter_as_progress` → `job_watch.activity` returns work_executing, work_completed, observer_waiting, blocked or unknown. Self-observing jobs are excluded. The value goes into `health.verdict()["activity"]` and the `ops.health` audit detail |
| F-392 Incident learning | COMPLETE | `test_incident_learning_and_recurrence` → `record_learning` requires root_cause, prevention_ref and regression_ref. `learning()` lists meaningful resolved incidents that lack learning, and open incidents in a family whose prevention was already recorded. The ops.health sweep opens `incident-recurrence:<family>`, and `/api/incidents` shows it |
| F-623 Owner actions & evidence drilldown | COMPLETE | `test_satisfied_leaves...`, `test_cc_provider_drill_and_routes` → every card carries `rank`, `urgency`, `steps`, minutes, cost and consequence. `GET /api/cc/drill?provider=&index=` drills any provider item to source, timestamp, transformation, confidence, reconciliation and safe external ids |
| F-665 Evidence WHY | COMPLETE in code; production defect GATED | same drill test. The envelope reuses `dashboard_truth.evidence`. The recorded defect ("production shows 275 unproven artefacts; the fix is undeployed") is closed only by a deploy, which is the owner gate `production_window` |
| F-870 Owner action packets | COMPLETE | `test_packets_and_gate_inventory`, `test_spend_gate_without_stated_cost_is_not_free` → each card has `why_software_cannot` (from `GATE_PACKETS`, or the new OwnerAction column), `requirement_kind`, `packet_missing` and `packet_complete`. A spend gate with no stated ceiling gets `max_cost_basis=UNKNOWN` instead of CA$0 "free" |

## Files

New: `src/brambleloop/ops/{owner_queue,job_watch,assurance,truth}.py`, `tests/test_w3_k7_owner_queue.py` (10),
`tests/test_w3_k7_ops_truth.py` (16).

Modified: `ops/{artefacts,backfill,health,incident_lifecycle,funding}.py`, `build2/executor.py` (approval_inbox),
`gates/incidents.py`, `runtime/release.py` (ops.health handler: `activity` + `ops.truth.sweep`;
ops.sentinel: declare_graduations + coverage; provenance_backfill relevance; readiness closer and canonical-model
close with named state), `runtime/{storefront_watch,etsy_ops}.py`, `growth/ads_readiness.py`,
`improve/{director,evolution}.py`, `commerce/orders_ingest.py`, `support/response_watch.py` (named lifecycle states).

**Integrator-owned edits (listed as required):** `core/models.py`. I added five columns to OwnerAction:
`state` (default "open"), `state_at`, `state_reason`, `expires_at` and `why_software_cannot`. I also added a
`@validates("done")` hook. `core.migrate` adds the columns in place. Existing rows backfill to `state="open"`,
and a legacy done row reads `closed_unclassified` through `owner_queue.effective_state`.

**Command Center edits (minimal):** in `providers.py`, the `ops_truth` provider and `observation_window` in
`validate`. In `tabs.py`, the operations tab gets a `truth` section. In `api.py`, `GET /api/cc/truth` and
`GET /api/cc/drill`, both read-only and under the default-deny `/api/cc/` owner-session prefix. In
`approvals.py`, card packet fields, defer→parked, and empty_state/parked in the inbox. In `readers.py`,
incident actionability fields.

## Runtime proof

`test_health_handler_runs_the_truth_sweep` runs the real `ops.health` cadence handler (`handle_health_sweep`)
against a seeded DB. It expires a lapsed OwnerAction, opens `postcondition:jobs_completed` for a DONE job with no
outputs, records the rollback baseline, runs the systemic check and writes the `ops.truth.sweep` audit row.
`test_coverage_ratio_and_per_class_graduation_via_sentinel` runs the real `ops.sentinel` handler twice: it
declares the `certificate` class graduated, and on the next sweep it blocks the product that has a certificate
missing a row.

## WIRING REQUESTS

1. `app/main.py` dashboard `_approvals()` currently prints "nothing is waiting on the owner" whenever there are
   no cards. Use `inbox["empty_state"]["state"]` and `["why"]` instead: print the empty message only for
   `PROVEN-EMPTY`, and otherwise print `"queue empty but UNPROVEN: " + why` (F-204).
2. `app/main.py` `/api/owner-actions`: add `"why_software_cannot": c.get("why_software_cannot"),
   "rank": c.get("rank"), "urgency": c.get("urgency"), "max_cost_basis": c.get("max_cost_basis")` to each
   action, and `"empty_state": inbox.get("empty_state"), "parked": inbox.get("parked_owner_actions")` to
   the response (F-870/F-623/F-180).
3. `app/main.py` dashboard tables for jobs, products, incidents and audit (F-203): add an as-of line taken from
   the newest row (`max(at)`) next to the existing query-time line.
4. Optional: `runtime/worker.py` CADENCES does not need a new entry, because the sweep rides `ops.health` (15 min).

## Not verified / open

- Nothing was deployed. Every production number (the 275 unproven artefacts, the restore proof, the boot guard)
  is unchanged until a deploy, which is the owner gate `production_window`.
- `owner_login` reads UNPROVEN until a real owner login is recorded in `cc_security_events`.
- Some producers still set `done=True` without naming a state (`improve/upgrades.py` and older paths). They now
  read `closed_unclassified`; they are not counted as satisfied.

## Tests run

New: `test_w3_k7_owner_queue` 10/10 and `test_w3_k7_ops_truth` 16/16.

Existing tests, all passing (OK-line counts): vacuity 7, secret_scan 7, reachability 11,
route_auth_default_deny 7, rc1_auth 11, w3_reachability_dynamic 3, health 39, artefacts 23,
provenance_backfill 12, cert_provenance 12, provenance_write_path 19, rebuild_graph 10,
incident_lifecycle 7, gates 44, funding 10, executor 44, v11_cc_views 13, v11_cc_actions 7,
v11_cc_auth 16, v11_wiring_cc 5, search_visibility 5, improve 32, improve_director 14,
v11_ads_readiness 11, response 13, cert_orders 23, etsy 17, cert_dashboard 18,
rc1_own_dashboard 4, money_truth 18, seasonal_incidents 6, cert_wiring 16,
cert_improve_autonomy 20, fb4_ops 12.

`test_launch` gives 27 OK and 1 FAIL
(`test_a_company_that_has_done_its_half_is_only_blocked_on_people`: unexpected `final_master_closure`
buildable item). This failure is **pre-existing**: the same failure reproduces on the base commit 04b811b
(checked via `git archive` of HEAD~1). It comes from the K4 merge and the snapshot's 300 OPEN rows, and
K7 code does not touch it.
