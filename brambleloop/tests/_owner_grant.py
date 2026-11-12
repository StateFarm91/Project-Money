"""WS4-0a test support: the owner's Command Center request, SCOPED to approve and rebase.

An owner publication/activation grant (or rebase) is signed only inside
`core.owner_grant_keys.owner_request`, which the Command Center action route enters after its
session, CSRF/nonce and step-up checks. Tests that drive the grant authorities directly (not
the route) call `scoped_owner_approvals()` once: it wraps exactly `approve` and `rebase` of
the publication and activation authorities so each call runs inside the owner request -- and
nothing else does. Review 6817118202 F1: a process-wide context made worker paths (the
completion verifier) run as if inside the owner request, which hid a verifier that re-signed.
The key pair itself comes from `_tmp.install()`. This lives in tests/ on purpose: production
code has no way to enter the context except the route.
"""
from __future__ import annotations

import functools

_DONE = {"wrapped": False}


def scoped_owner_approvals(session_public_id: str = "test-owner") -> None:
    if _DONE["wrapped"]:
        return
    from brambleloop.core import owner_grant_keys
    from brambleloop.ops import activation_authority, publication_authority

    def scoped(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            with owner_grant_keys.owner_request(session_public_id):
                return fn(*args, **kwargs)
        return inner

    for mod in (publication_authority, activation_authority):
        mod.approve = scoped(mod.approve)
        mod.rebase = scoped(mod.rebase)
    _DONE["wrapped"] = True
