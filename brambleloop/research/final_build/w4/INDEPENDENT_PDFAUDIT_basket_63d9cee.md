# Independent customer-product audit: Hexagonal Bread Basket (small) 1.2.0 customer editions

- **Audited at:** commit `63d9cee` on `claude/w4-PDFAUDIT-basket-63d9cee`. The manifest records engine `46921cee` on `claude/w4-PDF1`.
- **Subject:** `research/final_build/w4/customer_editions/market-basket-small-1.2.0/`: the US sale edition, the UK sale edition, the NOT-FOR-SALE proof and `MANIFEST.json`.
- **Owner ruling checked against:** this is a kitchen and home product, small size only. The PDFs must make no nursery, baby, child, three-size or nesting claim.
- **Method and severity scale:** the same as `INDEPENDENT_PDFAUDIT_coaster_b547434.md` (branch `claude/w4-PDFAUDIT-b547434`).
  - **Medium:** fix before sale.
  - **Low:** fix in the next pass.
  - **Info:** for the record; no fix needed.
- **Auditor:** an independent session. Every claim below was checked against the files, the compiled CIR and the twin.
- **Date:** 2026-10-31 (UTC).

## Verdict: **FIX BEFORE SALE** (text and artwork fixes only)

**What is sound:**
- The pattern arithmetic is correct. The 22 rounds give a flat 60-stitch hexagon base and a straight 60-stitch wall.
- Every printed size and yarn figure agrees with the twin.
- The editions reproduce byte-for-byte.
- The text contains no nursery, baby, child, three-size or nesting claim.
- The disclosures (AI use, renders rather than photographs, no physical sample) are accurate.
- No food-safety claim is made.
- Fonts are embedded. No text is below 9 pt or clipped.

**What blocks sale.** Four of the coaster defects recur unchanged: F2, F3, F4 and F8. There are also three new Medium defects:
- **N1:** the cover's brand logo prints "HOME · BABY · GIFTS · SEASONAL". This is the only place the word "baby" appears in a product the owner ruled must carry no baby claim.
- **N2:** the chart's colour-key note contradicts the page text.
- **N3:** the substitution line reads "1-1 x 100g balls".

None of these is a correctness or honesty failure in the stitch instructions. With the Medium items fixed in a 1.2.1 pass, I would rate the product FIT FOR CUSTOMER.

## 1. Reproducibility: PASS

I ran:

`PYTHONPATH=src python scripts/build_customer_editions.py --released 2026-10-27 --out /tmp/rebuild basket_small`

It completed in a fresh process in 45 s.

| File | Rebuilt SHA-256 | Committed / MANIFEST |
|---|---|---|
| US `market-basket-small-1.2.0.pdf` (13 pp) | `75af1ee5…f412` | match |
| UK `market-basket-small-1.2.0-uk.pdf` (13 pp) | `24f6317f…fbc0` | match |
| Proof `NOT-FOR-SALE-…-proof.pdf` (14 pp) | `e15ae0d3…5c20` | match |

The rebuilt `MANIFEST.json` differs from the committed one only in `engine_commit` and `engine_branch`, which are read from git HEAD at build time. This is the same expected difference as in the coaster audit.

## 2. Pattern correctness, checked as a crocheter would: PASS, with text defects

### Round walk

I compared the US edition (p7–8) with the compiled CIR (`compile_cir(cir_for('basket_small'))`, `ok=True`).

