# Opportunity pool and release portfolio

_Generated 2026-09-17 (UTC) from `brambleloop.radar`. Competitor observations dated 2026-09-17. Regenerate with `python -m brambleloop.radar.report`._

Master Plan section 33: do not commit the first SKUs before Market Radar runs; start from at least 30 concepts across several categories, score them, then choose roughly 8-12 release candidates. This document is that step, in full.

## Portfolio decision

11 selected from a pool of 34.

| Constraint (section 33) | Met |
|---|---|
| size 8 to 12 | yes |
| flagship seasonal | yes |
| several quick low price | yes |
| bundle ready family | yes |
| evergreen search product | yes |
| class c limited | yes |
| category spread | yes |
| bundles have members | yes |

Ranking alone would not have satisfied those constraints. The selector made these swaps, each one deliberately choosing a lower score to avoid concentrating the portfolio in a single demand pattern:

- swapped pet-snuggle-mat (score 0.6263) for nordic-star-ornaments (score 0.62) to satisfy bundle_ready_family
- added nordic-forest-bundle (score 0.7796): 2 members of family 'nordic-forest' are in the portfolio, so the bundle is fulfillable

## Selected release candidates

| # | Concept | Category | Class | CA$ | Score | Window / status |
|---|---|---|---|---|---|---|
| 1 | **Nordic Forest Collection Bundle** | seasonal_decor | A | 24.00 | 0.7796 | Christmas: ready 2026-09-24, window open 2026-07-19..2026-11-11 |
| 2 | **Nordic Forest Overlay Mosaic Throw** | mosaic_blanket | A | 12.50 | 0.7463 | Christmas: ready 2026-09-24, window open 2026-08-20..2026-11-18 |
| 3 | **Winter Village Graphghan** | graphghan | A | 10.50 | 0.7188 | Christmas: ready 2026-09-24, window open 2026-07-31..2026-11-13 |
| 4 | **Heirloom Cable Throw** | blanket | A | 11.50 | 0.6881 | evergreen: no window to miss |
| 5 | **Cloudline Textured Baby Blanket** | baby | A | 8.50 | 0.6763 | evergreen: no window to miss |
| 6 | **Harvest Table Runner** | runner | A | 6.50 | 0.6725 | Thanksgiving (CA): ready 2026-09-24, window open 2026-08-29..2026-10-01 |
| 7 | **Spooky Bunting Garland** | seasonal_decor | A | 4.50 | 0.6457 | Halloween: ready 2026-09-24, window open 2026-09-22..2026-10-23 |
| 8 | **Market Basket Trio** | basket | A | 6.50 | 0.6430 | evergreen: no window to miss |
| 9 | **Autumn Oak Overlay Mosaic Throw** | mosaic_blanket | A | 12.50 | 0.6355 | Thanksgiving (CA): ready 2026-09-24, window closed 2026-09-05 (missed) |
| 10 | **Pressed Flower Motif Library (12)** | flower | A | 6.00 | 0.6327 | evergreen: no window to miss |
| 11 | **Nordic Star Ornament Set (6)** | ornament | A | 5.50 | 0.6200 | Christmas: ready 2026-09-24, window opens 2026-11-17 (early) |

### Nordic Forest Collection Bundle

`nordic-forest-bundle` · seasonal_decor · Class A · CA$24.00 · maker 37-76h · our build lead 7d · family `nordic-forest`

Every profiled competitor sells family members individually and none bundles them. The bundle costs us almost nothing once the members exist and lifts order value well above the CA$8-12 ceiling the category has settled into.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.80 | 0.30 | 1.00 | 0.83 | 1.00 | 0.85 | **0.7796** |

### Nordic Forest Overlay Mosaic Throw

`nordic-forest-mosaic-throw` · mosaic_blanket · Class A · CA$12.50 · maker 30-60h · our build lead 7d · family `nordic-forest`

Overlay mosaic is the strongest demand signal we observed and it is pure Class A geometry: every row is a countable sequence the compiler can verify end to end. Our differentiation is three finished sizes from one chart, which no profiled competitor offers.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.92 | 0.12 | 1.00 | 0.76 | 0.89 | 0.72 | **0.7463** |

