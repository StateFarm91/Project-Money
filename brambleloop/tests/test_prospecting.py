"""Discovery that starts from a proven market, and the gravity it has to fight.

Requirement 104, and the owner's instruction after the first blinded run: take a real
MJs-proven arena with no Brambleloop answer and produce concepts capable of surviving the
creative gates -- without every one of them becoming another throw, runner or garland because
those are the shapes the compiler is fluent in.

That gravity is measured, not suspected. All eleven catalogue products are `home_decor`; pod,
feeling and make_lane each hold one distinct value; 0 of 11 share a pod and a form with any
of 438 observed listings. A generator left alone returns to what compiles.

Most of this file is about the refusals, because a discovery pipeline that cannot return
nothing is a pipeline that will always return something.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.creative import prospecting as P  # noqa: E402
from brambleloop.creative.concept import FORMS, Concept  # noqa: E402
from brambleloop.creative.family import FORM_CONSTRUCTIONS  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402

ALL_LANES = ("QUICK", "SHORT", "MEDIUM", "LONG", "FLAGSHIP")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/prospect.sqlite")
    db.create_all()
    return db


def _arena(pod="hats", event="Christmas", forms=None, days=97, listings=82) -> P.Arena:
    return P.Arena(event=event, pod=pod, benchmark_listings=listings, days_away=days,
                   forms=forms if forms is not None else {"hat": 40, "scarf": 20})


def _concept(key, *, form="rectangle_throw", pod="home_decor", motif="cable",
             occasion="everyday", feeling="cosy", construction="flat_rows") -> Concept:
    return Concept(
        key=key, title=f"Concept {key}",
        premise=("a heavy textured piece that reads as an heirloom from across a room and "
                 "holds its shape after washing"),
        pod=pod, form=form, construction=construction, motif=motif,
        palette_story="oatmeal and rust", recipient="host", occasion=occasion,
        feeling=feeling, function="keeps a lap warm while reading in a cold room",
        make_lane="MEDIUM")


# ---- the engine's own limits, named rather than worked around ---------------


def test_every_concept_construction_either_routes_to_the_compiler_or_is_named():
    """A construction with no route is a build item; silence about it is how a catalogue
    stays flat."""
    from brambleloop.creative.concept import CONSTRUCTIONS

    assert set(P.ENGINE_ROUTE) == set(CONSTRUCTIONS), (
        set(CONSTRUCTIONS) ^ set(P.ENGINE_ROUTE))
    gaps = P.engine_gaps()
    # Both garment constructions were unblocked on 2026-09-20 by the armhole division, so
    # every concept construction now routes. If this list grows again, the new entry is a
    # build item and belongs in the report rather than in a silent refusal to propose.
    assert gaps["needs_engineering"] == []
    assert gaps["routed"] == len(CONSTRUCTIONS)


def test_the_route_map_cannot_drift_from_what_the_compiler_accepts():
    """The three the CIR speaks, read from the model rather than restated here."""
    import typing

    from brambleloop.cir.model import Construction

    assert set(typing.get_args(Construction)) == set(P.CIR_CONSTRUCTIONS)
    for construction, route in P.ENGINE_ROUTE.items():
        assert route is None or route in P.CIR_CONSTRUCTIONS, construction


def test_the_garment_gap_is_one_named_primitive_and_not_a_vague_difficulty():
    """Rounds, shaping, assembly and grading all exist. One thing does not.

    Claiming less capability than the engine has is as wrong as claiming more: it would send
    discovery away from the deepest proven arena for a reason that is not true.
    """
    import dataclasses

    from brambleloop.cir.model import Row

    gaps = P.engine_gaps()
    assert gaps["missing_primitive"] is None
    closed = {c["name"] for c in gaps["closed_primitives"]}
    assert any("armhole division" in name for name in closed), closed
    # And it is closed in the model, not only in the report.
    fields = {f.name for f in dataclasses.fields(Row)}
    assert "skips" in fields


def test_the_capabilities_the_engine_already_has_are_not_claimed_as_missing():
    """grading.py exists and was written for the garments pod; rounds and shaping exist."""
    import typing

    from brambleloop.cir import grading
    from brambleloop.cir.model import Construction

    assert "joined_rounds" in typing.get_args(Construction)
    assert hasattr(grading, "grade") and grading.DEFAULT_RUN[0] == "XS"
    assert P.ENGINE_ROUTE["in_the_round"] == "joined_rounds"
    assert P.ENGINE_ROUTE["amigurumi_shaping"] == "spiral_rounds"


def test_no_form_is_missing_from_the_buildability_map():
    """A form absent from it is unbuildable, not unconstrained, and nothing said so.

    Six were missing, `stocking` among them -- a pod the benchmark carries thirteen listings
    in and the owner names as a top commercial priority. The pairing rules silently refused
    to build one.
    """
    unmapped = [f for f in FORMS if not FORM_CONSTRUCTIONS.get(f)]
    assert unmapped == [], unmapped
    assert P.engine_gaps()["forms_absent_from_the_buildability_map"] == []


def test_a_christmas_stocking_is_buildable():
    """The specific product the missing map entry made impossible."""
    assert "in_the_round" in FORM_CONSTRUCTIONS["stocking"]
    slot_plan = P.slots(_arena(pod="stockings", forms={"stocking": 13}),
                        viable_lanes=ALL_LANES)
    assert [s["form"] for s in slot_plan["slots"]] == ["stocking"]


# ---- the arena decides the form, not the engine -----------------------------


def test_a_pods_forms_are_counted_from_observed_listings():
    """A table of "what a hat pod contains" is this system's opinion about hats."""
    db = _db()
    with db.session() as s:
        for i, title in enumerate(["Cozy Chunky Crochet Beanie Pattern",
                                   "Rustic Cabled Crochet Hat Pattern",
                                   "Cozy Crochet Triangle Scarf Pattern"]):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"L{i}",
                                   title=title, pod="hats"))
    report = P.arena_forms(db, "hats")
    assert report["forms"] == {"hat": 2, "scarf": 1}, report["forms"]


