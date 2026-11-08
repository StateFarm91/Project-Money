"""W6 P0: every listing agent proven end to end, on the real chain, for one Launch-0 product.

One `cir.draft` for `hexagon-coaster-set` (a LAUNCH0_SLUGS product) is the only manual trigger
of the release chain. The real worker and the real handlers then drive, through the durable
job queue on a durable file-backed SQLite database, in SHADOW and with sockets closed:

  cir.draft -> cir.compile -> gate.certify -> listing.draft -> assets.build (US/UK PDFs)
  -> pricing.position -> listing.seo -> launch.plan -> marketing.schedule + store.publish

and then the `listing.package` cadence (runtime/listing_package_ops.py -> publish/
listing_package.sweep), enqueued exactly as `Scheduler.tick` enqueues a cadence.

  A. every stage ran from a job the stage before it enqueued (`job_links`, the queue's own
     causal record), and no stage was enqueued by hand after the first trigger;
  B. in SHADOW `store.publish` is refused (dead-lettered, `store.publish_refused` audited)
     and nothing is published;
  C. the release's listing package is BLOCKED, with the exact blocker set asserted (the sample
     photo is one of three; the other two are named with their gates below);
  D. with a FIXTURE full make and FIXTURE photograph recorded through the real intake
     (`physical.record` with `photos` -> `physical.photo` intake -> `assets.physical_upgrade`)
     and the owner's unedited attestation (FIXTURE), the package moves to its NEXT state,
     which is asserted exactly. It does not reach READY: see test D for why, and for the
     chain defect it found (pinned, not fixed).

Nothing here forges a gate reading: no frame is approved by hand, no listing-set certificate
or Etsy verification is supplied. Every fixture is labelled "FIXTURE — not physical evidence".

Run: cd brambleloop && python3 tests/test_w6_listing_chain_e2e.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  W3-HYG: per-process temp sandbox, removed at exit
import copy
import io
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="w6_listing_chain_e2e_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

import network_guard  # noqa: E402

network_guard.install()

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, EtsyTaxonomySnapshot, Job, JobStatus, Listing, ListingAsset, OwnerAction,
    PatternVersion, Phase, PhysicalPhoto, PhysicalTest,
)
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.publish import physical_upgrade as PU  # noqa: E402
from brambleloop.publish import sample_photo as SP  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import listing_package_ops, pipeline, release  # noqa: E402,F401
from brambleloop.runtime.lineage import JobLink  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402

SLUG = "hexagon-coaster-set"
FIXTURE = "FIXTURE — not physical evidence"
FIXTURE_TESTER = "fixture-tester-w6e2e"
# The owner's Command Center attestation is the owner's act; here it is a labelled fixture.
FIXTURE_OWNER = "owner:cc:FIXTURE-not-physical-evidence"

# The chain under test, each stage with the stage whose job must have enqueued it.
CHAIN = (
    ("cir.draft", None),
    ("cir.compile", "cir.draft"),
    ("gate.certify", "cir.compile"),
    ("listing.draft", "gate.certify"),
    ("assets.build", "listing.draft"),
    ("pricing.position", "assets.build"),
    ("listing.seo", "pricing.position"),
    ("launch.plan", "listing.seo"),
    ("marketing.schedule", "launch.plan"),
    ("store.publish", "launch.plan"),
)

_W: dict = {}


def _boot() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/w6_e2e.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    snap = FX.snapshot()       # the Etsy taxonomy fixture the payload builder reads offline
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    return db


def _drain(db, name, job_types=None, limit=400) -> Worker:
    w = Worker(db, name, phase=Phase.SHADOW, job_types=job_types, lease_seconds=900)
    for _ in range(limit):
        if not w.run_once():
            break
    return w


def _enqueue_cadence(db, cadence: str, window: int) -> int:
    """Enqueue one cadence exactly as `Scheduler.tick` does (agent, job type, inputs, key),
    without enqueueing every other cadence in the catalogue."""
    name, agent, job_type, _period = next(c for c in CADENCES if c[0] == cadence)
    job = JobQueue(db).enqueue(agent, job_type, {"cadence": name},
                               idempotency_key=f"cadence:{name}:{window}")
    return job.id


def _jobs(db) -> list[dict]:
    with db.session() as s:
        return [{"id": j.id, "type": j.job_type, "status": j.status, "key": j.idempotency_key,
                 "error": j.last_error or "", "inputs": dict(j.inputs or {}),
                 "outputs": dict(j.outputs or {}), "started": j.started_at,
                 "finished": j.finished_at}
                for j in s.scalars(select(Job).order_by(Job.id))]


def _links(db) -> dict[int, int]:
    with db.session() as s:
        return {r.child_id: r.parent_id for r in s.scalars(select(JobLink))}


def _blocker_key(b: dict) -> tuple[str, str]:
    """A blocker's stable identity: its source and the gate code / reader that raised it."""
    why = b["why"]
    for pattern in (r"^(FIRST_CUSTOMER_BLOCKING: \w+)", r"^(SAMPLE_PHOTO_REQUIRED)",
                    r"^(listing-set certificate \(#70\))", r"^(search certificate \(F-004\))",
                    r"^(ValueError: listing search profile not certified PASS)",
                    r"^(no valid listing-set certificate for [\w.@-]+?):"):
        m = re.match(pattern, why)
        if m:
            return b["source"], m.group(1)
    return b["source"], why[:60]


