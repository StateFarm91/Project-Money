# Self-improvement: department x KPI x lesson-consumer table (ENG-IMPROVE slice 1)

Generated from `brambleloop.improve.department_loops.DEPARTMENTS` and `improve.tuning.TUNABLES` on
2026-11-20. The static check reads each consumer module's source for its call. The **live** state of
each consumer (ACTIVE, DORMANT or MISSING) and each KPI value are not in this file. They are computed
from production rows by the `improve.self_tune` job and shown in Mission Control → Autonomy →
"Self-improvement (per department)".

Production has not been read for this table. The readback token is not available to this session, so
no live value is claimed here.

Rules (code-enforced, `department_loops.table`):
- A department with no consumer is a **FINDING** (`missing_consumer`). It is never a pass, and the job
  files an engineering change request for it.
- A consumer that is declared but did not act on a lesson in 30 days is **DORMANT**. That is also a
  FINDING (`dormant_consumer`) with a change request.
- A consumer whose call site has vanished from its module is **MISSING**.
- A KPI is **UNKNOWN** below 20 finished runs per window. The trend is computed with a two-proportion
  z-test and is never fabricated.

| Department | KPI (from rows) | Observation stream | Lesson evidence threshold | Consumer (call site) | Static check | Tunables declared (reader wired) |
|---|---|---|---|---|---|---|
| Research (`research`) | useful yield of `radar.`, `mjs.`, `intel.`, `research.`, `culture.` jobs | `jobs` rows of those types | `lessons` routed to `market_radar`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.runtime.pipeline` (lesson: market_radar) - radar.score nudges a concept's score by matched lessons<br>`brambleloop.intel.watchlist` (lesson: market_radar) - watchlist opportunities checked against lessons | PRESENT, PRESENT | `research.focus_weight.amigurumi` (not wired), `research.focus_weight.home_decor` (not wired), `research.watchlist_period_factor` (not wired) |
| Concept & creative (`concept_creative`) | useful yield of `creative.`, `seasonal.` jobs | `jobs` rows of those types | `lessons` routed to `product_creativity`, `portfolio`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.seasonal.daily` (lesson: portfolio) - seasonal remerchandising shaped by matched lessons | PRESENT | `concept.lesson_nudge_step` (not wired) |
| Pattern engineering (`engineering`) | useful yield of `cir.` jobs | `jobs` rows of those types | `lessons` routed to `pattern_engineering`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.runtime.pipeline` (lesson: pattern_engineering) - engineering lessons attached to a CIR draft | PRESENT | `engineering.lesson_match_words` (not wired) |
| QA / Product Truth (`qa`) | useful yield of `gate.`, `physical.` jobs | `jobs` rows of those types + `learn_decisions` | `lessons` routed to `quality`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.learn.improvement_status` (policy_loop: pattern_defect_watch) - defect watch queues extra review of releases | PRESENT | `qa.recheck_period_factor` (not wired) |
| Visual (`visual`) | useful yield of `assets.`, `visual.` jobs | `jobs` rows of those types + `learn_decisions` | `lessons` routed to `creative_assets`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.learn.improvement_status` (policy_loop: visual_gate_precheck) - visual pre-check flags assets before the gate | PRESENT | `visual.prompt_template` (not wired) |
| SEO & listing (`seo_listing`) | useful yield of `listing.`, `seo.`, `store.` jobs | `jobs` rows of those types | `lessons` routed to `seo_search`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.runtime.release` (lesson: seo_search) - lesson-matched queries get a tag slot | PRESENT | `listing.title_template` (not wired) |
| Pricing (`pricing`) | useful yield of `pricing.` jobs | `jobs` rows of those types | `lessons` routed to `pricing`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | **NONE: FINDING (missing_consumer), ECR filed by improve.self_tune** | n/a | `pricing.test_arm` (not wired) |
| Marketing (`marketing`) | useful yield of `growth.`, `marketing.`, `ads.` jobs | `jobs` rows of those types | `lessons` routed to `growth`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.growth.content` (lesson: growth) - content pieces shaped by matched lessons | PRESENT | `marketing.content_lesson_words` (not wired) |
| Finance (`finance`) | useful yield of `finance.`, `commerce.` jobs | `jobs` rows of those types + `learn_decisions` | `lessons` routed to `finance`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.learn.improvement_status` (policy_loop: release_cost_watch) - early cost-review flags (never moves a ceiling) | PRESENT | `finance.cost_flag_rank_weight` (not wired) |
| Ops / reliability (`ops`) | useful yield of `ops.`, `swarm.`, `autonomy.` jobs | `jobs` rows of those types | `lessons` routed to `runtime`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | **NONE: FINDING (missing_consumer), ECR filed by improve.self_tune** | n/a | `ops.queue_check_period_factor` (not wired) |
| Customer support (`support`) | useful yield of `support.` jobs | `jobs` rows of those types | `lessons` routed to `customer_experience`; VERIFIED = confidence measured/confirmed + evidence_ref; APPLIED = `acted_on_by` | `brambleloop.runtime.release` (lesson: customer_experience) - lessons attached to open support cases | PRESENT | `support.lesson_rank_weight` (not wired) |

## Findings (structural, before any production reading)

- **Pricing: no consumer.** Nothing reads `pricing` lessons. A FINDING, with an ECR filed by the job.
- **Ops / reliability: no consumer.** Nothing reads `runtime` lessons. A FINDING, with an ECR filed by
  the job.
- **Policy-loop consumers are weaker than lesson consumers.** QA, Visual and Finance count as consumers
  through `learn.improvement_status.next_work`, which reads the learned thresholds. Per
  `policy_loops.LOOPS` itself, these thresholds do not yet gate the release, render or cost paths (wiring
  requests W-B3/W-B4). Each counts as ACTIVE only when it writes `learn_decisions` rows in the window.
- **No tunable has a wired reader yet.** All 13 allowlisted tunables are declared and guarded, and the
  champion/challenger engine is tested. No production code yet reads `tuning.value(...)`, so no live
  challenger can run until a reader is wired (slice 2). The panel shows this as "not wired". It is not
  reported as tuning.
