"""W4-CCPACKET (F-878): the Launch-0 launch packet served in the Command Center.

GET /api/cc/launch/packet serves `launch.packet.build(db, sha=build.commit())` behind the
existing `/api/cc/*` gate (default-deny: owner session required, the operator bearer token is
not one), read-only (no row written by a packet read, no mutating method), cached for at most
`TTL` so page loads cannot stack full assessments, its verdict kept verbatim and mapped onto
the CC status vocabulary (READY -> OK; UNKNOWN never passing), and rendered on the Completion
view with its own as-of.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_ccpacket.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_ccpacket_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-CCPACKET harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth, launch_packet, providers  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

OPS = "p" * 40
PASS = "owner passphrase for the W4-CCPACKET harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
PATH = "/api/cc/launch/packet"
# Rows the owner-session gate itself touches on every request (session last_seen, login).
_AUTH_TABLES = {"cc_owner_sessions", "cc_security_events", "cc_nonces"}


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c


def _rows() -> dict:
    names = [n for n in inspect(DB.engine).get_table_names() if n not in _AUTH_TABLES]
    with DB.engine.connect() as conn:
        return {n: conn.execute(text(f'SELECT COUNT(*) FROM "{n}"')).scalar() for n in names}


def test_default_deny_without_owner_session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.get(PATH)
    assert r.status_code == 401, (r.status_code, r.text[:200])
    r = c.get(PATH, headers={"Authorization": f"Bearer {OPS}"})
    assert r.status_code == 401, "the operator bearer token is not an owner session"
    assert "packet" not in r.text


def test_real_packet_is_served_read_only_with_verdict_and_as_of():
    launch_packet.BUILD = None
    launch_packet.reset()
    launch_packet.WAIT_S = 600  # this test reads the real packet, so it waits for the build
    c = session()
    before = _rows()
    t0 = time.monotonic()
    r = c.get(PATH)
    took = time.monotonic() - t0
    assert r.status_code == 200, r.text[:500]
    assert r.headers.get("cache-control") == "no-store"
    assert _rows() == before, "reading the launch packet wrote a row"
    data = r.json()
    assert data["tab"] == "LAUNCH_PACKET" and data["generated_at"]
    env = data["sections"]["packet"]
    assert env["status"] in providers.STATUSES, env
    if env["status"] == "UNKNOWN" and not env.get("verdict"):
        raise AssertionError(f"packet build failed: {env.get('reason')}")
    assert env["verdict"] in ("READY", "BLOCKED", "UNKNOWN"), env["verdict"]
    assert env["as_of"] and env["candidate_sha"], env
    # A fresh shadow database has nothing certified or listed: never READY, never OK.
    assert env["verdict"] != "READY" and env["status"] != "OK", env["verdict"]
    assert env["reason"], "a non-OK packet says why"
    assert env["items"], "every Launch-0 product is listed"
    for it in env["items"]:
        assert it["status"] in providers.STATUSES and it["title"], it
    assert env["phase"]["phase"] == "shadow"
    print(f"   (packet build took {took:.1f}s)")
    launch_packet.WAIT_S = 2.0
    # Read-only: no mutating method exists on the route.
    assert c.post(PATH, json={}).status_code in (403, 404, 405)


def test_packet_is_cached_for_ttl_and_build_failure_is_unknown():
    calls = []

    def fake(db, *, sha, repo_root=None):
        calls.append(sha)
        return {"verdict": "READY", "generated_at": "2026-10-10T00:00:00+00:00",
                "candidate_sha": sha, "products": [{"slug": "x", "version": "1.0.0",
                                                    "candidate": "x", "publishable_now": True,
                                                    "open_gates": [], "unknown": []}],
                "phase": {"phase": "shadow", "agree": True}, "owner_queue": {}}

    launch_packet.BUILD = fake
    launch_packet.reset()
    try:
        c = session()
        a = c.get(PATH).json()["sections"]["packet"]
        b = c.get(PATH).json()["sections"]["packet"]
        assert len(calls) == 1, "a second read inside the TTL rebuilt the packet"
        assert a["status"] == "OK" and a["verdict"] == "READY" and "reason" not in a, a
        assert b["as_of"] == "2026-10-10T00:00:00+00:00", "the packet's own time is shown"
        assert a["items"][0]["status"] == "OK"

        def boom(db, *, sha, repo_root=None):
            raise RuntimeError("cannot read")

        launch_packet.BUILD = boom
        launch_packet.reset()
        u = c.get(PATH).json()
        env = u["sections"]["packet"]
        assert env["status"] == "UNKNOWN" and "RuntimeError" in env["reason"], env
        assert env["as_of"] is None and env["items"] == []
        assert u["status"] == "UNKNOWN"
    finally:
        launch_packet.BUILD = None
        launch_packet.reset()


def test_slow_build_runs_off_the_request_path_single_flight():
    import threading

    gate = threading.Event()
    calls = []

    def slow(db, *, sha, repo_root=None):
        calls.append(1)
        gate.wait(30)
        return {"verdict": "BLOCKED", "generated_at": "2026-10-10T01:00:00+00:00",
                "candidate_sha": sha, "products": [], "products_blocked": ["x"],
                "phase": {"phase": "shadow", "agree": True}, "owner_queue": {}}

    launch_packet.BUILD = slow
    launch_packet.reset()
    old = launch_packet.WAIT_S
    launch_packet.WAIT_S = 0.2
    try:
        c = session()
        t0 = time.monotonic()
        first = c.get(PATH).json()["sections"]["packet"]
        again = c.get(PATH).json()["sections"]["packet"]
        assert time.monotonic() - t0 < 10, "the request waited on the full build"
        assert first["status"] == "UNKNOWN" and "being generated" in first["reason"], first
        assert first["as_of"] is None and again["status"] == "UNKNOWN"
        assert len(calls) == 1, "concurrent reads started a second build"
        gate.set()
        for _ in range(100):
            done = c.get(PATH).json()["sections"]["packet"]
            if done.get("verdict"):
                break
            time.sleep(0.1)
        assert done["status"] == "BLOCKED" and done["reason"], done
        assert done["as_of"] == "2026-10-10T01:00:00+00:00"
        assert len(calls) == 1
    finally:
        gate.set()
        launch_packet.WAIT_S = old
        launch_packet.BUILD = None
        launch_packet.reset()


def test_pwa_renders_packet_on_completion_read_only():
    js = (STATIC / "js" / "views" / "completion.js").read_text()
    api = (STATIC / "js" / "api.js").read_text()
    assert "packetCard(pk)" in js and "api.launchPacket()" in js
    assert 'launchPacket: () => `${API_BASE}/launch/packet`' in api
    card = js[js.index("export function packetCard"):js.index("export async function render")]
    assert "freshness(env.as_of" in card
    for bad in ("innerHTML", "insertAdjacentHTML", "api.action", "post(", "guardedAction"):
        assert bad not in card, bad
    sw = (STATIC / "sw.js").read_text()
    assert "js/views/completion.js" in sw


if __name__ == "__main__":
    t0 = time.monotonic()
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
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
