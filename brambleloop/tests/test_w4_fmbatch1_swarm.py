"""W4-FMBATCH1 batch I: the gaps CLOSE5 named on F-394, F-470 and F-489.

- F-394 "Prioritize autonomous improvement by expected customer/business impact, risk
  reduction, confidence, cost and reversibility." (CLOSE5: risk reduction and confidence absent)
- F-470 Resource-Aware Concurrency (CLOSE5: storage and platform capacity not measured).
- F-489 "Measure wall-clock compression, idle-capacity time, duplicate-work avoidance, conflict
  rate, merge delay and useful throughput attributable to parallel execution." (CLOSE5:
  wall-clock compression and conflict rate not measured)
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="fmb1_swarm_")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus  # noqa: E402
from brambleloop.improve import roi  # noqa: E402
from brambleloop.swarm import metrics, resources  # noqa: E402

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


def _refused(fn):
    try:
        fn()
    except roi.RoiRefused as exc:
        return str(exc)
    raise AssertionError("expected a refusal")


# ---- F-394 -------------------------------------------------------------------------------

def test_f394_confidence_discounts_and_risk_reduction_adds():
    ranked = roi.prioritise([
        {"key": "loud_guess", "expected_impact": 0.5, "confidence": 0.2, "cost_cad": 0.0},
        {"key": "sure_thing", "expected_impact": 0.3, "confidence": 0.9, "cost_cad": 0.0},
        {"key": "risk_fix", "expected_impact": 0.05, "risk_reduction": 0.4, "confidence": 1.0,
         "cost_cad": 0.0},
    ])["ranked"]
    assert [r["key"] for r in ranked] == ["risk_fix", "sure_thing", "loud_guess"], ranked
    assert ranked[2]["expected_value"] == 0.1


def test_f394_an_unstated_confidence_never_outranks_a_stated_one_of_equal_value():
    ranked = roi.prioritise([
        {"key": "unstated", "expected_impact": 0.3, "cost_cad": 0.0},
        {"key": "stated", "expected_impact": 0.3, "confidence": 1.0, "cost_cad": 0.0},
    ])["ranked"]
    assert [r["key"] for r in ranked] == ["stated", "unstated"]
    assert ranked[1]["confidence_unstated"] is True
    assert "probability" in _refused(lambda: roi.prioritise(
        [{"key": "x", "expected_impact": 1, "confidence": 3}]))
    assert "non-negative" in _refused(lambda: roi.prioritise(
        [{"key": "x", "expected_impact": 1, "risk_reduction": -1}]))


# ---- F-470 -------------------------------------------------------------------------------

def _host(*, psi_io=None):
    root = Path(tempfile.mkdtemp(prefix="fmb1_host_", dir=_TMP))
    proc, cg = root / "proc", root / "cg"
    (proc / "self").mkdir(parents=True)
    cg.mkdir()
    (proc / "self" / "status").write_text("VmRSS:\t102400 kB\n")
    (cg / "memory.max").write_text(str(1024 ** 3))
    (cg / "cpu.pressure").write_text("some avg10=1 avg60=2.0 avg300=1 total=1\n")
    if psi_io is not None:
        (cg / "io.pressure").write_text(f"some avg10=1 avg60={psi_io} avg300=1 total=1\n")
    return proc, cg


def test_f470_storage_and_io_pressure_saturate_and_absent_paths_are_unknown():
    proc, cg = _host(psi_io=75.0)
    r = resources.read(None, proc=proc, cgroup=cg, load=lambda: (0.1, 0, 0),
                       storage_paths={"tmp": _TMP})
    assert r["saturated"] is True and "I/O pressure" in r["why"], r
    proc, cg = _host(psi_io=1.0)
    real = resources.read(None, proc=proc, cgroup=cg, load=lambda: (0.1, 0, 0),
                          storage_paths={"tmp": _TMP, "gone": "/no/such/path"})
    assert real["storage"]["gone"]["free_share"] is None
    assert "does not exist" in real["storage"]["gone"]["why"]
    assert real["storage"]["tmp"]["free_share"] is not None
    assert "cgroup" in real["platform_capacity_source"]
    # A nearly full working filesystem saturates the pool.
    orig = resources.storage
    resources.storage = lambda _p=None: {"tmp": {"free_gb": 0.5, "total_gb": 100.0,
                                                  "free_share": 0.005}}
    try:
        full = resources.read(None, proc=proc, cgroup=cg, load=lambda: (0.1, 0, 0))
    finally:
        resources.storage = orig
    assert full["saturated"] is True and "storage tmp" in full["why"], full


# ---- F-489 -------------------------------------------------------------------------------

def _db():
    db = Database(f"sqlite:///{_TMP}/w{datetime.now().timestamp()}.sqlite")
    db.create_all()
    return db


def test_f489_compression_parallel_throughput_and_conflict_rate_from_rows():
    db = _db()
    empty = metrics.parallel_window(db, now=NOW)
    assert empty["wall_clock_compression"] is None and "nothing to measure" in empty["why"]
    t0 = NOW - timedelta(hours=2)
    with db.session() as s:
        # Two jobs fully overlapping for an hour, one alone for an hour after.
        for k in range(2):
            s.add(Job(agent="a", job_type="x", inputs={}, status=JobStatus.DONE, attempts=1,
                      started_at=t0, finished_at=t0 + timedelta(hours=1)))
        s.add(Job(agent="a", job_type="y", inputs={}, status=JobStatus.DONE, attempts=2,
                  started_at=t0 + timedelta(hours=1), finished_at=t0 + timedelta(hours=2),
                  last_error="lease lost to another worker; reclaimed"))
    w = metrics.parallel_window(db, now=NOW)
    assert w["work_seconds"] == 3 * 3600 and w["busy_wall_seconds"] == 2 * 3600
    assert w["wall_clock_compression"] == 1.5
    assert w["useful_parallel_seconds"] == 2 * 3600          # 1 h with two running
    assert w["conflicts"] == 1 and w["attempts"] == 4 and w["conflict_rate"] == 0.25


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
