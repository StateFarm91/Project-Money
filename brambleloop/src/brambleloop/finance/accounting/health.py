"""Accounting source health (F-902, section 95: "disconnect an accounting source").

A figure is only as good as the source it came from. Each source family has a state:

* `measured`     -- connected and read recently enough to report from;
* `stale`        -- connected once, but the last read is older than its freshness bound;
* `never_read`   -- connected, but no completed read is recorded (zero would be unobserved);
* `disconnected` -- not connected. Figures that depend on it are UNKNOWN, never CA$0.00.

`orders` is read from `commerce.orders_ingest.source_state` (the same reading the books
use). `etsy_ledger` (charged fees, payouts) needs the same grant plus the owner's sealed
mapping verification (`finance.reconcile`). `bank` is the bank statement import; none is
connected in shadow. `spend` is this company's own cost ledger, written by every billable
call, so its availability is measured (each row's *basis* is reported separately).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .models import AcctStatementLine
from .schema import ensure

FRESHNESS = {"orders": timedelta(hours=24), "etsy_ledger": timedelta(hours=48),
             "bank": timedelta(days=7)}
MEASURED, STALE, NEVER_READ, DISCONNECTED = "measured", "stale", "never_read", "disconnected"


def _aware(at):
    if at is None:
        return None
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _last_import(s, source: str):
    return _aware(s.scalar(select(func.max(AcctStatementLine.imported_at)).where(
        AcctStatementLine.source == source)))


def reading(db, *, now: datetime | None = None) -> dict:
    from ...commerce import orders_ingest
    from .. import reconcile

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    out: dict[str, dict] = {}
    try:
        st = orders_ingest.source_state(db)
    except Exception as exc:  # noqa: BLE001 - an unreadable source is not a measured one
        st = {"open": False, "last_read_at": None, "measured": False,
              "why": f"order source unreadable: {type(exc).__name__}", "owner_action": ""}
    last = _aware(st.get("last_read_at"))
    if not st.get("open"):
        state, why = DISCONNECTED, st.get("why", "")
    elif last is None:
        state, why = NEVER_READ, st.get("why", "")
    elif now - last > FRESHNESS["orders"]:
        state, why = STALE, (f"last completed receipt read {last.isoformat()} is older than "
                             f"{FRESHNESS['orders']}; figures are as of then")
    else:
        state, why = MEASURED, ""
    out["orders"] = {"state": state, "last_read_at": last.isoformat() if last else None,
                     "why": why, "owner_action": st.get("owner_action", "")}

    try:
        verified = reconcile.mapping_state(db, record_incident=False)["verified"]
    except Exception:  # noqa: BLE001
        verified = False
    with db.session() as s:
        etsy_last = _last_import(s, "etsy_ledger")
        bank_last = _last_import(s, "bank")
    if not st.get("open"):
        e_state, e_why = DISCONNECTED, ("Etsy payment-account ledger needs the same "
                                        "transactions_r grant as the order source")
    elif not verified:
        e_state, e_why = NEVER_READ, ("ledger fee mapping is not owner-verified, so charged "
                                      "fees are at best `unverified`, not measured")
    elif etsy_last is None:
        e_state, e_why = NEVER_READ, "no Etsy ledger statement lines imported yet"
    elif now - etsy_last > FRESHNESS["etsy_ledger"]:
        e_state, e_why = STALE, f"last Etsy ledger import {etsy_last.isoformat()}"
    else:
        e_state, e_why = MEASURED, ""
    out["etsy_ledger"] = {"state": e_state, "last_read_at": etsy_last.isoformat()
                          if etsy_last else None, "why": e_why,
                          "owner_action": "verify the Etsy ledger mapping" if not verified
                          else ""}
    if bank_last is None:
        b_state, b_why = DISCONNECTED, ("no business bank statement has been imported; cash "
                                        "is UNKNOWN, not CA$0.00")
    elif now - bank_last > FRESHNESS["bank"]:
        b_state, b_why = STALE, f"last bank statement import {bank_last.isoformat()}"
    else:
        b_state, b_why = MEASURED, ""
    out["bank"] = {"state": b_state, "last_read_at": bank_last.isoformat() if bank_last
                   else None, "why": b_why, "owner_action": "open a business bank account and "
                   "provide statements (owner action; Finance cannot do banking)"
                   if b_state == DISCONNECTED else ""}
    out["spend"] = {"state": MEASURED, "last_read_at": now.isoformat(),
                    "why": "this company's own cost ledger (cost_entries); row bases vary",
                    "owner_action": ""}
    warnings = [f"{k}: {v['state'].upper()} -- {v['why']}" for k, v in out.items()
                if v["state"] != MEASURED]
    return {"as_of": now.isoformat(), "sources": out, "warnings": warnings,
            "revenue_known": out["orders"]["state"] in (MEASURED, STALE),
            "cash_known": out["bank"]["state"] in (MEASURED, STALE)}


def figure_reading(state: str, has_rows: bool) -> str:
    """How a sales-derived figure reads given its source state.

    measured -> `measured`; stale -> `stale` (as of the last read); disconnected/never read
    with recorded rows -> `lower_bound`; with none -> `UNKNOWN` (the figure is None).
    """
    if state == MEASURED:
        return "measured"
    if state == STALE:
        return "stale"
    return "lower_bound" if has_rows else "UNKNOWN"
