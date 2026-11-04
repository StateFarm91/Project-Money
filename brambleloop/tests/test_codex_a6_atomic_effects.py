"""Release persistence, its recertification audit and follow-on share a transaction."""
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from brambleloop.agents.registry import Registry
from brambleloop.core.models import ArtefactProvenance, AuditLog, Job, PatternVersion, Phase, utcnow
from brambleloop.products import launch0
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline
from brambleloop.runtime.lineage import JobLink
from brambleloop.runtime.worker import JobContext
from test_w5_a6_frozen_knowledge import _store


def _bound_certificate(cir):
    from brambleloop.runtime.release import _content_hash_of
    release_hash = _content_hash_of(cir)
    return release_hash, {"granted": True, "slug": cir.slug, "version": cir.version,
                          "content_hash": release_hash, "release_hash": release_hash}


def test_actual_job_context_release_audit_and_followon_commit_or_rollback_together():
    db, _ = _store()
    cir = launch0.cir_for("basket_small")
    queue = JobQueue(db)
    queue.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()}, priority=0)
    parent = queue.claim("atomic-test", job_types=["gate.certify"])
    assert parent is not None and parent.lease_token
    ctx = JobContext(job=parent, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    target, certificate = _bound_certificate(cir)
    pipeline._persist_release(ctx, cir, {"granted": True}, "a" * 64)
    withholding.record_reverification(db, cir.slug, cir.version,
                                      check="pdf", problem="pdf hash drift")

    def assert_state(session, expected_hash, count):
        version = session.scalar(select(PatternVersion))
        certificate = session.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "certificate"))
        assert version.release_hash == expected_hash and certificate.sha256 == expected_hash
        audits = list(session.scalars(select(AuditLog).where(AuditLog.action == "gate.recertified")))
        jobs = list(session.scalars(select(Job).where(Job.job_type == "gate.quality")))
        links = list(session.scalars(select(JobLink).where(JobLink.parent_id == parent.id)))
        assert len(audits) == len(jobs) == len(links) == count
        if count:
            assert audits[0].job_id == parent.id and audits[0].actor == parent.agent
            assert jobs[0].idempotency_key.startswith(f"reverify-after-recert:{cir.slug}@")
            assert links[0].child_id == jobs[0].id

    with db._sessions() as session:
        session.begin()
        assert pipeline._persist_release(ctx, cir, certificate, target,
                                         session=session, atomic_effects=True) == []
        assert_state(session, target, 1)
        with db.session() as observer:
            assert_state(observer, "a" * 64, 0)
        session.rollback()
    with db.session() as observer:
        assert_state(observer, "a" * 64, 0)

    with db._sessions() as session:
        with session.begin():
            pipeline._persist_release(ctx, cir, certificate, target,
                                      session=session, atomic_effects=True)
    with db.session() as observer:
        assert_state(observer, target, 1)


