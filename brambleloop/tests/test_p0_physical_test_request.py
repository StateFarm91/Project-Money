"""P0-PHYSICAL-TEST-REQUEST: a class-C release with no bound full make opens one tester work item.

Review PHYSICAL e8b458b5: no owner card (B-532: the sample is tester work, `tester_roster`;
the one owner card is the existing `tester_outreach`). Real queue, real Worker, file-backed
SQLite. The chain: `cir.compile` -> `gate.certify` (blocked: PHYSICAL_TEST_REQUIRED) -> one
`physical.sample_requested` work item, its kit from the CIR and twin, bound to the examined
content hash -> recertify adds none -> only a passed, independent full make of that content
satisfies it -> certify grants. Every product is a test fixture.

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


def _sample_cards(db) -> list:
    with db.session() as s:
        return [r.requirement_key for r in s.scalars(select(OwnerAction))
                if str(r.requirement_key or "").startswith("physical.sample")]


def _requests(db, artifact) -> list[dict]:
    with db.session() as s:
        return [dict(a.detail or {}) for a in s.scalars(select(AuditLog).where(
            AuditLog.action == PS.REQUESTED, AuditLog.artifact == artifact)
            .order_by(AuditLog.id))]


def _closes(db, artifact) -> list[dict]:
    with db.session() as s:
        return [dict(a.detail or {}) for a in s.scalars(select(AuditLog).where(
            AuditLog.action == PS.CLOSED, AuditLog.artifact == artifact)
            .order_by(AuditLog.id))]


class _Ctx:
    def __init__(self, db):
        self.db, self.audits = db, []

    def audit(self, action, **kw):
        from brambleloop.core.models import AuditLog as A

        with self.db.session() as s:
            s.add(A(actor="test", action=action, artifact=kw.get("artifact"),
                    detail=kw.get("detail")))


def test_class_c_opens_one_tester_work_item_and_no_owner_card():
    db = _db()
    import dataclasses

    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    cir = _class_c_sphere("Sample Sphere")
    cir.gauge = dataclasses.replace(cir.gauge, hook_mm=5.5)   # not the basket kit's 5.0
    out = _compile_then_certify(db, cir)
    assert out["action"] == "gate.blocked", out
    assert any("PHYSICAL_TEST_REQUIRED" in r for r in out["reasons"]), out["reasons"]
    assert _sample_cards(db) == [], _sample_cards(db)        # B-532: never an owner card
    asked = _requests(db, f"{cir.slug}@{cir.version}")
    assert len(asked) == 1, asked
    item = asked[0]
    assert item["route"] == "tester_roster" and item["owner_card"] is None
    kit = item["kit"]
    assert kit["slug"] == cir.slug and kit["content_hash"] == out["content_hash"]
    assert item["content_hash"] == out["content_hash"] and item["kit_hash"] == PS.kit_hash(kit)
    assert kit["hook_mm"] == 5.5 and kit["scope"] == "full_make"
    assert kit["pieces"] == [c.name for c in cir.components]
    # MED-2: the colours are the validator's keys, with the predicted metres and tolerance.
    twin = build_twin(cir, compile_cir(cir))
    assert kit["colours_to_weigh"] == sorted(twin.yarn_metres_by_color), kit
    assert kit["yarn_tolerance"] == 0.20
    for c, m in twin.yarn_metres_by_color.items():
        assert abs(kit["yarn_metres_predicted"][c] - m) < 0.1, (c, kit)
        assert f"{c}: about" in item["brief"] and "+-20%" in item["brief"], item["brief"]
    # HIGH-2: the brief says exactly what happens to a record missing a colour.
    assert "stored as not passed" in item["brief"] and "SAMPLE_COLOUR_UNMEASURED" in \
        item["brief"]


def test_a_missing_gauge_reads_unknown_never_none():
    from types import SimpleNamespace

    real = _class_c_sphere("Gaugeless Sphere")
    cir = SimpleNamespace(slug=real.slug, version=real.version, title=real.title,
                          materials=real.materials, components=real.components,
                          finished_size_note=real.finished_size_note,
                          gauge=SimpleNamespace(stitches_per_10cm=None, rows_per_10cm=None,
                                                stitch_type=None, hook_mm=None,
                                                yarn_weight=None))

    class _Cert:
        content_hash, twin_summary, risk_matrix = "c" * 64, {}, {"effective": "C"}

    kit = PS.sample_kit(cir, _Cert())
    assert str(kit["gauge"]).startswith("UNKNOWN"), kit["gauge"]
    assert "gauge None" not in PS.brief(kit)


def test_recertifying_the_same_content_adds_no_second_item():
    db = _db()
    cir = _class_c_sphere("Recert Sphere")
    _compile_then_certify(db, cir)
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    assert len(_requests(db, f"{cir.slug}@{cir.version}")) == 1
    assert _sample_cards(db) == []


def test_changed_content_under_the_same_version_opens_a_new_item():
    """MED-1: "decided" is bound to the content hash, not the version."""
    db = _db()
    cir = _class_c_sphere("Changed Sphere")
    first = _compile_then_certify(db, cir)
    cir.title = "Changed Sphere Revised"
    second = _compile_then_certify(db, cir)
    assert first["content_hash"] != second["content_hash"], (first, second)
    hashes = [r["content_hash"] for r in _requests(db, f"{cir.slug}@{cir.version}")]
    assert hashes == [first["content_hash"], second["content_hash"]], hashes


def test_a_passed_independent_full_make_satisfies_it_and_certification_grants():
    db = _db()
    cir = _class_c_sphere("Closed Sphere")
    out = _compile_then_certify(db, cir)
    job = _run(db, "quality_director", "physical.record",
               _sample_inputs(cir, scope="full_make", measured_width_cm=9.5))
    assert job.status is JobStatus.DONE, job.last_error
    closes = _closes(db, f"{cir.slug}@{cir.version}")
    assert [c["satisfied"] for c in closes] == [True], closes
    assert closes[0]["content_hash"] == out["content_hash"]
    assert PS.state(db, cir.slug, cir.version, out["content_hash"])["state"] == "satisfied"
    again = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()})
    assert again.status is JobStatus.DONE and again.outputs.get("granted") is True, again.outputs
    assert len(_requests(db, f"{cir.slug}@{cir.version}")) == 1
    assert cir.slug not in PS.open_requests(db)


def test_a_record_missing_a_colour_is_stored_not_passed_and_does_not_satisfy():
    """HIGH-1 / HIGH-2 behaviour: the record is stored (not refused), not passed, and the
    work item stays open with the reason."""
    from brambleloop.core.models import PhysicalTest

    db = _db()
    cir = _class_c_sphere("Unweighed Sphere")
    _compile_then_certify(db, cir)
    inputs = _sample_inputs(cir, scope="full_make", measured_width_cm=9.5)
    colours = sorted(inputs["grams_by_color"])
    inputs["grams_by_color"] = {c: g for c, g in inputs["grams_by_color"].items()
                                if c != colours[0]}
    if not inputs["grams_by_color"]:
        inputs["grams_by_color"] = {}
    job = _run(db, "quality_director", "physical.record", inputs)
    assert job.status is JobStatus.DONE, job.last_error
    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest).where(PhysicalTest.product_slug == cir.slug)))
        assert rows and rows[-1].passed is False, [(r.passed,) for r in rows]
    closes = _closes(db, f"{cir.slug}@{cir.version}")
    assert closes and closes[-1]["satisfied"] is False, closes
    assert "did not pass" in closes[-1]["why"], closes
    assert cir.slug in PS.open_requests(db)


def test_only_a_passed_independent_full_make_of_this_content_satisfies():
    """HIGH-1: owner-made, partial or failed records leave the item open, each said why."""
    db = _db()
    cir = _class_c_sphere("Strict Sphere")
    out = _compile_then_certify(db, cir)
    ctx, h = _Ctx(db), out["content_hash"]
    cases = [dict(passed=True, evidence_class="full_physical_make", owner_made=True),
             dict(passed=True, evidence_class="partial_physical", owner_made=False),
             dict(passed=False, evidence_class="full_physical_make", owner_made=False),
             dict(passed=True, evidence_class=None, owner_made=False)]
    for kw in cases:
        got = PS.close_on_record(ctx, cir.slug, cir.version, h, 1, **kw)
        assert got["satisfied"] is False and got["why"], (kw, got)
    assert PS.state(db, cir.slug, cir.version, h)["state"] == "open"
    # other content: not this item's record at all
    assert PS.close_on_record(ctx, cir.slug, cir.version, "f" * 64, 9, passed=True,
                              evidence_class="full_physical_make", owner_made=False) is None
    assert PS.state(db, cir.slug, cir.version, h)["state"] == "open"
    ok = PS.close_on_record(ctx, cir.slug, cir.version, h, 2, passed=True,
                            evidence_class="full_physical_make", owner_made=False)
    assert ok["satisfied"] is True and PS.state(db, cir.slug, cir.version, h)["state"] == \
        "satisfied"


def test_a_retest_is_never_also_a_sample_request():
    """M2: a stale-evidence retest is _request_physical_retest's; this module stays out."""
    class _Cert:
        physical_test_required, physical_test_passed = True, False
        content_hash = "d" * 64
        risk_matrix = {"requirement": {"retest_required": True}}

    assert PS.needs_request(_Cert()) is False
    _Cert.risk_matrix = {"requirement": {}}
    assert PS.needs_request(_Cert()) is True
    _Cert.content_hash = ""
    assert PS.needs_request(_Cert()) is False                      # M3: no content, no item


