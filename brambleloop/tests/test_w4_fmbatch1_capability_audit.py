"""F-624: a quarterly capability audit runs from the daily handoff, once per quarter, and
writes decision records comparing this quarter with the last."""
from __future__ import annotations

from datetime import datetime, timezone

from r2_autonomy_harness import boot, run_tests


def test_decisions_name_gaps_and_compare_with_last_quarter():
    from brambleloop.autonomy import capability_audit as A

    now = {"etsy": {"required_before_first_sale": ["a", "b"], "without_collector": ["b"],
                    "problems": []},
           "closure": {"open_defects": 5, "percent_complete": 80.0}}
    prev = {"closure": {"open_defects": 3, "percent_complete": 80.0}}
    made = A.decisions(now, prev)
    gaps = {d["gap"]: d for d in made}
    assert gaps["first-sale surfaces with no collector"]["evidence"] == ["b"]
    assert "grew" in gaps["Build 2 executable rows open"]["decision"]
    assert "no closure progress quarter on quarter" in gaps
    first = A.decisions(now, None)
    assert {d["gap"] for d in first} == {"first-sale surfaces with no collector",
                                         "Build 2 executable rows open"}
    assert first[1]["evidence"]["previous"] == "NO_PRIOR_AUDIT"
    unknown = A.decisions({"etsy": {"state": "UNKNOWN", "why": "x"}, "closure": {}}, None)
    assert unknown[0]["gap"] == "etsy_surfaces unreadable"


def test_runs_once_per_quarter_and_reads_the_previous_one():
    from brambleloop.autonomy import capability_audit as A, memory

    db = boot()
    q3 = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    q4 = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    r = A.run(db, now=q3)
    assert r["ran"] and r["quarter"] == "2026Q3"
    assert A.run(db, now=q3)["ran"] is False
    body = memory.get(db, "capability_audit:2026Q3")["body"]
    assert "etsy" in body["readings"] and "closure" in body["readings"]
    assert body["readings"]["etsy"].get("state") != "UNKNOWN", body["readings"]["etsy"]
    r4 = A.run(db, now=q4)
    assert r4["ran"] and memory.get(db, "capability_audit:2026Q4")["body"][
        "previous_quarter"] == "2026Q3"


def test_the_morning_handoff_runs_the_audit():
    import brambleloop.autonomy.handlers  # noqa: F401
    import brambleloop.runtime.pipeline  # noqa: F401
    from sqlalchemy import select

    from brambleloop.core.models import Job, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = boot()
    now = datetime(2027, 1, 5, 9, tzinfo=timezone.utc)
    q, w = JobQueue(db), Worker(db, "fmb1-capaudit", phase=Phase.SHADOW)
    q.enqueue("coo", "autonomy.morning_handoff", {"now": now.isoformat()},
              idempotency_key="fmb1-capaudit")
    while w.run_once():
        pass
    with db.session() as s:
        out = s.scalar(select(Job).where(Job.job_type == "autonomy.morning_handoff")).outputs
    assert out["capability_audit"]["quarter"] == "2027Q1", out


if __name__ == "__main__":
    run_tests(globals())
