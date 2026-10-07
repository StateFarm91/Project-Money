# W4-LEARN — why the Improvement system reads "12 cells, 0 measured, 0 lessons acted on"

Lane W4-LEARN, branch `claude/w4-LEARN` (from `claude/visual-investigation` @ fee1cfe).
Evidence gathered 2026-10-06T23:57Z – 2026-10-07T00:05Z. Read-only network only (two GETs to
production). Nothing deployed, nothing written to production.

## 1. Root cause #1 (dominant): production runs code that has no measurer, no miner and no consumer

| Evidence | Observation |
|---|---|
| `GET https://brambleloop-os-production.up.railway.app/health` | `build.commit = fcb982d57e29` (branch `claude/repository-setup-nc9x6o`, committed 2026-09-25T22:30Z); `worker_started_at 2026-09-25T22:31Z`, worker alive |
| `git ls-tree fcb982d brambleloop/src/brambleloop/improve/` | no `measure.py`, no `mine.py`, no `consume.py`, no `policy_loops.py`, no `runner.py` |
| `git show fcb982d:.../runtime/worker.py` | cadences `improve.nightly`, `improve.weekly`, `improve.retrospective` only — no `improve.measure`, `improve.mine`, `learn.scan` |
| `GET /api/improve` (production) | keys `retrospective, compounding, cells, governance` only (no `realised_benefit`, `director`); `unmeasured_cells` = all 12; every cell `history: []`; `compounding = {lessons: 0, routed: 0, acted_on: 0, cells: 12}` |
| `git rev-list --count fcb982d..fee1cfe` | 665 commits on the integration line not deployed |

At fcb982d `cells.record_capability` had **no runtime caller** and `bus.publish` / `bus.acted_on`
had **no runtime caller** (the code comments in `improve/measure.py`, `improve/mine.py` and
`improve/consume.py` on HEAD record exactly this). So in production the zeros are not
"shadow-mode suppression" and not "insufficient experiments": there is no producer. The
dashboard's "12 cells" is itself the fingerprint of the old build: HEAD has 13 (F-799 `learn`).

The CA$5,000 model's "0.00" has the same cause: HEAD (F-189) reports
`UNMEASURED / insufficient commercial evidence` while the #275 gate is unmet; fcb982d predates
that and renders the modelled bound as 0.00. `GET /api/war-room` returns 404 in production
(also absent from fcb982d).

**Remedy:** deploying the integration branch. That is not this lane's action (brief: no deploy,
no Railway mutation) — it is an integrator/owner step. Everything below is about what HEAD does
once deployed, and what this lane fixed so the deployed numbers are true.

## 2. What HEAD produces on a real shadow run (runtime proof, not a seeded fixture)

Fresh SQLite, SHADOW, network closed (proxy -> 127.0.0.1:9), in-process `Worker`, the three
Launch-0 CIRs enqueued at `cir.compile`; the system carried them through 30 jobs (cir.compile →
gate.certify → gate.lanes → listing.draft → assets.build → pricing.position → listing.seo →
launch.plan → marketing.schedule → store.publish). Then `improve.measure`, `improve.mine`,
`learn.scan` and `policy_loops.cycle` on that database (scripts kept in the lane scratchpad;
re-runnable via `tests/test_w4_learn_presale.py::test_runtime_shadow_chain_*` — see handoff).

| Cell | HEAD reading | Why / gate |
|---|---|---|
| pattern_engineering | **1.0** (3/3 certified) | measured |
| quality | **0.0** escaped defects over 3 released | measured |
| creative_assets | **0.0** blocked of 19 assets | measured |
| runtime | **3.0 dead letters/day — WRONG** | all 3 "dead" jobs are `store.publish` refused by design in SHADOW ("capability not enabled"). Fixed in this lane (§4). |
| learn | **0.0** (0 of 16 source-backed gaps covered) | measured after `learn.scan` |
| seo_search | UNMEASURED | no `Keyword` row: keywords come from marketplace research (Etsy public reads) — DATA-GATED on the read credential/benchmark ingestion |
| market_radar | UNMEASURED | no `BenchmarkObservation`: DATA-GATED on marketplace reads |
| product_creativity | UNMEASURED | no `creative.tournament` audit in this run (the tournament runs on its own cadence in production; not exercised by the chain) |
| pricing, customer_experience, portfolio, finance, growth | UNMEASURED, `data-gated` | need a sale / order / attributed revenue / forecast / traffic — POST-LAUNCH ONLY |

