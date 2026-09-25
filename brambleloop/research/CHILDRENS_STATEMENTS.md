# The children's statement set, from an obligation to a deliverable

**Department:** Children's Safety Deliverable
**Date:** 2026-09-25 (UTC)
**Phase:** `BRAMBLELOOP_PHASE=shadow`. Nothing published, nothing deployed, CA$0.00 spent.
**Reading behind this:** `research/CHILDRENS_CATEGORY.md` (2026-09-24) §2.10 and §6,
`src/brambleloop/intel/childrens.py`, `src/brambleloop/products/launch0.py`,
`src/brambleloop/publish/pdf.py`, `src/brambleloop/cir/writer.py`.

Evidence labels, as elsewhere in this repository: **SOURCED** — read from the document that
governs it, on a recorded date, with the sentence kept. **INFERRED** — this company reasoned,
and the reasoning can be argued with. **UNKNOWN** — not established, and not filled in with a
plausible answer.

---

## 1. What was measured before any of this was built

`intel.childrens.required_statements(subcategory, audience)` computed the statement set for a
children's pattern, and nothing consumed it. `launch0.statement_rendering_gap()` measured the
consequence by searching `publish/*.py`, `cir/*.py` and `commerce/*.py` for any statement's
distinctive words and finding **zero files**. `intel.childrens.assess()` reported both
Launch-0 children's products — `cloudline-baby-blanket` (`baby_blanket`, `under_3`) and
`nursery-nesting-baskets` (`nursery_decor`, `under_3`) — as *subject allowed, not ready to
ship*, with every one of their five required statements missing.

That is not a documentation gap. `STATEMENTS` held **descriptions of what must be said** —
"the age band the finished item is suitable for, stated as a band" — and no table anywhere
held the sentence. So the obligation was computable and the text did not exist, and the
deliverable had nothing to print even if it had wanted to.

**SOURCED** (this repository, re-run 2026-09-25 before any edit): five required statements
per children's product, zero rendered, zero files mentioning one.

---

## 2. The statements now exist, keyed by the obligation

`intel/childrens.py` gained `STATEMENT_SET`: one table holding, per key, the obligation, the
heading, the customer-facing text, a marker phrase, the source it cites, and the derived facts
it needs. `STATEMENTS` — the obligation-only view every earlier caller reads — is now
**derived** from it:

```python
STATEMENTS: dict[str, str] = {k: s.obligation for k, s in STATEMENT_SET.items()}
```

The alternative was a second dict of texts beside the dict of duties. That is the drift this
repository keeps meeting: two copies of one fact, one of them edited, both still looking
complete. `test_the_obligation_and_its_text_cannot_drift_apart` fails if anybody reintroduces
the second copy.

### What is derived rather than typed per product

`StatementFacts` carries the audience band, the finished dimensions, the declared colours, the
fibre and the compile date. Every one of them is already established elsewhere about the same
product — the size is on the cover, the colours are in the colour key, the fibre is on the
materials page, the band is on the candidate's children's assignment — so the safety block
cannot become a stale second copy of the pattern's own arithmetic. Two products produce two
different blocks from one table:

| | `cloudline-baby-blanket` | `market-basket-small` |
|---|---|---|
| age band | under 3 years | under 3 years |
| finished size in the block | 79 x 97 cm | 15 x 9 cm |
| fibre in the block | acrylic | cotton |
| colours | cream, ink | cream, wine |

**SOURCED** (the rendered PDFs, read back with `pypdf`, 2026-09-25).

### Citations

Seven of the ten statements cite a source from the `SOURCES` table already in that module.
Three do not, and the three are enumerated by `unsourced_statements()` rather than caveated:
`supervision`, `fibre_and_care` and `not_legal_advice` are this company's own conservative
practice. `research/CHILDRENS_CATEGORY.md` §2.10 lists all ten together and cites a source for
seven; attaching somebody else's regulation to the other three would borrow authority the
sentence has not got. **The document says so on the page**: a statement with no source prints
"Source: none. This is Brambleloop Studio's own practice rather than a published rule." A
reader who sees citations under seven notes and silence under the eighth would otherwise read
the silence as a citation that fell off.

---

## 3. The document renders them, for children's products only

