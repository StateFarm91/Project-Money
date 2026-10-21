# test_cert_wiring timing evidence (W-INTEG4)

`time_handlers.py` runs a test file as `__main__` with every job handler wrapped in a timer and
prints the slowest job types (count, total s, max s). The test itself is unchanged.

| run | tree | conditions | result |
|---|---|---|---|
| quiet_2026-10-21T0005Z_prod_b931d17 | production b931d17 (W4-FC324927f worktree) | quiet machine, run concurrently with the candidate (one core each) | 16/16 in 825 s |
| quiet_2026-10-21T0005Z_cand_b997efd | candidate b997efd | same, concurrently | 16/16 in 844 s (+19 s, +2.3 %) |
| loaded_2026-10-20T1430Z_cand_6b25eb0+fixes | INTEG4 working tree between 6b25eb0 and b997efd | other sessions' tests running | 16/16 in 1194 s |
| loaded_2026-10-20T1555Z_prod_b931d17 | production b931d17 | other sessions' tests running | 16/16 in 964 s |
| full suite 20261021T002000Z-11418 | b997efd | quiet machine, other workers paused, JOBS=3 | 16/16 in 870 s |

The only job types b997efd adds to the drain are `visual.image_production` (23 jobs, 15.7 s quiet)
and about +6 s in `ops.maturity_disagreements`. No handler waits on a provider, a timeout or a
retry sleep. `visual.rnd.cycle`, whose code is identical in both trees, varied 178-254 s between
runs, so the earlier 1194-1620 s readings were CPU contention, not added work. The 1200 s drain
limit was not changed.
