# Reference pattern purchase proposal (W-REFBUY)

Prepared 2026-10-31 (UTC) by W-REFBUY. **This is a proposal only. Nothing was bought, no account
was created, and nobody was contacted.** Purchases are consequential spend, so they are
OWNER ACTION and stay inside the CA$300 benchmark ceiling the owner approved on 2026-09-20
(B-501, B-512; enforced in code as `SET_BUDGET_CAD`).

The purpose is private study of transferable technique and instruction presentation: the
teardown laboratory, F-789 and F-797. Nothing here may be copied. Every pattern below is
personal-use only, and its text, charts and photographs never enter a Brambleloop product or
this repository (`gates/originality.py`, `teardown/licence.py`, B-566).

## 1. Currency, price sources and caveats

- **Exchange rate:** Bank of Canada daily average for **2026-10-30**: USD/CAD **1.3960** and
  EUR/CAD **1.5582** (Valet API `FXUSDCAD`, `FXEURCAD`, fetched 2026-10-31).
- **VERIFIED** means that on 2026-10-31 I saw the price on the designer's own store page:
  Ravelry for MJ's, Briana K, Chabepatterns and FireflyCrochets, and Fourthwall for HanJan.
  - These prices are in USD or EUR and include no tax.
  - A Canadian card may add a foreign-exchange margin of about 2.5%.
  - GST/HST may apply. I did not check whether Ravelry collects it.
  - For a hard ceiling, budget **×1.158**: 2.5% FX plus 13% HST.
- **UNVERIFIED** means I did not see the price today. **Etsy blocked every automated fetch**
  (HTTP 403 on shop and listing pages), so no current Etsy price is verified. Where the repo
  holds an Etsy price, it comes from the 2026-10-07 observation in
  `research/final_build/w4/GATE_CLEARANCE_BUSINESS.md`.
- **The designer's own Ravelry store is much cheaper than the Etsy prices in the repo.**
  - MJ's single patterns are US$6–10 on Ravelry, about CA$8.38–13.96.
  - The earlier Etsy plan lists the same kinds of pattern at CA$16–22.
  - Etsy shows a standing "50% off" display price (`radar/market.py`), so the real Etsy
    checkout price may be close to Ravelry's. Compare before buying.
  - The Ravelry route also produces a downloadable PDF in the buyer's Ravelry library.
- **Intake:** the teardown intake (`/ops/teardown`, `POST /api/teardown/intake`) is keyed to
  `listing_ref`, and its approved rows are Etsy listings. A purchase made on Ravelry needs a
  matching intake row, or a free-text `listing_ref`. **This is for the integrator to
  confirm.**

## 2. What is already owned or planned

### Owned (owner-supplied purchased PDFs; the private reconstructions are in the repo, the protected text is not)

| ref | pattern | designer | what it already teaches | repo evidence |
|---|---|---|---|---|
| benchmark 1 | **Cardigan with Pockets**: side-to-side textured cardigan, XS–5XL, open front, pockets sewn on | MJ's Off The Hook Designs (as supplied by the owner) | flat one-piece side-to-side body, BLO rib built into the rows, sewn-on sleeves and pockets, 9-size grading of a flat garment | `cir/benchmarks.py`, `research/bench1/product_truth.py` (CIR `bench1-cardigan-with-pockets`), `teardown/licence.py` (conservative licence) |
| benchmark 2 | **Mini Star Stitch Cardigan**: child cardigan, 0–3 m to size 12, hood | MJ's Off The Hook Designs Inc. | star-stitch body, one-piece body with yoke and sleeves, hood, BLO ribbed bands, 10-size child grading | `gates/originality.py` `BENCHMARK_2`, `quality/benchmark_e2e.py`, `teardown/licence.py` (personal-use licence) |

**Consequence for this proposal:** no flat side-to-side adult cardigan, no star-stitch child
cardigan and no hooded child cardigan is proposed.

### Owner-preserved commercial benchmarks: the two MJ's basket listings

Both listings sit in the stored MJ's catalogue snapshot
(`research/final_build/w4/mjs/raw_snapshot.json`, listing-clarity `refs`, 2026-10-07) and in
the production owner-action evidence
(`research/final_build/w4/evidence_BOARD/prod_api_build_20261019T1249Z.json`).

