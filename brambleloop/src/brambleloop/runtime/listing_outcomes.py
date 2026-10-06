"""`listing.outcomes`: the scheduled producer of listing outcomes (wave-3 K3, F-258).

Daily. Records every queued owner listing-level Stats export into `listing_outcomes` through
`creative.style_learning.record_outcome` (read back to prove the round trip), takes the
read-only Etsy API snapshot of each active listing's cumulative views and favourites, and
stores the per-listing funnel with its failing stage. Until its own cadence is wired (see the
K3 handoff WIRING REQUEST), the daily `commerce.readings` job runs it first, so the funnel
readers that follow read what was recorded today.

GREEN: Etsy read-only (`getListingsByShop`), this database only; nothing spent, published or
sent. No credential -> the API half is UNKNOWN and stores nothing.
"""
from __future__ import annotations

from .worker import JobContext, handlers

ACTION = "listing.outcomes"


def run(db, phase: str) -> dict:
    """One producer pass. The Etsy client is built the one way cluster B builds it."""
    from ..commerce import listing_outcomes
    from . import etsy_ops

    try:
        client = etsy_ops.build_client(db, phase)
    except Exception:  # noqa: BLE001 - no client is an UNKNOWN API half, not a failed run
        client = None
    return listing_outcomes.produce(db, client=client)


def summary(reading: dict) -> dict:
    return {
        "exports_processed": len(reading.get("exports") or []),
        "recorded_listings": reading.get("recorded_listings") or [],
        "api": (reading.get("api") or {}).get("status"),
        "api_observed": (reading.get("api") or {}).get("observed"),
        "listings": len(reading.get("listings") or []),
        "stages": {r["slug"]: r["stage"] for r in reading.get("listings") or []},
        "measurement": {k: (reading.get("measurement") or {}).get(k)
                        for k in ("organic", "paid", "basis")},
    }


@handlers.register(ACTION)
def handle_listing_outcomes(ctx: JobContext) -> dict:
    reading = run(ctx.db, ctx.phase.value)
    out = summary(reading)
    ctx.audit(ACTION, detail=out)
    return out
