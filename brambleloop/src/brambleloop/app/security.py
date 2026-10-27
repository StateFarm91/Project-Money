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

3. **Default-deny operator gate.** Every non-GET route, and every GET not on the
   `PUBLIC_GET_ROUTES` allow-list (W4-SECPATCH), requires the operator credential (`core.opsauth`: 503 when it is not
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
    ("POST", "/api/etsy/webhook"): (
        "Etsy cannot present the operator credential; each delivery is verified against its "
        "own HMAC-SHA256 signature (whsec_ secret in ETSY_WEBHOOK_SECRET, 300 s skew limit) "
        "before the body is parsed, refused with 503 while no secret is set, and a verified "
        "delivery only enqueues the authenticated receipt read (integrations.etsy_webhooks, "
        "F-512)"),
}

# GET routes that trigger work, or return customer/order/support content, or return
# operator-only material. Each also performs its own check; the gate makes it default.
OPERATOR_GET_ROUTES: frozenset[str] = frozenset({
    "/api/support",
    "/api/orders/ledger",
    "/api/continuity/export",
    "/api/etsy/oauth/start",
    "/api/etsy/oauth/status",
    "/api/teardown/intake",
    "/api/owner/phase",
    "/api/owner/phase/verdict",
    "/api/owner/phase/visibility",
    "/api/owner/ledger-mapping",
    "/api/learn/queue",
    "/api/learn/graph",
    "/api/learn/lessons/{slug}",
    # W3 K8 (commerce.estate_api, mounted by lane F): per-buyer CX workspace and the open
    # policy-violation incidents carry customer/shop-case content -> operator credential.
    "/api/cx/workspace",
    "/api/etsy/policy-violations",
    # W4-MJS wiring: the latest competitor-intelligence findings reading (operator only).
    "/api/mjs/findings",
    # W4-FMEND (F-878): the launch packet carries the owner queue, spend limits and product
    # gate state -> operator credential.
    "/api/launch/packet",
    # W4-SECFIX (independent security review e3747c5, LOW-2): owner-recorded Marketplace
    # Insights (search counts, related terms, who recorded them) are the shop's private demand
    # research, read from the owner's Shop Manager -> operator credential, like
    # /api/mjs/findings. tests/test_w4_secfix_insights_private.py sweeps every public GET.
    "/api/market-intel",
    "/api/insights",
    # W4-FMBATCH1 (F-089): the physical-truth dashboard names testers and carries their
    # notes -> operator credential.
    "/api/physical-truth",
    # W4-FMBATCH1 (F-451): the master view carries the owner queue and spend -> operator.
    "/api/orchestrator",
    # F-549: revenue, margin and owner actions in one card -> operator.
    "/api/etsy/scorecard",
    "/api/opportunities",
    "/api/evidence",
    "/api/finance/owner",
    # Review cbd4ff1 N-1 route audit: department spend/incidents/inbound tasks, the product
    # lifecycle board (unpublished product slugs and titles) and the spend-governance detail
    # (research questions, per-provider adoption cost) are operator reads.
    "/api/company/departments/{key}",
    "/api/products/lifecycle",
    "/api/spend-report/governance",
    "/api/marketing/constellation/{slug}",
    # F-671: the dossier includes support cases and orders -> operator.
    "/api/product/{slug}/dossier",
    # WIRE1 (F-748, F-680): the Visual Studio view and a product's visual evidence panel
    # carry unpublished candidate hashes, rejection reasons, spend-driven provider choice and
    # controlled-experiment runs -> operator. The owner reads them under /api/cc/visual/.
    "/api/visual/studio",
    "/api/visual/evidence/{slug}",
})

