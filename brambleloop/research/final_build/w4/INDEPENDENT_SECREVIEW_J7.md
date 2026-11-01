# Independent review J-7: W5-INTEG1 merge of P0-CIR-COLOURWORK (0ef729ac, 4ae17e1d)

- Reviewed: 2026-11-01 (UTC).
- Subject: `claude/w5-INTEG1`
  - 0ef729ac merges opus2/p0-cir-colourwork fa02cb49 into 799b3d24.
  - 4ae17e1d re-bases the colourwork test's Launch-0 digest pins.
- Scope: merge condition J-7 from review OPUS2J. The `cir/colour_changes.py` conflict with W4-PDF1's rounds wording is semantic.
- Mode: read-only. This report is the only file written. Nothing was deployed, published or spent.

## Verdict: DO NOT SHIP (J-7 not yet satisfied)

The integrator's fix does what the commit says:
- `rounds_instruction` now prints the tapestry sentence and the ends for joined and spiral rounds.
- It does this both when no main colour changes and when one does.
- The digest claims are true, every gate change is byte-for-byte fa02cb49's own reviewed change, and all 9 suites pass.

But the merged wording can still contradict the CIR. That is exactly the J-7 question.

PDF1's "Cut X after Rnd N and fasten it off; it is not used again" and its "Leave X attached while it rests" are both read from `rows_by_colour`. That field records only each round's **main** colour (`r.color`). It ignores the rounds where the same yarn is worked as a tapestry contrast.

So a CIR that compiles cleanly gets a written pattern that says three conflicting things:
- cut a yarn and fasten it off because it is "not used again";
- then work that same yarn as the contrast in a later round;
- "Do not cut at these changes".

Its "about 4" ends is also wrong for anyone who follows the cut (6). No gate catches this (J7-1).

No Launch-0 product is affected. None uses `Op.color`, and every Launch-0 digest and PDF text is unchanged. The defect is latent, and it is the first thing a tapestry release in rounds would hit.

The fix is small and local (below). After it, one short delta review is enough.

## Findings

| ID | Severity | Finding |
|---|---|---|
| J7-1 | **MEDIUM (blocking for J-7)** | Rounds wording tells the maker to cut a yarn "not used again" that the CIR works as a tapestry contrast in a later round. The ends are undercounted for that instruction. |
| J7-2 | LOW | Rounds wording says a yarn "rests" (carried at the join) in a round where the CIR works it as a tapestry contrast. |
| J7-3 | LOW (test gap) | Mutants M2, M5 and M8 survive every suite run: the changes>0 tapestry branch and the per-piece "on each" are untested for tapestry. M4 (writer routing) is killed only by `test_pdf_premium`'s Launch-0 text check, not by any tapestry test. |
| J7-4 | LOW (pre-existing, not this merge) | In a CIR that mixes rounds and rows, round pieces use `instruction()`. With tapestry only (changes == 0), that prints the tapestry sentence with **no** ends line. This is fa02cb49's behaviour for every changes == 0 tapestry piece. Nothing is dropped. |
| J7-5 | INFO (pre-existing, PDF1) | Spiral rounds get "falls at the join: make the joining sl st…", but spiral work has no join. This is the 799b3d24 PDF1 text and is unchanged by this merge. Raise it with PDF1. |

### J7-1 MEDIUM: "Cut … not used again" for a yarn that is used again as a contrast

Repro: `j7.py` case C. It is a joined-round piece:

| Round | Main colour | Stitches |
|---|---|---|
| 1-2 | natural | plain |
| 3 | rust | plain |
| 4 | rust | `Repeat([sc 2, sc 2 with natural] x3)` |
| 5 | rust | plain |

`compile_cir` is OK with no errors. The plan is `changes 1, tapestry_rows [4], ends 4, rows_by_colour {'natural': [1, 2], 'rust': [3, 4, 5]}`.

The Finishing section of the merged `writer.write_pattern` reads:

> The one colour change falls at the join: make the joining sl st at the end of the round before
> in the new colour. **Cut natural after Rnd 2 and fasten it off; it is not used again.**
> Colourwork round 4: work over the colour not in use so it is carried inside the stitches, and
> change colour on the last yarn-over of the stitch before the new colour. **Do not cut at these
> changes.** Ends to weave in: about 4.

