# W4-PDF1: visual audit of the first customer pattern editions

**Status.** Engine changes, tests and records are on `claude/w4-PDF1`. Nothing was published, and
no Etsy or Railway request was made. These PDFs go first to the independent reviewer and then to
the owner, who will inspect them before any sale.

## 1. What was built

| Edition | Pages | SHA-256 | State |
|---|---|---|---|
| `customer_editions/hexagon-coaster-set-1.2.0/hexagon-coaster-set-1.2.0.pdf` (US, sale) | 13 | `47d07b66b7bd25fcf3789bfff3b1e83489e317e676baf10d3b9ad8ed10da6b19` | final |
| `…/hexagon-coaster-set-1.2.0-uk.pdf` (UK, sale) | 13 | `675107fe739e978437eb1d29d55bcc92b68163a3cbd9309c45f186fca36b83aa` | final |
| `…/NOT-FOR-SALE-hexagon-coaster-set-1.2.0-photo-placeholder-proof.pdf` | 13 | `ac8304e99c2043607f46fcf3750e3cb2001d37d6dd0f4961ed8e0792e85271bb` | proof only |
| `customer_editions/market-basket-small-1.2.0/market-basket-small-1.2.0.pdf` (US, sale) | 13 | `75af1ee5cc2960c6bb125601dfed39fb5ee113eb3e878c5fa74abb238449f412` | final |
| `…/market-basket-small-1.2.0-uk.pdf` (UK, sale) | 13 | `24f6317fe74e4af868d19d490d1f3603e404aec2989d4f88a0a90c06bd1efbc0` | final |
| `…/NOT-FOR-SALE-market-basket-small-1.2.0-photo-placeholder-proof.pdf` | 14 | `e15ae0d3130dc319cc180404a2d337856f616d360e1927ee80cfeed319b25c20` | proof only |

Each folder has a `MANIFEST.json` that holds the following:
- the CIR fingerprint;
- the release hash (`gates.certificate.certify`, granted);
- every file's SHA-256 and page count;
- the engine commit (with a clean-source flag);
- the generation command;
- the SHA-256 of each font;
- the provenance of every figure: its kind, the renderer that drew it, the SHA-256 of the source PNG, and its page.

**Reproduce.** Run
`cd brambleloop && PYTHONPATH=src python scripts/build_customer_editions.py --released 2026-10-27 hexagon_coasters`.
The script renders each file twice and refuses to continue unless the two renders are
byte-identical. The same bytes were also reproduced across separate processes.

**Source releases.**
- `hexagon-coaster-set@1.2.0`: release hash `3754ed17a63b790dc2c04b0f744de3fad34e5893ca69c0ff9f0c7cb41090937b`.
- `market-basket-small@1.2.0`: release hash `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991`.

Both were certified by `certify(cir)`, with no blocking findings. The versions match
LAUNCH_PATH (1.2.0).

## 2. Where every number and picture comes from

| Content | Source (deterministic) |
|---|---|
| Round-by-round instructions and stitch counts | `cir.writer.write_pattern`. Each line is set exactly as written; the layout only styles the label, body and count. `test_every_written_line_reaches_the_page_unchanged` extracts them back from the PDF. |
| Finished size, yarn per colour, tolerance, progress table | the twin (`cir.twin`, `publish.value_stack.milestones`) |
| Gauge, hook, yarn names, colours | the CIR. Yarn is printed as the CIR names it ("dk cotton (dk)"); fibre comes from `fibres_named`. |
| Abbreviations, notation, techniques | `publish.abbreviations`. The new `TECHNIQUES` entries are templated through the stitch registry, so the UK edition says "double crochet". |
| Tips | `publish.tips`. Each tip is switched on by a feature of the compiled pattern, and every number in it is read from the twin, the compiler or the gauge. |
| Cover, gallery and schematic images | `visual.disclosed_render.render`. The pixels letter their own disclosure. The figure record's SHA-256 is the renderer's own frame (`test_the_disclosed_renders_are_the_renderers_own_frames`). |
| Construction diagrams beside the rounds | `publish.construction_diagrams.stages`. These reuse the disclosed renderer's geometry: one tile per twin cell, a rose outline on the newest round, and early rounds enlarged up to 2.5×. The page says all of this. |
| Chart, legend | `publish.charts` |
| Licence | `commerce.terms` |
| AI disclosure | `pdf.AI_DISCLOSURE`, plus `platform_policy.DISCLOSURES["deterministic_render"]` |
| Image statement | built on `render_contract.DISCLOSURE` |
| Physical-test status | `twin.calibrated`. It is stated as a fact about this edition: "unverified in this edition". There is no fixed claim about samples elsewhere. |
| Logo | the owner's canonical artwork (`brand.canonical_assets`, D-FB-17), resampled to 300 dpi at the size it is placed |

