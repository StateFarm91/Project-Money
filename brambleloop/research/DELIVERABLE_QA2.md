# Customer deliverable audit II — the pattern PDF, in both terminologies

**Date:** 2026-09-25 (UTC) · **Predecessor:** `research/DELIVERABLE_QA.md` (2026-09-24), whose
thirteen findings are established and were not re-litigated.

**Scope:** everything the buyer receives, read in **US and UK** this time — `publish/pdf.py`,
`publish/abbreviations.py`, `publish/charts.py`, `publish/value_stack.py`, `brand/bible.py`,
the release chain in `runtime/release.py` and `runtime/pipeline.py`, and the licence surfaces
`commerce/terms.py`, `commerce/seo.py`, `commerce/shop_package.py`, `growth/content.py`.

**Method:** render the real PDFs for all sixteen shippable designs in both terminologies,
extract every page with `pypdf`, and read them as somebody who has paid and is trying to make
the thing. Charts were rendered and looked at as images, not inferred from their code. Every
finding below was found by reading output, not by reading source.

**Out of scope by ownership:** `src/brambleloop/visual/**` and `src/brambleloop/cir/**` were
read, never edited. `integrations/etsy.py` and `integrations/http.py` were read, never edited —
the second PDF is attached through `EtsyClient.attach_file` as it already stands.

---

## What shipped

### 1. Both US and UK documents now ship — and the UK one was wrong in two places

`assets.build` rendered `pattern-us.pdf` and nothing else, while four live surfaces claimed
both: the listing title (`US and UK Terms`), the listing description (`US and UK
terminology`), the content FAQ (`the UK equivalent for every stitch in the key`) and a
Pinterest pin. The claim was unsupportable on both counts — one file, and no key has ever
listed equivalents.

`assets.build` and `store.publish` now render, store and attach both, keyed on
`pdf.TERMINOLOGIES`; neither names a file any more (`pdf.pattern_filename`), and the
listing/FAQ/pin copy now describes **two PDFs**, which is what the buyer receives.

**The UK PDF was verified by rendering and reading it, not by trusting the mapping** — and it
was wrong twice, in exactly the way the mapping could not show:

* **The gauge was still in US terms.** `cir.gauge.stitch_type` is a canonical code, which is a
  US abbreviation. `cir.writer` localises it on the instructions page; `publish/pdf.py` printed
  it raw in three other places. Every UK document in the catalogue said
  `16 sts x 18 rows = 10 cm in sc` on its cover and `10cm in dc` on page 4 — **one gauge, two
  stitches, in one file**. `sc` is not a UK abbreviation at all, so it was also a word that
  document's own key never defined; a UK maker resolving it against their own vocabulary
  swatches a treble, three times the height the gauge was measured at.
* **The special-stitch methods were still in US terms.** Every method paragraph said "double
  crochet". In UK terms that is the stitch a US pattern calls single crochet — *half the
  height*. So a UK document whose token had been correctly localised to `fptr` went on, in the
  paragraph that actually teaches the stitch, to tell the maker to finish it as a double
  crochet. Every post stitch at half height, cables that do not stand up, a throw about half
  its stated 129 cm. **This is the predecessor's finding #1 arriving again through prose
  instead of through a token**, and `unlocalised()` cannot see it: it renders ops through the
  writer and never sees a method paragraph.

Both are fixed at the source of the names rather than by a second table: `_gauge_stitch` routes
through `abbreviations.token`, and `METHOD` now holds no stitch name at all — every one arrives
as `{dc}`, resolved out of `cir.stitches` by `abbreviations.method(code, terminology)`.

The guard for the second one is `method_names_no_stitch_literally()`, checked on the templates
rather than on a render, because **a rendered UK document cannot be checked for this**: "double
crochet" is the US name of `dc` and the UK name of `sc`, the same eleven characters whether it
is right or wrong. The checkable property is the stronger one — a method paragraph names no
stitch except through the registry.

### 2. One licence, and a check that can see the PDF

