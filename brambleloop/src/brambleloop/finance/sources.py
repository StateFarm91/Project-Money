"""Where a sale came from, said honestly (F-283 First-Sale Attribution, F-289 Traffic Source
Separation).

The order ingest used to write `acquisition_source="etsy"` on every order. Every receipt is
an Etsy sale, so the label was not false -- but it answered a question nobody asked. The
question the Master asks is *which* Etsy: organic search, Etsy Ads, Offsite Ads, or a buyer
who arrived from something this company owns. "etsy" blends all four, and every reader
downstream (the growth loops, the channel stress test, CAC) read it as organic, because
that was the nearest key. A proxy that asserts a source the system does not know is worse
than `unknown`: `unknown` at least keeps the question open.

So:

* **Ingest writes `unknown`.** A receipt carries no traffic source. The source changes only
  when *evidence* arrives, and the evidence is kept beside it: an Offsite Ads fee on Etsy's
  payment-account ledger (Etsy charges that fee only on a sale it attributes to an offsite
  ad), a Stats export, or an owner statement. `attribute()` is the one writer, and it
  refuses a source without evidence.
* **The table always shows every channel**, including an explicit `unattributed` bucket.
  A blended total never hides its components: the total is the sum of the rows, and the
  unattributed row is as prominent as the others.
* **The first sale is a record**, written once, with its source and its evidence, and the
  sentence the Master insists on: one sale proves possibility, not scale.
"""
from __future__ import annotations

from datetime import datetime, timezone

# The channels the Master names, in the order the owner reads them. `unattributed` is not a
# channel; it is the honest name for every order whose channel is not known, and it is
# always shown.
CHANNELS: tuple[str, ...] = ("etsy_organic", "etsy_ads", "offsite_ads", "owned_direct")
UNATTRIBUTED = "unattributed"

# Raw `acquisition_source` values other modules already write, mapped to a named channel.
# Anything not here (including the legacy blanket "etsy", which never knew which Etsy
# channel it meant) is unattributed.
_TO_CHANNEL = {
    "etsy_organic": "etsy_organic", "etsy_search": "etsy_organic",
    "etsy_ads": "etsy_ads",
    "offsite_ads": "offsite_ads",
    "owned_direct": "owned_direct", "direct": "owned_direct", "email": "owned_direct",
    "pinterest": "owned_direct", "google": "owned_direct", "seo": "owned_direct",
}

# Sources `attribute` accepts. The four channels plus the owned sub-channels other readers
# already key on; `unknown` is the default and needs no evidence.
ATTRIBUTABLE = frozenset(CHANNELS) | frozenset({"etsy_search", "pinterest", "google", "email",
                                                "direct"})

FIRST_SALE_KIND = "commerce.first_sale"
FIRST_SALE_NOTE = ("One sale proves possibility, not scale. It says a buyer can find, trust "
                   "and pay for this product; it says nothing about how many more will.")


class AttributionRefused(ValueError):
    """A source claimed without evidence, or a source this module does not know."""


def channel(acquisition_source: str | None) -> str:
    return _TO_CHANNEL.get((acquisition_source or "").strip().lower(), UNATTRIBUTED)


def attribute(db, external_ref: str, source: str, *, evidence: str,
              by: str = "system") -> dict:
    """Set an order's acquisition source from evidence. The only writer of a known source.

    Idempotent: re-attributing to the same source with the same evidence changes nothing.
    A different source replaces the old one and the previous attribution is kept in the
    order's detail, so a correction is visible rather than silent.
    """
    from sqlalchemy import select

    from ..core.models import Customer, Order

    source = (source or "").strip().lower()
    if source not in ATTRIBUTABLE:
        raise AttributionRefused(f"{source!r} is not a channel this company reports "
                                 f"({sorted(ATTRIBUTABLE)})")
    if not (evidence or "").strip():
        raise AttributionRefused("an acquisition source without evidence is a guess; "
                                 "leave the order unknown instead")
    with db.session() as s:
        order = s.scalar(select(Order).where(Order.external_ref == external_ref))
        if order is None:
            raise AttributionRefused(f"no order {external_ref!r}")
        detail = dict(order.detail or {})
        current = detail.get("attribution") or {}
        if order.acquisition_source == source and current.get("evidence") == evidence:
            return {"changed": False, "source": source}
        history = list(detail.get("attribution_history") or [])
        if current:
            history.append(current)
        detail["attribution"] = {"source": source, "evidence": evidence, "by": by,
                                 "at": datetime.now(timezone.utc).isoformat()}
        detail["attribution_history"] = history
        order.detail = detail
        order.acquisition_source = source
        if source == "offsite_ads":
            order.offsite_ad_attributed = True
        # The customer's acquisition source is their first order's.
        customer = s.get(Customer, order.customer_id)
        if customer is not None and (customer.acquisition_source or "unknown") in (
                "unknown", "etsy"):
            first = s.scalar(select(Order).where(Order.customer_id == customer.id)
                             .order_by(Order.at, Order.id).limit(1))
            if first is not None and first.id == order.id:
                customer.acquisition_source = source
    return {"changed": True, "source": source}


