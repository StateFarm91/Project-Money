# W4-PDF1: visual audit of the first customer pattern editions

## 00. Basket release 1.3.0 (2026-10-31): back loop only at Rnd 11 (D-W4-OWNER-BASKET-1.3.0)

The owner approved the construction review's §4 fix for the **small** basket only.

**The source change.** `products.vessels.build_basket` works the first wall round of a
`DEFINED_EDGE_SIZES` size ("small") in the back loop:
`Row(11, [Op("sc", 60, loop="back")], 60, "cream")`, with the row note "back loop only: the
unworked front loops make the edge the base folds up along". The small basket's default version
is `SMALL_BASKET_VERSION = "1.3.0"`. The medium and large baskets stay at 1.2.1 with both-loops
walls; they are a held family, outside the approval.

**Validation.** Everything was recomputed, nothing carried over:
- compile, twin and reverse (US and UK) are clean, with no findings;
- `corners` = 6;
- 60 stitches on every wall round and 1,050 in total;
- the twin gives 16.0 × 13.9 × 8.7 cm and 40.2 m cream + 11.9 m wine, unchanged;
- the claims fingerprint is unchanged and the content fingerprint moved. The
  `release_fingerprints.tsv` row was updated with the version bump, by the documented path.

| Release | Release hash |
|---|---|
| `market-basket-small@1.3.0` | `c4aa14a000e5439b0dfb32812039178b5efed6b4ba840efef7e7c64a6b7c659c` |

**Copy.**
- `value_stack.soft_fold` returns None on a back-loop fold, so the 1.2.1 soft-fold wording is gone: no "turning upward over the first few rounds", no "about 8 to 9 cm", and no Rnd 11 "beginning to turn up".
- The PDF states the twin's 8.7 cm, which the twin now models correctly, because the twin's sharp fold is the fold this pattern makes.
- Rnd 11 reads "sc in back loop of next 60 sts" (US) or "dc in back loop of next 60 sts" (UK), followed by "-- back loop only: …".
- A new **Back loop only** technique note is triggered by the text, and the "Turning the base into the wall" tip now describes the ridge and the fold.
- **The renders now draw the shape the pattern makes, so the small basket carries no idealised caption.** The renders were redrawn (846fb89f) after the coordinator's instruction, under the owner rule "never show a shape the product does not have":
  - `render_contract.rim_softening`, which applies to `market-basket-small` only, gives the wall a defined fold at the base and corners that are crisp there and soften toward a rounded rim.
  - Each wall point moves radially from the hexagon toward the circle of the same perimeter, with a weight that is 0 at the fold and grows linearly to `RIM_CORNER_SOFTENING = 0.75` at the rim.
  - **0.75 is a modelling figure.** The review says the rim tends toward the circle, so the figure is backlog until a sample's rim measurement replaces it.
  - **The renderer:** it draws this wall, sizes the frame to the drawn rim, and softens construction-stage diagrams as a fraction of the finished wall's height.
  - **`render_verification`:** it measures the same wall, with tolerances unchanged:
    - per-stitch un-projection on the front face;
    - wall height read on the central column;
    - a new `rim_corners_cm` check across the corners at the top wall round. It expects 2R on a straight prism, so other products are measured as before and gain a check.
  - **The old straight-cornered prism now FAILS verification for this product** on `rim_corners_cm` (hero, scale and angle). Pinned by `test_pdf_premium.test_the_basket_render_draws_soft_corners_and_the_old_prism_fails_verification`.
  - The medium and large baskets and every other product draw as before. The medium and large keep their soft-fold caption.

**Independent reviews of the 1.3.0 renders and design (2026-10-31).** Sources: `INDEPENDENT_SECREVIEW_RENDER_38c1603.md` on `origin/claude/w4-SECREVIEW-RENDER-38c1603`, and `DESIGN_REVIEW_basket_small_1.3.0.md` on `origin/claude/w4-DESIGNREVIEW-basket-1.3.0`.

