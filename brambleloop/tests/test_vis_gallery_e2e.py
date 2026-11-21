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
  generator's pixels (a listing-size synthetic flat lay of the CIR per frame), Etsy, and
  the for-sale admission in `run_gallery` (b17-c A3: the fixture's blanket has real
  first-customer blockers, so its admission is doubled there and labelled `test_double`;
  test_9 runs the REAL admission on a separate chain and proves no paid call is made).

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
        run = self.current_run_key          # read before the call (the generator clears it)
        out = self.real.generate(**kw)
        sent = self.stub.calls[before:]
        self.requests.append({"role": kw["role"], "stage": kw["stage"],
                              "run": run,
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


def _motif_judger(db, cir, *, colours_seen=None):
    """The motif-fidelity vision transport, doubled: it describes what a faithful frame shows
    (the chart's own motif and colour count), in motif_fidelity's closed vocabulary.
    `publish.motif_fidelity.judge` decides in code. `colours_seen` makes it describe a frame
    with the wrong colour count, for the failing-frame test."""
    from brambleloop.publish import motif_fidelity as MF
    from brambleloop.publish.release_gates import _twin

    words = {1: "one", 2: "two", 3: "three", 4: "four"}

    def judger(image_ref, chart_path):
        want = MF.expected(cir, _twin(db, cir))
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

    # The person judges are StubJudges; every reading they make is labelled a test double so
    # production evidence never counts it as an independent verification.
    def _label(self, out):
        return {**out, "test_double": True}

    def identity(self, c):
        return self._label(super().identity(c))

    def anatomy(self, c):
        return self._label(super().anatomy(c))

    def realism(self, c):
        return self._label(super().realism(c))

    def body_proportions(self, c):
        return self._label(super().body_proportions(c))

    def outfit_consistency(self, c, outfit):
        return self._label(super().outfit_consistency(c, outfit))

    def motif_fidelity(self, c, bind):
        from brambleloop.visual import candidate_gates as CG

        self._seen("motif_fidelity", c)
        out = CG.motif_reading(self.db, c, judger=_motif_judger(self.db, self.cir))
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
    real_admission = IP.sale_admission
    IP.sale_admission = lambda *a, **k: {
        "admitted": True, "test_double": True,
        "why": "test_double: for-sale admission doubled for the gallery fixture (test_9 "
               "covers the real admission)"}
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
        IP.sale_admission = real_admission
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
    sent = {r["role"]: r for r in R["gen"].requests if r["run"] == R["key"]}
    # generated in this run, or recovered first from an image already made for the release
    from brambleloop.visual import gallery_recovery as GR

    recovered = {role for role in ("lifestyle", "size") if GR.already(db, R["key"], role)}
    assert set(sent) | recovered >= {"hero", "colour_context", "lifestyle", "angle", "detail",
                                     "size"}, (sorted(sent), recovered)
    # Laura + outfit conditioning: Laura's frames carry her canonical references and outfit.
    from sqlalchemy import select

    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        rows = list(s.scalars(select(ImageCandidate).where(
            ImageCandidate.run_key == R["key"])))
    laura = [r for r in rows if r.laura_present and r.role in ("lifestyle", "size")]
    assert laura and all(r.outfit_id for r in laura), [(r.role, r.outfit_id) for r in laura]
    assert len({r.outfit_id for r in laura}) == 1, "one outfit within the listing"
    assert rows
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
            # BATCH19D: D-OWNER-SALE-PIPELINE (HARD RULE) publishes only a release READY for
            # sale, so the real sale chain runs first: the agents' launch decision, then every
            # `sale.pipeline` stage (gallery -> premium PDFs built with the certified gallery
            # -> certified against D-OWNER-PDF-STANDARD -> attached -> READY). Nothing in it
            # is doubled beyond the gates `_owner_and_fake` already holds.
            premium = _drive_sale_pipeline(db, slug, version, rh)
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
            # The files sent are the certified premium editions, each certificate bound to
            # the `assets.build` hash of the same terminology for this release.
            got = sorted(f["sha256"] for f in fake.received_files[lid])
            assert got == sorted(premium["sha"].values()), (got, premium["sha"])
            assert premium["base"] == certified, (premium["base"], certified)
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
    S["published"] = True


def _drive_sale_pipeline(db, slug, version, rh) -> dict:
    """The real launch decision and the real sale-pipeline stages for this release, in order,
    until the run stops. Returns the certified premium editions' hashes and the base
    (`assets.build`) hashes their certificates are bound to."""
    import test_search_hero_publish as SH
    from brambleloop.core.models import JobStatus
    from brambleloop.publish import sale_pipeline as SPL
    from brambleloop.publish.sale_pipeline import PdfCertificate

    job = SH._run(db, "growth", "launch.plan", {"slug": slug, "version": version,
                                                 "release": rh})
    assert job.status is JobStatus.DONE, job.last_error
    SPL.ensure_tables(db)
    queued: list[dict] = []
    stage, ran = "admission", []
    for _ in range(len(SPL.STAGES) + 2):
        queued.clear()
        out = SPL.run_stage(db, {"slug": slug, "version": version, "release": rh,
                                 "stage": stage},
                            follow=lambda inputs, key: queued.append(inputs),
                            start_images=lambda *a, **k: None)
        ran.append((stage, out.get("state"), out.get("blocker")))
        state = (SPL.get(db, slug, version, rh) or {}).get("state")
        nxt = queued[0]["stage"] if queued else SPL.NEXT_STAGE.get(state)
        if state == SPL.READY or not nxt or nxt == stage:
            break
        stage = nxt
    certs = SPL.pdf_certificates(db, slug, version, rh)
    assert certs["both_pass"] is True, (certs, ran)
    with db.session() as s:
        base = {t: s.get(PdfCertificate, e["certificate_id"]).base_pdf_sha256
                for t, e in certs["editions"].items()}
    return {"sha": {t: e["pdf_sha256"] for t, e in certs["editions"].items()}, "base": base,
            "ran": ran}


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


def test_6_recovery_first_prior_images_are_rejudged_before_any_new_purchase():
    """assets.build starts the release's campaign run and its FLUX-gallery run. Images the
    campaign run already made for a slot the gallery shares (same release, role, Laura and
    outfit) are re-judged under the route and recovered; only the rest are generated."""
    from sqlalchemy import select

    from brambleloop.visual import gallery_recovery as GR
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate

    S = chain()
    R, db = S["R"], S["db"]
    rec = IP._stage_data(db, R["key"]).get("_recovery") or {}
    assert set(rec) >= {"lifestyle", "size"}, rec
    with db.session() as s:
        rows = {r.id: r for r in s.scalars(select(ImageCandidate))}
    for role in ("lifestyle", "size"):
        got = GR.already(db, R["key"], role)
        assert got and got["technical_status"] == "PASS", (role, got)
        src = rows[got["recovered_from"]]
        mine = rows[got["candidate_id"]]
        assert src.run_key != R["key"] and src.sha256 == mine.sha256, role
        assert mine.method == "recovered" and mine.cost_cad == 0.0
        assert mine.checks["_recovered"]["from_candidate"] == src.id
        assert mine.checks["motif_fidelity"]["status"] == "PASS"   # re-judged under the route
        # nothing was bought for the recovered slot in the gallery run
        assert not [q for q in R["gen"].requests if q["run"] == R["key"]
                    and q["role"] == role], role
    # a slot whose Laura/outfit/role differs is never recovered (generated instead)
    assert not GR.already(db, R["key"], "colour_context")
    assert [q for q in R["gen"].requests if q["run"] == R["key"]
            and q["role"] == "colour_context"]


def test_7_production_evidence_counts_the_gallery_from_rows():
    from brambleloop.ops import production_evidence as pe
    from datetime import datetime, timezone

    S = chain()
    db = S["db"]
    if not S.get("published"):
        test_3_package_draft_upload_and_byte_for_byte_readback_of_every_image_and_both_pdfs()
    vp = pe.visual_pipeline(db, now=datetime(2026, 11, 20, tzinfo=timezone.utc))
    g = vp["generated_galleries"]
    assert g["runs"] == 1, g
    im = g["images"]
    assert im["generated"] + im["recovered"] == 6 and im["recovered"] == 2, im
    # every PASS here used labelled test doubles: none is an independent verification
    assert im["independently_verified"] == 0 and im["verified_with_test_doubles"] == 6, im
    assert g["laura_identity"]["frames"] == 2, g["laura_identity"]
    assert g["laura_identity"]["identity_passed"] == 0          # stub identity never counts
    assert g["laura_identity"]["identity_held"] == 2
    assert g["completed_seven_image_galleries"] == 1, g
    assert g["awaiting_publication"] == 0 and g["etsy_drafts_verified"] == 1, g
    assert g["spent_cad"] == 0.0 and g["cost_per_completed_gallery_cad"] == 0.0, g
    assert vp["certified_pdfs"]["with_us_and_uk_pdf_hashes"] >= 1
    assert vp["etsy_drafts"]["fully_read_back"] >= 1
    import json

    text = json.dumps(g)
    assert S["R"]["key"] not in text and "cloudline" not in text      # counts only


def test_8_the_listing_set_rejudges_on_every_call_and_tampering_blocks_it():
    """After certification, `release_gates.listing_set` (what store.publish asks) re-judges the
    selected frames from their records: a reading that drops to UNKNOWN, a missing CONTENTS
    preview or bytes that differ from the selection each block the set."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    import test_search_hero_publish as SH
    from brambleloop.core.models import AuditLog
    from brambleloop.publish import release_gates as RG
    from brambleloop.visual.image_records import ImageCandidate

    S = chain()
    db, version = S["db"], S["version"]
    with laura_publication_double(db):
        ok = RG.listing_set(db, slug=SH.SLUG, version=version, issue=False)
        assert ok["kind"] == "generated_gallery" and ok["blocks_release"] is False, ok["reasons"]
        # 1. one frame's motif reading becomes UNKNOWN
        sel = RG.generated_selection(db, SH.SLUG, version)
        cid = next(f["candidate_id"] for f in sel["frames"] if f["role"] == "detail")
        with db.session() as s:
            row = s.get(ImageCandidate, cid)
            saved = dict(row.checks)
            row.checks = {**saved, "motif_fidelity": {"status": "UNKNOWN", "why": "tampered"}}
            flag_modified(row, "checks")
        try:
            out = RG.listing_set(db, slug=SH.SLUG, version=version, issue=False)
            assert out["blocks_release"] is True, out
            assert any("may not export" in r for r in out["reasons"]), out["reasons"]
        finally:
            with db.session() as s:
                row = s.get(ImageCandidate, cid)
                row.checks = saved
                flag_modified(row, "checks")
        # 2. the selection names bytes that are not the stored frame's
        with db.session() as s:
            bad = {**sel, "frames": [{**f, "sha256": "0" * 64} if f["role"] == "hero" else f
                                     for f in sel["frames"]]}
            s.add(AuditLog(actor="test", action=RG.SELECTED_ACTION,
                           artifact=f"{SH.SLUG}@{version}", detail=bad))
        try:
            out = RG.listing_set(db, slug=SH.SLUG, version=version, issue=False)
            assert out["blocks_release"] is True
            assert any("not on file as a generated-gallery frame" in str(f.get("why"))
                       for f in out["frames"]), out["frames"]
        finally:
            with db.session() as s:
                s.add(AuditLog(actor="test", action=RG.SELECTED_ACTION,
                               artifact=f"{SH.SLUG}@{version}", detail=sel))
        # 3. no certified CONTENTS preview
        real = RG.certified_contents_frame
        RG.certified_contents_frame = lambda *a, **k: {"status": "UNMEASURED",
                                                       "why": "tampered", "owner": "t"}
        try:
            out = RG.listing_set(db, slug=SH.SLUG, version=version, issue=False)
            assert out["blocks_release"] is True
            assert any(r.startswith("download-information frame") for r in out["reasons"])
        finally:
            RG.certified_contents_frame = real
        # The tampered selection changed what the certificate was bound to, so the stored
        # certificate was invalidated (recheck); it is re-issued only by a fresh, full pass.
        again = RG.listing_set(db, slug=SH.SLUG, version=version, issue=True,
                               store_renders=True)
        assert again["blocks_release"] is False, again["reasons"]
        assert again["certificate"]["valid"] is True


def test_9_a_release_with_a_failing_non_image_gate_makes_no_paid_call():
    """b17-c A3 (D-OWNER-SPEND-ORDER): with image generation activated, a certified release
    whose listing package still has a non-image blocker is not admitted for sale, so the
    paid FLUX route is never enqueued -- not by assets.build, not by listing.package -- and
    a FLUX job delivered anyway parks in the non-spending waiting state with 0 calls."""
    import test_search_hero_publish as SH
    from sqlalchemy import select

    from brambleloop.core.db import Database
    from brambleloop.core.models import Job
    from brambleloop.publish import listing_package as LP
    from brambleloop.visual import image_production as IP

    slug = "housewarming-key-basket"
    path, version, rh = SH._chain(slug, "basket")
    db = Database(f"sqlite:///{path}")
    # D-MAIN-IMAGE-ADMISSION: the basket's real blockers are only image ones plus the
    # publish-time gates, so it IS admitted (test_10). A real non-image gate is added here:
    # the stored listing is priced off its Launch-0 plan (LISTING_PRICE_NOT_PLAN).
    _price_off_plan(db, slug)

    def flux_jobs():
        with db.session() as s:
            return [j for j in s.scalars(select(Job).where(Job.job_type == IP.JOB_TYPE))
                    if (j.inputs or {}).get("route") == IP.SP.FLUX_ROUTE]

    assert flux_jobs() == [], "assets.build must not enqueue the paid FLUX route"

    class PaidGenerator(O.StubGenerator):
        name, paid, max_cost_cad_per_call = "paid-test-double", True, 0.50

    gen = PaidGenerator()
    from brambleloop.visual import gallery as G

    real_gates = G.gates_now
    # test_double: image generation activated (the owner's provider activation is live)
    G.gates_now = lambda db_, keys=(): {k: True for k in keys}
    try:
        job = SH._run(db, "listing", "listing.package",
                      {"slug": slug, "version": version, "release": rh})
        assert job.status.name == "DONE", job.last_error
        adm = IP.sale_admission(db, slug, version, rh)
        assert adm["admitted"] is False and adm["non_image_blockers"], adm
        assert all(b.get("image") is not True for b in adm["non_image_blockers"]), adm
        assert any("LISTING_PRICE_NOT_PLAN" in b["why"] for b in adm["non_image_blockers"]), adm
        assert flux_jobs() == [], "listing.package enqueued a release that is not for sale"
        follow, _ = O.drain(db, generator=gen, judges=None)
        got = IP.admit_for_sale(db, follow, slug=slug, version=version, release=rh)
        assert got["enqueued"] is False, got
        # A FLUX job that reaches the worker anyway (stale or hand-enqueued) parks unspent.
        first = IP.trigger(follow, slug=slug, version=version, release=rh,
                           route=IP.SP.FLUX_ROUTE)
        O.drain(db, generator=gen, judges=None)
        run = IP.get_run(db, first["run_key"])
        assert run["state"] == IP.SALE_WAITING, run
        assert run["generation_calls"] == 0 and run["spent_cad"] == 0.0, run
        assert gen.calls == 0
        assert IP.outfits.reserved_for(db, run["listing"]) is None
    finally:
        G.gates_now = real_gates
    db.engine.dispose()


# ---- D-MAIN-IMAGE-ADMISSION: publish-time gates do not stop image admission -----------------

PUBLISH_TIME = {"gauge_and_size_claims", "etsy_remote_state"}
# ENG-ESTIMATE-CLAIMS: this basket's gauge and size claims now PASS as truthful calculated
# estimates, so of the two allow-listed publish-time gates only the store-wide Etsy one still
# blocks it. The allow-list itself is unchanged (test_13).
BASKET_PUBLISH_TIME = {"etsy_remote_state"}


def _price_off_plan(db, slug):
    """A real non-image listing gate: the stored listing carries a price that is not its
    Launch-0 plan's, which `release_gates.for_publish` refuses as LISTING_PRICE_NOT_PLAN."""
    from sqlalchemy import select

    from brambleloop.core.models import Listing
    from brambleloop.products import launch0

    plan = launch0.launch_price(slug)["price_cad"]
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug))
        row.price_cad = round(float(plan) + 1.0, 2)


