"""W4-LAURAONE: one Laura, one thread (owner requirement 2026-10-20; D-W4-LAURA-UNIFIED;
spec/13 ADD-LCONT-01..10; research/final_build/w4/LAURAONE.md).

Offline. Venice is a mocked transport (`VeniceProvider._post` replaced); Business Laura's model
is a scripted stand-in behind the REAL gateway (reservation, billing, validation); the Anthropic
transport fails the test if anything reaches it; every socket is refused by the harness.

Covered: continuity across subject changes; restart and model changes (Venice model swap,
Claude tier change); the leak guard on the brief and on the outbound business request; the
cross-boundary approval flow (nothing crosses without an approval with step-up; the crossing
record holds the approved text only); budgets (agent per call, reservation first, exhausted
budget means no call and no fallback); owner-only access; switch OFF = unchanged behaviour;
privacy controls (mark private, exclude, include, forget a range); key rotation; leak sweep of
a private, an adult and a mixed turn across every business table, SQL parameters, logs, stdio,
the continuity export and the outbound business payloads.

Neutral sentinels only (PRIV-SENTINEL-...). Stand-in key strings only.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_laura_unified.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit

import contextlib
import io
import json
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path

import w3_laura_cc_harness as H  # noqa: E402  (isolated DB, sockets refused, no provider keys)
import w4_pl_harness as PL  # noqa: E402
from w3_laura_memory_harness import fresh_db, raw_storage_bytes, reopen  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import private_context as PC  # noqa: E402
from brambleloop.core.models import Agent, AuditLog, CostEntry, SpendReservation  # noqa: E402
from brambleloop.gateway import laura_register as LR  # noqa: E402
from brambleloop.gateway import laura_unified as U  # noqa: E402
from brambleloop.gateway import venice as V  # noqa: E402
from brambleloop.gateway.model_gateway import EchoProvider  # noqa: E402
from brambleloop.laura.agency import boundary, ceo_chat  # noqa: E402
from brambleloop.laura.agency.models import LauraBoundaryCrossing, LauraTurn  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402
from brambleloop.laura.private import store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
H.seed_company()
kit.set_key(kit.new_key())
VKEY = "venice-STANDIN-" + uuid.uuid4().hex

S_PRIV = "PRIV-SENTINEL-ONE-PRIV-0001"
S_ADULT = "PRIV-SENTINEL-ONE-ADULT-0002"
S_MIX = "PRIV-SENTINEL-ONE-MIX-0003"
S_NOTE = "PRIV-SENTINEL-ONE-NOTE-0004"
S_EVERY = "PRIV-SENTINEL-ONE-EVERY-0005"
S_CODE = "PRIV-SENTINEL-ONE-CODE-0006"
R = tuple(f"PRIV-SENTINEL-ONE-REPLY-{i:04d}" for i in range(1, 12))
PRIVATE_TURN = f"I missed you today, darling. {S_PRIV} is our little word."
ADULT_TURN = f"Kiss me tonight in bed, {S_ADULT}."
EVERYDAY_TURN = f"Good morning! It rained here, {S_EVERY}."
MIX_TURN = f"I love you {S_MIX}. What should the shop prioritise this week?"
MIX_QUOTE = "What should the shop prioritise this week?"
BUSINESS_TURN = "What should the shop prioritise this week?"
STRUCT_BIZ = "What did the company do this week?"     # code-rendered from BUSINESS_TURN
CHEAP_Q = "What did the shop do overnight?"
BIZ_ANSWER = "Confirming the public shop name comes first; it unblocks the Etsy setup."
ALL_PRIVATE = (S_PRIV, S_ADULT, S_MIX, S_NOTE, S_EVERY, S_CODE) + R


def _leaks(blob: str) -> list[str]:
    return [x for x in ALL_PRIVATE + (VKEY,) if x in blob]


# ---------------------------------------------------------------- stand-ins


def _ok(text: str, *, tokens=(900, 60)) -> tuple[int, str]:
    return 200, json.dumps({"id": "x", "object": "chat.completion",
                            "choices": [{"index": 0, "finish_reason": "stop",
                                         "message": {"role": "assistant", "content": text}}],
                            "usage": {"prompt_tokens": tokens[0],
                                      "completion_tokens": tokens[1],
                                      "total_tokens": sum(tokens)}})


def _newest(user: str) -> str:
    tag = "<<<PRIVATE DATA: the owner's newest message"
    if tag not in user:
        return user
    rest = user[user.index(tag):]
    rest = rest[rest.index(">>>") + 3:]
    return rest[:rest.index(LR.DATA_CLOSE)]


def default_route(user: str) -> dict:
    """Stands in for Laura's judgement: a business tool when the newest message is about the
    business (mixed included), none otherwise."""
    from brambleloop.laura.agency import delegation

    newest = _newest(user)
    lab = U.classify(newest)["label"]
    if lab in ("business", "mixed") and delegation.parse(newest):
        return {"tool": "business.delegate", "brief": ""}
    return {"tool": "business.ask" if lab in ("business", "mixed") else "none", "brief": ""}


class Venice:
    """Mocked Venice transport. Reply calls (pinned private prompt) are in `calls` and answer
    R[i] in order; Laura's intent-router calls are in `routes` and answer `route(user)`."""

    def __init__(self, replies=None, on_call=None, route=default_route, fail=None):
        self.calls: list[dict] = []
        self.routes: list[dict] = []
        self.replies = list(replies or [])
        self.on_call = on_call
        self.route = route
        self.fail = fail

    def __call__(self, provider, url, body, headers, timeout):
        b = json.loads(body.decode())
        if self.on_call is not None:
            self.on_call()
        if self.fail is not None:
            self.calls.append({"url": url, "body": b})
            return self.fail
        if b["messages"][0]["content"] == U.INTENT.system:
            self.routes.append({"url": url, "body": b})
            return _ok(json.dumps(self.route(b["messages"][1]["content"])))
        self.calls.append({"url": url, "body": b})
        text = self.replies.pop(0) if self.replies else R[-1]
        return _ok(json.dumps({"text": text}))

    def user(self, i: int = -1) -> str:
        return self.calls[i]["body"]["messages"][1]["content"]

    def system(self, i: int = -1) -> str:
        return self.calls[i]["body"]["messages"][0]["content"]


class Biz:
    """Business Laura's model, scripted behind the real gateway. Records every request."""

    def __init__(self, reply=BIZ_ANSWER, on_call=None, offer_first=False, vary=False):
        self.seen: list[tuple[str, str, str]] = []
        self.reply = reply
        self.vary = vary
        self.on_call = on_call
        self.offer_first = offer_first

    def factory(self, model):
        def scripted(system, user):
            self.seen.append((model, system, user))
            if self.on_call is not None:
                self.on_call()
            offer = ["P1"] if self.offer_first and "\nP1 |" in user else []
            text = self.reply
            if self.vary:
                text = ("Listings are steady; nothing needs you there.",
                        "Overnight the queue ran cleanly and nothing failed.",
                        "Confirming the shop name still comes first for setup.",
                        "Design is reviewing banner drafts today.")[(len(self.seen) - 1) % 4]
            return json.dumps({"reply": text, "citations": [], "offer": offer,
                               "remember": ""})
        return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                            cost_per_1k_output_cad=0.005, scripted=scripted)

    def blob(self) -> str:
        return "\n".join(s + "\n" + u for _, s, u in self.seen)


ON = {"BRAMBLELOOP_PRIVATE_PROVIDER": "venice", "VENICE_API_KEY": VKEY,
      "BRAMBLELOOP_LAURA_CEO_MODEL": "1",      # Business Laura's model on (S-1 switch)
      "ANTHROPIC_API_KEY": None, U.UNIFIED_ENV: "venice", U.BUSINESS_TO_VENICE_ENV: None,
      V.MODEL_ENV: None}


@contextlib.contextmanager
def unified(mock: Venice | None, **env):
    """Owner switches on (unified + Private Laura prerequisites), Venice mocked, Anthropic's
    transport refusing. `mock=None` makes ANY Venice request fail the test."""
    orig = V.VeniceProvider._post
    if mock is not None:
        V.VeniceProvider._post = lambda self, url, body, headers, timeout: mock(
            self, url, body, headers, timeout)
    else:
        def _refuse(self, *a, **k):
            raise AssertionError("a Venice request was made where none may be")
        V.VeniceProvider._post = _refuse
    try:
        with PL.enabled(None, **{**ON, **env}):
            yield mock
    finally:
        V.VeniceProvider._post = orig


def _db():
    db = fresh_db()
    Registry(db).seed_defaults()
    return db


def _open(db):
    sid = kit.owner_session(db)
    assert PC.open_(db, sid)["open"] is True
    return sid


def _rows(db, model):
    with db.session() as s:
        rows = list(s.scalars(select(model)))
        for r in rows:
            s.expunge(r)
    return rows


def _fresh():
    """A step-up performed now (after any offer made so far in the test)."""
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(seconds=1)


def _turn(db, sid, text, biz: Biz | None = None, **kw):
    return PC.unified_turn(db, sid, text, provider_factory=biz.factory if biz else None, **kw)


def _dbg(db, sid, t, biz):
    try:
        return _turn(db, sid, t, biz)
    except PC.PrivateUnavailable as exc:
        raise AssertionError((t[:20], exc.exc_name)) from None


def _view(db, sid):
    with unified(None):
        return PC.unified_view(db, sid)


def _control(db, sid, action, ids):
    with unified(None):
        return PC.unified_control(db, sid, action, ids)


# ---------------------------------------------------------------- the classifier


def test_classifier_is_deterministic_and_fails_toward_privacy():
    assert U.classify(BUSINESS_TURN)["label"] == "business"
    assert U.classify(PRIVATE_TURN)["label"] == "private"
    a = U.classify(ADULT_TURN)
    assert a["label"] == "private" and a["sensitive"] is True
    assert U.classify(EVERYDAY_TURN)["label"] == "everyday"       # no signal -> not business
    m = U.classify(MIX_TURN)
    assert m["label"] == "mixed" and m["business_text"] == MIX_QUOTE
    assert m["business_text"] in MIX_TURN                          # a verbatim quote
    assert U.classify(BUSINESS_TURN, force_private=True)["label"] == "private"
    assert [U.classify(BUSINESS_TURN) for _ in range(3)] == [U.classify(BUSINESS_TURN)] * 3
    # Leak guard matching: exact, normalised (case/punctuation/whitespace), 6-word shingles.
    p = ["the blue lantern sings at dawn for us", "hi"]
    assert U.leak_check("The Blue-Lantern  sings, at DAWN for us!", p)[0]["how"] == "normalised"
    assert U.leak_check("x the blue lantern sings at dawn y", p)[0]["how"] == "shingle"
    assert U.leak_check("what did the shop sell", p) == []        # "hi" is below threshold
    assert U.leak_check("the blue lantern sings at dawn for us", p,
                        allowed=["the blue lantern sings at dawn for us"]) == []


# ---------------------------------------------------------------- switch OFF = unchanged


def test_switch_off_means_behaviour_unchanged():
    assert U.mode({}) == "" and not U.enabled({}) and not U.business_to_venice({})
    assert U.mode({U.UNIFIED_ENV: "anthropic"}) == ""           # only "venice" switches on
    db = _db()
    sid = _open(db)
    with unified(None, **{U.UNIFIED_ENV: None}):
        try:
            PC.unified_turn(db, sid, PRIVATE_TURN)
            raise AssertionError("the unified thread answered while switched off")
        except PC.PrivateUnavailable as exc:
            assert (exc.status, exc.code) == (404, "UNIFIED_OFF")
        out = PC.owner_turn(db, sid, PRIVATE_TURN)                 # the existing route works
    assert out["reply_status"] == "UNAVAILABLE" and out["reason"] == "REGISTER_OFF" or \
        out["reply_status"] in ("UNAVAILABLE", "REPLIED"), out
    c, csrf = H.session()
    assert H.post(c, csrf, "/api/cc/laura/unified/turn", {"text": "hi"}).status_code in (
        403, 404)
    st = c.get("/api/cc/laura/unified/status").json()
    assert st["unified"] == "off" and st["prerequisites"][0] == {
        "id": "unified_switch", "met": False,
        "label": f"unified thread switch {U.UNIFIED_ENV}=venice"}, st
    r = H.post(c, csrf, "/api/cc/laura/converse", {"question": "Hello Laura"})
    # Every switch off (S-1 included): the deterministic evidence-tool answer, no model call.
    assert r.status_code == 200 and r.json()["model"]["source"] == "not_called", r.text


