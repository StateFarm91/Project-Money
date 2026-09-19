"""Reserves, velocity, the stop list and the architecture rung.

v1.4.3 requirements 49, 52, 53, 55. Four requirements about an autonomous system's relationship
with its own numbers.

A system that runs continuously and measures its own throughput will optimise throughput,
because throughput is the thing it can move without anybody's permission. A system with cash in
the account will find a use for it, because the obvious use is more of whatever produced it. A
system that reviews itself weekly will add work, because removing work is nobody's job. And a
system reporting confidence in one number will report zero for a year while a great deal is
built, which teaches its owner to stop reading the number.

None of these is a bug. Each is what the system does when nothing stops it.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.finance import reinvestment as R  # noqa: E402
from brambleloop.improve import velocity as V  # noqa: E402
from brambleloop.scale import confidence as C  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/discipline.sqlite")
    db.create_all()
    return db


# ---- the reserves (#49) ---------------------------------------------------


def test_the_reserves_fill_before_anything_is_spare():
    """Tax was never yours, and it arrives in April against an account that bought ads."""
    db = _db()
    # The reserves are CA$120 of tax, one month of operating cost and six months of cash
    # held against a bad quarter. A first CA$400 month does not clear them.
    modest = R.envelope(db, gross_cad=400.0, confidence=0.5)
    assert modest.tax_reserve_cad == 120.0
    assert modest.envelope_cad == 0.0
    assert modest.reserves_short_by_cad > 0
    assert modest.recommended_cad == 0.0
    assert "Nothing is spare" in modest.to_dict()["note"]

    rich = R.envelope(db, gross_cad=5000.0, confidence=0.5)
    expected = (5000.0 - 1500.0 - R.OPERATING_FLOOR_CAD
                - R.OPERATING_FLOOR_CAD * R.CASH_RESERVE_MONTHS)
    assert rich.envelope_cad == expected
    assert rich.recommended_cad < rich.envelope_cad


def test_the_recommendation_is_scaled_by_confidence_rather_than_by_appetite():
    """Cash from an unrepeatable source is not evidence that spending will repeat it."""
    db = _db()
    # With no customers the ladder is zero, so an account full of cash recommends nothing.
    unearned = R.envelope(db, gross_cad=20_000.0)
    assert unearned.envelope_cad > 10_000
    assert unearned.confidence == 0.0
    assert unearned.recommended_cad == 0.0

    confident = R.envelope(db, gross_cad=20_000.0, confidence=0.8)
    assert confident.recommended_cad > 0
    assert confident.recommended_cad == round(confident.envelope_cad * 0.8, 2)


def test_a_recommendation_can_never_authorise_itself():
    """There is no branch of this function that returns owner_approval_required False."""
    db = _db()
    result = R.recommend(db, gross_cad=50_000.0,
                         purpose="bounded paid discovery on the top-contributing SKU",
                         confidence=1.0)
    assert result["owner_approval_required"] is True
    assert result["consequential"] is True
    assert "no code path that authorises a spend" in result["authority"]

    tiny = R.recommend(db, gross_cad=5000.0, purpose="one week of bounded search ads",
                       confidence=0.01)
    assert tiny["owner_approval_required"] is True


def test_growth_is_a_category_not_a_purpose():
    db = _db()
    try:
        R.recommend(db, gross_cad=5000.0, purpose="growth", confidence=0.5)
    except R.ReinvestmentRefused as e:
        assert "how an envelope becomes a standing budget" in str(e)
    else:
        raise AssertionError("an unpurposed reinvestment was recommended")


# ---- quality-adjusted velocity (#52) --------------------------------------


def test_a_faster_week_that_cost_quality_is_a_worse_week():
    """The week an agent optimising its own throughput would produce."""
    before = V.Week("2026-09-12", releases=2, defect_rate=0.05, support_burden=0.02,
                    conversion=0.02, contribution_cad=200.0)
    after = V.Week("2026-09-19", releases=6, defect_rate=0.20, support_burden=0.02,
                   conversion=0.02, contribution_cad=200.0)
    result = V.quality_adjusted(before, after)
    assert result["faster"] is True
    assert result["verdict"] == "degraded"
    assert "defect_rate" in result["degraded"]
    assert "optimising its own throughput" in result["reason"]


def test_a_metric_moving_off_zero_is_not_skipped_by_the_divide_guard():
    """A defect rate going from none to some is the most important movement here.

    The natural implementation guards the division and skips it, which drops exactly the
    case the comparison exists for.
    """
    before = V.Week("2026-09-12", 2, defect_rate=0.0, support_burden=0.0,
                    conversion=0.02, contribution_cad=200.0)
    after = V.Week("2026-09-19", 6, defect_rate=0.30, support_burden=0.0,
                   conversion=0.02, contribution_cad=200.0)
    result = V.quality_adjusted(before, after)
    assert "defect_rate" in result["degraded"]
    assert result["movements"]["defect_rate"]["from_zero"] is True
    assert result["verdict"] == "degraded"


def test_a_single_week_is_a_count_rather_than_a_velocity():
    only = V.quality_adjusted(None, V.Week("2026-09-19", 6, 0.0, 0.0, 0.0, 0.0))
    assert only["comparable"] is False
    assert only["verdict"] == "baseline"
    assert "one week is a count, not a velocity" in only["reason"]


def test_the_release_count_is_never_returned_without_its_companions():
    """Structural, because a number an agent can move without a customer is the one it moves."""
    db = _db()
    reported = V.from_db(db)
    assert set(V.COMPANIONS) == {"defect_rate", "support_burden", "conversion",
                                 "contribution_cad"}
    assert reported["comparison"]["companions"] == list(V.COMPANIONS)
    for week in reported["weeks"]:
        for companion in V.COMPANIONS:
            assert companion in week, companion
    # Conversion is a measured zero rather than an omission, because a companion quietly
    # dropped from the pairing is how the pairing stops working.
    assert "measured zero rather than omitted" in reported["note"]


# ---- the stop-doing queue (#53) -------------------------------------------


def test_a_review_that_stops_nothing_has_to_say_why():
    """'Nothing to stop' is precisely what a bureaucracy reports, every week, for years."""
    try:
        V.stop_list([])
    except V.VelocityRefused as e:
        assert "nothing here ever removes one" in str(e)
    else:
        raise AssertionError("a silent empty stop list was accepted")

    lean = V.stop_list([], nothing_to_stop_because=(
        "every cadence added this month is still inside its first evaluation window"))
    assert lean["count"] == 0
    assert "is what a bureaucracy reports" in lean["note"]


def test_stopping_something_needs_a_reason_somebody_can_argue_with_later():
    try:
        V.Stop("cadence", "mjs_scan", "no")
    except V.VelocityRefused as e:
        assert "as arbitrary as starting it was" in str(e)
    else:
        raise AssertionError("a reasonless stop was accepted")

    try:
        V.Stop("vibes", "something", "it has stopped being useful to anybody")
    except V.VelocityRefused as e:
        assert "not a stop category" in str(e)
    else:
        raise AssertionError("an invented stop category was accepted")


def test_the_five_categories_are_separate_because_they_fail_differently():
    stops = [
        V.Stop("experiment", "thumbnail-contrast-a-b",
               "has run six weeks with no reachable conclusion and blocks the slot"),
        V.Stop("query", "crochet gift ideas",
               "monitored for a quarter and has never changed a decision"),
    ]
    result = V.stop_list(stops)
    assert result["count"] == 2
    assert result["by_category"] == {"experiment": 1, "query": 1}
    assert set(result["categories_untouched"]) == {"cadence", "polish", "infrastructure"}


def test_the_weekly_review_cannot_have_only_one_half():
    """A review that produced only new work is the thing #53 names."""
    db = _db()
    reviewed = V.review(db, nothing_to_stop_because=(
        "the only two cadences added this month are still inside their evaluation window"))
    assert "velocity" in reviewed and "stop" in reviewed
    assert "autonomous bureaucracy" in reviewed["rule"]