| Etsy listing | resolved name (Ravelry, same designer) | Ravelry price | inclusion |
|---|---|---|---|
| https://www.etsy.com/listing/1438034001/crochet-pattern-videotwo-toned-nesting | **Two-Toned Nesting Baskets** | US$7.00 VERIFIED | item 2 below |
| https://www.etsy.com/listing/1767833856/crochet-pattern-video-fall-for-granny | **Fall For Granny Baskets** | US$6.00 VERIFIED | item 3 below |

- **Inference, to confirm:** I matched each listing to its name through the URL slug plus the
  designer's catalogue. The repo stores only the slug and the listing ID, not the title.
- Both listings stay as commercial benchmarks for the monitoring registry whether or not they
  are bought. Buying them adds the instruction-level teardown.
- They are the closest commercial comparators to Brambleloop's own Launch-0 baskets:
  `market-basket-small/medium/large` (the Hexagonal Bread Basket family) and
  `nursery-nesting-baskets` (held).

### Earlier purchasing plan (approved, **not executed**)

- **The plan:** a 13-pick MJ's set, chosen by `intel/purchase_selection.py` for facet coverage
  (B-485, B-501, B-507, B-509, B-512). There are two versions:
  - the 2026-10-07 table: CA$280.50, `GATE_CLEARANCE_BUSINESS.md`;
  - the 2026-10-19 production card: CA$286.00, with a slightly different 13 that adds Two-Toned
    Nesting, Holiday Weave, Floor Pouf, Rustic Farmhouse, Woodland Deer, Lace Sock and the
    Hooded Blanket bundle.
- **Status:** the `benchmark_purchases` gate is still OPEN, so no `BenchmarkProduct` row
  exists. I found nothing in the repo showing that any of those 13 were bought.
- **How this proposal relates to it:** this proposal **replaces** that plan's ranking with a
  technique-gap ranking. Overlaps are marked "in earlier plan" so that the owner does not buy
  anything twice if the old card was partly actioned.

## 3. The capability gaps the ranking is weighted toward

The research-driven draft path supports only `flat_rows` panels. These are missing:

1. in-the-round shaping (bases, tubes, vessels, 3-D forms);
2. colourwork charts;
3. mosaic and tapestry;
4. granny and motif assembly;
5. garment grading;
6. amigurumi.

Each item says which gaps it fills, and how its instructions and charts are presented, which
is the second thing to learn.

## 4. Ranked proposal (learning value per dollar)

All prices are pattern-only, before FX margin and tax.