| Rnd | Instruction | Arithmetic | Stated | CIR |
|---|---|---|---|---|
| 1 | 6 sc in magic ring | 6 | 6 | 6 |
| 2 | [inc in next st] x 6 | 6×2 = 12 | 12 | 12 |
| 3 | [sc in next st, inc] x 6 | 6×3 = 18 | 18 | 18 |
| 4 | [sc in next 2 sts, inc] x 6 | 6×4 = 24 | 24 | 24 |
| 5 | [sc in next 3 sts, inc] x 6 | 30 | 30 | 30 |
| 6 | [sc in next 4 sts, inc] x 6 | 36 | 36 | 36 |
| 7 | [sc in next 5 sts, inc] x 6 | 42 | 42 | 42 |
| 8 | [sc in next 6 sts, inc] x 6 | 48 | 48 | 48 |
| 9 | [sc in next 7 sts, inc] x 6 | 54 | 54 | 54 |
| 10 | [sc in next 8 sts, inc] x 6 | 6×10 = 60 | 60 | 60 |
| 11–22 | sc in next 60 sts | 60 | 60 | 60 |

- **The base.** Every base round adds 6 stitches. The increase sits at the end of a repeat that grows by one stitch each round, so the increases stack into 6 corners. This is the standard flat sc hexagon.
- **Colours.** Rounds 15–16 and 18–19 are wine; all other rounds are cream. This gives 4 colour changes at the joins (14→15, 16→17, 17→18 and 19→20), which matches "changes colour 4 times".
- **Twin.** `row_widths` are {6, 12, …, 60, then 60 ×12}, `sides=6` and `shape=vessel`. These match the round walk.

### Size

The gauge is 12.5 sts × 13.8 rows = 10 cm in sc. Each row is 0.725 cm.

- **Across the points.** The Rnd 10 perimeter is 60 / 1.25 = 48.0 cm (twin `circumference_cm` 48.0). Each side is 8.0 cm, so across the points is 16.0 cm.
- **Across the flats.** 16.0 × √3/2 = 13.86, printed as 13.9 cm.
- **Radial cross-check.** 10 rounds × 0.725 cm gives a radius of about 7.25 cm, so about 14.5 cm across. That is within 5% of the across-flats figure, so the base size is internally plausible.
- **Height.** 12 wall rounds × 0.725 = 8.70 cm, printed as 8.7 cm. This agrees with the twin (`width_cm` 16.0, `across_flats_cm` 13.9, `height_cm` 8.7).

**"Checking your progress" (p5).** Every value is consistent:

| Round | Expected | Printed |
|---|---|---|
| 1 | 0.8 cm side, 1.6 cm across | ≈2 cm |
| 5 | 24 cm perimeter, 8 cm across | 8 cm |
| 11 | 0.7 cm tall | ≈1 cm tall |
| 16 | 6 wall rounds, 4.35 cm | ≈4 cm |
| 22 | 8.7 cm | ≈9 cm |

### Wall transition and rim

**Wall transition.** Rnd 11 is a plain sc round worked through both loops (twin cells `loop='both'`). There is no back-loop round and no turning ridge.

The arithmetic is right, but in practice the fabric will cup gradually over 2–3 rounds rather than "rise straight up" (p3). The pattern's own tip (p9) says "by Rnd 14 the wall will be clearly rising", which concedes the point. The real piece will therefore have:
- a slightly smaller flat footprint than 16.0 cm;
- a rounded lower edge;
- a little less than 8.7 cm of vertical wall.

The figures are disclosed as computed, so this is not an honesty failure. See N4.

**Rim.** Rnd 22 is plain sc, then fasten off. There is no finishing edge. That is acceptable for confident-beginner level, but it is the plainest possible rim (see the improvements).

### Yarn

The twin gives `yarn_metres_by_color` = {cream **40.2**, wine **11.9**}, with tolerance 0.20. These are the expected figures.

| Colour | Twin ±20% | Printed (p4) | Agrees |
|---|---|---|---|
| Cream | 32.2–48.2 m | 32–48 m (35–53 yd) | yes |
| Wine | 9.5–14.3 m | 10–14 m (10–16 yd) | yes (rounded) |
| Total | 41.7–62.5 m | 42–63 m (46–68 yd) on p2 | yes |

