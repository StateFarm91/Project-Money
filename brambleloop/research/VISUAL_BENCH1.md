# Commercial benchmark 1 — purchased pattern → Product Truth → full-product reference → photoreal hero → commercial truth gate → seller-photo comparison

**Branch** `claude/visual-investigation` from checkpoint **`90fa87a`** (E5 close); `a447c2f`, `1229442`, `4a08871`, `fcb982d` untouched. **Date** 2026-09-26. **Result: the hero benchmark SUCCEEDS on one image of twelve** — `research/bench1/out/gen/oa15_hifi_10.png` (sha256 `1879561f…`) passes every material Product Truth property, the deterministic silhouette / proportion / stitch-scale measures and all seven realism items, through a recorded, reproducible pipeline. It is not permission to publish. Yield on the final configuration is 1 of 3, overall 1 of 12; the dominant residual failure is the generator's gauge (stitch scale), which the gate now measures and which fails 9 of 12 draws. External spend **US$3.45** of the US$5.00 ceiling.

Everything below is read from `research/bench1/out/` (Product Truth with page citations, the CIR, the reference metadata, the manifest with every call, the gate records, the readings, the comparison). The seller's PDF, its text and photographs are NOT in the repository; `test_bench1.py` asserts that.

## 1. Materials identified

- **Purchased pattern:** "Cardigan with Pockets", a 12-page PDF (Microsoft Word "uzuncepli", created 2023-10-22), a beginner side-to-side textured crochet cardigan in Lion Brand Color Theory worsted acrylic, 6 mm hook, nine sizes XS–5XL, sample size S. Read from the PDF's extracted text at run time, not from memory or from E1/E2.
- **Seller / listing photographs:** four supplied images of the finished cardigan worn (three of the same dusty-pink sample on a model; a fourth, chunkier make on a different model). Used only as independent evidence, never as conditioning.
- **The pattern's own process photographs** (21 embedded images, a blue-grey sample) were extracted for reading the assembly and are likewise kept outside the repository.

## 2. Product Truth (Phase 1) — `research/bench1/product_truth.py`, `out/product_truth.json`

Every fact regex-matched from the PDF text and cited to its page. Size S (the sample):

| fact | value | page |
|---|---|---|
| construction | body one piece worked flat side to side: front (20 rows), chained sleeve opening (29 ch), back (50 rows), opening, front (20 rows), final plain row = 91 rows of 94 hdc; hem rib = 10 back-loop stitches in every row; sleeves separate, side to side, folded and seamed; neckband and pockets separate and sewn | 2, 4–12 |
| stitch pattern | crumpled waffle: alternating BLO/FLO hdc, offset each row | 4 |
| gauge | 14.5 st × 9.5 rows per 10 cm | 3 |
| stated measurements | bust 81, back width 53, armhole 15, sleeve 39, length 65 cm | 3 |
| sleeves | ch 63 → 62 sts, 30 rows, cuff 10 sts of BLO slip stitch | 8–9 |
| neckband | 7 sts, BLO hdc rows to the neckline's length | 10 |
| pockets | 2, optional, 24 sts × 13 rows, slip-stitch top edge, placement "try on to double-check" | 11–12 |
| yarn | 585 g worsted acrylic, colourway Stonewash | 3 |

Deterministic checks, all PASS: row totals add up (20+50+20+1 = 91); foundation = stitches + 1 on every piece; stated length 65 vs 64.8 from counts × gauge; back width 53 vs 52.6; armhole 15 vs 15.8 (half the sleeve circumference); back neck exists (10.5 cm). Sleeve length: 42.8 cm at hdc gauge vs 39 stated (+10 %, recorded: the cuff is slip stitch and shorter). The CIR built from the parse **compiles** (four components, benchmark-authored, chain gauge derived from the nine sizes as 18.65 ± 6 % per 10 cm) and the assembly check finds the sleeve-to-opening join **sound** (31.6 vs 31.1 cm); two joins (neckband, pockets) are unplaced because the pattern places them by fitting. The earlier independent encoding `cir/benchmarks.py` agrees with the parse on every count (cross-check, never a source). Two facts are DECLARED ASSUMED: pocket placement (centred on each front, 5 cm above the hem rib) and the colourway's RGB (sampled from the seller's photograph of it).

