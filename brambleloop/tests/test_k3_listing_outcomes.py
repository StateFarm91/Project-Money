"""Wave-3 K3: listing outcomes are written at runtime and read by the decision paths.

F-258 (conversion evidence loop), F-259 (neutral new-listing prior), F-260 (listing
experiment discipline), F-261 (underperformer remediation), F-282 (no zero-sales panic) and
F-297 (measurement before optimisation). Before K3 nothing at runtime wrote
`ListingOutcome`; every reader below was correct only because an empty table is UNMEASURED.

Every listing, export, Etsy listing and order here is a TEST FIXTURE in a throwaway database
or on `tests/fake_etsy.py`'s loopback server. Phase is shadow; no request leaves the machine.

Run: cd brambleloop && $PY tests/test_k3_listing_outcomes.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

for _k in list(os.environ):
    if _k.startswith("ETSY"):
        os.environ.pop(_k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, Listing, ListingOutcome, OperatingReading, PatternVersion, Phase,
    Product, RegisteredExperiment,
)
from brambleloop.commerce import listing_outcomes as LO  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops, growth_ops, pipeline  # noqa: E402,F401
from brambleloop.runtime import listing_outcomes as RLO  # noqa: E402
from brambleloop.runtime.worker import JobContext, Worker, handlers  # noqa: E402

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
P_START = (TODAY - timedelta(days=28)).isoformat()
P_END = (TODAY - timedelta(days=1)).isoformat()


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='k3_')}/k3.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _listing(db, slug: str, *, etsy_id: str = "", days_live: int = 30,
             state: str = "published") -> None:
    with db.session() as s:
        p = Product(slug=slug, title=slug, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0",
                             cir_json={"components": [{"name": "body"}]},
                             release_hash=hashlib.sha256(slug.encode()).hexdigest(),
                             certified=True, certificate={"stages_run": ["compile"]}))
        s.add(Listing(product_slug=slug, version="1.0.0", title=f"{slug} crochet pattern",
                      description="d", tags=["crochet pattern"], price_cad=9.0, state=state,
                      etsy_listing_id=etsy_id,
                      created_at=NOW - timedelta(days=days_live)))


def _work(db, agent: str, job_type: str, inputs: dict | None = None) -> Job:
    job = JobQueue(db).enqueue(agent, job_type, inputs or {},
                               idempotency_key=f"t:{job_type}:{time.time_ns()}")
    assert Worker(db, "t", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _run(db, job_type: str, inputs: dict | None = None, agent: str = "orchestrator") -> dict:
    queue = JobQueue(db)
    job = queue.enqueue(agent, job_type, inputs or {},
                        idempotency_key=f"r:{job_type}:{time.time_ns()}")
    ctx = JobContext(job=job, db=db, queue=queue, registry=Registry(db), phase=Phase.SHADOW)
    return handlers.get(job_type)(ctx)


def _refused(fn, needle: str):
    try:
        fn()
    except LO.OutcomeRefused as e:
        assert needle in str(e), (needle, str(e))
        return
    raise AssertionError(f"expected a refusal mentioning {needle!r}")


def _outcomes(db) -> list[ListingOutcome]:
    with db.session() as s:
        rows = list(s.scalars(select(ListingOutcome).order_by(ListingOutcome.product_slug)))
        for r in rows:
            s.expunge(r)
        return rows


# ---- the intake reads strictly (F-258) ---------------------------------------------------

def test_the_export_is_read_strictly_and_names_only_our_listings():
    db = _db()
    _listing(db, "coaster-a", etsy_id="7001")
    ok = "listing id,impressions,visits,favourites,orders\n7001,900,30,4,1\n"
    assert LO.parse_export(ok)[0]["visits"] == 30
    _refused(lambda: LO.parse_export("listing id,views,visits\n7001,10,5\n"), "page views")
    _refused(lambda: LO.parse_export("listing id,impressions,visits\n7001,,5\n"),
             "blank is not zero")
    _refused(lambda: LO.parse_export("listing id,impressions,visits\n7001,10,50\n"),
             "cannot be visited more often")
    _refused(lambda: LO.parse_export("listing id,impressions,visits,orders\n7001,100,5,9\n"),
             "orders from")
    _refused(lambda: LO.parse_export("listing id,impressions,visits\n7001,10,5\n7001,10,5\n"),
             "listed twice")
    _refused(lambda: LO.parse_export("listing id,impressions,visits,favourites\n7001,10,5,\n"),
             "blank is not zero")
    _refused(lambda: LO.submit_export(db, "listing id,impressions,visits\n9999,10,5\n",
                                      period_start=P_START, period_end=P_END),
             "not one of this shop's listings")
    _refused(lambda: LO.submit_export(db, ok, period_start=P_END, period_end=P_START),
             "end before it starts")
    _refused(lambda: LO.submit_export(db, ok, period_start=P_START,
                                      period_end=(TODAY + timedelta(days=3)).isoformat()),
             "not finished")
    # An absent optional column is UNKNOWN (None), never zero.
    row = LO.parse_export("slug,impressions,visits\ncoaster-a,10,5\n")[0]
    assert row["favourites"] is None and row["carts"] is None and row["orders"] is None
    # Nothing refused reached the table or the inbox.
    assert not _outcomes(db)
    print("OK test_the_export_is_read_strictly_and_names_only_our_listings")


def test_the_scheduled_daily_job_records_an_export_and_reads_it_back():
    db = _db()
    _listing(db, "coaster-a", etsy_id="7001")
    _listing(db, "throw-b")
    csv_text = ("listing id,impressions,visits,favourites,added to cart,orders\n"
                "7001,900,30,4,2,1\nthrow-b,1500,45,6,3,0\n")
    q = LO.submit_export(db, csv_text, period_start=P_START, period_end=P_END)
    assert q["queued"] and q["rows"] == 2 and q["listings"] == ["coaster-a", "throw-b"]
    again = LO.submit_export(db, csv_text, period_start=P_START, period_end=P_END)
    assert again["queued"] is False and again["status"] == "pending"
    # Queued is not recorded: the table is still empty until the producer runs.
    assert not _outcomes(db)

    # The runtime path: the daily commerce.readings job (scheduled, agent cfo) runs the
    # listing-outcome producer first.
    done = _work(db, "cfo", "commerce.readings")
    assert done.status == JobStatus.DONE, done.last_error
    produced = done.outputs["listing_outcomes"]
    assert produced["recorded_listings"] == ["coaster-a", "throw-b"], produced
    assert produced["api"] == "UNKNOWN"          # no Etsy credential: unread, never zero
    rows = {r.product_slug: r for r in _outcomes(db)}
    assert set(rows) == {"coaster-a", "throw-b"}
    a = rows["coaster-a"]
    assert (a.impressions, a.visits, a.favourites, a.orders) == (900, 30, 4, 1)
    assert a.source.startswith(LO.EXPORT_SOURCE) and a.detail["carts"] == 2
    assert a.period_start == P_START and a.period_end == P_END
    with db.session() as s:
        inbox = s.scalar(select(OperatingReading).where(OperatingReading.kind == LO.EXPORT_KIND))
        assert inbox.payload["status"] == "recorded"
        assert inbox.payload["round_trip"]["ok"] is True
        assert inbox.payload["round_trip"]["checked"] == 2
        assert s.scalar(select(AuditLog).where(AuditLog.action == RLO.ACTION)) is not None
    reading = LO.latest(db)
    assert reading["measurement"]["organic"] is True and reading["measurement"]["paid"] is False
    stages = {r["slug"]: r for r in reading["listings"]}
    assert stages["throw-b"]["carts"] == 3 and stages["throw-b"]["stage"]
    # A second run records nothing twice (the export is no longer pending).
    second = _run(db, RLO.ACTION, agent="cfo")
    assert second["exports_processed"] == 0 and len(_outcomes(db)) == 2
    print("OK test_the_scheduled_daily_job_records_an_export_and_reads_it_back")


def test_the_etsy_api_half_is_read_only_differenced_and_never_invents_impressions():
    from brambleloop.integrations.etsy import Credentials, EtsyClient
    from brambleloop.integrations.http import UrllibTransport
    from tests.fake_etsy import FakeEtsy

    db = _db()
    _listing(db, "coaster-a", etsy_id="7001")
    # No credential: UNKNOWN, and no snapshot stored.
    got = LO.api_snapshot(db, None)
    assert got["status"] == "UNKNOWN"
    with db.session() as s:
        assert s.scalar(select(OperatingReading).where(
            OperatingReading.kind == LO.SNAPSHOT_KIND)) is None

    with FakeEtsy() as fake:
        fake.listings["7001"] = {"listing_id": 7001, "state": "active", "views": 100,
                                 "num_favorers": 5, "title": "x"}
        fake.listings["7002"] = {"listing_id": 7002, "state": "draft", "views": 3}
        client = EtsyClient(UrllibTransport(), phase="shadow", base=fake.base,
                            credentials=Credentials(api_key=fake.keystring,
                                                    shared_secret=fake.shared_secret,
                                                    access_token="111.live-token",
                                                    shop_id=fake.shop_id))
        day1 = LO.produce(db, client=client, now=NOW - timedelta(days=1))
        assert day1["api"]["status"] == "OK" and day1["api"]["observed"] == 1
        first = day1["api"]["periods"]["7001"]
        assert first["visits"] == "UNKNOWN" and first["impressions"] == "UNKNOWN"
        fake.listings["7001"].update(views=160, num_favorers=4)
        day2 = LO.produce(db, client=client, now=NOW)
        ops = {r["operation"] for r in fake.requests}
    period = day2["api"]["periods"]["7001"]
    assert period["slug"] == "coaster-a" and period["visits"] == 60
    assert period["favourites"] == "UNKNOWN" and "fell" in period["favourites_why"]
    assert period["impressions"] == "UNKNOWN" and period["carts"] == "UNKNOWN"
    # Read-only: the only Etsy operation was the listing read.
    assert ops == {"getListingsByShop"}, ops
    # A visits count with no impressions is never written as a ListingOutcome row.
    assert not _outcomes(db)
    entry = next(r for r in day2["listings"] if r["slug"] == "coaster-a")
    assert entry["stage"] == "UNMEASURED" and entry["api_period"]["visits"] == 60
    print("OK test_the_etsy_api_half_is_read_only_differenced_and_never_invents_impressions")


# ---- the portfolio review diagnoses from produced rows (F-258, F-259, F-261, F-282) -------

def test_the_weekly_review_diagnoses_each_stage_from_the_produced_outcomes():
    db = _db()
    for slug in ("new-a", "quiet-b", "unseen-c", "unloved-d", "hesitant-e"):
        _listing(db, slug)
    # Before any outcome: every listing is NO_EVIDENCE, never failed (F-259).
    _work(db, "orchestrator", "portfolio.review")
    with db.session() as s:
        before = s.scalar(select(AuditLog).where(AuditLog.action == "portfolio.reviewed")
                          .order_by(AuditLog.id.desc())).detail
    labels = {c["slug"]: c["label"] for c in before["classifications_detail"]}
    assert labels and all(labels[s] == "NO_EVIDENCE" for s in
                          ("new-a", "quiet-b", "unseen-c", "unloved-d", "hesitant-e")), labels

    LO.submit_export(db, (
        "slug,impressions,visits,favourites,orders\n"
        "quiet-b,120,3,0,0\n"          # a short, quiet zero-sales window: exposure first
        "unseen-c,5000,20,1,0\n"       # shown and not chosen: hero/title
        "unloved-d,4000,120,2,0\n"     # clicked, not saved, not bought: appeal
        "hesitant-e,4000,120,20,0\n"   # clicked and saved, not bought: value/trust/price
    ), period_start=P_START, period_end=P_END)
    assert _work(db, "cfo", "commerce.readings").status == JobStatus.DONE
    _work(db, "orchestrator", "portfolio.review")
    with db.session() as s:
        after = s.scalar(select(AuditLog).where(AuditLog.action == "portfolio.reviewed")
                         .order_by(AuditLog.id.desc())).detail
    got = {c["slug"]: c for c in after["classifications_detail"]}
    assert after["exposure_read"]["listing_outcomes"] == 4
    assert got["new-a"]["label"] == "NO_EVIDENCE"                       # F-259
    assert got["quiet-b"]["label"] == "NO_EVIDENCE"                     # F-282 (no panic)
    assert got["unseen-c"]["label"] == "SEO_PROBLEM"                    # F-261 relevance
    # F-282 / F-261: adequate exposure with no conversion is a diagnosed appeal problem, not
    # "new shop" -- and the offer guard (#13) withholds the discard until offers are tried.
    d = got["unloved-d"]
    assert (d["label"] == "APPEAL_PROBLEM"
            or d["evidence"].get("discard_verdict_withheld") == "APPEAL_PROBLEM"), d
    assert got["hesitant-e"]["label"] == "CONVERSION_PROBLEM"           # F-261 value/trust
    # The producer's own reading names the same stages (one diagnosis, not two).
    stages = {r["slug"]: r["stage"] for r in LO.latest(db)["listings"]}
    assert stages["unseen-c"] == "SEO_PROBLEM" and stages["new-a"] == "UNMEASURED"
    assert stages["hesitant-e"] == "CONVERSION_PROBLEM"
    print("OK test_the_weekly_review_diagnoses_each_stage_from_the_produced_outcomes")


# ---- experiments refuse to conclude without exposure (F-260) -----------------------------

def test_a_listing_experiment_with_too_little_exposure_concludes_nothing():
    from brambleloop.commerce.listing_tests import MIN_EXPOSURE
    from brambleloop.growth.experiments import register_launch

    db = _db()
    _listing(db, "hexie-coaster-set", etsy_id="7101")
    register_launch(db, product="hexie-coaster-set", price_cad=18.0, today=TODAY)
    with db.session() as s:
        for row in s.scalars(select(RegisteredExperiment)):
            row.created_at = NOW - timedelta(days=40)
    start = (TODAY - timedelta(days=30)).isoformat()
    LO.submit_export(db, f"listing id,impressions,visits\n7101,{MIN_EXPOSURE - 1},4\n",
                     period_start=start, period_end=P_END)
    _run(db, RLO.ACTION, agent="cfo")
    out = _run(db, "growth.conclude", agent="experiment_steward")
    assert "hexie-coaster-set:thumbnail" not in out["concluded"]
    from brambleloop.growth.experiments import conclude_all

    first = {r["key"]: r for r in conclude_all(db)["results"]}
    thumb_r = first["hexie-coaster-set:thumbnail"]
    assert thumb_r["outcome"] == "not_tested" and "was not tested" in thumb_r["why"], thumb_r
    assert thumb_r["discipline"]["exposure"] == MIN_EXPOSURE - 1
    with db.session() as s:
        thumb = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "hexie-coaster-set:thumbnail"))
        assert thumb.state == "registered" and thumb.observed is None
        assert "last_verdict" not in (thumb.detail or {})

    # The next period's export brings exposure over the floor: now it may conclude.
    LO.submit_export(db, "listing id,impressions,visits\n7101,1200,30\n",
                     period_start=(TODAY - timedelta(days=29)).isoformat(),
                     period_end=(TODAY - timedelta(days=2)).isoformat())
    _run(db, RLO.ACTION, agent="cfo")
    res = {r["key"]: r for r in conclude_all(db)["results"]}
    assert res.get("hexie-coaster-set:thumbnail", {}).get("outcome") != "not_tested", res
    with db.session() as s:
        thumb = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "hexie-coaster-set:thumbnail"))
        verdict = (thumb.detail or {}).get("last_verdict") or {}
    assert verdict.get("discipline", {}).get("exposure", 0) >= MIN_EXPOSURE, verdict
    print("OK test_a_listing_experiment_with_too_little_exposure_concludes_nothing")


# ---- measurement before optimisation (F-297) ---------------------------------------------

def test_optimisers_wait_until_measurement_is_recorded_and_read_back():
    db = _db()
    _listing(db, "coaster-a", etsy_id="7001")
    # A hand-inserted row proves nothing about whether measurement works.
    with db.session() as s:
        s.add(ListingOutcome(product_slug="coaster-a", period_start="2026-01-01",
                             period_end="2026-01-07", impressions=900, visits=20,
                             source="fixture:hand"))
    status = LO.measurement_status(db)
    assert status["organic"] is False and status["paid"] is False
    plan = growth_ops.ads_plan(db, today=TODAY)
    row = next(p for p in plan["products"] if p["slug"] == "coaster-a")
    assert any(b.startswith("measurement before optimisation (#297)")
               for b in row["blocked_by"]), row["blocked_by"]
    steer = growth_ops.steer(db, today=TODAY)
    assert steer["measurement"]["organic"] is False

    # An organic export recorded through the intake and read back: organic proven, paid not.
    LO.submit_export(db, "listing id,impressions,visits,traffic source\n7001,900,30,etsy_search\n",
                     period_start=P_START, period_end=P_END)
    _run(db, RLO.ACTION, agent="cfo")
    status = LO.measurement_status(db)
    assert status["organic"] is True and status["paid"] is False
    row = next(p for p in growth_ops.ads_plan(db, today=TODAY)["products"]
               if p["slug"] == "coaster-a")
    blocked = [b for b in row["blocked_by"] if "#297" in b]
    assert blocked and "paid" in blocked[0]
    assert growth_ops.steer(db, today=TODAY)["measurement"]["organic"] is True

    # A paid period recorded the same way proves the paid half.
    LO.submit_export(db, "listing id,impressions,visits,traffic source\n7001,300,9,etsy_ads\n",
                     period_start=(TODAY - timedelta(days=60)).isoformat(),
                     period_end=(TODAY - timedelta(days=31)).isoformat())
    _run(db, RLO.ACTION, agent="cfo")
    assert LO.measurement_status(db)["paid"] is True
    row = next(p for p in growth_ops.ads_plan(db, today=TODAY)["products"]
               if p["slug"] == "coaster-a")
    assert not [b for b in row["blocked_by"] if "#297" in b], row["blocked_by"]
    # Organic-first (#242) reads only the organic period; the paid one is excluded.
    organic = growth_ops.organic_period(db, "coaster-a")
    assert organic is not None and organic.visits == 30 + 20
    print("OK test_optimisers_wait_until_measurement_is_recorded_and_read_back")


def test_the_producer_is_registered_and_reached_from_a_scheduled_job():
    from brambleloop.runtime import commerce_readings
    from brambleloop.runtime.worker import CADENCES

    assert handlers.get(RLO.ACTION) is not None
    scheduled = {c[2] for c in CADENCES}
    assert "commerce.readings" in scheduled
    assert commerce_readings._listing_outcomes is RLO
    print("OK test_the_producer_is_registered_and_reached_from_a_scheduled_job")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert tests
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            import traceback

            failed += 1
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failed else 0)