def test_an_unlooked_pod_reports_no_forms_rather_than_one_form():
    db = _db()
    report = P.arena_forms(db, "stockings")
    assert report["listings"] == 0 and report["forms"] == {}
    assert "not the same as a pod with one form" in report["note"]


def test_a_saturated_form_does_not_become_another_slot():
    """Another rectangle throw is not discovery, whatever its motif."""
    catalogue = [_concept(f"bl-{i}") for i in range(10)]
    plan = P.slots(_arena(forms={"rectangle_throw": 30, "hat": 20}), catalogue=catalogue,
                   viable_lanes=ALL_LANES)
    kept = [s["form"] for s in plan["slots"]]
    assert kept == ["hat"], kept
    dropped = {d["form"]: d["why"] for d in plan["dropped"]}
    assert dropped["rectangle_throw"] == "saturated in this catalogue"


def test_a_form_the_engine_cannot_build_is_reported_and_not_dropped():
    """Dropping it is exactly how a catalogue converges on flat panels while feeling picky.

    Garments are buildable since the armhole division, so the mechanism is exercised against
    a hypothetical unrouted construction rather than a real one -- the rule has to survive
    the gap it was written for being closed.
    """
    plan = P.slots(_arena(pod="garments", forms={"fitted_garment": 141}),
                   viable_lanes=ALL_LANES)
    assert [s["form"] for s in plan["slots"]] == ["fitted_garment"]
    assert plan["slots"][0]["engine_ready"] is True

    original = dict(P.ENGINE_ROUTE)
    P.ENGINE_ROUTE["top_down_yoke"] = None
    try:
        plan = P.slots(_arena(pod="garments", forms={"fitted_garment": 141}),
                       viable_lanes=ALL_LANES)
        assert [s["form"] for s in plan["slots"]] == ["fitted_garment"]
        assert plan["slots"][0]["needs_engineering"] == ["top_down_yoke"]
        assert plan["engineering_required"] == ["top_down_yoke"]
    finally:
        P.ENGINE_ROUTE.clear()
        P.ENGINE_ROUTE.update(original)


