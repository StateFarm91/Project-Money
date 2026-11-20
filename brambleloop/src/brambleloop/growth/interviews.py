"""Asking the first hundred buyers what happened, and not believing the answer too much.

Requirement 260. Invite a small voluntary sample of legitimate buyers and testers to give
structured feedback on why they clicked, why they bought, what nearly stopped them, whether
the pattern was clear and what they want next. No reward contingent on positive sentiment.
Convert responses into hypotheses.

The spec's last sentence is the honest one and it is worth not softening. A voluntary sample
answers a different question than the one asked: not "what do buyers think" but "what do the
people who answer surveys think", and those two populations differ most on exactly the axis
being measured -- the delighted and the furious both reply, the mildly disappointed majority
does not. So nothing this module produces is a measurement. It produces hypotheses, they are
labelled as such in the data rather than in a caveat, and the only route out of that label is
evidence from an instrument that did not ask anybody anything.

Three ways to bias a sample, in descending order of how easy they are to do by accident:

**Choose who to invite.** This is the one that needs guarding hardest, because it happens
before any volunteering and it feels like good sense. Inviting the buyers who left five
stars, or who came back a second time, or who never asked for a refund, produces a warm and
entirely useless sample, and every one of those selections can be described as "asking our
best customers". Selection is therefore restricted to rules that cannot see the outcome --
every order in a window, or every nth -- and outcome-correlated rules are refused by name.

**Pay for the answer you want.** "No reward contingent on positive sentiment" is checkable if
the incentive is fixed at invitation and identical across the round, and unfalsifiable if it
is decided afterwards. So the incentive lives on the invitation, a response may not carry
one, and a round whose invitations differ is refused. The intention of whoever set it is not
the test: an incentive chosen after reading the response is contingent by construction.

**Ask too late.** "What nearly stopped you" is the most valuable question here and the one
that decays fastest, because a person asked six weeks later does not recall a hesitation --
they construct a plausible one, sincerely. That answer is kept and marked `reconstructed`,
and reconstructed answers cannot carry a hypothesis on their own.

And the blind spot no sampling rule fixes: everyone who did not buy. They are the people
whose near-stop reason matters most and this instrument cannot reach a single one of them.
`commerce.friction` is where that half lives, because it reads the journey rather than the
survivors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from brambleloop.commerce import first_hundred
from brambleloop.growth import owned

# ---- what may be asked ----------------------------------------------------

WHY_CLICKED = "why_clicked"
WHY_BOUGHT = "why_bought"
WHAT_NEARLY_STOPPED = "what_nearly_stopped"
PATTERN_CLARITY = "pattern_clarity"
WHAT_NEXT = "what_next"

QUESTIONS: dict[str, str] = {
    WHY_CLICKED: "what made you open this listing rather than the others",
    WHY_BOUGHT: "what decided it",
    WHAT_NEARLY_STOPPED: "what almost made you close the tab",
    PATTERN_CLARITY: "where, if anywhere, the instructions were hard to follow",
    WHAT_NEXT: "what you would want us to make next",
}

# The vocabulary is closed. A questionnaire that gains a question each round cannot be
# compared across rounds, and the comparison is the only thing that makes a small sample
# worth running twice.
QUESTION_ORDER: tuple[str, ...] = (WHY_CLICKED, WHY_BOUGHT, WHAT_NEARLY_STOPPED,
                                   PATTERN_CLARITY, WHAT_NEXT)

# Only one question has a memory clock. Why they bought is a decision they made; what nearly
# stopped them is a feeling they had, and feelings are reconstructed, not retrieved.
RECALL_WINDOW_DAYS: dict[str, int] = {WHAT_NEARLY_STOPPED: 14}


# ---- who gets asked -------------------------------------------------------

SELECTION_RULES: dict[str, str] = {
    "all_in_window": "every order placed between two dates",
    "every_nth_order": "a fixed interval through the order sequence",
    "random_within_window": "a random draw from every order in a window",
}

# Each of these can be said out loud as a reason to prefer somebody, which is what makes them
# dangerous. All of them correlate with satisfaction, so all of them pre-select the answer.
NEVER_A_SELECTION_RULE: dict[str, str] = {
    "left_a_review": "reviewers are the two tails, not the middle",
    "left_a_good_review": "this is the survey answering itself",
    "repeat_buyer": "coming back is the outcome being measured",
    "no_refund_requested": "the unhappy are removed before they can answer",
    "seemed_friendly_in_support": "a judgement about tone, correlated with everything",
    "high_order_value": "willingness to pay is not a sampling frame for clarity",
}

MAX_SAMPLE = 20   # "a small voluntary sample" -- of a hundred customers, bounded on purpose


class InterviewRefused(ValueError):
    """A sample, an incentive or a claim the instrument cannot support."""


# ---- the incentive --------------------------------------------------------

NO_INCENTIVE = "none"
INCENTIVES: dict[str, str] = {
    NO_INCENTIVE: "nothing is offered",
    "fixed_credit": "a fixed shop credit, stated at invitation, paid on any response",
    "early_access": "early access to the next release, paid on any response",
}

NEVER_AN_INCENTIVE: dict[str, str] = {
    "prize_draw_for_good_feedback": "contingent on sentiment in the clearest possible way",
    "credit_if_helpful": "'helpful' is decided by the reader after reading",
    "refund_for_a_review": "buys the review, and Etsy prohibits it besides",
    "decided_after_reading": "contingency does not require intent, only ordering",
}


@dataclass(frozen=True)
class Invitation:
    """One person asked, with everything that could bias them fixed before they answer."""

    respondent_ref: str
    invited_on: date
    purchased_on: date
    selected_by: str
    incentive: str = NO_INCENTIVE
    order_ref: str = ""
    tester_ref: str = ""

    def __post_init__(self) -> None:
        if self.selected_by in NEVER_A_SELECTION_RULE:
            raise InterviewRefused(
                f"{self.selected_by!r} selects on the outcome: "
                f"{NEVER_A_SELECTION_RULE[self.selected_by]}. A sample chosen this way is "
                f"warm, defensible in a sentence, and measures nothing")
        if self.selected_by not in SELECTION_RULES:
            raise InterviewRefused(
                f"{self.selected_by!r} is not a selection rule: {sorted(SELECTION_RULES)}. "
                f"An unnamed rule cannot be shown to be blind to the answer")
        if self.incentive in NEVER_AN_INCENTIVE:
            raise InterviewRefused(
                f"{self.incentive!r} is contingent on sentiment: "
                f"{NEVER_AN_INCENTIVE[self.incentive]}")
        if self.incentive not in INCENTIVES:
            raise InterviewRefused(
                f"{self.incentive!r} is not a declared incentive: {sorted(INCENTIVES)}")
        if not (self.order_ref.strip() or self.tester_ref.strip()):
            raise InterviewRefused(
                "a respondent with neither an order nor a tester record is not a legitimate "
                "buyer or tester. This is the door a fabricated response walks through, and "
                "it is the same door the fake-review rule closes")
        if self.invited_on < self.purchased_on:
            raise InterviewRefused(
                "invited before they bought: the purchase date is what the recall window is "
                "measured from, and an invitation cannot precede it")


@dataclass(frozen=True)
class Response:
    """What one person said, anchored to the invitation that reached them."""

    respondent_ref: str
    responded_on: date
    answers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = sorted(set(self.answers) - set(QUESTIONS))
        if unknown:
            raise InterviewRefused(
                f"answers to questions that were not asked: {unknown}. The vocabulary is "
                f"closed so that two rounds can be compared")


def invite_gate(invitation: Invitation, consent: owned.Consent,
                today: date | None = None) -> dict:
    """Whether this invitation may be sent, under CASL rather than under enthusiasm.

    A feedback request to somebody who bought is a commercial electronic message, and the
    basis that carries it is the existing business relationship -- which expires two years
    after the transaction and not when the list stops being useful. `growth.owned` owns that
    clock; this only refuses to invent a second one.
    """
    verdict = owned.may_send(consent, today)
    if not verdict["may_send"]:
        return {"may_invite": False, **verdict,
                "why": f"CASL: {verdict['why']}"}
    if consent.basis == owned.IMPLIED_PUBLISHED:
        return {"may_invite": False, "basis": consent.basis,
                "why": ("a conspicuously published business address is a basis for writing "
                        "to a business about its business, not for surveying a private "
                        "buyer about their purchase")}
    return {"may_invite": True, "basis": consent.basis, "means": owned.BASES[consent.basis],
            "why": verdict["why"]}


# ---- the round ------------------------------------------------------------

@dataclass(frozen=True)
class Round:
    """One wave of invitations and whatever came back."""

    label: str
    invitations: tuple[Invitation, ...]
    responses: tuple[Response, ...] = ()

    def __post_init__(self) -> None:
        if not self.invitations:
            raise InterviewRefused("a round with no invitations has no sample to describe")
        if len(self.invitations) > MAX_SAMPLE:
            raise InterviewRefused(
                f"{len(self.invitations)} invitations exceeds the small sample this is meant "
                f"to be ({MAX_SAMPLE}). A large voluntary sample is not more representative, "
                f"only more confidently unrepresentative")
        incentives = {i.incentive for i in self.invitations}
        if len(incentives) > 1:
            raise InterviewRefused(
                f"a round offering different incentives to different people cannot show that "
                f"none of them was contingent on what was said: {sorted(incentives)}")
        rules = {i.selected_by for i in self.invitations}
        if len(rules) > 1:
            raise InterviewRefused(
                f"a round drawn by more than one selection rule has no describable sampling "
                f"frame: {sorted(rules)}")
        known = {i.respondent_ref for i in self.invitations}
        stray = sorted({r.respondent_ref for r in self.responses} - known)
        if stray:
            raise InterviewRefused(
                f"responses from people nobody invited: {stray}. Every response is anchored "
                f"to an invitation, because an unanchored response is indistinguishable from "
                f"an invented one")
        seen: set[str] = set()
        for r in self.responses:
            if r.respondent_ref in seen:
                raise InterviewRefused(
                    f"{r.respondent_ref} answered twice; one person, one weight")
            seen.add(r.respondent_ref)


def may_open(*, customers: int) -> dict:
    """Interviewing belongs to the trust sprint, and the trust sprint ends."""
    ends = first_hundred.SPRINT_ENDS_AT_CUSTOMERS
    if customers <= 0:
        return {"may_open": False,
                "why": ("no customers yet. There is nobody to ask, and a survey of testers "
                        "alone answers a question about testers")}
    return {"may_open": True, "customers": customers,
            "within_sprint": customers <= ends,
            "why": (f"inside the first {ends}, where each answer is a larger share of what "
                    f"is known" if customers <= ends else
                    f"past the first {ends}: still worth running, no longer the sprint")}


def sample(round_: Round) -> dict:
    """What the sample is, and -- said in the data -- what it is not."""
    invited = len(round_.invitations)
    responded = len(round_.responses)
    rate = responded / invited if invited else 0.0
    return {
        "label": round_.label, "invited": invited, "responded": responded,
        "response_rate": round(rate, 3),
        "selected_by": round_.invitations[0].selected_by,
        "frame": SELECTION_RULES[round_.invitations[0].selected_by],
        "incentive": round_.invitations[0].incentive,
        "incentive_means": INCENTIVES[round_.invitations[0].incentive],
        "represents": f"the {responded} people who chose to answer",
        "does_not_represent": (
            f"the {invited - responded} who did not, and the population they resemble. "
            f"Non-response is not missing data distributed like the data present: the "
            f"mildly disappointed are the likeliest to say nothing"),
        "cannot_reach": ("anybody who did not buy. Every respondent here is a survivor of "
                         "the decision this is trying to understand"),
        "is_a_measurement": False,
    }


def _recall(invitation: Invitation, response: Response, question: str) -> str:
    window = RECALL_WINDOW_DAYS.get(question)
    if window is None:
        return "recalled"
    days = (response.responded_on - invitation.purchased_on).days
    return "recalled" if days <= window else "reconstructed"


def answers(round_: Round) -> dict:
    """Every answer, with its recall quality attached rather than assumed."""
    by_ref = {i.respondent_ref: i for i in round_.invitations}
    out: dict[str, list[dict]] = {q: [] for q in QUESTION_ORDER}
    for response in round_.responses:
        inv = by_ref[response.respondent_ref]
        for question, text in response.answers.items():
            if not text.strip():
                continue
            out[question].append({
                "respondent_ref": response.respondent_ref,
                "text": text,
                "recall": _recall(inv, response, question),
                "days_after_purchase": (response.responded_on - inv.purchased_on).days,
            })
    return out


# ---- what comes out -------------------------------------------------------

HYPOTHESIS = "hypothesis"
FINDING = "finding"

# An interview cannot test an interview. The instruments that can are the ones that observe
# behaviour instead of asking about it.
EXTERNAL_TESTS: dict[str, str] = {
    "listing_test": "commerce.listing_tests -- change the listing, watch what happens",
    "friction_audit": "commerce.friction -- read the journey, including non-answerers",
    "regression": "gates.regression -- check the pattern itself against the claim",
    "experiment": "a designed experiment with a holdout, per requirement 266",
}

NOT_A_TEST: dict[str, str] = {
    "another_interview": ("asking the same self-selected people again reproduces the "
                          "selection, not the finding"),
    "a_larger_survey": "more of a biased sample is more bias, measured more precisely",
    "model_agreement": "a model agreeing with a hypothesis is not evidence about buyers",
}


@dataclass(frozen=True)
class Hypothesis:
    """A claim the interviews suggest, carrying the reason it is not yet a finding."""

    claim: str
    question: str
    supported_by: int
    of_responses: int
    testable_by: str
    recall: str = "recalled"

    def __post_init__(self) -> None:
        if self.question not in QUESTIONS:
            raise InterviewRefused(f"{self.question!r} is not a question this survey asks")
        if self.testable_by in NOT_A_TEST:
            raise InterviewRefused(
                f"{self.testable_by!r} cannot promote this: "
                f"{NOT_A_TEST[self.testable_by]}")
        if self.testable_by not in EXTERNAL_TESTS:
            raise InterviewRefused(
                f"{self.testable_by!r} is not an external test: {sorted(EXTERNAL_TESTS)}. A "
                f"hypothesis with no way to be wrong is an opinion with a sample size")
        if self.supported_by < 1 or self.supported_by > self.of_responses:
            raise InterviewRefused(
                "support has to be at least one response and at most all of them")

    @property
    def status(self) -> str:
        return HYPOTHESIS

    def to_dict(self) -> dict:
        return {
            "claim": self.claim, "question": self.question, "status": HYPOTHESIS,
            "supported_by": self.supported_by, "of_responses": self.of_responses,
            "recall": self.recall, "testable_by": self.testable_by,
            "test_means": EXTERNAL_TESTS[self.testable_by],
            "why_not_a_finding": (
                "a voluntary sample cannot establish a fact about buyers; it can only "
                "suggest one worth testing on an instrument that did not ask anybody"),
        }


def promote(hypothesis: Hypothesis, *, evidence: dict) -> dict:
    """The only route from hypothesis to finding, and it does not run through this module."""
    source = (evidence or {}).get("source")
    if source not in EXTERNAL_TESTS:
        return {"promoted": False, "status": HYPOTHESIS,
                "why": (f"evidence source {source!r} is not one of {sorted(EXTERNAL_TESTS)}. "
                        f"{NOT_A_TEST.get(source, 'an interview cannot confirm an interview')}")}
    if hypothesis.recall == "reconstructed" and not evidence.get("independent_of_recall"):
        return {"promoted": False, "status": HYPOTHESIS,
                "why": ("this hypothesis rests on reconstructed recall, so confirming it "
                        "needs evidence that does not depend on anybody remembering")}
    if not evidence.get("confirms"):
        return {"promoted": False, "status": HYPOTHESIS,
                "why": f"{source} ran and did not confirm it"}
    return {"promoted": True, "status": FINDING, "source": source,
            "why": f"confirmed by {EXTERNAL_TESTS[source]}"}


def state() -> dict:
    """What this instrument is for, and what it is structurally unable to say."""
    return {
        "requirement": 260,
        "produces": HYPOTHESIS,
        "never_produces": FINDING,
        "max_sample": MAX_SAMPLE,
        "questions": list(QUESTION_ORDER),
        "selection_rules": sorted(SELECTION_RULES),
        "refused_selection_rules": sorted(NEVER_A_SELECTION_RULE),
        "refused_incentives": sorted(NEVER_AN_INCENTIVE),
        "casl": "an invitation is a commercial electronic message; growth.owned gates it",
        "blind_spot": "non-buyers, entirely",
        "note": ("the sample's job is to generate hypotheses cheaply, not to settle them. "
                 "Settling them is what listing tests and the friction audit are for"),
    }