def _basket_packaged():
    """The key basket's real chain, through the real listing.package job (whose for-sale
    admission point runs). Its real blockers: the sample-photo requirement (an image
    reason) and the two publish-time first-customer gates."""
    if "basket" not in _S:
        import test_search_hero_publish as SH
        from brambleloop.core.db import Database

        slug = "housewarming-key-basket"
        path, version, rh = SH._chain(slug, "basket")
        db = Database(f"sqlite:///{path}")
        job = SH._run(db, "listing", "listing.package",
                      {"slug": slug, "version": version, "release": rh})
        assert job.status.name == "DONE", job.last_error
        _S["basket"] = (db, slug, version, rh)
    return _S["basket"]


def _flux_jobs(db):
    from sqlalchemy import select

    from brambleloop.core.models import Job
    from brambleloop.visual import image_production as IP

    with db.session() as s:
        return [j for j in s.scalars(select(Job).where(Job.job_type == IP.JOB_TYPE))
                if (j.inputs or {}).get("route") == IP.SP.FLUX_ROUTE]


def test_10_a_release_blocked_only_by_publish_time_gates_and_images_is_admitted():
    """(1) Blocked only by gauge_and_size_claims + etsy_remote_state + image reasons: the
    real listing.package admits it and enqueues its paid FLUX gallery route."""
    from brambleloop.publish import listing_package as LP
    from brambleloop.visual import image_production as IP

    db, slug, version, rh = _basket_packaged()
    pkg = LP.latest(db, slug, version)
    blockers = pkg["blockers"]
    assert pkg["state"] == LP.BLOCKED and blockers, pkg
    areas = {b.get("publish_time") for b in blockers if b.get("publish_time")}
    assert areas == BASKET_PUBLISH_TIME, blockers
    assert any(b.get("image") is True for b in blockers), blockers
    assert all(b.get("image") is True or b.get("publish_time") in PUBLISH_TIME
               for b in blockers), blockers
    adm = IP.sale_admission(db, slug, version, rh)
    assert adm["admitted"] is True, adm
    assert set(adm["publish_time_blockers"]) == BASKET_PUBLISH_TIME, adm
    assert "still block publishing" in adm["why"], adm
    jobs = _flux_jobs(db)
    assert len(jobs) == 1 and jobs[0].inputs["release"] == rh, [j.inputs for j in jobs]