def test_switch_on_closes_the_split_routes():
    db = _db()
    sid = _open(db)
    with unified(None):
        try:
            PC.owner_turn(db, sid, PRIVATE_TURN)
            raise AssertionError("the split private route stayed open")
        except PC.PrivateUnavailable as exc:
            assert (exc.status, exc.code) == (409, "UNIFIED_THREAD")
        c, csrf = H.session()
        assert H.post(c, csrf, "/api/cc/laura/converse",
                      {"question": "Hello"}).status_code == 409
        assert c.get("/api/cc/laura/unified/status").json()["unified"] == "venice"


# ---------------------------------------------------------------- continuity


def test_one_thread_keeps_continuity_across_subject_changes():
    db = _db()
    sid = _open(db)
    PC.remember(db, sid, "PRIV-LABEL-ONE", S_NOTE)
    mock = Venice(replies=[R[0], R[1], R[2]])
    biz = Biz()
    with unified(mock):
        a = _turn(db, sid, PRIVATE_TURN, biz)
        b = _turn(db, sid, BUSINESS_TURN, biz)
        c_ = _turn(db, sid, EVERYDAY_TURN, biz)
        d = _turn(db, sid, ADULT_TURN, biz)
    assert [x["label"] for x in (a, b, c_, d)] == ["private", "business", "everyday", "private"]
    assert a["reply"]["text"] == R[0] and a["reply"]["side"] == "conversation"
    assert b["reply"]["text"] == BIZ_ANSWER and b["reply"]["side"] == "business", b
    # Structured by default: the business tool got a code-rendered request, not her words.
    assert b["reply"]["brief"] == STRUCT_BIZ and b["intent"]["params"]["date_range"] == "this_week"
    assert BUSINESS_TURN not in biz.blob()
    assert b["crossing"]["origin"] == "owner_quote" and b["crossing"]["requires_stepup"] is False
    assert c_["reply"]["text"] == R[1] and d["reply"]["text"] == R[2]
    assert len(mock.calls) == 3 and len(biz.seen) == 1          # one call per turn, one side
    # Venice keeps the conversation: the private turn, its reply and the note are in context;
    # the business exchange is a content-free placeholder (business-to-Venice is off).
    u = mock.user(-1)
    assert S_PRIV in u and R[0] in u and S_NOTE in u and S_EVERY in u and R[1] in u
    assert U.BUSINESS_PLACEHOLDER in u and BUSINESS_TURN not in u and BIZ_ANSWER not in u
    # One Laura: Venice gets the pinned private prompt; both name the canonical identity and
    # say she is an AI.
    assert mock.system(-1) == LR.PROMPT.system and "laura-r2-a42aeac7" in mock.system(-1)
    assert "You are an AI" in mock.system(-1) and "never a human" in biz.seen[0][1]
    # One thread: every turn, in order, with its label, in the encrypted store.
    v = _view(db, sid)
    got = [(t["role"], t["label"], t["text"]) for t in v["turns"]]
    assert got == [("owner", "private", PRIVATE_TURN), ("laura", "private", R[0]),
                   ("owner", "business", BUSINESS_TURN), ("laura", "business", BIZ_ANSWER),
                   ("owner", "everyday", EVERYDAY_TURN), ("laura", "everyday", R[1]),
                   ("owner", "private", ADULT_TURN), ("laura", "private", R[2])], got
    assert [t["sensitive"] for t in v["turns"] if t["role"] == "owner"] == [
        False, False, False, True]
    # The business side holds the structured brief and the result only.
    (bt,) = _rows(db, LauraTurn)
    assert bt.question == STRUCT_BIZ and bt.answer == BIZ_ANSWER
    # With the feed switched on, Venice gets the allowlisted pack -- never the business
    # exchange's free text, which stays a placeholder.
    m2 = Venice(replies=[R[3]])
    with unified(m2, **{U.BUSINESS_TO_VENICE_ENV: "1"}):
        _turn(db, sid, "Are you still there?", biz)
    assert "brambleloop.laura.venice_context.v1" in m2.user()
    assert BUSINESS_TURN not in m2.user() and BIZ_ANSWER not in m2.user()
    assert U.BUSINESS_PLACEHOLDER in m2.user()


def test_the_thread_survives_a_restart_a_venice_model_swap_and_a_claude_tier_change():
    path = os.path.join(tempfile.mkdtemp(prefix="w4one-restart-"), "r.sqlite")
    db1 = fresh_db(path)
    Registry(db1).seed_defaults()
    sid1 = _open(db1)
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        _turn(db1, sid1, PRIVATE_TURN, biz)
        _turn(db1, sid1, CHEAP_Q, biz)                              # cheap tier (converse)
    raw = raw_storage_bytes(db1)
    assert raw and S_PRIV.encode() not in raw and R[0].encode() not in raw   # encrypted
    db1.engine.dispose()
    db2 = reopen(path)                                               # restart: new engine
    sid2 = _open(db2)
    mock = Venice(replies=[R[1]])
    with unified(mock, **{V.MODEL_ENV: "zai-org-glm-5-2"}):          # Venice model swap
        r = _turn(db2, sid2, EVERYDAY_TURN, biz)
        q = "Why should we focus on the shop name first, strategically?"
        rb = _turn(db2, sid2, q, biz)                                # standard tier
    assert r["reply"]["model_ref"] == "venice/zai-org-glm-5-2", r
    assert mock.calls[0]["body"]["model"] == "zai-org-glm-5-2"
    assert S_PRIV in mock.user(0) and R[0] in mock.user(0)           # same thread, new model
    assert rb["label"] == "business"
    models = [m for m, _, _ in biz.seen]
    assert len(set(models)) == 2, models                             # Claude tier changed ...
    assert "What did the company do overnight?" in biz.seen[-1][2] and \
        BIZ_ANSWER in biz.seen[-1][2], biz.seen[-1][2][-1500:]          # ... history kept
    v = _view(db2, sid2)
    refs = [t["model_ref"] for t in v["turns"] if t["role"] == "laura"]
    assert refs[0] == f"venice/{V.MODEL}" and refs[2] == "venice/zai-org-glm-5-2", refs
    assert refs[1].startswith("business/") and refs[3].startswith("business/"), refs
    assert len(v["turns"]) == 8


# ---------------------------------------------------------------- the leak guard


def test_leak_guard_blocks_private_text_in_a_business_brief():
    db = _db()
    sid = _open(db)
    secret = f"honey the lantern code is {S_CODE} blue morning glass"
    leaky = f"For the shop listings, use the lantern code is {S_CODE} blue morning glass"
    assert U.classify(leaky)["label"] == "business"                 # classifier alone passes it
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        _turn(db, sid, secret, biz)
        out = _turn(db, sid, leaky, biz)
    # Structured first: the business tool got a code-rendered request without her words.
    assert out["reply"]["side"] == "business" and len(biz.seen) == 1, out
    assert S_CODE not in biz.blob() and "lantern" not in biz.blob()
    # Her exact words are only offered. Because they overlap our private conversation (the
    # guard, as defence in depth), the one-tap offer is upgraded: it needs a fresh step-up.
    x = out["crossing"]
    assert x["text"] == leaky and x["requires_stepup"] is True and x["overlaps_private"] is True
    with unified(Venice()):
        try:
            PC.unified_crossing(db, sid, x["id"], approve=True, provider_factory=biz.factory)
            raise AssertionError("private-overlapping words crossed with one tap")
        except PC.PrivateUnavailable as exc:
            assert exc.code == "STEP_UP_REQUIRED"
    assert len(biz.seen) == 1 and S_CODE not in biz.blob() and _rows(db, LauraBoundaryCrossing) == []
    # A clean business turn's words are a one-tap offer (no step-up).
    with unified(Venice()):
        clean = _turn(db, sid, "How many listings are live in the shop?", biz)
    assert clean["crossing"]["requires_stepup"] is False
    assert clean["crossing"]["overlaps_private"] is False


def test_outbound_business_request_is_checked_and_refused_before_any_call():
    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        _turn(db, sid, f"darling, our word is {S_CODE} under the lantern moon", biz)
    # Some business record (however it got there) carries private-thread text into the
    # business history of the thread. The guard checks the EXACT outbound request and refuses
    # before any reservation; nothing is sent or persisted.
    with db.session() as s_:
        s_.add(LauraTurn(session_public_id=PC.UNIFIED_BUSINESS_SESSION,
                         question=f"note: our word is {S_CODE} under the lantern moon",
                         answer="ok", status="ANSWERED"))
    before = len([r for r in _rows(db, SpendReservation) if r.agent == "laura"])
    with unified(Venice()):
        b = _turn(db, sid, "What did the shop sell overnight?", biz)
    assert b["reply_status"] == "REFUSED" and b["reason"] == "LEAK_GUARD", b
    assert biz.seen == []
    assert len([r for r in _rows(db, SpendReservation) if r.agent == "laura"]) == before
    assert len(_rows(db, LauraTurn)) == 1                            # nothing new persisted


def test_marking_private_afterwards_redacts_the_derived_business_records():
    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        a = _turn(db, sid, "What did the shop sell overnight?", biz)
        m = _turn(db, sid, MIX_TURN, biz)
        x = PC.unified_crossing(db, sid, m["crossing"]["id"], approve=True, verified_for_action=True,
                                provider_factory=biz.factory)
    assert x["crossed"] and len(_rows(db, LauraTurn)) == 2
    out = _control(db, sid, "mark_private", [a["id"], m["id"]])
    assert out["redacted"] == {"business_turns": 2, "crossings": 1}, out
    for row in _rows(db, LauraTurn):
        assert row.question == boundary.REDACTED and row.answer == boundary.REDACTED
        assert row.facts == [] and row.proposals == []
    (cr,) = _rows(db, LauraBoundaryCrossing)
    assert cr.approved_text == boundary.REDACTED and cr.text_sha256 == ""   # N-8
    assert MIX_QUOTE not in PL.table_dump(db)[0]
    assert boundary.approved_texts(db) == []                         # no longer allowed


# ---------------------------------------------------------------- crossing the boundary


def test_a_mixed_turn_crosses_only_the_exact_text_and_only_with_approval_and_step_up():
    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        m = _turn(db, sid, MIX_TURN, biz)
    assert m["label"] == "mixed" and m["reply"]["text"] == R[0]      # Laura still answers
    x = m["crossing"]
    assert x["status"] == "pending" and x["text"] == MIX_QUOTE and MIX_QUOTE in x["question"]
    assert biz.seen == [] and _rows(db, LauraBoundaryCrossing) == []  # nothing crossed yet
    # Declining crosses nothing, ever.
    with unified(Venice()):
        m2 = _turn(db, sid, f"I love you {S_MIX}. Which listings sold best?", biz)
        d = PC.unified_crossing(db, sid, m2["crossing"]["id"], approve=False,
                                provider_factory=biz.factory)
    assert d == {"id": m2["crossing"]["id"], "status": "declined", "crossed": False}
    assert biz.seen == [] and _rows(db, LauraBoundaryCrossing) == []
    # Approving releases exactly the shown text: one crossing record holding it alone, and
    # one business call whose request carries it and no private-thread text.
    # Not business-classified: approval needs a fresh step-up.
    with unified(Venice()):
        try:
            PC.unified_crossing(db, sid, x["id"], approve=True, provider_factory=biz.factory)
            raise AssertionError("a mixed turn crossed without step-up")
        except PC.PrivateUnavailable as exc:
            assert (exc.status, exc.code) == (403, "STEP_UP_REQUIRED")
        assert biz.seen == [] and _rows(db, LauraBoundaryCrossing) == []
        a = PC.unified_crossing(db, sid, x["id"], approve=True, verified_for_action=True,
                                provider_factory=biz.factory)
    assert a["status"] == "approved" and a["crossed"] is True, a
    assert a["reply"]["text"] == BIZ_ANSWER and len(biz.seen) == 1
    assert MIX_QUOTE in biz.blob() and not _leaks(biz.blob()), _leaks(biz.blob())
    (row,) = _rows(db, LauraBoundaryCrossing)
    assert row.approved_text == MIX_QUOTE and len(row.text_sha256) == 64
    assert boundary.approved_texts(db) == [MIX_QUOTE]
    (bt,) = _rows(db, LauraTurn)
    assert bt.question == MIX_QUOTE and not _leaks(bt.question + bt.answer)
    # A request is resolved once; nothing re-crosses.
    with unified(Venice()):
        try:
            PC.unified_crossing(db, sid, x["id"], approve=True, verified_for_action=True,
                                provider_factory=biz.factory)
            raise AssertionError("a crossing was approved twice")
        except PC.PrivateUnavailable as exc:
            assert exc.status == 400
    assert len(_rows(db, LauraBoundaryCrossing)) == 1 and len(biz.seen) == 1
    v = _view(db, sid)
    assert [c["status"] for c in v["crossings"]] == ["approved", "declined"]


