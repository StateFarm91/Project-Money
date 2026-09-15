# THIS IS CLAUDE'S COMPETITION STRATEGY

_Selected 2026-09-15 (Day 1) on the evidence in `research/` after a 42-candidate sweep, five finalist deep-dives and an adversarial review (`research/ADVERSARIAL_REVIEW.md`). Decision D-005. This record changes only through `DECISION_LOG.md`._

## Business and target customer
**MapleSheets (working name; "MapleLedger" and "NorthLedger" are existing Canadian bookkeeping firms and were rejected): an Etsy shop of Canadian small-business templates.** Customers are Canadian sole proprietors, freelancers and Etsy/Shopify sellers who do their own bookkeeping for CRA Form T2125 and GST/HST and search Etsy for "bookkeeping spreadsheet canada", "T2125 template", "GST HST tracker". Evidence: several Canadian-specific listings already sell there (one at 4.8 stars), Etsy has native buyer search and in-marketplace ads at US$0.20-0.60 per click, and Etsy's seller API is approved in minutes for the owner's own shop, so the operator can publish and iterate listings itself.

## Problem and product
US and generic templates do not map to T2125 lines or handle GST/HST/PST/QST, the quick method, home-office and vehicle claims, or the $30,000 small-supplier rule. Products (spec in `products/etsy-templates/SPEC.md`, built by `build_templates.py`, every rate cross-checked against CRA pages in `TAX_REFERENCE.md`):
1. Canadian Sole Proprietor Bookkeeping System, T2125 edition (Excel + Google Sheets) — CA$29. Built (v1.0), validation in progress.
2. GST/HST Quick Method vs Regular calculator + small-supplier tracker — CA$14.
3. Home-office and vehicle expense workbook (Part 7 + Chart A) — CA$12.
4. Tax set-aside and instalment planner — CA$12.
5. Bundle — CA$44.
Line extensions after the 14-day test, chosen from Etsy API data (views/favourites of competitor listings): e.g. Shopify/Etsy-seller variant, therapist/allied-health practice templates (C08).

## Pricing and monetization
One-time digital downloads on Etsy (Etsy is the payment processor and collects sales tax where it is the marketplace facilitator). Net per CA$29 sale ≈ CA$25.7 before ads (listing US$0.20, 6.5% transaction, 3% + C$0.25 processing). Bundle raises ad-driven average order value. Own-domain checkout via Stripe only later, if Etsy proves demand.

