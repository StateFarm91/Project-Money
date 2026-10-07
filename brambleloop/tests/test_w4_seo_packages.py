"""W4-SEO: the Etsy search package -- produced by the real listing chain, persisted, consumed,
and updated from recorded Stats periods.

The real `gate.certify -> listing.draft -> assets.build -> pricing.position -> listing.seo`
handlers run on a temporary sqlite database (shadow worker, every outbound socket refused).
No Etsy taxonomy snapshot is stored in the main chain: that is the company's real state, so
the package must say EXTERNAL_GATED and name the gate, never assume a category. One chain runs
with the recorded-shape taxonomy FIXTURE (ids illustrative, not Etsy's) to prove the CERTIFIED
branch. The Stats export used for the update loop is FIXTURE data, submitted as
`submitted_by="fixture:test_w4_seo_packages"`; it measures nothing about any real listing.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="w4_seo_packages_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    EtsyTaxonomySnapshot, Job, JobStatus, Listing, Phase,
)
from brambleloop.products import vessels  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.seo import packages as P  # noqa: E402

SLUG = "hexagon-coaster-set"
CHAIN = ("gate.certify", "listing.draft", "assets.build", "pricing.position", "listing.seo")
_STATE: dict = {}


def _chain(name: str, *, fixture_taxonomy: bool) -> Database:
    if name in _STATE:
        return _STATE[name]
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    if fixture_taxonomy:
        snap = FX.snapshot()
        with db.session() as s:
            s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                       nodes=snap["nodes"], properties=snap["properties"]))
    JobQueue(db).enqueue("quality_director", "gate.certify",
                         {"cir": vessels.build_hexagon_coaster().to_dict()},
                         idempotency_key=f"cert-{name}", priority=0)
    worker = Worker(db, name, phase=Phase.SHADOW, job_types=list(CHAIN), lease_seconds=900)
    for _ in range(60):
        if not worker.run_once():
            break
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type.in_(CHAIN))))
        assert jobs, "the chain enqueued nothing"
        stuck = [(j.job_type, j.status.value, (j.last_error or "")[-300:]) for j in jobs
                 if j.status is not JobStatus.DONE]
        seo_job = next(j for j in jobs if j.job_type == "listing.seo")
        _STATE[name + ":seo_result"] = dict(seo_job.outputs or {})
    assert not stuck, stuck
    _STATE[name] = db
    return db


def _version(db) -> str:
    with db.session() as s:
        return s.scalar(select(Listing.version).where(Listing.product_slug == SLUG))


def test_listing_seo_persists_a_package_the_consumer_reads():
    db = _chain("real", fixture_taxonomy=False)
    version = _version(db)
    produced = _STATE["real:seo_result"].get("search_package") or {}
    assert produced.get("written") is True, produced
    pkg = P.current(db, SLUG, version)
    assert pkg is not None, "no CURRENT package bound to the drafted listing"
    tags = pkg["tags"]["values"]
    assert len(tags) == 13 and pkg["tags"]["rules"]["ok"], pkg["tags"]["rules"]
    assert pkg["title"]["text"] and pkg["title"]["chars"] <= pkg["title"]["limit"]["value"]
    assert pkg["primary_intent"] and pkg["primary_intent"]["phrase"]
    assert pkg["secondary_intents"], "no secondary intents"
    assert pkg["description"]["text"] and pkg["attributes"].get("file_type") == "PDF"
    assert pkg["pricing"]["status"] == "DECIDED" and pkg["pricing"]["price_cad"] > 0
    assert pkg["pricing"]["competitive_shelf"]["observed_on"], "shelf without a date"
    # Never assumed, never invented.
    assert pkg["category"]["taxonomy_id"] is None and pkg["category"]["gate"]
    assert pkg["readiness"]["state"] == P.EXTERNAL_GATED, pkg["readiness"]
    assert pkg["certificate"]["verdict"] == "REFUSED"
    assert set(pkg["certificate"]["failed"]) == {"category", "attributes"}
    assert pkg["evidence"]["volumes"] is None
    assert "demand" not in str(pkg["tags"]["evidence"])
    for t in pkg["tags"]["evidence"]:
        assert t["basis"] in ("measured", "observed", "modelled"), t
    assert pkg["learning"]["status"] == "UNKNOWN"
    assert all(v["value"] is None for v in pkg["learning"]["signals"].values())
    assert pkg["writes_to_etsy"] is False
    print("OK listing_seo_persists_a_package_the_consumer_reads")


def test_search_evidence_consumes_the_package():
    from brambleloop.commerce import search_evidence as se

    db = _chain("real", fixture_taxonomy=False)
    items = se.summary(db)["items"]
    assert items, "no search evidence rows"
    item = next(i for i in items if i["slug"] == SLUG)
    assert item["search_package"] and item["search_package"]["readiness"]["state"] \
        == P.EXTERNAL_GATED
    gate = se.supremacy_gate(db)
    assert not gate["cleared"]
    print("OK search_evidence_consumes_the_package")


def test_certified_branch_with_fixture_taxonomy_and_staleness():
    from brambleloop.commerce import search_evidence as se

    db = _chain("fixture", fixture_taxonomy=True)
    version = _version(db)
    pkg = P.current(db, SLUG, version)
    assert pkg is not None
    assert pkg["category"]["taxonomy_id"] is not None   # FIXTURE id, illustrative
    assert pkg["readiness"]["state"] == P.CERTIFIED, pkg["readiness"]
    assert pkg["certificate"]["verdict"] == "PASS"
    # Edit the listing after certification: the package no longer describes it.
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        row.title = row.title + " Edited"
    item = next(i for i in se.summary(db)["items"] if i["slug"] == SLUG)
    assert item["rungs"]["truthful_query_coverage"]["verdict"] != se.PASS
    print("OK certified_branch_with_fixture_taxonomy_and_staleness")


def test_stats_arrival_updates_the_package_through_the_seo_cycle():
    from brambleloop.commerce import listing_outcomes as lo
    from brambleloop.seo import jobs

    db = _chain("real", fixture_taxonomy=False)
    version = _version(db)
    first = jobs.run_cycle(db)
    assert first["packages"]["packages"] >= 1, first["packages"]
    again = jobs.run_cycle(db)
    assert not again["packages"]["written"], "an unchanged cycle rewrote a package"
    before = P.current(db, SLUG, version)
    # FIXTURE export (not a measurement of any real listing).
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)
    csv_text = ("listing id,impressions,visits,favourites,carts,orders\n"
                f"{SLUG},420,25,6,3,2\n")
    out = lo.submit_export(db, csv_text, period_start=start.isoformat(),
                           period_end=end.isoformat(),
                           submitted_by="fixture:test_w4_seo_packages")
    assert out["queued"], out
    lo.produce(db)
    cycle = jobs.run_cycle(db)
    assert f"{SLUG}@{version}" in cycle["packages"]["written"], cycle["packages"]
    after = P.current(db, SLUG, version)
    assert after["fingerprint"] != before["fingerprint"]
    sig = after["learning"]["signals"]
    assert after["learning"]["status"] == "MEASURED"
    assert (sig["impressions"]["value"], sig["visits"]["value"], sig["favourites"]["value"],
            sig["carts"]["value"], sig["orders"]["value"]) == (420, 25, 6, 3, 2)
    assert after["learning"]["diagnosis"]["stage"] == "ctr", after["learning"]["diagnosis"]
    hist = P.history(db, SLUG, version)
    assert len(hist) >= 2 and sum(h["state"] == "CURRENT" for h in hist) == 1, hist
    print("OK stats_arrival_updates_the_package_through_the_seo_cycle")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert tests
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {t.__name__}: {exc}")
    sys.exit(1 if failed else 0)
