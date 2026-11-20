"""Etsy sales-channel inventory with explicit readiness (F-590 Sales Channel Inventory).

Criterion: inventory every enabled Etsy sales channel/integration and its effect on listings,
inventory, payments, customer data and attribution; new channels require explicit readiness.

Two halves:

* **The inventory** (`INVENTORY`): every channel Etsy's API lets this company observe, with
  its effect on the five things the criterion names, whether this company has enabled it,
  and whether it is *readied* (decided, with its effects handled). Sources: Etsy's OpenAPI
  document as recorded in `intel.etsy_surfaces` (``sales_channels``: ``ShopReceipt.
  receipt_type`` "0 or 5 for Etsy.com, 1 for a Pattern shop"; listing flags
  ``CUSTOM_SHOPS (pattern), SELL_ON_FACEBOOK``).
* **The observation** (`observe`): every recorded order's `receipt_type` (written by
  `orders_ingest.lines`) counted per channel. A sale through a channel that is not readied --
  or an unrecognised receipt_type -- opens one incident per channel and is never folded into
  Etsy.com. An order whose receipt did not carry a type is counted `unknown`, not Etsy.com.
"""
from __future__ import annotations

from datetime import datetime, timezone

SIGNATURE = "commerce.sales_channel.unreadied"

INVENTORY: dict[str, dict] = {
    "etsy_com": {
        "name": "Etsy.com marketplace", "receipt_types": (0, 5), "enabled": True,
        "readied": True,
        "effects": {
            "listings": "the only storefront; every listing is published here",
            "inventory": "digital patterns: unlimited quantity, no stock to split",
            "payments": "Etsy Payments; fees read from the payment-account ledger "
                        "(finance.reconcile)",
            "customer_data": "Etsy buyer user id only, personal data dropped at ingest",
            "attribution": "unknown until ledger/Stats/owner evidence (finance.sources)",
        },
        "evidence": "intel.etsy_surfaces sales_channels (OpenAPI ShopReceipt.receipt_type)",
    },
    "pattern": {
        "name": "Pattern by Etsy (separate website)", "receipt_types": (1,), "enabled": False,
        "readied": False,
        "effects": {
            "listings": "mirrors Etsy listings on a second storefront",
            "inventory": "shares the Etsy listing inventory",
            "payments": "separate subscription and fee schedule not modelled here",
            "customer_data": "buyers who never visited etsy.com",
            "attribution": "off-marketplace traffic not covered by any reader here",
        },
        "evidence": "intel.etsy_surfaces sales_channels: NOT_APPLICABLE (no decision to buy "
                    "a Pattern subscription)",
    },
    "facebook": {
        "name": "Sell on Facebook (listing flag)", "receipt_types": (), "enabled": False,
        "readied": False,
        "effects": {
            "listings": "listings flagged SELL_ON_FACEBOOK appear on a third-party surface",
            "inventory": "shares the Etsy listing inventory",
            "payments": "unverified",
            "customer_data": "third-party platform data handling (CASL/privacy review)",
            "attribution": "social traffic not separable from receipts",
        },
        "evidence": "OpenAPI listing-state note names the SELL_ON_FACEBOOK flag",
    },
}


def channel_for(receipt_type) -> str:
    if receipt_type is None or receipt_type == "":
        return "unknown"
    try:
        rt = int(receipt_type)
    except (TypeError, ValueError):
        return f"unrecognised:{receipt_type}"
    for key, ch in INVENTORY.items():
        if rt in ch["receipt_types"]:
            return key
    return f"unrecognised:{rt}"


def inventory() -> dict:
    return {"channels": INVENTORY,
            "enabled": [k for k, v in INVENTORY.items() if v["enabled"]],
            "readied": [k for k, v in INVENTORY.items() if v["readied"]]}


def observe(db, *, now: datetime | None = None) -> dict:
    """Count recorded orders per channel; raise an incident per unreadied channel seen."""
    from sqlalchemy import select

    from ..core.models import Incident, Order

    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    with db.session() as s:
        for ref, detail in s.execute(select(Order.external_ref, Order.detail)).all():
            ch = channel_for((detail or {}).get("receipt_type"))
            counts[ch] = counts.get(ch, 0) + 1
            examples.setdefault(ch, [])
            if len(examples[ch]) < 5:
                examples[ch].append(ref)
        unready = sorted(ch for ch in counts
                         if ch != "unknown" and not INVENTORY.get(ch, {}).get("readied"))
        raised = []
        for ch in unready:
            sig = f"{SIGNATURE}:{ch}"[:200]
            inc = s.scalar(select(Incident).where(Incident.signature == sig,
                                                  Incident.resolved == False))  # noqa: E712
            if inc is None:
                s.add(Incident(signature=sig, severity="P1",
                               summary=(f"{counts[ch]} sale(s) arrived through sales channel "
                                        f"{ch!r}, which has no explicit readiness: its effect "
                                        f"on listings, inventory, payments, customer data "
                                        f"and attribution is not handled"),
                               detail={"channel": ch, "orders": examples[ch],
                                       "inventory": INVENTORY.get(ch)}))
            else:
                inc.detail = {**(inc.detail or {}), "orders": examples[ch],
                              "count": counts[ch]}
            raised.append(ch)
    return {"at": now.isoformat(), "by_channel": counts, "unreadied_seen": raised,
            "unknown_type_orders": counts.get("unknown", 0),
            "reading": "measured" if counts else "UNMEASURED", **inventory()}
