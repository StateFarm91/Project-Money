"""v1.1 lane I: model/provider failover (F-921) and cost-aware routing (F-922).

The transport is a stand-in (`EchoProvider` with an Anthropic model name), never a model's
judgement; no network call is made and no real spend can happen.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, SpendReservation  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.gateway import failover, routing  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway.model_gateway import EchoProvider  # noqa: E402

CHEAP_TASK = "listing_classify"       # cheap tier: haiku, approved fallback sonnet
DEEP_TASK = "benchmark_challenge"     # deep tier: opus, no fallback
AGENT = "market_radar"
PROMPT = "concept.naming@1"
VALUES = {"category": "c", "motifs": "m", "season": "s"}
GOOD = json.dumps({"names": ["A", "B", "C"]})


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _fail(db, model, n, *, kind_exc=None, at=None):
    for i in range(n):
        failover.record_attempt(db, provider="anthropic", model=model, ok=False, agent=AGENT,
                                error=kind_exc or TransientError("503"),
                                now=(at or datetime.now(timezone.utc)) - timedelta(seconds=n - i))


def _factory(failing: set[str]):
    def make(model: str):
        p = EchoProvider(name="anthropic", model=model, scripted=lambda s, u: GOOD,
                         fail_times=99 if model in failing else 0)
        prov = gw.AnthropicProvider(model=model)  # the real rates, so billing is realistic
        p.cost_per_1k_input_cad = prov.cost_per_1k_input_cad
        p.cost_per_1k_output_cad = prov.cost_per_1k_output_cad
        return p
    return make


# ---- policy -----------------------------------------------------------------


def test_fallbacks_only_go_up_and_deep_has_none():
    assert failover.APPROVED_FALLBACKS
    for tier_key, models in failover.APPROVED_FALLBACKS.items():
        base = failover.CAPABILITY_RANK[routing.TIERS[tier_key].model]
        for m in models:  # vacuity-ok: the deep tier has none by policy; asserted below
            assert failover.CAPABILITY_RANK[m] > base, (tier_key, m)
            assert m in gw.PRICES_USD_PER_MTOK, m
    assert failover.candidates(DEEP_TASK) == [routing.TIERS[routing.DEEP].model]
    assert failover.candidates(CHEAP_TASK) == ["claude-haiku-4-5", "claude-sonnet-5"]


def test_compiler_tasks_are_refused_not_routed():
    db = _db()
    d = failover.decide(db, "stitch_counts", agent=AGENT)
    assert d.action == failover.REFUSED
    try:
        failover.gateway_for(db, "stitch_counts", registry=Registry(db), agent=AGENT)
    except routing.TaskRefused:
        pass
    else:
        raise AssertionError("a pattern task reached a model")


# ---- F-921: health and failover ---------------------------------------------


def test_healthy_primary_is_chosen_and_unknown_is_not_down():
    db = _db()
    d = failover.decide(db, CHEAP_TASK, agent=AGENT)
    assert d.action == failover.CALL and d.chosen == "claude-haiku-4-5", d.to_dict()
    assert d.candidates[0]["health"] == failover.UNKNOWN


def test_failover_picks_the_healthy_approved_model_when_primary_is_down():
    db = _db()
    _fail(db, "claude-haiku-4-5", failover.DOWN_AFTER_CONSECUTIVE)
    h = failover.health(db)
    assert h["anthropic:claude-haiku-4-5"]["state"] == failover.DOWN
    d = failover.decide(db, CHEAP_TASK, agent=AGENT)
    assert d.action == failover.CALL and d.chosen == "claude-sonnet-5", d.to_dict()
    assert d.order == ["claude-sonnet-5"]
    assert "fallback" in d.reason


def test_a_down_model_half_opens_after_cooldown():
    db = _db()
    past = datetime.now(timezone.utc) - failover.COOLDOWN - timedelta(minutes=1)
    _fail(db, "claude-haiku-4-5", 3, at=past)
    assert failover.health(db)["anthropic:claude-haiku-4-5"]["state"] == failover.HALF_OPEN
    assert failover.decide(db, CHEAP_TASK, agent=AGENT).chosen == "claude-haiku-4-5"


def test_a_malformed_answer_is_not_an_outage():
    from brambleloop.core.resilience import MalformedModelOutput

    db = _db()
    _fail(db, "claude-haiku-4-5", 5, kind_exc=MalformedModelOutput("bad json"))
    assert failover.health(db)["anthropic:claude-haiku-4-5"]["state"] == failover.HEALTHY


def test_deep_task_with_its_model_down_parks_rather_than_degrading():
    db = _db()
    _fail(db, "claude-opus-5", 3)
    d = failover.decide(db, DEEP_TASK, agent=AGENT)
    assert d.action == failover.PARK and d.retry_after_s > 0, d.to_dict()
    try:
        failover.gateway_for(db, DEEP_TASK, registry=Registry(db), agent=AGENT)
    except failover.Parked as exc:
        assert isinstance(exc, TransientError)  # the worker retries it with backoff
        assert exc.decision["action"] == failover.PARK
    else:
        raise AssertionError("a deep task ran with its only approved model down")


def test_end_to_end_failover_records_attempts_and_bills_only_the_billed_call():
    db = _db()
    reg = Registry(db)
    gateway, d = failover.gateway_for(db, CHEAP_TASK, registry=reg, agent=AGENT,
                                      provider_factory=_factory({"claude-haiku-4-5"}))
    assert d.order == ["claude-haiku-4-5", "claude-sonnet-5"]
    out = gateway.complete_json(PROMPT, agent=AGENT, values=VALUES)
    assert out["_meta"]["model"] == "claude-sonnet-5", out["_meta"]
    with db.session() as s:
        attempts = [(r.artifact, r.detail["ok"]) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == failover.ATTEMPT_ACTION))]
        costs = list(s.scalars(select(CostEntry)))
        open_res = list(s.scalars(select(SpendReservation)
                                  .where(SpendReservation.released_at.is_(None))))
    assert attempts.count(("anthropic:claude-haiku-4-5", False)) == 2, attempts
    assert attempts.count(("anthropic:claude-sonnet-5", True)) == 1, attempts
    # The two 503s were not billed; the answer was, once, through the one spend path.
    assert len(costs) == 1 and costs[0].model == "claude-sonnet-5", costs
    assert costs[0].kind == routing.COST_KIND
    assert open_res == [], "a reservation was left holding budget"
    # The next decision remembers: two failures is DEGRADED, a third makes it DOWN.
    assert failover.health(db)["anthropic:claude-haiku-4-5"]["state"] == failover.DEGRADED
    _fail(db, "claude-haiku-4-5", 1)
    assert failover.decide(db, CHEAP_TASK, agent=AGENT).order == ["claude-sonnet-5"]


def test_a_total_outage_raises_and_corrupts_nothing():
    db = _db()
    reg = Registry(db)
    gateway, _d = failover.gateway_for(
        db, CHEAP_TASK, registry=reg, agent=AGENT,
        provider_factory=_factory({"claude-haiku-4-5", "claude-sonnet-5"}))
    try:
        gateway.complete_json(PROMPT, agent=AGENT, values=VALUES)
    except TransientError:
        pass
    else:
        raise AssertionError("a total outage returned an answer")
    with db.session() as s:
        assert list(s.scalars(select(CostEntry))) == []
        assert list(s.scalars(select(SpendReservation)
                              .where(SpendReservation.released_at.is_(None)))) == []
    # Every approved model is now DOWN for the next job: it parks instead of retrying blind.
    _fail(db, "claude-haiku-4-5", 1)
    _fail(db, "claude-sonnet-5", 1)
    assert failover.decide(db, CHEAP_TASK, agent=AGENT).action == failover.PARK
    st = failover.status(db)
    assert st["status"] == "DEGRADED" and st["models"]


# ---- F-922: cost-aware routing never exceeds a ceiling ----------------------


def _spend(db, cad, agent="someone"):
    with db.session() as s:
        s.add(CostEntry(agent=agent, amount_cad=cad, kind=routing.COST_KIND))


def test_routing_parks_when_the_month_cannot_afford_the_call():
    db = _db()
    ceiling = gw.monthly_ceiling_cad()
    _spend(db, ceiling - 1e-6)
    d = failover.decide(db, CHEAP_TASK, agent=AGENT)
    assert d.action == failover.PARK and "money" in d.reason, d.to_dict()
    assert all(not c["fits_month"] for c in d.candidates)


def test_a_dearer_fallback_is_not_used_when_it_would_cross_the_ceiling():
    db = _db()
    task = routing.TASKS[CHEAP_TASK]
    cheap = gw.estimate_cad("claude-haiku-4-5", input_tokens=task.typical_input_tokens,
                            output_tokens=task.max_output_tokens)
    dear = gw.estimate_cad("claude-sonnet-5", input_tokens=task.typical_input_tokens,
                           output_tokens=task.max_output_tokens)
    assert dear > cheap
    remaining = (cheap + dear) / 2
    _spend(db, gw.monthly_ceiling_cad() - remaining)
    assert failover.decide(db, CHEAP_TASK, agent=AGENT).chosen == "claude-haiku-4-5"
    _fail(db, "claude-haiku-4-5", 3)
    d = failover.decide(db, CHEAP_TASK, agent=AGENT)
    assert d.action == failover.PARK, d.to_dict()  # never routed into an overspend


def test_routing_respects_the_agent_daily_permission():
    db = _db()
    daily = gw.agent_daily_ceiling(db, AGENT)
    assert daily is not None and daily["daily_ceiling_cad"] > 0
    _spend(db, daily["daily_ceiling_cad"], agent=AGENT)
    d = failover.decide(db, CHEAP_TASK, agent=AGENT)
    assert d.action == failover.PARK and all(not c["fits_agent_day"] for c in d.candidates)


def test_an_identical_cacheable_request_is_served_without_a_call():
    db = _db()
    payload = {"title": "Granny square blanket pattern"}
    assert routing.TASKS[CHEAP_TASK].cacheable
    routing.remember_analysis(db, CHEAP_TASK, payload, {"pod": "blankets"})
    gateway, d = failover.gateway_for(db, CHEAP_TASK, registry=Registry(db), agent=AGENT,
                                      payload=payload, provider_factory=_factory(set()))
    assert gateway is None and d.action == failover.CACHED and d.cached == {"pod": "blankets"}


def test_status_is_unknown_without_attempts():
    db = _db()
    assert failover.status(db)["status"] == failover.UNKNOWN
    with db.session() as s:
        assert failover.status(s)["status"] == failover.UNKNOWN


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
