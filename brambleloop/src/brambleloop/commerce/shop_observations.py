"""The owner's dated readings of Shop Manager pages no API exposes (K8: F-568, F-585, F-592).

Etsy publishes no API for Policy Violations, Shared Access, installed Apps or most of
Settings > Options. `intel.etsy_surfaces` already says so and asks the owner for "a dated
statement of the page's contents, recorded against this key". Nothing could record one. This
module is that intake, and the rule it keeps is the registry's: **a statement closes an owner
action only when it is evidence** -- dated, complete, and saying what the page shows.

- `record()` appends one observation (`etsy.shop_observation` audit row, append-only) with the
  page key, when it was read, whether the reading is complete, the structured values and the
  owner's sentence. Customer content does not belong here and is refused by length/shape.
- Recording closes or reopens the seeded `etsy_surface:<key>` owner action on its merits:
  an empty Shared Access / Apps / Policy Violations page closes the check; anything listed
  keeps it open and becomes an incident (shop_security, policy_violations).
- `latest()` is what the daily handlers read. An observation older than the surface tolerates
  is STALE, and no observation at all is UNOBSERVED -- never "fine".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ACTION = "etsy.shop_observation"

#: The pages this intake accepts, the owner action a complete reading evidences, and how
#: old a reading may be before it is stale.
PAGES: dict[str, dict[str, Any]] = {
    "policy_violations": {"owner_action": "policy_violations_check", "max_age_days": 7,
                          "values": "items: list of {source_text, listing_id?, kind, "
                                    "deadline?}; [] when the page is empty"},
    "shared_access": {"owner_action": "shared_access_empty", "max_age_days": 30,
                      "values": "people: list of {label, permissions}; [] when empty"},
    "apps": {"owner_action": "apps_none_installed", "max_age_days": 30,
             "values": "apps: list of installed app names; [] when none"},
    "options": {"owner_action": None, "max_age_days": 30,
                "values": "controls: {control_key: value as shown}; labels: every control "
                          "label on the page"},
}

LIST_FIELD = {"policy_violations": "items", "shared_access": "people", "apps": "apps"}


class ObservationRefused(ValueError):
    """Not evidence: undated, incomplete where completeness is required, or malformed."""


def _parse(at) -> datetime:
    if isinstance(at, datetime):
        value = at
    else:
        try:
            value = datetime.fromisoformat(str(at or "").replace("Z", "+00:00"))
        except ValueError as e:
            raise ObservationRefused("observed_at must be an ISO 8601 date-time: an undated "
                                     "statement is not evidence") from e
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def record(db, *, page: str, observed_at, complete: bool, values: dict, statement: str,
           recorded_by: str = "owner", now: datetime | None = None) -> dict:
    """Append one dated observation and act on it. Returns what it closed and opened."""
    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    if page not in PAGES:
        raise ObservationRefused(f"unknown page {page!r}; one of {sorted(PAGES)}")
    when = _parse(observed_at)
    if when > now:
        raise ObservationRefused("observed_at is in the future")
    if not isinstance(complete, bool):
        raise ObservationRefused("complete must be true or false: only a complete reading "
                                 "may close anything")
    if not isinstance(values, dict):
        raise ObservationRefused("values must be an object")
    if not str(statement or "").strip():
        raise ObservationRefused("a statement of what the page shows is required")
    field = LIST_FIELD.get(page)
    if field is not None and not isinstance(values.get(field), list):
        raise ObservationRefused(f"values.{field} must be a list ([] when the page is empty)")
    if page == "options" and not isinstance(values.get("controls"), dict):
        raise ObservationRefused("values.controls must be an object of control -> value")
    detail = {"page": page, "observed_at": when.isoformat(), "complete": complete,
              "values": values, "statement": str(statement)[:500]}
    with db.session() as s:
        row = AuditLog(actor=recorded_by[:64], action=ACTION, artifact=f"etsy_page:{page}",
                       detail=detail)
        s.add(row)
        s.flush()
        obs_id = row.id
    out: dict[str, Any] = {"id": obs_id, "page": page, "complete": complete,
                           "owner_action": None}
    key = PAGES[page]["owner_action"]
    if key and complete:
        empty = not values.get(field)
        out["owner_action"] = {"key": f"etsy_surface:{key}",
                               "changed": _set_action(db, key, done=empty),
                               "done": empty}
    if page == "policy_violations":
        from . import policy_violations

        out["policy_violations"] = policy_violations.apply_observation(
            db, observation_id=obs_id, observed_at=when, complete=complete,
            items=values.get("items") or [], now=now)
    return out


def _set_action(db, key: str, *, done: bool) -> bool:
    from sqlalchemy import desc, select

    from ..core.models import OwnerAction

    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"etsy_surface:{key}")
            .order_by(desc(OwnerAction.id)).limit(1))
        if row is None or bool(row.done) == done:
            return False
        row.done = done
        return True


def latest(db, page: str, *, now: datetime | None = None) -> dict:
    """The newest observation of a page, with its evidence state. Never a bare None."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION,
                                              AuditLog.artifact == f"etsy_page:{page}")
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return {"page": page, "state": "UNOBSERVED", "observation": None}
        detail = dict(row.detail or {})
        detail["id"] = row.id
    age = (now - _parse(detail["observed_at"])).total_seconds() / 86400.0
    max_age = PAGES.get(page, {}).get("max_age_days") or 30
    state = "FRESH" if age <= max_age else "STALE"
    if not detail.get("complete"):
        state = "INCOMPLETE"
    return {"page": page, "state": state, "age_days": round(age, 2), "observation": detail}
