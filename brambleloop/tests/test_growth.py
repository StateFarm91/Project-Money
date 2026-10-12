"""The growth architecture, and the disciplines that stop it learning wrong things.

v1.4.3 requirements 231, 232, 234, 241, 263, 264, 265, 266, 270, 271, 272. None of this needs
a live customer to be built, and most of it needs to exist *before* the first one arrives:
an experiment whose threshold is chosen after the result is not an experiment, and by then
there is no way back to the version that would have been honest.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.growth import experiments as ex  # noqa: E402
from brambleloop.growth import loops, mix as portfolio  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/growth.sqlite")
    db.create_all()
    return db


# ---- portfolio ------------------------------------------------------------


def test_an_empty_portfolio_has_undefined_concentration_not_perfect_diversity():
    """#231. A divide-by-nothing reports perfect health for a shop with no products."""
    assert portfolio.concentration([])["measurable"] is False
    assert "not a diversified one" in portfolio.concentration([])["reason"]

    stressed = portfolio.stress_test([])
    assert stressed["testable"] is False
    assert "including the one where nothing goes wrong" in stressed["reason"]


def test_concentration_names_the_product_the_company_depends_on():
    """One product with dependants is not a portfolio, and the alarm says which one."""
    positions = [
        portfolio.Position("hero-throw", portfolio.HERO, revenue_cad=3000, family="throw"),
        portfolio.Position("coaster-set", portfolio.CORE, revenue_cad=400, family="coaster"),
        portfolio.Position("garland", portfolio.ENTRY, revenue_cad=300, family="garland"),
    ]
    c = portfolio.concentration(positions)
    assert c["top_sku"] == "hero-throw"
    assert c["alarm"] is True
    assert "one product with dependants" in c["note"]

    spread = portfolio.concentration([
        portfolio.Position(f"p{i}", portfolio.CORE, revenue_cad=500, family=f"f{i}")
        for i in range(8)])
    assert spread["alarm"] is False


def test_the_stress_test_asks_whether_the_target_survives_one_plausible_loss():
    """#270. Exploiting a winner stays aggressive; this measures what losing it would cost."""
    positions = [
        portfolio.Position("hero-throw", portfolio.HERO, revenue_cad=3500, family="throw"),
        portfolio.Position("second-throw", portfolio.CORE, revenue_cad=1200, family="throw"),
        portfolio.Position("coaster-set", portfolio.CORE, revenue_cad=800, family="coaster"),
    ]
    result = portfolio.stress_test(positions, target_cad=5000.0)

    assert result["testable"] is True
    top = [s for s in result["scenarios"] if s["scenario"] == "top SKU lost"][0]
    assert top["removed"] == "hero-throw"
    assert top["survives_target"] is False
    assert top["shortfall_cad"] > 0

    family = [s for s in result["scenarios"] if s["scenario"] == "top family lost"][0]
    assert family["removed"] == "throw"
    assert "top SKU lost" in result["fragile_to"]



def test_losing_the_top_season_and_the_top_channel_is_modelled_from_attributed_revenue():
    """#270, proof audit 2026-09-26: the season that carries the year and the channel that
    brings the buyers are the two losses a catalogue cannot see in its own SKU list."""
    positions = [
        portfolio.Position("xmas-throw", portfolio.HERO, revenue_cad=4000, family="throw"),
        portfolio.Position("coaster-set", portfolio.CORE, revenue_cad=2000, family="coaster"),
    ]
    result = portfolio.stress_test(
        positions, target_cad=5000.0,
        revenue_by_season={"Christmas": 4000, "": 2000},
        revenue_by_channel={"etsy_search": 5000, "pinterest": 700, "unknown": 300})
    by_name = {s["scenario"]: s for s in result["scenarios"]}
    assert by_name["top seasonal event lost"]["removed"] == "Christmas"
    assert by_name["top seasonal event lost"]["remaining_cad"] == 2000.0
    assert by_name["top traffic channel lost"]["removed"] == "etsy_search"
    assert {"top seasonal event lost", "top traffic channel lost"} <= set(result["fragile_to"])
    assert result["refused"] == []


