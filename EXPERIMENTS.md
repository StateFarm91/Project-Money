# EXPERIMENTS

Every major commercial assumption is an experiment. Template:

```
### EXP-NNN: <name>
- Status: planned | running | concluded
- Hypothesis:
- Max test cost:
- Expected result:
- Primary metric:
- Success threshold:
- Failure threshold:
- Decision deadline:
- If successful:
- If unsuccessful:
- Result / decision (filled at conclusion):
```

## Log

### EXP-001: Etsy visibility test (the most important 14-day test)
- Status: planned (starts the day the shop is live)
- Hypothesis: Etsy search shows a zero-review Canadian finance template listing to real buyers.
- Max test cost: CA$40 (shop setup + listing fees); no ads.
- Expected result: ≥150 cumulative views across the first two listings within 14 days of going live.
- Primary metric: daily listing views and favourites from the Etsy API (`getListing` / shop stats), benchmarked against competitor `views`/`num_favorers` from `findAllListingsActive`.
- Success threshold: ≥150 views AND (≥1 sale OR ≥5 favourites) by day 14 live.
- Failure threshold: <150 views OR (0 sales AND <5 favourites).
- Decision deadline: day 14 live (target 2026-10-06 if the shop opens 2026-09-22).
- If successful: fund Etsy Ads (EXP-002) on the best listing; publish the bundle and listings 3-4.
- If unsuccessful: rewrite titles/tags from competitor data; swap SKUs (C08 line); second 14-day window; no ad spend.
- Result / decision: pending.

### EXP-002: Etsy Ads unit economics
- Status: planned (eligible after the 15-day new-shop wait)
- Hypothesis: in-marketplace ads on the best listing produce sales at CAC below CA$20.
- Max test cost: CA$100 (CA$3/day, one listing, ~30 days) within the CA$200 ads cap.
- Expected result: 1 sale per 4-8 days at 2% conversion; better if digital converts at 3-5%.
- Primary metric: ad-attributed orders, clicks, spend (Etsy Ads dashboard, entered by the owner's 5-min check or read from order attribution).
- Success threshold: ROAS ≥ 2 over 100 clicks.
- Failure threshold: 100 clicks with 0 sales.
- Decision deadline: 100 clicks or 30 days, whichever first.
- If successful: raise budget in CA$2/day steps; extend to the bundle.
- If unsuccessful: stop ads; keep listings passive; SKU/keyword pivot.
- Result / decision: pending.

### EXP-003: Track B pre-test (deferred; only if EXP-001 passes and compute allows after Day 21)
- Status: deferred
- Hypothesis: strangers will pay CA$29 for a full-site automated WCAG pre-check delivered by email.
- Max test cost: CA$15 (domain) + owner Block 2 (40 min).
- Primary metric: free scans/week and paid pre-checks.
- Success threshold: ≥2 paid by day 21 of the page being live. Failure: <30 free scans/week or 0 paid → freeze.
- Result / decision: pending.

### EXP-004: Track B stage 1 — three products, kill fast
- Status: planned (needs OWNER_ACTIONS Block 2 and 3 researched products)
- Hypothesis: at least one of three research-selected products converts on Meta at ROAS ≥ 1.2 within CA$50 of spend each.
- Max test cost: CA$150 ads + CA$20 store/domain + CA$35 fal.ai + CA$35 Anthropic credits.
- Expected result: 1 of 3 products reaches ≥ 2 purchases.
- Primary metric: purchases, ROAS, add-to-cart rate, CPC (Meta Marketing API insights; Shopify orders).
- Success threshold: any product with ≥ 2 purchases and ROAS ≥ 1.2 at CA$50 spend.
- Failure threshold: per product: CA$50 spent with 0 purchases, or 60 clicks with 0 add-to-carts → kill. Track: all three killed → Track B stops.
- Decision deadline: 10 days after ads start.
- If successful: EXP-005 (stage 2 scale) on the passing product.
- If unsuccessful: Track B stops; budget back to reserve; lessons logged.
- Result / decision: pending.

### EXP-005: Track B stage 2 — scale the passing product
- Status: planned
- Hypothesis: the passing product holds ROAS ≥ 1.6 while budget rises 30% every 3 days up to CA$250 additional spend.
- Primary metric: ROAS on ≥ 20 purchases; refund rate < 8%; delivery complaints < 5%.
- Success threshold: ROAS ≥ 1.6 sustained; then reinvest proceeds.
- Failure threshold: ROAS < 1.2 over any CA$80 of spend → stop scaling; ROAS < 1.0 → kill.
- Decision deadline: CA$250 spent or Day 60, whichever first.
- Result / decision: pending.