## Distribution and first-customer plan
- **First 10:** Etsy search. Two listings live by Day 8, bundle by Day 12; titles, 13 tags and attributes built from competitor keyword neighbourhoods pulled through the API; 6 images per listing; AI assistance disclosed per Etsy's Creativity Standards. Etsy Ads at CA$3/day on the single best-performing listing from the day the 15-day new-shop wait ends (~Day 20-23); kill at 100 clicks with zero sales.
- **First 100:** reviews compounding search rank; bundle; weekly title/tag rewrites from API view data; Q4 "get ready for the 2026 tax year" angle; more SKUs in the same shop (they inherit the shop's reviews); tax season (Feb-Apr 2027) as the Day-180 payoff.
- **Why buy this rather than alternatives:** deeper Canadian coverage (all four sales-tax regimes, quick vs regular method with RC4058 rates, T2125 line mapping, Part 7 and Chart A schedules, small-supplier tracker), Excel and Sheets in one purchase, tested formulas with a visible version stamp, plain-English instructions.

## Why this beat the other finalists
- F2 (AODA/WCAG scanner): the adversarial review showed the demand thesis was wrong for 20-49 employee organizations (self-attestation, no website obligation), automated reports are a commodity with free vendor scanners, a CA$100 search-ads test is noise at CA$3-5+ CPC, and a new domain will not rank inside 90 days. Kept only as a deferred, cheap pre-test (`BACKLOG.md`).
- F3 (Bill 96 scan/pack): Shopify's free Translate & Adapt and CA$17/mo apps make French cheap; no evidence of paid intent; parked.
- F4 (chat-to-court PDF) and F5 (Express Entry alerts): proven intent but saturated (F4) or dependent on community posting the operator cannot do (F5).
- Runner-ups C03/C08/C28/C25 carry the same distribution objections without Etsy's native search and cheap in-marketplace ads.
- The channel finding that decided it: the only channels the operator can run end-to-end are marketplaces with native search and a publishing API. Etsy is the strongest of those for a Canadian owner.

## Initial capital allocation (CAD)
| Item | Amount | Type |
|---|---|---|
| Etsy shop setup fee + listing fees | ~40 | exploration |
| Etsy Ads (CA$3/day, capped) | ≤200 | exploration, released only after the 14-day test passes |
| Track B pre-test domain (deferred) | ≤15 | exploration |
| **Exploration cap** | **≤300** | |
| Reserve | ≥700 | growth capital, released only on measured ROAS/conversion |

## Day-90 economics (CAD; adversarially adjusted, `finance/PROJECTIONS.md`)
| | Downside | Base | Upside |
|---|---|---|---|
| Gross revenue | 0 | 300-450 | 1,200-1,800 |
| Net after fees, ads, setup | −250 | 0 to +150 | +900-1,300 |
P(first revenue ≤ 30 days) ≈ 40% **[med]**. This is a small, honest base case; the asset (shop, reviews, catalogue) peaks in tax season after Day 90.

## Targets
| Day | Date | Target |
|---|---|---|
| 7 | 2026-09-21 | Owner Block 1 done (shop live, API key, OAuth token); competitor listing data pulled; workbook v1 validated; listing 1 published |
| 14 | 2026-09-28 | 2 listings + bundle live; ≥ 50 cumulative views; heartbeat Routine running unattended |
| 30 | 2026-10-14 | 14-day visibility test evaluated (≥150 views and ≥1 sale or ≥5 favourites); Etsy Ads running; first sale; 4 listings live |
| 60 | 2026-11-13 | ≥ 8 cumulative sales (base); ads ROAS measured; line-extension decision; Track B pre-test only if A is stable |
| 90 | 2026-12-13 | ≥ 12 sales, ≥ 3 reviews, base revenue CA$300-450; Day-180 plan for tax season written |

## Kill, pivot, scale
- **14-day visibility test (EXP-001):** by the 14th day the shop is live, < 150 views or (0 sales and < 5 favourites) → rewrite titles/tags and SKUs before any ad spend; if a second 14 days fails → the niche is too thin: pivot SKUs (C08 line) or channel.
- **Ads (EXP-002):** 100 clicks with zero sales → stop ads on that listing.
- **Day-35 gate:** < 300 total views or 0 sales → stop ads, keep listings passive, redeploy compute to SKU pivot or the Track B pre-test.
- **Scale:** ads ROAS > 2 → raise budget in CA$2/day steps; a listing converting > 3% → clone the pattern into adjacent SKUs; ≥ 3 reviews → launch own-domain checkout and a Canadian SEO page.

## Automation architecture
Workbooks generated and tested by code (`build_templates.py`, formula evaluator tests); listings created/updated via Etsy Open API v3 (seller app, OAuth refresh token held in the Claude Code environment variables, never in the repo); listing images rendered programmatically; Etsy delivers files and receipts; daily API pull of views/favourites/orders → `KPI_DASHBOARD.md`; ledger rows from Etsy Payments statements; the mission-heartbeat Routine (`AUTOMATIONS.md`) runs the operator ~2-3 times per day within the compute budget. Owner-only actions are batched in `OWNER_ACTIONS.md`.

## Minimum owner involvement
- **Block 1 (Day 2, ~45 min):** open the Etsy shop (ID + selfie, bank, setup fee), create the seller API app, complete one OAuth approval, paste two secrets into the environment settings.
- **Later, 5 min each:** turn on Etsy Ads when the operator asks (after the 15-day wait); reply to any Etsy account-review request the operator drafts.
- **Weekly ≤ 10 min:** read the operator's summary; send operator-drafted replies to buyer messages if any.
- **Block 2 (deferred, ~40 min):** domain + Cloudflare + Stripe + Resend only if/when the Track B pre-test page is ready.
