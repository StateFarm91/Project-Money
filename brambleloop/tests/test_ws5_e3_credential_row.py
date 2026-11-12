"""WS5 E3: "Etsy credential usable" means usable, not configured.

`etsy_public.health()["usable"]` is true whenever the keystring and secret are set, so the
readback row read PASS through the whole 403 period. The row now reads
`/api/etsy` `credential.usable`: an OAuth-AUTHENTICATED read (the daily
`etsy.credential_health` getMe) within 26 h, a stored grant this deployment can open, and every
needed scope (transactions_r included) recorded as granted. The app-key `etsy.probe` ping is
reported but never relied on. The row reads WARN only when /api/etsy answered 200 with
`usable` false; a crashing or refused route, or a missing field, is UNKNOWN (review
6818959626). A real Etsy draft is refused unless the credential is usable.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws5_e3_credential_row.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "ops"))

import readback  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.integrations import etsy_oauth  # noqa: E402
from brambleloop.intel import etsy_public as EP  # noqa: E402

NOW = datetime(2026, 11, 12, 7, 0, tzinfo=timezone.utc)
ENV = {"ETSY_API_KEY": "k" * 24, "ETSY_SHARED_SECRET": "s" * 12}


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='ws5e3_')}/e.sqlite", scratch=True)
    db.create_all()
    return db


def _probe(db, *, ok, hours_ago=1, status=None):
    """The app-key ping record: reported, never the basis of usability."""
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="ping", detail={
            "at": (NOW - timedelta(hours=hours_ago)).isoformat(), "ok": ok,
            **({"status": status, "reason": f"ping returned HTTP {status}"} if status else {})}))


def _auth_read(db, *, ok=True, hours_ago=1.0, status="HEALTHY"):
    """The daily OAuth-authenticated getMe reading (`etsy.credential_health`)."""
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action="etsy.credential_health", detail={
            "observed_at": (NOW - timedelta(hours=hours_ago)).timestamp(), "status": status,
            "live": {"attempted": True, "ok": ok}}))


def _oauth(openable=True, scopes=etsy_oauth.SCOPES_WANTED):
    return (patch("brambleloop.core.oauth_store.credential_health",
                  return_value={"openable": openable}),
            patch("brambleloop.core.oauth_store.stored_scopes", return_value=tuple(scopes)))


def _usable(db):
    a, b = _oauth()
    with a, b:
        return EP.credential_usable(db, env=ENV, now=NOW)


def test_a_recent_authenticated_read_an_openable_grant_and_every_scope_is_usable():
    db = _db()
    _auth_read(db, hours_ago=2)
    c = _usable(db)
    assert c["usable"] is True and c["why"] == "" and c["scopes_not_granted"] == [], c
    assert c["authenticated_read_age_hours"] == 2.0


def test_an_app_key_ping_alone_is_not_an_authenticated_read():
    """Review 6818959626 (honesty): `etsy.probe` is GET ping with the app key only."""
    db = _db()
    _probe(db, ok=True, hours_ago=1)
    c = _usable(db)
    assert c["usable"] is False and "OAuth-authenticated" in c["why"], c
    assert c["probe_age_hours"] == 1.0             # still reported


def test_a_failed_unknown_or_unhealthy_authenticated_read_is_not_usable():
    for kw in ({"ok": False, "status": "UNHEALTHY"}, {"ok": None, "status": "UNKNOWN"},
               {"ok": True, "status": "UNHEALTHY"}, {"ok": None, "status": "HEALTHY"},
               {"ok": False, "status": "HEALTHY"}):
        db = _db()
        _auth_read(db, **kw)
        assert _usable(db)["usable"] is False, kw


def test_a_stale_read_a_missing_grant_or_a_missing_scope_is_not_usable():
    db = _db()
    _auth_read(db, hours_ago=EP.AUTH_READ_FRESH_HOURS + 0.5)
    assert _usable(db)["usable"] is False
    db = _db()
    _auth_read(db, hours_ago=EP.AUTH_READ_FRESH_HOURS - 0.5)
    assert _usable(db)["usable"] is True
    a, b = _oauth(openable=False)
    with a, b:
        assert EP.credential_usable(db, env=ENV, now=NOW)["usable"] is False
    a, b = _oauth(scopes=[s for s in etsy_oauth.SCOPES_WANTED if s != "transactions_r"])
    with a, b:
        c = EP.credential_usable(db, env=ENV, now=NOW)
    assert c["usable"] is False and c["scopes_not_granted"] == ["transactions_r"], c
    assert _usable(_db())["usable"] is False             # never read: not usable


def test_n3_a_future_dated_reading_is_not_recent():
    db = _db()
    _auth_read(db, hours_ago=-3)                         # three hours in the future
    c = _usable(db)
    assert c["usable"] is False and c["demonstrated_recently"] is False, c


def test_the_readback_row_reads_the_judgement_and_warns_only_on_a_200():
    row = next(r for r in readback.MANIFEST if r[0] == "Etsy credential usable")
    assert row[3] == "credential.usable" and row[6] == readback.WARN_IF_READ, row
    body = {"usable": True, "credential": {"usable": False}}      # configured, not usable
    assert readback._dig(body, row[3]) is False
    assert row[5](readback._dig(body, row[3]), body) is False
    assert row[5](readback._dig({"credential": {"usable": True}}, row[3]), {}) is True


class _Resp:
    """What a route returns when it answers other than 200 (as a JSONResponse does)."""

    def __init__(self, code, body):
        import json as _json

        self.status_code, self.body = code, _json.dumps(body).encode()


def _row_verdict(code, body, *, via_evidence=False):
    """The credential row's verdict when /api/etsy answers `code` with `body`, read directly
    with the operator token or through /api/readback/evidence's real projection."""
    from brambleloop.ops import production_evidence as PE
    from test_w4_smoke import OPS_TOKEN, SHA, _fetcher, _prod_bodies

    bodies = _prod_bodies(**{"/api/etsy": (code, body)})
    if via_evidence:
        handlers = {}
        for route in PE.DEPLOY_READBACK:
            c, b = bodies[route]
            handlers[route] = (lambda b=b: b) if c == 200 else (lambda c=c, b=b: _Resp(c, b))
        token = "test-readback-token"
        evidence = {"deploy_readback": PE.deploy_readback(handlers)}

        def fetch(url, tok=None):
            path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else "/"
            if path == readback.EVIDENCE_ENDPOINT:
                return (200, evidence) if tok == token else (401, {})
            return _fetcher(bodies)(url, tok)

        out = readback.run(SHA, url="https://prod.invalid", fetch=fetch, readback_token=token)
        rows = [i for i in out["features"] if i["endpoint"] == "/api/etsy"]
        assert rows and rows[0].get("via") == readback.EVIDENCE_ENDPOINT, rows
    else:
        out = readback.run(SHA, url="https://prod.invalid", fetch=_fetcher(bodies),
                           token=OPS_TOKEN)
        rows = [i for i in out["features"] if i["endpoint"] == "/api/etsy"]
    assert len(rows) == 1, rows
    return rows[0]["verdict"]