## 3. Product Truth vs the seller's photographs (Phase 2)

The same structured reader (gpt-5, sixteen fixed questions) read the four seller photographs; each answer was judged against Product Truth's expectation (`out/seller_vs_product_truth.json`). All four agree on: cardigan, open front, 0 closures, ribbed front band, ribbed hem band, ribbed cuffs, long sleeves, 2 hip pockets (3 of 4; the side view shows none), one colour, pink, no extra features, hand-crocheted. Disagreements recorded, not reconciled: body ridge direction (pattern: vertical; reader: horizontal on 3 of 4 — the bands' ridges dominate its reading, so the property is reported and not gated); texture family "other" on photograph 4 (the chunkier make); body length "hip" on photograph 1 (side view) and "mid_thigh" on the rest.

## 4. Full-product reference (Phase 3) — `research/bench1/reference.py`

A deterministic flat lay from Product Truth and the compiled CIR only: fronts laid on the back and joined at the shoulders, open at the centre, neckband up both fronts and across the back neck, hem rib, sleeves at the openings, cuffs gathered (slip-stitch rows are 0.3 of an hdc row), pockets at the declared assumed placement. Every texture cell is a stitch the compiler counted, drawn with its loop target's ridge along the row direction (vertical on the body and pockets, lengthwise on the sleeves, across the band), at counts × gauge. Outputs per version: RGB, mask, normal map (from the ridge height field), region map (12 regions) with legend and metadata.

| version | size | px/cm | stitch cell px | why |
|---|---|---|---|---|
| ref | 1024² | 6.5 | 4.5 × 6.8 | first hero framing |
| ref2 | 1536×1024 | 10.4 | 7.2 × 11.0 | the generator could not see the gauge at 4.5 px |
| ref3 | 1536×1024 | 10.4 | 7.2 × 11.0 | **cuff-end defect fixed**: ref/ref2 drew the sleeve's fabric position 0 at the shoulder, putting the cuff's back-loop bars at the upper sleeve as a ribbed insert the generator reproduced and the reader caught |

The reader saw the truth on the reference: cardigan, open, 0 closures, ribbed band, ribbed hem, ribbed cuffs, 2 hip pockets, long sleeves, waffle texture, one colour (it read ridge direction "none" and hand-crocheted "false", as expected of a rendering).

## 5. Generation (Phase 4) — `research/bench1/run_bench1.py`

E5's best configuration first: **gpt-image-1.5, `images/edits`, `input_fidelity=high`, quality medium**, references RGB + mask + normal; gemini-3-pro-image as the independent alternative. Presentation-only prompts (no stitch, count, pocket, band, length or construction named): v1 a plain flat-lay hero on linen; v2 the same with a hand-placed, slightly askew laydown (round 1's judge failures were "catalogue-perfect sterility"). Prompts and every parameter, reference digest, prompt digest, output digest and cost are in `out/bench1_manifest.json`.

## 6. Every attempt (Phase 5 gate) — `research/bench1/gate.py`, `out/bench1_gate.json`

