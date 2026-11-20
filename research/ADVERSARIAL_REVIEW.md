# Adversarial review of the two-track plan (Day 1)

Produced by a skeptical reviewer agent on 2026-09-15 with 6 searches and 3 fetches. Verdicts adopted in D-005: Track A (Etsy) survives, downgraded to a roughly break-even base case; Track B (AODA scanner) does not survive as specified (demand thesis wrong for 20-49 employee organizations; commodity reports; ads test too small to signal; new domain cannot rank in 90 days) and is kept only as a deferred cheap pre-test; F3 parked; parallel tracks rejected in favour of sequential execution because of the compute budget (LL-001).

## Objections carried into the plan
- D1 (strong): AODA website WCAG 2.0 AA obligation applies to 50+ employee organizations; the Dec-31-2026 filing is a self-attestation. Sources: mccarthy.ca 2026 AODA deadlines; levelaccess.com AODA 2026 checklist.
- D4 (strong): accessibilitychecker.org, UserWay, accessiBe all have AODA pages with free scanners; a CA$59 automated report has no precedent SKU.
- D5 (moderate): F1 comparable sales volumes were never captured (Etsy returns 403 to fetchers) → pull `findAllListingsActive` views/favourites via the API on Day 2-3 before building all SKUs.
- D6 (moderate): Sept-Dec is off-season for tax templates → lead with the year-round core SKU and a Q4 angle.
- X1 (moderate): Etsy Ads math is marginal for a CA$29 item (CPC US$0.20-0.60, ~2% conversion) → one listing, CA$3/day, bundle for AOV, kill at 100 clicks/0 sales.
- X2 (strong): Google Ads at CA$5-10/day cannot signal → no Google Ads account.
- X3 (strong): new-domain SEO is a Day-180 asset only.
- E1 (strong): sequence A then B; persist partial builds every run.
- E2 (moderate): Stripe Managed Payments is an async eligibility review → not on the critical path; plain Stripe first if own-domain checkout is ever needed.
- E3 (moderate): disclose AI assistance correctly; make tested formulas the selling point.
- E6 (moderate): if B is ever built, call it an "automated pre-check", never "readiness" or "compliant".
- E7 (moderate): one wrong rate is a 1-star review → automated rate tests with source URLs, version stamp, no-argument refunds.
- E9 (moderate): split the owner block; Etsy only on Day 2.

## Adjusted numbers (CAD)
| | Original | Adjusted |
|---|---|---|
| A: P(first revenue ≤30d) | 60% | 40% |
| A: Day-90 base revenue / net | 450 / 210 | ~300 / ~0 to +40 |
| B: P(first revenue ≤30d) | 35% | 10-15% |
| B: Day-90 base revenue / net | 900 / 560 | ~200 / ~−100 |

## The single most important 14-day test
"Does Etsy search show a zero-review Canadian finance listing to real buyers?" Metric: daily views and favourites via the API, benchmarked against competitor listings. Pass by Day 14 of the shop being live: ≥150 views and (≥1 sale or ≥5 favourites). Pass → fund ads and the bundle. Fail → pivot SKU/keywords before any ad or Track-B money.

Full reviewer output is preserved in the Day-1 session transcript; sources: mccarthy.ca, levelaccess.com, accessibilitychecker.org, userway.org, accessibe.com, docs.stripe.com (managed-payments eligibility), listingview.io, insightagent.app, iscompliant.app, selfemployed.com, seonib.com, wordstream.com, theedigital.com, digitalapplied.com, w3era.com.
