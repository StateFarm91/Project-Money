"""D-OWNER-NINTH-SHOP (owner directive 2026-11-19): ArtLoveDesing, the ninth research shop.

OFFLINE -- NOT PRODUCTION EVIDENCE. Every Etsy read is a recorded fixture reader (the watchlist
suite's); nothing touches a network, spends, or writes to Etsy.

What is pinned:

* the shop is in EVERY registry (benchmarks, watchlist, scan_evidence, radar), spelled exactly
  as the shop spells itself ("Desing"), with the owner-supplied URL verbatim and the canonical
  one beside it, role "permanent";
* the scan reads it on the watchlist cadence by the same official-API path, and the comparison
  answers each part the owner asked for (listings, prices, amigurumi, PDF languages and
  quality, reviews, trends) -- PDF quality honestly UNMEASURED, never approximated;
* an unreachable shop is a recorded limitation, never blocks the other eight and is never
  reported as scanned;
* no competitor content leaves the comparison.

Run: cd brambleloop && python3 tests/test_ninth_shop.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_intelrec_watchlist as W  # noqa: E402 - the watchlist's own fixture reader
from brambleloop.intel import benchmarks, watchlist  # noqa: E402
from brambleloop.intel import scan_evidence as SE  # noqa: E402
from brambleloop.intel.etsy_public import ReadFailed  # noqa: E402
from brambleloop.radar.market import COMPETITORS  # noqa: E402
from brambleloop.runtime.intel_ops import benchmark_alias  # noqa: E402

SHOP = "ArtLoveDesing"
KEY = "artlove_desing"
OWNER_URL = "https://www.etsy.com/ca/shop/ArtLoveDesing?ref=shop_profile&listing_id=4427559824"
CANONICAL = "https://www.etsy.com/ca/shop/ArtLoveDesing"
NINE = ("MJsOffTheHookDesigns", "MadelineMaeCo", "ZKBDESIGNER", "TheEasyDesign",
        "HanJanCrochet", "IvyLoop", "LoveandStitchDesigns", "FireflyCrochets", SHOP)
NOW = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)


def test_the_ninth_shop_is_in_every_registry_exactly():
    spec = benchmarks.spec_for(KEY)
    assert spec is not None and spec.shop_name == SHOP and spec.mandatory
    assert spec.owner_supplied_url == OWNER_URL and spec.canonical_url == CANONICAL
    assert benchmarks.ARTLOVE_OWNER_SUPPLIED_URL == OWNER_URL
    assert "D-OWNER-NINTH-SHOP" in spec.reason_for_inclusion
    assert tuple(b.shop_name for b in benchmarks.REGISTRY) == NINE
    m = watchlist.BY_KEY[KEY]
    assert (m.shop_name, m.owner_url, m.role, m.special) == (SHOP, OWNER_URL,
                                                             watchlist.PERMANENT, False)
    assert tuple(x.shop_name for x in watchlist.WATCHLIST) == NINE
    assert tuple(s for s, _u, _r in SE.OWNER_SHOPS) == NINE
    assert (SHOP, OWNER_URL, "permanent") in SE.OWNER_SHOPS
    prof = next(c for c in COMPETITORS if c.shop == SHOP)
    assert prof.url == CANONICAL
    # Nothing has been observed, so nothing is claimed about it.
    assert prof.observed_price_band_cad == (0.0, 0.0) and not prof.format_signals
    # Spelled as the shop spells itself: a "corrected" name would be a different seller.
    assert not any("ArtLoveDesign" in s for s in NINE)


def test_a_database_seeded_from_code_holds_nine_mandatory_benchmarks():
    from sqlalchemy import select

    from brambleloop.core.models import Benchmark

    db = W._db()
    with db.session() as s:
        rows = {b.key: b for b in s.scalars(select(Benchmark))}
    assert {b.key for b in benchmarks.REGISTRY} <= set(rows)
    assert rows[KEY].mandatory and rows[KEY].owner_supplied_url == OWNER_URL


class _Languages(W.Reader):
    """The fixture reader, with the shop's offered languages as findShops returns them."""

    def resolve_shop(self, name):
        shop = super().resolve_shop(name)
        if name == SHOP:
            shop["languages"] = ["en-US", "fr", "<b>not a code</b>"]
        return shop