# GETs that are deliberately public, with the reason. W4-SECPATCH (2026-10-26): this is now an
# ALLOW-LIST. Every GET/HEAD route not named here requires the operator credential (or, under
# `/api/cc/` and `OWNER_SESSION_PAGES`, the owner session). Until then every GET not in
# OPERATOR_GET_ROUTES was public "for an absent owner opening a URL", and production served
# the whole owner inbox, incident text, spend figures, job rows, gate internals and unpublished
# product slugs to anyone (`/`, `/api/owner-actions`, `/api/build`, `/api/incidents`, ...).
# The owner's surface is the authenticated Command Center (`/cc/`). The routes the deploy
# readback reads stay public but answer an unauthenticated caller with `PUBLIC_PROJECTIONS`
# only. `tests/test_w4_secpatch_public_surface.py` sweeps every public route.
PUBLIC_GET_NOTES: dict[str, str] = {
    "/": ("minimal public status page with no operational data; the full operations dashboard "
          "is served only to the operator credential (app.main.root)"),
    "/health": ("platform health check; unauthenticated callers get PUBLIC_PROJECTIONS only "
                "(status, db, build identity, worker liveness) -- ops/verify_deploy.py"),
    "/api/status": ("build identity and boot guard verdict only for unauthenticated callers "
                    "(PUBLIC_PROJECTIONS) -- ops/deployed_sha.py and ops/readback.py"),
    "/api/build": ("final_master.launch_ready only for unauthenticated callers "
                   "(PUBLIC_PROJECTIONS) -- ops/readback.py"),
    "/api/catalogue": ("`published` only for unauthenticated callers (PUBLIC_PROJECTIONS) -- "
                       "ops/readback.py"),
    "/api/etsy/oauth/callback": ("Etsy redirects the owner's browser here without a bearer "
                                 "header; guarded by a single-use state this service minted"),
    "/api/verify": ("standing verification read by the operator loop; unauthenticated callers "
                    "get each check's name and ok only (PUBLIC_PROJECTIONS) -- ops/readback.py"),
    "/api/verify/smoke": ("F-171 smoke matrix verdict and as-of only for unauthenticated "
                          "callers (PUBLIC_PROJECTIONS); read by ops/readback.py"),
    "/api/learn/metrics": ("guarded by its own Learn editor credential (learn.api._editor), "
                           "which is deliberately distinct from the operator token"),
    "/learn/{slug}": "customer-facing Learn lesson; serves owner-APPROVED lessons only",
    "/learn/{slug}/technique/{stitch}.svg": ("verified technique diagram of an APPROVED lesson "
                                             "only"),
    "/api/model-tournament/image/{sha256}": ("digest-addressed canonical reference images "
                                             "only; refuses every other stored artifact"),
    "/brand/fonts/{name}": "static brand font files",
    "/ops/teardown": "static page with no data; every request it makes carries the token",
    "/ops/teardown.js": "the static script of /ops/teardown; no data",
    "/ops/insights": "redirect to /ops/teardown#insights; no data",
}
PUBLIC_GET_ROUTES: frozenset[str] = frozenset(PUBLIC_GET_NOTES)

# What an unauthenticated caller may see of the public JSON reads: an allow-list projection
# (`project`) applied by `PublicProjectionMiddleware`, so a field added to one of these
# endpoints later stays private until somebody adds it here. Each kept field is one the deploy
# path reads (ops/verify_deploy.py, ops/deployed_sha.py, ops/readback.py) or a bare liveness
# word. `True` keeps a value; a dict keeps only those keys; a one-item list maps each element.
PUBLIC_PROJECTIONS: dict[str, object] = {
    "/health": {"status": True, "version": True, "db": True,
                "build": {"commit": True, "commit_short": True, "known": True},
                "runner": {"worker_alive": True}},
    "/api/status": {"version": True,
                    "build": {"commit": True, "commit_short": True, "known": True},
                    "boot_guard": {"enforced": True, "ok": True}},
    "/api/verify": {"ok": True, "checks": [{"check": True, "ok": True}]},
    "/api/verify/smoke": {"verdict": True, "as_of": True},
    "/api/build": {"final_master": {"launch_ready": True}},
    "/api/catalogue": {"published": True},
}

# Routers whose established contract is 403 for a refused credential (phase_api,
# publication_authority_api, activation_authority_api, ledger_mapping_api). Everything else
# answers 401 -- including `/api/owner/decision`, which is an app route, not one of these.
_FORBIDDEN_PREFIXES = ("/api/owner/phase", "/api/owner/publication/", "/api/owner/activation/",
                       "/api/owner/ledger-mapping", "/api/owner/storefront/")


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
        # W4-SECPATCH: default-deny for reads too; only PUBLIC_GET_ROUTES are open.
        return method in {"GET", "HEAD"} and (route_path in OPERATOR_GET_ROUTES
                                              or route_path not in PUBLIC_GET_ROUTES)
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


# Owner-facing pages and routes outside the JSON prefix that must carry the same owner-session
# gate (session + same-origin + CSRF + nonce for non-GET). `/cc/` itself is the public static
# PWA shell (it holds no data); these are not. `/api/store/live_observation` (W4-STORE) is the
# owner recording what the live Etsy storefront shows; it never writes to Etsy.
OWNER_SESSION_PAGES: frozenset[str] = frozenset({"/cc/store-preview",
                                                 "/cc/image-review",
                                                 "/api/store/live_observation"})


def owner_session_route(route_path: str) -> bool:
    return route_path.startswith(OWNER_SESSION_PREFIX) or route_path in OWNER_SESSION_PAGES


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


def route_path(scope) -> str:
    """The path the router matches on (`scope["path"]` without `root_path`).

    W4-SECPATCH2 (review F1): the projection and the owner-text scrub were keyed on the raw
    `scope["path"]`. Served under a root path (`--root-path`, a prefix proxy, a mount),
    `/x/api/status` routed to `api_status` but matched no projection, so an anonymous caller
    got the full body. Keying on the router's own path makes the two agree by construction."""
    from starlette.routing import get_route_path

    try:
        return get_route_path(scope) or ""
    except Exception:  # noqa: BLE001 - a malformed scope never matches a public projection
        return str(scope.get("path") or "")


