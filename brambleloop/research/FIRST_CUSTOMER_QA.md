# The first paying customer, working backward from the review they would leave

**Date:** 2026-09-25 (UTC) · **Lane:** C, First-Customer / Deliverable QA
**Predecessors, established and not re-litigated:** `research/DELIVERABLE_QA.md` (2026-09-24),
`DELIVERABLE_QA2.md`, `DELIVERABLE_QA3.md`, `CHILDRENS_STATEMENTS.md` (all 2026-09-25).

**The question.** Three waves of QA have run, so the easy defects are gone. What is left is
what the gates cannot see: the thing that produces a 1-3 star review **while every automated
check reports green**. The journey walked end to end — Etsy listing expectation, purchase,
download, the right files, US/UK terminology, materials, gauge, instructions, charts, the
abbreviation key, accessibility, licence, safety statements, opening the file on a phone, a
tablet and a desktop, working the pattern to completion, and getting help when confused.

**Method.** Render the real PDFs for every design the pipeline can ship, in both
terminologies, including the three nesting-basket variants the earlier catalogue loops leave
out; extract text, fonts, outlines, page boxes and image placements from the **bytes** with
`pypdf`; measure chart geometry with the renderer's own sizing functions; and check every
number the document prints against the twin that produced it. Nothing below is asserted from
a template or from a generator's opinion of itself.

**The pattern in the findings, stated once.** Every defect found in this wave is on a piece
worked **in the round**. That is not a coincidence and it is not luck: the previous three
waves were driven by flat blankets and throws, and every rule they wrote was correct for a
fabric whose rows stack vertically. A basket is a flat base with a cylinder standing on it,
and a coaster is a disc that grows outward and never upward. Four designs work that way — the
three `nursery-nesting-baskets` variants and `hexagon-coaster-set` — which is **two of the
three Launch-0 products, including the flagship**, and **eight documents** once both
terminologies are counted.

**Calibration.** `twin.calibrated` is `False` catalogue-wide. Nothing here claims a physical
measurement, and the one area that needs a worked sample is recorded as unresolved, not
passing.

---

## Findings, with the measurement behind each

### A1. Two of the three Launch-0 products explained their gauge with a stitch they do not contain — FIXED

`publish/pdf.py` printed this whenever a document's fabric row gauge differed from its swatch
row gauge by a tenth:

> Those two numbers are both right and they are not the same number. The swatch gauge is
> measured over plain sc; **this pattern is worked in taller stitches as well**, so its rows
> stack up faster.

Measured against `cir.stitches`, which is where a stitch's height is defined:

| design | gauge stitch | stitches in the fabric taller than it | distinct row heights in the twin |
|---|---|---|---|
| market-basket-small / medium / large | `sc` (h=1.0) | **none** | `[0.5]` |
| hexagon-coaster-set | `sc` (h=1.0) | **none** | `[0.455]` |
| every flat design (15 of them) | `sc` | `dc`, `fpdc`, `bpdc`, `bob`, `cable2x2` (h=3.0) | two |

So the sentence is true of every flat design and **false of all four round ones**, on the page
headed "Gauge, and why it matters here" — the page a careful maker reads to decide whether to
start.

The number beside it was not a row gauge either. `_fabric_row_gauge` was
`len(row_widths) / height_cm * 10`, which on a vessel divides the **total round count** by the
height that only the **wall** rounds produce:

| design | rounds | of which rise | printed "this fabric" | the wall's actual row gauge | stated swatch gauge |
|---|---|---|---|---|---|
| market-basket-large | 70 | 46 | **about 30 rows = 10 cm** | **20.0** | 20 |
| market-basket-medium | 51 | 32 | about 32 rows = 10 cm | 20.0 | 20 |
| market-basket-small | 32 | 18 | about 36 rows = 10 cm | 20.0 | 20 |
| hexagon-coaster-set | 10 | **0** | about 10 rows = 10 cm | *there is none* | 22 |

The basket's wall is worked at **exactly** the stated gauge. There was never anything to
reconcile; the document invented a 50% discrepancy and then explained it with a stitch the
pattern does not use. The coaster's "10 rows = 10 cm" divides a round count by a **diameter**.

