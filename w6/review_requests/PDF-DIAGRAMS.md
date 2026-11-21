# ENG-PDF-DIAGRAMS: component diagrams, placed assembly, eye options and a techniques appendix in the premium PDF

- Written 2026-11-21 UTC. Branch `eng/pdf-diagrams`, cut from `origin/claude/batch19-fixers` 8204c93.
- Not merged and not deployed; production is unchanged. No PR was opened, and nothing was pushed to `claude/repository-setup-nc9x6o`.
- Decision: D-ENG-PDF-DIAGRAMS-1 (DECISION_LOG.md). The decision index was regenerated.
- Inputs used:
  - TEARDOWN_HIGHLAND_COW_AMIGURUMI W1/L3/L4 and TEARDOWN_MADELINEMAECO_CAPYBARA M2/L4: progress imagery at every component is the number-one trust driver.
  - PDF_STRUCTURE_STANDARD and its amigurumi addendum.
  - D-OWNER-PDF-STANDARD, D-OWNER-PDF-TEMPLATE and D-OWNER-PDF-LOGO. The logo checks are unchanged.

## What the premium PDF now contains

1. **Per-component diagrams.** Implemented in `pdf_template.component_geometry`, `component_profile` and `component_caption`. Both layouts use them: the template (amigurumi variant) and the engine (amigurumi family, i.e. ENG-PLUSH toys).
   - Every piece is drawn as a silhouette from its stitch counts at gauge, one band per row or round. All pieces share one scale.
   - Each diagram carries round markers (R1, the widest round, the stuffing round and the last round), a dimension line, and the stamp DIAGRAM.
   - The caption states the size at gauge before stuffing: the widest round's diameter and circumference (or the width, for a flat piece), and the fabric length from the first round to the last.
   - Every caption ends "Drawn from the stitch data, not a photograph."
   - Flat pieces are now drawn too.
   - This fills the image slot until a real progress photo from a physical sample exists.
2. **Numbered assembly steps.**
   - Each step is numbered A1, A2, … and carries a placement callout tied to round numbers on the host piece, for example "Placement: rounds 5 to 7 of the head, 6 sts either side of centre." The callout is built from the seam's own `at_round`, `spans_rounds` and `stitches_from_centre`.
   - Each step has a placement diagram with the join rounds outlined and marked.
3. **Eye options with age guidance.**
   - Template: the existing panel gains an "Age guidance:" line. Embroidered eyes are the only option under 3; safety eyes are for 3 and over only, fitted with washers, and only when the certified materials list them.
   - Engine: already prints the child-safety gate's own eye-options statement. That statement is unchanged.
4. **Techniques appendix (`publish/technique_appendix.py`).** Generated from the CIR, never from prose.
   - It covers:
     - every stitch code the rows work;
     - loop targets;
     - how each piece starts and how it is worked;
     - colour changes and stuffing;
     - every seam method;
     - fastening off and weaving in.
   - The text is in our own words. Every stitch name goes through the registry for the edition's terminology. A guard test holds that no template spells out a stitch name that differs between US and UK terms.
   - Template: a last page, "A / APPENDIX", after the owner's eleven sections.
   - Engine: a page before "Terms and support".

## The checker (`publish/pdf_standard.py`): four new rules, none relaxed

| Rule | Families | What it recomputes from the CIR and gauge (not from renderer helpers) |
|---|---|---|
| `component_diagrams` | amigurumi | For each component: a "DIAGRAM of the <piece>," caption containing its diameter and circumference (or width), the fabric length from first to last row/round, and "markers: R<first> … R<last>.". It must end "not a photograph." within its own caption, and must not claim to be a photograph. |
| `assembly_steps` | amigurumi with seams | A1…An in order, each followed (before the next step) by its "Placement: … of the <host>" callout, plus the "diagrams, not photographs" caption. |
| `eye_options` | amigurumi | The panel covers the embroidered option, addresses safety eyes, and has "Age guidance:" and "under 3". If the materials list safety eyes, the under-3 warning is required; if they don't, the panel must state that safety eyes are not this pattern's option. |
| `techniques_appendix` | every family | Every technique `technique_appendix.entries(cir, terms)` requires is present under the appendix heading, with its explanation. |

