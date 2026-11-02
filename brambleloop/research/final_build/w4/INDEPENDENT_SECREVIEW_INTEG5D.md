# INDEPENDENT SECREVIEW INTEG5D — delta integration review of claude/w5-INTEG1 f8bf2782..f7466c06

- Reviewer: independent, adversarial, read-only (no deploy, publish, spend, Railway or production access).
- Date (UTC): 2026-11-02
- Range: `f8bf2782..f7466c06` on `claude/w5-INTEG1` (f8bf2782 and earlier covered by INTEG5B/INTEG5C).
  - `a0c6bfff` — merge of `origin/opus2/p0-tapestry` @ `71e26e6f` (tapestry baskets 67b67015 + OPUS2N fixes).
  - `f7466c06` — removes the duplicate top-level `fold_title` in `creative/fallback_constructions.py`.

## Verdict: **SHIP** (for certification)

No finding blocks certification. The merge resolutions are correct unions, the remaining
`fold_title` serves all three routes with no tapestry behaviour lost, tapestry output is
byte-identical to its parent, and all ten requested suites pass (0 failed, 0 UNKNOWN).
Two LOW / INFO items are recorded below; neither is introduced by a merge resolution in this delta.

## Findings

| ID | Severity | Finding | Repro |
|---|---|---|---|
| INTEG5D-1 | LOW (inherited from opus2/p0-tapestry, not a merge-resolution error) | `plan()` now applies `_colour_count_free` to slug and title for **every** category before the several-sizes check. A title such as "Two-Colour Basket" under a non-vessel category (`home`, `blanket`) moved from `refused` (INTEG1 f8bf2782, read as "two baskets") to `flat_panel` (tapestry parent and merge agree). This is the pre-existing gap — "Plain Storage Basket" and "Tapestry Diamond Basket" under `home` were already `flat_panel` at f8bf2782 — reached by one more title shape; the draft-time `name_truth` reading is skipped for `FLAT_PANEL` (`runtime/pipeline.py:897`), so the publish gate is the only backstop. Not verified here whether W-CONCEPT intake or publication refuses a basket-titled flat panel. Recommend: refuse a vessel head noun outside `VESSEL_CATEGORIES` in `plan()`, or document the backstop. | `plan(category="home", title="Two-Colour Basket")["family"]` → f8bf2782 `refused`, 71e26e6f `flat_panel`, f7466c06 `flat_panel`; `plan(category="home", title="Plain Storage Basket")` → `flat_panel` at all three. |
| INTEG5D-2 | INFO (pre-existing, outside the delta) | The duplicate-symbol AST scan over `src/` (module-level, class-body bindings, dict-literal keys, set and frozenset literals) finds no duplicate in any file this delta touches. It does find three pre-existing duplicates elsewhere: (a) `visual/drape.py:257` and `:283` both define the dict key `'support_friction'`, so the later "NOT MODELLED -- the support is frictionless" silently replaces "BOUNDED ASSUMPTION, OFF BY DEFAULT …". That disclosure text is wrong whenever friction is turned on; it last changed in merge `8f8827f` (INTEG8). (b) `intel/pods.py:57` lists `'week'` three times in a frozenset, which does no harm. (c) `brand/storefront.py` rebinds `ABOUT` on purpose (documented W4-COPY). In `tests/`, only helper and lambda names are rebound; no `test_*` function is shadowed. | `python3 dupscan.py src/brambleloop` (script below) |

Checks with no finding:

