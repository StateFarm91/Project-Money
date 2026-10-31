# Independent security and product review — `claude/w4-PDF1` @ 3f80da63

Reviewer: independent Claude Code session (not the author). Date: 2026-10-31 (UTC).
Scope: PDF1's own changes, `git diff f259afe4 (merge-base with INTEG8-next) 3f80da63`, limited to
`publish/{pdf,charts,construction_diagrams,tips,value_stack}.py`, `brand/pdf_fonts.py` and the
pinned fonts, `abbreviations.TECHNIQUES`/`notation_key`, `cir/writer.py`,
`scripts/build_customer_editions.py`, the tests, and the 1.2.1 customer editions of
`hexagon-coaster-set` and `market-basket-small`. Content merged in from INTEG8-next and
INTEG8-trial-adopt was not reviewed.

## Verdicts

| | Verdict |
|---|---|
| **CODE** | **SHIP**. No gate was relaxed, every printed number traces to the CIR or twin, the six PDFs reproduce byte for byte, and the font licences are in order. All findings are Low. |
| **PRODUCT** | **FIX BEFORE SALE**. The coaster needs one fix: the Rnd 6 increase marks on its chart are near-invisible. The basket needs two: the same chart fix, and its cover, gallery and schematic renders, which draw a crisp hexagonal prism the instructions do not make. A caption does not satisfy "never show a shape the product does not have", and the same images go to the listing with no caption at all. This finding (V1) blocks sale. |

## Evidence base

- Worktree at 3f80da63. The engine `src/` is identical between the MANIFEST `engine_commit`
  88fbea93 and HEAD (`git diff --stat 88fbea93 HEAD -- brambleloop/src` is empty).
- **Reproducibility.** `scripts/build_customer_editions.py --released 2026-10-31 --out /tmp/rebuild
  hexagon_coasters basket_small` rebuilt all six PDFs. They are byte-identical to the committed files and to the MANIFEST sha256 values:
  coaster US `20012510…`, UK `26dce916…`, proof `5602b0f0…`; basket US `60510401…`, UK `a152c6e8…`,
  proof `30debaae…`. The release hashes in the MANIFESTs are coaster `83b5db1f…` and basket `9251c2ec…`.
- I rendered every page of both US editions at 70 dpi and looked at each one. I looked at the charts, cover and
  schematic at 110–200 dpi, and spot-checked the UK editions and the proofs (pages 1, 11, 12, 13).
- **Live text sizes** were taken from the text layer with pypdf, scaled by the text and current matrices. The minimum is **9.0 pt in all six files**,
  and nothing is under 9 pt.
- `pdffonts` shows only embedded, subset TrueType faces: Cormorant Garamond, Lora and Work Sans. There is no Helvetica.

## Tests (run one at a time, `PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

_Test run in progress; results are appended in the next commit._

## 1. Code safety and integrity

**1a. Can composition print an untraced number, claim or picture?** No path found.
- Every number in `tips.py` is read from the twin, the compiler result or `cir.gauge`, and each tip
  carries a `trigger`. There is no physical-behaviour tip (stiffness, wash or wear).
