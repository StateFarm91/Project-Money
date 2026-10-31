"""W-PHYSFIX on W4-LAUNCHFIX: a completed physical upgrade leads the gallery with the sample photo.

`publish.sample_photo` (W4-LAUNCHFIX) refuses publication unless the FIRST frame of the
certified gallery is the unedited photograph of a passed full make of this release
(Etsy Help 44297885802647 and 115015663347). `physical_upgrade.plan_upgrade` used to append
the photo frame LAST, so a completed upgrade could never satisfy that gate. These tests run
the real intake, the real upgrade planner and the real listing-set certificate step
(`release_gates.certificate_step`); only the four promotion-gate readings per frame are
supplied, because producing them needs the full asset build, which is not what is under test.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Job, ListingAsset, PatternVersion, PhysicalPhoto, PhysicalTest, Product,
)
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import eligibility as el  # noqa: E402
from brambleloop.publish import physical_upgrade as pu  # noqa: E402
from brambleloop.publish import release_gates, sample_photo  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 (registers handlers)
from brambleloop.runtime.worker import Worker  # noqa: E402

BAND_GRAMS, BAND_METRES = 50.0, 77.0
RENDERS = (("hero", "DIGITAL_TWIN_RENDER"), ("chart", "DIGITAL_TWIN_RENDER"),
           ("pattern_preview", "DIGITAL_TWIN_RENDER"))


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/photo.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, job_type: str, inputs: dict) -> Job:
    job = JobQueue(db).enqueue("quality_director", job_type, inputs, priority=0)
    Worker(db, f"w-{job_type}", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _certified_basket(db):
    cir = launch0.cir_for("basket_small")
    _run(db, "gate.certify", {"cir": cir.to_dict()})
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == cir.slug, PatternVersion.version == cir.version))
        assert pv is not None and pv.certified, "the basket release did not certify"
        release = pv.release_hash
    return cir, release


def _passed_full_make(db, cir) -> int:
    twin = build_twin(cir, compile_cir(cir))
    job = _run(db, "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "tester-1",
        "scope": "full_make", "size": "small",
        "grams_by_color": {c: m / (BAND_METRES / BAND_GRAMS)
                           for c, m in twin.yarn_metres_by_color.items()},
        "ball_band_grams": BAND_GRAMS, "ball_band_metres": BAND_METRES,
        "measured_width_cm": twin.width_cm, "measured_height_cm": twin.height_cm,
        "holds_shape": True, "lies_flat": True, "instructions_followed": True})
    with db.session() as s:
        row = s.scalar(select(PhysicalTest).order_by(PhysicalTest.id.desc()).limit(1))
        assert row is not None and row.passed, job.last_error
        return row.id


def _render_gallery(db, cir) -> None:
    store = ArtifactStore()
    with db.session() as s:
        for pos, (role, cls) in enumerate(RENDERS, start=1):
            sha = store.put(f"r{pos}.png", f"render {role}".encode(), "image/png").sha256
            s.add(ListingAsset(product_slug=cir.slug, version=cir.version, position=pos,
                               asset_class=cls, role=role, sha256=sha, approved=True,
                               claims={}, blocked_reasons=[]))


def _upgrade(db, cir, test_id, *, unedited: bool = True) -> dict:
    sha = ArtifactStore().put("sample.jpg", b"unedited camera file of the made basket",
                              "image/jpeg").sha256
    rec = pu.intake(db, slug=cir.slug, version=cir.version, source="tester", sha256=sha,
                    rights_basis="tester_agreement", taken_by="tester-1",
                    physical_test_id=test_id, unedited=unedited)
    plan = pu.plan_upgrade(db, rec["photo_id"])
    assert plan["upgraded"], plan
    return {**plan, "sha256": sha}


def _recertify(db, cir, release) -> dict:
    """Asset truth approves the photo frame; the listing-set certificate is re-issued."""
    with db.session() as s:
        for f in s.scalars(select(ListingAsset).where(ListingAsset.product_slug == cir.slug)):
            f.approved, f.blocked_reasons = True, []
    with db.session() as s:
        frames = sorted(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version)),
            key=lambda f: f.position)
        for f in frames:
            s.expunge(f)
    per_frame = [{"position": f.position, "sha256": f.sha256, "role": f.role,
                  "gates": {g: {"outcome": el.PASSED} for g in el.GATES}} for f in frames]
    return release_gates.certificate_step(
        db, slug=cir.slug, version=cir.version, release_hash=release, frames=frames,
        per_frame=per_frame, geometry={"width_cm": 16.0, "height_cm": 8.7},
        claims={"title": cir.title}, issue=True)


def test_a_completed_upgrade_leads_with_the_photo_and_the_gate_accepts_it():
    db = _db()
    cir, release = _certified_basket(db)
    _render_gallery(db, cir)
    test_id = _passed_full_make(db, cir)
    plan = _upgrade(db, cir, test_id)
    assert plan["frame_position"] == 1, plan
    with db.session() as s:
        order = [(f.position, f.role, f.asset_class) for f in sorted(s.scalars(
            select(ListingAsset).where(ListingAsset.product_slug == cir.slug)),
            key=lambda f: f.position)]
    assert order[0] == (1, "proof", "PHYSICAL_PRODUCT_PHOTO"), order
    assert [r for _p, r, _c in order[1:]] == [r for r, _c in RENDERS], order
    # Re-certification semantics: until asset truth and the certificate re-run, it is refused.
    before = sample_photo.requirement(db, cir.slug, cir.version)
    assert before["satisfied"] is False, before
    cert = _recertify(db, cir, release)
    assert cert["valid"] and cert["issued"], cert
    after = sample_photo.requirement(db, cir.slug, cir.version)
    assert after["satisfied"] is True, after
    assert after["first_frame"]["sha256"] == plan["sha256"]


def test_without_a_photo_the_gate_still_refuses():
    db = _db()
    cir, release = _certified_basket(db)
    _render_gallery(db, cir)
    _passed_full_make(db, cir)
    cert = _recertify(db, cir, release)
    assert cert["valid"], cert
    out = sample_photo.requirement(db, cir.slug, cir.version)
    assert out["satisfied"] is False and "SAMPLE_PHOTO_REQUIRED" in out["reasons"][0], out


def test_a_photo_not_attested_unedited_does_not_lead_and_does_not_satisfy():
    db = _db()
    cir, release = _certified_basket(db)
    _render_gallery(db, cir)
    test_id = _passed_full_make(db, cir)
    plan = _upgrade(db, cir, test_id, unedited=False)
    assert plan["frame_position"] == len(RENDERS) + 1, plan
    _recertify(db, cir, release)
    assert sample_photo.requirement(db, cir.slug, cir.version)["satisfied"] is False


def test_a_photo_with_no_passed_full_make_behind_it_does_not_lead():
    db = _db()
    cir, _release = _certified_basket(db)
    _render_gallery(db, cir)
    plan = _upgrade(db, cir, None)
    assert plan["frame_position"] == len(RENDERS) + 1, plan
    with db.session() as s:
        photo = s.scalar(select(PhysicalPhoto))
        assert photo.detail["frame_position"] == plan["frame_position"]


def test_the_dormant_sample_request_asks_for_what_the_intake_requires():
    """The readiness owner request names the shape answer, "followed exactly?" and problems,
    which `physical.record` refuses a full make without (PHYSFIX G3, SECREVIEW F2)."""
    from brambleloop.launch import readiness

    action = readiness.PHYSICAL_SAMPLE.action
    for needle in ("holds its shape", "any problem", "followed exactly", "full_make"):
        assert needle in action, (needle, action)


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(exc)[:400])
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
