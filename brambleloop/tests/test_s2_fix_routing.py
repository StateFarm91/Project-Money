"""S2 fix (Main's verdict 6957356475, HIGH): OpenAI is routed per task, through the one router
every gateway builder asks, and an Anthropic path in the same process is untouched.

* `providers.vendor_for` reads `BRAMBLELOOP_MODEL_ROUTES` ("task=vendor,..."); a task it does
  not name stays on Anthropic. The process-wide switch may not name OpenAI.
* `failover.decide` / `gateway_for` / `job_gateway` build the routed vendor's provider; the
  ceiling ledger prices each call by the provider that serves it and records that provider.
* Real callers are driven: a `failover.gateway_for` JSON call and the `visual.inspect` grid
  describer (a vision judge, owner-activated as openai-vision) go to OpenAI, while another task
  in the same process reserves and builds on Anthropic.

No test reaches a network: `OpenAIProvider._post` is replaced; the network guard refuses sockets.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s2_fix_routing.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

import network_guard
from r2_autonomy_harness import boot, run_tests

network_guard.install()
os.environ.setdefault("OPENAI_API_KEY", "k")      # presence only; `_post` is always faked

from sqlalchemy import select  # noqa: E402

from brambleloop.gateway import failover, openai_chat as O, providers, routing  # noqa: E402
from brambleloop.gateway.model_gateway import NoProviderAvailable  # noqa: E402

AGENT = "orchestrator"
MINI = "gpt-4.1-mini-2025-04-14"


class Wire:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.sent: list[dict] = []

    def __enter__(self):
        self.original = O.OpenAIProvider._post
        wire = self

        def fake(provider, body, headers, timeout):
            wire.sent.append(json.loads(body.decode()))
            return wire.answers.pop(0)

        O.OpenAIProvider._post = fake
        return self

    def __exit__(self, *exc):
        O.OpenAIProvider._post = self.original


def ok(text, model=MINI, prompt_tokens=120, completion_tokens=40):
    return 200, json.dumps({
        "id": "chatcmpl-r1", "model": model,
        "choices": [{"message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}})


class _Routes:
    def __init__(self, table: str):
        self.table = table

    def __enter__(self):
        self.saved = os.environ.get(providers.ROUTES_VAR)
        os.environ[providers.ROUTES_VAR] = self.table
        return self

    def __exit__(self, *exc):
        if self.saved is None:
            os.environ.pop(providers.ROUTES_VAR, None)
        else:
            os.environ[providers.ROUTES_VAR] = self.saved


def _reservations(db):
    from brambleloop.core.models import SpendReservation

    with db.session() as s:
        return [((r.detail or {}).get("provider"), r.model)
                for r in s.scalars(select(SpendReservation))]


def test_the_router_is_per_task_and_the_process_switch_cannot_name_openai():
    env = {providers.ROUTES_VAR: "concept_ideation=openai"}
    assert providers.vendor_for("concept_ideation", env) == "openai"
    assert providers.vendor_for("topic_filing", env) == "anthropic"
    assert providers.for_task("topic_filing", env=env).name == "anthropic"
    p = providers.for_task("concept_ideation", env=env)
    assert (p.name, p.model) == ("openai", MINI)
    for bad in ({providers.VENDOR_VAR: "openai"},
                {providers.ROUTES_VAR: "concept_ideation"},
                {providers.ROUTES_VAR: "concept_ideation=nobody"}):
        try:
            providers.vendor_for("concept_ideation", bad)
            raise AssertionError(bad)
        except NoProviderAvailable:
            pass


def test_the_ledger_prices_each_call_by_the_provider_that_serves_it():
    from brambleloop.gateway import anthropic

    assert anthropic.provider_of_model(MINI) == "openai"
    assert anthropic.provider_of_model(routing.route("topic_filing")[1].model) == "anthropic"
    assert anthropic.provider_of_model("gpt-4.1") is None          # an alias is unpriced
    db = boot("s2fix-price-")
    a_model = routing.route("topic_filing")[1].model
    for model in (MINI, a_model):
        held = providers.check_budget(db, model=model, input_tokens=500, max_tokens=200,
                                      agent=AGENT, purpose="s2fix.price")
        assert held["estimate_cad"] > 0
    assert sorted(_reservations(db)) == sorted([("openai", MINI), ("anthropic", a_model)])


def test_gateway_for_builds_the_routed_vendor_and_bills_it_while_anthropic_stays():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway.anthropic import AnthropicProvider

    db = boot("s2fix-gw-")
    from test_s2_openai_provider import activate_text

    activate_text(db)
    registry = Registry(db)
    with _Routes("concept_ideation=openai"):
        gw, decision = failover.gateway_for(db, "concept_ideation", registry=registry,
                                            agent=AGENT)
        assert decision.action == failover.CALL
        assert [(p.name, p.model) for p in gw.providers] == [("openai", MINI)]
        assert all(r["provider"] == "openai" for r in decision.candidates)
        assert gw.escalation in (None, []), "no cross-vendor escalation"
        with Wire(ok('{"names": ["Fern", "Moss", "Bramble"]}')) as wire:
            data = gw.complete_json("concept.naming@1", agent=AGENT,
                                    values={"category": "throw", "motifs": "fern",
                                            "season": "autumn"})
        assert len(wire.sent) == 1 and wire.sent[0]["model"] == MINI
        assert data["_meta"]["provider"] == "openai"
        # A task the table does not name, in the same process, is Anthropic end to end.
        other, d2 = failover.gateway_for(db, "topic_filing", registry=registry, agent=AGENT)
        assert all(isinstance(p, AnthropicProvider) for p in other.providers)
        assert all(r["provider"] == "anthropic" for r in d2.candidates)
        jg = failover.job_gateway(db, "concept_ideation", registry=registry, agent=AGENT)
        assert [p.name for p in jg.providers] == ["openai"]
    with db.session() as s:
        rows = [(r.provider, r.model) for r in s.scalars(select(CostEntry))]
    assert rows == [("openai", MINI)], rows
    assert ("openai", MINI) in _reservations(db)


def _owner_session(db) -> str:
    from brambleloop.app.command_center import auth as cc_auth
    from brambleloop.app.command_center.models import OwnerSession

    cc_auth.ensure_tables(db)
    now = datetime.now(timezone.utc)
    pid = "s_" + secrets.token_hex(8)
    with db.session() as s:
        s.add(OwnerSession(public_id=pid, token_hash=secrets.token_hex(32), created_at=now,
                           last_seen_at=now, expires_at=now + timedelta(days=1),
                           stepup_until=now + timedelta(minutes=5)))
    return pid


def test_a_real_vision_judge_routed_to_openai_is_gated_reserved_and_billed_as_openai():
    from PIL import Image

    from brambleloop.core.models import CostEntry
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.visual import inspect

    db = boot("s2fix-vision-")
    G.activate(db, provider=G.OPENAI_VISION, scope=G.VISION, by="owner:test",
               session_public_id=_owner_session(db), daily_ceiling_cad=5.0,
               monthly_ceiling_cad=20.0, per_gallery_cad=5.0)
    path = os.path.join(_tmp.root() if hasattr(_tmp, "root") else "/tmp",
                        f"s2fix-{secrets.token_hex(4)}.png")
    Image.new("RGB", (64, 64), (200, 180, 150)).save(path)
    answer = json.dumps({"object_shown": "a crochet blanket", "object_count": 1,
                         "finished_or_in_progress": "finished", "human_present": False,
                         "text_present": False, "chart_or_diagram": False,
                         "dominant_colours": ["cream"], "clarity": "clear",
                         "third_party_marks": []})
    try:
        with _Routes(f"{inspect.TASK}=openai"), Wire(ok(answer, model="gpt-4.1-2025-04-14")) as w:
            out = inspect.identify_at_grid(path, families=["blanket"], db=db)
    finally:
        os.remove(path)
    assert out.get("verdict") == "clear", out
    assert len(w.sent) == 1
    sent = w.sent[0]
    assert sent["model"] == routing.openai_model_for(inspect.TASK)
    image = sent["messages"][-1]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,"), image[:40]   # a file, not its path
    assert ("openai", sent["model"]) in _reservations(db)
    with db.session() as s:
        costs = [(c.provider, c.model) for c in s.scalars(select(CostEntry))]
    # The cost row names the provider that served the call (it was hard-coded "anthropic").
    assert costs == [("openai", sent["model"])], costs


if __name__ == "__main__":
    run_tests(globals())
