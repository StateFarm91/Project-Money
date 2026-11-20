"""ENG-VIS-GALLERY: a generated seven-frame FLUX gallery, certified and read back from Etsy.

The owner's P0 "PERFECT FLUX 3 LISTING IMAGES" (D-OWNER-FLUX-GALLERY), proven end to end:

  certified CIR -> US/UK PDFs (assets.build) -> CIR reference renders -> Laura + outfit
  conditioning -> 7 frames (stub FLUX) -> independent QA -> certified gallery
  (gallery_persist.certify_gallery -> release_gates.generated_listing_set) -> listing package
  -> Etsy draft (FakeEtsy, loopback) -> byte-for-byte read-back of every image and BOTH PDFs.

What is real and what is a test double (every double is labelled in its readings):

* **Real:** gate.certify, assets.build (US/UK PDFs, the disclosed set's CONTENTS preview),
  listing.seo, the durable JobQueue, every image_production stage on the generated-gallery
  route, the FLUX 3 request builder on its StubRenderer (references in order, Laura's
  canonical three, the outfit, the room), candidate_gates.evaluate, the release binding, the
  quality floor, the outfit registry, campaign consistency and naturalism, the eligibility
  gallery exception, gallery_persist, release_gates.listing_set, listing.package,
  store.publish and the read-back. `publish.motif_fidelity` runs its real deterministic
  verdict; only its vision transport is doubled (`judger`).
* **Test doubles (labelled `test_double` in every reading they make):** product truth on an
  in-scene frame (the V1 end-band rule keeps the real verifier UNKNOWN on scene frames of a
  banded blanket -- `test_v6_gallery_e2e` pins that), identity / anatomy / realism / body /
  outfit judges (`test_w4_ownerimg.StubJudges`), the vision transport, Laura's per-image
  publication approval (ENG-VIS-IDENTITY's gate, which production has not qualified), the
  generator's pixels (a listing-size synthetic flat lay of the CIR per frame), and Etsy.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_vis_gallery_e2e.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox, removed at exit
import hashlib
import io
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import test_v6_gallery_e2e as V6  # noqa: E402
import test_w4_fidelity as T  # noqa: E402
import test_w4_ownerimg as O  # noqa: E402

STUB = "test_double"
_S: dict = {}


# ---- labelled doubles ----------------------------------------------------------------------

class GalleryGenerator(V6.V6Generator):
    """The real FLUX 3 request builder on its StubRenderer; each frame's bytes are a distinct
    listing-size flat lay of the CIR. The generator's own receipt is passed through as the
    candidate's identity evidence (the provenance receipt)."""

    def generate(self, **kw):
        from brambleloop.creative import flux3_generator as FG

        before = len(self.stub.calls)
        out = self.real.generate(**kw)
        sent = self.stub.calls[before:]
        self.requests.append({"role": kw["role"], "stage": kw["stage"],
                              "refs": [V6._sha_of(p) for p in sent[0]["refs"]] if sent else [],
                              "prompt": sent[0]["prompt"] if sent else ""})
        self.n += 1
        if kw["role"] == FG.IDENTITY_ANCHOR_ROLE:
            data = O.png(1024, 1024)
        else:
            data = T.flat_lay(self.cir, rotate=(self.n * 1.7) % 6 - 3,
                              fill=0.62 + (self.n % 7) * 0.02)
        receipt = dict(out.get("identity_evidence") or {})
        receipt.setdefault("request", {})
        if isinstance(receipt["request"], dict) and not receipt["request"].get(
                "request_sha256"):
            receipt["request"]["request_sha256"] = hashlib.sha256(
                (sent[0]["prompt"] if sent else str(self.n)).encode()).hexdigest()
        return {"data": data, "provider": "stub", "model": "stub-flux-3",
                "prompt": out["prompt"], "cost_cad": 0.0, "latency_s": 0.01,
                "identity_evidence": receipt}


def _motif_judger(cir, *, colours_seen=None):
    """The motif-fidelity vision transport, doubled: it describes what a faithful frame shows
    (the chart's own motif and colour count), in motif_fidelity's closed vocabulary.
    `publish.motif_fidelity.judge` decides in code. `colours_seen` makes it describe a frame
    with the wrong colour count, for the failing-frame test."""
    from brambleloop.publish import motif_fidelity as MF
    from brambleloop.publish.release_gates import _twin

    words = {1: "one", 2: "two", 3: "three", 4: "four"}

    def judger(image_ref, chart_path):
        want = MF.expected(cir, _twin(_S["db"], cir))
        n = colours_seen or want["colour_count"]
        return {"repeating_unit_shape": want["motif_named"] or "no visible repeat",
                "repeats_across": None,
                "colour_arrangement": f"{words.get(n, n)} colours in stripes",
                "same_pattern_as_chart": True, "fabric_readable": True}
    return judger


