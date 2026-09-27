"""Certification: the original-design pipeline, from tournament winner to engineering (C-61).

The audit of 9434c53 found the creative engine severed at its most important joint: a
tournament winner met the pre-engineering gate with no brief (so it failed "no thumbnail
storyboard", "no motifs" and "no WOW mechanism" by construction), nothing asked the funnel
whether it had been carried to prototype, and nothing ever queued `cir.draft`.

Every test here drives the runtime -- `creative.tournament`, `cir.draft`, `cir.compile`,
`mjs.scan`, `mjs.seasonal_sentinel`, `intel.pod_learning`, `listing.seo`, `launch.plan`
through the worker or the handler registry with a real JobContext on a real database -- with
only the model call substituted by a fixture generator. Every competitor listing, vision
judgement, order and listing row seeded here is a test fixture, never an observation or a
customer.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, BenchmarkObservation, CoverageGap, CultureConcept,
    CultureSignal, Job, JobStatus, Listing, MjsMissionEvent, Order, Customer, PodLesson,
    SerpSnapshot,
)
from brambleloop.creative import intake  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, Worker, handlers  # noqa: E402

CONS = {"stocking": ("flat_rows", "in_the_round", "seamless_tube"),
        "ornament": ("flat_rows", "in_the_round", "amigurumi_shaping")}
RECIPIENTS = ("self", "partner", "new_parent", "child", "teen", "grandparent", "host",
              "pet_owner", "colleague", "teacher", "friend_who_has_everything", "newlyweds",
              "student")
MOTIFS = ("gingerbread", "lantern", "bell", "sleigh", "nutcracker", "holly", "candle",
          "mitten", "wreath", "ornament", "bow", "candy", "woodland")
FEELINGS = ("nostalgic", "festive", "heirloom", "whimsical", "celebratory", "playful",
            "tender", "folkloric")
WORDS = ("acorn birch cinder dapple ember fennel garnet hazel indigo juniper kestrel linden "
         "meadow nutmeg oriel pebble quill russet sorrel thistle umber vervain willow yarrow "
         "zephyr alder bramble clover damson elder fern gorse heath iris jasper kelp larch "
         "myrtle nettle olive pine quince rowan sloe tansy").split()


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='cert_design_')}/design.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _stockings(db, n: int = 12, pod: str = "stockings") -> None:
    """Fixture benchmark listings: a proven Christmas stockings department."""
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"S{i}",
                title=("Festive Christmas Stocking Crochet Pattern",
                       "Christmas Ornament Crochet Pattern")[i % 2],
                pod=pod, price_cad=8.0, audit_state="audited",
                detail={"num_favorers": 90}))


def _unique(j: int, t: int) -> str:
    # Letters only: the premise tokeniser reads [a-z]+, so a digit suffix would collapse.
    return f"{WORDS[(j * 5 + t) % len(WORDS)]}q{chr(97 + j % 26)}{chr(97 + j // 26)}"


def stocking_field(copy_language_every: int = 0):
    """A fixture generator for a genuinely varied Christmas field.

    Each concept varies construction, recipient, motif and function and states a premise in
    its own words -- the shape a field needs to survive the sibling gate (#119). The model is
    the only thing substituted; every gate downstream is the real one.
    """
    count = {"n": 0, "form": {}}

    def gen(values, _call):
        form = values["form"].replace(" ", "_")
        out = []
        for _ in range(int(values.get("count") or 1)):
            j = count["n"]
            count["n"] += 1
            q = count["form"].setdefault(form, 0)
            count["form"][form] += 1
            u = [_unique(j, t) for t in range(4)]
            m = MOTIFS[j % len(MOTIFS)]
            premise = f"a {form} whose {m} {u[0]} {u[1]} {u[2]} {u[3]} cuff"
            if copy_language_every and j % copy_language_every == 0:
                premise = f"a {form} that is perfect for cosy nights and makes a great gift"
            out.append({
                "title": f"{u[0].title()} {m.title()} {form.title()}",
                "premise": premise,
                "construction": CONS.get(form, ("in_the_round",))[q % 3],
                "motif": f"{m} {u[1]}", "palette_story": "cranberry, cream and gold",
                "recipient": RECIPIENTS[q % len(RECIPIENTS)], "occasion": "christmas",
                "feeling": FEELINGS[j % len(FEELINGS)],
                "function": f"holds {u[2]} treats by the {u[3]} hearth", "wow": "cuff"})
        return {"concepts": out}
    return gen


def _patched(generator):
    from brambleloop.gateway import model_gateway

    saved = model_gateway.ModelGateway.complete_json
    asked: list[dict] = []

    def fake(self, ref, *, agent, values, required=None):
        asked.append(dict(values))
        return generator(values, len(asked))
    model_gateway.ModelGateway.complete_json = fake
    return saved, asked


def _handler(db, job_type: str, inputs: dict | None = None, *, generator=None,
             agent: str = "creative_director") -> tuple[dict, list]:
    """Enqueue, then dispatch through the handler registry with a real JobContext."""
    from brambleloop.gateway import model_gateway

    q = JobQueue(db)
    job = q.enqueue(agent, job_type, inputs or {},
                    idempotency_key=f"t:{job_type}:{os.urandom(4).hex()}")
    ctx = JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=None)
    handler = handlers.get(job_type)
    assert handler is not None, f"{job_type} has no registered handler"
    saved, asked = _patched(generator or stocking_field())
    try:
        return handler(ctx), asked
    finally:
        model_gateway.ModelGateway.complete_json = saved


def _drain(db, job_type: str, limit: int = 10) -> list[dict]:
    """Run queued jobs of one type through the real worker."""
    out = []
    for _ in range(limit):
        if not Worker(db, "cert-design", job_types=[job_type]).run_once():
            break
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == job_type)):
            out.append({"id": j.id, "status": j.status, "inputs": dict(j.inputs or {}),
                        "outputs": dict(j.outputs or {}), "error": j.last_error})
    return out


def _rows(db, action: str) -> list[tuple[int, str, dict]]:
    with db.session() as s:
        return [(r.id, r.artifact or "", dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def _jobs(db, job_type: str) -> list[Job]:
    with db.session() as s:
        rows = [j for j in s.scalars(select(Job).where(Job.job_type == job_type))]
        s.expunge_all()
        return rows


def _judge(db, slug: str, *, reads=True, craft=4.3) -> None:
    """A vision judge's recorded verdict on a concept board -- a fixture standing in for the
    model_provider/image_vision judge that does not exist in shadow."""
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=intake.JUDGED_ACTION, artifact=slug,
                       detail={"thumbnail_reads_small": reads, "craft_impression": craft,
                               "judge": "fixture vision judge"}))


def _tournament(db, **kw) -> tuple[dict, dict]:
    result, asked = _handler(db, "creative.tournament", **kw)
    rows = _rows(db, intake.INTAKE_ACTION)
    return result, (rows[-1][2] if rows else {})


# ---- C-61 core: the winner gets a generated brief and meets the gate with it ------------


def test_winner_brief_is_generated_and_the_gate_reads_it_88_110_115():
    """#88 #110 #115: the storyboard, the motifs and the WOW slot are produced from the
    winner, and the gate's deterministic brief checks pass on a real brief."""
    db = _db()
    _stockings(db)
    result, row = _tournament(db)
    assert result["ran"] is True and result["winner"], result
    brief = row["brief"]
    words = [w for w in brief["thumbnail_storyboard"].split() if len(w) > 3]
    assert len(words) >= 6 and row["concept"]["premise"].rstrip(".") in \
        brief["thumbnail_storyboard"]
    assert brief["motifs"] and set(brief["motifs"]) <= set(
        __import__("brambleloop.creative.invention", fromlist=["x"]).MOTIF_GRAMMAR["christmas"])
    assert brief["season"] == "christmas"
    gate = row["gate"]
    assert "premise_thumbnail" not in (gate["failed"] or [])
    assert "motif_grammar" not in (gate["failed"] or []), gate
    assert "emotional_promise" not in (gate["failed"] or [])
    # Taste is unjudged in shadow, so the honest decision is waiting on a vision model.
    assert gate["decision"] == "waiting" and "image_vision" in gate["waiting_on"]
    # The gate verdict is recorded against the winning design's slug.
    assert any(a == row["concept"]["key"] for _i, a, _d in _rows(db, "concept.gate_waiting"))


def test_a_carried_judged_winner_is_queued_drafted_and_compiled_3_277_281():
    """#3 #277 #281: the funnel carried the winner to prototype; once a vision judgement is
    recorded the held winner is re-presented on cadence, passes, and `cir.draft` authors a
    CIR the compiler accepts."""
    db = _db()
    _stockings(db)
    result, row = _tournament(db)
    slug = row["concept"]["key"]
    assert row["funnel"]["carried"] is True, row["funnel"]
    assert row["decision"] == intake.WAITING and not _jobs(db, "cir.draft")
    _judge(db, slug)
    out, _ = _handler(db, "mjs.seasonal_sentinel", {}, agent="market_radar")
    assert {"slug": slug, "decision": "engineering"} in out["regated"]["presented"], out
    drafts = _jobs(db, "cir.draft")
    assert len(drafts) == 1 and drafts[0].inputs["slug"] == slug
    assert drafts[0].inputs["brief"]["motifs"] == row["brief"]["motifs"]
    done = _drain(db, "cir.draft")
    assert done[0]["status"] == JobStatus.DONE and done[0]["outputs"]["drafted"] is True, done
    assert any(a.startswith(f"{slug}@") for _i, a, _d in _rows(db, "cir.drafted"))
    compiled = _drain(db, "cir.compile")
    assert compiled and compiled[0]["outputs"]["compiled"] is True, compiled
    assert _jobs(db, "gate.certify"), "a compiled winner was not sent to certification"


def test_a_winner_the_funnel_did_not_carry_is_never_engineered_3():
    """#3: a narrow field dies at research; its winner is not carried to prototype, so no
    judgement, however good, re-opens it and `cir.draft` refuses it by name."""
    from test_cert_ideation import _db as hats_db

    from test_cert_ideation import _run as ideation_run

    db = hats_db()

    result, _asked = ideation_run(db, "creative.tournament")
    row = _rows(db, intake.INTAKE_ACTION)[-1][2]
    assert row["decision"] == intake.NOT_CARRIED, row["decision"]
    assert "prototype" in row["funnel"]["why"]
    slug = row["concept"]["key"]
    _judge(db, slug)
    out, _ = _handler(db, "mjs.seasonal_sentinel", {}, agent="market_radar")
    assert not out["regated"]["queued"] and not _jobs(db, "cir.draft")
    # And enqueued directly, the engineering entry refuses it at the funnel.
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", {
        **row["payload"], "concept": {**row["payload"]["concept"],
                                      "thumbnail_reads_small": True,
                                      "craft_impression": 4.5}}, idempotency_key="direct")
    done = _drain(db, "cir.draft")
    assert done[0]["outputs"]["drafted"] is False
    assert not _jobs(db, "cir.compile")


