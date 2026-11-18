"""eng/r5-research-2, round 4: independent review of 5f8c02aa.

M1  -- a shop that relists listings it withdrew never counted again. `observe.scan` updated
       `last_seen` on an unchanged listing but left `audit_state == "withdrawn"`, so
       `watchlist.compare` kept counting the row as withdrawn and the arena stayed UNKNOWN
       forever: never re-proposed. A relisted row is now live again; the withdrawal stays in
       its history (`detail.withdrawal_history`) with the relisting added.
LOW -- renewal tasks were kept one per approved concept per day, forever. Only the last
       `RENEWAL_KEEP` are kept; a superseded one is EXPIRED, older ones are pruned.
LOW -- an OPEN renewal task lingered after the concept was withdrawn. It is closed with the
       withdrawal, recorded on the task and in the audit log.

Every scenario drives the REAL scan, comparison, research and intake job handlers; only the
clock the watchlist module reads is set to a simulated day.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_r5_research_4.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import _watchlist_sim as S  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import AuditLog, BenchmarkListing  # noqa: E402
from brambleloop.intel import research, watchlist  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar import proposal_writer as W  # noqa: E402
from test_r5_research_3 import _approved_through_day_0, _day, _states  # noqa: E402

SHOP = "MadelineMaeCo"


def _rows(db, refs) -> dict[str, BenchmarkListing]:
    with db.session() as s:
        rows = {r.listing_ref: r for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.listing_ref.in_([str(x) for x in refs])))}
        s.expunge_all()
        return rows


def _arena(rep: dict) -> tuple[list, list]:
    return ([a for a in rep["validated_arenas"] if a["pod"] == S.POD],
            [a for a in rep["unknown_arenas"] if a["pod"] == S.POD])


def test_m1_a_relisted_listing_counts_again_and_keeps_its_withdrawal_history():
    db = S.make_db()
    cats = S.default_catalogues()
    full = list(cats[SHOP])
    reader = S.Reader(cats)
    S.scan(db, reader, S.at(0, 6))
    validated, _ = _arena(watchlist.compare(db, now=S.at(0, 7)))
    assert validated, "fixture: the arena is corroborated before the withdrawal"

    # The shop drops 2 of its 3 listings: the arena is no longer corroborated.
    cats[SHOP] = full[:1]
    S.scan(db, reader, S.at(-1, 6))
    dropped = [str(x["listing_id"]) for x in full[1:]]
    assert {r.audit_state for r in _rows(db, dropped).values()} == {"withdrawn"}
    validated, unknown = _arena(watchlist.compare(db, now=S.at(-1, 7)))
    assert not validated and unknown, (validated, unknown)

    # It lists the identical listings again: they are live, and the arena is corroborated.
    cats[SHOP] = full
    S.scan(db, reader, S.at(-2, 6))
    rows = _rows(db, dropped)
    assert all(r.audit_state != "withdrawn" for r in rows.values()), \
        {k: r.audit_state for k, r in rows.items()}
    for r in rows.values():
        hist = (r.detail or {}).get("withdrawal_history") or []
        assert len(hist) == 1, r.detail
        assert hist[0]["withdrawn_first_noticed"] and hist[0]["relisted_at"], hist
        assert "withdrawn_first_noticed" not in (r.detail or {}), r.detail
    validated, unknown = _arena(watchlist.compare(db, now=S.at(-2, 7)))
    assert validated and not unknown, (validated, unknown)
    for obs in validated[0]["observations"]:
        assert obs["live_listings"] == 3, validated


def test_m1_a_relisted_and_changed_listing_keeps_its_withdrawal_history():
    db = S.make_db()
    cats = S.default_catalogues()
    full = list(cats[SHOP])
    reader = S.Reader(cats)
    S.scan(db, reader, S.at(0, 6))
    cats[SHOP] = full[:1]
    S.scan(db, reader, S.at(-1, 6))
    changed = {**full[1], "title": "Dish Cloth Crochet Pattern revised",
               "last_modified_timestamp": 2000}
    cats[SHOP] = [full[0], changed, full[2]]
    S.scan(db, reader, S.at(-2, 6))
    rows = _rows(db, [full[1]["listing_id"], full[2]["listing_id"]])
    for r in rows.values():
        assert r.audit_state != "withdrawn", r.audit_state
        assert len((r.detail or {}).get("withdrawal_history") or []) == 1, r.detail


def test_m1_withdraw_then_relist_is_re_proposed_through_the_daily_cycle():
    """The reviewer's reproduction, end to end: the approved concept is withdrawn while the
    shop has withdrawn listings, and once the identical listings return the gap is
    proposed and approved again on the new evidence. On 5f8c02aa the arena stays UNKNOWN
    with 2 rows withdrawn and nothing is ever re-proposed."""
    db = S.make_db()
    cats = S.default_catalogues()
    full = list(cats[SHOP])
    reader = S.Reader(cats)
    first = _approved_through_day_0(db, reader)
    cats[SHOP] = full[:1]
    for d in (-1, -2, -3):
        _day(db, reader, d)
    assert S.concepts(db)[0].state == intake.WITHDRAWN, _states(db)
    cats[SHOP] = full
    for d in (-4, -5, -6):
        _day(db, reader, d)
    rows = S.concepts(db)
    assert rows[-1].state == intake.APPROVED, _states(db)
    assert rows[-1].source_ref != first.source_ref, _states(db)
    gid, _ev, _ = S.gap(db)
    assert len(W.prior_proposals(db, gid)) == 2


def test_low_renewal_tasks_are_bounded_per_approved_concept():
    from brambleloop.intel import watchlist_research as WR

    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    row = _approved_through_day_0(db, reader)
    ctask = int(row.source_ref.split(":")[1])
    for d in range(-1, -9, -1):
        _day(db, reader, d)
        assert [c.state for c in S.concepts(db)] == [intake.APPROVED], (d, _states(db))
        renewals = [t for t in S.tasks(db) if "#renew:" in t.trigger]
        assert len(renewals) <= WR.RENEWAL_KEEP, \
            (d, [(t.id, t.state, t.trigger) for t in renewals])
        with db.session() as s:
            rs = s.get(research.ResearchTask, ctask).detail["renewed_support"]
        assert len(rs["chain"]) <= WR.RENEWAL_KEEP and rs["chain"][-1] == rs["task"], rs
        live = [t for t in renewals if t.state == research.ANSWERED]
        assert [t.id for t in live] == [rs["task"]], [(t.id, t.state) for t in renewals]
        assert intake.renewed_evidence(db, ctask, today=S.at(d).date())["ok"], d
    assert rs["pruned"] >= 1, rs
    assert not [t for t in S.tasks(db) if t.state == research.OPEN], \
        [(t.id, t.state, t.trigger) for t in S.tasks(db)]
    with db.session() as s:
        renewed = list(s.scalars(select(AuditLog).where(
            AuditLog.action == WR.RENEWED)))
    assert len(renewed) >= 8, len(renewed)        # the full history is in the audit log


def test_low_an_open_renewal_task_is_closed_with_the_withdrawal():
    from brambleloop.intel import watchlist_research as WR

    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    _approved_through_day_0(db, reader)
    _day(db, reader, -1)
    for d in (-2, -3, -4, -5, -6):
        _day(db, reader, d, scan=False)
    assert [c.state for c in S.concepts(db)] == [intake.WITHDRAWN], _states(db)
    lingering = [t for t in S.tasks(db) if t.state == research.OPEN
                 and t.trigger.startswith("watchlist_gap:")]
    assert not lingering, [(t.id, t.trigger) for t in lingering]
    closed = [t for t in S.tasks(db) if (t.detail or {}).get("closed")]
    assert closed and all(t.state == research.EXPIRED for t in closed), closed
    with db.session() as s:
        assert s.scalar(select(AuditLog.id).where(
            AuditLog.action == WR.CLOSED_WITH_WITHDRAWAL)) is not None


def test_low_close_renewals_spares_a_gap_another_approved_concept_rests_on():
    from brambleloop.intel import watchlist_research as WR

    db = S.make_db()
    research._ensure(db)
    common = dict(question="Is buyer demand in the kitchen_bath arena durable across shops?",
                  decision_ref="intel.opportunity_review:gap:7", domain="market_radar",
                  evidence_needed="x", stop_condition="y", if_unresolved="z")
    a = research.open_question(db, trigger="watchlist_gap:7", **common)["task"]
    b = research.open_question(db, trigger="watchlist_gap:7#after:1", **{
        **common, "question": common["question"] + " again"})["task"]
    with db.session() as s:
        s.get(research.ResearchTask, a).state = research.ANSWERED
    assert WR.close_renewals(db, concept_task_id=a, why="t", keep_for={a, 99}) == [b]
    b2 = research.open_question(db, trigger="watchlist_gap:7#renew:5", **{
        **common, "question": common["question"] + " third"})["task"]
    other = research.open_question(db, trigger="watchlist_gap:7#x", **{
        **common, "question": common["question"] + " fourth"})["task"]
    with db.session() as s:
        s.get(research.ResearchTask, other).state = research.ANSWERED
    assert WR.close_renewals(db, concept_task_id=a, why="t", keep_for={other}) == []
    assert next(t for t in S.tasks(db) if t.id == b2).state == research.OPEN


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
