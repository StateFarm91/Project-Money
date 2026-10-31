# Independent customer-product audit: Hexagon Coaster Set 1.2.0 customer editions

- **Audited at:** commit `b547434` on `claude/w4-PDFAUDIT-b547434`. The engine is `b93ce931`. `src/` and `scripts/` are unchanged between the two.
- **Subject:** `research/final_build/w4/customer_editions/hexagon-coaster-set-1.2.0/`. It contains the US sale edition, the UK sale edition, the NOT-FOR-SALE proof and `MANIFEST.json`.
- **Auditor:** an independent session. I did not rely on `PDF1_VISUAL_AUDIT.md`. Every claim below was checked against the files, the CIR and the twin.
- **Date:** 2026-10-31 (UTC).

## Verdict: **FIX BEFORE SALE** (minor fixes only)

The pattern is correct. A crocheter who follows either edition gets a flat six-cornered hexagon with the stated stitch counts. The editions reproduce byte-for-byte. Product-truth disclosures are accurate. Fonts are embedded, and no page is empty or clipped.

Nothing found is a correctness or honesty blocker. However, a few customer-facing text defects are cheap to fix and would cause confusion or support questions:
- an orphaned and misleading "plus 15%" sentence;
- a contradictory note about ends;
- no statement that the ch 1 does not count as a stitch;
- an unused "x" symbol in the chart key image.

These belong in a 1.2.1 pass before listing. With F1–F4 fixed, I would rate the product FIT FOR CUSTOMER.

## 1. Reproducibility: PASS

I ran:

`PYTHONPATH=src python scripts/build_customer_editions.py --released 2026-10-27 --out /tmp/rebuild hexagon_coasters`

It completed in a fresh process in 23 s.

| File | Rebuilt SHA-256 | Committed / MANIFEST |
|---|---|---|
| US `hexagon-coaster-set-1.2.0.pdf` | `47d07b66…6b19` | match |
| UK `hexagon-coaster-set-1.2.0-uk.pdf` | `675107fe…83aa` | match |
| Proof `NOT-FOR-SALE-…-proof.pdf` | `ac8304e9…71bb` | match |

The rebuilt `MANIFEST.json` is identical to the committed one in every field except `engine_commit` and `engine_branch`, which come from git HEAD at build time. Those two fields are the only difference.

## 2. Pattern correctness, checked as a crocheter would: PASS, with text defects

**Round walk.** I compared the US edition (p7) with the compiled CIR rows.

| Rnd | Instruction | Arithmetic | Stated | CIR |
|---|---|---|---|---|
| 1 | 6 sc in magic ring | 6 | 6 | 6 |
| 2 | [inc] x 6 | 6×2 = 12 | 12 | 12 |
| 3 | [sc 1, inc] x 6 | 6×3 = 18 | 18 | 18 |
| 4 | [sc 2, inc] x 6 | 6×4 = 24 | 24 | 24 |
| 5 | [sc 3, inc] x 6 | 6×5 = 30 | 30 | 30 |
| 6 (wine) | [sc 4, inc] x 6 | 6×6 = 36 | 36 | 36 |
| 7 | [sc 5, inc] x 6 | 6×7 = 42 | 42 | 42 |

- Every round adds 6 stitches, and the increase falls at the end of each repeat. In each round the repeat is one stitch longer, so the increases stack directly above the previous ones. That is the standard flat-hexagon construction for sc: 6 increases per round lies flat.
- The twin's `row_widths` are {6, 12, 18, 24, 30, 36, 42}, with `sides=6`. These match.