Gate: deterministic (silhouette IoU ≥ 0.80 after scale/shift alignment, aspect drift ≤ 0.10, sleeve span drift ≤ 0.12, **stitch scale** = texture period vs the reference's inside the front panel, ±35 %) → reader properties against Product Truth (material: type, open front, 0 closures, front band, hem band, cuffs, 2 hip pockets, long sleeves, body length, an all-over texture, one colour, no invented features) → the unchanged D judge (7 items). PASS only when every material property, every deterministic measure and every judge item passes; UNKNOWN never passes.

| candidate | reference | prompt | silhouette IoU | aspect drift | stitch-scale ratio | material fails | judge fails | verdict |
|---|---|---|---|---|---|---|---|---|
| oa15_hifi_1 | ref | v1 | 0.939 | 0.055 | 3.58 | stitch_scale | catalogue_perfect_sterility | FAIL |
| oa15_hifi_2 | ref | v1 | 0.943 | 0.057 | 2.53 | stitch_scale | fabric_folds_naturally | FAIL |
| oa15_hifi_3 | ref | v1 | 0.951 | 0.050 | 1.72 | stitch_scale | catalogue_perfect_sterility | FAIL |
| oa15_hifi_4 | ref | v2 | 0.946 | 0.066 | 2.15 | stitch_scale | fabric_folds_naturally | FAIL |
| oa15_hifi_5 | ref | v2 | 0.911 | 0.086 | 1.96 | stitch_scale | fabric_folds_naturally | FAIL |
| oa15_hifi_6 | ref | v2 | 0.936 | 0.066 | 2.05 | stitch_scale | — | FAIL |
| g3pro_1 | ref | v2 | 0.746 | 0.924 | 1.72 | silhouette, proportions, sleeve_span, stitch_scale | — | FAIL |
| g3pro_2 | ref | v2 | 0.700 | 0.500 | 3.58 | silhouette, proportions, sleeve_span, stitch_scale | — | FAIL |
| oa15_hifi_7 | ref2 | v2 | 0.970 | 0.022 | 1.00 | sleeve_length (read three-quarter) | — | FAIL |
| oa15_hifi_8 | ref2 | v2 | 0.940 | 0.006 | 1.59 | stitch_scale | — | FAIL |
| oa15_hifi_9 | ref2 | v2 | 0.969 | 0.022 | 2.15 | stitch_scale | — | FAIL |
| **oa15_hifi_10** | ref3 | v2 | 0.967 | 0.025 | 1.30 | — | — | **PASS** |
| oa15_hifi_11 | ref3 | v2 | 0.967 | 0.026 | 2.26 | stitch_scale | — | FAIL |
| oa15_hifi_12 | ref3 | v2 | 0.928 | 0.034 | 1.13 | sleeve_length (read three-quarter) | — | FAIL |

Reject reasons, in order of frequency: stitch scale (gauge drawn 1.6–3.6× coarser) 9; realism (sterile / too flat) 4; sleeve length read three-quarter 2; re-posed (Gemini) 2. Rounds 1–3 also carried the ribbed-insert defect from the reference (§4), which the reader flagged on 2 of 3 round-3 draws and missed on 6 of 6 earlier — recorded as a reader limitation for small invented features. Nothing was cherry-picked: all twelve are here, and the gate ran on every one.

**The certified hero.** gpt-image-1.5, `input_fidelity=high`, quality medium, 1536×1024, references ref3 (`8198f845…`, mask `52073c18…`, normal `efddf633…`), prompt v2 (`4447e8c0…`), output `1879561f…`, US$0.27. Reader: cardigan, open, 0 closures, ribbed front band, ribbed hem band, ribbed cuffs, 2 hip pockets, long sleeves, hip length, one pink colour, no extra features, hand-crocheted; texture "other". Judge: all seven items PASS. Silhouette 0.967, aspect drift 2.5 %, sleeve span within 3 %, stitch scale 1.30×.

## 7. Comparison: pattern truth vs structural product vs photoreal image vs seller's product (Phase 6) — `out/comparison.json`

| property | pattern truth | reference (read) | seller photos (read) | hero (read) |
|---|---|---|---|---|
| product / front / closures | cardigan, open, none | same | same ×4 | same |
| front band / hem band / cuffs | ribbed 4.8 cm band; 10-st rib hem; slip-stitch cuffs | ribbed / ribbed / ribbed | ribbed / ribbed / ribbed ×4 | ribbed / ribbed / ribbed |
| pockets | 2, hip, placement by fitting | 2, hip | 2, hip ×3 (side view: unseen) | 2, hip |
| sleeves | long (39 cm + drop shoulder) | long | long ×4 | long |
| body length | 65 cm, ~mid-thigh on 160 cm | hip (flat) | mid-thigh ×3, hip ×1 | hip (flat) |
| texture | crumpled waffle (checkered BLO/FLO) | waffle | waffle ×3, other ×1 | **other** (seed-stitch-like) |
| ridge direction | vertical | none | horizontal ×3, vertical ×1 | none |
| colour | Stonewash (1 colour) | pink | pink ×4 | pink |

Materially significant discrepancies and where they trace (full list with ids in `comparison.json`):
1. **Gauge / stitch scale** — generative presentation (+ reference pixel scale): the model invents a coarser gauge on 9 of 12 draws; two were independently read as child-sized. Now measured and gated; a 1.6× larger reference helped (ratio 1.0–1.3 on 4 of 6 later draws) but did not fix it.
2. **Stitch pattern appearance** — generative presentation: the material re-synthesis renders an all-over seed-like texture rather than the crumpled waffle (reader: "other" on 11 of 14 candidate reads; waffle on 3 of 4 seller photographs). Borderline material for a *pattern* listing (the stitch is the design's identity); the gate accepts any all-over texture today and this is the next instrument to build — E4's per-stitch correspondence becomes applicable exactly when the gauge is held.
3. **Invented ribbed inserts** — full-product geometry (our reference), fixed in ref3 and caught by the gate.
4. **Sleeve length read** — validation: a flat lay does not show where a sleeve falls; the reader guessed three-quarter on 2 of 12 (strictly failed).
5. **Ridge direction** — validation: unreadable by the reader even on ground truth; reported, not gated.
6. **Pocket placement, colour RGB** — missing physical information, declared assumed; both consistent with the seller's photographs.
7. **Chain gauge** — pattern parsing: the join is sound only under the derived chain gauge.

## 8. Yield and cost

| configuration | draws | structural + material PASS | judge PASS | certified |
|---|---|---|---|---|
| ref, prompt v1, gpt-image-1.5 hifi | 3 | 0 | 0 | 0 |
| ref, prompt v2, gpt-image-1.5 hifi | 3 | 0 | 1 | 0 |
| ref, prompt v2, gemini-3-pro-image | 2 | 0 | 2 | 0 |
| ref2, prompt v2, gpt-image-1.5 hifi | 3 | 0 | 3 | 0 |
| **ref3, prompt v2, gpt-image-1.5 hifi** | 3 | 1 | 3 | **1** |

Spend: generation US$3.04 (12 gpt-image-1.5 draws at US$0.19–0.27 by usage tokens, 2 Gemini at list), reader US$0.23 (4 seller photographs, reference, 14 candidate reads), judge US$0.18. **Total US$3.45** of US$5.00. Cost per certified hero at the final configuration: about US$0.90 per draw-triplet, i.e. US$0.30 per draw with a 1-in-3 observed yield (n = 3, not a rate).

## 9. Remaining blockers

- **Gauge is not held by the generator** (9 of 12). Resolution helps; nothing else available does (E5). A production route is the gated loop at ~US$0.30 per draw with a low, unmeasured yield.
- **Stitch-pattern identity is not gated.** Per-stitch correspondence (E4) needs the gauge held first; then it can be run on the body panels of a flat lay through the same projected-manifest approach (the flat lay is an orthographic camera, simpler than E4's).
- **Reader limits:** small invented features (missed 6 of 6 at 1024 px), sleeve length on a flat lay, ridge direction. The deterministic measures carry the gate where the reader is weak; a deterministic per-region texture check would close the invented-feature gap.
- **Absolute scale.** A flat lay has no ruler; the gauge check is the only protection against a child-sized reading.

## 10. Ready for the full listing pipeline?

**Hero: yes, as a gated loop, not as a one-shot.** The architecture (pattern → Product Truth → deterministic reference → fidelity-locked material re-synthesis → deterministic + reader + judge gate) produced a certified hero and rejected eleven for stated, traceable reasons. **Model / on-body and lifestyle: not yet.** Those need a body form and drape the reference does not have (E2's torso form was a placeholder), and every E5 finding about pose drift applies with more force when the garment is worn. **Detail images: possible now** from the same reference at higher magnification, subject to the stitch-pattern gate above. **Sizing / feature images: possible now** — they are diagrams from Product Truth, no generator needed.

## 11. Changes in the repository

`research/bench1/`: `product_truth.py` (parser, checks, CIR), `reference.py` (flat-lay builder, three versions), `reader.py`, `gate.py`, `run_bench1.py`, `test_bench1.py` (34 checks), `out/` (Product Truth, CIR JSON, reference sets, 14 candidates, manifest, gate records, readings, comparison). No change to `src/`, no gate integrated into production. The seller's PDF, its text and photographs are outside the repository.