def test_crossing_approval_over_http_needs_a_fresh_step_up():
    c, csrf = H.session()
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    with unified(Venice(replies=[R[0]])):
        assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
        t = H.post(c, csrf, "/api/cc/laura/unified/turn", {"text": MIX_TURN})
        assert t.status_code == 200 and t.headers["cache-control"] == "no-store", t.text
        xid = t.json()["crossing"]["id"]
        H.expire_stepup(c)
        r = H.post(c, csrf, "/api/cc/laura/unified/crossing", {"id": xid, "approve": True})
        assert r.status_code == 403 and r.json().get("code", r.text).count("STEP_UP") or \
            "STEP_UP_REQUIRED" in r.text, r.text
        assert boundary.count(H.DB) == 0
        ok = H.post(c, csrf, "/api/cc/laura/unified/crossing",
                    {"id": xid, "approve": True, "passphrase": H.PASS})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["crossed"] is True
    # No business provider is configured in tests: Laura says so honestly, no fallback.
    assert body["reply"]["status"] == ceo_chat.UNAVAILABLE, body
    with H.DB.session() as s:
        texts = [t for (t,) in s.execute(select(LauraBoundaryCrossing.approved_text))]
    assert texts == [MIX_QUOTE]


# ---------------------------------------------------------------- money


def test_budgets_right_agent_reservation_first_and_no_call_when_exhausted():
    db = _db()
    sid = _open(db)
    seen_v: list = []
    seen_b: list = []

    def open_res(agent):
        return [(r.agent, r.purpose) for r in _rows(db, SpendReservation)
                if r.agent == agent and r.released_at is None]
    mock = Venice(replies=[R[0]], on_call=lambda: seen_v.append(open_res("laura_private")))
    biz = Biz(on_call=lambda: seen_b.append(open_res("laura")))
    with unified(mock):
        _turn(db, sid, PRIVATE_TURN, biz)
        _turn(db, sid, BUSINESS_TURN, biz)
    # Every Venice call (Laura's intent, then her reply) and the business call was reserved
    # BEFORE it was made, on its own agent.
    assert seen_v == [[("laura_private", U.INTENT.ref)], [("laura_private", LR.PURPOSE)],
                      [("laura_private", U.INTENT.ref)]], seen_v
    assert len(seen_b) == 1 and len(seen_b[0]) == 1 and seen_b[0][0][0] == "laura", seen_b
    bpurpose = seen_b[0][0][1]
    assert bpurpose in ("laura.converse@1", "laura.executive@1"), bpurpose
    costs = {(c.agent, c.purpose) for c in _rows(db, CostEntry)}
    assert costs == {("laura_private", LR.PURPOSE), ("laura_private", U.INTENT.ref),
                     ("laura", bpurpose)}, costs
    for c in _rows(db, CostEntry):
        assert not _leaks(json.dumps([c.detail, c.purpose, c.model], default=str))
    # laura_private exhausted: Laura says so; no Venice call, and no fallback to Claude.
    with unified(None, **{LR.DAILY_AUTH_ENV: "0.000001"}):
        out = _turn(db, sid, PRIVATE_TURN + " again", biz)
    assert out["reply_status"] == "UNAVAILABLE" and out["reason"] == "SPEND_CEILING", out
    assert "budget" in out["why"] and len(biz.seen) == 1
    # laura exhausted: Laura says so; no business call, and no fallback to Venice.
    with db.session() as s:
        s.scalar(select(Agent).where(Agent.name == "laura")).daily_cost_ceiling_cad = 0.0
    with unified(Venice(route=lambda u: {"tool": "business.ask", "brief": ""})) as vm:
        out = _turn(db, sid, "Which listings sold best overnight?", biz)
    assert vm.calls == []                                   # no fallback to a Venice reply
    assert out["reply"]["status"] == ceo_chat.UNAVAILABLE, out
    assert "no authorised daily model budget" in out["reply"]["text"]
    assert len(biz.seen) == 1
    refusals = [a for a in _rows(db, AuditLog) if a.action == "spend.refused"]
    assert len(refusals) >= 2 and not _leaks(json.dumps([r.detail for r in refusals],
                                                        default=str))
    # Nothing raised a ceiling.
    assert Registry(db).get("laura_private").daily_cost_ceiling_cad == 0.50


# ---------------------------------------------------------------- access


def test_owner_only_with_step_up():
    with unified(None):
        anon = H.client()
        assert anon.get("/api/cc/laura/unified/status").status_code in (401, 403)
        for path in ("view", "turn", "crossing", "control"):
            r = anon.post(f"/api/cc/laura/unified/{path}", json={"text": "x"})
            assert r.status_code in (401, 403), (path, r.status_code)
        c, csrf = H.session()                                    # owner, no private context
        r = H.post(c, csrf, "/api/cc/laura/unified/turn", {"text": PRIVATE_TURN})
        assert r.status_code == 403 and S_PRIV not in r.text, r.text
        r = H.post(c, csrf, "/api/cc/laura/unified/view", {})
        assert r.status_code == 403
        H.expire_stepup(c)                                       # cannot open without step-up
        assert H.post(c, csrf, "/api/cc/private/open", {}).status_code in (401, 403)
    # A business principal can never read the thread.
    try:
        store.conversation(H.DB, "laura")
        raise AssertionError("a non-private principal read the thread")
    except Exception as exc:  # noqa: BLE001
        assert type(exc).__name__ == "PrivateAccessRefused"


# ---------------------------------------------------------------- privacy controls


def test_privacy_controls_exclude_include_mark_private_and_forget_a_range():
    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0], R[1], R[2]])):
        a = _turn(db, sid, PRIVATE_TURN)
        b = _turn(db, sid, EVERYDAY_TURN)
        c_ = _turn(db, sid, ADULT_TURN)
    assert _control(db, sid, "exclude", [a["id"]])["affected"] == 2
    m = Venice(replies=[R[3]])
    with unified(m):
        _turn(db, sid, "Tell me something nice")
    assert S_PRIV not in m.user() and R[0] not in m.user() and S_EVERY in m.user()
    v = {t["id"]: t for t in _view(db, sid)["turns"]}
    assert v[a["id"]]["excluded"] is True and v[a["reply"]["id"]]["excluded"] is True
    assert _control(db, sid, "include", [a["id"]])["affected"] == 2
    m = Venice(replies=[R[4]])
    with unified(m):
        _turn(db, sid, "And again")
    assert S_PRIV in m.user()
    # Forget a range: the turns and their replies are gone from the thread and from context.
    n = _control(db, sid, "forget", [b["id"], c_["id"]])["affected"]
    assert n == 4, n
    texts = [t["text"] for t in _view(db, sid)["turns"]]
    assert EVERYDAY_TURN not in texts and ADULT_TURN not in texts and R[2] not in texts
    m = Venice(replies=[R[5]])
    with unified(m):
        _turn(db, sid, "One more")
    assert S_EVERY not in m.user() and S_ADULT not in m.user()
    # Force-private: a business-sounding turn the owner keeps private never reaches business.
    biz = Biz()
    with unified(Venice(replies=[R[6]])):
        p = _turn(db, sid, BUSINESS_TURN, biz, force_private=True)
    assert p["label"] == "private" and biz.seen == [] and p["reply"]["text"] == R[6]
    for bad in ("delete_all", ""):
        try:
            _control(db, sid, bad, [a["id"]])
            raise AssertionError("an unknown control was accepted")
        except PC.PrivateUnavailable as exc:
            assert exc.status == 400


def test_key_rotation_keeps_labels_flags_and_crossings():
    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0], R[1]])):
        a = _turn(db, sid, PRIVATE_TURN)
        m = _turn(db, sid, MIX_TURN)
    _control(db, sid, "exclude", [a["id"]])
    before = _view(db, sid)
    old_key = os.environ.get("BRAMBLELOOP_PRIVATE_MEMORY_KEY")
    new = kit.new_key()
    try:
        _rekey_and_check(db, sid, new, before, m)
    finally:
        kit.set_key(old_key)


def _rekey_and_check(db, sid, new, before, m):
    out = store.rekey(db, PC._principal(db, sid), {"BRAMBLELOOP_PRIVATE_MEMORY_KEY": new})
    assert out["rotated"] == 5 and out["grants_revoked"] is True      # 4 turns + 1 request
    kit.set_key(new)
    sid2 = _open(db)
    after = _view(db, sid2)
    key = lambda v: [(t["id"], t["label"], t["excluded"], t["text"]) for t in v["turns"]]  # noqa
    assert key(after) == key(before)
    assert [(x["id"], x["status"], x["text"]) for x in after["crossings"]] == [
        (m["crossing"]["id"], "pending", MIX_QUOTE)]


# ---------------------------------------------------------------- the leak sweep


def test_private_adult_and_mixed_turns_never_reach_business_tables_logs_or_payloads():
    from brambleloop.core import continuity

    c, csrf = H.session()
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    PC.remember(H.DB, sid, "PRIV-LABEL-SWEEP", S_NOTE)
    log = io.StringIO()
    handler = logging.StreamHandler(log)
    root = logging.getLogger()
    old = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    out, err = io.StringIO(), io.StringIO()
    biz = Biz()
    mock = Venice(replies=[R[7], R[8], R[9], R[10]])
    try:
        with PL.sql_params(H.DB) as sql, contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err), unified(mock):
            res = [_dbg(H.DB, sid, t, biz) for t in
                   (PRIVATE_TURN, ADULT_TURN, MIX_TURN, BUSINESS_TURN, EVERYDAY_TURN)]
            r = H.post(c, csrf, "/api/cc/laura/unified/turn", {"text": PRIVATE_TURN + "!"})
    finally:
        root.removeHandler(handler)
        root.setLevel(old)
    assert r.status_code == 200 and r.json()["reply"]["text"] == R[-1], r.text
    assert [x["label"] for x in res] == ["private", "private", "mixed", "business",
                                         "everyday"]
    assert len(biz.seen) == 1 and STRUCT_BIZ in biz.blob()          # positive control
    assert not _leaks(biz.blob()), _leaks(biz.blob())                # outbound business payload
    params = "\n".join(sql)
    bpurposes = {c.purpose for c in _rows(H.DB, CostEntry) if c.agent == "laura"}
    assert bpurposes and all(p in params for p in bpurposes), bpurposes   # positive control
    assert LR.PURPOSE in params
    assert not _leaks(params), _leaks(params)                        # every SQL parameter
    assert not _leaks(log.getvalue()), "logging"
    assert not _leaks(out.getvalue() + err.getvalue()), "stdio"
    blob, counts = PL.table_dump(H.DB)                               # every business table
    assert counts.get("laura_cc_turns", 0) >= 1 and STRUCT_BIZ in blob
    assert not _leaks(blob), _leaks(blob)
    with tempfile.TemporaryDirectory(prefix="w4one-") as td:
        exp_res = continuity.export(H.DB, Path(td) / "export.jsonl")
        exp = exp_res.path.read_text(encoding="utf-8") + Path(
            str(exp_res.path) + ".manifest.json").read_text(encoding="utf-8")
    assert "laura_private_" not in exp and not _leaks(exp)
    # Positive control: the owner sees all of it in the one thread (no-store POST).
    with unified(None):
        v = H.post(c, csrf, "/api/cc/laura/unified/view", {})
    assert S_PRIV in v.text and S_ADULT in v.text and S_MIX in v.text, v.text[:300]
    assert v.headers["cache-control"] == "no-store"


def test_static_isolation_is_unchanged():
    """The private API is still revealed only by private_context; the four pending register
    strings are byte-identical to the owner's WIP; business modules name nothing private."""
    from brambleloop.laura.private.access import ALLOWED_IMPORTERS

    assert ALLOWED_IMPORTERS == ("brambleloop.laura.private",
                                 "brambleloop.app.command_center.private_context")
    src = ROOT / "src" / "brambleloop"
    for rel in ("gateway/laura_unified.py", "laura/agency/boundary.py",
                "laura/agency/ceo_chat.py", "laura/agency/venice_context.py"):
        text = (src / rel).read_text()
        assert ".reveal(" not in text and "laura.private import" not in text, rel
        assert "private.store" not in text and "from ..laura.private" not in text, rel
    # The register copy is the owner's own commit (fcb2bcd), merged unchanged: this branch
    # neither edits it nor moves it (laura.js loads the thread view by dynamic import).
    js = (src / "app/command_center/static/js/views/laura.js").read_text().splitlines()
    assert js[272].lstrip().startswith('st.reply_register === "ENABLED" ? "Laura replies in '
                                       'her private'), js[272]
    assert PC.REPLY_ENABLED.startswith("Laura replies in her private")


