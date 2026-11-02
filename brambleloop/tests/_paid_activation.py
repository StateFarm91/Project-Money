"""V0 test helper: the owner's explicit activation of a paid provider, recorded for real.

Since V0, a provider key is a credential, not an activation: no paid image or vision call is
made until the owner activates that provider for that scope through the Command Center (a
step-up-verified owner session, `paid_provider_gate.activate`). A test whose subject is the
behaviour AFTER activation calls `activate` first; a test about the gate itself never does.
The activation is the real record -- the owner session row and `G.activate` -- not a patch.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone


def owner_session(db) -> str:
    from brambleloop.app.command_center import auth as cc_auth
    from brambleloop.app.command_center.models import OwnerSession

    cc_auth.ensure_tables(db)
    now = datetime.now(timezone.utc)
    pid = "s_" + secrets.token_hex(8)
    with db.session() as s:
        s.add(OwnerSession(public_id=pid, token_hash=secrets.token_hex(32), created_at=now,
                           last_seen_at=now, expires_at=now + timedelta(days=1),
                           stepup_until=now + timedelta(minutes=5)))
    return pid


def activate(db, provider: str, *scopes: str, daily: float = 5.0, monthly: float = 20.0,
             per_gallery: float = 5.0) -> list[dict]:
    """Activate `provider` for each scope (default: every scope it has), as the owner."""
    from brambleloop.gateway import paid_provider_gate as G

    out = []
    for scope in scopes or G.scopes_for(provider):
        out.append(G.activate(db, provider=provider, scope=scope, by="owner:test",
                              session_public_id=owner_session(db), daily_ceiling_cad=daily,
                              monthly_ceiling_cad=monthly, per_gallery_cad=per_gallery))
    return out