| # | designer | pattern | category | price | CA$ | status | gaps | cumulative CA$ |
|---|---|---|---|---|---|---|---|---|
| 1 | MJ's Off The Hook Designs | Potted Paradise Mosaic Basket | baskets / home décor / mosaic | US$6.00 | 8.38 | VERIFIED | 1, 2, 3, 5 | 8.38 |
| 2 | MJ's Off The Hook Designs | Two-Toned Nesting Baskets | baskets (owner benchmark) | US$7.00 | 9.77 | VERIFIED | 1, 5 | 18.15 |
| 3 | MJ's Off The Hook Designs | Fall For Granny Baskets | baskets / seasonal (owner benchmark) | US$6.00 | 8.38 | VERIFIED | 1, 4, 5 | 26.53 |
| 4 | Chabepatterns (Maria Isabel) | Anthera Tapestry Bag | bags / tapestry | US$4.70 | 6.56 | VERIFIED | 1, 2, 3 | 33.09 |
| 5 | MJ's Off The Hook Designs | Halo Hugs V-Neck Sweater | women's garments | US$10.00 | 13.96 | VERIFIED | 1, 5 | **47.05** |
| 6 | Briana K Designs | Houndstooth Dog Sweater | pet | US$8.00 | 11.17 | VERIFIED | 1, 2, 5 | 58.22 |
| 7 | MJ's Off The Hook Designs | River Stone Granny Bag | bags / motif | US$6.00 | 8.38 | VERIFIED | 4 | 66.60 |
| 8 | HanJanCrochet (HanJan Crochet Ltd) | Happy Hearts Blanket Pattern | blankets / baby / mosaic | US$6.95 sale (reg. US$14.00) | 9.70 | VERIFIED (sale price; CA$19.54 at regular) | 2, 3 | 76.30 |
| 9 | FireflyCrochets (Mareeva Olga) | Christmas Moose ("Richard") | amigurumi / seasonal | €6.20 | 9.66 | VERIFIED | 1, 6 | 85.96 |
| 10 | MJ's Off The Hook Designs | Modern C2C Blanket | blankets / C2C | US$6.00 | 8.38 | VERIFIED | 2, 3 (C2C) | **94.34** |
| 11 | MJ's Off The Hook Designs | Holiday Weave Stocking | seasonal | US$8.00 | 11.17 | VERIFIED | 1, 2 | 105.51 |
| 12 | MJ's Off The Hook Designs | Granny Square Ball | seasonal / home décor / motif | US$6.00 | 8.38 | VERIFIED | 1, 4 | 113.89 |
| 13 | MJ's Off The Hook Designs | Dusty Rose Baby Set | baby & nursery | US$6.00 | 8.38 | VERIFIED | 1, 5 | 122.27 |
| 14 | TheEasyDesign (April Miller) | Meda (fringed triangle shawl) | women's accessories | US$5.00 | 6.98 | VERIFIED | shaping outside rectangles | 129.25 |
| 15 | MJ's Off The Hook Designs | The Perfect Fit Guidebook: Unlocking Pattern Sizing and Body Measurements | garment grading (education) | CA$21.00 (Etsy, 2026-10-07) | 21.00 | **UNVERIFIED** | 5 | 150.25 |
| 16 | MJ's Off The Hook Designs | Jumbo Amigurumi Snowman | amigurumi / seasonal | US$7.50 | 10.47 | VERIFIED | 1, 6 | 160.72 |
| 17 | MJ's Off The Hook Designs | Butterfly Kisses Mosaic Blanket | textured blankets / mosaic | US$10.00 | 13.96 | VERIFIED | 2, 3 | 174.68 |

### Totals

| tranche | items | pattern cost | with ×1.158 FX and HST contingency |
|---|---|---|---|
| **First CA$50** | 1–5 | **CA$47.05** | CA$54.48 |
| **First CA$100** | 1–10 | **CA$94.34** | CA$109.25 |
| Full list | 1–17 | **CA$174.68**: CA$153.68 verified plus CA$21.00 unverified | CA$202.28 |

The full list sits well inside the approved CA$300 ceiling.

**Alternative:** for item 11, the **Holiday Home Collection** ebook costs US$32.00 (CA$44.67,
VERIFIED). It holds six patterns: the Holiday Weave Stocking, Tree Skirt (5-point, one-piece),
Bauble and Blanket, plus the Bobble Tree Sweaters and the Holiday Wreath. It is worth it only
if the seasonal *family* teardown (one visual language across blanket, stocking, tree skirt and
ornament; `radar/market.py` "seasonal_families") is wanted in one purchase. Otherwise take the
single stocking.

## 5. Item detail

The same notes apply to every item unless an entry says otherwise.

- **Common licence:** personal use only. No sharing, copying, screenshots or resale of the
  pattern. The designer's photos may not be used. All sales are final.
- **PDF:** a downloadable PDF is delivered unless the entry says otherwise.
- **Duplication:** each entry is checked against the two owned benchmarks and the earlier plan.

### 1. Potted Paradise Mosaic Basket (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/potted-paradise-mosaic-basket. Also on
  the designer's site at https://www.mjsoffthehookdesigns.com/potted-paradise-mosaic-basket/.
- **Price:** US$6.00, which is CA$8.38. VERIFIED 2026-10-31.
- **Specification:**
  - three sizes, S/M/L: circumference 21.75, 26.25 and 30.5 in; height 6, 8.5 and 11 in;
  - worked bottom-up;
  - two strands of worsted held together, 6.0 mm hook, SC BLO gauge;
  - written instructions plus a chart; video available.
- **Learning objectives:**
  - how a mosaic chart is expressed in rounds rather than rows;
  - the base-to-wall turn;
  - how a stitch-count repeat must divide every size's circumference;
  - how a graded vessel is tabulated.
- **Gap:** in-the-round shaping, mosaic and colourwork charts, size grading of a 3-D form. This
  is the single highest gap density for the price.
