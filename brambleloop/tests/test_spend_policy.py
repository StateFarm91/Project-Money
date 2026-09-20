"""The governing spend policy, and the ways a cost rule quietly becomes a quality rule.

The owner raised the ceiling from CA$25 to CA$100 and reversed the argument that goes with
it: quality decides, cost is the tie-breaker, waste is refused at any budget. The build had
done the old thing faithfully, and the faithfulness was the problem -- routing decisions,
cadence intervals and analysis depths had accumulated whose stated reason was the ceiling
rather than the work.

Most of these tests are about that class of drift: a number written twice, a table nothing
reads, a bound hardcoded into a production assertion, a dimension that only exists where
somebody remembered to write it.
"""
from __future__ import annotations

import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.finance import spend_policy as P  # noqa: E402
from brambleloop.finance import spend_report as R  # noqa: E402
from brambleloop.gateway import anthropic as A  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402

SRC = ROOT / "src" / "brambleloop"
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


# ---- one ceiling ------------------------------------------------------------


def test_the_ceiling_is_written_once_and_everything_else_reads_it():
    """It was written twice -- in the gateway and in routing -- which is the defect this
    build keeps naming about prices: a number written twice is a number that will drift,
    and the one that bills is the one that is true."""
    assert routing.MONTHLY_CEILING_CAD == P.CEILING_CAD
    assert A.monthly_ceiling_cad() == P.CEILING_CAD
    assert P.CEILING_CAD == 100.0
    assert P.PREVIOUS_CEILING_CAD == 25.0


def test_no_module_hardcodes_a_ceiling_literal():
    """A second literal is a second ceiling, and the second one is always the stale one."""
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "spend_policy.py":
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"(ceiling\w*)\s*[:=]\s*(25\.0|100\.0)\b", line, re.I):
                offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert offenders == [], f"{offenders} write a ceiling rather than reading the policy"


def test_the_environment_may_lower_the_ceiling_and_never_raise_it():
    import os

    previous = os.environ.get("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD")
    try:
        os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"] = "5000"
        assert A.monthly_ceiling_cad() == P.CEILING_CAD
    finally:
        if previous is None:
            os.environ.pop("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD", None)
        else:
            os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"] = previous


def test_a_ceiling_is_not_a_target_and_the_policy_says_so():
    state = P.state()
    assert "the expectation is that most months cost far less" in \
        state["ceiling_is_not_a_target"]
    assert state["policy"] == "QUALITY FIRST. COST SECOND. WASTE NEVER."


# ---- quality may not be traded for cost -------------------------------------


def test_every_priority_the_owner_named_records_what_may_not_be_traded():
    assert len(P.PRIORITIES) == 6
    for priority in P.PRIORITIES:
        assert priority.never, f"{priority.key} names nothing it will not trade"
    keys = {p.key for p in P.PRIORITIES}
    assert {"product_creativity", "mjs_intelligence", "product_visualization",
            "model_identity", "listing_and_storefront_creative",
            "high_value_judgement"} == keys


def test_a_downgrade_argued_from_cost_is_refused_by_name():
    raised = None
    try:
        P.may_downgrade_for_cost(priority_key="mjs_intelligence",
                                 reason="the cheaper tier is adequate")
    except P.PolicyRefused as exc:
        raised = exc
    assert raised is not None
    assert "may not be traded for cost" in str(raised)
    assert "cost is the tie-breaker, not the argument" in str(raised)


def test_an_unknown_priority_is_refused_rather_than_waved_through():
    raised = None
    try:
        P.may_downgrade_for_cost(priority_key="something_else", reason="x")
    except P.PolicyRefused as exc:
        raised = exc
    assert raised is not None and "not one of the owner's spending priorities" in str(raised)


def test_waste_is_refused_at_any_budget_and_is_not_a_saving():
    assert "recompute_unchanged" in P.WASTE
    assert "ask_what_code_answers" in P.WASTE
    state = P.state()
    assert "waste_refused_at_any_budget" in state
    assert state["levers"], "the third clause is an instruction to keep using these"


# ---- routing reconciled ------------------------------------------------------


def test_the_gallery_task_is_not_on_the_cheap_tier():
    """MJs intelligence is the owner's second spending priority, and visual-analysis depth
    is named as something not to reduce for cost. The code called the cheap model directly
    and bypassed this table entirely for a day."""
    task, tier = routing.route("gallery_observation")
    assert task.tier != routing.CHEAP
    assert tier.model == "claude-sonnet-5"


def test_the_judgements_that_decide_what_ships_are_on_the_deep_tier():
    for key in ("creative_evaluation", "benchmark_challenge", "concept_generation",
                "construction_reading", "image_benchmark_judging"):
        task, _ = routing.route(key)
        assert task.tier == routing.DEEP, f"{key} decides what ships and is not on deep"


