"""The Shop Manager dashboard, from what this company can actually read (W4-C12).

F-551 (Dashboard Task Harvester): "Ingest Shop Manager dashboard top tasks, Shop Advisor
warnings, recent activity, open orders, messages needing response, renewals/expiry and
shop-specific reminders. Every actionable item becomes a durable task with owner, deadline,
evidence and closure proof."

F-552 (Dashboard KPI Snapshot): "Persist dashboard views/visits/orders/revenue and relevant date
range/channel context. Dashboard numbers are quick signals, not substitutes for detailed Stats."

F-562 (Stats Traffic-Source Model): "Track Etsy Search, Etsy app/other Etsy pages, direct
traffic, social, Etsy Ads, Offsite Ads and other available sources separately; preserve Etsy's
attribution definitions."

Etsy's Open API has no dashboard, Shop Advisor, conversations or Stats resource. So:

* `harvest()` reads only what this company already holds from the API -- ingested orders
  (`Order.detail.receipt_status`) and the daily listing census's renewal/expiry state -- and
  turns each actionable item into an `OwnerAction` with an owner, a deadline, the evidence row
  and, when the next harvest no longer observes it, a SATISFIED close naming that harvest as
  its proof. The dashboard-only sources are listed as UNAVAILABLE with why, never as "none".
  It writes nothing to Etsy.
* `kpi_snapshot()` persists orders and revenue for a stated date range from ingested orders
  (measured) beside the owner's dashboard reading of views/visits (owner-recorded) when one is
  given; views and visits are UNKNOWN otherwise, never 0. It is labelled a quick signal.
* `record_traffic_sources()` stores an owner-exported Stats traffic-source table with Etsy's
  source labels verbatim. Known labels are mapped to their Etsy definition; an unrecognised
  label is kept as itself, never folded into "other".
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

TASK_PREFIX = "etsy.dashboard:"
OPEN_RECEIPT_STATES = ("open", "paid", "payment processing")
ORDER_DEADLINE_HOURS = 24
RENEWAL_LEAD_DAYS = 7
KPI_KIND = "etsy.dashboard_kpi"
TRAFFIC_KIND = "etsy.stats_traffic_sources"

#: Dashboard sources and whether this company can read them.
SOURCES: dict[str, dict] = {
    "open_orders": {"available": True, "via": "orders ingested from Etsy receipts"},
    "renewals_expiry": {"available": True, "via": "the daily listing census"},
    "messages_needing_response": {"available": False,
                                  "why": "Etsy's Open API exposes no conversations resource"},
    "top_tasks": {"available": False, "why": "Shop Manager dashboard only; no API resource"},
    "shop_advisor": {"available": False, "why": "Shop Manager dashboard only; no API resource"},
    "recent_activity": {"available": False, "why": "Shop Manager dashboard only"},
    "shop_reminders": {"available": False, "why": "Shop Manager dashboard only"},
}

#: Etsy Stats traffic-source labels and Etsy's own meaning (F-562). Kept as Etsy words them.
ETSY_TRAFFIC_SOURCES: dict[str, str] = {
    "Etsy search": "visits from searches on Etsy",
    "Etsy app & other Etsy pages": "visits from the Etsy app and Etsy pages other than search",
    "Direct & other traffic": "typed or bookmarked visits and sources Etsy cannot attribute",
    "Social media": "visits from social networks",
    "Etsy Ads": "visits from Etsy Ads placements on Etsy",
    "Offsite Ads": "visits from Etsy's Offsite Ads on other sites",
    "Etsy marketing & SEO": "visits from Etsy's own marketing and search-engine traffic",
}


class DashboardRefused(ValueError):
    """An input this module will not record as evidence."""


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _stamp(at: datetime) -> str:
    """A unique period key per recorded snapshot (the date range lives in the payload)."""
    import uuid

    return f"{at.strftime('%y%m%d')}-{uuid.uuid4().hex[:13]}"


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ---- F-551 ---------------------------------------------------------------------------------

def _observed_items(db, now: datetime) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Order

    items = []
    with db.session() as s:
        for o in s.scalars(select(Order).order_by(Order.id)):
            st = str((o.detail or {}).get("receipt_status") or "").strip().lower()
            if st in OPEN_RECEIPT_STATES and not o.refunded:
                items.append({
                    "key": f"{TASK_PREFIX}order:{o.external_ref}", "kind": "open_order",
                    "owner": "support", "evidence": f"orders:{o.id} (receipt {st})",
                    "deadline": _aware(o.at) + timedelta(hours=ORDER_DEADLINE_HOURS),
                    "action": (f"Etsy order {o.external_ref} is {st}: confirm the buyer has "
                               f"the download and answer any question")})
    try:
        from ..runtime.etsy_ops import CENSUS_READING, latest_reading

        census = latest_reading(db, CENSUS_READING) or {}
    except Exception:  # noqa: BLE001 - no census is no renewal evidence, not "none due"
        census = {}
    for row in census.get("estate") or []:
        ren = row.get("renewal") or {}
        if not row.get("ours"):
            continue
        if ren.get("mode") == "expired" or ren.get("expiring_soon"):
            left = ren.get("days_to_expiry")
            deadline = now + timedelta(days=max(0.0, float(left or 0)))
            items.append({
                "key": f"{TASK_PREFIX}renewal:{row.get('listing_id')}", "kind": "renewal",
                "owner": "store_commerce",
                "evidence": f"etsy.listing_census@{census.get('observed_at')}",
                "deadline": deadline,
                "action": (f"Listing {row.get('listing_id')} ({row.get('slug')}) is "
                           f"{'expired' if ren.get('mode') == 'expired' else f'expiring in {left} days'}: "
                           f"decide renewal on its evidence (commerce.listing_lifecycle."
                           f"renewal_economics), never on the date alone")})
    return items


def harvest(db, *, now: datetime | None = None) -> dict:
    """Every API-reachable actionable item as a durable task; close what is no longer seen."""
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..ops import owner_queue

    now = _now(now)
    observed = _observed_items(db, now)
    seen = {i["key"] for i in observed}
    opened, kept, closed = [], [], []
    with db.session() as s:
        open_rows = {r.requirement_key: r for r in s.scalars(select(OwnerAction).where(
            OwnerAction.done == False,  # noqa: E712
            OwnerAction.requirement_key.like(f"{TASK_PREFIX}%")))}
        for it in observed:
            if it["key"] in open_rows:
                kept.append(it["key"])
                continue
            s.add(OwnerAction(
                requirement_key=it["key"], action=it["action"],
                reason=f"harvested from {it['evidence']}; owner {it['owner']}",
                minutes=5, blocks=it["key"], expires_at=None,
                consequence_of_delay=f"due {it['deadline'].isoformat()}"))
            opened.append(it["key"])
        for key, row in open_rows.items():
            if key not in seen:
                owner_queue.close(row, owner_queue.SATISFIED,
                                  f"closure proof: the harvest at {now.isoformat()} no longer "
                                  f"observes it in its source", now=now)
                closed.append(key)
    return {"at": now.isoformat(), "opened": opened, "still_open": kept, "closed": closed,
            "tasks": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                       for k, v in i.items()} for i in observed],
            "sources": SOURCES,
            "unavailable": sorted(k for k, v in SOURCES.items() if not v["available"])}


# ---- F-552 ---------------------------------------------------------------------------------

def kpi_snapshot(db, *, start: date, end: date, owner_reading: dict | None = None,
                 channel: str = "all", now: datetime | None = None) -> dict:
    """Persist one dated dashboard snapshot: measured orders/revenue, owner-read views/visits."""
    from sqlalchemy import select

    from ..core.models import OperatingReading, Order

    if end < start:
        raise DashboardRefused("a date range ends on or after it starts")
    lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    hi = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
    with db.session() as s:
        rows = [o for o in s.scalars(select(Order)) if lo <= _aware(o.at) < hi]
    orders = [o for o in rows if not o.refunded]
    reading = dict(owner_reading or {})
    for k in ("views", "visits"):
        if k in reading and (not isinstance(reading[k], int) or reading[k] < 0):
            raise DashboardRefused(f"{k} is a non-negative count read off the dashboard")
    if reading and not str(reading.get("read_on") or "").strip():
        raise DashboardRefused("an owner dashboard reading says when it was read")
    payload = {
        "range": {"start": start.isoformat(), "end": end.isoformat()}, "channel": channel,
        "orders": {"value": len(orders), "basis": "measured: ingested Etsy receipts"},
        "revenue_cad": {"value": round(sum(o.revenue_cad or 0.0 for o in orders), 2),
                        "basis": "measured: ingested Etsy receipts"},
        "views": ({"value": reading["views"], "basis": f"owner-recorded {reading['read_on']}"}
                  if "views" in reading else {"value": "UNKNOWN",
                                              "basis": "no API source; not read"}),
        "visits": ({"value": reading["visits"],
                    "basis": f"owner-recorded {reading['read_on']}"}
                   if "visits" in reading else {"value": "UNKNOWN",
                                                "basis": "no API source; not read"}),
        "note": "a dashboard snapshot is a quick signal, not a substitute for detailed Stats"}
    with db.session() as s:
        at = _now(now)
        s.add(OperatingReading(kind=KPI_KIND, at=at, period_key=_stamp(at), payload=payload))
    return payload


# ---- F-562 ---------------------------------------------------------------------------------

def parse_traffic_sources(text: str) -> list[dict]:
    """An owner-exported Stats traffic-source table; Etsy's labels kept verbatim."""
    reader = csv.DictReader(io.StringIO(text))
    heads = {(h or "").strip().lower(): h for h in reader.fieldnames or []}
    src = next((heads[h] for h in ("traffic source", "source") if h in heads), None)
    vis = next((heads[h] for h in ("visits", "visit count") if h in heads), None)
    if src is None or vis is None:
        raise DashboardRefused("the export needs a 'Traffic source' and a 'Visits' column")
    out = []
    for n, row in enumerate(reader, start=2):
        label = (row.get(src) or "").strip()
        raw = (row.get(vis) or "").strip().replace(",", "")
        if not label:
            raise DashboardRefused(f"line {n}: a row with no source label")
        if not raw.isdigit():
            raise DashboardRefused(f"line {n}: visits {raw!r} is not a count")
        out.append({"etsy_label": label, "visits": int(raw),
                    "etsy_definition": ETSY_TRAFFIC_SOURCES.get(label),
                    "recognised": label in ETSY_TRAFFIC_SOURCES})
    return out


def record_traffic_sources(db, *, text: str, start: date, end: date, exported_on: date,
                           now: datetime | None = None) -> dict:
    from ..core.models import OperatingReading

    rows = parse_traffic_sources(text)
    labels = [r["etsy_label"] for r in rows]
    if len(labels) != len(set(labels)):
        raise DashboardRefused("a source appears twice; Etsy reports each source once")
    payload = {"range": {"start": start.isoformat(), "end": end.isoformat()},
               "exported_on": exported_on.isoformat(), "basis": "owner-exported Etsy Stats",
               "sources": rows, "total_visits": sum(r["visits"] for r in rows),
               "unrecognised": [r["etsy_label"] for r in rows if not r["recognised"]]}
    with db.session() as s:
        at = _now(now)
        s.add(OperatingReading(kind=TRAFFIC_KIND, at=at, period_key=_stamp(at),
                               payload=payload))
    return payload
