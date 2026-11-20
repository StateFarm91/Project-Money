"""W4-SECPATCH: read an owner-only GET route the way the operator does.

Every GET not on `security.PUBLIC_GET_ROUTES` now needs the operator credential. A test that
exercises what such a route *computes* reads it with `get(client, path)`: the operator token
is configured for the duration of the call (the file's own token if it set one) and presented.
Tests about the refusal itself keep calling `client.get(path)` without it.
"""
from __future__ import annotations

import os

# Read lazily: a test file imports this before it has put `src` on the path or set its env.
TOKEN_VAR = "BRAMBLELOOP_OPS_TOKEN"
DEFAULT_TOKEN = "w4-secpatch-operator-test-token-0123456789"


def headers(extra: dict | None = None) -> dict:
    token = os.environ.get(TOKEN_VAR) or DEFAULT_TOKEN
    return {**(extra or {}), "Authorization": f"Bearer {token}"}


def get(client, path: str, **kw):
    _check_var()
    prev = os.environ.get(TOKEN_VAR)
    token = prev or DEFAULT_TOKEN
    os.environ[TOKEN_VAR] = token
    try:
        h = {**(kw.pop("headers", None) or {}), "Authorization": f"Bearer {token}"}
        return client.get(path, headers=h, **kw)
    finally:
        if prev is None:
            os.environ.pop(TOKEN_VAR, None)


def _check_var() -> None:
    from brambleloop.core import opsauth

    assert opsauth.TOKEN_VAR == TOKEN_VAR, opsauth.TOKEN_VAR
