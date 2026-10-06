"""A blinded comparison, and the three ways it quietly stops being one.

Requirement 94's remaining half: blinded human/agent benchmark comparison. It is the kind of
measurement that returns a confident number whether or not it measured anything, so most of
this file is about the failure modes rather than the happy path.

  - A blinding that is a promise rather than a check is not a blinding.
  - A judge that prefers the first option is measuring order, and produces a stable,
    confident, meaningless win rate.
  - A win rate from four pairs is not a capability, and "unmeasured" is not "parity".
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.creative import blinded as B  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/blinded.sqlite")
    db.create_all()
    return db


def _concept(key: str, pod: str = "blankets", motif: str = "cable") -> Concept:
    return Concept(
        key=key, title=f"Concept {key}",
        premise="a heavy textured throw that reads as an heirloom from across a room",
        pod=pod, form="rectangle_throw", construction="flat_rows", motif=motif,
        palette_story="oatmeal and rust", recipient="host", occasion="housewarming",
        feeling="cosy", function="warmth", make_lane="MEDIUM")


def _listing(ref: str, title: str, pod: str, price: float = 8.0) -> dict:
    return {"listing_ref": ref, "title": title, "pod": pod, "product_type": "6343",
            "price_cad": price}


# ---- blinding --------------------------------------------------------------


def test_the_judges_view_carries_neither_side_nor_reference():
    """The two fields that would end the experiment are the two that are not shown."""
    shown = B.blind(B.from_concept(_concept("bl-1")))
    assert set(shown) == set(B.CARD_FIELDS)
    assert "side" not in shown and "ref" not in shown


def test_a_card_carrying_a_tell_is_refused_rather_than_cleaned():
    """Cleaning silently is how the next tell gets through."""
    card = B.Card(ref="x", side=B.THEIRS, pod="blankets", form="rectangle_throw",
                  occasion="everyday", recipient="host", feeling="CROCHET PATTERN pdf")
    try:
        B.blind(card)
    except B.BlindingFailed as e:
        assert "crochet pattern" in str(e)
    else:
        raise AssertionError("a marketplace format word reached the judge")


def test_a_card_with_a_hole_in_it_is_identifiable_by_the_hole():
    card = B.Card(ref="x", side=B.OURS, pod="blankets", form="",
                  occasion="everyday", recipient="host", feeling="cosy")
    try:
        B.blind(card)
    except B.BlindingFailed as e:
        assert "form" in str(e)
    else:
        raise AssertionError("an empty field reached the judge")


def test_both_sides_are_described_in_the_same_vocabulary():
    """Different registers are a tell, and a subtle one."""
    ours = B.blind(B.from_concept(_concept("bl-1", pod="stockings")))
    theirs = B.blind(B.from_listing(
        _listing("1", "Cozy Crochet Christmas Stocking, Personalised", "stockings")))
    assert set(ours) == set(theirs)


def test_the_benchmark_side_is_read_from_facts_and_not_from_its_pattern():
    """Competitor research is demand and merchandising intelligence only."""
    card = B.from_listing(_listing(
        "1", "Chunky Rustic Farmhouse Pumpkin Stack, Fall Decor", "amigurumi", price=6.5))
    assert card.form == "toy"
    assert card.feeling == "folkloric"  # "rustic" is read before "chunky"
    assert "pumpkin stack" not in " ".join(card.presented().values()).lower()


def test_a_listing_whose_title_says_nothing_does_not_become_an_opponent():
    """A default on one side is a tell; a default on both is a fabrication about one."""
    try:
        B.from_listing(_listing("1", "Mj Signature Collection Piece", "blankets"))
    except B.Unreadable as e:
        assert "without inventing" in str(e)
    else:
        raise AssertionError("a listing was described from nothing")


def test_a_bundle_is_not_paired_against_a_single_product_concept():
    """Pairing against a six-pattern ebook measures format, not creativity."""
    for pod in B.NOT_COMPARABLE_PODS:
        try:
            B.from_listing(_listing("1", "Chunky Cozy Throw Blanket Ebook", pod))
        except B.Unreadable:
            pass
        else:
            raise AssertionError(f"{pod} became an opponent")


# ---- pairing ---------------------------------------------------------------


def test_a_cross_form_pairing_is_refused():
    """The confound the first live run walked straight into, with both guards green.

    11-1 to this catalogue, position share exactly 0.50, above the sample floor,
    `valid: true`. Worthless: the judge named "throw" in nine of twelve reasons against
    pillows, coasters and wreaths. A blanket beats a coaster on perceived value whoever
    designed it, so the run measured which object is bigger.
    """
    ours = B.from_concept(_concept("bl-1", pod="home_decor"))
    theirs = B.Card(ref="1", side=B.THEIRS, pod="home_decor", form="coaster",
                    occasion="everyday", recipient="self", feeling="bold")
    try:
        B.pair(ours, theirs)
    except B.NotComparable as e:
        assert "which object is bigger" in str(e)
    else:
        raise AssertionError("a throw was judged against a coaster")


def test_a_run_refuses_to_buy_a_measurement_whose_answer_is_already_known():
    """Below the floor the verdict is `unmeasured` whatever the judge says, so do not pay."""
    db = _db()
    _seed(db, n=3)
    gw = _Gateway()
    try:
        B.run(db, [_concept("bl-1")], gateway=gw, per_pod=3)
    except B.RunRefused as e:
        assert "already known" in str(e)
        assert gw.calls == 0, "it spent money on a run it had already decided was unmeasured"
    else:
        raise AssertionError("it bought a result it knew would be unmeasured")


def test_the_overlap_report_names_what_this_catalogue_makes_that_the_benchmark_does_not():
    """The empty side is the finding: it is a fact about the catalogue, not about the tool."""
    from brambleloop.creative.audit import catalogue_concepts

    overlap = B.form_overlap(catalogue_concepts(), [])
    assert overlap["our_concepts_with_an_opponent"] == 0
    forms = {r["form"] for r in overlap["ours_only"]}
    assert "rectangle_throw" in forms and "garland" in forms


def test_a_cross_pod_pairing_is_refused():
    """A stocking beating a cardigan measures which department is easier to love."""
    ours = B.from_concept(_concept("bl-1", pod="blankets"))
    theirs = B.from_listing(_listing("1", "Cozy Crochet Christmas Stocking", "stockings"))
    try:
        B.pair(ours, theirs)
    except B.NotComparable as e:
        assert "same-pod" in str(e)
    else:
        raise AssertionError("departments were compared instead of ideas")


def test_the_presentation_order_is_decided_before_anything_reads_the_pair():
    """Recorded up front, so the position bias is computable afterwards rather than argued."""
    ours = B.from_concept(_concept("bl-1"))
    theirs = B.from_listing(_listing("1", "Chunky Cable Throw Blanket", "blankets"))
    p = B.pair(ours, theirs, seed="fixed")
    assert p.first in (B.OURS, B.THEIRS)
    assert p.side_at("A") == p.first
    assert p.side_at("B") != p.first
    assert B.pair(ours, theirs, seed="fixed").first == p.first  # deterministic


def test_the_order_is_not_always_the_same_across_pairs():
    """A constant order is the bias, not a guard against it."""
    firsts = set()
    for i in range(40):
        ours = B.from_concept(_concept(f"bl-{i}"))
        theirs = B.from_listing(_listing(str(i), "Chunky Cable Throw Blanket", "blankets"))
        firsts.add(B.pair(ours, theirs).first)
    assert firsts == {B.OURS, B.THEIRS}


def test_no_slot_can_drown_the_others():
    """140 benchmark cardigans would make the overall rate a statement about cardigans."""
    listings = [_listing(str(i), "Cozy Crochet Cardigan Pattern", "garments")
                for i in range(50)]
    ours = _concept("bl-1", pod="garments")
    ours = Concept(**{**ours.__dict__, "form": "fitted_garment"})
    pairs = B.build_pairs([ours], listings, per_pod=3)
    assert len(pairs) == 3


# ---- tallying --------------------------------------------------------------


def _judgements(n: int, *, ours_wins: int, all_position_a: bool = False):
    out = []
    for i in range(n):
        ours = B.from_concept(_concept(f"bl-{i}"))
        theirs = B.from_listing(_listing(str(i), "Chunky Cable Throw Blanket", "blankets"))
        p = B.Pairing(ours, theirs, B.OURS if i % 2 == 0 else B.THEIRS)
        if all_position_a:
            pick = "A"
        else:
            want = B.OURS if i < ours_wins else B.THEIRS
            pick = "A" if p.first == want else "B"
        out.append(B.Judgement(p, pick))
    return out


def test_nothing_judged_is_unmeasured_and_not_parity():
    result = B.tally([])
    assert result["verdict"] == "unmeasured"
    assert not result["valid"]
    assert "not parity" in result["reason"]


def test_a_thin_run_reports_no_win_rate_however_good_it_looks():
    """Four straight wins is not a capability measurement."""
    result = B.tally(_judgements(4, ours_wins=4))
    assert result["verdict"] == "unmeasured"
    assert not result["valid"]
    assert result["ours"] == 4


def test_a_judge_that_always_picks_the_first_option_invalidates_the_run():
    """The classic failure of pairwise evaluation: stable, confident and meaningless."""
    result = B.tally(_judgements(20, ours_wins=0, all_position_a=True))
    assert result["verdict"] == "invalid"
    assert not result["valid"]
    assert result["position_share"] == 1.0
    assert "measured order" in result["reason"]


def test_the_bias_is_discarded_rather_than_corrected():
    """A correction on a judge that was not reading puts error bars around nothing."""
    result = B.tally(_judgements(20, ours_wins=0, all_position_a=True))
    assert "win_rate" in result           # still reported, so the run is inspectable
    assert result["valid"] is False       # and never usable


def test_a_balanced_run_above_the_floor_states_a_verdict():
    result = B.tally(_judgements(20, ours_wins=14))
    assert result["valid"]
    assert result["verdict"] == "ahead"
    assert result["win_rate"] == 0.7
    assert result["position_share"] <= B.MAX_POSITION_SHARE


def test_losing_is_reported_as_losing():
    """The measurement exists to be able to say this."""
    result = B.tally(_judgements(20, ours_wins=4))
    assert result["valid"] and result["verdict"] == "behind"


def test_the_tally_breaks_down_by_pod():
    result = B.tally(_judgements(20, ours_wins=14))
    assert result["by_pod"]["blankets"]["judged"] == 20


# ---- the run ---------------------------------------------------------------


class _Gateway:
    """A judge that always picks the option describing a throw."""

    def __init__(self, pick: str = "A"):
        self.pick = pick
        self.calls = 0

    def complete_json(self, ref, *, agent, values, required=None):
        self.calls += 1
        assert ref == "creative.blinded_appeal@1"
        # The gateway must never be handed anything that identifies a side.
        blob = repr(values).lower()
        assert "brambleloop" not in blob and "listing_ref" not in blob
        return {"pick": self.pick, "reason": "it reads as a gift"}


def _seed(db, n: int = 20):
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"L{i}",
                                   title="Chunky Cable Throw Blanket Pattern",
                                   pod="blankets", price_cad=7.5))


def test_a_run_with_no_observed_benchmark_is_refused():
    """An empty comparison is not a favourable one."""
    try:
        B.run(_db(), [_concept("bl-1")], gateway=_Gateway())
    except B.RunRefused as e:
        assert "no benchmark listing" in str(e)
    else:
        raise AssertionError("a comparison ran against nothing")


def test_a_run_whose_concepts_share_no_pod_with_the_benchmark_is_refused():
    db = _db()
    _seed(db)
    try:
        B.run(db, [_concept("bl-1", pod="education")], gateway=_Gateway())
    except B.RunRefused as e:
        assert "pod" in str(e)
    else:
        raise AssertionError("departments were compared instead of ideas")


def test_a_run_reports_what_it_judged_and_what_it_cost():
    db = _db()
    _seed(db)
    gw = _Gateway()
    result = B.run(db, [_concept(f"bl-{i}") for i in range(5)], gateway=gw, per_pod=3)
    assert result["pairs_judged"] == gw.calls > 0
    assert "cost_cad" in result and not result["stopped_on_ceiling"]
    # Every judgement went to position A, so the run must refuse to mean anything.
    assert result["verdict"] == "invalid"


def test_a_run_stops_on_the_ceiling_and_keeps_what_it_bought():
    """A creative measurement that spends the whole month's budget is the worse outcome."""
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway import routing

    db = _db()
    _seed(db)
    with db.session() as s:
        s.add(CostEntry(agent="test", kind="llm",
                        amount_cad=routing.MONTHLY_CEILING_CAD - 0.0001))
    result = B.run(db, [_concept(f"bl-{i}") for i in range(5)], gateway=_Gateway())
    assert result["stopped_on_ceiling"]
    assert result["pairs_judged"] == 0
    assert result["verdict"] == "unmeasured"


