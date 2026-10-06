"""Owner action authentication for the Command Center (F-887, F-888).

Threat model, briefly: the command center is a phone browser talking to a public origin. The
existing operator bearer token cannot live in a phone browser (any script on the origin could
read it, and it controls the whole company), so the owner gets a *session* instead:

* **Identity** -- a passphrase whose PBKDF2-SHA256 hash is provided by the hosting environment
  (`BRAMBLELOOP_OWNER_PASSPHRASE_HASH`; never the repository), optionally plus an RFC 6238
  TOTP code (`BRAMBLELOOP_OWNER_TOTP_SECRET`). Unset hash -> login is closed, not open.
* **Session** -- a random 256-bit token in an `HttpOnly; Secure; SameSite=Strict` `__Host-`
  cookie. Only its SHA-256 is stored. Absolute 12 h lifetime, 2 h idle timeout, revocable.
* **CSRF** -- every mutating request carries `X-CSRF-Token`, an HMAC of the session token, and
  a cross-site `Origin`/`Sec-Fetch-Site` is refused outright.
* **Replay** -- every mutating request carries a fresh `X-CC-Nonce` and an `X-CC-Timestamp`
  within +/-120 s; a nonce is accepted once (unique row in `cc_nonces`).
* **Step-up** -- consequential actions require a re-authentication within the last 5 minutes;
  five failed step-ups revoke the session.
* **Rate limits** -- login failures per client and globally, mutating requests per session.
* **Audit** -- every refusal (and every login/step-up) is a `cc_security_events` row.

The application-wide `security.operator_gate` calls `gate()` for every `/api/cc/*` route, so the
default-deny property of the app is unchanged: a new command-center route is closed until it
is deliberately listed as public.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...core import opsauth
from .. import security
from .models import OwnerSession, RequestNonce, SecurityEvent, ensure_tables

PASSPHRASE_VAR = "BRAMBLELOOP_OWNER_PASSPHRASE_HASH"
TOTP_VAR = "BRAMBLELOOP_OWNER_TOTP_SECRET"
COOKIE = "__Host-bl_cc"
CSRF_HEADER = "x-csrf-token"
NONCE_HEADER = "x-cc-nonce"
TS_HEADER = "x-cc-timestamp"

SESSION_TTL = timedelta(hours=12)
IDLE_TTL = timedelta(hours=2)
STEPUP_WINDOW = timedelta(minutes=5)
NONCE_SKEW_SECONDS = 120
NONCE_RETENTION = timedelta(minutes=10)
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_FAILS_PER_CLIENT = 5
LOGIN_FAILS_GLOBAL = 20
MUTATIONS_PER_MINUTE = 30
STEPUP_FAILS_REVOKE = 5
PBKDF2_ITERATIONS = 600_000
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

PREFIX = "/api/cc/"
# Command-center routes reachable without a session, each with the reason (kept short).
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/api/cc/auth/status"): "reports whether a session exists and nothing else",
    ("POST", "/api/cc/auth/login"): ("the login itself; rate limited, audited, JSON-only and "
                                     "same-origin only"),
}


class CCRefused(security.OperatorRefused):
    """A refusal with a machine-readable code for the PWA."""

    def __init__(self, status: int, message: str, code: str):
        super().__init__(status, message)
        self.code = code


def refused_handler(_request, exc: CCRefused):
    from fastapi.responses import JSONResponse

    return JSONResponse({"error": exc.message, "code": exc.code}, status_code=exc.status)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def iso(value: datetime | None) -> str | None:
    v = aware(value)
    return v.isoformat() if v else None


# ---- passphrase / TOTP ------------------------------------------------------


def hash_passphrase(passphrase: str, *, iterations: int = PBKDF2_ITERATIONS,
                    salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(iterations, base64.b64encode(salt).decode(),
                                           base64.b64encode(dk).decode())


def login_configured(env: dict | None = None) -> bool:
    e = env if env is not None else os.environ
    return _parse_hash((e.get(PASSPHRASE_VAR) or "").strip()) is not None


def _parse_hash(value: str):
    try:
        algo, iters, salt, dk = value.split("$")
        if algo != "pbkdf2_sha256" or int(iters) < 100_000:
            return None
        return int(iters), base64.b64decode(salt), base64.b64decode(dk)
    except (ValueError, TypeError):
        return None


def verify_passphrase(passphrase: str | None, env: dict | None = None) -> bool:
    e = env if env is not None else os.environ
    parsed = _parse_hash((e.get(PASSPHRASE_VAR) or "").strip())
    if parsed is None or not isinstance(passphrase, str) or not passphrase:
        return False
    iters, salt, expected = parsed
    got = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8", "surrogatepass"), salt,
                              iters)
    return hmac.compare_digest(got, expected)


def totp_required(env: dict | None = None) -> bool:
    e = env if env is not None else os.environ
    return bool((e.get(TOTP_VAR) or "").strip())


def totp_code(secret_b32: str, at: float | None = None, *, step: int = 30,
              digits: int = 6) -> str:
    key = base64.b32decode(secret_b32.strip().replace(" ", "").upper()
                           + "=" * (-len(secret_b32.strip().replace(" ", "")) % 8))
    counter = int((at if at is not None else time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(code: str | None, env: dict | None = None, at: float | None = None) -> bool:
    e = env if env is not None else os.environ
    secret = (e.get(TOTP_VAR) or "").strip()
    if not secret:
        return True
    code = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        return False
    t = at if at is not None else time.time()
    try:
        return any(hmac.compare_digest(totp_code(secret, t + d * 30), code) for d in (-1, 0, 1))
    except (ValueError, TypeError):
        return False


def verify_owner(passphrase, totp, env: dict | None = None) -> bool:
    ok_pass = verify_passphrase(passphrase, env)
    ok_totp = verify_totp(totp, env)
    return ok_pass and ok_totp


# ---- tokens -----------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()


def csrf_for(token: str) -> str:
    return hmac.new(token.encode("utf-8", "surrogatepass"), b"bl-cc-csrf-v1",
                    hashlib.sha256).hexdigest()


def client_hash(request) -> str:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    host = fwd or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent") or ""
    return hashlib.sha256(f"{host}|{ua}".encode("utf-8", "replace")).hexdigest()[:32]


# ---- audit ------------------------------------------------------------------


def record(db, *, kind: str, outcome: str, request=None, reason: str = "",
           session_public_id: str = "", detail: dict | None = None) -> None:
    """Append a security event in its own transaction (so it survives the refusal)."""
    try:
        ensure_tables(db)
        route = ""
        method = ""
        ch = ""
        if request is not None:
            r = request.scope.get("route")
            route = getattr(r, "path", None) or request.url.path
            method = request.method
            ch = client_hash(request)
        with db.session() as s:
            s.add(SecurityEvent(kind=kind, outcome=outcome, method=method[:8],
                                route=str(route)[:200], reason=str(reason)[:300],
                                session_public_id=session_public_id or "",
                                client_hash=ch, detail=dict(detail or {})))
    except Exception:  # noqa: BLE001 - auditing must never turn a refusal into an accept
        pass


def refuse(db, request, status: int, code: str, message: str, *, kind: str = "request",
           session_public_id: str = "") -> CCRefused:
    record(db, kind=kind, outcome="refused", request=request, reason=f"{code}: {message}",
           session_public_id=session_public_id)
    return CCRefused(status, message, code)


# ---- sessions ---------------------------------------------------------------


def create_session(db, request, *, device_label: str = "") -> tuple[str, dict]:
    ensure_tables(db)
    token = secrets.token_urlsafe(32)
    now = _now()
    public_id = "s_" + secrets.token_hex(8)
    with db.session() as s:
        s.add(OwnerSession(public_id=public_id, token_hash=_token_hash(token),
                           device_label=str(device_label or "")[:80],
                           client_hash=client_hash(request), created_at=now,
                           last_seen_at=now, expires_at=now + SESSION_TTL,
                           stepup_until=now + STEPUP_WINDOW))
    return token, session_view(db, public_id, current=public_id)


def session_view(db, public_id: str, *, current: str | None = None) -> dict | None:
    with db.session() as s:
        row = s.scalar(select(OwnerSession).where(OwnerSession.public_id == public_id))
        return None if row is None else _view(row, current)


def _view(row: OwnerSession, current: str | None = None) -> dict:
    last = aware(row.last_seen_at)
    return {"session_id": row.public_id, "device_label": row.device_label,
            "created_at": iso(row.created_at), "last_seen_at": iso(row.last_seen_at),
            "expires_at": iso(row.expires_at),
            "idle_expires_at": iso(last + IDLE_TTL) if last else None,
            "stepup_valid_until": iso(row.stepup_until),
            "revoked_at": iso(row.revoked_at), "revoked_reason": row.revoked_reason or None,
            "current": current is not None and row.public_id == current}


def _live(row: OwnerSession | None, now: datetime) -> str | None:
    """Why this session is not usable, or None."""
    if row is None:
        return "no session"
    if row.revoked_at is not None:
        return "session revoked"
    if aware(row.expires_at) <= now:
        return "session expired"
    if aware(row.last_seen_at) + IDLE_TTL <= now:
        return "session idle timeout"
    return None


def session_from_request(db, request) -> tuple[OwnerSession | None, str | None, str]:
    """(row, why-not-usable, token). Never raises."""
    token = request.cookies.get(COOKIE) or ""
    if not token or len(token) > 200:
        return None, "no session", ""
    try:
        ensure_tables(db)
        with db.session() as s:
            row = s.scalar(select(OwnerSession).where(
                OwnerSession.token_hash == _token_hash(token)))
            if row is not None:
                s.expunge(row)
    except Exception as exc:  # noqa: BLE001
        return None, f"session store unreadable ({type(exc).__name__})", token
    return row, _live(row, _now()), token


def revoke_session(db, public_id: str, reason: str) -> bool:
    with db.session() as s:
        row = s.scalar(select(OwnerSession).where(OwnerSession.public_id == public_id))
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = _now()
        row.revoked_reason = reason[:200]
        return True


def list_sessions(db, current: str | None = None, limit: int = 50) -> list[dict]:
    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(OwnerSession).order_by(OwnerSession.id.desc())
                              .limit(limit)))
        return [_view(r, current) for r in rows]


def grant_stepup(db, public_id: str) -> str:
    until = _now() + STEPUP_WINDOW
    with db.session() as s:
        row = s.scalar(select(OwnerSession).where(OwnerSession.public_id == public_id))
        row.stepup_until = until
        row.failed_stepups = 0
    return until.isoformat()


def failed_stepup(db, public_id: str) -> bool:
    """Count a failed step-up; returns True when the session was revoked for it."""
    with db.session() as s:
        row = s.scalar(select(OwnerSession).where(OwnerSession.public_id == public_id))
        row.failed_stepups = int(row.failed_stepups or 0) + 1
        if row.failed_stepups >= STEPUP_FAILS_REVOKE and row.revoked_at is None:
            row.revoked_at = _now()
            row.revoked_reason = "too many failed step-up attempts"
            return True
    return False


# ---- rate limits ------------------------------------------------------------


def login_rate_limited(db, request) -> bool:
    ensure_tables(db)
    since = _now() - LOGIN_WINDOW
    ch = client_hash(request)
    with db.session() as s:
        base = select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.kind == "login", SecurityEvent.outcome == "refused",
            SecurityEvent.at >= since)
        mine = s.scalar(base.where(SecurityEvent.client_hash == ch)) or 0
        total = s.scalar(base) or 0
    return mine >= LOGIN_FAILS_PER_CLIENT or total >= LOGIN_FAILS_GLOBAL


# ---- the gate ---------------------------------------------------------------


def _same_origin(request) -> bool:
    site = (request.headers.get("sec-fetch-site") or "").lower()
    if site and site not in ("same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit

        host = request.headers.get("host") or request.url.netloc
        if urlsplit(origin).netloc.lower() != host.lower():
            return False
    return True


def _check_freshness(db, request, public_id: str) -> None:
    nonce = request.headers.get(NONCE_HEADER) or ""
    ts = request.headers.get(TS_HEADER) or ""
    if not _NONCE_RE.match(nonce):
        raise refuse(db, request, 400, "STALE_REQUEST",
                     "X-CC-Nonce (16-128 chars of A-Za-z0-9_-) required",
                     session_public_id=public_id)
    try:
        skew = abs(time.time() - float(ts))
    except (TypeError, ValueError):
        skew = None
    if skew is None or skew > NONCE_SKEW_SECONDS:
        raise refuse(db, request, 400, "STALE_REQUEST",
                     f"X-CC-Timestamp must be unix seconds within {NONCE_SKEW_SECONDS}s",
                     session_public_id=public_id)
    now = _now()
    with db.session() as s:
        recent = s.scalar(select(func.count()).select_from(RequestNonce).where(
            RequestNonce.session_public_id == public_id,
            RequestNonce.at >= now - timedelta(minutes=1))) or 0
    if recent >= MUTATIONS_PER_MINUTE:
        raise refuse(db, request, 429, "RATE_LIMITED",
                     f"more than {MUTATIONS_PER_MINUTE} actions a minute",
                     session_public_id=public_id)
    try:
        with db.session() as s:
            # Older nonces are outside the timestamp window, so they cannot be replayed anyway.
            s.query(RequestNonce).filter(RequestNonce.at < now - NONCE_RETENTION).delete()
            s.add(RequestNonce(nonce=nonce, session_public_id=public_id, at=now))
    except IntegrityError:
        raise refuse(db, request, 409, "REPLAY", "request nonce already used",
                     session_public_id=public_id) from None


def gate(db, request, route_path: str) -> None:
    """Called by `security.operator_gate` for every `/api/cc/*` route."""
    method = request.method.upper()
    if (method, route_path) in PUBLIC_ROUTES:
        if method not in security.SAFE_METHODS and not _same_origin(request):
            raise refuse(db, request, 403, "CSRF", "cross-site request refused",
                         kind="login")
        return
    if not opsauth.configured():
        raise refuse(db, request, 503, "OPS_UNCONFIGURED",
                     f"{opsauth.TOKEN_VAR} is not configured, so the command center is closed")
    row, why, token = session_from_request(db, request)
    if why is not None:
        raise refuse(db, request, 401, "NOT_AUTHENTICATED",
                     f"owner session required ({why})")
    if method not in security.SAFE_METHODS:
        if not _same_origin(request):
            raise refuse(db, request, 403, "CSRF", "cross-site request refused",
                         session_public_id=row.public_id)
        supplied = request.headers.get(CSRF_HEADER) or ""
        if not supplied or not hmac.compare_digest(supplied.encode("utf-8", "replace"),
                                                   csrf_for(token).encode()):
            raise refuse(db, request, 403, "CSRF", "missing or wrong X-CSRF-Token",
                         session_public_id=row.public_id)
        _check_freshness(db, request, row.public_id)
    with db.session() as s:
        live = s.scalar(select(OwnerSession).where(OwnerSession.id == row.id))
        live.last_seen_at = _now()
    request.state.cc_session = {"public_id": row.public_id, "token": token,
                                "stepup_until": aware(row.stepup_until)}


def require_stepup(db, request, action: str) -> None:
    sess = getattr(request.state, "cc_session", None) or {}
    until = sess.get("stepup_until")
    if until is None or until <= _now():
        raise refuse(db, request, 403, "STEP_UP_REQUIRED",
                     f"{action} is a consequential action; re-authenticate (step-up) first",
                     kind="stepup", session_public_id=sess.get("public_id", ""))


def current_public_id(request) -> str:
    return (getattr(request.state, "cc_session", None) or {}).get("public_id", "")


def _cli() -> None:  # pragma: no cover - interactive
    import getpass
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "hash":
        print("usage: python -m brambleloop.app.command_center.auth hash")
        raise SystemExit(2)
    p1 = getpass.getpass("Owner passphrase (min 12 chars): ")
    p2 = getpass.getpass("Repeat: ")
    if p1 != p2 or len(p1) < 12:
        print("passphrases differ or are shorter than 12 characters")
        raise SystemExit(1)
    print(f"{PASSPHRASE_VAR}={hash_passphrase(p1)}")


if __name__ == "__main__":  # pragma: no cover
    _cli()
