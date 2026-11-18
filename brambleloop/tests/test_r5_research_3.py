"""eng/r5-research-2, round 3: independent review of a459d73e.

H3 -- a watchlist concept was approved and stayed approved about one day. Its research answer
      is in domain `market_radar` (fresh one day), so it expired the next day and intake's
      `withdraw_unsupported` withdrew the concept; `_blocked_by_prior` and
      `_decided_by_proposal` then blocked the gap on any state but REFUSED, so nothing was
      re-proposed although fresh evidence arrived daily. Now the approved concept's support is
      renewed from fresh, durable observations before it expires (daily comparison, and the
      6-hourly intake job when it is about to expire), intake judges the renewed answer, and
      a concept withdrawn because the evidence genuinely went stale is re-eligible -- keyed on
      the new evidence digest -- once fresh durable evidence returns. Never on stale evidence.
LOW -- the writer's own floor check is pinned by a test that fails without it.
LOW -- the anchor shop's figures are graded by the age of its last good read.
LOW -- `intake.evaluate` no longer raises TypeError when the approved pool leaves the row out.

Every scenario drives the REAL scan, comparison, research and intake job handlers; only the
clock the watchlist module reads is set to a simulated day.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_r5_research_3.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import _watchlist_sim as S  # noqa: E402
from brambleloop.intel import research, watchlist  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar import proposal_writer as W  # noqa: E402


def _day(db, reader, days_ago, *, scan=True):
    """One simulated day on the production schedule (runtime.worker.CADENCES): research
    expiry, the watchlist scan and concept intake every 6 h, the comparison and the Research
    Agent's sweep daily. `scan=False`: the shops are not read that day (they go stale)."""
    from brambleloop.runtime import worker

    cad = {c[2]: c[3] for c in worker.CADENCES}
    assert cad["intel.watchlist_scan"] == cad["radar.concept_intake"] == 6 * 3600
    assert cad["intel.watchlist_compare"] == cad["research.sweep"] == 24 * 3600
    for hour in (0, 6, 12, 18):
        when = S.at(days_ago, hour)
        research.expire_due(db, now=when)
        if scan:
            S.scan(db, reader, when)
        if hour == 6:
            S.compare(db, when.replace(minute=30))
            S.run_job(db, "research.sweep", agent="research_agent")
            for _ in range(3):
                try:
                    S.run_job(db, "research.investigate", agent="research_agent")
                except AssertionError:
                    break
        S.intake(db, when.replace(minute=45))


def _states(db) -> list[tuple]:
    return [(c.id, c.slug, c.state, c.source_ref) for c in S.concepts(db)]


def _approved_through_day_0(db, reader):
    for d in (2, 1, 0):
        _day(db, reader, d)
    rows = S.concepts(db)
    assert [c.state for c in rows] == [intake.APPROVED], [(c.state, c.reasons) for c in rows]
    return rows[0]


def test_h3_an_approved_concept_stays_approved_while_evidence_stays_fresh():
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    row = _approved_through_day_0(db, reader)
    for d in (-1, -2, -3, -4, -5):
        _day(db, reader, d)
        rows = S.concepts(db)
        assert [c.state for c in rows] == [intake.APPROVED], \
            (d, [(c.state, c.reasons) for c in rows])
        # Downstream: release/product jobs still find the slug in the approved pool.
        assert intake.seed_for(db, row.slug) is not None, d
        ev = intake.renewed_evidence(db, int(row.source_ref.split(":")[1]),
                                     today=S.at(d).date())
        assert ev is not None and ev["ok"], (d, ev)
        # The support rests on that day's own comparison reading, not an older one.
        with db.session() as s:
            t = s.get(research.ResearchTask, int(row.source_ref.split(":")[1]))
            assert t.detail["renewed_support"]["reading_day"] == S.at(d).date().isoformat()
    gid, _ev, _ = S.gap(db)
    # Renewed from each day's reading (plus the intake job's last-chance renewal before the
    # old answer expires): at most two renewals a day, and the gap is never re-proposed.
    assert len(W.prior_proposals(db, gid)) == 1
    renewals = [t for t in S.tasks(db) if "#renew:" in t.trigger]
    assert 5 <= len(renewals) <= 10, [(t.id, t.state, t.trigger) for t in S.tasks(db)]
    assert not [t for t in S.tasks(db) if t.state == research.OPEN], \
        [(t.id, t.state, t.trigger) for t in S.tasks(db)]


def test_h3_stale_evidence_withdraws_and_fresh_evidence_re_proposes():
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    first = _approved_through_day_0(db, reader)
    _day(db, reader, -1)
    assert [c.state for c in S.concepts(db)] == [intake.APPROVED]
    # The shops are not read again: their last good read (day -1, 18:00) ages past 48 h.
    for d in (-2, -3, -4, -5, -6):
        _day(db, reader, d, scan=False)
    rows = S.concepts(db)
    assert [c.state for c in rows] == [intake.WITHDRAWN], _states(db)
    assert any("expired" in r for r in rows[0].reasons), rows[0].reasons
    assert intake.seed_for(db, first.slug) is None
    # Stale evidence never resurrects it, and nothing new is approved on it.
    gid, _ev, _ = S.gap(db)
    got = W.write(db, today=S.at(-6).date())
    assert got["written"] == [], got
    # Fresh, durable evidence returns: the gap is re-proposed on the new evidence.
    for d in (-7, -8):
        _day(db, reader, d)
    rows = S.concepts(db)
    states = [c.state for c in rows]
    assert states[0] == intake.WITHDRAWN and states[-1] == intake.APPROVED, _states(db)
    assert intake.REFUSED not in states, [(c.state, c.reasons) for c in rows]
    assert rows[-1].source_ref != first.source_ref
    assert intake.seed_for(db, first.slug) is not None
    priors = W.prior_proposals(db, gid)
    assert len(priors) == 2 and priors[0]["digest"] != priors[1]["digest"], priors
    # And it stays approved while the evidence stays fresh.
    for d in (-9, -10):
        _day(db, reader, d)
    assert S.concepts(db)[-1].state == intake.APPROVED, _states(db)
    assert len(W.prior_proposals(db, gid)) == 2