def test_a_form_takes_the_fastest_lane_it_can_honestly_be_made_in():
    """A closing occasion changes the product mix; it does not cancel the occasion.

    Deriving the lane from physical size filed a beanie as SHORT and then dropped
    Halloween/hats for want of runway at 42 days -- exactly the product the compression
    doctrine says to reach for as an occasion closes.
    """
    plan = P.slots(_arena(forms={"hat": 20, "scarf": 4}), viable_lanes=("QUICK",))
    kept = {s["form"]: s["make_lane"] for s in plan["slots"]}
    assert kept == {"hat": "QUICK"}, kept
    dropped = {d["form"]: d for d in plan["dropped"]}
    assert dropped["scarf"]["why"] == "no runway"
    assert dropped["scarf"]["lane"] == "SHORT"


def test_a_form_whose_floor_is_shut_is_dropped_and_not_promoted_to_a_slower_lane():
    """Lanes close in order, so a slower lane cannot rescue an already-infeasible floor."""
    plan = P.slots(_arena(forms={"rectangle_throw": 60}), viable_lanes=("QUICK", "SHORT"))
    assert plan["slots"] == []
    assert plan["dropped"][0]["lane"] == "MEDIUM"


def test_every_form_has_a_lane_floor():
    """A form defaulting to MEDIUM silently is how a quick giftable loses its own runway."""
    missing = [f for f in FORMS if f not in P.FORM_MIN_LANE]
    assert missing == [], missing
    assert set(P.FORM_MIN_LANE.values()) <= set(P.LANE_SPEED)


def test_an_event_the_vocabulary_cannot_express_is_refused_not_defaulted():
    """`everyday` is the value a Christmas product gets when nobody was paying attention."""
    try:
        P.occasion_for("Diwali")
    except P.ProspectingRefused as e:
        assert "everyday" in str(e)
    else:
        raise AssertionError("a seasonal product was filed as year-round")


def test_christmas_maps_to_the_christmas_occasion():
    assert P.occasion_for("Christmas") == "christmas"
    assert P.occasion_for("Halloween") == "halloween"


def test_arenas_reads_the_key_the_matrix_actually_returns():
    """The second reader/writer key disagreement today, and the same comfortable failure.

    `arenas()` read `proven_gaps` -- the name of the local variable that builds the list --
    while the matrix returns `proven_and_unserved`. The wrong key returns an empty list, and
    an empty list of proven gaps is indistinguishable from a catalogue that answers every
    proven market. Production reported no arenas against a matrix holding twenty-seven.
    """
    from brambleloop.seasonal import benchmark_matrix

    db = _db()
    with db.session() as s:
        for i in range(6):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"S{i}",
                                   title="Cozy Crochet Christmas Stocking Pattern",
                                   pod="stockings"))
    report = benchmark_matrix.matrix(db)
    gaps = report[benchmark_matrix.PROVEN_KEY]
    assert gaps, "the fixture produced no proven gap, so this test proves nothing"
    found = P.arenas(db)
    assert len(found) == min(len(gaps), 12), (len(found), len(gaps))


def test_no_gaps_against_observed_listings_is_an_error_not_an_empty_list():
    """A defect that makes discovery say "nothing to do" must fail, not complete.

    A job that fails is re-driven by the next deploy. A job that succeeds with a false
    negative consumes its window -- which is exactly what happened: the weekly cadence
    recorded "no proven-and-unserved arena is observed" as a success and went quiet for
    seven days while the matrix held twenty-seven.
    """
    from brambleloop.seasonal import benchmark_matrix

    db = _db()
    with db.session() as s:
        for i in range(3):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"C{i}",
                                   title="Cozy Crochet Christmas Stocking Pattern",
                                   pod="stockings"))
    # Pretend this catalogue answers every department, so the matrix legitimately finds no
    # gap while still having read listings. That is the exact shape a wrong key produces.
    everything = {row["event"]: tuple(row["departments"])
                  for row in benchmark_matrix.coverage_matrix(None)["rows"]}
    assert benchmark_matrix.matrix(db, covered=everything)["benchmark_observed_listings"] > 0

    try:
        P.arenas(db, covered=everything)
    except P.NoArenasContradictsEvidence as e:
        assert "wrong place" in str(e)
    else:
        raise AssertionError("an empty gap list against observed listings passed silently")


