"""eng/r5-research-2: independent review of f95bd617 (research reaches the product pipeline).

H1 -- the real schedule blocked every new arena forever: on day 1 the answer was `low`, the
      writer proposed anyway, intake refused it (0.35 < 0.40) and `_already_proposed` then
      skipped the gap for good. Now nothing is proposed until the answer clears intake's own
      floor, and a refused proposal is re-eligible once its evidence rises.
H2 -- false facts from stale and withdrawn listings: compare() counted every stored row,
      ignoring shop freshness and withdrawn listings, and durability counted comparison runs.
      Now only fresh shops and live listings corroborate, durability is distinct observation
      dates per shop, facts name per-shop timestamps and listing ids, and a stale/withdrawn
      majority is UNKNOWN.
LOW -- one open research task per gap, refreshed in place, not a new task every day.

Every test drives the REAL scan, comparison, research and intake code through the real job
handlers; only the clock the watchlist module reads is set to a simulated day.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_r5_research_2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import _watchlist_sim as S  # noqa: E402
from brambleloop.intel import research, watchlist  # noqa: E402
from brambleloop.intel import watchlist_research as WR  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar import proposal_writer as W  # noqa: E402


def _real_cadence(db, reader, days_ago, *, compare_hour=6):
    """One simulated day on the production schedule (runtime.worker.CADENCES): the watchlist
    scan and concept intake every 6 h, the comparison daily, plus the daily research expiry
    (learn.scan) and the Research Agent's sweep."""
    from brambleloop.runtime import worker

    cad = {c[2]: c[3] for c in worker.CADENCES}
    assert cad["intel.watchlist_scan"] == cad["radar.concept_intake"] == 6 * 3600
    assert cad["intel.watchlist_compare"] == cad["research.sweep"] == 24 * 3600
    for hour in (0, 6, 12, 18):
        when = S.at(days_ago, hour)
        research.expire_due(db, now=when)
        S.scan(db, reader, when)
        if hour == compare_hour:
            S.compare(db, when.replace(minute=30))
            S.run_job(db, "research.sweep", agent="research_agent")
            for _ in range(3):   # the investigations the sweep queued, if any
                try:
                    S.run_job(db, "research.investigate", agent="research_agent")
                except AssertionError:
                    break
        S.intake(db, when.replace(minute=45))


def _approvals(db) -> list:
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        return [a.artifact for a in s.scalars(select(AuditLog).where(
            AuditLog.action == intake.APPROVED_ACTION))]


def test_h1_the_real_cadence_takes_a_new_arena_to_an_approved_concept():
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    # Durability (3 observation days) is reached on the real today: intake re-checks an
    # approval's research expiry against the real clock, so an approval on a simulated past
    # day would lapse at once.
    for days_ago in (2, 1):
        _real_cadence(db, reader, days_ago)
    # Two days in: corroborated, not yet durable -> nothing proposed, nothing refused.
    assert not [c for c in S.concepts(db) if c.state == intake.REFUSED], \
        [(c.slug, c.reasons) for c in S.concepts(db)]
    assert not S.concepts(db)
    for days_ago in (0, -1):
        _real_cadence(db, reader, days_ago)
    rows = S.concepts(db)
    assert _approvals(db), [(c.slug, c.state, c.reasons) for c in rows]
    assert not [c for c in rows if c.state == intake.REFUSED], \
        [(c.slug, c.reasons) for c in rows]
    gid, _ev, _state = S.gap(db)
    props = W.prior_proposals(db, gid)
    assert len(props) == 1 and props[0]["digest"], props
    # Review H3 (eng/r5-research-3): an approval record is not enough -- under continuously
    # fresh evidence the concept is STILL approved on every following day.
    slug = rows[0].slug
    for days_ago in (-2, -3, -4, -5, -6):
        _real_cadence(db, reader, days_ago)
        assert [c.state for c in S.concepts(db)] == [intake.APPROVED], \
            (days_ago, [(c.state, c.reasons) for c in S.concepts(db)])
        assert intake.seed_for(db, slug) is not None, days_ago


