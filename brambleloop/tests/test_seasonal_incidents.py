"""Seasonal incidents: raised for what a product can still act on, closed when that stops.

Production on 2026-09-26 held nine seasonal incidents and none of them was actionable. Every
certified product was scheduled against every event, so a Valentine's garland was "at risk"
for Halloween; the at-risk sentinel raised only the soonest row, so one new row opened a day
and none ever closed; the collection calendar never marked a milestone done, so a company
created on 2026-09-17 had "missed" every research date of the year; and preparation streams
the daily cadences had plainly started were reported late because nothing looked.

Each test here drives the real `seasonal.sentinel` handler through a worker, twice where the
property is about the second run, and asserts both halves: the stale row closes with a
reason, and the genuinely late product is still raised.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, Job, JobStatus, PatternVersion, Product,
)
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402 - registers the handlers
from brambleloop.runtime.worker import Worker  # noqa: E402


def _db(*slugs: str, created: datetime | None = None) -> Database:
    from brambleloop.products.builder import CATALOGUE, build

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/seasonal.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        for slug in slugs:
            cir = build(CATALOGUE[slug])
            product = Product(slug=slug, title=cir.title, status="certified")
            if created is not None:
                product.created_at = created
            s.add(product)
            s.flush()
            s.add(PatternVersion(product_id=product.id, version=cir.version,
                                 cir_json=cir.to_dict(), release_hash="0" * 64,
                                 certified=True, certificate={"granted": True}))
    return db


_RUNS = {"n": 0}


def _sentinel(db, as_of: date) -> None:
    _RUNS["n"] += 1
    JobQueue(db).enqueue("orchestrator", "seasonal.sentinel", {"as_of": as_of.isoformat()},
                         idempotency_key=f"seasonal-incidents-{_RUNS['n']}")
    worker = Worker(db, "seasonal-incidents-worker")
    for _ in range(20):
        if not worker.run_once():
            break
    with db.session() as s:
        dead = list(s.scalars(select(Job).where(Job.status == JobStatus.DEAD)))
    assert not dead, [(j.job_type, (j.last_error or "")[:300]) for j in dead]


def _incidents(db, prefix: str) -> list[Incident]:
    with db.session() as s:
        rows = [r for r in s.scalars(select(Incident).order_by(Incident.id))
                if r.signature.startswith(prefix)]
        for r in rows:
            s.expunge(r)
        return rows


def _audit(db, action: str, artifact: str | None, at: datetime) -> None:
    with db.session() as s:
        s.add(AuditLog(actor="test", action=action, artifact=artifact, at=at, detail={}))


# ---- products are scheduled against their own occasion ---------------------


def test_a_product_is_scheduled_only_against_the_occasion_it_is_for():
    from brambleloop.seasonal.leadtime import EVERGREEN, catalogue_plans, occasion_for

    assert occasion_for("valentine-heart-garland") == "Valentine's"
    assert occasion_for("spooky-garland") == "Halloween"
    assert occasion_for("cloudline-baby-blanket") == EVERGREEN

    db = _db("valentine-heart-garland", "spooky-garland", "cloudline-baby-blanket")
    room = catalogue_plans(db, today=date(2026, 9, 26))
    pairs = {(r["slug"], r["event"]) for r in room["plans"]}
    assert pairs == {("valentine-heart-garland", "Valentine's"),
                     ("spooky-garland", "Halloween")}, pairs
    assert room["products_evergreen"] == ["cloudline-baby-blanket"]
    assert room["products_scheduled"] == 3


# ---- at risk: raised per row, restated, then closed with the recommendation --


def test_an_at_risk_row_is_restated_the_next_day_and_closes_as_missed_with_the_next_window():
    from brambleloop.seasonal.leadtime import catalogue_plans

    db = _db("winter-village-graphghan", "cloudline-baby-blanket")
    # The row production actually held: a product scheduled against an event it is not for.
    with db.session() as s:
        L.open_or_restate(s, signature="seasonal.at_risk:cloudline-baby-blanket:Halloween",
                          severity="P2", summary="stale", product_slug="cloudline-baby-blanket")

    plan = next(r for r in catalogue_plans(db, today=date(2026, 9, 1))["plans"]
                if r["slug"] == "winter-village-graphghan")
    latest = date.fromisoformat(plan["latest_effective_launch"])
    day = latest - timedelta(days=5)
    signature = f"seasonal.at_risk:winter-village-graphghan:Christmas:{latest.year}"

    _sentinel(db, day)
    rows = _incidents(db, "seasonal.at_risk:")
    stale = next(r for r in rows if r.signature.endswith(":Halloween"))
    assert stale.resolved is True
    assert "not merchandised for Halloween" in stale.detail["resolution"]
    live = [r for r in rows if r.signature == signature]
    assert len(live) == 1 and live[0].resolved is False, [r.signature for r in rows]

    # A day later: the same condition, the same row. Nothing new opens.
    _sentinel(db, day + timedelta(days=1))
    live = [r for r in _incidents(db, "seasonal.at_risk:") if r.signature == signature]
    assert len(live) == 1 and live[0].resolved is False
    assert live[0].report_count >= 2
    assert live[0].detail["last_seen"]

    # Past the latest effective launch: missed, so the row closes carrying #297's decision
    # and the next occurrence's dates, and no new at-risk row opens in its place.
    _sentinel(db, latest + timedelta(days=1))
    rows = [r for r in _incidents(db, "seasonal.at_risk:") if not r.resolved]
    assert rows == [], [r.signature for r in rows]
    closed = next(r for r in _incidents(db, "seasonal.at_risk:") if r.signature == signature)
    assert closed.detail["resolution"].startswith(f"missed for Christmas {latest.year}")
    assert "Recommendation:" in closed.detail["resolution"]
    assert f"Next window: Christmas {latest.year + 1}" in closed.detail["resolution"]


# ---- the collection calendar ------------------------------------------------


def test_a_genuinely_late_product_still_raises_the_calendar_and_evidence_closes_it():
    """A product created in June that targets Christmas and has no physical test and no
    assets by late September is behind, with a lane still open -- that is raised. Halloween,
    which nothing targets, is not. Recorded evidence for the missed milestones closes it."""
    created = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _db("winter-village-graphghan", created=created)
    _sentinel(db, date(2026, 9, 19))

    rows = _incidents(db, "seasonal.calendar_behind:")
    assert [r.signature for r in rows] == ["seasonal.calendar_behind:Christmas:2026"], \
        [r.signature for r in rows]
    missed = rows[0].detail["behind"][0]["missed"]
    assert "physical_test_deadline" in missed
    assert "creative_production_deadline" in missed
    # Due before the product existed: preceded, not missed.
    assert "research_start" not in missed and "concept_freeze" not in missed
    assert "collection milestones are already past" in rows[0].summary

    # Still behind the next day: restated, not duplicated.
    _sentinel(db, date(2026, 9, 20))
    rows = _incidents(db, "seasonal.calendar_behind:")
    assert len(rows) == 1 and rows[0].resolved is False and rows[0].report_count >= 2

    # The work happened and was recorded.
    for action in ("physical.recorded", "assets.built"):
        _audit(db, action, "winter-village-graphghan@1.0.0",
               datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc))
    _sentinel(db, date(2026, 9, 21))
    rows = _incidents(db, "seasonal.calendar_behind:")
    assert len(rows) == 1 and rows[0].resolved is True
    assert "on schedule" in rows[0].detail["resolution"]


def test_a_calendar_row_closes_when_the_occasion_passes_or_nothing_targets_it():
    created = datetime(2026, 6, 1, tzinfo=timezone.utc)
    db = _db("winter-village-graphghan", created=created)
    # The two rows production held, raised from dates alone and keyed without a year.
    with db.session() as s:
        for event in ("Halloween", "Thanksgiving (CA)"):
            L.open_or_restate(s, signature=f"seasonal.calendar_behind:{event}",
                              severity="P2", summary="stale")
    _sentinel(db, date(2026, 9, 19))
    rows = {r.signature: r for r in _incidents(db, "seasonal.calendar_behind:")}
    for event in ("Halloween", "Thanksgiving (CA)"):
        assert rows[f"seasonal.calendar_behind:{event}"].resolved is True
        assert "no certified product is merchandised" in \
            rows[f"seasonal.calendar_behind:{event}"].detail["resolution"]
    assert rows["seasonal.calendar_behind:Christmas:2026"].resolved is False

    _sentinel(db, date(2026, 12, 27))
    row = next(r for r in _incidents(db, "seasonal.calendar_behind:")
               if r.signature == "seasonal.calendar_behind:Christmas:2026")
    assert row.resolved is True
    assert "Christmas 2026 occurrence has passed" in row.detail["resolution"]
    assert not [r for r in _incidents(db, "seasonal.calendar_behind:") if not r.resolved]


# ---- preparation --------------------------------------------------------------


def _a_day_with_overdue_preparation() -> date:
    from brambleloop.seasonal.compression import programme

    for offset in range(0, 90, 3):
        day = date(2026, 10, 1) + timedelta(days=offset)
        plan = programme("Christmas", today=day)
        if any(r["overdue"] for r in plan["preparation"]):
            return day
    raise AssertionError("no day in the autumn has overdue Christmas preparation")


def test_preparation_is_overdue_only_without_evidence_and_closes_when_it_starts():
    day = _a_day_with_overdue_preparation()
    db = _db()
    with db.session() as s:
        L.open_or_restate(s, signature="seasonal.preparation_late:QUICK:search_language",
                          severity="P3", summary="the old shape, with no event in it")
    _sentinel(db, day)
    rows = [r for r in _incidents(db, "seasonal.preparation_late:") if not r.resolved]
    assert rows, "nothing has started and something is overdue; it must be raised"
    for row in rows:
        assert row.signature.startswith("seasonal.preparation_late:Christmas:2026:"), \
            row.signature
        assert "nothing shows it has" in row.summary
    old = next(r for r in _incidents(db, "seasonal.preparation_late:")
               if r.signature == "seasonal.preparation_late:QUICK:search_language")
    assert old.resolved is True and old.detail["resolution"]

    # The daily cadences run: every stream now has evidence of having started.
    at = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=6)
    for action in ("mjs.scanned", "assets.built", "listing.seo_drafted",
                   "collection.assembled"):
        _audit(db, action, None, at)
    _sentinel(db, day + timedelta(days=1))
    still = [r for r in _incidents(db, "seasonal.preparation_late:") if not r.resolved]
    assert still == [], [r.signature for r in still]
    for row in rows:
        closed = next(r for r in _incidents(db, "seasonal.preparation_late:")
                      if r.signature == row.signature)
        assert "has started" in closed.detail["resolution"], closed.detail["resolution"]


def test_preparation_with_evidence_is_never_raised():
    from brambleloop.seasonal.compression import PREPARATION_EVIDENCE, PREPARATION_LEADS

    assert set(PREPARATION_EVIDENCE) == set(PREPARATION_LEADS)
    day = _a_day_with_overdue_preparation()
    db = _db()
    at = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=2)
    for action in ("culture.sweep", "assets.listing_images_built", "listing.drafted",
                   "collection.assembled"):
        _audit(db, action, None, at)
    _sentinel(db, day)
    assert _incidents(db, "seasonal.preparation_late:") == []


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
