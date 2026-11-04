"""A new certified release must not inherit the old release's quality cadence."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Job, JobStatus, PatternVersion
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import quality_ops
from brambleloop.runtime.worker import Worker


def test_reverification_readings_follow_exact_release_hash():
    cir = d._cir()
    db = d._db(cir)
    old_hash = "r" * 64
    for job_type, agent in quality_ops.CHECKS.items():
        job = JobQueue(db).enqueue(agent, job_type, {"slug": cir.slug, "version": cir.version,
                                                      "release_hash": old_hash})
        assert Worker(db, "quality-freshness", job_types=[job_type]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
    assert quality_ops.next_work(db) == []
    # Synthetic re-certification to another release identity, no physical proof.
    with db.session() as session:
        session.scalar(select(PatternVersion)).release_hash = "s" * 64
    todo = quality_ops.next_work(db)
    assert todo and todo[0]["job_type"] == "gate.quality", todo
    for job_type, agent in quality_ops.CHECKS.items():
        job = JobQueue(db).enqueue(agent, job_type, {"slug": cir.slug, "version": cir.version,
                                                      "release_hash": "s" * 64})
        assert Worker(db, "quality-freshness-new", job_types=[job_type]).run_once()
        with db.session() as session:
            assert session.get(Job, job.id).status == JobStatus.DONE
    assert quality_ops.next_work(db) == []


def test_malformed_or_unbound_readings_do_not_satisfy_freshness():
    from brambleloop.core.models import AuditLog
    cir = d._cir()
    db = d._db(cir)
    with db.session() as session:
        session.add(AuditLog(actor="fixture", action=quality_ops.READING,
                             artifact=f"{cir.slug}@{cir.version}", detail=["bad"]))
        session.add(AuditLog(actor="fixture", action=quality_ops.READING,
                             artifact=f"{cir.slug}@{cir.version}",
                             detail={"check": [], "release_hash": "r" * 64}))
        for check in quality_ops.CHECKS:
            session.add(AuditLog(actor="fixture", action=quality_ops.READING,
                                 artifact=f"{cir.slug}@{cir.version}", detail={"check": check}))
    assert quality_ops.next_work(db), "malformed or hashless audits are not current readings"
    job = JobQueue(db).enqueue("quality_director", "gate.quality", {})
    assert Worker(db, "quality-sweep", job_types=["gate.quality"]).run_once()
    with db.session() as session:
        row = session.get(Job, job.id)
        assert row.status == JobStatus.DONE and row.outputs["queued"] == 4
