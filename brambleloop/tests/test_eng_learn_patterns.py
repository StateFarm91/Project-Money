"""ENG-LEARN slice 2: the pattern learning loop on synthetic engineering outcomes.

The jobs below are synthetic `cir.compile` / `gate.certify` / `cir.draft` rows with a KNOWN
truth. The tests check that:
- a parameter region that really fails is learned as "avoid";
- a region that does not is NOT learned;
- the lessons reach Market Radar's matching;
- `advise` names the region a new CIR falls in;
- the first-pass trend is UNKNOWN on small samples, and "improving" only when it is.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402
from brambleloop.learning import pattern_lessons as PL  # noqa: E402
from brambleloop.learning import stats  # noqa: E402

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _cir(slug: str, rows: int, *, colours: int = 2) -> dict:
    return {"slug": slug, "version": "1.0.0", "title": slug.replace("-", " "),
            "construction": "flat_rows", "risk_class": "A",
            "colors": {chr(65 + i): f"c{i}" for i in range(colours)},
            "gauge": {"stitches_per_10cm": 16, "rows_per_10cm": 18, "yarn_weight": "worsted"},
            "components": [{"name": "panel", "construction": "flat_rows", "foundation": 40,
                            "rows": [{"ops": [{"stitch": "sc", "count": 40}]}] * rows}]}


def _design(db, i: int, *, rows: int, compiled: bool, granted: bool, at: datetime,
            family: str = "tote", category: str = "bag"):
    slug = f"fixture-{family}-{i}"
    cir = _cir(slug, rows)
    with db.session() as s:
        s.add(AuditLog(actor="crochet_engineer", action="cir.drafted",
                       artifact=f"{slug}@1.0.0", detail={"construction": family}, at=at))
        s.add(Job(agent="validator", job_type="cir.compile", inputs={"cir": cir},
                  outputs={"compiled": compiled,
                           "errors": [] if compiled else ["ERROR ROW_COUNT_MISMATCH: [panel row 3] x"]},
                  status=JobStatus.DONE, idempotency_key=f"c{i}{family}", finished_at=at))
        if compiled:
            s.add(Job(agent="quality_director", job_type="gate.certify", inputs={"cir": cir},
                      outputs={"granted": granted, "reasons": [] if granted else
                               ["ERROR REVERSE_MISMATCH: rows disagree",
                                "ERROR FINISHED_SIZE_OUTSIDE: too long"]},
                      status=JobStatus.DONE, idempotency_key=f"g{i}{family}",
                      finished_at=at + timedelta(minutes=1)))


def _cat(slug):
    return "bag"


def test_failing_region_is_learned_and_reaches_radar():
    db = _db()
    rng = random.Random(4)
    for i in range(40):
        long_ = i % 2 == 0
        ok = rng.random() < (0.15 if long_ else 0.9)
        _design(db, i, rows=120 if long_ else 30, compiled=True, granted=ok,
                at=NOW - timedelta(days=3, minutes=i))
    h = PL.harvest(db, category_for=_cat)
    assert h["observed"] == 80
    assert PL.harvest(db, category_for=_cat)["observed"] == 0     # idempotent
    d = PL.derive_lessons(db, now=NOW)
    assert d["lessons"] >= 1 and d["published"] >= 1, d
    from sqlalchemy import select

    from brambleloop.learning.store import DerivedLesson

    with db.session() as s:
        keys = {r.key: r.statement for r in s.scalars(select(DerivedLesson))}
    assert "pattern:tote:rows:100+:-" in keys, keys
    assert "REVERSE_MISMATCH" in keys["pattern:tote:rows:100+:-"]
    # Advice at draft time names the region a new long tote falls in, and not a short one.
    a = PL.advise(db, cir=_cir("new-long-tote", 130), family="tote")
    assert [h["key"] for h in a["avoid"]] == ["pattern:tote:rows:100+:-"]
    assert not PL.advise(db, cir=_cir("new-short-tote", 30), family="tote")["avoid"]
    # The lesson is routed to Market Radar and Pattern Engineering, where radar.score reads it.
    from brambleloop.improve import bus, consume

    assert any("tote" in x["statement"] for x in bus.inbox(db, "market_radar",
                                                         unacted_only=False))
    hit = consume.matching(db, "market_radar",
                           "fixture tote 0 market bag rows tote designs bag")
    assert hit and hit[0]["direction"] == -1


def test_noise_region_is_not_learned():
    db = _db()
    rng = random.Random(8)
    for i in range(60):
        _design(db, i, rows=120 if i % 2 else 30, compiled=True, granted=rng.random() < 0.6,
                at=NOW - timedelta(days=2, minutes=i))
    PL.harvest(db, category_for=_cat)
    assert PL.derive_lessons(db, now=NOW)["lessons"] == 0


def test_first_pass_counts_compile_failure_and_excludes_pending():
    db = _db()
    _design(db, 1, rows=30, compiled=False, granted=False, at=NOW - timedelta(days=1))
    _design(db, 2, rows=30, compiled=True, granted=True, at=NOW - timedelta(days=1))
    with db.session() as s:   # a design compiled but not yet certified: pending
        s.add(Job(agent="validator", job_type="cir.compile",
                  inputs={"cir": _cir("fixture-pending", 30)}, outputs={"compiled": True},
                  status=JobStatus.DONE, idempotency_key="pend", finished_at=NOW))
        # A halted certification says nothing about the design.
        s.add(Job(agent="quality_director", job_type="gate.certify",
                  inputs={"cir": _cir("fixture-pending", 30)},
                  outputs={"granted": False, "halted_by_incident": True},
                  status=JobStatus.DONE, idempotency_key="halt", finished_at=NOW))
    PL.harvest(db, category_for=_cat)
    by = {d["slug"]: d["first_pass"] for d in PL.designs(db)}
    assert by == {"fixture-tote-1": False, "fixture-tote-2": True, "fixture-pending": None}


def test_trend_is_unknown_on_small_samples_and_measured_when_real():
    db = _db()
    for i in range(4):
        _design(db, i, rows=30, compiled=True, granted=True, at=NOW - timedelta(days=1))
    PL.harvest(db, category_for=_cat)
    t = PL.first_pass_by_family(db, now=NOW)["families"]["tote"]
    assert t["trend"]["status"] == stats.UNKNOWN
    assert t["series"][-1]["status"] == stats.UNKNOWN          # 4 < TREND_MIN_N

    db = _db()
    rng = random.Random(2)
    for i in range(30):    # 10 weeks ago: 30% first pass
        _design(db, i, rows=30, compiled=True, granted=rng.random() < 0.3,
                at=NOW - timedelta(days=75, hours=i))
    for i in range(30, 60):  # this fortnight: 90% first pass
        _design(db, i, rows=30, compiled=True, granted=rng.random() < 0.9,
                at=NOW - timedelta(days=2, hours=i))
    PL.harvest(db, category_for=_cat)
    t = PL.first_pass_by_family(db, now=NOW)["families"]["tote"]["trend"]
    assert t["status"] == "MEASURED" and t["verdict"] == "improving", t

    db = _db()
    rng = random.Random(3)
    for i in range(60):    # same rate in both windows: never "improving"
        _design(db, i, rows=30, compiled=True, granted=rng.random() < 0.6,
                at=NOW - timedelta(days=75 if i < 30 else 2, hours=i))
    PL.harvest(db, category_for=_cat)
    t = PL.first_pass_by_family(db, now=NOW)["families"]["tote"]["trend"]
    assert t["verdict"] == "no_significant_change", t


def test_draft_refusal_and_code_sources():
    db = _db()
    with db.session() as s:
        s.add(Job(agent="crochet_engineer", job_type="cir.draft", inputs={"slug": "x-bag"},
                  outputs={"drafted": False, "gate": "construction", "construction": "refused",
                           "hold": "needs_charted_panel"},
                  status=JobStatus.DONE, idempotency_key="d1", finished_at=NOW))
    PL.harvest(db, category_for=_cat)
    from sqlalchemy import select

    from brambleloop.learning.store import PatternObservation

    with db.session() as s:
        o = s.scalar(select(PatternObservation))
        assert o.stage == "draft" and o.codes[0]["source"] == "construction"
    assert PL.source_of("REVERSE_MISMATCH", "certify") == "reverse"
    assert PL.source_of("FINISHED_SIZE_OUTSIDE", "certify") == "size_truth"
    assert PL.source_of("NAME_OUTRUNS_PATTERN", "certify") == "product_truth"
    assert PL.source_of("ROW_COUNT_MISMATCH", "compile") == "compiler"
    assert PL.code_of("ERROR TOPOLOGY_INCONSISTENT: x") == "TOPOLOGY_INCONSISTENT"


def test_fisher_is_exact():
    # 5/5 vs 0/5: p = 1/252
    assert abs(PL.fisher_greater(5, 5, 0, 5) - 1 / 252) < 1e-6
    assert PL.fisher_greater(0, 5, 5, 5) == 1.0


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{'FAILED' if fails else 'PASSED'}: {fails} failing")
    sys.exit(1 if fails else 0)
