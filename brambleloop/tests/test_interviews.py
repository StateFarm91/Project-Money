"""Asking the first hundred buyers, and the three ways the answer is decided in advance.

Requirement 260. A voluntary sample answers "what do the people who answer surveys think",
and the ways it stops answering anything else are all comfortable: invite the customers who
liked you, pay for the answer you wanted, or ask so late that the person constructs a memory
rather than reporting one.

The last test here is the one that matters most: nothing this module produces is ever a
finding, and the only route out of `hypothesis` runs through an instrument that did not ask
anybody a question.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.growth import interviews as I  # noqa: E402
from brambleloop.growth import owned  # noqa: E402

BOUGHT = date(2026, 9, 1)
ASKED = date(2026, 9, 3)


def _inv(ref: str, **kw) -> I.Invitation:
    args = dict(respondent_ref=ref, invited_on=ASKED, purchased_on=BOUGHT,
                selected_by="all_in_window", order_ref=f"order-{ref}")
    args.update(kw)
    return I.Invitation(**args)


def _round(n: int = 5, responses=()) -> I.Round:
    return I.Round(label="round-1", invitations=tuple(_inv(f"r{i}") for i in range(n)),
                   responses=tuple(responses))


# ---- choosing who to ask --------------------------------------------------


def test_every_outcome_correlated_selection_rule_is_refused_by_name():
    """Each of these can be described as 'asking our best customers', which is the problem."""
    for rule in I.NEVER_A_SELECTION_RULE:
        try:
            _inv("r1", selected_by=rule)
        except I.InterviewRefused as e:
            assert "outcome" in str(e), rule
        else:  # pragma: no cover
            raise AssertionError(f"{rule} was accepted as a sampling frame")


def test_an_unnamed_selection_rule_is_refused():
    try:
        _inv("r1", selected_by="the ones we thought would reply")
    except I.InterviewRefused as e:
        assert "blind to the answer" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an undescribed frame was accepted")


def test_the_permitted_rules_cannot_see_the_outcome():
    for rule in I.SELECTION_RULES:
        assert rule not in I.NEVER_A_SELECTION_RULE
        _inv("r1", selected_by=rule)


def test_a_round_drawn_by_two_rules_has_no_describable_frame():
    invitations = (_inv("a", selected_by="all_in_window"),
                   _inv("b", selected_by="every_nth_order"))
    try:
        I.Round(label="mixed", invitations=invitations)
    except I.InterviewRefused as e:
        assert "sampling frame" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a round with two frames was accepted")


# ---- paying for the answer ------------------------------------------------


def test_every_contingent_incentive_is_refused():
    for bad in I.NEVER_AN_INCENTIVE:
        try:
            _inv("r1", incentive=bad)
        except I.InterviewRefused as e:
            assert "contingent" in str(e), bad
        else:  # pragma: no cover
            raise AssertionError(f"{bad} was accepted as an incentive")


def test_contingency_does_not_require_intent_only_ordering():
    """An incentive chosen after reading the response is contingent however kindly meant."""
    assert "decided_after_reading" in I.NEVER_AN_INCENTIVE
    assert "ordering" in I.NEVER_AN_INCENTIVE["decided_after_reading"]


def test_a_response_cannot_carry_an_incentive_at_all():
    assert "incentive" not in I.Response.__dataclass_fields__
    assert "incentive" in I.Invitation.__dataclass_fields__


def test_a_round_offering_different_incentives_is_refused():
    invitations = (_inv("a", incentive="fixed_credit"), _inv("b", incentive=I.NO_INCENTIVE))
    try:
        I.Round(label="mixed", invitations=invitations)
    except I.InterviewRefused as e:
        assert "contingent on what was said" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a round with varying incentives was accepted")


# ---- legitimacy -----------------------------------------------------------


def test_a_respondent_with_no_order_and_no_tester_record_is_refused():
    try:
        I.Invitation(respondent_ref="r1", invited_on=ASKED, purchased_on=BOUGHT,
                     selected_by="all_in_window")
    except I.InterviewRefused as e:
        assert "fabricated response" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unanchored respondent was accepted")


def test_a_response_from_somebody_nobody_invited_is_refused():
    stray = I.Response(respondent_ref="ghost", responded_on=ASKED)
    try:
        I.Round(label="r", invitations=(_inv("r0"),), responses=(stray,))
    except I.InterviewRefused as e:
        assert "invented one" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unanchored response was accepted")


def test_one_person_answers_once():
    twice = (I.Response(respondent_ref="r0", responded_on=ASKED),
             I.Response(respondent_ref="r0", responded_on=ASKED))
    try:
        I.Round(label="r", invitations=(_inv("r0"),), responses=twice)
    except I.InterviewRefused as e:
        assert "one person, one weight" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a doubled respondent was accepted")


def test_the_sample_stays_small_on_purpose():
    many = tuple(_inv(f"r{i}") for i in range(I.MAX_SAMPLE + 1))
    try:
        I.Round(label="big", invitations=many)
    except I.InterviewRefused as e:
        assert "confidently unrepresentative" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an oversized voluntary sample was accepted")


# ---- CASL -----------------------------------------------------------------


def test_an_invitation_rides_the_purchase_relationship_and_its_clock():
    consent = owned.Consent(address_ref="ref-1", basis=owned.IMPLIED_PURCHASE,
                            obtained_on=BOUGHT, source="etsy order")
    fresh = I.invite_gate(_inv("r0"), consent, today=ASKED)
    stale = I.invite_gate(_inv("r0"), consent, today=BOUGHT + timedelta(days=800))
    assert fresh["may_invite"] is True
    assert stale["may_invite"] is False and "CASL" in stale["why"]


def test_a_published_business_address_is_not_a_basis_for_surveying_a_buyer():
    consent = owned.Consent(address_ref="ref-2", basis=owned.IMPLIED_PUBLISHED,
                            obtained_on=BOUGHT, source="their shop page")
    out = I.invite_gate(_inv("r0"), consent, today=ASKED)
    assert out["may_invite"] is False
    assert "private buyer" in out["why"]


def test_withdrawn_consent_stops_the_invitation():
    consent = owned.Consent(address_ref="ref-3", basis=owned.EXPRESS, obtained_on=BOUGHT,
                            source="signup", withdrawn_on=BOUGHT + timedelta(days=1))
    assert I.invite_gate(_inv("r0"), consent, today=ASKED)["may_invite"] is False


# ---- asking too late ------------------------------------------------------


def test_the_near_stop_answer_decays_and_says_so():
    prompt = I.Response(respondent_ref="r0", responded_on=BOUGHT + timedelta(days=3),
                        answers={I.WHAT_NEARLY_STOPPED: "the price"})
    late = I.Response(respondent_ref="r1", responded_on=BOUGHT + timedelta(days=60),
                      answers={I.WHAT_NEARLY_STOPPED: "the price"})
    out = I.answers(I.Round(label="r", invitations=(_inv("r0"), _inv("r1")),
                            responses=(prompt, late)))
    recalls = {a["respondent_ref"]: a["recall"] for a in out[I.WHAT_NEARLY_STOPPED]}
    assert recalls == {"r0": "recalled", "r1": "reconstructed"}


def test_only_the_feeling_question_has_a_clock():
    """A decision is retrieved; a hesitation is rebuilt. Only one of those needs a window."""
    assert set(I.RECALL_WINDOW_DAYS) == {I.WHAT_NEARLY_STOPPED}
    late = I.Response(respondent_ref="r0", responded_on=BOUGHT + timedelta(days=60),
                      answers={I.WHY_BOUGHT: "the chart"})
    out = I.answers(I.Round(label="r", invitations=(_inv("r0"),), responses=(late,)))
    assert out[I.WHY_BOUGHT][0]["recall"] == "recalled"


def test_answers_to_questions_that_were_not_asked_are_refused():
    try:
        I.Response(respondent_ref="r0", responded_on=ASKED,
                   answers={"would_you_recommend_us": "yes"})
    except I.InterviewRefused as e:
        assert "closed" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the questionnaire grew a question")


# ---- what the sample is, and is not ---------------------------------------


def test_the_sample_reports_who_it_does_not_represent():
    out = I.sample(_round(5, [I.Response(respondent_ref="r0", responded_on=ASKED)]))
    assert out["response_rate"] == 0.2
    assert out["is_a_measurement"] is False
    assert "4 who did not" in out["does_not_represent"]
    assert "did not buy" in out["cannot_reach"]


def test_interviewing_needs_at_least_one_customer():
    assert I.may_open(customers=0)["may_open"] is False
    assert I.may_open(customers=12)["within_sprint"] is True
    assert I.may_open(customers=400)["within_sprint"] is False


# ---- hypotheses, and the one thing that promotes them ---------------------


def _hyp(**kw) -> I.Hypothesis:
    args = dict(claim="the chart is what sells it", question=I.WHY_BOUGHT,
                supported_by=3, of_responses=4, testable_by="listing_test")
    args.update(kw)
    return I.Hypothesis(**args)


def test_a_hypothesis_is_never_a_finding():
    h = _hyp()
    assert h.status == I.HYPOTHESIS
    assert h.to_dict()["status"] == I.HYPOTHESIS
    assert "voluntary sample cannot establish" in h.to_dict()["why_not_a_finding"]


def test_an_interview_cannot_test_an_interview():
    for bad in I.NOT_A_TEST:
        try:
            _hyp(testable_by=bad)
        except I.InterviewRefused as e:
            assert "cannot promote this" in str(e), bad
        else:  # pragma: no cover
            raise AssertionError(f"{bad} was accepted as a test")


def test_a_hypothesis_with_no_way_to_be_wrong_is_refused():
    try:
        _hyp(testable_by="it is obviously true")
    except I.InterviewRefused as e:
        assert "opinion with a sample size" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an untestable hypothesis was accepted")


def test_promotion_runs_only_through_an_external_instrument():
    h = _hyp()
    inside = I.promote(h, evidence={"source": "another_interview", "confirms": True})
    outside = I.promote(h, evidence={"source": "listing_test", "confirms": True})
    assert inside["promoted"] is False and inside["status"] == I.HYPOTHESIS
    assert outside["promoted"] is True and outside["status"] == I.FINDING


def test_an_external_test_that_did_not_confirm_does_not_promote():
    out = I.promote(_hyp(), evidence={"source": "listing_test", "confirms": False})
    assert out["promoted"] is False and "did not confirm" in out["why"]


def test_a_reconstructed_hypothesis_needs_evidence_independent_of_memory():
    h = _hyp(question=I.WHAT_NEARLY_STOPPED, recall="reconstructed")
    weak = I.promote(h, evidence={"source": "listing_test", "confirms": True})
    strong = I.promote(h, evidence={"source": "listing_test", "confirms": True,
                                    "independent_of_recall": True})
    assert weak["promoted"] is False and "remembering" in weak["why"]
    assert strong["promoted"] is True


def test_support_cannot_exceed_the_responses_it_came_from():
    try:
        _hyp(supported_by=9, of_responses=4)
    except I.InterviewRefused as e:
        assert "at most all of them" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a hypothesis outnumbered its own sample")


def test_state_says_what_this_instrument_never_produces():
    out = I.state()
    assert out["produces"] == I.HYPOTHESIS and out["never_produces"] == I.FINDING
    assert out["blind_spot"] == "non-buyers, entirely"
    assert "left_a_good_review" in out["refused_selection_rules"]


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
