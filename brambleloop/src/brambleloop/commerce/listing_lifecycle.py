"""One listing lifecycle trail across every path that touches an Etsy listing (F-545).

Before this module the facts F-545 asks for existed in five places with five shapes:
`store.published` (create, images, files, read-back), `store.activated` /
`store.activate_incomplete` (activation), `etsy.exercise_draft_created` /
`etsy.exercise_draft_removed` (test listings), `etsy.listing_census` (what Etsy holds) and
nothing at all for a rollback. A reader had to know all of them to answer "what happened to
listing 123".

This module is the one shape:

- `record()` appends a `listing.lifecycle` row to the append-only audit log with the action,
  actor, evidence, remote id, before/after state and the rollback/cleanup result. New paths
  (the census drift observation, the rollback executor) write through it.
- `trail()` reads that row kind *and* the legacy rows, normalised into the same shape and
  ordered in time, so the history is unified without rewriting the producers that already
  audit correctly (the publish pipeline, activation, the exercise).
- `test_listings()` answers F-545's last sentence: every test listing is unmistakable (it is
  only ever created by the exercise path, and named by it) and is confirmed deleted only by a
  later read of Etsy -- an unmatched creation is reported as possibly stranded.

The audit log is append-only by design (core.models.AuditLog), which is what makes this a
trail rather than a status column.
"""
from __future__ import annotations

from typing import Any

ACTION = "listing.lifecycle"

#: The actions F-545 names, plus the observation and rollback this lane adds.
ACTIONS = ("create", "update", "image", "file", "activate", "deactivate", "delete",
           "observe_drift", "rollback", "cleanup")

#: Legacy audit actions read into the trail, and the lifecycle action each one means.
LEGACY = {
    "store.published": "create",
    "store.publish_incomplete": "create",
    "store.activated": "activate",
    "store.activate_incomplete": "activate",
    "etsy.exercise_draft_created": "create",
    "etsy.exercise_draft_removed": "delete",
}


class LifecycleRefused(ValueError):
    """A lifecycle row missing what makes it evidence."""


def record(db, *, action: str, listing_id: str, actor: str, evidence: str,
           before: dict | None = None, after: dict | None = None,
           result: str = "", slug: str | None = None, version: str | None = None,
           test_listing: bool = False, rollback: dict | None = None) -> dict:
    """Append one lifecycle row. Refuses a row with no listing, actor or evidence."""
    from ..core.models import AuditLog

    if action not in ACTIONS:
        raise LifecycleRefused(f"unknown lifecycle action {action!r}; one of {ACTIONS}")
    if not str(listing_id or "").strip():
        raise LifecycleRefused("a lifecycle row names the remote listing id")
    if not actor.strip() or not evidence.strip():
        raise LifecycleRefused("a lifecycle row names its actor and its evidence; a row "
                               "without them is a claim, not a trail")
    detail = {"action": action, "listing_id": str(listing_id), "evidence": evidence[:500],
              "before": before or {}, "after": after or {}, "result": result[:300],
              "slug": slug, "version": version, "test_listing": bool(test_listing),
              "rollback": rollback}
    with db.session() as s:
        row = AuditLog(actor=actor[:64], action=ACTION, artifact=f"etsy:{listing_id}",
                       detail=detail)
        s.add(row)
        s.flush()
        return {"id": row.id, **detail}


def _legacy_listing_id(detail: dict) -> str:
    return str(detail.get("etsy_listing_id") or detail.get("listing_id") or "")


def trail(db, listing_id: str | None = None, *, limit: int = 500) -> list[dict]:
    """Every lifecycle event, oldest first, from this module's rows and the legacy ones."""
    from sqlalchemy import or_, select

    from ..core.models import AuditLog

    out: list[dict] = []
    with db.session() as s:
        q = select(AuditLog).where(or_(AuditLog.action == ACTION,
                                       AuditLog.action.in_(tuple(LEGACY))))
        if listing_id is not None:
            q = q.where(or_(AuditLog.artifact == f"etsy:{listing_id}",
                            AuditLog.action.in_(tuple(LEGACY))))
        for row in s.scalars(q.order_by(AuditLog.id)):
            d = dict(row.detail or {})
            if row.action == ACTION:
                lid = str(d.get("listing_id") or "")
                event = {**d, "source_action": ACTION}
            else:
                lid = _legacy_listing_id(d)
                artifact = row.artifact or ""
                slug, _, version = artifact.partition("@")
                event = {
                    "action": LEGACY[row.action], "listing_id": lid,
                    "evidence": row.action, "before": {},
                    "after": ({"state_on_etsy": d.get("state_on_etsy")}
                              if "state_on_etsy" in d else
                              {"files_sent": [f.get("name") for f in
                                              d.get("files_sent") or []],
                               "images_uploaded": d.get("images_uploaded")}
                              if row.action.startswith("store.publish") else {}),
                    "result": ("verified" if row.action in ("store.published",
                                                            "store.activated")
                               else "incomplete" if row.action.startswith("store.")
                               else "confirmed_gone" if row.action.endswith("removed")
                               else "created"),
                    "slug": slug or None, "version": version or None,
                    "test_listing": row.action.startswith("etsy.exercise"),
                    "rollback": None, "source_action": row.action}
            if not lid or (listing_id is not None and lid != str(listing_id)):
                continue
            event.update(id=row.id, at=row.at.isoformat() if row.at else None,
                         actor=row.actor)
            out.append(event)
    return out[-limit:]


