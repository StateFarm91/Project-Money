"""Final Build: the committed closure matrix is exactly the adjudicated aggregation (F-843/F-844).

A matrix edited by hand, or a worker claim that skipped the integrator's evidence rules, would
let a requirement read more mature than its evidence. The rules are pinned here.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "research" / "final_build"


def _aggregate():
    spec = importlib.util.spec_from_file_location("fb_aggregate", FB / "aggregate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _matrix():
    return json.loads((FB / "closure_matrix.json").read_text())


def test_every_registry_record_is_mapped_exactly_once_without_problems():
    reg = json.loads((FB / "master_registry.json").read_text())
    m = _matrix()
    assert m["summary"]["unmapped"] == [] and m["summary"]["problems"] == []
    assert sorted(r["uid"] for r in m["matrix"]) == sorted(r["uid"] for r in reg["requirements"])


def test_no_row_claims_commercial_evidence_that_does_not_exist():
    assert all(r["maturity"] != "COMMERCIALLY-EVIDENCED" for r in _matrix()["matrix"])


def test_exercised_rows_cite_a_committed_production_artefact():
    import re
    for r in _matrix()["matrix"]:
        if r["maturity"] in ("EXERCISED", "PRODUCTION-OBSERVED"):
            ev = " ".join(map(str, r["evidence"]))
            assert re.search(r"research/b2_resume/evidence/prod_|prod_api_verify_\d", ev), r["uid"]


def test_integrated_rows_have_a_producer_reached_from_a_live_root():
    agg = _aggregate()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    order = agg.LEVELS
    for r in _matrix()["matrix"]:
        if order.index(r["maturity"]) >= order.index("INTEGRATED"):
            mod = agg._module_of(r["producer"])
            assert mod and reach[mod]["reached"], r["uid"]


def test_a_worker_claim_above_its_evidence_is_lowered_with_a_reason():
    agg = _aggregate()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    row = {"maturity": "EXERCISED", "tests": [], "producer": "src/brambleloop/nonexistent.py::f",
           "evidence": ["BUILD_STATE.md says it ran"]}
    level, notes = agg.cap(row, reach)
    assert level == "IMPLEMENTED" and len(notes) == 2


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
    sys.exit(1 if fails else 0)
