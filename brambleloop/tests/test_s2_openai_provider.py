"""S2 increment 1: the OpenAI provider inside the existing model gateway.

Main's S2 (#28, 6953884261): an OpenAI text/vision adapter in the EXISTING gateway, explicit
model/version, retry/fallback, provider identity and provenance on results, estimate ->
reserve -> settle with an uncertain-billing state, HOLD when credits are exhausted, the CA$100
cash ceiling still enforced, Anthropic unchanged, no live calls in tests.

No test here reaches a network: `OpenAIProvider._post` is replaced, and the network guard
refuses sockets.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s2_openai_provider.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import os

import network_guard
from r2_autonomy_harness import boot, run_tests

network_guard.install()
os.environ.setdefault("OPENAI_API_KEY", "k")      # presence only; `_post` is always faked

from brambleloop.gateway import openai_chat as O  # noqa: E402
from brambleloop.gateway import paid_calls, providers, routing  # noqa: E402
from brambleloop.gateway.anthropic import ProviderUnusable  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402

AGENT = "orchestrator"


class Wire:
    """Replaces `OpenAIProvider._post`; records every request that would have left."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.sent: list[tuple[dict, dict]] = []

    def __enter__(self):
        self.original = O.OpenAIProvider._post
        wire = self

        def fake(provider, body, headers, timeout):
            wire.sent.append((json.loads(body.decode()), dict(headers)))
            status, text = wire.answers.pop(0)
            return status, text

        O.OpenAIProvider._post = fake
        return self

    def __exit__(self, *exc):
        O.OpenAIProvider._post = self.original


def ok(text='{"names": ["Fern", "Moss", "Bramble"]}', model="gpt-4.1-mini-2025-04-14",
       prompt_tokens=120, completion_tokens=40, finish="stop"):
    return 200, json.dumps({
        "id": "chatcmpl-1", "model": model,
        "choices": [{"message": {"role": "assistant", "content": text},
                     "finish_reason": finish}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}})


def test_a_text_call_returns_the_gateways_response_with_provider_identity():
    p = O.OpenAIProvider(model="gpt-4.1-mini-2025-04-14")
    with Wire(ok(text="hello")) as wire:
        r = p.complete("be brief", "say hello", max_tokens=50)
    assert (r.text, r.provider, r.model) == ("hello", "openai", "gpt-4.1-mini-2025-04-14")
    assert (r.input_tokens, r.output_tokens, r.replayed) == (120, 40, False)
    body, headers = wire.sent[0]
    assert body["model"] == "gpt-4.1-mini-2025-04-14" and body["max_tokens"] == 50
    assert body["messages"] == [{"role": "system", "content": "be brief"},
                                {"role": "user", "content": "say hello"}]
    assert headers["Authorization"] == "Bearer k"
    # A reasoning snapshot takes `max_completion_tokens`.
    with Wire(ok(model="gpt-5-2025-08-07")) as wire:
        O.OpenAIProvider(model="gpt-5-2025-08-07").complete("", "x", max_tokens=9)
    assert wire.sent[0][0]["max_completion_tokens"] == 9 and "max_tokens" not in wire.sent[0][0]
    assert wire.sent[0][0]["messages"] == [{"role": "user", "content": "x"}]


def test_only_a_pinned_priced_snapshot_is_accepted():
    for alias in ("gpt-4.1", "gpt-4o", "gpt-5", "o3"):
        try:
            O.OpenAIProvider(model=alias)
            raise AssertionError(f"{alias!r} must be refused")
        except O.BudgetExceeded as exc:
            assert "pinned" in str(exc)
    p = O.OpenAIProvider(model="gpt-4.1-2025-04-14")
    assert p.cost_per_1k_input_cad > 0 and p.cost_per_1k_output_cad > 0
    assert O.estimate_cad("gpt-4.1-2025-04-14", input_tokens=1_000_000, output_tokens=0) > 2.0
    try:
        O.estimate_cad("gpt-4.1", input_tokens=10, output_tokens=10)
        raise AssertionError("an unpriced model must not be estimated")
    except O.BudgetExceeded:
        pass


