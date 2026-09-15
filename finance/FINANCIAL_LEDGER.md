# FINANCIAL_LEDGER

The auditable record of **actual** financial events is `finance/FINANCIAL_LEDGER.csv`. Projections are in `finance/PROJECTIONS.md` and never mix with actuals.

Columns: id, datetime_utc, description, business/product/channel, revenue, expense, platform/payment fees, advertising, refunds/chargebacks, net contribution, running available cash, capital deployed/committed, evidence reference (receipt, payout report, statement).

Rules:
- One row per real event, with an evidence reference. Pending or expected amounts are not events.
- "Running available cash" starts at the authorized 1,000.00 CAD and moves only on real spend, real received payouts, or owner reallocation.
- Revenue is recorded when the platform confirms the sale; payouts and fees are recorded when they post.
- `python3 ops/ledger.py` summarizes the CSV for the dashboard.

## Summary (Day 1)

| Item | CAD |
|---|---|
| Gross revenue | 0.00 |
| Expenses (all categories) | 0.00 |
| Net contribution | 0.00 |
| Available cash | 1,000.00 (authorized, owner-held) |
| Capital deployed / committed | 0.00 |