| Finding | Resolution |
|---|---|
| F1 (HIGH): the caption was removed for an unmeasured shape | `render_contract.ESTIMATED_SHAPE` reads "Rim shape estimated until a sample is made." It appears in:<br>• the PDF: cover second line, About box, schematic caption and gallery;<br>• the listing copy: the new `DISCLOSURES["estimated_shape"]`, added when any disclosed frame carries `manifest["estimated"]`;<br>• the alt text of the hero, scale and gallery-angle frames, all ≤ 250 characters.<br>`export_check` refuses a frame whose note is missing from the alt text or the copy. Nothing claims the shape is measured. |
| F2 (MED): the rim was widened across the flats | `render_contract.soft_radius` now pulls only points outside the same-perimeter circle, so the corners move and the flats stay at the twin's 13.86 cm. The new `rim_flats_cm` check fails the old widening model (test). Measured: hero 13.85 against 13.86. |
| F3: margin | The verifier docstring states what `rim_corners_cm` proves (soft against straight), what it cannot (the 0.75 magnitude), and the margin (prism 3.4 % against a 2 % tolerance). |
| F4: versions | `disclosed-render-contract/3.1`, `disclosed-render/3.1.0` (qualified alongside 3.0.0, which is identical for every other product), `render-verification/3.1.0`. |
| F5: citation | The construction review is cited by branch path in `render_contract`. |
| F6: "rise straight up" | Now reads "turn up at a defined edge to make the wall" (pages 2 and 3). |
| D3: Rnd 11 height | Now reads "about 0.7 cm tall" (`value_stack.milestones`, one decimal under 1.5 cm). |
| D4: TEST PDF date | `quality/tester_kit.py:406` hard-codes `released_on=date(2026, 10, 7)`. That file is W-PHYSFIX's builder, so the fix is the one-line hook below, for integration: `released_on=date.fromisoformat(kit.get("released_on", "2026-10-31"))`. |
| D2: kit fields | These arrive with W-PHYSFIX. The kit is rebuilt after PHYSFIX merges and stays PROVISIONAL until then. |

**Visuals and listing.**
- The shadow release chain was re-run on 1.3.0 (`manual_listings/evidence_PDF1_basket_1.3.0_chain_run.json`).
- Results:
  - `gate.certify` granted;
  - all six listing assets are at 1.3.0;
  - the listing-set certificate is `valid` at release hash `c4aa14a0…`, with DATA_TRUTH, LAYOUT_QA, COMMERCIAL_QA and POLICY_PROVENANCE passed over all eight frames;
  - `store.publish` is dead in SHADOW, as expected.
- The chain's `assets.build` PDFs are byte-identical to the customer editions below.
- **Re-run after the soft-corner change:**
  - the listing-set certificate is still `valid` at `c4aa14a0…`, with all four gates passed;
  - the hero, scale and angle frames are new bytes;
  - each disclosed frame was re-verified from its bytes with `verify_claim` and passed, with `rim_corners_cm` at 15.46 cm against 15.48 cm.

**Editions** (`--released 2026-10-31`):

| File | Pages | SHA-256 |
|---|---|---|
| `customer_editions/market-basket-small-1.3.0/market-basket-small-1.3.0.pdf` (US) | 13 | `fcdded05f60501f1430ce37edac4d18a40c98880ca87b38f46d587887a51a499` |
| `…/market-basket-small-1.3.0-uk.pdf` (UK) | 13 | `dc3f7d6eee587b0f903c0ed08aa30da4cbc7069457ce8991c4d1612b7fd741b5` |
| `…/NOT-FOR-SALE-market-basket-small-1.3.0-photo-placeholder-proof.pdf` | 14 | `f07e0a3517f528202d52c87edb6e1342e59df2668b097345c8d2fe9bdb83abf3` |

**Tester kit (PROVISIONAL** until W-PHYSFIX reaches `claude/w4-INTEG8-next`**):**

