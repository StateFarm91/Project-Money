"""S2 review 6979817823: one estimator for a call's reservation and its paid-provider gate.

MEDIUM: `culture.classify` reserved the user text only while the OpenAI gate estimated system
+ user, so every OpenAI-routed classify was refused `reservation_underfunded`. Both now use
`providers.input_tokens`; the test runs the REAL classify caller routed to OpenAI with an owner
`openai-text` activation, faking only the outgoing request.
LOWs: `/api/cc/paid-providers` lists `openai-text`; a process-wide switch to a routed-only
vendor is a loud owner card naming `BRAMBLELOOP_MODEL_ROUTES`.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s2_fix_estimator.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import os

import network_guard
from r2_autonomy_harness import boot, run_tests

network_guard.install()
os.environ.setdefault("OPENAI_API_KEY", "k")      # presence only; `_post` is always faked

from sqlalchemy import select  # noqa: E402

from brambleloop.gateway import openai_chat as O, providers  # noqa: E402
from test_s2_fix_routing import MINI, Wire, _owner_session, _reservations, _Routes, ok  # noqa


def test_one_estimator_counts_system_user_and_images_per_model():
    assert providers.input_tokens(MINI, system="s" * 400, user="u" * 400) == 200
    assert providers.input_tokens(MINI, user="u" * 8, images=2) == 2 + 2 * 2500
    assert providers.input_tokens("gpt-4.1-2025-04-14", images=1) == 1600
    from brambleloop.gateway import anthropic

    assert providers.input_tokens("claude-sonnet-4-5", images=1) == \
        anthropic.IMAGE_TOKENS_ESTIMATE
    # The vision callers reserve the Anthropic per-image figure through `providers`; it must
    # cover every OpenAI vision model's own per-image figure the gate charges.
    for model in O.VISION_MODELS:
        assert providers.IMAGE_TOKENS_ESTIMATE >= providers.image_tokens(model), model


def test_the_gate_estimates_with_the_shared_estimator():
    p = O.OpenAIProvider(model=MINI)
    seen = {}
    real = O.estimate_cad

    def spy(model, *, input_tokens, output_tokens):
        seen.setdefault("calls", []).append(input_tokens)
        return real(model, input_tokens=input_tokens, output_tokens=output_tokens)

    O.estimate_cad = spy
    try:
        try:
            p.complete("S" * 400, "U" * 4000, max_tokens=50)
        except Exception:  # noqa: BLE001 - not activated: refused after estimating
            pass
    finally:
        O.estimate_cad = real
    assert seen["calls"][0] == providers.input_tokens(MINI, system="S" * 400, user="U" * 4000)


def test_classify_routed_to_openai_is_reserved_gated_and_answered():
    from brambleloop.core.models import CostEntry
    from brambleloop.culture import classify as C
    from brambleloop.gateway import paid_provider_gate as G

    db = boot("s2fix-classify-")
    G.activate(db, provider=G.OPENAI_TEXT, scope=G.TEXT, by="owner:test",
               session_public_id=_owner_session(db), daily_ceiling_cad=5.0,
               monthly_ceiling_cad=20.0, per_gallery_cad=5.0)
    topics = ["Cottagecore", "Granny Square"]
    answer = json.dumps({"Cottagecore": "viral_aesthetic", "Granny Square": "nostalgia_era"})
    with _Routes(f"{C.TASK}=openai"), Wire(ok(answer)) as w:
        out = C.classify(topics, db=db)
    assert len(w.sent) == 1, out
    assert out.get("filed") == {"Cottagecore": "viral_aesthetic",
                                "Granny Square": "nostalgia_era"}, out
    assert ("openai", w.sent[0]["model"]) in _reservations(db)
    with db.session() as s:
        costs = [c.provider for c in s.scalars(select(CostEntry))]
    assert costs == ["openai"], (costs, out)


def test_the_owner_view_lists_openai_text():
    from brambleloop.gateway import paid_provider_gate as G

    db = boot("s2fix-view-")
    rows = G.owner_view(db)["providers"]
    text = [r for r in rows if r["provider"] == G.OPENAI_TEXT]
    assert {r["scope"] for r in text} == {G.TEXT, G.PROBE}, rows
    assert G.OPENAI_TEXT in G.owner_view(db)["month_gated_cad"]


def test_a_routed_only_process_switch_is_a_loud_owner_card_until_it_is_removed():
    from brambleloop.core.models import OwnerAction

    db = boot("s2fix-card-")

    def card():
        with db.session() as s:
            return [(r.done, r.state, r.action) for r in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == providers.VENDOR_CARD_KEY))]

    assert providers.vendor_switch_card(db, env={})["state"] == "clear" and card() == []
    env = {providers.VENDOR_VAR: "openai"}
    assert providers.vendor_switch_card(db, env=env)["state"] == "raised"
    assert providers.vendor_switch_card(db, env=env)["state"] == "raised"     # one card
    rows = card()
    assert len(rows) == 1 and rows[0][0] is False and providers.ROUTES_VAR in rows[0][2]
    assert providers.vendor_switch_card(db, env={})["state"] == "closed"
    assert card()[0][:2] == (True, "satisfied")



def test_the_health_sweep_raises_the_vendor_switch_card():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import OwnerAction
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.release import handle_health_sweep
    from brambleloop.runtime.worker import JobContext

    db = boot("s2fix-sweep-")
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    saved = os.environ.get(providers.VENDOR_VAR)
    os.environ[providers.VENDOR_VAR] = "openai"
    try:
        ctx = JobContext(job=queue.enqueue("orchestrator", "ops.health",
                                           {"cadence": "health_sweep"}),
                         db=db, queue=queue, registry=Registry(db), phase=None)
        out = handle_health_sweep(ctx)
    finally:
        if saved is None:
            os.environ.pop(providers.VENDOR_VAR, None)
        else:
            os.environ[providers.VENDOR_VAR] = saved
    assert (out.get("model_vendor") or {}).get("state") == "raised", out.get("model_vendor")
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == providers.VENDOR_CARD_KEY,
            OwnerAction.done.is_(False))) is not None

def test_the_owner_card_example_route_names_a_real_task():
    """Verdict 6985175377 LOW: the card's example route is a task the router knows."""
    from brambleloop.culture import classify
    from brambleloop.gateway import routing

    assert providers.EXAMPLE_ROUTE_TASK in routing.TASKS
    assert providers.EXAMPLE_ROUTE_TASK == classify.TASK
    from brambleloop.core.models import OwnerAction

    db = boot("s2fix-route-")
    providers.vendor_switch_card(db, env={providers.VENDOR_VAR: "openai"})
    with db.session() as s:
        action = s.scalars(select(OwnerAction.action).where(
            OwnerAction.requirement_key == providers.VENDOR_CARD_KEY)).one()
    assert f"{providers.ROUTES_VAR}={providers.EXAMPLE_ROUTE_TASK}=openai" in action, action
    assert "culture_classify" not in action