def test_h1_a_refused_proposal_is_re_eligible_when_its_evidence_rises():
    """A proposal refused on `low` evidence (as f95bd617 wrote on day 1, and as a production
    database may already hold) no longer blocks the gap once a durable answer exists."""
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    S.scan(db, reader, S.at(2, 6))
    S.compare(db, S.at(2, 7))
    gid, ev, _ = S.gap(db)
    tid = ev["research_task_id"]
    assert [t.state for t in S.tasks(db)] == [research.OPEN]
    # What the old code did on day 1: a low answer and a proposal on it, refused by intake.
    research.add_source(db, tid, source="fixture", citation="old low answer",
                        retrieval="internal", read_on=S.at(2).date())
    f = research.add_finding(db, tid, claim_class="fact", rests_on=["S1"],
                             statement="one day of corroboration")
    research.answer(db, tid, outcome="not yet shown durable", confidence="low",
                    now=S.at(2, 8), effect={"kind": "constraint_established",
                                            "statement": f"one day ({f})"},
                    conclusion={"alternatives": [], "constraints": ["one day"],
                                "unresolved": [], "next_test": {}, "applicability": {}})
    band = W.bands(W.POD_CONCEPTS[S.POD]["category"])
    intake.attach_proposal(db, tid, W.proposal_for(gid, S.POD, tid, 2, {
        "refs": [f, "S1"], "confidence": "low", "facts": 1}, band))
    S.intake(db, S.at(2, 9))
    assert [c.state for c in S.concepts(db)] == [intake.REFUSED]
    assert any("below 0.4" in r for r in S.concepts(db)[0].reasons)
    for d in (1, 0):
        research.expire_due(db, now=S.at(d, 5))
        S.scan(db, reader, S.at(d, 6))
        S.compare(db, S.at(d, 7))
        S.intake(db, S.at(d, 9))
    assert _approvals(db), [(c.state, c.reasons) for c in S.concepts(db)]


def test_h1_nothing_is_proposed_below_intakes_floor():
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    S.scan(db, reader, S.at(0, 6))
    S.compare(db, S.at(0, 7))
    got = W.write(db, today=S.TODAY)
    assert got["written"] == [], got
    assert any("not answered" in s["why"] or "floor" in s["why"]
               for s in got["skipped"] if s["pod"] == S.POD), got["skipped"]


def _stale_and_withdrawn(db):
    """The reviewer's reproduction: two shops last observed 30 days ago, every listing since
    withdrawn, and the daily comparison still running."""
    cats = S.default_catalogues()
    reader = S.Reader(cats)
    S.scan(db, reader, S.at(31, 6))
    cats["MadelineMaeCo"], cats["ZKBDESIGNER"] = [], []
    S.scan(db, reader, S.at(30, 6))           # the listings vanish: withdrawn
    for d in (2, 1, 0):
        S.compare(db, S.at(d, 7))
        S.intake(db, S.at(d, 9))


def test_h2_stale_shops_and_withdrawn_listings_are_never_a_fact():
    db = S.make_db()
    _stale_and_withdrawn(db)
    with S.clock(S.at(0, 8)):
        rep = watchlist.compare(db)
    assert all(a["pod"] != S.POD for a in rep["validated_arenas"]), rep["validated_arenas"]
    unknown = [a for a in rep["unknown_arenas"] if a["pod"] == S.POD]
    assert unknown and unknown[0]["value"] == "UNKNOWN", rep["unknown_arenas"]
    facts = [f for t in S.tasks(db) for f in (t.findings or []) if f["claim_class"] == "fact"]
    assert facts == [], facts
    assert [c for c in S.concepts(db) if c.state == intake.APPROVED] == []


def test_h2_stale_only_shops_are_unknown_even_with_live_rows():
    """Rows still live, but no shop observed for 30 days: never corroborated."""
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    S.scan(db, reader, S.at(30, 6))
    for d in (2, 1, 0):
        S.compare(db, S.at(d, 7))
    with S.clock(S.at(0, 8)):
        rep = watchlist.compare(db)
    assert [a["pod"] for a in rep["validated_arenas"]] == []
    assert [a["pod"] for a in rep["unknown_arenas"]] == [S.POD]
    assert not [f for t in S.tasks(db) for f in (t.findings or [])
                if f["claim_class"] == "fact"]


def test_h2_a_withdrawn_majority_is_unknown_even_with_two_fresh_shops():
    db = S.make_db()
    cats = S.default_catalogues()
    cats["MadelineMaeCo"] = S.dishcloths(5000, 10)
    cats["ZKBDESIGNER"] = S.dishcloths(6000, 10)
    reader = S.Reader(cats)
    S.scan(db, reader, S.at(0, 1))
    cats["MadelineMaeCo"] = S.dishcloths(5000, 3)
    cats["ZKBDESIGNER"] = S.dishcloths(6000, 3)
    S.scan(db, reader, S.at(0, 6))            # 14 of 20 rows withdrawn
    with S.clock(S.at(0, 7)):
        rep = watchlist.compare(db)
    assert [a["pod"] for a in rep["unknown_arenas"]] == [S.POD], rep
    assert "withdrawn" in rep["unknown_arenas"][0]["why"]


def test_h2_durability_is_distinct_observations_not_comparison_runs():
    """One scan, three daily comparisons: one observation date, so not durable."""
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    S.scan(db, reader, S.at(1, 23))
    for when in (S.at(1, 23).replace(minute=30), S.at(0, 1), S.at(0, 22)):
        S.compare(db, when)
    ts = S.tasks(db)
    assert len(ts) == 1 and ts[0].state == research.OPEN, [(t.state, t.confidence) for t in ts]
    assert not [f for f in ts[0].findings or [] if f["claim_class"] == "fact"]
    prog = (ts[0].detail or {})["watchlist_progress"]
    assert prog["days"] == 1, prog


