# INDEPENDENT SECURITY / PRODUCT-TRUTH REVIEW: OPUS2V

- Reviewer: independent, adversarial, read-only (Claude Opus 5.5). Reviewed on 2026-11-02 (UTC).
- Subjects:
  1. `origin/opus2/p0-pouch` at `1ea3079e`, based on `claude/w5-INTEG1` `4af3418f`. This is the pouch and stuffed-finishing split.
  2. `origin/opus2/p0-construction-registry` at `a7b34050`. The commits under review are `ffb74996` and `a7b34050`.
- Prior reports: OPUS2P, OPUS2R and OPUS2T (`brambleloop/research/final_build/w4/`).
- Nothing was modified, pushed, deployed or published. Scratch worktrees were created with `--detach` and removed at the end. Each test suite was run alone, one at a time.

## Verdicts

| # | Subject | Verdict | One line |
|---|---|---|---|
| 1 | Pouch and stuffed-finishing split (`9e0c653a`, `62998a6d`, `934d97d1`, `d232b6bf`, `b2e8b491`, `1ea3079e`) | **SHIP** | Each of the four re-applied commits matches its original line for line, except the amigurumi hunks. No toy route, builder, construction or test is on the branch. P-5, P-6a/b, P-8 and P-9 are correct at every yarn weight and every chart and size, and every new guard is killed by a test. The merge into INTEG1 `30b04b35` is clean. Two LOW residuals remain (P-6c is still open, and the material name on a one-colour pouch). |
| 2 | Construction registry fixes (`ffb74996`, `a7b34050`) | **DO NOT SHIP** | R-1 is met as written: all eight named repros are held, including "Fox Plush". R-2, R-3 (in code), R-4, R-5, R-6 and R-7 are correct. Four problems remain. **(a)** The new `title_route` delegates the vessel and tote families to `plan()`, which is open-world for those families. A research brief titled "Lidded Basket", "Basket with Handles", "Sleepy Fox", "Blanket", "Giant Basket" or "Sunflower Tote" drafts a plain basket or tote with `name_truth == []`, and the PDF renders. That contradicts the commit's own claim that "a brief's title can promise nothing the construction does not make" (OPUS2V-1, HIGH). **(b)** `motif_promise` is still not part of the publish-time `name_truth` (OPUS2V-2, MED). **(c)** The branch still carries the amigurumi toy, and OPUS2T-4 is still open on it: the radar `handle_cir_draft` drafts "Ｂear" and renders its PDF with no children's block (OPUS2V-3, HIGH, carried). **(d)** OPUS2T-6 does not reproduce on the production intake path, where key equals slug. The hold still reads `req.key` rather than the CIR's slug (OPUS2V-4, MED). |

## Findings