def test_an_invalid_route_refuses_only_its_own_task():
    """Verdict 6998037105 MEDIUM: one bad entry never refuses the fleet. With
    `topic_filing=openai,typo_task=openai` topic_filing still routes and unrelated tasks still
    resolve; a malformed entry refuses only the task it names."""
    from brambleloop.gateway import routing
    from brambleloop.gateway.model_gateway import NoProviderAvailable

    t = providers.EXAMPLE_ROUTE_TASK
    env = {providers.ROUTES_VAR: f"{t}=openai,typo_task=openai"}
    assert "typo_task" not in routing.TASKS and "listing_copy" in routing.TASKS
    table, invalid = providers.parse_routes(env)
    assert table == {t: "openai"} and [b["entry"] for b in invalid] == ["typo_task=openai"]
    assert providers.vendor_for(t, env) == "openai"
    assert providers.vendor_for("listing_copy", env) == providers.DEFAULT_VENDOR
    assert providers.for_task("listing_copy", env=env).name == providers.DEFAULT_VENDOR
    # A malformed entry names its task: that task is refused, the rest are not.
    env = {providers.ROUTES_VAR: f"listing_copy,{t}=openai"}
    try:
        providers.vendor_for("listing_copy", env)
        raise AssertionError("a malformed entry must refuse its own task")
    except NoProviderAvailable as exc:
        assert "is not task=vendor" in str(exc) and "other tasks are unaffected" in str(exc)
    assert providers.vendor_for(t, env) == "openai"
    assert providers.vendor_for("concept_ideation", env) == providers.DEFAULT_VENDOR
    # A route naming an undeclared task refuses that task (and only it).
    try:
        providers.vendor_for("typo_task", {providers.ROUTES_VAR: "typo_task=openai"})
        raise AssertionError("an undeclared routed task must be refused")
    except NoProviderAvailable as exc:
        assert "not a routing task" in str(exc), exc