def test_copy_language_premises_are_refused_at_generation_109():
    """#109: a premise that delivers its feeling only as listing copy never becomes a
    concept, and the gate's promise check names the object part that carries it."""
    db = _db()
    _stockings(db)
    result, row = _tournament(db, generator=stocking_field(copy_language_every=4))
    rows = [r for r in _rows(db, "creative.tournament")][-1][2]
    problems = rows["field"]["problems"]
    assert any("no emotional promise in the object" in p for p in problems), problems[:3]
    assert "perfect for" not in row["concept"]["premise"]
    assert row["brief"]["promise"]["execution"] in (
        "motif", "structure", "texture", "colour_relationship", "scale", "finish")
    assert row["brief"]["promise"]["feeling"] == row["concept"]["feeling"]


def test_the_tournament_judges_the_real_window_and_plans_make_time_per_skill_112_283():
    """#112: research is judged at the arena's real days to the event, and late-window
    capacity is graded; #283: make time is estimated per maker skill with launch dates."""
    db = _db()
    _stockings(db)
    result, row = _tournament(db)
    t = _rows(db, "creative.tournament")[-1][2]
    assert isinstance(t["days_to_event"], int) and t["days_to_event"] == result["days_to_event"]
    assert t["window"] is not None and "new_work_should_be_no_heavier_than" in t["window"]
    make = row["brief"]["make_time"]
    days = {k: v["effective_make_days"] for k, v in make["by_skill"].items()}
    assert set(days) == set(intake.MAKER_SKILLS)
    assert days["beginner"] > days["experienced"], days
    assert make["planned_for_skill"] == "beginner"      # a QUICK lane is beginner work
    assert make["plan"]["preferred_launch"] < make["plan"]["latest_effective_launch"]
    assert set(row["brief"]["window_by_skill"]) == set(intake.MAKER_SKILLS)


