# Independent review J-7B: delta review of the J7 fix (2d2d9446 vs 4ae17e1d)

- Reviewed: 2026-11-02 (UTC).
- Subject: `claude/w5-INTEG1` commit 2d2d9446 ("fix review J7 (J7-1..J7-3)"), diffed against 4ae17e1d.
- Closes: review J7 (`INDEPENDENT_SECREVIEW_J7.md` on `claude/w5-SECREVIEW-J7`), findings J7-1 MED, J7-2 LOW and J7-3 LOW.
- Mode: read-only. This report is the only file written. Nothing was deployed, published or spent, and Railway and production were not touched.

## Verdict: SHIP (J-7 satisfied)

J7-1 and J7-2 are fixed.

On every case I tried, a "Cut X after Rnd N … not used again" or "X rests" sentence is now true against the CIR. That covers J7's cases C and D, 13 hand-built variants and 4,500 random joined- and spiral-round CIRs checked by an independent oracle. The ends count always matches the wording.

The same oracle flags 1,008 of 1,500 random CIRs on 4ae17e1d, so it does detect the J7 defect.

Output is unchanged where it should be:
- All 11 Launch-0 `write_pattern` texts are byte-identical between the two commits.
- Over 600 random CIRs, every non-tapestry text, every turned-row text and every `instruction()` result is byte-identical.

No gate is touched and no test line is removed. All 8 requested suites pass.

Two LOW items remain. Neither makes an instruction false, so neither blocks:
- J7's own M8 mutant still survives.
- A yarn used only as a contrast still gets no rest or cut wording.

## Findings

| ID | Severity | Finding |
|---|---|---|
| J7B-1 | LOW (test gap) | J7's mutant **M8** still survives every suite, including `test_pdf_premium`. J7 defined M8 as "tapestry sentence moved before the join lead". The new test pins a different order: the sentence must come *before the ends line* (I call that M8b, and it is killed). Only the order of sentences is unpinned; no instruction becomes false. |
| J7B-2 | LOW (completeness, not truth) | A yarn that is **only ever a contrast** gets no "rests", "pick up" or "Cut … after Rnd N" wording, because `rounds_instruction` still loops over `rows_by_colour` (main colours only). J7 suggested adding this; the fix did not. Nothing printed is false, and the ends count fits carrying the yarn to the end. But the maker is not told what to do with the contrast between its colourwork rounds or after the last one (variants V1, V10 and V11). |
| J7B-3 | INFO | `rows = plan.rows_used.get(colour) or plan.rows_by_colour[colour]`: the fallback can never run, because every main colour is appended to `rows_used` on line 90. Separately, the de-duplication guard `if not used or used[-1] != r.index` can never be false, because `in_row` is a de-duplicated set that excludes the main colour. That makes F5 an equivalent mutant. Both are harmless. |
| J7B-4 | INFO | The `{each}` ("on each <piece>") on the changes > 0 ends line (F7) is killed only by `test_pdf_premium`'s Launch-0 text, not by a tapestry test. The new `make=2` assertion covers only the changes == 0 branch. This is the pre-existing PDF1 line. |
| J7B-5 | INFO | Colours are listed in order of their first *main* round, not their first use. In V8, sage (a contrast in Rnd 3, main in Rnd 5) is described after rust. This is cosmetic. |
| J7B-6 | INFO (pre-existing, PDF1) | Mutant F8, where the writer always passes `upright=False` (so every piece gets "on the wrong side at the join" instead of "up the inside of the join"), survives the fast set and `test_pdf_premium`. It is not introduced by 2d2d9446. Raise it with PDF1. |
| — | open, declared | J7-4 (mixed rounds and rows: no ends line) and J7-5 (spiral rounds told to "make the joining sl st") are unchanged and recorded as follow-ups in the commit. V6 confirms J7-5 still prints for spiral rounds. Neither is a regression. |

## 1. J7-1: the cut decision, re-run and stressed

