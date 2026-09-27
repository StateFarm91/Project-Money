"""Adversarial certification: the MJs mission, run end to end (#206-#228, #302-#316).

The 2026-09-27 proof-chain audit found the MJs libraries unit-tested and called by nothing.
Every test here drives the *runtime*: the `mjs.scan`, `intel.benchmark_health`,
`intel.pod_learning` and `mjs.seasonal_sentinel` handlers on a real worker, the
`swarm.allocate` reservation and the `/api/mjs/veto` route -- and asserts the library's
effect is persisted or enforced, with at least one adversarial case per gate.

No test fetches anything. Observations are stored by `observe.scan` driven by a recorded
fixture reader (the same injected-reader path `tests/test_intel.py` uses), and the Etsy
credential is removed so the handler's own scan is blocked and the mission pipeline runs on
what was stored. Every listing below is a fixture, not a real listing.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Agent, AuditLog, Benchmark, BenchmarkListing, CompetitiveStandard, CoverageGap, Incident,
    Job, JobStatus, Lesson, MjsMissionEvent, PodCapabilityReading, PodLesson, SwarmAllocation,
)
from brambleloop.intel import benchmarks, capacity, mission_runtime, observe  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

AS_OF = "2026-09-27"
NEW_TYPES = ("intel.benchmark_health", "intel.pod_learning", "mjs.seasonal_sentinel")

DESCRIPTION = (
    "Crochet PATTERN, PDF instant download, 14 pages. Written instructions and a stitch "
    "chart, US terms. Sizes XS, S, M, L, XL, 2XL, 3XL with finished measurements. Worsted "
    "weight yarn, about 1200 yards, 5 mm hook.")


class FixtureReader:
    """A recorded benchmark catalogue. Never touches a network."""

    def __init__(self, listings, images=6):
        self.listings = listings
        self.n_images = images

    def resolve_shop(self, name):
        return {"shop_id": 4242, "shop_name": name}

    def catalogue(self, shop_id, **kwargs):
        return list(self.listings)

    def images(self, ref):
        return [{"rank": i + 1, "hex_code": "1F3A2E", "hue": 150, "saturation": 30,
                 "brightness": 22, "is_black_and_white": False,
                 "url_fullxfull": f"https://fixture.invalid/{ref}/{i}.jpg"}
                for i in range(self.n_images)]

    def videos(self, ref):
        return []


def _listing(lid, title, favourites, *, description=DESCRIPTION, **extra):
    return {"listing_id": lid, "title": title,
            "price": {"amount": 850, "divisor": 100, "currency_code": "CAD"},
            "tags": ["crochet pattern"], "materials": ["yarn"], "state": "active",
            "last_modified_timestamp": 1000, "num_favorers": favourites, "taxonomy_id": 66,
            "is_digital": True, "description": description,
            "url": f"https://fixture.invalid/listing/{lid}", **extra}


BASELINE = [
    _listing(1002, "Striped Cardigan Crochet Pattern", 90),
    _listing(1003, "Chunky Granny Blanket Crochet Pattern", 40),
]
CROPPED = _listing(1001, "Cropped Striped Cardigan Pattern, V-Neck Button Cardigan", 180)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cert_mjs_')}/mjs.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    with db.session() as s:
        agent = s.scalar(select(Agent).where(Agent.name == "market_radar"))
        agent.allowed_job_types = list(agent.allowed_job_types or []) + list(NEW_TYPES)
    return db


def _no_credential():
    saved = {k: os.environ.pop(k, None) for k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET",
                                                  "ETSY_KEYSTRING")}
    return saved


def _restore(saved):
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


def _run(db, job_type: str, inputs: dict | None = None, *, agent="market_radar") -> dict:
    saved = _no_credential()
    try:
        job = JobQueue(db).enqueue(agent, job_type, {"as_of": AS_OF, **(inputs or {})},
                                   priority=0,
                                   idempotency_key=f"t:{job_type}:{os.urandom(4).hex()}")
        assert Worker(db, "cert-mjs", job_types=[job_type]).run_once()
    finally:
        _restore(saved)
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _scan(db, listings, images=6):
    observe.scan(db, FixtureReader(listings, images=images), env={})


def _events(db) -> list[MjsMissionEvent]:
    with db.session() as s:
        rows = list(s.scalars(select(MjsMissionEvent).order_by(MjsMissionEvent.id)))
        s.expunge_all()
        return rows


def _mission(db) -> MjsMissionEvent:
    _scan(db, BASELINE)
    _scan(db, BASELINE + [CROPPED])
    out = _run(db, "mjs.scan")
    assert out["ran"] is False, "the handler's own scan must be blocked with no credential"
    assert out["mission"]["processed"] == 1, out
    return next(e for e in _events(db) if e.listing_ref == "1001")


# ---- #214 / #211 / #216 / #308: the new-listing event, end to end -----------------------


def test_owner_christmas_cardigan_is_produced_by_the_runtime_from_observed_data():
    """#308 as a fixture over #306/#307: nothing here names Christmas or a palette."""
    db = _db()
    ev = _mission(db)
    assert ev.pod == "garments" and ev.arena == "cardigan"
    assert ev.proven is True and ev.entered is True
    decision = ev.steps["response"]["consider_arena"]
    assert decision["enter"] is True
    preserved = {c["key"] for c in decision["preserved_characteristics"]}
    assert {"silhouette", "colour_blocking", "neckline", "closure"} <= preserved, preserved
    target = ev.steps["response"]["seasonal_target"]
    assert target["event"] == "Christmas", target
    assert target["make_hours_basis"].startswith("assumed")
    seas = ev.steps["response"]["seasonalise"]
    assert seas["complete"] is True and seas["palette_only"] is False
    assert seas["answered"]["colour_palette"] == "forest, cranberry, cream and gold"


