# Independent security review: A1 · P0-SAFETY-CHILDREN

- **Reviewed:** 2026-11-02 (UTC). Read-only and adversarial.
- **Subject:** `origin/opus2/p0-amigurumi`, commits 6ab946ff and 98d216b0 (delta `c5671087..98d216b0`).
- **Also checked:** `origin/opus2/p0-construction-registry` at da4f331a, and the split onto `origin/claude/w5-INTEG1` at 7c42e706.
- **Method:** scratch worktrees `a1rev-ami` (98d216b0), `a1rev-reg` (da4f331a) and `a1rev-integ` (7c42e706 with the extracted A1 diff applied), each created with `git worktree add --detach`. Python is `/home/user/bl-runs/venv-integ4/bin/python`. One suite ran at a time.

## Verdicts

| Subject | Verdict | Why |
|---|---|---|
| Children's refusal (A1: `launch0.child_words_in`, `launch0.stuffed_figure`, `pdf._refuse_an_undecided_childrens_title`, `test_opus2_a1_children`) | **DO NOT SHIP** | Every named acceptance title is refused through `handle_cir_draft` and through `assets.build` on a durable DB. That includes "Ｂear", "𝐁ear", "Cosy Ｒabbit", "Juniper Friend" (key `t3-home_decor-toy-0`), an empty title and Cyrillic "Bеar". A plain basket is unaffected. **However, the refusal is not keyed on the construction that the required design names.** `stuffed_figure` = `stuff_before_closing` **and** a seam with `stitches_from_centre`. That second field is an optional placement detail. A stuffed, closed toy whose pieces are placed by `at_round` only, or a stuffed ball with no sewn pieces, renders with no children's block under a neutral title (A1-1, HIGH). There is no confusable or invisible-character fold, so "Bаby Basket" (Cyrillic а) and "Ba​by Basket" render undecided (A1-2, MED). Split onto INTEG1: the source hunks apply and pass, but A1's only test needs the toy and fails there, and every A1 guard mutant survives on INTEG1 (A1-3, MED). |
| Amigurumi toy (OPUS2T-5 small-parts and bear ear) | **DO NOT SHIP until a fixed A1 ships first.** The toy's own delta is acceptable. | Every sewn-on piece (ear and base) is computed against the 31.7 mm cylinder, and offending weights are refused by name. 9/9 small-parts mutants are killed. All toys this route builds are `stuffed_figure`, so the current gate does refuse them. The toy must not land without the children's refusal. Margins are thin on nominal gauge for a pattern that tells the maker to "work tightly" (A1-5, MED). |

OPUS2T-4: closed for every CIR the amigurumi route builds. The design form required by the integrator is not met (A1-1, A1-2).

OPUS2T-5: closed.

OPUS2T-6 / OPUS2V-4: closed in effect. The registry hold code is unchanged: it still reads `child_words_in(req.title, req.key)` and not the CIR's slug and title. Two things now protect this path instead:
- the renderer refuses every amigurumi-built CIR by construction;
- the registry's own title route holds "Juniper Friend", "", "Bеar" and "Woodland Keepsake".

The integrator's literal requirement ("the registry hold reads the CIR's slug and title") is **not implemented** (A1-6, LOW).

