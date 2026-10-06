"""Trial balance, accrual view and cash view (F-903, F-905).

Two bases, never blended:

* **Accrual** (management view): revenue when the sale is paid on Etsy, fees and refunds
  when charged, expenses when incurred -- including modelled listing-fee exposure, labelled.
  Read from every income-statement account in the journal.
* **Cash**: money that moved through a bank account this company can see -- account 1000
  only. With no bank statement imported, every cash figure is UNKNOWN (None), not zero.

Every result carries `basis_of_accounting`, and the two functions return disjoint key sets
for their money figures (`accrual_*` vs `cash_*`), so one basis cannot be passed off as the
other by a reader that picks a key. Revenue-derived figures are `None` when the order source
is disconnected and nothing is recorded (F-902); with rows recorded they are a labelled lower
bound.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from . import accounts as A
from . import health as H
from .ledger import balances, to_cad, verify_chain
from .models import AcctJournalEntry
from .schema import ensure

# The books' reserve rate (finance.books.TAX_RESERVE_RATE): a management reserve against
# net sales, not a booked liability. Imported so the two can never disagree.
from ..books import TAX_RESERVE_RATE


def _bal(b: dict, code: str) -> int:
    return int((b.get(code) or {}).get("balance", 0))


def _by_basis(b: dict, codes) -> dict:
    out: dict[str, int] = {}
    for c in codes:
        for k, v in ((b.get(c) or {}).get("by_basis") or {}).items():
            out[k] = out.get(k, 0) + int(v)
    return {k: to_cad(v, 4) for k, v in out.items() if v}


def _held(db, period, since, until) -> list[dict]:
    from ...commerce import orders_ingest

    if period:
        y, m = (int(x) for x in period.split("-"))
        since = datetime(y, m, 1, tzinfo=timezone.utc)
        until = datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
    try:
        return orders_ingest.held(db, since=since, until=until)
    except Exception:  # noqa: BLE001
        return []


def trial_balance(db, *, period: str | None = None, upto_period: str | None = None,
                  since: datetime | None = None, until: datetime | None = None) -> dict:
    db = ensure(db)
    with db.session() as s:
        b = balances(s, period=period, upto_period=upto_period, since=since, until=until)
        n = s.query(AcctJournalEntry).count()
    rows = []
    dr_total = cr_total = 0
    for acc in A.CHART:
        a = b.get(acc.code)
        if not a:
            continue
        net = a["debit"] - a["credit"]
        dr, cr = (net, 0) if net >= 0 else (0, -net)
        dr_total += dr
        cr_total += cr
        rows.append({"account": acc.code, "name": acc.name, "type": acc.type,
                     "debit_cad": to_cad(dr, 4), "credit_cad": to_cad(cr, 4),
                     "by_basis_cad": {k: to_cad(v, 4) for k, v in a["by_basis"].items() if v}})
    chain = verify_chain(db)
    return {"period": period, "upto_period": upto_period,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "rows": rows, "total_debit_cad": to_cad(dr_total, 4),
            "total_credit_cad": to_cad(cr_total, 4),
            "balanced": dr_total == cr_total, "entries_in_journal": n,
            "chain_ok": chain["ok"], "chain_head": chain["head"],
            "currency": "CAD"}


def accrual(db, *, period: str | None = None, since: datetime | None = None,
            until: datetime | None = None, health: dict | None = None) -> dict:
    """The management (accrual) income statement for a period or a date window."""
    db = ensure(db)
    health = health or H.reading(db)
    with db.session() as s:
        b = balances(s, period=period, since=since, until=until)
    gross, refunds, discounts = _bal(b, A.SALES), _bal(b, A.REFUNDS), _bal(b, A.DISCOUNTS)
    fees = _bal(b, A.MARKETPLACE_FEES)
    op = {c: _bal(b, c) for c in A.OPERATING_ACCOUNTS}
    operating = sum(op.values())
    net_sales = gross - refunds - discounts
    reserve = int(round(max(0, net_sales) * TAX_RESERVE_RATE))
    contribution = net_sales - fees - op.get(A.ADS, 0)
    profit_before_reserve = net_sales - fees - operating
    net_profit = profit_before_reserve - reserve
    src = health["sources"]["orders"]["state"]
    has_sales = bool(gross or refunds)
    sales_reading = H.figure_reading(src, has_sales)
    held = _held(db, period, since, until)
    sales_why = health["sources"]["orders"]["why"]
    if held and sales_reading == "measured":
        sales_reading = "lower_bound"
        sales_why = (f"{len(held)} sale line(s) held by the order ingest with UNKNOWN CAD "
                     f"value ({', '.join(h['ref'] for h in held[:5])}); figures are a "
                     f"lower bound")
    known = sales_reading != "UNKNOWN"

    def sales_fig(v: int) -> float | None:
        return to_cad(v) if known else None

    revenue_basis = _by_basis(b, (A.SALES,))
    fee_basis = _by_basis(b, (A.MARKETPLACE_FEES,))
    op_basis = _by_basis(b, A.OPERATING_ACCOUNTS)
    estimated = {k: v for k, v in {**fee_basis}.items() if k != "measured"}
    op_est = {k: v for k, v in op_basis.items() if k != "measured"}
    return {
        "basis_of_accounting": "accrual",
        "period": period, "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None, "currency": "CAD",
        "sales_reading": sales_reading,
        "sales_why": sales_why,
        "held_orders": [h["ref"] for h in held],
        "accrual_gross_sales_cad": sales_fig(gross),
        "accrual_refunds_cad": sales_fig(refunds),
        "accrual_discounts_cad": sales_fig(discounts),
        "accrual_net_sales_cad": sales_fig(net_sales),
        "accrual_platform_fees_cad": sales_fig(fees),
        "accrual_operating_costs_cad": to_cad(operating, 4),
        "accrual_operating_by_account_cad": {A.BY_CODE[c].name: to_cad(v, 4)
                                             for c, v in op.items() if v},
        "accrual_contribution_cad": sales_fig(contribution),
        "accrual_profit_before_tax_reserve_cad": sales_fig(profit_before_reserve),
        "accrual_tax_reserve_cad": sales_fig(reserve),
        "accrual_net_profit_cad": sales_fig(net_profit),
        "revenue_by_basis_cad": revenue_basis,
        "fees_by_basis_cad": fee_basis,
        "operating_by_basis_cad": op_basis,
        "estimated_components": {"fees": estimated, "operating": op_est},
        "all_measured": (sales_reading == "measured" and not estimated and not op_est
                         and set(revenue_basis) <= {"measured"}),
        "tax_reserve_rate": TAX_RESERVE_RATE,
        "tax_reserve_note": ("a management reserve against net sales (finance.books rate); "
                             "not a booked liability -- the GST/HST treatment is for the "
                             "human accountant (tax_pack)"),
        "_micros": {"gross": gross, "refunds": refunds, "discounts": discounts, "fees": fees,
                    "operating": operating, "net_sales": net_sales, "reserve": reserve,
                    "contribution": contribution, "net_profit": net_profit},
    }


def cash(db, *, period: str | None = None, since: datetime | None = None,
         until: datetime | None = None, health: dict | None = None) -> dict:
    """The cash-basis view: only bank account movements. UNKNOWN without a bank source."""
    db = ensure(db)
    health = health or H.reading(db)
    bank = health["sources"]["bank"]
    with db.session() as s:
        b = balances(s, period=period, since=since, until=until)
        upto = balances(s)
    known = bank["state"] in (H.MEASURED, H.STALE)
    acct = b.get(A.BANK) or {"debit": 0, "credit": 0}
    return {
        "basis_of_accounting": "cash",
        "period": period, "currency": "CAD",
        "cash_reading": (bank["state"] if known else "UNKNOWN"),
        "cash_why": bank["why"],
        "cash_receipts_cad": to_cad(acct["debit"]) if known else None,
        "cash_disbursements_cad": to_cad(acct["credit"]) if known else None,
        "cash_net_movement_cad": to_cad(acct["debit"] - acct["credit"]) if known else None,
        "cash_bank_balance_cad": to_cad(_bal(upto, A.BANK)) if known else None,
        "note": ("Cash basis counts only money seen moving through a bank account. Etsy's "
                 "payment-account balance is a receivable (expected payout), shown in "
                 "`cash.position`, never as cash."),
    }
