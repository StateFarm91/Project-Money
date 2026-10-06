"""#38 in the scorer (C-69): opportunity scores discount stale or mismatched evidence.

The stamps existed (`trend_provenance.weight` / `usable_value`) and no scorer read them. Here
`radar.score` runs through the worker over stamped evidence and the discounted score is what
decides promotion; the API search-index captures are stamped too.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, InsightsSnapshot, Job, JobStatus, SerpSnapshot, TrendProvenance,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import provenance  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

SLUG = "chunky-ribbed-scarf"          # raw score 0.5987 on 2026-09-17, threshold 0.55
TODAY = date(2026, 9, 17)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/trend.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _insight(db, keyword, geography, observed):
    with db.session() as s:
        s.add(InsightsSnapshot(keyword=keyword, search_count=900, geography=geography,
                               observed_on=datetime.combine(observed, datetime.min.time(),
                                                            tzinfo=timezone.utc)))


def _score(db, key):
    job = JobQueue(db).enqueue("market_radar", "radar.score",
                               {"slug": SLUG, "as_of": TODAY.isoformat()},
                               idempotency_key=key, priority=0)
    Worker(db, key, job_types=["radar.score"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        return dict(row.outputs)


def test_stale_foreign_evidence_discounts_the_score_below_promotion():
    db = _db()
    _insight(db, "chunky scarf", "united states", date(2025, 6, 1))
    provenance.stamp_all(db, today=TODAY)
    out = _score(db, "stale")
    assert out["raw_score"] > pipeline.PROMOTION_THRESHOLD
    assert out["evidence"]["measured"] and out["evidence"]["discount"] < 1.0
    assert out["score"] < pipeline.PROMOTION_THRESHOLD and out["promoted"] is False
    assert "evidence discount" in out["reason"]
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "radar.evidence_discount"))
        assert row.detail["not_presentable"], "stale US data was presentable as current CA"


def test_current_canadian_evidence_keeps_full_weight():
    db = _db()
    _insight(db, "chunky scarf", "canada", date(2026, 9, 10))
    provenance.stamp_all(db, today=TODAY)
    out = _score(db, "fresh")
    assert out["evidence"]["discount"] == 1.0 and out["score"] == out["raw_score"]


def test_no_evidence_is_unmeasured_and_leaves_the_score_alone():
    out = _score(_db(), "none")
    assert out["evidence"]["measured"] is False and out["score"] == out["raw_score"]


def test_serp_captures_are_stamped_with_their_population_and_window():
    db = _db()
    with db.session() as s:
        s.add(SerpSnapshot(query="chunky scarf pattern", total_count=1200,
                           captured_at=datetime(2026, 9, 16, tzinfo=timezone.utc)))
    provenance.stamp_all(db, today=TODAY)
    with db.session() as s:
        stamp = s.scalar(select(TrendProvenance).where(
            TrendProvenance.source_table == "serp_snapshots"))
    assert stamp is not None and stamp.population == "GLOBAL"
    assert stamp.weight is not None and stamp.weight < 1.0 and stamp.window_to == "2026-09-16"


def test_mjs_benchmark_listings_are_stamped_global_over_their_seen_window_and_discount_scores():
    """C-80 defect 14 (#38): the MJs listing observations are trend evidence, stamped GLOBAL
    with the span they were seen over, and the scorer reads them like every other stamp."""
    from brambleloop.core.models import BenchmarkListing

    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="mjs-1", listing_ref="L1",
                               title="Chunky ribbed scarf crochet pattern", pod="wearables",
                               price_cad=9.5,
                               first_seen=datetime(2025, 5, 1, tzinfo=timezone.utc),
                               last_seen=datetime(2025, 6, 1, tzinfo=timezone.utc)))
    out = provenance.stamp_all(db, today=TODAY)
    assert out["by_population"]["GLOBAL"] >= 1
    with db.session() as s:
        stamp = s.scalar(select(TrendProvenance).where(
            TrendProvenance.source_table == "benchmark_listings"))
    assert stamp is not None and stamp.population == "GLOBAL" and stamp.source == "mjs:mjs-1"
    assert stamp.window_from == "2025-05-01" and stamp.window_to == "2025-06-01"
    assert stamp.weight is not None and stamp.weight < 0.7, "a year-old global datum at full weight"
    scored = _score(db, "mjs")
    assert scored["evidence"]["measured"] and scored["evidence"]["discount"] < 1.0
    assert scored["evidence"]["rows"] >= 1


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