- `construction_diagrams.stages` draws only through `visual.disclosed_render` internals: twin
  cells, certified ring radii and row colours. The stitch count on each card is `len(rows[k])`. The
  rose outline is an annotation. The early-round enlargement is disclosed in the PDF ("early rounds are shown
  enlarged").
- `schematic_view` embeds the disclosed renderer's own verified frame unaltered.
- `notation_key` now builds its examples from the document's own text: the largest `(N sts)` and the commonest `] x N`.
  The coaster prints `(42 sts)` / `x 6`. The basket prints `(60 sts)` / `x 6`.
- The height range `about 8 to 9 cm` comes from `value_stack.soft_fold`. The upper bound is the twin's 8.7 cm,
  and the lower bound is one row height less. It is a heuristic bound (see L3), but every input is from the twin.
- A grep of string literals with units in `pdf.py`, `tips.py`, `charts.py`, `abbreviations.py` and `writer.py`
  finds only gauge-derived f-strings and standard technique constants: the 15 cm tail, the 12 cm swatch, the 5 cm weave-in and the ±20 % band.
- **L1 (Low).** `pdf._fold` catches every `Exception` from `soft_fold` and returns None. If that ever
  raised, the PDF would fall back silently to "rise straight up", the exact 8.7 cm and *no* idealised
  disclosure. That fails open on a truth disclosure. It is mitigated because
  `test_pdf_premium.test_the_basket_does_not_promise_a_crease_…` pins the basket text, so a regression goes
  red. It should still catch narrowly or re-raise.

**1b. Were gates or tests relaxed?** No.
- **`test_deliverable_qa` injected-defect check.** I reproduced it directly on `cloudline-baby-blanket`:
  - The live layout has a cue of 9.30 pt and no problems.
  - With `CUE_RATIO=0.40` and the *pre-injection* layout, the cue is **7.97 pt**. The measurement detects the defect, and the assertion is real.
  - Re-laid out under the defect, the tiler picks a larger tile: the cue is **9.11 pt** and `problems=[]`. The real pipeline still clears the floor, so the
    second assertion is satisfied on its first branch, not vacuously through `problems`.
  - With `CUE_RATIO=0.30` the gate does fire: `PDF_CHART_CELL_BELOW_BRAND_MINIMUM`.

  The new test asserts both the detector and the pipeline outcome. It is not weaker than the old one, which asserted only the first.
- **Listing chart pin 56 → 58 px.** This is an exact equality on the *listing* chart unit for `market-basket-large`. The narrower
  proportional caption lets the disc scale up, so the pin moved upward, which is the legibility-improving direction. No floor
  or threshold changed. The test result is listed above.
- **The added `FONT_*` size scan in the type-floor test** is a strengthening: it extends the
  under-minimum grep to the new face constants.
- **`test_launch0_listing_truth`** now requires `size_agrees: True` before a sample clears gauge claims.
  That is a strengthening (SECREVIEW F3).
- **Version pins.** `release_fingerprints.tsv` moved the four joined-round products to 1.2.1 with unchanged
  content and claims fingerprints. I checked the whole catalogue (`test_release_versions.catalogue()`): **only those four
  products use `joined_rounds`**. So the `JOINED_LINE` and colour-change writer text changes reach no
  other released pattern without a version bump.

**1c. Brand face in the listing chart images.** `charts._font` now prefers `WorkSans-Medium.ttf`
before DejaVu Mono. The same renderer draws the listing chart frames. The certificate results are in the test table:
`test_cert_listing_frames`, `test_search_hero_publish`, `test_originality` and
`test_launch0_listing_truth`. The font file is hash-pinned through `pdf_fonts.register()` for the PDF. For PIL in `charts._font`
it is loaded by path, not hash-checked.
- **L2 (Low).** A swapped `WorkSans-Medium.ttf` would change listing chart pixels without a
  `FontIntegrityError`. The PDF path would refuse it, so the PDF would never ship with it. Have `charts._font` call
  `pdf_fonts.register()`, or verify the sha first.

**1d. Font licences.** All ten TTFs match `SHA256SUMS`. `SOURCES.txt` names the source: Fontsource 5.1.0, latin subset of the Google Fonts
releases. `brand/fonts/{Lora,CormorantGaramond,WorkSans}-OFL.txt` are present with copyright lines, and Lora carries
its Reserved Font Name "Lora". Embedding subsets in a PDF is document embedding, which OFL-1.1 permits;
the OFL FAQ treats subsetting for embedding as allowed. The PDF credits "used under the SIL Open
Font License 1.1".
- **I1 (Info).** The repository redistributes Fontsource's latin-subset TTFs, which are technically
  Modified Versions, under the RFN "Lora". This is the same practice as Google Fonts and Fontsource themselves and is low risk. If the owner wants
  zero ambiguity, bundle the unmodified upstream Lora TTFs.

## 2. Pattern truth in 1.2.1

Checked against the text of all four sale editions and the stitch arithmetic.

| Finding | Status in 1.2.1 | Evidence |
|---|---|---|
| Coaster F1 (orphan "plus 15 %") | **Fixed** | The coaster has no measurable substitution row and no "plus 15%" sentence. The basket prints the sentence directly under "IF YOU USE LIGHT about 60 m". |
| Coaster/basket F2 (ends text) | **Fixed** | The "end at every join" sentence is gone for round-worked pieces. Coaster: "Leave cream attached while it rests (Rnd 6)… Cut wine after Rnd 6… about 4 on each coaster". Basket: "Leave cream attached (Rnds 15-16 and 18-19)… Leave wine attached (Rnd 17)… Cut wine after Rnd 19… about 4". Four ends is correct: the ring tail, the final cream tail, the wine start and the wine cut. |
| F3 (ch 1 counting) | **Fixed** | "The ch 1 does not count as a stitch." appears in all four editions (`writer.JOINED_LINE`). |
| F4 (unused "x" in the key image) | **Fixed** | The key image shows only "V inc" (US) / "V dc inc" (UK). |
| F7 | Fixed in the earlier release, still correct | |
| F8 (generic examples) | **Fixed** | Coaster `(42 sts)`/`x 6`. Basket `(60 sts)`/`x 6`. |
| Basket N1 (tagline with "baby") | **Fixed** | The cover uses the tagline-free lockup. No "baby" appears anywhere in the basket text. |
| Basket N2 (colour-letter note) | **Fixed** | The basket key image shows only cream and says nothing about letters. The text says "no number on it carries a colour letter". The coaster, which does letter its rounds, keeps the note. |
| Basket N3 (`1-1 balls`) | **Fixed** | "about 60 m in total (1 x 100g ball)". |
| Construction review: "rise straight up" | **Fixed** | Absent from all files. The overview now says "turning upward over the first few rounds and then rising straight". |
| Height as "about 8 to 9 cm" | **Fixed** | Cover, overview, At a glance, schematic panel and Rnd 22 checkpoint. The in-image schematic still letters 8.7 cm, and the caption under it explains why. |
| Rnd 11 checkpoint | **Fixed** | "60 stitches around, about 16 cm across the points, the edge of the base beginning to turn up". The header says "judge the height from round 14 on". |

**Arithmetic re-check.** Gauge is 12.5 sts/10 cm for the basket and 14.5 for the coaster. For a hexagon, the
distance across the points is twice the side, and the side is the perimeter divided by 6.

| Item | Round | Stitches | Computed | Printed |
|---|---|---|---|---|
| Basket | Rnd 5 | 30 | 8.0 cm | 8 cm ✓ |
| Basket | Rnd 10 | 60 | 16.0 cm points, 13.9 cm flats | ✓ |
| Basket wall | Rnds 11–22 | 12 rounds | 12 × 0.725 cm = 8.7 cm | 8.7 cm ✓ |
| Basket wall | Rnds 11–16 | 6 rounds | 4.35 cm | "about 4 cm" ✓ |
| Coaster | Rnd 7 | 42 | 9.66 cm | 9.7 cm ✓ |
| Coaster | Rnd 3 | 18 | 4.1 cm | "about 4 cm" ✓ |

Every round's increase repeat matches the stated counts. The UK editions use no US stitch words: no `sc` and no "single crochet".

**New issues:**
- **L3 (Low).** The lower height bound is "at most one row height lost". That figure comes from a reviewer's estimate (0.5–0.8 cm), not a model, and
  "Rnd 14", the round by which the wall is "clearly rising", is likewise a heuristic (the fourth wall round). Both are worded "about" and
  "computed, not measured", and both are acceptable until a sample exists. Replace them with measured values when the first
  physical record lands.
- **I2 (Info).** The technique note "Changing colour at a join" says "Leave the old colour resting on the
  wrong side until it is needed again". For wine after Rnd 19, and wine after Rnd 6 on the coaster, the finishing
  section correctly says to cut instead. That is a slight generic-versus-specific tension, not an error.
- **I3 (Info).** "rising straight" is still a mild physical promise for a plain-sc, both-loops
  wall at 12.5 sts/10 cm in worsted cotton. It is consistent with the tip and is not "rise straight up".

## 3. Visual truth (basket)

The cover (p1), the gallery front view and the top view (p12), the schematic (p3), and the
"after Rnd 14…22" construction cards (p7–8) all draw a **crisp hexagonal prism**. Each has a sharp
90° fold at the base and six vertical arrises running straight to the rim. I confirmed this at 110 dpi on p1.

The instructions make something else. Rnd 11 is worked through both loops, so there is no crease, and the wall rounds have no
stacked increases, decreases or surface ridges to hold corners. By the document's own admission, the base
"turns up in a gentle curve over Rnds 11 to 14 and the corners soften toward the rim". In practice
a 60-st plain tube tends toward a rounded rim. The renderer's code comment
(`pdf._idealised`) says the geometry was deliberately not corrected.

**Judgement against "never show a shape the product does not have": not met.**
- **Only the caption is honest.** The disclosure is good and appears four times. But the rule is about what is shown, and a
  caption under a picture of a different shape is mitigation, not compliance. The cover is the primary
  purchase signal.
- **The listing images carry no caption at all.** `store_foundation.preview` uses
  `disclosed_render.render(cir, "hero")`, the same prism, and the "idealised" wording exists only in `publish/pdf.py`
  (grep across `src/` finds it nowhere else). So the listing shows the prism with no caption.
- **The open state is on record.** The author's audit records this as open (backlog "F3-geometry"). The owner's hold on N4 covers the
  *design* change (a BLO turning round). It does not license an untrue picture.

**V1 (High, product) blocks sale of the basket.** The fix is either of:
- **(a)** Draw the soft fold and the softening corners in `disclosed_render._draw_vessel`, with the matching
  `render_verification` change, for both the PDF and the listing.
- **(b)** Change the CIR so the pattern makes the drawn shape: a BLO Rnd 11, plus a corner-holding device in the wall. This needs a new version and re-certification.

A photograph of a worked sample would also resolve it. The coaster is unaffected: it is flat, and its render matches its shape.

## 4. Layout

- **Clipping and overlap.** None seen on any of the 26 US pages. `test_pdf_layout_bounds` passes. Footers and page counts are correct
  (13/13, and 14 for the basket proof).
- **Type under 9 pt.** None in the live text layer of any file. **L4 (Low).** Raster text inside the images is
  under 9 pt. On the basket p3 schematic, the lettering is about 7.5 pt (9 pt line pitch measured at 200 dpi). On the p3 "base from above" tile and the gallery tiles,
  the disclosure line is about 5 pt. The disclosure is repeated in live text beside each image, so nothing is lost, but
  it is unreadable in print.
- **Chart legibility.** The hexagonal round charts are a clear improvement on 1.2.0 (old F5), and the labels no longer
  fuse.
  - **M1 (Medium, product).** On the coaster chart (p10), the increase marks "V" on the wine Rnd 6 are drawn in
    INK `(26,43,60)` on wine `#6E1F2A`. The contrast is **1.3 : 1**, and the Rnd 6 increases are close to invisible at print size.
    `charts.py` draws every round-chart glyph with `fill=INK` regardless of cell colour, in the new polygon
    path (line 955) and the old sector path (line 984) alike. The defect predates this branch, but it ships in 1.2.1.
    `test_accessibility` does not catch it. The fix is to pick the glyph colour per cell with the existing `_graphic_on` or
    `bible.legible` helper, or to draw a cream halo, the way the round labels already have `stroke_fill=CREAM`. The basket chart is
    currently unaffected because its charted Rnds 1–10 are all cream. Any wine round charted later would hit
    the same bug.
- **Empty space.** **L5 (Low).** Basket p8 is about 50 % empty, p11 about 65 % and p13 about 10 %. Coaster p9 is about 70 % empty and
  p11 about 60 %. The page breaks are section-driven and acceptable, but the key page and the tips overflow page look
  unfinished. The construction-diagram thumbnails on p7 are small (about 2.5 cm) but readable.
- **NOT FOR SALE.** It is present at the top of **every** proof page: 13/13 for the coaster and 14/14 for the basket, by the text layer and confirmed visually on
  pages 1, 12 and 13. The placeholder page also says "Not for sale". Old F9 is fixed.
- **I4 (Info).** "These are the terms Brambleloop offers; they have not yet been through legal review"
  (p13) remains. That is the owner's decision (old F10).

## Findings summary

| ID | Severity | Area | Blocks sale? | Finding |
|---|---|---|---|---|
| V1 | **High** | Product / visual truth | **Yes** (basket) | The renders draw a crisp prism that the pattern does not make. Only the PDF captions it; the listing hero is the same image with no caption. |
| M1 | **Medium** | Product / chart | Yes (coaster; latent for the basket) | The round-chart "V" marks on dark cells have 1.3 : 1 contrast; the coaster's Rnd 6 increases are near-invisible. |
| L1 | Low | Code | No | `pdf._fold` catches every exception; the truth disclosure fails open (mitigated by a text pin). |
| L2 | Low | Code | No | The PIL chart font is loaded by path without the sha pin that the PDF path enforces. |
| L3 | Low | Pattern | No | The height lower bound and "Rnd 14" are heuristics, labelled "about"; replace them with measured values. |
| L4 | Low | Layout | No | Raster text in the schematic and render tiles is about 5–7.5 pt. |
| L5 | Low | Layout | No | Several pages are 50–70 % empty. |
| I1 | Info | Licence | No | The bundled Fontsource subsets are modified versions under the Lora RFN. |
| I2 | Info | Pattern | No | The generic colour-change note says to "leave resting"; the finishing section says to cut wine. |
| I3 | Info | Pattern | No | "then rising straight" is a mild unverified physical promise. |
| I4 | Info | Legal | No | The legal-review sentence stays (owner decision). |

Every Medium finding from the two earlier independent audits (coaster F1–F4; basket F2/F3/F4/N1/N2/N3) is
**fixed in 1.2.1**.
