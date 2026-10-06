# handoff K11 (wave 3): authority and governance model

Branch `claude/w3-K11`, base `claude/visual-investigation` @ 04b811b. Phase stayed shadow. There were no
paid calls, no network, and no Etsy, Railway or customer effects.

I reused lane D's mechanisms and did not build a second model:

- the COO orchestrator and its single enqueue boundary;
- `charters.PROTECTED_JOB_TYPES` and `SAFE_GENERATED`;
- `laura.core.constitution.review`;
- `improve.governance` and its tiers;
- `Registry.authorize`.

Lane F's step-up (`app/command_center/auth.require_stepup`) is the route-level guard for the new owner APIs.
I did not import lane F's code, because it is not merged; see wiring request 2.

## New package `brambleloop.authority` (lane-owned)

| Module | What |
|---|---|
| `classes.py` | Eleven `ActionClass`es, OBSERVE … CREDENTIALS:<br>• five are AUTONOMOUS and six are GATED;<br>• `JOB_CLASS` classifies every job type the runtime knows, all 140;<br>• `classify()` is fail-closed (consequential name words gate an unlisted type);<br>• build plane vs operate plane: `BUILD_PLANE_JOB_TYPES`, `plane_violations`, `runtime_role` (`BRAMBLELOOP_RUNTIME_ROLE=build`). |
| `models.py` | Tables `authority_policies` and `company_work_items`. `ensure_tables` follows the `autonomy.models` pattern. |
| `policy.py` | `AuthorityPolicy` grant/revoke, the ladder (owner_each → bounded → standing), `safe_history` measured from jobs and incidents rows, `effective_level` (shadow first, auto-demotion), and `check_dispatch`, which is called by `Registry.authorize`. |
| `dag.py` | The durable company coordinator:<br>• operations: `submit`, `record_mission`, `approve`, `cancel`, `reconcile`, `recompute`, `dispatch`, `tick`, `summary`, `known_failure`;<br>• states: blocked, awaiting_approval, approved, ready, enqueued, done, failed, refused, cancelled. |
| `constitution.py` | The 13 F-700 clauses, each naming its importable enforcers, plus `evaluate(db, action)`, which fails closed. |

## Edits outside the package (minimal)

- **`agents/registry.py` `Registry.authorize`:** after the existing checks, it calls `authority.policy.check_dispatch`. A gated class runs only in these cases:
  - the agent is declared in code for it at YELLOW or RED; or
  - an owner `AuthorityPolicy` covers it.

  It is refused in these cases:
  - the agent is GREEN without a policy;
  - the grant is a runtime DB widening ("silent authority expansion");
  - the agent is a build-plane agent;
  - the job is DEPLOY;
  - the runtime is a build runtime.

  An exception while checking a gated type refuses it.
- **`autonomy/orchestrator.py`:**
  - `_enqueue_mission` records the mission as an `enqueued` DAG node.
  - `_raise_approval` submits the protected candidate as an `awaiting_approval` node, deduplicated on the same `requirement_key`.
  - `tick()` runs `dag.tick` every tick and reports it under `report["dag"]`. A DAG error is reported in `errors.company_dag` and never stops departments.
- **`laura/core/constitution.py` `review`:** adds the company constitution check (`blocked_by` gains `"constitution"` on a violation; fails closed).
- **`improve/governance.py`:**
  - six new `PROTECTED_GATES`: publication_authority, spend_authority, credentials, legal_tax, customer_remedy, canonical_identity;
  - each has `GATE_OPERATORS = ()`, so no department may propose them;
  - `_AUTHORITY_SURFACES` adds plain-word detection of these surfaces in `implied_surfaces`;
  - `check_owner_authority` has more owner-only phrases.

## Rows