**Class A.** A maker who checks their rounds against "30 rows = 10 cm" and finds 20 concludes
their tension is a third out and re-swatches, or rips back. It is the gauge page of the
flagship, and it is wrong in two independent ways at once.

**Fixed** in `publish/pdf.py`:

* `_fabric_row_gauge` now measures **only the rows that stack**. `twin.geometry` already
  separates them: a ring that rises has `rise_cm > 0`, a ring that only widens does not. A
  piece with no rising ring has no vertical row gauge and the function returns `None` rather
  than a number.
* `_taller_than_gauge(cir, twin)` measures the reconciliation paragraph's **premise** against
  `cir.stitches`, and the paragraph prints only when the premise holds.
* `_round_gauge_note` says the useful thing instead, in the piece's own numbers — which gauge
  governs which dimension. The large basket now reads: *"Rounds 1 to 24 grow the base outward
  without adding height, so the 18 stitches to 10 cm in sc is what decides how wide the base
  comes out. The 20 rows to 10 cm is the gauge of the 46 straight rounds above it, which is
  where the height comes from."* Every number read back off the twin.

Every flat document is byte-unchanged except for one word in a shared sentence (below).

### A2. The flagship's progress table put 5.6 cm of height on a flat disc — FIXED

`value_stack.milestones` computed `height_so_far_cm = height * index / total`. Measured
against `twin.geometry.rings[i].axial_cm`, which is the twin's own cumulative height:

| product | milestone round | the document printed | the twin says |
|---|---|---|---|
| market-basket-large | 17 of 70 | **about 6 cm made** | **0.0 cm** — still a flat base |
| market-basket-large | 35 of 70 | about 12 cm made | 5.5 cm |
| market-basket-large | 52 of 70 | about 17 cm made | 14.0 cm |
| market-basket-medium | 12 of 51 | about 4 cm made | **0.0 cm** |
| market-basket-medium | 25 of 51 | about 8 cm made | 3.0 cm |
| market-basket-small | 8 of 32 | about 2 cm made | **0.0 cm** |
| market-basket-small | 16 of 32 | about 5 cm made | 1.0 cm |

The section is headed *"Checking your progress"* and its own paragraph says **"If it does not,
the difference is gauge, and it is easier to fix now than at row 70."** So the document hands
a maker a disc lying flat on the table and tells them it should be six centimetres tall, and
then tells them the discrepancy is their tension.

**Class A**, and the largest single defect found in this wave.

**Two earlier audits recorded this as not fixable here** — "`TwinModel` exposes only a total
height, so the milestones have to interpolate; `cir/**` is not this department's". That is
**true of a flat piece and false of a round one**: `cir.geometry.Revolution` carries
`axial_cm` and `radius_cm` for every ring, and nothing was reading them. The half that could
be closed without touching `cir/**` is closed.

**Fixed** in `publish/value_stack.py` and `publish/pdf.py`: a round piece reports the ring's
own `axial_cm` and `diameter_cm`, the milestone carries `interpolated` so a caller knows which
of the two it holds, and the document prints the measurement a maker can actually take:

> ROUND 17 OF 70 — 102 stitches around, about 18 cm across, still flat
> ROUND 35 OF 70 — 144 stitches around, about 26 cm across and 6 cm tall

The table is also now headed in the pattern's own unit. It said "ROW 17 OF 70" in a document
that numbers every line `Rnd`.

**Still open, class D:** a *flat* piece still interpolates, because for a flat piece the twin
genuinely exposes only a total. On `cloudline-baby-blanket` row 1 that is 1.1 cm printed
against 0.56 cm actual — small, because only the first row differs in height. The fix is a
per-row cumulative height on `TwinModel`, which is `cir/**`. Unchanged from both predecessors,
and now narrowed to the flat case only.

### A3. The abbreviation key told every round-worked buyer the opposite of the instructions — FIXED

`abbreviations.NOTATION` glossed `Rnd` as:

> round -- **worked continuously, not turned at the end** like a row

Every round-worked pattern this company ships is **joined**. Measured on the rendered text of
all eight documents: the cover says `CONSTRUCTION: joined rounds`, and fifteen lines below the
key the instructions say *"Join each round with a sl st to the first stitch, then ch 1 to
begin the next round."*

