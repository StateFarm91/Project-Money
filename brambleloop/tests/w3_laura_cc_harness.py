"""Shared harness for the W3 lane F "Talk to Laura" tests (not a test file itself).

Isolated SQLite database, no network, shadow phase, no model credentials; a real owner
session through the real `/api/cc/*` routes (session cookie + CSRF + fresh nonce/timestamp).
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import socket
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TMP = tempfile.mkdtemp(prefix="w3_laura_cc_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("BRAMBLELOOP_LAURA_PHRASING", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the Laura harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

OPS = "q" * 40
PASS = "owner passphrase for the laura harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db

from brambleloop.visual import canonical as _canonical  # noqa: E402

CANON_ID = _canonical.IDENTITY_ID
# Lane D now applies the D-FB-14 r2 amendment inside laura genesis `ensure()` (pinned
# CURRENT_SHA256), so this harness no longer re-pins anything: lane D's own verification runs
# unmodified, and a stale pin would fail these suites closed (IdentityTampered).
LANE_D_REPINNED = False


def now() -> datetime:
    return datetime.now(timezone.utc)


def client() -> TestClient:
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)


def session():
    c = client()
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def fresh(csrf: str) -> dict:
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def post(c, csrf, path, body):
    return c.post(path, json=body, headers=fresh(csrf))


def expire_stepup(c) -> None:
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def seed_company() -> dict:
    """Durable evidence for grounded answers: jobs, a mission, a lesson, products, an
    owner action. Returns the ids so tests can check the answer cites them."""
    from brambleloop.autonomy import memory
    from brambleloop.core.models import (Job, JobStatus, Lesson, OwnerAction, PatternVersion,
                                         Product)

    t = now() - timedelta(hours=2)
    with DB.session() as s:
        j = Job(agent="orchestrator", job_type="seasonal.sentinel", inputs={},
                outputs={"checked": 4}, status=JobStatus.DONE, finished_at=t)
        s.add(j)
        les = Lesson(origin_cell="growth", subject="shawl-keywords",
                     statement="buyers search 'triangle shawl' far more than 'kerchief'",
                     confidence="observed", at=t)
        s.add(les)
        p = Product(slug="harbour-shawl", title="Harbour Shawl", status="certified")
        s.add(p)
        s.flush()
        pv = PatternVersion(product_id=p.id, version="1", cir_json={}, certified=True,
                            release_hash="r" * 64)
        s.add(pv)
        oa = OwnerAction(requirement_key="test:confirm-shop-name",
                         action="confirm the public shop name", reason="Etsy shop setup",
                         minutes=2, consequence_of_delay="shop name stays unconfirmed")
        s.add(oa)
        s.flush()
        ids = {"job": j.id, "lesson": les.id, "product": p.id, "pv": pv.id, "oa": oa.id}
    memory.remember(DB, "autonomy:product_design:test-mission", kind="mission",
                    department="product_design", subject="seasonal.sentinel: launch windows",
                    state="useful", body={"job_id": ids["job"]},
                    sources=[f"jobs:{ids['job']}"])
    return ids


def run(globs: dict) -> None:
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globs.items()) if n.startswith("test_") and callable(f)]
    assert tests, "no tests collected"
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