| File | SHA-256 |
|---|---|
| `tester_kit/market-basket-small-1.3.0-TEST.pdf` (13 pp) | `48e54525d105687a5079189fca0764aee4eb2eee125503aef64afbbb12b344c6` |
| `tester_kit/market-basket-small-1.3.0-RECORD-SHEET.pdf` (2 pp) | `f8072169eb2dfd2b66b3b2d3002c8288451bdb902d627415b9c1fd3be03b9f29` |
| `tester_kit/KIT_MANIFEST.json` | `9794656d5c53f461c3ee75e3299d67648b293f6266b4ada975f6fc6daa10f009` |

**Superseded.** The basket 1.2.1 editions and kit PDFs are kept in the tree as a record. See
`customer_editions/market-basket-small-1.2.1/SUPERSEDED.md`. The coaster is unaffected and
stays at 1.2.1.

**Visual check.**
- US pages 1, 6, 7 and 9 were checked at 100 dpi: the cover caption, the technique note, the Rnd 11 card with its "after Rnd 14" diagram, and the tip. The page count is unchanged at 13.
- An independent design review follows, and nothing was commissioned.

## 0. Release 1.2.1 (2026-10-31): corrected from both independent audits

This section supersedes the 1.2.0 editions below. They are retired from
`customer_editions/` and kept in the git history.

**Scope of the change.**
- 1.2.1 is a text-only release. Stitches, counts, geometry and yarn figures are all unchanged.
- The basket's base-to-wall design change (N4) is on hold, by owner decision, pending a construction review. `vessels.py` changed only its `RELEASE_VERSION`.
- Both releases were certified through `gates.certificate.certify`.

| Release | Release hash |
|---|---|
| `hexagon-coaster-set@1.2.1` | `83b5db1f2cb4e9d2ce6a8011ed43278d048e4d9b60aaccc7086f0853e599534e` |
| `market-basket-small@1.2.1` | `9251c2ecbba689a1b3caeae1fbb63b9f80d81555ccc9ebdb947a193904f27edf` |

**The editions.** All were built with `--released 2026-10-31`; each folder holds a `MANIFEST.json`.

| File | Pages | SHA-256 |
|---|---|---|
| `customer_editions/hexagon-coaster-set-1.2.1/hexagon-coaster-set-1.2.1.pdf` (US) | 13 | `486374908a883156ba98d5e8ca775c4e097e6747d6a88b2a4cda1a87f941e813` |
| `…/hexagon-coaster-set-1.2.1-uk.pdf` (UK) | 13 | `7de39602b67005a07df4c8503cb342beb4ec916f333006471f0fab606096feec` |
| `…/NOT-FOR-SALE-hexagon-coaster-set-1.2.1-photo-placeholder-proof.pdf` | 13 | `70edfa9e3cd1512f2e5e3b554acf4ffef2ee4db93e672bb0db366cea4c87e357` |
| `customer_editions/market-basket-small-1.2.1/market-basket-small-1.2.1.pdf` (US) | 13 | `60510401f175e97841a57dc4111b2ea7d6144dd88873e5222982810c0eaa43b6` |
| `…/market-basket-small-1.2.1-uk.pdf` (UK) | 13 | `a152c6e8d54c2986dede372edf8ebede661ea011682d315bbacf16bb25151e2c` |
| `…/NOT-FOR-SALE-market-basket-small-1.2.1-photo-placeholder-proof.pdf` | 14 | `30debaae4556bbd8eee954891a489c595065d97ca8a7fb8484a3172d422b2eb5` |

> **PROVISIONAL (2026-10-31).** These 1.2.1 kits do not yet carry the record-sheet fields that W-PHYSFIX added on `claude/w4-PHYSFIX` 29378b85: wall-height method, `base_edge`, `corners_at_rim` and `rim_across_points_cm`. They also lack its one-tester terms. Once PHYSFIX lands in `claude/w4-INTEG8-next` (Batch 4), merge it and rebuild the kits with `tester_kit_coaster.py`. Do not commission a tester from these files.

**The tester kits,** rebuilt by `research/final_build/w4/tester_kit_coaster.py`, bind to the new
content hashes:

