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


# ---- W4-C13 F-597: the storefront change budget --------------------------------------------
#
# F-597: "Limit simultaneous storefront/listing experiments so causal attribution remains
# possible. Emergency policy/safety fixes bypass the experiment budget but are separately
# tagged." An experiment is opened before it is applied and closed when it is concluded or
# reverted; the budget counts the open ones. At most `EXPERIMENT_BUDGET` run at once, and never
# two on the same surface (a listing, the shop banner, a section). An emergency -- a policy,
# safety, truth or incident fix -- is always allowed, is tagged `emergency`, and does not use
# the budget; experiments overlapping it are marked confounded so their reading is not
# attributed to them.

CHANGE_ACTION = "storefront.change_opened"
CLOSE_ACTION = "storefront.change_closed"
EXPERIMENT_BUDGET = 2
EMERGENCY_KINDS = ("policy", "safety", "truth", "incident")


class ChangeRefused(ValueError):
    """An experiment over the budget, or a change without what makes it attributable."""


# Stored in `operating_readings` (never pruned by `ops.retention`): an open experiment that
# retention forgot would free budget it still uses.
def _put(s, kind: str, detail: dict) -> None:
    import uuid

    from ..core.models import OperatingReading

    s.add(OperatingReading(kind=kind, period_key=uuid.uuid4().hex[:20], payload=detail,
                           at=datetime.now(timezone.utc)))


def _changes(db) -> tuple[dict[str, dict], set[str]]:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    opened, closed = {}, set()
    with db.session() as s:
        for a in s.scalars(select(OperatingReading).where(OperatingReading.kind.in_(
                (CHANGE_ACTION, CLOSE_ACTION))).order_by(OperatingReading.id)):
            d = dict(a.payload or {})
            if a.kind == CHANGE_ACTION:
                opened[d["key"]] = {**d, "at": a.at.isoformat()}
            else:
                closed.add(d["key"])
    return opened, closed


def change_budget(db) -> dict:
    opened, closed = _changes(db)
    live = [c for k, c in opened.items() if k not in closed]
    exps = [c for c in live if c["kind"] == "experiment"]
    return {"budget": EXPERIMENT_BUDGET, "experiments_open": len(exps),
            "available": max(0, EXPERIMENT_BUDGET - len(exps)),
            "experiments": exps, "emergencies": [c for c in live if c["kind"] == "emergency"]}


def open_change(db, *, key: str, surface: str, kind: str, reason: str, by: str,
                emergency_kind: str = "") -> dict:
    """Open one storefront change before it is applied; refuse an experiment over budget."""
    if kind not in ("experiment", "emergency"):
        raise ChangeRefused("a storefront change is an experiment or an emergency fix")
    if not key.strip() or not surface.strip() or len((reason or "").split()) < 3:
        raise ChangeRefused("a change names itself, the surface it touches and why")
    if kind == "emergency" and emergency_kind not in EMERGENCY_KINDS:
        raise ChangeRefused(f"an emergency is one of {EMERGENCY_KINDS}; anything else is an "
                            f"experiment and uses the budget")
    opened, closed = _changes(db)
    if key in opened:
        raise ChangeRefused(f"change {key!r} is already recorded")
    b = change_budget(db)
    confounds: list[str] = []
    if kind == "experiment":
        same = [c["key"] for c in b["experiments"] if c["surface"] == surface]
        if same:
            raise ChangeRefused(f"{surface} already carries experiment {same[0]}: two at once "
                                f"cannot be told apart")
        if b["available"] <= 0:
            raise ChangeRefused(f"{b['experiments_open']} experiments are open (budget "
                                f"{EXPERIMENT_BUDGET}); conclude one first so each result "
                                f"stays attributable (F-597)")
    else:
        confounds = [c["key"] for c in b["experiments"] if c["surface"] == surface]
    detail = {"key": key, "surface": surface, "kind": kind, "reason": reason[:300],
              "by": by[:60], "emergency_kind": emergency_kind or None,
              "confounds": confounds}
    with db.session() as s:
        _put(s, CHANGE_ACTION, detail)
    return detail


def close_change(db, key: str, *, outcome: str, by: str) -> dict:
    opened, closed = _changes(db)
    if key not in opened or key in closed:
        raise ChangeRefused(f"no open change {key!r}")
    with db.session() as s:
        _put(s, CLOSE_ACTION, {"key": key, "outcome": outcome[:300], "by": by[:60]})
    return {"key": key, "closed": True}
