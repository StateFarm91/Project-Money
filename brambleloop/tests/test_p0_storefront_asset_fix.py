"""P0-STOREFRONT-ASSET-FIX: asset-health findings become bounded, keyed work.

Review STOREFRONT d8b2754b (DO NOT SHIP) found that the first cut re-drove the whole release
chain. It flipped a live listing to `draft`, overwrote owner photographs, raced a fresh
certification and never closed its cards. These tests pin the fixed behaviour:

* F1/F2: the rebuild is `fix_only`. Drained through the real Worker on a PUBLISHED listing,
  it leaves the listing's state, price and Etsy id alone, records no price point, and reaches
  no `launch.plan` / `marketing.schedule` / `store.publish`. The owner gets a card.
* F3: a release whose own chain is queued, running or unfinished is not rebuilt.
* F4: a gallery holding an owner photograph (or any non-render frame) is not rebuilt.
* F5: ASSET_LOW_RESOLUTION is reported, never routed to a rebuild.
* F6: cards close when their finding clears in a reading that measured it. A card the owner
  closed is not re-opened unless the evidence changed.
* F7: the full OwnerAction set and the card fields are pinned. The UNKNOWN health guard and a
  held brand-mark card are covered.

Two fixtures: the F-527 fixtures from `test_w4_c3` (fast, no chain), and the real certified
Launch-0 chain from `test_w6_fix_only_rebuild` (real SQLite file, Worker and handlers).
Every product is a test fixture. Nothing is sent to Etsy.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_p0_storefront_asset_fix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.core.models import (AuditLog, Job, JobStatus, ListingAsset,  # noqa: E402
                                     OwnerAction, PriceObservation)
from brambleloop.ops import owner_queue  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.runtime.release import chain_key  # noqa: E402
from brambleloop.store_foundation import asset_health as AH  # noqa: E402
from tests.test_w4_c3 import _certify, _db, _run  # noqa: E402
import test_w6_fix_only_rebuild as W6  # noqa: E402

ICON_KEY = "storefront.asset:ICON_MISSING:shop_icon"


def _shop(db, icon="", age=0.0):
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {"observed_at": time.time() - age,
                           "shop": {"icon_url_fullxfull": icon, "image_url_760x100": ""}})


def _seeded():
    db = _db()
    _shop(db)
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


def _all_cards(db) -> list[tuple]:
    """Every OwnerAction row, keyless ones included: (key, done, state)."""
    with db.session() as s:
        return sorted((r.requirement_key, bool(r.done), r.state)
                      for r in s.scalars(select(OwnerAction)))


def _card(db, key):
    with db.session() as s:
        row = s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == key)
                        .order_by(OwnerAction.id.desc())).first()
        s.expunge(row)
        return row


def _routed(db) -> dict:
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == AH.ROUTED)
                       .order_by(AuditLog.id.desc()))
        return dict(row.detail or {}) if row else {}


def _review(db):
    return _run(db, "storefront_director", "storefront.review")


class _Patch:
    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


def _sweep(findings=None, raises=False):
    def fake():
        if raises:
            raise RuntimeError("unreadable marks")
        return {"findings": list(findings or []), "marks_checked": 1,
                "fix_count": len(findings or [])}
    return fake


MARK = {"code": "MARK_OFF_PALETTE", "subject": "brambleloop-mark.svg",
        "route_to": "storefront_director", "why": "fill #ff0000 is not a palette colour",
        "severity": "fix"}
MARK_KEY = f"storefront.asset:{MARK['code']}:{MARK['subject']}"


# ---- routing on the F-527 fixtures ------------------------------------------------------

def test_each_stale_or_missing_listing_image_set_gets_one_fix_only_rebuild():
    db = _seeded()
    rv = _review(db)
    jobs = _rebuilds(db)
    assert [(j.job_type, j.inputs["slug"]) for j in jobs] == [
        ("assets.build", "no-hero"), ("assets.build", "old-assets")], \
        [(j.job_type, j.idempotency_key) for j in jobs]
    old = next(j for j in jobs if j.inputs["slug"] == "old-assets")
    assert old.inputs == {"slug": "old-assets", "version": "2.0.0",
                          "release": "old-assets2.0.0",
                          "rebuild": "asset-health:old-assets2.0.0",
                          "fix_only": True}, old.inputs
    assert old.idempotency_key == "asset-fix:old-assets:old-assets2.0.0"
    assert all(j.agent == "publishing" and j.inputs["fix_only"] is True for j in jobs)
    assert rv["asset_health"]["rebuilds_queued"] == 2
    routed = _routed(db)
    assert {q["slug"]: q["codes"] for q in routed["queued"]} == {
        "no-hero": ["HERO_MISSING"], "old-assets": ["ASSETS_STALE", "HERO_MISSING"]}
    # F5: low resolution is reported honestly, never sent to a rebuild that cannot fix it.
    assert {"code": "ASSET_LOW_RESOLUTION", "subject": "bad-assets",
            "why": AH.LOW_RES_WHY} in routed["not_routed"], routed["not_routed"]
    # A gate-blocked frame is not "fixed" by rendering the same release again.
    assert {"code": "ASSET_BLOCKED", "subject": "bad-assets",
            "why": "not a re-render fix"} in routed["not_routed"], routed["not_routed"]
    assert routed["live_image_cards"] == [] and routed["cards_closed"] == []
    # The icon has no API: exactly one owner row in the whole queue, nothing sent to Etsy.
    assert _all_cards(db) == [(ICON_KEY, False, "open")], _all_cards(db)
    card = _card(db, ICON_KEY)
    assert "Shop Manager" in card.action and "500 x 500" in card.action, card.action
    assert card.max_cost_cad == 0.0 and card.minutes == 10, (card.max_cost_cad, card.minutes)
    assert card.consequence_of_delay == "the shop keeps showing the asset as it is"
    assert card.why_software_cannot == ("Etsy's Open API has no endpoint that sets the "
                                        "shop icon")
    assert card.blocks == "storefront asset shop_icon"
    assert card.reason.startswith("brand asset health") and "[evidence " in card.reason
    assert rv["writes_performed"] == 0 and rv["etsy_calls"] == 0


def test_a_rerun_queues_nothing_and_raises_no_second_card():
    db = _seeded()
    _review(db)
    before = [j.id for j in _rebuilds(db)]
    rv = _review(db)
    assert [j.id for j in _rebuilds(db)] == before and len(before) == 2
    assert rv["asset_health"]["rebuilds_queued"] == 0
    assert len(_routed(db)["already_queued"]) == 2
    assert _all_cards(db) == [(ICON_KEY, False, "open")], _all_cards(db)


def test_a_new_release_can_be_rebuilt_again():
    db = _seeded()
    _review(db)
    _certify(db, "old-assets", "3.0.0")
    _review(db)
    keys = [j.idempotency_key for j in _rebuilds(db) if j.inputs["slug"] == "old-assets"]
    assert keys == ["asset-fix:old-assets:old-assets2.0.0",
                    "asset-fix:old-assets:old-assets3.0.0"], keys


def test_an_unreadable_health_check_routes_nothing():
    db = _seeded()

    def broken(_db):
        raise RuntimeError("boom")
    with _Patch(AH, "check", broken):
        rv = _review(db)
    assert _rebuilds(db) == [] and _all_cards(db) == [], _all_cards(db)
    assert _routed(db) == {}, "route() never ran on an UNKNOWN reading"
    assert rv["asset_health"]["rebuilds_queued"] == 0 and rv["asset_health"]["fixes"] is None


# ---- F3: the release's own chain is still coming -----------------------------------------

def test_a_release_whose_own_chain_is_in_flight_is_not_rebuilt():
    db = _seeded()
    q = JobQueue(db)
    # no-hero: its own listing.draft is still queued (a fresh certification).
    q.enqueue("listing", "listing.draft", {"slug": "no-hero", "version": "1.0.0",
                                           "release": "no-hero1.0.0"},
              idempotency_key=chain_key("listing", "no-hero", "1.0.0", "no-hero1.0.0"))
    # old-assets: its own normal assets.build died.
    j = q.enqueue("publishing", "assets.build",
                  {"slug": "old-assets", "version": "2.0.0", "release": "old-assets2.0.0",
                   "rebuild": ""},
                  idempotency_key=chain_key("assets", "old-assets", "2.0.0",
                                            "old-assets2.0.0"))
    with db.session() as s:
        s.get(Job, j.id).status = JobStatus.DEAD
    _review(db)
    assert _rebuilds(db) == [], [j.idempotency_key for j in _rebuilds(db)]
    why = {(n["subject"], n["code"]): n["why"] for n in _routed(db)["not_routed"]}
    assert "listing.draft" in why[("no-hero", "HERO_MISSING")], why
    assert "own assets.build" in why[("old-assets", "ASSETS_STALE")], why


def test_a_pending_certification_of_the_slug_is_waited_for():
    db = _seeded()
    JobQueue(db).enqueue("validator", "gate.certify", {"cir": {"slug": "no-hero"}},
                         idempotency_key="cert-no-hero")
    _review(db)
    assert [j.inputs["slug"] for j in _rebuilds(db)] == ["old-assets"]


def test_a_release_its_own_draft_withheld_is_not_rebuilt():
    db = _seeded()
    j = JobQueue(db).enqueue("listing", "listing.draft",
                             {"slug": "no-hero", "version": "1.0.0", "release": "no-hero1.0.0"},
                             idempotency_key=chain_key("listing", "no-hero", "1.0.0",
                                                       "no-hero1.0.0"))
    with db.session() as s:
        s.get(Job, j.id).status = JobStatus.DONE   # done, and it queued no assets.build
    _review(db)
    assert [j.inputs["slug"] for j in _rebuilds(db)] == ["old-assets"]
    why = {(n["subject"], n["code"]): n["why"] for n in _routed(db)["not_routed"]}
    assert "built no images" in why[("no-hero", "HERO_MISSING")], why


def test_a_finished_chain_does_not_block_the_rebuild():
    db = _seeded()
    q = JobQueue(db)
    for stage, jt in (("listing", "listing.draft"), ("assets", "assets.build")):
        j = q.enqueue("publishing", jt, {"slug": "no-hero", "version": "1.0.0",
                                         "release": "no-hero1.0.0"},
                      idempotency_key=chain_key(stage, "no-hero", "1.0.0", "no-hero1.0.0"))
        with db.session() as s:
            s.get(Job, j.id).status = JobStatus.DONE
    _review(db)
    assert [j.inputs["slug"] for j in _rebuilds(db)] == ["no-hero", "old-assets"]


# ---- F4: never overwrite an owner photograph ---------------------------------------------

def test_a_gallery_with_an_owner_photo_is_not_rebuilt():
    db = _seeded()
    with db.session() as s:
        s.add(ListingAsset(product_slug="no-hero", version="1.0.0", position=1,
                           asset_class="PHYSICAL_PRODUCT_PHOTO", role="hero", approved=False,
                           sha256="OWNERPHOTO", blocked_reasons=["awaiting review"]))
    _review(db)
    assert [j.inputs["slug"] for j in _rebuilds(db)] == ["old-assets"]
    why = {(n["subject"], n["code"]): n["why"] for n in _routed(db)["not_routed"]}
    assert "1:PHYSICAL_PRODUCT_PHOTO" in why[("no-hero", "HERO_MISSING")], why


# ---- F6: cards close, and a closed card stays closed ------------------------------------

def test_the_icon_card_closes_when_the_icon_is_read_and_not_on_a_stale_reading():
    db = _seeded()
    _review(db)
    _shop(db, age=30 * 86400)          # a stale reading measures nothing: the card stays
    _review(db)
    assert _all_cards(db) == [(ICON_KEY, False, "open")], _all_cards(db)
    _shop(db, icon="https://example.invalid/icon.png")
    _review(db)
    assert _all_cards(db) == [(ICON_KEY, True, owner_queue.SATISFIED)], _all_cards(db)
    assert _card(db, ICON_KEY).state_reason == AH.AUTO_CLOSED
    assert _routed(db)["cards_closed"][0]["key"] == ICON_KEY
    _shop(db)                          # the icon is removed again: a new card opens
    _review(db)
    assert _all_cards(db) == [(ICON_KEY, False, "open"),
                              (ICON_KEY, True, owner_queue.SATISFIED)], _all_cards(db)


def test_a_card_the_owner_closed_is_not_reopened_until_the_evidence_changes():
    db = _seeded()
    from brambleloop.brand import asset_consistency

    with _Patch(asset_consistency, "sweep", _sweep([MARK])):
        _review(db)
        with db.session() as s:
            row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == MARK_KEY))
            assert row is not None and not row.done
            assert row.why_software_cannot.startswith("a brand mark is a design decision")
            assert MARK["why"] in row.action and row.max_cost_cad == 0.0 and row.minutes == 10
            owner_queue.close(row, owner_queue.WITHDRAWN, "owner: the red is intentional")
        _review(db)
        assert [c for c in _all_cards(db) if c[0] == MARK_KEY] == [
            (MARK_KEY, True, owner_queue.WITHDRAWN)], _all_cards(db)
        assert _routed(db)["owner_closed_same_evidence"][0]["key"] == MARK_KEY
    changed = {**MARK, "why": "fill #00ff00 is not a palette colour"}
    with _Patch(asset_consistency, "sweep", _sweep([changed])):
        _review(db)
    assert [c for c in _all_cards(db) if c[0] == MARK_KEY] == [
        (MARK_KEY, False, "open"), (MARK_KEY, True, owner_queue.WITHDRAWN)], _all_cards(db)


def test_a_held_brand_mark_card_closes_only_on_a_sweep_that_ran():
    db = _seeded()
    from brambleloop.brand import asset_consistency

    with _Patch(asset_consistency, "sweep", _sweep([MARK])):
        _review(db)
    assert _all_cards(db) == [(ICON_KEY, False, "open"),
                              (MARK_KEY, False, "open")], _all_cards(db)
    with _Patch(asset_consistency, "sweep", _sweep(raises=True)):
        _review(db)
    assert (MARK_KEY, False, "open") in _all_cards(db), _all_cards(db)  # UNKNOWN never clears
    with _Patch(asset_consistency, "sweep", _sweep([])):
        _review(db)
    assert _all_cards(db) == [(ICON_KEY, False, "open"),
                              (MARK_KEY, True, owner_queue.SATISFIED)], _all_cards(db)


# ---- F1/F2/F4 through the real Worker on a certified chain -------------------------------

def _chain_review(db):
    JobQueue(db).enqueue("storefront_director", "storefront.review", {}, priority=0,
                         idempotency_key=f"sf-review-{time.time_ns()}")
    W6._drain(db, name=f"sf-{time.time_ns()}")


def _gallery(db, slug, version):
    with db.session() as s:
        return [(a.position, a.asset_class, a.role, a.sha256, bool(a.approved))
                for a in s.scalars(select(ListingAsset).where(
                    ListingAsset.product_slug == slug, ListingAsset.version == version)
                    .order_by(ListingAsset.position))]


def _types(db):
    with db.session() as s:
        return [(j.job_type, j.status) for j in s.scalars(select(Job).order_by(Job.id))]


def _frames(db, slug, version):
    with db.session() as s:
        return list(s.scalars(select(ListingAsset).where(ListingAsset.product_slug == slug,
                                                         ListingAsset.version == version)))


def test_on_a_live_listing_the_photo_is_kept_and_the_fix_never_reaches_publish():
    st = W6.chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    W6._set_listing(db, slug, version, state="published", etsy_listing_id="1234567",
                    price_cad=12.34)
    # The hero's approval is lost (standing for a hero a later check blocked): HERO_MISSING.
    with db.session() as s:
        for a in s.scalars(select(ListingAsset).where(ListingAsset.product_slug == slug,
                                                      ListingAsset.version == version)):
            if a.role == "hero":
                a.approved = False
    renders = _gallery(db, slug, version)
    assert renders and all(r[1] in AH.RENDER_CLASSES for r in renders), renders
    # 1) F4: the owner's photograph leads the gallery (physical_upgrade renumbers the renders
    #    behind it). The review routes no rebuild and the photograph row survives.
    with db.session() as s:
        for a in s.scalars(select(ListingAsset).where(ListingAsset.product_slug == slug,
                                                      ListingAsset.version == version)
                           .order_by(ListingAsset.position.desc())):
            a.position += 1
            s.flush()
        s.add(ListingAsset(product_slug=slug, version=version, position=1,
                           asset_class="PHYSICAL_PRODUCT_PHOTO", role="hero",
                           sha256="OWNERPHOTO", approved=False,
                           blocked_reasons=["awaiting asset-truth review"]))
    with_photo = _gallery(db, slug, version)
    _chain_review(db)
    assert _rebuilds(db) == [], [j.idempotency_key for j in _rebuilds(db)]
    assert _gallery(db, slug, version) == with_photo
    assert with_photo[0] == (1, "PHYSICAL_PRODUCT_PHOTO", "hero", "OWNERPHOTO", False)
    # 2) Without the photograph the fix-only rebuild runs, through the real Worker.
    with db.session() as s:
        for a in s.scalars(select(ListingAsset).where(ListingAsset.product_slug == slug,
                                                      ListingAsset.version == version)
                           .order_by(ListingAsset.position)):
            if a.asset_class == "PHYSICAL_PRODUCT_PHOTO":
                s.delete(a)
            else:
                a.position -= 1
            s.flush()
    assert _gallery(db, slug, version) == renders
    before, cards_before = W6._listing(db, slug, version), set(_all_cards(db))
    with db.session() as s:
        points = s.scalar(select(func.count()).select_from(PriceObservation))
    jobs_before = len(_types(db))
    _chain_review(db)
    fixes = _rebuilds(db)
    assert len(fixes) == 1 and fixes[0].status == JobStatus.DONE, \
        [(j.idempotency_key, j.status, j.error) for j in fixes]
    assert fixes[0].inputs["fix_only"] is True
    ran = [t for t, _s in _types(db)[jobs_before:]]
    assert "listing.seo" in ran, ran                                     # the fix ran
    assert not [t for t in ran if t in W6.DOWNSTREAM], ran              # and stopped
    with db.session() as s:   # none carries the fix's token or its fix_only flag, ever
        assert not [j.job_type for j in s.scalars(select(Job).where(Job.job_type.in_(
            ("launch.plan", "marketing.schedule", "store.publish"))))
            if (j.inputs or {}).get("fix_only")
            or str((j.inputs or {}).get("rebuild", "")).startswith("asset-health")]
    assert W6._listing(db, slug, version) == before                      # state, price, id
    assert before["state"] == "published" and before["price"] == 12.34
    assert before["etsy"] == "1234567"
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(PriceObservation)) == points
    after = _gallery(db, slug, version)
    assert [r[:3] for r in after] == [r[:3] for r in renders], after    # same render frames
    assert next(r for r in after if r[2] == "hero")[4] is True          # hero restored
    # The owner, not the system, takes the new images to the live listing.
    token = fixes[0].inputs["release"][:16]
    live_key = f"storefront.live_images:{slug}@{version}:{token}"
    new = set(_all_cards(db)) - cards_before
    assert {k for k, _d, _s in new} == {live_key, f"listing.live_update:{slug}@{version}"}, new
    with db.session() as s:
        photo = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == live_key))
        assert f"listing.live_update:{slug}@{version}" in photo.action, photo.action
    card = _card(db, live_key)
    assert not card.done and card.max_cost_cad == 0.0 and card.minutes == 15
    assert "1234567" in card.action and f"job {fixes[0].id}" in card.action, card.action
    assert card.why_software_cannot == "live listings are never changed autonomously"
    assert card.consequence_of_delay == "the live listing keeps showing its current images"


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
