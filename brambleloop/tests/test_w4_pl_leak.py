"""W4-PRIVLAURA (PL-4, PL-6, PL-7; G-6): adversarial leak tests for the private reply.

1. While replies are generated (and while the provider fails with private-looking text in its
   error body), four detectors watch: every SQL statement's bound parameters, Python logging at
   DEBUG, stdout/stderr, and every business (Base) table afterwards -- paid_call_records, cost
   rows, audit_log (model attempts, spend refusals), company_timeline, company_memory,
   incidents, security events, the analysis cache -- plus the continuity export. No owner text
   and no reply text appears in any of them. Inside a job scope the reply is refused outright
   (so the paid-call journal can never hold it).
2. With a private reply in the store, every business surface (Talk to Laura incl. the CEO
   briefing, Ask Company, presence, identity, every CC tab and provider, CC GET routes) runs
   with an SQL watch: none touches a `laura_private_` table and none echoes a sentinel.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_pl_leak.py
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import tempfile
from pathlib import Path
from types import SimpleNamespace

import w3_laura_cc_harness as H  # noqa: E402
import w4_pl_harness as PL  # noqa: E402

from brambleloop.app.command_center import private_context  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.gateway import paid_calls  # noqa: E402
from brambleloop.laura.private import _testkit as kit  # noqa: E402

DB = H.DB
H.seed_company()
kit.set_key(kit.new_key())
OWNER = tuple(f"PRIV-SENTINEL-LEAK-{i:04d}" for i in range(1, 7))
REPLIES = tuple(f"PRIV-SENTINEL-LEAKREPLY-{i:04d}" for i in range(1, 4))
PROVIDER_BODY = "PRIV-SENTINEL-LEAK-PROVIDERBODY"
ALL = OWNER + REPLIES + (PROVIDER_BODY,)


def _leaks(blob: str) -> list[str]:
    return [x for x in ALL if x in blob]


def _open(c, csrf) -> str:
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    assert H.post(c, csrf, "/api/cc/private/open", {}).status_code == 200
    return c.get("/api/cc/auth/status").json()["session"]["session_id"]


def test_reply_text_never_reaches_business_tables_logs_paid_calls_or_cache():
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
    stub = PL.Stub(answers=[json.dumps({"text": r}) for r in REPLIES[:2]])
    try:
        with PL.sql_params(DB) as sql, contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            H.post(c, csrf, "/api/cc/private/remember", {"key": "PRIV-LABEL-L", "text": OWNER[0]})
            with PL.enabled(stub):
                a = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[1]}).json()
                b = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[2]}).json()
            with PL.enabled(PL.Stub(fail=TransientError(f"anthropic 500: {PROVIDER_BODY}"))):
                e = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[3]}).json()
            with PL.enabled(PL.Stub(fail=ValueError(f"unreadable {PROVIDER_BODY}"))):
                f = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[4]}).json()
            # Inside a job scope: refused before any request; the journal stays empty.
            job = SimpleNamespace(id=777, job_type="laura.executive_tick", agent="laura",
                                  attempts=1, lease_token="t", leased_by="w")
            with PL.enabled(None), paid_calls.job_scope(DB, job):
                j = private_context.owner_turn(DB, sid, OWNER[5])
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    assert a["reply_status"] == b["reply_status"] == "REPLIED", (a, b)
    assert a["reply"]["text"] == REPLIES[0] and b["reply"]["text"] == REPLIES[1]
    assert e["reply_status"] == f["reply_status"] == "UNAVAILABLE", (e, f)
    assert e["reason"] == f["reason"] == "PROVIDER_ERROR"
    assert PROVIDER_BODY not in json.dumps([e, f])
    assert j["reply_status"] == "UNAVAILABLE" and j["reason"] == "JOB_SCOPE", j
    assert len(sql) > 20, len(sql)
    assert "laura.private_reply@1" in "\n".join(sql)          # positive control: params seen
    assert not _leaks("\n".join(sql)), _leaks("\n".join(sql))           # bound parameters
    assert not _leaks(log.getvalue()), "logging"
    assert not _leaks(out.getvalue() + err.getvalue()), "stdio"
    blob, counts = PL.table_dump(DB)
    assert counts.get("cost_entries", 0) >= 2, counts      # the replies were billed ...
    assert "laura.private_reply@1" in blob and "model.attempt" in blob   # positive control
    assert not _leaks(blob), _leaks(blob)                  # ... with no content anywhere
    assert paid_calls.rows(DB, job_id=777) == []
    with tempfile.TemporaryDirectory(prefix="w4pl-") as td:
        res = continuity.export(DB, Path(td) / "export.jsonl")
        exp = res.path.read_text(encoding="utf-8") + Path(
            str(res.path) + ".manifest.json").read_text(encoding="utf-8")
    # Private TABLES are all `laura_private_*`; the billing agent `laura_private` (W4-PLACT,
    # D-W4-PL-3) is a business row by design and carries no content.
    assert "laura_private_" not in exp and not _leaks(exp)
    # Positive control: the owner does see the reply in the private view.
    v = H.post(c, csrf, "/api/cc/private/view", {})
    assert REPLIES[0] in v.text and v.headers["cache-control"] == "no-store"


def test_business_surfaces_stay_clean_while_a_private_reply_exists():
    from sqlalchemy import event

    from brambleloop.app.command_center import ask, providers, tabs
    from brambleloop.laura.agency import identity_view, presence, talk

    c, csrf = H.session()
    _open(c, csrf)
    with PL.enabled(PL.Stub(answers=[json.dumps({"text": REPLIES[2]})])):
        r = H.post(c, csrf, "/api/cc/private/turn", {"text": OWNER[0]}).json()
    assert r["reply_status"] == "REPLIED"
    hits: list[str] = []

    def watch(_conn, _cursor, statement, *_a):
        if "laura_private" in statement:
            hits.append(statement[:120])
    qs = ["What did your company do overnight?", "What are you working on?",
          "What genuinely needs me?", "Who are you?", "What did I tell you privately?",
          "What do you remember about us?", "What did you say to me last night?",
          "Brief me: overnight, money, decisions, risks, what you will do next",
          "Have Design make three more banners"]
    outs = []
    event.listen(DB.engine, "before_cursor_execute", watch)
    try:
        for q in qs:
            outs.append(json.dumps(talk.converse(DB, q, session_public_id="s"), default=str))
            outs.append(json.dumps(ask.ask(DB, q), default=str))
        outs.append(json.dumps(talk.overview(DB), default=str))
        outs.append(json.dumps(presence.capabilities(), default=str))
        outs.append(json.dumps(identity_view.visible_identity(), default=str))
        for name in ("home", "store", "operations", "autonomy", "insights", "money"):
            outs.append(json.dumps(getattr(tabs, name)(DB), default=str))
        for key in providers.PROVIDERS:
            if key not in ("accounting_drill", "timeline"):
                outs.append(json.dumps(providers.call(key, DB), default=str))
        for path in ("/api/cc/laura", "/api/cc/laura/conversation", "/api/cc/home",
                     "/api/cc/timeline", "/api/cc/notifications", "/api/cc/laura/presence",
                     "/api/cc/laura/voice-spec"):
            outs.append(c.get(path).text)
    finally:
        event.remove(DB.engine, "before_cursor_execute", watch)
    assert len(outs) > 30
    assert hits == [], hits
    assert not _leaks("\n".join(outs)), _leaks("\n".join(outs))


if __name__ == "__main__":
    H.run(globals())
