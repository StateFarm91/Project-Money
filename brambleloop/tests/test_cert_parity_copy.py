"""Cluster W1b: creative parity, benchmark currency, listing copy and imagery, in the runtime.

The 2026-09-27 proof-chain audit (C-41, C-44, C-45, C-47) found each of these libraries
tested and either uncalled or called in a way that could not work:

  C-45  `_benchmark_quality` read the newest ten blind-review rows of any product, so with
        eleven in the catalogue one was permanently unjudged, and a months-old row counted.
  #67 #76 #218  the review compared five dimensions, ignored the dated benchmark set, named
        none of the MJs challenge dimensions and sent nothing back to development.
  #81   the escalation ladder was recorded and its free rung never enqueued.
  #41   the disclosure check ran before the Listing row existed, so it read UNMEASURED.
  #35 #36 #63 #68 #139 #203 #240  uncalled from the chain.

Every test here drives a registered handler through the worker (or the reader the handler
uses) and asserts the effect is persisted or enforced. Buyers, reviews and signals here are
fixtures; nothing is published and no model is asked anything.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_ART = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART.name

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, BenchmarkObservation, CultureSignal, Job, JobStatus, Listing,
)
from brambleloop.creative import blind_review as R  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402 - registers handlers
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.core.models import Phase  # noqa: E402
from brambleloop.visual import parity  # noqa: E402

SLUG = "hexagon-coaster-set"
KEY = "mjs_off_the_hook_designs"
_TMP = tempfile.mkdtemp()
_CHAIN: dict = {}


def _boot(path: str) -> Database:
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _chain_file() -> str:
    """One certified product through the whole post-certification chain, run once."""
    if not _CHAIN:
        from brambleloop.products.vessels import build_hexagon_coaster

        path = f"{_TMP}/chain.sqlite"
        db = _boot(path)
        JobQueue(db).enqueue("quality_director", "gate.certify",
                             {"cir": build_hexagon_coaster().to_dict()})
        w = Worker(db, "w1b-chain")
        for _ in range(100):
            if not w.run_once():
                break
        _CHAIN["path"] = path
    return _CHAIN["path"]


def _fresh_chain() -> Database:
    """A private copy of the chain database, so a test that mutates it mutates only itself."""
    import sqlite3

    src = _chain_file()
    dst = f"{_TMP}/copy-{datetime.now().timestamp()}.sqlite"
    # The sqlite backup API rather than a file copy: the chain's writes may still be in the
    # write-ahead log, which a copy of the main file would silently leave behind.
    with sqlite3.connect(src) as source, sqlite3.connect(dst) as target:
        source.backup(target)
    return Database(f"sqlite:///{dst}")


def _run(db: Database, agent: str, job_type: str, inputs: dict, *, key: str) -> Job:
    """Enqueue one job and run exactly it (and nothing it enqueues) through the worker."""
    JobQueue(db).enqueue(agent, job_type, inputs, priority=0, idempotency_key=key)
    w = Worker(db, f"w1b-{job_type}", phase=Phase.SHADOW, job_types=[job_type])
    for _ in range(5):
        if not w.run_once():
            break
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.idempotency_key == key))
        s.expunge(job)
        return job


def _audits(db: Database, action: str, artifact: str | None = None) -> list[dict]:
    with db.session() as s:
        q = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
        if artifact is not None:
            q = q.where(AuditLog.artifact == artifact)
        return [dict(r.detail or {}, _job_id=r.job_id) for r in s.scalars(q)]


def _jobs(db: Database, job_type: str) -> list[Job]:
    with db.session() as s:
        rows = list(s.scalars(select(Job).where(Job.job_type == job_type).order_by(Job.id)))
        for r in rows:
            s.expunge(r)
        return rows


def _seo_inputs(db: Database) -> dict:
    job = [j for j in _jobs(db, "listing.seo") if j.status == JobStatus.DONE][0]
    return dict(job.inputs)


def _observed_pod(db, pod: str, *, at: datetime, listings: int = 4, images: int = 3,
                  cards: bool = False, video: bool = True, media: int = 8) -> None:
    with db.session() as s:
        for i in range(listings):
            ref = f"{pod}-{i}-{at.date()}"
            s.add(BenchmarkListing(
                benchmark_key=KEY, listing_ref=ref, title=f"{pod} {i}", pod=pod,
                audit_state="audited", media_count=media,
                detail={"gallery_audited": True, "has_video": video}))
            shots = ("hero_styled", "detail_macro", "flat_lay", "in_use")
            for rank in range(images):
                observation = {"shot_type": shots[rank % len(shots)],
                               "thumbnail_readability": "reads clearly at grid scale",
                               "detail_coverage": "close stitch detail shown",
                               "gift_narrative": "framed as a gift for a new baby"}
                if cards:
                    observation["infographic_use"] = "size and materials card, clear"
                s.add(BenchmarkObservation(
                    benchmark_key=KEY, listing_ref=ref, kind="gallery_image_observation",
                    at=at, detail={"image": {"rank": rank + 1}, "observation": observation}))


def _frame(role: str = "hero", readable: bool | None = True) -> dict:
    return {"made": True, "role": role, "readable_at_grid": readable, "version": "1.0.0",
            "image_ref": f"ref-{role}"}


# ---- C-45: the reader parity uses ----------------------------------------------------


def test_c45_every_one_of_eleven_products_reads_its_own_review():
    """Eleven rows, one per catalogue product, written in catalogue order. The old reader
    scanned the newest ten rows of any product: the first product written (the reproduced
    case was winter-village-graphghan) was never found and stayed unjudged for ever."""
    db = _boot(f"{_TMP}/c45.sqlite")
    slugs = [s for s, _ in R.catalogue_slugs()]
    assert len(slugs) == 11
    slugs = ["winter-village-graphghan"] + [s for s in slugs if s != "winter-village-graphghan"]
    for slug in slugs:
        R.record(db, {"slug": slug, "materially_inferior": False, "verdict": R.NOT_INFERIOR,
                      "why": f"fixture: {slug} judged level",
                      "reviewed_at": datetime.now(timezone.utc).isoformat()})
    for slug in slugs:
        read = pipeline._benchmark_quality(db, slug)
        assert read is not None, f"{slug} is unjudged: the reader missed its row"
        assert read["slug"] == slug and read["materially_inferior"] is False
    # And the gate sees it: COMPETITIVE is judged for the product the old reader lost.
    out = parity.assess([], benchmark_quality=pipeline._benchmark_quality(db, slugs[0]))
    assert out["dimensions"][parity.COMPETITIVE]["verdict"] == parity.PASS


def test_c45_a_months_old_review_is_not_todays_comparison():
    """Adversarial: a favourable verdict from sixty days ago. The old reader returned it and
    parity passed COMPETITIVE on it; now it reads as stale and unjudged, and says why."""
    db = _boot(f"{_TMP}/c45-stale.sqlite")
    old = datetime.now(timezone.utc) - timedelta(days=60)
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=R.ACTION, artifact="pet-snuggle-mat",
                       at=old, detail={"slug": "pet-snuggle-mat", "materially_inferior": False,
                                       "verdict": R.NOT_INFERIOR, "why": "old and kind",
                                       "reviewed_at": old.isoformat()}))
    read = pipeline._benchmark_quality(db, "pet-snuggle-mat")
    assert read is not None and read["stale"] is True
    assert read["materially_inferior"] is None and read["recorded_verdict"] == R.NOT_INFERIOR
    out = parity.assess([], benchmark_quality=read)
    competitive = out["dimensions"][parity.COMPETITIVE]
    assert competitive["verdict"] == parity.UNJUDGED
    assert "days old" in competitive["why"]
    # A second product's fresh row does not stand in for it.
    R.record(db, {"slug": "spooky-garland", "materially_inferior": False,
                  "reviewed_at": datetime.now(timezone.utc).isoformat()})
    assert pipeline._benchmark_quality(db, "pet-snuggle-mat")["stale"] is True


def test_store_publish_reads_the_product_own_review_through_the_handler():
    """#71/#75 through store.publish: eleven other rows after this product's, and the
    listing.parity row still carries this product's verdict on COMPETITIVE."""
    db = _fresh_chain()
    R.record(db, {"slug": SLUG, "materially_inferior": True, "why": "fixture: behind",
                  "reviewed_at": datetime.now(timezone.utc).isoformat()})
    for slug, _ in R.catalogue_slugs():
        R.record(db, {"slug": slug, "materially_inferior": None, "why": "fixture",
                      "reviewed_at": datetime.now(timezone.utc).isoformat()})
    job = _run(db, "store_operator", "store.publish", {"slug": SLUG, "version": "1.0.0"},
               key="w1b-publish-own-review")
    assert job.status == JobStatus.DEAD and "SHADOW" in (job.last_error or "")
    row = [a for a in _audits(db, "listing.parity") if a["_job_id"] == job.id][0]
    assert row["dimensions"][parity.COMPETITIVE]["verdict"] == parity.FAIL
    assert row["dimensions"][parity.COMPETITIVE]["why"] == "fixture: behind"


