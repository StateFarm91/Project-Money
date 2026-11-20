"""Wave-4 lane SPEND, K5b: paid-call discipline in the gateway.

F-312 deterministic-before-generative, F-313 quality-proven routing, F-314 escalation, F-316
output-token discipline, F-317 batching with isolation, F-472 a breaker shared across workers,
F-328 no spend without a question, F-309 the shared systematic-failure breaker, F-318 a paid
backlog that does not drain is an incident. No test reaches a network: every provider is an
`EchoProvider` transport stand-in.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w4_spend_paid_discipline.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import importlib
import json

from r2_autonomy_harness import boot, run_tests

NAMES = '{"names": ["Fern", "Moss", "Bramble"]}'


def _echo(model, text=NAMES, fail_times=0, name="anthropic"):
    from brambleloop.gateway.model_gateway import EchoProvider

    return EchoProvider(name=name, model=model, cost_per_1k_input_cad=0.001,
                        cost_per_1k_output_cad=0.001, fail_times=fail_times,
                        scripted=(text if callable(text) else (lambda s, u: text)))


def _ask(gateway, agent="orchestrator"):
    return gateway.complete_json("concept.naming@1", agent=agent,
                                 values={"category": "throw", "motifs": "fern",
                                         "season": "autumn"})


def _cost_rows(db):
    from sqlalchemy import select

    from brambleloop.core.models import CostEntry

    with db.session() as s:
        return [(float(r.amount_cad), r.model, r.purpose) for r in s.scalars(select(CostEntry))]


def _refusals(db, which):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog
    from brambleloop.finance import spend_report

    with db.session() as s:
        return [d for d in s.scalars(select(AuditLog.detail).where(
            AuditLog.action == spend_report.REFUSED_ACTION)) if (d or {}).get("which") == which]


# -- F-312 ------------------------------------------------------------------------------------

def test_every_deterministic_question_names_code_that_exists_and_never_reaches_a_provider():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import failover, routing

    alts = routing.DETERMINISTIC_ALTERNATIVES
    assert alts, "the deterministic-alternative table is empty"
    assert set(routing.PATTERN_TASKS_REFUSED) <= set(alts), "a refused task has no pointer"
    assert not set(alts) & set(routing.TASKS), "a model task shadows a deterministic one"
    db = boot()
    called = []
    for key, target in alts.items():
        mod, fn = target.split(":")
        assert callable(getattr(importlib.import_module(mod), fn)), target
        try:
            routing.route(key)
            raise AssertionError(f"{key} routed to a model")
        except routing.TaskRefused as exc:
            assert target in str(exc), str(exc)
        d = failover.decide(db, key, agent="orchestrator")
        assert d.action == failover.REFUSED, d.to_dict()
        try:
            failover.gateway_for(db, key, registry=Registry(db), agent="orchestrator",
                                 provider_factory=lambda m: called.append(m) or _echo(m))
            raise AssertionError("gateway_for built a gateway for a deterministic question")
        except routing.TaskRefused:
            pass
    assert called == [], f"a provider was constructed for {called}"
    print(f"   {len(alts)} deterministic questions refused before any provider")


# -- F-316 ------------------------------------------------------------------------------------

def test_every_prompt_and_task_has_a_closed_schema_and_a_sized_output_budget():
    from brambleloop.gateway import laura_phrase  # noqa: F401  (registers its prompt)
    from brambleloop.gateway import prompts, routing

    every = prompts.all_prompts()
    assert len(every) >= 6, [p.ref for p in every]
    for p in every:
        assert p.output_schema, f"{p.ref} has no schema"
        assert 0 < p.max_output_tokens <= prompts.OUTPUT_TOKEN_CAP, (p.ref, p.max_output_tokens)
    assert routing.OUTPUT_TOKEN_CAP == prompts.OUTPUT_TOKEN_CAP
    assert routing.TASKS
    for key, task in routing.TASKS.items():
        assert 0 < task.max_output_tokens <= routing.OUTPUT_TOKEN_CAP, key
    # A three-name answer does not get a 2048-token allowance any more.
    assert prompts.get("concept.naming@1").max_output_tokens <= 300
    for bad in (prompts.Prompt(name="w4.noschema", version="1", system="s", template="t",
                               max_output_tokens=100),
                prompts.Prompt(name="w4.nobudget", version="1", system="s", template="t",
                               output_schema=("x",)),
                prompts.Prompt(name="w4.vast", version="1", system="s", template="t",
                               output_schema=("x",), max_output_tokens=50_000)):
        try:
            prompts.register(bad)
            raise AssertionError(f"{bad.ref} was registered")
        except prompts.PromptRefused:
            pass


def test_truncated_output_is_rejected_and_billed_not_passed_on():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.resilience import MalformedModelOutput
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot()
    g = ModelGateway([_echo("claude-haiku-4-5", text='{"names": ["Fern", "Mo')],
                     registry=Registry(db))
    try:
        _ask(g)
        raise AssertionError("a truncated answer was accepted")
    except MalformedModelOutput:
        pass
    billed = [r for r in _cost_rows(db) if r[0] > 0]
    assert billed, "a truncated answer the provider billed left no ledger row"


# -- F-313 ------------------------------------------------------------------------------------

def test_a_cheaper_route_needs_recorded_equivalence_and_a_regression_reverses_it():
    from brambleloop.gateway import failover, routing

    db = boot()
    task = "gallery_observation"                      # declared standard
    cheap = routing.TIERS[routing.CHEAP].model
    std = routing.TIERS[routing.STANDARD].model
    # Cost alone is refused by name.
    try:
        routing.override_route(db, task, routing.CHEAP, reason="haiku is cheaper")
        raise AssertionError("a cost-only downgrade was accepted")
    except routing.RouteRefused as exc:
        assert "may not be traded for cost" in str(exc) and "no recorded evidence" in str(exc)
    # Too small an eval set is not evidence.
    floors = {"shot_type": True, "composition": True, "legibility": True}
    routing.record_route_evidence(db, task, std, floors=floors, items=8, eval_ref="ev-1")
    routing.record_route_evidence(db, task, cheap, floors=floors, items=8, eval_ref="ev-1")
    try:
        routing.override_route(db, task, routing.CHEAP, reason="equivalent on ev-1")
        raise AssertionError("an 8-item eval authorised a downgrade")
    except routing.RouteRefused:
        pass
    # Equivalence on the same, large-enough eval set: accepted and in force.
    routing.record_route_evidence(db, task, std, floors=floors, items=40, eval_ref="ev-2")
    routing.record_route_evidence(db, task, cheap, floors=floors, items=40, eval_ref="ev-2")
    routing.override_route(db, task, routing.CHEAP, reason="equivalent on ev-2")
    _t, tier, basis = routing.effective_route(db, task)
    assert tier.key == routing.CHEAP and basis["basis"] == "evidenced_override", basis
    d = failover.decide(db, task, agent="market_radar")
    assert d.order and d.order[0] == cheap and "F-313" in d.reason, d.to_dict()
    # A regression recorded afterwards reverses it with nobody touching the override.
    routing.record_route_evidence(db, task, cheap, floors={**floors, "legibility": False},
                                  items=40, eval_ref="ev-2")
    _t, tier, basis = routing.effective_route(db, task)
    assert tier.key == routing.STANDARD and basis.get("override_reversed"), basis
    assert failover.decide(db, task, agent="market_radar").order[0] == std


# -- F-314 ------------------------------------------------------------------------------------

def test_an_unsure_cheap_answer_is_asked_once_more_one_tier_up_and_a_sure_one_is_not():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import failover, routing

    db = boot()
    cheap = routing.TIERS[routing.CHEAP].model
    std = routing.TIERS[routing.STANDARD].model
    asked = []

    def factory(model):
        conf = 0.3 if model == cheap else 0.95

        def say(s, u):
            asked.append(model)
            return json.dumps({"names": ["Fern", "Moss", "Bramble"], "confidence": conf})
        return _echo(model, text=say)

    g, d = failover.gateway_for(db, "concept_ideation", registry=Registry(db),
                                agent="creative_director", provider_factory=factory)
    assert d.order[0] == cheap and [p.model for p in g.escalation] == [std]
    out = _ask(g, agent="creative_director")
    assert asked == [cheap, std], asked
    assert out["_meta"]["model"] == std and out["_meta"]["escalation"]["ran"], out["_meta"]
    assert {r[1] for r in _cost_rows(db) if r[0] > 0} == {cheap, std}, "both calls billed"
    # A confident answer is not escalated, and an answer silent on confidence is not either.
    assert routing.needs_escalation({"names": [], "confidence": 0.9}) == ""
    assert routing.needs_escalation({"names": []}) == ""
    assert routing.needs_escalation({"verifiable": False})
    # Deep has nowhere to go; an optional nicety never pays a stronger tier.
    assert routing.escalation_tier("benchmark_challenge") is None
    assert routing.escalation_tier("laura.business_phrase") is None


def test_an_escalation_the_ceiling_refuses_returns_the_answer_marked_unsure():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import routing
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot()
    cheap = routing.TIERS[routing.CHEAP].model
    g = ModelGateway([_echo(cheap, text=json.dumps({"names": ["A", "B", "C"],
                                                    "confidence": 0.2}))],
                     registry=Registry(db))
    g.escalation = [_echo("unpriced-zero-model")]       # refused before any call (C-35)
    g.escalation[0].cost_per_1k_input_cad = g.escalation[0].cost_per_1k_output_cad = 0.0
    out = _ask(g)
    esc = out["_meta"]["escalation"]
    assert esc["ran"] is False and esc["unsure"] is True and esc["refused"], esc


# -- F-317 ------------------------------------------------------------------------------------

def test_a_batch_isolates_each_item_and_stops_whole_at_the_ceiling():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import routing
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot()
    cheap = routing.TIERS[routing.CHEAP].model

    def say(s, u):
        return "not json at all" if "poison" in u else NAMES

    g = ModelGateway([_echo(cheap, text=say)], registry=Registry(db))
    items = [{"category": c, "motifs": "fern", "season": "autumn"}
             for c in ("throw", "poison", "hat")]
    out = g.complete_each("concept.naming@1", items, agent="orchestrator")
    assert [o["index"] for o in out] == [0, 1, 2]
    assert [o["ok"] for o in out] == [True, False, True], out
    assert out[0]["result"]["names"] == ["Fern", "Moss", "Bramble"]
    assert "Malformed" in out[1]["error"], out[1]
    # A ceiling refusal ends the batch: the remaining items are named as not attempted.
    import os

    os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"] = "0.0000001"
    try:
        out = ModelGateway([_echo(cheap)], registry=Registry(boot())).complete_each(
            "concept.naming@1", items, agent="orchestrator")
    finally:
        del os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"]
    assert not any(o["ok"] for o in out) and "budget" in out[0]["error"], out
    assert all("not attempted" in o["error"] for o in out[1:]), out


# -- F-472 ------------------------------------------------------------------------------------

def test_a_second_worker_does_not_pay_to_rediscover_an_outage_the_first_recorded():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.resilience import TransientError
    from brambleloop.gateway import failover, routing
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot()
    cheap = routing.TIERS[routing.CHEAP].model
    # Worker A: its provider fails three times (breaker threshold high so only the durable
    # record, not A's own in-process breaker, can carry the outage to B).
    a = ModelGateway([_echo(cheap, fail_times=99)], registry=Registry(db),
                     breaker_threshold=50)
    for _ in range(2):
        try:
            _ask(a)
        except TransientError:
            pass
    assert failover.health(db)[f"anthropic:{cheap}"]["state"] == failover.DOWN
    # Worker B: a fresh gateway (new process in production) never calls the provider.
    b_provider = _echo(cheap, fail_times=99)
    b = ModelGateway([b_provider], registry=Registry(db), breaker_threshold=50)
    try:
        _ask(b)
        raise AssertionError("B answered through a DOWN provider")
    except TransientError as exc:
        assert "DOWN across workers" in str(exc), str(exc)
    assert b_provider._failures == 0, "B paid to rediscover the outage"


# -- F-328 ------------------------------------------------------------------------------------

def test_a_paid_call_naming_no_question_is_refused_and_recorded():
    from brambleloop.gateway import anthropic as gw

    db = boot()
    for kw in ({}, {"purpose": "  "}):
        try:
            gw.check_budget(db, model=gw.PROBE_MODEL, input_tokens=100, max_tokens=50, **kw)
            raise AssertionError(f"a paid call with no question was allowed: {kw}")
        except gw.NoQuestionRefused as exc:
            assert isinstance(exc, gw.BudgetExceeded)
    assert len(_refusals(db, "no_question")) == 2
    # A question, or the evidence the call serves, is enough; arithmetic-only is untouched.
    a = gw.check_budget(db, model=gw.PROBE_MODEL, input_tokens=100, max_tokens=50,
                        purpose="gallery_observation")
    b = gw.check_budget(db, model=gw.PROBE_MODEL, input_tokens=100, max_tokens=50,
                        evidence_ref="listing:123:image:4")
    gw.check_budget(db, model=gw.PROBE_MODEL, input_tokens=100, max_tokens=50, reserve=False)
    for r in (a, b):
        gw.release_reservation(db, r.get("reservation_id"))


def test_every_production_reserving_call_site_names_its_question():
    import ast
    from pathlib import Path

    from r2_autonomy_harness import SRC

    sites = 0
    for p in Path(SRC, "brambleloop").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(
                    n.func, "id", None)) in ("check_budget", "check_budget_cad"):
                kws = {k.arg: k.value for k in n.keywords}
                if "reserve" in kws and ast.unparse(kws["reserve"]) == "False":
                    continue
                sites += 1
                assert "purpose" in kws or "evidence_ref" in kws, f"{p}:{n.lineno}"
                assert ast.unparse(kws.get("purpose", ast.Constant("x"))) not in ("''", '""'), \
                    f"{p}:{n.lineno} passes an empty purpose"
    assert sites >= 15, sites
    print(f"   {sites} reserving call sites, each names its question")


# -- F-309 ------------------------------------------------------------------------------------

def test_a_floor_that_never_passes_stops_every_paid_call_for_that_method_until_it_changes():
    from brambleloop.finance import systematic
    from brambleloop.gateway import anthropic as gw

    db = boot()
    handler = "w4.test_handler"
    systematic.declare(handler, "m1")
    for i in range(systematic.MIN_ASKS_TO_BLOCK - 1):
        systematic.record(db, handler, "m1", {"parse": "fail"})
    # Four failures: unclassified, not blocked ("nobody asked enough" != "does not work").
    r = gw.check_budget(db, model=gw.PROBE_MODEL, input_tokens=10, max_tokens=10,
                        purpose=handler)
    gw.release_reservation(db, r["reservation_id"])
    systematic.record(db, handler, "m1", {"parse": "fail"})
    try:
        gw.check_budget(db, model=gw.PROBE_MODEL, input_tokens=10, max_tokens=10,
                        purpose=handler)
        raise AssertionError("a systematically failing method was paid for again")
    except gw.SystematicFailureRefused as exc:
        assert isinstance(exc, gw.BudgetExceeded) and "never once passed" in str(exc)
    assert _refusals(db, "systematic_failure")
    # One pass ever makes it stochastic: retrying is the remedy, so it is allowed.
    systematic.declare(handler, "m2")                  # a new method clears the block
    r = gw.check_budget(db, model=gw.PROBE_MODEL, input_tokens=10, max_tokens=10,
                        purpose=handler)
    gw.release_reservation(db, r["reservation_id"])
    systematic.declare(handler, "m1")
    systematic.record(db, handler, "m1", {"parse": "pass"})
    assert systematic.measure(db, handler, "m1")["stochastic"] == ["parse"]
    assert systematic.refusal(db, handler) == ""


def test_gallery_vision_feeds_the_breaker_and_reports_pending_before():
    from brambleloop.finance import systematic
    from brambleloop.intel import vision

    db = boot()
    out = vision.analyse(db, "w4-empty-benchmark", limit=3,
                         provider=_echo("claude-sonnet-5"))
    assert "pending_before" in out and out["pending_before"] == out["remaining"] == 0, out
    assert systematic.declared().get(vision.TASK) == vision.method_version()


# -- F-318 ------------------------------------------------------------------------------------

def test_a_paid_backlog_that_does_not_fall_is_a_financial_integrity_incident():
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from brambleloop.core.models import Incident
    from brambleloop.finance import spend_hygiene

    db = boot()
    now = datetime.now(timezone.utc)
    assert spend_hygiene.flat_backlogs(db, now) == [], "no runs is not a finding"
    for i, (before, after) in enumerate([(100, 99), (99, 101), (101, 100)]):
        spend_hygiene.note_backlog_run(db, processor="gallery_observation:mjs",
                                       pending_before=before, pending_after=after,
                                       processed=1, cost_cad=0.4, agent="market_radar",
                                       now=now - timedelta(hours=3 - i))
    # A draining processor in the same window is not flagged.
    for i, (before, after) in enumerate([(50, 40), (40, 30), (30, 20)]):
        spend_hygiene.note_backlog_run(db, processor="other:drains", pending_before=before,
                                       pending_after=after, processed=10, cost_cad=0.4,
                                       now=now - timedelta(hours=3 - i))
    flat = spend_hygiene.flat_backlogs(db, now)
    assert [f["processor"] for f in flat] == ["gallery_observation:mjs"], flat
    assert flat[0]["cad"] == 1.2 and flat[0]["pending_after"] >= flat[0]["pending_before"]
    out = spend_hygiene.sweep(db, now=now)
    assert out["ceilings_changed"] == 0
    with db.session() as s:
        inc = list(s.scalars(select(Incident).where(
            Incident.signature.like("spend-flat-paid-backlog:%"))))
    assert len(inc) == 1 and inc[0].severity == "P1", [(i.signature, i.severity) for i in inc]


if __name__ == "__main__":
    run_tests(globals())