The predecessor found three copies and reported two unified. There were **four**, and the
fourth was the one the customer keeps.

| surface | what it said |
|---|---|
| `commerce/terms.py` (the decision) | sold "by individual makers and small businesses, not manufactured at scale"; personal use **and teaching** |
| `brand/storefront.py` | already rendering from the decision |
| `commerce/seo.py` | "Sell what you make" — no limit |
| **`publish/pdf.py` — the PDF** | "This pattern is for your personal use. You may sell finished items you make from it" — **no limit, and no teaching right** |

The PDF was simultaneously *more* permissive than the decision on selling and *less* permissive
on teaching, and it is the most authoritative surface a buyer holds.

**Requirement 40's consistency check exists for exactly this and could not see it.**
`terms.consistency(pdf_text, …)` was called everywhere with `terms.render(terms, "pdf")` — the
decision rendered for the PDF surface, *not the PDF*. It compared the decision with itself on
the one surface that had diverged and reported three surfaces consistent.

Now: `commerce.terms.BRAMBLELOOP_TERMS` is stated in its own source as **the canonical Launch-0
licence**; `publish/pdf.py` holds no licence text (`LICENCE` is gone, `licence_paragraphs()`
renders the decision), and `commerce/seo.py` renders it too, supplying only its own heading —
surfaces are allowed different headings and not different answers. Four surfaces, one source.
`test_the_licence_in_the_real_pdf_is_the_one_the_company_decided` extracts the text from the
rendered PDF and runs the consistency check on that, and the companion case proves it now fails
on a hand-written PDF surface.

**Legal review: no concrete reason found that it must precede first sale.** These are terms this
company offers about its own copyright work in its own jurisdiction; nothing in them is a
regulated disclosure, a consumer-law notice, or a statement whose absence voids a sale.
`enforceable` stays `False` and the page says so, which is the honest word for an unreviewed
term. Review is scheduled before material scale (owner decision 4), not as a launch blocker.
This is recorded in `terms.py` beside the decision so the next reader does not have to ask.

**One thing changed while unifying.** Printed side by side for the first time, the licence block
said "questions are answered by email" directly above the document's own paragraph telling
buyers to ask through the shop they bought it from. **There is no support mailbox.** A term that
names an unreachable channel is worse than a narrower one, because the buyer who tries it
concludes nobody is there. `SUPPORT_POLICY` gained `version_aware_shop_message` and that is now
the chosen option; the old option is kept, unchosen, for the day a mailbox exists.

---

## New findings, ranked by whether they stop somebody making the thing

### 1. The chart showed a repeat the pattern does not have, at 1.9 mm per cell — FIXED

The worst thing in the document, and the headline feature of the product.

`charts.detect_repeat` searches for a row period that **divides** the row count and **starts at
row 1**. Eight of the sixteen shippable designs satisfy neither — they open with setup rows and
then repeat a block whose period is not a divisor of the total:

| design | `detect_repeat` said | the written pattern says |
|---|---|---|
| heirloom-cable-blanket | 8 × **121** | rows 2–5, 29 more times |
| chunky-ribbed-scarf | 4 × **101** | rows 2–5, 24 more times |
| bobble-floor-pillow | 5 × **53** | rows 2–5, 12 more times |
| cloudline-baby-blanket | 9 × **88** | rows 9–16, 9 more times |
| harvest-table-runner | 8 × **112** | rows 9–16, 12 more times |
| pet-snuggle-mat | 8 × **56** | rows 9–16, 5 more times |
| cottage-wall-hanging | 8 × **48** | rows 9–16, 4 more times |
| mosaic-placemat-pair | 9 × **40** | rows 9–16, 3 more times |

So the cabled throw's chart page read *"This chart shows one repeat: 8 stitches wide and 121
rows tall. Work it 18 times across and once up"* — three pages after instructions saying
*"Repeat rows 2-5 29 more times"*. **Two repeat detectors, one fabric, two answers, and the
chart printed the wrong one.**