- **Merge resolution (remerge-diff vs both parents).** Both conflicts are clean unions. `STOCKING`/`TAPESTRY` constants both kept. In `handle_cir_draft`, the STOCKING branch is the INTEG1 branch verbatim (`STOCKING_PRIMITIVES`, `FC.stocking`). The TAPESTRY branch is the tapestry branch verbatim: it keeps the two-distinct-colours refusal and uses `TAPESTRY_PRIMITIVES` and `FC.tapestry_basket`. No primitive or builder is crossed between the two. The elif chain has no repeated family.
- **plan() routing order and disjointness.** `VESSEL_CATEGORIES={"basket"}`, `PET_CATEGORIES={"pet"}`, and stocking is title/`"stocking"`-category driven after both. `tapestry_route` runs only inside the `basket` branch and returns before pet and stocking, so it cannot capture a pet or stocking concept. A differential `plan()` probe (31 titles × 6 categories, at f8bf2782, 71e26e6f and f7466c06) shows every merged result equal to INTEG1's for `pet`/`stocking` routes and equal to the tapestry parent's for `basket`. The only cell that differs from both parents' agreement is INTEG5D-1, and the parents themselves disagree there.
- **f7466c06 fold_title.** The surviving definition (`fallback_constructions.py:32`) is the deleted tapestry copy plus `.replace("’", "'")`. Callers: pet route (195/196), stocking route (236), `tapestry_route` (898), `_tapestry_chart` (951), `tapestry_basket` (979). For tapestry, the U+2019 fold changes no route: "Mom’s Tapestry Basket" is still refused, by the token `s`/`'` instead of the leftover `’`, and only the reason text differs. `tapestry_basket` CIR `to_dict()` and `write_pattern(..., "US")` SHA-256 are identical at 71e26e6f and f7466c06 for four titles (diamond, check, small two-colour, large bicolour checkerboard).
- **cir/colour_changes.py.** The only change is the OPUS2N-3 contrast join/cut sentence in `_tapestry_sentence`, gated `not plan.turned`. `colour_changes.py` is identical between 71e26e6f and f7466c06. `rows_by_colour` and `last_row` are real `ColourPlan` fields, so the `getattr` defaults are never used. Contrast-only colours are excluded from `mains`, so there is no duplicate "Cut" next to the J-7/J7B per-main wording (lines 164-178). Minor wording gap, not reachable by the shipped charts (every chart line has a contrast cell): a contrast skipped in one band round would be listed by round without saying it is carried through the gap.
- **No reliance on the unmerged claim reader.** `d4486b8c`, `5889cc37` and `2f9c413d` (`origin/opus2/p0-cir-colourwork`) are ancestors of neither 71e26e6f nor f7466c06. With INTEG1's J-6 `colourwork_claims`, tapestry titles add a `colourwork` claim ("Two-Colour Basket", "Colour Work Diamond Basket"). `fabric_truth` stays `backed=True`, with `name_truth=[]` and 0 reverse-compare ERRORs, for 8 tapestry titles.

## Commands

All run from `brambleloop/` at f7466c06, one at a time. `requirements.txt` was installed first because the fresh container lacked `sqlalchemy`; before that, the four pipeline-importing suites failed at import, and that run counts as nothing.

| Suite | Result |
|---|---|
| `PYTHONPATH=src:tests python3 tests/test_opus2_tapestry_basket.py` | exit 0, 7 OK, 0 failed |
| `PYTHONPATH=src:tests python3 tests/test_opus2_pet_bed.py` | exit 0, 7 OK, 0 failed |
| `PYTHONPATH=src:tests python3 tests/test_opus2_stocking.py` | exit 0, 7 OK, 0 failed |
| `PYTHONPATH=src:tests python3 tests/test_opus2_draft_constructions.py` | exit 0, 18 OK, 0 failed |
| `PYTHONPATH=src:tests python3 tests/test_opus2_cir_colourwork.py` | exit 0, 17 OK, 0 failed |
| `PYTHONPATH=src:tests python3 tests/test_w5_integfix.py` | exit 0, 5/5 passed |
| `PYTHONPATH=src:tests python3 tests/test_launch0.py` | exit 0, 52 OK, 0 FAIL/ERROR |
| `PYTHONPATH=src:tests python3 tests/test_reverse.py` | exit 0, 18 OK, 0 FAIL/ERROR |
| `PYTHONPATH=src:tests python3 tests/test_twin.py` | exit 0, 8 OK, 0 FAIL/ERROR |
| `PYTHONPATH=src:tests python3 tests/test_vacuity.py` | exit 0, 8 OK, 0 FAIL/ERROR |

The full suite was not run, as instructed.

Review commands:

```
git show --remerge-diff a0c6bfff -- brambleloop/src
git show f7466c06
git diff f8bf2782 f7466c06 -- brambleloop/src
git diff 71e26e6f f7466c06 -- brambleloop/src/brambleloop/products/launch0.py   # INTEG1-side J-6 claim reader
git merge-base --is-ancestor {d4486b8c,5889cc37,2f9c413d} {71e26e6f,f7466c06}   # all: not ancestor
grep -rn fold_title brambleloop/src brambleloop/tests
# worktrees at f8bf2782 / 71e26e6f / f7466c06, then:
#   plan() differential probe (31 titles x 6 categories)
#   tapestry_basket -> compile_cir -> build_twin -> fabric_truth / name_truth / reverse.compare
#   sha256 of cir.to_dict() and writer.write_pattern(cir, result, "US"), parent vs merge
```

Duplicate-symbol scan (`dupscan.py`, run as `python3 dupscan.py src/brambleloop` and `python3 dupscan.py tests`). It reports repeated module-level and class-body bindings (def, class, Assign, AnnAssign), repeated constant keys in any dict literal, and repeated constant elements in set and `frozenset([...])` literals. Delta files: none.
