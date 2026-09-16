# CURRENT_STATE

_Last updated: 2026-09-16T00:20Z (Day 1, heartbeat)_

## One-paragraph state

Day 1. Strategy selected (D-005) and amended the same evening (D-009): **Track A, MapleSheets** (Etsy shop of Canadian small-business templates, plus a print-on-demand line) is the floor; **Track B, a capped paid-social e-commerce store** (Shopify + CJ Dropshipping + Meta ads + AI creatives + AI support agent) is the owner-authorized swing with stage gates. The AODA/WCAG scanner is now a backlog option only. Listing 1 (Canadian Sole Proprietor Bookkeeping System, T2125 edition 2026, CA$29), listing 2 (GST/HST quick-method calculator + small-supplier tracker, CA$14) and listing 3 (Home-Office and Vehicle Expense Workbook, CA$12) are built, validated (0 formula errors, key values verified, including the home-office loss-cap logic against a below-cap net income) and packaged with copy and images. The Etsy API client is written and unit-tested. Nothing is published yet because the shop does not exist: **owner Block 1 in `OWNER_ACTIONS.md` is the only blocker.** No money has been spent.

## Money

| Item | Value |
|---|---|
| Starting bankroll (authorized max) | $1,000.00 CAD |
| Capital deployed | $0.00 |
| Spent to date | $0.00 |
| Gross revenue to date | $0.00 |
| Allocation (MASTER_STRATEGY) | Track A ≤ $190; Track B ≤ $520 in two gated stages; reserve ≥ $290 |

## What is running

- **Mission heartbeat is live:** Routine `trig_019rtbCKLSFc8hNajuiWm9E4` fires the persistent operator session `session_01GpoRAgr4kBWxi1752HufQh` at 00:14, 08:14 and 16:14 UTC; plumbing verified by a test commit (`AUTOMATIONS.md`).

## Owner-only blockers

- **Block 1 (Etsy shop + API app + OAuth, optional Printify), ~45-55 min** and **Block 2 (Shopify, CJ, Cloudflare, Anthropic, Meta, fal.ai), ~2 h in three parts** — `OWNER_ACTIONS.md`. Owner confirmed on Day 1 they will do both. Until Block 1: no Etsy listings. Until Block 2A/2B/2C: no store build / support agent / ads respectively.

## Exact next actions (in order)

1. When the owner says the shop exists and `ETSY_KEYSTRING` is in the environment: run `products/etsy-templates/etsy_api.py auth-url`, post the link, exchange the pasted redirect URL, hand back the refresh token for the environment variable.
2. Competitor pull: `etsy_api.py search "bookkeeping spreadsheet canada"` (and "T2125", "GST HST tracker", "canadian tax template"); write `research/etsy/competitors-<date>.json` and the keyword-neighbourhood note; adjust listing 1 title/tags if the data says so.
3. Resolve the taxonomy id (`etsy_api.py taxonomy template`), create listing 1 as draft, upload the ZIP and six images, activate; record the listing id in `products/etsy-templates/listings.json`.
4. Start EXP-001 (14-day visibility test): daily stats pull → `KPI_DASHBOARD.md`.
5. Build listing 2 (quick-method calculator + small-supplier tracker) with its own tests; publish; then the bundle.
6. **Track B:** product research done (`products/store/PRODUCT_RESEARCH.md`, D-011: cocktail smoker kit, windshield snow cover, pet brush bundle; brand Pine and Nook). Next: implement `products/store/SPEC.md` modules 0-3 with offline tests now; when Block 2A lands, verify CJ landed costs/warehouses and re-confirm or swap products; when 2B lands, trademark check → buy domain via Cloudflare API → support agent; when 2C lands, creatives → launch checklist → EXP-004.
7. Meanwhile for Track A (no credentials needed): listing 4 (instalment planner; verify 2026 federal/provincial brackets and CPP rates first — not yet done, needs a web check) generator with tests and images; ledger importer for Etsy Payments; `ops/status.py` Etsy extension; Printify API client + 3-5 Canadian-gift designs for the POD line (publish once `PRINTIFY_TOKEN` exists).
