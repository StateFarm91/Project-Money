"""R2 security, audit ddf9c6e L1-L3 (command-center owner actions and request origin).

* L1: publication.approve enforces evidence readiness on the server: any gated section FAIL or
  UNKNOWN (the inbox card's "Not ready") refuses, whatever the client sends.
* L2: revoking an id that is not a grant of that ledger is a 404 and seals nothing.
* L3: the Origin check compares scheme + host + port; authority refusals never echo raw
  Python exception text (stable message to the owner, detail kept in the audit row).

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_security_actions.py
"""
from __future__ import annotations

import os
from unittest.mock import patch

from r2_security_harness import DB, PASS, client, fresh, login, run  # noqa: I001
from sqlalchemy import func, select

from brambleloop.app.command_center.models import SecurityEvent
from brambleloop.core.models import AuditLog, Listing, PatternVersion, Product
from brambleloop.ops import activation_authority as act
from brambleloop.ops import publication_authority as pub
from brambleloop.runtime import etsy_ops

REL = "rel" * 10
BODY = {"slug": "r2probe", "version": "1.0.0", "release": REL}


def _seed_release():
    with DB.session() as s:
        if s.scalar(select(Product).where(Product.slug == "r2probe")) is not None:
            return
        p = Product(slug="r2probe", title="Probe", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"x": 1},
                             release_hash=REL, certified=True, certificate={"findings": []}))
        s.add(Listing(product_slug="r2probe", version="1.0.0", title="t", description="d",
                      tags=[], price_cad=5.0, state="draft", release_hash=REL))


def _count(action: str) -> int:
    with DB.session() as s:
        return s.scalar(select(func.count()).select_from(AuditLog)
                        .where(AuditLog.action == action)) or 0


def _session():
    c = client()
    csrf = login(c)
    return c, csrf


def test_publication_approve_refuses_when_evidence_is_not_ready():
    _seed_release()
    c, csrf = _session()
    with patch.dict(os.environ, {pub.KILL_SWITCH_VAR: "1"}), \
            patch.object(etsy_ops, "certified_payload", return_value={"title": "t"}), \
            patch.object(etsy_ops, "sent_fields", side_effect=lambda x: x):
        cards = [x for x in c.get("/api/cc/approvals").json()["cards"]
                 if x["card_id"] == "publication:r2probe@1.0.0"]
        assert len(cards) == 1 and cards[0]["executable"] is False, cards
        assert cards[0]["recommendation"].startswith("Not ready"), cards[0]["recommendation"]
        r = c.post("/api/cc/actions/publication.preview", json=BODY, headers=fresh(csrf))
        assert r.status_code == 200, r.text
        states = {d["section"]: d["state"] for d in r.json()["result"]["display"]}
        assert any(v != "PASS" for k, v in states.items() if k != "economics"), states
        digest = r.json()["result"]["digest"]
        before = _count(pub.APPROVED)
        r = c.post("/api/cc/actions/publication.approve", headers=fresh(csrf),
                   json={**BODY, "expected_digest": digest, "reason": "probe"})
        assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
        assert "evidence not ready" in r.json()["error"], r.text
        assert _count(pub.APPROVED) == before, "a grant was sealed despite failing evidence"
        # Control: with every gated section passing, the same approval is recorded.
        passing = {k: {"state": pub.PASS, "why": "test"}
                   for k in pub.GATED_SECTIONS + ("economics",)}
        passing["summary"] = {"all_gated_sections_pass": True, "not_passing": [],
                              "unknown": [], "economics_basis": pub.PASS}
        with patch.object(pub, "evidence", return_value=passing):
            r = c.post("/api/cc/actions/publication.preview", json=BODY, headers=fresh(csrf))
            digest = r.json()["result"]["digest"]
            r = c.post("/api/cc/actions/publication.approve", headers=fresh(csrf),
                       json={**BODY, "expected_digest": digest, "reason": "probe"})
        assert r.status_code == 200, r.text
        assert _count(pub.APPROVED) == before + 1
        # An UNKNOWN section (never PASS) refuses too.
        unknown = {**passing, "search": {"state": pub.UNKNOWN, "why": "unread"},
                   "summary": {"all_gated_sections_pass": False, "not_passing": ["search"],
                               "unknown": ["search"], "economics_basis": pub.PASS}}
        with patch.object(pub, "evidence", return_value=unknown):
            r = c.post("/api/cc/actions/publication.approve", headers=fresh(csrf),
                       json={**BODY, "expected_digest": digest, "reason": "probe"})
        assert r.status_code == 409 and "search" in r.json()["error"], r.text


