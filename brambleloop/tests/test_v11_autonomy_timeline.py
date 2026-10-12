"""v1.1 lane A: company memory, company timeline, the status provider and the autonomy map.

F-920 (persistent, queryable, source-linked memory), F-927 (company timeline), the lane C
provider contract (`brambleloop.autonomy.status.summary` / `timeline`), and directive §3 (a
machine-readable autonomy map generated from the code that is actually wired).
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import map as amap  # noqa: E402
from brambleloop.autonomy import memory, orchestrator, status  # noqa: E402
from brambleloop.autonomy.models import CompanyMemory, TimelineEvent  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, Incident, OwnerAction  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

CONTRACT = {"status", "as_of", "basis", "items", "sources"}
MAP_JSON = ROOT / "src" / "brambleloop" / "autonomy" / "autonomy_map.json"


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="v11a-tl-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def run(db):
    orchestrator.tick(db)
    w = Worker(db, "w")
    for _ in range(100):
        if not w.run_once():
            break
    orchestrator.tick(db)


def test_providers_never_raise_on_an_empty_database_and_say_unknown():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/empty.sqlite")
    db.create_all()
    s = status.summary(db)
    t = status.timeline(db)
    for out in (s, t):
        assert CONTRACT <= set(out), out
        assert out["status"] == "UNKNOWN" and out["basis"] == "unknown", out
        assert out["reason"]
    # Not even a schema: still UNKNOWN, still no exception.
    bare = Database(f"sqlite:///{tempfile.mkdtemp()}/bare.sqlite")
    assert status.summary(bare)["status"] == "UNKNOWN"
    assert status.timeline(bare)["status"] in ("UNKNOWN",)


def test_summary_reports_every_department_with_wake_and_blockers():
    db = boot()
    memory.block_department(db, "growth", reason="owner must approve ad budget",
                            owner_action="OA-ADS")
    run(db)
    with db.session() as session:          # the contract passes a Session
        out = status.summary(session)
    assert CONTRACT <= set(out), out
    assert out["status"] in status.STATUSES and out["basis"] == "measured", out["status"]
    json.dumps(out, default=str)
    depts = out["items"]
    assert depts and len(depts) == 11, len(depts)
    for i in depts:
        assert i["status"] in status.STATUSES, i
        assert i["next_wake"], i
        assert isinstance(i["blockers"], list)
    growth = next(i for i in depts if i["department"] == "growth")
    assert growth["status"] == "BLOCKED"
    assert growth["blockers"][0]["owner_action"] == "OA-ADS"
    assert out["orchestrator"]["last_tick"] and out["orchestrator"]["stale"] is False
    assert out["overnight"]["latest_brief"] is not None
    assert out["timeline"], "summary carries recent timeline events"


def test_timeline_records_and_merges_sources_newest_first():
    db = boot()
    run(db)
    with db.session() as s:
        s.add(Incident(severity="P1", signature="test:sig", summary="a real incident"))
        s.add(OwnerAction(requirement_key="k", action="approve something"))
        s.add(CostEntry(agent="cfo", amount_cad=0.25, provider="p", purpose="probe"))
    out = status.timeline(db, limit=500)
    assert CONTRACT <= set(out) and out["status"] == "OK", out.get("reason")
    sources = {e["source"] for e in out["items"]}
    assert {"company_timeline", "incidents", "owner_actions", "cost_entries"} <= sources, sources
    kinds = {e["kind"] for e in out["items"]}
    assert {"mission.created", "mission.useful", "incident", "spend"} <= kinds, kinds
    ats = [e["at"] for e in out["items"]]
    assert ats and ats == sorted(ats, reverse=True)
    assert all(e["refs"] for e in out["items"] if e["source"] == "company_timeline")
    assert len(status.timeline(db, limit=5)["items"]) == 5


def test_memory_and_timeline_writes_are_idempotent_on_their_key():
    db = boot()
    a = memory.remember(db, "k1", kind="lesson", department="learn", body={"v": 1},
                        sources=["jobs:1"])
    b = memory.remember(db, "k1", kind="lesson", department="learn", body={"v": 2})
    assert a["created"] and not b["created"]
    assert memory.get(db, "k1")["body"] == {"v": 2}
    assert memory.record_event(db, "e1", kind="x", summary="s") is True
    assert memory.record_event(db, "e1", kind="x", summary="s") is False
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(CompanyMemory)) == 1
        assert s.scalar(select(func.count()).select_from(TimelineEvent)) == 1


def test_the_autonomy_map_is_generated_from_live_wiring():
    data = amap.build()
    json.dumps(data, default=str)
    deps = data["departments"]
    assert len(deps) == 11
    for d in deps:
        for field in ("mission", "authority", "wake_mechanisms", "cadence", "evidence_inputs",
                      "work_generation", "mission_creation", "execution", "durable_output",
                      "downstream_consumers", "follow_on", "learning_signal",
                      "improvement_path", "next_wake", "blockers"):
            assert field in d, (d["department"], field)
        assert d["wake_mechanisms"]["orchestrator"], d["department"]
        assert d["authority"]["generatable"], d["department"]
        assert d["never_woken_job_types"] == [], (d["department"], d["never_woken_job_types"])
    kinds = {b["kind"] for b in data["broken_links"]}
    assert "permission_without_handler" in kinds        # AM-10, reported not hidden
    assert not kinds & {"cadence_without_handler", "cadence_not_permitted",
                        "generatable_without_handler"}, data["broken_links"]
    ids = {f["id"] for f in data["audit_findings"]}
    assert {"AM-01", "AM-07", "AM-10"} <= ids
    assert data["counts"]["follow_on_edges"] > 10


def test_the_committed_map_matches_the_generator():
    assert MAP_JSON.exists(), "autonomy_map.json was not generated"
    committed = json.loads(MAP_JSON.read_text())
    live = amap.build()
    assert committed["generated_by"] == "brambleloop.autonomy.map"
    assert [d["department"] for d in committed["departments"]] == \
        [d["department"] for d in live["departments"]]
    assert committed["counts"] == live["counts"], (committed["counts"], live["counts"])


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