### Winter Village Graphghan

`winter-village-graphghan` · graphghan · Class A · CA$10.50 · maker 35-70h · our build lead 7d

Graphghans are chart-native, which plays directly to our chart rendering, and the category is markedly less crowded than mosaic.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.70 | 0.38 | 1.00 | 0.81 | 0.75 | 0.66 | **0.7188** |

### Heirloom Cable Throw

`heirloom-cable-blanket` · blanket · Class A · CA$11.50 · maker 25-50h · our build lead 7d

Texture rather than colourwork; a different buyer from the mosaic audience and still fully countable.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.85 | 0.20 | 1.00 | 0.55 | 0.82 | 0.55 | **0.6881** |

### Cloudline Textured Baby Blanket

`cloudline-baby-blanket` · baby · Class A · CA$8.50 · maker 6-16h · our build lead 7d · family `cloudline`

Baby demand does not wait for a holiday and the make time is short enough that the buy window is always open. Evergreen search anchor.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.82 | 0.25 | 1.00 | 0.55 | 0.61 | 0.64 | **0.6763** |

### Harvest Table Runner

`harvest-table-runner` · runner · Class A · CA$6.50 · maker 4-9h · our build lead 7d

Thin shelf, clear seasonal pull, and a runner is a rectangle: fully verifiable.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.42 | 0.68 | 1.00 | 0.92 | 0.46 | 0.58 | **0.6725** |

### Spooky Bunting Garland

`spooky-garland` · seasonal_decor · Class A · CA$4.50 · maker 1.5-4h · our build lead 7d

Small, fast, and Halloween is the nearest event with an open window.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.80 | 0.30 | 1.00 | 0.63 | 0.32 | 0.48 | **0.6457** |

### Market Basket Trio

`market-basket-trio` · basket · Class A · CA$6.50 · maker 2-6h · our build lead 7d

Three sizes from one set of instructions; the sizing maths is exactly what our compiler is for.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.62 | 0.50 | 1.00 | 0.55 | 0.46 | 0.56 | **0.6430** |

### Autumn Oak Overlay Mosaic Throw

`autumn-oak-mosaic-throw` · mosaic_blanket · Class A · CA$12.50 · maker 30-55h · our build lead 7d · family `autumn-oak`

Autumn mosaic is the single best-evidenced listing we found. The window for a throw is however nearly closed this year; strong for next season, weak for now. Scored honestly against the autumn window rather than parked as evergreen.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.92 | 0.12 | 1.00 | 0.05 | 0.89 | 0.60 | **0.6355** |

### Pressed Flower Motif Library (12)

`pressed-flower-motifs` · flower · Class A · CA$6.00 · maker 0.5-2h · our build lead 7d

A motif library is reusable inventory for us, not just a product: section 5's 'reusable original validated motif libraries' in literal form.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.56 | 0.50 | 1.00 | 0.55 | 0.43 | 0.66 | **0.6327** |

### Nordic Star Ornament Set (6)

`nordic-star-ornaments` · ornament · Class A · CA$5.50 · maker 1-3h · our build lead 7d · family `nordic-forest`

Flat, countable, one evening to make, and it seeds the Nordic motif library that the throw and stocking reuse. Fastest path to first reviews.

| demand | competition headroom | verifiability | seasonal fit | margin | whitespace | **score** |
|---|---|---|---|---|---|---|
| 0.72 | 0.45 | 1.00 | 0.21 | 0.39 | 0.68 | **0.6200** |

## Full ranking

