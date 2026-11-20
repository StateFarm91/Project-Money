"""Certification C-40 / #206: benchmark URL health through the sanctioned read API.

Against 63f2493 (and the MJs wiring as first delivered) the health check could only ever read
`unverified` without a browser worker, although the read credential this company already
holds can ask Etsy which shop the name belongs to. These tests drive the real handler path
(`mission_runtime.benchmark_health`) with a fake reader: no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.intel import mission_runtime as mr  # noqa: E402
from brambleloop.intel.etsy_public import NotConfigured, ReadFailed  # noqa: E402

SHOP = benchmarks.MJS_SHOP


class _Reader:
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def resolve_shop(self, name):
        self.asked.append(name)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _db():
    db = Database("sqlite://")
    db.create_all()
    benchmarks.seed(db)
    return db


def _mjs(out):
    return next(r for r in out["results"] if r["key"] == benchmarks.MJS_KEY)


def test_the_named_shop_reported_by_etsy_reads_healthy_without_a_browser():
    reader = _Reader({"shop_id": 1, "shop_name": SHOP,
                      "url": f"https://www.etsy.com/shop/{SHOP}?utm_source=x"})
    out = mr.benchmark_health(_db(), env={}, reader_factory=lambda: reader)
    res = _mjs(out)
    assert out["capability"] == "etsy_api"
    assert res["state"] == benchmarks.HEALTHY, res
    assert res["detail"]["basis"] == "etsy_api_findShops"
    # The locale segment difference is not a move: the registry is not re-pointed.
    assert res["url"] == benchmarks.MJS_CANONICAL_URL
    assert reader.asked and reader.asked[0] == SHOP


def test_a_shop_whose_own_url_names_someone_else_is_wrong_shop_and_opens_an_incident():
    reader = _Reader({"shop_id": 2, "shop_name": SHOP,
                      "url": "https://www.etsy.com/shop/SomebodyElse"})
    out = mr.benchmark_health(_db(), env={}, reader_factory=lambda: reader)
    assert _mjs(out)["state"] == benchmarks.WRONG_SHOP
    assert any(sig.endswith(benchmarks.MJS_KEY) for sig in out["incidents_opened"]), out


def test_a_name_etsy_cannot_find_exactly_is_unreachable_not_healthy():
    out = mr.benchmark_health(_db(), env={},
                              reader_factory=lambda: _Reader(ReadFailed("not found exactly")))
    assert _mjs(out)["state"] == benchmarks.UNREACHABLE


def test_no_credential_stays_unverified():
    out = mr.benchmark_health(_db(), env={},
                              reader_factory=lambda: _Reader(NotConfigured("no key")))
    assert _mjs(out)["state"] == benchmarks.UNVERIFIED
    out = mr.benchmark_health(_db(), env={})           # no credential in env: no reader at all
    assert out["capability"] == "unverified"
    assert _mjs(out)["state"] == benchmarks.UNVERIFIED


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
