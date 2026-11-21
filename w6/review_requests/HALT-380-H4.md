VERDICT: H4 PARTLY CONFIRMED. A real starvation path exists and is fixed, but none of the four named candidates is it, and the production readback does not prove it caused the ~15 h verify gap.

# Review request: HALT-380 H4 (rebuild jobs starved, not wrong)

**Branch:** `eng/halt-380-h4`, cut from `claude/w6-release-19d1`. Not merged, not deployed, no PR.
Production is unchanged.

**Input:** the production 7b250d61 readback quoted in the brief:
- done 171 / pending 12;
- oldest unfinished 0.13 h;
- `already_queued` 50, `retry_waiting` 2;
- 8 verified in 24 h, the newest at 2026-11-20T13:12Z.

This session did not read production. It holds no operator token and read no Railway values.

## What was tested

`brambleloop/tests/test_halt380_h4_rebuild_drain.py` drains the real worker on a
production-shaped estate. What is real and what is stubbed:

- **Real:** queue, claim tier, aging, `lane_hold` / `share_decision`, the `chain.rebuild`
  handler, `ops.sentinel` and its propagation, and the cadence keys.
- **Estate:** the 12 live HALT products, each certified with a stored release. Each has a pdf
  and a marketing artefact recorded under the pre-deploy chain fingerprint. The chain then
  moves.
- **Stubbed:** only the three stage handlers that a targeted rebuild enqueues
  (`gate.certify`, `assets.build`, `pricing.position`). The stub rewrites the product's
  provenance rows under the current fingerprint and binds them to the stage job.
  Whether a stage rebuilds artefacts correctly stays covered by
  `test_eng_stale_rebuild_loop` end-to-end.
- **Simulated time:** `run_after`, `created_at` and `finished_at` are shifted back in 10-minute
  steps. Each simulated hour enqueues the hourly `ops.sentinel` and the whole-catalogue
  `chain_rebuild` cadence under their real keys.

| Candidate from the brief | Result | Test |
|---|---|---|
| (1) pending jobs re-created, or `run_after` pushed forward before a claim | **Refuted.** Across the next hour's sentinel and cadence, the same 12 pending verify jobs keep their ids, and `run_after` moves only with the clock. | `test_h4_hourly_cadence_and_sentinel_do_not_reset_a_pending_verify` |
| (2) the boot sweep or hourly `chain_rebuild` supersedes them | **Refuted.** The whole-catalogue scan never touches targeted jobs: it has no code path that updates a job row. All 12 products verify with 2/2 artefacts completed. | `test_h4_twelve_stale_products_each_reach_verify_and_verify_completes` |
| (3) deploy restarts kill leases and the attempt cap ends them | **Refuted at this rate.** One `chain.rebuild` lease is killed every 20 simulated minutes. Every product still verifies and no verify job dead-letters. | `test_h4_deploy_restarts_do_not_exhaust_verify` |
| (4) idempotency keys collide, so verify never enqueues | **Refuted.** `rebuild-verify:{slug}:{job.id}:{n}` is unique per attempt, and all 12 verify jobs were enqueued. | same as (2) |

## What was found instead: protected work was held by the function mix

The reproduction used two workers. One other job is running, for example a
`listing.package`, so the `distribution` function holds 1 of its 1-slot share. One ordinary
`radar.scan` job is waiting.

In that pool, **every** claimed `chain.rebuild` was handed back by `share_decision`:
- 32 `swarm.lane_held` audits, all `function_share`;
- the reason recorded each time: "distribution already runs 1 of 2 workers against a share
  of 1, while ['market_intelligence'] have runnable work below their share";
- first passes never ran, so no verify job was ever enqueued.

`chain.rebuild` is in the `truth_defect` claim tier. The claim tier (CB2-G02) exists so that
ordinary work never runs while runnable protected work waits. `share_decision` inverted that:
the claim took the protected job first, and the share then returned it every 60 s so that
ordinary work of another function could run.

This fits the readback's shape: stage jobs and other distribution work occupy the function,
and ordinary backlog is nearly always waiting. Rebuilds then run only when the distribution
function happens to be idle at the moment of the claim.

## Fix

In `brambleloop/src/brambleloop/swarm/capacity.py`, `share_decision` now lets a job yield
only to waiting work of its own claim tier or a higher one: `claim_tier(waiting) <= claim_tier(job)`.
This applies to both the function mix and the production-lane split.

What that means in practice:
- Protected work never yields to ordinary work.
- The mix still binds among ordinary work exactly as before.
- The mix also still binds among protected work of one tier. Two `test_cert_lanes_capacity`
  tests depend on that (`ops.queue_check` yielding to `support.triage`). A first, blanket
  exemption broke them, so it was narrowed to the tier filter.

**No gate is weakened:**
- An ordinary job in the same pool is still share-held. The test asserts this, and also
  asserts that protected work still yields to protected work of another function.
- The hard agent-lane concurrency limit (`claim_decision` inside `lane_hold`) is unchanged.
- No validation, withholding, `rebuild_withheld`, binding or verify-attempt rule was touched.
- No budget or spend path was touched.

**Mutation check:** with the `capacity.py` change reverted, the lane test (32 holds, 0
verified) and the gate test both fail. With the change, all 5 tests in the suite pass.

## Honest limits

- The readback says the oldest unfinished rebuild is 0.13 h old. Chronic holding of *existing*
  jobs would leave older pending rows, so this is not proof that the share hold caused the 15 h
  gap. It is the one starvation mechanism the drain reproduces.
- If production verify passes do run and come back stale or unbound, the cause is "wrong", not
  "starved". In that case the next readback should show `chain.rebuild_unbound` rows or
  `rebuild-incomplete:*` incidents.
- Ask the readback for these: `swarm.lane_held` audits with `artifact = chain.rebuild` in the
  last 24 h, the `chain.rebuild_verified` detail (`outstanding` / `unbound`), and the
  `chain.rebuild_unbound` count.
- Production runs Postgres. This suite ran on SQLite only.

## Suites run (SQLite, this branch)

- `test_halt380_h4_rebuild_drain`: 5/5.
- `test_cert_lanes_capacity`: pass.
- `test_eng_stale_rebuild_loop`: pass. Its Postgres half was skipped because there is no local
  toolchain.
- `test_cert_rebuild_chain`: pass.
- `test_vacuity`: pass.
- `test_w4_resume_runner`: one failure, `test_f7_the_declared_final_segment_set_covers_every_matching_suite`.
  It names `test_clothing_e2e.py` and `test_eng_animals.py` as undeclared. It fails identically
  on the base `claude/w6-release-19d1` (pre-existing, not this change). The new suite is
  declared in `scripts/suite_final_segment.txt`.
