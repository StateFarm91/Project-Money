"""R2 security, audit ddf9c6e M1: an unauthenticated party cannot lock the real owner out,
and brute force stays bounded.

* X-Forwarded-For is trusted only through a configured proxy hop count (default: never).
* Only wrong credentials count toward a limit; 429/CSRF/malformed refusals do not.
* The global limit refuses unknown devices *before* verification (brute-force resistance)
  but never blocks a trusted device (cookie from an earlier login) or a login carrying an
  operator-minted single-use recovery code -- the passphrase is still required for both.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_security_login_lockout.py
"""
from __future__ import annotations

import os
from datetime import timedelta

from r2_security_harness import (DB, OPS, PASS, auth, clear_login_events, client,  # noqa: I001
                                 run)

from brambleloop.app.command_center.models import SecurityEvent

ATTEMPTS = 1000
HOPS_VAR = "BRAMBLELOOP_TRUSTED_PROXY_HOPS"  # literal: documented deployment contract
DEVICE_COOKIE = "__Host-bl_dev"


def _hops(n: int | None):
    if n is None:
        os.environ.pop(HOPS_VAR, None)
    else:
        os.environ[HOPS_VAR] = str(n)


def _owner_device_cookie() -> str:
    """Log the owner in once (before any attack) and return the trusted-device cookie."""
    c = client(peer="192.0.2.10")
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    dev = c.cookies.get(DEVICE_COOKIE)
    assert dev, "a successful login must issue the trusted-device cookie"
    return dev


def _mint_recovery() -> str:
    c = client(peer="192.0.2.99")
    assert c.post("/api/owner/cc/login-recovery").status_code == 401  # operator gate
    r = c.post("/api/owner/cc/login-recovery", headers={"Authorization": f"Bearer {OPS}"})
    assert r.status_code == 200, r.text
    return r.json()["recovery_code"]


def test_spoofed_forwarded_for_is_ignored_without_a_trusted_proxy():
    clear_login_events()
    _hops(None)
    atk = client(peer="198.51.100.50")
    codes = [atk.post("/api/cc/auth/login", json={"passphrase": f"guess{i}"},
                      headers={"X-Forwarded-For": f"203.0.113.{i}",
                               "User-Agent": f"ua{i}"}).status_code for i in range(12)]
    assert codes[:auth.LOGIN_FAILS_PER_CLIENT] == [401] * auth.LOGIN_FAILS_PER_CLIENT, codes
    assert set(codes[auth.LOGIN_FAILS_PER_CLIENT:]) == {429}, codes
    # The owner, from her own address, is not affected (global failures are only 5).
    assert client(peer="192.0.2.20").post(
        "/api/cc/auth/login", json={"passphrase": PASS}).status_code == 200


def test_railway_hop_takes_the_right_most_entry():
    clear_login_events()
    _hops(1)
    try:
        atk = client(peer="10.0.0.1")  # the platform proxy
        codes = [atk.post("/api/cc/auth/login", json={"passphrase": f"g{i}"},
                          headers={"X-Forwarded-For": f"203.0.113.{i}, 198.51.100.7"}
                          ).status_code for i in range(10)]
        assert codes[:auth.LOGIN_FAILS_PER_CLIENT] == [401] * auth.LOGIN_FAILS_PER_CLIENT
        assert set(codes[auth.LOGIN_FAILS_PER_CLIENT:]) == {429}, codes
        own = client(peer="10.0.0.1").post(
            "/api/cc/auth/login", json={"passphrase": PASS},
            headers={"X-Forwarded-For": "198.51.100.7, 203.0.113.250, 192.0.2.30"})
        assert own.status_code == 200, own.text
    finally:
        _hops(None)


def test_refusals_for_being_limited_do_not_extend_the_lockout():
    clear_login_events()
    atk = client(peer="198.51.100.60")
    for i in range(auth.LOGIN_FAILS_PER_CLIENT):
        assert atk.post("/api/cc/auth/login", json={"passphrase": f"x{i}"}).status_code == 401
    for _ in range(50):
        assert atk.post("/api/cc/auth/login", json={"passphrase": "x"}).status_code == 429
    # Age only the wrong-credential failures out of the window: the 50 refusals that were
    # themselves rate-limited must not keep the client locked.
    with DB.session() as s:
        rows = s.query(SecurityEvent).filter(SecurityEvent.kind == "login",
                                             SecurityEvent.reason.like("BAD_CREDENTIALS:%"))
        n = 0
        for row in rows:
            row.at = auth._now() - auth.LOGIN_WINDOW - timedelta(minutes=1)
            n += 1
    assert n == auth.LOGIN_FAILS_PER_CLIENT, n
    assert client(peer="198.51.100.60").post(
        "/api/cc/auth/login", json={"passphrase": PASS}).status_code == 200


