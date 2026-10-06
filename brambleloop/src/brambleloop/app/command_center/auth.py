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
  Only a wrong credential (``BAD_CREDENTIALS``) counts; a refusal for being rate limited,
  cross-site or malformed never extends a lockout. The client is the socket peer unless the
  operator configures the trusted proxy (`BRAMBLELOOP_TRUSTED_PROXY_HOPS`, or
  `BRAMBLELOOP_CLIENT_IP_HEADER`): a client-supplied `X-Forwarded-For` is never trusted on its
  own. The *global* limit refuses unknown devices before the credential is checked, but cannot
  lock the owner out: a browser that has logged in before carries a trusted-device cookie
  (`__Host-bl_dev`, only its hash stored) and is limited per device instead, and a single-use
  recovery code minted with the operator credential (`POST /api/owner/cc/login-recovery`)
  lets a new device past the client and global limits. Neither replaces the passphrase/TOTP.
* **Audit** -- every refusal (and every login/step-up) is a `cc_security_events` row.

The application-wide `security.operator_gate` calls `gate()` for every `/api/cc/*` route, so the
default-deny property of the app is unchanged: a new command-center route is closed until it
is deliberately listed as public.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import math
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
from .models import (OwnerSession, RequestNonce, SecurityEvent, ensure_tables, kv_get,
                     kv_set)

log = logging.getLogger("brambleloop.cc.auth")

PASSPHRASE_VAR = "BRAMBLELOOP_OWNER_PASSPHRASE_HASH"
TOTP_VAR = "BRAMBLELOOP_OWNER_TOTP_SECRET"
COOKIE = "__Host-bl_cc"
DEVICE_COOKIE = "__Host-bl_dev"
# Trusted-proxy configuration (see `client_ip`). Railway terminates TLS at one edge proxy that
# appends the address it saw to X-Forwarded-For, so production sets HOPS=1.
TRUSTED_HOPS_VAR = "BRAMBLELOOP_TRUSTED_PROXY_HOPS"
CLIENT_IP_HEADER_VAR = "BRAMBLELOOP_CLIENT_IP_HEADER"
PUBLIC_ORIGIN_VAR = "BRAMBLELOOP_PUBLIC_ORIGIN"
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
LOGIN_FAILS_PER_DEVICE = 5
DEVICE_TTL = timedelta(days=90)
MAX_TRUSTED_DEVICES = 20
RECOVERY_TTL = timedelta(minutes=15)
DEVICES_KEY = "cc_trusted_devices"
RECOVERY_KEY = "cc_login_recovery"
FAILED_LOGIN_CODE = "BAD_CREDENTIALS"
MUTATIONS_PER_MINUTE = 30
STEPUP_FAILS_REVOKE = 5
PBKDF2_ITERATIONS = 600_000
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
# A nonce row must outlive every timestamp that could still pass the freshness check, or a
# purged nonce becomes replayable (audit ddf9c6e M2). Checked at import, not by `assert`.
if NONCE_RETENTION <= timedelta(seconds=2 * NONCE_SKEW_SECONDS):
    raise RuntimeError("NONCE_RETENTION must exceed twice NONCE_SKEW_SECONDS")

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


def _trusted_hops() -> int:
    try:
        return max(0, min(int((os.environ.get(TRUSTED_HOPS_VAR) or "0").strip()), 10))
    except ValueError:
        return 0


def client_ip(request) -> str:
    """The client address, trusting forwarding headers only as far as the operator configured.

    * default (no configuration): the socket peer. `X-Forwarded-For` is attacker-controlled
      and is ignored, so rotating it cannot mint fresh rate-limit buckets.
    * `BRAMBLELOOP_CLIENT_IP_HEADER=<name>`: that header, for a platform that overwrites it.
    * `BRAMBLELOOP_TRUSTED_PROXY_HOPS=N`: the N-th entry from the right of X-Forwarded-For.
      Each trusted proxy appends the address it saw, so the right-most N entries were written
      by our own proxies and everything to their left is client-supplied. Railway: N=1.
      Fewer entries than N means the request did not come through the proxies: socket peer.
    """
    peer = request.client.host if request.client else ""
    header = (os.environ.get(CLIENT_IP_HEADER_VAR) or "").strip().lower()
    if header:
        value = (request.headers.get(header) or "").split(",")[-1].strip()
        return value[:64] or peer
    hops = _trusted_hops()
    if hops == 0:
        return peer
    raw = ",".join(request.headers.getlist("x-forwarded-for"))
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    if len(entries) < hops:
        return peer
    return entries[-hops][:64]