def test_a_judge_that_fails_costs_a_pair_and_not_the_run():
    db = _db()
    _seed(db)

    class Flaky(_Gateway):
        def complete_json(self, ref, *, agent, values, required=None):
            self.calls += 1
            if self.calls % 2:
                raise RuntimeError("provider unavailable")
            return {"pick": "B", "reason": "warmer"}

    result = B.run(db, [_concept(f"bl-{i}") for i in range(5)], gateway=Flaky())
    assert result["problems"] and result["pairs_judged"] > 0


def test_a_pick_that_is_not_a_presented_position_is_not_counted():
    db = _db()
    _seed(db, n=30)
    result = B.run(db, [_concept(f"bl-{i}") for i in range(6)],
                   gateway=_Gateway(pick="neither"))
    assert result["pairs_judged"] == 0
    assert result["problems"]


# ---- the ledger the ceiling actually reads ---------------------------------


def test_a_gateway_call_moves_the_budget_it_is_checked_against():
    """The defect that would have made the monthly ceiling ornamental.

    `ModelGateway` recorded its calls as kind "model" and every ceiling counts kind "llm", so
    a real call would have been invisible to the budget: the ceiling would have read CA$0.00
    forever while money left the account. It never bit because nothing had ever constructed a
    ModelGateway -- the blinded run is the first thing that does, and would have been the
    first real spend, uncapped.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import routing
    from brambleloop.gateway.model_gateway import ModelGateway

    db = _db()
    Registry(db).seed_defaults()

    class Provider:
        name = "stub"
        model = "claude-opus-5"
        cost_per_1k_input_cad = 0.01
        cost_per_1k_output_cad = 0.02

        def complete(self, system, user, *, max_tokens):
            from brambleloop.gateway.model_gateway import ModelResponse
            return ModelResponse(text='{"pick": "A", "reason": "warmer"}', provider=self.name,
                                 model=self.model, input_tokens=1000, output_tokens=100,
                                 latency_ms=1.0)

    before = routing.spent_this_month(db)
    gateway = ModelGateway([Provider()], registry=Registry(db))
    gateway.complete_json("creative.blinded_appeal@1", agent="creative_director",
                          values={"option_a": {}, "option_b": {}},
                          required=("pick", "reason"))
    after = routing.spent_this_month(db)
    assert gateway.spend_cad() > 0, "the call cost nothing, so this proves nothing"
    assert after > before, (
        f"the gateway spent CA${gateway.spend_cad()} and the ceiling still reads "
        f"CA${after}: the budget is counting rows the gateway does not write")


def test_the_ceiling_reads_one_kind_and_every_writer_uses_it():
    """A literal in four places had already disagreed in one of them."""
    from brambleloop.gateway import routing

    src = (ROOT / "src" / "brambleloop" / "gateway")
    for name in ("model_gateway.py", "anthropic.py", "routing.py"):
        text = (src / name).read_text()
        assert 'kind="model"' not in text, name
        stray = [ln for ln in text.splitlines()
                 if 'kind="llm"' in ln or 'kind == "llm"' in ln]
        assert not stray, f"{name} carries a literal cost kind: {stray}"
    assert routing.COST_KIND == "llm"


# ---- the two measures #94 names that nothing computed ----------------------


def test_a_field_with_one_value_is_reported_as_a_missing_field():
    """"The catalogue is repetitive" is not actionable; naming the field is."""
    from brambleloop.creative.tournament import theme_fatigue

    report = theme_fatigue([_concept(f"bl-{i}") for i in range(10)])
    worst = report["worst"]
    assert worst["share"] == 1.0
    assert report["by_field"]["feeling"]["distinct"] == 1
    assert "nowhere to record" in report["note"]


def test_a_varied_catalogue_reports_no_fatigue():
    """A measurement that fires on everything says nothing about anything."""
    from brambleloop.creative.concept import FEELINGS, OCCASIONS
    from brambleloop.creative.tournament import theme_fatigue

    concepts = []
    for i in range(12):
        c = _concept(f"bl-{i}")
        concepts.append(Concept(
            key=c.key, title=c.title, premise=c.premise,
            pod=("blankets", "hats", "bags", "ornaments")[i % 4],
            form=("rectangle_throw", "hat", "bag", "ornament")[i % 4],
            construction=c.construction, motif=f"motif-{i}",
            palette_story=c.palette_story,
            recipient=("self", "child", "host", "teen")[i % 4],
            occasion=OCCASIONS[i % len(OCCASIONS)],
            feeling=FEELINGS[i % len(FEELINGS)],
            function=c.function, make_lane=("QUICK", "SHORT", "MEDIUM")[i % 3]))
    report = theme_fatigue(concepts)
    assert report["fatigued"] == [], report["fatigued"]


def test_theme_fatigue_on_an_empty_catalogue_is_not_a_clean_bill_of_health():
    from brambleloop.creative.tournament import theme_fatigue

    report = theme_fatigue([])
    assert report["concepts"] == 0 and report["fatigued"] == []
    assert "nothing can be repetitive yet" in report["note"]


def test_novelty_reports_the_minimum_beside_the_mean():
    """A catalogue can average a comfortable distance and contain one product twice."""
    from brambleloop.creative.tournament import novelty

    twins = [_concept("bl-a"), _concept("bl-b")]
    far = Concept(key="bl-c", title="c", premise=twins[0].premise, pod="hats", form="hat",
                  construction="in_the_round", motif="stripe", palette_story="x",
                  recipient="teen", occasion="birthday", feeling="playful",
                  function="worn", make_lane="QUICK")
    report = novelty(twins + [far])
    assert report["min_distance"] < report["mean_distance"]
    assert set(report["closest_pair"].values()) & {"bl-a", "bl-b"}


def test_one_concept_cannot_have_a_novelty_distance():
    """Unmeasurable is not novel."""
    from brambleloop.creative.tournament import novelty

    report = novelty([_concept("bl-1")])
    assert not report["measurable"]
    assert "not novel" in report["reason"]


def test_the_existing_catalogue_measures_as_badly_as_the_owner_says():
    """The owner's defect report, as a number rather than an agreement.

    Three fields hold exactly one value across all eleven products, because the generator has
    nowhere to record a second. If this test ever fails because the numbers improved, it
    should be updated to the new floor, not deleted.
    """
    from brambleloop.creative.audit import catalogue_concepts
    from brambleloop.creative.tournament import novelty, theme_fatigue

    concepts = catalogue_concepts()
    fatigue = theme_fatigue(concepts)
    single_valued = [f for f, row in fatigue["by_field"].items() if row["distinct"] == 1]
    assert set(single_valued) >= {"pod", "feeling", "make_lane"}, single_valued
    assert novelty(concepts)["mean_distance"] < 0.5


def test_a_run_from_an_older_method_is_reported_as_superseded():
    """Production is holding an 11-1 `ahead` verdict that the method no longer stands behind.

    Deleting it would be tidier and worse: the record of a measurement that was wrong is the
    thing that stops the same mistake being made confidently a second time.
    """
    from brambleloop.core.models import AuditLog

    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="creative.blinded",
                       detail={"verdict": "ahead", "valid": True, "win_rate": 0.9167}))
    run = B.last_run(db)
    assert run["superseded"] and run["valid"] is False
    assert run["verdict"] == "ahead"          # kept for the record
    assert "object size" in run["superseded_reason"]


def test_a_current_run_is_not_marked_superseded():
    from brambleloop.core.models import AuditLog

    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="creative.blinded",
                       detail={"verdict": "parity", "valid": True,
                               "method_version": B.METHOD_VERSION}))
    assert "superseded" not in B.last_run(db)



# ---- the search-grid blind tournament (#126) ------------------------------


def _audited_pod(db, pod="blankets", n=6):
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{pod}-{i}",
                title=f"Chunky Throw Blanket {i}", pod=pod, audit_state="audited",
                price_cad=9.0, media_count=6,
                detail={"image_urls": [f"https://i.etsystatic.com/{pod}-{i}_fullxfull.jpg"],
                        "num_favorers": 400}))


def _our_frames():
    return [{"made": True, "slug": "autumn-oak-mosaic-throw", "role": "hero",
             "image_ref": "artifacts/autumn-oak-hero.png"},
            {"made": True, "slug": "cloudline-baby-blanket", "role": "hero",
             "image_ref": "artifacts/cloudline-hero.png"}]


def test_the_grid_is_blinded_seeded_and_fails_until_a_judge_ranks_it():
    """The expected result today, and the finding: no judge has ranked the grid, so it
    fails. A threshold cleared by default is the brand favouritism #126 forbids."""
    db = _db()
    _audited_pod(db)
    grid = B.render_grid(db, _our_frames(), pod="blankets", seed=7)

    assert grid["benchmark_cells"] == 6 and grid["our_cells"] == 2
    assert len(grid["cells"]) == 8
    # What a judge sees carries no side, no ref, no seller, no price, no reviews, no title.
    for cell in grid["cells"]:
        assert set(cell) == {"cell", "row", "col", "thumbnail", "pod"}
    assert set(grid["key"]) == {c["cell"] for c in grid["cells"]}
    assert sorted(k["side"] for k in grid["key"].values()).count(B.OURS) == 2
    assert grid["judge_fields"] == list(B.GRID_JUDGE_FIELDS)
    assert all(v is None for v in grid["our_scores"].values())
    assert grid["verdict"] == "fail"
    assert "no judge has ranked" in grid["why"]

    # Seeded: the same seed gives the same order; a different seed moves things.
    again = B.render_grid(db, _our_frames(), pod="blankets", seed=7)
    assert [c["cell"] for c in again["cells"]] == [c["cell"] for c in grid["cells"]]
    assert [c["thumbnail"] for c in again["cells"]] == [c["thumbnail"] for c in grid["cells"]]
    other = B.render_grid(db, _our_frames(), pod="blankets", seed=8)
    assert [c["thumbnail"] for c in other["cells"]] != [c["thumbnail"] for c in grid["cells"]]


