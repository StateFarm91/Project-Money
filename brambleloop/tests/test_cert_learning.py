"""Adversarial certification: the learning loop (measure -> mine -> propose -> judge ->
promote -> monitor -> rollback), driven through the real handlers on a seeded file DB.

Each test tries to falsify one claim the loop makes about itself. A failing test is a
finding; assertions state the documented contract and are not weakened to get green.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import importlib
import pkgutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import (bus, cells, director, governance, monitor,  # noqa: E402
                                 tiers)

H = ("re-ranking candidate phrases by cluster before length should raise the number of "
     "distinct clusters the catalogue answers within a week")


def _db() -> Database:
    tmp = tempfile.mkdtemp(prefix="cert_learn_")
    db = Database(f"sqlite:///{tmp}/learn.sqlite")
    db.create_all()
    from brambleloop.agents.registry import Registry

    Registry(db).seed_defaults()
    return db


_N = [0]


def _run(db, job_type: str, agent: str = "orchestrator") -> dict:
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline, release  # noqa: F401 -- registers handlers
    from brambleloop.runtime.worker import JobContext, handlers

    _N[0] += 1
    q = JobQueue(db)
    job = q.enqueue(agent, job_type, {}, idempotency_key=f"cert:{job_type}:{_N[0]}")
    ctx = JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=None)
    return handlers.get(job_type)(ctx)


def _tested(db, cell="seo_search", *, proposed_by="listing", touches=("weights",),
            baseline=1.0, result=2.0) -> int:
    cells.record_capability(db, cell, baseline, sample=5)
    iid = cells.propose(db, cell=cell, hypothesis=H, expected_effect="more clusters",
                        rollback_ref=f"weights:{cell}:v1", touches=touches,
                        proposed_by=proposed_by)
    if not cells.BY_KEY[cell].higher_is_better:
        result = baseline - (result - baseline)
    assert cells.test_result(db, iid, result) == cells.TESTING
    return iid


def _state(db, iid):
    from brambleloop.core.models import Improvement

    with db.session() as s:
        r = s.get(Improvement, iid)
        return r.state, dict(r.evidence or {})


def _refused(fn) -> bool:
    try:
        fn()
    except (cells.ImprovementRefused, governance.GovernanceRefused, tiers.TierRefused):
        return True
    return False


# ---- the whole chain through the handlers ---------------------------------------------------


def test_full_chain_measure_mine_propose_judge_promote_monitor_rollback():
    from brambleloop.core.models import Incident, Lesson
    from test_improve_handlers import _seed

    db = _db()
    _seed(db)
    measured = _run(db, "improve.measure")
    assert measured["measured"] >= 1, measured
    mined = _run(db, "improve.mine")
    assert mined["published"] >= 1 and mined["routed_to"], mined
    again = _run(db, "improve.mine")
    assert again["published"] == 0, "mining the same evidence twice published twice"

    base = cells.latest_capability(db, "seo_search")
    assert base is not None
    iid = cells.propose(db, cell="seo_search", hypothesis=H, expected_effect="more clusters",
                        rollback_ref="weights:seo:v1", touches=("weights",),
                        proposed_by="listing")
    assert cells.test_result(db, iid, base + 3) == cells.TESTING
    weekly = _run(db, "improve.weekly")
    assert iid not in [e["improvement"] for e in weekly["executed"]], \
        "the weekly cycle promoted an unapproved change"
    cells.approve(db, iid, approved_by="evaluator", why="beat the baseline on the holdout")
    weekly = _run(db, "improve.weekly")
    assert iid in [e["improvement"] for e in weekly["executed"]], weekly["queued_for_authority"]
    assert _state(db, iid)[0] == cells.PROMOTED

    # A production reading below the baseline captured before the change.
    cells.record_capability(db, "seo_search", base - 1, detail={"from": "measure"})
    mon = _run(db, "improve.monitor")
    assert mon["reverted"] == [iid], mon
    assert _state(db, iid)[0] == cells.REVERTED
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == f"{monitor.ROLLBACK_SIGNATURE}:{iid}"))
        lesson = s.scalar(select(Lesson).where(
            Lesson.evidence_ref == f"rollback:improvement:{iid}"))
    assert inc is not None and inc.resolved is False and "weights:seo:v1" in inc.summary
    assert lesson is not None and "quality" in lesson.routed_to
    # Idempotent: a second monitor pass with no new reading neither re-reverts nor re-opens.
    mon2 = _run(db, "improve.monitor")
    assert mon2["reverted"] == [], mon2


# ---- separation of duties ------------------------------------------------------------------


def test_proposer_cannot_approve_or_promote_through_any_door():
    db = _db()
    iid = _tested(db, proposed_by="listing")
    leaks = []
    for label, attempt in (
            ("approve exact", lambda: cells.approve(db, iid, approved_by="listing")),
            ("approve padded", lambda: cells.approve(db, iid, approved_by="  listing ")),
            ("approve case", lambda: cells.approve(db, iid, approved_by="Listing")),
            ("promote exact", lambda: cells.promote(db, iid, promoted_by="listing")),
            ("promote anonymous", lambda: cells.promote(db, iid)),
            ("execute_approved as proposer",
             lambda: _assert_not_executed(director.execute_approved(db, executor="listing"),
                                          iid))):
        if not _refused(attempt):
            leaks.append(label)
        if _state(db, iid)[0] != cells.TESTING:
            leaks.append(f"{label} changed state to {_state(db, iid)[0]}")
            break
    assert not leaks, f"the proposer got through: {leaks}"


def test_promote_refuses_a_case_or_whitespace_variant_of_the_proposer():
    db = _db()
    iid = _tested(db, proposed_by="listing")
    cells.approve(db, iid, approved_by="evaluator", why="independent holdout win")
    ok = _refused(lambda: cells.promote(db, iid, promoted_by="listing "))
    assert ok, ("cells.promote compares promoted_by to the proposer without normalising: "
                f"'listing ' promoted listing's own change (state {_state(db, iid)[0]})")


def _assert_not_executed(out, iid):
    if iid in [e["improvement"] for e in out["executed"]]:
        return
    raise cells.ImprovementRefused("not executed")


def test_promote_requires_an_independent_approval():
    db = _db()
    iid = _tested(db, proposed_by="listing")
    ok = _refused(lambda: cells.promote(db, iid, promoted_by="evaluator"))
    assert ok, ("cells.promote promoted a TESTING change nobody approved: approval is only "
                "checked by director.execute_approved, not by the door it calls")


def test_an_unattributed_proposal_cannot_be_self_approved_and_self_promoted():
    db = _db()
    iid = _tested(db, proposed_by="")
    cells.approve(db, iid, approved_by="listing", why="i wrote it and it is good")
    ok = _refused(lambda: cells.promote(db, iid, promoted_by="listing"))
    assert ok, ("a proposal with no recorded proposer is approved and promoted by the same "
                "agent: separation of duties is opt-in via proposed_by")


# ---- governance: gate weakening and Product Truth ------------------------------------------


EVASIONS = (
    ("verb inflection", "lowering the certification gate threshold from 0.9 to 0.8 should "
                        "raise the first pass rate", ("weights",)),
    ("synonym verb", "decrease the gate threshold on certification so more patterns certify "
                     "first time", ("weights",)),
    ("object beyond 4 tokens", "lower the minimum acceptable certification score threshold so "
                               "more patterns pass first time", ("weights",)),
    ("numeric change to a named gate constant", "set REGRESSION_TOLERANCE from 0.05 to 0.25 so "
                                                "fewer promoted changes are reverted", ("weights",)),
    ("protected gate named, no weaken verb", "raise the allowed gauge deviation in "
                                             "deterministic validation from five to fifteen "
                                             "percent so more patterns certify", ("weights",)),
    ("raise a tolerance on a check", "raise the tolerance on the round count check so fewer "
                                     "patterns are refused by the compiler", ("tolerance",)),
    ("product truth by description", "let the fabric renderer read stitches from the beauty "
                                     "photo instead of the certified chart to speed renders",
     ("prompt",)),
    ("product truth, capitalised touch", "relax the lock a little so more renders clear the "
                                         "inspection each week", ("Product_Truth",)),
    ("product truth, padded touch", "relax the lock a little so more renders clear the "
                                    "inspection each week", (" product_truth",)),
    ("product truth touched, neutral wording", "replace the certified chart source used by the "
                                               "fabric renderer with the photo derived stitch "
                                               "map", ("product_truth",)),
)


def test_controls_the_documented_refusals_still_refuse():
    for h, t in (("relax the product truth lock so more fabric renders pass inspection", ("weights",)),
                 ("lower the gate threshold on certification so the defect count stops rising", ("weights",)),
                 ("relax the lock a little", ("product_truth",))):
        assert governance.check(h, touches=t).ok is False, h


def test_gate_weakening_and_product_truth_evasions_are_refused_at_propose():
    db = _db()
    cells.record_capability(db, "pattern_engineering", 0.5, sample=5)
    bypassed = []
    for label, hypothesis, touches in EVASIONS:
        if not _refused(lambda: cells.propose(
                db, cell="pattern_engineering", hypothesis=hypothesis,
                expected_effect="higher first pass", rollback_ref="cfg:v1",
                touches=touches, proposed_by="crochet_engineer")):
            bypassed.append(label)
    assert not bypassed, f"{len(bypassed)}/{len(EVASIONS)} evasions accepted: {bypassed}"


def test_every_protected_gate_grades_into_the_owner_gated_tier():
    wrong = {g: tiers.classify((g,)).key for g in governance.PROTECTED_GATES
             if tiers.classify((g,)).key != "gate"}
    assert not wrong, ("protected gates that tiers grades below 'gate' (promotable without "
                       f"owner approval once proposed with neutral wording): {wrong}")


def test_product_truth_change_cannot_promote_without_owner_approval():
    db = _db()
    cells.record_capability(db, "creative_assets", 0.5, sample=5)
    iid = cells.propose(db, cell="creative_assets",
                        hypothesis=("replace the certified chart source used by the fabric "
                                    "renderer with the photo derived stitch map"),
                        expected_effect="fewer blocked assets", rollback_ref="render:v1",
                        touches=("product_truth",), proposed_by="asset_truth")
    cells.test_result(db, iid, 0.3)
    cells.approve(db, iid, approved_by="evaluator", why="beat baseline on holdout set")
    promoted = not _refused(lambda: cells.promote(
        db, iid, promoted_by="evaluator",
        evidence=(tiers.REGRESSION_TEST, tiers.ADVERSARIAL_TEST)))
    assert not promoted, ("a change touching product_truth promoted with caller-asserted "
                          "evidence and no owner_approval (graded 'code', not 'gate')")


# ---- failed / unapproved experiments ---------------------------------------------------------


def test_failed_or_baseline_less_experiments_cannot_promote():
    db = _db()
    cells.record_capability(db, "seo_search", 5.0)
    worse = cells.propose(db, cell="seo_search", hypothesis=H, expected_effect="x",
                          rollback_ref="w:v1", touches=("weights",), proposed_by="listing")
    assert cells.test_result(db, worse, 4.0) == cells.REJECTED
    equal = cells.propose(db, cell="seo_search", hypothesis=H, expected_effect="x",
                          rollback_ref="w:v1", touches=("weights",), proposed_by="listing")
    assert cells.test_result(db, equal, 5.0) == cells.REJECTED
    fresh = cells.propose(db, cell="growth", hypothesis=H, expected_effect="x",
                          rollback_ref="w:v1", touches=("weights",), proposed_by="growth")
    assert cells.test_result(db, fresh, 99.0) == cells.REJECTED    # no baseline
    for iid in (worse, equal, fresh):
        assert _refused(lambda: cells.approve(db, iid, approved_by="evaluator"))
        assert _refused(lambda: cells.promote(db, iid, promoted_by="evaluator"))
        assert _state(db, iid)[0] == cells.REJECTED
    out = director.execute_approved(db)
    assert out["executed"] == []


# ---- regression, incident, lessons ------------------------------------------------------------


def test_regression_inside_tolerance_but_below_baseline_reverts_with_incident():
    from brambleloop.core.models import Incident

    db = _db()
    iid = _tested(db, "seo_search", baseline=10.0, result=10.2)
    cells.approve(db, iid, approved_by="evaluator", why="beat baseline on holdout")
    cells.promote(db, iid, promoted_by="evaluator")
    cells.record_capability(db, "seo_search", 9.9, detail={"from": "measure"})  # -2.9%, < base
    out = monitor.sweep(db)
    assert [r["improvement"] for r in out["reverted"]] == [iid], out["note"]
    with db.session() as s:
        assert s.scalar(select(Incident).where(
            Incident.signature == f"{monitor.ROLLBACK_SIGNATURE}:{iid}")) is not None


def test_lessons_persist_across_connections_and_reach_other_products_briefs():
    db = _db()
    url = str(db.engine.url)
    lid = bus.publish(db, origin_cell="quality", subject="construction_preference",
                      statement="seamless yoke constructions certified first pass far more "
                                "often than set-in sleeves this month",
                      evidence_ref="cert:lesson:1", confidence="measured")
    again = bus.publish(db, origin_cell="quality", subject="construction_preference",
                        statement="same evidence re-read tonight should not duplicate the lesson",
                        evidence_ref="cert:lesson:1", confidence="measured")
    assert lid == again
    db2 = Database(url)                              # a fresh process's view of the same file
    assert lid in [l["id"] for l in bus.inbox(db2, "product_creativity")]
    a = bus.brief_lessons(db2, artifact="cable-throw")
    b = bus.brief_lessons(db2, artifact="granny-cardigan")
    assert lid in a["lesson_ids"] and lid in b["lesson_ids"]
    assert a["provenance"]["recorded"] and b["provenance"]["recorded"]
    assert bus.brief_lessons(db2, artifact="cable-throw")["provenance"]["recorded"] is False
    bus.acted_on(db2, lid, "product_creativity", how="yoke-first briefs")
    assert lid not in [l["id"] for l in bus.inbox(Database(url), "product_creativity")]


# ---- conflicts / overfitting ------------------------------------------------------------------


def test_opposed_metrics_block_both_and_a_proposer_cannot_resolve():
    db = _db()
    a = _tested(db, "product_creativity", proposed_by="market_radar")
    b = _tested(db, "pattern_engineering", proposed_by="crochet_engineer",
                touches=("ranking",))
    for iid in (a, b):
        cells.approve(db, iid, approved_by="evaluator", why="beat baseline on holdout")
    assert _refused(lambda: cells.promote(db, a, promoted_by="evaluator"))
    assert _refused(lambda: cells.promote(db, b, promoted_by="evaluator"))
    assert director.execute_approved(db)["executed"] == []
    assert _refused(lambda: director.resolve(db, keep=a, drop=b, resolved_by="market_radar",
                                             why="creativity matters more than first pass"))
    director.resolve(db, keep=a, drop=b, resolved_by="owner",
                     why="novelty is the brand; certification rate recovers later")
    assert cells.promote(db, a, promoted_by="evaluator") == cells.PROMOTED


def test_shared_surface_conflict_is_not_evaded_by_spelling_the_surface_differently():
    db = _db()
    a = _tested(db, "seo_search", proposed_by="listing", touches=("weights",))
    b = _tested(db, "quality", proposed_by="quality_director", touches=("Weights ",))
    found = director.conflicts(db)
    assert any({f["a"], f["b"]} == {a, b} for f in found), (
        "director.conflicts intersects raw strings; tiers lower-cases and strips the same "
        "surfaces, so 'Weights ' and 'weights' are one surface to the tier and two to the "
        "Director")


# ---- nothing mutates source constants ---------------------------------------------------------


def _constants() -> dict:
    import brambleloop

    snap = {}
    for pkg in ("gates", "cir", "publish", "quality", "improve"):
        mod = importlib.import_module(f"brambleloop.{pkg}")
        for info in pkgutil.iter_modules(mod.__path__):
            name = f"brambleloop.{pkg}.{info.name}"
            try:
                m = importlib.import_module(name)
            except Exception:  # noqa: BLE001 - an unimportable module has no runtime state
                continue
            for key, value in vars(m).items():
                if key.isupper() and isinstance(value, (int, float, str, tuple, list, dict,
                                                        set, frozenset)):
                    snap[f"{name}.{key}"] = repr(copy.deepcopy(value))
    assert brambleloop
    return snap


def test_a_full_nightly_and_weekly_run_mutates_no_constant():
    from test_improve_handlers import _seed

    before = _constants()
    assert len(before) > 100, len(before)
    db = _db()
    _seed(db)
    iid = _tested(db, "seo_search", proposed_by="listing")
    cells.approve(db, iid, approved_by="evaluator", why="beat baseline on holdout")
    for jt in ("improve.measure", "improve.mine", "improve.nightly", "improve.weekly",
               "improve.retrospective", "improve.monitor", "improve.nightly",
               "improve.weekly"):
        _run(db, jt)
    after = _constants()
    changed = sorted(k for k in before if after.get(k) != before[k])
    assert not changed, f"constants changed at runtime: {changed[:10]}"


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            t0 = time.monotonic()
            try:
                fn()
                print(f"OK   {name} ({time.monotonic() - t0:.1f}s)")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(e).__name__}: {str(e)[:600]}")
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
