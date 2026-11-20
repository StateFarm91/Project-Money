"""Every refund, cancellation, case and complaint gets a reason code and an owner (F-535).

Refunds were a flag on an ingested order, counted into refund rate and the kill table; no
reason, no owner, and nothing noticed when the same thing kept happening. This module:

- **classifies** deterministically (no model call): the text Etsy's refund rows carry
  (`reason`, `note_from_issuer`, captured by `orders_ingest`), else the linked support case's
  question, else nothing -- in which case the code is `unrecorded` and the owner is the
  owner, because only a person can read Etsy's case page. Every code has an owning
  department and the investigation it triggers: listing, deliverable, pricing, policy or
  product.
- **assigns** the code onto the order's / case's `detail.root_cause` with the text it was
  read from and when, re-assigning only when that text changes.
- **triggers** on repetition: the same code on the same product `REPEAT_THRESHOLD` times in
  `REPEAT_WINDOW_DAYS` opens one `cx.repeated_cause:<product>:<code>` incident naming the
  investigation and its owner, and closes it, with the reading that says so, when the count
  falls back under the threshold.

Text is classified and never quoted into incidents: a buyer's words stay on their case.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

REPEAT_THRESHOLD = 3
REPEAT_WINDOW_DAYS = 90
PREFIX = "cx.repeated_cause:"

#: code -> (investigation kind, owning department, pattern)
REASONS: dict[str, tuple[str, str, str]] = {
    "expected_physical_item": ("listing", "listing",
                               r"thought (it|i was|this) (was|buying|bought)|not a (finished|"
                               r"physical)|expected (a|the) (finished|physical|real)|"
                               r"(it'?s|is) (only|just) a pattern|wanted the (finished|actual)"),
    "download_access": ("deliverable", "support",
                        r"download|can'?t open|cannot open|won'?t open|file (is )?(corrupt|"
                        r"blank|empty|missing)|no (file|pdf)|didn'?t receive"),
    "pattern_error": ("deliverable", "quality",
                      r"mistake|error|typo|wrong (count|stitch|number)|doesn'?t add up|"
                      r"(row|round|rnd) \d+ (is|was) wrong|stitch count"),
    "terminology_mismatch": ("listing", "listing", r"\b(uk|us|british|american) terms?\b|"
                                                   r"terminology"),
    "skill_mismatch": ("product", "creative",
                       r"too (hard|difficult|advanced|complicated)|beginner|over my head"),
    "sizing_or_gauge": ("product", "quality",
                        r"too (big|small|large|tight|loose)|\bgauge\b|tension|finished size"),
    "price_value": ("pricing", "cfo", r"too expensive|overpriced|not worth|cheaper|price"),
    "duplicate_purchase": ("policy", "support",
                           r"bought (it )?twice|duplicate|already (bought|purchased|own)|"
                           r"purchased (it )?(by mistake|accidentally)"),
    "changed_mind": ("policy", "support", r"changed (my )?mind|no longer (want|need)|"
                                          r"don'?t (want|need) it"),
}
UNRECORDED = "unrecorded"
GENERAL = "general_question"
#: Codes that are not a cause to investigate.
NOT_A_CAUSE = (UNRECORDED, GENERAL)


def classify(text: str, *, kind: str = "refund") -> dict:
    """(code, investigation, owner) for one piece of text. First matching code wins."""
    t = (text or "").lower()
    if t.strip():
        for code, (investigation, owner, pattern) in REASONS.items():
            if re.search(pattern, t):
                return {"code": code, "investigation": investigation, "owner": owner}
    if kind == "case" and t.strip():
        return {"code": GENERAL, "investigation": None, "owner": "support"}
    return {"code": UNRECORDED, "investigation": "owner_review", "owner": "owner"}


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


def _aware(at: datetime | None) -> datetime | None:
    if at is None:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def assign(db, *, now: datetime | None = None) -> dict:
    """Write a root cause onto every refunded/cancelled order and every support case."""
    from sqlalchemy import select

    from ..core.models import Order, SupportCase

    now = now or datetime.now(timezone.utc)
    assigned = {"orders": 0, "cases": 0}
    with db.session() as s:
        cases = {c.id: c for c in s.scalars(select(SupportCase))}
        for o in s.scalars(select(Order)):
            detail = dict(o.detail or {})
            state = str(detail.get("state") or "")
            if not (o.refunded or state in ("partially_refunded", "fully_refunded",
                                            "cancelled") or
                    float(((detail.get("refund") or {}).get("cad")) or 0.0) > 0):
                continue
            reasons = " | ".join((detail.get("refund") or {}).get("reasons") or [])
            basis = "etsy refund reason"
            if not reasons and o.support_case_id and o.support_case_id in cases:
                reasons, basis = cases[o.support_case_id].question or "", "linked support case"
            if not reasons:
                basis = "no reason recorded"
            prior = detail.get("root_cause") or {}
            if prior.get("from") == _digest(reasons) and prior.get("code"):
                continue
            kind = "cancellation" if state == "cancelled" else "refund"
            detail["root_cause"] = {**classify(reasons), "kind": kind, "basis": basis,
                                    "from": _digest(reasons), "assigned_at": now.isoformat()}
            o.detail = detail
            assigned["orders"] += 1
        for c in cases.values():
            detail = dict(c.detail or {})
            prior = detail.get("root_cause") or {}
            text = c.question or ""
            if prior.get("from") == _digest(text) and prior.get("code"):
                continue
            kind = "complaint" if (c.escalated or c.specialist in ("happiness", "escalate")) \
                else "case"
            detail["root_cause"] = {**classify(text, kind="case"), "kind": kind,
                                    "basis": "support case question",
                                    "from": _digest(text), "assigned_at": now.isoformat()}
            c.detail = detail
            assigned["cases"] += 1
    return assigned


def causes(db, *, now: datetime | None = None, days: int = REPEAT_WINDOW_DAYS) -> list[dict]:
    """Every assigned cause in the window: product, code, kind, owner, when. No text."""
    from sqlalchemy import select

    from ..core.models import Order, SupportCase

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    out = []
    linked: set[int] = set()
    with db.session() as s:
        for o in s.scalars(select(Order)):
            rc = (o.detail or {}).get("root_cause")
            if rc and _aware(o.at) and _aware(o.at) >= since:
                out.append({"source": "order", "id": o.id, "product": o.product_slug,
                            "at": _aware(o.at).isoformat(), **rc})
                if o.support_case_id:
                    # The refund and the case that led to it are one event, counted once.
                    linked.add(int(o.support_case_id))
        for c in s.scalars(select(SupportCase)):
            rc = (c.detail or {}).get("root_cause")
            if c.id in linked:
                continue
            if rc and _aware(c.at) and _aware(c.at) >= since:
                out.append({"source": "case", "id": c.id, "product": c.product_slug or "",
                            "at": _aware(c.at).isoformat(), **rc})
    return out


def repeated(db, *, now: datetime | None = None) -> dict:
    """Open/close one investigation incident per (product, code) at the threshold."""
    from ..ops import incident_lifecycle as lifecycle

    now = now or datetime.now(timezone.utc)
    counts: dict[tuple[str, str], list[dict]] = {}
    for c in causes(db, now=now):
        if c["code"] in NOT_A_CAUSE:
            continue
        counts.setdefault((c.get("product") or "(none)", c["code"]), []).append(c)
    hot = {k: v for k, v in counts.items() if len(v) >= REPEAT_THRESHOLD}
    opened = []
    with db.session() as s:
        for (product, code), rows in sorted(hot.items()):
            investigation, owner, _p = REASONS[code]
            _, new = lifecycle.open_or_restate(
                s, signature=f"{PREFIX}{product}:{code}", severity="P2",
                product_slug=None if product == "(none)" else product,
                summary=(f"{len(rows)} {code.replace('_', ' ')} causes on {product} in "
                         f"{REPEAT_WINDOW_DAYS} days: open a {investigation} investigation "
                         f"(owner: {owner})"),
                detail={"product": product, "code": code, "count": len(rows),
                        "investigation": investigation, "owner": owner,
                        "kinds": sorted({r["kind"] for r in rows}),
                        "refs": [f"{r['source']}:{r['id']}" for r in rows][:20]})
            if new:
                opened.append(f"{PREFIX}{product}:{code}")
        life = lifecycle.reconcile(
            s, PREFIX, lambda row: tuple(row.signature[len(PREFIX):].rsplit(":", 1)) in hot,
            resolution=(f"the {REPEAT_WINDOW_DAYS}-day count fell below {REPEAT_THRESHOLD} "
                        f"at {now.isoformat()}"))
    return {"opened": opened, "open": sorted(f"{p}:{c}" for p, c in hot),
            "resolved": life["resolved"], "threshold": REPEAT_THRESHOLD,
            "window_days": REPEAT_WINDOW_DAYS}


def run(db, *, now: datetime | None = None) -> dict:
    """Assign, then look for repetition. The daily entry point."""
    assigned = assign(db, now=now)
    rep = repeated(db, now=now)
    by_code: dict[str, int] = {}
    for c in causes(db, now=now):
        by_code[c["code"]] = by_code.get(c["code"], 0) + 1
    return {"assigned": assigned, "repeated": rep, "by_code": by_code}