def test_a_new_listing_runs_every_step_in_order_and_enqueues_a_divergent_tournament():
    db = _db()
    ev = _mission(db)
    assert list(ev.steps) == ["routing", "decomposition", "panel", "lessons", "memory",
                              "coverage", "response", "breakthrough"]
    # 1 director
    assert ev.steps["routing"]["standing"]["catalogue_breadth"] == "behind"
    assert ev.steps["routing"]["standing"]["beginner_support"] == "unknown"
    # 2 decomposition: mechanisms from observed fields only; unread inputs are unknown
    classes = set(ev.steps["decomposition"]["classes_covered"])
    assert {"presentation", "information", "range"} <= classes
    assert ev.decision == "run_a_tournament"
    # 4 + 5 lessons and memory
    assert ev.steps["lessons"]["written"] and ev.steps["memory"]["learned"]
    with db.session() as s:
        held = {r.subject for r in s.scalars(select(PodLesson).where(
            PodLesson.pod == "garments"))}
    assert {"mjs:gallery_depth", "mjs:size_range", "mjs:deliverable_stated"} <= held
    # 6 coverage left 'uncovered'
    with db.session() as s:
        gap = s.get(CoverageGap, ev.gap_id)
        assert gap.state == "concepting", gap.state
    # 8 the divergent tournament, labelled with what it was diverged from
    with db.session() as s:
        job = s.get(Job, ev.tournament_job_id)
        assert job.job_type == "creative.tournament" and job.agent == "creative_director"
        assert job.inputs["lane"] == "breakthrough"
        assert job.inputs["diverged_from"] == "observed_market"
        assert job.inputs["mjs_event_id"] == ev.id
        assert job.priority == orc.priority_for("creative.tournament")
    # #309: the stages ran in order and stopped at the first gate that has not passed
    assert ev.pipeline["completed"] == ["observation", "pod_routing", "market_decomposition",
                                        "demand_and_season_fit"]
    assert ev.pipeline["stopped"]["stage"] == "seasonal_tournament"
    with db.session() as s:
        audited = s.scalar(select(AuditLog).where(AuditLog.action == "mjs.mission_events"))
        assert audited is not None


def test_the_director_never_reasons_over_the_same_listing_content_twice():
    db = _db()
    _mission(db)
    again = _run(db, "mjs.scan")
    assert again["mission"]["processed"] == 0 and again["mission"]["pending"] == 0
    assert len(_events(db)) == 1


