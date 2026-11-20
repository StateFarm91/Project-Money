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
- **`enforce_standard=False`** on `build_pattern_pdf` exists only for tests that build a deliberately defective
  document to inspect one property of it. Two `test_deliverable_qa` tests use it: the outline-removal injection,
  which also drops the section kickers, and the all-grey colours, which leave no renderable hero. Both now also
  assert that the audit fails. `test_no_production_code_turns_the_standard_off` keeps it out of `src/`.
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

Suites run on this branch:

- test_pdf_standard, test_pdf_premium, test_deliverable, test_deliverable_qa
- test_pdf_layout_bounds, test_cert_publish_gates, test_learn_publish_contract, test_publish_execution_gate
- test_search_hero_publish, test_w4_ccgap_pdfium, test_w4_firstsale_deliverables, test_w4_integ4_deliverable_routes
- test_s1_product_truth_3, test_compiler, test_twin, test_reverse
- test_w4_resume_runner, test_v11_autonomy_timeline (map regenerated), test_vacuity
- the licence-surface suites: test_platform_policy, test_shop_package, test_w4_copy, test_w3_store_copy_surfaces,
  test_w3_store_copy_routing

The final results are in the #28 post.

**Risk for the wide run:** any other caller that renders a PDF for a CIR missing what its family needs is now
refused. For example, a synthetic test CIR with no CYC yarn weight would fail. Only the suites listed above were
run here.

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