def test_11_the_same_release_plus_any_other_non_image_blocker_is_not_admitted():
    """(2) The same real package plus one more non-image blocker -- of any kind, including an
    unattributable one, a first-customer area off the allow-list, and a forged publish_time
    tag from another source -- is not admitted. (The real-gate version is test_9.)"""
    from brambleloop.publish import listing_package as LP
    from brambleloop.visual import image_production as IP

    db, slug, version, rh = _basket_packaged()
    real = LP.latest(db, slug, version)
    extras = [
        {"source": "release_gates.for_publish", "why": "LISTING_PRICE_NOT_PLAN: off plan"},
        {"source": "release_gates.for_publish", "why": "FIRST_CUSTOMER_BLOCKING: "
         "listing_claims: UNRESOLVED -- x"},
        {"source": "release_gates.for_publish", "publish_time": "listing_claims", "why": "x"},
        {"source": "release_gates.for_publish", "publish_time": "imagery", "why": "x"},
        {"source": "release_gates.for_publish", "publish_time": True, "why": "x"},
        {"source": "certified_payload", "publish_time": "etsy_remote_state", "why": "x"},
        {"source": "assets.build", "why": "no assets.build certifies PDFs"},
        "an unattributable blocker",
        {},
    ]
    assert extras
    real_latest = LP.latest
    try:
        for extra in extras:
            # test_double: the recorded package, plus one extra blocker
            LP.latest = lambda *a, _e=extra, **k: {**real, "blockers": real["blockers"] + [_e]}
            adm = IP.sale_admission(db, slug, version, rh)
            assert adm["admitted"] is False, (extra, adm)
            assert adm["non_image_blockers"] == [extra], (extra, adm)
    finally:
        LP.latest = real_latest
    assert IP.sale_admission(db, slug, version, rh)["admitted"] is True


