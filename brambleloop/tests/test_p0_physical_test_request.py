"""P0-PHYSICAL-TEST-REQUEST: a class-C release with no bound full make raises one owner action.

Real queue, real Worker, file-backed SQLite. Nothing is inserted by hand except the fixture
tester agreement that `physical.record` requires. The chain under test is
`cir.compile` -> `gate.certify` (blocked: PHYSICAL_TEST_REQUIRED) -> one
`physical.sample:<slug>@<version>` OwnerAction whose kit is built from that CIR and bound to
the examined content hash -> recertify adds none -> `physical.record` closes it -> certify
grants on the evidence and reopens nothing. Every product is a test fixture.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_p0_physical_test_request.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, OwnerAction  # noqa: E402
from brambleloop.ops import owner_queue  # noqa: E402
from brambleloop.quality import physical_sample as PS  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from tests.test_physical_record_blocked import (  # noqa: E402
    _class_c_sphere, _db, _run, _sample_inputs,
)


def _compile_then_certify(db, cir) -> dict:
    """cir.compile -> the gate.certify it enqueues, both through the real Worker."""
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()}, priority=0)
    path = str(db.engine.url)
    for jt in ("cir.compile", "gate.certify"):
        w = Worker(Database(path), f"w-{jt}", job_types=[jt])
        while w.run_once():
            pass
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.artifact == f"{cir.slug}@{cir.version}",
            AuditLog.action.in_(("gate.certified", "gate.blocked")))
            .order_by(AuditLog.id.desc()))
        jobs = list(s.scalars(select(Job).where(Job.job_type == "gate.certify")))
        assert jobs and all(j.status == JobStatus.DONE for j in jobs), \
            [(j.status, j.last_error) for j in jobs]
        return {"action": row.action, **dict(row.detail or {})}


def _actions(db, slug, version) -> list[OwnerAction]:
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == PS.requirement_key(slug, version))
            .order_by(OwnerAction.id)))
        for r in rows:
            s.expunge(r)
        return rows


def _requests(db, artifact) -> list[dict]:
    with db.session() as s:
        return [dict(a.detail or {}) for a in s.scalars(select(AuditLog).where(
            AuditLog.action == PS.REQUESTED, AuditLog.artifact == artifact)
            .order_by(AuditLog.id))]


def test_class_c_raises_one_keyed_request_whose_kit_is_this_cir():
    db = _db()
    import dataclasses

    cir = _class_c_sphere("Sample Sphere")
    # A hook that is not the basket kit's 5.0 mm, so the kit must read it from this CIR.
    cir.gauge = dataclasses.replace(cir.gauge, hook_mm=5.5)
    assert cir.gauge.hook_mm == 5.5
    out = _compile_then_certify(db, cir)
    assert out["action"] == "gate.blocked", out
    assert any("PHYSICAL_TEST_REQUIRED" in r for r in out["reasons"]), out["reasons"]
    rows = _actions(db, cir.slug, cir.version)
    assert len(rows) == 1 and not rows[0].done, rows
    row = rows[0]
    assert row.max_cost_cad > 0 and row.minutes > 0, (row.max_cost_cad, row.minutes)
    assert "withheld" in row.consequence_of_delay and cir.slug in row.blocks
    asked = _requests(db, f"{cir.slug}@{cir.version}")
    assert len(asked) == 1 and asked[0]["owner_action"] == "queued", asked
    kit = asked[0]["kit"]
    # The kit is this CIR's -- not the fixed basket kit -- and bound to the examined content.
    assert kit["slug"] == cir.slug and kit["version"] == cir.version
    assert kit["content_hash"] == out["content_hash"] == asked[0]["content_hash"]
    assert asked[0]["kit_hash"] == PS.kit_hash(kit)
    assert kit["hook_mm"] == cir.gauge.hook_mm and kit["yarn_weight"] == cir.gauge.yarn_weight
    assert [y["name"] for y in kit["yarn"]] == [m.name for m in cir.materials]
    assert kit["pieces"] == [c.name for c in cir.components] and kit["scope"] == "full_make"
    assert asked[0]["kit_hash"][:12] in row.action
    assert row.requirement_key == f"physical.sample:{cir.slug}@{cir.version}"


def test_recertifying_the_same_version_adds_no_second_request():
    db = _db()
    cir = _class_c_sphere("Recert Sphere")
    _compile_then_certify(db, cir)
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    rows = _actions(db, cir.slug, cir.version)
    assert len(rows) == 1 and not rows[0].done, rows
    states = [a["owner_action"] for a in _requests(db, f"{cir.slug}@{cir.version}")]
    assert states == ["queued", "restated", "restated"], states


def test_a_recorded_make_closes_the_request_and_certification_reopens_nothing():
    db = _db()
    cir = _class_c_sphere("Closed Sphere")
    out = _compile_then_certify(db, cir)
    job = _run(db, "quality_director", "physical.record",
               _sample_inputs(cir, scope="full_make", measured_width_cm=9.5))
    assert job.status is JobStatus.DONE, job.last_error
    rows = _actions(db, cir.slug, cir.version)
    assert len(rows) == 1 and rows[0].done and rows[0].state == owner_queue.SATISFIED, \
        [(r.done, r.state, r.state_reason) for r in rows]
    assert out["content_hash"][:12] in rows[0].state_reason
    again = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    assert again.status is JobStatus.DONE and again.outputs.get("granted") is True, again.outputs
    assert len(_actions(db, cir.slug, cir.version)) == 1   # the granted cert asks nothing
    # ...and does not even restate it: a passed make means no request is needed at all.
    assert [a["owner_action"] for a in _requests(db, f"{cir.slug}@{cir.version}")] == ["queued"]


def test_a_decided_request_is_never_reopened_by_a_recertify():
    db = _db()
    cir = _class_c_sphere("Declined Sphere")
    _compile_then_certify(db, cir)
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == PS.requirement_key(cir.slug, cir.version)))
        owner_queue.close(row, owner_queue.WITHDRAWN, "owner declined the sample spend")
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    rows = _actions(db, cir.slug, cir.version)
    assert len(rows) == 1 and rows[0].state == owner_queue.WITHDRAWN, rows
    assert _requests(db, f"{cir.slug}@{cir.version}")[-1]["owner_action"] == "already_decided"


def test_a_class_a_release_raises_no_sample_request():
    from tests import fixtures

    db = _db()
    cir = fixtures.good_sphere()
    cir.risk_class = "A"
    cir.title = "Plain Sphere"
    _compile_then_certify(db, cir)
    assert _actions(db, cir.slug, cir.version) == []
    assert _requests(db, f"{cir.slug}@{cir.version}") == []


def test_a_record_for_other_content_does_not_close_the_request():
    db = _db()
    cir = _class_c_sphere("Other Sphere")
    _compile_then_certify(db, cir)

    class _Ctx:
        def __init__(self, db):
            self.db, self.audits = db, []

        def audit(self, action, **kw):
            self.audits.append((action, kw))

    ctx = _Ctx(db)
    got = PS.close_on_record(ctx, cir.slug, cir.version, "f" * 64, 999)
    assert got["closed"] is False, got
    rows = _actions(db, cir.slug, cir.version)
    assert len(rows) == 1 and not rows[0].done


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