What is wrong:
- natural is used again, in Rnd 4.
- If the maker cuts natural as told, they must rejoin it for Rnd 4: 2 more ends, 6 in total, not "about 4".
- If they carry it instead, the "cut" sentence is wrong.
- "Do not cut" contradicts "Cut natural".

This is the "instruction that contradicts the CIR" that J-7 asked about. Here it is "cut" where the yarn should be carried.

Origin: this is an integration defect.
- On 799b3d24 (PDF1 only), no CIR could use a main colour as a later stitch colour, because `Op.color` did not exist.
- On fa02cb49 (colourwork only), round pieces used `instruction()`, which says "carry … rather than cutting".
- Only the union produces the contradiction.

`certificate.colour_carry_findings` does not look at this. It fires only on a designer note that claims a carry. No other gate reads the finishing text against `rows_by_colour`.

Ends: `plan.ends` itself is right for the carried reading. `colours_seen` is a set, so tapestry colours are not double-counted, and in rounds `tapestry_cuts` stays 0 because it is gated on `plan.turned`. The error is in the cut sentence, not in the arithmetic.

Suggested fix in `colour_changes.py`:
- Build a per-colour "rows used" list that includes tapestry rows. Each `IN_ROW` event already has its (row, colour).
- Use that list for the "Cut X after Rnd N … not used again" test (`rows_used[-1] < plan.last_row`).
- Use it for `_rests` too, so a yarn worked as a contrast in a round does not "rest" there (this also fixes J7-2).
- A contrast whose last use is before the last round should then also get "Cut … after Rnd N". Today it gets nothing, which is harmless but uneven.

Add a regression test with case C. It should assert:
- the pattern does not say "Cut natural after Rnd 2";
- the ends line matches the instruction actually given.

### J7-2 LOW: "rests" while it is being worked

Repro: `j7.py` case D.

| Round | Main colour | Stitches |
|---|---|---|
| 1-2 | natural | plain |
| 3 | rust | natural contrast |
| 4 | natural | plain |

The output is "Leave natural attached while it rests (Rnd 3), carrying it loosely up the inside of the join, and pick it up again for Rnd 4", but Rnd 3 works natural inside the stitches.

The action (keep it attached) is not harmful, so this is LOW. The same fix as J7-1 removes it.

### J7-3 LOW: surviving mutants

See the mutation table. The integrator's test covers only changes == 0 (M1 and M3 killed). What survives:
- M2: drop the tapestry sentence when a main colour also changes. This is the second half of the J-7 condition.
- M4: route every round piece through the turned-row `instruction()`. This is killed only by `test_pdf_premium::test_the_1_2_1_text_fixes_reach_the_documents`, which checks non-tapestry Launch-0 text. The new test's `"Colourwork round 3"` string is printed by both paths, so the writer half of the test cannot tell them apart.
- M5: drop "on each <piece>" in the tapestry-only line.
- M8: misplace the tapestry sentence.

Add assertions for:
- a joined-round piece with a main change plus tapestry (`j7.py` case B), asserting "Colourwork round 3" and the PDF1 "colour change falls at the join" lead;
- `make > 1` asserting "on each".

## Checks requested

### 1. `cir/colour_changes.py`