def test_12_the_publish_path_still_refuses_on_both_publish_time_gates():
    """(3) Admission for images changes nothing at publication: for_publish still lists both
    gates and blocks, and store.publish (real release gates, real Launch-0 scope gate)
    refuses with both reasons and makes no Etsy request."""
    import test_search_hero_publish as SH
    from brambleloop.core.models import JobStatus, Phase
    from brambleloop.publish import eligibility
    from brambleloop.publish import release_gates as RG
    from tests.fake_etsy import FakeEtsy

    db, slug, version, rh = _basket_packaged()
    verdict = RG.for_publish(db, slug=slug, version=version, read_only=True,
                             stage=RG.STAGE_ACTIVATION)
    assert verdict["blocks_release"] is True
    gated = RG.publish_time_reasons(verdict)
    assert set(gated.values()) == BASKET_PUBLISH_TIME, gated
    assert all(r in verdict["reasons"] for r in gated), (gated, verdict["reasons"])
    real_scope = eligibility.product_publication
    with FakeEtsy() as fake, SH._owner_and_fake(fake):
        eligibility.product_publication = real_scope   # the Launch-0 scope gate runs for real
        SH._grant(db, version, rh, slug=slug)
        job = SH._run(db, "store_operator", "store.publish",
                      {"slug": slug, "version": version, "release": rh},
                      phase=Phase.LIMITED_PRODUCTION)
        out = job.outputs or {}
        assert job.status is not JobStatus.DONE or out.get("published") is not True, out
        said = (job.last_error or "") + str(out)
        for area in BASKET_PUBLISH_TIME:
            assert f"FIRST_CUSTOMER_BLOCKING: {area}:" in said, (area, said[:2000])
        assert SH._creates(fake) == [] and not fake.received_images, fake.requests


