# Four-shop comparison: the system's competitor evidence for each watchlist shop

- **Shops compared:** Mrs J (MJsOffTheHookDesigns), MadelineMaeCo, ZKBDESIGNER and TheEasyDesign.
- **Prepared:** 2026-10-26 (UTC) on `claude/w4-INTELREC`.
- **Rules followed:**
  - Only evidence the system actually holds is used.
  - Every item carries its source and timestamp.
  - Revenue, conversion and profit are never invented.
  - No competitor text, titles, images or instructions are copied. Figures are counts, medians and shares.
  - Shops are named here because this is the owner's own report. The stored records use aliases only (L-3).
- **No pages were browsed.** etsy.com shop and search pages answer software with HTTP 403 (DataDome). The standing decisions (B-268, B-500 in `MARKETINTEL.md`) forbid fetching etsy.com pages or passing bot protection. The only compliant automated source is the official Etsy Open API v3. That API needs the production credential, which this session must not use. So no light public read was possible. Nothing was approximated in its place.

**Evidence sources:**

| Label | Source | Timestamp |
|---|---|---|
| **[S1]** | Production `/api/benchmark-selection`, anonymous capture (`evidence/prod_benchmark_selection_2026-10-26T1356Z.json`) | 2026-10-26T13:56Z |
| **[S2]** | `research/final_build/w4/MJS_FINDINGS.md`, read from production's public endpoints then: `/api/teardown`, `/api/arbitrage*`, `/api/gallery-intelligence`, `/api/mjs`, `/api/audit` | 2026-10-07T00:04Z |
| **[S3]** | `intel/benchmarks.py` registry note: the first full catalogue observation, read through the API | 2026-09-19 |
| **[S4]** | Production job counts, anonymous `/api/jobs` capture (`evidence/prod_job_counts_2026-10-26T1724Z.json`) | 2026-10-26T17:24Z |
| **[S5]** | Production `/api/etsy` capture | 2026-10-19 |

## 1. What the system holds per shop

| | Mrs J | MadelineMaeCo | ZKBDESIGNER | TheEasyDesign |
|---|---|---|---|---|
| Registered target | Yes, since Build 2 (#301 anchor) | Yes on INTELREC only (876b4fee); not deployed | Yes on INTELREC only; not deployed | Yes on INTELREC only; not deployed |
| Data collected | Yes. 442 listings observed [S1]; 441 at [S2] | **None** | **None** | **None** |
| Collection still needed | none | `intel.watchlist_scan` after deploy (official API: `findShops`, shop listings, listing images, shop reviews) | same | same |

For the three new shops, every row below reads **NOT COLLECTED**. The collection that fills each row is named. There are no guesses.

## 2. Mrs J: what is observed, with sources

**Catalogue size and structure.**

- 442 listings observed [S1, 13:56Z today]; 441 at [S2]; 438 at the first baseline [S3].
- Departments at [S2], a share of 441 (*proxy for shelf allocation*): garments 32%, hats 20%, blankets 19%, collections 7%.
- Twelve permanent pods hold the catalogue. Four were added from the first observation [S3]: kitchen/bath 13 listings, soft sculpture/amigurumi 11, multi-pattern ebooks 12, guidebooks 2.
- The shop's own stated location is the United States [S3, the registry's `market="US"`].

**New-product cadence.**

- The system measures it with fingerprint diffs on each scan.
- Production audit rows at [S2] show scans running. The latest then saw 441 listings, inspected 65 and skipped 310 unchanged.
- *The rate of new listings per week needs operator readback* of `mjs.scanned` rows.

**Pricing and promotions** (observed [S2], n=437):

- Prices are tightly clustered. The median is CA$18 in most pods, CA$22 for garments and CA$19 for stockings, with near-zero IQR.
- **0 of 441 listings were on sale** at [S2].
- Today's selection [S1] agrees: garments CA$22, hats/bags/blankets/amigurumi/ornaments CA$18, stockings CA$19, kitchen/bath CA$16, education CA$21, a collection CA$85.

**Seasonal strategy.**

- The [S2] proxy found 10 stocking and 13 ornament listings at the opening of the Christmas window.
- Every listing selected at [S1] is classed `evergreen` by our seasonal routing (*derived*).
- *Seasonal positioning by title is unmeasured from public endpoints* [S2]. The in-database path measures it, and that needs readback.

**Bundles and families.**

- Collections sell at a median of CA$60.5, against CA$18 for single patterns (3.36×, n=29) [S2, observed].
- The [S1] selection includes one bundle (collections) priced at CA$85.

**Photography and gallery composition** [S2]:

- The median gallery has 10 images: 342 listings have 10 or more, and 58 have fewer than 5.
- 116 of 142 audited galleries include a video.
- The most common judged shots are flat_lay, in_use and hero_styled.
- 87 of 143 hero palettes are low-saturation neutrals.
- [S1] has 9 of 10 selected listings with a rich gallery and video.

**SEO and merchandising.**