# ---- #81: the free rung is executed, not only recorded ------------------------------------


def test_a_taken_deterministic_rung_enqueues_assets_build_once():
    db = _fresh_chain()
    R.record(db, {"slug": SLUG, "materially_inferior": True, "why": "fixture: inferior",
                  "reviewed_at": datetime.now(timezone.utc).isoformat()})
    before = len(_jobs(db, "assets.build"))
    job = _run(db, "store_operator", "store.publish", {"slug": SLUG, "version": "1.0.0"},
               key="w1b-escalate-1")
    row = [a for a in _audits(db, "listing.parity") if a["_job_id"] == job.id][0]
    assert row["escalation"]["taken"] == "deterministic_representation"
    builds = _jobs(db, "assets.build")
    assert len(builds) == before + 1, "the taken rung was recorded and not enqueued"
    assert builds[-1].inputs["rebuild"].startswith("parity-escalation:")
    assert _audits(db, "creative.escalation_taken", f"{SLUG}@1.0.0")
    # Same failure, same evidence: a retried publish does not queue it again.
    _run(db, "store_operator", "store.publish", {"slug": SLUG, "version": "1.0.0"},
         key="w1b-escalate-2")
    assert len(_jobs(db, "assets.build")) == before + 1
    # Release stays blocked: the ladder never lowers the bar.
    assert row["blocks_release"] is True


