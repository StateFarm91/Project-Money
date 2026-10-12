# Lane I handoff — reliability / observability / failover / SLOs / always-on hosting path

Branch `claude/v11-I` (base `claude/visual-investigation` @ 0694fb7). Written 2026-10-06 UTC.
Nothing pushed, nothing deployed, no Railway mutation, no network call, no spend.

## Requirements

| ID | Status | What / why |
|---|---|---|
| F-880 (hosting side) | **PARTIAL — GATED** | Topology, restart policy, watchdog, backups, cost and owner actions in `CLOUD_HOSTING_PLAN.md`. Recommend keeping the single always-on container + a 5-min cron watchdog (+CA$0.50–1.00/month est., ASSUMED prices). Gated on owner approvals (plan §7) and deploy approval. |
| F-881 (hosting side) | **PARTIAL — GATED** | Plan §3 lists exactly what removes the Claude-heartbeat dependency; the code pieces (heartbeat rows, stale detectors, watchdog entrypoint, soak grader) are BUILT; wiring W-1..W-4 (lane A) and the watchdog service are pending. Whether production's embedded scheduler runs unpoked is **not proven**: plan §5 gives the read-only query; App Sleeping must be checked by the owner. |
| F-900 | **COMPLETE (backend), wiring to lane C pending** | `ops/recovery.py`: `restart_stuck_job`, `release_stale_lease`, `rerun_department_cycle`, `recent` — refuse unsafe cases (live lease, in-flight cycle, deliberate refusals, thrash-breaker), idempotent by `request_id`, every success *and* refusal audited. Health/backlog/dead letters/incidents/last cadences are in `ops.slo.summary` + existing `ops.health`. |
| F-921 | **COMPLETE in gateway; adoption at call sites is a WIRING REQUEST (W-8)** | `gateway/failover.py`: durable per-model health from `model.attempt` audit rows (DOWN after 3 consecutive failures, HALF_OPEN after 10 min, malformed ≠ outage, budget refusal not recorded), approved fallbacks **stronger-only** (deep tier: none → PARK), `Parked` is a `TransientError` so the worker retries with backoff. `ModelGateway` now records every attempt durably and keys breakers per model. Until W-8, production call sites still pass one provider, so they get durable health visibility but no model fallback. |
| F-922 | **COMPLETE in gateway (same W-8 caveat)** | `failover.decide`: declared-tier model first (routing by question shape), cache hit → no call, compiler tasks refused, each candidate pre-checked against month remaining + agent daily permission; a dearer fallback that would cross the ceiling → PARK. Authoritative check and spend recording unchanged (`check_budget_cad` reservation + `ModelGateway._record` is still the only billing path). |
| F-923 | **COMPLETE (code); GATED for a real reading** | `command_center_availability` SLO counts only external probe rows; process heartbeat shown as a labelled proxy, never as the SLI; <50 % coverage → UNKNOWN; strict (an interval with any failed probe is down). No reading exists until the watchdog runs in production. Degraded mode documented (plan §9). |
| F-924 | **COMPLETE (code); wiring pending** | `ops/slo.py`: scheduler freshness, cadence freshness, queue latency, recovery time, department heartbeat, department useful work (per-department useful hours vs expected hours; `did_no_work` judge; self-observing jobs excluded), error budgets (MET / AT_RISK at ≥75 % budget / BREACHED / UNKNOWN). `check()` raises/restates/closes `slo.*` incidents via `incident_lifecycle` (stored notifications only). Stale scheduler → P1 `slo.scheduler_stale`; stalled queue → P1 `slo.worker_stalled`. |
| Directive §1 | **DONE (prepare)** | New recurring cost identified before incurring it: watchdog ≈ CA$0.50–1.00/month; nothing incurred. |
| Directive §16 | **GATED on deploy approval** | `ops.slo.soak_report(db, start, end)` grades a lights-out window from durable rows only; refuses future end; <24 h → INCOMPLETE; any UNKNOWN → INCOMPLETE; interactive/dev actor → FAIL. **Soak not started.** |
| Directive §17 | **DONE (prepare); no deploy** | `CLOUD_HOSTING_PLAN.md`. Decommission of failed `Project-Money` service recommended as owner action (not done). |

## Files

