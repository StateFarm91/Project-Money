# Customer deliverable audit III — the chart, measured where the buyer reads it

**Date:** 2026-09-25 (UTC) · **Predecessors:** `research/DELIVERABLE_QA.md` (2026-09-24) and
`research/DELIVERABLE_QA2.md` (2026-09-25), whose findings are established and were not
re-litigated. This file is an append, not a rewrite: nothing above it was changed.

**Scope:** the four items left ranked-open at the end of `DELIVERABLE_QA2.md`, worked in that
order, on the three Launch-0 products and the documents they produce —
`nursery-nesting-baskets` (three basket variants), `cloudline-baby-blanket`,
`hexagon-coaster-set` — plus every other design the pipeline can ship, in **both**
terminologies.

**Owned and edited:** `publish/charts.py`, `publish/pdf.py`, `tests/test_deliverable_qa.py`,
`tests/test_accessibility.py`. `publish/abbreviations.py`, `publish/value_stack.py` and
`tests/test_render.py` were read and needed no change. Nothing in `cir/**`, `visual/**`,
`ops/**`, `integrations/**`, `products/**`, `commerce/**`, `runtime/**` was touched.
`brand/bible.py` was re-confirmed as the single palette and contrast source and needed no
change either.

**Instrument.** Three things, all of them on the artefact rather than on the plan:

1. `_on_page_cell_mm(width, height, unit_px)` — `_Doc.image`'s own scale arithmetic, so the
   number is the size a chart's readable unit reaches **on the printed page**, which is a
   property of neither the renderer nor the document alone.
2. `charts.flat_type_px` / `charts.round_type_px` — the functions the renderer itself calls to
   pick its font sizes, so a check asking "how big is the type in this picture" asks the
   renderer instead of a reading of it. Multiplied by the page scale, that is points on paper.
3. `pypdf` extraction of the real PDF bytes for everything the document *says*.

---

## 1. The round chart's readable unit was not measured — CLOSED, and it was the worst defect in the deliverable

`_chart_art` returned `cell_mm: None` for every piece worked in the round, so the legibility
check read *not applicable* rather than *checked*. `DELIVERABLE_QA2` called that "the honest
stopgap, not the answer" and expected the hexagon coaster's rings to be comfortable. They are.
**The baskets are not**, and the baskets are the Launch-0 flagship.

Measured for the first time, on the rendered chart, at the size `_Doc.image` puts it on a
Letter page:

| Launch-0 chart | ring, before | round number, before | ring, after | round number, after |
|---|---|---|---|---|
| nesting basket, large (25 cm) | **1.21 mm** | **2.1 pt** | 6.86 mm | 11.7 pt |
| nesting basket, medium (20 cm) | **1.65 mm** | **2.9 pt** | 8.58 mm | 14.6 pt |
| nesting basket, small (15 cm) | **2.53 mm** | **4.2 pt** | 11.44 mm | 19.5 pt |
| hexagon coaster set | 6.64 mm | 11.3 pt | 6.64 mm (unchanged) | 11.3 pt |

1.21 mm per ring is three times worse than the 1.9 mm flat chart that was the headline finding
of the previous audit, on the flagship product, and it survived two audits **because the one
number that would have shown it was `None`**. A check that excuses a case is not a check that
covers it.

### Why a basket's chart could not be legible, and what it is now

A whole disc puts its *diameter* across the page, so a ring is at most half the usable width
divided by the round count: about `90 / (rounds + 1)` mm, whatever the render resolution. The
large basket has **70 rounds**. No choice of pixels makes that readable; the geometry forbids
it. Two things were wrong at once, and each has a counterpart the flat chart already does:

* **Forty-six of those seventy rounds are a straight side wall** — `sc` in every stitch, 144
  stitches, no shaping. A basket is a flat base with a cylinder standing on it, and drawing the
  wall as forty-six concentric rings is not only illegible, it is *a picture of a disc the
  basket is not*. `charts.round_block` finds the trailing run of rounds with no shaping and a
  constant stitch count — derived from the twin, with the shaping codes read out of
  `cir.stitches` via `consumes != produces` rather than listed — and the chart shows rounds 1
  to 24. This is the round counterpart of `row_block`.
* **Every round repeats six identical wedges**, because a disc from a magic ring is
  `[sc in next n, inc] x 6`. `charts.wedge_count` derives that period from the twin the same
  way `detect_repeat` derives a column period, colour included; the chart draws one wedge, so
  the radius rather than the diameter spans the page — exactly twice the ring width. This is
  the round counterpart of the flat chart's column crop.

