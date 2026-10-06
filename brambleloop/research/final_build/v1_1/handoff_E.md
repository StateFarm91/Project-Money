# v1.1 lane E: controller-grade Accountant (F-901..F-917): handoff

Branch `claude/v11-E`, based on `claude/visual-investigation` @ 0694fb7. Shadow only: no network, no
spend, no money movement. Everything below was run on throwaway SQLite databases with synthetic
rows that went through the real writers (`orders_ingest.ingest` with a fake reader,
`reconcile.apply`, `spend_report.record`, `reservations.reserve`).

## Requirements

| ID | Status | Where / evidence |
|---|---|---|
| F-901 Accountant agent | COMPLETE (code + job handler). GATED on wiring | `accounting/controller.py` `run_cycle` (post, match, post, anomalies, close check), `PERSONA`; `job.py` registers `finance.accounting.cycle`. It does not run on a cadence until the WIRING REQUEST is applied. |
| F-902 source of truth; UNKNOWN is not $0.00 | COMPLETE | `posting_rules.py` posts from `ledger`, `cost_entries` and matched bank lines. `health.py` reports each source as measured, stale, never_read or disconnected. Revenue figures are `None`/UNKNOWN when the source is disconnected and empty, and a labelled `lower_bound` when rows exist or orders are held. Test: `test_disconnecting_the_order_source_turns_money_unknown_not_zero` (§95). |
| F-903 double-entry ledger | COMPLETE | `ledger.py` + `models.py`. Amounts are integer micro-CAD, so debits equal credits exactly. Chart of accounts in `accounts.py`. Records are append-only: the ORM refuses update and delete, and a SHA-256 hash chain detects raw-SQL edits. A correction is a reversal plus a new version. Locked periods never move, and a late change is booked in the next open period. |
| F-904 reconciliation | COMPLETE (statement import); live feeds GATED | `reconciliation.py`: `import_statement` is idempotent on replay and flags duplicates (same source, kind, ref and amount within 3 days under a new id). `match` pairs payouts with bank deposits, bank charges with cost charge ids, and Etsy fee/refund/payment lines with orders. Unmatched lines, `fee_mismatch` and `refund_mismatch` become exceptions. §95 test `test_injected_duplicate_fee_payment_and_refund_are_detected_and_not_double_counted`. No bank or Etsy-ledger feed exists (owner action / `transactions_r`). |
| F-905 accrual vs cash | COMPLETE | `views.accrual` uses `accrual_*` keys and `views.cash` uses `cash_*` keys, which do not overlap. Cash is UNKNOWN without a bank source. |
| F-906 profitability | COMPLETE | `profitability.by(db, order\|product\|release\|family\|channel\|period)`. Rows sum to the total, `unattributed` is shown explicitly, and each row's basis is actual or estimated. |
| F-907 cost attribution | COMPLETE | `attribution.report`: by product, release, department, agent, provider, model, category and purpose, with the unattributed share. |
| F-908 cash & runway | COMPLETE; cash GATED (no bank) | `cash.position`: expected payout (receivable), obligations, committed reservations, declared bills, sales-tax reserve, income-tax set-aside, safe discretionary budget, runway range. All cash-dependent figures are UNKNOWN in shadow. |
| F-909 tax pack | COMPLETE (preparation only) | `tax_pack.pack(db, "2026-10"\|"2026-Q4"\|"2026")`: CAD, Canada, by original currency, source-linked rows, 7 questions for the accountant. `collected_cad` is None (not assumed). No filing path exists. |
| F-910 month-end close | COMPLETE | `close.checklist` (12 steps: block or warn), `lock_period`, `verify_lock`, `status`. |
| F-911 anomalies | COMPLETE | `anomalies.detect`: duplicate charge, unexpected fee rate, missing deposit, refund anomaly, spend spike (reuses `governor.anomaly`), margin deterioration, reconciliation drift (books disagreement, broken chain, bank balance snapshot). Findings become exceptions with evidence. |
| F-912 spend governor | COMPLETE (Finance side) | `policy.check_spend(db, proposal) -> {allow, reasons, challenge_id, verdict, escalate_to, checks}`. A durable `acct_challenges` row is written per call. Without a verified owner-action authority the best verdict is `escalated` (allow=False). §95 test `test_growth_spend_violating_margin_and_cash_policy_is_blocked_by_finance`. |
| F-913 forecast honesty | COMPLETE | `forecast.forecast` returns low/high ranges with assumptions, sample size and confidence, `is_booked=False`, and no point value. There is no revenue forecast without at least 10 measured orders. |
| F-914 money dashboard data | COMPLETE (provider) | `dashboard.summary(db, window=...)` follows the brief's contract and accepts a `Database` or a bare `Session`. |
| F-915 drill-through | COMPLETE | `dashboard.drill(db, metric)` returns every journal line, the loaded source row (order, cost entry, ledger row, statement line), reversal chains, and a sum check. §95 test `test_displayed_profit_traces_to_orders_fees_spend_and_corrections`. |
| F-916 accountant handoff | COMPLETE | `handoff.export(db, dir, spec)` writes CSV, JSON and TXT plus `manifest.json` (sha256 per file) and `notes.txt` explaining the bases. |
| F-917 guardrails | COMPLETE | `guardrails.audit_package()` statically checks that no module defines money-moving, filing, signing or banking names and none imports a network or payment client. `refuse()` exists and is tested. |
| Safe discretionary budget / tax reserve | COMPLETE (UNKNOWN in shadow) | `cash.position`. |

