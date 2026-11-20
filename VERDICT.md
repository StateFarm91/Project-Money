VERDICT: DO NOT SHIP 2763340b3583bb7729e8fc7707b904f14159749c

Unit: origin/eng/plush @ 2763340b (ENG-PLUSH slices 1-3: amigurumi, cushions, baby, under the child-safety content gate).
Base: origin/claude/w6-INTEG3 @ 39b92619. Reviewed 2026-11-20 by an independent reviewer.
Merge: two textual conflicts, both union-resolved by keeping both sides. `DECISION_LOG.md` kept D-OWNER-STANDING-INTERNAL and D-OWNER-CORE-FAMILIES. `scripts/suite_final_segment.txt` kept test_eng_approvals and test_research_flow. `autonomy_map.json` was regenerated and has a one-line mechanical diff.

The blockers are two required suites that are red, and they are red on the branch tip as well, not only on the merge. The safety design is sound: UNKNOWN is never PASS, and physical evidence holds every stuffed or sewn item. Several of its rules are deny-lists with real gaps, though, listed below.

## Suite counts (merged tree, deps from requirements.lock, `JOBS=4 SUITE_REGISTRY=0`)

27 suites ran. 472 tests passed and 2 suites failed, in 995 s.

Every suite requested passed except these two:
test_eng_plush, test_opus2_amigurumi, test_opus2_a1_children, test_eng_families, test_gates, test_opus2_draft_constructions, test_s1_product_truth_3, test_deliverable_qa, test_w5_concept_intake, test_prospecting, test_compiler, test_twin, test_reverse, test_blanket_size_truth, test_a1r_child_safety_core, test_childrens, test_codex_a1_{assignment_content, child_title, listing_child, small_parts_finite, stuffing_evidence}, test_opus2_a9_u6_child_vocab, test_w4_children, test_w4_fmbatch1_childrens_demand, test_v11_autonomy_timeline.

FAILING:
- test_vacuity
- test_w4_resume_runner

Both also fail on the bare branch tip 2763340b.

Mutation run (`scripts/mutate_plush.py`, with real deps): **43 of 44 killed. 1 SURVIVED.** The 44/44 claim does not reproduce.

Note: in an environment without sqlalchemy, every mutant reads as "KILLED" because the suite fails at import. The script cannot tell an import error from a kill.

## HIGH

H1. **test_vacuity is red, and the unit introduced it.**
- New possibly-empty assertion loops: `tests/test_eng_plush.py:142-143` and `:609-610` (`for ... in cir.components / comp.rows`), and `tests/test_opus2_amigurumi.py:250` and `:259` (`sorted(refused)` / `sorted(drafted)`).
- These are the round-count assertions the product-truth claim rests on. An empty iterable would pass them vacuously.
- Fix: add non-emptiness asserts.

H2. **test_w4_resume_runner f7 is red, and the unit introduced it.**
- `tests/test_eng_plush.py` is not declared in `scripts/suite_final_segment.txt`, which the branch modified.
- Fix: add it to that file.

H3. **The documented results do not exist.**
- `research/final_build/w6/review_requests/plush_slice1.md:179,183` and slices 2 and 3 point to `plush_results.md` for "suite list and counts at the pushed commit". That file is not in the tree.
- The suites it would report are red (H1, H2), and the mutation run is 43/44, not all killed.
- Under the honesty rule, the review package claims verification that was not done.

## MEDIUM

M1. **Hard-part deny-list gaps** (`src/brambleloop/gates/child_safety.py:169-174`).
- Probed on the drafted bear, which states embroidered eyes. FEATURES_EMBROIDERED **PASSES** with any of these added as materials:
  - "2 x 9 mm black eyes"
  - "9mm animal eyes with washers"
  - "craft eyes", "doll eyes", "toy eyes", "crystal eyes"
  - "rhinestones"
  - "pom-pom nose"
  - "an eye back"
  - "press studs", "hook and eye", "toggle"
- Literal safety eyes, buttons, beads, bells and pellets are caught.
- Today the PHYSICAL_EVIDENCE UNKNOWN holds every stuffed or sewn toy, so nothing ships. Once evidence authority exists, this check is the only guard.
- Fix: invert the rule. Any eye or nose material or instruction not stated as embroidered with yarn FAILs.

