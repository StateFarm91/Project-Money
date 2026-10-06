# Handoff — v1.1 lane B (Learn / continuous self-improvement)

Branch `claude/v11-B` (worktree `.claude/worktrees/v11-B`), based on `claude/visual-investigation`
@ 0694fb7. Not pushed. Phase stays shadow; no network, spend, Etsy, deploy or customer action.

## Requirements

| ID | Status | Notes |
|---|---|---|
| Directive §4 (loop must change future behaviour with measured evidence; never weaken protected surfaces) | **PARTIAL → COMPLETE in code, PARTIAL in production data** | Full loop observe → guarded proposal → cross-agent challenge → shadow eval vs baseline (frozen rows, holdout) → `improve.sandbox` promotion (independent evaluator, regression + adversarial tests, scoring tier) → consumer read → post-change monitor → verified rollback → persisted lesson → next cycle reads it. Proved end to end in tests on the live handlers. In production every loop is `UNMEASURED` until outcome rows exist, and the two lesson loops log no decisions until W-B1 is applied. |
| F-891 agent intelligence standard | PARTIAL | Decisions carry evidence (row ids, fingerprints, readings), uncertainty (UNMEASURED with reason, sample floors) and escalation (non-scoring tiers → owner card via existing pipeline). Deterministic by design; no model calls. |
| F-918 KPIs with anti-gaming | COMPLETE (for the 5 loops) | Each loop has metric + guardrail KPI; a win bought by losing the guardrail is blocked (`compare`/`guardrail_objections`); review-load cap stops "flag everything". Test `test_guardrail_kpi_and_cross_agent_challenge_refuse_a_gamed_win`. |
| F-919 cross-agent challenge | COMPLETE (for improvement proposals) | `policy_loops.challenge`: a specialist from another department (never the proposer) re-checks invariants, sample, margin, holdout, guardrail before the proposal enters the pipeline; CHALLENGED_OUT is persisted and remembered. |
| F-920 persistent memory of lessons | COMPLETE (for the loops) | `learn_policy_lessons` (promoted / retained / rolled_back / challenged_out / refused), `learn_proposals`, `learn_decisions`; source-linked; the next cycle reads them (`MEMORY_SKIPPED`). |
| F-922 cost-aware routing | GATED → lane I | `improve/` has only the code-mirrored routing registry (owner card, no run producer). Left to lane I as instructed. `release_cost_watch` is a cost-per-release *flag* loop, not routing. |

## Files

Created: `src/brambleloop/improve/invariants.py`, `src/brambleloop/improve/policy_loops.py`,
`src/brambleloop/learn/improvement_status.py`, `tests/test_v11_learn_loops.py`,
`research/final_build/v1_1/LEARN_LOOP_AUDIT.md`, this file,
`research/final_build/v1_1/evidence/B_runtime_proof.json`, `B_test_results.txt`,
`B_DB1_monitor_defect.txt`.

Modified: `improve/runner.py` (policy_loop trial/executor/monitor/rollback/verifier registered;
`policy_loops.cycle` runs at the start of each sandbox pass, isolated), `improve/consume.py`
(`matching` reads the promoted threshold for seo/support cells; optional `subject=` logs the
decision), `improve/monitor.py` (D-B1 fix), `learn/models.py` (3 additive tables created by the
existing `create_all`; no migration of existing tables).

## Defect fixed

**D-B1** `improve.monitor.sweep` judged trial-metric promotions in capability units and wrote
REVERTED without running the rollback executor (registry kept the challenger running). Reproduced
on base; fixed; regression test added. See `evidence/B_DB1_monitor_defect.txt`.

## Tests (python3 3.11, `PYTHONPATH=src`, from `brambleloop/`)

`python3 tests/test_v11_learn_loops.py` → **18 OK, 0 FAIL** (7 tests):
e2e SEO loop (outcomes → proposal → sandbox → promotion → next `consume.matching` decides
differently, and `release.py` calls that consumer); rollback on regression (verified at the
consumer, incident opened, lesson persisted, rolled-back value not re-proposed); 12 protected /
undeclared / out-of-bounds proposals refused + recorded + audited, executor and consumer-read
re-checks; D-B1; predictor loop (visual gate outcomes → promoted pre-check → `next_work` item);
provider contract on empty and populated DBs; anti-gaming + cross-agent challenge.

