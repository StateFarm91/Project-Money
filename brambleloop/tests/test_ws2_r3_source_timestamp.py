"""WS2 R3 (audit WS2_research_audit): the "source timestamp" is Etsy's clock, not ours.

Each observed listing keeps Etsy's `last_modified_timestamp` (as ISO 8601 UTC), each scan
carries the newest one it read, and the scan evidence and the readback section report that
value -- or None with the reason when it was not recorded. Our own scan time is never
substituted for it.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws2_r3_source_timestamp.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import BenchmarkListing, Job, JobStatus  # noqa: E402
from brambleloop.intel import benchmarks, observe  # noqa: E402
from brambleloop.intel import scan_evidence as SE  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from test_ws2_r1_competitor_scans import NOW, _db, _fixture, _watch  # noqa: E402

T1 = 1_762_000_000          # 2025-11-01T12:26:40Z
T2 = 1_762_900_000          # 2025-11-11T22:26:40Z
ISO1 = datetime.fromtimestamp(T1, tz=timezone.utc).isoformat()
ISO2 = datetime.fromtimestamp(T2, tz=timezone.utc).isoformat()


class _Reader:
    """The public reader's surface `observe.scan` uses, with fixed catalogue payloads."""

    def __init__(self, listings):
        self.listings = listings

    def resolve_shop(self, name):
        return {"shop_id": 1}

    def catalogue(self, shop_id):
        return list(self.listings)

    def images(self, ref):
        return []

    def videos(self, ref):
        return []


def _listing(ref, ts, title="Coaster pattern"):
    return {"listing_id": ref, "title": title, "description": "", "price": {"amount": 800,
            "divisor": 100}, "tags": [], "materials": [], "state": "active",
            "last_modified_timestamp": ts, "num_favorers": 1, "url": ""}


def test_source_modified_at_converts_etsys_epoch_seconds_and_refuses_junk():
    assert observe.source_modified_at({"last_modified_timestamp": T1}) == ISO1
    assert observe.source_modified_at({"last_modified_timestamp": str(T2)}) == ISO2
    for junk in (None, "", 0, -5, "soon", True, [1]):
        assert observe.source_modified_at({"last_modified_timestamp": junk}) is None, junk
    assert observe.source_modified_at({}) is None


def test_a_scan_keeps_etsys_time_per_listing_and_the_newest_per_scan():
    db = _db()
    out = observe.scan(db, _Reader([_listing(11, T1), _listing(12, T2)]),
                       benchmark_key="bm-r3", shop_name="ShopR3", env={})
    report = out.to_report()
    assert report["source_timestamp"] == {"newest_listing_modified_at": ISO2,
                                          "basis": "Etsy last_modified_timestamp"}, report
    with db.session() as s:
        got = {r.listing_ref: (r.detail or {}).get("source_modified_at") for r in s.scalars(
            select(BenchmarkListing).where(BenchmarkListing.benchmark_key == "bm-r3"))}
    assert got == {"11": ISO1, "12": ISO2}, got
    # It is Etsy's clock, not the scan's.
    assert report["source_timestamp"]["newest_listing_modified_at"] != report["observed_at"]


def test_an_unchanged_listing_from_before_r3_gains_its_timestamp():
    db = _db()
    observe.scan(db, _Reader([_listing(21, T1)]), benchmark_key="bm-r3b", shop_name="S",
                 env={})
    with db.session() as s:
        row = s.scalar(select(BenchmarkListing).where(BenchmarkListing.listing_ref == "21"))
        row.detail = {k: v for k, v in (row.detail or {}).items()
                      if k != "source_modified_at"}
    out = observe.scan(db, _Reader([_listing(21, T1)]), benchmark_key="bm-r3b",
                       shop_name="S", env={})
    assert out.unchanged == 1
    with db.session() as s:
        row = s.scalar(select(BenchmarkListing).where(BenchmarkListing.listing_ref == "21"))
        assert (row.detail or {}).get("source_modified_at") == ISO1


def test_a_payload_without_timestamps_reports_none_not_our_clock():
    db = _db()
    listing = _listing(31, None)
    out = observe.scan(db, _Reader([listing]), benchmark_key="bm-r3c", shop_name="S", env={})
    assert out.to_report()["source_timestamp"]["newest_listing_modified_at"] is None


def test_the_evidence_reports_etsys_time_for_the_anchor_and_the_watched_shops():
    db, ok_member, _refused = _fixture()
    rep = SE.report(db, now=NOW)
    by = {r["shop"]: r for r in rep["shops"]}
    anchor = by[benchmarks.MJS_SHOP]
    # The fixture's scans predate R3: no Etsy time recorded, and our clock is not used.
    assert anchor["last_successful"] and anchor["source_timestamp"] is None, anchor
    assert anchor["source_timestamp_basis"].startswith("not recorded"), anchor
    watched = next(r for r in rep["shops"] if r.get("key") == ok_member.key)
    assert watched["source_timestamp"] is None and watched["last_successful"]
    # Scans that recorded Etsy's time report it.
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE,
                  inputs={}, outputs={"ran": True, "source_timestamp": ISO2},
                  finished_at=NOW - timedelta(hours=1)))
    _watch(db, ok_member, {"state": "ok", "last_ok_at": (NOW - timedelta(hours=2)).isoformat(),
                           "last_attempt_at": (NOW - timedelta(hours=2)).isoformat(),
                           "source_timestamp": ISO1})
    rep = SE.report(db, now=NOW)
    by = {r["shop"]: r for r in rep["shops"]}
    assert by[benchmarks.MJS_SHOP]["source_timestamp"] == ISO2
    assert by[benchmarks.MJS_SHOP]["source_timestamp_basis"].startswith("Etsy")
    watched = next(r for r in rep["shops"] if r.get("key") == ok_member.key)
    assert watched["source_timestamp"] == ISO1
    # The readback section projects it.
    section = PE.competitor_scans(db, now=NOW)
    anchor_row = next(r for r in section["shops"] if r["owner_order"] == 1)
    assert anchor_row["etsy_source_timestamp"] == ISO2, anchor_row
    assert anchor_row["etsy_source_timestamp"] != anchor_row["last_successful"]


def test_the_scan_jobs_carry_etsys_time_into_their_outputs():
    import inspect

    from brambleloop.intel import watchlist
    from brambleloop.runtime import release

    assert '"source_timestamp": report["source_timestamp"]["newest_listing_modified_at"]' in \
        inspect.getsource(release.handle_mjs_scan)
    assert 'source_timestamp=report["source_timestamp"]["newest_listing_modified_at"]' in \
        inspect.getsource(watchlist)


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
