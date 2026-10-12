# W4-CCFINST: F-620 Command Center Finance (owner statement, MTD beside YTD)

Branch `claude/w4-CCFINST`, based on INTEG2 `16e36ae`.

**Criterion** (registry F-620, quoted): "Show MTD/YTD sales, refunds, Etsy fees, free ad credit, cash ad spend, AI/infrastructure/software expenses, contribution profit, margin, tax reserve, payout/cash position, unreconciled items and monthly-close status."

CCFM1 recorded this row as blocked on F-614 and F-610. Both producers now exist:

- the credit wallet `finance.credits`, with an `ads_credit` kind (F-629/F-614);
- the Accountant's `close.status`, MTD/YTD windows and exceptions.

So the row is buildable now.

## What is built

`app/command_center/finance_statement.statement(db)` produces the statement. It appears in the Money tab as the section `finance_statement`, rendered by `money.js` `financeStatementCard`: a three-column table (Line, MTD, YTD) plus the monthly-close line. It fits 390 px.

Each line keeps its producer's reading:

| Line | Source and rule |
|---|---|
| Sales, refunds, Etsy fees, contribution, tax reserve, cash, expected payout | The Accountant's summary for windows `mtd` and `ytd` |
| AI & image spend, infrastructure & software | The accrual per-account split. These are recorded cost rows, so they read RECORDED, not measured. |
| Free ad credit | Wallet `ads_credit` rows, ESTIMATED because the draw order is assumed. With no ad credit recorded it is UNKNOWN, because an unrecorded credit is not a zero credit. |
| Cash ad spend | Recorded advertising spend. When an ad credit exists it is ESTIMATED: recorded spend less the credit estimated drawn. |
| Margin | Contribution divided by net sales, only when both are known and net sales is positive |
| Unreconciled items | The count of open accounting exceptions |
| Monthly close | Whether the previous period is locked (`close.status`) |

Any cell the source cannot give is UNKNOWN with a reason, never CA$0.00. The statement writes nothing of its own. The only write is the Accountant's existing idempotent posting refresh.

## Tests

`tests/test_w4_ccfinst.py` has 4 tests. The cc_mock gains a `ccfinst money` block, which checks MTD beside YTD, that unknown cells read Unknown, and the fit at 390 px.

## Results
These results are from before the INTEG2 `16e36ae` merge, on `083c9fc`, through the gate:

| Test | Passed |
|---|---|
| test_w4_ccfinst | 4/4 |
| test_v11_cc_views | 13/13 |
| test_w4_ccfm1 | 8/8 |
| test_w4_ccgap_views | 10/10 |
| test_v11_pwa_static | 81/0 |
| test_cert_dashboard | 18/18 |

## Checkpoint (2026-10-12, controlled pause)

**Status:** PARTIAL. The code is complete, but verification is incomplete.

**Rows:** F-620 advanced, pending the browser check.

**Not run:**

- the cc_mock check, including the new `ccfinst money` block;
- the required regression set;
- the post-merge rerun.

**Known defects:** none known. The mock block has never been executed, so a selector or regex fix may be needed.

**Next step:** run the following through the gate:

1. `test_w4_ccfinst`;
2. the required set: test_vacuity, test_launch, test_cost_governance_wave2, test_search_hero_publish, test_cert_listing_frames, test_v11_autonomy_timeline;
3. `node tests/fixtures/cc_mock/check.mjs`.

Fix any red.
