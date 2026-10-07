# handoff FM (wave 4) — existing Final Master completion

Branch `claude/w4-FM` (base claude/visual-investigation @ fee1cfe). Worktree `.claude/worktrees/W4-FM`.
Owned clusters (after the 2026-10-07 restart): FOLD, FOLD-R, REGATE, REMAP, STRUCTURAL, PROCESS,
V11-MAP; then K13, K14, K15. K5a/K5b -> lane SPEND, K9 -> lane K9 (skipped).

## Whole Final Master (917 rows = v1.0 866 + v1.1 51), launch-critical
| | at resume (ce36d9e) | now |
|---|---|---|
| PROVEN | 243 | 294 |
| OWNER/DATA/EXTERNAL-GATED | 76 (v1.0 only) | 114 |
| OPEN-DEFECT | 171 (120 v1.0 + 51 v1.1 unmapped) | 82 |
| ... after integrator accepts w4/OVERRIDES_PROPOSED_FM.json (19 structural rows, dry-run all COMPLETE) | | 63 |

## Done
- reachability: provider-table pair edge (build2/reachability.py, WIP 9e9cf0d completed) +
  tests/test_w4_fm_provider_table.py; module_reachability.json regenerated on 8b67414
  (+10 modules reached: finance/accounting/{dashboard,forecast}, seo/{status,strategy,constraints,
  learning}, learn/improvement_status, visual/rnd/{evolution,sequence,status}; none lost).
- w4/fold.py (180 rows on fee1cfe) and w4/close_fm.py (44 rows on 8b67414: REGATE 22, FOLD
  residuals incl. K8 W1 wiring landed, REMAP 3, K14 F-135; 4 honest refreshes stay OPEN:
  F-030/F-254 frames missing -> visual lane, F-159 prod logs unscanned, F-416 Dockerfile pins).
  Evidence per row in w4/CLOSE_REPORT.json + mapping/remap_8b67414/remap_w4_close.json.
- V11-MAP: w4/v11_map.py -> mapping/v11.json (51 rows); aggregate.py load_registry()/
  mapping_files() read master_registry_v1_1.json + mapping/v11.json, so the v1.1 rows are in
  closure_matrix.json, LAUNCH_SCOPE.json and the runtime snapshot build2/final_master_closure.json.
  v1.1: 41 COMPLETE, 8 GATED (deploy / bank feed / CASL), 2 OPEN (F-914 period controls ->
  CC wiring request; F-926 preview v2 -> lane STORE K16).
- K15: F-913/F-915/F-927 PROVEN via the provider-table edge; F-914 OPEN (wiring request below).
- tests/test_final_closure_matrix.py: registry-equality now covers v1.0 + v1.1 (stricter, not looser).
- w4/fm_ledger.py reads v1.1 from the canonical matrix.

## Integrator acceptance requested (F-867: a lane cannot certify itself)
`w4/OVERRIDES_PROPOSED_FM.json` = the 16 wave-3 TOOLS proposals + F-342, F-177, F-843.
Dry run: `python3 research/final_build/aggregate.py --overrides research/final_build/w4/OVERRIDES_PROPOSED_FM.json --dry-run`
-> 0 problems, every row COMPLETE (completion_target TESTED, structural producer).
Accept by copying entries into research/final_build/overrides.json with accepted_by set.

## WIRING REQUESTS
1. Lane CC (app/command_center/api.py + tabs.money): GET /api/cc/money must accept
   `period`/`window` and pass it to the accounting provider as `dashboard.summary(db, window=...)`;
   test a 7d request returns the 7d envelope (closes F-914).
2. Integrator (Dockerfile): pin `FROM python:3.11-slim@sha256:<digest>` and the apt
   fonts-dejavu-core version, then `scripts/supply_chain.py verify --strict` (F-416). (Docker Hub
   digest lookup was rate-limited 429 from this container.)

## Remaining (not lane-executable now)
- PROCESS (F-169, F-839, F-840, F-841, F-845, F-846, F-848, F-878): need the integrator's frozen
  successor candidate, release-eligible clean full suite, final_proof report and an independent
  re-audit on that SHA.
- K13 F-123 (vacuity BASELINE shrink across many lanes' tests), F-834 (final_proof on real packets).
- Production-gated rows (production_window etc.): owner deploy.

## Tests run (this lane, sequential, all exit 0)
test_w4_fm_provider_table 4, test_reachability, test_w3_reachability_dynamic, test_final_closure_matrix 12,
test_w3_final_master_gate 13, test_w3_overrides_proposed 6, test_maturity_request_snapshot 5,
test_final_proof, test_closure 27, test_master_registry_v11 5, test_final_master_registry 5,
test_vacuity, test_secret_scan, test_w3_tmp_hygiene.

## Resume
`git -C .claude/worktrees/W4-FM log -1`; regenerate: `python3 research/final_build/w4/close_fm.py --apply
&& python3 research/final_build/w4/v11_map.py && python3 research/final_build/aggregate.py &&
python3 research/final_build/w4/fm_ledger.py` (from brambleloop/).