# ---- #67 / #76 / #218: the review itself --------------------------------------------------


def test_review_is_built_on_the_dated_benchmark_set_and_refuses_a_stale_one():
    db = _boot(f"{_TMP}/stale-set.sqlite")
    _observed_pod(db, "blankets", at=datetime.now(timezone.utc) - timedelta(days=90),
                  media=2, images=2, video=False)
    frames = [_frame("hero"), _frame("detail")]
    result = R.review(db, slug="autumn-oak-mosaic-throw", pod="blankets", frames=frames)
    assert result["benchmark_set"]["usable"] is False
    assert result["benchmark_set"]["refused"] == "stale"
    assert result["verdict"] == R.UNKNOWN and result["materially_inferior"] is None
    assert "current sample" in result["why"]

    fresh = _boot(f"{_TMP}/fresh-set.sqlite")
    _observed_pod(fresh, "blankets", at=datetime.now(timezone.utc) - timedelta(days=2),
                  media=2, images=2, video=False)
    ok = R.review(fresh, slug="autumn-oak-mosaic-throw", pod="blankets", frames=frames)
    assert ok["benchmark_set"]["usable"] is True
    assert ok["benchmark_set"]["set"]["current"] is True
    assert ok["benchmark_set_comparison"]["pod"] == "blankets"
    assert ok["verdict"] == R.NOT_INFERIOR


def test_the_missing_67_dimensions_are_compared_and_can_put_us_behind():
    """Adversarial: benchmark galleries that teach with information cards, against a
    listing of ours with none on file. Information density is judged and behind."""
    db = _boot(f"{_TMP}/density.sqlite")
    _observed_pod(db, "blankets", at=datetime.now(timezone.utc) - timedelta(days=1),
                  media=2, images=2, video=False, cards=True)
    frames = [_frame("hero"), _frame("detail")]
    result = R.review(db, slug="s", pod="blankets", frames=frames, cards=[])
    dims = result["comparison"]["dimensions"]
    for name in ("finished_result_clarity", "information_density", "consistency",
                 "visual_polish", "physical_proof"):
        assert name in dims, name
    assert dims["information_density"]["state"] == "behind"
    # With cards on file the same listing is level on it.
    level = R.review(db, slug="s", pod="blankets", frames=frames,
                     cards=[{"asset_class": "INFOGRAPHIC", "role": "size"},
                            {"asset_class": "PATTERN_PREVIEW", "role": "pattern_preview"}])
    assert level["comparison"]["dimensions"]["information_density"]["state"] == "level"


