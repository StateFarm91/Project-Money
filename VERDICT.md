# Review b18-c — 2026-11-20 (independent reviewer)

Base: eng/colourwork b098fcce (Batch 17). Each unit was merged locally onto the base. Suites
ran with `JOBS=4 SUITE_REGISTRY=0 THEN_FULL=0`, using the dependencies from requirements.lock
and requirements-test.lock. All suite runs were in parallel on 4 CPUs.

| Unit | Head | Verdict |
|---|---|---|
| A eng/composer | 71579761 | **BLOCK**: one HIGH finding, a mechanical fix |
| B eng/pdf-template | 5a6f0361 | **BLOCK**: one HIGH finding, a merge-only regression |
| C eng/plush | 5f5fc4c3 | **BLOCK**: one HIGH finding, child safety weakened on merge |

All three are close. Each blocker has a small, exact fix, listed below.

---

## A. eng/composer @ 71579761: BLOCK

**Merge.**
- Two conflicts:
  - `autonomy_map.json`: `generated_at` only, so the base side was kept.
  - `publish/pdf_standard.py` `_LABEL`: both sides add the same "after Rnd N:" lookbehind. The base's `(?<![Aa]fter )` was kept because it is a superset of the composer's `(?<!after )`.

**Suites** (test_eng_composer, test_eng_families, test_pdf_standard, test_vacuity, test_w4_resume_runner, test_compiler, test_twin, test_reverse, test_deliverable_qa):
- TOTAL PASSING: 203; suites failing: 1 (test_vacuity).

**Mutation:** in `validate()`, `if shape not in SHAPES` was changed to `if False`. `test_unexpressible_plans_are_refused_by_the_missing_primitive` failed, so the mutant was **KILLED**. It surfaced as a `KeyError 'hexagon'`, not as a named refusal.

**Probes:**
- Composition is deterministic: two `compose()` calls on the same plan give identical `to_dict()` output.
- A plan that sets `risk_class="A"` on a gathered toy is still forced to class C.
- Composed drafts enqueue `cir.compile`, so they go through the normal compile, twin, reverse and certify chain.
- Subjects are generic shapes. No competitor content was found.

**Findings:**

1. **HIGH: test_vacuity is red, and the unit introduced it.**
   - Possibly-empty assertion loops:
     - `tests/test_eng_composer.py:282` (`cases.items()`);
     - `tests/test_eng_composer.py:303` (`cases.items()`);
     - `tests/test_eng_composer.py:585` (`probes.items()`).
   - Fix: put `assert cases` / `assert probes` (or a `len(...) ==` assertion) before each loop. Then re-run test_vacuity.
2. **MEDIUM: a malformed proposal crashes instead of being refused by name.**
   - `validate()` calls `int(p.get("make"))`, `int(edging["rows"])` and `float(b["from"])`, and calls `p.get` on parts that are not dicts. All of these raise outside `ComposeRefused`.
   - Probes on the owl plan:
     - `make="two"` raises ValueError;
     - block `from="x"` raises ValueError;
     - `parts=["body"]` raises AttributeError.
   - `adjudicate()` catches only `ComposeRefused`, so one bad model proposal aborts the whole adjudication. The proposals after it are never tried.
   - Not reachable today: the pipeline uses `plan_for` templates only.
   - Fix: in `validate()`, type-check every numeric field and require each part to be a dict, appending a named reason when a check fails. Wrap the `validate()` call in `compose()` so that any non-`ComposeRefused` exception becomes `ComposeRefused("plan", ...)`. Add a test with these three probes.
3. **LOW: an unknown shape is not refused by name.** The mutant above shows that `_REQUIRED_DIMS[shape]` is the next line to fail when the guard is gone. That is fine, but the test would be stronger if it asserted that `exc.primitive == "hexagon"`. It may already do so; confirm that the KeyError cannot satisfy it.

---

## B. eng/pdf-template @ 5a6f0361: BLOCK

**Merge.** Conflicts were in BUILD_STATE.md and DECISION_LOG.md (union of both sides) and in `autonomy_map.json` (`generated_at`).