class GalleryJudges(V6.V6Judges):
    """V6's judges plus the two the route needs: motif fidelity (real verdict, doubled
    transport) and, for in-scene frames, a labelled product-truth double."""

    def __init__(self, db, vision, cir, *, fail_role=None, unknown_role=None):
        super().__init__(db, vision)
        self.cir = cir
        self.fail_role, self.unknown_role = fail_role, unknown_role

    def product_truth(self, c, bind):
        from brambleloop.visual import candidate_gates as CG
        from brambleloop.visual import image_production as IP

        if c.get("role") == IP.ANCHOR_ROLE:
            return super().product_truth(c, bind)
        self._seen("product_truth", c)
        if c.get("role") == self.fail_role:
            return CG._c(CG.FAIL, "test double: the frame shows the wrong colour count",
                         codes=["off_palette_colour"], test_double=True,
                         fidelity={"status": CG.FAIL, "release_hash": bind.get("release_hash")})
        if c.get("role") == self.unknown_role:
            return CG._c(CG.UNKNOWN, "test double: unreadable", test_double=True,
                         fidelity={"status": CG.UNKNOWN})
        # The real lifestyle verifier runs (anchor, region palette, the blind item reading
        # campaign consistency compares). Only V1's end-band rule -- an anchor's band
        # measurement is never promoted into a scene frame, so craft_texture stays UNKNOWN
        # on a banded blanket's scene -- is doubled, and only when it is the sole gap.
        from brambleloop.visual.vision_judges import blind_consistency

        fid = CG.fidelity_reading(self.db, c, bind, judge=self.vision,
                                  consistency=blind_consistency,
                                  locate=self.real.adapters().product_region)
        if fid["status"] == CG.UNKNOWN and fid.get("unknown") == ["craft_texture"] \
                and not fid.get("failed"):
            fid = {**fid, "status": CG.PASS, "test_double": "V1 end-band rule doubled",
                   "unknown": []}
        return CG._c(fid["status"], f"fidelity {fid['status']} (end-band rule: test double)",
                     test_double=True, codes=list(fid.get("codes") or []), fidelity=fid)

    def motif_fidelity(self, c, bind):
        from brambleloop.visual import candidate_gates as CG

        self._seen("motif_fidelity", c)
        out = CG.motif_reading(self.db, c, judger=_motif_judger(self.cir))
        return {**out, "test_double": "transport"}


@contextmanager
def laura_publication_double(db):
    """ENG-VIS-IDENTITY's per-image Laura publication approval, doubled for this run's own
    generated Laura frames only (production approves none today)."""
    from sqlalchemy import select

    from brambleloop.visual import canonical
    from brambleloop.visual.image_records import ImageCandidate

    real = canonical.PUBLICATION_APPROVED
    with db.session() as s:
        shas = {r.sha256 for r in s.scalars(select(ImageCandidate).where(
            ImageCandidate.laura_present.is_(True))) if r.sha256}
    canonical.PUBLICATION_APPROVED = frozenset(set(real) | shas)
    try:
        yield shas
    finally:
        canonical.PUBLICATION_APPROVED = real


# ---- the chain, once --------------------------------------------------------------------------

def run_gallery(db, *, fail_role=None, unknown_role=None):
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import laura_home as H
    from brambleloop.visual import room_references as RR
    from brambleloop.visual.launch_imagery import _listing_parts

    cir = _listing_parts(V6.CLOUD)[1][0]
    from sqlalchemy import select

    from brambleloop.core.models import PatternVersion

    with db.session() as s:
        rel = s.scalar(select(PatternVersion)).release_hash
    room = H.scene_for(cir.slug)["room"]
    manifest, _entry, _rb = V6._room_manifest(room)
    real_manifest = RR.MANIFEST
    RR.MANIFEST = manifest
    _S["db"] = db
    try:
        vision = V6.StubVision(cir)
        judges = GalleryJudges(db, vision, cir, fail_role=fail_role, unknown_role=unknown_role)
        gen = GalleryGenerator(db, cir)
        follow, _ = O.drain(db, generator=gen, judges=judges)
        first = IP.trigger(follow, slug=cir.slug, version=cir.version, release=rel,
                           route="generated_gallery")
        _, ran = O.drain(db, generator=gen, judges=judges, limit=160)
    finally:
        RR.MANIFEST = real_manifest
    return {"key": first["run_key"], "gen": gen, "judges": judges, "ran": ran, "cir": cir,
            "release": rel, "follow": follow}