def test_the_mjs_challenge_names_its_eight_dimensions():
    db = _boot(f"{_TMP}/challenge.sqlite")
    _observed_pod(db, "blankets", at=datetime.now(timezone.utc), media=8)
    result = R.review(db, slug="s", pod="blankets", frames=[_frame("hero")])
    challenge = result["mjs_challenge"]["dimensions"]
    assert set(challenge) == {"concept_desirability", "distinctiveness", "product_clarity",
                              "thumbnail_strength", "styling", "apparent_craftsmanship",
                              "giftability", "purchase_confidence"}
    # Giftability cannot be judged from our side and says which judge it needs, while
    # carrying the benchmark's recorded reads.
    assert challenge["giftability"]["state"] == "unjudged"
    assert challenge["giftability"]["theirs_reads"]
    assert result["verdict"] == R.INFERIOR and result["returns_to_development"] is True


def test_an_inferior_product_is_returned_to_creative_development_by_the_handler():
    """#218 through creative.blind_review: the handler re-queues the product's photography
    job with the finding, once per day, and records the return."""
    db = _boot(f"{_TMP}/return.sqlite")
    slug = "autumn-oak-mosaic-throw"
    from brambleloop.publish import owned_photography

    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=owned_photography.ACTION, detail={
            "made": True, "slug": slug, "version": "1.0.0", "role": "hero",
            "method_version": owned_photography.METHOD_VERSION,
            "readable_at_grid": True, "image_ref": "fixture-hero"}))
    _observed_pod(db, "blankets", at=datetime.now(timezone.utc), media=8)
    job = _run(db, "creative_director", "creative.blind_review", {}, key="w1b-blind-1")
    assert job.status == JobStatus.DONE, job.last_error
    returned = {r["slug"]: r for r in job.outputs["returned_to_development"]}
    assert slug in returned
    queued = [j for j in _jobs(db, "assets.owned_photography")
              if (j.inputs or {}).get("slug") == slug]
    assert queued and queued[0].inputs["reason"] == "blind_review_inferior"
    assert _audits(db, "creative.returned_to_development", slug)
    # The row parity reads is this run's, current, and inferior.
    read = pipeline._benchmark_quality(db, slug)
    assert read["materially_inferior"] is True and read["method_version"] == R.METHOD_VERSION
    # Products with nothing to compare are not returned: UNKNOWN is looked at, not redone.
    assert "cloudline-baby-blanket" not in returned
    _run(db, "creative_director", "creative.blind_review", {}, key="w1b-blind-2")
    assert len([j for j in _jobs(db, "assets.owned_photography")
                if (j.inputs or {}).get("slug") == slug]) == 1


# ---- #41 / C-47: disclosures measured after the row exists, and at publish ----------------


def test_the_disclosure_check_measures_the_stored_listing_in_the_chain():
    db = _fresh_chain()
    checked = _audits(db, "listing.disclosure_checked", f"{SLUG}@1.0.0") + \
        _audits(db, "listing.disclosure_finding", f"{SLUG}@1.0.0")
    assert checked, "listing.seo never ran the disclosure check"
    assert checked[-1]["checked"] is True, "the check ran before the Listing row existed"
    assert checked[-1]["finding"] is False
    # listing.draft ran first and could only say UNMEASURED: that is the C-47 defect.
    draft = [j for j in _jobs(db, "listing.draft")][0]
    assert draft.outputs["disclosures"]["reading"] == "UNMEASURED"