# ---- the staged confidence ladder (#55) -----------------------------------


def test_the_architecture_stage_is_earned_and_moves_neither_band():
    """#55, and the property that makes it honest.

    A ladder whose every rung reads 0.00 shows no stages at all and teaches its owner to stop
    reading it. The architecture rung is the one this company can earn — and earning it does
    not move the modelled probability by a point, because the ladder takes a minimum over the
    critical layers and this one is not critical.
    """
    db = _db()
    rungs = {r.key: r for r in C.ladder(db)}
    assert "architecture" in rungs
    assert rungs["architecture"].critical is False
    assert rungs["architecture"].confidence > 0.0
    assert C.probability(db)["probability"] == 0.0

    stages = [r["layer"] for r in C.bands(db)["stages"]]
    assert stages[0] == "architecture"
    assert "product_quality" in stages and "demand" in stages


def test_a_smaller_target_is_not_a_nearer_one_when_nothing_has_been_sold():
    """A model that scaled with the size of the goal would show CA$3,000 as likely."""
    db = _db()
    result = C.bands(db)
    targets = {b["target_cad_per_month"]: b["probability"] for b in result["bands"]}
    assert set(targets) == set(C.TARGETS)
    assert targets[3000.0] == targets[5000.0] == 0.0
    assert result["identical"] is True
    assert "a smaller target is not a nearer one" in result["note"]
    assert "not convertible into confidence about revenue" in result["note"]


def test_the_target_chooses_the_question_rather_than_adjusting_the_answer():
    db = _db()
    for target in C.TARGETS:
        result = C.probability(db, target_cad=target)
        assert result["target_cad_per_month"] == target
        assert result["probability"] == 0.0
        assert result["weakest_critical_layer"]


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
