"""The web edge's security rules, in one place (independent audit A3-01, A3-02, A3-04).

Four things live here because each was previously decided route by route, and a rule that is
decided route by route is a rule the next route forgets:

1. **Escaping.** `esc()` is the only way a value enters server-rendered HTML. `Markup` marks a
   fragment this code built itself (a tag, a pill, a nested table) so it is not escaped twice.
   Everything else -- a job error, an owner-card text, a product title, an exception message --
   is data and is escaped, because any of them can carry text that arrived from outside (an
   unauthenticated query string dead-lettered into `Job.last_error` was the A3-01 vector).

2. **Response headers.** Every response carries a strict Content-Security-Policy (no inline
   script, no framing, no third-party anything), `X-Content-Type-Options: nosniff`, a
   `Referrer-Policy` and `X-Frame-Options`. A route that needs a stricter policy (the OAuth
   callback page) sets its own and it is left alone.

3. **Default-deny operator gate.** Every non-GET route, and every GET listed in
   `OPERATOR_GET_ROUTES`, requires the operator credential (`core.opsauth`: 503 when it is not
   configured, 401 -- 403 on the owner phase/publication/activation routers, preserving their
   contract -- when it is
   missing or wrong). The gate is installed as an application-wide dependency, so a new route
   is closed until somebody adds it to `PUBLIC_MUTATING_ROUTES` with a reason. The test
   `tests/test_route_auth_default_deny.py` walks `app.routes` and fails on any mutating route
   that is neither gated nor justified.

4. **Customer-identifier scrub.** Defence in depth for A3-04: on a response to a request that
   did not present the operator credential, any known buyer identifier is replaced with
   `[customer]` before it leaves. The primary fix is that no owner-facing text embeds one; the
   scrub is what keeps the next forgotten write path from publishing a buyer's handle.
"""
from __future__ import annotations

import html as _html
import json as _json
import re
from typing import Callable, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse

from ..core import opsauth


# ---- 1. escaping ------------------------------------------------------------


class Markup(str):
    """An HTML fragment this module's callers built from escaped parts. Not escaped again."""

    __slots__ = ()


def esc(value) -> Markup:
    """Escape one value for an HTML text node or a double/single-quoted attribute."""
    if isinstance(value, Markup):
        return value
    if value is None:
        return Markup("")
    return Markup(_html.escape(str(value), quote=True))


def safe_url(value) -> str:
    """Only http(s) or same-origin paths may become an href; anything else is dropped."""
    v = str(value or "").strip()
    if v.startswith("/") and not v.startswith("//"):
        return v
    if re.match(r"^https?://", v, re.IGNORECASE):
        return v
    return ""


# ---- 2. response headers ----------------------------------------------------

