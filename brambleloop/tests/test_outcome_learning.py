"""Creativity outcome learning: concept attributes joined to outcomes (#89).

Concepts, listings and orders below are synthetic fixtures. The empty-database test is the
company today: every outcome UNMEASURED with its reason.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import outcome_learning as OL  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402

FORMS = ("rectangle_throw", "rectangle_throw", "rectangle_throw", "ornament", "basket", "hat")
CONSTRUCTIONS = ("flat_rows", "flat_rows", "flat_rows", "amigurumi_shaping", "in_the_round",
                 "top_down_yoke")
RECIPIENTS = ("self", "self", "self", "child", "host", "teen")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _concepts(n: int = 6) -> list[Concept]:
    return [Concept(key=f"c{i}", title=f"Concept {i}",
                    premise=f"A distinct fixture idea number {i} shown plainly here",
                    pod="home_decor", form=FORMS[i], construction=CONSTRUCTIONS[i],
                    motif="stripe" if i < 3 else f"motif{i}", palette_story="p",
                    recipient=RECIPIENTS[i], occasion="everyday", feeling="cosy",
                    function="warmth" if i < 3 else f"f{i}", make_lane="QUICK")
            for i in range(n)]


def _seed(db, slugs, *, contribution: dict[str, float], orders_each: int = 10):
    from brambleloop.core.models import Customer, ListingOutcome, Order

    with db.session() as s:
        cust = Customer(customer_ref="fixture-buyer")
        s.add(cust)
        s.flush()
        for slug in slugs:
            s.add(ListingOutcome(product_slug=slug, period_start="2027-01-01",
                                 period_end="2027-01-31", impressions=1000, visits=100,
                                 favourites=5, source="fixture"))
            for k in range(orders_each):
                s.add(Order(customer_id=cust.id, external_ref=f"{slug}-{k}",
                            at=datetime(2027, 1, 15, tzinfo=timezone.utc), product_slug=slug,
                            revenue_cad=20.0, contribution_cad=contribution[slug],
                            reviewed=k == 0))


def test_an_empty_database_is_unmeasured_with_reasons():
    out = OL.learn(_db(), _concepts())
    assert out["status"] == OL.UNMEASURED and "nothing is live" in out["why"]
    assert out["novelty"]["status"] == OL.UNMEASURED
    assert out["novelty"]["novelty_is_rewarded"] is False
    assert all(v["status"] == OL.UNMEASURED
               for a in out["by_attribute"].values() for v in a.values())


def test_the_catalogue_is_joined_by_default_and_unmeasured_today():
    out = OL.learn(_db())
    assert out["concepts"] > 0 and out["concepts_with_outcomes"] == 0
    assert out["status"] == OL.UNMEASURED


def test_the_attribute_minimum_boundary():
    concepts = _concepts()
    db = _db()
    _seed(db, ["c0", "c1"], contribution={"c0": 5.0, "c1": 5.0})
    form = OL.learn(db, concepts)["by_attribute"]["form"]["rectangle_throw"]
    assert form["status"] == OL.UNMEASURED and "2 concept" in form["why"]
    db = _db()
    _seed(db, ["c0", "c1", "c2"], contribution={k: 5.0 for k in ("c0", "c1", "c2")})
    form = OL.learn(db, concepts)["by_attribute"]["form"]["rectangle_throw"]
    assert form["status"] == OL.MEASURED and form["concepts"] == OL.MIN_CONCEPTS_PER_VALUE
    m = form["metrics"]
    assert m["ctr"]["value"] == 0.1 and m["conversion"]["value"] == 0.1
    assert m["contribution"]["value"] == 150.0 and m["reviews"]["value"] == 0.1


def test_the_novelty_check_needs_both_halves():
    concepts = _concepts()
    db = _db()
    slugs = ["c0", "c1", "c2", "c3", "c4"]
    _seed(db, slugs, contribution={k: 5.0 for k in slugs})
    nov = OL.learn(db, concepts)["novelty"]
    assert nov["status"] == OL.UNMEASURED and nov["high_novelty_outperforms"] is None


def _novelty_run(high_pays: bool) -> dict:
    concepts = _concepts()
    db = _db()
    slugs = [c.key for c in concepts]
    # c0..c2 are near-duplicates (low novelty); c3..c5 differ in everything.
    contribution = {k: (2.0 if int(k[1]) < 3 else 8.0) for k in slugs}
    if not high_pays:
        contribution = {k: 10.0 - v for k, v in contribution.items()}
    _seed(db, slugs, contribution=contribution)
    return OL.learn(db, concepts)["novelty"]


def test_novelty_is_reported_in_either_direction_and_never_rewarded():
    up = _novelty_run(True)
    assert up["status"] == OL.MEASURED and up["high_novelty_outperforms"] is True
    assert set(up["groups"]["high"]["concepts"]) == {"c3", "c4", "c5"}
    down = _novelty_run(False)
    assert down["status"] == OL.MEASURED and down["high_novelty_outperforms"] is False
    assert down["useful_originality"] == []
    assert up["novelty_is_rewarded"] is False and down["novelty_is_rewarded"] is False


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
    sys.exit(1 if fails else 0)
