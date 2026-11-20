# Lane J audit -- AREA finance -- candidate ddf9c6e (final-candidate-ddf9c6e)

Verdict: CONDITIONAL. No LAUNCH-BLOCKING item (shadow phase; the package has no capability to move money,
file tax, bank or borrow -- `guardrails.audit_package()` ok, no network imports). 1 HIGH, 11 MEDIUM, 7 LOW.
All repros: `sh run_all.sh` (this dir; temp SQLite, sockets refused). Interpreter .venv/bin/python, PYTHONPATH=src.

## HIGH
H1. Month-end close locks with unreconciled statement lines / undetected anomalies  (p19_close_gap.py)
  close.py:77-95 (checklist reads only exceptions already opened) and :119 (lock_period). The checklist does
  not run reconciliation.match() / anomalies.detect() nor read `acct_statement_lines.state`. Repro: after a cycle,
  import two etsy_ledger lines for the prior month matching nothing, no match() -> `closable=True`, lock written,
  verify_lock intact; match() afterwards opens 2 `unmatched_statement_line` exceptions in the now-locked period
  (they can never block). Lock is irreversible. Same for duplicate cost rows (anomaly never opened until detect()).
  Fix: checklist calls match()+detect() (or blocks if last cycle < last statement import / any unmatched line in period).

## MEDIUM
M1. Stale bank cash rendered `measured` (p02 A). cash.py:99 `cash_reading = "measured" if cash_known` while
  health.cash_known includes STALE (bank >7d). Bank imported 9 days ago -> cash CA$500.00 `measured`, MONEY tab
  state MEASURED, safe_discretionary_budget CA$188.95 `derived`, no stale marker on the item. Fix: reading "stale".
M2. Unmatched bank deposit -> cash CA$0.00 `measured` (p02 B). Only matched bank lines post to 1000
  (posting_rules.py:_bank_desired); deposit 900 unmatched + balance snapshot 1234 -> summary/drill cash 0.0
  measured/OK. Drift anomaly exists but only after detect(); the figure is a proxy shown as measurement.
M3. drill("expected_payout") returns status OK value 0.0 on disconnected order source (p01) while summary says
  UNKNOWN. dashboard.py:357 only treats `cash` as unknowable; expected_payout/owner_payable are "derived".
M4. Stale orders shown MEASURED (p13): last receipt read 10 days ago -> ledger summary `stale` but
  MONEY tab headline revenue MEASURED (dashboard_truth.revenue_reading), source_health.warning None,
  books.py sales_reading "measured" (orders_ingest.py:217 has no freshness bound; only accounting/health.py does).
  close.py:59 also passes STALE as "source_completeness pass" (p03: lock with orders 3d stale).
M5. FX-assumed revenue labelled measured / actual (p09). dashboard.py:128-135: gross/net/refunds reading=`sr`,
  estimated_cad=0.0 though revenue_by_basis = {measured 80.0, modelled 12.59} (USD sale at assumed rate). Profit is
  also "measured"-capable if only revenue is modelled. Fix: include revenue_by_basis non-measured in `estimated`.
M6. Morning brief + recorded_spend hardcode basis "measured" (p12). tabs.py:235 (and :49 RECORDED->measured):
  modelled etsy_listing_fee + unknown-basis llm row -> `basis: measured`, "CA$1.28 (recorded)".
M7. Tax pack prints UNKNOWN fees as 0.0 (p16). tax_pack.py:114: sales UNKNOWN -> gross None but
  marketplace_fees 0.0 / listing_fees 0.0, in a file whose notes.txt says "never 0.00".
M8. Duplicate sale row not detected when external_id differs (p04). posting_rules.py:94-97 keys identity on
  (category,source,external_id) and ignores evidence_ref when external_id is set: second `sale` row for the same
  receipt (evidence_ref identical) -> gross 92.59 -> 104.59, fees 10.96 -> 12.35, 0 exceptions.
  Fix: also key (category, evidence_ref) for sales.
M9. Hash seal omits fields that drive logic (p11). ledger._canon (:88) excludes reverses_id, product_slug,
  family, release, channel, department, detail, source_period, posted_at and posting memo/currency/amount_original.
  Raw-SQL edits to all of them leave verify_chain ok=True (reverses_id feeds active_entries -> double-post/reverse
  confusion; product_slug/channel feed profitability and the check_spend margin rule). Tail deletion also undetected
  (self-heals only if the source row still exists; locked months caught by verify_lock).
M10. books.py `cash_cad` = net profit proxy (p15). books.py:152/213: all-measured P&L (gross 100, fees 10, ops 5)
  -> cash_cad 72.0 "derived_cash_proxy" (served by app/main.py:719, pipeline CFO) while ledger cash is UNKNOWN.
