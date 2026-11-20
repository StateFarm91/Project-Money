"""Cost attribution: where the money went and what it was for (F-907).

Read from the journal's expense postings, which come from `cost_entries` (provider, model,
agent, department, product, purpose -- the columns `finance.spend_report.record` fills) and
from the Etsy ledger (marketplace and listing fees). Spend with no product is not spread
across products: it is reported as `unattributed`, and its share is a first-class number.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from . import accounts as A
from .ledger import to_cad
from .models import AcctJournalEntry, AcctPosting
from .schema import ensure

CATEGORY = {
    A.MARKETPLACE_FEES: "marketplace_fees", A.LISTING_FEES: "marketplace_fees",
    A.ADS: "ads", A.AI_API: "model_api", A.IMAGE: "image_render",
    A.INFRA: "software_infra", A.TESTING: "contractor_physical_test",
    A.BENCHMARK: "benchmark_purchases", A.OTHER_EXPENSE: "other",
    A.REFUNDS: "refunds", A.DISCOUNTS: "discounts",
}
DIMENSIONS = ("product", "release", "department", "agent", "provider", "model", "category",
              "purpose")


def report(db, *, period: str | None = None, since: datetime | None = None,
           until: datetime | None = None) -> dict:
    db = ensure(db)
    q = (select(AcctJournalEntry, AcctPosting)
         .join(AcctPosting, AcctPosting.entry_id == AcctJournalEntry.id)
         .where(AcctPosting.account.in_(list(CATEGORY))))
    if period:
        q = q.where(AcctJournalEntry.period == period)
    if since is not None:
        q = q.where(AcctJournalEntry.at >= since)
    if until is not None:
        q = q.where(AcctJournalEntry.at <= until)
    out = {d: {} for d in DIMENSIONS}
    by_basis: dict[str, int] = {}
    total = unattributed = 0
    with db.session() as s:
        for e, p in s.execute(q):
            amt = p.debit_micros - p.credit_micros
            d = e.detail or {}
            keys = {"product": e.product_slug or "unattributed",
                    "release": e.release or "unattributed",
                    "department": e.department or "unattributed",
                    "agent": d.get("agent") or ("etsy" if e.rule == "ledger_row" else "unattributed"),
                    "provider": d.get("provider") or ("etsy" if e.rule == "ledger_row"
                                                      else "unattributed"),
                    "model": d.get("model") or "n/a",
                    "category": CATEGORY[p.account],
                    "purpose": d.get("purpose") or ("sale" if e.rule == "ledger_row"
                                                    else "unstated")}
            for dim, k in keys.items():
                out[dim][k] = out[dim].get(k, 0) + amt
            by_basis[p.basis] = by_basis.get(p.basis, 0) + amt
            total += amt
            if not e.product_slug:
                unattributed += amt
    return {
        "period": period, "currency": "CAD",
        "total_cad": to_cad(total, 4),
        "by": {dim: {k: to_cad(v, 4) for k, v in sorted(m.items(), key=lambda kv: -kv[1])}
               for dim, m in out.items()},
        "by_basis_cad": {k: to_cad(v, 4) for k, v in by_basis.items() if v},
        "unattributed_cad": to_cad(unattributed, 4),
        "unattributed_share": round(unattributed / total, 4) if total else None,
        "note": ("Costs and contra-revenue (refunds, discounts) by product, release, "
                 "department, agent, provider, model and category. Spend without a product "
                 "is `unattributed` and is never spread across products by this report."),
    }