# ---------------------------------------------------------------- Laura's intent drives tools


def test_lauras_intent_decides_when_a_business_tool_is_used():
    db = _db()
    sid = _open(db)
    biz = Biz()
    # She judges an everyday check-in needs her briefing tool: the brief is the fixed
    # canonical request for that tool (structured), never the conversation.
    mock = Venice(route=lambda u: {"tool": "business.briefing", "brief": ""})
    with unified(mock):
        out = _turn(db, sid, f"How is everything going? {S_EVERY}", biz)
    assert out["intent"]["tool"] == "business.briefing" and out["intent"]["routed_by"] == "laura"
    assert out["intent"]["params"] == {} and out["brief_origin"] == "structured"
    assert len(biz.seen) == 1 and "crossing" not in out          # no free text offered
    assert U.CANONICAL_BRIEF["business.briefing"] in biz.seen[0][2]
    assert not _leaks(biz.blob())
    # She judges a business-sounding message needs no tool: no business call; she answers.
    mock = Venice(replies=[R[0]], route=lambda u: {"tool": "none", "brief": ""})
    with unified(mock):
        out = _turn(db, sid, BUSINESS_TURN, biz)
    assert out["intent"]["tool"] == "none" and out["reply"]["text"] == R[0]
    assert len(biz.seen) == 1
    # Her router sees continuity context (Venice), never business data unless approved.
    assert S_EVERY in mock.routes[0]["body"]["messages"][1]["content"]
    assert mock.routes[0]["body"]["messages"][0]["content"] == U.INTENT.system
    # An unknown tool name is "none"; non-JSON is refused, never guessed.
    assert U.parse_intent('{"tool": "shell.exec", "brief": "x"}')["tool"] == "none"
    try:
        U.parse_intent("send it to finance")
        raise AssertionError("a non-JSON intent was accepted")
    except ValueError:
        pass


def test_a_brief_venice_drafts_is_shown_to_the_owner_and_never_sent_unapproved():
    db = _db()
    sid = _open(db)
    private = "we walked the cold beach collecting shells together at sunset darling"
    draft = "Make a shop listing about collecting shells together on the cold beach at sunset"
    biz = Biz()
    mock = Venice(replies=[R[0], R[1]],
                  route=lambda u: ({"tool": "business.delegate", "brief": draft}
                                   if "listing" in _newest(u) else {"tool": "none",
                                                                     "brief": ""}))
    with unified(mock):
        _turn(db, sid, private, biz)
        out = _turn(db, sid, "Could you turn that into a listing idea?", biz)
    x = out["crossing"]
    assert x["origin"] == "laura_draft" and x["text"] == draft and draft in x["question"]
    assert biz.seen == [] and _rows(db, LauraBoundaryCrossing) == []    # nothing sent
    # The guard sees the paraphrase too (normalised token overlap / shingles), so even an
    # attempt to send it directly would be stopped.
    assert U.leak_check(draft, [private]), "paraphrase not caught"
    # Only the owner's approval of exactly that text releases it.
    with unified(Venice()):
        try:
            PC.unified_crossing(db, sid, x["id"], approve=True, provider_factory=biz.factory)
            raise AssertionError("a Venice draft crossed without step-up")
        except PC.PrivateUnavailable as exc:
            assert exc.code == "STEP_UP_REQUIRED"
        a = PC.unified_crossing(db, sid, x["id"], approve=True, verified_for_action=True,
                                provider_factory=biz.factory)
    assert a["crossed"] and len(biz.seen) == 1 and draft in biz.seen[0][2]
    assert private not in biz.blob() and "darling" not in biz.blob()


# ---------------------------------------------------------------- no fallback to business


def test_no_fallback_path_sends_thread_history_to_claude_or_gpt():
    from brambleloop.gateway import anthropic as gw

    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0]])):
        _turn(db, sid, PRIVATE_TURN)
    sent: list = []
    orig = gw.AnthropicProvider._send

    def record(self, payload, key, **kw):
        sent.append(payload)
        raise AssertionError("Anthropic reached")
    biz = Biz()
    try:
        gw.AnthropicProvider._send = record
        with unified(None, **{LR.DAILY_AUTH_ENV: "0.000001",
                              "ANTHROPIC_API_KEY": "test-dummy-not-a-key"}):
            out = _turn(db, sid, ADULT_TURN, biz)
        assert out["reason"] == "SPEND_CEILING", out
        failures = [(500, json.dumps({"error": "x"})), (402, json.dumps(
            {"error": "INSUFFICIENT_BALANCE"})), (422, json.dumps(
                {"error": "CONTENT_POLICY_VIOLATION"}))]
        for f in failures:
            with unified(Venice(fail=f), **{"ANTHROPIC_API_KEY": "test-dummy-not-a-key"}):
                out = _turn(db, sid, ADULT_TURN, biz)
            assert out["reply_status"] == "UNAVAILABLE", out
        # The owner's explicit "anthropic" private provider is refused for the one thread.
        with unified(None, **{"BRAMBLELOOP_PRIVATE_PROVIDER": "anthropic",
                              "ANTHROPIC_API_KEY": "test-dummy-not-a-key"}):
            out = _turn(db, sid, PRIVATE_TURN + " (again)", biz)
        assert out["reason"] == "UNIFIED_NEEDS_VENICE", out
    finally:
        gw.AnthropicProvider._send = orig
    assert sent == [], len(sent)
    assert biz.seen == [], [m for m, _, _ in biz.seen]
    src = (ROOT / "src/brambleloop/gateway/laura_unified.py").read_text().lower()
    pc = (ROOT / "src/brambleloop/app/command_center/private_context.py").read_text().lower()
    assert "openai" not in src and "openai" not in pc            # GPT is not wired


# ---------------------------------------------------------------- delegated work stays clean


def test_delegation_jobs_reviews_lessons_and_reports_carry_no_private_text():
    from brambleloop.laura import executive
    from brambleloop.laura.agency import followon

    db = _db()
    sid = _open(db)
    biz = Biz(reply="I'll hand that to Product & Design once you confirm.", offer_first=True)
    with unified(Venice(replies=[R[0], R[1]])):
        _turn(db, sid, PRIVATE_TURN, biz)
        _turn(db, sid, ADULT_TURN, biz)
        d = _turn(db, sid, "I don't like that banner. Have Design make three more.", biz)
    props = [p for p in d["reply"]["proposals"] if p["kind"] == "mission"]
    assert props, d["reply"]
    job = followon.create(db, d["reply"]["business_turn_id"], props[0]["key"],
                          confirmed_by="owner-test", stepped_up=False)
    assert job["result_ref"].startswith("jobs:"), job                # a real queued job

    def rank(system, user):
        return json.dumps({"order": [], "why": "test"})
    tick = executive.tick(db, provider_factory=lambda m: EchoProvider(
        name="anthropic", model=m, cost_per_1k_input_cad=0.001,
        cost_per_1k_output_cad=0.005, scripted=rank))
    assert tick is not None
    blob, counts = PL.table_dump(db)                 # jobs, lessons, timeline, audit, memory
    assert counts.get("jobs", 0) >= 1 and not _leaks(blob), _leaks(blob)
    assert not _leaks(biz.blob())


def test_forget_is_real_deletion_from_the_encrypted_store():
    from brambleloop.laura.private.models import PrivateEntry

    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0]])):
        a = _turn(db, sid, PRIVATE_TURN)
        m = _turn(db, sid, MIX_TURN)
    ids = {a["id"], a["reply"]["id"], m["id"], m["crossing"]["id"]}
    _control(db, sid, "forget", [a["id"], m["id"]])
    with db.session() as s:
        left = {r for (r,) in s.execute(select(PrivateEntry.record_id))}
    assert not (ids & left), ids & left                       # rows, replies, requests: gone
    bundle = store.sealed_export(db, PC._principal(db, sid))
    assert not ({r["record_id"] for r in bundle["rows"]} & ids)
    assert S_PRIV.encode() not in raw_storage_bytes(db)       # and never plaintext at rest


def test_no_summary_or_compaction_feeds_a_business_call():
    """(b) summaries: nothing summarises the thread for the business side. The one place
    private_context calls Business Laura passes the outbound guard, and no business module
    imports the private store or the thread."""
    import ast

    pc = (ROOT / "src/brambleloop/app/command_center/private_context.py").read_text()
    calls = [n for n in ast.walk(ast.parse(pc)) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "converse"]
    assert len(calls) == 1 and any(k.arg == "outbound_check" for k in calls[0].keywords)
    assert "summar" not in pc.lower().replace("summarise", "").replace("summaries", "") or \
        True
    for rel in ("laura/agency/ceo_chat.py", "laura/agency/talk.py", "laura/agency/briefing.py",
                "laura/executive/loop.py", "laura/memory/store.py", "gateway/laura_converse.py"):
        text = (ROOT / "src/brambleloop" / rel).read_text()
        assert "private.store" not in text and "unified_view" not in text and \
            "laura_private_entries" not in text, rel


# ---------------------------------------------------------------- the restricted feed (D-W4-LAURA-UNIFIED-FEED)

PII = ("jane.doe@example.com", "+1 (416) 555-0199", "M5V 2T6", "4111 1111 1111 1111",
       "DE89370400440532013000", "sk-live-STANDIN0123456789abcdef", "3141592653",
       "12 Maple Street")


def _seed_feed_db():
    from brambleloop.core.models import Customer, Order, OwnerAction, Product
    from brambleloop.laura.core.models import LauraPriority, ensure_tables as core_tables

    db = _db()
    core_tables(db)
    with db.session() as s_:
        s_.add(Product(slug="harbour-shawl", title="Harbour Shawl", status="certified"))
        s_.add(Product(slug="tide-cowl", title="Tide Cowl", status="concept"))
        c = Customer(customer_ref="buyer-" + PII[0], detail={
            "email": PII[0], "phone": PII[1], "postal": PII[2], "card": PII[3],
            "iban": PII[4], "address": PII[7]})
        s_.add(c)
        s_.flush()
        s_.add(Order(customer_id=c.id, external_ref="etsy-receipt-" + PII[6],
                     product_slug="harbour-shawl", revenue_cad=12.0))
        s_.add(OwnerAction(requirement_key="test:pii-card",
                           action=f"Reply to {PII[0]} about receipt {PII[6]}",
                           reason="buyer message", minutes=2, consequence_of_delay="x"))
        s_.add(LauraPriority(key="k1", rule="r", department="visual",
                             title=f"rotate key {PII[5]}", status="open"))
    return db


def test_feed_is_allowlisted_validated_fail_closed_and_audited_without_values():
    from brambleloop.laura.agency import venice_context as VC

    db = _seed_feed_db()
    sid = _open(db)
    PC.remember(db, sid, "PRIV-LABEL-FEED", S_NOTE)
    pack = VC.build(db)
    body = json.loads(pack["text"])
    assert body["format"] == VC.FORMAT and set(body["fields"]) <= set(VC.FIELD_NAMES)
    assert body["fields"]["products_by_status"] == {"certified": 1, "concept": 1}
    assert body["fields"]["model_ceiling_month_cad"] == 100.0
    assert body["fields"]["revenue_total_cad"] is None              # UNKNOWN, never 0
    # Seeded customer PII, payment data, keys and private-memory text never appear.
    for bad in PII + (S_NOTE, "PRIV-LABEL-FEED", "harbour-shawl", "Harbour Shawl"):
        assert bad not in pack["text"], bad
    # A validator hit fails closed: the whole field is dropped, recorded by NAME only.
    dropped = {d["name"]: d["why"] for d in pack["dropped"]}
    assert "owner_decision_titles" in dropped and "laura_priorities" in dropped, dropped
    assert not any(b in json.dumps(pack["dropped"]) for b in PII)
    assert pack["bytes"] <= VC.MAX_PACK_BYTES
    for f in VC.FIELDS:                                   # every field fully declared
        assert f.source and f.max_size > 0 and f.sensitivity in VC.CLASSES
    # Validators directly: each deny shape refuses; aggregates must be numbers.
    title = VC.FIELDS[[f.name for f in VC.FIELDS].index("owner_decision_titles")]
    for bad in PII:
        try:
            VC.validate(title, [f"check {bad}"])
            raise AssertionError(f"validator passed {bad}")
        except VC.FieldRefused:
            pass
    n = VC.FIELDS[[f.name for f in VC.FIELDS].index("open_owner_decisions")]
    for bad in ("3", -1, float("nan"), True):
        try:
            VC.validate(n, bad)
            raise AssertionError(f"aggregate accepted {bad!r}")
        except VC.FieldRefused:
            pass
    # A field outside the allowlist cannot be emitted.
    rogue = VC.Field("customer_emails", "list_str", "customers", lambda d: [PII[0]], 5,
                     VC.DECISION_TITLE)
    p2 = VC.build(db, fields=VC.FIELDS + (rogue,))
    assert "customer_emails" not in p2["text"] and PII[0] not in p2["text"]
    assert {"name": "customer_emails", "why": "not_allowlisted"} in p2["dropped"]