| Row | Status | Evidence |
|---|---|---|
| F-669 Progressive Authority | COMPLETE | `classes.JOB_CLASS` and `policy.check_dispatch` in `Registry.authorize` (live on every worker dispatch). Tests: `test_f669_*` (4). The worker dead-letters a DB-widened `store.publish` without running the handler. |
| F-497 Build vs Operate Separation | COMPLETE (code); token scope GATED | `plane_violations` returns `[]` for DEFAULT_AGENTS. Build-plane agents (orchestrator) are refused gated classes at authorize and at grant. DEPLOY is held by nobody. `BRAMBLELOOP_RUNTIME_ROLE=build` refuses every gated class. Tests: `test_f497_*` (2). **GATED:** a read-only build-session credential scope (GitHub/Railway token) is credential configuration, which is owner-only (`production_deploy` / credentials). |
| F-703 Earned Autonomy Ladder | COMPLETE | `policy.grant` covers these rules:<br>• owner only, with step-up and a decision id;<br>• agents and Laura are refused;<br>• one rung at a time;<br>• `MIN_SAFE` measured history;<br>• DEPLOY, LEGAL-TAX and CREDENTIALS are capped.<br>`effective_level` is shadow-first and demotes on a dead letter or incident. It is consumed by `dag.recompute` and `Registry.authorize`. Tests: `test_f703_*` (3). |
| F-658 Durable Coordinator | COMPLETE | `company_work_items` persists dependencies, priority, ownership (department, agent, submitter), authority state and completion evidence. `dag.tick` runs inside every `autonomy.orchestrate` job (15 min plus the idle wake). Tests: `test_f658_*` (2) cover the restart and the orchestrator integration. Runtime proof is below. |
| F-702 Authority gated, initiative not | COMPLETE | `awaiting_approval` node with one deduplicated OwnerAction. Independent items are dispatched on the same tick. Approved gated work does not run in SHADOW. Test: `test_f702_f721_awaiting_approval_blocks_only_dependants`. |
| F-721 Owner block does not cascade | COMPLETE | Same test, plus `test_f721_a_failed_dependency_blocks_its_branch_only`. The department-level non-cascade is already D's orchestrator, covered by existing tests. |
| F-700 Constitution | COMPLETE | `authority.constitution`. Every enforcer is imported by a test. The per-action clauses block, and the check fails closed. It is consumed by `dag.dispatch` and Laura's `review`. Tests: `test_f700_*` (3). |
| F-708 Protected Truth and Authority | COMPLETE | Governance refuses the credentials, legal/tax, customer-remedy, publication and spend authority surfaces, whether declared or implied. Tiers grade them `gate`. Test: `test_f708_*`. The live consumer is `governance.check` in improve cells/runner/league/roles/upgrades. |
| F-743 No Model Drift Through Learning | COMPLETE | `canonical_identity` is a protected surface with no operator. Prompts, routing and adapter tuning still pass. `cells.propose` refuses an identity change. Test: `test_f743_*`. |

Notes:

- The K11 audit hint asks for an "awaiting-approval job state". `JobStatus` is in `core/models.py`, which the integrator owns. The state is therefore a work-item state: protected work is never a job until it is approved. I made no JobStatus change and none is required.
- `pricing.experiment` is held by the GREEN `pricing` agent and is classified PUBLISH (a live price change). It is now refused at authorize unless the owner grants a policy. It has no handler, so nothing at runtime changes. This is a tightening, not a weakening.

## Tests

All runs used the venv interpreter with `PYTHONPATH=src`, on the final code. I did not run the full suite.

**New test file:** `test_w3_k11_authority`, 18/18 passing.

**Existing suites for the modules I touched.** All passed; the numbers are OK counts.

| Suite | OK |
|---|---|
| test_v11_autonomy_orchestrator | 14 |
| test_cert_orchestration | 20 |
| test_roles | 35 |
| test_r2_autonomy_useful_work | 6 |
| test_w3_laura_core_constitution | 7 |
| test_w3_laura_core_executive | 7 |
| test_w3_laura_core_wiring | 6 |
| test_w3_laura_core_identity | 11 |
| test_w3_laura_core_continuity | 2 |
| test_persistence | 11 |
| test_improve | 32 |
| test_improve_director | 14 |
| test_improve_handlers | 8 |
| test_cert_learning | 15 |
| test_cert_improve_autonomy | 20 |
| test_cert_improve_wave | 24 |
| test_upgrades | 25 |
| test_cert_culture_teardown | 16 |
| test_cert_wiring | 16 |
| test_v11_wiring | 14 |
| test_v11_wiring_cc | 5 |
| test_v11_cc_actions | 7 |
| test_v11_learn_loops | 18 |
| test_w3_k10_learn | 23 |
| test_r2_security_department_block | 2 |
| test_r2_product_policy_alias | 7 |
| test_platform | 22 |
| test_spend_governance | 36 |
| test_takeover | 11 |
| test_teardown_audits | 21 |
| test_cert_cost | 19 |
| test_escalation | 8 |
| test_etsy_surfaces | 53 |
| test_etsy_readback_observe | 37 |
| test_cert_growth_ops | 13 |
| test_cert_orders | 23 |
| test_dashboard_spend | 7 |
| test_w3_spend_attribution | 4 |
| test_w3_spend_hygiene | 6 |

