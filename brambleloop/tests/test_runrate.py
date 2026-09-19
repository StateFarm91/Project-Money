"""Funnel arithmetic, unit costs, and the metric everyone optimises instead.

v1.4.3 requirements 24, 25, 28, 31. A revenue target is a wish until it is a funnel, and the
useful part of writing it as one is not the number at the end. It is that only one term is ever
binding, and the company almost always works on a different one — because the binding term is
usually the one nobody owns, and the term under our hand is always the listing.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.finance import unit_cost as U  # noqa: E402
from brambleloop.scale import runrate as RR  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/runrate.sqlite")
    db.create_all()
    return db


# ---- contribution per visitor (#24) ---------------------------------------


def test_the_dearer_product_wins_and_the_conversion_ranking_disagrees():
    """#24's whole point, and the reason it needs stating.

    A CA$25 pattern at 1.6% beats a CA$12 pattern at 2.5% per visitor, and every instinct in
    e-commerce says the second listing is the healthier one — because conversion rate is the
    number that feels like performance, and it is a ratio whose denominator you are buying.
    """
    result = RR.per_visitor([
        {"slug": "premium-throw", "price_cad": 25.0, "conversion": 0.016},
        {"slug": "cheap-coaster", "price_cad": 12.0, "conversion": 0.025},
    ])
    assert result["best"] == "premium-throw"
    assert result["conversion_ranking_disagrees"] is True
    assert "denominator you are also buying" in result["note"]
    assert result["ranked"][0]["revenue_per_visitor"] == 0.4


def test_contribution_rate_can_reverse_a_revenue_per_visitor_ranking():
    """Revenue per visitor is the improvement over conversion; contribution is the answer."""
    result = RR.per_visitor([
        {"slug": "bundle", "price_cad": 40.0, "conversion": 0.010,
         "contribution_rate": 0.35},
        {"slug": "single", "price_cad": 25.0, "conversion": 0.014,
         "contribution_rate": 0.80},
    ])
    assert result["ranked"][0]["revenue_per_visitor"] < 0.4
    assert result["best"] == "single"


# ---- the decomposition (#25) ----------------------------------------------


def test_the_target_is_four_companies_rather_than_one_plan():
    """200 x CA$15 and 120 x CA$25 are the same CA$3,000 and different businesses."""
    d = RR.decompose()
    assert d["target_cad_per_month"] == 3000.0
    by_price = {o["price_cad"]: o for o in d["options"]}
    assert by_price[15.0]["orders_per_month"] == 200.0
    assert by_price[25.0]["orders_per_month"] == 120.0
    assert "visible as a decision" in d["note"]


def test_required_visits_come_only_from_an_observed_conversion_rate():
    """A funnel built from category benchmarks is a confident plan about a different company."""
    unmeasured = RR.decompose()
    assert all(o["required_visits_per_month"] is None for o in unmeasured["options"])
    assert "company that does not exist" in unmeasured["options"][0]["from"]

    observed = RR.decompose(observed=RR.Observed(visits=10_000, orders=200))
    by_price = {o["price_cad"]: o for o in observed["options"]}
    # 120 orders at a measured 2% conversion needs 6,000 visits.
    assert by_price[25.0]["required_visits_per_month"] == 6000
    assert "observed conversion" in by_price[25.0]["from"]


# ---- the constraint (#25, #28) --------------------------------------------


def test_the_binding_term_cannot_be_named_from_terms_nobody_measured():
    """Naming it anyway picks whichever term somebody happens to have a benchmark for."""
    result = RR.constraint(RR.Observed())
    assert result["identifiable"] is False
    assert set(result["unmeasured"]) >= {"traffic", "conversion", "aov"}
    assert "whichever term somebody has a benchmark for" in result["reason"]


def test_a_working_listing_nobody_sees_is_a_traffic_constraint():
    """Walked in funnel order, so the earliest binding term wins.

    Fixing conversion while nobody is arriving is work that cannot show up, and it is the
    most natural work to choose.
    """
    observed = RR.Observed(visits=1200, impressions=40_000, orders=36,
                           revenue_cad=900.0, repeat_orders=2)
    result = RR.constraint(observed)
    assert result["identifiable"] is True
    assert result["constraint"] == "traffic"
    assert result["rule"] == "strong_conversion_low_traffic"
    assert "nobody is seeing it" in result["action"]
    assert result["needed_visits_per_month"] > observed.visits


def test_impressions_that_do_not_become_visits_are_the_thumbnail():
    observed = RR.Observed(visits=200, impressions=100_000, orders=6,
                           revenue_cad=150.0, repeat_orders=0)
    result = RR.constraint(observed)
    assert result["constraint"] == "ctr"
    assert "the thumbnail and the title, not the product" in result["action"]


def test_rising_defects_outrank_every_commercial_term():
    """Scaling a defect multiplies it (#28)."""
    observed = RR.Observed(visits=20_000, impressions=500_000, orders=400,
                           revenue_cad=10_000.0, repeat_orders=40)
    result = RR.constraint(observed, refund_rate=0.12)
    assert result["rule"] == "rising_defects"
    assert "stop scaling and investigate" in result["action"]


def test_allowable_cac_is_set_against_contribution_not_revenue():
    """Setting it against the top line is how a business buys customers at a loss."""
    result = RR.allowable_cac(25.0, 0.7)
    assert result["allowable_cac_cad"] == 17.5
    assert "never revenue" in result["note"]
    try:
        RR.allowable_cac(25.0, 0.0)
    except RR.RunRateRefused as e:
        assert "contribution rate" in str(e)
    else:
        raise AssertionError("a zero contribution rate produced an allowable CAC")


# ---- unit cost (#31) ------------------------------------------------------


def test_an_artefact_produced_by_uncosted_work_is_not_reported_as_cheap():
    """Free is the most dangerous price."""
    from brambleloop.core.models import AuditLog, CostEntry

    db = _db()
    with db.session() as s:
        for i in range(3):
            s.add(AuditLog(actor="orchestrator", action="gate.certified",
                           artifact=f"p{i}@1.0.0"))
        s.add(CostEntry(agent="orchestrator", kind="llm", amount_cad=1.50))

    result = U.unit_costs(db)
    pattern = result["artefacts"]["validated_pattern"]
    assert pattern["produced"] == 3
    assert pattern["produced_by_uncosted_work"] == 3
    assert "the figure above is a floor" in pattern["note"]
    # The spend is real and unattributed rather than silently spread over the artefacts.
    assert result["operating_cost_cad"] == 1.5
    assert result["unattributed_cost_cad"] == 1.5


def test_spending_with_no_contribution_is_reported_as_burning():
    """The comfortable failure: every number rising while nobody divides."""
    from brambleloop.core.models import CostEntry

    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="orchestrator", kind="llm", amount_cad=40.0))

    result = U.unit_costs(db)
    assert result["burning"] is True
    assert result["contribution_cad"] == 0.0
    assert result["contribution_per_operating_dollar"] == 0.0
    assert "burns more than it earns is failure" in result["note"]


def test_a_production_plan_cannot_be_priced_from_an_assumed_unit_cost():
    db = _db()
    result = U.throughput_target(db, target_products=10, budget_cad=100.0)
    assert result["affordable"] is None
    assert "a different company" in result["reason"]


def test_both_of_the_ratios_31_names_are_reported_even_when_one_side_is_zero():
    from brambleloop.core.models import AuditLog, CostEntry

    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="orchestrator", kind="llm", amount_cad=20.0))
        for i in range(4):
            s.add(AuditLog(actor="orchestrator", action="gate.certified",
                           artifact=f"p{i}@1.0.0"))
    result = U.unit_costs(db)
    assert result["validated_products_per_operating_dollar"] == 0.2
    assert result["contribution_per_operating_dollar"] == 0.0
    assert set(U.ARTEFACTS) >= {"concept", "validated_pattern", "pdf", "listing",
                                "visual_asset", "support_case", "acquired_customer"}


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