def test_a_flagship_carries_a_wow_from_its_own_words_and_one_without_fails_115_290():
    """#115: the WOW mechanism is read from the winner's premise; a flagship whose words
    carry none still fails by name. #290: a flagship on a short trend is refused."""
    from brambleloop.creative.concept import Concept
    from brambleloop.creative.prospecting import Candidate

    db = _db()
    q = JobQueue(db)
    ctx = JobContext(job=q.enqueue("creative_director", "creative.tournament", {}), db=db,
                     queue=q, registry=Registry(db), phase=None)
    base = dict(pod="blankets", form="rectangle_throw", construction="modular_panels",
                motif="woodland lantern procession", palette_story="forest and gold",
                recipient="grandparent", occasion="housewarming", feeling="heirloom",
                function="covers a sofa and becomes a wall of lanterns", make_lane="FLAGSHIP")
    good = Candidate(concept=Concept(
        key="t1-x-0", title="Lantern Procession Throw",
        premise="a throw whose modular lantern panels unfold into a woodland procession",
        **base), slot=None)
    plan = {"lessons": {"lesson_ids": []}, "vision": None}
    got = intake.intake(ctx, candidate=good, plan=plan, source="test", funnel_rounds=[])
    row = _rows(db, intake.INTAKE_ACTION)[-1][2]
    from brambleloop.creative.invention import WOW_MECHANISMS

    assert row["brief"]["wow_mechanism"] in WOW_MECHANISMS, row["brief"]
    assert "modular" in row["brief"]["derivation"]["wow"]
    assert "wow" not in (row["gate"]["failed"] or [])
    assert got["decision"] == intake.NOT_CARRIED       # no funnel run, no engineering
    plain = Candidate(concept=Concept(
        key="t1-x-1", title="Plain Throw",
        premise="a warm soft throw in two quiet colours for the sofa at night",
        **{**base, "construction": "flat_rows", "motif": "quiet colours",
           "function": "covers a sofa"}), slot=None)
    intake.intake(ctx, candidate=plain, plan=plan, source="test", funnel_rounds=[])
    row = _rows(db, intake.INTAKE_ACTION)[-1][2]
    assert row["brief"]["wow_mechanism"] is None and "wow" in row["gate"]["failed"]
    # #290: the same flagship translated from a film moment (short seasonal) is refused.
    with db.session() as s:
        s.add(CultureSignal(key="fixture-film", topic="a film", domain="film"))
        cc = CultureConcept(signal_key="fixture-film", slug="fixture-film-throw",
                            family="blanket", premise="p")
        s.add(cc)
        s.flush()
        cc_id = cc.id
    intake.intake(ctx, candidate=good, plan=plan, source="test", funnel_rounds=[],
                  culture_id=cc_id)
    row = _rows(db, intake.INTAKE_ACTION)[-1][2]
    assert row["brief"]["half_life"]["half_life"] == "short_seasonal"
    assert "half_life" in row["gate"]["failed"] and row["decision"] == intake.REFUSED


