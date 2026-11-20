# AUTONOMY_FIX — departments idle while eligible work exists (owner Rule #1)

Lane W4-AUTONOMY, branch `claude/w4-AUTONOMY` from production commit **0417f35**. As of
2026-10-11 (UTC). Basis: **measured** (public GETs of production, Railway deploy logs, local
reproduction on SQLite and on a real Postgres 16). Nothing was deployed, restarted, enqueued in
production, published, sent or spent. Shadow mode, authority, spend ceilings and model policy
are unchanged. Evidence files: `evidence_AUTONOMY/`.

## 1. Production evidence (0417f35, read 14:39–14:45Z)

`/health`: runner enabled, pool 3, `worker_target` 3, one dedicated `control` lane
(autonomy.orchestrate/department_review/morning_handoff, ops.heartbeat/health/queue_check),
0 restarts, scheduler ticking. Railway deploy logs show only uvicorn start lines — the runner
logs nothing about department state, so the evidence below is from `/api/jobs`, `/api/audit`
and `/api/queue/dead`.

| Observation | Source |
|---|---|
| The **only** open jobs are model jobs parked because the Anthropic balance is spent: creative.tournament ×4 + creative.grid_tournament (Product & Design), intel.gallery_analysis (Intelligence), seasonal.cycle_proof (Visual), all `pending`, attempts 0 | `/api/jobs?limit=3000`; `ai.parked` audit: "the Anthropic account balance is spent (open owner action)", `park_seconds` 1800, re-parked every 30 min |
| `ops.sentinel` dead-lettered **7 times in 8 minutes** (14:27–14:35Z), every attempt: `StringDataRightTruncation: value too long for type character varying(200)` on `INSERT INTO jobs` | `/api/queue/dead`, `job.failed` audit |
| The same sentinel runs reported `rebuild`: 14 products (autumn-oak-mosaic-throw … winter-village-graphghan) stale, `publication_blocked` | `ops.sentinel` audit detail; **0** `ops.rebuild_propagated` rows ever |
| The control lane's own `autonomy.orchestrate` (worker `web-2-control`) was **held** 60 s by the pool's infrastructure function share | `swarm.lane_held` 14:03:17Z |
| 166 function-share holds in the first 30 min; several name `market_intelligence` as the starved function while its only due work was the parked model jobs | `swarm.lane_held` audit |

## 2. Root causes

1. **Parked work made departments BUSY (primary).** `autonomy.generators.Snapshot` counted
   every PENDING/RUNNING/FAILED job as department work. The orchestrator skips a BUSY
   department entirely, so Product & Design, Intelligence and Visual — holding only jobs no
   worker can run until the balance is topped up (up to 24 h) — received none of the
   deterministic, charter-generatable work their generators held (seasonal.sentinel,
   creative.outcome_learning, intel.pod_learning, intel.benchmark_refresh, visual.rnd.cycle,
   visual.identity_drift). `rule1.measure` used the same count, so it reported
   `idle_at_end: false` and **masked the defect**. The same "any pending job" test stopped
   `orchestrator.idle_wake` and Laura's "company queue is empty → give departments their next
   safe work" path from ever firing during the outage.
2. **Sentinel rebuild key overflowed Postgres.** `rebuild_graph.enqueue` keys each product's
   rebuild on `rebuild:product:{slug}:{every moved ref=fp}`; with the release chain moved
   under 14 products the key is 544 chars. SQLite ignores VARCHAR(200), so every test passed;
   Postgres refuses the insert. Product Truth's sentinel died on every attempt (Laura's P1
   incident priority and its rework kept re-delegating it) and Store/Commerce never received
   the 14 `chain.rebuild` jobs.
3. **Share holds were not work-conserving against unrunnable work.** `capacity.share_decision`
   held a runnable job whenever another function had due work below its share — including
   model jobs that `park_if_model_down` would immediately give back. And it applied the
   pool's mix to the dedicated control lane, delaying the orchestrator that feeds idle
   departments.

Not defects (left alone): store.publish refusals (shadow, by design); mjs.scan /
taxonomy 403s (Etsy credential, owner action); the parked model jobs themselves (spent
balance — OWNER ACTION already open; no spend authority here).

## 3. Fixes

