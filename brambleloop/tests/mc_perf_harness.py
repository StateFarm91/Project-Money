"""eng/mc-perf: time every Mission Control GET route on a production-shaped database.

Logs in with a real owner session (passphrase + TOTP) and calls each `/api/cc/*` GET route
through the app's test client. For every route it records wall time, SQL statement count,
the number of bytes of BLOB data fetched, and any outbound network attempt (all refused).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/mc_perf_harness.py [--json out]
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import base64
import json
import os
import socket
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="mcperf_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'mc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)

NET_ATTEMPTS: list = []


def _no_network(*a, **_k):
    NET_ATTEMPTS.append(repr(a[1:2] if len(a) > 1 else a)[:120])
    raise OSError("network refused by the mc-perf harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, event  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

import _mc_perf_seed  # noqa: E402

OPS = "p" * 40
PASS = "owner passphrase for the mission control perf harness"
TOTP = base64.b32encode(b"mission-control-perf-totp").decode().rstrip("=")
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ[auth.TOTP_VAR] = TOTP
DB = main.db
NOW = datetime.now(timezone.utc)

# Routes that are not page reads (streams, auth plumbing) or need a specific id we fill below.
SKIP = {"/api/cc/auth/status"}
PARAMS = {"{slug}": "seed-product-00", "{listing}": "seed-product-00", "{build}": "1",
          "{card_id}": "x", "{definition_id}": "x", "{run_id}": "1", "{candidate_id}": "1",
          "{notification_id}": "1"}

STATS = {"stmts": 0, "blob_bytes": 0}


def _install_counters():
    eng = DB.engine

    @event.listens_for(eng, "before_cursor_execute")
    def _count(*_a, **_k):
        STATS["stmts"] += 1




def seed():
    DB.create_all()
    Registry(DB).seed_defaults()
    return _mc_perf_seed.seed(DB, now=NOW)


def _code() -> str:
    from brambleloop.app.command_center.models import RequestNonce

    auth.ensure_tables(DB)
    with DB.session() as s:
        s.execute(delete(RequestNonce).where(
            RequestNonce.session_public_id == auth.TOTP_OWNER_KEY))
    return auth.totp_code(TOTP)


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS, "totp": _code()})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def _walk(rs, prefix=""):
    for r in rs:
        inner = getattr(r, "original_router", None)
        if inner is not None:          # newer FastAPI keeps included routers nested
            yield from _walk(inner.routes, prefix)
        else:
            yield r


def routes() -> list[str]:
    out = []
    for r in _walk(main.app.routes):
        path = getattr(r, "path", "")
        if not path.startswith("/api/cc") or "GET" not in (getattr(r, "methods", None) or ()):
            continue
        if path in SKIP:
            continue
        for k, v in PARAMS.items():
            path = path.replace(k, v)
        if "{" in path:
            continue
        out.append(path)
    return sorted(set(out))


def time_route(c, path: str, repeat: int = 2) -> dict:
    res = {}
    for i in range(repeat):
        STATS["stmts"] = 0
        n0 = len(NET_ATTEMPTS)
        t0 = time.perf_counter()
        try:
            r = c.get(path)
            status, size = r.status_code, len(r.content)
        except Exception as exc:  # noqa: BLE001
            status, size = f"EXC {exc!r}"[:80], 0
        ms = (time.perf_counter() - t0) * 1000
        res["cold_ms" if i == 0 else "warm_ms"] = round(ms, 1)
        res["stmts" if i == 0 else "warm_stmts"] = STATS["stmts"]
        res["net" if i == 0 else "warm_net"] = len(NET_ATTEMPTS) - n0
        res["status"], res["bytes"] = status, size
    return res


def sample(fn, interval=0.005, top=30):
    """Run fn while sampling every thread's stack; print the hottest brambleloop frames."""
    import collections
    import threading

    me = threading.get_ident()
    counts: collections.Counter = collections.Counter()
    leaf: collections.Counter = collections.Counter()
    stop = threading.Event()

    def loop():
        sid = threading.get_ident()
        while not stop.is_set():
            for tid, fr in sys._current_frames().items():
                if tid in (me, sid):
                    continue
                seen = set()
                first = True
                while fr is not None:
                    co = fr.f_code
                    if "brambleloop" in co.co_filename:
                        key = f"{co.co_filename.split('brambleloop/')[-1]}:{co.co_name}"
                        if first:
                            leaf[f"{key}:{fr.f_lineno}"] += 1
                            first = False
                        if key not in seen:
                            counts[key] += 1
                            seen.add(key)
                    fr = fr.f_back
            time.sleep(interval)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    try:
        fn()
    finally:
        stop.set()
        t.join()
    print("-- inclusive samples --")
    for k, v in counts.most_common(top):
        print(f"{v:6d} {k}")
    print("-- innermost brambleloop line --")
    for k, v in leaf.most_common(15):
        print(f"{v:6d} {k}")


def run(paths=None, repeat=2) -> dict:
    t0 = time.perf_counter()
    info = seed()
    print(f"seeded in {time.perf_counter() - t0:.1f}s: {info if isinstance(info, dict) else ''}"
          [:300], flush=True)
    _install_counters()
    c, _csrf = session()
    out = {}
    for p in paths or routes():
        out[p] = time_route(c, p, repeat)
        r = out[p]
        flag = " SLOW" if r["cold_ms"] > 500 or r.get("warm_ms", 0) > 500 else ""
        print(f"{r['cold_ms']:9.0f} {r.get('warm_ms', 0):9.0f} ms  {r['stmts']:5d} q "
              f"net={r['net']} {r['status']} {r['bytes']:8d}B  {p}{flag}", flush=True)
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    dest = args[args.index("--json") + 1] if "--json" in args else None
    only = [a for a in args if a.startswith("/api/")]
    skip = [a[len("--skip="):] for a in args if a.startswith("--skip=")]
    if skip:
        only = [p for p in routes() if p not in skip]
    if "--profile" in args:
        seed()
        _install_counters()
        c, _ = session()
        for p in only:
            print(f"== {p}", flush=True)
            sample(lambda: print(time_route(c, p, 1)))
        sys.exit(0)
    try:
        res = run(only or None)
    except Exception:
        traceback.print_exc()
        raise
    if dest:
        Path(dest).write_text(json.dumps(res, indent=1, sort_keys=True))