def test_listings(db) -> dict:
    """Every exercise listing: created, confirmed deleted by a read, or possibly stranded."""
    events = [e for e in trail(db, limit=100000) if e.get("test_listing")]
    created: dict[str, dict] = {}
    deleted: set[str] = set()
    for e in events:
        if e["action"] == "create":
            created.setdefault(e["listing_id"], e)
        elif e["action"] == "delete" and e.get("result") == "confirmed_gone":
            deleted.add(e["listing_id"])
    stranded = sorted(set(created) - deleted)
    return {"created": len(created), "confirmed_deleted": len(deleted & set(created)),
            "stranded": stranded,
            "rule": ("a test listing is confirmed deleted only by a later read of Etsy "
                     "(etsy.exercise_draft_removed); a creation without one is stranded")}


def summary(db) -> dict[str, Any]:
    """Counts by action, for the estate view. No customer content."""
    events = trail(db, limit=100000)
    counts: dict[str, int] = {}
    for e in events:
        counts[e["action"]] = counts.get(e["action"], 0) + 1
    return {"events": len(events), "by_action": counts, "test_listings": test_listings(db)}


# ---- W4-C12 F-034: the new-listing learning window -----------------------------------------
#
# F-034: "Schedule evidence capture during Etsy's temporary new-listing boost." A newly
# activated listing gets a temporary visibility boost (the same fact `publish.release_gates.
# renewal_decision` cites), so its first two weeks are the one period whose evidence cannot be
# reconstructed later. The schedule starts only from a VERIFIED activation in the trail -- a
# listing that is not live has no boost -- and each capture is a dated record of what was read
# (a Stats export, the listing page, the census), never a number this module produces.

WINDOW_ACTION = "listing.learning_window"
WINDOW_DAYS = (0, 1, 3, 7, 14)
WINDOW_BASIS = ("Etsy states new and renewed listings get a temporary boost and publishes no "
                "duration; 14 days is this company's assumption, labelled as one")
CAPTURE_SOURCES = ("stats_export", "listing_page", "census", "search_visibility")


def _activated_at(db, listing_id: str):
    from datetime import datetime, timezone

    for e in trail(db, str(listing_id)):
        if e["action"] == "activate" and e.get("result") == "verified" and e.get("at"):
            at = datetime.fromisoformat(e["at"])
            return at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return None