def test_a_baseline_is_not_a_market_event():
    db = _db()
    _scan(db, BASELINE + [CROPPED])
    out = _run(db, "mjs.scan")
    assert out["mission"]["pending"] == 0 and not _events(db)


# ---- gates: adversarial cases --------------------------------------------------------------


def test_ceiling_check_refuses_a_parity_objective_and_nothing_is_started():
    """#227: an objective naming the benchmark as the thing to match stops the lane."""
    db = _db()
    _scan(db, BASELINE)
    _scan(db, BASELINE + [CROPPED])
    queued = []
    out = mission_runtime.process(db, enqueue=lambda *a, **k: queued.append(a),
                                  today=date.fromisoformat(AS_OF),
                                  objective="match MJs on the cropped cardigan")
    ev = next(e for e in _events(db) if e.listing_ref == "1001")
    assert ev.steps["panel"]["ceiling"]["permitted"] is False
    assert ev.entered is False and not queued and ev.tournament_job_id is None
    with db.session() as s:
        assert s.get(CoverageGap, ev.gap_id).state == "uncovered"
    assert ev.steps["response"]["consider_arena"]["enter"] is False
    assert out["processed"] == 1


def test_may_enter_refuses_an_arena_whose_incumbent_nobody_decomposed():
    """#215: a listing with no observable mechanism cannot be entered blind."""
    db = _db()
    bare = _listing(1004, "Oversized Cardigan Crochet Pattern", 300, description="")
    _scan(db, BASELINE)
    _scan(db, BASELINE + [bare], images=1)
    _run(db, "mjs.scan")
    ev = next(e for e in _events(db) if e.listing_ref == "1004")
    assert ev.proven is True
    assert ev.steps["panel"]["may_enter"]["may_enter"] is False
    assert "blind" in ev.steps["panel"]["may_enter"]["why"]
    assert ev.entered is False and ev.tournament_job_id is None
    assert ev.steps["response"]["consider_arena"]["enter"] is False


def test_an_unproven_arena_is_considered_and_refused_with_a_reason():
    """#306: MUST consider is satisfied by a recorded refusal, never by silence."""
    db = _db()
    quiet = _listing(1005, "Striped Beanie Hat Crochet Pattern", 12)
    _scan(db, BASELINE)
    _scan(db, BASELINE + [quiet])
    _run(db, "mjs.scan")
    ev = next(e for e in _events(db) if e.listing_ref == "1005")
    assert ev.arena == "hat" and ev.proven is False and ev.entered is False
    decision = ev.steps["response"]["consider_arena"]
    assert decision["enter"] is False and "not demonstrated" in decision["reason"]
    assert ev.steps["response"]["seasonalise"] is None


def test_the_bar_is_raised_only_by_two_sellers_and_never_lowered():
    """#219 + #220 through the runtime: one shop is a preference, and a slip lowers nothing."""
    db = _db()
    ev = _mission(db)
    bar = {b["standard"]: b for b in ev.steps["panel"]["bar"]}
    assert bar["gallery_images"]["outcome"] == "raised"
    assert bar["gallery_images"]["applied"] is False and bar["gallery_images"]["held"]
    assert ev.steps["panel"]["panel_state"]["is_a_panel"] is False
    with db.session() as s:
        std = s.scalar(select(CompetitiveStandard).where(
            CompetitiveStandard.key == "gallery_images"))
        assert std.value is None and std.history[-1]["applied"] is False

    # A second, independent seller shows the same mechanism in the same pod.
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="fixture_second_seller", listing_ref="x1",
                               title="Fitted Cardigan Pattern", pod="garments",
                               fingerprint="f", media_count=8,
                               detail={"gallery_audited": True}))
    _scan(db, BASELINE + [CROPPED, _listing(1006, "Boxy Cardigan Crochet Pattern", 70)],
          images=9)
    _run(db, "mjs.scan")
    raised = next(e for e in _events(db) if e.listing_ref == "1006")
    gal = next(b for b in raised.steps["panel"]["bar"] if b["standard"] == "gallery_images")
    assert raised.steps["panel"]["learnable"]["gallery_depth"]["learnable"] is True
    assert gal["outcome"] == "raised" and gal["applied"] is True
    with db.session() as s:
        assert s.scalar(select(CompetitiveStandard.value).where(
            CompetitiveStandard.key == "gallery_images")) == 9.0

    _scan(db, BASELINE + [CROPPED, _listing(1006, "Boxy Cardigan Crochet Pattern", 70),
                          _listing(1007, "Cropped Cardigan Crochet Pattern", 40)], images=6)
    _run(db, "mjs.scan")
    slipped = next(e for e in _events(db) if e.listing_ref == "1007")
    gal = next(b for b in slipped.steps["panel"]["bar"] if b["standard"] == "gallery_images")
    assert gal["outcome"] == "refused_lowering" and gal["applied"] is False
    with db.session() as s:
        assert s.scalar(select(CompetitiveStandard.value).where(
            CompetitiveStandard.key == "gallery_images")) == 9.0


