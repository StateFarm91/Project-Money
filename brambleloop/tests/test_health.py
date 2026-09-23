"""#185: online means work is progressing, not that HTTP returned 200.

The test that carries this file is the one where everything is alive and nothing is
happening. Every liveness signal is green -- the worker ticks, the scheduler ticks, the
queue is empty, the database answers -- and the system has achieved nothing. An ordinary
health check calls that healthy, which is how a week of achieving nothing passes.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Job, JobStatus, PatternVersion, Product, SpendLimit)
from brambleloop.ops import health as H  # noqa: E402

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _alive(**over):
    base = {"worker_last_tick": (NOW - timedelta(seconds=10)).isoformat(),
            "scheduler_last_tick": (NOW - timedelta(seconds=30)).isoformat()}
    base.update(over)
    return base


def _read(db, runner_state=None, env=None):
    with db.session() as s:
        return H.read(s, runner_state=runner_state or _alive(), env=env or {}, now=NOW)


def _work(db, *, finished=None, status=JobStatus.DONE):
    with db.session() as s:
        s.add(Job(agent="a", job_type="t", status=status, inputs={},
                  finished_at=finished or (NOW - timedelta(minutes=5)),
                  created_at=NOW - timedelta(minutes=10)))


# --- the one that matters -----------------------------------------------------------------

def test_everything_alive_and_nothing_happening_is_idle_rather_than_healthy():
    db = _db()
    verdict = H.verdict(_read(db))
    assert verdict["state"] == H.IDLE
    assert "a week of achieving nothing passes a health check" in verdict["why"]
    alive = {r["signal"]: r["state"] for r in verdict["readings"]}
    assert alive["worker_heartbeat"] == H.HEALTHY
    assert alive["scheduler_freshness"] == H.HEALTHY
    assert alive["queue_age"] == H.HEALTHY
    assert alive["database"] == H.HEALTHY
    assert alive["progress"] == H.IDLE


def test_a_completed_job_in_the_window_is_what_makes_it_healthy():
    db = _db()
    _work(db)
    assert H.verdict(_read(db))["state"] == H.HEALTHY


def test_work_completed_before_the_window_does_not_count():
    db = _db()
    _work(db, finished=NOW - timedelta(days=2))
    assert H.verdict(_read(db))["state"] == H.IDLE


def test_a_failed_job_is_not_progress():
    db = _db()
    _work(db, status=JobStatus.FAILED)
    assert H.verdict(_read(db))["state"] == H.IDLE


# --- liveness signals ------------------------------------------------------------------------

def test_a_silent_worker_is_down():
    db = _db()
    _work(db)
    state = _alive(worker_last_tick=(NOW - timedelta(minutes=30)).isoformat())
    verdict = H.verdict(_read(db, runner_state=state))
    assert verdict["state"] == H.DOWN
    assert verdict["down"] == ["worker_heartbeat"]


def test_a_starting_worker_is_not_a_dead_one():
    db = _db()
    _work(db)
    verdict = H.verdict(_read(db, runner_state={"worker_starting": True}))
    assert verdict["state"] == H.HEALTHY


def test_a_worker_that_never_ticked_is_down_rather_than_unknown():
    db = _db()
    _work(db)
    verdict = H.verdict(_read(db, runner_state={"worker_last_tick": None,
                                                "scheduler_last_tick": None}))
    assert verdict["state"] == H.DOWN
    assert "worker_heartbeat" in verdict["down"]


def test_a_live_worker_and_a_stalled_queue_is_a_worker_that_is_not_working():
    db = _db()
    _work(db)
    with db.session() as s:
        s.add(Job(agent="a", job_type="t", status=JobStatus.PENDING, inputs={},
                  created_at=NOW - timedelta(hours=5)))
    verdict = H.verdict(_read(db))
    assert verdict["state"] == H.DEGRADED
    assert verdict["degraded"] == ["queue_age"]
    stalled = next(r for r in verdict["readings"] if r["signal"] == "queue_age")
    assert "alive and not working" in stalled["why"]


def test_a_stale_scheduler_means_no_cadence_has_fired():
    db = _db()
    _work(db)
    state = _alive(scheduler_last_tick=(NOW - timedelta(hours=2)).isoformat())
    verdict = H.verdict(_read(db, runner_state=state))
    assert "scheduler_freshness" in verdict["degraded"]


# --- absence is a gate, not a fault -------------------------------------------------------------

def test_an_unconfigured_integration_is_unknown_rather_than_down():
    """Reporting it as down makes the dashboard red for a decision nobody has made."""
    db = _db()
    readings = {r.signal: r for r in _read(db)}
    for signal in ("integrations", "rendered_pages", "model_gateway"):
        assert readings[signal].state == H.UNKNOWN
        assert "a gate rather than a fault" in readings[signal].why
    assert H.verdict(_read(db))["down"] == []


def test_a_configured_integration_reads_healthy():
    db = _db()
    readings = {r.signal: r for r in _read(db, env={"ANTHROPIC_API_KEY": "sk-x"})}
    assert readings["model_gateway"].state == H.HEALTHY


def test_nothing_ever_certified_is_a_state_rather_than_a_fault():
    db = _db()
    readings = {r.signal: r for r in _read(db)}
    assert readings["certificate_freshness"].state == H.UNKNOWN
    assert "not a fault" in readings["certificate_freshness"].why


def test_a_chain_that_has_stopped_producing_is_degraded():
    db = _db()
    _work(db)
    with db.session() as s:
        s.add(Product(slug="p", title="P"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json={}, certified=True,
                             created_at=NOW - timedelta(days=90)))
    verdict = H.verdict(_read(db))
    assert "certificate_freshness" in verdict["degraded"]


def test_a_paused_spend_limit_is_degraded():
    db = _db()
    _work(db)
    with db.session() as s:
        s.add(SpendLimit(scope="llm", daily_cap_cad=1.0, paused=True))
    verdict = H.verdict(_read(db))
    assert "spend" in verdict["degraded"]


# --- self-healing is bounded by what this system can do ------------------------------------------

def test_a_dead_letter_is_the_deploys_repair_rather_than_a_timers():
    """Re-driving on a fifteen-minute timer re-runs a failure nothing has fixed, ninety-six
    times a day. A dead letter is fixed by a code change, so the deploy is the trigger."""
    db = _db()
    with db.session() as s:
        s.add(Job(agent="a", job_type="t", status=JobStatus.DEAD, inputs={},
                  last_error="TypeError: something genuinely broke"))
    with db.session() as s:
        out = H.remediation(s, H.read(s, runner_state=_alive(), now=NOW))
    assert out["repaired_here"] == []
    handled = out["repaired_elsewhere"][0]
    assert handled["condition"] == "dead_letters" and handled["repaired_by"] == "deploy"
    assert "nothing has fixed" in handled["how"]


def test_a_deliberate_refusal_is_the_guard_working_rather_than_a_backlog():
    """Production holds 134 dead letters and every one is a publication refused by shadow
    mode. Reporting those as a repair backlog puts a permanent false number on the console,
    and a number that is always there is a number nobody reads."""
    db = _db()
    with db.session() as s:
        for i in range(3):
            s.add(Job(agent="store_operator", job_type="store.publish", status=JobStatus.DEAD,
                      inputs={}, last_error="refused: shadow mode forbids publication"))
    with db.session() as s:
        out = H.remediation(s, H.read(s, runner_state=_alive(), now=NOW))
    conditions = {h["condition"]: h for h in out["repaired_elsewhere"]}
    assert conditions["deliberate_refusals"]["count"] == 3
    assert conditions["deliberate_refusals"]["repaired_by"] == "nothing"
    assert "the guard working, not a backlog" in conditions["deliberate_refusals"]["how"]
    assert "dead_letters" not in conditions


def test_a_dead_worker_is_escalated_rather_than_restarted():
    """Nothing here has process control over its own host, and a repair that is announced
    and does not happen is worse than none, because nobody looks."""
    db = _db()
    state = _alive(worker_last_tick=(NOW - timedelta(minutes=30)).isoformat())
    with db.session() as s:
        readings = H.read(s, runner_state=state, now=NOW)
        out = H.remediation(s, readings)
    assert [e["needs"] for e in out["must_escalate"]] == ["restart_container"]
    assert "process control" in out["must_escalate"][0]["why"]
    assert "restart_container" not in H.ALREADY_AUTOMATIC


def test_a_stalled_queue_points_at_the_repair_that_already_runs():
    """A lease is reclaimed on every claim, so a stalled queue with leases being reclaimed
    is a worker that is not claiming at all -- a different signal's problem."""
    db = _db()
    with db.session() as s:
        s.add(Job(agent="a", job_type="t", status=JobStatus.PENDING, inputs={},
                  created_at=NOW - timedelta(hours=5)))
    with db.session() as s:
        out = H.remediation(s, H.read(s, runner_state=_alive(), now=NOW))
    stalled = next(h for h in out["repaired_elsewhere"] if h["condition"] == "stalled_queue")
    assert stalled["repaired_by"] == "queue.claim"
    assert "not claiming at all" in stalled["note"]