def test_a_thin_grid_or_an_empty_side_is_refused_rather_than_padded():
    db = _db()
    _audited_pod(db, n=3)
    for ours in (_our_frames(), []):
        try:
            B.render_grid(db, ours, pod="blankets")
        except B.GridRefused:
            pass
        else:
            raise AssertionError("a three-benchmark grid was built")
    _audited_pod(db, pod="hats", n=6)
    try:
        B.render_grid(db, [], pod="hats")
    except B.GridRefused as exc:
        assert "nothing to place" in str(exc)
    else:
        raise AssertionError("a grid with no side of ours was built")


def test_judgements_are_read_against_the_threshold_and_a_partial_judging_still_fails():
    db = _db()
    _audited_pod(db)
    grid = B.render_grid(db, _our_frames(), pod="blankets", seed=1)
    ours = [c for c, k in grid["key"].items() if k["side"] == B.OURS]

    ranked = {c: {f: 0.8 for f in B.GRID_JUDGE_FIELDS} for c in ours}
    clear = B.render_grid(db, _our_frames(), pod="blankets", seed=1, judgements=ranked)
    assert clear["verdict"] == "clear" and clear["below_threshold"] == []

    weak = {c: {**{f: 0.8 for f in B.GRID_JUDGE_FIELDS}, "desire": 0.2} for c in ours}
    failed = B.render_grid(db, _our_frames(), pod="blankets", seed=1, judgements=weak)
    assert failed["verdict"] == "fail" and failed["below_threshold"] == ["desire"]

    partial = {ours[0]: {f: 0.9 for f in B.GRID_JUDGE_FIELDS}}
    half = B.render_grid(db, _our_frames(), pod="blankets", seed=1, judgements=partial)
    assert half["verdict"] == "fail" and set(half["unjudged"]) == set(B.GRID_JUDGE_FIELDS)


