"""ENG-P0-PIPELINE: a watchlist arena is not stopped by radar slots that carry no concept.

Production readback (46908fe66, evidence 2026-11-28T06:04Z): factory_visibility.supply
last_admit {ready 7, admitted 0, waiting_on_research 7}; ready_by_pod garments 4 and hats 3,
both research `absent` / `gap_not_pursuing`; concepts_admitted 0 and cir.draft 0 every day
since 2026-11-22. The same two pods read `gap_not_pursuing` on 2026-11-21
(tests/test_supply_research.py docstring) and nothing reopened them.

Cause. `intel.watchlist.review` routes an open arena to the radar.score of the pool concepts
that match its pod, and stops the arena (`not_pursuing`, plus a creative_rejection lesson)
after MAX_FAILED_ATTEMPTS "measured" attempts without a promotion. For garments
(lattice-triangle-shawl, cropped-cardigan) and for hats (cloudline-baby-hat,
alpine-slouch-beanie) those matches are radar SLOTS that name a category and a price and
carry no concept at all, so #88 refuses them as "not a concept yet" before any other check
applies. `score_outcome` counted those refusals as measurements of the arena. Once stopped,
`concept_pool.research_status` (D-ENG-SUPPLY-FEED: `not_pursuing` closes the arena) withheld
the arena's research from the pool's own READY original concepts for good.

Fix. (1) `score_outcome` reads a #88 no-concept refusal (`preengineering.judged_no_concept`)
as `not_attempted`: the slot is still refused, the arena was not measured. (2)
`reopen_mismeasured_stops`, run by the daily comparison and by the review, re-judges a stop
this rule made from its attempts' own radar.score jobs; if fewer than MAX_FAILED_ATTEMPTS
are still measured failures, the gap moves `not_pursuing -> uncovered`, keeps only genuine
attempts and the stop's lesson is withdrawn with that evidence. No gate is changed: the
research floor, intake, originality and the pre-engineering gate judge everything after.

Every listing, shop, judgement and product here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_p0_mismeasured_stop.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

import test_supply_feed as SF  # noqa: E402 - the nine-shop scan fixture and its comparisons
import test_w4_intelrec_watchlist as IW  # noqa: E402 - the enqueuer

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from brambleloop.core.models import CoverageGap, Job, JobStatus, Lesson  # noqa: E402
from brambleloop.creative import preengineering as PE  # noqa: E402
from brambleloop.intel import coverage  # noqa: E402
from brambleloop.intel import watchlist as W  # noqa: E402
from brambleloop.radar import concept_pool as P  # noqa: E402
from brambleloop.radar.opportunity import POOL, score_concept  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

NOW = SF.NOW
PLACEHOLDERS = ("lattice-triangle-shawl", "cropped-cardigan")   # the garments matches


def _gap(db, pod):
    with db.session() as s:
        g = s.scalar(select(CoverageGap).where(CoverageGap.benchmark_key == W.WATCHLIST_KEY,
                                               CoverageGap.pod == pod))
        return g.id, g.state, dict(g.evidence or {})


def _run_scores_and_settle(db):
    w = Worker(db, "p0-score", job_types=["radar.score"])
    while w.run_once():
        pass
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "radar.score")):
            if j.finished_at is not None:
                j.finished_at = j.finished_at - W.SETTLE - timedelta(hours=1)


def _new_corroborator(db, gid, n):
    """A later daily comparison saw one more corroborating shop: the arena's fingerprint moves,
    so the next routed score is a new attempt, not a repeat measurement (N-3)."""
    with db.session() as s:
        row = s.get(CoverageGap, gid)
        ev = dict(row.evidence or {})
        ev["corroborated_by"] = list(ev.get("corroborated_by") or []) + [f"fixture-shop-{n}"]
        row.evidence = ev
        flag_modified(row, "evidence")


def _stop_garments_the_old_way(db):
    """The production state, made by the real review with the defect restored: placeholder
    refusals counted as measured attempts until the arena was stopped."""
    gid, state, _ev = _gap(db, "garments")
    assert state == coverage.UNCOVERED, state
    q = IW._enqueuer(db)
    real = PE.judged_no_concept
    PE.judged_no_concept = lambda gate: False
    try:
        for n in range(W.MAX_FAILED_ATTEMPTS + 1):
            W.review(db, enqueue=q, now=NOW)
            _run_scores_and_settle(db)
            if _gap(db, "garments")[1] == coverage.NOT_PURSUING:
                break
            _new_corroborator(db, gid, n)
        W.review(db, enqueue=q, now=NOW)
    finally:
        PE.judged_no_concept = real
    gid, state, ev = _gap(db, "garments")
    assert state == coverage.NOT_PURSUING, (state, ev.get("failed_attempts"))
    assert W._decision(db, gid)["last"] == "stopped_after_failures"
    return gid


def _state():
    db, _ev = SF._production_state()
    W.record_comparison(db, now=NOW)       # today's comparison: research fresh for the pool
    return db


# ---- the classification ----------------------------------------------------------------------

def test_a_placeholder_slot_is_judged_no_concept_and_a_real_concept_is_not():
    by = {s.slug: s for s in POOL}
    for slug in PLACEHOLDERS:
        gate = PE.gate_concept(None, score_concept(by[slug], NOW.date()).to_dict(),
                               today=NOW.date())
        assert gate["decision"] == PE.REFUSED and gate["failed"] == ["premise_thumbnail"]
        assert PE.judged_no_concept(gate), gate["reasons"]
        # the stored radar.score output keeps only failed/reasons, and is judged the same
        assert PE.judged_no_concept({k: gate[k] for k in ("failed", "reasons")})
    # a built concept refused on another check, or a #88 refusal of a concept that exists,
    # is a real judgement and is never read as "no concept"
    assert not PE.judged_no_concept({"failed": ["premise_thumbnail", "novelty"],
                                     "reasons": ["#88 premise_thumbnail: x is not a concept "
                                                 "yet", "#87 novelty: a near-duplicate"]})
    assert not PE.judged_no_concept({"failed": ["premise_thumbnail"],
                                     "reasons": ["#88 premise_thumbnail: the premise does "
                                                 "not read at thumbnail size"]})
    assert not PE.judged_no_concept({"failed": [], "reasons": []})
    assert not PE.judged_no_concept(None)


def test_placeholder_refusals_are_not_attempts_and_never_stop_an_arena():
    db = _state()
    gid, _s, _e = _gap(db, "garments")
    q = IW._enqueuer(db)
    decisions = []
    for n in range(W.MAX_FAILED_ATTEMPTS + 1):
        out = W.review(db, enqueue=q, now=NOW)
        decisions += [d["last"] for d in out["decisions"] if d.get("gap") == gid]
        _run_scores_and_settle(db)
        _new_corroborator(db, gid, n)
    out = W.review(db, enqueue=q, now=NOW)
    decisions += [d["last"] for d in out["decisions"] if d.get("gap") == gid]
    gid, state, ev = _gap(db, "garments")
    assert state == coverage.UNCOVERED, (state, decisions)
    assert not ev.get("failed_attempts"), ev.get("failed_attempts")
    assert "route_refused" in decisions, decisions
    with db.session() as s:
        assert s.scalar(select(Lesson).where(
            Lesson.evidence_ref == f"watchlist_gap:{gid}")) is None
        # the slots themselves are still refused by #88: no gate was relaxed
        for j in s.scalars(select(Job).where(Job.job_type == "radar.score",
                                             Job.idempotency_key.like(f"watchlist_score:{gid}:%"))):
            assert j.status == JobStatus.DONE and (j.outputs or {}).get("promoted") is False
            assert ((j.outputs or {}).get("gate") or {}).get("failed") == ["premise_thumbnail"]


# ---- production's state, reproduced and repaired --------------------------------------------

def test_reproduces_production_ready_garments_wait_on_a_stopped_arena():
    db = _state()
    _stop_garments_the_old_way(db)
    out = P.replenish(db, now=NOW, unit_cad=0.12)
    e = out["result"]["ready_by_pod"]["garments"]
    assert e["ready"] > 0 and e["research"] == P.RESEARCH_ABSENT, e
    assert e["why"] == "gap_not_pursuing", e
    assert not [r for r in P_rows(db) if r.state == P.ADMITTED and r.pod == "garments"]


def test_the_daily_comparison_reopens_the_mismeasured_stop_and_the_pool_admits():
    db = _state()
    gid = _stop_garments_the_old_way(db)
    with db.session() as s:
        lessons = [l.id for l in s.scalars(select(Lesson).where(
            Lesson.evidence_ref == f"watchlist_gap:{gid}",
            Lesson.subject == "creative_rejection"))]
    assert lessons, "the stop published its lesson"
    got = W.record_comparison(db, now=NOW)
    assert {"gap": gid, "pod": "garments"} in got["reopened"], got["reopened"]
    gid, state, ev = _gap(db, "garments")
    assert state == coverage.UNCOVERED, state
    assert ev["failed_attempts"] == [] and len(ev["mismeasured_attempts"]) >= 2, ev
    d = W._decision(db, gid)
    assert d["last"] == W.REOPENED_DECISION, d
    assert d["history"][-1]["lessons_withdrawn"] == lessons, d["history"][-1]
    with db.session() as s:
        assert all(s.get(Lesson, i).withdrawn_at is not None for i in lessons)
    st = P.research_status(db, "garments", today=NOW.date(), now=NOW)
    assert st["status"] == P.RESEARCH_PRESENT, st
    # The allowance is unchanged (5 per run, highest priority first): successive pool passes
    # reach the garments concepts once the higher-ranked pods are admitted.
    for _ in range(12):
        out = P.replenish(db, now=NOW, unit_cad=0.12)
        assert len(out["admitted"]) <= out["allowance"]["units"] <= P.ADMIT_PER_RUN
        admitted = [r for r in P_rows(db) if r.state == P.ADMITTED and r.pod == "garments"]
        if admitted or not out["admitted"]:
            break
    assert admitted, (out["result"]["ready_by_pod"], out["allowance"])
    assert all(r.research_task_id == st["research"]["task"] for r in admitted)
    # idempotent: a second pass reopens nothing and withdraws nothing again
    assert W.reopen_mismeasured_stops(db, now=NOW) == []


def P_rows(db):
    with db.session() as s:
        rows = list(s.scalars(select(P.ConceptPoolEntry)))
        s.expunge_all()
        return rows


def test_genuine_failures_other_decisions_and_unreadable_attempts_stay_stopped():
    db = _state()
    gid = _stop_garments_the_old_way(db)
    _gid, _st, ev = _gap(db, "garments")
    ids = [i for a in ev["failed_attempts"] for i in a["job_ids"]]
    # (a) the attempts were genuine measurements: a built concept refused on its merits
    with db.session() as s:
        saved = {}
        for j in s.scalars(select(Job).where(Job.id.in_(ids))):
            saved[j.id] = dict(j.outputs or {})
            out = dict(j.outputs or {})
            out["gate"] = {"decision": "refused", "failed": ["novelty"], "unmeasured": [],
                           "reasons": ["#87 novelty: too close to a catalogue design"]}
            j.outputs = out
    assert W.reopen_mismeasured_stops(db, now=NOW) == []
    assert _gap(db, "garments")[1] == coverage.NOT_PURSUING
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.id.in_(ids))):
            j.outputs = saved[j.id]
    # (b) an attempt's job is gone (retention): nothing is inferred
    def _attempt_ids(replace):
        with db.session() as s:
            row = s.get(CoverageGap, gid)
            ev2 = dict(row.evidence or {})
            ev2["failed_attempts"] = [dict(a, job_ids=[replace.get(i, i) for i in a["job_ids"]])
                                      for a in ev2["failed_attempts"]]
            row.evidence = ev2
            flag_modified(row, "evidence")
    gone = max(ids) + 10_000
    with db.session() as s:
        assert s.get(Job, gone) is None
    _attempt_ids({ids[0]: gone})
    assert W.reopen_mismeasured_stops(db, now=NOW) == []
    assert _gap(db, "garments")[1] == coverage.NOT_PURSUING
    _attempt_ids({gone: ids[0]})
    # (c) a stop this rule did not make (an owner or other decision) is never touched
    W._record_decision(db, gid, "owner_stopped", today=NOW.date())
    assert W.reopen_mismeasured_stops(db, now=NOW) == []
    assert _gap(db, "garments")[1] == coverage.NOT_PURSUING
    # and with the rule's own stop restored, the repair applies (the cases above were real)
    W._record_decision(db, gid, "stopped_after_failures", today=NOW.date())
    assert [r["gap"] for r in W.reopen_mismeasured_stops(db, now=NOW)] == [gid]


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failed = 0
    assert TESTS
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {str(exc)[:1500]}")
            traceback.print_exc(limit=4)
    print(f"{len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