| Rank | Concept | Cat | Cls | Score | demand | competition headroom | verifiability | seasonal fit | margin | whitespace | In |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Nordic Forest Collection Bundle | seasonal_decor | A | 0.7796 | 0.80 | 0.30 | 1.00 | 0.83 | 1.00 | 0.85 | yes |
| 2 | Nordic Forest Overlay Mosaic Throw | mosaic_blanket | A | 0.7463 | 0.92 | 0.12 | 1.00 | 0.76 | 0.89 | 0.72 | yes |
| 3 | Winter Village Graphghan | graphghan | A | 0.7188 | 0.70 | 0.38 | 1.00 | 0.81 | 0.75 | 0.66 | yes |
| 4 | Heirloom Cable Throw | blanket | A | 0.6881 | 0.85 | 0.20 | 1.00 | 0.55 | 0.82 | 0.55 | yes |
| 5 | Cloudline Textured Baby Blanket | baby | A | 0.6763 | 0.82 | 0.25 | 1.00 | 0.55 | 0.61 | 0.64 | yes |
| 6 | Harvest Table Runner | runner | A | 0.6725 | 0.42 | 0.68 | 1.00 | 0.92 | 0.46 | 0.58 | yes |
| 7 | Spooky Bunting Garland | seasonal_decor | A | 0.6457 | 0.80 | 0.30 | 1.00 | 0.63 | 0.32 | 0.48 | yes |
| 8 | Market Basket Trio | basket | A | 0.6430 | 0.62 | 0.50 | 1.00 | 0.55 | 0.46 | 0.56 | yes |
| 9 | Autumn Oak Overlay Mosaic Throw | mosaic_blanket | A | 0.6355 | 0.92 | 0.12 | 1.00 | 0.05 | 0.89 | 0.60 | yes |
| 10 | Pressed Flower Motif Library (12) | flower | A | 0.6327 | 0.56 | 0.50 | 1.00 | 0.55 | 0.43 | 0.66 | yes |
| 11 | Pet Snuggle Mat | pet | A | 0.6263 | 0.52 | 0.60 | 1.00 | 0.55 | 0.36 | 0.60 |  |
| 12 | Mosaic Placemat Pair | placemat | A | 0.6213 | 0.45 | 0.65 | 1.00 | 0.55 | 0.39 | 0.62 |  |
| 13 | Nordic Star Ornament Set (6) | ornament | A | 0.6200 | 0.72 | 0.45 | 1.00 | 0.21 | 0.39 | 0.68 | yes |
| 14 | Hexagon Coaster Set | coaster | A | 0.6135 | 0.60 | 0.48 | 1.00 | 0.55 | 0.32 | 0.50 |  |
| 15 | Chunky Ribbed Scarf | scarf | A | 0.5987 | 0.64 | 0.34 | 1.00 | 0.55 | 0.39 | 0.42 |  |
| 16 | Pumpkin Cluster Set (3 sizes) | seasonal_decor | B | 0.5873 | 0.80 | 0.30 | 0.62 | 0.65 | 0.39 | 0.55 |  |
| 17 | Cloudline Baby Hat Set | baby | B | 0.5699 | 0.82 | 0.25 | 0.62 | 0.55 | 0.39 | 0.55 |  |
| 18 | Nordic Forest Mosaic Storage Basket | basket | B | 0.5690 | 0.62 | 0.50 | 0.62 | 0.55 | 0.46 | 0.58 |  |
| 19 | Heart Motif Garland | seasonal_decor | A | 0.5663 | 0.80 | 0.30 | 1.00 | 0.09 | 0.32 | 0.44 |  |
| 20 | Everyday Market Tote | bag | B | 0.5618 | 0.66 | 0.38 | 0.62 | 0.55 | 0.54 | 0.54 |  |
| 21 | Bobble Floor Pillow | pillow | B | 0.5590 | 0.58 | 0.52 | 0.62 | 0.55 | 0.50 | 0.52 |  |
| 22 | Lattice Triangle Shawl | shawl | B | 0.5577 | 0.58 | 0.42 | 0.62 | 0.55 | 0.61 | 0.58 |  |
| 23 | Nursery Cloud and Star Mobile | nursery | B | 0.5564 | 0.60 | 0.45 | 0.62 | 0.55 | 0.46 | 0.60 |  |
| 24 | Woodland Fox Amigurumi | amigurumi | B | 0.5563 | 0.88 | 0.10 | 0.62 | 0.55 | 0.43 | 0.48 |  |
| 25 | Cottage Botanical Wall Hanging | wall_decor | B | 0.5536 | 0.50 | 0.55 | 0.62 | 0.55 | 0.54 | 0.60 |  |
| 26 | Alpine Slouch Beanie | hat | B | 0.5442 | 0.74 | 0.22 | 0.62 | 0.55 | 0.46 | 0.50 |  |
| 27 | Nordic Forest Mosaic Stocking | stocking | B | 0.5342 | 0.68 | 0.40 | 0.62 | 0.23 | 0.54 | 0.62 |  |
| 28 | Everyday Cropped Cardigan | garment | C | 0.5254 | 0.70 | 0.28 | 0.22 | 0.55 | 1.00 | 0.58 |  |
| 29 | No-Sew Reindeer Amigurumi | amigurumi | B | 0.5249 | 0.88 | 0.10 | 0.62 | 0.22 | 0.36 | 0.70 |  |
| 30 | Wedding Ring Cushion | wedding | B | 0.5210 | 0.40 | 0.62 | 0.62 | 0.55 | 0.46 | 0.50 |  |
| 31 | Boxy Summer Tee | garment | C | 0.5198 | 0.70 | 0.28 | 0.22 | 0.55 | 0.96 | 0.56 |  |
| 32 | Pocket Penguin Trio | amigurumi | B | 0.5108 | 0.88 | 0.10 | 0.62 | 0.22 | 0.39 | 0.52 |  |
| 33 | Easter Egg Cosy Set | seasonal_decor | B | 0.4801 | 0.80 | 0.30 | 0.62 | 0.00 | 0.32 | 0.46 |  |
| 34 | Mother's Day Lace Shawlette | shawl | B | 0.4747 | 0.58 | 0.42 | 0.62 | 0.00 | 0.61 | 0.52 |  |

