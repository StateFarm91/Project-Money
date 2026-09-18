"""CA$5,000 a month: the paths to it, and a probability that cannot be talked upward.

v1.4.3 requirements 229, 230, 269, 270, 273, 274, 275, and the owner's framing that governs
all of them — the probability must be *earned from actual market evidence, not manufactured
from optimistic assumptions*.

Most of these tests are attacks. The failure mode this module exists to prevent is not a bug;
it is a system that has built something impressive, sold nothing, and reports a number that
makes everyone feel good about it.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.scale import confidence, target  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/scale.sqlite")
    db.create_all()
    return db


def _sell(db, orders: int, aov: float = 25.0, months_back: int = 0) -> None:
    """Record real ledger sales — the only thing this model treats as demand."""
    from brambleloop.core.models import LedgerEntry

    when = datetime.now(timezone.utc) - timedelta(days=30 * months_back)
    with db.session() as s:
        for i in range(orders):
            s.add(LedgerEntry(at=when, category="sale", description=f"order {i}",
                              gross_cad=aov, evidence_ref=f"etsy:{months_back}:{i}"))


def _certify(db, n: int, physical: int = 0) -> None:
    from brambleloop.core.models import PatternVersion, PhysicalTest, Product

    with db.session() as s:
        for i in range(n):
            product = Product(slug=f"p{i}", title=f"P{i}", status="certified")
            s.add(product)
            s.flush()
            s.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                 release_hash="0" * 64, certified=True,
                                 certificate={"granted": True}))
        for i in range(physical):
            s.add(PhysicalTest(product_slug=f"p{i}", version="1.0.0", tester_ref=f"t{i}",
                               passed=True))


# ---- the attacks ----------------------------------------------------------


def test_a_sophisticated_system_that_has_sold_nothing_reports_effectively_zero():
    """#230, stated as plainly as the requirement states it.

    Nineteen certified designs, a deterministic compiler, a reverse compiler, release gates,
    a benchmark mission and a seasonal engine — and not one customer. The number has to be
    near zero, and the statement has to say that no amount of further building moves it.
    """
    db = _db()
    _certify(db, 19, physical=0)

    result = confidence.probability(db)
    assert result["probability"] < 0.05, result["ladder"]
    assert "Effectively zero" in result["honest_statement"]
    assert "only customers do" in result["honest_statement"]

    # And the rung that is actually earned says so, rather than everything reading as zero
    # for the same undifferentiated reason.
    quality = [r for r in result["ladder"] if r["layer"] == "product_quality"][0]
    assert quality["confidence"] > 0.5
    assert quality["evidence"]["certified_patterns"] == 19
    assert quality["confidence"] < 0.6, "validation alone must not clear 0.6 without samples"


def test_no_caller_can_argue_the_model_upward_without_orders_in_the_ledger():
    """The hole every scoring model has, closed.

    Several rungs need counts from systems that do not exist yet — attribution, repeat
    tracking, portfolio roles. A caller supplying those could otherwise report a perfectly
    diversified, highly converting business into a database holding no sales. Everything
    measured *from orders* is bounded by the order count, which comes from the ledger.
    """
    db = _db()
    _certify(db, 19, physical=5)

    inflated = confidence.probability(
        db, observed_conversion=0.09, conversion_sample=99_999,
        selling_skus=99, product_families=9, acquisition_loops=9,
        repeat_orders=9_999, top_sku_revenue_share=0.0, outside_customers=9_999)

    assert inflated["probability"] < 0.05
    for layer in ("conversion", "aov", "portfolio_resilience"):
        rung = [r for r in inflated["ladder"] if r["layer"] == layer][0]
        assert rung["confidence"] == 0.0, (layer, rung)

    # The two the caller actually inflated carry the mark of having been cut back to what the
    # ledger supports. `aov` is already zero on its own evidence, so it needs no clamp.
    for layer in ("conversion", "portfolio_resilience"):
        rung = [r for r in inflated["ladder"] if r["layer"] == layer][0]
        assert rung["evidence"].get("bounded_by_demand") is True, layer
        assert rung["evidence"]["orders_in_ledger"] == 0


def test_the_ladder_is_a_minimum_so_one_fatal_layer_cannot_be_averaged_away():
    """#274, and the specific failure an average hides.

    "We can make it, price it, photograph it, and nobody buys it" is six strong layers and one
    fatal one. An average reports 0.85 and a minimum reports the truth.
    """
    db = _db()
    _certify(db, 19, physical=5)
    _sell(db, 300, aov=25.0, months_back=0)
    _sell(db, 300, aov=25.0, months_back=1)
    _sell(db, 300, aov=25.0, months_back=2)

    # Everything strong except acquisition: no repeatable way to produce qualified traffic.
    result = confidence.probability(
        db, observed_conversion=0.02, conversion_sample=50_000,
        selling_skus=12, product_families=4, acquisition_loops=0,
        repeat_orders=300, top_sku_revenue_share=0.2, outside_customers=700)

    assert result["weakest_critical_layer"] == "acquisition"
    assert result["probability"] == 0.0

    others = [r["confidence"] for r in result["ladder"]
              if r["layer"] != "acquisition" and r["critical"]]
    assert min(others) > 0.7, "the other layers should be strong, or this proves nothing"
    assert sum(others) / len(others) > 0.7, "an average would have reported a healthy number"


def test_an_early_fluke_cannot_become_a_plan():
    """A 100% conversion rate over two visits is not a 100% conversion rate.

    Shrinkage by sample size is what stops the first lucky week from setting the company's
    expectations for the year.
    """
    assert confidence.shrink(1.0, 0, 1000) == 0.0
    assert confidence.shrink(1.0, 2, 1000) < 0.01
    assert confidence.shrink(1.0, 100, 1000) < 0.15
    assert confidence.shrink(1.0, 1000, 1000) == 1.0
    assert confidence.shrink(1.0, 5000, 1000) == 1.0

    # Three orders is demand evidence, and it is nearly worthless as demand evidence.
    db = _db()
    _certify(db, 19, physical=5)
    _sell(db, 3)
    tiny = confidence.probability(db, observed_conversion=0.05, conversion_sample=60)
    demand = [r for r in tiny["ladder"] if r["layer"] == "demand"][0]
    assert 0 < demand["confidence"] < 0.05


def test_seventy_five_percent_is_unreachable_while_the_evidence_standard_is_unmet():
    """#275 is a floor made of counts, so it cannot be reasoned around.

    Even with every rung at its maximum, a shop with two months of history and three selling
    SKUs may not report 75%.
    """
    db = _db()
    _certify(db, 19, physical=5)
    _sell(db, 200, months_back=0)
    _sell(db, 200, months_back=1)

    result = confidence.probability(
        db, observed_conversion=0.02, conversion_sample=50_000,
        selling_skus=3, product_families=1, acquisition_loops=3,
        repeat_orders=200, top_sku_revenue_share=0.1, outside_customers=300)

    gate = result["evidence_gate"]
    assert gate["satisfied"] is False
    assert "selling_skus" in gate["unmet"] and "product_families" in gate["unmet"]
    assert "months_of_history" in gate["unmet"]
    assert result["probability"] <= confidence.GATE_CEILING
    if result["capped_by"] == "the evidence gate (#275)":
        assert result["probability"] == confidence.GATE_CEILING


def test_the_gate_opening_is_what_finally_allows_a_high_number():
    """And when the evidence does exist, the model says so rather than staying pessimistic.

    A model that can only ever report near zero is as useless as one that flatters — it would
    stop being read. This is the case that proves the ceiling is a gate and not a cap.
    """
    db = _db()
    _certify(db, 19, physical=5)
    for month in range(4):
        _sell(db, 220, aov=26.0, months_back=month)

    result = confidence.probability(
        db, observed_conversion=0.024, conversion_sample=60_000,
        selling_skus=9, product_families=3, acquisition_loops=2,
        repeat_orders=260, top_sku_revenue_share=0.22, outside_customers=600)

    assert result["evidence_gate"]["satisfied"] is True
    assert result["probability"] > 0.75, result["ladder"]
    assert result["capped_by"] == "the weakest critical layer"


def test_an_empty_portfolio_is_not_a_diversified_one():
    """#270. Zero selling SKUs is total concentration, not an undefined ratio.

    A concentration metric computed over an empty set is the kind of divide-by-nothing that
    reports perfect health for a shop with no products.
    """
    db = _db()
    _certify(db, 19, physical=5)
    _sell(db, 300)

    empty = confidence.ladder(db, selling_skus=0, product_families=0,
                              top_sku_revenue_share=1.0)
    resilience = [r for r in empty if r.key == "portfolio_resilience"][0]
    assert resilience.confidence == 0.0

    one_hit = confidence.ladder(db, selling_skus=6, product_families=2,
                                top_sku_revenue_share=0.85)
    assert [r for r in one_hit if r.key == "portfolio_resilience"][0].confidence < 0.3

    spread = confidence.ladder(db, selling_skus=9, product_families=3,
                               top_sku_revenue_share=0.2)
    assert [r for r in spread if r.key == "portfolio_resilience"][0].confidence > 0.7


# ---- the scenario matrix --------------------------------------------------


def test_every_scenario_states_both_gross_and_contribution():
    """A target hit on paper and missed in the bank.

    CA$5,000 gross is not CA$5,000 net: Etsy takes a transaction fee, payment processing and
    a listing fee, and refunds come off the top. Reporting only gross is how a plan reaches
    its number and the owner does not.
    """
    matrix = target.matrix()
    assert matrix["target_cad_per_month"] == 5000.0

    for scenario in matrix["scenarios"]:
        assert scenario["gross_cad"] >= 4900
        assert scenario["contribution_cad"] < scenario["gross_cad"]
        assert 0.8 < scenario["contribution_margin"] < 0.95
        # Gross alone never counts as reaching the target.
        assert "reaches_target_contribution" in scenario

    paid = [x for x in matrix["scenarios"] if "ads" in x["name"]][0]
    unpaid = [x for x in matrix["scenarios"] if x["name"].startswith("balanced:")][0]
    assert paid["contribution_cad"] < unpaid["contribution_cad"]


def test_required_visits_account_for_repeat_and_off_platform_orders():
    """Repeat buyers do not arrive through the search funnel.

    Dividing every order by the conversion rate overstates the traffic a shop needs and makes
    every path look impossible; ignoring the composition entirely makes them all look easy.
    """
    plain = target.Scenario("plain", 200, 25.0, 0.02, "assumed", 0, 0.0, 0.0, 0.0, 0.01)
    repeating = target.Scenario("repeat", 200, 25.0, 0.02, "assumed", 0, 0.30, 0.0, 0.0, 0.01)
    mixed = target.Scenario("mixed", 200, 25.0, 0.02, "assumed", 0, 0.0, 0.25, 0.0, 0.01)

    assert plain.required_visits == 10_000
    assert repeating.required_visits == 7_000
    assert mixed.required_visits == 7_500

    # A conversion rate of zero cannot be divided by, and must not crash the matrix.
    assert target.Scenario("none", 200, 25.0, 0.0, "assumed", 0, 0, 0, 0, 0
                           ).required_visits == 0


def test_a_scenario_built_on_an_assumed_rate_is_never_evidence_supported():
    """#273: the CEO chooses the most evidence-supported path, not the prettiest spreadsheet.

    Today every path is assumed, so the count of evidence-supported paths is zero — and the
    note says the attractive row is the one to distrust, because it is attractive on account
    of its assumptions rather than its difficulty.
    """
    assumed = target.matrix()
    assert assumed["evidence_supported_paths"] == 0
    assert all(not x["conversion"]["trustworthy"] for x in assumed["scenarios"])
    assert "the one to distrust" in assumed["note"]

    # A small observed sample is still not evidence.
    thin = target.matrix(conversion_rate=0.03, basis="observed", sample=40)
    assert thin["evidence_supported_paths"] == 0

    measured = target.matrix(conversion_rate=0.021, basis="observed", sample=5_000)
    assert measured["evidence_supported_paths"] == len(measured["scenarios"])
    assert "only ones the" in measured["note"]


def test_the_binding_constraint_is_ranked_by_share_rather_than_by_gap():
    """#229 asks for the binding constraint weekly, and absolute gaps cannot be compared.

    400 visits and 0.4 percentage points of conversion are not comparable as differences;
    they are directly comparable as fractions of what the target needs.
    """
    result = target.binding_constraint({
        "qualified_visits": 9_000,      # 90% of what is needed
        "conversion_rate": 0.002,       # 10%
        "aov_cad": 24.0,                # 96%
        "orders_per_month": 150,        # 75%
    })
    assert result["binding"] == "conversion_rate"
    shares = [g["share_of_needed"] for g in result["gaps"]]
    assert shares == sorted(shares), "gaps must be ranked worst-first"

    # An empty company is bound by whichever number is zero, not by an error.
    assert target.binding_constraint({})["gaps"][0]["share_of_needed"] == 0.0


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