Neither is applied unless it is needed. `_round_chart_art` walks a ladder — whole disc, then
the shaped block, then one wedge of the shaped block, then one wedge of the whole piece —
predicts each rung's ring size from geometry alone (a 2400-pixel square is not rendered to be
thrown away), renders the first rung that can clear the floor, and **reports the number
measured on the image that was actually produced**. The hexagon coaster takes rung one and its
chart is byte-identical to before.

**A chart that shows part of a piece and does not say so would be a new defect, not a fix**, so
the caption states what is left out in the document's own numbers, all read back out of the
twin — including the two contrast bands up the basket's wall, which are in the rounds the chart
no longer draws:

> It shows rounds 1 to 24, which are the rounds that shape the piece. Rounds 25 to 70 are then
> worked straight at 144 stitches with no increases. Drawing them would add 46 identical rings
> and shrink every ring in this chart, so the chart stops at round 24. They are worked in cream
> except rounds 44-45 and 56-57 in wine, and the written instructions give the colour of every
> round.

Verified by extraction from the real PDF in both terminologies.

---

## 2. Chart labels sat under the raised floor — CLOSED, and the floor was derived from the wrong number

`CHART_MIN_CELL_MM` was `MIN_BODY_PT / 0.62`, and **0.62 is the stitch glyph — the largest
piece of type in the picture**. A floor derived from the largest type certifies the one thing
that was never in danger. The row and column numbers are set at 0.55 of a cell and the colour
cue at 0.46, so at the cell size that floor permitted:

| type in a flat chart | ratio | at the old floor | measured, worst design, before | after |
|---|---|---|---|---|
| stitch glyph | 0.62 | 9.0 pt | 8.59 pt (`pressed-flower-motifs`) | 12.40 pt |
| row / column number | 0.55 | **7.98 pt** | **7.93 pt** | 11.00 pt |
| colour cue letter | 0.46 | **6.67 pt** | **6.61 pt** | 9.20 pt |

The colour cue is the mark that makes a mosaic chart readable to a maker who cannot tell the
yarns apart by hue. It was shipping at 6.6 pt against a brand minimum of 9.

The fix is not a bigger number, it is the right derivation. The ratios are now named once in
`charts.py` (they were bare literals inside two render functions, with a third copy of `0.62`
in `pdf.py`), and the floor comes from the **smallest** of them:
`CHART_MIN_CELL_MM = MIN_BODY_PT / min(0.62, 0.55, 0.46) / mm` = **6.90 mm**, up from 5.12,
and `CHART_MIN_RING_MM = MIN_BODY_PT / min(0.55, 0.60) / mm` = **5.77 mm** for round charts,
which set no cue. Every design in the catalogue clears its floor with no chart redesign: the
existing crop path handles `pressed-flower-motifs`, which was the only flat chart between the
old floor and the new one.

**Every piece of type inside every chart in the catalogue now measures at or above 9pt on the
page.** The tightest is the colour cue at 9.20 pt.

The legend image is measured too, and passes: its type is fixed pixels rather than a ratio
(there is no readable unit for a list of rows to be a fraction of), and at every entry count
the taxonomy can produce it lands at 10.6 pt and 12.0 pt. It is named in `LEGEND_TYPE_PX` and
checked rather than assumed, because a legend tall enough to be scaled down by page height
would shrink it — about twenty-seven entries, which nothing can currently reach.

The raise is strictly stronger than what it replaced: a higher floor, and nothing that passed
before at or above 6.90 mm is now permitted to fail.

---

## 3. The legend baked its text into pixels — CLOSED, and the pointer that excused it was false

`DELIVERABLE_QA2` ranked this third because "both keys are now in text elsewhere with pointers
to them". Measured against the extracted PDF text, **one of those two pointers pointed at
nothing**:

> The stitch key in the image above is also written out under Abbreviations, earlier in this
> document.

The Abbreviations page writes out *abbreviations*: `cable2x2` means a 2-over-2 cable crossing.
It has never carried a chart symbol, in any document this company has ever rendered. A maker
who saw an **X** on the chart and followed that sentence arrived at a page with no X on it, and
the mapping from mark to stitch existed in exactly one place in the whole deliverable — the
rendered legend image, in pixels, unsearchable, unselectable and invisible to a screen reader.
This is the same defect the colour key had on 2026-09-24, on the other half of the same image,
and it was covered by a sentence rather than fixed.

There is now a **Chart symbols** section in text on the chart page, ordered by symbol (the
direction a key is read in), from `charts.GLYPHS` for the mark and `cir.stitches` through
`publish/abbreviations.py` for the name — so the picture and the paragraph cannot disagree, and
a UK document cannot acquire a US stitch name by way of a chart key. Verified in both
terminologies: the cabled throw's US document reads `X cable2x2 2-over-2 cable crossing`,
`] fpdc front post double crochet`; its UK document reads `] fptr front post treble crochet`.

