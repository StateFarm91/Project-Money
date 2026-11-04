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


if __name__ == "__main__":
    main()
