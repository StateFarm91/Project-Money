"""Old release audit results cannot hide current unverifiable checks."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Job, JobStatus, Listing, PatternVersion
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import quality_ops
from brambleloop.runtime.worker import Worker


def test_old_release_result_does_not_hide_current_unknown_from_quality_sweep():
    cir = d._cir()
    db = d._db(cir)
    with db.session() as session:
        session.scalar(select(PatternVersion)).release_hash = "n" * 64
    def run(agent, job_type, inputs):
        job = JobQueue(db).enqueue(agent, job_type, inputs)
        worker = Worker(db, "quality-release-status", job_types=[job_type])
        for _ in range(4):
            assert worker.run_once()
            with db.session() as session:
                row = session.get(Job, job.id)
                if row.status == JobStatus.DONE:
                    return dict(row.outputs)
        raise AssertionError("queued check did not complete")
    current = {"slug": cir.slug, "version": cir.version, "release_hash": "n" * 64}
    assert run("policy", "gate.policy", current)["ok"] is None
    with db.session() as session:
        session.add(Listing(product_slug=cir.slug, version=cir.version,
                            title="Crochet pattern", description="Crochet pattern.",
                            tags=["crochet"], price_cad=6.5, state="draft"))
    assert run("policy", "gate.policy", {**current, "release_hash": "o" * 64})["ok"] is True
    report = run("quality_director", "gate.quality", {})
    assert any(row["check"] == "gate.policy" for row in report["unverifiable"]), report
    assert run("policy", "gate.policy", current)["ok"] is True
    assert not any(row["check"] == "gate.policy" for row in quality_ops.unverifiable(db))
    from brambleloop.core.models import AuditLog
    with db.session() as session:
        session.add(AuditLog(actor="fixture", action=quality_ops.READING,
                             artifact=f"{cir.slug}@{cir.version}",
                             detail={"check": "gate.policy", "release_hash": "n" * 64,
                                     "ok": "pass"}))
    assert any(row["check"] == "gate.policy" for row in quality_ops.unverifiable(db))