- **Relevance:**
  - very high: Brambleloop's Nordic Forest Mosaic Storage Basket concept (`radar/opportunity.py`);
  - Brambleloop's own basket family;
  - any future mosaic-in-the-round product.
- **Licence:** finished items may be sold with designer credit.
- **Duplication:** none. Not in either earlier plan, and neither owned benchmark is worked in
  the round or uses mosaic.

### 2. Two-Toned Nesting Baskets (MJ's Off The Hook Designs): owner-preserved benchmark

- **Source:** https://www.ravelry.com/patterns/library/two-toned-nesting-baskets. Etsy listing
  https://www.etsy.com/listing/1438034001/crochet-pattern-videotwo-toned-nesting.
- **Price:** US$7.00, which is CA$9.77. VERIFIED on Ravelry; Etsy price UNVERIFIED.
- **Specification:** S/M/L, seamless in the round, bulky yarn, HDC, video.
- **Learning objectives:**
  - how a commercial best-seller presents nesting sizes;
  - the base increase scheme and the stop-increasing point;
  - the colour-change join in rounds;
  - how sizes are stated against the finished dimensions.
- **Gap:** in-the-round vessels, multi-size grading.
- **Relevance:** direct commercial comparator for `market-basket-small/medium/large` and the
  held `nursery-nesting-baskets`. It is also a check on our size-claim gate.
- **Licence:** a free web version also exists. The PDF purchase adds the formatted
  instruction layout, which is what is studied.
- **Duplication:** **in earlier plan** (2026-10-19 card). None against the owned benchmarks.

### 3. Fall For Granny Baskets (MJ's Off The Hook Designs): owner-preserved benchmark

- **Source:** https://www.ravelry.com/patterns/library/fall-for-granny-baskets. Etsy listing
  https://www.etsy.com/listing/1767833856/crochet-pattern-video-fall-for-granny.
- **Price:** US$6.00, which is CA$8.38. VERIFIED on Ravelry; Etsy price UNVERIFIED.
- **Specification:**
  - four sizes, S–XL;
  - bottom-up in the round, granny-cluster stitch in bulky yarn;
  - matches the Fall For Granny Blanket and Pumpkins.
- **Learning objectives:**
  - granny clusters worked as a continuous round fabric;
  - how a four-size vessel is graded;
  - how a seasonal family member is cross-referenced.
- **Gap:** in-the-round shaping, a granny-stitch structure, grading.
- **Relevance:** baskets and seasonal family merchandising.
- **Duplication:** none. Not in either earlier plan.

### 4. Anthera Tapestry Bag (Chabepatterns, Maria Isabel): non-benchmark, justified

- **Source:** https://www.ravelry.com/patterns/library/anthera-tapestry-bag
- **Price:** US$4.70, which is CA$6.56. VERIFIED.
- **Specification:**
  - 26.5 × 23 cm;
  - in the round, bottom-up, tapestry crochet;
  - support chart plus round-by-round text;
  - English and Spanish.
- **Learning objectives:**
  - tapestry carry and float management;
  - how a tapestry chart maps onto rounds;
  - chart-plus-text cross-referencing.
- **Gap:** tapestry and colourwork charts in the round. No benchmark shop showed a tapestry
  pattern I could verify, which is why this designer is included.
- **Relevance:** bags and home décor with charted motifs.
- **Licence:** finished items may be sold in small quantities with credit. No formal licence is
  named, so treat it as personal use.
- **Duplication:** none.

### 5. Halo Hugs V-Neck Sweater (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/halo-hugs-v-neck-sweater
- **Price:** US$10.00, which is CA$13.96. VERIFIED.
- **Specification:**
  - XS–5X (9 sizes), finished bust 35–64.5 in;
  - top-down and seamless: the yoke is worked flat, then joined into turned rounds, and the
    sleeves are joined to the body;
  - schematic included.
- **Learning objectives:**
  - top-down yoke increase grading across 9 sizes;
  - the V-neck shaping rate;
  - the flat-to-round transition;
  - how 9-size tables and the schematic are presented.
