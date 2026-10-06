"""Fixtures for tests/test_w3_priv_*.py. Neutral sentinel data only -- no personal content."""
from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime, timedelta, timezone

SENTINELS = tuple(f"PRIV-SENTINEL-{i:04d}" for i in range(1, 9))


def new_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def set_key(value: str | None) -> None:
    from .crypto import ENV
    if value is None:
        os.environ.pop(ENV, None)
    else:
        os.environ[ENV] = value


def owner_session(db, *, stepup: bool = True, expired: bool = False,
                  revoked: bool = False) -> str:
    from ...app.command_center.models import OwnerSession

    now = datetime.now(timezone.utc)
    pid = "s_" + secrets.token_hex(8)
    with db.session() as s:
        s.add(OwnerSession(public_id=pid, token_hash=secrets.token_hex(32),
                           device_label="test", created_at=now, last_seen_at=now,
                           expires_at=now + (timedelta(hours=-1) if expired
                                             else timedelta(hours=8)),
                           stepup_until=(now + timedelta(minutes=5)) if stepup else None,
                           revoked_at=now if revoked else None,
                           revoked_reason="test" if revoked else ""))
    return pid


def revoke(db, pid: str) -> None:
    from sqlalchemy import update

    from ...app.command_center.models import OwnerSession
    with db.session() as s:
        s.execute(update(OwnerSession).where(OwnerSession.public_id == pid)
                  .values(revoked_at=datetime.now(timezone.utc)))


def expire(db, pid: str) -> None:
    from sqlalchemy import update

    from ...app.command_center.models import OwnerSession
    with db.session() as s:
        s.execute(update(OwnerSession).where(OwnerSession.public_id == pid)
                  .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))


def private_principal(db):
    from .access import PRIVATE_FLAG, open_context
    return open_context(db, owner_session(db), flag=PRIVATE_FLAG)


def seed(db) -> dict:
    """Store every sentinel as facts and turns. Returns ids and the principal."""
    from . import store
    p = private_principal(db)
    ids = {"facts": [], "turns": []}
    for i, s in enumerate(SENTINELS[:4]):
        ids["facts"].append(store.remember(db, p, f"k{i}", s))
    t1 = store.record_turn(db, p, "owner", f"note {SENTINELS[4]} end")
    t2 = store.record_turn(db, p, "laura", f"ack {SENTINELS[5]}", reply_to=t1,
                           model_ref="provider-a/model-1")
    ids["turns"] += [t1, t2]
    ids["facts"].append(store.remember(db, p, "quoted", SENTINELS[4], provenance="interaction",
                                       sources=[t1]))
    t3 = store.record_turn(db, p, "owner", SENTINELS[6])
    ids["turns"].append(t3)
    ids["facts"].append(store.remember(db, p, "k-last", SENTINELS[7]))
    ids["principal"] = p
    return ids
