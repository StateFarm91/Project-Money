"""W4-L0PACKET: the Launch-0 product readiness packet is generated from the gates, per release.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_l0_product_readiness.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Listing, PatternVersion, Product  # noqa: E402
from brambleloop.gates.certificate import GAUGE_STANDARD  # noqa: E402
from brambleloop.launch import product_readiness as PR  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402

FAILS = 0
_PACKET = {}


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


def _empty_packet() -> dict:
    if not _PACKET:
        _PACKET.update(PR.build(_db(), inventory={"cleared_slugs": [], "products": []}))
    return _PACKET


def test_the_packet_covers_the_eight_launch0_products_and_every_release():
    p = _empty_packet()
    assert [x["candidate"] for x in p["products"]] == list(l0.LAUNCH0_SLUGS)
    assert p["product_count"] == len(l0.LAUNCH0_SLUGS) == 8
    rels = [r["cir_slug"] for x in p["products"] for r in x["releases"]]
    assert len(rels) == 10 and len(set(rels)) == 10, rels
    for x in p["products"]:
        assert x["releases"], x["candidate"]
        for r in x["releases"]:
            assert set(r["gates"]) == set(PR.GATES), r["gates"].keys()


def test_nothing_is_ready_on_an_empty_database_and_each_gap_names_an_owner():
    p = _empty_packet()
    assert p["products"]
    for x in p["products"]:
        assert x["ready_to_request_publication"] is False, x["candidate"]
        assert x["gates"]["certification"] == PR.FAIL
        assert x["remaining"], x["candidate"]
        for item in x["remaining"]:
            assert item["owner"] in (PR.COMPANY, PR.OWNER, PR.EXTERNAL), item
            assert item["remaining"], item
    assert p["publishes_anything"] is False


def test_product_truth_is_computed_now_and_passes_for_every_launch0_product():
    p = _empty_packet()
    assert p["products"]
    for x in p["products"]:
        assert x["gates"]["product_truth"] == PR.PASS, x["candidate"]
        for r in x["releases"]:
            assert r["gates"]["product_truth"]["physically_calibrated"] is False


def test_cap1_additions_are_labelled_as_not_approved_products():
    p = _empty_packet()
    scopes = {x["candidate"]: x["scope"] for x in p["products"]}
    assert scopes
    for slug in l0.PROPOSED_SLUGS:
        assert "CAP-1" in scopes[slug] and "not approved" in scopes[slug], scopes[slug]
    assert scopes["cloudline-baby-blanket"] == "Launch-0"


def _store(db, cir, *, price, bound=True):
    with db.session() as s:
        p = Product(slug=cir.slug, title=cir.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash="r" * 64,
                             certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
        s.add(Listing(product_slug=cir.slug, version=cir.version, title=cir.title,
                      description="d", tags=[], price_cad=price,
                      release_hash=("r" * 64) if bound else "other"))


def _release_row(p, cir_slug):
    for x in p["products"]:
        for r in x["releases"]:
            if r["cir_slug"] == cir_slug:
                return r
    raise KeyError(cir_slug)


def test_an_off_plan_listing_price_fails_the_price_gate_and_the_plan_passes():
    cir = l0.cir_for("placemat_pair")
    db = _db()
    _store(db, cir, price=9.50)
    r = _release_row(PR.build(db, inventory={"cleared_slugs": [], "products": []}), cir.slug)
    g = r["gates"]["price_plan"]
    assert g["state"] == PR.FAIL and g["owner"] == PR.COMPANY, g
    assert g["plan_cad"] == 5.00 and g["listing_cad"] == 9.50, g
    db2 = _db()
    _store(db2, cir, price=5.00)
    r2 = _release_row(PR.build(db2, inventory={"cleared_slugs": [], "products": []}), cir.slug)
    assert r2["gates"]["price_plan"]["state"] == PR.PASS, r2["gates"]["price_plan"]


def test_listing_readiness_needs_a_bound_listing_and_launch_clearance():
    cir = l0.cir_for("snowflake_ornaments")
    db = _db()
    _store(db, cir, price=4.50, bound=False)
    inv = {"cleared_slugs": [cir.slug], "products": [{"slug": cir.slug, "failing": []}]}
    g = _release_row(PR.build(db, inventory=inv), cir.slug)["gates"]["listing_readiness"]
    assert g["state"] == PR.FAIL and "not bound" in g["why"], g
    db2 = _db()
    _store(db2, cir, price=4.50)
    g2 = _release_row(PR.build(db2, inventory={"cleared_slugs": [], "products": [
        {"slug": cir.slug, "failing": ["usable_listing_asset"]}]}), cir.slug)
    assert g2["gates"]["listing_readiness"]["state"] == PR.FAIL
    assert "usable_listing_asset" in g2["gates"]["listing_readiness"]["why"]
    g3 = _release_row(PR.build(db2, inventory=inv), cir.slug)["gates"]["listing_readiness"]
    assert g3["state"] == PR.PASS, g3


def test_a_missing_category_is_company_matcher_work_and_unknown_is_never_pass():
    # W4-FIRSTSALE: re-attributed from owner to company on production evidence -- the daily
    # etsy.taxonomy_refreshed rows (2026-10-17..20) read 3065 nodes with the keystring already
    # configured and credential_refused=false; what remains is the company's matcher.
    ev = {"search": {"state": "FAIL", "why": "search certificate refuses",
                     "reasons": ["search certificate (F-005): category UNKNOWN -- no stored "
                                 "Etsy taxonomy snapshot"]}}
    g = PR._seo(ev)
    assert g["state"] == PR.FAIL and g["owner"] == PR.COMPANY and "matcher" in g["remaining"]
    assert PR._row("PASSING", "x")["state"] == PR.UNKNOWN
    assert PR._worst([PR.PASS, PR.UNKNOWN]) == PR.UNKNOWN
    assert PR._worst([PR.PASS, PR.FAIL, PR.UNKNOWN]) == PR.FAIL
    assert PR._worst([]) == PR.UNKNOWN
    assert PR._image_truth({})["state"] == PR.UNKNOWN


def test_the_markdown_names_every_product_and_gate():
    p = _empty_packet()
    md = PR.render_markdown(p)
    assert p["products"]
    for x in p["products"]:
        assert x["candidate"] in md
    for g in PR.GATES:
        assert g in md


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
