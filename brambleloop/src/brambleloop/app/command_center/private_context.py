"""The owner-private context in the Command Center (PRIV contract, spec/07 Ruling 2).

This is the ONLY non-private module allowed to import `laura.private.{access,store}` or call
`.reveal()` (`laura.private.access.ALLOWED_IMPORTERS`; a static test enforces it). Everything
private enters and leaves through here, and only here:

* Opening needs a live owner session with a FRESH step-up (`access.open_context`). The grant id
  never goes to the client: it is looked up server-side, per request, from the session's own
  unrevoked grant and re-verified by `access.require` on every store call.
* Values are revealed only while building the private view's response body (served with
  `Cache-Control: no-store`). Nothing private is written to notifications, the timeline, audit
  detail, Ask Company, Talk to Laura (business), any provider summary or Python logging.
* Refusals are recorded as security events with kind `private_context` and the exception
  CLASS NAME only -- never the body, text, key or a record id.
* What exists: owner-supplied facts, owner turns, forget, close. What does NOT exist: Laura's
  private conversational register. A private reply from Laura is GATED (PRIV handoff): no model
  is prompted here, nothing generates or styles private text, and the underlying provider's
  usage policies remain the outer limit. `owner_turn` records the owner's words and returns
  `reply_status: GATED`.

Business paths never import this module (`test_w3_laura_cc_private` proves it statically and
with an SQL watch), and `laura.private.firewall.reject_private` refuses its values on every
protected path.
"""
from __future__ import annotations

from datetime import datetime, timezone

REPLY_GATED = ("Laura's private conversational register is not implemented (GATED, D-FB-15/"
               "D-FB-16 item 11): your words are stored encrypted in the private context; no "
               "reply is generated.")


class PrivateUnavailable(Exception):
    """Mapped by the route to an HTTP status with a generic message. `status` 403/503/400."""

    def __init__(self, status: int, code: str, exc_name: str):
        super().__init__(code)
        self.status = status
        self.code = code
        self.exc_name = exc_name


def _map(exc: Exception) -> PrivateUnavailable:
    from ...laura.private.errors import (KeyUnavailable, PrivateAccessRefused,
                                         PrivateRefused)

    name = type(exc).__name__
    if isinstance(exc, KeyUnavailable):
        return PrivateUnavailable(503, "PRIVATE_UNAVAILABLE", name)
    if isinstance(exc, PrivateAccessRefused):
        return PrivateUnavailable(403, "PRIVATE_REFUSED", name)
    if isinstance(exc, PrivateRefused):
        return PrivateUnavailable(400, "PRIVATE_INPUT_REFUSED", name)
    return PrivateUnavailable(500, "PRIVATE_ERROR", name)


def _grant_id(db, session_public_id: str) -> str | None:
    """The session's newest live grant (server-side; never sent to the client)."""
    from sqlalchemy import inspect, select

    from ...laura.private.models import PrivateGrant

    if not inspect(db.engine).has_table(PrivateGrant.__tablename__):
        return None
    now = datetime.now(timezone.utc)
    with db.session() as s:
        rows = list(s.scalars(select(PrivateGrant).where(
            PrivateGrant.session_public_id == session_public_id,
            PrivateGrant.revoked_at.is_(None)).order_by(PrivateGrant.id.desc()).limit(5)))
        for g in rows:
            exp = g.expires_at if g.expires_at.tzinfo else g.expires_at.replace(
                tzinfo=timezone.utc)
            if exp > now:
                return g.grant_id
    return None


def _principal(db, session_public_id: str):
    from ...laura.private import access
    from ...laura.private.errors import PrivateAccessRefused

    gid = _grant_id(db, session_public_id)
    if gid is None:
        raise PrivateAccessRefused("no open private context on this session")
    return access.resume(db, session_public_id, gid)


def _call(fn):
    try:
        return fn()
    except PrivateUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure becomes a generic refusal
        raise _map(exc) from None


def status(db, session_public_id: str) -> dict:
    """Non-content status for the badge: configured? open? what is gated?"""
    from ...laura.private import store

    try:
        is_open = bool(session_public_id) and _grant_id(db, session_public_id) is not None
    except Exception:  # noqa: BLE001
        is_open = False
    return {"configured": store.configured(), "open": is_open,
            "requires": "a fresh owner step-up to open; closes on logout/revoke or after 30 min",
            "reply_register": "GATED", "reply_why": REPLY_GATED,
            "isolation": "encrypted owner-only store; never read by business, public, customer "
                         "or protected paths"}


def open_(db, session_public_id: str) -> dict:
    from ...laura.private import access

    def run():
        p = access.open_context(db, session_public_id, flag=access.PRIVATE_FLAG)
        access.require(db, p, "open")      # verify the fresh grant end to end
        return {"open": True, "ttl_minutes": int(access.GRANT_TTL.total_seconds() // 60)}
    return _call(run)


def close(db, session_public_id: str) -> dict:
    from ...laura.private import access

    return _call(lambda: {"closed": access.close_context(db, _principal(db,
                                                                         session_public_id))})


def on_session_revoked(db, session_public_id: str, reason: str = "session_revoked") -> int:
    """Belt and braces for logout / revoke (access.require already refuses a dead session)."""
    from ...laura.private import access

    try:
        return access.revoke_session_contexts(db, session_public_id, reason)
    except Exception:  # noqa: BLE001 - the session itself is already revoked
        return 0


def _row(r) -> dict:
    return {"id": r.record_id, "kind": r.kind, "provenance": r.provenance,
            "at": (r.created_at.isoformat() if hasattr(r.created_at, "isoformat")
                   else (str(r.created_at) if r.created_at else None)),
            "role": r.role, "key": r.key.reveal() if r.key is not None else None,
            "text": r.value.reveal() if r.value is not None else None}


def view(db, session_public_id: str, *, limit: int = 50) -> dict:
    """Facts + conversation, revealed for the private response body only."""
    from ...laura.private import store

    def run():
        p = _principal(db, session_public_id)
        return {"facts": [_row(r) for r in store.facts(db, p)],
                "conversation": [_row(r) for r in store.conversation(db, p, limit=limit)],
                "reply_register": "GATED"}
    return _call(run)


def remember(db, session_public_id: str, key: str, text: str) -> dict:
    from ...laura.private import store

    return _call(lambda: {"id": store.remember(db, _principal(db, session_public_id),
                                               str(key or ""), str(text or ""),
                                               provenance="owner_supplied")})


def owner_turn(db, session_public_id: str, text: str) -> dict:
    """Record what the owner typed. Laura's private reply is GATED: none is generated."""
    from ...laura.private import store

    return _call(lambda: {"id": store.record_turn(db, _principal(db, session_public_id),
                                                  "owner", str(text or "")),
                          "reply": None, "reply_status": "GATED", "why": REPLY_GATED})


def forget(db, session_public_id: str, record_id: str) -> dict:
    from ...laura.private import store

    return _call(lambda: {"deleted": store.forget(db, _principal(db, session_public_id),
                                                  str(record_id or ""))})