A round chart marks only where the stitch count changes, so its symbol section lists only the
marks it draws — telling a round chart's reader about a symbol in every square is the mistake
`COLOUR_CUE_NOTE_ROUND` was written to stop.

The legend image stays. It is good, and nothing in the document is now said only as pixels.

---

## 4. `publish/charts.py` holding the brand palette as RGB triples — NOT REAL, already closed

Measured, not assumed. `charts.py` lines 31–35 read `bible.rgb255(...)`; `charts.MUTED` is
`bible.legible(...)` of `bible.rgb255("muted")` on cream; there is no `contrast_ratio` and no
`0.2126` in the module. This was `DELIVERABLE_QA2` finding #9 and it was fixed there; the
ranked open list I was handed was stale on this one point. **No diff is owed to any other lane
for it.**

The check that guards it was weak, so it was strengthened rather than left: it named two of the
six hex codes as forbidden literals, which leaves four ways back. It now parses the module and
fails on **any** three-integer tuple whose value is a brand colour, and asserts the contrast
arithmetic has not regrown locally. Proved to fire on an injected literal.

---

## New defects found while measuring

Ranked by whether they stop somebody making the thing.

### A. The colour key described a chart that was not in front of the reader — FIXED

Found because fix #1 created it, and it is the same shape as `DELIVERABLE_QA2` #4 arriving by a
different route. The document printed a **Colour key** whenever the CIR held more than one yarn,
above the sentence *"each round number on the chart carries its yarn's letter"*. That is a
claim about the picture decided from the pattern. A basket's contrast bands are up the wall, in
the straight rounds the chart no longer draws, so every round on the cropped picture is cream
and **not one of them carries a letter** — in all three Launch-0 basket variants.

The decision of which colours a chart labels now lives in one place per chart kind
(`charts.flat_cue_letters`, `charts.round_cue_labels`), the renderer calls it, and the document
asks the same function. Where there are no letters, the document prints **Colours** instead —
the yarn names and their hex values, under a heading that promises nothing — and says why:
*"Every round this chart shows is worked in one colour, so no number on it carries a colour
letter. The written instructions name the yarn for every row and round in the pattern."*

This also closes a latent version of the same bug on flat charts: a two-colour design whose
chart is cropped to a single-colour repeat would have printed a key to letters the picture does
not carry.

### B. A round chart's footer named marks it does not draw — FIXED