## How the score is computed

Weighted sum of six components, each 0-1. Weights:

- **demand** — 0.28
- **competition headroom** — 0.18
- **verifiability** — 0.20
- **seasonal fit** — 0.14
- **margin** — 0.10
- **whitespace** — 0.10

No model is asked to rank concepts. A model is good at proposing concepts and bad at being consistent about why one beats another, and "the model preferred it" is not a reason anyone can audit six weeks later when a SKU underperforms.

## Category evidence

| Category | Demand | Competition | Headroom |
|---|---|---|---|
| amigurumi | 0.88 | 0.90 | -0.02 |
| baby | 0.82 | 0.75 | +0.07 |
| bag | 0.66 | 0.62 | +0.04 |
| basket | 0.62 | 0.50 | +0.12 |
| blanket | 0.85 | 0.80 | +0.05 |
| coaster | 0.60 | 0.52 | +0.08 |
| flower | 0.56 | 0.50 | +0.06 |
| garment | 0.70 | 0.72 | -0.02 |
| graphghan | 0.70 | 0.62 | +0.08 |
| hat | 0.74 | 0.78 | -0.04 |
| mosaic_blanket | 0.92 | 0.88 | +0.04 |
| nursery | 0.60 | 0.55 | +0.05 |
| ornament | 0.72 | 0.55 | +0.17 |
| pet | 0.52 | 0.40 | +0.12 |
| pillow | 0.58 | 0.48 | +0.10 |
| placemat | 0.45 | 0.35 | +0.10 |
| quick_make | 0.75 | 0.68 | +0.07 |
| runner | 0.42 | 0.32 | +0.10 |
| scarf | 0.64 | 0.66 | -0.02 |
| seasonal_decor | 0.80 | 0.70 | +0.10 |
| shawl | 0.58 | 0.58 | +0.00 |
| stocking | 0.68 | 0.60 | +0.08 |
| tree_skirt | 0.55 | 0.45 | +0.10 |
| wall_decor | 0.50 | 0.45 | +0.05 |
| wedding | 0.40 | 0.38 | +0.02 |

## Competitor profiles

### HanJanCrochet

Premium overlay-mosaic blankets, pattern + video, strong seasonal cadence. Observed 2026-09-17 at CA$8.47-11.65. Discounting: 50% off displayed with a countdown timer; regular price ~CA$23.30.

