"""Wave 3 lane TOOLS: the STRUCTURAL-row override proposal, and the adjudicator rules it relies on.

* `w3/OVERRIDES_PROPOSED.json` covers exactly lane K's 16 STRUCTURAL rows, is unaccepted (F-867),
  and a dry run of it raises no problem and closes every row it proposes to close.
* `--dry-run` writes nothing; a non-dry run refuses any override file but overrides.json.
* A maturity override is a claim and is capped like one (it cannot lift a row past its evidence).
* F-847: wave work that names no registry row is unclassified scope and is a problem.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "research" / "final_build"
PROPOSED = FB / "w3" / "OVERRIDES_PROPOSED.json"


def _aggregate():
    spec = importlib.util.spec_from_file_location("fb_aggregate_w3o", FB / "aggregate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _workdir(agg, overrides: dict | None = None, waves: dict | None = None) -> Path:
    """A private copy of the adjudicator's inputs, so a run never touches the committed files."""
    work = Path(tempfile.mkdtemp(prefix="w3o_"))
    for name in ("master_registry.json", "module_reachability.json"):
        shutil.copy(FB / name, work / name)
    shutil.copytree(FB / "mapping", work / "mapping",
                    ignore=shutil.ignore_patterns("*.md", "__pycache__"))
    if overrides is not None:
        (work / "overrides.json").write_text(json.dumps(overrides))
    if waves is not None:
        (work / "waves").mkdir()
        for name, data in waves.items():
            (work / "waves" / name).write_text(json.dumps(data))
    agg.HERE = work
    agg.SNAPSHOT = work / "snap.json"
    return work


def _run(agg, argv=None):
    with contextlib.redirect_stdout(io.StringIO()):
        return agg.main(argv or [])


def test_the_proposal_covers_exactly_lane_ks_structural_rows_and_is_unaccepted():
    closure = json.loads((FB / "w3" / "CLOSURE_f0c2d12.json").read_text())
    structural = {r["uid"] for r in closure["launch_critical"] if r.get("cluster") == "STRUCTURAL"}
    prop = json.loads(PROPOSED.read_text())
    assert set(prop["overrides"]) == structural and len(structural) == 16
    for uid, e in prop["overrides"].items():
        assert e["completion_target"] == "TESTED", uid
        assert len(e["reason"].strip()) >= 80, uid       # a reason, not a label
        assert e["accepted_by"] is None, uid              # F-867: never self-accepted


def test_a_dry_run_of_the_proposal_raises_no_problem_closes_every_row_and_writes_nothing():
    agg = _aggregate()
    work = _workdir(agg)
    rep = _run(agg, ["--overrides", str(PROPOSED), "--dry-run"])
    assert rep["dry_run"] is True and rep["problems"] == []
    assert set(rep["rows"]) == set(json.loads(PROPOSED.read_text())["overrides"])
    for uid, r in rep["rows"].items():
        assert r["completion"] == "COMPLETE", (uid, r["reasons"])
        assert r["maturity"] == "TESTED" and r["completion_target"] == "TESTED", uid
    assert not (work / "closure_matrix.json").exists()
    assert not (work / "snap.json").exists() and not (work / "LAUNCH_SCOPE.json").exists()
    shutil.rmtree(work)


def test_the_unaccepted_proposal_applied_for_real_changes_nothing():
    """Copied verbatim into overrides.json (accepted_by null), every entry is refused."""
    agg = _aggregate()
    work = _workdir(agg, overrides=json.loads(PROPOSED.read_text())["overrides"])
    _run(agg)
    m = json.loads((work / "closure_matrix.json").read_text())
    by = {r["uid"]: r for r in m["matrix"]}
    assert m["summary"]["structural_target_overrides"] == []
    assert sum("override without reason/accepted_by" in p for p in m["summary"]["problems"]) == 16
    assert by["F-170"]["completion"] == "OPEN"
    shutil.rmtree(work)


def test_only_overrides_json_can_be_applied_without_dry_run():
    agg = _aggregate()
    work = _workdir(agg)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            _run(agg, ["--overrides", str(PROPOSED)])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("a non-dry run applied a proposal file")
    assert not (work / "closure_matrix.json").exists()
    shutil.rmtree(work)


def test_a_maturity_override_is_a_claim_capped_by_the_evidence():
    """Setting maturity after cap() would certify past the evidence; it is capped like any claim."""
    agg = _aggregate()
    work = _workdir(agg, overrides={"F-170": {
        "maturity": "DEPLOYED", "reason": "test", "accepted_by": "integrator"}})
    _run(agg)
    row = {r["uid"]: r for r in json.loads((work / "closure_matrix.json").read_text())["matrix"]}["F-170"]
    assert row["maturity_claimed"] == "DEPLOYED"
    assert row["maturity"] == "TESTED"                   # run_tests.sh is never reached
    assert any("override maturity" in n and "adjudicated by cap()" in n for n in row["adjudication"])
    shutil.rmtree(work)


def test_a_wave_item_outside_the_registry_is_unclassified_scope():
    """F-847: work reported by a wave that names no registry row is drift, not silently dropped."""
    agg = _aggregate()
    work = _workdir(agg, waves={
        "INTEGRATED.json": {"X1": {"merge": "deadbeef"}},
        "fb1_X1.json": {"requirements": [{"uid": "F-170", "status": "DONE"},
                                         {"uid": "F-NEW-IDEA", "status": "DONE"}]}})
    _run(agg)
    m = json.loads((work / "closure_matrix.json").read_text())
    probs = m["summary"]["problems"]
    assert any("'F-NEW-IDEA' is not a registry row" in p and "F-847" in p for p in probs), probs
    assert not any("F-170" in p for p in probs)
    by = {r["uid"]: r for r in m["matrix"]}
    assert by["F-170"]["wave"][0]["cluster"] == "X1"
    shutil.rmtree(work)


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
