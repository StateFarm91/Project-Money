"""W6 FIX-ONLY: a remediation rebuild is bounded.

Reviews PORTFOLIO f3bea437 and STOREFRONT d8b2754b found that an autonomous remediation
(an SEO fix, an asset fix) re-drove the whole release chain. It flipped a LIVE listing back
to local `draft`, reverted its price from stale inputs, and reached `store.publish` with no
owner gate. That re-opened FMBATCH1 F-1, which `integrations/taxonomy_drift.py` closed only
for its own re-queue.

`fix_only: True` in a chain's inputs now bounds every such rebuild:
* `assets.build` carries it to `pricing.position` and on to `listing.seo`;
* `pricing.position` records no price point, because no price is applied;
* `listing.seo` never changes a live listing's row. It records the candidate copy
  (`listing.fix_candidate`) and raises an owner card. On a draft it refreshes the copy but
  keeps the existing price;
* `listing.seo` stops before `launch.plan`, so `marketing.schedule` and `store.publish` are
  never enqueued. `launch.plan` itself refuses a fix-only input as a backstop.

Real SQLite file, real Worker and real handlers, on a real certified Launch-0 chain.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w6_fix_only_rebuild.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
_TMP = tempfile.mkdtemp(prefix="w6_fixonly_")

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Job, JobStatus, Listing, ListingSearchProfile,  # noqa: E402
                                     OwnerAction, Phase, PriceObservation)
from brambleloop.products import builder  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

_STATE: dict = {}
DOWNSTREAM = ("launch.plan", "marketing.schedule", "store.publish")


def _drain(db, name="fixonly", limit=500):
    w = Worker(db, name, phase=Phase.SHADOW, lease_seconds=900)
    for _ in range(limit):
        if not w.run_once():
            break


def chain() -> dict:
    if _STATE:
        return _STATE
    db = Database(f"sqlite:///{_TMP}/chain.db")
    db.create_all()
    Registry(db).seed_defaults()
    cir = builder.for_slug("cloudline-baby-blanket")
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                         idempotency_key="fo-compile")
    _drain(db)
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
            j.status = JobStatus.CANCELLED
        build = s.scalars(select(Job).where(Job.job_type == "assets.build",
                                            Job.status == JobStatus.DONE)
                          .order_by(Job.id)).first()
        assert build is not None, "the chain built no assets"
        inputs = dict(build.inputs or {})
    _STATE.update(db=db, slug=cir.slug, version=cir.version, inputs=inputs)
    return _STATE


def _listing(db, slug, version):
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        assert row is not None, "the chain drafted no listing"
        return {"state": row.state, "price": row.price_cad, "title": row.title,
                "etsy": row.etsy_listing_id, "tags": list(row.tags or [])}


def _set_listing(db, slug, version, **kw):
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        for k, v in kw.items():
            setattr(row, k, v)


def _jobs(db, token):
    with db.session() as s:
        return [(j.job_type, j.status) for j in s.scalars(select(Job).order_by(Job.id))
                if (j.inputs or {}).get("rebuild") == token]


def _audits(db, action):
    with db.session() as s:
        return [dict(a.detail or {}) for a in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def _price_points(db):
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(PriceObservation))


def _fix(db, inputs, token):
    JobQueue(db).enqueue("publishing", "assets.build",
                         {**inputs, "rebuild": token, "fix_only": True}, priority=0,
                         idempotency_key=f"fo-{token}")
    _drain(db, name=f"fo-{token}")


def test_a_fix_only_rebuild_never_touches_a_live_listing_and_never_reaches_publish():
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="published", etsy_listing_id="1234567",
                 price_cad=12.34)
    from brambleloop.commerce import elasticity

    # The live price was changed to 12.34, and its price point opened. A rebuild that
    # recorded its own computed price would open a second one; nothing was applied.
    elasticity.record_price_set(db, product_slug=slug, category="blanket", price_cad=12.34,
                                set_by="owner")
    before, points = _listing(db, slug, version), _price_points(db)
    _fix(db, st["inputs"], "live-1")
    ran = _jobs(db, "live-1")
    types = [t for t, _s in ran]
    assert "listing.seo" in types, ran                       # the fix really ran
    assert not [t for t in types if t in DOWNSTREAM], ran   # and stopped before launch
    assert _listing(db, slug, version) == before             # state, price, copy, Etsy id
    assert _price_points(db) == points                       # no fabricated price point
    cand = _audits(db, "listing.fix_candidate")
    assert cand and cand[-1]["applied"] is False and cand[-1]["live"] is True, cand
    with db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"listing.live_update:{slug}@{version}"))
        assert card is not None and not card.done and card.max_cost_cad == 0.0
        assert card.minutes and card.consequence_of_delay
    assert _audits(db, "chain.fix_only_stopped"), "the stop is recorded"


def test_either_an_etsy_id_or_a_published_state_alone_makes_a_listing_live():
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    for n, kw in enumerate(({"state": "draft", "etsy_listing_id": "7654321"},
                            {"state": "published_manually", "etsy_listing_id": ""})):
        _set_listing(db, slug, version, price_cad=12.34, title=f"live title {n}", **kw)
        before, prof = _listing(db, slug, version), _profile(db, slug, version)
        _fix(db, st["inputs"], f"live-only-{n}")
        assert _listing(db, slug, version) == before, (kw, _listing(db, slug, version))
        assert _profile(db, slug, version) == prof, kw          # review 9e8665c3 N3


def test_a_fix_only_rebuild_of_a_draft_refreshes_copy_but_keeps_its_price():
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="draft", etsy_listing_id="", price_cad=12.34,
                 title="an old weak title")
    _fix(db, st["inputs"], "draft-1")
    after = _listing(db, slug, version)
    assert after["state"] == "draft" and after["price"] == 12.34, after   # no revert
    assert after["title"] != "an old weak title", after                    # copy refreshed
    assert not [t for t, _s in _jobs(db, "draft-1") if t in DOWNSTREAM]


def _profile(db, slug, version):
    with db.session() as s:
        rows = s.scalars(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug))
        return sorted(repr({c.name: getattr(r, c.name) for c in r.__table__.columns})
                      for r in rows)


def test_a_live_listing_keeps_its_search_profile_and_the_candidate_is_complete():
    """Review 6cbc08e6 F2 (profile untouched, so no false F-294) and F4 (full candidate)."""
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="published", etsy_listing_id="1234567")
    before = _profile(db, slug, version)
    _fix(db, st["inputs"], "prof-1")
    assert _profile(db, slug, version) == before
    cand = _audits(db, "listing.fix_candidate")[-1]["candidate"]
    assert cand["description"] and cand["title"] and "taxonomy" in cand, cand


def test_a_withdrawn_listing_is_not_revived_as_a_draft():
    """Review 6cbc08e6 F3."""
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="withdrawn", etsy_listing_id="")
    _fix(db, st["inputs"], "wd-1")
    assert _listing(db, slug, version)["state"] == "withdrawn"


def test_the_bound_never_leaks_into_an_ordinary_re_price():
    """Review 6cbc08e6 F1: ordinary re-drives copy the latest assets.build outputs."""
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="draft", etsy_listing_id="")
    _fix(db, st["inputs"], "leak-1")
    with db.session() as s:
        built = [dict(j.outputs or {}) for j in s.scalars(
            select(Job).where(Job.job_type == "assets.build", Job.status == JobStatus.DONE)
            .order_by(Job.id))
            if (j.inputs or {}).get("rebuild") == "leak-1"]
    assert built and all("fix_only" not in b for b in built), built
    # What _reprice_on_plan_drift enqueues: the latest build's outputs plus a token.
    JobQueue(db).enqueue("pricing", "pricing.position", {**built[-1], "rebuild": "leak-2"},
                         priority=0, idempotency_key="fo-leak-2")
    _drain(db, name="fo-leak-2")
    assert "launch.plan" in [t for t, _s in _jobs(db, "leak-2")], _jobs(db, "leak-2")


def test_the_drift_requeue_never_inherits_the_bound():
    """Review 9e8665c3 N1: taxonomy drift copies the newest listing.seo inputs."""
    from brambleloop.integrations import taxonomy_drift

    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="draft", etsy_listing_id="")
    _fix(db, st["inputs"], "drift-1")
    with db.session() as s:
        newest = s.scalars(select(Job).where(Job.job_type == "listing.seo",
                                             Job.status == JobStatus.DONE)
                           .order_by(Job.id.desc())).first()
        assert (newest.inputs or {}).get("fix_only") is True     # the fix run itself
        copied = taxonomy_drift._last_seo_inputs(s, slug, version)
    assert copied and "fix_only" not in copied, copied


def test_every_chain_re_drive_strips_the_bound():
    """Review 9e8665c3 N1/N6: each path that copies a stored chain job uses the helper."""
    import inspect

    from brambleloop.finance import launch_review
    from brambleloop.integrations import taxonomy_drift
    from brambleloop.runtime import release as R

    assert R.without_fix_only({"a": 1, "fix_only": True}) == {"a": 1}
    for fn in (R._reprice_on_plan_drift, R._targeted_rebuild, launch_review.run,
               taxonomy_drift._last_seo_inputs):
        assert "without_fix_only(" in inspect.getsource(fn), fn.__name__


def test_a_rejected_candidate_is_never_put_to_the_owner():
    """Review 9e8665c3 N2: a live-listing candidate the gates refuse raises no card."""
    from brambleloop.agents.registry import Registry
    from brambleloop.runtime import release as R
    from brambleloop.runtime.worker import JobContext

    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="published", etsy_listing_id="5550001")
    with db.session() as s:
        for a in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == f"listing.live_update:{slug}@{version}")):
            a.done = True
    q = JobQueue(db)
    ctx = JobContext(job=q.enqueue("listing", "listing.seo", {"slug": slug, "version": version},
                                   idempotency_key="fo-n2"),
                     db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)

    class Copy:
        title, tags, description = "t", ["a"], "d"

    out = R._fix_only_candidate(ctx, slug, version, copy=Copy(), choice={}, props={},
                                attributes={}, blocking=["DESCRIPTION_TOO_SHORT"])
    assert out["ok"] is False and out["blocking"] == ["DESCRIPTION_TOO_SHORT"], out
    with db.session() as s:
        assert not [a for a in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == f"listing.live_update:{slug}@{version}",
            OwnerAction.done == False))]  # noqa: E712
    assert _audits(db, "listing.fix_candidate")[-1]["rejected"] == ["DESCRIPTION_TOO_SHORT"]


def _clear_cards(db, slug, version):
    with db.session() as s:
        for a in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == f"listing.live_update:{slug}@{version}")):
            a.done = True


def _open_card(db, slug, version):
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == f"listing.live_update:{slug}@{version}",
            OwnerAction.done == False)))  # noqa: E712
        return [r.action for r in rows]


def _forced_gate_failure():
    """Make the real `listing.seo` gates refuse every candidate (review a5781649 R2)."""
    from brambleloop.commerce import seo as seo_mod

    real = seo_mod.check_listing_limits

    def refuse(copy):
        return list(real(copy)) + ["TITLE_OVER_LIMIT: forced by test"]

    seo_mod.check_listing_limits = refuse
    return lambda: setattr(seo_mod, "check_listing_limits", real)


def test_a_gate_refused_candidate_through_listing_seo_raises_no_card():
    """Review a5781649 R2: end to end through the handler, so dropping `blocking=` fails."""
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="published", etsy_listing_id="5550002")
    _clear_cards(db, slug, version)
    restore = _forced_gate_failure()
    try:
        _fix(db, st["inputs"], "gate-ref-1")
    finally:
        restore()
    assert "listing.seo" in [t for t, _s in _jobs(db, "gate-ref-1")]
    assert not _open_card(db, slug, version), _open_card(db, slug, version)
    newest = _audits(db, "listing.fix_candidate")[-1]
    assert any("TITLE_OVER_LIMIT" in r for r in newest["rejected"]), newest["rejected"]
    with db.session() as s:
        seo = s.scalars(select(Job).where(Job.job_type == "listing.seo")
                        .order_by(Job.id.desc())).first()
        assert (seo.inputs or {}).get("rebuild") == "gate-ref-1"
        assert (seo.outputs or {}).get("ok") is False, seo.outputs
    assert not [t for t, _s in _jobs(db, "gate-ref-1") if t in DOWNSTREAM]


def test_a_later_refused_candidate_never_hijacks_an_open_card():
    """Review a5781649 R1: pass, then reject, with the card left open between the two runs."""
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="published", etsy_listing_id="5550003")
    _clear_cards(db, slug, version)
    _fix(db, st["inputs"], "ptr-a")
    passed = _audits(db, "listing.fix_candidate")[-1]
    assert passed["rejected"] == [], passed["rejected"]
    sha_a = passed["candidate_sha"]
    cards = _open_card(db, slug, version)
    assert len(cards) == 1 and sha_a in cards[0], cards
    restore = _forced_gate_failure()
    try:
        _fix(db, st["inputs"], "ptr-b")
    finally:
        restore()
    refused = _audits(db, "listing.fix_candidate")[-1]
    assert refused["rejected"], _jobs(db, "ptr-b")
    # The copy is identical; only the gates changed. The card offering it must not survive.
    assert refused["candidate_sha"] == sha_a
    assert not _open_card(db, slug, version), _open_card(db, slug, version)
    with db.session() as s:
        closed = s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == f"listing.live_update:{slug}@{version}")
            .order_by(OwnerAction.id.desc())).first()
        assert closed.state == "withdrawn" and sha_a in (closed.state_reason or "")
    # A later passing run offers its own candidate again, by hash.
    _fix(db, st["inputs"], "ptr-c")
    cards = _open_card(db, slug, version)
    assert len(cards) == 1 and sha_a in cards[0] and "newest" not in cards[0], cards


def test_flow_health_does_not_read_a_fix_only_stop_as_a_stall():
    """Review 9e8665c3 N5."""
    from brambleloop.ops import flow_health

    handed_off = flow_health.HANDOFFS["listing.seo"][0]
    assert handed_off({"ok": True}) is True
    assert handed_off({"ok": True, "candidate_only": True,
                       "stopped_before": "launch.plan"}) is False


def _gallery(db, slug, version):
    from brambleloop.core.models import ListingAsset

    with db.session() as s:
        return [(a.position, a.asset_class, a.sha256, a.approved) for a in s.scalars(
            select(ListingAsset).where(ListingAsset.product_slug == slug,
                                       ListingAsset.version == version)
            .order_by(ListingAsset.position))]


def test_a_fix_only_rebuild_never_rewrites_a_live_listings_gallery_rows():
    """Review STOREFRONT a1331372 M2: Etsy still shows the old images; so must the rows."""
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="published", etsy_listing_id="5550004")
    from brambleloop.core.models import ListingAsset

    with db.session() as s:                       # the gallery buyers see, marked distinctly
        for a in s.scalars(select(ListingAsset).where(ListingAsset.product_slug == slug,
                                                      ListingAsset.version == version)):
            a.sha256 = "e" * 64
    before = _gallery(db, slug, version)
    assert before, "the chain persisted no gallery"
    _fix(db, st["inputs"], "fr-live-1")
    assert "assets.build" in [t for t, _s in _jobs(db, "fr-live-1")]
    assert _gallery(db, slug, version) == before
    cand = _audits(db, "listing.fix_frame_candidate")
    assert cand and cand[-1]["live"] is True and cand[-1]["frames"], cand


def test_no_rebuild_ever_replaces_a_physical_photograph_slot():
    """Review A3 U5 84085fa8 F2: an ordinary rebuild's render never overwrites a photo."""
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    _set_listing(db, slug, version, state="draft", etsy_listing_id="")
    from brambleloop.core.models import ListingAsset

    with db.session() as s:
        a = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == slug,
                                                ListingAsset.version == version,
                                                ListingAsset.position == 1))
        a.asset_class, a.sha256, a.approved = "PHYSICAL_PRODUCT_PHOTO", "f" * 64, True
    JobQueue(db).enqueue("publishing", "assets.build", {**st["inputs"], "rebuild": "fr-ph-1"},
                         priority=0, idempotency_key="fo-fr-ph-1")
    _drain(db, name="fo-fr-ph")
    assert "assets.build" in [t for t, _s in _jobs(db, "fr-ph-1")]
    assert _gallery(db, slug, version)[0] == (1, "PHYSICAL_PRODUCT_PHOTO", "f" * 64, True)
    kept = _audits(db, "listing.frame_photo_kept")
    assert kept and 1 in kept[-1]["positions"], kept


def test_launch_plan_refuses_a_fix_only_input_whoever_enqueued_it():
    st = chain()
    db, slug, version = st["db"], st["slug"], st["version"]
    JobQueue(db).enqueue("growth", "launch.plan",
                         {"slug": slug, "version": version, "rebuild": "lp-1",
                          "fix_only": True}, priority=0, idempotency_key="fo-lp-1")
    _drain(db, name="fo-lp")
    assert not [t for t, _s in _jobs(db, "lp-1") if t in ("marketing.schedule",
                                                           "store.publish")]
    assert _audits(db, "launch.fix_only_refused")


def test_an_ordinary_rebuild_still_runs_the_whole_chain():
    st = chain()
    db = st["db"]
    JobQueue(db).enqueue("publishing", "assets.build", {**st["inputs"], "rebuild": "full-1"},
                         priority=0, idempotency_key="fo-full-1")
    _drain(db, name="fo-full")
    assert "launch.plan" in [t for t, _s in _jobs(db, "full-1")], _jobs(db, "full-1")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