def test_this_sweep_repairs_nothing_itself_and_says_why():
    """Which is the finding rather than a gap: both obvious repairs already happen."""
    db = _db()
    _work(db)
    with db.session() as s:
        out = H.remediation(s, H.read(s, runner_state=_alive(), now=NOW))
    assert out["repaired_here"] == []
    assert out["repaired_elsewhere"] == [] and out["must_escalate"] == []
    assert "re-runs a failure nothing has fixed" in out["note"]


# --- escalation is for persistence -----------------------------------------------------------------

def test_one_bad_sweep_is_a_blip():
    bad = [H.Reading("worker_heartbeat", H.DOWN)]
    good = [H.Reading("worker_heartbeat", H.HEALTHY)]
    assert H.persistence([bad, good, good])["persistent"] == []


def test_the_same_signal_across_consecutive_sweeps_is_a_condition():
    bad = [H.Reading("worker_heartbeat", H.DOWN)]
    out = H.persistence([bad] * H.ESCALATE_AFTER_SWEEPS)
    assert out["persistent"] == ["worker_heartbeat"]
    assert out["consecutive"]["worker_heartbeat"] == H.ESCALATE_AFTER_SWEEPS


def test_a_run_is_broken_by_a_good_sweep_rather_than_accumulated():
    bad = [H.Reading("queue_age", H.DEGRADED)]
    good = [H.Reading("queue_age", H.HEALTHY)]
    out = H.persistence([bad, bad, good, bad])
    assert out["persistent"] == []
    assert out["consecutive"]["queue_age"] == 1


