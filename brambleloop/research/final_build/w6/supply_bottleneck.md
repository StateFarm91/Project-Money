# Supply bottleneck: how new products enter engineering (ENG-SUPPLY, 2026-11-19)

Base: `origin/claude/w6-INTEG2` @ a35ad302. Everything here was read from the code at that commit, with
file:line references. **No production database, queue or Railway reading was taken.** Builders are not
allowed to read production, so the production queue depths and ages are UNKNOWN here. Where a figure
below is a rate, it is the rate the code permits, not one that was observed.

## Answer

New products are throttled by two separate gates:

1. **The Launch-0 seeder has a WIP limit but a finite source.** `release_recovery.seed_launch0`
   (WIP_LIMIT = 2, SEED_PER_RUN = 1, hourly) draws only from the release registry: eight Launch-0
   releases. Once those are seeded, it opens `catalogue-exhausted:launch0`. A further product then
   needs an integrator code change (`builder.CATALOGUE` / `RELEASE_VERSIONS`). Supply stops.
2. **The research and creative producers have an unlimited source but no admission at all.**
   - `radar.score`, `creative.intake` and `creative.regate` enqueue `cir.draft` directly under
     `draft:<slug>`.
   - Nothing bounds work in progress, cost or stage backlog for them.
   - They are counted as WIP only after the fact (`release_recovery.py:220`).
   - In practice they are rarely reached:
     - They stall at the pre-engineering gate, which waits on a vision judgement while
       `image_vision` is closed.
     - The permanent `draft:<slug>` key means a slug drafts once ever.

When the vision gate does open, one 6-hourly `radar.scan` can promote the whole static pool in a
single tick. That queues roughly ten `cir.draft` jobs at once on one worker, with no cost check.
This is reproduced in `tests/test_w5_a4a_research_to_concept.py`: before ENG-SUPPLY, every pool
promotion and the research concept were drafted in the same tick.

So the real production bottleneck is twofold:
- **Source exhaustion:** the only paced producer has a finite registry.
- **No admission for the unbounded producers:** they are either gated shut upstream or arrive as an
  unpaced burst.

A fixed seed count cannot fix either. The fix is a single admission door that every producer offers
into, paced by measured capacity and cost.

## Every source of new products (at a35ad302)

| # | Producer | Site | Key | Source | Rate / WIP limit | Gates that throttle it |
|---|---|---|---|---|---|---|
| A | `radar.score` promotion | runtime/pipeline.py:695 | `draft:<slug>` (permanent) | Static `radar.opportunity.POOL` + approved `radar_concepts` rows (research) | No WIP. Fed by `radar.scan` (6h), `radar.concept_intake` (6h), `portfolio.review` (7d), `intel.watchlist` queue_scores, `creative.family_engine` amplify (24h) | `PROMOTION_THRESHOLD = 0.55` (pipeline.py:38). Risk class A/B only. Trend-evidence discount. Pre-engineering gate (`creative/preengineering.gate_concept`): WAITING without a vision judgement |
| B | `creative.intake` (tournament / expedition winners) | creative/intake.py:806 | `draft:<slug>` | Weekly `creative.tournament` and `creative.expedition` | No WIP | Funnel carried. `ideation.pre_engineering_gate` cleared. `_ceiling_gate` (release.py:6515) on the creative spend |
| C | `creative.regate` (re-present WAITING winners) | creative/intake.py:1121 | `draft:<slug>` | `mjs.seasonal_sentinel` (24h), tournament, expedition | `REGATE_LIMIT = 20` per run, `REGATE_ROWS = 200` (intake.py:55-56). No WIP | Same pre-engineering gate, once a vision judgement exists |
| D | `chain.rebuild` redraft | runtime/release.py:5508 | `redraft:<slug>:<fp>:d<doc>` | Certified releases whose code design or document moved | Hourly. No WIP | Only already-certified products: a rebuild, not new supply |
| E | `seed_launch0` | runtime/release_recovery.py:377 | `launch0-seed:<slug>:<v>:<fp>:d<doc>` | Launch-0 release registry (8 releases) | **SEED_PER_RUN = 1, WIP_LIMIT = 2, IN_FLIGHT_HORIZON = 6h**, hourly via chain.rebuild | Finite. Exhausts into `catalogue-exhausted:launch0`, after which supply needs a code change |
| F | `product.pipeline` board drafts | products/pipeline_board.py:1017 | `pipeline-draft:<slug>` | ENGINEERED ∪ catalogue | n/a | **Dead:** no handler registration or cadence exists |

Upstream feeders of A–C, each with its own bound:
- **Ideation:** `radar/ideation.py` `MAX_IN_FLIGHT = 1` research task.
- **Proposals:** `radar/proposal_writer` `MAX_EVALUATIONS_PER_RUN = 10`, `MAX_FAMILY_VARIATIONS = 2`.
- **Intake:** `radar.intake` approves only `SUPPORTED_FORMS` and `flat_rows`.
- **Portfolio:** `opportunity.select_portfolio` `MAX_PER_CATEGORY = 3`, `MAX_CLASS_C = 1`.

How a research concept becomes a CIR:
1. Answered research (`research.investigate`).
2. `proposal_writer` writes a proposal.
3. `radar.intake` approves it (a `radar_concepts` row).
4. `radar.score` promotes it (≥ 0.55, risk A/B, pre-engineering gate).
5. `cir.draft` resolves it:
   - `_seed_for` reads the approved row.
   - `_engineered_cir` returns None for a non-catalogue slug.
   - `fallback_constructions.plan()` builds the CIR (vessel, cosy, tote, panel, ...), or refuses
     it by name.
