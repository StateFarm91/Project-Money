"""ENG-LEARN slices 3-4: suspended learners wired to real input, proof of improvement, commerce.

The tests check that:
- **The five suspended jobs.** Each was parked by the thrash breaker's backoff (identical
  output states). Each now has a real upstream input that lifts the backoff when it changes,
  and a work count that sees its own work. None is simply unsuspended.
- **Upstream progress is judged by declared work.** A bare `ran: true` with nothing measured
  is not progress.
- **Readback and Mission Control** show UNKNOWN on an empty company, and MEASURED trends only
  when the sample supports them.
- **Commerce lessons** come only from real-provenance rows. A fixture row is never learned from.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus  # noqa: E402
from brambleloop.learning import progress, stats  # noqa: E402
from brambleloop.swarm import orchestrate as O  # noqa: E402

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
SUSPENDED = ("creative.image_benchmark", "creative.outcome_learning",
             "creative.reference_reading", "visual.rnd.cycle", "improve.monitor")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def test_every_suspended_learner_has_a_real_upstream_input():
    from brambleloop.runtime import pipeline  # noqa: F401  (registers handlers)
    from brambleloop.runtime.worker import CADENCES, handlers

    cadenced = {c[2] for c in CADENCES}
    assert SUSPENDED
    for jt in SUSPENDED + ("learning.loops",):
        ups = O.UPSTREAM_INPUTS.get(jt)
        assert ups, f"{jt} has no upstream input: its backoff can never lift on new evidence"
        for u in ups:
            assert u in handlers._handlers or u in cadenced, (jt, u)


def test_made_progress_reads_declared_work_not_a_bare_ran():
    assert O.made_progress({"ran": True, "measured": 0}, "improve.measure") is False
    assert O.made_progress({"ran": True, "measured": 3}, "improve.measure") is True
    assert O.made_progress({"ran": True}, None) is True          # undeclared: unchanged
    assert O.made_progress({"work_done": 0, "ran": True}, "improve.measure") is False
    assert O.made_progress({"exports_processed": 1}, "listing.outcomes") is True


def test_new_upstream_evidence_lifts_a_parked_learner():
    db = _db()
    since = NOW - timedelta(days=2)
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{O.THRASH_SIGNATURE_PREFIX}creative.outcome_learning",
                       summary="parked", at=since,
                       detail={"suspension": {"job_type": "creative.outcome_learning",
                                              "kind": O.BACKOFF, "since": since.isoformat(),
                                              "suspend_until": (NOW + timedelta(days=30)).isoformat(),
                                              "factor": 32}}))
    assert "creative.outcome_learning" in O.suspended_job_types(db, now=NOW)
    with db.session() as s:   # an upstream that ran and did nothing does NOT lift it
        s.add(Job(agent="cfo", job_type="listing.outcomes", inputs={},
                  outputs={"exports_processed": 0, "recorded_listings": 0},
                  status=JobStatus.DONE, finished_at=NOW - timedelta(hours=3),
                  idempotency_key="lo-1"))
    assert "creative.outcome_learning" in O.suspended_job_types(db, now=NOW)
    with db.session() as s:   # new real outcomes recorded: lifted
        s.add(Job(agent="cfo", job_type="listing.outcomes", inputs={},
                  outputs={"exports_processed": 1, "recorded_listings": 4},
                  status=JobStatus.DONE, finished_at=NOW - timedelta(hours=1),
                  idempotency_key="lo-2"))
    assert "creative.outcome_learning" not in O.suspended_job_types(db, now=NOW)


def test_learning_loops_is_free_and_registered():
    from brambleloop.runtime import pipeline
    from brambleloop.runtime.worker import CADENCES, handlers

    assert "learning.loops" in O.FREE_JOB_TYPES
    assert "learning.loops" in handlers._handlers
    assert any(c[2] == "learning.loops" for c in CADENCES)
    assert pipeline.WORK_KEYS["learning.loops"] == ("work_done",)
    # a standing count is not work for the promotion monitor
    assert "promoted" not in pipeline.WORK_KEYS["improve.monitor"]
    assert pipeline.did_no_work({"ran": True, "promoted": 4, "judged": 0},
                                "improve.monitor") is True


def test_visual_rnd_counts_hero_work():
    from brambleloop.autonomy.visual_rnd_job import summarise

    idle = summarise({"classes": {"blanket": {"hero": {"evaluated": 0, "promoted": False}}}})
    assert idle["work_done"] == 0
    busy = summarise({"classes": {"blanket": {"hero": {"evaluated": 3, "promoted": True},
                                              "hero_calibration": {"verdict": "overturned"}}}})
    assert busy["hero_evaluated"] == 3 and busy["hero_promoted"] == 1
    assert busy["work_done"] == 5


def test_progress_is_unknown_on_an_empty_company():
    db = _db()
    s = progress.summary(db, now=NOW)
    assert s["image"]["trend"]["status"] == stats.UNKNOWN
    assert all(w["status"] == stats.UNKNOWN for w in s["image"]["series"])
    assert s["pattern"]["trend"]["status"] == stats.UNKNOWN
    assert s["commerce"]["status"] == "UNMEASURED"
    rb = progress.readback(db, now=NOW)
    assert rb["image"]["first_pass_latest"] == stats.UNKNOWN
    assert rb["pattern"]["trend"] == stats.UNKNOWN
    assert rb["image"]["lessons_acted_on"] == 0
    from brambleloop.ops.production_evidence import evidence

    ev = evidence(db, now=NOW)
    assert ev["learning"]["readable"] is True
    assert ev["learning"]["image"]["trend"] == stats.UNKNOWN


def test_image_trend_measured_only_when_real():
    import test_eng_learn as T
    from brambleloop.learning import image_lessons as IL

    db = T._db()
    rng = random.Random(1)
    for i in range(60):    # ten weeks ago, 40% first-pass
        T._frame(db, i=i, prompt_version="x", accepted=rng.random() < 0.4,
                 at=NOW - timedelta(days=75, minutes=i))
    for i in range(60, 120):  # this fortnight, 85%
        T._frame(db, i=i, prompt_version="x", accepted=rng.random() < 0.85,
                 at=NOW - timedelta(days=2, minutes=i))
    IL.harvest(db, family_for=T.FAM)
    t = progress.image_trend(db, now=NOW)
    assert t["trend"]["status"] == "MEASURED" and t["trend"]["verdict"] == "improving", t
    # Retries are not first-pass frames: a pile of second attempts changes nothing.
    for i in range(120, 400):
        T._frame(db, i=i, prompt_version="x", accepted=False, attempt=2,
                 at=NOW - timedelta(days=1, minutes=i))
    IL.harvest(db, family_for=T.FAM)
    assert progress.image_trend(db, now=NOW)["trend"]["verdict"] == "improving"


def _sales(db, slug: str, visits: int, orders: int, *, real: bool = True):
    from brambleloop.core.models import Customer, ListingOutcome, Order

    prov = {"provenance": "real"} if real else {"provenance": "synthetic"}
    with db.session() as s:
        c = Customer(customer_ref=f"buyer-{slug}")
        s.add(c)
        s.flush()
        s.add(ListingOutcome(product_slug=slug, period_start="2027-01-01",
                             period_end="2027-01-31", impressions=visits * 10, visits=visits,
                             favourites=visits // 20, source="fixture", detail=prov))
        for k in range(orders):
            s.add(Order(customer_id=c.id, external_ref=f"{slug}-{k}", product_slug=slug,
                        revenue_cad=10.0, detail=prov))


def test_commerce_learns_only_from_real_rows():
    from brambleloop.learning import commerce_lessons as CL

    db = _db()
    _sales(db, "a-pillow", 5000, 200, real=False)
    _sales(db, "b-pillow", 5000, 10, real=False)
    out = CL.cycle(db, now=NOW)
    assert out["status"] == "UNMEASURED" and out["lessons"] == 0 and out["work_done"] == 0


def test_commerce_lesson_from_real_sales_reaches_radar():
    import test_eng_learn as T
    from brambleloop.learning import commerce_lessons as CL
    from brambleloop.learning import image_lessons as IL

    db = T._db()
    # Two listings, each with accepted frames from a different image arm.
    for i, (slug, pv) in enumerate((("a-pillow", "learn:7:2"), ("b-pillow", "learn:3:1"))):
        T._frame(db, i=i, prompt_version=pv, accepted=True)
        from brambleloop.visual.image_records import ImageCandidate

        with db.session() as s:
            s.get(ImageCandidate, i + 1).slug = slug
    IL.harvest(db, family_for=T.FAM)
    _sales(db, "a-pillow", 2000, 120)
    _sales(db, "b-pillow", 2000, 20)
    out = CL.cycle(db, now=NOW)
    assert out["status"] == "MEASURED" and out["lessons"] >= 1 and out["published"] >= 1, out
    from brambleloop.improve import bus

    inbox = bus.inbox(db, "market_radar", unacted_only=False)
    assert any("Real Etsy sales" in x["statement"] for x in inbox)
    assert progress.summary(db, now=NOW)["commerce"]["status"] == "MEASURED"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{'FAILED' if fails else 'PASSED'}: {fails} failing")
    sys.exit(1 if fails else 0)
