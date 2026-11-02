# Independent security / truth review OPUS2P: tapestry basket fixes (OPUS2N), amigurumi bear and bunny, drawstring pouch

- Reviewer: independent, adversarial, read-only Claude Code session (branch `claude/w5-SECREVIEW-OPUS2P`).
- Date: 2026-11-02 (UTC).
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
  The only network use was `git fetch`, plus `pip install -r brambleloop/requirements.txt` into the
  reviewer container (needed for `sqlalchemy`).
- This report is the only file written. Every probe and mutation ran in scratch worktrees in the
  session scratchpad. After each mutation the original file was written back, and
  `git status --porcelain` shows 0 lines in both mutation worktrees.

| # | Subject | Branch | Head | Delta reviewed |
|---|---|---|---|---|
| 1 | Tapestry basket: fixes for OPUS2N-1, N-2, N-3, N-4, N-6 | origin/opus2/p0-tapestry | 71e26e6f | 67b67015..71e26e6f |
| 2a | Stuffed piece not damp-finished (a9fac088), plus the shared writer change | origin/opus2/p0-amigurumi | 3b0a8867 | 67b67015..3b0a8867, `cir/writer.py` |
| 2b | Amigurumi bear and bunny (e80a0be0), plus OPUS2N-1 on it (3b0a8867) | same | same | `fallback_constructions.py` amigurumi block, `pipeline.py` |
| 2c | Drawstring pouch (b4ea6795, c7a8d31e), plus OPUS2N-1 on it (3b0a8867) | same | same | `cir/assembly.py` `openings_cm`, pouch block, tests |

Note: `opus2/p0-amigurumi` is stacked on 67b67015, not on 71e26e6f. It does **not** contain the
tapestry fixes in subject 1. Merge 71e26e6f first, or rebase, or the OPUS2N tapestry holes come back
(INFO, OPUS2P-12).

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | Tapestry basket (71e26e6f) | **SHIP** | Each requirement is met and pinned. **N-1:** the allowlist is total. Emoji, other scripts, symbols, numeral forms and zero-width characters before the head noun are all refused. **N-2:** "round" is gone, and "Round Tapestry Basket" is refused. **N-3:** the contrast yarn is told when to join and when to cut. The rounds named (16 and 33 at the medium size) match the CIR's own colour band, and a mutant that shifts them by one is killed. **N-4:** a title naming two charts or two sizes is refused. **N-6:** mutant T8 is now killed. Every new guard is killed by a test except two mutants, and both are equivalent on the shipped product (TP9, TP11). Launch-0 and catalogue digests are byte-identical to 67b67015. The only residual is LOW: the join and cut wording is printed in Finishing, after the rounds (OPUS2P-9). |
| 2a | Stuffed finishing (a9fac088) | **SHIP** | The branch reads the assembly's `stuff_before_closing`, not the title. It also changes the printed finishing of two existing engineered candidates that are not in Launch-0: `heart-row-ring-pillow` loses "damp-finish it standing up … towel" and `spring-garden-kneeler` loses "Block the finished piece: pin it out damp". Both changes make the text truer. Launch-0 digests are unchanged. Residual LOW: the next line still says "Check the ball band before blocking" (OPUS2P-8). |
| 2b | Amigurumi bear and bunny (e80a0be0, 3b0a8867) | **DO NOT SHIP** | **The children's-product gate does not apply to most of the toys this route drafts (OPUS2P-1, HIGH).** The PDF renderer refuses an undecided children's product only when the title or slug contains a word from `CHILD_AUDIENCE_WORDS`. That list has "amigurumi" but not toy, teddy, bear, bunny, rabbit or plush. Four of the seven titles the route's own test pins as drafted ("Teddy Bear", "Cosy Rabbit", "Simple Crochet Bear", "Round‑Ball Bunny Plush") contain no such word. A stuffed toy under one of those titles and a neutral slug renders a full pattern PDF with **no children's safety block**, on nobody's decision. The route's geometry is otherwise sound: 0 compile findings at every yarn weight, a circular body, a base that closes stitch for stitch, ear arithmetic that matches the round's count, a computed circumference, a refused height, risk class C, embroidered features, no safety eyes and no safety claim. But `cir.assembly` never measures the joins. It returns `unmeasurable`, which the certificate grades WARNING, so a wrong base is not caught (OPUS2P-2, MED). Nothing bounds how small the toy can be (OPUS2P-3, MED). |
| 2c | Drawstring pouch (b4ea6795, c7a8d31e, 3b0a8867) | **SHIP** (the pouch on its own; the branch is blocked by 2b) | The eyelets are real. `openings_cm` now sees a ch-2 bridge inside a repeat, once per repetition, and both mutants of that change are killed. The cord is computed: circumference + 2 × 20 cm ties, and dropping either term is killed. The thread join is measured (0.4 cm girth vs 3.2 cm inside) and assembles at every yarn weight. The allowlist is total over the prefix, and the head is anchored. The residuals are LOW wording issues: "starting and ending at the same eyelet" cannot hold with both ends outside when the eyelet count is even (OPUS2P-5); the next-round instruction is vague and the materials line prints the same text twice (OPUS2P-6). |

