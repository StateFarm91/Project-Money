"""W4-SECPATCH2: review of SECPATCH 4ff953da, F1 and F2.

F1: the public projection and the owner-text scrub were keyed on the raw `scope["path"]`.
Served under a root path, `/x/api/status` routed to `api_status` and matched no projection,
so an anonymous caller got the full body. They are now keyed on the router's path.
F2: two Authorization headers were read first-wins by the gate and last-wins by the
middlewares; any request carrying more than one is now refused with 400.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_w4_secpatch2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import asyncio
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="secpatch2_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'sp2.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
OPS = "s" * 40
os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS


def _no_network(*_a, **_k):
    raise OSError("network refused by the secpatch2 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()


def _call(path: str, *, root_path: str = "", headers=()) -> tuple[int, bytes]:
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "GET", "scheme": "https", "server": ("testserver", 443),
             "client": ("203.0.113.9", 5555), "root_path": root_path, "path": path,
             "raw_path": path.encode(), "query_string": b"",
             "headers": [(b"host", b"testserver"), *headers]}
    sent: list[dict] = []
    done = {"in": False}

    async def receive():
        if done["in"]:
            await asyncio.sleep(3600)
        done["in"] = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(main.app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


def _fields(body: bytes) -> set[str]:
    data = json.loads(body)
    return set(data) if isinstance(data, dict) else set()


def test_the_projection_holds_under_a_root_path():
    allowed = set(security.PUBLIC_PROJECTIONS["/api/status"])
    plain_status, plain = _call("/api/status")
    assert plain_status == 200 and _fields(plain) <= allowed, _fields(plain) - allowed
    status, body = _call("/x/api/status", root_path="/x")
    assert status == 200, body[:300]
    assert _fields(body) <= allowed, sorted(_fields(body) - allowed)
    # positive control: the operator credential still sees the full view under the root path
    status, full = _call("/x/api/status", root_path="/x",
                         headers=[(b"authorization", f"Bearer {OPS}".encode())])
    assert status == 200 and _fields(full) - allowed, "the operator view lost its fields"


def test_route_path_strips_the_root_path():
    assert security.route_path({"root_path": "/x", "path": "/x/api/status"}) == "/api/status"
    assert security.route_path({"root_path": "", "path": "/api/status"}) == "/api/status"


def test_two_authorization_headers_are_refused():
    for order in ([b"Bearer junk", f"Bearer {OPS}".encode()],
                  [f"Bearer {OPS}".encode(), b"Bearer junk"]):
        status, body = _call("/api/status",
                             headers=[(b"authorization", order[0]),
                                      (b"authorization", order[1])])
        assert status == 400 and b"more than one Authorization" in body, (status, body)
    status, _ = _call("/api/status", headers=[(b"authorization", f"Bearer {OPS}".encode())])
    assert status == 200
    assert security.scope_authorization({"headers": [(b"authorization", b"a"),
                                                     (b"authorization", b"b")]}) is None


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
