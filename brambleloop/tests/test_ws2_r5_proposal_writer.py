"""WS2 R5: validated watchlist gaps with answered research become concept proposals (CA$0).

Before this, `radar.intake.attach_proposal` had no production caller, so concept intake never
had automatic input. `radar.proposal_writer.write` is that caller. Every research source,
finding and competitor listing here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws2_r5_proposal_writer.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import AuditLog, BenchmarkListing, CoverageGap  # noqa: E402
from brambleloop.intel import research  # noqa: E402
from brambleloop.intel.benchmarks import MJS_KEY  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.radar import proposal_writer as W  # noqa: E402
from test_w5_concept_intake import TODAY, _answered_task, _db, _rows, _run  # noqa: E402


_N = iter(range(1, 10_000))


def _gap(db, pod="kitchen_bath", *, task=None, shops=("madeline_mae_co", "zkb_designer"),
         state="uncovered"):
    with db.session() as s:
        g = CoverageGap(benchmark_key=W.WATCHLIST_KEY, arena=f"watchlist:{pod}:{next(_N)}",
                        pod=pod,
                        state=state, evidence={"corroborated_by": list(shops),
                                               **({"research_task_id": task} if task else {})})
        s.add(g)
        s.flush()
        return g.id


def _task(db, trigger):
    tid, _f = _answered_task(db, trigger=trigger,
                             question=f"Is buyer demand in the arena durable? ({trigger})")
    return tid


def _proposals(db, tid):
    with db.session() as s:
        return list((s.get(research.ResearchTask, tid).detail or {}).get("concept_proposals")
                    or [])


def test_a_validated_gap_with_answered_research_gets_one_proposal_in_our_words():
    db = _db()
    tid = _task(db, "watchlist_gap:fixture-1")
    gid = _gap(db, task=tid)
    out = W.write(db, today=TODAY)
    assert [w["task"] for w in out["written"]] == [tid], out
    props = _proposals(db, tid)
    assert len(props) == 1
    p = props[0]
    assert p["slug"] == f"coaster-kitchen-bath-gap-{gid}" and p["category"] == "coaster"
    assert p["concept"]["construction"] == "flat_rows" and p["concept"]["pod"] == "kitchen_bath"
    assert p["evidence"] == ["F1", "S1"], p["evidence"]
    band = W.bands("coaster")
    assert p["price_cad"] == band["price_cad"] and p["maker_hours"] == band["maker_hours"]
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == W.ACTION))
        assert row.detail["slug"] == p["slug"]
    # Once per task: a second run writes nothing.
    assert W.write(db, today=TODAY)["written"] == []
    assert len(_proposals(db, tid)) == 1


def test_the_proposal_passes_intake_end_to_end_through_the_real_handler():
    """The real `radar.concept_intake` job writes the proposal and intake approves it."""
    db = _db()
    tid = _task(db, "watchlist_gap:fixture-e2e")
    _gap(db, task=tid)
    out = _run(db, "radar.concept_intake", {"as_of": TODAY.isoformat()}, key="t:intake:r5")
    assert out["proposals_written"] == 1, out
    rows = _rows(db)
    assert rows and rows[-1].state == intake.APPROVED, [(r.slug, r.state, r.reasons)
                                                        for r in rows]


def test_ineligible_gaps_are_skipped_with_their_reason():
    db = _db()
    open_task = research.open_question(
        db, question="Is the arena durable (open)?", trigger="watchlist_gap:open",
        decision_ref="x", domain="competitor_positioning", query_terms=["x"],
        evidence_needed="x", stop_condition="x", if_unresolved="x")["task"]
    cases = {
        _gap(db, task=_task(db, "watchlist_gap:a"), shops=("one_shop",)):
            "not corroborated by two",
        _gap(db, pod="garments", task=_task(db, "watchlist_gap:b")): "no category",
        _gap(db, task=None): "no research question",
        _gap(db, task=open_task): "not answered",
        _gap(db, task=_task(db, "watchlist_gap:c"), state="covered"): "already covered",
    }
    out = W.write(db, today=TODAY)
    assert out["written"] == []
    why = {s["gap"]: s["why"] for s in out["skipped"]}
    assert len(cases) == 5 and len(why) == 5, why
    for gid, needle in cases.items():
        assert needle in why[gid], (gid, why[gid])


def test_an_expired_or_unresolved_task_or_one_with_a_proposal_is_skipped():
    db = _db()
    tid = _task(db, "watchlist_gap:exp")
    with db.session() as s:
        s.get(research.ResearchTask, tid).expires_on = __import__("datetime").datetime(
            TODAY.year, TODAY.month, TODAY.day) - timedelta(days=1)
    gid = _gap(db, task=tid)
    assert "expired" in {s["gap"]: s["why"] for s in W.write(db, today=TODAY)["skipped"]}[gid]
    db = _db()
    tid = _task(db, "watchlist_gap:own")
    intake.attach_proposal(db, tid, {"slug": "owner-proposal"})
    gid = _gap(db, task=tid)
    assert "already carries" in {s["gap"]: s["why"]
                                 for s in W.write(db, today=TODAY)["skipped"]}[gid]
    assert [p["slug"] for p in _proposals(db, tid)] == ["owner-proposal"]


def test_only_fact_grade_findings_and_their_sources_are_cited():
    db = _db()
    tid = _task(db, "watchlist_gap:infer")
    research.add_finding(db, tid, statement="fixture: buyers may also want sets",
                         claim_class="inference", rests_on=["F1"], confidence="low")
    _gap(db, task=tid)
    W.write(db, today=TODAY)
    assert _proposals(db, tid)[0]["evidence"] == ["F1", "S1"]


def test_no_competitor_text_reaches_a_proposal():
    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=MJS_KEY, listing_ref="c1",
                               title="Secret Competitor Coaster Title", pod="kitchen_bath",
                               detail={"tags": ["secrettag"]}))
    tid = _task(db, "watchlist_gap:nocopy")
    _gap(db, task=tid)
    W.write(db, today=TODAY)
    text = json.dumps(_proposals(db, tid)).lower()
    assert "secret" not in text and "secrettag" not in text


def test_every_mapped_pod_is_a_supported_flat_rows_concept_in_the_closed_vocabulary():
    from brambleloop.creative import concept as C
    from brambleloop.intel.pods import POD_KEYS

    for pod, spec in W.POD_CONCEPTS.items():
        assert pod in POD_KEYS, pod
        assert spec["form"] in intake.SUPPORTED_FORMS[spec["category"]], pod
        assert spec["recipient"] in C.RECIPIENTS and spec["occasion"] in C.OCCASIONS
        assert spec["feeling"] in C.FEELINGS
        assert W.bands(spec["category"]) is not None, pod


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
