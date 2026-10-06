"""The first-response clock on recorded buyer messages (F-043).

Etsy's seller standard is a first response within 48 hours (`gates.policy_knowledge` records
it as text). Until this module nothing measured how long a recorded buyer message had been
waiting: `support.triage` set the refund/case window and enqueued a draft, and a draft held
in shadow mode is not a response anybody received.

What this does, on every `support.triage` run:

- For every recorded **buyer message** (a `SupportCase` that came in through `intake`, so
  `detail.awaiting_reply` is set) with no reply recorded as sent, it computes the hours since
  the buyer wrote (`case.at`, which the owner-recorded intake sets to the message's own time).
- At **24h** it raises one owner action (`support.first_response:case:<id>`) and one P2
  incident; at **36h** the incident becomes P1 and the action says so; at **48h** the
  standard is breached and the incident says that too. One row per case, restated, never
  duplicated.
- When the reply is recorded as sent (`record_reply_sent`, or `case.sent`) or the case is
  resolved, the action closes and the incident resolves, on that evidence.

What it does not do: read Etsy Messages. There is no Etsy messages API; a buyer message
enters only when the owner records it (`record_buyer_message`, the operator-authenticated
`/api/support/messages` route). An unrecorded message is not watched, and the watch says
how many messages it is watching so that "no alerts" can never be read as "no buyers waiting".
"""
from __future__ import annotations

from datetime import datetime, timezone

STANDARD_HOURS = 48.0
WARN_HOURS = 24.0
ESCALATE_HOURS = 36.0

KEY_PREFIX = "support.first_response:"
SIGNATURE_PREFIX = "support.first_response:"
OWNER_SOURCE = "owner_recorded"


