"""The first ten sales as a protected learning cohort (F-595 First-10-Sales Learning Protocol).

Criterion: treat the first ten sales as a protected learning cohort: inspect search source,
conversion path, questions, download/support friction, reviews/refunds and economics after
each sale without destabilizing listings with constant edits.

* **After each sale** (`review`, called at the end of every `orders_ingest.ingest`): each of
  the first ten countable orders gets one durable inspection record
  (`OperatingReading` kind ``commerce.first_ten``, period ``sale01``..``sale10``) holding the
  six things the criterion names. A field this company cannot see yet is ``UNKNOWN`` with
  what would supply it -- never a guess, never zero. Records are refreshed on later runs
  (a refund or a review arriving after the sale reaches its record) with the change kept.
* **Without destabilising listings** (`edit_hold`): while the cohort is open (fewer than ten
  inspected sales), a non-emergency edit to a live listing is held. The SEO proposal carries
  the hold (`seo.proposals.propose` -> ``edit_hold``); an emergency (policy, truth or
  incident) is never held.
"""
from __future__ import annotations

from datetime import datetime, timezone

KIND = "commerce.first_ten"
COHORT_SIZE = 10
UNKNOWN = "UNKNOWN"


def _record(o, n: int, s) -> dict:
    from sqlalchemy import select

    from ..core.models import Customer, SupportCase
    from ..finance import sources

    detail = o.detail or {}
    attribution = detail.get("attribution") or {}
    customer = s.get(Customer, o.customer_id)
    cref = getattr(customer, "customer_ref", None)
    cases = []
    if cref:
        cases = list(s.scalars(select(SupportCase).where(SupportCase.customer_ref == cref)))
    friction = [c for c in cases
                if any(w in (c.question or "").lower()
                       for w in ("download", "file", "pdf", "open", "print", "access"))]
    refund = detail.get("refund") or {}
    return {
        "sale_number": n, "external_ref": o.external_ref, "at": o.at.isoformat(),
        "product_slug": o.product_slug, "version": o.version,
        "search_source": {"channel": sources.channel(o.acquisition_source),
                          "acquisition_source": o.acquisition_source or "unknown",
                          "evidence": attribution.get("evidence") or UNKNOWN,
                          "search_term": o.search_term or UNKNOWN},
        "conversion_path": (detail.get("conversion_path") or
                            {"reading": UNKNOWN,
                             "needs": "an Etsy Stats export for the sale's day "
                                      "(POST /api/attribution/stats)"}),
        "questions": {"support_cases": len(cases),
                      "escalated": sum(1 for c in cases if c.escalated)},
        "download_support_friction": {"cases": len(friction),
                                      "unresolved": sum(1 for c in friction if not c.resolved)},
        "review": {"reviewed": bool(o.reviewed)},
        "refund": {"refunded": bool(o.refunded), "state": detail.get("state"),
                   "refund_cad": refund.get("cad"), "reasons": refund.get("reasons") or []},
        "economics": {"price_cad": o.price_cad, "revenue_cad": o.revenue_cad,
                      "fees_cad": o.fees_cad, "fees_basis": o.fees_basis,
                      "offsite_ads_fee_cad": o.offsite_ads_fee_cad,
                      "contribution_cad": o.contribution_cad},
    }


def review(db, *, now: datetime | None = None) -> dict:
    """Write or refresh one inspection record per sale among the first ten."""
    from sqlalchemy import select

    from ..core.models import OperatingReading, Order
    from . import orders_ingest

    now = now or datetime.now(timezone.utc)
    written, refreshed = [], []
    with db.session() as s:
        held = orders_ingest.held_refs(s)
        cohort = [o for o in s.scalars(select(Order).order_by(Order.at, Order.id))
                  if orders_ingest.countable(o, held)][:COHORT_SIZE]
        for n, o in enumerate(cohort, start=1):
            rec = _record(o, n, s)
            key = f"sale{n:02d}"
            row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND,
                                                          OperatingReading.period_key == key))
            if row is None:
                s.add(OperatingReading(kind=KIND, period_key=key, at=now,
                                       payload={**rec, "inspected_at": now.isoformat(),
                                                "history": []}))
                written.append(key)
                continue
            old = dict(row.payload or {})
            if old.get("external_ref") != rec["external_ref"]:
                # an earlier sale arrived late or this one was voided: the slot moves, kept
                rec_hist = list(old.get("history") or []) + [
                    {"replaced": old.get("external_ref"), "at": now.isoformat()}]
            else:
                rec_hist = list(old.get("history") or [])
            changed = sorted(k for k in rec if old.get(k) != rec[k])
            if changed:
                rec_hist.append({"at": now.isoformat(), "changed": changed})
                row.payload = {**old, **rec, "history": rec_hist,
                               "refreshed_at": now.isoformat()}
                row.at = now
                refreshed.append(key)
        inspected = len(cohort)
    return {"cohort_size": COHORT_SIZE, "inspected": inspected, "open": inspected < COHORT_SIZE,
            "written": written, "refreshed": refreshed,
            "note": "one sale proves possibility, not scale; ten are a learning cohort"}


def state(db) -> dict:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        rows = list(s.scalars(select(OperatingReading).where(OperatingReading.kind == KIND)
                              .order_by(OperatingReading.period_key)))
        records = [dict(r.payload or {}) for r in rows]
    return {"inspected": len(records), "open": len(records) < COHORT_SIZE, "records": records}


def edit_hold(db, slug: str, *, live: bool, emergency: bool = False) -> dict:
    """Whether a change to this listing is held while the cohort is open."""
    try:
        st = state(db)
    except Exception as exc:  # noqa: BLE001 - unknown cohort state holds nothing silently
        return {"held": False, "reading": UNKNOWN, "why": type(exc).__name__}
    if not live:
        return {"held": False, "why": "not a live listing; drafts are not destabilised"}
    if emergency:
        return {"held": False, "why": "an emergency (policy, truth, incident) is never held"}
    if st["open"]:
        return {"held": True, "slug": slug, "inspected": st["inspected"],
                "why": (f"the first-ten-sales cohort is open ({st['inspected']}/"
                        f"{COHORT_SIZE} inspected): non-emergency edits to live listings "
                        f"are held so each sale is read against a stable listing (F-595)")}
    return {"held": False, "why": "the first-ten cohort is complete"}
