"""#247: search clusters seeded from questions makers demonstrably asked.

The decision this file is mostly about is where the questions come from. A keyword list
produced by asking a model what crocheters search for is a list of things that sound like
searches, and it is indistinguishable from a good one until a year of writing has been spent
on it. The complaint themes counted from observed reviews are the one list of maker
questions this company has evidence for.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.growth import clusters as C  # noqa: E402
from brambleloop.intel.observe import COMPLAINT_THEMES, RECURRING_AT  # noqa: E402


# --- where the questions come from ---------------------------------------------------------

def test_every_question_is_behind_a_theme_the_observer_already_counts():
    assert set(C.QUESTIONS) == set(COMPLAINT_THEMES)


def test_a_question_nobody_has_been_seen_to_ask_cannot_be_added():
    try:
        C.Cluster("how_do_i_crochet_a_yacht", "blankets")
    except C.ClusterRefused as exc:
        assert "sounds like a search" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an imagined question became a cluster")


def test_the_recurrence_floor_is_the_observers_own():
    """The word "recurring" is doing the same work in both places."""
    assert C.RECURRING_AT is RECURRING_AT
    thin = C.check(C.Cluster("counts_wrong", "blankets", leads_to="x", observed=1))
    assert thin["ok"] is False
    assert "one customer's bad day" in thin["reasons"][0]


def test_a_theme_seen_often_enough_with_a_destination_is_buildable():
    out = C.check(C.Cluster("counts_wrong", "blankets", leads_to="winter-throw", observed=7))
    assert out["ok"] is True
    assert out["question"].startswith("why do my stitch counts")
    assert out["answers_with"] == "tool"


# --- a cluster with no destination is a blog -------------------------------------------------

def test_the_third_link_is_the_one_that_goes_missing():
    out = C.check(C.Cluster("counts_wrong", "blankets", observed=7))
    assert out["ok"] is False
    assert any("enjoyable to make" in r for r in out["reasons"])


def test_every_question_says_why_the_paid_thing_comes_next():
    for theme, spec in C.QUESTIONS.items():
        assert len(spec["why_paid_next"].split()) >= 8, theme
        assert spec["answers_with"], theme


def test_one_cluster_admits_it_sells_least():
    """Better than pretending every article sells something."""
    assert "least of all" in C.QUESTIONS["delivery_problem"]["why_paid_next"]


# --- two clusters answering the same question ------------------------------------------------

def test_two_clusters_on_one_question_compete_with_each_other():
    out = C.overlap([C.Cluster("counts_wrong", "blankets", leads_to="a", observed=5),
                     C.Cluster("counts_wrong", "blankets", leads_to="b", observed=5)])
    assert out["ok"] is False
    assert out["competing"][0]["theme"] == "counts_wrong"
    assert "the one that loses was still written" in out["why"]


def test_the_same_question_in_a_different_department_is_not_a_clash():
    out = C.overlap([C.Cluster("counts_wrong", "blankets", leads_to="a", observed=5),
                     C.Cluster("counts_wrong", "hats", leads_to="b", observed=5)])
    assert out["ok"] is True


# --- the plan ----------------------------------------------------------------------------------

def test_clusters_are_ranked_by_how_often_the_question_was_actually_asked():
    out = C.plan({"counts_wrong": 7, "sizing_wrong": 4}, pod="blankets",
                 destinations={"counts_wrong": "a", "sizing_wrong": "b"})
    assert out["ranked"] == ["counts_wrong", "sizing_wrong"]
    assert out["buildable"] == 2


def test_a_thin_theme_is_carried_in_the_plan_and_not_built():
    out = C.plan({"counts_wrong": 7, "support_slow": 1}, pod="blankets",
                 destinations={"counts_wrong": "a", "support_slow": "b"})
    assert out["ranked"] == ["counts_wrong"]
    assert out["of"] == 2 and out["buildable"] == 1


def test_nothing_recurring_is_a_finding_about_the_observation():
    out = C.plan({"counts_wrong": 1}, pod="blankets", destinations={"counts_wrong": "a"})
    assert out["buildable"] == 0
    assert "about the observation rather than about the department" in out["note"]


def test_a_theme_with_no_question_behind_it_is_refused_in_the_plan():
    try:
        C.plan({"vibes": 9}, pod="blankets")
    except C.ClusterRefused as exc:
        assert "not themes with questions behind them" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unseeded theme was planned")


# --- what cannot be measured ---------------------------------------------------------------------

def test_none_of_the_requirements_metrics_can_be_measured_yet():
    out = C.measurement()
    assert out["measurable"] is False
    assert set(out["metrics"]) == {"organic_qualified_visits", "assisted_conversion",
                                   "email_capture", "revenue_contribution"}
    assert "unbuilt funnel look like a failed one" in out["why"]


def test_state_says_where_the_questions_came_from():
    out = C.state()
    assert "COMPLAINT_THEMES" in out["seeded_from"]
    assert out["recurring_at"] == RECURRING_AT
    assert "a year of writing" in out["note"]


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
