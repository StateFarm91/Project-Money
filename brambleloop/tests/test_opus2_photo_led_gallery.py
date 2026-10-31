"""OPUS2-P0: P0-GALLERY-ASSEMBLY -- a disclosed set led by the unedited sample photograph.

`listing_set.certify_disclosed` refused a mixed set, so a Launch-0 gallery could not lead with
the owner's sample photograph even after W-PHYSFIX-PHOTO's photo-first ordering. These tests
drive the real chain (gate.certify, assets.build) for the Cloudline blanket, then add a
FIXTURE physical test and photograph. The full-make classifier arrives with W-PHYSFIX
(`risk_matrix.physical_class_of`); where a test needs it, a labelled stand-in is installed.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_photo_led_gallery.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import io
import os
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="opus2_photo_led_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    EtsyTaxonomySnapshot, Job, JobStatus, Listing, ListingAsset, ListingSetCertificateRecord,
    PatternVersion, Phase, PhysicalPhoto, PhysicalTest,
)
from brambleloop.gates import risk_matrix  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import eligibility as el  # noqa: E402
from brambleloop.publish import listing_set as LS  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

_STATE: dict = {}
GOOD = {k: True for k in LS.PHOTO_ATTESTATION}


def _db(name):
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    snap = FX.snapshot()
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    return db


def _run(db, agent, job_type, inputs, key):
    job = JobQueue(db).enqueue(agent, job_type, inputs, idempotency_key=key, priority=0)
    Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=[job_type],
           lease_seconds=900).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _release(name):
    """The blanket certified, its disclosed set built, its copy drafted -- a fresh DB."""
    from brambleloop.publish import disclosed_listing

    db = _db(name)
    cir = L.cir_for("cloudline_blanket")
    job = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "c")
    assert job.outputs.get("granted"), job.outputs
    with db.session() as s:
        rh = s.scalar(select(PatternVersion)).release_hash
    job = _run(db, "publishing", "assets.build", {"slug": cir.slug, "version": cir.version,
                                                  "release": rh, "rebuild": "x"}, "a")
    assert job.status is JobStatus.DONE, job.last_error
    with db.session() as s:
        s.add(Listing(product_slug=cir.slug, version=cir.version,
                      title="Cloudline Textured Baby Blanket | Crochet Pattern PDF",
                      description=("A worsted-weight baby blanket pattern.\n\n"
                                   + disclosed_listing.COPY_DISCLOSURE),
                      tags=["baby blanket crochet"], price_cad=7.5, state="draft"))
    return db, cir


def _hero_bytes(db, cir):
    """A FIXTURE 'photograph': the certified hero's pixels re-encoded, so it is a distinct
    file that reads at thumbnail size (a camera photo is not available offline)."""
    from brambleloop.publish import listing_asset

    rec = listing_asset.last(db, slug=cir.slug)
    hero = min(rec["frames"], key=lambda f: int(f["position"]))
    data = ArtifactStore().get(hero["image"]["sha256"], db=db)
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(out, format="JPEG", quality=92)
    return out.getvalue()


def _add_photo(db, cir, *, approved=True, unedited=True, passed=True, version=None):
    data = _hero_bytes(db, cir)
    stored = ArtifactStore().put(f"photos/{cir.slug}.jpg", data, "image/jpeg")
    with db.session() as s:
        t = PhysicalTest(product_slug=cir.slug, version=version or cir.version,
                         tester_ref="fixture-tester", passed=passed,
                         completed_at=datetime.now(timezone.utc),
                         measured={"evidence_class": "full_make"})
        s.add(t)
        s.flush()
        p = PhysicalPhoto(product_slug=cir.slug, version=cir.version, source="tester",
                          sha256=stored.sha256, rights_basis="tester assignment (fixture)",
                          taken_by="fixture-tester", physical_test_id=t.id,
                          detail={"unedited": unedited})
        s.add(p)
        s.flush()
        s.add(ListingAsset(product_slug=cir.slug, version=cir.version, position=99,
                           asset_class="PHYSICAL_PRODUCT_PHOTO", role="hero",
                           sha256=stored.sha256, approved=approved,
                           blocked_reasons=[] if approved else ["awaiting asset-truth review"],
                           claims={"physical_photo_id": p.id, "provenance": "camera",
                                   "leads_gallery": True}))
    return stored.sha256


class _FullMake:
    """Stand-in for W-PHYSFIX's `risk_matrix.physical_class_of` (not on this base)."""

    def __enter__(self):
        self.had = hasattr(risk_matrix, "physical_class_of")
        self.saved = getattr(risk_matrix, "physical_class_of", None)
        risk_matrix.physical_class_of = lambda m: (
            (risk_matrix.FULL_PHYSICAL_MAKE, "fixture") if m.get("evidence_class") == "full_make"
            else ("partial", "fixture"))

    def __exit__(self, *a):
        if self.had:
            risk_matrix.physical_class_of = self.saved
        else:
            del risk_matrix.physical_class_of


def _latest_cert(db, cir):
    with db.session() as s:
        row = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == cir.slug)
            .order_by(ListingSetCertificateRecord.id.desc()).limit(1))
        return dict(row.certificate or {}) if row is not None else None


