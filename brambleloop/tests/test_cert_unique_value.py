"""#163 and #169 in the running chain, not as a tautology (C-69).

`advantages_from_certificate` returns `deterministic_validation` for every granted certificate,
so on its own #163 could never block anything. The comparison now runs against the purchased
benchmarks' composite: an advantage a benchmark already provides at the top of the scale is
parity. These tests certify real designs through the worker with benchmark findings seeded and
assert what the chain then does -- withholds, marks the release, and refuses to draft its
listing on the hourly rebuild -- and that the delight mechanisms are measured and acted on.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkProduct, Improvement, Job, JobStatus, PatternVersion, Phase,
    TeardownFinding,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.teardown import lab  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/uv.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _certify(db, slug):
    from brambleloop.runtime.pipeline import _engineered_cir

    cir = _engineered_cir(slug)
    job = JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                               idempotency_key=f"c:{slug}", priority=0)
    Worker(db, "uv", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        return cir, dict(row.outputs)


def _benchmark(db, scores: dict[str, float], category="mosaic_blanket"):
    with db.session() as s:
        s.add(BenchmarkProduct(ref="bench-1", seller="fixture", category=category))
        for dim, score in scores.items():
            s.add(TeardownFinding(benchmark_ref="bench-1", dimension=dim, score=score,
                                  mechanism="fixture", improvement="fixture"))


def test_a_release_whose_advantages_every_benchmark_matches_is_withheld_and_not_redriven():
    db = _db()
    _benchmark(db, {"pattern_correctness_evidence": 5, "listing_promise_alignment": 5,
                    "materials_clarity": 5, "support_experience": 5, "chart_quality": 5})
    cir, out = _certify(db, "nordic-forest-mosaic-throw")
    assert out["granted"] and out.get("withheld") is True, out
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        assert "teardown QA (#163)" in pv.certificate["withheld"]
        assert not list(s.scalars(select(Job).where(Job.job_type == "listing.draft")))
    # the hourly rebuild would otherwise draft the listing the withhold refused
    job = JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="hourly",
                               priority=0)
    Worker(db, "uv-rebuild", job_types=["chain.rebuild"]).run_once()
    with db.session() as s:
        done = s.get(Job, job.id)
        assert done.status == JobStatus.DONE, done.last_error
        assert done.outputs["withheld"] and not done.outputs["restarted"]
        assert not list(s.scalars(select(Job).where(Job.job_type == "listing.draft")))


def test_an_advantage_beyond_the_best_benchmark_lets_the_release_proceed():
    db = _db()
    _benchmark(db, {"pattern_correctness_evidence": 3})
    cir, out = _certify(db, "nordic-forest-mosaic-throw")
    assert not out.get("withheld"), out
    with db.session() as s:
        qa = [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == lab.ACTION_QA))][-1]
        assert list(s.scalars(select(Job).where(Job.job_type == "listing.draft")))
    comparison = qa["unique_value"]["comparison"]
    assert comparison["verdicts"]["deterministic_validation"]["state"] == "beyond"
    assert qa["unique_value"]["status"] == "beyond"


def test_with_no_benchmark_scored_the_comparison_is_unmeasured_not_a_pass():
    db = _db()
    cir, out = _certify(db, "nordic-forest-mosaic-throw")
    with db.session() as s:
        qa = [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == lab.ACTION_QA))][-1]
    assert qa["unique_value"]["status"] == "UNMEASURED" and not qa["blocks_release"]
    assert all(v["state"] == "unmeasured"
               for v in qa["unique_value"]["comparison"]["verdicts"].values())


def test_delight_is_measured_from_the_products_artefacts_and_the_weakest_is_acted_on():
    db = _db()
    cir, out = _certify(db, "nordic-forest-mosaic-throw")
    qa = lab.product_qa(db, cir.slug)
    delight = qa["delight"]
    assert delight["answerable"] is True
    assert {"customization", "confidence"} <= set(delight["drivers"])
    assert delight["weakest"] in ("customization", "confidence")
    act = qa["delight_action"]
    assert act and (act.get("improvement") or act.get("refused") or act.get("already_open")), act
    if act.get("improvement"):
        with db.session() as s:
            imp = s.get(Improvement, act["improvement"])
            assert imp.baseline_ref.startswith(f"delight:{cir.slug}:")
        again = lab.product_qa(db, cir.slug)["delight_action"]
        assert again.get("already_open"), "the same weakness opens one hypothesis, not two"


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