class _Response:
    def __init__(self, text):
        self.text, self.input_tokens, self.output_tokens = text, 1200, 300


class _JudgeProvider:
    """A stand-in vision judge that scores what it is shown by a picture->score table held
    OUTSIDE anything the system sends (the 'content' of each image), never by where the
    picture came from. `per_judge` lets judges disagree so the median is actually tested.
    It records every system prompt and prompt it receives so the tests can assert nothing
    it was sent names a side, a slug or a listing reference (C-4)."""
    name, model = "anthropic", "claude-sonnet-5"
    cost_per_1k_input_cad, cost_per_1k_output_cad = 0.004, 0.02

    def __init__(self, ours_score, theirs_score, *, silent_judge="", per_judge=None):
        self.ours, self.theirs, self.silent, self.calls = ours_score, theirs_score, silent_judge, []
        self.per_judge = per_judge or {}
        # What each picture looks like, decided by the test, not by the grid.
        self.content = {f.get("image_ref"): "ours" for f in _our_frames()}

    def see(self, system, prompt, urls, *, max_tokens):
        import json as _json
        import re as _re
        self.calls.append((system, prompt, list(urls)))
        if self.silent and self.silent in system:
            return _Response("I cannot rank these.")
        labels = _re.search(r"in this order: ([^.]+)\.", prompt).group(1).split(", ")
        judge = next((j for j in self.per_judge if j in system), None)
        ours_v, theirs_v = self.per_judge.get(judge, (self.ours, self.theirs))
        rows = []
        for label, url in zip(labels, urls):
            v = ours_v if self.content.get(url) == "ours" else theirs_v
            rows.append({"cell": label, "attention": v, "comprehension": v, "desire": v,
                         "distinctiveness": v})
        return _Response(_json.dumps({"cells": rows}))


