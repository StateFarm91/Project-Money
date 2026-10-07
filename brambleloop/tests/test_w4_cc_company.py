"""W4-CC: the Command Center company overview and completion-effort board.

GET /api/cc/company and GET /api/cc/completion are owner-session gated (default-deny), every
section carries status/as_of/basis, an absent department provider makes departments UNKNOWN
(never "sleeping" and never 0), the Build 2 closure is computed off the request path, and the
committed COMPLETION_BOARD.json validates against the schema the reader enforces.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_cc_company.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import re
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_cc_company_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_COMPLETION_BOARD", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-CC harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth, company, providers  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import Job, JobStatus  # noqa: E402

OPS = "w" * 40
PASS = "owner passphrase for the W4-CC harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
BOARD = ROOT / "research" / "final_build" / "w4" / "COMPLETION_BOARD.json"

SECTIONS = ("company_status", "departments", "agents", "owner_actions", "approvals", "store",
            "store_visibility", "product_pipeline", "finance", "autonomy", "learn",
            "build2_closure", "final_master_closure", "visual", "laura", "blockers",
            "completion_effort")


def _fake_build2(_db):
    return {"closure": {"total": 3, "counts": {"COMPLETE+PROVEN": 1, "OWNER-GATED": 1,
                                               "DATA-GATED": 0, "EXTERNAL-BLOCKED": 0,
                                               "OPEN": 1},
                        "closed_out": False, "closeout_indeterminate": False,
                        "gates_checked_live": True, "by_section": {}, "external_blockers": [],
                        "open": [{"id": 7, "title": "t", "why": "w"}], "matrix_as_of": "x"},
            "maturity": {"covered_by_the_registry": 1, "rungs": {}, "highest_rung_reached": {},
                         "no_rung_reached": 0, "registered_but_never_run": 0,
                         "is_production": False}}


company.COMPUTE_BUILD2 = _fake_build2


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c


class AbsentProvider:
    def __init__(self, *keys):
        self.mods = sorted({providers.PROVIDERS[k][0] for k in keys})

    def __enter__(self):
        self.prev = {m: sys.modules.get(m, _MISSING) for m in self.mods}
        for m in self.mods:
            sys.modules[m] = None  # type: ignore[assignment]

    def __exit__(self, *exc):
        for m, prev in self.prev.items():
            if prev is _MISSING:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = prev


_MISSING = object()


def test_routes_default_deny_without_owner_session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    paths = ["/api/cc/company", "/api/cc/completion"]
    assert paths
    for p in paths:
        r = c.get(p)
        assert r.status_code == 401, (p, r.status_code, r.text[:200])
        # The operator bearer token is not an owner session either.
        r = c.get(p, headers={"Authorization": f"Bearer {OPS}"})
        assert r.status_code == 401, (p, "bearer", r.status_code)
        assert "sections" not in r.text


def test_company_every_section_is_an_honest_envelope():
    company._BUILD2.reset()
    c = session()
    r = c.get("/api/cc/company")
    assert r.status_code == 200, r.text[:500]
    assert r.headers.get("cache-control") == "no-store"
    data = r.json()
    assert data["tab"] == "COMPANY" and data["generated_at"]
    s = data["sections"]
    missing = [k for k in SECTIONS if k not in s]
    assert not missing, missing
    for k in SECTIONS:
        env = s[k]
        assert env.get("status") in providers.STATUSES, (k, env.get("status"))
        assert "as_of" in env and "basis" in env, k
        if env["status"] == "UNKNOWN":
            assert env.get("reason"), (k, "UNKNOWN without a reason")
    assert data["status"] in providers.STATUSES and data["reason"]
    st = s["company_status"]["items"][0]
    assert st["phase"] == "shadow", st
    assert s["laura"]["talk_href"] == "#/laura"
    assert s["completion_effort"]["href"] == "#/completion"


def test_departments_unknown_when_autonomy_provider_absent():
    with AbsentProvider("autonomy"):
        c = session()
        s = c.get("/api/cc/company").json()["sections"]
    d = s["departments"]
    assert d["items"], "charter departments listed even without the provider"
    assert d["status"] == "UNKNOWN" and d["reason"], d.get("reason")
    for it in d["items"]:
        assert it["state"] == "UNKNOWN", it
        assert it["why"], it
        assert it["state"] != "sleeping"
    assert d["counts"]["UNKNOWN"] == len(d["items"])
    assert d["counts"]["sleeping"] == 0
    # Company status may not read OK on top of an UNKNOWN department view.
    assert s["company_status"]["status"] != "OK"


def test_department_state_mapping():
    cases = [("OK", 0, "sleeping"), ("OK", 2, "active"), ("BLOCKED", 1, "blocked"),
             ("DEGRADED", 0, "unhealthy"), ("UNKNOWN", 3, "UNKNOWN"), (None, 0, "UNKNOWN"),
             ("weird", 0, "UNKNOWN")]
    assert cases
    for st, running, want in cases:
        assert company.department_state(st, running) == want, (st, running)


def test_agent_with_running_job_is_active_with_current_job():
    now = datetime.now(timezone.utc)
    with DB.session() as s:
        j = Job(agent="orchestrator", job_type="ops.heartbeat", inputs={},
                status=JobStatus.RUNNING, started_at=now, run_after=now)
        s.add(j)
        s.flush()
        jid = j.id
        s.add(Job(agent="orchestrator", job_type="ops.heartbeat", inputs={},
                  outputs={"summary": "heartbeat ok", "did_work": True},
                  status=JobStatus.DONE, started_at=now - timedelta(minutes=5),
                  finished_at=now - timedelta(minutes=4), run_after=now))
        s.commit()
    try:
        env = company.agents(DB)
        assert env["items"], env
        orch = next(i for i in env["items"] if i["name"] == "orchestrator")
        assert orch["state"] == "active", orch
        assert orch["current_job"]["job_id"] == jid
        assert orch["current_job"]["source"] == f"jobs:{jid}"
        assert orch["next_wake"], "orchestrator has worker cadences"
        for i in env["items"]:
            assert i["state"] in company.STATES, i
            if i["name"] != "orchestrator":
                assert i["current_job"] is None
    finally:
        with DB.session() as s:
            row = s.get(Job, jid)
            row.status = JobStatus.DONE
            row.finished_at = datetime.now(timezone.utc)
            s.commit()


def test_build2_closure_is_computed_off_the_request_path():
    company._BUILD2.reset()
    gate = {"go": False}

    def slow(_db):
        while not gate["go"]:
            time.sleep(0.01)
        return _fake_build2(_db)

    company.COMPUTE_BUILD2 = slow
    try:
        t0 = time.monotonic()
        first = company.build2_snapshot(DB)
        assert time.monotonic() - t0 < 2, "the request must not wait for the matrix"
        assert first["status"] == "UNKNOWN" and "computing" in first["reason"], first
        gate["go"] = True
        done = company.build2_snapshot(DB, wait=5)
        assert done["status"] == "DEGRADED", done
        assert done["closure"]["counts"]["OPEN"] == 1 and done["as_of"]
        assert "1 requirement(s) OPEN" in done["reason"]
    finally:
        company.COMPUTE_BUILD2 = _fake_build2
        company._BUILD2.reset()


def test_build2_failure_is_unknown_with_reason():
    company._BUILD2.reset()

    def boom(_db):
        raise RuntimeError("graph source changed during analysis")

    company.COMPUTE_BUILD2 = boom
    try:
        company.build2_snapshot(DB, wait=5)
        out = company.build2_snapshot(DB, wait=5)
        assert out["status"] == "UNKNOWN", out
        assert "graph source changed" in out["reason"], out["reason"]
        assert out["items"] == []
    finally:
        company.COMPUTE_BUILD2 = _fake_build2
        company._BUILD2.reset()


def test_final_master_section_reads_packaged_snapshot():
    fm = company.final_master(DB)
    assert fm["status"] in providers.STATUSES
    assert fm["read_at"] and fm["as_of_basis"]
    assert isinstance(fm.get("launch_critical_total"), int) and fm["launch_critical_total"] > 0


def test_committed_board_validates():
    board = json.loads(BOARD.read_text())
    assert board["lanes"], "board has lanes"
    assert company.validate_board(board) == [], company.validate_board(board)
    out = company.completion(DB)
    assert out["status"] in providers.STATUSES and not out["schema_errors"], out
    assert out["as_of"] == out["board_updated_at"]
    lanes = {i["lane"] for i in out["items"]}
    assert "W4-CC" in lanes, lanes
    # rows_closed null on every seeded lane: the total is UNKNOWN (None), never 0.
    if all(i["rows_closed_count"] is None for i in out["items"]):
        assert out["rows_closed_total"] is None


def _write_board(obj) -> str:
    p = os.path.join(_TMP, f"board_{time.monotonic_ns()}.json")
    Path(p).write_text(json.dumps(obj) if not isinstance(obj, str) else obj)
    return p


def test_board_absent_malformed_and_stale():
    prev = os.environ.get(company.BOARD_ENV)
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    try:
        os.environ[company.BOARD_ENV] = os.path.join(_TMP, "nope.json")
        out = company.completion(DB, now=now)
        assert out["status"] == "UNKNOWN" and "not found" in out["reason"]
        os.environ[company.BOARD_ENV] = _write_board("{not json")
        assert company.completion(DB, now=now)["status"] == "UNKNOWN"
        bad = {"kind": "brambleloop.completion_board", "schema_version": 1,
               "updated_at": "2026-10-07T00:00:00+00:00",
               "lanes": [{"lane": "X", "status": "SHIPPED-ISH"}]}
        os.environ[company.BOARD_ENV] = _write_board(bad)
        out = company.completion(DB, now=now)
        assert out["status"] == "DEGRADED" and out["schema_errors"], out
        assert out["basis"] == "unknown"
        lane = {k: None for k in company.BOARD_REQUIRED}
        good = {"kind": "brambleloop.completion_board", "schema_version": 1,
                "updated_at": "2026-10-07T11:00:00+00:00",
                "lanes": [{**lane, "lane": "A", "worker": "w", "task": "t", "status": "RUNNING",
                           "last_update_at": "2026-10-07T06:00:00+00:00",
                           "rows_closed": {"count": 4, "ids": ["F-1"]}},
                          {**lane, "lane": "B", "worker": "w", "task": "t", "status": "DONE",
                           "last_update_at": "2026-10-07T06:00:00+00:00",
                           "rows_closed": {"count": 0, "ids": []}},
                          {**lane, "lane": "C", "worker": "w", "task": "t",
                           "status": "BLOCKED", "blocker": "owner gate etsy_api"}]}
        os.environ[company.BOARD_ENV] = _write_board(good)
        out = company.completion(DB, now=now)
        assert not out["schema_errors"], out["schema_errors"]
        assert out["stale"] == ["A"], out["stale"]
        assert out["status"] == "BLOCKED" and out["counts"]["BLOCKED"] == 1
        assert out["rows_closed_total"] == 4 and out["rows_closed_lanes_unknown"] == 1
        assert out["board_age_minutes"] == 60.0
    finally:
        if prev is None:
            os.environ.pop(company.BOARD_ENV, None)
        else:
            os.environ[company.BOARD_ENV] = prev


def test_completion_route_returns_board():
    c = session()
    r = c.get("/api/cc/completion")
    assert r.status_code == 200, r.text[:300]
    board = r.json()["sections"]["board"]
    assert board["items"] and board["provider"] == "company.completion"


def test_pwa_has_company_and_completion_views():
    routes = (STATIC / "js" / "routes.js").read_text()
    ids = re.findall(r'id: "([a-z]+)"', routes)
    assert ids
    sw = (STATIC / "sw.js").read_text()
    api_js = (STATIC / "js" / "api.js").read_text()
    for view in ("company", "completion"):
        assert view in ids, ids
        f = STATIC / "js" / "views" / f"{view}.js"
        assert f.is_file() and "export async function render" in f.read_text(), view
        assert f'"js/views/{view}.js"' in sw, f"{view} missing from the service-worker shell"
        assert f"/{view}`" in api_js, f"{view} endpoint missing from api.js"
    home = (STATIC / "js" / "views" / "home.js").read_text()
    assert "#/company" in home and "#/completion" in home


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
