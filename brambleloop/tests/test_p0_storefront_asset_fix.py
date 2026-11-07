"""P0-STOREFRONT-ASSET-FIX: asset-health findings become keyed work, once per release.

The real `storefront.review` handler runs on file-backed SQLite with the same fixtures as
F-527's own test (`test_w4_c3`):
- a certified product with no hero;
- one whose only images are for an older version (its images no longer match the release);
- one with a low-resolution hero and a gate-blocked frame;
- a live shop with no icon.
Every product is a test fixture. Nothing is sent to Etsy.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_p0_storefront_asset_fix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import AuditLog, Job, ListingAsset, OwnerAction  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.store_foundation import asset_health as AH  # noqa: E402
from tests.test_w4_c3 import _certify, _db, _run  # noqa: E402


def _seeded():
    db = _db()
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {"observed_at": time.time(),
                           "shop": {"icon_url_fullxfull": "", "image_url_760x100": ""}})
    _certify(db, "no-hero")
    _certify(db, "old-assets", "2.0.0")
    _certify(db, "bad-assets")
    _certify(db, "fine-assets")
    with db.session() as s:
        s.add(ListingAsset(product_slug="old-assets", version="1.0.0", position=1,
                           asset_class="DIGITAL_TWIN_RENDER", role="hero", approved=True))
        s.add(ListingAsset(product_slug="bad-assets", version="1.0.0", position=1,
                           asset_class="DIGITAL_TWIN_RENDER", role="hero", approved=True,
                           claims={"width_px": 1000, "height_px": 1000}))
        s.add(ListingAsset(product_slug="bad-assets", version="1.0.0", position=2,
                           asset_class="AI_LIFESTYLE_CONCEPT", role="lifestyle",
                           approved=False, blocked_reasons=["off-brand palette"]))
        s.add(ListingAsset(product_slug="fine-assets", version="1.0.0", position=1,
                           asset_class="DIGITAL_TWIN_RENDER", role="hero", approved=True,
                           claims={"width_px": 2400, "height_px": 2400}))
    return db


def _rebuilds(db) -> list[Job]:
    with db.session() as s:
        rows = list(s.scalars(select(Job).where(Job.idempotency_key.like("asset-fix:%"))
                              .order_by(Job.idempotency_key)))
        for r in rows:
            s.expunge(r)
        return rows


def _cards(db) -> list[str]:
    with db.session() as s:
        return sorted(r.requirement_key for r in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("storefront.asset:%"))))


def _routed(db) -> dict:
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == AH.ROUTED)
                       .order_by(AuditLog.id.desc()))
        return dict(row.detail or {})


def test_each_stale_or_missing_listing_image_set_gets_one_release_keyed_rebuild():
    db = _seeded()
    rv = _run(db, "storefront_director", "storefront.review")
    jobs = _rebuilds(db)
    assert [(j.job_type, j.inputs["slug"]) for j in jobs] == [
        ("assets.build", "bad-assets"), ("assets.build", "no-hero"),
        ("assets.build", "old-assets")], [(j.job_type, j.idempotency_key) for j in jobs]
    old = next(j for j in jobs if j.inputs["slug"] == "old-assets")
    assert old.inputs["version"] == "2.0.0" and old.inputs["release"] == "old-assets2.0.0"
    assert old.idempotency_key == "asset-fix:old-assets:old-assets2.0.0"
    assert all(j.agent == "publishing" for j in jobs)
    assert rv["asset_health"]["rebuilds_queued"] == 3
    routed = _routed(db)
    bad = next(q for q in routed["queued"] if q["slug"] == "bad-assets")
    assert bad["codes"] == ["ASSET_LOW_RESOLUTION"], bad   # one rebuild, its reasons listed
    # A gate-blocked frame is not "fixed" by rendering the same release again.
    assert {"code": "ASSET_BLOCKED", "subject": "bad-assets",
            "why": "not a re-render fix"} in routed["not_routed"], routed["not_routed"]
    # The icon has no API: one owner card, nothing written to Etsy.
    assert _cards(db) == ["storefront.asset:ICON_MISSING:shop_icon"]
    assert rv["writes_performed"] == 0 and rv["etsy_calls"] == 0


def test_a_rerun_queues_nothing_and_raises_no_second_card():
    db = _seeded()
    _run(db, "storefront_director", "storefront.review")
    before = [j.id for j in _rebuilds(db)]
    rv = _run(db, "storefront_director", "storefront.review")
    assert [j.id for j in _rebuilds(db)] == before and len(before) == 3
    assert rv["asset_health"]["rebuilds_queued"] == 0
    assert len(_routed(db)["already_queued"]) == 3
    assert _cards(db) == ["storefront.asset:ICON_MISSING:shop_icon"]
    with db.session() as s:
        open_cards = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("storefront.asset:%"))))
    assert len(open_cards) == 1


def test_a_new_release_can_be_rebuilt_again():
    db = _seeded()
    _run(db, "storefront_director", "storefront.review")
    _certify(db, "old-assets", "3.0.0")
    _run(db, "storefront_director", "storefront.review")
    keys = [j.idempotency_key for j in _rebuilds(db) if j.inputs["slug"] == "old-assets"]
    assert keys == ["asset-fix:old-assets:old-assets2.0.0",
                    "asset-fix:old-assets:old-assets3.0.0"], keys


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
