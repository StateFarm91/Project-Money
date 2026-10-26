# W4-LAUNCH_ORDER: readiness of the 8 opening products, and a seasonal launch order

**Context**
- **Branch and date:** `claude/w4-LAUNCHPREP`, with `origin/claude/w4-LISTREADY` @ d69a3ec merged
  in, on 2026-10-26 (UTC).
- **Type:** read-only research and documentation. No test suite, no Etsy call, no production
  write, no spend.
- **Production** is **15800536** (the b997efd release, INTEG4) in SHADOW. It does not contain
  LISTREADY's R1–R11 fixes.
- **Production reads** were unauthenticated public GETs on 2026-10-26 between 00:55 and 01:10Z:
  - `/health`, `/api/launch`, `/api/incidents`, `/api/seasonal`, `/api/seasonal/cycle`,
    `/api/serp`;
  - `/api/audit` for `gate.certified`, `gate.halted`, `assets.built`, `assets.frame_review`,
    `etsy.taxonomy_refreshed`, `etsy.shop_snapshot`, `serp.captured` and
    `visual.image_production`.
- **Code facts** come from d69a3ec, computed locally (CIR, twin, `launch0`,
  `seasonal.leadtime`, `risk_matrix`).
- **Gate states** come from the most recent full local rehearsal on that code:
  - `evidence_FIRSTSALE/firstsale.json` (2026-10-20);
  - `evidence_PRODREADY/prodready.json` (2026-10-19).
- **No product code has changed since that rehearsal.** `git diff cc0c54ea d69a3ec` over
  `products/`, `cir/` and the listing paths shows only inventory text, gate wiring and an
  export guard. No CIR, PDF, render or price changed.
- **UNKNOWN** marks anything with no evidence.

## 1. Readiness table

### 1a. Per product (code d69a3ec; gates from the local rehearsal)

| product | release(s) | PDFs (US+UK) | Product Truth | price | listing title (chars), tags | delivery (rehearsal) |
|---|---|---|---|---|---|---|
| nursery-nesting-baskets | market-basket-small / -medium / -large **@1.2.0** | PASS ×3: both terms; byte-identical rebuild; AI disclosure and package statements in each; 9 / 10 / 11 pp | PASS | CA$6.50 each | "Hexagonal Bread / Storage / Market Basket \| Crochet Pattern PDF \| Nursery \| …" (105–107), 13 tags | PASS (durable, both PDFs) |
| cloudline-baby-blanket | **@1.2.0** | PASS, 35 pp | PASS | CA$7.50 | "Cloudline Textured Baby Blanket \| …" (104), 13 | PASS |
| hexagon-coaster-set | **@1.2.0** | PASS | PASS | CA$4.00 | "Hexagon Coaster Set \| …" (92), 13 | PASS |
| nordic-star-ornaments | **@1.5.0** | PASS | PASS | CA$4.50 | "Textured Stripe Ornament Set (6) \| …" (72), 13 | PASS |
| winter-village-graphghan | **@1.3.0** | PASS | PASS | CA$7.50 | "Winter Snowfall Relief Throw \| … \| Blanket \| …" (78), 13 | PASS |
| nordic-forest-mosaic-throw-baby | **@1.3.0** | PASS, 10 pp | PASS | CA$7.50 | "Nordic Forest Relief Baby Blanket \| …" (73), 13 | PASS |
| mosaic-placemat-pair | **@1.4.0** | PASS | PASS | CA$5.00 | "Raised Diamond Lattice Placemat Pair \| …" (76), 13 | PASS |
| housewarming-key-basket | **@0.1.0** | PASS | PASS | CA$5.50 | "Housewarming Key Basket \| …" (96), 13 | PASS |

Notes:
- Prices are `launch0.launch_price`. The stored listing equals the plan.
- Net after Etsy fees is modelled at CA$3.34 (coasters) to CA$6.51 (blankets).
- Product Truth covers: compiles clean; title, assembly, motif, fabric and size-label promises
  backed. Every release is still physically uncalibrated (see §1c).

### 1b. The image gallery and its verification (all 8 the same)

**What the gallery is made of:**
- **No FLUX-generated frame exists for any Launch-0 product.**
  - The FLUX 3 pipeline is in the code: `visual/image_production.py`, with
    `creative/flux3_generator` as its generator.
  - Production has **0** `visual.image_production` audit rows.
  - LISTREADY records that Launch-0 uses the disclosed renders.
  - The Laura lifestyle pipeline (VISNEXT2) is not merged.
- **Every frame is deterministic, drawn from the certified CIR:**
  - **disclosed render frames:** hero, scale, detail, plus an angle view for the three
    basket vessels;
  - **disclosed gallery frames:** construction (vessels), colour context, materials, and
    sizing (small basket only);
  - **a contents / pattern-preview frame** showing a real page excerpt;
  - **a stitch chart.**
