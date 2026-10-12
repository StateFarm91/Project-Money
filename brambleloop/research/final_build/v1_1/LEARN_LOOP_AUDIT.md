# Learn / continuous self-improvement — loop audit (v1.1 lane B)

Date: 2026-10-06 (UTC). Base: `claude/visual-investigation` @ 0694fb7. Branch: `claude/v11-B`.
Scope: `src/brambleloop/improve/**`, `src/brambleloop/learn/**`, against directive §4 and F-891,
F-918, F-919, F-920, F-922.

**What "closes" means here.** A loop closes when a measured outcome produces a change that a
later decision **in code the live runtime reaches** actually reads, and the change can be
measured again afterwards and rolled back. Writing a lesson, recording a capability point or
opening an owner card is not closing a loop. "Live runtime reaches" means a registered handler
on a `runtime.worker.CADENCES` entry calls it, directly or transitively.

## 1. Verdict per mechanism (before lane B)

| Mechanism | Observe | Propose | Shadow eval vs baseline | Promote / rollback | Consumer that changes later behaviour | Verdict |
|---|---|---|---|---|---|---|
| `improve.replay` (job-priority policy) via `improve.sandbox` / `improve.monitor` | historical Job rows | challenger neighbours, `cells.propose` | league replay, shared set + holdout | scoring tier auto-promote, `league.rollback` verified | `swarm.orchestrate.priority_for` on every enqueue | **CLOSED** (proved by `test_cert_improve_wave`), but see defect D-B1 |
| `self_audit` trial (teardown standard floor) | teardown self-audits | teardown finding → `cells.propose` | `enforce.catalogue_scores` | `adopt_floor` / `drop_floor`, verified | `release_gates.for_publish`, support pattern_help obligations | **CLOSED** (adopts a standard; changes no artefact) |
| `counterfactual_rollback` trial (self-review `declining_capability`) | capability points | `profiles` self-review | baseline of the last promotion | promotes, **but no executor** | none — a promotion records a capability point only | **DEAD END** (promotion on paper) |
| `improve.league` routing / image challengers (`bootstrap`) | config registry | `bootstrap.register_routing_challengers` | needs recorded runs; nothing produces them (a model call = spend) | code-mirrored → owner card only | none automatically | **DEAD END by design** (spend-gated). F-922 left to lane I |
| Lesson bus: `mine` → `bus.publish` → `consume.matching` | incidents, refusals, dead letters | lessons (text) | **none** | **none** | radar score nudge (±0.06), pattern-engineering band nudge, SEO tag slots, support case lessons, creative brief | **OPEN LOOP**: behaviour changes, effect never measured, no baseline, no rollback ("benefit: unmeasured") |
| `improve.measure` | capability per cell | — | — | — | — | measurement only (many cells data-gated in shadow) |
| `improve.monitor.sweep` (capability) | capability points | — | — | `cells.monitor` revert | — | works for non-trial rows; **defect D-B1** for trial rows |
| `profiles` self-review | own rows | `never_measured`, `declining_capability` | see above | see above | — | proposes; only `declining_capability` reaches a trial (dead end above) |
| `director` | open proposals | — | — | conflict blocking, weekly `execute_approved` (scoring tier) | via `cells.promote` | governance (works) |
| `nightly`, `weekly`, `evolution`, `velocity`, `freshness` | rows | owner cards (architecture, STOP list, metric revisions) | — | — | owner decides | reporting + owner cards; no automatic behaviour change (correct for architecture changes) |
| `roi`, `roles`, `tiers`, `upgrades`, `governance` | — | — | — | evidence/tier/authority gates | — | governance infrastructure (works; reused) |
| `learn/` (`service`, `api`, `runtime`) | pattern CIRs, support cases → topic gaps (`learn.scan`, hourly) | lessons authored by people | human review per revision | — | help links in PDF/listing/support, gated on an owned HTTPS origin | **not a self-improvement loop**: the Learn *content* product (crochet lessons). Live scan; no automatic content |

### Defect found and fixed

**D-B1 — the capability monitor reverts trial-metric promotions on paper.**
`improve.monitor.sweep` judged *every* promoted improvement against its cell's newest capability
point. For a trial-metric promotion (job-priority replay, self-audit floor) the result is in the
trial's units, not the cell's: a replay on-time share of 0.6 was compared with the `runtime`
cell's dead-letters-per-day reading of 0.0, judged "degraded", and `cells.monitor` wrote
`REVERTED` **without running the rollback executor**. The registry kept the challenger as
incumbent and `priority_for` kept reading it — exactly the C-81 failure. In production
`improve.measure` writes a runtime point daily, so every job-priority promotion would be
"reverted" on paper at the next `improve.monitor`. Reproduced on base
(`evidence/B_DB1_monitor_defect.txt`); fixed by skipping trial-metric rows in the sweep (they are
judged by `runner.monitor_trials`, which executes and verifies). Regression test:
`test_capability_monitor_no_longer_reverts_a_trial_promotion_on_paper`.

## 2. What lane B built: five measured launch loops

