"""Held support drafts must not close the buyer's first-response alert."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import Incident, Job, JobStatus, OwnerAction, Phase, SupportCase
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401 -- register real handlers
from brambleloop.runtime.worker import Worker
from brambleloop.support import response_watch


def test_worker_draft_keeps_first_response_open_until_owner_records_sent(tmp_path):
    url = f"sqlite:///{tmp_path / 'support.db'}"
    db = Database(url, scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    now = datetime.now(timezone.utc)
    case_id = response_watch.record_buyer_message(
        db, customer_ref="fixture-buyer", message="Where is my PDF?",
        received_at=now - timedelta(hours=30), now=now)["case_id"]
    queue = JobQueue(db)
    job = queue.enqueue("support", "support.reply", {"case_id": case_id},
                        idempotency_key=f"fixture-support:{case_id}")
    assert Worker(db, "fixture-support-worker", phase=Phase.SHADOW,
                  job_types=["support.reply"]).run_once()
    with db.session() as session:
        assert session.get(Job, job.id).status == JobStatus.DONE
        case = session.get(SupportCase, case_id)
        assert case.answer and case.resolved and not case.sent
        assert case.detail["response_measured_as"] == "draft_ready"
    # A new database instance models a worker restart; no customer is contacted.
    reopened = Database(url, scratch=True)
    first = response_watch.watch(reopened, now=now)
    assert case_id in first["raised"]
    second = response_watch.watch(reopened, now=now + timedelta(hours=7))
    assert case_id in second["escalated"]
    with reopened.session() as session:
        action = session.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == response_watch.key_for(case_id)))
        incident = session.scalar(select(Incident).where(
            Incident.signature == f"{response_watch.SIGNATURE_PREFIX}case:{case_id}"))
        assert not action.done and not incident.resolved and incident.severity == "P1"
    response_watch.record_reply_sent(reopened, case_id, now=now + timedelta(hours=7))
    assert case_id in response_watch.watch(reopened, now=now + timedelta(hours=7))["closed"]