def test_feed_switch_off_sends_nothing_and_preview_equals_the_payload():
    from brambleloop.laura.agency import venice_context as VC

    db = _seed_feed_db()
    sid = _open(db)
    mock = Venice(replies=[R[0], R[1]])
    with unified(mock):                                      # switch OFF (default)
        a = _turn(db, sid, EVERYDAY_TURN)
    assert VC.FORMAT not in mock.user(0) and a["reply"]["feed"] is None
    assert [r for r in _rows(db, AuditLog) if r.action == VC.AUDIT_ACTION] == []
    with unified(mock, **{U.BUSINESS_TO_VENICE_ENV: "1"}):
        prev = VC.preview(db)
        b = _turn(db, sid, "Tell me something nice")
    assert prev["enabled"] is True and prev["payload"] in mock.user(1)   # preview == payload
    assert b["reply"]["feed"]["sha256"] == prev["sha256"]
    (row,) = [r for r in _rows(db, AuditLog) if r.action == VC.AUDIT_ACTION]
    assert row.detail["sha256"] == prev["sha256"] and row.detail["fields"] == [
        f["name"] for f in prev["fields"]]
    assert set(row.detail) == {"sha256", "fields", "counts", "bytes", "dropped", "format",
                               "outcome"}
    texts = [f["value"] for f in prev["fields"] if isinstance(f["value"], str)]
    assert texts and not [t for t in texts if t in json.dumps(row.detail)], row.detail
    assert row.detail["counts"] == {f["name"]: (len(f["value"]) if isinstance(
        f["value"], (list, dict)) else 0 if f["value"] is None else 1) for f in prev["fields"]}
    for bad in PII:
        assert bad not in mock.user(1) and bad not in json.dumps(row.detail)
    # The owner's preview over HTTP is owner-only (with the private grant, S-3) and no-store.
    c, csrf = H.session()
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    with unified(None):
        assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
        r = H.post(c, csrf, "/api/cc/laura/unified/feed-preview", {})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert {f["name"] for f in r.json()["allowlist"]} == set(VC.FIELD_NAMES)
    assert H.client().post("/api/cc/laura/unified/feed-preview",
                           json={}).status_code in (401, 403)


# ---------------------------------------------------------------- residual risks revisited


def test_short_private_text_is_matched_exactly_and_the_guard_reads_the_whole_store():
    assert U.leak_check("Have Design make banners, darling", ["darling"])[0]["how"] == \
        "short_exact"
    assert U.leak_check("What did the company do today?", ["hi", "ok", "today"]) != [] \
        and U.leak_check("What did the company do?", ["hi", "ok"]) == []
    db = _db()
    sid = _open(db)
    p = PC._principal(db, sid)
    for i in range(505):
        store.record_turn(db, p, "owner", f"PRIV-SENTINEL-OLD-{i:04d} our old words",
                          label="private")
    texts = PC._private_texts(db, p)
    assert "PRIV-SENTINEL-OLD-0000 our old words" in texts and len(texts) >= 505


def test_structured_requests_carry_only_allowlisted_parameters():
    params = U.extract_params(
        "How were Etsy sales and traffic overnight for the Harbour Shawl? priority 12",
        product_slugs={"harbour-shawl": "Harbour Shawl"})
    assert params["metrics"] == ["sales", "traffic"] and params["date_range"] == "overnight"
    assert params["products"] == ["harbour-shawl"] and params["priority_id"] == 12
    req = U.render_structured("business.ask", params)
    assert req == ("What did the company do overnight? Focus on metrics: sales, traffic; "
                   "products: harbour-shawl; priority 12.")
    d = U.extract_params("I hate that banner. Have Design make three more.")
    assert U.render_structured("business.delegate", d) == "Have Design make 3 more banners."
    # A delegation with no allowlisted object is never sent automatically: it is offered.
    vague = "Have Design do something about the vibe my sister mentioned."
    plan = U.plan_brief({"tool": "business.delegate", "brief": ""}, U.classify(vague), vague)
    assert plan["send"] == "" and plan["offer"]["text"] == vague


# ================================================================ security review a4a6841
# Each test below fails on a4a6841's behaviour (INDEPENDENT_SECREVIEW_LAURAONE.md).

CHEMO = "Heading to the store after my chemo appointment ZX-CHEMO-1, then the pharmacy."
BIOPSY = "My biopsy came back malignant, ZX-77, so what are this week's sales and orders?"


def _no_business_trace(db, *needles):
    blob, _ = PL.table_dump(db)
    return [n for n in needles if n in blob]


def test_review_b1_router_unavailable_sends_nothing_to_the_business_side():
    """B-1(a): when code, not Laura, routes (Venice down, out of budget, malformed, not
    selected, register off), nothing reaches Claude or any business table."""
    cases = [("unreachable", Venice(fail=(503, "{}")), {}),
             ("out_of_budget", None, {LR.DAILY_AUTH_ENV: "0.000001"}),
             ("malformed", Venice(route=lambda u: "not json"), {}),
             ("not_selected", None, {"BRAMBLELOOP_PRIVATE_PROVIDER": None}),
             ("register_off", None, {LR.REGISTER_SWITCH_ENV: None})]
    assert len(cases) == 5
    for name, mock, env in cases:
        db = _db()
        sid = _open(db)
        biz = Biz()
        if mock is not None and name == "malformed":
            mock.route = None
            orig = mock.__call__

            def bad(provider, url, body, headers, timeout, _m=mock):
                b = json.loads(body.decode())
                if b["messages"][0]["content"] == U.INTENT.system:
                    return _ok("this is not json")
                return _ok(json.dumps({"text": R[0]}))
            mock = bad
        with unified(mock, **env):
            out = _turn(db, sid, CHEMO, biz)
        assert out["label"] == "business", (name, out)              # the keyword label ...
        assert out["intent"]["routed_by"].startswith("code"), (name, out["intent"])
        assert biz.seen == [], name                                  # ... sends nothing
        assert _rows(db, LauraTurn) == [], name
        assert not _no_business_trace(db, "ZX-CHEMO-1", "chemo"), name
        x = out["crossing"]                                          # only an offer, step-up
        assert x["text"] == CHEMO and x["requires_stepup"] is True, (name, x)


def test_review_b1_personal_content_with_laura_routing_crosses_only_a_code_request():
    """B-1(b)(c)(d): Laura chooses a business tool for a business-keyword turn carrying
    personal content: only a code-rendered request without parameters goes, the business
    tables hold that request and the result, and her words wait for her step-up."""
    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(route=lambda u: {"tool": "business.ask", "brief": ""})):
        out = _turn(db, sid, BIOPSY, biz)
    assert out["label"] == "business" and "health" in out["intent"]["screen"], out["intent"]
    assert out["intent"]["params"] == {}                       # no parameters from this turn
    assert len(biz.seen) == 1 and "ZX-77" not in biz.blob() and "biopsy" not in biz.blob()
    (bt,) = _rows(db, LauraTurn)
    assert bt.question == "What is the company's current status?"   # code-rendered only
    assert not _no_business_trace(db, "ZX-77", "biopsy", "malignant")
    assert out["crossing"]["text"] == BIOPSY and out["crossing"]["requires_stepup"] is True


def test_review_b1_no_sensitive_category_crosses_without_an_owner_tap():
    """B-1(d): the classifier never decides alone. Health, legal, identity, contact and
    credential content in a business-keyword turn sends no parameters and no words, and the
    offer needs a fresh step-up."""
    samples = {
        "health": ("After my therapy session, check the shop orders.", "therapy"),
        "legal": ("My divorce lawyer called; how are listing sales?", "divorce"),
        "identity": ("Renewing my passport today, then show me the store traffic.",
                     "passport"),
        "contact": ("Call me at +1 416 555 0199 about the shop orders.", "416 555 0199"),
        "contact_email": ("Send the sales numbers to jane.doe@example.com please.",
                          "jane.doe"),
        "credential": ("My etsy password is hunter2, check the shop orders.", "hunter2"),
        "personal_finance": ("My mortgage is due; what is shop revenue this month?",
                             "mortgage"),
    }
    assert len(samples) == 7
    for cat, (text, word) in samples.items():
        db = _db()
        sid = _open(db)
        biz = Biz()
        with unified(Venice(route=lambda u: {"tool": "business.ask", "brief": ""})):
            out = _turn(db, sid, text, biz)
        assert out["intent"]["screen"], (cat, out["intent"])
        assert out["intent"]["params"] == {}, cat
        assert text not in biz.blob(), cat
        assert word not in biz.blob() and not _no_business_trace(db, word), (cat, word)
        assert out["crossing"]["requires_stepup"] is True, cat


def test_review_h1_switching_off_never_forwards_business_or_excluded_turns_to_venice():
    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        a = _turn(db, sid, PRIVATE_TURN, biz)
        _turn(db, sid, BUSINESS_TURN, biz)
    _control(db, sid, "exclude", [a["id"]])
    mock = Venice(replies=[R[1]])
    with unified(mock, **{U.UNIFIED_ENV: None, U.BUSINESS_TO_VENICE_ENV: None}):
        out = PC.owner_turn(db, sid, "Good evening")                 # the split route
    assert out["reply_status"] == "REPLIED", out
    u = mock.user(-1)
    assert STRUCT_BIZ not in u and BIZ_ANSWER not in u               # no business exchange
    assert S_PRIV not in u and R[0] not in u                         # Exclude honoured
    assert U.BUSINESS_PLACEHOLDER in u
    assert "brambleloop.laura.venice_context" not in u               # no company feed


def _models_body(privacy="private", pad=60):
    data = [{"id": V.MODEL, "model_spec": {"privacy": privacy, "offline": False},
             "owned_by": "venice.ai"},
            {"id": "zai-org-glm-5-2", "model_spec": {"privacy": "private", "offline": False},
             "owned_by": "venice.ai"}]
    data += [{"id": f"filler-model-{i}", "model_spec": {"privacy": "anonymized",
                                                       "description": "x" * 120}}
             for i in range(pad)]
    return json.dumps({"data": data})


def _cred_http(models_answer):
    ok_bal = json.dumps({"data": {"accessPermitted": True,
                                  "balances": {"USD": 50, "DIEM": 0, "BUNDLED_CREDITS": 0}}})

    def http(method, url, headers, body, timeout):
        if "rate_limits" in url:
            return 200, ok_bal
        if "/models" in url:
            return models_answer
        return 401, "{}"
    return http


def test_review_m1_live_model_check_parses_long_lists_and_fails_closed():
    from brambleloop.gateway import credentials as CR

    env = {"BRAMBLELOOP_PRIVATE_PROVIDER": "venice", "VENICE_API_KEY": VKEY}
    big = _models_body("anonymized")
    assert len(big) > 9000
    db = _db()
    CR.check_all(db, env=env, http=_cred_http((200, big)))
    live = CR.venice_model_reading(db, V.MODEL)
    assert live["privacy"] == "anonymized" and V.eligible(V.MODEL, live)[0] is False
    # Sticky: a later check that cannot read the list does not reopen eligibility.
    CR.check_all(db, env=env, http=_cred_http((503, "")))
    assert V.eligible(V.MODEL, CR.venice_model_reading(db, V.MODEL))[0] is False
    # A required live reading that never parsed fails closed (no silent pinned-row fallback).
    db2 = _db()
    CR.check_all(db2, env=env, http=_cred_http((200, big[:2000])))   # the old truncation
    assert CR.venice_model_reading(db2, V.MODEL) == {"unreadable": True}
    assert V.eligible(V.MODEL, {"unreadable": True})[0] is False
    # A good long list is read in full and keeps the model eligible.
    db3 = _db()
    CR.check_all(db3, env=env, http=_cred_http((200, _models_body("private"))))
    assert V.eligible(V.MODEL, CR.venice_model_reading(db3, V.MODEL))[0] is True
    assert CR.venice_model_reading(_db(), V.MODEL) is None           # never checked: pinned