def test_the_scan_and_comparison_cover_what_the_owner_asked_to_monitor():
    db = W._db()
    W._with_reader(_Languages())
    try:
        out = watchlist.scan_all(db, force=True, now=NOW)
        rep = watchlist.compare(db, now=NOW + timedelta(minutes=1))
    finally:
        watchlist.reader_factory = None
    mine = next(x for x in out["shops"] if x["key"] == KEY)
    assert mine["ran"] is True and mine["listings_seen"] == 1, mine
    assert out["observed"] == len(NINE) - 1          # every non-anchor shop, this one included
    row = next(s for s in rep["shops"] if s["alias"] == benchmark_alias(KEY))
    assert row["role"] == watchlist.PERMANENT
    focus = row["monitoring_focus"]
    assert set(focus) == {"listings", "prices", "amigurumi", "pdf_languages", "pdf_quality",
                          "reviews", "trends"}, focus
    assert set(focus) == set(benchmarks.ARTLOVE_FOCUS)
    figures = row["figures"]
    for part, names in focus.items():
        assert names, part
        for name in names:
            assert name in figures, (part, name)
    assert figures["listings_observed"]["value"] == 1
    assert figures["listings_observed"]["grade"] == "MEASURED"
    assert figures["price_median_cad"]["grade"] == "MEASURED"
    assert figures["review_count"]["grade"] == "MEASURED"
    assert figures["recurring_complaint_themes"]["grade"] == "DERIVED"
    # The fixture listing is a dishcloth: zero amigurumi is a reading, not an unknown.
    assert figures["amigurumi_listings"] == {**figures["amigurumi_listings"], "value": 0,
                                             "grade": "DERIVED"}
    # Languages: codes only, from findShops; payload text that is not a code is dropped.
    assert figures["listing_languages"]["value"] == ["en-US", "fr"]
    assert figures["listing_languages"]["source"] == "findShops"
    assert "not a code" not in json.dumps(watchlist._state(db, KEY))
    # PDF quality: no compliant source, so UNMEASURED with its reason -- never a proxy score.
    pq = figures["pdf_quality"]
    assert pq["grade"] == "UNMEASURED" and pq["value"] == "UNKNOWN" and pq["why"], pq
    assert rep["scope"]["pdf_quality"] == "UNMEASURED"
    assert rep["scope"]["pdf_languages"] == "MEASURED"
    assert rep["scope"]["amigurumi"] == "DERIVED"
    # Amigurumi is counted for a shop that has some (FireflyCrochets' fixture moose).
    fire = next(s for s in rep["shops"] if s["alias"] == benchmark_alias("firefly_crochets"))
    assert fire["figures"]["amigurumi_listings"]["value"] == 1
    # The other shops carry no focus they were never given.
    assert all(s["monitoring_focus"] == {} for s in rep["shops"] if s is not row)


def test_an_unreachable_ninth_shop_is_a_limitation_and_never_blocks_the_others():
    db = W._db()

    class Gone(W.Reader):
        def resolve_shop(self, name):
            if name == SHOP:
                self.calls.append(("resolve", name))
                raise ReadFailed(f"{name!r} was not found exactly. Etsy returned [], and a "
                                 f"near match is a different seller")
            return super().resolve_shop(name)

    W._with_reader(Gone())
    try:
        out = watchlist.scan_all(db, force=True, now=NOW)
    finally:
        watchlist.reader_factory = None
    mine = next(x for x in out["shops"] if x["key"] == KEY)
    assert mine["ran"] is False and mine["scanned"] is False
    assert mine["state"] == watchlist.NOT_ACCESSIBLE and mine["on"] == "2026-11-19"
    # Owner-named but never observed: said so, not dressed up as a seed observation.
    assert "not yet observed" in mine["alternative_evidence"], mine
    assert out["observed"] == len(NINE) - 2                # the other seven non-anchor shops
    assert KEY not in out["outages"] and out["not_accessible"][0]["key"] == KEY
    st = watchlist._state(db, KEY)
    assert st["monitoring"] == "kept" and not st.get("last_ok_at") and "shop" not in st
    rep = SE.report(db, now=NOW + timedelta(minutes=1))
    assert SHOP not in rep["scanned"]
    rec = next(r for r in rep["shops"] if r["shop"] == SHOP)
    assert rec["state"] != SE.SCANNED and rec["owner_url"] == OWNER_URL, rec
    sm = watchlist.summary(db, now=NOW + timedelta(minutes=1))
    assert any("not accessible since 2026-11-19" in x for x in sm["not_accessible"]), sm


def test_no_competitor_content_or_name_leaves_the_comparison():
    db = W._db()
    W._with_reader(_Languages())
    try:
        watchlist.scan_all(db, force=True, now=NOW)
    finally:
        watchlist.reader_factory = None
    rep = watchlist.record_comparison(db)["report"]
    watchlist._assert_no_content(rep)
    text = json.dumps(rep)
    for item in W.CATALOGUES[SHOP]:
        assert item["title"] not in text and item["description"] not in text
    assert SHOP.lower() not in text.lower() and KEY not in text and "4427559824" not in text


def test_the_readback_row_counts_nine():
    sys.path.insert(0, str(ROOT.parent / "ops"))
    import readback

    assert readback.RESEARCH_SHOPS == len(SE.OWNER_SHOPS) == len(NINE)
    assert readback.COMPETITOR_SCANS_ITEM == (
        "competitor shops scanned (nine-shop research network)")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"PASS: {fails} failing" if not fails else f"FAILED: {fails} failing")
    sys.exit(1 if fails else 0)
