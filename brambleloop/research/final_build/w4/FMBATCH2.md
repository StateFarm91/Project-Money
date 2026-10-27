# W4-FMBATCH2: partial rows taken over from the frozen lanes

Branch `claude/w4-FMBATCH2`, cut from FMBATCH1 at 62fcf5ed (8bd4e3b0 adds the Batch 3
acceptance plan). Coordinator instruction, 2026-10-26: take the partial rows whose remaining
gap is code that can be written without an owner, a provider or a live shop: F-601, F-454,
F-451, F-602, F-464, F-672 and F-091. Check `origin/claude/w4-AGENTS2` before each row.
Nothing here is deployed. Proposals are in `OVERRIDES_PROPOSED_FMBATCH2.json` (the dry run
reports `problems: []`); none is applied.

AGENTS2 head at check time: fb681316. It changes 140 files, including `autonomy/charters.py`,
`generators.py`, `map.py`, `runtime/worker.py` (cadences only), `runtime/release.py`,
`swarm/orchestrate.py`, `laura/executive/loop.py` and several `visual/*` modules.

## F-672: the pipeline records its own lifecycle moves (4676c472)

- **What it does.** `Worker.run_once` calls `products.lifecycle.after_job` after every
  completed job. For pipeline job types (`cir.*`, `gate.certify`, `assets.*`, `listing.*`,
  `store.*` and `commerce.orders_ingest`), it derives the stage the product's rows now show.
- **When the stage moved.** It records the move, with history, in company memory.
- **Illegal moves.** A move that is neither an allowed move nor a forward step is recorded with
  `legal: false` and audited as `product.lifecycle_anomaly`. It is never dropped silently.
- **Failure handling.** The hook never fails the job that ended.
- **Collision check.** AGENTS2 edits only the `CADENCES` table in `worker.py`, not `run_once`.
- **Test.** `tests/test_w4_fmbatch2_lifecycle_pipeline.py`. It fails without the hook, because
  no record is written.
- **What writing the test showed.** A stand-in `gate.certify` handler that writes a certified
  version without a provenance row is killed (DEAD) by the worker's provenance backstop. That
  is correct behaviour. The fixture therefore writes the certified version beforehand.

## F-091: 22 more callers behind the provider boundary (cd1f4a17)

- **Facade additions.** `gateway/providers.py` gains `provider_for` (equal to `for_task`) and
  five more neutral names: `usable`, `last_probe`, `spent_this_month_cad`,
  `agent_daily_ceiling` and `USD_TO_CAD`. These are ledger and probe readings, not model calls.
- **What moved.** 22 callers now import the facade:
  - the visual modules: registry, photoreal, inspect, tournament, bible and fidelity;
  - the creative modules: blinded, intake, prospecting, reference and image_stages;
  - the others: motif_fidelity, provider_accounts, health, funding_packet, governor,
    spend_policy, executor, dependency, insights_budget, market_map and launch readiness.
- **Call sites.** Every `check_budget` call site already passes `purpose`, which the facade
  requires.
- **What is left.** `PENDING` goes from 26 to 4: `runtime/release`, `runtime/worker`, `app/main`
  and `experiments/controlled`. They drive the vendor's own probe and provider objects
  (`probe`, `vision_probe`, `AnthropicProvider`, `NO_KEY_REASON`, `DEFAULT_MODEL`). This is
  proposed as by design; the integrator decides.
- **Collision check.** AGENTS2 changes three of the migrated files (`visual/fidelity`,
  `creative/image_stages`, `launch/readiness`), but not their import lines.
- **New test.** `test_every_name_a_migrated_caller_reads_resolves_through_the_facade` fails if
  a caller reads a name the facade lacks. It was seen failing with the new names removed.
- **Suites run, by name.** All passed:
  - bible, blinded, dependency, governor, insights_budget, intake, model_tournament,
    motif_fidelity, photoreal_calibration, prospecting, provider_accounts and reference_pack;
  - spend_policy, w4_fidelity, w4_fluxstages, access, the three fmbatch1 provider suites and
    fallback_draft_provenance.
- **Failures not caused by this change:**
  - `test_health` fails 8 tests both here and at 4676c472. The `resources` signal is DEGRADED
    because this host's disk has 1% free (3.6 GB). That is the environment, not code.
  - `test_visual_inspection` failed 1 test at 4676c472 as well. The cause was a model-literal
    rule broken by FMBATCH1's own `gateway/fallback_contract.py` (da81fe71). It is fixed in
    8111ce1d: capabilities are now built from `routing.TIERS`, with the same content.

