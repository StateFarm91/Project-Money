"""What #180 adds to a league that was already refusing the obvious cheat.

Requirement 180. `improve.league` was built for #95/#96 and already refuses a challenger that
brings its own tasks, weighs cost as an outcome, and records why every version exists. Four
things it was quietly missing, each tested here:

The shared set is overfitted by the league rather than by any one author. Refusing
self-introduced tasks stops one person gaming one comparison; it does nothing about a hundred
challengers judged, over a year, against the same forty tasks. A holdout is the only thing
that shows it, and winning the tuned set while losing the untuned one is the signature.

Latency is the fourth axis and the one that looks free, because it is nobody's line item
until a cadence starts missing its window and the miss gets blamed on load.

A fixed margin is not a significance test. 0.03 on four tasks is a coin, and a league
promoting on coins churns while every report counting promotions calls it progress.

Rollback is a recorded target. The moment it is needed is the moment nobody can reconstruct
what was running last Tuesday.
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

BIG = tuple(f"task_{i:02d}" for i in range(20))
SMALL = ("a", "b", "c", "d")
HOLDOUT = ("held_01", "held_02", "held_03", "held_04", "held_05")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/league.sqlite")
    db.create_all()
    return db


def _pair(*, tasks=BIG, inc_q=0.70, ch_q=0.80, inc_lat=None, ch_lat=None,
          inc_hold=None, ch_hold=None, holdout=()):
    inc = L.Result(1, tasks, inc_q, 0.002, 0.99, latency_s=inc_lat,
                   holdout_tasks=holdout, holdout_quality=inc_hold)
    ch = L.Result(2, tasks, ch_q, 0.002, 0.99, latency_s=ch_lat,
                  holdout_tasks=holdout, holdout_quality=ch_hold)
    return inc, ch


# ---- a margin is not a significance test ----------------------------------


def test_the_bar_gets_harder_as_the_task_set_gets_smaller():
    assert L.required_margin(4) > L.required_margin(8) > L.required_margin(L.SIGNIFICANT_TASKS)
    assert L.required_margin(L.SIGNIFICANT_TASKS) == L.QUALITY_MARGIN
    assert L.required_margin(200) == L.QUALITY_MARGIN


def test_an_empty_task_set_can_never_clear_the_bar():
    assert L.required_margin(0) == float("inf")


def test_the_same_gain_promotes_on_a_large_set_and_is_held_on_a_small_one():
    """0.05 across twenty tasks is a result; 0.05 across four is which four."""
    big = L.compare(*_pair(tasks=BIG, ch_q=0.75), shared_tasks=BIG)
    small = L.compare(*_pair(tasks=SMALL, ch_q=0.75), shared_tasks=SMALL)
    assert big["promote"] is True
    assert small["promote"] is False
    assert "for 4 tasks" in small["blockers"][0]


def test_the_comparison_reports_the_bar_it_used_and_what_it_measured_on():
    out = L.compare(*_pair(tasks=SMALL), shared_tasks=SMALL)
    assert out["tasks_compared"] == 4
    assert out["required_margin"] == round(L.required_margin(4), 4)


# ---- latency, the axis that looks free ------------------------------------


def test_a_win_that_is_four_times_slower_is_a_trade_not_a_win():
    out = L.compare(*_pair(ch_q=0.78, inc_lat=1.0, ch_lat=4.0), shared_tasks=BIG)
    assert out["promote"] is False
    assert out["latency_ratio"] == 4.0
    assert "misses its window" in out["blockers"][0]


def test_a_large_enough_improvement_may_buy_the_time():
    out = L.compare(*_pair(ch_q=0.99, inc_lat=1.0, ch_lat=4.0), shared_tasks=BIG)
    assert out["promote"] is True


def test_a_modest_slowdown_inside_the_tolerance_passes():
    out = L.compare(*_pair(ch_q=0.80, inc_lat=1.0, ch_lat=1.2), shared_tasks=BIG)
    assert out["promote"] is True
    assert out["latency_ratio"] == 1.2


def test_latency_that_was_not_measured_is_named_rather_than_read_as_instant():
    out = L.compare(*_pair(), shared_tasks=BIG)
    assert out["latency_ratio"] is None
    assert out["unmeasured_axes"] == ["latency_s"]
    assert out["promote"] is True, "an unmeasured axis is not a blocker, only a gap"


def test_latency_is_one_of_the_axes_the_league_declares():
    assert "latency_s" in L.AXES
    assert L.AXES["latency_s"][0] is False, "lower is better"


# ---- the holdout ----------------------------------------------------------


def test_winning_the_tuned_set_and_losing_the_holdout_is_refused():
    """The signature of a league that has fitted its own task set."""
    out = L.compare(*_pair(ch_q=0.85, inc_hold=0.70, ch_hold=0.60, holdout=HOLDOUT),
                    shared_tasks=BIG)
    assert out["promote"] is False
    assert out["holdout"] == "lost"
    assert "what fitting the task set looks like from outside" in out["blockers"][0]


def test_a_challenger_that_holds_up_on_the_holdout_is_promoted():
    out = L.compare(*_pair(ch_q=0.85, inc_hold=0.70, ch_hold=0.74, holdout=HOLDOUT),
                    shared_tasks=BIG)
    assert out["promote"] is True and out["holdout"] == "held"
    assert out["evidence"] == "tuned_set_and_holdout"


def test_a_small_dip_on_the_holdout_is_noise_rather_than_overfitting():
    out = L.compare(*_pair(ch_q=0.85, inc_hold=0.70, ch_hold=0.69, holdout=HOLDOUT),
                    shared_tasks=BIG)
    assert out["holdout"] == "held"
    assert out["promote"] is True


def test_a_holdout_that_overlaps_the_shared_set_is_refused():
    """A leaked holdout is the same evidence twice, reported as two."""
    leaky = BIG[:2] + HOLDOUT
    try:
        L.compare(*_pair(inc_hold=0.7, ch_hold=0.8, holdout=leaky), shared_tasks=BIG)
    except L.LeagueRefused as e:
        assert "worse than none" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a holdout that had been tuned against was accepted")


def test_a_comparison_with_no_holdout_says_the_evidence_is_the_tuned_set_only():
    out = L.compare(*_pair(), shared_tasks=BIG)
    assert out["holdout"] == "not_run"
    assert out["evidence"] == "tuned_set_only"
    assert out["promote"] is True, "no holdout is a weaker claim, not a refusal"


# ---- rollback -------------------------------------------------------------


def _two_versions(db):
    first = L.register(db, kind="prompt", key="listing_copy", payload="v1",
                       why_changed="the first listing prompt, written against the spec",
                       affected_departments=("listing",))
    second = L.register(db, kind="prompt", key="listing_copy", payload="v2",
                        why_changed="lead with the finished size rather than the yarn",
                        affected_departments=("listing",))
    return first, second


def test_rollback_restores_the_named_version_and_retires_the_current_one():
    db = _db()
    first, second = _two_versions(db)
    L.promote(db, first["id"], outcome={"quality": 0.7}, evidence_ref="run-1")
    L.promote(db, second["id"], outcome={"quality": 0.8}, evidence_ref="run-2")
    out = L.rollback(db, kind="prompt", key="listing_copy",
                     to_config_id=first["id"], why="live quality fell after promotion")
    assert out["rolled_back"] is True
    assert out["config_id"] == first["id"]
    assert out["from_config_id"] == second["id"]
    assert L.rollback_target(db, kind="prompt", key="listing_copy")["incumbent"][
        "config_id"] == first["id"]


def test_a_rollback_with_no_reason_is_refused():
    db = _db()
    first, second = _two_versions(db)
    L.promote(db, second["id"], outcome={}, evidence_ref="run-2")
    try:
        L.rollback(db, kind="prompt", key="listing_copy",
                   to_config_id=first["id"], why="  ")
    except L.LeagueRefused as e:
        assert "only question anybody asks of this row" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unexplained rollback was accepted")


def test_a_rollback_may_not_change_which_configuration_is_running():
    db = _db()
    first, _ = _two_versions(db)
    other = L.register(db, kind="prompt", key="support_reply", payload="x",
                       why_changed="a different configuration entirely, for support replies",
                       affected_departments=("support",))
    L.promote(db, first["id"], outcome={}, evidence_ref="run-1")
    try:
        L.rollback(db, kind="prompt", key="listing_copy",
                   to_config_id=other["id"], why="oops")
    except L.LeagueRefused as e:
        assert "is not a rollback" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a rollback swapped the configuration")


def test_rolling_back_to_the_current_incumbent_is_a_no_op_not_an_error():
    db = _db()
    first, _ = _two_versions(db)
    L.promote(db, first["id"], outcome={}, evidence_ref="run-1")
    out = L.rollback(db, kind="prompt", key="listing_copy",
                     to_config_id=first["id"], why="belt and braces")
    assert out["rolled_back"] is False and "already the incumbent" in out["why"]


def test_the_rollback_target_is_answered_before_it_is_needed():
    db = _db()
    first, second = _two_versions(db)
    L.promote(db, first["id"], outcome={}, evidence_ref="run-1")
    before = L.rollback_target(db, kind="prompt", key="listing_copy")
    L.promote(db, second["id"], outcome={}, evidence_ref="run-2")
    after = L.rollback_target(db, kind="prompt", key="listing_copy")
    assert before["available"] is False
    assert "no rollback" in before["why"]
    assert after["available"] is True
    assert after["rollback_to"]["config_id"] == first["id"]


def test_the_rollback_reason_survives_in_the_registry():
    db = _db()
    first, second = _two_versions(db)
    L.promote(db, first["id"], outcome={"quality": 0.7}, evidence_ref="run-1")
    L.promote(db, second["id"], outcome={"quality": 0.8}, evidence_ref="run-2")
    L.rollback(db, kind="prompt", key="listing_copy", to_config_id=first["id"],
               why="support volume doubled")
    rows = L.standings(db, kind="prompt", key="listing_copy")
    text = str(rows)
    assert "support volume doubled" in text


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
