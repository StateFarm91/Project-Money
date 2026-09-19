"""Price memory, control cohorts and bundle attribution.

v1.4.3 requirements 45, 46, 48. Three requirements, one mistake: something changed, sales
moved, therefore the thing that changed caused it.

The mistake is not carelessness. Every version of it is locally reasonable and every version
makes a dashboard improve, which is why none of them is caught by looking at the dashboard.
The price dropped in November and sales rose — it was December. Ads went on and conversion
improved — paid traffic is differently intentioned traffic. The bundle sold well — the buyers
were already ours, and they used to buy the higher-margin thing next to it.

So these tests are mostly about refusing to answer, and about the arithmetic being done on
contribution rather than on revenue.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import attribution as A  # noqa: E402
from brambleloop.commerce import elasticity as E  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/commerce.sqlite")
    db.create_all()
    return db


def _point(price: float, orders: int, **kw) -> E.PricePoint:
    base = dict(product_slug="throw", category="blanket", visits=1000,
                revenue_cad=price * orders, contribution_cad=price * orders * 0.6,
                season="autumn", traffic_source="organic")
    base.update(kw)
    return E.PricePoint(price_cad=price, orders=orders, **base)


# ---- elasticity (#46) -----------------------------------------------------


def test_an_unmeasured_elasticity_is_not_an_elasticity_of_zero():
    """Zero is not the absence of a claim. It is the claim that price does not matter."""
    db = _db()
    m = E.memory(db)
    assert m["measurable"] is False
    assert m["elasticity"] is None
    assert "unmeasured, not inelastic" in m["reason"]


def test_a_comparison_across_a_confounder_is_refused_rather_than_flagged():
    """A warning attached to a number is read once; the number travels on alone."""
    autumn = _point(12.0, 40)
    winter = _point(9.0, 60, season="winter")
    across_seasons = E.compare(autumn, winter)
    assert across_seasons["comparable"] is False
    assert "different seasons" in across_seasons["problems"][0]
    assert "response to the price" in across_seasons["problems"][0]
    assert across_seasons["elasticity"] is None

    paid = _point(9.0, 60, traffic_source="promoted")
    across_traffic = E.compare(autumn, paid)
    assert across_traffic["comparable"] is False
    assert "about the audience, not the price" in across_traffic["problems"][0]


def test_two_prices_too_close_or_two_samples_too_small_are_refused():
    assert E.compare(_point(12.0, 40), _point(11.5, 45))["comparable"] is False
    assert "indistinguishable from noise" in \
        E.compare(_point(12.0, 40), _point(11.5, 45))["problems"][0]

    thin = E.compare(_point(12.0, 40), _point(9.0, 3))
    assert thin["comparable"] is False
    assert "that is not a rate" in thin["problems"][0]


def test_a_clean_comparison_decides_on_contribution_rather_than_revenue():
    """A price that sells more at a worse margin is a busier version of the same business."""
    dearer = E.PricePoint("throw", "blanket", 14.0, 1000, 30, 420.0, 300.0,
                          season="autumn", traffic_source="organic")
    cheaper = E.PricePoint("throw", "blanket", 9.0, 1000, 45, 405.0, 220.0,
                           season="autumn", traffic_source="organic")
    result = E.compare(dearer, cheaper)
    assert result["comparable"] is True
    assert result["elasticity"] is not None
    # More units and more revenue at the lower price, and less contribution.
    assert result["higher_contribution_at_cad"] == 14.0
    assert "busier version of the same business" in result["note"]


def test_price_memory_reports_per_category_because_elasticity_is_category_specific():
    db = _db()
    E.record(db, _point(12.0, 40))
    E.record(db, _point(9.0, 60))
    E.record(db, _point(6.0, 5, category="coaster", product_slug="coaster"))
    m = E.memory(db)
    categories = {c["category"]: c for c in m["categories"]}
    assert categories["blanket"]["measurable"] is True
    # One readable point in coasters is not a curve.
    assert categories["coaster"]["measurable"] is False
    assert categories["blanket"]["prices_held"] == [9.0, 12.0]


# ---- control cohorts (#48) ------------------------------------------------


def test_one_arm_cannot_separate_a_better_listing_from_bought_traffic():
    promoted = E.Arm("k", "throw", E.PROMOTED, visits=1000, orders=30,
                     revenue_cad=360.0, spend_cad=40.0)
    alone = E.holdout(None, promoted)
    assert alone["separable"] is False
    assert "no organic control" in alone["reason"]
    assert "looks the same either way" in alone["reason"]


def test_incrementality_is_measured_against_what_the_control_predicts():
    """Counting the control's own performance as a result of the spend is the whole error."""
    organic = E.Arm("o", "throw", E.ORGANIC, visits=1000, orders=20, revenue_cad=240.0)
    promoted = E.Arm("p", "throw", E.PROMOTED, visits=1000, orders=30, revenue_cad=360.0,
                     spend_cad=50.0)
    result = E.holdout(organic, promoted)
    assert result["separable"] is True
    # 1000 promoted visits at the organic 2% rate would have produced 20 orders.
    assert result["incremental_orders"] == 10
    assert result["cost_per_incremental_order_cad"] == 5.0

    # Paid traffic that converts worse than organic bought visits, not sales.
    worse = E.holdout(organic, E.Arm("p2", "throw", E.PROMOTED, visits=2000, orders=20,
                                     revenue_cad=240.0, spend_cad=80.0))
    assert worse["incremental_orders"] < 0
    assert worse["paid_traffic_converts_worse"] is True
    assert "bought visits, not sales" in worse["note"]


