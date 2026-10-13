"""What the Accountant has done and found, in one owner-facing reading (F-682 Accountant
Activity).

Criterion: show last reconciliation, discrepancies, close status, tax/threshold alerts and
evidence; never silently force mismatches to zero.

* **last reconciliation** -- the latest `finance.accounting.cycle` run (controller.run_cycle
  persists one `OperatingReading` per day): when, and its matching report. Never run is
  ``None`` with that said, not a reconciliation dated today.
* **discrepancies** -- every OPEN accounting exception (unmatched statement lines, fee and
  refund mismatches with booked vs statement amounts) plus every open
  ``finance.reconciliation.*`` incident (Etsy fees against no internal order, unclassified
  or anomalous ledger entries). Nothing here resolves, nets or zeroes one: the reading only
  lists, and a mismatch keeps both sides of its figures.
* **close status** -- `close.status` (locked periods, whether last month is locked).
* **tax/threshold alerts** -- the GST/HST small-supplier threshold (CA$30,000 of taxable
  supplies over four consecutive calendar quarters; the figure is the accountant's to
  confirm, as `tax_pack.QUESTIONS` says) and Etsy's Offsite Ads 365-day sales threshold
  (read from the policy reading, `commerce.paid_media.offsite_ads_terms`). Each alert says
  whether it is approaching (>= 80 %) or crossed, and from which rows.
* **evidence** -- the modules and tables each figure came from.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SMALL_SUPPLIER_CAD = 30000.0
APPROACHING = 0.8


def _quarters_back(now: datetime) -> datetime:
    """Start of the calendar quarter three quarters before the current one (4 quarters)."""
    q0 = (now.month - 1) // 3
    y, q = now.year, q0 - 3
    while q < 0:
        q += 4
        y -= 1
    return datetime(y, 3 * q + 1, 1, tzinfo=timezone.utc)


def _alert(name: str, value: float | None, threshold: float, unit: str, why: str,
           source: str) -> dict:
    if value is None:
        return {"alert": name, "level": "UNKNOWN", "value": None, "threshold": threshold,
                "unit": unit, "why": why, "source": source}
    share = value / threshold if threshold else None
    level = ("crossed" if share is not None and share >= 1 else
             "approaching" if share is not None and share >= APPROACHING else "clear")
    return {"alert": name, "level": level, "value": round(value, 2), "threshold": threshold,
            "share": round(share, 4) if share is not None else None, "unit": unit,
            "why": why, "source": source}


def activity(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ...commerce import orders_ingest
    from ...core.models import Incident, OperatingReading, Order
    from . import close as close_mod
    from . import exceptions as X
    from .controller import CYCLE_KIND
    from .schema import ensure

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == CYCLE_KIND)
                       .order_by(OperatingReading.at.desc()).limit(1))
        last = ({"at": row.at.isoformat() if row.at else None,
                 "matching": (row.payload or {}).get("matching"),
                 "anomalies": (row.payload or {}).get("anomalies"),
                 "close": (row.payload or {}).get("close")} if row is not None else None)
        incidents = [{"signature": i.signature, "severity": i.severity, "summary": i.summary,
                      "detail": i.detail, "at": i.at.isoformat() if i.at else None}
                     for i in s.scalars(select(Incident).where(
                         Incident.resolved == False,  # noqa: E712
                         Incident.signature.like("finance.reconciliation%")))]
        held = orders_ingest.held_refs(s)
        since4q = _quarters_back(now)
        orders = [o for o in orders_ingest.countable_orders(s, select(Order)) if o.at]
        def _aware(t):
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        supplies = sum(float(o.revenue_cad or 0.0) for o in orders
                       if _aware(o.at) >= since4q)
        trailing365 = sum(float(o.revenue_cad or 0.0) for o in orders
                          if _aware(o.at) >= now - timedelta(days=365))
        held_count = len(held)
    exceptions = X.listing(db, open_only=True)
    try:
        close_status = close_mod.status(db, now=now)
    except Exception as exc:  # noqa: BLE001
        close_status = {"reading": "UNKNOWN", "why": type(exc).__name__}
    unknown_part = (f"; {held_count} held sale(s) have UNKNOWN value and are not in the sum"
                    if held_count else "")
    alerts = [_alert("gst_hst_small_supplier", supplies, SMALL_SUPPLIER_CAD, "CAD",
                     "taxable supplies over the last four calendar quarters (countable "
                     "orders' revenue) against the small-supplier threshold; the threshold "
                     "and what counts are the accountant's to confirm" + unknown_part,
                     "orders (orders_ingest.countable) since " + since4q.date().isoformat())]
    try:
        from ...commerce import paid_media
        from ...scale.target import USD_PER_CAD

        terms = paid_media.offsite_ads_terms()
        alerts.append(_alert("etsy_offsite_ads_365d", trailing365 * USD_PER_CAD,
                             float(terms["threshold_usd"]), "USD",
                             "trailing 365-day sales against Etsy's Offsite Ads threshold; at "
                             "or above it participation is mandatory and the reduced fee "
                             "applies" + unknown_part,
                             "orders (365 days) + gates.policy_knowledge advertising_rules"))
    except Exception as exc:  # noqa: BLE001
        alerts.append({"alert": "etsy_offsite_ads_365d", "level": "UNKNOWN",
                       "why": type(exc).__name__})
    discrepancies = {"open": len(exceptions) + len(incidents),
                     "accounting_exceptions": exceptions, "reconciliation_incidents": incidents,
                     "note": ("listed as found; never netted, resolved or set to zero by this "
                              "reading -- a mismatch keeps its booked and statement figures")}
    return {
        "as_of": now.isoformat(),
        "last_reconciliation": last if last else {
            "reading": "NEVER_RUN",
            "why": "no finance.accounting.cycle has run on this database"},
        "discrepancies": discrepancies,
        "close": close_status,
        "tax_threshold_alerts": alerts,
        "evidence": {
            "last_reconciliation": "operating_readings kind finance.accounting.cycle "
                                   "(finance.accounting.controller.run_cycle)",
            "discrepancies": "acct_exceptions (open) + incidents finance.reconciliation.*",
            "close": "acct_period_locks (finance.accounting.close.status)",
            "alerts": "orders + gates.policy_knowledge",
        },
    }