| Kit file | SHA-256 |
|---|---|
| basket `…-1.2.1-TEST.pdf` | `28b877ed081654d1b8861f406879b1b38a0aa871f9d8cd6a075649c41a566e6c` |
| basket `…-1.2.1-RECORD-SHEET.pdf` | `7aadefa2f7df848d60ff91910b1b2fc99bbda2388e860e877182179a77abb883` |
| coaster `…-1.2.1-TEST.pdf` | `2992eb1e7edff3b0664e81646fffdacbc3ebdd883937699b8609d6f7cdbff26d` |
| coaster `…-1.2.1-RECORD-SHEET.pdf` | `13451d201e6085296041a16909a8e4f1631ac6567126e375d2ff10e985666bc5` |

**How each audit finding was resolved.** Each fix is pinned by a test in `tests/test_pdf_premium.py`
unless stated otherwise.

| Finding | Resolution |
|---|---|
| F2: ends contradiction, "all 2/4 changes", "up the inside" on a flat coaster | `cir.colour_changes.rounds_instruction` derives the text per colour. A colour whose last round is not the last is cut and fastened off ("Cut wine after Rnd 6" on the coaster, "Cut wine after Rnd 19" on the basket). A resting colour is carried on the wrong side (flat) or up the inside (vessel). Ends are given per piece ("about 4 on each coaster"). "Both colour changes" / "All four colour changes". Turned-row wording is unchanged. |
| F3: whether the ch 1 counts | `writer.JOINED_LINE`: "The ch 1 does not count as a stitch." |
| F7: row-gauge contradiction | The disc gauge note says the row gauge is a swatch check only. |
| F1: orphaned "plus 15%" | The sentence is printed only under substitution metres that are actually printed. On the coaster there are none, so it is absent. |
| N3: "1-1 x 100g balls" | Now "1 x 100g ball". |
| F4 / N2: key does not match the chart | The legend is built from the marks, colours and letters the printed chart actually carries. The coaster key is V only (no x). The basket key is cream only, with no letter note. |
| F5 / F6: chart readability | Charts are drawn as hexagons for stacked-increase pieces. Round numbers sit on plain cells with a cream halo, with no box over a cell. The chart uses the Work Sans brand face. It is embedded at 3× the pixels of the measured rung, with the grid line scaled to match. Legibility is still measured on the 1× rung. |
| F8: generic notation examples | The examples now come from the pattern itself: coaster `[ ... ] x 6` and `(42 sts)`; basket `(60 sts)`. |
| F9: proof marking | "NOT FOR SALE" appears on every page of the proofs. |
| N5: split caption | Chart and schematic captions are kept whole. |
| N6: seam tip | On a vessel the tip now says "turn the basket so the line sits at the back". |
| N1: logo on product PDFs | The cover uses the tagline-free horizontal lockup (`identity_system.lockup_horizontal`). The owner's raster is untouched. |
| F10: legal-review sentence | Kept, because it is true until a legal review exists. |
| N4: base-to-wall transition | On hold, by owner decision. No design change. |
| Construction review F2 (basket copy) | Independent review `CONSTRUCTION_REVIEW_basket_small_1.2.0.md` (verdict on N4: cosmetic, not a defect). "Rise straight up" is gone from the overview and the construction text. It now reads "make the wall, turning upward over the first few rounds and then rising straight", which agrees with the tip. The Rnd 11 checkpoint now reads "the edge of the base beginning to turn up". The checkpoint header no longer blames gauge for the height of the first wall rounds ("judge the height from round 14 on"). |
| Construction review F3 (visual promise) | Captioned, not corrected. The cover, schematic, About box and gallery each say: "These pictures are idealised: they draw a sharp edge where the base meets the wall and corners running straight up it. Worked as written, the base turns up in a gentle curve over Rnds 11 to 14 and the corners soften toward the rim." The cover caption reads "Idealised digital rendering". **The render geometry itself is unchanged**, and that remains open: see the backlog below. |
| Construction review F4 (height) | `value_stack.soft_fold` detects a vessel whose first wall round is worked through both loops. Everywhere the PDF composes a height, it prints the range "about 8 to 9 cm": the range runs from the twin's 8.7 cm upper bound down to one row height (0.725 cm) less. The in-pixel annotation on the schematic render still letters 8.7 cm. The caption under it says that this figure assumes a sharp fold. |

