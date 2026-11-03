"""A8 P0-CULTURE-TO-IDEATION: a rising culture signal opens a research task that reaches
`radar.concept_intake` (wiring #6; acceptance in P0_WIRING_50937469.md s5).

Real runtime on a real SQLite FILE: the momentum readings are recorded through
`culture.radar.observe`, the registered `culture.ideate` job runs through a `Worker`, and the
A4(a) chain (`research.investigate` -> `radar.concept_intake` -> `radar.score` -> `cir.draft`)
runs through the scheduler and the worker exactly as in test_w5_a4a_research_to_concept, whose
fixtures this reuses. The only stand-in is A4(a)'s recorded vision verdict (model I/O). Every
reading, competitor listing, shop and price here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w5_a8_culture_to_ideation.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w5_a4a_research_to_concept as A  # noqa: E402
from brambleloop.core.models import CoverageGap, JobStatus  # noqa: E402
from brambleloop.culture import ideation_bridge as B  # noqa: E402
from brambleloop.culture import radar  # noqa: E402
from brambleloop.intel import research  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import ideation, intake  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

TODAY = date.today()


def _readings(db, signal: str, values) -> None:
    # Explicit test-fixture rights declaration; never invent one in production.
    from sqlalchemy import select
    from brambleloop.core.models import CultureSignal
    with db.session() as session:
        filed = session.scalar(select(CultureSignal.id).where(CultureSignal.key == signal))
    if filed is None:
        radar.record(db, radar.Signal(key=signal, topic=signal, domain="viral_aesthetic",
                                      sources=("synthetic fixture",)))
    for i, v in enumerate(values):
        radar.observe(db, signal, channel="reference", interest=v,
                      observed_on=(TODAY - timedelta(days=len(values) - i)).isoformat(),
                      source="fixture pageviews")


def _ideate(db) -> dict:
    job = JobQueue(db).enqueue("market_radar", "culture.ideate", {},
                               idempotency_key=f"t:ideate:{datetime.now().timestamp()}")
    w = Worker(db, "a8", job_types=["culture.ideate"])
    while w.run_once():                 # a cadence tick may have queued one ahead of it
        pass
    with db.session() as s:
        row = s.get(type(job), job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _culture_gaps(db) -> list[CoverageGap]:
    from sqlalchemy import select

    with db.session() as s:
        rows = list(s.scalars(select(CoverageGap).where(
            CoverageGap.benchmark_key == B.CULTURE_KEY).order_by(CoverageGap.id)))
        s.expunge_all()
        return rows


def test_a_rising_culture_signal_opens_a_research_task_that_reaches_concept_intake():
    db = A._db()
    _readings(db, "Dishcloth", (0.2, 0.35, 0.6))           # rising
    A._listings(db, "kitchen_bath", A.KITCHEN)
    out = _ideate(db)
    assert out["rising"] == ["Dishcloth"] and len(out["opened"]) == 1, out
    gaps = _culture_gaps(db)
    assert [(g.arena, g.pod) for g in gaps] == [("culture:Dishcloth", "kitchen_bath")]
    assert gaps[0].evidence["culture_signal"] == "Dishcloth"
    tasks = A._tasks(db)
    assert [t.trigger for t in tasks] == [f"ideation_gap:{gaps[0].id}"], tasks
    assert tasks[0].detail["ideation_brief"]["pod"] == "kitchen_bath"
    # the brief is A4(a)'s: the gap, its pod and its arena id; the topic is evidence only
    assert tasks[0].detail["ideation_brief"] == {"gap": gaps[0].id, "pod": "kitchen_bath",
                                                 "arena": "culture:Dishcloth"}
    restore = A._judge_intake_concepts()
    try:
        A._drive(db, datetime.now(timezone.utc))
    finally:
        restore()
    task = A._tasks(db)[0]
    assert task.state == research.ANSWERED, task.state
    slug = task.detail["concept_proposals"][0]["slug"]
    rows = [(r.slug, r.state, r.source_ref) for r in A._concepts(db)]
    assert (slug, intake.APPROVED, f"research_task:{task.id}") in rows, rows
    intakes = [j for j in A._jobs(db, "radar.concept_intake") if j.status == JobStatus.DONE]
    assert intakes, "concept_intake never ran"
    drafts = [j for j in A._jobs(db, "cir.draft") if j.idempotency_key == f"draft:{slug}"]
    assert len(drafts) == 1 and drafts[0].status == JobStatus.DONE, drafts
    # idempotent: another day's run opens nothing new
    again = _ideate(db)
    assert again["opened"] == [] and len(A._tasks(db)) == 1 and len(_culture_gaps(db)) == 1


def test_sensitive_falling_flat_single_reading_and_unplaced_signals_open_nothing():
    db = A._db()
    _readings(db, "Washcloth", (0.6, 0.3))                 # falling
    _readings(db, "Pot_holder", (0.4, 0.4))                # flat
    _readings(db, "Christmas_stocking", (0.5,))            # one reading: not a momentum
    _readings(db, "Cottagecore", (0.1, 0.5))               # rising, but no pod places it
    out = _ideate(db)
    assert out["rising"] == [] and out["opened"] == [] and _culture_gaps(db) == [], out
    why = {s["signal"]: s["why"] for s in out["skipped"]}
    assert "not rising" in why["Washcloth"] and "not rising" in why["Pot_holder"]
    assert why["Cottagecore"].startswith("unplaced")
    assert A._audits(db, B.UNPLACED) and len(A._audits(db, B.UNPLACED)) == 1
    _ideate(db)
    assert len(A._audits(db, B.UNPLACED)) == 1              # named once, not daily
    # sensitive: classify's own rule decides, whatever the momentum
    from brambleloop.culture import classify

    real = classify.sensitive
    classify.sensitive = lambda topic: "dishcloth" in str(topic).lower() or real(topic)
    try:
        _readings(db, "Dishcloth", (0.1, 0.9))
        out = _ideate(db)
    finally:
        classify.sensitive = real
    assert out["rising"] == [] and _culture_gaps(db) == [], out
    assert A._tasks(db) == []


def test_one_in_flight_a_second_rising_signal_waits_for_the_first():
    """A(4)a's bound holds for culture gaps too: the second waits, nothing is dropped."""
    db = A._db()
    _readings(db, "Dishcloth", (0.2, 0.6))
    _readings(db, "Christmas_stocking", (0.1, 0.7))
    out = _ideate(db)
    assert len(out["opened"]) == ideation.MAX_IN_FLIGHT == 1 and out["waiting"], out
    assert len(_culture_gaps(db)) == 2 and len(A._tasks(db)) == 1


