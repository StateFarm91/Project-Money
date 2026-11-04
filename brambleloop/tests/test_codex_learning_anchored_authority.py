"""Fixture-only signed grant; no production trust anchor exists."""
import base64
import json
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog
from brambleloop.core.sealed_chain import GrantLedger
from brambleloop.improve import learning_authority as a


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class FixtureFence:
    """No concurrency guarantee; not a production fence."""
    def assert_held(self, session, expected):
        assert session.in_transaction()


class FixtureAnchor:
    def __init__(self, tail):
        self.tail = tail
    def current_tail(self, session):
        return self.tail


@pytest.fixture
def context(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'learning.db'}", scratch=True)
    db.create_all()
    key = Ed25519PrivateKey.generate()
    def sign(body):
        return base64.b64encode(key.sign(raw(body))).decode()
    def verify(body, seal):
        try:
            key.public_key().verify(base64.b64decode(seal, validate=True), raw(body))
            return True
        except (ValueError, InvalidSignature):
            return False
    expected = {"domain": a.DOMAIN, "principal": a.PRINCIPAL, "producer": "producer",
                "reviewer": "reviewer", "rule_id": 1, "rule_version": 2,
                "rule_digest": "a" * 64, "evaluation_id": 3, "evaluation_digest": "b" * 64}
    ledger = GrantLedger(approved=a.APPROVED, revoked=a.REVOKED, rebased=a.REBASED,
                         principal=a.PRINCIPAL, seal=sign, verify=verify,
                         signature="fixture", label="fixture")
    ident = ledger.append(db, action=a.APPROVED, artifact="fixture", detail=expected)
    with db.session() as session:
        row = session.get(AuditLog, ident)
        anchor = FixtureAnchor((row.id, row.detail["seal"]))
    return db, ledger, ident, expected, verify, anchor


def test_signed_grant_allows_transaction_and_rollback(context):
    db, _, ident, expected, verify, anchor = context
    with db._sessions() as session, session.begin():
        def action(s):
            s.add(AuditLog(actor="fixture", action="fixture.action", detail={}))
            s.flush()
        a.guarded_database_action(session, ident, expected, verify=verify,
                                  anchor=anchor, fence=FixtureFence(), action=action)
        session.rollback()
    with db.session() as session:
        assert session.scalar(select(AuditLog).where(AuditLog.action == "fixture.action")) is None


def test_unconfigured_anchor_or_fence_never_runs_action(context):
    db, _, ident, expected, verify, anchor = context
    with db._sessions() as session, session.begin():
        for bad_anchor, fence in ((None, FixtureFence()), (anchor, None)):
            with pytest.raises(a.AuthorityRefused):
                a.guarded_database_action(session, ident, expected, verify=verify, anchor=bad_anchor,
                                          fence=fence, action=lambda _: pytest.fail("must not act"))


def test_wrong_binding_revocation_and_tail_truncation_refuse(context):
    db, ledger, ident, expected, verify, anchor = context
    with db._sessions() as session, session.begin():
        for altered in ({**expected, "rule_digest": "c" * 64},
                        {**expected, "reviewer": expected["producer"]}):
            with pytest.raises(a.AuthorityRefused):
                a.authorize_in_session(session, ident, altered, verify=verify, anchor=anchor,
                                       fence=FixtureFence())
    revoked = ledger.revoke(db, ident)
    with db.session() as session:
        row = session.get(AuditLog, revoked)
        anchor.tail = (row.id, row.detail["seal"])
    with db._sessions() as session, session.begin():
        with pytest.raises(a.AuthorityRefused):
            a.authorize_in_session(session, ident, expected, verify=verify, anchor=anchor,
                                   fence=FixtureFence())
    with db.session() as session:
        session.delete(session.get(AuditLog, revoked))
    with db._sessions() as session, session.begin():
        with pytest.raises(a.AuthorityRefused, match="tail"):
            a.authorize_in_session(session, ident, expected, verify=verify, anchor=anchor,
                                   fence=FixtureFence())


def test_invalid_signature_cannot_authorize_even_with_matching_tail(context):
    db, _, ident, expected, verify, anchor = context
    with db.session() as session:
        row = session.get(AuditLog, ident)
        row.detail = {**row.detail, "seal": base64.b64encode(b"x" * 64).decode()}
        anchor.tail = (ident, row.detail["seal"])
    with db._sessions() as session, session.begin():
        with pytest.raises(a.AuthorityRefused):
            a.authorize_in_session(session, ident, expected, verify=verify, anchor=anchor,
                                   fence=FixtureFence())


def test_pending_changes_are_not_silently_flushed(context):
    db, _, ident, expected, verify, anchor = context
    with db._sessions() as session, session.begin():
        session.add(AuditLog(actor="fixture", action="pending", detail={}))
        with pytest.raises(a.AuthorityRefused, match="clean"):
            a.authorize_in_session(session, ident, expected, verify=verify, anchor=anchor,
                                   fence=FixtureFence())
