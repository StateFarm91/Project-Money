# Catalogue reconciliation: the preview's five products, production's 16, and the proposed 8 (W4-CATALOG, 2026-10-11)

Branch `claude/w4-CATALOG`, based on `origin/claude/w4-INTEG2` (68224ac). Production runs `0417f35`.

All production evidence was read on 2026-10-11 with public GET requests:

- `/api/status`
- `/api/catalogue`
- `/api/launch`
- `/api/storefront/preview`

`/api/cc/store` and `/api/launch/packet` need an owner session (they returned 401), so they were
not read. Nothing was published, written or spent. Two products count as the same only where a
release hash shows it.

## 1. Why the preview shows these five products at these prices

The customer-style preview is the **Owner Store Preview**:

- `/cc/store-preview` renders `store_foundation.preview.render_preview`.
- That renders `surfaces["opening_grid"]`.
- That comes from `store_foundation.content.launch0_products(db)`.

`launch0_products` makes **one row per Launch-0 candidate** in
`products.launch0.LAUNCH0_SLUGS`. There are five candidates. The list is capped at 5 by
`test_launch0`, and the 8-product proposal (CAP-1) is not approved. A product with three sizes
is still one row.

For each row:

- **Variant shown:** the middle variant.
- **Title:** the drafted `Listing` row of that variant's release, if one exists. Otherwise the
  CIR title passed through `commerce.seo.build_title`. The card prints the full title. The
  five names quoted in the question are each title's first segment, before the first `|`; the
  banner's product-truth finding lists the same five names.
