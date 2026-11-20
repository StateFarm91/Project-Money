"""W4-CATALOG: the shop's first screen shows each product once, at its current release.

Production (0417f35, /api/launch opening_grid, 2026-10-11) read `ready: true` with
`visible: [nordic-star-ornaments, nordic-star-ornaments, cloudline-baby-blanket,
cloudline-baby-blanket, autumn-oak-mosaic-throw, pressed-flower-motifs]`: two listing rows per
product (1.0.0 beside its re-engineered 1.4.0 / 1.2.0), because `brand.storefront.opening_grid`
made one tile per listing row and `legacy_status` clears a Launch-0 slug at any version. The
older tile sold a release the company had replaced. The grid now keeps the newest certified
version of each product and reports the older listing as superseded.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_catalog_reconciliation.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import storefront  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Listing, ListingAsset, PatternVersion, Product  # noqa: E402
from brambleloop.gates.certificate import GAUGE_STANDARD  # noqa: E402

TODAY = date(2026, 10, 11)
FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def _release(db, slug, version, price, *, listed=True):
    with db.session() as s:
        from sqlalchemy import select

        p = s.scalar(select(Product).where(Product.slug == slug))
        if p is None:
            p = Product(slug=slug, title=slug.replace("-", " ").title())
            s.add(p)
            s.flush()
        s.add(PatternVersion(product_id=p.id, version=version, cir_json={}, certified=True,
                             certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
        if listed:
            s.add(Listing(product_slug=slug, version=version, title=f"{slug} {version}",
                          description="d", tags=[], price_cad=price))
            s.add(ListingAsset(product_slug=slug, version=version, position=1,
                               asset_class="deterministic_render", role="hero",
                               sha256="a" * 64, approved=True))


def _inventory(*slugs):
    return {"cleared_slugs": list(slugs), "products": [{"slug": s, "failing": []}
                                                       for s in slugs]}


def test_a_product_listed_at_two_releases_shows_once_at_the_current_one():
    db = _db()
    _release(db, "cloudline-baby-blanket", "1.0.0", 7.5)
    _release(db, "cloudline-baby-blanket", "1.2.0", 7.5)
    _release(db, "nordic-star-ornaments", "1.0.0", 4.5)
    _release(db, "nordic-star-ornaments", "1.4.0", 4.5)
    grid = storefront.opening_grid(db, today=TODAY, inventory=_inventory(
        "cloudline-baby-blanket", "nordic-star-ornaments"))
    shown = [(t["slug"], t["version"]) for t in grid["tiles"]]
    assert len(shown) == 2, shown
    assert sorted(shown) == [("cloudline-baby-blanket", "1.2.0"),
                             ("nordic-star-ornaments", "1.4.0")], shown
    superseded = {(x["slug"], x["version"]) for x in grid["excluded"]
                  if x["why"].startswith("superseded")}
    assert superseded == {("cloudline-baby-blanket", "1.0.0"),
                          ("nordic-star-ornaments", "1.0.0")}, grid["excluded"]


def test_distinct_products_are_untouched():
    db = _db()
    for slug, price in (("cloudline-baby-blanket", 7.5), ("nordic-star-ornaments", 4.5),
                        ("hexagon-coaster-set", 4.0)):
        _release(db, slug, "1.2.0", price)
    grid = storefront.opening_grid(db, today=TODAY, inventory=_inventory(
        "cloudline-baby-blanket", "nordic-star-ornaments", "hexagon-coaster-set"))
    assert len(grid["tiles"]) == 3, grid["tiles"]
    assert not grid["excluded"], grid["excluded"]


def test_the_owner_preview_reads_the_listing_of_the_current_release_only():
    # Production holds nordic-star-ornaments 1.0.0 ("Nordic Star Ornament Set (6)") beside
    # 1.4.0. A superseded row with the higher id must not name or price the current product.
    from brambleloop.products import launch0 as l0
    from brambleloop.store_foundation.content import launch0_products

    cur = l0.cir_for("snowflake_ornaments")
    assert cur.version != "1.0.0"
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug=cur.slug, version=cur.version, title="CURRENT RELEASE",
                      description="d", tags=[], price_cad=4.5))
        s.flush()
        s.add(Listing(product_slug=cur.slug, version="1.0.0", title="SUPERSEDED RELEASE",
                      description="d", tags=[], price_cad=9.99))
    rows = {r["candidate"]: r for r in launch0_products(db)}
    row = rows["nordic-star-ornaments"]
    assert row["title"] == "CURRENT RELEASE", row["title"]
    assert row["price_cad"] == 4.5, row["price_cad"]
    # With only the superseded row stored it is still read, but it says which release it is.
    db2 = _db()
    with db2.session() as s:
        s.add(Listing(product_slug=cur.slug, version="1.0.0", title="SUPERSEDED RELEASE",
                      description="d", tags=[], price_cad=9.99))
    row2 = {r["candidate"]: r for r in launch0_products(db2)}["nordic-star-ornaments"]
    assert "superseded_release=1.0.0" in row2["title_basis"], row2["title_basis"]
    assert f"current {cur.version}" in row2["price_basis"], row2["price_basis"]
    from brambleloop.store_foundation import content as C, readiness as R

    surf = C.build(db2)
    codes = [f["code"] for f in R._check_opening_grid(surf["opening_grid"])]
    assert "TITLE_FROM_SUPERSEDED_RELEASE" in codes, codes


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
