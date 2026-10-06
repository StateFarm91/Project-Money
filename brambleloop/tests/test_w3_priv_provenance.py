"""W3-PRIV: only owner-supplied text and genuine interaction records; never generated history.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_priv_provenance.py
"""
from __future__ import annotations

from w3_laura_memory_harness import check, finish, fresh_db, raises

from brambleloop.laura.private import _testkit as kit
from brambleloop.laura.private import store
from brambleloop.laura.private.errors import PrivateProvenanceRefused

kit.set_key(kit.new_key())
S = kit.SENTINELS


def test_generated_or_unknown_provenance_is_refused():
    db = fresh_db()
    p = kit.private_principal(db)
    raises(PrivateProvenanceRefused, store.remember, db, p, "a", S[0], generated=True)
    bad = ["generated", "summary", "inferred", "imported", "model", "model_memory", "", None,
           "OWNER_SUPPLIED", "owner_supplied "]
    for prov in bad:
        raises(PrivateProvenanceRefused, store.remember, db, p, "a", S[0], provenance=prov)
    assert store.facts(db, p) == []


def test_owner_supplied_cites_nothing_and_needs_real_text():
    db = fresh_db()
    p = kit.private_principal(db)
    raises(PrivateProvenanceRefused, store.remember, db, p, "a", S[0], sources=["pt_x"])
    for bad in ("", "   ", 5, b"bytes", None, "x" * (store.MAX_TEXT + 1)):
        raises(PrivateProvenanceRefused, store.remember, db, p, "a", bad)
    for bad in ("", "y" * 121, 3):
        raises(PrivateProvenanceRefused, store.remember, db, p, bad, S[0])
    assert store.remember(db, p, "a", S[0]).startswith("pf_")


def test_interaction_facts_must_quote_existing_turns_verbatim():
    db = fresh_db()
    p = kit.private_principal(db)
    t = store.record_turn(db, p, "owner", f"alpha {S[1]} omega")
    raises(PrivateProvenanceRefused, store.remember, db, p, "q", S[1], provenance="interaction")
    raises(PrivateProvenanceRefused, store.remember, db, p, "q", S[1],
           provenance="interaction", sources=["pt_" + "0" * 32])
    raises(PrivateProvenanceRefused, store.remember, db, p, "q", "a paraphrase of it",
           provenance="interaction", sources=[t])
    raises(PrivateProvenanceRefused, store.remember, db, p, "q", S[1],
           provenance="interaction", sources=[{"id": t}])
    rid = store.remember(db, p, "q", S[1], provenance="interaction", sources=[t])
    f = store.facts(db, p, "q")
    assert f[0].record_id == rid and f[0].provenance == "interaction" and f[0].sources == (t,)


def test_laura_turns_must_answer_a_live_owner_turn_once():
    db = fresh_db()
    p = kit.private_principal(db)
    o = store.record_turn(db, p, "owner", S[2])
    raises(PrivateProvenanceRefused, store.record_turn, db, p, "laura", S[3])        # no reply_to
    raises(PrivateProvenanceRefused, store.record_turn, db, p, "laura", S[3], reply_to=o)  # no model
    raises(PrivateProvenanceRefused, store.record_turn, db, p, "laura", S[3],
           reply_to="pt_" + "0" * 32, model_ref="m")
    r = store.record_turn(db, p, "laura", S[3], reply_to=o, model_ref="provider-a/m1")
    raises(PrivateProvenanceRefused, store.record_turn, db, p, "laura", S[4], reply_to=r,
           model_ref="m")                                                        # reply to a reply
    raises(PrivateProvenanceRefused, store.record_turn, db, p, "laura", S[4], reply_to=o,
           model_ref="m")                                                        # second reply
    raises(PrivateProvenanceRefused, store.record_turn, db, p, "owner", S[4], reply_to=o)
    raises(PrivateProvenanceRefused, store.record_turn, db, p, "owner", S[4], model_ref="m")
    for role in ("system", "assistant", "narrator", "", None):
        raises(PrivateProvenanceRefused, store.record_turn, db, p, role, S[4])
    assert len(store.conversation(db, p)) == 2


def test_history_cannot_be_backfilled_from_another_conversation():
    db = fresh_db()
    old = kit.private_principal(db)
    o = store.record_turn(db, old, "owner", S[5])
    new = kit.private_principal(db)                       # a later, separate private context
    raises(PrivateProvenanceRefused, store.record_turn, db, new, "laura", S[6], reply_to=o,
           model_ref="provider-b/m2")
    assert [t.role for t in store.conversation(db, new)] == ["owner"]


def test_no_parameter_accepts_a_past_date_or_author():
    db = fresh_db()
    p = kit.private_principal(db)
    for kw in ({"created_at": "2001-01-01T00:00:00Z"}, {"occurred_at": "2001"},
               {"author": "owner"}, {"timestamp": 0}):
        raises(TypeError, store.remember, db, p, "a", S[0], **kw)
        raises(TypeError, store.record_turn, db, p, "owner", S[0], **kw)
    assert store.facts(db, p) == [] and store.conversation(db, p) == []


def test_refusal_messages_carry_no_content():
    db = fresh_db()
    p = kit.private_principal(db)
    t = store.record_turn(db, p, "owner", S[7])
    e = raises(PrivateProvenanceRefused, store.remember, db, p, S[0], S[1],
               provenance="interaction", sources=[t])
    assert all(s not in str(e) for s in S), str(e)


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
