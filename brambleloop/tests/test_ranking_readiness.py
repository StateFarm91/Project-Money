"""F-003: ranking readiness is five independent dimensions, each MEASURED or UNMEASURED.

No blended score exists, UNMEASURED is never PASS, the profile is called from launch.plan, and
/api/catalogue shows the search certificate's verdict where it used to show the planning
proxy `search_share`.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_ranking_readiness.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import inspect
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import ranking_readiness as rr  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Listing, ListingSearchProfile, ListingSetCertificateRecord, SupportCase,
)
from brambleloop.gates.platform_policy import DISCLOSURES  # noqa: E402
from brambleloop.publish.release_gates import search_fingerprint  # noqa: E402

SLUG, VERSION = "cloudline-baby-blanket", "1.0.0"


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def _listing(db, *, price=8.5, disclosed=True):
    desc = "A baby blanket pattern.\n\n" + (DISCLOSURES["digital_download"] if disclosed else "")
    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version=VERSION, title="Baby blanket crochet pattern",
                      description=desc, tags=["baby blanket"], price_cad=price))
    return desc


def _search_profile(db, desc, *, verdict="PASS", stale=False):
    checks = {k: {"ok": True, "why": "ok"} for k in
              ("category", "attributes", "copy", "tags", "description")}
    fp = search_fingerprint(title="Baby blanket crochet pattern" + ("x" if stale else ""),
                            description=desc, tags=["baby blanket"], taxonomy_id=123,
                            properties=[])
    with db.session() as s:
        s.add(ListingSearchProfile(product_slug=SLUG, version=VERSION, category_status="CHOSEN",
                                   taxonomy_id=123, properties=[], verdict=verdict,
                                   certificate={"checks": checks}, fingerprint=fp))


def test_an_empty_shop_is_unmeasured_not_passed_and_never_blended():
    db = _db()
    prof = rr.profile(db, SLUG)
    assert set(prof["dimensions"]) == set(rr.DIMENSIONS)
    assert prof["blended_score"] is None
    for name in ("listing_quality", "click_readiness", "conversion_readiness",
                 "service_quality"):
        d = prof["dimensions"][name]
        assert d["status"] == rr.UNMEASURED and d["verdict"] is None, (name, d)
    assert prof["search_certificate"]["verdict"] == "NONE"
    # the summary never prints UNMEASURED as PASS
    assert all(v != rr.PASS for k, v in rr.summary(prof).items() if k != "shop_quality")


def test_dimensions_are_independent():
    db = _db()
    desc = _listing(db)
    _search_profile(db, desc)
    prof = rr.profile(db, SLUG, VERSION)
    dims = prof["dimensions"]
    assert dims["listing_quality"]["status"] == rr.MEASURED
    assert dims["listing_quality"]["verdict"] == rr.PASS, dims["listing_quality"]
    # no listing-set certificate: click readiness stays unmeasured, and does not drag the
    # search dimension down with it (the hero is counted once, here)
    assert dims["click_readiness"]["status"] == rr.UNMEASURED
    with db.session() as s:
        s.add(ListingSetCertificateRecord(product_slug=SLUG, version=VERSION, state="valid",
                                          certificate={"frames": [{"position": 1,
                                                                   "sha256": "f" * 64,
                                                                   "job": "hero"}]}))
    prof = rr.profile(db, SLUG, VERSION)
    assert prof["dimensions"]["click_readiness"]["verdict"] == rr.PASS
    assert prof["search_certificate"]["verdict"] == "PASS"


def test_a_stale_certificate_fails_listing_quality_and_shows_stale():
    db = _db()
    desc = _listing(db)
    _search_profile(db, desc, stale=True)
    prof = rr.profile(db, SLUG, VERSION)
    assert prof["search_certificate"]["verdict"] == "STALE"
    lq = prof["dimensions"]["listing_quality"]
    assert lq["status"] == rr.MEASURED and lq["verdict"] == rr.FAIL
    assert "F-294" in lq["why"]


def test_a_measured_failure_outranks_an_unmeasured_component():
    db = _db()
    _listing(db, price=0.0, disclosed=False)
    conv = rr.conversion_readiness(db, SLUG, VERSION, first_customer=None)
    assert conv["status"] == rr.MEASURED and conv["verdict"] == rr.FAIL
    assert "price" in conv["why"] and "disclosure" in conv["why"]
    db2 = _db()
    _listing(db2)
    conv = rr.conversion_readiness(db2, SLUG, VERSION, first_customer=None)
    assert conv["status"] == rr.UNMEASURED and conv["verdict"] is None


def test_service_quality_is_measured_only_from_sent_responses():
    db = _db()
    assert rr.service_quality(db)["status"] == rr.UNMEASURED
    now = datetime.now(timezone.utc)
    with db.session() as s:
        for minutes in (2, 3, 4):
            s.add(SupportCase(customer_ref="c1", question="q", answer="a", escalated=False,
                              at=now - timedelta(hours=1),
                              detail={"response_minutes": minutes,
                                      "response_measured_as": "sent"}))
    sq = rr.service_quality(db)
    assert sq["status"] == rr.MEASURED and sq["verdict"] == rr.PASS, sq


def test_launch_plan_calls_the_profile():
    from brambleloop.runtime import release

    src = inspect.getsource(release.handle_launch_plan)
    assert "ranking_readiness.profile(" in src
    assert 'out["ranking_readiness"]' in src


def test_the_catalogue_shows_the_certificate_verdict_not_the_proxy():
    tmp = tempfile.mkdtemp(prefix="fb4_cat_")
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(tmp, 'c.db')}"
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(tmp, "artifacts")
    os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    main.db.create_all()
    with main.db.session() as s:
        s.add(Listing(product_slug=SLUG, version=VERSION, title="t", description="d",
                      tags=[], price_cad=8.5, seo_score=0.91))
    body = TestClient(main.app).get("/api/catalogue").json()
    row = next(r for r in body["listings"] if r["slug"] == SLUG)
    assert "search_share" not in row, row
    assert row["search_certificate"] == "NONE"
    assert set(row["ranking_readiness"]) == set(rr.DIMENSIONS)
    assert row["ranking_readiness"]["listing_quality"] == rr.UNMEASURED
    assert "no blended score" in body["ranking_readiness_basis"]["rule"]


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
