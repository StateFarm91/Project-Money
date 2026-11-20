# F1 (C06) — Etsy shop: Canadian small-business finance templates

_Deep-dive 2026-09-15 (Day 1). Uncertainty labels: **[low]** well-evidenced, **[med]** partly evidenced, **[high]** assumption. Evidence URLs are in `research/candidates/CANDIDATES.md` (C06) plus the verification searches noted here._

## Business and target customer
Canadian sole proprietors, freelancers and Etsy/Shopify sellers who do their own bookkeeping for CRA Form T2125 and GST/HST. They search Etsy for "bookkeeping spreadsheet canada", "T2125 template", "GST HST tracker", "canadian tax tracker". **[low]** Verified live: multiple Canadian-specific listings exist (T2125 Form Helper 4.8-star; "Canada Etsy Shopify Bookkeeping Spreadsheet"; "Canadian Bookkeeping Spreadsheet Template"; "Business Use of Home Expenses ... T2125", listed 2025-08-22), and Etsy has a "bookkeeping template" market page for Canada.

## Problem and offer
Generic US templates do not map to T2125 lines or handle GST/HST/QST/PST, quick method vs regular method, home-office and mileage claims, or quarterly instalments. Offer: a line of 4-6 listings built as Google Sheets + Excel:
1. Core Canadian bookkeeping system (T2125 mapping, income/expense, sales-tax by province, dashboard) CA$29.
2. GST/HST tracker + quick-method vs regular-method calculator CA$14.
3. Home-office and vehicle/mileage claim workbook CA$12.
4. Quarterly instalment and tax-set-aside planner CA$12.
5. Bundle of all CA$44. Later: Shopify/Etsy-seller variant, 2027 tax-year edition.
AI assistance disclosed per Etsy's 2025-26 Creativity Standards. **[med]** on which listings sell; **[low]** on the format.

## Pricing and monetization; fee stack
Etsy Canada: listing US$0.20; 6.5% transaction; 3% + C$0.25 processing; GST/HST charged on Etsy's fees; Offsite Ads 15% only on attributed sales (optional under US$10k/yr); one-time shop setup fee US$15-29 **[low]** (sources in CANDIDATES.md C06). Net on a CA$29 sale ≈ CA$25.7 before ads (≈ 89%). Digital items are not held in a payment reserve **[low]**.

## Competitors (verified)
| Name | URL | Price | Weakness |
|---|---|---|---|
| Etsy Tax Template / T2125 Form Helper | etsy.com/listing/4336668570 | not captured (typ. CA$15-35) | Etsy-seller-specific; no multi-regime sales tax or CSV import claims **[med]** |
| Canada Etsy/Shopify Bookkeeping Spreadsheet | etsy.com/listing/1120208853 | not captured | "NOT tax registered" sellers only |
| Canadian Bookkeeping Spreadsheet Template | etsy.com/listing/1511437457 | not captured | generic P&L; no T2125 mapping evident |
| Business Use of Home Expenses (T2125/T2042/T2121) | etsy.com/listing/1453411810 | not captured | single-purpose |
Roughly 8-12 Canadian-specific listings vs hundreds of US ones **[med]**.

## Distribution
- First 10 customers: Etsy search on long-tail Canadian tax keywords (titles, 13 tags, attributes), 5-8 mockup images per listing, honest descriptions; Etsy Ads at CA$3-5/day once the 15-day new-shop waiting period ends **[low]** (verified: minimum $1/day; 15-day wait; digital conversion 3-5%; run untouched 30 days).
- First 100: reviews compounding search rank; seasonal editions (2027 tax year, Q4 "get ready for tax time"); a companion SEO page on the operator's own domain linking to the shop; cross-listing the bundle on the operator's own site via Stripe Managed Payments (Etsy's ToS allows selling elsewhere).
- Why buy this over alternatives: deeper Canadian coverage (all four sales-tax regimes, quick vs regular method, instalments) in both Sheets and Excel, updated for the tax year, with disclosed AI assistance and clear screenshots. **[med]**
- Cost to reach: ads CA$150-250 over the window; listing fees < CA$5. Distribution hypothesis testable in ~21 days after shop opening. **[low]**

## Timelines and probabilities
- Owner opens shop + ID/selfie + fee + bank: Day 2-5 (owner block). Operator builds templates Day 2-6; listings via Etsy seller-app API Day 6-8; ads from ~Day 20-22.
- Days to MVP: 6. Days to first customer: 12-30 **[med]**.
- P(first revenue) ≤7d: 5% · ≤14d: 30% · ≤30d: 60%. **[med]**

## Economics (CAD)
| | Downside | Base | Upside | Assumptions |
|---|---|---|---|---|
| Day-30 revenue | 0 | 60 | 250 | 2 sales base; organic only until ads start |
| Day-90 revenue | 50 | 450 | 1,800 | base: ~16 sales across listings at ~CA$28 avg; upside: ads ROAS>2 + Q4 pre-tax-season demand |
| Day-90 net profit | −250 | 210 | 1,300 | fees 11%, ads 150-250, setup 40 |
Uncertainty **[high]** on volumes; **[low]** on fees. Gross margin ≈ 89% before ads. Likely CAC via ads CA$5-15 per sale **[med]**. Payback immediate on one-time sales. Pricing power medium (CA$10-45 band). Sales cycle: minutes (impulse/search). Repeat: low per customer; asset compounds via reviews and yearly editions.

## Failure
P(meaningful failure) ≈ 40%. Causes: zero-review shop not surfaced against incumbents with hundreds of reviews; ads not converting; Etsy AI-content policy friction; the strongest demand window (Feb-Apr) is after Day 90.

## Capital
Setup CA$40 (shop fee + listings); ads CA$150-250; total CA$200-300. Working capital none (digital).

## Owner workload
Setup 45-60 min (create shop, photo-ID + selfie verification, Etsy Payments bank details, accept terms, pay setup fee, create a Seller App API key at developers.etsy.com and hand it over, set Etsy Ads daily budget once eligible). Weekly ≤10 min (occasional buyer messages the operator drafts replies for; the operator cannot log into Etsy's inbox).

## Automation architecture
Templates generated by Python (openpyxl; Sheets versions via Google Sheets API or as .xlsx importable) with automated formula tests; listings created/updated through Etsy Open API v3 with a Seller App (approved in minutes for own-shop use, verified); images rendered programmatically; Etsy delivers files and receipts; daily API pull of views/favourites/orders into `KPI_DASHBOARD.md`; ledger rows from Etsy Payments statements. Etsy Ads budget changes are a dashboard action (no ads API) **[med]**.

## Platform and legal risks
Etsy Creativity Standards (disclose AI assistance; handmade/"designed by seller" framing is accurate: the operator designs the workbook); no tax advice claims (templates, not advice; disclaimer); Canadian tax rates change yearly (maintenance). Refunds on digital items are rare but honoured.

## Kill / pivot / scale
- Kill: by Day 35 (≈ Day 14 of ads) fewer than 300 total listing views or zero sales → stop ads, keep listings passive, reallocate.
- Pivot: if views are high but sales low → price/preview/image experiments; if one listing sells → deepen that niche (e.g. Shopify-seller variant).
- Scale: ads ROAS > 2 → raise budget in steps; add C08-style profession templates as new lines; add own-domain checkout.
Day-180 potential **[med]**: peak season Feb-Apr 2027; reviews and yearly editions compound.
