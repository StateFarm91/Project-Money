# SECREL (2026-10-26): security patch, certified

Integrator: W-INTEG5. **No deploy was made.** Production is 051dbee2, re-read by `ops/deployed_sha.py` at about 19:35Z.

| | |
|---|---|
| Suite SHA | **`4ff953da1d51c31a8d8856d971a4d483d6975dd0`** (`claude/w4-SECPATCH`; frozen as `claude/final-candidate-4ff953d`) |
| Deploy head | **`b2e49455`** = 4ff953d, then release record 5abc9676, then DEPLOYED_HISTORY. Records only. |
| Content | public-surface deny-by-default (`PUBLIC_GET_ROUTES` allow-list), public projections, owner-text scrub |
| Independent review | ship YES, no blocking findings (7412c124). The F1 follow-up rides the combined release as SECPATCH2. |
| Full suite | run `20261026T172357Z-3395`: 682 suites, 7627 s. **9125 passing, 0 failing, release_eligible true** |
| deploy_guard record | `RELEASE_4ff953da….json`, tree_sha256 `a2f38e718b0b…` |
| `DRY_RUN=1 sh ops/deploy.sh --deployed 051dbee2…` | **ALLOW**, including its built-in rollback check |
| Rollback rehearsal | to 051dbee2: **ALLOW** |
| Migration | no schema change (no model, table or column edit from 051dbee2 to 4ff953d) |
| DEPLOYED_HISTORY | adds 051dbee2. The 15800536 entry is reconciled with INTEG4's evidence. The file is byte-identical to Batch 2's 62770fbe, so later merges do not conflict. |