def test_vision_readings_reach_the_briefs_and_the_storyboard_278():
    """#278: judged competitor photography is concept evidence -- it reaches every model
    brief and frames the storyboard -- and with none the plan says UNMEASURED."""
    db = _db()
    _stockings(db)
    result, row = _tournament(db)
    assert "UNMEASURED" in _rows(db, "creative.tournament")[-1][2]["ideation"]["vision"]["state"]
    assert "hero product only" in row["brief"]["thumbnail_storyboard"]
    db = _db()
    _stockings(db)
    with db.session() as s:
        for i in range(4):
            s.add(BenchmarkObservation(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"S{i}",
                kind="gallery_image_observation",
                detail={"observation": {"shot_type": "hero_styled",
                                        "silhouette_strength": "a clear hooked outline",
                                        "motif_legibility": "one large motif per cuff"}}))
    result, asked = _handler(db, "creative.tournament")
    row = _rows(db, intake.INTAKE_ACTION)[-1][2]
    block = _rows(db, "creative.tournament")[-1][2]["ideation"]
    assert block["vision"]["judged_images"] == 4
    assert all("competitor photography" in a["brief"] for a in asked)
    assert all("one large motif per cuff" in a["brief"] for a in asked)
    assert row["brief"]["thumbnail_storyboard"].startswith("hero styled")


