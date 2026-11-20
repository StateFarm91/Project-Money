"""ENG-BENCHBUY: the benchmark shopping list across all nine watchlist shops.

The owner will buy benchmark patterns, with variety from every shop scanned daily, and owner
demand (MadelineMaeCo, baby products, stuffed animals/amigurumi, pillows) counts. What is
tested here is what could go wrong with real money and a competitor's copyright attached:
a list that over-buys one shop, one that blows the budget, one that offers something already
owned, an empty shop that disappears, a path that buys by itself, and a list invented from
scan data that is not there.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import inspect
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (BenchmarkListing, BenchmarkProduct, OperatingReading,  # noqa: E402
                                     OwnerAction)
from brambleloop.intel import benchmark_refresh as BR  # noqa: E402
from brambleloop.intel import purchase_selection as P  # noqa: E402
from brambleloop.intel import watchlist  # noqa: E402
from brambleloop.teardown import intake  # noqa: E402

SHOPS = [m.key for m in watchlist.WATCHLIST]
MADELINE = "madeline_mae_co"
MJS = "mjs_off_the_hook_designs"
_N = [100000]


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _add(db, shop, title, *, price=6.0, pod="hats", kind="download", fav=10, tags=None,
         media=10, ref=None, state="queued"):
    _N[0] += 1
    ref = ref or str(_N[0])
    detail = {"tags": tags if tags is not None else ["crochet pattern"], "num_favorers": fav}
    if kind is not None:
        detail["options"] = {"listing_type": kind}
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=shop, listing_ref=ref, title=title, pod=pod, price_cad=price,
            media_count=media, url=f"https://www.etsy.com/listing/{ref}", detail=detail,
            audit_state=state))
    return ref


def _catalogue(db, per_shop=8):
    """Every shop: eight digital pattern listings that differ in what they teach."""
    words = ["Cardigan sizes", "Beanie in the round", "Mosaic blanket", "Granny square motif",
             "Colourwork chart", "Amigurumi bear", "Baby blanket", "Floor pillow cushion",
             "Scarf flat", "Tapestry bag"]
    for shop in SHOPS:
        for i in range(per_shop):
            _add(db, shop, f"{words[i % len(words)]} {shop} {i} pattern",
                 price=3.0 + 0.5 * i, pod=["garments", "hats", "blankets", "home_decor", "bags",
                                     "amigurumi", "blankets", "home_decor"][i % 8])


def _picks(out):
    return out["to_buy"]


def _count(out, shop):
    return sum(1 for p in out["to_buy"] if p["shop_key"] == shop)


# ---- variety and quotas ---------------------------------------------------------------------

def test_variety_comes_from_every_one_of_the_nine_shops_within_quota():
    db = _db()
    _catalogue(db)
    out = P.shopping_list(db)
    assert out["status"] == "OK" and out["shops_total"] == 9
    assert out["shops_with_picks"] == 9, [(s["shop_name"], s["status"]) for s in out["shops"]]
    for shop in SHOPS:
        cap = 5 if shop == MADELINE else 3
        assert 1 <= _count(out, shop) <= cap, (shop, _count(out, shop))
    assert _count(out, MADELINE) == 5          # her quota is used when she has the demand items
    assert all(_count(out, s) == 3 for s in SHOPS if s != MADELINE)


def test_the_quota_binds_even_when_a_shop_has_far_more_to_teach():
    db = _db()
    for i in range(30):
        _add(db, "zkbdesigner", f"Unique thing {i} pattern", price=3.0, pod="hats" if i % 2 else "bags",
             tags=[f"tag{i}", "pattern"], media=2 + i)
    out = P.shopping_list(db)
    assert _count(out, "zkbdesigner") == 3


def test_no_pick_is_made_without_a_new_facet():
    db = _db()
    for i in range(12):
        _add(db, "ivyloop", "Plain mug rug pattern", price=6.0, pod="home_decor")
    out = P.shopping_list(db)
    assert _count(out, "ivyloop") == 1
    assert out["stopped_because"] == "nothing_left_to_learn"
    for p in out["to_buy"]:
        assert p["new_facets"], p


# ---- the facets: capability gap first, owner demand second, favourites last -------------------

def test_capability_gap_is_covered_before_anything_else_and_demand_ranks_next():
    db = _db()
    gap = _add(db, "ivyloop", "Mosaic cushion pattern", price=9.0, pod="home_decor", fav=1)
    plain = _add(db, "ivyloop", "Zzz plain thing pattern", price=9.0, pod="bags", fav=9999)
    demand = _add(db, "ivyloop", "Baby lovey pattern", price=9.0, pod="education", fav=2)
    out = P.shopping_list(db)
    order = [p["listing_ref"] for p in out["to_buy"]]
    assert order[0] == gap                       # a gap (mosaic) beats 9999 favourites
    assert order.index(demand) < order.index(plain)   # owner demand beats a merely popular one
    first = out["to_buy"][0]
    assert "mosaic tapestry" in first["teaches"] and "pillow cushion" in first["teaches"]


def test_favourites_only_break_a_tie():
    db = _db()
    lo = _add(db, "ivyloop", "Plain bag pattern", price=7.0, pod="bags", fav=3)
    hi = _add(db, "ivyloop", "Plain bag pattern", price=7.0, pod="bags", fav=500)
    out = P.shopping_list(db)
    assert [p["listing_ref"] for p in out["to_buy"]] == [hi]     # identical facets: favourites
    # ... and favourites never beat a facet: the low-favourite listing with a gap wins
    gap = _add(db, "firefly_crochets", "Granny motif pattern", price=7.0, pod="bags", fav=0)
    _add(db, "firefly_crochets", "Plain bag pattern", price=7.0, pod="bags", fav=9000)
    out = P.shopping_list(db)
    assert [p for p in out["to_buy"] if p["shop_key"] == "firefly_crochets"][0]["listing_ref"] == gap
    assert lo not in [p["listing_ref"] for p in out["to_buy"]]


def test_only_pattern_digital_downloads_are_eligible():
    db = _db()
    ok = _add(db, "ivyloop", "Beanie pattern", pod="hats")
    _add(db, "ivyloop", "Finished beanie", kind="physical", pod="hats")
    _add(db, "ivyloop", "Mystery thing pattern", kind=None, pod="bags")
    _add(db, "ivyloop", "Yarn bundle", kind="download", pod="bags", tags=["yarn"])
    _add(db, "ivyloop", "Withdrawn pattern", pod="bags", state="withdrawn")
    out = P.shopping_list(db)
    assert [p["listing_ref"] for p in out["to_buy"]] == [ok]
    ivy = next(s for s in out["shops"] if s["shop_key"] == "ivyloop")
    assert ivy["excluded"] == {"not_digital_download": 1, "digital_status_unknown": 1,
                               "not_a_pattern": 1, "withdrawn": 1}


# ---- budget in code ---------------------------------------------------------------------------

def test_the_budget_is_never_exceeded_and_every_price_shows_the_contingency():
    db = _db()
    _catalogue(db)
    for ceiling in (300.0, 120.0, 40.0, 7.0, 0.0):
        out = P.shopping_list(db, budget_ceiling_cad=ceiling)
        assert out["total_with_contingency_cad"] <= ceiling + 1e-9, (ceiling, out["total_with_contingency_cad"])
        assert out["budget"]["within_budget"] is True
        for p in out["to_buy"]:
            assert p["price_with_contingency_cad"] == round(p["price_cad"] * 1.158, 2)
            assert p["contingency_factor"] == 1.158
    tight = P.shopping_list(db, budget_ceiling_cad=40.0)
    assert tight["stopped_because"] == "budget_exhausted"
    assert tight["budget_excluded"]["shortfall_cad"] > 0


def test_recorded_benchmark_spend_comes_off_the_300_ceiling():
    assert intake.SET_BUDGET_CAD == 300.0
    db = _db()
    _catalogue(db)
    with db.session() as s:
        s.add(BenchmarkProduct(ref="own-1", seller="Someone", title="Other thing", pod="hats",
                               listing_ref="not-a-listing", paid_cad=270.0))
        s.add(BenchmarkProduct(ref="own-2", seller="Someone", title="Unpriced", pod="hats",
                               listing_ref="nope", paid_cad=0.0))
    out = P.shopping_list(db)
    assert out["budget"]["recorded_spend_cad"] == 270.0
    assert out["budget"]["remaining_cad"] == 30.0
    assert out["total_with_contingency_cad"] <= 30.0
    assert out["budget"]["unknown_price_for"] == ["own-2"]     # UNKNOWN, never counted as CA$0
    overspent = P.shopping_list(_db_with_spend(310.0))
    assert overspent["to_buy_count"] == 0 and overspent["budget"]["remaining_cad"] < 0


def _db_with_spend(spend):
    db = _db()
    _catalogue(db, per_shop=2)
    with db.session() as s:
        s.add(BenchmarkProduct(ref="own-x", seller="S", title="x", paid_cad=spend))
    return db


# ---- owned items --------------------------------------------------------------------------------

def test_owned_items_are_excluded_and_bought_picks_keep_their_status():
    db = _db()
    _add(db, MJS, "Mini Star Stitch Cardigan Pattern", pod="garments")
    _add(db, MJS, "Cardigan with Pockets pattern", pod="garments")
    keep = _add(db, MJS, "Baby hat pattern", pod="hats")
    held = _add(db, "ivyloop", "Beanie pattern", pod="hats", ref="777")
    by_title = _add(db, "ivyloop", "Owned elsewhere pattern", pod="bags", ref="778")
    with db.session() as s:
        s.add(BenchmarkProduct(ref="p1", seller="IvyLoop", title="Owned elsewhere pattern",
                               listing_ref="zzz", paid_cad=5.0))
    out = P.shopping_list(db)
    refs = {p["listing_ref"] for p in out["to_buy"]}
    titles = " ".join(p["title"].lower() for p in out["to_buy"])
    assert "cardigan" not in titles                 # both MJ benchmarks
    assert by_title not in refs                     # a BenchmarkProduct row, matched by title
    assert keep in refs and held in refs
    # once bought, it leaves "to buy", stays on the list with its status
    ledger = out["to_buy"]
    with db.session() as s:
        s.add(BenchmarkProduct(ref="ivyloop-777", seller="IvyLoop", title="Beanie pattern",
                               listing_ref="777", paid_cad=6.0, files=[]))
    again = P.shopping_list(db, ledger=ledger)
    assert "777" not in {p["listing_ref"] for p in again["to_buy"]}
    ivy = next(s for s in again["shops"] if s["shop_key"] == "ivyloop")
    assert {p["listing_ref"]: p["status"] for p in ivy["picks"]}["777"] == "bought"
    with db.session() as s:
        row = s.scalar(select(BenchmarkProduct).where(BenchmarkProduct.ref == "ivyloop-777"))
        row.files = [{"name": "a.pdf"}]
    done = P.shopping_list(db, ledger=ledger)
    ivy = next(s for s in done["shops"] if s["shop_key"] == "ivyloop")
    assert {p["listing_ref"]: p["status"] for p in ivy["picks"]}["777"] == "intake done"


# ---- empty shops and missing data ----------------------------------------------------------------

def test_an_empty_shop_is_visible_with_its_reason():
    db = _db()
    _add(db, "ivyloop", "Beanie pattern")
    _add(db, "zkbdesigner", "Finished hat", kind="physical")
    _add(db, "hanjan_crochet", "Plain pattern", pod="bags")
    out = P.shopping_list(db)
    by = {s["shop_key"]: s for s in out["shops"]}
    assert len(out["shops"]) == 9                           # every shop is listed, never dropped
    assert by["zkbdesigner"]["status"] == "EMPTY"
    assert "not a digital download" in by["zkbdesigner"]["reason"]
    assert by[MADELINE]["status"] == "UNKNOWN"
    assert "no scanned listings" in by[MADELINE]["reason"]
    assert by["ivyloop"]["status"] == "PICKED"


def test_unknown_when_scan_data_is_missing_and_no_card_is_raised():
    db = _db()
    out = P.shopping_list(db)
    assert out["status"] == "UNKNOWN" and out["to_buy"] == []
    assert "no watchlist shop has scanned listings" in out["reason"]
    assert all(s["status"] == "UNKNOWN" for s in out["shops"])
    got = BR.refresh_shopping(db, today=date(2026, 11, 20))
    assert got["status"] == "UNKNOWN"
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == P.OWNER_CARD_KEY)) is None
    # a listing whose digital status was never observed is UNKNOWN, not assumed a download
    db2 = _db()
    _add(db2, "ivyloop", "Beanie pattern", kind=None)
    out2 = P.shopping_list(db2)
    assert out2["to_buy"] == []
    assert next(s for s in out2["shops"] if s["shop_key"] == "ivyloop")["excluded"] == {
        "digital_status_unknown": 1}


# ---- the daily refresh and the one owner card ----------------------------------------------------

def test_one_consolidated_owner_card_and_a_quiet_second_day():
    db = _db()
    _catalogue(db, per_shop=4)
    day = date(2026, 11, 20)
    got = BR.refresh_shopping(db, today=day)
    n, cost = got["to_buy_count"], got["total_with_contingency_cad"]
    assert got["card"]["state"] == "raised" and got["changed"] is True
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("benchmark_shopping:%"), OwnerAction.done == False)))  # noqa: E712
    assert len(rows) == 1
    assert rows[0].action == f"Buy {n} benchmark patterns, ≤ CA${cost:.2f}"
    assert rows[0].max_cost_cad == cost <= intake.SET_BUDGET_CAD
    again = BR.refresh_shopping(db, today=day)           # same data: restated, not duplicated
    assert again["card"]["state"] == "restated" and again["changed"] is False
    with db.session() as s:
        assert len(list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("benchmark_shopping:%"))))) == 1
        assert len(list(s.scalars(select(OperatingReading).where(
            OperatingReading.kind == P.SHOPPING_KIND)))) == 1


def test_the_card_closes_when_nothing_is_left_to_buy():
    db = _db()
    _add(db, "ivyloop", "Beanie pattern")
    BR.refresh_shopping(db, today=date(2026, 11, 20))
    with db.session() as s:
        for row in s.scalars(select(BenchmarkListing)):
            row.audit_state = "withdrawn"
    got = BR.refresh_shopping(db, today=date(2026, 11, 21))
    assert got["card"]["state"] == "closed" and got["to_buy_count"] == 0


def test_the_loop_is_registered_daily_free_and_reads_after_the_scans():
    from brambleloop.runtime import worker
    from brambleloop.swarm import orchestrate

    cad = {c[2]: c for c in worker.CADENCES} if hasattr(worker, "CADENCES") else None
    if cad is None:                                   # name differs: find the tuple by job type
        cad = {}
        for name in dir(worker):
            val = getattr(worker, name)
            if isinstance(val, tuple) and val and isinstance(val[0], tuple) and len(val[0]) == 4:
                cad.update({c[2]: c for c in val})
    assert cad["intel.benchmark_shopping"][3] == 24 * 60 * 60
    assert "intel.benchmark_shopping" in orchestrate.FREE_JOB_TYPES
    assert orchestrate.UPSTREAM_INPUTS["intel.benchmark_shopping"] == (
        "intel.watchlist_scan", "mjs.scan")


# ---- safety: no purchase path -----------------------------------------------------------------------

def test_no_auto_purchase_path_exists():
    src = inspect.getsource(P) + inspect.getsource(BR.refresh_shopping)
    for forbidden in ("import requests", "import httpx", "urllib", "etsy_public", "http.client",
                      "socket", "checkout", "def buy", "def purchase", "stripe", "paypal",
                      "enqueue"):
        assert forbidden not in src, forbidden
    # the whole selection runs with the network switched off
    import socket

    real = socket.socket

    def boom(*a, **k):
        raise AssertionError("the shopping list touched the network")

    socket.socket = boom
    try:
        db = _db()
        _catalogue(db, per_shop=3)
        BR.refresh_shopping(db, today=date(2026, 11, 20))
    finally:
        socket.socket = real
    out = P.shopping_list(db)
    assert "Nothing is bought automatically" in out["not_a_purchase"]
    # the only reader of a purchased file is the quarantined intake; nothing in the list
    # touches the library
    assert "library" not in inspect.getsource(P.shopping_list)


def test_a_purchase_from_another_shop_enters_only_through_the_quarantined_intake():
    import tempfile

    from brambleloop.teardown import library

    db = _db()
    ref = _add(db, "ivyloop", "Beanie pattern", pod="hats", ref="555")
    with tempfile.TemporaryDirectory() as tmp:
        env = {library.LIBRARY_ENV: tmp}
        got = intake.receive(db, ref, [("pattern.pdf", b"%PDF-1.4 synthetic")], env=env,
                             mirror_files=False)
        assert got
        row = db.session().__enter__().scalar(select(BenchmarkProduct))
        assert row.ref == "ivyloop-555" and row.seller == "IvyLoop"
        assert (Path(tmp) / "ivyloop-555" / "pattern.pdf").exists()


# ---- the Mission Control read model ---------------------------------------------------------------

def test_the_insights_panel_groups_by_shop_with_the_real_listing_url_and_status():
    from brambleloop.app.command_center import tabs

    db = _db()
    assert tabs.benchmark_shopping(db)["status"] == "UNKNOWN"          # not built yet
    _catalogue(db, per_shop=3)
    _add(db, "zkbdesigner", "Finished hat", kind="physical", ref="9001")
    BR.refresh_shopping(db, today=date(2026, 11, 20))
    panel = tabs.benchmark_shopping(db)
    assert panel["status"] == "OK" and len(panel["groups"]) == 9
    assert panel["owner_card"]["action"] == (
        f"Buy {panel['to_buy_count']} benchmark patterns, \u2264 CA${panel['total_with_contingency_cad']:.2f}")
    for g in panel["groups"]:
        assert g["status"] in ("PICKED", "EMPTY", "UNKNOWN") and g["reason"]
        for p in g["picks"]:
            assert p["url"].startswith("https://www.etsy.com/listing/")
            assert p["price_cad"] and p["price_with_contingency_cad"] and p["teaches"]
            assert p["answers"] and p["status"] == "to buy"
    assert tabs.insights(db)["sections"]["benchmark_shopping"]["status"] == "OK"


def test_the_panel_offers_no_purchase_control():
    js = (ROOT / "src/brambleloop/app/command_center/static/js/views/insights.js").read_text()
    for control in ('h("button"', 'h("form"', 'h("input"', "onclick", "fetch(", "api.post", "method:"):
        assert control not in js, control
    py = inspect.getsource(sys.modules["brambleloop.app.command_center.tabs"].benchmark_shopping)
    assert "refresh_shopping" not in py and "shopping_list(" not in py      # reads the stored list


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"{'FAILED' if fails else 'ALL PASSED'}")
    sys.exit(1 if fails else 0)