def test_a_crashing_or_refused_route_is_unknown_not_warn():
    """Review 6818959626 (MED): a 500 or 401 used to read WARN on both paths."""
    assert _row_verdict(200, {"credential": {"usable": False}}) == readback.WARN
    assert _row_verdict(200, {"credential": {"usable": True}}) == readback.PASS
    for code, body in ((500, {"credential": {"usable": False}}), (401, {}), (500, None),
                       (200, {}), (200, {"credential": {}})):
        assert _row_verdict(code, body) == readback.UNKNOWN, (code, body)


def test_n4_deploy_readback_reads_the_dotted_field():
    from brambleloop.ops import production_evidence as PE

    handlers = {r: (lambda: {}) for r in PE.DEPLOY_READBACK}
    handlers["/api/etsy"] = lambda: {"usable": True, "credential": {"usable": False}}
    out = PE.deploy_readback(handlers)
    assert out["/api/etsy"] == {"status": 200, "fields": {"credential.usable": False}}, out
    handlers["/api/etsy"] = lambda: {"credential": {"usable": True}}
    assert PE.deploy_readback(handlers)["/api/etsy"]["fields"] == {"credential.usable": True}
    handlers["/api/etsy"] = lambda: {"usable": True}                # field absent
    assert PE.deploy_readback(handlers)["/api/etsy"]["fields"] == {"credential.usable": None}

    def boom():
        raise RuntimeError("route crashed")

    handlers["/api/etsy"] = boom
    assert PE.deploy_readback(handlers)["/api/etsy"]["status"] == 500


