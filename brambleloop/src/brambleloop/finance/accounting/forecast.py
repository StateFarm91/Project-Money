"""Forecasts as ranges with their basis, never as booked figures (F-913).

A forecast here has no single `value`: it has `low_cad` / `high_cad`, the assumptions it was
made from, the sample behind it and a confidence word. `is_booked` and `is_measured` are
always False. Revenue is forecast only from *measured* orders (sales source measured and at
least `MIN_ORDERS` orders in the lookback); otherwise there is no revenue forecast and the
reason says why -- a forecast from no data is arithmetic on a hope.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import accounts as A
from . import health as H
from .ledger import to_cad
from .models import AcctJournalEntry, AcctPosting
from .schema import ensure

MIN_ORDERS = 10
LOOKBACK_DAYS = 60


def _daily(s, accounts, since, until) -> dict[str, int]:
    q = (select(AcctJournalEntry.at, AcctPosting.account, AcctPosting.debit_micros,
                AcctPosting.credit_micros)
         .join(AcctPosting, AcctPosting.entry_id == AcctJournalEntry.id)
         .where(AcctPosting.account.in_(list(accounts)), AcctJournalEntry.at >= since,
                AcctJournalEntry.at <= until))
    out: dict[str, int] = {}
    for at, account, dr, cr in s.execute(q):
        acc = A.BY_CODE[account]
        v = (dr - cr) * (1 if acc.normal_debit else -1)
        d = at.date().isoformat()
        out[d] = out.get(d, 0) + v
    return out


def forecast(db, *, horizon_days: int = 30, now: datetime | None = None) -> dict:
    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS)
    health = H.reading(db, now=now)
    with db.session() as s:
        costs = _daily(s, A.OPERATING_ACCOUNTS, since, now)
        sales = _daily(s, (A.SALES,), since, now)
        orders = len({r for (r,) in s.execute(
            select(AcctJournalEntry.source_ref)
            .join(AcctPosting, AcctPosting.entry_id == AcctJournalEntry.id)
            .where(AcctJournalEntry.rule == "ledger_row", AcctJournalEntry.kind == "original",
                   AcctPosting.account == A.SALES, AcctJournalEntry.at >= since)) if r})
    cost_days = max(1, min(LOOKBACK_DAYS, (now - since).days))
    total_cost = sum(costs.values())
    recent = sum(v for d, v in costs.items() if d >= (now - timedelta(days=7)).date().isoformat())
    per_day = [total_cost / cost_days, recent / 7]
    cost = ({"low_cad": to_cad(min(per_day) * horizon_days),
             "high_cad": to_cad(max(per_day) * horizon_days * 1.25),
             "assumptions": [f"daily operating spend between the {LOOKBACK_DAYS}-day and "
                             "7-day averages", "high end +25% for unplanned work",
                             "the monthly model ceiling caps the true maximum"],
             "confidence": "medium" if len(costs) >= 14 else "low",
             "sample_days_with_spend": len(costs)} if total_cost else None)
    revenue = None
    revenue_why = ""
    if health["sources"]["orders"]["state"] != H.MEASURED:
        revenue_why = ("no revenue forecast: the order source is "
                       f"{health['sources']['orders']['state']}, so there are no measured "
                       "orders to project from")
    elif orders < MIN_ORDERS:
        revenue_why = (f"no revenue forecast: {orders} measured orders in {LOOKBACK_DAYS} "
                       f"days (< {MIN_ORDERS}); a range from so few sales would be a guess")
    else:
        total = sum(sales.values())
        rate = orders / LOOKBACK_DAYS
        aov = total / orders
        lo = max(0.0, rate * horizon_days - 2 * math.sqrt(rate * horizon_days))
        hi = rate * horizon_days + 2 * math.sqrt(rate * horizon_days)
        revenue = {"low_cad": to_cad(lo * aov), "high_cad": to_cad(hi * aov),
                   "assumptions": ["order arrivals continue at the trailing rate "
                                   "(Poisson, +/-2 sd)", "average order value unchanged",
                                   "no promotion, seasonality or ranking change"],
                   "confidence": "low" if orders < 30 else "medium",
                   "sample_orders": orders}
    return {"as_of": now.isoformat(), "horizon_days": horizon_days, "currency": "CAD",
            "is_booked": False, "is_measured": False, "basis": "modelled",
            "presentation": "range only; never a point estimate presented as fact",
            "operating_cost": cost, "revenue": revenue, "revenue_why": revenue_why}
