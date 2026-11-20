"""W4-PLACEMATPRICE: an off-plan Launch-0 listing is re-priced through the release path.

Production holds `mosaic-placemat-pair@1.3.0` as a draft listing at CA$9.50, priced on the
generic band before CAP-1 put the placemat in Launch-0; its plan is CA$5.00. The listing is
current by chain version and release hash, so `chain.rebuild` used to call it "current" and
leave the price. It now sees the plan drift, enqueues `pricing.position` from the release's
own assets.build measurement (the same payload `_targeted_rebuild` re-prices from), and the
Launch-0 pricing path carries CA$5.00 on to `listing.seo`. Nothing is written to Etsy.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_placemat_reprice.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = tempfile.mkdtemp(prefix="reprice_art_")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, Listing, PatternVersion, Phase, Product,
)
from brambleloop.gates.certificate import GAUGE_STANDARD  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

SLUG = "mosaic-placemat-pair"
FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def _db(price: float, *, with_assets: bool = True):
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/r.db")
    db.create_all()
    Registry(db).seed_defaults()
    cir = l0.cir_for("placemat_pair")
    rh = "b2cd736f0f34" + "0" * 52
    with db.session() as s:
        p = Product(slug=SLUG, title=cir.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash=rh,
                             certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
        s.add(Listing(product_slug=SLUG, version=cir.version, title=cir.title,
                      description="d", tags=[], price_cad=price, state="draft",
                      chain_version=release.CHAIN_VERSION, release_hash=rh))
    if with_assets:
        job = JobQueue(db).enqueue("publishing", "assets.build",
                                   {"slug": SLUG, "version": cir.version},
                                   idempotency_key="seed-assets")
        with db.session() as s:
            row = s.get(Job, job.id)
            row.status = JobStatus.DONE
            row.outputs = {"slug": SLUG, "version": cir.version, "pdf_sha256": "p" * 64,
                           "release": rh}
    return db, cir, rh


def _run(db, job_type, inputs, key):
    job = JobQueue(db).enqueue("listing" if job_type == "chain.rebuild" else "pricing",
                               job_type, inputs, priority=0, idempotency_key=key)
    Worker(db, f"t-{key}", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _jobs(db, job_type):
    with db.session() as s:
        out = [(j.id, dict(j.inputs or {}), j.status) for j in s.scalars(
            select(Job).where(Job.job_type == job_type).order_by(Job.id))]
    return out


def test_an_off_plan_listing_is_repriced_through_pricing_position():
    db, cir, rh = _db(9.50)
    r = _run(db, "chain.rebuild", {}, "rb1")
    assert r.status == JobStatus.DONE, r.last_error
    assert r.outputs["repriced"] == [f"{SLUG}@{cir.version}"], r.outputs
    pricing = _jobs(db, "pricing.position")
    assert len(pricing) == 1, pricing
    jid, inputs, _st = pricing[0]
    assert inputs["slug"] == SLUG and inputs["release"] == rh and inputs["rebuild"], inputs
    # The Launch-0 pricing path prices it from its plan and carries that to listing.seo.
    Worker(db, "t-price", phase=Phase.SHADOW, job_types=["pricing.position"]).run_once()
    with db.session() as s:
        done = s.get(Job, jid)
        assert done.status == JobStatus.DONE, done.last_error
        assert done.outputs["price_cad"] == 5.00, done.outputs
    seo = _jobs(db, "listing.seo")
    assert seo and seo[-1][1]["price_cad"] == 5.00, seo
    # listing.seo is what writes the drafted row (`_persist_listing`). In this fixture the
    # assets payload is synthetic (no rendered frames), so listing.seo must REFUSE it rather
    # than draft a listing with unclassified images -- and the row keeps its old price until
    # a real assets.build measurement carries the re-price through.
    Worker(db, "t-seo", phase=Phase.SHADOW, job_types=["listing.seo"]).run_once()
    with db.session() as s:
        seo_job = s.get(Job, seo[-1][0])
        assert seo_job.status == JobStatus.DONE, seo_job.last_error
        assert seo_job.outputs.get("ok") is False and any(
            "POLICY_CLASSIFICATION" in b for b in seo_job.outputs["blocking"]), seo_job.outputs
        row = s.scalar(select(Listing).where(Listing.product_slug == SLUG,
                                             Listing.version == cir.version))
        assert row.price_cad == 9.50 and not row.etsy_listing_id
    with db.session() as s:
        req = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "chain.reprice_requested")))
        assert len(req) == 1 and req[0].detail["plan_cad"] == 5.00, [r.detail for r in req]


def test_the_reprice_is_enqueued_once_per_drift():
    db, cir, _rh = _db(9.50)
    _run(db, "chain.rebuild", {}, "rb-a")
    _run(db, "chain.rebuild", {"cadence": 2}, "rb-b")
    assert len(_jobs(db, "pricing.position")) == 1, _jobs(db, "pricing.position")


def test_a_listing_on_plan_is_current_and_nothing_is_repriced():
    db, cir, _rh = _db(5.00)
    r = _run(db, "chain.rebuild", {}, "rb-ok")
    assert r.outputs["repriced"] == [], r.outputs
    assert _jobs(db, "pricing.position") == []


def test_without_an_assets_measurement_it_is_refused_and_said():
    db, cir, _rh = _db(9.50, with_assets=False)
    r = _run(db, "chain.rebuild", {}, "rb-noassets")
    assert _jobs(db, "pricing.position") == []
    with db.session() as s:
        refused = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "chain.reprice_refused")))
    assert len(refused) == 1 and "assets.build" in refused[0].detail["refused"]
    assert r.outputs["repriced"] == [f"{SLUG}@{cir.version}"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