Created: `src/brambleloop/ops/slo.py` (tables `ops_runtime_samples`, `ops_leases`; SLOs; detectors;
`summary`; `check`; `soak_report`; watchdog CLI `python -m brambleloop.ops.slo watchdog|evaluate`),
`src/brambleloop/ops/recovery.py`, `src/brambleloop/gateway/failover.py`,
`tests/test_v11_reliability_slo.py`, `tests/test_v11_reliability_gateway.py`,
`tests/test_v11_reliability_recovery.py`, `research/final_build/v1_1/CLOUD_HOSTING_PLAN.md`,
this file, `research/final_build/v1_1/evidence/I_runtime_proof.json`.
Modified: `src/brambleloop/gateway/model_gateway.py` (attempt recording + per-model breaker keys),
`src/brambleloop/ops/health.py` (`ops.slo` added to `SELF_OBSERVING_JOB_TYPES`).
`ops/incident_lifecycle.py` reused unchanged.

## Tests (`cd brambleloop && PYTHONPATH=src python3 tests/<file>`)

| Suite | Result |
|---|---|
| test_v11_reliability_slo.py | 26 OK, 0 FAIL |
| test_v11_reliability_gateway.py | 14 OK, 0 FAIL |
| test_v11_reliability_recovery.py | 12 OK, 0 FAIL |
| test_gateway.py (existing) | 30 OK, 0 FAIL |
| test_health.py (existing) | 39 OK, 0 FAIL |
| test_incident_lifecycle.py (existing) | 7 OK, 0 FAIL |
| test_cert_cost / test_model_spend_paths / test_cost_governance_wave2 / test_spend_policy / test_model_identity / test_gates / test_cert_spend_hosts | 19 / 12 / 39 / 24 / 28 / 44 / 4 OK, 0 FAIL |
| test_vacuity.py | my files clean; 3 pre-existing findings in files I did not touch (test_launch0_listing_truth, test_pattern_truth, test_web_security) |
| test_secret_scan.py | 1 pre-existing finding in `tests/test_rc1_ord2.py:169` (not mine) |
| test_rc1_spend.py | 19 OK, 1 FAIL pre-existing/environmental (`numpy` missing in this interpreter) |
| test_cert_claude_independence.py | 3 OK, 1 FAIL pre-existing (Dockerfile `COPY release` vs the test's allowed set; Dockerfile untouched) |

## Runtime proof

`scratchpad/laneI/runtime_proof.py`: a real `Scheduler.tick()` and a real `Worker` (restricted to
`ops.heartbeat` / `ops.queue_check`, so no handler can reach the network) on a scratch SQLite file for
400 s of wall clock, with the scheduler heartbeat + lease written exactly as W-1 asks; then
`ops.slo.summary` and `ops.slo.check` on the resulting rows. Output committed as
`evidence/I_runtime_proof.json`; summary below in "Observed". This proves the code path on real
scheduler/worker rows locally. It is **not** production evidence and not a soak.

## WIRING REQUESTS

**W-1 (lane A — `app/runner.py::_scheduler_loop`, and `app/scheduler_entry.py` loop):** after a
successful `Scheduler(db).tick()`:
```python
from ..ops import slo as _slo
try:
    _slo.record_heartbeat(db, "scheduler", instance=name_or_pid, detail={"enqueued": len(enqueued)})
except Exception:  # noqa: BLE001 - liveness evidence must never stop scheduling
    log.exception("scheduler heartbeat row not written")
```
In the split topology (`scheduler_entry`, `BRAMBLELOOP_SCHEDULER_ONCE=0`) wrap the tick in
`if _slo.acquire_lease(db, "scheduler", holder, ttl_s=180):` (renews each tick; a second scheduler
idles). Not needed in the single container (`numReplicas: 1`, idempotent window keys).

**W-2 (lane A — `app/runner.py::_worker_loop`, index 0 only):** at most once per 60 s
`_slo.record_heartbeat(db, "worker", instance=name)` in the same try/except shape.

**W-3 (lane A — `app/runner.py`):** a supervisor thread: if `STATE.scheduler_last_tick` is older than
15 min (and `STATE.starting` is false), `log.critical(...)` then `os._exit(1)` so Railway's restart
policy replaces the container. Opt-out env `BRAMBLELOOP_SELF_EXIT_ON_STALE=0` for tests.

**W-4 (lane A — `runtime/worker.py::CADENCES` + handler registration in `runtime/pipeline.py`):**
```python
("slo_check", "orchestrator", "ops.slo", 15 * 60),
```
```python
@handlers.register("ops.slo")
def handle_slo(ctx: JobContext) -> dict:
    from ..ops import slo
    r = slo.check(ctx.db)
    return {"ran": True, "inspected": len(r["slos"]), "incidents": r["incidents"]}
```
plus `"ops.slo"` in the orchestrator agent's `allowed_job_types` (`agents/registry.py`) and in
`swarm.orchestrate.LIVENESS_JOB_TYPES` (a watchdog must never be backed off).

**W-5 (lane C — `app/main.py`):** Operations page reads `brambleloop.ops.slo.summary(db)`. Owner-auth
POST routes (through `app/security.py`, CSRF as for other owner actions), actor = authenticated identity,
`request_id` generated client-side per tap:
`recovery.restart_stuck_job(db, job_id, actor=, request_id=)`,
`recovery.release_stale_lease(db, name, actor=, request_id=)`,
`recovery.rerun_department_cycle(db, cadence, actor=, request_id=)`; GET `recovery.recent(db)`.
Optional read-only GET for the soak grade: `slo.soak_report(db, start=<iso>)`.

**W-6 (integrator — `core/db.py::Database.create_all`):** add
`from ..ops import slo as _slo_tables  # noqa: F401; v1.1 SLO samples + leases` beside the Learn
import. (`slo` also creates its two tables lazily on first use, so nothing breaks before this.)

**W-7 (integrator, after owner approval):** `railway.json` diff and new `railway.watchdog.json` exactly
as in `CLOUD_HOSTING_PLAN.md` §2.1–2.2 (`restartPolicyType ALWAYS` is already accepted by
`test_cert_claude_independence`).

**W-8 (integrator — `runtime/release.py` lines ~4391, ~4505, ~4633, ~5010; `intel/vision.py`,
`creative/blinded.py`, `creative/prospecting.py` where they build a gateway):** replace
`ModelGateway([AnthropicProvider(model=tier.model)], registry=ctx.registry, job_id=ctx.job.id)` with
```python
from ..gateway import failover
gateway, _decision = failover.gateway_for(ctx.db, <TASK_KEY>, registry=ctx.registry,
                                          agent=<agent>, job_id=ctx.job.id)
```
where `<TASK_KEY>` is the key already passed to `routing.route(...)` on the line above. `Parked`
subclasses `TransientError`, so the worker's existing retry/backoff handles it.

## Observed / not verified

* Observed locally (`evidence/I_runtime_proof.json`, 400 s wall clock, after the fix below): 20 real
  scheduler ticks, 3 jobs run by the real worker, scheduler lease live, overall status OK;
  scheduler_freshness MET 1.0, queue_latency MET 1.0, department_heartbeat MET 1.0;
  availability / cadence_freshness / recovery_time / department_useful_work UNKNOWN (no probe, too
  little history, no incidents — correctly not graded); no incidents opened. The first run (before
  the fix) opened 12 department incidents on a six-minute-old system.
* `summary(db)` does not embed `ops.health.read` (it needs process-local runner state); the
  Command Center should show both providers side by side.
* NOT verified: anything in production (no deploy, no Railway access); Railway prices (ASSUMED);
  Railway healthcheck semantics and volume-backup availability on the owner's plan; App Sleeping state;
  whether production's scheduler runs between `/api/verify` pokes.
* Defect found and fixed by the runtime proof: department SLOs judged a six-minute-old system
  against a full day and opened 12 incidents; expectations now scale to the company's history in
  the window (under 1 h → UNKNOWN), and the aggregate useful-work breach no longer duplicates the
  per-department incidents (regression test `test_a_just_started_company_is_not_judged_against_a_full_day`).
* Open defect noted (not mine): `gateway.routing.USD_PER_CAD = 0.715` vs `gateway.anthropic.USD_TO_CAD
  = 1.37` (1/0.715 = 1.399) — two FX assumptions; failover uses the anthropic one (the one that bills).
* `soak_report`'s "follow-on work" criterion is a proxy (non-cadence jobs created); swap for lane A's
  mission/handoff rows once integrated.