def test_pods_lesson_refuses_protected_expression_at_the_point_of_writing():
    """#217: the guard the runtime lessons pass through is the one that refuses a copy."""
    from brambleloop.intel import pods

    try:
        pods.lesson("garments", "styling", "copy the pattern text of row 1 into ours")
    except pods.MechanismRefused:
        pass
    else:
        raise AssertionError("a competitor's instructions were accepted as a lesson")


def test_repetition_moves_nothing_and_contradiction_raises_a_challenger_that_wins():
    """#316: outcomes from later benchmark listings, a challenger, and resolution on outcomes."""
    db = _db()
    _mission(db)
    small = [_listing(2000 + i, f"Relaxed Cardigan Crochet Pattern {i}", 30)
             for i in range(3)]
    listings = BASELINE + [CROPPED]
    for extra in small:
        listings = listings + [extra]
        _scan(db, listings, images=2)
        _run(db, "mjs.scan")
    with db.session() as s:
        rows = list(s.scalars(select(PodLesson).where(
            PodLesson.pod == "garments", PodLesson.subject == "mjs:gallery_depth")))
        incumbent = next(r for r in rows if r.origin == "observation")
        challenger = next(r for r in rows if r.origin == "challenger")
        assert len(incumbent.contradicted_by) >= 2 and not incumbent.supported_by
        assert all(e["kind"] == "benchmark_contradicted" for e in incumbent.contradicted_by)
        assert challenger.active is True and incumbent.active is False
        assert incumbent.superseded_by == challenger.id
        # Seeing the size range again is repetition: still one version, not four.
        sizes = list(s.scalars(select(PodLesson).where(
            PodLesson.pod == "garments", PodLesson.subject == "mjs:size_range")))
        assert len([r for r in sizes if r.origin == "observation"]) == 1
        assert len(sizes[0].supported_by) >= 3


# ---- #206 URL health ---------------------------------------------------------------------


def test_benchmark_health_is_unverified_without_a_capability_and_refuses_a_stranger():
    db = _db()
    out = _run(db, "intel.benchmark_health")
    assert out["states"] == ["unverified"] and out["capability"] == "unverified"

    saved = benchmarks.fetcher_for
    try:
        benchmarks.fetcher_for = lambda db, env=None: (
            lambda url: (200, "https://www.etsy.com/ca/shop/Impostor"))
        out = _run(db, "intel.benchmark_health")
        assert out["states"] == ["wrong_shop"] and out["incidents_opened"]
        with db.session() as s:
            row = s.scalar(select(Benchmark).where(Benchmark.key == benchmarks.MJS_KEY))
            assert row.canonical_url == benchmarks.MJS_CANONICAL_URL
            assert s.scalar(select(Incident).where(
                Incident.signature == f"benchmark.url_health:{benchmarks.MJS_KEY}",
                Incident.resolved == False)) is not None  # noqa: E712

        moved = "https://www.etsy.com/shop/MJsOffTheHookDesigns"
        benchmarks.fetcher_for = lambda db, env=None: (lambda url: (200, moved))
        out = _run(db, "intel.benchmark_health")
        assert out["states"] == ["moved"]
        benchmarks.seed(db)   # a deploy must not put the old route back
        with db.session() as s:
            row = s.scalar(select(Benchmark).where(Benchmark.key == benchmarks.MJS_KEY))
            assert row.canonical_url == moved
            assert s.scalar(select(Incident).where(
                Incident.signature == f"benchmark.url_health:{benchmarks.MJS_KEY}",
                Incident.resolved == False)) is None  # noqa: E712
    finally:
        benchmarks.fetcher_for = saved