class MessageRefused(ValueError):
    """A recorded message or reply the watch cannot accept as stated."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse(at: str | datetime | None, *, now: datetime) -> datetime:
    if at is None or at == "":
        return now
    if isinstance(at, datetime):
        value = _aware(at)
    else:
        try:
            value = _aware(datetime.fromisoformat(str(at).replace("Z", "+00:00")))
        except ValueError as exc:
            raise MessageRefused(f"{at!r} is not an ISO 8601 time") from exc
    if value > now:
        raise MessageRefused("a message cannot have been received in the future")
    return value


def key_for(case_id: int) -> str:
    return f"{KEY_PREFIX}case:{case_id}"


# How long an identical message with no stated receipt time is treated as the same message.
# With `received_at` stated the key is exact and there is no window.
DUPLICATE_WINDOW_HOURS = 24.0


def intake_key(customer_ref: str, message: str, received_at: datetime | None) -> str:
    """The idempotency key of one recorded buyer message: who, when, and a hash of what."""
    import hashlib

    content = hashlib.sha256(" ".join(str(message).split()).encode("utf-8")).hexdigest()
    when = received_at.astimezone(timezone.utc).isoformat() if received_at else "-"
    return hashlib.sha256(f"{customer_ref}\x1f{when}\x1f{content}".encode("utf-8")).hexdigest()


def _existing_case(db, customer_ref: str, key: str, *, explicit_time: bool, now: datetime):
    """The case this exact message was already recorded as, if any.

    With a stated receipt time the key is exact. Without one, the same words from the same
    buyer are the same message while that case is unanswered and under a day old -- after
    that, the buyer saying it again is a new message.
    """
    from sqlalchemy import select

    from ..core.models import SupportCase

    with db.session() as s:
        for case in s.scalars(select(SupportCase).where(SupportCase.customer_ref == customer_ref)
                              .order_by(SupportCase.id.desc())):
            detail = case.detail or {}
            if detail.get("intake_key") != key:
                continue
            if not explicit_time:
                try:
                    recorded = _aware(datetime.fromisoformat(str(detail.get("recorded_at"))))
                except ValueError:
                    continue
                if (_answered(case) or (now - recorded).total_seconds() / 3600.0
                        > DUPLICATE_WINDOW_HOURS):
                    continue
            s.expunge(case)
            return case
    return None


def record_buyer_message(db, *, customer_ref: str, message: str, received_at=None,
                         product_slug: str | None = None, version: str | None = None,
                         channel: str = "etsy_messages", now: datetime | None = None) -> dict:
    """The owner records a buyer message they read in Etsy (no API delivers them).

    The case's clock starts at `received_at` -- when the buyer wrote, as the owner read it
    -- not when it was typed in here, so a message recorded a day late is already a day old.
    """
    from ..core.models import SupportCase
    from .department import CustomerExperience

    now = now or datetime.now(timezone.utc)
    if not str(customer_ref or "").strip() or not str(message or "").strip():
        raise MessageRefused("customer_ref and message are required")
    at = _parse(received_at, now=now)
    ref = str(customer_ref)[:80]
    key = intake_key(ref, str(message), at if received_at not in (None, "") else None)
    existing = _existing_case(db, ref, key, explicit_time=received_at not in (None, ""),
                              now=now)
    if existing is not None:
        # A3-13: the same message recorded twice (a retry, a double tap) is one case and one
        # first-response card, not two. The caller is told it was a duplicate.
        return {"case_id": existing.id, "duplicate": True,
                "received_at": _aware(existing.at).isoformat() if existing.at else None,
                "hours_waiting": (round((now - _aware(existing.at)).total_seconds() / 3600.0, 2)
                                  if existing.at else None)}
    case_id = CustomerExperience(db).intake(customer_ref=str(customer_ref)[:80],
                                            message=str(message), product_slug=product_slug,
                                            version=version, source=OWNER_SOURCE)
    with db.session() as s:
        case = s.get(SupportCase, case_id)
        case.at = at
        case.detail = {**dict(case.detail or {}), "channel": channel,
                       "received_at": at.isoformat(), "recorded_at": now.isoformat(),
                       "intake_key": key}
    return {"case_id": case_id, "duplicate": False, "received_at": at.isoformat(),
            "hours_waiting": round((now - at).total_seconds() / 3600.0, 2)}


def record_reply_sent(db, case_id: int, *, sent_at=None, now: datetime | None = None) -> dict:
    """The owner records that the reply reached the buyer. Stops the clock for that case."""
    from ..core.models import SupportCase

    now = now or datetime.now(timezone.utc)
    at = _parse(sent_at, now=now)
    with db.session() as s:
        case = s.get(SupportCase, int(case_id))
        if case is None:
            raise MessageRefused(f"no support case {case_id}")
        received = _aware(case.at) if case.at else None
        if received is not None and at < received:
            raise MessageRefused("a reply cannot have been sent before the message arrived")
        detail = dict(case.detail or {})
        if detail.get("first_response_at"):
            raise MessageRefused(f"case {case_id} already has a first response recorded at "
                                 f"{detail['first_response_at']}")
        detail.update({"first_response_at": at.isoformat(), "awaiting_reply": False})
        case.detail = detail
        case.sent = True
    return {"case_id": int(case_id), "first_response_at": at.isoformat(),
            "hours_to_first_response": (round((at - received).total_seconds() / 3600.0, 2)
                                        if received else None)}


def _answered(case) -> bool:
    detail = case.detail or {}
    return bool(case.sent or case.resolved or detail.get("first_response_at"))


def watch(db, *, now: datetime | None = None) -> dict:
    """Raise, escalate or close the first-response alert for every recorded buyer message."""
    from sqlalchemy import select

    from ..core.models import Incident, OwnerAction, SupportCase
    from ..ops import incident_lifecycle as lifecycle

    now = now or datetime.now(timezone.utc)
    raised, escalated, breached, closed, watching = [], [], [], [], []
    with db.session() as s:
        cases = [c for c in s.scalars(select(SupportCase)) if (c.detail or {}).get(
            "awaiting_reply") is not None or (c.detail or {}).get("first_response_at")]
        for case in cases:
            key = key_for(case.id)
            signature = f"{SIGNATURE_PREFIX}case:{case.id}"
            action = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == key,
                OwnerAction.done == False))  # noqa: E712
            if _answered(case):
                if action is not None:
                    from ..ops import owner_queue
                    owner_queue.close(action, owner_queue.SATISFIED,
                                      "the support case has a recorded response")
                    closed.append(case.id)
                lifecycle.resolve_signatures(
                    s, [signature], now=now,
                    resolution=("first response recorded at "
                                f"{(case.detail or {}).get('first_response_at') or 'case close'}"))
                continue
            watching.append(case.id)
            hours = (now - _aware(case.at)).total_seconds() / 3600.0
            if hours < WARN_HOURS:
                continue
            left = STANDARD_HOURS - hours
            stage = ("breached" if left <= 0 else
                     "escalated" if hours >= ESCALATE_HOURS else "warning")
            severity = "P2" if stage == "warning" else "P1"
            # A3-04: the case id only. Owner-queue text is rendered on the dashboard, the
            # console, the war room and /api/owner-actions; a buyer identifier in it is a
            # buyer identifier on all of them. The operator opens the case (GET /api/support,
            # credentialed) to see who it is.
            text = (f"Reply to buyer message (support case {case.id}) "
                    f"in Etsy Messages now: it has waited {hours:.1f}h of Etsy's "
                    f"{STANDARD_HOURS:.0f}h first-response standard"
                    + (f" ({left:.1f}h left)." if left > 0 else " -- the standard is "
                       "already breached; reply now and record it.")
                    + " A drafted reply, if any, is on the case. Then record the reply as "
                      "sent so this alert closes.")
            if action is None:
                s.add(OwnerAction(
                    requirement_key=key, action=text,
                    reason=("Replies are drafts in shadow mode and no Etsy messages API "
                            "exists, so only the owner can send it. Etsy measures sellers "
                            "against a 48-hour first response."),
                    max_cost_cad=0.0, minutes=5,
                    consequence_of_delay=("the buyer waits; past 48h the shop misses Etsy's "
                                          "response standard and a case or refund becomes "
                                          "likelier"),
                    blocks="buyer support"))
                raised.append(case.id)
            elif action.action != text:
                action.action = text
            incident, opened = lifecycle.open_or_restate(
                s, signature=signature, severity=severity,
                summary=(f"Buyer message unanswered for {hours:.1f}h (case {case.id}); "
                         f"stage {stage}"),
                detail={"case_id": case.id, "hours_waiting": round(hours, 2),
                        "stage": stage, "owner_action": key,
                        "standard_hours": STANDARD_HOURS}, now=now)
            if incident.severity != severity and severity == "P1":
                incident.severity = "P1"
                incident.summary = (f"Buyer message unanswered for {hours:.1f}h (case "
                                    f"{case.id}); stage {stage}")
                escalated.append(case.id)
            elif not opened:
                incident.summary = (f"Buyer message unanswered for {hours:.1f}h (case "
                                    f"{case.id}); stage {stage}")
            if stage == "breached":
                breached.append(case.id)
    return {"watching": watching, "raised": raised, "escalated": escalated,
            "breached": breached, "closed": closed,
            "thresholds_hours": [WARN_HOURS, ESCALATE_HOURS, STANDARD_HOURS],
            "note": ("watches only buyer messages recorded here; Etsy Messages are not "
                     "ingested (no API), so an unrecorded message is not watched")}