def test_n5_from_evidence_rebuilds_the_nested_field():
    body = {"deploy_readback": {"/api/etsy": {"status": 200,
                                              "fields": {"credential.usable": False}}}}
    code, rebuilt = readback._from_evidence(body, "/api/etsy")
    assert code == 200 and rebuilt == {"credential": {"usable": False}}, rebuilt
    assert readback._dig(rebuilt, "credential.usable") is False
    body["deploy_readback"]["/api/etsy"]["fields"] = {"credential.usable": True,
                                                      "packets": {"list_length": 2}}
    _code, rebuilt = readback._from_evidence(body, "/api/etsy")
    assert rebuilt == {"credential": {"usable": True}, "packets": [None, None]}, rebuilt
    assert readback._from_evidence({"deploy_readback": {}}, "/api/etsy") == (None, None)


def test_n5_the_evidence_path_gives_the_same_verdicts():
    assert _row_verdict(200, {"credential": {"usable": False}},
                        via_evidence=True) == readback.WARN
    assert _row_verdict(200, {"credential": {"usable": True}},
                        via_evidence=True) == readback.PASS
    assert _row_verdict(500, {"credential": {"usable": False}},
                        via_evidence=True) == readback.UNKNOWN
    assert _row_verdict(200, {}, via_evidence=True) == readback.UNKNOWN


def test_api_etsy_carries_the_judgement():
    db = _db()
    _probe(db, ok=False, status=403)
    a, b = _oauth()
    with a, b:
        cap = EP.capability(db, env=ENV)
    assert cap["usable"] is True and cap["credential"]["usable"] is False, cap


class _Client:
    def __init__(self, base, transport=None):
        from brambleloop.integrations.http import UrllibTransport

        self.BASE = base
        self.transport = transport if transport is not None else UrllibTransport()


def test_a_real_draft_is_refused_unless_the_credential_is_usable():
    """Review 6818959626 (HIGH): the pre-create gate, before the intent is claimed."""
    from brambleloop.integrations.etsy import EtsyClient
    from brambleloop.runtime import pipeline

    real = _Client(EtsyClient.BASE)
    fake = _Client("http://127.0.0.1:9/v3/application")
    db = _db()
    a, b = _oauth()
    with a, b:
        why = pipeline.real_draft_credential_refusal(db, real)
        assert why and "not usable" in why and "OAuth-authenticated" in why, why
        assert pipeline.real_draft_credential_refusal(db, fake) is None   # not a real draft
        # Etsy's base with an in-memory transport cannot reach Etsy: not a real draft.
        assert pipeline.real_draft_credential_refusal(
            db, _Client(EtsyClient.BASE, transport=object())) is None
        assert pipeline.real_draft_credential_refusal(db, object()) is None  # no BASE at all
    _auth_read(db, hours_ago=1)
    with patch.object(EP, "credential_usable",
                      lambda db_, **_k: {"usable": True, "why": ""}):
        assert pipeline.real_draft_credential_refusal(db, real) is None
    with patch.object(EP, "credential_usable", side_effect=RuntimeError("db gone")):
        assert "UNKNOWN" in pipeline.real_draft_credential_refusal(db, real)


def test_the_gate_runs_before_the_draft_intent_is_claimed():
    """A refusal provably sends nothing: the gate precedes the intent claim and the create."""
    import inspect

    from brambleloop.runtime import pipeline

    src = inspect.getsource(pipeline._publish_and_read_back)
    gate = src.index("real_draft_credential_refusal(ctx.db, client)")
    assert gate < src.index("draft_intent.claim(") and gate < src.index("client.publish(")
    assert 'raise PermanentError("PUBLISH_EXECUTION_REFUSED: " + credential_refusal)' in src


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
