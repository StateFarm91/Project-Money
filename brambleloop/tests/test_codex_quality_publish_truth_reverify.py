"""Daily quality recheck must apply existing publish-name safety truth."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Job, JobStatus, Listing
from brambleloop.products import inventory
from brambleloop.publish import eligibility, withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker


def test_real_worker_holds_child_audience_not_bound_to_design_and_recovers():
    cir = inventory._engineered("heart-row-ring-pillow")
    listing = {"title": "Ring pillow crochet pattern", "description": "A crochet ring pillow.",
               "tags": ["baby gift"], "price_cad": 6.5, "state": "draft"}
    assert any("child audience" in x for x in eligibility.name_truth(cir, listing))
    db = d._db(cir, listing)
    def run():
        job = JobQueue(db).enqueue("asset_truth", "gate.asset_truth", {"slug": cir.slug,
            "version": cir.version, "release_hash": "r" * 64})
        assert Worker(db, "quality-child-audience", job_types=["gate.asset_truth"]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)
    result = run()
    assert result["ok"] is False and "child audience" in str(result["problems"]), result
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    with db.session() as session:
        session.scalar(select(Listing)).tags = ["wedding gift"]
    assert run()["ok"] is True
    assert not withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
