# SEO packages: every catalogue product's Etsy search package (W4-SEO)

Generated 2026-10-07T01:33:48+00:00 by `research/final_build/w4/seo_packages_build.py (real release chain, shadow worker, scratch SQLite, network closed, no Etsy taxonomy snapshot)`. The machine record is `SEO_PACKAGES.json`; packages are also persisted by `listing.seo` in `seo_search_packages` (`seo.packages`) and refreshed by every `seo.cycle`.

## Counts

- Products with a CIR: **21**
- Viable (Product Truth clean: title, assembly and fabric promises backed): **7**; not viable: 14
- Listings drafted by the real chain: **15**
- Search packages persisted: **17** (7 for viable products)
- Search certificate PASS: **0**; FAIL/REFUSED: **17**
- Readiness: {'EXTERNAL_GATED': 5, 'BLOCKED': 12}
- Supremacy gate cleared: False (failed ['conversion_readiness', 'truthful_query_coverage'], unmeasured ['competitive_thumbnail', 'no_unresolved_first_party_warning'])

## Why the certificate fails

The F-004 search certificate needs a category CHOSEN from a stored Etsy seller-taxonomy snapshot. None exists: there is no app keystring in this environment and the read-only endpoint answers 403 without one, so no taxonomy id is assumed and the `category` and `attributes` checks fail. For a package marked EXTERNAL_GATED every other check passes: copy, tags, description and the hero. The gate: etsy_taxonomy_read: listing.taxonomy_refresh needs the app keystring (ETSY_KEYSTRING / ETSY_API_KEY, read-only GET /seller-taxonomy/*); no Etsy taxonomy snapshot is stored, so no category id is chosen and none is assumed.

Search volume: none. No Etsy search-volume figure is measured for any phrase. Tag bases are `observed` (dated buyer language) or `modelled` (query-model templates). The model's demand and competition constants are not copied into packages.

## Per product

Competitor context: `research/final_build/w4/MJS_FINDINGS.json` (as of 2026-10-07; one benchmark seller, production public read-only endpoints). Benchmark price IQR is `observed` for that seller; favourites are a demand `proxy`; seasonal pods are a seasonality `proxy`. It is not the Etsy market and no competitor copy is stored.

| Product | Viable | PIPE status | Readiness | Certificate | Title (chars) | Tags (basis) | Price CAD | Benchmark pod: median (IQR) → position | Fav. proxy | Primary intent |
|---|---|---|---|---|---|---|---|---|---|---|
| autumn-oak-mosaic-throw | False | COMPANY_WORK | no package | - | - | - | - | - | - | fabric claim: claims 'mosaic'; the fabric puts at most 1 colour(s) in any one row, and a two-colour motif needs two |
| bobble-floor-pillow | False | COMPANY_WORK | no package | - | - | - | - | - | - | not in products.launch0 inventory (no Product Truth gate run there); PIPE: physical_calibration (OWNER); outside_launch_scope (COMPANY); not_built_by_planner (C |
| chunky-ribbed-scarf | False | COMPANY_WORK | no package | - | - | - | - | - | - | not in products.launch0 inventory (no Product Truth gate run there); PIPE: physical_calibration (OWNER); outside_launch_scope (COMPANY); not_built_by_planner (C |
| cloudline-baby-blanket | True | OWNER_AND_DEPLOY_GATED | EXTERNAL_GATED | REFUSED (failed ['category', 'attributes']) | Cloudline Textured Baby Blanket | Crochet Pattern PDF | Written Instru... (104) | 13 (obs 0, mod 13, meas 0) | 7.5 | blankets: 18.0 (18.0-18.0, n=85) → below benchmark p25 | 1400.0 | baby crochet pattern pdf |
| cottage-wall-hanging | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Cottage Botanical Wall Hanging | Crochet Pattern PDF | Decor | US and ... (78) | 13 (obs 0, mod 13, meas 0) | 6.21 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | wall decor crochet pattern pdf |
| harvest-table-runner | True | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Harvest Table Runner | Crochet Pattern PDF | Written Instructions and ... (93) | 13 (obs 0, mod 13, meas 0) | 6.94 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | runner crochet pattern pdf |
| heirloom-cable-blanket | False | COMPANY_WORK | no package | - | - | - | - | - | - | not in products.launch0 inventory (no Product Truth gate run there); PIPE: physical_calibration (OWNER); outside_launch_scope (COMPANY); not_built_by_planner (C |
| hexagon-coaster-set | True | COMPANY_WORK | EXTERNAL_GATED | REFUSED (failed ['category', 'attributes']) | Hexagon Coaster Set | Crochet Pattern PDF | Written Instructions and C... (92) | 13 (obs 0, mod 13, meas 0) | 4.0 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | coaster crochet pattern pdf |
| market-basket-large | True | OWNER_AND_DEPLOY_GATED | EXTERNAL_GATED | REFUSED (failed ['category', 'attributes']) | Hexagonal Market Basket | Crochet Pattern PDF | Nursery | Written Inst... (106) | 13 (obs 0, mod 13, meas 0) | 6.5 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | basket crochet pattern pdf |
| market-basket-medium | True | OWNER_AND_DEPLOY_GATED | EXTERNAL_GATED | REFUSED (failed ['category', 'attributes']) | Hexagonal Storage Basket | Crochet Pattern PDF | Nursery | Written Ins... (107) | 13 (obs 0, mod 13, meas 0) | 6.5 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | basket crochet pattern pdf |
| market-basket-small | True | OWNER_AND_DEPLOY_GATED | EXTERNAL_GATED | REFUSED (failed ['category', 'attributes']) | Hexagonal Bread Basket | Crochet Pattern PDF | Nursery | Written Instr... (105) | 13 (obs 0, mod 13, meas 0) | 6.5 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | basket crochet pattern pdf |
| mosaic-placemat-pair | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Mosaic Placemat Pair | Crochet Pattern PDF | Written Instructions and ... (93) | 13 (obs 0, mod 13, meas 0) | 5.98 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | placemat crochet pattern pdf |
| nordic-forest-mosaic-throw-baby | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'copy']) | ... (0) | 0 (obs 0, mod 0, meas 0) | 13.37 | blankets: 18.0 (18.0-18.0, n=85) → below benchmark p25 | 1400.0 | mosaic blanket crochet pattern pdf |
| nordic-forest-mosaic-throw-large | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'copy']) | ... (0) | 0 (obs 0, mod 0, meas 0) | 14.0 | blankets: 18.0 (18.0-18.0, n=85) → below benchmark p25 | 1400.0 | mosaic blanket crochet pattern pdf |
| nordic-forest-mosaic-throw-throw | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Nordic Forest Overlay Mosaic Throw | Crochet Pattern PDF | Christmas |... (96) | 13 (obs 0, mod 13, meas 0) | 14.0 | blankets: 18.0 (18.0-18.0, n=85) → below benchmark p25 | 1400.0 | mosaic blanket crochet pattern pdf |
| nordic-star-ornaments | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Nordic Star Ornament Set (6) | Crochet Pattern PDF | Christmas | US an... (80) | 13 (obs 0, mod 13, meas 0) | 4.63 | ornaments: 18.0 (17.0-18.0, n=13) → below benchmark p25 | 435.0 | ornament crochet pattern pdf |
| pet-snuggle-mat | True | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Pet Snuggle Mat | Crochet Pattern PDF | Written Instructions and Chart... (88) | 13 (obs 0, mod 13, meas 0) | 5.11 | seasonal_gift: 18.0 (18.0-18.0, n=10) → below benchmark p25 | 491.0 | pet crochet pattern pdf |
| pressed-flower-motifs | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Pressed Flower Motif Library (12) | Crochet Pattern PDF | US and UK Te... (73) | 13 (obs 0, mod 13, meas 0) | 4.83 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | flower crochet pattern pdf |
| spooky-garland | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Spooky Bunting Garland | Crochet Pattern PDF | Halloween | Seasonal De... (91) | 13 (obs 0, mod 13, meas 0) | 5.23 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | seasonal decor crochet pattern pdf |
| valentine-heart-garland | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Heart Motif Garland | Crochet Pattern PDF | Valentine's | Seasonal Dec... (90) | 13 (obs 0, mod 13, meas 0) | 5.23 | home_decor: 18.0 (17.5-18.0, n=11) → below benchmark p25 | 911.0 | seasonal decor crochet pattern pdf |
| winter-village-graphghan | False | COMPANY_WORK | BLOCKED | REFUSED (failed ['category', 'attributes', 'hero']) | Winter Village Graphghan | Crochet Pattern PDF | Christmas | Written I... (109) | 13 (obs 0, mod 13, meas 0) | 12.0 | blankets: 18.0 (18.0-18.0, n=85) → below benchmark p25 | 1400.0 | graphghan crochet pattern pdf |

## Findings for other departments

- Pricing: 17 of 17 packaged products are priced below the benchmark seller's observed p25 for their pod (benchmark pattern medians CA$18-22). This is one seller's shelf, not the market, and price is decided by `pricing.position`; it is recorded as evidence for the pricing inbox, not acted on here.
- Viable but BLOCKED on the hero image (company imagery work): harvest-table-runner, pet-snuggle-mat.
- Every other viable product is EXTERNAL_GATED: only the Etsy taxonomy read remains.

## Not viable: Product Truth findings

- `autumn-oak-mosaic-throw`: fabric claim: claims 'mosaic'; the fabric puts at most 1 colour(s) in any one row, and a two-colour motif needs two
- `bobble-floor-pillow`: not in products.launch0 inventory (no Product Truth gate run there); PIPE: physical_calibration (OWNER); outside_launch_scope (COMPANY); not_built_by_planner (COMPANY)
- `chunky-ribbed-scarf`: not in products.launch0 inventory (no Product Truth gate run there); PIPE: physical_calibration (OWNER); outside_launch_scope (COMPANY); not_built_by_planner (COMPANY)
- `cottage-wall-hanging`: assembly promise: the title names 'wall hanging'; the CIR carries 0 seams and 1 pieces
- `heirloom-cable-blanket`: not in products.launch0 inventory (no Product Truth gate run there); PIPE: physical_calibration (OWNER); outside_launch_scope (COMPANY); not_built_by_planner (COMPANY); production_stale (DEPLOY)
- `mosaic-placemat-pair`: title promise: the title claims 2 pieces and the CIR makes 1; fabric claim: claims 'mosaic'; the fabric puts at most 1 colour(s) in any one row, and a two-colour motif needs two
- `nordic-forest-mosaic-throw-baby`: fabric claim: claims 'mosaic'; the fabric puts at most 1 colour(s) in any one row, and a two-colour motif needs two
- `nordic-forest-mosaic-throw-large`: fabric claim: claims 'mosaic'; the fabric puts at most 1 colour(s) in any one row, and a two-colour motif needs two
- `nordic-forest-mosaic-throw-throw`: fabric claim: claims 'mosaic'; the fabric puts at most 1 colour(s) in any one row, and a two-colour motif needs two
- `nordic-star-ornaments`: title promise: the title claims 6 pieces and the CIR makes 1
- `pressed-flower-motifs`: title promise: the title claims 12 pieces and the CIR makes 1
- `spooky-garland`: assembly promise: the title names 'garland'; the CIR carries 0 seams and 1 pieces
- `valentine-heart-garland`: assembly promise: the title names 'garland'; the CIR carries 0 seams and 1 pieces
- `winter-village-graphghan`: fabric claim: claims 'graphghan'; the fabric puts at most 1 colour(s) in any one row, and a two-colour motif needs two

These products may still have a drafted listing and a package, because `listing.seo` blocks product-identity findings only for Launch-0. Their readiness is not a sale decision: a product whose title promises what its CIR does not make must be re-engineered or renamed before it is merchandised.

## Post-launch update loop

Owner listing-level Stats export → `commerce.listing_outcomes.submit_export` → `produce` (ListingOutcome rows, carts in detail) → next `seo.cycle` (`seo.jobs.run_cycle` → `seo.packages.refresh`) writes a new package version. Its `learning` block carries impressions, visits, favourites, carts, orders and the funnel diagnosis. Search-term export → `POST /api/attribution/stats` → `seo.evidence` → per-tag `measured` evidence with EARNING/VANITY learning. Proven with FIXTURE data in `tests/test_w4_seo_packages.py`. No real listing is live, so every real package's learning is UNKNOWN.
