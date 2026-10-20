"""W4-CLOSE6: F-040 Shop Quality Gate -- the live shop, including its About, gates launch.

  F-040  "Icon, About/brand presentation and core trust elements must be complete before
          launch."

The mapping said readiness checked only draft storefront text. That is stale. W4-ETSYSURF
made launch readiness (`etsy_first_sale_surfaces`) read the daily `etsy.shop_snapshot`, a
getShop read judged by `intel.etsy_surfaces.assess_shop`. Production b931d17 reads the live
shop daily, and readiness is held on what is missing there today: banner, shipping policy,
additional policy, a digital listing
(research/final_build/w4/evidence_CLOSE6/prod_api_launch_shop_20261020T1329Z.json).

One part of the criterion was not covered. getShop has no About field, so nothing could see
the About story, and readiness never asked about it. The owner's dated reading of the shop
page (POST /api/etsy/shop-observation, page `about`) is now its evidence. Readiness holds
unless that reading is fresh and says the About is published.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_shop.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.commerce import shop_observations  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import etsy_surfaces as es  # noqa: E402
from brambleloop.launch import readiness  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402

import test_etsy_surfaces as tes  # noqa: E402  (its known-good getShop body)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/shop.sqlite")
    db.create_all()
    return db


def _snapshot(db, body: dict):
    now = time.time()
    snap = {"observed_at": now, "shop": body}
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING,
                           {**snap, "status": es.assess_shop(snap, now=now).to_dict()})


def _about(db, present: bool, *, days_ago: float = 0.0, complete: bool = True):
    shop_observations.record(
        db, page="about", complete=complete,
        observed_at=(datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        values={"about_present": present, "matches_storefront": present},
        statement="Shop page read: the About section " + ("shows" if present else
                                                          "is empty"))


def _failing(db):
    item = readiness.etsy_first_sale_surfaces(db)
    return item, item.evidence["shop_checks_failing"]


def test_a_complete_live_shop_with_its_about_observed_has_no_shop_failure():
    db = _db()
    _snapshot(db, tes._good_shop())
    _about(db, True)
    item, failing = _failing(db)
    assert failing == [], failing
    assert item.evidence["about_story"]["state"] == "FRESH"


def test_the_about_story_must_be_evidenced_published_and_fresh():
    for setup, expect in ((lambda db: None, "about_story:unobserved"),
                          (lambda db: _about(db, False), "about_story:not_published"),
                          (lambda db: _about(db, True, days_ago=45), "about_story:stale"),
                          (lambda db: _about(db, True, complete=False),
                           "about_story:incomplete")):
        db = _db()
        _snapshot(db, tes._good_shop())
        setup(db)
        item, failing = _failing(db)
        assert failing == [expect], (expect, failing)
        assert item.ready is False and item.blocked_by == readiness.BLOCKED_OWNER
    try:
        shop_observations.record(db, page="about", complete=True,
                                 observed_at=datetime.now(timezone.utc).isoformat(),
                                 values={}, statement="looked")
        raise AssertionError("an About reading without about_present was accepted")
    except shop_observations.ObservationRefused:
        pass


def test_a_missing_icon_or_no_shop_reading_holds_launch():
    db = _db()
    body = dict(tes._good_shop(), icon_url_fullxfull=None)
    _snapshot(db, body)
    _about(db, True)
    item, failing = _failing(db)
    assert "icon_set" in failing and item.ready is False
    db = _db()
    _about(db, True)
    item, _failing_ = _failing(db)
    assert item.ready is False, "no shop reading is no evidence, never a pass"


def test_production_holds_launch_on_the_live_shop_as_it_is():
    ev = json.loads((ROOT / "research/final_build/w4/evidence_CLOSE6/"
                     "prod_api_launch_shop_20261020T1329Z.json").read_text())
    assert ev["build"]["commit"].startswith("b931d17")
    item = ev["etsy_first_sale_surfaces"]
    assert item["ready"] is False and ev["launch_ready"] is False
    assert "banner_set" in item["evidence"]["shop_checks_failing"]
    snaps = ev["shop_snapshots"]
    assert snaps and all(s["detail"]["evidence"] == "FRESH" for s in snaps), \
        "the live shop is read daily in production"


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 4, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