OPUS2V-3: closed on da4f331a, which carries 98d216b0 unchanged.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| A1-1 | **HIGH** (child safety, design contract) | **The refusal keys on "stuffed AND span-placed", not on "closed stuffed form".** `launch0.stuffed_figure` returns `stuffed and placed`, where `placed = any(s.stitches_from_centre is not None)`. The integrator required that ANY closed stuffed form be treated as a children's product whatever its title, slug or key: `closed_3d_form`, `stuff_before_closing`, or an amigurumi or shaped-piece build. The following render with **no children's block** and decision `undecided`: (a) the amigurumi toy with its ear seams placed by `at_round` only (`stitches_from_centre=None`), titled "Juniper Friend"; (b) the same toy with no ears (a stuffed ball), titled "Juniper Friend"; (c) a radar `panel_pair` cushion "Juniper Friend" (`bobble-floor-pillow`/`wedding-ring-cushion` seeds, stuffed); (d) the catalogue stuffed pieces `heart-row-ring-pillow` and `spring-garden-kneeler` (stuffed, undecided). (c) and (d) are excluded by the commit's design ("a stuffed cushion or kneeler is not one"). No route today emits (a) or (b) with a neutral title, so the hole is latent. Protection still rests on one optional placement field, not on the construction. In variant (e), the toy with `stuff_before_closing` dropped while fibrefill stays in `materials`, even `risk_matrix.closed_3d_form` cannot see it. *Fix:* key on `stuff_before_closing` (or `closed_3d_form`) or the `creative.fallback_constructions.amigurumi` primitive. Record explicit, reasoned `NOT_MERCHANDISED_TO_A_CHILD` entries for `heart-row-ring-pillow` and `spring-garden-kneeler`, so Launch-0 renders unchanged. Accept that radar cushions are held until decided. Pin (a) and (b) as refused. | `a1rev-probes/p1.py` (variants), `p2.py` (pillow), `survey.py` |
| A1-2 | MED (child safety, second layer) | **`child_words_in` is NFKC-folded only. It has no confusable fold and no invisible-character strip.** The integrator asked for NFKC **and confusable** folding. Through the worker (`handle_cir_draft`, durable sqlite), "Bаby Basket" (Cyrillic а) and "Ba​by Basket" draft as a basket, and `build_pattern_pdf` **renders** with no children's decision. ASCII "Baby Basket" is refused. For toys the gap is covered: the amigurumi route refuses non-ASCII leftovers, and the construction gate catches the result. For every non-stuffed children's product, the word layer is the only layer. *Fix:* strip Cf (format) characters, fold a confusables table (at least Cyrillic and Greek Latin look-alikes), and pin "Bаby" and "Ba​by". | `p1.py` ("Bаby Basket", "Ba​by Basket") |
| A1-3 | MED (process / split) | **A1 cannot be split from the toy as committed, and on INTEG1 it is untested.** The source hunks apply cleanly to 7c42e706 (`launch0.py` at offset +49). `test_childrens`, `test_launch0`, `test_pdf_premium` and `test_opus2_stuffed_finishing` pass. But `test_opus2_a1_children` **fails** on INTEG1 (1 failed), because it needs the amigurumi route to draft "Ｂear". The tests that kill M2, M4 and M5 live in `test_opus2_amigurumi` (toy side). On INTEG1+A1, mutants SM1 (`stuffed_figure` returns False), SM2 (no NFKC) and SM3 (renderer ignores construction) **all survive** every available suite. *Fix:* give A1 a toy-independent test: a hand-built stuffed CIR plus fold cases, through `handle_cir_draft` with a basket seed and through `assets.build`. | `mut_split.out` |
| A1-4 | MED (owner control) | **A stuffed figure is accepted under any non-UNDECIDED state, including the implicit exemption.** The renderer returns when `state != UNDECIDED`. `_decided_not_for_children` gives `NOT_FOR_CHILDREN` automatically to every candidate variant slug whose candidate declares no sub-category. A "Teddy Bear" toy CIR under slug `harvest-table-runner` renders with `figure=True` and no children's block. This is not reachable today, because candidate slugs take the engineered path in `cir.draft`. Still, the decision is keyed on the slug, not on (slug, construction), and nobody wrote that exemption for a toy. There is no runtime auto-approval: decisions are code constants only (`EXTRA_CHILDRENS_ASSIGNMENTS`, `NOT_MERCHANDISED_TO_A_CHILD`, `CANDIDATES`). *Fix:* for a stuffed form, accept only `ASSIGNED` or an explicit `NOT_MERCHANDISED_TO_A_CHILD` entry, never the implicit candidate exemption. | inline probe in the report commands |
| A1-5 | MED (toy, small parts) | **The small-parts geometry uses nominal yarn-weight gauge with zero tolerance, and the pattern says "work tightly".** Drafted margins (mm, flat): bunny DK ear 27.6 × 62.5 passes **only** because 62.5 > 57.1, a 5.4 mm (9%) margin. Bunny worsted ear width is 32.0 against a 31.7 mm cylinder, so it also passes on its length (72.5). Bear DK (ear 31.2) and sport are refused correctly. A tighter-than-gauge make, or a soft ear that bends or folds when placed without compression, could enter the cylinder. This is UNKNOWN, not PASS. It is mitigated: the toy is render-refused until an owner decision, and an ASSIGNED children's product goes through `intel.childrens.assess`. *Fix:* apply a tolerance (for example 15%), or restrict the route to worsted and heavier and drop bunny DK, and require a physical small-parts check before any children's assignment. | weight table in this report |
| A1-6 | LOW | **The registry hold still reads `req.title`/`req.key`.** OPUS2V-4's literal fix was not made. It is now redundant with the construction gate for the toy, and with the registry title route ("Juniper Friend", "", "Bеar" and "Woodland Keepsake" are held; "Ｂear", "Cosy Ｒabbit" and "𝐁ear" with key ≠ slug draft and are PDF-refused). | `a1rev-probes/reg.py` |
| A1-7 | LOW | **Survey and renderer have diverged.** `childrens_titles_without_an_assignment` reports title words only, while the renderer now also blocks on construction. The `child_words_in` docstring promises they cannot diverge. The refusal text reads "the title '' is a stuffed figure" (cosmetic). | code read |
| A1-8 | INFO | **Verified true.** <br>(1) `assets.build` through the real Worker on a durable sqlite store refuses (job FAILED) all 7 toy title/slug cases: 4 by words, 3 ("Juniper Friend"/design slug, "", Cyrillic "Bеar") by construction. The plain basket is DONE (14 pages). The commit's test never runs `assets.build`; this review did. <br>(2) Non-toys are unaffected through the worker: vessel and tapestry basket, tote, drawstring pouch, egg cosy, cushion, triangle shawl and "Pet Bed" all render. The stocking and nursery mobile are refused by route, as before. <br>(3) Launch-0: no catalogue or engineered CIR (20 + 26 surveyed) is a `stuffed_figure`, so no catalogue document gains a refusal. `test_launch0` and `test_pdf_premium` pass on both heads. <br>(4) No removed or weakened assertions in either delta. | `p4.py`, `p5.py`, `survey.py` |