- **Strength.** 'Bestseller in Patterns & Blueprints, 200+ bought in the last week' on the fall blanket; 8.4k reviews on the hero listing. Photography is warm, styled and consistent across the grid.
- **Gap we can attack.** Charts are images rather than interactive; sizing options are limited to one finished size per pattern.
- **Formats.** PATTERN + VIDEO, PDF, mosaic overlay, seasonal collections

### MJsOffTheHookDesigns

Seasonal mosaic and colourwork blankets ('Autumn's Charm'). Observed 2026-09-17 at CA$8.47-11.64. Discounting: 50% off as a standing display price.

- **Strength.** Broad seasonal family: blanket, stocking, basket and tree skirt in one visual language, which cross-sells.
- **Gap we can attack.** Family members are sold individually; no obvious bundle at a bundle price.
- **Formats.** PATTERN + VIDEO, mosaic, stockings, tree skirts, baskets

### FireflyCrochets

Character amigurumi (Christmas moose/reindeer). Observed 2026-09-17 at CA$2.75-8.78. Discounting: frequent deep discounts on older listings.

- **Strength.** Low price point drives volume and review accumulation.
- **Gap we can attack.** Amigurumi is Class B/C for validation -- harder for us to guarantee early.
- **Formats.** PDF, amigurumi, no-sew variants

### LoveandStitchDesigns

Everyday garments and striped wearables. Observed 2026-09-17 at CA$9.90-14.05. Discounting: 55% off from ~CA$22.00.

- **Strength.** A single recurring model across the grid makes the shop read as one brand.
- **Gap we can attack.** Garments are Class C: they need physical testing, which is slow for us at first.
- **Formats.** PATTERN + VIDEO, garments, recurring human model

### IvyLoop

Seeded by owner; profile to be filled on first live scan. Observed 2026-09-17 at CA$0.00-0.00.

- **Strength.** Not yet observed.
- **Gap we can attack.** Not yet observed.

Competitor research is demand and merchandising intelligence only. No competitor instructions, charts, photography or protected designs are copied, referenced as source material, or used to derive a pattern.

## Category-level observations

- **price band** — Crochet patterns cluster at CA$4-12; premium pattern+video sits CA$8.50-14. Etsy takes 6.5% transaction + 3% + CA$0.25 processing.
- **discount norm** — Near-universal '50-60% off' display pricing with a struck-through reference price. Section 9 forbids us running a perpetual fake sale, so we price honestly at the real number and compete on trust and quality.
- **video is table stakes** — The top sellers in mosaic/blankets all advertise 'PATTERN + VIDEO'. A pattern without a tutorial reads as lower value.
- **mosaic demand** — Overlay mosaic Christmas blankets show heavy favouriting (one listing at 4,794 favourites, another at 1,789). Nordic/forest/festive motifs recur across shops.
- **seasonal families** — Winners ship a family -- blanket, stocking, basket, tree skirt, ornament -- in one visual language, but rarely bundle them.
- **amigurumi volume** — Amigurumi sells at CA$2.75-8.78 with very high review counts (43.2k on one collection), but it is Class B/C to validate.
- **review moat** — Category leaders hold 8k-43k reviews. We cannot out-review them; we can out-specify them on accuracy, sizing options and chart quality.

## Buying windows

Shopping date is modelled separately from making date (section 5). A 60-hour throw bought in December cannot be finished for Christmas, so the demand peak for a Christmas blanket pattern is autumn, and a radar sorted by "days until the holiday" would be wrong by three months.

| Event | Date | Typical make | Buy window | Status today |
|---|---|---|---|---|
| Christmas | 2026-12-25 | 30-60h | 2026-08-20 → 2026-11-18 | open |
| Halloween | 2026-10-31 | 2-8h | 2026-09-18 → 2026-10-22 | not yet |
| Thanksgiving (CA) | 2026-10-12 | 2-10h | 2026-08-28 → 2026-10-03 | open |
| Valentine's | 2027-02-14 | 2-8h | 2027-01-02 → 2027-02-05 | not yet |
| Easter | 2027-04-04 | 2-8h | 2027-02-20 → 2027-03-26 | not yet |
| Mother's Day | 2027-05-09 | 4-15h | 2027-03-20 → 2027-04-28 | not yet |

