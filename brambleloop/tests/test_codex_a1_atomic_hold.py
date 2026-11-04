"""Child safety audit and owner action share a real database transaction."""
import dataclasses
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from unittest.mock import patch

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

import test_a1r_child_safety_core as harness
from brambleloop.agents.registry import Registry
from brambleloop.core.models import AuditLog, Job, JobStatus, OwnerAction, Phase, utcnow
from brambleloop.core.resilience import TransientError
from brambleloop.products import inventory, launch0
from brambleloop.publish.pdf import ChildrensDecisionRequired
from brambleloop.queue.durable import JobQueue
from brambleloop.queue.effects import LeaseLost
from brambleloop.runtime import release
from brambleloop.runtime.worker import JobContext, Worker


def _claimed(db, key):
    q = JobQueue(db)
    q.enqueue("publishing", "assets.build", {"slug": "fixture", "version": "1.0.0"},
              idempotency_key=key)
    job = q.claim(key, ["assets.build"])
    return JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)


def _exc():
    return ChildrensDecisionRequired("fixture", "safety_refusal", "synthetic safety finding",
                                     version="1.0.0", content_digest="a" * 64)


def test_concurrent_safety_holds_share_one_owner_action():
    db, _ = harness._store()
    contexts = [_claimed(db, "hold-0"), _claimed(db, "hold-1")]
    barrier = Barrier(2)

    def report(ctx):
        barrier.wait(timeout=10)
        for _ in range(50):
            try:
                return release._childrens_hold(ctx, _exc())
            except TransientError:
                sleep(0.02)
        raise AssertionError("owner queue remained contended")

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(result["held"] for result in pool.map(report, contexts))
    with db.session() as session:
        actions = list(session.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("childrens-safety:fixture@1.0.0:%"))))
        audits = list(session.scalars(select(AuditLog).where(
            AuditLog.action == release.CHILDRENS_HOLD, AuditLog.artifact == "fixture@1.0.0")))
    assert len(actions) == 1 and len(audits) == 2


def test_stale_producer_cannot_write_safety_hold():
    db, _ = harness._store()
    ctx = _claimed(db, "stale-hold")
    with db.session() as session:
        session.execute(update(Job).where(Job.id == ctx.job.id).values(lease_token="new-attempt"))
    with pytest.raises(LeaseLost):
        release._childrens_hold(ctx, _exc())
    with db.session() as session:
        assert not list(session.scalars(select(OwnerAction)))
        assert not list(session.scalars(select(AuditLog).where(
            AuditLog.action == release.CHILDRENS_HOLD)))


def test_postgresql_owner_and_job_contention_fails_fast_and_retries():
    from sqlalchemy import text

    db, _ = harness._store()
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL")
    ctx = _claimed(db, "contended-hold")
    with db.session() as locked:
        locked.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": release.OWNER_QUEUE_LOCK})
        with pytest.raises(TransientError, match="contended"):
            release._childrens_hold(ctx, _exc())
    with db.session() as locked:
        locked.scalar(select(Job).where(Job.id == ctx.job.id).with_for_update())
        with pytest.raises(TransientError, match="conflicted"):
            release._childrens_hold(ctx, _exc())
    with db.session() as session:
        assert not list(session.scalars(select(OwnerAction)))
        assert not list(session.scalars(select(AuditLog).where(
            AuditLog.action == release.CHILDRENS_HOLD)))
    assert release._childrens_hold(ctx, _exc())["held"]


def test_real_worker_retries_after_owner_action_write_failure_atomically():
    db, _ = harness._store()
    cir = dataclasses.replace(inventory._engineered("cloudline-baby-blanket"),
                              designer_notes="Use snap-in eyes.")
    from brambleloop.core.models import PatternVersion, Product
    with db.session() as session:
        product = Product(slug=cir.slug, title=cir.title)
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version=cir.version,
                                   cir_json=cir.to_dict(), certified=True))
    queue = JobQueue(db)
    queued = queue.enqueue("publishing", "assets.build", {"slug": cir.slug, "version": cir.version},
                           idempotency_key="hold-failure")

    def fail_owner_action(session, *_):
        if any(isinstance(row, OwnerAction) and
               (row.requirement_key or "").startswith("childrens-safety:") for row in session.new):
            raise RuntimeError("simulated owner-action write failure")

    with patch.dict(launch0._ASSIGNED_DECISION_CIR_SHA256,
                    {cir.slug: launch0._cir_decision_digest(cir)}):
        event.listen(Session, "before_flush", fail_owner_action)
        try:
            assert Worker(db, "hold-fail", job_types=["assets.build"]).run_once()
        finally:
            event.remove(Session, "before_flush", fail_owner_action)
        with db.session() as session:
            assert session.get(Job, queued.id).status == JobStatus.FAILED
            assert not list(session.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key.like("childrens-safety:%"))))
            assert not list(session.scalars(select(AuditLog).where(
                AuditLog.action == release.CHILDRENS_HOLD)))
            session.get(Job, queued.id).run_after = utcnow()
        assert Worker(db, "hold-retry", job_types=["assets.build"]).run_once()
    with db.session() as session:
        assert session.get(Job, queued.id).status == JobStatus.DONE
        assert len(list(session.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("childrens-safety:%"))))) == 1
        assert len(list(session.scalars(select(AuditLog).where(
            AuditLog.action == release.CHILDRENS_HOLD)))) == 1
