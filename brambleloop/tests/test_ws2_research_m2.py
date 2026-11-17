"""Research M2 (reviews 6954809399, 6957516781): a watchlist gap reaches concept intake
unattended, from current observations only.

Driven through the real daily `intel.watchlist.record_comparison` (the real `compare()` over
stored scan state and `benchmark_listings` rows, nothing patched) and the real
`radar.concept_intake` handler, on the real cadence: a comparison each day and intake after it.

* H1: day 1 is low confidence -- nothing is proposed (intake's own floor), so nothing blocks
  the gap; by day 3 the answer is medium and the concept is APPROVED.
* H2: shops not scanned within FRESH_HOURS, and withdrawn listings, are not evidence: a stale or
  withdrawn majority answers nothing (UNKNOWN, task left open). Durability is distinct
  observation dates per shop, not comparison runs. Facts carry per-shop scan times and listing
  ids, and no shop name, title or URL.
* A refused proposal is re-eligible only when the evidence grade rises; a pending one blocks,
  and the comparison opens no new question for that gap.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws2_research_m2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import BenchmarkListing, CoverageGap  # noqa: E402
from brambleloop.intel import research, watchlist  # noqa: E402
from brambleloop.intel import watchlist_research as WR  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar import proposal_writer as W  # noqa: E402
from test_w5_concept_intake import TODAY, _db, _rows, _run  # noqa: E402

POD = "kitchen_bath"
SHOPS = ("madeline_mae_co", "zkbdesigner")


def _at(days_ago: int, hour: int = 9) -> datetime:
    return datetime.combine(TODAY - timedelta(days=days_ago), time(hour), tzinfo=timezone.utc)


def _observe(db, key, when, *, live=4, withdrawn=0, pod=POD):
    """One successful scan of a watchlist shop: its state, and its listing rows."""
    watchlist._save_state(db, key, {"state": "ok", "last_ok_at": when.isoformat(),
                                    "last_attempt_at": when.isoformat(),
                                    "consecutive_failures": 0, "shop": {}}, now=when)
    with db.session() as s:
        have = {r.listing_ref: r for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == key, BenchmarkListing.pod == pod))}
        for i in range(live + withdrawn):
            ref = f"{key[:3]}-{pod}-{i}"
            row = have.get(ref) or BenchmarkListing(benchmark_key=key, listing_ref=ref,
                                                    title=f"fixture {i}", pod=pod,
                                                    price_cad=12.0, first_seen=when)
            row.audit_state = "withdrawn" if i >= live else "discovered"
            row.last_seen = when
            s.add(row)


def _day(db, days_ago, *, scan=SHOPS, **kw):
    for key in scan:
        _observe(db, key, _at(days_ago), **kw)
    return watchlist.record_comparison(db, now=_at(days_ago, 10))


def _gap(db):
    with db.session() as s:
        g = s.scalar(select(CoverageGap).where(CoverageGap.benchmark_key == "watchlist",
                                               CoverageGap.pod == POD))
        return (g.id, dict(g.evidence or {})) if g else (None, {})


def _task(db, tid):
    with db.session() as s:
        t = s.get(research.ResearchTask, tid)
        s.expunge(t)
        return t


def test_the_real_cadence_proposes_nothing_low_and_approves_once_durable():
    db = _db()
    outcomes = []
    for days_ago in (2, 1, 0):
        got = _day(db, days_ago)
        day = (TODAY - timedelta(days=days_ago)).isoformat()
        out = _run(db, "radar.concept_intake", {"as_of": day}, key=f"t:m2:cad:{day}")
        outcomes.append((got["research"][0].get("confidence"), out["proposals_written"]))
    # Day 1 and 2: fewer than DURABLE_DAYS observation dates -> low -> no proposal at all.
    assert outcomes[:2] == [("low", 0), ("low", 0)], outcomes
    assert outcomes[2] == ("medium", 1), outcomes
    rows = _rows(db)
    assert rows and rows[-1].state == intake.APPROVED, [(r.state, r.reasons) for r in rows]
    _gid, ev = _gap(db)
    t = _task(db, ev["research_task_id"])
    assert [f["claim_class"] for f in t.findings] == ["fact", "fact", "unresolved"]
    assert all(s["retrieval"] == "internal" for s in t.sources)
    blob = json.dumps([t.findings, t.sources])
    assert f"{SHOPS[0][:3]}-{POD}-0" in blob                 # listing ids are cited
    for m in watchlist.WATCHLIST:                               # never a shop name or key
        assert m.shop_name.lower() not in blob.lower() and m.key not in blob


def test_stale_shops_answer_nothing():
    db = _db()
    for key in SHOPS:                                     # last scanned 30 days ago
        _observe(db, key, _at(30))
    got = watchlist.record_comparison(db, now=_at(0, 10))
    assert got["gaps"], "compare still validates the arena from stored rows"
    res = got["research"][0]
    assert res["answered"] is False and res["why"].startswith("UNKNOWN"), res
    _gid, ev = _gap(db)
    t = _task(db, ev["research_task_id"])
    assert t.state == research.OPEN and not [f for f in (t.findings or [])
                                             if f["claim_class"] == "fact"]


def test_withdrawn_listings_answer_nothing():
    db = _db()
    got = _day(db, 0, live=0, withdrawn=5)
    res = got["research"][0]
    assert res["answered"] is False and "UNKNOWN" in res["why"], res


def test_durability_counts_distinct_observation_dates_per_shop():
    """The second shop is not scanned on day 1; the comparison still carries its day-2 rows
    forward (and counts it), but that is one observation, not two."""
    db = _db()
    _day(db, 2)                                           # both scanned
    _day(db, 1, scan=SHOPS[:1])                           # only the first
    got = _day(db, 0)                                     # both again
    res = got["research"][0]
    assert res["answered"] is True and res["confidence"] == "low", res
    assert len(res["durable_shops"]) == 1, res
    t = _task(db, res["task"])
    stmt = t.findings[1]["statement"]
    assert ": 3 (" in stmt and ": 2 (" in stmt, stmt


def test_a_refused_proposal_is_re_eligible_only_when_the_grade_rises():
    db = _db()
    for days_ago in (2, 1, 0):
        _day(db, days_ago)
    gid, ev = _gap(db)
    tid = ev["research_task_id"]
    W.write(db, today=TODAY)
    intake._ensure(db)
    with db.session() as s:                               # intake refused it at 0.65
        rows = list(s.scalars(select(intake.RadarConcept).where(
            intake.RadarConcept.source_ref == f"research_task:{tid}")))
        if not rows:
            rows = [intake.RadarConcept(slug="fixture", source="research",
                                        source_ref=f"research_task:{tid}",
                                        fingerprint="f" * 64, seed={}, concept={}, brief={},
                                        evidence=[], reasons=[], detail={})]
            s.add(rows[0])
        for r in rows:
            r.state, r.quality = intake.REFUSED, 0.65
    assert "refused" in (W._blocking_proposal(db, gid, 0.65) or "")
    assert W._blocking_proposal(db, gid, 0.80) is None
    with db.session() as s:
        for r in s.scalars(select(intake.RadarConcept).where(
                intake.RadarConcept.source_ref == f"research_task:{tid}")):
            r.state = intake.PROPOSED
    assert "proposed" in (W._blocking_proposal(db, gid, 0.99) or "")
    # A pending proposal: the next comparison opens no new research question for the gap.
    with db.session() as s:
        before = len(list(s.scalars(select(research.ResearchTask))))
    _day(db, -1)
    with db.session() as s:
        after = len(list(s.scalars(select(research.ResearchTask))))
    assert after == before, (before, after)


def test_a_task_that_is_not_open_is_never_touched():
    db = _db()
    q = research.open_question(
        db, question="Is buyer demand in the kitchen_bath arena durable across the shops?",
        trigger="watchlist_gap:999", decision_ref="x", domain="market_radar",
        query_terms=[POD], evidence_needed="x", stop_condition="x", if_unresolved="x",
        time_bound_days=14, now=_at(0))
    research.stop(db, q["task"], why="fixture: stopped", remains_unknown="durability")
    for key in SHOPS:
        _observe(db, key, _at(0))
    out = WR.answer(db, gap_id=999, task_id=q["task"], pod=POD, now=_at(0, 10))
    assert out["answered"] is False and "not open" in out["why"]


def test_the_thresholds_are_pinned():
    assert (WR.DURABLE_DAYS, WR.DURABILITY_WINDOW_DAYS, WR.FRESH_HOURS) == (3, 14, 48)


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