- **Gap:** garment grading and in-the-round construction. Both owned garments are seamed or flat.
- **Relevance:** women's garments, the highest-ticket category.
- **Duplication:**
  - partial overlap with benchmark 2, which also joins sleeves to a yoke, but that is child
    sizing and star stitch;
  - none with benchmark 1;
  - not in either earlier plan.

### 6. Houndstooth Dog Sweater (Briana K Designs): non-benchmark, justified

- **Source:** https://www.ravelry.com/patterns/library/houndstooth-dog-sweater-5
- **Price:** US$8.00, which is CA$11.17. VERIFIED.
- **Specification:**
  - 8 sizes, XXS–3X, chest 13.75–34.25 in;
  - top-down in the round, ribbed neckband, harness opening;
  - two-colour houndstooth with a chart.
- **Learning objectives:**
  - grading a non-human body (chest and neck);
  - the harness-opening construction;
  - a two-colour repeat chart.
- **Gap:** pet products, which no benchmark shop covers with a verifiable listing. Also fills
  in-the-round shaping, colourwork charts and grading.
- **Relevance:** the pet category, which is entirely absent today.
- **Licence:** personal use. Finished items may be sold. The pattern also unlocks in the
  designer's app.
- **Duplication:** none.

### 7. River Stone Granny Bag (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/river-stone-granny-bag
- **Price:** US$6.00, which is CA$8.38. VERIFIED.
- **Specification:**
  - 15 granny puff squares in three colours, seamed, with a strap;
  - schematic and granny-square stitch diagram;
  - worsted yarn, 545 yd.
- **Learning objectives:**
  - motif count and layout-to-schematic presentation;
  - turning flat motifs into a 3-D sling by seaming;
  - the stitch-diagram conventions.
- **Gap:** granny and motif assembly.
- **Relevance:** bags; granny-square products generally.
- **Duplication:** none. Not in either earlier plan.

### 8. Happy Hearts Blanket Pattern (HanJanCrochet)

- **Source:** https://hanjancrochet-shop.fourthwall.com/products/happy-hearts-blanket-pattern.
  It is also on Ravelry as "Happy Hearts Blanket" by Hannah Cross at £5.50 (not converted).
- **Price:** US$6.95 sale, which is CA$9.70. VERIFIED. The regular price is US$14.00, which is
  CA$19.54.
- **Specification:**
  - overlay mosaic, flat rows, one colour per row;
  - full mosaic charts;
  - about 33 × 40 in, adjustable from baby blanket to throw;
  - video; US terms with UK conversion.
- **Learning objectives:**
  - how the category's top overlay-mosaic seller lays out charts, row keys and colour
    sequencing;
  - the size-adjustment rule, which is that repeats scale the blanket.
- **Gap:** mosaic charts. This is the closest technique to the existing `flat_rows` engine, so
  it is the cheapest gap to close next.
- **Relevance:**
  - baby and nursery blankets, where Cloudline is the incumbent;
  - textured and mosaic throws.
- **Licence:** personal use. Small-quantity sale of finished items with credit. Non-refundable.
- **Duplication:** none.

### 9. Christmas Moose "Richard" (FireflyCrochets, Mareeva Olga)

- **Source:** https://ravelry.com/patterns/library/christmas-moose-4. It is also sold on the
  Firefly Crochet website; the Etsy shop is https://www.etsy.com/ca/shop/FireflyCrochets.
- **Price:** €6.20, which is CA$9.66. VERIFIED on Ravelry; Etsy price UNVERIFIED.
- **Specification:**
  - about 38 cm sitting;
  - parts worked in the round and sewn;
  - safety eyes, fibrefill, post-stitch and tapestry details;
  - 18 A4 pages with 78 process photos.
- **Learning objectives:**
  - the amigurumi part-by-part structure;
  - joining and placement instructions;
  - how a photo-dense tutorial is paced.
- **Gap:** amigurumi and in-the-round 3-D shaping.
- **Relevance:** amigurumi and seasonal characters. Note: amigurumi is Class B/C for validation
  (`radar/market.py`).
- **Licence:** all rights reserved. Limited handmade sale of finished items with a link to the
  shop.
- **Duplication:** none.

### 10. Modern C2C Blanket (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/modern-c2c-blanket
- **Price:** US$6.00, which is CA$8.38. VERIFIED.
- **Specification:**
  - 50 × 60 in;
  - bulky and worsted versions;
  - written instructions plus charts; two videos.
