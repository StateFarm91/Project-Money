"""#255/#251: tools that answer before they ask, and a flow judged on the wrong number.

Two failures carry this file. A free calculator that withholds its answer until somebody
hands over an email address is a lead capture form wearing a calculator's name. And a
lifecycle programme judged on open rate is optimised toward subject lines and away from the
purchase -- which is why there is no open rate here to optimise.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.growth import owned, tools as T  # noqa: E402
from brambleloop.growth.experiments import CAUSAL_DESIGNS, HOLDOUT, NO_CONTROL  # noqa: E402


# --- #255: the tool answers first --------------------------------------------------------

def test_a_tool_that_asks_before_it_answers_is_a_capture_form():
    out = T.check_tool(T.Tool("yardage_helper", asks_for_email_before_answering=True,
                              leads_to="winter-throw",
                              why_next="the pattern this yardage was for"))
    assert out["ok"] is False
    assert any("wearing a calculator's name" in r for r in out["reasons"])


def test_an_address_after_the_answer_is_fine_and_says_so():
    out = T.check_tool(T.Tool("yardage_helper", leads_to="winter-throw",
                              why_next="somebody who knows how much yarn it takes wants the "
                                       "pattern it was for"))
    assert out["ok"] is True
    assert "never as the price of it" in out["email_after_the_answer_is_fine"]


def test_a_tool_with_no_path_to_anything_is_a_gift():
    out = T.check_tool(T.Tool("size_calculator"))
    assert any("is not this requirement" in r for r in out["reasons"])


def test_five_of_the_six_tools_are_arithmetic_this_system_already_runs():
    """The useful finding is which is an owner action and which is engineering."""
    out = T.inventory()
    assert len(out["already_computed"]) == 5
    assert out["needs_building"] == ["motif_preview"]
    assert "one owner action rather than" in out["note"]


def test_every_tool_names_where_its_arithmetic_lives():
    for key, spec in T.TOOLS.items():
        assert spec["computed_by"], key
        assert spec["answers"], key
        assert isinstance(spec["exists"], bool), key


def test_a_tool_nobody_named_is_refused():
    try:
        T.Tool("vibe_checker")
    except T.ToolRefused as exc:
        assert "is not a tool" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented tool joined the layer")


# --- #251: the number this programme refuses to be judged on --------------------------------

def test_there_is_no_open_rate_to_optimise():
    assert "open_rate" in T.NEVER_REPORTED_AS_PERFORMANCE
    out = T.check_flow(T.Flow("launch", "purchase", design=HOLDOUT))
    assert "open_rate" not in out
    assert "open_rate" in out["never_reported"]


def test_a_flow_sent_to_everybody_measures_the_people_who_were_buying_anyway():
    out = T.check_flow(T.Flow("launch", "purchase", design=NO_CONTROL))
    assert out["may_claim_contribution"] is False
    assert any("no incremental anything" in r for r in out["reasons"])
    assert "is not a contribution" in out["note"]


def test_a_holdout_makes_the_difference_the_flows():
    out = T.check_flow(T.Flow("launch", "purchase", design=HOLDOUT))
    assert out["may_claim_contribution"] is True
    assert HOLDOUT in CAUSAL_DESIGNS


def test_a_segment_built_on_an_open_is_built_on_a_mail_client():
    try:
        T.Flow("launch", "opened_an_email")
    except T.ToolRefused as exc:
        assert "fetched an image" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a segment was built on an open")


def test_segments_come_from_something_the_subscriber_did_or_said():
    for evidence in T.SEGMENT_EVIDENCE:
        assert T.check_flow(T.Flow("welcome", evidence))["segment_evidence"] == evidence


def test_all_six_flows_the_requirement_names_exist():
    assert set(T.FLOWS) == {"welcome", "category_interest", "launch",
                            "post_purchase_support", "cross_sell", "seasonal_reactivation"}


# --- the cap is on the person ------------------------------------------------------------------

def test_the_frequency_cap_counts_the_person_rather_than_the_flow():
    """Five flows that each send politely once a week send five times a week to the person
    who is in all five, and every flow's own report looks reasonable."""
    out = T.frequency({"a": 5, "b": 1})
    assert out["ok"] is False
    assert out["over_cap"] == {"a": 5}
    assert "the person in all five gets five" in out["why"]


def test_nobody_over_the_cap_is_reported_plainly():
    assert T.frequency({"a": 1})["ok"] is True


# --- consent is not restated ----------------------------------------------------------------------

def test_every_send_goes_through_the_casl_gate():
    consent = owned.Consent("addr-1", owned.EXPRESS, date(2026, 1, 1), "signup form")
    message = {"sender_name": "Brambleloop", "mailing_address": "a real address",
               "contact": "hello@example.invalid",
               "unsubscribe_url": "https://example.invalid/u"}
    out = T.may_send(consent, message, today=date(2026, 9, 20))
    assert out["sendable"] is True
    assert "not legal advice" in out["screen_not_clearance"]

    withdrawn = owned.Consent("addr-2", owned.EXPRESS, date(2026, 1, 1), "signup form",
                              withdrawn_on=date(2026, 5, 1))
    assert T.may_send(withdrawn, message, today=date(2026, 9, 20))["sendable"] is False


def test_state_names_what_it_refuses_to_be_judged_on():
    out = T.state()
    assert "open rate" in out["note"]
    assert out["max_sends_per_week"] == T.MAX_SENDS_PER_WEEK
    assert "growth.owned" in out["consent"]


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