`"V marks an increase, A a decrease"` was printed on every round chart, as a literal. `GLYPHS`
draws a **double crochet** increase as `W` and a decrease as `M`. A disc worked in double
crochet would carry a footer naming two marks that are not on it and omitting the two that are.
No design in this catalogue works a disc that way, so the sentence has never yet been wrong on
a shipped document — which is the same shape as the two stitches that shared one glyph
(`DELIVERABLE_QA2` #5): a defect whose only sample cannot contain it. `charts.round_mark_note`
builds the sentence from the marks present, with increase/decrease read from the taxonomy's
`consumes`/`produces`. Covered by a test that constructs the case the catalogue cannot.

### C. Chart titles and footers clipped at large type sizes — FIXED

The title is centred half a margin from the top of the canvas and the last footer line half a
margin from the bottom. That is fine while a line of type is shorter than the 56-pixel margin,
and it was, because the ring was capped at 22 pixels and the type with it. A chart sized to
fill the page sets 68-pixel type, and the first thing a reader met was a title with its
ascenders cut off and a footer missing its last line's descenders. The head and foot are now
measured from the font, identical to the old arithmetic wherever a line still fits the margin —
which is every chart that was rendering before this change.

### D. Not fixed, carried forward

* **`TwinModel` exposes only a total height** (`cir/**`), so `value_stack.milestones` still
  interpolates linearly. Unchanged from both predecessors. Not ours to fix.
* **`stitches.Stitch` has no crossing direction** (`cir/**`).
  `PDF_CABLE_DIRECTION_UNSPECIFIED` is still the only problem any catalogue document reports,
  and its test still asserts the field's absence so the finding deletes itself when the field
  arrives.
* **Nothing verifies the PDF against a physically worked sample.** `twin.calibrated` is `False`
  for the whole catalogue and the document says so where it matters. Still the largest
  unmeasured risk in the deliverable.
* **The straight rounds of a basket are described rather than drawn.** This is the right trade
  at 70 rounds and the caption is explicit about it, but a maker who wants to *see* where the
  wall's contrast bands fall has only the written line. A second, coarse "where the bands are"
  strip alongside the wedge chart would close it. Not Launch-0-blocking; recorded so the next
  reader does not have to rediscover the trade.
* **`runtime/release.py` stores a second, illegible chart.** `assets.build` writes a standalone
  `chart.png` beside the PDF and renders it with `render_any_chart(cir, twin,
  ChartSpec(cell_px=26))` — the whole seventy-round disc, the chart the document itself no
  longer prints. One release, two charts, and the one with a URL is the unreadable one.
  `runtime/**` is not this lane's, so the call `publish/pdf.py::chart_image(cir, twin)` exists
  for the integrator and the change is one line:

  ```diff
  --- a/brambleloop/src/brambleloop/runtime/release.py
  +++ b/brambleloop/src/brambleloop/runtime/release.py
  @@
  -    render_any_chart(cir, twin, ChartSpec(cell_px=26)).save(chart_png, format="PNG")
  +    # The chart the customer's document prints, chosen on the size a cell or ring lands at
  +    # on the page. `render_any_chart` at the default spec is the whole piece, which for a
  +    # seventy-round basket is 1.2 mm per ring -- a second chart, and the illegible one.
  +    from ..publish.pdf import chart_image
  +    chart_image(cir, twin).save(chart_png, format="PNG")
  ```

  `render_any_chart` and `ChartSpec` may then be unused imports in that module; check before
  removing, since other call sites in it may still need them.

* **The round chart draws a basket's wall as rings around its base.** With the crop in place
  the customer's chart no longer does this, but `render_round_chart` still will if asked for
  the whole piece — and `listing_assets._chart_frame` asks for exactly that, captioned "every
  round, from the centre out". The listing image is therefore a picture of a 70-round disc
  where the product is a 24-round base with a wall on it. `publish/listing_assets.py` is
  outside this lane's four owned modules; flagged, not touched.

---

## Tests

`tests/test_deliverable_qa.py` — **53 checks** (was 48), all passing.
`tests/test_accessibility.py` — **2 new checks**, all passing.
`tests/test_render.py` — unchanged, passing.

**No check was removed or weakened.** Two existing assertions changed, and both are stronger:

1. `test_no_chart_cell_is_smaller_than_the_brand_allows_type_to_be` no longer skips a chart
   that reports `cell_mm is None` — it asserts the number exists — and its floor rose from
   5.12 mm to 6.90 mm. Strictly stronger on both counts.
2. `test_the_chart_and_its_legend_are_pictures_and_the_document_says_where_the_text_is`
   asserted that a pointer sentence existed. The pointer was wrong. It now asserts that the
   thing pointed at is in the document — a Chart symbols section containing every mark the
   chart draws, after Abbreviations and before the pointer. A sentence can satisfy the old
   assertion while the key is nowhere; it cannot satisfy this one.

Four new checks are proved against an **injected** defect, so they go on being tested after the
live defect is fixed: the legibility floor is shown reporting for a flat chart *and* a round
one by raising the floor; the type-size check is shown failing when `CUE_RATIO` is lowered; the
symbol-key check is shown failing when the block is not printed; the palette check is shown
failing on a re-introduced literal.

Suites re-run clean **on the committed tree**, with their check counts:
`test_deliverable_qa` (53), `test_accessibility` (11), `test_render` (6), `test_product_run`
(36), `test_gates` (33), `test_geometry` (44), `test_layout_qa` (16), `test_deliverable` (14),
`test_texture` (25), `test_products` (16), `test_listing_set` (18), `test_listing_schema` (14),
`test_launch0` (50), `test_childrens` (38), `test_acceptance_gates` (23), `test_visual` (10),
`test_mobile` (17), `test_value_stack` (7), `test_bible` (13), `test_teardown_reader`,
`test_quality`, `test_listing_parity_gate`. Zero failing.
`run_tests.sh` was not run — the integrator does that.

## Byte-level notes for the integrator

* **Every flat chart in the catalogue renders byte-identically** except `pressed-flower-motifs`,
  which the raised floor now crops to its repeat. Proved by hashing every chart and legend
  before and after each refactor step.
* **Every round chart changes**, in three ways: the footer sentence is now built from the marks
  present, the head/foot padding is measured from the font, and the three baskets are cropped
  and drawn as one wedge. The hero fabric render (`render_round_fabric`, `plain=True`) is
  byte-identical.
* `publish/listing_assets.py` renders a round chart for listing frame 6 and its bytes change
  with the footer sentence. `test_listing_set` and `test_listing_parity_gate` pass.
* Basket documents lost a page (10 → 9) because the round chart's footer is shorter.