## Provider contracts

- `brambleloop.finance.accounting.dashboard.summary(db, *, window="30d", now=None, refresh=True)`. Contains `status`, `as_of`, `basis`, `items`, `sources`, plus `reason`, `source_health`, `tax_reserve`, `payout_status`, `runway`, `obligations`, `exceptions`, `close` and `forecast`. Each item has `metric`, `label`, `value_cad` (None means UNKNOWN), `reading`, `actual_cad`, `estimated_cad`, `drill` and `why`. `refresh=True` runs the idempotent posting first, which writes journal rows; pass `refresh=False` for a pure read.
- `brambleloop.finance.accounting.dashboard.drill(db, metric, *, window="30d")`. Valid metrics: gross_sales, refunds, discounts, net_sales, fees, operating_spend, contribution, profit, tax_reserve, cash, expected_payout, owner_payable.
- `brambleloop.finance.accounting.dashboard.next_work(db) -> list[dict]`. Each item has `id`, `department`="finance", `kind` (run_cycle, post_rows, reconcile, investigate, close_month or connect_source), `title`, `priority` (1 is high), `ready`, `blocked_by`, `handler` ("module:function") and `evidence`. The list is sorted by priority, with ready items first.
- `brambleloop.finance.accounting.policy.check_spend(db, proposal)` (for lane H). The proposal keys are documented in the module docstring.

## Books agreement (F-902)

`reconciliation.compare_with_books` runs `Books.profit_and_loss` and the journal over the same window.
On the realistic shadow dataset they agree on gross sales, refunds, fees, net sales, operating costs
and tax reserve (`E_books_agreement.json`, test `test_ledger_agrees_with_the_books_on_a_realistic_shadow_dataset`).

**When they disagree, the ledger wins. `books.py` has been flagged, not re-pointed.** I changed only
its docstring, and its tests pass. The known differences are:

1. A duplicate `ledger` row for the same external object is summed by the books but refused by the ledger.
2. **Books bug (latent):** a `discount` row is subtracted from net sales *and* counted again in
   operating costs. No writer emits discount rows today.
3. A sale whose order is `unreconciled` but not held is summed by the books but excluded by the ledger.

The ledger also labels USD sales converted at an assumed FX rate as `modelled`, while the books call
them measured. This changes the label only; the amounts are the same.

Re-pointing `Books.profit_and_loss` at the journal is a follow-up for the integrator. It touches many
readers.

## Files

All new files are under `brambleloop/src/brambleloop/finance/accounting/`: `__init__`, `schema`,
`models`, `accounts`, `ledger`, `posting_rules`, `exceptions`, `health`, `reconciliation`, `views`,
`profitability`, `attribution`, `cash`, `forecast`, `tax_pack`, `close`, `anomalies`, `policy`,
`handoff`, `dashboard`, `controller`, `guardrails`, `job` and `shadow_dataset`.

The only change to an existing file is the docstring of `finance/books.py`.

Tests: `tests/test_v11_accounting_{ledger,reconciliation,money,drill,controller}.py`.

