"""S2 fix (Main's verdict 6957356475): the ledger, the OpenAI text limits, and the LOWs.

MEDIUM ledger: `finance.credits.split` carries gross USD, the live reservations and the
UNCERTAIN calls held against the provider, and per-grant expiry; the Command Center owner
finance view shows every model provider's ledger.
MEDIUM limits: OpenAI starts with its own tighter-only month cap, and OpenAI text needs the
owner's `openai-text` activation (with its own ceilings) before any request leaves.
LOWs: HOLD is read outside a job scope; a successful call closes a stale HOLD; the answer must
come from the pinned snapshot and its response id is kept; -mini image tokens are reserved
high; the per-minute window is locked; the provider HOLD action's cost is UNKNOWN, not CA$25.

No test reaches a network: `OpenAIProvider._post` is replaced; the network guard refuses sockets.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s2_fix_ledger.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import os
import threading
from datetime import datetime, timedelta, timezone

import network_guard
from r2_autonomy_harness import boot, run_tests

network_guard.install()
os.environ.setdefault("OPENAI_API_KEY", "k")

from sqlalchemy import select  # noqa: E402

from brambleloop.gateway import openai_chat as O, paid_calls, providers  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from test_s2_openai_provider import AGENT, Wire, activate_text, activated, ok  # noqa: E402

MINI = "gpt-4.1-mini-2025-04-14"


def test_the_ledger_has_gross_usd_held_uncertain_and_per_grant_expiry():
    from brambleloop.core.models import CostEntry
    from brambleloop.finance import credits
    from brambleloop.gateway.routing import USD_PER_CAD

    db = boot("s2fix-ledger-")
    now = datetime.now(timezone.utc)
    today = now.date()
    credits.grant(db, provider="openai", kind="promotional_credit", amount=1.0,
                  currency="CAD", granted_on=(today - timedelta(days=10)).isoformat(),
                  expires_on=(today - timedelta(days=1)).isoformat(), evidence_ref="ev:a")
    credits.grant(db, provider="openai", kind="promotional_credit", amount=2.0,
                  currency="CAD", granted_on=(today - timedelta(days=10)).isoformat(),
                  evidence_ref="ev:b")
    with db.session() as s:
        s.add(CostEntry(agent=AGENT, kind="llm", amount_cad=0.5, provider="openai",
                        model=MINI, at=now - timedelta(days=5)))
        s.add(paid_calls.PaidCallRecord(key="k-unc", effect="openai.chat", fingerprint="f",
                                        outcome=paid_calls.UNCERTAIN, estimate_cad=0.07,
                                        provider="openai", model=MINI))
    held = providers.check_budget(db, model=MINI, input_tokens=400, max_tokens=200,
                                  agent=AGENT, purpose="s2fix.ledger")
    got = credits.split(db, "openai", now=now)
    assert abs(got["gross_usd"] - round(0.5 * USD_PER_CAD, 6)) < 1e-6, got
    assert got["calls"][0]["usd"] == round(0.5 * USD_PER_CAD, 6)
    assert "DERIVED" in got["usd_basis"]
    assert got["reservations"] == 1 and abs(got["reserved_cad"] - held["estimate_cad"]) < 1e-6
    assert got["uncertain_calls"] == 1 and got["uncertain_cad"] == 0.07
    assert abs(got["exposure_cad"] - (got["billable_cash_cad"] + got["reserved_cad"]
                                      + got["uncertain_cad"])) < 1e-6
    grants = {g["expires_on"]: g for g in got["grants"]}
    expired = grants[(today - timedelta(days=1)).isoformat()]
    assert expired["expired"] is True and expired["estimated_left_cad"] == 0.0
    open_ = grants[None]
    assert open_["expiry_basis"] == "UNKNOWN" and open_["expired"] is False
    # Released reservations no longer count as held.
    providers.release_reservation(db, held["reservation_id"], actual_cad=0.0)
    assert credits.split(db, "openai", now=now)["reserved_cad"] == 0.0


def test_the_command_center_owner_finance_view_shows_each_model_provider():
    from brambleloop.app import main
    from brambleloop.finance import credits

    db = boot("s2fix-cc-")
    view = credits.model_providers(db)
    assert {"anthropic", "openai"} <= set(view["providers"])
    assert view["providers"]["openai"]["balance"] == "UNKNOWN"
    src = open(main.__file__, encoding="utf-8").read()
    owner_view = src[src.index("def _finance_owner_view"):]
    owner_view = owner_view[:owner_view.index("\n@app.")]
    assert "credits.model_providers(db" in owner_view
    assert '"model_providers": guard(model_providers)' in owner_view


def test_openai_starts_with_its_own_tighter_month_cap():
    from brambleloop.core.models import CostEntry
    from brambleloop.finance import spend_policy
    from brambleloop.gateway.anthropic import BudgetExceeded

    cap = spend_policy.PROVIDER_CEILINGS_CAD["openai"]
    assert 0 < cap < spend_policy.CEILING_CAD
    assert cap == round(spend_policy.CEILING_CAD * spend_policy.OPENAI_DEFAULT_CEILING_SHARE, 2)
    db = boot("s2fix-cap-")
    with db.session() as s:
        # Spent by another agent, so this agent's own daily permission is not what binds.
        s.add(CostEntry(agent="intel", kind="llm", amount_cad=cap - 0.0001, provider="openai",
                        model=MINI, at=datetime.now(timezone.utc)))
    try:
        providers.check_budget(db, model=MINI, input_tokens=4000, max_tokens=2000,
                               agent=AGENT, purpose="s2fix.cap")
        raise AssertionError("OpenAI at its own cap must be refused, below the company month")
    except BudgetExceeded as exc:
        assert "provider" in str(exc)
    # Anthropic is not held by OpenAI's cap.
    from brambleloop.gateway import routing

    providers.check_budget(db, model=routing.route("topic_filing")[1].model, input_tokens=400,
                           max_tokens=200, agent=AGENT, purpose="s2fix.cap")


def test_openai_text_needs_the_owners_activation_before_any_request():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway.model_gateway import ModelGateway

    db = boot("s2fix-act-")
    gw = ModelGateway([O.OpenAIProvider(model=MINI)], registry=Registry(db))
    with Wire(ok()) as wire:
        try:
            gw.complete_json("concept.naming@1", agent=AGENT,
                             values={"category": "throw", "motifs": "fern", "season": "autumn"})
            raise AssertionError("OpenAI text without an owner activation must be refused")
        except Exception as exc:  # noqa: BLE001 - the gateway may wrap the refusal
            assert "not_activated_by_owner" in repr(exc) or "openai-text" in repr(exc), exc
    assert wire.sent == []
    assert G.scopes_for(G.OPENAI_TEXT) == (G.TEXT, G.PROBE)
    # Activated (a fresh database: the refused attempts above are recorded as failures).
    db = boot("s2fix-act2-")
    activate_text(db)
    gw = ModelGateway([O.OpenAIProvider(model=MINI)], registry=Registry(db))
    with Wire(ok()) as wire:
        data = gw.complete_json("concept.naming@1", agent=AGENT,
                                values={"category": "throw", "motifs": "fern", "season": "autumn"})
    assert len(wire.sent) == 1 and data["_meta"]["provider"] == "openai"
    assert data["_meta"]["response_id"] == "chatcmpl-1"


def test_hold_is_read_outside_a_job_scope_and_a_success_clears_a_stale_hold():
    from brambleloop.ops import funding

    db = boot("s2fix-hold-")
    activate_text(db)
    funding.note_provider(db, "openai", "insufficient_quota: spent")
    assert funding.blocked_provider(db, "openai")["blocked"] is True
    p = O.OpenAIProvider(model=MINI)
    # No job scope: the reservation's database is where the HOLD is read.
    providers.check_budget(db, model=MINI, input_tokens=1, max_tokens=5, agent=AGENT,
                           purpose="s2fix.hold")
    with Wire(ok()) as wire:
        try:
            p.complete("", "x", max_tokens=5)
            raise AssertionError("HOLD must refuse outside a job scope too")
        except O.ProviderUnusable as exc:
            assert "HOLD" in str(exc)
    assert wire.sent == []
    G.take_budget()
    # A HOLD opened while a call is in flight is closed by that call's success.
    with activated(db=db, activate=False):
        real = O.OpenAIProvider._send

        def opens_then_succeeds(provider, payload, key, *, timeout=None):
            funding.note_provider(db, "openai", "insufficient_quota: raced")
            return real(provider, payload, key, timeout=timeout)

        funding.cleared_provider(db, "openai")
        O.OpenAIProvider._send = opens_then_succeeds
        try:
            with Wire(ok()):
                p.complete("", "y", max_tokens=5)
        finally:
            O.OpenAIProvider._send = real
    assert funding.blocked_provider(db, "openai")["blocked"] is False


def test_an_answer_from_another_model_is_refused_and_counted_uncertain():
    with activated():
        with Wire(ok(model="gpt-4.1-2025-04-14")) as wire:
            try:
                O.OpenAIProvider(model=MINI).complete("", "x", max_tokens=5)
                raise AssertionError("an answer from another snapshot must not be used")
            except ValueError as exc:
                assert O._classify_failure(exc) == paid_calls.UNCERTAIN
        assert len(wire.sent) == 1
    with activated(), Wire(ok()):
        r = O.OpenAIProvider(model=MINI).complete("", "y", max_tokens=5)
    assert r.response_id == "chatcmpl-1" and r.model == MINI


def test_mini_image_tokens_are_reserved_high_and_the_rate_window_is_locked():
    assert O.image_tokens(MINI) >= 2500 > O.image_tokens("gpt-4.1-2025-04-14") - 1000
    import time

    class SlowList(list):
        """Yields the thread between the count and the append, so an unlocked check-then-
        append lets every thread through (20 of 20, measured); the lock keeps it to 5."""

        def append(self, item):
            time.sleep(0.002)
            return super().append(item)

    saved = (O.RATE_LIMIT_PER_MINUTE, O._RECENT_SENDS)
    O._RECENT_SENDS = SlowList()
    O.RATE_LIMIT_PER_MINUTE = 5
    allowed, refused = [], []
    barrier = threading.Barrier(20)

    def one():
        barrier.wait()
        try:
            O._rate_check(None)
            allowed.append(1)
        except O.RateLimited:
            refused.append(1)
    try:
        threads = [threading.Thread(target=one) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(allowed) == 5 and len(refused) == 15, (len(allowed), len(refused))
    finally:
        O.RATE_LIMIT_PER_MINUTE = saved[0]
        O._RECENT_SENDS = saved[1]


def test_the_provider_hold_action_cost_is_unknown_not_a_placeholder():
    from brambleloop.core.models import OwnerAction
    from brambleloop.ops import funding

    db = boot("s2fix-cost-")
    funding.note_provider(db, "openai", "insufficient_quota: spent")
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == funding.provider_key("openai")))
        assert row.max_cost_basis == "UNKNOWN" and row.max_cost_cad == 0.0


if __name__ == "__main__":
    run_tests(globals())
