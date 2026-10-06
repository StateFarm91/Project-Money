# Handoff: v1.1 lane A (cloud autonomy / factory / orchestration)

- **Branch:** `claude/v11-A`
- **Base:** `claude/visual-investigation` @ 0694fb7
- **Worktree:** `.claude/worktrees/v11-A`
- **Pushed:** no. **Deployed:** no. **Phase:** shadow throughout.

## Requirements

| ID | Status | Evidence / why |
|---|---|---|
| PRIORITY ZERO | **COMPLETE in code and test; GATED for hosted proof** | `autonomy.orchestrator` runs the loop inside the runtime. Each step is listed with its evidence: observe (Snapshot), determine/prioritise (generators: handoff > overdue > self-review, with learned no-op suppression), create missions (job + memory + timeline), execute (worker), validate/measure (`reconcile_missions`), hand off (`charters.consumes`), learn (`department_review` → KPI snapshot + routed `lessons`), repeat (15-min cadence + idle wake). A 24 h hosted lights-out soak has **not** run. |
| F-880 | PARTIAL | The loop lives entirely in the embedded runner, with no external dependency. Hosting and deploy are outside this lane. |
| F-881 | COMPLETE (runtime side) | Nothing in the loop imports or needs a session. The overnight test enqueues nothing after its first tick. |
| F-890 | COMPLETE | All 11 departments are chartered and every wired job type maps to exactly one department (test). Each department has cadences plus orchestrator-generated work. |
| F-891 | PARTIAL | Orchestration is deterministic and evidence-based. Model-reasoning agents are unchanged (lane B and others). |
| F-892 | COMPLETE | `autonomy/charters.py` defines, per department: mission, agents, generatable allowlist, forbidden, inputs, outputs, KPIs, escalation, evidence requirement and handoffs. `validate()` runs at import. The `coo` agent is structurally forbidden every protected type. |
| F-893 | COMPLETE | `autonomy.orchestrate` runs on the scheduler (`executive_orchestrator`, 15 min). Protected departments are served first. Protected work goes to owner approval items. |
| F-894 | COMPLETE | A blocked department (memory block, or owner action) is skipped and the others continue. A failing generator is isolated as DEGRADED. Both have tests. |
| F-895 | COMPLETE (simulated) | The overnight simulation produced useful missions in 10 of 10 unblocked departments, with no spend and no protected job. |
| F-896 | COMPLETE (data) | `autonomy.morning_handoff` writes `company_memory` with kind=morning_brief, daily after 11:00 UTC. It covers jobs completed per department, missions, spend (UNKNOWN when there are no rows), incidents, owner decisions and blocked departments. Lane C renders it. |
| F-918 | COMPLETE | `autonomy.kpis` returns VOID when a guardrail trips. Duplicates count once, no-ops count zero, and UNKNOWN is never 0 (test). |
| F-920 | COMPLETE | The `company_memory` table is keyed, idempotent and source-linked. It holds missions, KPI snapshots, lessons, briefs, blocks and approvals. |
| F-927 | COMPLETE | `company_timeline` plus `status.timeline()`, which merges incidents, owner actions, spend and significant jobs. |
| F-929 | COMPLETE | Generated work carries evidence. Protected work is never enqueued: the charter check, the enqueue-boundary check and the registry structural forbid all apply. |
| F-930 | COMPLETE | Same as F-929. Generated job types come from a reasoned non-spending allowlist (`SAFE_GENERATED`). `coo` has a CA$0 ceiling. |
| §95 kill test | COMPLETE | A SIGKILLed real process ran the orchestrate job and was reclaimed. The effects equal one clean run. |
| §95 block test | COMPLETE | See the orchestrator and overnight tests. |

## Files

**Created**
- `src/brambleloop/autonomy/`: `__init__`, charters, generators, orchestrator, kpis, memory,
  models, handlers, status, map, proof, and `autonomy_map.json` (generated).
- `src/brambleloop/runtime/lanes.py`
- `tests/test_v11_autonomy_{orchestrator,kpis,recovery,overnight,timeline}.py`
- `tests/test_continuous_operations.py`
- `research/final_build/v1_1/AUTONOMY_MAP_AUDIT.md`
- `research/final_build/v1_1/evidence/A_runtime_proof.json`
- `research/final_build/v1_1/evidence/A_overnight_simulation.json`

**Modified**
- `queue/durable.py`: per-claim `lease_token`, and a token fence on complete, fail and heartbeat.
- `core/models.py`: additive nullable `Job.lease_token`. `core.migrate` adds it in place.
- `runtime/worker.py`:
  - passes the token everywhere;
  - adds the `executive_orchestrator` cadence;
  - adds `Scheduler.tick` → `idle_wake`.
- `runtime/pipeline.py`: imports the autonomy handlers.
- `agents/registry.py`: the `coo` agent.
- `app/runner.py`: the control lane (`_lane_loop`), plus a lanes entry in `STATE`.
  The worker-name format is unchanged: a hostname change was tried, and reverted because
  `test_cert_claude_independence` reads `web-<pid>`.
