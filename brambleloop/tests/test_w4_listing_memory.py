"""W4-AGENTS W2 (F-505): the listing-test memory has a runtime caller.

`growth.experiments.conclude_all` writes what a concluded listing experiment established to the
durable memory (under the listing-test discipline), and `persist` refuses to register a test
of an idea the memory holds as disproved in the same context -- stored as killed with the
disproof as its reason. An UNKNOWN context writes nothing and refuses nothing.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_listing_memory.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce import listing_tests as LT  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Listing, ListingMemory, ListingOutcome,  # noqa: E402
                                     RegisteredExperiment)
from brambleloop.growth import experiments as X  # noqa: E402
from brambleloop.radar.opportunity import POOL  # noqa: E402
from brambleloop.seasonal.daily import DEPARTMENT_OF  # noqa: E402

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='w4mem_')}/m.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _slugs(n=2):
    """Concept seeds with a pod and the same season, so they share a context."""
    ok = [c for c in POOL if DEPARTMENT_OF.get(c.category) and not c.is_bundle]
    first = ok[0]
    same = [c for c in ok if DEPARTMENT_OF.get(c.category) == DEPARTMENT_OF.get(first.category)
            and (c.season or "none") == (first.season or "none")]
    assert len(same) >= n, "need two seeds in one pod and season"
    return [c.slug for c in same[:n]]


def _listing(db, slug, price=8.0):
    with db.session() as s:
        s.add(Listing(product_slug=slug, version="1.0", title=slug, description="d",
                      tags=[], price_cad=price, state="draft",
                      created_at=NOW - timedelta(days=60)))


def _thumbnail(slug, key=None):
    e = next(e for e in X.launch_pack(product=slug, hypothesis="", price_cad=8.0, today=TODAY)
             if e.key.endswith(":thumbnail"))
    if key:
        e.key = key
    return e


def _outcome(db, slug, start, end, impressions, visits):
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, version="1.0", period_start=start.isoformat(),
                             period_end=end.isoformat(), impressions=impressions,
                             visits=visits, source="test export"))


def _disprove(db, slug):
    """Register the thumbnail test 40 days ago, with a 20-day baseline before it and a
    28-day exposed window after it whose CTR is below the failure threshold."""
    X.persist(db, _thumbnail(slug), product_slug=slug)
    reg = NOW - timedelta(days=40)
    with db.session() as s:
        for row in s.scalars(select(RegisteredExperiment).where(
                RegisteredExperiment.product_slug == slug)):
            row.created_at = reg
    _outcome(db, slug, (reg - timedelta(days=21)).date(), (reg - timedelta(days=2)).date(),
             900, 9)
    _outcome(db, slug, (reg + timedelta(days=1)).date(), (reg + timedelta(days=28)).date(),
             2000, 10)                                           # CTR 0.005 <= 0.008


def test_a_concluded_disproof_is_written_to_the_memory():
    db = _db()
    slug = _slugs(1)[0]
    _listing(db, slug)
    _disprove(db, slug)
    out = {r["key"]: r for r in X.conclude_all(db, today=TODAY)["results"]}
    r = out[f"{slug}:thumbnail"]
    assert r["concluded"] and r["verdict"] == "failure", r
    assert r["memory"]["written"] is True and r["memory"]["outcome"] == LT.DISPROVED, r
    with db.session() as s:
        mem = list(s.scalars(select(ListingMemory)))
        assert len(mem) == 1 and mem[0].idea == "thumbnail" and mem[0].exposure == 2000
        ctx, why = LT.context_for(db, slug)
        assert ctx is not None and mem[0].context == ctx.key(), why
        # idempotent: a re-run of the conclusion is not a second finding
        assert LT.remember_conclusion(db, f"{slug}:thumbnail", discipline=r.get(
            "discipline") or {"exposure": 2000, "window": {"days": 28}})["written"] is False


def test_a_disproved_idea_is_not_registered_again_in_the_same_context():
    db = _db()
    a, b = _slugs(2)
    _listing(db, a)
    _listing(db, b)
    _disprove(db, a)
    X.conclude_all(db, today=TODAY)
    assert LT.context_for(db, a)[0].key() == LT.context_for(db, b)[0].key()
    res = X.persist(db, _thumbnail(b), product_slug=b)
    assert res["state"] == X.KILLED and "listing memory (F-505)" in res["killed_reason"], res
    assert "disproved here" in res["killed_reason"]
    # a different context (another price band) is not refused
    db2 = _db()
    _listing(db2, a)
    _disprove(db2, a)
    X.conclude_all(db2, today=TODAY)
    _listing(db2, b, price=25.0)
    other = X.persist(db2, _thumbnail(b), product_slug=b)
    assert other["state"] == X.REGISTERED, other


def test_an_unknown_context_writes_nothing_and_refuses_nothing():
    db = _db()
    slug = _slugs(1)[0]
    # no drafted listing: the price band is UNKNOWN
    ctx, why = LT.context_for(db, slug)
    assert ctx is None and "UNKNOWN" in why
    assert LT.registration_refusal(db, _thumbnail(slug), slug) is None
    ctx, why = LT.context_for(db, "not-a-seeded-concept")
    assert ctx is None and "UNKNOWN" in why
    _disprove(db, slug)
    out = {r["key"]: r for r in X.conclude_all(db, today=TODAY)["results"]}
    r = out[f"{slug}:thumbnail"]
    assert r["concluded"] and r["memory"]["written"] is False and "UNKNOWN" in \
        r["memory"]["why"], r
    with db.session() as s:
        assert s.scalar(select(ListingMemory)) is None


def test_an_unexposed_or_baseline_less_test_is_never_remembered():
    db = _db()
    slug = _slugs(1)[0]
    _listing(db, slug)
    X.persist(db, _thumbnail(slug), product_slug=slug)
    reg = NOW - timedelta(days=40)
    with db.session() as s:
        for row in s.scalars(select(RegisteredExperiment)):
            row.created_at = reg
    # exposed window but NO pre-period: the conclusion may stand, the memory stays empty
    _outcome(db, slug, (reg + timedelta(days=1)).date(), (reg + timedelta(days=28)).date(),
             2000, 10)
    out = {r["key"]: r for r in X.conclude_all(db, today=TODAY)["results"]}
    r = out[f"{slug}:thumbnail"]
    assert r["concluded"] and r["memory"]["written"] is False, r
    assert X.pre_period(db, f"{slug}:thumbnail") == {"days": 0, "value": None}
    with db.session() as s:
        assert s.scalar(select(ListingMemory)) is None


def test_only_listing_variables_touch_the_memory():
    assert LT.experiment_variables("x:thumbnail") == ("thumbnail",)
    assert LT.experiment_variables("x:search") == ("title", "tags")
    assert LT.experiment_variables("x:pinterest_content") is None
    for v in LT.EXPERIMENT_VARIABLES.values():
        assert set(v) <= set(LT.VARIABLES)
    assert isinstance(TODAY, date)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