def test_a_listing_whose_copy_lost_its_disclosure_is_blocked_at_publish():
    db = _fresh_chain()
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        row.title = "Hexagon Coasters"
        row.description = "Lovely coasters."
    job = _run(db, "store_operator", "store.publish", {"slug": SLUG, "version": "1.0.0"},
               key="w1b-publish-disclosure")
    row = [a for a in _audits(db, "listing.parity") if a["_job_id"] == job.id][0]
    assert row["disclosures"]["finding"] is True
    assert row["blocks_release"] is True and "#41" in row["why"]
    # Shadow is still the outermost reason.
    assert "SHADOW" in (job.last_error or "")


# ---- #35: every release classified, disclosures generated and enforced --------------------


def test_every_release_is_classified_and_its_disclosures_are_in_the_copy():
    db = _fresh_chain()
    classified = _audits(db, "listing.classified", f"{SLUG}@1.0.0")
    assert classified and classified[-1]["classification"]["ok"] is True
    owed = classified[-1]["classification"]["disclosures"]
    assert owed
    with db.session() as s:
        description = s.scalar(select(Listing.description)
                               .where(Listing.product_slug == SLUG))
    for sentence in owed:
        assert sentence in description, sentence
    # No policy snapshot exists here, so the class is recorded as not enabled -- and the
    # publish-time re-check blocks on it rather than assuming the reading is current.
    assert classified[-1]["class_enablement"]["enabled"] is False
    job = _run(db, "store_operator", "store.publish", {"slug": SLUG, "version": "1.0.0"},
               key="w1b-publish-class")
    row = [a for a in _audits(db, "listing.parity") if a["_job_id"] == job.id][0]
    assert row["classification"]["ok"] is False and "#35" in row["why"]


def test_a_generated_hero_photograph_is_refused_by_the_policy_gate_in_listing_seo():
    """Adversarial: an AI-generated product photograph on file in the hero role. Labelled or
    not, it is a picture of an object that does not exist, and listing.seo blocks."""
    db = _fresh_chain()
    from brambleloop.publish import owned_photography

    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=owned_photography.ACTION, detail={
            "made": True, "slug": SLUG, "version": "1.0.0", "role": "hero",
            "method_version": owned_photography.METHOD_VERSION, "generated": True,
            "disclosed_as_illustration": True, "image_ref": "fixture-generated-hero"}))
    job = _run(db, "listing", "listing.seo", _seo_inputs(db), key="w1b-seo-generated")
    assert job.status == JobStatus.DONE
    assert job.outputs["ok"] is False
    assert any("POLICY_CLASSIFICATION" in b for b in job.outputs["blocking"])


# ---- #36: provenance stored when images are built -----------------------------------------


def test_image_provenance_is_stored_by_assets_build():
    db = _fresh_chain()
    rows = _audits(db, "assets.image_provenance", f"{SLUG}@1.0.0")
    assert rows, "record_image was never called by assets.build"
    images = rows[-1]["images"]
    assert len(images) >= 6
    for image in images:
        assert image["pattern_version"] == "1.0.0"
        assert image["nature"] == "simulated" and image["is_proof"] is False
        assert image["ai_assisted"] is False and image["colourway"]
    assert rows[-1]["proof"]["has_physical_proof"] is False
    from brambleloop.commerce import buyer_trust

    assert buyer_trust.gallery_proof_on_file(db, slug=SLUG)["has_physical_proof_reading"] \
        is False
    # A photograph arriving on the render path is refused rather than guessed at.
    try:
        buyer_trust.records_for_frames([{"position": 9, "role": "hero",
                                         "asset_class": "PHYSICAL_PRODUCT_PHOTO"}],
                                       slug=SLUG, version="1.0.0")
    except buyer_trust.TrustRefused:
        pass
    else:
        raise AssertionError("a photograph was recorded without a consent basis")


# ---- #63 and #68: evidence-to-creative, and defects into fixtures --------------------------


def test_assets_build_walks_the_evidence_to_creative_flow():
    db = _fresh_chain()
    flows = _audits(db, "creative.evidence_flow", f"{SLUG}@1.0.0")
    assert flows, "brief_from_truth / check_creative / advance were never called"
    flow = flows[-1]
    assert flow["steps"] == ["compiled_twin_truth", "engineering_evidence", "creative_brief",
                             "conversion_creative", "independent_asset_truth",
                             "layout_commercial_policy_gates"]
    assert flow["creative"]["ok"] is True and flow["export_ready"] is True
    assert flow["brief"]["derived_from"].startswith("chart:")
    assert flow["independence"]["independent"] is True


