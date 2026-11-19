# ENG-CREDITS — routing audit and proposed task→provider allocation (W6)

Status: **PROPOSAL. Nothing here changes live routing.** Routing changes go through the owner
card (`gateway.providers.routes_card` / `BRAMBLELOOP_MODEL_ROUTES`) and need the measured
evidence that `gateway.routing.equivalence` requires (`MIN_EVIDENCE_ITEMS` = 20). This document
does not set `BRAMBLELOOP_MODEL_VENDOR`, and must never set it to `openai`.

Base: `claude/w6-INTEG2` @ a35ad302. Date: 2026-11-19 (UTC). Paths are relative to
`brambleloop/src/brambleloop/`.

## 0. The credit does not change the decision rule

The owner receives about US$100 a month of Anthropic API credit, and possibly an OpenAI credit.
**Promotional credit is not spending authority.** The CA$100/month cash ceiling
(`finance/spend_policy.py` `CEILING_CAD`) counts every recorded call, credit or not. The
per-agent daily ceilings and purpose allocations are unchanged.

The credit is UNKNOWN until the owner records a verified grant: Command Center
`POST /api/cc/finance/model-credit` (step-up), read back from `finance.credits.model_credit_accounting`.
So the allocation below is ranked by **quality first, then cost** (spend_policy's order). It is
never ranked by "whose credit is free".

**No measured quality evidence exists in this repository.** Per-task `routing.evidence` rows
(`routing.record_route_evidence`) live in the production database, which builders do not read.
Every move below is a hypothesis with a stated way to measure it. None is a measured result.

## 1. Which tasks call a model, and why

Tiers: C = `claude-haiku-4-5`, S = `claude-sonnet-5`, D = `claude-opus-5` (`gateway/routing.py` `TIERS`).

| Task (tier) | Call site | Trigger | Feeds a certified product? | Governing ceiling | Why a model |
|---|---|---|---|---|---|
| topic_filing (C) | `culture/classify.py:139` | `culture.sweep`, daily | no | market_radar CA$4/day | closed-vocabulary filing of discovered topics; there is no keyword fallback |
| gallery_observation (S) | `intel/vision.py:586`; `intel/serp.py:520` | `intel.gallery_analysis` every 2 h; `intel.serp_capture` daily | indirectly (MJs evidence) | 40% allocation (`ALLOCATION`) + market_radar | judging composition and shot type from a photo is taste; the Etsy API cannot answer it |
| gallery_observation (S), the taste gate | `creative/intake.py:1013` (`judge_held`) | `regate_held` from tournament / expedition / seasonal sentinel | **yes** (the concept build gate) | the job's agent; `may_spend` is not checked | concept desirability (see §2, F-A2) |
| construction_reading (D) | `creative/reference.py:148` | `creative.reference_reading`, daily | **yes** (concept briefs) | creative_director CA$28/day | how a competitor object is built; a misreading becomes a design constraint |
| concept_ideation (C) | `creative/prospecting.py` via `runtime/release.py:6315` | `creative.tournament`, weekly | **yes** | creative_director | a wide, inexpensive field (#3) |
| concept_generation (D) | `runtime/release.py:6446`, `:6875` | `creative.expedition` weekly; `seasonal.cycle_proof` weekly | **yes** | creative_director | decides what the company tries to sell |
| benchmark_challenge (D) | `creative/blinded.py:648` via `runtime/release.py:6203` | `creative.blinded`, every 14 days | **yes** (independent review) | creative_director | release-blocking blinded comparison (#315) |
| asset_inspection (S) | `visual/inspect.py:323,413,513`; `visual/fidelity.py:1074`; `visual/photoreal.py:98`; `visual/bible.py:193`; `visual/model_registry.py`; `publish/motif_fidelity.py:375` | `assets.build` frame review, `visual.image_production`, `listing.seo` exported review, model photography | **yes** (release frames) | **quality_director CA$1.00/day** | does an image show what its caption claims (#61, #79) |
| image_benchmark_judging (D) | `gateway/image_bench.py:1024`; `visual/tournament.py:289` | `creative.image_benchmark` and `creative.model_tournament`, hourly | no (provider choice) | `BENCHMARK_BUDGET_CAD`; creative_director | blind image scoring |
| laura.* (C/S) | `gateway/laura_*.py`, `laura/executive/loop.py:664` | Command Center; `laura.executive_tick` | no | laura CA$0.50/day; 1–8% allocations | conversation and ranking over supplied facts |
| (probes, no task) | `gateway/anthropic.py:1070` `probe`; `:1231` `vision_probe` | `model.probe`, `ops.capability_probes`, every 6 h | no | month ceiling | provider liveness (fixed haiku model) |

Declared tasks with **no runtime call site**: `listing_copy` (copy is deterministic templating in
`commerce/seo.py`), `creative_evaluation`, `listing_classify`, `listing_mechanisms`,
`seasonal_signal`.

## 2. Findings

### Deterministic work that asks a model (flagged, not changed)

- **F-D1 `gateway/compat_pack.py` `TASKS` (lines ~107–127).** These ask a model to extract
  gauge and yardage, which are `DETERMINISTIC_ALTERNATIVES` keys (`cir.grading:grade`,
  `cir.twin:build_twin`). They also ask for per-metric comparisons and relative-change
  arithmetic. The pack never calls `routing.route()`, so the F-312 refusal does not reach it.
  It has no runtime caller today, but it is billable if anyone runs it.
  Proposed fix: route it through `route()`, or delete the arithmetic and extraction items and
  compute them in code.
- **F-D2 `review.mining` prompt (`gateway/prompts.py` ~139–150)** asks the model for a theme
  `count`. Counting belongs in code: return the theme labels and count them. It is unused at
  runtime.
- **F-D3 `laura.exec_rank` (`laura/executive/loop.py` ~657–668)** asks a model to re-order
  candidates that code has already scored. This is borderline. The fallback is the
  deterministic order, and the call has its own 2% stop. Proposed measurement: the share of
  ticks where the model order differs from the score order. If it is under 10% across 20+
  ticks, retire the call.
- No declared `TASKS` key shadows a `DETERMINISTIC_ALTERNATIVES` key, and `route()` refuses all
  of them. No compiler, arithmetic or database path calls a model.

### Routing inconsistencies (flagged, not changed)

- **F-A1** Three call sites bypass `BRAMBLELOOP_MODEL_ROUTES`: they use
  `gateway.anthropic.provider_for`, not `gateway.providers.for_task`.
  The sites are `gateway/image_bench.py:1024`, `runtime/release.py:8711` (grid tournament) and
  `gateway/laura_register.py:535`. They are harmless while every route is Anthropic. They would
  silently ignore an owner-approved route.
- **F-A2** Concept desirability (#218) is declared `creative_evaluation` on the deep tier. It is
  actually judged by `intake.judge_held` on the gallery_observation standard tier, and
  `may_spend` is not checked. This is a de-facto tier downgrade on Priority 1 work, which
  spend_policy forbids as a silent outcome. It should be an owner-card routing decision with
  evidence, not a quiet code path.
- **F-A3** Some spend is filed under purposes that are not `TASKS` keys:
  `search_grid_tournament`, `model_tournament`, `compat_pack` and `model.probe`. For example,
  `search_grid_tournament` uses the gallery_observation model but escapes its 40% stop.
- **F-A4** `publish/motif_fidelity.py:374` calls `provider.see` without `check_budget`. The
  vision gate refuses an unreserved call, so in production this check most likely always
  returns UNMEASURABLE. A certified-product check is silently doing nothing (see §4).
- **F-A5** `seasonal.cycle_proof` is scheduled under publishing but bills creative_director.

## 3. Proposed task→provider allocation

Rule: quality first, cost second, waste never. OpenAI is **routed-only** (`providers.ROUTED_ONLY`),
capped at `OPENAI_DEFAULT_CEILING_SHARE` (25%) of the month, and needs the owner's
`openai-text` activation. Outcome routing and fallback stay Anthropic-only (`ROUTABLE_PROVIDERS`).

| Task | Today | Proposal | Evidence needed before the owner card |
|---|---|---|---|
| concept_generation, construction_reading, benchmark_challenge | Anthropic D | **Keep.** These are the highest-stakes judgements. | none: this is no change |
| creative_evaluation (the taste gate) | runs as S under gallery_observation | **Owner card:** route `judge_held` to the declared task `creative_evaluation` (D). Give it its own allocation line, carved out of the 40% gallery stop. | `routing.equivalence("creative_evaluation", "standard")` on ≥20 held concepts, judged by both tiers, blind |
| asset_inspection | Anthropic S, quality_director CA$1/day | **Keep the tier.** Raise quality_director's daily ceiling only through an owner action, with the starvation evidence (`finance.credits.productive_model_use`). | refusals by `which=agent` for quality_director this month |
| concept_ideation, topic_filing | Anthropic C | **Keep.** These are cheap by design (#3). | none |
| gallery_observation (MJs) | Anthropic S | **Keep.** It is the second spending priority. | none |
| image_benchmark_judging | Anthropic D, superseded | **No spend.** `image_bench.SUPERSEDED` (FLUX 3 ruling). The hourly no-op jobs could be descheduled. | none |
| laura.* | C/S, behind owner switches | **Keep.** Owner switches stay off by default. | n/a |
| any task → OpenAI | n/a | **Only a single routed task, for an A/B, through `BRAMBLELOOP_MODEL_ROUTES`** (e.g. `topic_filing=openai`, the documented `EXAMPLE_ROUTE_TASK`). Never by vendor default. | 20+ paired items through `routing.record_route_evidence` |

Expected effect on credit: the proposal does not move spend to a provider because of its credit.
If the Anthropic credit is recorded, most Anthropic spend is estimated to be absorbed by it.
That is reported, and it authorises nothing.

## 4. Productive use: where an approved call would raise certified throughput or quality

The read-only view `finance.credits.productive_model_use(db)` reports, for each family:
- this month's calls and spend;
- refusals by which ceiling said no;
- the governing agent ceiling;
- `NO_CALLER` when the task has no call site.

| Family | Task(s) | Where it is starved | Status of wiring |
|---|---|---|---|
| Concept generation | concept_generation, concept_ideation, construction_reading | Not starved by money: creative_director has CA$28/day. Weekly cadence and F-098 parking (provider down) are the limits. | No change. It runs within its ceilings. |
| Independent review | benchmark_challenge | `blinded.MIN_PAIRS` = 12 like-for-like pairs: it refuses before spending when evidence is thin. The limit is evidence, not money. | No change: spending earlier would buy a weaker verdict. |
| Independent review (images) | asset_inspection | **quality_director CA$1.00/day.** This is the tightest bound on certified-product work. One `assets.build` frame review plus hero review can reach it. | **Owner action**, not code. The view reports refusals with `which=agent` for quality_director. |
| Listing-copy refinement | listing_copy | **No caller.** Copy is deterministic and claim-gated. | Not wired. A model refinement pass would need a claim-gate re-check and a CIR-fact diff guard first. Proposed as a follow-up, not added here. |
| Defect learning | none declared | **No model task.** `improve.failure_memory` is deterministic. | Not wired: no declared task, and adding one is a routing change. |
| Motif fidelity | asset_inspection | **Silently UNMEASURABLE** (F-A4: no reservation). | Flagged for the visual owner. Fixing it adds a paid caller, which must be declared in `tests/test_cert_spend_hosts` and reviewed. |

No new paid caller was added by ENG-CREDITS. No ceiling, allocation or route was changed.
