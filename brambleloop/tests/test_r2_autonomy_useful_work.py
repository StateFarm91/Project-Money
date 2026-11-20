"""R2 autonomy, audit ddf9c6e H-1: the useful-work judge is honest.

Proxy is not measurement: an all-zero / `measurable: false` output is a no-op, the judge reads
an explicit per-job-type declaration of which output keys measure work, and the self-review
and morning handoff no longer hardcode `generated: 1`. The orchestrator's mission outcome,
the department KPI, the SLO and the soak all read this one judge.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_autonomy_useful_work.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from r2_autonomy_harness import boot, run_tests

from sqlalchemy import select  # noqa: E402

# The outputs lane J recorded from real handlers on an empty database (J_repro_vacuous_outputs).
VACUOUS = {
    "support.triage": {"cases": 0, "by_specialist": {}, "escalated": 0, "row_hotspots": [],
                       "readings": {"confusion": {"measurable": False}},
                       "triage": {"triaged": [], "reply_jobs": []}},
    "physical.upgrade_impact": {"upgrades": 0, "measured": 0},
    "visual.identity_drift": {"batches": 0, "measurable": False, "gradual_drift": [],
                              "incidents_opened": []},
    "ops.sentinel": {"checked": 0, "fresh": 0, "stale": 0, "unproven": 0,
                     "publication_blocked": [], "rebuild": [], "rebuild_enqueued": []},
    "seasonal.sentinel": {"products_scheduled": 0, "at_risk": 0, "missed": 0,
                          "counts": {"on_track": 0}},
    "growth.distribution": {"reading_id": 9, "products": 0, "pins_ready": [],
                            "pins_amplified": [], "video_modules": 0},
}


def test_vacuous_outputs_are_noop_with_and_without_the_job_type():
    from brambleloop.autonomy import kpis
    from brambleloop.runtime.pipeline import did_no_work

    assert VACUOUS
    for jt, out in VACUOUS.items():
        assert did_no_work(out, jt), (jt, out)
        assert did_no_work(out), ("generic", jt, out)
        assert kpis.did_no_work(out, jt), jt
    for out in ({"cases": 0}, {"checked": 0}, {"measurable": False}, {}, {"ran": False},
                {"ran": True, "status": "UNMEASURED"}, {"reading_id": 12}):
        assert did_no_work(out), out


def test_declared_work_keys_count_and_nothing_else_does():
    from brambleloop.runtime.pipeline import WORK_KEYS, did_no_work

    assert not did_no_work({"cases": 2}, "support.triage")
    assert not did_no_work({"triage": {"triaged": [7]}}, "support.triage")
    assert did_no_work({"incidents_opened": [], "gradual_drift": [], "batches": 4},
                       "visual.identity_drift")
    assert not did_no_work({"incidents_opened": ["x"]}, "visual.identity_drift")
    # a handler may state its work directly
    assert did_no_work({"work_done": 0, "cases": 5}, "support.triage")
    assert not did_no_work({"work_done": 3})
    # pure liveness is never useful work on its own
    assert WORK_KEYS["ops.heartbeat"] == ()
    assert did_no_work({"queue": {"pending": 4}, "dead_letters": 2}, "ops.heartbeat")


def test_every_cadence_and_generatable_type_declares_its_work_keys():
    import brambleloop.autonomy.handlers  # noqa: F401 - registers the autonomy job types
    from brambleloop.autonomy import charters
    from brambleloop.runtime.pipeline import WORK_KEYS
    from brambleloop.runtime.worker import CADENCES

    types = {jt for _n, _a, jt, _p in CADENCES} | set(charters.SAFE_GENERATED)
    assert len(types) > 50, len(types)
    missing = sorted(t for t in types if t not in WORK_KEYS)
    assert not missing, missing


def test_self_review_and_handoff_count_only_new_content():
    import brambleloop.autonomy.handlers  # noqa: F401
    import brambleloop.runtime.pipeline  # noqa: F401
    from brambleloop.core.models import Job, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.pipeline import did_no_work
    from brambleloop.runtime.worker import Worker

    db = boot()
    q, w = JobQueue(db), Worker(db, "r2-h1", phase=Phase.SHADOW)
    now = datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc)
    for i in range(3):
        q.enqueue("coo", "autonomy.department_review",
                  {"department": "visual", "mission": f"m{i}", "now": now.isoformat()},
                  idempotency_key=f"r2-h1-review-{i}")
        q.enqueue("coo", "autonomy.morning_handoff", {"now": now.isoformat()},
                  idempotency_key=f"r2-h1-brief-{i}")
        while w.run_once():
            pass
    with db.session() as s:
        reviews = [j.outputs for j in s.scalars(select(Job).where(
            Job.job_type == "autonomy.department_review").order_by(Job.id))]
        briefs = [j.outputs for j in s.scalars(select(Job).where(
            Job.job_type == "autonomy.morning_handoff").order_by(Job.id))]
    assert len(reviews) == 3 and len(briefs) == 3, (reviews, briefs)
    for out in reviews + briefs:
        assert "generated" not in out, out
    useful_reviews = [o for o in reviews if not did_no_work(o, "autonomy.department_review")]
    assert len(useful_reviews) == 1, reviews
    # the briefs: the first is new; later identical ones are not
    assert not did_no_work(briefs[0], "autonomy.morning_handoff"), briefs[0]
    assert did_no_work(briefs[-1], "autonomy.morning_handoff"), briefs[-1]


def test_orchestrator_records_noop_missions_and_suppression_can_fire():
    import brambleloop.autonomy.handlers  # noqa: F401
    import brambleloop.runtime.pipeline  # noqa: F401
    from brambleloop.autonomy import memory, orchestrator
    from brambleloop.core.models import Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = boot()
    q, w = JobQueue(db), Worker(db, "r2-h1-orch", phase=Phase.SHADOW)
    base = datetime.now(timezone.utc)
    for n in range(4):
        orchestrator.tick(db, q, now=base + timedelta(hours=7 * n))
        while w.run_once():
            pass
    orchestrator.reconcile_missions(db, now=base + timedelta(hours=30))
    missions = memory.recall(db, kind="mission", limit=500)
    assert missions, "no missions generated"
    states = [m["state"] for m in missions]
    assert "noop" in states, states       # on ddf9c6e every mission read "useful"
    assert "useful" in states, states     # but genuinely new findings still count


def test_slo_departments_use_the_same_judge():
    from brambleloop.core.models import Job, JobStatus, utcnow
    from brambleloop.ops import slo

    db = boot()
    now = utcnow()
    with db.session() as s:
        for jt, out in VACUOUS.items():
            s.add(Job(agent="x", job_type=jt, inputs={}, outputs=out, status=JobStatus.DONE,
                      created_at=now - timedelta(hours=3), started_at=now - timedelta(hours=1),
                      finished_at=now - timedelta(minutes=30), attempts=1))
    with db.session() as s:
        _hb, _useful, rows = slo.departments(s, now)
    assert rows, rows
    assert all(r["useful_hours"] == 0 for r in rows), [(r["department"], r["useful_hours"])
                                                      for r in rows]


if __name__ == "__main__":
    run_tests(globals())