def _world() -> dict:
    """The chain, run once from one trigger, then the package sweep. Read-only for tests."""
    if _W:
        return _W
    assert SLUG in L.LAUNCH0_SLUGS
    db = _boot()
    first = JobQueue(db).enqueue("crochet_engineer", "cir.draft", {"slug": SLUG}).id
    worker = _drain(db, "w6-e2e-chain")
    jobs_after_chain = _jobs(db)
    package_job = _enqueue_cadence(db, "listing_package", 0)
    _drain(db, "w6-e2e-package", job_types=["listing.package"])
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        version, rh = pv.version, pv.release_hash
    _W.update(db=db, first=first, worker=worker, jobs=jobs_after_chain, package_job=package_job,
              links=_links(db), version=version, release=rh,
              package=copy.deepcopy(LP.latest(db, SLUG, version)),
              package_run=next(j for j in _jobs(db) if j["id"] == package_job))
    return _W


def _stage(w, job_type) -> dict:
    hits = [j for j in w["jobs"] if j["type"] == job_type]
    assert len(hits) == 1, (job_type, [(j["id"], j["status"]) for j in hits])
    return hits[0]


# ---- A. every stage ran from a job the previous stage enqueued ----------------------------

def test_a_every_stage_ran_from_the_job_its_predecessor_enqueued():
    w = _world()
    by_id = {j["id"]: j for j in w["jobs"]}
    assert len(by_id) >= len(CHAIN), sorted((j["id"], j["type"]) for j in w["jobs"])
    for job_type, parent_type in CHAIN:
        job = _stage(w, job_type)
        if parent_type is None:
            assert job["id"] == w["first"] and job["id"] not in w["links"], job
            continue
        parent = by_id[w["links"][job["id"]]]   # KeyError: no causal link was recorded
        assert parent["type"] == parent_type, (job_type, parent["type"], parent_type)
        assert parent["status"] is JobStatus.DONE, (parent_type, parent["error"][:300])
        if job_type != "store.publish":
            assert job["status"] is JobStatus.DONE, (job_type, job["status"], job["error"][:400])
    # No manual enqueue after the first trigger: every chain job but the first has a parent.
    roots = [j for j in w["jobs"] if j["id"] not in w["links"]]
    assert [r["id"] for r in roots] == [w["first"]], [(r["id"], r["type"]) for r in roots]
    # The package sweep is its own declared trigger (a cadence), and it ran to completion.
    assert ("listing_package", "listing", "listing.package", 6 * 60 * 60) in CADENCES
    run = w["package_run"]
    assert run["type"] == "listing.package" and run["status"] is JobStatus.DONE, run["error"]
    assert run["key"].startswith("cadence:listing_package:")
    assert run["outputs"]["releases"] == 1 and run["outputs"]["publishes"] is False


