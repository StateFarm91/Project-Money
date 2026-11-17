"""Research M2 (review 6954809399): a watchlist gap reaches concept intake unattended.

Nothing in `src/` produced an answered research task with a `fact` finding, so every watchlist
gap was skipped by the proposal writer. `intel.watchlist_research.answer`, called by the daily
comparison, answers the gap's open question from the comparison readings already recorded.

Proved here on real-shaped rows (stored `intel.watchlist_compare` readings, the real
`record_comparison`, the real `radar.concept_intake` handler):
* three days of corroboration -> an answered task with dated, internal, fact-grade evidence ->
  a proposal -> an APPROVED radar concept;
* one day only -> confidence `low` -> no proposal (intake's evidence floor);
* what the readings cannot show (sales) is an `unresolved` finding, never a fact;
* a task that is not open is never touched; the daily re-opened question never proposes the
  same gap twice;
* no competitor shop name, title or URL is written.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws2_research_m2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import AuditLog, CoverageGap  # noqa: E402
from brambleloop.intel import research, watchlist  # noqa: E402
from brambleloop.intel import watchlist_research as WR  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar import proposal_writer as W  # noqa: E402
from brambleloop.runtime.etsy_ops import store_reading  # noqa: E402
from test_w5_concept_intake import TODAY, _db, _rows, _run  # noqa: E402

POD = "kitchen_bath"
ALIASES = ["bm-1a2b3c4d5e", "bm-6f7a8b9c0d"]


def _at(days_ago: int) -> datetime:
    return datetime.combine(TODAY - timedelta(days=days_ago), time(9), tzinfo=timezone.utc)


def _rep(when: datetime, arenas):
    return {"at": when.isoformat(), "shops": [], "scope": {},
            "validated_arenas": [{"pod": p, "corroborated_by": list(a)} for p, a in arenas],
            "copies_competitor_content": False, "uncertainty": "fixture"}


def _compare(db, days_ago: int, arenas=((POD, ALIASES),)):
    """Run the real `record_comparison` for one day, with the day's comparison report."""
    when = _at(days_ago)
    with patch.object(watchlist, "compare", lambda db_, now=None: _rep(when, arenas)):
        return watchlist.record_comparison(db, now=when)


def _gap(db):
    with db.session() as s:
        g = s.scalar(select(CoverageGap).where(CoverageGap.benchmark_key == "watchlist",
                                               CoverageGap.pod == POD))
        return g.id, dict(g.evidence or {})


def _task(db, tid):
    with db.session() as s:
        t = s.get(research.ResearchTask, tid)
        s.expunge(t)
        return t


def test_three_days_of_corroboration_reach_an_approved_concept_unattended():
    db = _db()
    for days_ago in (2, 1):
        for store_day in (days_ago,):
            store_reading(db, watchlist.COMPARE_READING, _rep(_at(store_day), [(POD, ALIASES)]),
                          now=_at(store_day))
    got = _compare(db, 0)
    assert got["research"] and got["research"][0]["answered"] is True, got["research"]
    gid, ev = _gap(db)
    t = _task(db, ev["research_task_id"])
    assert t.state == research.ANSWERED and t.confidence == "medium", (t.state, t.confidence)
    classes = [f["claim_class"] for f in t.findings]
    assert classes == ["fact", "fact", "unresolved"], t.findings
    assert all(s["retrieval"] == "internal" and s["read_on"] for s in t.sources), t.sources
    assert "UNKNOWN" in t.findings[2]["statement"] and "sell" in t.findings[2]["statement"]
    assert "3 of the 3" in t.findings[1]["statement"], t.findings[1]
    out = _run(db, "radar.concept_intake", {"as_of": TODAY.isoformat()}, key="t:m2:e2e")
    assert out["proposals_written"] == 1, out
    rows = _rows(db)
    assert rows and rows[-1].state == intake.APPROVED, [(r.slug, r.state, r.reasons)
                                                        for r in rows]
    blob = json.dumps([t.findings, t.sources, (t.detail or {}).get("concept_proposals")])
    for shop in watchlist.WATCHLIST:
        assert shop.shop_name.lower() not in blob.lower() and shop.key not in blob
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == WR.ACTION)) is not None