def chain():
    if not _S.get("done"):
        import test_search_hero_publish as SH
        from brambleloop.core.db import Database
        from brambleloop.visual import gallery_persist as GP

        path, version, rh = SH._chain()
        db = Database(f"sqlite:///{path}")
        R = run_gallery(db)
        with laura_publication_double(db) as shas:
            R["status"] = GP.gallery_status(db, R["key"])
            R["certify"] = GP.certify_gallery(db, R["key"])
            R["laura_shas"] = shas
        _S.update(R=R, db=db, version=version, rh=rh, path=path, done=True)
    return _S


# ---- tests ------------------------------------------------------------------------------------

def test_1_seven_frame_flux_campaign_is_generated_from_cir_references_with_laura():
    from brambleloop.visual import image_production as IP

    S = chain()
    R, db = S["R"], S["db"]
    run = IP.get_run(db, R["key"])
    card = run["card"]
    assert card["route"] == "generated_gallery", card.get("route")
    roles = [r["role"] for r in card["roles"]]
    assert roles == ["hero", "colour_context", "lifestyle", "angle", "detail", "size",
                     "whats_included"], roles
    assert card["campaign_standard"]["ok"] is True, card["campaign_standard"]
    sent = {r["role"]: r for r in R["gen"].requests}
    assert set(sent) >= {"hero", "colour_context", "lifestyle", "angle", "detail", "size"}
    # Laura + outfit conditioning: Laura's frames carry her canonical references and outfit.
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        rows = list(s.scalars(select(ImageCandidate).where(
            ImageCandidate.run_key == R["key"])))
    laura = [r for r in rows if r.laura_present and r.role in ("lifestyle", "size")]
    assert laura and all(r.outfit_id for r in laura), [(r.role, r.outfit_id) for r in laura]
    assert len({r.outfit_id for r in laura}) == 1, "one outfit within the listing"
    for r in rows:
        if r.role in sent:
            kinds = [x["kind"] for x in r.references]
            assert "pattern_derived" in kinds, (r.role, kinds)     # CIR product references
    assert run["spent_cad"] == 0.0


def test_2_independent_qa_passes_every_frame_and_the_gallery_is_certified():
    from sqlalchemy import select

    from brambleloop.core.models import ListingAsset, ListingSetCertificateRecord

    S = chain()
    R, db = S["R"], S["db"]
    assert R["status"]["ok"] is True, [(b.get("role"), b["gate"], b["status"], b["why"][:200])
                                       for b in R["status"]["blockers"]]
    assert R["certify"]["certified"] is True, R["certify"].get("why")
    with db.session() as s:
        assets = list(s.scalars(select(ListingAsset).order_by(ListingAsset.position)))
        cert = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.state == "valid"))
    gen = [a for a in assets if (a.claims or {}).get("route") == "generated_gallery"]
    assert len(gen) == 6, [(a.position, a.role) for a in assets]
    for a in gen:
        c = a.claims
        assert c["is_photograph"] is False and c["is_render"] is True
        assert c["physical_sample_evidence"] is False
    frames = cert.certificate["frames"]
    assert [f["job"] for f in frames] == ["DESIRE", "COLOUR_CONTEXT", "LIFESTYLE", "ANGLE",
                                          "DETAIL", "SCALE", "CONTENTS"], frames
    assert all(f["kind"] == "generated_render" for f in frames[:6])
    assert frames[6]["kind"] == "disclosed_gallery_frame"
    assert {f["sha256"] for f in frames[:6]} == {a.sha256 for a in gen}


