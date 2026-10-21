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
# W4-LISTREADY (review F7): pages whose reading is the owner's own attestation -- identity
# verification and the tax position (KYC), and where buyer messages reach -- are accepted only
# from the owner's Command Center session with step-up (`POST /api/cc/etsy/shop-observation`),
# never from the shared operator credential.
OWNER_ATTESTED_PAGES = frozenset({"messages", "legal_and_tax"})

PAGES: dict[str, dict[str, Any]] = {
    "policy_violations": {"owner_action": "policy_violations_check", "max_age_days": 7,
                          "values": "items: list of {source_text, listing_id?, kind, "
                                    "deadline?}; [] when the page is empty"},
    "shared_access": {"owner_action": "shared_access_empty", "max_age_days": 30,
                      "values": "people: list of {label, permissions}; [] when empty"},
    "apps": {"owner_action": "apps_none_installed", "max_age_days": 30,
             "values": "apps: list of installed app names; [] when none"},
    # W4-FIRSTSALE2: two first-sale surfaces Etsy publishes no API for at all (no messaging
    # resource; no identity, entity or tax-registration resource). Evidenced only by the
    # owner's dated, complete reading; `SATISFIED` decides whether it closes the action.
    "messages": {"owner_action": "messages_watch", "max_age_days": 30,
                 "values": "notifications_inbox: the address Etsy message notifications go "
                           "to (non-empty); reply_window_hours: the agreed reply window (> 0)"},
    "legal_and_tax": {"owner_action": "legal_and_tax_setup", "max_age_days": 90,
                      "values": "identity_verified: bool (Etsy shows verification complete); "
                                "tax_position: the GST/HST position chosen, as stated "
                                "(non-empty); decided_on: ISO date the position was chosen"},
    # LAUNCHPREP E2: whether Policy settings shows an editable delivery text box for this
    # digital-only shop. A dated `false` is the evidence that lets a blank policy_shipping read
    # not applicable (`intel.etsy_surfaces`); `true` keeps the check as it is.
    "delivery_policy": {"owner_action": None, "max_age_days": 90,
                        "values": "editable_delivery_box: bool (true if Policy settings shows a "
                                  "delivery/shipping text box you can type in; false if only "
                                  "Etsy's fixed 'Instant downloads' policy is shown)"},
    "options": {"owner_action": None, "max_age_days": 30,
                "values": "controls: {control_key: value as shown}; labels: every control "
                          "label on the page"},
}

LIST_FIELD = {"policy_violations": "items", "shared_access": "people", "apps": "apps"}


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


#: Pages whose reading closes its owner action only when the values say the requirement is
#: met (not when a list is empty). Only the owner's stated values are read; nothing inferred.
SATISFIED = {
    "messages": lambda v: _text(v.get("notifications_inbox"))
    and isinstance(v.get("reply_window_hours"), (int, float))
    and not isinstance(v.get("reply_window_hours"), bool) and v["reply_window_hours"] > 0,
    "legal_and_tax": lambda v: v.get("identity_verified") is True
    and _text(v.get("tax_position")) and _text(v.get("decided_on")),
}


def satisfied(page: str, observation: dict | None) -> bool | None:
    """True/False for a complete reading of a SATISFIED page; None when there is none."""
    if page not in SATISFIED or not observation or not observation.get("complete"):
        return None
    return bool(SATISFIED[page](observation.get("values") or {}))


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
    if page == "messages" and not (_text(values.get("notifications_inbox"))
                                   and "reply_window_hours" in values):
        raise ObservationRefused("values.notifications_inbox (text) and "
                                 "values.reply_window_hours are required")
    if page == "delivery_policy" and not isinstance(values.get("editable_delivery_box"), bool):
        raise ObservationRefused("values.editable_delivery_box must be true or false")
    if page == "legal_and_tax":
        if not isinstance(values.get("identity_verified"), bool):
            raise ObservationRefused("values.identity_verified must be true or false")
        if values.get("decided_on"):
            try:
                decided = datetime.fromisoformat(str(values["decided_on"]))
            except ValueError as e:
                raise ObservationRefused("values.decided_on must be an ISO date") from e
            # W4-LISTREADY (review F7): a decision cannot be dated after the reading of it.
            if (decided if decided.tzinfo else decided.replace(tzinfo=timezone.utc)) > now:
                raise ObservationRefused("values.decided_on is in the future")
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
    if key and complete and page in SATISFIED:
        done = bool(SATISFIED[page](values))
        out["owner_action"] = {"key": f"etsy_surface:{key}",
                               "changed": _set_action(db, key, done=done), "done": done}
    elif key and complete:
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
