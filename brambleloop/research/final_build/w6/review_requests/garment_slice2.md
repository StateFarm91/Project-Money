# ENG-GARMENT slice 2: review request (the garment PDF)

Branch `eng/garment`. NOT merged, NOT deployed. Builds on slice 1 (b4c3eeb).

## What is new
| file | what |
|---|---|
| `src/brambleloop/publish/garment_pdf.py` | `build(release, terminology)` renders one document covering every size. It refuses a release that is not granted, then re-reads its own output (`verify`) and refuses if anything is wrong. |
| `src/brambleloop/publish/garment_schematic.py` | `measures(cir)` reads every dimension of a size from its compiled rows and twin. `primitives()` lays out the pieces to scale at the middle size. Each dimension is lettered, and a legend gives its value for every size, smallest first. The one primitive list is rendered by `to_svg` (the schematic as SVG) and by `draw` (onto the PDF page). |
| `src/brambleloop/publish/garment_writer.py` | The right band is titled "buttonhole band" only when it has buttonholes. |
| `src/brambleloop/products/garment_families.py` | Ball put-ups are keyed by the normalised weight (medium 200 m/100 g, light 230 m/100 g, each inside its published band). An unknown weight is refused. |

## Structure (research/benchmarks/PDF_STRUCTURE_STANDARD.md, structure only)
The document has these sections, in order:
1. Cover.
2. At a glance. Overview table: skill, sizes with the CYC source, fit band, yarn weight with CYC number, hook in mm and US letter, construction, gauge, editions.
3. Supplies:
   - yarn, with m, yd and g per ball;
   - balls per size;
   - hook;
   - notions (buttons with count and mm, markers, needle);
   - **a gauge for each fabric**: the main fabric, and the back-loop band fabric, which the pattern computes at the same gauge.
4. How it is made (construction narrative).
5. Size chart. Columns: body chest, finished chest, ease, length, upper arm, and yarn per size in balls, yards and metres, in cm and in. Followed by a fit note and a ±20% yardage note.
6. Schematic.
7. Tips (7).
8. Abbreviations in US or UK terms, with special stitches.
9. Pattern: smallest size first, the others in parentheses, a stitch count after every row line.
10. Finishing: seams, picked-up bands with their rates as small fractions, buttons.
11. Child safety, where it applies. The `gates.child_safety` statements, with citations and access dates. The "this garment has no buttons, ties or cords" note sits inside the section.
12. Yarn and gauge: substitution by CYC weight and m/100 g, and troubleshooting.
13. Terms, licence and support. **Our own licence** comes from `commerce.terms` via `pdf.licence_paragraphs`; no competitor text is used.
14. About Brambleloop Studio. No persona and no invented designer.

Also included:
- The AI-assistance disclosure.
- A "no sample photograph" note. There is no gallery: no real sample photo exists.

## verify() (runs on every render; any problem refuses the PDF)
- Every section is present.
- The pattern lines are read back per size (`garment_fit.multi_size_problems`) and every row of every size matches the compiler.
- Every pattern line appears in the extracted text.
- The size chart is re-derived from the twin (`garment_fit.claim_problems`), and every size's row is in the text.
- The schematic SVG is non-empty and was drawn on the page.
- For a child or baby garment, the gate's SAFETY_SECTION, CITATIONS, NO_CERTIFICATION_CLAIM and NO_HARD_PARTS_IN_TEXT checks pass on the rendered text.
  - The last of these caught two real defects in my own first draft: a "Seams, bands and buttons" kicker, and a "no buttons" sentence placed outside the safety section.

## Tests (`tests/test_eng_garment.py`, slice 2)
- All 5 designs × US/UK render the full structure, the size chart (every size, balls and yards), every pattern line, and the schematic SVG plus legend.
- Buttons are stated only where they apply. The child-safety section is present and passes on the baby and child documents (UK).
- An ungranted release, here with a tampered yardage claim, is refused.

## Honest status
- There are no photographs: no garment has been made. Tutorial video/QR is not claimed.
- Layout was checked by rendering pages to PNG and reading them. No mobile-reader QA has been done on garment PDFs.