Lessons on HEAD from the same run: `improve.mine` published exactly **one** lesson —
`dead:store.publish:capability not enabled`, subject `defect`, routed to quality,
pattern_engineering, runtime. Two defects in that:

1. **It is a false lesson.** A shadow-phase refusal is the system obeying the phase, not a defect
   (same contamination as the runtime cell).
2. **Root cause #2: no consumer for the routed cells.** Runtime consumers of the lesson bus
   (`consume.matching` → `bus.acted_on`) exist only for `market_radar` (radar.score),
   `seo_search` (listing.seo tag slots) and `customer_experience` (support.mine). `defect`
   lessons route to quality / pattern_engineering / runtime, none of which reads its inbox, so a
   defect lesson can never be "acted on" — structurally 0, before or after launch.
   `bus.brief_lessons` (product_creativity) records provenance but never `acted_on`.

Policy loops (`improve/policy_loops.py`) on the same run: `visual_gate_precheck` has 19
observed decisions but no positive outcome (the gate blocked nothing), so F1 is undefined —
honest UNMEASURED, not a bug. `pattern_defect_watch` needs 14 days of post-certification
observation; `release_cost_watch` needs actual `CostEntry` rows (0 — no paid model call in
shadow); `seo_lesson_match` / `support_lesson_match` need listing outcomes / support cases
(post-launch). `improve.replay` (job priority) needs ≥20 jobs over ≥3 days — production has
weeks of job history, so it is executable there once deployed.

## 3. Classification of the zeros

| Cause | Applies to | Executable before sales? |
|---|---|---|
| Missing runtime wiring in the deployed build (no producer/consumer) | all 12 cells, all lessons, CA$5K "0.00" | yes — by deploying HEAD (integrator/owner; not this lane) |
| Measurement contamination (shadow refusals counted as dead letters / mined as defects) | runtime cell, mine | yes — fixed here |
| No consumer for routed cells | defect / instruction_clarity / sizing lessons | yes — a `learn` consumer added here (§4) |
| Missing marketplace data | seo_search, market_radar | needs read-only Etsy research ingestion (EXTERNAL/DATA-GATED) |
| Missing customer evidence | pricing, customer_experience, portfolio, finance, growth; seo/support policy loops; the CA$5K gate | POST-LAUNCH only |
| Shadow-mode suppression | none found — measurement and mining run in SHADOW | — |
| Insufficient experiments | predictor loops (no positives / observation window) | partly: internal pre-sale experiments added (§4) |

## 4. CA$5,000/month model — evidence gate (`scale/confidence.py`, #275)

Counts: `selling_skus ≥ 4`, `product_families ≥ 2`, `outside_customers ≥ 40`, `orders ≥ 60`,
`acquisition_loops ≥ 2`, `months_of_history ≥ 3`; plus eight qualitative conditions
(no open policy risk, conservative scenario near target, seasonal/evergreen balance, observed
bundle AOV, low defect/refund severity, downside near target, …). Every count is a count of
sales/customer/traffic rows, and every condition is about observed commercial behaviour.
**No part of the gate is executable before sales.** The only pre-sale-movable layers of the
ladder are non-critical architecture signals (restores proved, publish refusals, dead letters),
and the probability is a minimum over critical layers, so they cannot raise it. The correct
pre-sale display is `UNMEASURED / insufficient commercial evidence` (HEAD already does this);
the post-launch ingestion path that will feed the gate is `commerce.orders_ingest` →
`LedgerEntry(category="sale")` (verified present on HEAD, exercised by
`scripts/shadow_rehearsal.py` against the fake Etsy receipt feed).

## 5. Resolution in this lane

See `handoff_LEARN.md` for the row-by-row status, tests and before/after numbers.