- **Learning objectives:**
  - the C2C increase and decrease corners;
  - how a C2C chart is presented and how a maker reads it;
  - converting between two yarn weights.
- **Gap:** C2C and chart-based construction.
- **Relevance:** graphghan-style blankets.
- **Licence:** a free web version exists. Buy the PDF only for the chart layout. Defer this item
  if the free version is enough.
- **Duplication:** none.

### 11. Holiday Weave Stocking (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/holiday-weave-stocking
- **Price:** US$8.00, which is CA$11.17. VERIFIED.
- **Specification:**
  - toe-up in continuous rounds;
  - join-as-you-go ribbed cuff, tassel;
  - six-colour striped moss stitch;
  - colour-repeat chart and schematic.
- **Learning objectives:**
  - toe-up tube shaping;
  - join-as-you-go cuff;
  - a colour-sequence chart.
- **Gap:** in-the-round shaping, colour charts.
- **Relevance:** seasonal stockings, the department B-501 prioritised.
- **Duplication:**
  - **possible overlap with the earlier plan:** Etsy listing 1825269747 is "holiday-weave",
    which is also the listing ID in the owner-supplied MJ's URL;
  - which Holiday Weave item that listing is: UNKNOWN;
  - check before buying.

### 12. Granny Square Ball (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/granny-square-ball. Etsy listing
  https://www.etsy.com/listing/1613235888/crochet-pattern-granny-square-ball.
- **Price:** US$6.00, which is CA$8.38. VERIFIED on Ravelry. The Etsy price of CA$18.00 from
  2026-10-07 is UNVERIFIED.
- **Specification:**
  - two granny squares form a cover for a clear ornament ball;
  - 8 in and 12.5 in sizes;
  - schematic.
