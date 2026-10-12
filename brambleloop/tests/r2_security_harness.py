"""Shared harness for the R2 security regression tests (tests/test_r2_security_*.py).

Real FastAPI app, TestClient, fresh SQLite DB, no network. Each test file imports this module
first so its environment is set before the app is imported.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import socket
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TMP = tempfile.mkdtemp(prefix="r2_security_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'r2.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in ("BRAMBLELOOP_TRUSTED_PROXY_HOPS", "BRAMBLELOOP_CLIENT_IP_HEADER",
           "BRAMBLELOOP_PUBLIC_ORIGIN"):
    os.environ.pop(_k, None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the r2 security harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

OPS = "r" * 40
PASS = "owner passphrase for the r2 security harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db


def client(peer: str = "testclient", **kw) -> TestClient:
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False,
                      client=(peer, 50000), **kw)


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


def clear_login_events() -> None:
    from brambleloop.app.command_center.models import SecurityEvent

    with DB.session() as s:
        s.query(SecurityEvent).delete()


def run(globals_: dict) -> None:
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals_.items()) if n.startswith("test_") and callable(f)]
    assert tests, "no tests collected"
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
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