The construction-review fixes are composer text only. `write_pattern` output and the release
hash are unchanged, so these are still 1.2.1. The coaster has no wall and its bytes are
unchanged. Pinned by `test_pdf_premium.test_the_basket_does_not_promise_a_crease_its_instructions_do_not_make`.

**Independent review at 3f80da63 (`INDEPENDENT_SECREVIEW_PDF1_3f80da6.md`: code SHIP, product FIX BEFORE SALE).**

| Finding | Resolution |
|---|---|
| M1: round-chart marks fixed in ink (1.3:1 on the coaster's wine Rnd 6) | `charts.render_round_chart` now draws each mark in `_readable_on(<that cell's colour>)`, on both the polygon path and the sector path. On the coaster, the Rnd 6 marks are cream on wine; checked visually at 150 dpi. The basket's charted Rnds 1-10 are all cream, so its bytes are unchanged. Pinned by `test_pdf_premium.test_every_round_chart_increase_mark_reads_on_its_own_cell`: every mark reaches 4.5:1 against its own cell, and the injected fixed-ink defect fails the test. |
| L1: `pdf._fold` failed open | It now raises `pdf.FoldDisclosureRefused`, so the document is not built without the disclosure. Pinned by `test_the_soft_fold_disclosure_fails_closed`. |
| L2: PIL chart font not sha-pinned | `charts._font` loads the brand face through the new `brand.pdf_fonts.verified_path`, which checks the same SHA256SUMS and raises `FontIntegrityError`. Pinned by `test_the_chart_font_is_sha_pinned`. |
| V1: basket renders draw a crisp prism | **Unchanged, by coordinator instruction.** It waits on the owner's 1.3.0 (back-loop Rnd 11) decision. If that is approved, the pattern will make the shape the render draws. **This blocks sale of the basket.** |

**Backlog from the independent review (recorded, not fixed here):**
- **L3:** the height lower bound (one row height) and "Rnd 14" are heuristics. Replace them with measured values when the first physical record lands.
- **L4:** raster text inside the schematic and render tiles is about 5-7.5 pt. The same disclosure appears beside each tile in live text.
- **L5:** several pages are 50-70 % empty (basket p8/p11, coaster p9/p11).

**Backlog from the construction review (recorded, not fixed here):**
- **F3-geometry.** Draw the soft base edge and the softening corners in `visual.disclosed_render._draw_vessel`. That needs a matching change to `visual.render_verification` (wall-round banding off the front face). The same renderer feeds the listing images, so it belongs to a renderer and listing pass, not this text release.
- **F5 (yardage).** The 22 joining sl st + ch 1 (about 0.85 m) and the woven tails are not counted. That is about 2-3 %, inside the ±20 % band, and the error runs low.
- **F6 (hook).** `creative.prototype.gauge_for` hard-codes `hook_mm=5.0` for every weight. 12.5 sts / 10 cm is a mid-band density, not a structural one. "Whatever hook gets you gauge" and the DK substitution can both produce a soft wall.
- **Kit fields (review §5).** `wall_height_method`, `base_edge` / `wall_vertical_from_rnd`, `corners_at_rim` with `rim_across_points_cm`, and `rnd11_height_cm` are not on the record sheet yet. Adding them is a kit change, and the CA$66 approval would need to be re-read against the new sheet.

**Visual check.** All pages of the US and UK editions of both products, and both proofs, were
rendered at 100/80/50 dpi and inspected.
- The hexagon charts are crisp. No round number collides with a mark.
- Fixed during this pass: the coaster's colour tip still said "up the inside". It is now "on the wrong side at the join".
- The text of all six files contains none of these terms: nursery, baby, child, CPSIA, nesting, three sizes, under 3.

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
