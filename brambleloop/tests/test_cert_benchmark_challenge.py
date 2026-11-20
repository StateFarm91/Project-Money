"""Certification C-40 / #168: the pre-launch benchmark challenge actually compares something.

Against 63f2493 the readiness requirement matched benchmarks on a slug family nobody files a
benchmark under ("nordic" for nordic-forest-mosaic-throw) and passed our own scores as {}.
So even with a purchased, torn-down benchmark in the right category the challenge could
never compare, and could never be passed on the merits. These tests fail on that code.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (BenchmarkProduct, PatternVersion, Product,  # noqa: E402
                                     TeardownFinding)
from brambleloop.launch import readiness  # noqa: E402
from brambleloop.teardown.pipeline import CRITICAL_DIMENSIONS  # noqa: E402

SLUG = "nordic-forest-mosaic-throw"      # concept seed category: mosaic_blanket
CATEGORY = "mosaic_blanket"


def _db(*, benchmark_category=CATEGORY, bench_score=3.0, our_score=None) -> Database:
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        p = Product(slug=SLUG, title="Nordic Forest Mosaic Throw")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True,
                             certificate={"granted": True}))
        s.add(BenchmarkProduct(ref="bench-1", seller="a seller", category=benchmark_category))
        for dim in CRITICAL_DIMENSIONS:
            s.add(TeardownFinding(benchmark_ref="bench-1", dimension=dim, score=bench_score,
                                  mechanism="observed"))
            if our_score is not None:
                s.add(TeardownFinding(benchmark_ref=f"brambleloop:{SLUG}", dimension=dim,
                                      score=our_score, mechanism="self audit"))
    return db


def _challenge(db) -> dict:
    report = readiness.assess(db, phase="shadow")
    req = next(r for r in report.requirements if r.key == "benchmark_challenge")
    return {"ready": req.ready, **req.evidence}


def test_the_category_comes_from_the_concept_seed_not_the_slug_family():
    ev = _challenge(_db(our_score=4.0))
    assert ev["category"] == CATEGORY, ev["category"]
    assert ev["per_category"][0]["comparable"] is True, ev["per_category"][0]


def test_a_product_at_least_level_on_every_critical_dimension_passes():
    ev = _challenge(_db(bench_score=3.0, our_score=4.0))
    assert ev["blocks_release"] is False and ev["ready"] is True, ev
    assert ev["per_category"][0]["verdict"] != "unavailable"


def test_materially_inferior_on_a_critical_dimension_blocks():
    ev = _challenge(_db(bench_score=4.0, our_score=1.0))
    assert ev["blocks_release"] is True and ev["ready"] is False
    assert ev["comparable"] is True


def test_our_product_never_audited_blocks_rather_than_passing_by_omission():
    ev = _challenge(_db(our_score=None))
    assert ev["blocks_release"] is True
    assert any(r["state"] == "unscored" for r in ev["rows"])


def test_a_benchmark_in_another_category_is_not_a_match():
    ev = _challenge(_db(benchmark_category="amigurumi", our_score=4.0))
    assert ev["blocks_release"] is True
    assert ev["per_category"][0]["comparable"] is False


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