def test_the_radar_skill_gap_brief_is_consumed_by_ideation_114():
    """#114: the radar's measured skill gap is read by the next tournament, reaches the
    model's brief, and steers the winner toward the missing level."""
    db = _db()
    _stockings(db)
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="radar.skill_gap", detail={
            "missing": ["beginner_quick_win"], "over": ["advanced_heirloom"],
            "brief": "ideate new concepts at ['beginner_quick_win'] for this wave",
            "as_of": "2026-09-27"}))
    result, asked = _handler(db, "creative.tournament")
    block = _rows(db, "creative.tournament")[-1][2]["ideation"]
    assert block["skill_gap"]["missing"] == ["beginner_quick_win"]
    assert block["skill_gap"]["source"].startswith("radar.skill_gap row")
    assert all("missing beginner_quick_win work" in a["brief"] for a in asked)
    assert block["winner"]["fills_skill_gap"] is True


def test_design_provenance_is_keyed_on_the_winning_design_101():
    """#101: the provenance names the winning design, and compounding counts designs."""
    from brambleloop.improve import bus, roi

    db = _db()
    _stockings(db)
    lesson = bus.publish(db, origin_cell="product_creativity", subject="creative_rejection",
                         statement=("stocking concepts whose cuffs repeat the same fold were "
                                    "killed as sameness, so vary the cuff construction"),
                         evidence_ref="test:autopsy:1")
    _tournament(db)
    _tournament(db)
    slugs = {r[2]["concept"]["key"] for r in _rows(db, intake.INTAKE_ACTION)}
    prov = {a: d for _i, a, d in _rows(db, "design.provenance")}
    assert slugs <= set(prov), (slugs, list(prov))
    assert all(lesson in prov[s]["lesson_ids"] for s in slugs)
    report = roi.compounding_report(db)
    assert report["designs"] == len(slugs) and report["briefs_recorded"] >= 1
    assert report["designs_using_accumulated_knowledge"] == len(slugs)


# ---- #314 #316 #318: the mission reads the design pipeline ------------------------------


def _mjs_mission(db, listings_extra=()):
    """The MJs fixture mission from test_cert_mjs: one new cropped cardigan listing."""
    import test_cert_mjs as M

    M.benchmarks.seed(db)
    M._scan(db, M.BASELINE)
    M._scan(db, M.BASELINE + [M.CROPPED, *listings_extra])
    saved = M._no_credential()
    try:
        out, _ = _handler(db, "mjs.scan", {"as_of": M.AS_OF}, agent="market_radar")
    finally:
        M._restore(saved)
    return out


def test_gap_queue_scores_timing_search_and_make_time_and_advances_314():
    """#314: the gap queue scores seasonal timing, search opportunity and make time from
    rows, and a winner moves its department's gap past `concepting`."""
    db = _db()
    with db.session() as s:
        s.add(SerpSnapshot(query="christmas cardigan crochet pattern", total_count=4200))
    _mjs_mission(db)
    with db.session() as s:
        gap = s.scalar(select(CoverageGap).where(CoverageGap.pod == "garments"))
        components = dict(gap.components["components"])
        missing = list(gap.components["missing"])
    assert {"seasonal_timing", "search_opportunity", "make_time"} <= set(components), components
    assert 0.0 < components["search_opportunity"] < 1.0
    assert set(missing) == {"expected_contribution", "creative_potential"}
    # A stockings department winner that clears engineering moves its gap to engineering.
    db2 = _db()
    _stockings(db2)
    from brambleloop.intel import coverage
    coverage.upsert(db2, benchmark_key=benchmarks.MJS_KEY, arena="Christmas stockings",
                    pod="stockings", components={"apparent_demand": 0.5})
    _r, row = _tournament(db2)
    _judge(db2, row["concept"]["key"])
    _handler(db2, "mjs.seasonal_sentinel", {}, agent="market_radar")
    with db2.session() as s:
        gap = s.scalar(select(CoverageGap).where(CoverageGap.pod == "stockings"))
        assert gap.state == "engineering" and gap.product_slug == row["concept"]["key"]


