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
