"""W4-CAP1: the placemat's price is its Launch-0 plan (CA$5.00), not production's CA$9.50.

Production (/api/catalogue, 0417f35) holds `mosaic-placemat-pair@1.3.0` (release b2cd736f0f34)
as a draft listing at CA$9.50. It was priced before the placemat joined Launch-0, on the
generic path: `release.CATEGORY_BANDS_CAD` has no "placemat" band, so it fell to the
unsourced `DEFAULT_BAND` (4.50-9.50) and landed on its ceiling. The Launch-0 plan prices it at
CA$5.00 on the SOURCED CA$4-12 crochet-pattern cluster (`products.launch0.price_plan`), which
PT-04 makes the price of record for a Launch-0 product. Now that CAP-1 put it in Launch-0:
pricing.position prices it from the plan, and a stored listing off-plan is refused at
publication and reported on the store grid. Nothing is written to Etsy.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_cap1_placemat_price.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Listing  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.publish import release_gates as rg  # noqa: E402
from brambleloop.runtime import release  # noqa: E402

SLUG = "mosaic-placemat-pair"
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


def test_the_plan_price_is_sourced_and_inside_its_band():
    lp = l0.launch_price(SLUG)
    assert lp is not None and lp["price_cad"] == 5.00, lp
    assert lp["within_plan_band"] and lp["band_cad"] == (4.0, 12.0), lp
    assert l0.candidate(SLUG).price.basis == l0.SOURCED


def test_the_cause_of_9_50_was_the_unsourced_default_band():
    assert "placemat" not in release.CATEGORY_BANDS_CAD
    assert release.DEFAULT_BAND[1] == 9.50
    # Since CAP-1 the release chain takes the Launch-0 path for it (PT-04), never that band.
    rec = release._product_record(SLUG, {"slug": SLUG})
    assert rec is not None and rec["launch0"] is True, rec


def test_an_off_plan_listing_is_drift_and_the_plan_matches():
    assert rg.launch_price_check(SLUG, 9.50)["state"] == "DRIFT"
    assert rg.launch_price_check(SLUG, 5.00)["state"] == "MATCH"
    assert rg.launch_price_check(SLUG, None)["state"] == "NO_LISTING"
    assert rg.launch_price_check("pet-snuggle-mat", 7.50)["state"] == "NOT_APPLICABLE"


def test_publication_refuses_the_off_plan_listing():
    version = l0.cir_for("placemat_pair").version
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version=version, title="Diamond Lattice Placemat Pair",
                      description="d", tags=[], price_cad=9.50))
    g = rg.for_publish(db, slug=SLUG, version=version, store_root=tempfile.mkdtemp(),
                       read_only=True)
    drift = [r for r in g["reasons"] if r.startswith("LISTING_PRICE_NOT_PLAN")]
    assert len(drift) == 1 and "CA$9.50" in drift[0] and "CA$5.00" in drift[0], g["reasons"]
    db2 = _db()
    with db2.session() as s:
        s.add(Listing(product_slug=SLUG, version=version, title="Diamond Lattice Placemat Pair",
                      description="d", tags=[], price_cad=5.00))
    g2 = rg.for_publish(db2, slug=SLUG, version=version, store_root=tempfile.mkdtemp(),
                        read_only=True)
    assert not [r for r in g2["reasons"] if r.startswith("LISTING_PRICE_NOT_PLAN")]


def test_the_store_grid_reports_the_drift():
    from brambleloop.store_foundation import content as C, readiness as R

    version = l0.cir_for("placemat_pair").version
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version=version, title="Diamond Lattice Placemat Pair",
                      description="d", tags=[], price_cad=9.50))
    surf = C.build(db)
    row = next(p for p in surf["opening_grid"].value if p["candidate"] == SLUG)
    assert row["price_cad"] == 9.50 and row["plan_price_cad"] == 5.00, row
    found = [f for f in R._check_opening_grid(surf["opening_grid"])
             if f["code"] == "LISTING_PRICE_NOT_PLAN"]
    assert len(found) == 1 and SLUG in found[0]["detail"], found


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