def _rebuild(db: Database, key: str) -> Job:
    return _run(db, "publishing", "assets.build",
                {"slug": SLUG, "version": "1.0.0", "release": "", "rebuild": key}, key=key)


def test_creative_that_invents_a_stitch_is_blocked_and_sent_back_to_the_brief():
    db = _fresh_chain()
    original = release.build_frames

    def inventing(*a, **kw):
        frames = original(*a, **kw)
        frames[0].depicts_stitches = list(frames[0].depicts_stitches) + ["popcorn"]
        return frames

    release.build_frames = inventing
    try:
        job = _rebuild(db, "w1b-invent")
    finally:
        release.build_frames = original
    assert job.outputs["ok"] is False
    assert any(b.startswith("CREATIVE_INVENTED") for b in job.outputs["blocking_image_problems"])
    flow = [f for f in _audits(db, "creative.evidence_flow") if f["_job_id"] == job.id][0]
    assert flow["blocked_at"] == "conversion_creative"
    assert flow["restart"]["to"] == "creative_brief"


def test_a_visual_defect_becomes_a_fixture_and_a_recurrence_is_a_fixture_bug():
    db = _fresh_chain()
    original = release.check_frame_plan

    def flat_hero(frames):
        return list(original(frames)) + [
            "LISTING_HERO_FABRIC_FLAT: fixture -- the hero render has no internal contrast"]

    release.check_frame_plan = flat_hero
    try:
        first = _rebuild(db, "w1b-defect-1")
        second = _rebuild(db, "w1b-defect-2")
    finally:
        release.check_frame_plan = original
    assert first.outputs["ok"] is False and second.outputs["ok"] is False
    from brambleloop.publish import defects

    rows = defects.fixtures(db)
    kinds = [(r["class"], r["kind"]) for r in rows]
    assert (defects.WEAK_HERO, defects.FIRST) in kinds
    assert (defects.WEAK_HERO, defects.RECURRENCE) in kinds
    assert defects.WEAK_HERO in defects.fixtured_classes(db)
    assert all(r["reproduces_with"].startswith(f"assets.build {SLUG}@1.0.0") for r in rows)
    # The second build replayed the first build's fixture and it failed: the regression
    # was caught by the fixture, not rediscovered.
    blocked = [a for a in _audits(db, "assets.listing_images_blocked")
               if a["_job_id"] == second.id][0]
    assert blocked["fixture_replay"]["failed"]
    assert defects.history(db)["monotonic"] is True


# ---- #139: listing copy screened by the rights router ------------------------------------


def test_a_declared_catchphrase_in_the_copy_blocks_listing_seo_unless_cleared():
    db = _fresh_chain()
    with db.session() as s:
        title = s.scalar(select(Listing.title).where(Listing.product_slug == SLUG))
    phrase = " ".join(title.split("|")[0].split()[:2])  # a phrase the copy certainly carries
    with db.session() as s:
        s.add(CultureSignal(key="fixture-catchphrase", topic="fixture", domain="film",
                            lane="original_concept",
                            protected_tokens=[{"text": phrase, "asset_class": "slogan",
                                               "source": "fixture"}]))
    job = _run(db, "listing", "listing.seo", _seo_inputs(db), key="w1b-seo-rights")
    assert job.outputs["ok"] is False
    assert any(b.startswith("RIGHTS_DIRECT_USE") for b in job.outputs["blocking"])

    # With a recorded basis the signal is in the direct lane and the copy may carry it.
    with db.session() as s:
        row = s.scalar(select(CultureSignal).where(CultureSignal.key == "fixture-catchphrase"))
        row.lane = "direct_reference"
        row.basis = {"kind": "brambleloop_original", "recorded_by": "owner",
                     "evidence": "fixture: this phrase is our own coinage, recorded here"}
    job = _run(db, "listing", "listing.seo", _seo_inputs(db), key="w1b-seo-rights-2")
    assert job.outputs["ok"] is True, job.outputs.get("blocking")


