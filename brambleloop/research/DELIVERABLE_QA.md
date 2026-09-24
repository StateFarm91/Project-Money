# Customer deliverable audit — the pattern PDF

**Date:** 2026-09-24 (UTC) · **Scope:** everything the buyer receives — `publish/pdf.py`,
`publish/charts.py`, `publish/abbreviations.py`, `publish/difficulty.py`,
`publish/value_stack.py`, `publish/substitution.py`, `publish/layout_qa.py`, the release
chain in `runtime/release.py` and `runtime/pipeline.py`, the claims gate in
`gates/asset_truth.py`, and the document reader in `teardown/reader.py`.

**Method:** render the real PDFs (`cloudline-baby-blanket`, `heirloom-cable-blanket`,
`bobble-floor-pillow`, the eleven catalogue designs, the hexagon coaster), extract every
page's text with `pypdf`, and read them as somebody who has paid for them and is trying to
make the thing. Not as the pipeline, which was reporting success throughout.

**Out of scope by ownership:** `src/brambleloop/visual/**` and `src/brambleloop/cir/**` are
owned by the Visual Department and were read, never edited. Two findings below need changes
there and are marked **NEEDS CIR COORDINATION**.

---

## Ranked findings

Ranked by whether the defect stops somebody making the thing they paid for. A defect that
makes the garment un-makeable outranks one that makes it ugly, which outranks a typo.

### 1. A UK-terms document instructs the wrong stitch — FIXED (guard) / NEEDS CIR COORDINATION (root)

`cir/writer._term` localises `sc → dc`, `hdc → htr`, `dc → tr`, `tr → dtr` and the shaping
stitches, and has **no entry for `fpdc`, `bpdc`, `bob`, `cable2x2` or `cable1x1`**.
`write_op` also short-circuits `sk` before the map is consulted, so the `sk → miss` entry
that does exist is never reached.

A UK render of the Heirloom Cable Throw therefore prints `fpdc in next 4 sts`. In UK terms
`fpdc` reads as *front post **double** crochet*, and UK "double crochet" is the stitch a US
pattern calls single crochet — **half the height** of the stitch the pattern was compiled and
measured against. Every post stitch in the fabric would be worked at the wrong height, the
cables would not stand up, and the finished length would be roughly half the stated 129 cm.

Measured, not assumed: `abbreviations.unlocalised("UK")` renders a real op through the writer
and reports `('bpdc', 'fpdc', 'sk')` today. `unlocalised("US")` is empty.

**Fixed here:** `build_pattern_pdf` now refuses to render a document in a terminology whose
stitches it cannot name truthfully, on the same ground as a pattern that fails compilation.
Nothing renders UK terms in the pipeline today, which is why the rule could be set at full
strength — a rule written after the first wrong UK document exists is a rule argued against a
sunk cost.

**Needs Visual:** `_term` should gain `fpdc → fptr`, `bpdc → bptr`, and `write_op` should send
`sk` through `_term`. `publish/abbreviations.TOKENS` already states what each should print,
and the guard relaxes by itself as the writer is fixed.

**Related commercial exposure:** `growth/content.py` publishes "**US or UK terms?** Written in
US terms, with the UK equivalent for every stitch in the key", and a Pinterest pin claims
"Chart and written instructions, US and UK terms." `assets.build` renders `pattern-us.pdf`
only. The claim is not currently supportable and should be narrowed by whoever owns listing
copy.

### 2. A cabled throw was sold, labelled and gated as beginner work — FIXED

`_difficulty` existed **three times**, each with its own copy of the literal
`{"tr", "dc_inc", "dc_dec"}`:

| location | what it decided |
|---|---|
| `publish/pdf.py` (old `_difficulty`) | the word printed on the PDF cover |
| `runtime/release.py:547` | the difficulty claimed on the listing |
| `gates/asset_truth.py:228` | whether an unsupported beginner claim is blocked |

All three were written before post stitches, bobbles and cable crossings entered the registry
in B-080 and none was updated. The Heirloom Cable Throw — front and back post double crochet
with a 2-over-2 crossing on every fourth row — printed **DIFFICULTY: beginner** on its cover,
claimed beginner on its listing, and passed the gate whose stated job is to catch exactly
that, because a cable is not `tr`. Three readings of one stale list agreeing with each other
is not corroboration.

**Fixed:** one ladder in `publish/difficulty.py`, keyed on `cir.stitches.known_codes()`, with
`unrated()` asserted empty so a stitch added without a rung fails a test instead of arriving
as "beginner". `release._difficulty` and `asset_truth` now import it. The throw is
`intermediate`; nothing else in the catalogue changes rung.

### 3. The document had no abbreviation key, and the only key it had could not contain one — FIXED

The shipped PDF defined no abbreviations anywhere in text. The single key in the document was
the **rendered legend image** on the chart page, built from `twin.stitch_types_used` — the
stitches that produced a *cell in the fabric*.

