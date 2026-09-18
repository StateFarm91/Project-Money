"""Working backward from the customer's finished object.

Requirements 283, 284, 285, 297, 310, 311 — the owner flagged the first as non-negotiable.
The failure this whole module exists to prevent is subtle and expensive: a shop launches its
Christmas blanket on December 1st, nobody can finish a forty-hour blanket in three weeks, and
the listing's own conversion data reports that Christmas blankets do not sell.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.seasonal import leadtime as lt  # noqa: E402

CHRISTMAS = date(2026, 12, 25)


def test_a_long_make_gets_an_earlier_launch_than_a_quick_one_by_arithmetic():
    """#285, and the reason it is computed rather than assigned.

    Giving flagships "the earliest runway" as a policy invites someone to tune the policy. It
    is not a policy: the customer's make time is a term in the subtraction, so a sixty-hour
    cardigan lands months before a three-hour ornament without anybody deciding it should.
    """
    ornament = lt.compile_launch("Christmas", CHRISTMAS, make_hours=3.0)
    cardigan = lt.compile_launch("Christmas", CHRISTMAS, make_hours=60.0)
    flagship = lt.compile_launch("Christmas", CHRISTMAS, make_hours=120.0)

    assert ornament.lane == lt.QUICK
    assert cardigan.lane == lt.LONG
    assert flagship.lane == lt.FLAGSHIP

    assert flagship.latest_effective_launch < cardigan.latest_effective_launch
    assert cardigan.latest_effective_launch < ornament.latest_effective_launch

    order = lt.runway_order([ornament, flagship, cardigan])
    assert [p.lane for p in order] == [lt.FLAGSHIP, lt.LONG, lt.QUICK]


def test_every_term_of_the_backward_chain_is_actually_subtracted():
    """#284 spells the formula out, so the test checks the formula rather than a date.

    A plan that folded the buffers into one constant would pass any test that only compared
    two products. The one that catches it is arithmetic: change one term, and exactly that
    many days move.
    """
    base = lt.compile_launch("Christmas", CHRISTMAS, make_hours=20.0)
    expected = (CHRISTMAS
                - timedelta(days=base.completion_buffer_days)
                - timedelta(days=base.effective_make_days)
                - timedelta(days=base.planning_buffer_days)
                - timedelta(days=base.marketplace_ramp_days))
    assert base.latest_effective_launch == expected

    # The marketplace ramp is the buffer seasonal plans most often forget, so move it alone.
    slower = lt.compile_launch("Christmas", CHRISTMAS, make_hours=20.0,
                               assumptions=lt.DEFAULT.measured(marketplace_ramp_days=31))
    assert (base.latest_effective_launch - slower.latest_effective_launch).days == 10

    # Preferred sits earlier than latest by exactly the learning and iteration windows.
    gap = (base.latest_effective_launch - base.preferred_launch).days
    assert gap == lt.DEFAULT.creative_iteration_days + lt.DEFAULT.ad_learning_days
    assert base.work_must_start_by < base.preferred_launch


def test_a_beginner_pattern_is_scheduled_for_a_beginner():
    """The estimate has to be the one that leaves the customer with a finished object.

    Scheduling a beginner cardigan on an experienced maker's hours produces a listing that is
    truthful about hours and wrong about dates, which is the same customer outcome as lying.
    """
    experienced = lt.compile_launch("Christmas", CHRISTMAS, make_hours=40.0,
                                    skill="experienced")
    beginner = lt.compile_launch("Christmas", CHRISTMAS, make_hours=40.0, skill="beginner")

    assert beginner.effective_make_days > experienced.effective_make_days
    assert beginner.latest_effective_launch < experienced.latest_effective_launch

    try:
        lt.compile_launch("Christmas", CHRISTMAS, make_hours=10.0, skill="wizard")
    except ValueError as e:
        assert "unknown skill" in str(e)
    else:
        raise AssertionError("an unknown skill level was silently scheduled")


def test_an_assumption_cannot_graduate_to_measured_by_being_overwritten():
    """The distinction this module is built to preserve.

    A launch date derived from six guesses and one derived from six months of sales data are
    different objects, and a dashboard that renders them identically is how the second gets
    treated with the caution of the first — or the first with the confidence of the second.
    """
    plan = lt.compile_launch("Christmas", CHRISTMAS, make_hours=30.0)
    assert plan.assumptions.fully_measured is False
    assert set(plan.assumptions.evidence().values()) == {"assumed"}
    assert plan.to_dict()["fully_measured"] is False

    improved = lt.DEFAULT.measured(hours_per_week=5.2, marketplace_ramp_days=17)
    assert improved.source_of("hours_per_week") == "measured"
    assert improved.source_of("ad_learning_days") == "assumed"
    assert improved.fully_measured is False

    # And the original is untouched: a measurement is a new set of assumptions, not a patch
    # applied to the shared default.
    assert lt.DEFAULT.hours_per_week == 7.0
    assert lt.DEFAULT.source_of("hours_per_week") == "assumed"

    try:
        lt.DEFAULT.measured(vibes=True)
    except ValueError as e:
        assert "not assumptions" in str(e)
    else:
        raise AssertionError("an invented field was accepted as a measurement")


def test_a_product_that_missed_its_window_is_never_launched_on_its_seasonal_premise():
    """#297. Finished engineering is not a reason.

    The customer cannot make it in time, the listing says they can, and the conversion data
    that comes back teaches the shop the wrong lesson about the whole category.
    """
    cardigan = lt.compile_launch("Christmas", CHRISTMAS, make_hours=60.0)
    too_late = cardigan.latest_effective_launch + timedelta(days=1)

    assert cardigan.status(too_late) == lt.MISSED
    action, why = cardigan.recommendation(too_late)
    assert action in (lt.SIMPLIFY, lt.HOLD, lt.PIVOT_EVERGREEN)
    assert action != lt.LAUNCH
    assert "cannot finish" in why or "too late" in why or "window has closed" in why

    ornament = lt.compile_launch("Christmas", CHRISTMAS, make_hours=3.0)
    late_for_ornament = ornament.latest_effective_launch + timedelta(days=1)
    assert ornament.recommendation(late_for_ornament)[0] == lt.PIVOT_EVERGREEN


def test_the_sentinel_separates_at_risk_from_merely_late():
    """#311 wants escalation while escalation still changes something.

    'Past preferred' and 'at risk' are different situations: the first has runway to spend,
    the second is the last window in which reallocating agents alters the outcome. Collapsing
    them into one amber light means either crying wolf in September or noticing in December.
    """
    plan = lt.compile_launch("Christmas", CHRISTMAS, make_hours=30.0)

    assert plan.status(plan.preferred_launch - timedelta(days=1)) == lt.ON_TRACK
    assert plan.status(plan.preferred_launch + timedelta(days=1)) == lt.PAST_PREFERRED
    assert plan.status(plan.latest_effective_launch - timedelta(days=3)) == lt.AT_RISK
    assert plan.status(plan.latest_effective_launch + timedelta(days=1)) == lt.MISSED

    report = lt.sentinel([plan], plan.latest_effective_launch - timedelta(days=3))
    assert report["counts"][lt.AT_RISK] == 1
    assert report["plans"][0]["days_to_latest"] == 3
    assert report["plans"][0]["recommendation"] == lt.LAUNCH
    assert "assumed" in report["note"]


def test_the_lane_boundaries_are_continuous_and_a_negative_make_time_is_refused():
    """Every make time falls in exactly one lane, including the boundary values."""
    assert lt.classify(0.5) == lt.QUICK
    assert lt.classify(lt.LANE_MAX_HOURS[lt.QUICK]) == lt.QUICK
    assert lt.classify(lt.LANE_MAX_HOURS[lt.QUICK] + 0.1) == lt.SHORT
    assert lt.classify(lt.LANE_MAX_HOURS[lt.MEDIUM]) == lt.MEDIUM
    assert lt.classify(1000.0) == lt.FLAGSHIP

    try:
        lt.classify(-1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("a negative make time was classified")


def test_it_compiles_against_the_seasonal_calendar_that_already_exists():
    """Reuse rather than a second calendar, because two calendars drift."""
    from brambleloop.radar.market import SEASONAL_EVENTS

    christmas = [e for e in SEASONAL_EVENTS if e.name == "Christmas"][0]
    plan = lt.plan_for_seasonal_event(christmas, make_hours=christmas.typical_make_hours[1])

    assert plan.event == "Christmas"
    assert plan.event_date == christmas.event_date
    assert plan.lane in (lt.LONG, lt.FLAGSHIP)
    # The finding that made this requirement non-negotiable: a slow maker's Christmas blanket
    # had to be live before the autumn, not during it.
    assert plan.latest_effective_launch < date(2026, 10, 1)


def test_make_time_is_derived_from_the_twin_rather_than_typed_in():
    """#283 asks for an estimate per product, and this company does not accept typed figures.

    A finished size cannot be asserted here; it is computed from the twin and a claim that
    disagrees is blocked. Make time decides whether a customer has a finished object by
    Christmas, so it gets the same treatment: stitch count, colour changes and per-piece
    finishing, all read off the twin.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    compiled = compile_cir(cir)
    twins = [build_twin(cir, compiled, component=c.name) for c in cir.components]

    estimate = lt.estimate_make_hours(twins)
    assert estimate.stitches == sum(t.stitch_total for t in twins)
    assert estimate.hours > 0
    assert estimate.lane == lt.classify(estimate.hours)
    assert estimate.evidence == "assumed"
    assert "twin" in estimate.basis

    # Finishing is per piece and is the term optimistic estimates drop, so it must be visible.
    doubled = lt.estimate_make_hours(twins + twins)
    assert doubled.components == 2
    assert doubled.hours > 2 * (estimate.hours - lt.DEFAULT.finishing_hours_per_component)

    try:
        lt.estimate_make_hours([])
    except ValueError:
        pass
    else:
        raise AssertionError("a pattern with no components was given a make time")


def test_colour_changes_are_counted_in_the_order_a_person_crochets():
    """A grid comparison would count a stripe sequence as a change per cell.

    The maker swaps yarn when the next stitch is a different colour from the one they just
    worked, following the row. Anything else over-counts two-colour work, which is most of
    this catalogue, and inflates every seasonal deadline that depends on it.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    compiled = compile_cir(cir)
    twin = build_twin(cir, compiled, component=cir.components[0].name)

    changes = lt.colour_changes(twin)
    assert 0 <= changes < twin.stitch_total, (changes, twin.stitch_total)


def test_calibration_says_it_has_no_samples_rather_than_inventing_a_rate():
    """The honest outcome today, and the one a stub would get wrong.

    No completed physical test has reported hours, so there is nothing to calibrate from. A
    function that returned a plausible number here would put a `measured` label on a guess --
    which is precisely the distinction the rest of this module exists to keep.
    """
    import tempfile

    from brambleloop.core.db import Database

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/calib.sqlite")
    db.create_all()

    assumptions, report = lt.calibrate_from_samples(db)
    assert report["samples_usable"] == 0
    assert report["measured_rate"] is None
    assert assumptions.source_of("stitches_per_hour") == "assumed"
    assert "remains an assumption" in report["note"]


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
