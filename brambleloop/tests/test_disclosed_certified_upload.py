"""D-FB-7 / D-FB-9: the disclosed render set through the one certified upload path, and the
presentation standard parity applies to it.

The real `gate.certify` + `assets.build` handlers on a temporary sqlite database, every
outbound socket refused, no model or image provider, no spend. One release is built once and
shared; each control works on its own copy of the evidence.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="disclosed_upload_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Job, JobStatus, Listing, ListingSetCertificateRecord, Phase,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

SLUG = "cloudline-baby-blanket"
_STATE: dict = {}


def _built():
    """One certified release with its disclosed set filed by the real assets.build handler."""
    if "db" not in _STATE:
        db = Database(f"sqlite:///{tempfile.mkdtemp()}/upload.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        cir = pipeline._engineered_cir(SLUG)
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key="cert", priority=0)
        Worker(db, "c", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
        job = JobQueue(db).enqueue("publishing", "assets.build",
                                   {"slug": cir.slug, "version": cir.version, "release": "",
                                    "rebuild": "disclosed"}, idempotency_key="d", priority=0)
        Worker(db, "b", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()
        with db.session() as s:
            assert s.get(Job, job.id).status == JobStatus.DONE
        _STATE.update(db=db, cir=cir)
    return _STATE["db"], _STATE["cir"]


def _set_copy(db, cir, description: str) -> None:
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == cir.slug,
                                             Listing.version == cir.version))
        if row is None:
            s.add(Listing(product_slug=cir.slug, version=cir.version,
                          title="Cloudline Baby Blanket - Digital Crochet Pattern",
                          description=description, price_cad=9.5, state="draft"))
        else:
            row.description = description


def _valid_certs(db, cir) -> list:
    with db.session() as s:
        return [r.certificate for r in s.scalars(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == cir.slug,
            ListingSetCertificateRecord.state == "valid"))]


def _disclosing_copy():
    from brambleloop.publish import disclosed_listing

    return ("A worsted-weight baby blanket pattern, written in US terms.\n\n"
            + disclosed_listing.COPY_DISCLOSURE)


# --------------------------------------------------------------------------- parity (D-FB-9)

def test_lifestyle_quality_reads_the_presentation_standard_for_a_verified_render():
    from brambleloop.publish import listing_asset
    from brambleloop.visual import parity

    db, cir = _built()
    _set_copy(db, cir, _disclosing_copy())
    frames = listing_asset.frames_for(db, slug=SLUG)
    assert all(f["presentation_qa"]["disclosure_in_copy"] is True for f in frames)
    verdict = parity.assess(frames)
    lq = verdict["dimensions"]["lifestyle_quality"]
    assert lq["verdict"] == "pass", lq
    # Still blocked: HERO (no vision description) and COMPETITIVE (no blind review) are
    # unchanged gates, and unjudged is not a pass.
    assert set(verdict["unjudged"]) == {"hero", "competitive_blind_review"}, verdict["unjudged"]
    assert verdict["blocks_release"] is True


def test_copy_without_the_disclosure_fails_lifestyle_quality():
    from brambleloop.publish import listing_asset
    from brambleloop.visual import parity

    db, cir = _built()
    _set_copy(db, cir, "A worsted-weight baby blanket pattern.")
    try:
        verdict = parity.assess(listing_asset.frames_for(db, slug=SLUG))
    finally:
        _set_copy(db, cir, _disclosing_copy())
    lq = verdict["dimensions"]["lifestyle_quality"]
    assert lq["verdict"] == "fail" and "disclosure_in_copy" in lq["why"], lq


def test_each_presentation_check_failing_or_missing_blocks():
    from brambleloop.publish import listing_asset
    from brambleloop.visual import parity

    db, cir = _built()
    base = listing_asset.frames_for(db, slug=SLUG)
    for check in parity.PRESENTATION_CHECKS:
        failed = copy.deepcopy(base)
        failed[1]["presentation_qa"][check] = False
        assert parity.assess(failed)["dimensions"]["lifestyle_quality"]["verdict"] == "fail", check
        missing = copy.deepcopy(base)
        missing[2]["presentation_qa"][check] = None
        assert parity.assess(missing)["dimensions"]["lifestyle_quality"]["verdict"] \
            == "unjudged", check
    absent = copy.deepcopy(base)
    del absent[0]["presentation_qa"]
    assert parity.assess(absent)["dimensions"]["lifestyle_quality"]["verdict"] == "unjudged"


def test_the_presentation_route_needs_structural_pass_and_gives_a_photo_nothing():
    from brambleloop.publish import listing_asset
    from brambleloop.visual import parity

    db, cir = _built()
    base = listing_asset.frames_for(db, slug=SLUG)
    # A tampered binding: structural truth is not PASS, so no presentation verdict.
    unbound = copy.deepcopy(base)
    unbound[0]["image"]["sha256"] = "0" * 64
    got = parity.presentation_quality(unbound[0])
    assert got["verdict"] == "unjudged" and "structural_truth" in got["unknown"], got
    # A photograph claiming the kind with a copied manifest and a perfect presentation record.
    photo = copy.deepcopy(base)
    for f in photo:
        f["generated"] = True
        f["provider"] = "some-image-model"
    verdict = parity.assess(photo)
    assert verdict["dimensions"]["lifestyle_quality"]["verdict"] != "pass"
    assert verdict["dimensions"]["product_truth"]["verdict"] != "pass"


# --------------------------------------------------------------------------- the upload path

class _FakeEtsy:
    """EtsyClient.publish's collaborators, recorded. The real publish() body runs."""

    def __init__(self):
        self.uploads = []

    def refusal(self):
        return None

    def create_draft(self, payload, **kw):   # J-product P-5: publish passes grant=
        return "L1"

    def attach_file(self, listing_id, *, filename, data):
        return True

    def upload_image(self, listing_id, *, filename, data, rank=1, alt_text=""):
        self.uploads.append({"filename": filename, "rank": rank, "alt_text": alt_text,
                             "bytes": len(data)})
        return {}

    # J-product P-5: publish() uploads through the private, grant-covered `_upload_image`.
    _upload_image = upload_image
    _attach_file = attach_file   # likewise the grant-covered private file upload


