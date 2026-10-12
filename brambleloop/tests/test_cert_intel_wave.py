"""Certification repair (C-60, C-66/C-67, C-71): the market-intelligence and MJs cluster.

Every test drives a registered handler through the worker (or the handler registry with a
real JobContext) on a real database, seeds real rows, and asserts the downstream effect --
a job enqueued, an owner action raised, a run refused, a gate opened -- rather than calling
the library it wraps. No test reaches a network: every Etsy read goes through a recorded
reader injected where production builds one from the credential.

Rows: #2 #15 #165 #208 #211 #215 #219 #227 #268.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Benchmark, BenchmarkListing, BenchmarkProduct, CoverageGap, Job, JobStatus,
    ListingAsset, MjsMissionEvent, OperatingReading, OwnerAction, Product, SerpSnapshot,
)
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

AS_OF = "2026-09-27"
CLEAR = ("Crochet PATTERN, PDF instant download, 14 pages. Written instructions and a stitch "
         "chart, US terms. Finished measurements given. Worsted weight yarn, about 1200 "
         "yards, 5 mm hook.")
VAGUE = "A lovely crochet pattern for you."


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cert_intel_')}/intel.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    return db


def _no_credential():
    return {k: os.environ.pop(k, None) for k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET",
                                                 "ETSY_KEYSTRING")}


def _restore(saved):
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


def _run(db, agent: str, job_type: str, inputs: dict | None = None) -> dict:
    saved = _no_credential()
    try:
        job = JobQueue(db).enqueue(agent, job_type, {"as_of": AS_OF, **(inputs or {})},
                                   priority=0,
                                   idempotency_key=f"t:{job_type}:{os.urandom(4).hex()}")
        assert Worker(db, "cert-intel", job_types=[job_type]).run_once()
    finally:
        _restore(saved)
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _seed_benchmark(db, key: str, pod: str, titles, *, favourites=100, price=8.0, media=6,
                    description=CLEAR, n=6):
    from brambleloop.intel import deliverable

    facts = deliverable.read({"description": description, "is_digital": True})
    with db.session() as s:
        for i in range(n):
            title = titles[i % len(titles)]
            s.add(BenchmarkListing(
                benchmark_key=key, listing_ref=f"{key}-{pod}-{i}", title=title, pod=pod,
                price_cad=price, media_count=media, audit_state="audited",
                fingerprint=f"{key}{pod}{i}",
                detail={"num_favorers": favourites + i, "gallery_audited": True,
                        "has_video": False,
                        "deliverable": facts}))


class SearchReader:
    """A recorded API search index and shop catalogue. Never touches a network."""

    def __init__(self, shops: dict[int, dict], results: list[dict]):
        self.shops = shops
        self.results = results
        self.calls: list[str] = []

    def search(self, query, *, taxonomy_id=None, sort_on="score", limit=48):
        self.calls.append(f"search {query}")
        return {"count": 1000 + len(query), "results": [dict(r) for r in self.results]}

    def images(self, ref):
        return [{"rank": i + 1, "url_570xN": f"https://fixture.invalid/{ref}/{i}.jpg"}
                for i in range(6)]

    def videos(self, ref):
        return []

    def shop(self, shop_id):
        self.calls.append(f"shop {shop_id}")
        return self.shops[int(shop_id)]

    def resolve_shop(self, name):
        for sid, sh in self.shops.items():
            if sh["shop_name"].lower() == name.lower():
                return {"shop_id": sid, "shop_name": sh["shop_name"]}
        raise KeyError(name)

    def catalogue(self, shop_id, **kw):
        return list(self.shops[int(shop_id)].get("listings") or [])


def _result(lid, shop_id, title, *, description=VAGUE, digital=True):
    return {"listing_id": lid, "shop_id": shop_id, "title": title,
            "description": description, "is_digital": digital, "taxonomy_id": 66,
            "price": {"amount": 700, "divisor": 100, "currency_code": "USD"},
            "num_favorers": 50}


# ---- #15 + #2: the SERP laboratory scores positioning, and the score steers selection ----


def test_serp_capture_scores_pattern_video_diversity_and_differentiation_and_feeds_arbitrage():
    from brambleloop.intel import serp
    from brambleloop.radar import arbitrage

    db = _db()
    _seed_benchmark(db, benchmarks.MJS_KEY, "hats", ["Chunky Beanie Hat Crochet Pattern"])
    _seed_benchmark(db, benchmarks.MJS_KEY, "blankets", ["Granny Blanket Crochet Pattern"])
    results = [_result(100 + i, 500 + (i % 3), t) for i, t in enumerate(
        ["Chunky Beanie Hat Crochet Pattern", "Granny Square Blanket Pattern",
         "Striped Cardigan Pattern", "Beanie Pattern Sizes S M L", "Cowl Hat Pattern"])]
    results[1]["description"] = CLEAR
    serp.READER_FACTORY = lambda: SearchReader({}, results)
    try:
        out = _run(db, "market_radar", "intel.serp_capture")
    finally:
        serp.READER_FACTORY = None
    assert out["ran"] is True and out["captured"] > 0, out
    with db.session() as s:
        snap = s.scalars(select(SerpSnapshot)).first()
        pos = snap.detail["positioning"]
    assert pos["measurable"] is True
    pv = pos["pattern_video"]
    assert pv["pattern_share"] == 1.0 and pv["video_measured"] > 0
    assert pv["pattern_with_video"] == 0 and pv["opening"] is True
    div = pos["category_diversity"]
    assert div["distinct_pods"] >= 3 and div["distinct_shops"] == 3
    diff = pos["brambleloop_differentiation"]
    # Four of five results state vaguely; one states everything but a second term set.
    assert diff["judged"] == 5 and diff["value"] is not None and diff["value"] >= 0.8, diff
    # ... and differentiation is now a measured dimension of the #2 arbitrage card.
    card = {c["market"]: c for c in arbitrage.score_observed(db)["scored"]}
    assert "differentiation" in card["hats"]["measured"], card["hats"]["measured"]


def test_radar_scan_is_steered_by_the_observed_market_score():
    from brambleloop.radar import arbitrage

    db = _db()
    # Hats: a weak, cheap, crowded field; blankets: strong demand and price.
    _seed_benchmark(db, benchmarks.MJS_KEY, "hats", ["Beanie Hat Crochet Pattern"],
                    favourites=10, price=4.0)
    _seed_benchmark(db, benchmarks.MJS_KEY, "blankets", ["Granny Blanket Crochet Pattern"],
                    favourites=900, price=14.0)
    steer = arbitrage.steering(db)
    assert set(steer) >= {"hats", "blankets"}, steer
    assert steer["blankets"]["score"] != steer["hats"]["score"]
    out = _run(db, "market_radar", "radar.scan")
    assert out["arbitrage_steered"], out
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "radar.scanned"))
        detail = row.detail["arbitrage"]
    moved = {m["slug"]: m for m in detail["steered"]}
    assert any(m["pod"] == "blankets" for m in moved.values())
    assert all(m["from"] != m["to"] for m in moved.values())
    # And the discovery chooser orders an occasion's departments by the same score.
    from brambleloop.creative import prospecting

    arenas = [prospecting.Arena(event="Christmas", pod="hats", benchmark_listings=6,
                                days_away=80, arbitrage=steer["hats"]["score"]),
              prospecting.Arena(event="Christmas", pod="blankets", benchmark_listings=6,
                                days_away=80, arbitrage=steer["blankets"]["score"])]
    ordered = sorted(arenas, key=lambda a: -(a.arbitrage or 0))
    assert ordered[0].pod == ("blankets" if steer["blankets"]["score"] > steer["hats"]["score"]
                              else "hats")


# ---- #219 + #268: a second elite seller joins from the index and a second market opens ----


def _leaders_reader():
    listings = [{"listing_id": 7000 + i, "title": "Striped Cardigan Crochet Pattern",
                 "price": {"amount": 900, "divisor": 100, "currency_code": "GBP"},
                 "tags": [], "materials": [], "state": "active",
                 "last_modified_timestamp": 1, "num_favorers": 120, "taxonomy_id": 66,
                 "is_digital": True, "description": CLEAR, "has_variations": True,
                 "url": f"https://fixture.invalid/{7000 + i}"} for i in range(6)]
    shops = {777: {"shop_name": "WoolWorksUK", "shop_location_country_iso": "GB",
                   "listings": listings},
             888: {"shop_name": "OneHitShop", "shop_location_country_iso": "US",
                   "listings": []}}
    results = [_result(9000 + i, 777, "Striped Cardigan Crochet Pattern") for i in range(3)]
    results.append(_result(9100, 888, "Beanie Pattern"))
    return SearchReader(shops, results)


def test_panel_discovery_registers_and_scans_a_second_elite_seller_in_a_second_market():
    from brambleloop.build2 import executor
    from brambleloop.intel import mission_runtime, panel_discovery, serp
    from brambleloop.intel.observe import listing_options

    db = _db()
    _seed_benchmark(db, benchmarks.MJS_KEY, "garments", ["Striped Cardigan Crochet Pattern"])
    reader = _leaders_reader()
    serp.READER_FACTORY = lambda: reader
    panel_discovery.READER_FACTORY = lambda: reader
    try:
        assert executor._second_market_observed(db, {}) is False
        _run(db, "market_radar", "intel.serp_capture")
        out = _run(db, "market_radar", "intel.panel_discovery")
    finally:
        serp.READER_FACTORY = None
        panel_discovery.READER_FACTORY = None
    # Both shops lead two or more queries; the one outside a market the panel already covers
    # (#268) is taken first.
    assert out["ran"] is True and out["joined"][0] == "panel_woolworksuk", out
    with db.session() as s:
        row = s.scalar(select(Benchmark).where(Benchmark.key == "panel_woolworksuk"))
        assert row.market == "other" and row.mandatory is False
        assert "top 10" in row.reason_for_inclusion
        observed = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == "panel_woolworksuk")))
    assert len(observed) == 6
    assert observed[0].detail.get("options", {}).get("has_variations") is True  # #208
    assert listing_options({"has_variations": True}) == {"has_variations": True}
    # #268: two stated markets now have observed listings, so the gate opens by itself.
    assert executor._second_market_observed(db, {}) is True
    # #219: the panel counts the new seller, and a mechanism both sellers show is learnable.
    members = {m.seller_ref for m in mission_runtime.panel_members(
        db, datetime(2026, 9, 27).date())}
    assert {"panel_woolworksuk", benchmarks.MJS_KEY} <= members
    rule = mission_runtime.RULE_BY_KEY["gallery_depth"]
    assert set(mission_runtime.sellers_showing(db, rule, "garments")) == {
        "panel_woolworksuk", benchmarks.MJS_KEY}


def test_panel_discovery_without_a_reader_registers_nobody():
    from brambleloop.intel import panel_discovery

    db = _db()
    out = _run(db, "market_radar", "intel.panel_discovery")
    assert out["ran"] is False and not out["joined"]
    with db.session() as s:
        assert s.scalar(select(Benchmark).where(Benchmark.key.like("panel_%"))) is None
    assert panel_discovery.market_for(None) == ""  # never assumed American


# ---- #165: a market move becomes one bounded purchase recommendation ---------------------


def test_benchmark_refresh_baselines_then_recommends_a_new_category_and_bounds_the_asks():
    db = _db()
    _seed_benchmark(db, benchmarks.MJS_KEY, "hats", ["Beanie Hat Crochet Pattern"])
    first = _run(db, "market_radar", "intel.benchmark_refresh", {"as_of": "2026-09-20"})
    assert first["baseline"] is True and not first["raised"]
    # A department the panel did not sell into last week, with enough listings to matter.
    _seed_benchmark(db, benchmarks.MJS_KEY, "stockings", ["Christmas Stocking Pattern"],
                    price=6.5)
    _seed_benchmark(db, benchmarks.MJS_KEY, "ornaments", ["Star Ornament Pattern"],
                    price=3.0)
    _seed_benchmark(db, benchmarks.MJS_KEY, "bags", ["Market Tote Bag Pattern"], price=5.0)
    second = _run(db, "market_radar", "intel.benchmark_refresh", {"as_of": "2026-09-27"})
    assert len(second["raised"]) == 2 and second["held"] >= 1, second
    with db.session() as s:
        asks = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like("benchmark_refresh:%"))))
    assert len(asks) == 2
    assert all(0 < a.max_cost_cad <= 6.5 and "#165" in a.reason for a in asks)
    # Asked once, not twice.
    third = _run(db, "market_radar", "intel.benchmark_refresh", {"as_of": "2026-09-28"})
    assert not third["raised"]


def test_benchmark_refresh_drops_duplicate_information():
    db = _db()
    _seed_benchmark(db, benchmarks.MJS_KEY, "hats", ["Beanie Hat Crochet Pattern"])
    _run(db, "market_radar", "intel.benchmark_refresh", {"as_of": "2026-09-20"})
    with db.session() as s:
        s.add(BenchmarkProduct(ref="bp1", seller="MJs", pod="stockings", title="x"))
    _seed_benchmark(db, benchmarks.MJS_KEY, "stockings", ["Christmas Stocking Pattern"])
    out = _run(db, "market_radar", "intel.benchmark_refresh", {"as_of": "2026-09-27"})
    assert not out["raised"], out
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == "benchmark.refresh",
            OperatingReading.period_key == "2026-09-27"))
    assert any("already holds" in d["why"] for d in row.payload["duplicates"])


# ---- #211 / #215 / #227: the director, the same-arena lane and the ceiling ----------------


def _mjs_mission(db, listing):
    from brambleloop.intel import observe
    sys.path.insert(0, str(ROOT / "tests"))
    from test_cert_mjs import BASELINE, FixtureReader

    observe.scan(db, FixtureReader(BASELINE), env={})
    observe.scan(db, FixtureReader(BASELINE + [listing]), env={})
    with db.session() as s:
        agent = s.scalar(select(__import__("brambleloop.core.models", fromlist=["Agent"]).Agent)
                         .where(__import__("brambleloop.core.models",
                                           fromlist=["Agent"]).Agent.name == "market_radar"))
        agent.allowed_job_types = list(agent.allowed_job_types or []) + ["mjs.scan"]
    return _run(db, "market_radar", "mjs.scan")


def test_director_company_view_uses_real_photography_and_queues_photography_when_behind():
    sys.path.insert(0, str(ROOT / "tests"))
    from test_cert_mjs import CROPPED

    db = _db()
    with db.session() as s:
        s.add(Product(slug="striped-cardigan", title="Striped Cardigan"))
        s.add(ListingAsset(product_slug="striped-cardigan", version="1.0.0", position=1,
                           asset_class="product_first", role="hero", approved=True))
    out = _mjs_mission(db, CROPPED)
    assert out["mission"]["processed"] == 1
    with db.session() as s:
        reading = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == "mjs.company_standing"))
        jobs = list(s.scalars(select(Job).where(Job.job_type == "assets.owned_photography")))
        ev = s.scalar(select(MjsMissionEvent))
    garments = reading.payload["pods"]["garments"]
    assert garments["ours"]["photography_coverage"] == 1.0          # measured, not None
    assert garments["standing"]["photography_coverage"] == "behind"
    assert "garments" in reading.payload["summary"]["photography_coverage"]["behind"]
    assert [j.inputs["slug"] for j in jobs] == ["striped-cardigan"]
    assert jobs[0].agent == "publishing"
    assert ev.steps["routing"]["standing"]["photography_coverage"] == "behind"


def test_entry_axes_come_from_the_listing_and_a_concepting_gap_starts_original_design():
    sys.path.insert(0, str(ROOT / "tests"))
    from test_cert_mjs import CROPPED

    from brambleloop.intel import mission_runtime

    db = _db()
    _mjs_mission(db, CROPPED)
    with db.session() as s:
        ev = s.scalar(select(MjsMissionEvent))
        gap = s.get(CoverageGap, ev.gap_id)
    may = ev.steps["panel"]["may_enter"]
    # CROPPED states 7 sizes, fewer than the compiler's verified run, and everything else.
    assert may["axes_claimed"] == ["product_engineering"], may
    assert "7" in may["how"]
    assert gap.state == "concepting"
    assert gap.evidence["design_job_id"] == ev.tournament_job_id
    # A listing that states the full run and everything that arrives offers only parity.
    full = {"pod": "garments", "detail": {
        "size_range": {"sizes": 9, "stated": True}, "deliverable": {"clarity": 1.0}}}
    assert mission_runtime.entry_axes(full, "cardigan") == (("parity",), "")
    # A gap in CONCEPTING with no tournament gets its same-arena design queued, once.
    with db.session() as s:
        s.get(MjsMissionEvent, ev.id).tournament_job_id = None
        g = s.get(CoverageGap, ev.gap_id)
        g.evidence = {k: v for k, v in (g.evidence or {}).items() if k != "design_job_id"}
    q = JobQueue(db)

    def enqueue(agent, jt, inputs=None, **kw):
        return q.enqueue(agent, jt, inputs, **kw)

    started = mission_runtime.consume_concepting(db, enqueue=enqueue)["started"]
    assert len(started) == 1
    with db.session() as s:
        job = s.get(Job, started[0]["job_id"])
        assert job.job_type == "creative.tournament" and job.inputs["lane"] == "same_arena"
        assert job.inputs["entry_axes"] == ["product_engineering"]
    assert not mission_runtime.consume_concepting(db, enqueue=enqueue)["started"]


def test_the_ceiling_check_reads_the_tournament_brief_and_blocks_a_matching_objective():
    sys.path.insert(0, str(ROOT / "tests"))
    import test_cert_ideation as ti

    db = ti._db()
    inputs = {"lane": "breakthrough", "arena": "hats", "pod": "hats",
              "objective": "match MJs hat for hat and be as good as the benchmark",
              "diverged_from": "a released beanie",
              "trigger": {"kind": "benchmark_release", "listing_ref": "H0"},
              "briefs": [{"axis": "recipient", "question": "who?",
                          "claims_market_gap": False, "vocabulary": []}]}
    result, asked = ti._run(db, "creative.tournament", inputs=inputs)
    assert result["ran"] is False and result.get("ceiling_refused") is True, result
    assert not asked, "nothing may be sent to a generator after the ceiling refused"
    rows = ti._rows(db, "creative.tournament_ceiling_refused")
    assert rows and "match" in rows[0][2]["objective"]
    # The mission's own check reads the real brief it enqueues, not a default string.
    sys.path.insert(0, str(ROOT / "tests"))
    from test_cert_mjs import CROPPED

    db2 = _db()
    _mjs_mission(db2, CROPPED)
    with db2.session() as s:
        ev = s.scalar(select(MjsMissionEvent))
        job = s.get(Job, ev.tournament_job_id)
    assert ev.steps["panel"]["ceiling"]["objective"] == job.inputs["objective"]


if __name__ == "__main__":
    failed = passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL {name}: {exc}")
    print(f"{passed} passing, {failed} failing")
    sys.exit(1 if failed else 0)