def learning_window(db, listing_id: str, *, now=None) -> dict:
    """The capture schedule for one listing's boost window, and which captures are on file."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    start = _activated_at(db, listing_id)
    if start is None:
        return {"listing_id": str(listing_id), "state": "NOT_LIVE",
                "why": "no verified activation in the lifecycle trail: no boost to capture",
                "schedule": []}
    with db.session() as s:
        done = {int((a.detail or {}).get("day")): dict(a.detail or {})
                for a in s.scalars(select(AuditLog).where(
                    AuditLog.action == WINDOW_ACTION,
                    AuditLog.artifact == f"etsy:{listing_id}"))}
    schedule = []
    for d in WINDOW_DAYS:
        due = start + timedelta(days=d)
        cap = done.get(d)
        schedule.append({"day": d, "due_at": due.isoformat(),
                         "state": ("captured" if cap else "due" if due <= now
                                   else "scheduled"),
                         **({"capture": cap} if cap else {})})
    return {"listing_id": str(listing_id), "state": "WINDOW",
            "activated_at": start.isoformat(), "schedule": schedule, "basis": WINDOW_BASIS,
            "missed": [x["day"] for x in schedule if x["state"] == "due"
                       and now - datetime.fromisoformat(x["due_at"]) > timedelta(days=2)]}


def due_captures(db, listing_ids, *, now=None) -> list[dict]:
    """Every capture due now across these listings (for a cadence or an owner card)."""
    out = []
    for lid in listing_ids:
        w = learning_window(db, lid, now=now)
        out += [{"listing_id": str(lid), **x} for x in w["schedule"] if x["state"] == "due"]
    return out


def record_capture(db, listing_id: str, *, day: int, source: str, evidence: str,
                   observed_at, values: dict | None = None, actor: str = "owner") -> dict:
    """File one window capture: what was read, from where, when. Refuses a capture early."""
    from datetime import datetime, timedelta, timezone

    from ..core.models import AuditLog

    if day not in WINDOW_DAYS:
        raise LifecycleRefused(f"day {day} is not a window capture day {WINDOW_DAYS}")
    if source not in CAPTURE_SOURCES:
        raise LifecycleRefused(f"source {source!r} is not one of {CAPTURE_SOURCES}")
    if not str(evidence or "").strip():
        raise LifecycleRefused("a capture names its evidence (an export file, a page read)")
    start = _activated_at(db, listing_id)
    if start is None:
        raise LifecycleRefused("the listing has no verified activation; nothing to capture")
    at = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
    if at < start + timedelta(days=day) or at > datetime.now(timezone.utc):
        raise LifecycleRefused("a capture is observed on or after its due day, never before "
                               "it and never in the future")
    detail = {"day": day, "source": source, "evidence": evidence[:300],
              "observed_at": at.isoformat(), "values": dict(values or {})}
    with db.session() as s:
        s.add(AuditLog(actor=actor[:64], action=WINDOW_ACTION, artifact=f"etsy:{listing_id}",
                       detail=detail))
    return {"listing_id": str(listing_id), **detail}


# ---- W4-C12 F-554: the bulk listing operations guard ---------------------------------------
#
# F-554: "Support safe bulk edits/renewals only with preview, affected-count proof, invariant
# checks and rollback plan. Never bulk-edit Product Truth, safety or legal fields from a
# heuristic." No bulk path exists, and this adds none: `bulk_plan` is the guard any future one
# must pass, and it writes nothing to Etsy. A plan is only a plan: it carries the preview, the
# count the caller expected and the count that would change, the invariant results, and the
# before-snapshot it would roll back to. `verify_plan` refuses to let a plan run against a
# listing estate that moved after it was previewed.

BULK_ACTION = "listing.bulk_plan"
BULK_OPERATIONS = ("edit", "renew")
#: Fields a bulk operation may never touch: Product Truth (what the product is), safety and
#: legal. They change only through a certified release, one listing at a time.
PROTECTED_FIELDS = frozenset({
    "description", "materials", "who_made", "when_made", "is_supply", "type", "taxonomy_id",
    "is_digital", "file_data", "production_partner_ids", "is_customizable",
    "is_personalizable", "personalization_instructions", "processing_min", "processing_max",
    "shipping_profile_id", "return_policy_id", "tax", "item_weight", "item_dimensions_unit",
    "safety", "legal"})
BULK_FIELDS = frozenset({"tags", "title", "price", "quantity", "should_auto_renew",
                         "featured_rank", "shop_section_id", "state"})


def _fp(obj) -> str:
    import hashlib
    import json

    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def bulk_plan(db, *, operation: str, changes: dict, current: dict[str, dict],
              expected_count: int, reason: str, actor: str,
              renewal_reasons: dict[str, str] | None = None) -> dict:
    """Preview a bulk operation and prove it safe, or refuse. Writes no listing."""
    from ..core.models import AuditLog

    if operation not in BULK_OPERATIONS:
        raise LifecycleRefused(f"{operation!r} is not a bulk operation {BULK_OPERATIONS}")
    if not reason.strip() or not actor.strip():
        raise LifecycleRefused("a bulk plan names its reason and its actor")
    fields = {f for ch in changes.values() for f in (ch or {})}
    protected = sorted(fields & PROTECTED_FIELDS)
    if protected:
        raise LifecycleRefused(
            f"{protected} are Product Truth, safety or legal fields: never bulk-edited, and "
            f"never from a heuristic; they change through a certified release (F-554)")
    unknown = sorted(fields - BULK_FIELDS)
    if unknown:
        raise LifecycleRefused(f"{unknown} are not fields a bulk operation may set")
    problems, preview, rollback = [], [], {}
    missing = sorted(set(changes) - set(current))
    if missing:
        problems.append(f"listings {missing[:10]} are not in the current estate snapshot")
    for lid, ch in sorted(changes.items()):
        before = dict(current.get(lid) or {})
        diff = {f: {"from": before.get(f), "to": v} for f, v in (ch or {}).items()
                if before.get(f) != v}
        if operation == "renew":
            from ..publish.release_gates import renewal_decision

            why = (renewal_reasons or {}).get(lid, "")
            verdict = renewal_decision(reason=why, listing_state=str(before.get("state", "")),
                                       material_change=why if why.startswith("material") else "")
            if not verdict["allowed"]:
                problems.append(f"{lid}: {verdict['why']}")
        if "tags" in diff and len(list((ch or {}).get("tags") or [])) > 13:
            problems.append(f"{lid}: more than 13 tags")
        if "price" in diff and float((ch or {}).get("price") or 0) <= 0:
            problems.append(f"{lid}: a price must be positive")
        if diff:
            preview.append({"listing_id": lid, "diff": diff})
            rollback[lid] = {f: before.get(f) for f in diff}
    affected = len(preview)
    if affected != int(expected_count):
        problems.append(f"the operation would change {affected} listing(s); the caller "
                        f"expected {expected_count}")
    plan = {"operation": operation, "reason": reason[:300], "actor": actor[:64],
            "affected": affected, "expected": int(expected_count), "preview": preview,
            "rollback": rollback, "invariants": problems, "safe": not problems,
            "estate_fingerprint": _fp({k: current.get(k) for k in sorted(changes)})}
    plan["fingerprint"] = _fp({k: plan[k] for k in ("operation", "preview", "rollback")})
    with db.session() as s:
        s.add(AuditLog(actor=actor[:64], action=BULK_ACTION, artifact=f"bulk:{operation}",
                       detail={k: plan[k] for k in ("operation", "reason", "affected",
                                                     "expected", "safe", "invariants",
                                                     "fingerprint", "estate_fingerprint")}))
    return plan


def verify_plan(plan: dict, current: dict[str, dict]) -> dict:
    """Before any execution: the plan is safe and the estate is still what was previewed."""
    if not plan.get("safe"):
        return {"may_run": False, "why": "; ".join(plan.get("invariants") or [])[:400]}
    rollback = plan.get("rollback") or {}
    drifted = [lid for lid in sorted(rollback)
               if {f: (current.get(lid) or {}).get(f) for f in rollback[lid]} != rollback[lid]]
    if drifted:
        return {"may_run": False, "why": f"listings {drifted[:10]} changed since the preview"}
    return {"may_run": True, "why": "previewed, counted, invariants hold, estate unchanged",
            "rollback": rollback}


# ---- W4-C12 F-555: renewal economics ------------------------------------------------------
#
# F-555: "Measure manual/automatic renewal economics and performance. Renew because evidence
# supports the listing, not merely because expiry is approaching." The renewal fee is the fee
# schedule's modelled figure; the evidence is the listing's measured outcome periods. A
# listing with no measured period is UNMEASURED and is never auto-renewed on hope; a listing
# whose measured contribution per renewal period does not cover the fee is let expire; expiry
# approaching changes nothing in either direction. Renewal itself still passes
# `publish.release_gates.renewal_decision` (expired, or a material change) -- never recency.

RENEWAL_MIN_VISITS = 30


def renewal_economics(db, *, slug: str, net_per_sale_cad: float, usd_per_cad: float,
                      days_to_expiry: float | None = None, mode: str = "") -> dict:
    """Whether the evidence supports renewing this listing, with the arithmetic shown."""
    from datetime import date

    from sqlalchemy import select

    from ..core.models import ListingOutcome
    from . import fee_schedule

    try:
        fee = fee_schedule.listing_fee_cad(usd_per_cad)
    except Exception as e:  # noqa: BLE001 - an unquotable fee is unknown, never zero
        return {"slug": slug, "decision": "UNMEASURED", "auto_renew": False,
                "why": f"the renewal fee is not quotable: {e}"[:200]}
    months = fee_schedule.LISTING_RENEWAL_MONTHS or 4
    with db.session() as s:
        rows = [(r.period_start, r.period_end, int(r.visits or 0), r.orders)
                for r in s.scalars(select(ListingOutcome).where(
                    ListingOutcome.product_slug == slug))]
    measured = [r for r in rows if r[3] is not None]
    visits = sum(r[2] for r in measured)
    orders = sum(int(r[3]) for r in measured)
    days = sum(max(1, (date.fromisoformat(r[1]) - date.fromisoformat(r[0])).days + 1)
               for r in measured) if measured else 0
    out = {"slug": slug, "renewal_fee_cad": fee, "renewal_months": months,
           "measured_days": days, "visits": visits, "orders": orders, "mode": mode or None,
           "days_to_expiry": days_to_expiry,
           "rule": "expiry approaching is not evidence; measured contribution is"}
    if not measured or visits < RENEWAL_MIN_VISITS:
        return {**out, "decision": "UNMEASURED", "auto_renew": False,
                "why": (f"{visits} measured visit(s) (needs {RENEWAL_MIN_VISITS}): the "
                        f"evidence cannot yet support a renewal, so none is automatic")}
    per_day = orders * float(net_per_sale_cad) / days
    expected = round(per_day * months * 30.4, 4)
    renew = expected > fee
    return {**out, "expected_contribution_cad": expected,
            "decision": "RENEW" if renew else "LET_EXPIRE", "auto_renew": renew,
            "why": (f"{orders} order(s) in {days} measured day(s) at CA${net_per_sale_cad:.2f} "
                    f"net project CA${expected:.2f} over {months} months against a "
                    f"CA${fee:.2f} fee")}
