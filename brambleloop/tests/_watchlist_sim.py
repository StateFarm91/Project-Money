"""Shared fixture for the eng/r5-research-2 tests: real watchlist scans and comparisons on
simulated days.

* `Reader` answers like the official API (recorded shapes, fixture listings) for every
  watchlist shop; `catalogues` is mutable so a later scan can withdraw listings.
* `clock(when)` sets the time the watchlist module reads (`watchlist._now`) so the REAL job
  handlers (`intel.watchlist_scan`, `intel.watchlist_compare`), which pass no time, run on a
  simulated day. Nothing in the comparison, research or proposal code is patched.

No competitor content: titles here are fixture strings, and the tests assert none of them
(nor any shop name) reaches a research task or a proposal.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

for _k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET", "ETSY_KEYSTRING", "ANTHROPIC_API_KEY"):
    os.environ.pop(_k, None)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CoverageGap, Job, JobStatus, Phase  # noqa: E402
from brambleloop.intel import benchmarks, research, watchlist  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

POD = "kitchen_bath"
TODAY = date.today()
SHOP_IDS = {m.shop_name: 100 + i for i, m in enumerate(watchlist.WATCHLIST)}


def listing(lid: int, title: str) -> dict:
    return {"listing_id": lid, "title": title,
            "price": {"amount": 700, "divisor": 100, "currency_code": "CAD"},
            "tags": ["crochet pattern"], "materials": ["yarn"], "state": "active",
            "last_modified_timestamp": 1000, "num_favorers": 10, "taxonomy_id": 66,
            "is_digital": True, "is_sale": False,
            "description": "Crochet PATTERN, PDF instant download. US terms.",
            "url": f"https://fixture.invalid/listing/{lid}"}


def dishcloths(base: int, n: int = 3) -> list[dict]:
    return [listing(base + i, f"Dish Cloth Crochet Pattern {i}") for i in range(n)]


def default_catalogues() -> dict[str, list[dict]]:
    """Two watchlist shops each list 3 dish cloths (kitchen_bath); the others one listing in
    a pod nobody else occupies, so only kitchen_bath can be corroborated."""
    cats = {m.shop_name: [] for m in watchlist.WATCHLIST}
    cats["MadelineMaeCo"] = dishcloths(5000)
    cats["ZKBDESIGNER"] = dishcloths(6000)
    return cats


class Reader:
    def __init__(self, catalogues: dict[str, list[dict]]):
        self.catalogues = catalogues

    def resolve_shop(self, name):
        return {"shop_id": SHOP_IDS[name], "shop_name": name, "transaction_sold_count": 100,
                "review_count": 10, "review_average": 4.8, "num_favorers": 50,
                "listing_active_count": len(self.catalogues.get(name) or [])}

    def catalogue(self, shop_id, **kw):
        name = next(n for n, i in SHOP_IDS.items() if i == shop_id)
        return list(self.catalogues.get(name) or [])

    def images(self, ref):
        return [{"rank": 1, "url_fullxfull": f"https://fixture.invalid/{ref}.jpg"}]

    def videos(self, ref):
        return []

    def reviews(self, shop_id, *, limit=100):
        return []


def make_db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='r5r2-')}/r.db")
    db.create_all()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    return db


def at(days_ago: int, hour: int = 9) -> datetime:
    return datetime.combine(TODAY - timedelta(days=days_ago), time(hour), tzinfo=timezone.utc)


@contextmanager
def clock(when: datetime):
    real = watchlist._now
    watchlist._now = lambda now=None: now or when
    try:
        yield
    finally:
        watchlist._now = real


@contextmanager
def reading_with(reader: Reader):
    watchlist.reader_factory = lambda: reader
    try:
        yield
    finally:
        watchlist.reader_factory = None


def run_job(db, job_type: str, inputs: dict | None = None, *, agent: str = "market_radar"):
    """Enqueue one job and run exactly it through the real worker; its outputs."""
    job = JobQueue(db).enqueue(agent, job_type, dict(inputs or {}), priority=0,
                               idempotency_key=f"t:{job_type}:{os.urandom(6).hex()}")
    Worker(db, "r5r2", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (job_type, row.status, row.last_error)
        return dict(row.outputs or {})


def scan(db, reader: Reader, when: datetime) -> dict:
    with clock(when), reading_with(reader):
        return run_job(db, "intel.watchlist_scan", {"force": True})


def compare(db, when: datetime) -> dict:
    with clock(when):
        return run_job(db, "intel.watchlist_compare")


def intake(db, when: datetime) -> dict:
    return run_job(db, "radar.concept_intake", {"as_of": when.date().isoformat()})


def gap(db, pod: str = POD):
    with db.session() as s:
        g = s.scalar(select(CoverageGap).where(CoverageGap.benchmark_key == "watchlist",
                                               CoverageGap.pod == pod))
        return None if g is None else (g.id, dict(g.evidence or {}), g.state)


def tasks(db) -> list:
    research._ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(research.ResearchTask).order_by(research.ResearchTask.id)))
        s.expunge_all()
        return rows


def concepts(db) -> list:
    from brambleloop.radar import intake as I

    I._ensure(db)
    with db.session() as s:
        rows = list(s.scalars(select(I.RadarConcept).order_by(I.RadarConcept.id)))
        s.expunge_all()
        return rows
