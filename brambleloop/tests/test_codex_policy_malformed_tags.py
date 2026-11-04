"""Malformed listing tags must not clear a policy re-verification hold."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Job, JobStatus, Listing
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker


def test_real_policy_worker_keeps_hold_until_tags_are_well_formed():
    cir = d._cir()
    db = d._db(cir, {"title": "Crochet pattern PDF", "description": "Guaranteed to fit.",
                     "tags": ["crochet"], "price_cad": 6.5, "state": "draft"})
    def run():
        job = JobQueue(db).enqueue("policy", "gate.policy", {"slug": cir.slug,
            "version": cir.version, "release_hash": "r" * 64})
        assert Worker(db, "malformed-tags", job_types=["gate.policy"]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)
    assert run()["ok"] is False
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    for malformed in ({"crochet": True}, "crochet", None, [42]):
        with db.session() as session:
            row = session.scalar(select(Listing))
            row.description, row.tags = "Crochet pattern.", malformed
        assert run()["ok"] is False
        assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    with db.session() as session:
        session.scalar(select(Listing)).tags = ["crochet"]
    assert run()["ok"] is True
    assert not withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
