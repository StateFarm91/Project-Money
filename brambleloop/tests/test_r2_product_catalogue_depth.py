"""R2 / J-product P-2: launch.readiness catalogue_depth counts PRODUCTS, not sizes.

Launch-0 is three products (one basket in three sizes, a coaster set, a blanket) and five
in-scope CIR slugs. The launch gate counted 5 certified versions against the floor of 8 while
store_foundation counted 3 products; the owner directive is not to count sizes as separate
products unless the Master defines them that way, and it does not. The floor is unchanged.
Repro: research/final_build/audit_ddf9c6e/j_product_depth.py.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_product_catalogue_depth.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import tempfile

from _r2_harness import run

os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", tempfile.mkdtemp(prefix="r2depth_"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import PatternVersion, Product  # noqa: E402
from brambleloop.launch import readiness as R  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402


def _db_with(slugs) -> Database:
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for slug in slugs:
            p = Product(slug=slug, title=slug, status="certified")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={},
                                 release_hash="1" * 64, certified=True,
                                 certificate={"granted": True}))
    return db


def _depth(db):
    report = R.assess(db, phase="shadow", providers=[], storage_durable=False)
    return next(r for r in report.requirements if r.key == "catalogue_depth")


def test_the_floor_is_unchanged():
    assert R.MIN_LISTINGS_TO_OPEN == 8


def test_basket_sizes_map_to_one_product():
    # D-W4-OWNER-BASKET-IDENTITY (2026-10-27): the small basket is its own launched product,
    # the Hexagonal Bread Basket; the medium and large stay one product, the nursery family
    # held for separately verified future releases. Sizes are still not products.
    sizes = [s for s in L.launch_scope_slugs() if s.startswith("market-basket-")]
    assert len(sizes) == 3, sizes
    assert R.product_of_slug("market-basket-small") == "hexagonal-bread-basket"
    assert {R.product_of_slug(s) for s in sizes if s != "market-basket-small"} == {
        "nursery-nesting-baskets"}


def test_launch0_reports_eight_products_with_the_list_in_evidence():
    # W4-PIPE 2026-10-07: five products. W4-LAUNCHREADY 2026-10-11, owner-approved CAP-1: eight -- the
    # Nordic Forest baby blanket, the placemat pair and the housewarming key basket joined. The rule
    # is unchanged: sizes are not products, and certified patterns alone are not listings.
    cir = sorted({L.cir_for(v.build).slug for c in L.LAUNCH0_SLUGS
                  for v in L.candidate(c).variants})
    # D-W4-OWNER-BASKET-IDENTITY: the launched basket is one size, so 8 releases, not 10.
    assert len(cir) == 8, cir
    req = _depth(_db_with(cir))
    ev = req.evidence
    assert ev["certified_patterns"] == 8, ev            # versions still reported, beside
    assert ev["products_counted"] == 8, ev
    assert ev["products"] == sorted(L.LAUNCH0_SLUGS), ev
    assert "sizes" in ev["counting_rule"], ev
    # Eight certified products with no listing rows: the floor counts listed products too.
    assert ev["products_with_listings"] == [], ev
    assert not req.ready, "certified patterns with no listings met the floor"


def test_a_product_outside_launch0_counts_as_itself_once():
    assert R.product_of_slug("harvest-table-runner") == "harvest-table-runner"
    cir = sorted(s for s in L.launch_scope_slugs()
                 if s not in ("nursery-nesting-baskets", "hexagonal-bread-basket"))
    ev = _depth(_db_with(cir + ["market-basket-small-copy"])).evidence
    assert ev["certified_patterns"] + len(ev["legacy_counted_zero"]["slugs"]) >= 10, ev
    assert ev["products_counted"] <= len(L.LAUNCH0_SLUGS) + 1, ev


run(globals())
