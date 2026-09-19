"""A major holiday is attacked with faster products as the slow ones close. It is not dropped.

The owner's correction on 2026-09-19, held as tests so it never has to be given again. The
make-time interval work established that a 150-hour flagship cannot be finished for this
Christmas. A careless reader turns that into "Christmas is closed", and those are different
sentences separated by most of the commercial year.

So what is tested here is the difference: that the engine retires *product classes* one at a
time, that capacity moves into the fastest open lane rather than out of the occasion, that a
closed launch lane is not a closed occasion, and that the shift happens by arithmetic rather
than by somebody remembering in November.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.seasonal import compression as C  # noqa: E402

CHRISTMAS = date(2026, 12, 25)


def _at(days_out: int) -> dict:
    return C.programme("Christmas", today=CHRISTMAS - timedelta(days=days_out))


# ---- the correction itself ------------------------------------------------


def test_a_retired_flagship_does_not_retire_christmas():
    plan = _at(97)

    assert [r["lane"] for r in plan["retired_classes"]] == ["FLAGSHIP"]
    assert plan["mix"]["open_lanes"], "the occasion was closed by one product class"
    assert plan["capacity"]["share"] >= C.MIN_PRIORITY_SHARE
    assert "never about the occasion" in plan["note"]


def test_a_retirement_is_scoped_to_one_class_and_one_occasion():
    """So that 'the flagship is impossible' cannot be read a fortnight later as 'Christmas
    is closed'."""
    for row in _at(97)["retired_classes"]:
        assert row["scope"] == "this product class for this occasion only"
        assert row["last_optimistic_launch"]


def test_capacity_moves_into_the_fastest_open_lane_as_the_slow_ones_close():
    """The behaviour the owner should never have to ask for twice: the mix shifts from
    medium to short to quick, and it falls out of the arithmetic rather than a decision."""
    leaders = {d: _at(d)["mix"]["leading_lane"] for d in (150, 120, 75, 45)}

    assert leaders[150] == "MEDIUM"
    assert leaders[120] in ("SHORT", "MEDIUM")
    assert leaders[75] == "QUICK"
    assert leaders[45] == "QUICK"

    order = ["QUICK", "SHORT", "MEDIUM", "LONG", "FLAGSHIP"]
    assert order.index(leaders[150]) > order.index(leaders[75]), (
        "the mix did not get faster as the runway shrank")


def test_a_lane_that_closes_hands_its_share_to_the_lanes_behind_it():
    wide, narrow = _at(120)["mix"]["shares"], _at(60)["mix"]["shares"]

    assert narrow["QUICK"] > wide["QUICK"]
    assert narrow.get("MEDIUM", 0.0) == 0.0
    assert round(sum(narrow.values()), 2) == 1.0, "capacity leaked out of the occasion"


def test_urgency_outranks_comfort_because_the_tight_lane_is_the_one_about_to_be_lost():
    plan = _at(150)
    shares = plan["mix"]["shares"]

    assert shares["MEDIUM"] > shares["QUICK"], (
        "a comfortable lane with months of runway outranked the one that shuts first")


# ---- a closed launch lane is not a closed occasion ------------------------


def test_the_programme_merchandises_when_nothing_can_still_be_launched():
    """A company that stops working on Christmas in late November stops in the fortnight it
    earns the money."""
    plan = _at(30)

    assert plan["mix"]["open_lanes"] == []
    assert plan["mode"]["mode"] == C.MERCHANDISE
    assert plan["capacity"]["share"] == C.MIN_PRIORITY_SHARE
    assert "not a closed occasion" in plan["note"]


def test_the_reservation_is_released_only_after_the_buyers_last_make_date():
    plan = _at(10)

    assert plan["mode"]["mode"] == C.POST_OCCASION
    assert plan["capacity"]["share"] == 0.0
    assert "next year" in plan["note"]


def test_a_priority_programme_cannot_be_left_with_no_capacity_while_lanes_are_open():
    plan = _at(97)
    plan["capacity"]["share"] = 0.0
    try:
        C.check(plan)
    except C.CompressionRefused as e:
        assert "rounding error" in str(e)
    else:
        raise AssertionError("a priority programme was stood down while lanes were open")


def test_a_priority_programme_cannot_be_stood_down_in_its_selling_fortnight():
    plan = _at(30)
    plan["capacity"]["share"] = 0.0
    try:
        C.check(plan)
    except C.CompressionRefused as e:
        assert "earns the money" in str(e)
    else:
        raise AssertionError("the reservation was released in the merchandising window")


# ---- christmas is a taxonomy ----------------------------------------------


def test_christmas_is_not_blankets():
    plan = _at(97)
    departments = {a["department"] for a in plan["arenas"]}

    for expected in ("stockings", "ornaments", "home_decor", "bags", "seasonal_gift", "hats"):
        assert expected in departments, expected
    assert len(departments) > 2


def test_a_department_whose_lanes_have_all_retired_drops_out_by_itself():
    late = _at(60)
    departments = {a["department"] for a in late["arenas"]}

    assert "blankets" not in departments, "a blanket was still being pursued at 60 days"
    assert "ornaments" in departments
    assert any(row["department"] == "blankets" for row in late["closed_arenas"])


def test_a_priority_programme_with_open_lanes_must_name_something_to_pursue():
    plan = _at(97)
    plan["arenas"] = []
    try:
        C.check(plan)
    except C.CompressionRefused as e:
        assert "are not blankets" in str(e)
    else:
        raise AssertionError("an occasion with open lanes named no department")


def test_a_bundle_is_only_proposed_where_its_members_share_a_lane():
    """Departments in different lanes make a bundle whose slowest member decides the launch
    date, which is how a quick make ends up waiting for a throw."""
    for bundle in _at(97)["bundles"]:
        assert len(bundle["departments"]) >= 2
        assert bundle["lane"] in C.LANE_ORDER


# ---- preparation and next year --------------------------------------------


def test_preparation_starts_before_the_launch_it_serves():
    plan = _at(150)
    by_lane = [row for row in plan["preparation"] if row["lane"] == "MEDIUM"]

    assert by_lane, plan["preparation"][:2]
    lane = next(s for s in plan["lanes"] if s["lane"] == "MEDIUM")
    for row in by_lane:
        assert row["starts_on"] < lane["latest_optimistic_launch"], row
    assert {row["stream"] for row in by_lane} == set(C.PREPARATION_LEADS)


def test_search_language_is_mapped_before_the_copy_is_written():
    leads = C.PREPARATION_LEADS
    assert leads["search_language"][0] > leads["listing_copy"][0], (
        "copy would be written before buyer language was mapped, which writes it in ours")


def test_next_years_flagship_is_started_early_and_capped():
    plan = _at(97)
    track = plan["next_year"]

    assert track["tracked"] is True
    assert "FLAGSHIP" in track["may_start"]
    assert track["capacity_cap"] == C.NEXT_YEAR_FLAGSHIP_CAP
    assert track["capacity_cap"] < plan["capacity"]["share"], (
        "next year's flagship could take more capacity than this year's occasion")


def test_an_uncalibrated_plan_says_so():
    assert _at(97)["calibrated"] is False


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