| ID | Severity | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2V-1 | **HIGH** (Product Truth) | 2 | **R-1 routes every registry build through `FC.plan`. For the vessel and tote families, `plan()` itself lets an unknown word pass.** `title_route` maps vessel to `plan(category="basket")` and tote to `plan(category="bag")`. Neither route has an allowlist of head nouns or modifiers like the ones the pouch, tapestry and amigurumi routes have. `_plain` holds only the words in `MOTIF_WORDS` and the chart words. Each of the following drafts through `pipeline._draft_creative` with a production design-slug key, compiles, gives `name_truth == []` and `motif_promise.backed == True`, and **the PDF renders**: "Lidded Basket" (no lid), "Basket with Handles" (no handles), "Sleepy Fox", "Blanket", "Cat" (all plain baskets), "Giant Basket" and "XL Basket" (drafted at medium, 19.2 cm), "Sunflower Basket", "Owl Basket", "Fox Basket", "Strawberry Basket", "Rainbow Basket", "Striped Basket", "Teddy Bear Pattern" (basket), and "Sunflower Tote", "Fox Tote", "Rainbow Tote", "Striped Tote" (plain tote). The commit and docstring say the title "can promise nothing the construction does not make", which is false for two of the five families. The radar path already has the same `plan()` gap (OPUS2T-1/-2/-3, OPUS2P-13). The registry gives free-text research titles a new way into it. UNKNOWN passes. *Fix:* give the vessel and tote routes an allowlist like the pouch's `_POUCH_ALLOWED_WORDS` (head ∈ {basket, bin, bowl, caddy, …}, with a closed set of modifiers and size words, and every other word refused). At minimum, apply such an allowlist inside `title_route` for the vessel and tote families. Pin "Lidded Basket", "Basket with Handles", "Sleepy Fox", "Giant Basket" and "Sunflower Tote" as held. | `opus2v-probes/reg4.py` (request_for and build); `opus2v-probes/reg5.py` (end to end, PDF RENDERED) |
| OPUS2V-2 | MED (Product Truth) | 2 | **`motif_promise` was not added to the publish-time `name_truth`.** This was requested under R-1. `eligibility.name_truth` composes `title_promise`, `assembly_promise`, `fabric_truth` and an imagery check. The imagery check runs only when the CIR declares a `products.motifs:` primitive. `motif_promise` is enforced only in `launch0.product_truth` and `manual_adoption`. On the radar path, `plan(basket, …)` drafts "Diamond Basket", "Heart Basket", "Snowflake Basket", "Chevron Basket", "Pumpkin Basket" and "Fir Tree Basket" as a plain vessel. Each has `motif_promise.backed == False` and `name_truth == []`, so `product_publication` raises no NAME_OUTRUNS_PATTERN. The registry path holds these titles in `_plain`, so this is defence in depth for the registry and a live gap for the radar path. *Fix:* call `l0.motif_promise(cir)` inside `name_truth`. Pin "Heart Basket" (plain vessel) as refused at publish. | `opus2v-probes/mp.py` |
| OPUS2V-3 | **HIGH** (child safety; carried OPUS2T-4, still open) | 2 | **The branch still contains the amigurumi toy, and the renderer's children's gate still depends on title words.** `launch0.child_words_in` is not NFKC-folded. `pdf._refuse_an_undecided_childrens_title` is not keyed on the construction (`stuff_before_closing` or `closed_3d_form`). Reproduced on `a7b34050` through `pipeline.handle_cir_draft` with the `pocket-penguin-trio` seed: titles "Ｂear" and "Cosy Ｒabbit" draft, and **`build_pattern_pdf` renders with no children's block**. `F.amigurumi` with a neutral slug does the same. The registry path holds these titles (see OPUS2V-4), so the hole is on the radar path. The branch should not ship while it carries the toy (OPUS2P and OPUS2T: DO NOT SHIP), or until OPUS2T-4 fix (1) lands. | `opus2v-probes/radar.py`; `opus2v-probes/reg3.py` (B) |
| OPUS2V-4 | MED (child safety, structural) | 2 | **OPUS2T-6 is closed on the production path, but only because of an invariant nothing enforces.** In production, `intake.py:730` sets `designed = replace(concept, key=slug)`, and `_payload` sends `slug=designed.key`. So `req.key` equals the job slug, which is the CIR slug, and `req.title` (or the key when the title is empty) equals the CIR title. The hold therefore reads the same strings the renderer reads. With design-slug keys, every probe either was held or had its PDF refused: "Ｂear", "𝐁ear", "Ｔeddy Ｂear", "Cosy Ｒabbit", "Ball Ｂear", "Ｂunny", Cyrillic "Bеar", "Be​ar", an empty title, "Juniper Friend" and "Woodland Keepsake". No toy rendered without the block through the registry. OPUS2T-6's repro, a `t3-…-toy-N` key, is the tournament key, and intake replaces it. But if `concept.key` and the job slug ever differ, the hold reads the wrong strings: with key `t3-home_decor-toy-7` and slug `ear-581a8d84`, the title "Ｂear" is **DRAFTED and the PDF RENDERED** with no children's block. *Fix:* run the hold on the strings the CIR will carry (`slug` passed to `_draft_creative` and `concept.title`), or close the renderer per OPUS2T-4 (1). Also pin a toy test with key ≠ slug. | `opus2v-probes/reg2.py` (production keys: all held or refused); `opus2v-probes/reg3.py` (A: key ≠ slug, PDF RENDERED) |
| OPUS2V-5 | LOW (test gap) | 2 | **The R-3 5% bound is not pinned.** Mutant R7 (`TAPESTRY_WALL_TOLERANCE = 0.25`) survives `test_opus2_review_r`. The test checks the wall against the constant itself, which makes that check tautological, and only requires `fitted and refused`. A 25% tolerance re-admits OPUS2R-3's fir-and-star small (60 → 48, ratio 0.80). The code is correct: across 8 charts × 3 sizes × 8 weights, 112 baskets were built with maximum deviation 4.8%, and 104 were refused. *Fix:* assert a literal (≤ 0.05), or pin fir-and-star small at worsted as refused. | mutant R7 |
| OPUS2V-6 | LOW (test gap) | 2 | Mutants R15 (the `len(said) > 1` two-size hold removed) and R16 (the pouch `_several_sizes` check in `title_route` removed) survive `test_opus2_review_r`. The behaviour is correct: "Small Large Heart Tapestry Basket", "Small Large Ridged Basket" and "Mini Big Basket" are held. It is just not pinned. Mutants R13b and R13c (the toy hold reads only the key) survive `test_opus2_amigurumi` and `test_opus2_research_to_development`, but `test_opus2_review_r` kills R13. | mutants |
| OPUS2V-7 | LOW (Product Truth, radar) | 2 | R-5 made "tulip" and "tulips" the backed words for tulip-trellis, but "tulip" is not in `launch0.MOTIF_WORDS`. "Tulip Basket" drafts as a plain vessel on the radar path with `motif_promise.backed == True` and `name_truth == []`. The registry holds it, because `_plain` also reads `LIBRARY_CHART_WORDS`. *Fix:* add tulip and tulips to `MOTIF_WORDS`. | `opus2v-probes/mp.py` |
| OPUS2V-8 | LOW (carried OPUS2T-9 / P-6c) | 1 | The pouch still prints "This pattern uses 2 colours, so there is an end to secure at every join and every change". The cord is a separate piece, and the pouch has no colour change. The `b2e8b491` message claims only P-6a and P-6b, which is accurate. | `opus2v-probes/pouch_all.py` (medium text dump) |
| OPUS2V-9 | LOW | 1 | On a one-colour pouch the only material line is "<weight> acrylic (<colour>) for the pouch", but the same yarn also makes the cord. Nothing printed is false about quantity, and yardage is not stated, but "each yarn says what it is for" is incomplete. *Fix:* "for the pouch and the cord" when `cord_colour == main`. | `pouch_all.py` (`single` rows) |
| OPUS2V-10 | INFO | 1 | **Checked and true on the pouch branch.** Eyelets (lace → bulky): 24/16/12/10/8/6, always even and ≥ 6. Super bulky (4) and jumbo (2) are refused with a ValueError, which `handle_cir_draft` turns into a refusal (`pipeline.py` `except (ValueError, KeyError)`). Every allowed weight, in one colour and two, compiles with 0 findings, assembles, and gives 0 reverse-read ERRORs. The cord wording "so both ends come out of two neighbouring eyelets on the outside" is true for even N, because the cord crosses the wall N times. The eyelet note "work 2 sc into each ch-2 space" matches the CIR (4 sc + 2 sc = 6 per repeat, the same count all round). The materials are "(forest) for the pouch; (cream) for the cord". P-8: the stuffed branch drops the "Check the ball band before blocking" line, and unstuffed pieces keep it (test over the whole catalogue). P-9: across 4 charts × every size × 8 weights (64 baskets), the join note is on the first contrast round and the cut note on the last. These match the CIR's own colour band and the Finishing text, are printed on those round lines, and compile with 0 reverse ERRORs. | `pouch_all.py`, `tap_p9.py` |
| OPUS2V-11 | INFO | 1 | **Equivalence and absence of the toy.** Comparing the +/- lines of each commit shows that `9e0c653a` = `a9fac088`, `62998a6d` = `b4ea6795` and `934d97d1` = `c7a8d31e` exactly (range-diff shows only context and the cherry-pick trailer). `d232b6bf` = `3b0a8867` minus exactly the amigurumi hunks (the `amigurumi_route` leftover check and the `test_opus2_amigurumi` change). `b2e8b491` = the pouch, writer and tapestry hunks of `c5671087`, with an identical writer hunk. In `git diff 4af3418f..1ea3079e`, the only grep hits for amigurumi, bear, bunny, toy, plush, teddy and stuff are three. First, the `writer.py` comment "OPUS2 (amigurumi)" and "on a toy or a stuffed pillow". Second, the pouch test's fixture seed `_seed_for("woodland-fox-amigurumi")`, a pre-existing radar seed used only for its geometry and colours. Third, the stuffed-finishing test. No `AMIGURUMI` constant, route, builder, pipeline branch or toy test is present. Files touched: COORDINATION.json (a claim), `assembly.py`, `writer.py`, `fallback_constructions.py`, `pipeline.py`, and 4 tests. Nothing unexpected. **Removed or weakened assertions:** only ("bag", "Drawstring Bag") moves from refused to `POUCH`, as reviewed in OPUS2P-12. | `git range-diff`; `diff` of +/- lines |
| OPUS2V-12 | INFO | 2 | **Checked and true on the registry branch.** All 8 R-1 repros are held as 'title' through `_draft_creative`, including "Fox Plush", which is not pinned in the test but holds. R-2: brief small vs title "Large" → held 'size'. A size on amigurumi, pouch or tote → held (ENGINE). The title size is adopted for vessel and tapestry. R-3: the wall stays within 5% (see V-5), and a chart taller than the wall is refused. R-4: a non-mapping brief is held, and a malformed `benchmarks_consulted` gives `cir.draft_refused`, not a crash. R-5: `split(":")[1]`, with no effect on `products.motifs.grid:` primitives. R-6: the grid sha12 is recorded on both paths. R-7: deduplicated. The test changes in `test_opus2_research_to_development` tighten assertions; they do not weaken them (the soft pouch is now held 'title'; the fixtures get valid titles). | `reg.py`, `reg2.py`, tests |