**UNKNOWN is never PASS.** Each of the following fails its rule (tested):
- no gauge;
- a piece with no counted rows;
- a seam with no `at_round`, or a seam onto a piece the CIR does not have;
- a technique the appendix cannot explain.

When the appendix cannot be generated, the template raises `TemplateBlocked` (section `appendix`) and the engine refuses with a `ValueError`. Neither prints a partial appendix.

**Mutation coverage.** `tests/test_pdf_diagrams.py` `AMI_MUTATIONS` has 16 mutations across the 4 rules, and each fails its rule by id in both US and UK. `test_pdf_standard.test_every_rule_has_a_mutation` now also reads `AMI_MUTATIONS`.

**Existing checks and tests that changed (please check these):**
- **Template audit, `logo_thank_you`.** It now reads the copyright section's last page instead of the document's last page, because the appendix follows the copyright page. The thank-you block still has to embed the logo, so the check is the same strength.
- **`test_pdf_standard` GOLDEN core.** It now includes `techniques_appendix`.
- **`test_pdf_template` 14-page master.** It now expects 13 owner sections plus `appendix`: copyright at index 12, appendix at index 13.

## Tests

Command: `PY=<venv from requirements.lock + requirements-test.lock, Python 3.13> JOBS=4 SUITE_REGISTRY=0 SUITES="…" bash run_tests.sh`
- Tree: 5ab4340, clean.
- Run record: `artifacts/suite_runs/20261121T004915Z-2942.json`.
- Result: **503 passing, 2 failing suites, both pre-existing.** Running the same two suites with the same venv on base 8204c93 gives the identical failures:
  - `test_eng_colourwork::test_categories_and_techniques_without_proof_are_held_by_name`: the "Wave Tapestry Tote" routing reason text.
  - `test_w4_ccgap_pdfium::test_a_render_in_flight_at_interpreter_exit…`: SIGSEGV at interpreter exit. This venv is Python 3.13; earlier reports used 3.11.

| Suite | OK | FAIL |
|---|---|---|
| test_accessibility | 11 | 0 |
| test_childrens | 40 | 0 |
| test_compiler | 9 | 0 |
| test_deliverable_qa | 61 | 0 |
| test_eng_colourwork | 19 | 1 |
| test_eng_families | 16 | 0 |
| test_eng_homedecor | 18 | 0 |
| test_eng_plush | 73 | 0 |
| test_final_standard | 28 | 0 |
| test_launch0 | 52 | 0 |
| test_opus2_amigurumi | 9 | 0 |
| test_pdf_diagrams | 14 | 0 |
| test_pdf_layout_bounds | 3 | 0 |
| test_pdf_premium | 27 | 0 |
| test_pdf_standard | 23 | 0 |
| test_pdf_template | 31 | 0 |
| test_reverse | 18 | 0 |
| test_schematic | 5 | 0 |
| test_texture | 25 | 0 |
| test_twin | 8 | 0 |
| test_vacuity | 8 | 0 |
| test_w3_decision_index | 3 | 0 |
| test_w4_ccgap_pdfium | 2 | 1 |

## Not done / honest limits

- Real progress photos need a physical sample. The diagram is the stand-in, labelled as a diagram.
- The real amigurumi template build still blocks on the child-safety width × height gap (D-ENG-PDF-TEMPLATE-2). Template amigurumi pages are exercised only through the test fixture, with that one fact stubbed.
- The engine's eye-options text is the child-safety gate's. It offers no safety-eye option, by gate design.
- Earlier, under system Python without sqlalchemy/scipy, many suites failed on imports. Those were environmental; the venv run above is the record.
