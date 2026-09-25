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

    estimate = lt.estimate_make_hours(twins, makes=lt.makes_of(cir))
    assert estimate.stitches == sum(t.stitch_total for t in twins)
    assert estimate.hours > 0
    assert estimate.lane == lt.classify(estimate.hours)
    assert estimate.evidence == "assumed"
    assert "twin" in estimate.basis

    # Finishing is per piece and is the term optimistic estimates drop, so it must be visible.
    doubled = lt.estimate_make_hours(twins, makes={c.name: 2 for c in cir.components})
    assert doubled.pieces == 2 * estimate.pieces
    assert doubled.hours > 2 * (estimate.hours - lt.DEFAULT.finishing_hours_per_component)

    try:
        lt.estimate_make_hours([], makes={})
    except ValueError:
        pass
    else:
        raise AssertionError("a pattern with no components was given a make time")


def test_make_time_counts_every_piece_the_pattern_says_to_work():
    """A twin holds one coaster. The buyer receives four.

    `Component.make` is the CIR's statement of multiplicity and the estimator did not read it,
    so a set of four reported the make-time of one -- in the figure that decides whether a
    customer can finish before the event, and the figure a listing quotes to a buyer. The
    check is against an independently computed single-instance estimate rather than against the
    total's own arithmetic, because a total compared with itself divided by four would pass on
    any number at all.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    compiled = compile_cir(cir)
    twin = build_twin(cir, compiled, component=cir.components[0].name)
    one = lt.estimate_make_hours([twin], makes={twin.component: 1})

    cir.components[0].make = 4
    four = lt.estimate_for(cir, compiled)

    assert four.pieces == 4 and four.components == 1
    assert four.stitches == 4 * twin.stitch_total
    assert four.colour_changes == 4 * one.colour_changes
    # Tolerance is four times the 2dp rounding of the single-piece figure, and is still two
    # orders of magnitude tighter than the error it exists to catch.
    assert abs(four.hours - 4 * one.hours) < 0.05, (four.hours, one.hours)
    assert four.lane == lt.classify(four.hours)
    # The breakdown has to show the multiplicity, or a total is unauditable.
    assert four.per_component[0]["make"] == 4
    assert abs(four.per_component[0]["hours_each"] - one.hours) < 0.02, four.per_component


def test_the_estimator_refuses_to_assume_one_of_each():
    """Defaulting the count to one is the defect, so there is no default.

    Both refusals are the same rule from opposite sides: a component whose multiplicity nobody
    stated, and a multiplicity expressed by repeating the twin instead (which silently loses
    whichever count the caller meant, and would have made `pieces` disagree with the CIR).
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    compiled = compile_cir(cir)
    twin = build_twin(cir, compiled, component=cir.components[0].name)

    try:
        lt.estimate_make_hours([twin], makes={})
    except ValueError as e:
        assert "refusing to assume one of each" in str(e), e
    else:
        raise AssertionError("a component with no stated make count was given a make time")

    try:
        lt.estimate_make_hours([twin, twin], makes={twin.component: 1})
    except ValueError as e:
        assert "multiplicity belongs in `makes`" in str(e), e
    else:
        raise AssertionError("the same component was counted twice under one name")

    for bad in ({twin.component: 0}, {twin.component: 1.5}):
        try:
            lt.estimate_make_hours([twin], makes=bad)
        except ValueError as e:
            assert "whole numbers of at least one" in str(e), e
        else:
            raise AssertionError(f"accepted a make count of {bad}")


def test_calibration_divides_by_the_stitches_the_tester_actually_worked():
    """The worst version of the same bug: a wrong number wearing the `measured` label.

    `calibrate_from_samples` is the only route from assumed to measured. It divided the
    tester's reported hours into the stitches of *one* of each component, so a tester who
    crocheted a set of four and reported four and a half hours would have established a stitch
    rate four times too slow -- and every seasonal launch date in the company would then have
    been derived from it with a `measured` label on it.
    """
    import tempfile

    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.core.db import Database
    from brambleloop.core.models import PatternVersion, PhysicalTest, Product
    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    cir.components[0].make = 4
    compiled = compile_cir(cir)
    twin = build_twin(cir, compiled, component=cir.components[0].name)
    hours = 4.5

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/calib-make.sqlite")
    db.create_all()
    with db.session() as s:
        product = Product(slug=cir.slug, title=cir.title)
        s.add(product)
        s.flush()
        s.add(PatternVersion(product_id=product.id, version=cir.version,
                             cir_json=cir.to_dict(), certified=True))
        s.add(PhysicalTest(product_slug=cir.slug, version=cir.version, tester_ref="t-1",
                           passed=True, measured={"hours": hours}))
        s.commit()

    assumptions, report = lt.calibrate_from_samples(db)
    assert report["samples_usable"] == 1, report
    expected = round(4 * twin.stitch_total / hours, 1)
    assert report["measured_rate"] == expected, (report, expected)
    # And the value it would have reported before the fix, which must not come back.
    assert report["measured_rate"] != round(twin.stitch_total / hours, 1)
    assert assumptions.source_of("stitches_per_hour") == "measured"


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