def test_pod_memory_is_fed_by_brambleloop_responses_and_challenged_316():
    """#316: a winner is an interpretation the pod holds; its launch outcomes move it, and a
    contradicted interpretation gets a commercial-execution challenger."""
    db = _db()
    _stockings(db)
    _r, row = _tournament(db)
    slug = row["concept"]["key"]
    lesson = row["pod_lesson"]
    assert lesson["subject"] == "response:christmas"
    out, _ = _handler(db, "intel.pod_learning", {}, agent="market_radar")
    assert out["responses"]["state"].startswith("UNMEASURED"), out
    # A fixture launch 70 days old with no order is a failed launch; a second response the
    # same is a second contradiction, which raises a challenger.
    _r2, row2 = _tournament(db, generator=stocking_field(copy_language_every=0))
    old = datetime.now(timezone.utc) - timedelta(days=70)
    with db.session() as s:
        for sl in {slug, row2["concept"]["key"]}:
            s.add(Listing(product_slug=sl, version="1.0.0", title="t", description="d",
                          state="published", created_at=old))
    _handler(db, "intel.pod_learning", {}, agent="market_radar")
    with db.session() as s:
        rows = list(s.scalars(select(PodLesson).where(
            PodLesson.pod == "stockings", PodLesson.subject == "response:christmas")))
        incumbent = next(r for r in rows if r.origin == "brambleloop_response")
        kinds = [e["kind"] for e in incumbent.contradicted_by or []]
        challengers = [r for r in rows if r.origin == "challenger"]
    slugs = set(incumbent.detail["slugs"])
    assert kinds.count("launch_failed") == len(slugs), kinds
    if len(slugs) >= 2:
        assert challengers and challengers[0].active, "a contradicted response was not challenged"
    # An order is a sale: it supports the interpretation.
    with db.session() as s:
        c = Customer(customer_ref="fixture-customer")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="fixture-order-1", product_slug=slug,
                    revenue_cad=8.0))
    _handler(db, "intel.pod_learning", {}, agent="market_radar")
    with db.session() as s:
        inc = s.get(PodLesson, incumbent.id)
        assert any(e["kind"] == "launch_sold" for e in inc.supported_by or [])


def test_mission_report_carries_every_318_field_from_rows():
    db = _db()
    _mjs_mission(db)
    from brambleloop.intel.mission import mission_report

    report = mission_report(db)
    for field in ("last_successful_scan", "listings_changed_new", "pod_assignments",
                  "top_uncovered_opportunities", "upcoming_seasonal_adaptations",
                  "launch_deadlines", "comparison_results", "products_launched",
                  "conversion_revenue", "mission_incidents"):
        assert field in report, field
    assert report["last_successful_scan"]
    assert report["listings_changed_new"]["last_scan"].get("new listing") == 1
    assert report["pod_assignments"].get("garments") == 1
    assert report["upcoming_seasonal_adaptations"][0]["event"] == "Christmas"
    assert report["launch_deadlines"][0]["latest_effective_launch"]
    assert report["conversion_revenue"]["state"].startswith("UNMEASURED")
    assert "UNMEASURED" in str(report["comparison_results"])
    # The owner's command centre (the `/` route) renders them from the same database.
    from brambleloop.app import main

    saved = main.db
    main.db = db
    try:
        html = main.dashboard()
    finally:
        main.db = saved
    for label in ("last successful scan", "pod assignments", "top uncovered",
                  "seasonal adaptations", "launch deadlines", "comparison results",
                  "products launched", "conversion / revenue", "mission incidents"):
        assert label in html, label


