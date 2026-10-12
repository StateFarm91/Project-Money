"""W4-IMPROVEMETRICS: value ranking, audit trail, learning health, withdrawn lessons.

Rows: F-394 (Improvement Value Ranking), F-398 (Improvement Audit Trail), F-399 (Learning
Health Metrics), F-605 (Company Learning Memory: withdrawn claims).
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_improvemetrics.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_impmetrics_")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, Improvement, Lesson  # noqa: E402
from brambleloop.improve import bus, cells, consume, roi  # noqa: E402

_n = [0]
H = ("re-weighting the seo cluster score toward long-tail phrases should raise distinct query "
     "clusters because the measured gap is in long-tail coverage")


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _refused(fn, exc=roi.RoiRefused) -> str:
    try:
        fn()
    except exc as e:
        return str(e)
    raise AssertionError("expected a refusal")


# ---- F-394 -------------------------------------------------------------------------------

def test_launch_blockers_lead_and_reversibility_breaks_ties():
    ranked = roi.prioritise([
        {"key": "big", "expected_impact": 0.9, "cost_cad": 0.0, "tier": "scoring"},
        {"key": "gate_tie", "expected_impact": 0.2, "cost_cad": 0.0, "tier": "gate"},
        {"key": "scoring_tie", "expected_impact": 0.2, "cost_cad": 0.0, "tier": "scoring"},
        {"key": "blocker", "expected_impact": 0.01, "cost_cad": 5.0, "tier": "code",
         "blocks_launch": "launch.readiness:etsy_api"},
    ])["ranked"]
    assert [r["key"] for r in ranked] == ["blocker", "big", "scoring_tie", "gate_tie"], ranked
    assert ranked[0]["blocks_launch"] == "launch.readiness:etsy_api"
    assert ranked[2]["reversibility_rank"] == 0 and ranked[3]["reversibility_rank"] == 4


def test_old_ordering_is_unchanged_without_the_new_fields():
    ranked = roi.prioritise([
        {"key": "paid", "expected_impact": 0.30, "cost_cad": 2.0},
        {"key": "free", "expected_impact": 0.05, "cost_cad": 0.0},
    ])["ranked"]
    assert [r["key"] for r in ranked] == ["free", "paid"]


def test_a_blocker_flag_must_name_its_readiness_item_and_tiers_must_exist():
    assert "names the readiness" in _refused(lambda: roi.prioritise(
        [{"key": "x", "expected_impact": 1, "blocks_launch": True}]))
    assert "unknown risk tier" in _refused(lambda: roi.prioritise(
        [{"key": "x", "expected_impact": 1, "tier": "vibes"}]))


# ---- F-398 -------------------------------------------------------------------------------

def _promoted(db, *, attribute: bool, sha: str | None):
    cells.record_capability(db, "seo_search", 3.0)
    iid = cells.propose(db, cell="seo_search", hypothesis=H, expected_effect="more clusters",
                        rollback_ref="weights:v1", touches=("weights",), proposed_by="listing")
    if attribute:
        with db.session() as s:
            s.add(CostEntry(agent="listing", amount_cad=0.42, kind="llm", purpose="trial",
                            detail={"improvement_id": iid}))
    assert cells.test_result(db, iid, 4.0) == cells.TESTING
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline")
    old = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    if sha:
        os.environ["RAILWAY_GIT_COMMIT_SHA"] = sha
    else:
        os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
    try:
        cells.promote(db, iid, promoted_by="evaluator")
    finally:
        if old is None:
            os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
        else:
            os.environ["RAILWAY_GIT_COMMIT_SHA"] = old
    return iid


def test_promotion_stamps_build_and_attributed_spend():
    db = _db()
    iid = _promoted(db, attribute=True, sha="0417f3516f30bb7c52926187fc475a0f46536e86")
    with db.session() as s:
        row = s.get(Improvement, iid)
        assert row.build_sha == "0417f3516f30bb7c52926187fc475a0f46536e86"
        assert row.spend_cad == 0.42
    h = cells.history(db)[0]
    assert h["build_sha"].startswith("0417f35") and h["spend_cad"] == 0.42
    assert h["promoted_at"] and h["spend_basis"].startswith("recorded")


def test_unknown_build_and_unattributed_spend_stay_unknown():
    from brambleloop.core import build

    db = _db()
    env_known = build.identity()["known"]
    iid = _promoted(db, attribute=False, sha=None)
    h = next(r for r in cells.history(db) if r["id"] == iid)
    assert h["spend_cad"] is None and h["spend_basis"].startswith("UNKNOWN")
    if not env_known:  # no other commit variable set in this environment
        assert h["build_sha"] is None


# ---- F-399 -------------------------------------------------------------------------------

def test_learning_health_rates_are_none_until_a_verdict():
    db = _db()
    rep = cells.retrospective(db)["learning_health"]
    assert rep["decided"] == 0 and rep["adoption_rate"] is None and rep["rejection_rate"] is None


def test_learning_health_measures_adoption_rejection_regressions_and_cost():
    db = _db()
    _promoted(db, attribute=True, sha="abc1234")
    worse = cells.propose(db, cell="pricing", hypothesis=H.replace("seo", "price"),
                          expected_effect="x", rollback_ref="p:v1", touches=("pricing",),
                          proposed_by="pricing")
    cells.record_capability(db, "pricing", 10.0)
    with db.session() as s:
        s.get(Improvement, worse).baseline_value = 10.0
    cells.test_result(db, worse, 5.0)
    rep = cells.retrospective(db)["learning_health"]
    assert rep["decided"] == 2 and rep["adoption_rate"] == 0.5 and rep["rejection_rate"] == 0.5
    assert rep["regressions_caught"] == 0
    assert rep["cost_per_adopted_cad"] == 0.42, rep
    import importlib.util

    if importlib.util.find_spec("brambleloop.improve.failure_memory") is None:
        assert rep["repeated_failures_avoided"] is None
        assert "not built" in rep["repeated_failures_avoided_basis"]
    else:
        assert isinstance(rep["repeated_failures_avoided"], int)


# ---- F-605 -------------------------------------------------------------------------------

def test_a_withdrawn_lesson_is_kept_but_no_longer_matched():
    db = _db()
    with db.session() as s:
        row = Lesson(origin_cell="quality", subject="blanket drape",
                     statement="heavier yarn weights make blankets drape better for buyers",
                     routed_to=["pricing"], evidence_ref="experiments:7")
        s.add(row)
        s.flush()
        lid = row.id
    text = "heavier yarn weights make blankets drape better"
    assert [m["id"] for m in consume.matching(db, "pricing", text)] == [lid]
    try:
        bus.withdraw(db, lid, reason="no", evidence_ref="", withdrawn_by="quality")
    except bus.WithdrawRefused:
        pass
    else:
        raise AssertionError("a withdrawal without a reason and evidence was accepted")
    out = bus.withdraw(db, lid, reason="a larger holdout showed no drape difference",
                       evidence_ref="experiments:19", withdrawn_by="quality")
    assert out["withdrawn"] is True
    assert consume.matching(db, "pricing", text) == []
    with db.session() as s:
        kept = s.get(Lesson, lid)
        assert kept is not None and "experiments:19" in kept.withdrawn_reason
    assert bus.withdraw(db, lid, reason="again for some reason here", evidence_ref="x:1",
                        withdrawn_by="quality")["already"] is True


def test_api_improve_carries_history():
    src = (ROOT / "src" / "brambleloop" / "app" / "main.py").read_text(encoding="utf-8")
    body = src[src.index('@app.get("/api/improve")'):src.index('@app.get("/api/war-room")')]
    assert '"history": cells_history(db, limit=50)' in body


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
