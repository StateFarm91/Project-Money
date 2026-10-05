"""D-FB-7 runtime chain: the real `assets.build` handler produces, files and serves the
disclosed render set, and the parity reader judges PRODUCT_TRUTH from it.

Worker.run_once on a temporary sqlite database, every outbound socket refused, no model or
image provider, no spend.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="disclosed_runtime_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

SLUG = "cloudline-baby-blanket"


def _certified_and_built():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/disclosed.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    cir = pipeline._engineered_cir(SLUG)
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                         idempotency_key="cert", priority=0)
    Worker(db, "c", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
    job = JobQueue(db).enqueue("publishing", "assets.build",
                               {"slug": cir.slug, "version": cir.version, "release": "",
                                "rebuild": "disclosed"}, idempotency_key="disclosed", priority=0)
    Worker(db, "b", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
    return db, cir


def test_assets_build_files_verified_disclosed_frames_that_parity_reads():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import disclosed_listing, listing_asset
    from brambleloop.visual import parity
    from brambleloop.visual.product_authority import structural_floor

    db, cir = _certified_and_built()
    with db.session() as s:
        rows = [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == disclosed_listing.ACTION))]
    assert len(rows) == 1 and rows[0]["made"] and rows[0]["usable_as_listing_asset"], rows
    # The frames are persisted, content-addressed, and durable in the database too.
    frames = listing_asset.frames_for(db, slug=SLUG)
    assert [f["role"] for f in frames] == ["hero", "scale", "detail"]
    for f in frames:
        assert f["kind"] == "disclosed_render" and f["generated"] is False
        assert f["durable"] is True
        data = ArtifactStore().get(f["image"]["sha256"], db=db)
        assert f["disclosed_render"]["image_sha256"] == f["image"]["sha256"]
        assert len(data) > 1000
        # The gate reads the persisted record, not the in-memory render.
        assert structural_floor(f)["status"] == "PASS", structural_floor(f)
    verdict = parity.assess(frames)
    assert verdict["dimensions"]["product_truth"]["verdict"] == "pass", verdict["dimensions"]
    assert verdict["dimensions"]["mobile_grid"]["verdict"] == "pass"
    assert verdict["dimensions"]["gallery"]["verdict"] == "pass"
    # Parity still blocks on the dimensions this work does not answer, and says which.
    assert verdict["blocks_release"] is True
    assert set(verdict["unjudged"]) == {"hero", "lifestyle_quality", "competitive_blind_review"}

    # The build's own audit row reports the set, and a rebuild of the same design reuses it.
    with db.session() as s:
        built = [r.detail for r in s.scalars(select(AuditLog).where(AuditLog.action.in_(
            ("assets.listing_images_built", "assets.listing_images_blocked"))))]
    assert built[-1]["disclosed_render"]["usable"] is True

    # Export: only with the disclosure in the copy; the certified-image path refuses them.
    try:
        disclosed_listing.export_images(db, slug=SLUG, description="A pattern.")
    except disclosed_listing.DisclosureMissing:
        pass
    else:
        raise AssertionError("disclosed frames exported without the copy disclosure")
    out = disclosed_listing.export_images(
        db, slug=SLUG, description="A pattern.\n\n" + disclosed_listing.COPY_DISCLOSURE)
    assert len(out) == 3 and all(alt.startswith(disclosed_listing.DISCLOSURE)
                                 for _n, _b, alt in out)


def test_the_certified_image_path_refuses_a_disclosed_frame():
    from brambleloop.publish import disclosed_listing
    from brambleloop.runtime import etsy_ops

    db, cir = _certified_and_built()
    sha = next(iter(disclosed_listing.disclosed_shas(db)))
    original = etsy_ops.certified_frames
    etsy_ops.certified_frames = lambda *a, **k: {
        "frames": [{"sha256": sha, "position": 1}], "problems": [], "record_id": 1}
    try:
        got = etsy_ops.certified_images(db, SLUG, cir.version)
    finally:
        etsy_ops.certified_frames = original
    assert got["images"] == [] and any("disclosed render" in p for p in got["problems"])


def test_listing_asset_make_falls_back_to_the_disclosed_set_only_in_launch_scope():
    """The product-first path: generative redraw is refused (F-852), so a Launch-0 product
    gets its disclosed render set, filed where `last` finds it; a product outside Launch-0
    has no authoritative CIR to verify against and is offered nothing."""
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.products import launch0
    from brambleloop.products.builder import for_slug
    from brambleloop.publish import disclosed_listing, listing_asset

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/make.sqlite")
    db.create_all()
    cir = launch0.cir_for("hexagon_coasters")
    out = listing_asset.make(db, cir, build_twin(cir, compile_cir(cir)))
    assert out["kind"] == "disclosed_render" and out["made"] and out["usable_as_listing_asset"]
    last = listing_asset.last(db, slug=cir.slug)
    assert last["kind"] == "disclosed_render" and listing_asset.usable(last)
    with db.session() as s:
        assert s.scalars(select(AuditLog).where(
            AuditLog.action == disclosed_listing.ACTION)).first() is not None

    other = for_slug("winter-village-graphghan")
    refused = listing_asset.make(db, other, build_twin(other, compile_cir(other)))
    assert not refused.get("made") and refused.get("kind") != "disclosed_render"


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("PASS", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    sys.exit(bool(failures))