`cir.writer.construction_lines`' own docstring states why this matters: *"A maker who does not
know whether to join has a different fabric from the one the pattern was validated as: joining
leaves a seam up the side, spiralling does not."* It states it once, at the top of the
component, and the reverse compiler reads it back and checks it. The key was a second copy of
a decision that already had a single source, and the second copy was wrong.

**Class A.** Three statements in one document and two answers, about the one construction
decision the pattern's own author flags as producing a different object.

**Fixed:** the gloss states only what is true of every round pattern and points at the source
instead of answering — *"round -- worked around the piece rather than in turned rows. How each
round is started and finished is stated once, at the top of the instructions."*

### A4. Support sent buyers looking for a column that does not exist — FIXED

`support/concierge.py` answered *"is this in UK terms?"* with:

> The pattern is written in US terms and the stitch key lists the UK equivalent for every
> stitch used, so you can work it either way.

That is the claim `DELIVERABLE_QA2` §2.1 found unsupportable on **four** surfaces and withdrew
from all of them: no key has ever listed equivalents. Since that audit the release chain
renders, stores and attaches **both** documents (`pdf.TERMINOLOGIES`, `runtime/release.py:180`,
`runtime/pipeline.py:630-660`). The listing title, the listing description, the content FAQ and
the Pinterest pin were all corrected. **Support was missed**, and it is the surface that
answers the question directly.

**Class A**, because of the shape of the wrongness: the buyer already owns the UK PDF, and the
answer sends them away to hand-translate a pattern instead. A 2-star review saying "the
listing says UK terms and there aren't any" is the predictable outcome.

**Fixed**, derived rather than restated: the answer is built from `pdf.TERMINOLOGIES` and
`pdf.pattern_filename`, so it cannot drift from what is actually attached.

### A5. The listing's chart was a picture of an object the product is not — FIXED

`publish/listing_assets._chart_frame` carried **both** of the defects `publish/pdf.py` had
already been corrected for, one module over. Flagged as open by `DELIVERABLE_QA3` §D; here it
is measured and closed.

**The round branch** called `render_round_chart` with no block and no wedge — the whole piece.
Measured on the rendered frame, at the size `_chart_frame` pastes it:

| product | rounds drawn | ring on the 2000 px frame | as a share of the frame | after the fix |
|---|---|---|---|---|
| market-basket-large | 70 | **8.2 px** | **0.41%** | **43.2 px** |
| market-basket-medium | 51 | 11.2 px | 0.56% | 50.9 px |
| market-basket-small | 32 | 17.7 px | 0.88% | 59.4 px |
| hexagon-coaster-set | 10 | 44.9 px | 2.25% | 64.3 px |

It was captioned **"every round, from the centre out"** on a product that is a 24-round base
with a 46-round wall standing on it — so the shopper's picture of a nursery basket was a flat
seventy-ring disc, at two pixels a ring once Etsy scales it.

**The flat branch** asked `detect_repeat`, the detector `DELIVERABLE_QA2` §1 established is the
wrong one for eight of the sixteen shippable designs. Measured:

| design | the listing's caption said | the document's chart says |
|---|---|---|
| heirloom-cable-blanket | one repeat · 8 sts × **121 rows** | rows 1-5, then rows 2-5, 29 times more |
| cloudline-baby-blanket | one repeat · 9 sts × **88 rows** | rows 1-16, then rows 9-16, 9 times more |
| chunky-ribbed-scarf | 4 sts × **101 rows** | rows 2-5, 24 times more |
| bobble-floor-pillow | 5 sts × **53 rows** | rows 2-5, 12 times more |
| harvest-table-runner, pet-snuggle-mat, cottage-wall-hanging, mosaic-placemat-pair | 8-9 sts × the whole fabric | rows 9-16 |

A shopper who compares the listing image with the pattern they bought finds two different
charts of one product.

**Class A** for the round case (it is the flagship's chart, and the picture is of the wrong
object); **B** for the flat case (the chart is legible, the caption disagrees with the file).