def test_the_grid_is_judged_by_an_independent_panel_blinded_to_side():
    db = _db()
    _audited_pod(db)
    judge = _JudgeProvider(0.8, 0.4)
    out = B.grid_tournament(db, _our_frames(), pod="blankets", provider=judge, seed=7)
    assert out["verdict"] == "clear", out["why"]
    assert all(v == 0.8 for v in out["our_scores"].values())
    assert "key" not in out, "the side key must not travel with the judged result"
    assert out["panel"]["judged_by"] == sorted(j for j, _ in B.GRID_JUDGES)
    # Each judge saw every cell, in its own order, and never a side or a ref.
    orders = [urls for _, _, urls in judge.calls]
    assert len({tuple(o) for o in orders}) > 1, "every judge saw the same order"
    assert out["panel"]["cost_cad"] > 0
    # Blinding: nothing a judge was sent names a side, one of our slugs or a listing ref.
    leaks = ("agent", "human", "ours", "theirs", "autumn-oak", "cloudline", "blankets-")
    for system, prompt, _ in judge.calls:
        text = (system + " " + prompt).lower()
        assert not any(word in text for word in leaks), text[:200]


def test_the_panel_verdict_is_the_median_not_the_mean_or_the_minimum():
    """C-4: judges disagree. Two rank our renders 0.6, one outlier ranks them 0.0. The mean
    (0.4) and the minimum (0.0) would fail the 0.5 threshold; the median (0.6) clears it."""
    db = _db()
    _audited_pod(db)
    judges = [j for j, _ in B.GRID_JUDGES]
    judge = _JudgeProvider(0.6, 0.3, per_judge={judges[0]: (0.6, 0.3), judges[1]: (0.6, 0.3),
                                                 judges[2]: (0.0, 0.9)})
    out = B.grid_tournament(db, _our_frames(), pod="blankets", provider=judge, seed=3)
    assert all(v == 0.6 for v in out["our_scores"].values()), out["our_scores"]
    assert out["verdict"] == "clear", out["why"]