def test_the_sentinel_runs_on_a_cadence_and_raises_only_what_can_still_be_acted_on():
    """The owner's instruction after this engine's first finding.

    "Use this lead-time engine continuously rather than rediscovering seasonal timing
    manually." Timing is not established once: a date that was comfortable in September is
    missed in October without anything changing except the date.

    What it raises matters as much as that it runs. An at-risk window is the last one where
    reallocating effort changes the outcome, so it becomes an incident. A missed window does
    not: #297 already decided what happens to those, and an incident per missed product per
    day trains everyone to ignore the channel.
    """
    import tempfile

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import (
        AuditLog, Incident, Job, JobStatus, PatternVersion, Product,
    )
    from brambleloop.products.builder import CATALOGUE, build
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import CADENCES, Worker

    assert any(c[2] == "seasonal.sentinel" for c in CADENCES), \
        "seasonal timing is not on a cadence, so somebody has to remember to look"

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/seasonal.sqlite")
    db.create_all()
    Registry(db).seed_defaults()

    with db.session() as s:
        for slug, design in list(CATALOGUE.items())[:3]:
            cir = build(design)
            product = Product(slug=slug, title=cir.title, status="certified")
            s.add(product)
            s.flush()
            s.add(PatternVersion(product_id=product.id, version="1.0.0",
                                 cir_json=cir.to_dict(), release_hash="0" * 64,
                                 certified=True, certificate={"granted": True}))

    # Pick a day that is deliberately inside one product's at-risk window, rather than
    # hoping the calendar produces one. An earlier version of this test asserted over an
    # empty incident list and passed while the handler raised in production on every run.
    from brambleloop.seasonal.leadtime import catalogue_plans

    preview = catalogue_plans(db)
    soonest = min(preview["plans"], key=lambda r: r["latest_effective_launch"])
    as_of = (date.fromisoformat(soonest["latest_effective_launch"])
             - timedelta(days=5)).isoformat()

    JobQueue(db).enqueue("orchestrator", "seasonal.sentinel", {"as_of": as_of},
                         idempotency_key="seasonal-test-1")
    worker = Worker(db, "seasonal-worker")
    for _ in range(50):
        if not worker.run_once():
            break

    with db.session() as s:
        assessed = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "seasonal.assessed")))
        # Scoped to the at-risk signature: the same cadence also checks the collection
        # calendar (#123) and raises its own incident, which is a different question.
        incidents = [i for i in s.scalars(select(Incident))
                     if i.signature.startswith("seasonal.at_risk:")]
        jobs_dead = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD)))

    assert not jobs_dead, [(j.job_type, (j.last_error or '')[:200]) for j in jobs_dead]
    assert assessed, "the sentinel ran and recorded nothing"
    detail = assessed[-1].detail
    assert detail["products_scheduled"] == 3
    assert set(detail["counts"]) == {"on_track", "past_preferred", "at_risk", "missed"}
    # Named rows, not just a count: a count is not something anybody can act on.
    for row in detail["at_risk"]:
        assert row["slug"] and row["event"] and "days_to_latest" in row
    # Calibration state travels with the assessment, so a date built from assumptions is
    # never read as one built from measurement.
    assert detail["calibration"]["samples_usable"] == 0

    # Non-vacuous: the chosen day guarantees an at-risk window, so exactly one P2 is raised
    # for the soonest, carrying the slug and the runway rather than a generic message.
    assert len(incidents) == 1, [i.signature for i in incidents]
    raised = incidents[0]
    assert raised.signature.startswith("seasonal.at_risk:")
    assert raised.severity == "P2"
    assert raised.product_slug and raised.product_slug in raised.summary
    assert "runway" in raised.summary
    assert raised.halts_publication is False, "a timing risk must not halt publication"
    assert raised.detail["days_to_latest"] <= 21


# ---- the rolling calendar -------------------------------------------------


def test_the_calendar_rolls_so_no_event_is_ever_discovered_late():
    """#286's actual objection is to strike teams.

    A shop with strike teams attends to Christmas in October and discovers in March that
    Easter's window shut in January. On a rolling calendar every event is always some number
    of days away, and the day after Christmas it is 364 rather than zero.
    """
    from datetime import date

    from brambleloop.seasonal import calendar as cal

    boxing_day = date(2026, 12, 26)
    rolled = cal.rolling(boxing_day)
    christmas = [e for e in rolled["events"] if e["event"] == "Christmas"][0]
    assert christmas["days_away"] > 300, "Christmas vanished the day after Christmas"
    assert christmas["phase"] == "research"

    # Horizons index into the events rather than duplicating them.
    horizons = {h["days"]: h["events"] for h in rolled["horizons"]}
    assert list(horizons) == list(cal.HORIZONS)
    for smaller, larger in zip(cal.HORIZONS, cal.HORIZONS[1:]):
        assert set(horizons[smaller]) <= set(horizons[larger])