**Fixed:** `_chart_frame` now calls `charts.round_block` / `charts.wedge_count` and
`charts.row_block` — the same three measurements the document uses — and captions what it
shows in the numbers the written instructions use. `chart_frame_unit_px(cir, twin)` is new and
public: it is the listing's counterpart of `pdf._on_page_cell_mm`, and it exists because the
old defect was invisible precisely for want of that number.

**No legibility floor is asserted, and that is deliberate.** This company has a declared
minimum type size for a printed page (`bible.TYPOGRAPHY["min_body_pt"]`) and **none for a
listing image**, so a pixel floor would be a number chosen rather than derived. What the test
checks instead is that the listing draws the block the document draws — and the document's
chart is already held to a floor derived from the brand's own 9pt minimum, so the listing
inherits a derived floor by construction. The pixel numbers above are recorded as regression
pins, not as a claim that they are legible. **This is weaker than a measured floor and is
stated as such.**

### B1. `sl st` is used in eight documents and defined in none of them — FIXED

The Abbreviations page says, in the document's own words:

> Every abbreviation it uses is below; nothing in the instructions is left to be looked up
> elsewhere.

Scanned across every rendered document for the crochet abbreviations a maker actually meets —
`sl st`, `ss`, `yo`, `rep`, `beg`, `sp`, `blo`, `flo`, `rs`, `ws`, `tog`, `fo`, `mc`, `cc` and
others — **exactly one** appears undefined anywhere in the catalogue, and it appears in all
eight round-worked documents: **`sl st`**.

The mechanism: `abbreviations.TOKENS` is the vocabulary of the **writer's ops**, and
`write_op(Op("slst", 1))` prints `slst`. The slip stitch in these documents does not come from
an op — it comes from `cir.writer.JOINED_LINE`, a hand-written sentence that spells it
`sl st`. The key looked for `slst`, found none and printed no entry; `undefined_tokens` looked
for the same string and agreed the key was complete.

**Class B.** Most crocheters know `sl st`, so this does not stop the piece being made — but it
falsifies the document's own sentence on its own key page, in the product sold as the one with
a complete key, and the check written to prevent exactly this could not see it.

**Fixed:** `abbreviations.EXTRA_SPELLINGS` declares the spellings a document contains that
`write_op` never emits, `stitch_key` prints the entry under the spelling the document actually
uses, and `undefined_tokens` scans every spelling in both vocabularies. Strictly stronger:
nothing that was checked before is unchecked now.

**Root, not ours:** `JOINED_LINE` is also **unlocalised** — the UK document prints `sl st`
where `cir.stitches.UK_TERMS` gives `ss`. Exact diff below. It is harmless in practice (`sl st`
is common in UK patterns and the key now defines it), which is why it is C and not B.

### B2. Support could not answer a question about a round — FIXED

`concierge._ROW_Q` was `\brow\s+(\d+)\b`. Two of the three Launch-0 products are worked in the
round and their documents number every line `Rnd`, so a buyer asking *"how many stitches at the
end of round 24?"* missed the canonical-answer path entirely and fell through to the final
escalation branch. Nothing was wrong with the answer; the question was not recognised.

Measured against `support/service.TARGETS`: that is the difference between the
`canonical_minutes: 5.0` target and the `escalated_hours: 24.0` one, for **every** stitch-count
question about the flagship.

**Class B.** **Fixed:** the pattern matches `row`, `round` and `rnd`, and the answer is worded
in the unit the buyer's own document prints, read off the component's construction.

### B3. Support printed the gauge stitch as a raw canonical code — FIXED

`"Gauge is 18 stitches and 20 rows to 10 cm in sc"`. `cir.gauge.stitch_type` is a canonical
code, which is to say a **US** abbreviation, to a buyer who may be reading the UK file. This is
`DELIVERABLE_QA2` §1's gauge defect — *"`sc` is not a UK abbreviation at all... a UK maker
resolving it against their own vocabulary swatches a treble, three times the height"* — fixed
on the cover and arriving again through support.

**Class B.** **Fixed:** both spellings, resolved through `abbreviations.token`, because support
does not know which of the two files the buyer opened.

### B4. A seven-to-ten page PDF with no bookmarks — FIXED

