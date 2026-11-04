"""Nonproduction transaction-composition experiment; fixture fence is not a lock."""
import pytest
from sqlalchemy import select
from brambleloop.agents.registry import Registry
from brambleloop.cir import knowledge as markers
from brambleloop.core.models import AuditLog, DesignRule, Job, PatternVersion, Phase
from brambleloop.improve import design_knowledge as dk, knowledge_gate as kg, learning_authority as auth
from brambleloop.improve.owner_grant_append import append_owner_grant_in_session
from brambleloop.products import launch0
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline
from brambleloop.runtime.worker import JobContext
from test_codex_a6_atomic_effects import _bound_certificate
from test_codex_learning_owner_grant_append import setup, FixtureAnchor, FixtureFence, FixtureStepUp


def test_fixture_signed_rule_and_release_effects_share_caller_rollback(setup):
    db, rule_id, sign, verify = setup
    anchor, fence = FixtureAnchor(), FixtureFence()
    with db._sessions() as session, session.begin():
        grant_id = append_owner_grant_in_session(db, session, rule_id, sign=sign, verify=verify,
                         anchor=anchor, fence=fence, owner_decision=FixtureStepUp())
    cir = launch0.cir_for("basket_small")
    records = dk.applicable_to_cir(db, cir)
    pin = next(r["pin"] for r in records if r["pin"]["rule_id"] == rule_id)
    cir = dk.freeze_pins(db, cir, [pin])
    assert [m["pin"] for m in markers.markers(cir)] == [pin]
    queue = JobQueue(db)
    queue.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()}, priority=0)
    parent = queue.claim("fixture-authority", job_types=["gate.certify"])
    ctx = JobContext(job=parent, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    target, certificate = _bound_certificate(cir)  # synthetic; NOT gate-issued authority
    with db._sessions() as session, session.begin():
        rule = session.get(DesignRule, rule_id)
        approval = session.scalar(select(AuditLog).where(
            AuditLog.action == "design_knowledge.rule_approved",
            AuditLog.artifact == f"design-rule:{rule_id}").order_by(AuditLog.id.desc()))
        expected = {"domain": auth.DOMAIN, "principal": auth.PRINCIPAL,
                    "producer": rule.producer, "reviewer": rule.approved_by,
                    "rule_id": rule.id, "rule_version": rule.version,
                    "rule_digest": dk.rule_digest(rule), "evaluation_id": approval.detail["evaluation_id"],
                    "evaluation_digest": approval.detail["evaluation_digest"]}
        session.expire_all()
        assert kg.refusal(db, cir, session=session) is None
        class StaleAnchor(FixtureAnchor):
            def current_tail(self, session):
                return (0, "")
        with pytest.raises(auth.AuthorityRefused):
            auth.authorize_in_session(session, grant_id, expected, verify=verify,
                                      anchor=StaleAnchor(), fence=fence)
        assert session.scalar(select(PatternVersion).where(PatternVersion.release_hash == target)) is None
        auth.authorize_in_session(session, grant_id, expected, verify=verify, anchor=anchor, fence=fence)
        pipeline._persist_release(ctx, cir, certificate, target, session=session, atomic_effects=True)
        session.rollback()
    with db.session() as session:
        assert session.scalar(select(PatternVersion).where(PatternVersion.release_hash == target)) is None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "gate.recertified")) is None
        assert session.scalar(select(Job).where(Job.job_type == "gate.quality")) is None
    with db._sessions() as session, session.begin():
        assert kg.refusal(db, cir, session=session) is None
        auth.authorize_in_session(session, grant_id, expected, verify=verify, anchor=anchor, fence=fence)
        pipeline._persist_release(ctx, cir, certificate, target, session=session, atomic_effects=True)
    with db.session() as session:
        assert session.scalar(select(PatternVersion).where(PatternVersion.release_hash == target)) is not None