def test_an_unattributed_season_or_channel_is_refused_rather_than_estimated():
    positions = [portfolio.Position("p", portfolio.CORE, revenue_cad=6000, family="f")]
    result = portfolio.stress_test(positions, revenue_by_season={"": 6000},
                                   revenue_by_channel={"unknown": 6000})
    refused = {r["scenario"]: r for r in result["refused"]}
    assert set(refused) == {"top seasonal event lost", "top traffic channel lost"}
    assert all(r["reading"] == "UNMEASURED" for r in refused.values())
    assert all(s["scenario"] not in refused for s in result["scenarios"])


def test_the_report_carries_a_diversification_plan_that_waits_for_revenue():
    """The route `/api/growth` serves: shape actions now, revenue actions once measured."""
    db = _db()
    out = portfolio.report(db)
    plan = out["diversification_plan"]
    assert any(a["action"] == "create a ENTRY product" for a in plan["actions"])
    assert all(a["reading"] == "measured" for a in plan["actions"])
    assert "revenue concentration" in plan["unmeasured"]
    assert "top seasonal event lost" in plan["unmeasured"]

    fragile = portfolio.stress_test(
        [portfolio.Position("xmas", portfolio.HERO, revenue_cad=5500, family="t")],
        revenue_by_season={"Christmas": 5500}, revenue_by_channel={"etsy_search": 5500})
    plan = portfolio.diversification_plan(
        portfolio.shape([portfolio.Position("xmas", portfolio.HERO, revenue_cad=5500)]),
        {"measurable": False}, fragile)
    actions = " ".join(a["action"] for a in plan["actions"])
    assert "evergreen CORE" in actions and "second acquisition channel" in actions

def test_a_role_that_does_not_exist_cannot_be_assigned():
    """#232. Roles are declared so a gap is something the system can see."""
    try:
        portfolio.Position("x", "FAVOURITE")
    except portfolio.PortfolioRefused as e:
        assert "not a portfolio role" in str(e)
    else:
        raise AssertionError("an invented role was accepted")

    shape = portfolio.shape([portfolio.Position(f"p{i}", portfolio.CORE) for i in range(10)])
    assert shape["skus"] == 10
    assert portfolio.ENTRY in shape["roles_absent"]
    assert portfolio.HERO in shape["roles_absent"]
    assert any(g["role"] == portfolio.ENTRY and g["missing_entirely"] for g in shape["gaps"])


# ---- experiments ----------------------------------------------------------


def test_a_threshold_declared_after_the_result_is_not_a_threshold():
    """#241. Every launch ships with the lines already drawn.

    Deciding afterwards what would have counted as success is how every experiment succeeds
    and nothing is learned — and it does not feel like cheating, which is what makes it
    common.
    """
    pack = ex.launch_pack(product="fir-yoke-cardigan", hypothesis="x", price_cad=12.0,
                          today=date(2026, 9, 19))
    assert len(pack) == 4
    for experiment in pack:
        assert experiment.success_threshold != experiment.failure_threshold
        assert experiment.minimum_sample > 0
        assert experiment.stop_on > date(2026, 9, 19)

    # An experiment with no sample floor concludes on its first data point.
    try:
        ex.Experiment(key="x", hypothesis="this should move the conversion rate upward",
                      metric="conversion_rate", design=ex.HOLDOUT,
                      success_threshold=0.02, failure_threshold=0.01,
                      minimum_sample=0, stop_on=date(2026, 12, 1))
    except ex.ExperimentRefused as e:
        assert "first data point" in str(e)
    else:
        raise AssertionError("an experiment with no minimum sample was registered")


def test_stopping_early_at_a_good_number_is_refused():
    """The most common way to find an effect that is not there."""
    pack = ex.launch_pack(product="p", hypothesis="x", price_cad=10.0)
    thumbnail = pack[0]

    verdict = ex.record(thumbnail, 0.09, 12)
    assert verdict["verdict"] == "undersampled"
    assert verdict["claimable"] is False
    assert "Stopping early" in verdict["reason"]
    assert thumbnail.state == ex.RUNNING

    passed = ex.record(thumbnail, 0.09, 2000)
    assert passed["verdict"] == "success"
    assert passed["claimable"] is True

    # And a concluded experiment cannot be fed more data until it says something nicer.
    try:
        ex.record(thumbnail, 0.5, 9000)
    except ex.ExperimentRefused as e:
        assert "oldest way to be wrong" in str(e)
    else:
        raise AssertionError("a concluded experiment accepted more data")