def test_h2_facts_name_per_shop_timestamps_and_listing_ids():
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    for d in (2, 1, 0):
        S.scan(db, reader, S.at(d, 6))
        S.compare(db, S.at(d, 7))
    _gid, ev, _ = S.gap(db)
    t = next(x for x in S.tasks(db) if x.id == ev["research_task_id"])
    assert t.state == research.ANSWERED and t.confidence == "medium", (t.state, t.confidence)
    facts = [f for f in t.findings if f["claim_class"] == "fact"]
    assert len(facts) == 2
    now_fact, durable_fact = facts[0]["statement"], facts[1]["statement"]
    for lid in ("5000", "5001", "5002", "6000", "6001", "6002"):
        assert lid in now_fact, now_fact
    assert now_fact.count(S.at(0, 6).isoformat()) == 2, now_fact
    for d in (2, 1, 0):
        assert S.at(d).date().isoformat() in durable_fact, durable_fact
    blob = json.dumps([t.findings, t.sources, t.detail], default=str)
    for m in watchlist.WATCHLIST:
        assert m.shop_name.lower() not in blob.lower() and m.key not in blob
    assert "Dish Cloth" not in blob and "fixture.invalid" not in blob


def test_low_one_open_task_per_gap_refreshed_not_duplicated():
    """Before durability: one open task, refreshed daily. After approval: no new tasks."""
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    S.scan(db, reader, S.at(6, 6))
    for d in (6, 5, 4, 3, 2):                 # comparisons with no new scan after day 6
        research.expire_due(db, now=S.at(d, 5))
        S.compare(db, S.at(d, 7))
        S.run_job(db, "research.sweep", agent="research_agent")
    ts = S.tasks(db)
    assert [t.state for t in ts] == [research.OPEN], [(t.id, t.state) for t in ts]
    for d in (1, 0, -1, -2, -3):              # durable on day 0; then three more days
        research.expire_due(db, now=S.at(d, 5))
        S.scan(db, reader, S.at(d, 6))
        S.compare(db, S.at(d, 7))
        S.intake(db, S.at(d, 9))
    ts = S.tasks(db)
    seen = [(t.id, t.state, t.trigger) for t in ts]
    # Review H3 (eng/r5-research-3) changed the "no new task after approval" expectation: a
    # market_radar answer is fresh for one day, so the approved concept's support is renewed
    # exactly once per later day (days -1, -2, -3) -- never duplicated, never left open.
    # Review LOW (round 4): superseded renewal tasks are pruned to the last RENEWAL_KEEP, so
    # the once-per-day renewals are counted from the audit log, where every one is recorded.
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog
    from brambleloop.intel import watchlist_research as WR

    plain = [t for t in ts if "#renew:" not in t.trigger]
    renewals = [t for t in ts if "#renew:" in t.trigger]
    assert len(plain) == 1 and plain[0].state in (research.ANSWERED, research.EXPIRED), seen
    assert len(renewals) == WR.RENEWAL_KEEP, seen
    assert all(t.state in (research.ANSWERED, research.EXPIRED) for t in renewals), seen
    assert [t.state for t in renewals].count(research.ANSWERED) == 1, seen
    with db.session() as s:
        logged = list(s.scalars(select(AuditLog).where(AuditLog.action == WR.RENEWED)))
        by = [int(a.detail["renewed_by"]) for a in logged]
    assert len(by) == 3 and len(set(by)) == 3, by
    assert {t.id for t in renewals} == set(by[-WR.RENEWAL_KEEP:]), (by, seen)
    assert len({t.answered_at.date() for t in renewals}) == WR.RENEWAL_KEEP, seen
    assert _approvals(db)
    assert [c.state for c in S.concepts(db)].count(intake.REFUSED) == 0
    assert [c.state for c in S.concepts(db)] == [intake.APPROVED], \
        [(c.state, c.reasons) for c in S.concepts(db)]


def test_the_sweep_leaves_a_task_the_comparison_is_refreshing():
    from brambleloop.intel import research_agent

    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    S.scan(db, reader, S.at(0, 6))
    S.compare(db, S.at(0, 7))
    tid = S.tasks(db)[0].id
    assert tid not in research_agent.due_for_investigation(db, now=S.at(0, 8))
    # The comparison stopped refreshing it two days ago: the agent picks it up again.
    assert tid in research_agent.due_for_investigation(db, now=S.at(0, 8) +
                                                       WR.REFRESHED_WITHIN + S.timedelta(
                                                           hours=1))


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
