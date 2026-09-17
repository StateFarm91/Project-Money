"""The books, the CFO challenge and the CA$100K trajectory (sections 1, 14, 15, 34).

Every number here is zero, and that is what makes these tests worth writing now. Accounting
built alongside the first sale is accounting nobody has checked; accounting built while the
answer is obviously zero can be checked against an answer everyone already knows.

The tests that matter most are the refusals: no run rate from no orders, no cost-per-customer
from no customers, and a tax reserve that is never counted as ours.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, LedgerEntry, SpendLimit  # noqa: E402
from brambleloop.finance.books import (  # noqa: E402
    ANNUAL_TARGET_CAD, TAX_RESERVE_RATE, Books, ProfitAndLoss, cfo_challenge, trajectory,
)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _spend(db, agent: str, amount: float, kind: str) -> None:
    """Record a cost directly, bypassing the per-agent ceiling.

    Going through Registry.record_cost would be refused — the ads agent's daily ceiling is
    CA$1.00 and the guard is doing its job. These tests are about what the books say once
    money has been spent, so the spend is written the way a real charge arriving from a
    provider would be reconciled in.
    """
    with db.session() as s:
        s.add(CostEntry(agent=agent, kind=kind, amount_cad=amount,
                        detail={"note": "reconciled charge, not an agent request"}))


def _with_sales(db, *, orders: int, price: float, fees: float, refunds: float = 0.0):
    with db.session() as s:
        for i in range(orders):
            s.add(LedgerEntry(category="sale", description=f"order {i}", gross_cad=price,
                              fees_cad=fees, refunds_cad=refunds / max(1, orders),
                              evidence_ref=f"test-{i}"))


# ---- the books -------------------------------------------------------------


def test_an_empty_business_reports_zeroes_rather_than_nothing():
    pl = Books(_db()).profit_and_loss()
    d = pl.to_dict()
    assert d["gross_sales_cad"] == 0.0
    assert d["orders"] == 0 and d["customers"] == 0
    assert d["all_figures_observed"] is True


def test_every_line_section_fifteen_names_is_present():
    d = Books(_db()).profit_and_loss().to_dict()
    for line in ("gross_sales_cad", "discounts_cad", "refunds_cad", "net_sales_cad",
                 "platform_fees_cad", "operating_costs_cad", "tax_reserve_cad",
                 "contribution_margin_cad", "net_profit_cad", "cash_cad"):
        assert line in d, line


def test_operating_cost_is_read_from_real_agent_spend():
    db = _db()
    Registry(db).record_cost("market_radar", 0.12, kind="llm")
    Registry(db).record_cost("publishing", 0.03, kind="api")
    pl = Books(db).profit_and_loss()
    assert abs(pl.operating_costs_cad - 0.15) < 1e-6
    assert pl.cost_by_kind["llm"] == 0.12
    assert pl.net_profit_cad < 0, "cost with no revenue is a loss, and should read as one"


def test_tax_is_reserved_and_never_counted_as_ours():
    """Counting it as revenue is how a business discovers a liability it already spent."""
    db = _db()
    _with_sales(db, orders=10, price=12.5, fees=1.46)
    pl = Books(db).profit_and_loss()
    assert pl.net_sales_cad == 125.0
    assert abs(pl.tax_reserve_cad - 125.0 * TAX_RESERVE_RATE) < 0.01
    assert pl.net_profit_cad == round(125.0 - 14.6 - 0.0 - pl.tax_reserve_cad, 4)
    assert pl.cash_cad == pl.net_profit_cad


def test_contribution_margin_removes_only_the_costs_that_vary_with_selling():
    db = _db()
    _with_sales(db, orders=10, price=12.5, fees=1.46)
    _spend(db, "ads", 5.0, "ads")
    Registry(db).record_cost("market_radar", 0.9, kind="llm")
    pl = Books(db).profit_and_loss()
    # Fees and ads vary with selling; the radar's model spend does not.
    assert pl.contribution_margin_cad == round(125.0 - 14.6 - 5.0, 2)
    assert pl.operating_costs_cad > 5.0, "the radar's model spend is still an operating cost"


def test_refunds_reduce_net_sales():
    db = _db()
    _with_sales(db, orders=10, price=12.5, fees=1.46, refunds=25.0)
    pl = Books(db).profit_and_loss()
    assert pl.refunds_cad == 25.0
    assert pl.net_sales_cad == 100.0


# ---- unit economics --------------------------------------------------------


def test_cost_per_validated_pattern_is_computable_without_revenue():
    """Section 34's ratio catches an expensive production pipeline before any sale exists."""
    db = _db()
    Registry(db).record_cost("market_radar", 1.10, kind="llm")
    out = Books(db).unit_economics(products_validated=11, listings_drafted=11)
    assert out["cost_per_validated_pattern_cad"] == 0.1
    assert out["cost_per_listing_cad"] == 0.1


