"""OPUS2-P0: P0-COMPETITOR-EVIDENCE -- which named shops were actually scanned, and what then.

Every scan row, memory state and observed listing here is a TEST FIXTURE; no shop is read.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_scan_evidence.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Benchmark, BenchmarkListing, Job, JobStatus, OperatingReading,
)
from brambleloop.intel import benchmarks, watchlist  # noqa: E402
from brambleloop.intel import scan_evidence as SE  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_scan_')}/s.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _by_shop(rep):
    return {r["shop"]: r for r in rep["shops"]}


def _watch_state(db, shop, body):
    member = next(m for m in watchlist.WATCHLIST if m.shop_name == shop)
    memory.remember(db, watchlist.STATE_PREFIX + member.key, kind="intel.watchlist",
                    department="intelligence", subject=f"watchlist {member.key}",
                    state=body.get("state", "unknown"), body=body, sources=["fixture"], now=NOW)
    return member.key


def test_wired_daily_and_permitted():
    assert ("scan_evidence", "market_radar", "intel.scan_evidence", 86400) in CADENCES
    Registry(_db()).authorize("market_radar", "intel.scan_evidence")


def test_nothing_recorded_means_never_attempted_or_not_registered_never_scanned():
    rep = SE.report(_db(), now=NOW)
    shops = _by_shop(rep)
    assert [s for s, _u, _r in SE.OWNER_SHOPS] == [r["shop"] for r in rep["shops"]]
    assert len(shops) == 8 and rep["scanned"] == []
    assert shops["MJsOffTheHookDesigns"]["state"] == SE.NEVER
    for shop in ("MadelineMaeCo", "ZKBDESIGNER", "TheEasyDesign"):
        assert shops[shop]["state"] == SE.NEVER and shops[shop]["schedule"]["every_hours"] == 6
    registered = {m.shop_name for m in watchlist.WATCHLIST}
    for shop in ("HanJanCrochet", "IvyLoop", "LoveandStitchDesigns", "FireflyCrochets"):
        want = SE.NEVER if shop in registered else SE.NOT_REGISTERED
        assert shops[shop]["state"] == want, (shop, shops[shop]["state"])
        if want == SE.NOT_REGISTERED:
            assert shops[shop]["last_successful"] is None and "no scan can have run" in \
                shops[shop]["failure_reason"]
    assert all(r["downstream"]["listings_observed"] == 0 for r in rep["shops"])
    assert rep["credential"].startswith("UNKNOWN")
    assert all(r["observed"] is False and r["why"] for r in rep["reference_listings"])


def test_a_scanned_anchor_reports_its_times_provenance_and_observed_listings():
    db = _db()
    scanned_at = NOW - timedelta(hours=3)
    with db.session() as s:
        s.add(Benchmark(key=benchmarks.MJS_KEY, shop_name=benchmarks.MJS_SHOP,
                        canonical_url=benchmarks.MJS_CANONICAL_URL, last_scan_at=scanned_at,
                        scan_health={"state": "healthy"}))
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE,
                  inputs={}, outputs={"new": 2}, finished_at=scanned_at))
        for ref in ("A1", "A2", SE.REFERENCE_LISTINGS[0][0]):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=ref,
                                   pod="home_decor", first_seen=scanned_at,
                                   last_seen=scanned_at))
    rep = SE.report(db, now=NOW)
    mjs = _by_shop(rep)["MJsOffTheHookDesigns"]
    assert mjs["state"] == SE.SCANNED and mjs["last_successful"].startswith("2026-10-31T09")
    assert mjs["failure_reason"] is None and mjs["downstream"]["listings_observed"] == 3
    assert mjs["schedule"]["job_type"] == "mjs.scan" and "Open API v3" in mjs["method"]
    refs = {r["listing_id"]: r for r in rep["reference_listings"]}
    assert refs[SE.REFERENCE_LISTINGS[0][0]]["observed"] is True
    assert refs[SE.REFERENCE_LISTINGS[1][0]]["observed"] is False
    assert rep["scanned"] == ["MJsOffTheHookDesigns"]


def test_a_failed_anchor_attempt_after_a_success_is_its_current_failure():
    db = _db()
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE,
                  inputs={}, outputs={"new": 1}, finished_at=NOW - timedelta(days=1)))
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE,
                  inputs={}, outputs={"ran": False, "reason": "ping returned HTTP 403"},
                  finished_at=NOW - timedelta(hours=1)))
    mjs = _by_shop(SE.report(db, now=NOW))["MJsOffTheHookDesigns"]
    # Review OPUS2B2 F3.1: a refusal newer than the last success is the anchor's state; the
    # old success stays as last_successful.
    assert mjs["state"] == SE.NOT_ACCESSIBLE and "403" in mjs["failure_reason"]
    assert mjs["last_successful"] is not None


def test_review_opus2b2_f31_success_then_repeated_refusal_is_not_scanned():
    """The reviewer's repro: once scanned in August, refused by the API ever since."""
    db = _db()
    _watch_state(db, "MadelineMaeCo", {"state": "credential_refused",
                                       "last_ok_at": "2026-08-01T00:00:00+00:00",
                                       "last_attempt_at": "2026-10-31T06:00:00+00:00",
                                       "last_error": "403 key refused",
                                       "consecutive_failures": 40})
    _watch_state(db, "ZKBDESIGNER", {"state": "source_outage",
                                     "last_ok_at": "2026-10-01T00:00:00+00:00",
                                     "last_attempt_at": "2026-10-31T06:00:00+00:00",
                                     "last_error": "timeout", "consecutive_failures": 3})
    rep = SE.report(db, now=NOW)
    shops = _by_shop(rep)
    m = shops["MadelineMaeCo"]
    assert m["state"] == SE.NOT_ACCESSIBLE, m
    assert m["failure_reason"] == "403 key refused" and m["consecutive_failures"] == 40
    assert m["last_successful"] == "2026-08-01T00:00:00+00:00"
    z = shops["ZKBDESIGNER"]
    assert z["state"] == SE.ATTEMPTED and z["failure_reason"] == "timeout", z
    # Neither is counted as scanned, and both reach the owner-facing list.
    assert not any(r["state"] == SE.SCANNED for r in (m, z))
    listed = {r["shop"] if isinstance(r, dict) else r for r in rep.get("not_scanned", [])}
    assert {"MadelineMaeCo", "ZKBDESIGNER"} <= listed, rep.get("not_scanned")