The amigurumi branch can merge once OPUS2P-1 is fixed and pinned, and OPUS2P-2 and P-3 are either fixed
or explicitly accepted as UNKNOWN that blocks release. Until then the pouch and the stuffed-finishing
change ride a blocked branch. Splitting them out is the owner's or Secondary's call.

## Findings

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2P-1 | **HIGH** (blocking: child safety) | 2b | **A drafted toy reaches the PDF with no children's safety block, because the children's gate depends on title words.** `publish.pdf._refuse_an_undecided_childrens_title` returns early unless `launch0.child_words_in(cir.title, cir.slug)` finds a word from `CHILD_AUDIENCE_WORDS` = (baby, babies, infant, newborn, nursery, toddler, child, children, kids, crib, cot, lovey, amigurumi). The new route drafts toys whose titles contain none of these. Probe results, each built with `F.amigurumi` and then `pdf.build_pattern_pdf(cir)`: **"Teddy Bear"** (slug `cosy-teddy-bear`), **"Bunny Plush"**, **"Simple Crochet Bear"** and **"Cosy Rabbit"** each give 0 compile findings, `childrens_decision` = `undecided`, and the PDF **renders with no "Safety notes for a children's item" heading**. "Ball Bear Amigurumi" (slug `ami-x`) is correctly refused, but only because of the word "amigurumi". The closed-form signal is already in the CIR: `risk_matrix` sets `closed_3d_form` from `stuff_before_closing`, and the route itself knows it is drafting a toy. Neither reaches the children's gate. The certificate's `PHYSICAL_TEST_REQUIRED` (class C) holds release until a full physical make, but a physical make adds no children's statements, so the hole survives it. The commit says the toy "makes no toy-safety claim … that is the children's-products decision". That is true of the pattern text, but the decision is never forced. *Fix (any one):* (a) make `amigurumi()` impossible to render or list unless `childrens_decision(slug)` is not UNDECIDED: refuse in `handle_cir_draft`, or key `_refuse_an_undecided_childrens_title` on `closed_3d_form` / `construction == AMIGURUMI`, not only on title words; (b) add toy, teddy, bear, bunny, rabbit, plush, plushie, stuffie and softie to `CHILD_AUDIENCE_WORDS` (narrower, still word-based). Pin "Teddy Bear" with a neutral slug as refused by the renderer. | `ami_child.py` |
| OPUS2P-2 | **MED** | 2b | **The toy's joins are never measured. UNKNOWN is graded WARNING, and the code comment claims the opposite.** The comment says "so `cir.assembly` measures every join". In fact `assembly.assemble` returns `unmeasurable` ("body: no finished size, so it cannot be placed") at every yarn weight, and `certificate.assembly_findings` turns that into `WARNING ASSEMBLY_UNMEASURABLE`. A mutant CIR with a **30-st base sewn onto the 18-st opening** compiles with 0 findings and is still only `unmeasurable`/WARNING. The ear and base arithmetic is checked only by `test_opus2_amigurumi` against the module constants (A12 and A13 are killed there), never by a gate on the CIR. The brief's "assembles truthfully" is therefore UNKNOWN, not PASS. *Fix:* measure stitch-count joins without a finished size: the base's last round against `at_round`'s count, and the ear's flat width against `stitches_from_centre`. Or make `unmeasurable` an ERROR for a CIR whose seams name `at_round`. Correct the comment. | `asm.py` |
| OPUS2P-3 | **MED** | 2b | **No lower bound on the toy's size, and the size is set by the concept's yarn weight.** The body is a fixed 36 sts, so the size scales with gauge. The circumference is about 10 cm at lace, 14 at fingering, 20 at sport, 25 at DK, 29 at worsted, 38 at bulky, 51 at super bulky and 103 at jumbo (`weights.py`). At lace that is a stuffed ball about 3.2 cm across, with ears smaller still: about the 31.7 mm small-parts cylinder (16 CFR 1501; SOR/2011-17 s.7, cited in `intel/childrens.py`). Whether it fails the cylinder is UNKNOWN, and nothing computes it. Combined with OPUS2P-1, a small toy can reach the PDF with no children's statements. `gauge_for` also prints `hook_mm=5.0` at every weight, so "5.0mm hook" with lace gauge is pre-existing but visible here (INFO). *Fix:* restrict the route to worsted/aran (or DK and up), or refuse when the computed body diameter is under a stated floor (e.g. 6 cm). Pin the refusal. | `weights.py` |
| OPUS2P-4 | LOW | 2b | **Repeated or doubled animal words still draft one toy.** "Bear Bear", "Bunny Bunny Bunny", "Teddy Teddy Bear", "Cosy Cosy Bear" and "Rabbit Bunny" each draft one toy. "Bear Bear" reads as two. Test gaps: **A4** (the last-word head check removed) survives, though under it "Bear Crochet", "Bunny Simple" and "Bear Ball" would draft. **A6** (the two-kinds refusal removed) survives, because no pinned title has two kinds without another refusal ("Bear Bunny" is not pinned). Under A6, `kinds.pop()` drafts one kind arbitrarily. **A3** (the plural-animal regex removed) survives as equivalent: a plural is never a synonym, so it is refused as unknown or as a missing animal. *Fix:* refuse a repeated animal token. Pin "Bear Bunny", "Bear Bear" and "Bear Crochet". | `route.py amigurumi < ami.txt`; mutants A3, A4, A6 |
| OPUS2P-5 | LOW | 2c | **"Starting and ending at the same eyelet" is false whenever the eyelet count is even.** A cord woven in and out through N eyelets crosses the wall N times. Both ends come out on the outside only if N is even, and then they come out of the first and last eyelets, which are adjacent. Ending at the same eyelet means N + 1 crossings, which puts both ends outside only when N is odd. The computed counts are 23 at lace, 17 fingering, 11 sport, 9 DK, **8 worsted/aran, 6 bulky, 4 super bulky, 2 jumbo**. At the default worsted, following the instruction leaves one end inside the pouch. A 2-eyelet pouch at jumbo does not gather as a drawstring at all. The cord length uses the sc gauge for a slip-stitched chain, which is usually shorter per stitch. The length is labelled "about … Computed", so that is acceptable. *Fix:* word the step by parity ("… so both ends come out of two neighbouring eyelets"), or force an even count and say so. Refuse fewer than 6 eyelets. | `weights.py`, `dump.py pouch` |
| OPUS2P-6 | LOW | 2c | **Wording gaps in the pouch text.** (a) The eyelet round's note "work the next round's sts into each ch-2 space" is followed by "sc in next 48 sts". It never says **2 sc in each ch-2 space**. Mutant P12, which removes the note, survives. (b) The materials line prints "worsted acrylic; worsted acrylic": the pouch yarn and the cord yarn, with no colour, so the buyer cannot tell what the second line is for. (c) Finishing says "This pattern uses 2 colours, so there is an end to secure at every join and every change". The cord is a separate piece, and there is no colour change. | `dump.py pouch "Drawstring Pouch" bag` |
| OPUS2P-7 | LOW | 2b | **Small instruction gaps on the toy.** The ears are never told to fasten off leaving a long tail for sewing. The component notes ("Unstuffed: flatten the cup…", "Worked from the top of the head down") are not printed by the writer. Only the seam's "Sew each flattened ear" carries the flattening. Nothing printed is false. | `dump.py amigurumi "Teddy Bear" amigurumi` |
| OPUS2P-8 | LOW | 2a | **"Not blocked" is followed by "before blocking".** On every stuffed piece (the toy, `heart-row-ring-pillow`, `spring-garden-kneeler`), the new "This piece is stuffed and closed, so it is not blocked: do not soak, pin or press it" is followed by the unconditional "Check the ball band before blocking with heat or water." *Fix:* drop or reword that line in the stuffed branch. | `ce.py`; diff base vs ami |
| OPUS2P-9 | LOW | 1 | **The N-3 join and cut instruction is printed in Finishing, after the rounds.** "Join cream at the start of Rnd 16 … cut cream after Rnd 33 and fasten it off" appears on line 49 of the pattern. Rnd 16 itself (line 25) says only "sc in next 2 sts with cream". The wording is true and matches the CIR, but a maker reading top-down meets it after the work. *Fix:* also emit the join on the first contrast round and the cut on the last. | `tapfull.py` |
| OPUS2P-10 | INFO | 1 | **Two tapestry mutants survive, both equivalent on the shipped product.** **TP9** (main colours not excluded from the join/cut list): the main colour never appears as an `IN_ROW` event in the chart band, so the output is identical. **TP11** (the wording also applied to turned rows): no turned-row colourwork product exists. Neither is pinned by a CIR that would tell them apart. | mutations |
| OPUS2P-11 | INFO | 2b, 2c | **Checked and true.** (a) The route refuses every safety or audience word tried in the title: baby, safe, child safe, teether, nursery, lovey, rattle, newborn, toddler, "for babies", toy, keychain. (b) The pattern text has no "safe" or "safety", and the test pins this (A15 and A18 killed). Listing copy such as "baby safe", "child safe" or "safe for babies" is refused by the existing `store_foundation.lint` rule `TRUTH_SAFETY_CERT` (pre-existing). (c) Features are embroidered and no safety eyes are listed. (d) A closed piece compiles closed: fibrefill is a material, `stuff_before_closing` is set, and `risk_matrix` reports `closed_3d_form` → class C → `PHYSICAL_TEST_REQUIRED`. (e) The body is staggered, so "round" is truthful (A11 killed). (f) The circumference is computed and the height refused (A16 killed). (g) The pouch's OPUS2N-1 leftover rule is killed (P1), and so is the amigurumi one (A1). "Ｂear", "Bear‐Amigurumi" and "Ｄrawstring Pouch" fold to ASCII and draft. That is correct, not a bypass. | `route.py`, mutations |
| OPUS2P-12 | INFO | all | **Gates and catalogue.** No gate file changed. `assembly.openings_cm` was broadened, which finds more openings and is stricter. Launch-0 and catalogue digests (23 builders, US+UK text) are identical on 67b67015, 71e26e6f and 3b0a8867, except the two stuffed engineered candidates in 2a: aggregate `d98b035011da8369` on base and 71e26e6f, `2037321551f1a0ca` on 3b0a8867. **Removed or weakened assertions:** in `test_opus2_draft_constructions` one refused title, ("bag", "Drawstring Bag"), becomes an assertion that it drafts as `POUCH`. That is the intended change, and it is still never a tote. No other test line was removed. The amigurumi branch does not contain 71e26e6f. | `dig.py` |
| OPUS2P-13 | INFO (pre-existing, not in delta) | - | (a) `category=basket` drafts "Teddy Bear", "Drawstring Pouch" and "Drawstring Bag" as a plain vessel, and `category=blanket`/`accessory` drafts "Teddy Bear" as a flat panel. This is the same on 67b67015. (b) "Tape​stry Basket" (ZWSP) and "Tapèstry Basket" fall through to the plain vessel and pass `fabric_truth`, `motif_promise` and `name_truth` on both heads. The Unicode fold is on `opus2/p0-cir-colourwork` 5889cc37 and is not merged here (OPUS2O-12). "Diamond Basket" on the plain vessel is caught by `motif_promise`. | `route.py`, `vesselgate.py`, `vg2.py` |