# ---- #308 / #309: the MJs response, end to end as far as software goes -----------------


def test_mjs_response_is_walked_from_listing_to_engineering_309():
    """#309: an MJs stockings listing becomes a Christmas response tournament, the winner
    passes intake once judged, `cir.draft` runs, and the event's pipeline walks past
    make-time, launch dates and CIR engineering from the rows those stages wrote -- and stops
    where the next gate has genuinely not passed, saying why."""
    import test_cert_mjs as M

    db = _db()
    _stockings(db)
    stocking = M._listing(1101, "Christmas Stocking Crochet Pattern, Cuffed Holiday Stocking",
                          320)
    M.benchmarks.seed(db)
    M._scan(db, M.BASELINE)
    M._scan(db, M.BASELINE + [stocking])
    saved = M._no_credential()
    try:
        _handler(db, "mjs.scan", {"as_of": M.AS_OF}, agent="market_radar")
    finally:
        M._restore(saved)
    with db.session() as s:
        ev = s.scalar(select(MjsMissionEvent).where(MjsMissionEvent.listing_ref == "1101"))
        assert ev is not None and ev.entered, "the stocking listing was not entered"
        job = s.get(Job, ev.tournament_job_id)
        inputs, event_id = dict(job.inputs), ev.id
    assert inputs["seasonal_target"] == "Christmas"
    result, _ = _handler(db, "creative.tournament", inputs)
    assert result["arena"] == "Christmas/stockings", result["arena"]
    row = _rows(db, intake.INTAKE_ACTION)[-1][2]
    assert row["mjs_event_id"] == event_id
    slug = row["concept"]["key"]
    _judge(db, slug)
    _handler(db, "mjs.seasonal_sentinel", {"as_of": M.AS_OF}, agent="market_radar")
    _drain(db, "cir.draft")
    _drain(db, "cir.compile")
    _handler(db, "mjs.seasonal_sentinel", {"as_of": M.AS_OF}, agent="market_radar")
    with db.session() as s:
        pipe = s.get(MjsMissionEvent, event_id).pipeline
    assert pipe["winner"] == slug
    assert pipe["completed"][:8] == ["observation", "pod_routing", "market_decomposition",
                                     "demand_and_season_fit", "seasonal_tournament",
                                     "make_time_estimate", "launch_dates",
                                     "cir_engineering"], pipe["completed"]
    assert pipe["stopped"] is not None and pipe["stopped"]["evidence"]


def test_christmas_cardigan_path_runs_to_the_gate_that_stops_it_308():
    """#308: the MJs cropped-cardigan listing becomes a Christmas garments tournament with
    Christmas cardigans in the field; the funnel's proposition stage applies #111's family
    test, which no fitted cardigan construction passes (no quick companion), so no cardigan
    is carried to prototype and none is engineered. The pipeline records exactly that stop.
    This is a real owner-rule conflict, reported rather than bypassed."""
    db = _db()
    _mjs_mission(db)
    with db.session() as s:
        ev = s.scalar(select(MjsMissionEvent).where(MjsMissionEvent.listing_ref == "1001"))
        inputs, event_id = dict(s.get(Job, ev.tournament_job_id).inputs), ev.id
    assert inputs["seasonal_target"] == "Christmas"

    count = {"n": 0}

    def cardigans(values, _call):
        out = []
        for _ in range(int(values.get("count") or 1)):
            j = count["n"]
            count["n"] += 1
            u = [_unique(j, t) for t in range(4)]
            out.append({
                "title": f"{u[0].title()} Cropped Cardigan",
                "premise": (f"a cropped cardigan with {u[0]} {u[1]} {u[2]} {u[3]} "
                            f"{_unique(j, 5)} {_unique(j, 6)} woodland banding"),
                "construction": ("top_down_yoke", "cable_panel", "bottom_up",
                                 "modular_panels")[j % 4],
                "motif": f"woodland star {u[1]}",
                "palette_story": "forest, cranberry, cream and gold",
                "recipient": RECIPIENTS[j % len(RECIPIENTS)], "occasion": "christmas",
                "feeling": FEELINGS[j % len(FEELINGS)],
                "function": f"a {u[2]} layer for {u[3]} mornings", "wow": "yoke"})
        return {"concepts": out}

    result, _ = _handler(db, "creative.tournament", inputs, generator=cardigans)
    assert result["arena"] == "Christmas/garments", result["arena"]
    t = _rows(db, "creative.tournament")[-1][2]
    rounds = {r["stage"]: r for r in t["rounds"]}
    assert rounds["research"]["survived"] >= 35, rounds["research"]
    assert rounds["proposition"]["causes"].get("no_family"), rounds["proposition"]
    assert "prototype" not in t["stages_run"]
    assert not _jobs(db, "cir.draft")
    with db.session() as s:
        pipe = s.get(MjsMissionEvent, event_id).pipeline
    assert pipe["stopped"]["stage"] == "seasonal_tournament", pipe
    assert "no winner" in pipe["stopped"]["evidence"]


