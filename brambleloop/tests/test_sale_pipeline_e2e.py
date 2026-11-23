"""ENG-SALE-PIPELINE end to end: a certified, for-sale release becomes READY with no owner step
(D-OWNER-SALE-PIPELINE, HARD RULE).

Real: `gate.certify` and `assets.build` for the Cloudline baby blanket (both text PDFs rendered,
hashed and stored); every `sale.pipeline` stage and every `visual.image_production` stage
through the real worker handlers on the durable queue; the release.py hand-off from image
production to the gallery stage; the premium US/UK render with the certified images in the
standard's slots; `publish.pdf_standard` on the stored bytes; the certificates; the listing
package; the ready rule; the board.

test_double (labelled, nothing else is replaced):
* the image generator and its judges (`StubGenerator`, `StubJudges` from test_w4_ownerimg:
  free, no network, no spend);
* the generated-gallery certificate route. ENG-VIS-GALLERY's `certify_gallery` is not merged
  in this branch, so `CertifiedGalleryDouble` stands in for the valid listing-set certificate
  it issues: seven certified campaign frames, served through `etsy_ops.certified_frames` /
  `certified_images` only after the chain asked for certification;
* the upstream chain decisions this test does not re-run (`listing.seo` and `launch.plan`
  DONE rows) and the buyer-facing publication gates (`release_gates.for_publish`), which are
  covered by their own suites.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_sale_pipeline_e2e.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import io
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="sale_e2e_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
import test_w4_ownerimg as O  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (EtsyTaxonomySnapshot, Job, JobStatus, Listing,  # noqa: E402
                                     PatternVersion)
from brambleloop.runtime import pipeline, release as _release  # noqa: E402,F401
from brambleloop.core.phase import Phase  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.publish import sale_pipeline as SPL  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.shot_plans import campaign_plan  # noqa: E402

_R: dict = {}


class CertifiedGalleryDouble:
    """test_double for ENG-VIS-GALLERY's generated-gallery certificate (seven frames)."""

    def __init__(self, db, slug, version, release, listing):
        from brambleloop.core.artifacts import ArtifactStore

        self.db, self.slug, self.version, self.release = db, slug, version, release
        self.certified = False
        self.asked = 0
        self.frames, self.data = [], {}
        for r in campaign_plan(listing)["roles"]:
            im = Image.new("RGB", (2000, 2000), (30 + 20 * r["position"], 110, 90))
            b = io.BytesIO()
            im.save(b, "PNG")
            sha = ArtifactStore().put(f"double/{slug}/{r['role']}.png", b.getvalue(),
                                      "image/png", db=db, keep="test_double").sha256
            self.frames.append({"position": r["position"], "role": r["role"], "sha256": sha,
                                "kind": "ai_generated", "honesty_label": "AI-generated",
                                "alt_text": r["role"]})
            self.data[sha] = b.getvalue()

    def install(self):
        real_frames, real_images = etsy_ops.certified_frames, etsy_ops.certified_images
        real_route = SPL._gallery_route_certify

        def frames(db, slug, version, *, release=""):
            if self.certified and (slug, version) == (self.slug, self.version):
                return {"frames": list(self.frames), "record_id": 4242, "problems": []}
            return real_frames(db, slug, version, release=release)

        def images(db, slug, version, *, release="", store_root=None):
            if self.certified and (slug, version) == (self.slug, self.version):
                return {"images": [(f"{f['role']}.png", self.data[f["sha256"]])
                                   for f in self.frames], "record_id": 4242,
                        "order": [f["sha256"] for f in self.frames], "problems": []}
            return real_images(db, slug, version, release=release, store_root=store_root)

        def route(db, slug, version, release):
            self.asked += 1
            run = SPL.image_run(db, slug, version, release)
            if run and run["state"] == "ready_for_owner_review":
                self.certified = True
                return {"certified": True, "why": "test_double certificate"}
            return {"certified": False, "why": "gallery not assembled"}

        etsy_ops.certified_frames, etsy_ops.certified_images = frames, images
        SPL._gallery_route_certify = route
        return lambda: (setattr(etsy_ops, "certified_frames", real_frames),
                        setattr(etsy_ops, "certified_images", real_images),
                        setattr(SPL, "_gallery_route_certify", real_route))


