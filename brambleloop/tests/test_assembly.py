"""Deterministic object geometry: pieces placed, joins checked, nothing guessed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir import assembly, benchmarks as B
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.model import CIR, Component, Gauge, Op, Row, Seam
from brambleloop.cir.twin import build_twin
from brambleloop.visual import correspondence as C


def _built(size="S"):
    c = B.cardigan(size)
    r = compile_cir(c)
    assert r.ok
    twins = {x.name: build_twin(c, r, component=x.name) for x in c.components}
    return c, twins, assembly.assemble(c, twins)


# ---- the chain-span primitive --------------------------------------------

def test_a_bridging_chain_adds_no_width_of_its_own():
    """The measured defect: 27 bridge chains counted as 27 extra units of width.

    A chain laid across a gap occupies the stitches it replaced. Counting it as additional
    fabric made the benchmark body +1.11% too wide at XS.
    """
    g = Gauge(14.5, 9.5, stitch_type="hdc")
    bridged = Row(index=2, ops=[Op("hdc", 64), Op("ch", 27, spans=26)], declared_count=91)
    plain = Row(index=3, ops=[Op("hdc", 90)], declared_count=90)
    cir = CIR(slug="s", title="S", version="1.0.0", construction="flat_rows", gauge=g,
              components=[Component("p", "flat_rows",
                                    [Row(index=1, ops=[Op("hdc", 90)], declared_count=90),
                                     bridged, plain], foundation=90)])
    r = compile_cir(cir)
    rows = {x.index: x for x in r.rows}
    w_bridge, _ = assembly and __import__(
        "brambleloop.cir.twin", fromlist=["row_width_cm"]).row_width_cm(rows[2], g)
    w_plain, _ = __import__(
        "brambleloop.cir.twin", fromlist=["row_width_cm"]).row_width_cm(rows[3], g)
    assert abs(w_bridge - w_plain) < 0.05, (
        f"a bridged row measured {w_bridge:.2f}cm against {w_plain:.2f}cm of plain fabric; "
        f"the bridge is being added to the width instead of laid across it")


def test_the_benchmark_body_width_matches_its_own_stitch_count():
    """The +1.11% error, gone and stated in its own terms."""
    for size in B.SIZES:
        i = B.SIZES.index(size)
        c, twins, _ = _built(size)
        true_cm = B.BODY_STS[i] / B.GAUGE_STS * 10
        assert abs(twins["body"].width_cm - true_cm) / true_cm < 0.005, (
            f"{size}: twin {twins['body'].width_cm} vs {true_cm:.2f} from the counts")


def test_a_chain_that_adds_width_says_so_when_the_chain_gauge_is_unknown():
    """Measuring chains at stitch gauge is an over-estimate, and must be declared."""
    from brambleloop.cir.twin import row_width_cm
    g = Gauge(14.5, 9.5, stitch_type="hdc")                 # no chain gauge
    cir = CIR(slug="s", title="S", version="1.0.0", construction="flat_rows", gauge=g,
              components=[Component("p", "flat_rows",
                                    [Row(index=1, ops=[Op("hdc", 10), Op("ch", 5)],
                                         declared_count=15)], foundation=10)])
    r = compile_cir(cir)
    _, caveat = row_width_cm(r.rows[0], g)
    assert "chain gauge" in caveat and "over-estimate" in caveat
    # And with a chain gauge stated, nothing is assumed.
    g2 = Gauge(14.5, 9.5, stitch_type="hdc", chains_per_10cm=18.4)
    _, caveat2 = row_width_cm(r.rows[0], g2)
    assert caveat2 == ""


# ---- placement in object space -------------------------------------------

def test_grain_decides_which_way_a_panel_lies_on_the_object():
    """Same counts, different object. Reading them without grain transposes the garment."""
    c, twins, geo = _built("S")
    body = geo.footprints["body"]
    assert body.grain == "across"
    # Worked sideways: the fabric's row direction runs AROUND the body, the stitch direction
    # runs UP it -- so the object is taller than the fabric's "height" suggests.
    assert body.up_cm == twins["body"].width_cm
    assert body.across_cm == twins["body"].height_cm


def test_a_join_compares_the_length_of_both_edges():
    c, twins, geo = _built("M")
    sleeve_join = next(j for j in geo.joins
                       if j.piece_a == "sleeve" and j.piece_b == "body")
    assert sleeve_join.length_a_cm and sleeve_join.length_b_cm
    assert sleeve_join.verdict == "sound", sleeve_join.why


def test_an_opening_is_a_feature_of_a_piece_not_one_of_its_outer_edges():
    """A sleeve joins a slit inside the body, not the body's side.

    The first edge vocabulary could only name a rectangle's four sides, so the sleeve was
    compared against the body's full height and a garment that assembles perfectly well was
    reported impossible.
    """
    c, twins, geo = _built("M")
    body = geo.footprints["body"]
    assert body.openings, "the armhole was not derived from the bridge chains"
    assert body.edge_cm("opening") == 2 * body.openings[0], (
        "a slit takes stitches down both sides, so the length sewn is twice the span")
    assert body.edge_cm("opening") != body.edge_cm("left")


def test_a_mismatched_join_is_reported_rather_than_eased_away():
    c = B.cardigan("M")
    c.assembly.append(Seam("whipstitch", "pocket", "neck_ribbing",
                           edge_a="top", edge_b="left"))
    r = compile_cir(c)
    twins = {x.name: build_twin(c, r, component=x.name) for x in c.components}
    geo = assembly.assemble(c, twins)
    assert geo.verdict == "does_not_assemble"
    assert geo.mismatched_joins


def test_an_unstated_join_stays_unchecked_instead_of_being_invented():
    """The pattern gives pocket placement only in a photograph, so nothing may assume it."""
    c, twins, geo = _built("S")
    pocket = next(j for j in geo.joins if j.piece_a == "pocket")
    assert pocket.verdict == "unchecked"
    assert "does not say which edges" in pocket.why
    assert geo.verdict == "partially_placed"


def test_a_derived_length_reports_indeterminate_rather_than_guessing():
    """A discrepancy inside the derivation's own error bars is not evidence either way.

    The armhole length comes from a chain gauge solved out of the pattern, good to about
    +-6%. At XS the sleeve-to-armhole difference falls inside that, so neither 'fits' nor
    'does not fit' is supportable and the check must say so.
    """
    c, twins, geo = _built("XS")
    join = next(j for j in geo.joins if j.piece_a == "sleeve" and j.piece_b == "body")
    assert join.verdict == "indeterminate", join.why
    assert "chain gauge" in join.why
    # A stated chain gauge removes the uncertainty and the verdict becomes a real one.
    c2 = B.cardigan("XS")
    c2.gauge.chain_gauge_uncertainty = 0.0
    r2 = compile_cir(c2)
    t2 = {x.name: build_twin(c2, r2, component=x.name) for x in c2.components}
    j2 = next(j for j in assembly.assemble(c2, t2).joins
              if j.piece_a == "sleeve" and j.piece_b == "body")
    assert j2.verdict in ("sound", "mismatched")


def test_pieces_sewn_onto_a_body_do_not_enlarge_its_silhouette():
    c, twins, geo = _built("S")
    assert geo.silhouette_across_cm == round(geo.footprints["body"].across_cm, 1)
    assert geo.silhouette_up_cm == round(geo.footprints["body"].up_cm, 1)


# ---- correspondence with the real garment --------------------------------

def test_the_photograph_comparison_never_reports_full():
    """Stitch-level truth is not obtainable from listing photography, ever.

    A comparison that could reach FULL from photographs alone would be claiming the evidence
    settles something it cannot.
    """
    c, twins, geo = _built("S")
    res = C.compare(c, geo, twins, size="S")
    assert res.verdict == "PARTIAL"
    assert res.counts.get(C.NOT_OBSERVABLE, 0) >= 1
    assert res.counts.get(C.CONTRADICTS, 0) == 0


def test_unobservable_characteristics_are_never_counted_as_agreement():
    c, twins, geo = _built("S")
    res = C.compare(c, geo, twins, size="S")
    for ch in res.characteristics:
        if not ch.observable_in_photography:
            assert ch.verdict == C.NOT_OBSERVABLE
            assert ch.observed == ""


def test_a_contradiction_is_decisive():
    c, twins, geo = _built("S")
    res = C.compare(c, geo, twins, size="S",
                    observations={"cuff gathering": ("not gathered at all",
                                                     "contradicts the prediction")})
    assert res.verdict == "CONTRADICTED"


def test_the_predictions_are_computed_and_carry_real_numbers():
    c, twins, geo = _built("S")
    named = {ch.name: ch.predicted for ch in C.predict(c, geo, twins)}
    assert "65 cm" in named["overall length"]
    assert "slip stitch" in named["sleeve volume"]
    assert "checkered" in named["body texture class"]
    assert "vertically" in named["texture direction"]


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
