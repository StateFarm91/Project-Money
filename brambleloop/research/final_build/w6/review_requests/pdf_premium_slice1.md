# Review request: ENG-PDF-PREMIUM slice 1 (`eng/pdf-premium`)

**Base:** `origin/claude/w6-INTEG3` @ 307c7e62. Nothing is deployed, nothing was spent, and there were no network
calls beyond git and pip (the container lacked `sqlalchemy`; `requirements.lock` was installed).

## The gap

The PDF engine was already rich. Nothing held a document to the premium structure
(`research/benchmarks/PDF_STRUCTURE_STANDARD.md`, structure only), and nothing did so by family. Auditing the rendered
bytes of every catalogue document found these gaps on every product:

- no CYC number or US hook size;
- no "or size to obtain gauge";
- yarn in metres only, with no balls;
- no length per gram for substitution;
- no RS/WS labels;
- a licence with no credit and no disclaimer;
- no brand page.

It also found two buyer-facing defects:

- the pullover cover read **"Makes 4 bodys"**;
- the ring pillow (one object, three pieces) read **"Makes 3 pillows"**.

## What changed

- **`publish/pdf_standard.py`** (new):
  - `family_of(cir)` reads the family from the CIR (graded → garment, else `gates.first_customer` product-type words).
  - `RULES` holds 22 rules, each with the families it applies to and its condition: colourwork, assembly, child item,
    special stitches, dimensions. Running header, folio and release footer are checked per page.
  - `audit()` / `audit_text()` / `refuse_if_incomplete()` run on extracted text, never on the template.
  - The row-count rule parses every `Row/Rnd N:` label in the instructions and requires a printed count that the
    **compiler** certifies for that row index.
- **`publish/pdf.py`**:
  - `build_pattern_pdf` audits its own finished bytes and raises `PremiumStandardRefused`. The audit is in
    `PatternDocument.standard`. Pages are extracted once, and the joined text seeds the `extracted_text` cache.
  - Overview: a SIZES row, CYC number, `5 mm (US H-8)`.
  - Supplies: per-colour yd (m) in the US edition, m in the UK edition, 100 g balls at the shortest CYC length, a
    ball-band note, and the hook "or size to obtain gauge".
  - Substitution: the CYC class plus yd/g (US) or m/g (UK).
  - RS/WS: labels from the CIR's turns, with Row 1 RS by stated convention (`RS_NOTE`).
  - Brand and licence: Disclaimer, "About Brambleloop Studio".
  - Schematic: measurements set as text.
  - Cover: a schematic hero, labelled as a rendering, when no stitch render exists.
  - Pieces: `makes_words` / `per_piece` fix the piece-count wording and the per-piece yarn split on assembled designs.
- **`commerce/terms.py`**: new option `permitted_small_scale_with_credit`, which is now chosen. Its first clause is
  the old sentence verbatim. `store_foundation/claims.py` C-07 is updated to match.
- **`autonomy_map.json`**: regenerated via `python -m brambleloop.autonomy.map --write`. Only the timestamp changed.
- DECISION_LOG **D-ENG-PDF-PREMIUM-1**; BUILD_STATE entry.

## Measured

All 13 documents pass in **US and UK**:

- the 11 Launch-0 and proposed products;
- harbour pullover XS;
- the heart ring pillow.

| Family | Representative | Rules required beyond core |
|---|---|---|
| small home goods | hexagon coasters | colourwork chart |
| blanket | nordic forest baby | colourwork chart, safety |
| basket | market basket small | inline diagrams, colourwork chart |
| garment | harbour pullover XS | size chart, assembly |
| pillow | heart ring pillow | inline diagrams, assembly, colourwork chart |

## Tests

`tests/test_pdf_standard.py` has 24 tests:

- golden structure per family, in both editions;
- amigurumi rule selection;
- US/UK term correctness;
- yd vs m;
- hook US+mm;
- a certified count after every row, across 4 documents and 2 editions;
- RS/WS;
- reproducible bytes, US and UK;
- piece-count wording;
- licence and disclaimer;
- brand page, never Laura;
- **one mutation per rule**, with coverage asserted against `RULE_IDS`;
- the header/footer mutation;
- the special-stitch rule on a bobble context;
- an end-to-end refusal when the renderer drops the licence.

Suite results are in the push comment.

## Not done (honest)

- **Multi-size garment edition** (smallest size first, others in parentheses) is not built. Each graded size still
  ships as its own CIR and PDF, with the full size chart. No rule claims the convention yet.
- **Garment inline diagrams** at the sleeve join and neck are not built, and garments are not required to have them.
- **Amigurumi**: no engine exists, so only the rule set is fixed.
- **Overview claim:** `overview_paragraphs` still says every document "includes construction diagrams, a chart, a
  schematic". That should be derived from what was actually rendered (slice 2).
- **Pullover overview** says "from 4 pieces, 46.4 x 115.2 cm" (the "each" is now dropped). What that dimension
  measures for an assembled garment needs checking in slice 2.
- **Licence:** the credit requirement is a licence change made under the PDF-premium directive. It is still not
  legally reviewed, and every surface says so.
