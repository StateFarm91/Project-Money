"""What a Brambleloop design must state, and what a benchmark may leave out.

The owner's rule generalised: a construction fact that materially determines the finished
object belongs in the authoritative source, not in a photograph. The asymmetry between our
designs and our records of other people's is the load-bearing part.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir import benchmarks as B, specification as S
from brambleloop.cir.model import CIR, Component, Gauge, Op, Row, Seam
from brambleloop.products.builder import CATALOGUE, for_slug


def _two_piece(*, edges=True, grain="up"):
    g = Gauge(14.5, 9.5, stitch_type="hdc")
    rows = [Row(index=i, ops=[Op("hdc", 20)], declared_count=20, turning_chain=1)
            for i in range(1, 6)]
    return CIR(slug="thing", title="Thing", version="1.0.0", construction="flat_rows",
               gauge=g,
               components=[Component("body", "flat_rows", rows, foundation=20, grain=grain),
                           Component("trim", "flat_rows", rows, foundation=20, grain=grain)],
               assembly=[Seam("whipstitch", "trim", "body",
                              edge_a="bottom" if edges else None,
                              edge_b="top" if edges else None)])


def test_a_brambleloop_design_must_state_its_join_targets():
    """A join that does not say which edges meet cannot be placed or checked."""
    gaps = S.reconstructive_gaps(_two_piece(edges=False))
    assert any(g.fact == "join target" for g in gaps)
    assert not S.reconstructive_gaps(_two_piece(edges=True))


def test_a_brambleloop_design_must_state_panel_orientation():
    bad = _two_piece()
    object.__setattr__(bad.components[0], "grain", "")
    assert any(g.fact == "panel orientation" for g in S.reconstructive_gaps(bad))


def test_a_design_with_width_adding_chains_must_state_a_chain_gauge():
    """Chains are narrower than worked stitches, so spans made of them need their own gauge."""
    c = _two_piece()
    c.components[0].rows[1].ops.append(Op("ch", 5))          # adds width, spans nothing
    assert any(g.fact == "chain gauge" for g in S.reconstructive_gaps(c))
    c.gauge.chains_per_10cm = 18.4
    assert not any(g.fact == "chain gauge" for g in S.reconstructive_gaps(c))


def test_a_bridging_chain_needs_no_chain_gauge_because_it_adds_no_width():
    c = _two_piece()
    c.components[0].rows[1].ops.append(Op("ch", 5, spans=4))
    assert not any(g.fact == "chain gauge" for g in S.reconstructive_gaps(c))


def test_the_gate_refuses_an_underspecified_brambleloop_design():
    try:
        S.refuse_an_underspecified_design(_two_piece(edges=False))
    except S.SpecificationIncomplete as exc:
        assert "a photograph is not a specification" in str(exc)
    else:
        raise AssertionError("an underspecified Brambleloop design was certified")


def test_a_benchmark_may_be_as_incomplete_as_its_source():
    """Falsifying a record to make it look complete would destroy the benchmark.

    The purchased cardigan states pocket placement and neckline length only in a photograph.
    Inventing numbers for them would make the reconstruction agree with itself rather than
    with the real garment, which is the one thing a benchmark exists to prevent.
    """
    cardigan = B.cardigan("S")
    assert cardigan.authored == "benchmark"
    report = S.is_reconstructible(cardigan)
    assert report["reconstructible"] is False
    assert report["held_to_the_standard"] is False
    assert "allowed to be as incomplete as its source" in report["why"]
    S.refuse_an_underspecified_design(cardigan)          # must not raise


def test_the_same_design_authored_by_brambleloop_is_refused():
    """The asymmetry is about who controls the specification, not about the design."""
    ours = B.cardigan("S")
    ours.authored = "brambleloop"
    try:
        S.refuse_an_underspecified_design(ours)
    except S.SpecificationIncomplete:
        pass
    else:
        raise AssertionError("the standard did not apply to a Brambleloop design")


def test_authorship_defaults_to_being_held_to_the_standard():
    """A new design must not inherit a benchmark's permission to be vague."""
    assert _two_piece().authored == "brambleloop"


def test_the_benchmarks_gaps_are_exactly_the_two_its_pattern_leaves_to_a_photograph():
    gaps = S.reconstructive_gaps(B.cardigan("M"))
    where = " ".join(g.where for g in gaps)
    assert "pocket" in where and "neck_ribbing" in where
    assert "sleeve" not in where, "the sleeve join IS stated and must not be reported missing"


def test_every_existing_catalogue_product_is_reconstructible():
    """The rule has to hold for what is already certified, or it is not a rule yet."""
    bad = []
    for slug in CATALOGUE:
        cir = for_slug(slug)
        if cir is None:
            continue
        gaps = S.reconstructive_gaps(cir)
        if gaps:
            bad.append((slug, [g.fact for g in gaps]))
    assert not bad, f"certified products that cannot be reconstructed: {bad}"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("OK  ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, repr(e)); traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