Existing suites for modules I modified (all re-run after the change): test_cert_improve_wave 24/0,
test_improve 32/0, test_improve_director 14/0, test_improve_handlers 8/0, test_cert_learning 15/0,
test_learn_launch 13/0, test_learn_input_shapes 1/0, test_learn_publish_contract 3/0,
test_learning 18/0, test_outcome_learning 5/0, test_roles 35/0, test_swarm_runtime 10/0,
test_cert_improve_autonomy 18/2 — the 2 are `ModuleNotFoundError: numpy`, identical on base (no
interpreter here has both numpy and sqlalchemy). test_vacuity 6/1 and test_secret_scan 5/1: the
remaining findings are in files I did not touch (unchanged since 0694fb7) and pass on the current
base cddf7d1 (repaired upstream by rc1-INT); my test file is not among them.

## Runtime proof

`evidence/B_runtime_proof.json` — executed the registered `improve.sandbox` and `improve.monitor`
handlers on a scratch SQLite DB: empty provider → `UNKNOWN` with reason; code default
`min_shared=2` applies a 2-word lesson; after seeding 24 decisions + listing outcomes the sandbox
promoted `min_shared=3` (config v2), and the same 2-word decision no longer applies; 8 regressing
post-promotion outcomes → monitor rolled back to v1, verified, the 2-word match applies again; a
`daily_cost_ceiling_cad` proposal → REFUSED; provider → `DEGRADED` "4 of 5 loops UNMEASURED".

## Provider contracts

`brambleloop.learn.improvement_status.summary(db) -> dict` — `status` ∈ OK/DEGRADED/BLOCKED/UNKNOWN,
`reason`, `as_of` (UTC ISO or null), `basis` ("measured"|"unknown"), `items` (one per loop: active
value + source, reading MEASURED/UNMEASURED + why, decisions logged/with outcome, last evaluation
with baseline/result/basis, proposals by state, promotions, rollbacks, refusals, consumer +
status), `pipeline` (improvements by trial and state, rollback_pending), `lessons`, `guardrail`,
`sources`. Never raises (unreadable → UNKNOWN with reason).

`brambleloop.learn.improvement_status.next_work(db) -> list[dict]` — read-only, never raises,
sorted by priority desc. Each item: `kind`, `key` (stable idempotency key), `priority` (int 1–100,
higher = more urgent), `reason`, `evidence` (row ids/values), `department: "learn"`, `job_type`
(an existing registered handler — `improve.sandbox` / `improve.monitor` — or null for a review
item). Kinds: `learn.complete_rollback` 90, `learn.monitor_promotion` 75,
`learn.sandbox_proposal` 70, `finance.cost_review` 65, `quality.extra_review` 60,
`visual.precheck` 55, `learn.evaluate_loop` 50, `learn.lesson_gap` 40 (+20 if the topic is on
the defect watchlist), `learn.instrument_loop` 20, `learn.provider_error` 10.

## WIRING REQUESTS (shared file `runtime/release.py`, not owned by lane B)

**W-B1 (needed for the SEO and support loops to collect production decisions):**
- `runtime/release.py` ~L909 (in `handle_listing_seo`):
  `consume.matching(ctx.db, "seo_search", listing_text)` →
  `consume.matching(ctx.db, "seo_search", listing_text, subject=slug)`
- `runtime/release.py` ~L2225 (support.mine loop `for case_id, question, have in cases:`):
  `consume.matching(ctx.db, "customer_experience", question, min_shared=1)` →
  `consume.matching(ctx.db, "customer_experience", question, min_shared=1, subject=f"support_case:{case_id}")`

**W-B3 (optional, tightening only):** where the release gate assembles a release's QA obligations,
add `from ..improve.policy_loops import requires_extra_review` and, when
`requires_extra_review(ctx.db, cir)["extra_review"]`, add an extra-review obligation. Never use it
to skip any existing check.

**W-B4 (optional, tightening only):** in the render path, read `policy_loops.visual_precheck(db)["groups"]`
and route an asset of a listed `asset_class/role` group to the existing pre-gate inspection first.

No cadence/agent/band edit is required: the loops run inside the already scheduled
`improve.sandbox` and `improve.monitor` jobs.

## Not verified / open

- No production data exists in shadow, so no loop has a production measurement; the provider says so.
- Market Radar and Pattern Engineering lesson nudges remain unmeasured open loops; counterfactual-rollback
  promotions still execute nothing (see audit).
- The replay estimator is biased when coverage is thin; mitigated by sample floors and the holdout,
  not eliminated. Labelled as such in `basis`.
- Scoring-tier cooldown (6 h) is shared with the job-priority replay, and only one policy-loop proposal is
  in flight at a time (by design, so loops never contend for the `score` surface in the Director).
