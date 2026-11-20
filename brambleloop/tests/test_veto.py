"""The owner's veto, and the feedback that usually evaporates.

Requirement 228. A veto is easy: somebody says no and the thing does not ship. What is hard
is that the reason evaporates -- it arrives as a sentence in a conversation, is acted on
once, and six months later nobody can say whether the same objection was raised eleven times
or once. An evaluator that could have been trained on eleven instances of one objection was
trained on nothing instead, and the owner goes on making the same call by hand.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.intel import veto as V  # noqa: E402

T0 = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)


def _veto(reason: str = "generic", ref: str = "p1", **kw) -> V.Veto:
    args = dict(subject_ref=ref, scope=V.FLAGSHIP_CREATIVE, reason=reason)
    args.update(kw)
    return V.Veto(**args)


def _prediction(i: int, *, predicted: bool, actual: bool, ahead: bool = True) -> V.Prediction:
    ruled = T0 + timedelta(hours=i)
    return V.Prediction(subject_ref=f"p{i}", predicted_veto=predicted, owner_vetoed=actual,
                        predicted_at=ruled - timedelta(hours=1) if ahead
                        else ruled + timedelta(hours=1),
                        owner_ruled_at=ruled)


# ---- a reason that can be counted -----------------------------------------


def test_a_reason_outside_the_vocabulary_cannot_be_counted():
    try:
        _veto(reason="it just doesn't feel right")
    except V.VetoRefused as e:
        assert "eleven unique sentences are a mood" in str(e)
    else:  # pragma: no cover
        raise AssertionError("free-text feedback was recorded as a countable reason")


def test_the_veto_reaches_only_what_the_requirement_grants_it():
    assert set(V.VETO_SCOPE) == {V.IDENTITY, V.FLAGSHIP_CREATIVE}
    try:
        _veto(scope="everything")
    except V.VetoRefused as e:
        assert "an approval step on everything" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the veto reached outside its scope")


def test_a_recorded_veto_carries_what_the_reason_means():
    out = _veto().to_dict()
    assert out["reason"] == "generic"
    assert "any shop's" in out["means"]


# ---- repetition is a finding about the evaluator --------------------------


def test_one_veto_is_a_product_that_missed():
    out = V.memory([_veto()])
    assert out["findings"] == []
    assert out["unrepeated"] == ["generic"]


def test_two_is_still_not_a_finding():
    out = V.memory([_veto(ref="a"), _veto(ref="b")])
    assert out["findings"] == []


def test_the_third_repetition_is_a_finding_about_the_evaluator():
    out = V.memory([_veto(ref=f"p{i}") for i in range(3)])
    assert len(out["findings"]) == 1
    finding = out["findings"][0]
    assert finding["finding"] == "about the evaluator, not about the products"
    assert "whichever product happened to arrive third" in finding["why"]


def test_different_reasons_do_not_add_up_to_one_finding():
    vetoes = [_veto(reason="generic", ref="a"), _veto(reason="uncanny", ref="b"),
              _veto(reason="off_identity", ref="c")]
    assert V.memory(vetoes)["findings"] == []


def test_the_memory_is_the_thing_chat_feedback_never_produces():
    out = V.memory([_veto(ref=f"p{i}") for i in range(5)])
    assert out["by_reason"] == {"generic": 5}
    assert "evaporates" in out["why"]


def test_an_empty_memory_reports_nothing_rather_than_health():
    out = V.memory([])
    assert out["vetoes"] == 0 and out["findings"] == [] and out["by_reason"] == {}


# ---- the veto is not retired by claiming alignment ------------------------


def test_a_handful_of_predictions_settles_nothing():
    out = V.alignment([_prediction(i, predicted=True, actual=True) for i in range(5)])
    assert out["state"] == V.HELD
    assert "agreement about a handful" in out["why"]


def test_perfect_agreement_over_enough_predictions_retires_the_veto():
    out = V.alignment([_prediction(i, predicted=i % 2 == 0, actual=i % 2 == 0)
                       for i in range(V.MIN_PREDICTIONS)])
    assert out["state"] == V.RETIRED
    assert out["agreement"] == 1.0


def test_a_single_missed_veto_holds_it_however_good_the_rate():
    predictions = [_prediction(i, predicted=True, actual=True)
                   for i in range(V.MIN_PREDICTIONS)]
    predictions.append(_prediction(99, predicted=False, actual=True))
    out = V.alignment(predictions)
    assert out["state"] == V.HELD
    assert out["missed_vetoes"] == 1
    assert "that error is the asymmetric one" in out["why"].lower()


def test_over_vetoing_alone_does_not_hold_the_veto_while_agreement_clears_the_bar():
    """A false veto costs a regeneration; a missed one ships what the owner refused. Two
    over-vetoes in thirty-two still clears 90%, and the asymmetry is that the same count of
    *missed* vetoes would not."""
    over = [_prediction(i, predicted=True, actual=True) for i in range(V.MIN_PREDICTIONS)]
    over += [_prediction(90 + i, predicted=True, actual=False) for i in range(2)]
    out = V.alignment(over)
    assert out["state"] == V.RETIRED
    assert out["missed_vetoes"] == 0 and out["over_vetoes"] == 2
    assert out["agreement"] < 1.0

    missed = [_prediction(i, predicted=True, actual=True) for i in range(V.MIN_PREDICTIONS)]
    missed += [_prediction(90 + i, predicted=False, actual=True) for i in range(2)]
    held = V.alignment(missed)
    assert held["state"] == V.HELD, "the same count of the other error holds the veto"


def test_both_error_counts_are_reported_on_either_path():
    retired = V.alignment([_prediction(i, predicted=i % 2 == 0, actual=i % 2 == 0)
                           for i in range(V.MIN_PREDICTIONS)])
    held = V.alignment([_prediction(i, predicted=True, actual=True) for i in range(3)])
    assert retired["missed_vetoes"] == 0 and retired["over_vetoes"] == 0
    assert "missed_vetoes" not in held, "too few predictions to count anything yet"


def test_a_prediction_dated_after_the_ruling_has_demonstrated_nothing():
    try:
        _prediction(1, predicted=True, actual=True, ahead=False)
    except V.VetoRefused as e:
        assert "the easiest training data to hand" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an evaluator was graded on answers it had already seen")


def test_there_is_no_argument_that_retires_the_veto():
    import inspect

    signature = inspect.signature(V.alignment)
    assert list(signature.parameters) == ["predictions"]


def test_state_says_the_veto_is_held_and_why_there_is_nothing_to_retire_it_with():
    out = V.state()
    assert out["requirement"] == 228
    assert "no veto has been recorded" in out["today"]
    assert out["retirement"]["min_predictions"] == V.MIN_PREDICTIONS
    assert "no veto the evaluator would have missed" in out["retirement"]["and"]


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
