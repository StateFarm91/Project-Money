# CERTFIX-4 review request

Branch `certfix/4` (from `claude/w6-INTEG8-wip` 511a8c6). Final SHA: see `git log -1 certfix/4` (the commit that adds this file; recorded in the push message). NOT merged, NOT deployed, no PR.

Counts are OK / FAIL per suite, run locally with `PYTHONPATH=src:tests` after installing requirements.lock + requirements-test.lock.

| Suite | OK | FAIL | Cause and fix |
|---|---|---|---|
| test_w3_decision_index | 3 | 0 | Regenerated `decision_index.json` with `python -m brambleloop.core.decision_index` (52 ids). |
| test_w3_tmp_hygiene | 16 | 0 | `test_eng_improve_readback.py` made temp dirs without the sandbox; added `import _tmp; _tmp.install()`. |
| test_eng_catalogue_perf | 3 | 0 | Cold read 1.13-1.26 s idle (was 1.9-2.7 s), bound still 2.0 s. See note 1. |
| test_final_closure_matrix | 12 | 0 | See note 2: a shallow clone lacked the commits; no code change. |
| test_w4_fmbatch1_adoptions | 2 | 0 | Added the `onnxruntime` adoption row. |
| test_w4_fmbatch1_licenses | 4 | 0 | Added licence rows: onnxruntime (MIT), flatbuffers (Apache-2.0), protobuf (BSD-3-Clause), packaging (Apache-2.0 OR BSD-2-Clause), from installed metadata. |
| test_w4_fmbatch1_drift | 10 | 0 | See note 3: fixture change, not a licence/drift entry. |
| test_ws4_7_postgres | 5 | 0 | Real defect; see note 4. Ran against a local Postgres 16 (installed, throwaway cluster). |
| test_vacuity | 8 | 0 | |
| test_w4_resume_runner | 40 | 0 | |
| test_w4_prodready_deps | 3 | 0 | Passes with the onnxruntime lock already present. |
| Neighbours: test_eng_improve_readback 5, test_eng_catalogue 13, _fix1 9, _agents 10, test_motif_backlog 26, test_r2_product_catalogue_depth 4 | all OK | 0 | Run because inventory loading and `register_models` changed. |

## Notes
1. **Perf.** The cold read was already grouped/indexed (not per-product scans); the profile showed the cost was building 70k job records. `_Job.from_row` unpacks the fixed-order column tuple once instead of a dozen Row attribute lookups. ORM-entity callers still use `__init__`. Behaviour is unchanged. Timing is load-dependent: under a busy 8-job cert run it may still approach the bound; I measured only on an idle 4-core box.
2. **Closure matrix.** The environment's clone was shallow, so the 40-char mapping SHAs (0417f35..., fee1cfe...) were not present. `git fetch --unshallow` fixed it; the matrix/basis files are unchanged. The cert checkout must have full history.
3. **Drift.** The fixture ran an unrestricted worker for 100 jobs. Since ENG-DEMAND-SUPPLY, `supply.admit` admits more concepts and builds five more products, so "a change elsewhere" touched their taxonomy nodes and `_profile` saw six profiles. The worker is now restricted to the hexagon chain's job types. No assertion was changed. It also fell from ~500 s to ~25 s.
4. **Postgres.** `motif_recovery` (publish/motif_backlog.py) was not imported by `Database.register_models`, so the migration owner never created it and the worker refused to start ("1 table(s) do not exist yet"). That would have bitten a fresh production database too. Registered it. I also added the worker's stderr to the rc assertion message (diagnostic only). The suite SKIPs without a Postgres; it needs a Postgres binary (16 here) it can run as a throwaway cluster.

## Not done
Only the suites above were run, not the full ~1000-suite certification. The other failures in the cert lists (r5_research, shadow, swarm_runtime, v11_cc_views, w4_contracts, etc.) were out of scope.