def test_a_cohort_arm_must_be_one_of_the_two_that_mean_something():
    try:
        E.Arm("k", "throw", "everyone", visits=10, orders=1, revenue_cad=12.0)
    except E.ElasticityRefused as e:
        assert "not a cohort arm" in str(e)
    else:
        raise AssertionError("an invented arm was accepted")


# ---- bundle attribution (#45) ---------------------------------------------


def test_a_bundle_cannot_be_judged_without_a_before():
    """The after-window shows a bundle selling and says nothing about where its buyers came from."""
    result = A.bundle_effect(
        "cosy-bundle",
        bundle=A.Period("cosy-bundle", 40, 600.0, 300.0),
        components_before=[],
        components_after=[A.Period("throw", 50, 600.0, 300.0)])
    assert result.measurable is False
    assert "the entire question" in result.reason
    assert A.amplification_check(result)["may_declare_winner"] is False


def test_a_bundle_that_moved_revenue_cannot_be_declared_a_winner():
    """Both halves are true at once: the bundle sold, and the buyers were already ours."""
    before = [A.Period("throw", 100, 1400.0, 800.0), A.Period("coaster", 60, 300.0, 180.0)]
    after = [A.Period("throw", 45, 630.0, 360.0), A.Period("coaster", 55, 275.0, 165.0)]
    bundle = A.Period("cosy-bundle", 60, 900.0, 405.0)

    result = A.bundle_effect("cosy-bundle", bundle=bundle, components_before=before,
                             components_after=after)
    assert result.measurable is True
    assert result.cannibalised_orders == 60
    assert result.contribution_delta_cad < 0
    verdict = A.amplification_check(result)
    assert verdict["may_declare_winner"] is False
    assert verdict["verdict"] == "displacing"
    assert "the buyers were already ours" in verdict["why"]


def test_a_genuinely_incremental_bundle_still_names_what_it_displaced():
    before = [A.Period("throw", 100, 1400.0, 800.0), A.Period("coaster", 60, 300.0, 180.0)]
    after = [A.Period("throw", 95, 1330.0, 760.0), A.Period("coaster", 40, 200.0, 120.0)]
    bundle = A.Period("cosy-bundle", 50, 900.0, 450.0)

    result = A.bundle_effect("cosy-bundle", bundle=bundle, components_before=before,
                             components_after=after)
    verdict = A.amplification_check(result)
    assert verdict["may_declare_winner"] is True
    assert verdict["contribution_delta_cad"] > 0
    # Incremental overall, and one component lost a third of its volume, which is said out
    # loud rather than netted away.
    assert verdict["displacement_alarms"] == ["coaster"]
    assert result.attach_rate is not None


def test_too_few_orders_is_anecdote_arithmetic():
    before = [A.Period("throw", 100, 1400.0, 800.0)]
    after = [A.Period("throw", 95, 1330.0, 760.0)]
    result = A.bundle_effect("cosy-bundle", bundle=A.Period("cosy-bundle", 4, 60.0, 30.0),
                             components_before=before, components_after=after)
    assert result.measurable is False
    assert "anecdote arithmetic" in result.reason
    assert "takes a quarter to surface" in result.reason


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
