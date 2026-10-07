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
    sizes = [s for s in L.launch_scope_slugs() if s.startswith("market-basket-")]
    assert len(sizes) == 3, sizes
    assert {R.product_of_slug(s) for s in sizes} == {"nursery-nesting-baskets"}


def test_launch0_reports_five_products_with_the_list_in_evidence():
    # W4-PIPE 2026-10-07: Launch-0 is five products (seven CIR slugs: three basket sizes) since
    # the snowflake ornaments and the snowfall throw joined it. The rule is unchanged: sizes
    # are not products, and five products do not meet a floor of eight.
    cir = sorted(s for s in L.launch_scope_slugs() if s != "nursery-nesting-baskets")
    assert len(cir) == 7, cir
    req = _depth(_db_with(cir))
    ev = req.evidence
    assert ev["certified_patterns"] == 7, ev            # versions still reported, beside
    assert ev["products_counted"] == 5, ev
    assert ev["products"] == sorted(L.LAUNCH0_SLUGS), ev
    assert "sizes" in ev["counting_rule"], ev
    assert not req.ready, "5 products met a floor of 8"


def test_a_product_outside_launch0_counts_as_itself_once():
    assert R.product_of_slug("harvest-table-runner") == "harvest-table-runner"
    cir = sorted(s for s in L.launch_scope_slugs() if s != "nursery-nesting-baskets")
    ev = _depth(_db_with(cir + ["market-basket-small-copy"])).evidence
    assert ev["certified_patterns"] + len(ev["legacy_counted_zero"]["slugs"]) >= 7, ev
    assert ev["products_counted"] <= len(L.LAUNCH0_SLUGS) + 1, ev


run(globals())