**Gauge and size.** The gauge is 14.5 sts/10 cm in sc.
- The Rnd 7 perimeter is 42 / 1.45 = 28.97 cm. Each side is therefore 4.83 cm.
- Across the points: 2 × 4.83 = 9.66 cm, printed as 9.7 cm.
- Across the flats: 9.66 × √3/2 = 8.36 cm, printed as 8.4 cm.
- These agree with the twin (`across_points_cm` 9.7, `across_flats_cm` 8.4, `circumference_cm` 29.0).
- I also checked the size radially using row gauge: 7 rounds × 0.625 cm gives a radius of about 4.4 cm, so about 8.75 cm across. That is within 4% of the across-flats figure, so the size is internally plausible.
- The "Checking your progress" values on p5 are all consistent with this geometry: Rnd 1 ≈ 1.4 cm, Rnd 3 ≈ 4.1 cm, Rnd 5 ≈ 6.9 cm, Rnd 7 ≈ 9.7 cm (printed as "about 10").

**Yarn.** The twin gives `yarn_metres_by_color` = {cream 22.6, wine 6.2} for all 4 coasters, with tolerance 0.20.

| Colour | Twin estimate ±20% | Printed | Agrees |
|---|---|---|---|
| Cream | 18.1–27.1 m | 18–27 m | yes |
| Wine | 4.96–7.44 m | 5–7 m | yes |
| Total | 23.0–34.6 m | 23–35 m | yes |
| Per coaster, cream | 4.5–6.8 m | 4.5–6.8 m | yes |
| Per coaster, wine | 1.2–1.9 m | 1.2–1.9 m | yes |

- Wine is used only in Rnd 6. That round is 36 of 168 stitches per coaster (21%), and wine's share of the yarn estimate is also 21%. The two are consistent.

**Terminology.**
- The US edition uses sc and inc ("single crochet increase").
- The UK edition maps every sc to dc and every inc to "dc inc" in all places: overview, gauge, swatch, abbreviations, techniques, all 7 rounds, the tips, the text chart legend and the raster legend image (p11, checked at 110 dpi).
- No US term leaks into the UK edition, and no UK term leaks into the US edition.

**Abbreviations.**
- Every abbreviation used in the instructions is defined on p6: ch, inc / dc inc, sc / dc, sl st, st/sts, Rnd and magic ring.
- No abbreviation is used without a definition.
- One abbreviation, "x", is defined in the key image but never used (see F4).

## 3. Product truth: PASS

| Check | Result | Evidence |
|---|---|---|
| No claim that a physical sample exists | PASS | p1, p2, p3, p13 all say "computed, not measured" / "Physical testing: Unverified in this edition". The twin has `calibrated=False`. No text claims a sample was made, photographed or tested. |
| AI disclosure is present and accurate | PASS | p2 and p13: "created with AI assistance, and every row's stitch count was checked before release". Certification ran compile and reverse; confidence scores are arithmetic 1.0 and instruction 1.0. |
| Every image is a disclosed render or a placeholder | PASS | p1, p3 and p12 are renders, each captioned "Digital rendering … not a photograph". p7 shows construction diagrams. The p10 chart is labelled as a chart. In the proof, the p12 placeholder is labelled "Placeholder for a photograph of a tester's sample. Not for sale." p12 of the sale editions says "This edition contains no photographs". The proof correctly omits that sentence. |
| "Makes 4" is consistent | PASS | It appears on p1 ("Makes 4 coasters"), p2 ("four hexagonal coasters", "4 coasters"), p4 (yarn quantities "for all 4" plus a per-coaster figure), p7 ("Coaster (make 4)"), p9 ("makes 4 coasters") and p12 ("The set of 4"). The CIR has `make=4`. |
| No unsupported safety or material claims | PASS | There is no heat-resistance, food-safe, washability or child-safety claim. "Cotton" comes from the CIR material name, `dk cotton`. Blocking advice defers to the ball band. |

## 4. Layout quality: PASS, with minor findings

