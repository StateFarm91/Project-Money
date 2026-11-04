"""An incident outage must not suppress a confirmed quality publication hold."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Incident, Job, JobStatus
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import quality_ops
from brambleloop.runtime.worker import Worker


def test_real_worker_holds_before_incident_failure_and_retries():
    cir = d._cir()
    db = d._db(cir, {"title": "Crochet pattern PDF", "description": "Guaranteed to fit.",
                     "tags": ["crochet"], "price_cad": 6.5, "state": "draft"})
    job = JobQueue(db).enqueue("policy", "gate.policy", {"slug": cir.slug, "version": cir.version,
                                                         "release_hash": "r" * 64})
    worker = Worker(db, "quality-incident-failure", job_types=["gate.policy"])
    with patch.object(quality_ops, "_incident", side_effect=RuntimeError("synthetic outage")):
        assert worker.run_once()
    with db.session() as session:
        row = session.get(Job, job.id)
        assert row.status == JobStatus.FAILED, (row.status, row.last_error)
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    # Expedite this synthetic retry; production backoff is unchanged.
    with db.session() as session:
        session.get(Job, job.id).run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert worker.run_once()
    with db.session() as session:
        row = session.get(Job, job.id)
        assert row.status == JobStatus.DONE and row.outputs["ok"] is False
        assert session.scalar(select(Incident).where(Incident.product_slug == cir.slug)) is not None
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