- Tags are stored per listing under the existing rules. No aggregate is in a public capture.
- *needs operator readback*: `/api/teardown` and `/api/arbitrage`.
- The deliverable statement is a weakness: 154 of 439 descriptions are unclear. They are silent on delivery (438), page extent (432), hook (218), finished size (196) and terms (79) [S2, observed]. [S1] marks all 10 selected listings `deliverable_stated: unstated`.

**Reviews and trust.**

- 100 reviews were read at [S2]. 5 were rated 3 or lower.
- The recurring theme is "instructions unclear" (3 reviews). These are theme counts only. No text is stored.
- *The shop-level review count and average are not in any capture.* `intel.watchlist_compare` reads them from `findShops` for the new shops. For Mrs J they need `findShops` or a readback.

**Public sales milestones.**

- **Not held.** No capture records `transaction_sold_count`, and the API exposes no competitor revenue.
- Favourites are the labelled popularity proxy: the [S2] median favourites per listing are garments 1701, stockings 1472, blankets 1400, amigurumi 1111, bags 920.
- In [S1] the selected listings range from 439 to 13,378 favourites.

**Positioning (derived).**

- A broad, video-led, US-market catalogue at a narrow CA$16–22 single-pattern band, with bundles at about 3.4×.
- Strongest favourite density is in garments and stockings.

**AI use:**

| Claim | Label | Basis |
|---|---|---|
| Uses AI-generated imagery | **unknown** | no evidence collected |
| Uses AI-written listings | **unknown** | no evidence collected |
| Shop is AI-operated | **unknown** | never assumed |

## 3. MadelineMaeCo, ZKBDESIGNER, TheEasyDesign

For each of the three shops, every topic in this section reads **NOT COLLECTED**:

- catalogue size and structure; categories; new-product cadence;
- pricing and promotions; seasonal strategy; bundles and families;
- photography and gallery; SEO and merchandising;
- reviews and trust; public sales milestones; positioning.

AI use reads **unknown** (no evidence; never assumed).

**What collection fills them.** `intel.watchlist_scan` (6-hourly; adaptive per shop) and `intel.watchlist_compare` (daily) record:

| Data | Source | Grade |
|---|---|---|
| Catalogue, categories (our pods), price, `is_sale`, variations, deliverable/bundle facts, gallery image counts, tags, favourites | shop listings + listing images | MEASURED, or DERIVED where marked in `intel/watchlist.SCOPE` |
| Public sales (`transaction_sold_count`), review count and average, shop favourites, active listing count | `findShops` | MEASURED |
| Recurring complaint themes (counted, never quoted) | `getReviewsByShop`, weekly | DERIVED |
| New-listing cadence | fingerprint diffs over successive scans | |

**Not covered by this collection:**

- Image-level vision judgement runs for the anchor only, inside `market_radar`'s ceiling.
- Off-Etsy channels (websites, YouTube, Pinterest) have no compliant collector, so they stay UNAVAILABLE.

## 4. Techniques to test

These come from Mrs J's evidence. They are hypotheses for our own A/B tests, not copies.

1. **A ten-image gallery plus a technique video as the baseline.** At [S2], 342 of 441 listings have 10+ images and 116 of 142 have video. Test our certified listings at 10 images against fewer, once traffic exists.
2. **Priced bundles in every family.** Collections take a median of about 3.4× a single pattern (n=29) [S2]. Test a family bundle beside each launch family. Winner Amplification and `creative.family_engine` are in the combined candidate.
3. **A narrow single-pattern price band.** A tight CA$18 median with near-zero IQR [S2]. Test launch prices inside the observed band against our pool prices, which sit 39–69% below it [S2].
4. **Saturated colourways against neutral heroes.** 87 of 143 hero palettes are low-saturation [S2]. Test saturated colourways as a differentiator.

## 5. Weaknesses to avoid (theirs, and ours to beat)

1. **Unstated deliverables.** 154 of 439 descriptions are unclear about what arrives [S2]. Every one of our listings states pages, hook, finished size and terms. Product Truth already enforces this.
2. **"Instructions unclear"** is the only recurring complaint theme [S2]. Our CIR-certified patterns, compiler-checked counts and photo steps answer it.
3. **Thin galleries.** 58 listings have fewer than 5 images [S2]. Thin galleries are an opening.

## 6. Original-product opportunities

These are arenas, never designs.

- At [S2], seven proven arenas had no Brambleloop answer: hats/wearables, amigurumi, garments, collections, Christmas stockings, kitchen/bath and education.
- Stockings show high favourite density from a thin range [S2]. The original-stocking opportunity for this Christmas is time-critical.
- These go to the existing pipeline as original, divergent concepts (#215/#216/#227). On INTELREC, an arena that two or more watchlist shops occupy and we do not becomes a validated opportunity. Laura's `intel.opportunity_review` decides on it.
- **Not yet known.** Whether MadelineMaeCo, ZKBDESIGNER or TheEasyDesign corroborate any of these arenas is unknown until their first scans.

## 7. What this comparison cannot say yet

- Competitor revenue, conversion and profit. The API does not expose them, and none are inferred.
- Anything about the three new shops (§3).
- Mrs J's current-week change rate and current findings. These need readback of `mjs.scanned`, `mjs.findings` and `mjs.mission_events`. The [S2] figures are 19 days old.
