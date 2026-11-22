"""F-13: /health proves database reachability at constant cost.

The probe used to count the whole jobs table on every platform health check. It must not
touch the jobs table at all, must still answer 200 with ``db: "ok"`` when the database is
reachable, and 503 with ``db: "unreachable"`` (class of failure only) when it is not.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/app.sqlite"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_RUNNER_START_DELAY"] = "0"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from brambleloop.app import main as app_main, runner  # noqa: E402

_JOBS = re.compile(r"\bjobs\b", re.IGNORECASE)


class _capture:
    """Records every statement the engine executes while active; optionally fails them."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.statements: list[str] = []

    def _listen(self, conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        self.statements.append(statement)
        if self.fail:
            raise OperationalError(statement, params, Exception("connection refused"))

    def __enter__(self) -> "_capture":
        event.listen(app_main.db.engine, "before_cursor_execute", self._listen)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(app_main.db.engine, "before_cursor_execute", self._listen)


def _client() -> TestClient:
    return TestClient(app_main.app, raise_server_exceptions=False)


def test_health_issues_no_statement_against_the_jobs_table():
    with _client() as c:
        with _capture() as cap:
            r = c.get("/health")
    assert r.status_code == 200, r.text
    assert r.json()["db"] == "ok" and r.json()["status"] == "ok", r.json()
    assert cap.statements, "the health probe executed no statement at all"
    touching = [s for s in cap.statements if _JOBS.search(s)]
    assert not touching, f"/health touched the jobs table: {touching}"


def test_health_answers_503_unreachable_when_the_engine_fails():
    with _client() as c:
        with _capture(fail=True):
            r = c.get("/health")
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["db"] == "unreachable" and body["status"] == "degraded", body
    assert "connection refused" not in r.text, "failure detail leaked to the public body"


def test_health_public_body_keeps_its_projection_shape():
    from brambleloop.app.security import PUBLIC_PROJECTIONS

    with _client() as c:
        body = c.get("/health").json()
    assert set(body) == set(PUBLIC_PROJECTIONS["/health"]), sorted(body)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    runner.stop()
    sys.exit(1 if fails else 0)
