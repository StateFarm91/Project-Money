# CURRENT_STATE

_Last updated: 2026-09-15T17:10Z (Day 1)_

## One-paragraph state

Day 1. Strategy selected (D-005): **MapleSheets**, an Etsy shop of Canadian small-business templates, run sequentially; the AODA/WCAG scanner is a deferred cheap pre-test and Bill 96 is parked. Listing 1 (Canadian Sole Proprietor Bookkeeping System, T2125 edition 2026, CA$29) is built, validated (0 formula errors, key values verified) and packaged with a quick-start PDF, README and six listing images. The Etsy API client is written and unit-tested. Nothing is published yet because the shop does not exist: **owner Block 1 in `OWNER_ACTIONS.md` is the only blocker.** No money has been spent.

## Money

| Item | Value |
|---|---|
| Starting bankroll (authorized max) | $1,000.00 CAD |
| Capital deployed | $0.00 |
| Spent to date | $0.00 |
| Gross revenue to date | $0.00 |
| Exploration cap (MASTER_STRATEGY) | ≤ $300 CAD; reserve ≥ $700 |

## What is running

- Nothing unattended yet; the mission-heartbeat Routine is created at the end of the Day-1 session (`AUTOMATIONS.md`).

## Owner-only blockers

- **Block 1 (Etsy shop + API app + OAuth), ~45 min** — `OWNER_ACTIONS.md`. Until done: no listings, no EXP-001.

## Exact next actions (in order)

1. When the owner says the shop exists and `ETSY_KEYSTRING` is in the environment: run `products/etsy-templates/etsy_api.py auth-url`, post the link, exchange the pasted redirect URL, hand back the refresh token for the environment variable.
2. Competitor pull: `etsy_api.py search "bookkeeping spreadsheet canada"` (and "T2125", "GST HST tracker", "canadian tax template"); write `research/etsy/competitors-<date>.json` and the keyword-neighbourhood note; adjust listing 1 title/tags if the data says so.
3. Resolve the taxonomy id (`etsy_api.py taxonomy template`), create listing 1 as draft, upload the ZIP and six images, activate; record the listing id in `products/etsy-templates/listings.json`.
4. Start EXP-001 (14-day visibility test): daily stats pull → `KPI_DASHBOARD.md`.
5. Build listing 2 (quick-method calculator + small-supplier tracker) with its own tests; publish; then the bundle.
6. Meanwhile (no credentials needed): listing 2-4 generators, shop policy and About text for the owner, ledger importer for Etsy Payments.
