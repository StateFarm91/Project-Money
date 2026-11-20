"""Seasonal storefront transitions, and the three ways a takeover costs more than it buys.

v1.4.3 requirement 131. The surfaces turn over ahead of each buying window, scheduled from
the collection calendar rather than whenever somebody notices the date.

The failures held here are the ones a to-do list cannot catch: every surface transitioning on
one date, a takeover with no end so the Christmas banner is still up in February, and a shop
that reinvents its wordmark every quarter and calls the result seasonal.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.brand import takeover as T  # noqa: E402

CHRISTMAS = date(2026, 12, 25)
TODAY = date(2026, 9, 19)


def test_surfaces_do_not_all_transition_on_the_same_date():
    """Scheduling them together is how a shop ends up premature or late on everything."""
    plan = T.schedule("Christmas", CHRISTMAS, today=TODAY)

    dates = {r["transitions_on"] for r in plan["surfaces"]}
    assert len(dates) >= 3, dates
    order = [r["surface"] for r in plan["surfaces"]]
    assert order.index("banner") < order.index("thumbnails"), (
        "thumbnails turned over before the banner; a thumbnail saying December in October "
        "competes against what the buyer can still finish")


def test_every_takeover_has_an_end_date_scheduled_with_its_start():
    """The failure is not the banner going up late; it is the banner still being up in
    February, which says nobody is home more loudly than an empty shop does."""
    plan = T.schedule("Christmas", CHRISTMAS, today=TODAY)

    assert plan["ends_on"] > plan["event_date"]
    assert all(r["reverts_on"] == plan["ends_on"] for r in plan["surfaces"])


def test_a_takeover_left_up_after_its_occasion_is_named():
    plan = T.schedule("Christmas", date(2025, 12, 25), today=TODAY)

    assert plan["past_its_revert_date"], plan["note"]
    assert "says nobody is home" in plan["note"]


def test_an_overdue_transition_is_named_rather_than_counted():
    plan = T.schedule("Halloween", date(2026, 10, 31), today=TODAY)

    assert "banner" in plan["overdue"], plan["overdue"]
    assert "past their transition date" in plan["note"]


def test_the_dates_come_from_the_collection_calendar_not_from_taste():
    from brambleloop.seasonal.calendar import MILESTONES

    milestones = {name: days for name, days, _ in MILESTONES}
    leads = {s.key: s.lead_days for s in T.SURFACES}

    assert leads["banner"] == milestones["promotional_ramp"]
    assert leads["thumbnails"] == milestones["peak_window_opens"]
    assert leads["featured_collection"] == milestones["listing_indexing_date"]
    assert T.ENDS_DAYS_AFTER_EVENT == -milestones["clearance_or_evergreen"]


# ---- brand continuity -----------------------------------------------------


def test_a_takeover_that_changes_the_wordmark_is_refused():
    """A storefront that resets its identity every quarter is not seasonal, it is
    unrecognisable, and the timeliness is worth less than the recognition it spends."""
    try:
        T.plan("Christmas", CHRISTMAS, {"banner": "pine and cream, holly accent"},
               today=TODAY, changes_invariants=("wordmark",))
    except T.TakeoverRefused as e:
        assert "BREAKS_CONTINUITY" in str(e)
        assert "resets the shop" in str(e)
    else:
        raise AssertionError("a takeover reset the shop's identity and was scheduled")


def test_policy_text_is_an_invariant_because_it_is_a_promise():
    assert "policy_text" in T.CONTINUITY_INVARIANTS
    try:
        T.plan("Christmas", CHRISTMAS, {"banner": "pine and cream, holly accent"},
               today=TODAY, changes_invariants=("policy_text",))
    except T.TakeoverRefused as e:
        assert "promises rather than decoration" in str(e)
    else:
        raise AssertionError("seasonal copy was allowed to rewrite the policies")


def test_a_takeover_with_no_event_is_refused():
    """#131 schedules these from the calendar; a takeover with no event is a storefront
    change somebody felt like making."""
    try:
        T.plan("", CHRISTMAS, {"banner": "something festive"}, today=TODAY)
    except T.TakeoverRefused as e:
        assert "NOT_SCHEDULED" in str(e)
    else:
        raise AssertionError("an ad-hoc storefront change was scheduled as a takeover")


def test_a_listed_surface_that_says_nothing_is_refused():
    try:
        T.plan("Christmas", CHRISTMAS, {"banner": "   "}, today=TODAY)
    except T.TakeoverRefused as e:
        assert "SURFACE_EMPTY" in str(e)
    else:
        raise AssertionError("a surface was listed with no change and counted as planned")


def test_a_valid_plan_carries_its_schedule_and_what_it_held_constant():
    plan = T.plan("Christmas", CHRISTMAS,
                  {"banner": "pine and cream ground, single holly accent",
                   "thumbnails": "warm daylight, one red thread through the set"},
                  today=TODAY)

    assert set(plan["changes"]) == {"banner", "thumbnails"}
    assert "wordmark" in plan["continuity_held"]
    assert len(plan["surfaces"]) == 2


def test_the_calendar_rolls_up_what_is_overdue_across_events():
    roll = T.calendar({"Christmas": CHRISTMAS, "Halloween": date(2026, 10, 31)},
                      today=TODAY)

    assert roll["overdue_surfaces"] >= 1
    assert len(roll["takeovers"]) == 2
    assert roll["invariants"]["voice"]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
