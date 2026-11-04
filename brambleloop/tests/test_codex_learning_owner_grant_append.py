"""Composition fixtures only: no production keys, anchor, fence or step-up."""
import base64
import json
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from brambleloop.core.models import AuditLog, DesignRule, OperatingReading
from brambleloop.improve import design_knowledge as knowledge
from brambleloop.improve import learning_authority as authority
from brambleloop.improve.owner_grant_append import append_owner_grant_in_session
from test_w5_a6_frozen_knowledge import _approved_rule, _store


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class FixtureAnchor:
    """Transactional fixture only; NOT independently protected."""
    def current_tail(self, session):
        row = session.scalar(select(OperatingReading).where(OperatingReading.kind == "fixture.anchor"))
        return tuple(row.payload["tail"])
    def advance_tail(self, session, old, new):
        row = session.scalar(select(OperatingReading).where(OperatingReading.kind == "fixture.anchor"))
        if tuple(row.payload["tail"]) != old:
            raise ValueError("tail changed")
        row.payload = {"tail": list(new)}
        session.flush()


class FixtureFence:
    """No cross-writer exclusion; NOT a production fence."""
    def assert_held(self, session, expected):
        assert session.in_transaction() and expected["rule_id"] > 0


class FixtureStepUp:
    """No user authentication; NOT an owner step-up."""
    def assert_exact_decision(self, session, binding):
        assert session.in_transaction() and binding["domain"] == authority.DOMAIN
        assert binding["reviewer"] == "owner" and binding["rule_digest"]


@pytest.fixture
def setup():
    db, _ = _store()
    approved = _approved_rule(db)
    with db.session() as s:
        s.add(OperatingReading(kind="fixture.anchor", period_key="tail", payload={"tail": [0, ""]}))
    key = Ed25519PrivateKey.generate()
    def sign(body):
        return base64.b64encode(key.sign(_canonical(body))).decode()
    def verify(body, seal):
        try:
            key.public_key().verify(base64.b64decode(seal, validate=True), _canonical(body))
            return True
        except (ValueError, InvalidSignature):
            return False
    return db, approved["rule_id"], sign, verify


def test_stepup_grant_append_verifies_in_callers_transaction(setup):
    db, rule_id, sign, verify = setup
    anchor, fence = FixtureAnchor(), FixtureFence()
    with db._sessions() as session, session.begin():
        grant_id = append_owner_grant_in_session(db, session, rule_id, sign=sign, verify=verify,
                         anchor=anchor, fence=fence, owner_decision=FixtureStepUp())
    with db._sessions() as session, session.begin():
        rule = session.get(DesignRule, rule_id)
        approval = session.scalar(select(AuditLog).where(
            AuditLog.action == "design_knowledge.rule_approved",
            AuditLog.artifact == f"design-rule:{rule_id}").order_by(AuditLog.id.desc()))
        expected = {"domain": authority.DOMAIN, "principal": authority.PRINCIPAL,
                    "producer": rule.producer, "reviewer": rule.approved_by,
                    "rule_id": rule.id, "rule_version": rule.version,
                    "rule_digest": knowledge.rule_digest(rule),
                    "evaluation_id": approval.detail["evaluation_id"],
                    "evaluation_digest": approval.detail["evaluation_digest"]}
        session.expire_all()
        authority.authorize_in_session(session, grant_id, expected, verify=verify,
                                       anchor=anchor, fence=fence)
        assert expected["reviewer"] == "owner" and expected["producer"] != "owner"


def test_missing_stepup_anchor_or_fence_and_rollback_fail_closed(setup):
    db, rule_id, sign, verify = setup
    anchor, fence = FixtureAnchor(), FixtureFence()
    for missing in ("anchor", "fence", "owner_decision"):
        kwargs = {"anchor": anchor, "fence": fence, "owner_decision": FixtureStepUp()}
        kwargs[missing] = None
        with db._sessions() as session, session.begin():
            with pytest.raises(authority.AuthorityRefused):
                append_owner_grant_in_session(db, session, rule_id, sign=sign, verify=verify, **kwargs)
    with pytest.raises(RuntimeError):
        with db.session() as session:
            append_owner_grant_in_session(db, session, rule_id, sign=sign, verify=verify,
                anchor=anchor, fence=fence, owner_decision=FixtureStepUp())
            raise RuntimeError("fixture interruption")
    with db.session() as session:
        assert session.scalar(select(AuditLog).where(AuditLog.action == authority.APPROVED)) is None
        assert anchor.current_tail(session) == (0, "")


def test_anchor_failure_cannot_leave_grant_when_refusal_is_caught(setup):
    db, rule_id, sign, verify = setup
    class FailedAnchor(FixtureAnchor):
        def advance_tail(self, session, old, new):
            super().advance_tail(session, old, new)
            raise ValueError("fixture compare-and-swap failure")
    with db._sessions() as session, session.begin():
        with pytest.raises(authority.AuthorityRefused):
            append_owner_grant_in_session(db, session, rule_id, sign=sign, verify=verify,
                anchor=FailedAnchor(), fence=FixtureFence(), owner_decision=FixtureStepUp())
    with db.session() as session:
        assert session.scalar(select(AuditLog).where(AuditLog.action == authority.APPROVED)) is None
        assert FixtureAnchor().current_tail(session) == (0, "")


def test_owner_decision_must_accept_the_exact_current_binding(setup):
    db, rule_id, sign, verify = setup
    class RefusedDecision:
        def assert_exact_decision(self, session, binding):
            # Simulate a challenge previously accepted for another rule digest.
            if binding["rule_digest"] != "0" * 64:
                raise ValueError("owner did not accept this evidence")
    with db._sessions() as session, session.begin():
        with pytest.raises(authority.AuthorityRefused):
            append_owner_grant_in_session(db, session, rule_id, sign=sign, verify=verify,
                anchor=FixtureAnchor(), fence=FixtureFence(), owner_decision=RefusedDecision())
    with db.session() as session:
        assert session.scalar(select(AuditLog).where(AuditLog.action == authority.APPROVED)) is None


def test_successful_append_is_undone_by_outer_transaction_rollback(setup):
    db, rule_id, sign, verify = setup
    session = db._sessions()
    try:
        with session.begin():
            append_owner_grant_in_session(db, session, rule_id, sign=sign, verify=verify,
                anchor=FixtureAnchor(), fence=FixtureFence(), owner_decision=FixtureStepUp())
            session.rollback()
    finally:
        session.close()
    with db.session() as session:
        assert session.scalar(select(AuditLog).where(AuditLog.action == authority.APPROVED)) is None
        assert FixtureAnchor().current_tail(session) == (0, "")
