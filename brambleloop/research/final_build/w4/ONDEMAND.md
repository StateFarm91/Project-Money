# W4-ONDEMAND: run checks now instead of waiting for the schedule

Owner directive, 2026-10-11: remove unnecessary waiting. Branch `claude/w4-ONDEMAND`, based on
`claude/w4-INTEG2` at 61ddc18. Nothing is deployed. No Railway writes.

## What was built

All of this runs only the **existing** job types and handlers. No handler, budget, gate or
authority check was added, copied or bypassed.

### The "Run checks now" card (Home and Operations)

The card is `static/js/views/_checks.js`. For each check it shows the last result
(OK / not OK / running / never run), how long ago it ran, and whether that run was on demand.
Each check has one button, disabled during the check's cool-down.

| Check | Existing job(s) it queues | Step-up | Min interval | Why |
|---|---|---|---|---|
| `model` | `model.probe` | yes (external) | 60 s | smallest ceiling-checked Anthropic call |
| `capabilities` | `ops.capability_probes`: vision, image generation, pages, culture, owned surfaces | yes | **15 min** | pays for one image generation and one vision call (both ceiling-checked) |
| `etsy` | `etsy.probe` (read-only ping) | yes | 60 s | |
| `offsite` | `ops.offsite_archive` (full encrypted round trip) | yes | 15 min | writes and reads the bucket |
| `continuity` | `ops.continuity` | no | 5 min | local restore proof |
| `certification` | `gate.lanes` + `chain.rebuild` | no | 60 s | re-checks certified releases; re-certifies anything whose inputs moved |
| `launch_readiness` | `launch.readiness` | no | 60 s | |

Under the buttons, a picker covers **every other scheduled cadence**. It uses the existing
`POST /api/cc/operations/recovery/rerun-cycle`, which:
- requires step-up;
- is refused while a job of that type is in flight;
- is idempotent per request;
- is audited as `recovery.*`.

That route existed before this branch but had no phone button.

### API

- `GET /api/cc/checks` returns each check's last result, its cadence, the time the next run is
  allowed, and the list of other cadences.
- `POST /api/cc/checks/{key}/run` queues the check.
- Both sit behind `security.operator_gate` → `auth.gate`: owner session, CSRF, nonce and
  timestamp, and the per-session mutation limit. External checks also call
  `auth.require_stepup`.
- A run inside a check's window returns **429 `RATE_LIMITED`**. It is audited as
  `cc.check.refused` with the seconds left. A successful run is audited as `cc.check.run`.

### How a run is queued

`ops/on_demand.py` contains no handler logic. It looks the agent and job type up in
`runtime.worker.CADENCES`, then calls `JobQueue.enqueue`:
- inputs are `{"on_demand": true, "requested_by": ...}`;
- the idempotency key is unique per second;
- a run is skipped (and the existing job id reported) when a job of that type is already
  PENDING, RUNNING or FAILED-and-retrying.

The worker then claims the job as usual, with:
- an authority check;
- the model gateway's monthly ceiling;
- parking of model jobs;
- the Etsy client's own gate and rate limit.

### Event chains (enqueue-only, never fail the triggering job)

**A `model.probe` succeeds:**
- Every PENDING job in `MODEL_JOB_TYPES` whose `run_after` lies in the future (that is, a
  parked one) is brought forward to now. This is audited as `ai.unparked`.
- If the previous probe was not OK (credits just arrived), or this probe was run on demand,
  `ops.capability_probes` is queued, which includes the vision probe. It is queued once per
  hour at most, and never while one is in flight.
- A routine scheduled success queues nothing extra.

**An on-demand Etsy re-check succeeds**, or **the Etsy OAuth callback succeeds:**
- `listing.taxonomy_refresh`, `mjs.scan` and `intel.serp_capture` are queued, each once per
  hour at most and skipped while one is in flight.
- The Command Center's existing "Re-check Etsy connection" button now marks its probe
  `on_demand`.
- A **scheduled** Etsy probe keeps W4-ETSYCOMM's rule (taxonomy only, and only when no snapshot
  exists). `test_w4_etsycomm` holds that rule, so it was kept rather than widened.

