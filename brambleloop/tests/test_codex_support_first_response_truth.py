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
from brambleloop.support.department import CustomerExperience


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
        assert case.answer and not case.resolved and not case.sent
        assert case.detail["response_measured_as"] == "draft_ready"
        # Legacy drafts were already marked resolved. They still must not
        # suppress the first-response clock after this change is deployed.
        case.resolved = True
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


def test_new_held_draft_without_existing_case_is_not_resolved(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    reply = CustomerExperience(db).handle(customer_ref="fixture-buyer",
                                          message="Where is my PDF?")
    assert not reply.sent and not reply.escalated
    with db.session() as session:
        case = session.scalar(select(SupportCase))
        assert case.answer and not case.sent and not case.resolved


def test_late_draft_does_not_replace_previously_recorded_sent_case(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    now = datetime.now(timezone.utc)
    case_id = response_watch.record_buyer_message(
        db, customer_ref="fixture-buyer", message="Where is my PDF?", now=now)["case_id"]
    with db.session() as session:
        session.get(SupportCase, case_id).answer = "Previously recorded owner answer"
    response_watch.record_reply_sent(db, case_id, now=now)
    job = JobQueue(db).enqueue("support", "support.reply", {"case_id": case_id},
                               idempotency_key=f"fixture-late:{case_id}")
    assert Worker(db, "fixture-late-worker", phase=Phase.SHADOW,
                  job_types=["support.reply"]).run_once()
    # The department can also be called directly, outside the worker handler.
    CustomerExperience(db).handle(customer_ref="fixture-buyer", message="Where is my PDF?",
                                  case_id=case_id)
    with db.session() as session:
        case = session.get(SupportCase, case_id)
        assert session.get(Job, job.id).outputs["skipped"] == "first_response_already_recorded"
        assert case.sent and case.detail["first_response_at"]
        assert case.answer == "Previously recorded owner answer"
        assert "response_measured_as" not in case.detail


def test_triage_does_not_enqueue_a_draft_after_recorded_sent_reply(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    now = datetime.now(timezone.utc)
    case_id = response_watch.record_buyer_message(
        db, customer_ref="fixture-buyer", message="Where is my PDF?", now=now)["case_id"]
    response_watch.record_reply_sent(db, case_id, now=now)
    result = CustomerExperience(db).triage_cases(JobQueue(db), now=now)
    assert case_id not in result["needing_reply"]
    assert not result["reply_jobs"]
    with db.session() as session:
        case = session.get(SupportCase, case_id)
        assert case.sent and case.detail["first_response_at"]


def test_invalid_first_response_timestamps_cannot_silence_the_watch(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    now = datetime.now(timezone.utc)
    received = now - timedelta(hours=30)
    markers = ["not-a-time", (now + timedelta(hours=1)).isoformat(),
               (received - timedelta(minutes=1)).isoformat(),
               (received + timedelta(hours=1)).isoformat()]
    ids = []
    for index, marker in enumerate(markers):
        case_id = response_watch.record_buyer_message(
            db, customer_ref=f"fixture-{index}", message="Where is my PDF?",
            received_at=received, now=now)["case_id"]
        ids.append(case_id)
        with db.session() as session:
            case = session.get(SupportCase, case_id)
            case.detail = {**case.detail, "first_response_at": marker}
    result = response_watch.watch(db, now=now)
    assert all(case_id in result["raised"] for case_id in ids[:3])
    assert ids[3] not in result["raised"]


def test_invalid_legacy_response_marker_does_not_suppress_real_draft_worker(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    now = datetime.now(timezone.utc)
    case_id = response_watch.record_buyer_message(
        db, customer_ref="fixture-buyer", message="Where is my PDF?",
        received_at=now - timedelta(hours=30), now=now)["case_id"]
    with db.session() as session:
        case = session.get(SupportCase, case_id)
        case.detail = {**case.detail, "first_response_at": "not-a-time"}
    result = CustomerExperience(db).triage_cases(JobQueue(db), now=now)
    assert case_id in [entry["case"] for entry in result["reply_jobs"]]
    assert Worker(db, "fixture-invalid-marker", phase=Phase.SHADOW,
                  job_types=["support.reply"]).run_once()
    with db.session() as session:
        case = session.get(SupportCase, case_id)
        assert case.answer and not case.sent and not case.resolved
        assert case.detail["first_response_at"] == "not-a-time"
        assert case.detail["response_measured_as"] == "draft_ready"
    assert case_id in response_watch.watch(db, now=now)["raised"]


def test_operator_intake_deduplicates_only_same_product_and_version(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from brambleloop.core import opsauth

    monkeypatch.setenv(opsauth.TOKEN_VAR, "test-operator-token-for-fixtures-only")
    monkeypatch.setenv("BRAMBLELOOP_DATABASE_URL", f"sqlite:///{tmp_path / 'support.db'}")
    from brambleloop.app import main

    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    monkeypatch.setattr(main, "db", db)
    client = TestClient(main.app)
    headers = {"Authorization": "Bearer test-operator-token-for-fixtures-only"}
    body = {"event": "buyer_message", "customer_ref": "fixture-buyer",
            "message": "Where is my PDF?", "product_slug": "fixture-a", "version": "1.0.0"}
    assert client.post("/api/support/messages", json=body).status_code == 401
    first = client.post("/api/support/messages", headers=headers, json=body).json()
    repeat = client.post("/api/support/messages", headers=headers, json=body).json()
    assert repeat["duplicate"] and repeat["case_id"] == first["case_id"]
    other_product = client.post("/api/support/messages", headers=headers,
                                json={**body, "product_slug": "fixture-b"}).json()
    other_version = client.post("/api/support/messages", headers=headers,
                                json={**body, "version": "2.0.0"}).json()
    unknown_version = client.post("/api/support/messages", headers=headers,
                                  json={**body, "version": None}).json()
    assert len({first["case_id"], other_product["case_id"],
                other_version["case_id"], unknown_version["case_id"]}) == 4
    received = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    timed = {**body, "received_at": received}
    timed_first = client.post("/api/support/messages", headers=headers, json=timed).json()
    timed_repeat = client.post("/api/support/messages", headers=headers, json=timed).json()
    timed_other = client.post("/api/support/messages", headers=headers,
                              json={**timed, "version": "2.0.0"}).json()
    assert timed_repeat["duplicate"] and timed_repeat["case_id"] == timed_first["case_id"]
    assert timed_other["case_id"] != timed_first["case_id"]
    too_long = client.post("/api/support/messages", headers=headers,
                           json={**body, "customer_ref": "x" * 81})
    assert too_long.status_code == 400
    with db.session() as session:
        cases = list(session.scalars(select(SupportCase)))
        assert len(cases) == 6
        assert session.get(SupportCase, other_version["case_id"]).version == "2.0.0"