- **Price:** the drafted row's price, if one exists. Otherwise
  `launch0.launch_price` (the candidate's own price plan, decided by `commerce.pricing`).

None of this is a stored storefront. The page is recomputed from code and the database every
time it loads.

| preview card | candidate | release shown | title source | price source | in production DB? |
|---|---|---|---|---|---|
| Hexagonal Storage Basket CA$6.50 | `nursery-nesting-baskets` | `market-basket-medium@1.2.0` (middle of S/M/L) | CIR title "Crochet Hexagonal Storage Basket" with "Crochet" removed (S is "Bread Basket", L is "Market Basket") | `launch_price`: plan CA$6.50, CA$4–12 cluster, SOURCED | **No.** No `market-basket-*` release is stored. |
| Cloudline Textured Baby Blanket CA$7.50 | `cloudline-baby-blanket` | `cloudline-baby-blanket@1.2.0` | the drafted listing for 1.2.0 | listing CA$7.50, which equals the plan's proposed price, below the band on purpose | **Yes.** Release `7c63dbdd501f` is identical to the scratch-chain release. |
| Hexagon Coaster Set CA$4.00 | `hexagon-coaster-set` | `hexagon-coaster-set@1.2.0` | CIR title | `launch_price` CA$4.00 (floor of the cluster band) | **No.** Only `hexie-coaster-set@1.0.0` is stored. |
| Nordic Snowflake Ornament Set CA$4.50 | `nordic-star-ornaments` | `nordic-star-ornaments@1.4.0` | the drafted listing for 1.4.0 | listing CA$4.50 | **Yes.** Release `18c6e64fa4c5` is identical. |
| Winter Snowfall Relief Throw CA$7.50 | `winter-village-graphghan` | `winter-village-graphghan@1.3.0` | CIR title (there is no 1.3.0 listing) | `launch_price` CA$7.50 | **Certified, not listed.** Release `b41e0430fe3d` appears in `/api/launch` physical evidence and is identical. |

So the direct answers to the questions asked:

- **Yes,** "Winter Snowfall Relief Throw" is the `winter-village-graphghan@1.3.0` release. The
  release hash `b41e0430fe3d` is the same in production and in the scratch chain. Its 1.0.0
  ancestor was titled "Winter Village Graphghan", and its listing is withdrawn.
- **The baskets are not the production `market-basket-trio` record.** They are three CIRs,
  `market-basket-small/medium/large@1.2.0`, that production has never stored.
  - `market-basket-trio` is a retired alias (`launch0.LEGACY_DUPLICATES`).
  - The engineered `market-basket-trio` design was the medium basket. The same lineage is stated
    in `products.vessels` as `catalogue_provenance("market-basket-trio")`.
  - Production's `market-basket-trio@1.0.0` (`90ddbc8e4244`, "Storage Basket", CA$8.00) is a
    pre-calibration Build-1 release. Its content fingerprint is not public.
  - **Whether it is the same release as the medium basket is unproven.** Being the same design
    lineage is not the same as being the same release.
- **The coasters are in the same position.** The preview shows `hexagon-coaster-set@1.2.0`.
  Production has only the retired alias `hexie-coaster-set@1.0.0` (`bdf2c0bf3f9c`, CA$9.50,
  legacy, counted as zero), and equivalence is unproven.

## 2. The 16 product records in production

These come from `/api/status`: 16 products and 27 certified versions. Releases are from
`/api/catalogue` listings and from the `/api/launch` physical-evidence release keys.

- **Counted:** `/api/launch` `catalogue_depth` counts this product (a Launch-0 release, or one
  re-certified under the current gauge standard).
- **Legacy-0:** pre-calibration, counted as zero (F-119).

| # | production slug | versions @ release (listing state) | counted? | production title | relation to Launch-0 / preview |
|---|---|---|---|---|---|
| 1 | autumn-oak-mosaic-throw | 1.0.0 `0373a3fa0855` (draft); 1.4.0 `e025490ba3fa` (draft) | counted | "Autumn Oak Overlay Mosaic Throw" (1.0.0); "Fir and Star Relief Throw" (1.4.0) | outside Launch-0. 1.4.0 was retitled to what its CIR makes. |
| 2 | cloudline-baby-blanket | 1.0.0 `479a75c3cc39` (draft); 1.2.0 `7c63dbdd501f` (draft) | counted | Cloudline Textured Baby Blanket | **Launch-0, preview card 2** (1.2.0). 1.0.0 is superseded. |
| 3 | harvest-table-runner | 1.0.0 `19cc31025770` (withdrawn); 1.2.0 `179cb1277bec` (draft) | counted | Harvest Table Runner | Launch-0 reserve, not launched. Its window closed 2026-10-12. |
| 4 | heirloom-cable-blanket | 1.0.0 `70cc6f5a2ddf` (withdrawn) | legacy-0 | Heirloom Cable Throw | outside |
| 5 | hexie-coaster-set | 1.0.0 `bdf2c0bf3f9c` (draft, CA$9.50) | legacy-0 | Hexagon Coaster Set | **retired alias** of preview card 3. The `hexagon-coaster-set@1.2.0` release is not in production. |
| 6 | market-basket-trio | 1.0.0 `90ddbc8e4244` (draft, CA$8.00) | legacy-0 | Storage Basket | **retired alias** of preview card 1. `market-basket-*@1.2.0` is not in production. |
| 7 | mosaic-placemat-pair | 1.0.0 `897c81cfa30f` (draft); 1.3.0 `b2cd736f0f34` (draft, CA$9.50) | counted | "Mosaic Placemat Pair"; "Diamond Lattice Placemat Pair" | **CAP-1 proposal product.** 1.3.0 is identical to the proposal's release `b2cd736f0f34`. Production priced it CA$9.50 from the category band; the plan is CA$5.00. |
| 8 | nordic-forest-bundle | 1.0.0 `ddfee48219bd` (draft); collection (withdrawn) | legacy-0 | Nordic Forest Collection Bundle | a bundle, with no CIR of its own |
| 9 | nordic-forest-mosaic-throw | 1.0.0 `aa4c36a2a1d4`; 1.3.0 `0a51f89def89` (both draft) | counted | "Nordic Forest Overlay Mosaic Throw"; "Nordic Forest Relief Throw" | The throw is outside Launch-0. The CAP-1 baby size (`…-baby@1.3.0`) is a different CIR and slug, and is not in production. |
| 10 | nordic-star-ornaments | 1.0.0 `75c0a9b013fa` (draft); 1.4.0 `18c6e64fa4c5` (draft) | counted | "Nordic Star Ornament Set (6)"; "Nordic Snowflake Ornament Set (6)" | **Launch-0, preview card 4** (1.4.0). 1.0.0 is superseded. |
| 11 | pet-snuggle-mat | 1.0.0 `33c1d6687349` (withdrawn); 1.2.0 `5dccca80a6ab` (draft) | counted | Pet Snuggle Mat | outside. Fails `LISTING_PRODUCT_TYPE_UNSUPPORTED`. |
| 12 | pressed-flower-motifs | 1.0.0 `19d99fd6917d`; 1.3.0 `d5d9cbcb66cb` (draft) | counted | "Pressed Flower Motif Library (12)"; "Heart Applique Motif Library (12)" | outside. The slug and the current title disagree. |
| 13 | pumpkin-cluster-set | 1.0.0 `f5959cc65c01` (withdrawn) | legacy-0 | Pumpkin Cluster Set (3 sizes) | outside |
| 14 | spooky-garland | 1.0.0 `47eef6b90773` (withdrawn) | counted | Spooky Bunting Garland | outside. Its window was missed. |
| 15 | valentine-heart-garland | 1.0.0 `66e764929dbe`; 1.3.0 `9dc4e281d071` (draft) | counted | Heart Motif Garland | outside |
| 16 | winter-village-graphghan | 1.0.0 `4137e907f38c` (withdrawn); 1.3.0 `b41e0430fe3d` (**certified, no listing**) | counted | "Winter Village Graphghan" (1.0.0) | **Launch-0, preview card 5** (1.3.0 = "Winter Snowfall Relief Throw") |

The table identifies 26 of the 27 certified versions. The 27th cannot be identified from the
public endpoints, so it is recorded as UNKNOWN, not assumed.

**Naming discrepancies, reconciled. Each is an owner naming decision; none has been renamed:**

- **Slug names a different product than the title** (the slug is kept because the radar,
  portfolio and product rows key on it):
  - `winter-village-graphghan`: the slug names a picture graphghan; the release is a relief
    throw.
  - `pressed-flower-motifs`: the slug says flowers; the release is heart appliqué.
  - `autumn-oak-mosaic-throw` 1.4.0: the slug says autumn oak; the title says fir and star.
- **One product named after one of its sizes:** the basket card says "Hexagonal Storage Basket",
  which is the medium basket's CIR title, for a three-size product. Its plan title is "Nesting
  Baskets, three sizes". The store grid check already reports `TITLE_PLAN_MISMATCH` as an owner
  naming decision.
- **Retired aliases still have production rows:** `market-basket-trio` and `hexie-coaster-set`
  have draft listings in production. The publish path refuses them by name (PT-11), and since
  D-W5-7 (`084d6d6`) product readers map back to them.

## 3. The opening-grid checks: exact conditions and why production fails

There are four checks.

**A. launch.readiness `opening_grid` (F-238).** Code: `brand.storefront.opening_grid`.

It passes only when there are no problems. A tile is shown only if the product is
launch-cleared, meaning `app.dashboard_truth.LAUNCH_CRITERIA` all hold:

- `certified`
- `usable_listing_asset`
- `creative_gate_survivor`
- `gauge_standard`

It must also not be uncleared legacy (`legacy_status`). The grid then fails if any of these
apply:

- `OPENING_GRID_EMPTY`
- `OPENING_GRID_LADDER_FLAT`: one price rung shown while the catalogue has several
- `OPENING_GRID_SEASON_HIDDEN`: a live takeover's products are below the fold
- `OPENING_GRID_FILLER`
- coherence is unmeasured, or `bible.check_grid_coherence` fails, over the first 6 tiles

**Production reads `ready: true`, but that is wrong.** The visible tiles are
`nordic-star-ornaments` ×2, `cloudline-baby-blanket` ×2, `autumn-oak-mosaic-throw` and
`pressed-flower-motifs`.

The cause: the grid made one tile per listing row, and `legacy_status` clears a Launch-0 slug at
any version. So a product listed at two releases appeared twice, and the older tile sold a
superseded release. **This is fixed in `8c1de55`** (one tile per product, at its newest
certified version; the older listing is reported as superseded).

**B. launch.readiness `storefront_preview` (F-239/F-293).** Code: `brand.storefront_preview`.

The first 6 visible tiles must each have a valid `ListingSetCertificateRecord` naming frame 1,
and the bytes must be present. At least `PHONE_TILES` = 4 tiles must render. Icon, banner,
announcement and sections must also pass.

**Production FAILS:** "0 certified tile(s) render, a phone's first screen needs 4". None of
production's listed releases has a listing-set certificate. On the scratch chain all 7 Launch-0
releases render, with listing sets certified.

**C. Store-foundation grid check.** Code: `store_foundation.readiness._check_opening_grid`,
over the five Launch-0 products.

| finding | type | meaning |
|---|---|---|
| `GRID_EMPTY` | fail | no Launch-0 product |
| `CATALOGUE_DEPTH` | owner | 5 products is fewer than `MIN_LISTINGS_TO_OPEN` = 8. The threshold is not lowered: this is **CAP-1 / D-FB-9**. |
| title length | — | per-title length limit |
| `TITLE_POSITIONING_CONFLICT` | owner | |
| `TITLE_PLAN_MISMATCH` | owner | e.g. the baskets |
| `PRICE_UNKNOWN` | fail | |
| `TITLE_NOT_DRAFTED` | unverified | true for the baskets, coasters and throw, which have no Launch-0 listing in production |
| `LISTINGS_UNREADABLE` | unverified | |
| `TITLE_FROM_SUPERSEDED_RELEASE` | unverified | **new in `1423cf4`** |

**D. launch.readiness `catalogue_depth`.** It needs at least 8 products, each certified and
cleared and each with a listing. Sizes collapse to their product.

**Production reads `ready: true` with 11 products, because by rule F-119 re-certified legacy
releases count.** The 11 products are:

- autumn-oak-mosaic-throw
- cloudline-baby-blanket
- harvest-table-runner
- mosaic-placemat-pair
- nordic-forest-mosaic-throw
- nordic-star-ornaments
- pet-snuggle-mat
- pressed-flower-motifs
- spooky-garland
- valentine-heart-garland
- winter-village-graphghan

**C and D disagree:** C counts 5 Launch-0 products, D counts 11 cleared products. This is
reported and not changed, because counting re-certified legacy is the recorded F-119/F-120 rule.
Whether the opening collection is Launch-0 only is part of CAP-1.

## 4. Proposed 8-product launch collection

Four decisions are kept separate and none of them is taken here:

1. **catalogue approval** (CAP-1)
2. **certification** (company; already done on the scratch chain)
3. **draft creation** (needs an Etsy shop)
4. **publication** (a sealed owner grant per release, D-FB-10)

Evidence for every row:

- **Certification, images, PDFs:** scratch shadow release chains.
  - First five: `evidence_PRODUCT/e2e_launch0_chain.json`, 2026-10-11.
  - All eight: W4-LAUNCHREADY `readiness_catalogue_floor_8products.json`.
  - Each release has its certificate granted, nothing withheld, Product Truth PASS, and
    originality CHECKED.
  - **Images:** 3 disclosed hero, scale and detail frames, structurally verified on their bytes,
    covered by a valid listing-set certificate (PASS).
  - **PDFs:** US and UK `final_pdf` PASS.
- **Prices:** `launch0.price_plan`, all SOURCED bands.

| # | title (plan / CIR) | slug → release @ version (scratch release hash) | price CA$ | category / section | description (from the candidate) | production status |
|---|---|---|---|---|---|---|
| 1 | Nesting Baskets, three sizes / "Crochet Hexagonal Bread, Storage, Market Basket" | `nursery-nesting-baskets` → `market-basket-small` `1ddde587f537`, `-medium` `00182234041c`, `-large` `cc698c1b1498`, all @1.2.0 | 6.50 | basket / home | one pattern, three hexagonal baskets in the round, 16.0/20.8/25.6 cm across the points | not stored |
| 2 | Cloudline (Textured) Baby Blanket | `cloudline-baby-blanket@1.2.0` `7c63dbdd501f` | 7.50 | baby / baby | 79.2 × 96.4 cm two-colour blanket, worked flat | certified + draft listing |
| 3 | Hexagon Coaster Set (4) | `hexagon-coaster-set@1.2.0` `3754ed17a63b` | 4.00 | coaster / home | four hexagonal coasters, 9.7 cm across the points, contrast round | not stored (alias `hexie` 1.0.0 only) |
| 4 | Nordic Snowflake Ornament Set (6) | `nordic-star-ornaments@1.4.0` `18c6e64fa4c5` | 4.50 | ornament / seasonal | six 9.6 × 10.2 cm flat snowflakes, relief on an sc ground | certified + draft listing |
| 5 | Winter Snowfall Relief Throw | `winter-village-graphghan@1.3.0` `b41e0430fe3d` | 7.50 | blanket / blankets | 86.4 × 91.8 cm throw, sparse snowfall relief | certified, **no listing** |
| 6 *(CAP-1)* | Nordic Forest Relief Baby Blanket | `nordic-forest-mosaic-throw-baby@1.3.0` `01679f95e4dd` | 7.50 | baby / baby | 57.6 × 67.8 cm fir-and-star relief blanket | not stored |
| 7 *(CAP-1)* | Diamond Lattice Placemat Pair | `mosaic-placemat-pair@1.3.0` `b2cd736f0f34` | 5.00 (production listing says 9.50) | placemat / home | two 28.8 × 47.7 cm placemats, raised diamond lattice | certified + draft listing, **release identical** |
| 8 *(CAP-1)* | Housewarming Key Basket | `housewarming-key-basket@0.1.0` `142b52f0f9c6` | 5.50 | basket / home | round catch-all, 18.3 cm across, 11.1 cm tall, basketweave relief | not stored. Version is 0.1.0, a pre-release number, so name it 1.0.0 before release (a version decision, not a gate). |

**Outstanding blockers on all 8.** Each is the owner's or external, unchanged from
`PRODUCT_FIX.md`:

- **Search certificate:** needs the Etsy taxonomy snapshot (app keystring).
- **Durable PDF storage:** CA$5/month or less.
- **Physical evidence:** tester commission. The class-B releases need partial physical
  evidence, CA$32.40 or less each.
- **Parity:** needs `image_vision` credits (CA$25 or less) plus benchmark observation.
- **Etsy policy pages:** must be read in.
- **Etsy remote state:** unverifiable without a live shop.
- **Sealed publication grant:** one per release.

**Production-specific blockers.** Production first needs these Launch-0 releases to run through
its own release chain, which happens on deploy and the normal cadence; no publication is
involved:

- 5 of the 8 have no stored release: baskets, coasters, and the three CAP-1 products except
  the placemat.
- The throw has no listing.
- No production release has a listing-set certificate.

**Also for the owner.** The production placemat listing (CA$9.50) and the coaster alias listing
(CA$9.50) carry prices from the pre-Launch-0 category band. If CAP-1 is approved, the Launch-0
price plan (CA$5.00, CA$4.00) applies through `launch_price`.

## 5. Fixes made (company-side, with tests)

| commit | defect | test |
|---|---|---|
| `8c1de55` | The F-238 opening grid showed a product once per listed release: production showed ornaments ×2 and blanket ×2. Now one tile per product at its newest certified version; the older listing is excluded as superseded. | `tests/test_w4_catalog_reconciliation.py` |
| `1423cf4` | The Owner Store Preview chose the drafted listing by slug, so a superseded release's row with a higher id could name and price the product. Now keyed by (slug, version) and the current release wins. A superseded-only row is still read, as the existing test requires, but its basis names the release and the grid check reports `TITLE_FROM_SUPERSEDED_RELEASE`. | same file |

**Not changed:**

- the Launch-0 cap (CAP-1)
- `catalogue_depth`'s F-119 counting rule
- any slug or title (owner naming decisions)

**Focused tests run, all passing:**

- `test_w4_catalog_reconciliation`
- `test_storefront_fb4`
- `test_v11_store_foundation`
- `test_v11_store_preview`
- `test_w3_store_ux_structure`
- `test_vacuity`

## 6. CAP-1 approved by the owner (2026-10-11) — branch `claude/w4-CAP1`

**What was approved:** the Launch-0 cap rises from 5 to 8. **What was not approved:** the eight
products themselves, Etsy drafts, publication, ads, spend, or leaving shadow (D-CAP1-1).

### What changed in the code

- `products.launch0.CATALOGUE_FLOOR_APPROVED = True`. This adds three products to Launch-0:
  `nordic-forest-mosaic-throw-baby`, `mosaic-placemat-pair` and `housewarming-key-basket`.
- The cap tests now expect 8 instead of 5. This is the change the decision implies, with counts
  as W4-LAUNCHREADY measured them. The `CATALOGUE_DEPTH` finding still fires when a grid has
  fewer than 8 products.
- **No gate was changed.** `tests/test_w4_cap1_gates_intact.py` checks each of the three new
  products separately, with nothing recorded for it. Each one is still refused by:
  - certification (not PASS)
  - the listing-set certificate (not PASS)
  - the storefront tile (`not_certified`)
  - launch clearance (not cleared, and absent from the opening grid)
  - `for_publish` (blocks, and no owner grant exists)
- **Registry gap closed.** The baby blanket is now linked to the radar concept it belongs to
  (`SIZE_OF_RADAR_CONCEPT`). The key basket has no radar opportunity; that origin is now
  recorded (`NO_RADAR_CONCEPT`), so it no longer reads as a missing link.

### The placemat price: CA$5.00 is correct, CA$9.50 is not

| | value | where it came from |
|---|---|---|
| production draft listing, `mosaic-placemat-pair@1.3.0` (`b2cd736f0f34`) | CA$9.50 | The generic pricing path, before the placemat joined Launch-0. `release.CATEGORY_BANDS_CAD` has no `placemat` band, so it fell back to `DEFAULT_BAND` (CA$4.50–9.50), which has no evidence behind it, and landed on the ceiling. |
| Launch-0 price plan, `launch0.price_plan` | **CA$5.00** | A SOURCED CA$4–12 crochet-pattern cluster (`radar/market.py`), set one rung above the coaster set it pairs with, and decided by `commerce.pricing`. Rule PT-04 makes this plan the price of record for a Launch-0 product. |

The fix has three parts:

1. Since CAP-1, `pricing.position` prices the placemat from its plan.
2. Publication now refuses any Launch-0 listing whose stored price differs from its plan
   (`release_gates.launch_price_check`, `LISTING_PRICE_NOT_PLAN`).
3. The store grid reports the mismatch.

The production draft is corrected by re-running `pricing.position` for that release. Nothing is
written to Etsy. Tests: `tests/test_w4_cap1_placemat_price.py`.

### Housewarming Key Basket (still version 0.1.0)

The full release chain was run again on a scratch database in shadow mode (97 s). Evidence:
`evidence_CAP1/key_basket_chain.json`.

The release hash is `142b52f0f9c6…` again, so the build is reproducible.

| check | result |
|---|---|
| compile | 0 errors, 0 warnings |
| certified | yes; the certificate was granted |
| physical test required | no |
| Product Truth (5 gates) | PASS; the twin is not calibrated |
| final PDF (US and UK) | PASS |
| terminology, counts, listing claims | PASS |
| imagery | PASS |
| licence and safety statements | PASS |
| listing set, disclosure | PASS |
| listing draft | 13 tags, CA$5.50, inside the plan band |

**Blocking:** the same owner and external blockers as the other seven products:

- search category and taxonomy
- gauge and size claims (UNRESOLVED)
- Etsy remote state (UNVERIFIABLE)
- non-durable fulfilment storage
- parity and policy (UNKNOWN)
- rollback (UNKNOWN on this database, because the daily rehearsal did not run)

**Verdict.** It is release-quality to the same standard as the other Launch-0 releases. Two
caveats apply:

- **Version.** Its version is honestly `0.x`. `products.moment_candidates` keeps a candidate at
  `0.x` until it clears Product Truth, its taste gate and an owner-governed adoption.
  - Product Truth: cleared.
  - Taste gate: like every Launch-0 product, it survives only as `needs_taste` (structurally
    clean, not judged by eyes).
  - Adoption: CAP-1 approved the configuration only.

  So the number is **not** bumped here. When the owner adopts the product, the normal release
  path applies: a new version in the builder, then re-certification under the new release hash.
- **Demand.** Its own demand is UNKNOWN. It has no radar opportunity; it is a moment-first
  creative candidate.

**Recommendation:** it can go to the owner for adoption alongside the other two new products,
labelled as "demand UNKNOWN; engineering and certification evidence equal to the rest".
