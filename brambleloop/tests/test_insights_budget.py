"""The Insights query budgeter allocates by information gain and cannot buy anything (#37).

The resource does not exist yet, so the tests are about the arithmetic being right, the
allocation refusing to rank from nothing, the snapshot store lowering the value of a keyword
already asked, and the recommendation never becoming a purchase.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing, Keyword  # noqa: E402
from brambleloop.intel import insights_budget as I  # noqa: E402

KEY = "mjs_off_the_hook_designs"


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _pod(db, pod: str, title: str, *, price: float, favourites: int | None, n: int = 5):
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(
                benchmark_key=KEY, listing_ref=f"{pod}-{i}", title=f"{title} {i}", pod=pod,
                price_cad=price, media_count=3,
                detail={"num_favorers": favourites} if favourites is not None else {}))


def test_the_arithmetic_rewards_promising_unknowns_and_discounts_what_was_asked():
    unknown_and_good = I.information_gain(confidence=0.2, value=0.9, prior_queries=0)
    known_and_good = I.information_gain(confidence=0.9, value=0.9, prior_queries=0)
    unknown_and_poor = I.information_gain(confidence=0.2, value=0.1, prior_queries=0)
    asked_before = I.information_gain(confidence=0.2, value=0.9, prior_queries=3)
    assert unknown_and_good > known_and_good
    assert unknown_and_good > unknown_and_poor
    assert asked_before == round(unknown_and_good / 4, 4)
    for bad in ({"confidence": 1.2, "value": 0.5, "prior_queries": 0},
                {"confidence": 0.5, "value": -0.1, "prior_queries": 0},
                {"confidence": 0.5, "value": 0.5, "prior_queries": -1}):
        try:
            I.information_gain(**bad)
        except I.BudgetRefused:
            pass
        else:
            raise AssertionError(f"{bad} was accepted")


def test_nothing_scored_means_nothing_allocated_and_insufficient_evidence():
    db = _db()
    plan = I.allocate(db)
    assert plan["allocatable"] is False and plan["allocation"] == {}
    verdict = I.may_buy_insights(db)
    assert verdict["recommendation"] == I.INSUFFICIENT
    assert verdict["purchased"] is False
    assert verdict["expected_value_cad"] is None


def test_the_least_measured_promising_department_is_asked_first():
    """Hats carry no favourites, so demand is unmeasured and their confidence is lower;
    the uncertainty is what a query buys, so hats come first."""
    db = _db()
    _pod(db, "garments", "Cosy Ribbed Cardigan Crochet Pattern", price=9.0, favourites=300)
    _pod(db, "hats", "Chunky Ribbed Beanie Crochet Pattern", price=6.0, favourites=None)
    plan = I.allocate(db, queries=40)
    assert plan["allocatable"] is True
    by_pod = {g["pod"]: g for g in plan["gains"]}
    assert by_pod["hats"]["confidence"] < by_pod["garments"]["confidence"]
    assert plan["first"] == "hats"
    assert sum(plan["allocation"].values()) == 40
    assert plan["allocation"]["hats"] >= plan["allocation"]["garments"]


def test_a_keyword_already_snapshotted_lowers_the_value_of_asking_again():
    db = _db()
    _pod(db, "garments", "Cosy Ribbed Cardigan Crochet Pattern", price=9.0, favourites=300)
    _pod(db, "hats", "Chunky Ribbed Beanie Crochet Pattern", price=6.0, favourites=None)
    before = {g["pod"]: g["gain"] for g in I.allocate(db)["gains"]}
    with db.session() as s:
        s.add(Keyword(phrase="chunky beanie crochet pattern"))
        s.add(Keyword(phrase="ribbed beanie pattern"))
        s.add(Keyword(phrase="something that routes nowhere"))
    priors = I.prior_queries(db)
    assert priors["hats"] == 2 and priors["garments"] == 0
    after = {g["pod"]: g["gain"] for g in I.allocate(db)["gains"]}
    assert after["hats"] < before["hats"]
    assert after["garments"] == before["garments"]


def test_the_recommendation_states_its_assumptions_and_never_buys():
    db = _db()
    _pod(db, "garments", "Cosy Ribbed Cardigan Crochet Pattern", price=9.0, favourites=300)
    _pod(db, "hats", "Chunky Ribbed Beanie Crochet Pattern", price=6.0, favourites=None)
    cheap = I.may_buy_insights(db, monthly_cost_cad=0.01)
    dear = I.may_buy_insights(db, monthly_cost_cad=10_000.0)
    assert cheap["recommendation"] == I.BUY
    assert dear["recommendation"] == I.DO_NOT_BUY
    assert cheap["expected_value_cad"] == dear["expected_value_cad"] > 0
    for verdict in (cheap, dear):
        assert verdict["purchased"] is False
        assert "owner" in verdict["owner_gate"].lower()
        assert verdict["evidence"]["lines"]
        assert verdict["assumptions"]
    default = I.may_buy_insights(db)
    assert default["monthly_cost_cad"] == I.ETSY_PLUS_CAD_PER_MONTH
    assert "assumed" in default["cost_basis"]
    # No code path in the module performs a purchase: nothing callable is named for one.
    assert not [n for n in dir(I) if callable(getattr(I, n))
                and ("purchase" in n.lower() or n.lower() in ("buy", "upgrade"))]


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
