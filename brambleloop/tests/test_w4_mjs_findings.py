"""W4-MJS: stored MJs evidence becomes findings that product work actually reads.

Drives the runtime, not the library: the Scheduler enqueues the `mjs_scan` cadence, a Worker
runs `mjs.scan` (the Etsy credential removed, so the handler's own read is blocked and the
mission runs on what earlier scans stored), and the test asserts that the day's
`mjs.findings` reading is persisted with provenance and confidence, that the actionable
findings reach the lesson bus, and that the consumers read them: `radar.score` acts on the
seasonal lesson through `improve.consume.matching`, and a creative brief draws on them
through `creative.ideation.lessons`. A second cadence window over a changed catalogue
produces new intel with no prompt, superseding the old lesson rather than duplicating it.

No test fetches anything. Every listing below is a fixture, not a real listing.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    BenchmarkObservation, Job, JobStatus, Lesson, OperatingReading,
)
from brambleloop.intel import benchmarks, findings, market_map, observe  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Scheduler, Worker  # noqa: E402

AS_OF = date(2026, 10, 7)
DESC = ("Crochet PATTERN, PDF instant download, 9 pages. Written instructions, US terms. "
        "Worsted weight yarn, about 300 yards, 5 mm hook.")


class FixtureReader:
    def __init__(self, listings):
        self.listings = listings

    def resolve_shop(self, name):
        return {"shop_id": 4242, "shop_name": name}

    def catalogue(self, shop_id, **kwargs):
        return list(self.listings)

    def images(self, ref):
        sat = 6 if int(ref) % 2 else 40
        return [{"rank": i + 1, "hex_code": "C4C0B7", "hue": 40, "saturation": sat,
                 "brightness": 76, "is_black_and_white": False,
                 "url_fullxfull": f"https://fixture.invalid/{ref}/{i}.jpg"} for i in range(10)]

    def videos(self, ref):
        return [{"video_id": 1}] if int(ref) % 3 == 0 else []


def _l(lid, title, fav, cents=1800):
    return {"listing_id": lid, "title": title,
            "price": {"amount": cents, "divisor": 100, "currency_code": "CAD"},
            "tags": ["crochet pattern"], "materials": ["yarn"], "state": "active",
            "last_modified_timestamp": 1000, "num_favorers": fav, "taxonomy_id": 66,
            "is_digital": True, "description": DESC, "url": f"https://fixture.invalid/{lid}"}


CATALOGUE = (
    [_l(2000 + i, f"Christmas Stocking Crochet Pattern {i}", 1500 + i) for i in range(6)]
    + [_l(2100 + i, f"Chunky Blanket Crochet Pattern {i}", 1200 + i) for i in range(6)]
    + [_l(2200 + i, f"Beanie Hat Crochet Pattern {i}", 900 + i) for i in range(6)]
)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='w4_mjs_')}/f.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    return db


def _scan(db, listings):
    observe.scan(db, FixtureReader(listings), env={})


def _reviews(db):
    with db.session() as s:
        s.add(BenchmarkObservation(
            benchmark_key=benchmarks.MJS_KEY, kind="official_api_read", grade="mandated",
            detail={"reviews": observe.complaint_themes(
                [{"review": "confusing and unclear", "rating": 2}] * 3
                + [{"review": "lovely", "rating": 5}] * 7)}))


def _cadence_scan(db, now) -> dict:
    """The scheduler's cadence window, then the worker: no prompt, no direct enqueue."""
    saved = {k: os.environ.pop(k, None) for k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET",
                                                  "ETSY_KEYSTRING")}
    try:
        enqueued = Scheduler(db).tick(now=now)
        assert "mjs_scan" in enqueued, enqueued
        with db.session() as s:
            job = s.scalar(select(Job).where(Job.job_type == "mjs.scan",
                                             Job.status == JobStatus.PENDING))
            job.inputs = {**(job.inputs or {}), "as_of": now.date().isoformat()}
            job_id = job.id
        assert Worker(db, "w4-mjs", job_types=["mjs.scan"]).run_once()
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    with db.session() as s:
        row = s.get(Job, job_id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def test_cadence_produces_findings_with_provenance_and_consumers():
    db = _db()
    _scan(db, CATALOGUE)
    _reviews(db)
    out = _cadence_scan(db, datetime(2026, 10, 7, 1, 0, tzinfo=timezone.utc))
    f = out["findings"]
    assert f and "error" not in f, out
    assert f["findings"] >= 6 and f["lessons"], f
    stored = findings.latest(db)
    assert stored, "no mjs.findings reading stored"
    keys = {x["key"] for x in stored["findings"]}
    assert {"pricing", "presentation", "palette", "seasonality", "customer_pain",
            "deliverable_gaps", "demand_by_pod"} <= keys, keys
    assert stored["findings"], "vacuity"
    for x in stored["findings"]:
        assert x["confidence"]["grade"] in ("observed", "proxy"), x
        assert x["provenance"]["tables"] and x["provenance"]["sample"], x
        assert x["consumer"]["readers"], x
    # never competitor text: no fixture title appears in any stored finding
    blob = str(stored)
    assert "Crochet Pattern 3" not in blob and "confusing" not in blob
    print("OK cadence_produces_findings_with_provenance_and_consumers")


def test_radar_score_and_creative_brief_consume_the_findings():
    from brambleloop.creative import ideation
    from brambleloop.runtime.worker import JobContext, handlers  # noqa: F401
    from brambleloop.queue.durable import JobQueue

    db = _db()
    _scan(db, CATALOGUE)
    _reviews(db)
    findings.refresh(db, today=AS_OF)
    seasonal = next(x for x in findings.latest(db)["findings"] if x["key"] == "seasonality")
    lid = seasonal["lesson_id"]
    # Market Radar: radar.score on a Christmas stocking concept acts on the seasonal lesson.
    job = JobQueue(db).enqueue("market_radar", "radar.score",
                               {"slug": "nordic-forest-stocking", "as_of": AS_OF.isoformat()},
                               idempotency_key="w4:radar")
    assert Worker(db, "w4-radar", job_types=["radar.score"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        assert (row.outputs or {}).get("lesson_adjustment", 0) > 0, row.outputs
        acted = [e["cell"] for e in s.get(Lesson, lid).acted_on_by]
    assert "market_radar" in acted, acted
    # Creativity: every tournament/expedition brief draws the published findings.
    brief = ideation.lessons(db, kind="tournament", event="christmas", pod="stockings")
    ours = {x["lesson_id"] for x in findings.latest(db)["findings"]
            if x["consumer"]["bus_subject"] and "product_creativity" in x["consumer"]["cells"]}
    assert ours, "vacuity"
    assert ours <= set(brief["lesson_ids"]), (ours, brief["lesson_ids"])
    print("OK radar_score_and_creative_brief_consume_the_findings")


def test_second_window_on_changed_catalogue_supersedes_without_duplicating():
    db = _db()
    _scan(db, CATALOGUE)
    t0 = datetime(2026, 10, 7, 1, 0, tzinfo=timezone.utc)
    first = _cadence_scan(db, t0)["findings"]
    # Same evidence in the next window on the same day: nothing new is published.
    same = _cadence_scan(db, t0 + timedelta(hours=2))["findings"]
    assert sorted(same["lessons"]) == sorted(first["lessons"]) and not same["superseded"]
    # The benchmark adds eight pricier ornaments; the next day's window finds it unprompted.
    _scan(db, CATALOGUE + [_l(2300 + i, f"Christmas Ornament Crochet Pattern {i}", 2000, 2400)
                           for i in range(8)])
    later = _cadence_scan(db, t0 + timedelta(days=1))["findings"]
    assert "pricing" in later["changed"] and later["superseded"], later
    with db.session() as s:
        live = [l for l in s.scalars(select(Lesson).where(
            Lesson.evidence_ref.like("mjs_finding:pricing:%"),
            Lesson.superseded_by.is_(None)))]
        days = list(s.scalars(select(OperatingReading.period_key).where(
            OperatingReading.kind == findings.KIND)))
    assert len(live) == 1, [l.evidence_ref for l in live]
    assert sorted(days) == ["2026-10-07", "2026-10-08"], days
    print("OK second_window_on_changed_catalogue_supersedes_without_duplicating")


def test_unknown_is_never_zero():
    # Market map: an unaudited gallery's video is unknown, not False.
    row = market_map.describe_listing({"title": "Blanket", "price_cad": 18, "media_count": 3})
    assert row.attributes["gallery_structure"]["has_video"] is None
    # Seasonal positioning is read from the listing's words with word boundaries.
    assert findings.seasonal_positioning("Christmas Stockings") == "Christmas"
    assert findings.seasonal_positioning("Bookshelf Basket") == ""
    # Empty evidence yields no finding and says why, rather than zeros.
    out = findings.synthesize({"pods": {}}, today=AS_OF)
    assert out["findings"] == [] and out["unmeasured"], out
    # A public snapshot without reviews reports customer pain unmeasured, never 0 complaints.
    snap = {"market_map": {"rows": [
        {"pod": "hats", "observed_on": "2026-10-06T00:00:00+00:00",
         "attributes": {"visible_pricing": {"price_cad": 18.0},
                        "gallery_structure": {"images": 10}}}] * 6}}
    res = findings.synthesize(findings.evidence_from_public_snapshot(snap), today=AS_OF)
    assert any(u["key"] == "customer_pain" for u in res["unmeasured"]), res["unmeasured"]
    assert any(u["key"] == "video" for u in res["unmeasured"])
    print("OK unknown_is_never_zero")


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert tests, "vacuity"
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
    sys.exit(1 if failed else 0)
