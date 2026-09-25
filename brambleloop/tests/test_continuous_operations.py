"""Restart, stale completion, concurrent admission and time-gated marketing regressions."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brambleloop.core.db import Database
from brambleloop.core.models import Job, JobStatus, OwnerAction, utcnow
from brambleloop.agents.registry import Registry
from brambleloop.queue.durable import JobQueue, LeaseLost
from brambleloop.growth import ads_readiness as ads
from brambleloop.gateway import anthropic as gw


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    database.create_all()
    Registry(database).seed_defaults()
    yield database
    database.engine.dispose()


@pytest.mark.parametrize("operation", ["complete", "fail", "heartbeat"])
def test_stale_attempt_cannot_mutate_successor(db, operation):
    q = JobQueue(db)
    job = q.enqueue("validator", "cir.compile")
    first = q.claim("same-worker-name")
    with db.session() as s:
        s.get(Job, job.id).lease_expires_at = utcnow() - timedelta(seconds=1)
    second = q.claim("same-worker-name")
    args = (job.id, "old failure") if operation == "fail" else (job.id,)
    with pytest.raises(LeaseLost):
        getattr(q, operation)(*args, lease_token=first.lease_token)
    assert q.get(job.id).lease_token == second.lease_token
    q.complete(job.id, {"winner": True}, lease_token=second.lease_token)
    assert q.get(job.id).outputs == {"winner": True}


def test_simultaneous_claims_are_distinct(db):
    q = JobQueue(db)
    for _ in range(8):
        q.enqueue("validator", "cir.compile")
    start = Barrier(8)
    def claim(i):
        start.wait()
        return q.claim(str(i)).id
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(claim, range(8)))
    assert len(set(ids)) == 8


def test_concurrent_budget_admission_cannot_share_last_dollar(db, monkeypatch):
    monkeypatch.setattr(gw, "monthly_ceiling_cad", lambda: 1.0)
    monkeypatch.setattr(gw, "estimate_cad", lambda *a, **k: 0.6)
    start = Barrier(2)
    def attempt(i):
        start.wait()
        try:
            gw.check_budget(db, model="test", input_tokens=1, max_tokens=1, holder=str(i))
            return "reserved"
        except gw.BudgetExceeded:
            return "refused"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ["refused", "reserved"]


def test_agent_daily_cap_counts_other_live_reservations(db, monkeypatch):
    monkeypatch.setattr(gw, "estimate_cad", lambda *a, **k: 0.6)
    gw.check_budget(db, model="test", input_tokens=1, max_tokens=1, agent="validator", holder="a")
    with pytest.raises(gw.AgentCeilingExceeded):
        gw.check_budget(db, model="test", input_tokens=1, max_tokens=1, agent="validator", holder="b")


def test_countdown_survives_restart_and_never_grants_eligibility(db):
    before = datetime(2026, 9, 25, tzinfo=timezone.utc)
    first = ads.tick(db, now=before)
    assert first["days_remaining"] == 9
    assert first["last_verified_at"] is None
    assert first["date_is_estimate"]
    restarted = Database(str(db.engine.url))
    try:
        due = ads.tick(restarted, now=ads.REPORTED_RECHECK)
        ads.tick(restarted, now=ads.REPORTED_RECHECK + timedelta(hours=1))
        assert due["etsy_ads_status"] == "RECHECK_REQUIRED"
        assert due["activation_authorised"] is False
        with restarted.session() as s:
            actions = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == ads.REFRESH_KEY)))
            assert len(actions) == 1
    finally:
        restarted.engine.dispose()


def test_verified_eligibility_is_not_spend_authority_and_expires(db):
    now = ads.REPORTED_RECHECK
    ads.tick(db, now=now)
    verified = ads.record_evidence(db, status="ELIGIBLE", evidence_source="Etsy UI evidence ref 1",
                                  verified_at=now, now=now)
    assert verified["etsy_ads_status"] == "ELIGIBLE"
    assert not verified["activation_authorised"]
    assert ads.tick(db, now=now + timedelta(hours=1))["etsy_ads_status"] == "ELIGIBLE"
    assert ads.tick(db, now=now + timedelta(days=1))["etsy_ads_status"] == "RECHECK_REQUIRED"


def test_future_evidence_is_refused(db):
    with pytest.raises(ValueError):
        ads.record_evidence(db, status="ELIGIBLE", evidence_source="Etsy UI",
            verified_at=utcnow() + timedelta(days=1))


def test_scheduler_and_worker_run_marketing_preparation(db):
    from brambleloop.runtime import pipeline
    from brambleloop.runtime.worker import Scheduler, Worker
    Scheduler(db).tick()
    worker = Worker(db, job_types=["marketing.ads_readiness"])
    assert worker.run_once()
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.job_type == "marketing.ads_readiness"))
        assert job.status == JobStatus.DONE
        assert job.outputs["preparation"]["campaign_activated"] is False


def test_lane_partition_is_disjoint_and_covers_every_handler():
    from brambleloop.runtime import pipeline
    from brambleloop.runtime.worker import handlers
    from brambleloop.runtime.lanes import partitions
    lanes = partitions(handlers.known(), "departments")
    flattened = [kind for kinds in lanes.values() for kind in kinds]
    assert len(flattened) == len(set(flattened))
    assert set(flattened) == set(handlers.known())
    assert "marketing.ads_readiness" in lanes["marketing"]
    assert "assets.owned_photography" in lanes["production"]


def test_marketing_progresses_while_production_is_blocked(db):
    from threading import Event
    from brambleloop.runtime.worker import HandlerRegistry, Worker
    registry = HandlerRegistry()
    started, release = Event(), Event()
    @registry.register("cir.compile")
    def slow(ctx):
        started.set()
        assert release.wait(10)
        return {"finished": True}
    @registry.register("marketing.ads_readiness")
    def marketing(ctx):
        return ads.tick(ctx.db)
    q = JobQueue(db)
    q.enqueue("validator", "cir.compile")
    job = q.enqueue("growth", "marketing.ads_readiness")
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(Worker(db, "production", job_types=["cir.compile"], registry=registry).run_once)
        try:
            assert started.wait(5)
            assert Worker(db, "marketing", job_types=["marketing.ads_readiness"], registry=registry).run_once()
            assert q.get(job.id).status == JobStatus.DONE
            assert not pending.done()
        finally:
            release.set()
        assert pending.result()


def test_worker_discards_stale_result_without_failing_new_attempt(db):
    from brambleloop.runtime.worker import HandlerRegistry, Worker
    registry = HandlerRegistry()
    q = JobQueue(db)
    job = q.enqueue("validator", "cir.compile")
    @registry.register("cir.compile")
    def reclaimed(ctx):
        with db.session() as s:
            s.get(Job, job.id).lease_expires_at = utcnow() - timedelta(seconds=1)
        new = q.claim("replacement")
        q.complete(new.id, {"correct": True}, lease_token=new.lease_token)
        return {"stale": True}
    worker = Worker(db, registry=registry)
    assert worker.run_once()
    assert worker.stats.completed == 0
    assert q.get(job.id).outputs == {"correct": True}


def test_ads_evidence_route_requires_operator_and_exposes_no_authority(db, monkeypatch):
    from fastapi.testclient import TestClient
    from brambleloop.app import main
    monkeypatch.setattr(main, "db", db)
    monkeypatch.setenv("BRAMBLELOOP_OPS_TOKEN", "test-only-operator-key-not-a-real-secret")
    client = TestClient(main.app)
    ads.tick(db)
    path = "/api/etsy/ads-readiness/evidence"
    data = {"status": "ELIGIBLE", "evidence_source": "dated Etsy Shop Manager capture",
            "verified_at": utcnow().isoformat()}
    assert client.post(path, json=data).status_code == 401
    response = client.post(path, json=data,
        headers={"Authorization": "Bearer test-only-operator-key-not-a-real-secret"})
    assert response.status_code == 200
    assert response.json()["activation_authorised"] is False
    assert client.get("/api/etsy/ads-readiness").json()["etsy_ads_status"] == "ELIGIBLE"


def test_one_healthy_lane_cannot_hide_a_stalled_lane():
    from brambleloop.app.runner import RunnerState
    state = RunnerState(enabled=True, worker_last_tick=utcnow(), lanes={
        "marketing": {"last_tick": utcnow().isoformat()},
        "production": {"last_tick": (utcnow() - timedelta(minutes=5)).isoformat()}})
    assert state.to_dict()["worker_alive"] is False


def test_embedded_department_runner_starts_refills_and_stops(db, monkeypatch):
    import time
    from brambleloop.app import runner
    from brambleloop.runtime import worker
    monkeypatch.setenv("BRAMBLELOOP_WORKER_LANES", "departments")
    monkeypatch.setenv("BRAMBLELOOP_EMBEDDED_WORKER", "1")
    monkeypatch.setattr(runner, "_START_DELAY", 0)
    monkeypatch.setattr(runner, "_SCHEDULER_INTERVAL", 0.05)
    monkeypatch.setattr(runner, "_IDLE_SLEEP", 0.01)
    monkeypatch.setattr(worker, "CADENCES", [("ads", "growth", "marketing.ads_readiness", 3600)])
    q = JobQueue(db)
    runner.start(db)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and ads.state(db)["etsy_ads_status"] == "NOT_INITIALISED":
            time.sleep(0.02)
        assert ads.state(db)["etsy_ads_status"] != "NOT_INITIALISED"
        job = q.enqueue("growth", "marketing.ads_readiness")
        while time.monotonic() < deadline and q.get(job.id).status != JobStatus.DONE:
            time.sleep(0.02)
        assert q.get(job.id).status == JobStatus.DONE
        assert set(runner.STATE.lanes) == {"operations", "marketing", "finance", "production"}
        assert runner.STATE.scheduler_last_tick is not None
    finally:
        runner.stop(timeout=5)
    assert not runner._threads
