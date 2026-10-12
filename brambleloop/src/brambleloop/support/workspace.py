"""One customer-experience workspace: messages, orders, reviews, refunds, risk, fixes (F-689).

Support triage, the first-response watch, order ingest and refund root causes each kept
their own rows. F-689 asks for them *in one place*, joined on the buyer: what they wrote,
what they bought, whether they reviewed, whether they were refunded or cancelled and why,
which confusion keeps recurring, which cases or policy notices are at risk, and which
upstream fixes are open because of it.

Two views, deliberately different in what they may show:

- `workspace(db, customer_ref=...)` -- the operator view. It joins on `customer_ref` (the
  Etsy buyer id, never a name or email) and carries a case's question **truncated**; it
  belongs behind the operator credential (`app.main.CUSTOMER_DATA_ROUTES`).
- `summary(db)` -- aggregates only (counts, rates, codes, risks, fix signatures), safe for
  the dashboard and the provider contract. It never contains a buyer's words or reference.

Nothing here sends anything to anyone: in shadow every reply stays a draft, and a commercial
electronic message needs recorded CASL consent (`Customer.casl_consent`), which this module
reports and never assumes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

QUESTION_CHARS = 160


def _iso(at) -> str | None:
    if at is None:
        return None
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).isoformat()


def _risks(db) -> dict[str, Any]:
    """Case and policy risk, from the incidents the watches already raise."""
    from sqlalchemy import select

    from ..core.models import Incident

    prefixes = {"response": "support.first_response", "policy_violation":
                "etsy.policy_violation:", "suspected_takedown": "policy_violation_suspected:",
                "repeated_cause": "cx.repeated_cause:", "policy_text":
                "etsy.shop:policy_inconsistent"}
    out: dict[str, list] = {k: [] for k in prefixes}
    with db.session() as s:
        for row in s.scalars(select(Incident).where(Incident.resolved == False)):  # noqa: E712
            for key, prefix in prefixes.items():
                if row.signature.startswith(prefix):
                    out[key].append({"signature": row.signature, "severity": row.severity,
                                     "halts": row.halts_publication})
    return out


def _upstream_fixes(db) -> list[dict]:
    """Open fixes CX caused: repeated causes (listing/deliverable/pricing/policy/product)
    and row-hotspot defect candidates support mining has audited."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Incident

    fixes = []
    with db.session() as s:
        for row in s.scalars(select(Incident).where(
                Incident.signature.like("cx.repeated_cause:%"),
                Incident.resolved == False)):  # noqa: E712
            d = row.detail or {}
            fixes.append({"kind": d.get("investigation"), "owner": d.get("owner"),
                          "product": d.get("product"), "cause": d.get("code"),
                          "count": d.get("count"), "signature": row.signature})
        seen = set()
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == "support.defect_candidate")
                .order_by(desc(AuditLog.id)).limit(50)):
            d = row.detail or {}
            key = (d.get("product"), d.get("row"))
            if key in seen:
                continue
            seen.add(key)
            fixes.append({"kind": "deliverable", "owner": "quality", "product":
                          d.get("product"), "cause": f"row {d.get('row')} hotspot",
                          "count": d.get("mentions"), "signature": None})
    return fixes