Read off the real bytes: `/Outlines` absent, `rd.outline == []`, `/PageMode /UseNone`, no
`/StructTreeRoot` and no `/MarkInfo` (reportlab produces an untagged document).

This is the "opening it on a phone and a tablet" step. A maker works with the piece in their
hands and goes back to the chart and the abbreviations repeatedly; with no outline that is ten
pages of scrolling each time, on the device most of them use. It is also the only navigational
structure assistive software has in an untagged PDF.

**Class B.** **Fixed:** `_Doc.heading` bookmarks every section heading at or above
`OUTLINE_HEADING_PT`. The basket's outline now reads *At a glance · Materials · Abbreviations ·
Instructions (US terms) · Chart · Safety notes for a children's item · Terms and support*, and
every entry resolves to a page. The keys are derived from the headings and their order, so the
render is still a pure function of the release — proved by re-render equality in the test, the
property `invariant=1` exists to protect.

### C1. `/Creator: anonymous` in the document properties — FIXED

reportlab's default. In any reader's Document Properties panel the Application field read
**"anonymous"**. Now "Brambleloop Studio pattern compiler". One line, public API.

### C2. `/CreationDate D:20000101000000Z` — NOT FIXED, and why

The same panel says the file was created on **1 January 2000**, while the cover and the terms
page say `RELEASED 2026-09-24`. It is an artefact of `invariant=1`, which is load-bearing: it
is what makes the certified hash mean what `assets.build` says it means.

Not fixed because the only way to set a truthful, still-deterministic date is to overwrite
reportlab's private `PDFDocument._timeStamp` (or to set `SOURCE_DATE_EPOCH` globally, which is
process-wide and unsafe in a test suite). Reaching into a third-party library's internals for a
cosmetic field is a worse trade than the field. Recorded so the next reader does not
re-discover it. **Class C.**

### C3. The basket's chart caption is on one page and the chart on the next — NOT FIXED

Measured from the content streams: `market-basket-large-us.pdf` page 6 carries the "Chart"
heading and 154 words of caption and no image; page 7 carries the chart image alone
(2386×2619 px placed at 180×197.5 mm) and 9 words, which are the running head and the footer.
On a phone or tablet in single-page mode the explanation and the picture are never visible
together. Nothing on either page is false. **Class C**, recorded rather than fixed because the
fix is a layout change to the chart page and this lane's remaining time was better spent on the
wrong numbers above it.

### C4. The large basket's size is 25 cm on the listing and 26 cm in the PDF — NOT FIXED (not ours)

| surface | says |
|---|---|
| `products/launch0.py` candidate variant | "**25 cm** across, 23 cm tall" |
| the twin | 25.5 × 23.0 cm |
| the PDF cover and the listing size frame | "**26** x 23 cm" |

Small, one product only (small and medium agree exactly), and in the buyer's favour. It is a
hand-typed round number in the candidate meeting a rounded one in the renderer. **Class C**,
`products/**`; diff below.

### C5. A vessel's size card was labelled like a flat rectangle — FIXED

`listing_assets._size_frame` drew the piece as a solid block against a 180 cm human bar and
labelled it `26 × 23 cm`. The drawing is defensible — the side profile of a cylinder *is* that
rectangle — but the label made a shopper picture a flat mat 26 cm by 23 cm. The catalogue's own
words for a basket are "25 cm across, 23 cm tall"; the listing image now uses them.

### D1. Nothing verifies any of this against a physically worked sample

`twin.calibrated` is `False` for the whole catalogue. Every measurement in this report, and
every measurement in the document, is arithmetic from a stated gauge. `gates/first_customer`
reports `gauge_and_size_claims: UNRESOLVED / blocks: True` for exactly this reason and that
remains correct. **Unchanged, and still the largest unmeasured risk in the deliverable.**

### D2. `stitches.Stitch` has no crossing direction

`PDF_CABLE_DIRECTION_UNSPECIFIED` is still the only problem any catalogue document reports, and
its test still asserts the field's absence so the finding deletes itself when `cir/**` adds it.
**Unchanged from all three predecessors.**

### D3. The basket's wall rounds are described rather than drawn