def test_no_key_refuses_before_any_request():
    saved = os.environ.pop("OPENAI_API_KEY")
    try:
        with Wire() as wire:
            try:
                O.OpenAIProvider().complete("", "x", max_tokens=5)
                raise AssertionError("no key must refuse")
            except ProviderUnusable:
                pass
        assert wire.sent == []
    finally:
        os.environ["OPENAI_API_KEY"] = saved


def test_failures_are_classified_declined_or_uncertain():
    p = O.OpenAIProvider()
    cases = [((429, '{"error":{"type":"rate_limit_exceeded"}}'), TransientError, "declined"),
             ((503, "overloaded"), TransientError, "declined"),
             ((400, '{"error":{"message":"bad"}}'), ProviderUnusable, "declined"),
             ((-1, ""), O.OpenAITimeout, "uncertain"),
             ((0, ""), TransientError, "declined")]
    for answer, kind, billing in cases:
        with Wire(answer):
            try:
                p.complete("", "x", max_tokens=5)
                raise AssertionError(answer)
            except kind as exc:
                assert O._classify_failure(exc) == getattr(paid_calls, billing.upper()), answer
    # An answer whose usage is missing or not an integer arrived after transmission: its
    # cost is unknown, never coerced to zero.
    for usage in ({}, {"prompt_tokens": 1.5, "completion_tokens": 2},
                  {"prompt_tokens": True, "completion_tokens": 3},
                  {"prompt_tokens": 0, "completion_tokens": 0}):
        with Wire((200, json.dumps({"choices": [{"message": {"content": "x"}}],
                                    "usage": usage}))):
            try:
                p.complete("", "x", max_tokens=5)
                raise AssertionError(usage)
            except ValueError as exc:
                assert O._classify_failure(exc) == paid_calls.UNCERTAIN


def test_exhausted_credit_is_permanent_and_puts_the_provider_on_hold():
    from brambleloop.ops import funding
    from brambleloop.queue.durable import JobQueue

    db = boot("s2-hold-")
    q = JobQueue(db, lease_seconds=60)
    q.enqueue(AGENT, "ops.queue_check", {"x": 1}, idempotency_key="s2-hold")
    job = q.claim("W1")
    quota = (429, '{"error":{"code":"insufficient_quota","message":"You exceeded your '
                  'current quota"}}')
    with paid_calls.job_scope(db, job), Wire(quota) as wire:
        try:
            O.OpenAIProvider().complete("", "x", max_tokens=5)
            raise AssertionError("exhausted credit must refuse")
        except ProviderUnusable as exc:
            assert getattr(exc, "credit_exhausted", False)
    assert len(wire.sent) == 1
    hold = funding.blocked_provider(db, "openai")
    assert hold["blocked"] is True and "OpenAI" in hold["action"], hold
    # Its own row: the shared (Anthropic) balance action is not opened by it.
    assert funding.blocked(db)["blocked"] is False
    # On HOLD, nothing is sent, and a second exhaustion does not open a second action.
    with paid_calls.job_scope(db, job), Wire(ok()) as wire:
        try:
            O.OpenAIProvider().complete("", "y", max_tokens=5)
            raise AssertionError("a held provider must refuse")
        except ProviderUnusable as exc:
            assert "HOLD" in str(exc)
    assert wire.sent == []
    assert funding.note_provider(db, "openai", "insufficient_quota")["raised"] is False
    # The owner adds credit and the action is closed: calls go out again.
    assert funding.cleared_provider(db, "openai")["cleared"] is True
    with paid_calls.job_scope(db, job), Wire(ok(text="back")) as wire:
        assert O.OpenAIProvider().complete("", "z", max_tokens=5).text == "back"
    assert len(wire.sent) == 1


def test_vendor_routing_keeps_anthropic_the_default_and_pins_openai_per_tier():
    default = providers.for_task("topic_filing", env={})
    assert default.name == "anthropic"
    # One declared task per tier.
    by_tier = {}
    for key, task in routing.TASKS.items():
        by_tier.setdefault(routing.route(key)[1].key, key)
    assert set(by_tier) == set(routing.TIERS), by_tier
    for task in by_tier.values():
        p = providers.for_task(task, env={providers.VENDOR_VAR: "openai"})
        assert p.name == "openai"
        _task, tier = routing.route(task)
        assert p.model == routing.OPENAI_MODEL_BY_TIER[tier.key]
        assert p.model in O.PRICES_USD_PER_MTOK
    assert set(routing.OPENAI_MODEL_BY_TIER) == set(routing.TIERS)
    try:
        providers.for_task("not-a-declared-task", env={providers.VENDOR_VAR: "openai"})
        raise AssertionError("an undeclared task must be refused before any provider exists")
    except routing.TaskRefused:
        pass