## Split analysis (A1 vs toy, onto claude/w5-INTEG1 7c42e706)

**Children's refusal (A1)**
- `src/brambleloop/products/launch0.py`: hunk `@@ -1390,10 +1390,27 @@` (`child_words_in` NFKC and the new `stuffed_figure`).
- `src/brambleloop/publish/pdf.py`: hunk `@@ -751,13 +751,19 @@` (`_refuse_an_undecided_childrens_title` adds `figure`).
- `tests/test_opus2_a1_children.py`: new file (toy-dependent).
- The A1-relevant test `test_review_opus2t_t4_the_construction_triggers_the_childrens_gate` lives inside the toy file `tests/test_opus2_amigurumi.py`.

**Toy (OPUS2T-5)**
- `src/brambleloop/creative/fallback_constructions.py`, both hunks: `SMALL_PARTS_*`, `ami_separable_pieces`, `ami_small_parts`, bear ear `plain` 2→3, and the refusal in `amigurumi()`.
- `tests/test_opus2_amigurumi.py`: `test_review_opus2t_t5_…` (plus the t4 test above).

**Applying to 7c42e706 (`git apply --check`)**
- `a1_src.diff` (launch0 + pdf): **OK**, launch0 at offset +49.
- `a1_test.diff`: **OK**.
- `toy.diff`: **does not apply**, because INTEG1 has no amigurumi.

**Tests on INTEG1 + A1**