## Mutations

Each mutant was applied in the scratch worktree, the named suite was run, and the file was restored with `git checkout`.

Subject 1 (pouch, `1ea3079e`):

| Mutant | Change | Result |
|---|---|---|
| V1 | ball-band line printed for stuffed pieces too | killed (`test_opus2_stuffed_finishing`) |
| V2 | eyelet step = lcm(6, unit) (odd counts possible) | killed (`test_opus2_drawstring_pouch`) |
| V3 | `< POUCH_MIN_EYELETS` refusal removed | killed |
| V4 | eyelet note loses "2 sc into each ch-2 space" | killed |
| V5 | cord note back to "starting and ending at the same eyelet" | killed |
| V6 | P-9 cut note removed | killed (`test_opus2_tapestry_basket`) |
| V7 | P-9 join note placed one round late | killed |
| V8 | cord material loses "for the cord" | killed |
| V9 | `stuffed = False` | killed (`test_opus2_stuffed_finishing`) |
| V10 | `POUCH_MIN_EYELETS = 2` | killed |

Subject 2 (registry, `a7b34050`):

| Mutant | Change | Result |
|---|---|---|
| R1 | `_title_agrees` returns before any check | killed (`test_opus2_review_r`) |
| R2 | amigurumi kind-vs-title check off | killed |
| R3 | tapestry chart-vs-title check off | killed |
| R4 | brief/title size conflict hold off | killed |
| R5 | title size not adopted | killed |
| R6 | size-on-unsized-family hold off | killed |
| R7 | `TAPESTRY_WALL_TOLERANCE = 0.25` | **survives** (V-5) |
| R8 | chart-taller-than-wall check off | killed |
| R9 | malformed-brief hold off | killed |
| R11 | knowledge-gap dedupe reverted | killed |
| R12 | `split(":", 1)[1]` (ffb74996 reverted) | killed |
| R13 | toy hold reads key only | killed (`test_opus2_review_r`); survives `test_opus2_amigurumi` (R13b) and `test_opus2_research_to_development` (R13c) |
| R15 | two-size title hold off | **survives** (V-6) |
| R16 | pouch `_several_sizes` in `title_route` off | **survives** (V-6) |