`j7b.py` (in the reviewer's scratchpad, summarised below) builds 12-stitch rounds pieces: Rnd 1 `sc 6`, Rnd 2 `inc 6`, then `sc 12`, with a tapestry repeat in the stated rounds. Each piece is compiled, analysed and passed to `writer.write_pattern`. Every fixture compiles OK.

| Case | Rounds (main colour / contrast) | Wording on 2d2d9446 | True against the CIR? |
|---|---|---|---|
| **C (J7)** | N 1-2, R 3-5, N contrast Rnd 4 | "Leave natural attached while it rests (Rnd 3) … pick it up again for Rnd 4. Cut natural after Rnd 4 …" Ends 4. | yes. The J7-1 "Cut natural after Rnd 2" is gone. |
| **D (J7)** | N 1-2, R 3 + N contrast, N 4 | "Cut rust after Rnd 3 …". There is no "natural rests". Ends 4. | yes (J7-2 fixed) |
| V1 contrast-only | N 1-2, R 3-5, sage contrast Rnd 4 | "Cut natural after Rnd 2" (true). Nothing is said about sage. Ends 6. | yes. Silent on sage (J7B-2). |
| V2 two contrasts | N 1-2, R 3-5, sage + navy contrasts Rnd 4 | "Cut natural after Rnd 2". Ends 8 (4 yarns). | yes |
| V2b two contrasts, one returning | N 1-2, R 3-5, N + sage contrasts Rnd 4 | natural rests Rnd 3, picked up for Rnd 4, cut after Rnd 4. Ends 6. | yes |
| V3 contrast in last round | N 1-2, R 3-5, N contrast Rnd 5 | natural rests Rnds 3-4, picked up for Rnd 5, not cut. Ends 4. | yes |
| V4 rest → contrast → rest → main | N 1-2, R 3-5, N contrast 4, N 6 | "natural rests (Rnds 3 and 5) … pick it up again for Rnds 4 and 6". Rust is cut after Rnd 5. Ends 4. | yes |
| V4b, extended | … then R 7, R 8 + N contrast | natural rests 3, 5 and 7 and is picked up for 4, 6 and 8. Rust rests 6. Nobody is cut. Ends 4. | yes |
| V5 make = 2 | case C, `make=2` | case C wording plus "about 4 on each body" | yes |
| V6 spiral | case C, spiral | case C wording (still says "joining sl st", which is J7-5) | yes, apart from J7-5 |
| V7 | N 1, R 2-3 + N contrast in 3, N 4-5 | natural rests Rnd 2, picked up for Rnd 3. Rust is cut after Rnd 3. | yes |
| V8 contrast that later becomes main | N 1-2, R 3-4 + sage contrast in 3, sage 5 | sage rests Rnd 4, picked up for Rnd 5. Natural is cut after 2 and rust after 4. Ends 6. | yes |
| V9 | N 1-2, R 3-4 + N contrasts, N 5 | rust is cut after Rnd 4. natural has no rest. | yes |
| V10 contrast-only, twice | N 1-2, R 3-8, sage contrast 4 and 7 | "Cut natural after Rnd 2". Nothing is said about sage between Rnds 4 and 7. | yes. Silent (J7B-2). |
| V11 changes == 0 | N 1-5, rust contrast Rnd 3 | tapestry sentence, "Ends … about 4" | yes. Silent on rust after Rnd 3 (J7B-2, pre-existing). |

**Random oracle.** `oracle.py` generates random joined and spiral rounds pieces:
- 3-10 rounds;
- main colour from 3 yarns;
- 0, 1 or 2 contrasts per round from 4 yarns;
- `make` of 1-3.

It computes each yarn's rounds of use **independently** of `colour_changes` by walking the ops itself. It then parses the writer's colour line and checks:
- every "Cut X after Rnd N" has N equal to the last use of X;
- every "rests (Rnds …)" round is a round where X is not used;
- every "pick it up again for Rnd M" round is a round where X is used;
- there is no "rejoin";
- ends = 2 × the number of yarns used;
- "on each body" appears when `make > 1`.

| Tree | Seed / N | Bad | Cut sentences checked | Rest sentences checked |
|---|---|---|---|---|
| 4ae17e1d (before) | 11 / 1,500 | **1,008** | 2,491 | 2,163 |
| 2d2d9446 | 11 / 1,500 | **0** | 1,983 | 2,498 |
| 2d2d9446 | 12 / 3,000 | **0** | 3,992 | 5,049 |

**Ends.** In rounds, `plan.cut` and `tapestry_cuts` are always 0: the cut path is gated on `plan.turned`. So `ends = 2 × yarns`, one join and one fasten-off per yarn. In rounds the wording only ever says "cut … not used again", which is that yarn's final fasten-off, or "leave attached". It never says "rejoin". Every ends count is therefore consistent with the wording, in every case above and in all 4,500 oracle pieces.

## 2. J7-2: no "rests" in a round where the yarn is worked

Case D now prints no rest sentence for natural. V2b, V4, V4b and V7 put a yarn's contrast round between main rounds; the contrast round is never inside a "rests" span. The oracle found 0 violations across 7,547 rest sentences on 2d2d9446.

## 3. Unchanged output

`diff.py` was run in clean worktrees of both commits.

| Set | Count | Identical |
|---|---|---|
| Launch-0 `write_pattern(cir_for(b), compile_cir(…))`, every `launch0.BUILDERS` key | 11 | **11 / 11 byte-identical** |
| Random CIRs: `instruction()` (turned-row wording), any construction | 600 | 600 / 600 |
| Random `flat_rows` (with or without tapestry): full `write_pattern` | 208 | 208 / 208 |
| Random joined or spiral without tapestry: full `write_pattern` | 243 | 243 / 243 |
| Random joined or spiral with tapestry | 149 | 126 differ, 23 identical. This is the intended change; all differences are inside the colour line. |

`instruction()` and `_row_instruction()` are untouched by the diff. The only new state is `ColourPlan.rows_used`.

The other users of `plan_component` read only `changes` and `carry_is_possible`: `products/builder.py`, `products/nordic_forest.py` and `gates/certificate.py`. No caller serialises a `ColourPlan`, so no digest can move.

## 4. Mutation testing

Mutants were applied one at a time in a scratch worktree of 2d2d9446 and reverted after each run; `git status` was clean afterwards. The fast set is `test_w5_integfix`, `test_opus2_cir_colourwork`, `test_colour`, `test_compiler`, `test_twin` and `test_reverse`. Survivors were also run against `test_pdf_premium`.

| Mutant | Change | Result |
|---|---|---|
| F0 | **revert the fix**: rounds wording reads `rows_by_colour` | **killed** (`test_w5_integfix`) |
| F1 | main colour not added to `rows_used` | killed (`test_w5_integfix`) |
| F2 | contrast not added to `rows_used` | killed (`test_w5_integfix`) |
| F3 | rests read main colours only; cut reads `rows_used` | killed (`test_w5_integfix`) |
| F4 | cut reads main colours only; rests read `rows_used` | killed (`test_w5_integfix`) |
| F5 | drop the de-duplication guard | survives all. **Equivalent** (J7B-3). |
| F6 | contrast recorded only on the yarn's first use | killed (`test_w5_integfix`) |
| F7 | drop "on each" on the changes > 0 ends line | survives the fast set; killed by `test_pdf_premium` (J7B-4) |
| M2 | drop the tapestry sentence when a main colour changes | **killed** (`test_w5_integfix`); it survived on 4ae17e1d |
| M4 | writer `in_rounds = False` | **killed** (`test_w5_integfix`); it was killed only by `test_pdf_premium` on 4ae17e1d |
| M5 | drop "on each" on the tapestry-only line | **killed** (`test_w5_integfix`); it survived on 4ae17e1d |
| M8 | (J7's definition) tapestry sentence moved before the join lead | **survives all, including `test_pdf_premium`** (J7B-1) |
| M8b | (the integrator's reading) tapestry sentence after the ends line | killed (`test_w5_integfix`); passes `test_pdf_premium` |
| F8 | writer passes `upright=False` always (pre-existing PDF1) | survives the fast set and `test_pdf_premium`. This is **pre-existing** and outside this commit: no tapestry or rounds test pins "up the inside of the join" versus "on the wrong side at the join" (J7B-6). |

The commit message says "All five mutations (including reverting the fix) are killed". That is true of F0, M2, M4, M5 and M8b, but not of J7's M8.

Suggested one-line pin for M8 (optional): `assert line.index("falls at the join") < line.index("Colourwork round 4")`.

## 5. Nothing relaxed

`git diff --numstat 4ae17e1d 2d2d9446` touches only two files:
- `cir/colour_changes.py`: +9/−1. The one removed line is `rows = plan.rows_by_colour[colour]`, replaced by the `rows_used` read.
- `tests/test_w5_integfix.py`: +54/−0.

No gate file, compiler, certificate, launch0 or listing code is touched. No test line or assertion is removed or loosened, and no pin value changes.

## Test table: 2d2d9446, run one at a time

Command: `PYTHONPATH=src:tests python tests/<f>`, from `brambleloop/` after `pip install -r requirements.txt`. `run_tests.sh` was not run.

| Suite | Result | Time |
|---|---|---|
| test_w5_integfix.py | 5/5 OK | 3 s |
| test_opus2_cir_colourwork.py | 15/15 OK | <1 s |
| test_colour.py | 7/7 OK | 3 s |
| test_compiler.py | 9/9 OK | <1 s |
| test_twin.py | 8/8 OK | <1 s |
| test_reverse.py | 18/18 OK | <1 s |
| test_pdf_premium.py | 27/27 OK | 169 s |
| test_vacuity.py | 8/8 OK | 12 s |

All 8 exit 0.

## Repro scripts

These are in the reviewer's scratchpad; their logic is summarised here.

- **`j7b.py`**: the case table in §1. It uses `Repeat([sc k, sc k with <contrast>]…)` over a 12-stitch round, with `k=2` for one contrast and `k=1` for two.
- **`oracle.py <seed> <n>`**: the random rounds oracle in §1. Yarn use is computed by walking `Row.ops` and `Repeat.ops` for `Op.color`, plus each row's main colour. Pieces that do not compile are skipped.
- **`diff.py <out.json>`**: the Launch-0 texts plus 600 random CIRs (seed 7; flat, joined and spiral; 60% with contrasts). Run once per worktree and compare.
- **`mut.py`**: the string-replace mutants in §4, each asserted to match exactly once and reverted with `git checkout -- .` after its run.

## To do (non-blocking)

1. Pin J7's M8: the join lead comes before the tapestry sentence (J7B-1).
2. Pin the upright "inside of the join" wording (J7B-6, PDF1).
3. Give a contrast-only yarn its own rest and cut wording, and a tapestry assertion for "on each" when changes > 0 (J7B-2, J7B-4). Do this alongside J7-4 and J7-5.
