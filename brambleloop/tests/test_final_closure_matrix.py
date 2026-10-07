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
    # v1.1 (F-880..F-930) is additive to v1.0 (§96): its rows are registry records too, so the
    # matrix maps v1.0 + v1.1 exactly once each (wave 4, lane FM).
    v11 = json.loads((FB / "master_registry_v1_1.json").read_text())
    uids = [r["uid"] for r in reg["requirements"]] + [r["id"] for r in v11["requirements"]]
    assert len(v11["requirements"]) == 51 and len(set(uids)) == len(uids)
    m = _matrix()
    assert m["summary"]["unmapped"] == [] and m["summary"]["problems"] == []
    assert sorted(r["uid"] for r in m["matrix"]) == sorted(uids)
    assert {r["uid"] for r in m["matrix"] if r["version"] == "v1.1"} == \
        {r["id"] for r in v11["requirements"]}


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



# ---- F-836 / F-837 / F-834: the closure validator's evidence rules ------------------------

_REACHED_PRODUCER = "src/brambleloop/runtime/worker.py::Worker.run_once"
_REAL_TEST = "tests/test_final_closure_matrix.py::test_no_row_claims_commercial_evidence_that_does_not_exist"


def _row(**kw):
    row = {"uid": "F-X", "maturity": "INTEGRATED", "tests": [_REAL_TEST],
           "producer": _REACHED_PRODUCER, "durable_state": "jobs", "evidence": ["note"]}
    row.update(kw)
    return row


def test_a_fact_only_tests_write_cannot_hold_integrated():
    """F-836: a durable_state table with no non-test writer in a reached module caps at TESTED."""
    agg = _aggregate()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    level, notes = agg.cap(_row(), reach)
    assert level == "INTEGRATED" and notes == []
    # creator_profiles is written only by tests (tests/test_creators.py and friends).
    assert agg.writer_index()["writers"]["creator_profiles"] == []
    level, notes = agg.cap(_row(durable_state="creator_profiles (agreed creators)"), reach)
    assert level == "TESTED" and any("F-836" in n and "creator_profiles" in n for n in notes)
    # A writer that exists but is unreached is no better than none.
    jobs_writers = agg.writer_index()["writers"]["jobs"]
    assert jobs_writers
    unreached = {**reach, **{m: {**reach.get(m, {}), "reached": False} for m in jobs_writers}}
    level, _ = agg.cap(_row(), unreached)
    assert level == "TESTED"


def test_all_proxy_evidence_refuses_integrated_but_one_direct_item_does_not():
    """F-837: proxy evidence is flagged on the item, and proxy alone never reaches INTEGRATED."""
    agg = _aggregate()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    level, notes = agg.cap(_row(evidence=[{"ref": "seo_score", "proxy": True},
                                          "[proxy] click-through stands in for conversion"]),
                           reach)
    assert level == "TESTED" and any("F-837" in n for n in notes)
    level, _ = agg.cap(_row(evidence=[{"ref": "seo_score", "proxy": True}, "direct readback"]),
                       reach)
    assert level == "INTEGRATED"


def test_the_committed_matrix_is_exactly_its_adjudication():
    """Every row's maturity is what cap() gives its claim today (no hand edits, no drift)."""
    agg = _aggregate()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    overrides = (json.loads((FB / "overrides.json").read_text())
                 if (FB / "overrides.json").exists() else {})
    rows = _matrix()["matrix"]
    assert len(rows) > 800
    for r in rows:
        if "maturity" in overrides.get(r["uid"], {}):
            continue
        level, _ = agg.cap({**r, "maturity": r["maturity_claimed"]}, reach)
        assert level == r["maturity"], (r["uid"], level, r["maturity"])


def test_every_row_states_protected_action_applicability():
    """final_proof.py refuses a row whose protected-action applicability is unknown (F-834)."""
    rows = _matrix()["matrix"]
    assert len(rows) > 800
    for r in rows:
        assert r["protected_action_applicability"] in ("protected", "unprotected"), r["uid"]
        if r.get("protected_effect"):
            assert r["protected_action_applicability"] == "protected", r["uid"]


