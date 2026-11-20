"""OPUS2: the automatic listing package (INTEG-LISTING-JOB), on the real release chain.

A real certification, a real `assets.build` and a drafted listing on a scratch database in
SHADOW, with sockets closed. The package is assembled only from what that chain stored, and
nothing is published. The owner's review request appears only when nothing blocks the package.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_listing_package.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="opus2_listing_package_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    EtsyTaxonomySnapshot, Job, JobStatus, Listing, OperatingReading, OwnerAction, PatternVersion,
    Phase,
)
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, Worker, handlers  # noqa: E402

_CACHE: dict = {}


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
    """The blanket certified, its assets built and its copy drafted, on a fresh DB."""
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
                      tags=["baby blanket crochet"], price_cad=7.5, state="draft",
                      release_hash=rh))
    return db, cir, rh


def _shared():
    if "rel" not in _CACHE:
        _CACHE["rel"] = _release("shared")
    return _CACHE["rel"]


def test_the_job_is_registered_scheduled_and_never_publishes():
    from brambleloop.authority import classes
    from brambleloop.autonomy import charters

    assert handlers.get("listing.package") is not None
    assert ("listing_package", "listing", "listing.package", 6 * 60 * 60) in CADENCES
    Registry(_db("reg")).authorize("listing", "listing.package")
    # Review OPUS2F A-6: it writes internally (via for_publish too), so BUILD like chain.rebuild.
    assert classes.JOB_CLASS["listing.package"] == classes.JOB_CLASS["chain.rebuild"]
    assert charters.department_of("listing.package") == "store_commerce"
    assert "listing.package" not in charters.PROTECTED_JOB_TYPES


def test_a_package_is_assembled_from_the_chains_own_stored_outputs():
    db, cir, rh = _shared()
    pkg = LP.assemble(db, cir.slug, cir.version)
    assert pkg is not None and pkg["release_hash"] == rh and pkg["publishes"] is False
    # Files: the PDFs assets.build stored for this exact release.
    files = pkg["files"]
    assert files and set(files["pdf_sha256_by_terminology"]) >= {"US"}
    for sha in files["pdf_sha256_by_terminology"].values():
        assert ArtifactStore().get(sha, db=db)            # bytes are on file under the hash
    # Identity from the certified pattern version and launch0.
    assert pkg["identity"]["risk_class"] == cir.risk_class
    assert pkg["identity"]["childrens_decision"] is not None
    # Every blocker names the reader it came from; nothing is silently dropped.
    assert all(b["source"] and b["why"] for b in pkg["blockers"])
    assert pkg["state"] == (LP.READY if not pkg["blockers"] else LP.BLOCKED)
    # Where the payload builder answers, the copy is exactly what store.publish would send.
    if pkg["copy"] is not None:
        from brambleloop.runtime import etsy_ops

        assert pkg["copy"] == etsy_ops.sent_fields(etsy_ops.certified_payload(
            db, cir.slug, cir.version))
    else:
        assert any(b["source"] == "certified_payload" for b in pkg["blockers"])


def test_in_shadow_with_no_sample_photo_the_package_is_blocked_and_no_review_is_asked():
    db, cir, _rh = _release("shadow")          # its own DB: other tests record packages
    out = _run(db, "listing", "listing.package", {}, "p1")
    assert out.status is JobStatus.DONE, out.last_error
    assert out.outputs["publishes"] is False and out.outputs["releases"] == 1
    pkg = LP.latest(db, cir.slug, cir.version)
    assert pkg["state"] == LP.BLOCKED and pkg["blockers"], pkg["state"]
    assert pkg["markdown_sha256"]
    md = ArtifactStore().get(pkg["markdown_sha256"], db=db).decode()
    for section in ("## 1. Title", "## 2. Description", "## 4. Tags", "## 6. Digital files",
                    "## 7. Disclosures", "## 8. Gallery", "## 9. Outstanding publication"):
        assert section in md, section
    with db.session() as s:
        assert not list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{LP.ACTION_PREFIX}%"))))
    # Idempotent: an unchanged chain rewrites nothing.
    again = _run(db, "listing", "listing.package", {}, "p2")
    assert again.outputs["changed"] == 0 and not pipeline.did_no_work(
        out.outputs, "listing.package") and pipeline.did_no_work(again.outputs,
                                                                 "listing.package")
    with db.session() as s:
        assert len(list(s.scalars(select(OperatingReading).where(
            OperatingReading.kind == LP.KIND)))) == 1


def _requests(db, cir, *, open_only=False):
    with db.session() as s:
        q = select(OwnerAction).where(OwnerAction.requirement_key.like(
            f"{LP.ACTION_PREFIX}{cir.slug}@{cir.version}:%"))
        if open_only:
            q = q.where(OwnerAction.done == False)  # noqa: E712
        return list(s.scalars(q.order_by(OwnerAction.id)))


def _source_checked_fixture(db, cir, package):
    """When simulating READY, bind the fixture to the actual stored Listing copy.

    The publication gate is still synthetic. This does not assert release eligibility.
    """
    with db.session() as session:
        listing = session.scalar(select(Listing).where(
            Listing.product_slug == cir.slug, Listing.version == cir.version))
        copy = {"title": listing.title, "description": listing.description, "tags": listing.tags}
    return {**package, "copy": copy, "listing_snapshot_sha256": LP.listing_copy_digest(copy),
            "source_snapshot_sha256": LP._release(db, cir.slug, cir.version)["source_snapshot_sha256"]}


def test_a_ready_package_asks_for_one_review_and_a_new_blocker_withdraws_it():
    db, cir, _rh = _release("ready")
    pkg = _source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version))
    ready = {**pkg, "state": LP.READY, "blockers": [], "fingerprint": "a" * 64}
    r1 = LP.record(db, ready)
    r2 = LP.record(db, ready)                                   # unchanged: not asked twice
    assert r1["review_requested"] is True and r2["review_requested"] is False
    open_ = _requests(db, cir, open_only=True)
    assert len(open_) == 1 and open_[0].max_cost_cad == 0.0
    assert "Publishing remains your decision" in open_[0].reason
    blocked = {**pkg, "state": LP.BLOCKED,
               "blockers": [{"source": "fixture", "why": "a new defect"}], "fingerprint": "b" * 64}
    r3 = LP.record(db, blocked)
    assert r3["review_withdrawn"] is True and _requests(db, cir, open_only=True) == []
    row = _requests(db, cir)[0]
    assert row.state == "superseded" and "a new defect" in row.state_reason


def test_review_opus2f_a2_a_review_the_owner_completed_is_never_asked_again():
    db, cir, _rh = _release("a2")
    ready = {**_source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version)), "state": LP.READY, "blockers": [],
             "fingerprint": "c" * 64}
    LP.record(db, ready)
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key.like(
            f"{LP.ACTION_PREFIX}%")))
        row.done, row.state = True, "satisfied"
    again = LP.record(db, ready)
    assert again["review_requested"] is False and len(_requests(db, cir)) == 1


def test_review_opus2f_a3_a_changed_ready_package_supersedes_the_stale_request():
    db, cir, _rh = _release("a3")
    # Simulate two certified release snapshots by changing both persisted sources.
    with db.session() as session:
        pv = session.scalar(select(PatternVersion))
        listing = session.scalar(select(Listing).where(Listing.product_slug == cir.slug))
        pv.release_hash = listing.release_hash = "1" * 64
    base = {**_source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version)),
            "state": LP.READY, "blockers": []}
    LP.record(db, {**base, "release_hash": "1" * 64, "fingerprint": "d" * 64})
    assert len(_requests(db, cir, open_only=True)) == 1
    with db.session() as session:
        pv = session.scalar(select(PatternVersion))
        listing = session.scalar(select(Listing).where(Listing.product_slug == cir.slug))
        pv.release_hash = listing.release_hash = "2" * 64
    # Review U6 H1: the A9 listing-package fence withdraws the stale request in the same
    # transaction that changes the release, before any new package is assembled.
    assert _requests(db, cir, open_only=True) == []
    stale = [r for r in _requests(db, cir) if r.requirement_key.endswith("d" * 16)]
    assert len(stale) == 1 and stale[0].state == "superseded", [
        (r.requirement_key, r.state) for r in _requests(db, cir)]
    updated = _source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version))
    r = LP.record(db, {**updated, "state": LP.READY, "blockers": [],
                       "release_hash": "2" * 64, "fingerprint": "e" * 64})
    # Nothing is left for record() to withdraw: the fence already did it.
    assert r["review_requested"] is True and r["review_withdrawn"] is False
    open_ = _requests(db, cir, open_only=True)
    assert len(open_) == 1 and "222222222222" in open_[0].reason
    assert open_[0].requirement_key.endswith("e" * 16)


def test_review_opus2f_a1_a_pdf_from_another_release_is_never_this_releases_file():
    from brambleloop.core.models import AuditLog

    db, cir, rh = _release("a1")
    with db.session() as s:
        stray = Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
                    inputs={"slug": cir.slug, "version": cir.version},      # no release
                    outputs={"pdf_sha256_by_terminology": {"US": "0" * 64}})
        s.add(stray)
        s.flush()
        s.add(AuditLog(actor="publishing", action="assets.built", job_id=stray.id,
                       artifact=f"{cir.slug}@{cir.version}",
                       detail={"pdf_sha256_by_terminology": {"US": "0" * 64}}))
    files = LP._files(db, cir.slug, cir.version, rh)
    assert files and "0" * 64 not in files["pdf_sha256_by_terminology"].values()
    assert LP._files(db, cir.slug, cir.version, "") is None       # empty release binds nothing
    assert LP._files(db, cir.slug, cir.version, "9" * 64) is None  # another release: none


def test_review_opus2f_a4_copy_written_for_another_release_blocks():
    db, cir, rh = _release("a4")
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == cir.slug))
        row.release_hash = "7" * 64
    pkg = _source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version))
    assert any(b["source"] == "listing" and "written for release" in b["why"]
               for b in pkg["blockers"]), pkg["blockers"]
    # A second row for the same slug@version cannot exist: the database refuses it, so the
    # package and certified_payload always read the same listing.
    import sqlalchemy.exc

    try:
        with db.session() as s:
            s.add(Listing(product_slug=cir.slug, version=cir.version, title="x",
                          description="y", tags=[], price_cad=1.0, state="draft",
                          release_hash=rh))
    except sqlalchemy.exc.IntegrityError:
        pass
    else:
        raise AssertionError("two listing rows for one release were accepted")


def test_review_opus2f_a5_the_rendered_gallery_shows_each_images_alt_text():
    pkg = {"slug": "s", "version": "1.0.0", "state": LP.BLOCKED, "release_hash": "r",
           "identity": {}, "copy": None, "files": {}, "disclosures": [], "blockers": [],
           "gallery": [{"position": 1, "kind": "sample_photo", "sha256": "a" * 64,
                        "honesty_label": None, "alt_text": "A folded blanket on a chair"},
                       {"position": 2, "kind": "chart", "sha256": "b" * 64,
                        "honesty_label": None, "alt_text": None}]}
    text = LP.render(pkg)
    assert "   Alt text: A folded blanket on a chair" in text
    assert text.count("Alt text:") == 1                 # no empty alt line is invented


def test_review_opus2f_a8_one_release_failing_to_record_does_not_stop_the_sweep():
    db, cir, _rh = _shared()
    real_releases, real_record = LP.certified_releases, LP.record
    LP.certified_releases = lambda _db: [("broken", "9.9.9"), (cir.slug, cir.version)]
    real_assemble = LP.assemble
    LP.assemble = lambda d, slug, version: ({"slug": "broken", "version": "9.9.9",
                                             "state": LP.BLOCKED}
                                            if slug == "broken" else real_assemble(d, slug,
                                                                                    version))

    def record(d, package, **k):
        if package["slug"] == "broken":
            raise RuntimeError("record failed for this one release")
        return real_record(d, package, **k)

    LP.record = record
    try:
        out = LP.sweep(db)
    finally:
        LP.certified_releases, LP.record, LP.assemble = real_releases, real_record, real_assemble
    keys = [r.get("key") for r in out["results"]]
    assert out["releases"] == 2 and keys[0] == "broken@9.9.9"
    assert "record failed" in out["results"][0]["error"]
    assert keys[1] == f"{cir.slug}@{cir.version}" and "error" not in out["results"][1]


def test_review_opus2ef2_ef24_ready_blocked_ready_asks_the_owner_again():
    db, cir, _rh = _release("ef24")
    pkg = _source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version))
    ready = {**pkg, "state": LP.READY, "blockers": [], "fingerprint": "f" * 64}
    blocked = {**pkg, "state": LP.BLOCKED,
               "blockers": [{"source": "fixture", "why": "transient"}], "fingerprint": "9" * 64}
    assert LP.record(db, ready)["review_requested"] is True
    assert LP.record(db, blocked)["review_withdrawn"] is True
    back = LP.record(db, ready)                  # same content again: the owner never answered
    assert back["review_requested"] is True, back
    assert len(_requests(db, cir, open_only=True)) == 1
    # A withdrawal by the owner, unlike the job's own supersede, is an answer: not re-asked.
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.done == False,  # noqa: E712
                                                 OwnerAction.requirement_key.like(
                                                     f"{LP.ACTION_PREFIX}%")))
        row.done, row.state = True, "withdrawn"
    assert LP.record(db, ready)["review_requested"] is False


def test_review_opus2ef2_ef25_a_request_under_the_legacy_key_is_superseded():
    db, cir, _rh = _release("ef25")
    legacy = f"{LP.ACTION_PREFIX}{cir.slug}@{cir.version}"
    with db.session() as s:
        s.add(OwnerAction(requirement_key=legacy, action="old review", reason="r"))
    ready = {**_source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version)), "state": LP.READY, "blockers": [],
             "fingerprint": "7" * 64}
    out = LP.record(db, ready)
    assert out["review_requested"] is True and out["review_withdrawn"] is True
    open_ = _requests(db, cir, open_only=True)
    assert len(open_) == 1 and open_[0].requirement_key.endswith("7" * 16)


def test_review_opus2g_l51_an_owner_deferral_survives_a_transient_block():
    db, cir, _rh = _release("l51")
    pkg = _source_checked_fixture(db, cir, LP.assemble(db, cir.slug, cir.version))
    ready = {**pkg, "state": LP.READY, "blockers": [], "fingerprint": "6" * 64}
    blocked = {**pkg, "state": LP.BLOCKED,
               "blockers": [{"source": "fixture", "why": "transient"}], "fingerprint": "5" * 64}
    LP.record(db, ready)
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key.like(
            f"{LP.ACTION_PREFIX}%")))
        row.state = "parked"
    LP.record(db, blocked)
    LP.record(db, ready)
    rows = _requests(db, cir)
    assert len(rows) == 1 and rows[0].state == "parked", [(r.state, r.done) for r in rows]
    # Review U6 H1: a new fingerprint whose rendered owner question is byte-identical is
    # the same question, so the owner's deferral stands and nothing new is raised.
    assert LP.render({**ready, "fingerprint": "3" * 64}) == LP.render(ready)
    same = LP.record(db, {**ready, "fingerprint": "3" * 64})
    assert same["review_requested"] is False and same["review_withdrawn"] is False, same
    rows = _requests(db, cir)
    assert len(rows) == 1 and rows[0].state == "parked", [(r.state, r.done) for r in rows]
    # New rendered content is a new question: the parked request is superseded and a new
    # one is raised.
    new_question = {**ready, "fingerprint": "4" * 64,
                    "disclosures": [*(ready.get("disclosures") or []),
                                    "U6 H1 fixture: a disclosure the owner has not seen"]}
    assert LP.render(new_question) != LP.render(ready)
    changed = LP.record(db, new_question)
    assert changed["review_requested"] is True and changed["review_withdrawn"] is True
    open_ = _requests(db, cir, open_only=True)
    assert len(open_) == 1 and open_[0].requirement_key.endswith("4" * 16)


def test_an_uncertified_or_unlisted_release_gets_no_package():
    db = _db("empty")
    assert LP.certified_releases(db) == [] and LP.assemble(db, "nope", "1.0.0") is None
    out = _run(db, "listing", "listing.package", {}, "e")
    assert out.outputs["releases"] == 0 and pipeline.did_no_work(out.outputs, "listing.package")


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
