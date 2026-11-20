"""#253/#256: a club is a promise of work not yet done, and a reward is for an action.

The cadence is the only one of #253's four questions that can be answered today, and it is
the one that ends clubs: month one ships what already existed, and month two needs a new
pattern, certified, on a date somebody else chose.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import club as C, referral as F  # noqa: E402
from brambleloop.commerce.reviews import GATING_PHRASES  # noqa: E402


# --- #253: the cadence is the one that ends clubs ------------------------------------------

def test_the_cadence_is_the_only_question_answerable_today():
    out = C.research_plan()
    assert out["answerable_today"] == ["delivery_cadence"]
    assert len(out["needs_customers_or_a_credential"]) == 3
    assert "ends clubs" in out["note"]


def test_a_cadence_with_no_headroom_does_not_fit():
    """A club that exactly fits its period has no room for the week somebody is ill, and
    there is always that week."""
    out = C.check_cadence(C.Cadence(period_days=30, product_lead_days=25))
    assert out["fits"] is False
    assert "month two is where this breaks" in out["why"]
    assert "there is always that week" in out["no_headroom_note"]


def test_a_cadence_with_room_fits():
    assert C.check_cadence(C.Cadence(period_days=30, product_lead_days=18))["fits"] is True


def test_two_products_a_period_needs_twice_the_room():
    out = C.check_cadence(C.Cadence(period_days=60, product_lead_days=25,
                                    products_per_period=2))
    assert out["fits"] is False
    assert out["needed_days"] == 65.0


def test_a_cadence_needs_a_period_and_a_lead_time():
    try:
        C.check_cadence(C.Cadence(period_days=0, product_lead_days=10))
    except C.ClubRefused as exc:
        assert "above zero" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a zero-length period was costed")


def test_unanswered_is_not_answered_no_and_neither_is_a_launch():
    out = C.may_launch({})
    assert out["may_launch"] is False
    assert len(out["unanswered"]) == 4
    assert "Unanswered is not answered no" in out["why"]


def test_a_cadence_that_does_not_fit_answers_its_own_question_no():
    out = C.may_launch({q: True for q in C.QUESTIONS},
                       cadence=C.Cadence(period_days=30, product_lead_days=25))
    assert out["may_launch"] is False
    assert out["answered_no"] == ["delivery_cadence"]


def test_all_four_answered_and_a_cadence_that_fits_may_launch():
    out = C.may_launch({q: True for q in C.QUESTIONS},
                       cadence=C.Cadence(period_days=30, product_lead_days=18))
    assert out["may_launch"] is True


def test_a_question_this_lane_does_not_ask_is_refused():
    try:
        C.may_launch({"vibes": True})
    except C.ClubRefused as exc:
        assert "not questions this lane asks" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented question was answered")


def test_the_nature_of_a_club_is_stated_before_anything_else():
    assert "liability before it is income" in C.NATURE
    assert "does not exist yet" in C.state()["note"]


# --- #256: an action, not an opinion -----------------------------------------------------------

def test_a_reward_is_for_something_a_customer_does():
    try:
        F.Mechanic("m", "writes_a_nice_review")
    except F.ReferralRefused as exc:
        assert "never for an opinion" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an opinion was made rewardable")


def test_showing_what_you_made_however_it_went_is_the_action():
    assert "however it went" in F.REWARDABLE["shows_finished_project"]


def test_copy_that_asks_for_a_rating_is_refused_with_the_other_modules_phrases():
    out = F.check(F.Mechanic("m", "shares_a_link", attribution="referral_code",
                             reward_cad=1.0, copy="leave a review and get a credit"),
                  contribution_per_customer_cad=5.0)
    assert out["ok"] is False
    assert any("third direction" in r for r in out["reasons"])
    assert "leave a review" in GATING_PHRASES


def test_a_mechanic_nothing_can_attribute_will_be_judged_favourably_anyway():
    out = F.check(F.Mechanic("m", "shares_a_link", reward_cad=1.0),
                  contribution_per_customer_cad=5.0)
    assert any("by the person who proposed it" in r for r in out["reasons"])


def test_a_reward_larger_than_the_margin_is_growth_that_loses_money():
    out = F.check(F.Mechanic("m", "shares_a_link", attribution="referral_code",
                             reward_cad=3.0), contribution_per_customer_cad=5.0)
    assert any("stopping at the top line" in r for r in out["reasons"])


def test_a_reward_with_nothing_to_check_it_against_is_refused():
    out = F.check(F.Mechanic("m", "shares_a_link", attribution="referral_code",
                             reward_cad=1.0))
    assert any("cost per acquired customer" in r for r in out["reasons"])


def test_a_clean_mechanic_runs():
    out = F.check(F.Mechanic("m", "shows_finished_project", attribution="unique_link",
                             reward_cad=1.0, copy="Show us what you made"),
                  contribution_per_customer_cad=5.0)
    assert out["ok"] is True


def test_an_unmeasured_programme_is_the_one_everybody_remembers_fondly():
    out = F.outcome(attributed_customers=None, contribution_cad=None, reward_spend_cad=0.0)
    assert out["measurable"] is False
    assert "remembers fondly" in out["why"]


def test_the_outcome_is_contribution_after_what_the_rewards_cost():
    out = F.outcome(attributed_customers=10, contribution_cad=50.0, reward_spend_cad=10.0)
    assert out["net_cad"] == 40.0 and out["worth_it"] is True
    assert F.outcome(attributed_customers=10, contribution_cad=5.0,
                     reward_spend_cad=10.0)["worth_it"] is False


def test_state_says_it_shares_its_refusals():
    assert F.state()["shares_its_refusals_with"] == "commerce.reviews"
    assert "a positive review" in F.state()["never_rewardable"]


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
