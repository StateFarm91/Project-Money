"""CATALOGUE-UNBLOCK (2026-11-22): the owner's research-bar ruling and the catalogue defects
whose fixes live in the research, supply and inventory paths.

* R1 D-OWNER-RESEARCH-BAR -- "Drop discount, bar 0.45": no evidence multiplier, threshold
  0.45, and concepts already refused only on the old bar are re-scored through the normal
  radar.score -> products.supply admission path (WIP limit included).
* D3 -- a promoted bundle never got its cir.draft: admission read it as engine demand.
* D4 -- "certification halted by an open incident" stayed on the catalogue after the
  incident closed; a real open incident still holds.

Real code on SQLite throughout; every slug here that is not a pool concept is a TEST FIXTURE.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="catalogue_unblock_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_SUPPLY_MAX_WIP"] = "2"

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, JobStatus, Phase  # noqa: E402
from brambleloop.gates.incidents import DefectReport, IncidentTracker  # noqa: E402
from brambleloop.ops import research_rescore as RS  # noqa: E402
from brambleloop.products import demand as D  # noqa: E402
from brambleloop.products import production_inventory as INV  # noqa: E402
from brambleloop.products import supply  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import provenance  # noqa: E402
from brambleloop.radar.opportunity import POOL, score_concept  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release_recovery as RR  # noqa: E402
from brambleloop.runtime.worker import JobContext  # noqa: E402

TODAY = date(2026, 11, 22)
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/c{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _ctx(db, job=None, key="holder"):
    job = job or JobQueue(db).enqueue("orchestrator", "supply.admit", {}, idempotency_key=key)
    return JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                      phase=Phase.SHADOW)


def _done(db, job_type, inputs, outputs, key):
    job = JobQueue(db).enqueue("market_radar", job_type, inputs, idempotency_key=key)
    with db.session() as s:
        row = s.get(Job, job.id)
        row.status, row.outputs = JobStatus.DONE, outputs
    return job.id


# ---- R1: D-OWNER-RESEARCH-BAR ----------------------------------------------------------------

def test_the_bar_is_045_and_the_evidence_discount_is_not_applied():
    assert pipeline.PROMOTION_THRESHOLD == 0.45
    assert pipeline.APPLY_EVIDENCE_DISCOUNT is False
    db = _db()
    from brambleloop.core.models import InsightsSnapshot
    from datetime import datetime, timezone

    seed = next(s for s in POOL if s.slug == "chunky-ribbed-scarf")
    with db.session() as s:                     # stale foreign evidence: discount < 1
        s.add(InsightsSnapshot(keyword="chunky scarf", search_count=900,
                               geography="united states",
                               observed_on=datetime(2025, 6, 1, tzinfo=timezone.utc)))
    provenance.stamp_all(db, today=TODAY)
    v = pipeline.promotion_verdict(db, seed, score_concept(seed, TODAY).to_dict(), TODAY)
    assert v["evidence"]["measured"] and v["evidence"]["discount"] < 1.0
    assert v["evidence"]["applied"] is False
    assert v["evidence_score"] == v["rescored"].score        # recorded, not multiplied
    assert "evidence discount" not in str(v["why"] or "")


def test_a_score_between_045_and_055_now_clears_the_bar():
    db = _db()
    seed = next(s for s in POOL if s.slug == "chunky-ribbed-scarf")
    rescored = score_concept(seed, TODAY)
    real = pipeline.score_concept
    try:
        # A fixture score in the band the owner opened (0.45 <= s < 0.55).
        rescored.score = 0.5
        pipeline.score_concept = lambda *_a, **_k: rescored
        v = pipeline.promotion_verdict(db, seed, rescored.to_dict(), TODAY)
    finally:
        pipeline.score_concept = real
    assert v["adjusted"] >= pipeline.PROMOTION_THRESHOLD
    assert "below promotion threshold" not in str(v["why"] or "")


def test_research_only_refusals_are_rescored_through_the_normal_path():
    db = _db()
    old = ("score 0.4973 below promotion threshold 0.55 after the evidence discount "
           "(3 stamped row(s), mean usable weight 0.70; the opportunity score is "
           "multiplied by 0.85)")
    _done(db, "radar.score", {"slug": "alpine-slouch-beanie"},
          {"slug": "alpine-slouch-beanie", "promoted": False, "reason": old, "gate": None},
          "s1")
    # A concept the pre-engineering gate refused is not a research-bar refusal.
    _done(db, "radar.score", {"slug": "chunky-ribbed-scarf"},
          {"slug": "chunky-ribbed-scarf", "promoted": False, "reason": "premise",
           "gate": {"decision": "refused"}}, "s2")
    # A concept whose newest score promoted it is not a candidate.
    _done(db, "radar.score", {"slug": "cosy-bunny-lovey"},
          {"slug": "cosy-bunny-lovey", "promoted": False, "reason": old}, "s3a")
    _done(db, "radar.score", {"slug": "cosy-bunny-lovey"},
          {"slug": "cosy-bunny-lovey", "promoted": True}, "s3b")
    with db.session() as s:
        assert RS.candidates(s) == ["alpine-slouch-beanie"]
    q = JobQueue(db)
    out = RS.run(db, lambda a, jt, inp, idempotency_key: q.enqueue(
        a, jt, inp, idempotency_key=idempotency_key), commit="abc123", as_of="2026-11-22")
    assert out["enqueued"] == ["alpine-slouch-beanie"]
    again = RS.run(db, lambda a, jt, inp, idempotency_key: q.enqueue(
        a, jt, inp, idempotency_key=idempotency_key), commit="abc123", as_of="2026-11-22")
    assert again["enqueued"] == [] and again["duplicates"] == 1   # once per commit
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.idempotency_key.like("rescore-bar:%"))))
    assert [j.job_type for j in jobs] == ["radar.score"]          # the normal path
    assert jobs[0].inputs["slug"] == "alpine-slouch-beanie"
    # Nothing here drafted, admitted or promoted anything.
    with db.session() as s:
        assert s.scalar(select(Job.id).where(Job.job_type == "cir.draft")) is None


def test_the_class_c_refusal_is_also_rescored():
    assert RS.is_research_only_refusal(
        {"slug": "cropped-cardigan", "promoted": False,
         "reason": "Class C requires physical testing that does not exist yet"})
    assert not RS.is_research_only_refusal(
        {"slug": "x", "promoted": False, "reason": "owner veto"})


# ---- D3: a promoted bundle gets its cir.draft ----------------------------------------------

def test_a_bundle_is_not_engine_demand():
    seed = next(s for s in POOL if s.slug == "nordic-forest-bundle")
    v = D.engine_verdict(seed.slug, score_concept(seed, TODAY).to_dict())
    assert v["certified"] is True and v["family"] == "bundle", v


def test_a_promoted_bundle_offer_is_admitted_to_its_draft():
    db = _db()
    ctx = _ctx(db)
    seed = next(s for s in POOL if s.slug == "nordic-forest-bundle")
    out = supply.offer(ctx, slug=seed.slug, payload=score_concept(seed, TODAY).to_dict(),
                       key=f"draft:{seed.slug}", source="radar.score", family=seed.family,
                       demand=0.6)
    assert out["admitted"] is True, out
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.idempotency_key == f"draft:{seed.slug}"))
    assert job is not None and job.job_type == "cir.draft"


def test_a_non_bundle_without_an_engine_is_still_engine_demand():
    v = D.engine_verdict("fixture-wreath", {"title": "Holiday Thing", "category":
                                            "seasonal_decor"})
    assert v["known"] and not v["certified"]


# ---- D4: a cleared certification halt is not shown as an open incident -------------------

def _launch0_cir(slug="hexagon-coaster-set"):
    for c in RR.launch0_releases():
        if c.slug == slug:
            return c
    raise KeyError(slug)


def _halted_row(db):
    cir = _launch0_cir()
    tracker = IncidentTracker(db)
    for i in range(3):                       # Gate E: a real customer-defect P1
        tracker.report(DefectReport(cir.slug, "1.0.0", "coaster", 4, f"c{i}", "row 4"))
    q = JobQueue(db)
    for jt, key in (("cir.draft", "d"), ("cir.compile", "c")):
        j = q.enqueue("crochet_engineer", jt, {"slug": cir.slug, "version": cir.version},
                      idempotency_key=key)
        with db.session() as s:
            row = s.get(Job, j.id)
            row.status = JobStatus.DONE
            row.outputs = {"artifact": f"{cir.slug}@{cir.version}", "compiled": True}
    job = q.enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                    idempotency_key="certify-first")
    out = pipeline.handle_certify(_ctx(db, job))
    with db.session() as s:
        row = s.get(Job, job.id)
        row.status, row.outputs = JobStatus.DONE, out
    assert out.get("halted_by_incident") is True
    return cir, tracker


def _item(db, cir):
    INV.reset_snapshot()
    inv = INV.derive(db)
    return next(i for i in inv["items"] if i["slug"] == cir.slug
                and i["version"] == cir.version)


def test_an_open_incident_still_holds_certification():
    db = _db()
    cir, _ = _halted_row(db)
    it = _item(db, cir)
    assert it["why"].startswith("certification halted by an open incident"), it["why"]
    assert any("halted" in h.get("why", "") for h in it["holds"])


def test_a_closed_incident_lifts_the_hold_and_the_retry_redrives_it():
    db = _db()
    cir, tracker = _halted_row(db)
    with db.session() as s:
        ids = [i.id for i in s.scalars(select(Incident).where(Incident.resolved.is_(False)))]
    for i in ids:
        tracker.resolve(i, "fixture: resolved")
    it = _item(db, cir)
    assert "halted by an open incident" not in it["why"], it["why"]
    assert it["why"].startswith("certification halt cleared"), it["why"]
    assert not any("halted" in h.get("why", "") for h in it["holds"])
    holder = _ctx(db, JobQueue(db).enqueue("listing", "chain.rebuild", {},
                                           idempotency_key="rb"))
    r = RR.retry_halted(holder)
    assert r["retried"] == [f"{cir.slug}@{cir.version}"]


def test_an_unreadable_incident_table_never_lifts_the_hold():
    db = _db()
    cir, _ = _halted_row(db)
    real = IncidentTracker.certification_halts
    try:
        def boom(self, slug):
            raise RuntimeError("unreadable")
        IncidentTracker.certification_halts = boom
        it = _item(db, cir)
    finally:
        IncidentTracker.certification_halts = real
    assert it["why"].startswith("certification halted by an open incident"), it["why"]


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except Exception as exc:  # noqa: BLE001
                import traceback

                fails += 1
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    print(f"{'FAILED' if fails else 'PASSED'}: {fails} failing")
    sys.exit(1 if fails else 0)