`publish/pdf.py` sets a "Safety notes for a children's item" section on its own page, before
the terms page, in **both terminologies** (US and UK), and only when
`launch0.childrens_assignment(cir.slug)` returns an audience.

The switch is the assignment, not the fabric, and it is off by default. `cir.model.CIR`
records nothing about who the finished object is for, and it should not: the same fabric is a
lap blanket or a baby blanket depending on how it is sold, which is a merchandising decision.
So the renderer asks the catalogue. `harvest-table-runner` and `hexagon-coaster-set` carry no
safety block, and a test asserts that no statement's marker appears in the runner's PDF —
because ten safety paragraphs on an object that needs none is how a real warning stops being
read.

**SOURCED**: 8 documents (3 basket variants + 1 blanket, x2 terminologies) each carry all five
required statements, measured by extracting text from the PDF bytes.

---

## 4. The gate, and why it refuses rather than reports

`build_pattern_pdf` renders the document, extracts the text from the finished bytes, looks for
each required statement's marker, and **raises** if one is missing.

Refusal rather than a `problems` entry, and the difference is load-bearing. `problems` is for a
defect in a document that is still the right document — a chart cell under the brand minimum, a
cable whose crossing direction the CIR cannot state. `runtime/release.py` audits problems
without blocking on them (`ctx.audit("assets.deliverable_problems", ...)`), so a finding here
would have been recorded and shipped. `publish/pdf.py` already had the pattern for the other
case: it refuses a CIR that does not compile, and refuses a terminology whose stitches it
cannot name truthfully. A children's pattern missing a safety statement is that case.

**Measured on the artefact, not the template.** The check extracts text from the real PDF with
`pypdf`, not from `_Doc.prose` (what the module *chose* to say) and not from the statement
table (what it *intended* to say). `publish/pdf.licence_paragraphs` documents what happens
otherwise: requirement 40's consistency check compared the decision with itself and reported
three surfaces consistent while the customer's own document granted a different licence. A
check that cannot see the artefact it exists to measure is not a check.

**Proved against an injected defect** (`test_a_childrens_document_missing_a_statement_is_
refused_rather_than_shipped`): rename the blanket's yarn to one that names no fibre, and
`build_pattern_pdf` raises with `fibre_and_care` named. Clear the children's assignment on the
same defective CIR and it renders fine — the gate is about the audience, not the yarn name.

---

## 5. The honest blocker: fibre

The brief was explicit that `fibre_and_care` requires fibre content, that the CIR does not
record fibre, and that neither inventing one nor letting an unstated fibre satisfy the gate
was acceptable. Both halves of that are true and they are about **different things**, so the
diagnosis is worth writing out.

**SOURCED — the schema records no fibre.** `cir.model.Material` has `name`, `yarn_weight`,
`colorway`, `metres_estimate`, `color_id`. There is no fibre field and no composition field.
`cir.writer.finishing_lines` cites the ball band for exactly this reason: "Nothing here claims
anything about a fibre this schema does not record." That statement is still true of the
schema, and this work did not change it.

**SOURCED — the fibre fact is nevertheless present, customer-facing, and already read from
this field by production code.** Every Launch-0 material is named `"worsted acrylic"`,
`"worsted cotton"` or `"dk cotton"`. The materials page of this very PDF already prints that
name to the buyer (`doc.kv(m.color_id or m.name, described)`). And `publish/substitution.py`
already reads a fibre class out of `Material.name` against `FIBRE_CLASSES` to write the yarn
substitution guidance the customer reads two pages earlier. So reading the fibre from
`Material.name` is not a new liberty; it is the reading this package already makes, reused,
against the same vocabulary so there is one definition of what a fibre word is.

**INFERRED — a yarn name is not a fibre content, and the statement says only what is
recorded.** "worsted acrylic" is a yarn description. It is not "100% acrylic", and this module
must not upgrade one into the other. The rendered statement therefore names *the fibre this
pattern was written for* and leaves the composition of the finished object to the ball band of
the yarn the maker actually bought — which is also the honest answer, because the buyer of a
*pattern* chooses their own yarn and it is their yarn that decides what the finished object is
made of. The sentence says this in as many words: "We state the fibre this pattern was written
for; we do not state a fibre content for your finished item, because the yarn in your hands is
what decides that."

