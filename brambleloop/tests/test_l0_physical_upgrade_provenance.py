"""L0 P0-PHYSICAL-UPGRADE-PROVENANCE (Main 6719551012 / 6719697398).

`assets.physical_upgrade` (publish.physical_upgrade.plan_upgrade) wrote the camera photo's
PHYSICAL_PRODUCT_PHOTO gallery frame with no `visual_truth` provenance row. On a database whose
provenance backlog is closed the worker's backstop refused the job (DEAD, "provenance refused")
AFTER the frame and the photo's `upgrade_queued` state had committed: the orphan frame then
turned provenance enforcement OFF estate-wide (`prior_unproven`), and the backfill could not
prove it (a camera photo is never an assets.build output), so it stayed off; the photo was
stuck ("already upgraded").

Pinned here, on the real intake / attestation / planner / backfill:
* the frame's visual_truth lineage is recorded with the frame, naming the photo by hash;
* frame + provenance + photo state are atomic: a refused lineage leaves no frame, the photo
  is not marked upgraded, and a retry then succeeds;
* an orphan frame left by the old defect is proven by the daily backfill from its intake row
  (hash-matched), so it cannot hold enforcement off; a frame whose photo hash does not match
  stays unproven;
* the real `assets.physical_upgrade` job records the lineage under its own job id.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_l0_physical_upgrade_provenance.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

import test_physfix_photo_first as PF  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    ArtefactProvenance, JobStatus, ListingAsset, PhysicalPhoto,
)
from brambleloop.ops import artefacts as P  # noqa: E402
from brambleloop.ops import backfill  # noqa: E402
from brambleloop.publish import physical_upgrade as pu  # noqa: E402


def _ready(db=None):
    """A certified basket with a passed full make, a rendered gallery and an attested photo."""
    db = db or PF._db()
    cir, _release = PF._certified_basket(db)
    test_id = PF._passed_full_make(db, cir)
    PF._render_gallery(db, cir)
    sha = ArtifactStore().put("sample.jpg", b"unedited camera file of the made basket",
                              "image/jpeg").sha256
    rec = pu.intake(db, slug=cir.slug, version=cir.version, source="tester", sha256=sha,
                    rights_basis="tester_agreement", taken_by="tester-1",
                    physical_test_id=test_id, unedited=True)
    pu.attest_unedited(db, rec["photo_id"], actor=PF.OWNER, confirm=pu.UNEDITED_CONFIRMATION)
    return db, cir, rec["photo_id"], sha


def _run_upgrade(db, photo_id):
    """The real assets.physical_upgrade job, enqueued as `physical.photo` enqueues it."""
    from brambleloop.core.models import Job
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    job = JobQueue(db).enqueue("publishing", "assets.physical_upgrade",
                               {"photo_id": photo_id}, priority=0,
                               idempotency_key=f"physical_upgrade:{photo_id}")
    Worker(db, "w-upgrade", job_types=["assets.physical_upgrade"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


JOB_LINEAGE = P.Lineage(created_by="publishing", job_id=4242, validation_status="blocked")


def _photo_frames(db, cir):
    with db.session() as s:
        return [(f.id, f.position, f.sha256) for f in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version,
            ListingAsset.asset_class == "PHYSICAL_PRODUCT_PHOTO"))]


def _visual_row(db, cir, frame_id):
    with db.session() as s:
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "visual_truth",
            ArtefactProvenance.artefact_key == P.visual_key(cir.slug, cir.version, frame_id)))
        if row is None:
            return None
        s.expunge(row)
        return row


def test_the_photo_frame_is_recorded_with_its_visual_truth_lineage():
    db, cir, photo_id, sha = _ready()
    plan = pu.plan_upgrade(db, photo_id, lineage=JOB_LINEAGE)
    assert plan["upgraded"], plan
    [(fid, _pos, fsha)] = _photo_frames(db, cir)
    row = _visual_row(db, cir, fid)
    assert row is not None and fsha == sha and row.sha256 == sha
    assert (row.inputs or {}) == {f"asset:physical_photo_{photo_id}": sha}, row.inputs
    assert row.created_by == "publishing" and row.job_id == 4242 and row.source == "recorded"
    assert row.validation_status == "blocked"       # unapproved until asset truth re-runs
    _assert_unapproved(db, fid)


def test_a_direct_call_outside_a_job_invents_no_lineage():
    """A recorded lineage must name its job; a caller with none records nothing."""
    db, cir, photo_id, _sha = _ready()
    assert pu.plan_upgrade(db, photo_id)["upgraded"]
    [(fid, _pos, _s)] = _photo_frames(db, cir)
    assert _visual_row(db, cir, fid) is None


def test_frame_provenance_and_photo_state_are_atomic_on_a_refused_lineage():
    db, cir, photo_id, _sha = _ready()
    with db.session() as s:
        before = sorted((f.id, f.position) for f in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug)))
    saved = P.record_lineage

    def refuse(*_a, **_k):
        raise P.ProvenanceRefused("refused for the test")

    P.record_lineage = refuse
    try:
        try:
            pu.plan_upgrade(db, photo_id, lineage=JOB_LINEAGE)
        except P.ProvenanceRefused:
            pass
        else:
            raise AssertionError("a refused lineage was swallowed")
    finally:
        P.record_lineage = saved
    assert _photo_frames(db, cir) == [], "a refused lineage left a half-written frame"
    with db.session() as s:
        after = sorted((f.id, f.position) for f in s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug)))
        photo = s.get(PhysicalPhoto, photo_id)
        assert photo.state != "upgrade_queued", photo.state      # still retryable
        assert "planned_on" not in (photo.detail or {})
    assert after == before, (before, after)                     # no frame was renumbered
    plan = pu.plan_upgrade(db, photo_id, lineage=JOB_LINEAGE)    # the retry completes
    assert plan["upgraded"] and len(_photo_frames(db, cir)) == 1, plan


def test_an_orphan_frame_from_a_refused_upgrade_is_proven_by_the_backfill():
    """The old defect's leftover (a frame with no provenance) cannot hold enforcement off:
    the daily `ops.provenance_backfill` proves it from its hash-matched intake row."""
    db, cir, photo_id, sha = _ready()
    saved = pu.plan_upgrade
    # the pre-fix planner, run by the real job: it writes the frame and no lineage
    pu.plan_upgrade = lambda db_, pid, **kw: saved(db_, pid, **{**kw, "lineage": None})
    try:
        job = _run_upgrade(db, photo_id)
    finally:
        pu.plan_upgrade = saved
    [(fid, _pos, _s)] = _photo_frames(db, cir)
    assert _visual_row(db, cir, fid) is None                      # the orphan
    key = ("visual_truth", P.visual_key(cir.slug, cir.version, fid))
    with db.session() as s:
        gate = P.graduation(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
        assert key in {tuple(k) for k in gate["instrument"]}, gate["instrument"]
    with db.session() as s:
        report = backfill.run(s)
    row = _visual_row(db, cir, fid)
    assert row is not None and row.source == "backfilled" and row.sha256 == sha, report
    assert (row.inputs or {}) == {f"asset:physical_photo_{photo_id}": sha}
    assert (row.evidence or {}).get("physical_photo_id") == photo_id, row.evidence
    assert row.job_id == job.id and row.created_by == "publishing", (row.job_id, job.id)
    with db.session() as s:
        gate = P.graduation(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
        assert key not in {tuple(k) for k in gate["instrument"]}, gate["instrument"]


def test_a_camera_frame_whose_photo_hash_differs_stays_unproven():
    db, cir, photo_id, _sha = _ready()
    _run_upgrade(db, photo_id)                    # the photo's upgrade job exists
    other = ArtifactStore().put("x.jpg", b"some other file", "image/jpeg").sha256
    with db.session() as s:
        s.add(ListingAsset(product_slug=cir.slug, version=cir.version, position=50,
                           asset_class="PHYSICAL_PRODUCT_PHOTO", role="proof", sha256=other,
                           claims={"physical_photo_id": photo_id}, approved=False,
                           blocked_reasons=["x"]))
    with db.session() as s:
        backfill.run(s)
    fid = next(f for f, _p, sh in _photo_frames(db, cir) if sh == other)
    assert _visual_row(db, cir, fid) is None, "a hash mismatch was proven"
    with db.session() as s:
        frame = s.get(ListingAsset, fid)
        frame.claims = {}                                         # names no photo at all
    with db.session() as s:
        backfill.run(s)
    assert _visual_row(db, cir, fid) is None


def test_a_frame_of_another_product_naming_the_photo_stays_unproven():
    """The photo is proof only for the product it was taken of."""
    db, cir, photo_id, sha = _ready()
    _run_upgrade(db, photo_id)
    with db.session() as s:
        s.add(ListingAsset(product_slug="some-other-product", version=cir.version,
                           position=1, asset_class="PHYSICAL_PRODUCT_PHOTO", role="proof",
                           sha256=sha, claims={"physical_photo_id": photo_id},
                           approved=False, blocked_reasons=["x"]))
    with db.session() as s:
        backfill.run(s)
        fid = s.scalar(select(ListingAsset.id).where(
            ListingAsset.product_slug == "some-other-product"))
    with db.session() as s:
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "visual_truth",
            ArtefactProvenance.artefact_key == P.visual_key("some-other-product",
                                                             cir.version, fid)))
        assert row is None, "a photo of one product proved another product's frame"


def test_an_orphan_frame_with_no_upgrade_job_stays_unproven():
    """Backfill needs the job that made the frame: a hash-matched photo alone is not enough."""
    db, cir, photo_id, _sha = _ready()
    assert pu.plan_upgrade(db, photo_id)["upgraded"]            # no job ever ran
    [(fid, _pos, _s)] = _photo_frames(db, cir)
    with db.session() as s:
        report = backfill.run(s)
    assert _visual_row(db, cir, fid) is None, report


def test_the_real_upgrade_job_records_the_lineage_under_its_own_job_id():
    db, cir, photo_id, sha = _ready()
    job = _run_upgrade(db, photo_id)
    assert job.status is JobStatus.DONE, (job.status, (job.last_error or "")[:400])
    [(fid, _pos, _s)] = _photo_frames(db, cir)
    row = _visual_row(db, cir, fid)
    assert row is not None and row.job_id == job.id and row.sha256 == sha, row
    assert row.created_by == job.agent and row.validation_status == "blocked"
    assert P.lineage_gaps(row, job_id=job.id) == [], P.lineage_gaps(row, job_id=job.id)
    _assert_unapproved(db, fid)


def _assert_unapproved(db, fid):
    """Review L0 MED-2: the frame is never approved by planning the upgrade."""
    with db.session() as s:
        frame = s.get(ListingAsset, fid)
        assert frame.approved is False, "planning the upgrade approved the frame"
        assert frame.blocked_reasons == [
            "awaiting asset-truth review and listing-set re-certification"], (
            frame.blocked_reasons)


def _verdict(db, cir, fid):
    with db.session() as s:
        current = P.current_from_db(s)
        key = P.visual_key(cir.slug, cir.version, fid)
        return next(v for v in P.check(s, current=current)
                    if v.artefact_class == "visual_truth" and v.artefact_key == key)


def test_the_sentinel_reads_the_recorded_frame_fresh_and_raises_no_halt():
    """Review L0 HIGH-1: the frame's `asset:physical_photo_<id>` input has a current
    fingerprint (the stored photo's hash), so the sentinel reads it FRESH and opens no
    publication-halting stale-artefact incident; a changed photo hash reads STALE."""
    from brambleloop.core.models import Incident

    db, cir, photo_id, sha = _ready()
    job = _run_upgrade(db, photo_id)
    assert job.status is JobStatus.DONE, job.last_error
    [(fid, _pos, _s)] = _photo_frames(db, cir)
    with db.session() as s:
        current = P.current_from_db(s)
        assert current[f"asset:physical_photo_{photo_id}"] == sha
    v = _verdict(db, cir, fid)
    assert v.state == P.FRESH, (v.state, v.why)
    with db.session() as s:
        P.sweep(s, current=P.current_from_db(s))
    with db.session() as s:
        key = P.visual_key(cir.slug, cir.version, fid)
        halts = [i for i in s.scalars(select(Incident).where(Incident.resolved.is_(False)))
                 if key in (i.signature or "") or key in (i.summary or "")]
        assert halts == [], [(i.signature, i.summary) for i in halts]
    # honesty: if the stored photo's hash were to change, the frame is no longer fresh
    with db.session() as s:
        s.get(PhysicalPhoto, photo_id).sha256 = "0" * 64
    assert _verdict(db, cir, fid).state == P.STALE


def test_generated_frames_have_a_current_fingerprint_too():
    """Review L0 HIGH-1 (latent twin): `asset:image_candidate_<id>` (visual.gallery_persist)
    is published from the stored candidate's hash."""
    from brambleloop.visual.image_records import ImageCandidate

    db, cir, _photo_id, _sha = _ready()
    with db.session() as s:
        c = ImageCandidate(sha256="a" * 64, run_key="r", method="autonomous",
                           provenance_kind="ai_generated_autonomous", slug=cir.slug,
                           version=cir.version, release="r" * 64, listing="l",
                           role="lifestyle", technical_status="PASS")
        s.add(c)
        s.flush()
        cid = c.id
    with db.session() as s:
        assert P.current_from_db(s)[f"asset:image_candidate_{cid}"] == "a" * 64


def test_backfill_credits_only_an_upgrade_job_that_wrote_the_frame():
    """Review L0 LOW-3: DONE, or DEAD by the provenance backstop alone (the pre-fix orphan);
    any other job state proves nothing. An approved frame is backfilled `passed`."""
    from brambleloop.core.models import Job

    cases = (
        (JobStatus.DEAD, "provenance refused: visual_truth x has no lineage", True),
        (JobStatus.DEAD, "ValueError: something else", False),
        (JobStatus.FAILED, "provenance refused: visual_truth x", False),
        (JobStatus.PENDING, "", False),
        (JobStatus.RUNNING, "", False),
    )
    for status, err, proven in cases:
        db, cir, photo_id, _sha = _ready()
        saved = pu.plan_upgrade
        pu.plan_upgrade = lambda db_, pid, **kw: saved(db_, pid, **{**kw, "lineage": None})
        try:
            job = _run_upgrade(db, photo_id)
        finally:
            pu.plan_upgrade = saved
        with db.session() as s:
            row = s.get(Job, job.id)
            row.status, row.last_error = status, err
        [(fid, _pos, _s)] = _photo_frames(db, cir)
        with db.session() as s:
            backfill.run(s)
        got = _visual_row(db, cir, fid)
        assert (got is not None) == proven, (status, err, got)
    # an approved frame (A3 approved it) is backfilled as passed
    db, cir, photo_id, _sha = _ready()
    saved = pu.plan_upgrade
    pu.plan_upgrade = lambda db_, pid, **kw: saved(db_, pid, **{**kw, "lineage": None})
    try:
        _run_upgrade(db, photo_id)
    finally:
        pu.plan_upgrade = saved
    [(fid, _pos, _s)] = _photo_frames(db, cir)
    with db.session() as s:
        s.get(ListingAsset, fid).approved = True
    with db.session() as s:
        backfill.run(s)
    assert _visual_row(db, cir, fid).validation_status == "passed"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