def test_the_newest_open_item_travels_with_its_testing_demand():
    """MED-3 / M14: quality.testers.plan hands the release's newest open kit to its demand."""
    from datetime import date

    from brambleloop.quality import testers

    db = _db()
    cir = _class_c_sphere("Demand Sphere")
    first = _compile_then_certify(db, cir)
    cir.title = "Demand Sphere Two"
    second = _compile_then_certify(db, cir)
    plan = testers.plan(db, [{"slug": cir.slug, "risk_class": "C", "specialty": "amigurumi",
                              "make_hours": 4.0, "needed_by": date(2026, 12, 1)}],
                        today=date(2026, 11, 7))
    rows = [r for r in plan["unassigned"] + plan["assignments"]
            if r.get("product_slug") == cir.slug]
    assert rows and rows[0]["sample_request"]["content_hash"] == second["content_hash"], rows
    assert rows[0]["sample_request"]["content_hash"] != first["content_hash"]
    assert "SAMPLE_COLOUR_UNMEASURED" in rows[0]["sample_request"]["brief"]


def test_a_class_a_release_opens_no_item():
    from tests import fixtures

    db = _db()
    cir = fixtures.good_sphere()
    cir.risk_class = "A"
    cir.title = "Plain Sphere"
    _compile_then_certify(db, cir)
    assert _requests(db, f"{cir.slug}@{cir.version}") == [] and _sample_cards(db) == []


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
