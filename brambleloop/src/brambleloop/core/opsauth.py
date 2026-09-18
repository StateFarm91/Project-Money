"""The operator credential for endpoints that must never be open.

Requirement 51 asks for cloud-side backup; the owner's Build-2 authorization adds the
constraint that matters more than the feature: do not expose `DATABASE_URL` or other
production secrets "through logs, repository files or unauthenticated endpoints."

So anything that can return database contents authenticates through here. Three properties,
each chosen against a specific way this goes wrong:

**Absent means closed, not open.** If `BRAMBLELOOP_OPS_TOKEN` is unset the endpoint refuses
everyone. The opposite default -- open until configured -- is how a backup endpoint ends up
serving the whole company to the internet during the window between deploying it and
remembering to set the variable.

**Constant-time comparison.** A plain `==` on a secret leaks its prefix to anyone willing to
measure, which turns a 32-character token into a short search.

**Never echoed.** The token is not logged, not returned in an error, and not included in any
audit detail. A refusal says only that it was refused.
"""
from __future__ import annotations

import hmac
import os

TOKEN_VAR = "BRAMBLELOOP_OPS_TOKEN"

# Short tokens invite guessing. This is checked at use time rather than trusted, because a
# placeholder like "changeme" is exactly what gets left in an environment variable.
MIN_TOKEN_LENGTH = 24


class OpsAuthUnavailable(RuntimeError):
    """No operator token is configured, so the endpoint cannot be used by anyone."""


class OpsAuthRefused(PermissionError):
    """A credential was presented and did not match."""


def configured(env: dict[str, str] | None = None) -> bool:
    e = env if env is not None else os.environ
    return len((e.get(TOKEN_VAR) or "").strip()) >= MIN_TOKEN_LENGTH


def token_health(env: dict[str, str] | None = None) -> dict:
    """Whether the credential is usable, without revealing anything about its value."""
    e = env if env is not None else os.environ
    raw = (e.get(TOKEN_VAR) or "").strip()
    return {
        "configured": bool(raw),
        "usable": len(raw) >= MIN_TOKEN_LENGTH,
        "min_length": MIN_TOKEN_LENGTH,
        "reason": ("" if len(raw) >= MIN_TOKEN_LENGTH
                   else "not set" if not raw
                   else f"shorter than {MIN_TOKEN_LENGTH} characters"),
    }


def check(presented: str | None, env: dict[str, str] | None = None) -> None:
    """Raise unless `presented` is the configured operator token.

    Accepts either a bare token or an `Authorization: Bearer <token>` header value, so the
    caller does not have to parse it and get that wrong.
    """
    e = env if env is not None else os.environ
    expected = (e.get(TOKEN_VAR) or "").strip()
    if len(expected) < MIN_TOKEN_LENGTH:
        raise OpsAuthUnavailable(
            f"{TOKEN_VAR} is not set to a usable value, so this endpoint is closed. It is "
            f"set in the hosting environment, never in this repository.")

    supplied = (presented or "").strip()
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise OpsAuthRefused("operator credential rejected")