**The gate still fails closed.** `fibres_named()` returns nothing when any material's name
carries no recognised fibre word, `fibre_and_care` is then reported **unrenderable with the
reason**, and the product cannot be rendered at all. An unstated fibre is not treated as
satisfied. The injected-defect test is exactly this case.

### What would remove the inference — for the Visual/CIR owner

`cir/**` is not this department's to change. The precise request:

> Add `fibre_content: tuple[tuple[str, int], ...] = ()` to `cir.model.Material` — a sequence of
> `(fibre, percent)` pairs, validated in `__post_init__` to sum to 100 when non-empty and to
> draw its fibre names from a closed vocabulary. Leave the default empty, so a CIR that does
> not state it is refused by the children's gate rather than assumed.

With that field present, `publish.pdf.fibres_named` reads it in preference to the yarn name,
the statement can state an actual fibre content, and the free-text inference is dead code that
a test can delete. **Until then**: `UNKNOWN` — the fibre *content* of any Brambleloop pattern.
What is SOURCED is the fibre the pattern was written for, from the CIR's own yarn name.

---

## 6. 16 CFR 1500.19: the caveat, discharged, with what remains

`CHOKING_WARNING` carried this note: the text was "quoted from search results summarising 16
CFR 1500.19" because "the regulation renders the statement as an image", and it asked for a
rendered copy to be checked before any live listing (`CHILDRENS_CATEGORY.md` §6 item 4).

Three retrievals on 2026-09-25, over outbound HTTPS at no cost:

1. **SOURCED** — `https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-16?chapter=II&subchapter=C&part=1500&section=1500.19`
   (HTTP 200). The text of (b)(1) ends *"...shall bear or contain the following cautionary
   statement:"* and stops. Eight `<img>` elements — `ER27FE95.001` through `.008` — carry
   (b)(1) through (b)(4) and (f). **The caveat's premise is confirmed from the primary source
   rather than assumed.**
2. **SOURCED** — `https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title15-section1278`
   (HTTP 200). 15 U.S.C. 1278(a)(2) reads *"The cautionary statement required by paragraph (1)
   for a toy or game shall be as follows:"* and likewise prints nothing. **The statute does not
   carry the string either**, so there is no machine-readable copy anywhere to copy from.
3. **SOURCED** — `https://img.federalregister.gov/ER27FE95.001/ER27FE95.001_large.png`
   (HTTP 200, 7,435 bytes, sha256
   `c22fc31a1b4a1873180c3d00fea9d40bbf117dcb12e7e3bd3fb2d2c1c7c48d9e`), the rule's own
   rendering as published at 60 FR 10752, 1995-02-27, retrieved and read. Under the triangular
   safety-alert symbol it sets:

   ```
   WARNING:
   CHOKING HAZARD--Small parts
   Not for children under 3 yrs.
   ```

**The constant was wrong and is now right.** It read
`"WARNING: CHOKING HAZARD - Small parts. Not for children under 3 yrs."` — one line, a spaced
hyphen for the rule's double hyphen, and a full stop the rule does not set. 16 CFR 1500.19(d)(1)
requires the statements "blocked together within a square or rectangular area" and says "the
statements must appear on at least two lines", so the line structure is part of what is
required and the old one-line version could not have satisfied it.
`test_the_choking_statement_is_the_regulated_wording` now pins the exact three lines, because a
transcription is the kind of fact somebody tidies on the assumption the double hyphen is a typo.

### What is still not confirmed, and is said so

- **INFERRED, not SOURCED as text**: this is a **transcription of a 1995 bitmap by a reader**,
  not a string copied from machine-readable text, because no machine-readable copy exists.
  That is a different evidence class from reading prose and it is counted separately:
  `RENDERED_IMAGE` is a new retrieval kind and `image_read_sources()` enumerates it.
  `unfetched_sources()` deliberately excludes it — a source read as a picture is not the
  `search_summary` failure, where nobody read the page at all, and folding it in would have
  made the list that exists to be *shortened* get longer when a gap was closed. The diagnosis
  is written into that function's docstring.
- **UNKNOWN**: the safety alert symbol. 1500.19(d) governs how the statement is set, the
  symbol is a glyph this document cannot draw, and it is not in the string. A listing that has
  to satisfy 1500.19(d) needs it as artwork. Nobody has done that, and **nothing ships on it
  today**: no Launch-0 product is in the 3-to-under-6 band with a small part, so
  `choking_small_parts` is not in either product's required set.