**Suites** (test_pdf_template, test_pdf_standard, test_owner_gallery_complete, plus the common six):
- TOTAL PASSING: 201; suites failing: 1 (test_pdf_template).

**Mutation:** `_Facts.block()` was changed to return `""` instead of raising TemplateBlocked. `test_a_missing_required_fact_blocks_the_build_never_a_placeholder` failed ("built without yarn"), so the mutant was **KILLED**.

**Visual comparison.**
- I rebuilt the proofs myself (`scripts/build_template_proofs.py` into scratch). That produced hexagon-coaster-set US/UK: 20 pages each, audit PASS, all `proof_test_double`.
- I rendered the owner's `spec/07` (14 pages) to PNG and compared it with the proof's contact sheet.
- These match the template, with section numbering and titles identical:
  - the page order 01–11;
  - the header (logo plus BRAMBLELOOP / CROCHET PATTERNS, collection name, terminology);
  - the footer;
  - the forest band;
  - the cream ground;
  - the rose kickers;
  - the serif titles;
  - the two-column pattern;
  - the 7-slot gallery split 4 + 3.
- The canonical logo is on the cover and in every header. The owner banner is on the About page. The thank-you block carries the logo.
- No "MASTER LAYOUT" marker and no bracket placeholders appear.
- The PDF_LAYOUT default is `"engine"`. An unknown layout raises. `proof` and `gallery` are stripped on the engine path. Under the template, no complete certified gallery means GalleryAwaiting. Test doubles are marked NOT CUSTOMER-READY on every page.

**Findings:**

1. **HIGH: two amigurumi tests fail on the merged tree but pass on the branch tip.**
   - The failing tests are `test_a_stuffed_toy_blocks_on_the_child_safety_size_it_cannot_state` and `test_family_amigurumi_needs_the_child_safety_gate_or_it_blocks`.
   - On the merge, the build blocks earlier, in `[notes]`: "child-safety statements cannot be rendered: fibre_and_care: fibres is not recorded for this product".
   - This comes from `intel.childrens.render_statements` (`:821`), which arrived in the base via ENG-PLUSH 2763340. The template's notes section (`pdf_template.py:2090`, `P.childrens_statements`) supplies no fibre for `tests/fixture_amigurumi.py`, whose yarn is named "worsted cotton".
   - It fails closed, so no safety risk, but the amigurumi variant cannot render at all on the integrated tree.
   - Fix: make `childrens_statements` / `StatementFacts` derive the fibre from `Material.name` for this fixture. Alternatively, give the fixture a fibre the base parser reads. Then re-run test_pdf_template on the merge.
2. **LOW: sections split onto near-empty pages.** Proof pages 3 ("Your download includes" alone), 5, 18 and 20 (the thank-you block alone) hold one small panel each. In the template, each of those sections fits on its page, so this costs 20 pages against 14. Fix: let the layout pass keep a short trailing panel with its section when it fits, or shrink the panel's spacing.
3. **INFO: premium-standard "cover" fails on every proof.** This is expected: the proofs use test doubles, which are labelled TEST DOUBLE, not rendering or photograph. With real frames, `RENDER_LABEL` / `PHOTO_LABEL` satisfy the checker. No customer-ready proof exists until a certified gallery does, as the review request already says.

---

## C. eng/plush @ 5f5fc4c3 (plush-fix re-review): BLOCK

**Merge.** Conflicts:
- BUILD_STATE.md, DECISION_LOG.md: union.
- `autonomy_map.json`: `generated_at`.
- `suite_final_segment.txt`: base kept; test_eng_plush is present in both.
- `tests/test_eng_plush.py`: `c` versus `comp` variable naming.
- `gates/child_safety.py`, two hunks:
  1. Both sides were kept: ENG-GARMENT's `garment_months` / `_garment_closures` and plush's `_cord_word`.
  2. In the chain-run loop, the base's "the next row works into it" exemption was kept, called with plush's new `chain_runs(row)` signature.

