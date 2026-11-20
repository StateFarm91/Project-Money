"""W4-PRIVLAURA (PL-6): only a live owner session with a fresh step-up and an open private
context gets a reply; every other caller is refused BEFORE any model call, reservation or
spend; a missing or bad key is 503 and nothing is spent.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_pl_auth.py
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import w3_laura_cc_harness as H  # noqa: E402
import w4_pl_harness as PL  # noqa: E402

from sqlalchemy import select, update  # noqa: E402

from brambleloop.core.models import AuditLog, CostEntry, SpendReservation  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402
from brambleloop.laura.private import store  # noqa: E402
from brambleloop.laura.private.errors import PrivateAccessRefused  # noqa: E402
from brambleloop.laura.private.models import PrivateGrant  # noqa: E402

DB = H.DB
S = kit.SENTINELS
KEY = kit.new_key()
kit.set_key(KEY)


def _money_rows() -> tuple[int, int, int]:
    with DB.session() as s:
        return (len(list(s.scalars(select(CostEntry)))),
                len(list(s.scalars(select(SpendReservation)))),
                len(list(s.scalars(select(AuditLog).where(
                    AuditLog.action == "spend.refused")))))


def _open(c, csrf) -> str:
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
    return c.get("/api/cc/auth/status").json()["session"]["session_id"]


def test_only_a_fresh_stepup_owner_session_gets_a_reply():
    from brambleloop.laura.memory import Principal

    money = _money_rows()
    with PL.enabled(None):            # any model request fails this test
        anon = H.client()
        assert anon.post("/api/cc/private/turn", json={"text": S[0]}).status_code in (401, 403)
        op = H.client()
        r = op.post("/api/cc/private/turn", json={"text": S[0]},
                    headers={"Authorization": f"Bearer {H.OPS}"})
        assert r.status_code in (401, 403), r.status_code       # the operator token is not
        c, csrf = H.session()                                   # an owner session
        r = H.post(c, csrf, "/api/cc/private/turn", {"text": S[0]})   # session, not opened
        assert r.status_code == 403 and r.json()["code"] == "PRIVATE_REFUSED", r.text
        H.expire_stepup(c)
        r = H.post(c, csrf, "/api/cc/private/open", {})                # stale step-up
        assert r.status_code == 403, r.text
        # A verified BUSINESS owner principal is not a private principal.
        owner_sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
        for bad in (Principal.owner(owner_sid), Principal.laura(), "owner",
                    {"session": owner_sid}, None):
            try:
                store.record_turn(DB, bad, "owner", S[1])
                raise AssertionError(f"{type(bad).__name__} reached the private store")
            except PrivateAccessRefused:
                pass
        # An expired grant on an otherwise live session.
        c2, csrf2 = H.session()
        sid2 = _open(c2, csrf2)
        with DB.session() as s:
            s.execute(update(PrivateGrant).where(PrivateGrant.session_public_id == sid2)
                      .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        r = H.post(c2, csrf2, "/api/cc/private/turn", {"text": S[2]})
        assert r.status_code == 403 and S[2] not in r.text, r.text
        # Another session cannot use this session's open context.
        c3, csrf3 = H.session()
        _open(c3, csrf3)
        c4, csrf4 = H.session()
        r = H.post(c4, csrf4, "/api/cc/private/turn", {"text": S[3]})
        assert r.status_code == 403, r.text
    assert _money_rows() == money, (money, _money_rows())       # nothing reserved or billed
    # Positive control: the same opened session does get a reply once enabled.
    stub = PL.Stub()
    with PL.enabled(stub):
        out = H.post(c3, csrf3, "/api/cc/private/turn", {"text": S[4]}).json()
    assert out["reply_status"] == "REPLIED" and len(stub.calls) == 1, out


def test_missing_or_bad_key_is_503_and_no_model_call():
    c, csrf = H.session()
    _open(c, csrf)
    money = _money_rows()
    try:
        for bad in (None, "", "AAAA", "A" * 44):     # absent, empty, short, degenerate
            kit.set_key(bad)
            with PL.enabled(None):
                st = c.get("/api/cc/private/status").json()
                assert st["configured"] is False and st["reply_register"] == "GATED", st
                r = H.post(c, csrf, "/api/cc/private/turn", {"text": S[5]})
                assert r.status_code == 503 and r.json()["code"] == "PRIVATE_UNAVAILABLE", \
                    (bad and len(bad), r.text)
                assert S[5] not in r.text
        assert _money_rows() == money                # refused before any spend or reservation
    finally:
        kit.set_key(KEY)
    assert os.environ.get("ANTHROPIC_API_KEY") is None


if __name__ == "__main__":
    H.run(globals())
