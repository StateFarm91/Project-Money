"""Configurations competing, and the three ways a league stops meaning anything.

v1.4.3 requirements 95 and 96. A challenger that brings its own tasks wins every time; a
league that reports only quality takes every expensive trade and finds the bill at the end of
the month; and a registry that records the change without the reason answers the question
nobody asks.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import league as L  # noqa: E402

SHARED = ("summarise_pattern", "write_listing", "answer_support", "name_collection")


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/league.sqlite")
    db.create_all()
    return db


def _incumbent(quality=0.70, cost=0.002, reliability=0.99) -> L.Result:
    return L.Result(1, SHARED, quality, cost, reliability)


def _challenger(quality=0.80, cost=0.002, reliability=0.99, tasks=SHARED) -> L.Result:
    return L.Result(2, tasks, quality, cost, reliability)


# ---- the registry (#96) ---------------------------------------------------


def test_a_version_records_why_it_exists_not_only_that_it_does():
    db = _db()
    try:
        L.register(db, kind="prompt", key="listing.draft", payload="v2",
                   why_changed="improved", affected_departments=("listing",))
    except L.LeagueRefused as e:
        assert "should it still be" in str(e)
    else:
        raise AssertionError("a bare change was registered")

    try:
        L.register(db, kind="prompt", key="listing.draft", payload="v2",
                   why_changed="rewritten to lead with the finished size rather than the yarn",
                   affected_departments=())
    except L.LeagueRefused as e:
        assert "whichever one notices first" in str(e)
    else:
        raise AssertionError("a change with no affected departments was registered")


def test_an_identical_payload_does_not_create_a_new_version():
    """Otherwise the registry records redeploys as evolution."""
    db = _db()
    first = L.register(db, kind="prompt", key="listing.draft", payload="body",
                       why_changed="the first version of the listing draft prompt",
                       affected_departments=("listing",))
    again = L.register(db, kind="prompt", key="listing.draft", payload="body",
                       why_changed="a different reason, same text entirely",
                       affected_departments=("listing",))
    assert first["version"] == 1
    assert again["unchanged"] is True
    assert again["version"] == 1


def test_an_incumbent_that_was_never_measured_is_named_as_such():
    """It is running because it was first, which is the commonest reason anything runs."""
    db = _db()
    L.register(db, kind="prompt", key="listing.draft", payload="v1",
               why_changed="the first version of the listing draft prompt",
               affected_departments=("listing",), incumbent=True)
    report = L.standings(db)
    assert report["incumbents_with_no_measured_outcome"] == ["listing.draft"]
    assert "because they were first" in report["note"]


def test_promotion_records_the_run_that_justified_it():
    db = _db()
    first = L.register(db, kind="prompt", key="listing.draft", payload="v1",
                       why_changed="the first version of the listing draft prompt",
                       affected_departments=("listing",), incumbent=True)
    second = L.register(db, kind="prompt", key="listing.draft", payload="v2",
                        why_changed="leads with finished size rather than yarn weight",
                        affected_departments=("listing",))

    try:
        L.promote(db, second["id"], outcome={"quality": 0.8}, evidence_ref="")
    except L.LeagueRefused as e:
        assert "names the run" in str(e)
    else:
        raise AssertionError("a promotion was recorded with no evidence")

    L.promote(db, second["id"], outcome={"quality": 0.8}, evidence_ref="league:2026-09-19")
    report = L.standings(db)
    assert [i["version"] for i in report["incumbents"]] == [2]
    assert report["retired"][0]["version"] == 1
    assert first["id"] != second["id"]


# ---- the league (#95) -----------------------------------------------------


def test_a_challenger_that_brings_its_own_tasks_is_refused():
    """The failure that makes every other check decorative."""
    try:
        L.compare(_incumbent(), _challenger(tasks=SHARED + ("a_case_i_am_good_at",)),
                  shared_tasks=SHARED)
    except L.LeagueRefused as e:
        assert "wins every time" in str(e)
    else:
        raise AssertionError("a challenger was judged on its own tasks")


def test_a_challenger_that_skipped_the_hard_cases_has_not_beaten_anything():
    held = L.compare(_incumbent(), _challenger(tasks=SHARED[:2]), shared_tasks=SHARED)
    assert held["promote"] is False
    assert held["reason"] == "incomplete"
    assert "skipped the hard cases" in held["why"]


def test_a_small_gain_is_noise_and_promoting_on_it_makes_a_league_churn():
    marginal = L.compare(_incumbent(), _challenger(quality=0.72), shared_tasks=SHARED)
    assert marginal["promote"] is False
    assert "within the" in marginal["blockers"][0]

    real = L.compare(_incumbent(), _challenger(quality=0.80), shared_tasks=SHARED)
    assert real["promote"] is True


def test_the_cost_bar_scales_with_the_ratio_rather_than_sitting_at_one_threshold():
    """A flat bar treats 1.3x and 5x as the same trade, and they are not."""
    modest = L.compare(_incumbent(), _challenger(quality=0.75, cost=0.0024),
                       shared_tasks=SHARED)
    assert modest["cost_ratio"] == 1.2
    assert modest["promote"] is True

    expensive = L.compare(_incumbent(), _challenger(quality=0.78, cost=0.010),
                          shared_tasks=SHARED)
    assert expensive["cost_ratio"] == 5.0
    assert expensive["promote"] is False
    assert "would be needed at that ratio" in expensive["blockers"][0]

    # Quintupling the spend is allowed to buy a large improvement.
    worth_it = L.compare(_incumbent(), _challenger(quality=0.99, cost=0.010),
                         shared_tasks=SHARED)
    assert worth_it["promote"] is True


def test_a_configuration_that_wins_when_it_answers_and_fails_more_often_has_not_won():
    flaky = L.compare(_incumbent(), _challenger(quality=0.90, reliability=0.80),
                      shared_tasks=SHARED)
    assert flaky["promote"] is False
    assert any("reliability fell" in b for b in flaky["blockers"])


def test_a_promotion_passes_the_same_boundary_as_any_other_self_improvement():
    """Swapping a configuration is a change to how the company works."""
    try:
        L.compare(_incumbent(), _challenger(), shared_tasks=SHARED,
                  touches=("asset_truth",),
                  hypothesis="lower the thumbnail threshold so more assets pass")
    except L.LeagueRefused as e:
        assert "improvement boundary" in str(e)
    else:
        raise AssertionError("a gate-weakening promotion passed the league")

    allowed = L.compare(_incumbent(), _challenger(), shared_tasks=SHARED,
                        touches=("listing_copy",),
                        hypothesis="a shorter listing prompt should raise first-pass quality")
    assert allowed["promote"] is True


def test_all_three_axes_are_reported_because_a_league_showing_one_picks_the_trade():
    result = L.compare(_incumbent(), _challenger(), shared_tasks=SHARED)
    assert set(result["axes"]) == {"quality", "cost_cad", "reliability"}
    assert set(L.AXES) == {"quality", "cost_cad", "reliability"}


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