- **Wine share.** Wine is 4 rounds × 60 = 240 of 1,050 stitches, or 22.9%. Wine's share of the estimate is 11.9 / 52.1 = 22.8%. The two are consistent.
- **Substitution row.** "If you use light: about 60 m" equals 52.1 × 1.15 = 59.9. So the "plus 15%" sentence now sits under the figure it describes, and **coaster F1 is resolved here**. The same row prints "(1-1 x 100g balls)" (N3).
- **Making time.** "about 2.1 hours" for 1,050 sts is about 500 sts/h. That is plausible for sc and is disclosed as an estimate.

### Terminology and legends

- **US edition.** It uses sc and inc ("single crochet increase").
- **UK edition.** I diffed the text layers with sc→dc normalised. Every sc maps to dc and every inc to "dc inc" in all places: overview, gauge, abbreviations, techniques, all 22 rounds, tips, the text chart legend ("V dc inc double crochet increase") and the colophon. No US term leaks into the UK edition, and no UK term leaks into the US edition.
- **Abbreviations.** Every abbreviation used in the instructions is defined on p6.
- **Raster stitch key (p11).** It still defines "x sc single crochet", but the chart draws no x marks (F4).

## 3. Product truth and the owner's ruling: PASS in the text; one artwork defect

| Check | Result | Evidence |
|---|---|---|
| No nursery, baby, child, three-size or nesting claim in the text | PASS | I grepped the text layer of all three files for nurser/baby/child/kid/infant/toddler/three/sizes/nest/stack/"set of": 0 hits. The PDF metadata (Title, Subject, Keywords) is clean. Support (p13) speaks of "the size this pattern states", singular. "Makes one hexagonal basket" (p2). |
| …in the images | **FAIL (N1)** | The p1 brand logo raster carries the tagline "HOME · BABY · GIFTS · SEASONAL" (verified at 250 dpi). This is brand artwork, not a product claim, but it is the word the ruling removes, on the cover. |
| Kitchen and home positioning | Neutral | The text never says "kitchen" or "home". It neither contradicts nor asserts the ruling. The listing copy is out of scope for this audit. |
| No claim of a physical sample or photograph | PASS | p2, p3, p5 and p13 say "computed, not measured" / "Physical testing: Unverified in this edition" (twin `calibrated=False`). p12 of the sale editions says "This edition contains no photographs". Every image is captioned as a digital rendering or a diagram. The proof's p12 placeholder reads "Placeholder for a photograph of a tester's sample. Not for sale." |
| AI disclosure is accurate | PASS | p2 and p13: "created with AI assistance, and every row's stitch count was checked before release". This matches the compiler's clean compile and the certified release. |
| No unsupported food-safety claim | PASS | There is no food-safe, food-contact, washable-for-food, dishwasher or heat claim. "Bread" appears only in the title. The only washing reference is generic end-securing ("in wear or washing", p8). Blocking advice defers to the ball band. |

## 4. Layout: PASS, with minor findings

- **Fonts.** In all three files, every font is an embedded TrueType subset: Cormorant Garamond, Lora and Work Sans. There are no base-14 fonts (`pdffonts`). As with the coaster, every subset carries the tag `AAAAAA+` (Info).
- **Text size and clipping.** I measured the text layer with pdfplumber. There are 0 words below 9 pt and 0 words outside the page box in the US and UK editions.
- **Visual inspection.**
  - I rendered all 13 US pages at 50 dpi as a contact sheet, plus p1–3 at 100 dpi, p1's logo at 250 dpi, and p10–11 of both sale editions at 110 dpi.
  - There are no empty or clipped pages, and no overlapping body text.
  - The instruction cards on p7–8 are clean, and every round has its colour and stitch count.
- **Empty space.**
  - p8 is about 25% empty and p13 about 15% empty. This is acceptable.
  - The chart caption on p10 breaks mid-sentence ("Rounds 11 to | 22 are then worked…") onto p11 (N5).
- **The proof.** It carries "PROOF COPY WITH PHOTO PLACEHOLDERS – NOT FOR SALE" only at the top of p1, the same as the coaster (F9). Its colophon correctly says 14 pages.

