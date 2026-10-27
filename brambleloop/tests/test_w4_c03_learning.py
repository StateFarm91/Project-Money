"""W4-C03: the learning loop's EXPERIMENT step for every department, research into it, and
superseded evidence retention.

Rows (Final Master, quoted):
- F-705 "Every department continuously runs OBSERVE -> detect opportunity/failure ->
  HYPOTHESIS -> EXPERIMENT -> MEASURE -> ADVERSARIAL VALIDATION -> PROMOTE/REJECT -> MONITOR."
- F-412 "Translate promising research into the smallest bounded experiment that can falsify or
  support its applicability before a large build or spend."
- F-126 "Keep invalid/confounded experiments marked superseded with reason."
No model call; spends nothing.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]

from brambleloop.core.db import Database  # noqa: E402

H = ("answering the sizing question on the listing before checkout should cut support cases "
     "per order, because most cases ask it")
_n = [0]


def _db() -> Database:
    _n[0] += 1
    tmp = tempfile.mkdtemp(prefix="c03_learning_")
    db = Database(f"sqlite:///{tmp}/d{_n[0]}.sqlite")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    return db


def _point(db, cell, value, at):
    from brambleloop.core.models import CapabilityPoint
    from brambleloop.improve import cells, measure

    with db.session() as s:
        s.add(CapabilityPoint(cell=cell, metric=cells.BY_KEY[cell].metric, value=value,
                              sample=10, at=at, detail={"from": measure.SOURCE}))


def _row(db, iid):
    from brambleloop.core.models import Improvement

    with db.session() as s:
        r = s.get(Improvement, iid)
        return r.state, dict(r.evidence or {}), r.baseline_value, r.result_value


def _propose(db, cell="customer_experience", days=7, **kw):
    from brambleloop.improve import cells, profiles

    return cells.propose(db, cell=cell, hypothesis=kw.pop("hypothesis", H),
                         expected_effect="fewer support cases per order",
                         rollback_ref="restore the listing FAQ v1 text",
                         touches=("weights",), proposed_by=profiles.CELL_AGENT[cell],
                         scope={"max_days": days}, **kw)


# ---- F-705 ----------------------------------------------------------------------------------

def test_f705_every_department_cell_has_an_experiment_step_and_every_stage():
    from brambleloop.improve import bounded, cells, runner

    cov = bounded.coverage()
    assert [i["cell"] for i in cov["items"]] == [c.key for c in cells.CELLS]
    for item in cov["items"]:
        assert item["stages"]["experiment"] == [bounded.TRIAL], item
        assert set(item["stages"]) == set(bounded.STAGES) and item["complete"], item
    assert cov["complete"] and runner.TRIALS[bounded.TRIAL] is bounded.trial
    # A bounded proposal on any cell resolves to the trial (before: no trial -> waits for ever).
    assert runner.trial_for({"scope": {"max_days": 7}}) == bounded.TRIAL
    assert runner.trial_for({"scope": {}}) is None


def test_f705_a_cx_experiment_runs_the_whole_loop_through_the_sandbox():
    from brambleloop.improve import bounded, cells, runner

    db = _db()
    now = datetime.now(timezone.utc)
    _point(db, "customer_experience", 0.30, now - timedelta(days=12))
    iid = _propose(db)
    state, ev, base, _ = _row(db, iid)
    assert state == cells.PROPOSED and base == 0.30
    out = runner.run(db)
    w = next(x for x in out["waiting"] if x["improvement"] == iid)
    assert w["trial"] == bounded.TRIAL and "not started" in w["why"], w

    started = bounded.start(db, iid, applied_by="customer_experience",
                            applied_ref="listing-faq:v2", undo="restore the FAQ v1 text",
                            now=now - timedelta(days=9))
    assert started["max_days"] == 7
    try:
        bounded.start(db, iid, applied_by="customer_experience", applied_ref="x",
                      undo="restore it again")
        raise AssertionError("a started experiment does not start twice")
    except bounded.ExperimentRefused:
        pass
    # Only one reading inside the window: not yet a measurement.
    _point(db, "customer_experience", 0.22, now - timedelta(days=8))
    out = runner.run(db)
    w = next(x for x in out["waiting"] if x["improvement"] == iid)
    assert "1 production reading" in w["why"], w
    _point(db, "customer_experience", 0.20, now - timedelta(days=4))
    _point(db, "customer_experience", 0.50, now - timedelta(days=1))   # after the window
    out = runner.run(db)
    state, ev, base, result = _row(db, iid)
    assert result == 0.21, (result, out["waiting"])     # mean of the two in-window readings
    assert ev["sandbox"]["trial"] == bounded.TRIAL
    assert ev["tests"]["adversarial_test"]["passed"], ev["tests"]
    assert ev["approved_by"] == "evaluator"
    assert state == cells.PROMOTED, (state, out["held"])


def test_f705_a_baseline_is_taken_before_the_change_never_after():
    from brambleloop.improve import bounded

    db = _db()
    now = datetime.now(timezone.utc)
    iid = _propose(db, cell="finance")                   # no reading at proposal time
    assert _row(db, iid)[2] is None
    try:
        bounded.start(db, iid, applied_by="finance", applied_ref="forecast:v2",
                      undo="restore forecast v1 model", now=now)
        raise AssertionError("no reading before the change means nothing to compare with")
    except bounded.ExperimentRefused as exc:
        assert "no production reading before the change" in str(exc)
    _point(db, "finance", 0.4, now - timedelta(hours=2))
    _point(db, "finance", 0.1, now + timedelta(hours=2))  # after the change: never a baseline
    bounded.start(db, iid, applied_by="finance", applied_ref="forecast:v2",
                  undo="restore forecast v1 model", now=now)
    _, ev, base, _ = _row(db, iid)
    assert base == 0.4 and ev["baseline_anchored"]["ref"].startswith("capability_history:")


# ---- F-126 ----------------------------------------------------------------------------------

def test_f126_a_confounded_experiment_is_retained_superseded_with_reason_and_not_a_failure():
    from brambleloop.core.models import Improvement
    from brambleloop.improve import bounded, cells, director, failure_memory, runner, superseded

    db = _db()
    now = datetime.now(timezone.utc)
    _point(db, "customer_experience", 0.30, now - timedelta(days=20))
    iid = _propose(db)
    other = _propose(db, hypothesis=H + " and a second unrelated change to the same page")
    bounded.start(db, iid, applied_by="customer_experience", applied_ref="faq:v2",
                  undo="restore the FAQ v1 text", now=now - timedelta(days=10))
    with db.session() as s:                              # another change landed in the window
        r = s.get(Improvement, other)
        r.state, r.promoted_at = cells.PROMOTED, now - timedelta(days=6)
    _point(db, "customer_experience", 0.50, now - timedelta(days=8))
    _point(db, "customer_experience", 0.55, now - timedelta(days=5))
    out = runner.run(db)
    assert any(x["improvement"] == iid and x.get("superseded") for x in out["rejected"]), out
    state, ev, base, result = _row(db, iid)
    mark = ev["superseded"]
    assert state == cells.REJECTED and mark["kind"] == "confounded" and base == 0.30
    assert mark["confounders"][0]["improvement"] == other and "attributed" in mark["reason"]
    assert ev["experiment"]["applied_ref"] == "faq:v2"   # retained, not deleted
    # Not a measured failure: the same idea may be proposed again.
    assert failure_memory.check(db, cell="customer_experience", hypothesis=H,
                                touches=("weights",), scope={"max_days": 7}) is None
    # Reported, not counted as a verdict.
    ran = director.experiments(db, days=30)
    assert iid not in [e["improvement"] for e in ran["completed"]]
    assert [e["improvement"] for e in ran["superseded"]] == [iid]
    assert cells.retrospective(db, days=30)["experiments_superseded"][0]["improvement"] == iid
    assert superseded.listing(db)[0]["improvement"] == iid
    # Write-once, and a reason is required.
    for kw in ({"kind": "invalid", "reason": "measured on the wrong cell entirely"},):
        try:
            superseded.supersede(db, iid, by="evaluator", **kw)
            raise AssertionError("a superseded marker is write-once")
        except superseded.SupersedeRefused as exc:
            assert "write-once" in str(exc)
    third = _propose(db, hypothesis=H + " measured over a longer window this time")
    try:
        superseded.supersede(db, third, kind="invalid", reason="bad", by="evaluator")
        raise AssertionError("a reason is required")
    except superseded.SupersedeRefused:
        pass


# ---- F-412 ----------------------------------------------------------------------------------

def test_f412_answered_research_reaches_the_sandbox_as_a_bounded_experiment():
    import test_w4_fmbatch1_research as T
    from brambleloop.improve import bounded, cells, runner
    from brambleloop.intel import research as R

    db = _db()
    tid = T._open(db, decision="pricing.bundle_size")["task"]
    R.add_source(db, tid, source="Etsy", citation="https://etsy.com/p", retrieval="fetched",
                 read_on=T.NOW.date())
    R.add_finding(db, tid, statement="no cap is published", claim_class="fact",
                  rests_on=("S1",))
    R.add_finding(db, tid, statement="bundles of five files convert better than twenty",
                  claim_class="hypothesis")
    nt = {"what": "list one product as a 5-file and a 20-file bundle for two weeks",
          "falsified_if": "conversion is equal within noise", "max_days": 14,
          "max_spend_cad": 0}
    R.answer(db, tid, outcome="test it", now=T.NOW,
             effect={"kind": "hypothesis_produced", "statement": "bundle size hypothesis"},
             conclusion=T._empty(next_test=nt))
    unowned = T._open(db, trigger="t:other", decision="unmapped.thing",
                      question="Does an unmapped decision get filed under a guess?")["task"]
    out = runner.run(db)
    intake = out["research_intake"]
    assert [b["task"] for b in intake["bridged"]] == [tid], intake
    iid = intake["bridged"][0]["improvement"]
    state, ev, _b, _r = _row(db, iid)
    assert state == cells.PROPOSED and ev["scope"]["max_days"] == 14
    assert ev["proposed_by"] == bounded.RESEARCH_PROPOSER
    assert ev["evidence_ids"] == [f"research_tasks:{tid}"]
    w = next(x for x in out["waiting"] if x["improvement"] == iid)
    assert w["trial"] == bounded.TRIAL, w
    # Idempotent: the next pass bridges nothing new.
    again = runner.run(db)["research_intake"]
    assert again["bridged"] == [] and unowned


# ---- Laura CEO execution of the loop ---------------------------------------------------------

def test_laura_turns_a_stalled_experiment_into_a_measurement_mission():
    from brambleloop.improve import bounded
    from brambleloop.laura import executive
    from brambleloop.laura.executive import loop

    assert loop.PROVIDERS["self_improvement"] == ("brambleloop.improve.bounded", "learn",
                                                  "improve.measure")
    db = _db()
    quiet = executive.tick(db)
    assert "laura:provider:self_improvement" not in {p["key"] for p in quiet["priorities"]}
    assert quiet["observed"]["providers"]["self_improvement"] == "OK"
    now = datetime.now(timezone.utc)
    _point(db, "customer_experience", 0.30, now - timedelta(days=20))
    iid = _propose(db)
    bounded.start(db, iid, applied_by="customer_experience", applied_ref="faq:v2",
                  undo="restore the FAQ v1 text", now=now - timedelta(days=10))
    assert bounded.summary(db)["status"] == "DEGRADED"
    r = executive.tick(db)
    p = next(x for x in r["priorities"] if x["key"] == "laura:provider:self_improvement")
    assert p["department"] == "learn" and p["job_type"] == "improve.measure", p
    out = next(o for o in r["outcomes"] if o["priority"] == p["key"])
    # Delegated now, or already open from an earlier delegation: either way the measurement
    # the experiment waits for is queued, once.
    assert out["outcome"] in ("delegated", "in_progress"), out
    from brambleloop.core.models import Job

    with db.session() as s:
        from sqlalchemy import select

        assert [j.status for j in s.scalars(select(Job).where(
            Job.job_type == "improve.measure"))], "no improve.measure job"


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
