# handoff R-AUTO: lane J autonomy findings (audit ddf9c6e) repaired

Branch `claude/r2-AUTO` from `claude/visual-investigation` @ 5acf26d (contains r2-SEC). Phase stays
shadow; no Railway call, no network, no spend. `railway.json` untouched.

## Per finding

| ID | Status | What changed |
|----|--------|--------------|
| H-1 | COMPLETE | `runtime/pipeline.did_no_work(outputs, job_type=None)` is the one judge: empty, `ran:false`, `measurable:false` → no-op; explicit `work_done`; per-job-type `WORK_KEYS` declaration (every one of the 100 cadence types + all SAFE_GENERATED types declared, test-enforced); undeclared types are useful only with a generic work counter > 0 or a durable artefact key. `reading_id` is not an artefact. `department_review` / `morning_handoff` no longer hardcode `generated: 1`: they report `new_finding` / `new_brief` = content hash differs from the previous snapshot/brief (clocks/ids stripped) or `lessons_routed`. Callers pass the job type: orchestrator `reconcile_missions`, `kpis`, `status`, `proof`, `handlers.build_brief`, `ops.slo.departments` (soak criterion reads `departments`). Failure of the judge now means "not useful" (was "useful"). `ops.queue_check` re-drive keeps the old narrow rule as `reported_no_work` (a once-per-deploy cost decision, not a usefulness measurement). |
| M-1 | COMPLETE | `kpis.VOLATILE` strips snapshot/brief keys, run/request/trace ids, lease token, attempts, created/updated stamps; ISO timestamps inside strings are normalised. Self-measurement types (`department_review`, `morning_handoff`) are excluded from the department's own KPI and from the brief. 10 identical reviews → 1 useful. |
| M-2 | COMPLETE | `Scheduler.tick` isolates each cadence: failure → deduplicated P2 incident `scheduler.cadence_failed:<name>` + audit row, other cadences continue, tick completes (runner heartbeats → no stale self-exit). Only a tick where every attempted cadence failed raises. Restart-loop risk documented in `CLOUD_HOSTING_PLAN.md`. |
| M-3 | COMPLETE | Soak criterion now reads `queue.lease_reclaimed` audit rows (new, written on every reclaim), `effect_intents`, `draft_creation_intents`, `effect.duplicate_refused`, and cost entries on reclaimed jobs / duplicate request ids. Reclaimed job not declared effect-free and without an intent → FAIL. SIGKILL double-apply repro → FAIL; guarded variant → PASS with 1 refused duplicate. |
| L-1 | COMPLETE (paid calls PARTIAL, stated) | `queue/effects.py`: `EffectIntent` table (lazy `ensure_table`, no shared-file edit), `guard()` = `ctx.assert_lease()` + write-ahead claim + APPLIED / RELEASED (`EffectNotSent`) / UNCERTAIN; repeats refused with P1 reconcile incident. `JobContext.assert_lease()` / `ctx.effect()`. Applied to `store.activate`; `store.publish` keeps `draft_intent`. `EFFECT_INVENTORY` + `AT_LEAST_ONCE_EFFECTS` document semantics: paid model calls remain at-least-once (gateway not owned) and are caught by the soak. |
| L-2 | COMPLETE | Scheduler skips a blocked department's cadences (never-pause departments exempt via the single F-889 rule). Blocks default to 24 h expiry (`BLOCK_DEFAULT_TTL`); legacy rows without `until` lapse 24 h after `since`; explicit `renew_block`. |

## Changed test expectations (read these)
* `test_v11_autonomy_overnight`: `sum(useful missions) >= 30` → `>= 15`, plus new assertions that no review hardcodes usefulness and each review's verdict equals its `new_finding`/`lessons_routed`. The 30 was produced by the vacuous judge (H-1); honest measured value on that simulation: 16.
* `test_persistence`: `did_no_work({"ran": True})` / `did_no_work({})` were asserted *useful*; that is the H-1 defect, now asserted no-op; the old behaviour is asserted for `reported_no_work`.
* `test_v11_autonomy_kpis`, `test_v11_reliability_slo`: synthetic fixtures renamed to the real handlers' declared keys; assertions unchanged.

## Out-of-lane edit
`ops/retention.py` KNOWN_READ_ACTIONS: added `queue.lease_reclaimed`, `effect.duplicate_refused` (windowed). Without it `ops.retention` refuses to run (unknown read action).

## Runtime proof (real runner, `python -m brambleloop.autonomy.proof --seconds 660`)
`R-AUTO_runtime_proof.json`: 660 s, closed network, shadow, 0 restarts, 0 cost rows, 266 jobs; 249 done:
**117 useful / 132 no-op**; 10 dead = shadow refusals of `store.publish`. Orchestrator generated 19
missions: 8 useful, 3 no-op, 8 still queued at window end; last tick: support, finance,
intelligence SATURATED. product_design 1/30 useful, support 1/2, finance 2/9.

## Not verified
Postgres; real Railway restart counter; a 24 h soak (still GATED); effect guard on live Etsy.
