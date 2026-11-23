# REDRIVE-FIRE: why neither image redrive fired, and the fix

Branch `eng/redrive-fire`, from b48ff952 (Batch 19i18 release record). Not merged, not deployed.

## What production showed (19i18, 2026-11-23T01:50Z)

- 6 image runs blocked:
  - `product_generation:budget:exhausted` ×3 (provider daily ceiling, from yesterday);
  - `fidelity_gate:product_truth` ×2;
  - `product_generation:provider` ×1.
- FLUX spend today: CA$0.07. The daily ceiling reset at 00:00Z.
- 23 candidates, unchanged since yesterday.
- The readback had no `method_redrives` field.

## The path, from the job registry to the restart

| Step | Code | Gate |
|---|---|---|
| Cadence | `runtime/worker.py` `CADENCES`: `("chain_successors", "listing", "chain.successors", 3600)` | hourly |
| Enqueue | `Scheduler.tick` | skips every job type in `swarm.orchestrate.suspended_job_types` (thrash breaker, free-poll backoff); skips blocked departments; `boot_deferred_run_after` (not set for this type) |
| Handler | `runtime/release.py` `handle_chain_successors` | none |
| Sweep | `runtime/chain_successors.sweep` → `image_production.redrive_capability_blocked` | none |
| Restart | `restartable` → `restart` (enqueues `visual.image_production` at a new epoch) | MAX_RESTARTS, budget-stop finality except the daily ceiling, one per UTC day, one per method version, headroom under the call and spend caps |

## Root cause: the sweep was parked by the backoff

`chain.successors` sat in the thrash breaker's free-poll backoff at ×32 (BUILD_STATE, Production
Diagnosis: "chain.successors (x32)"). That is 32 hours between runs.

The backoff treats three identical outputs as an idle poll. A sweep whose only blocked runs are
waiting for the UTC day to change does return identical outputs: only the clock moves, and the
clock is not in the outputs.

ENG-RECOVERY gives a parked free loop one probe run per new release. Under 19i18 (deployed
01:44Z) that probe came before the run was due, or ran and saw "waiting". The breaker then
re-parked the sweep. Nothing else wakes a backoff for this job type:
- it had no `UPSTREAM_INPUTS` and no `INPUT_PROBES` entry;
- its outputs could not change before it ran.

So the 00:00Z reset reached no code. The method redrive had the same dependency: it fired only
if that one per-release probe saw the run at the right moment.

### Candidates ruled out

- **Not scheduled or enqueued.** It is in `CADENCES` and `FREE_JOB_TYPES`, and not
  boot-deferred. It is skipped only while suspended.
- **SHADOW or the unproven-build halt.** The boot guard forces SHADOW on Railway, but no code
  on the image path reads the phase (`gateway/paid_provider_gate.py`,
  `visual/image_production.py`). Production spent CA$0.07 on FLUX today while in SHADOW. The
  unproven-build halt (`release.unproven_build`, `halts_publication=True`) gates publication
  only (`production_evidence.publication_refusal_reasons`). Nothing was over-broad, so nothing
  was lifted. Galleries are already made before publication, as the owner wants, and
  publication stays gated.
- **`restartable()` reading a missing field.** The block's UTC day comes from `updated_at`,
  which `_update` sets on every block. Old unstamped candidates read as `pre-method` by design.
  Both work on the fixtures.
- **The evidence field not wired: true, and a separate defect.** `production_evidence._vp_runs`
  never read `stages._method_redrive`. The sweep's counts appeared only in the
  `chain.successors` job outputs, which a parked job never produced. The handler's audit row
  left the image fields out entirely.

## The fix

1. **The sweep's input, read from the rows.** `visual/image_production.redrive_due(session,
   since)` returns the first blocked run that the sweep would restart now but could not have
   restarted when the backoff was recorded. That is one of:
   - a daily-ceiling stop whose UTC midnight passed after `since`, and which has not been
     redriven today;
   - a fidelity block whose FAIL frames all come from another method version, with no restart
     under the current version and no readback under it.

   Both exclude runs at MAX_RESTARTS and experiment runs (`#` keys).
   `swarm.orchestrate.INPUT_PROBES["chain.successors"]` calls it, so `upstream_progressed` lifts
   the backoff, and `_free_poll_backoff` does not deepen it, while a restart is due. This is the
   existing mechanism for "the input changed" (ENG-LEARN). `chain.successors` is not made a
   liveness loop, so an idle sweep still backs off.