def test_h3_withdrawn_blocks_only_its_own_evidence():
    p = {"task": 1, "slug": "s", "quality": 0.7, "digest": "aaa"}
    assert W._blocked_by_prior([{**p, "state": intake.WITHDRAWN}], "aaa", 0.7)
    assert W._blocked_by_prior([{**p, "state": intake.WITHDRAWN}], "bbb", 0.7) is None
    for blocking in (None, intake.PROPOSED, intake.APPROVED):
        assert W._blocked_by_prior([{**p, "state": blocking}], "bbb", 0.9), blocking
    # A withdrawn prior next to an approved one: the approved one still blocks.
    assert W._blocked_by_prior([{**p, "state": intake.WITHDRAWN},
                                {**p, "task": 2, "state": intake.APPROVED}], "bbb", 0.9)


def test_h3_the_intake_job_renews_a_support_about_to_expire():
    """A late comparison cannot let the support lapse between two intake passes: the intake
    job renews a support that expires within 12 h from the latest fresh reading."""
    from brambleloop.intel import watchlist_research as WR

    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    row = _approved_through_day_0(db, reader)
    ctask = int(row.source_ref.split(":")[1])
    # Day -1: scans, but the comparison does not run; intake runs at 00:45 of day -1
    # (support answered day 0 06:30 expires day -1 06:30 -- within 12 h).
    S.scan(db, reader, S.at(-1, 0))
    S.intake(db, S.at(-1, 0).replace(minute=45))
    got = intake.renewed_support(db, ctask)
    assert got is not None, "the intake job did not renew the support"
    t = next(x for x in S.tasks(db) if x.id == got["task"])
    assert t.state == research.ANSWERED and t.trigger.endswith(f"#renew:{ctask}")
    assert S.concepts(db)[0].state == intake.APPROVED
    # Not due again (expires in ~24 h): no second renewal on the next pass.
    out = watchlist.renew_approved_support(db, now=S.at(-1, 6),
                                           expiring_within=WR.RENEW_AHEAD)
    assert out and not out[0].get("renewed"), out


def test_low_the_writers_own_floor_check_refuses_a_low_answer():
    """A task ANSWERED with `low` confidence passes every other writer check; only the
    writer's floor check (intake.research_evidence) keeps it from being proposed."""
    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    S.scan(db, reader, S.at(0, 6))
    S.compare(db, S.at(0, 7))
    gid, ev, _ = S.gap(db)
    tid = ev["research_task_id"]
    research.add_source(db, tid, source="fixture", citation="low answer",
                        retrieval="internal", read_on=S.at(0).date())
    f = research.add_finding(db, tid, claim_class="fact", rests_on=["S1"],
                             statement="one day of corroboration")
    research.answer(db, tid, outcome="not yet durable", confidence="low", now=S.at(0, 8),
                    effect={"kind": "constraint_established", "statement": f"one day ({f})"},
                    conclusion={"alternatives": [], "constraints": ["one day"],
                                "unresolved": [], "next_test": {}, "applicability": {}})
    got = W.write(db, today=S.TODAY)
    assert got["written"] == [], got
    why = [s["why"] for s in got["skipped"] if s["gap"] == gid]
    assert why and "floor" in why[0] and "below 0.4" in why[0], why


def _anchor_rows(db, last_seen: datetime):
    from brambleloop.core.models import BenchmarkListing

    with db.session() as s:
        for i in range(3):
            s.add(BenchmarkListing(benchmark_key=watchlist.WATCHLIST[0].key,
                                   listing_ref=str(9000 + i), title="fixture", pod=S.POD,
                                   price_cad=7.0, audit_state="discovered",
                                   first_seen=last_seen, last_seen=last_seen))


def test_low_the_anchor_is_graded_by_the_age_of_its_last_good_read():
    now = S.at(0, 12)
    for age, grade in ((timedelta(days=30), "STALE"), (timedelta(hours=1), "MEASURED")):
        db = S.make_db()
        _anchor_rows(db, now - age)
        rep = watchlist.compare(db, now=now)
        anchor = next(s for s in rep["shops"] if s["role"] == watchlist.ANCHOR)
        assert anchor["figures"]["listings_observed"]["grade"] == grade, (age, anchor)
        assert anchor["figures"]["price_median_cad"]["grade"] == grade, (age, anchor)


def test_low_evaluate_withdraws_instead_of_raising_when_the_pool_leaves_the_row_out():
    """Approved as of a past day whose research has since expired by the real clock: the
    hand-off finds no approved concept. Old code raised TypeError and failed the job."""
    from sqlalchemy import select

    from brambleloop.core.models import Job

    db = S.make_db()
    reader = S.Reader(S.default_catalogues())
    for d in (6, 5, 4):
        S.scan(db, reader, S.at(d, 6))
        S.compare(db, S.at(d, 7))
    out = S.intake(db, S.at(4, 9))            # the real job handler must finish
    rows = S.concepts(db)
    assert [c.state for c in rows] == [intake.WITHDRAWN], _states(db)
    assert any("not in the approved pool at hand-off" in r for r in rows[0].reasons), \
        rows[0].reasons
    assert out["approved"] == [], out
    with db.session() as s:
        assert s.scalar(select(Job.id).where(Job.job_type == "radar.score")) is None


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