# ---- #293 / #283 at launch: buyer language and skill-aware windows ------------------------


OBSERVED_TITLES = ("Christmas Blanket Crochet Pattern", "Christmas Ornament Crochet Pattern",
                   "Christmas Decor Crochet Pattern", "Christmas Coaster Crochet Pattern",
                   "Christmas Pillow Crochet Pattern", "Christmas Runner Crochet Pattern",
                   "Christmas Stocking Crochet Pattern", "Christmas Garland Crochet Pattern")


def test_launch_path_uses_observed_buyer_language_and_the_patterns_own_skill_293_283():
    """One full shadow release cycle (plan.cycle drained through the worker).

    #293: `listing.seo` maps each product to buyer facets from its own facts and tags the
    phrases buyers were observed using. #283: `launch.plan`'s window decision and the
    seasonal sentinel's war room are planned for the maker the pattern's printed difficulty
    is bought by, with the whole skill distribution recorded."""
    from test_shadow import boot, drain

    from brambleloop.seasonal.leadtime import catalogue_plans

    db = boot()
    with db.session() as s:
        for i, title in enumerate(OBSERVED_TITLES * 2):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"B{i}",
                                   title=title, pod="home_decor", price_cad=7.0))
    JobQueue(db).enqueue("orchestrator", "plan.cycle", {})
    drain(db)
    seo = [d for _i, _a, d in _rows(db, "listing.seo_drafted")]
    assert seo, "no listing reached listing.seo"
    mapped = [d["buyer_language"] for d in seo if (d.get("buyer_language") or {}).get("mapped")]
    assert mapped, [d.get("buyer_language") for d in seo][:2]
    observed_tags = {t for bl in mapped for t in bl["tags"]}
    with db.session() as s:
        tagged = {t for lst in s.scalars(select(Listing)) for t in (lst.tags or [])}
    assert observed_tags and observed_tags <= tagged, (observed_tags, sorted(tagged)[:20])
    assert all(o["competition"] == "UNMEASURED" or isinstance(o["competition"], float)
               for bl in mapped for o in bl["observed"])

    room = catalogue_plans(db)
    assert room["plans"], "no certified seasonal product was scheduled"
    for plan in room["plans"]:
        assert plan["skill"] in ("beginner", "adventurous_beginner", "intermediate")
        assert plan["difficulty"] and len(plan["make_time_by_skill"]) == 4
        assert plan["effective_make_days"] == \
            plan["make_time_by_skill"][plan["skill"]]["effective_make_days"]
    decisions = [d.get("window_decision") for _i, _a, d in _rows(db, "launch.planned")
                 if isinstance(d.get("window_decision"), dict)]
    decisions += [j.outputs.get("window_decision") for j in _jobs(db, "launch.plan")
                  if isinstance((j.outputs or {}).get("window_decision"), dict)]
    seasonal = [w for w in decisions if w.get("make_time_by_skill")]
    assert seasonal, "no launch.plan window decision carried the skill distribution"
    assert all(w["skill"] in ("beginner", "adventurous_beginner", "intermediate")
               for w in seasonal)


if __name__ == "__main__":
    failed = 0
    passed = 0
    only = sys.argv[1:] or None
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn) and (not only or name in only):
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