def test_through_the_gateway_an_openai_call_reserves_settles_and_records_provenance():
    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot("s2-gw-")
    gw = ModelGateway([O.OpenAIProvider(model="gpt-4.1-mini-2025-04-14")],
                      registry=Registry(db))
    with Wire(ok()) as wire:
        data = gw.complete_json("concept.naming@1", agent=AGENT,
                                values={"category": "throw", "motifs": "fern",
                                        "season": "autumn"})
    assert len(wire.sent) == 1
    assert data["_meta"]["provider"] == "openai"
    assert data["_meta"]["model"] == "gpt-4.1-mini-2025-04-14"
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry)))
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "openai" and row.model == "gpt-4.1-mini-2025-04-14"
    p = O.OpenAIProvider(model="gpt-4.1-mini-2025-04-14")
    expected = 120 / 1000 * p.cost_per_1k_input_cad + 40 / 1000 * p.cost_per_1k_output_cad
    assert abs(float(row.amount_cad) - expected) < 1e-6, (row.amount_cad, expected)
    assert float(row.estimated_cad) >= float(row.amount_cad)


def test_the_monthly_ceiling_binds_an_openai_call_before_any_request():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import anthropic as gwmod
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot("s2-ceiling-")
    original = gwmod.monthly_ceiling_cad
    gwmod.monthly_ceiling_cad = lambda *a, **k: 0.0
    try:
        gw = ModelGateway([O.OpenAIProvider(model="gpt-4.1-2025-04-14")],
                          registry=Registry(db))
        with Wire(ok()) as wire:
            try:
                gw.complete_json("concept.naming@1", agent=AGENT,
                                 values={"category": "throw", "motifs": "fern",
                                         "season": "autumn"})
                raise AssertionError("a call over the ceiling must be refused")
            except Exception as exc:  # noqa: BLE001
                assert "ceiling" in str(exc).lower() or isinstance(exc, gwmod.BudgetExceeded), exc
        assert wire.sent == [], "the refusal came after a request left"
    finally:
        gwmod.monthly_ceiling_cad = original


def test_a_vision_call_is_gated_as_openai_vision_and_refused_without_activation():
    from brambleloop.gateway import paid_provider_gate as gate

    p = O.OpenAIProvider(model="gpt-4.1-mini-2025-04-14")
    with Wire(ok()) as wire:
        try:
            p.see("", "describe", ["https://example.test/a.jpg"], max_tokens=50)
            raise AssertionError("a paid vision call with no owner activation must refuse")
        except gate.PaidCallRefused:
            pass
    assert wire.sent == []
    for bad in ([], ["u"] * (O.MAX_IMAGES_PER_CALL + 1)):
        try:
            p.see("", "x", bad, max_tokens=5)
            raise AssertionError(bad)
        except ProviderUnusable:
            pass


def test_the_per_minute_rate_limit_refuses_before_sending_and_reads_the_ledger():
    from datetime import datetime, timezone

    from brambleloop.core.models import CostEntry

    saved = (O.RATE_LIMIT_PER_MINUTE, list(O._RECENT_SENDS))
    O._RECENT_SENDS.clear()
    O.RATE_LIMIT_PER_MINUTE = 2
    try:
        p = O.OpenAIProvider()
        with Wire(ok(), ok(), ok()) as wire:
            p.complete("", "a", max_tokens=5)
            p.complete("", "b", max_tokens=5)
            try:
                p.complete("", "c", max_tokens=5)
                raise AssertionError("the third request in a minute must be refused")
            except O.RateLimited as exc:
                assert O._classify_failure(exc) == paid_calls.DECLINED
        assert len(wire.sent) == 2
        # A new process (empty window) still counts the ledger's last minute.
        O._RECENT_SENDS.clear()
        db = boot("s2-rate-")
        with db.session() as s:
            for _ in range(2):
                s.add(CostEntry(agent=AGENT, kind="llm", amount_cad=0.01, provider="openai",
                                model=p.model, at=datetime.now(timezone.utc)))
        try:
            O._rate_check(db)
            raise AssertionError("the ledger's last minute must count")
        except O.RateLimited:
            pass
        # Another provider's rows do not count against this one.
        db2 = boot("s2-rate2-")
        with db2.session() as s:
            for _ in range(5):
                s.add(CostEntry(agent=AGENT, kind="llm", amount_cad=0.01, provider="anthropic",
                                model="m", at=datetime.now(timezone.utc)))
        O._RECENT_SENDS.clear()
        O._rate_check(db2)
    finally:
        O.RATE_LIMIT_PER_MINUTE = saved[0]
        O._RECENT_SENDS[:] = saved[1]