### No new spend

- A run, or a chain, writes no cost rows itself; this is tested.
- Every model or image call made by the queued jobs goes through the existing ceiling-checked
  gateway.
- The worst case added by the card is bounded by the cool-downs:
  - `capabilities` (the only check that pays for an image) at most 4 times an hour;
  - `model` at most 60 times an hour at a fraction of a cent each.
- Both still stop at the monthly model ceiling.

## Tests (focused)

`tests/test_w4_ondemand.py` has 17 checks. They cover:
- **Auth:** 401 without a session; 403 CSRF without the token.
- **Step-up:** external checks are refused without step-up and queue nothing; internal checks
  run without it.
- **Rate limit:** 429 inside the window, audited, with no extra job; paid checks are spaced
  15 min apart.
- **Enqueue correctness:** every queued job type is a scheduled one; jobs in flight are not
  doubled; no cost rows are written.
- **Chains:**
  - un-parking;
  - capability probes on a transition but not on a routine success;
  - the `model.probe` handler runs the chain end to end;
  - Etsy follow-ons queue once per hour;
  - a scheduled Etsy probe does not fan out, but an on-demand re-check does;
  - a successful OAuth callback queues the follow-ons;
  - the re-check button marks its probe on demand.

Also run: `test_w4_etsycomm`, `test_route_auth_default_deny`, `test_v11_pwa_static`,
`test_w4_ccux`. The service-worker shell lists `_checks.js`, with its version bumped to
`cc-shell-v12`.

## Review: every scheduled check and its on-demand path

Every cadence now has an on-demand path from the phone:
- 8 cadences (7 checks) have their own button;
- 4 are also queued by an event;
- the rest go through the step-up picker.

"Waiting is short" marks cadences that run hourly or more often, where a dedicated button would
save less than an hour.

114 scheduled cadences.

