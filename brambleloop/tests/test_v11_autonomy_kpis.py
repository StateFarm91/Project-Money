"""v1.1 lane A: department KPIs with anti-gaming guardrails (F-918).

Optimising a metric must not be able to override Product Truth, customer safety, financial
truth or authority, and a KPI must not be farmable by no-op or duplicate work.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import kpis, memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Job, JobStatus, Lesson, PatternVersion,  # noqa: E402
                                     Product, SupportCase, utcnow)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="v11a-kpi-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def finished(db, job_type, outputs, *, status=JobStatus.DONE, inputs=None, error=None):
    with db.session() as s:
        s.add(Job(agent="cfo", job_type=job_type, inputs=inputs or {}, outputs=outputs,
                  status=status, last_error=error, finished_at=utcnow(), attempts=1))


def test_an_empty_database_reads_unknown_never_zero():
    db = boot()
    r = kpis.compute(db, "finance")
    k = r["kpis"]["useful_completions_24h"]
    assert k["status"] == "UNKNOWN" and k["value"] is None, k
    assert r["kpis"]["cadence_freshness"]["value"] in (None, 0.0)
    assert r["kpis"]["cadence_freshness"]["status"] in ("OK", "UNKNOWN")


def test_duplicate_and_noop_outputs_cannot_farm_the_useful_count():
    db = boot()
    finished(db, "finance.reconcile", {"pl": {"net": 1}})
    base = kpis.compute(db, "finance")["kpis"]["useful_completions_24h"]["value"]
    assert base == 1, base
    for _ in range(50):     # the same answer fifty times
        finished(db, "finance.reconcile", {"pl": {"net": 1}, "at": utcnow().isoformat()})
    for _ in range(50):     # fifty runs that did nothing
        finished(db, "commerce.readings", {"ran": False})
    for _ in range(20):     # generated work that did nothing
        finished(db, "commerce.order_readings", {"ran": True, "new": 0},
                 inputs={"source": "autonomy", "department": "finance"})
    r = kpis.compute(db, "finance")
    assert r["kpis"]["useful_completions_24h"]["value"] == 1, r["counted"]
    assert r["counted"]["noop"] == 70 and r["counted"]["generated_noop"] == 20, r["counted"]
    finished(db, "finance.reconcile", {"pl": {"net": 2}})     # genuinely new output
    assert kpis.compute(db, "finance")["kpis"]["useful_completions_24h"]["value"] == 2


def test_a_refused_job_voids_every_kpi_of_its_department():
    db = boot()
    finished(db, "finance.reconcile", {"pl": {"net": 1}})
    finished(db, "finance.governor", None, status=JobStatus.DEAD,
             error="budget exceeded: agent 'cfo' would exceed its daily ceiling")
    r = kpis.compute(db, "finance")
    assert r["guardrails"]["tripped"], r["guardrails"]
    for name, k in r["kpis"].items():
        assert k["status"] == "VOID" and k["value"] is None, (name, k)
    # Another department is unaffected.
    other = kpis.compute(db, "growth")
    assert not other["guardrails"]["tripped"]


def test_customer_truth_breach_voids_support_in_shadow():
    db = boot()
    finished(db, "support.triage", {"cases": 1}, inputs={})
    with db.session() as s:
        s.add(SupportCase(customer_ref="c", question="q", sent=True))
    r = kpis.compute(db, "support")
    assert r["guardrails"]["tripped"], r
    assert any("sent while the phase is shadow" in b for b in r["guardrails"]["breaches"])
    assert r["kpis"]["useful_completions_24h"]["status"] == "VOID"


def test_product_truth_breach_voids_product_truth():
    db = boot()
    with db.session() as s:
        p = Product(slug="x", title="x")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={}, certified=True,
                             certificate=None))
    r = kpis.compute(db, "product_truth")
    assert r["guardrails"]["tripped"] and r["kpis"]["cadence_freshness"]["status"] == "VOID"


def test_department_review_persists_snapshot_and_routes_a_lesson_once():
    db = boot()
    finished(db, "finance.governor", None, status=JobStatus.DEAD,
             error="permission denied: nope")
    q = JobQueue(db)
    q.enqueue("coo", "autonomy.department_review", {"department": "finance",
                                                     "mission": "m-1"},
              idempotency_key="rv-1")
    w = Worker(db, "w")
    assert w.run_once() and w.stats.completed == 1, w.stats
    snap = memory.get(db, "kpi:finance:m-1")
    assert snap and snap["kind"] == "kpi_snapshot", snap
    assert snap["body"]["guardrails"]["tripped"]
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(Lesson).where(
            Lesson.origin_cell == "finance"))
    assert n == 1, n
    # A second review of the same evidence routes no second lesson.
    q.enqueue("coo", "autonomy.department_review", {"department": "finance",
                                                     "mission": "m-1"},
              idempotency_key="rv-2")
    assert w.run_once()
    with db.session() as s:
        n2 = s.scalar(select(func.count()).select_from(Lesson).where(
            Lesson.origin_cell == "finance"))
    assert n2 == 1, n2


def test_fingerprint_ignores_volatile_keys_only():
    a = kpis.fingerprint({"x": 1, "at": "2026-01-01", "nested": {"now": 5, "y": 2}})
    b = kpis.fingerprint({"x": 1, "at": "2027-01-01", "nested": {"now": 9, "y": 2}})
    c = kpis.fingerprint({"x": 2, "at": "2026-01-01", "nested": {"now": 5, "y": 2}})
    assert a == b and a != c
    assert datetime.now(timezone.utc)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
