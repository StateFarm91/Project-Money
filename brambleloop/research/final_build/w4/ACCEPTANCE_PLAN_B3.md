# W4-FMBATCH1 → Batch 3: production acceptance checklist

Written 2026-10-26 on `claude/w4-FMBATCH2`, cut from the frozen FMBATCH1 head `62fcf5ed`.

**What this covers.** Every row this branch holds at E: built, integrated and tested on the branch, and waiting only for a release. The rows that are gated on a deploy *and* something else are listed separately at the end.

**What "accepted" means.** A row is accepted when the named check passes on production at the Batch 3 commit. Everything below is read-only, and every check needs one of three things:

- nothing (a public read);
- the operator credential (`Authorization: Bearer $OPS`);
- time for a cadence to run.

**Rules for reading the checks.**
- UNKNOWN or UNMEASURED is never a pass. It is a legitimate *state* only where the row says so, for example when no buyer exists yet.
- No check spends, publishes, writes to Etsy or changes the phase.

**Columns.**
- **When**: how long after the deploy the evidence exists. "Immediate" means on the first request.
- **Kind**:
  - **R**: runtime, observable in production.
  - **B**: build-side tool. It never runs in production; it is accepted by its test passing at the merged commit, which the integration checklist already runs.
  - **D**: shown on the dashboard.

## 0. Before anything else: deploy-level checks

| Check | Pass |
|---|---|
| Boot and schema | `/health` returns 200 at the Batch 3 SHA. The only schema change in this branch is two additive, nullable columns on `research_tasks` (`deadline`, `detail`, from batch R). `core.db.create_all` adds them through `core.migrate.apply`; no manual migration is needed. |
| `/api/verify` | `ok` is true and `checks.no_satisfied_owner_action_presented.ok` is true. `status` is `OK` only if `readbacks.smoke_matrix.verdict` is `PASS` (review N-6). If it reads `UNKNOWN` or `DEGRADED`, read `smoke_matrix.unknown` and `smoke_matrix.degraded` before accepting the rows below. |
| Route auth (review N-1) | Without a credential: `/api/finance/owner`, `/api/opportunities`, `/api/evidence?subject=x`, `/api/products/lifecycle`, `/api/company/departments/executive` and `/api/spend-report/governance` each return 401. With `$OPS` they return 200. |
| No owner-inbox text in public (coordinator decision) | Unauthenticated `/`, `/m`, `/api/build`, `/api/console`, `/api/owner-actions` and `/api/war-room` contain no OwnerAction text. Spot check: take one open card's `action` from `/api/owner-actions` with `$OPS`, then confirm it is absent from the unauthenticated bodies (where it reads `[owner decision: see /cc/]`). `/` shows a count linking to `/cc/`. |
| Retention guard (026365a1) | At the first `retention_sweep` (24 h): the newest `ops.retention` audit row exists and no `ops.retention_refused` row was written (a refusal would carry `unknown_read_actions`). The row's `policy.protected_actions` includes `visual.hero_review`, `gate.certified` and `cir.compiled`. No schema change; the scan reads the `.py` sources the image already ships (`COPY src`) and takes ~3-15 s inside the daily job. |

## 1. Runtime rows (R / D)