The consequence was worse than the contradiction. An 8 × 121 block scaled to fit the page is a
**16 mm wide ribbon down a 216 mm page at 1.9 mm per cell**, carrying a glyph of about 3pt. The
chart page was three pages, two of them almost entirely blank.

Fixed by asking the detector the written pattern already uses. `charts.row_block` reads
`cir.rowcycle.detect_cycle` — the canonical answer, since the written pattern collapses to it
and the reverse compiler expands it back. The chart shows rows 1 through the end of the first
repeat, so no row is omitted, and the caption states the same numbers the instructions do:
*"work rows 1 to 5 once, then work rows 2 to 5 29 times more, exactly as the written
instructions say."* Measured across the catalogue, cells went from **1.9–4.3 mm to 5.1–7.5 mm**
and the cabled throw's document from 8 pages to 6.

### 2. Nothing measured the chart's type, and the gate that stood in for it was a proxy — FIXED

The check that should have caught #1 was `full_cols > 48` — a column count standing in for "this
will be too small to read". The harvest table runner is 48 stitches wide, failed the gate **by
one stitch**, and printed its whole 48 × 112 fabric at 2.1 mm per cell.

The deeper reason nothing saw it: **the chart's type is pixels inside an image**. The
source-level fixture that holds every `size=` and `setFont` in `pdf.py` to the brand's 9pt
minimum cannot see a glyph drawn into a PNG and then scaled by `_Doc.image` to fit the page —
how large it ends up is a property of neither the renderer nor the document alone.

`_on_page_cell_mm` now does the same arithmetic `_Doc.image` does, the chart is chosen on that
measurement rather than on a column count, and `PDF_CHART_CELL_BELOW_BRAND_MINIMUM` reports the
number when a chart cannot be made legible. The floor is **derived, not chosen**:
`MIN_BODY_PT / CHART_GLYPH_RATIO` = 5.12 mm, the cell size at which the chart's glyph reaches
the brand's own minimum type size. Every design clears it; the test proves the check still
fires by raising the floor rather than by waiting for a bad design.

### 3. The key-completeness check could not come out badly, and was run on one section — FIXED

`undefined_tokens(text, terminology)` built the key from `text` and then asked whether anything
in `text` was missing from it. That is a comparison with one possible answer, and the
unreachable branch carried a `pragma: no cover` saying so, under a docstring calling itself
*"the inverse check, and the one that matters"*.

It was also run only on the writer's instruction text — one section of eight. The document also
sets a cover, a gauge block, a materials list, a colour key and a finishing section, and
**none of them was ever measured**. That is where the UK gauge line's `sc` was sitting.

Three changes, each needed for the check to be able to fail:

1. `_Doc` accumulates its own prose, and the check runs last, on the whole document.
2. It takes `defined` — the key that was actually **printed** — instead of deriving one.
3. **It scans both vocabularies.** Scoping to `terminology` is what let the real defect
   through: `sc` is not a UK rendering of anything, so a UK-only scan had nothing to look for.

Two things had to be got right before it was usable, both diagnosed as the *artefact* being
wrong or the *check* over-reaching rather than by relaxing a threshold:

* The UK special-stitch method said "Miss the top of that stitch" — `miss` is the UK token for
  `sk`, used there as an ordinary verb, in a document whose key does not define it. **The
  artefact was wrong**: the prose now reads "Do not work into the top of that stitch", which is
  clearer and terminology-free.
* The UK hexagon coaster was reported as using an undefined `inc`. **The check was
  over-reaching**: the UK rendering of `inc` is "dc inc", which contains the US rendering.
  Defined tokens are struck out longest-first before the scan, so a token that only ever appears
  inside a longer defined one is not reported.

### 4. The chart told the maker to follow a key that existed only as pixels — FIXED

The chart marks every square with its yarn's letter and the greyscale note says in so many words
*"follow the letters rather than the shading"*. The letter-to-yarn mapping existed in exactly one
place: the rendered legend image — unsearchable, unselectable, invisible to a screen reader, and
gone entirely on a reader that dropped the images. The document instructed a maker to rely on a
key it had only drawn.

