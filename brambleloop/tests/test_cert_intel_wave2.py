"""Certification repair (C-60): policy, physical proof, creative gates, seasonal and visual rows.

Handler-level, like `test_cert_intel_wave.py`: each test runs a registered handler through
the worker (or the handler registry with a real JobContext) on a real database and asserts
the downstream effect. No network: feeds and readers are injected where production builds
them from a credential.

Rows: #39 #64 #116 #125 #126 #128 #139 #201 #210 #287 #299.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", tempfile.mkdtemp(prefix="cert_intel_art_"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, Customer, Incident, Job, JobStatus, ListingAsset,
    ListingOutcome, OperatingReading, Order, PhysicalPhoto, Product, SeasonalTeam,
)
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

AS_OF = "2026-09-27"


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cert_intel2_')}/w.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    benchmarks.seed(db)
    return db


def _run(db, agent: str, job_type: str, inputs: dict | None = None, *,
         expect=JobStatus.DONE) -> dict:
    job = JobQueue(db).enqueue(agent, job_type, {"as_of": AS_OF, **(inputs or {})},
                               priority=0,
                               idempotency_key=f"t:{job_type}:{os.urandom(4).hex()}")
    assert Worker(db, "cert-intel2", job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == expect, (row.status, row.last_error)
        return dict(row.outputs or {})


# ---- #39: a material policy change blocks until reviewed and tested ------------------------


def test_a_material_policy_change_opens_a_blocking_incident_until_reviewed():
    from brambleloop.gates import platform_policy as pp
    from brambleloop.publish import release_gates

    db = _db()
    pp.record_snapshot(db, "seller_policy", text="the rules as read on Monday",
                       checked_on=AS_OF, read_by="owner", basis="page")
    out = _run(db, "orchestrator", "ops.policy_watch")
    assert out["changes_opened"] == [], "a first reading is not a change"
    pp.record_snapshot(db, "seller_policy", text="the rules as read on Friday -- changed",
                       checked_on=AS_OF, read_by="owner", basis="page")
    out = _run(db, "orchestrator", "ops.policy_watch")
    assert out["changes_opened"] == ["seller_policy"], out
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "policy_changed:seller_policy"))
        assert inc is not None and inc.halts_publication and not inc.resolved
    # Enforced where the workflows run: publication and new-class enablement refuse.
    gates = release_gates.staleness(db, slug="any-product")
    assert gates["blocks"] and any("platform policy changed" in r for r in gates["reasons"])
    try:
        pp.check_new_class(db, product_class=pp.SELLER_DESIGNED_DIGITAL)
    except pp.PolicyRefused as exc:
        assert "#39" in str(exc)
    else:
        raise AssertionError("a new class was enabled over an unreviewed policy change")
    assert pp.policy_stamp(db)["certified_against_current_policy"] is False
    # Reviewed and tested: the next watch resolves it and the block lifts.
    pp.review_change(db, "seller_policy", reviewed_by="owner",
                     tested="listing, publishing and support flows re-run against it")
    _run(db, "orchestrator", "ops.policy_watch")
    with db.session() as s:
        assert s.scalar(select(Incident).where(
            Incident.signature == "policy_changed:seller_policy")).resolved
    assert not any("platform policy changed" in r
                   for r in release_gates.staleness(db, slug="any-product")["reasons"])


# ---- #64: a physical photograph becomes an upgrade task and a measured comparison ----------


def test_a_physical_photo_with_rights_upgrades_the_listing_and_measures_impact():
    db = _db()
    with db.session() as s:
        s.add(ListingAsset(product_slug="cable-throw", version="1.0.0", position=1,
                           asset_class="AI_LIFESTYLE_CONCEPT", role="hero", approved=True))
    sha = hashlib.sha256(b"a real photograph").hexdigest()
    out = _run(db, "quality_director", "physical.photo",
               {"slug": "cable-throw", "version": "1.0.0", "source": "tester",
                "sha256": sha, "rights_basis": "tester_agreement", "taken_by": "tester-1"})
    assert out["may_use"] is True and out["upgrade_job"], out
    up = _run(db, "publishing", "assets.physical_upgrade", {"photo_id": out["photo_id"]})
    assert up["upgraded"] is True and up["replaceable"][0]["role"] == "hero"
    with db.session() as s:
        frame = s.scalar(select(ListingAsset).where(
            ListingAsset.asset_class == "PHYSICAL_PRODUCT_PHOTO"))
        assert frame.sha256 == sha and frame.approved is False
        assert frame.claims["rights_basis"] == "tester_agreement"
    impact = _run(db, "quality_director", "physical.upgrade_impact")
    assert impact["upgrades"] == 1 and impact["measured"] == 0      # UNMEASURED, not zero
    with db.session() as s:
        s.add(ListingOutcome(product_slug="cable-throw", period_start="2026-09-01",
                             period_end="2026-09-14", visits=100, first_frame_views=1000,
                             first_frame_engagements=20, orders=2, source="fixture"))
        photo = s.get(PhysicalPhoto, out["photo_id"])
        photo.detail = {**photo.detail, "baseline": {"ctr": 0.02, "conversion": 0.02}}
        s.add(ListingOutcome(product_slug="cable-throw", period_start="2026-10-01",
                             period_end="2026-10-14", visits=100, first_frame_views=1000,
                             first_frame_engagements=35, orders=4, source="fixture"))
    impact = _run(db, "quality_director", "physical.upgrade_impact",
                  {"as_of": "2026-10-15"})
    assert impact["measured"] == 1
    with db.session() as s:
        reading = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == "physical.upgrade_impact",
            OperatingReading.period_key == "2026-10-15"))
    r = reading.payload["readings"][0]
    assert r["ctr_after"] == 0.035 and r["ctr_delta"] > 0


def test_a_photo_without_rights_is_held_and_never_used():
    db = _db()
    out = _run(db, "quality_director", "physical.photo",
               {"slug": "cable-throw", "source": "customer",
                "sha256": hashlib.sha256(b"unlicensed").hexdigest()})
    assert out["may_use"] is False and out["upgrade_job"] is None
    with db.session() as s:
        assert s.scalar(select(ListingAsset)) is None


# ---- #125 / #126: measured top decile, and a board that requests the grid -----------------

HAT_TITLES = ["Cozy Chunky Beanie Hat Pattern", "Festive Christmas Hat Pattern",
              "Rustic Farmhouse Beanie Pattern", "Classic Toque Hat Pattern",
              "Playful Baby Hat Pattern", "Cozy Cottage Beanie Pattern"]
FLAGSHIP = {"key": "lantern-brim-beanie", "title": "Lantern Brim Beanie",
            "premise": ("a beanie whose folded brim stands proud of the crown so the "
                        "silhouette reads as a lantern from across a room"),
            "pod": "hats", "form": "hat", "construction": "in_the_round", "motif": "lantern",
            "palette_story": "ember and soot", "recipient": "teacher",
            "occasion": "halloween", "feeling": "whimsical",
            "function": "keeps a teacher warm on duty", "make_lane": "FLAGSHIP"}


def _hats(db):
    with db.session() as s:
        for i, t in enumerate(HAT_TITLES):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"H{i}",
                                   title=t, pod="hats"))


def test_radar_score_measures_a_flagship_against_the_top_decile_and_requests_its_grid():
    db = _db()
    _hats(db)
    out = _run(db, "market_radar", "radar.score",
               {"slug": "pumpkin-cluster-set", **FLAGSHIP})
    gate = out["gate"]
    assert "top_decile" not in gate["unmeasured"], gate
    with db.session() as s:
        row = s.scalars(select(AuditLog).where(
            AuditLog.action.like("concept.gate_%")).order_by(AuditLog.id.desc())).first()
        top = row.detail["checks"]["top_decile"]
        grid_jobs = list(s.scalars(select(Job).where(
            Job.job_type == "creative.grid_tournament")))
    assert top["status"] == "pass", top
    # #126: a board was rendered from the prototype twin and the grid was requested with it.
    assert len(grid_jobs) == 1
    board = grid_jobs[0].inputs["concepts"][0]["board_image"]
    assert board.startswith("artifact:")
    # A concept that is the page's commonest card sits below the top decile and is refused.
    common = {**FLAGSHIP, "key": "cosy-christmas-hat", "occasion": "christmas",
              "recipient": "self", "feeling": "cosy",
              "premise": "a cosy christmas beanie in a chunky rib with a folded cuff"}
    out = _run(db, "market_radar", "radar.score", {"slug": "pumpkin-cluster-set", **common})
    with db.session() as s:
        row = s.scalars(select(AuditLog).where(
            AuditLog.action.like("concept.gate_%")).order_by(AuditLog.id.desc())).first()
    assert row.detail["checks"]["top_decile"]["status"] == "fail", row.detail["checks"]


# ---- #128: a breakout is decomposed and adjacent original work is queued -------------------


def test_a_breakout_is_decomposed_and_an_adjacent_original_tournament_is_queued():
    db = _db()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    with db.session() as s:
        for slug in ("nordic-forest-mosaic-throw", "autumn-oak-mosaic-throw"):
            s.add(Product(slug=slug, title=slug))
        cust = Customer(customer_ref="c1")
        s.add(cust)
        s.flush()
        for i in range(30):
            s.add(Order(customer_id=cust.id, external_ref=f"o{i}", at=now,
                        product_slug="nordic-forest-mosaic-throw", category="mosaic_blanket",
                        price_cad=12.5, revenue_cad=12.5))
        for i in range(3):
            s.add(Order(customer_id=cust.id, external_ref=f"p{i}", at=now,
                        product_slug="autumn-oak-mosaic-throw", category="mosaic_blanket",
                        price_cad=12.5, revenue_cad=12.5))
    out = _run(db, "orchestrator", "seasonal.engine")
    assert "nordic-forest-mosaic-throw" in out["breakouts"], out
    assert out["breakout_adjacent_queued"], out
    with db.session() as s:
        mining = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == "seasonal.breakout_mining"))
        job = s.get(Job, out["breakout_adjacent_queued"][0])
    assert mining.payload["mined"][0]["winner"] == "nordic-forest-mosaic-throw"
    assert job.job_type == "creative.tournament" and job.inputs["lane"] == "breakout_adjacent"
    assert {b["axis"] for b in job.inputs["briefs"]} == {
        "format", "recipient", "complexity", "bundle_position"}
    assert "never a recolour" in job.inputs["objective"]


def test_no_orders_means_no_breakout_and_nothing_queued():
    db = _db()
    out = _run(db, "orchestrator", "seasonal.engine")
    assert out["breakouts"] == [] and out["breakout_adjacent_queued"] == []


# ---- #287: teams carry a real owner, and their shares steer the wheel ----------------------


def test_strike_teams_have_real_owners_and_their_shares_drive_selection():
    from brambleloop.creative import prospecting
    from brambleloop.seasonal.daily import active_shares

    db = _db()
    _run(db, "orchestrator", "seasonal.engine")
    with db.session() as s:
        teams = list(s.scalars(select(SeasonalTeam).where(SeasonalTeam.state == "active")))
    assert teams
    assert all(t.owner_agent in ("crochet_engineer", "listing", "creative_director", "growth")
               for t in teams), [t.owner_agent for t in teams]
    assert all(t.owns.get("owner_reason") for t in teams)
    shares = active_shares(db)
    assert shares and all(v > 0 for v in shares.values())
    # A team-held occasion is the priority half of the wheel; with no team it is not.
    team_event = sorted(shares)[0]
    found = [prospecting.Arena(event=team_event, pod="hats", benchmark_listings=5,
                               days_away=60, forms={"hat": 5}),
             prospecting.Arena(event="Nobody's Day", pod="bags", benchmark_listings=9,
                               days_away=50, forms={"bag": 9})]
    picks = {prospecting.choose(found, cycle=c, today=date(2026, 9, 27),
                                shares={team_event: 0.6}).event for c in range(10)}
    assert team_event in picks


# ---- #139: quote-class tokens are declared at filing and screened out of copy --------------


def test_a_catchphrase_topic_declares_a_slogan_token_the_copy_screen_refuses():
    from brambleloop.core.models import CultureSignal
    from brambleloop.culture import classify, demand, feeds, radar

    db = _db()
    reading = {"article": "Here's_Johnny!", "signal_key": "wiki:heres_johnny",
               "source": "wikimedia:fixture", "observed_on": AS_OF}
    saved = (feeds.discover, classify.classify, feeds.env_override, feeds.default_articles,
             feeds.sweep, demand.record, radar.route_findings)
    feeds.discover = lambda *a, **k: {"topics": [{"article": reading["article"]}]}
    classify.classify = lambda topics, db=None: {"filed": {}, "placed": {
        reading["article"]: "meme"}, "sensitive": []}
    feeds.env_override = lambda *a, **k: []
    feeds.default_articles = lambda *a, **k: []
    feeds.sweep = lambda *a, **k: {"readings": [reading], "source": "fixture",
                                   "recorded": 1, "attempted": 1, "failures": [],
                                   "channel": "fixture", "measures": "fixture"}
    demand.record = lambda *a, **k: {"recorded": 0}
    radar.route_findings = lambda *a, **k: {"recorded": 0, "skipped": []}
    try:
        _run(db, "market_radar", "culture.sweep")
    finally:
        (feeds.discover, classify.classify, feeds.env_override, feeds.default_articles,
         feeds.sweep, demand.record, radar.route_findings) = saved
    with db.session() as s:
        sig = s.scalar(select(CultureSignal).where(CultureSignal.key == "wiki:heres_johnny"))
    classes = {t["asset_class"] for t in sig.protected_tokens}
    assert "slogan" in classes, sig.protected_tokens
    problems, reading_out = release._quote_screen(
        db, "Here's Johnny crochet pattern -- a cosy late-night cowl")
    assert reading_out["quote_catchphrase_tokens"] >= 1
    assert problems and "RIGHTS_DIRECT_USE" in problems[0]


# ---- #201: gradual drift across batches opens a halting incident ---------------------------


def test_gradual_identity_drift_across_batches_opens_an_incident():
    from brambleloop.publish import model_photography

    db = _db()
    base = datetime(2026, 9, 20, tzinfo=timezone.utc)
    # Four batches of two frames; the hair dimension drifts in more frames each batch while
    # every other dimension matches.
    plan = [0, 1, 1, 2]
    with db.session() as s:
        for batch, drifted in enumerate(plan):
            for frame in range(2):
                dims = {d: "match" for d in ("face", "eyes", "age", "stylisation", "stature",
                                             "build", "shoulders", "torso", "bust")}
                dims["hair"] = "drift" if frame < drifted else "match"
                s.add(AuditLog(actor="publishing", action=model_photography.ACTION,
                               job_id=None, at=base + timedelta(days=batch, minutes=frame),
                               detail={"identity": {"dimensions": dims}}))
    out = _run(db, "quality_director", "visual.identity_drift")
    assert out["measurable"] and "hair" in out["gradual_drift"], out
    assert "face" not in out["gradual_drift"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "identity_drift_series:hair"))
        assert inc is not None and inc.halts_publication
        assert s.scalar(select(OperatingReading).where(
            OperatingReading.kind == "visual.identity_drift")) is not None


def test_too_few_batches_is_unmeasured_not_stable():
    db = _db()
    out = _run(db, "quality_director", "visual.identity_drift")
    assert out["measurable"] is False and out["gradual_drift"] == []


# ---- #116: the reference reading is gated on vision and stores its decomposition ----------


def test_reference_reading_refuses_without_vision_and_stores_decompositions_with_it():
    from brambleloop.core.models import BenchmarkObservation
    from brambleloop.creative import ideation, reference

    db = _db()
    out = _run(db, "creative_director", "creative.reference_reading")
    assert out["ran"] is False and "image_vision" in out["reason"]

    # With a vision provider (injected; production requires a recorded vision probe) the
    # same path reads, records and stores.
    with db.session() as s:
        for i in range(2):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"G{i}",
                                   title="Striped Cardigan Pattern", pod="garments",
                                   detail={"image_urls": [f"https://fixture.invalid/{i}.jpg"]}))
            for _ in range(2):
                s.add(BenchmarkObservation(
                    benchmark_key=benchmarks.MJS_KEY, listing_ref=f"G{i}",
                    kind="gallery_image_observation", grade="primary",
                    detail={"observation": {"palette_role": "accent",
                                            "setting": "studio",
                                            "emotional_merchandising": "calm"}}))

    from brambleloop.gateway import anthropic as gw

    class Seer:
        model = gw.provider_for(reference.TASK).model
        cost_per_1k_input_cad = 0.0
        cost_per_1k_output_cad = 0.0

        def see(self, system, prompt, images, max_tokens=0):
            from brambleloop.gateway.model_gateway import ModelResponse

            text = ('{"silhouette_class": "boxy", "neckline": "crew", '
                    '"colour_blocking": "stripe", "edge_finish": "ribbed", '
                    '"styling_context": "layering"}')
            return ModelResponse(text=text, input_tokens=10, output_tokens=10,
                                 provider="fixture", model=self.model, latency_ms=1.0)

    got = reference.run(db, provider=Seer(), today=date(2026, 9, 27))
    assert got["ran"] and len(got["read"]) == 2, got
    assert "garments" in got["decompositions_stored"]
    stored = reference.stored_decomposition(db, "garments")
    assert stored["primitives"]
    # Ideation reads the stored record rather than recomputing it.
    lessons = ideation.lessons(db, kind="tournament", event="Christmas", pod="garments")
    assert lessons["reference"]["usable"] is True
    assert "stored decomposition" in lessons["reference"]["reason"]


# ---- #210 / #299: pod maps persisted and read; matrix cells carry the listed columns -------


def test_pod_maps_are_persisted_and_order_the_same_arena_lane():
    from brambleloop.intel import mission_runtime

    db = _db()
    with db.session() as s:
        for pod, n in (("hats", 6), ("blankets", 6)):
            for i in range(n):
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,
                                       listing_ref=f"{pod}{i}", pod=pod,
                                       title=f"Chunky {pod[:-1]} crochet pattern",
                                       price_cad=8.0 if pod == "hats" else 14.0,
                                       detail={"num_favorers": 20 if pod == "hats" else 400}))
    agent_types = None
    with db.session() as s:
        from brambleloop.core.models import Agent

        a = s.scalar(select(Agent).where(Agent.name == "market_radar"))
        agent_types = list(a.allowed_job_types or [])
    assert "intel.pod_learning" in agent_types
    out = _run(db, "market_radar", "intel.pod_learning")
    assert set(out["pod_maps"]) >= {"hats", "blankets"}, out
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == "mjs.pod_maps"))
    hats = row.payload["pods"]["hats"]
    assert hats["history"]["observed_listings"] == 6 and hats["rubric"]
    assert "image_evidence" in hats["opportunity"]
    prio = mission_runtime._pod_priority(db)
    assert set(prio) >= {"hats", "blankets"}


def test_matrix_cells_carry_the_columns_the_requirement_lists():
    from brambleloop.seasonal import benchmark_matrix

    db = _db()
    with db.session() as s:
        for i in range(6):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"S{i}",
                                   pod="stockings", title="Christmas Stocking Crochet Pattern",
                                   media_count=6, audit_state="audited",
                                   detail={"gallery_audited": True, "num_favorers": 50}))
    m = benchmark_matrix.matrix(db, today=date(2026, 9, 27))
    cells = [c for r in m["rows"] if r["event"] == "Christmas" for c in r["cells"]
             if c["department"] == "stockings"]
    assert cells, "no Christmas/stockings cell"
    cell = cells[0]
    for column in ("benchmark_concepts", "merchandising_mechanisms",
                   "adaptation_opportunities", "our_products"):
        assert column in cell, column
    assert cell["benchmark_concepts"].get("stocking") == 6
    assert cell["merchandising_mechanisms"].get("gallery_depth") == 6
    assert cell["adaptation_opportunities"][0]["arena"] == "stocking"


# ---- #86: the creativity benchmark memory is UNMEASURED without judged images, learns from
# them, and steers the ideation brief ------------------------------------------------------


def test_benchmark_memory_is_unmeasured_without_judged_images_then_steers_the_brief():
    from brambleloop.core.models import Agent, BenchmarkObservation
    from brambleloop.creative import benchmark_memory, ideation

    db = _db()
    with db.session() as s:
        a = s.scalar(select(Agent).where(Agent.name == "creative_director"))
        assert "creative.benchmark_memory" in (a.allowed_job_types or [])

    # No judged image: the memory runs on its cadence and says UNMEASURED with the reason,
    # and the brief carries no market attribute rather than a guessed one.
    out = _run(db, "creative_director", "creative.benchmark_memory")
    assert out["measured"] is False and out["state"] == "UNMEASURED", out
    assert out["rewarded"] == []
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == benchmark_memory.KIND))
        assert row is not None and "image_vision" in row.payload["reason"]
        assert row.payload["outcomes"]["brambleloop"]["orders"] == "UNMEASURED"
    lessons = ideation.lessons(db, kind="tournament", event="Christmas", pod="hats")
    assert lessons["market_attributes"] == []

    # Judged gallery observations (the rows intel.gallery_analysis writes) carrying the #86
    # vocabulary, on listings with the API's favourites. Three listings read as a clever
    # transformation and are the popular ones; two read as minimalism and are not.
    with db.session() as s:
        for i, (attr, phrase, favourites) in enumerate((
                ("transformation", "reads as a hat that becomes a bag", 900),
                ("transformation", "one make, two uses shown in frame one", 700),
                ("transformation", "the fold is the selling point", 800),
                ("minimalism", "single colour, no trim", 40),
                ("minimalism", "plain field, one motif", 60))):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"M{i}",
                                   pod="hats", title="Crochet Hat Pattern",
                                   detail={"num_favorers": favourites}))
            s.add(BenchmarkObservation(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"M{i}",
                kind="gallery_image_observation", grade="primary",
                detail={"observation": {attr: phrase, "setting": "studio"}}))

    out = _run(db, "creative_director", "creative.benchmark_memory")
    assert out["measured"] is True and set(out["attributes"]) == {"transformation",
                                                                   "minimalism"}
    assert out["rewarded"] == ["transformation"], out
    reading = benchmark_memory.latest(db)
    t, m = reading["attributes"]["transformation"], reading["attributes"]["minimalism"]
    assert t["listings"] == 3 and t["demand_lift"] > 1 and m["demand_lift"] < 1
    assert "reads as a hat that becomes a bag" in t["phrases"]
    # Only the closed vocabulary is stored: the merchandising field on the same observation
    # is not a commercial attribute and does not enter the memory.
    assert "setting" not in reading["attributes"]

    # Acted on: the tournament brief names what the market rewards, with its measured lift.
    lessons = ideation.lessons(db, kind="tournament", event="Christmas", pod="hats")
    assert [a["attribute"] for a in lessons["market_attributes"]] == ["transformation"]
    assert lessons["market_attributes"][0]["seen_in_pod"] is True
    plan = ideation.plan(db, kind="tournament", event="Christmas", pod="hats",
                         forms=["hat"], cycle=0, today=date(2026, 9, 27))
    text, _ = ideation.constraints_text(plan, 0)
    assert "market rewards transformation" in text and "hat that becomes a bag" in text


# ---- #226: a measured discernment reading changes which pod's lane starts first -----------


def test_a_measured_discernment_reading_reorders_the_same_arena_lane():
    from brambleloop.core.models import PodCapabilityReading
    from brambleloop.intel import mission_runtime

    db = _db()
    with db.session() as s:
        for pod in ("hats", "blankets"):
            for i in range(6):
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,
                                       listing_ref=f"{pod}{i}", pod=pod,
                                       title=f"Chunky {pod[:-1]} crochet pattern",
                                       price_cad=8.0, detail={"num_favorers": 120}))
    _run(db, "market_radar", "intel.pod_learning")
    before = mission_runtime._pod_priority(db)
    assert before["hats"] == before["blankets"] > 0, before

    # A pod whose discernment has been measured at zero precision -- twelve settled calls,
    # none of them right -- keeps half its opportunity; the unmeasured pod keeps all of it.
    with db.session() as s:
        s.add(PodCapabilityReading(
            pod="hats", measured=True,
            discernment={"reading": "measured", "settled": 12, "precision": 0.0},
            creativity={"reading": "measured", "responses": 6},
            balance={"reading": "measured"}, detail={}))
    _run(db, "market_radar", "intel.pod_learning")
    after = mission_runtime._pod_priority(db)
    assert after["blankets"] == before["blankets"]
    assert abs(after["hats"] - before["hats"] * 0.5) < 1e-9, (before, after)
    assert after["blankets"] > after["hats"]


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
