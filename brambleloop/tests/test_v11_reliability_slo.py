"""v1.1 lane I: SLO math, UNKNOWN on no data, stale-scheduler detection, leases, watchdog.

F-923 / F-924. Every objective is computed from durable rows; these tests write those rows
directly (jobs, ops_runtime_samples, incidents) and check the arithmetic and the incidents.
No clock is faked in production code: `now` is an explicit parameter.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus  # noqa: E402
from brambleloop.ops import slo  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _job(s, job_type="ops.queue_check", *, status=JobStatus.DONE, created=None, started=None,
         finished=None, key=None, outputs=None, run_after=None):
    created = created or NOW - timedelta(minutes=5)
    j = Job(agent="orchestrator", job_type=job_type, status=status, created_at=created,
            run_after=run_after or created, started_at=started, finished_at=finished,
            idempotency_key=key, outputs=outputs, inputs={})
    s.add(j)
    s.flush()
    return j


def _open(db, sig):
    with db.session() as s:
        return [i for i in s.query(Incident).filter(Incident.signature == sig).all()]


# ---- error budget arithmetic ---------------------------------------------


def test_error_budget_states_and_unknown():
    assert slo.error_budget(None, 0.99)["state"] == slo.UNKNOWN
    assert slo.error_budget(None, 0.99)["budget_consumed_share"] is None
    met = slo.error_budget(0.995, 0.99)
    assert met["state"] == slo.MET and abs(met["budget_consumed_share"] - 0.5) < 1e-9
    risk = slo.error_budget(0.992, 0.99)
    assert risk["state"] == slo.AT_RISK, risk
    br = slo.error_budget(0.98, 0.99)
    assert br["state"] == slo.BREACHED and br["budget_remaining_share"] == 0.0
    perfect_target = slo.error_budget(1.0, 1.0)
    assert perfect_target["state"] == slo.MET
    assert slo.error_budget(0.9, 1.0)["state"] == slo.BREACHED


# ---- UNKNOWN when there is no data ------------------------------------------


def test_empty_database_is_unknown_never_zero_or_met():
    db = _db()
    out = slo.summary(db)
    json.dumps(out)  # contract: JSON-serialisable
    assert out["status"] == slo.UNKNOWN, out["status"]
    for key in ("status", "as_of", "basis", "items", "sources"):
        assert key in out
    slos = [i for i in out["items"] if i["kind"] == "slo"]
    assert len(slos) == len(slo.SLOS)
    for item in slos:
        assert item["state"] == slo.UNKNOWN, item
        assert item["sli"] is None, item
    depts = [i for i in out["items"] if i["kind"] == "department"]
    assert depts
    for d in depts:
        assert d["state"] == slo.UNKNOWN, d


def test_summary_accepts_an_open_session_too():
    db = _db()
    with db.session() as s:
        out = slo.summary(s)
    assert out["status"] == slo.UNKNOWN


# ---- F-923 availability -----------------------------------------------------


def test_availability_needs_an_external_probe_not_a_process_heartbeat():
    db = _db()
    slo.record_heartbeat(db, "web", instance="web-1", now=NOW - timedelta(minutes=1))
    with db.session() as s:
        r = slo.availability(s, NOW)
    assert r["state"] == slo.UNKNOWN and r["sli"] is None
    assert r["measure"]["proxy"] is not None  # shown, labelled proxy, not used as the SLI


def test_availability_counts_intervals_and_breaches_on_a_failed_interval():
    db = _db()
    start = NOW - timedelta(hours=2)
    for i in range(24):
        slo.record_probe(db, slo.AVAILABILITY_COMPONENT, ok=True,
                         now=start + timedelta(minutes=5 * i, seconds=30))
    with db.session() as s:
        r = slo.availability(s, NOW)
    assert r["sli"] == 1.0 and r["state"] == slo.MET, r
    slo.record_probe(db, slo.AVAILABILITY_COMPONENT, ok=False,
                     now=NOW - timedelta(minutes=2))
    with db.session() as s:
        r = slo.availability(s, NOW)
    assert r["state"] == slo.BREACHED, r
    assert r["sli"] < 1.0


def test_availability_with_thin_coverage_is_unknown_not_up():
    db = _db()
    # Two probes ten hours apart: coverage far below 50% of the span.
    slo.record_probe(db, slo.AVAILABILITY_COMPONENT, ok=True, now=NOW - timedelta(hours=10))
    slo.record_probe(db, slo.AVAILABILITY_COMPONENT, ok=True, now=NOW - timedelta(minutes=1))
    with db.session() as s:
        r = slo.availability(s, NOW)
    assert r["state"] == slo.UNKNOWN, r
    assert r["measure"]["coverage"] < slo.MIN_COVERAGE


# ---- F-924 scheduler: stale detection and incidents ------------------------


def test_stale_scheduler_from_cadence_jobs_raises_and_then_resolves_an_incident():
    db = _db()
    with db.session() as s:
        _job(s, "ops.heartbeat", key="cadence:infra_heartbeat:1",
             created=NOW - timedelta(hours=2), started=NOW - timedelta(hours=2),
             finished=NOW - timedelta(hours=2))
    with db.session() as s:
        st = slo.scheduler_staleness(s, NOW)
    assert st["stale"] is True and st["age_s"] >= 7200, st
    report = slo.check(db, now=NOW)
    assert slo.SIG_SCHEDULER_STALE in report["incidents"]["opened"], report["incidents"]
    rows = _open(db, slo.SIG_SCHEDULER_STALE)
    assert len(rows) == 1 and rows[0].severity == "P1" and not rows[0].resolved
    # Re-check while still stale: restated, not duplicated.
    report = slo.check(db, now=NOW + timedelta(minutes=1))
    assert slo.SIG_SCHEDULER_STALE in report["incidents"]["restated"]
    assert len(_open(db, slo.SIG_SCHEDULER_STALE)) == 1
    # The scheduler comes back (self-heartbeat wired): the incident closes with evidence.
    slo.record_heartbeat(db, "scheduler", instance="sched-1", now=NOW + timedelta(minutes=2))
    report = slo.check(db, now=NOW + timedelta(minutes=3))
    assert slo.SIG_SCHEDULER_STALE in report["incidents"]["resolved"], report["incidents"]
    row = _open(db, slo.SIG_SCHEDULER_STALE)[0]
    assert row.resolved and "scheduler seen again" in row.detail["resolution"]


def test_scheduler_heartbeat_takes_precedence_and_has_a_tighter_threshold():
    db = _db()
    with db.session() as s:
        _job(s, "ops.heartbeat", key="cadence:infra_heartbeat:2",
             created=NOW - timedelta(minutes=5))
    slo.record_heartbeat(db, "scheduler", now=NOW - timedelta(minutes=20))
    with db.session() as s:
        st = slo.scheduler_staleness(s, NOW)
    assert st["stale"] is True and "scheduler" in st["source"], st


def test_no_scheduler_evidence_is_unknown_not_stale():
    db = _db()
    with db.session() as s:
        st = slo.scheduler_staleness(s, NOW)
    assert st["stale"] is None
    report = slo.check(db, now=NOW)
    assert report["incidents"]["opened"] == []


def test_scheduler_freshness_sli_from_heartbeats():
    db = _db()
    for m in range(0, 120):
        slo.record_heartbeat(db, "scheduler", now=NOW - timedelta(minutes=120 - m))
    with db.session() as s:
        r = slo.scheduler_freshness(s, NOW)
    assert r["sli"] == 1.0 and r["state"] == slo.MET, r
    # A 40-minute gap in the last two hours breaches 99%.
    db2 = _db()
    for m in list(range(0, 60)) + list(range(100, 120)):
        slo.record_heartbeat(db2, "scheduler", now=NOW - timedelta(minutes=120 - m))
    with db2.session() as s:
        r2 = slo.scheduler_freshness(s, NOW)
    assert r2["state"] == slo.BREACHED and r2["sli"] < 0.99, r2


def test_worker_stall_detected_when_due_work_waits_and_nothing_starts():
    db = _db()
    with db.session() as s:
        _job(s, "finance.governor", status=JobStatus.PENDING,
             created=NOW - timedelta(hours=1), run_after=NOW - timedelta(hours=1))
    report = slo.check(db, now=NOW)
    assert report["worker"]["stalled"] is True
    assert slo.SIG_WORKER_STALLED in report["incidents"]["opened"]
    with db.session() as s:
        _job(s, "ops.queue_check", status=JobStatus.RUNNING, created=NOW,
             started=NOW + timedelta(minutes=1))
    report = slo.check(db, now=NOW + timedelta(minutes=2))
    assert report["worker"]["stalled"] is False
    assert slo.SIG_WORKER_STALLED in report["incidents"]["resolved"]


# ---- F-924 queue latency, cadence freshness, recovery time -----------------


def test_queue_latency_fraction_and_percentiles():
    db = _db()
    with db.session() as s:
        for i in range(19):
            c = NOW - timedelta(hours=3, minutes=i)
            _job(s, created=c, started=c + timedelta(minutes=1), finished=c + timedelta(minutes=2))
        c = NOW - timedelta(hours=2)
        _job(s, created=c, started=c + timedelta(minutes=40), finished=c + timedelta(minutes=41))
    with db.session() as s:
        r = slo.queue_latency(s, NOW)
    assert abs(r["sli"] - 19 / 20) < 1e-9, r
    # Exactly at target: met, but the whole error budget is spent -> AT_RISK, not MET.
    assert r["state"] == slo.AT_RISK, r
    assert r["measure"]["max_s"] == 2400


def test_a_backed_off_retry_is_measured_from_its_due_time_not_creation():
    db = _db()
    with db.session() as s:
        c = NOW - timedelta(hours=3)
        _job(s, created=c, run_after=c + timedelta(hours=1), started=c + timedelta(hours=1, minutes=2))
    with db.session() as s:
        r = slo.queue_latency(s, NOW)
    assert r["sli"] == 1.0, r


def test_cadence_freshness_flags_a_cadence_that_stopped_completing():
    db = _db()
    from brambleloop.runtime.worker import CADENCES

    assert CADENCES
    hourly = [c for c in CADENCES if c[3] == 3600]
    assert hourly
    with db.session() as s:
        _job(s, "ops.heartbeat", key="cadence:infra_heartbeat:0",
             created=NOW - timedelta(days=60))
        for _n, _a, jt, period in CADENCES:
            _job(s, jt, finished=NOW - timedelta(seconds=period // 2),
                 started=NOW - timedelta(seconds=period // 2))
    with db.session() as s:
        r = slo.cadence_freshness(s, NOW)
    assert r["sli"] == 1.0, r["measure"]
    stale_type = hourly[0][2]
    with db.session() as s:
        for j in s.query(Job).filter(Job.job_type == stale_type).all():
            j.finished_at = NOW - timedelta(hours=5)
    with db.session() as s:
        r = slo.cadence_freshness(s, NOW)
    assert r["sli"] < 1.0
    assert stale_type in [x["job_type"] for x in r["measure"]["stale"]]


def test_recovery_time_from_resolved_platform_incidents():
    db = _db()
    with db.session() as s:
        for i, minutes in enumerate((10, 20, 30, 200)):
            first = NOW - timedelta(hours=10 + i)
            s.add(Incident(signature=f"health:sig{i}", severity="P2", resolved=True, at=first,
                           detail={"first_seen": first.isoformat(),
                                   "resolved_at": (first + timedelta(minutes=minutes)).isoformat(),
                                   "resolution": "x"}))
        s.add(Incident(signature="release.something", severity="P2", resolved=False,
                       at=NOW - timedelta(days=2), detail={}))
    with db.session() as s:
        r = slo.recovery_time(s, NOW)
    assert abs(r["sli"] - 0.75) < 1e-9 and r["state"] == slo.BREACHED, r


# ---- departments ------------------------------------------------------------


def test_department_useful_work_counts_useful_hours_and_alerts_on_breach():
    db = _db()
    with db.session() as s:
        for h in range(24):
            t = NOW - timedelta(hours=h, minutes=30)
            _job(s, "finance.governor", created=t, started=t, finished=t,
                 outputs={"ran": True, "moved": 1})
            _job(s, "support.triage", created=t, started=t, finished=t,
                 outputs={"ran": False})
    with db.session() as s:
        hb, uw, rows = slo.departments(s, NOW)
    by = {r["department"]: r for r in rows}
    assert by["finance"]["useful_hours"] == 24 and by["finance"]["state"] == slo.MET, by["finance"]
    assert by["customer_support"]["useful_hours"] == 0
    assert by["customer_support"]["state"] == slo.BREACHED
    assert by["customer_support"]["heartbeat"] is True  # it ran; it just did nothing useful
    report = slo.check(db, now=NOW)
    sig = f"{slo.SIG_BREACH}department_useful_work:customer_support"
    assert sig in report["incidents"]["opened"], report["incidents"]
    assert _open(db, sig)[0].severity == "P3"


def test_self_observing_jobs_are_never_useful_work():
    db = _db()
    with db.session() as s:
        t = NOW - timedelta(minutes=30)
        _job(s, "ops.heartbeat", created=t, started=t, finished=t, outputs={"queue": {}})
    with db.session() as s:
        _hb, _uw, rows = slo.departments(s, NOW)
    platform = [r for r in rows if r["department"] == "platform"][0]
    assert platform["useful_hours"] == 0 and platform["completed_jobs_window"] == 0


# ---- leases -----------------------------------------------------------------


def test_lease_single_holder_expiry_and_release():
    db = _db()
    assert slo.acquire_lease(db, "scheduler", "a", ttl_s=60, now=NOW)
    assert not slo.acquire_lease(db, "scheduler", "b", ttl_s=60, now=NOW + timedelta(seconds=10))
    assert slo.acquire_lease(db, "scheduler", "a", ttl_s=60, now=NOW + timedelta(seconds=20))
    assert slo.acquire_lease(db, "scheduler", "b", ttl_s=60, now=NOW + timedelta(seconds=200))
    st = slo.lease_state(db, "scheduler", now=NOW + timedelta(seconds=201))
    assert st["holder"] == "b" and st["live"]
    assert not slo.release_lease(db, "scheduler", "a")
    assert slo.release_lease(db, "scheduler", "b")


# ---- watchdog ---------------------------------------------------------------


def test_watchdog_records_probe_heartbeat_and_runs_the_check():
    db = _db()
    out = slo.watchdog(db, url="https://example.invalid/health",
                       fetch=lambda u, t: (200, b"ok"), now=NOW)
    assert out["probe"]["ok"] is True
    out = slo.watchdog(db, url="https://example.invalid/health",
                       fetch=lambda u, t: (_ for _ in ()).throw(OSError("down")),
                       now=NOW + timedelta(minutes=5))
    assert out["probe"]["ok"] is False and "OSError" in out["probe"]["error"]
    with db.session() as s:
        from brambleloop.ops.slo import RuntimeSample

        kinds = sorted((r.kind, r.component, r.ok) for r in s.query(RuntimeSample).all())
    assert ("probe", "command_center", False) in kinds
    assert ("probe", "command_center", True) in kinds
    assert ("heartbeat", "watchdog", True) in kinds


def test_prune_removes_only_old_samples():
    db = _db()
    slo.record_heartbeat(db, "scheduler", now=NOW - timedelta(days=40))
    slo.record_heartbeat(db, "scheduler", now=NOW - timedelta(days=1))
    assert slo.prune_samples(db, now=NOW) == 1


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
