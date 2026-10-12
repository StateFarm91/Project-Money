"""W4-PRIVLAURA (PL-5, G-9): a private reply is a new paid purpose under agent `laura`, and it is
refused BEFORE the call unless the owner has authorised it -- and Laura's existing CA$0.50/day
permission and the monthly ceiling still bind. Every refusal is audited without content.

Direct calls into `gateway.laura_register.reply` (the isolated call) with plain strings, and the
private-context path for the end-to-end case. Stubbed transport; neutral sentinels only.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_pl_budget.py
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from w3_laura_memory_harness import check, finish, fresh_db
import w4_pl_harness as PL

from sqlalchemy import select

from brambleloop.agents.registry import Registry
from brambleloop.core.models import AuditLog, CostEntry, SpendReservation
from brambleloop.gateway import laura_register as LR
from brambleloop.gateway import paid_calls

USER = LR.render_user(facts=[("PRIV-LABEL-B", "PRIV-SENTINEL-BUDGET-1")],
                      turns=[("owner", "PRIV-SENTINEL-BUDGET-2")],
                      message="PRIV-SENTINEL-BUDGET-3")
SENT = ("PRIV-SENTINEL-BUDGET-1", "PRIV-SENTINEL-BUDGET-2", "PRIV-SENTINEL-BUDGET-3", PL.REPLY)


def _db():
    db = fresh_db()
    Registry(db).seed_defaults()
    return db


def _refusals(db) -> list:
    with db.session() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == "spend.refused")))


def _reservations(db) -> list:
    with db.session() as s:
        return list(s.scalars(select(SpendReservation)))


def _costs(db, purpose=LR.PURPOSE) -> list:
    with db.session() as s:
        return list(s.scalars(select(CostEntry).where(CostEntry.purpose == purpose)))


def _call(db):
    try:
        return LR.reply(db, system=LR.PROMPT.system, user=USER, env=None)
    except LR.ReplyUnavailable as exc:
        return exc.code


def _clean(db, where: str) -> None:
    blob, _ = PL.table_dump(db)
    leaked = [x for x in SENT if x in blob]
    assert not leaked, (where, leaked)


def test_private_reply_is_refused_without_authorised_ceiling():
    db = _db()
    assert Registry(db).get("laura").daily_cost_ceiling_cad == 0.50   # unchanged ceiling
    for value in (None, "", "0", "-1", "nan", "inf", "abc"):
        with PL.enabled(None, **{LR.DAILY_AUTH_ENV: value}):
            assert LR.daily_authorisation_cad() == 0.0, value
            assert _call(db) == "SPEND_UNAUTHORISED", value
    refused = _refusals(db)
    assert len(refused) == 7 and all(r.artifact == LR.PURPOSE for r in refused)
    assert {r.detail["which"] for r in refused} == {"purpose_daily_unauthorised"}
    assert all(r.actor == "laura" and r.detail["estimate"] > 0 for r in refused)
    assert _reservations(db) == [] and _costs(db) == []      # refused before any reservation
    _clean(db, "unauthorised")


def test_over_the_authorisation_or_lauras_day_is_refused_pre_call():
    db = _db()
    # 1. The owner's figure is smaller than one call's padded estimate.
    with PL.enabled(None, **{LR.DAILY_AUTH_ENV: "0.001"}):
        assert _call(db) == "SPEND_CEILING"
    # 2. Today's private-reply spend already fills the authorisation.
    with db.session() as s:
        s.add(CostEntry(agent="laura", amount_cad=0.395, kind="llm", purpose=LR.PURPOSE,
                        provider="anthropic", model="claude-sonnet-5"))
    with PL.enabled(None, **{LR.DAILY_AUTH_ENV: "0.40"}):
        assert _call(db) == "SPEND_CEILING"
    whiches = [r.detail["which"] for r in _refusals(db)]
    assert whiches == ["purpose_daily_authorisation"] * 2, whiches
    # 3. A generous owner figure cannot lift Laura's CA$0.50/day permission: her other
    #    spend today leaves no room, so check_budget_cad refuses (agent_daily_ceiling).
    db2 = _db()
    with db2.session() as s:
        s.add(CostEntry(agent="laura", amount_cad=0.499, kind="llm",
                        purpose="laura.ceo_briefing@3", provider="anthropic",
                        model="claude-sonnet-5"))
    with PL.enabled(None, **{LR.DAILY_AUTH_ENV: "5.00"}):
        assert _call(db2) == "BUDGET"
    assert [r.detail["which"] for r in _refusals(db2)] == ["agent_daily_ceiling"]
    assert _costs(db2) == [] and _reservations(db2) == []
    # 4. The monthly ceiling binds too (spent month).
    db3 = _db()
    with db3.session() as s:
        s.add(CostEntry(agent="orchestrator", amount_cad=10_000.0, kind="llm",
                        purpose="concept_generation", provider="anthropic",
                        model="claude-opus-5"))
    with PL.enabled(None):
        assert _call(db3) == "BUDGET"
    assert [r.detail["which"] for r in _refusals(db3)] == ["monthly_ceiling"]
    for d in (db, db2, db3):
        _clean(d, "ceilings")


def test_a_paid_reply_bills_tokens_and_cost_only_and_releases_its_reservation():
    db = _db()
    stub = PL.Stub()
    with PL.enabled(stub):
        out = LR.reply(db, system=LR.PROMPT.system, user=USER)
    assert out["text"] == PL.REPLY and out["model_ref"] == "anthropic/claude-sonnet-5"
    assert out["tokens_in"] == 120 and out["tokens_out"] == 30 and out["cost_cad"] > 0
    costs = _costs(db)
    assert len(costs) == 1 and costs[0].agent == "laura" and costs[0].kind == "llm"
    assert costs[0].estimated_cad > costs[0].amount_cad > 0
    res = _reservations(db)
    assert len(res) == 1 and res[0].released_at is not None and res[0].purpose == LR.PURPOSE
    assert res[0].agent == "laura"
    _clean(db, "paid reply")
    # A refused system prompt or empty message never reaches the provider.
    with PL.enabled(None):
        for sys_, user in (("You are someone else.", USER), (LR.PROMPT.system, "  ")):
            try:
                LR.reply(db, system=sys_, user=user)
                raise AssertionError("refused input reached the provider")
            except LR.ReplyUnavailable as exc:
                assert exc.code == "REFUSED"


def test_inside_a_job_scope_the_reply_is_refused():
    db = _db()
    job = SimpleNamespace(id=4242, job_type="laura.executive_tick", agent="laura",
                          attempts=1, lease_token="t", leased_by="w")
    with PL.enabled(None):
        with paid_calls.job_scope(db, job):
            assert paid_calls.current_job_id() == 4242
            assert _call(db) == "JOB_SCOPE"
    assert _reservations(db) == [] and _costs(db) == []


def test_the_owner_figure_is_read_by_name_only():
    e = LR.enablement({LR.REGISTER_SWITCH_ENV: "1", LR.DAILY_AUTH_ENV: "0.25",
                       "ANTHROPIC_API_KEY": "x", LR.PRIVATE_KEY_ENV: "y"})
    assert e["enabled"] is True and e["spend_authorised_cad_per_day"] == 0.25
    blob = json.dumps(e)
    assert '"y"' not in blob and ': "x"' not in blob, blob                # no secret values
    assert LR.enablement({})["enabled"] is False                         # default OFF
    assert LR.enablement({LR.REGISTER_SWITCH_ENV: "true", LR.DAILY_AUTH_ENV: "1",
                          "ANTHROPIC_API_KEY": "x", LR.PRIVATE_KEY_ENV: "y"})[
        "enabled"] is False                                              # exactly "1"


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
assert _TESTS
for _n, _f in _TESTS:
    check(_n, _f)
finish()
