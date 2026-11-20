"""W4-PRODDIAG: an Etsy credential refusal is reported, not retried into dead letters.

Production 2026-10-10 (fcb982d): `etsy.probe` recorded `ping returned HTTP 403` (the gates
etsy_api, etsy_shop and benchmark_observation closed, correctly), and every two-hourly
`mjs.scan` sent the same refused key to `find_shops`, raised ReadFailed, was retried until
dead, and failed /api/verify's no_unexpected_dead_letters_in_24h. The refusal is external;
turning it into dead letters (and repeated requests with a refused key) was the code defect.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_proddiag.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-PRODDIAG harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.intel import benchmarks, observe  # noqa: E402
from brambleloop.intel import etsy_public as ep  # noqa: E402

ENV = {ep.KEYSTRING_VAR: "k", ep.SECRET_VAR: "s"}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/pd.sqlite")
    db.create_all()
    benchmarks.seed(db)
    return db


@dataclass
class _R:
    status: int
    body: dict
    headers: dict


class _Fixed:
    def __init__(self, status: int, body: dict | None = None):
        self.status, self.body, self.calls = status, body or {}, 0

    def request(self, method, url, *, headers, body=None, timeout=20.0):
        assert method == "GET", "read-only"
        self.calls += 1
        return _R(self.status, self.body, {})


def _record_probe(db, detail: dict):
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="ping",
                       detail=detail))


def test_read_failed_carries_status_and_probe_records_it():
    reader = ep.PublicReader(_Fixed(403), env=ENV, sleep=lambda _s: None)
    try:
        reader.get("ping")
    except ep.ReadFailed as e:
        assert e.status == 403 and e.credential_refused
    else:
        raise AssertionError("403 did not raise")
    db = _db()
    rec = ep.probe(db, env=ENV, transport=_Fixed(403))
    assert rec["ok"] is False and rec["status"] == 403, rec
    assert ep.auth_refused(ep.last_probe(db))
    assert "k" not in str(rec.get("reason", "")).split(), "credential never in the record"
    assert not ep.usable(db)


def test_auth_refused_reads_legacy_reason_text_and_ignores_other_failures():
    legacy = {"ok": False, "reason": "ReadFailed: ping returned HTTP 403 — Etsy v3 requires "
                                     "x-api-key as keystring:shared_secret; check X"}
    assert ep.auth_refused(legacy)
    assert ep.auth_refused({"ok": False, "status": 401, "reason": ""})
    assert not ep.auth_refused({"ok": False, "reason": "ping failed 4 times: HTTP 503"})
    assert not ep.auth_refused({"ok": True, "status": 403})
    assert not ep.auth_refused(None)


def test_scan_does_not_knock_after_a_refused_probe():
    db = _db()
    _record_probe(db, {"at": "2026-10-10T00:01:55+00:00", "endpoint": "ping", "ok": False,
                       "reason": "ReadFailed: ping returned HTTP 403 — check X"})
    t = _Fixed(200, {"results": []})
    out = observe.scan_or_explain(db, env=ENV, transport=t, adaptive=False)
    assert out["ran"] is False and out["credential_refused"] is True, out
    assert "403" in out["reason"] and out["substituted"] is False
    assert t.calls == 0, "a refused credential was sent to Etsy again"


def test_scan_refused_mid_run_is_reported_not_raised():
    db = _db()  # no probe recorded: the refusal arrives during the scan itself
    t = _Fixed(403)
    out = observe.scan_or_explain(db, env=ENV, transport=t, adaptive=False)
    assert out["ran"] is False and out["credential_refused"] is True, out
    assert t.calls == 1, "a 401/403 is not retried"


def test_transient_failures_still_raise_for_the_job_retry():
    db = _db()
    t = _Fixed(503)
    try:
        observe.scan(db, ep.PublicReader(t, env=ENV, max_attempts=2, sleep=lambda _s: None),
                     env=ENV)
    except ep.ReadFailed as e:
        assert not e.credential_refused
    else:
        raise AssertionError("a server fault was swallowed")


def test_scan_resumes_once_a_probe_succeeds():
    db = _db()
    _record_probe(db, {"ok": False, "status": 403, "reason": "ping returned HTTP 403"})
    _record_probe(db, {"ok": True, "endpoint": "ping"})
    t = _Fixed(200, {"results": []})
    try:
        observe.scan_or_explain(db, env=ENV, transport=t, adaptive=False)
    except ep.ReadFailed:
        pass  # the exact-shop match fails on an empty result; what matters is it asked
    assert t.calls >= 1, "the scan stayed parked after the credential worked again"


def test_mjs_scan_handler_completes_with_the_refusal_named():
    from brambleloop.runtime import release

    src = Path(release.__file__).read_text()
    i = src.index('def handle_mjs_scan')
    body = src[i:src.index("\ndef ", i + 10)]
    assert '"credential_refused": bool(outcome.get("credential_refused"))' in body


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:800]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
