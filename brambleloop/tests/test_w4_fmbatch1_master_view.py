"""F-451: the master orchestrator view joins every section, guards each, and is operator-only."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1mv_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/m.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the test")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.autonomy import master_view as MV  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()
SECTIONS = ("requirements", "departments", "dependencies", "owner_gates", "external_blockers",
            "spend", "deployments", "active_work")


def test_every_section_reads_from_its_source():
    JobQueue(main.db).enqueue("orchestrator", "ops.slo", {})
    v = MV.view(main.db, env={})
    for k in SECTIONS:
        assert k in v and not (isinstance(v[k], dict) and v[k].get("state") == "UNKNOWN"), (k, v[k])
    assert v["active_work"]["by_status"].get("PENDING", v["active_work"]["by_status"].get(
        "pending")) == 1
    assert v["departments"]["records_complete"].endswith("/ 12")
    assert isinstance(v["spend"]["spent_cad"], (int, float)) and "headroom" in v["spend"]


def test_one_broken_source_is_unknown_and_the_rest_still_read():
    from brambleloop.finance import spend_report

    real = spend_report.what_it_bought
    spend_report.what_it_bought = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    try:
        v = MV.view(main.db, env={})
    finally:
        spend_report.what_it_bought = real
    assert v["spend"]["state"] == "UNKNOWN" and "RuntimeError" in v["spend"]["why"]
    assert "ready_total" in v["requirements"]


def test_route_is_operator_only():
    c = TestClient(main.app)
    token = "m" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        assert c.get("/api/orchestrator").status_code == 401
        r = c.get("/api/orchestrator", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and set(SECTIONS) <= set(r.json())
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