def test_a_signal_nobody_named_cannot_be_reported():
    try:
        H.Reading("vibes", H.HEALTHY)
    except H.HealthRefused as exc:
        assert "is not a signal" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented signal was reported")


def test_the_sweep_escalates_a_condition_and_not_a_blip():
    """Two bad sweeps raise nothing; the third raises once and the fourth does not raise
    again. The history comes from the handler's own audit trail rather than from memory,
    because a container replacement is exactly when conditions happen."""
    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Incident
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401  -- registers handlers
    from brambleloop.runtime.release import handle_health_sweep
    from brambleloop.runtime.worker import JobContext

    db = _db()
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    with db.session() as s:
        # A real condition: a job that has been pending for five hours. The worker is
        # demonstrably alive -- it is running this sweep -- and it is not draining the queue.
        s.add(Job(agent="a", job_type="t", status=JobStatus.PENDING, inputs={},
                  created_at=datetime.now(timezone.utc) - timedelta(hours=5)))

    escalated = []
    for i in range(4):
        ctx = JobContext(job=queue.enqueue("orchestrator", "ops.health",
                                           {"cadence": "health_sweep"},
                                           idempotency_key=f"h{i}"),
                         db=db, queue=queue, registry=Registry(db), phase=None)
        escalated.append(handle_health_sweep(ctx)["escalated"])

    assert escalated[0] == [] and escalated[1] == []
    assert escalated[2] == ["health:queue_age"]
    assert escalated[3] == []
    with db.session() as s:
        rows = list(s.scalars(select(Incident)))
    assert all(r.halts_publication is False for r in rows)   # infrastructure, not a product


def test_a_sweep_running_inside_a_worker_does_not_report_that_worker_down():
    """runner.STATE is process-local, so in a split deployment the process reading it is not
    the process writing it, and the heartbeat would read None forever -- an hourly "the
    worker is down" raised by a worker that is demonstrably running. This sweep executing at
    all is stronger evidence than a heartbeat field."""
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.release import handle_health_sweep
    from brambleloop.runtime.worker import JobContext

    db = _db()
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.health",
                                       {"cadence": "health_sweep"}),
                     db=db, queue=queue, registry=Registry(db), phase=None)
    out = handle_health_sweep(ctx)
    assert out["bad"] == []
    assert out["state"] == H.IDLE          # honest: alive, and achieving nothing yet


# --- #183: the console -----------------------------------------------------------------------

def _client():
    import os
    import tempfile

    tmp = tempfile.mkdtemp()
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{tmp}/console.sqlite"
    os.environ.setdefault("BRAMBLELOOP_EMBEDDED_WORKER", "0")
    from fastapi.testclient import TestClient

    from brambleloop.app import main as app_main

    return TestClient(app_main.app)


def test_the_console_answers_both_of_an_absent_owners_questions():
    """Is it working, and is anything waiting on me. A count of queued actions answers
    neither, which is why approvals arrive as cards with their consequence of waiting."""
    with _client() as c:
        body = c.get("/api/console").json()
    assert set(body) >= {"health", "queues", "products", "agents", "spend", "incidents",
                         "approvals", "experiments", "deployment", "learning_changes"}
    assert body["approvals"]["cards"]
    card = body["approvals"]["cards"][0]
    assert card["gate"] and card["action"]


def test_the_console_never_reports_healthy_while_nothing_is_happening():
    """A console that cannot say idle is one that will report a green week of nothing. In
    this harness the worker is deliberately not running, so the verdict is `down` -- and the
    reading that matters is `progress`, which is idle whatever the processes are doing."""
    with _client() as c:
        body = c.get("/api/console").json()
    readings = {r["signal"]: r["state"] for r in body["health"]["readings"]}
    assert readings["progress"] == H.IDLE
    assert body["health"]["state"] != H.HEALTHY


