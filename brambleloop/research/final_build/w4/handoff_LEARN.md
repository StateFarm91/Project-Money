# W4-LEARN handoff

Branch `claude/w4-LEARN` (worktree `.claude/worktrees/W4-LEARN`, from `claude/visual-investigation`
@ fee1cfe). Latest pushed SHA: see `git log -1 origin/claude/w4-LEARN` (updated each commit).
Diagnosis with evidence: `research/final_build/w4/LEARN_DIAGNOSIS.md`.

## Root cause (one line)

Production runs fcb982d (2026-09-25), which has no `improve.measure`, `improve.mine`,
`consume`, `policy_loops` or `learn.scan` — no producer and no consumer — so 12/12 cells
unmeasured, 0 lessons, CA$5K shown as 0.00. HEAD already has the wiring; deploying HEAD is the
integrator/owner step (no deploy in this lane). This lane made HEAD's numbers true and added what
can move before a sale.

## Items

| Item | Status | Evidence (tests in `tests/test_w4_learn_presale.py`) | Runtime consumer |
|---|---|---|---|
| Runtime cell counted shadow refusals as dead letters (3.0/day on a clean shadow run) | PROVEN fixed | `test_runtime_cell_counts_defect_dead_letters_only` | `improve.measure` handler → `measure.measure_runtime` (uses `queue.durable.classify_dead_letter`) |
| Miner published a false `defect` lesson from shadow refusals | PROVEN fixed | `test_mine_publishes_no_lesson_for_a_shadow_refusal` | `improve.mine` / nightly MINE |
| Release-gate blocks (pre-sale failures) never mined | PROVEN | `test_mine_turns_a_release_gate_block_into_one_routed_lesson` | `improve.mine` reads `store.release_gates` with `blocks_release` |
| Defect lessons had no consumer (routed to quality/pattern_engineering/runtime only) | PROVEN | `test_defect_lesson_moves_the_matching_gap_and_is_recorded_acted_on` (through the Worker), `test_without_a_lesson_...` (control) | `learn.scan` handler → `learn.metrics.calendar` → `consume.act` → `bus.acted_on` |
| Pre-sale internal outcomes (8 metrics) | PROVEN (6/8 measured on the shadow chain) | `test_presale_*` (5 tests) | `improve.measure` → `presale.record` (AuditLog `improve.presale`, per change); `improvement_status.summary()["presale"]` |
| Portfolio grouped revenue by receipt ref, not product | PROVEN fixed | `test_portfolio_attributes_revenue_to_the_order_product_not_the_receipt` | `measure_portfolio` via `Order.external_ref` |
| Finance read `finance.forecast` audits nobody writes | PROVEN fixed | `test_finance_reads_the_forecasts_the_company_actually_records` | `measure_finance` reads `scale.forecast` OperatingReadings (`scale.evidence.record_forecast`) |
| Provider shows cells/lessons/post-launch-only list | PROVEN | `test_provider_carries_cells_lessons_and_presale` | `learn.improvement_status.summary()["cells"]` |
| seo_search cell | DATA-GATED / OPEN wiring | no `Keyword` producer exists anywhere in src | WIRING REQUEST W4L-1 |
| market_radar cell | EXTERNAL-GATED | needs `BenchmarkObservation` (Etsy public reads) | `intel.observe` (exists) |
| product_creativity cell | DATA-GATED | needs a `creative.tournament` run (own cadence) | exists |
| pricing, customer_experience, portfolio, finance, growth | DATA-GATED (post-launch) | need sale/order/forecast/traffic rows | ingestion: `commerce.orders_ingest` → LedgerEntry/Order; `support.department` → SupportCase; `scale.evidence.record_forecast`; `growth.loops` GrowthLoop |
| CA$5K evidence gate | DATA-GATED (post-launch) | every count/condition is commercial; no pre-sale part executable | HEAD shows UNMEASURED (F-189); prod shows 0.00 only because it is fcb982d |
| Policy loops (promotion/rollback) | DATA-GATED | visual_gate_precheck has 19 outcomes, 0 positives (F1 undefined); defect watch needs 14 d; cost watch needs actual CostEntry; seo/support need customers | `improve.sandbox` → `runner.run` → `policy_loops.cycle` (exists) |

## Before / after (same three Launch-0 CIRs, real shadow chain, in-process Worker, network closed)

| | Production (fcb982d) | HEAD before this lane | After |
|---|---|---|---|
| cells measured | 0 / 12 | 5 / 13 (runtime wrong: 3.0 dead/day) | 5 / 13 (runtime 0.0, true) |
| pre-sale outcomes measured | — | — | 6 / 8 (gate first-pass 1.0, Product Truth refusals 0.0, render QA blocks 0.0, search certificate 0.0, release gates 0.0, time to publish request 0.10 h; creative survival + cost per ready UNMEASURED) |
| lessons routed / acted on | 0 / 0 | 1 (false) / 0 | release-gate lesson routed / 0 acted (no learner topic matches a taxonomy gap — honest) |
| lesson changes a decision | no consumer | no consumer for defects | proven through the Worker (unit-level), acted_on recorded only on a moved rank |

## Tests run (focused)

test_w4_learn_presale 12/12; test_measure 7, test_mine 7, test_improve 32, test_improve_handlers 8,
test_improve_director 14, test_w3_k10_learn 23, test_cert_learning 15, test_v11_learn_loops 18,
test_learn_launch 13, test_cert_improve_autonomy 20 — 0 FAIL (remaining guard tests: see
latest commit message / below).

## Wiring requests

- **W4L-1 (owner of runtime/release.py listing.seo or intel):** write `Keyword` rows for the
  queries each listing answers (phrase, covered_by=[slug]) — the `seo_search` cell's declared
  source has no producer. Not done here: `intel.insights_budget` reads Keyword rows as
  researched-query snapshots, so a producer must be agreed with that reader.
- **W4L-2 (CC, app/main.py `_improve`):** add rows from
  `learn.improvement_status.summary(db)["presale"]` ("pre-sale outcomes measured: N / 8",
  labelled internal) and `["cells"]["post_launch_only"]`, so the owner sees what is
  data-gated instead of only "0 measured".
- **W4L-3 (integrator/owner):** deploy the integration branch; production's zeros are the
  undeployed build (fcb982d).

## Next deterministic action

Rerun `scratchpad/proof.py`-equivalent after merge to refresh the before/after table; then
W4L-1 once the intel owner agrees the Keyword semantics.
