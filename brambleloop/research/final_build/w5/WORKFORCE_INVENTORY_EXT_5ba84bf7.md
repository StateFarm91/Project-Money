# Workforce inventory: extension of P0_WIRING_50937469

- **Tree:** `/home/user/bl-runs/wt-b5cert` @ `5ba84bf7` (Batch 5 candidate). This was a read-only trace. No tests were run, no git state was changed, and no file was written inside the tree. `git status --porcelain` stayed clean.
- **Production:** `0967c3ee` on Railway in SHADOW.
- **Base document:** `origin/claude/w4-INTEG8-next:brambleloop/research/final_build/w5/P0_WIRING_50937469.md` (25 handoffs; 16 departments × 12 criteria). This file **extends** it:
  - (a) new department rows 17–31, in the same matrix format;
  - (b) all 171 job types, with handler, producer and status;
  - (c) new gaps not covered by A1–A9, Codex P0-LEARNING-REFERENCE or the visual-production audit.
- **Paths:** relative to `brambleloop/src/brambleloop/` unless stated otherwise.
- **Method:**
  - The handler registry was read by importing `app.runner` with bytecode writes disabled (`python -B`, cwd = scratchpad), then calling `HandlerRegistry.known()` and `inspect` for file:line.
  - `JOB_BANDS`, `JOB_CLASS`, `worker.CADENCES` and `autonomy.charters.department_of` were read the same way.
  - Producers were found with a regex over every `enqueue(<agent>, "<job_type>"` call site in `src/`. Each non-cadence producer was then traced by hand to its enclosing handler or route.
- **Production evidence in the repo:**
  - Source: `brambleloop/research/final_build/w4/evidence_BOARD/prod_readback_0967c3eee287_20261102T0331Z.json` (2026-11-02T03:31Z).
  - PASS:
    - worker alive;
    - shadow holds;
    - nothing published;
    - publication refusals recorded;
    - no unexpected dead letters;
    - every agent has a cost ceiling;
    - smoke matrix (probes, continuity, cadences, queue, search).
  - NEEDS_OPERATOR: department health, swarm runtime, funding packets, offsite archive, continuity proof, Etsy credential.
  - There are no per-job-type production rows. Prod is therefore **U** unless one of those PASS lines covers the row.

## Spec architecture (Master Plan v1.2, extracted with `pdftotext`)

The spec PDF extracted cleanly.

§16 "Full Agent Organization" and the addenda require these groups:

- **Executive:** CEO/Orchestrator, CFO/Skeptic, Policy, Quality Director.
- **Intelligence:** competitor, category, trend, seasonality, keyword/search.
  - §4 adds Discovery, Digital Twin Builder, Change Detector, Review Miner, White-Space, Category Analyst, Trend Forecaster and Seasonality Engine.
- **Creative:** Creative Director, Collection Architect, category specialists.
- **Engineering:** Crochet Engineer, CIR Compiler, Validator, Digital Twin, Reverse Compiler, Adversarial Reviewer, Gauge/Yardage, Test Coordinator.
- **Brand/Publishing:** Storefront Director, Brand Model Consistency, PDF/Charts, Visual Director, Asset Truth, Listing, Thumbnail Warfare, Etsy SEO.
- **Commercial/Growth:** Pricing, Promotion, Bundles, Revenue, Store Operator, Portfolio, Search Domination, Launch Velocity, Growth, Pinterest, Etsy Ads, Social, Email, SEO, Video, Attribution.
  - §9 adds Market Price Scanner, Price Experiment Agent, Bundle Economist and Revenue Optimizer.
  - §11 adds Pinterest Organic/Paid, Creative Testing and Creator/Partnership Research.
- **Customer Experience:** Concierge, Download, Crochet Help, Materials, Troubleshooter, Happiness, Incident, Review Intelligence.
- **Operations:** Scheduler, Queue, Integration Health, Cost, Backup/Recovery, Owner Action Queue.
- **Addenda:**
  - §27 Model Gateway (failover, eval fixtures before model upgrades);
  - §28 Security, Privacy and DR (least privilege, restore drill, incident playbooks for leaked credentials, compromised integrations and unauthorized ad spend);
  - §29 IP/Originality Agent;
  - §30 Owned Audience (CASL consent);
  - §31 Localization/Accessibility;
  - §34 Cost-to-create metrics.
- **§32 acceptance tests that bear on the new rows:** model-provider failover; support incident creation; "a repeated customer defect simulation … creates a correlated incident"; ad-budget breach prevention; backup and restore.

The code models **11 charters** (`autonomy/charters.py:181-427`): executive, intelligence, product_design, product_truth, visual, store_commerce, support, finance, growth, learn, platform. The 31 matrix departments below map onto them, and the column in the job table says which.

## Job-type closure: summary

| Check | Result |
|---|---|
| `JOB_BANDS` (`swarm/orchestrate.py:707`) | 171 |
| `JOB_CLASS` (`authority/classes.py:53`) | 171 |
| In BANDS but not CLASS | **none** |
| In CLASS but not BANDS | **none** |
| Handlers registered via `app.runner` import | 169. Also importing `autonomy.handlers`, `laura.executive.handlers`, `autonomy.visual_rnd_job` and `autonomy.period_packs` adds none, because the runner already loads them |
| Handler with no band or class | none |
| Banded and classed with **no handler** | `assets.render`, `pricing.experiment` |
| Job types on a `worker.CADENCES` entry | 130 (137 cadence rows, including 8 `role_*` → `improve.role_work`) |

**Status counts (171):**

| Status | Count | Notes |
|---|---|---|
| LIVE | **159** | Handler plus an automatic producer (cadence or upstream handler) |
| … of which gated | 6 | The automatic producer exists, but the handler refuses or holds in SHADOW or behind a closed gate: `store.publish`, `store.activate`, `store.update`, `ads.campaign`, `support.reply` (drafts only), `visual.image_production` (`image_generation` gate) |
| … of which boot-once | 1 | `creative.photoreal_calibration`, enqueued at boot when none is recorded (`app/main.py:549`). It has no cadence |
| MANUAL | **8** | `physical.record`, `physical.photo`, `assets.physical_upgrade` (only chained from `physical.photo`), `assets.launch_review`, `visual.controlled_experiment` (owner routes); `creative.model_freeze`, `visual.portrait_repair`, `visual.provider_trial` (boot-once, conditioned on an owner approval) |
| ORPHAN | **2** | `cir.reengineer`, `research.flag_architecture` |
| UNHANDLED | **2** | `assets.render`, `pricing.experiment` |
| TEST-ONLY | **0** | No banded type is exercised only by tests. Note that `cir.reengineer` and `research.flag_architecture` are enqueued directly by tests (`tests/test_w4_c07_product_dev.py`, `tests/test_w4_research_agent.py`); in production they are ORPHAN |

What LIVE does and does not mean:

- **LIVE means "something automatic enqueues it".** It does **not** mean the handler produces meaningful output in SHADOW. Many LIVE cadences report UNMEASURED with no input, for example `listing.outcomes`, `commerce.*`, `portfolio.review` classification and `creative.family_engine` amplify. The base matrix records those.
- **Production execution of any of them is U.** The only exception is the readback's "smoke matrix … cadences PASS", which is aggregate and not per job type.

---

## (a) New department rows 17–31 (same 12 criteria)

**Values:** Y, P (partial), N, U (unknown). U never counts as a pass. Prod is U unless the 2026-11-02 readback covers the row.