| Row | When | Production check | Pass |
|---|---|---|---|
| F-010 | 24 h (`etsy_taxonomy`) | The newest `listing.taxonomy_refresh` job output has a `drift` block with `requeue_enabled: false`. | No `listing.seo`, `launch.plan` or `store.publish` job carries a `:tx` idempotency key. A drift, if any, appears as a P1 `taxonomy-drift:<slug>` incident plus an OwnerAction `taxonomy_drift:<id>`. With no drift the block reports an empty list; that is a pass. |
| F-139, F-140, F-149 | 15 min (`health_sweep`) | The `ops.health` output carries the hygiene section: a homogeneous-backlog incident, flapping and stale-signal defects, and disk growth samples. | Disk samples are present; at most one incident per homogeneous backlog. |
| F-092, F-093, F-094 | Immediate (`/api/verify` / scale dependency report) | `scale.dependency` report: provider register, the `ai_provider` axis, the diversification trigger. | `ai_provider` reads existential unless a fallback-drill row is younger than N days; the trigger lists its reasons. |
| F-099 | 24 h | `gateway.provider_snapshot` audit row. | One snapshot row; a `gateway.provider_change` row only if something changed. |
| F-150 | B | — | `test_w4_fmbatch1_failclass` at the merged commit. |
| F-200, F-201, F-670, F-488 (D) | Immediate | `/` renders in owner-decision order: health, waiting-on-owner (a count), launch blockers, …, with folded tables. | Light/dark tokens are present (`prefers-color-scheme`). The Trends block has two SVG sparklines with "drill down" links. The headline has a "Critical path (build steps)" card, which reads UNMEASURED until the first `build.tick` and then shows a number. |
| F-653 (D) | Immediate | `/m` at phone width. | One column; tables scroll in their own box; owner decisions shown as a count only. |
| F-394, F-470, F-489 | 1 h | `/api/useful-work` and `/api/swarm` show resource and parallel-window readings. | Readings are present; an unreadable resource shows UNKNOWN, never saturated. |
| F-398 | 24 h (`improve.nightly`) | Improvement audit record (`improve.cells.audit_record`). | A promoted change carries an evidence fingerprint. With no promotion the gap list is reported; that is a pass. |
| F-621, F-661, F-668, F-729 | Immediate (owner session) | `/api/cc/*` company, executive, agents and autonomy blocks. | Each envelope has `status` and `reason`; the autonomy block carries `useful_work`. |
| F-431, F-405, F-408, F-411, F-419, F-420, F-426, F-432, F-435, F-444, F-449, F-413, F-421, F-422, F-423 | 1 h (`learn_gap_scan`) | The newest `learn.scanned` audit row has `research.opened`, `overdue_stopped`, `search_strategy` and `run`. | Each key is present. `run.fetches.enabled` is false unless the owner has switched fetches on. Tasks opened in production carry `detail.search_rounds`. |
| F-153, F-157 | At the deploy | The `ops/deploy.sh` output and the release record's signing evidence. | It states the signing status (`unavailable` today), and the deploy refuses if `BRAMBLELOOP_SIGNING_REQUIRED=1` and the status is not `verified`. |
| F-381, F-380 | At the deploy | `ops/deploy.sh` readback, then `rollback_decision`. | A P0 is reported with the exact rollback command, and nothing is pushed unless `AUTO_ROLLBACK=1` **and** `--auto-rollback-reason` were given on that run (review N-4). |
| F-107 | Immediate | `/api/spend-report` `value_units` attribution. | Every bucket has a `what_it_bought` line; unattributed spend is counted, not dropped. |
| F-089 | Immediate ($OPS) | `/api/physical-truth`. | Each Class B/C product shows tester, stage and due date. An unparseable date gives `overdue: None` and is counted in `overdue_unknown`. |
| F-096 | — | No production check without a paid drill (`compat_pack` has no live caller). | Accepted at B level by `test_w4_fmbatch1_compat`. A live run is an owner-approved paid drill. |
| F-190, F-194 | Immediate | `/api/seasonal` (cohort counts) and the scale confidence progress text. | `counts_by_cohort` is present, and evidence-gate progress shows per class. |
| F-357 | 24 h (`culture_sweep`) | `/api/seasonal` `childrens_demand_windows`. | After the first sweep each sub-category shows MEASURED (12+ months returned by Wikimedia) or a named failure; `baby_garments` may legitimately fail if the article is refused. Before the sweep it reads UNMEASURED, which is correct, not a fail. |
| F-198 | Immediate | `/api/build` gate-clearance section. | `owned_surfaces` lists `why_required` and is held until `live_listings`. |
| F-374 | 24 h | `improve` pricing-shadow trial. | The trial row is present. The price-at-outcome writer is in the listings lane (after the listings release). |
| F-389 | 24 h (`improve.league`) | `improve.cost_learning` output in the league cycle. | Present; a cost class without data reads UNMEASURED. |
| F-656, F-719, F-720, F-722 | 15 min (`executive_orchestrator`) | `/api/useful-work` and the orchestrator missions. | Pull order is RUN→GROW→IMPROVE, WATCHING spans are recorded, and the ready-work alarm names its diagnosis. Idle wakes are at most one per 5 min (`autonomy.orchestrate:idle:*` keys). |
| F-620, F-681 | Immediate ($OPS) | `/api/finance/owner`. | It has windows, ads, `cash_and_payout`, `unreconciled` (with `items` and `unreconciled_cad`) and `monthly_close`. Unauthenticated `/api/finance` has none of these keys. |
| F-827 (D) | Immediate | The Studio Learn card on `/`. | Lessons by state and learner-need coverage are shown. |
| F-467 | On an owner write | After any write to `/api/owner/*` or `/api/insights/*`, a `build.tick` job with trigger `gate_write` is queued within a minute. | A job row is present. |
| F-482 | B | — | `test_w4_fmbatch1_contracts` at the merged commit. The integrator records the merge in `ops/CONTRACT_CHANGES.md`; the api_routes pin at FMBATCH1's head is `556ba71935bfe4c4`. |
| F-550 | 24 h (`commerce_readings`) | `intel.etsy_ops_report` daily exceptions in the readings output. | Present; read-only (no Etsy write). |
| F-618 | Immediate | `/api/scale` run-rate / books use `analytics.metrics`. | Conversion, AOV and margin match `analytics.metrics` definitions; no source reads 0 when unmeasured. |
| F-549 | Immediate ($OPS) | `/api/etsy/scorecard`. | All 11 lines are present; `conversion`, `ads` and `oauth_api_health` read UNMEASURED until data exists. |
| F-671 | Immediate ($OPS) | `/api/product/<slug>/dossier` for a certified slug. | Every product-keyed table is listed, and an empty table is named. |
| F-465, F-452, F-466 | 1 h (`build_tick`) | `/api/build` `queue.critical_path`, and `fm_fanout` in the newest `build.tick` output. | `critical_path.length` ≥ 1, `gates_by_unblocked` lists gates, and `fm_fanout.unevaluable` lists gate keys with no live check. An `fm_unblocked` build event appears only when the set changes. |
| F-630 | 1 h | `/api/build` `queue.pre_launch_scope.phase == "shadow"`. | Each READY item has `pre_launch_scope`, and launch-serving items come first. |
| F-673 | Immediate ($OPS) | `/api/opportunities`. | Cards carry radar, arbitrage (UNMEASURED until rankable), feasibility and `next_experiment`. |
| F-723, F-417 | 2 h (`gallery_analysis`) / immediate ($OPS) | `/api/spend-report/governance`. | `learning_value` shows a `learning_value.expected` line per gallery batch at or above CA$0.25 and its realisation after the batch. `adoptions` lists every requirement and provider, with cost measured from cost entries. |
| F-624 | Daily (morning handoff) | Company memory `capability_audit:2026Q4`. | One row this quarter with `decisions` and both readings. A second handoff in the same quarter adds nothing. |
| F-407 | Immediate | `/api/policy` `knowledge.surfaces.*.source_tiers`. | Every URL is tiered, and an unknown host reads `unclassified`. |
| F-448 | On use ($OPS) | `POST /api/research/evidence` with a URL or terms. | Returns 200 with `recorded`; 401 without the credential. |
| F-475 | Immediate ($OPS) | `/api/evidence?subject=blanket`. | `searched` lists every corpus, including provenance, pod lessons, trend provenance and company memory. |
| F-490 | When it triggers | `parallelism_advice` (in the swarm allocation). | With 3+ defect dead letters in an hour or a fresh P0/P1, the advice is `scale_down` with `backpressure` reasons. Otherwise it is the governor's verdict. |
| F-581, F-582 | On use | Any `SpendGuard.set_limit("software:<tool>", …)`. | Refused without a `finance.tool_evaluation` decision_ref whose ROI exceeds its cost. No software scope exists today, so there is nothing to observe until one is proposed; that is a pass by absence. |
| F-667 | Immediate ($OPS) | `/api/company/departments/executive`. | All sections are present, including `inbound_tasks`; 401 without the credential. |
| F-694, F-690 | 6 h (`failure_mine`) | The newest `improve.mine` audit row has `readings_published`. | It has finance, policy and customer keys; each is a list, or UNKNOWN with a reason. |
| F-807, F-803, F-830 | 1 h (`learn_gap_scan`) | `learn.scanned` `graph_feeds`, and `/api/learn/graph?node=stitch:dc` (Learn editor credential). | `prerequisites` > 0, a `stitch:dc` → `stitch:hdc` prerequisite edge exists, and `search_sources` and `faq_nodes` are counted. |
| F-814 | Immediate ($OPS) | `/api/marketing/constellation/<slug>` for a product with a pattern. | Content, lessons, `faq`, `internal_links` and `filtered_out` are present. |
| F-824 | Immediate | `/learn/<slug>` for an approved lesson, if any exists. | The response has an `accessibility` report and `alt` text per diagram. With no approved lesson the page is 404, which is a pass by absence; accept again at the first lesson. |
| F-800 | Immediate (Learn editor) | `/api/learn/curriculum`. | The three tracks are listed with coverage. |
| F-357 retention entry | — | Covered by section 0's retention check. | — |