`DELIVERABLE_QA3` §D's trade, re-read and **judged correct**. The caption names the rounds, the
stitch count and the colour of every band the picture leaves out, and the alternative — 46
identical rings — costs every ring two thirds of its width. A "where the bands fall" strip
would close it. Not Launch-0 blocking. **Unchanged.**

---

## Cross-boundary diffs — exact, for the owners

### 1. `gates/first_customer.py` — the Launch-0 terminology gate is the vacuous call (**class B for its owner**)

`check_terminology` calls `ab.undefined_tokens(text, terminology)` with no `defined`. That
function's own docstring says what that means: *"Left to default it is derived from `text` ...
and that makes the check vacuous: the key is then a function of the same string, so every token
in the string is in the key by construction."* So the first-customer gate's terminology check
could only ever report PASS on the key-completeness half — and it did, on eight documents that
used an abbreviation their key did not define.

```diff
--- a/brambleloop/src/brambleloop/gates/first_customer.py
+++ b/brambleloop/src/brambleloop/gates/first_customer.py
@@ def check_terminology(cir, docs: dict) -> Check:
     for terminology, doc in sorted(docs.items()):
         text = extracted_text(doc.pdf_bytes)
-        missing = ab.undefined_tokens(text, terminology)
+        # `defined` is the point of this call. Left to default, the key is derived from
+        # `text`, every token in the string is in it by construction and the branch below is
+        # unreachable -- which `undefined_tokens`' own docstring says. Pass the key the
+        # document actually printed, which is what makes the comparison able to fail.
+        missing = ab.undefined_tokens(
+            text, terminology,
+            defined={e.token for e in ab.stitch_key(doc.prose, terminology)})
         if missing:
```

### 2. `cir/writer.py` — a basket is blocked with flat-fabric instructions (**class A for Lane B**)

`finishing_lines` has no shape awareness, so all three nesting baskets say:

> Block the finished piece to 26 x 23 cm: pin it out damp to those measurements, easing rather
> than stretching, and **leave it to dry flat**.

Followed literally on a basket, that pins the walls out and dries the piece as a pancake — the
one instruction in the document that can destroy a finished object. `26 x 23` are a diameter
and a height, not two flat dimensions. This is a "working the pattern to completion" defect and
is the highest-value item on this list for another lane.

```diff
--- a/brambleloop/src/brambleloop/cir/writer.py
+++ b/brambleloop/src/brambleloop/cir/writer.py
@@ def finishing_lines(...)
-    if width_cm and height_cm:
+    # A piece worked in the round into a vessel is not blocked flat. `twin.shape` already
+    # distinguishes them, and "leave it to dry flat" is the one line in this document that
+    # can destroy a finished object.
+    if width_cm and height_cm and shape in ("vessel", "tube", "cone", "dome"):
+        out.append(f"Block the finished piece to {width_cm:.0f} cm across and "
+                   f"{height_cm:.0f} cm tall: damp it, stand it on its base and pack it out "
+                   f"to shape -- a rolled towel or a bowl inside it works -- and leave it to "
+                   f"dry standing, not flat. Those are the dimensions this pattern's gauge "
+                   f"produces.")
+    elif width_cm and height_cm:
         out.append(f"Block the finished piece to {width_cm:.0f} x {height_cm:.0f} cm: pin "
```

`shape` has to reach `finishing_lines`; `build_twin` already computes it (`TwinModel.shape`),
and `publish/pdf._tools_required` keys the blocking-pins entry on the phrase `"pin it out"`, so
the materials list drops the pins by itself once a vessel stops asking for them.

### 3. `cir/writer.py` — `JOINED_LINE` is unlocalised (**class C**)

`"Join each round with a sl st to the first stitch"` is a literal, so the UK document prints
the US spelling; `cir.stitches.UK_TERMS["slst"]` is `ss`. `abbreviations.unlocalised()` cannot
see it because it renders **ops** through the writer and this is prose — the same blind spot as
the method paragraphs in `DELIVERABLE_QA2` §1. Harmless in practice (`sl st` is common in UK
patterns and the key now defines it either way), so it is C.

