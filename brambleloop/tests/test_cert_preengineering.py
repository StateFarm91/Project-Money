"""The pre-engineering gate, the lane router and the tester plan, through the runtime.

The proof-chain audit (2026-09-27, C-41) found #5, #43, #83, #87, #88, #108, #110, #114, #115,
#125 and #126 implemented as tested libraries that nothing on the running path called:
`radar.score` enqueued `cir.draft` on an opportunity score alone. These tests run the
handlers -- `radar.score`, `radar.scan`, `cir.draft`, `creative.grid_tournament` and
`gate.lanes` -- through the worker or the handler registry with a real JobContext, and assert
the gate's effect is persisted and enforced. Every competitor listing and judge score here is
a test fixture; none is an observation or a customer.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, BenchmarkListing, Job, JobStatus, Listing, PatternVersion, PhysicalTest,
)
from brambleloop.creative import preengineering as pe  # noqa: E402
from brambleloop.intel.benchmarks import MJS_KEY  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import JobContext, Worker, handlers  # noqa: E402

TODAY = date(2026, 9, 17)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/pre.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent: str, job_type: str, inputs: dict, key: str = "") -> dict:
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0,
                               idempotency_key=key or f"t:{job_type}:{id(inputs)}")
    assert Worker(db, "pre-test").run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _ctx(db, agent: str, job_type: str, inputs: dict) -> JobContext:
    q = JobQueue(db)
    return JobContext(job=q.enqueue(agent, job_type, inputs), db=db, queue=q,
                      registry=Registry(db), phase=None)


def _actions(db) -> dict[str, list[AuditLog]]:
    out: dict[str, list[AuditLog]] = {}
    with db.session() as s:
        for row in s.scalars(select(AuditLog).order_by(AuditLog.id)):
            out.setdefault(row.action, []).append(row)
    return out


def _jobs(db, job_type: str) -> list[Job]:
    with db.session() as s:
        return [j for j in s.scalars(select(Job)) if j.job_type == job_type]


def _benchmarks(db, pod: str = "stockings", n: int = 6) -> None:
    """Fixture competitor listings: titles readable by the comparables reader, thumbnails
    as URL pointers the grid never fetches."""
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(
                benchmark_key=MJS_KEY, listing_ref=f"fixture-{pod}-{i}",
                title=f"Festive Christmas Stocking Crochet Pattern {i}", pod=pod,
                audit_state="audited",
                detail={"image_urls": [f"https://example.invalid/{pod}/{i}.jpg"]}))


# A concept that clears every deterministic check. The two judged fields are set as a vision
# judge would set them; in production nothing sets them while image_vision is closed.
GOOD = dict(
    key="lantern-pocket-stocking", title="Lantern Pocket Stocking",
    premise=("A stocking whose cuff folds down into a row of lantern-shaped pockets that "
             "glow with contrasting yarn windows"),
    pod="stockings", form="stocking", construction="modular_panels", motif="lantern",
    palette_story="ember windows on pine", recipient="child", occasion="housewarming",
    feeling="celebratory", function="holds small notes and treats in each pocket",
    make_lane="LONG")
GOOD_BRIEF = dict(
    thumbnail_storyboard=("deep green stocking, cuff folded down showing six lantern pockets "
                          "with glowing amber windows"),
    silhouette_qualifiers=["modular_reveal"])


def _judged(**over) -> dict:
    return {**GOOD, "thumbnail_reads_small": True, "craft_impression": 4.2, **over}


# ---- the gate as a library, adversarially -----------------------------------------------


def test_a_radar_slot_is_refused_because_it_is_a_category_not_a_concept():
    v = pe.gate_concept(None, {"slug": "pumpkin-cluster-set", "title": "Pumpkin Cluster Set"},
                        today=TODAY)
    assert v["decision"] == pe.REFUSED and not v["engineer"]
    assert v["failed"] == ["premise_thumbnail"]
    assert "slot" in v["reasons"][0] and "#88" in v["reasons"][0]


def test_unjudged_taste_waits_and_is_never_passed():
    v = pe.gate_concept(None, {"concept": GOOD, "brief": GOOD_BRIEF}, benchmark=[],
                        today=TODAY)
    assert v["decision"] == pe.WAITING and not v["engineer"], v
    assert {"premise_thumbnail", "jury", "novelty", "grid_tournament"} <= set(v["unmeasured"])
    assert "image_vision" in v["waiting_on"]
    assert "Unmeasured is never passing" in v["consequence"]


def test_each_deterministic_check_refuses_on_its_own():
    base = {"concept": _judged(), "brief": dict(GOOD_BRIEF)}

    def gate(concept=None, brief=None, **kw):
        return pe.gate_concept(None, {"concept": {**base["concept"], **(concept or {})},
                                      "brief": {**base["brief"], **(brief or {})}},
                               benchmark=kw.get("benchmark", []), today=TODAY)

    # #88: no storyboard.
    assert "premise_thumbnail" in gate(brief={"thumbnail_storyboard": "a stocking"})["failed"]
    # #108: a generic form with no qualifier.
    v = gate(concept={"form": "round_disc", "construction": "in_the_round"},
             brief={"silhouette_qualifiers": []})
    assert "silhouette" in v["failed"], v["failed"]
    # #110: a Christmas concept built only from the clichés.
    v = gate(concept={"occasion": "christmas", "make_lane": "MEDIUM"},
             brief={"motifs": ["tree", "santa"]})
    assert "motif_grammar" in v["failed"], v["reasons"]
    # ... and one that declares nothing at all.
    v = gate(concept={"occasion": "halloween", "make_lane": "MEDIUM"})
    assert "motif_grammar" in v["failed"]
    # ... while a recombined selection passes that check.
    v = gate(concept={"occasion": "christmas", "make_lane": "MEDIUM"},
             brief={"motifs": ["lantern", "tree"]})
    assert v["checks"]["motif_grammar"]["status"] == pe.PASS
    # #115: a flagship with no WOW mechanism, and one with an ungrounded mechanism.
    assert "wow" in gate(concept={"make_lane": "FLAGSHIP"})["failed"]
    v = gate(concept={"make_lane": "FLAGSHIP"},
             brief={"wow_mechanism": "modular_reveal", "wow_grounding": "wow"})
    assert "wow" in v["failed"]
    # #125: a flagship measured below the category's top decile.
    v = gate(concept={"make_lane": "FLAGSHIP"},
             brief={"wow_mechanism": "modular_reveal",
                    "wow_grounding": "cuff pockets assemble into a lantern street scene",
                    "strength_score": 0.6, "strength_score_source": "fixture judge",
                    "benchmark_scores": [0.4, 0.5, 0.6, 0.7, 0.8, 0.9]})
    assert "top_decile" in v["failed"] and "wow" not in v["failed"], v["reasons"]
    # ... and a score with no named judge is not a measurement.
    v = gate(concept={"make_lane": "FLAGSHIP"},
             brief={"strength_score": 0.99, "benchmark_scores": [0.1] * 6})
    assert v["checks"]["top_decile"]["status"] == pe.UNMEASURED
    # #87: a recolour of our own catalogue.
    from brambleloop.creative.audit import catalogue_concepts

    import dataclasses

    mine = catalogue_concepts()[0]
    recolour = dataclasses.replace(mine, key="recolour", palette_story="different colours")
    v = pe.gate_concept(None, recolour, brief=GOOD_BRIEF, benchmark=[], today=TODAY)
    assert "novelty" in v["failed"], v["checks"]["novelty"]


def test_novelty_refuses_a_concept_indistinguishable_from_an_observed_listing():
    db = _db()
    _benchmarks(db)
    # What the fixture titles state, read the way the comparables reader reads them. The
    # titles say "Christmas"; before C-55 the reader misread that as "everyday".
    twin = _judged(key="their-stocking", recipient="self", occasion="christmas",
                   feeling="festive")
    v = pe.gate_concept(db, {"concept": twin, "brief": GOOD_BRIEF}, today=TODAY)
    assert "novelty" in v["failed"], v["checks"]["novelty"]
    assert v["checks"]["novelty"]["detail"]["benchmark_twin"].startswith("fixture-")
    # With nothing observed, the anti-clone half is unmeasured, not passed.
    v = pe.gate_concept(_db(), {"concept": _judged(), "brief": GOOD_BRIEF}, today=TODAY)
    assert v["checks"]["novelty"]["status"] == pe.UNMEASURED


def test_the_rebuild_exemption_is_a_closed_list():
    assert pe.established(None, "nordic-forest-mosaic-throw")
    assert pe.established(None, "pet-snuggle-mat")
    assert pe.established(None, "pumpkin-cluster-set") is None
    assert pe.established(None, "lantern-pocket-stocking") is None


# ---- radar.score: the gate on the path to engineering ------------------------------------


def test_radar_score_no_longer_engineers_a_slot_on_its_opportunity_score():
    """Pre-repair, pumpkin-cluster-set (0.587, Class B) was promoted straight to cir.draft."""
    db = _db()
    out = _run(db, "market_radar", "radar.score",
               {"slug": "pumpkin-cluster-set", "as_of": TODAY.isoformat()})
    assert out["score"] >= pipeline.PROMOTION_THRESHOLD
    assert out["promoted"] is False and out["gate"]["decision"] == pe.REFUSED
    assert not _jobs(db, "cir.draft"), "a refused concept reached engineering"
    acts = _actions(db)
    assert acts["concept.gate_refused"][0].artifact == "pumpkin-cluster-set"
    assert acts["concept.returned_to_ideation"][0].detail["to"] == "creative development"
    assert acts["concept.autopsy"][0].artifact == "pumpkin-cluster-set"
    assert acts["radar.scored"][-1].detail["gate"] == pe.REFUSED


def test_radar_score_passes_a_catalogue_rebuild_through():
    db = _db()
    out = _run(db, "market_radar", "radar.score",
               {"slug": "nordic-forest-mosaic-throw", "as_of": TODAY.isoformat()})
    assert out["promoted"] is True and out["gate_exempt"]
    assert _jobs(db, "cir.draft")
    assert "concept.gate_exempt" in _actions(db)


def test_radar_score_gates_a_concept_carried_by_the_job():
    db = _db()
    out = _run(db, "market_radar", "radar.score", {
        "slug": "pumpkin-cluster-set", "as_of": TODAY.isoformat(),
        "concept": {**GOOD, "key": "pumpkin-cluster-set"}, "brief": GOOD_BRIEF})
    assert out["promoted"] is False and out["gate"]["decision"] == pe.WAITING
    assert not _jobs(db, "cir.draft")
    assert "concept.gate_waiting" in _actions(db)
    assert "concept.returned_to_ideation" not in _actions(db), \
        "a waiting concept is not a refused one"


# ---- cir.draft: the same gate at the engineering entry ------------------------------------


def test_cir_draft_refuses_a_new_concept_enqueued_directly():
    db = _db()
    out = _run(db, "crochet_engineer", "cir.draft", {"slug": "pumpkin-cluster-set"})
    assert out["drafted"] is False and out["gate"] == pe.REFUSED
    assert not _jobs(db, "cir.compile")
    out = _run(db, "crochet_engineer", "cir.draft",
               {"slug": GOOD["key"], "concept": GOOD, "brief": GOOD_BRIEF}, key="d2")
    assert out["drafted"] is False and out["gate"] == pe.WAITING
    assert not _jobs(db, "cir.compile")


def test_cir_draft_still_rebuilds_an_established_design():
    # PT-11: the coaster is engineered under its Launch-0 slug; the retired concept slug
    # `hexie-coaster-set` is routed to it (tests/test_launch0_listing_truth.py).
    db = _db()
    out = _run(db, "crochet_engineer", "cir.draft", {"slug": "hexagon-coaster-set"})
    assert out.get("engineered") is True
    assert _jobs(db, "cir.compile")


# ---- #126: the grid tournament feeds the gate ---------------------------------------------


def _fixture_judges(monkey_scores: float):
    """Replace the vision panel with fixed fixture judgements. No network, no spend."""
    from brambleloop.creative import blinded

    real = blinded.judge_grid

    def fake(db, grid, **kw):
        cells = {c["cell"] for c in grid["cells"]}
        return {"judgements": {c: {f: monkey_scores for f in blinded.GRID_JUDGE_FIELDS}
                               for c in cells},
                "judges": ["fixture"], "judged_by": ["fixture"], "problems": [],
                "stopped_by": "", "cost_cad": 0.0, "method": "test fixture"}

    blinded.judge_grid = fake
    return lambda: setattr(blinded, "judge_grid", real)


def test_a_waiting_expensive_concept_requests_its_grid_and_passes_only_once_it_clears():
    db = _db()
    _benchmarks(db)
    concept = {"concept": _judged(), "brief": {**GOOD_BRIEF,
                                               "board_image": "file:///boards/lantern.png"}}

    # 1. Everything judged but the grid: waits, and queues the grid as a creative job.
    verdict = pe.gate_concept(db, concept, today=TODAY)
    assert verdict["decision"] == pe.WAITING and verdict["unmeasured"] == ["grid_tournament"]
    ctx = _ctx(db, "market_radar", "radar.score", {})
    effects = pe.record(ctx, verdict, source="test")
    assert effects["grid_requested"] is True
    grid_jobs = _jobs(db, "creative.grid_tournament")
    assert grid_jobs and grid_jobs[0].inputs["concepts"][0]["key"] == GOOD["key"]
    assert grid_jobs[0].agent == "creative_director"

    # 2. The handler grids the board. Judges rank it below the threshold: refused.
    restore = _fixture_judges(0.2)
    try:
        out = _run(db, "creative_director", "creative.grid_tournament",
                   dict(grid_jobs[0].inputs), key="g1")
    finally:
        restore()
    assert out["concepts"][GOOD["key"]] == "fail"
    verdict = pe.gate_concept(db, concept, today=TODAY)
    assert verdict["decision"] == pe.REFUSED and verdict["failed"] == ["grid_tournament"]

    # 3. Judges rank it in the top half on every field: every check measured, passed.
    restore = _fixture_judges(0.8)
    try:
        _run(db, "creative_director", "creative.grid_tournament",
             dict(grid_jobs[0].inputs), key="g2")
    finally:
        restore()
    verdict = pe.gate_concept(db, concept, today=TODAY)
    assert verdict["decision"] == pe.PASSED and verdict["engineer"], verdict["reasons"]


def test_a_grid_that_cannot_be_built_leaves_the_concept_waiting():
    db = _db()
    _benchmarks(db, n=3)            # below MIN_GRID_BENCHMARKS
    out = _run(db, "creative_director", "creative.grid_tournament",
               {"concepts": [{"key": GOOD["key"], "board_image": "file:///b.png",
                              "pod": "stockings"}]})
    assert out["concepts"][GOOD["key"]] == "refused"
    v = pe.gate_concept(db, {"concept": _judged(), "brief": GOOD_BRIEF}, today=TODAY)
    assert v["checks"]["grid_tournament"]["status"] == pe.UNMEASURED
    assert not v["engineer"]


def test_a_passed_concept_enqueued_directly_is_refused_by_the_funnel():
    """C-61 / #3 strengthened this test. It used to assert that a concept which passes every
    gate check is engineered when `cir.draft` is enqueued with it directly. The funnel's
    `may_engineer` now stands at the same entry: a concept reaches engineering only as a
    tournament winner the staged funnel carried to prototype (the positive path is proved
    through `creative.tournament` in test_cert_design_pipeline.py). The gate still runs first
    and passes here -- the refusal names the funnel, not the gate."""
    db = _db()
    _benchmarks(db)
    restore = _fixture_judges(0.8)
    try:
        _run(db, "creative_director", "creative.grid_tournament",
             {"concepts": [{"key": GOOD["key"], "board_image": "file:///b.png",
                            "pod": "stockings"}]})
    finally:
        restore()
    out = _run(db, "crochet_engineer", "cir.draft", {
        "slug": GOOD["key"], "concept": _judged(), "brief": GOOD_BRIEF,
        "title": GOOD["title"], "category": "stocking",
        "stitch_repeat": [["sc", 2], ["dc", 2]], "width_stitches": 40, "rows": 8,
        "colors": {"pine": "#244A3A", "ember": "#C49545"}}, key="pass")
    assert out["drafted"] is False and out["gate"] == "funnel", out
    assert "winner intake" in out["reasons"][0]
    assert not _jobs(db, "cir.compile"), "a concept reached engineering outside the funnel"


def test_the_release_side_grid_verdict_is_recorded_per_product():
    db = _db()
    _run(db, "creative_director", "creative.grid_tournament", {})
    rows = _actions(db)["creative.grid_tournament"]
    products = rows[-1].detail["products"]
    assert "pet-snuggle-mat" in products
    verdict = pe.release_grid_verdict(db, "pet-snuggle-mat")
    assert verdict["cleared"] is False and verdict["why"], verdict


# ---- #114: the wave's skill portfolio -----------------------------------------------------


def test_radar_scan_measures_the_wave_skill_portfolio_and_writes_the_gap_as_a_brief():
    db = _db()
    out = _run(db, "market_radar", "radar.scan", {"as_of": TODAY.isoformat()})
    sp = out["skill_portfolio"]
    acts = _actions(db)
    row = acts["radar.skill_portfolio"][0].detail
    assert set(row["levels"]) == {s for s in out["selected"] if s != "nordic-forest-bundle"}
    if not sp["segmented"]:
        gap = acts["radar.skill_gap"][0].detail
        assert gap["missing"] == sp["missing"] and "brief" in gap


def test_skill_portfolio_flags_a_wave_of_only_flagships():
    from brambleloop.radar.opportunity import POOL

    blankets = [s for s in POOL if s.maker_hours[0] >= 25]
    wave = pe.wave_skill_portfolio(blankets)
    assert not wave["wave"]["segmented"]
    assert "beginner_quick_win" in pe.missing_skill_levels(wave["wave"])


# ---- #5 and #43: gate.lanes over certified releases ---------------------------------------


def _certify(db, slug: str) -> None:
    from brambleloop.runtime.pipeline import _engineered_cir

    cir = _engineered_cir(slug)
    _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, key=f"c:{slug}")


def test_gate_lanes_routes_certified_products_and_plans_their_testing():
    db = _db()
    for slug in ("hexagon-coaster-set", "market-basket-medium", "nordic-forest-mosaic-throw"):
        _certify(db, slug)
    with db.session() as s:
        assert len(list(s.scalars(select(PatternVersion)
                                  .where(PatternVersion.certified.is_(True))))) == 3

    out = handlers.get("gate.lanes")(_ctx(db, "quality_director", "gate.lanes",
                                          {"as_of": TODAY.isoformat()}))
    assert out["products"] == 3
    acts = _actions(db)
    routed = {r.artifact.split("@")[0]: r.detail for r in acts["gate.lane_routed"]}
    assert set(routed) == {"hexagon-coaster-set", "market-basket-medium",
                           "nordic-forest-mosaic-throw"}
    for detail in routed.values():
        assert detail["release"]["ok"] is True, detail["release"]
        assert detail["search_grid"]["cleared"] is False
        if detail["two_queues_open"]:
            # A lane, or neither with both queues' refusals stated.
            assert detail["lane"] in ("fast", "flagship") or (
                detail["fast_refusals"] and detail["flagship_refusals"]), detail
        else:
            assert detail["lane"] is None and detail["why"]
    assert routed["nordic-forest-mosaic-throw"]["profile"]["pod"] == "blankets"

    plan = acts["quality.tester_plan"][0].detail
    assert plan["demands"], "a Class B product needs a sample and was not forecast"
    assert all(d["risk_class"] in ("B", "C") for d in plan["demands"])
    assert plan["unassigned"] and not plan["assignments"], \
        "nobody is recorded as a tester, so nothing can be assigned"


def test_gate_lanes_assigns_a_qualified_tester_and_never_outside_a_specialty():
    db = _db()
    _certify(db, "market-basket-medium")
    _certify(db, "hexagon-coaster-set")
    with db.session() as s:
        # Fixture testers: one who has tested a coaster (kitchen_bath) twice.
        for i in range(2):
            s.add(PhysicalTest(product_slug="hexagon-coaster-set", version="1.0.0",
                               tester_ref="fixture-tester-a", passed=True))
    handlers.get("gate.lanes")(_ctx(db, "quality_director", "gate.lanes",
                                    {"as_of": TODAY.isoformat()}))
    plan = _actions(db)["quality.tester_plan"][0].detail
    basket = next(d for d in plan["demands"] if d["product_slug"] == "market-basket-medium")
    assigned = {a["product_slug"] for a in plan["assignments"]}
    if basket["specialty"] != "kitchen_bath":
        assert "market-basket-medium" not in assigned, "assigned outside the tester's specialty"
        assert any(u["product_slug"] == "market-basket-medium" for u in plan["unassigned"])


def test_gate_lanes_withdraws_a_release_that_skipped_an_owed_gate():
    db = _db()
    _certify(db, "hexagon-coaster-set")
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        cert = dict(pv.certificate)
        cert["stages_run"] = [x for x in cert["stages_run"] if x != "reverse"]
        pv.certificate = cert
        s.add(Listing(product_slug="hexagon-coaster-set", version=pv.version, title="t",
                      description="", tags=[], price_cad=4.5))
    out = handlers.get("gate.lanes")(_ctx(db, "quality_director", "gate.lanes",
                                          {"as_of": TODAY.isoformat()}))
    assert out["release_refused"] == ["hexagon-coaster-set"]
    assert "reverse" in _actions(db)["gate.lane_release_refused"][0].detail["why"]
    with db.session() as s:
        states = {row.state for row in s.scalars(select(Listing))}
    assert states == {"withdrawn"}


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