- `app/worker_entry.py`: not changed.

## Codex 8877f05 reuse

- **Ported:**
  - the lease-token fence, adapted so a write returns False/None instead of raising
    `LeaseLost`, because the base already had name fencing (C-13);
  - lanes, narrowed to a *control lane*, because the base already had the C-68 pool;
  - the stale-attempt, simultaneous-claim and lane tests.
- **Not ported:**
  - `growth/ads_readiness.py` (lane H);
  - gateway budget-admission changes, which are not lane A's files;
  - the `MarketplaceCapability` model;
  - the codex runner's per-lane all-alive semantics.

## Tests (each run individually: `cd brambleloop && PYTHONPATH=src python3 tests/<f>.py`)

| File | Result |
|---|---|
| test_v11_autonomy_orchestrator | 14 OK |
| test_v11_autonomy_kpis | 7 OK |
| test_v11_autonomy_recovery | 3 OK (real SIGKILL subprocess) |
| test_v11_autonomy_overnight | 1 OK (~45 s) |
| test_v11_autonomy_timeline | 6 OK |
| test_continuous_operations | 5 OK |

Existing suites for the modified modules: see `EXISTING_RESULTS` below. The integrator fills
this in from the final report.

## Runtime proof

- `evidence/A_runtime_proof.json`: `python -m brambleloop.autonomy.proof --seconds 900` ran
  the real `app.runner.start()` in a child process. Phase was shadow, the database was a temp
  SQLite file, the environment carried no credentials, and every proxy pointed at a closed
  port, so there was no network. Nothing was enqueued by hand after boot. Observed at commit
  2fdb8d3 (code identical to HEAD except the band and naming fixes):
  - **Duration and throughput:** 900 s, 261 jobs; 247 done and 11 dead at the end. The worker
    was alive in every sample. The scheduler enqueued all cadences itself.
  - **Orchestrator:** it ran 4 times, twice on its cadence and twice from the idle-queue wake.
    Once the cadence burst drained, it generated 19 missions across all 11 departments. 18 of
    them produced useful output: store_commerce had 1 of 2 useful, and every other department
    had all of its missions useful.
  - **Store/Commerce:** 10 `store.publish` dead letters. These are the *existing* release chain
    refused by SHADOW, which is correct; the orchestrator generated no protected job. One
    `ads.adjust` ran from its existing cadence and recorded 0 spend.
  - **Spend:** 0 `cost_entries` rows.
  - **Learning and handoff:** 9 KPI snapshots and 1 morning brief. `status.summary` = OK.
  - **The 1 DEFECT dead letter:** `launch.readiness` failed with ModuleNotFoundError: numpy.
    That is this sandbox's Python, which lacks numpy; it is not a code defect, and the same
    error appears in test_fb4_ops and test_cert_wiring here.
- `evidence/A_overnight_simulation.json`: 32 orchestrator ticks over a simulated 8 h, with the
  clock advanced via `inputs.now`. Queue, worker and handlers were real. Store/Commerce was
  blocked all night.
  - Useful missions by department: platform 12, product_truth 12, support 11, finance 6,
    growth 5, learn 5, product_design 4, intelligence 4, executive 4, visual 3,
    store_commerce 0 (blocked).
  - 0 protected jobs and 0 cost rows.
  - 20 KPI snapshots and 1 morning brief.

## WIRING REQUESTS (shared files lane A does not own)

1. `core/db.py` `Database.create_all`, beside the other additive imports:
   `from ..autonomy import models as autonomy_models  # noqa: F401; company memory/timeline`.
   Until then, the tables are still registered whenever `runtime.pipeline` is imported, which
   the runner and worker do. `autonomy.models.ensure_tables` also creates them lazily.
2. `core/continuity.py` `NON_REDERIVABLE`: add `"company_memory", "company_timeline"`. They are
   already exported and restored; this only labels them non-rederivable.
3. `app/main.py`, for lane C: expose `brambleloop.autonomy.status.summary(db)` and
   `timeline(db, limit)` behind operator auth on the Operations tab. Owner block/unblock
   (F-889) can call `autonomy.memory.block_department` / `unblock_department` through an
   owner-authenticated route.

## Open defects / not verified

- **AM-10, open:** registry permissions with no handler: gate.quality, gate.policy,
  gate.asset_truth, cir.twin, cir.reverse, and others. The agents `asset_truth` and `policy`
  can run nothing. The fix lives in gates/ and cir/, outside lane A.
- **Saturation is honest:** an idle department whose evidence is exhausted reports SATURATED
  and waits for new evidence, an overdue cadence, or the 6 h review. It does not invent work.
- "Useful" means `runtime.pipeline.did_no_work` is false. That is an existing heuristic, and
  it counts outputs with no `ran`/work-counter keys as useful.
- No hosted run happened, so production behaviour is unverified. The lights-out 24 h soak is
  still an open gate.
- `test_cert_claude_independence::test_the_deployed_image_and_start_command_carry_no_session_state`
  fails on the base Dockerfile (`COPY release`). It is pre-existing and not caused by lane A;
  the Dockerfile is untouched.