## 2. Build-side rows (B): no production acceptance

These are accepted when their tests pass at the merged commit. They never run in production, and nothing in them may write to it (coordinator decision, F-463).

| Rows | Tool | Test |
|---|---|---|
| F-485, F-476, F-492, F-462, F-457 | `ops/registry.py`, `ops/lock.py` | test_w4_fmbatch1_deadlock, test_w4_fmbatch1_dupwork, test_w4_fmbatch1_lane_stop, test_w4_fmbatch1_lease_scope, test_w4_fmbatch1_swarm |
| F-459, F-460, F-712, F-713 | `ops/integrate.py`, `ops/task_contract.py` | test_w4_fmbatch1_integrate, test_w4_fmbatch1_task_contract |
| F-494, F-484 | `ops/dispatch.py` | test_w4_fmbatch1_dispatch |
| F-455 | `ops/context_pack.py` | test_w4_fmbatch1_context_pack |
| F-415 | `ops/licenses.py` | test_w4_fmbatch1_licenses (also fails CI-style if a dependency lands unregistered) |
| F-496 | `app/hq_worker.py` (optional; not started by Batch 3) | test_w4_fmbatch1_hq_worker |
| F-146, F-150 | `run_tests.sh`, `scripts/classify_failure.py` | test_w4_fmbatch1_runtests_trap, test_w4_fmbatch1_failclass |
| F-156 | `ops/SIGNING_RECOVERY.md` | test_w4_fmbatch1_signing |
| F-864, F-868, F-869 | `ops/session_log.py` (log in the repository) | test_w4_fmbatch1_session_log |

## 3. Rows that need more than a deploy

| Row | What the deploy does not supply | What would accept it |
|---|---|---|
| F-699 | A registered prompt challenger running under a spend reservation (owner spend). | The owner approves a bounded challenger reservation, and one `improve.league` cycle records the challenger against the incumbent. |
| F-705 | A sandbox trial for each department cell that lacks one; trials need measurement data. | After the deploy, `improve.sandbox` records one trial per cell named in `/api/profiles` as lacking one. Cells with no data stay UNMEASURED. |
| F-096 | A live compat-pack run (a paid drill). | An owner-approved drill against the configured provider; `compat_pack` cost rows appear under purpose `compat_pack`. |
| F-374 | The price-at-outcome writer (listings lane). | After the listings release, outcome rows carry `price_cad`. |
| F-602, F-601, F-454, F-451, F-464, F-672, F-441, F-412, F-095, F-091 (B) | Partial by design; see FMBATCH1.md for each missing part. | Not acceptable from this branch alone. |
| F-483, F-579, F-652 imagery | Owner-gated (D-W4-FMBATCH1-BUILDSIDE; the F-652 decision). | Owner decisions. |
| F-463 | Blocked by design. | — |
