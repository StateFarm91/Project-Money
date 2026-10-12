# Handoff: wave 3 lane TOOLS (K13 closure tooling, K14 supply chain and deploy tooling)

Branch `claude/w3-TOOLS`. The work is in commit 1390cb6 from session 1, a merge of `claude/visual-investigation` (cfb19b5, no conflicts), and one completion commit. The base is f0c2d12.

## Rows

"COMPLETE" means: the code is in place, it has a test, and the runtime consumer is named. **Maturity in `closure_matrix.json` will not move until the integrator re-maps these rows and regenerates `module_reachability.json` on the integrated head.** That reachability file is still from f0c2d12, so `build2/final_master.py` is not in it yet.

| Row | Status | Evidence (test, and consumer) |
|---|---|---|
| F-129, F-136 | COMPLETE | `test_w3_final_master_gate::test_the_runtime_recomputes_every_verdict...`. Consumer: `build2/final_master` → `launch/readiness`, `executor.report` |
| F-130, F-860 | COMPLETE | `::test_executor_reports_parked_work_split_by_kind_and_the_final_master` |
| F-133 | COMPLETE | `::test_an_orphaned_partial_is_named_by_both...` |
| F-382, F-844 | COMPLETE | `::test_the_ladder_keeps_every_rung_distinct...` |
| F-400, F-879 | COMPLETE | `::test_post_launch_rows_never_block...` and `::test_the_launch_readiness_gate_consumes_the_closure` |
| F-831, F-832 | COMPLETE | `::test_complete_needs_a_named_producer_and_consumer` |
| F-838 | COMPLETE | `::test_only_an_explicit_keyed_gate_takes_work_out_of_open` |
| F-833 | COMPLETE | `test_w3_reachability_dynamic` (3 tests) |
| F-867 | COMPLETE | `::test_an_override_needs_a_reason_and_an_accepting_integrator` and `test_w3_overrides_proposed` (6 tests) |
| F-834 | GATED (`data`) | `final_proof` has never been run on a real evidence packet. It needs a production receipt. |
| F-123 | OPEN | The detector works, but its baseline of 109 entries has not been reduced. Those entries are in about 50 test files that other lanes own. Reducing it is a separate cross-lane task. |
| F-331, F-333, F-335, F-341, F-342 | COMPLETE (structural) | `test_w3_suite_job_identity` (6 tests): durable job id, attach, EXIT sentinel, a late observer in a fresh process, and the work/observer role split |
| F-158 | COMPLETE | `test_w3_supply_chain` (6 tests). `deploy_guard record` embeds the lock verification, the SBOM and the change record. |
| F-416 | GATED (`owner production_window`) | The base image is not pinned by digest and the apt package is unpinned. Both are named as findings, and the remedy is in `ops/DEPLOY_CONTROLS.md`. The Dockerfile is on the deploy path, so it was not edited. |
| F-159 | COMPLETE | `test_secret_scan`, including scanning inside PDF streams |
| F-380, F-381 | COMPLETE (code). Rehearsal GATED (`production_window`) | `test_w3_deploy_evidence` (3 tests): a `release.boot_verdict` audit row, and the known-good predecessor taken from DEPLOYED_HISTORY |
| F-397 | COMPLETE | `test_w3_hq_independence` (4 tests) |
| F-135 | GATED (`production_window`) | The lease-recovery drill needs an authorised deploy. |
| F-461 | GATED (owner, `deploy_trigger_config`) | The exact owner steps are actions 1, 2 and 5 in `ops/DEPLOY_CONTROLS.md`. `railway.json` was not touched and nothing was deployed. |

## STRUCTURAL proposal (lane K's 16 rows)

The proposal is in `research/final_build/w3/OVERRIDES_PROPOSED.json`. Every entry has `accepted_by: null`. A dry run of it:

```
python3 research/final_build/aggregate.py --overrides research/final_build/w3/OVERRIDES_PROPOSED.json --dry-run
```

raises 0 problems and makes all 16 rows COMPLETE at a TESTED target.

Four rows go further than lowering the target:

- **F-344 and F-350:** their partials were stale. `ffcb62e` added registry-ack accounting and `ops/incidents.py`, and the proposal cites those.
- **F-836 and F-837:** the recorded defects are cleared. Both are now derived by code rather than declared by the packet: fixture provenance, reviewer `direct_confirmed`, and the `cap()` checks.
- **F-847:** the producer is now `aggregate.launch_scope`.
- **F-178:** once reachability is regenerated, re-map it to `final_master.py` at INTEGRATED and drop its override.

## Adjudicator changes made in this session

- `aggregate.py`: `maturity` is now an evidence override key, so an override can no longer lift maturity past `cap()`.
- `aggregate.py`: added a `--dry-run` / `--overrides` mode. A non-dry run refuses any file other than `overrides.json`.
- `aggregate.py`: a wave item whose uid is not in the registry is now recorded as a problem (F-847). Before, it was dropped silently.
- `final_master_closure.json` was regenerated. Its basis was stale after the merge.

## Wiring requests

None.

## What I could not verify

- Building the image from the lock.
- Any deploy or rollback rehearsal.
- `final_proof` on real packets.