- **Both sides kept.** `rows_by_colour`, `last_row`, `rounds_instruction`, `_rests`, `_span` and `_COUNT_WORDS` come from PDF1. `tapestry_rows`, `tapestry_cuts`, `first_tapestry_cut_row`, `_tapestry_sentence`, `_row_list`, `_row_instruction` and the `IN_ROW`/`TAPESTRY_CUT` events come from colourwork. `git show --cc` shows nothing else changed.
- **Tapestry sentence and ends in rounds.** These are printed for joined and spiral rounds, with no change (`j7.py` A) and with a change (B). Both read "Colourwork round 3: … Do not cut at these changes. Ends to weave in: about 4." (B adds PDF1's join and cut lines.)
- **Ends.** `2*len(colours_seen) + 2*cut + 2*tapestry_cuts`. A set means no double count. In rounds `tapestry_cuts` is always 0, which is correct: a joined or spiral round ends where it starts, so a contrast is always at the join. The figure is right for a carried contrast and wrong only together with the false "cut" sentence (J7-1).
- **Contradictions.** Yes: J7-1 and J7-2.
- **Turned-row `instruction()`.** Unchanged. `git diff fa02cb49 0ef729ac -- cir/colour_changes.py` touches only the added PDF1 fields and functions and the new rounds lines. `instruction` and `_row_instruction` are byte-identical to fa02cb49.

### 2. `cir/writer.py` (auto-merged)

- `0ef729ac` vs `799b3d24` adds only colourwork's `write_op` "with <colour>" wrapper.
- `0ef729ac` vs `fa02cb49` adds only PDF1's `_is_upright`, `JOINED_LINE` and the routing.
- Routing: `in_rounds` is true only when **every** component is joined or spiral.
  - Then each piece goes through `rounds_instruction`, which now carries the tapestry sentence.
  - Otherwise each piece, rounds included, goes through `instruction()`, which also carries it (with unit "round" from `plan.turned`).
- No path drops the colourwork sentence. Mixed case E printed "body: Colourwork round 3: …". That path has no ends line when changes == 0 (J7-4, pre-existing).
- The whole block is gated on `len(cir.colors) > 1`. A tapestry CIR with one declared colour fails at compile (`UNKNOWN_COLOR`, tested in `test_opus2_cir_colourwork`), so this gate cannot hide one.

### 3. Digest re-base: both claims verified

I took the SHA-256 of `cir_for(b).to_json()` for every `launch0.BUILDERS` entry (11 CIRs) in clean worktrees of each commit (`dig.py`):

| Comparison | Result |
|---|---|
| 799b3d24 vs 0ef729ac | **identical (11/11)** |
| 0ef729ac vs 4ae17e1d | identical |
| 4ae17e1d pins vs 0ef729ac digests | **equal** |
| old pins (0ef729ac test) vs d230e8fd (merge base) | equal |
| fa02cb49 vs d230e8fd | identical, so colourwork moves no digest |

The four that moved between fa02cb49 and 0ef729ac all changed version, and both commits are on PDF1's reviewed line:

| Product | Version change | Commit |
|---|---|---|
| basket_small | 1.2.0 → 1.3.0 | 69516b8f (D-W4-OWNER-BASKET-1.3.0) |
| basket_medium | 1.2.0 → 1.2.1 | 1a8336c9 ("PDF1 (B) … coaster and basket to 1.2.1") |
| basket_large | 1.2.0 → 1.2.1 | 1a8336c9 |
| hexagon_coasters | 1.2.0 → 1.2.1 | 1a8336c9 |

The other 7 are unchanged. The 4ae17e1d diff touches only those 4 pin strings and adds a comment.

### 4. The new test and mutation testing

The mutations were run in a scratch worktree of 4ae17e1d and reverted after each run (`git status` clean). Each mutant was run against `test_w5_integfix`, `test_opus2_cir_colourwork`, `test_colour`, `test_compiler` and `test_twin`. Survivors were also run against `test_pdf_premium`, `test_launch0_listing_truth` and `test_reverse`.

| Mutant | Change | Result |
|---|---|---|
| M1 | `rounds_instruction` returns None when changes == 0 (the requested mutant) | **killed**: `test_w5_integfix` FAIL (the new test), `test_opus2_cir_colourwork` FAIL |
| M2 | drop the tapestry sentence in the changes > 0 branch | **survives all 8** |
| M3 | changes == 0 line without "Ends to weave in" | killed (`test_w5_integfix`) |
| M4 | writer: `in_rounds = False` (round pieces use turned `instruction()`) | killed only by `test_pdf_premium` (`test_the_1_2_1_text_fixes_reach_the_documents`). Survives the new J-7 test and the other 7 suites. |
| M5 | drop "on each <piece>" in the tapestry-only line | **survives all 8** |
| M6 | ends without `2*tapestry_cuts` | killed (`test_opus2_cir_colourwork`) |
| M7 | tapestry colour not added to `colours_seen` | killed (`test_opus2_cir_colourwork`, 3 tests) |
| M8 | tapestry sentence moved before the join lead | survives the fast 5 (wording order only; not run on the slow suites) |

Slow-suite runs: M2 and M5 pass `test_pdf_premium`, `test_launch0_listing_truth` and `test_reverse`. M4 fails 1 test in `test_pdf_premium` and passes the other two. Every mutant was reverted, and the worktree was clean afterwards.

### 5. OPUS2J I-2 repro on the merged tree: still refused

Repro: `i2.py`, on 4ae17e1d. A round piece with a single `sc 1 with rust` in a 12-st Rnd 3, all other rounds plain natural.

| Construction | Title / tags | `fabric_truth.backed` | `colourwork_findings` |
|---|---|---|---|
| joined | "Overlay Mosaic Intarsia Basket" / mosaic, fair isle, intarsia | False | 6 (refused) |
| joined | "Fair Isle Basket" / fair isle | False | 2 |
| joined | "Tapestry Basket" / tapestry | False | 2 |
| joined | "Mosaic Basket" | False | 1 |
| spiral | same four | False ×4 | 6 / 2 / 2 / 1 |

### 6. Nothing else relaxed

For every non-conflicted source file in the merge, the change against the first parent was compared with fa02cb49's own change against the merge base d230e8fd (+/- lines, md5). All are identical: `launch0.py`, `first_customer.py`, `compiler.py`, `model.py`, `reverse.py`, `twin.py`, `moment_candidates.py`, `pipeline_board.py` and `test_opus2_cir_colourwork.py`. So no gate text differs from what OPUS2J reviewed.

Tests from 799b3d24 to 4ae17e1d:
- lines are only added (+372 in `test_opus2_cir_colourwork.py`, +28 in `test_w5_integfix.py`);
- no test line is removed;
- no assertion is loosened.

The only edit to existing colourwork test lines is the 4 pin values verified in §3. `COORDINATION.json` is a metadata union.

## Test table: merged tree 4ae17e1d, run one at a time

Command: `PYTHONPATH=src:tests python tests/<f>`, run from `brambleloop/` after `pip install -r requirements.txt`.

| Suite | Result | Time |
|---|---|---|
| test_w5_integfix.py | 4/4 OK | 3 s |
| test_opus2_cir_colourwork.py | 15/15 OK | 1 s |
| test_colour.py | 7/7 OK | 2 s |
| test_compiler.py | 9/9 OK | <1 s |
| test_twin.py | 8/8 OK | <1 s |
| test_reverse.py | 18/18 OK | <1 s |
| test_pdf_premium.py | 27/27 OK | 156 s |
| test_launch0_listing_truth.py | 14/14 OK | 487 s |
| test_vacuity.py | 8/8 OK | 11 s |

All 9 exit 0. `run_tests.sh` was not run.

A first attempt ran without `sqlalchemy` installed and every DB-importing suite failed at import. Those results were discarded, and everything above was re-run after the install.

## Repro scripts

The scripts are kept in the reviewer's scratchpad and are short enough to inline.

- **`j7.py`** builds the fixtures and prints `analyse()`, `compile_cir` status and the `## Finishing` section of `writer.write_pattern`. The fixtures all use the same 12-st joined-round body as the integrator's fixture (Rnd 1 `sc 6`, Rnd 2 `inc 6`):
  - **A, B:** joined and spiral. Rnd 3 has a rust contrast. Rnd 4 stays natural in A and is main rust in B.
  - **C:** natural 1-2, rust 3-5, natural contrast in Rnd 4.
  - **D:** natural 1-2, rust 3 with natural contrast, natural 4.
  - **E:** joined body with a contrast, plus a flat strap.
- **`i2.py`:** the OPUS2J I-2 fixture, judged by `launch0.fabric_truth` and `first_customer.colourwork_findings`.
- **`dig.py`:** `{b: sha256(L.cir_for(b).to_json())}` over `launch0.BUILDERS`, run in a clean worktree per commit.

## To close J-7

1. Fix J7-1 and J7-2 in `rounds_instruction`: cut and rest decisions read from all uses of a yarn, including tapestry rounds.
2. Add tests for case C, case B, and `make > 1`. These kill M2 and M5, and they give M4 a tapestry-specific kill.
3. Get one short delta review of that change. Everything else in this merge is acceptable as-is.