M2. **Cord and loop deny-list gaps** (`child_safety.py:175-176`, `372-388`).
- NO_CORDS_OR_LOOPS **PASSES** with any of these notes:
  - "Tie a bow around the neck."
  - "Add a loop for hanging."
  - "Attach a lace to the pram."
  - "Crochet a leash."
  - "Make a 60 cm chain and tie it on."
- It also passes with materials "a 40 cm length of yarn to tie on", "a pacifier chain" and "leather lacing".
- Only "ties" (plural) and "hanging loop" are matched, despite the docstring's "loop words".
- The chain-run check measures each `Op` alone, so `ch 6, ch 6, ch 6` and `(ch 6) x5` in one round both PASS. That is 18 and 30 chains.
- A flat baby blanket needs no physical evidence, so a corded blanket could reach a PASS verdict.

M3. **certify ignores the catalogue's children's assignment** (`src/brambleloop/gates/certificate.py:544`).
- `_child_safety.evaluate(cir, result)` is called with no `childrens`.
- `applies()` (`child_safety.py:266-281`) consults `childrens_decision_for` only for closed stuffed forms.
- So a FLAT design assigned to a child, with no child word in its title or slug (say an appliqué baby throw), gets no child-safety findings at certify.
- The PDF path does evaluate it, but refuses only on FAIL. A HELD verdict (a sewn appliqué needs physical evidence) renders, and certification would be granted without the physical evidence the gate requires.
- Fix: pass `launch0.childrens_assignment(cir.slug)` into the gate, or treat any assigned slug as in scope.
- This is latent: the only assigned flat slugs today carry "baby".

M4. **Age suitability is stated, not enforced.**
- `child_safety.py` never reads the age band.
- `_physical` (`:436-448`) keys on the subcategory (`lovey` / `amigurumi_toy`), contradicting its docstring (`:26-29`, "anything assigned to a child under 3 needs a physical ... test").
- The `age_suitability` statement (`:121-129`) is printed unconditionally. Its line "every sewn-on piece is larger than the small-parts cylinder" therefore prints even when SMALL_PARTS is UNKNOWN (a HELD document still renders).

M5. **A mutant survives: "gate: a closed piece in rounds is not a toy"** (`child_safety.py:276-277`).
- With that scope rule removed, test_eng_plush still passes, so a closed stuffed piece in rounds is in scope only via other triggers.
- It needs a direct test: a closed, stuffed, single-piece ball with a neutral title and no placed seam.

## LOW

L1. **The mutation harness cannot tell import or environment errors from kills.** It should require the unmutated baseline to pass first.

L2. **Unread quotes.** Citation quotes for canada.ca and cpsc.gov were summariser-extracted, per the review request's own words. The PDF prints them as verbatim with "accessed 2026-11-20". Re-read them word for word before any listing; the gate does not enforce this.

L3. **Closed-form checks can be skipped.** `cir/closed_forms.py` skips all checks for a component with no compiled rows (`if not rows: continue`). Compile normally fails first, but it is a silent pass path.

L4. **Asset colour truth is loosened.** `gates/asset_truth.py` now accepts any colour worked in any piece, not only the hero piece. This is intended, but it means a hero image may depict a colour that appears only on an ear.

## Checks that held

- Every mutant except M5 was killed with real dependencies, covering the joins, closed forms, stuffing, small parts, physical-evidence UNKNOWN, text and citation checks, the certify wiring and the PDF wiring.
- No certification claim is made. The `_CLAIMS` regex exempts the gate's own denial.
- Embroidered eyes alone do not pass: a stuffed or sewn toy is always HELD on PHYSICAL_EVIDENCE.
- Amigurumi and lovey are physical_gate, not verified. Textures, other animals, accessories and multiple toys are held with a `construction_unsupported` reason, and no texture engine is claimed.
- Routing admits only certifying families. No competitor content was found; the Highland cow appliqué is original geometry.
- The A1-R decision gate is not weakened. Cushions stay held until the owner decides.

To ship, fix H1-H3 and M1-M3 at minimum, add a direct test for M5, and re-run.
