"""W4-LAURA1 budget: the owner-approved CA$0.50/day model ceiling for Laura (2026-10-11,
DECISION_LOG D-W4-LAURA1-BUDGET), enforced through the existing registry + gateway path.

* declared in `agents.registry.DEFAULT_AGENTS` and reconciled into the agent row;
* the daily cap is checked AND a reservation is written BEFORE the provider is called;
* a call that would exceed CA$0.50 today is refused with no provider call, and the briefing
  falls back transparently to the deterministic text (no new spend);
* the monthly ceiling still binds even when Laura's day has room;
* model selection is unchanged (the declared standard tier).

No network, no API key, stub transport only.
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_laura1_budget.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import w3_laura_cc_harness as H  # noqa: E402  (isolated environment, network refused)

from sqlalchemy import delete, select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry, ceiling_audit  # noqa: E402
from brambleloop.core.models import Agent, AuditLog, CostEntry  # noqa: E402
from brambleloop.finance import reservations, spend_policy, spend_report  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import laura_briefing, routing  # noqa: E402
from brambleloop.laura.agency import talk  # noqa: E402

DB = H.DB
H.seed_company()
PURPOSE = laura_briefing.PROMPT.ref
Q = ("Laura, give me a complete but concise CEO briefing. Tell me what Brambleloop "
     "accomplished in the last 24 hours, what each department is working on, what is "
     "preventing our first Etsy sale, and the five most important things you need me to "
     "decide. Separate verified facts from unknowns, and tell me what you can handle without "
     "my involvement.")
SECTIONS = ("What we accomplished in the last 24 hours", "What each department is working on",
            "What is preventing our first Etsy sale", "The 5 decisions I need from you, ranked",
            "Verified facts vs unknowns", "What I can handle without you")


def _billed():
    with DB.session() as s:
        return list(s.scalars(select(CostEntry).where(CostEntry.purpose == PURPOSE)))


def _clear(tag: str) -> None:
    with DB.session() as s:
        s.execute(delete(CostEntry).where(CostEntry.purpose == tag))


def _seed_spend(agent: str, cad: float, tag: str) -> None:
    with DB.session() as s:
        s.add(CostEntry(agent=agent, amount_cad=cad, kind=routing.COST_KIND, purpose=tag,
                        at=datetime.now(timezone.utc)))


def _factory(calls: list, events: list | None = None, seen: list | None = None):
    def make(model):
        from brambleloop.gateway.model_gateway import EchoProvider

        def scripted(system, user):
            calls.append(model)
            if events is not None:
                events.append("provider_call")
            if seen is not None:      # what is reserved at the moment the provider is asked
                seen.extend(r for r in reservations.outstanding(DB)["reservations"]
                            if r["agent"] == "laura")
            return json.dumps({"sections": []})

        return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                            cost_per_1k_output_cad=0.001, scripted=scripted)
    return make


def _complete_fallback(r: dict) -> None:
    heads = [l[3:] for l in r["answer"].splitlines() if re.match(r"^\d\. [A-Z]", l)]
    assert heads == list(SECTIONS), heads
    assert r["answer"].splitlines()[1].startswith("Model synthesis unavailable:"), r["answer"]
    assert "deterministic fallback briefing" in r["answer"]


def test_owner_approved_ceiling_is_declared_and_reconciled_into_the_registry():
    spec = next(a for a in DEFAULT_AGENTS if a["name"] == "laura")
    assert spec["daily_cost_ceiling_cad"] == 0.50
    assert Registry(DB).get("laura").daily_cost_ceiling_cad == 0.50
    perm = gw.agent_daily_ceiling(DB, "laura")
    assert perm["daily_ceiling_cad"] == 0.50, perm
    assert laura_briefing.laura_daily_permission(DB) == 0.50
    with DB.session() as s:
        rows = [(a.name, a.daily_cost_ceiling_cad) for a in s.scalars(select(Agent))]
    audit = ceiling_audit(rows)
    assert audit["ok"] is True and "laura" not in audit["declared_no_spend"], audit
    # model selection unchanged: the declared standard tier, no stronger fallback
    task, tier = routing.route(laura_briefing.TASK)
    assert tier.model == routing.TIERS[routing.STANDARD].model and not task.stronger_fallback


def test_cap_is_checked_and_reserved_before_the_provider_call():
    events: list = []
    seen: list = []
    calls: list = []
    real = gw.check_budget_cad

    def spy(db, **kw):
        if kw.get("agent") == "laura":
            events.append("check_and_reserve")
        return real(db, **kw)

    gw.check_budget_cad = spy
    try:
        before = len(_billed())
        r = talk.converse(DB, Q, session_public_id="s_budget_ok",
                          provider_factory=_factory(calls, events, seen))
    finally:
        gw.check_budget_cad = real
    assert calls and r["synthesis"]["source"] == "model", r["synthesis"]
    assert events == ["check_and_reserve", "provider_call"], events
    assert seen and all(0 < x["amount_cad"] <= 0.50 for x in seen), seen
    assert {x["purpose"] for x in seen} == {PURPOSE}, seen
    after = [x for x in reservations.outstanding(DB)["reservations"] if x["agent"] == "laura"]
    assert after == [], "the reservation is released once the call is billed"
    billed = _billed()[before:]
    assert len(billed) == 1 and billed[0].agent == "laura", billed


def test_a_call_that_would_exceed_the_daily_cap_is_refused_with_no_provider_call():
    tag = "test:laura-day-spent"
    _seed_spend("laura", 0.49, tag)               # CA$0.49 of CA$0.50 already spent today
    try:
        calls: list = []
        before = len(_billed())
        r = talk.converse(DB, Q, session_public_id="s_budget_day",
                          provider_factory=_factory(calls))
        assert calls == [], "no provider call past the daily cap"
        assert len(_billed()) == before, "no new spend past the daily cap"
        assert r["synthesis"]["source"] == "unavailable", r["synthesis"]
        assert "agent 'laura'" in r["synthesis"]["reason"] and "0.50" in \
            r["synthesis"]["reason"], r["synthesis"]["reason"]
        _complete_fallback(r)
        # the authoritative check itself, with its reservation: refused, nothing reserved,
        # and the refusal audited
        try:
            gw.check_budget_cad(DB, estimate_cad=0.05, agent="laura", purpose=PURPOSE)
        except gw.AgentCeilingExceeded:
            pass
        else:
            raise AssertionError("CA$0.49 + CA$0.05 > CA$0.50 was allowed")
        assert [x for x in reservations.outstanding(DB)["reservations"]
                if x["agent"] == "laura"] == []
        with DB.session() as s:
            last = s.scalars(select(AuditLog).where(
                AuditLog.action == spend_report.REFUSED_ACTION)
                .order_by(AuditLog.id.desc())).first()
        assert last.detail["agent"] == "laura" and last.detail["which"] == \
            "agent_daily_ceiling" and last.detail["ceiling"] == 0.5, last.detail
    finally:
        _clear(tag)


def test_the_monthly_ceiling_still_applies_when_lauras_day_has_room():
    tag = "test:month-spent"
    ceiling = spend_policy.ceiling_cad()
    month = routing.spent_this_month(DB)
    _seed_spend("market_radar", max(0.0, ceiling - month - 0.01), tag)  # month all but spent
    try:
        assert gw.agent_daily_ceiling(DB, "laura")["spent_today_cad"] < 0.10
        calls: list = []
        before = len(_billed())
        r = talk.converse(DB, Q, session_public_id="s_budget_month",
                          provider_factory=_factory(calls))
        assert calls == [] and len(_billed()) == before, (calls, r["synthesis"])
        assert r["synthesis"]["source"] == "unavailable"
        assert "month" in r["synthesis"]["reason"], r["synthesis"]["reason"]
        _complete_fallback(r)
        try:
            gw.check_budget_cad(DB, estimate_cad=0.05, agent="laura", purpose=PURPOSE)
        except gw.AgentCeilingExceeded:
            raise AssertionError("the month should refuse before the agent's day")
        except gw.BudgetExceeded:
            pass
        else:
            raise AssertionError("the monthly ceiling did not bind")
    finally:
        _clear(tag)


if __name__ == "__main__":
    H.run(globals())