- **Fonts.** In all three files, every font is an embedded subset: Cormorant Garamond, Lora and Work Sans. There are no base-14 fonts. (Checked with `pdffonts`.)
- **Text size and clipping.** I measured the text layer with pdfplumber. There are 0 words below 9 pt and 0 words outside the page box in the US and UK editions.
- **Visual inspection.** I rendered all 39 pages at 60 dpi, and p7, p10 and p11 at 110–150 dpi.
  - There are no empty pages.
  - There is no clipped or overlapping body text.
  - The cover, overview, materials and instruction cards are clean and well-aligned.
  - p9 is about half empty and p11 about 40% empty. This is acceptable.
- **The proof** carries "PROOF COPY WITH PHOTO PLACEHOLDERS – NOT FOR SALE" only at the top of p1. The interior pages carry no mark (see F9).

## 5. Originality: PASS (with the gate's own caveat)

- `certify()` passes the originality stage. It reports one WARNING: `ORIGINALITY_DURABLE_EVIDENCE_UNCHECKED` (no database corpus or licence review).
- `originality.compare()` against both code benchmarks gives `clear` on numeric, features and construction. Wording is `unmeasured`, because no benchmark wording fingerprint has been captured.
- The design is the generic six-increase sc hexagon, a mathematical construction that is not ownable.
- The prose, layout, diagrams and chart are all generated by house code.
- I found nothing resembling a third-party layout, text or diagram.

## 6. Tests

`PYTHONPATH=src:tests nice -n 19 python tests/<f>`, run one at a time:

- `test_pdf_premium.py`: 17 OK, 0 FAIL, exit 0.
- `test_deliverable_qa.py`: 57 OK, 4 FAIL, exit 1. All 4 failures are `ModuleNotFoundError("No module named 'sqlalchemy'")`, which is an environment gap in this container, not a product defect:
  - `test_every_place_that_renders_the_customer_pdf_pins_its_date`
  - `test_every_place_that_ships_the_customer_pdf_ships_every_terminology`
  - `test_support_does_not_send_a_buyer_looking_for_a_column_that_does_not_exist`
  - `test_the_pdf_the_listing_and_the_gate_read_one_difficulty_ladder`

  These four are **unverified** here.

## 7. Findings

Severity scale: **Medium** (fix before sale), **Low** (fix in next pass), **Info**.

