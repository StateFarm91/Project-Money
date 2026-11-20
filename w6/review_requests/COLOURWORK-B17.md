# Review request — ENG-COLOURWORK × Batch 17

- Branch: `eng/colourwork`
- Merge commit: `b098fccea62b9f2647b9356a24c99c5df1fe3534`
  (parents: eng/colourwork `78d62994`, claude/w6-INTEG7-wip `c6d4400a`, which is dde3ea62 + garment(+plush) + pdf-premium + vis-identity + wardrobe-scenes + daily)
- Written 2026-11-20 UTC. No PR opened; no secrets or Railway variables read.

## Conflict resolution (both sides kept)
| File | Resolution |
|---|---|
| cir/model.py | `chart` + `stuff_at_round`/`closes`; to_dict optional-pop list = gauge, work_direction, feature, chart, stuff_at_round (closes popped when False) |
| cir/compiler.py | `colourwork.chart_findings` (on clean arithmetic) and `closed_forms.check` both run |
| creative/fallback_constructions.py | colourwork route first, then lovey, then amigurumi |
| runtime/pipeline.py | COLOURWORK_TAPESTRY, AMIGURUMI, ENVELOPE/APPLIQUE/LOVEY elif blocks |
| creative/construction_families.py | garment families + proofs, plush pairs, colourwork pairs; technique split colourwork / mosaic_or_c2c / charted_tapestry; `garment_or_wearable` → GARMENT_FAMILIES; LOVEY declared-family rule + tapestry basket exception |
| tests/test_eng_families.py | admitted set + FEATURE_SAMPLES + pair probes include every family |
| DECISION_LOG.md, research/.../construction_families.md, scripts/suite_final_segment.txt | kept both / union |

Two semantic fixes after the textual merge:
1. `tests/test_eng_families.py` had two `_proof_exists` definitions; colourwork's narrower one (families/colourwork suites only) shadowed the general one and rejected the plush/garment proofs. Removed the narrower duplicate. Restored the `here` binding the garment-side check uses.
2. `publish/pdf_standard.py::_LABEL` read "Stuff after Rnd 16:" / "Close after Rnd 18:" as round labels → "Rnd 16 has no stitch count". **Pre-existing on INTEG7 itself** (test_eng_plush failed 3 tests at c6d4400a). Fixed with a `(?<![Aa]fter )` lookbehind; test_pdf_standard 23/0.

## b17-b finding 2 (chart-mirror mutant)
Added to `tests/test_eng_colourwork.py`:
- `test_a_chart_of_rounds_is_drawn_mirrored_with_stitch_one_at_the_right` — renders A,B,C with `rounds=True`, samples cell fill pixels (page order must be C,B,A) and the printed column numbers (3,2,1).
- `test_a_flat_chart_control_is_not_mirrored` — `rounds=False` gives A,B,C and 1,2,3.
Mutant (drop both `reversed(...)` in `render_chart`) → rounds test FAILS (`['A','B','C']`), control passes. Killed.

## Generated
`autonomy/autonomy_map.json` regenerated with `python -m brambleloop.autonomy.map --write`.

## Suites (`JOBS=4 SUITE_REGISTRY=0 bash run_tests.sh`, venv from the lock files)
| Suite | Passing | Failing |
|---|---|---|
| test_eng_colourwork | 20 | 0 |
| test_eng_garment | 28 | 0 |
| test_eng_plush | 25 | 0 |
| test_eng_families | 16 | 0 |
| test_opus2_amigurumi | 9 | 0 |
| test_compiler | 9 | 0 |
| test_twin | 8 | 0 |
| test_reverse | 18 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |
| **Total** | **181** | **0** |
Extra: test_pdf_standard 23 / 0 (touched by fix 2).

Not done: full unfiltered suite; b17-b findings 3 (originality unmeasured warning) and 6 remain open.
