"""#30: where the week goes, and why the default is not more engineering.

The requirement names the failure it prevents -- endless technical polishing starving
distribution -- and this module's own first draft committed it: a build mix with
distribution at 15% against the floor of 20% it enforces everywhere else, with a docstring
claiming the floor was respected. The invariant test below is what caught it, and it is kept
because that is the only kind of proof that survives the next edit.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce.lanes import QaEvidence, qa_stable  # noqa: E402
from brambleloop.scale import allocation as A  # noqa: E402

STABLE = qa_stable(QaEvidence(regression_fixtures=9, regression_passed=True,
                              certified_releases=4, open_halting_incidents=0))
UNSTABLE = qa_stable(QaEvidence())


# --- the mixes obey their own rules -----------------------------------------------------------

def test_every_mix_this_module_ships_passes_its_own_check():
    """The invariant that caught the module contradicting itself."""
    for name, mix in (("mature", A.MATURE_MIX), ("build", A.BUILD_MIX)):
        out = A.check_mix(mix)
        assert out["ok"] is True, (name, out["reasons"])


def test_distribution_keeps_its_floor_during_the_build_too():
    """Which is the whole requirement: the starvation begins before there is an audience."""
    assert A.BUILD_MIX[A.DISTRIBUTION] >= A.FLOORS[A.DISTRIBUTION]


def test_the_mature_mix_is_the_requirements_own_numbers():
    assert A.MATURE_MIX == {A.PRODUCT_QA: 0.30, A.MARKET_INTELLIGENCE: 0.30,
                            A.DISTRIBUTION: 0.30, A.INFRASTRUCTURE: 0.10}


def test_a_mix_that_starves_distribution_is_refused_with_the_reason():
    out = A.check_mix({A.PRODUCT_QA: 0.60, A.MARKET_INTELLIGENCE: 0.20,
                       A.DISTRIBUTION: 0.10, A.INFRASTRUCTURE: 0.10})
    assert out["ok"] is False
    assert any("shown to nobody" in r for r in out["reasons"])


def test_the_platform_is_how_the_work_happens_and_is_not_the_work():
    out = A.check_mix({A.PRODUCT_QA: 0.20, A.MARKET_INTELLIGENCE: 0.20,
                       A.DISTRIBUTION: 0.20, A.INFRASTRUCTURE: 0.40})
    assert any("is not the work" in r for r in out["reasons"])


def test_shares_that_do_not_total_a_week_are_refused():
    out = A.check_mix({A.PRODUCT_QA: 0.30, A.MARKET_INTELLIGENCE: 0.30,
                       A.DISTRIBUTION: 0.30, A.INFRASTRUCTURE: 0.30})
    assert any("not an allocation of a week" in r for r in out["reasons"])


def test_an_invented_function_is_refused():
    try:
        A.check_mix({"vibes": 1.0})
    except A.AllocationRefused as exc:
        assert "are not functions" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented function was allocated a week")


# --- after core engineering stabilizes ---------------------------------------------------------

def test_the_mature_mix_does_not_apply_while_the_chain_is_still_moving():
    out = A.allocate(qa=UNSTABLE)
    assert out["phase"] == "build"
    assert out["mature_mix_applies"] is False
    assert out["mix"] == A.BUILD_MIX
    assert "cannot distribute safely" in out["note"]


def test_stability_is_evidence_rather_than_a_flag():
    try:
        A.allocate(qa={"ok": True})
    except A.AllocationRefused as exc:
        assert "condition about evidence" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a bare flag decided the allocation")


def test_the_same_definition_of_stable_as_the_production_queues():
    """Two definitions of 'stable' is one definition and one excuse."""
    from brambleloop.commerce import lanes

    # Identity, not equality: this module re-exports the function rather than holding a
    # second one that agrees today.
    assert A.qa_stable is lanes.qa_stable


# --- the tilt ------------------------------------------------------------------------------------

def test_an_unmeasured_bottleneck_is_not_a_bottleneck():
    """Guessing does not produce a random answer; it produces the term nearest the code."""
    out = A.allocate(qa=STABLE, constraint={"identifiable": False, "reason": "four of the "
                                            "funnel's terms have never been observed"})
    assert out["mix"] == A.MATURE_MIX
    assert out["tilted_toward"] is None
    assert "nearest the code" in out["note"]


def test_no_constraint_at_all_is_the_mature_mix_rather_than_more_engineering():
    out = A.allocate(qa=STABLE)
    assert out["mix"] == A.MATURE_MIX
    assert "not a bottleneck" in out["why"]


def test_a_traffic_constraint_moves_work_to_distribution():
    out = A.allocate(qa=STABLE, constraint={"identifiable": True, "constraint": "traffic"})
    assert out["tilted_toward"] == A.DISTRIBUTION
    assert out["mix"][A.DISTRIBUTION] == 0.40
    assert abs(sum(out["mix"].values()) - 1.0) < 1e-9


def test_a_conversion_constraint_moves_work_to_the_product():
    out = A.allocate(qa=STABLE, constraint={"identifiable": True, "constraint": "conversion"})
    assert out["tilted_toward"] == A.PRODUCT_QA
    assert "visibly backs it" in out["because"]


def test_no_tilt_crosses_a_floor():
    for term in A.TILT_FOR:
        out = A.allocate(qa=STABLE, constraint={"identifiable": True, "constraint": term})
        for function, floor in A.FLOORS.items():
            assert out["mix"][function] >= floor - 1e-9, (term, function)
        assert A.check_mix(out["mix"])["ok"] is True, term


def test_the_tilt_costs_whoever_can_spare_it_most():
    """Not whoever is listed first: a tilt that always takes from the same function
    eventually takes from the one that could least afford it."""
    out = A.allocate(qa=STABLE, constraint={"identifiable": True, "constraint": "traffic"})
    spare = {f: A.MATURE_MIX[f] - A.FLOORS[f] for f in A.FUNCTIONS if f != A.DISTRIBUTION}
    richest = max(spare, key=spare.get)
    assert out["mix"][richest] < A.MATURE_MIX[richest]


def test_a_constraint_this_module_cannot_move_is_refused_rather_than_absorbed():
    try:
        A.allocate(qa=STABLE, constraint={"identifiable": True, "constraint": "morale"})
    except A.AllocationRefused as exc:
        assert "whatever we were going to do anyway" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unmapped constraint produced an allocation")


def test_every_mapped_term_says_which_function_and_why():
    for term, (function, why) in A.TILT_FOR.items():
        assert function in A.FUNCTIONS, term
        assert len(why.split()) >= 6, term


def test_the_weekly_cadence_actually_runs():
    """A module nobody calls is exactly "whatever was easiest to pick up", which is the
    thing this requirement prevents. So the allocation is a cadence -- and a handler whose
    interesting half no test executes is an untested handler with a passing test beside it,
    which this build has shipped twice."""
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.release import handle_capacity_review
    from brambleloop.runtime.worker import JobContext

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.capacity", {}), db=db,
                     queue=queue, registry=Registry(db), phase=None)

    out = handle_capacity_review(ctx)
    assert out["phase"] == "build"            # nothing is certified yet, and it says so
    assert out["two_queues_open"] is False
    assert out["tilted_toward"] is None       # the funnel's terms are unmeasured
    assert A.check_mix(out["mix"])["ok"] is True


def test_state_reports_the_mix_and_the_floors():
    out = A.state()
    assert out["mature_mix"] == A.MATURE_MIX
    assert out["floors"][A.DISTRIBUTION] == A.FLOORS[A.DISTRIBUTION]
    assert "always available" in out["note"]


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
