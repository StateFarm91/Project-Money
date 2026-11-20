"""ENG-VISUAL: the listing-image and PDF factory end to end, on a real certified fixture product.

The owner's chain: certified pattern -> PDF hashes -> FLUX images -> identity/product QA ->
finished gallery -> listing package -> authorised Etsy draft -> remote read-back of both PDF
files and every image. Proven here through the real handlers, with the provider and Etsy
replaced by doubles, and with `visual_pipeline` (/api/readback/evidence) asserted to count
exactly what happened. Nothing is forced: no verdict is written, no gate is patched except the
ones `test_search_hero_publish` already holds with their own tests (#75 parity, #126 grid,
the Launch-0 scope gate).

Two halves, because the code has two gallery paths today:

A. **Generated gallery** (`test_v6_gallery_e2e`): `assets.build` triggers
   `visual.image_production`; the real FLUX 3 generator builds every request on its
   StubRenderer (no network, no spend); identity, outfit and product QA run (identity and
   anatomy through labelled stub judges -- production has no qualified identity method); the
   7-frame campaign standard holds; the run stops at the owner card on named gates. The
   generated gallery is NOT certifiable and this test pins why (the audit's stage 8):
   `approve` refuses, and nothing reaches listing.package or Etsy.

B. **Certified gallery to Etsy** (`test_search_hero_publish`): `gate.certify` ->
   `assets.build` (US and UK PDFs, the disclosed render set, the listing-set certificate) ->
   `listing.seo` -> owner grant -> `store.publish` on `tests/fake_etsy` (loopback) ->
   read-back. Asserted: exactly the two certified PDFs arrived byte-for-byte (sha256 equal to
   the hashes `assets.build` recorded), both are listed by getAllListingFiles, every certified
   image arrived in order byte-for-byte, the read-back verified fields, files and images, and
   `listing.package` recorded its reading.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_visual_factory_e2e.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox, removed at exit
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
_A: dict = {}


def _half_a():
    if not _A:
        import test_v6_gallery_e2e as V6

        _A["V6"] = V6
        _A["R"] = V6._run()
    return _A["V6"], _A["R"]


# ---- A. generated gallery: stub FLUX -> identity/product QA -> owner card ------------------

def test_a1_stub_flux_images_are_generated_for_every_campaign_role_with_no_spend():
    V6, R = _half_a()
    from brambleloop.visual import image_production as IP

    run = R["run"]
    assert run["stage"] == "owner_card", run["stage"]
    assert run["spent_cad"] == 0.0
    roles = [r["role"] for r in R["gen"].requests]
    assert set(V6.GALLERY_ROLES) <= set(roles), roles
    assert IP.resolve_generator(R["db"]).paid is True     # production would be paid (gated)


def test_a2_the_gallery_meets_the_seven_frame_campaign_standard():
    _V6, R = _half_a()
    card = R["run"]["card"]
    assert len(card["roles"]) == 7, [r["role"] for r in card["roles"]]
    assert card["campaign_standard"]["ok"] is True, card["campaign_standard"]
    assert card["set_check"]["ok"] is True, card["set_check"]


def test_a3_identity_and_product_qa_ran_on_every_generated_frame_and_are_counted():
    from sqlalchemy import select

    from brambleloop.ops import production_evidence as pe
    from brambleloop.visual.image_records import ImageCandidate

    _V6, R = _half_a()
    db = R["db"]
    with db.session() as s:
        cands = [(c.role, c.laura_present, c.checks, c.technical_status)
                 for c in s.scalars(select(ImageCandidate).where(
                     ImageCandidate.run_key == R["key"]))]
    assert cands, "no candidate was recorded"
    laura = [c for c in cands if c[1]]
    assert laura, "no Laura frame in the cloudline campaign"
    for role, _l, checks, _st in laura:
        assert (checks.get("identity") or {}).get("status"), (role, checks.get("identity"))
    gallery = [c for c in cands if c[0] in _V6.GALLERY_ROLES]
    assert {c[0] for c in gallery} == set(_V6.GALLERY_ROLES), [c[0] for c in cands]
    for role, _l, checks, _st in gallery:
        assert (checks.get("product_truth") or {}).get("status"), role
    with db.session() as s:   # the fixture DB also holds the owner-upload fallback rows
        every = [(c.laura_present, c.technical_status)
                 for c in s.scalars(select(ImageCandidate))]
    vp = pe.visual_pipeline(db, now=NOW)
    assert vp["images"]["candidates"] == len(every) >= len(cands), vp["images"]
    assert vp["images"]["verified"] == sum(1 for _l, t in every if t == "PASS")
    assert vp["images"]["failed"] == sum(1 for _l, t in every if t == "FAIL")
    idn = vp["laura_identity_checks"]
    assert idn["laura_frames"] == sum(1 for lp_, _t in every if lp_) >= len(laura), idn
    assert idn["run"] + idn["not_run"] == idn["laura_frames"], idn
    # The run stopped on its named gates: one blocked gallery, grouped without its text.
    assert vp["galleries"]["blocked"] == 1 and vp["galleries"]["valid"] == 0, vp["galleries"]
    assert all(k.startswith("owner_card:") for k in vp["galleries"]["blocked_reasons_grouped"])
    assert "UNKNOWN (failed" not in json.dumps(vp)
    # Production has no qualified identity method: never claimed, whatever the stubs read.
    assert vp["laura_identity_method"]["production_qualified"] is False


def test_a4_the_generated_gallery_cannot_be_certified_and_reaches_no_listing_or_etsy():
    """The audit's stage-8 blocker, pinned: until the owner gates (identity method, F-852
    verified exception, Etsy policy, Laura publication) read PASS, a generated gallery is
    never certified, and no listing package or Etsy request is made from it."""
    from sqlalchemy import select

    from brambleloop.core.models import ListingAsset, ListingSetCertificateRecord
    from brambleloop.visual import image_production as IP

    _V6, R = _half_a()
    db = R["db"]
    dec = IP.approve(db, R["key"], decided_by="owner:test")
    assert dec["approved"] is False, dec
    with db.session() as s:
        assert list(s.scalars(select(ListingAsset))) == []
        assert list(s.scalars(select(ListingSetCertificateRecord))) == []
    blockers = R["run"]["card"]["publication_blockers"]
    assert any(b.startswith("F-852") for b in blockers), blockers
    assert any(b.startswith("Laura publication gate") for b in blockers), blockers


# ---- B. certified pattern -> PDFs -> certified gallery -> package -> FakeEtsy draft ---------

# D-OWNER-GALLERY-COMPLETE: a listing is uploaded only with its whole certified gallery
# (`shot_plans.CAMPAIGN_MIN_FRAMES`). The key basket's disclosed set plus its verified
# supplements certifies eight frames on the production path; the blanket's certifies six
# (no ANGLE/CONSTRUCTION for a flat piece), so the blanket is refused before Etsy (b0) and
# the complete gallery is the one that reaches a draft (b1).
FULL_SLUG = "housewarming-key-basket"
FULL_CATEGORY = "basket"


def test_b0_a_six_frame_disclosed_gallery_is_blocked_before_anything_reaches_etsy():
    import test_search_hero_publish as SH
    from brambleloop.core.db import Database
    from brambleloop.core.models import JobStatus, Phase
    from brambleloop.runtime import etsy_ops
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES
    from tests.fake_etsy import FakeEtsy

    path, version, rh = SH._chain()
    db = Database(f"sqlite:///{path}")
    cert = etsy_ops.certified_frames(db, SH.SLUG, version, release=rh)
    assert 0 < len(cert["frames"]) < CAMPAIGN_MIN_FRAMES, cert
    assert any(p.startswith("gallery incomplete") for p in cert["problems"]), cert
    with FakeEtsy() as fake, SH._owner_and_fake(fake):
        SH._grant(db, version, rh)
        job = SH._run(db, "store_operator", "store.publish",
                      {"slug": SH.SLUG, "version": version, "release": rh},
                      phase=Phase.LIMITED_PRODUCTION)
        assert job.status is JobStatus.DONE, job.last_error
        out = job.outputs
        assert out.get("published") is False and out.get("blocked") is True, out
        assert any("gallery incomplete" in r for r in out.get("reasons") or []), out
        assert SH._creates(fake) == [] and not fake.received_images, fake.requests
    db.engine.dispose()


def test_b1_certified_pdfs_and_every_image_reach_the_draft_and_are_read_back():
    from sqlalchemy import select

    import test_search_hero_publish as SH
    from brambleloop.core.db import Database
    from brambleloop.core.models import (
        AuditLog, JobStatus, ListingSetCertificateRecord, OperatingReading, Phase)
    from brambleloop.ops import production_evidence as pe
    from brambleloop.publish import listing_package as lp
    from brambleloop.runtime.pipeline import _certified_pdf_hashes
    from tests.fake_etsy import FakeEtsy

    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    path, version, rh = SH._chain(FULL_SLUG, FULL_CATEGORY)
    db = Database(f"sqlite:///{path}")
    slug = FULL_SLUG
    certified = _certified_pdf_hashes(db, slug, version, rh)
    assert set(certified or {}) == {"US", "UK"} and all(certified.values()), certified
    vp = pe.visual_pipeline(db, now=NOW)
    assert vp["certified_pdfs"]["with_us_and_uk_pdf_hashes"] == 1, vp["certified_pdfs"]
    assert vp["etsy_drafts"]["drafts"] == 0

    # The listing package is assembled and recorded from the certified rows.
    job = SH._run(db, "listing", "listing.package", {"slug": slug, "version": version})
    assert job.status is JobStatus.DONE, job.last_error
    pkg = lp.latest(db, slug, version)
    assert pkg is not None and pkg.get("state") in (lp.READY, lp.BLOCKED), pkg
    files = (pkg.get("files") or {}).get("pdf_sha256_by_terminology") or {}
    if files:
        assert files == certified, (files, certified)
    with db.session() as s:
        assert s.scalar(select(OperatingReading).where(OperatingReading.kind == lp.KIND))

    with FakeEtsy() as fake, SH._owner_and_fake(fake):
        SH._grant(db, version, rh, slug=slug)
        job = SH._run(db, "store_operator", "store.publish",
                      {"slug": slug, "version": version, "release": rh},
                      phase=Phase.LIMITED_PRODUCTION)
        assert job.status is JobStatus.DONE, job.last_error
        out = job.outputs
        assert out.get("published") is True and out.get("read_back_verified") is True, out
        assert out["files_attached_by_terminology"] == {"US": True, "UK": True}, out
        lid = out["etsy_listing_id"]
        assert len(SH._creates(fake)) == 1
        assert fake.listings[lid]["state"] == "draft"
        # Both PDFs: the exact certified bytes arrived, and Etsy lists both files.
        got = sorted(f["sha256"] for f in fake.received_files[lid])
        assert got == sorted(certified.values()), (got, certified)
        assert len(fake.files[lid]) == 2, fake.files[lid]
        # Every image: the certified set, in order, byte for byte.
        with db.session() as s:
            rec = s.scalar(select(ListingSetCertificateRecord).where(
                ListingSetCertificateRecord.state == "valid"))
            frames = sorted((int(f["position"]), f["sha256"])
                            for f in rec.certificate["frames"])
        uploaded = sorted((int(i["rank"]), i["sha256"]) for i in fake.received_images[lid])
        assert uploaded == frames and len(uploaded) >= CAMPAIGN_MIN_FRAMES, (uploaded, frames)
        assert len(fake.images[lid]) == len(frames)
    # The read-back is recorded, and the evidence counts it -- files and images both verified.
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "store.published",
                                              AuditLog.artifact == f"{slug}@{version}"))
        rb = row.detail["read_back"]
    assert rb["verified"] is True and rb["files"]["verified"] is True, rb
    assert rb["images"] is not None and rb["images"]["verified"] is True, rb["images"]
    vp = pe.visual_pipeline(db, now=NOW)
    dr = vp["etsy_drafts"]
    assert dr["drafts"] == 1 and dr["fully_read_back"] == 1, dr
    assert dr["releases"][0]["pdfs_attached"] == ["UK", "US"]
    assert vp["listing_packages"]["listing_ready"] + vp["listing_packages"]["blocked"] >= 1
    db.engine.dispose()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
