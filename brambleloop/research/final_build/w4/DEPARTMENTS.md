# W-AGENTS department capability audit (owner directive 2026-10-25)

Date 2026-10-26 (UTC). Branch `claude/w4-AGENTS`. No departments were created.

**Sources.**
- Code: `agents/registry.py`, `autonomy/charters.py`, `runtime/worker.CADENCES`, `runtime/worker.handlers` (after `runtime.pipeline` is imported), `authority/classes.py`, `laura/executive/loop.py` and `laura/agency/delegation.py`.
- Production, through public read-only GETs at 2026-10-26 ~01:16Z: `/health` (build 1580053629), `/api/jobs?limit=2000` (ids 30858–32857, about 32 hours), `/api/queue/cadences` (115 cadences, `never_enqueued: []`) and `/api/departments`.
- The probe script and raw reads are in the session scratchpad; they are not committed.

**The test of "operational".** A registry entry does not count. An agent is operational only when all of these hold:
- a handler is registered for its job type;
- a cadence or chain wakes it;
- production completed it in the window;
- its output reports work done, not `ran: false`.

## Shared machinery

All of this already exists, and every department uses it:
- **Permissions:** `Registry.authorize` checks forbidden combinations, then allowed job types, then the action class (`authority/policy.check_dispatch`).
- **Spend:** the per-agent daily ceiling (`record_cost`), plus `gateway.anthropic.check_budget` before every model call and the monthly ceiling.
- **Model routing:** the provider-neutral gateway and failover. `worker.MODEL_JOB_TYPES` are parked while the provider is down.
- **Evidence:** `AuditLog`, `operating_readings` and `company_memory`.
- **Deliverable review:** the useful-work judge (`pipeline.did_no_work`); COO `autonomy.department_review` KPIs with anti-gaming guardrails; Laura's REVIEW/CHALLENGE of each mission she delegated.
- **Failure handling:**
  - lease, retry and backoff, then a dead letter (`queue.durable`);
  - `ops.queue_check` re-drives a dead letter once per deploy;
  - `improve.mine` turns dead letters into lessons;
  - write-ahead effect intents for external writes (`queue.effects`).
- **Laura's authority:**
  - she can delegate only job types that are both in the charter's `generatable` list and in `SAFE_GENERATED`, through the COO enqueue boundary and the constitution check;
  - protected types become owner cards;
  - spending, her own identity and the logo/banner are refused.

## Department table

**Columns.**
- **Handled/declared:** job types the department's agents hold that have a handler.
- **Prod done:** jobs completed in the ~32-hour window.
- **Model:** handlers that reach a model or vision provider.
- **Laura may delegate:** the charter's `generatable` list.

| Owner's department | Charter / agents (authority, CA$/day) | Handled / declared | Woken by | Model | Prod done | Laura may delegate | Verdict, and what is missing |
|---|---|---|---|---|---|---|---|
| Executive (Laura) | executive: laura (G, 0.50), coo (G, 0), orchestrator (G, 3.00), swarm_steward (G, 0.25) | 50/50 | 48 cadences; laura every 5 min, COO every 15 min | laura briefing (gateway, CA$0.50 cap) | coo 558, laura 393, orchestrator 635, swarm 102 | morning_handoff, scale.trajectory, department_review | **Operational.** Delegation is real but GREEN-only. The last `autonomy.orchestrate` enqueued 0 missions and holds approvals (`store_commerce:publication_review`). |
| Product Development | product_design: creative_director (G, 28.00), crochet_engineer (G, 4.00) | 19/20 (`cir.revise` missing) | 16 cadences; `cir.draft` only from radar promotions | 10 creative.* types | creative 20; **crochet_engineer 0** | seasonal.sentinel, outcome_learning, department_review | **Partly.** Research runs; 4 cadences were last no-ops (blinded: 1 pair; reference_reading: image_vision closed; the model tournament and pack are already done). **No CIR drafted in the window**, and a failing CIR has **no revise path** (`cir.revise`). |
| Brand & Publishing | store_commerce: **storefront_director** (G, 0; W-AGENTS) + visual: publishing (PDF/assets) | storefront 3/3 (new) | daily `storefront_review` (new) | none (deterministic) | 0 (not deployed yet) | `storefront.review` | **Built in code (b5226f7), not in production.** Proposals only; writes are held in SHADOW. |
| Growth & Marketing | growth: growth (G, 2.00), ads (Y, 1.00), experiment_steward (G, 0.25) | 11/11 (`content.draft` added) | 7 cadences | none | 13 | journey, distribution, conclude, ads_readiness | **Observes and plans; executes nothing**, correctly: there is no owned channel (`owned_surfaces`), no ad authority and no data. 64/64 experiments are `no_data`. |
| Etsy Operations | store_commerce: listing (G, 2.00), store_operator (Y, 1.00), pricing (G, 1.00) | 14/15 (`pricing.experiment` missing: protected) | 6 cadences | listing.seo | 21 (seo.cycle 15) | remerchandising, seo.cycle, storefront.review | **Reads and proposes.** store.publish and store.activate are held by phase and grant (correct). `pricing.position` did not run in the window. |
| Visual Production | visual: publishing (G, 2.00) | 10/11 (`assets.render` missing) | 4 cadences | 7 | 12 | identity_drift, visual.rnd.cycle | **No useful output.** `assets.owned_photography` ran 10 times on `market-basket-trio`, which has **no CIR** (repeated no-op); model_photography is a no-op; visual.rnd generated 0. |
| Market Intelligence | intelligence: market_radar (G, 4.00) | 14/15 (`radar.competitor_snapshot` missing) | 13 cadences | 4 | 67 (+12 pending) | radar.score, benchmark_refresh, pod_learning | **Operational for reads.** mjs.scan found 80 new listings; intel.acceptance FAIL 12/13; one mjs.scan read timed out. |
| Finance | finance: cfo (G, 1.00) | 10/10 | 9 cadences | none | 74 | reconcile, order_readings, readings, escalation, accounting cycle and period pack | **Operational.** Real authenticated receipt reads (0 receipts); books from observed entries only. |
| Customer Experience | support: support (Y, 2.00) | 2/2 (`support.reply` protected) | hourly triage | none | 32 (0 cases) | support.triage | **Correctly idle**: there are no customers. |
| Engineering & Reliability | platform + learn: orchestrator, learn (G, 0) and 8 meta-agents (G, 0.25 each) | all handled | 41+ cadences | probes only | orchestrator 635, learn 32, meta 2 each | queue_check, maturity, slo, improve.* | **Operational.** `/api/verify` and `/api/departments` answer (the departments 500 of AGENT_AUDIT is gone in production). |
| Quality & Compliance | product_truth: quality_director (G, 1.00), validator (G, 1.00), asset_truth (G, 1.00), policy (G, 1.00) | in production **8/13**; `cir.twin`, `cir.reverse`, `gate.asset_truth`, `gate.policy` and `gate.quality` have no handler | 3 cadences | gate.certify | quality_director 6; **validator, asset_truth and policy 0: they could never run** | sentinel, upgrade_impact | **Registry-only for 3 of 4 agents** (AM-10). The checks run only inside `gate.certify`; nothing re-checks a release after certification. **Fixed in batch 1.** |