# ---- #213 seasonal urgency in the adaptive interval -----------------------------------------


def test_seasonal_pressure_tightens_the_scan_interval_at_runtime():
    from datetime import datetime, timezone

    db = _db()
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    calm = observe.adaptive_interval(db, now=now, seasonal=False)
    ramp = observe.adaptive_interval(db, now=now, seasonal=True)
    assert calm["interval_seconds"] == observe.FIXED_INTERVAL_SECONDS
    assert ramp["interval_seconds"] == observe.SEASONAL_CEILING_SECONDS
    assert ramp["bounded_by"] == "seasonal"
    # Undirected, the calendar decides: Halloween is 34 days away on this date.
    assert observe.adaptive_interval(db, now=now)["seasonal_pressure"] is True
    quiet = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    assert observe.adaptive_interval(db, now=quiet)["seasonal_pressure"] is False
    # scan_due consumes it: 4 hours since a scan is due in a ramp and not otherwise.
    from brambleloop.core.models import BenchmarkObservation
    with db.session() as s:
        s.add(BenchmarkObservation(benchmark_key=benchmarks.MJS_KEY, kind="official_api_read",
                                   at=now - timedelta(hours=4), detail={"changes": []}))
    assert observe.scan_due(db, now=now, seasonal=True)["due"] is True
    assert observe.scan_due(db, now=now, seasonal=False)["due"] is False


# ---- #226 pod capability from rows ---------------------------------------------------------


def test_pod_capability_is_computed_from_rows_and_unmeasured_is_never_zero():
    db = _db()
    _mission(db)
    out = _run(db, "intel.pod_learning")
    assert out["pods"] >= 1 and out["records"] >= 1 and out["judgements"] >= 1
    with db.session() as s:
        reading = s.scalar(select(PodCapabilityReading).where(
            PodCapabilityReading.pod == "garments"))
        assert reading is not None and reading.measured is False
        assert reading.discernment["reading"] == "unmeasured"
        assert "precision" not in reading.discernment
        assert reading.balance["records"] >= 1


# ---- #302 the reserved floor in swarm.allocate --------------------------------------------


def test_allocate_reserves_the_mission_floor_and_records_it():
    db = _db()
    q = JobQueue(db)
    for i in range(20):
        q.enqueue("market_radar", "radar.scan", {}, idempotency_key=f"g{i}")
    q.enqueue("market_radar", "mjs.scan", {}, idempotency_key="m0")
    record = orc.allocate(db)
    lane = record["lanes"]["market_radar"]
    res = lane["mjs_reserve"]
    assert res["reserve_floor"] == capacity.MJS_RESERVED_SPECIALISTS
    assert res["mission_open"] == 1 and res["generic_open"] == 20
    assert res["mission_specialists"] >= capacity.MJS_RESERVED_SPECIALISTS
    assert lane["granted"] == res["total"]
    with db.session() as s:
        row = s.get(SwarmAllocation, record["allocation_id"])
        assert row.detail["mjs_reserve"]["reserve_floor"] == capacity.MJS_RESERVED_SPECIALISTS


def test_generic_research_cannot_draw_below_the_floor_when_money_is_short():
    res = capacity.reserve_lane(mission_open=2, generic_open=40, granted=1, affordable=4,
                                work_per_specialist=orc.WORK_PER_SPECIALIST)
    assert res["total"] == 4 and res["mission_specialists"] == 3
    assert res["generic_granted"] == 1 and res["generic_refused"]
    assert "catalogue_coverage" in res["would_starve"]
    # With no mission work waiting the floor is held idle, not enforced against generic work.
    idle = capacity.reserve_lane(mission_open=0, generic_open=40, granted=1, affordable=4,
                                 work_per_specialist=orc.WORK_PER_SPECIALIST)
    assert idle["reserve_binding"] is False and idle["generic_granted"] == 4
    assert not idle["generic_refused"]