M11. check_spend `kind` allowlist + NaN (p06). policy.py:83,92: phase block only for kind in EXTERNAL_KINDS and
  ads caps only for kind=="ads". With bank cash and an approved OwnerAction: kind "advertising"/"etsy_ads"/"ads "
  amount 900 (> campaign cap) in SHADOW -> verdict cleared allow=True; amount NaN passes cash/caps/margin/authority
  (only the phase block stops kind=ads). Latent: only ads_readiness calls it, with kind fixed to "ads".
  Fix: normalise+validate kind against a closed set (unknown -> blocked), reject non-finite amount.
M12. Tamper not surfaced in the Money summary (p03). Balanced raw-SQL edit in a locked month: verify_chain False,
  verify_lock intact False, but dashboard.summary shows 0 exceptions and status driven only by staleness; the alarm
  waits for the next anomalies.detect cycle (<=6h). Fix: summary reads verify_chain (cheap) and BLOCKs.

## LOW
L1. duplicate_charge detector (anomalies.py DUP_WINDOW 60s, DUP_MIN_CAD 0.50): identical 3.00 llm rows 61s apart,
  no charge id -> no finding (p03); sub-50c model calls can never trigger it.
L2. spend_report.record (:419) accepts negative amounts: a -80 row drops month spend 90 -> 10 and re-grants a 20 call
  (p14). No negative producer found; NaN fails closed on SQLite (NOT NULL) but Postgres behaviour not tested.
L3. drill `check.matches` (dashboard.py:372) compares value to itself (tautology). Independent summary-vs-drill
  comparison over 5 windows x 12 metrics found 0 mismatches (p18), so numbers are traceable; the check is cosmetic.
L4. money_drill("revenue") when MEASURED returns UNKNOWN "drill-through (lane E) is not built" (tabs.py:119-141, p07);
  headline revenue (20.5, reconciled-only, all time) and ledger gross_sales (92.59, 30d) are two different
  "revenue" numbers on one tab.
L5. sustainable_economics passes with measured_orders=0 and its pass/fail flips with the ASSUMED SCENARIOS volume
  (1->False, 20/60->True, 1e6->True; p08). Labelled MODELLED, so not mislabelled, but assumed volume decides.
L6. Late adjustment to a locked month (source ledger row edited in place) books silently: locked period intact,
  current period moves +100, 0 exceptions, no owner notice (p20).
L7. No runtime caller of close.lock_period (only owner/manual); locked-period/late-adjustment code is test-only in
  production. Forecast cost low end divides by 60 days regardless of history length (accounting/forecast.py:~58).

## Checked and SOUND (evidence)
- Ledger balance/chart/idempotency: validate() refuses 5 bad shapes; 6 concurrent post_all -> 16 entries/16 keys,
  chain ok (p04). Re-run idempotent (cycle posted 0 new). ORM update/delete refused (existing tests, re-run pass).
- Raw edit of amount in a locked month detected by verify_chain AND verify_lock (p03). Locked month figures did not
  move after a source edit (p20).
- Statement duplicates: same ref/amount new id, ref case/space variants detected; suffix/amount+0.01/4-days-later
  variants surface as unmatched/fee_mismatch exceptions, never silently double counted (p10).
- Empty/disconnected DB: summary every sales figure None/UNKNOWN, cash/safe/runway UNKNOWN, forecast revenue None
  (p01). Drill unposted -> UNKNOWN. summary == drill for all metrics (p18).
- Spend ceiling: 10 threads x CA$30 vs CA$100 -> exactly 3 granted, outstanding 90 (p05); NaN/inf/neg/str/None
  estimates refused; failover is stronger-only, pre-filtered, and every provider attempt re-enters check_budget_cad.
- rc1-SPEND still holds: billed-malformed counted, usage-missing counted at estimate, timeout-after-send counted,
  reservations released with actual (p21 + test_rc1_spend 0 failing). rc1-ORD tests 0 failing.
- FX is a single constant (core/fx.py); no stray 1.37 literal remains.
- Growth ads: propose() hard_ceiling + finance_check; shadow phase + cash UNKNOWN block; NaN daily -> IntegrityError
  (fail closed); no executor; check_spend only records an opinion.
- Authority: guardrails.audit_package ok; no pay/transfer/file/borrow function or network import in accounting/**.
- Existing suites re-run green: test_v11_accounting_{ledger,money,drill,reconciliation,controller}, test_v11_ads_challenge,
  test_money_truth, test_books_basis_truth, test_rc1_spend, test_rc1_order_truth.