def _run_job(db, agent, job_type, inputs, key):
    job = JobQueue(db).enqueue(agent, job_type, inputs, idempotency_key=key, priority=0)
    Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=[job_type],
           lease_seconds=900).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _drain(db, job_types, limit=80):
    """The worker loop over the real handlers for the chain's two job types."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    ran = []
    for _ in range(limit):
        # the launch.plan entry delays admission a few minutes; the test does not wait
        with db.session() as s:
            s.execute(update(Job).where(Job.status == JobStatus.PENDING)
                      .values(run_after=datetime.now(timezone.utc) - timedelta(seconds=1)))
        w = Worker(db, "w-chain", phase=Phase.SHADOW, job_types=list(job_types),
                   lease_seconds=900)
        if not w.run_once():
            break
        with db.session() as s:
            j = s.scalars(select(Job).where(Job.job_type.in_(job_types))
                          .where(Job.started_at.is_not(None)).order_by(Job.started_at.desc(), Job.id.desc())).first()
            ran.append((j.job_type, (j.inputs or {}).get("stage"), j.status.value,
                        (j.outputs or {}).get("state") or (j.outputs or {}).get("status")))
    return ran


def _chain():
    if _R:
        return _R
    from brambleloop.publish import release_gates

    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/e2e.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    snap = FX.snapshot()
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    # D-OWNER-LAURA-MANDATORY: a gallery is never ready without a generated Laura frame, and
    # only a Laura listing's plan asks for one (shot_plans.LIFESTYLE_BRIEF). The chain runs on
    # the Cloudline baby blanket, whose campaign plan marks its lifestyle, size and colour
    # frames for Laura, so the generator produces them exactly as production would. A
    # Laura-free plan (coasters, baskets, placemats) correctly stops at the gallery stage with
    # laura_lifestyle_missing (test_v2_gallery_consistency).
    cir = L.cir_for("cloudline_blanket")
    job = _run_job(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "certify")
    assert job.outputs.get("granted"), job.outputs
    with db.session() as s:
        release = s.scalar(select(PatternVersion)).release_hash
    job = _run_job(db, "publishing", "assets.build", {"slug": cir.slug, "version": cir.version,
                                                      "release": release, "rebuild": "x"}, "a")
    assert job.status is JobStatus.DONE, job.last_error
    # The release chain's own stages, through their real handlers: pricing.position ->
    # listing.seo -> launch.plan. launch.plan's exit is what raises the sale chain's admission.
    upstream = _drain(db, ("pricing.position", "listing.seo", "launch.plan"), limit=10)
    with db.session() as s:
        listing_row = s.scalar(select(Listing).where(Listing.product_slug == cir.slug))
        assert listing_row is not None and listing_row.release_hash == release, upstream
    from brambleloop.visual.outfits import listing_of

    listing = listing_of(cir.slug)
    double = CertifiedGalleryDouble(db, cir.slug, cir.version, release, listing)
    restore = double.install()
    real_gen, real_judges = IP.resolve_generator, CG.RealJudges
    real_gate = release_gates.for_publish
    gen = O.StubGenerator()                            # test_double, free
    IP.resolve_generator = lambda _db: gen
    CG.RealJudges = lambda _db: O.StubJudges()         # test_double
    release_gates.for_publish = lambda *a, **k: {"reasons": [], "blocks_release": False}
    try:
        before = SPL.get(db, cir.slug, cir.version, release)
        with db.session() as s:          # launch.plan raised the admission, nothing else did
            entry = [j.inputs for j in s.scalars(select(Job).where(
                Job.job_type == SPL.JOB_TYPE))]
        assert entry == [{"slug": cir.slug, "version": cir.version, "release": release,
                          "stage": "admission"}], (entry, upstream)
        ran = _drain(db, (SPL.JOB_TYPE, IP.JOB_TYPE))
        pkg_mid = None
        _R.update(db=db, cir=cir, release=release, ran=ran, gen=gen, double=double,
                  upstream=upstream,
                  before=before, pkg_mid=pkg_mid,
                  run=SPL.get(db, cir.slug, cir.version, release),
                  image=SPL.image_run(db, cir.slug, cir.version, release),
                  certs=SPL.pdf_certificates(db, cir.slug, cir.version, release),
                  ready=SPL.ready_for_sale(db, cir.slug, cir.version, release),
                  board=SPL.board(db), package=LP.latest(db, cir.slug, cir.version),
                  premium=SPL.certified_premium_pdfs(db, cir.slug, cir.version, release))
    finally:
        IP.resolve_generator, CG.RealJudges = real_gen, real_judges
        release_gates.for_publish = real_gate
        restore()
    return _R


def test_the_release_reaches_ready_with_no_owner_step():
    R = _chain()
    assert R["before"] is None
    assert R["run"]["state"] == SPL.READY, (R["run"], R["ran"])
    assert R["ready"]["ready"] is True, R["ready"]
    stages = [st for jt, st, *_ in R["ran"] if jt == SPL.JOB_TYPE]
    for st in SPL.STAGES:
        assert st in stages, (st, stages)
    assert all(status == "done" for _jt, _st, status, _o in R["ran"]), R["ran"]


def test_image_production_ran_through_its_stages_and_handed_on():
    R = _chain()
    assert R["image"]["state"] == "ready_for_owner_review", R["image"]
    # D-OWNER-LAURA-MANDATORY: the gallery holds a generated Laura frame no check FAILed
    rd = IP.readiness(R["db"], R["image"]["listing"], run_key_=R["image"]["run_key"])
    # (gallery_ready itself also needs publishable frames, which SHADOW never grants)
    assert rd["laura_lifestyle_ok"] is True and rd["set_check"]["ok"], rd["set_check"]
    assert any(e["laura"] and e["source"] == "generated" for e in rd["roles"]), rd["roles"]
    assert R["gen"].calls >= 1 and R["image"]["spent_cad"] == 0.0
    img_jobs = [x for x in R["ran"] if x[0] == IP.JOB_TYPE]
    assert len(img_jobs) >= 10, img_jobs
    # the gallery stage came after the image run ended, and asked for certification
    first_gallery = next(i for i, x in enumerate(R["ran"]) if x[:2] == (SPL.JOB_TYPE, "gallery"))
    last_image = max(i for i, x in enumerate(R["ran"]) if x[0] == IP.JOB_TYPE)
    assert first_gallery > last_image and R["double"].asked >= 1


def test_both_premium_pdfs_embed_exactly_the_certified_gallery_and_are_certified():
    from brambleloop.publish import pdf_photos as PP
    from brambleloop.publish import pdf_standard as PS

    R = _chain()
    assert R["certs"]["both_pass"], R["certs"]
    assert set(R["premium"]) == {"US", "UK"}
    # D-OWNER-PDF-TEMPLATE: the owner's master template carries all seven certified frames
    # (its seven gallery slots, hero on the cover) and nothing else as a photograph.
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    want = {PP.sha256(PP.rendition(R["double"].data[f["sha256"]])) for f in R["double"].frames}
    assert len(want) == CAMPAIGN_MIN_FRAMES
    for t, data in R["premium"].items():
        doc = PS.read(data)
        embedded = {im["sha256"] for p in doc["pages"] for im in p["images"] if im.get("dct")}
        assert embedded == want, t
        assert PS.layout_of(doc) == "template", t
        expected = (R["run"]["evidence"] or {}).get("expected")
        assert len(expected["gallery_frames"]) == CAMPAIGN_MIN_FRAMES, expected
        r = PS.check(data, cir=R["cir"], terminology=t, expected=expected,
                     require_template=True)
        by = {c["check"]: c["status"] for c in r["checks"]}
        assert r["verdict"] == "PASS", (t, r["failed"], r["unknown"])
        assert by["logo:cover"] == by["slot:gallery7"] == by["layout"] == "PASS", by
        assert R["certs"]["editions"][t]["verdict"] == "PASS"
        assert R["certs"]["editions"][t]["bound_to_release_pdfs"]
    assert R["premium"]["US"] != R["premium"]["UK"]



def test_the_checker_fails_a_wrong_logo_a_short_or_reordered_gallery_and_another_layout():
    """Every new rule can fail on the real premium bytes (mutation, not vacuity)."""
    from PIL import Image, ImageOps

    from brambleloop.publish import pdf as P
    from brambleloop.publish import pdf_standard as PS

    R = _chain()
    data = R["premium"]["US"]
    expected = dict((R["run"]["evidence"] or {}).get("expected"))
    frames = list(expected["gallery_frames"])
    assert len(frames) == 7

    def status(exp, name, **kw):
        r = PS.check(data, cir=R["cir"], terminology="US", expected=exp, **kw)
        return {c["check"]: c["status"] for c in r["checks"]}[name], r["verdict"]

    assert status(expected, "slot:gallery7") == ("PASS", "PASS")
    assert status({**expected, "gallery_frames": frames[:6]}, "slot:gallery7") == (
        "FAIL", "FAIL")
    assert status({**expected, "gallery_frames": frames[::-1]}, "slot:gallery7") == (
        "FAIL", "FAIL")
    # The logo match is perceptual against the canonical rendition, and nothing else passes.
    logo = P._cover_logo()
    assert PS.logo_matches(logo)
    assert not PS.logo_matches(ImageOps.invert(logo.convert("RGB")))
    assert not PS.logo_matches(Image.new("RGB", logo.size, (240, 236, 228)))
    saved = list(PS._LOGO_REF)
    PS._LOGO_REF[:] = [PS._logo_signature(ImageOps.invert(logo.convert("RGB")))]
    try:
        assert status(expected, "logo:cover") == ("FAIL", "FAIL")
    finally:
        PS._LOGO_REF[:] = saved
    # The engine layout is refused when the sale pipeline requires the owner template.
    hashes = (R["run"]["readiness"]["gates"]["pdf_text"] or {}).get("hashes")
    base = SPL._base_pdf_bytes(R["db"], R["cir"].slug, R["cir"].version, R["release"], "US",
                               hashes["US"])
    r = PS.check(base, cir=R["cir"], terminology="US", expected=expected,
                 require_template=True)
    by = {c["check"]: c for c in r["checks"]}
    assert r["layout"] == "engine" and by["layout"]["status"] == "FAIL", by["layout"]
    assert r["verdict"] == "FAIL"

def test_one_unknown_check_among_passes_is_unknown_and_never_certifies():
    """Review b19-a #2: UNKNOWN is never PASS. On the real premium bytes every check PASSES
    except the cover logo, whose reader is made to raise (UNKNOWN). The verdict is UNKNOWN,
    and the certificate recorded from it does not make both editions pass."""
    from brambleloop.publish import pdf_standard as PS

    R = _chain()
    expected = dict((R["run"]["evidence"] or {}).get("expected"))
    ev = R["run"]["evidence"]
    restore = R["double"].install()               # the certified gallery, as during the chain
    real_logo = PS._cover_logo_check

    def unreadable_logo(_pdf_bytes):
        raise RuntimeError("cover image unreadable")

    try:
        for t, data in R["premium"].items():
            r = PS.check(data, cir=R["cir"], terminology=t, expected=expected,
                         require_template=True)
            assert r["verdict"] == "PASS", (t, r["failed"], r["unknown"])
        PS._cover_logo_check = unreadable_logo
        for t, data in R["premium"].items():
            r = PS.check(data, cir=R["cir"], terminology=t, expected=expected,
                         require_template=True)
            by = {c["check"]: c["status"] for c in r["checks"]}
            assert by.pop("logo:cover") == "UNKNOWN", by
            assert by and set(by.values()) == {"PASS"}, by     # the only non-PASS check
            assert r["verdict"] == "UNKNOWN" and r["failed"] == [], (t, r["verdict"])
        got = SPL.certify_pdfs(R["db"], R["cir"].slug, R["cir"].version, R["release"],
                               files=ev["premium_pdfs"], expected=ev["expected"],
                               gallery_record_id=ev["gallery_record_id"],
                               base=ev["base_pdfs"])
        assert {v["verdict"] for v in got.values()} == {"UNKNOWN"}, got
        certs = SPL.pdf_certificates(R["db"], R["cir"].slug, R["cir"].version, R["release"])
        assert certs["both_pass"] is False, certs
        assert {e["verdict"] for e in certs["editions"].values()} == {"UNKNOWN"}, certs
        assert SPL.certified_premium_pdfs(R["db"], R["cir"].slug, R["cir"].version,
                                          R["release"]) is None
    finally:
        PS._cover_logo_check = real_logo
        # re-certify with the real reader so the fixture's certificates are as the chain left
        SPL.certify_pdfs(R["db"], R["cir"].slug, R["cir"].version, R["release"],
                         files=ev["premium_pdfs"], expected=ev["expected"],
                         gallery_record_id=ev["gallery_record_id"], base=ev["base_pdfs"])
        assert SPL.pdf_certificates(R["db"], R["cir"].slug, R["cir"].version,
                                    R["release"])["both_pass"] is True
        restore()


def test_the_listing_package_carries_the_gallery_and_both_pdfs():
    R = _chain()
    pkg = R["package"]
    assert pkg["state"] == LP.READY and pkg["release_hash"] == R["release"], pkg["blockers"]
    assert [g["sha256"] for g in pkg["gallery"]] == [f["sha256"] for f in R["double"].frames]
    prem = pkg["files"]["premium_pdfs"]
    assert {t: prem[t]["verdict"] for t in prem} == {"US": "PASS", "UK": "PASS"}


def test_the_board_counts_what_happened():
    b = _chain()["board"]
    assert b["readable"] and b["eligible"] == 1 and b["gallery_done"] == 1
    assert b["pdfs_certified"] == 1 and b["ready"] == 1 and b["blocked_by_reason"] == {}
    assert b["stalled"] == 0


def test_the_admission_reservation_was_consumed_once():
    R = _chain()
    assert R["run"]["reservation"] == "consumed" and R["run"]["reserved_cad"] == \
        SPL._per_listing_cap()
    # duplicate events are deduplicated: one job per stage key
    with R["db"].session() as s:
        keys = [j.idempotency_key for j in s.scalars(select(Job).where(
            Job.job_type == SPL.JOB_TYPE))]
    assert len(keys) == len(set(keys))


if __name__ == "__main__":
    import traceback

    failed = 0
    for name, fn in sorted((n, f) for n, f in dict(globals()).items() if n.startswith("test_")):
        try:
            fn()
            print("OK  ", name)
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL", name)
            traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