## Batches

### Batch 1 (done): Quality & Compliance agents are operational

`runtime/quality_ops.py` adds handlers for:
- `gate.quality` (quality_director, daily cadence `quality_reverify`): queues one check of each kind per newest certified release, idempotent per release per day;
- `cir.twin` and `cir.reverse` (validator): compile, the twin, and the written pattern reverse-compiled in US and UK terms;
- `gate.asset_truth` (asset_truth): shape and technique claims of the title and listing copy against the twin;
- `gate.policy` (policy): `check_listing` on the drafted listing.

**AM-10 is respected.** These checks are *not* a verdict path:
- they run only on releases that are already certified;
- they never certify, revoke or block anything;
- a disagreement becomes one deduplicated **P2, non-halting** incident (regression detection).

`gate.quality` is generatable by Product Truth (SAFE_GENERATED), so Laura and the COO can delegate the sweep. `test_roles.DECLARED_BUT_UNBUILT` loses these five types, and AM-10 status is updated.

**Authorised by:**
- the Master Plan §16 Engineering roles (Validator, Digital Twin, Reverse Compiler) and Brand/Publishing roles (Asset Truth);
- §17 (Adversarial QA, Asset Truth, Policy Gate);
- F-892 (charters: an agent is only real with authority it can use);
- F-701 (autonomy is core).

### Batch 2 (done): Visual Production stops asking to photograph slugs with no CIR

Production ran `assets.owned_photography` 10 times in 32 hours on `market-basket-trio` (E-12). That slug is a retired concept with no CIR (`products.launch0.LEGACY_DUPLICATES`), so every run was a no-op.

Two enqueuers passed such slugs without checking for a CIR, and both now skip them:
- the blind-review "return to development" path (`runtime/release.py`), which records `creative.return_skipped` with the reason;
- the MJs director's photography-coverage request (`intel/mission_runtime.company_standing`).

The cadence's own picker already skipped CIR-less slugs. Test: `test_w4_departments.test_photography_is_never_requested_for_a_slug_with_no_cir`.

### Batch 3 (done): Product Development revises a failed CIR once (`cir.revise`)

**Finding: `cir.draft` has no model path.** It drafts from engineered designs, `concept_to_cir` and `creative.prototype.author`, which are all deterministic, and Master Plan §2 forbids asking a model for instructions. So `cir.revise` is deterministic too: no model, no network, CA$0, inside the crochet_engineer CA$4.00 ceiling. No stub was needed.

How it works (`runtime/engineering_ops.py`):
- `cir.compile` used to end a failing concept with "the concept dies here". It now hands the failure to the crochet engineer **once** (`MAX_REVISIONS = 1`, keyed on the CIR fingerprint).
- The engineer applies only rules that change declared geometry parameters, never the design's idea. There is one rule today:
  - `REPEAT_DIVISIBILITY`, which answers the compiler's REPEAT / COUNT_MISMATCH / UNDERRUN / OVERRUN errors on a uniform flat panel;
  - the width becomes the nearest multiple of the repeat unit, with every row, declared count and the foundation moving together;
  - the width change is recorded.
- A revision that compiles goes back through `cir.compile`, then `gate.certify`. Deterministic validation decides.
- Anything else is recorded as `cir.revise_unrepairable` with its finding codes, not guessed at.
- `cir.revise` leaves `DECLARED_BUT_UNBUILT`.

Tests: `test_w4_departments.test_a_failed_compile_is_revised_once_and_goes_back_through_the_compiler` and `test_an_unrepairable_failure_is_recorded_not_guessed`.

### Next batches (not done yet; each is authorised and bounded)

- **B4 Market Intelligence.** `radar.competitor_snapshot`: a read-only snapshot of the existing sanctioned observations. It is for demand and merchandising only and never copies instructions or images.
- **Stays unbuilt, by authority:**
  - `pricing.experiment` (PUBLISH, protected; owner authority required);
  - `assets.render` (no requirement row names a separate render job; `assets.build` covers it).
