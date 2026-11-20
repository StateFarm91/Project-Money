# Track B product research — Q4 2026 store (CA/US, Meta ads, CJ Dropshipping)

Research date: 2026-09-15. Analyst: Claude (product-research subagent). Budget used: 20 web searches, 10 page fetches (both caps reached).
Currency: retail in CAD; supplier costs are quoted in USD as the sources give them. FX is **not** verified in this report; convert at the live rate at launch (assumption used for ranges: 1 USD ≈ 1.35–1.40 CAD).

Labels used throughout: **[E]** = read directly from a cited source; **[A]** = analyst assumption/estimate, not verified; **not found** = looked for, could not verify within budget.

## Hard filters applied

Price band CA$25–60; landed cost (product + shipping to CA/US) ≤ 1/3 of retail; not fragile; no battery/electrical certification exposure; no supplements/cosmetics/health/medical claims; no licensed characters, brands, or look-alikes; no weapons/adult/regulated items; no unsubstantiable claims; delivery ≤ 8 days to most of CA/US from the chosen warehouse; low return risk (no sizing-dependent apparel).

Important limitation: **CJ Dropshipping product pages and search pages redirect to a human-verification wall for automated fetches** (all five CJ fetches returned a 302 to `frontend.cjdropshipping.com/egg/cj/validation.html`). I did not attempt to bypass it. Therefore every CJ price, US-warehouse stock flag and per-SKU shipping estimate below is **[A]** unless a CJ blog article stated it. Existence of CJ listings *is* verified (URLs appear in CJ's own site index via search). Verifying prices needs a logged-in CJ account (Owner Block 2A) or the CJ API.

## Summary table (8 shortlisted)

| # | Product | Category | Evidence strength | Landed cost (CA$) | Retail (CA$) | Retail ÷ landed | Warehouse / days | Ad angle (visual hook → problem) | Biggest risk |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Cocktail smoker kit (wood top + 4 wood chips; **no glass cloche, no torch**) | Bar / gifting | **Strong** — quantified Amazon US market data (Jul 2026) + 4 independent 2026 buying guides + featured in CJ's Aug-2025 winning-products post | 11–21 [A] | 45–55 | 2.1–5.0× [A] | CJ listing exists [E]; US-warehouse variant **not verified** | Smoke swirls under the glass, lift, sip → a bar-quality drink at home; "gift for the person who has everything" | Torch/butane (ship without torch); glass variants fragile; Amazon anchors US$27–48 with Prime |
| 2 | Magnetic windshield snow/ice cover | Auto / winter utility | **Medium** — mainstream retail presence (Amazon incl. a 2016-era ASIN still selling and a "2026 New" listing, Walmart, Miles Kimball) + ≥2 single-product Shopify brands (AutoPrimez, Winkflo) which implies paid-ad sellers [A]; no sales numbers found | 12–18 [A] | 35–45 | 1.9–3.8× [A] | CJ **not verified** (verification wall) | Peel it off and the ice comes with it → no scraping at −20 °C | Weather-triggered timing; wind/theft/fit complaints; low gift appeal; no quantified demand data |
| 3 | Self-cleaning slicker brush (+ deshedding comb bundle) | Pet | **Medium** — two independent 2026 supplier guides give consistent cost/retail numbers; CJ has multiple listings; ad run-length data not found | 8–18 (cost range is [E], shipping [A]) | 29–34 single / 39 bundle | 1.6–4.3× | CJ listings exist [E]; US-warehouse **not verified** | Brush, click, fur drops off in one clump → shedding hair on everything | Heavily saturated; low AOV; Amazon at ~US$10–15 |
| 4 | Oversized hooded wearable blanket (plain colours only) | Home comfort / winter | **Medium-weak** — mainstream retail adoption (Amazon "Wearable Blankets" category, Target, Walmart, Bedsure, Big Blanket); market-size claims come from low-credibility report mills; "+35% Q4-2025" claim is from a blog, unverified | 27–45 [A] (heavy: ~0.8–1.2 kg) | 49–59 | 1.1–2.2× [A] → **likely fails the 1/3 rule** unless a US-warehouse SKU lands ≤ CA$19 | CJ listings exist [E] (3 URLs); US-warehouse **not verified**; some CJ prints look character-like → use plain colours | A hoodie the size of a blanket → cold evenings, "wearable cozy" | Shipping weight kills margin; Walmart/Amazon price anchors; quality variance |
| 5 | 12-in-1 vegetable chopper | Kitchen | **Strong demand, weak fit** — Fullstar model >79,500 five-star Amazon reviews; repeatedly viral on TikTok/Reels 2025–26; but demand is captured by Amazon at US$22.99–25 | 15–24 [A] (0.6–0.9 kg) | 39–45 | 1.6–3.0× [A] → borderline | CJ listings exist [E] (2 URLs); US-warehouse **not verified** | One press, a whole onion diced → meal-prep time, tears | Amazon price anchor ~US$25 Prime; blade/quality complaints; saturation |
| 6 | Door draft stopper (double-sided or 2-pack) | Home / winter energy | **Medium** — Bob Vila 2026 expert-tested list, Yahoo top-10, Suptikes ~3,000 five-star Amazon reviews; ad data not found | 8–14 [A] | 25–32 (2-pack) | 1.8–4.0× [A] | CJ **not verified** | Candle flame stops flickering the instant it slides under the door → drafts, heating bills | Low ticket; door-width fit returns; commodity |
| 7 | Memory-foam travel neck pillow | Travel | **Weak** — single source (AutoDS Q4-2026 list: "highest engagement score", "quiet saturation", ~US$25 potential profit); second source not found | 16–24 [A] | 39–49 | 1.6–3.1× [A] | CJ **not verified** | Head stays up when you doze off → neck pain on flights (comfort framing only, no health claim) | Single-source evidence; bulky; comfort is subjective → returns |
| 8 | Chunky knit scarf & beanie set | Winter accessories / gifting | **Weak** — single source (AutoDS Q4-2026: "bundle format increases AOV"); second source not found | 10–16 [A] | 35–45 | 2.2–4.5× [A] | CJ **not verified** | Matching set, one gift, done → holiday gifting for women | Taste/colour returns; no demand numbers; fashion competition |

Considered and **rejected at the filter** (for transparency): magnetic collision ball game (CJ blog reports "over 100,000 copies sold on TikTok Shop" — but it is a magnet toy subject to Canada Toys Regulations / CPSC magnet rules, and the category leader "Kollide" is a brand, so generic versions are look-alikes); USB-heated blanket/vest (battery/electrical); sunset/LED lamps, candle warmers, diffusers, mini bag sealers (electrical/heating elements); fleece thermal leggings (sizing); slim pre-lit Christmas trees (electrical, bulky); chunky knit blanket (> CA$60, heavy); "aesthetic home products" (too vague to source).

---

## 1. Cocktail smoker kit — bar / gifting

**What to sell:** wooden smoker top (fits any glass) + 4 wood-chip flavours in a gift box. **Do not** sell variants with a glass cloche (fragile) or a bundled butane torch (flame device; butane cannot ship by air; torch adds a hazard and a warranty headache). Product page says "use any kitchen torch or lighter".

**Evidence of traction**
- [E] Amazon US market report for "cocktail smoker" (asinsight.com, data dated July 2026): weekly search volume 1,795; 134 ASINs tracked; the US$20–50 tier is 50 % of listings (114 products); top-10 average monthly sales **1,480 units** at an average price **US$32.92**, average rating 4.5; leader ASIN B0BJV68C17 ≈ **7,000 units/month at US$47.99**; two fast-growing listings at US$26.99 and US$39.99 showing +100 % month-over-month (500 units/month each). https://www.asinsight.com/report/US/cocktail-smoker
  - Note: the search-engine snippet of the same report quoted "3,484 weekly searches, 126 competitors as of May 2026" — a different data month; both are recorded here, neither adjusted.
- [E] Four independent 2026 buying/gift guides treat the category as current: bourboninspector.com (2026), prohibitiondenver.com (July 2026), theconsumers.guide (2026), orifuture.com 2026 gift guide ("one of the most visually stunning cool gifts for cocktail lovers"; names the KUZKUZY kit at US$43.99 with a 4.6-star rating "across thousands of reviews"). https://bourboninspector.com/whiskey-smoker-kit/ · https://prohibitiondenver.com/best-whiskey-smoker-kits/ · https://www.theconsumers.guide/reviews/best-cocktail-smoker-kits-home-bartending-2026 · https://orifuture.com/blogs/news/9-cool-gifts-for-cocktail-lovers-the-ultimate-2026-buying-guide
- [E] CJ Dropshipping featured a cocktail smoker kit (glass cloche, smoker gun, 4 wood-chip varieties, recipes) in "Top 7 Winning Products to Dropship — first week of August 2025", noting cocktail culture on social media and gift-guide/unboxing fit. https://cjdropshipping.com/blogs/winning-products/Top-7-Winning-Products-to-Dropship-August-2025
- Meta Ad Library run-length: **not found** (Ad Library requires an interactive browser session; not queried in this pass).

**Supplier reality**
- [E] CJ carries the product category (see the CJ blog post above). Specific SKU price, weight and US-warehouse stock: **not verified** (verification wall).
- [E] CJ operates US warehouses in New Jersey and Chino, CA; US-stocked SKUs ship domestically in roughly 3–7 days per CJ's own articles. https://cjdropshipping.com/article-details/164 · https://cjdropshipping.com/article-details/146
- [A] Landed cost for a wood top + 4 chip tins: US$8–15 including CN→CA/US line-haul (≈ CA$11–21). If only a China-warehouse SKU exists, expect 8–15 days to Canada, which **fails the ≤ 8-day filter** — a US-warehouse SKU is a launch condition.

**Retail the market already pays:** [E] US$26.99–47.99 for the Amazon leaders; top-10 average US$32.92. Proposed store price **CA$49** (≈ US$36), inside the band and below the leader.

**Ad angle:** 9-second clip: smoke curls under an upturned glass, lift, pour, sip. Problem solved: an "impressive" home cocktail / a gift that looks expensive. Q4 fit: **strong** (host gifts, Secret Santa, stocking-stuffer-plus).

**Biggest risk:** Amazon Prime sells the same category at US$27–48 with next-day delivery; the store must win on the video and on gift-box presentation, not price. Secondary: variant selection (must avoid glass/torch).

---

## 2. Magnetic windshield snow/ice cover — auto / winter utility (Canada-specific)

**Evidence of traction**
- [E] Retail presence across channels: Amazon listings including a long-standing ASIN (B01BE5Q4FY, Ice King, ASIN structure indicates a 2016-era listing still active) and a "2026 New Magnetic Windshield Cover" listing (B0G2Q88JFD); Walmart category pages; Miles Kimball catalog. https://www.amazon.com/Ice-King-Magnetic-Windshield-Cover/dp/B01BE5Q4FY · https://www.amazon.com/Magnetic-Windshield-Waterproof-360%C2%B0Windproof-Green-2PCS/dp/B0G2Q88JFD · https://www.walmart.com/c/kp/magnetic-windshield-cover-snow-and-ice · https://www.mileskimball.com/buy-magnetic-windshield-cover-328991
- [E] At least two single-brand Shopify stores sell it as a hero product with trademark-style naming ("Winkflo™ Anti-Snow Car Windshield Cover", AutoPrimez "Magnetic All-Weather Windshield Snow Cover"). [A] Such stores are almost always paid-social funnels; this is indirect evidence that someone is buying ads for it. https://winkflo.com/products/windshieldcover · https://www.autoprimez.com/products/magnetic-all-weather-windshield-snow-ice-cover
- Sales volumes, Amazon rank, Google Trends: **not found** within budget.

**Supplier reality:** CJ availability **not verified** (search page hit the verification wall). [A] Category is a commodity widely stocked by CJ/AliExpress suppliers; product cost US$6–10, weight 0.4–0.7 kg, landed ≈ CA$12–18. US-warehouse stock: **not verified**.

**Retail the market already pays:** exact Amazon/Walmart prices were **not captured** in the fetched snippets ("not found"). Proposed store price **CA$39** (2-pack at CA$59 as an upsell).

**Ad angle:** dashcam-style clip: frozen windshield, cover peeled back, glass clear underneath; "Put it on in 30 seconds, never scrape again." Problem solved: 6:50 a.m. scraping. Q4 fit: **strong in Canada and the northern US from late October**; irrelevant in the US Sun Belt (geo-target accordingly).

**Biggest risk:** weather-dependent demand (needs the first frost — fine for a Nov/Dec window, but stage-1 tests in early October may read falsely negative); complaints about wind, magnet scratches, theft, and fit on trucks/SUVs; gift appeal is low, so it does not benefit from Black Friday gifting.

---

## 3. Self-cleaning slicker brush (+ comb bundle) — pet

**Evidence of traction**
- [E] productlair.com "15 Best Pet Dropshipping Products for 2026 (US trends)": retail US$22–28, supplier cost US$5–8, "very strong ad creative potential". https://productlair.com/blog/best-pet-dropshipping-products
- [E] Spocket 2026 dog-accessories guide: US retail commonly US$12–30, supplier listings US$3–9 per unit; recommends Meta interest targeting ("Dogs", "Cats", "PetSmart") and 10-second TikTok demo clips. https://www.spocket.co/blogs/dog-accessories-dropshipping-guide-best-products-and-suppliers
- [E] Listed among "best problem-solving dropshipping products" (alidropship). https://alidropship.com/best-problem-solving-dropshipping-products/
- Ad run-length, Amazon rank: **not found**.

**Supplier reality**
- [E] CJ listings exist, e.g. "Pet Pumpkin Brush — self-cleaning slicker brush" https://cjdropshipping.com/product/pet-pumpkin-brush-pet-grooming-self-cleaning-slicker-brush-for-dogs-cats-puppy-rabbit-cat-brush-grooming-gently-removes-loose-undercoat-mats-tangled-hair-slicker-brush-p-1561538210651066368.html and a double-sided undercoat rake https://cjdropshipping.com/product/grooming-brush-for-pet-dog-cat-deshedding-tool-rake-comb-fur-remover-reduce-2-side-dematting-tool-for-dogs-cats-pets-grooming-brush-double-sided-shedding-and-dematting-undercoat-rake-hair-removal-comb-p-1561283436978524160.html
- CJ price and US-warehouse stock: **not verified**. [A] Product US$3–9 [E-range] + shipping US$3–5 (light, ~0.2 kg) → landed CA$8–18.

**Retail the market already pays:** [E] US$22–28 (productlair), US$12–30 (Spocket). Proposed **CA$34** brush alone or **CA$39** brush + rake bundle (bundle lifts AOV so a CA$50 test buys more signal).

**Ad angle:** 8-second clip: brush a golden retriever, press the button, a fur pancake falls into the bin. Problem solved: hair on the couch. Q4 fit: **neutral/evergreen** (pet gifting exists but is not the driver).

**Biggest risk:** the most saturated of the three picks; Amazon sells it at US$10–15. Wins only if the creative is authentic (real pet, real living room) and the bundle price feels fair.

---

## 4. Oversized hooded wearable blanket — home comfort / winter

**Evidence of traction**
- [E] Amazon has a dedicated "Wearable Blankets" category with a New Releases chart; Target, Walmart (multiple listings), Bedsure and Big Blanket Co ("Hideout Hoodie") sell it — mainstream adoption. https://www.amazon.com/gp/new-releases/home-garden/17874220011 · https://www.target.com/s/oversized+blanket+hoodie · https://bedsurehome.com/collections/blanket-hoodie · https://bigblanket.com/products/hideout-hoodie
- [Weak] Market-report mills claim a global wearable-blanket market of USD 3.8 B (2025) → 4.1 B (2026), 8.1 % CAGR (deepmarketinsights.com; low credibility). A blog claims "35 % increase in sales in Q4 2025 for hoodie blankets" (fzgolden.com; unverifiable). Recorded, not relied on.
- Google Trends December peak: **not verified** (not fetched).

**Supplier reality:** [E] CJ listings exist: https://cjdropshipping.com/product/ovesized-wearable-blanket-hoodie-winter-cute-print-fleece-sleepwaer-warm-and-cozy-sofa-homewaer-p-1573125892296560640.html and https://cjdropshipping.com/product/hoodie-sweatshirt-with-big-pocket-tops-sweater-comfortable-loose-double-sided-fleece-thicker-wearable-blanket-p-1374599054109052928.html (a USB-heated variant also exists — **excluded**, electrical). Prices, weights, US-warehouse stock: **not verified**. [A] Product US$12–18 + shipping US$8–15 for a 0.8–1.2 kg parcel → landed CA$27–45.

**Retail:** Walmart/Amazon price points were not captured ("not found"); dropship stores typically list CA$49–69 [A]. Proposed CA$59 — **fails the 1/3 landed rule on current assumptions**. Only viable if a CJ US-warehouse SKU is confirmed at ≤ US$14 all-in.

**Ad angle:** "A hoodie the size of a blanket" — person disappears into it on the couch. Q4 fit: **very strong** (gifting + cold).

**Biggest risk:** shipping weight and mass-retail price anchors. Kept on the shortlist as the first alternate because its Q4 fit is the best of the eight.

---

## 5. 12-in-1 vegetable chopper — kitchen

**Evidence of traction**
- [E] Fullstar chopper: "over 79,500 perfect five-star reviews on Amazon", repeatedly "goes viral on TikTok", sale price US$25 (SheKnows/Yahoo, 2025–26 deal coverage). https://www.sheknows.com/living/articles/2573850/vegetable-chopper-amazon/ · https://www.yahoo.com/lifestyle/life-changing-viral-tiktok-veggie-144050199.html
- [E] "Heavily featured across TikTok, Facebook Reels and YouTube Shorts in 2025" (Medium first-person review, which also documents blade/durability complaints). https://medium.com/@Daily-Smart-Finds/i-bought-the-viral-12-in-1-vegetable-chopper-here-is-the-messy-truth-f02af9e59acd
- [E] Amazon carries a "2026 Upgraded 12 in 1" listing (B0GTZKFB5T); a 16-in-1 model tested at US$22.99. https://www.amazon.com/Vegetable-Upgraded-Multifunctional-Container-Accessories/dp/B0GTZKFB5T

**Supplier reality:** [E] CJ listings exist: https://cjdropshipping.com/product/12-in-1-manual-vegetable-chopper-kitchen-gadgets-food-chopper-onion-cutter-vegetable-slicer-p-1583305201992749056.html · https://cjdropshipping.com/product/12pcs-multifunctional-vegetable-chopper-handle-food-grate-food-chopper-vegetable-slicer-dicer-cut-kitchen-gadgets-p-1374636151603859456.html. Price/US stock **not verified**. [A] landed CA$15–24.

**Retail:** [E] US$22.99–25 on Amazon (sale), list ~US$30–35 [A]. Store price would need CA$39–45 → margin borderline and price-comparison exposure high.

**Ad angle:** one press dices an onion; container fills. Q4 fit: moderate (holiday cooking).

**Biggest risk:** the buyer can find the identical item on Amazon Prime at US$25 in one search. Not recommended for stage 1.

---

## 6. Door draft stopper — home / winter energy

**Evidence:** [E] Bob Vila 2026 expert-tested list; Yahoo "10 best draft stoppers"; Suptikes adhesive silicone stopper "close to 3,000 five-star reviews" on Amazon; MAXTID and MAGZO weighted models named. https://www.bobvila.com/articles/best-door-draft-stopper/ · https://www.yahoo.com/lifestyle/10-best-draft-stoppers-keep-010009661.html. Ad data and Google Trends: **not found**.
**Supplier:** CJ **not verified**. [A] landed CA$8–14 for a double-sided or 2-pack.
**Retail:** [A] US$15–30 typical; store CA$25–32 only as a 2-pack.
**Ad angle:** candle flame stops flickering the instant the stopper slides under the door; "cut the draft, cut the bill". Q4 fit: strong Nov–Jan.
**Risk:** low ticket; door-width measurement returns; commodity with no creative moat.

## 7. Memory-foam travel neck pillow — travel

**Evidence:** [E] AutoDS "Best Q4 Dropshipping Products 2026": "highest possible engagement score", "quiet saturation", "around US$25 in potential profit". https://www.autods.com/blog/q4-dropshipping-products/ — second independent source: **not found**.
**Supplier:** CJ **not verified**. [A] landed CA$16–24 (0.4–0.6 kg).
**Retail:** [A] CA$39–49.
**Ad angle:** head stays upright when the traveller dozes (comfort framing only; no pain/health claims). Q4 fit: holiday travel, moderate.
**Risk:** single-source evidence; subjective comfort → returns; strong incumbents (Trtl, Cabeau).

## 8. Chunky knit scarf & beanie set — winter accessories / gifting

**Evidence:** [E] AutoDS Q4-2026 list recommends coordinated scarf + beanie bundles for AOV. Second source: **not found**.
**Supplier:** CJ **not verified**. [A] landed CA$10–16.
**Retail:** [A] CA$35–45 for the set.
**Ad angle:** one gift box, matching set, done. Q4 fit: strong.
**Risk:** taste-driven returns (colour, texture), no demand numbers, fashion competition.

---

## Recommendations — 3 products, 3 different categories

**Pick 1 — Cocktail smoker kit (bar / gifting), CA$49.** The only candidate with quantified, current demand data (top-10 Amazon listings averaging 1,480 units/month at US$32.92 in July 2026; a leader moving ~7,000/month at US$47.99) cross-checked by four independent 2026 buying guides and a CJ winning-products feature. It has the most spectacular 9-second demo of the eight, sits naturally in Black Friday / Secret Santa gifting, and the price band leaves headroom over a CA$11–21 landed cost. Launch conditions: a wood-only, torch-free SKU stocked in a CJ US warehouse; product page states "use your own kitchen torch or lighter"; wood chips only (no flavoured liquids, no consumables that need food labelling).

**Pick 2 — Magnetic windshield snow/ice cover (auto / winter utility), CA$39.** Materially different buyer and trigger (weather, not gifting). Evidence is presence-based rather than quantified, but the presence is broad (decade-old Amazon listing still active, "2026 New" listings, Walmart, catalogue retailers) and at least two dedicated Shopify brands are running it as a hero product, which is the classic footprint of a paid-social winner. Low landed cost, non-fragile, one-size, and a Canadian audience that needs no persuading about the problem. Geo-target CA + northern US states only; expect the stage-1 test to read better after the first frost (late October) than in early October.

**Pick 3 — Self-cleaning slicker brush + undercoat rake bundle (pet), CA$39.** Third distinct category and audience (pet owners, evergreen, emotionally motivated). Two independent 2026 supplier guides agree on cost (US$3–9) and retail (US$22–30), so it is the candidate with the least cost uncertainty; multiple CJ listings exist. Its weakness is saturation, so it is sold as a bundle at CA$39 with a real-pet creative rather than a studio demo.

**Why these three and not the alternates:** they draw on three unrelated demand drivers (gifting, weather, pets), so a miss on one says nothing about the others; each has a demo that fits a silent 6–10 second feed video; none is electrical, fragile, sized, or claim-dependent. The hooded blanket has the best Q4 fit but fails the landed-cost rule on current assumptions; it is the first alternate if a CJ US-warehouse price ≤ US$14 all-in is confirmed. The vegetable chopper has the strongest raw demand but that demand is already served at US$25 on Amazon Prime.

**Blocking uncertainty for all three:** CJ price, weight and US-warehouse stock could not be read (verification wall). Until a logged-in CJ account (Owner Block 2A) or the CJ API confirms them, the landed-cost column is an assumption and the 8-day delivery filter is unproven.

---

## Brand-name check

Method: five coined, product-agnostic names, one web search each for existing businesses, plus a DNS lookup of the exact .com (a resolving name means the domain is registered; a non-resolving name is a hint of availability, not proof — DNS was validated against a nonsense control domain that correctly failed).

| Name | Web-search conflict | .com DNS | Verdict |
|---|---|---|---|
| Tuckwell | **Conflict** — Tuckwells, UK agricultural-machinery dealer (est. 1954, 10 outlets) with retail shops and an online clothing store. | registered | Reject |
| Fernbay | **Conflict** — fernbay.com is an existing site; "Fern Bay Store" is an Australian general store. | registered | Reject |
| Dwellry | No exact match, but confusable with Dwell (UK furniture retailer), dwell.com shop, Dwell & Company, DwellStudio — all home category. | registered | Reject (category confusion + domain taken) |
| Bramblo | No exact match; nearest are Bramble Company (furniture, home category), Bramble Berry (soap supplies), Brambles Ltd (logistics). | registered | Not recommended (domain taken; home-category neighbour) |
| Wyncroft | **Conflict** — Wyncroft Wine, Michigan winery with an online shop (a direct problem for a store selling a cocktail accessory). | registered | Reject |
| Marloway (backup, 6th search) | No exact match; nearest are Marlow (NZ athleisure), Marlow Goods (Brooklyn shop), marlowstore.com. | registered (resolves to addresses typical of domain parking) | Not recommended unless the parked domain is cheap; would need a trademark check |

All five original names and the backup have registered .coms, so none is a clean recommendation. A DNS sweep of 55 further coined names (no web-search conflict check possible — search budget exhausted) found these **.com names with no DNS record** (availability hint only):

- **wrenporch.com — "Wren Porch"** (recommended candidate: short, two common words, product-agnostic, evokes seasonal/home/outdoor without naming a category)
- tuckandnook.com — "Tuck & Nook"
- hearthwren.com — "Hearthwren"
- cozyporch.com — "Cozy Porch" (generic; higher trademark-collision risk on "cozy")
- pineandnook.com, hearthporch.com, nookandtote.com, hearthandtote.com, keepandhearth.com

**Top brand name: Wren Porch (wrenporch.com)** — subject to two checks the next session must run before purchase: one web search for existing "Wren Porch" businesses/trademarks (CIPO + USPTO TESS), and a registrar availability check (DNS absence is not proof). Also check wrenporch.ca.

---

## What I could not verify

- **CJ Dropshipping prices, weights, US-warehouse stock and per-SKU delivery days** for every product: CJ serves a human-verification wall to automated fetches. Needs a logged-in account or the CJ API.
- **Meta Ad Library run lengths** for any product: not queried (needs an interactive browser session). The "long-running ad" criterion is therefore inferred from single-product Shopify stores and multi-year retail presence, not measured.
- **Google Trends direction** for any product: not fetched.
- **Amazon Movers & Shakers** rank data: not fetched; the only quantified Amazon data is the third-party asinsight.com cocktail-smoker report.
- **Exact retail prices** for the windshield cover, hooded blanket, draft stopper, neck pillow and scarf set: snippets did not include prices; ranges are assumptions.
- **Second independent source** for the neck pillow and scarf set (AutoDS only).
- **Domain availability**: DNS-only; no registrar or WHOIS query; no trademark search (CIPO/USPTO) for any name.
- **FX rate** CAD/USD at launch.
- copyfy.io's "50 winning picks for Q4 2026" list returned HTTP 403 and was not read.

## Sources consulted (all)

Trend lists: easync.io Q4 2026 guide; eprolo.com Q4 products; sourcinbox.com Q4 list; autods.com Q4 products & holiday guides; cjdropshipping.com TikTok-viral 2026, pet-products 2026, Aug-2025 winning products, US-warehouse articles 164/146; adnabu.com TikTok trending 2026; webbeeglobal.com; quicksync.pro; findniche.com; sellthetrend.com; wiio.com; sovran.ai.
Product evidence: asinsight.com cocktail-smoker report; bourboninspector.com; prohibitiondenver.com; theconsumers.guide; orifuture.com; blindpigdrinkingco.com; amazon.com (B01BE5Q4FY, B0G2Q88JFD, B0GTZKFB5T, wearable-blankets new releases); walmart.com; mileskimball.com; autoprimez.com; winkflo.com; icekingusa.com; productlair.com; spocket.co; alidropship.com; doba.com; sheknows.com; yahoo.com; aol.com; stylecaster.com; medium.com (Daily-Smart-Finds); bobvila.com; dadimprovement.com; bigblanket.com; bedsurehome.com; target.com; techsciresearch.com; deepmarketinsights.com; fzgolden.com.
Brand checks: tuckwells.com; tracxn.com; fernbay.com; yelp.com (Fern Bay Store); dwell.com; wikipedia (Dwell retailer); faire.com; klossfurniture.com; brambleberry.com; globaldata.com (Brambles); wyncroftwine.com; marlowstore.com; marlowgoods.com.

## Addendum (Day 1, evening): first live Meta Ad Library probes (public page, via `intel/adlibrary_probe.mjs`)

Run 2026-09-15 under the owner-approved project permission rule (D-013). Counts are active ads returned for a keyword search; "dated" ads are those whose start date was visible on the loaded page; longevity = ads older than 28 days. Snapshot values.

| Keyword | Country | Active ads | Dated | Earliest start | Older than 28 d | Read |
|---|---|---|---|---|---|---|
| cocktail smoker kit | US | 58 | 13 | 2024-07-03 | 11 | **Strong**: many advertisers, several ads running for months; someone is profiting |
| windshield snow cover | CA | 29 | 29 | 2026-05-26 | 5 | **Seasonal ramp**: all ads started since late May, five past four weeks, new ones daily |
| windshield snow cover | US | 140 | 30 | 2026-05-26 | 4 | **Broad seasonal ramp**: 140 active ads, mostly new; supports a Canada + northern-US test after first frost |
| self cleaning slicker brush | US | 6 | 5 | 2026-08-30 | 0 | **Weak**: almost no paid-ad activity; demand is Amazon-search-driven and saturated; low AOV |
| wearable hooded blanket | US | 69 | 24 | 2025-12-10 | 7 | **Strong Q4 signal**: broad advertiser base, several long-running; blocked only by the landed-cost rule until CJ pricing is verified |

**Provisional re-ranking (pending CJ landed costs, Block 2A):** 1. cocktail smoker kit (torch-free SKU); 2. wearable hooded blanket (only if a US-warehouse SKU lands at or under US$14); 3. magnetic windshield snow cover (Canada + northern US, launch after first frost); pet brush bundle moves to WATCH. The full scored queue (SPEC section 8) replaces this list before any ad spend.
