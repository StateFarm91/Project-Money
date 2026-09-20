"""#16: a listing test that can be read, and a memory that can also forget.

The test worth writing twice is the one about exposure. A listing nobody saw did not fail,
and the consequence of getting it wrong is not a wrong verdict -- it is a disproof written
into the memory, blocking an idea nobody ever tried.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import listing_tests as T  # noqa: E402
from brambleloop.growth.experiments import (  # noqa: E402
    HOLDOUT, NO_CONTROL, PRE_POST, Experiment)

CTX = T.Context("ornaments", "under_6", "Christmas", "new")


def _plan(observed=0.01, sample=400, design=HOLDOUT, key="t1"):
    plan = Experiment(key, "a clearer title lifts click-through on ornament listings", "ctr",
                      design, 0.05, 0.02, 200, date(2026, 11, 1))
    plan.observed, plan.sample = observed, sample
    return plan


def _test(**over):
    base = dict(key="t1", listing_ref="L1", plan=_plan(), variables=("title",), context=CTX,
                pre_period_days=21, pre_period_value=0.03, window_days=21, exposure=1200)
    base.update(over)
    return T.ListingTest(**base)


# --- a test that can be read ---------------------------------------------------------------

def test_a_listing_nobody_saw_did_not_fail():
    """The defect that matters here. To anything reading the outcome column, an unexposed
    test and a failed one are the same row."""
    unexposed = _test(exposure=None)
    out = T.read(unexposed)
    assert out["outcome"] == T.NOT_TESTED
    assert out["remember"] is False
    assert "writes nothing to memory" in out["why"]

    thin = T.read(_test(exposure=12))
    assert thin["outcome"] == T.NOT_TESTED
    assert any("did not fail, it was not tested" in p for p in thin["problems"])


def test_an_unreadable_test_cannot_write_a_disproof():
    """Because the disproof would block an idea nobody has actually tried."""
    memory: list[T.Memory] = []
    assert T.remember(memory, _test(exposure=None))["written"] is False
    assert memory == []
    assert T.may_test(memory, idea="title", context=CTX)["may_test"] is True


def test_a_missing_pre_period_is_refused_in_both_its_forms():
    no_days = T.check_design(_test(pre_period_days=2))
    assert any("pre-period of 2 day" in p for p in no_days["problems"])
    no_value = T.check_design(_test(pre_period_value=None))
    assert any("same gap wearing a sufficient number of days" in p
               for p in no_value["problems"])


def test_a_short_window_measures_the_weekday():
    out = T.check_design(_test(window_days=3))
    assert any("measures the weekday" in p for p in out["problems"])


def test_a_readable_test_reads():
    out = T.read(_test())
    assert out["outcome"] == T.DISPROVED
    assert out["remember"] is True
    assert out["attributable_to_one_variable"] is True


# --- one primary variable at a time --------------------------------------------------------

def test_a_multi_variable_test_belongs_to_the_bundle_and_blocks_nothing_later():
    """"Where practical" is an invitation to never do it, so a rebuild is allowed -- it
    simply cannot claim any one of the things it changed."""
    bundled = _test(variables=("title", "thumbnail", "price"))
    out = T.read(bundled)
    assert out["attributable_to_one_variable"] is False
    assert out["idea"] == "price+thumbnail+title"
    assert any("belongs to the bundle" in q for q in out["qualifications"])

    memory: list[T.Memory] = []
    T.remember(memory, bundled, on=date(2026, 9, 20))
    assert T.may_test(memory, idea="title", context=CTX)["may_test"] is True


def test_a_variable_outside_the_vocabulary_cannot_be_remembered():
    try:
        _test(variables=("we changed the listing",))
    except T.ListingTestRefused as exc:
        assert "cannot be remembered as a variable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unrememberable variable was accepted")


def test_a_test_that_changes_nothing_is_a_period_of_time():
    try:
        _test(variables=())
    except T.ListingTestRefused as exc:
        assert "period of time" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a test with no variable was accepted")


# --- confounders ----------------------------------------------------------------------------

def test_a_confounded_window_is_about_something_else():
    out = T.read(_test(confounders=("shop_sale", "seasonal_peak")))
    assert out["remember"] is False
    assert any("confounded by" in q for q in out["qualifications"])


def test_an_invented_confounder_is_refused():
    try:
        _test(confounders=("mercury_retrograde",))
    except T.ListingTestRefused as exc:
        assert "are not confounders" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented confounder was recorded")


def test_only_a_causal_design_may_close_a_question():
    """A disproof is the one verdict that stops future work, so it is the one held to the
    design standard. A pre/post cannot separate the change from the week it happened in."""
    weak = _test(plan=_plan(design=PRE_POST))
    out = T.read(weak)
    assert out["outcome"] == T.DISPROVED
    assert out["remember"] is False
    assert any("cannot separate this from the season" in q for q in out["qualifications"])

    none = T.read(_test(plan=_plan(design=NO_CONTROL)))
    assert none["remember"] is False


def test_a_supported_result_is_kept_even_when_it_is_only_associative():
    """It closes nothing, so it is not held to the standard a disproof is held to."""
    won = _test(plan=_plan(observed=0.09, design=PRE_POST))
    out = T.read(won)
    assert out["outcome"] == T.SUPPORTED
    assert out["remember"] is True


def test_an_inconclusive_result_closes_nothing_and_opens_nothing():
    memory: list[T.Memory] = []
    out = T.remember(memory, _test(plan=_plan(observed=0.035)))
    assert out["written"] is False
    assert "closes nothing" in out["why"]


# --- the memory ------------------------------------------------------------------------------

def test_the_memory_refuses_a_question_it_has_already_answered_here():
    memory: list[T.Memory] = []
    T.remember(memory, _test(), on=date(2026, 9, 20))
    out = T.may_test(memory, idea="title", context=CTX)
    assert out["may_test"] is False
    assert "spends the same month to learn the same thing" in out["why"]
    assert out["exposure"] == 1200


def test_a_disproof_applies_to_the_context_that_produced_it_and_nowhere_else():
    memory: list[T.Memory] = []
    T.remember(memory, _test(), on=date(2026, 9, 20))
    other = T.Context("blankets", "over_20", "Christmas", "new")
    out = T.may_test(memory, idea="title", context=other)
    assert out["may_test"] is True
    assert "is not disproved" in out["why"]


def test_a_memory_that_never_forgets_is_a_way_to_stop_learning():
    memory: list[T.Memory] = []
    T.remember(memory, _test(), on=date(2026, 9, 20))
    out = T.may_test(memory, idea="title", context=CTX, changed_since=("shop_maturity",))
    assert out["may_test"] is True
    assert out["reopened_by"] == ["shop_maturity"]


def test_reopening_needs_a_named_change_rather_than_a_feeling():
    memory: list[T.Memory] = []
    T.remember(memory, _test(), on=date(2026, 9, 20))
    try:
        T.may_test(memory, idea="title", context=CTX, changed_since=("things feel different",))
    except T.ListingTestRefused as exc:
        assert "reopens every question ever closed" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unnamed change reopened a closed question")


def test_an_empty_memory_says_it_is_empty_rather_than_reporting_nothing_known():
    out = T.known([])
    assert out["count"] == 0
    assert "none has been supported either" in out["note"]


def test_known_scopes_to_a_context_when_asked():
    memory: list[T.Memory] = []
    T.remember(memory, _test(), on=date(2026, 9, 20))
    T.remember(memory, _test(key="t2", listing_ref="L2", plan=_plan(key="t2"),
                             variables=("thumbnail",),
                             context=T.Context("blankets", "over_20", "none", "new")),
               on=date(2026, 9, 20))
    assert T.known(memory)["count"] == 2
    assert T.known(memory, context=CTX)["count"] == 1


def test_the_memory_outlives_the_process():
    """A memory held in a list is not a memory: "we tried that last year" is exactly what a
    restart loses, and losing it is how a disproved idea gets funded again."""
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        assert T.write(s, _test(), on=date(2026, 9, 20))["written"] is True
    with db.session() as s:
        memory = T.load(s)
    assert [m.idea for m in memory] == ["title"]
    assert T.may_test(memory, idea="title", context=CTX)["may_test"] is False


def test_recording_the_same_result_twice_is_a_re_run_rather_than_a_second_finding():
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        assert T.write(s, _test(), on=date(2026, 9, 20))["written"] is True
        second = T.write(s, _test(), on=date(2026, 9, 21))
    assert second["written"] is False
    assert "already recorded" in second["why"]
    with db.session() as s:
        assert len(T.load(s)) == 1


def test_an_unreadable_test_writes_no_durable_row_either():
    from brambleloop.core.db import Database

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        assert T.write(s, _test(exposure=None))["written"] is False
    with db.session() as s:
        assert T.load(s) == []


def test_a_context_keyed_on_a_near_miss_is_refused():
    """A memory keyed on "under_10" while the benchmarks say "6_to_10" matches nothing, so
    every closed question quietly reopens and the memory reads as empty rather than broken."""
    for bad in (("ornaments", "under_10", "Christmas", "new"),
                ("ornament", "under_6", "Christmas", "new"),
                ("ornaments", "under_6", "christmas", "new"),
                ("ornaments", "under_6", "Christmas", "mature")):
        try:
            T.Context(*bad)
        except T.ListingTestRefused as exc:
            assert "matches nothing" in str(exc), bad
        else:  # pragma: no cover
            raise AssertionError(f"{bad} was accepted as a context")


def test_state_names_the_floors_and_why_they_exist():
    out = T.state()
    assert out["floors"]["exposure"] == T.MIN_EXPOSURE
    assert "did not fail" in out["note"]


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