## Mutations

Each mutant was applied, the named suites were run, and the original file was written back.

| ID | Subject | Mutant | Result |
|---|---|---|---|
| TP1 | 1 | N-1 leftover check disabled | killed (test_opus2_tapestry_basket) |
| TP2 | 1 | leftover ignores non-ASCII | killed |
| TP3 | 1 | "round" re-added (N-2) | killed |
| TP4 | 1 | one-chart refusal removed (N-4) | killed |
| TP5 | 1 | one-size refusal removed (N-4) | killed |
| TP6 | 1 | old T8: the plural-noun guard in `_colour_count_free` removed (N-6) | killed |
| TP7 | 1 | join sentence removed (N-3) | killed |
| TP8 | 1 | cut clause removed (N-3) | killed |
| TP9 | 1 | main colours not excluded from the join/cut list | survives (equivalent; P-10) |
| TP10 | 1 | join/cut rounds shifted by one | killed |
| TP11 | 1 | join/cut wording also on turned rows | survives (equivalent, no such product; P-10) |
| A1 | 2b | amigurumi leftover (N-1) disabled | killed (test_opus2_amigurumi) |
| A2 | 2b | `_MULTIPLE_WORDS` refusal removed | killed |
| A3 | 2b | plural-animal regex removed | survives (equivalent; P-4) |
| A4 | 2b | last-word head check removed | **survives** (P-4) |
| A5 | 2b | unknown-word refusal removed | killed |
| A6 | 2b | two-kinds refusal removed | **survives** (P-4) |
| A7 | 2b | teddy-only-bear check removed | killed |
| A8 | 2b | baby, mini, giant, safe allowlisted | killed |
| A9 | 2a | stuffed finishing branch disabled | killed |
| A10 | 2b | risk_class C → A | killed |
| A11 | 2b | body increases stacked (hexagon) | killed |
| A12 | 2b | base disc 12 sts on an 18-st opening | killed by the test only; no gate sees it (P-2) |
| A13 | 2b | ear "back" arithmetic wrong | killed |
| A14 | 2b | `stuff_before_closing=False` | killed |
| A15 | 2b | "12 mm safety eyes" added to materials | killed |
| A16 | 2b | size note computed from 30 sts | killed |
| A17 | 2b | bear ear flat width 5 (raises) | killed |
| A18 | 2b | "Attach safety eyes" in the prose | killed |
| A19 | 2b | ear make=1 | killed |
| P1 | 2c | pouch leftover (N-1) disabled | killed (test_opus2_drawstring_pouch) |
| P2 | 2c | pouch multiplicity refusal removed | killed |
| P3 | 2c | `_POUCH_HEAD` `$` → `\b` | killed |
| P4 | 2c | mini, lined, baby allowlisted | killed |
| P5 | 2c | `openings_cm` repeat flattening reverted | killed |
| P6 | 2c | each repeat counted once, not `times` | killed |
| P7 | 2c | cord omits the circumference | killed |
| P8 | 2c | cord omits the ties | killed |
| P9 | 2c | eyelet round made plain | killed |
| P10 | 2c | the `drawstring` trigger removed (every bag goes to the pouch route) | killed (both suites) |
| P11 | 2c | eyelets 3 rounds lower than the stated rim | killed |
| P12 | 2c | the next-round ch-space note removed | **survives** (P-6) |
| P13 | 2c | eyelet count off by one | killed |