def test_a_design_with_no_control_may_never_claim_cause():
    """#266. Revenue that would have happened anyway is not a result.

    A pre/post comparison cannot separate the change from the week it happened in, and
    seasonality is the largest effect in this business.
    """
    pack = ex.launch_pack(product="p", hypothesis="x", price_cad=10.0)
    search = [e for e in pack if e.design == ex.PRE_POST][0]
    price = [e for e in pack if e.design == ex.HOLDOUT][0]

    assert search.supports_causal_claim is False
    assert price.supports_causal_claim is True

    verdict = ex.record(search, 900, 30)
    assert verdict["causal"] is False
    assert "never as cause" in verdict["claim"]

    causal = ex.record(price, 0.03, 900)
    assert causal["causal"] is True
    assert "supports a causal claim" in causal["claim"]


def test_scaling_is_gated_on_more_than_a_good_number():
    """#272. A product that converts well and generates tickets is ready to be fixed."""
    assert ex.scale_readiness({c: True for c in ex.SCALE_CONDITIONS})["ready"] is True

    partial = ex.scale_readiness({"product_quality_stable": True,
                                  "contribution_positive_or_bounded": True})
    assert partial["ready"] is False
    assert "support_load_acceptable" in partial["unmet"]
    assert "multiplies whatever is already true" in partial["note"]


# ---- growth loops ---------------------------------------------------------


def test_a_loop_earns_its_strength_from_traffic_rather_than_being_assigned_one():
    """#271. A channel somebody believes in behaves like a working one until it must carry."""
    db = _db()
    loops.seed(db)

    live = loops.from_db(db)
    assert len(live) == len(loops.REGISTRY)
    assert all(loop.strength == loops.UNTESTED for loop in live)
    assert loops.evidence_summary(live)["with_evidence"] == 0
    assert "writing down ambitions" in loops.evidence_summary(live)["note"]

    assert loops.observe(db, "pinterest", visits=40, orders=1) == loops.ATTEMPTED
    assert loops.evidence_summary(loops.from_db(db))["with_evidence"] == 0

    assert loops.observe(db, "pinterest", visits=300, orders=6) == loops.MEASURED
    assert loops.observe(db, "pinterest", visits=300, orders=6) == loops.REPEATABLE
    assert loops.evidence_summary(loops.from_db(db))["with_evidence"] == 1

    # A strength cannot be claimed on a sample too small to mean anything.
    try:
        loops.Loop("x", "X", strength=loops.MEASURED, visits=12)
    except loops.LoopRefused as e:
        assert "hopeful about" in str(e)
    else:
        raise AssertionError("a strength was claimed on twelve visits")

    try:
        loops.observe(db, "telepathy", visits=100)
    except loops.LoopRefused as e:
        assert "unknown loop" in str(e)
    else:
        raise AssertionError("traffic was recorded against a loop nobody declared")


def test_the_constraint_solver_ranks_by_gain_per_week_not_by_gap():
    """#264. The biggest gap is often the slowest to close.

    A week spent on the largest shortfall buys less than a week spent somewhere cheaper, so
    ranking by distance-from-target sends agents to the wrong place confidently.
    """
    empty = loops.constraint({})
    assert empty["current_monthly_cad"] == 0.0
    assert empty["primary_constraint"] == "qualified_visits"
    assert "doubling conversion doubles nothing" in empty["note"]

    running = loops.constraint({"qualified_visits": 4000, "conversion_rate": 0.015,
                                "aov_cad": 18.0, "repeat_rate": 0.05})
    ranked = running["ranked"]
    assert [r["gain_per_week_cad"] for r in ranked] == sorted(
        [r["gain_per_week_cad"] for r in ranked], reverse=True)
    assert running["primary_constraint"] == ranked[0]["term"]
    assert all(r["effort_weeks"] > 0 for r in ranked)
    assert running["current_monthly_cad"] > 0


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