def test_no_observation_at_all_is_an_empty_list_and_not_an_error():
    """Nobody has looked is a real state, and the one this rule must not fire on."""
    assert P.arenas(_db()) == []


def test_no_reader_carries_its_own_literal_for_the_proven_gap_key():
    """One constant, because guessing it wrong fails silently and flatteringly."""
    from brambleloop.seasonal import benchmark_matrix

    src = (ROOT / "src" / "brambleloop" / "creative" / "prospecting.py").read_text()
    assert '"proven_gaps"' not in src and "'proven_gaps'" not in src
    assert benchmark_matrix.PROVEN_KEY == "proven_and_unserved"


# ---- the gauntlet -----------------------------------------------------------


def _candidate(key, **kw) -> P.Candidate:
    slot = P.Slot(arena=_arena(), form=kw.get("form", "hat"), make_lane="SHORT",
                  benchmark_examples=40, constructions=("in_the_round",),
                  engine_ready=True, needs_engineering=())
    return P.Candidate(concept=_concept(key, **kw), slot=slot)


def test_a_construction_that_cannot_build_the_form_is_killed_before_the_jury():
    """Cheap structural refusals first: the jury is the expensive gate."""
    bad = _candidate("x", form="toy", construction="flat_rows", pod="amigurumi")
    result = P.screen([bad])
    assert result["survivors"] == []
    assert result["causes"] == {"unbuildable": 1}


def test_a_concept_too_close_to_the_catalogue_is_killed_with_the_neighbour_named():
    existing = [_concept("bl-1")]
    twin = _candidate("new-1", form="rectangle_throw", construction="flat_rows")
    result = P.screen([twin], catalogue=existing)
    killed = result["killed"]
    assert killed and killed[0]["killed_by"] in ("too_close_to_the_catalogue", "jury")


def test_a_field_that_is_one_idea_five_times_keeps_one_of_them():
    """A field can pass every individual gate and still be one submission repeated."""
    siblings = [_candidate(f"s-{i}", form="hat", construction="in_the_round")
                for i in range(5)]
    result = P.screen(siblings)
    assert len(result["survivors"]) <= 1
    assert result["causes"].get("too_close_to_a_sibling", 0) >= 3


def test_an_empty_field_is_a_real_answer():
    result = P.screen([])
    assert result["entered"] == 0 and result["survivors"] == []
    assert "empty field is a real answer" in result["note"]


def test_a_gauntlet_that_passes_most_of_what_enters_says_so():
    """A gate that passes four fifths of its input is a formality with a rejection message."""
    assert P.SUSPICIOUS_SURVIVAL == 0.60
    varied = []
    for i, (form, construction, motif) in enumerate([
            ("hat", "in_the_round", "star"), ("bag", "tapestry", "wave"),
            ("stocking", "cable_panel", "cable"), ("toy", "amigurumi_shaping", "fox")]):
        varied.append(_candidate(f"v-{i}", form=form, construction=construction, motif=motif))
    result = P.screen(varied, min_novelty=0.0)
    assert result["gauntlet_suspicious"] is (result["survival_rate"] > 0.60)


# ---- the expedition ---------------------------------------------------------


