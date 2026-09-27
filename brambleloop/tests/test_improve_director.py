"""The controlled loop end to end: governance, separation of duties, the Director, the week.

Requirements 85, 91, 92, 93, 96, 100, 102, 178, 192. "Agents constantly improve the system"
is only safe if each step refuses the failure it exists for: a self-review that weakens a
gate, an agent promoting its own change, two cells optimising against each other, a weekly
cycle that writes reports and executes nothing (or executes everything), a promotion that
regresses and is reverted silently, and a league with nothing registered to challenge.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import (bootstrap, cells, director, governance, monitor,  # noqa: E402
                                 profiles)

H = ("a change to how {cell} ranks its candidates should move its metric in the right "
     "direction within one week of evidence")


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _improvements(db):
    from sqlalchemy import select

    from brambleloop.core.models import Improvement

    with db.session() as s:
        return [(r.id, r.cell, r.state) for r in s.scalars(select(Improvement))]


def _tested(db, cell: str, *, touches=("weights",), proposed_by="market_radar",
            baseline=0.5, result=0.6) -> int:
    """A proposal that beat its baseline in the sandbox and now awaits a judge."""
    cells.record_capability(db, cell, baseline, sample=10)
    better = result if cells.BY_KEY[cell].higher_is_better else baseline - (result - baseline)
    iid = cells.propose(db, cell=cell, hypothesis=H.format(cell=cell),
                        expected_effect="metric improves", rollback_ref=f"weights:{cell}:v1",
                        touches=touches, proposed_by=proposed_by)
    assert cells.test_result(db, iid, better) == cells.TESTING
    return iid


# ---- governance, end to end through the self-review queue ----------------------------------


def test_a_self_review_that_weakens_a_gate_threshold_is_refused_end_to_end():
    db = _db()
    reviews = [{"cell": "quality", "measurements": 1, "proposals": [{
        "kind": "declining_capability",
        "hypothesis": ("lower the gate threshold on certification so the defect count stops "
                       "rising across the next three measurements"),
        "touches": ("weights",), "rollback_ref": "weights:quality:v1"}]}]
    out = profiles.queue_proposals(db, reviews=reviews)
    assert out["persisted"] == 0 and len(out["refused"]) == 1
    assert "weaken a policy gate" in out["refused"][0]["why"]
    assert _improvements(db) == []


def test_a_self_review_that_weakens_product_truth_is_refused_end_to_end():
    """Declaring an innocuous surface does not make a Product Truth weakening tuning."""
    db = _db()
    for hypothesis in (
            "relax the product truth lock so more fabric renders pass inspection each week",
            "loosen product-truth matching tolerance so listing renders clear faster"):
        reviews = [{"cell": "creative_assets", "measurements": 1, "proposals": [{
            "kind": "declining_capability", "hypothesis": hypothesis,
            "touches": ("weights",), "rollback_ref": "weights:assets:v1"}]}]
        out = profiles.queue_proposals(db, reviews=reviews)
        assert out["persisted"] == 0, hypothesis
        assert "product_truth" in out["refused"][0]["why"], out["refused"]
    assert _improvements(db) == []
    # Touching the protected surface directly, and a gate-tier surface, are refused too.
    assert governance.check("relax the lock a little", touches=("product_truth",)).ok is False
    assert governance.check("relax the tolerance", touches=("truth_gate",)).ok is False
    # And strengthening it is still allowed.
    assert governance.check("tighten the product truth lock so fewer mismatched renders ship",
                            touches=("product_truth",)).ok is True


def test_the_nightly_queue_is_real_and_bounded():
    db = _db()
    first = profiles.queue_proposals(db)
    assert first["persisted"] == 12                    # every cell is unmeasured tonight
    assert all(q["touches"] == ["cadence"] for q in first["queued"])
    again = profiles.queue_proposals(db)
    assert again["persisted"] == 0 and len(again["already_open"]) == 12
    from brambleloop.core.models import Improvement
    with db.session() as s:
        row = s.get(Improvement, first["queued"][0]["improvement"])
        assert row.evidence["proposed_by"] and row.rollback_ref


# ---- separation of duties ------------------------------------------------------------------


def test_a_proposing_agent_cannot_approve_or_promote_its_own_change():
    db = _db()
    iid = _tested(db, "seo_search", proposed_by="listing")
    for attempt in (lambda: cells.approve(db, iid, approved_by="listing"),
                    lambda: cells.promote(db, iid, promoted_by="listing"),
                    lambda: cells.promote(db, iid)):
        try:
            attempt()
        except cells.ImprovementRefused:
            continue
        raise AssertionError("a proposer approved or promoted its own change")
    # A role without the judging power may not approve either.
    try:
        cells.approve(db, iid, approved_by="failure_miner")
    except cells.ImprovementRefused:
        pass
    else:
        raise AssertionError("a proposing role approved a change")
    cells.approve(db, iid, approved_by="evaluator", why="beat baseline on the holdout")
    assert cells.promote(db, iid, promoted_by="evaluator") == cells.PROMOTED


# ---- the Improvement Director (#91) --------------------------------------------------------


def test_two_cells_touching_one_surface_are_flagged_and_neither_promotes():
    db = _db()
    a = _tested(db, "seo_search", proposed_by="listing")
    b = _tested(db, "creative_assets", proposed_by="asset_truth")
    for iid in (a, b):
        cells.approve(db, iid, approved_by="evaluator", why="beat the baseline")
    found = director.detect(db)
    assert {frozenset((c["a"], c["b"])) for c in found["conflicts"]} == {frozenset((a, b))}
    for iid in (a, b):
        try:
            cells.promote(db, iid, promoted_by="evaluator")
        except cells.ImprovementRefused as exc:
            assert "conflict" in str(exc)
        else:
            raise AssertionError("a conflicted change was promoted")
    # A proposer may not decide its own conflict; somebody else can.
    try:
        director.resolve(db, keep=a, drop=b, resolved_by="listing",
                         why="search matters more than the thumbnail this week")
    except cells.ImprovementRefused:
        pass
    else:
        raise AssertionError("a proposer resolved its own conflict")
    director.resolve(db, keep=a, drop=b, resolved_by="owner",
                     why="search language is the constraint named this week")
    assert cells.promote(db, a, promoted_by="evaluator") == cells.PROMOTED
    assert dict((i, st) for i, _c, st in _improvements(db))[b] == cells.REJECTED


def test_opposing_metrics_conflict_even_on_different_surfaces():
    db = _db()
    a = _tested(db, "finance", touches=("weights",), proposed_by="cfo")
    b = _tested(db, "runtime", touches=("ranking",), proposed_by="orchestrator")
    pairs = director.conflicts(db)
    assert len(pairs) == 1 and pairs[0]["opposed_metrics"] and not pairs[0]["shared_surfaces"]
    assert {pairs[0]["a"], pairs[0]["b"]} == {a, b}


def test_measurement_proposals_never_conflict():
    db = _db()
    profiles.queue_proposals(db)                 # twelve proposals, all touching "cadence"
    assert director.conflicts(db) == []


def test_every_cell_has_a_backlog_and_experiment_set():
    db = _db()
    profiles.queue_proposals(db)
    iid = _tested(db, "seo_search", proposed_by="listing")
    books = director.backlogs(db)
    assert set(books) == set(cells.BY_KEY)
    assert [r["id"] for r in books["seo_search"]["experiments"]] == [iid]
    assert len(books["pricing"]["backlog"]) == 1


# ---- the week (#100) -----------------------------------------------------------------------


def test_the_week_executes_only_approved_tested_scoring_changes():
    db = _db()
    approved = _tested(db, "seo_search", proposed_by="listing")
    cells.approve(db, approved, approved_by="evaluator", why="beat the baseline cleanly")
    unapproved = _tested(db, "market_radar", touches=("priority",), proposed_by="radar")
    prompt = _tested(db, "creative_assets", touches=("prompt",), proposed_by="asset_truth")
    cells.approve(db, prompt, approved_by="evaluator", why="beat the baseline cleanly")
    gate = _tested(db, "quality", touches=("release",), proposed_by="quality_director")
    out = director.execute_approved(db)
    assert [e["improvement"] for e in out["executed"]] == [approved]
    queued = {q["improvement"]: q for q in out["queued_for_authority"]}
    assert set(queued) == {unapproved, prompt, gate}
    assert queued[gate]["authority"] == "owner"
    assert "not yet approved" in queued[unapproved]["why"]


def test_the_retrospective_names_what_to_stop_and_what_is_next():
    db = _db()
    cells.record_capability(db, "seo_search", 3.0, sample=5)
    for _ in range(2):
        iid = cells.propose(db, cell="seo_search", hypothesis=H.format(cell="seo_search"),
                            expected_effect="more clusters", rollback_ref="w:1",
                            touches=("weights",), proposed_by="listing")
        cells.test_result(db, iid, 1.0)          # worse: rejected, the same reason twice
    _tested(db, "pricing", proposed_by="pricing")
    report = cells.retrospective(db)
    for key in ("stop_doing", "top_next_upgrades", "experiments_completed",
                "experiments_killed", "learned", "department_health", "bottleneck",
                "regressed_cells"):
        assert key in report, key
    assert len(report["experiments_killed"]) == 2
    assert any("tactic family in seo_search" in s["stop"] for s in report["stop_doing"])
    assert report["top_next_upgrades"][0]["cell"] == "pricing"
    assert report["top_next_upgrades"][0]["next_step"] == "an independent judge's approval"


# ---- monitoring and rollback (#93) ---------------------------------------------------------


def test_a_regression_below_baseline_is_reverted_with_a_rollback_proposal():
    from sqlalchemy import select

    from brambleloop.core.models import Incident, Lesson

    db = _db()
    iid = _tested(db, "seo_search", proposed_by="listing", baseline=3.0, result=4.0)
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline cleanly")
    cells.promote(db, iid, promoted_by="evaluator")
    cells.record_capability(db, "seo_search", 2.0, sample=5,
                            detail={"from": "improve.measure"})
    out = monitor.sweep(db)
    assert [r["improvement"] for r in out["reverted"]] == [iid]
    rollback = out["reverted"][0]["rollback"]
    assert rollback["opened"] and rollback["rollback_ref"] == "weights:seo_search:v1"
    again = monitor.sweep(db)
    assert again["reverted"] == [] and again["promoted"] == 0
    with db.session() as s:
        incidents = list(s.scalars(select(Incident).where(
            Incident.signature == f"improve-rollback:{iid}")))
        lessons = list(s.scalars(select(Lesson).where(
            Lesson.evidence_ref == f"rollback:improvement:{iid}")))
    assert len(incidents) == 1 and not incidents[0].resolved
    assert len(lessons) == 1


def test_below_baseline_reverts_even_inside_the_tolerance():
    """3.0 baseline, 3.1 won the promotion, production reads 2.99: within 5% of the sandbox
    number, and worse than not having made the change at all."""
    db = _db()
    iid = _tested(db, "seo_search", proposed_by="listing", baseline=3.0, result=3.1)
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline narrowly")
    cells.promote(db, iid, promoted_by="evaluator")
    out = cells.monitor(db, iid, 2.99)
    assert out["action"] == "reverted" and out["below_baseline"] is True


def test_a_promotion_holding_above_baseline_is_held_once_per_reading():
    db = _db()
    iid = _tested(db, "seo_search", proposed_by="listing", baseline=3.0, result=4.0)
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline cleanly")
    cells.promote(db, iid, promoted_by="evaluator")
    assert monitor.sweep(db)["waiting"][0]["improvement"] == iid
    cells.record_capability(db, "seo_search", 4.1, sample=5, detail={"from": "improve.measure"})
    assert [h["improvement"] for h in monitor.sweep(db)["held"]] == [iid]
    assert monitor.sweep(db)["unchanged"][0]["improvement"] == iid


# ---- the league's incumbents (#96) ---------------------------------------------------------


def test_incumbents_register_once_and_no_challenger_runs():
    from sqlalchemy import func, select

    from brambleloop.core.models import ConfigVersion
    from brambleloop.gateway import routing

    db = _db()
    first = bootstrap.ensure(db)
    assert first["routing"]["registered"] == len(routing.TASKS)
    assert first["challengers_run"] == 0
    with db.session() as s:
        count = s.scalar(select(func.count()).select_from(ConfigVersion))
        incumbents = s.scalar(select(func.count()).select_from(ConfigVersion)
                              .where(ConfigVersion.incumbent.is_(True)))
    second = bootstrap.ensure(db)
    assert second["routing"] == {"registered": 0, "unchanged": len(routing.TASKS)}
    assert second["challengers_run"] == 0
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(ConfigVersion)) == count
    assert incumbents == count                   # nothing but incumbents: nothing was run


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