## F-601 (part): the Executive / COO improvement cell (a9cf46de)

- **The cell.** `improve.cells` gains `executive`, with metric
  `critical_path_parked_requirements` (lower is better). It is measured from the stored
  executive plan (`executive:plan`): the sum of each critical-path gate's `unblocks`.
- **Readings.** With no plan stored, the result is NotMeasured. An empty critical path is a
  real 0 over the one plan read.
- **Wiring.** The cell is registered in `freshness.CELL_WORLD` (OPERATIONAL) and
  `profiles.CELL_AGENT` (`coo`). `departments.coverage` now reports the executive department
  complete.
- **Test pins.** The cell-count pins in test_measure, test_improve and test_improve_handlers
  move from 13 to 14, with the reason. test_w4_fmbatch1_departments now asserts that the
  executive department is complete.
- **Not built here.** The compliance/policy and analytics charters. They belong in
  `autonomy/charters.py`, which AGENTS2 is editing now (dept batch 1 is "Quality & Compliance
  agents operational").

## F-454, F-451, F-602: proposed, not built

- **F-454.** The analytics and integration agents are department-handler work AGENTS2 is doing
  in `charters`, `generators` and `map`. Building them here would collide. The build-side-lanes
  part is blocked by design under the F-463 decision.
- **F-451.** `/api/orchestrator` already joins every runtime section, deployments included
  (`master_view`). The only gap left is build-side lane state, which by F-463 never enters the
  production database.
- **F-602.** The executive plan is live and now has a cell. The merge/deploy queue and file
  ownership are build-side (`ops/deploy_guard.py`, `ops/registry.py`). The runtime never holds
  the repository.

## F-464: not converted (reason, and the design for whoever does it)

The two render handlers, `handle_model_photography` and `handle_owned_photography`, are in
`runtime/release.py`, which AGENTS2 is editing. The block they hold is the BFL submit-then-poll
loop in `gateway/images._generate_reserved`: up to `BFL_POLL_ATTEMPTS = 150` ×
`BFL_POLL_SECONDS = 2.0`, which is 300 s per render with `time.sleep`. It runs inside the paid
render path. These are its invariants:

- the reservation is taken before the request;
- `billing["accepted"]` is set on a 2xx, so a later failure is billed;
- `paid_calls.guarded` replays a render a retried attempt already paid for;
- the CostEntry is written exactly once.

**What a safe conversion needs.**

1. `images.submit_render(...)` returns `{op_ref: polling_url, reservation_id, fingerprint}`
   once the provider has accepted the request (billed from that point).
2. A `paid_calls` record keyed by the fingerprint, in state ACCEPTED, so that a retried poll
   job never submits again.
3. `images.poll_render(op_ref)`: one GET and a status classification (ready, in progress or
   terminal). On ready it fetches the bytes and writes the one CostEntry.
4. The handlers split at each render into `runtime.awaiting.defer(...)` and a poll job, with
   the vision checks that follow a render moved into the poll job's done branch. Paid vision
   checks must not run again on a replay.

**Risk.**

- The mechanism (`runtime/awaiting`) is already built and tested.
- Each of the four steps above changes billing semantics on a paid path, and fakes can prove
  only part of that. The BFL status vocabulary, the presigned-URL expiry (about 10 minutes)
  and the moderation outcomes need a live render to accept.
- I did not change it on a branch that cannot run a render.

**Proposed handling.** Hand it to the product-engine lane after AGENTS2 merges, or let the
owner authorise one live render for acceptance. The row stays B.

## Ledger

`ENGINEERING_LEDGER` was regenerated. FM engineering completion goes from 725 to 726 of 917
(F-672 moves to E). Build 2 is unchanged at 316 of 320.

## Coordinator decisions (2026-10-26)

- **F-091.** The 4 remaining vendor-probe callers are accepted as by design. This is recorded in DECISION_LOG, and the proposal reason is updated. No further migration is planned.
- **F-464.** Handed to the product-engine lane after AGENTS2 merges. The proposal is now `other_lane:product-engine`. The design above is the hand-off.
- **Lane state.** FMBATCH2 is on hold. No unblocked actionable rows remain here.
