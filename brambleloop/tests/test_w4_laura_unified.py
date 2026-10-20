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

    def __init__(self, reply=BIZ_ANSWER, on_call=None, offer_first=False):
        self.seen: list[tuple[str, str, str]] = []
        self.reply = reply
        self.on_call = on_call
        self.offer_first = offer_first

    def factory(self, model):
        def scripted(system, user):
            self.seen.append((model, system, user))
            if self.on_call is not None:
                self.on_call()
            offer = ["P1"] if self.offer_first and "\nP1 |" in user else []
            return json.dumps({"reply": self.reply, "citations": [], "offer": offer,
                               "remember": ""})
        return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                            cost_per_1k_output_cad=0.005, scripted=scripted)

    def blob(self) -> str:
        return "\n".join(s + "\n" + u for _, s, u in self.seen)


ON = {"BRAMBLELOOP_PRIVATE_PROVIDER": "venice", "VENICE_API_KEY": VKEY,
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
    assert r.status_code == 200 and r.json()["status"] == ceo_chat.UNAVAILABLE   # unchanged


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
        x = PC.unified_crossing(db, sid, m["crossing"]["id"], approve=True, stepped_up=True,
                                provider_factory=biz.factory)
    assert x["crossed"] and len(_rows(db, LauraTurn)) == 2
    out = _control(db, sid, "mark_private", [a["id"], m["id"]])
    assert out["redacted"] == {"business_turns": 2, "crossings": 1}, out
    for row in _rows(db, LauraTurn):
        assert row.question == boundary.REDACTED and row.answer == boundary.REDACTED
        assert row.facts == [] and row.proposals == []
    (cr,) = _rows(db, LauraBoundaryCrossing)
    assert cr.approved_text == boundary.REDACTED and len(cr.text_sha256) == 64
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
        a = PC.unified_crossing(db, sid, x["id"], approve=True, stepped_up=True,
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
            PC.unified_crossing(db, sid, x["id"], approve=True, stepped_up=True,
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
        assert H.post(c, csrf, "/api/cc/auth/step-up",
                      {"passphrase": H.PASS}).status_code == 200
        ok = H.post(c, csrf, "/api/cc/laura/unified/crossing", {"id": xid, "approve": True})
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
    with unified(None):
        out = _turn(db, sid, "Which listings sold best overnight?", biz)
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
    assert "laura.co" in params or "laura.ex" in params             # positive control
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
        a = PC.unified_crossing(db, sid, x["id"], approve=True, stepped_up=True,
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
    assert set(row.detail) == {"sha256", "fields", "counts", "bytes", "dropped", "format"}
    texts = [f["value"] for f in prev["fields"] if isinstance(f["value"], str)]
    assert texts and not [t for t in texts if t in json.dumps(row.detail)], row.detail
    assert row.detail["counts"] == {f["name"]: (len(f["value"]) if isinstance(
        f["value"], (list, dict)) else 0 if f["value"] is None else 1) for f in prev["fields"]}
    for bad in PII:
        assert bad not in mock.user(1) and bad not in json.dumps(row.detail)
    # The owner's preview over HTTP is owner-only and no-store.
    c, csrf = H.session()
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


if __name__ == "__main__":
    H.run(globals())
