"""The per-order operations ledger (F-558 Order Operations Ledger).

Criterion: for every order, reconcile payment, item/version, digital delivery state, buyer
issue, refund/cancellation/case state and downstream accounting evidence.

One row per recorded order, each of the six parts read from the row that holds it, and a
`problems` list naming every part that does not reconcile -- an order is `reconciled` only
when the list is empty. Nothing is inferred to fill a gap:

* **payment** -- the receipt state (`detail.state`), the amount in its own currency and in CAD
  with the FX basis; a held (UNKNOWN-value) sale is listed from `orders_ingest.held`.
* **item/version** -- the listing id and the version that was live when it sold, with how
  that was known (`version_basis`); an unknown version is a problem.
* **digital delivery** -- Etsy's own fields (OpenAPI: ShopReceiptTransaction.is_digital, "When
  true, the transaction recorded the purchase of a digital listing"; ShopReceipt.is_shipped).
  Etsy makes a digital file available on payment and the API exposes no download event, so
  the state is ``available_on_payment`` (digital + paid), ``not_digital`` (a physical line --
  a problem for a pattern shop), or ``UNKNOWN`` (the receipt did not say).
* **buyer issue** -- support cases for the buyer, open or escalated.
* **refund / cancellation / case** -- the receipt's refund amount and reasons, cancellation.
* **accounting** -- the sale's ledger row (`LedgerEntry.evidence_ref`), its fee basis and
  reconciliation state; a missing ledger row, or one whose figures disagree with the order,
  is a problem.
"""
from __future__ import annotations

UNKNOWN = "UNKNOWN"


def _delivery(detail: dict) -> dict:
    d = detail.get("delivery") or {}
    digital, state = d.get("is_digital"), detail.get("state")
    if digital is None:
        return {"state": UNKNOWN, "why": "the receipt line did not carry is_digital"}
    if not digital:
        return {"state": "not_digital", "why": "Etsy recorded a non-digital line"}
    if state in ("cancelled",):
        return {"state": "cancelled", "why": "cancelled before or after payment"}
    return {"state": "available_on_payment",
            "why": ("digital listing paid on Etsy: Etsy makes the file available on payment; "
                    "no download event is exposed by the API"), "download_observable": False}


def ledger(db) -> dict:
    from sqlalchemy import select

    from ..core.models import Customer, LedgerEntry, Order, SupportCase
    from . import orders_ingest

    rows, problems_total = [], 0
    with db.session() as s:
        held_refs = orders_ingest.held_refs(s)
        ledger_rows = {e.evidence_ref: e for e in s.scalars(select(LedgerEntry).where(
            LedgerEntry.category == "sale"))}
        for o in s.scalars(select(Order).order_by(Order.at, Order.id)):
            d = o.detail or {}
            cust = s.get(Customer, o.customer_id)
            cases = list(s.scalars(select(SupportCase).where(
                SupportCase.customer_ref == cust.customer_ref))) if cust else []
            led = ledger_rows.get(o.external_ref)
            refund = d.get("refund") or {}
            problems = []
            if o.external_ref in held_refs or d.get("revenue_unknown"):
                problems.append("payment: held, value UNKNOWN")
            if not o.version:
                problems.append("item/version: version not known")
            delivery = _delivery(d)
            if delivery["state"] in (UNKNOWN, "not_digital"):
                problems.append(f"delivery: {delivery['state']}")
            if led is None:
                problems.append("accounting: no sale ledger row")
            else:
                if abs(float(led.fees_cad or 0) - float(o.fees_cad or 0)) > 0.005:
                    problems.append("accounting: ledger fees differ from the order")
                if abs(float(led.refunds_cad or 0) - float(refund.get("cad") or 0)) > 0.005 \
                        and not d.get("ledger_refund_cad"):
                    problems.append("accounting: ledger refund differs from the receipt")
            open_cases = [c for c in cases if not c.resolved]
            rows.append({
                "order": o.external_ref, "at": o.at.isoformat() if o.at else None,
                "payment": {"state": d.get("state"), "currency": o.currency,
                            "amount_original": o.amount_original, "revenue_cad": o.revenue_cad,
                            "fx_measured": bool(o.fx_measured)},
                "item": {"listing_id": d.get("listing_id"), "product_slug": o.product_slug,
                         "version": o.version or UNKNOWN,
                         "version_basis": d.get("version_basis")},
                "delivery": delivery,
                "buyer_issue": {"cases": len(cases), "open": len(open_cases),
                                "escalated": sum(1 for c in cases if c.escalated)},
                "refund_case": {"state": d.get("state"), "refunded": bool(o.refunded),
                                "refund_cad": refund.get("cad"),
                                "reasons": refund.get("reasons") or [],
                                "cancelled": d.get("state") == "cancelled"},
                "accounting": ({"ledger_row": led.id, "fees_basis": led.fees_basis,
                                "reconciliation_state": led.reconciliation_state,
                                "fees_cad": led.fees_cad, "refunds_cad": led.refunds_cad}
                               if led is not None else None),
                "problems": problems, "reconciled": not problems,
            })
            problems_total += bool(problems)
    held = orders_ingest.held(db)
    return {"orders": len(rows), "reconciled": len(rows) - problems_total,
            "with_problems": problems_total, "held_sales": len(held), "rows": rows,
            "reading": "measured" if rows else "UNMEASURED"}