def test_a_the_certified_release_flows_through_every_stage_with_its_own_artefacts():
    w = _world()
    rh = w["release"]
    assert rh and len(rh) == 64
    cert = _stage(w, "gate.certify")["outputs"]
    assert cert["granted"] is True and cert["release_hash"] == rh, cert
    assets = _stage(w, "assets.build")["outputs"]
    assert assets["release"] == rh
    pdfs = assets["pdf_sha256_by_terminology"]
    assert set(pdfs) == {"US", "UK"} and pdfs["US"] != pdfs["UK"], pdfs
    for sha in (pdfs["US"], pdfs["UK"]):
        assert ArtifactStore().get(sha, db=w["db"])[:5] == b"%PDF-"
    price = _stage(w, "pricing.position")["outputs"]["price_cad"]
    seo = _stage(w, "listing.seo")
    assert seo["outputs"]["ok"] is True, seo["outputs"]
    # The Listing row was written by the chain (listing.seo, priced by pricing.position),
    # never inserted here: it is created inside the listing.seo job's run window.
    with w["db"].session() as s:
        rows = list(s.scalars(select(Listing).where(Listing.product_slug == SLUG)))
        assert len(rows) == 1, rows
        row = rows[0]
        assert row.version == w["version"] and row.release_hash == rh
        assert row.price_cad == price and row.title and row.tags
        created = row.created_at.replace(tzinfo=None)
    assert seo["started"].replace(tzinfo=None) <= created <= seo["finished"].replace(tzinfo=None)
    plan = _stage(w, "launch.plan")["outputs"]
    assert not plan.get("held") and not plan.get("withheld"), plan
    assert _stage(w, "marketing.schedule")["outputs"]["published"] is False


# ---- B. SHADOW refuses publication ---------------------------------------------------------

def test_b_in_shadow_store_publish_is_refused_and_nothing_is_published():
    w = _world()
    pub = _stage(w, "store.publish")
    assert pub["status"] is JobStatus.DEAD, pub["status"]
    assert "SHADOW" in pub["error"], pub["error"][:300]
    dead = [j for j in JobQueue(w["db"]).dead_letters() if j.job_type == "store.publish"]
    assert [j.id for j in dead] == [pub["id"]]
    with w["db"].session() as s:
        refusals = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "store.publish_refused", AuditLog.job_id == pub["id"])))
        assert refusals and "shadow" in refusals[0].detail["reason"], refusals
        listing = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        assert listing.state == "draft" and listing.etsy_listing_id == "", (
            listing.state, listing.etsy_listing_id)
        assert not list(s.scalars(select(AuditLog).where(
            AuditLog.action.in_(("store.published", "store.activated")))))
    assert w["package"]["publishes"] is False


# ---- C. the package is BLOCKED, and on exactly what ----------------------------------------

# Observed on this chain. The task named SAMPLE_PHOTO_REQUIRED as the expected sole blocker;
# two more appear, and they are asserted rather than hidden:
#   * FIRST_CUSTOMER_BLOCKING: gauge_and_size_claims -- gate gates/first_customer.py (read by
#     release_gates.for_publish): no passed physical sample is bound to this content, so the
#     set-of-four size claim is unproven. A real independent full make clears it (see D).
#   * FIRST_CUSTOMER_BLOCKING: etsy_remote_state -- gate gates/first_customer.py: four
#     launch-blocking Etsy claims (array_encoding_tags, form_encoded_create,
#     multipart_image_upload, oauth_token_endpoint) are unverified because no authenticated
#     round trip against Etsy exists. Needs a live Etsy connection; cannot clear offline.
#   * SAMPLE_PHOTO_REQUIRED -- gate publish/sample_photo.py: no unedited photograph on file.
BLOCKERS_C = {
    ("release_gates.for_publish", "FIRST_CUSTOMER_BLOCKING: gauge_and_size_claims"),
    ("release_gates.for_publish", "FIRST_CUSTOMER_BLOCKING: etsy_remote_state"),
    ("release_gates.for_publish", "SAMPLE_PHOTO_REQUIRED"),
}


def test_c_the_package_is_blocked_on_exactly_the_observed_set():
    w = _world()
    pkg = w["package"]
    assert pkg is not None and pkg["release_hash"] == w["release"]
    assert pkg["state"] == LP.BLOCKED, pkg["state"]
    keys = [_blocker_key(b) for b in pkg["blockers"]]
    assert len(keys) == len(set(keys)) and set(keys) == BLOCKERS_C, keys
    photo = next(b["why"] for b in pkg["blockers"] if b["why"].startswith(SP.CODE))
    assert "no unedited photograph of a sample made from this release is on file" in photo
    # The rest of the package is complete: copy, US and UK files, a certified gallery.
    assert pkg["copy"] and pkg["copy"]["title"]
    assert set(pkg["files"]["pdf_sha256_by_terminology"]) == {"US", "UK"}
    assert pkg["gallery"] and pkg["gallery"][0]["position"] == 1
    with w["db"].session() as s:   # a blocked package asks the owner for no review
        assert not list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{LP.ACTION_PREFIX}%"))))


# ---- D. a FIXTURE sample and photograph through the real intake ----------------------------

