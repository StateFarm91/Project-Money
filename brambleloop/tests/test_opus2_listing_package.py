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
    assert classes.JOB_CLASS["listing.package"] == classes.JOB_CLASS["listing.outcomes"]
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


def test_a_ready_package_asks_for_one_review_and_a_new_blocker_withdraws_it():
    db, cir, _rh = _shared()
    pkg = LP.assemble(db, cir.slug, cir.version)
    ready = {**pkg, "state": LP.READY, "blockers": [], "fingerprint": "ready-fixture"}
    r1 = LP.record(db, ready)
    r2 = LP.record(db, {**ready, "fingerprint": "ready-fixture-2"})
    assert r1["review_requested"] is True and r2["review_requested"] is False
    with db.session() as s:
        open_ = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == f"{LP.ACTION_PREFIX}{cir.slug}@{cir.version}",
            OwnerAction.done == False)))  # noqa: E712
    assert len(open_) == 1 and open_[0].max_cost_cad == 0.0
    assert "Publishing remains your decision" in open_[0].reason
    blocked = {**pkg, "state": LP.BLOCKED,
               "blockers": [{"source": "fixture", "why": "a new defect"}],
               "fingerprint": "blocked-fixture"}
    r3 = LP.record(db, blocked)
    assert r3["review_withdrawn"] is True
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"{LP.ACTION_PREFIX}{cir.slug}@{cir.version}"))
    assert row.done is True and row.state == "superseded" and "a new defect" in row.state_reason


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
