"""W3-PRIV: the private store encrypts at rest, refuses without a key, detects tampering.

Neutral sentinel data only. Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_priv_store.py
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

from sqlalchemy import select, text, update
from w3_laura_memory_harness import check, finish, fresh_db, raises

from brambleloop.core.db import Base
from brambleloop.laura.private import _testkit as kit
from brambleloop.laura.private import crypto, store
from brambleloop.laura.private.errors import (IntegrityRefused, KeyMismatch, KeyUnavailable,
                                              PrivateAccessRefused)
from brambleloop.laura.private.models import TABLES, PrivateEntry
from brambleloop.laura.private.values import PrivateValue

KEY = kit.new_key()
kit.set_key(KEY)


def _db_bytes(db) -> bytes:
    path = Path(db.engine.url.database)
    with db.engine.connect() as c:          # flush WAL into the main file
        c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    blob = path.read_bytes()
    for extra in (path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        if extra.exists():
            blob += extra.read_bytes()
    return blob


def test_roundtrip_returns_private_values():
    kit.set_key(KEY)
    db = fresh_db()
    ids = kit.seed(db)
    got = store.facts(db, ids["principal"])
    assert len(got) == 6, len(got)
    vals = {r.value.reveal() for r in got}
    assert set(kit.SENTINELS[:4]) <= vals and kit.SENTINELS[7] in vals
    assert all(isinstance(r.value, PrivateValue) for r in got)
    conv = store.conversation(db, ids["principal"])
    assert [r.role for r in conv] == ["owner", "laura", "owner"]
    assert conv[1].reply_to == conv[0].record_id and conv[1].model_ref == "provider-a/model-1"
    one = store.facts(db, ids["principal"], "k1")
    assert len(one) == 1 and one[0].value.reveal() == kit.SENTINELS[1]


def test_content_is_encrypted_at_rest():
    kit.set_key(KEY)
    db = fresh_db()
    kit.seed(db)
    blob = _db_bytes(db)
    assert len(blob) > 1000
    hits = [s for s in kit.SENTINELS if s.encode() in blob]
    assert not hits, hits
    for label in (b"k0", b"quoted", b"provider-a/model-1"):
        assert label not in blob, label           # keys and model refs are inside ciphertext
    with db.session() as s:
        rows = list(s.scalars(select(PrivateEntry)))
    assert len(rows) == 9
    for r in rows:
        assert r.scheme == "aesgcm256-v1" and len(r.ciphertext) > 20


def test_missing_key_refuses_and_writes_nothing():
    kit.set_key(KEY)
    db = fresh_db()
    p = kit.private_principal(db)
    store.remember(db, p, "a", kit.SENTINELS[0])
    kit.set_key(None)
    try:
        e = raises(KeyUnavailable, store.remember, db, p, "b", kit.SENTINELS[1])
        assert kit.SENTINELS[1] not in str(e)
        raises(KeyUnavailable, store.facts, db, p)
        raises(KeyUnavailable, store.record_turn, db, p, "owner", kit.SENTINELS[2])
        from brambleloop.laura.private.access import PRIVATE_FLAG, open_context
        raises(KeyUnavailable, open_context, db, kit.owner_session(db), flag=PRIVATE_FLAG)
    finally:
        kit.set_key(KEY)
    with db.session() as s:
        assert s.scalar(select(text("count(*)")).select_from(PrivateEntry)) == 1


def test_weak_or_malformed_keys_are_refused():
    import base64
    for bad in ("", "   ", "not base64 !!", base64.b64encode(b"x" * 16).decode(),
                base64.b64encode(b"\x00" * 32).decode()):
        raises(KeyUnavailable, crypto.load_keys, {crypto.ENV: bad})
    k = crypto.load_keys({crypto.ENV: KEY})
    assert KEY not in repr(k) and "enc" not in str(k).replace("key_id", "")


def test_tampered_ciphertext_and_metadata_are_refused():
    kit.set_key(KEY)
    db = fresh_db()
    ids = kit.seed(db)
    p = ids["principal"]
    target = ids["facts"][0]
    with db.session() as s:
        row = s.scalar(select(PrivateEntry).where(PrivateEntry.record_id == target))
        ct = bytearray(__import__("base64").b64decode(row.ciphertext))
        ct[3] ^= 0x01
        row.ciphertext = __import__("base64").b64encode(bytes(ct)).decode()
    e = raises(IntegrityRefused, store.facts, db, p)
    assert all(s not in str(e) for s in kit.SENTINELS)
    store.forget(db, p, target)
    store.facts(db, p)                                # clean again
    # Relabelling bound metadata (provenance) fails authentication too.
    with db.session() as s:
        s.execute(update(PrivateEntry).where(PrivateEntry.record_id == ids["facts"][1])
                  .values(provenance="interaction"))
    raises(IntegrityRefused, store.facts, db, p)
    store.forget(db, p, ids["facts"][1])
    # Swapping two rows' ciphertexts (moving content) fails too.
    with db.session() as s:
        a, b = [s.scalar(select(PrivateEntry).where(PrivateEntry.record_id == r))
                for r in ids["facts"][2:4]]
        a.nonce, b.nonce, a.ciphertext, b.ciphertext = b.nonce, a.nonce, b.ciphertext, a.ciphertext
    raises(IntegrityRefused, store.facts, db, p)


def test_a_different_key_cannot_read():
    kit.set_key(KEY)
    db = fresh_db()
    ids = kit.seed(db)
    kit.set_key(kit.new_key())
    try:
        raises(PrivateAccessRefused, store.facts, db, ids["principal"])   # tag no longer valid
        p2 = kit.private_principal(db)                                    # grant under new key
        raises(KeyMismatch, store.facts, db, p2)
    finally:
        kit.set_key(KEY)


def test_private_values_never_stringify_serialise_or_pickle():
    v = PrivateValue(kit.SENTINELS[0])
    for rendered in (str(v), repr(v), f"{v}", "%s" % v, "{}".format(v), str([v]),
                     str({"x": v})):
        assert kit.SENTINELS[0] not in rendered, rendered
    raises(TypeError, json.dumps, {"x": v})
    raises(TypeError, pickle.dumps, v)
    raises(AttributeError, setattr, v, "x", 1)
    assert v.reveal() == kit.SENTINELS[0]


def test_tables_are_separate_from_business_memory_and_base():
    kit.set_key(KEY)
    db = fresh_db()
    kit.seed(db)
    assert set(TABLES) == {"laura_private_entries", "laura_private_grants",
                           "laura_private_access"}
    assert not set(TABLES) & set(Base.metadata.tables), "private tables on core Base"
    with db.engine.connect() as c:
        mem = c.exec_driver_sql("select count(*) from company_memory").scalar() \
            if db.engine.dialect.has_table(c, "company_memory") else 0
    assert mem == 0, "the private store wrote business memory"
    from brambleloop.laura import memory as lm
    raises(lm.TierRefused, lm.read, db, "private", None, lm.Principal.laura())


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
