"""#259: the trust sprint, and the four fifths of it that happen before the first customer.

Reading the requirement as written produces a plan that starts on the day of the first sale,
and that is the wrong day for four of the five. A flawless download is a property of the
delivery path; the first buyer either gets the file or does not.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import first_hundred as F  # noqa: E402
from brambleloop.commerce.buyer_trust import REQUIRED_DISCLOSURES  # noqa: E402


# --- when each priority actually happens ----------------------------------------------------

def test_four_of_the_five_do_not_need_a_customer():
    out = F.state()
    assert len(out["before_the_first_customer"]) == 4
    assert out["needs_customers"] == ["rapid_support"]


def test_rapid_support_is_the_one_that_genuinely_waits():
    """It is a response time, and there is nothing to respond to yet."""
    assert F.PRIORITIES["rapid_support"]["when"] == F.DURING
    assert "nothing to respond to yet" in F.PRIORITIES["rapid_support"]["why_not_later"]


def test_every_before_priority_says_why_it_cannot_wait():
    for key, spec in F.PRIORITIES.items():
        if spec["when"] != F.BEFORE:
            continue
        assert len(spec["why_not_later"].split()) >= 6, key
        assert spec["ready_when"], key


def test_truthful_expectations_points_at_the_disclosures_that_already_exist():
    assert all(d in F.PRIORITIES["truthful_expectations"]["ready_when"]
               for d in sorted(REQUIRED_DISCLOSURES)[:1])


# --- the sprint that has not started ------------------------------------------------------------

def test_nothing_ready_and_nobody_bought_is_reported_as_both():
    out = F.status(customers=0, readiness=F.Readiness())
    assert out["started"] is False
    assert out["before_the_first_customer"]["outstanding"] == [
        "flawless_downloads", "truthful_expectations", "defect_prevention",
        "post_purchase_clarity"]
    assert "four of its five priorities do not need it to" in out["note"]


def test_the_four_can_be_finished_before_anybody_arrives():
    out = F.status(customers=0, readiness=F.Readiness(True, True, True, True))
    before = out["before_the_first_customer"]
    assert before["outstanding"] == []
    assert "the only time they can be" in before["note"]


def test_a_started_sprint_counts_down_and_says_each_arrives_once():
    out = F.status(customers=40, readiness=F.Readiness(True, True, True, True))
    assert out["started"] is True and out["finished"] is False
    assert "60 customers left" in out["note"]


def test_the_sprint_ends():
    """A permanent sprint is just how the company works, and calling it a sprint is how
    nobody asks when the extra cost stops."""
    out = F.status(customers=100, readiness=F.Readiness(True, True, True, True))
    assert out["finished"] is True
    assert "the ordinary standard" in out["note"]


def test_support_is_unmeasurable_until_there_is_something_to_respond_to():
    out = F.status(customers=0, readiness=F.Readiness())
    assert out["rapid_support"]["measurable"] is False
    assert "needs something to respond to" in out["rapid_support"]["why"]
    measured = F.status(customers=10, readiness=F.Readiness(), measured_response_hours=3.0)
    assert measured["rapid_support"]["measurable"] is True


def test_a_negative_customer_count_is_not_a_count():
    try:
        F.status(customers=-1, readiness=F.Readiness())
    except F.SprintRefused as exc:
        assert "not a count" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a negative cohort was reported on")


# --- what the sprint may spend ---------------------------------------------------------------------

def test_the_sprint_spends_time_and_prevention():
    for kind in F.MAY_SPEND:
        assert F.check_investment(kind)["allowed"] is True


def test_the_sprint_may_not_spend_the_price():
    """A discount teaches the hundred buyers whose repeat behaviour matters most that the
    price is negotiable, and they are exactly the cohort the value ladder depends on."""
    out = F.check_investment("a launch discount", is_discount=True)
    assert out["allowed"] is False
    assert "the cohort the value ladder depends on" in out["why"]
    assert F.check_investment("the price")["allowed"] is False


def test_something_outside_the_list_is_not_a_trust_investment():
    out = F.check_investment("a billboard")
    assert out["allowed"] is False
    assert "is not something this sprint spends" in out["why"]


def test_state_says_when_the_sprint_ends():
    out = F.state()
    assert out["ends_at_customers"] == F.SPRINT_ENDS_AT_CUSTOMERS == 100
    assert "arrives exactly once" in out["note"]


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
