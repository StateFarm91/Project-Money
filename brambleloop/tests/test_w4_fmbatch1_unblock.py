"""F-467: a successful write to a gate-opening route enqueues build.tick at once (one per
minute per route); refused writes and ordinary reads do not."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1ub_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/u.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the test")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.build2 import unblock as U  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import Job  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()
TOKEN = "u" * 40


def _ticks():
    with main.db.session() as s:
        return [j.idempotency_key for j in s.scalars(select(Job).where(
            Job.job_type == "build.tick")) if (j.idempotency_key or "").startswith(
            "build.tick:event:")]


def test_route_classification():
    assert U.opens_gates("POST", "/api/insights/snapshot")
    assert U.opens_gates("POST", "/api/owner/phase/transition")
    assert U.opens_gates("GET", "/api/etsy/oauth/callback")
    assert not U.opens_gates("GET", "/api/insights/snapshot")
    assert not U.opens_gates("POST", "/api/dead-letters/requeue")


def test_a_successful_gate_write_recomputes_now_and_a_refused_one_does_not():
    c = TestClient(main.app)
    body = {"keyword": "zz crochet hat", "search_count": 120, "recorded_by": "owner"}
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        refused = c.post("/api/insights/snapshot", json=body)
        assert refused.status_code in (401, 403) and _ticks() == []
        ok = c.post("/api/insights/snapshot", json=body,
                    headers={"Authorization": f"Bearer {TOKEN}"})
        assert ok.status_code == 200, ok.text
        assert len(_ticks()) == 1 and "api.insights.snapshot" in _ticks()[0]
        again = c.post("/api/insights/snapshot", json={**body, "keyword": "zz other"},
                       headers={"Authorization": f"Bearer {TOKEN}"})
        assert again.status_code == 200 and len(_ticks()) == 1     # one per minute
        assert c.get("/api/status").status_code == 200 and len(_ticks()) == 1
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
