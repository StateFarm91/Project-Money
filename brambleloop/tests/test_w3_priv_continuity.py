"""W3-PRIV: the private context survives restart and model swap; it is never decrypted
without the key; an owner-held sealed backup restores into a fresh database.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_priv_continuity.py
"""
from __future__ import annotations

import json
import tempfile

from w3_laura_memory_harness import TMPDIRS, check, finish, fresh_db, raises

from brambleloop.core.db import Database
from brambleloop.laura.private import _testkit as kit
from brambleloop.laura.private import store
from brambleloop.laura.private.errors import (IntegrityRefused, KeyMismatch, KeyUnavailable,
                                              PrivateAccessRefused)

KEY = kit.new_key()
S = kit.SENTINELS


def _path():
    td = tempfile.TemporaryDirectory(prefix="w3priv-cont-")
    TMPDIRS.append(td)
    return f"{td.name}/c.sqlite"


def test_restart_and_model_swap_keep_the_same_context():
    kit.set_key(KEY)
    path = _path()
    db1 = fresh_db(path)
    p1 = kit.private_principal(db1)
    store.remember(db1, p1, "k", S[0])
    o1 = store.record_turn(db1, p1, "owner", S[1])
    store.record_turn(db1, p1, "laura", S[2], reply_to=o1, model_ref="provider-a/model-1")
    db1.engine.dispose()
    del db1, p1                                          # "process restart"
    db2 = Database(f"sqlite:///{path}")                  # new engine, new session, new grant
    p2 = kit.private_principal(db2)
    o2 = store.record_turn(db2, p2, "owner", S[3])
    store.record_turn(db2, p2, "laura", S[4], reply_to=o2, model_ref="provider-b/model-2")
    conv = store.conversation(db2, p2)
    assert [t.value.reveal() for t in conv] == list(S[1:5])
    assert [t.model_ref for t in conv] == [None, "provider-a/model-1", None,
                                           "provider-b/model-2"]
    assert store.facts(db2, p2, "k")[0].value.reveal() == S[0]


def test_after_restart_without_the_key_nothing_is_readable():
    kit.set_key(KEY)
    path = _path()
    db1 = fresh_db(path)
    p1 = kit.private_principal(db1)
    store.remember(db1, p1, "k", S[5])
    db1.engine.dispose()
    kit.set_key(None)
    try:
        db2 = Database(f"sqlite:///{path}")
        raises(KeyUnavailable, store.facts, db2, p1)
        raises(KeyUnavailable, kit.private_principal, db2)
        assert not store.configured()
    finally:
        kit.set_key(KEY)
    assert store.facts(Database(f"sqlite:///{path}"), p1)[0].value.reveal() == S[5]


def test_sealed_backup_restores_into_a_fresh_database_with_the_same_key():
    kit.set_key(KEY)
    db1 = fresh_db()
    ids = kit.seed(db1)
    bundle = store.sealed_export(db1, ids["principal"])
    text = json.dumps(bundle)
    assert len(bundle["rows"]) == 9
    assert not [s for s in S if s in text], "sealed export holds plaintext"
    db2 = fresh_db()
    p2 = kit.private_principal(db2)
    assert store.restore_sealed(db2, p2, bundle) == 9
    assert store.restore_sealed(db2, p2, bundle) == 0                 # idempotent
    assert len(store.facts(db2, p2)) == 6 and len(store.conversation(db2, p2)) == 3
    # Tampered bundle row and wrong-key restore are refused.
    bad = json.loads(text)
    bad["rows"][0]["provenance"] = "interaction" if bad["rows"][0]["provenance"] != \
        "interaction" else "owner_supplied"
    raises(IntegrityRefused, store.restore_sealed, db2, p2, bad)
    kit.set_key(kit.new_key())
    try:
        db3 = fresh_db()
        raises(KeyMismatch, store.restore_sealed, db3, kit.private_principal(db3), bundle)
        raises(PrivateAccessRefused, store.restore_sealed, db2, p2, bundle)
    finally:
        kit.set_key(KEY)


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