# No inline script anywhere: the one page with behaviour (/ops/teardown) loads its script from
# this origin. Inline *style* stays allowed: the dashboard is server-rendered with a <style>
# block and style attributes, and a style cannot read a token.
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; font-src 'self'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'; object-src 'none'")

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware:
    """Pure ASGI, so streaming bodies and background tasks are untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {k.decode("latin-1").lower() for k, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if name.lower() not in present:
                        headers.append((name.encode("latin-1"), value.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, _send)


# ---- 3. default-deny operator gate ------------------------------------------

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Non-GET routes that do NOT take the operator credential, each with the reason. Keep it short.
PUBLIC_MUTATING_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/api/learn/lessons/{slug}/review"): (
        "guarded by its own, deliberately distinct Learn reviewer credential "
        "(learn.api._reviewer); the operator token must not be able to approve a lesson"),
    ("POST", "/api/cc/auth/login"): (
        "the owner command-center login itself: verifies the owner passphrase hash (and TOTP "
        "when configured), rate limited, same-origin and JSON only, every failure audited in "
        "cc_security_events (app.command_center.auth)"),
}

# GET routes that trigger work, or return customer/order/support content, or return
# operator-only material. Each also performs its own check; the gate makes it default.
OPERATOR_GET_ROUTES: frozenset[str] = frozenset({
    "/api/support",
    "/api/continuity/export",
    "/api/etsy/oauth/start",
    "/api/etsy/oauth/status",
    "/api/teardown/intake",
    "/api/owner/phase",
    "/api/owner/ledger-mapping",
    "/api/learn/queue",
    "/api/learn/graph",
    "/api/learn/lessons/{slug}",
})

# GETs that are deliberately public, with the reason. Everything not listed here and not in
# OPERATOR_GET_ROUTES is a read-only aggregate view (the dashboard's "absent owner opens a
# URL" convenience), and `tests/test_customer_data_auth.py` sweeps those for customer data.
PUBLIC_GET_NOTES: dict[str, str] = {
    "/health": "platform health check; generic body, no infrastructure detail (A3-12)",
    "/api/etsy/oauth/callback": ("Etsy redirects the owner's browser here without a bearer "
                                 "header; guarded by a single-use state this service minted"),
    "/api/verify": ("standing verification read by the operator loop; read-only apart from "
                    "stamping its own verdict"),
    "/ops/teardown": "static page with no data; every request it makes carries the token",
}

# Routers whose established contract is 403 for a refused credential (phase_api,
# publication_authority_api, activation_authority_api, ledger_mapping_api). Everything else
# answers 401 -- including `/api/owner/decision`, which is an app route, not one of these.
_FORBIDDEN_PREFIXES = ("/api/owner/phase", "/api/owner/publication/", "/api/owner/activation/",
                       "/api/owner/ledger-mapping")


def refusal_status(route_path: str) -> int:
    return 403 if route_path.startswith(_FORBIDDEN_PREFIXES) else 401


class OperatorRefused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def operator_refused_handler(request: Request, exc: OperatorRefused) -> JSONResponse:
    # Each route family keeps the refusal body it always had: the app's own routes answered
    # {"error": ...}, the APIRouter-based ones (owner phase/publication/activation, Learn)
    # raised HTTPException, i.e. {"detail": ...}.
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    key = "detail" if path.startswith(_FORBIDDEN_PREFIXES + ("/api/learn/",)) else "error"
    return JSONResponse({key: exc.message}, status_code=exc.status)


def requires_operator(method: str, route_path: str) -> bool:
    method = method.upper()
    if method in SAFE_METHODS:
        return method in {"GET", "HEAD"} and route_path in OPERATOR_GET_ROUTES
    return (method, route_path) not in PUBLIC_MUTATING_ROUTES


# v1.1 Owner Command Center (F-887): `/api/cc/*` is authenticated by the owner *session*
# (cookie + CSRF + nonce + step-up), not the operator bearer token, which must never live in a
# phone browser. The command center registers its verifier here at mount time; until it does,
# every `/api/cc/*` route is closed (503). The gate stays the one application-wide dependency.
OWNER_SESSION_PREFIX = "/api/cc/"
_owner_session_gate: Callable | None = None


def register_owner_session_gate(fn: Callable | None) -> None:
    """`fn(request, route_path)` raises `OperatorRefused` (or a subclass) to refuse."""
    global _owner_session_gate
    _owner_session_gate = fn


def owner_session_route(route_path: str) -> bool:
    return route_path.startswith(OWNER_SESSION_PREFIX)


def operator_gate(request: Request) -> None:
    """Application-wide dependency. Default-deny for anything that is not a public read."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or request.url.path
    if owner_session_route(route_path):
        if _owner_session_gate is None:
            raise OperatorRefused(503, "owner command center authentication not installed")
        _owner_session_gate(request, route_path)
        return
    if not requires_operator(request.method, route_path):
        return
    try:
        opsauth.check(request.headers.get("authorization"))
    except opsauth.OpsAuthUnavailable as e:
        raise OperatorRefused(503, str(e)) from None
    except opsauth.OpsAuthRefused:
        raise OperatorRefused(refusal_status(route_path),
                              "operator credential required") from None


