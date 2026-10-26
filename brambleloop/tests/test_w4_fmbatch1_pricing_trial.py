"""F-374: isolated experimentation for pricing -- a shadow trial on measured price points."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.commerce import pricing  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Improvement, ListingOutcome  # noqa: E402
from brambleloop.improve import runner  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _proposal(db, **change):
    with db.session() as s:
        r = Improvement(cell="pricing", metric="contribution_per_visitor",
                        hypothesis="price the coaster at a measured better point",
                        baseline_value=0.05, evidence={"kind": "price_point", "change": change})
        s.add(r)
        s.flush()
        return r.id


def _outcome(db, slug, start, price, visits, orders):
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, period_start=start, period_end=start,
                             visits=visits, orders=orders, source="test",
                             detail={"price_cad": price}))


def test_registered_and_routed_by_kind():
    assert "pricing_shadow" in runner.TRIALS and "policy_loop" in runner.TRIALS
    assert runner.trial_for({"kind": "price_point"}) == "pricing_shadow"
    assert "pricing_shadow" not in runner.EXECUTORS     # never changes a live price


def test_measured_price_point_scores_contribution_per_visitor():
    db = _db()
    _outcome(db, "hex", "2026-10-01", 6.0, 80, 3)
    _outcome(db, "hex", "2026-10-08", 6.0, 60, 2)        # 140 visits, 5 orders at CA$6
    _outcome(db, "hex", "2026-10-15", 7.0, 40, None)     # orders unknown: not a point
    iid = _proposal(db, slug="hex", price_cad=6.0)
    out = runner.trial_pricing_shadow(db, iid)
    net = float(pricing.net_contribution(6.0)["net_contribution"]["amount"])
    assert out["ran"] is True
    assert out["value"] == round(5 * net / 140, 6)
    assert out["reads"]["visits"] == 140 and out["reads"]["orders"] == 5
    again = runner.trial_pricing_shadow(db, iid)          # re-derivable for the adversary
    assert again["value"] == out["value"] and again["run_ref"] == out["run_ref"]


def test_unmeasured_or_thin_price_is_not_extrapolated():
    db = _db()
    _outcome(db, "hex", "2026-10-01", 6.0, 40, 1)
    thin = runner.trial_pricing_shadow(db, _proposal(db, slug="hex", price_cad=6.0))
    assert thin["ran"] is False and "40 measured visits" in thin["why"]
    never = runner.trial_pricing_shadow(db, _proposal(db, slug="hex", price_cad=9.5))
    assert never["ran"] is False and "not extrapolated" in never["why"]
    assert runner.trial_pricing_shadow(db, _proposal(db, price_cad=6.0))["ran"] is False


def test_prices_below_the_floors_are_refused():
    db = _db()
    for price in (pricing.MIN_PRICE_CAD - 0.5, pricing.MIN_PRICE_CAD):
        iid = _proposal(db, slug="hex", price_cad=price)
        net = float(pricing.net_contribution(max(price, 0.01))["net_contribution"]["amount"])
        if price >= pricing.MIN_PRICE_CAD and net >= pricing.MIN_NET_CONTRIBUTION_CAD:
            continue
        try:
            runner.trial_pricing_shadow(db, iid)
            raise AssertionError(f"CA${price} should be refused")
        except runner.SandboxRefused:
            pass


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
