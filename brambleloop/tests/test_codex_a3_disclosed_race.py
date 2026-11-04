"""Photo-led certificate issuance must not use revoked photo evidence."""
from unittest.mock import patch

from sqlalchemy import select

import test_opus2_photo_led_gallery as fixture
from brambleloop.core.models import ListingSetCertificateRecord, PhysicalPhoto
from brambleloop.publish import photo_asset_review, release_gates
from brambleloop.runtime import etsy_ops


def test_disclosed_certificate_refuses_revocation_before_record():
    db, cir = fixture._release("disclosed-race")
    fixture._add_photo(db, cir)
    original = release_gates._record_certificate
    calls = []

    def revoke_before_record(db_, cert, **kwargs):
        with db_.session() as session:
            photo = session.scalar(select(PhysicalPhoto).where(
                PhysicalPhoto.product_slug == cir.slug))
            photo.detail = {**photo.detail, "owner_attestation": {}}
        with patch.object(release_gates, "listing_set", return_value={}):
            calls.append(photo_asset_review.sweep(db_))
        return original(db_, cert, **kwargs)

    with patch.object(release_gates, "_record_certificate", side_effect=revoke_before_record):
        verdict = fixture._verdict(db, cir)
    assert calls, "the revocation must occur at the certificate-record boundary"
    assert not verdict["certificate"].get("valid")
    assert not verdict["certificate"].get("issued")
    with db.session() as session:
        assert not list(session.scalars(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == cir.slug,
            ListingSetCertificateRecord.state == "valid")))
    assert not etsy_ops.certified_frames(db, cir.slug, cir.version)["frames"]


def test_consumer_refuses_revoked_attestation_before_next_sweep():
    db, cir = fixture._release("consumer-stale")
    fixture._add_photo(db, cir)
    verdict = fixture._verdict(db, cir)
    assert verdict["certificate"].get("valid"), verdict
    with db.session() as session:
        photo = session.scalar(select(PhysicalPhoto).where(
            PhysicalPhoto.product_slug == cir.slug))
        photo.detail = {**photo.detail, "owner_attestation": {}}
    # No sweep here: the consuming boundary must re-read current evidence.
    output = etsy_ops.certified_frames(db, cir.slug, cir.version)
    assert not output["frames"] and output["problems"], output


if __name__ == "__main__":
    test_disclosed_certificate_refuses_revocation_before_record()
    test_consumer_refuses_revoked_attestation_before_next_sweep()
    print("PASS disclosed photo-led revocation during certificate recording")
