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


def test_no_pod_can_drown_the_others():
    """140 benchmark garments would make the overall rate a statement about garments."""
    listings = ([_listing(str(i), "Cozy Crochet Cardigan Pattern", "garments") for i in range(50)]
                + [_listing("x", "Chunky Throw Blanket", "blankets")])
    pairs = B.build_pairs([_concept("bl-1", pod="garments")], listings, per_pod=3)
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


def _seed(db, n: int = 6):
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
    _seed(db)
    result = B.run(db, [_concept("bl-1")], gateway=_Gateway(pick="neither"))
    assert result["pairs_judged"] == 0
    assert result["problems"]


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