def test_13_the_allow_list_is_what_admits():
    """(4) The allow-list is load-bearing: emptied, the release of test_10 is not admitted;
    and only the two named areas are on it."""
    from brambleloop.publish import release_gates as RG
    from brambleloop.visual import image_production as IP

    assert RG.PUBLISH_TIME_AREAS == frozenset(PUBLISH_TIME)
    db, slug, version, rh = _basket_packaged()
    assert IP.sale_admission(db, slug, version, rh)["admitted"] is True
    saved = RG.PUBLISH_TIME_AREAS
    RG.PUBLISH_TIME_AREAS = frozenset()
    try:
        adm = IP.sale_admission(db, slug, version, rh)
        assert adm["admitted"] is False, adm
        assert {b.get("publish_time") for b in adm["non_image_blockers"]} == \
            BASKET_PUBLISH_TIME, adm
        assert RG.publish_time_reasons({"publication_scope": {"reasons": [
            {"code": "FIRST_CUSTOMER_BLOCKING", "area": "etsy_remote_state", "why": "x"}]}}) \
            == {}
    finally:
        RG.PUBLISH_TIME_AREAS = saved
    # Read from the structured area, never the text: a reason without an area is not on it.
    assert RG.publish_time_reasons({"publication_scope": {"reasons": [
        {"code": "FIRST_CUSTOMER_BLOCKING", "why": "etsy_remote_state: UNVERIFIABLE -- x"},
        {"code": "OTHER", "area": "etsy_remote_state", "why": "x"},
        {"code": "FIRST_CUSTOMER_BLOCKING", "area": "imagery", "why": "x"}]}}) == {}


if __name__ == "__main__":
    import os

    only = [x for x in os.environ.get("VIS_E2E_ONLY", "").split(",") if x]
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn) and (
                not only or any(name.startswith(o) for o in only)):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