def test_watchlist_states_scanned_outage_and_not_accessible_are_reported_as_recorded():
    db = _db()
    _watch_state(db, "MadelineMaeCo", {"state": "ok", "last_ok_at": "2026-10-31T06:00:00+00:00",
                                       "last_attempt_at": "2026-10-31T06:00:00+00:00",
                                       "listings_seen": 41})
    _watch_state(db, "ZKBDESIGNER", {"state": "source_outage",
                                     "last_attempt_at": "2026-10-31T06:00:00+00:00",
                                     "last_error": "timeout", "consecutive_failures": 2})
    _watch_state(db, "TheEasyDesign", {"state": "not_accessible",
                                       "last_attempt_at": "2026-10-31T06:00:00+00:00",
                                       "limitation": "not accessible: shop not found",
                                       "limitation_on": "2026-10-31",
                                       "last_error": "not accessible: shop not found"})
    shops = _by_shop(SE.report(db, now=NOW))
    assert shops["MadelineMaeCo"]["state"] == SE.SCANNED
    assert shops["MadelineMaeCo"]["listings_seen_last_scan"] == 41
    z = shops["ZKBDESIGNER"]
    assert z["state"] == SE.ATTEMPTED and z["failure_reason"] == "timeout" and \
        z["consecutive_failures"] == 2 and z["last_successful"] is None
    e = shops["TheEasyDesign"]
    assert e["state"] == SE.NOT_ACCESSIBLE and any("shop not found" in x
                                                   for x in e["limitations"])


def test_the_job_writes_one_reading_per_day_and_reports_work():
    db = _db()
    q = JobQueue(db)

    def run():
        job = q.enqueue("market_radar", "intel.scan_evidence", {},
                        idempotency_key=f"t:{os.urandom(4).hex()}")
        return handlers.get("intel.scan_evidence")(JobContext(
            job=job, db=db, queue=q, registry=Registry(db), phase=None))

    out = run()
    run()
    assert out["shops"] == 8 and not pipeline.did_no_work(out, "intel.scan_evidence")
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(OperatingReading).where(
            OperatingReading.kind == SE.READING_KIND))
    assert n == 1 and SE.latest(db)["shops"][0]["shop"] == "MJsOffTheHookDesigns"


def test_the_evidence_copies_no_competitor_content():
    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="Z9",
                               title="A COMPETITOR TITLE THAT MUST NOT BE COPIED",
                               url="https://www.etsy.com/listing/Z9/secret", pod="home_decor"))
    text = str(SE.report(db, now=NOW))
    assert "COMPETITOR TITLE" not in text and "/listing/Z9/secret" not in text


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
