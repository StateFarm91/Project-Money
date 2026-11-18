"""WS2 R4 (audit WS2_research_audit): facts the scanners computed but never kept.

* A watched shop keeps each failed attempt's time and CLASS (never its text) for 30 days, and
  the readback counts the last 7 days by class. The anchor's count comes from its failed
  `mjs.scan` jobs; a deferral is not an attempt (R2).
* The anchor keeps Etsy's active-listing count per scan, and the readback reports it.
* Live listing coverage excludes withdrawn listings, next-due and backoff are projected
  (R1, pinned again here so R4's row is whole).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws2_r4_kept_scan_facts.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.core.models import Job, JobStatus  # noqa: E402
from brambleloop.intel import benchmarks, observe, watchlist  # noqa: E402
from brambleloop.intel.etsy_public import ReadFailed  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from test_ws2_r1_competitor_scans import NOW, _db, _fixture, _watch  # noqa: E402
from test_ws2_r3_source_timestamp import T1, _listing, _Reader  # noqa: E402


def _row(db, order):
    return next(r for r in PE.competitor_scans(db, now=NOW)["shops"]
                if r["owner_order"] == order)


def test_note_error_keeps_class_and_time_only_and_drops_old_entries():
    st = {"error_history": [{"at": (NOW - timedelta(days=40)).isoformat(), "class": "old"},
                            "junk", {"at": (NOW - timedelta(days=2)).isoformat(),
                                     "class": "source_outage"}]}
    watchlist._note_error(st, "credential_refused", now=NOW)
    assert st["error_history"] == [
        {"at": (NOW - timedelta(days=2)).isoformat(), "class": "source_outage"},
        {"at": NOW.isoformat(), "class": "credential_refused"}], st
    for _ in range(watchlist.ERROR_HISTORY_MAX + 5):
        watchlist._note_error(st, "x", now=NOW)
    assert len(st["error_history"]) == watchlist.ERROR_HISTORY_MAX


class _Failing:
    def __init__(self, exc):
        self.exc = exc

    def resolve_shop(self, name):
        raise self.exc


def test_a_watched_shops_failures_are_kept_by_class():
    db = _db()
    member = next(m for m in watchlist.WATCHLIST if m.key != benchmarks.MJS_KEY)
    refused = ReadFailed("HTTP 403 Forbidden", status=403)
    for i, exc in enumerate((refused, RuntimeError("boom with a shop name in it"))):
        watchlist.scan_member(db, member, _Failing(exc), force=True,
                              now=NOW + timedelta(minutes=i))
    st = watchlist._state(db, member.key)
    classes = [e["class"] for e in st["error_history"]]
    assert classes == ["credential_refused", "RuntimeError"], st["error_history"]
    assert all(set(e) == {"at", "class"} for e in st["error_history"])


def test_the_readback_counts_errors_over_seven_days_by_class_with_no_text():
    db, ok_member, refused_member = _fixture()
    _watch(db, refused_member, {
        "state": "credential_refused", "consecutive_failures": 3,
        "last_attempt_at": (NOW - timedelta(hours=1)).isoformat(),
        "last_error": "HTTP 403 Forbidden for https://openapi.etsy.com/... SecretShop",
        "error_history": [
            {"at": (NOW - timedelta(days=9)).isoformat(), "class": "source_outage"},
            {"at": (NOW - timedelta(days=3)).isoformat(), "class": "credential_refused"},
            {"at": (NOW - timedelta(hours=1)).isoformat(), "class": "credential_refused"},
            {"at": (NOW - timedelta(hours=2)).isoformat(), "class": "a name: SecretShop"}]})
    section = PE.competitor_scans(db, now=NOW)
    order = [i for i, r in enumerate(section["shops"], 1)
             if r["failure_class"] == "credential_refused"][0]
    row = section["shops"][order - 1]
    assert row["errors_7d"] == {"count": 3, "by_class": {"credential_refused": 2, "other": 1},
                                "window_days": 7}, row["errors_7d"]
    assert "SecretShop" not in json.dumps(section)


def test_the_anchors_errors_come_from_its_failed_jobs_and_deferrals_do_not_count():
    db, *_ = _fixture()
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"ran": False, "deferred": True, "reason": "not due"},
                  finished_at=NOW - timedelta(hours=1)))
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"ran": False, "credential_refused": True,
                           "reason": "credential refused"},
                  finished_at=NOW - timedelta(hours=2)))
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DEAD, inputs={},
                  outputs={}, last_error="TimeoutError: read timed out",
                  finished_at=NOW - timedelta(days=1)))
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DEAD, inputs={},
                  outputs={}, last_error="TimeoutError: old",
                  finished_at=NOW - timedelta(days=8)))
    errors = _row(db, 1)["errors_7d"]
    assert errors["count"] == 2 and errors["by_class"].get("credential_refused") == 1, errors
    assert sum(errors["by_class"].values()) == 2


def test_the_anchor_keeps_etsys_active_listing_count():
    db = _db()

    class _Shop(_Reader):
        def resolve_shop(self, name):
            return {"shop_id": 1, "listing_active_count": 438}

    out = observe.scan(db, _Shop([_listing(1, T1)]), benchmark_key="bm-r4",
                       shop_name="S", env={})
    assert out.to_report()["shop"] == {"listing_active_count": 438}

    class _Junk(_Reader):
        def resolve_shop(self, name):
            return {"shop_id": 1, "listing_active_count": "many"}

    out = observe.scan(_db(), _Junk([_listing(1, T1)]), benchmark_key="bm-r4b",
                       shop_name="S", env={})
    assert out.to_report()["shop"] == {"listing_active_count": None}
    # The readback reads it from the anchor's newest successful scan.
    db, *_ = _fixture()
    assert _row(db, 1)["etsy_active_listing_count"] is None
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"ran": True, "etsy_active_listing_count": 412},
                  finished_at=NOW - timedelta(hours=4)))
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"ran": True, "etsy_active_listing_count": 438},
                  finished_at=NOW - timedelta(hours=1)))
    assert _row(db, 1)["etsy_active_listing_count"] == 438


def test_live_coverage_excludes_withdrawn_and_next_due_is_projected():
    db, *_ = _fixture()
    row = _row(db, 1)
    assert row["listings_live"] == 2, row          # three stored, one withdrawn
    assert "next_due" in row and "backoff_until" in row


def test_the_mjs_job_output_carries_the_count():
    import inspect

    from brambleloop.runtime import release

    assert '"etsy_active_listing_count": report["shop"]["listing_active_count"]' in \
        inspect.getsource(release.handle_mjs_scan)


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