---

## 7. The instrument: `statement_rendering_gap()` replaced

The old function grepped `publish/*.py`, `cir/*.py` and `commerce/*.py` for a statement's
distinctive words. **It was the right alarm** — zero files means nothing can print the set —
and it is the wrong instrument for the question it was standing in for. "Does a source file
mention choking" and "does the customer's PDF carry the choking statement" are different
questions, and the first is satisfied by a comment. Now that `publish/pdf.py` renders the
block, the grep would report success for a build in which the section was laid out off the
bottom of the last page and never reached a reader.

The headline now comes from the artefact: for every Launch-0 children's variant, in every
terminology sold, the required statement set is checked against the text extracted from the
rendered PDF. The old reading is **kept** under `source_grep`, with its limitation named,
because throwing away a measurement is how the next reader loses the history of one.

`childrens_view()` changed for the same reason. `as_built` passed a hard-coded `()` — honest
when nothing was rendered, and a constant that would have gone on reporting a gap after the gap
closed. It now reads the rendered document. `as_planned` stays, because it asks a different
question: the commitment, not the artefact.

---

## 8. The listing surface: which statements, and which not

`commerce/seo.build_description` gained an optional children's statement set, printed under
`SAFETY AND SUITABILITY` above the "how this was made" block.

**The test applied: does the buyer need this before they pay?** Three do.

| statement | in the listing | why |
|---|---|---|
| `age_suitability` | yes | the buyer is choosing for one particular child; the band decides whether this is the right pattern |
| `safe_sleep` | yes | a baby blanket is bought for a cot unless somebody says otherwise, and the place to say otherwise is before the money |
| `selling_finished_items` | yes | a maker buying in order to sell is taking on manufacturer obligations; finding out after purchase is too late |
| `choking_small_parts` | yes, where required | gift suitability: a buyer shopping for a three-year-old decides at the listing |
| `face_construction` | no | an instruction for working the piece |
| `supervision` | no | about using an object the buyer does not yet have |
| `construction_integrity` | no | gauge and seam guidance, unreadable out of the context of the rows |
| `fibre_and_care` | no | about the finished object, and the ball band of the yarn they choose governs it |
| `mobile_removal` | no | a making-and-using fact |
| `not_legal_advice` | no | the abbreviated set and its disclaimer travel together in the document |

**What is deliberately NOT claimed.** **SOURCED** — 15 U.S.C. 1278(c) (read at
uscode.house.gov, 2026-09-25) requires the cautionary statement in any advertisement offering
*"a product for which a cautionary statement is required under subsection (a) or (b)"*, and
subsections (a) and (b) attach to a toy, game, ball, marble or balloon. **The product on our
listing is a PDF, not a toy**, so that advertising requirement does not reach us. The choking
statement is on the list above for our own reason — gift suitability — and not a regulator's,
and `commerce/seo.py` says so in the comment beside the list.

The listing prints the statements' **own words**, not a shortened restatement. Requirement
40's lesson applies exactly: the licence diverged across four surfaces because each surface
wrote its own version of one decision. A listing paraphrase of a safety statement is the same
defect with a worse consequence.

**UNKNOWN — whether Etsy itself requires any of this in a listing description.** The Etsy
Children and Baby Products policy is a `search_summary` source in `intel/childrens.py`;
`etsy.com` returns HTTP 403 to this environment, so nobody in this build has read the page.
That gap is unchanged and is still enumerated by `unfetched_sources()`.

---

## 9. Defects found, ranked

1. **`nordic-forest-mosaic-throw-baby` is a children's product with no children's
   assignment.** Its title is "Nordic Forest Overlay Mosaic Blanket (Baby)". The safety block
   is keyed on the assignment, so it would render with no safety notes while every other gate
   passed — the silent version of the failure this whole module exists to prevent, one layer
   above where `intel.childrens` can see it. It does not ship today because it fails the
   colourwork gate, which is luck rather than design.
   **Not fixed here**: whether a product is merchandised to a child is a merchandising
   decision, and a title word is evidence for it rather than the decision. `launch0.
   childrens_titles_without_an_assignment()` now reports it and a test pins that it is
   reported. **Owner: product planning.**
