"""Retention cannot erase durable draft admissions, including dead letters."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from brambleloop.core.db import Database
from brambleloop.core.models import Job, JobStatus
from brambleloop.ops import flow_health, retention
from brambleloop.queue.durable import DuplicateJob, JobQueue


def test_retention_and_purge_preserve_draft_admissions_after_restart(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'durable.sqlite'}")
    db.create_all()
    old = datetime.now(timezone.utc) - timedelta(days=500)
    with db.session() as session:
        for slug, status in (("refused", JobStatus.DONE), ("cancelled", JobStatus.CANCELLED),
                             ("dead", JobStatus.DEAD)):
            session.add(Job(agent="crochet_engineer", job_type="cir.draft", inputs={"slug": slug},
                            idempotency_key=f"draft:{slug}", status=status, created_at=old,
                            finished_at=old, last_error="shadow mode"))
        session.add(Job(agent="crochet_engineer", job_type="cir.draft",
                        inputs={"slug": "recovery"}, idempotency_key="seed:recovery:v1",
                        status=JobStatus.DONE, created_at=old, finished_at=old))
        # Make retention's job-type recency and completed-work floor irrelevant.
        for i in range(1005):
            session.add(Job(agent="test", job_type="housekeeping", inputs={}, status=JobStatus.DONE,
                            idempotency_key=f"test:{i}", created_at=old, finished_at=old))
    result = retention.apply(db)
    assert result["removed"]["jobs"] > 0
    assert JobQueue(db).purge_dead(job_types=["cir.draft"]) == 0
    reopened = Database(str(db.engine.url))
    assert flow_health.drafted_slugs(reopened, {"refused", "cancelled", "dead", "recovery"}) == {
        "refused", "cancelled", "dead", "recovery"}
    assert flow_health.drafted_slugs(reopened, (s for s in ["recovery"])) == {"recovery"}
    for slug in ("refused", "cancelled", "dead"):
        with pytest.raises(DuplicateJob):
            JobQueue(reopened).enqueue("crochet_engineer", "cir.draft", {"slug": slug},
                                       idempotency_key=f"draft:{slug}", priority=0)
    with reopened.session() as session:
        assert len(list(session.scalars(select(Job).where(Job.idempotency_key.like("draft:%"))))) == 3
