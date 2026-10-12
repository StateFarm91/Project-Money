"""W4-FMEND (F-878): the launch packet is served on an operator-gated runtime GET.

`GET /api/launch/packet` (app/main.py) serves the same packet as the owner Command Center
(`command_center.launch_packet.view` -> `launch.packet.build(db, sha=build.commit())`) behind
the operator credential (`security.OPERATOR_GET_ROUTES`). Because the route calls with the
database, `launch/packet.py` is reached from a live root under `build2.reachability`'s rules,
which is the matrix's F-878 gap ("not reached from a runtime root").

NOT in candidate c131f07: this wiring is for the next release.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_fmend_packet_route.py
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

_TMP = tempfile.mkdtemp(prefix="w4_fmend_packet_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'p.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-FMEND harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.app import main, security  # noqa: E402
from brambleloop.app.command_center import launch_packet  # noqa: E402
from brambleloop.core import build as build_mod  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

OPS = "f" * 40
os.environ[opsauth.TOKEN_VAR] = OPS
main.db.create_all()
PATH = "/api/launch/packet"


def client():
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)


def test_the_route_is_operator_gated():
    assert PATH in security.OPERATOR_GET_ROUTES
    c = client()
    assert c.get(PATH).status_code == 401
    assert c.get(PATH, headers={"Authorization": "Bearer " + "x" * 40}).status_code == 401
    assert c.post(PATH, json={}, headers={"Authorization": f"Bearer {OPS}"}).status_code in (
        404, 405)


def test_the_route_serves_the_packet_for_the_running_build():
    calls = []

    def fake(db, *, sha, repo_root=None):
        calls.append(sha)
        return {"verdict": "BLOCKED", "generated_at": "2026-10-11T00:00:00+00:00",
                "candidate_sha": sha,
                "products": [{"slug": "x", "version": "1.0.0", "candidate": "x",
                              "publishable_now": False, "unknown": [],
                              "open_gates": [{"section": "listing", "state": "FAIL"}]}],
                "products_blocked": ["x"], "phase": {"phase": "shadow", "agree": True},
                "owner_queue": {}}

    launch_packet.BUILD = fake
    launch_packet.reset()
    try:
        r = client().get(PATH, headers={"Authorization": f"Bearer {OPS}"})
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        env = data["sections"]["packet"]
        assert data["tab"] == "LAUNCH_PACKET"
        assert calls == [build_mod.commit()], calls
        assert env["candidate_sha"] == build_mod.commit()
        assert env["verdict"] == "BLOCKED" and env["status"] == "BLOCKED" and env["reason"]
    finally:
        launch_packet.BUILD = None
        launch_packet.reset()


def test_an_unreadable_packet_is_unknown_never_passing():
    def boom(db, *, sha, repo_root=None):
        raise RuntimeError("cannot read")

    launch_packet.BUILD = boom
    launch_packet.reset()
    try:
        data = client().get(PATH, headers={"Authorization": f"Bearer {OPS}"}).json()
        assert data["status"] == "UNKNOWN", data
        assert "RuntimeError" in data["sections"]["packet"]["reason"]
    finally:
        launch_packet.BUILD = None
        launch_packet.reset()


def test_the_packet_builder_is_reached_from_a_live_root():
    from brambleloop.build2 import reachability

    reachability.clear_cache()
    for mod in ("launch/packet.py", "app/command_center/launch_packet.py"):
        got = reachability.reached(mod)
        assert got.get("reached") is True, (mod, got)
    fn = reachability.function_reached("launch/packet.py", "build")
    assert fn.get("reached") is True, fn


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