## Merge-tree

- `git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/p0-pouch` gives `0dc43fefde969540171538626190b7dbc450b01d`, exit 0, so the merge is **clean**. The only commit between `4af3418f` and INTEG1 `30b04b35` touches `swarm/orchestrate.py`.
- `git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/p0-construction-registry` gives `037284e75dbb9e709f4cb653eaca422562c4358f`, exit 0, so it is also textually clean. That merge would bring in the amigurumi toy (OPUS2V-3).

## Tests run (one at a time; venv-integ4)

- Pouch `1ea3079e`: `test_opus2_drawstring_pouch`, `test_opus2_stuffed_finishing`, `test_opus2_tapestry_basket`, `test_opus2_draft_constructions`, `test_launch0` and `test_vacuity` all exited 0.
- Registry `a7b34050`: `test_opus2_review_r`, `test_opus2_research_to_development`, `test_opus2_tapestry_basket`, `test_opus2_draft_constructions`, `test_opus2_amigurumi`, `test_opus2_drawstring_pouch`, `test_launch0`, `test_eligibility`, `test_vacuity` and `test_pdf_premium` (run once) all exited 0.

## Commands

```
git -C /home/user/Project-Money fetch origin
S=/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad
git worktree add --detach $S/opus2v-pouch origin/opus2/p0-pouch
git worktree add --detach $S/opus2v-reg   origin/opus2/p0-construction-registry
git range-diff a9fac088^! 9e0c653a^!   # likewise b4ea6795/62998a6d, c7a8d31e/934d97d1
for p in "a9fac088 9e0c653a" "b4ea6795 62998a6d" "c7a8d31e 934d97d1" "3b0a8867 d232b6bf"; do set -- $p; diff <(git show $1 --format= | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)') <(git show $2 --format= | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)'); done
git diff 4af3418f origin/opus2/p0-pouch | grep -E '^\+' | grep -inE 'amigurumi|\bbear|bunny|\btoy|plush|teddy|stuff'
git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/p0-pouch
git merge-tree --write-tree origin/claude/w5-INTEG1 origin/opus2/p0-construction-registry
cd <worktree>/brambleloop && PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py
/home/user/bl-runs/venv-integ4/bin/python $S/opus2v-probes/{pouch_all,tap_p9}.py            # pouch worktree
/home/user/bl-runs/venv-integ4/bin/python $S/opus2v-probes/{reg,reg2,reg3,reg4,reg5,radar,mp,tap_r3}.py   # registry worktree
$S/opus2v-probes/mut.sh NAME FILE OLD NEW SUITE                                              # mutations
git worktree remove --force $S/opus2v-pouch; git worktree remove --force $S/opus2v-reg
```

Probes are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/opus2v-probes/`.