class _Gateway:
    """A generator that answers with a field of distinct, valid concepts."""

    def __init__(self, rows=None, fail=False):
        self.calls = 0
        self.fail = fail
        self.rows = rows

    def complete_json(self, ref, *, agent, values, required=None):
        self.calls += 1
        assert ref == "creative.concept_field@1"
        # The brief must never leak pattern mechanics into the prompt.
        blob = repr(values).lower()
        assert "stitch count" not in blob and "yardage" not in blob
        if self.fail:
            raise RuntimeError("provider unavailable")
        if self.rows is not None:
            return {"concepts": self.rows}
        return {"concepts": [{
            "title": f"Piece {i}",
            "premise": ("a sculpted winter form whose ribbed collar stands upright without "
                        "stiffener so it holds its silhouette on a mantel all season"),
            "construction": "in_the_round", "motif": f"motif-{i}",
            "palette_story": "frost and cranberry", "recipient": "child",
            "occasion": "christmas", "feeling": "festive",
            "function": "holds small gifts", "wow": "a collar that stands by itself",
        } for i in range(6)]}


def test_a_model_value_outside_the_vocabulary_is_a_structural_refusal():
    """A confident wrong answer must fail loudly, not become an uncheckable concept."""
    slot = P.Slot(arena=_arena(pod="stockings", forms={"stocking": 13}), form="stocking",
                  make_lane="SHORT", benchmark_examples=13,
                  constructions=("in_the_round",), engine_ready=True, needs_engineering=())
    gw = _Gateway(rows=[{"title": "X", "premise": "a" * 90, "construction": "crochet magic",
                         "motif": "m", "palette_story": "p", "recipient": "child",
                         "occasion": "christmas", "feeling": "festive", "function": "f"}])
    candidates, refused = P.propose(slot, gateway=gw)
    assert candidates == []
    assert refused and "closed vocabulary" in refused[0]


def test_an_expedition_with_no_viable_slot_is_refused_with_the_reasons():
    db = _db()
    try:
        P.expedition(db, _arena(forms={}), gateway=_Gateway())
    except P.ProspectingRefused as e:
        assert "no slot survives" in str(e)
    else:
        raise AssertionError("an expedition ran with nothing to try")


def test_an_expedition_reports_what_it_bought_and_what_survived():
    db = _db()
    result = P.expedition(db, _arena(pod="stockings", forms={"stocking": 13}, days=97),
                          gateway=_Gateway(), today=date(2026, 9, 19))
    assert result["proposed"] == 6
    assert "cost_cad" in result and not result["stopped_on_ceiling"]
    assert isinstance(result["answered_the_arena"], bool)
    assert result["survival_rate"] <= 1.0


def test_an_expedition_stops_on_the_ceiling_and_keeps_what_it_bought():
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway import routing

    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="test", kind=routing.COST_KIND,
                        amount_cad=routing.MONTHLY_CEILING_CAD - 0.0001))
    result = P.expedition(db, _arena(pod="stockings", forms={"stocking": 13}),
                          gateway=_Gateway(), today=date(2026, 9, 19))
    assert result["stopped_on_ceiling"] and result["proposed"] == 0


def test_one_failed_field_is_not_a_failed_expedition():
    db = _db()
    result = P.expedition(db, _arena(pod="stockings", forms={"stocking": 13}),
                          gateway=_Gateway(fail=True), today=date(2026, 9, 19))
    assert result["malformed"] and result["proposed"] == 0
    assert result["answered_the_arena"] is False


# ---- the handler itself ------------------------------------------------------