def workspace(db, *, customer_ref: str | None = None, limit: int = 50) -> dict:
    """The operator view, one entry per buyer. Operator credential only."""
    from sqlalchemy import select

    from ..core.models import Customer, Order, SupportCase

    buyers: dict[str, dict] = {}

    def buyer(ref: str) -> dict:
        return buyers.setdefault(ref, {"customer_ref": ref, "messages": [], "orders": [],
                                       "reviews": [], "refunds": [], "casl_consent": None})

    with db.session() as s:
        cq = select(SupportCase).order_by(SupportCase.id.desc())
        if customer_ref:
            cq = cq.where(SupportCase.customer_ref == customer_ref)
        for c in s.scalars(cq.limit(max(1, min(limit, 500)) * 4)):
            d = c.detail or {}
            buyer(c.customer_ref)["messages"].append({
                "case_id": c.id, "at": _iso(c.at), "product": c.product_slug,
                "desk": c.specialist, "escalated": c.escalated, "resolved": c.resolved,
                "reply": "sent" if c.sent else ("draft" if c.answer else "none"),
                "theme": d.get("theme"), "root_cause": (d.get("root_cause") or {}).get("code"),
                "question": (c.question or "")[:QUESTION_CHARS]})
        customers = {c.id: c for c in s.scalars(select(Customer))}
        oq = select(Order).order_by(Order.id.desc())
        for o in s.scalars(oq.limit(max(1, min(limit, 500)) * 4)):
            cust = customers.get(o.customer_id)
            ref = cust.customer_ref if cust else f"customer:{o.customer_id}"
            if customer_ref and ref != customer_ref:
                continue
            d = o.detail or {}
            b = buyer(ref)
            b["casl_consent"] = bool(cust.casl_consent) if cust else None
            b["orders"].append({"order": o.external_ref, "at": _iso(o.at),
                                "product": o.product_slug, "version": o.version,
                                "state": d.get("state"), "support_case_id": o.support_case_id})
            if o.reviewed:
                b["reviews"].append({"order": o.external_ref,
                                     "stars": d.get("review_stars", d.get("rating"))})
            rc = d.get("root_cause")
            if o.refunded or rc:
                b["refunds"].append({"order": o.external_ref, "state": d.get("state"),
                                     "refund_cad": (d.get("refund") or {}).get("cad"),
                                     "reason_code": (rc or {}).get("code"),
                                     "owner": (rc or {}).get("owner")})
    rows = sorted(buyers.values(), key=lambda b: -(len(b["messages"]) + len(b["orders"])))
    return {"buyers": rows[:limit], "count": len(buyers), "nothing_sent": all(
        m["reply"] != "sent" for b in rows for m in b["messages"]),
        "risks": _risks(db), "upstream_fixes": _upstream_fixes(db)}


def summary(db) -> dict:
    """Aggregates only; provider-shaped; never raises on an empty database."""
    try:
        from sqlalchemy import select

        from ..commerce import cx_root_cause
        from ..core.models import Order, SupportCase
        from .department import confusion_reading

        with db.session() as s:
            cases = list(s.scalars(select(SupportCase)))
            orders = list(s.scalars(select(Order)))
        causes = cx_root_cause.causes(db)
        by_code: dict[str, int] = {}
        for c in causes:
            by_code[c["code"]] = by_code.get(c["code"], 0) + 1
        risks = _risks(db)
        fixes = _upstream_fixes(db)
        stars = [int(v) for o in orders if o.reviewed
                 for v in [(o.detail or {}).get("review_stars", (o.detail or {}).get(
                     "rating"))] if isinstance(v, (int, float))]
        reading = {
            "messages": {"cases": len(cases), "open": sum(1 for c in cases if not c.resolved),
                         "escalated": sum(1 for c in cases if c.escalated),
                         "replies_sent": sum(1 for c in cases if c.sent)},
            "orders": {"count": len(orders),
                       "refunded_or_cancelled": sum(1 for o in orders if o.refunded),
                       "reviewed": sum(1 for o in orders if o.reviewed)},
            "reviews": {"count": len(stars),
                        "mean_stars": round(sum(stars) / len(stars), 2) if stars
                        else "UNMEASURED"},
            "refund_causes": by_code,
            "recurring_confusion": confusion_reading(db),
            "risks": {k: len(v) for k, v in risks.items()},
            "upstream_fixes": [{k: f[k] for k in ("kind", "owner", "product", "cause",
                                                  "count")} for f in fixes],
        }
        if not cases and not orders:
            status, basis = "UNKNOWN", "unknown"
        elif any(r["halts"] for v in risks.values() for r in v):
            status, basis = "DEGRADED", "measured"
        else:
            status, basis = "OK", "measured"
        return {"status": status, "as_of": datetime.now(timezone.utc).isoformat(),
                "basis": basis, "items": [reading], "reason": (
                    "no support case and no order on file" if status == "UNKNOWN" else ""),
                "sources": ["support_cases", "orders", "incidents:cx.repeated_cause",
                            "incidents:etsy.policy_violation", "audit_log:support."
                            "defect_candidate"]}
    except Exception as e:  # noqa: BLE001 - provider contract: never raise
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": [], "reason": f"{type(e).__name__}: {str(e)[:200]}"}
