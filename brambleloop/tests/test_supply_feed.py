"""ENG-SUPPLY-FEED: READY pool concepts reach engineering from scan evidence, unaided.

Production readback (94daf054, 13:50Z): factory_visibility.supply pool_total 142 (ready 32,
held 95, refused 15, admitted 0); one product in flight; WIP 4, 4 open slots, 0 offers
waiting; 0 certified in 24 h. Nothing fed engineering.

`concept_pool.admit_ready` admits a READY concept only when its pod has an answered research
task behind a validated watchlist gap, and the allowance has units. The suites before this
one built that research by hand (`test_concepts100._answered_task`: a fixture task and a
hand-made gap), so they never exercised the real link from the nine-shop scans.

The real link is `intel.watchlist.record_comparison`: a validated arena becomes a watchlist
coverage gap, its research question is opened and `watchlist_research.answer` answers it from
the recorded comparisons. `compare` dropped every pod we already sell in (`_our_pods`), so a
pod with an existing product never got a gap or a question, and its READY concepts waited
forever. Production has 16 products; the READY concepts the pool ranks first (cushions,
wall panels, baskets, totes) are in exactly those pods.

This suite builds that state on a scratch SQLite file, with no hand-made research:

* nine-shop watchlist scans (fixture listing rows, real shop read state), read on three
  earlier days by the real daily comparison, so the arenas are durable;
* 16 existing certified products in home decor, blankets and bags, whose listing work is held
  behind the open publishing halt (the real `incident_lifecycle.escalate_systemic`);
* Launch-0 exhausted, paid vision open with a FIXTURE vision judge.

Only cadence jobs are enqueued (`intel.watchlist_compare`, `radar.concept_pool`,
`radar.concept_intake`, `mjs.seasonal_sentinel`, `supply.admit`); the real worker drains
whatever they cause.

Every listing, shop observation, judgement and product here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_supply_feed.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

import test_concepts100 as C100  # noqa: E402 - the scratch database
import test_new_product_flow as NPF  # noqa: E402 - Launch-0 exhaustion, vision, fixture judge
import test_supply_lane as LANE  # noqa: E402 - the staleness halt and the drain

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, CoverageGap, Job, JobStatus, Product,
)
from brambleloop.intel import research  # noqa: E402
from brambleloop.intel import watchlist as W  # noqa: E402
from brambleloop.intel.pods import route  # noqa: E402
from brambleloop.ops import production_evidence as pe  # noqa: E402
from brambleloop.products import supply  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import concept_pool as P  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
HISTORY_DAYS = 3
CADENCE_JOBS = (("market_radar", "intel.watchlist_compare"),) + LANE.CADENCE_JOBS
CYCLES = 4
MAX_JOBS_PER_CYCLE = 400

# Fixture listing nouns (what a shop sells) and fixture-only design names. No real listing.
NOUNS = ("Bunny Amigurumi", "Stuffed Fox", "Plush Whale", "Baby Blanket", "Baby Cardigan",
         "Cushion Cover", "Lumbar Pillow", "Storage Basket", "Tapestry Basket", "Tote Bag",
         "Wall Hanging", "Table Runner", "Coaster", "Dishcloth", "Throw Blanket",
         "Mosaic Blanket", "Granny Throw", "Beanie", "Shawl", "Sweater", "Cardigan",
         "Ornament", "Christmas Stocking", "Placemat")
SECRET = ("Zephyrine", "Quorra", "Velloria", "Marrowind", "Thistlegarde", "Ombrevale",
          "Fennimore", "Brisquel", "Cantorell")
# Production's existing products sit in these pods (titles are fixtures).
EXISTING_TITLES = ("Striped Cushion Cover", "Sofa Throw Blanket", "Placemat Pair",
                   "Granny Square Blanket", "Market Tote", "Banded Storage Basket")
COVERED = {"home_decor", "blankets", "bags"}


def _shops():
    return [m for m in W.WATCHLIST if m.role != W.ANCHOR]


def _scan(db) -> None:
    n = 7000
    with db.session() as s:
        for i, m in enumerate(_shops()):
            for noun in NOUNS:
                for k in range(3):
                    n += 1
                    t = f"Vintage {SECRET[(i + k) % len(SECRET)]} {noun} Pattern {k}"
                    s.add(BenchmarkListing(benchmark_key=m.key, listing_ref=f"fx-{n}",
                                           title=t, pod=route(t), price_cad=6.0 + n % 5,
                                           last_seen=NOW, first_seen=NOW - timedelta(days=9),
                                           detail={"num_favorers": n % 40}))


def _read_shops(db, at: datetime) -> None:
    """What a successful watchlist scan of every shop records (`scan_member`'s state)."""
    for m in _shops():
        W._save_state(db, m.key, {"state": "ok", "last_ok_at": at.isoformat()}, now=at)


def _history(db) -> None:
    """The earlier daily comparisons, by the real function the cadence job runs."""
    for d in range(HISTORY_DAYS, 0, -1):
        at = NOW - timedelta(days=d)
        _read_shops(db, at)
        W.record_comparison(db, now=at)
    _read_shops(db, NOW - timedelta(hours=1))      # today's scan; the compare job reads it


def _production_state():
    db = C100._db()
    NPF._exhaust_launch0(db)
    ev = LANE._open_staleness_halt(db, LANE._existing_slugs(), stale=LANE.STALE)
    with db.session() as s:
        for i, p in enumerate(s.scalars(select(Product).order_by(Product.slug))):
            p.title = EXISTING_TITLES[i % len(EXISTING_TITLES)]
    _scan(db)
    _history(db)
    NPF._open_vision(db)
    return db, ev


def _drain(db, *, cycles: int = CYCLES) -> None:
    for c in range(cycles):
        q = JobQueue(db)
        for agent, job_type in CADENCE_JOBS:
            q.enqueue(agent, job_type, {"cadence": f"fixture-{c}"},
                      idempotency_key=f"fixture-cadence:{job_type}:{c}", priority=0)
        w = Worker(db, f"feed-{c}")
        for _ in range(MAX_JOBS_PER_CYCLE):
            if not w.run_once():
                break


def _rows(db, action):
    return LANE._rows(db, action)


def _drafts(db) -> dict[str, Job]:
    with db.session() as s:
        out = {j.idempotency_key.split(":", 1)[1]: j for j in s.scalars(
            select(Job).where(Job.job_type == "cir.draft",
                              Job.idempotency_key.like("draft:pool-%")))}
        s.expunge_all()
        return out


def _admitted_pool(db) -> list[P.ConceptPoolEntry]:
    return [r for r in C100._pool(db) if r.state == P.ADMITTED]


# ---- the production state -------------------------------------------------------------------

def test_the_state_is_productions_and_research_is_never_hand_made():
    db, ev = _production_state()
    assert ev["systemic"] and LANE._systemic_open(db), ev
    assert W._our_pods(db) == COVERED, W._our_pods(db)
    with db.session() as s:
        assert len(list(s.scalars(select(Product.id)))) == LANE.EXISTING
        tasks = list(s.scalars(select(research.ResearchTask)))
        gaps = list(s.scalars(select(CoverageGap)))
    # every research task was opened by the watchlist comparison for a watchlist gap
    assert tasks and all(t.trigger.startswith("watchlist_gap:") for t in tasks), \
        [t.trigger for t in tasks]
    assert gaps and all(g.benchmark_key == W.WATCHLIST_KEY for g in gaps)
    # covered arenas are linked, and never left reading as an open opportunity
    covered = {g.pod: g for g in gaps if (g.evidence or {}).get("covered_by_us")}
    assert set(covered) == COVERED, sorted(covered)
    assert all(g.state == "concepting" for g in covered.values()), \
        {p: g.state for p, g in covered.items()}
    assert not {g["pod"] for g in W._open_gaps(db)} & COVERED
    # the 24-hour market_radar answer from yesterday's comparison is (nearly) spent: today's
    # comparison must answer again, so nothing is admitted on yesterday's evidence
    P.replenish(db, now=NOW, unit_cad=0.12, admit=False)
    st = P.research_status(db, "home_decor", today=NOW.date(), now=NOW)
    assert st["status"] == P.RESEARCH_UNANSWERED and st["why"] == "evidence_expiring", st
    rows = C100._pool(db)
    ready = Counter(r.pod for r in rows if r.state == P.READY)
    assert sum(ready.values()) >= 20 and set(ready) & COVERED, ready


# ---- the fix, end to end --------------------------------------------------------------------

def test_scan_evidence_feeds_engineering_unaided_with_the_halt_open():
    db, _ev = _production_state()
    judge, restore = LANE._with_judge()
    try:
        _drain(db)
    finally:
        restore()
    drafts = _drafts(db)
    pool = {r.slug: r for r in _admitted_pool(db)}
    offered = {a for a, _d in _rows(db, supply.OFFERED)}
    admitted = {a for a, _d in _rows(db, supply.ADMITTED)}
    traced = []
    for slug, job in drafts.items():
        row = pool.get(slug)
        if row is None:
            continue
        # scan evidence: the pool entry cites stored listing rows of watchlist shops
        refs = [e["ref"] for e in row.evidence["refs"]]
        assert refs and all(r.startswith("benchmark_listing:") for r in refs), (slug, refs)
        # READY -> admitted onto the research the comparison answered for a watchlist gap
        with db.session() as s:
            t = s.get(research.ResearchTask, int(row.research_task_id))
            gap = s.get(CoverageGap, int(t.trigger.split(":", 1)[1].split("#", 1)[0]))
            assert t.trigger.startswith("watchlist_gap:") and t.domain == "market_radar"
            assert gap.benchmark_key == W.WATCHLIST_KEY and gap.pod == row.pod
            assert len((gap.evidence or {}).get("corroborated_by") or []) >= 2
            assert any(f.get("claim_class") == "fact" for f in t.findings or [])
            ok = s.scalar(select(intake.RadarConcept).where(
                intake.RadarConcept.slug == slug,
                intake.RadarConcept.state.in_((intake.APPROVED, "handed_off", "consumed"))))
            score = s.scalar(select(Job).where(Job.job_type == "radar.score",
                                               Job.idempotency_key.like(f"score:{slug}:%")))
        # -> intake approved -> score -> supply offer -> supply.admit -> cir.draft
        assert score is not None and score.status == JobStatus.DONE, slug
        assert slug in offered and slug in admitted, (slug, "not through the one door")
        assert job.status in (JobStatus.DONE, JobStatus.RUNNING, JobStatus.PENDING,
                              JobStatus.FAILED), job.status
        traced.append((slug, row.lane, row.pod, ok is not None))
    assert len(traced) >= 4, (traced, sorted(drafts), sorted(pool))
    lanes = {lane for _s, lane, _p, _ok in traced}
    pods = {pod for _s, _l, pod, _ok in traced}
    # core families: pillows (an arena we already sell in) and clothing reach engineering
    assert lanes & {"cushion"}, lanes
    assert lanes & {"shawl", "beanie", "scarf"}, lanes
    assert pods & COVERED, pods            # the defect: covered pods never fed engineering
    # nothing was published, the halt is still open, the existing listing work still held
    assert LANE._systemic_open(db)
    with db.session() as s:
        assert not list(s.scalars(select(Job).where(Job.job_type == "store.publish",
                                                    Job.status == JobStatus.DONE)))
    # no competitor word reached a concept or a proposal
    text = json.dumps([[r.title, r.concept, r.brief] for r in C100._pool(db)]).lower()
    assert not [w for w in SECRET if w.lower() in text]
    # the readback says what happened, in its own vocabulary
    v = pe.factory_visibility(db, now=datetime.now(timezone.utc))["supply"]
    assert v["last_admit"]["admitted"] >= 0 and v["allowance"]["why"] in P.ALLOWANCE_BINDINGS
    assert v["pool_by_state"][P.ADMITTED] >= 4, v["pool_by_state"]
    print("    traced to cir.draft:", sorted((lane, pod) for _s, lane, pod, _o in traced))


def test_mutation_covered_pods_unlinked_admit_nothing_there():
    """The defect restored: the comparison links no covered arena (`link_demand` -> []).
    READY concepts in the pods we sell in are never admitted, and the readback says why."""
    orig = W.link_demand
    W.link_demand = lambda rep: []
    try:
        db, _ev = _production_state()
        judge, restore = LANE._with_judge()
        try:
            _drain(db, cycles=2)
        finally:
            restore()
    finally:
        W.link_demand = orig
    admitted = Counter(r.pod for r in _admitted_pool(db))
    assert not set(admitted) & COVERED, admitted
    assert not {s for s in _drafts(db) if s.startswith(("pool-cushion-", "pool-wall-panel-",
                                                         "pool-basket-", "pool-tote-"))}
    v = pe.factory_visibility(db, now=datetime.now(timezone.utc))["supply"]
    for pod in COVERED & set(v["ready_by_pod"]):
        assert v["ready_by_pod"][pod]["research"] == P.RESEARCH_ABSENT, v["ready_by_pod"]
        assert v["ready_by_pod"][pod]["why"] == "no_watchlist_gap", v["ready_by_pod"]
    assert v["ready_by_research"][P.RESEARCH_ABSENT] > 0, v


def test_no_corroboration_no_research_and_nothing_admitted():
    """Honesty: with stale shop reads the comparison corroborates nothing, so no research is
    answered and nothing is admitted. Research is never fabricated to fill the pool."""
    db = C100._db()
    _scan(db)
    for d in range(HISTORY_DAYS, -1, -1):
        at = NOW - timedelta(days=d)
        _read_shops(db, at - timedelta(days=5))          # every read older than 48 h
        W.record_comparison(db, now=at)
    out = P.replenish(db, now=NOW, unit_cad=0.12)
    assert out["admitted"] == [], out["admitted"]
    res = out["result"]
    assert res["ready"] > 0 and res["waiting_on_research"] == res["ready"], res
    assert {e["research"] for e in res["ready_by_pod"].values()} <= {
        P.RESEARCH_ABSENT, P.RESEARCH_UNANSWERED}, res["ready_by_pod"]
    with db.session() as s:
        assert not list(s.scalars(select(research.ResearchTask).where(
            research.ResearchTask.state == research.ANSWERED)))


def test_a_stopped_arena_is_not_researched_for_the_pool():
    db, _ev = _production_state()
    with db.session() as s:
        for g in s.scalars(select(CoverageGap).where(CoverageGap.pod == "hats")):
            g.state = "not_pursuing"
    st = P.research_status(db, "hats", today=NOW.date(), now=NOW)
    assert st == {"status": P.RESEARCH_ABSENT, "why": "gap_not_pursuing"}, st


def test_the_allowance_still_bounds_admission_and_the_cap_is_unchanged():
    from brambleloop.finance import spend_policy

    assert spend_policy.ceiling_cad() == 100.0
    db, _ev = _production_state()
    W.record_comparison(db, now=NOW)
    out = P.replenish(db, now=NOW, unit_cad=0.12)
    assert len(out["admitted"]) == P.ADMIT_PER_RUN, out["admitted"]
    assert out["result"]["allowance"] == {"units": P.ADMIT_PER_RUN, "unit_cad": 0.12,
                                          "why": "per_run"}, out["result"]
    assert out["result"]["capped_by_allowance"] > 0
    # an unknown unit cost admits nothing (fail closed), and says so
    db2, _ev = _production_state()
    W.record_comparison(db2, now=NOW)
    orig = P.unit_cost_cad
    P.unit_cost_cad = lambda: None
    try:
        out2 = P.replenish(db2, now=NOW)
    finally:
        P.unit_cost_cad = orig
    assert out2["admitted"] == [] and out2["result"]["allowance"]["why"] == "unit_cost_unknown"


def test_factory_visibility_supply_feed_fields_use_fixed_vocabulary_only():
    db, _ev = _production_state()
    v0 = pe.factory_visibility(db, now=NOW)["supply"]
    assert v0["allowance"] is None and v0["last_admit"] is None       # UNKNOWN, never 0
    W.record_comparison(db, now=NOW)
    P.replenish(db, now=NOW, unit_cad=0.12)
    v = pe.factory_visibility(db, now=NOW)["supply"]
    assert set(v["allowance"]) == {"units", "unit_cad", "why"}, v["allowance"]
    assert v["allowance"]["why"] in P.ALLOWANCE_BINDINGS
    from brambleloop.intel.pods import POD_KEYS

    assert v["ready_by_pod"] and set(v["ready_by_pod"]) <= set(POD_KEYS) | {"unrecognised"}
    for e in v["ready_by_pod"].values():
        assert set(e) == {"ready", "research", "why"}, e
        assert e["research"] in P.RESEARCH_STATUSES + ("unknown",), e
        assert e["why"] in P.RESEARCH_WHY + ("unknown",), e
    assert set(v["ready_by_research"]) == set(P.RESEARCH_STATUSES) | {"unknown"}
    assert set(v["last_admit"]) == {"ready", "admitted", "waiting_on_research",
                                    "capped_by_allowance", "at"}, v["last_admit"]
    assert v["last_admit"]["admitted"] == P.ADMIT_PER_RUN
    assert sum(e["ready"] for e in v["ready_by_pod"].values()) == v["pool_by_state"][P.READY]
    text = json.dumps(v)
    assert "pool-" not in text and "existing-" not in text, text
    assert not [w for w in SECRET if w.lower() in text.lower()]


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failed = 0
    assert TESTS
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {str(exc)[:1500]}")
            traceback.print_exc(limit=4)
    print(f"{len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