A turning chain produces no cell. A skipped stitch produces no cell. So `Ch 1, turn` and
`sk next st` could appear in the instructions of a document whose only key was structurally
incapable of holding them: a key measured on a sample that cannot contain the broken case.
Being an image, it was also unreadable to a screen reader, unsearchable and unselectable.

Worse, the cable throw's instructions read `cable2x2 over next 4 sts` and `bob in next st` —
internal canonical codes, not abbreviations any maker has ever seen, with no method given for
working them.

**Fixed:** an **Abbreviations** section, a **How to read a row** notation section and a
**Special stitches** section, all driven by the rendered instruction text, with every meaning
taken from `cir.stitches` rather than restated. The legend image stays and the chart page now
points at the text key. `undefined_tokens()` asserts the inverse property — nothing in the
instructions is missing from the key — across every shippable design.

### 4. The stated gauge and the pattern's own finished length described two different fabrics — FIXED

Cloudline states `16 sts x 18 rows = 10 cm in sc` and its own progress table says 88 rows
come to 97 cm — **9 rows to 10 cm**. Both numbers are right: the swatch is plain sc and the
blanket is mostly dc, which `twin._flat_dimensions` correctly accumulates at twice the height.
The document printed one of them, and asserted "the finished size above is computed from the
gauge above".

A maker checking their work at row 22 measures 24 cm where the stated row gauge implies 12.
The only conclusion available to them is that their gauge is catastrophically wrong, and the
cheapest response is to rip out a correct blanket. Same shape on the cable throw: 121 rows,
129 cm, 9.4 rows per 10 cm against a stated 18.

**Fixed:** where the fabric's own row gauge differs from the swatch gauge by ≥10%, the
document prints both, says which to check against what, and says why they differ. Derived from
`twin.height_cm` and the twin's own row count, so it cannot become a second opinion about a
measurement the twin has already made.

### 5. The certified hash does not identify the file the customer downloads — FIXED

`_Doc`'s docstring says the render is fixed so "the hash means what `assets.build` says it
means". `released_on` defaulted to `date.today()` and is printed on the cover, so the bytes
are a function of **when somebody happened to render them**. Artifact storage is not durable,
so a purchased file is re-rendered on demand, and `pipeline.handle_store_publish` renders it
*again* at upload time — the file uploaded to Etsy was never the file whose hash was recorded.

`test_the_same_certified_pattern_renders_the_same_file_every_time` renders three times in one
process on one day: a proof measured on a sample that cannot contain the broken case, under a
docstring asserting the property the code lacked.

**Fixed:** both handlers that render the customer's file — `assets.build`, which records the
hash, and `store.publish`, which uploads the bytes — now pin the document to
`PatternVersion.created_at`. A new test moves the clock (`pdf.date` stubbed to 2030-01-01) to
prove a pinned release renders byte-identical across days and an unpinned one does not, and a
second walks both modules' sources so that a third render site cannot be added unpinned.

### 6. The materials list was the page a buyer takes to the shop, and it listed only yarn — FIXED

No hook, no colourway (it is in the CIR and in the written instructions), no tapestry needle
though the finishing section says to weave in ends, no blocking pins though it says to pin the
piece out damp, no cable needle though the pattern crosses stitches. Every entry now added is
required by a line this document actually contains, so the list cannot drift into a generic
"you will need" block promising tools the pattern never uses.

### 7. The licence had no owner, no date and no pattern id — FIXED

`LICENCE` is a sound paragraph with nothing to attach it to: no copyright notice, no year, no
designer, no release identifier. The support promise ("tell us and we will fix the pattern")
named no route. Now: a copyright line with the release year and holder, the designer, the
release version and date, the `slug@version` pattern id, and a support sentence that names the
shop as the route — which is the only channel this company actually has. Set as prose, not as
a labelled row, so the teardown reader keeps reporting the licence as a mention rather than a
section (that distinction is deliberate and `SELF_TEST_MENTIONS` depends on it).

### 8. A readiness verdict computed from the wrong evidence — FIXED

`teardown/reader.SECTION_CUES["abbreviations"]` counted the phrases `"us terms"` and
`"uk terms"`. This document's instructions heading reads **"Instructions (US terms)"**, so
`reader.self_test()` reported an `abbreviations` section present in a PDF that had none — and
that section list feeds `ready`, the flag that says the laboratory is fit to receive CA$292 of
somebody else's work.

It failed in both directions. The same cue would credit a purchased competitor pattern with a
key they had not written, on precisely the section our own product was missing — so the
category gap was invisible from the outside too. A terminology note is not a stitch key. Cue
removed; `"stitches used"`, `"key to the chart"` and `"symbol key"` added. The self-test now
reports `abbreviations` because the document earns it.

