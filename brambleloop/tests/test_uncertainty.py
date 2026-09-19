"""Make-time as a distribution, and the claim that had to be withdrawn.

The lead-time engine chains make-time, buffers and ramp into a launch date. Every term is an
assumption, and the chain produced a single date that was then reported as a fact — and then
as an *impossibility*: "LONG and FLAGSHIP Christmas work is arithmetically impossible."

The arithmetic is exact. Its inputs are guesses. This build refuses that move everywhere else
— unmeasured is not zero, absent is not inferred, a benchmark is not a measurement — and then
made it in the one place where the output is a decision about a whole season.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.seasonal import calendar as C  # noqa: E402
from brambleloop.seasonal import uncertainty as U  # noqa: E402
from brambleloop.seasonal.leadtime import compile_launch  # noqa: E402

TODAY = date(2026, 9, 19)
CHRISTMAS = date(2026, 12, 25)


def test_the_interval_is_wide_while_nobody_has_been_timed():
    """No Brambleloop maker has ever been timed, and the interval says so."""
    blind = U.interval(90.0)
    assert blind.calibrated is False
    assert blind.low_hours < 90.0 < blind.high_hours
    assert "no maker has been timed" in blind.to_dict()["basis"]
    # Asymmetric, because craft overruns: a good project finishes a little early and a bad
    # one finishes very late. A symmetric band would be a third wrong claim dressed as rigour.
    assert (blind.high_hours - 90.0) > (90.0 - blind.low_hours) * 2


def test_only_samples_narrow_the_interval_and_it_never_reaches_a_point():
    few = U.interval(90.0, samples=3)
    many = U.interval(90.0, samples=U.SAMPLES_FOR_FULL_WEIGHT)
    assert few.spread > many.spread
    assert many.calibrated is True

    # Even fully calibrated it stays an interval: two people making the same object differ,
    # and a tighter band would claim to know the maker rather than the pattern.
    assert many.low_hours < 90.0 < many.high_hours
    assert U.interval(90.0, samples=999).spread == many.spread


def test_impossible_requires_the_optimistic_bound_to_have_passed():
    """The correction, stated as the rule it is."""
    still_possible = U.feasibility(days_available=97, days_needed_point=135,
                                   days_needed_low=95, days_needed_high=243)
    assert still_possible["verdict"] == U.HIGH_RISK
    assert still_possible["blocks"] is False
    assert "runway is insufficient" in still_possible["meaning"]

    genuinely_closed = U.feasibility(days_available=97, days_needed_point=202,
                                     days_needed_low=134, days_needed_high=382)
    assert genuinely_closed["verdict"] == U.INFEASIBLE
    assert genuinely_closed["blocks"] is True
    assert genuinely_closed["shortfall_against_optimistic"] == 37
    assert "cannot establish impossibility" in genuinely_closed["note"]


def test_a_long_christmas_project_is_high_risk_rather_than_impossible():
    """The specific claim that was wrong, as a regression test.

    A 90-hour project reads as impossible on a point estimate built from an assumed seven
    crochet hours a week, and reads as high risk once the interval is honest about never
    having timed anybody.
    """
    plan = compile_launch("Christmas", CHRISTMAS, make_hours=90.0)
    graded = plan.feasibility(TODAY)
    assert graded["verdict"] == U.HIGH_RISK
    assert graded["blocks"] is False
    # The point estimate's date has indeed passed -- which is what produced the wrong claim.
    assert plan.latest_effective_launch < TODAY
    assert plan.latest_optimistic_launch >= TODAY


def test_a_flagship_christmas_project_genuinely_is_closed():
    """And the correction does not become an excuse: some windows really have shut."""
    plan = compile_launch("Christmas", CHRISTMAS, make_hours=150.0)
    graded = plan.feasibility(TODAY)
    assert graded["verdict"] == U.INFEASIBLE
    assert graded["blocks"] is True
    assert plan.latest_optimistic_launch < TODAY


def test_the_calendar_reads_a_window_as_a_gradient_rather_than_a_cliff():
    assert C.heaviest_launchable_lane(97, today=TODAY) == "LONG"

    verdicts = {r["lane"]: r["verdict"] for r in C.lane_feasibility(97, today=TODAY)}
    assert verdicts["QUICK"] == U.COMFORTABLE
    assert verdicts["SHORT"] == U.COMFORTABLE
    assert verdicts["MEDIUM"] == U.TIGHT
    assert verdicts["LONG"] == U.HIGH_RISK
    assert verdicts["FLAGSHIP"] == U.INFEASIBLE


def test_a_near_event_still_closes_the_heavy_lanes():
    """The interval widens what is attemptable; it does not abolish the calendar."""
    assert C.heaviest_launchable_lane(20, today=TODAY) in (None, "QUICK")
    verdicts = {r["lane"]: r["verdict"] for r in C.lane_feasibility(20, today=TODAY)}
    assert verdicts["FLAGSHIP"] == U.INFEASIBLE
    assert verdicts["LONG"] == U.INFEASIBLE


def test_samples_move_the_verdict_because_that_is_the_only_thing_that_should():
    """More planning does not narrow an interval. Timing somebody does."""
    blind = compile_launch("Christmas", CHRISTMAS, make_hours=45.0).feasibility(TODAY)
    timed = compile_launch("Christmas", CHRISTMAS, make_hours=45.0,
                           samples=U.SAMPLES_FOR_FULL_WEIGHT).feasibility(TODAY)
    assert blind["days_needed"]["pessimistic"] > timed["days_needed"]["pessimistic"]
    assert timed["verdict"] in (U.COMFORTABLE, U.TIGHT)


def test_the_sample_count_comes_from_passed_physical_tests():
    from brambleloop.core.models import PhysicalTest

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/u.sqlite")
    db.create_all()
    assert U.sample_count(db) == 0

    with db.session() as s:
        s.add(PhysicalTest(product_slug="a", version="1.0.0", tester_ref="t1", passed=True))
        s.add(PhysicalTest(product_slug="b", version="1.0.0", tester_ref="t2", passed=False))
    # A failed test is not a timing sample: it says the pattern was wrong, not how long it took.
    assert U.sample_count(db) == 1


def test_the_plan_carries_its_interval_so_a_reader_cannot_see_only_the_point():
    plan = compile_launch("Christmas", CHRISTMAS, make_hours=90.0)
    rendered = plan.to_dict()
    assert rendered["make_time"]["low_hours"] < 90.0 < rendered["make_time"]["high_hours"]
    assert rendered["latest_optimistic_launch"]
    assert rendered["latest_pessimistic_launch"]
    assert rendered["make_time"]["calibrated"] is False


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
