"""Opt-in real-handler races on a disposable local PostgreSQL database."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import Job, JobStatus, Phase, SupportCase
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401 -- register handlers
from brambleloop.runtime.worker import Worker
from brambleloop.support import response_watch
from brambleloop.support.department import CustomerExperience


def test_sent_and_draft_transactions_serialize_in_both_orders():
    raw = os.getenv("CODEX_SUPPORT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("no disposable PostgreSQL test database supplied")
    parsed = make_url(raw)
    if (parsed.get_backend_name() != "postgresql" or parsed.host != "127.0.0.1"
            or parsed.database != "codex_support_test"
            or os.getenv("CODEX_SUPPORT_DISPOSABLE_DATABASE") != "yes"):
        pytest.fail("requires explicit disposable loopback PostgreSQL database")
    db = Database(raw, scratch=True)
    assert not inspect(db.engine).get_table_names(), "database must be empty"
    db.create_all()
    Registry(db).seed_defaults()
    for first in ("owner", "worker"):
        now = datetime.now(timezone.utc)
        case_id = response_watch.record_buyer_message(
            db, customer_ref=f"fixture-{first}", message="Where is my PDF?", now=now)["case_id"]
        job = JobQueue(db).enqueue("support", "support.reply", {"case_id": case_id},
                                   idempotency_key=f"fixture-race:{case_id}")
        locked, release = threading.Event(), threading.Event()

        def hold_before_flush(session, _context, _instances):
            if threading.current_thread().name == f"fixture-{first}" and any(
                    isinstance(row, SupportCase) and row.id == case_id for row in session.dirty):
                locked.set()
                assert release.wait(10)

        def owner():
            threading.current_thread().name = "fixture-owner"
            return response_watch.record_reply_sent(db, case_id)

        def worker():
            threading.current_thread().name = "fixture-worker"
            return Worker(db, f"fixture-support-{first}", phase=Phase.SHADOW,
                          job_types=["support.reply"]).run_once()

        event.listen(Session, "before_flush", hold_before_flush)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                initial = pool.submit(owner if first == "owner" else worker)
                assert locked.wait(10)
                other = pool.submit(worker if first == "owner" else owner)
                try:
                    with pytest.raises(TimeoutError):
                        other.result(timeout=0.25)
                finally:
                    release.set()
                initial.result(timeout=15)
                other.result(timeout=15)
        finally:
            event.remove(Session, "before_flush", hold_before_flush)
        with db.session() as session:
            case = session.get(SupportCase, case_id)
            assert case.sent and case.detail.get("first_response_at")
            assert session.get(Job, job.id).status == JobStatus.DONE
            if first == "owner":
                assert session.get(Job, job.id).outputs["skipped"] == "first_response_already_recorded"

    for first in ("owner", "triage"):
        now = datetime.now(timezone.utc)
        case_id = response_watch.record_buyer_message(
            db, customer_ref=f"fixture-triage-{first}", message="Where is my PDF?", now=now)["case_id"]
        locked, release = threading.Event(), threading.Event()

        def hold_before_flush(session, _context, _instances):
            if threading.current_thread().name == f"fixture-{first}" and any(
                    isinstance(row, SupportCase) and row.id == case_id for row in session.dirty):
                locked.set()
                assert release.wait(10)

        def owner():
            threading.current_thread().name = "fixture-owner"
            return response_watch.record_reply_sent(db, case_id)

        def triage():
            threading.current_thread().name = "fixture-triage"
            return CustomerExperience(db).triage_cases(now=now)

        event.listen(Session, "before_flush", hold_before_flush)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                initial = pool.submit(owner if first == "owner" else triage)
                assert locked.wait(10)
                other = pool.submit(triage if first == "owner" else owner)
                try:
                    with pytest.raises(TimeoutError):
                        other.result(timeout=0.25)
                finally:
                    release.set()
                initial.result(timeout=15)
                other.result(timeout=15)
        finally:
            event.remove(Session, "before_flush", hold_before_flush)
        with db.session() as session:
            case = session.get(SupportCase, case_id)
            assert case.sent and case.detail.get("first_response_at")
            assert case.detail.get("triaged_at")
