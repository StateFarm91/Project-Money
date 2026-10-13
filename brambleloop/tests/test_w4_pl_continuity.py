"""W4-PRIVLAURA (PL-8, PL-9, G-11): one Laura across restart, model change and a new grant, and
key rotation through the existing sealed backup path.

* restart = a new Database engine on the same file, a new owner session and a new private grant;
  the reply model changes (a different `model_ref`); the history and notes are the same, the
  earlier turns feed the next reply, and the identity record and the pinned prompt are unchanged;
* `store.rekey`: sealed_export (old key) -> re-seal -> replace; the old key can no longer read,
  the new key reads the same history, and `restore_sealed` accepts the rotated bundle.

Direct calls (no HTTP); stubbed transport; neutral sentinels only.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_pl_continuity.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit

import json
import os
import tempfile

from w3_laura_memory_harness import check, finish, fresh_db, raises, reopen
import w4_pl_harness as PL

from brambleloop.agents.registry import Registry
from brambleloop.app.command_center import private_context
from brambleloop.gateway import laura_register
from brambleloop.laura.core import identity
from brambleloop.laura.private import _testkit as kit
from brambleloop.laura.private import crypto, store
from brambleloop.laura.private.errors import (KeyMismatch, PrivateAccessRefused,
                                              PrivateRefused)

S = kit.SENTINELS
TMP = tempfile.mkdtemp(prefix="w4pl-cont-")


def _boot(path: str):
    db = fresh_db(path)
    Registry(db).seed_defaults()
    return db


def _session(db) -> str:
    sid = kit.owner_session(db)
    assert private_context.open_(db, sid)["open"] is True
    return sid


def test_restart_and_model_change_keep_one_laura():
    kit.set_key(kit.new_key())
    path = os.path.join(TMP, "restart.sqlite")
    db1 = _boot(path)
    ident_before = identity.current(db1)["sha256"]
    system_before = laura_register.PROMPT.system
    sid1 = _session(db1)
    private_context.remember(db1, sid1, "PRIV-LABEL-CONT", S[0])
    with PL.enabled(PL.Stub(model="claude-sonnet-5")):
        a = private_context.owner_turn(db1, sid1, S[1])
    assert a["reply_status"] == "REPLIED", a
    db1.engine.dispose()

    db2 = reopen(path)                                   # a new engine, no create_all
    sid2 = _session(db2)                                 # a new session and a new grant
    stub = PL.Stub(answers=[json.dumps({"text": "PRIV-SENTINEL-REPLY-0002"})],
                   model="claude-sonnet-5-20270101")      # the model behind the tier changed
    with PL.enabled(stub):
        b = private_context.owner_turn(db2, sid2, S[2])
    assert b["reply_status"] == "REPLIED", b
    user = stub.calls[0]["messages"][0]["content"]
    assert S[0] in user and S[1] in user and PL.REPLY in user, "memory did not feed cognition"
    v = private_context.view(db2, sid2)
    turns = [(t["role"], t["text"]) for t in v["conversation"]]
    assert turns == [("owner", S[1]), ("laura", PL.REPLY), ("owner", S[2]),
                     ("laura", "PRIV-SENTINEL-REPLY-0002")], turns
    assert any(f["text"] == S[0] for f in v["facts"])
    p = private_context._principal(db2, sid2)
    refs = [t.model_ref for t in store.conversation(db2, p) if t.role == "laura"]
    assert refs == ["anthropic/claude-sonnet-5", "anthropic/claude-sonnet-5-20270101"], refs
    # Same Laura: the identity record and the pinned register prompt did not move.
    assert identity.current(db2)["sha256"] == ident_before == identity.CURRENT_SHA256
    assert laura_register._system() == system_before == laura_register.PROMPT.system
    assert identity.public_profile()["visual_identity_id"] == "laura-r2-a42aeac7"


def test_key_rotation_via_sealed_export_restore():
    old_key, new_key = kit.new_key(), kit.new_key()
    kit.set_key(old_key)
    db = _boot(os.path.join(TMP, "rekey.sqlite"))
    sid = _session(db)
    private_context.remember(db, sid, "PRIV-LABEL-ROT", S[3])
    with PL.enabled(PL.Stub()):
        assert private_context.owner_turn(db, sid, S[4])["reply_status"] == "REPLIED"
    p = private_context._principal(db, sid)
    before = [(t.role, t.value.reveal(), t.reply_to, t.model_ref, t.created_at)
              for t in store.conversation(db, p)]
    facts_before = [(f.key.reveal(), f.value.reveal()) for f in store.facts(db, p)]
    raises(KeyMismatch, store.rekey, db, p, {crypto.ENV: old_key})       # same key refused
    raises(PrivateRefused, store.rekey, db, "owner", {crypto.ENV: new_key})  # no principal
    out = store.rekey(db, p, {crypto.ENV: new_key})
    assert out["rotated"] == len(before) + len(facts_before) and out["grants_revoked"]
    assert out["old_key_id"] != out["new_key_id"]
    blob = json.dumps({k: v for k, v in out.items() if k != "bundle"})
    assert not [x for x in S if x in blob] and old_key not in blob and new_key not in blob
    assert not [x for x in S if x in json.dumps(out["bundle"])]          # ciphertext only
    # The old grant is revoked; the old key cannot read the rotated rows.
    raises(PrivateAccessRefused, store.facts, db, p)
    sid_old = _session(db)                               # still the old key in the env
    raises(KeyMismatch, store.facts, db, private_context._principal(db, sid_old))
    # The new key reads the same history, links and provenance intact; replies continue.
    kit.set_key(new_key)
    sid_new = _session(db)
    p2 = private_context._principal(db, sid_new)
    after = [(t.role, t.value.reveal(), t.reply_to, t.model_ref, t.created_at)
             for t in store.conversation(db, p2)]
    assert after == before, (after, before)
    assert [(f.key.reveal(), f.value.reveal()) for f in store.facts(db, p2)] == facts_before
    assert [f.value.reveal() for f in store.facts(db, p2, "PRIV-LABEL-ROT")] == [S[3]]
    with PL.enabled(PL.Stub()):
        assert private_context.owner_turn(db, sid_new, S[5])["reply_status"] == "REPLIED"
    # restore_sealed accepts the rotated bundle under the new key, into a fresh database.
    fresh = _boot(os.path.join(TMP, "restored.sqlite"))
    sid_f = _session(fresh)
    pf = private_context._principal(fresh, sid_f)
    assert store.restore_sealed(fresh, pf, out["bundle"]) == out["rotated"]
    assert [t.value.reveal() for t in store.conversation(fresh, pf)] == [b[1] for b in before]


def test_key_missing_after_restart_means_no_reply_and_no_spend():
    from sqlalchemy import select

    from brambleloop.app.command_center.private_context import PrivateUnavailable
    from brambleloop.core.models import CostEntry, SpendReservation

    key = kit.new_key()
    kit.set_key(key)
    path = os.path.join(TMP, "nokey.sqlite")
    db1 = _boot(path)
    sid = _session(db1)
    with PL.enabled(PL.Stub()):
        assert private_context.owner_turn(db1, sid, S[6])["reply_status"] == "REPLIED"
    db1.engine.dispose()
    kit.set_key(None)
    try:
        db2 = reopen(path)
        with PL.enabled(None):            # any model request fails this test
            for fn in (lambda: private_context.owner_turn(db2, sid, S[7]),
                       lambda: private_context.view(db2, sid),
                       lambda: private_context.open_(db2, kit.owner_session(db2))):
                try:
                    fn()
                    raise AssertionError("the private context answered without its key")
                except PrivateUnavailable as exc:
                    assert exc.status == 503 and exc.code == "PRIVATE_UNAVAILABLE"
        assert private_context.status(db2, sid)["configured"] is False
        with db2.session() as s_:
            assert len(list(s_.scalars(select(CostEntry)))) == 1      # only the first reply
            assert all(r.released_at is not None for r in s_.scalars(select(SpendReservation)))
    finally:
        kit.set_key(key)
    sid2 = _session(reopen(path))                  # the key back: the history is intact
    v = private_context.view(reopen(path), sid2)
    assert [t["text"] for t in v["conversation"]] == [S[6], PL.REPLY]


check("test_key_missing_after_restart_means_no_reply_and_no_spend",
      test_key_missing_after_restart_means_no_reply_and_no_spend)
check("test_restart_and_model_change_keep_one_laura", test_restart_and_model_change_keep_one_laura)
check("test_key_rotation_via_sealed_export_restore", test_key_rotation_via_sealed_export_restore)
finish()
