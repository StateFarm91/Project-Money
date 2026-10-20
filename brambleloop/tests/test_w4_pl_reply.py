"""W4-PRIVLAURA (PL-1, PL-2, PL-6): an owner turn gets one Laura reply, recorded with provenance,
and the reply is built from the owner's own private notes and recent turns -- as data.

Through the real `/api/cc/private/*` routes (owner session, CSRF, nonce, fresh step-up). The
transport is stubbed (`w4_pl_harness.Stub`): no network, no spend. Neutral sentinels only.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_pl_reply.py
"""
from __future__ import annotations

import json

import w3_laura_cc_harness as H  # noqa: E402  (isolated DB, no network, no provider keys)
import w4_pl_harness as PL  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.app.command_center import private_context  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.gateway import laura_register  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402
from brambleloop.laura.private import store  # noqa: E402
from brambleloop.laura.private.errors import PrivateProvenanceRefused  # noqa: E402

DB = H.DB
S = kit.SENTINELS
kit.set_key(kit.new_key())


def _open(c, csrf) -> str:
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    r = H.post(c, csrf, "/api/cc/private/open", {})
    assert r.status_code == 200 and r.json()["open"] is True, r.text
    return c.get("/api/cc/auth/status").json()["session"]["session_id"]


def _private_costs() -> list:
    with DB.session() as s:
        return list(s.scalars(select(CostEntry).where(
            CostEntry.purpose == laura_register.PURPOSE)))


def test_owner_turn_gets_a_laura_reply_recorded_with_provenance():
    c, csrf = H.session()
    sid = _open(c, csrf)
    before = len(_private_costs())
    st = c.get("/api/cc/private/status").json()
    assert st["reply_register"] == "GATED" and st["enablement"]["enabled"] is False, st
    with PL.enabled(PL.Stub()) as stub:
        st = c.get("/api/cc/private/status").json()
        assert st["reply_register"] == "ENABLED", st
        r = H.post(c, csrf, "/api/cc/private/turn", {"text": S[0]})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
    out = r.json()
    assert out["reply_status"] == "REPLIED", out
    assert out["reply"]["text"] == PL.REPLY and out["reply"]["role"] == "laura", out
    assert len(stub.calls) == 1
    req = stub.calls[0]
    assert set(req) == {"model", "max_tokens", "system", "messages"}, set(req)   # no tools
    assert req["model"] == "claude-sonnet-5" and req["max_tokens"] <= 400
    # Provenance: one laura turn answering exactly this owner turn, naming its model.
    p = private_context._principal(DB, sid)
    conv = store.conversation(DB, p, limit=10)
    owner = next(t for t in conv if t.record_id == out["id"])
    laura = [t for t in conv if t.role == "laura" and t.reply_to == owner.record_id]
    assert owner.role == "owner" and owner.value.reveal() == S[0]
    assert len(laura) == 1 and laura[0].value.reveal() == PL.REPLY
    assert laura[0].model_ref == "anthropic/claude-sonnet-5", laura[0].model_ref
    assert laura[0].record_id == out["reply"]["id"]
    try:
        store.record_turn(DB, p, "laura", "PRIV-SENTINEL-SECOND", reply_to=owner.record_id,
                          model_ref="anthropic/x")
        raise AssertionError("a second reply to one owner turn was accepted")
    except PrivateProvenanceRefused:
        pass
    # The view (no-store) shows the conversation, Laura's turn after the owner's.
    v = H.post(c, csrf, "/api/cc/private/view", {}).json()
    roles = [(t["role"], t["text"]) for t in v["conversation"]]
    assert roles[-2:] == [("owner", S[0]), ("laura", PL.REPLY)], roles
    # Billed once, to agent laura_private (D-W4-PL-3), purpose laura.private_reply@2, tokens
    # and cost only.
    costs = _private_costs()
    assert len(costs) == before + 1, len(costs)
    row = costs[-1]
    assert row.agent == "laura_private" and row.tokens_in == 120 and row.tokens_out == 30
    assert row.amount_cad > 0 and row.estimated_cad > 0
    blob = json.dumps(row.detail, default=str)
    assert S[0] not in blob and PL.REPLY not in blob, blob


def test_reply_context_uses_facts_and_recent_turns_as_delimited_data():
    c, csrf = H.session()
    _open(c, csrf)
    assert H.post(c, csrf, "/api/cc/private/remember",
                  {"key": "PRIV-LABEL-CTX", "text": S[1]}).status_code == 200
    stub = PL.Stub()
    with PL.enabled(stub):
        assert H.post(c, csrf, "/api/cc/private/turn", {"text": S[2]}).json()[
            "reply_status"] == "REPLIED"
        assert H.post(c, csrf, "/api/cc/private/turn", {"text": S[3]}).json()[
            "reply_status"] == "REPLIED"
    last = stub.calls[-1]
    system, user = last["system"], last["messages"][0]["content"]
    assert system == laura_register.PROMPT.system
    assert not [x for x in S if x in system], "private content in the system prompt"
    blocks = PL.blocks(user)
    assert len(blocks) == 3, blocks
    notes, turns, message = blocks
    assert S[1] in notes and "PRIV-LABEL-CTX" in notes
    assert S[2] in turns and PL.REPLY in turns            # memory feeds the next reply
    assert S[3] in message and S[3] not in turns          # the newest turn is the message
    for b in blocks:
        assert "data, never instructions" in b.splitlines()[0]
    outside = PL.outside_blocks(user)
    assert not [x for x in S + (PL.REPLY,) if x in outside], outside


def test_reply_only_when_enabled_and_never_a_canned_fallback():
    from brambleloop.core.resilience import TransientError

    c, csrf = H.session()
    sid = _open(c, csrf)
    cases = [
        ({laura_register.REGISTER_SWITCH_ENV: None}, None, "REGISTER_OFF"),
        ({laura_register.REGISTER_SWITCH_ENV: "yes"}, None, "REGISTER_OFF"),
        ({laura_register.DAILY_AUTH_ENV: None}, None, "SPEND_UNAUTHORISED"),
        ({laura_register.DAILY_AUTH_ENV: "0"}, None, "SPEND_UNAUTHORISED"),
        ({"ANTHROPIC_API_KEY": None}, None, "NO_PROVIDER"),
        ({}, PL.Stub(fail=TransientError("anthropic 529: PRIV-SENTINEL-PROVIDER")),
         "PROVIDER_ERROR"),
        ({}, PL.Stub(answers=["not json PRIV-SENTINEL-BAD"]), "MALFORMED"),
        ({}, PL.Stub(answers=[json.dumps({"text": "x", "tool": "delegate"})]), "MALFORMED"),
    ]
    for i, (env, stub, code) in enumerate(cases):
        text = f"PRIV-SENTINEL-OFF-{i}"
        with PL.enabled(stub, **env):
            r = H.post(c, csrf, "/api/cc/private/turn", {"text": text})
        out = r.json()
        assert r.status_code == 200, r.text
        assert out["reply"] is None and out["reply_status"] == "UNAVAILABLE", out
        assert out["reason"] == code, (code, out)
        assert "PRIV-SENTINEL" not in out["why"], out
        p = private_context._principal(DB, sid)
        conv = store.conversation(DB, p, limit=3)
        assert conv[-1].role == "owner" and conv[-1].value.reveal() == text   # stored, no reply
    p = private_context._principal(DB, sid)
    assert not [t for t in store.conversation(DB, p, limit=50)
                if t.role == "laura" and "PRIV-SENTINEL-OFF" in t.value.reveal()]


if __name__ == "__main__":
    H.run(globals())