def test_long_signal_keys_do_not_collapse_to_the_same_gap_after_restart():
    from brambleloop.core.db import Database

    db = A._db()
    prefix = "Dishcloth_" + "a" * 63
    first, second = prefix + "1", prefix + "2"
    assert len(first) <= 80 and f"culture:{first}"[:80] == f"culture:{second}"[:80]
    _readings(db, first, (0.2, 0.6))
    _readings(db, second, (0.1, 0.7))
    out = _ideate(db)
    gaps = _culture_gaps(db)
    assert len(gaps) == 2 and len({g.arena for g in gaps}) == 2, out
    assert {g.evidence["culture_signal"] for g in gaps} == {first, second}
    assert all(len(g.arena) <= 80 for g in gaps)
    fresh = Database(str(db.engine.url))
    _ideate(fresh)
    assert len(_culture_gaps(fresh)) == 2


def test_existing_long_signal_gap_is_reused_only_for_exact_identity():
    from brambleloop.intel import coverage

    db = A._db()
    prefix = "Dishcloth_" + "a" * 63
    first, second = prefix + "1", prefix + "2"
    old_arena = f"culture:{first}"[:80]
    old_id = coverage.upsert(db, benchmark_key=B.CULTURE_KEY, arena=old_arena,
                             pod="kitchen_bath", evidence={"culture_signal": first})
    _readings(db, first, (0.2, 0.6))
    _readings(db, second, (0.1, 0.7))
    _ideate(db)
    gaps = _culture_gaps(db)
    assert len(gaps) == 2, [(g.id, g.arena) for g in gaps]
    assert any(g.id == old_id and g.evidence["culture_signal"] == first for g in gaps)
    assert any(g.id != old_id and g.evidence["culture_signal"] == second for g in gaps)


