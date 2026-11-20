"""Wave-3 lane SPEND, W-8: release-chain handlers build their gateway through failover.

`failover.job_gateway` = `gateway_for` with the (None, decision) CACHED return handled (a
multi-call handler never receives a None gateway), PARK raised as a TransientError, and spend
recording unchanged (an ordinary ModelGateway; `_record` stays the only billing writer). No
test here reaches a network.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_spend_gateway_w8.py
"""
from __future__ import annotations

import ast
from pathlib import Path

from r2_autonomy_harness import SRC, boot, run_tests

W8_HANDLERS = ("handle_creative_blinded", "handle_creative_tournament",
               "handle_creative_expedition", "handle_seasonal_cycle_proof")


def _fake_factory(model):
    from brambleloop.gateway.model_gateway import EchoProvider

    return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                        cost_per_1k_output_cad=0.001,
                        scripted=lambda s, u: '{"names": ["Fern", "Moss", "Bramble"]}')


def test_job_gateway_is_an_ordinary_gateway_on_the_decided_order():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import failover
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot()
    g = failover.job_gateway(db, "concept_generation", registry=Registry(db),
                             agent="creative_director", job_id=None,
                             provider_factory=_fake_factory)
    assert isinstance(g, ModelGateway), type(g)
    assert g.decision.action == failover.CALL, g.decision.to_dict()
    assert [p.model for p in g.providers] == g.decision.order


def test_a_cached_decision_never_hands_a_handler_a_none_gateway():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import failover, routing

    db = boot()
    real = failover.decide
    failover.decide = lambda *a, **k: failover.Decision(
        failover.CACHED, "concept_generation", "creative_director", cached={"x": 1},
        reason="an identical request was answered before")
    try:
        g = failover.job_gateway(db, "concept_generation", registry=Registry(db),
                                 agent="creative_director", provider_factory=_fake_factory)
    finally:
        failover.decide = real
    assert g is not None
    _task, tier = routing.route("concept_generation")
    assert [p.model for p in g.providers] == [tier.model]
    assert "multi-call handler" in g.decision.reason


def test_park_is_raised_as_a_retryable_error():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.resilience import TransientError
    from brambleloop.gateway import failover

    db = boot()
    real = failover.decide
    failover.decide = lambda *a, **k: failover.Decision(
        failover.PARK, "concept_generation", "creative_director", reason="all down",
        retry_after_s=600)
    try:
        failover.job_gateway(db, "concept_generation", registry=Registry(db),
                             agent="creative_director", provider_factory=_fake_factory)
        raise AssertionError("PARK must raise")
    except failover.Parked as exc:
        assert isinstance(exc, TransientError)
    finally:
        failover.decide = real


def test_spend_stays_single_path_through_job_gateway():
    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway import failover

    db = boot()
    g = failover.job_gateway(db, "concept_generation", registry=Registry(db),
                             agent="creative_director", provider_factory=_fake_factory)
    g.complete_json("concept.naming@1", agent="creative_director",
                    values={"category": "throw", "motifs": "fern", "season": "autumn"})
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry)))
    assert len(rows) == 1 and rows[0].kind == "llm", rows


def test_the_four_release_handlers_use_job_gateway():
    src = (Path(SRC) / "brambleloop" / "runtime" / "release.py").read_text()
    tree = ast.parse(src)
    found = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name in W8_HANDLERS:
            body = ast.get_source_segment(src, fn) or ""
            found[fn.name] = ("failover.job_gateway(" in body,
                              "ModelGateway([AnthropicProvider" in body)
    assert set(found) == set(W8_HANDLERS), found
    for name, (uses, bypasses) in found.items():
        assert uses and not bypasses, (name, uses, bypasses)


if __name__ == "__main__":
    run_tests(globals())