def _TransportTestGrant():
    from brambleloop.integrations.etsy import OwnerGrant

    class _VerifiedGrantForTransportTests(OwnerGrant):
        def __init__(self):
            super().__init__(None, action=OwnerGrant.PUBLISH, approval_id=1, slug=SLUG,
                             version="1")

        def refusal(self, *, action, listing_id=""):
            return None if action == self.action else "wrong action"

    return _VerifiedGrantForTransportTests()


def test_the_disclosed_set_is_certified_and_served_with_its_alt_text():
    import hashlib

    from brambleloop.integrations.etsy import EtsyClient
    from brambleloop.publish import disclosed_listing, release_gates
    from brambleloop.runtime import etsy_ops

    db, cir = _built()
    _set_copy(db, cir, _disclosing_copy())
    verdict = release_gates.listing_set(db, slug=SLUG, version=cir.version)
    assert verdict["kind"] == "disclosed_render", verdict
    assert not verdict["blocks_release"], verdict["reasons"]
    assert verdict["certificate"]["valid"] is True, verdict["certificate"]
    assert all(g == "passed" for f in verdict["frames"] for g in f["gates"].values())
    cert = _valid_certs(db, cir)[-1]
    rec = disclosed_listing.last_asset(db, slug=SLUG)
    assert [f["sha256"] for f in cert["frames"]] == [f["image"]["sha256"] for f in
                                                     sorted(rec["frames"],
                                                            key=lambda f: f["position"])]
    assert all(f["kind"] == "disclosed_render" and f["alt_text"].startswith(
        disclosed_listing.DISCLOSURE) for f in cert["frames"])
    assert cert["disclosures"] == [disclosed_listing.DISCLOSURE]

    served = etsy_ops.certified_images(db, SLUG, cir.version)
    assert served["problems"] == [], served["problems"]
    assert len(served["images"]) == 3
    for (name, data), entry, frame in zip(served["images"], served["images"], cert["frames"]):
        assert hashlib.sha256(data).hexdigest() == frame["sha256"]
        assert entry.alt_text == frame["alt_text"]
    assert all(o["alt_text"] for o in served["order"])  # bound in the publish digest

    # rc1-AUTH D3: the client itself requires the owner's grant. Without one nothing is sent.
    fake = _FakeEtsy()
    refused = EtsyClient.publish(fake, payload=None, filename="p.pdf", data=b"%PDF",
                                 images=served["images"])
    assert refused.published is False and fake.uploads == [], refused
    assert any("OwnerGrant" in p for p in refused.problems), refused.problems
    # The documented transport-test grant (tests/test_etsy.py): its database verification is
    # stubbed as passing because this test is about which bytes and alt text are uploaded,
    # not about the grant. The real sealed-grant verification is exercised in
    # tests/test_publish_execution_gate.py and tests/test_rc1_auth.py.
    outcome = EtsyClient.publish(fake, payload=None, filename="p.pdf", data=b"%PDF",
                                 images=served["images"], grant=_TransportTestGrant())
    assert outcome.images_uploaded == 3, outcome
    assert [u["alt_text"] for u in fake.uploads] == [f["alt_text"] for f in cert["frames"]]


