"""F-667: a department workspace renders every section together from the running tables."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1dw_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/w.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.autonomy import charters, department_workspace as W, departments  # noqa: E402
from brambleloop.core.models import CostEntry, Incident, Job, JobStatus  # noqa: E402

main.db.create_all()
Registry(main.db).seed_defaults()
SECTIONS = ("coverage", "agents", "spend", "improvement", "incidents", "blockers")


def test_one_department_renders_every_section_with_its_rows():
    dept = next(d for d in departments.COMPANY if d["charter"] and d["cells"])
    agent = sorted(charters.BY_KEY[dept["charter"]].agents)[0]
    with main.db.session() as s:
        s.add(Job(agent=agent, job_type="x.y", status=JobStatus.PENDING, inputs={}))
        s.add(Job(agent=agent, job_type="x.y", status=JobStatus.DEAD, inputs={}))
        s.add(CostEntry(agent=agent, kind="model", amount_cad=0.75, purpose="p"))
        s.add(Incident(severity="P2", signature=f"{agent}.failure", summary="s"))
    w = W.workspace(main.db, dept["key"])
    for sec in SECTIONS:
        assert sec in w, sec
        assert not (isinstance(w[sec], dict) and w[sec].get("state") == "UNKNOWN"), (sec, w[sec])
    assert w["agents"][agent]["queued"] == 1
    assert w["spend"]["cad_30d"] == 0.75
    assert set(w["improvement"]) == set(dept["cells"])
    assert w["incidents"] and any("dead-lettered" in b for b in w["blockers"])


def test_route_is_operator_only_and_unknown_department_is_404():
    from brambleloop.core import opsauth

    c = TestClient(main.app)
    key = departments.COMPANY[0]["key"]
    token = "w" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        assert c.get(f"/api/company/departments/{key}").status_code == 401
        h = {"Authorization": f"Bearer {token}"}
        assert c.get(f"/api/company/departments/{key}", headers=h).status_code == 200
        assert c.get("/api/company/departments/nope", headers=h).status_code == 404
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
