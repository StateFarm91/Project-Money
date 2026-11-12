"""WS4-0a test support: act as the owner's Command Center request for the rest of this thread.

An owner publication/activation grant (or rebase) is signed only inside
`core.owner_grant_keys.owner_request`, which the Command Center action route enters after its
session, CSRF/nonce and step-up checks. Tests that exercise the grant authorities directly (not
the route) call `as_owner()` once; the key pair itself comes from `_tmp.install()`. This lives
in tests/ on purpose: production code has no way to enter the context except the route.
"""
from __future__ import annotations


def as_owner(session_public_id: str = "test-owner") -> None:
    from brambleloop.core import owner_grant_keys

    owner_grant_keys._OWNER_REQUEST.set(session_public_id)
