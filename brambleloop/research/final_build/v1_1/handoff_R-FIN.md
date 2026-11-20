# Handoff R-FIN — repair of the finance audit of final-candidate-ddf9c6e

Source: `research/final_build/audit_ddf9c6e/REPORT_finance.md` (1 HIGH, 12 MEDIUM, 7 LOW).
Branch `claude/r2-FIN` (from `claude/visual-investigation` e631dad). Phase stays SHADOW; no
network, spend, deploy or push.

## Per finding
| ID | Status | Fix (file) | Regression test |
|---|---|---|---|
| H1 | FIXED | `close.checklist` runs post → match → post → `anomalies.detect` itself (`refresh_books`, default on); new `statement_lines` step blocks on any unmatched line dated in the period (read from `acct_statement_lines`); `lock_period` always refreshes, then re-checks inside the journal lock (no unmatched line, no open period exception, no unposted row, same TB hash) before writing the irreversible lock | test_r2_finance_close (3 tests) |
| M1 | FIXED | `cash.position`: bank STALE → reading `stale`; safe budget and runway UNKNOWN unless cash is fresh+reconciled | test_r2_finance_money |
| M2 | FIXED | `cash.position`: unmatched money-moving bank line or balance-snapshot drift → cash UNKNOWN (unreconciled) | test_r2_finance_money |
| M3/L3 | FIXED | `dashboard._drill` takes reading/value from the summary's providers; `check.matches` compares against an independently computed figure | test_r2_finance_money |
| M4 | FIXED | close: STALE orders block; `books.py` sales_reading `STALE` past the 24 h bound; MONEY tab headline/source_health STALE (tabs.py) | close + views tests |
| M5 | FIXED | `views.accrual` exposes revenue/refund non-measured bases; summary gross/net/refunds/contribution/profit `estimated` with signed `estimated_cad` | test_r2_finance_money |
| M6 | FIXED | brief and recorded_spend basis from row bases (`listing_costs.cost_basis`); derived→basis `derived` | test_r2_finance_views |
| M7 | FIXED | tax pack fees None when source UNKNOWN and nothing recorded | test_r2_finance_money |
| M8 | FIXED | posting_rules: sales also keyed on `(sale, evidence_ref)` | test_r2_finance_money |
| M9 | FIXED | Seal v2 (`detail.seal=2`) covers all entry fields incl. reverses_id, dimensions, detail, source_period, posted_at, posting currency/amount_original/memo/line. Old rows verify under v1 and are counted (`legacy_v1_entries`); stripping the marker fails. Tail deletion: cycle records chain anchors (`operating_readings`, kind `finance.accounting.chain_anchor`); verify_chain checks them | test_r2_finance_money (2) |
| M10 | FIXED | `ProfitAndLoss.cash_cad` always None, reading UNKNOWN | test_r2_finance_money; test_finance line ~195 changed from `cash_cad == net_profit` to `cash_cad is None` (stricter; arithmetic still pinned) |
| M11 | FIXED | `policy.check_spend`: kind normalised (ads synonyms → ads), unknown kind blocks; non-finite amount / expected contribution blocks | test_r2_finance_views |
| M12 | FIXED | `dashboard.summary` verifies chain + every lock on read → BLOCKED, `integrity` key | test_r2_finance_close |
| L1 | DEFERRED | Widening DUP_WINDOW / lowering DUP_MIN_CAD flags legitimate repeated identical model calls, and every anomaly blocks the close; charge-id dedup at posting remains the real guard | — |
| L2 | FIXED | `spend_report.record` refuses negative / NaN / inf | test_r2_finance_money |
| L4 | FIXED | `money_drill("revenue")` returns the headline rows with a check and a note distinguishing it from 30-day gross_sales | test_r2_finance_views |
| L5 | PARTIAL | by design a pre-launch MODELLED gate where assumed volume may only block (existing tests pin it); added `evidenced_by_measured_orders` | test_r2_finance_money |
| L6 | FIXED | late adjustment opens a `late_adjustment` exception in the booking period | test_r2_finance_close |
| L7 | FIXED (forecast) / DEFERRED (lock caller) | forecast averages over actual history; no autonomous `lock_period` caller added — an irreversible lock stays an owner/operator action | test_r2_finance_close |

## Verification
All 23 new tests fail on e631dad (ddf9c6e finance code) and pass here.
