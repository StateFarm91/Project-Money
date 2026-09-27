"""Certification: the ideation handlers consume every ideation input at runtime.

Requirements 85, 101, 105, 117, 118, 119, 120, 121, 122, 124, 142, 232. The proof-chain audit
found each of these as a tested library that `creative.tournament` and `creative.expedition`
never called. These tests run the handlers themselves -- through the handler registry, with a
real JobContext and a real queue -- with only the model call substituted, and assert on the
audit row and on what the model was actually asked. Against the pre-repair handlers every one
of them fails: there was no `ideation` block, no brief carried a cell, and nothing was cut.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, BenchmarkListing, SerpSnapshot,  # noqa: E402
                                     SupportCase)
from brambleloop.intel import benchmarks  # noqa: E402

MOTIFS = ("lantern", "acorn", "moth", "ember", "thistle", "shutter",
          "keyhole", "pinecone", "chimney", "birch", "hearth", "harvest")
RECIPIENTS = ("child", "teacher", "host", "grandparent")


def _db(listings=8, forms_titles=("Cozy Chunky Crochet Beanie Hat Pattern",)) -> Database:
    from brambleloop.agents.registry import Registry

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/ideation.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        n = 0
        for title in forms_titles:
            for _ in range(listings):
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,
                                       listing_ref=f"H{n}", title=title, pod="hats"))
                n += 1
    return db


def _run(db, job_type: str, *, generator=None, inputs=None):
    """Enqueue, then dispatch through the handler registry with a real JobContext."""
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import model_gateway
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import release  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import JobContext, handlers

    q = JobQueue(db)
    ctx = JobContext(job=q.enqueue("creative_director", job_type, inputs or {}), db=db, queue=q,
                     registry=Registry(db), phase=None)
    handler = handlers.get(job_type)
    assert handler is not None, f"{job_type} has no registered handler"
    saved = model_gateway.ModelGateway.complete_json
    asked: list[dict] = []

    def fake(self, ref, *, agent, values, required=None):
        asked.append(dict(values))
        if generator is not None:
            return generator(values, len(asked))
        want = int(values.get("count") or 1)
        return {"concepts": [{
            "title": f"{MOTIFS[i % len(MOTIFS)].title()} Brim Beanie {len(asked)}-{i}",
            "premise": (f"a beanie whose folded brim stands proud of the crown so the "
                        f"silhouette reads as a {MOTIFS[i % len(MOTIFS)]} from across a "
                        f"room"),
            "construction": "in_the_round", "motif": MOTIFS[i % len(MOTIFS)],
            "palette_story": "ember and soot",
            "recipient": RECIPIENTS[i % len(RECIPIENTS)],
            "occasion": "christmas", "feeling": "folkloric",
            "function": "keeps a child warm and findable after dark",
            "wow": "a brim engineered to hold its own shape"} for i in range(want)]}

    model_gateway.ModelGateway.complete_json = fake
    try:
        result = handler(ctx)
    finally:
        model_gateway.ModelGateway.complete_json = saved
    return result, asked


def _rows(db, action):
    with db.session() as s:
        return [(r.id, r.artifact, dict(r.detail or {})) for r in
                s.scalars(select(AuditLog).where(AuditLog.action == action)
                          .order_by(AuditLog.id))]


def _ideation(db, action="creative.tournament"):
    rows = _rows(db, action)
    assert rows, f"no {action} row was written"
    block = rows[-1][2].get("ideation")
    assert block, f"the {action} row carries no ideation block: {sorted(rows[-1][2])}"
    return block


# ---- #85 / #101: lessons reach the generator ---------------------------------


def test_the_tournament_reads_lessons_and_sends_them_to_the_model():
    from brambleloop.improve.bus import publish

    db = _db()
    statement = ("concepts whose brims fold twice were killed as sameness three times, so "
                 "the next hat field must vary the crown instead")
    lesson_id = publish(db, origin_cell="product_creativity", subject="creative_rejection",
                        statement=statement, evidence_ref="test:autopsy:1")
    result, asked = _run(db, "creative.tournament")
    assert result["ran"] is True, result
    block = _ideation(db)
    assert lesson_id in block["lessons"]["lesson_ids"], block["lessons"]
    assert asked and all(statement[:60] in a["brief"] for a in asked), \
        "the lesson never reached the model's brief"
    # #101: the design's provenance names the lesson it drew on.
    prov = [d for _i, art, d in _rows(db, "design.provenance")
            if art.startswith("ideation:tournament:")]
    assert prov and lesson_id in prov[-1]["lesson_ids"], prov


def test_with_no_lessons_the_run_says_it_starts_from_nothing_rather_than_inventing_one():
    db = _db()
    _run(db, "creative.expedition")
    block = _ideation(db, "creative.expedition")
    assert block["lessons"]["lesson_ids"] == []
    assert "no lesson recorded" in block["lessons"]["state"]


# ---- #105 / #142 / #122 / #121: the briefs are cells, themes, occasions, programmes ----


def test_every_model_call_is_briefed_against_a_universe_cell_theme_and_occasion():
    from brambleloop.creative import universe
    from brambleloop.culture.translate import THEMES

    db = _db()
    _, asked = _run(db, "creative.tournament")
    block = _ideation(db)
    assert block["calls_briefed"] == len(asked) > 0
    assert block["cells_briefed"], "no universe cell was briefed"
    valid = {f'christmas|{c["department"]}|{c["context"]}' for c in universe.cells("christmas")}
    assert set(block["cells_briefed"]) <= valid
    # A hats arena answers the wearable department, not a keyword.
    assert all(c.split("|")[1] == "wearable" for c in block["cells_briefed"])
    assert set(block["themes_briefed"]) <= set(THEMES) and block["themes_briefed"]
    assert set(block["occasions_briefed"]) <= set(universe.NON_HOLIDAY_OCCASIONS)
    assert block["occasions_briefed"]
    assert block["four_season"]["program"] in universe.PROGRAM_MEANING
    for a in asked:
        assert "universe cell:" in a["brief"] and "franchise-free territory:" in a["brief"]
        assert "season programme:" in a["brief"] and "gift (" in a["brief"]


def test_the_next_run_briefs_cells_the_last_one_did_not():
    db = _db()
    _run(db, "creative.expedition")
    first = set(_ideation(db, "creative.expedition")["cells_briefed"])
    _run(db, "creative.expedition")
    second = set(_ideation(db, "creative.expedition")["cells_briefed"])
    assert first and second and not (first & second), (first, second)


def test_the_four_season_agent_writes_the_programme_ideation_then_reads():
    db = _db()
    result, _ = _run(db, "creative.four_season")
    assert result["ran"] is True and result["program"]
    rows = _rows(db, "creative.four_season")
    assert len(rows) == 1 and rows[0][2]["occasion"]
    assert rows[0][2]["holiday_independent_share"] is not None
    _run(db, "creative.tournament")
    block = _ideation(db)
    assert block["four_season"]["source"] == f"creative.four_season row {rows[0][0]}"
    assert block["four_season"]["program"] == rows[0][2]["program"]


# ---- #117 / #118: saturation is measured and enforced -------------------------


def _crowd_hats(db, n=900):
    with db.session() as s:
        s.add(SerpSnapshot(query="christmas crochet hat pattern", total_count=n))


def test_a_crowded_form_with_no_angle_is_never_generated():
    db = _db(forms_titles=("Cozy Chunky Crochet Beanie Hat Pattern",
                           "Chunky Crochet Scarf Pattern"))
    _crowd_hats(db)
    _run(db, "creative.expedition")
    block = _ideation(db, "creative.expedition")
    sat = block["saturation"]
    assert "hat" in sat["excluded_forms"], sat
    assert sat["decisions"]["hat"]["may_enter"] is False
    assert all(b["form"] != "hat" for b in block["briefs_sent"]), \
        "a saturated form with no unmet angle reached the generator"


def test_a_saturated_arena_moves_the_run_to_less_saturated_territory():
    db = _db()
    _crowd_hats(db)
    _run(db, "creative.tournament")
    rows = _rows(db, "creative.tournament") or _rows(db, "creative.tournament_blocked")
    block = rows[-1][2]["ideation"]
    assert block["moved_from"][0]["arena"] == "Christmas/hats", block.get("moved_from")
    assert block["event"] != "Christmas"


def test_every_arena_saturated_blocks_visibly_and_asks_the_model_nothing():
    db = _db()
    with db.session() as s:
        for word in ("christmas", "halloween", "easter", "valentine", "thanksgiving",
                     "mother", "father", "back"):
            s.add(SerpSnapshot(query=f"{word} crochet hat pattern", total_count=900))
    result, asked = _run(db, "creative.tournament")
    assert result["ran"] is False and "saturated" in result["reason"], result
    assert asked == []
    assert _rows(db, "creative.tournament_blocked"), "the block left no audit row"


def test_the_white_space_agent_mines_complaints_and_its_angle_unlocks_the_crowded_form():
    db = _db()
    _crowd_hats(db)
    with db.session() as s:
        s.add(SupportCase(customer_ref="fixture-1",
                          question="there are so many pieces to sew together on this"))
        s.add(SupportCase(customer_ref="fixture-2",
                          question="too many seams, the sewing took longer than the hat"))
    ws, _ = _run(db, "creative.white_space")
    assert ws["minable"] is True and ws["strongest"] == "excessive_sewing", ws
    result, asked = _run(db, "creative.tournament")
    assert result["ran"] is True, result
    block = _ideation(db)
    assert block["white_space"]["source"].startswith("creative.white_space row")
    decision = block["saturation"]["decisions"]["hat"]
    assert decision["may_enter"] is True and decision["angle_kind"] == "construction_fix"
    assert all("enter only on this angle" in a["brief"] for a in asked)
    assert all("buyers say:" in a["brief"] for a in asked)


def test_the_white_space_agent_with_nothing_recorded_proposes_nothing():
    db = _db()
    ws, _ = _run(db, "creative.white_space")
    assert ws["minable"] is False and ws["hypotheses"] == 0
    assert "nothing to mine" in ws["reason"]


def test_an_unmeasured_form_is_reported_unmeasured_not_open():
    db = _db()
    _run(db, "creative.expedition")
    sat = _ideation(db, "creative.expedition")["saturation"]
    assert sat["unmeasured"] == ["hat"] and sat["measured"] == [] and not sat["excluded_forms"]


# ---- #119: per-axis quotas ------------------------------------------------------


def _cand(key, **kw):
    from brambleloop.creative.concept import Concept
    from brambleloop.creative.prospecting import Candidate

    fields = dict(form="hat", construction="in_the_round", motif="lantern",
                  recipient="child", feeling="folkloric", make_lane="QUICK",
                  function="keeps a child warm and findable after dark")
    fields.update(kw)
    distance = fields.pop("distance", 0.8)
    c = Candidate(concept=Concept(
        key=key, title=f"Concept {key}",
        premise="a beanie whose folded brim stands proud of the crown from across a room",
        pod="hats", palette_story="ember and soot", occasion="christmas", **fields),
        slot=None)
    c.nearest_distance = distance
    return c


def test_a_value_that_would_dominate_an_axis_is_deferred_and_named():
    from brambleloop.creative import ideation

    field = [_cand(f"k{i}", motif="lantern" if i < 5 else f"m{i}", distance=0.9 - i / 100)
             for i in range(8)]
    got = ideation.quotas(field)
    admitted = [c.concept.motif for c in got["admitted"]]
    assert admitted.count("lantern") / len(admitted) <= 0.5, admitted
    assert any("motif_family" in d["axes"] for d in got["deferred"]), got["deferred"]
    # Form is one value across the whole field: fixed by the arena, reported, not enforced.
    assert "form" in got["fixed_by_arena"] and "motif_family" in got["enforced_axes"]


def test_the_handler_records_field_and_shortlist_diversity_per_axis():
    from brambleloop.creative import universe

    db = _db()
    _run(db, "creative.tournament")
    block = _ideation(db)
    assert block["field_diversity"]["measurable"] is True
    assert set(block["field_diversity"]["axes"]) == set(universe.DIVERSITY_AXES)
    assert "quota_deferred" in block and "quota_enforced_axes" in block


# ---- #124: the moving floor ------------------------------------------------------


def _seed_history(db, *, event="Christmas", distance=0.95, n=6, premise=""):
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="creative.expedition",
                       artifact=f"{event}/hats",
                       detail={"survivors": [{
                           "key": f"old-{event}-{i}", "title": f"Old {i}",
                           "premise": premise or "an old survivor", "function": "",
                           "novelty_distance": distance, "make_lane": "QUICK"}
                           for i in range(n)]}))


def test_the_floor_rises_with_the_trailing_cohort_and_cuts_what_would_once_have_passed():
    db = _db()
    _seed_history(db, distance=0.99, n=6)
    _run(db, "creative.tournament")
    block = _ideation(db)
    assert block["floor"]["derived_from"] == "trailing_median", block["floor"]
    assert block["floor_applied"] == 0.99
    winner = block["winner"]
    assert winner is None or winner["novelty_distance"] >= 0.99, winner
    assert all(b["novelty_distance"] < 0.99 for b in block["below_floor"])


def test_the_floor_cuts_survivors_below_it_and_the_winner_clears_it():
    from brambleloop.creative import ideation, standard

    history = [standard.Scored(key=f"h{i}", score=0.7) for i in range(8)]
    plan = {"floor": standard.floor(history), "role": {"role": "CORE", "lanes": ["QUICK"]}}
    field = [_cand("low", distance=0.5, motif="a"), _cand("high", distance=0.8, motif="b")]
    got = ideation.select(plan, candidates=field, survivors=field)
    assert got["floor_applied"] == 0.7
    assert [b["key"] for b in got["below_floor"]] == ["low"]
    assert got["winner"]["key"] == "high"
    # Six months ago (absolute floor 0.45) the low one would have passed.
    early = {"floor": standard.floor([]), "role": plan["role"]}
    assert not ideation.select(early, candidates=field, survivors=field)["below_floor"]


def test_a_weak_cohort_cannot_lower_the_floor_below_the_absolute():
    from brambleloop.creative import standard

    db = _db()
    _seed_history(db, distance=0.10, n=8)
    _run(db, "creative.expedition")
    block = _ideation(db, "creative.expedition")
    assert block["floor_applied"] == standard.ABSOLUTE_FLOOR


# ---- #120: mechanism transfer ------------------------------------------------------


def test_a_mechanism_that_survived_at_halloween_is_transferred_with_a_new_theme():
    db = _db()
    _seed_history(db, event="Halloween", n=3,
                  premise="modular character pocket units that each read as a figure")
    _, asked = _run(db, "creative.tournament")
    t = _ideation(db)["transfer"]
    assert t["mechanism"] == "modular_character_pockets" and t["evidence"] == "measured"
    assert t["from_season"] == "Halloween" and t["to_season"] == "Christmas"
    assert "halloween" not in t["original_theme"].lower()
    assert all("modular character pockets" in a["brief"] for a in asked)


def test_with_no_evidence_the_transfer_says_it_is_exploratory():
    db = _db()
    _run(db, "creative.tournament")
    t = _ideation(db)["transfer"]
    assert t["evidence"] == "UNMEASURED" and t["support"] == 0


# ---- #232: roles guide creation ------------------------------------------------------


def test_the_portfolio_gap_picks_the_role_and_the_next_run_moves_to_the_next_gap():
    from brambleloop.growth import mix

    assert mix.next_role([])["role"] == mix.CORE
    assert mix.next_role([], pending=[mix.CORE])["role"] == mix.ENTRY
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="creative.tournament",
                       artifact="Christmas/hats",
                       detail={"ideation": {"winner": {"key": "w1", "role": "CORE"}}}))
    _, asked = _run(db, "creative.tournament")
    block = _ideation(db)
    assert block["role"]["role"] == mix.ENTRY, block["role"]
    assert all("portfolio role: ENTRY" in a["brief"] for a in asked)
    if block["winner"]:
        assert block["winner"]["role"] == mix.ENTRY


def test_an_invented_role_cannot_be_pending():
    from brambleloop.growth import mix

    assert mix.next_role([], pending=["VIRAL"])["pending"] == []


# ---- the pre-engineering gate -------------------------------------------------------


def test_the_winner_meets_the_real_pre_engineering_gate_and_is_not_cleared_unmeasured():
    db = _db()
    result, _ = _run(db, "creative.tournament")
    block = _ideation(db)
    gate = block["pre_engineering_gate"]
    if block["winner"] is None:
        assert gate["gate"] == "not_called" and result["cleared_for_engineering"] is False
        return
    assert gate["gate"] == "creative.preengineering.gate_concept", gate
    # Vision and model judgements are CLOSED, so the honest verdict is not "passed".
    assert gate["verdict"]["decision"] in ("waiting", "refused"), gate["verdict"]
    assert result["cleared_for_engineering"] is False
    with db.session() as s:
        verdicts = [r.artifact for r in s.scalars(select(AuditLog))
                    if r.action.startswith("concept.gate_")]
    # C-61: the verdict is recorded against the winning *design* (its stable design slug),
    # not the tournament slot key, which repeats across runs.
    assert block["winner"]["design_slug"] in verdicts, "the gate verdict was not recorded"


def test_the_gate_is_called_with_the_winner_and_a_raising_gate_blocks():
    from brambleloop.creative import ideation, preengineering

    seen = []
    saved = preengineering.gate_concept
    try:
        preengineering.gate_concept = (
            lambda db, concept, **kw: seen.append(concept.key) or {"engineer": True})
        got = ideation.pre_engineering_gate(None, _cand("winner-1"))
        assert got["gate"] == "creative.preengineering.gate_concept"
        assert seen == ["winner-1"] and got["cleared_for_engineering"] is True

        def boom(db, concept, **kw):
            raise RuntimeError("gate unavailable")
        preengineering.gate_concept = boom
        got = ideation.pre_engineering_gate(None, _cand("winner-2"))
        assert got["cleared_for_engineering"] is False and "gate unavailable" in got["error"]
    finally:
        preengineering.gate_concept = saved


# ---- #138: culture-engine candidates are a concept source -------------------------


def _culture(db, *, family, slug, premise):
    from brambleloop.core.models import CultureConcept

    with db.session() as s:
        row = CultureConcept(signal_key="fixture-signal", slug=slug, family=family,
                             premise=premise, era="mid_century_holiday",
                             theme="cozy_movie_night", status="candidate")
        s.add(row)
        s.flush()
        return row.id


def test_live_culture_candidates_are_developed_and_meet_the_same_gates():
    db = _db()
    wanted = _culture(db, family="wearable", slug="fixture-brass-lamp-beanie",
                      premise="a beanie in the mid century holiday territory carrying the "
                              "safety of a blanket and a screen")
    ignored = _culture(db, family="pet", slug="fixture-pet-bed",
                       premise="a pet bed in the mid century holiday territory")

    def generator(values, n):
        assert "fixture-brass-lamp-beanie" in values["brief"], "the candidate was not briefed"
        want = int(values.get("count") or 1)
        return {"concepts": [{
            "title": f"Brass Lamp Beanie {n}-{i}",
            "premise": (f"a beanie whose crown is banded like a {MOTIFS[i % len(MOTIFS)]} "
                        f"lamp shade so it reads mid century from across a room"),
            "construction": "in_the_round", "motif": MOTIFS[i % len(MOTIFS)],
            "palette_story": "brass and walnut", "recipient": RECIPIENTS[i % 4],
            "occasion": "christmas", "feeling": "nostalgic",
            "function": "keeps a head warm on a cold walk to a movie",
            "wow": "a banded crown that holds its shape"} for i in range(want)]}

    result, asked = _run(db, "creative.tournament", generator=generator)
    assert asked, "the generator was never asked"
    block = _ideation(db)
    assert block["culture"]["available"] == 2
    assert [c["id"] for c in block["culture"]["matching"]] == [wanted]
    assert block["culture_briefed"] == [wanted] and ignored not in block["culture_briefed"]
    # Same gauntlet: the developed concepts entered the field and were screened like any
    # other, and the one that won met the same pre-engineering gate.
    assert result["generated"] > 0 and result["stages_run"][:2] == ["ideation", "research"]
    if block["winner"]:
        assert block["winner"]["culture_origin"] == wanted
        assert block["pre_engineering_gate"]["gate"] == "creative.preengineering.gate_concept"
        assert result["cleared_for_engineering"] is False


def test_a_breakthrough_tournament_uses_its_trigger_arena_and_divergent_briefs():
    """#216: mjs.scan queues a divergent tournament on a benchmark release. The run must use
    that job's arena and carry its divergent questions to the model, not the weekly wheel's
    ordinary brief (found by the MJs wiring: the handler ignored its inputs)."""
    db = _db()
    inputs = {"lane": "breakthrough", "arena": "hats", "pod": "hats",
              "objective": "search for original white space around the hats arena",
              "diverged_from": "a released pom-pom beanie",
              "trigger": {"kind": "benchmark_release", "listing_ref": "H0"},
              "briefs": [{"axis": "recipient", "question": "who is nobody making hats for?",
                          "claims_market_gap": False, "vocabulary": []}]}
    result, asked = _run(db, "creative.tournament", inputs=inputs)
    assert result["ran"] is True, result
    block = _ideation(db)
    assert block["breakthrough"]["diverged_from"] == "a released pom-pom beanie"
    assert asked and all("who is nobody making hats for?" in a["brief"] for a in asked)
    assert all("diverge from (never reproduce)" in a["brief"] for a in asked)
    # An ordinary run carries none of it.
    _r2, asked2 = _run(_db(), "creative.tournament")
    assert asked2 and not any("breakthrough objective" in a["brief"] for a in asked2)


def test_both_standing_agents_are_registered_handlers():
    from brambleloop.runtime import release  # noqa: F401
    from brambleloop.runtime.worker import handlers

    for job in ("creative.white_space", "creative.four_season", "creative.tournament",
                "creative.expedition"):
        assert handlers.get(job) is not None, job


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL {name}: {exc}")
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