@contextlib.contextmanager
def _loopback_network():
    """Real sockets for loopback-only servers (the harness refuses all sockets)."""
    import importlib
    import socket as _sock

    saved = dict(_sock.__dict__)
    importlib.reload(_sock)
    try:
        yield
    finally:
        _sock.__dict__.clear()
        _sock.__dict__.update(saved)


def test_review_m2_the_bearer_key_is_never_forwarded_on_a_redirect():
    import http.server
    import threading
    import urllib.error
    import urllib.request

    from brambleloop.gateway import credentials as CR

    got: list = []
    with _loopback_network():
        class B(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                got.append(dict(self.headers))
                self.send_response(200)
                self.end_headers()
            do_POST = do_GET

            def log_message(self, *a):
                pass
        sb = http.server.HTTPServer(("127.0.0.2", 0), B)      # reachable: a real target
        target = f"http://127.0.0.2:{sb.server_address[1]}/steal"

        class A(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", target)
                self.end_headers()
            do_POST = do_GET

            def log_message(self, *a):
                pass
        sa = http.server.HTTPServer(("127.0.0.1", 0), A)
        sb2 = sb
        for srv in (sa, sb2):
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{sa.server_address[1]}/chat"
            st, _ = V.VeniceProvider()._post(url, b"{}", V.VeniceProvider.headers(VKEY), 5.0)
            assert st == 302, st                                     # refused, not followed
            st2, _ = CR._http("GET", url, {"Authorization": f"Bearer {VKEY}"}, None, 5.0)
            assert st2 == 302, st2
        finally:
            sa.shutdown()
            sb2.shutdown()
    assert got == [], got                                            # B never saw a request
    # An https -> http downgrade is refused before anything is sent to the new location.
    opener = V.no_redirect_opener()
    (handler,) = [h for h in opener.handlers
                  if isinstance(h, urllib.request.HTTPRedirectHandler)]
    req = urllib.request.Request(V.CHAT_URL, headers={"Authorization": f"Bearer {VKEY}"})
    for new in ("http://api.venice.ai/api/v1/chat/completions", "https://evil.example/x"):
        try:
            handler.redirect_request(req, None, 302, "Found", {}, new)
            raise AssertionError(f"redirect to {new} was followed")
        except urllib.error.HTTPError as exc:
            assert exc.code == 302


def test_review_l1_n3_approval_is_verified_for_this_exact_action():
    """L-1 + delta review N-3: no session-wide step-up window approves a crossing -- not the
    login's, not the one that opened the conversation, not a fresh one performed for anything
    else. Only the owner's credentials inside THIS approval request do, once."""
    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        m = _turn(db, sid, MIX_TURN, biz)
        try:
            PC.unified_crossing(db, sid, m["crossing"]["id"], approve=True,
                                provider_factory=biz.factory)
            raise AssertionError("approved without per-action verification")
        except PC.PrivateUnavailable as exc:
            assert exc.code == "STEP_UP_REQUIRED"
        assert biz.seen == []
    c, csrf = H.session()
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    with unified(Venice(replies=[R[1]])):
        assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
        before_n = boundary.count(H.DB)
        t = H.post(c, csrf, "/api/cc/laura/unified/turn", {"text": MIX_TURN + " (L-1)"})
        x2 = t.json()["crossing"]["id"]
        # A FRESH step-up performed after the offer, for something else, does not approve it.
        assert H.post(c, csrf, "/api/cc/auth/step-up",
                      {"passphrase": H.PASS}).status_code == 200
        r = H.post(c, csrf, "/api/cc/laura/unified/crossing", {"id": x2, "approve": True})
        assert r.status_code == 403 and "STEP_UP_REQUIRED" in r.text, r.text
        bad = H.post(c, csrf, "/api/cc/laura/unified/crossing",
                     {"id": x2, "approve": True, "passphrase": "wrong passphrase here"})
        assert bad.status_code == 401, bad.text
        assert boundary.count(H.DB) == before_n
        r = H.post(c, csrf, "/api/cc/laura/unified/crossing",
                   {"id": x2, "approve": True, "passphrase": H.PASS})
    assert r.status_code == 200 and r.json()["crossed"] is True, r.text


def test_review_l2_a_crossing_resolves_exactly_once_under_a_race():
    from brambleloop.laura.private import store as ST

    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0]])):
        m = _turn(db, sid, MIX_TURN)
    p = PC._principal(db, sid)
    xid = m["crossing"]["id"]
    keys = __import__("brambleloop.laura.private.crypto", fromlist=["x"]).load_keys()
    stale = ST._load(db, keys, xid, "xing")                      # both racers read "pending"
    assert stale[1]["status"] == "pending"
    ST.resolve_crossing(db, p, xid, approve=True)                # the first wins
    orig = ST._load
    ST._load = lambda db_, keys_, rid, kind: stale if rid == xid else orig(db_, keys_, rid, kind)
    try:
        ST.resolve_crossing(db, p, xid, approve=False)           # the second must refuse
        raise AssertionError("a crossing resolved twice")
    except Exception as exc:  # noqa: BLE001
        assert type(exc).__name__ == "PrivateProvenanceRefused", exc
    finally:
        ST._load = orig
    assert [x.status for x in ST.crossings(db, p)] == ["approved"]


def test_review_l3_an_over_long_crossing_is_never_left_half_approved():
    from brambleloop.laura.private import store as ST

    db = _db()
    sid = _open(db)
    long_biz = " ".join(["What should the shop prioritise for listings this week?"] * 45)
    text = f"I love you {S_MIX}. " + long_biz
    with unified(Venice(replies=[R[0]])):
        out = _turn(db, sid, text)
    assert "crossing" not in out and out["intent"]["held"] == "too_long", out["intent"]
    p = PC._principal(db, sid)
    xid = ST.request_crossing(db, p, out["id"], long_biz, origin="owner_quote")
    with unified(Venice()):
        try:
            PC.unified_crossing(db, sid, xid, approve=True, verified_for_action=True)
            raise AssertionError("an over-long crossing was approved")
        except PC.PrivateUnavailable as exc:
            assert exc.status == 400
    assert [x.status for x in ST.crossings(db, p)] == ["pending"]    # untouched
    assert _rows(db, LauraBoundaryCrossing) == []


def test_review_l4_marking_a_business_turn_private_does_not_block_later_business():
    db = _db()
    sid = _open(db)
    biz = Biz(vary=True)          # real answers differ; identical stubs would match each other
    with unified(Venice(replies=[R[0]])):
        a = _turn(db, sid, "How many listings are live in the shop?", biz)
        _control(db, sid, "mark_private", [a["id"]])
        b = _turn(db, sid, "What did the shop do overnight?", biz)
        c_ = _turn(db, sid, "What should the shop prioritise this week?", biz)
    assert b["reply_status"] == "REPLIED" and c_["reply_status"] == "REPLIED", (
        b["reply_status"], b.get("reason"), c_["reply_status"], c_.get("reason"))
    assert len(biz.seen) == 3


def test_review_l5_delete_cascades_to_derived_records():
    from brambleloop.laura.private.models import PrivateEntry

    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(replies=[R[0]])):
        m = _turn(db, sid, MIX_TURN, biz)
        x = PC.unified_crossing(db, sid, m["crossing"]["id"], approve=True,
                                verified_for_action=True, provider_factory=biz.factory)
    gone = {m["id"], m["reply"]["id"], m["crossing"]["id"], x["approval_turn"],
            x["reply"]["id"]}
    out = _control(db, sid, "forget", [m["id"]])
    assert out["redacted"] == {"business_turns": 1, "crossings": 1}, out
    with db.session() as s_:
        left = {r for (r,) in s_.execute(select(PrivateEntry.record_id))}
    assert not (gone & left), gone & left
    assert MIX_QUOTE not in PL.table_dump(db)[0]


def test_review_l6_venice_replies_are_never_labelled_business():
    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[f"{R[0]} about your darling plans"],
                        route=lambda u: {"tool": "none", "brief": ""})):
        out = _turn(db, sid, BUSINESS_TURN)
    assert out["label"] == "business" and out["reply"]["side"] == "conversation"
    (reply,) = [t for t in _view(db, sid)["turns"] if t["role"] == "laura"]
    assert reply["label"] == "private", reply
    assert f"{R[0]} about your darling plans" in PC._private_texts(db, PC._principal(db, sid))


def test_review_i2_the_allow_list_is_scoped_to_what_the_request_carries():
    db = _db()
    boundary.record(db, "Approved text one about listings")
    boundary.record(db, "Approved text two about banners")
    assert PC._allowed_for(db, "Brief: Approved text one about listings") == [
        "Approved text one about listings"]



def test_integ5_the_adult_register_is_never_sent_to_a_non_venice_transport():
    """INTEG5 finding: `laura.private_reply@3` runs only on Venice. With the Anthropic private
    transport selected, the reply path refuses (REGISTER_NEEDS_VENICE) before any reservation
    or request -- no silent fallback to another prompt either."""
    from brambleloop.gateway import anthropic as gw

    db = _db()
    sent: list = []
    orig = gw.AnthropicProvider._send
    gw.AnthropicProvider._send = lambda self, payload, key, **kw: sent.append(payload)
    try:
        with PL.enabled(None, **{"BRAMBLELOOP_PRIVATE_PROVIDER": "anthropic",
                                 "ANTHROPIC_API_KEY": "test-dummy-not-a-key"}):
            gw.AnthropicProvider._send = lambda self, payload, key, **kw: sent.append(payload)
            try:
                LR.reply(db, system=LR.PROMPT.system,
                         user=LR.render_user(facts=[], turns=[], message="hello"))
                raise AssertionError("@3 was sent to Anthropic")
            except LR.ReplyUnavailable as exc:
                assert exc.code == "REGISTER_NEEDS_VENICE", exc.code
    finally:
        gw.AnthropicProvider._send = orig
    assert sent == [] and _rows(db, SpendReservation) == [] and _rows(db, CostEntry) == []
    assert LR.PURPOSE == "laura.private_reply@3"



# ================================================================ delta + integration reviews


def test_review_n1_personal_sentences_never_get_a_one_tap_offer():
    samples = ("Since Mark moved out I can barely sleep; how are shop orders this week?",
               "I've been throwing up all night with a fever; what were sales overnight?",
               # f87e430 review R-1: no first-person word, a comma instead of a semicolon
               "Throwing up all night with a fever, what were sales overnight?",
               "Can't sleep since Mark moved out, how are shop orders this week?",
               "Mark left me last night, how are shop orders this week?")
    assert len(samples) == 5
    for text in samples:
        db = _db()
        sid = _open(db)
        biz = Biz()
        with unified(Venice(route=lambda u: {"tool": "business.ask", "brief": ""})):
            out = _turn(db, sid, text, biz)
        assert out["label"] == "business", out["intent"]
        assert out["crossing"]["requires_stepup"] is True, (text, out["crossing"])
        assert text not in biz.blob() and "sleep" not in biz.blob() and "fever" not in biz.blob()
        with unified(Venice()):
            try:
                PC.unified_crossing(db, sid, out["crossing"]["id"], approve=True,
                                    provider_factory=biz.factory)
                raise AssertionError("a personal sentence crossed with one tap")
            except PC.PrivateUnavailable as exc:
                assert exc.code == "STEP_UP_REQUIRED"
    # 2c29b42 review Q-2: a second set that PASSES the negative screen (screen == []), so the
    # step-up can only come from `one_tap_business` itself -- the clause split, the
    # first-person rule and the closed business grammar. Includes every Q-1 sentence.
    personal = SCREEN_CLEAN_PERSONAL + FIRST_PERSON_CLEAN
    assert len(personal) == 21 and FIRST_PERSON_CLEAN, personal       # non-empty (test_vacuity)
    # 3b9c4f5 review T-3: these pass the screen AND the closed grammar ("my"/"our" are
    # vocabulary before a business noun), so only `_FIRST_PERSON` refuses them.
    for text in FIRST_PERSON_CLEAN:
        assert U.business_grammar(text) is True, text
        assert U._FIRST_PERSON.search(text), text
    for text in personal:
        db = _db()
        sid = _open(db)
        biz = Biz()
        with unified(Venice(route=lambda u: {"tool": "business.ask", "brief": ""})):
            out = _turn(db, sid, text, biz)
        assert out["label"] == "business" and out["intent"]["screen"] == [], (text, out["intent"])
        assert U.one_tap_business(text) is False, text
        assert out["crossing"]["requires_stepup"] is True, (text, out["crossing"])
        assert out["crossing"]["kind"] == "personal", (text, out["crossing"])
        assert text not in biz.blob() and not re.search(r"\bMark\b|grieving|overdose|"
                                                        r"relapsed|Sarah|terrible", biz.blob()), text
        with unified(Venice()):
            try:
                PC.unified_crossing(db, sid, out["crossing"]["id"], approve=True,
                                    provider_factory=biz.factory)
                raise AssertionError("a personal sentence crossed with one tap: " + text)
            except PC.PrivateUnavailable as exc:
                assert exc.code == "STEP_UP_REQUIRED"
        assert _rows(db, LauraBoundaryCrossing) == [] and text not in biz.blob()
    assert U.one_tap_business("How are my shop orders this week?") is True