# ---- #311 the seasonal deadline sentinel -------------------------------------------------


def test_sentinel_escalates_an_at_risk_mjs_opportunity_and_reallocates_its_work():
    db = _db()
    ev = _mission(db)
    target = ev.steps["response"]["seasonal_target"]
    preferred = date.fromisoformat(target["preferred_launch"])
    latest = date.fromisoformat(target["latest_effective_launch"])
    at_risk = max(preferred + timedelta(days=1), latest - timedelta(days=10))
    assert preferred < at_risk <= latest
    with db.session() as s:
        before = s.get(Job, ev.tournament_job_id).priority
    out = _run(db, "mjs.seasonal_sentinel", {"as_of": at_risk.isoformat()})
    assert out["counts"]["at_risk"] == 1 and out["incidents_opened"]
    assert out["reallocated"] == 1
    with db.session() as s:
        after = s.get(Job, ev.tournament_job_id).priority
        assert after == orc.priority_for("mjs.seasonal_sentinel") < before
        inc = s.scalar(select(Incident).where(Incident.signature.like("mjs.seasonal_at_risk:%")))
        assert inc.severity == "P2" and not inc.resolved


def test_sentinel_defers_a_missed_window_without_an_incident():
    db = _db()
    ev = _mission(db)
    latest = date.fromisoformat(ev.steps["response"]["seasonal_target"]
                                ["latest_effective_launch"])
    out = _run(db, "mjs.seasonal_sentinel",
               {"as_of": (latest + timedelta(days=2)).isoformat()})
    assert out["counts"]["missed"] == 1 and not out["incidents_opened"]
    with db.session() as s:
        row = s.get(MjsMissionEvent, ev.id)
        assert row.seasonal["deferred_from"]["event"] == "Christmas"
        assert row.seasonal["target"]["event"] != "Christmas"


# ---- #228 the owner's veto, through the route --------------------------------------------


def test_the_veto_route_records_counts_and_feeds_lessons():
    token = "cert-mjs-operator-token-0123456789"
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/app.sqlite"
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = token
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    with TestClient(main.app) as c:
        db = main.db
        Registry(db).seed_defaults()
        benchmarks.seed(db)
        with db.session() as s:
            agent = s.scalar(select(Agent).where(Agent.name == "market_radar"))
            agent.allowed_job_types = list(agent.allowed_job_types or []) + list(NEW_TYPES)
        ev = _mission(db)
        auth = {"authorization": f"Bearer {token}"}
        body = {"subject_ref": f"mjs_event:{ev.id}", "scope": "flagship_creative_quality",
                "reason": "generic"}

        assert c.post("/api/mjs/veto", json=body).status_code == 401
        bad = c.post("/api/mjs/veto", json={**body, "reason": "i just did not like it"},
                     headers=auth)
        assert bad.status_code == 400
        late = c.post("/api/mjs/veto", json={**body, "predicted_veto": True,
                                             "predicted_at": "2999-01-01T00:00:00+00:00"},
                      headers=auth)
        assert late.status_code == 400, "a prediction dated after the ruling was accepted"

        first = c.post("/api/mjs/veto", json=body, headers=auth).json()
        assert first["recorded"] and first["pod_lessons_contradicted"]
        assert first["alignment"]["state"] == "held_by_owner"
        for _ in range(2):
            last = c.post("/api/mjs/veto", json={**body, "subject_ref": "flagship:x"},
                          headers=auth).json()
        assert last["memory"]["findings"][0]["reason"] == "generic"
        assert last["lessons_published"]
        with db.session() as s:
            assert s.scalar(select(Lesson).where(
                Lesson.evidence_ref == "owner_veto_finding:generic")) is not None
            lesson = s.get(PodLesson, first["pod_lessons_contradicted"][0]["lesson_id"])
            assert any(e["kind"] == "owner_veto" for e in lesson.contradicted_by)


def test_every_new_job_type_has_a_decided_band():
    for t in NEW_TYPES:
        assert orc.band_for(t)["mapped"], t
    assert orc.priority_for("mjs.seasonal_sentinel") == orc.priority_for("seasonal.sentinel")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