```diff
-JOINED_LINE = ("Join each round with a sl st to the first stitch, then ch 1 to begin the "
-               "next round.")
+def joined_line(terminology: str = "US") -> str:
+    """No stitch name in a literal. `unlocalised()` renders ops and never sees this line."""
+    return (f"Join each round with a {stitches.term('slst', terminology)} to the first "
+            f"stitch, then ch 1 to begin the next round.")
```

Note this would change what the document prints, so `publish/abbreviations.EXTRA_SPELLINGS`
must keep `sl st` (a buyer's older file still says it) and `cir/reverse.py` must still parse
both spellings.

### 4. `cir/rowcycle.py` — "Repeat rows" in a pattern that has no rows (**class C**)

`describe()` produces *"Repeat rows 59-62 2 more times, ending with row 70"* sixty-two lines
after `Rnd 1`. The reverse compiler parses this sentence, so any change has to keep
`cir/reverse.py` reading both forms:

```diff
-def describe(cycle: RowCycle, final_row_index: int) -> str:
+def describe(cycle: RowCycle, final_row_index: int, *, unit: str = "row") -> str:
     last = final_row_index
     times = "once more" if cycle.repeats == 1 else f"{cycle.repeats} more times"
-    return (f"Repeat rows {cycle.start}-{cycle.end} {times}, "
-            f"ending with row {last}. ({cycle.repeats + 1} repeats of the "
-            f"{cycle.period}-row block in total.)")
+    return (f"Repeat {unit}s {cycle.start}-{cycle.end} {times}, "
+            f"ending with {unit} {last}. ({cycle.repeats + 1} repeats of the "
+            f"{cycle.period}-{unit} block in total.)")
```

### 5. `runtime/pipeline.py` — two of the three Launch-0 products have no CIR route (**class A for its owner**)

Measured: `_engineered_cir("nursery-nesting-baskets")` and `_engineered_cir("hexagon-coaster-set")`
both return `None`. `ENGINEERED` does not list them and `products.builder.CATALOGUE` does not
contain them, so `cir.draft` cannot produce a pattern for either. `cloudline-baby-blanket`
routes fine. Nothing is live, so nothing is wrong today — but the flagship cannot currently be
drafted by the pipeline, and the basket product is three variants under one slug, which needs a
decision about how the variants are delivered in one purchase. **Not this lane's file; flagged
with the measurement rather than guessed at.**

### 6. Already applied, confirmed, no diff owed

`runtime/release.py` now calls `publish.pdf.chart_image` rather than `render_any_chart` at the
default spec (`DELIVERABLE_QA3` §D), and `release.py` passes `childrens=` to
`build_description` (`CHILDRENS_STATEMENTS` §9.6). Both were open in the predecessors and both
are closed in the tree this lane read.

---

## What was measured and found **not** to be a defect

Said with the measurement, because "we looked and it was fine" is worth as much as a finding.

* **Non-embedded fonts.** The PDFs carry `/Helvetica` and `/Helvetica-Bold` as base-14 Type 1
  with no `/FontDescriptor`. That is not a substitution risk introduced by carelessness — it is
  the brand's declared face: `bible.TYPOGRAPHY` is `{"display": "Helvetica-Bold", "body":
  "Helvetica"}`. Every base-14 face is guaranteed present in every conforming reader.
* **Page geometry on a phone.** Every page is exactly 216 × 279 mm with no overflow, no
  landscape page and no content outside the text area; nothing forces horizontal panning
  beyond the ordinary pinch-zoom of any Letter PDF.
* **File names.** `pattern_filename` alone is `pattern-us.pdf`, which would collide in a
  downloads folder — but both upload sites prefix the slug (`{slug}-pattern-us.pdf`), so the
  buyer's file is distinctly named. Not a defect.
* **`/Lang`, `/Author`, `/Subject`, `page N of M`, the document-length sentence.** All present
  in the bytes, as `DELIVERABLE_QA` §11 left them.
* **The licence.** Re-extracted from the rendered PDF and run through `terms.consistency`; one
  source, four surfaces, as `DELIVERABLE_QA2` §2 left it.
* **The children's safety block.** All five required statements present in all eight
  children's documents, each with its source or an explicit statement that it has none, as
  `CHILDRENS_STATEMENTS` §3 left it.
* **`publish/charts.py` and the brand palette.** No literal triples, no local contrast
  arithmetic, as `DELIVERABLE_QA3` §4 left it.
* **The round chart's crop and caption.** Re-measured: the large basket's ring is 6.86 mm on
  the page and its caption names every round, stitch count and colour band the picture leaves
  out. `DELIVERABLE_QA3` §1 holds.

---

## Tests

`tests/test_deliverable_qa.py` — **7 checks added** (53 → 60). `tests/test_accessibility.py`,
`test_render.py`, `test_teardown_reader.py`, `test_listing_set.py`, `test_value_stack.py` —
unchanged and passing.

**No check was removed, weakened or re-pinned.** Two existing behaviours changed and both are
strictly stronger: `undefined_tokens` now scans more spellings in both vocabularies than it did
(nothing it caught before is uncaught), and `stitch_key` prints an entry for any spelling the
document contains rather than only for the writer's token.

**Six of the seven are proved against an injected defect**, so they go on testing after the
live defect is fixed:

| check | the defect, injected |
|---|---|
| progress table | `value_stack._rings_by_row` forced to `None` — the old blindness — and the table claims 5.6 cm on a round the twin measures at 0.0 |
| gauge premise | `_taller_than_gauge` and `_fabric_row_gauge` both restored to the shipped behaviour; the false sentence and "about 30 rows = 10 cm" both come back in the real bytes |
| `Rnd` gloss | the old gloss restored into `NOTATION`; the check fires on a document that also carries the instruction it contradicts |
| abbreviation key | both halves separately — a key that lost the `sl st` entry is reported by the scan, and clearing `EXTRA_SPELLINGS` makes the key lose it |
| PDF outline | `OUTLINE_HEADING_PT` raised above every heading; the outline goes empty, which is the state the file shipped in |
| listing chart | the old `render_round_chart` call, whole-disc, measured beside the new one |

The seventh, the support check, is proved by construction: it asserts the withdrawn sentence is
absent and that both `pattern_filename`s are named, so restoring the old answer fails it.

Suites re-run on the final tree, with their counts: `test_deliverable_qa` **60/0** (was 53),
`test_accessibility` **11/0**, `test_render` **6/0**, `test_teardown_reader` **12/0**,
`test_listing_set` **18/0**, `test_value_stack` **7/0**, `test_product_run` **36/0**,
`test_gates` **33/0**, `test_first_customer_gate` **12/0**, `test_layout_qa` **16/0**,
`test_brand` **23/0**, `test_texture` **25/0**. Zero failing.
`run_tests.sh` was not run — the integrator runs it.

## Byte-level notes for the integrator

* **A flat document's prose changes in two places and nowhere else.** "At these rows the
  **fabric** should measure" became "At these rows the **piece** should measure", because the
  sentence is shared with the round case where "fabric" is the wrong word; and each milestone
  reads "about 49 cm **of fabric** made" rather than "about 49 cm made", because the line is
  now built where the measurement is made rather than restated in the renderer. Both numbers
  are unchanged. Every other flat byte is unchanged except the new `/Outlines` object and the
  `/Creator` string, which change every file in the catalogue.
* **All eight round-worked documents change substantively** — the gauge block, the progress
  table and the `Rnd` gloss. Page counts are unchanged (baskets 10, coaster 7).
* **Every PDF in the catalogue gains an outline and a Creator.** Renders remain
  byte-deterministic for a fixed release date, proved in the suite.
* **`listing_assets` frame 3 and frame 6 change bytes** for round products; frame 6 changes for
  the eight flat designs whose repeat detector differed. `test_listing_set` and
  `test_product_run` pass.

---

**Standing rules.** `BRAMBLELOOP_PHASE=shadow` throughout. **CA$0.00 spent**, no model call,
no image generation, nothing published, nothing deployed. Committed on the lane's branch;
**not pushed and not merged**. No existing check was weakened. **No physical calibration is
claimed anywhere** — `twin.calibrated` is `False` catalogue-wide and every number in this
report is arithmetic from a stated gauge.
