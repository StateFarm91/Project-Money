"""#257: reading our own reviews, on a base too small to read.

Two things carry this file. Gating is not buying -- no money moves -- which is why it gets
written into a support template by a shop that would never buy a review. And a star
distribution over three reviews is not a light version of the analysis; it is a number
people act on.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import reviews as R  # noqa: E402
from brambleloop.commerce.buyer_trust import REQUIRED_DISCLOSURES  # noqa: E402
from brambleloop.intel.observe import RECURRING_AT  # noqa: E402


# --- the base is too small ----------------------------------------------------------------

def test_a_distribution_over_three_reviews_is_refused_rather_than_caveated():
    out = R.distribution([5, 5, 4])
    assert out["readable"] is False
    assert "one bad day away from 3.7" in out["why"]
    assert "a number people act on" in out["why"]


def test_themes_stay_readable_when_the_average_is_not():
    out = R.distribution([5, 5, 4])
    assert str(RECURRING_AT) in out["themes_are_still_readable"]


def test_a_real_base_reads():
    out = R.distribution([5] * 15 + [4] * 4 + [2])
    assert out["readable"] is True
    assert out["counts"][5] == 15
    assert out["share_below_four"] == 0.05


def test_something_that_is_not_a_star_rating_is_refused():
    try:
        R.distribution([5, 7])
    except R.ReviewRefused as exc:
        assert "not star ratings" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a seven-star review was counted")


# --- the routing is the useful part ----------------------------------------------------------

def test_a_misunderstanding_is_usually_a_missing_disclosure():
    """Routing it to the design queue rewrites a pattern that was correct."""
    out = R.route([R.Theme("expected_a_finished_item", "misunderstood", 5)])
    finding = out["findings"][0]
    assert finding["route_to"] == "listing"
    assert finding["disclosure"] == "digital_not_finished"
    assert "rewrites a pattern that was correct" in finding["why"]


def test_every_mapped_misunderstanding_points_at_a_real_disclosure():
    for theme, disclosure in R.MISUNDERSTANDING_TO_DISCLOSURE.items():
        assert disclosure in REQUIRED_DISCLOSURES, theme


def test_a_misunderstanding_with_no_disclosure_behind_it_goes_to_support():
    out = R.route([R.Theme("something_odd", "misunderstood", 4)])
    assert out["findings"][0]["route_to"] == "support"


def test_a_wish_is_a_question_about_what_to_make_next():
    out = R.route([R.Theme("a_matching_pillow", "wished_for", 4)])
    assert out["findings"][0]["route_to"] == "product_selection"


def test_praise_is_what_the_listing_may_say_because_they_said_it_first():
    out = R.route([R.Theme("clear_charts", "praised", 6)])
    assert out["findings"][0]["route_to"] == "listing_claims"
    assert "they said it first" in out["findings"][0]["why"]


def test_a_theme_below_the_floor_is_one_buyers_experience():
    out = R.route([R.Theme("clear_charts", "praised", 1)])
    assert out["findings"] == []
    assert out["below_the_floor"][0]["theme"] == "clear_charts"
    assert "nothing recurs often enough" in out["note"]


def test_a_category_nobody_named_is_refused():
    try:
        R.Theme("x", "vibes", 5)
    except R.ReviewRefused as exc:
        assert "is not a category" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented category was routed")


# --- gating is not buying ------------------------------------------------------------------------

def test_a_support_reply_that_asks_for_a_rating_is_refused():
    """The version a small shop actually commits, usually by accident, attached to the thing
    the buyer was owed anyway."""
    out = R.check_support_copy(
        "Here is the corrected file. If this helped, a review would mean a lot!")
    assert out["ok"] is False
    assert "no money moves" in out["why"]
    assert "a review would mean" in out["found"]


def test_a_reply_that_just_helps_passes():
    out = R.check_support_copy("Here is the corrected file, and sorry for the trouble.")
    assert out["ok"] is True


def test_every_way_of_asking_is_caught():
    for phrase in ("please leave a review", "a 5 star rating helps", "rate us if you can",
                   "could you update your review"):
        assert R.check_support_copy(phrase)["ok"] is False, phrase


def test_state_names_all_three_prohibited_verbs():
    out = R.state()
    joined = " ".join(out["never"])
    assert "fabricate" in joined and "purchase" in joined and "gate" in joined
    assert "no money moves" in out["note"]


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
