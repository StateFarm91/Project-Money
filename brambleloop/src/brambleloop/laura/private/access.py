"""Who may touch the private context: only a live, explicitly private owner context.

CONTRACT FOR LANE F (Command Center) -- the only caller expected to import this module:

1. The owner signs in as today (`app/command_center/auth.py`): a `cc_owner_sessions` row.
2. To enter the private view the owner performs an explicit action ("Open private context")
   with a FRESH step-up (`stepup_until > now`, i.e. passphrase/TOTP re-verified within
   `auth.STEPUP_WINDOW`). The route is owner-authenticated, CSRF-checked, POST only, and calls
       principal = access.open_context(db, session_public_id, flag=access.PRIVATE_FLAG)
   It raises `PrivateAccessRefused` (or `KeyUnavailable`) on any failure; map it to 403/503
   with a generic message. The principal is held server-side for the request only -- never
   serialised to the client, never cached across requests (re-open per request with the
   grant id kept in the server-side session, or call `resume(db, session_public_id,
   grant_id)` each request).
3. Every store call takes that principal and re-verifies on every call: exact type
   `PrivatePrincipal`; HMAC tag under the configured key; grant exists, matches the session,
   was issued under the current key, is not revoked or expired (TTL `GRANT_TTL`, never past
   the session's expiry); and the owner session itself is still present, unrevoked and
   unexpired. Revoking or expiring the owner session therefore ends private access at once.
4. Logout / session revoke must call `revoke_session_contexts(db, session_public_id)`
   (belt and braces: step 3 already refuses a revoked session).
5. Refused attempts may be recorded by F in `cc_security_events` ONLY as
   kind="private_context", outcome="refused", with the exception class name as reason --
   never the request body, the text, the key or any record id.
6. Private plaintext is revealed (`PrivateValue.reveal()`) only while rendering the private
   view response, with `Cache-Control: no-store`, outside notifications, the timeline,
   audit detail, Ask Company and every provider summary.

Every other principal -- `laura.memory.Principal` of any kind (including a verified
business owner principal), Laura's business context, departments, public, customer, the
operator token, strings, dicts, None, subclasses -- is refused.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, select, update

from . import crypto
from .errors import KeyUnavailable, PrivateAccessRefused, PrivateRefused
from .models import PrivateAccess, PrivateGrant, ensure_tables

PRIVATE_FLAG = "owner_private_context.v1"
GRANT_TTL = timedelta(minutes=30)
#: Modules allowed to import the private API / call `.reveal()` (static test enforces).
ALLOWED_IMPORTERS = ("brambleloop.laura.private",
                     "brambleloop.app.command_center.private_context")


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, repr=False)
class PrivatePrincipal:
    session_public_id: str
    grant_id: str
    tag: str
    __brambleloop_private__ = True   # the firewall refuses it on every protected path

    def __repr__(self) -> str:
        return "PrivatePrincipal(<redacted>)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("a private principal cannot be serialised")


def record_access(db, op: str, outcome: str, reason: str = "", principal=None) -> None:
    """The private context's own access log. Fixed vocabulary only; never content."""
    try:
        ensure_tables(db)
        with db.session() as s:
            s.add(PrivateAccess(op=op[:24], outcome=outcome[:8], reason=reason[:40],
                                principal_type=type(principal).__name__[:40]))
    except Exception:  # noqa: BLE001 - the refusal stands even if its log row cannot be written
        pass


def _owner_session(db, session_public_id: str):
    from ...app.command_center.models import OwnerSession

    if not inspect(db.engine).has_table(OwnerSession.__tablename__):
        raise PrivateAccessRefused("no owner session store: private access cannot be verified")
    with db.session() as s:
        return s.scalar(select(OwnerSession).where(
            OwnerSession.public_id == session_public_id))


def _check_session(row, now: datetime, *, need_stepup: bool) -> None:
    if row is None:
        raise PrivateAccessRefused("owner session not found")
    if row.revoked_at is not None:
        raise PrivateAccessRefused("owner session revoked")
    if _aware(row.expires_at) is None or _aware(row.expires_at) <= now:
        raise PrivateAccessRefused("owner session expired")
    if need_stepup and (_aware(row.stepup_until) is None or _aware(row.stepup_until) <= now):
        raise PrivateAccessRefused("a fresh step-up is required to open the private context")


