"""The weekly deep cycle, and the review that is only allowed to add.

Requirement 194. `improve.velocity` already refuses the add-only review for cadences,
experiments, polish, queries and infrastructure, and the argument does not stop there: an
architecture review permitted to add specialists and never to merge or retire one grows the
org chart every week, forever, with each addition individually defensible -- which is exactly
what makes the total indefensible and invisible.

The sharpest rule here is the metric revision. A department that changes its own success
measure after a bad quarter has not improved; it has moved the goalposts, and from inside it
feels like better measurement, because the old metric genuinely was imperfect. Every metric is.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.improve import cells  # noqa: E402
from brambleloop.improve import weekly as W  # noqa: E402

AT = datetime(2026, 9, 20, 6, 0, tzinfo=timezone.utc)


def _full(read: int = 10, findings: int = 1):
    return [W.DomainReading(domain=d, read=read, findings=findings) for d in W.DOMAINS]


def _change(**kw) -> W.ArchitectureChange:
    args = dict(move=W.ADD, subject="ads_analyst", proposed_by="failure_miner",
                because="nothing currently owns paid-media attribution at all")
    args.update(kw)
    return W.ArchitectureChange(**args)


# ---- the eight domains, audited rather than visited ------------------------


def test_every_domain_the_requirement_names_is_present():
    for name in ("product_creativity", "pattern_correctness", "competitor_intelligence",
                 "conversion", "ads", "support", "infrastructure", "cost"):
        assert name in W.DOMAINS
    assert len(W.DOMAINS) == 8


def test_a_domain_with_nothing_read_is_not_audited():
    reading = W.DomainReading(domain="ads", read=0)
    assert reading.outcome == W.NOT_AUDITED


def test_findings_from_nothing_read_are_refused():
    try:
        W.DomainReading(domain="ads", read=0, findings=3)
    except W.WeeklyRefused as e:
        assert "from a row somebody looked at" in str(e)
    else:  # pragma: no cover
        raise AssertionError("findings appeared from nowhere")


def test_a_cycle_missing_a_domain_is_not_complete():
    out = W.cycle(_full()[:5], [], at=AT)
    assert out["complete"] is False
    assert len(out["not_audited"]) == 3
    assert "the same output as one that did" in out["why"]


def test_a_full_cycle_is_complete_even_with_no_findings():
    out = W.cycle(_full(findings=0), [], at=AT)
    assert out["complete"] is True
    assert out["total_findings"] == 0


def test_a_domain_audited_twice_is_refused():
    readings = _full() + [W.DomainReading(domain="ads", read=1)]
    try:
        W.cycle(readings, [], at=AT)
    except W.WeeklyRefused as e:
        assert "audited twice" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a domain was audited twice")


def test_an_invented_domain_is_refused():
    try:
        W.DomainReading(domain="vibes", read=1)
    except W.WeeklyRefused as e:
        assert "not a weekly domain" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the audit grew a domain")


# ---- the architecture review must be able to subtract ----------------------


def test_three_of_the_four_moves_are_not_additions():
    assert len(W.MOVES) == 4
    assert set(W.SUBTRACTIVE) == {W.MERGE, W.RETIRE}
    assert W.ADD not in W.SUBTRACTIVE


def test_a_week_that_only_added_is_asked_why():
    out = W.cycle(_full(), [_change()], at=AT)
    assert out["architecture"]["only_added"] is True
    assert "one individually defensible step at a time" in out["architecture"]["note"]


def test_a_week_that_only_added_may_answer_and_is_not_blocked():
    out = W.cycle(_full(), [_change()], at=AT,
                  nothing_to_subtract_because="every department earned its cost this quarter")
    assert out["complete"] is True
    assert "every department earned its cost" in out["architecture"]["note"]


def test_a_week_that_subtracted_is_not_asked_anything():
    changes = [_change(),
               _change(move=W.RETIRE, subject="portfolio",
                       because="its single number is already reported by the finance cell")]
    out = W.cycle(_full(), changes, at=AT)
    assert out["architecture"]["only_added"] is False
    assert out["architecture"]["note"] == ""
    assert out["architecture"]["subtracted"] == 1


def test_adding_a_specialist_for_something_a_department_already_owns_is_refused():
    try:
        _change(subject="pricing")
    except W.WeeklyRefused as e:
        assert "two roles end up doing one job" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a duplicate department was added")


def test_merging_or_retiring_something_that_is_not_a_department_is_refused():
    try:
        _change(move=W.MERGE, subject="the vibes team",
                because="it duplicates work another team already does")
    except W.WeeklyRefused as e:
        assert "is not a department" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a non-existent department was merged")


def test_an_architecture_change_needs_an_arguable_reason():
    try:
        _change(because="seems right")
    except W.WeeklyRefused as e:
        assert "somebody can argue with" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the org chart changed on a shrug")


# ---- the metric revision --------------------------------------------------


def _revision(**kw) -> W.ArchitectureChange:
    args = dict(move=W.REVISE_METRIC, subject="growth", proposed_by="failure_miner",
                replaces_metric=cells.BY_KEY["growth"].metric,
                new_metric="attributable_orders_per_loop",
                because=("counting loops says nothing about whether any of them produced an "
                         "order, which is the thing growth is for"))
    args.update(kw)
    return W.ArchitectureChange(**args)


def test_a_department_may_not_revise_its_own_success_measure():
    try:
        _revision(proposed_by="growth")
    except W.WeeklyRefused as e:
        assert "moved the goalposts" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a department regraded itself")


def test_a_revision_argued_from_the_number_being_unflattering_is_refused():
    for phrase in W.GOALPOST_PHRASES:
        try:
            _revision(because=f"the current metric {phrase} what this team actually does")
        except W.WeeklyRefused as e:
            assert "argument about the reading" in str(e), phrase
        else:  # pragma: no cover
            raise AssertionError(f"{phrase!r} passed as a reason to change the scoreboard")


def test_a_revision_must_name_the_metric_it_replaces():
    try:
        _revision(replaces_metric="something_else")
    except W.WeeklyRefused as e:
        assert "cannot be checked against it afterwards" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a revision replaced a metric nobody had")


def test_a_revision_to_the_same_metric_is_refused():
    try:
        _revision(new_metric=cells.BY_KEY["growth"].metric)
    except W.WeeklyRefused as e:
        assert "the new metric is the old one" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a no-op revision was accepted")


def test_a_valid_revision_preserves_the_old_metrics_history():
    out = _revision().to_dict()
    assert out["replaces_metric"] == cells.BY_KEY["growth"].metric
    assert "removes the only evidence that it was self-serving" in out["history"]


def test_a_revision_with_no_new_metric_is_refused():
    try:
        _revision(new_metric="")
    except W.WeeklyRefused as e:
        assert "names the new metric" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a revision replaced a metric with nothing")


# ---- who may propose ------------------------------------------------------


def test_a_judging_role_may_not_propose_an_architecture_change():
    """B-423 applies to the org chart too: the evaluator rules on changes, it does not
    author them, and a revision to a scoreboard is the last place to relax that."""
    out = W.check_proposer(_revision(proposed_by="evaluator"))
    assert out["ok"] is False
    assert "may not propose" in out["why"]


def test_a_proposing_role_may_revise_another_departments_metric():
    assert W.check_proposer(_revision())["ok"] is True


def test_the_cycle_enforces_the_proposer_check_rather_than_trusting_the_caller():
    """A rule enforced at one call site is enforced at the call sites somebody thought of."""
    try:
        W.cycle(_full(), [_revision(proposed_by="evaluator")], at=AT)
    except W.WeeklyRefused as e:
        assert "may not propose" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a change from a judging role went through the cycle")


def test_a_department_proposing_its_own_retirement_is_allowed():
    change = _change(move=W.RETIRE, subject="portfolio", proposed_by="portfolio",
                     because="its single number is already reported by the finance cell")
    out = W.check_proposer(change)
    assert out["ok"] is True
    assert "costs the proposer" in out["why"]


# ---- the roadmap ----------------------------------------------------------


def test_an_item_carried_four_weeks_is_a_decision_nobody_is_making():
    out = W.roadmap(W.cycle(_full(), [], at=AT),
                    carried=[{"item": "ads attribution", "weeks_carried": 9},
                             {"item": "thumbnail test", "weeks_carried": 1}])
    assert [i["item"] for i in out["stuck"]] == ["ads attribution"]
    assert out["carried"][0]["weeks_carried"] == 9
    assert "opposite responses" in out["why"]


def test_the_roadmap_carries_the_cycles_completeness_forward():
    partial = W.roadmap(W.cycle(_full()[:2], [], at=AT))
    full = W.roadmap(W.cycle(_full(), [], at=AT))
    assert partial["complete_cycle"] is False
    assert full["complete_cycle"] is True


def test_state_names_what_it_builds_on_and_what_it_refuses():
    out = W.state()
    assert out["requirement"] == 194
    assert "improve.velocity" in out["builds_on"]
    assert any("its own success measure" in r for r in out["refuses"])
    assert "grows the org chart forever" in out["note"]


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