# ---- #240: diversification applied in listing.seo ---------------------------------------


def test_listing_seo_applies_the_query_portfolio_to_its_tags():
    """The handler reads every other listing's tags, records the shared phrases and the
    catalogue reading, and keeps the original tags when no reachable alternative exists."""
    db = _fresh_chain()
    with db.session() as s:
        mine = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        tags = list(mine.tags)
        s.add(Listing(product_slug="fixture-rival", version="1.0.0", title="Rival",
                      description="rival listing", tags=tags[:3], price_cad=5.0))
    job = _run(db, "listing", "listing.seo", _seo_inputs(db), key="w1b-seo-diversify")
    assert job.outputs["ok"] is True, job.outputs.get("blocking")
    reading = job.outputs["query_portfolio"]
    assert reading["other_listing_tags"] == 3
    assert sorted(reading["shared_before"]) == sorted(tags[:3])
    # Never fewer slots: with every reachable query already spent, the tags stand.
    assert len(job.outputs["listing"]["tags"]) == len(tags)
    rows = [a for a in _audits(db, "listing.query_portfolio") if a["_job_id"] == job.id]
    assert rows and rows[0]["catalogue"]["measurable"] is True
    assert rows[0]["catalogue"]["listings"] == 2 and "stuffing" in rows[0]


def test_diversify_moves_slots_off_shared_phrases_when_alternatives_exist():
    """The helper listing.seo calls, with more reachable queries than slots: phrases a rival
    already spends a slot on are replaced, and the listing keeps every slot."""
    from brambleloop.commerce.search import Query, choose_tags

    db = _boot(f"{_TMP}/diversify.sqlite")
    queries = [Query(phrase=f"{a} {b}", demand=0.5 - i * 0.01, competition=0.2)
               for i, (a, b) in enumerate((a, b) for a in ("oak", "fern", "moss", "birch",
                                                           "cedar", "maple")
                                          for b in ("coaster", "mat", "doily", "trivet"))]
    tags = choose_tags(queries)
    with db.session() as s:
        s.add(Listing(product_slug="fixture-rival", version="1.0.0", title="Rival",
                      description="rival", tags=tags[:4], price_cad=5.0))
    new, reading = release._diversify_tags(db, "mine", queries, tags)
    assert reading["changed"] is True
    assert len(reading["shared_after"]) < len(reading["shared_before"]) == 4
    assert len(new) >= len(tags)
    # Adversarial: with no other listing the tags are untouched and the reading says why.
    same, why = release._diversify_tags(_boot(f"{_TMP}/diversify-empty.sqlite"), "mine",
                                        queries, tags)
    assert same == tags and why["changed"] is False


# ---- #203: the photography handler plans from shot_plan ----------------------------------


def test_the_model_photography_handler_records_the_shot_plan_it_renders_from():
    from brambleloop.products import builder
    from brambleloop.publish import model_photography

    blanket = builder.for_slug("autumn-oak-mosaic-throw")
    worn = dataclasses.replace(blanket, slug="fixture-beanie-hat")
    original = builder.for_slug
    builder.for_slug = lambda slug, version="1.0.0": worn if slug == worn.slug else original(
        slug, version)
    try:
        db = _boot(f"{_TMP}/shotplan.sqlite")
        job = _run(db, "publishing", "assets.model_photography", {"slug": worn.slug},
                   key="w1b-shotplan")
    finally:
        builder.for_slug = original
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["ran"] is False  # image generation is closed here
    plan = job.outputs["shot_plan"]
    assert plan["render_here"] == ["fit", "detail"]
    assert set(plan["met_by_assets_build"]) == {"construction", "evidence"}
    assert set(plan["uncovered"]) == {"hero", "scale"}
    assert _audits(db, model_photography.PLAN_ACTION, f"{worn.slug}@1.0.0")

    # Negative: a product-first form plans no model frame, and the sequence renders none.
    out = model_photography.sequence(None, blanket, None, work_dir=_TMP)
    assert out["made"] is False and out["shot_plan"]["render_here"] == []


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"\n  {sum(1 for n in globals() if n.startswith('test_')) - fails} passing, "
          f"{fails} failing")
    sys.exit(1 if fails else 0)
