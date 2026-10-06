"""Contribution and profit by order, product, release, family, channel and period (F-906).

Read from the journal, so a figure here sums the same postings as the trial balance --
reversals included, which is how a corrected sale nets to its corrected amount.

* `contribution` = revenue - refunds - discounts - marketplace fees.
* `profit`       = contribution - costs attributed to the same key (ads, model/API, image,
  testing ... posted with that product/channel). Costs with no key are not spread: they sit
  in an explicit `unattributed` row, so the rows always sum to the company total.
* Every row carries `basis`: `actual` only when every contributing line is `measured`;
  otherwise `estimated`, with the modelled/unknown amounts listed (`estimated_cad`).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from . import accounts as A
from .ledger import to_cad
from .models import AcctJournalEntry, AcctPosting
from .schema import ensure

DIMENSIONS = ("order", "product", "release", "family", "channel", "period")
UNATTRIBUTED = "unattributed"


def _rows(s, *, period=None, since=None, until=None):
    q = (select(AcctJournalEntry.id, AcctJournalEntry.period, AcctJournalEntry.product_slug,
                AcctJournalEntry.release, AcctJournalEntry.family, AcctJournalEntry.channel,
                AcctJournalEntry.source_ref, AcctJournalEntry.rule, AcctJournalEntry.kind,
                AcctPosting.account, AcctPosting.debit_micros, AcctPosting.credit_micros,
                AcctPosting.basis)
         .join(AcctPosting, AcctPosting.entry_id == AcctJournalEntry.id))
    if period:
        q = q.where(AcctJournalEntry.period == period)
    if since is not None:
        q = q.where(AcctJournalEntry.at >= since)
    if until is not None:
        q = q.where(AcctJournalEntry.at <= until)
    return list(s.execute(q))


def _key(dim: str, r) -> str:
    v = {"order": r.source_ref if r.rule == "ledger_row" else "",
         "product": r.product_slug, "release": r.release, "family": r.family,
         "channel": r.channel, "period": r.period}[dim]
    return v or UNATTRIBUTED


def by(db, dimension: str, *, period: str | None = None, since: datetime | None = None,
       until: datetime | None = None) -> dict:
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension must be one of {DIMENSIONS}")
    db = ensure(db)
    with db.session() as s:
        rows = _rows(s, period=period, since=since, until=until)
    groups: dict[str, dict] = {}
    for r in rows:
        acc = A.BY_CODE[r.account]
        if acc.statement != "income_statement":
            continue
        g = groups.setdefault(_key(dimension, r), {
            "revenue": 0, "refunds": 0, "discounts": 0, "fees": 0, "attributed_costs": 0,
            "estimated": 0, "sale_refs": set(), "by_account": {}})
        signed = (r.debit_micros - r.credit_micros) * (1 if acc.normal_debit else -1)
        if r.account == A.SALES:
            g["revenue"] += signed
            if r.kind == "original" and r.source_ref:
                g["sale_refs"].add(r.source_ref)
        elif r.account == A.REFUNDS:
            g["refunds"] += signed
        elif r.account == A.DISCOUNTS:
            g["discounts"] += signed
        elif r.account == A.MARKETPLACE_FEES:
            g["fees"] += signed
        else:
            g["attributed_costs"] += signed
        g["by_account"][r.account] = g["by_account"].get(r.account, 0) + signed
        if r.basis != "measured":
            g["estimated"] += abs(signed)
    out_rows = []
    totals = {"revenue": 0, "contribution": 0, "profit": 0}
    for key, g in sorted(groups.items()):
        contribution = g["revenue"] - g["refunds"] - g["discounts"] - g["fees"]
        profit = contribution - g["attributed_costs"]
        totals["revenue"] += g["revenue"]
        totals["contribution"] += contribution
        totals["profit"] += profit
        out_rows.append({
            dimension: key,
            "revenue_cad": to_cad(g["revenue"], 4), "refunds_cad": to_cad(g["refunds"], 4),
            "discounts_cad": to_cad(g["discounts"], 4), "fees_cad": to_cad(g["fees"], 4),
            "attributed_costs_cad": to_cad(g["attributed_costs"], 4),
            "contribution_cad": to_cad(contribution, 4), "profit_cad": to_cad(profit, 4),
            "contribution_margin": (round(contribution / g["revenue"], 4)
                                    if g["revenue"] > 0 else None),
            "orders_referenced": len(g["sale_refs"]),
            "basis": "actual" if not g["estimated"] else "estimated",
            "estimated_cad": to_cad(g["estimated"], 4),
            "by_account_cad": {A.BY_CODE[c].name: to_cad(v, 4)
                               for c, v in sorted(g["by_account"].items()) if v},
        })
    return {"dimension": dimension, "period": period, "rows": out_rows,
            "total_revenue_cad": to_cad(totals["revenue"], 4),
            "total_contribution_cad": to_cad(totals["contribution"], 4),
            "total_profit_cad": to_cad(totals["profit"], 4),
            "note": ("rows sum to the journal total; costs without this key are in the "
                     "`unattributed` row and are not spread across products. `estimated` "
                     "means at least one contributing amount is modelled or of unknown basis.")}
