"""Failure mining: failures grouped into routed lessons, once, and jury deaths kept as memory.

Requirements 85, 97, 101, 193. Counting unresolved incidents is not mining. These tests hold
`improve.mine` to what it claims: it reads incidents, gate and asset refusals, dead letters and
recorded jury runs; groups them by signature; publishes each group once, idempotent on its
evidence reference; routes it by `SUBJECT_ROUTING`; and freezes a defective CIR as a
regression fixture when an incident carries one.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import bus, mine  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _seed(db, *, cir: dict | None = None):
    from brambleloop.core.models import AuditLog, Incident, Job, JobStatus

    with db.session() as s:
        s.add(Incident(severity="P1", signature="row-94-count", product_slug="cable-throw",
                       summary="round 94 count does not match", detail={}))
        s.add(Incident(severity="P2", signature="row-94-count", product_slug="cable-throw",
                       summary="same defect reported again", report_count=3, detail={}))
        if cir is not None:
            s.add(Incident(severity="P1", signature="declared-count", summary="count wrong",
                           detail={"cir": cir}))
        s.add(Incident(severity="P1", signature="closed", summary="fixed", resolved=True,
                       detail={}))
        s.add(AuditLog(actor="quality", action="gate.blocked", artifact="cable-throw@1.0.0",
                       detail={"reasons": ["E_COUNT: round 94 declares 23"]}))
        s.add(AuditLog(actor="quality", action="gate.blocked", artifact="cable-throw@1.0.1",
                       detail={"reasons": ["E_COUNT: round 94 declares 22"]}))
        s.add(AuditLog(actor="asset_truth", action="assets.hero_blocked",
                       artifact="cable-throw@1.0.0", detail={"blocking": ["thumbnail: low"]}))
        s.add(AuditLog(actor="orchestrator", action="gate.passed", detail={}))
        s.add(Job(agent="a", job_type="assets.render", status=JobStatus.DEAD, inputs={},
                  last_error="TimeoutError: render took too long"))
        s.add(Job(agent="a", job_type="assets.render", status=JobStatus.DEAD, inputs={},
                  last_error="TimeoutError: render took too long again"))
        s.add(AuditLog(actor="creative_director", action="creative.tournament",
                       artifact="christmas/home",
                       detail={"field": {"generated": 40}, "survivors": [],
                               "causes": {"sameness": 30, "genericness": 6}}))


def _lessons(db):
    from sqlalchemy import select

    from brambleloop.core.models import Lesson

    with db.session() as s:
        return [(l.subject, l.origin_cell, l.evidence_ref, list(l.routed_to))
                for l in s.scalars(select(Lesson).order_by(Lesson.id))]


def test_failures_are_grouped_by_signature_and_published_once_each():
    db = _db()
    _seed(db)
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        tournament = s.scalar(select(AuditLog.id).where(
            AuditLog.action == "creative.tournament"))
    out = mine.mine(db, fixture_dir=Path(tempfile.mkdtemp()))
    refs = sorted(e["evidence_ref"] for e in out["published"])
    assert refs == sorted([
        "incident:row-94-count",                       # two incidents, one defect
        "gate.blocked:e_count",                        # two refusals, one code
        "assets.hero_blocked:thumbnail",
        "dead:assets.render:timeouterror",             # two dead letters, one error code
        f"creative.tournament:audit:{tournament}",     # one jury run, one lesson
    ]), refs
    assert out["found"] == 5 and out["incidents"] == 2   # the resolved one is not read
    incident = next(e for e in out["published"] if e["kind"] == "incident")
    assert incident["members"] == 2 and incident["reports"] == 4


def test_mining_is_idempotent_on_evidence():
    """An unresolved incident re-read tomorrow is the same lesson, not a second one."""
    db = _db()
    _seed(db)
    fixtures = Path(tempfile.mkdtemp())
    first = mine.mine(db, fixture_dir=fixtures)
    before = _lessons(db)
    second = mine.mine(db, fixture_dir=fixtures)
    assert _lessons(db) == before
    assert second["found"] == 0
    # The watermark means refusals and dead letters already mined are not re-read; the open
    # incident is, and resolves to its existing lesson.
    assert second["blocked"] == 0 and second["dead"] == 0 and second["incidents"] == 2
    assert [e["lesson"] for e in second["reused"]] == [
        e["lesson"] for e in first["published"] if e["kind"] == "incident"]


def test_each_group_is_routed_by_the_subject_table():
    db = _db()
    _seed(db)
    out = mine.mine(db, fixture_dir=Path(tempfile.mkdtemp()))
    by_kind = {e["kind"]: e for e in out["published"]}
    assert by_kind["incident"]["routed_to"] == list(bus.SUBJECT_ROUTING["defect"])
    assert by_kind["asset_block"]["routed_to"] == list(bus.SUBJECT_ROUTING["thumbnail"])
    assert by_kind["jury_autopsy"]["routed_to"] == list(
        bus.SUBJECT_ROUTING["creative_rejection"])
    stored = {ref: routed for _subj, _origin, ref, routed in _lessons(db)}
    # The origin cell is not its own audience: routing sends a lesson to the others.
    assert "quality" not in stored["incident:row-94-count"]
    assert "pattern_engineering" in stored["incident:row-94-count"]
    assert any(l["evidence_ref"] == "incident:row-94-count"
               for l in bus.inbox(db, "pattern_engineering"))


def test_an_incident_carrying_a_cir_is_frozen_as_a_regression_fixture():
    from fixtures import broken_stitch_count

    db = _db()
    _seed(db, cir=broken_stitch_count().to_dict())
    directory = Path(tempfile.mkdtemp())
    out = mine.mine(db, fixture_dir=directory)
    captured = [f for f in out["regression_fixtures"] if f["captured"]]
    assert len(captured) == 1 and captured[0]["expected_codes"]
    assert list(directory.glob("*.json"))
    # Once captured, never again.
    again = mine.mine(db, fixture_dir=directory)
    assert again["regression_fixtures"] == []


def test_jury_deaths_become_training_memory_the_brief_reads_back():
    """#85: an autopsy computed and thrown away teaches nothing. Kept as a lesson, it
    reaches Creativity's own brief (include_own) and the departments the deaths concern."""
    db = _db()
    _seed(db)
    mine.mine(db, fixture_dir=Path(tempfile.mkdtemp()))
    own = bus.inbox(db, "product_creativity", include_own=True)
    jury = [l for l in own if l["subject"] == "creative_rejection"]
    assert len(jury) == 1 and "'sameness'" in jury[0]["statement"]
    assert any(l["subject"] == "creative_rejection" for l in bus.inbox(db, "market_radar"))


def test_a_self_judged_field_is_refused_as_memory():
    from brambleloop.core.models import AuditLog
    from brambleloop.creative.audit import creativity_director

    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="creative.tournament",
                       detail={"field": {"generated": 20}, "causes": {"sameness": 9},
                               "judged_by": "creative_director"}))
    out = creativity_director(db)
    assert out["kept"] == [] and len(out["refused"]) == 1
    assert "sole judge" in out["refused"][0]["why"]


def test_an_empty_company_mines_nothing_and_says_so():
    db = _db()
    out = mine.mine(db, fixture_dir=Path(tempfile.mkdtemp()))
    assert out["read"] == 0 and out["found"] == 0 and out["published"] == []


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tests"))
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
