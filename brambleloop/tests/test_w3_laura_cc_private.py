"""W3 lane F: the owner-private context in the Command Center (PRIV contract, spec/07 Ruling 2).

* the only way in is `app.command_center.private_context` behind /api/cc/private/*: a live
  owner session, CSRF/nonce, and a FRESH step-up to open; the grant id never reaches the client;
* values are revealed only in the private POST responses (no-store); Laura's private reply
  register stays GATED -- an owner message is stored, no reply is generated;
* logout / session revoke ends private access; another session cannot use the grant; no key
  configured -> 503 and nothing else is affected;
* refusals are security events of kind `private_context` carrying the class name only;
* business paths -- Talk to Laura, presence, overview, every CC tab and provider -- never read
  the private tables (SQL watch) and never echo private sentinels, even with a context open;
  the firewall refuses private values at Laura's business entry points.

Neutral sentinel data only. Run: cd brambleloop && PYTHONPATH=src python
tests/test_w3_laura_cc_private.py
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import w3_laura_cc_harness as H  # noqa: E402

from sqlalchemy import event, select  # noqa: E402

from brambleloop.app.command_center.models import SecurityEvent  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402
from brambleloop.laura.private.firewall import PrivateInputRefused  # noqa: E402
from brambleloop.laura.private.values import PrivateValue  # noqa: E402

DB = H.DB
H.seed_company()
S = kit.SENTINELS
kit.set_key(kit.new_key())


@contextmanager
def sql_watch():
    hits: list[str] = []

    def before(_conn, _cursor, statement, *_a):
        if "laura_private" in statement:
            hits.append(statement.split("\n")[0][:120])

    event.listen(DB.engine, "before_cursor_execute", before)
    try:
        yield hits
    finally:
        event.remove(DB.engine, "before_cursor_execute", before)


def _open(c, csrf):
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    r = H.post(c, csrf, "/api/cc/private/open", {})
    assert r.status_code == 200 and r.json()["open"] is True, r.text
    assert "grant" not in r.text.lower(), r.text            # grant id stays server-side


def test_opening_needs_a_fresh_step_up_and_status_is_non_content():
    c, csrf = H.session()
    st = c.get("/api/cc/private/status").json()
    assert st["configured"] is True and st["open"] is False and st["reply_register"] == "GATED"
    H.expire_stepup(c)
    r = H.post(c, csrf, "/api/cc/private/open", {})
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    r = H.post(c, csrf, "/api/cc/private/view", {})
    assert r.status_code == 403 and r.json()["code"] == "PRIVATE_REFUSED", r.text
    _open(c, csrf)
    assert c.get("/api/cc/private/status").json()["open"] is True
    anon = H.client()
    assert anon.post("/api/cc/private/view", json={}).status_code in (401, 403)
    assert anon.get("/api/cc/private/status").status_code in (401, 403)


def test_owner_notes_and_messages_round_trip_and_no_reply_is_generated():
    c, csrf = H.session()
    _open(c, csrf)
    r = H.post(c, csrf, "/api/cc/private/remember", {"key": "PRIV-LABEL-A", "text": S[0]})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
    r = H.post(c, csrf, "/api/cc/private/turn", {"text": S[1]})
    out = r.json()
    assert r.status_code == 200 and out["reply"] is None and out["reply_status"] == "GATED", out
    v = H.post(c, csrf, "/api/cc/private/view", {})
    assert v.status_code == 200 and v.headers["cache-control"] == "no-store", (v.status_code,
                                                                                v.text[:300])
    body = v.json()
    assert any(f["text"] == S[0] and f["key"] == "PRIV-LABEL-A" for f in body["facts"]), body
    turns = body["conversation"]
    assert turns and all(t["role"] == "owner" for t in turns), turns   # nothing from Laura
    assert any(t["text"] == S[1] for t in turns)
    fid = next(f["id"] for f in body["facts"] if f["text"] == S[0])
    assert H.post(c, csrf, "/api/cc/private/forget", {"id": fid}).json()["deleted"] >= 1
    body = H.post(c, csrf, "/api/cc/private/view", {}).json()
    assert not any(f["text"] == S[0] for f in body["facts"])
    bad = H.post(c, csrf, "/api/cc/private/remember", {"key": "", "text": ""})
    assert bad.status_code == 400 and S[0] not in bad.text, bad.text


def test_other_sessions_logout_and_close_end_access():
    c1, csrf1 = H.session()
    _open(c1, csrf1)
    H.post(c1, csrf1, "/api/cc/private/turn", {"text": S[2]})
    c2, csrf2 = H.session()                                  # a second device, no step-up open
    r = H.post(c2, csrf2, "/api/cc/private/view", {})
    assert r.status_code == 403 and S[2] not in r.text, r.text
    assert H.post(c1, csrf1, "/api/cc/private/close", {}).json()["closed"] is True
    r = H.post(c1, csrf1, "/api/cc/private/view", {})
    assert r.status_code == 403, r.text
    _open(c1, csrf1)
    sid = c1.get("/api/cc/auth/status").json()["session"]["session_id"]
    assert H.post(c1, csrf1, "/api/cc/auth/logout", {}).status_code == 200
    from brambleloop.laura.private.models import PrivateGrant
    with DB.session() as s:
        live = [g for g in s.scalars(select(PrivateGrant).where(
            PrivateGrant.session_public_id == sid)) if g.revoked_at is None]
    assert live == [], live


def test_refusals_are_security_events_with_class_name_only():
    c, csrf = H.session()
    H.post(c, csrf, "/api/cc/private/remember", {"key": "k", "text": S[3]})   # not open
    with DB.session() as s:
        ev = list(s.scalars(select(SecurityEvent).where(SecurityEvent.kind == "private_context")))
    assert ev, "refusal not recorded"
    for e in ev:
        blob = json.dumps({"r": e.reason, "d": getattr(e, "detail", None)}, default=str)
        assert not any(x in blob for x in S), blob
        assert "PrivateAccessRefused" in e.reason or "PRIVATE" in e.reason, e.reason


def test_no_key_is_503_and_nothing_else_is_affected():
    saved = __import__("os").environ.get("BRAMBLELOOP_PRIVATE_MEMORY_KEY")
    kit.set_key(None)
    try:
        c, csrf = H.session()
        assert c.get("/api/cc/private/status").json()["configured"] is False
        assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
        r = H.post(c, csrf, "/api/cc/private/open", {})
        assert r.status_code == 503 and r.json()["code"] == "PRIVATE_UNAVAILABLE", r.text
        r = H.post(c, csrf, "/api/cc/laura/ask", {"question": "What genuinely needs me?"})
        assert r.status_code == 200, r.text
    finally:
        kit.set_key(saved)


def test_business_paths_never_read_the_private_context_even_while_it_is_open():
    from brambleloop.app.command_center import providers, tabs
    from brambleloop.laura.agency import followon, identity_view, presence, talk

    c, csrf = H.session()
    _open(c, csrf)
    for i, s_ in enumerate(S[4:]):
        H.post(c, csrf, "/api/cc/private/remember", {"key": f"PRIV-LABEL-{i}", "text": s_})
        H.post(c, csrf, "/api/cc/private/turn", {"text": s_})
    qs = ["What did your company do overnight?", "What are you working on?",
          "How does your store look?", "What's making money / losing money?",
          "What did you learn?", "What genuinely needs me?", "Who are you?",
          "What did I tell you privately?", "What do you remember about us?",
          f"Search {S[4]}", "Have Design make three more banners"]
    outs = []
    with sql_watch() as hits:
        for q in qs:
            outs.append(json.dumps(talk.converse(DB, q, session_public_id="s"), default=str)
                        .replace(f"Search {S[4]}", ""))
        outs.append(json.dumps(talk.overview(DB), default=str))
        outs.append(json.dumps(presence.capabilities(), default=str))
        outs.append(json.dumps(identity_view.visible_identity(), default=str))
        for name in ("home", "store", "operations", "autonomy", "insights", "money"):
            outs.append(json.dumps(getattr(tabs, name)(DB), default=str))
        for key in providers.PROVIDERS:
            if key not in ("accounting_drill", "timeline"):
                outs.append(json.dumps(providers.call(key, DB), default=str))
        for path in ("/api/cc/laura", "/api/cc/laura/conversation", "/api/cc/home",
                     "/api/cc/timeline", "/api/cc/notifications", "/api/cc/laura/presence"):
            outs.append(c.get(path).text)
    assert len(outs) > 20
    assert hits == [], hits
    # The owner's own question echoing back ("Search <sentinel>") is input, not a leak.
    blob = "\n".join(outs).replace(f"Search {S[4]}", "")
    assert not [x for x in S if x in blob], [x for x in S if x in blob]
    # The firewall refuses private values at Laura's business entry points.
    for fn in (lambda: talk.converse(DB, PrivateValue("x")),
               lambda: followon.create(DB, 1, PrivateValue("k"), confirmed_by="o",
                                       stepped_up=False)):
        try:
            fn()
        except PrivateInputRefused:
            continue
        raise AssertionError("private value accepted on a business path")


def test_only_private_context_imports_the_private_api_in_the_command_center_and_agency():
    import ast
    from pathlib import Path

    root = Path(H.ROOT) / "src" / "brambleloop"
    files = list((root / "app" / "command_center").glob("*.py")) + \
        list((root / "laura" / "agency").glob("*.py"))
    assert len(files) > 10
    offenders = []
    for f in files:
        if f.name == "private_context.py":
            continue
        text = f.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom) and node.module and "private" in node.module \
                    and not node.module.endswith("firewall") \
                    and not node.module.endswith("values") \
                    and "private_context" not in node.module:
                offenders.append((f.name, node.module))
        if ".reveal(" in text:
            offenders.append((f.name, ".reveal("))
    assert offenders == [], offenders
    # Only the API module (routes) imports private_context; no reader, tab or Laura module.
    users = [f.name for f in files if f.name not in ("private_context.py", "api.py")
             and any((isinstance(n, ast.ImportFrom) and any(
                 "private_context" in (x.name or "") for x in n.names))
                 or (isinstance(n, ast.ImportFrom) and "private_context" in (n.module or ""))
                 for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))))]
    assert users == [], users


if __name__ == "__main__":
    H.run(globals())
