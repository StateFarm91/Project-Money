"""A year with many occasions in it, and the constant that says this is a Christmas company.

Requirement 33, whose merge instruction is the point: preserve Christmas as the current
campaign, not the company identity. `compression.PRIORITY_PROGRAMMES` is `{"Christmas": 0.45}`
-- a constant naming one occasion and granting it nearly half of engineering capacity
permanently, read by five modules. That is the Christmas Strike Team in code, and no amount of
rolling-wave machinery wrapped around it changes what it says.

So the tests here are mostly about the score having no favourites, the evergreen floor being
taken before anything is granted, and an emergency being structurally unable to reach a gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.seasonal import engine as E  # noqa: E402


def _factors(**overrides) -> dict:
    out = {k: 0.8 for k in E.FACTORS}
    out.update(overrides)
    return out


def _opp(event: str = "Christmas", days: int = 96, **overrides) -> E.Opportunity:
    return E.Opportunity(event=event, days_away=days, factors=_factors(**overrides))


# ---- the score has no favourites ------------------------------------------


def test_the_allocation_is_invariant_under_renaming_every_occasion():
    """The strongest form of "no favourites": permute the names and nothing moves.

    The first version of this test scanned the source for occasion names and failed on a
    docstring that used Christmas as an example -- which is prose, not a favour. What matters
    is that no name changes an outcome, and that is a property of the behaviour."""
    first = E.allocate([_opp("Christmas", days=96, expected_demand=0.9),
                        _opp("Halloween", days=96, expected_demand=0.4)])
    renamed = E.allocate([_opp("weddings", days=96, expected_demand=0.9),
                          _opp("graduation", days=96, expected_demand=0.4)])
    assert first["seasonal"]["Christmas"] == renamed["seasonal"]["weddings"]
    assert first["seasonal"]["Halloween"] == renamed["seasonal"]["graduation"]
    assert first["evergreen"] == renamed["evergreen"]


def test_an_occasion_outside_the_listed_universe_is_scored_like_any_other():
    """The requirement's universe ends with "and other evidence-backed occasions", so an
    occasion that shows up in the evidence must not need a code change to be worked."""
    assert "eclipse viewing party" not in E.UNIVERSE
    out = E.allocate([_opp("eclipse viewing party", days=96)])
    assert out["seasonal"]["eclipse viewing party"] > 0


def test_two_identical_occasions_score_identically_whatever_they_are_called():
    a = _opp("Christmas")
    b = _opp("Valentine's", days=96)
    assert a.score == b.score
    shares = E.allocate([a, b])["seasonal"]
    assert shares["Christmas"] == shares["Valentine's"]


def test_the_factors_multiply_because_they_are_conjunctive():
    """An average would let six good factors carry one fatal one."""
    hopeless = _opp(time_remaining=0.0)
    assert hopeless.score == 0.0
    assert hopeless.factors["expected_demand"] == 0.8, "demand is still strong and irrelevant"


def test_the_binding_factor_is_named():
    out = _opp(product_fit=0.1).to_dict()
    assert out["binding_factor"] == "product_fit"
    assert "construction vocabulary" in out["binding_means"]


def test_a_missing_factor_is_refused_rather_than_defaulted():
    try:
        E.Opportunity(event="Easter", days_away=200,
                      factors={k: 0.5 for k in list(E.FACTORS)[:5]})
    except E.EngineRefused as e:
        assert "silently set to one" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a factor was left out and the score carried on")


def test_a_factor_above_one_could_manufacture_a_score():
    try:
        _opp(expected_demand=3.0)
    except E.EngineRefused as e:
        assert "manufacture a score" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a factor above one was accepted")


def test_every_factor_the_requirement_names_is_present():
    for name in ("expected_demand", "achievable_visibility", "contribution_potential",
                 "time_remaining", "product_fit", "competitive_weakness",
                 "production_feasibility"):
        assert name in E.FACTORS
    assert len(E.FACTORS) == 7


# ---- three horizons -------------------------------------------------------


def test_the_three_horizons_the_requirement_names_exist():
    assert E.HORIZONS == (E.NOW, E.NEXT, E.LATER)


def test_an_occasion_moves_between_horizons_as_the_year_turns():
    assert _opp(days=20).horizon == E.NOW
    assert _opp(days=96).horizon == E.NEXT
    assert _opp(days=300).horizon == E.LATER


def test_the_allocation_reports_every_horizon_even_when_empty():
    out = E.allocate([_opp(days=20)])
    assert set(out["by_horizon"]) == set(E.HORIZONS)
    assert out["by_horizon"][E.LATER] == []


def test_the_seasonal_universe_covers_the_occasions_the_requirement_lists():
    for event in ("Christmas", "Valentine's", "Easter", "Mother's Day", "Halloween",
                  "Canadian Thanksgiving", "weddings", "baby showers", "back-to-school"):
        assert event in E.UNIVERSE


# ---- the evergreen floor --------------------------------------------------


def test_evergreen_never_drops_to_zero_however_strong_the_season():
    out = E.allocate([_opp(**{k: 1.0 for k in E.FACTORS})])
    assert out["evergreen"] == E.EVERGREEN_FLOOR
    assert out["seasonal"]["Christmas"] == round(1.0 - E.EVERGREEN_FLOOR, 4)


def test_the_floor_survives_the_rounding_of_three_equal_shares():
    """Rounding each share independently put three equal occasions at 0.8001 against a pool
    of 0.8, which eats the evergreen floor from above. Small, and it is the one number here
    that has to hold."""
    out = E.allocate([_opp("a"), _opp("b", days=96), _opp("c", days=96)])
    assert round(out["evergreen"] + sum(out["seasonal"].values()), 4) <= 1.0
    assert out["seasonal_granted"] <= round(1.0 - E.EVERGREEN_FLOOR, 4)
    assert "rounded through when the arithmetic is tight" in out["floor_taken_first"]


def test_the_floor_holds_across_many_awkward_share_counts():
    for count in range(1, 12):
        out = E.allocate([_opp(f"e{i}", days=96) for i in range(count)])
        assert out["seasonal_granted"] <= round(1.0 - E.EVERGREEN_FLOOR, 4), count


def test_a_zero_floor_is_refused():
    try:
        E.allocate([_opp()], evergreen_floor=0.0)
    except E.EngineRefused as e:
        assert "nothing to sell in February" in str(e)
    else:  # pragma: no cover
        raise AssertionError("evergreen was allowed to reach zero")


def test_no_occasion_scoring_leaves_the_whole_pool_with_evergreen():
    out = E.allocate([_opp(time_remaining=0.0)])
    assert out["seasonal_granted"] == 0.0
    assert "capacity across occasions nothing supports" in out["why"]


def test_the_evergreen_categories_are_the_durable_ones():
    for category in ("baby", "amigurumi", "blankets", "accessories", "garments"):
        assert category in E.EVERGREEN_CATEGORIES


# ---- squads stand down by arithmetic --------------------------------------


def test_a_squad_stands_down_when_its_score_falls_below_the_alternatives():
    weak = _opp("Halloween", expected_demand=0.2, product_fit=0.2)
    strong = _opp("Christmas")
    out = E.squad_state(weak, currently_active=True, alternatives=[strong])
    assert out["state"] == E.STAND_DOWN
    assert "permanent cost justified once" in out["why"]


def test_a_squad_stays_active_while_it_is_the_best_use_of_the_capacity():
    strong = _opp("Christmas")
    weak = _opp("Halloween", expected_demand=0.2)
    out = E.squad_state(strong, currently_active=True, alternatives=[weak])
    assert out["state"] == E.ACTIVE


def test_a_squad_that_does_not_warrant_existing_names_its_binding_factor():
    out = E.squad_state(_opp("Easter", production_feasibility=0.05),
                        currently_active=False, alternatives=[])
    assert out["state"] == E.NOT_WARRANTED
    assert out["binding"] == "production_feasibility"


def test_standing_down_does_not_need_anybody_to_notice():
    """The threshold is a constant, and the comparison is arithmetic."""
    assert isinstance(E.SQUAD_STANDDOWN_SCORE, float)
    below = _opp("x", expected_demand=0.1, product_fit=0.1, achievable_visibility=0.1)
    assert below.score < E.SQUAD_STANDDOWN_SCORE
    assert E.squad_state(below, currently_active=True,
                         alternatives=[])["state"] == E.STAND_DOWN


# ---- reuse without cloning ------------------------------------------------


def test_a_construction_primitive_may_cross_seasons():
    out = E.may_reuse("construction_primitive", from_season="Halloween",
                      to_season="Christmas")
    assert out["may_reuse"] is True
    assert "how something was built, not what it was" in out["why"]


def test_a_commercial_lesson_may_cross():
    assert E.may_reuse("commercial_lesson", from_season="Halloween",
                       to_season="Christmas")["may_reuse"] is True


def test_recolouring_last_octobers_product_is_the_named_failure():
    for kind in ("design", "motifs", "colourway", "listing_copy"):
        out = E.may_reuse(kind, from_season="Halloween", to_season="Christmas")
        assert out["may_reuse"] is False, kind
    out = E.may_reuse("design", from_season="Halloween", to_season="Christmas")
    assert "it is the product again" in out["why"]


def test_an_unclassified_thing_is_refused_rather_than_crossing_by_default():
    try:
        E.may_reuse("mood", from_season="Halloween", to_season="Christmas")
    except E.EngineRefused as e:
        assert "the default is the one that matters" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unclassified thing crossed seasons")


def test_reuse_is_a_question_about_crossing():
    try:
        E.may_reuse("design", from_season="Christmas", to_season="Christmas")
    except E.EngineRefused as e:
        assert "crossing seasons" in str(e)
    else:  # pragma: no cover
        raise AssertionError("reuse within one season was treated as crossing")


# ---- emergency mode cannot reach a gate -----------------------------------


def test_a_breakout_asked_to_move_a_gate_is_refused():
    for gate in E.BREAKOUT_MAY_NEVER_MOVE:
        try:
            E.breakout(sku="p1", velocity=30.0, baseline=5.0, requests=(gate,))
        except E.EngineRefused as e:
            assert "non-bypassable" in str(e), gate
        else:  # pragma: no cover
            raise AssertionError(f"a breakout moved {gate}")


def test_the_refusal_is_structural_rather_than_an_approval_somebody_grants():
    try:
        E.breakout(sku="p1", velocity=30.0, baseline=5.0, requests=("quality_gate",))
    except E.EngineRefused as e:
        assert "rather than an approval step somebody can grant" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a gate move was approvable")


def test_a_breakout_may_move_allocation():
    out = E.breakout(sku="p1", velocity=30.0, baseline=5.0,
                     requests=("capacity_allocation", "bundle_candidates"))
    assert out["breakout"] is True and out["multiple"] == 6.0


def test_a_product_doing_slightly_better_than_usual_is_not_an_emergency():
    out = E.breakout(sku="p1", velocity=6.0, baseline=5.0)
    assert out["breakout"] is False
    assert "slightly better than usual" in out["why"]


def test_a_first_product_has_no_baseline_to_exceed():
    out = E.breakout(sku="p1", velocity=30.0, baseline=0.0)
    assert out["breakout"] is False
    assert "every first product an emergency" in out["why"]


def test_an_emergency_mode_names_its_exit():
    out = E.breakout(sku="p1", velocity=30.0, baseline=5.0)
    assert "the new normal allocation, renamed" in out["exit"]


def test_a_request_outside_the_breakouts_authority_is_refused():
    try:
        E.breakout(sku="p1", velocity=30.0, baseline=5.0, requests=("hiring",))
    except E.EngineRefused as e:
        assert "outside a breakout's authority" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a breakout reached outside its scope")


# ---- what is still to replace ---------------------------------------------


def test_state_names_the_constant_this_requirement_exists_to_replace():
    out = E.state()
    assert out["requirement"] == 33
    assert "PRIORITY_PROGRAMMES" in out["still_to_replace"]
    assert "Christmas Strike Team in code" in out["still_to_replace"]


def test_the_constant_it_names_is_really_still_there():
    """The claim in state() is checked rather than asserted, so it cannot go stale silently."""
    from brambleloop.seasonal.compression import PRIORITY_PROGRAMMES

    assert "Christmas" in PRIORITY_PROGRAMMES, (
        "if this fails the migration happened and state()['still_to_replace'] is now wrong")


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
