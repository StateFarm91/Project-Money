"""WS2 R6 and R7 (audit WS2_research_audit).

R6: the watchlist scan passed `env={}` to `observe.scan`, which hid the Etsy credential from
`mission.record`, so every watchlist observation was graded `supporting`. The real
environment now reaches the grading: with the credential an official API read is graded as
the observation it is; without it, it is still `supporting`.

R7: HanJanCrochet is a seed shop (`hanjan_crochet`) and a second-market candidate. The
second-market join refuses a shop already registered under any key, and a panel row that
duplicates a code-registered shop is not scanned a second time.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws2_r6_r7_watchlist_env_dedupe.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import Benchmark, BenchmarkObservation  # noqa: E402
from brambleloop.intel import benchmarks, panel_discovery, second_market  # noqa: E402
from brambleloop.intel import watchlist  # noqa: E402
from test_ws2_r1_competitor_scans import NOW, _db  # noqa: E402
from test_ws2_r3_source_timestamp import T1, _listing, _Reader  # noqa: E402

CRED = {"ETSY_API_KEY": "fixture-keystring", "ETSY_SHARED_SECRET": "fixture-secret"}


def _grades(db, key):
    with db.session() as s:
        # The scan's own observation (`observe.scan` -> `mission.record`); the weekly reviews
        # pass files its own row and is not what R6 changes.
        return [r.grade for r in s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == key,
            BenchmarkObservation.kind == "official_api_read"))
            if "catalogue_coverage" in (r.detail or {})]


class _WatchReader(_Reader):
    """The watchlist also reads the shop's reviews weekly."""

    def reviews(self, *a, **k):
        return []


def _member():
    return next(m for m in watchlist.WATCHLIST if m.role != watchlist.ANCHOR)


def test_r6_with_the_credential_a_watchlist_read_is_not_graded_supporting():
    db = _db()
    m = _member()
    out = watchlist.scan_member(db, m, _WatchReader([_listing(1, T1)]), now=NOW,
                                force=True, env=CRED)
    assert out["ran"] is True, out
    grades = _grades(db, m.key)
    assert grades and all(g != "supporting" for g in grades), grades


def test_r6_without_the_credential_it_stays_supporting():
    db = _db()
    m = _member()
    watchlist.scan_member(db, m, _WatchReader([_listing(1, T1)]), now=NOW, force=True,
                          env={})
    assert _grades(db, m.key) == ["supporting"]


def test_r6_scan_all_passes_its_environment_to_each_shop():
    import inspect

    src = inspect.getsource(watchlist)
    assert "env={})" not in src.replace("`env={}`", "")
    assert "force=force,\n                                     env=env)" in src


class _ShopReader:
    def resolve_shop(self, name):
        return {"shop_id": 77}

    def shop(self, shop_id):
        return {"shop_name": "HanJanCrochet", "shop_location_country_iso": "KR"}


def test_r7_the_second_market_join_refuses_a_shop_registered_under_another_key():
    db = _db()
    benchmarks.seed(db)
    out = second_market.ensure_selected(db, _ShopReader(), now=NOW)
    han = next(o for o in out if o["shop_name"] == "HanJanCrochet")
    assert han["state"] == "already_registered" and han["key"] == benchmarks.HANJAN.key, han
    # The verified market is recorded on the existing registration.
    assert benchmarks.market_of(db, benchmarks.HANJAN.key) == han["market"] == "other", han
    with db.session() as s:
        rows = [r.key for r in s.scalars(select(Benchmark).where(
            Benchmark.shop_name == "HanJanCrochet"))]
    assert rows == [benchmarks.HANJAN.key], rows


def test_r7_an_existing_panel_duplicate_is_not_scanned_twice():
    db = _db()
    benchmarks.seed(db)
    dup = panel_discovery._key_for("HanJanCrochet")
    with db.session() as s:
        s.add(Benchmark(key=dup, shop_name="HanJanCrochet", platform="etsy",
                        canonical_url="https://example.invalid/x", mandatory=False,
                        scan_health={"state": "discovered"}))
        s.add(Benchmark(key=panel_discovery._key_for("OtherLeader"), shop_name="OtherLeader",
                        platform="etsy", canonical_url="https://example.invalid/y",
                        mandatory=False, scan_health={"state": "discovered"}))
    scanned = []

    import brambleloop.intel.observe as observe

    real = observe.scan

    def fake_scan(db_, reader, *, benchmark_key, shop_name, **kw):
        scanned.append(benchmark_key)
        return real(db_, _Reader([_listing(1, T1)]), benchmark_key=benchmark_key,
                    shop_name=shop_name, env={})

    observe.scan = fake_scan
    try:
        out = panel_discovery.discover(db, reader=_ShopReader(), now=NOW)
    finally:
        observe.scan = real
    assert out["ran"] is True, out
    assert sorted(scanned) == [panel_discovery._key_for("OtherLeader")], scanned
    # The member filter itself, independent of discovery.
    import inspect

    src = inspect.getsource(panel_discovery)
    assert "owned = {spec.shop_name.lower() for spec in benchmarks.REGISTRY}" in src


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