Evidence: `research/final_build/v1_1/evidence/E_*.json`.

## Tests run (python3; the repo `.venv` lacks sqlalchemy)

```
cd brambleloop
PYTHONPATH=src python3 tests/test_v11_accounting_ledger.py          # 10 passed
PYTHONPATH=src python3 tests/test_v11_accounting_reconciliation.py  # 7 passed
PYTHONPATH=src python3 tests/test_v11_accounting_money.py           # 9 passed
PYTHONPATH=src python3 tests/test_v11_accounting_drill.py           # 4 passed
PYTHONPATH=src python3 tests/test_v11_accounting_controller.py      # 9 passed
```

Existing tests:
- `test_finance` passes (21 OK).
- `test_books_basis_truth` passes (2).
- `test_spend_policy` passes (24 OK).
- `test_money_truth` has 17 OK and 1 FAIL from `ModuleNotFoundError: numpy` in this interpreter. This is environmental and unrelated.
- `test_vacuity` and `test_secret_scan` each have one FAIL in files this lane did not touch (`test_launch0_listing_truth.py`, `test_pattern_truth.py`, `test_web_security.py`, `test_rc1_ord2.py:169`). None of this lane's files are listed.

## Runtime proof

`PYTHONPATH=src python3 -m brambleloop.finance.accounting.shadow_dataset research/final_build/v1_1/evidence`
seeds 7 receipts across 2 months (CAD and USD, partial and full refund, a 2-line bundle), 4 Etsy
ledger fee entries, 7 cost rows, 1 listing-fee exposure and 1 live reservation. It then runs the cycle.

Observed results:
- Trial balance: 16 entries, balanced, chain OK (`E_trial_balance.json`).
- Books agreement: agree=true (`E_books_agreement.json`).
- Profit drill: value 56.34, and the rows sum to 56.3448 (`E_drill_profit.json`).
- Duplicate injection: 3 duplicate statement lines flagged, accrual totals unchanged (`E_duplicate_injection.json`).
- Growth ads proposal: blocked by the phase, cash, margin and caps checks (`E_spend_challenge.json`).
- Summary: status DEGRADED, basis estimated, cash UNKNOWN (`E_summary.json`).

## WIRING REQUESTS (integrator)

1. **`core/db.py` `Database.create_all`**: add
   `from ..finance.accounting import models as accounting_models  # noqa: F401; v1.1 accounting tables`
   next to the `learn_models` import. Until then, `accounting.schema.ensure` creates the 6 `acct_*`
   tables lazily on first use.
2. **`runtime/pipeline.py`**: add
   `from ..finance.accounting import job as accounting_job  # noqa: E402,F401  (v1.1 F-901 Accountant cycle)`
   next to the `from . import orders` line.
3. **`runtime/worker.py` CADENCES**: add
   `("accounting_cycle", "cfo", "finance.accounting.cycle", 6 * 60 * 60),`
   after the `orders_ingest` entry.
4. **`agents/registry.py`** (cfo agent `allowed_job_types`): add `"finance.accounting.cycle"`.
5. Lane C: call `dashboard.summary(db)` and `dashboard.drill(db, metric)`.
   Lane A: call `dashboard.next_work(db)`.
   Lane H: call `policy.check_spend(db, proposal)` and treat `allow=False` as final for the spender.

## Open defects / not verified

- No real bank, Etsy payment-account ledger or processor feed was exercised. Etsy ledger line shapes
  reuse `finance.reconcile.normalise`, whose type and unit mapping is itself UNVERIFIED (see that module).
- `check_spend` reaches the `cleared` verdict only outside shadow. That path is tested by
  monkeypatching `core.phase.effective`, not through a real recorded phase transition.
- `summary(refresh=True)` writes journal rows during a read. It is idempotent, but lane C may prefer
  `refresh=False` and rely on the cycle job once it is wired.
- Postgres was not exercised. It uses an advisory lock (`pg_advisory_xact_lock(734543611)`) and
  BigInteger micro amounts. Behaviour was verified on SQLite only.
- Anomalies live in `acct_exceptions` and do not open `incidents` rows or owner notifications. Routing
  them to the notification policy is a follow-up.
- The GST/HST small-supplier threshold (CA$30,000) is stated as a question for the accountant, not as
  a rule this code applies.