There is now a **Colour key** section in text, ordered by letter (the direction a key is read
in), rendered from `charts.color_letters` so the page and the picture cannot disagree.

And the sentence saying where to look had to stop being one sentence: it said *"each square on
the chart carries its yarn's letter"* for every pattern, and **a round chart has no squares** —
`render_round_chart` puts the letter on the round *number*, and only for a round worked entirely
in one colour. On the one construction where a reader most needs telling where to look, the
legend described a chart that was not in front of them. `COLOUR_CUE_NOTE_FLAT` and
`COLOUR_CUE_NOTE_ROUND` are stated once and used by both the legend image and the PDF.

### 5. Two different stitches drew the same chart glyph — FIXED

`GLYPHS` mapped both `sc` and `cable1x1` to `"x"`. Nothing in the catalogue uses `cable1x1`, so
the two had never appeared in one chart and the collision was invisible — **a defect whose only
sample could not contain it**. A chart drawing two stitches with one mark, above a legend
listing that mark twice, is a maker working the wrong stitch off the chart this product is sold
on. `cable1x1` is now `"/"`, the single crossing to `"X"`'s double, and a test asserts the map is
injective and covers every registered stitch.

### 6. The chart's own small type was below the accessibility floor — FIXED

The predecessor corrected the document's prose to WCAG AA and left the chart, which is inside
that same document. `muted` on `cream` is **4.48:1** and it is the colour of the chart's row and
stitch numbers, its caption and the legend's colour-cue note — the labels a maker reads with the
work in their hands. Half the type in the file was measured and half was not.

The contrast arithmetic and the 4.5 floor moved to `brand/bible.py` — one implementation, read
by both renderers — and `charts.MUTED` is darkened through it to **4.68:1**. The palette itself
is untouched and every existing colour renders byte-identically.

### 7. The colour cue's own legibility was decided by a proxy, and it was wrong — FIXED

`charts._readable_on` said it picked the colour "a human can actually read" and decided from a
weighted-average lightness against a hand-set threshold of `0.55`, which is not a contrast
measurement and does not have to agree with one. What it draws is the per-colour letter — the
feature that makes a mosaic chart readable by a maker who cannot tell the yarns apart by hue —
and yarn colourways arrive from the CIR as arbitrary hex, so a threshold standing in for the
measurement will eventually meet the colour it is wrong about. On the brand's own `muted` it
chose cream at **4.48:1**; on a plain mid-grey the result was **3.9:1**.

There was a subtler version of the same mistake in the first fix: ranking the two candidates
*before* moving them picks the one with nowhere to go. On a mid-lightness yarn the brand cream
measures fractionally better than the brand ink and is already nearly white, while the ink can be
darkened all the way to legible. Both candidates are now moved first and the better *result*
taken. **Every brand colour's choice is unchanged**; only the failing cases move.

### 8. The greyscale warning counted colours it had not counted — FIXED

*"Printing in black and white: two of these colours are close in lightness"* — however many
pairs merged. On a four-colour pattern where three merge, "two" sends a maker looking for a pair
that is not the problem. No pattern in the catalogue fails the greyscale check, so **the one
sentence in the document nobody has ever read was the one with the arithmetic wrong in it**.
`print_safety` already knew which pairs; it now returns `merging_pairs` and the document names
them. Covered by a test that constructs the failing case, since the catalogue cannot.

### 9. The chart renderer held its own copy of the brand palette — FIXED

`brand/bible.py` says "anything that renders an asset reads from here". `publish/charts.py` held
six of those hex codes **written out as RGB triples** — which is how a duplicate survives a
search for the hex string that would have found it. The PDF was corrected on 2026-09-24 and the
chart inside it was not, so the chart was the last asset where the brand was not actually
locked. Now `bible.rgb255`, byte-identical output, and a test that fails on a returning literal.