| # | Page | Sev | Finding | Evidence |
|---|---|---|---|---|
| F1 | p4 (US/UK) | **Medium** | The orphaned and misleading sentence "Those metres are this pattern's own estimate plus 15%." No substitution metres are printed: `guide["how_much"]` rows are all non-measurable, so nothing is shown. The reader can only connect the sentence to the Materials figures. Those figures are the twin estimate ±20%, with no +15% margin. A buyer may therefore think a buffer is already included and buy too little. Not noted in the author's audit. | `publish/pdf.py:2125-2129` prints the sentence unconditionally inside the substitution block, whether or not any `how_much` row was printed. |
| F2 | p8 | **Medium** | Contradictory finishing text. One line says "there is an end to secure at every join and every change". The next says to carry the colour rather than cut it, with "about 4" ends. There are 7 joins per coaster, so "every join" is wrong. Also, "carry … the colour not in use" does not tell the maker that the wine yarn is cut after Rnd 6, because it is never needed again. | `cir/writer.py:247-248`, `cir/colour_changes.py:89`. The author's audit lists only the "all 2 changes" wording. |
| F3 | p7 | **Medium** | The pattern never says whether the "ch 1 to begin the next round" counts as a stitch. The stitch totals only work if it does not, and this is the most common beginner error in joined rounds. The pattern is rated "confident beginner". | p7 round header: "Join each round with a sl st to the first stitch, then ch 1 to begin the next round." |
| F4 | p11 | **Medium** | The raster stitch-key image defines "x sc single crochet" (UK: "x dc double crochet"). The chart draws no "x" marks: plain cells are blank. The text key on the same page correctly lists only V. A buyer will look for x marks that do not exist. | p11 key image compared with the p10 chart at 110 dpi. |
| F5 | p10 | Low | The chart is hard to read. It is drawn as concentric circles although the piece is a hexagon. Round labels collide with V marks ("V7A", "2AV"). The "6B" label box covers a cell. It is rendered in a monospace face at about 72 ppi. | p10 at 110 dpi. The author's audit records this under §7. I agree, but rank it higher than the author does, because the chart is the second way a buyer checks the pattern. |
| F6 | p10–11 | Low | Raster text in the chart and key is effectively about 8 pt, in grey on cream. This is below the 9 pt floor. The text-layer test cannot see it, because it is pixels. | Chart caption and the key's grey note, measured from line pitch at 110 dpi. |
| F7 | p5 | Low | "There is no row gauge to check it against" contradicts the stated gauge (14.5 sts **x 16.0 rows**) and swatch step 2 ("up 10 cm for 16 rows"). | p5 text. |
| F8 | p6 | Low | The generic "How to read a row" examples, `[ … ] x 4` "four times" and `(120 sts)`, do not match this pattern, which uses x 6 and never exceeds 42 sts. | p6. |
| F9 | proof, p2–13 | Low | The NOT-FOR-SALE mark appears only at the top of p1. Pages extracted from the proof would carry no mark. This is internal-only, so the risk is low. | Text diff between the proof and the US edition: the only additions are the p1 banner and the p12 placeholder. |
| F10 | p13 | Low | A sale edition prints "These are the terms Brambleloop offers; they have not yet been through legal review." The statement is honest, but it signals an unfinished product to the buyer. This is an owner decision: have the terms reviewed, or keep the sentence. | p13. |
| F11 | p2, p4 | Info | Gauge plausibility: 14.5 sc to 10 cm in DK cotton on a 5 mm hook is looser than typical. Many makers will need to go up a hook size to reach it. The pattern does tell them to change hook to match gauge, so this is not a defect until a sample is measured. | It is computed, not measured (`calibrated=False`). |
| F12 | all | Info | The US edition uses Commonwealth spelling ("colour", "centre"). This fits a Canadian brand and is not an error. In the UK edition, "tension" is the more idiomatic word than "gauge". | All pages. |
| F13 | fonts | Info | Every font subset carries the same tag, `AAAAAA+` (reportlab invariant mode). The fonts render correctly in poppler. Strict preflight tools may warn. | `pdffonts` output. |

**What the author's audit got right.** I verified its hashes, reproducibility, figure provenance, disclosures and UK legend fix. Its §7 already lists the round-chart and "all 2 changes" weaknesses. It missed F1, F3, F4, F6, F7 and F8. It also described F2 only as a wording issue, although the text is contradictory.

## 8. Most valuable quality improvements

1. **Fix the four Medium text defects in a 1.2.1 writer pass:**
   - F1: print "plus 15%" only next to the metres it describes;
   - F2: replace the contradictory sentence with "cut the wine after Rnd 6; carry cream up the join";
   - F3: add "the ch 1 does not count as a stitch";
   - F4: omit key entries for symbols the chart does not draw.

   Each is a one-line change, though each changes the certified text and the release hash.
2. **Redraw the round chart as a hexagon in the brand typefaces, as vector art.**
   - Draw it as six wedges with the V marks stacked on the spokes.
   - Move the round labels off the stitch cells.
   - Use type of at least 9 pt.

   This is the single biggest visual upgrade, and it fixes F5 and F6.
3. **Make a physical sample, measure it and calibrate the twin.** This turns "computed, not measured" into measured size and yarn figures, settles the hook question in F11, and allows a real photograph to replace the proof placeholder.
4. **Add written colour-change cues inside the rounds,** for example "join Rnd 5 with wine" and "join Rnd 6 with cream; fasten off wine". At present this information exists only in the Techniques and Finishing sections.
5. **Mark every page of the proof as NOT FOR SALE,** using a running header or a diagonal watermark.
6. **Install `sqlalchemy` in the test environment,** so the four deliverable-QA checks (date pinning, terminology shipping, support columns, difficulty ladder) actually run.