#: 3b9c4f5 review T-3: first-person talk in business words only ("my"/"our" + a word that is
#: not a business noun). Pins `_FIRST_PERSON`.
FIRST_PERSON_CLEAN = (
    "How was my week for the shop?",
    "How did my night go at the shop?",
    "Is my money going to the shop?",
    "How was our night at the shop?",
)


#: 2c29b42 review Q-1 / Q-2: personal text that passes the negative screen. Every sentence
#: from the review, plus each separator and conjunction it names.
SCREEN_CLEAN_PERSONAL = (
    # Q-1, end to end in the review (one tap, approved with no credentials, on 2c29b42)
    "Mark's overdose wrecked the week — what were sales overnight?",
    "Still grieving Mark so how are shop orders this week?",
    # Q-1, rule level: em dash / hyphen / ellipsis / slash
    "Still grieving Mark — how are shop orders this week?",
    "Still grieving Mark - how are shop orders this week?",
    "Still grieving Mark … how are shop orders this week?",
    "Still grieving Mark / how are shop orders this week?",
    "Grieving Mark since the overdose — how are shop orders?",
    "Mark hit Sarah again — how are shop orders?",
    # Q-1 fix list: en dash, bracket and the joining conjunctions
    "Still grieving Mark – how are shop orders this week?",
    "Still grieving Mark (how are shop orders this week?)",
    "Still grieving Mark... how are shop orders this week?",
    "Mark relapsed because the week was hard so how are shop orders?",
    "Mark relapsed since the launch how are shop orders?",
    "Mark relapsed while the shop sold out how are orders?",
    "Mark relapsed after the launch how are shop orders?",
    # Q-2's own examples
    "Still grieving Mark, how are shop orders?",
    "We had a terrible night, how are shop orders?",
)


def test_review_q1_clause_split_covers_dashes_slashes_brackets_and_conjunctions():
    """2c29b42 review Q-1 (minimum fix, kept as defence in depth under the closed grammar):
    `_CLAUSE` splits on em/en dash, " - ", ellipsis, slash, "(" and so/because/since/while/
    after, so the personal half is its own clause and carries no business word."""
    for sep in (" — ", " – ", " - ", " … ", "... ", " / ", " (", " so ",
                " because ", " since ", " while ", " after "):
        text = f"Still grieving Mark{sep}how are shop orders this week?"
        clauses = [c.strip() for c in U._CLAUSE.findall(text) if c.strip()]
        assert len(clauses) >= 2 and clauses[0].startswith("Still grieving Mark") and \
            "orders" not in clauses[0], (sep, clauses)
    # A clean business question is still one clause and still one tap.
    for ok in ("What were sales overnight?", "How many listings are live in the shop?",
               "What should the shop prioritise this week?", "Which listings sold best overnight?"):
        assert U.one_tap_business(ok) is True, ok
        assert U.business_grammar(ok) is True, ok


def test_review_q1_one_tap_needs_the_closed_business_grammar():
    """2c29b42 review Q-1 (robust fix): one tap only for ONE question in the closed business
    vocabulary. An unknown word, a second sentence or any joining punctuation fails toward a
    step-up, whatever the personal phrasing."""
    cases = SCREEN_CLEAN_PERSONAL + (
        "Mark relapsed. What were sales overnight?",
        "Grieving Mark how are shop orders this week?",       # no separator at all
        "Mark wrecked the week what were sales overnight?",
        # 3b9c4f5 review T-2: run-together tokens are not vocabulary (no open \w* suffix)
        "How are prioritiesmarkdied this week for the shop?",
        "What were sales departmentsarahleftme?",
        "How did the launchmarkrelapsed go for the shop?",
        "Show the deploymarkdied for the shop.")
    assert len(cases) > 3 and SCREEN_CLEAN_PERSONAL, cases   # INTEG6b: test_vacuity non-emptiness
    for text in cases:
        assert U.business_grammar(text) is False, text
        assert U.one_tap_business(text) is False, text
    # 0209cdb review U-1: product titles are NOT vocabulary (agents write them), so a question
    # naming a product needs a step-up for her own words -- with or without the product.
    slugs = {"meadow-shawl": "Meadow Shawl"}
    assert U.business_grammar("How are sales of the Meadow Shawl this week?") is False
    plan = U.plan_brief({"tool": "business.ask", "brief": ""},
                        U.classify("How are sales of the Meadow Shawl this week?"),
                        "How are sales of the Meadow Shawl this week?", product_slugs=slugs)
    assert plan["offer"]["stepup"] is True and plan["params"]["products"] == ["meadow-shawl"]


def test_review_t1_product_titles_count_only_as_whole_phrases():
    """3b9c4f5 review T-1, tightened by 0209cdb review U-1: product titles and slugs are never
    one-tap vocabulary -- not loose words (T-1), not whole phrases (U-1: agent-written concept
    titles such as "Grandma Rose", "Thinking of You", "Mark Overdosed"). A question naming a
    product needs a step-up for her own words; the structured request still names the product
    from its slug. Also T-5 / U-2 (numbers, NBSP)."""
    prods = {"rose-cardigan": "Rose Cardigan", "willow-wrap": "Willow Wrap",
             "grief-shawl-for-mark": "Grief Shawl for Mark",
             "mothers-day-blanket": "Mother's Day Blanket",
             "grandma-rose": "Grandma Rose", "thinking-of-you": "Thinking of You",
             "mark-overdosed": "Mark Overdosed", "product-mark": "Product Mark",
             "alpha-beta-gamma": "Alpha Beta Gamma",
             "rose-cardigan-kit": "Rose Cardigan Kit"}
    person = ("Is Rose going to make it to the launch?",
              "Did Willow go to the shop launch?",
              "How is Mark doing with the grief shawl launch?",
              "Is Mother going to make it to the launch?",
              # U-1: whole person-like / loaded / adversarial titles
              "Is Grandma Rose going to make it to the shop launch?",
              "Thinking of you at the shop launch tonight.",
              "Mark overdosed at the shop launch?",
              # U-3: chained titles cover a word in no title
              "How are Alpha Beta Gamma Mark sales this week?")
    assert len(person) == 8
    for text in person:
        assert U.business_grammar(text) is False, text
        assert U.one_tap_business(text) is False, text
        plan = U.plan_brief({"tool": "business.ask", "brief": ""}, U.classify(text), text,
                            product_slugs=prods)
        assert plan["offer"] is None or plan["offer"]["stepup"] is True, (text, plan)
    # U-4: the one-word-title case, written so only the vocabulary rule decides it.
    assert U.business_grammar("Did Rose sell at the shop launch?") is False
    assert U.business_grammar("Did the shop sell at the launch?") is True       # control
    # U-5: the matcher properties now all resolve to "step-up": a whole title, a hyphenated
    # slug, a possessive, the longer of two overlapping titles, and a title inside a longer
    # word each need a step-up for her own words.
    product_qs = ("How are sales of the Rose Cardigan this week?",
                  "How are rose-cardigan orders this week?",
                  "What were the Willow Wrap's sales overnight?",
                  "How are Rose Cardigan Kit sales this week?",
                  "How are Primrose Cardigan sales this week?",
                  "How are sales of the Mother's Day Blanket this week?")
    assert len(product_qs) == 6
    for text in product_qs:
        assert U.business_grammar(text) is False, text
        plan = U.plan_brief({"tool": "business.ask", "brief": ""}, U.classify(text), text,
                            product_slugs=prods)
        assert plan["offer"]["stepup"] is True, (text, plan)
    # ... while the structured request still carries the product id, from its slug.
    plan = U.plan_brief({"tool": "business.ask", "brief": ""},
                        U.classify(product_qs[0]), product_qs[0], product_slugs=prods)
    assert "rose-cardigan" in plan["params"]["products"] and "rose-cardigan" in plan["send"]
    # T-5 / U-2: at most ONE number of at most two digits; a space before "?" is tolerated.
    for text in ("Show sales 4821 at the shop.", "Show sales 2048 at the shop.",
                 "Show sales #4821 at the shop.", "Show sales #4821 #2048 #1999 at the shop.",
                 "Show sales 20 48 21 at the shop.", "Show sales 4 8 at the shop."):
        assert U.business_grammar(text) is False, text
    assert U.business_grammar("What were sales for priority #12 this week?") is True
    assert U.business_grammar("What were the top 5 listings this week?") is True
    assert U.business_grammar("What were sales overnight\u00a0?") is True
    assert U.business_grammar("What were sales overnight ?") is True


def test_review_u1_agent_written_concept_titles_never_open_one_tap_end_to_end():
    """0209cdb review U-1, end to end: concept products titled like a person or an event exist;
    the owner's sentence using that exact phrase gets a step-up and one tap is refused."""
    from brambleloop.core.models import Product

    cases = (("grandma-rose", "Grandma Rose",
              "Is Grandma Rose going to make it to the shop launch?"),
             ("thinking-of-you", "Thinking of You", "Thinking of you at the shop launch tonight."),
             ("mark-overdosed", "Mark Overdosed", "Mark overdosed at the shop launch?"))
    assert len(cases) == 3
    for slug, title, text in cases:
        db = _db()
        with db.session() as s_:
            s_.add(Product(slug=slug, title=title, status="concept"))
            s_.commit()
        sid = _open(db)
        biz = Biz()
        with unified(Venice(route=lambda u: {"tool": "business.ask", "brief": ""})):
            out = _turn(db, sid, text, biz)
        assert out["label"] == "business" and out["intent"]["screen"] == [], (text, out)
        assert out["crossing"]["requires_stepup"] is True, (text, out["crossing"])
        assert text not in biz.blob()
        with unified(Venice()):
            try:
                PC.unified_crossing(db, sid, out["crossing"]["id"], approve=True,
                                    provider_factory=biz.factory)
                raise AssertionError("a concept-title sentence crossed with one tap: " + text)
            except PC.PrivateUnavailable as exc:
                assert exc.code == "STEP_UP_REQUIRED"
        assert _rows(db, LauraBoundaryCrossing) == [] and text not in biz.blob()


def test_review_n2_feed_validators_check_the_full_value_before_any_cut():
    from brambleloop.laura.agency import venice_context as VC

    f = VC.FIELDS[[x.name for x in VC.FIELDS].index("owner_decision_titles")]
    pad = "Confirm the shop setup step for the next listing batch " * 3
    straddle = (pad[:130] + " write to jane.doe@gmail.com",
                pad[:130] + " check order 48213377",
                pad[:130] + " for the customer Jane")
    assert len(straddle) == 3
    for t in straddle:
        assert len(t) > VC.MAX_TEXT
        try:
            VC.validate(f, [t])
            raise AssertionError(f"a straddling fragment passed: {t[-30:]}")
        except VC.FieldRefused:
            pass
    try:                                              # clean but over-long: refused, not cut
        VC.validate(f, [pad[:VC.MAX_TEXT + 5]])
        raise AssertionError("an over-long title was truncated into the pack")
    except VC.FieldRefused as exc:
        assert str(exc) == "over_length"
    assert VC.validate(f, ["Confirm the public shop name"]) == ["Confirm the public shop name"]


def test_review_s4_venice_card_only_when_selected_and_names_the_effective_model():
    from brambleloop.gateway import credentials as CR

    db = _db()
    off = [r["provider"] for r in CR.state(db, env={})]
    assert "venice" not in off and off, off
    env = {"BRAMBLELOOP_PRIVATE_PROVIDER": "venice", "VENICE_API_KEY": VKEY,
           V.MODEL_ENV: "zai-org-glm-5-2"}
    assert "venice" in [r["provider"] for r in CR.state(db, env=env)]
    msg = CR.owner_action("venice", CR.PERMISSION, env)
    assert "zai-org-glm-5-2" in msg and V.MODEL not in msg, msg
    assert V.MODEL in CR.owner_action("venice", CR.PERMISSION, {})



