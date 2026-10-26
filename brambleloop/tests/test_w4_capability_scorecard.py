"""Build 2 #94 Creativity Capability Scorecard: every named measure, over time, from the rows
the company writes. Unmeasured is UNMEASURED, never 0.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_capability_scorecard.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, ListingOutcome, Phase, Product  # noqa: E402
from brambleloop.creative import capability_scorecard as CS  # noqa: E402
from brambleloop.creative.audit import catalogue_concepts  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4cap_")
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/s{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _at(month):
    return datetime(2026, month, 15, tzinfo=timezone.utc)


def test_an_empty_company_is_unmeasured_everywhere_never_zero():
    rep = CS.scorecard(_db())
    assert rep["periods"] == [] and rep["market"]["winner_rate"] == "UNMEASURED"
    assert rep["objective"]["verdict"] == "UNMEASURED"
    assert rep["pending_market_evidence"] is True


def test_every_named_measure_is_combined_per_month_and_trended():
    db = _db()
    keys = [c.key for c in catalogue_concepts()]
    assert len(keys) >= 4
    with db.session() as s:
        for i, key in enumerate(keys[:4]):
            s.add(Product(slug=key, title=key, created_at=_at(9 if i < 2 else 10)))
        # tournaments: September 2 of 10 survive, October 5 of 10
        s.add(AuditLog(actor="creative_director", action="creative.tournament", at=_at(9),
                       detail={"field": {"generated": 10}, "survivors": ["a", "b"]}))
        s.add(AuditLog(actor="creative_director", action="creative.tournament", at=_at(10),
                       detail={"field": {"generated": 10}, "survivors": list("abcde")}))
        # blinded: an invalid September run is ignored; a valid October run counts
        s.add(AuditLog(actor="creative_director", action="creative.blinded", at=_at(9),
                       detail={"valid": False, "judged": 3, "ours": 3}))
        s.add(AuditLog(actor="creative_director", action="creative.blinded", at=_at(10),
                       detail={"valid": True, "judged": 20, "ours": 13}))
        # market: one concept with enough evidence and a sale, one seen too little
        s.add(ListingOutcome(product_slug=keys[0], period_start="2026-10-01",
                             period_end="2026-10-31", impressions=500, visits=25, orders=2,
                             source="test"))
        s.add(ListingOutcome(product_slug=keys[1], period_start="2026-10-01",
                             period_end="2026-10-31", impressions=40, visits=1, orders=0,
                             source="test"))
    rep = CS.scorecard(db)
    per = {p["period"]: p for p in rep["periods"]}
    assert per["2026-09"]["survival_rate"] == 0.2 and per["2026-10"]["survival_rate"] == 0.5
    assert per["2026-09"]["desirability_win_rate"] == "UNMEASURED"   # invalid run: not 0
    assert per["2026-10"]["desirability_win_rate"] == 0.65
    assert per["2026-09"]["novelty_mean"] != 0 and isinstance(
        per["2026-10"]["novelty_mean"], float)                        # new vs everything earlier
    assert isinstance(per["2026-10"]["fatigue_share"], float)
    m = rep["market"]["concepts"]
    assert m[keys[0]]["ctr"] == 0.05 and m[keys[0]]["conversion"] == 0.08
    assert m[keys[0]]["winner"] is True
    assert m[keys[1]]["ctr"] == "UNMEASURED" and m[keys[1]]["winner"] == "UNMEASURED"
    assert rep["market"]["winner_rate"] == 1.0
    assert rep["trends"]["quality"]["survival_rate"] == "improving"
    assert rep["objective"]["verdict"] in ("quality improving", "mixed")


def test_the_scorecard_job_runs_daily_and_stores_one_reading():
    assert ("capability_scorecard", "creative_director", "creative.capability_scorecard",
            86400) in CADENCES
    db = _db()
    Registry(db).authorize("creative_director", "creative.capability_scorecard")
    job = JobQueue(db).enqueue("creative_director", "creative.capability_scorecard", {})
    out = handlers.get("creative.capability_scorecard")(JobContext(
        job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    assert out["objective"] == "UNMEASURED" and out["winner_rate"] == "UNMEASURED"


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