| # | Department | Impl | Trig | Up | Down | Dur | Idem | Fail | Bud/Sec | Truth | Out | Prod | NoC | Single biggest missing link |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 17 | Finance: budget and spend governance (CFO/Skeptic) | Y: `finance.reconcile` `runtime/pipeline.py:3179`; `finance.challenge` `:3206`; `finance.escalation_check` `:3239`; `finance.governor` `runtime/release.py:7079`; reservations `finance/reservations.py:72`; `spend_plan.guard` `visual/spend_plan.py:71`; accounting cycle `finance/accounting/job.py:17` | Y: cadences `worker.py:612,662,715,1025,1034` | P: model spend is from gateway `CostEntry` (`gateway/model_gateway.py:521`, `gateway/routing.py:459`). Infra cost is *declared*, not billed (`pipeline.py:3219-3221`). No provider billing API is read (`finance/spend_hygiene.py:158-175`). The Etsy ledger mapping is UNVERIFIED (`finance/reconcile.py:25-31`) | Y: governor pauses an agent via a reservation hold, plus an incident (`release.py:7081-7087`); escalation becomes an owner action at 80% | Y: `cost_entries`, `spend_reservations`, `PortfolioReview` | P: escalation is keyed per month. `finance.challenge` is enqueued with `idempotency_key=None` (`pipeline.py:3202`), so a retried reconcile duplicates it | Y: unmeasurable readings act on nothing and say why (`finance/governor.py` docstring) | Y: per-agent `daily_cost_ceiling_cad` (`agents/registry.py`), dispatch check (`agents/registry.py:583`). Readback: "every agent has a cost ceiling" PASS | Y: "UNKNOWN is never 0" (`charters.py:340`) | P: P&L is zero-revenue in SHADOW | P (readback: cost ceilings) | Y | Provider-billed spend is never reconciled to the internal ledger (owner-reported facts only, `spend_hygiene.py:162`). Ceilings bind on estimates |
| 18 | Security: authority, secrets and credentials | Y: `authority/classes.py:53` (fail-closed classing), `authority/policy.py:292` `check_dispatch`, `ops/log_secret_guard.py:90`, `ops/credential_register.py:42-153`, `ops.provider_credentials` (`release.py:9722`), `etsy.credential_health` (`etsy_ops.py:878`) | Y: dispatch check on every job (`agents/registry.py:583`); cadences `worker.py:739,944` | Y | **N**: `SecretLogGuard` redacts and counts in-process, but `summary()` (`log_secret_guard.py:143`) has **no consumer**. A caught secret never becomes an incident, an owner rotation action or a SecurityEvent | P: `credential_register.REGISTER` is a static code tuple, not DB state | Y | P: permission failures are not retried (`worker.py:~404`) | Y: phase gate (`worker.py:150-166`), protected classes. Readback: shadow holds and nothing published (PASS) | Y | P | P (readback: shadow/publish) | Y | A secret caught in logs is invisible: there is no incident and no rotation request (spec §28 leaked-credential playbook) |
| 19 | Operations: reliability, sentinel, truth sweep, continuity | Y: `ops.heartbeat` `pipeline.py:2649`, `ops.health` `release.py:7158`, `ops.sentinel` `:7318`, `ops.continuity` `:3759`, `ops.offsite_archive` `:8413`, `ops.retention` `:8356`, `ops.dependencies` `:7530`, `ops.slo` `v11_wiring.py:25`, `ops/truth.py:315` | Y: `worker.py:607,742,747,882,886,927,931,1029` | Y | P: `ops.health` "repairs nothing itself" by design (`release.py:7166`). `ops/flow_health.py` STALLED/LOOPING is read only by `app/command_center/production.py` and `products/production_inventory.py` | Y | Y | Y: escalation waits for persistence; per-commit dead-letter re-drive | Y: never deploys (`charters.py:406`) | Y | Y | P (readback: worker alive, smoke incl. continuity/cadences PASS; continuity proof and offsite NEEDS_OPERATOR) | Y | A stalled or looping product (flow_health) produces no incident, re-drive or named hold. Only `ops.thrash` acts, and only on identical calls |
| 20 | Executive: Laura and COO mission generation | Y: `autonomy.orchestrate` `autonomy/handlers.py:36`; `laura.executive_tick` `laura/executive/handlers.py:37`; generators `autonomy/generators.py:150-437`; `plan.cycle` `pipeline.py:3011` | Y: 900 s (`worker.py:1011`), 300 s (`worker.py:1015`), daily | P: reads KPIs, incidents, dead letters and 7 provider summaries (`laura/executive/loop.py:51-74`). **No product-flow provider** (flow_health / production_inventory) | P: missions are restricted to the charter `generatable` allowlist (`charters.py:192-404`). It reviews and measures, and never re-drives a product | Y: `company_memory` | Y: mission keys per window | Y: KPI VOID guardrails (`charters.py:155-170`) | Y: protected types are never generatable (`charters.py:446-452`) | Y | P | U (readback: `/api/departments` NEEDS_OPERATOR) | Y | Laura and the COO cannot see or act on stalled products. The product chain is absent from `PROVIDERS` |
| 21 | Owner queue and approvals (Command Center) | Y: `ops/owner_queue.py:129-430`, dedupe and guard, `app/command_center/approvals.py:579` `execute`, `/api/owner/decision` (`app/main.py:1436`) | P: `owner_queue.sweep` runs inside `ops/truth.py:315`; approvals are owner clicks (by design) | Y | **P**: publication, activation, storefront, improvement, challenger, ads limit, launch decisions and adoptions are dispatched (`approvals.py:604-760`). Any other decided card has **no consumer**. `creative.reengineer:owner_choice` (`engineering_ops.py:251-280`) cannot be decided by any route and nothing enqueues `cir.reengineer` | Y | Y: one row per `requirement_key` (`owner_queue.ensure`) | Y: expiry, supersede | Y: ops-token auth (`main.py:1449`) | Y | Y | U | P: owner only | Owner decisions are not generically dispatched back into the queue (cir.reengineer is ORPHAN). External owner notification is in-app only, by design: a GATED item (`app/command_center/notifications.py:28-30`) |
| 22 | Customer support / CX | Y: `support.triage` `release.py:2536`, `support.reply` `release.py:2423`, `support/department.py:283-403`, `support/response_watch.py:135` | Y: hourly (`worker.py:663`) | **N**: cases are owner-recorded only (`response_watch.py:135`, `tabs.py:1075`). There is no Etsy messages integration | P: reply drafts, never sent (`release.py:2430-2432`). **Defect hotspots ≥3 write only an audit row `support.defect_candidate`** (`release.py:2608-2611`): no incident, no QA re-run, no withholding | Y: `support_cases` | Y: reply keyed on the case | Y: 24 h and 36 h response clock to owner action (`release.py:2556-2560`) | Y: CUSTOMER-REMEDY gated, CASL | Y: "answers cite the version" | P | U | Y | A repeated row defect does not create a correlated incident or feed the correction loop (spec §10; §32 acceptance test) |
| 23 | Physical sampling and testers (Test Coordinator) | P: `physical.record` `release.py:2963`, `physical.photo` `:3584`, `assets.physical_upgrade` `:3594`, `physical.upgrade_impact` `:3710`; `quality/tester_kit.py`, `quality/testers.py` | **N** for intake: owner upload routes only (`app/main.py:5285,5301`). `physical.upgrade_impact` is daily (`worker.py:806`) | P: Risk C is excluded at score (`pipeline.py:431`). The certificate requires a full make for effective class C (`gates/certificate.py:365-366`) | P: record → `assets.build` (`release.py:3142`); photo → physical upgrade (`:3575`) | Y | Y | Y: refuses partial attestations, routes to the owner (`release.py:3532`) | Y: kit cost CA$66 owner card (`ops/owner_queue.py:552-554`) | Y | P | U | P: needs a physical action (owner) | `physical_test_required` on a certificate raises no per-product tester request. The tester kit is hard-wired to one build, `BUILD_KEY="basket_small"` (`quality/tester_kit.py:36`) |
| 24 | Seasonal and planning | Y: `seasonal.engine` `release.py:7611`, `seasonal.sentinel` `:3835`, `seasonal.remerchandising` `:6397`, `seasonal.harvest` `:7139`, `mjs.seasonal_sentinel` `:4419`, `plan.strategy` `pipeline.py:3300` | Y: daily (`worker.py:692,778,863,646,800`) | P: occasions are scored only when every factor is observed ("none today", `release.py:7615-7617`) | P: uncovered MJs-derived seasonal events → `creative.tournament` via `mjs.seasonal_sentinel` (`release.py:4459`); breakouts → tournament (`:7656`). `seasonal.sentinel` itself only recomputes launch dates (`release.py:3835-3846`). The tournament is vision-gated (base #6) | Y: `operating_readings` `seasonal.daily` | Y: per event/ISO week keys | Y | Y: CA$0 | Y | P | U | Y | Concept supply for an upcoming window depends entirely on the vision-gated tournament (base #6). There is no deterministic fallback brief |
| 25 | Paid media (Etsy Ads / Pinterest Paid) | Y: `ads.adjust` `growth_ops.py:479`, `ads.campaign` `:536`, `marketing.ads_readiness` `v11_wiring.py:35`, `commerce/paid_media.py` | Y: daily (`worker.py:684,1037`) | P: no outcomes in SHADOW | N (by design): "no ad integration exists to spend through" (`growth_ops.py:545-546`) | Y | Y | Y: terminal refusal while `ad_authority` is closed (`growth_ops.py:551-556`) | Y: owner caps, `paid_media.authorise_spend`, SPEND class | Y | P: plan only | U | Y | Owner-gated: no ad authority and no channel adapter. **Not a code P0 in SHADOW** |
| 26 | Storefront and brand (Storefront Director) | Y: `storefront.review` `storefront_ops.py:32`, `content.draft` `:66`, `store.update` `:161`, `store_foundation/*` | Y: daily (`worker.py:952`); Laura provider (`loop.py:61`) | Y | P: text gaps → `content.draft` → `store.update` (held in SHADOW, `storefront_ops.py:195`). **`asset_health` fix routes are stored as a reading only** (`storefront_ops.py:46`, no consumer) | Y | Y: digest keys (`:49-52`) | Y: UNKNOWN on an unreadable health | Y: owner storefront authority | Y | P | U | Y | Brand/listing asset findings routed "to Brand/Visual" (`store_foundation/asset_health.py:4`) never become jobs |
| 27 | Model governance and gateway | Y: `model.probe` `release.py:3725`, `gateway/failover.py`, `gateway/fallback_contract.py`, `gateway/evals.py`, `visual.model_ledger`, `creative.model_freeze`; parking `worker.py:199-260` | Y: `model.probe` cadence (`worker.py:736`) and boot (`app/main.py:430`) | Y | **P**: a cross-provider fallback is routed only on a contract PASS (`fallback_contract.py:14-19`). PASS needs `gateway.contract_eval` rows. Their only writer is `failover_drill` (`:257`), **which no production code calls**. `gateway/evals.py` fixtures are never run by a job | Y: audit rows | Y | P: parks model jobs ≤ 24 h, then the handler refuses honestly | Y: paid-call fencing (`gateway/paid_calls.py:313`) | Y: deterministic validation independent of models | P | U | Y | Cross-provider failover can never be qualified in production, so an Anthropic outage parks all model work (spec §27, §32 failover test) |
| 28 | Compliance: policy, IP and CASL | Y: `gate.policy` (`quality_ops.py:191`), `ops.policy_watch` (`release.py:5373`), `etsy.openapi_reverify` (`etsy_ops.py:1644`), originality refusal (`pipeline.py:937`), `publish/release_gates.py`; CASL guards in `growth/owned.py` and `notifications.py` | Y: `worker.py:823,1003`; `gate.policy` via daily re-verify | Y: sanctioned Help Center API only | P: a material policy change → incident and owner review (`release.py:5480-5512`). Affected releases are re-verified only on the next daily `quality_reverify` | Y | Y: incident per source, opened once | Y | Y: nothing is sent externally (CASL) | Y | Y | U | Y | No immediate re-verification of certified releases when a policy reading changes (≤ 24 h lag). Name/IP clearance belongs to A2 |
| 29 | Pricing intelligence and promotions | P: `pricing.position` (`release.py:715`, wrapped at `:9770`), `commerce/elasticity.py`, `commerce/promotion.py`, `commerce/pricing_intel.py` | Y: chained from `assets.build` (`release.py:619`), reprice on plan drift (`:5146`) | P: no conversion data in SHADOW | P: → `listing.seo` (`release.py:812`). **`pricing.experiment` is banded, classed PUBLISH and has no handler** | Y | Y | Y: pricing refusal → owner (`chain_successors.py:115-138`) | Y: live price change is PUBLISH | Y | P | U | Y | `pricing.experiment` is UNHANDLED. The spec's Price Experiment and Promotion agents have no runnable job |
| 30 | SEO and search visibility | Y: `listing.seo` (`release.py:973`), `seo.cycle` (`seo/handler.py:14`), `listing.taxonomy_refresh` (`release.py:1523`) → `taxonomy_drift.after_refresh` → `listing.seo` rebuild (`integrations/taxonomy_drift.py:282`), search-visibility watch/aging (`storefront_watch.py:102`, `c12_ops.py:34`) | Y: `worker.py:674,677,995,1031` | P: Etsy recommendations come only from owner dashboard exports (`etsy.dashboard_harvest` `c12_ops.py:67`) | Y | Y | Y | Y | Y | Y | Y | U | Y | No automated search-performance input in SHADOW (owner exports only). Wired otherwise |
| 31 | Portfolio and product mortality | Y: `portfolio.review` (`pipeline.py:3025`), `growth/portfolio.py` ladders, `commerce/offers.may_retire` | Y: weekly (`worker.py:611`) | P: classification is NO_EVIDENCE until outcomes exist | **P**: only "missing from portfolio" → `radar.score` (`pipeline.py:3165-3168`). STAR / SEO_PROBLEM / CONVERSION_PROBLEM / QUALITY_PROBLEM / REWORK / RETIRE are stored as **text actions** in `PortfolioReview` (`pipeline.py:3142-3146`). No job is enqueued | Y | Y | Y: offer-guard refuses discard | Y | Y | P | U | Y | Classifications never become work (an SEO rebuild, QA re-verify, correction or owner retire card). Input is dormant in SHADOW |

### Corrections and extensions to existing rows 1–16

- **Row 3 (Product Development).**
  - `cir.reengineer` is ORPHAN. Its owner card (`engineering_ops.py:251-280`) has no decision route, so the "owner card only" path in base #13 cannot run either.
- **Row 2 (Research).**
  - `research.flag_architecture` is ORPHAN: `intel/research_agent.py:534` has no caller.
  - `research.investigate` is LIVE via `research.sweep` (`intel_ops.py:246`).
- **Row 15 (Orchestration).**
  - Two banded and classed types have no handler: `assets.render` and `pricing.experiment`.
  - A test asserts every *handler* is banded, but nothing asserts every *banded type* has a handler or producer.
  - Five cadence-less boot-once jobs (`app/main.py:351-549`) run only when the container restarts after the owner condition becomes true.
- **Row 16 (Command Center).**
  - The stall finding is confirmed: `ops/flow_health.py` has exactly two consumers, both read-only (`app/command_center/production.py`, `products/production_inventory.py`).

---

## (c) New gaps not covered by A1–A9, P0-LEARNING-REFERENCE or the visual audit

**Excluded as already assigned:**

- A1 child safety; A2 name/object (IP names); A3 photo asset review.
- A4 research → new concept, plus enrichment and re-draft.
- A5 correction loop after certify, quality or assets.
- A6 learning → design; A7 POOL supply stall; A8 culture → ideation; A9 event-driven listing package.
- Codex P0-LEARNING-REFERENCE.
- All FLUX, gallery and vision work (the visual audit).

**Priority:**

- **1** = safety or correctness.
- **2** = a missing autonomous connection or operational dependency for unattended 24/7 running.
- **5** = enhancement.

**Acceptance tests:** every test uses a real SQLite file DB, a real `DurableQueue`, the registered handlers and `Worker.tick()` plus repeated `run_once()`. No mocks.

| ID | Pri | Department | Exact missing function | Build on (file:line) | Acceptance test | Depends on |
|---|---|---|---|---|---|---|
| **P0-SUPPORT-DEFECT-INCIDENT** | 1 | Customer Support → Product Truth | A support row hotspot (≥ N distinct cases citing the same slug@version row) must open a correlated P1 incident (`support.defect:<slug>:<version>:<row>`). It must also enqueue a deterministic re-verify of that release (`cir.twin` / `cir.reverse` with the cited row), and withhold publication of that release until the re-verify passes or the owner dismisses it. Today it writes only an audit row | `runtime/release.py:2608-2611` (the audit-only branch); `support/department.py:283-325` `mine_cases`; withholding as in `runtime/quality_ops.py:165-211`; incident lifecycle `ops/incident_lifecycle.py` | 1. Seed a certified release and three owner-recorded `SupportCase` rows citing row 12 (via `response_watch` intake). 2. Run `support_triage`. 3. Assert one open incident with that signature, one `cir.twin` job keyed on slug@version, and a withholding row. 4. A second triage adds nothing. 5. A fourth case updates the incident without opening a duplicate. Mirrors spec §32 "repeated customer defect simulation" | A5 (consumes the incident as a correction trigger) |
| **P0-SECRET-LEAK-ESCALATE** | 1 | Security | A secret caught by `SecretLogGuard` must persist a durable `SecurityEvent` / incident (fingerprint only, never the value). It must open one owner rotation action per fingerprint through `credential_register` and mark the matching credential `rotation_required`. Today `summary()` has no consumer and the counts die with the process | `ops/log_secret_guard.py:90-152` (`SecretLogGuard`, `summary`); `ops/credential_register.py:36-153`; `app/command_center/notifications.py` `SecurityEvent` (critical always surfaces); `ops.health` `runtime/release.py:7158` as the cadence reader | 1. Install the guard in-process. 2. Run a test handler that logs a string matching an Anthropic key pattern. 3. Run `infra_heartbeat` / `health_sweep`. 4. Assert one incident or `SecurityEvent` with the fingerprint, no raw value in any DB row, and one owner action. 5. A repeat log of the same secret adds none | none |
| **P0-FLOW-STALL-ACT** | 2 | Operations / Executive / Command Center | A scheduled `ops.flow_watch` (or an extension of `ops.sentinel`) that reads `ops/flow_health` STALLED / LOOPING per product. For each one it must (a) open one incident keyed on slug and state, (b) enqueue the bounded re-drive that fits the stage (`chain.rebuild` for that slug, or `chain.successors`), or write a named hold after N attempts, and (c) appear as a Laura `PROVIDERS` entry so the COO prioritises it. Today the stall is display-only | `ops/flow_health.py:67,90-177`; `products/production_inventory.py:56-70,605-640`; `laura/executive/loop.py:51-74` (`PROVIDERS`); `runtime/release.py:4898` `chain.rebuild` | 1. Seed a release whose last job (`listing.draft`) is DONE and whose successor never ran, with the clock advanced past the stall threshold. 2. `tick` and run. 3. Assert one incident, one re-drive job with a deterministic key and a Laura priority row. 4. With the re-drive failing N times, assert a named hold and no further jobs after more ticks. Distinct from A7, which is concept supply and not in-flight products | none (complements A5 and A7) |
| **P0-OWNER-DECISION-DISPATCH** | 2 | Owner Queue / Product Development | A decision route for `creative.reengineer:owner_choice` (the slug choice), plus a dispatcher that enqueues `cir.reengineer` with `owner_action_id` and the chosen `slugs` when the card is decided. Generalise this as a registry `requirement_key → job_type` so a decided card resumes its work. Today `cir.reengineer` is ORPHAN and the card is undecidable | `runtime/engineering_ops.py:251-316` (`reengineer_card`, handler); `app/command_center/approvals.py:579-780` `execute`; `ops/owner_queue.py:129-170` `transition` / `close` | 1. Run `creative.salvage_review` to raise the card. 2. POST the decision with one slug (ops-auth). 3. `run_once` until idle. 4. Assert `cir.reengineer` ran, then `cir.compile`, then `gate.certify` for that slug. 5. A second POST is refused or idempotent | none |
| **P0-JOBTYPE-CLOSURE** | 2 | Orchestration | Close the inventory. (a) `pricing.experiment`: implement a handler that refuses in SHADOW and requires owner PUBLISH authority, or remove it from `JOB_BANDS`, `JOB_CLASS`, the agent allowlists and the Laura delegation map. (b) `assets.render`: remove it, or alias it to `assets.build`. (c) `research.flag_architecture`: wire `request_architecture_review` from `research.investigate` when a finding contradicts a recorded assumption, or retire it. (d) Add a coverage test: every `JOB_BANDS` key has a registered handler and is either on a cadence, enqueued by a registered handler, or on an explicit `MANUAL_JOB_TYPES` allowlist | `swarm/orchestrate.py:707-924`; `authority/classes.py:53-117`; `agents/registry.py:204,276,383,811,896,991`; `laura/agency/delegation.py:60-71`; `intel/research_agent.py:534-540`; `runtime/intel_ops.py:190-262` | Real-registry test: import `app.runner` and assert `set(JOB_BANDS) == set(handlers.known())` and that each type is in `CADENCES ∪ producers ∪ MANUAL_JOB_TYPES`. If `pricing.experiment` is kept: enqueue it in SHADOW and assert a named refusal, not a dead letter "no handler" | none |
| **P0-FAILOVER-DRILL** | 2 | Model governance | A bounded, budgeted `model.failover_drill` cadence that runs `fallback_contract.failover_drill` on the golden items for each gate tier against the configured second provider, inside the agent ceiling. It records `gateway.contract_eval` / `gateway.contract_latency` so `failover.decide` can route a qualified fallback. It runs `gateway/evals.py` fixtures as part of the drill. Today nothing in production writes those rows, so a cross-provider fallback is permanently UNKNOWN | `gateway/fallback_contract.py:84-129,214-320`; `gateway/failover.py`; `gateway/evals.py`; `model.probe` `runtime/release.py:3725`; parking `runtime/worker.py:199-260` | 1. With a fake second-provider client injected at the gateway's provider seam (no network), run the drill job. 2. Assert ≥ `MIN_EVAL_SAMPLES` contract-eval rows and a PASS verdict. 3. Mark Anthropic DOWN in failover health and run a model job. 4. Assert it routed to the fallback and was not parked. 5. With the budget at its ceiling, assert the drill refuses by name | Owner: second-provider credential and spend approval if it is not already held (Venice key exists per `gateway/venice.py`; whether it is usable is UNKNOWN) |
| **P0-PHYSICAL-TEST-REQUEST** | 2 | Physical sampling | When a certificate is `physical_test_required` (effective risk C) without a bound full make, raise one per-product owner action. It must carry the exact sample spec (the yarn, hook and size from CIR, a kit built for that slug, maximum cost, minutes) and state the consequence (the release stays withheld). Today the kit builder is fixed to `BUILD_KEY="basket_small"` and nothing is raised per product | `gates/certificate.py:365-395`; `quality/tester_kit.py:36,313-460`; `ops/owner_queue.py:330-347,552-558`; `ops/publication_authority.py:166-168` | 1. Certify a class-C CIR via `cir.compile` → `gate.certify`. 2. Assert one `OwnerAction` keyed `physical.sample:<slug>@<version>` whose kit payload hash matches the CIR, and publication authority shows `required_not_passed`. 3. A recertify of the same version adds none. 4. A `physical.record` intake closes it | A3 (photo review closes the loop after the make) |
| **P0-PORTFOLIO-ACT** | 2 | Portfolio / Commercial Intelligence | Turn `portfolio.review` classifications into bounded jobs. SEO_PROBLEM → `listing.seo` rebuild (key `seo-fix:<slug>:<review>`). QUALITY_PROBLEM → `gate.quality` for that release. REWORK → the A5 correction entry. RETIRE → an owner retire card (never automatic). Each is capped per week. Today they are text in `PortfolioReview.actions` | `runtime/pipeline.py:3025-3170`; `growth/portfolio.py` (`LADDERS`, labels); `integrations/taxonomy_drift.py:282` (rebuild-token pattern for `listing.seo`) | 1. Seed `listing_outcomes` giving one SKU high impressions and low clicks, and another high sales with P1 incidents. 2. Run `portfolio_review`. 3. Assert one `listing.seo` rebuild and one `gate.quality` job, and no retire job without an owner card. 4. A rerun in the same week adds nothing | A5; dormant until outcomes exist (`listing.outcomes`) |
| P0-FINANCE-CHALLENGE-IDEM | 5 | Finance | Key `finance.challenge` as `challenge:<reconcile job id>` instead of `None` | `runtime/pipeline.py:3202` | 1. Run `finance_reconcile` once. 2. Force a retry after the enqueue (lease expiry). 3. Assert exactly one `finance.challenge` | none |
| P0-STOREFRONT-ASSET-FIX | 5 | Storefront / Brand | Route `asset_health` findings to jobs. A stale listing asset → `assets.build` rebuild. A missing or low-resolution brand asset → a storefront content proposal or owner card. Today the routes are stored as a reading with no consumer | `runtime/storefront_ops.py:36-46`; `store_foundation/asset_health.py:26-93` | 1. Seed a listing asset whose hash no longer matches its release. 2. Run `storefront_review`. 3. Assert one keyed rebuild job and none on a rerun | none |
| P0-PROVIDER-BILLING-RECON | 5 | Finance | Reconcile provider-billed spend (Anthropic usage, fal, Railway) to the `CostEntry` ledger. Today only owner-reported facts are compared | `finance/spend_hygiene.py:158-175`; `ops/provider_accounts.py` | 1. With a recorded billing fact that diverges by more than the threshold, run `finance_governor`. 2. Assert one discrepancy incident | Owner: read-only billing API keys |

**Owner-gated items found (not code P0s):**

1. External owner notification (email, SMS or push) is gated by design (`notifications.py:28-30`). Today, P0 and P1 incidents reach the owner only when they open the Command Center.
2. Ads channel and authority (row 25).
3. Etsy message intake for support (row 22).
4. Etsy ledger mapping verification (`finance/reconcile.py:25-31`).

---

## (b) Job-type table by department (171 types)

**Status key:**

- **LIVE** = handler plus an automatic producer.
- **LIVE (gated)** = an automatic producer exists, but the handler refuses or holds in SHADOW or behind a closed gate.
- **LIVE\*** = boot-once.
- **MANUAL** = only an owner route or a boot job conditioned on an owner approval.
- **ORPHAN** = handler with no producer.
- **UNHANDLED** = banded and classed with no handler.

Handler file:line comes from `inspect` and points at the registered function (for wrapped handlers, the wrapper). Cadence entries are given as `name@runtime/worker.py:line`.

#### 1. Market Intelligence (18)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `creative.benchmark_memory` | RESEARCH | benchmark_change | `runtime/release.py:4348` | cadence benchmark_memory@worker.py:811 | **LIVE** |
| `culture.sweep` | RESEARCH | benchmark_change | `runtime/release.py:7748` | cadence culture_sweep@worker.py:899 | **LIVE** |
| `intel.acceptance` | RESEARCH | benchmark_change | `runtime/release.py:8335` | cadence intel_acceptance@worker.py:711 | **LIVE** |
| `intel.benchmark_health` | RESEARCH | benchmark_change | `runtime/release.py:4307` | cadence mjs_benchmark_health@worker.py:798 | **LIVE** |
| `intel.benchmark_refresh` | RESEARCH | benchmark_change | `runtime/release.py:4399` | cadence benchmark_refresh@worker.py:804 | **LIVE** |
| `intel.gallery_analysis` | RESEARCH | benchmark_change | `runtime/release.py:7862` | cadence gallery_analysis@worker.py:919 | **LIVE** |
| `intel.panel_discovery` | RESEARCH | benchmark_change | `runtime/release.py:4374` | cadence panel_discovery@worker.py:802 | **LIVE** |
| `intel.pod_learning` | RESEARCH | exploration | `runtime/release.py:4324` | cadence mjs_pod_learning@worker.py:799 | **LIVE** |
| `intel.scan_evidence` | OBSERVE | benchmark_change | `runtime/evidence_ops.py:15` | cadence scan_evidence@worker.py:985 | **LIVE** |
| `intel.serp_capture` | RESEARCH | exploration | `runtime/release.py:4515` | cadence serp_capture@worker.py:795 | **LIVE** |
| `intel.watchlist_compare` | RESEARCH | benchmark_change | `runtime/intel_ops.py:306` | cadence watchlist_compare@worker.py:967 | **LIVE** |
| `intel.watchlist_scan` | RESEARCH | benchmark_change | `runtime/intel_ops.py:279` | cadence watchlist_scan@worker.py:966 | **LIVE** |
| `mjs.reviews` | RESEARCH | benchmark_change | `runtime/release.py:7668` | cadence mjs_reviews@worker.py:817 | **LIVE** |
| `mjs.scan` | RESEARCH | benchmark_change | `runtime/release.py:4198` | cadence mjs_scan@worker.py:792; owner/boot route app/main.py:2968 | **LIVE** |
| `mjs.seasonal_sentinel` | OBSERVE | seasonal_deadline | `runtime/release.py:4419` | cadence mjs_seasonal_sentinel@worker.py:800 | **LIVE** |
| `radar.competitor_snapshot` | RESEARCH | benchmark_change | `runtime/intel_ops.py:151` | cadence competitor_snapshot@worker.py:959 | **LIVE** |
| `radar.scan` | RESEARCH | benchmark_change | `runtime/pipeline.py:214` | cadence signal_review@worker.py:609; also runtime/pipeline.py:3019 | **LIVE** |
| `teardown.enforce` | BUILD | benchmark_change | `runtime/release.py:7039` | cadence teardown_enforce@worker.py:936 | **LIVE** |

#### 2. Research & Opportunity Discovery (6)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `intel.opportunity_review` | RESEARCH | new_opportunity | `runtime/intel_ops.py:321` | laura.executive_tick provider 'intelligence' laura/executive/loop.py:66,299 | **LIVE** |
| `radar.concept_intake` | RESEARCH | new_opportunity | `runtime/intel_ops.py:335` | cadence concept_intake@worker.py:973 | **LIVE** |
| `radar.score` | RESEARCH | new_opportunity | `runtime/pipeline.py:367` | runtime/pipeline.py:267, runtime/pipeline.py:350, runtime/pipeline.py:3167, intel/watchlist.py:741 | **LIVE** |
| `research.flag_architecture` | RESEARCH | exploration | `runtime/intel_ops.py:262` | only intel/research_agent.py:538 request_architecture_review(), which has no caller | **ORPHAN** |
| `research.investigate` | RESEARCH | exploration | `runtime/intel_ops.py:190` | runtime/intel_ops.py:246, intel/research_agent.py:527 | **LIVE** |
| `research.sweep` | RESEARCH | exploration | `runtime/intel_ops.py:231` | cadence research_sweep@worker.py:970 | **LIVE** |

#### 3. Product Development (10)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `cir.draft` | BUILD | proven_winner | `runtime/pipeline.py:650` | runtime/release.py:5054, runtime/release_recovery.py:240, runtime/pipeline.py:492, creative/intake.py:806 | **LIVE** |
| `cir.reengineer` | BUILD | proven_winner | `runtime/engineering_ops.py:282` | nothing enqueues; handler requires a decided REENGINEER_CARD that no route can decide (runtime/engineering_ops.py:254-300) | **ORPHAN** |
| `cir.revise` | BUILD | proven_winner | `runtime/engineering_ops.py:95` | cir.compile failure runtime/pipeline.py:1015 | **LIVE** |
| `collection.assemble` | BUILD | proven_winner | `runtime/release.py:2744` | runtime/release.py:2734, runtime/release.py:5073, runtime/pipeline.py:704 | **LIVE** |
| `creative.candidates_file` | BUILD | exploration | `runtime/pipeline.py:604` | cadence creative_candidates_file@worker.py:655 | **LIVE** |
| `creative.expedition` | RESEARCH | new_opportunity | `runtime/release.py:5856` | cadence arena_expedition@worker.py:850 | **LIVE** |
| `creative.grid_tournament` | RESEARCH | new_opportunity | `runtime/release.py:8051` | cadence grid_tournament@worker.py:710; also creative/preengineering.py:695 | **LIVE** |
| `creative.salvage_review` | RESEARCH | housekeeping | `runtime/engineering_ops.py:172` | cadence salvage_review@worker.py:990 | **LIVE** |
| `creative.tournament` | RESEARCH | new_opportunity | `runtime/release.py:5684` | cadence product_tournament@worker.py:858; also runtime/release.py:4459, runtime/release.py:7656, intel/mission_runtime.py:738 | **LIVE** |
| `creative.white_space` | RESEARCH | exploration | `runtime/release.py:6048` | cadence white_space_discovery@worker.py:652 | **LIVE** |

#### 4. Technical Validation (2)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `cir.compile` | TEST | proven_winner | `runtime/pipeline.py:1000` | runtime/engineering_ops.py:128, runtime/engineering_ops.py:309, runtime/pipeline.py:665, runtime/pipeline.py:756 | **LIVE** |
| `gate.certify` | TEST | truth_defect | `runtime/pipeline.py:1098` | runtime/release_recovery.py:184, runtime/pipeline.py:1026 | **LIVE** |

#### 5. Independent Quality Review (6)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `cir.reverse` | TEST | proven_winner | `runtime/quality_ops.py:191` | runtime/quality_ops.py:241 | **LIVE** |
| `cir.twin` | TEST | proven_winner | `runtime/quality_ops.py:191` | runtime/quality_ops.py:239 | **LIVE** |
| `gate.asset_truth` | TEST | truth_defect | `runtime/quality_ops.py:191` | runtime/quality_ops.py:243 | **LIVE** |
| `gate.lanes` | TEST | truth_defect | `runtime/release.py:8178` | cadence production_lanes@worker.py:649; also runtime/pipeline.py:1228 | **LIVE** |
| `gate.policy` | TEST | truth_defect | `runtime/quality_ops.py:191` | runtime/quality_ops.py:245 | **LIVE** |
| `gate.quality` | TEST | truth_defect | `runtime/quality_ops.py:230` | cadence quality_reverify@worker.py:956; also runtime/pipeline.py:1647 | **LIVE** |

#### 6. Learning (17)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `creative.capability_scorecard` | RESEARCH | exploration | `runtime/engineering_ops.py:208` | cadence capability_scorecard@worker.py:1000 | **LIVE** |
| `creative.outcome_learning` | RESEARCH | exploration | `runtime/release.py:7122` | cadence outcome_learning@worker.py:645 | **LIVE** |
| `creative.photo_principles` | RESEARCH | exploration | `runtime/engineering_ops.py:226` | cadence photo_principles@worker.py:979 | **LIVE** |
| `creative.reference_reading` | RESEARCH | benchmark_change | `runtime/release.py:3673` | cadence reference_reading@worker.py:813 | **LIVE** |
| `creative.style_learning` | RESEARCH | exploration | `runtime/release.py:7102` | cadence style_learning@worker.py:644 | **LIVE** |
| `improve.league` | TEST | exploration | `runtime/release.py:6995` | cadence improve_league@worker.py:661 | **LIVE** |
| `improve.measure` | OBSERVE | exploration | `runtime/release.py:6876` | cadence capability_measure@worker.py:629 | **LIVE** |
| `improve.mine` | RESEARCH | exploration | `runtime/release.py:6904` | cadence failure_mine@worker.py:637 | **LIVE** |
| `improve.monitor` | OBSERVE | exploration | `runtime/release.py:6924` | cadence promotion_monitor@worker.py:640 | **LIVE** |
| `improve.nightly` | BUILD | exploration | `runtime/release.py:6565` | cadence nightly_improvement@worker.py:620 | **LIVE** |
| `improve.replay` | TEST | exploration | `runtime/release.py:7017` | cadence improve_replay@worker.py:934 | **LIVE** |
| `improve.retrospective` | RESEARCH | exploration | `runtime/release.py:4575` | cadence improvement_retrospective@worker.py:820 | **LIVE** |
| `improve.role_work` | BUILD | exploration | `runtime/release.py:6462` | cadence role_<key> x8 (_role_cadences)@worker.py:1063-1072 | **LIVE** |
| `improve.sandbox` | TEST | exploration | `runtime/release.py:6962` | cadence improve_sandbox@worker.py:660 | **LIVE** |
| `improve.weekly` | BUILD | exploration | `runtime/release.py:6706` | cadence weekly_evolution@worker.py:624 | **LIVE** |
| `learn.scan` | RESEARCH | exploration | `learn/runtime.py:5` | cadence learn_gap_scan@worker.py:605 | **LIVE** |
| `learning.knowledge_gaps` | OBSERVE | exploration | `runtime/learning_gaps_ops.py:15` | cadence knowledge_gaps@worker.py:634 | **LIVE** |

#### 7. Premium PDF (1)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `assets.build` | BUILD | proven_winner | `runtime/release.py:9760` | runtime/release.py:3142, runtime/release.py:3642, runtime/pipeline.py:1731, runtime/pipeline.py:3428 | **LIVE** |

#### 8. Visual production & Laura (16)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `assets.model_photography` | BUILD | proven_winner | `runtime/release.py:6124` | cadence model_photography@worker.py:777 | **LIVE** |
| `assets.owned_photography` | BUILD | proven_winner | `runtime/release.py:8876` | cadence owned_photography@worker.py:772; also intel/mission_runtime.py:1202 | **LIVE** |
| `assets.render` | BUILD | proven_winner | `-` | none (only agents/registry.py:204 allowlist) | **UNHANDLED** |
| `creative.blind_review` | RESEARCH | benchmark_change | `runtime/release.py:7980` | cadence blind_review@worker.py:708 | **LIVE** |
| `creative.blinded` | RESEARCH | exploration | `runtime/release.py:5641` | cadence blinded_benchmark@worker.py:841 | **LIVE** |
| `creative.four_season` | RESEARCH | exploration | `runtime/release.py:6083` | cadence four_season_programme@worker.py:657 | **LIVE** |
| `creative.image_benchmark` | RESEARCH | exploration | `runtime/release.py:8481` | cadence image_benchmark@worker.py:759; also runtime/release.py:8601; owner/boot route app/main.py:309 | **LIVE** |
| `creative.model_freeze` | BUILD | exploration | `runtime/release.py:9388` | boot-once on owner approval app/main.py:370 | **MANUAL** |
| `creative.model_reference_pack` | RESEARCH | exploration | `runtime/release.py:9437` | cadence model_reference_pack@worker.py:765 | **LIVE** |
| `creative.model_tournament` | RESEARCH | exploration | `runtime/release.py:8611` | cadence model_tournament@worker.py:762; owner/boot route app/main.py:335 | **LIVE** |
| `creative.north_star` | RESEARCH | exploration | `runtime/orders.py:160` | cadence creative_north_star@worker.py:680 | **LIVE** |
| `creative.photoreal_calibration` | RESEARCH | exploration | `runtime/release.py:9652` | boot-once when none recorded app/main.py:549 (no cadence; once per deploy until done) | **LIVE*** |
| `visual.controlled_experiment` | RESEARCH | exploration | `runtime/release.py:3652` | owner route app/command_center/api.py:639 | **MANUAL** |
| `visual.identity_drift` | OBSERVE | truth_defect | `runtime/release.py:3691` | cadence identity_drift@worker.py:808 | **LIVE** |
| `visual.portrait_repair` | BUILD | exploration | `runtime/release.py:8717` | boot-once on owner-approved portrait app/main.py:445 | **MANUAL** |
| `visual.rnd.cycle` | RESEARCH | exploration | `autonomy/visual_rnd_job.py:54` | cadence visual_rnd@worker.py:1022 | **LIVE** |

#### 9. Gallery Assembly (2)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `assets.launch_review` | BUILD | proven_winner | `runtime/release.py:3631` | owner route app/command_center/api.py:758,786 | **MANUAL** |
| `visual.image_production` | BUILD | proven_winner | `runtime/release.py:3610` | assets.build runtime/release.py:629; stages self-enqueue release.py:3622; image_generation gate | **LIVE (gated)** |

#### 10. Listing Package (2)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `listing.draft` | DRAFT | proven_winner | `runtime/pipeline.py:1710` | runtime/release.py:5005, runtime/pipeline.py:1273 | **LIVE** |
| `listing.package` | BUILD | proven_winner | `runtime/listing_package_ops.py:15` | cadence listing_package@worker.py:724 | **LIVE** |

#### 11. Etsy Operations (6)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `etsy.listing_census` | OBSERVE | benchmark_change | `runtime/etsy_ops.py:1262` | cadence etsy_listing_census@worker.py:1005 | **LIVE** |
| `etsy.probe` | OBSERVE | benchmark_change | `runtime/release.py:4152` | cadence etsy_probe@worker.py:787; owner/boot route app/main.py:3282, app/command_center/etsy_connect.py:72 | **LIVE** |
| `etsy.shop_snapshot` | OBSERVE | benchmark_change | `runtime/etsy_ops.py:1002` | cadence etsy_shop_snapshot@worker.py:945 | **LIVE** |
| `store.activate` | PUBLISH | proven_winner | `runtime/pipeline.py:2382` | store.publish runtime/pipeline.py:2358; protected | **LIVE (gated)** |
| `store.live_drift` | OBSERVE | truth_defect | `runtime/etsy_ops.py:1473` | cadence store_live_drift@worker.py:948; owner/boot route app/command_center/api.py:904 | **LIVE** |
| `store.publish` | PUBLISH | proven_winner | `runtime/pipeline.py:1809` | launch.plan runtime/release.py:2257; refused in SHADOW pipeline.py:1856 | **LIVE (gated)** |

#### 12. Marketing / Launch (9)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `growth.conclude` | TEST | new_opportunity | `runtime/release.py:7569` | cadence growth_conclude@worker.py:690 | **LIVE** |
| `growth.distribution` | DRAFT | new_opportunity | `runtime/growth_ops.py:912` | cadence growth_distribution@worker.py:685 | **LIVE** |
| `growth.experiments` | TEST | new_opportunity | `runtime/release.py:2031` | cadence growth_experiments@worker.py:705 | **LIVE** |
| `growth.journey` | OBSERVE | truth_defect | `runtime/growth_ops.py:1235` | cadence growth_journey@worker.py:686 | **LIVE** |
| `growth.preproduction` | DRAFT | exploration | `runtime/release.py:9695` | cadence preproduction_validation@worker.py:703 | **LIVE** |
| `growth.steer` | BUILD | housekeeping | `runtime/growth_ops.py:1407` | cadence growth_steer@worker.py:687 | **LIVE** |
| `launch.plan` | DRAFT | seasonal_deadline | `runtime/release.py:9781` | runtime/release.py:1422, runtime/chain_successors.py:170 | **LIVE** |
| `launch.readiness` | OBSERVE | seasonal_deadline | `runtime/release.py:4639` | cadence launch_readiness@worker.py:728; owner/boot route app/main.py:1123 | **LIVE** |
| `marketing.schedule` | DRAFT | seasonal_deadline | `runtime/release.py:2297` | runtime/release.py:2254 | **LIVE** |

#### 13. Commercial Analytics (5)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `commerce.order_readings` | OBSERVE | exploration | `runtime/orders.py:103` | cadence order_readings@worker.py:678 | **LIVE** |
| `commerce.orders_ingest` | OBSERVE | exploration | `runtime/orders.py:74` | cadence orders_ingest@worker.py:670 | **LIVE** |
| `commerce.readings` | OBSERVE | exploration | `runtime/commerce_readings.py:241` | cadence commerce_readings@worker.py:666 | **LIVE** |
| `improve.commercial_lessons` | OBSERVE | exploration | `runtime/commercial_ops.py:14` | cadence commercial_lessons@worker.py:631 | **LIVE** |
| `listing.outcomes` | OBSERVE | exploration | `runtime/listing_outcomes.py:45` | cadence listing_outcomes@worker.py:1019 | **LIVE** |

#### 14. Family Engine & Winner Amplification (3)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `creative.family_engine` | RESEARCH | new_opportunity | `runtime/engineering_ops.py:142` | cadence family_engine@worker.py:976 | **LIVE** |
| `intel.children_portfolio` | RESEARCH | new_opportunity | `runtime/intel_ops.py:168` | cadence children_portfolio@worker.py:982 | **LIVE** |
| `listing.cross_sell_graph` | RESEARCH | new_opportunity | `runtime/engineering_ops.py:195` | cadence cross_sell_graph@worker.py:991 | **LIVE** |

#### 15. Orchestration (10)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `build.tick` | BUILD | housekeeping | `runtime/release.py:5526` | cadence build_tick@worker.py:828; also build2/unblock.py:37 | **LIVE** |
| `chain.rebuild` | BUILD | truth_defect | `runtime/release.py:4897` | cadence chain_rebuild@worker.py:718; also runtime/release.py:5280, runtime/release.py:5362, runtime/growth_ops.py:1428; owner/boot route app/main.py:1098 | **LIVE** |
| `chain.successors` | BUILD | proven_winner | `runtime/release.py:9793` | cadence chain_successors@worker.py:721 | **LIVE** |
| `ops.capacity` | OBSERVE | housekeeping | `runtime/release.py:7448` | cadence capacity_review@worker.py:877; also runtime/orders.py:147 | **LIVE** |
| `ops.queue_check` | OBSERVE | truth_defect | `runtime/pipeline.py:2934` | cadence queue_check@worker.py:608 | **LIVE** |
| `ops.thrash` | OBSERVE | truth_defect | `runtime/release.py:7595` | cadence thrash_sweep@worker.py:691 | **LIVE** |
| `swarm.allocate` | BUILD | housekeeping | `runtime/release.py:1990` | cadence swarm_allocate@worker.py:697 | **LIVE** |
| `swarm.backlog` | BUILD | housekeeping | `runtime/release.py:2018` | cadence swarm_backlog@worker.py:699 | **LIVE** |
| `swarm.orphans` | BUILD | housekeeping | `runtime/release.py:2001` | cadence swarm_orphans@worker.py:698 | **LIVE** |
| `swarm.review` | OBSERVE | housekeeping | `runtime/release.py:1977` | cadence swarm_review@worker.py:696 | **LIVE** |

#### 17. Finance / Budget & Spend Governance (6)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `finance.accounting.cycle` | OBSERVE | housekeeping | `finance/accounting/job.py:17` | cadence accounting_cycle@worker.py:1034 | **LIVE** |
| `finance.accounting.period_pack` | DRAFT | housekeeping | `autonomy/period_packs.py:86` | cadence accounting_period_pack@worker.py:1025 | **LIVE** |
| `finance.challenge` | OBSERVE | truth_defect | `runtime/pipeline.py:3206` | finance.reconcile runtime/pipeline.py:3202 (idempotency_key=None) | **LIVE** |
| `finance.escalation_check` | OBSERVE | truth_defect | `runtime/pipeline.py:3239` | cadence spend_escalation@worker.py:715 | **LIVE** |
| `finance.governor` | OBSERVE | truth_defect | `runtime/release.py:7079` | cadence finance_governor@worker.py:662 | **LIVE** |
| `finance.reconcile` | OBSERVE | proven_winner | `runtime/pipeline.py:3179` | cadence finance_reconcile@worker.py:612 | **LIVE** |

#### 18. Security / Authority & Credentials (2)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `etsy.credential_health` | OBSERVE | benchmark_change | `runtime/etsy_ops.py:878` | cadence etsy_credential_health@worker.py:944 | **LIVE** |
| `ops.provider_credentials` | OBSERVE | truth_defect | `runtime/release.py:9722` | cadence provider_credentials@worker.py:739 | **LIVE** |

#### 19. Operations / Reliability, Sentinel & Recovery (11)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `ops.capability_probes` | TEST | truth_defect | `runtime/release.py:7697` | cadence capability_probes@worker.py:893; owner/boot route app/main.py:287 | **LIVE** |
| `ops.continuity` | TEST | truth_defect | `runtime/release.py:3759` | cadence continuity_proof@worker.py:742; owner/boot route app/main.py:1172 | **LIVE** |
| `ops.dependencies` | OBSERVE | housekeeping | `runtime/release.py:7530` | cadence dependency_sweep@worker.py:931 | **LIVE** |
| `ops.health` | OBSERVE | truth_defect | `runtime/release.py:7158` | cadence health_sweep@worker.py:886 | **LIVE** |
| `ops.heartbeat` | OBSERVE | truth_defect | `runtime/pipeline.py:2649` | cadence infra_heartbeat@worker.py:607 | **LIVE** |
| `ops.maturity_disagreements` | OBSERVE | housekeeping | `runtime/ops_watch.py:16` | cadence maturity_disagreements@worker.py:731 | **LIVE** |
| `ops.offsite_archive` | BUILD | truth_defect | `runtime/release.py:8413` | cadence offsite_archive@worker.py:747 | **LIVE** |
| `ops.provenance_backfill` | OBSERVE | housekeeping | `runtime/release.py:7419` | cadence provenance_backfill@worker.py:713 | **LIVE** |
| `ops.retention` | BUILD | housekeeping | `runtime/release.py:8356` | cadence retention_sweep@worker.py:927 | **LIVE** |
| `ops.sentinel` | OBSERVE | truth_defect | `runtime/release.py:7318` | cadence stale_artefact_sentinel@worker.py:882 | **LIVE** |
| `ops.slo` | OBSERVE | truth_defect | `runtime/v11_wiring.py:25` | cadence slo_check@worker.py:1029 | **LIVE** |

#### 20. Executive / Laura & COO (7)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `autonomy.department_review` | OBSERVE | housekeeping | `autonomy/handlers.py:96` | autonomy.orchestrate generators autonomy/generators.py:209; laura loop laura/executive/loop.py:267 | **LIVE** |
| `autonomy.morning_handoff` | DRAFT | housekeeping | `autonomy/handlers.py:225` | autonomy.orchestrate autonomy/generators.py:262 | **LIVE** |
| `autonomy.orchestrate` | BUILD | truth_defect | `autonomy/handlers.py:36` | cadence executive_orchestrator@worker.py:1011 | **LIVE** |
| `laura.executive_tick` | BUILD | truth_defect | `laura/executive/handlers.py:37` | cadence laura_executive@worker.py:1015 | **LIVE** |
| `plan.cycle` | BUILD | new_opportunity | `runtime/pipeline.py:3011` | cadence daily_review@worker.py:610; owner/boot route app/main.py:1078 | **LIVE** |
| `plan.strategy` | DRAFT | exploration | `runtime/pipeline.py:3300` | cadence strategy_review@worker.py:613 | **LIVE** |
| `scale.trajectory` | RESEARCH | exploration | `runtime/orders.py:129` | cadence trajectory_nightly@worker.py:679 | **LIVE** |

#### 22. Customer Support (2)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `support.reply` | CUSTOMER-REMEDY | customer_incident | `runtime/release.py:2423` | support.triage via support/department.py:398; drafts only, never sent | **LIVE (gated)** |
| `support.triage` | DRAFT | truth_defect | `runtime/release.py:2536` | cadence support_triage@worker.py:663 | **LIVE** |

#### 23. Physical Sampling / Testers (4)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `assets.physical_upgrade` | BUILD | proven_winner | `runtime/release.py:3594` | chained only from physical.photo (owner upload) runtime/release.py:3575 | **MANUAL** |
| `physical.photo` | OBSERVE | truth_defect | `runtime/release.py:3584` | owner upload route app/main.py:5301 | **MANUAL** |
| `physical.record` | OBSERVE | truth_defect | `runtime/release.py:2963` | owner upload route app/main.py:5285 | **MANUAL** |
| `physical.upgrade_impact` | OBSERVE | exploration | `runtime/release.py:3710` | cadence physical_upgrade_impact@worker.py:806 | **LIVE** |

#### 24. Seasonal / Planning (5)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `seasonal.cycle_proof` | BUILD | exploration | `runtime/release.py:6281` | cadence seasonal_cycle_proof@worker.py:871 | **LIVE** |
| `seasonal.engine` | BUILD | seasonal_deadline | `runtime/release.py:7611` | cadence seasonal_engine@worker.py:692 | **LIVE** |
| `seasonal.harvest` | OBSERVE | exploration | `runtime/release.py:7139` | cadence season_harvest@worker.py:646 | **LIVE** |
| `seasonal.remerchandising` | DRAFT | seasonal_deadline | `runtime/release.py:6397` | cadence remerchandising_review@worker.py:863 | **LIVE** |
| `seasonal.sentinel` | OBSERVE | seasonal_deadline | `runtime/release.py:3835` | cadence seasonal_sentinel@worker.py:778; owner/boot route app/main.py:2950 | **LIVE** |

#### 25. Paid Media (Ads) (3)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `ads.adjust` | SPEND | new_opportunity | `runtime/growth_ops.py:479` | cadence ads_review@worker.py:684 | **LIVE** |
| `ads.campaign` | SPEND | new_opportunity | `runtime/growth_ops.py:536` | ads.adjust runtime/growth_ops.py:502; refused while ad_authority closed | **LIVE (gated)** |
| `marketing.ads_readiness` | OBSERVE | housekeeping | `runtime/v11_wiring.py:35` | cadence ads_readiness@worker.py:1037 | **LIVE** |

#### 26. Storefront / Brand (3)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `content.draft` | DRAFT | proven_winner | `runtime/storefront_ops.py:66` | runtime/storefront_ops.py:49 | **LIVE** |
| `store.update` | PUBLISH | proven_winner | `runtime/storefront_ops.py:161` | content.draft runtime/storefront_ops.py:85; held in SHADOW storefront_ops.py:195 | **LIVE (gated)** |
| `storefront.review` | OBSERVE | new_opportunity | `runtime/storefront_ops.py:32` | cadence storefront_review@worker.py:952 | **LIVE** |

#### 27. Model Governance / Gateway (3)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `model.probe` | TEST | truth_defect | `runtime/release.py:3725` | cadence model_probe@worker.py:736; owner/boot route app/main.py:3415 | **LIVE** |
| `visual.model_ledger` | OBSERVE | housekeeping | `runtime/quality_ops.py:320` | cadence model_ledger@worker.py:987 | **LIVE** |
| `visual.provider_trial` | RESEARCH | exploration | `runtime/release.py:8776` | boot-once on owner 2026-09-23 authorisation app/main.py:487 | **MANUAL** |

#### 28. Compliance / Policy & CASL (2)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `etsy.openapi_reverify` | OBSERVE | truth_defect | `runtime/etsy_ops.py:1644` | cadence etsy_openapi_reverify@worker.py:1003 | **LIVE** |
| `ops.policy_watch` | OBSERVE | truth_defect | `runtime/release.py:5373` | cadence policy_watch@worker.py:823 | **LIVE** |

#### 29. Pricing Intelligence (2)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `pricing.experiment` | PUBLISH | new_opportunity | `-` | none; Laura delegation maps price wording to it as protected (laura/agency/delegation.py:66) | **UNHANDLED** |
| `pricing.position` | RESEARCH | proven_winner | `runtime/release.py:9770` | runtime/release.py:619, runtime/release.py:5146 | **LIVE** |

#### 30. SEO / Search Visibility (7)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `etsy.dashboard_harvest` | OBSERVE | housekeeping | `runtime/c12_ops.py:67` | cadence dashboard_harvest@worker.py:997 | **LIVE** |
| `listing.search_visibility_aging` | OBSERVE | housekeeping | `runtime/c12_ops.py:34` | cadence search_visibility_aging@worker.py:995 | **LIVE** |
| `listing.search_visibility_watch` | OBSERVE | housekeeping | `runtime/storefront_watch.py:102` | cadence search_visibility_watch@worker.py:677 | **LIVE** |
| `listing.seo` | DRAFT | proven_winner | `runtime/release.py:973` | runtime/release.py:812, runtime/release.py:887, runtime/release.py:2169, integrations/taxonomy_drift.py:282 | **LIVE** |
| `listing.taxonomy_refresh` | RESEARCH | exploration | `runtime/release.py:1523` | cadence etsy_taxonomy@worker.py:674 | **LIVE** |
| `listing.window_captures` | OBSERVE | housekeeping | `runtime/c12_ops.py:56` | cadence window_captures@worker.py:996 | **LIVE** |
| `seo.cycle` | DRAFT | housekeeping | `seo/handler.py:14` | cadence seo_cycle@worker.py:1031 | **LIVE** |

#### 31. Portfolio & Product Mortality (1)

| Job type | JOB_CLASS | Band | Handler | Automatic producer(s) | Status |
|---|---|---|---|---|---|
| `portfolio.review` | OBSERVE | exploration | `runtime/pipeline.py:3025` | cadence portfolio_review@worker.py:611; also runtime/pipeline.py:3320 | **LIVE** |