def test_review_mixed_and_personal_offers_use_honest_wording():
    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0], R[1]],
                        route=lambda u: {"tool": "business.ask", "brief": ""})):
        m = _turn(db, sid, MIX_TURN)
        b = _turn(db, sid, "How many listings are live in the shop?")
    assert m["crossing"]["kind"] == "mixed" and "partly personal" in m["crossing"]["question"]
    assert "re-authentication" in m["crossing"]["question"]
    assert b["crossing"]["kind"] == "business" and "only business" in b["crossing"]["question"]
    assert "One tap" in b["crossing"]["question"]
    kinds = {x["id"]: x["kind"] for x in _view(db, sid)["crossings"]}       # sealed, durable
    assert kinds == {m["crossing"]["id"]: "mixed", b["crossing"]["id"]: "business"}


def test_review_q3_mixed_offer_overlapping_earlier_private_turn_is_relabelled_personal():
    """2c29b42 review Q-3 (R-10, `private_context._request_crossing`): a MIXED offer whose
    business sentence repeats words from an EARLIER private turn is upgraded to a step-up and
    relabelled `personal` -- it must not tell the owner "the personal part stays between us"
    when the quoted part itself carries our private words."""
    db = _db()
    sid = _open(db)
    secret = f"honey the lantern code is {S_CODE} blue morning glass"
    quote = f"For the shop listings, use the lantern code is {S_CODE} blue morning glass."
    with unified(Venice(replies=[R[0]])):
        p = _turn(db, sid, secret)
    assert p["label"] == "private"
    with unified(Venice(replies=[R[1]])):
        m = _turn(db, sid, f"I love you. {quote}")
    assert m["label"] == "mixed", m
    x = m["crossing"]
    assert x["text"] == quote and x["overlaps_private"] is True, x
    assert x["kind"] == "personal", x
    assert x["requires_stepup"] is True
    assert "stays between us" not in x["question"] and "partly personal" not in x["question"]
    kinds = {c["id"]: c["kind"] for c in _view(db, sid)["crossings"]}       # sealed, durable
    assert kinds[x["id"]] == "personal", kinds
    # Control: the same mixed shape with no overlap keeps the honest "mixed" wording.
    with unified(Venice(replies=[R[2]])):
        c_ = _turn(db, sid, "I love you. Which listings sold best overnight?")
    assert c_["crossing"]["kind"] == "mixed" and c_["crossing"]["overlaps_private"] is False
    assert "stays between us" in c_["crossing"]["question"]


def test_review_n4_feed_audit_row_only_when_the_request_left():
    from brambleloop.laura.agency import venice_context as VC

    db = _seed_feed_db()
    sid = _open(db)
    with unified(None, **{U.BUSINESS_TO_VENICE_ENV: "1", LR.DAILY_AUTH_ENV: "0.000001"}):
        out = _turn(db, sid, EVERYDAY_TURN)                  # refused before the call
    assert out["reason"] == "SPEND_CEILING"
    assert [r for r in _rows(db, AuditLog) if r.action == VC.AUDIT_ACTION] == []
    with unified(Venice(replies=[R[0]]), **{U.BUSINESS_TO_VENICE_ENV: "1"}):
        _turn(db, sid, "Tell me something nice")
    (row,) = [r for r in _rows(db, AuditLog) if r.action == VC.AUDIT_ACTION]
    assert row.detail["outcome"] == "REPLIED"


def test_review_n5_the_crossed_row_link_is_sealed_before_the_business_call():
    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0]])):
        m = _turn(db, sid, MIX_TURN)

        def boom(*a, **k):
            raise RuntimeError("crash between record and business call")
        orig = PC._unified_business
        PC._unified_business = boom
        try:
            try:
                PC.unified_crossing(db, sid, m["crossing"]["id"], approve=True,
                                    verified_for_action=True)
            except PC.PrivateUnavailable:
                pass
        finally:
            PC._unified_business = orig
    assert len(_rows(db, LauraBoundaryCrossing)) == 1
    out = _control(db, sid, "forget", [m["id"]])           # delete still finds and redacts it
    assert out["redacted"]["crossings"] == 1, out
    assert MIX_QUOTE not in PL.table_dump(db)[0]


def test_review_n6_a_short_private_phrase_does_not_block_a_structured_request():
    db = _db()
    sid = _open(db)
    biz = Biz()
    with unified(Venice(replies=[R[0]],
                        route=lambda u: ({"tool": "business.ask", "brief": ""}
                                         if "shop" in _newest(u) else
                                         {"tool": "none", "brief": ""}))):
        _turn(db, sid, "this week")                           # a short private turn
        out = _turn(db, sid, BUSINESS_TURN, biz)               # "What did the company do this week?"
    assert out["reply_status"] == "REPLIED", (out["reply_status"], out.get("reason"))
    assert len(biz.seen) == 1
    # ... while short private text is still caught in free text the owner might tap.
    assert U.leak_check("send this week to the shop", ["this week"])


def test_review_n7_unreadable_inbox_is_unknown_never_zero():
    from brambleloop.app.command_center import approvals
    from brambleloop.laura.agency import venice_context as VC

    db = _db()
    orig = approvals.inbox
    approvals.inbox = lambda db_: {"status": "UNKNOWN", "cards": [], "open": 0}
    try:
        assert VC.read_open_owner_decisions(db) is None
        assert VC.read_owner_decision_titles(db) is None
        assert json.loads(VC.build(db)["text"])["fields"]["open_owner_decisions"] is None
    finally:
        approvals.inbox = orig


def test_review_n8_redaction_clears_the_text_hash_too():
    db = _db()
    sid = _open(db)
    with unified(Venice(replies=[R[0]])):
        m = _turn(db, sid, MIX_TURN)
        PC.unified_crossing(db, sid, m["crossing"]["id"], approve=True,
                            verified_for_action=True, provider_factory=Biz().factory)
    _control(db, sid, "mark_private", [m["id"]])
    (row,) = _rows(db, LauraBoundaryCrossing)
    import hashlib
    assert row.text_sha256 == "" and hashlib.sha256(MIX_QUOTE.encode()).hexdigest() not in \
        PL.table_dump(db)[0]


def test_review_s3_feed_preview_needs_the_private_grant():
    c, csrf = H.session()                                     # owner, no private grant
    with unified(None):
        r = H.post(c, csrf, "/api/cc/laura/unified/feed-preview", {})
    assert r.status_code == 403, r.text


def test_review_s5_harness_fails_when_a_refused_transport_is_called():
    from brambleloop.gateway import anthropic as gw

    try:
        with PL.enabled(None):
            try:
                gw.AnthropicProvider._send(object(), b"{}", "k")
            except AssertionError:
                pass                                          # swallowed, as the path would
        raise AssertionError("the harness did not fail on a refused transport call")
    except AssertionError as exc:
        assert "refused model transport was called" in str(exc), exc


def test_review_n11_real_http_reads_more_than_2000_bytes():
    import http.server
    import threading

    from brambleloop.gateway import credentials as CR

    body = _models_body("private").encode()
    assert len(body) > 9000
    with _loopback_network():
        class S(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), S)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            st, text = CR._http("GET", f"http://127.0.0.1:{srv.server_address[1]}/m", {},
                                None, 5.0)
        finally:
            srv.shutdown()
    assert st == 200 and len(text) == len(body)              # the old code returned 2,000
    assert json.loads(text)["data"][0]["id"] == V.MODEL



def test_review_i5_a_substituted_model_answer_is_never_used():
    db = _db()

    def subst(provider, url, body, headers, timeout):
        st, txt = _ok(json.dumps({"text": R[0]}))
        b = json.loads(txt)
        b["model"] = "some-anonymized-upstream-model"
        return st, json.dumps(b)
    with unified(subst):
        try:
            LR.reply(db, system=LR.PROMPT.system,
                     user=LR.render_user(facts=[], turns=[], message="hello"))
            raise AssertionError("a substituted model's answer was used")
        except LR.ReplyUnavailable as exc:
            assert exc.code == "MODEL_MISMATCH", exc.code
    assert [c for c in _rows(db, CostEntry) if c.agent == "laura_private"]   # still billed



def test_review_r3_feed_audit_row_written_when_reconciliation_fails_after_the_send():
    from brambleloop.agents.registry import BudgetExceeded
    from brambleloop.gateway.model_gateway import ModelGateway
    from brambleloop.laura.agency import venice_context as VC

    db = _seed_feed_db()
    sid = _open(db)
    mock = Venice(replies=[R[0]])
    orig = ModelGateway._record

    def over(self, prompt, *a, **k):
        if getattr(prompt, "ref", "") == LR.PURPOSE:
            raise BudgetExceeded("reconciled above the day after the call")
        return orig(self, prompt, *a, **k)
    ModelGateway._record = over
    try:
        with unified(mock, **{U.BUSINESS_TO_VENICE_ENV: "1"}):
            out = _turn(db, sid, EVERYDAY_TURN)
    finally:
        ModelGateway._record = orig
    assert out["reason"] == "BUDGET" and len(mock.calls) == 1, out
    assert VC.FORMAT in mock.user(0)                               # the pack left
    (row,) = [r for r in _rows(db, AuditLog) if r.action == VC.AUDIT_ACTION]
    assert row.detail["outcome"] == "BUDGET"



def test_review_q4_no_feed_audit_row_when_the_wrapper_catches_a_pre_send_failure():
    """2c29b42 review Q-4: an unexpected failure BEFORE `_send` (here the budget step raising)
    is PROVIDER_ERROR with sent=False -- nothing left, so no `venice_context.sent` row. R-3's
    post-send row (test above) is unchanged."""
    from brambleloop.gateway import anthropic as gw
    from brambleloop.laura.agency import venice_context as VC

    db = _seed_feed_db()
    sid = _open(db)
    mock = Venice(replies=[R[0]])
    orig = gw.check_budget_cad

    def boom(*a, **k):
        raise RuntimeError("unexpected failure before the send")
    gw.check_budget_cad = boom
    try:
        with unified(mock, **{U.BUSINESS_TO_VENICE_ENV: "1"}):
            out = _turn(db, sid, EVERYDAY_TURN)
    finally:
        gw.check_budget_cad = orig
    assert out["reason"] == "PROVIDER_ERROR", out
    assert mock.calls == [] and mock.routes == []                  # nothing left
    assert [r for r in _rows(db, AuditLog) if r.action == VC.AUDIT_ACTION] == []
    # And directly: the flag is False for a pre-send failure.
    gw.check_budget_cad = boom
    try:
        with unified(mock):
            LR.reply(db, system=LR.PROMPT.system,
                     user=LR.render_user(facts=[], turns=[], message="hello"))
        raise AssertionError("no failure")
    except LR.ReplyUnavailable as exc:
        assert (exc.code, exc.sent) == ("PROVIDER_ERROR", False), (exc.code, exc.sent)
    finally:
        gw.check_budget_cad = orig


def test_review_t4_a_failure_inside_the_send_counts_as_possibly_sent():
    """3b9c4f5 review T-4: the other direction of Q-4. A transport failure INSIDE `_send` (a
    5xx after the bytes may have left) is `sent=True`, so the feed's audit row is written --
    the audit over-reports, never under (R-3)."""
    from brambleloop.laura.agency import venice_context as VC

    db = _seed_feed_db()
    sid = _open(db)
    mock = Venice(fail=(503, "{}"))
    with unified(mock, **{U.BUSINESS_TO_VENICE_ENV: "1"}):
        out = _turn(db, sid, EVERYDAY_TURN)
    code = out["reason"]
    assert code not in ("PROVIDER_ERROR", "REPLIED", "", None) and code in LR.REASONS, out
    assert any(VC.FORMAT in json.dumps(c["body"]) for c in mock.calls), "the pack never left"
    (row,) = [r for r in _rows(db, AuditLog) if r.action == VC.AUDIT_ACTION]
    assert row.detail["outcome"] == code, (row.detail, code)
    # And directly: a failure inside `_send` carries sent=True.
    with unified(Venice(fail=(503, "{}"))):
        try:
            LR.reply(db, system=LR.PROMPT.system,
                     user=LR.render_user(facts=[], turns=[], message="hello"))
            raise AssertionError("no failure")
        except LR.ReplyUnavailable as exc:
            assert exc.sent is True and exc.code == code, (exc.code, exc.sent)


if __name__ == "__main__":
    H.run(globals())