Not mutated, because no guard exists for it: the children's gate for a toy with no child word
(P-1), a toy-size floor (P-3) and eyelet parity (P-5). Each is a live gap, not a mutant.

## Suites run (all exit 0 after `pip install -r requirements.txt`)

| Head | Suites |
|---|---|
| 71e26e6f | test_opus2_tapestry_basket (0 failed); test_opus2_draft_constructions (0 failed); test_opus2_cir_colourwork (0 failed); test_fallback_draft_provenance (OK); test_compiler; test_reverse; test_twin; test_launch0 |
| 3b0a8867 | test_opus2_amigurumi (0 failed); test_opus2_drawstring_pouch (0 failed); test_opus2_draft_constructions (0 failed); test_opus2_tapestry_basket (0 failed); test_opus2_cir_colourwork (0 failed); test_opus2_size_claims (0 failed); test_fallback_draft_provenance (OK); test_compiler; test_reverse; test_twin; test_launch0; test_pattern_truth; test_vacuity |

Before the install, suites that import `sqlalchemy` failed at import. That is an environment
problem, not a code failure.

## Commands

```
git fetch origin opus2/p0-tapestry opus2/p0-amigurumi
git diff 67b67015 71e26e6f; git diff 67b67015 3b0a8867 -- brambleloop/src brambleloop/tests
git worktree add --detach $S/{tap,ami,base,mtap,mami} {71e26e6f,3b0a8867,67b67015,71e26e6f,3b0a8867}   # S = scratchpad
cd $S/<wt>/brambleloop && PYTHONPATH=src:tests python3 tests/<suite>.py           # one at a time
PYTHONPATH=src:tests python3 $S/probes/ami_child.py                  # P-1: build_pattern_pdf on drafted toys
PYTHONPATH=src:tests python3 $S/probes/route.py amigurumi < ami.txt   # 60 toy titles
PYTHONPATH=src:tests python3 $S/probes/route.py bag < pouch.txt       # 41 pouch titles
PYTHONPATH=src:tests python3 $S/probes/route.py basket < tap.txt      # 30 tapestry titles (71e26e6f)
PYTHONPATH=src:tests python3 $S/probes/weights.py                     # 9 yarn weights x {bear, bunny, pouch}: compile, reverse, assemble
PYTHONPATH=src:tests python3 $S/probes/asm.py                         # P-2: unmeasurable -> WARNING; a 30-st base unseen
PYTHONPATH=src:tests python3 $S/probes/dump.py {amigurumi|pouch} <title> <category>
PYTHONPATH=src:tests python3 $S/probes/tapfull.py                     # P-9 placement
PYTHONPATH=src:tests python3 $S/probes/dig.py                         # digests on base / 71e26e6f / 3b0a8867
python3 $S/probes/mut.py $S/mtap mtap.json; python3 $S/probes/mut.py $S/mami mami.json
```