def test_the_phase_decides_what_work_is_useful_today():
    """Research at launch time and creative at ninety days are both waste."""
    from brambleloop.seasonal import calendar as cal

    assert cal.phase_for(400) == "research"
    assert cal.phase_for(200) == "concept"
    assert cal.phase_for(150) == "engineering"
    assert cal.phase_for(100) == "test"
    assert cal.phase_for(75) == "assets"
    assert cal.phase_for(45) == "launch"
    assert cal.phase_for(20) == "optimise"
    assert cal.phase_for(3) == "late_quick_make"
    assert cal.phase_for(-1) == "closed"


def test_the_heaviest_launchable_lane_comes_from_the_lead_time_engine():
    """Asked rather than tabulated, so the two cannot disagree.

    And the honest answer for a near event is nothing at all, rather than a lane no customer
    could finish.
    """
    from brambleloop.seasonal import calendar as cal

    assert cal.heaviest_launchable_lane(300) == "FLAGSHIP"
    assert cal.heaviest_launchable_lane(5) is None

    far = cal.heaviest_launchable_lane(300)
    near = cal.heaviest_launchable_lane(100)
    assert cal.LANE_ORDER.index(far) >= cal.LANE_ORDER.index(near)


def test_a_flash_trend_cannot_buy_flagship_engineering():
    """#290. Multi-week work on something that expires first costs the window too."""
    from brambleloop.seasonal import calendar as cal

    for half_life, lane in (("flash", "FLAGSHIP"), ("flash", "MEDIUM"),
                            ("short_seasonal", "LONG")):
        try:
            cal.check_half_life(half_life, lane)
        except cal.CalendarRefused as e:
            assert "ceiling" in str(e)
        else:
            raise AssertionError(f"{half_life} bought {lane} engineering")

    cal.check_half_life("flash", "QUICK")
    cal.check_half_life("recurring_seasonal", "LONG")
    cal.check_half_life("evergreen", "FLAGSHIP")

    try:
        cal.check_half_life("probably-fine", "QUICK")
    except cal.CalendarRefused as e:
        assert "not a half-life" in str(e)
    else:
        raise AssertionError("an unclassified trend was allowed engineering effort")


def test_the_sentinel_checks_the_dated_milestones_as_well_as_the_launch_dates():
    """#123 on the same cadence as #283, because they answer different questions.

    The launch-date work asks whether a customer could still finish the object. This asks
    whether the work that had to happen by now happened — and that slips silently, because a
    phase that is late does not announce itself, it becomes the next phase.
    """
    import tempfile

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, Incident, Job, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import Worker

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/calendar.sqlite")
    db.create_all()
    Registry(db).seed_defaults()

    JobQueue(db).enqueue("orchestrator", "seasonal.sentinel", {"as_of": "2026-09-19"},
                         idempotency_key="seasonal-calendar-1")
    worker = Worker(db, "seasonal-calendar-worker")
    for _ in range(50):
        if not worker.run_once():
            break

    with db.session() as s:
        dead = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD)))
        checked = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "seasonal.calendar_checked")))
        incidents = [i for i in s.scalars(select(Incident))
                     if i.signature.startswith("seasonal.calendar_behind:")]

    assert not dead, [(j.job_type, (j.last_error or "")[:200]) for j in dead]
    assert checked, "the calendar check ran and recorded nothing"
    behind = checked[-1].detail["events_behind"]
    # Every seasonal event is behind, which is the honest state: this company has never run a
    # collection calendar, so nothing has ever been done by a date.
    assert "Christmas" in behind
    assert "Halloween" in behind

    # One incident for the worst-affected event, not one per missed milestone: eight rows
    # about one Christmas is the noise that trains everybody to close the channel.
    assert len(incidents) == 1
    assert "collection milestones are already past" in incidents[0].summary
    assert "becomes the next phase" in incidents[0].summary
    assert len(incidents[0].detail["behind"]) >= 2


def test_depth_is_measured_against_the_ecosystem_an_event_actually_spans():
    """#288. Six Christmas products say nothing about whether five are blankets."""
    from datetime import date

    from brambleloop.seasonal import calendar as cal

    matrix = cal.coverage_matrix(date(2026, 9, 19),
                                 covered={"Christmas": ("blankets", "home_decor")})
    christmas = [r for r in matrix["rows"] if r["event"] == "Christmas"][0]

    assert set(christmas["covered"]) == {"blankets", "home_decor"}
    assert "stockings" in christmas["gaps"] and "garments" in christmas["gaps"]
    assert 0 < christmas["depth"] < 1
    # Ranked by how thin the coverage is, so the emptiest event leads.
    assert matrix["rows"][0]["depth"] <= matrix["rows"][-1]["depth"]
    assert matrix["ecosystem_depth"] < 0.2, "the catalogue is not this broad"


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
