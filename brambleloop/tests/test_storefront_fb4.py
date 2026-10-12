"""Storefront launch surfaces: shop SEO (F-236), opening grid (F-238), pre-launch preview
(F-239/F-293) and seller identity (F-240).

Each test builds the state it judges in a throwaway SQLite database. No network, no model.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_storefront_fb4.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import sys
import tempfile
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import seller_identity, storefront  # noqa: E402
from brambleloop.brand import storefront_preview as sp  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Listing, ListingAsset, ListingSetCertificateRecord, OperatingReading, PatternVersion,
    Product,
)
from brambleloop.gates.certificate import GAUGE_STANDARD  # noqa: E402

TODAY = date(2026, 11, 2)


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def _product(db, slug, price, *, version="1.0.0", hero="deterministic_render",
             listed=True, granted=True):
    with db.session() as s:
        p = Product(slug=slug, title=slug.replace("-", " ").title())
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=version, cir_json={}, certified=True,
                             certificate={"granted": granted,
                                          "gauge_standard": GAUGE_STANDARD if granted else ""}))
        if listed:
            s.add(Listing(product_slug=slug, version=version, title=f"{slug} crochet pattern",
                          description="d", tags=[], price_cad=price))
            s.add(ListingAsset(product_slug=slug, version=version, position=1,
                               asset_class=hero, role="hero", sha256="a" * 64, approved=True))


def _inventory(*slugs, failing=()):
    rows = [{"slug": s, "failing": []} for s in slugs]
    rows += [{"slug": s, "failing": ["gauge_standard"]} for s in failing]
    return {"cleared_slugs": list(slugs), "products": rows}


def _takeover(db, event="Christmas"):
    with db.session() as s:
        s.add(OperatingReading(kind="storefront.takeover", period_key=f"{event}:banner",
                               payload={"state": "applied", "event": event, "surface": "banner",
                                        "change": f"{event} makes, checked row by row.",
                                        "reverts_on": (TODAY + timedelta(days=30)).isoformat()}))


# ---- F-236: shop SEO -------------------------------------------------------------------

def test_the_drafted_storefront_passes_its_seo_check():
    store = storefront.build_storefront()
    assert store.tagline, "the tagline is carried onto the storefront"
    assert storefront.check_shop_seo(store) == []
    assert store.problems == []


def test_a_stuffed_tagline_fails():
    store = replace(storefront.build_storefront(),
                    tagline="Crochet Pattern Crochet Blanket Crochet Throw Pattern")
    problems = storefront.check_storefront(store)
    assert any(p.startswith("STORE_SEO_STUFFED") and "tagline" in p for p in problems), problems


def test_a_category_silent_tagline_fails():
    store = replace(storefront.build_storefront(),
                    tagline="Quietly beautiful things for slow evenings")
    problems = storefront.check_shop_seo(store)
    assert any(p.startswith("STORE_SEO_CATEGORY_SILENT") and "tagline" in p
               for p in problems), problems


def test_a_keyword_stuffed_about_fails_and_readiness_reads_it():
    stuffed = storefront.ABOUT + "\n\n" + " ".join(["crochet pattern"] * 40)
    store = replace(storefront.build_storefront(), about=stuffed)
    assert any("STORE_SEO_STUFFED" in p and "About" in p
               for p in storefront.check_storefront(store))
    listy = storefront.ABOUT + "\n\nblanket, throw, afghan, crochet, pattern, pdf, easy"
    store = replace(storefront.build_storefront(), about=listy)
    assert any(p.startswith("STORE_SEO_KEYWORD_LIST") for p in storefront.check_shop_seo(store))
    # launch readiness consumes check_storefront, so the SEO check is on the launch gate
    import inspect

    from brambleloop.launch import readiness

    assert "check_storefront(build_storefront(db=db))" in inspect.getsource(readiness.assess)


# ---- F-238: the opening grid -----------------------------------------------------------

def test_the_opening_grid_refuses_uncleared_and_legacy_filler():
    db = _db()
    _product(db, "heirloom-cable-blanket", 11.50)
    _product(db, "cloudline-baby-blanket", 8.50)
    _product(db, "cottage-wall-hanging", 10.50, granted=False)   # legacy, uncleared
    _product(db, "autumn-oak-mosaic-throw", 12.50)                    # not launch-cleared
    grid = storefront.opening_grid(
        db, today=TODAY,
        inventory=_inventory("heirloom-cable-blanket", "cloudline-baby-blanket",
                             "cottage-wall-hanging", failing=("autumn-oak-mosaic-throw",)))
    shown = {t["slug"] for t in grid["tiles"]}
    assert shown == {"heirloom-cable-blanket", "cloudline-baby-blanket"}, shown
    why = {e["slug"]: e["why"] for e in grid["excluded"]}
    assert why["cottage-wall-hanging"].startswith("legacy filler")
    assert why["autumn-oak-mosaic-throw"].startswith("not launch-cleared")


def test_season_first_then_strongest_first_with_the_basis_labelled():
    db = _db()
    for slug, price in (("heirloom-cable-blanket", 11.50), ("cloudline-baby-blanket", 8.50),
                        ("nordic-forest-stocking", 7.50), ("nordic-forest-basket", 6.50)):
        _product(db, slug, price)
    _takeover(db, "Christmas")
    grid = storefront.opening_grid(db, today=TODAY, inventory=_inventory(
        "heirloom-cable-blanket", "cloudline-baby-blanket", "nordic-forest-stocking",
        "nordic-forest-basket"))
    order = [t["slug"] for t in grid["tiles"]]
    assert order[0] == "nordic-forest-stocking", order          # the live season leads
    assert grid["active_events"] == ["Christmas"]
    rest = grid["tiles"][1:]
    values = [t["strength"]["value"] for t in rest]
    assert values == sorted(values, reverse=True), values         # then strongest first
    assert all(t["strength"]["basis"] == "prior" for t in grid["tiles"])


def test_the_first_screen_shows_more_than_one_price_rung():
    db = _db()
    slugs = ["heirloom-cable-blanket", "cloudline-baby-blanket", "nordic-forest-stocking",
             "nordic-forest-basket", "autumn-oak-mosaic-throw", "winter-village-graphghan",
             "nordic-forest-mosaic-throw"]
    for slug in slugs:
        _product(db, slug, 9.00)                                   # all premium
    _product(db, "no-sew-reindeer", 4.50)                          # one entry rung
    grid = storefront.opening_grid(db, today=TODAY,
                                   inventory=_inventory(*slugs, "no-sew-reindeer"))
    window = grid["visible"]
    assert len(window) == storefront.OPENING_GRID_VISIBLE
    assert len({t["tier"] for t in window}) >= 2, [t["tier"] for t in window]
    assert "OPENING_GRID_LADDER_FLAT" not in " ".join(grid["problems"])


def test_an_empty_grid_and_an_unjudgeable_grid_are_not_ready():
    db = _db()
    grid = storefront.opening_grid(db, today=TODAY, inventory=_inventory())
    assert not grid["ok"] and grid["problems"][0].startswith("OPENING_GRID_EMPTY")
    assert grid["coherence"]["status"] == "UNMEASURED"
    # a product with no CIR palette cannot be judged as part of a coherent grid
    _product(db, "nordic-forest-stocking", 7.50)
    grid = storefront.opening_grid(db, today=TODAY,
                                   inventory=_inventory("nordic-forest-stocking"))
    assert grid["coherence"]["status"] == "UNMEASURED"
    assert not grid["ok"]


def test_grid_coherence_is_run_on_the_visible_window():
    db = _db()
    _product(db, "cloudline-baby-blanket", 8.50)
    _product(db, "winter-village-graphghan", 10.50)
    grid = storefront.opening_grid(db, today=TODAY, inventory=_inventory(
        "cloudline-baby-blanket", "winter-village-graphghan"))
    assert grid["coherence"]["status"] == "MEASURED", grid["coherence"]
    assert grid["coherence"]["ok"] is True, grid["coherence"]
    # mixed hero treatments in the first screen are flagged by bible.check_grid_coherence
    db2 = _db()
    _product(db2, "cloudline-baby-blanket", 8.50, hero="deterministic_render")
    _product(db2, "winter-village-graphghan", 10.50, hero="ai_lifestyle_concept")
    grid = storefront.opening_grid(db2, today=TODAY, inventory=_inventory(
        "cloudline-baby-blanket", "winter-village-graphghan"))
    assert any("BRAND_HERO_INCONSISTENT" in p for p in grid["problems"]), grid["problems"]


def test_readiness_registers_the_new_storefront_requirements():
    from brambleloop.launch import readiness

    db = _db()
    reqs = {r.key: r for r in readiness._storefront_items(db)}
    assert set(reqs) == {"opening_grid", "storefront_preview", "seller_identity"}
    assert reqs["opening_grid"].ready is False and reqs["opening_grid"].blocked_by == "build"
    assert reqs["storefront_preview"].ready is False
    live = reqs["storefront_preview"].evidence["live_inspection"]
    assert live["status"] == "EXTERNAL_GATED" and live["passed"] is False
    assert reqs["seller_identity"].ready is False
    assert reqs["seller_identity"].blocked_by == "owner"


# ---- F-239 / F-293: the preview --------------------------------------------------------

def test_the_simulated_icon_is_legible_at_40_and_70_px():
    icon = sp.render_icon()
    for size in sp.ICON_SIZES:
        r = sp.icon_legibility(icon, size)
        assert r["ok"], r
        assert r["contrast"] >= sp.ICON_MIN_CONTRAST
    from PIL import Image

    faint = Image.new("RGB", (500, 500), sp._rgb("cream"))
    r = sp.icon_legibility(faint, 40)
    assert not r["ok"] and any("contrast" in p for p in r["problems"])


def test_a_wordmark_at_the_left_edge_is_cut_by_the_phone_crop():
    crops = sp.banner_crops()
    assert crops["phone"]["ok"] and crops["desktop"]["ok"], crops
    left = sp.banner_crops(box=(100, 150, 600, 250))
    assert left["desktop"]["ok"]
    assert not left["phone"]["ok"]
    assert "safe area" in left["phone"]["problems"][0]
    tiny = sp.banner_crops(box=(700, 190, 900, 210))
    assert any("tall" in p for p in tiny["phone"]["problems"])


def test_the_announcement_opening_must_fit_a_phone():
    ok = sp.announcement_opening(storefront.ANNOUNCEMENT_TEMPLATES["Christmas"])
    assert ok["ok"], ok
    long = sp.announcement_opening("A very long opening sentence that keeps going " * 4)
    assert not long["ok"] and long["truncated"]
    assert not long["shown"].endswith(" ")


def test_the_preview_uses_certified_frames_and_never_claims_live_inspection():
    from PIL import Image

    from brambleloop.core.artifacts import ArtifactStore

    db = _db()
    root = tempfile.mkdtemp(prefix="fb4_preview_")
    store = ArtifactStore(root)
    slugs = ["cloudline-baby-blanket", "winter-village-graphghan", "autumn-oak-mosaic-throw",
             "hexagon-coaster-set"]
    for n, slug in enumerate(slugs):
        _product(db, slug, 8.0 + n)
        buf = io.BytesIO()
        Image.new("RGB", (400, 400), (36, 74, 58)).save(buf, format="PNG")
        sha = store.put(f"{slug}/hero.png", buf.getvalue(), "image/png").sha256
        if slug != "hexagon-coaster-set":
            with db.session() as s:
                s.add(ListingSetCertificateRecord(
                    product_slug=slug, version="1.0.0", state="valid",
                    certificate={"frames": [{"position": 1, "sha256": sha, "job": "hero"}]}))
    grid = storefront.opening_grid(db, today=TODAY, inventory=_inventory(*slugs))
    view = sp.preview(db, grid=grid, store_root=root)
    status = {t["slug"]: t["status"] for t in view["tiles"]}
    assert status["hexagon-coaster-set"] == "not_certified", status
    assert sum(1 for v in status.values() if v == "rendered") == 3
    assert not view["ok"]                       # a phone's first screen needs four
    assert view["icon"]["basis"] == sp.SIMULATED
    assert view["live_inspection"]["status"] == "EXTERNAL_GATED"
    assert view["live_inspection"]["passed"] is False
    assert view["grid_render_sha256"]["phone_grid"]


# ---- F-240: seller identity ------------------------------------------------------------

def test_legal_identity_is_unknown_and_never_invented():
    st = seller_identity.state()
    assert all(f["legal"] == seller_identity.UNKNOWN for f in st["fields"])
    assert set(st["undetermined"]) == {f.key for f in seller_identity.fields()}
    assert st["problems"] == [] and st["complete"] is False
    invented = tuple(replace(f, legal="Jane Example") if f.key == "name" else f
                     for f in seller_identity.fields())
    problems = seller_identity.check_identity(invented)
    assert any(p.startswith("IDENTITY_LEGAL_UNCONFIRMED") for p in problems), problems


def test_an_unsourced_difference_is_refused_and_a_cited_one_must_be_on_file():
    confirmed = tuple(
        replace(f, legal="J. Owner", legal_source="owner_confirmed_at_kyc:2026-11-01")
        if f.key == "name" else f for f in seller_identity.fields())
    problems = seller_identity.check_identity(confirmed)
    assert any(p.startswith("IDENTITY_DIFFERENCE_UNSOURCED") for p in problems), problems
    # citing a rule the repository never read is refused too
    problems = seller_identity.check_identity(confirmed,
                                              {"name": ("seller_policy", "shop_names_free")})
    assert any(p.startswith("IDENTITY_RULE_NOT_ON_FILE") for p in problems), problems
    # a rule that is on file makes the difference PERMITTED (the mechanism, not a claim that
    # this particular rule covers names -- no reading on file does)
    rows = seller_identity.compare(confirmed, {"name": ("seller_policy", "shop_policies")})
    assert next(r for r in rows if r["key"] == "name")["state"] == seller_identity.PERMITTED


def test_the_storefront_check_refuses_a_stale_identity():
    store = replace(storefront.build_storefront(), shop_name="Some Other Studio")
    assert any(p.startswith("IDENTITY_STALE") for p in storefront.check_storefront(store))


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
