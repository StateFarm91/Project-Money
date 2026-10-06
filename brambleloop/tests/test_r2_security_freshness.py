"""R2 security, audit ddf9c6e M2: X-CC-Timestamp must be a finite number of unix seconds
within the skew window (fail closed), and a nonce is retained for longer than any timestamp
that could still pass, so a purged nonce can never be replayed.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_security_freshness.py
"""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

from r2_security_harness import DB, auth, client, fresh, login, run  # noqa: I001

from brambleloop.app.command_center.models import RequestNonce

NON_FINITE = ("nan", "NaN", "-nan", "inf", "-inf", "Infinity", "-Infinity", "1e999",
              "not-a-number", "", "0x10", "None")


def test_non_finite_or_non_numeric_timestamps_are_refused():
    c = client()
    csrf = login(c)
    assert NON_FINITE
    for ts in NON_FINITE:
        r = c.post("/api/cc/home/seen", json={},
                   headers=fresh(csrf, **{"X-CC-Timestamp": ts}))
        assert r.status_code == 400 and r.json()["code"] == "STALE_REQUEST", (ts, r.text)
    # Control: a current timestamp is accepted.
    assert c.post("/api/cc/home/seen", json={}, headers=fresh(csrf)).status_code == 200


def test_a_purged_nonce_cannot_be_replayed():
    c = client()
    csrf = login(c)
    nonce = uuid.uuid4().hex
    hdr = {"X-CC-Nonce": nonce, "X-CC-Timestamp": str(int(time.time())), "X-CSRF-Token": csrf}
    assert c.post("/api/cc/home/seen", json={}, headers=hdr).status_code == 200
    assert c.post("/api/cc/home/seen", json={}, headers=hdr).status_code == 409
    # Age the nonce past retention and trigger the purge.
    with DB.session() as s:
        n = 0
        for row in s.query(RequestNonce).filter(RequestNonce.nonce == nonce):
            row.at = auth._now() - auth.NONCE_RETENTION - timedelta(minutes=1)
            n += 1
    assert n == 1
    assert c.post("/api/cc/home/seen", json={}, headers=fresh(csrf)).status_code == 200
    # The identical captured request now carries a timestamp outside the window: refused.
    hdr["X-CC-Timestamp"] = str(int(time.time()) - int(auth.NONCE_RETENTION.total_seconds())
                                - 60)
    r = c.post("/api/cc/home/seen", json={}, headers=hdr)
    assert r.status_code == 400 and r.json()["code"] == "STALE_REQUEST", r.text
    # The audit's exact repro: a captured request whose timestamp is "nan" replayed after
    # its nonce was purged.
    hdr["X-CC-Timestamp"] = "nan"
    r = c.post("/api/cc/home/seen", json={}, headers=hdr)
    assert r.status_code == 400 and r.json()["code"] == "STALE_REQUEST", r.text


def test_retention_outlives_the_freshness_window():
    assert auth.NONCE_RETENTION > timedelta(seconds=2 * auth.NONCE_SKEW_SECONDS)


if __name__ == "__main__":
    run(globals())