6. `cir.compile`, then `gate.certify`.

**`cir.draft` does not require a catalogue slug.** Only `seed_launch0` is registry-bound.

## Gates that apply to every producer after enqueue

- **Swarm claim** (`swarm/orchestrate.lane_hold`, :2055):
  - Agent-lane concurrency from the latest `swarm.allocate`.
  - `swarm/capacity.share_decision`: the #30 function mix (slots plus a 24h job-seconds window)
    and the #5 Fast/Flagship lane split.
  - A held job goes back to the queue.
- **Workers:** `BRAMBLELOOP_WORKER_THREADS` (default 3), activated by `capacity.worker_target`.
  It is one worker without an allocation, or when resources are saturated.
- **Spend:**
  - `finance/spend_policy`: monthly ceiling CA$100, escalation at 80%, per-provider caps.
  - Per-agent daily permission: `crochet_engineer` CA$4.00 (agents/registry.py:179).
  - `gateway/anthropic.check_budget_cad` before each paid call.
- **Bands:** `cir.draft` and the chain stages are band `proven_winner`; `gate.certify` and
  `chain.rebuild` are `truth_defect`.
- **Executive Orchestrator** (`autonomy.orchestrate`, 15 min): it cannot generate `cir.draft`
  (not in product_design's `generatable`).

## What ENG-SUPPLY changes (slice 1)

`brambleloop/src/brambleloop/products/supply.py` is the one admission door.

**Producers offer, they do not enqueue.**
- A, B and C call `supply.offer(...)` with exactly the payload and `draft:<slug>` key they used to
  enqueue.
- The offer is recorded durably (`supply.offered`) and admitted at once if there is room.
- Otherwise it waits in the supply queue.
- A re-offer of a waiting key adds no row.

**Admission** runs from `supply.admit` (new cadence, 15 min) and `chain.rebuild` (hourly). A
candidate is admitted only when every one of these holds; each run records every admission and
refusal with its reason (`supply.admission`):

| Factor | Reading | Bound (default) |
|---|---|---|
| Free worker capacity | `swarm.capacity.worker_target` → WIP ceiling = 2 × active workers | `MAX_WIP = 4` (env `BRAMBLELOOP_SUPPLY_MAX_WIP`, hard cap 8). One worker → 2, the historical limit |
| Queue depth and age per stage | Due PENDING/FAILED jobs of each chain stage | Oldest due job ≤ 6h |
| Expected work per stage | Mean measured job-seconds per stage (7d), else 300 s labelled ESTIMATED | Due backlog ≤ 2h of expected job-seconds per worker |
| Model and image cost | `spend_policy.binding_ceiling`: month remaining vs (in-flight + 1) × expected product cost (measured from `CostEntry.product_slug` over 30d, else CA$5 labelled ESTIMATED); month below the 80% escalation share; `crochet_engineer` / `publishing` daily permission not spent | Unreadable spend refuses (UNKNOWN is never PASS) |
| Blocked / waiting products | `waiting_on`: an open physical test, a certified release needing a sample with none completed, or an open owner action naming the product. These hold **no** WIP slot unless a job is RUNNING. Finished, dead-lettered and cancelled chains hold nothing | — |
| Family diversity | Family from the offer, else the pool seed, else the slug | `MAX_PER_FAMILY = 1` in flight |
| Research demand | Research-backed originals before static-pool re-promotions, then measured demand (radar adjusted score) descending, unknown last, then oldest | — |
| Trickle | `MAX_ADMIT_PER_RUN = 1` | A freed slot never becomes a burst |

**Ordering and refusals:**
- Launch-0 keeps first claim on a freed slot (owner launch scope, D-W4-LAUNCH-SCOPE). While research
  offers wait, it holds at most `limit − 1` slots, so research supply is never starved. The yield is
  recorded.
- One candidate's refusal (in flight, family) never stops the loop. Only a global refusal
  (capacity, backlog, cost) refuses everything, and it is named on every candidate.
- A slot frees automatically: by the next `supply.admit` run (≤ 15 min) after a chain finishes,
  dead-letters, or parks on a sample or the owner. There is no manual kick.
- **Restart-safe:** the queue is the audit log plus the durable job queue. An admitted offer is
  never admitted twice, even if its `cir.draft` job is later pruned (`supply.admitted` is read
  by key).

Nothing in ENG-SUPPLY certifies, lists, publishes or spends. Admission enqueues the ordinary
`cir.draft`, so every gate downstream is unchanged.

## Not changed / still open

- **The pre-engineering gate still holds new concepts WAITING without a vision judgement.** That
  is a correct gate: while `image_vision` is closed, the research stream is gated shut upstream of
  admission. Opening it is a capability or owner decision, not a supply change.
- **`draft:<slug>` is still a permanent key.** A slug drafts once; a revised concept needs a new
  slug.
- **The static pool is finite.** The research stream is the permanent supply:
  - `radar.concept_intake` every 6h.
  - `research.sweep` daily.
  - `creative.tournament` / `creative.expedition` weekly.
  - The `creative.family_engine` amplify step daily.
- **Product-family generation** (`creative.family_engine` amplify → `radar.score`) now enters
  through admission like every other promotion.
- **`product.pipeline` (F) is dead code.** It is left as is; it is not a supply path.