def test_1000_wrong_attempts_from_rotating_addresses_never_succeed_and_owner_still_logs_in():
    clear_login_events()
    dev = _owner_device_cookie()
    clear_login_events()
    _hops(1)
    try:
        codes = []
        for i in range(ATTEMPTS):
            # Distinct real-looking addresses as the proxy saw them (a botnet), each with a
            # forged left-hand X-Forwarded-For entry and a rotating user agent.
            real = f"100.{(i // 250) % 250}.{(i // 5) % 250}.{i % 5 + 1}"
            atk = client(peer="10.0.0.1")
            r = atk.post("/api/cc/auth/login", json={"passphrase": f"wrong-{i}"},
                         headers={"X-Forwarded-For": f"203.0.113.{i % 250}, {real}",
                                  "User-Agent": f"bot-{i}"})
            codes.append(r.status_code)
            assert auth.COOKIE not in r.cookies, "a wrong passphrase must never get a session"
        assert len(codes) == ATTEMPTS
        assert 200 not in codes, "a wrong passphrase succeeded"
        assert set(codes) <= {401, 429}, set(codes)
        # Brute-force budget: at most the global limit was ever verified in the window.
        assert codes.count(401) <= auth.LOGIN_FAILS_GLOBAL, codes.count(401)
        assert codes.count(429) >= ATTEMPTS - auth.LOGIN_FAILS_GLOBAL
        # A new, unknown device is refused while the global limit holds (before verification).
        stranger = client(peer="10.0.0.1").post(
            "/api/cc/auth/login", json={"passphrase": PASS},
            headers={"X-Forwarded-For": "192.0.2.77"})
        assert stranger.status_code == 429, stranger.text
        # The owner's phone (trusted device from an earlier login) still gets in.
        phone = client(peer="10.0.0.1", cookies={DEVICE_COOKIE: dev})
        r = phone.post("/api/cc/auth/login", json={"passphrase": PASS},
                       headers={"X-Forwarded-For": "192.0.2.10"})
        assert r.status_code == 200, r.text
        # ... but a trusted device still needs the passphrase.
        r = client(peer="10.0.0.1", cookies={DEVICE_COOKIE: dev}).post(
            "/api/cc/auth/login", json={"passphrase": "not it"},
            headers={"X-Forwarded-For": "192.0.2.10"})
        assert r.status_code == 401, r.text
        # A brand-new device recovers with an operator-minted single-use code.
        code = _mint_recovery()
        laptop = client(peer="10.0.0.1")
        r = laptop.post("/api/cc/auth/login", json={"passphrase": PASS, "recovery_code": code},
                        headers={"X-Forwarded-For": "192.0.2.88"})
        assert r.status_code == 200, r.text
        r = client(peer="10.0.0.1").post(
            "/api/cc/auth/login", json={"passphrase": PASS, "recovery_code": code},
            headers={"X-Forwarded-For": "192.0.2.89"})
        assert r.status_code == 429, "a recovery code is single use"
        # A forged device cookie or recovery code buys an attacker nothing.
        r = client(peer="10.0.0.1", cookies={DEVICE_COOKIE: "f" * 43}).post(
            "/api/cc/auth/login", json={"passphrase": PASS, "recovery_code": "x" * 32},
            headers={"X-Forwarded-For": "192.0.2.90"})
        assert r.status_code == 429, r.text
    finally:
        _hops(None)


def test_a_stolen_device_cookie_is_still_rate_limited_per_device():
    clear_login_events()
    dev = _owner_device_cookie()
    c = client(peer="198.51.100.70", cookies={DEVICE_COOKIE: dev})
    codes = [c.post("/api/cc/auth/login", json={"passphrase": f"n{i}"}).status_code
             for i in range(auth.LOGIN_FAILS_PER_DEVICE + 3)]
    assert codes[:auth.LOGIN_FAILS_PER_DEVICE] == [401] * auth.LOGIN_FAILS_PER_DEVICE, codes
    assert set(codes[auth.LOGIN_FAILS_PER_DEVICE:]) == {429}, codes
    clear_login_events()


if __name__ == "__main__":
    run(globals())