def test_an_owner_set_openai_provider_ceiling_binds_before_any_request():
    from brambleloop.agents.registry import Registry
    from brambleloop.finance import spend_policy
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot("s2-pceiling-")
    saved = dict(spend_policy.PROVIDER_CEILINGS_CAD)
    spend_policy.PROVIDER_CEILINGS_CAD["openai"] = 0.0
    try:
        gw = ModelGateway([O.OpenAIProvider(model="gpt-4.1-2025-04-14")],
                          registry=Registry(db))
        with Wire(ok()) as wire:
            try:
                gw.complete_json("concept.naming@1", agent=AGENT,
                                 values={"category": "throw", "motifs": "fern",
                                         "season": "autumn"})
                raise AssertionError("the openai provider ceiling must bind")
            except Exception as exc:  # noqa: BLE001
                assert "openai" in str(exc).lower() or "provider" in str(exc).lower(), exc
        assert wire.sent == []
    finally:
        spend_policy.PROVIDER_CEILINGS_CAD.clear()
        spend_policy.PROVIDER_CEILINGS_CAD.update(saved)


def test_the_ledger_splits_promo_credit_from_billable_cash_and_the_balance_is_unknown():
    from datetime import datetime, timezone

    from brambleloop.core.models import CostEntry
    from brambleloop.finance import credits

    db = boot("s2-split-")
    credits.ensure_table(db)
    credits.grant(db, provider="openai", kind="promotional_credit", amount=1.0,
                  currency="CAD", granted_on="2026-11-10", expires_on="2026-12-31",
                  source="owner_reported", evidence_ref="test")
    def at(day):
        return datetime(2026, 11, day, 12, tzinfo=timezone.utc)
    with db.session() as s:
        for day, cad, provider in ((5, 0.30, "openai"),       # before the grant: cash
                                   (11, 0.60, "openai"),      # credit
                                   (12, 0.70, "openai"),      # 0.40 credit + 0.30 cash
                                   (13, 0.20, "openai"),      # credit spent: cash
                                   (11, 9.00, "anthropic")):  # another provider: not here
            s.add(CostEntry(agent=AGENT, kind="llm", amount_cad=cad, provider=provider,
                            model="m", at=at(day)))
    out = credits.split(db, "openai", now=at(14))
    assert [c["source"] for c in out["calls"]] == ["billable_cash", "promo_credit", "mixed",
                                                   "billable_cash"], out["calls"]
    assert abs(out["promo_credit_cad"] - 1.0) < 1e-9 and abs(out["billable_cash_cad"] - 0.8) < 1e-9
    assert abs(out["ledger_cad"] - 1.8) < 1e-9 and out["credit_left_cad"] == 0.0
    assert out["basis"] == "ESTIMATED" and out["ceilings_changed"] == 0
    # An expired credit absorbs nothing after its expiry.
    db2 = boot("s2-split2-")
    credits.ensure_table(db2)
    credits.grant(db2, provider="openai", kind="promotional_credit", amount=5.0, currency="CAD",
                  granted_on="2026-11-01", expires_on="2026-11-03", source="owner_reported",
                  evidence_ref="test")
    with db2.session() as s:
        s.add(CostEntry(agent=AGENT, kind="llm", amount_cad=0.5, provider="openai", model="m",
                        at=at(4)))
    assert credits.split(db2, "openai", now=at(5))["billable_cash_cad"] == 0.5
    bal = O.balance(db)
    assert bal["balance"] == "UNKNOWN" and bal["ledger"]["billable_cash_cad"] == out["billable_cash_cad"]
    assert O.balance()["balance"] == "UNKNOWN"


if __name__ == "__main__":
    run_tests(globals())