def iter_api_routes(app):
    """Every API route the app serves, as (path, methods, dependant), routers included.

    FastAPI 0.14x no longer copies an included router's routes into `app.routes`; it keeps an
    `_IncludedRouter` that composes them lazily. A sweep over `app.routes` alone silently
    skipped every router (owner phase, publication, activation, Learn, storefront), which is
    exactly the kind of blind spot a security enumeration must not have.
    """
    from fastapi.routing import APIRoute

    def walk(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield r.path, set(r.methods or ()), r.dependant
                continue
            candidates = getattr(r, "effective_candidates", None)
            if candidates is None:
                continue
            for c in candidates():
                if hasattr(c, "effective_candidates"):
                    yield from walk([c])
                elif isinstance(getattr(c, "original_route", None), APIRoute):
                    yield c.path, set(c.methods or ()), c.dependant

    yield from walk(app.routes)


def presents_operator_credential(authorization: str | None) -> bool:
    try:
        opsauth.check(authorization)
        return True
    except (opsauth.OpsAuthUnavailable, opsauth.OpsAuthRefused):
        return False


# ---- 4. customer-identifier scrub -------------------------------------------

REDACTED = "[customer]"
# Shorter identifiers are too likely to collide with ordinary words in a response.
MIN_REF_LENGTH = 6


# Placeholder references some write paths use when no buyer is known. Not identifiers.
_NOT_IDENTIFIERS = frozenset({"unknown", "anonymous", "customer", "buyer", "seller", "owner"})


def build_scrubber(refs: Iterable[str]) -> Callable[[str], str] | None:
    """A function replacing every known identifier in a text with `[customer]`."""
    variants: set[str] = set()
    for ref in refs:
        r = str(ref or "").strip()
        if len(r) < MIN_REF_LENGTH or r.lower() in _NOT_IDENTIFIERS:
            continue
        variants.add(r)
        variants.add(_html.escape(r, quote=True))
    if not variants:
        return None
    pattern = re.compile(
        r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(v) for v in
                                          sorted(variants, key=len, reverse=True))
        + r")(?![A-Za-z0-9])", re.IGNORECASE)
    return lambda text: pattern.sub(REDACTED, text)


def scrub_body(body: bytes, content_type: str, scrub: Callable[[str], str]) -> bytes:
    """Scrub a JSON body value by value (structure untouched) or an HTML body as text."""
    if "application/json" in content_type:
        try:
            data = _json.loads(body)
        except ValueError:
            return body

        def walk(v):
            if isinstance(v, str):
                return scrub(v)
            if isinstance(v, list):
                return [walk(x) for x in v]
            if isinstance(v, dict):
                return {(scrub(k) if isinstance(k, str) else k): walk(x)
                        for k, x in v.items()}
            return v

        cleaned = walk(data)
        if cleaned == data:
            return body
        try:
            return _json.dumps(cleaned, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            return body
    return scrub(body.decode("utf-8", errors="replace")).encode("utf-8")


class CustomerRefScrubMiddleware:
    """Redact known buyer identifiers from unauthenticated JSON and HTML responses."""

    def __init__(self, app, refs_provider: Callable[[], Iterable[str]]):
        self.app = app
        self.refs_provider = refs_provider

    def _scrubber(self):
        # Read per response, not cached: a cache is a window in which a buyer recorded a
        # second ago is not yet redacted, and the read is three indexed column scans.
        try:
            return build_scrubber(self.refs_provider())
        except Exception:  # noqa: BLE001 - no database yet means no identifiers to scrub
            return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        auth = None
        for k, v in scope.get("headers") or []:
            if k.lower() == b"authorization":
                auth = v.decode("latin-1")
        if presents_operator_credential(auth):
            return await self.app(scope, receive, send)

        state: dict = {"start": None, "chunks": [], "buffer": None, "ctype": ""}

        async def _send(message):
            if message["type"] == "http.response.start":
                ctype = ""
                for k, v in message.get("headers") or []:
                    if k.lower() == b"content-type":
                        ctype = v.decode("latin-1").lower()
                state["ctype"] = ctype
                state["buffer"] = ("application/json" in ctype or "text/html" in ctype)
                if not state["buffer"]:
                    await send(message)
                else:
                    state["start"] = message
                return
            if message["type"] == "http.response.body" and state["buffer"]:
                state["chunks"].append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = b"".join(state["chunks"])
                scrub = self._scrubber()
                if scrub is not None:
                    body = scrub_body(body, state["ctype"], scrub)
                start = state["start"]
                headers = [(k, v) for k, v in start.get("headers") or []
                           if k.lower() != b"content-length"]
                headers.append((b"content-length", str(len(body)).encode("latin-1")))
                await send({**start, "headers": headers})
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, _send)