def _verdict(db, cir):
    from brambleloop.publish import release_gates

    return release_gates.listing_set(db, slug=cir.slug, version=cir.version)


def test_photo_lead_frame_refuses_each_missing_proof_and_wrong_release_or_wording():
    base = {"asset_id": "p", "sha256": "a" * 64, "alt_text": "Photograph of a sample",
            "represented_variant": "single", "attestation": {**GOOD, "slug": "s", "version": "1"}}
    assert LS.PHOTO_ATTESTATION
    for k in LS.PHOTO_ATTESTATION:
        bad = {**base, "attestation": {**base["attestation"], k: False}}
        try:
            LS.photo_lead_frame(slug="s", version="1", photo=bad, listing_variant="single")
        except LS.ListingSetRefused as e:
            assert k in str(e)
        else:
            raise AssertionError(k)
    f = LS.photo_lead_frame(slug="s", version="1", photo=base, listing_variant="single")
    assert (f.position, f.job, f.purpose, f.kind, f.honesty_label) == (
        1, el.PROOF, el.PHYSICAL_PROOF, LS.PHOTO_LEAD, el.PHOTO_LABEL)
    for photo, variant, word in (
            ({**base, "attestation": {**base["attestation"], "version": "2"}}, "single",
             "another release"),
            ({**base, "represented_variant": "large"}, "single", "one sample is one size"),
            ({**base, "alt_text": "Digital render of the blanket"}, "single", "render")):
        try:
            LS.photo_lead_frame(slug="s", version="1", photo=photo, listing_variant=variant)
        except LS.ListingSetRefused as e:
            assert word in str(e), (word, str(e))
        else:
            raise AssertionError(word)


def test_without_a_lead_photo_the_disclosed_certificate_is_unchanged():
    db, cir = _release("plain")
    v = _verdict(db, cir)
    assert v["certificate"]["valid"] is True, v["reasons"]
    cert = _latest_cert(db, cir)
    kinds = {f.get("kind") for f in cert["frames"]}
    assert LS.PHOTO_LEAD not in kinds and LS.DISCLOSED_RENDER in kinds, kinds
    _STATE["plain_frames"] = len(cert["frames"])


def test_an_attested_approved_sample_photo_leads_and_every_render_keeps_its_disclosure():
    db, cir = _release("led")
    sha = _add_photo(db, cir)
    with _FullMake():
        v = _verdict(db, cir)
    assert v["certificate"]["valid"] is True, v["reasons"]
    cert = _latest_cert(db, cir)
    frames = sorted(cert["frames"], key=lambda f: f["position"])
    assert frames[0]["kind"] == LS.PHOTO_LEAD and frames[0]["sha256"] == sha
    assert frames[0]["honesty_label"] == "" and frames[0]["job"] == el.PROOF
    assert [f["position"] for f in frames] == list(range(1, len(frames) + 1))
    renders = [f for f in frames[1:] if f.get("kind") in (LS.DISCLOSED_RENDER,
                                                         LS.DISCLOSED_SUPPLEMENT)]
    assert renders and renders[0]["position"] == 2 and len(renders) == len(frames) - 1
    from brambleloop.publish.disclosed_listing import DISCLOSURE

    assert all(f["honesty_label"] in (DISCLOSURE, el.PREVIEW_LABEL) for f in renders)
    assert DISCLOSURE in cert["disclosures"]
    if "plain_frames" in _STATE:
        assert len(frames) == _STATE["plain_frames"] + 1


def test_an_unapproved_photo_or_one_without_the_full_make_classifier_never_leads():
    db, cir = _release("unapproved")
    _add_photo(db, cir, approved=False)
    with _FullMake():
        v = _verdict(db, cir)
    assert v["certificate"]["valid"] is False
    assert any(el.DATA_TRUTH in r for r in v["reasons"]), v["reasons"]
    db, cir = _release("noclassifier")
    _add_photo(db, cir)
    had = hasattr(risk_matrix, "physical_class_of")
    if not had:
        v = _verdict(db, cir)
        assert v["certificate"]["valid"] is False
        assert any("full_make" in r for r in v["reasons"]), v["reasons"]


def test_an_edited_photo_or_a_failed_make_never_leads():
    for kw, word in (({"unedited": False}, "unedited"), ({"passed": False}, "test_passed")):
        db, cir = _release(f"bad-{word}")
        _add_photo(db, cir, **kw)
        with _FullMake():
            v = _verdict(db, cir)
        assert v["certificate"]["valid"] is False
        assert any(word in r for r in v["reasons"]), (word, v["reasons"])


def test_the_upload_serves_the_photo_first_with_its_certified_alt_text():
    from brambleloop.runtime import etsy_ops

    db, cir = _release("upload")
    sha = _add_photo(db, cir)
    with _FullMake():
        v = _verdict(db, cir)
    assert v["certificate"]["valid"] is True, v["reasons"]
    with db.session() as s:
        rh = s.scalar(select(PatternVersion)).release_hash
    got = etsy_ops.certified_images(db, cir.slug, cir.version, release=rh)
    assert got["problems"] == [], got["problems"]
    first = got["order"][0]
    assert first["sha256"] == sha and first["kind"] == LS.PHOTO_LEAD
    assert first["alt_text"].startswith("Photograph of a") and got["images"][0].alt_text \
        == first["alt_text"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
