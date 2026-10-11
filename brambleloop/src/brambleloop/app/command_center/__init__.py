"""Owner Command Center (v1.1 lane C): `/api/cc/*` JSON API + `/cc/` static PWA.

`install(app, db)` is the single mount point used by `app/main.py`:

* registers `auth.gate` as the owner-session verifier inside `security.operator_gate`
  (default-deny for every `/api/cc/*` route);
* registers the refusal handler (JSON `{"error", "code"}`);
* includes the API router;
* mounts `static/` at `/cc/` behind a strict, inline-free Content-Security-Policy.

See `research/final_build/v1_1/COMMAND_CENTER_API.md` for the contract.
"""
from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"

CC_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; manifest-src 'self'; worker-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'")


class _StrictStatic:
    """Wraps the static app so every `/cc/` response carries the command center's CSP."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers") or []
                           if k.lower() not in (b"content-security-policy", b"cache-control")]
                headers.append((b"content-security-policy",
                                CC_CONTENT_SECURITY_POLICY.encode("latin-1")))
                headers.append((b"cache-control", b"no-cache"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, _send)


CC_ROOT = "/cc/"


async def cc_slash_redirect(request):
    """`/cc` -> `/cc/` with a *relative* Location (W4-CCUX).

    Starlette's own trailing-slash redirect builds an absolute URL from the scheme the app sees.
    Behind Railway's TLS-terminating edge that scheme is `http`, so the owner's phone was sent
    to `http://<host>/cc/` and only then bounced back to https (a plaintext hop, and a mixed-
    scheme warning on some browsers). A path-only Location is resolved by the browser against
    the URL it actually requested, so the scheme and host are whatever the trusted edge served
    -- correct with or without `X-Forwarded-Proto`, and with nothing taken from a client-
    supplied Host or forwarding header. The query string is kept; the path is fixed, so this
    cannot be turned into an open redirect.
    """
    from starlette.responses import Response

    query = request.url.query
    location = CC_ROOT + (f"?{query}" if query else "")
    return Response(status_code=308, headers={"location": location, "cache-control": "no-store"})


def install(app, db) -> None:
    from starlette.staticfiles import StaticFiles

    from .. import security
    from . import auth
    from .api import make_router
    from .models import ensure_tables

    try:
        ensure_tables(db)
    except Exception:  # noqa: BLE001 - created lazily on first use otherwise
        pass
    security.register_owner_session_gate(lambda request, path: auth.gate(db, request, path))
    app.add_exception_handler(auth.CCRefused, auth.refused_handler)
    app.include_router(make_router(db))
    # Before the static mount, so the route wins; owner-session gated (security.py).
    from .api import STORE_PREVIEW_PATH, store_preview_handler

    app.add_api_route(STORE_PREVIEW_PATH, store_preview_handler(db), methods=["GET"],
                      include_in_schema=False)
    # W4-STORE wiring: owner-session gated (security.OWNER_SESSION_PAGES), CSRF + nonce.
    from .api import LIVE_OBSERVATION_PATH, live_observation_handler

    app.add_api_route(LIVE_OBSERVATION_PATH, live_observation_handler(db), methods=["POST"],
                      include_in_schema=False)
    # Operator-credential gated (not under /api/cc/): owner lockout recovery (M1).
    from .api import LOGIN_RECOVERY_PATH, login_recovery_handler

    app.add_api_route(LOGIN_RECOVERY_PATH, login_recovery_handler(db), methods=["POST"],
                      include_in_schema=False)
    # W4-CCUX: scheme-correct `/cc` -> `/cc/` (relative Location; see cc_slash_redirect).
    # A plain Starlette route: it serves no data, like the static mount below.
    app.add_route("/cc", cc_slash_redirect, methods=["GET", "HEAD"], include_in_schema=False)
    STATIC_DIR.mkdir(exist_ok=True)
    app.mount("/cc", _StrictStatic(StaticFiles(directory=str(STATIC_DIR), html=True)),
              name="command_center_static")
