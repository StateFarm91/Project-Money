# Product pipeline backlog (W4-PIPE)

Generated 2026-10-07T01:44:01+00:00 at `e72f086` by `research/final_build/w4/pipeline_run.py` (shadow, scratch DB + scratch artefact store). Stages: INTELLIGENCE → DESIGN → PRODUCT → PRODUCT_TRUTH → VISUAL → SEARCH → LISTING_READINESS → PUBLICATION. Publication is never advanced (`advances_publication` = False).

## Candidates at each stage (current stage = first stage not PASS)

| stage | at stage | passed |
|---|---|---|
| INTELLIGENCE | 0 | 57 |
| DESIGN | 30 | 27 |
| PRODUCT | 0 | 27 |
| PRODUCT_TRUTH | 7 | 20 |
| VISUAL | 15 | 5 |
| SEARCH | 5 | 0 |
| LISTING_READINESS | 0 | 0 |
| PUBLICATION | 0 | 0 |

Competitor findings as of 2026-10-07 (intel.findings; demand and merchandising intelligence only).

## Bundle families (mjs.findings bundle_premium)

| family | members | cleared Product Truth | ready to price |
|---|---|---|---|
| kitchen_texture | diamond-lattice-dishcloth, basketweave-textured-washcloth, basketweave-textured-hand-towel, mosaic-placemat-pair | diamond-lattice-dishcloth, basketweave-textured-washcloth, basketweave-textured-hand-towel, mosaic-placemat-pair | True |
| table_runners | heart-relief-table-runner, pumpkin-relief-table-runner, fir-star-relief-table-runner | heart-relief-table-runner, pumpkin-relief-table-runner, fir-star-relief-table-runner | True |

## Backlog

| candidate | source | stage | status | next step | clearer |
|---|---|---|---|---|---|
| cloudline-baby-blanket | launch0 | SEARCH | FAIL | fix the listing copy the gates refuse | COMPANY |
| hexagon-coaster-set | launch0 | SEARCH | FAIL | fix the listing copy the gates refuse | COMPANY |
| market-basket-large | launch0 | SEARCH | FAIL | fix the listing copy the gates refuse | COMPANY |
| market-basket-medium | launch0 | SEARCH | FAIL | fix the listing copy the gates refuse | COMPANY |
| market-basket-small | launch0 | SEARCH | FAIL | fix the listing copy the gates refuse | COMPANY |
| basketweave-textured-hand-towel | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| basketweave-textured-washcloth | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| chevron-relief-scarf | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| cottage-wall-hanging | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| diamond-lattice-dishcloth | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| fir-star-relief-table-runner | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| harvest-table-runner | catalogue | VISUAL | FAIL | renderer refused this design (W4-CREATIVE owns the renderer; the gate is not relaxed): change the palette/design to one it can draw and verify | COMPANY |
| heart-relief-table-runner | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| mosaic-placemat-pair | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| nordic-star-ornaments | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| pet-snuggle-mat | catalogue | VISUAL | FAIL | renderer refused this design (W4-CREATIVE owns the renderer; the gate is not relaxed): change the palette/design to one it can draw and verify | COMPANY |
| pressed-flower-motifs | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| pumpkin-relief-table-runner | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| teacher-chevron-pencil-roll | creative | VISUAL | FAIL | renderer refused this design (W4-CREATIVE owns the renderer; the gate is not relaxed): change the palette/design to one it can draw and verify | COMPANY |
| winter-village-graphghan | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| autumn-oak-mosaic-throw | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| bobble-floor-pillow | catalogue | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch (physical calibration) | OWNER |
| chunky-ribbed-scarf | catalogue | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch (physical calibration) | OWNER |
| heirloom-cable-blanket | catalogue | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch (physical calibration) | OWNER |
| nordic-forest-mosaic-throw | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| spooky-garland | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| valentine-heart-garland | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| alpine-slouch-beanie | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| boxy-summer-tee | radar_pool | DESIGN | NOT_RUN | Class C: needs physical testing and graded sizing before design (OWNER/tester) | COMPANY |
| cloudline-baby-hat | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| cropped-cardigan | radar_pool | DESIGN | NOT_RUN | Class C: needs physical testing and graded sizing before design (OWNER/tester) | COMPANY |
| easter-egg-cosies | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| everyday-market-tote | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| first-christmas-stocking | creative | DESIGN | NOT_RUN | engineer a in_the_round builder for a stocking (fir-and-star, forest and cream); the products.builder tiler makes flat rows only | COMPANY |
| gap-amigurumi-and-soft-sculpture | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| gap-education-and-guidebooks | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| gap-garments-and-clothing | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| gap-hats-and-wearables | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| heart-row-ring-pillow | creative | DESIGN | NOT_RUN | engineer a in_the_round builder for a pillow (heart-row, cream and wine); the products.builder tiler makes flat rows only | COMPANY |
| hexie-coaster-set | catalogue | DESIGN | BLOCKED | retired concept: its design ships as hexagon-coaster-set | COMPANY |
| housewarming-key-basket | creative | DESIGN | NOT_RUN | engineer a in_the_round builder for a basket (basketweave, pine and cream); the products.builder tiler makes flat rows only | COMPANY |
| lattice-triangle-shawl | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| market-basket-trio | catalogue | DESIGN | BLOCKED | retired concept: its design ships as market-basket-small, market-basket-medium, market-basket-large | COMPANY |
| mothers-day-heart-tea-cosy | creative | DESIGN | NOT_RUN | engineer a seamless_tube builder for a tube (heart-row, cream and wine); the products.builder tiler makes flat rows only | COMPANY |
| mothers-day-shawlette | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| no-sew-reindeer | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nordic-forest-basket | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nordic-forest-bundle | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nordic-forest-stocking | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nursery-cloud-mobile | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| pocket-penguin-trio | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| pumpkin-cluster-set | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| reading-nook-cable-wrap | creative | DESIGN | NOT_RUN | engineer a side_to_side builder for a draped_garment (cable-twist, forest and cream); the products.builder tiler makes flat rows only | COMPANY |
| snowfall-advent-garland | creative | DESIGN | NOT_RUN | engineer a motif_join builder for a garland (snowfall, forest and cream); the products.builder tiler makes flat rows only | COMPANY |
| spring-garden-kneeler | creative | DESIGN | NOT_RUN | engineer a modular_panels builder for a pillow (tulip-trellis, pine and gold); the products.builder tiler makes flat rows only | COMPANY |
| wedding-ring-cushion | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| woodland-fox-amigurumi | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
