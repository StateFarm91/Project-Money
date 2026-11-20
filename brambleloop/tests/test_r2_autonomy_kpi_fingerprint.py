"""R2 autonomy, audit ddf9c6e M-1: identical-content reviews fingerprint identically.

The self-review put a per-mission `snapshot` key in its outputs and VOLATILE did not strip it,
so ten reviews of an idle department counted as ten distinct useful completions.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_autonomy_kpi_fingerprint.py
"""
from __future__ import annotations

from datetime import datetime, timezone

from r2_autonomy_harness import boot, run_tests

from sqlalchemy import select


def test_snapshot_ids_timestamps_and_run_ids_do_not_change_the_fingerprint():
    from brambleloop.autonomy import kpis

    a = {"ran": True, "department": "visual", "snapshot": "kpi:visual:autonomy:visual:1",
         "run_id": "r-1", "request_id": "q-1", "summary": "read at 2026-10-06T07:00:00+00:00",
         "kpis": {"useful": "OK"}}
    b = {"ran": True, "department": "visual", "snapshot": "kpi:visual:autonomy:visual:2",
         "run_id": "r-2", "request_id": "q-2", "summary": "read at 2026-10-07T09:13:44.5Z",
         "kpis": {"useful": "OK"}}
    c = dict(b, kpis={"useful": "VOID"})
    assert kpis.fingerprint(a) == kpis.fingerprint(b)
    assert kpis.fingerprint(a) != kpis.fingerprint(c)


def test_ten_identical_reviews_count_as_one_useful():
    import brambleloop.autonomy.handlers  # noqa: F401
    import brambleloop.runtime.pipeline  # noqa: F401
    from brambleloop.autonomy import kpis
    from brambleloop.core.models import Job, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    db = boot()
    q, w = JobQueue(db), Worker(db, "r2-m1", phase=Phase.SHADOW)
    now = datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc)
    for i in range(10):
        q.enqueue("coo", "autonomy.department_review",
                  {"department": "visual", "mission": f"m{i}", "now": now.isoformat()},
                  idempotency_key=f"r2-m1-{i}")
        while w.run_once():
            pass
    with db.session() as s:
        rows = [(j.job_type, j.outputs) for j in s.scalars(
            select(Job).where(Job.job_type == "autonomy.department_review"))]
    assert len(rows) == 10, len(rows)
    useful = {kpis.fingerprint(o) for jt, o in rows if not kpis.did_no_work(o, jt)}
    assert len(useful) == 1, useful
    # ...and the department cannot review itself into a score.
    r = kpis.compute(db, "visual", now=datetime.now(timezone.utc))
    v = r["kpis"]["useful_completions_24h"]["value"]
    assert v in (None, 0), r["kpis"]["useful_completions_24h"]


if __name__ == "__main__":
    run_tests(globals())