---

## What was found and not fixed

**`TwinModel` still exposes only a total height** (`cir/**`, Visual-owned), so
`value_stack.milestones` still interpolates linearly. Unchanged from the predecessor's report,
and it did not block this work.

**`stitches.Stitch` still has no crossing direction** (`cir/**`, Visual-owned).
`PDF_CABLE_DIRECTION_UNSPECIFIED` is still the only problem any catalogue document reports, and
its test still asserts the field's absence so the finding deletes itself when Visual adds it.

**The round chart's readable unit is not measured.** A round chart's unit is the width of a ring,
not a square cell, and `_chart_art` returns `cell_mm: None` for it rather than a passing number —
so the legibility check reads as *not applicable*, not as *checked*. The hexagon coaster's rings
are comfortable today; the measurement should exist before a round design with sixty rounds does.

**The chart's row and column labels are set at 0.55 of the cell**, against the glyph's 0.62. At
the new floor the glyph reaches the brand's 9pt minimum and the labels land near 8pt. Raising the
floor to satisfy the labels would inflate every chart in the catalogue; the honest statement is
that the floor is set by the glyph and the labels sit just under it.

**The legend image still bakes its text into pixels.** Both keys it contains — stitch and colour
— are now in text elsewhere in the document with a line pointing at them, so a reader who cannot
see the image has a route to everything in it. The image itself is still an image.

**Nothing verifies the PDF against a physically worked sample.** `twin.calibrated` is `False`
for the whole catalogue and the document says so where it matters. Unchanged, and still the
largest unmeasured risk in the deliverable.

---

## Tests

`tests/test_deliverable_qa.py` — **41 checks** (was 22), all passing. No existing check was
removed, weakened or re-pinned. Each new one states what it measures and why, and the ones
pinning a gap say which module owns the fix.

Three of them are the kind this codebase keeps needing — a check proved against an **injected**
defect rather than against a live one, so that it does not stop being tested the moment the
defect is fixed: the method-template guard is shown failing on a hand-written "double crochet",
the chart legibility floor is shown reporting by raising the floor, and the licence consistency
check is shown failing on a hand-written PDF surface.

Suites re-run clean: `test_deliverable_qa`, `test_deliverable`, `test_products`, `test_texture`,
`test_layout_qa`, `test_accessibility`, `test_gates`, `test_bible`, `test_brand`,
`test_commerce`, `test_shop_package`, `test_platform_policy`, `test_growth`, `test_pins`,
`test_commercial_truth`, `test_teardown_reader`, `test_teardown_readiness`, `test_value_stack`,
`test_substitution`, `test_render`, `test_visual`, `test_listing_schema`, `test_listing_set`,
`test_listing_assets` via `test_product_run`, `test_mobile`, `test_eligibility`, `test_defects`,
`test_dimensions`, `test_motif_fidelity`, `test_crochet_topology`, `test_compiler`,
`test_reverse`, `test_twin`, `test_rowcycle`, `test_etsy`, `test_etsy_capability`,
`test_shadow`, `test_acceptance_gates`, `test_launch`, `test_teardown`, `test_quality`,
`test_proof`, `test_buyer_trust`, `test_trust`, `test_offers`, `test_first_hundred`,
`test_friction`, `test_product_run`.

`run_tests.sh` was not run (out of scope for this worktree).

## Collision notes

`runtime/release.py` was edited in `assets.build` only (the render/store block and the two
payload keys) — Reliability II may hold other parts of that file.
`integrations/etsy.py` and `integrations/http.py` were not touched; the second file is attached
through the existing public `attach_file`.

---

**Continued in `research/DELIVERABLE_QA3.md` (2026-09-25).** The four items ranked open at
the end of this file were worked in order there: the round chart's ring is now measured and was
1.2 mm on the Launch-0 baskets, the legibility floor is re-derived from the smallest type a
chart sets rather than the largest, the chart's symbol key is now in text, and the palette
finding was already closed here as #9.