def _principal_tag(keys, session_public_id: str, grant_id: str) -> str:
    return crypto.tag(keys, "private-principal", session_public_id, grant_id)


def open_context(db, session_public_id, *, flag, now: datetime | None = None
                 ) -> PrivatePrincipal:
    """Issue a private grant on a live owner session with a fresh step-up."""
    now = _now(now)
    try:
        if flag != PRIVATE_FLAG:
            raise PrivateAccessRefused("the private context must be requested explicitly")
        if not isinstance(session_public_id, str) or not session_public_id:
            raise PrivateAccessRefused("an owner session is required")
        keys = crypto.load_keys()
        row = _owner_session(db, session_public_id)
        _check_session(row, now, need_stepup=True)
        ensure_tables(db)
        grant_id = "pg_" + secrets.token_hex(16)
        expires = min(now + GRANT_TTL, _aware(row.expires_at))
        with db.session() as s:
            s.add(PrivateGrant(grant_id=grant_id, session_public_id=session_public_id,
                               key_id=keys.key_id, created_at=now, expires_at=expires))
    except PrivateRefused as exc:
        record_access(db, "open", "refused", type(exc).__name__, session_public_id)
        raise
    record_access(db, "open", "ok", "", session_public_id)
    return PrivatePrincipal(session_public_id, grant_id,
                            _principal_tag(keys, session_public_id, grant_id))


def resume(db, session_public_id: str, grant_id: str) -> PrivatePrincipal:
    """Rebuild the principal for a later request; it is verified again on use."""
    keys = crypto.load_keys()
    return PrivatePrincipal(session_public_id, grant_id,
                            _principal_tag(keys, session_public_id, grant_id))


def require(db, principal, op: str, *, now: datetime | None = None):
    """Return (keys, grant) for a genuine private principal, else raise and log the refusal."""
    now = _now(now)
    try:
        if type(principal) is not PrivatePrincipal:
            raise PrivateAccessRefused("only a live private owner context may use this store")
        keys = crypto.load_keys()
        if not crypto.tags_equal(principal.tag, _principal_tag(
                keys, principal.session_public_id, principal.grant_id)):
            raise PrivateAccessRefused("private principal failed verification")
        if not inspect(db.engine).has_table(PrivateGrant.__tablename__):
            raise PrivateAccessRefused("no private grant exists")
        with db.session() as s:
            grant = s.scalar(select(PrivateGrant).where(
                PrivateGrant.grant_id == principal.grant_id))
        if grant is None or grant.session_public_id != principal.session_public_id:
            raise PrivateAccessRefused("private grant not found")
        if not crypto.tags_equal(grant.key_id, keys.key_id):
            raise PrivateAccessRefused("private grant was issued under a different key")
        if grant.revoked_at is not None:
            raise PrivateAccessRefused("private grant revoked")
        if _aware(grant.expires_at) <= now:
            raise PrivateAccessRefused("private grant expired")
        _check_session(_owner_session(db, principal.session_public_id), now,
                       need_stepup=False)
    except (PrivateRefused, KeyUnavailable) as exc:
        record_access(db, op, "refused", type(exc).__name__, principal)
        raise
    return keys, grant


def close_context(db, principal) -> bool:
    require(db, principal, "close")
    with db.session() as s:
        n = s.execute(update(PrivateGrant).where(
            PrivateGrant.grant_id == principal.grant_id,
            PrivateGrant.revoked_at.is_(None)).values(
            revoked_at=_now(), revoked_reason="closed")).rowcount
    record_access(db, "close", "ok", "", principal)
    return bool(n)


def revoke_session_contexts(db, session_public_id: str, reason: str = "session_revoked") -> int:
    """Revoke every private grant on an owner session (call on logout / session revoke)."""
    if not inspect(db.engine).has_table(PrivateGrant.__tablename__):
        return 0
    with db.session() as s:
        n = s.execute(update(PrivateGrant).where(
            PrivateGrant.session_public_id == session_public_id,
            PrivateGrant.revoked_at.is_(None)).values(
            revoked_at=_now(), revoked_reason=reason[:40])).rowcount
    record_access(db, "revoke", "ok", reason, session_public_id)
    return int(n or 0)