| # | File | Change |
|---|---|---|
| 1 | `autonomy/generators.py` | `actionable()` + `DUE_GRACE_SECONDS` (60 s): a department is BUSY only on RUNNING or due PENDING/FAILED work. Parked/backed-off jobs go to `waiting_by_department`. `open_by_type` still counts everything, and handoff candidates now skip a consumer type already open, so a waiting job is never duplicated. |
| 1 | `autonomy/orchestrator.py` | reports `waiting_jobs` per department; `idle_wake` fires when nothing is due. |
| 1 | `laura/executive/loop.py` | `company_work_open` counts due work; new `company_work_waiting`; `open_by_type` unchanged (no double delegation). |
| 2 | `queue/durable.py` | `fit_idempotency_key`: a key over 200 chars becomes prefix + `#` + sha256 digest of the whole key, at the single enqueue boundary. Deterministic (idempotency kept), collision-free for shared prefixes, identity for keys that fit. |
| 3 | `swarm/capacity.py` | `unrunnable_waiting`: due model jobs while the provider is measurably down are not "starved work". With the provider up the #30 mix is unchanged. |
| 3 | `swarm/orchestrate.py`, `runtime/worker.py` | a worker claiming only `runtime.lanes.CONTROL` types skips the pool's function/lane *share* (agent-lane concurrency still applies). The pool still holds the same job type under the mix. |

## 4. Regression tests — `tests/test_w4_autonomy_idle_departments.py` (10)

Against unmodified 0417f35 code, 8 of 10 fail (the two that pass assert unchanged behaviour:
due work still makes a department BUSY; with the provider up the mix still holds):
departments with only parked jobs read BUSY (`{'product_design': 3, 'intelligence': 1,
'visual': 1}`); `rule1_defect` masked; idle wake suppressed; Laura `company_work_open` 5;
rebuild key length 544; long-key idempotency; share hold for unrunnable model work; control
lane held. All 10 pass on this branch.

## 5. Reproduction and simulation

**Postgres 16 (local, private socket)** — `evidence_AUTONOMY/pg_repro.py`, 14 products, chain
moved:

```
0417f35: FAILED DataError (psycopg2.errors.StringDataRightTruncation) value too long for type character varying(200)
fixed:   OK enqueued 14 artefacts; re-run already_queued 14 ; jobs 14 ; max key len 200
```

**Seeded like production** — `evidence_AUTONOMY/sim.py` (shadow, proxies closed, no keys):
spent-balance owner action + the 7 parked model jobs, then 3 × (orchestrator tick + worker
drain ≤ 40 claims).

| | 0417f35 | this branch |
|---|---|---|
| Product & Design / Intelligence / Visual state, ticks 1–3 | BUSY, BUSY, BUSY | GENERATED ×3 |
| Missions generated for those three | 0 | 9 (creative.outcome_learning, seasonal.sentinel, intel.pod_learning, intel.benchmark_refresh, visual.rnd.cycle, visual.identity_drift, then department reviews) |
| Jobs done in those departments | 0 | 6 (visual.rnd.cycle judged useful; the rest honest no-ops on an empty DB) |
| `rule1_defect` at end | false (masked: `idle_at_end` false) | false (eligible work exhausted, `idle_at_end` true) |
| Parked model jobs still pending, not run, not paid | 7 | 7 |

(The simulation ran before the 60 s due grace was added; the grace only treats work due within a minute as busy, so 30-minute parks are unaffected.)

On production data the generated work has real evidence to consume (14 stale products,
seasonal milestones, benchmark observations), so the useful share will be higher than on an
empty DB; that is a prediction, not a measurement, until this is deployed.

## 6. Focused existing suites (one at a time, private TMPDIR)

| Suite | Result |
|---|---|
| test_w4_autonomy_idle_departments (new) | 10/10 |
| test_v11_autonomy_orchestrator | 14/14 (incl. `test_an_empty_queue_wakes_the_orchestrator_immediately`, which first failed on a strict `run_after <= now` and led to the 60 s due grace) |
| test_cert_improve_autonomy | 20/20 |
| test_w3_laura_core_executive | 7/7 (a first run lost its temp sandbox to an external cleanup; re-run in isolation passed) |
| test_w4_auto_status | 11/11 |
| test_r2_autonomy_useful_work | 6/6 |
| test_v11_autonomy_overnight | 1/1 |
| test_rebuild_graph | 10/10 |
| test_cert_lanes_capacity | all pass |
| test_lane_admission_concurrency | all pass |

No existing assertion was edited. The full suite was not run (shared cores).

## 7. Not done / owner

* Not deployed: the integrator promotes this branch; production keeps 0417f35 until then.
* After deploy, verify: `/api/queue/dead` shows no new `ops.sentinel` truncation; an
  `ops.rebuild_propagated` audit row appears and 14 `chain.rebuild` jobs run; `ai.parked`
  continues while departments receive deterministic missions.
* The parked model work resumes only when the Anthropic balance is topped up (existing
  OWNER ACTION `model_provider_balance`; no new owner action).