def client_key(request) -> str:
    """Rate-limit key: the client address only (a user agent is attacker-chosen)."""
    return hashlib.sha256(f"ip|{client_ip(request)}".encode("utf-8", "replace")
                          ).hexdigest()[:32]


def client_hash(request) -> str:
    """Session fingerprint shown to the owner (address + user agent)."""
    ua = request.headers.get("user-agent") or ""
    return hashlib.sha256(f"{client_ip(request)}|{ua}".encode("utf-8", "replace")
                          ).hexdigest()[:32]


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
            ch = client_key(request)
        with db.session() as s:
            s.add(SecurityEvent(kind=kind, outcome=outcome, method=method[:8],
                                route=str(route)[:200], reason=str(reason)[:300],
                                session_public_id=session_public_id or "",
                                client_hash=ch, detail=dict(detail or {})))
    except Exception:  # noqa: BLE001 - auditing must never turn a refusal into an accept
        pass


def refuse(db, request, status: int, code: str, message: str, *, kind: str = "request",
           session_public_id: str = "", detail: dict | None = None) -> CCRefused:
    record(db, kind=kind, outcome="refused", request=request, reason=f"{code}: {message}",
           session_public_id=session_public_id, detail=detail)
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


def _failed_logins():
    """Wrong-credential login refusals inside the window. Nothing else counts: a 429, a CSRF or
    a malformed-body refusal is not a guess, and counting it let an attacker keep a lockout
    alive with refused requests alone (audit ddf9c6e M1)."""
    return select(func.count()).select_from(SecurityEvent).where(
        SecurityEvent.kind == "login", SecurityEvent.outcome == "refused",
        SecurityEvent.reason.like(f"{FAILED_LOGIN_CODE}:%"),
        SecurityEvent.at >= _now() - LOGIN_WINDOW)


def login_throttle(db, request, *, device_id: str | None = None,
                   recovery: bool = False) -> str | None:
    """Why this login may not even be verified now, or None.

    * a trusted device (cookie from an earlier successful login) is limited per device only;
    * a valid single-use recovery code (minted with the operator credential) is not limited;
    * anything else is limited per client address, then globally.
    The passphrase (and TOTP) is still required in every case."""
    ensure_tables(db)
    with db.session() as s:
        if device_id:
            n = s.scalar(_failed_logins().where(
                SecurityEvent.session_public_id == device_id)) or 0
            return "device" if n >= LOGIN_FAILS_PER_DEVICE else None
        if recovery:
            return None
        mine = s.scalar(_failed_logins().where(
            SecurityEvent.client_hash == client_key(request))) or 0
        if mine >= LOGIN_FAILS_PER_CLIENT:
            return "client"
        total = s.scalar(_failed_logins()) or 0
    return "global" if total >= LOGIN_FAILS_GLOBAL else None


def login_rate_limited(db, request) -> bool:
    """Back-compatible boolean form for a request with no device cookie or recovery code."""
    return login_throttle(db, request) is not None


# ---- trusted devices and recovery codes (lockout resistance, audit ddf9c6e M1) --------


def _kv_update(db, key: str, fn):
    ensure_tables(db)
    with db.session() as s:
        value = dict(kv_get(s, key, {}) or {})
        out = fn(value)
        kv_set(s, key, value)
        return out


def trusted_device(db, request) -> str | None:
    """The public id of the trusted device this request's cookie names, or None."""
    token = request.cookies.get(DEVICE_COOKIE) or ""
    if not token or len(token) > 200:
        return None
    ensure_tables(db)
    with db.session() as s:
        devices = (kv_get(s, DEVICES_KEY, {}) or {}).get("devices") or {}
    entry = devices.get(_token_hash(token))
    if not isinstance(entry, dict):
        return None
    try:
        if datetime.fromisoformat(entry["expires_at"]) <= _now():
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return str(entry.get("id") or "") or None