def test_one_day_of_corroboration_is_low_confidence_and_proposes_nothing():
    db = _db()
    got = _compare(db, 0)
    assert got["research"][0]["answered"] is True
    _gid, ev = _gap(db)
    t = _task(db, ev["research_task_id"])
    assert t.confidence == "low" and "1 of the 1" in t.findings[1]["statement"]
    # The writer passes the answer on; concept intake's evidence floor refuses a low one.
    _run(db, "radar.concept_intake", {"as_of": TODAY.isoformat()}, key="t:m2:low")
    rows = _rows(db)
    assert rows and all(r.state != intake.APPROVED for r in rows), [(r.state, r.reasons)
                                                                  for r in rows]
    assert any("below 0.4" in " ".join(r.reasons or []) for r in rows)


def test_a_task_that_is_not_open_is_never_touched():
    db = _db()
    q = research.open_question(
        db, question="Is buyer demand in the kitchen_bath arena durable across the watchlist shops?", trigger="watchlist_gap:999",
        decision_ref="x", domain="market_radar", query_terms=[POD], evidence_needed="x",
        stop_condition="x", if_unresolved="x", time_bound_days=14, now=_at(0))
    research.stop(db, q["task"], why="fixture: stopped by the agent",
                  remains_unknown="durability")
    store_reading(db, watchlist.COMPARE_READING, _rep(_at(0), [(POD, ALIASES)]), now=_at(0))
    out = WR.answer(db, gap_id=999, task_id=q["task"], pod=POD, now=_at(0))
    assert out["answered"] is False and "not open" in out["why"]
    assert _task(db, q["task"]).findings in ([], None) or all(
        f["claim_class"] != "fact" for f in _task(db, q["task"]).findings)


def test_no_reading_for_the_arena_answers_nothing():
    db = _db()
    q = research.open_question(
        db, question="Is buyer demand durable (none)?", trigger="watchlist_gap:998",
        decision_ref="x", domain="market_radar", query_terms=[POD], evidence_needed="x",
        stop_condition="x", if_unresolved="x", time_bound_days=14, now=_at(0))
    store_reading(db, watchlist.COMPARE_READING, _rep(_at(0), [("home_decor", ALIASES)]),
                  now=_at(0))
    out = WR.answer(db, gap_id=998, task_id=q["task"], pod=POD, now=_at(0))
    assert out["answered"] is False and _task(db, q["task"]).state == research.OPEN


def test_the_reopened_daily_question_never_proposes_the_same_gap_twice():
    db = _db()
    for d in (3, 2, 1):
        store_reading(db, watchlist.COMPARE_READING, _rep(_at(d), [(POD, ALIASES)]), now=_at(d))
    _compare(db, 1)
    assert W.write(db, today=TODAY - timedelta(days=1))["written"], "first proposal"
    gid, _ev = _gap(db)
    # The answer expires (market_radar freshness) and the question re-opens with "#after:".
    research.expire_due(db, now=_at(0) + timedelta(hours=1))
    _compare(db, 0)
    _gid, ev = _gap(db)
    assert _task(db, ev["research_task_id"]).state == research.ANSWERED
    second = W.write(db, today=TODAY)
    assert second["written"] == [], second
    assert any("already carries a proposal" in s["why"] for s in second["skipped"]
               if s["gap"] == gid), second["skipped"]


def test_the_durability_threshold_is_pinned():
    assert (WR.DURABLE_DAYS, WR.DURABILITY_WINDOW_DAYS) == (3, 14)


def test_a_reading_corroborated_by_one_shop_answers_nothing():
    db = _db()
    q = research.open_question(
        db, question="Is buyer demand in the kitchen_bath arena durable for one shop?",
        trigger="watchlist_gap:997", decision_ref="x", domain="market_radar",
        query_terms=[POD], evidence_needed="x", stop_condition="x", if_unresolved="x",
        time_bound_days=14, now=_at(0))
    store_reading(db, watchlist.COMPARE_READING, _rep(_at(0), [(POD, ALIASES[:1])]),
                  now=_at(0))
    out = WR.answer(db, gap_id=997, task_id=q["task"], pod=POD, now=_at(0))
    assert out["answered"] is False and _task(db, q["task"]).state == research.OPEN


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