| Suite | Result |
|---|---|
| test_childrens | OK |
| test_launch0 | OK (41 s) |
| test_pdf_premium | OK (124 s) |
| test_opus2_stuffed_finishing | 0 failed |
| **test_opus2_a1_children** | **1 failed** (needs the toy) |

A1's mutants are unguarded there (A1-3).

## Mutations (98d216b0; each applied, run, restored; worktree verified clean)

| ID | Mutant | Result |
|---|---|---|
| M1 | `stuffed_figure` always False | killed (test_opus2_a1_children) |
| M2 | `child_words_in` without NFKC | survives a1_children; killed (test_opus2_amigurumi) |
| M3 | renderer reads words only | killed (a1_children: "" rendered) |
| M4 | `stuffed_figure` = placed only | survives a1_children; killed (amigurumi) |
| M5 | `stuffed_figure` = stuffed only (the integrator's design) | survives a1_children; killed (amigurumi: it asserts catalogue stuffed pieces are NOT figures, so the test pins the narrower design) |
| M6 | `ami_small_parts` returns [] | killed |
| M7 | base piece dropped | killed |
| M8 | depth ignored (narrow only) | killed |
| M9 | depth 25.4 | killed |
| M10 | cylinder 30.0 | killed |
| M11 | bear ear back to 2 plain rounds | killed |
| M12 | body floor 0 cm | killed |
| M13 | ear depth ignores plain rounds | killed |
| M14 | small-parts call removed | killed |
| SM1 | M1 on INTEG1+A1 | **survives** (childrens, stuffed_finishing, launch0) |
| SM2 | M2 on INTEG1+A1 | **survives** |
| SM3 | M3 on INTEG1+A1 | **survives** |

## Suites (each run alone, exit 0 unless noted)

| Head | Results |
|---|---|
| 98d216b0 | test_opus2_a1_children (0 failed, 25 s); test_opus2_amigurumi (0 failed); test_childrens; test_launch0 (42 s); test_vacuity; test_pdf_premium (OK, 136 s, run once on this head) |
| da4f331a | test_opus2_research_to_development (0 failed); test_opus2_a1_children (0 failed) |
| 7c42e706+A1 | test_childrens; test_opus2_stuffed_finishing; test_launch0; test_pdf_premium (124 s); **test_opus2_a1_children exit 1** |

test_opus2_stuffed_finishing is not present on the amigurumi branch.

## Small-parts table (98d216b0, nominal gauge, mm flat: narrow × long)

| Weight | Bear ear | Bunny ear | Base | Drafted |
|---|---|---|---|---|
| sport | 25.3×33.3 | 22.2×50.5 | 31.8 | refused (both) |
| dk | 31.2×41.4 | 27.6×**62.5** | 39.5 | bear refused, **bunny drafted** |
| worsted/aran | 36.2×48.0 | **32.0**×72.5 | 45.8 | drafted |
| bulky+ | ≥47 | ≥42 | ≥60 | drafted |

## Commands

```
S=/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad
PY=/home/user/bl-runs/venv-integ4/bin/python
git worktree add --detach $S/a1rev-ami 98d216b0; …a1rev-reg da4f331a; …a1rev-integ 7c42e706
git diff c5671087..98d216b0 -- …/launch0.py …/pdf.py > a1_src.diff   # + a1_test.diff, toy.diff
(cd a1rev-integ && git apply --check a1_src.diff a1_test.diff toy.diff)
cd <wt>/brambleloop && PYTHONPATH=src:tests:$S/a1rev-probes $PY $S/a1rev-probes/{p1,p2,p3,p4,p5,survey}.py
cd a1rev-reg/brambleloop && PYTHONPATH=src:tests $PY $S/a1rev-probes/reg.py
python3 $S/a1rev-probes/mut.py $S/a1rev-ami $S/a1rev-probes/muts.json
python3 $S/a1rev-probes/mut.py $S/a1rev-integ $S/a1rev-probes/muts_split.json
```

The probes and the mutation logs are kept in `$S/a1rev-probes/`. The worktrees were removed after the review.