def test_revoking_a_non_existent_or_foreign_id_is_404_and_seals_nothing():
    c, csrf = _session()
    before = (_count(pub.REVOKED), _count(act.REVOKED))
    r = c.post("/api/cc/actions/publication.revoke", json={"approval_id": 999999},
               headers=fresh(csrf))
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND", r.text
    r = c.post("/api/cc/actions/activation.revoke", json={"approval_id": 999999},
               headers=fresh(csrf))
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND", r.text
    # An id that exists but is not a grant of that ledger (here: an ordinary audit row).
    with DB.session() as s:
        row = AuditLog(actor="r2", action="something.else", artifact="x", detail={})
        s.add(row)
        s.flush()
        other = row.id
    r = c.post("/api/cc/actions/publication.revoke", json={"approval_id": other},
               headers=fresh(csrf))
    assert r.status_code == 404, r.text
    assert (_count(pub.REVOKED), _count(act.REVOKED)) == before


def test_origin_check_compares_scheme_host_and_port():
    c, csrf = _session()
    body = {"scope": "publishing", "reason": "origin probe"}
    refused = ("http://testserver", "https://testserver:8443", "http://testserver:443",
               "https://testserver.evil.example", "null", "testserver")
    assert refused
    for origin in refused:
        r = c.post("/api/cc/home/seen", json={}, headers=fresh(csrf, Origin=origin))
        assert r.status_code == 403 and r.json()["code"] == "CSRF", (origin, r.text)
        r = client().post("/api/cc/auth/login", json={"passphrase": PASS},
                          headers={"Origin": origin})
        assert r.status_code == 403, (origin, r.text)
    for origin in ("https://testserver", "https://testserver:443", "HTTPS://TestServer"):
        r = c.post("/api/cc/home/seen", json={}, headers=fresh(csrf, Origin=origin))
        assert r.status_code == 200, (origin, r.text)
    assert body


def test_refusals_do_not_echo_python_exception_text():
    c, csrf = _session()
    r = c.post("/api/cc/actions/activation.revoke", json={"approval_id": "nope"},
               headers=fresh(csrf))
    assert r.status_code == 409, r.text
    assert "invalid literal" not in r.text and "int()" not in r.text, r.text
    assert r.json()["error"] == "approval_id must be an integer", r.text
    raw = "internal detail at 0x7f00dead: 'NoneType' object is not subscriptable"
    with patch.object(pub, "snapshot", side_effect=TypeError(raw)):
        r = c.post("/api/cc/actions/publication.preview", json=BODY, headers=fresh(csrf))
    assert r.status_code == 409, r.text
    assert "0x7f00dead" not in r.text and "NoneType" not in r.text, r.text
    # The detail is kept for the operator in the security-event audit row.
    with DB.session() as s:
        row = s.scalars(select(SecurityEvent).where(SecurityEvent.kind == "action")
                        .order_by(SecurityEvent.id.desc())).first()
        assert row is not None and raw in str((row.detail or {}).get("message")), row.detail
    # Deliberate authority refusals still reach the owner verbatim.
    with patch.object(act, "snapshot", return_value={"x": 1}):
        r = c.post("/api/cc/actions/activation.approve", headers=fresh(csrf),
                   json={**BODY, "expected_digest": "0" * 64, "reason": "probe"})
    assert r.status_code == 409 and "preview changed" in r.json()["error"], r.text


if __name__ == "__main__":
    run(globals())
