"""The Final Master closure is a live, recomputed gate (wave 3, lane TOOLS, cluster K13).

F-129 live re-audit, F-130 parked split by kind, F-133 no orphaned partial, F-136 machine-derived
completion, F-382/F-844 the eight-rung ladder, F-400/F-879 launch driven by the launch-critical
set with post-launch rows excluded, F-831/F-832 producer->consumer chain, F-838 only an explicit
gate removes work from OPEN, F-860 a visual-blocked lane does not stall unrelated work, F-867
an override needs a reason and an accepting integrator.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FB = ROOT / "research" / "final_build"

from brambleloop.build2 import final_master as FM  # noqa: E402


def _aggregate():
    spec = importlib.util.spec_from_file_location("fb_aggregate_w3", FB / "aggregate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snap():
    return json.loads(FM.SNAPSHOT.read_text())


def _lc_row(**over):
    row = {"uid": "F-999", "launch_class": "LAUNCH-CRITICAL", "completion": "COMPLETE",
           "title": "t", "maturity": "INTEGRATED", "maturity_claimed": "INTEGRATED",
           "coverage": "FULL", "defect": False, "gate": {"kind": "none", "key": None},
           "has_missing_part": True, "next_action": "", "has_producer": True,
           "has_consumer": True, "structural": False, "completion_target": None,
           "overridden": [], "mapped_on": "x"}
    row.update(over)
    return row


def _write(snap) -> Path:
    p = Path(tempfile.mkdtemp()) / "snap.json"
    p.write_text(json.dumps(snap))
    return p


def test_the_shipped_snapshot_is_exactly_the_projection_of_the_committed_matrix():
    agg = _aggregate()
    matrix = json.loads((FB / "closure_matrix.json").read_text())
    assert len(matrix["matrix"]) > 800
    want = agg.runtime_snapshot(matrix)
    assert _snap() == json.loads(json.dumps(want)), "regenerate with aggregate.py"
    # It ships in the image and is bound by the release tree digest (F-397).
    from brambleloop.ops import release_record
    rel = FM.SNAPSHOT.relative_to(ROOT).as_posix()
    assert release_record.deployable(rel), rel


def test_the_runtime_recomputes_every_verdict_and_agrees_with_the_adjudicator():
    s = FM.summary()
    snap = _snap()
    lc = [r for r in snap["rows"] if r["launch_class"] == "LAUNCH-CRITICAL"]
    assert len(lc) > 400
    assert s["integrity_violations"] == [], s["integrity_violations"][:5]
    assert s["launch_critical"] == snap["summary"]["launch_critical_completion"] | {
        k: 0 for k in ("COMPLETE", "GATED", "OPEN")
        if k not in snap["summary"]["launch_critical_completion"]}
    assert s["launch_critical_open"] == snap["summary"]["launch_critical_open"]
    # Honest today: open launch-critical work exists, so the gate is not ready.
    assert s["launch_critical_open"] > 0 and s["launch_ready"] is False
    assert s["status"] in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN")
    for key in ("as_of", "basis", "items", "sources"):
        assert key in s


def test_a_label_the_rules_do_not_support_is_an_integrity_violation_and_blocks():
    snap = _snap()
    lc = [r for r in snap["rows"] if r["launch_class"] == "LAUNCH-CRITICAL"
          and r["completion"] == "OPEN" and r["maturity"] in ("IMPLEMENTED", "TESTED")]
    assert lc
    bad = copy.deepcopy(snap)
    for r in bad["rows"]:
        if r["uid"] == lc[0]["uid"]:
            r["completion"] = "COMPLETE"          # a hand edit claiming completion
    s = FM.summary(path=_write(bad))
    assert s["status"] == "BLOCKED" and s["launch_ready"] is False
    assert any(v["uid"] == lc[0]["uid"] for v in s["integrity_violations"])


def test_only_an_explicit_keyed_gate_takes_work_out_of_open():
    """F-838: a default/none gate or a blank key leaves unfinished work OPEN."""
    base = dict(maturity="TESTED", completion="OPEN")
    assert FM.verdict(_lc_row(**base, gate={"kind": "owner", "key": "etsy_api"}))[0] == "GATED"
    assert FM.verdict(_lc_row(**base, gate={"kind": "owner", "key": ""}))[0] == "OPEN"
    assert FM.verdict(_lc_row(**base, gate={"kind": "none", "key": "x"}))[0] == "OPEN"
    assert FM.verdict(_lc_row(**base, gate={"kind": "build", "key": "x"}))[0] == "OPEN"
    # A defect is never merely gated.
    assert FM.verdict(_lc_row(**base, defect=True,
                              gate={"kind": "owner", "key": "k"}))[0] == "OPEN"


def test_the_ladder_keeps_every_rung_distinct_and_unknown_rungs_are_open():
    """F-382/F-844: INTEGRATED and COMMERCIALLY-EVIDENCED are rungs; nothing else is."""
    assert FM.LEVELS == tuple(_aggregate().LEVELS)
    assert "INTEGRATED" in FM.LEVELS and "COMMERCIALLY-EVIDENCED" in FM.LEVELS
    assert FM.verdict(_lc_row(maturity="TESTED"))[0] == "OPEN"
    assert FM.verdict(_lc_row(maturity="INTEGRATED"))[0] == "COMPLETE"
    assert FM.verdict(_lc_row(maturity="production"))[0] == "OPEN"


def test_complete_needs_a_named_producer_and_consumer():
    """F-831/F-832: a module alone is not a capability."""
    assert FM.verdict(_lc_row(has_consumer=False))[0] == "OPEN"
    assert FM.verdict(_lc_row(has_producer=False))[0] == "OPEN"
    agg = _aggregate()
    row = {"launch_class": "LAUNCH-CRITICAL", "maturity": "INTEGRATED", "coverage": "FULL",
           "producer": "src/brambleloop/x.py", "consumer": "", "gate": {"kind": "none"}}
    assert agg.completion(row)[0] == "OPEN"
    assert agg.completion({**row, "consumer": "app/main.py"})[0] == "COMPLETE"


def test_an_orphaned_partial_is_named_by_both_the_adjudicator_and_the_runtime():
    """F-133."""
    agg = _aggregate()
    row = {"launch_class": "LAUNCH-CRITICAL", "maturity": "TESTED", "coverage": "PARTIAL",
           "missing_part": "", "next_action": "do x", "gate": {"kind": "none"}}
    assert any("orphaned partial" in r for r in agg.completion(row)[1])
    snap = {"rows": [_lc_row(maturity="TESTED", completion="OPEN", coverage="PARTIAL",
                             has_missing_part=False, next_action="do x")]}
    v = FM.integrity(snap)
    assert v and "orphaned partial" in v[0]["violation"]
    assert json.loads((FB / "closure_matrix.json").read_text())["summary"][
        "orphaned_partials"] == []


def test_post_launch_rows_never_block_and_launch_is_ready_only_with_zero_open():
    """F-400/F-879: another possible improvement is not a launch blocker."""
    rows = [_lc_row(uid="F-1"), _lc_row(uid="F-2", maturity="TESTED", completion="GATED",
                                         gate={"kind": "owner", "key": "etsy_api"})]
    rows += [{"uid": f"F-{i}", "launch_class": "MATURE", "completion": "POST-LAUNCH"}
             for i in range(10, 40)]
    s = FM.summary(path=_write({"rows": rows}))
    assert s["launch_ready"] is True and s["status"] == "OK", s
    assert s["post_launch_excluded"] == 30 and s["gated_by_kind"]["owner"] == 1
    rows.append(_lc_row(uid="F-3", maturity="TESTED", completion="OPEN", coverage="PARTIAL",
                        next_action="build it"))
    s = FM.summary(path=_write({"rows": rows}))
    assert s["launch_ready"] is False and s["launch_critical_open"] == 1
    assert [r["uid"] for r in s["items"]] == ["F-3"]


def test_an_absent_snapshot_is_unknown_never_ready():
    s = FM.summary(path=Path(tempfile.mkdtemp()) / "nope.json")
    assert s["status"] == "UNKNOWN" and s["launch_ready"] is False and s["items"] == []


def test_a_lowered_target_is_honoured_only_on_a_structural_row():
    agg = _aggregate()
    tooling = {"launch_class": "LAUNCH-CRITICAL", "maturity": "TESTED", "coverage": "FULL",
               "producer": "brambleloop/run_tests.sh::write_record", "consumer": "",
               "gate": {"kind": "none"}, "completion_target": "TESTED"}
    assert agg.structural_producer(tooling)[0] is True
    assert agg.completion(tooling)[0] == "COMPLETE"
    runtime = {**tooling, "producer": "src/brambleloop/launch/readiness.py::assess"}
    assert agg.structural_producer(runtime)[0] is False
    assert agg.completion(runtime)[0] == "OPEN"
    # `ops/x.py` is repo-root tooling only when the runtime package has no such module.
    assert agg.structural_producer({"producer": "ops/waiter.py (repo root)"})[0] is True
    assert agg.structural_producer({"producer": "ops/health.py"})[0] is False
    # The runtime refuses a lowered target the adjudicator did not mark structural.
    assert FM.verdict(_lc_row(maturity="TESTED", completion_target="TESTED",
                              structural=False))[0] == "OPEN"
    v = FM.integrity({"rows": [_lc_row(maturity="TESTED", completion="OPEN",
                                       completion_target="TESTED", structural=False,
                                       coverage="FULL")]})
    assert any("not structural" in x["violation"] for x in v)


def test_an_override_needs_a_reason_and_an_accepting_integrator():
    """F-867: the override file is not a channel for a worker to certify itself."""
    agg = _aggregate()
    work = Path(tempfile.mkdtemp())
    for name in ("master_registry.json", "module_reachability.json"):
        (work / name).write_text((FB / name).read_text())
    (work / "mapping").mkdir()
    for f in (FB / "mapping").glob("s[0-9].json"):
        (work / "mapping" / f.name).write_text(f.read_text())
    (work / "overrides.json").write_text(json.dumps({
        "F-170": {"completion_target": "TESTED"},                       # no reason
        "F-205": {"completion_target": "TESTED", "reason": "operator tooling",
                  "accepted_by": "integrator"},
        "F-001": {"completion_target": "TESTED", "reason": "x", "accepted_by": "integrator"},
    }))
    agg.HERE = work
    agg.SNAPSHOT = work / "snap.json"
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        agg.main()
    m = json.loads((work / "closure_matrix.json").read_text())
    by = {r["uid"]: r for r in m["matrix"]}
    probs = m["summary"]["problems"]
    assert any(p.startswith("F-170: override without reason") for p in probs), probs
    assert any(p.startswith("F-001: completion_target") for p in probs), probs
    assert by["F-205"].get("completion_target") == "TESTED"
    assert by["F-205"]["completion"] == "COMPLETE", by["F-205"]["completion_reasons"]
    assert by["F-170"].get("completion_target") is None
    assert by["F-001"].get("completion_target") is None
    assert m["summary"]["structural_target_overrides"] == ["F-205"]
    snap = json.loads((work / "snap.json").read_text())
    assert FM.integrity(snap) == []


def test_the_launch_readiness_gate_consumes_the_closure():
    """The live consumer: readiness carries a final_master_closure item that blocks on OPEN."""
    from brambleloop.core.db import Database
    from brambleloop.launch.readiness import assess

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/r.sqlite")
    db.create_all()
    items = {r.key: r for r in assess(db, phase="shadow").requirements}
    item = items["final_master_closure"]
    assert item.ready is False and item.blocked_by is not None
    assert item.evidence["launch_critical_open"] == FM.summary()["launch_critical_open"] > 0


def test_executor_reports_parked_work_split_by_kind_and_the_final_master():
    """F-130 and F-860: visual-blocked work is parked as external; unrelated work stays ready."""
    from brambleloop.build2 import executor as E
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/e.sqlite")
    db.create_all()
    E.sync(db, env={})
    q = E.queue(db)
    kinds = q["parked_by_kind"]
    assert set(kinds) == {"owner_gated", "data_gated", "external_blocked", "unclassified"}
    assert sum(len(v) for v in kinds.values()) == q["parked_total"] > 0
    assert kinds["unclassified"] == []
    visual = set(q["parked_by_capability"].get("model_bearing_render", []))
    assert visual and visual <= set(kinds["external_blocked"])
    assert q["executable_remaining"] == (q["ready_total"] + q["dependency_waiting_total"]
                                         + q["running_total"])
    # F-860: with the visual gate closed, unrelated ready work (an infrastructure task added
    # beside the visual-parked ones) is the next thing and can be claimed.
    from brambleloop.core.models import BuildTask
    with db.session() as s:
        s.add(BuildTask(requirement_id=990001, title="unrelated infrastructure work",
                        section="infra", status="missing", state=E.READY, priority=1.0,
                        depends_on=[]))
    q = E.queue(db)
    assert q["ready_total"] == 1 and q["next"]["requirement_id"] == 990001
    assert set(q["parked_by_capability"].get("model_bearing_render", [])) == visual
    E.claim(db, 990001, worker="w3-tools-test")
    q = E.queue(db)
    assert q["running_total"] == 1 and q["parked_total"] == sum(
        len(v) for v in q["parked_by_kind"].values())
    rep = E.report(db, env={})
    assert rep["final_master"]["launch_ready"] is False
    assert rep["final_master"]["integrity_violations"] == []


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