2. **The probe cannot hold the sweep at hourly.** A due run stops being due once the sweep
   acts:
   - it is unblocked;
   - today's redrive is in its history;
   - or its method readback names the current version.

   A method redrive whose restart was refused (cap, race) now records the readback as
   `eligible` under the current version.
3. **The evidence is wired.**
   - `visual_pipeline.galleries.method_redrives` holds `{eligible, done, no_headroom}` counts
     under the current method. The field is always present, so zero means none were judged.
   - `visual_pipeline.galleries.redrive_due` holds `daily_ceiling_reset`, `method_redrive` or
     None.
   - The `chain.successors_swept` audit adds `method_redrives` and the image run keys
     (restarted, waiting, refused).

## Unchanged

- Every cap: per-gallery spend (`effective_cap`), the call cap, the provider's daily and
  monthly ceilings, MAX_RESTARTS.
- One restart per UTC day and one per method version.
- Spend, calls and attempts are not reset.
- The probe restarts nothing; the sweep does, under all of the above.

## Tests

`tests/test_redrive_fire.py` (new) drives the real path: `Scheduler.tick` → `Worker.run_once` →
handler → sweep → restart. The backoff comes from the real `thrash_sweep`, then is held at ×32
as production showed.

- **Blocked yesterday on the daily ceiling, restarts today.**
  - Without the probe (the 19i18 breaker), the sweep stays suspended and no job runs.
  - With it, the backoff lifts, the next window runs the sweep, and the run restarts once at
    epoch 1. Calls and spend are unchanged, and the history records `daily_ceiling_redrive`
    with today's date.
  - Blocked again today: nothing is due, the backoff stands, and there is no second restart.
- **Old-method fidelity block.**
  - Parked under the current release, so the re-arm probe cannot reach it.
  - It restarts once at `product_generation` under the current method, and the readback shows
    `method_redrives.done == 1`.
  - After a FAIL under the current method: nothing is due, and the sweep refuses with
    `method_redrive:already_redriven`.
- **No headroom.** Judged once (`no_headroom`), then not due again.
- **Not due.** A ceiling stop from today, any other budget stop, and a run at MAX_RESTARTS.
- **Readback.** The field is present with zeros when nothing was judged.

Suites run (`SUITE_REGISTRY=0 SUITES=... JOBS=$(nproc) PY=python3 bash run_tests.sh`, run record
20261123T015808Z-1683): **21 suites, TOTAL PASSING 251, suites failing 0.** They are:
- test_redrive_fire, test_image_method_redrive, test_image_daily_ceiling_redrive and
  test_vacuity;
- test_eng_recovery, test_swarm_runtime, test_r2_autonomy_useful_work, test_watchlist_cadence,
  test_eng_learn_wiring, test_eng_improve, test_eng_daily and test_eng_catalogue_agents;
- test_opus2_chain_deadends, test_v2_capability_redrive and test_p0_storefront_asset_fix;
- test_visual_pipeline_evidence, test_visual_factory_e2e, test_vis_gallery_e2e,
  test_w4_readback_evidence, test_w4_ccgap_live and test_w4_close5_rows4.

test_audit_build_state_current also passes (4/4). The full suite was not run.

## Not verified

- **The live effect.** It needs a deploy, and this branch deploys nothing. After a deploy, the
  readback should show:
  - `galleries.redrive_due` going to None within an hour;
  - 3 restarts by `daily_ceiling_redrive` (any that still meet today's CA$0.07 ceiling block
    again, which is correct);
  - `method_redrives` counts for the 2 fidelity runs.
- **Whether the 19i17 probe reached the fidelity runs.** That cannot be read offline. If it
  did and they were refused for headroom, `method_redrives.no_headroom` will say so on the next
  readback.
- **The ×32 level on 19i18 specifically.** It is taken from BUILD_STATE's diagnosis of the same
  loop. It was not re-read from production for this report.
