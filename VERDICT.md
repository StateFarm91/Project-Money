# Review b17-b — engine units A/B/C against claude/w6-INTEG6 (dde3ea62)

Reviewed 2026-11-20 UTC. Each unit merged locally onto dde3ea62 in its own worktree; nothing pushed to the unit branches, no PR opened, no secrets/Railway variables read.
Suites: `JOBS=2 SUITE_REGISTRY=0 SUITES="<unit suites> test_vacuity test_w4_resume_runner test_compiler test_twin test_reverse" bash run_tests.sh` (PY pointed at a throwaway venv built from requirements.lock + requirements-test.lock; the checkout has no .venv).

| Unit | Merge | Suites | Mutation | Verdict |
|---|---|---|---|---|
| A eng/garment @ 376a6046 | conflicts (docs/lists/generated map only) | 237 passing, 0 failing | caught | **SHIP** |
| B eng/colourwork @ 78d62994 | conflicts (DECISION_LOG, suite list only) | 162 passing, 0 failing | caught (float); chart-mirror mutant SURVIVED | **SHIP** (finding 2 must follow) |
| C eng/homedecor @ 33de16ac | conflicts (BUILD_STATE, DECISION_LOG only) | 114 passing, 0 failing | caught (FLAT_HI); `spans` mutant SURVIVED | **BLOCK** (finding 1) |

## Merge conflicts (resolved locally; none touched engine code)
- A: BUILD_STATE.md, DECISION_LOG.md (kept both), scripts/suite_final_segment.txt (union), autonomy/autonomy_map.json (kept base; it is generated, counts differ: cadences 148 vs 143 — regenerate with brambleloop.autonomy.map after merge).
- B: DECISION_LOG.md (kept both), suite_final_segment.txt (union).
- C: BUILD_STATE.md, DECISION_LOG.md (kept both).
- Branches were cut from older bases (64146306 / 307c7e62); a direct diff against dde3ea62 looks like mass deletions but the merge is additive — rebase, not diff-read, is the right check.

## Mutations (run on a copy, targeted suite only)
- A: gates/garment_fit.py SEAM_TOLERANCE 0.06→0.60, CHEST_TOLERANCE 0.05→0.50 → `test_mutation_finished_off_target_is_caught` FAILS (GARMENT_EASE_OUT_OF_BAND). Good.
- B: cir/colourwork.py MAX_FLOAT tapestry 12→999 → test_eng_colourwork 1 failure. Good.
- C: creative/homedecor.py FLAT_HI → 99 → `test_mutant_base_that_cups_or_ruffles...` FAILS. Good. But cir/geometry.py `increases = ... and not getattr(op,"spans",0)` reverted → 0 failures (survivor).

## UNKNOWN / gate-weakening check
- A: UNKNOWN is an ERROR (`CHILD_SAFETY_<code>_UNKNOWN`, `PART_GEOMETRY_NO_GAUGE`). No gate loosened; only additive. Pass.
- B: no gate removed; originality adds a `chart` dimension. Its "unmeasured" verdict (no benchmark chart captured) is not "material", i.e. does not escalate — same behaviour as the existing wording dimension (WARNING only for competitor-informed designs). Not new, but see finding 3.
- C: see finding 1 (in-module UNKNOWN→silent pass).
- Pre-existing in base (not introduced by any unit): gates/policy.py whole-word IP match lets "Disneyland …" through (see finding 4).

## Findings
1. **C — HIGH — UNKNOWN treated as PASS in `creative/homedecor.py::findings`.** When a vessel noun is in the title but the body twin has no readable rings (twin missing/`geometry is None`, e.g. no gauge), `_rings()` returns `[]`; the base-flat check needs `len(rings) >= nbase >= 2` and the bowl check needs `len(rings) > nbase`, so both silently emit nothing. Reproduced: `H.findings(dataclasses.replace(plain, title="Bowl Tide Basket"), {})` → `[]`. Fix: after `rings = _rings(twins, body.name)`, add `if not rings: err("VESSEL_GEOMETRY_UNKNOWN", "vessel claim cannot be checked: the twin has no readable geometry (UNKNOWN is not a pass)"); return out`; likewise error (not skip) when `body.foundation_kind != "magic_ring"` and the name claims round/bowl/lid. Add a test calling `findings(..., {})` and asserting the code.
2. **B — MEDIUM — chart PDF round orientation is unpinned.** Mutating `publish/charts.py::render_chart` so `rounds=True` no longer reverses `grid`/`colors` leaves every suite green; test_eng_colourwork `_pdfs` only checks key/text presence. Reading the code the orientation is correct (stitch 1 drawn at right, numbered from the right), so SHIP, but a wrong mirror would print a wrong customer chart. Fix: add a test rendering `render_chart(..., grids=([["a","b","c"]],[["A","B","C"]]), rounds=True)` and asserting the pixel colour at the rightmost cell equals colour A, leftmost equals C (and the label under the right column is "1"); and a flat (`rounds=False`) control.
3. **B — LOW — originality chart dimension "unmeasured" never blocks.** A charted tapestry with no captured benchmark chart is cleared on that dimension. Fix: in `gates/originality.py` where `dims["chart"]["verdict"]="unmeasured"` is set, keep it, but make `similarity_review` raise the existing unmeasured WARNING for any charted CIR (not only when `benchmarks_consulted` is non-empty) so the gap is visible in the certificate.
4. **BASE — MEDIUM (pre-existing, not a blocker for these units) — policy IP term match.** `_IP_TERM_RX` requires non-word on both sides, so "Disneyland crochet blanket" and "Taylor Swiftie scarf" return no POLICY_IP_RISK. Fix: allow a trailing word-fragment for the long distinctive terms (e.g. `disney`, `marvel`, `pokemon`), keep whole-word only for short terms like `nba`/`nhl`/`nfl`.
5. **C — LOW — survivor in shared geometry.** The `spans` exclusion in `cir/geometry.py::_increase_and_parentage` is not pinned by any test. Fix: add a test in test_eng_homedecor/test_twin: a row with a chain op carrying `spans>0` must not appear in `consumed_by_increase`; assert the base-corner count is unchanged with the opening present.
6. **A/B/C — LOW — new suites not in `scripts/suite_final_segment.txt`** (test_eng_garment, test_opus2_a1_children, test_opus2_amigurumi, test_eng_colourwork, test_eng_homedecor). A full run globs tests/test_*.py so they still run; only checkpoint segments miss them. Fix: append the six names.
7. **A — LOW — autonomy_map.json** conflicted (generated). After merge run `python -m brambleloop.autonomy.map` and commit rather than hand-merging.

Not done: full unfiltered suite (only the requested subsets); no live/visual inspection of the rendered PDFs.