def test_the_dashboard_carries_the_two_views_the_requirement_named():
    with _client() as c:
        page = c.get("/").text
    assert "<h2>Waiting on the owner</h2>" in page
    assert "<h2>Learning changes</h2>" in page
    assert "<h2>Health</h2>" in page
    # and every block rendered: a guarded block that failed says so in place
    assert "unavailable: " not in page


def test_the_signals_endpoint_carries_its_evidence():
    with _client() as c:
        body = c.get("/api/health-signals").json()
    assert body["verdict"]["state"] in (H.HEALTHY, H.IDLE, H.DEGRADED, H.DOWN)
    assert body["remediation"]["repaired_here"] == []
    assert "restart_container" in body["cannot_repair"]


def test_state_says_what_online_is_allowed_to_mean():
    out = H.state()
    assert out["states"][:2] == [H.HEALTHY, H.IDLE]
    assert "not that HTTP returned 200" in out["note"]
    assert "restart_container" in out["cannot_repair"]
    assert set(out["already_automatic"]) == {"clear_expired_lease", "requeue_dead_letter"}



def _job(s, job_type, outputs, minutes_ago, now):
    import datetime

    from brambleloop.core.models import Job, JobStatus

    s.add(Job(agent="a", job_type=job_type, inputs={}, outputs=outputs,
              status=JobStatus.DONE,
              finished_at=now - datetime.timedelta(minutes=minutes_ago)))


def _now():
    import datetime

    return datetime.datetime.now(datetime.timezone.utc)


def test_a_cadence_repeating_itself_is_not_new_evidence():
    """2026-09-22, and the reason a stalled day looked healthy from the outside.

    The system ran 44 cadences and 2,893 jobs with every liveness signal green, while the
    gallery cadence re-judged the same twenty-five images every two hours -- returning
    `judged: 25` each time, at about CA$8.50 a day -- and five other cadences returned
    `ran: false`. `progress` counts completed jobs and so reported work being done.
    Completed jobs are not produced evidence, and nothing could tell them apart.
    """
    import datetime

    from brambleloop.core.db import Database
    from brambleloop.ops import health

    db = Database("sqlite://")
    db.create_all()
    now = _now()
    with db.session() as s:
        _job(s, "intel.gallery_analysis", {"judged": 25, "remaining": 475}, 30, now)
        _job(s, "intel.gallery_analysis", {"judged": 25, "remaining": 475}, 150, now)

    with db.session() as s:
        fresh, repeated = health._evidence(s, now)
    assert fresh == set()
    assert repeated == {"intel.gallery_analysis"}


def test_a_cadence_whose_result_moved_is_new_evidence():
    from brambleloop.core.db import Database
    from brambleloop.ops import health

    db = Database("sqlite://")
    db.create_all()
    now = _now()
    with db.session() as s:
        _job(s, "intel.gallery_analysis", {"judged": 25, "remaining": 450}, 30, now)
        _job(s, "intel.gallery_analysis", {"judged": 25, "remaining": 475}, 150, now)

    with db.session() as s:
        fresh, _ = health._evidence(s, now)
    assert fresh == {"intel.gallery_analysis"}


def test_the_sweep_refuses_to_call_a_spinning_loop_healthy():
    """The signal exists so that eight hours of this is visible rather than reassuring."""
    import os

    from brambleloop.core.db import Database
    from brambleloop.ops import health

    db = Database("sqlite://")
    db.create_all()
    now = _now()
    with db.session() as s:
        for i in range(health.MIN_COMPLETIONS + 2):
            _job(s, "intel.gallery_analysis", {"judged": 25, "remaining": 475}, 10 + i, now)

    with db.session() as s:
        readings = health.read(s, runner_state={}, env=dict(os.environ),
                               executing_worker=True)
    by = {r.signal: r for r in readings}
    assert by["progress"].state == health.HEALTHY, "jobs really did complete"
    assert by["evidence_freshness"].state == health.IDLE, \
        "a loop returning the same result every run reported as producing evidence"
    assert "intel.gallery_analysis" in \
        by["evidence_freshness"].evidence["cadences_repeating_themselves"]


def test_one_run_in_the_window_is_new_rather_than_repeated():
    """There is nothing for a first run to repeat, and calling it stale would be a verdict
    computed from absence of evidence."""
    from brambleloop.core.db import Database
    from brambleloop.ops import health

    db = Database("sqlite://")
    db.create_all()
    now = _now()
    with db.session() as s:
        _job(s, "seasonal.cycle_proof", {"complete": False}, 30, now)

    with db.session() as s:
        fresh, repeated = health._evidence(s, now)
    assert fresh == {"seasonal.cycle_proof"} and repeated == set()

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