def test_weak_renders_fail_the_grid_on_the_panel_median():
    db = _db()
    _audited_pod(db)
    out = B.grid_tournament(db, _our_frames(), pod="blankets", provider=_JudgeProvider(0.2, 0.9))
    assert out["verdict"] == "fail" and set(out["below_threshold"]) == set(B.GRID_JUDGE_FIELDS)


def test_a_judge_that_does_not_answer_leaves_the_grid_unjudged_not_averaged():
    db = _db()
    _audited_pod(db)
    out = B.grid_tournament(db, _our_frames(), pod="blankets",
                            provider=_JudgeProvider(0.9, 0.1, silent_judge="gift"))
    assert out["verdict"] == "fail" and out["unjudged"], out
    assert "unjudged" in out["why"]


def test_the_grid_judges_stop_on_the_ceiling_and_the_grid_stays_unjudged():
    from brambleloop.core.models import CostEntry
    from brambleloop.finance import spend_policy

    db = _db()
    _audited_pod(db)
    with db.session() as s:
        s.add(CostEntry(agent="gateway", amount_cad=spend_policy.CEILING_CAD, kind="llm",
                        purpose="test"))
    judge = _JudgeProvider(0.9, 0.1)
    out = B.grid_tournament(db, _our_frames(), pod="blankets", provider=judge)
    assert judge.calls == [], "a judge was called past the ceiling"
    assert out["verdict"] == "fail" and out["panel"]["stopped_by"]



def test_a_christmas_title_reads_as_christmas_not_everyday():
    """Certification C-55: the title words are singularised ("christma"), and the occasion
    table was compared unnormalised, so every Christmas listing read as "everyday" and the
    pre-engineering twin check could not see a Christmas benchmark."""
    card = B.from_listing({"title": "Festive Christmas Stocking Crochet Pattern",
                                 "listing_ref": "bench-x"})
    assert card.occasion == "christmas", card.occasion
    assert card.form == "stocking"

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
