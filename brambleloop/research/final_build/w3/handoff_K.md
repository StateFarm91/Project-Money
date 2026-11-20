# Handoff — wave-3 lane K (Final Master closure audit)

Branch `claude/w3-K`. Base: `claude/v11-CANON` @ f0c2d12. Only research outputs changed; no `src/` edits.

## Requirements addressed
| Requirement | Status | What was done |
|---|---|---|
| F-177, F-843 | PARTIAL | Mechanical closure regenerated on f0c2d12, plus a triage overlay. The fold into the canonical mapping is left to the integrator. |
| F-839 | PARTIAL | Reachability regenerated on f0c2d12. The independent re-audit of a frozen successor is still outstanding. |

## Files
| File | What changed |
|---|---|
| `research/final_build/module_reachability.json` | Regenerated on head. It now covers 503 modules, of which 425 are reached. |
| `research/final_build/closure_matrix.json`, `LAUNCH_SCOPE.json` | `aggregate.py` was re-run. Only the basis line changed. |
| `research/final_build/w3/closure_w3.py` | Triage and overlay script. It can be re-run. |
| `research/final_build/w3/CLOSURE_f0c2d12.json` | Machine-readable result. |
| `research/final_build/w3/CLOSURE_f0c2d12.md` | Human summary. |

## Tests
`tests/test_final_closure_matrix.py`: 12 passed, 0 failed. `tests/test_final_proof.py`: no failures.

## Result
- **Mechanical layer:** launch-critical rows stand at 73 COMPLETE, 66 GATED and 300 OPEN. This layer is out of date, because its mapping rows still come from 6f9a2f7.
- **Triage layer:** 138 COMPLETE, 91 GATED and 210 OPEN. The OPEN rows split into 181 buildable (clusters K1–K14), 10 PROCESS, 16 STRUCTURAL and 3 REMAP.
- **v1.1 rows:** 35 are complete pending re-certification, 8 are GATED and 8 are OPEN (clusters K15 and K16).

## Wiring requests
1. **Fold the triage into the canonical matrix.** Turn the R rows in `CLOSURE_f0c2d12.json` into `mapping/remap_f0c2d12/*.json`, add the SHA to `aggregate.REMAP_SHAS`, then re-aggregate. An independent accept is required first (F-867).
2. **Decide the STRUCTURAL rows.** Add `overrides.json` entries for the 16 rows whose producer is operator tooling: either target TESTED, with a reason, or move them to post-launch.
3. **Register the new scope.** The Laura rulings (spec/07) and the store-preview v2 work should be registry rows or `overrides.json` entries (F-847).

## Not verified
- I did not run the tests cited for the R rows.
- I did not re-check rows that were already mechanically GATED, or the M rows.
- I have no runtime or production proof for any row.
