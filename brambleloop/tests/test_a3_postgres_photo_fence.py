"""Real PostgreSQL photo-source row-lock regression (disposable local DB only).

Set A3_TEST_POSTGRES_URL to a fresh localhost database named codex_photo_test.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import _tmp; _tmp.install()  # noqa: E702
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

import test_physfix_photo_first as T
import test_opus2_photo_asset_review as A
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import ListingAsset, PhysicalPhoto, PhysicalTest
from brambleloop.publish import photo_asset_review as par
from brambleloop.quality import tester_programme as tp


def main():
    url = os.environ.get("A3_TEST_POSTGRES_URL", "")
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgresql+psycopg2") or parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/codex_photo_test":
        raise RuntimeError("A3_TEST_POSTGRES_URL must point to local disposable codex_photo_test")
    db = Database(url, scratch=True)
    # The strict URL guard above limits this reset to the named disposable test DB.
    db.drop_all()
    db.create_all()
    Registry(db).seed_defaults()
    tp.record_agreement(db, handle_ref="tester-1", specialties=["home_decor"],
                        express_consent=True, consent_source="test fixture", relationship="none",
                        qualification="https://www.ravelry.com/projects/tester/basket")
    cir, release = T._certified_basket(db)
    T._render_gallery(db, cir)
    test_id = T._passed_full_make(db, cir)
    plan = T._upgrade(db, cir, test_id)
    with db.session() as s:
        frame = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == cir.slug,
                                                   ListingAsset.asset_class == par.PHOTO_CLASS))
        frame_id = frame.id
    result = par.review_frame(db, frame_id, reissue=False)
    assert result["approved"], result
    with db.session() as s:
        frames = list(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version)))
        for frame in frames:
            s.expunge(frame)
    with db.session() as locked:
        par._lock(locked, db)
        assert par.photo_snapshot_current(locked, db, cir.slug, cir.version, frames)
        for model, row_id, attr, value in (
            (PhysicalPhoto, plan["photo_id"], "rights_basis", "revoked"),
            (PhysicalTest, test_id, "passed", False),
        ):
            try:
                with db.session() as writer:
                    writer.execute(text("SET LOCAL lock_timeout = '250ms'"))
                    row = writer.get(model, row_id)
                    setattr(row, attr, value)
                    writer.flush()
            except OperationalError as exc:
                assert getattr(exc.orig, "pgcode", None) == "55P03", exc
            else:
                raise AssertionError(f"{model.__name__} writer crossed the held lock")
    # Exercise the actual certificate handler, injecting a competing source writer
    # at its photo check without replacing the real truth checks or their result.
    checks = par._checks
    attempted = []
    def concurrent_writer(*args, **kwargs):
        if not attempted:
            attempted.append(True)
            try:
                with db.session() as writer:
                    writer.execute(text("SET LOCAL lock_timeout = '250ms'"))
                    writer.get(PhysicalTest, test_id).passed = False
                    writer.flush()
            except OperationalError as exc:
                assert getattr(exc.orig, "pgcode", None) == "55P03", exc
            else:
                raise AssertionError("physical make changed during certificate issuance")
        return checks(*args, **kwargs)
    par._checks = concurrent_writer
    try:
        _, verdict = A._certify_without_touching_approval(db, cir, release)
    finally:
        par._checks = checks
    assert attempted and verdict["valid"] and verdict["issued"], verdict
    with db.session() as writer:
        writer.get(PhysicalTest, test_id).passed = False
    with db.session() as locked:
        par._lock(locked, db)
        assert not par.photo_snapshot_current(locked, db, cir.slug, cir.version, frames)
    from brambleloop.runtime import etsy_ops
    assert etsy_ops.certified_frames(db, cir.slug, cir.version, release=release)["problems"]
    print("PASS PostgreSQL photo and physical-test writers blocked; revoked make refused")
    every_evidence_writer_waits_for_the_review(db, url, cir, plan, test_id)


def every_evidence_writer_waits_for_the_review(db, url, cir, plan, test_id):
    """Review U5 F4: one PostgreSQL test per evidence source. While a review holds the photo
    lock (exclusive), each writer -- through its own session, as production writes -- is
    refused by `lock_timeout` (55P03). An unrelated write is not; two evidence writers never
    wait for each other (shared + shared)."""
    from brambleloop.core.models import (ArtefactProvenance, AuditLog,
                                         ListingSetCertificateRecord, PatternVersion, Product)
    from brambleloop.publish import photo_fence
    from brambleloop.publish import physical_upgrade as pu

    sep = "&" if "?" in url else "?"
    timed = Database(f"{url}{sep}options=-c%20lock_timeout%3D250ms", scratch=True)
    with db.session() as s:
        pv_id = s.scalar(select(PatternVersion.id).join(Product).where(
            Product.slug == cir.slug, PatternVersion.version == cir.version))
        photo_sha = s.get(PhysicalPhoto, plan["photo_id"]).sha256
    from brambleloop.core.artifacts import ArtifactStore

    sha2 = ArtifactStore().put("sample2.jpg", b"a second unedited camera file, F4",
                               "image/jpeg").sha256
    rec2 = pu.intake(db, slug=cir.slug, version=cir.version, source="tester", sha256=sha2,
                     rights_basis="tester_agreement", taken_by="tester-1",
                     physical_test_id=test_id, unedited=True)
    pu.attest_unedited(db, rec2["photo_id"], actor=T.OWNER, confirm=pu.UNEDITED_CONFIRMATION)

    def pv_certified(s):
        s.get(PatternVersion, pv_id).certified = False

    def pv_cir(s):
        row = s.get(PatternVersion, pv_id)
        row.cir_json = {**(row.cir_json or {}), "f4_probe": True}

    def provenance(s):
        s.add(ArtefactProvenance(artefact_class="listing_image", artefact_key="f4",
                                 provider="replicate", model="flux-pro", sha256=photo_sha))

    def sibling_leader(s):
        s.add(ListingAsset(product_slug=cir.slug, version=cir.version, position=99,
                           asset_class=par.PHOTO_CLASS, role="proof", sha256="9" * 64,
                           approved=False, claims={"leads_gallery": True},
                           blocked_reasons=[par.AWAITING]))

    def disclosed(s):
        s.add(AuditLog(actor="publishing", action=photo_fence.DISCLOSED_ACTION,
                       artifact=f"{cir.slug}@{cir.version}", detail={"probe": "F4"}))

    def certificate(s):
        s.add(ListingSetCertificateRecord(product_slug=cir.slug, version=cir.version,
                                          release_hash="r" * 64, state="valid",
                                          certificate={"frames": []}))

    writers = {"PatternVersion.certified": pv_certified, "PatternVersion.cir_json": pv_cir,
               "ArtefactProvenance insert": provenance,
               "sibling ListingAsset leads_gallery": sibling_leader,
               "disclosed render set": disclosed,
               "ListingSetCertificateRecord insert": certificate}
    with db.session() as locked:
        par._lock(locked, db)
        for label, write in writers.items():
            try:
                with timed.session() as w:
                    write(w)
                    w.flush()
            except OperationalError as exc:
                assert getattr(exc.orig, "pgcode", None) == "55P03", (label, exc)
            else:
                raise AssertionError(f"{label} crossed the held photo lock")
        # physical_upgrade.plan_upgrade renumbers frames in its own sessions
        try:
            pu.plan_upgrade(timed, rec2["photo_id"])
        except OperationalError as exc:
            assert getattr(exc.orig, "pgcode", None) == "55P03", exc
        else:
            raise AssertionError("plan_upgrade crossed the held photo lock")
        # an unrelated write is not fenced
        with timed.session() as w:
            w.add(AuditLog(actor="test", action="f4.unrelated", artifact="x", detail={}))
    # after the review: two evidence writers in flight at once never wait for each other
    with timed.session() as a:
        disclosed(a)
        a.flush()
        with timed.session() as b:
            provenance(b)
            b.flush()
    print("PASS F4: six evidence sources and plan_upgrade wait for the review; "
          "unrelated and concurrent writers do not")

if __name__ == "__main__":
    main()
