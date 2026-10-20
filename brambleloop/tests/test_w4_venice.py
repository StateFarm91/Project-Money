"""W4-VENICE: Private Laura on Venice AI (owner ruling D-W4-PL-VENICE; spec/13 ADD-PLV-01..08).

Venice is a TRANSPORT on the one existing Private Laura reply path. These tests drive that path
over a MOCKED Venice transport (`VeniceProvider._post` replaced; the harness also refuses every
socket), so there is no network and no spend. The Anthropic transport is replaced by one that
fails the test if it is ever used: a Venice failure must never fall back to another provider.

Covered: switch OFF by default; auth header shape; pinned model and request shape (our pinned
system prompt only, Venice's own system prompt off, web search off, reasoning off, output cap);
the atomic `laura_private` reservation exists BEFORE the request; budget refusals make no
request; classified failures (one attempt, honest reason, no fake reply, correct billing);
no private text in billing, logs, audit, SQL parameters, business tables, the continuity
export or the paid-call journal; what Venice receives is only the pinned prompt plus the
private turn and its minimal private context; owner-only access; persistence across restart
in the encrypted store; credential health for Venice (owner-enabled only); price table and the
CA$0.50/day arithmetic used in VENICE.md.

Neutral sentinels only (PRIV-SENTINEL-...). Stand-in key strings only.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_venice.py
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

import w3_laura_cc_harness as H  # noqa: E402  (isolated DB, sockets refused, no provider keys)
import w4_pl_harness as PL  # noqa: E402
from w3_laura_memory_harness import fresh_db, raw_storage_bytes, reopen  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import private_context  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, SpendReservation  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import credentials as CR  # noqa: E402
from brambleloop.gateway import laura_register as LR  # noqa: E402
from brambleloop.gateway import paid_calls  # noqa: E402
from brambleloop.gateway import venice as V  # noqa: E402
from brambleloop.laura.core import identity  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = H.DB
H.seed_company()
kit.set_key(kit.new_key())
VKEY = "venice-STANDIN-" + uuid.uuid4().hex          # a stand-in, hunted for everywhere
VENICE_ON = {"BRAMBLELOOP_PRIVATE_PROVIDER": "venice", "VENICE_API_KEY": VKEY}
OWNER = tuple(f"PRIV-SENTINEL-VEN-{i:04d}" for i in range(1, 9))
REPLIES = tuple(f"PRIV-SENTINEL-VENREPLY-{i:04d}" for i in range(1, 6))
BODY = "PRIV-SENTINEL-VEN-PROVIDERBODY"
ALL = OWNER + REPLIES + (BODY, VKEY)


def _leaks(blob: str) -> list[str]:
    return [x for x in ALL if x in blob]


def _ok(text: str, *, tokens=(900, 60), cost_usd=None, finish="stop") -> tuple[int, str]:
    body = {"id": "x", "object": "chat.completion", "model": V.MODEL,
            "choices": [{"index": 0, "finish_reason": finish,
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1],
                      "total_tokens": sum(tokens)}}
    if cost_usd is not None:
        body["cost"] = {"usd": cost_usd, "diem": 0}
    return 200, json.dumps(body)


class Venice:
    """The mocked transport: records each request; answers from a script (then a reply)."""

    def __init__(self, answers=None, on_call=None):
        self.calls: list[dict] = []
        self.answers = list(answers or [])
        self.on_call = on_call

    def __call__(self, provider, url, body, headers, timeout):
        self.calls.append({"url": url, "body": json.loads(body.decode()),
                           "headers": dict(headers), "timeout": timeout})
        if self.on_call is not None:
            self.on_call()
        if self.answers:
            return self.answers.pop(0)
        return _ok(json.dumps({"text": REPLIES[0]}))


@contextlib.contextmanager
def venice(mock: Venice | None, **env):
    """Owner switches on, Venice selected with a stand-in key, the Venice transport mocked and
    the Anthropic transport set to FAIL the test if anything reaches it."""
    orig = V.VeniceProvider._post
    if mock is not None:
        V.VeniceProvider._post = lambda self, url, body, headers, timeout: mock(
            self, url, body, headers, timeout)
    else:
        def _refuse(self, *a, **k):
            raise AssertionError("a Venice request was made where none may be")
        V.VeniceProvider._post = _refuse
    try:
        with PL.enabled(None, **{**VENICE_ON, **env}):   # Anthropic `_send` refuses
            yield mock
    finally:
        V.VeniceProvider._post = orig


def _db():
    db = fresh_db()
    Registry(db).seed_defaults()
    return db


USER = LR.render_user(facts=[("PRIV-LABEL-VEN", OWNER[0])], turns=[("owner", OWNER[1])],
                      message=OWNER[2])


def _call(db, **kw):
    try:
        return LR.reply(db, system=LR.PROMPT.system, user=USER, **kw)
    except LR.ReplyUnavailable as exc:
        return exc.code


def _rows(db, model):
    with db.session() as s:
        return list(s.scalars(select(model)))


# ---------------------------------------------------------------- switch, shape, pin

def test_the_switch_is_off_by_default_and_nothing_is_sent():
    assert V.selected({}) == "" and V.selected({"BRAMBLELOOP_PRIVATE_PROVIDER": "Venice"}) \
        == "venice" and V.selected({"BRAMBLELOOP_PRIVATE_PROVIDER": "openai"}) == ""
    e = LR.enablement({LR.REGISTER_SWITCH_ENV: "1", LR.DAILY_AUTH_ENV: "0.5",
                       LR.PRIVATE_KEY_ENV: "k", "VENICE_API_KEY": VKEY,
                       "ANTHROPIC_API_KEY": "a"})
    assert e["provider"] is None and e["enabled"] is False, e      # a key alone selects nothing
    assert VKEY not in json.dumps(e)
    db = _db()
    mock = Venice()
    with venice(mock, BRAMBLELOOP_PRIVATE_PROVIDER=None):   # every other switch on
        assert _call(db) == "PROVIDER_NOT_SELECTED"
    assert mock.calls == [] and _rows(db, SpendReservation) == [] and \
        _rows(db, CostEntry) == []
    # Selected but no key: no request either.
    with venice(Venice(), VENICE_API_KEY=None) as m:
        assert _call(db) == "NO_PROVIDER" and m.calls == []
    # The status prerequisite is unmet until the owner selects Venice with a key.
    met = {p["id"]: p["met"] for p in private_context.prerequisites(db, boot={}, env={})}
    assert met["private_provider_venice"] is False
    met = {p["id"]: p["met"] for p in private_context.prerequisites(db, boot={},
                                                                     env=VENICE_ON)}
    assert met["private_provider_venice"] is True
    assert not [m for m in V.PRIVATE_MODELS if m.startswith(("claude", "openai", "gemini"))]


def test_auth_header_shape_pinned_model_and_request_body():
    db = _db()
    mock = Venice()
    with venice(mock):
        out = LR.reply(db, system=LR.PROMPT.system, user=USER)
    assert out["text"] == REPLIES[0] and out["model_ref"] == f"venice/{V.MODEL}", out
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call["url"] == "https://api.venice.ai/api/v1/chat/completions" == V.CHAT_URL
    assert call["headers"]["Authorization"] == f"Bearer {VKEY}"           # exact shape
    assert call["headers"]["Content-Type"] == "application/json"
    b = call["body"]
    assert V.MODEL == "zai-org-glm-5-2" and b["model"] == V.MODEL         # pinned
    assert b["model"] in V.PRIVATE_MODELS                                  # zero-retention class
    assert b["messages"] == [{"role": "system", "content": LR.PROMPT.system},
                             {"role": "user", "content": USER}]            # nothing else
    vp = b["venice_parameters"]
    assert vp["include_venice_system_prompt"] is False                     # ours only
    assert vp["enable_web_search"] == "off" and vp["enable_web_scraping"] is False
    assert vp["disable_thinking"] is True and b["reasoning_effort"] == "none"
    assert b["max_completion_tokens"] == LR.PROMPT.max_output_tokens == 400
    assert "tools" not in b and "character_slug" not in vp and b["stream"] is False
    # The pinned prompt is the canonical identity with the truthful-AI clauses (unchanged).
    p = LR.PROMPT.system
    assert LR.PURPOSE == "laura.private_reply@2"
    assert identity.public_profile()["visual_identity_id"] == "laura-r2-a42aeac7" and \
        "laura-r2-a42aeac7" in p
    for clause in ("You are an AI. Never claim or imply that you are human",
                   "never claim a body, a physical action or a place",
                   "the provider's usage policies are the outer limit and you never work "
                   "around them"):
        assert clause in p, clause
    # An anonymized (third-party-visible) model cannot be constructed.
    try:
        V.VeniceProvider(model="claude-opus-5-5")
    except gw.BudgetExceeded:
        pass
    else:
        raise AssertionError("an anonymized model was accepted")


# Verified ANONYMIZED by Venice's own GET /api/v1/models (model_spec.privacy), 2026-10-20,
# including the uncensored and roleplay ones: the upstream provider sees the prompt.
ANONYMIZED = ("qwen-3-6-plus", "aion-labs-aion-3-0", "aion-labs-aion-3-0-mini",
              "aion-labs-aion-3-5", "aion-labs-aion-3-5-mini",
              "abliteration-abliterated-model-large-v2", "claude-opus-5-5", "openai-gpt-55",
              "gemini-3-1-pro-preview")


def test_anonymized_models_are_refused_and_the_guardrails_reach_venice():
    for m in ANONYMIZED:
        try:
            V.VeniceProvider(model=m)
        except gw.BudgetExceeded:
            continue
        raise AssertionError(f"anonymized model {m} was accepted")
    assert not set(ANONYMIZED) & set(V.PRIVATE_MODELS)
    # The pinned default is unchanged until the owner approves a switch.
    assert V.MODEL == "zai-org-glm-5-2" and V.PRIVATE_MODELS == frozenset({V.MODEL})
    # @2 states the guardrails explicitly and keeps every @1 sentence verbatim; @1 stays.
    p = LR.PROMPT.system
    for clause in ("adults only", "minor", "fictional AI persona",
                   "never portray, impersonate or use the name, likeness or voice of any real "
                   "person", "nothing illegal"):
        assert clause in p, clause
    v1 = LR.LAURA_PRIVATE_REPLY_V1.system
    assert p.replace(LR.GUARDRAILS, "") == v1 and LR.PURPOSE == "laura.private_reply@2"
    assert "Nothing you write is sexually explicit" in p          # D-W4-PL-2 untouched
    mock = Venice()
    with venice(mock):
        LR.reply(_db(), system=LR.PROMPT.system, user=USER)
    assert mock.calls[0]["body"]["messages"][0]["content"] == p and LR.GUARDRAILS in p


# ---------------------------------------------------------------- money

def test_the_reservation_exists_before_the_request_and_billing_is_tokens_and_cost_only():
    db = _db()
    seen: list = []

    def during():
        open_ = [r for r in _rows(db, SpendReservation)
                 if r.agent == "laura_private" and r.released_at is None]
        seen.append([(r.amount_cad, r.purpose, r.model) for r in open_])
    mock = Venice(answers=[_ok(json.dumps({"text": REPLIES[1]}), tokens=(1500, 150))],
                  on_call=during)
    expect = V.estimate_for(LR.PROMPT.system, USER, LR.PROMPT.max_output_tokens)
    with venice(mock):
        out = LR.reply(db, system=LR.PROMPT.system, user=USER)
    assert seen == [[(expect, LR.PURPOSE, V.MODEL)]], seen          # reserved BEFORE the call
    (cost,) = [c for c in _rows(db, CostEntry) if c.agent == "laura_private"]
    pin, pout = V.PRICES_USD_PER_MTOK[V.MODEL]
    want = (1500 / 1000 * round(pin / 1000 * gw.USD_TO_CAD, 8)
            + 150 / 1000 * round(pout / 1000 * gw.USD_TO_CAD, 8))
    assert abs(cost.amount_cad - want) < 1e-9 and abs(out["cost_cad"] - round(want, 6)) < 1e-6
    assert (cost.provider, cost.model, cost.purpose) == ("venice", V.MODEL, LR.PURPOSE)
    assert (cost.tokens_in, cost.tokens_out) == (1500, 150)
    assert cost.estimated_cad == expect
    (res,) = _rows(db, SpendReservation)
    assert res.released_at is not None and abs(res.actual_cad - cost.amount_cad) < 1e-7
    assert not _leaks(json.dumps([cost.detail, res.detail], default=str))
    # Venice's own reported charge is a floor for the bill (never below what it says).
    db2 = _db()
    with venice(Venice(answers=[_ok(json.dumps({"text": REPLIES[1]}), tokens=(10, 10),
                                    cost_usd=0.01)])):
        LR.reply(db2, system=LR.PROMPT.system, user=USER)
    (c2,) = _rows(db2, CostEntry)
    assert abs(c2.amount_cad - round(0.01 * gw.USD_TO_CAD, 6)) < 1e-9, c2.amount_cad


def test_budget_refusals_make_no_request():
    db = _db()
    with venice(Venice(), **{LR.DAILY_AUTH_ENV: None}) as m:          # no owner figure
        assert _call(db) == "SPEND_UNAUTHORISED" and m.calls == []
    with venice(Venice(), **{LR.DAILY_AUTH_ENV: "0.000001"}) as m:    # figure below one call
        assert _call(db) == "SPEND_CEILING" and m.calls == []
    with db.session() as s:                                          # the day already spent
        s.add(CostEntry(agent="laura_private", amount_cad=0.5, kind="llm",
                        purpose=LR.PURPOSE, provider="venice", model=V.MODEL))
    with venice(Venice(), **{LR.DAILY_AUTH_ENV: "0.50"}) as m:
        assert _call(db) == "SPEND_CEILING" and m.calls == []
    refusals = [a for a in _rows(db, AuditLog) if a.action == "spend.refused"]
    assert len(refusals) == 3, len(refusals)
    assert not _leaks(json.dumps([r.detail for r in refusals], default=str))
    assert all((r.detail or {}).get("provider", "venice") == "venice" for r in refusals), \
        [r.detail for r in refusals]
    assert [r for r in _rows(db, SpendReservation) if r.released_at is None] == []


# ---------------------------------------------------------------- failures

FAILURES = [
    ((401, json.dumps({"error": f"AUTHENTICATION_FAILED {BODY}"})), "PROVIDER_AUTH", False),
    ((402, json.dumps({"error": f"INSUFFICIENT_BALANCE {BODY}"})), "PROVIDER_CREDIT", False),
    ((403, f"API_ACCESS_DISABLED {BODY}"), "PROVIDER_AUTH", False),
    ((422, f"CONTENT_POLICY_VIOLATION {BODY}"), "PROVIDER_POLICY", False),
    ((429, f"RATE_LIMIT_EXCEEDED {BODY}"), "PROVIDER_RATE_LIMITED", False),
    ((500, f"INFERENCE_FAILED {BODY}"), "PROVIDER_UNREACHABLE", False),
    ((503, f"MODEL_AT_CAPACITY {BODY}"), "PROVIDER_UNREACHABLE", False),
    ((504, f"REQUEST_TIMEOUT {BODY}"), "PROVIDER_UNREACHABLE", True),    # billed UNKNOWN
    ((0, ""), "PROVIDER_UNREACHABLE", False),                           # unreachable
    ((-1, ""), "PROVIDER_UNREACHABLE", True),                           # read timeout
    ((400, f"INVALID_REQUEST {BODY}"), "PROVIDER_ERROR", False),
    ((404, f"MODEL_NOT_FOUND {BODY}"), "PROVIDER_ERROR", False),
]


def test_classified_failures_are_honest_single_attempts_with_no_fallback():
    assert len(FAILURES) == 12
    for answer, code, counted_at_estimate in FAILURES:
        db = _db()
        mock = Venice(answers=[answer])
        with venice(mock):                       # Anthropic `_send` fails the test if used
            got = _call(db)
        assert got == code, (answer[0], got, code)
        assert len(mock.calls) == 1, (answer[0], "retried")              # one attempt
        reason = LR.REASONS[code]
        assert BODY not in reason and VKEY not in reason
        if code in ("PROVIDER_UNREACHABLE", "PROVIDER_AUTH", "PROVIDER_CREDIT",
                    "PROVIDER_RATE_LIMITED"):
            assert reason.startswith("I can't reach my private model right now"), reason
        costs = _rows(db, CostEntry)
        if counted_at_estimate:
            (c,) = costs                         # unknown whether it billed: the estimate
            assert c.amount_cad == V.estimate_for(LR.PROMPT.system, USER, 400) and \
                c.tokens_in == c.tokens_out == 0
        else:
            assert costs == [], (answer[0], [c.amount_cad for c in costs])  # declined: no bill
        assert [r for r in _rows(db, SpendReservation) if r.released_at is None] == []
        attempts = [a for a in _rows(db, AuditLog) if a.action == "model.attempt"]
        assert [a.artifact for a in attempts] == [f"venice:{V.MODEL}"], attempts
        assert not _leaks(json.dumps([a.detail for a in _rows(db, AuditLog)], default=str))
        assert not _leaks(json.dumps([c.detail for c in costs], default=str))
    # Malformed 200 and a truncated answer: billed (the provider answered), no reply text.
    for answer in (_ok("not json"), _ok('{"text": "cut', finish="length"),
                   _ok(json.dumps({"text": ""}))):
        db = _db()
        with venice(Venice(answers=[answer])):
            assert _call(db) == "MALFORMED"
        assert len(_rows(db, CostEntry)) == 1
    # A provider marked DOWN is not called at all (no stronger fallback, no other provider).
    db = _db()
    for _ in range(6):
        with venice(Venice(answers=[(503, "MODEL_OFFLINE")])):
            _call(db)
    with venice(Venice()) as m:
        got = _call(db)
    assert got in ("PROVIDER_DOWN", "PROVIDER_UNREACHABLE"), got
    if got == "PROVIDER_DOWN":
        assert m.calls == []


def test_the_private_context_shows_unavailable_never_a_fake_reply():
    c, csrf = H.session()
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
    with venice(Venice(answers=[(0, "")])):
        r = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[7]}).json()
    assert r["reply"] is None and r["reply_status"] == "UNAVAILABLE", r
    assert r["reason"] == "PROVIDER_UNREACHABLE" and "can't reach my private model" in r["why"]
    v = H.post(c, csrf, "/api/cc/private/view", {}).json()
    roles = [t["role"] for t in v["conversation"] if t["text"] == OWNER[7]]
    assert roles == ["owner"]                                    # stored; no Laura turn faked
    assert not [t for t in v["conversation"] if t["role"] == "laura" and
                t.get("text") in ("", None)]


# ---------------------------------------------------------------- privacy

def _open(c, csrf) -> str:
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
    return c.get("/api/cc/auth/status").json()["session"]["session_id"]


def test_venice_receives_only_the_private_turn_and_nothing_private_leaks_anywhere():
    from brambleloop.core import continuity

    c, csrf = H.session()
    sid = _open(c, csrf)
    log = io.StringIO()
    handler = logging.StreamHandler(log)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    out, err = io.StringIO(), io.StringIO()
    mock = Venice(answers=[_ok(json.dumps({"text": REPLIES[2]})),
                           _ok(json.dumps({"text": REPLIES[3]})),
                           (500, f"INFERENCE_FAILED {BODY}"), (-1, "")])
    try:
        with PL.sql_params(DB) as sql, contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            H.post(c, csrf, "/api/cc/private/remember",
                   {"key": "PRIV-LABEL-VENLEAK", "text": OWNER[3]})
            with venice(mock):
                a = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[4]}).json()
                b = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[5]}).json()
                e = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[6]}).json()
                f = private_context.owner_turn(DB, sid, OWNER[7])
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    assert a["reply_status"] == b["reply_status"] == "REPLIED", (a, b)
    assert e["reason"] == f["reason"] == "PROVIDER_UNREACHABLE", (e, f)
    assert BODY not in json.dumps([e, f])
    # What Venice received: the pinned system prompt plus ONE user message made of the three
    # delimited private blocks (owner notes, recent private turns, newest message) and the
    # fixed template. Nothing from the company: no business memory, finance or catalogue.
    assert len(mock.calls) == 4
    second = mock.calls[1]["body"]["messages"]
    assert [m["role"] for m in second] == ["system", "user"]
    assert second[0]["content"] == LR.PROMPT.system
    user = second[1]["content"]
    assert len(PL.blocks(user)) == 3
    assert OWNER[3] in user and OWNER[4] in user and REPLIES[2] in user and OWNER[5] in user
    assert PL.outside_blocks(user).strip().endswith('Reply to the newest message. JSON: '
                                                   '{"text": "..."}')
    outside = PL.outside_blocks(user)
    assert not [x for x in OWNER + REPLIES if x in outside]
    sent = json.dumps(mock.calls)
    company = ("harbour-shawl", "Harbour Shawl", "triangle shawl", "seasonal.sentinel",
               "confirm the public shop name")             # H.seed_company() business records
    assert not [x for x in company if x in sent], "business data sent to Venice"
    # Nowhere else: SQL bound parameters, logging, stdio, every business table, the
    # continuity export, the paid-call journal and the analysis cache.
    assert len(sql) > 20 and "laura.private_reply@2" in "\n".join(sql)   # positive control
    assert not _leaks("\n".join(sql)), _leaks("\n".join(sql))
    assert not _leaks(log.getvalue()), "logging"
    assert not _leaks(out.getvalue() + err.getvalue()), "stdio"
    blob, counts = PL.table_dump(DB)
    assert counts.get("cost_entries", 0) >= 2, counts
    assert "venice" in blob and "model.attempt" in blob                 # positive control
    assert not _leaks(blob), _leaks(blob)
    assert counts.get("paid_call_records", 0) == 0, counts               # never journalled
    assert paid_calls.current_job_id() is None
    with tempfile.TemporaryDirectory(prefix="w4ven-") as td:
        res = continuity.export(DB, Path(td) / "export.jsonl")
        exp = res.path.read_text(encoding="utf-8") + Path(
            str(res.path) + ".manifest.json").read_text(encoding="utf-8")
    assert "laura_private_" not in exp and not _leaks(exp)
    # Positive control: the owner sees the replies in the private view.
    v = H.post(c, csrf, "/api/cc/private/view", {})
    assert REPLIES[2] in v.text and REPLIES[3] in v.text
    assert v.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- access and persistence

def test_owner_only_access():
    anon = H.client()
    for path in ("/api/cc/private/turn", "/api/cc/private/view", "/api/cc/private/open"):
        r = anon.post(path, json={"text": OWNER[0]})
        assert r.status_code in (401, 403), (path, r.status_code)
    assert anon.get("/api/cc/private/status").status_code in (401, 403)
    c, csrf = H.session()                       # an owner session WITHOUT the private step-up
    with venice(Venice()) as m:
        r = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[0]})
        assert r.status_code in (401, 403), r.status_code
        assert m.calls == []
    assert OWNER[0] not in r.text


def test_persistence_across_restart_in_the_encrypted_store():
    kit.set_key(kit.new_key())
    path = os.path.join(tempfile.mkdtemp(prefix="w4ven-restart-"), "r.sqlite")
    db1 = fresh_db(path)
    Registry(db1).seed_defaults()
    sid1 = kit.owner_session(db1)
    assert private_context.open_(db1, sid1)["open"] is True
    private_context.remember(db1, sid1, "PRIV-LABEL-VENREST", OWNER[0])
    with venice(Venice(answers=[_ok(json.dumps({"text": REPLIES[0]}))])):
        a = private_context.owner_turn(db1, sid1, OWNER[1])
    assert a["reply_status"] == "REPLIED", a
    raw = raw_storage_bytes(db1)
    assert raw and not [x for x in (OWNER[0], OWNER[1], REPLIES[0]) if x.encode() in raw]
    db1.engine.dispose()
    db2 = reopen(path)                                   # a restart: new engine, new session
    sid2 = kit.owner_session(db2)
    assert private_context.open_(db2, sid2)["open"] is True
    mock = Venice(answers=[_ok(json.dumps({"text": REPLIES[1]}))])
    with venice(mock):
        b = private_context.owner_turn(db2, sid2, OWNER[2])
    assert b["reply_status"] == "REPLIED", b
    user = mock.calls[0]["body"]["messages"][1]["content"]
    assert OWNER[0] in user and OWNER[1] in user and REPLIES[0] in user   # memory feeds it
    v = private_context.view(db2, sid2)
    turns = [(t["role"], t["text"]) for t in v["conversation"]]
    assert turns == [("owner", OWNER[1]), ("laura", REPLIES[0]), ("owner", OWNER[2]),
                     ("laura", REPLIES[1])], turns
    from brambleloop.laura.private import store
    refs = [t.model_ref for t in store.conversation(db2, private_context._principal(db2, sid2))
            if t.role == "laura"]
    assert refs == [f"venice/{V.MODEL}"] * 2, refs


# ---------------------------------------------------------------- credential health

class Http:
    def __init__(self, answer=(200, json.dumps({"data": {
            "accessPermitted": True, "balances": {"USD": 12.5, "DIEM": 0,
                                                  "BUNDLED_CREDITS": 1.0}}}))):
        self.answer, self.calls = answer, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        if "venice" in url:
            return self.answer
        return (200, '{"credits": 500}') if "bfl" in url else (200, '{"input_tokens": 3}')


def test_venice_credential_health_is_owner_enabled_and_reads_the_balance():
    h = Http()
    got = CR.check_venice({"VENICE_API_KEY": VKEY}, h)
    assert got["status"] == CR.OK and got["balance_usd"] == 12.5, got
    (call,) = h.calls
    assert call["method"] == "GET" and call["body"] is None
    assert call["url"] == "https://api.venice.ai/api/v1/api_keys/rate_limits"
    assert call["headers"]["Authorization"] == f"Bearer {VKEY}"
    assert CR.check_venice({}, h)["status"] == CR.MISSING
    low = {"data": {"accessPermitted": True, "balances": {"USD": 0, "DIEM": 0,
                                                          "BUNDLED_CREDITS": 0}}}
    assert CR.check_venice({"VENICE_API_KEY": VKEY}, Http((200, json.dumps(low))))[
        "status"] == CR.INSUFFICIENT_CREDIT
    denied = {"data": {"accessPermitted": False, "balances": {"USD": 50}}}
    assert CR.check_venice({"VENICE_API_KEY": VKEY}, Http((200, json.dumps(denied))))[
        "status"] == CR.PERMISSION
    for st, want in ((401, CR.REJECTED), (402, CR.INSUFFICIENT_CREDIT), (403, CR.PERMISSION),
                     (429, CR.RATE_LIMITED), (503, CR.OUTAGE), (0, CR.OUTAGE)):
        g = CR.check_venice({"VENICE_API_KEY": VKEY}, Http((st, f"x {VKEY}")))
        assert g["status"] == want and VKEY not in json.dumps(g), (st, g)
    assert CR.check_venice({"VENICE_API_KEY": VKEY}, Http((200, "nope")))["status"] == CR.UNKNOWN
    # check_all: Venice is NOT checked until the owner selects it (cost of the check UNKNOWN).
    db = _db()
    h = Http()
    recs = CR.check_all(db, env={"VENICE_API_KEY": VKEY}, http=h)
    assert [r["provider"] for r in recs] == ["bfl", "anthropic"]
    assert not [c for c in h.calls if "venice" in c["url"]]
    h = Http()
    recs = CR.check_all(db, env=VENICE_ON, http=h)
    (vr,) = [r for r in recs if r["provider"] == "venice"]
    assert vr["status"] == CR.OK and vr["estimate_cad"] is None             # UNKNOWN, never 0
    assert vr["estimate_basis"].startswith("UNKNOWN")
    stored = json.dumps([a.detail for a in _rows(db, AuditLog)], default=str)
    assert VKEY not in stored and VKEY[-4:] + '"' not in stored
    st = {p["provider"]: p for p in CR.state(db, owner=True, env=VENICE_ON)}
    assert st["venice"]["status"] == CR.OK and st["venice"]["fingerprint"]["last4"] == VKEY[-4:]
    assert VKEY not in json.dumps(st)
    assert "VENICE_API_KEY" in CR.owner_action("venice", CR.MISSING)


# ---------------------------------------------------------------- prices and the day

def test_price_table_and_the_daily_arithmetic_in_venice_md():
    assert V.PRICES_USD_PER_MTOK[V.MODEL] == (1.40, 4.40)
    assert V.CONTEXT_TOKENS[V.MODEL] == 1_000_000
    pin, pout = V.PRICES_USD_PER_MTOK[V.MODEL]
    typical_usd = 1500 / 1e6 * pin + 150 / 1e6 * pout                   # a typical reply
    typical_cad = typical_usd * gw.USD_TO_CAD
    assert 0.0038 < typical_cad < 0.0040, typical_cad
    assert int(0.50 // typical_cad) == 127, int(0.50 // typical_cad)
    worst = V.estimate_for(LR.PROMPT.system, "x" * 12000, 400)          # a long context
    assert worst < 0.02, worst
    doc = (ROOT / "research/final_build/w4/VENICE.md").read_text(encoding="utf-8")
    for needle in ("zai-org-glm-5-2", "https://api.venice.ai/api/v1", "Authorization: Bearer",
                   "VENICE_API_KEY", "BRAMBLELOOP_PRIVATE_PROVIDER=venice", "127",
                   "PRODUCTION ACCEPTANCE TEST", "ADD-PLV-07", "include_venice_system_prompt"):
        assert needle in doc, needle


if __name__ == "__main__":
    H.run(globals())
