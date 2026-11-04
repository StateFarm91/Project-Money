"""Late or unscoped quality jobs must not clear current-release holds."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Job, JobStatus, Listing, PatternVersion
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker


def test_stale_or_missing_release_hash_cannot_clear_quality_hold():
    cir = d._cir()
    db = d._db(cir, {"title": "Crochet pattern PDF", "description": "Guaranteed to fit.",
                     "tags": ["crochet"], "price_cad": 6.5, "state": "draft"})
    def run(inputs):
        job = JobQueue(db).enqueue("policy", "gate.policy", inputs)
        assert Worker(db, "quality-stale-job", job_types=["gate.policy"]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)
    ref = {"slug": cir.slug, "version": cir.version}
    old = {**ref, "release_hash": "r" * 64}
    assert run(old)["ok"] is False
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    with db.session() as session:
        session.scalar(select(PatternVersion)).release_hash = "s" * 64
        session.scalar(select(Listing)).description = "Crochet pattern."
    for stale in (old, ref):
        result = run(stale)
        assert result.get("ok") is None and result.get("ran") is False, result
        assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    assert run({**ref, "release_hash": "s" * 64})["ok"] is True
    assert not withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
