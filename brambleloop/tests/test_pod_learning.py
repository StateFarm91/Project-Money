"""Pods that get better, and the two ways of getting better that pull against each other.

Requirement 226's last sentence -- *the pod should become measurably more discerning and
creative over time* -- contains a trap. A pod that rejects everything is maximally discerning
and contributes nothing; a pod that accepts everything is maximally generative and worthless.
A single score can rise while either one collapses, and the one that collapses is whichever
the score happens to weight least. So there are two measures and nothing returns one without
the other.

The second trap is in how discernment gets measured. Rejection rate is available immediately
and rises whenever a pod is being careful, which is why it gets used. It measures caution.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.improve import freshness  # noqa: E402
from brambleloop.intel import pod_learning as L  # noqa: E402
from brambleloop.intel.panel import PARITY  # noqa: E402

POD = "stockings"


def _record(kind: str = L.NEW_MECHANISM, **kw) -> L.Record:
    args = dict(pod=POD, kind=kind, subject="folded hem cuff",
                evidence_ref="observation/mjs-2026-09-12")
    args.update(kw)
    return L.Record(**args)


def _judge(predicted: bool, outcome, n: int = 0) -> L.Judgement:
    return L.Judgement(pod=POD, subject=f"s{n}", predicted_worth_doing=predicted,
                       outcome_worked=outcome)


def _settled(correct: int, wrong: int):
    out = [_judge(True, True, i) for i in range(correct)]
    out += [_judge(True, False, 100 + i) for i in range(wrong)]
    return out


# ---- the six record kinds -------------------------------------------------


def test_every_record_kind_the_requirement_names_exists():
    for kind in ("category_mistake", "failed_response", "new_mechanism",
                 "successful_response", "current_benchmark", "challenger_strategy"):
        assert kind in L.RECORD_KINDS
    assert len(L.RECORD_KINDS) == 6


def test_the_kinds_split_into_what_went_wrong_and_what_worked():
    assert set(L.FROM_FAILURE) | set(L.FROM_SUCCESS) == set(L.RECORD_KINDS)
    assert not set(L.FROM_FAILURE) & set(L.FROM_SUCCESS)


def test_a_kind_outside_the_six_is_refused():
    try:
        _record(kind="interesting")
    except L.PodLearningRefused as e:
        assert "which way a pod is drifting" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the memory grew a category")


def test_a_record_with_no_evidence_is_something_somebody_remembers():
    try:
        _record(evidence_ref="  ")
    except L.PodLearningRefused as e:
        assert "repetition without an outcome is not learning" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a remembered thing was recorded as a learned one")


def test_an_invented_pod_is_refused():
    try:
        _record(pod="vibes")
    except L.PodLearningRefused as e:
        assert "is not a pod" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a pod nobody defined recorded a lesson")


# ---- discernment is precision, not rejection rate -------------------------


def test_a_small_sample_of_calls_demonstrates_nothing():
    out = L.discernment(_settled(3, 1))
    assert out["reading"] == L.UNMEASURED
    assert "confident nonsense" in out["why"]


def test_precision_is_scored_against_what_happened():
    out = L.discernment(_settled(10, 2))
    assert out["reading"] == "measured"
    assert out["precision"] == round(10 / 12, 3)


def test_rejection_rate_is_named_and_refused_as_the_measure():
    out = L.discernment(_settled(10, 2))
    assert "rejection_rate" not in out
    assert "It is not this" in out["not_a_rejection_rate"]


def test_a_pod_that_never_says_no_is_not_discerning():
    """All-yes calls that all worked still report how few noes there were."""
    out = L.discernment(_settled(12, 0))
    assert out["said_not_worth_doing"] == 0
    assert "a pod that never says no is not discerning" in out["why"]


def test_noes_that_would_have_worked_are_counted():
    calls = _settled(10, 0) + [_judge(False, True, 200), _judge(False, False, 201)]
    out = L.discernment(calls)
    assert out["said_not_worth_doing"] == 2
    assert out["of_those_would_have_worked"] == 1


def test_unsettled_calls_do_not_count_toward_precision():
    calls = _settled(10, 2) + [_judge(True, None, 300) for _ in range(20)]
    out = L.discernment(calls)
    assert out["settled"] == 12
    assert out["precision"] == round(10 / 12, 3)


# ---- creativity -----------------------------------------------------------


def _responses(original: int, parity: int):
    out = [{"subject": f"o{i}", "axes": ["product_engineering"]} for i in range(original)]
    out += [{"subject": f"p{i}", "axes": [PARITY]} for i in range(parity)]
    return out


def test_a_handful_of_responses_is_a_fact_about_a_handful():
    out = L.creativity(_responses(2, 1))
    assert out["reading"] == L.UNMEASURED
    assert "a fact about three answers" in out["why"]


def test_originality_is_the_share_offering_something_beyond_matching():
    out = L.creativity(_responses(4, 4))
    assert out["original_share"] == 0.5
    assert out["parity_only"] == 4


def test_a_pod_that_only_matches_scores_zero_creativity():
    out = L.creativity(_responses(0, 6))
    assert out["original_share"] == 0.0
    assert "not becoming more creative however much it learns" in out["why"]


# ---- the memory leans somewhere -------------------------------------------


def test_a_memory_of_only_failures_teaches_caution():
    out = L.balance([_record(kind=L.CATEGORY_MISTAKE) for _ in range(10)])
    assert out["reading"] == L.DRIFTING_CAUTIOUS
    assert "a cautious specialist stops finding things" in out["why"]


def test_a_memory_of_only_mechanisms_teaches_imitation():
    out = L.balance([_record(kind=L.NEW_MECHANISM) for _ in range(10)])
    assert out["reading"] == L.DRIFTING_IMITATIVE
    assert "through the learning system rather than through a decision" in out["why"]


def test_a_mixed_memory_is_balanced_and_has_no_target_ratio():
    records = [_record(kind=L.CATEGORY_MISTAKE) for _ in range(4)]
    records += [_record(kind=L.NEW_MECHANISM) for _ in range(6)]
    out = L.balance(records)
    assert out["reading"] == L.BALANCED
    assert "no correct ratio" in out["why"]


def test_an_empty_memory_is_empty_rather_than_drifting():
    out = L.balance([])
    assert out["reading"] == L.UNMEASURED
    assert "it is empty" in out["why"]


def test_the_balance_reports_the_kinds_it_actually_saw():
    out = L.balance([_record(kind=L.FAILED_RESPONSE), _record(kind=L.CURRENT_BENCHMARK)])
    assert set(out["by_kind"]) == {L.FAILED_RESPONSE, L.CURRENT_BENCHMARK}


# ---- never one number -----------------------------------------------------


def test_capability_returns_both_halves_always():
    out = L.capability(POD, judgements=_settled(10, 2), responses=_responses(3, 3),
                       records=[_record()])
    assert "discernment" in out and "creativity" in out
    assert "collapses" in out["never_one_number"]


def test_one_unmeasured_half_is_not_a_passing_half():
    out = L.capability(POD, judgements=_settled(10, 2), responses=_responses(1, 1),
                       records=[_record()])
    assert out["measured"] is False
    assert "an unmeasured half is not a passing half" in out["why"]


def test_there_is_no_single_pod_score_anywhere_in_the_module():
    import inspect

    source = inspect.getsource(L)
    assert "def pod_score" not in source
    assert "overall_score" not in source


def test_a_capability_report_for_an_invented_pod_is_refused():
    try:
        L.capability("vibes", judgements=[], responses=[], records=[])
    except L.PodLearningRefused as e:
        assert "is not a pod" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented pod got a capability report")


# ---- participation in the existing architecture ---------------------------


def test_the_pod_clock_is_taken_from_freshness_rather_than_restated():
    assert L.POD_WORLD == freshness.ADVERSARIAL
    assert L.POD_STALE_AFTER_HOURS == freshness.WORLD_SPEED[freshness.ADVERSARIAL][0]


def test_pods_are_deliberately_not_department_cells():
    from brambleloop.improve import cells

    overlap = set(L.state()["pods"]) & set(cells.BY_KEY)
    assert not overlap, f"a pod and a department share a key: {sorted(overlap)}"
    assert "would make 'department' mean two things" in L.state()["not_a_department"]


def test_every_pod_is_covered_by_the_report():
    from brambleloop.intel.pods import POD_KEYS

    assert set(L.state()["pods"]) == set(POD_KEYS)


def test_state_names_what_it_builds_on_rather_than_reimplementing_it():
    out = L.state()
    assert out["requirement"] == 226
    assert "intel.memory" in out["builds_on"]
    assert "never rejection rate" in out["note"]


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
