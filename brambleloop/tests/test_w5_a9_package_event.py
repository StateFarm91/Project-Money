"""W5-A9 (P0-PACKAGE-EVENT): the listing package is raised by the chain, not only by the sweep.

The real release chain runs from `gate.certify` on a SQLite FILE through `JobQueue` (the
durable queue) and `Worker.run_once` with every registered handler. No cadence is ticked and
no clock is advanced: the package exists because `launch.plan`, the last stage that writes what
the package reads, enqueued `listing.package` for that one release.

* In SHADOW the package is blocked, its blockers are exactly what the six-hourly sweep finds,
  no owner review is asked and `store.publish` stays refused.
* A re-delivered event is a duplicate key; a second event or the sweep afterwards writes no
  second package reading and no second owner-queue row.
* Where every gate passes (the gate reading is replaced by a READY one, the handler, `record`
  and the owner queue stay real) the event raises the owner's review request at once, and the
  sweep after it raises none.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w5_a9_package_event.py
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
_TMP = tempfile.mkdtemp(prefix="w5_a9_package_event_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    EtsyTaxonomySnapshot, Job, JobStatus, Listing, OperatingReading, OwnerAction, Phase,
)
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.queue.durable import DuplicateJob, JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

_STATE: dict = {}


def _db(name):
    path = Path(tempfile.mkdtemp(dir=_TMP)) / f"{name}.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    snap = FX.snapshot()
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    assert path.exists()                       # a real file, not :memory:
    return db


def _drain(db, name, limit=600):
    w = Worker(db, name, phase=Phase.SHADOW, lease_seconds=900)
    for _ in range(limit):
        if not w.run_once():
            break


def _jobs(db, job_type):
    with db.session() as s:
        rows = list(s.scalars(select(Job).where(Job.job_type == job_type).order_by(Job.id)))
        for r in rows:
            s.expunge(r)
        return rows


def _requests(db):
    with db.session() as s:
        return [(r.requirement_key, r.done, r.state) for r in s.scalars(
            select(OwnerAction).where(OwnerAction.requirement_key.like(
                f"{LP.ACTION_PREFIX}%")).order_by(OwnerAction.id))]


def _readings(db):
    with db.session() as s:
        return [(r.period_key, dict(r.payload or {})) for r in s.scalars(
            select(OperatingReading).where(OperatingReading.kind == LP.KIND))]


def _certify_and_drain(name):
    db = _db(name)
    cir = L.cir_for("cloudline_blanket")
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                         idempotency_key=f"{name}-certify", priority=0)
    _drain(db, f"{name}-chain")
    return db, cir


def _shadow():
    if not _STATE:
        db, cir = _certify_and_drain("shadow")
        # What the chain itself queued, before any test enqueues a package job of its own.
        _STATE.update(db=db, cir=cir, chain_packages=_jobs(db, "listing.package"))
    return _STATE["db"], _STATE["cir"]


def _run(db, inputs, key):
    job = JobQueue(db).enqueue("listing", "listing.package", inputs, idempotency_key=key,
                               priority=0)
    Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=["listing.package"],
           lease_seconds=900).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def test_certification_reaches_the_package_by_event_without_the_sweep():
    db, cir = _shadow()
    plans = _jobs(db, "launch.plan")
    assert plans and all(j.status is JobStatus.DONE for j in plans), \
        [(j.status, j.last_error) for j in plans]
    pkgs = _STATE["chain_packages"]
    # Package jobs raised by the chain (never a cadence), for this release only. One per
    # launch.plan run: an evergreen pivot (date-dependent) re-runs launch.plan once more.
    assert 1 <= len(pkgs) <= len(plans), [(j.idempotency_key, j.inputs) for j in pkgs]
    assert len({j.idempotency_key for j in pkgs}) == len(pkgs)
    for job in pkgs:
        assert job.status is JobStatus.DONE, job.last_error
        assert job.outputs["trigger"] == "event", job.outputs
    job = pkgs[0]
    assert job.status is JobStatus.DONE, job.last_error
    assert job.idempotency_key.startswith(f"package:{cir.slug}:{cir.version}:"), \
        job.idempotency_key
    assert not job.idempotency_key.startswith("cadence:")
    assert job.inputs["slug"] == cir.slug and job.inputs["version"] == cir.version
    assert job.outputs["trigger"] == "event" and job.outputs["eligible"] is True
    assert job.outputs["releases"] == 1 and job.outputs["publishes"] is False
    # The package reading exists now -- no 6 h cadence window had to pass.
    readings = _readings(db)
    assert [k for k, _ in readings] == [f"{cir.slug}@{cir.version}"], readings
    pkg = LP.latest(db, cir.slug, cir.version)
    assert pkg["release_hash"] and pkg["markdown_sha256"]


def test_in_shadow_the_event_package_is_blocked_exactly_as_the_sweep_finds_it():
    db, cir = _shadow()
    before = LP.latest(db, cir.slug, cir.version)
    assert before["state"] == LP.BLOCKED and before["blockers"], before["state"]
    assert _requests(db) == []                  # nothing ready, so nothing asked of the owner
    # The sweep (the safety net) re-assembles the same release and finds nothing to change:
    # same blockers, same fingerprint, one reading, no owner row.
    sweep = _run(db, {"cadence": "listing_package"}, "cadence:listing_package:sweep-1")
    assert sweep.status is JobStatus.DONE, sweep.last_error
    assert sweep.outputs["trigger"] == "sweep" and sweep.outputs["changed"] == 0
    assert pipeline.did_no_work(sweep.outputs, "listing.package")
    after = LP.latest(db, cir.slug, cir.version)
    assert after["blockers"] == before["blockers"]
    assert after["fingerprint"] == before["fingerprint"]
    assert len(_readings(db)) == 1 and _requests(db) == []
    # Etsy publication stays refused in SHADOW and nothing went live.
    publishes = _jobs(db, "store.publish")
    assert publishes and all(j.status is not JobStatus.DONE for j in publishes), \
        [(j.status, j.outputs) for j in publishes]
    with db.session() as s:
        assert all(r.state != "active" and not r.etsy_listing_id
                   for r in s.scalars(select(Listing)))


def test_a_redelivered_or_second_event_creates_no_duplicate():
    db, cir = _shadow()
    first = _STATE["chain_packages"][0]
    # The same event again is the same key: refused by the queue as a duplicate.
    try:
        JobQueue(db).enqueue("listing", "listing.package", dict(first.inputs),
                             idempotency_key=first.idempotency_key)
        raise AssertionError("a re-delivered package event was queued twice")
    except DuplicateJob:
        pass
    # A second event under another key (e.g. a rebuild) rewrites nothing.
    again = _run(db, dict(first.inputs), first.idempotency_key + ":again")
    assert again.status is JobStatus.DONE and again.outputs["changed"] == 0
    assert len(_readings(db)) == 1 and _requests(db) == []


def test_an_ineligible_release_is_left_to_the_sweep():
    db, _cir = _shadow()
    out = _run(db, {"slug": "no-such-product", "version": "1.0.0"}, "package:nope")
    assert out.status is JobStatus.DONE and out.outputs["eligible"] is False
    assert out.outputs["releases"] == 0 and len(_readings(db)) == 1


def test_when_every_gate_passes_the_event_asks_the_owner_once_and_the_sweep_adds_nothing():
    """The publication gates are replaced by a passing reading (they cannot pass in SHADOW);
    the event job, `record`, the owner queue and the sweep are the real ones."""
    real = LP.assemble

    def passing(db, slug, version):
        pkg = real(db, slug, version)
        if pkg is None:
            return None
        # The gate is synthetic, but the simulated READY copy must still be
        # the exact persisted Listing the real recorder will bind and review.
        with db.session() as session:
            listing = session.scalar(select(Listing).where(
                Listing.product_slug == slug, Listing.version == version))
            copy = {"title": listing.title, "description": listing.description,
                    "tags": listing.tags}
        return {**pkg, "state": LP.READY, "blockers": [], "copy": copy,
                "listing_snapshot_sha256": LP.listing_copy_digest(copy),
                "source_snapshot_sha256": LP._release(db, slug, version)["source_snapshot_sha256"],
                "fingerprint": "e" * 48 + pkg["fingerprint"][:16]}

    LP.assemble = passing
    try:
        db, cir = _certify_and_drain("ready")
        pkgs = _jobs(db, "listing.package")
        assert pkgs and all(j.outputs["trigger"] == "event" for j in pkgs), \
            [(j.idempotency_key, j.outputs) for j in pkgs]
        assert pkgs[0].outputs["ready"] == 1
        rows = _requests(db)
        assert len(rows) == 1 and rows[0][1] is False, rows       # asked once, still open
        sweep = _run(db, {"cadence": "listing_package"}, "cadence:listing_package:sweep-r")
        assert sweep.outputs["changed"] == 0
        again = _run(db, dict(pkgs[0].inputs), pkgs[0].idempotency_key + ":again")
        assert again.outputs["changed"] == 0
        assert _requests(db) == rows and len(_readings(db)) == 1
        # Asking the owner is all it does: publication stays refused in SHADOW.
        assert all(j.status is not JobStatus.DONE for j in _jobs(db, "store.publish"))
    finally:
        LP.assemble = real


def test_the_sweep_is_kept_as_the_safety_net():
    from brambleloop.runtime.worker import CADENCES

    assert ("listing_package", "listing", "listing.package", 6 * 60 * 60) in CADENCES


def test_competing_package_records_never_reopen_a_stale_owner_request():
    from threading import Event, Thread, current_thread

    from brambleloop.core.models import PatternVersion, Product

    db = _db("package-race")
    with db.session() as session:
        product = Product(slug="race-product", title="Original Product")
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                   certified=True, release_hash="r" * 64))
        session.add(Listing(product_slug="race-product", version="1.0.0",
                            title="Original Product a", description="fixture", tags=[],
                            release_hash="r" * 64))
    def package(letter):
        copy = {"title": f"Original Product {letter}", "description": "fixture", "tags": []}
        return {"slug": "race-product", "version": "1.0.0", "fingerprint": letter * 64,
                "state": LP.READY, "release_hash": "r" * 64, "identity": {}, "copy": copy,
                "listing_snapshot_sha256": LP.listing_copy_digest(copy),
                "source_snapshot_sha256": LP._release(db, "race-product", "1.0.0")["source_snapshot_sha256"],
                "blockers": []}
    a, b = package("a"), package("b")
    LP.record(db, a)
    entered, resume = Event(), Event()
    real_lock = release._serialise_owner_queue
    results, errors = [], []

    def delayed_lock(session, database):
        if current_thread().name == "old-package":
            entered.set()
            assert resume.wait(20)
        return real_lock(session, database)

    def old_record():
        try:
            results.append(LP.record(db, a))
        except Exception as exc:
            errors.append(repr(exc))

    release._serialise_owner_queue = delayed_lock
    try:
        thread = Thread(target=old_record, name="old-package")
        thread.start()
        assert entered.wait(20)
        with db.session() as session:
            listing = session.scalar(select(Listing).where(Listing.product_slug == "race-product"))
            listing.title = b["copy"]["title"]
        b["source_snapshot_sha256"] = LP._release(db, "race-product", "1.0.0")["source_snapshot_sha256"]
        LP.record(db, b)
        resume.set()
        thread.join(20)
        assert not thread.is_alive() and not errors, errors
    finally:
        resume.set()
        release._serialise_owner_queue = real_lock
    assert results[0]["retry"] is True, results
    assert LP.latest(db, "race-product", "1.0.0")["fingerprint"] == b["fingerprint"]
    active = [key for key, done, _state in _requests(db) if not done]
    assert active == [f"{LP.ACTION_PREFIX}race-product@1.0.0:{b['fingerprint'][:16]}"], active
    # A snapshot taken before a competing commit is rejected even if record()
    # itself starts only after the new package has been stored.
    stale = LP.record(db, a, expected_fingerprint=a["fingerprint"])
    assert stale["retry"] is True, stale
    assert [key for key, done, _state in _requests(db) if not done] == active


def test_ineligible_event_and_sweep_close_stale_owner_reviews():
    from brambleloop.core.models import PatternVersion, Product
    from brambleloop.ops import owner_queue

    for defect in ("uncertified", "missing_listing", "parked"):
        db = _db(f"ineligible-{defect}")
        slug, version = "fixture-review", "1.0.0"
        with db.session() as session:
            product = Product(slug=slug, title="Fixture Review")
            session.add(product)
            session.flush()
            session.add(PatternVersion(product_id=product.id, version=version, cir_json={},
                                       certified=True, release_hash="a" * 64))
            session.add(Listing(product_slug=slug, version=version, title="Fixture Review",
                                description="Fixture", tags=[], release_hash="a" * 64))
        copy = {"title": "Fixture Review", "description": "Fixture", "tags": []}
        package = {"slug": slug, "version": version, "fingerprint": "b" * 64,
                   "state": LP.READY, "release_hash": "a" * 64, "identity": {},
                   "copy": copy, "listing_snapshot_sha256": LP.listing_copy_digest(copy),
                   "source_snapshot_sha256": LP._release(db, slug, version)["source_snapshot_sha256"],
                   "blockers": []}
        assert LP.record(db, package)["review_requested"]
        with db.session() as session:
            if defect == "missing_listing":
                listing = session.scalar(select(Listing).where(Listing.product_slug == slug))
                session.delete(listing)
            else:
                pv = session.scalar(select(PatternVersion).join(Product).where(Product.slug == slug))
                pv.certified = False
            if defect == "parked":
                action = session.scalar(select(OwnerAction).where(OwnerAction.done == False))
                action.state = owner_queue.PARKED
        job = _run(db, {"slug": slug, "version": version}, f"t:ineligible:{defect}")
        assert job.status == JobStatus.DONE and not job.outputs["eligible"], job.outputs
        assert LP.latest(db, slug, version)["state"] == LP.BLOCKED
        actions = _requests(db)
        if defect == "parked":
            assert len(actions) == 1 and actions[0][2] == owner_queue.PARKED, actions
        else:
            assert len(actions) == 1 and actions[0][1] is True, actions
            assert actions[0][2] == owner_queue.SUPERSEDED, actions
        # The safety-net sweep neither reopens a request nor rewrites the hold.
        again = LP.sweep(db)
        assert again["changed"] == 0, again
        assert _requests(db) == actions


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
