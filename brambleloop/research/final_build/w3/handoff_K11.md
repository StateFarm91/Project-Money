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

(counts filled in below)

## Runtime proof

`research/final_build/w3/K11_runtime_proof.py` writes `evidence/K11_runtime_proof.json` (see the results section below).

## WIRING REQUESTS

1. **Integrator (`core/db.py` `create_all`):** add `from ..authority import models as _authority_models  # noqa: F401` next to the other lane imports. Until then, `authority.models.ensure_tables` creates both tables on first use.
2. **Lane F (Command Center, `app/command_center/api.py`):**
   - Add `POST /api/cc/authority/approve/{key}`, which calls `require_stepup(db, request, "authority.approve")` and then `authority.dag.approve(db, key, approved_by="owner", step_up_verified=True, approval_ref=<owner_action id>)`.
   - Add `POST /api/cc/authority/grant`, which calls `require_stepup` and then `authority.policy.grant(..., granted_by="owner", step_up_verified=True)`.
   - Add the provider entries `authority.dag.summary` and `authority.policy.summary` to `providers.py`.

   Until this lands, approvals and grants have no HTTP route. Domain APIs only.
3. **Optional, lane D / F:** Laura delegations that have real ordering could `dag.submit(..., depends_on=[...])`. Today the producers are the COO (missions and approvals) and API callers.
4. **`runtime/pipeline.py` owner:** none needed.
