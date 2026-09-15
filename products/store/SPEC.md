# Track B — store stack specification (v1, Day 1)

Owner: Claude operator sessions. Status: spec; implement in this order as credentials land (`CREDENTIALS_SETUP.md`). Every module has offline tests with recorded fixtures; no live call is made until its env var exists. Nothing here stores secrets.

## 0. Safety rails (build first, test hardest)
- `ops/caps.py`: single source of truth for money caps: `TRACK_B_STAGE1_ADS=150`, `TRACK_B_STAGE2_ADS=250`, `PER_PRODUCT_STAGE1=50`, `TRACK_A_ADS=200`, `TOTAL_BANKROLL=1000`. Any function that creates or raises a budget imports these and refuses to exceed them; the ledger (`finance/FINANCIAL_LEDGER.csv`) is read to compute spend-to-date before any increase.
- Meta campaigns are created with **lifetime budgets and end dates** so caps hold even when no session runs. Daily-budget mode is forbidden in code.
- Idempotency: every external write records an idempotency key in `ops/actions.log` (append-only, committed) before the call; reruns check the log first.
- Kill switch: `ops/killswitch.py pause-all` pauses every active ad set and is the first thing a session runs if ROAS data is missing or the ledger is inconsistent.

## 1. `products/store/shopify_client.py` (Admin GraphQL API, version 2026-07)
- Auth: `SHOPIFY_ADMIN_TOKEN`, `SHOPIFY_STORE_DOMAIN`.
- Ops: create/update products with variants, images, SEO fields; set inventory tracking to "continue selling"/managed by CJ; markets CA (CAD) + US (USD, rounded pricing); shipping profiles with honest delivery ranges (from CJ estimates + 2 days); policies pages (shipping, refunds, privacy, terms) generated from templates; theme settings (Dawn: hero, trust bar, product page blocks); orders read; fulfilment/tracking sync; discounts; abandoned checkout read (for the support agent's context only, no unsolicited email: CASL).
- Tests: fixture-based; a `--dry-run` that prints the mutations.

## 2. `products/store/cj_client.py` (CJ open API v2)
- Auth: `CJ_API_KEY` → access token refresh.
- Ops: product search with warehouse filter (US/CA), variant and shipping-cost query per destination, landed-cost calculator (product + shipping + payment fees), order creation from Shopify orders (or rely on the CJ Shopify app; the client verifies routing and pulls tracking), tracking sync back to Shopify fulfilments.

## 3. `products/store/meta_client.py` (Marketing API)
- Auth: `META_SYSTEM_TOKEN`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, `META_PIXEL_ID`.
- Ops: create campaign (objective SALES, Advantage+ shopping where available), ad set with **lifetime budget** and end date, CA+US targeting, pixel purchase optimization; upload image/video creatives; create ads with honest primary text and a landing URL carrying UTM; pull insights (spend, impressions, clicks, add-to-cart, purchases, ROAS) daily into `KPI_DASHBOARD.md` and `EXPERIMENTS.md`; pause/scale ad sets under the gate rules (+30% every 3 days while ROAS ≥ 1.6; kill rules from EXP-004/005).
- Pixel/CAPI: install the pixel via Shopify's Facebook channel or theme snippet; server events optional in v1.

## 4. Creative pipeline `products/store/creatives/`
- Inputs: supplier photos (rights: provided by the supplier for resale listings), product facts, angle.
- Images: Pillow compositions (1080×1080 and 1080×1350): product on clean background, benefit headline, price badge, trust line; 4 variants per product.
- Video: fal.ai image-to-video (Kling/Wan) 5-10 s clips from 2-3 product photos → ffmpeg (imageio-ffmpeg) stitches clips, adds captions (DejaVu font), 9:16 and 1:1 exports, no music (or CC0 only); 2-3 variants per product; cost target ≤ US$2 per product.
- Copy: honest claims only; delivery time stated on the ad's landing page; no urgency fakery.

## 5. Support agent `products/store/support-agent/` (Cloudflare Worker)
- Inbound: Cloudflare Email Routing (support@domain) → Worker → parse (postal-mime) → D1 `messages`.
- Brain: Anthropic API (Haiku 4.5) with a policy prompt (shipping times, refund policy, tone), tools: Shopify order lookup by email/order number, CJ tracking lookup. Auto-replies for: where is my order, delivery time, change address before shipment, refund request within policy (issue via Shopify refund mutation when order ≤ policy window and not shipped), cancellation. Escalates everything else (writes to D1 `escalations`, surfaced in the next operator run's checklist, SLA ≤ 8 h).
- Outbound: reply via Cloudflare Email Workers send (or Resend if needed); every reply logged; no marketing content (CASL).
- Chargebacks: `disputes.py` pulls Shopify Payments disputes and drafts evidence (tracking, policy, correspondence) for the operator to submit.

## 6. Ledger and KPIs
- `ops/ledger_import.py`: Shopify payouts (Admin API) and Meta invoices/spend (insights) → ledger rows with evidence references; CJ purchase costs per order; Etsy Payments statements for Track A.
- Dashboard fields for Track B: spend, revenue, orders, ROAS, refund rate, delivery complaints, support auto-resolution rate.

## 7. Launch checklist (all must be true before any ad set goes live)
- Store: policies live with real delivery ranges; support address working end-to-end (test email round-trip); pixel firing on purchase (test order); prices and markets set; product pages honest.
- Ads: lifetime caps set in Meta; UTM on all links; creatives reviewed for claims.
- Ops: support agent deployed and tested with 5 scripted cases; kill switch tested; ledger importer tested; `EXPERIMENTS.md` EXP-004 status = running with start date.

## 8. Product-intelligence pipeline (added Day 1 evening after an external audit; D-012)
Purpose: replace a one-time product pick with a scored queue that is re-run on every heartbeat, so the three products that receive stage-1 budget are the best available on launch day, not on September 15.

**Discovery (target 100-300 candidates).** CJ Dropshipping weekly winning-product reports and trending lists (public; API after Block 2A); supplier category feeds; Q4 seasonal lists from at least two independent 2026 sources; optional one-month subscription to one paid ad-intelligence tool (Minea, Dropship.io or Sell The Trend) only if the free pipeline cannot rank with confidence, funded from the tools budget with a cap decision logged first.
**Ad validation.** Meta Ad Library (public transparency tool) queried by product keyword and country via the sandbox's headless browser: count of active ads, number of distinct advertisers, earliest "started running" dates (longevity), media types. Rate-limited, keyword-level, no login. Signal: multiple independent advertisers with ads older than 3-4 weeks and new ads still appearing.
**Demand validation.** Google Trends (pytrends or the export endpoint) for 12-month direction, Q4 seasonality and CA/US geography; Amazon best-seller movement from published reports (no scraping of Amazon).
**Saturation and pricing.** Competitor Shopify stores found by search; their public `/products.json` catalogues give prices, variants and how many stores sell the item; page quality noted by hand-rules (reviews, shipping statement, trust elements).
**Supplier economics.** CJ API: landed cost to CA and US, warehouse stock (US/CA flag), processing and delivery estimates, supplier rating; margin rule (landed ≤ 1/3 retail) and break-even ROAS computed per product.
**Scoring (0-100).** Demand 20, ad longevity/independent advertisers 20, saturation (inverse) 15, margin 15, shipping speed/reliability 15, Q4 relevance 10, creative potential (visual demo, problem obvious in 3 seconds) 5. Legitimacy filter is pass/fail before scoring. Output `products/store/PRODUCT_QUEUE.md` with per-product sub-scores, estimated break-even ROAS, evidence links and a TEST / WATCH / REJECT verdict. Re-run each heartbeat; the queue can change until the day ads launch; a product already in test is not swapped mid-test.
**Implementation.** `products/store/intel/`: `adlibrary_probe.mjs` (Playwright), `trends.py`, `shopify_catalog.py`, `cj_costs.py` (after key), `score.py`, `build_queue.py`; fixtures and offline tests; a `--dry` mode that scores from cached inputs.

## 9. Stage-1 diagnostic gates (replaces "no purchase at CA$50 → kill"; D-012)
The CA$50 per product is a screen, not proof. After each CA$25 of spend (and daily), classify the funnel with Meta insights + Shopify analytics before any kill:
| Symptom | Likely cause | Action (within the product's budget) |
|---|---|---|
| Link CTR < 0.8% after ~1,500 impressions | creative or hook | swap to the next creative variant (2-3 prepared per product); one swap allowed |
| CTR ≥ 0.8% but landing-page-view → add-to-cart < 3% | product page, offer, price | fix page (images, benefits, price test, shipping statement); continue |
| ATC ≥ 3% but initiate-checkout low | trust, shipping cost/time, price shock | fix shipping display, add trust elements, test free shipping threshold |
| Checkouts but no purchases | checkout or payment friction | verify Shopify Payments, wallets, address/tax display |
| CTR ≥ 1.5% and ATC ≥ 5% but no purchase yet at CA$50 | insufficient data | extend from the CA$50 extension pool |
Kill when: CTR < 0.6% after a creative swap, OR the diagnosed fix has been applied and a further CA$25 shows no improvement, OR both CTR and ATC are below threshold. Budget: three screens of CA$50 (CA$150) plus a CA$50 extension pool (moved from stage 2, which becomes CA$200); total ads for Track B unchanged at CA$400. Creative-level reporting (per ad) is mandatory in the daily insights pull.

### 8a. Tooling facts established on Day 1 (what the pipeline can actually use here)
| Source | Status in this sandbox | Use |
|---|---|---|
| Meta Ad Library (browser) | **Works under the owner-approved rule (D-013):** `node products/store/intel/adlibrary_probe.mjs "<keyword>" US|CA [--json]` returns active-ad count, dated ads, earliest start and ads older than 28 days. Occasionally declined by the safety check (LL-008): retry once, then mark unavailable. A few keywords per run. | Ad-longevity and advertiser-breadth signal for scoring (SPEC section 8). Plain fetch still returns 403. |
| Google Trends via `pytrends` (needs `urllib3<2`) | Works | 12-month direction, seasonality, CA vs US geo, related queries. Verified 2026-09-15 for the three Day-1 candidates. |
| Competitor Shopify catalogues (`/products.json`) | Works (plain HTTPS) | Prices, variants, catalogue size, product rotation over time (the two single-product stores cited for the windshield cover had already rotated to other items by Day 1: a signal in itself). |
| CJ Dropshipping | Product pages block automated fetches; API after Block 2A | Landed cost, warehouse stock, delivery estimates, supplier ratings. |
| CJ weekly winning-product reports, Q4 trend lists, Amazon market reports | Public pages via search/fetch | Discovery and demand cross-checks; no Amazon scraping. |