## 5. Originality: PASS

- The design is the generic six-increase sc hexagon, extended into a straight-walled vessel and given two wine stripes. This is a mathematical construction that is not ownable.
- The prose, layout, diagrams, chart and renders are all produced by house code from the CIR.
- I found nothing resembling a third-party layout, text or diagram.
- The gate's own caveat from the coaster audit still applies: durable originality evidence (a database corpus or licence review) is unchecked, and wording similarity is unmeasured.

## 6. Tests

`PYTHONPATH=src:tests nice -n 19 python tests/<f>`, run one at a time:

- `test_pdf_premium.py`: 17 OK, 0 FAIL, exit 0.
- `test_deliverable_qa.py`: see the result line appended at the end of this section.

## 7. Recurrence of the coaster findings F1–F10

| Coaster # | Status here | Basket evidence |
|---|---|---|
| F1 orphaned "plus 15%" sentence | **Resolved** | A measurable substitution row (light: about 60 m = 52.1 × 1.15) is printed directly above the sentence. It introduces N3. |
| F2 contradictory ends text | **Recurs (Medium)** | p8: "there is an end to secure at every join and every change", then "carry it … rather than cutting it. Ends to weave in: about 4". There are 22 joins, not 22 ends. The text also never says to cut the wine after Rnd 19, since it is never needed again. Source: `cir/writer.py:247-248`. |
| F3 ch 1 counting | **Recurs (Medium)** | p7: "Join each round with a sl st to the first stitch, then ch 1 to begin the next round." It never says the ch 1 does not count, and the totals depend on that. For 22 joined rounds this is the commonest beginner error. |
| F4 unused "x" in the key image | **Recurs (Medium)** | p11 raster key: "x sc single crochet" (UK: "x dc double crochet"). The chart draws no x marks, while the text key correctly lists only V. |
| F5 round chart for a hexagon | **Recurs (Low)** | p10: the chart is drawn as concentric circles. Round labels fuse with V marks ("V10", "V9" … "V2V"). It uses a monospace raster face. |
| F6 raster text under 9 pt | Not reproduced (Low, watch) | The key note and chart caption read at about 9–10 pt from line pitch at 110 dpi, but in low-contrast grey monospace on cream. |
| F7 "no row gauge" contradiction | **Resolved** | p5 now explains both gauges correctly: stitch gauge for the base, row gauge for the wall. |
| F8 generic "How to read a row" examples | **Recurs (Low)** | p6: "[ … ] x 4 … four times" and "(120 sts)". This pattern uses x 6 and never exceeds 60 sts. |
| F9 proof marked on p1 only | **Recurs (Low)** | The text diff between the proof and the US edition shows only the p1 banner, the p12 placeholder and the page counts. |
| F10 "not yet been through legal review" | **Recurs (Low, owner decision)** | p13. |

## 8. Findings

