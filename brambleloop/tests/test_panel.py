"""Learning from the best shops without becoming one of them.

Requirements 215, 219, 220, 227. The failure #227 guards is one of aggregation rather than of
any single decision: every individual choice to match the benchmark is defensible -- they are
good, this is what good looks like, we should be at least this good -- and a year of
defensible choices is a shop that looks like a copy of a shop. There is no moment where
anybody decides to become derivative, which is why it needs a refusal rather than a caution.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.intel import panel as P  # noqa: E402

TODAY = date(2026, 9, 20)


def _member(ref: str, **kw) -> P.Member:
    args = dict(seller_ref=ref, categories=("blankets",), added_on=date(2026, 1, 1))
    args.update(kw)
    return P.Member(**args)


def _entry(**kw) -> P.ArenaEntry:
    args = dict(arena="stocking", benchmark_ref="mjs-stocking-1",
                what_makes_theirs_work="the cuff sits flat and photographs well at thumbnail",
                axes=("product_engineering",),
                how="a folded-hem cuff that cannot curl, worked in one piece")
    args.update(kw)
    return P.ArenaEntry(**args)


# ---- a panel of one is not a panel ----------------------------------------


def test_the_anchor_alone_is_not_a_panel():
    out = P.panel_state([_member(P.ANCHOR, is_anchor=True)], on=TODAY)
    assert out["is_a_panel"] is False
    assert "one shop's aesthetic with a formal name" in out["why"]


def test_three_sellers_make_a_panel():
    members = [_member(P.ANCHOR, is_anchor=True), _member("b"), _member("c")]
    out = P.panel_state(members, on=TODAY)
    assert out["is_a_panel"] is True and out["count"] == 3
    assert out["anchor"] == [P.ANCHOR]


def test_the_panel_changes_over_time():
    members = [_member(P.ANCHOR, is_anchor=True), _member("b"),
               _member("c", removed_on=date(2026, 6, 1)),
               _member("d", added_on=date(2026, 12, 1))]
    out = P.panel_state(members, on=TODAY)
    assert out["members"] == [P.ANCHOR, "b"]
    assert "members join and leave" in out["changing"]


def test_a_panel_is_read_per_category():
    members = [_member(P.ANCHOR, is_anchor=True, categories=("blankets", "hats")),
               _member("b", categories=("hats",)),
               _member("c", categories=("blankets",))]
    assert P.panel_state(members, on=TODAY, category="hats")["count"] == 2
    assert P.panel_state(members, on=TODAY, category="blankets")["count"] == 2


def test_a_member_with_no_categories_teaches_nothing_in_particular():
    try:
        _member("b", categories=())
    except P.PanelRefused as e:
        assert "a list of good shops" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a panel member was added with nothing to teach")


# ---- a mechanism needs more than one shop ---------------------------------


def test_one_shop_doing_something_is_a_preference():
    out = P.mechanism_is_learnable(mechanism="folded hem cuff", seen_in=(P.ANCHOR,))
    assert out["learnable"] is False
    assert f"best-of-{P.ANCHOR}" in out["why"]
    assert "one more seller" in out["what_would_settle_it"]


def test_two_independent_sellers_make_it_a_mechanism():
    out = P.mechanism_is_learnable(mechanism="folded hem cuff", seen_in=(P.ANCHOR, "b"))
    assert out["learnable"] is True


def test_the_same_seller_twice_is_still_one_seller():
    out = P.mechanism_is_learnable(mechanism="x", seen_in=(P.ANCHOR, P.ANCHOR, P.ANCHOR))
    assert out["learnable"] is False
    assert out["sellers"] == [P.ANCHOR]


# ---- the bar moves up and never down --------------------------------------


def _change(**kw) -> P.StandardChange:
    args = dict(standard="thumbnail_legibility", from_value=0.7, to_value=0.8,
                higher_is_better=True, prompted_by="observation mjs-2026-09-12",
                because="their gallery reads at 170px and ours does not")
    args.update(kw)
    return P.StandardChange(**args)


def test_a_benchmark_improving_raises_the_bar():
    out = P.move_bar(_change())
    assert out["outcome"] == P.RAISED
    assert "the competitive bar is dynamic" in out["why"]


def test_a_standard_is_never_lowered_because_a_competitor_slipped():
    out = P.move_bar(_change(to_value=0.5))
    assert out["outcome"] == P.REFUSED_LOWERING
    assert "race to the bottom with a paper trail" in out["why"]


def test_lowering_is_refused_on_a_lower_is_better_standard_too():
    out = P.move_bar(_change(standard="support_cases_per_order", from_value=0.1,
                             to_value=0.2, higher_is_better=False))
    assert out["outcome"] == P.REFUSED_LOWERING


def test_tightening_a_lower_is_better_standard_is_a_raise():
    out = P.move_bar(_change(standard="support_cases_per_order", from_value=0.2,
                             to_value=0.1, higher_is_better=False))
    assert out["outcome"] == P.RAISED


def test_a_standard_change_names_the_observation_behind_it():
    try:
        _change(prompted_by="  ")
    except P.PanelRefused as e:
        assert "not a why anybody can re-examine" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a standard moved on nothing")


def test_the_refusal_says_where_a_genuinely_wrong_standard_gets_fixed():
    out = P.move_bar(_change(to_value=0.5))
    assert "does not travel through a benchmark observation" in (
        out["if_the_standard_is_genuinely_wrong"])


# ---- entering an arena ----------------------------------------------------


def test_sharing_an_arena_with_an_elite_seller_is_not_a_reason_to_stay_out():
    out = P.may_enter(_entry())
    assert out["may_enter"] is True
    assert "not a reason to stay out of it" in out["why"]


def test_parity_alone_is_refused():
    out = P.may_enter(_entry(axes=(P.PARITY,)))
    assert out["may_enter"] is False
    assert "anybody decides to become derivative" in out["why"]
    assert out["what_would_allow_it"] == sorted(P.SUPERIORITY_AXES)


def test_parity_plus_a_real_axis_is_permitted():
    out = P.may_enter(_entry(axes=(P.PARITY, "usability")))
    assert out["may_enter"] is True and out["axes"] == ["usability"]


def test_an_axis_named_without_a_mechanism_is_an_intention():
    out = P.may_enter(_entry(how="  "))
    assert out["may_enter"] is False
    assert "do not survive contact with a design review" in out["why"]


def test_an_invented_axis_is_refused_because_better_is_what_everybody_thinks():
    try:
        _entry(axes=("better",))
    except P.PanelRefused as e:
        assert "better is what everybody thinks they are doing" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an open-ended axis was accepted")


def test_entering_blind_is_refused():
    try:
        _entry(what_makes_theirs_work="")
    except P.PanelRefused as e:
        assert "entering it blind" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an arena was entered without knowing why the incumbent wins")


# ---- the floor is not the ceiling -----------------------------------------


def test_matching_a_competitor_is_refused_as_an_objective():
    for objective in ("match MJs on thumbnail quality",
                      "reach parity with the benchmark on chart clarity",
                      "keep up with the leader",
                      "be as good as the incumbent"):
        out = P.ceiling_check(objective=objective)
        assert out["permitted"] is False, objective
        assert "white space" in out["why"]


def test_matching_this_shops_own_last_release_is_ordinary_consistency():
    out = P.ceiling_check(objective="as good as our last release")
    assert out["permitted"] is True
    assert "ordinary consistency" in out["why"]


def test_an_objective_of_its_own_is_permitted():
    assert P.ceiling_check(objective="the clearest chart on Etsy")["permitted"] is True


def test_an_unstated_objective_cannot_be_checked():
    try:
        P.ceiling_check(objective="  ")
    except P.PanelRefused as e:
        assert "cannot be checked against anything" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a blank objective passed")


def test_state_names_the_aggregation_failure():
    out = P.state()
    assert set(out["requirements"]) == {215, 219, 220, 227}
    assert "one of aggregation" in out["note"]
    assert any("nothing but parity" in r for r in out["refuses"])


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
