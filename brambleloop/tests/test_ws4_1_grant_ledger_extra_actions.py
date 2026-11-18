"""WS4-1: `GrantLedger(extra_actions=...)` keeps a family's other events on its one chain.

The standing policy (WS4 design §1.1) has events beyond approve / revoke / rebase:
activated, suspended and resumed. Every one must be a link of the family chain, because
otherwise deleting a suspension row would go undetected (design test T-CH-4). These tests use
a fixture family with a fixture HMAC key and an Ed25519 family with a throwaway key, so
nothing here depends on a deployment secret.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import hmac
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.core.sealed_chain import GrantLedger  # noqa: E402

APPROVED, REVOKED, REBASED = "t.policy.approved", "t.policy.revoked", "t.policy.rebased"
ACTIVATED, SUSPENDED, RESUMED = "t.policy.activated", "t.policy.suspended", "t.policy.resumed"
_FIXTURE_KEY = b"ws4-1 fixture key, not a credential"


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/l.sqlite", scratch=True)
    db.create_all()
    return db


def _hmac_seal(body: dict) -> str:
    return hmac.new(_FIXTURE_KEY, json.dumps(body, sort_keys=True, default=str).encode(),
                    hashlib.sha256).hexdigest()


def _ledger(extra=(ACTIVATED, SUSPENDED, RESUMED), **kw) -> GrantLedger:
    return GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED,
                       principal="owner:command-center", seal=_hmac_seal,
                       signature="t-policy-chain", label="test policy", extra_actions=extra,
                       **kw)


def _life(db, ledger):
    """approve -> activate -> suspend -> resume -> approve (a second version)."""
    a1 = ledger.append(db, action=APPROVED, artifact="sp-1", detail={"v": 1})
    ledger.append(db, action=ACTIVATED, artifact="sp-1", detail={"approval_id": a1})
    s = ledger.append(db, action=SUSPENDED, artifact="sp-1", detail={"why": "stop condition"})
    r = ledger.append(db, action=RESUMED, artifact="sp-1", detail={"approval_id": a1})
    a2 = ledger.append(db, action=APPROVED, artifact="sp-1", detail={"v": 2})
    return a1, s, r, a2


def _delete(db, ident):
    with db.session() as s:
        s.delete(s.get(AuditLog, ident))


def test_extra_events_are_links_of_the_one_chain():
    db, ledger = _db(), _ledger()
    a1, s, r, a2 = _life(db, ledger)
    c = ledger.chain(db, record_incident=False)
    assert c["valid"], c
    rows = [rid for rid, ok, _ in c["rows"]]
    assert len(rows) == 5 and s in rows and r in rows, c["rows"]
    with db.session() as sess:
        details = [sess.get(AuditLog, i).detail for i in rows]
    assert [d["seq"] for d in details] == [1, 2, 3, 4, 5]
    assert [d["event"] for d in details] == [APPROVED, ACTIVATED, SUSPENDED, RESUMED, APPROVED]
    assert ledger.refusal(db, a2) is None and ledger.refusal(db, a1) is None


def test_t_ch_4_deleting_a_suspension_row_breaks_the_chain_and_refuses_every_grant():
    db, ledger = _db(), _ledger()
    a1, s, _r, a2 = _life(db, ledger)
    _delete(db, s)
    c = ledger.chain(db, record_incident=False)
    assert not c["valid"], c
    for ident in (a1, a2):
        why = ledger.refusal(db, ident)
        assert why and "does not verify" in why, why


def test_without_extra_actions_the_same_deletion_goes_unnoticed():
    """The defect WS4-1 closes, shown on a family that does not declare its extra events:
    rows written outside the chain do not count, so removing one changes nothing."""
    db, ledger = _db(), _ledger(extra=())
    a1 = ledger.append(db, action=APPROVED, artifact="sp-1", detail={"v": 1})
    with db.session() as sess:   # a row under an undeclared action is never on the chain
        sess.add(AuditLog(actor="x", action=SUSPENDED, artifact="sp-1", detail={}))
        sess.flush()
        stray = sess.query(AuditLog).filter(AuditLog.action == SUSPENDED).one().id
    _delete(db, stray)
    assert ledger.chain(db, record_incident=False)["valid"]
    assert ledger.refusal(db, a1) is None


def test_append_refuses_an_action_outside_the_chain():
    db = _db()
    for ledger, bad in ((_ledger(), "t.policy.other"), (_ledger(extra=()), SUSPENDED)):
        try:
            ledger.append(db, action=bad, artifact="sp-1", detail={})
        except ValueError as exc:
            assert "is not an action of" in str(exc)
        else:
            raise AssertionError(f"{bad} was appended off the chain")
    with db.session() as sess:
        assert sess.query(AuditLog).count() == 0


def test_a_hand_inserted_suspension_or_resume_row_breaks_the_chain():
    for action in (SUSPENDED, RESUMED, ACTIVATED):
        db, ledger = _db(), _ledger()
        a1 = ledger.append(db, action=APPROVED, artifact="sp-1", detail={"v": 1})
        with db.session() as sess:
            sess.add(AuditLog(actor="owner:command-center", action=action, artifact="sp-1",
                              detail={"event": action, "seq": 2, "prev_id": a1,
                                      "prev_seal": "0" * 64, "seal": "0" * 64}))
        assert not ledger.chain(db, record_incident=False)["valid"], action
        assert ledger.refusal(db, a1), action


def test_a_replayed_extra_event_breaks_the_chain():
    db, ledger = _db(), _ledger()
    a1, s, _r, _a2 = _life(db, ledger)
    with db.session() as sess:
        orig = sess.get(AuditLog, s)
        sess.add(AuditLog(actor=orig.actor, action=orig.action, artifact=orig.artifact,
                          detail=dict(orig.detail)))
    assert not ledger.chain(db, record_incident=False)["valid"]
    assert ledger.refusal(db, a1)


def test_an_extra_event_cannot_re_anchor_a_broken_chain():
    db, ledger = _db(), _ledger()
    a1, s, _r, _a2 = _life(db, ledger)
    _delete(db, s)
    # A sealed resume written after the break does not restore any grant: only a revocation
    # or an owner rebase may re-anchor (and a rebase voids the grants before it).
    try:
        ledger.append(db, action=RESUMED, artifact="sp-1", detail={"approval_id": a1})
    except ValueError:
        pass
    assert not ledger.chain(db, record_incident=False)["valid"]
    assert ledger.refusal(db, a1)
    ledger.rebase(db, "test: re-anchor after a deleted suspension")
    c = ledger.chain(db, record_incident=False)
    assert c["valid"] and ledger.refusal(db, a1) and "predates" in ledger.refusal(db, a1)
    a3 = ledger.append(db, action=APPROVED, artifact="sp-1", detail={"v": 3})
    ledger.append(db, action=SUSPENDED, artifact="sp-1", detail={"why": "after rebase"})
    assert ledger.refusal(db, a3) is None


def test_action_names_must_be_distinct():
    for extra in ((APPROVED,), (REVOKED,), (ACTIVATED, ACTIVATED), ("",), (None,)):
        try:
            _ledger(extra=extra)
        except ValueError:
            continue
        raise AssertionError(f"extra_actions={extra!r} accepted")


def test_existing_families_are_unchanged():
    """Families that declare no extra events load exactly their three actions, as before."""
    from brambleloop.ops import activation_authority, publication_authority

    for mod in (publication_authority, activation_authority):
        led = mod._ledger() if hasattr(mod, "_ledger") else mod.LEDGER
        assert led.extra_actions == () and led.actions == (led.approved, led.revoked,
                                                           led.rebased), mod.__name__


def test_asymmetric_family_seals_extra_events_with_its_signing_key():
    """An Ed25519 family (verify-only on the worker) verifies its extra events the same way:
    a suspension sealed under a different key breaks the chain."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()

    def body_bytes(body):
        return json.dumps(body, sort_keys=True, default=str).encode()

    def seal_with(k):
        return lambda body: k.sign(body_bytes(body)).hex()

    def verify(body, sig):
        try:
            key.public_key().verify(bytes.fromhex(sig), body_bytes(body))
            return True
        except Exception:  # noqa: BLE001
            return False

    db = _db()
    good = GrantLedger(
        approved=APPROVED, revoked=REVOKED, rebased=REBASED, principal="owner:command-center",
        seal=seal_with(key), verify=verify, signature="t-ed", label="test ed policy",
        extra_actions=(ACTIVATED, SUSPENDED, RESUMED))
    forger = GrantLedger(
        approved=APPROVED, revoked=REVOKED, rebased=REBASED, principal="owner:command-center",
        seal=seal_with(other), verify=verify, signature="t-ed", label="test ed policy",
        extra_actions=(ACTIVATED, SUSPENDED, RESUMED))
    a1 = good.append(db, action=APPROVED, artifact="sp-1", detail={"v": 1})
    good.append(db, action=ACTIVATED, artifact="sp-1", detail={"approval_id": a1})
    assert good.chain(db, record_incident=False)["valid"] and good.refusal(db, a1) is None
    forger.append(db, action=RESUMED, artifact="sp-1", detail={"approval_id": a1})
    assert not good.chain(db, record_incident=False)["valid"]
    assert good.refusal(db, a1)


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
