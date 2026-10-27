"""W4-FMBATCH1: F-398 Improvement Audit Trail -- one joined record per adopted improvement.

F-398: "Every adopted autonomous improvement records trigger/evidence, old version, new
version, tests, quality-floor verdicts, spend, deployment, observed outcome and rollback
reference." CLOSE5: those were not one record. `cells.audit_record` joins them and names what
is missing; `cells.audit_gaps` lists adopted improvements whose record is incomplete.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import test_w4_improvemetrics as IM  # noqa: E402  (reuses its promotion fixture)
from brambleloop.core.models import Improvement  # noqa: E402
from brambleloop.improve import cells  # noqa: E402

SHA = "0417f3516f30bb7c52926187fc475a0f46536e86"


def _record(db, iid):
    with db.session() as s:
        return cells.audit_record(s.get(Improvement, iid))


def test_an_adopted_improvement_without_tests_or_an_observation_names_the_gaps():
    db = IM._db()
    iid = IM._promoted(db, attribute=True, sha=SHA)
    rec = _record(db, iid)
    assert rec["complete"] is False
    assert set(rec["missing"]) == {"tests", "observed_outcome"}, rec["missing"]
    for field in ("trigger_evidence", "old_version", "new_version", "quality_floor_verdicts",
                  "spend", "deployment", "rollback_ref"):
        assert rec[field] is not None, field
    assert rec["deployment"]["build_sha"] == SHA and rec["spend"]["spend_cad"] == 0.42
    gaps = cells.audit_gaps(db)
    assert gaps["adopted"] == 1 and gaps["incomplete"][0]["id"] == iid


def test_tests_and_an_observed_outcome_complete_the_record_and_history_carries_it():
    db = IM._db()
    iid = IM._promoted(db, attribute=True, sha=SHA)
    cells.record_test(db, iid, kind="regression_test", ref="tests/test_x.py", passed=True,
                      recorded_by="evaluator")
    held = cells.monitor(db, iid, 4.0)
    assert held["action"] == "held"
    rec = _record(db, iid)
    assert rec["complete"] is True, rec["missing"]
    assert rec["observed_outcome"]["observed"] == 4.0 and rec["observed_outcome"]["degraded"] is False
    assert cells.audit_gaps(db)["incomplete"] == []
    assert next(h for h in cells.history(db) if h["id"] == iid)["audit"]["complete"] is True


def test_unattributed_spend_and_unknown_build_are_missing_not_defaulted():
    db = IM._db()
    iid = IM._promoted(db, attribute=False, sha=None)
    rec = _record(db, iid)
    assert "spend" in rec["missing"] and rec["spend"] is None


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