def test_incomparable_stale_future_and_same_day_readings_do_not_create_a_trend():
    db = A._db()
    def observe(signal, channel, value, day, source):
        radar.observe(db, signal, channel=channel, interest=value,
                      observed_on=day.isoformat(), source=source)
    for key in ("Dishcloth", "Washcloth", "Potholder", "Pot_holder", "Hot_pad"):
        radar.record(db, radar.Signal(key=key, topic=key, domain="viral_aesthetic",
                                      sources=("synthetic fixture",)))
    # Mixed marketplace/reference scales can falsely look rising.
    observe("Dishcloth", "reference", 0.8, TODAY - timedelta(days=2), "ref")
    observe("Dishcloth", "marketplace", 0.1, TODAY - timedelta(days=1), "market")
    observe("Dishcloth", "marketplace", 0.5, TODAY, "market")
    # Distinct sources and duplicate readings on one date are not a series.
    observe("Washcloth", "reference", 0.1, TODAY - timedelta(days=2), "a")
    observe("Washcloth", "reference", 0.9, TODAY - timedelta(days=1), "b")
    observe("Potholder", "reference", 0.1, TODAY, "ref")
    observe("Potholder", "reference", 0.9, TODAY, "ref")
    observe("Pot_holder", "reference", 0.1, TODAY - timedelta(days=90), "ref")
    observe("Pot_holder", "reference", 0.9, TODAY - timedelta(days=89), "ref")
    observe("Hot_pad", "reference", 0.1, TODAY + timedelta(days=1), "ref")
    observe("Hot_pad", "reference", 0.9, TODAY + timedelta(days=2), "ref")
    result = _ideate(db)
    assert result["rising"] == [] and not _culture_gaps(db), result
    assert all("unknown" in item["why"] for item in result["skipped"]), result


def test_protected_or_undeclared_signal_stays_on_named_rights_hold():
    from brambleloop.culture.rights import ProtectedToken, WORK_TITLE

    db = A._db()
    # All names here are synthetic fixtures, not claims about a real work.
    radar.record(db, radar.Signal(key="Dishcloth", topic="Fixture", domain="film",
        tokens=(ProtectedToken(text="Oat Furrow", asset_class=WORK_TITLE,
                               source="synthetic fixture"),),
        sources=("synthetic fixture",)))
    _readings(db, "Dishcloth", (0.2, 0.6))
    # A feed can write observations without filing any rights declaration.
    for day, value in ((TODAY - timedelta(days=2), 0.2), (TODAY - timedelta(days=1), 0.6)):
        radar.observe(db, "Washcloth", channel="reference", interest=value,
                      observed_on=day.isoformat(), source="synthetic fixture")
    A._listings(db, "kitchen_bath", A.KITCHEN)
    out = _ideate(db)
    assert out["rising"] == [] and not _culture_gaps(db) and not A._tasks(db), out
    assert len([item for item in out["skipped"] if "rights hold" in item["why"]]) == 2, out


def test_the_job_is_registered_scheduled_and_banded():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.authority import classes
    from brambleloop.runtime.pipeline import WORK_KEYS
    from brambleloop.runtime.worker import CADENCES, handlers
    from brambleloop.swarm import orchestrate

    assert ("culture_ideate", "market_radar", "culture.ideate", 86400) in CADENCES
    assert handlers.get("culture.ideate") is not None
    assert "culture.ideate" in next(a for a in DEFAULT_AGENTS
                                    if a["name"] == "market_radar")["allowed_job_types"]
    assert not classes.is_gated("culture.ideate")
    assert WORK_KEYS["culture.ideate"] == ("work_done",)
    assert orchestrate.JOB_BANDS["culture.ideate"] == "benchmark_change"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:900])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