2. **`CHOKING_WARNING` was not the regulated wording.** Wrong punctuation, wrong line
   structure, and 1500.19(d)(1) makes the line structure part of the requirement. **Fixed**,
   against the rule's own rendering. Nothing had shipped on it.
3. **`cir.model.Material` records no fibre.** Section 5. **Not fixed** — it is a CIR field and
   `cir/**` is not this department's. Specified precisely above.
4. **`statement_rendering_gap()` measured source files for a question about a document.**
   **Fixed**; old reading kept beside the new one.
5. **`childrens_view()["as_built"]` was a hard-coded `()`.** Honest when written and a
   constant that could not notice the gap closing. **Fixed**: it reads the PDF.
6. **`runtime/release.py:365` does not pass the children's statements to
   `build_description`.** So the live listing chain will produce a children's listing with no
   safety section, and `seo.childrens_listing_audit` will fail it. `runtime/**` is not this
   department's. **The precise change**: at `release.py:365`, pass
   `childrens=publish.pdf.childrens_statements(cir, twin, assignment)` where
   `assignment = products.launch0.childrens_assignment(cir.slug)`, when that is not None.
   **Owner: whoever owns `runtime/release.py`.** Nothing is live, so nothing is wrong today.

## 10. What is still blocked

- **The fibre content claim** — blocked on `cir.model.Material` gaining a fibre field
  (section 5). The *statement* is unblocked and renders; the *composition* claim is not made.
- **The safety alert symbol for 1500.19(d)** — blocked on artwork nobody has made. Not needed
  by any Launch-0 product.
- **Reading Etsy's Children and Baby Products policy verbatim** — unchanged, HTTP 403.
- **`twin.calibrated` is False catalogue-wide** — every finished measurement printed in the
  safety block is arithmetic from a stated gauge, exactly as it is on the cover. The safety
  block does not make a new claim about it, and the document's existing tolerance language is
  untouched.

Nothing here is an OWNER ACTION REQUIRED item. Nothing needs money, KYC, legal acceptance or a
physical act.

---

## 11. What was re-run, and what it counted

Every suite this diff can reach, on the final code, with
`PYTHONPATH=src <python> tests/<file>.py`. `run_tests.sh` was not run: the integrator runs it.

| suite | passing | failing | was |
|---|---|---|---|
| `test_childrens` | 38 | 0 | 30 |
| `test_launch0` | 46 | 0 | 43 |
| `test_deliverable_qa` | 46 | 0 | 41 |
| `test_commerce` | 53 | 0 | 47 |
| `test_product_run` | 35 | 0 | 35 |
| `test_gates` | 33 | 0 | 33 |
| `test_shop_package` | 18 | 0 | 18 |
| `test_friction` | 19 | 0 | 19 |
| `test_rowcycle` | 20 | 0 | 20 |
| `test_accessibility` | 9 | 0 | 9 |
| `test_teardown_reader` | 12 | 0 | 12 |
| `test_teardown_proof_run` | 7 | 0 | 7 |
| `test_listing_parity_gate` | 6 | 0 | 6 |
| `test_products` | 16 | 0 | 16 |

**Twenty-two checks added, none removed, no threshold lowered.** Two existing assertions in
`test_childrens` changed and both got stronger: the source-date check went from `==` to `>=`
so a *later* confirmation can be recorded honestly, and the choking-statement check went from
"starts with WARNING: CHOKING HAZARD" to the exact three confirmed lines. Two assertions in
`test_launch0` changed because the gap they asserted has closed, and the replacements are
measured on the rendered document rather than on a constant.

**Two checks are proved against an injected defect**, so neither stops being a test once the
defect is fixed: renaming the blanket's yarn to one naming no fibre makes
`build_pattern_pdf` refuse (`test_a_childrens_document_missing_a_statement_is_refused_rather_
than_shipped`), and building the listing without the statements makes
`seo.childrens_listing_audit` fail (`test_the_listing_audit_fails_on_a_description_that_lost_
the_block`).

The obligation tables were checked for silent change by importing the previous revision of
`intel/childrens.py` alongside the new one: all ten obligations byte-identical, every
constraint, sub-category, statement set and verdict unchanged, one source added and none
removed. Renders are still byte-deterministic for a fixed release date.
