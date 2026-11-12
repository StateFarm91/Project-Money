"""A4A-2 (MED, evidence honesty) and A4A-3 (MED, liveness) from Main's verdict on A4a.

A4A-2: a crash after the research task was answered but before the proposal was attached
used to let the re-delivery build a proposal from TODAY's observations even below the
evidence floor; a listing with no price raised a TypeError. The floor is now re-checked at
attach time with a named outcome, and a missing price is refused.

A4A-3: an ended gap (insufficient evidence, no object, title clash, stall) was never
reopened. It now remembers the evidence it ended on and reopens -- once per new evidence
fingerprint, at most MAX_REOPENS times -- when that evidence changes.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_a4a_fix_floor_and_reopen.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import delete  # noqa: E402

from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.intel import research  # noqa: E402
from brambleloop.radar import ideation, intake  # noqa: E402
import test_w5_a4a_research_to_concept as T  # noqa: E402

NOW = datetime.now(timezone.utc)


def test_a4a2_a_crash_between_answer_and_attach_cannot_propose_below_the_floor():
    db = T._db()
    gid = T._gap(db, "kitchen_bath")
    T._listings(db, "kitchen_bath", T.KITCHEN)
    real = intake.attach_proposal

    def crash(*_a, **_k):
        raise RuntimeError("process died after the task was answered")

    intake.attach_proposal = crash
    try:
        try:
            T._drive(db, NOW)
        except AssertionError:
            pass
    finally:
        intake.attach_proposal = real
    task = T._tasks(db)[0]
    assert task.state == research.ANSWERED and not (task.detail or {}).get(
        "concept_proposals"), "fixture: answered, proposal not attached"
    # The observations thin out below the floor before the re-delivery.
    with db.session() as s:
        s.execute(delete(BenchmarkListing))
    T._listings(db, "kitchen_bath", T.KITCHEN[:1])

    class _Ctx:
        def __init__(self, db_):
            self.db = db_
            self.audits = []

        def audit(self, action, **kw):
            self.audits.append(action)

        def enqueue(self, *a, **k):
            return None

    ctx = _Ctx(db)
    out = ideation.investigate(ctx, task.id)
    assert out["proposed"] is False and out["outcome"] == ideation.OUT_INSUFFICIENT, out
    assert all(r.startswith("at attach: ") for r in out["reasons"]), out["reasons"]
    assert not (T._tasks(db)[0].detail or {}).get("concept_proposals")
    assert T._ideation(db, gid)["outcome"] == ideation.OUT_INSUFFICIENT


def test_a4a2_a_missing_price_is_refused_not_a_type_error():
    db = T._db()
    obs = {"object": ideation.POD_OBJECTS["kitchen_bath"][0], "price_median_cad": None,
           "pod": "kitchen_bath", "listings": 5, "shops": 3, "object_listings": 3,
           "oldest": "2026-11-01", "newest": "2026-11-08", "price_min_cad": None,
           "price_max_cad": None}
    out = ideation.build_proposal(db, 7, obs, finding="F1", source="S1")
    assert out == {"refused": ["no observed listing carries a price"]}, out


def test_a4a3_an_ended_gap_reopens_once_its_evidence_changes_and_is_bounded():
    db = T._db()
    gid = T._gap(db, "kitchen_bath")
    T._listings(db, "kitchen_bath", T.KITCHEN[:1])          # too thin: ends insufficient
    T._drive(db, NOW)
    assert T._ideation(db, gid)["outcome"] == ideation.OUT_INSUFFICIENT
    first_task = T._ideation(db, gid)["task"]
    # Next tick: the end is recorded with its evidence fingerprint; nothing reopens.
    T._drive(db, NOW + timedelta(days=1))
    rec = T._ideation(db, gid)
    assert rec.get("ended_fingerprint") and rec["task"] == first_task, rec
    T._drive(db, NOW + timedelta(days=2))
    assert T._ideation(db, gid)["task"] == first_task       # unchanged evidence: no reopen
    # New evidence arrives: the gap reopens with a new question.
    T._listings(db, "kitchen_bath", T.KITCHEN[1:], days_ago=1)
    restore = T._judge_intake_concepts()
    try:
        T._drive(db, NOW + timedelta(days=3))
    finally:
        restore()
    rec = T._ideation(db, gid)
    assert rec["task"] != first_task and rec.get("reopens") == 1, rec
    assert rec["history"][0]["task"] == first_task
    assert T._audits(db, ideation.REOPENED)
    triggers = sorted(t.trigger for t in T._tasks(db))
    assert any(tr.endswith(":reopen1") for tr in triggers), triggers


def test_a4a3_reopens_are_capped():
    assert ideation.MAX_REOPENS == 3
    assert set(ideation.REOPENABLE) >= set(ideation.NAMED_ENDS) | {"stalled"}


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception:  # noqa: BLE001
                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
