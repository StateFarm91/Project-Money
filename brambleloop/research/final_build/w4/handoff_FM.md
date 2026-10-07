# handoff FM (wave 4) — existing Final Master completion

Branch `claude/w4-FM` (base claude/visual-investigation @ fee1cfe). Worktree `.claude/worktrees/W4-FM`.

## Status
- [x] module_reachability.json regenerated on fee1cfe (622 modules, 523 reached; none lost vs f0c2d12).
- [x] FM_LEDGER.json/.md v0 (917 rows: 866 v1.0 + 51 v1.1) via w4/fm_ledger.py; claims parsed by w4/claims.py
- [x] FM_OPEN_CLUSTERS.json v0 (launch-critical OPEN 351 before fold; hand-off clusters K5a/K5b/K9/K12/K2/K8/K16 to other lanes)
- [ ] fold wave-3 claims into mapping/remap_fee1cfe + re-aggregate snapshot

## Next deterministic action
Build w4/fold.py: remap FOLD + FOLD-R rows on fee1cfe (verified tests + reached producer), fold into mapping s*.json, add REMAP_SHAS fee1cfe, re-run aggregate, regenerate ledger.