def test_no_certificate_without_the_copy_disclosure_and_nothing_served():
    from brambleloop.publish import release_gates
    from brambleloop.runtime import etsy_ops

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/nocopy.sqlite")
    db.create_all()
    src, cir = _built()
    _copy_rows(src, db)
    _set_copy(db, cir, "A worsted-weight baby blanket pattern.")
    verdict = release_gates.listing_set(db, slug=SLUG, version=cir.version)
    assert verdict["blocks_release"] and not verdict["certificate"]["valid"]
    assert any("disclosure missing from the listing copy" in r for r in verdict["reasons"]), \
        verdict["reasons"]
    assert _valid_certs(db, cir) == []
    served = etsy_ops.certified_images(db, SLUG, cir.version)
    assert served["images"] == [] and served["problems"]


def test_the_upload_path_refuses_a_certificate_that_was_altered_or_bytes_that_changed():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import release_gates
    from brambleloop.runtime import etsy_ops

    db, cir = _built()
    _set_copy(db, cir, _disclosing_copy())
    release_gates.listing_set(db, slug=SLUG, version=cir.version)
    # 1. alt text edited in the certificate after issue: no longer the filed alt text.
    with db.session() as s:
        row = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == SLUG,
            ListingSetCertificateRecord.state == "valid"))
        original = copy.deepcopy(row.certificate)
        body = copy.deepcopy(row.certificate)
        body["frames"][0]["alt_text"] = "A photograph of the finished blanket."
        row.certificate = body
    served = etsy_ops.certified_images(db, SLUG, cir.version)
    assert served["images"] == [] and served["problems"], served
    # 2. the kind stripped: the disclosed bytes no longer carry a certified alt text.
    with db.session() as s:
        row = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == SLUG,
            ListingSetCertificateRecord.state == "valid"))
        body = copy.deepcopy(original)
        for f in body["frames"]:
            f.pop("kind", None)
            f.pop("alt_text", None)
        row.certificate = body
    served = etsy_ops.certified_images(db, SLUG, cir.version)
    assert served["images"] == [] and any("did not certify as one" in p
                                          for p in served["problems"]), served
    with db.session() as s:
        row = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == SLUG,
            ListingSetCertificateRecord.state == "valid"))
        row.certificate = original
    assert etsy_ops.certified_images(db, SLUG, cir.version)["problems"] == []
    # 3. the stored bytes changed on disk under their hash: refused, never uploaded.
    sha = original["frames"][1]["sha256"]
    store = ArtifactStore()
    path = Path(store.root) / sha[:2] / sha
    saved = path.read_bytes()
    try:
        path.write_bytes(saved[:-10] + b"0123456789")
        served = etsy_ops.certified_images(db, SLUG, cir.version)
        assert served["images"] == [] and served["problems"], served
    finally:
        path.write_bytes(saved)


def _copy_rows(src, dst) -> None:
    """The certified release and the disclosed set, copied into a fresh database."""
    from brambleloop.core.models import (
        ArtefactProvenance, AuditLog, DurableArtifact, ListingAsset, PatternVersion, Product,
    )

    with src.session() as s:
        rows = {m: [{c.name: getattr(r, c.name) for c in m.__table__.columns}
                    for r in s.scalars(select(m))]
                for m in (Product, PatternVersion, ListingAsset, AuditLog, ArtefactProvenance,
                          DurableArtifact)}
    with dst.session() as s:
        for m, items in rows.items():
            for item in items:
                if "job_id" in item:
                    item["job_id"] = None  # the jobs table is not copied
                s.add(m(**item))


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    sys.exit(bool(failures))