| Cadence | Job type | Every | On-demand path | Event trigger |
|---|---|---|---|---|
| `learn_gap_scan` | `learn.scan` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `infra_heartbeat` | `ops.heartbeat` | 15 min | Re-run picker (step-up). Runs every 15 min or more often, so waiting is short |  |
| `queue_check` | `ops.queue_check` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `signal_review` | `radar.scan` | 6 h | Re-run picker (step-up) |  |
| `daily_review` | `plan.cycle` | 1 d | Re-run picker (step-up) |  |
| `portfolio_review` | `portfolio.review` | 7 d | Re-run picker (step-up) |  |
| `finance_reconcile` | `finance.reconcile` | 1 d | Re-run picker (step-up) |  |
| `strategy_review` | `plan.strategy` | 30 d | Re-run picker (step-up) |  |
| `nightly_improvement` | `improve.nightly` | 1 d | Re-run picker (step-up) |  |
| `weekly_evolution` | `improve.weekly` | 7 d | Re-run picker (step-up) |  |
| `capability_measure` | `improve.measure` | 1 d | Re-run picker (step-up) |  |
| `failure_mine` | `improve.mine` | 6 h | Re-run picker (step-up) |  |
| `promotion_monitor` | `improve.monitor` | 1 d | Re-run picker (step-up) |  |
| `style_learning` | `creative.style_learning` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `outcome_learning` | `creative.outcome_learning` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `season_harvest` | `seasonal.harvest` | 1 d | Re-run picker (step-up) |  |
| `production_lanes` | `gate.lanes` | 1 d | **Card button** `certification` |  |
| `white_space_discovery` | `creative.white_space` | 7 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `creative_candidates_file` | `creative.candidates_file` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `four_season_programme` | `creative.four_season` | 7 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `improve_sandbox` | `improve.sandbox` | 1 d | Re-run picker (step-up) |  |
| `improve_league` | `improve.league` | 1 d | Re-run picker (step-up) |  |
| `finance_governor` | `finance.governor` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `support_triage` | `support.triage` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `commerce_readings` | `commerce.readings` | 1 d | Re-run picker (step-up) |  |
| `orders_ingest` | `commerce.orders_ingest` | 6 h | Re-run picker (step-up) |  |
| `etsy_taxonomy` | `listing.taxonomy_refresh` | 1 d | Re-run picker (step-up) | after an on-demand Etsy re-check succeeds, or a successful OAuth callback |
| `search_visibility_watch` | `listing.search_visibility_watch` | 1 d | Re-run picker (step-up) |  |
| `order_readings` | `commerce.order_readings` | 1 d | Re-run picker (step-up) |  |
| `trajectory_nightly` | `scale.trajectory` | 1 d | Re-run picker (step-up) |  |
| `creative_north_star` | `creative.north_star` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `ads_review` | `ads.adjust` | 1 d | Re-run picker (step-up) |  |
| `growth_distribution` | `growth.distribution` | 1 d | Re-run picker (step-up) |  |
| `growth_journey` | `growth.journey` | 1 d | Re-run picker (step-up) |  |
| `growth_steer` | `growth.steer` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `growth_conclude` | `growth.conclude` | 1 d | Re-run picker (step-up) |  |
| `thrash_sweep` | `ops.thrash` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `seasonal_engine` | `seasonal.engine` | 1 d | Re-run picker (step-up) |  |
| `swarm_review` | `swarm.review` | 1 d | Re-run picker (step-up) |  |
| `swarm_allocate` | `swarm.allocate` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `swarm_orphans` | `swarm.orphans` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `swarm_backlog` | `swarm.backlog` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `preproduction_validation` | `growth.preproduction` | 1 d | Re-run picker (step-up) |  |
| `growth_experiments` | `growth.experiments` | 1 d | Re-run picker (step-up) |  |
| `blind_review` | `creative.blind_review` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `grid_tournament` | `creative.grid_tournament` | 7 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `intel_acceptance` | `intel.acceptance` | 1 d | Re-run picker (step-up) |  |
| `provenance_backfill` | `ops.provenance_backfill` | 1 d | Re-run picker (step-up) |  |
| `spend_escalation` | `finance.escalation_check` | 6 h | Re-run picker (step-up) |  |
| `chain_rebuild` | `chain.rebuild` | 1 h | **Card button** `certification` |  |
| `launch_readiness` | `launch.readiness` | 1 d | **Card button** `launch_readiness` |  |
| `maturity_disagreements` | `ops.maturity_disagreements` | 1 d | Re-run picker (step-up) |  |
| `model_probe` | `model.probe` | 6 h | **Card button** `model` |  |
| `continuity_proof` | `ops.continuity` | 1 d | **Card button** `continuity` |  |
| `offsite_archive` | `ops.offsite_archive` | 1 d | **Card button** `offsite` |  |
| `image_benchmark` | `creative.image_benchmark` | 1 h | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `model_tournament` | `creative.model_tournament` | 1 h | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `model_reference_pack` | `creative.model_reference_pack` | 1 h | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `owned_photography` | `assets.owned_photography` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `model_photography` | `assets.model_photography` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `seasonal_sentinel` | `seasonal.sentinel` | 1 d | Re-run picker (step-up) |  |
| `etsy_probe` | `etsy.probe` | 6 h | **Card button** `etsy` |  |
| `mjs_scan` | `mjs.scan` | 2 h | Re-run picker (step-up) | after an on-demand Etsy re-check succeeds, or a successful OAuth callback |
| `serp_capture` | `intel.serp_capture` | 1 d | Re-run picker (step-up) | after an on-demand Etsy re-check succeeds, or a successful OAuth callback |
| `mjs_benchmark_health` | `intel.benchmark_health` | 1 d | Re-run picker (step-up) |  |
| `mjs_pod_learning` | `intel.pod_learning` | 1 d | Re-run picker (step-up) |  |
| `mjs_seasonal_sentinel` | `mjs.seasonal_sentinel` | 1 d | Re-run picker (step-up) |  |
| `panel_discovery` | `intel.panel_discovery` | 7 d | Re-run picker (step-up) |  |
| `benchmark_refresh` | `intel.benchmark_refresh` | 7 d | Re-run picker (step-up) |  |
| `physical_upgrade_impact` | `physical.upgrade_impact` | 1 d | Re-run picker (step-up) |  |
| `identity_drift` | `visual.identity_drift` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `benchmark_memory` | `creative.benchmark_memory` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `reference_reading` | `creative.reference_reading` | 1 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `mjs_reviews` | `mjs.reviews` | 7 d | Re-run picker (step-up) |  |
| `improvement_retrospective` | `improve.retrospective` | 7 d | Re-run picker (step-up) |  |
| `policy_watch` | `ops.policy_watch` | 1 d | Re-run picker (step-up) |  |
| `build_tick` | `build.tick` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `blinded_benchmark` | `creative.blinded` | 14 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `arena_expedition` | `creative.expedition` | 7 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `product_tournament` | `creative.tournament` | 7 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `remerchandising_review` | `seasonal.remerchandising` | 7 d | Re-run picker (step-up) |  |
| `seasonal_cycle_proof` | `seasonal.cycle_proof` | 7 d | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `capacity_review` | `ops.capacity` | 7 d | Re-run picker (step-up) |  |
| `stale_artefact_sentinel` | `ops.sentinel` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `health_sweep` | `ops.health` | 15 min | Re-run picker (step-up). Runs every 15 min or more often, so waiting is short |  |
| `capability_probes` | `ops.capability_probes` | 6 h | **Card button** `capabilities` | after a model probe succeeds (transition or on-demand) |
| `culture_sweep` | `culture.sweep` | 1 d | Re-run picker (step-up) |  |
| `gallery_analysis` | `intel.gallery_analysis` | 2 h | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `retention_sweep` | `ops.retention` | 1 d | Re-run picker (step-up) |  |
| `dependency_sweep` | `ops.dependencies` | 1 d | Re-run picker (step-up) |  |
| `improve_replay` | `improve.replay` | 1 d | Re-run picker (step-up) |  |
| `teardown_enforce` | `teardown.enforce` | 1 d | Re-run picker (step-up) |  |
| `etsy_credential_health` | `etsy.credential_health` | 1 d | Re-run picker (step-up) |  |
| `etsy_shop_snapshot` | `etsy.shop_snapshot` | 1 d | Re-run picker (step-up) |  |
| `store_live_drift` | `store.live_drift` | 1 d | Re-run picker (step-up) |  |
| `etsy_openapi_reverify` | `etsy.openapi_reverify` | 7 d | Re-run picker (step-up) |  |
| `etsy_listing_census` | `etsy.listing_census` | 1 d | Re-run picker (step-up) |  |
| `executive_orchestrator` | `autonomy.orchestrate` | 15 min | Re-run picker (step-up). Runs every 15 min or more often, so waiting is short |  |
| `laura_executive` | `laura.executive_tick` | 5 min | Re-run picker (step-up). Runs every 5 min or more often, so waiting is short |  |
| `listing_outcomes` | `listing.outcomes` | 1 d | Re-run picker (step-up) |  |
| `visual_rnd` | `visual.rnd.cycle` | 6 h | Re-run picker (step-up). Not given its own button: creative or model spend, so the schedule and budget govern it |  |
| `accounting_period_pack` | `finance.accounting.period_pack` | 1 d | Re-run picker (step-up) |  |
| `slo_check` | `ops.slo` | 15 min | Re-run picker (step-up). Runs every 15 min or more often, so waiting is short |  |
| `seo_cycle` | `seo.cycle` | 6 h | Re-run picker (step-up) |  |
| `accounting_cycle` | `finance.accounting.cycle` | 6 h | Re-run picker (step-up) |  |
| `ads_readiness` | `marketing.ads_readiness` | 1 h | Re-run picker (step-up). Runs every 1 h or more often, so waiting is short |  |
| `role_evaluator` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
| `role_failure_miner` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
| `role_experiment_designer` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
| `role_prompt_tool_challenger` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
| `role_cost_optimiser` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
| `role_reliability_engineer` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
| `role_creative_critic` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
| `role_lesson_router` | `improve.role_work` | 1 d | Re-run picker (step-up) |  |
