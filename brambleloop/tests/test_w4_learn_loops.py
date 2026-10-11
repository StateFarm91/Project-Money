"""W4-LEARN: the learning loops are measured experiments with a bounded backlog.

Production (0417f35, 2026-10-11) read: 15 improvement proposals all PROPOSED and "waiting for a
trial" on every sandbox pass; 379 lessons, 369 of them one per raw incident signature (300
`stale-artefact:<kind>:<slug>@<v>#<n>` rows), 0 acted on; the job-priority replay retired all
six challengers on 11,958 real jobs and would never re-judge them; the retrospective named
market_radar "regressed" and the bottleneck for 0.11 h -> 0.14 h of evidence age. Each test
holds one repair to the rows it moves.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import backlog, bus, cells, loops, mine  # noqa: E402


_REAL_REMEASURE = backlog.remeasure_delight


def _stub(fn) -> None:
    """Replace the delight re-measurement for one test (restored by the runner below)."""
    backlog.remeasure_delight = fn


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _improvement(db, iid):
    from brambleloop.core.models import Improvement

    with db.session() as s:
        r = s.get(Improvement, iid)
        return r.state, dict(r.evidence or {}), r.result_value


def _delight(db, *, slug="spooky-garland", driver="customization", score=3.0,
             days_old=0.0):
    """A delight proposal exactly as `teardown.lab._act_on_delight` writes one."""
    from brambleloop.core.models import Improvement

    iid = cells.propose(
        db, cell="product_creativity",
        hypothesis=(f"Raising {driver} on {slug} from {score} to at least 4 would make the "
                    f"product feel better than expected after purchase (#169)"),
        expected_effect=f"{driver} scores 4 or more on the next measured QA",
        rollback_ref=f"teardown-product-qa:{slug}", proposed_by="teardown_lab")
    with db.session() as s:
        row = s.get(Improvement, iid)
        row.baseline_ref = f"delight:{slug}:{driver}"
        row.baseline_value = score
        row.at = datetime.now(timezone.utc) - timedelta(days=days_old)
    return iid


# ---- lessons: one per pattern, not one per report ------------------------------------------


def test_incident_family_strips_instances_and_keeps_plain_signatures():
    slugs = frozenset({"hexie-coaster-set", "mosaic-placemat-pair"})
    fam = mine.incident_family
    assert fam("row-94-count") == "row-94-count"
    assert fam("stale-artefact:visual_truth:hexie-coaster-set@1.0.0#91") == \
        "stale-artefact:visual_truth"
    assert fam("stale-artefact:marketing_asset:hexie-coaster-set:teaser:d773dbe287cada4f",
               slugs=slugs) == "stale-artefact:marketing_asset"
    assert fam("seasonal.at_risk:mosaic-placemat-pair:Halloween", slugs=slugs) == \
        "seasonal.at_risk"
    assert fam("slo.breach:department_useful_work:product_truth") == \
        "slo.breach:department_useful_work:product_truth"
    assert fam("policy_stale:advertising_rules") == "policy_stale:advertising_rules"


def test_stale_artefact_reports_are_one_lesson_and_old_per_signature_lessons_are_superseded():
    from brambleloop.core.models import Incident, Lesson, Product

    db = _db()
    sigs = [f"stale-artefact:visual_truth:hexie-coaster-set@1.0.0#{n}" for n in (89, 90, 91)]
    with db.session() as s:
        s.add(Product(slug="hexie-coaster-set", title="Hexie coaster set"))
        for sig in sigs:
            s.add(Incident(severity="P1", signature=sig, product_slug="hexie-coaster-set",
                           summary="visual truth is older than its upstreams", detail={}))
    # What production's bus holds today: one lesson per raw signature.
    legacy = bus.publish(db, origin_cell="quality", subject="defect",
                         statement="Unresolved P1 incident for one artefact rebuild number 89",
                         evidence_ref=f"incident:{sigs[0]}")
    assert bus.compounding(db)["routed"] == 1

    out = mine.mine(db, fixture_dir=Path(tempfile.mkdtemp()))
    incident_groups = [e for e in out["published"] if e["kind"] == "incident"]
    assert [e["evidence_ref"] for e in incident_groups] == [
        "incident:stale-artefact:visual_truth"], out["published"]
    assert incident_groups[0]["members"] == 3
    family = incident_groups[0]["lesson"]
    assert out["superseded"] == [legacy]
    with db.session() as s:
        assert s.get(Lesson, legacy).superseded_by == family
        assert "incident family" in s.get(Lesson, family).statement
    comp = bus.compounding(db)
    assert comp["lessons"] == 1 and comp["superseded"] == 1, comp
    assert [l["id"] for l in bus.inbox(db, "runtime")] == [family]
    # Idempotent: the family is re-read tomorrow as the same lesson.
    again = mine.mine(db, fixture_dir=Path(tempfile.mkdtemp()))
    assert again["found"] == 0 and again["superseded"] == []


# ---- the bounded improvement backlog --------------------------------------------------------


def test_a_delight_hypothesis_whose_driver_rose_is_verified_on_its_own_metric():
    db = _db()
    iid = _delight(db)
    _stub(lambda _db, slug, driver: {
        "measured": True, "value": 4.0, "run_ref": f"delight:{slug}:{driver}:4.0",
        "why": "two certified sizes of one design"})
    out = backlog.evaluate(db)
    assert [v["improvement"] for v in out["verified"]] == [iid], out
    state, ev, result = _improvement(db, iid)
    assert state == cells.TESTING and result == 4.0
    assert ev["sandbox"]["by"] == backlog.EVALUATOR and ev["backlog"]["baseline"] == 3.0


def test_a_delight_hypothesis_whose_driver_fell_is_rejected_as_a_regression():
    db = _db()
    iid = _delight(db)
    _stub(lambda *_a: {
        "measured": True, "value": 2.0, "run_ref": "delight:x:2.0", "why": "fell"})
    out = backlog.evaluate(db)
    assert [v["improvement"] for v in out["regressed"]] == [iid]
    assert _improvement(db, iid)[0] == cells.REJECTED


def test_an_unchanged_delight_hypothesis_waits_inside_its_ttl_and_expires_after_it():
    db = _db()
    young = _delight(db, slug="spooky-garland", days_old=1)
    old = _delight(db, slug="hexie-coaster-set", days_old=backlog.DELIGHT_TTL_DAYS + 1)
    _stub(lambda _db, slug, driver: {
        "measured": True, "value": 3.0, "run_ref": "x", "why": "one certified size"})
    out = backlog.evaluate(db)
    assert [w["improvement"] for w in out["waiting"]] == [young]
    assert [e["improvement"] for e in out["expired"]] == [old]
    state, ev, _ = _improvement(db, old)
    assert state == cells.REJECTED and ev["why"].startswith("expired unexecuted")
    assert out["open_before"] == 2 and out["open_after"] == 1


def test_an_unreadable_driver_is_unknown_never_a_score():
    db = _db()
    iid = _delight(db, days_old=2)
    _stub(lambda *_a: {
        "measured": False, "value": None, "why": "nothing to read"})
    out = backlog.evaluate(db)
    assert out["waiting"][0]["measured"] is False and out["waiting"][0]["reading"] is None
    assert _improvement(db, iid)[2] is None


def test_untrialled_proposals_expire_and_an_over_full_cell_is_trimmed_oldest_first():
    from brambleloop.core.models import Improvement

    db = _db()
    ids = []
    for n in range(backlog.OPEN_CAP_PER_CELL + 3):
        ids.append(cells.propose(
            db, cell="quality", hypothesis=f"Tightening check number {n} would catch more "
                                           f"defects before release in the quality cell",
            expected_effect="fewer escaped defects", rollback_ref="code:abc",
            proposed_by="failure_miner"))
    with db.session() as s:
        s.get(Improvement, ids[0]).at = (datetime.now(timezone.utc)
                                         - timedelta(days=backlog.STALE_PROPOSAL_DAYS + 1))
    out = backlog.evaluate(db)
    assert [e["improvement"] for e in out["expired"]] == [ids[0]]
    assert [d["improvement"] for d in out["deferred"]] == ids[1:3]
    assert out["open_after"] == backlog.OPEN_CAP_PER_CELL


def test_the_delight_producer_is_admission_controlled():
    db = _db()
    iid = _delight(db, days_old=backlog.DELIGHT_TTL_DAYS + 1)
    cells.reject(db, iid, why="expired unexecuted: test")
    refused = backlog.admit_delight(db, cell="product_creativity",
                                    ref="delight:spooky-garland:customization")
    assert refused and refused["cooldown"]
    for n in range(backlog.OPEN_CAP_PER_CELL):
        _delight(db, slug=f"product-{n}")
    full = backlog.admit_delight(db, cell="product_creativity",
                                 ref="delight:new-product:customization")
    assert full and full["deferred"]
    assert backlog.admit_delight(db, cell="pattern_engineering",
                                 ref="delight:new-product:instruction_clarity") is None


def test_the_sandbox_pass_runs_the_backlog_and_says_so():
    from brambleloop.improve import runner

    db = _db()
    _delight(db, days_old=backlog.DELIGHT_TTL_DAYS + 1)
    out = runner.run(db, regression_dir=Path(tempfile.mkdtemp()))
    assert "backlog" in out and "error" not in out["backlog"], out.get("backlog")
    # The product has no certified version here, so its driver is UNKNOWN and it expires as
    # unmeasured rather than being scored.
    assert out["backlog"]["expired"][0]["why"] == "expired unmeasured"


# ---- the replay re-judges, and the retrospective does not call noise a regression -----------


def test_retired_replay_challengers_are_retrialled_after_the_retrial_window():
    from brambleloop.core.models import ConfigVersion, Job, JobStatus
    from brambleloop.improve import replay
    from brambleloop.swarm.orchestrate import clear_policy_cache

    clear_policy_cache()
    tmp = tempfile.mkdtemp(prefix="w4learn_")
    db = Database(f"sqlite:///{tmp}/r.sqlite")
    db.create_all()
    now = datetime.now(timezone.utc)
    with db.session() as s:      # equal jobs: no neighbour can beat the incumbent
        for d in range(5):
            t0 = (now - timedelta(days=6 - d)).replace(hour=1, minute=0, second=0,
                                                      microsecond=0)
            for i in range(10):
                s.add(Job(agent="orchestrator", job_type="improve.nightly", inputs={},
                          priority=85, status=JobStatus.DONE, created_at=t0, run_after=t0,
                          started_at=t0, finished_at=t0 + timedelta(minutes=5)))
    first = replay.cycle(db, now=now)
    assert first["ran"] and len(first["retired"]) == 6 and not first["proposed"]
    same_week = replay.cycle(db, now=now + timedelta(days=1))
    assert same_week["challengers_reopened"] == [] and same_week["compared"] == []
    with db.session() as s:
        for c in s.scalars(select(ConfigVersion).where(ConfigVersion.retired_at.is_not(None))):
            c.retired_at = now - timedelta(days=replay.RETRIAL_DAYS + 1)
    later = replay.cycle(db, now=now + timedelta(days=1))
    assert len(later["challengers_reopened"]) == 6
    assert len(later["compared"]) == 6 and len(later["retired"]) == 6
    db.engine.dispose()


def test_freshness_inside_the_scan_cadence_is_not_a_regression():
    db = _db()
    cells.record_capability(db, "market_radar", 0.11)
    cells.record_capability(db, "market_radar", 0.14)
    report = cells.retrospective(db)
    assert report["capability_movement"]["market_radar"]["direction"] == "flat"
    assert report["bottleneck"] != "market_radar"
    cells.record_capability(db, "market_radar", 30.0)      # a day stale: a real regression
    assert cells.retrospective(db)["capability_movement"]["market_radar"]["direction"] == \
        "regressed"


# ---- the scoreboard ------------------------------------------------------------------------


def test_the_scoreboard_reports_unknown_for_loops_without_data_never_zero():
    db = _db()
    board = loops.scoreboard(db)
    by = {x["loop"]: x for x in board["loops"]}
    assert set(by) >= {"capability_cells", "lesson_bus", "job_priority_replay",
                       "improvement_backlog", "realised_benefit", "growth_experiments",
                       "learn_gap_coverage"}
    for name in ("capability_cells", "job_priority_replay", "realised_benefit",
                 "growth_experiments"):
        assert by[name]["status"] == loops.UNKNOWN and by[name]["why"], by[name]
    assert len(board["loops"]) == len(loops.LOOPS)
    for entry in board["loops"]:
        if entry["status"] != loops.UNKNOWN:
            continue
        assert entry.get("why"), entry


def test_the_scoreboard_counts_a_decided_backlog_as_a_measured_loop():
    db = _db()
    _delight(db, days_old=backlog.DELIGHT_TTL_DAYS + 1)
    _stub(lambda *_a: {
        "measured": True, "value": 3.0, "run_ref": "x", "why": "unchanged"})
    backlog.evaluate(db)
    board = loops.scoreboard(db)
    impr = next(x for x in board["loops"] if x["loop"] == "improvement_backlog")
    assert impr["status"] == loops.MEASURED and impr["outcomes"]["decided"] == 1
    assert board["experiments"]["rejected"] == 1 and board["experiments"]["open"] == 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tests"))
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
            finally:
                backlog.remeasure_delight = _REAL_REMEASURE
    sys.exit(1 if fails else 0)