| # | Page | Sev | Finding | Evidence |
|---|---|---|---|---|
| N1 | p1 (all 3 files) | **Medium** | The cover logo prints the tagline "HOME · BABY · GIFTS · SEASONAL". It is the only appearance of "baby" in a product the owner ruled must carry no baby claim. It is brand artwork from `brand.canonical_assets hero_logo`, so the same tagline is likely on every product cover. Use a tagline-free lockup, or an owner-approved tagline, on product PDFs. | p1 at 250 dpi. The MANIFEST figure source is "owner artwork, exact". |
| F2 | p8 | **Medium** | Contradictory ends text; no instruction to cut the wine after Rnd 19. | See §7. |
| F3 | p7 | **Medium** | It does not say whether the ch 1 counts as a stitch. | See §7. |
| F4 | p11 | **Medium** | The key image defines an "x" mark that the chart never draws. | See §7. |
| N2 | p11 | **Medium** | The colour-key note in the raster says "Each round number on the chart carries its yarn's letter". The chart's round numbers carry no letters, and the text directly below says "no number on it carries a colour letter". The key also lists wine "B", although no charted round (1–10) is wine. | p11 at 110 dpi; `publish/charts.py:150`. |
| N3 | p4 | **Medium** | "about 60 m in total (1-1 x 100g balls)" is a degenerate range. It should read "1 x 100g ball". | `publish/pdf.py:2116` prints `{lo}-{hi}` unconditionally; `substitution.py` returns `[1, 1]`. |
| N4 | p3, p7, p9 | Low | The wall transition has no back-loop or turning round. p3 says the wall rises "straight up", but plain sc cups gradually; the p9 tip concedes "by Rnd 14 the wall will be clearly rising". The footprint, the height and the look of a crisp basket base will fall short of the render. A design change, not an arithmetic one. | Twin cells `loop='both'` on Rnd 11. |
| N5 | p10–11 | Low | The chart caption is split mid-sentence across the page break ("Rounds 11 to" / "22 are then worked…"). | Contact sheet. |
| N6 | p9 | Low | The "line of joins" tip says to keep the seam "on the side that will face down or inward". On a basket the join line runs up the wall, so the advice does not fit this product. Suggest "at the back of the basket". | p9. |
| F5 | p10 | Low | Round chart drawn as circles; labels collide. | See §7. |
| F8 | p6 | Low | Generic x 4 / 120 sts examples. | See §7. |
| F9 | proof | Low | NOT FOR SALE appears on p1 only. | See §7. |
| F10 | p13 | Low | Legal-review sentence (owner decision). | See §7. |
| N7 | p2, p4 | Info | 12.5 sc to 10 cm in worsted cotton on 5 mm is loose for a structural vessel. The wall may not stand unaided; the finishing text already suggests stuffing it with a towel to dry. Substituting DK at this gauge (p4) would be softer still. This is not a defect until a sample is measured. | `calibrated=False`. |
| N8 | all | Info | No food-safety claim is made, and none should be added without evidence. If one is ever wanted, the honest form is "use with a cloth liner"; never "food-safe". | §3. |
| F12/F13 | all | Info | Commonwealth spelling in the US edition, and the `AAAAAA+` subset tags, carry over from the coaster. Neither is an error. | |

## 9. Most valuable quality improvements

1. **Swap the cover lockup for a tagline-free logo on product PDFs (N1).** This is the cheapest way to make the cover literally comply with the ruling on this and every future kitchen or home product. The owner should choose the replacement lockup, because the asset is owner artwork.
2. **One 1.2.1 writer pass for the Medium text defects.** Each is a one-line change, though each changes the certified text and the release hash.
   - F2: "Cut the wine after Rnd 19; carry the cream up the inside of the join."
   - F3: "The ch 1 does not count as a stitch."
   - F4 and N2: emit key entries only for marks and letters the chart actually draws.
   - N3: print "1 x 100g ball" when the range collapses.
3. **Add a back-loop-only Rnd 11, or a sl-st turning ridge** (a CIR change, re-certified). It gives the basket a crisp base edge, makes "rise straight up" true, and makes the render, footprint and height figures honest in practice. It is the single biggest improvement to the physical product.
4. **Finish the rim.** Add a final round of reverse sc or sl st through both loops. This adds structure and a premium look at about 60 stitches of extra yarn.
5. **Redraw the round chart as a hexagon in vector art and the brand typefaces (F5).** The same improvement was recommended for the coaster.
6. **Make and measure a physical sample.** This calibrates the twin and settles whether the wall stands at the stated gauge (N7). It also lets a real photograph replace the proof placeholder.
7. **Mark every proof page NOT FOR SALE (F9). Keep the page-break logic from splitting captions (N5).**

- Interim: `test_deliverable_qa.py` still running at the time of the first push (8 OK, 0 FAIL so far); the final count is added in a follow-up commit.