**Suites** (test_eng_plush, test_opus2_amigurumi, test_opus2_a1_children, test_eng_families, plus the common six):
- TOTAL PASSING: 243; suites failing: 1. The failure was test_w4_resume_runner `p09_a`, which passed when re-run alone (load contention, environmental).
- test_eng_garment was run separately on the merged tree: **2 FAIL**.

**Mutation:** the ATTACHMENTS_KNOWN UNKNOWN return was changed to PASS. `test_an_unknown_attachment_on_a_flat_baby_blanket_holds_it` failed, so the mutant was **KILLED**.

**Prior verdict (plush-2763340b), re-checked:**
- **H1 vacuity:** fixed. test_vacuity passes on the merge.
- **H2 F7 declaration:** fixed. test_eng_plush is in `suite_final_segment.txt`, and test_w4_resume_runner passes.
- **H3 results:** `plush_results.md` now exists with measured run IDs. Its claim is 565/0 suites and 65/65 mutants at f95e603. I did not re-run all 65 mutants; one mutant was killed here. It states honestly that five suites were not run.
- **M1 hard parts:** fixed.
  - All 12 earlier material probes now FAIL FEATURES_EMBROIDERED (craft, doll, toy and crystal eyes, rhinestones, pom-pom nose, press studs, hook and eye, toggle, and others).
  - Most also give MATERIALS_KNOWN UNKNOWN, through an allow-list.
- **M2 cords:** fixed. All 5 note probes and all 3 material probes FAIL NO_CORDS_OR_LOOPS. The chain-run check now tokenises runs across Ops and repeats.
- **M3:** fixed. certify passes `launch0.childrens_assignment(cir.slug)` (`certificate.py:555`).
- **M4:** age-banded eye options and age guidance are now printed. There is a test for each reviewer probe.
- **M5:** a direct test was added ("Juniper Friend"). The survivor is now reported killed.
- **Unknowns hold:** "Sew on the felt heart" gives ATTACHMENTS_KNOWN UNKNOWN, and an unidentified material gives MATERIALS_KNOWN UNKNOWN. A verdict with any UNKNOWN is HELD, never PASS.

**Findings:**

1. **HIGH: child safety is weakened on merge. Graded children's garments leave the child-safety gate.**
   - Plush's `applies()` begins with `if cir.grading is not None and not (stuffed or closes): return False` (`gates/child_safety.py:~426`). That early return comes before the base's ENG-GARMENT rule (`if garment_months(cir) is not None: return True`).
   - Every baby or child garment therefore skips the gate, including GARMENT_CLOSURES (no buttons for under-3s).
   - Evidence on the merged tree:
     - `test_eng_garment::test_every_size_of_every_design_is_granted_and_passes_the_garment_gates` gives `AssertionError(('brookside-kids-sweater','2'))`, because `child_safety` is not in `stages_run`.
     - `test_buttons_and_child_safety_are_stated_where_they_apply` gives `AssertionError('little-wren-baby-cardigan')`, because the safety section is missing.
   - Exact fix, verified in a scratch worktree (test_eng_garment 27/27 OK). Make three changes:
     - **(a)** Delete the plush early-return block in `applies()`. The base's chain-loop exemption already covers the bridged armhole chain it was written for.
     - **(b)** In `_STITCH_LOOP_TERMS` (`child_safety.py:286`), change `\s+loops?` to `[\s-]+loops?`. Without this, the baby cardigan's "back-loop bands" fails NO_CORDS_OR_LOOPS on "loop".
     - **(c)** `tests/test_eng_plush.py:233-240` asserts the removed exclusion (`assert not CS.applies(fake)` for a graded garment). Invert it to assert that a graded baby or child garment IS inside the gate, using a real graded CIR from the test_eng_garment fixtures, not `grading=object()`.
   - With (a) and (b) applied, test_eng_plush is 72 OK and 1 FAIL, and the one failure is exactly that test. Then add test_eng_garment to the plush review list and re-run.
2. **LOW: test_w4_resume_runner `p09_a` failed under 3×JOBS=4 load and passed alone.** This is environmental, not the unit's doing. Note it for whoever runs the integrated suite.

Unit C is otherwise the strongest of the three: the deny-lists are now allow-lists, and UNKNOWN holds the item.