def test_invalid_routes_raise_one_owner_card_naming_each_entry():
    from brambleloop.core.models import OwnerAction

    db = boot("s2fix-routes-card-")

    def card():
        with db.session() as s:
            return [(r.done, r.action) for r in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == providers.ROUTES_CARD_KEY))]

    assert providers.routes_card(db, env={})["state"] == "clear" and card() == []
    env = {providers.ROUTES_VAR: f"{providers.EXAMPLE_ROUTE_TASK}=openai,typo_task=openai,oops"}
    out = providers.routes_card(db, env=env)
    assert out["state"] == "raised" and len(out["invalid"]) == 2, out
    assert providers.routes_card(db, env=env)["state"] == "raised"          # one card
    rows = card()
    assert len(rows) == 1 and rows[0][0] is False
    assert "'typo_task=openai'" in rows[0][1] and "'oops'" in rows[0][1], rows[0][1]
    good = {providers.ROUTES_VAR: f"{providers.EXAMPLE_ROUTE_TASK}=openai"}
    assert providers.routes_card(db, env=good)["state"] == "closed"
    assert card()[0][0] is True


def test_the_health_sweep_raises_the_invalid_routes_card():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import OwnerAction
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.release import handle_health_sweep
    from brambleloop.runtime.worker import JobContext

    db = boot("s2fix-routes-sweep-")
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    saved = os.environ.get(providers.ROUTES_VAR)
    os.environ[providers.ROUTES_VAR] = "typo_task=openai"
    try:
        ctx = JobContext(job=queue.enqueue("orchestrator", "ops.health",
                                           {"cadence": "health_sweep"}),
                         db=db, queue=queue, registry=Registry(db), phase=None)
        out = handle_health_sweep(ctx)
    finally:
        if saved is None:
            os.environ.pop(providers.ROUTES_VAR, None)
        else:
            os.environ[providers.ROUTES_VAR] = saved
    assert (out.get("model_routes") or {}).get("state") == "raised", out.get("model_routes")
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == providers.ROUTES_CARD_KEY,
            OwnerAction.done.is_(False))) is not None

def test_an_unknown_vendor_or_a_duplicate_route_is_named_and_refused():
    """Verdict 6999967600 S2 LOW: `topic_filing=bogus` and a task routed twice are invalid
    entries: each refuses only its task and is named on the owner card."""
    from brambleloop.gateway.model_gateway import NoProviderAvailable

    t = providers.EXAMPLE_ROUTE_TASK
    env = {providers.ROUTES_VAR: f"{t}=bogus,listing_copy=openai,listing_copy=anthropic"}
    table, invalid = providers.parse_routes(env)
    assert table == {}, table
    whys = {b["entry"]: b["why"] for b in invalid}
    assert "not a registered model vendor" in whys[f"{t}=bogus"]
    assert "a second time" in whys["listing_copy=anthropic"]
    for task in (t, "listing_copy"):
        try:
            providers.vendor_for(task, env)
            raise AssertionError(f"{task} resolved through an invalid route")
        except NoProviderAvailable as exc:
            assert "other tasks are unaffected" in str(exc), exc
    assert providers.vendor_for("concept_ideation", env) == providers.DEFAULT_VENDOR
    db = boot("s2fix-routes-card-2-")
    out = providers.routes_card(db, env=env)
    assert out["state"] == "raised" and len(out["invalid"]) == 2, out


if __name__ == "__main__":
    run_tests(globals())