def scope_authorization(scope) -> str | None:
    """The request's single Authorization header (latin-1), or None. Every layer reads it
    through here; a request with more than one is refused outright by
    `SingleAuthorizationMiddleware` before any layer sees it (review F2)."""
    found = [v for k, v in (scope.get("headers") or []) if k.lower() == b"authorization"]
    return found[0].decode("latin-1") if len(found) == 1 else None


class SingleAuthorizationMiddleware:
    """Refuse (400) any HTTP request carrying more than one Authorization header.

    W4-SECPATCH2 (review F2): the gate read the first header and the projection/scrub
    middlewares the last, so `[Bearer junk, Bearer valid]` passed the public gate and was
    then served unprojected. One header or none; never a choice between two."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and sum(
                1 for k, _v in (scope.get("headers") or [])
                if k.lower() == b"authorization") > 1:
            body = b'{"error": "more than one Authorization header", "code": "BAD_REQUEST"}'
            await send({"type": "http.response.start", "status": 400,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        return await self.app(scope, receive, send)


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
        auth = scope_authorization(scope)
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


# ---- 5. public projection (W4-SECPATCH) -------------------------------------


def project(value, spec):
    """Keep only what `spec` names (see PUBLIC_PROJECTIONS). A shape mismatch keeps nothing."""
    if spec is True:
        return value
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            return None
        return {k: project(value[k], sub) for k, sub in spec.items() if k in value}
    if isinstance(spec, list) and len(spec) == 1:
        if not isinstance(value, list):
            return None
        return [project(v, spec[0]) for v in value]
    return None


class PublicProjectionMiddleware:
    """Reduce the public JSON reads to `PUBLIC_PROJECTIONS` for a caller without the operator
    credential. Allow-list, so a field nobody reviewed never reaches the public. A body that is
    not JSON (an error page) is replaced, not passed through."""

    def __init__(self, app, projections: dict | None = None):
        self.app = app
        self.projections = PUBLIC_PROJECTIONS if projections is None else projections

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        spec = self.projections.get(route_path(scope))
        if spec is None:
            return await self.app(scope, receive, send)
        auth = scope_authorization(scope)
        if presents_operator_credential(auth):
            return await self.app(scope, receive, send)

        state: dict = {"start": None, "chunks": []}

        async def _send(message):
            if message["type"] == "http.response.start":
                state["start"] = message
                return
            if message["type"] == "http.response.body":
                state["chunks"].append(message.get("body", b""))
                if message.get("more_body"):
                    return
                start = state["start"]
                try:
                    data = _json.loads(b"".join(state["chunks"]) or b"null")
                    out = project(data, spec)
                except ValueError:
                    out = None
                if out is None:
                    out = {"error": "not available without the operator credential"}
                body = _json.dumps(out, separators=(",", ":")).encode("utf-8")
                headers = [(k, v) for k, v in start.get("headers") or []
                           if k.lower() not in (b"content-length", b"content-type")]
                headers += [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("latin-1"))]
                await send({**start, "headers": headers})
                await send({"type": "http.response.body",
                            "body": b"" if scope.get("method") == "HEAD" else body,
                            "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, _send)


# ---- 6. owner-inbox text scrub (FMBATCH1 62fcf5ed, ported by W4-SECPATCH) -----------------
#
# Defence in depth behind the read gate above. No owner-inbox text (an OwnerAction's action,
# reason, consequence, blocks or why-software-cannot; an access request's action, purpose,
# scope or consequence) and no open incident's text appears on a response to a request that
# did not present the operator credential. A full text and its first OWNER_PREFIX characters
# are both redacted, so a display that truncates a text still leaks nothing.

OWNER_REDACTED = "[owner-only: see /cc/]"
OWNER_MIN_LENGTH = 16
OWNER_PREFIX = 48


def build_owner_scrubber(texts: Iterable[str]) -> Callable[[str], str] | None:
    variants: set[str] = set()
    for t in texts:
        t = str(t or "").strip()
        if len(t) < OWNER_MIN_LENGTH:
            continue
        for v in ({t, t[:OWNER_PREFIX]} if len(t) > OWNER_PREFIX else {t}):
            variants.add(v)
            variants.add(_html.escape(v, quote=True))
    if not variants:
        return None
    pattern = re.compile("|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True)))
    return lambda text: pattern.sub(OWNER_REDACTED, text)


class OwnerTextScrubMiddleware(CustomerRefScrubMiddleware):
    """Redact owner-inbox and incident texts from unauthenticated JSON and HTML responses.

    Not on the Command Center: `/api/cc/*` and OWNER_SESSION_PAGES are refused by the owner-
    session gate to anyone without the owner's session, and the owner reading them must see
    the decisions they are asked to make, not the redaction marker."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and owner_session_route(route_path(scope)):
            return await self.app(scope, receive, send)
        return await super().__call__(scope, receive, send)

    def _scrubber(self):
        try:
            return build_owner_scrubber(self.refs_provider())
        except Exception:  # noqa: BLE001 - no database yet means no owner texts to scrub
            return None