- **Learning objectives:** turning a flat motif into a sphere, and the schematic for that.
- **Gap:** motif assembly into 3-D, in-the-round.
- **Relevance:** ornaments and seasonal décor.
- **Duplication:** **in earlier plan** (2026-10-07 table, #13).

### 13. Dusty Rose Baby Set (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/dusty-rose-baby-set. Etsy listing
  https://www.etsy.com/listing/628097461/crochet-pattern-dusty-rose-baby-set.
- **Price:** US$6.00, which is CA$8.38. VERIFIED on Ravelry. The Etsy price of CA$20.00 from
  2026-10-07 is UNVERIFIED.
- **Specification:**
  - hat in 6 sizes (newborn to 24 m);
  - booties in 5 sizes;
  - blanket 32 × 40 in;
  - stripes and texture.
- **Learning objectives:**
  - how a multi-item baby set is packaged;
  - grading a baby hat (crown in the round) and booties.
- **Gap:** in-the-round grading at baby scale; set merchandising.
- **Relevance:** baby and nursery, Brambleloop's Launch-0 strength.
- **Licence:**
  - a free version exists;
  - the hat and bootie videos are on the designer's site behind a coupon login;
  - the PDF is downloadable.
- **Duplication:**
  - **in both earlier plans**;
  - shares child sizing with benchmark 2, which is a garment, not accessories.

### 14. Meda (TheEasyDesign, April Miller)

- **Source:** https://www.ravelry.com/patterns/library/meda-2. The Etsy shop is
  https://www.etsy.com/shop/TheEasyDesign.
- **Price:** US$5.00, which is CA$6.98. VERIFIED on Ravelry.
- **Specification:**
  - fringed boho triangle shawl;
  - filet, one row per repeat;
  - any yarn weight, 250–350 yd.
- **Learning objectives:**
  - triangular shaping rate;
  - gauge-agnostic instruction writing;
  - a minimal, high-volume pattern format: the shop has about 430k sales.
- **Gap:** non-rectangular shaping, accessories.
- **Relevance:** women's accessories, and quick, low-price products.
- **Licence:** the shop says finished items may be sold with credit. The Ravelry page shows no
  licence, so treat it as personal use.
- **Duplication:** none.

### 15. The Perfect Fit Guidebook (MJ's Off The Hook Designs)

- **Source:** https://www.etsy.com/listing/1500579838/the-perfect-fit-guidebook-unlocking.
  I did not find it on Ravelry.
- **Price:** CA$21.00 from the 2026-10-07 repo observation. **UNVERIFIED**, because Etsy
  returned 403.
- **Learning objectives:** how a commercial designer explains body measurement, ease and size
  selection to makers.
- **Gap:** garment grading presentation, which is customer-facing sizing education.
- **Relevance:** every garment, and Brambleloop's own size-choice copy.
- **Licence:** education guide, personal use. PDF assumed but UNVERIFIED.
- **Duplication:** **in both earlier plans**.

### 16. Jumbo Amigurumi Snowman (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/jumbo-amigurumi-snowman
- **Price:** US$7.50, which is CA$10.47. VERIFIED.
- **Specification:**
  - 18, 20 and 24 in;
  - one continuous piece, bottom-up, no sewn snowballs;
  - super bulky, SC BLO.
- **Learning objectives:**
  - one-piece amigurumi with no sewn joins;
  - grading an amigurumi across three sizes.
- **Gap:** amigurumi and in-the-round shaping. It complements item 9, which is pieced.
- **Relevance:** seasonal décor.
- **Duplication:** none. The earlier plan's amigurumi pick is the Rustic Farmhouse Pumpkin, a
  different form.

### 17. Butterfly Kisses Mosaic Blanket (MJ's Off The Hook Designs)

- **Source:** https://www.ravelry.com/patterns/library/butterfly-kisses-mosaic-blanket
- **Price:** US$10.00, which is CA$13.96. VERIFIED.
- **Specification:** 50 × 60 in, overlay mosaic, chart.
- **Learning objectives:** a second overlay-mosaic chart convention, to set against HanJan
  (item 8).
- **Gap:** mosaic charts.
- **Relevance:** mosaic throws.
- **Duplication:** none in the owned set. **Lowest priority**, because it is technique-redundant
  with items 1 and 8.

## 6. Benchmark shops I could not price

| shop | finding | action |
|---|---|---|
| ZKBDESIGNER | Etsy-only. Search snippets show baby blankets (animal granny squares, a "Piglet and Pooh" blanket), a flower tutorial and a flower-pot set. Etsy returned 403, so I saw no price. | **Not proposed.** The "Piglet and Pooh" listing uses third-party character IP; do not buy it as a reference. Re-check the animal-granny blanket when a browser worker can read Etsy. |
| IvyLoop | No listing or off-Etsy presence found. Profile empty in `radar/market.py`. | Not proposed: nothing verifiable. |
| LoveandStitchDesigns | No off-Etsy presence found. The repo records garments at CA$9.90–14.05 (2026-09-17). | Not proposed: nothing verifiable. Halo Hugs (item 5) covers the garment gap. |
| MadelineMaeCo | Etsy-only. The "Belly Friends" amigurumi line (for example Mini Belly Ellie) appears in third-party reviews. I saw no price. | Optional candidate, UNVERIFIED: a nursery amigurumi reference to add if the price is CA$10 or less on Etsy checkout. |

## 7. Recommended purchase order (owner action)

- **Tranche 1, first CA$50 (CA$47.05 before FX and tax):** items 1–5.
  - Both owner-preserved basket benchmarks;
  - mosaic in the round;
  - tapestry;
  - a top-down graded women's garment.
- **Tranche 2, first CA$100 (CA$94.34 cumulative):** add items 6–10.
  - Pet;
  - motif assembly;
  - HanJan mosaic chart layout;
  - amigurumi;
  - C2C.
- **Tranche 3 (CA$174.68 cumulative):** items 11–17, only after tranche 1 has been torn down
  and the engine work it informs has started.
- Before buying items 2, 11, 12, 13 or 15, check that they were not already bought under the
  earlier 13-pick card.
- For each purchase, compare the Etsy checkout price with the designer's Ravelry price and
  take the cheaper one. Record the actual CA$ paid at intake (`paid_cad`).
- Owner minutes: about 3–4 per purchase (buy, download, intake upload), so about 20 minutes
  for tranche 1 and about 40 minutes for tranche 2.
- **Consequence of waiting:** the draft engine stays limited to `flat_rows`, and in-the-round,
  chart, motif and amigurumi work continues without a commercial reference for instruction
  presentation. There is no external deadline.
