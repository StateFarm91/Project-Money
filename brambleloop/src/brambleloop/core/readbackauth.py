"""W4-READBACK: the read-only readback credential, separate from the operator token.

`GET /api/readback/evidence` serves projected production evidence (`ops.production_evidence`)
to an operator loop that must not hold the operator credential: the operator token can
export, write and exercise authority, and a verifier needs none of that. So this is a second,
narrower credential with the same three rules as `core.opsauth`, plus two of its own:

* **Absent means closed.** `BRAMBLELOOP_READBACK_TOKEN` unset, or shorter than
  `MIN_TOKEN_LENGTH`, closes the endpoint to everyone (503).
* **Constant-time comparison**, on bytes (a non-ASCII header is a refusal, never a 500).
* **Never echoed**: not logged, not returned, not in any audit detail.
* **Never the operator token.** If the configured value equals `BRAMBLELOOP_OPS_TOKEN` the
  credential is treated as not configured (a shared value would make the read-only token an
  operator token), and a presented operator token is refused here outright.
* **Grants nothing else.** `app.security.operator_gate` consults this module for
  `READBACK_ROUTES` only; every other route still checks `core.opsauth`, which this value
  never matches. No export, write or authority action can use it.
"""
from __future__ import annotations

import hmac
import os

from . import opsauth

TOKEN_VAR = "BRAMBLELOOP_READBACK_TOKEN"
MIN_TOKEN_LENGTH = 32


class ReadbackAuthUnavailable(RuntimeError):
    """No usable readback token is configured, so the endpoint is closed to everyone."""


class ReadbackAuthRefused(PermissionError):
    """A credential was presented and is not the readback token."""


def _b(value: str) -> bytes:
    return value.encode("utf-8", "surrogatepass")


def _same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(_b(a), _b(b))


def _expected(e) -> str:
    raw = (e.get(TOKEN_VAR) or "").strip()
    if len(raw) < MIN_TOKEN_LENGTH:
        return ""
    if _same(raw, (e.get(opsauth.TOKEN_VAR) or "").strip()):
        return ""
    return raw


def configured(env: dict[str, str] | None = None) -> bool:
    return bool(_expected(env if env is not None else os.environ))


def token_health(env: dict[str, str] | None = None) -> dict:
    """Whether the credential is usable, without revealing anything about its value."""
    e = env if env is not None else os.environ
    raw = (e.get(TOKEN_VAR) or "").strip()
    shared = bool(raw) and _same(raw, (e.get(opsauth.TOKEN_VAR) or "").strip())
    usable = len(raw) >= MIN_TOKEN_LENGTH and not shared
    return {"configured": bool(raw), "usable": usable, "min_length": MIN_TOKEN_LENGTH,
            "reason": ("" if usable else "not set" if not raw
                       else "equal to the operator token" if shared
                       else f"shorter than {MIN_TOKEN_LENGTH} characters")}


def check(presented: str | None, env: dict[str, str] | None = None) -> None:
    """Raise unless `presented` is the configured readback token (bare or `Bearer <t>`)."""
    e = env if env is not None else os.environ
    expected = _expected(e)
    if not expected:
        raise ReadbackAuthUnavailable(
            f"{TOKEN_VAR} is not set to a usable value, so this endpoint is closed. It is set "
            f"in the hosting environment, never in this repository, and it must differ from "
            f"the operator token.")
    supplied = (presented or "").strip()
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    if _same(supplied, (e.get(opsauth.TOKEN_VAR) or "").strip()):
        raise ReadbackAuthRefused("readback credential required")
    if not _same(supplied, expected):
        raise ReadbackAuthRefused("readback credential required")
