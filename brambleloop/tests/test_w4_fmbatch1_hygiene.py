"""W4-FMBATCH1 batch O: signal hygiene on the health sweep.

- F-139 "Homogeneous large backlogs create one actionable incident with count/scope while
  retaining item evidence."
- F-140 "A permanently noisy/false health signal is itself a defect."
- F-149 "Monitor scratch/cache growth, disk utilization and abnormal file-count growth before
  ENOSPC."
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="fmb1_hyg_")

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus  # noqa: E402
from brambleloop.ops import signal_hygiene as H  # noqa: E402

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _dead(db, job_type, n, error="TimeoutError: The read operation timed out"):
    with db.session() as s:
        for _ in range(n):
            s.add(Job(agent="a", job_type=job_type, inputs={}, status=JobStatus.DEAD,
                      last_error=error, created_at=NOW - timedelta(hours=1)))


def _open(db, prefix):
    with db.session() as s:
        return [r for r in s.scalars(select(Incident).where(Incident.resolved == False))  # noqa: E712
                if r.signature.startswith(prefix)]


def test_f139_one_incident_per_homogeneous_backlog_with_every_id():
    db = _db()
    _dead(db, "intel.gallery_analysis", 5)
    _dead(db, "radar.score", 2, error="KeyError: 'slug'")         # below the threshold
    _dead(db, "store.publish", 6, error="PublishRefused: shadow mode refuses publication")
    with db.session() as s:
        out = H.aggregate_dead_letters(s, now=NOW)
    assert out["aggregated"] == {"intel.gallery_analysis": 5}, out
    assert out["below_threshold"] == {"radar.score": 2}
    rows = _open(db, "dead-letters:")
    assert len(rows) == 1 and rows[0].signature == "dead-letters:intel.gallery_analysis"
    d = rows[0].detail
    assert d["count"] == 5 and len(d["job_ids"]) == 5 and d["job_ids_truncated"] == 0
    assert d["errors"] == {"TimeoutError: The read operation timed out": 5}
    # A second sweep restates, never duplicates; the backlog cleared resolves it.
    with db.session() as s:
        assert H.aggregate_dead_letters(s, now=NOW)["opened"] == []
        for j in s.scalars(select(Job).where(Job.status == JobStatus.DEAD,
                                             Job.job_type == "intel.gallery_analysis")):
            j.status = JobStatus.DONE
    with db.session() as s:
        assert H.aggregate_dead_letters(s, now=NOW)["resolved"] == [
            "dead-letters:intel.gallery_analysis"]
    assert _open(db, "dead-letters:") == []


def test_f140_a_flapping_signal_is_raised_as_a_defect_and_a_steady_one_is_not():
    db = _db()
    with db.session() as s:
        for k in range(4):
            s.add(Incident(signature="health:queue_age", severity="P1", resolved=True,
                           at=NOW - timedelta(days=k + 1), detail={}))
        s.add(Incident(signature="health:disk", severity="P1", resolved=True,
                       at=NOW - timedelta(days=2), detail={}))
    with db.session() as s:
        out = H.noisy_signals(s, now=NOW)
    assert out["flapping"] == {"health:queue_age": 4} and out["opened"] == ["health:queue_age"]
    assert [r.signature for r in _open(db, "noisy-signal:")] == ["noisy-signal:health:queue_age"]
    # Nine days later the flapping is outside the window: the defect resolves.
    with db.session() as s:
        assert H.noisy_signals(s, now=NOW + timedelta(days=9))["resolved"] == [
            "noisy-signal:health:queue_age"]


def test_f140_a_signal_open_and_unconfirmed_for_weeks_is_a_defect():
    db = _db()
    old = NOW - timedelta(days=20)
    with db.session() as s:
        s.add(Incident(signature="health:integrations", severity="P1", at=old,
                       detail={"last_seen": old.isoformat()}))
        s.add(Incident(signature="health:spend", severity="P1", at=old,
                       detail={"last_seen": (NOW - timedelta(hours=1)).isoformat()}))
    with db.session() as s:
        out = H.noisy_signals(s, now=NOW)
    assert list(out["stuck_unconfirmed"]) == ["health:integrations"], out


def _samples(temp, free, hours):
    return [(NOW - timedelta(hours=h), {"temp_dirs_left_behind": t, "free_gb": {"tmp": f}})
            for h, t, f in zip(hours, temp, free)]


def test_f149_growth_and_projected_enospc_alarm_and_a_flat_disk_does_not():
    flat = H.disk_trend(_samples([3, 3, 3, 3], [10.0, 10.0, 10.0, 10.0], [20, 14, 7, 0]),
                        now=NOW)
    assert flat["state"] == "OK" and flat["alarms"] == []
    growing = H.disk_trend(_samples([0, 20, 40, 60], [10.0, 10.0, 10.0, 10.0],
                                    [20, 14, 7, 0]), now=NOW)
    assert [a["what"] for a in growing["alarms"]] == ["temp_dirs"], growing
    filling = H.disk_trend(_samples([3, 3, 3, 3], [10.0, 8.0, 6.0, 4.0], [20, 14, 7, 0]),
                           now=NOW)
    a = filling["alarms"][0]
    assert a["what"] == "free:tmp" and a["hours_to_full"] <= H.ENOSPC_HORIZON_HOURS
    few = H.disk_trend(_samples([1, 2], [5.0, 4.0], [3, 0]), now=NOW)
    assert few["state"] == "UNKNOWN"                     # too few samples is never "fine"


def test_f149_the_sweep_stores_samples_and_raises_and_resolves_the_trend_incident():
    from brambleloop.core.models import AuditLog

    db = _db()
    with db.session() as s:
        for h, free in ((18, 10.0), (12, 8.0), (6, 6.0)):
            s.add(AuditLog(actor="orchestrator", action=H.SAMPLE_ACTION,
                           at=NOW - timedelta(hours=h),
                           detail={"temp_dirs_left_behind": 2, "free_gb": {"tmp": free}}))
    facts = {"temp_dirs_left_behind": 2, "filesystems": {"tmp": {"free_gb": 4.0}}}
    with db.session() as s:
        out = H.sweep(db, s, facts=facts, now=NOW)
    assert out["disk_trend"]["state"] == "ALARM" and out["disk_trend"]["sampled"] is True
    assert [r.signature for r in _open(db, "disk-trend:")] == ["disk-trend:free:tmp"]
    assert out["dead_letter_aggregation"]["aggregated"] == {}
    steady = {"temp_dirs_left_behind": 2, "filesystems": {"tmp": {"free_gb": 4.0}}}
    with db.session() as s:
        for h in (5, 4, 3):
            s.add(AuditLog(actor="orchestrator", action=H.SAMPLE_ACTION,
                           at=NOW + timedelta(hours=24 - h),
                           detail={"temp_dirs_left_behind": 2, "free_gb": {"tmp": 4.0}}))
    with db.session() as s:
        later = H.sweep(db, s, facts=steady, now=NOW + timedelta(hours=24))
    assert later["disk_trend"]["state"] == "OK", later
    assert _open(db, "disk-trend:") == []


def test_the_health_sweep_runs_the_hygiene_checks():
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    db = _db()
    Registry(db).seed_defaults()
    _dead(db, "intel.gallery_analysis", 3)
    JobQueue(db).enqueue("orchestrator", "ops.health", {}, idempotency_key="fmb1-health")
    Worker(db, job_types=["ops.health"]).run_once()
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.idempotency_key == "fmb1-health"))
        out = dict(job.outputs or {})
    assert out["hygiene"]["dead_letter_aggregation"]["aggregated"] == {
        "intel.gallery_analysis": 3}, out.get("hygiene")
    assert [r.signature for r in _open(db, "dead-letters:")] == [
        "dead-letters:intel.gallery_analysis"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