def test_3_package_draft_upload_and_byte_for_byte_readback_of_every_image_and_both_pdfs():
    from sqlalchemy import select

    import test_search_hero_publish as SH
    from brambleloop.core.models import (AuditLog, JobStatus, ListingSetCertificateRecord,
                                         Phase)
    from brambleloop.publish import listing_package as lp
    from brambleloop.runtime.pipeline import _certified_pdf_hashes
    from tests.fake_etsy import FakeEtsy

    S = chain()
    db, version, rh = S["db"], S["version"], S["rh"]
    slug = SH.SLUG
    certified = _certified_pdf_hashes(db, slug, version, rh)
    assert set(certified or {}) == {"US", "UK"}, certified
    with laura_publication_double(db):
        job = SH._run(db, "listing", "listing.package", {"slug": slug, "version": version})
        assert job.status is JobStatus.DONE, job.last_error
        pkg = lp.latest(db, slug, version)
        assert pkg is not None, pkg
        with FakeEtsy() as fake, SH._owner_and_fake(fake):
            SH._grant(db, version, rh)
            job = SH._run(db, "store_operator", "store.publish",
                          {"slug": slug, "version": version, "release": rh},
                          phase=Phase.LIMITED_PRODUCTION)
            assert job.status is JobStatus.DONE, job.last_error
            out = job.outputs
            assert out.get("published") is True, out
            assert out.get("read_back_verified") is True, out
            lid = out["etsy_listing_id"]
            assert fake.listings[lid]["state"] == "draft"
            got = sorted(f["sha256"] for f in fake.received_files[lid])
            assert got == sorted(certified.values()), (got, certified)
            with db.session() as s:
                rec = s.scalar(select(ListingSetCertificateRecord).where(
                    ListingSetCertificateRecord.state == "valid"))
                frames = sorted((int(f["position"]), f["sha256"])
                                for f in rec.certificate["frames"])
            uploaded = sorted((int(i["rank"]), i["sha256"])
                              for i in fake.received_images[lid])
            assert uploaded == frames and len(uploaded) == 7, (uploaded, frames)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "store.published"))
        rb = row.detail["read_back"]
    assert rb["verified"] is True and rb["files"]["verified"] is True, rb
    assert rb["images"]["verified"] is True, rb["images"]


def _fresh(**kw):
    import test_search_hero_publish as SH
    from brambleloop.core.db import Database

    path, _version, _rh = SH._chain()
    db = Database(f"sqlite:///{path}")
    return db, run_gallery(db, **kw)


def test_4_a_failing_frame_blocks_the_gallery_with_a_reason_and_repair_is_bounded():
    from sqlalchemy import select

    from brambleloop.core.models import ListingAsset
    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate

    db, R = _fresh(fail_role="detail")
    with laura_publication_double(db):
        st = GP.gallery_status(db, R["key"])
        out = GP.certify_gallery(db, R["key"])
    assert st["ok"] is False and out["certified"] is False
    mine = [b for b in st["blockers"] if b.get("role") == "detail"
            and b["gate"] == "product_fidelity"]
    assert mine and mine[0]["status"] == "FAIL", st["blockers"]
    b = mine[0]
    assert "wrong colour count" in b["why"] and b["owner"] == "ENG-VIS-GALLERY", b
    # bounded: the run's repair loop spent at most MAX_ATTEMPTS_PER_ROLE on the frame, and
    # the next action is a hold naming the bound, not another purchase
    with db.session() as s:
        tries = [r.attempt for r in s.scalars(select(ImageCandidate).where(
            ImageCandidate.run_key == R["key"], ImageCandidate.role == "detail"))]
    assert 1 < len(tries) <= IP.MAX_ATTEMPTS_PER_ROLE, tries
    assert b["next"]["kind"] == "hold" and "repair bound spent" in b["next"]["how"], b["next"]
    # every other frame passed: only the failing one is named
    assert {x.get("role") for x in st["blockers"]} <= {"detail", "gallery"}, st["blockers"]
    with db.session() as s:
        assert not [a for a in s.scalars(select(ListingAsset))
                    if (a.claims or {}).get("route") == "generated_gallery"]
    assert IP.get_run(db, R["key"])["spent_cad"] == 0.0


def test_5_unmeasured_never_counts_as_pass():
    from sqlalchemy import select

    from brambleloop.core.models import ListingAsset
    from brambleloop.visual import gallery_persist as GP

    db, R = _fresh(unknown_role="angle")
    with laura_publication_double(db):
        st = GP.gallery_status(db, R["key"])
        out = GP.certify_gallery(db, R["key"])
    assert out["certified"] is False
    mine = [b for b in st["blockers"] if b.get("role") == "angle"]
    assert mine, st["blockers"]
    assert {b["status"] for b in mine if b["gate"] == "product_fidelity"} == {"UNMEASURED"}
    assert all(b["next"]["kind"] in ("measure", "hold") for b in mine), mine
    measure = [b for b in mine if b["gate"] == "product_fidelity"][0]
    assert measure["next"]["kind"] == "measure" and "no new image" in measure["next"]["how"]
    with db.session() as s:
        assert not [a for a in s.scalars(select(ListingAsset))
                    if (a.claims or {}).get("route") == "generated_gallery"]
    # without the Laura double her frames are UNMEASURED on publication, never PASS
    st2 = GP.gallery_status(db, R["key"])
    pub = [b for b in st2["blockers"] if b["gate"] == "laura_publication"]
    assert pub and {b["status"] for b in pub} == {"UNMEASURED"}
    assert {b["owner"] for b in pub} == {"ENG-VIS-IDENTITY"}


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
