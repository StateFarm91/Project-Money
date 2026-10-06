"""v1.1 lane C: Owner Command Center authentication (F-887, F-888; §95 "attempt a high-impact
approval without authenticated owner authority: refuse and audit it").

Walks the real app's `/api/cc/*` routes (never a hand list) and proves: every route except
the two public auth routes refuses without a session; every mutating route refuses without a
CSRF token, with a wrong one, cross-site, without a fresh nonce/timestamp and on a replayed
nonce; consequential actions need step-up; refused attempts are audited in
`cc_security_events` and do not touch `audit_log`; login is rate limited; TOTP is enforced
when configured; sessions can be listed and revoked; the cookie is HttpOnly/Secure/Strict;
an unset operator credential closes the whole command center (503).

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_cc_auth.py
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="v11_cc_auth_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the command-center harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.app import main, security  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession, SecurityEvent  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402

OPS = "k" * 40
PASS = "owner passphrase for the harness only"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # the RFC 6238 documentation example, not a credential
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
PUBLIC = set(auth.PUBLIC_ROUTES)


def client() -> TestClient:
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)


def login(c: TestClient, **extra) -> str:
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS, **extra})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def fresh(csrf: str | None, **over) -> dict:
    h = {"X-CC-Nonce": uuid.uuid4().hex, "X-CC-Timestamp": str(int(time.time()))}
    if csrf is not None:
        h["X-CSRF-Token"] = csrf
    h.update(over)
    return h


def cc_routes() -> list[tuple[str, str]]:
    out = []
    for path, methods, _dep in security.iter_api_routes(main.app):
        if path.startswith("/api/cc/"):
            for m in sorted(methods - {"HEAD", "OPTIONS"}):
                out.append((m, path))
    return out


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def counts() -> tuple[int, int]:
    with main.db.session() as s:
        return (s.scalar(select(func.count()).select_from(SecurityEvent)) or 0,
                s.scalar(select(func.count()).select_from(AuditLog)) or 0)


def test_route_enumeration_covers_the_contract():
    routes = cc_routes()
    assert len(routes) >= 30, routes
    for want in (("POST", "/api/cc/actions/{action}"), ("POST", "/api/cc/emergency/pause"),
                 ("POST", "/api/cc/emergency/kill"), ("POST", "/api/cc/emergency/resume"),
                 ("POST", "/api/cc/ask"), ("GET", "/api/cc/home"), ("GET", "/api/cc/money"),
                 ("POST", "/api/cc/auth/login"), ("GET", "/api/cc/auth/status")):
        assert want in routes, want


def test_every_non_public_route_refuses_without_a_session_and_audits():
    c = client()
    routes = [r for r in cc_routes() if r not in PUBLIC]
    assert routes
    ev0, audit0 = counts()
    bad = []
    for method, path in routes:
        r = c.request(method, concrete(path), json={}, headers=fresh("x" * 64))
        if r.status_code != 401 or r.json().get("code") != "NOT_AUTHENTICATED":
            bad.append((method, path, r.status_code, r.text[:120]))
    assert not bad, bad
    ev1, audit1 = counts()
    assert ev1 - ev0 == len(routes), (ev1 - ev0, len(routes))
    assert audit1 == audit0, "a refused request changed audit_log"


def test_operator_bearer_alone_is_not_an_owner_session():
    c = client()
    r = c.post("/api/cc/actions/publication.revoke", json={"approval_id": 1},
               headers={**fresh(None), "Authorization": f"Bearer {OPS}"})
    assert r.status_code == 401, r.text


def test_unauthenticated_high_impact_approval_is_refused_and_audited():
    c = client()
    ev0, audit0 = counts()
    r = c.post("/api/cc/actions/publication.approve",
               json={"slug": "x", "version": "1", "release": "r", "expected_digest": "d",
                     "reason": "forged"}, headers=fresh(None))
    assert r.status_code == 401, r.text
    with main.db.session() as s:
        row = s.scalars(select(SecurityEvent).order_by(SecurityEvent.id.desc())).first()
    assert row.outcome == "refused" and row.route == "/api/cc/actions/{action}", row.route
    assert "NOT_AUTHENTICATED" in row.reason
    assert counts()[0] == ev0 + 1 and counts()[1] == audit0


def test_mutating_routes_need_csrf_nonce_and_same_origin():
    c = client()
    csrf = login(c)
    mutating = [r for r in cc_routes() if r[0] != "GET" and r not in PUBLIC]
    assert len(mutating) >= 12, len(mutating)
    bad = []
    for method, path in mutating:
        for headers, want, code in ((fresh(None), 403, "CSRF"),
                                    (fresh("0" * 64), 403, "CSRF"),
                                    (fresh(csrf, Origin="https://evil.example"), 403, "CSRF"),
                                    (fresh(csrf, **{"Sec-Fetch-Site": "cross-site"}), 403,
                                     "CSRF"),
                                    ({"X-CSRF-Token": csrf}, 400, "STALE_REQUEST"),
                                    (fresh(csrf, **{"X-CC-Timestamp": str(int(time.time())
                                                                          - 3600)}),
                                     400, "STALE_REQUEST")):
            r = c.request(method, concrete(path), json={}, headers=headers)
            if r.status_code != want or r.json().get("code") != code:
                bad.append((method, path, want, r.status_code, r.text[:100]))
    assert not bad, bad[:5]


def test_replayed_nonce_is_refused():
    c = client()
    csrf = login(c)
    h = fresh(csrf)
    r1 = c.post("/api/cc/home/seen", json={}, headers=h)
    assert r1.status_code == 200, r1.text
    r2 = c.post("/api/cc/home/seen", json={}, headers=h)
    assert r2.status_code == 409 and r2.json()["code"] == "REPLAY", r2.text
    with main.db.session() as s:
        assert s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.reason.like("REPLAY%"))) >= 1


def _expire_stepup(c: TestClient) -> None:
    st = c.get("/api/cc/auth/status").json()
    with main.db.session() as s:
        row = s.scalar(select(OwnerSession).where(
            OwnerSession.public_id == st["session"]["session_id"]))
        row.stepup_until = auth._now() - timedelta(seconds=1)


def test_consequential_actions_need_step_up_but_pausing_does_not():
    c = client()
    csrf = login(c)
    _expire_stepup(c)
    assert c.get("/api/cc/auth/status").json()["stepup_valid_until"] is None
    for action in ("publication.approve", "activation.approve", "improvement.approve",
                   "challenger.approve"):
        r = c.post(f"/api/cc/actions/{action}", json={"id": 1, "why": "a b c d"},
                   headers=fresh(csrf))
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", (action, r.text)
    r = c.post("/api/cc/emergency/resume", json={"scope": "spend", "reason": "resume now"},
               headers=fresh(csrf))
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    # Tightening never waits on step-up.
    r = c.post("/api/cc/emergency/pause", json={"scope": "spend", "reason": "pause it"},
               headers=fresh(csrf))
    assert r.status_code == 200, r.text
    # Wrong step-up is refused and audited; the right one opens the window.
    r = c.post("/api/cc/auth/step-up", json={"passphrase": "wrong"}, headers=fresh(csrf))
    assert r.status_code == 401 and r.json()["code"] == "BAD_CREDENTIALS"
    r = c.post("/api/cc/auth/step-up", json={"passphrase": PASS}, headers=fresh(csrf))
    assert r.status_code == 200 and r.json()["stepup_valid_until"]
    r = c.post("/api/cc/emergency/resume", json={"scope": "spend", "reason": "resume now"},
               headers=fresh(csrf))
    assert r.status_code == 200, r.text


def test_failed_step_ups_revoke_the_session():
    c = client()
    csrf = login(c)
    last = None
    for _ in range(auth.STEPUP_FAILS_REVOKE):
        last = c.post("/api/cc/auth/step-up", json={"passphrase": "nope"}, headers=fresh(csrf))
    assert last is not None and "revoked" in last.json()["error"], last.text
    assert c.get("/api/cc/home").status_code == 401


def test_login_failures_are_rate_limited_and_audited():
    c = TestClient(main.app, base_url="https://testserver",
                   headers={"user-agent": "rate-limit-probe"})
    with main.db.session() as s:
        before = s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.kind == "login", SecurityEvent.outcome == "refused")) or 0
    codes = [c.post("/api/cc/auth/login", json={"passphrase": f"guess-{i}"}).status_code
             for i in range(auth.LOGIN_FAILS_PER_CLIENT + 1)]
    assert codes[:auth.LOGIN_FAILS_PER_CLIENT] == [401] * auth.LOGIN_FAILS_PER_CLIENT, codes
    assert codes[-1] == 429, codes
    # Even the right passphrase is refused while limited.
    assert c.post("/api/cc/auth/login", json={"passphrase": PASS}).status_code == 429
    with main.db.session() as s:
        after = s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.kind == "login", SecurityEvent.outcome == "refused"))
    assert after - before >= auth.LOGIN_FAILS_PER_CLIENT + 2
    # Clear this probe's failures so later tests are not globally limited.
    with main.db.session() as s:
        s.query(SecurityEvent).filter(SecurityEvent.kind == "login").delete()


def test_login_is_json_and_same_origin_only():
    c = client()
    r = c.post("/api/cc/auth/login", data={"passphrase": PASS})
    assert r.status_code == 400, r.text
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS},
               headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "CSRF", r.text


def test_cookie_flags_and_session_listing_and_revocation():
    c1, c2 = client(), client()
    r = c1.post("/api/cc/auth/login", json={"passphrase": PASS, "device_label": "phone"})
    cookie = r.headers["set-cookie"]
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "__Host-bl_cc="):
        assert flag.lower() in cookie.lower(), (flag, cookie)
    csrf1 = r.json()["csrf_token"]
    csrf2 = login(c2, device_label="laptop")
    sessions = c1.get("/api/cc/account/sessions").json()["sessions"]
    assert sessions and sum(1 for s_ in sessions if s_["current"]) == 1
    other = c2.get("/api/cc/auth/status").json()["session"]["session_id"]
    r = c1.post(f"/api/cc/account/sessions/{other}/revoke", json={}, headers=fresh(csrf1))
    assert r.status_code == 200, r.text
    assert c2.get("/api/cc/home").status_code == 401
    assert c2.post("/api/cc/home/seen", json={}, headers=fresh(csrf2)).status_code == 401
    r = c1.post("/api/cc/auth/logout", json={}, headers=fresh(csrf1))
    assert r.status_code == 200
    assert c1.get("/api/cc/auth/status").json()["authenticated"] is False


def test_totp_is_required_when_configured():
    os.environ[auth.TOTP_VAR] = TOTP_SECRET
    try:
        c = client()
        r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
        assert r.status_code == 401
        r = c.post("/api/cc/auth/login", json={"passphrase": PASS, "totp": "000000"
                                               if auth.totp_code(TOTP_SECRET) != "000000"
                                               else "111111"})
        assert r.status_code == 401
        r = c.post("/api/cc/auth/login",
                   json={"passphrase": PASS, "totp": auth.totp_code(TOTP_SECRET)})
        assert r.status_code == 200, r.text
        assert c.get("/api/cc/auth/status").json()["totp_required"] is True
    finally:
        os.environ.pop(auth.TOTP_VAR, None)
        with main.db.session() as s:
            s.query(SecurityEvent).filter(SecurityEvent.kind == "login").delete()
    # RFC 6238 test vector (SHA-1, T=59 -> 94287082, 8 digits; 6-digit truncation 287082).
    key = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert auth.totp_code(key, 59) == "287082"


def test_unset_operator_credential_closes_the_command_center():
    c = client()
    csrf = login(c)
    os.environ.pop(opsauth.TOKEN_VAR)
    try:
        assert c.get("/api/cc/home").status_code == 503
        assert c.post("/api/cc/emergency/pause", json={}, headers=fresh(csrf)).status_code == 503
        assert c.get("/api/cc/auth/status").status_code == 200
    finally:
        os.environ[opsauth.TOKEN_VAR] = OPS


def test_login_closed_when_no_passphrase_hash_is_configured():
    saved = os.environ.pop(auth.PASSPHRASE_VAR)
    try:
        c = client()
        r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
        assert r.status_code == 503 and r.json()["code"] == "LOGIN_NOT_CONFIGURED"
        assert c.get("/api/cc/auth/status").json()["login_configured"] is False
    finally:
        os.environ[auth.PASSPHRASE_VAR] = saved


def test_passphrase_hash_is_salted_and_never_stored_in_sessions():
    h1, h2 = auth.hash_passphrase("same"), auth.hash_passphrase("same")
    assert h1 != h2 and h1.startswith("pbkdf2_sha256$600000$")
    c = client()
    login(c)
    token = c.cookies.get(auth.COOKIE)
    assert token
    with main.db.session() as s:
        hashes = list(s.scalars(select(OwnerSession.token_hash)))
    assert hashes and token not in hashes


def test_refusals_never_echo_secrets():
    c = client()
    r = c.post("/api/cc/auth/login", json={"passphrase": "attempt-" + OPS})
    assert OPS not in r.text and PASS not in r.text
    with main.db.session() as s:
        s.query(SecurityEvent).filter(SecurityEvent.kind == "login").delete()


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