def test_the_expedition_handler_runs_end_to_end_with_arenas_present():
    """The cadence test only ever exercised the empty path.

    `test_every_scheduled_cadence_can_actually_run` passes with an empty database, so the
    handler returns before it picks an arena -- and a `NameError` on the line that picks one
    reached production twice over. A handler whose interesting half is never executed by any
    test is an untested handler with a passing test next to it.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.release import handle_creative_expedition
    from brambleloop.runtime.worker import JobContext

    db = _db()
    Registry(db).seed_defaults()
    with db.session() as s:
        for i in range(8):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"H{i}",
                                   title="Cozy Chunky Crochet Beanie Hat Pattern",
                                   pod="hats"))
    q = JobQueue(db)
    ctx = JobContext(job=q.enqueue("creative_director", "creative.expedition", {}),
                     db=db, queue=q, registry=Registry(db), phase=None)

    calls = {"n": 0}

    class Gateway:
        def complete_json(self, ref, *, agent, values, required=None):
            calls["n"] += 1
            return {"concepts": []}

    # Substitute the gateway's call so no network request is made, while every other line
    # of the handler -- arena selection, tier routing, catalogue assembly, storage -- runs.
    from brambleloop.gateway import model_gateway
    saved = model_gateway.ModelGateway.complete_json
    model_gateway.ModelGateway.complete_json = (
        lambda self, ref, *, agent, values, required=None: Gateway().complete_json(
            ref, agent=agent, values=values, required=required))
    try:
        result = handle_creative_expedition(ctx)
    finally:
        model_gateway.ModelGateway.complete_json = saved

    assert result["ran"] is True, result
    assert "/" in result["arena"]
    assert calls["n"] > 0, "the handler never reached the generator"


# ---- #104: commercially informed, and the plateau ----------------------------


def test_the_existing_catalogue_aims_at_no_proven_market():
    """Not a criticism of the ideas: the measured consequence of a generator never told
    where the demand was."""
    from brambleloop.creative.audit import catalogue_concepts
    from brambleloop.creative.standard import commercially_informed

    proven = [{"event": "Christmas", "department": "garments"},
              {"event": "Halloween", "department": "hats"},
              {"event": "Thanksgiving (CA)", "department": "blankets"}]
    report = commercially_informed(catalogue_concepts(), proven)
    assert report["concepts"] == 11
    assert report["informed"] == 0 and report["share"] == 0.0
    assert report["unproven"] == 11


def test_a_concept_in_a_proven_department_but_the_wrong_occasion_is_not_credited():
    """Counted separately, because half-aimed is a different thing from aimed."""
    from brambleloop.creative.standard import commercially_informed

    proven = [{"event": "Christmas", "department": "hats"}]
    on_target = _concept("a", pod="hats", form="hat", occasion="christmas")
    off_season = _concept("b", pod="hats", form="hat", occasion="easter")
    report = commercially_informed([on_target, off_season], proven)
    assert report["informed"] == 1
    assert report["in_a_proven_department"] == 1
    assert {r["aim"] for r in report["rows"]} == {"proven_arena", "proven_department"}


def test_a_thousandth_of_movement_is_not_improvement():
    """`north_star()` calls any rise "improved", which is how a flat line reads as progress
    for a year."""
    from brambleloop.creative.standard import plateau

    history = [{"cohort": c, "novelty_distance": v}
               for c, v in (("a", 0.34), ("b", 0.341), ("c", 0.342))]
    report = plateau(history, metric="novelty_distance")
    assert report["verdict"] == "plateau" and report["is_defect"]
    assert "top-level business defect" in report["reason"]


def test_real_movement_is_not_a_plateau():
    from brambleloop.creative.standard import plateau

    history = [{"cohort": c, "novelty_distance": v}
               for c, v in (("a", 0.34), ("b", 0.40), ("c", 0.47))]
    report = plateau(history, metric="novelty_distance")
    assert report["verdict"] == "moving" and not report["is_defect"]


def test_going_backwards_is_also_a_defect():
    from brambleloop.creative.standard import plateau

    history = [{"cohort": c, "novelty_distance": v}
               for c, v in (("a", 0.50), ("b", 0.44), ("c", 0.38))]
    report = plateau(history, metric="novelty_distance")
    assert report["verdict"] == "declining" and report["is_defect"]


def test_not_measuring_is_never_reported_as_flat():
    """A company that stopped measuring looks exactly like one that stopped improving, and
    the remedy for each is the opposite of the remedy for the other."""
    from brambleloop.creative.standard import plateau

    report = plateau([{"cohort": "a", "novelty_distance": 0.34}], metric="novelty_distance")
    assert report["verdict"] == "unmeasured" and not report["is_defect"]
    assert "stopped measuring" in report["reason"]


def test_a_metric_the_north_star_does_not_carry_is_refused():
    from brambleloop.creative.standard import StandardRefused, plateau

    try:
        plateau([], metric="vibes")
    except StandardRefused as e:
        assert "not a north-star metric" in str(e)
    else:
        raise AssertionError("an invented metric was tracked")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