### 9. Small print below the accessibility floor and below the brand's own minimum — FIXED

Measured as contrast ratios on the real palette:

| text | before | after |
|---|---|---|
| `muted` on `cream` (yardage caveat, substitution notes, chart instructions, page numbers) | 4.48 | 4.70 |
| `gold` on `pine` (cover subtitle, 11pt) | 3.65 | 4.61 |

WCAG 2.1 AA for text under 18pt is 4.5. The footer and running head were set at **8pt**
against `bible.TYPOGRAPHY["min_body_pt"] = 9`. The brand palette is untouched — the document
darkens its own ink only as far as it must, so a future palette that is legible on its own
renders exactly as specified. A source-level fixture now fails on any type set below the brand
minimum, because that defect is invisible in a passing render.

### 10. The palette lived in two places, and the brand said it lived in one — FIXED (partly)

`brand/bible.py` says "anything that renders an asset reads from here", and `publish/pdf.py`
held its own copies of the same six hex codes. The customer's document was the one artefact
where the brand was not actually locked. `pdf.py` now reads `bible.PALETTE`.
`publish/charts.py` still holds its own copies — left alone to avoid colliding with the Visual
Department's live work; see *Remaining*.

### 11. Download integrity had no signal a buyer could use — FIXED

The footer said `page 5`, which cannot tell anyone whether their download stopped early. It
now says `page 5 of 8`, the terms page states the document's length, and the file carries an
author, a subject and a `/Lang` catalogue entry (a PDF with no author is "Untitled" in any
library, and assistive software reads the language first).

### 12. Cable crossing direction cannot be stated — NEEDS CIR COORDINATION

`cir.stitches.CABLE_2X2`'s own comment says which two stitches cross in front "is a property
of the stitch rather than prose nobody validated". **The `Stitch` dataclass has no such
property.** A cable held at the front and one held at the back are mirror images in the fabric
and the identical op to every check in this system.

The piece is makeable — every crossing in a pattern is the same operation, so a maker who
picks a side and keeps to it gets cables — but they may run the opposite way from the product
photography. The document now says exactly that and no more;
`PDF_CABLE_DIRECTION_UNSPECIFIED` is returned on `PatternDocument.problems` and audited by
`assets.build`. Picking a side here would print a fact the compiler never checked.

**Needs Visual:** a `crosses: Literal["front", "back"]` field on `Stitch` (or on the op), after
which the document can state it and the finding can be deleted.

### 13. `_times(1)` printed "1 times" — FIXED

"Work it 14 times across and **1 times** up." On a premium product, in the sentence that tells
a maker how to place the repeat.

---

## What was found and not fixed

**`value_stack.milestones` interpolates height linearly.** `height_so_far_cm = height * index
/ total` is a second height model that disagrees with the twin's row-by-row accumulation
wherever rows differ in height — the same "one value in two places" shape as the difficulty
ladder. On today's products the error is small (Cloudline row 1: 1.1 cm printed, 0.56 cm
actual) because only the first row differs, but a pattern with a tall section and a short one
would print a milestone a maker cannot match. Not fixed because the honest fix is to read
cumulative height off the twin, and the twin exposes only a total — that is a small addition
to `cir/twin.py`, which this department may not edit. **Needs Visual:** a per-row cumulative
height on `TwinModel`.

**`publish/charts.py` duplicates the brand palette** (`CREAM`, `PINE`, `INK`, `MUTED`, `LINE`)
and the legend's text is baked into pixels. Left alone to avoid colliding with the Visual
Department's live work on chart rendering. Two follow-ups for whoever owns it: read
`bible.PALETTE`, and check the legend's own text contrast the way `pdf.contrast` now does.

**The repeat chart can be a sliver.** Cloudline's detected repeat is 9 stitches by 88 rows, so
the "one repeat" chart is a 1:10 strip scaled to fit the page height — about 2.8 mm per cell.
Legible, barely. A repeat whose aspect ratio is extreme should probably be charted as a few
repeats across rather than one. Chart layout is Visual's.

**`value_stack.print_safety`'s warning hardcodes "two of these colours"** regardless of how
many merge. Cosmetic; left for the owner of that requirement.

**Nothing verifies the PDF against a physically worked sample.** Every measurement in the
document is modelled. `twin.calibrated` is `False` for the whole catalogue, and the document
says so where it matters (the yardage tolerance). That is honest, and it is still the largest
unmeasured risk in the deliverable.

---

## Tests

`tests/test_deliverable_qa.py` — 22 checks, all passing. Each states what it measures and
why, and the ones pinning a defect say which module owns the fix. Suites re-run clean after
the changes: `test_deliverable_qa`, `test_teardown_reader`, `test_accessibility`,
`test_texture`, `test_gates`, `test_value_stack`, `test_layout_qa`, `test_product_run`.

No existing check was removed and no threshold was lowered.