def issue_device(db) -> tuple[str, str]:
    """(cookie token, device id) for a browser that just logged in successfully."""
    token = secrets.token_urlsafe(32)
    device_id = "d_" + secrets.token_hex(8)
    now = _now()

    def add(value):
        devices = dict(value.get("devices") or {})
        devices[_token_hash(token)] = {"id": device_id, "created_at": now.isoformat(),
                                       "expires_at": (now + DEVICE_TTL).isoformat()}
        live = sorted(((k, v) for k, v in devices.items()
                       if str(v.get("expires_at", "")) > now.isoformat()),
                      key=lambda kv: kv[1].get("created_at", ""))[-MAX_TRUSTED_DEVICES:]
        value["devices"] = dict(live)

    _kv_update(db, DEVICES_KEY, add)
    return token, device_id


def mint_recovery_code(db) -> dict:
    """A single-use, 15-minute login recovery code. Caller must hold the operator credential."""
    code = secrets.token_urlsafe(24)
    now = _now()
    expires = now + RECOVERY_TTL

    def add(value):
        codes = {k: v for k, v in dict(value.get("codes") or {}).items()
                 if str(v.get("expires_at", "")) > now.isoformat()}
        codes[_token_hash(code)] = {"expires_at": expires.isoformat()}
        value["codes"] = dict(list(codes.items())[-5:])

    _kv_update(db, RECOVERY_KEY, add)
    return {"recovery_code": code, "expires_at": expires.isoformat(), "single_use": True}


def consume_recovery_code(db, code) -> bool:
    """True if `code` is a live recovery code; it is spent either way (single use)."""
    if not isinstance(code, str) or not code or len(code) > 200:
        return False
    h = _token_hash(code)
    now = _now().isoformat()

    def take(value):
        codes = dict(value.get("codes") or {})
        entry = codes.pop(h, None)
        value["codes"] = codes
        return isinstance(entry, dict) and str(entry.get("expires_at", "")) > now

    return bool(_kv_update(db, RECOVERY_KEY, take))


# ---- the gate ---------------------------------------------------------------


_DEFAULT_PORTS = {"https": 443, "http": 80}
_LOOPBACK = ("localhost", "127.0.0.1", "::1")


def _origin_tuple(value: str):
    """(scheme, host, port) of an origin, or None when it is not a usable http(s) origin."""
    from urllib.parse import urlsplit

    try:
        u = urlsplit(value.strip())
        scheme = u.scheme.lower()
        if scheme not in _DEFAULT_PORTS or not u.hostname:
            return None
        return scheme, u.hostname.lower(), u.port or _DEFAULT_PORTS[scheme]
    except ValueError:
        return None


def expected_origin(request):
    """The one origin the command center is served from: scheme + host + port.

    `BRAMBLELOOP_PUBLIC_ORIGIN` (e.g. https://brambleloop.example) wins when set. Otherwise the
    origin is https on the request's Host -- the session cookie is `__Host-`/Secure, so the
    command center only works over https; a plain-http origin is accepted only for a loopback
    host served over http (local development). TLS terminates at the platform proxy, so the
    scheme the app itself sees is not evidence of what the browser used.
    """
    configured = (os.environ.get(PUBLIC_ORIGIN_VAR) or "").strip()
    if configured:
        return _origin_tuple(configured)
    host = request.headers.get("host") or request.url.netloc
    scheme = "https"
    probe = _origin_tuple(f"https://{host}")
    if probe and probe[1] in _LOOPBACK and request.url.scheme == "http":
        scheme = "http"
    return _origin_tuple(f"{scheme}://{host}")


def _same_origin(request) -> bool:
    site = (request.headers.get("sec-fetch-site") or "").lower()
    if site and site not in ("same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if origin:
        got, want = _origin_tuple(origin), expected_origin(request)
        if got is None or want is None or got != want:
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
        stamp = float(ts)
        # nan compares False with everything, so `nan > N` let it through (audit ddf9c6e M2).
        skew = abs(time.time() - stamp) if math.isfinite(stamp) else None
    except (TypeError, ValueError, OverflowError):
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