def table(db, *, since: datetime | None = None, until: datetime | None = None) -> dict:
    """Orders and revenue per channel, every channel present, unattributed explicit.

    Only countable orders (`orders_ingest.countable`): a voided order (refunded in full or
    cancelled) is not an order, and an unreconciled or held one has UNKNOWN revenue, so
    neither moves any channel -- the same rule the books use. The total is the sum of the
    rows; it is never shown without them.
    """
    from sqlalchemy import select

    from ..commerce import orders_ingest
    from ..core.models import Order

    rows = {k: {"orders": 0, "revenue_cad": 0.0, "contribution_cad": 0.0}
            for k in (*CHANNELS, UNATTRIBUTED)}
    with db.session() as s:
        q = select(Order)
        if since is not None:
            q = q.where(Order.at >= since)
        if until is not None:
            q = q.where(Order.at <= until)
        # rc1-ORD2: only countable orders (orders_ingest.countable) -- a voided, unreconciled
        # or held order is neither an order nor revenue on any channel.
        for o in orders_ingest.countable_orders(s, q):
            row = rows[channel(o.acquisition_source)]
            row["orders"] += 1
            row["revenue_cad"] += float(o.revenue_cad or 0.0)
            row["contribution_cad"] += float(o.contribution_cad or 0.0)
    for row in rows.values():
        row["revenue_cad"] = round(row["revenue_cad"], 2)
        row["contribution_cad"] = round(row["contribution_cad"], 2)
    total_orders = sum(r["orders"] for r in rows.values())
    return {
        "channels": rows,
        "total_orders": total_orders,
        "unattributed_share": (round(rows[UNATTRIBUTED]["orders"] / total_orders, 4)
                               if total_orders else None),
        "note": ("Every channel is shown, including the orders whose channel is not known. "
                 "A receipt does not say how the buyer arrived; an order moves out of "
                 "`unattributed` only on evidence (an Offsite Ads fee on Etsy's ledger, a "
                 "Stats export, an owner statement)."),
    }


def first_sale(db) -> dict | None:
    """The stored first-sale record, or None when there has been no sale.

    A record whose only sale was voided (refunded in full or cancelled) is kept in the
    database with its history, but is not a first sale: this returns None for it (E2).
    """
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == FIRST_SALE_KIND).limit(1))
        if row is None or (row.payload or {}).get("voided"):
            return None
        return dict(row.payload or {})


def record_first_sale(db) -> dict | None:
    """Write (once) or refresh the first-sale record from the earliest order.

    The record is written the first time an order exists and is never replaced by a later
    order. Its source is refreshed from the order, so evidence that arrives after the sale
    (an Offsite Ads fee posted a day later) reaches it, and each change is kept.

    A voided order (refunded in full or cancelled) is not a sale (RC1 audit E2): the record
    is taken from the earliest order that is not voided, and a recorded first sale that is
    later voided is replaced by the next one -- the voided one stays in the history. When no
    order remains that is not voided, the record is kept, marked `voided`, and reads as no
    first sale.
    """
    from sqlalchemy import select

    from ..core.models import OperatingReading, Order

    from ..commerce import orders_ingest as _oi

    with db.session() as s:
        # rc1-ORD2: the first sale is the earliest *countable* order (orders_ingest.countable):
        # not voided, and not unreconciled/held (revenue UNKNOWN -- listed below by name).
        held = _oi.held_refs(s)
        order = next((o for o in s.scalars(select(Order).order_by(Order.at, Order.id))
                      if _oi.countable(o, held)), None)
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == FIRST_SALE_KIND).limit(1))
        if order is None:
            if row is not None and not (row.payload or {}).get("voided"):
                old = dict(row.payload or {})
                history = list(old.get("history") or [])
                history.append({"external_ref": old.get("external_ref"), "voided": False,
                                "why": "the order was refunded in full or cancelled"})
                row.payload = {**old, "voided": True, "history": history}
                row.at = datetime.now(timezone.utc)
            return None
        attribution = (order.detail or {}).get("attribution") or {}
        payload = {
            "external_ref": order.external_ref, "at": order.at.isoformat(),
            "product_slug": order.product_slug, "version": order.version,
            "price_cad": order.price_cad, "currency": order.currency,
            "amount_original": order.amount_original,
            "acquisition_source": order.acquisition_source or "unknown",
            "channel": channel(order.acquisition_source),
            "evidence": (attribution.get("evidence") or
                         "none: the receipt does not say how the buyer arrived, so the "
                         "source is unknown until a ledger fee, a Stats export or the owner "
                         "says otherwise"),
            "order_source": order.source,
            "note": FIRST_SALE_NOTE,
        }
        # A sale held by the ingest (CAD value or refund UNKNOWN, RC1 audit E1/E3) is not an
        # order row, but it may be the real first sale: the record says so by name.
        from ..commerce import orders_ingest

        earlier = [h["ref"] for h in orders_ingest.held(db, until=order.at)
                   if h.get("state") not in ("fully_refunded", "cancelled")]
        payload["earlier_held_sales"] = earlier
        payload["first_sale_uncertain"] = bool(earlier)
        if row is None:
            s.add(OperatingReading(kind=FIRST_SALE_KIND, period_key="first",
                                   payload={**payload, "recorded_at":
                                            datetime.now(timezone.utc).isoformat(),
                                            "history": []}))
            return {**payload, "created": True}
        old = dict(row.payload or {})
        payload["voided"] = False
        if old.get("external_ref") != payload["external_ref"]:
            # Never replaced by a later order -- unless the recorded one was voided; an
            # earlier one arriving late is kept in the history so the change is visible.
            old_order = s.scalar(select(Order).where(
                Order.external_ref == old.get("external_ref")))
            old_voided = (old.get("voided") or old_order is None
                          or not _oi.countable(old_order, held))
            if old.get("at", "") <= payload["at"] and not old_voided:
                return {**old, "created": False}
        changed = {k: v for k, v in payload.items() if old.get(k) != v}
        if changed:
            history = list(old.get("history") or [])
            history.append({k: old.get(k) for k in changed})
            row.payload = {**old, **payload, "history": history}
            row.at = datetime.now(timezone.utc)
        return {**payload, "created": False, "changed": sorted(changed)}
