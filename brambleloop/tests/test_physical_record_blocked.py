"""A physical sample can be recorded for a release blocked only on physical evidence (F-078).

`physical.record` used to load the CIR through the certified-only loader, so a release whose
one missing piece was the sample (Class C, a gauge outside its yarn's band) could never
receive the sample that would unblock it, and the row it wrote carried no content hash.
These tests drive the real handlers through the queue -- no PhysicalTest row is inserted by
hand: blocked release -> `physical.record` -> `gate.certify` grants on that evidence; a
sample of different content does not count; an unknown release or an unexamined content
hash is refused and nothing is stored. Every product here is a test fixture.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_physical_record_blocked.py
"""
from __future__ import annotations

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
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, PatternVersion, PhysicalTest, Product,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 (registers handlers)
from brambleloop.runtime.worker import Worker  # noqa: E402

BAND_GRAMS, BAND_METRES = 100.0, 210.0


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/blocked.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent: str, job_type: str, inputs: dict) -> Job:
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0)
    Worker(db, f"w-{job_type}", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _class_c_sphere(title: str = "Test Sphere"):
    from brambleloop.creative.prototype import gauge_for
    from tests import fixtures

    cir = fixtures.good_sphere()
    cir.gauge = gauge_for("worsted")
    cir.risk_class = "C"
    cir.title = title
    return cir


def _certify(db, cir) -> tuple[str, dict]:
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.artifact == f"{cir.slug}@{cir.version}",
            AuditLog.action.in_(("gate.certified", "gate.blocked")))
            .order_by(AuditLog.id.desc()).limit(1))
        return row.action, dict(row.detail or {})


def _sample_inputs(cir, **extra) -> dict:
    """A sample that agrees with the twin: the yarn it predicted, the size it claimed."""
    twin = build_twin(cir, compile_cir(cir))
    grams = {c: m / (BAND_METRES / BAND_GRAMS) for c, m in twin.yarn_metres_by_color.items()}
    out = {"slug": cir.slug, "version": cir.version, "tester_ref": "tester-1",
           "grams_by_color": grams, "ball_band_grams": BAND_GRAMS,
           "ball_band_metres": BAND_METRES}
    if twin.width_cm:
        out["measured_width_cm"] = round(twin.width_cm, 1)
    if twin.height_cm:
        out["measured_height_cm"] = round(twin.height_cm, 1)
    return {**out, **extra}


def _physical_rows(db) -> list[PhysicalTest]:
    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest).order_by(PhysicalTest.id)))
        for r in rows:
            s.expunge(r)
        return rows


def _certified(db, slug: str) -> bool:
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(Product.slug == slug))
        return bool(pv is not None and pv.certified)


def test_a_class_c_release_blocked_on_physical_evidence_takes_its_sample_and_certifies():
    db = _db()
    cir = _class_c_sphere()
    action, detail = _certify(db, cir)
    assert action == "gate.blocked", detail
    assert any("PHYSICAL_TEST_REQUIRED" in r for r in detail["reasons"]), detail["reasons"]
    content = detail["content_hash"]
    assert not _certified(db, cir.slug)

    # F-072/F-081 (K6): Class C needs a *full make* of this content, so the tester reports
    # the scope and the finished measurement a full make records (F-076). The sphere's twin
    # refuses a flat width, so the measurement is recorded without a size comparison.
    job = _run(db, "quality_director", "physical.record",
               _sample_inputs(cir, scope="full_make", measured_width_cm=9.5))
    assert job.status is JobStatus.DONE, job.last_error
    assert job.outputs["content_hash"] == content, job.outputs
    assert job.outputs["release_certified"] is False
    rows = _physical_rows(db)
    assert len(rows) == 1 and rows[0].passed is True, [(r.passed, r.measured) for r in rows]
    # The row itself names the text the tester worked -- not inferred later from timing.
    assert rows[0].measured["content_hash"] == content

    action, detail = _certify(db, cir)
    assert action == "gate.certified", detail["reasons"]
    assert detail["physical_evidence"]["passed"] is True
    assert detail["physical_evidence"]["bound"] == [rows[0].id]
    assert _certified(db, cir.slug)


def test_a_sample_bound_to_different_content_does_not_count():
    db = _db()
    cir = _class_c_sphere()
    _, first = _certify(db, cir)
    job = _run(db, "quality_director", "physical.record", _sample_inputs(cir))
    assert job.status is JobStatus.DONE, job.last_error
    # The pattern changes under the same version: the sample was worked against the old text.
    revised = _class_c_sphere("Test Sphere, Revised")
    action, detail = _certify(db, revised)
    assert action == "gate.blocked", detail
    assert detail["content_hash"] != first["content_hash"]
    assert detail["physical_evidence"]["passed"] is False
    assert "invalidated" in detail["physical_evidence"]["unbound"][0]["why"], detail
    assert not _certified(db, revised.slug)


def test_a_sample_naming_content_the_chain_never_examined_is_refused_and_not_stored():
    db = _db()
    cir = _class_c_sphere()
    _certify(db, cir)
    job = _run(db, "quality_director", "physical.record",
               _sample_inputs(cir, content_hash="f" * 64))
    assert job.status is not JobStatus.DONE, job.outputs
    assert "not content the chain examined" in (job.last_error or ""), job.last_error
    assert _physical_rows(db) == []
    action, _ = _certify(db, cir)
    assert action == "gate.blocked"


def test_a_sample_for_an_unknown_release_is_refused():
    db = _db()
    cir = _class_c_sphere()
    job = _run(db, "quality_director", "physical.record", _sample_inputs(cir))
    assert job.status is not JobStatus.DONE, job.outputs
    assert "has been examined" in (job.last_error or ""), job.last_error
    _certify(db, cir)
    job = _run(db, "quality_director", "physical.record",
               _sample_inputs(cir, version="9.9.9"))
    assert job.status is not JobStatus.DONE and _physical_rows(db) == [], job.last_error


def test_a_failed_sample_is_stored_bound_but_does_not_unblock():
    db = _db()
    cir = _class_c_sphere()
    _, first = _certify(db, cir)
    # Instructions not followed: stored (a disagreement is evidence) but never a pass.
    job = _run(db, "quality_director", "physical.record",
               _sample_inputs(cir, instructions_followed=False))
    assert job.status is JobStatus.DONE, job.last_error
    rows = _physical_rows(db)
    assert rows and rows[-1].passed is False
    assert rows[-1].measured["content_hash"] == first["content_hash"]
    action, detail = _certify(db, cir)
    assert action == "gate.blocked" and detail["physical_evidence"]["passed"] is False


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, repr(e)[:400])
    print(f"{len(tests) - fails}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
