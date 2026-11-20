"""Re-audit L-1 and L-2 (INDEPENDENT_REAUDIT_7421ef6), each as a permanent test.

* L-1 -- an accepted TOTP code was not marked used, so a captured passphrase + code pair could
  be replayed for ~90 s. Each time-step is now accepted once per owner (login and step-up
  alike), a wrong passphrase never burns the code, and `/api/cc/auth/status` states whether a
  second factor is configured without revealing anything secret. TOTP stays optional in code.
* L-2 -- the login throttle counted past failures, then ran the slow PBKDF2 check, then wrote
  the failure: a concurrent burst all passed the throttle. An attempt is now reserved (counted)
  before verification and withdrawn on success; only wrong credentials extend a lockout.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_auditfix_cc_auth.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_auditfix_cc_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
os.environ.pop("BRAMBLELOOP_TRUSTED_PROXY_HOPS", None)
os.environ.pop("BRAMBLELOOP_CLIENT_IP_HEADER", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the command-center harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import RequestNonce, SecurityEvent  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

OPS = "k" * 40
PASS = "owner passphrase for the harness only"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # the RFC 6238 documentation example, not a credential
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()


def client() -> TestClient:
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)


def _clear_logins():
    with main.db.session() as s:
        s.query(SecurityEvent).filter(SecurityEvent.kind == "login").delete()


def _login_rows(reason_prefix: str = auth.FAILED_LOGIN_CODE) -> int:
    with main.db.session() as s:
        return int(s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.kind == "login", SecurityEvent.outcome == "refused",
            SecurityEvent.reason.like(f"{reason_prefix}%"))) or 0)


def _reserved_rows() -> int:
    with main.db.session() as s:
        return int(s.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.reason == auth.RESERVED_REASON)) or 0)


def _forget_used_steps():
    # Each test starts from a clean owner step record: tests in one process share the 30 s
    # step, and a code legitimately spent by the previous test is (correctly) refused here.
    with main.db.session() as s:
        s.query(RequestNonce).filter(
            RequestNonce.session_public_id == auth.TOTP_OWNER_KEY).delete()


class _totp:
    def __enter__(self):
        os.environ[auth.TOTP_VAR] = TOTP_SECRET
        _forget_used_steps()

    def __exit__(self, *a):
        os.environ.pop(auth.TOTP_VAR, None)
        _clear_logins()
        _forget_used_steps()


# ---- L-1 -------------------------------------------------------------------------------


def test_l1_a_totp_code_is_accepted_once_at_login():
    with _totp():
        code = auth.totp_code(TOTP_SECRET)
        r = client().post("/api/cc/auth/login", json={"passphrase": PASS, "totp": code})
        assert r.status_code == 200, r.text
        # The same passphrase + code pair, replayed from another browser inside its window.
        r = client().post("/api/cc/auth/login", json={"passphrase": PASS, "totp": code})
        assert r.status_code == 401, (r.status_code, r.text)
        assert r.json()["code"] == auth.FAILED_LOGIN_CODE


def test_l1_a_login_code_cannot_be_replayed_for_step_up():
    with _totp():
        code = auth.totp_code(TOTP_SECRET)
        c = client()
        r = c.post("/api/cc/auth/login", json={"passphrase": PASS, "totp": code})
        assert r.status_code == 200, r.text
        csrf = r.json()["csrf_token"]
        import uuid
        h = {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
             "X-CC-Timestamp": str(int(time.time()))}
        r = c.post("/api/cc/auth/step-up", json={"passphrase": PASS, "totp": code}, headers=h)
        assert r.status_code == 401, (r.status_code, r.text)


def test_l1_a_wrong_passphrase_does_not_burn_the_owners_code():
    with _totp():
        code = auth.totp_code(TOTP_SECRET)
        assert auth.verify_owner("wrong passphrase entirely", code, db=main.db) is False
        assert auth.verify_owner(PASS, code, db=main.db) is True
        assert auth.verify_owner(PASS, code, db=main.db) is False  # replay refused


def test_l1_steps_are_recorded_and_distinct_steps_are_independent():
    with _totp():
        t = time.time()
        step = int(t // 30)
        # A step far from now is never accepted, and consuming one step leaves others usable.
        assert auth.consume_totp_step(main.db, step + 1000) is True
        assert auth.consume_totp_step(main.db, step + 1000) is False
        assert auth.consume_totp_step(main.db, step + 1001) is True


def test_l1_totp_stays_optional_and_the_status_says_so_plainly():
    os.environ.pop(auth.TOTP_VAR, None)
    body = client().get("/api/cc/auth/status").json()
    assert body["totp_required"] is False
    assert body["second_factor"]["configured"] is False
    assert "passphrase only" in body["second_factor"]["summary"]
    # Optional in code: passphrase-only login still works when the owner has not set TOTP.
    assert client().post("/api/cc/auth/login", json={"passphrase": PASS}).status_code == 200
    with _totp():
        r = client().get("/api/cc/auth/status")
        sf = r.json()["second_factor"]
        assert sf["configured"] is True and sf["kind"] == "totp" and sf["replay_protected"]
        assert TOTP_SECRET not in r.text and auth.totp_code(TOTP_SECRET) not in r.text
    _clear_logins()


# ---- L-2 -------------------------------------------------------------------------------


class _Req:
    """The two things the throttle reads from a request: the peer and the headers."""

    class _H(dict):
        def getlist(self, _k):
            return []

    def __init__(self, ip="203.0.113.7"):
        self.client = type("C", (), {"host": ip})()
        self.headers = self._H()
        self.scope = {}
        self.method = "POST"
        self.url = type("U", (), {"path": "/api/cc/auth/login"})()


def test_l2_concurrent_reservations_never_exceed_the_per_client_limit():
    _clear_logins()
    granted, limited, errors = [], [], []
    barrier = threading.Barrier(16)

    def one():
        try:
            barrier.wait()
            aid, why = auth.reserve_login_attempt(main.db, _Req())
            (granted if aid is not None else limited).append(aid or why)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=one) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert 1 <= len(granted) <= auth.LOGIN_FAILS_PER_CLIENT, (granted, limited)
    # Refused-for-limit reservations are withdrawn: only granted attempts are counted.
    assert _login_rows() == len(granted), (_login_rows(), granted)
    _clear_logins()


def test_l2_a_concurrent_wrong_credential_burst_is_held_to_the_limit():
    _clear_logins()
    real = auth.verify_owner

    def slow_wrong(*_a, **_k):
        time.sleep(0.4)  # the PBKDF2 window the race lived in
        return False

    auth.verify_owner = slow_wrong
    statuses, errors = [], []
    barrier = threading.Barrier(12)

    def one():
        try:
            c = client()
            barrier.wait()
            r = c.post("/api/cc/auth/login", json={"passphrase": "a wrong guess here"})
            statuses.append(r.status_code)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    try:
        threads = [threading.Thread(target=one) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        auth.verify_owner = real
    try:
        assert not errors, errors
        verified = statuses.count(401)
        assert 1 <= verified <= auth.LOGIN_FAILS_PER_CLIENT, statuses
        assert statuses.count(429) == len(statuses) - verified, statuses
        assert _login_rows() == verified and _reserved_rows() == 0
    finally:
        _clear_logins()


def test_l2_success_releases_the_reservation_and_failure_is_recorded_once():
    _clear_logins()
    r = client().post("/api/cc/auth/login", json={"passphrase": "not the passphrase"})
    assert r.status_code == 401 and r.json()["code"] == auth.FAILED_LOGIN_CODE
    assert _login_rows() == 1 and _reserved_rows() == 0
    r = client().post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    assert _login_rows() == 1 and _reserved_rows() == 0
    _clear_logins()


def test_l2_only_wrong_credentials_extend_the_lockout():
    _clear_logins()
    for _ in range(auth.LOGIN_FAILS_PER_CLIENT):
        assert client().post("/api/cc/auth/login",
                             json={"passphrase": "wrong guess"}).status_code == 401
    for _ in range(3):
        r = client().post("/api/cc/auth/login", json={"passphrase": PASS})
        assert r.status_code == 429, r.text
    # Rate-limited refusals added no counted failure (they are not guesses).
    assert _login_rows() == auth.LOGIN_FAILS_PER_CLIENT and _reserved_rows() == 0
    _clear_logins()


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
            import traceback
            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