def test_a_cheap_tier_task_survives_being_asked_why():
    """Under a quality-first policy every cheap-tier choice has to be justified by the
    question rather than by the price."""
    for key, task in routing.TASKS.items():
        if task.tier != routing.CHEAP:
            continue
        assert task.why, f"{key} is on the cheap tier with no stated reason"
        assert P.REFUSED_JUSTIFICATION not in task.why.lower()


# ---- spend accounting ---------------------------------------------------------


def test_every_dimension_the_owner_asked_for_is_a_column_rather_than_a_json_key():
    from brambleloop.core.models import CostEntry

    columns = set(CostEntry.__table__.columns.keys())
    assert {"provider", "model", "agent", "department", "product_slug", "purpose",
            "estimated_cad"} <= columns, (
        "a dimension that has to be grepped out of a JSON field is a dimension nobody "
        "reports on")


def test_unknown_spend_is_counted_rather_than_dropped():
    """A report that dropped it would show a tidier number that does not match the bill,
    and the gap would be exactly the spending nobody could account for."""
    db = _db()
    R.record(db, agent="orchestrator", amount_cad=2.0, purpose="")
    R.record(db, agent="orchestrator", amount_cad=1.0, purpose="gallery_observation")
    out = R.what_it_bought(db)
    assert out["spent_cad"] == 3.0
    assert out["by_purpose"][R.UNATTRIBUTED]["cad"] == 2.0


def test_the_reservation_is_kept_beside_the_bill():
    """An estimate nobody compares against the invoice can drift by a factor of three, and
    did: every ceiling check in that session was computed against the wrong number."""
    db = _db()
    R.record(db, agent="a", amount_cad=3.0, estimated_cad=1.0, purpose="concept_generation")
    reconciliation = R.what_it_bought(db)["reconciliation"]
    row = reconciliation["by_purpose"]["concept_generation"]
    assert row["ratio"] == 3.0
    assert row["under_estimated"] is True
    assert row["within_tolerance"] is False


def test_a_call_with_no_reservation_is_counted_separately_from_a_variance_of_zero():
    db = _db()
    R.record(db, agent="a", amount_cad=1.0, purpose="x")
    assert R.what_it_bought(db)["reconciliation"]["calls_with_no_reservation"] == 1


def test_the_report_answers_by_every_dimension():
    db = _db()
    R.record(db, agent="market_radar", amount_cad=1.0, purpose="gallery_observation",
             provider="anthropic", model="claude-sonnet-5", department="intel",
             product_slug="a-hat")
    out = R.what_it_bought(db)
    for key in ("by_purpose", "by_model", "by_provider", "by_agent", "by_department",
                "by_product"):
        assert out[key], f"{key} is empty on a row that carried every dimension"


# ---- escalation ----------------------------------------------------------------


def test_an_untroubled_month_asks_for_nothing():
    out = P.escalation(_db(), now=NOW)
    assert out["required"] is False
    assert "Nothing is being constrained and nothing is asked for" in out["why"]


def test_an_escalation_carries_all_six_fields_the_owner_asked_for():
    db = _db()
    R.record(db, agent="creative_director", amount_cad=P.CEILING_CAD * 0.9,
             purpose="concept_generation", model="claude-opus-5", department="creative")
    out = P.escalation(db, now=NOW, constrained=["the weekly arena expedition"],
                       expected_value="two more expeditions a month")
    assert out["required"] is True
    for field in ("current_spend_cad", "burn_rate_cad_per_day", "what_the_money_produced",
                  "what_is_constrained", "proposed_ceiling_cad", "expected_improvement"):
        assert field in out, f"{field} missing: a request without it is a bill"
    assert out["what_the_money_produced"]["concept_generation"]["cad"] > 0
    assert "quality is not silently degraded" in out["not_doing_meanwhile"]


def test_the_escalation_fires_before_the_first_refusal_rather_than_at_it():
    """An escalation arriving at the moment of the first refusal arrives too late to be a
    decision and only in time to be a complaint."""
    assert 0.5 < P.ESCALATE_AT_SHARE < 1.0
    assert P.headroom(P.CEILING_CAD * P.ESCALATE_AT_SHARE)["escalate"] is True
    assert P.headroom(P.CEILING_CAD * 0.5)["escalate"] is False


def test_the_projection_says_it_is_arithmetic_rather_than_a_forecast():
    db = _db()
    R.record(db, agent="a", amount_cad=1.0, purpose="x")
    out = R.what_it_bought(db)
    assert "arithmetic rather than a forecast" in out["projection_is_linear"]
    assert out["burn_rate_cad_per_day"] > 0


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