**Guard suites:** test_vacuity 7, test_secret_scan 7, test_reachability 11 and test_w3_reachability_dynamic 3, all passing.

**Not finished:** `test_product_run` hit my 1500 s timeout because the machine was heavily loaded. It had 7 OK and 0 FAIL when it was stopped.

**Failures I did not cause:**

- `test_v11_autonomy_timeline::test_the_committed_map_matches_the_generator` fails because the committed autonomy map is stale. It records 107 cadences and 125 handlers; the live code has 111 and 129. The test fails the same way on the integrator head e7b207c. K11 adds no cadence, handler or agent.
- `test_cost_governance_wave2` has 5 failures, from another lane:
  - the audit actions `launch.assessed`, `launch.held` and `launch.planned` have no retention decision;
  - the temp prefix `bl-laura-proof-` is unregistered.

  None of these are K11 audit actions, and K11 reads no audit action by name.

## Runtime proof

`research/final_build/w3/K11_runtime_proof.py` writes `evidence/K11_runtime_proof.json`.

**Setup:**

- It runs the real `Worker` on a temporary SQLite database, phase shadow, with sockets closed.
- I ran it on the K11 working tree, with code identical to 1fd6db3. The JSON's `commit` field says 04b811b because that was HEAD at the time.
- I seeded three DAG nodes through `dag.submit`, and they are labelled as seeded:
  - `store.publish` (PUBLISH);
  - a `growth.distribution` that depends on it;
  - an independent `seo.cycle`.
- I enqueued `autonomy.orchestrate` and drained the queue.

**Run 1** (13 jobs, 0 denied, 0 failed):

| Node | State |
|---|---|
| publish | `awaiting_approval` |
| promote | `blocked`, waiting on proof:publish |
| seo | `enqueued` as jobs:13; it ran in the same drain |

**After a restart** (a new `Database` on the same file, then a second orchestrate job):

- seo is `done`, with evidence `{job_id 13, job_status done, did_no_work true, output_keys}`. `did_no_work` is reported as true: this was the first SEO cycle on an empty database.
- publish is still `awaiting_approval`, and promote is still `blocked`.
- The DAG holds mission nodes with completion evidence: 12 `done` and 11 `enqueued`.

**Totals:** 26 jobs, 0 dead, **0 `store.publish` jobs**.

**Live registry refusals:**

- `pricing:pricing.experiment`: the agent is GREEN and the job is PUBLISH.
- `orchestrator:store.publish`.
- A build runtime asking for `store_operator:store.publish`.
- A grant made by `laura`, because agents never self-grant.

This was a bounded window of about 2.5 minutes, not a soak. The approve-then-execute path in a non-shadow phase is proven in unit tests only. In shadow, an approved item stays `approved`. Nothing ran in production, by design.

## WIRING REQUESTS

1. **Integrator (`core/db.py` `create_all`):** add `from ..authority import models as _authority_models  # noqa: F401` next to the other lane imports. Until then, `authority.models.ensure_tables` creates both tables on first use.
2. **Lane F (Command Center, `app/command_center/api.py`):**
   - Add `POST /api/cc/authority/approve/{key}`, which calls `require_stepup(db, request, "authority.approve")` and then `authority.dag.approve(db, key, approved_by="owner", step_up_verified=True, approval_ref=<owner_action id>)`.
   - Add `POST /api/cc/authority/grant`, which calls `require_stepup` and then `authority.policy.grant(..., granted_by="owner", step_up_verified=True)`.
   - Add the provider entries `authority.dag.summary` and `authority.policy.summary` to `providers.py`.

   Until this lands, approvals and grants have no HTTP route. Domain APIs only.
3. **Optional, lane D / F:** Laura delegations that have real ordering could `dag.submit(..., depends_on=[...])`. Today the producers are the COO (missions and approvals) and API callers.
4. **`runtime/pipeline.py` owner:** none needed.