def test_existing_followon_is_not_treated_as_fresh_reverification():
    db, _ = _store()
    cir = launch0.cir_for("basket_small")
    queue = JobQueue(db)
    queue.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()}, priority=0)
    parent = queue.claim("atomic-test", job_types=["gate.certify"])
    assert parent is not None and parent.lease_token
    ctx = JobContext(job=parent, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    target, certificate = _bound_certificate(cir)
    pipeline._persist_release(ctx, cir, {"granted": True}, "a" * 64)
    withholding.record_reverification(db, cir.slug, cir.version, check="pdf", problem="drift")
    key = f"reverify-after-recert:{cir.slug}@{cir.version}:{target[:16]}"
    queue.enqueue("quality_director", "gate.quality", {}, priority=0, idempotency_key=key)
    with db._sessions() as session:
        with session.begin():
            with pytest.raises(ValueError, match="fresh recertification"):
                pipeline._persist_release(ctx, cir, certificate, target,
                                          session=session, atomic_effects=True)
            # A caller catching the refusal must not be able to accidentally
            # commit a partially updated release with unrelated work.
            session.add(AuditLog(actor="test", action="unrelated-after-hold"))
    with db.session() as observer:
        assert observer.scalar(select(PatternVersion)).release_hash == "a" * 64
        assert len(list(observer.scalars(select(Job).where(Job.idempotency_key == key)))) == 1
        assert not list(observer.scalars(select(AuditLog).where(AuditLog.action == "gate.recertified")))
        assert observer.scalar(select(AuditLog).where(AuditLog.action == "unrelated-after-hold"))


def test_followon_failure_rolls_back_release_and_audit():
    db, _ = _store()
    cir = launch0.cir_for("basket_small")
    queue = JobQueue(db)
    queue.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()}, priority=0)
    parent = queue.claim("atomic-test", job_types=["gate.certify"])
    assert parent is not None and parent.lease_token
    ctx = JobContext(job=parent, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    target, certificate = _bound_certificate(cir)
    pipeline._persist_release(ctx, cir, {"granted": True}, "a" * 64)
    withholding.record_reverification(db, cir.slug, cir.version, check="pdf", problem="drift")
    with patch.object(queue, "enqueue", side_effect=RuntimeError("unavailable")):
        with pytest.raises(RuntimeError, match="unavailable"):
            with db._sessions() as session:
                with session.begin():
                    pipeline._persist_release(ctx, cir, certificate, target,
                                              session=session, atomic_effects=True)
    with db.session() as observer:
        assert observer.scalar(select(PatternVersion)).release_hash == "a" * 64
        assert not list(observer.scalars(select(AuditLog).where(AuditLog.action == "gate.recertified")))


def test_missing_lineage_schema_refuses_without_partial_release():
    db, _ = _store()
    cir = launch0.cir_for("basket_small")
    queue = JobQueue(db)
    queue.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()}, priority=0)
    parent = queue.claim("atomic-test", job_types=["gate.certify"])
    assert parent is not None and parent.lease_token
    ctx = JobContext(job=parent, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    target, certificate = _bound_certificate(cir)
    pipeline._persist_release(ctx, cir, {"granted": True}, "a" * 64)
    withholding.record_reverification(db, cir.slug, cir.version, check="pdf", problem="drift")
    JobLink.__table__.drop(db.engine)
    with pytest.raises(DBAPIError) as failure:
        with db._sessions() as session:
            with session.begin():
                pipeline._persist_release(ctx, cir, certificate, target,
                                          session=session, atomic_effects=True)
    assert "job_links" in str(failure.value).lower()
    with db.session() as observer:
        assert observer.scalar(select(PatternVersion)).release_hash == "a" * 64
        assert not list(observer.scalars(select(Job).where(Job.job_type == "gate.quality")))
        assert not list(observer.scalars(select(AuditLog).where(AuditLog.action == "gate.recertified")))


@pytest.mark.parametrize("mismatch", ["token", "actor", "content", "expired", "same-hash",
                                      "not-granted", "certificate-slug", "certificate-hash"])
def test_atomic_release_rejects_untrusted_job_or_ambiguous_duplicate(mismatch):
    db, _ = _store()
    cir = launch0.cir_for("basket_small")
    queue = JobQueue(db)
    queue.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()}, priority=0)
    parent = queue.claim("atomic-test", job_types=["gate.certify"])
    assert parent is not None and parent.lease_token
    job_view = SimpleNamespace(id=parent.id, agent=parent.agent, job_type=parent.job_type,
                               leased_by=parent.leased_by, lease_token=parent.lease_token)
    ctx = JobContext(job=job_view, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    if mismatch == "token":
        job_view.lease_token = "stale-token"
    elif mismatch == "actor":
        job_view.agent = "different-agent"
    elif mismatch == "content":
        import dataclasses
        cir = dataclasses.replace(cir, title="A different title")
    elif mismatch == "expired":
        with db.session() as session:
            session.get(Job, parent.id).lease_expires_at = utcnow() - timedelta(seconds=1)
    elif mismatch == "same-hash":
        target, certificate = _bound_certificate(cir)
        pipeline._persist_release(ctx, cir, certificate, target)
        with db.session() as session:
            session.scalar(select(PatternVersion)).certified = False
    target, certificate = _bound_certificate(cir)
    if mismatch == "not-granted":
        certificate["granted"] = False
    elif mismatch == "certificate-slug":
        certificate["slug"] = "different-slug"
    elif mismatch == "certificate-hash":
        certificate["content_hash"] = "0" * 64
    with pytest.raises(ValueError):
        with db._sessions() as session:
            with session.begin():
                pipeline._persist_release(ctx, cir, certificate, target,
                                          session=session, atomic_effects=True)
    with db.session() as observer:
        version = observer.scalar(select(PatternVersion))
        if mismatch == "same-hash":
            assert version is not None and version.certified is False
        else:
            assert version is None
        assert not list(observer.scalars(select(Job).where(Job.job_type == "gate.quality")))
        assert not list(observer.scalars(select(AuditLog).where(AuditLog.action == "gate.recertified")))
