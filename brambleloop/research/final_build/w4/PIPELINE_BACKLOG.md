# Product pipeline backlog (W4-PIPE)

Generated 2026-10-07T09:15:28+00:00 at `8e5f825` by `research/final_build/w4/pipeline_run.py` (shadow, scratch DB + scratch artefact store). Stages: INTELLIGENCE → DESIGN → PRODUCT → PRODUCT_TRUTH → VISUAL → SEARCH → LISTING_READINESS → PUBLICATION. Publication is never advanced (`advances_publication` = False).

## Candidates at each stage (current stage = first stage not PASS)

| stage | at stage | passed |
|---|---|---|
| INTELLIGENCE | 0 | 57 |
| DESIGN | 23 | 34 |
| PRODUCT | 0 | 34 |
| PRODUCT_TRUTH | 10 | 24 |
| VISUAL | 16 | 8 |
| SEARCH | 8 | 0 |
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
| cloudline-baby-blanket | launch0 | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| hexagon-coaster-set | launch0 | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| market-basket-large | launch0 | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| market-basket-medium | launch0 | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| market-basket-small | launch0 | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| nordic-star-ornaments | launch0 | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| pet-snuggle-mat | catalogue | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| winter-village-graphghan | launch0 | SEARCH | UNKNOWN | listing.taxonomy_refresh with the deployed app's Etsy read access (EXTERNAL), then listing.seo | EXTERNAL |
| basketweave-textured-hand-towel | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| basketweave-textured-washcloth | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| chevron-relief-scarf | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| cottage-wall-hanging | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| diamond-lattice-dishcloth | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| fir-star-relief-table-runner | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| first-christmas-stocking | creative | VISUAL | FAIL | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| harvest-table-runner | catalogue | VISUAL | FAIL | repair the frames the verifier/QA refused (renderer fixes: W4-RENDER; the gate is not relaxed) | COMPANY |
| heart-relief-table-runner | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| housewarming-key-basket | creative | VISUAL | FAIL | the disclosed renderer cannot name this round piece's outline (staggered increases: cir.geometry.corners returns None); renderer/geometry work | COMPANY |
| mosaic-placemat-pair | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| mothers-day-heart-tea-cosy | creative | VISUAL | FAIL | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| pressed-flower-motifs | catalogue | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| pumpkin-relief-table-runner | proposal | VISUAL | UNKNOWN | the pixel verifier's authority is the Launch-0 registry (D-FB-7): structural truth is UNKNOWN until the product is registered as a Launch-0 candidate (cap 5 pro | COMPANY |
| snowfall-advent-garland | creative | VISUAL | FAIL | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| teacher-chevron-pencil-roll | creative | VISUAL | FAIL | the disclosed renderer draws one compiled piece; an assembled multi-piece render is renderer work (visual owner; the gate is not relaxed) | COMPANY |
| autumn-oak-mosaic-throw | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| bobble-floor-pillow | catalogue | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch (physical calibration) | OWNER |
| chunky-ribbed-scarf | catalogue | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch (physical calibration) | OWNER |
| heart-row-ring-pillow | creative | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch or makes the full piece (physical evidence) | OWNER |
| heirloom-cable-blanket | catalogue | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch (physical calibration) | OWNER |
| nordic-forest-mosaic-throw | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| reading-nook-cable-wrap | creative | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch or makes the full piece (physical evidence) | OWNER |
| spooky-garland | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| spring-garden-kneeler | creative | PRODUCT_TRUTH | FAIL | a pattern tester works the new stitch or makes the full piece (physical evidence) | OWNER |
| valentine-heart-garland | catalogue | PRODUCT_TRUTH | FAIL | rename to what the fabric makes or change the CIR (new version) | COMPANY |
| alpine-slouch-beanie | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| boxy-summer-tee | radar_pool | DESIGN | NOT_RUN | Class C: needs physical testing and graded sizing before design (OWNER/tester) | COMPANY |
| cloudline-baby-hat | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| cropped-cardigan | radar_pool | DESIGN | NOT_RUN | Class C: needs physical testing and graded sizing before design (OWNER/tester) | COMPANY |
| easter-egg-cosies | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| everyday-market-tote | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| gap-amigurumi-and-soft-sculpture | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| gap-education-and-guidebooks | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| gap-garments-and-clothing | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| gap-hats-and-wearables | intelligence | DESIGN | NOT_RUN | W4-CREATIVE: write a moment-first brief (creative.emotional_brief) for this arena, then engineer a deterministic design; never copy the benchmark | COMPANY |
| hexie-coaster-set | catalogue | DESIGN | BLOCKED | retired concept: its design ships as hexagon-coaster-set | COMPANY |
| lattice-triangle-shawl | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| market-basket-trio | catalogue | DESIGN | BLOCKED | retired concept: its design ships as market-basket-small, market-basket-medium, market-basket-large | COMPANY |
| mothers-day-shawlette | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| no-sew-reindeer | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nordic-forest-basket | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nordic-forest-bundle | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nordic-forest-stocking | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| nursery-cloud-mobile | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| pocket-penguin-trio | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| pumpkin-cluster-set | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| wedding-ring-cushion | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
| woodland-fox-amigurumi | radar_pool | DESIGN | NOT_RUN | engineer a deterministic design (products.builder Design or a dedicated builder); prototype.FORM_GEOMETRY sizes: bag, basket, coaster, flat_panel, hat, ornament | COMPANY |
