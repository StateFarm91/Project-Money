"""W4-ONDEMAND: run the existing checks now, and chain the follow-ons, without new authority.

Owner directive 2026-10-11: remove unnecessary waiting. These tests pin down five things:
- the "Run checks now" routes sit behind the owner session, CSRF and freshness gate;
- checks that call outside services need step-up;
- each check is rate-limited and audited, refusals included;
- a run only enqueues the job types the schedule already runs, never doubles one in flight,
  and spends nothing itself;
- the event chains fire on a model-probe, Etsy-probe or OAuth success, without multiplying.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ondemand.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_ondemand_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "BRAMBLELOOP_IMAGE_KEY", "BRAMBLELOOP_ARCHIVE")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-ONDEMAND harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Job, JobStatus,  # noqa: E402
                                     Phase)
from brambleloop.ops import on_demand as OD  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, MODEL_JOB_TYPES, Worker  # noqa: E402

PASS = "owner passphrase for the on-demand harness"
OPS = "d" * 40
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
SCHEDULED_TYPES = {row[2] for row in CADENCES}


def _session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def _fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def _expire_stepup():
    with DB.session() as s:
        for row in s.scalars(select(OwnerSession)):
            row.stepup_until = auth._now() - timedelta(minutes=1)


def _jobs(job_type: str) -> list[Job]:
    with DB.session() as s:
        rows = list(s.scalars(select(Job).where(Job.job_type == job_type)))
        for r in rows:
            s.expunge(r)
        return rows


def _clear(*job_types: str, audits: tuple[str, ...] = ()):
    with DB.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type.in_(job_types))):
            s.delete(j)
        for a in s.scalars(select(AuditLog).where(AuditLog.action.in_(audits))):
            s.delete(a)


# ---- auth, CSRF, step-up -----------------------------------------------------------------

def test_routes_need_a_session_and_csrf():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/checks").status_code == 401
    assert anon.post("/api/cc/checks/launch_readiness/run", json={}).status_code == 401
    c, _csrf = _session()
    r = c.post("/api/cc/checks/launch_readiness/run", json={},
               headers={"X-CC-Nonce": uuid.uuid4().hex, "X-CC-Timestamp": str(int(time.time()))})
    assert r.status_code == 403 and r.json()["code"] == "CSRF", r.text


def test_status_lists_every_check_with_its_scheduled_cadence():
    c, _ = _session()
    body = c.get("/api/cc/checks").json()
    keys = {row["key"] for row in body["checks"]}
    assert keys == set(OD.CHECKS)
    for row in body["checks"]:
        assert row["jobs"] and all(j["scheduled_every_s"] > 0 for j in row["jobs"])
        assert row["requires_stepup"] == OD.CHECKS[row["key"]].external


def test_an_external_check_needs_step_up_and_queues_nothing_without_it():
    _clear("model.probe", audits=(OD.RUN_ACTION,))
    c, csrf = _session()
    _expire_stepup()
    r = c.post("/api/cc/checks/model/run", json={}, headers=_fresh(csrf))
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert _jobs("model.probe") == []


def test_an_internal_check_runs_without_step_up_and_is_audited():
    _clear("launch.readiness", audits=(OD.RUN_ACTION,))
    c, csrf = _session()
    _expire_stepup()
    r = c.post("/api/cc/checks/launch_readiness/run", json={}, headers=_fresh(csrf))
    assert r.status_code == 200, r.text
    [res] = r.json()["results"]
    assert res["enqueued"] is True
    [job] = _jobs("launch.readiness")
    assert job.agent == "orchestrator" and job.inputs["on_demand"] is True
    with DB.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == OD.RUN_ACTION,
                                              AuditLog.artifact == "check:launch_readiness"))
        assert row is not None and row.detail["by"].startswith("owner:cc:")


def test_a_second_run_inside_the_window_is_429_audited_and_queues_nothing():
    _clear("ops.continuity", audits=(OD.RUN_ACTION, OD.REFUSED_ACTION))
    c, csrf = _session()
    assert c.post("/api/cc/checks/continuity/run", json={}, headers=_fresh(csrf)).status_code == 200
    r = c.post("/api/cc/checks/continuity/run", json={}, headers=_fresh(csrf))
    assert r.status_code == 429 and r.json()["code"] == "RATE_LIMITED", r.text
    assert len(_jobs("ops.continuity")) == 1
    with DB.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == OD.REFUSED_ACTION,
                                               AuditLog.artifact == "check:continuity"))


def test_an_external_check_with_step_up_queues_the_scheduled_job():
    _clear("model.probe", audits=(OD.RUN_ACTION,))
    c, csrf = _session()                   # a fresh login carries a step-up window
    r = c.post("/api/cc/checks/model/run", json={}, headers=_fresh(csrf))
    assert r.status_code == 200, r.text
    [job] = _jobs("model.probe")
    assert job.agent == "orchestrator"


def test_unknown_check_is_404():
    c, csrf = _session()
    assert c.post("/api/cc/checks/nope/run", json={}, headers=_fresh(csrf)).status_code == 404


# ---- enqueue correctness and no spend ----------------------------------------------------

def test_every_check_only_uses_scheduled_job_types_and_spends_nothing():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    with DB.session() as s:
        cost_before = s.scalar(select(func.count()).select_from(CostEntry))
    for key in OD.CHECKS:
        out = OD.run_check(DB, key, actor="owner:cc:test", now=now)
        for res in out["results"]:
            assert res["job_type"] in SCHEDULED_TYPES, res
    with DB.session() as s:
        assert s.scalar(select(func.count()).select_from(CostEntry)) == cost_before


def test_a_job_already_in_flight_is_not_doubled():
    _clear("launch.readiness", audits=(OD.RUN_ACTION,))
    JobQueue(DB).enqueue("orchestrator", "launch.readiness", {}, idempotency_key="sched-x")
    out = OD.run_check(DB, "launch_readiness", actor="owner:cc:test",
                       now=datetime(2031, 1, 1, tzinfo=timezone.utc))
    assert out["results"][0]["enqueued"] is False
    assert len(_jobs("launch.readiness")) == 1


def test_paid_checks_are_spaced_further_apart():
    _clear("ops.capability_probes", audits=(OD.RUN_ACTION, OD.REFUSED_ACTION))
    t0 = datetime(2032, 1, 1, tzinfo=timezone.utc)
    OD.run_check(DB, "capabilities", actor="owner:cc:test", now=t0)
    try:
        OD.run_check(DB, "capabilities", actor="owner:cc:test", now=t0 + timedelta(minutes=5))
    except OD.CheckRefused as exc:
        assert exc.code == "RATE_LIMITED" and exc.retry_after_s > 0
    else:
        raise AssertionError("a paid check ran twice in five minutes")


# ---- event chains --------------------------------------------------------------------------

def _parked(job_type: str, key: str) -> int:
    job = JobQueue(DB).enqueue("creative_director", job_type, {}, idempotency_key=key,
                               run_after=datetime.now(timezone.utc) + timedelta(minutes=25))
    return job.id


def test_model_ok_unparks_parked_jobs_and_queues_capability_probes_on_transition():
    _clear("ops.capability_probes", *MODEL_JOB_TYPES)
    jid = _parked(sorted(MODEL_JOB_TYPES)[0], "parked-1")
    out = OD.after_model_ok(DB, previous={"ok": False}, on_demand=False)
    assert out["unparked"] == 1 and out["capability_probes"]["enqueued"] is True
    with DB.session() as s:
        assert OD._aware(s.get(Job, jid).run_after) <= datetime.now(timezone.utc)
    again = OD.after_model_ok(DB, previous={"ok": True}, on_demand=True)
    assert again["capability_probes"]["enqueued"] is False   # one in flight already
    assert len(_jobs("ops.capability_probes")) == 1


def test_a_routine_scheduled_success_does_not_queue_extra_probes():
    _clear("ops.capability_probes")
    out = OD.after_model_ok(DB, previous={"ok": True}, on_demand=False)
    assert out["capability_probes"] is None and _jobs("ops.capability_probes") == []


def test_the_model_probe_handler_runs_the_chain():
    from brambleloop.gateway import anthropic as gw

    _clear("model.probe", "ops.capability_probes", audits=("model.probe",))
    with DB.session() as s:
        s.add(AuditLog(actor="orchestrator", action="model.probe",
                       detail={"ok": False, "reason": "credit balance is too low"}))
    original = gw.probe
    gw.probe = lambda db, **kw: {"ok": True, "model": "stub"}
    try:
        JobQueue(DB).enqueue("orchestrator", "model.probe", {"on_demand": True},
                             priority=0, idempotency_key="mp-chain")
        w = Worker(DB, "w-od-model", phase=Phase.SHADOW, job_types=["model.probe"])
        w.run_once()
    finally:
        gw.probe = original
    [job] = [j for j in _jobs("model.probe") if j.idempotency_key == "mp-chain"]
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["chain"]["capability_probes"]["enqueued"] is True
    assert len(_jobs("ops.capability_probes")) == 1


def test_etsy_ok_queues_taxonomy_and_market_intel_once_per_hour():
    types = ("listing.taxonomy_refresh", "mjs.scan", "intel.serp_capture")
    _clear(*types)
    out = OD.after_etsy_ok(DB, trigger="test")
    assert [r["job_type"] for r in out["results"]] == list(types)
    assert all(r["enqueued"] for r in out["results"])
    assert _jobs("listing.taxonomy_refresh")[0].agent == "listing"
    assert _jobs("mjs.scan")[0].agent == "market_radar"
    again = OD.after_etsy_ok(DB, trigger="test")
    assert not any(r["enqueued"] for r in again["results"])
    assert all(len(_jobs(t)) == 1 for t in types)


def test_the_etsy_probe_handler_chains_only_for_an_on_demand_recheck():
    from brambleloop.intel import etsy_public as ep

    types = ("listing.taxonomy_refresh", "mjs.scan", "intel.serp_capture")
    _clear("etsy.probe", *types, audits=("etsy.probe",))
    with DB.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": False}))
    original = ep.probe
    ep.probe = lambda db, **kw: {"ok": True, "application_id": 1}
    try:
        JobQueue(DB).enqueue("market_radar", "etsy.probe", {}, priority=0,
                             idempotency_key="ep-scheduled")
        Worker(DB, "w-od-etsy", phase=Phase.SHADOW, job_types=["etsy.probe"]).run_once()
        assert _jobs("mjs.scan") == [], "a scheduled probe must not fan out"
        JobQueue(DB).enqueue("market_radar", "etsy.probe", {"on_demand": True}, priority=0,
                             idempotency_key="ep-chain")
        Worker(DB, "w-od-etsy", phase=Phase.SHADOW, job_types=["etsy.probe"]).run_once()
    finally:
        ep.probe = original
    assert all(len(_jobs(t)) == 1 for t in types)


def test_a_successful_oauth_callback_queues_the_follow_ons():
    from brambleloop.integrations import etsy_authorise

    types = ("listing.taxonomy_refresh", "mjs.scan", "intel.serp_capture")
    _clear(*types)
    done = SimpleNamespace(ok=True, outcome="granted", detail={}, http_status=200,
                           headline="Connected", explanation="ok", what_to_do="nothing")
    original = etsy_authorise.finish
    etsy_authorise.finish = lambda db, params, transport=None: done
    try:
        c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
        r = c.get("/api/etsy/oauth/callback?code=x&state=y")
    finally:
        etsy_authorise.finish = original
    assert r.status_code == 200, r.text
    assert all(len(_jobs(t)) == 1 for t in types)


def test_the_recheck_button_marks_its_probe_on_demand():
    from brambleloop.app.command_center import etsy_connect

    out = etsy_connect.recheck(DB, actor="owner:cc:test")
    with DB.session() as s:
        assert s.get(Job, out["job_id"]).inputs.get("on_demand") is True


def _run_all() -> int:
    failures = 0
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failures += 1
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
