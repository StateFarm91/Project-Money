"""W3-PRIV: only a live, explicitly private owner context reaches the private store.

Principal spoofing, revoked/expired sessions, missing step-up, grant expiry and closure.
Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_priv_access.py
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from w3_laura_memory_harness import check, finish, fresh_db, raises

from brambleloop.laura import memory as lm
from brambleloop.laura.private import _testkit as kit
from brambleloop.laura.private import access, crypto, store
from brambleloop.laura.private.errors import KeyUnavailable, PrivateAccessRefused
from brambleloop.laura.private.models import PrivateAccess, PrivateGrant

KEY = kit.new_key()
kit.set_key(KEY)
OPS = [lambda db, p: store.facts(db, p),
       lambda db, p: store.conversation(db, p),
       lambda db, p: store.remember(db, p, "x", kit.SENTINELS[0]),
       lambda db, p: store.record_turn(db, p, "owner", kit.SENTINELS[0]),
       lambda db, p: store.forget(db, p, "pf_x"),
       lambda db, p: store.sealed_export(db, p)]


def _all_refused(db, principal) -> int:
    n = 0
    for op in OPS:
        try:
            op(db, principal)
        except (PrivateAccessRefused, KeyUnavailable) as e:
            assert all(s not in str(e) for s in kit.SENTINELS)
            n += 1
    return n


def test_every_non_private_principal_is_refused():
    db = fresh_db()
    kit.seed(db)
    owner_sid = kit.owner_session(db)
    from brambleloop.laura.memory.principals import verify
    verify(db, lm.Principal.owner(owner_sid))       # a genuinely verified business owner
    others = [lm.Principal.owner(owner_sid), lm.Principal.laura(),
              lm.Principal.public("store_preview"), lm.Principal.customer("c-1"),
              lm.principal_for_surface("ask_company_non_owner"),
              lm.principal_for_surface("support_draft"),
              "operator-token-placeholder", owner_sid, {"session_public_id": owner_sid},
              None, 0, object()]
    try:
        others.append(lm.Principal.department("finance"))
    except lm.PermissionRefused:
        others.append(lm.Principal("department", "finance"))
    assert len(others) >= 13
    for p in others:
        assert _all_refused(db, p) == len(OPS), p


def test_forged_and_subclassed_principals_are_refused():
    db = fresh_db()
    ids = kit.seed(db)
    real = ids["principal"]
    sid = real.session_public_id
    forged = [access.PrivatePrincipal(sid, real.grant_id, "0" * 64),
              access.PrivatePrincipal(sid, "pg_" + "1" * 32, real.tag),
              access.PrivatePrincipal(kit.owner_session(db), real.grant_id, real.tag),
              dataclasses.replace(real, tag=real.tag[:-1] + ("0" if real.tag[-1] != "0"
                                                                else "1"))]
    other_keys = crypto.load_keys({crypto.ENV: kit.new_key()})
    forged.append(access.PrivatePrincipal(sid, real.grant_id, crypto.tag(
        other_keys, "private-principal", sid, real.grant_id)))

    class Sub(access.PrivatePrincipal):
        pass
    forged.append(Sub(sid, real.grant_id, real.tag))
    # A grant on session A cannot be re-pointed at another live session B.
    b = kit.owner_session(db)
    forged.append(access.resume(db, b, real.grant_id))
    assert len(forged) == 7
    for p in forged:
        assert _all_refused(db, p) == len(OPS), p
    assert len(store.facts(db, real)) == 6           # the genuine one still works


def test_opening_requires_flag_live_session_and_fresh_stepup():
    db = fresh_db()
    ok = kit.owner_session(db)
    raises(PrivateAccessRefused, access.open_context, db, ok, flag=True)
    raises(PrivateAccessRefused, access.open_context, db, ok, flag="owner")
    raises(PrivateAccessRefused, access.open_context, db, "", flag=access.PRIVATE_FLAG)
    raises(PrivateAccessRefused, access.open_context, db, "s_missing", flag=access.PRIVATE_FLAG)
    for bad in (kit.owner_session(db, revoked=True), kit.owner_session(db, expired=True),
                kit.owner_session(db, stepup=False)):
        raises(PrivateAccessRefused, access.open_context, db, bad, flag=access.PRIVATE_FLAG)
    p = access.open_context(db, ok, flag=access.PRIVATE_FLAG)
    assert store.facts(db, p) == []
    with db.session() as s:
        g = s.scalar(select(PrivateGrant).where(PrivateGrant.grant_id == p.grant_id))
    assert g.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc) \
        + access.GRANT_TTL + timedelta(seconds=5)


def test_revoked_or_expired_session_ends_access_immediately():
    db = fresh_db()
    p = kit.private_principal(db)
    store.remember(db, p, "a", kit.SENTINELS[0])
    kit.revoke(db, p.session_public_id)
    assert _all_refused(db, p) == len(OPS)
    p2 = kit.private_principal(db)
    store.facts(db, p2)
    kit.expire(db, p2.session_public_id)
    assert _all_refused(db, p2) == len(OPS)


def test_grant_expiry_close_and_session_revocation_of_grants():
    db = fresh_db()
    p = kit.private_principal(db)
    with db.session() as s:
        s.execute(update(PrivateGrant).where(PrivateGrant.grant_id == p.grant_id)
                  .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    assert _all_refused(db, p) == len(OPS)
    p2 = kit.private_principal(db)
    assert access.close_context(db, p2) is True
    assert _all_refused(db, p2) == len(OPS)
    p3 = kit.private_principal(db)
    assert access.revoke_session_contexts(db, p3.session_public_id) == 1
    assert _all_refused(db, p3) == len(OPS)


def test_refusals_are_logged_privately_without_content():
    db = fresh_db()
    kit.seed(db)
    _all_refused(db, lm.Principal.laura())
    with db.session() as s:
        rows = list(s.scalars(select(PrivateAccess).where(PrivateAccess.outcome == "refused")))
    assert len(rows) >= len(OPS)
    blob = " ".join(f"{r.op}|{r.reason}|{r.principal_type}" for r in rows)
    assert "PrivateAccessRefused" in blob and "Principal" in blob
    assert all(s not in blob for s in kit.SENTINELS)


def test_principal_does_not_leak_through_repr_or_serialisation():
    import json
    import pickle
    db = fresh_db()
    p = kit.private_principal(db)
    assert p.tag not in repr(p) and p.grant_id not in str(p)
    raises(TypeError, pickle.dumps, p)
    raises(TypeError, json.dumps, p)


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