There is no photograph in any sale edition. The proof variant has dashed boxes labelled
PLACEHOLDER, and its cover is marked "NOT FOR SALE".

## 3. Page-by-page visual audit: hexagon-coaster-set 1.2.0

Every page of the US and UK editions was rendered at 100 dpi, and each page was inspected with
the Read tool. The proof was checked at 70 dpi on its cover and gallery; the other pages are
identical to the US edition. The table records the final state and what was fixed along the
way. Iterations v1–v7 are summarised in §6.

| Page | Content | Checked | Result |
|---|---|---|---|
| 1 | Cover: owner artwork in a framed plate; title; "Crochet pattern · US/UK terms · version 1.2.0"; "Makes 4 coasters"; hero render (4 coasters) with the in-pixel disclosure and an italic caption; forest band with skill, size, yarn and hook; folio | clipping, contrast of the folio on the forest band, logo edge, title fit | Clean. Fixed earlier: the folio was grey on forest (illegible), and the logo's paper read as a stray rectangle (now a deliberate frame). The proof's banner overlapped the frame (moved). |
| 2 | Overview (4 sentences built from the CIR); At-a-glance panel with 10 icon rows; "About this pattern" box (AI, pictures, physical testing) | wrapping, panel overflow, redundant wording | Clean. Fixed earlier: the box spilled onto its own page; "hexagonal coasters: hexagon," was redundant; a lowercase start after the bold lead-in; a clumsy closing sentence. |
| 3 | How it is made: the construction sentence; the scale render with dimension line and in-pixel measurements; the measurements column | image size, column overflow | Clean. White space below is accepted, not padded. |
| 4 | Materials: two yarn cards (drawn ball in the CIR colour, letter A/B, amounts for all 4); hook and notions with icons; how much yarn per colour (for all 4 and for each one); substitution | card text against the drawn tail, icon alignment | Fixed: the icon/label overlap, and text running into the yarn-ball tail. |
| 5 | Gauge: 4 numbered check steps (the 4th uses the round-3 milestone); round-gauge note; progress table | badge contrast | Fixed: white on rose was 3.9:1; the badge is now on rose_deep. |
| 6 | Abbreviations, how to read a row, techniques used (5) | typography | Fixed: "--" in the Rnd gloss (em dash at source). |
| 7 | Instructions: the writer's header panel; diagram note; "Coaster (make 4)"; join line; 7 cards, one per round, each with its diagram and the count in rose | counts split across lines; card overflow; header truncation | Fixed: "(42 / sts)" split across lines (counts are now unbreakable); **a header line was silently cut to its first wrapped line** (a real truncation bug: lines are now wrapped in full, and overflow elsewhere is reported as `PDF_TEXT_DOES_NOT_FIT`); in UK the Rnd 7 card orphaned onto the next page (tightened). |
| 8 | Finishing (the writer's lines, bulleted), then Tips (4 of 7 cards) | orphaned headings | Clean |
| 9 | Tips (3 cards) | – | Clean; lower two-thirds empty (accepted) |
| 10 | Chart (round chart, placed at the size its legibility floor was measured at) | caption/chart fit | Fixed: a blank page appeared because the caption pushed the chart over a page. The caption now goes below the chart when both cannot fit, and the chart is never shrunk below its floor. |
| 11 | Chart caption (continued), legend image, chart symbols, colour key | legend terminology | **Fixed:** the UK legend said "inc single crochet increase (UK double crochet increase)" while the UK text says `dc inc`. The legend is now keyed in the edition's own terminology. |
| 12 | Gallery: hero (set of 4) and detail, side by side, captioned as renderings | sizing | Fixed: the hero was too small with the detail orphaned onto a new page. |
| 13 | Terms and support: licence bullets; legal-review note; customer support; support scope; about this document; typefaces; ©; release table; page-count line | `(c)` | Fixed (©) |

**Every page:**
- Running head: brand · title, then terminology · version.
- Footer: ©, the pattern id, and "page N of 13".
- Fonts embedded and subset: Cormorant Garamond, Lora and Work Sans. No base-14 font (`pdffonts`: all `emb yes`).
- No missing glyph and no type below 9 pt. `_Doc.text` checks every string and reports problems; both lists are empty.

## 4. Product data conflicts (requested by the coordinator)

**The CIR itself is not ambiguous.**
- `products/vessels.py:60` declares the small basket's use as `BasketSize("small", "bread basket", …)`.
- The CIR title is "Crochet Hexagonal Bread Basket".

**The conflicts were in the catalogue and copy around it, on this branch's base (`origin/claude/w4-INTEG8-next`):**

| File:line | String |
|---|---|
| `src/brambleloop/products/launch0.py:619-620` | candidate `nursery-nesting-baskets`, title "Nesting Baskets, three sizes" (owns the small CIR as variant "small") |
| `src/brambleloop/products/launch0.py:621-625` | "One pattern, three hexagonal baskets …" |
| `src/brambleloop/products/launch0.py:641-643` | `qualifiers=("nursery",)`, `subcategory="nursery_decor"`, `audience=ch.UNDER_3` |
| `src/brambleloop/creative/emotional_brief.py:440-441` | `nursery-nesting-baskets`: recipient `new_parent`, occasion `new_baby` |
| `src/brambleloop/seo/strategy.py:5, 96-102, 234-235, 279, 351, 358` | "ONE listing, three sizes"; "nesting baskets"; "basket in 3 sizes"; "Hexagon Nesting Baskets Crochet Pattern in 3 Sizes" |
| `src/brambleloop/seo/facts.py:204, 212-213` | "sells the nesting baskets as ONE product in three sizes" |
| `src/brambleloop/seo/shop.py:63` | `nursery-nesting-baskets` in the shop section map |
| `src/brambleloop/store_foundation/preview_sources.py:222` | announcement: "Our first patterns are here: nesting baskets, a textured baby blanket …" |
| `src/brambleloop/creative/audit.py:317` | `nursery-nesting-baskets: hexagon` |
| `origin/claude/w4-LISTING1@5bf9aaf3: manual_listings/market-basket-small-1.2.0/LISTING_PACKAGE.md:26, 31, 38, 90-91, 160, 225, 231-232, 269` | "Nesting Baskets, three sizes"; `('nursery_decor','under_3')`; "… Crochet Pattern PDF \| Nursery \| …"; "intended for children under 3 years"; tags "nursery crochet", "nursery basket" |
| same package, lines 161 and 343 | shot plans styled "with bread or rolls on a set table", alongside the under-3 framing |
| `origin/claude/w4-LISTING1@5bf9aaf3: manual_listings/hexagon-coaster-set-1.2.0/LISTING_PACKAGE.md:104` | "the first photo is an unedited photograph of a set of four coasters made from this exact pattern version". No such photograph exists. It is a template line for the future, and it must not ship as-is. |

**In the customer PDF itself,** before the fix the basket edition carried the full children's
safety block for `nursery_decor` / `under_3`, including:
- "This pattern makes an item intended for children under 3 years …";
- the safe-sleep note.

It came from `launch0.childrens_assignment("market-basket-small")`, not from the CIR. The PDF
module was not hand-edited to remove it. The removal comes from the source correction
(D-W4-OWNER-BASKET-IDENTITY on `claude/w4-LISTING1`, which makes the small basket its own
`hexagonal-bread-basket` candidate with no children's assignment). A preview merge of
`origin/claude/w4-LISTING1@565475dc` gives a basket PDF whose extracted text contains 0 × each of
"nursery", "baby", "child", "nesting", "three sizes" and "under 3". The word "BABY" remains only
as pixels in the owner's logo artwork (the shop's category line "HOME · BABY · GIFTS ·
SEASONAL"); that is not a product claim and the logo is not editable (D-FB-17).

**Coaster: "makes 4".** The CIR backs 4 (`Component.make = 4`). The PDF states it in five places:
- the cover ("Makes 4 coasters");
- the overview ("This pattern makes four hexagonal coasters");
- the pieces row;
- the yarn amounts ("for all 4", plus per coaster);
- the gallery caption ("The set of 4").

`test_the_coaster_document_says_it_makes_four` pins this.

**Terminology and fibre.** Each edition states its terms in four places:
- the cover kicker;
- the running head;
- "Instructions (US|UK terms)";
- the terms table.

`test_each_edition_states_its_own_terminology` pins this. The fibre line reads "DK weight (light),
cotton" or "Worsted weight (medium), cotton", taken from the named yarn ("dk cotton", "worsted
cotton") by `fibres_named`. It does not claim "100%".

## 5. market-basket-small 1.2.0

Built after merging `origin/claude/w4-LISTING1@d11fe80f` (D-W4-OWNER-BASKET-IDENTITY) into this
branch, at engine/merge commit `46921cee`. The release hash is unchanged
(`1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991`), and the certified
pattern text was not touched. The command was
`PYTHONPATH=src python scripts/build_customer_editions.py --released 2026-10-27 basket_small`.
The three files above are byte-identical to the preview built from the WIP merge, and each was
rendered twice with identical bytes.

**Owner ruling (kitchen and home, small size only).** Verified by text extraction
(`publish.pdf.extracted_text`) on all three files: "nursery", "baby", "child", "CPSIA",
"nesting", "three sizes" and "under 3" each occur 0 times. The children's safety page is gone,
because the catalogue no longer assigns the small basket to children. The document's use and
size are the CIR's own: the title "Crochet Hexagonal Bread Basket", and one basket, 16.0 cm
across the points, 13.9 cm across the flats and 8.7 cm tall. "BABY" survives only as pixels in
the owner's logo line, which is the brand artwork and not a product claim.

**Page-by-page (US, 13 pages, 100 dpi; UK checked for terminology).**
1. Cover: angle render showing the inside, the stripes and the base; folio legible on the band.
2. Overview: "one hexagonal basket, base 16.0 cm across the points, 13.9 cm across the flats; 8.7 cm tall"; at-a-glance panel; About box.
3. How it is made: elevation schematic with height and width; measurements column; base plan beside "Rnds 1 to 10: a flat base of 60 stitches". Fixed during QA: "Rnd 1 to 10" became "Rnds".
4. Materials: worsted cotton cards. Fixed: the 3-line description ran into the yarn-ball tail. No blocking pins, correctly, because the writer says not to block the piece flat.
5. Gauge: the round-5 milestone check; the two-gauges note; the 5-row progress table.
6. Abbreviations and techniques.
7. and 8. Instructions: 10 stage cards (base: Rnds 2, 4, 6, 8, 10; wall: each colour boundary at 14, 16, 17, 19, 22). Every count matches the writer (`test_stage_diagrams_match_the_written_counts`).
8. Finishing: "Do not block this piece flat …".
9. Tips: 6 cards, including "Turning the base into the wall" with Rnd 11/14 from the twin. There is no "matching set" tip, because the pattern makes one basket.
10. and 11. Round chart (rounds 1–10, wedges; the grid is now at 3:1 contrast). The caption continues on page 11 under the 2-lines-each-side rule; the legend is in the edition's own terminology.
12. Gallery: hero, plus angle and base views, captioned as renderings.
13. Terms and support.

The proof (14 pages) adds placeholder boxes in the gallery and a "NOT FOR SALE" banner on the
cover; the banner was moved clear of the logo frame.


## 6. Engine changes (`claude/w4-PDF1`)

- **Fonts.** `brand/pdf_fonts.py` and `brand/fonts/pdf/*.ttf` (OFL; bytes pinned by SHA256SUMS
  and refused if changed). Every string goes through `_Doc.text`, which records any missing
  glyph and any type below 9 pt as document problems. The canvas uses `initialFontName`, so no
  base-14 font is referenced.
- **Palette.** The identity palette (`brand.identity_system.ROLES`, D-FB-16/17) replaces the
  superseded `bible` palette in the document. Every text colour goes through `bible.legible` and
  is tested at ≥ 4.5:1 on paper, on surface and on the forest band.
- **Layout.** The sections are:
  - branded cover;
  - overview and the At-a-glance icon panel;
  - "About this pattern";
  - construction section with schematic and measurements (vessels add the base plan), placed before the materials;
  - yarn cards;
  - gauge-check steps;
  - techniques;
  - instruction cards with construction diagrams;
  - finishing;
  - tips;
  - chart;
  - gallery;
  - terms.

  Two supporting changes: widow/orphan control in `para`, and no silent truncation anywhere.
- **New modules.** `publish/construction_diagrams.py` and `publish/tips.py`;
  `abbreviations.TECHNIQUES`, covered by `method_names_no_stitch_literally`.
- **Charts.** The cell and wedge grid is raised to WCAG 1.4.11 3:1 non-text contrast
  (`charts.GRID`). It was 1.3:1, and the basket's rings could not be counted.
  `render_legend(terminology=…)` keys stitches in the edition's own terminology.
- **Gates were extended, not relaxed.**
  - The type-size source check now also reads `FONT_*, <size>` calls.
  - The layout-bounds test reads the embedded faces.
  - The new `tests/test_pdf_premium.py` covers:
    - embedding;
    - glyphs;
    - pinned font bytes;
    - reproducibility;
    - written lines intact;
    - "makes 4";
    - terminology;
    - figure provenance;
    - proof versus sale;
    - physical status;
    - stage counts against the writer;
    - tip triggers;
    - technique localisation;
    - legend terminology;
    - contrast.
- **Regressions found by the suites, and fixed:**
  - the graded garments' "Sizes and fit" and "Care" sections had been dropped (F-761);
  - the disclosed render was being drawn before the children's refusal;
  - the cover kicker in capitals hid "version X" from `visual.contents_frame`;
  - a "Licence" kicker turned the teardown reader's rights mention into a heading;
  - the schematic had to come before the materials (now it does).

## 7. Known weaknesses (not fixed here)

- The chart image is a 72 ppi raster in a monospace face, from the pre-existing `charts.py`.
  It is legible, and measured as legible, but it looks technical next to the rest of the book.
  The coaster's round chart is drawn as circles while the piece is a hexagon. Round numbers
  crowd the V marks of the stacked increases ("V7A").
- There is no photography at all, so the benchmarks' strongest assets (styled product photos,
  process photos) are replaced by diagrams and disclosed renders. That is correct until a
  sample exists, but it is visibly less warm.
- Writer wording, left unchanged because changing it alters the certified text and its hash:
  - "all 2 changes" (coaster) and "all 4 changes" (basket);
  - "carry it loosely up the inside of the join" on a flat coaster, where "inside" is unclear;
  - "Ends to weave in: about 4" reads per piece but does not say so.

  These are recorded for a 1.2.1 writer pass.
- White space is left at the foot of some pages (schematic, tips continuation, gallery) rather
  than filled.