# The next state, observed. Still BLOCKED, and READY is not reachable here without forging:
#   * gauge_and_size_claims and the no-photo SAMPLE_PHOTO_REQUIRED are gone: the FIXTURE full
#     make is bound to this release's content and the FIXTURE photo qualifies
#     (sample_photo.qualifying_photos lists it).
#   * The photo frame that assets.physical_upgrade adds is unapproved ("awaiting asset-truth
#     review and listing-set re-certification") and no production job approves a
#     PHYSICAL_PRODUCT_PHOTO frame, so the listing-set certificate (#70, publish/listing_set.py
#     via release_gates.listing_set) refuses with failing DATA_TRUTH and COMMERCIAL_QA. Every
#     other blocker below follows from that missing certificate:
#       - search certificate (F-004): the hero frame is not export-ready;
#       - FIRST_CUSTOMER_BLOCKING: imagery (gates/first_customer.py): no valid certificate;
#       - SAMPLE_PHOTO_REQUIRED (publish/sample_photo.py): the qualifying photo is not in a
#         valid listing-set certificate yet;
#       - certified_payload: the search profile is not certified PASS;
#       - certified_frames: no valid listing-set certificate.
#     Approving the frame by hand would be bypassing asset truth, so it is not done.
#   * FIRST_CUSTOMER_BLOCKING: etsy_remote_state still needs a live Etsy round trip.
BLOCKERS_D = {
    ("release_gates.for_publish", "listing-set certificate (#70)"),
    ("release_gates.for_publish", "search certificate (F-004)"),
    ("release_gates.for_publish", "FIRST_CUSTOMER_BLOCKING: imagery"),
    ("release_gates.for_publish", "FIRST_CUSTOMER_BLOCKING: etsy_remote_state"),
    ("release_gates.for_publish", "SAMPLE_PHOTO_REQUIRED"),
    ("certified_payload", "ValueError: listing search profile not certified PASS"),
    ("certified_frames", "no valid listing-set certificate for hexagon-coaster-set@1.2.1"),
}


def _fixture_photo_bytes() -> bytes:
    """FIXTURE — not physical evidence: a plain JPEG standing in for a camera file (no camera
    offline). Never a render or generation: the system has no record of having made it."""
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (1200, 1200), (196, 178, 160)).save(out, format="JPEG", quality=92)
    return out.getvalue()


def _with_sample() -> dict:
    w = _world()
    if "sample" in w:
        return w["sample"]
    import test_physfix as PF     # its intake-shaped sample builder, not a copy of it
    from brambleloop.cir.model import CIR
    from brambleloop.quality import tester_programme as tp

    db = w["db"]
    with db.session() as s:
        cir = CIR.from_dict(dict(s.scalar(select(PatternVersion)).cir_json))
    # Tester independence through the one intake (SECREVIEW R12): relationship "none".
    tp.record_agreement(db, handle_ref=FIXTURE_TESTER, specialties=["home_decor"],
                        express_consent=True, consent_source=FIXTURE, relationship="none",
                        qualification="https://www.ravelry.com/projects/fixture/hexagon-coaster")
    sha = ArtifactStore().put(f"physical/{SLUG}-fixture.jpg", _fixture_photo_bytes(),
                              "image/jpeg").sha256
    inputs = PF._inputs(cir, scope="full_make", made={"coaster": 4}, lies_flat=True,
                        tester_ref=FIXTURE_TESTER)
    # (No `notes`: free-text tester notes read as a recorded problem and make it PARTIAL. The
    # FIXTURE label is carried by the tester agreement's consent source and the photo note.)
    inputs["photos"] = [{"sha256": sha, "source": "tester", "rights_basis": "tester_agreement",
                         "taken_by": FIXTURE_TESTER, "unedited": True, "note": FIXTURE}]
    record = JobQueue(db).enqueue("quality_director", "physical.record", inputs).id
    _drain(db, "w6-e2e-physical",
           job_types=["physical.record", "physical.photo", "assets.physical_upgrade"])
    with db.session() as s:
        photo = s.scalar(select(PhysicalPhoto).where(PhysicalPhoto.sha256 == sha))
        pid = photo.id
    attested = PU.attest_unedited(db, pid, actor=FIXTURE_OWNER,
                                  confirm=PU.UNEDITED_CONFIRMATION)
    package_job = _enqueue_cadence(db, "listing_package", 1)       # the next cadence window
    _drain(db, "w6-e2e-package-2", job_types=["listing.package"])
    jobs = [j for j in _jobs(db) if j["id"] >= record]
    w["sample"] = {"record": record, "photo_id": pid, "sha": sha, "attested": attested,
                   "jobs": jobs, "links": _links(db), "package_job": package_job,
                   "requirement": SP.requirement(db, SLUG, w["version"]),
                   "package": copy.deepcopy(LP.latest(db, SLUG, w["version"]))}
    return w["sample"]