# ---- F-177 / F-178 / F-843: completion verdict and basis -----------------------------------


def test_completion_is_computed_per_row_and_the_open_count_is_summarised():
    """Computed, not asserted: release needs launch_critical_open == 0, which is not pinned yet."""
    agg = _aggregate()
    m = _matrix()
    for r in m["matrix"]:
        verdict, reasons = agg.completion(r)
        assert (r["completion"], r["completion_reasons"]) == (verdict, reasons), r["uid"]
        if r["launch_class"] == "LAUNCH-CRITICAL":
            assert verdict in ("COMPLETE", "GATED", "OPEN"), r["uid"]
            if verdict == "COMPLETE":
                assert agg.LEVELS.index(r["maturity"]) >= agg.LEVELS.index("INTEGRATED")
                assert r["coverage"] == "FULL" and not r.get("defect")
            if verdict == "GATED":
                assert r["gate"]["kind"] in ("owner", "data", "external") and r["gate"]["key"]
        else:
            assert verdict in ("POST-LAUNCH", "NOT-APPLICABLE"), r["uid"]
    lc = [r for r in m["matrix"] if r["launch_class"] == "LAUNCH-CRITICAL"]
    assert m["summary"]["launch_critical_open"] == sum(r["completion"] == "OPEN" for r in lc)
    assert sum(m["summary"]["launch_critical_completion"].values()) == len(lc)
    # A row below target is never COMPLETE, and an open defect is never merely GATED.
    assert agg.completion({"launch_class": "LAUNCH-CRITICAL", "maturity": "TESTED",
                           "coverage": "FULL", "gate": {"kind": "none"}})[0] == "OPEN"
    assert agg.completion({"launch_class": "LAUNCH-CRITICAL", "maturity": "INTEGRATED",
                           "coverage": "PARTIAL", "defect": "wrong",
                           "gate": {"kind": "owner", "key": "k"}})[0] == "OPEN"


def test_basis_names_the_actual_mapping_commits():
    import subprocess

    m = _matrix()
    mapping = m["basis"]["mapping"]
    shas = {mapping["base"]} | {v["sha"] for v in mapping["remaps"].values()}
    for sha in shas:
        assert len(sha) == 40
        assert subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", sha + "^{commit}"],
                              capture_output=True).returncode == 0, sha
    assert {r["mapped_on"] for r in m["matrix"]} <= shas
    assert mapping["rows_on_base"] + sum(v["rows"] for v in mapping["remaps"].values()) == \
        len(m["matrix"])
    assert "019ebf0 (+" not in json.dumps(m["basis"])


# ---- F-847: the launch-scope ledger ----------------------------------------------------------


def test_launch_scope_classifies_every_row_and_every_reclassification_has_a_reason():
    agg = _aggregate()
    scope = json.loads((FB / "LAUNCH_SCOPE.json").read_text())
    m = _matrix()
    by_uid = {e["uid"]: e for e in scope["entries"]}
    assert len(by_uid) == len(scope["entries"]) == len(m["matrix"])
    for r in m["matrix"]:
        e = by_uid[r["uid"]]
        assert e["scope"] == agg.SCOPE_OF[r["launch_class"]], r["uid"]
        assert e["scope"] in ("launch-critical", "post-launch", "rejected")
        assert e["reason"].strip(), r["uid"]          # every classification says why
        if e["reclassified"]:
            assert e["scope"] != "launch-critical" and e["reclassified_against"]
            assert len(e["reason"].strip()) >= 20, (r["uid"], e["reason"])
    # Every source-P0 row outside launch scope is recorded as a reclassification.
    for r in m["matrix"]:
        if r["launch_class"] != "LAUNCH-CRITICAL" and "P0" in str(r.get("master_priority")):
            assert r["uid"] in scope["reclassified_out_of_launch"], r["uid"]
    assert scope["counts"] == {k: v for k, v in {
        "launch-critical": sum(r["launch_class"] == "LAUNCH-CRITICAL" for r in m["matrix"]),
        "post-launch": sum(r["launch_class"] == "MATURE" for r in m["matrix"]),
        "rejected": sum(r["launch_class"] == "NA" for r in m["matrix"])}.items() if v}


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