`improve/policy_loops.py` generalises the one loop that closed (job-priority replay) to the
five launch decisions, plugged into the **existing** pipeline rather than a parallel one:
proposals are ordinary `Improvement` rows with trial `policy_loop`, registered in
`runner.TRIALS / EXECUTORS / MONITORS / ROLLBACKS / VERIFIERS`, versions are `ConfigVersion`
rows (kind `scoring`, so the league defers promotion to the sandbox), promotion goes through
`cells.promote` (separation of duties, Director, scoring-tier cooldown/ceiling).

| Loop | Param (default, bounds) | Outcome rows | Metric / guardrail KPI (F-918) | Proposer → challenger (F-919) | Consumer | Consumer reached live today? |
|---|---|---|---|---|---|---|
| `seo_lesson_match` | `min_shared` (2, 1–4) | `listing_outcomes` | CTR / conversion | experiment_designer → quality | `consume.matching(cell="seo_search")` ← `runtime.release` listing.seo | **Yes, the read.** Decision logging needs W-B1 (subject) |
| `support_lesson_match` | `min_shared` (1, 1–4) | `support_cases` | resolved-without-escalation / resolved share | experiment_designer → quality | `consume.matching(cell="customer_experience")` ← `runtime.release` support.mine | **Yes, the read.** Decision logging needs W-B1 |
| `pattern_defect_watch` | `min_topic_defect_rate` (0.5, 0.05–1) | `pattern_versions` × `incidents` / troubleshooter cases | F1 of extra-review flags / review load ≤ 0.5 | failure_miner → pattern_engineering | `defect_watchlist`, `requires_extra_review`; `next_work` (`quality.extra_review`, lesson-gap priority) | via lane A's `next_work` enqueue; release-gate read = W-B3 |
| `visual_gate_precheck` | `precheck_flag_rate` (0.5, 0.05–1) | `listing_assets` approved / blocked | F1 of pre-check flags / review load ≤ 0.5 | experiment_designer → quality | `visual_precheck`; `next_work` (`visual.precheck`) | via lane A; render-path read = W-B4 |
| `release_cost_watch` | `early_cost_flag_cad` (1.0, 0.1–20) | `cost_entries` (actual `amount_cad` only) | F1 of cost-review flags vs > 2× median release cost / review load ≤ 0.5 | cost_optimiser → reliability_engineer | `cost_watch`; `next_work` (`finance.cost_review`) | via lane A. Flags only — never moves a ceiling |

Each loop now has, in code and exercised by tests:

1. **Durable proposal record** — `learn_proposals` (every state: REFUSED, CHALLENGED_OUT,
   NO_GAIN, MEMORY_SKIPPED, HELD, PROPOSED, PROMOTED, REJECTED, ROLLED_BACK) linked to the
   `Improvement` row and `ConfigVersion`.
2. **Shadow evaluation against a baseline with a metric** — deterministic, on a frozen
   decision set (ids + outcome fingerprint), newest 20 % held out; replay estimator for the two
   lesson loops, exact counterfactual F1 for the three watch loops (features computed only from
   earlier subjects). Evidence floors are UPPERCASE constants in a protected package, so the
   governance scan protects them too.
3. **Automatic promote / rollback with guardrail check** — `improve/invariants.py`:
   hard-coded `PROTECTED_INVARIANTS` (product_truth, customer_safety, accounting_truth,
   authorization, security, spend_controls, evidence_requirements, protected_gates) +
   every protected constant `governance` discovers + "undeclared parameter = protected" + hard
   bounds. Applied at proposal, at the cross-agent challenge, at execution, and on the
   consumer's read (a tampered registry value falls back to the code default).
4. **A consumer that changes subsequent behaviour** — table above.
5. **Post-change measurement → retain or verified rollback → persisted lesson**
   (`learn_policy_lessons`), and **memory changes the next decision**: a value rolled back or
   challenged out in the last 30 days is not re-proposed (`MEMORY_SKIPPED`, audited).

Where it runs: `policy_loops.cycle` is called at the start of `improve.runner.run`
(the `improve.sandbox` cadence, daily, already scheduled); monitoring/rollback run in
`runner.monitor_trials` (the `improve.monitor` cadence). **No new handler or cadence** was
needed — adding one would also break `test_roles` / `test_swarm_runtime` without shared-file
edits.

## 3. Still open (honest)

* **Decision logging for the two lesson loops needs W-B1**: `runtime.release` must pass
  `subject=` to `consume.matching`. Until then the consumer *reads* the promoted threshold live,
  but the loop records no new decisions in production, so it stays `UNMEASURED`.
* **Pattern / visual / cost consumers are reached through `next_work`** (lane A's orchestrator)
  until W-B3/W-B4 wire a direct read into the release gate / render path. They only ever add
  scrutiny.
* **Market Radar and Pattern Engineering lesson nudges** (`consume.score_adjustment`,
  `HEURISTIC_KEY`) remain unmeasured open loops; same pattern applies (a `radar_lesson_step`
  loop) once concept outcomes are joinable.
* **Counterfactual-rollback promotions** still execute nothing (dead end above).
* **F-922 cost-aware routing**: `improve/` has only the code-mirrored routing registry
  (owner-card only, no run producer); left to lane I as instructed.
* In shadow there are no listing outcomes, support cases or real costs, so in production every
  loop reads `UNMEASURED` today. The provider reports exactly that (`status: UNKNOWN` on an
  empty DB), never zeros.