def test_cost_per_customer_is_none_not_zero_when_there_are_no_customers():
    out = Books(_db()).unit_economics(products_validated=11, listings_drafted=11)
    assert out["cost_per_acquired_customer_cad"] is None
    assert "undefined" in out["note"]


# ---- the CFO ---------------------------------------------------------------


def test_the_cfo_speaks_up_when_everything_is_nominally_fine():
    """A reviewer who only speaks during a crisis is a reviewer nobody has calibrated."""
    db = _db()
    Registry(db).record_cost("market_radar", 0.12, kind="llm")
    challenges = cfo_challenge(Books(db).profit_and_loss(), infra_monthly_cad=7.0)
    assert challenges
    assert any(c.subject == "revenue" for c in challenges)
    assert any(c.subject == "burn" for c in challenges)
    assert not [c for c in challenges if c.severity == "block"]


def test_infrastructure_above_the_owners_ceiling_is_a_block():
    pl = Books(_db()).profit_and_loss()
    blocks = [c for c in cfo_challenge(pl, infra_monthly_cad=45.0, infra_ceiling_cad=20.0)
              if c.severity == "block"]
    assert blocks and blocks[0].subject == "infrastructure"
    assert "bring the owner" in blocks[0].ask


def test_advertising_with_no_attributable_orders_is_a_block():
    db = _db()
    _spend(db, "ads", 30.0, "ads")
    blocks = [c for c in cfo_challenge(Books(db).profit_and_loss())
              if c.severity == "block"]
    assert any(c.subject == "paid media" for c in blocks), blocks
    assert any("pause" in c.ask for c in blocks)


def test_a_paused_budget_scope_stays_blocking():
    db = _db()
    with db.session() as s:
        s.add(SpendLimit(scope="ads:meta", daily_cap_cad=5.0, lifetime_cap_cad=50.0,
                         paused=True))
    with db.session() as s:
        limits = list(s.scalars(__import__("sqlalchemy").select(SpendLimit)))
    blocks = [c for c in cfo_challenge(Books(db).profit_and_loss(), limits=limits)
              if c.severity == "block"]
    assert any("ads:meta" in c.subject for c in blocks), blocks


# ---- trajectory ------------------------------------------------------------


def test_no_orders_produces_no_forecast():
    """The CA$100K figure is the one most likely to be repeated back as a projection."""
    t = trajectory(Books(_db()).profit_and_loss(), today=date(2026, 9, 17))
    assert t["is_forecast"] is False
    assert t["run_rate_cad"] is None and t["projection"] is None
    assert "not a forecast" in t["note"]
    assert t["target_annual_cad"] == ANNUAL_TARGET_CAD


def test_the_target_arithmetic_is_labelled_as_arithmetic():
    t = trajectory(Books(_db()).profit_and_loss())
    req = t["what_the_target_requires"]
    assert req["orders_per_day_at_aov_17"] > 0
    assert "arithmetic on the target" in t["note"]


def test_a_run_rate_appears_only_once_orders_exist_and_says_how_thin_it_is():
    db = _db()
    _with_sales(db, orders=12, price=12.5, fees=1.46)
    t = trajectory(Books(db).profit_and_loss(), today=date(2026, 9, 17))
    assert t["is_forecast"] is True
    assert t["run_rate_cad"] > 0
    assert t["observed_orders"] == 12
    assert "direction, not a number" in t["note"]


def test_a_forecast_never_claims_more_than_the_data_supports():
    db = _db()
    _with_sales(db, orders=1, price=12.5, fees=1.46)
    t = trajectory(Books(db).profit_and_loss())
    assert "1 orders" in t["note"] or "orders" in t["note"]
    assert t["share_of_target"] < 1.0


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