def test_d_a_fixture_sample_through_the_real_intake_moves_the_package_to_its_next_state():
    w = _world()
    d = _with_sample()
    db = w["db"]
    by_type = {j["type"]: j for j in d["jobs"]}
    rec = by_type["physical.record"]
    assert rec["status"] is JobStatus.DONE, rec["error"][:400]
    out = rec["outputs"]
    assert out["outcome"] == "PASS" and out["size_proof"] is True, out
    assert out["content_hash"] == w["release"] and out["physical_test_id"]
    with db.session() as s:
        test = s.get(PhysicalTest, out["physical_test_id"])
        assert test.passed and test.measured["evidence_class"] == "full_physical_make"
        assert test.measured["tester_agreement"]["relationship"] == "none"
    # The photo came in through the intake inside physical.record, bound to that make.
    assert [p["photo_id"] for p in out["photos"]] == [d["photo_id"]]
    assert out["photos"][0]["may_use"] is True
    assert d["attested"]["attested"] is True and d["attested"]["moved_to_front"] is True
    req = d["requirement"]
    assert [q["photo_id"] for q in req["qualifying"]] == [d["photo_id"]], req
    assert req["satisfied"] is False
    pkg = d["package"]
    assert pkg["state"] == LP.BLOCKED, pkg["state"]
    keys = [_blocker_key(b) for b in pkg["blockers"]]
    assert len(keys) == len(set(keys)) and set(keys) == BLOCKERS_D, keys
    photo = next(b["why"] for b in pkg["blockers"] if b["why"].startswith(SP.CODE))
    assert "not in a valid listing-set certificate for this release yet" in photo, photo
    cert = next(b["why"] for b in pkg["blockers"] if b["why"].startswith("listing-set"))
    assert "DATA_TRUTH" in cert and "COMMERCIAL_QA" in cert, cert
    with db.session() as s:
        lead = min(s.scalars(select(ListingAsset).where(ListingAsset.product_slug == SLUG)),
                   key=lambda f: f.position)
        assert lead.asset_class == "PHYSICAL_PRODUCT_PHOTO" and lead.sha256 == d["sha"]
        assert lead.approved is False      # nothing here approved it; asset truth has not run
        assert not list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{LP.ACTION_PREFIX}%"))))


def test_d_the_real_upgrade_job_completes_with_the_frame_provenance_recorded():
    """L0 P0-PHYSICAL-UPGRADE-PROVENANCE (was the pinned CHAIN DEFECT): `assets.physical_upgrade`
    records the PHYSICAL_PRODUCT_PHOTO frame's `visual_truth` lineage with the frame, so on a
    database the chain built itself the job is DONE, its provenance row names this job, and
    the provenance backlog stays closed (enforcement is not switched off by the frame)."""
    from brambleloop.core.models import ArtefactProvenance, ListingAsset
    from brambleloop.ops import artefacts as P

    d = _with_sample()
    up = [j for j in d["jobs"] if j["type"] == "assets.physical_upgrade"]
    assert len(up) == 1, [(j["id"], j["type"]) for j in d["jobs"]]
    assert d["links"][up[0]["id"]] == d["record"]       # enqueued by physical.record itself
    assert up[0]["status"] is JobStatus.DONE, (up[0]["status"], up[0]["error"][:400])
    with _world()["db"].session() as s:
        photo = s.get(PhysicalPhoto, d["photo_id"])
        assert photo.state == "upgrade_queued"
        frame = s.scalar(select(ListingAsset).where(
            ListingAsset.asset_class == "PHYSICAL_PRODUCT_PHOTO",
            ListingAsset.sha256 == photo.sha256))
        assert frame is not None
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "visual_truth",
            ArtefactProvenance.artefact_key == P.visual_key(frame.product_slug, frame.version,
                                                             frame.id)))
        assert row is not None and row.job_id == up[0]["id"] and row.source == "recorded"
        assert P.lineage_gaps(row, job_id=up[0]["id"]) == []
        assert P.may_enforce_unproven(s)["may_enforce_unproven"] is True

if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            import traceback

            fails += 1
            print("FAIL", name, repr(e)[:600])
            traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