- **Uploaded set per release** (the images Etsy would receive):
  - 9 for the small basket;
  - 8 for the medium basket, the large basket and the key basket;
  - 6 for each of the others.
- **Certified listing set:** 6 roles (hero, what's included, size, materials, pattern preview,
  chart). Cloudline, the ornaments and the baby throw add a seventh, "collection".

**Disclosure.**
- Every image carries the disclosure in its alt text.
- Every description carries `platform_policy.DISCLOSURES["disclosed_render"]` ("each listing
  image is a digital rendering of the pattern's finished design, not a photograph … no sample
  has been photographed…").
- The descriptions also carry the AI-assisted design sentence ("This design was created with AI
  assistance, and every row's stitch count is checked before release.").
- The AI disclosure is in both PDFs. In the rehearsal, disclosure PASS on all 10 releases.

**Verification state.**

| check | state |
|---|---|
| deterministic render verification on the bytes (image truth) | **PASS** (listing set certified) |
| legibility: every essential line ≥ 11 px at display size, on all uploaded images | **PASS** |
| Etsy upload-payload contract | **PASS** (0 warnings) |
| **independent vision review (B3)** | **FAIL**: every frame "unreviewed" |
| `no_third_party_marks` | **UNKNOWN** (needs a vision run) |

**Why B3 cannot run yet:**
- The owner-approved CA$7.07 batch (D-W4-LAUNCH-VISION-BATCH) is on LISTREADY, which is
  **not deployed**.
- **Production's model credit is exhausted.** `/api/launch` → `model_credits` reads:
  "anthropic 400: Your credit balance is too low to access the Anthropic API". The last probe
  was 2026-10-26 00:00Z.
- B3 therefore needs the deploy **and** an Anthropic credit top-up.

### 1c. Shop-wide gates and the physical sample

**Etsy taxonomy:**
- Production's daily refresh now resolves the category, on snapshot 2 (2026-10-22; read again
  2026-10-26 00:19Z).
- **All eight categories are CHOSEN** on node **6343**:
  `Craft Supplies & Tools > Patterns & How To > Patterns & Blueprints` (path ids
  562 / 6229 / 6343).
- Crochet is confirmed by Etsy's own property **"Craft type" (47626759760) = "Crochet"
  (value 543)**.
- The categories covered are: basket, blanket, baby, coaster, ornament, placemat,
  mosaic_blanket and graphghan.
- **B2 is closed in production's reading.**

**SEO:**
- In the rehearsal, SEO failed only because the category was UNKNOWN (B2). Copy, tags,
  description and hero all passed.
- With B2 now CHOSEN, SEO should pass once `listing.seo` re-runs on certified releases.
- That needs the deploy: production has 0 `listing.seo` rows. **UNKNOWN until then.**

**Physical sample, required for every product** (B4 needs a `full_physical_make` bound to the
content):

| product | effective class | tester hours (est., ×1.3) | yarn (twin) | spend ceiling, ESTIMATED (`risk_matrix.owner_action_spec`) |
|---|---|---|---|---|
| hexagon-coaster-set | A | 4.5 | 28.8 m DK cotton | CA$92.03 |
| housewarming-key-basket | B | 3.4 | 73.9 m worsted cotton | CA$73.18 |
| nordic-star-ornaments | A | 7.3 | 49.3 m worsted acrylic | CA$149.93 |
| mosaic-placemat-pair | A | 9.5 | 217.4 m | CA$204.67 |
| nordic-forest-mosaic-throw-baby | A | 11.5 | 311.7 m | CA$252.80 |
| nursery-nesting-baskets (3 makes) | B | 2.8 + 5.0 + 8.1 = 15.9 | 357.1 m | CA$59.65 + 108.96 + 175.08 = CA$343.69 |
| cloudline-baby-blanket | B | 19.9 | 605.4 m | CA$440.61 |
| winter-village-graphghan | B | 24.1 | 650.1 m | CA$529.11 |
| **all 8** | | **≈ 96 h** | | **≈ CA$2,086, not approved** |

**Roster:** production has 0 `tester.agreement_recorded` rows and 0 `physical.recorded` rows.

**A finding that confirms "whole item" for every product (not a fix):**
- `physical.record` compares the sample's yarn against the **whole-object** twin
  (`quality/physical.py:145-156`).
- A swatch or component therefore always reads a factor below 0.4. That is an ERROR, and the
  sample does not pass.
- So a `partial_physical` sample can never clear `gauge_and_size_claims` through the existing
  intake, even for a Class A product.
- W-LISTREADY should know this if a partial-test path is ever wanted. It would need a
  swatch-scoped estimate.

### 1d. Production today, and publication readiness

| item | production 15800536 |
|---|---|
| Launch-0 releases certified at the code's versions | **0 of 10**. Last `gate.certified` 2026-10-11 (older versions, e.g. ornaments 1.4.0 and placemat 1.3.0). Ornaments 1.5.0 and placemat 1.4.0 `gate.halted` on 10-20. |
| systemic halt | **P0 `systemic-halt:publication` open, current** (confirmed 01:02Z). 299 stale-artefact P1s (UNCONFIRMED). This is the R1 defect, fixed on LISTREADY and not deployed. |
| listings on Etsy | 0 (`has_a_digital_listing` fails; listing census FRESH, empty) |
| durable artifact storage | `artifact_storage: durable false`. Production PDFs are `durable: false`. |
| phase / publication switch | SHADOW; the publication kill-switch is off |

**Publication readiness: NOT READY for all 8.** The blockers are the same for each, in
dependency order:
1. Deploy LISTREADY (owner approval). Then the chain certifies and builds the 10 releases, in
   about 1–10 h at one seed an hour.
2. B3 vision review: top up Anthropic credit, then activate the approved batch (≤ CA$7.07).
3. B4 physical sample for **that** product: tester recruited, make, intake.
4. First authorised Etsy draft, which confirms the image upload (`etsy_upload_confirmed`).
5. Owner go-live: phase, publication grant, kill-switch, and listing fees of US$0.20 per
   listing.

**Steps 1, 2, 4 and 5 are shop-wide or minutes of work. Step 3 is per product and takes days.**
The physical sample is therefore what decides the launch order.

## 2. Seasonal launch order

### 2a. Demand evidence (repo and production first; no competitor content copied)

**Etsy active-listing counts.** These come from production's daily `serp.captured` reads,
2026-10-12 → 2026-10-26, through `findAllListingsActive`.
- This is a **PROXY for seller entry, not for searches** (MARKETINTEL §1).
- Etsy publishes no search volume.

| query | 10-12 | 10-26 | change |
|---|---|---|---|
| crochet bauble pattern | 2,943 | 3,650 | +24.0 % |
| crochet stocking pattern | 8,011 | 9,330 | +16.5 % |
| crochet ornament pattern | 53,992 | 60,352 | **+11.8 %** |
| crochet advent calendar pattern | 699 | 777 | +11.2 % |
| crochet christmas pattern | 164,668 | 181,922 | **+10.5 %** |
| crochet thanksgiving pattern | 22,326 | 23,543 | +5.5 % |
| crochet gift set pattern | 21,270 | 22,363 | +5.1 % |
| crochet throw pattern | 35,466 | 36,738 | +3.6 % |
| crochet coaster pattern | 20,322 | 20,915 | +2.9 % |
| crochet placemat pattern | 5,301 | 5,370 | +1.3 % |
| crochet blanket pattern | 90,192 | 91,181 | +1.1 % |
| crochet halloween pattern | 89,468 | 89,510 | +0.0 % (season over) |

**What the intel and planning code says:**
- **`market_intel` opportunities**, from the favourite-velocity-per-listing proxy. They were
  flagged daily from 10-20 to 10-26:
  - **"crochet ornament pattern" on all 7 days**;
  - "throw" on 10-22 and 10-26;
  - "placemat" on 10-23;
  - "stocking" on 10-26.
- **`radar.market.OBSERVATIONS`** (2026-09-17, commercial signals only):
  - overlay-mosaic Christmas blankets are heavily favourited;
  - Nordic, forest and festive motifs recur;
  - winning shops ship a seasonal family (blanket, ornament, basket…);
  - pattern prices cluster at CA$4–12.
- **Maker lead time decides demand** (`radar.market`, section 5). People buy a Christmas
  blanket pattern weeks before they make it. Small decor is bought late.
- **Baby-occasion interest** (`launch0.PAGEVIEWS`, Wikipedia proxy, 2025-09 → 2026-08):
  - highest in September (11,077), **lowest in December (6,914)**;
  - back to 8,402 in January.

  Baby products are evergreen but soft through December.
- **Backward chain** (`seasonal.leadtime.compile_launch`). For Christmas 2026-12-25, this is
  the latest date a listing must be live for a typical "adventurous beginner" maker to finish.
  It includes the 21-day marketplace ramp, 10-day completion buffer and planning buffer, and is
  computed from each CIR's own make hours. All terms are ASSUMED; the rate is uncalibrated.

| release | occasion (seed) | make h (est.) | latest live for Christmas | optimistic / pessimistic | status today, 10-26 |
|---|---|---|---|---|---|
| nordic-star-ornaments 1.5.0 | Christmas | 5.63 | **11-14** | 11-17 / 11-05 | open, tight |
| nordic-forest-mosaic-throw-baby 1.3.0 | Christmas | 8.86 | **11-07** | 11-13 / 10-25 | open, tight |
| winter-village-graphghan 1.3.0 | Christmas | 18.55 | **10-26** | 11-06 / 09-27 | **closing today**; only fast makers after 11-06 |
| mosaic-placemat-pair 1.4.0 | evergreen (holiday table) | 7.27 | 11-10 | 11-14 / 10-29 | open |
| hexagon-coaster-set 1.2.0 | unassigned (gift) | 3.46 | 11-17 | 11-19 / 11-11 | open |
| housewarming-key-basket 0.1.0 | unassigned (gift) | 2.61 | 11-18 | 11-19 / 11-14 | open |
| market baskets S/M/L 1.2.0 | unassigned (nursery) | 2.15 / 3.88 / 6.20 | 11-18 / 11-16 / 11-11 | | open |
| cloudline-baby-blanket 1.2.0 | evergreen (baby) | 15.27 | 10-30 (not its season) | | evergreen |

### 2b. Recommended order (no product dropped)

**Two orders, because they differ.**
- **Commission testers** in the order of the time each Christmas product needs, all in
  parallel, this week.
- **Publish** each product the moment its own sample binds, in the order below.

Every product is listed. A product that misses its peak still launches into the window that
follows.

| # | product | why here | window |
|---|---|---|---|
| 1 | **nordic-star-ornaments** | The strongest seasonal evidence: "ornament" was an intel opportunity on all 7 days, and ornament listings are up 11.8 % in two weeks. It is a QUICK make bought late, so it is still sellable well into November. CA$4.50 is impulse and stocking-stuffer priced. The sample is small: 7.3 h, 49 m. | live by **11-14** (optimistic 11-17) |
| 2 | **hexagon-coaster-set** | The quickest sample in the catalogue (4.5 h, 28.8 m; LAUNCHPREP Task A), so it is the likeliest *first* listing and first sale. It also proves the whole Etsy path (upload confirmation, delivery, reviews) before the Christmas rush. It is a gift / hostess item ("gift set" listings +5.1 %). | live by 11-17 |
| 3 | **nordic-forest-mosaic-throw-baby** | Nordic and forest mosaic is the motif family with the heaviest observed favouriting, and "throw" was flagged as an opportunity. The tightest window of the open Christmas items: start its tester the same day as the ornaments. | live by **11-07** (optimistic 11-13) |
| 4 | **mosaic-placemat-pair** | Holiday table and hosting; "placemat" was flagged 10-23, in a small, uncrowded market (5.4 k listings). Evergreen afterwards. | by 11-10, then evergreen |
| 5 | **housewarming-key-basket** | Gift item with a quick sample (3.4 h) and the latest Christmas cut-off (11-18). Housewarming demand runs through New Year moves and all year. | by 11-18, then evergreen |
| 6 | **winter-village-graphghan** | The Christmas cut-off for a typical maker is today. Its 24 h tester make cannot bind before about mid-November, so it misses most Christmas-2026 makers. **Launch it anyway, as soon as the sample binds:** the listing is a winter throw ("Winter Snowfall Relief Throw"), not a Christmas-dated item, so it sells through January–February. It also becomes the anchor of the seasonal family for Christmas 2027, when it should be live by late September. Start its tester **now**, in parallel: it is the longest make. | live as soon as it binds; winter through Feb |
| 7 | **nursery-nesting-baskets** | Evergreen nursery; three makes are needed (15.9 h, CA$343.69). Baby interest troughs in December and recovers in January, so it launches into the January rise without losing peak demand. | December → January |
| 8 | **cloudline-baby-blanket** | Evergreen baby with a 19.9 h make (CA$440.61). It has the same December trough as the baskets, and its largest sample cost is better spent after the first sales prove the path. | January (baby-shower interest rising) |

**What this order assumes, and what moves it:**
- **It is the owner's decision.**
  - The tester spend is about CA$2,086 for all 8, ESTIMATED and not approved.
  - The outreach message needs the owner's explicit confirmation of its exact wording.
  - The order lets the owner approve in tranches:
    - **tranche 1:** ornaments, coasters and baby throw, about CA$495;
    - **tranche 2:** placemats, key basket and graphghan, about CA$807;
    - **tranche 3:** baskets and Cloudline, about CA$784.
- **Christmas is lost for everything if the shop-wide steps slip.** The deploy, Anthropic
  credit top-up plus the B3 batch, first draft and go-live must all happen in the first half of
  November. At that point the ornaments and coasters still sell into December, and the rest
  move to their evergreen windows. The order does not change.
- **Every date is an estimate.**
  - Make times use an assumed 700 sts/h and 0.6 h finishing per piece; no maker has been timed.
  - Listing counts are a supply proxy.
  - The first sample's `hours` calibrates the rate (`leadtime.calibrate_from_samples`) and will
    tighten every window above.
- **Nothing here changes a gate.** A product publishes only when every first-sale gate passes.
