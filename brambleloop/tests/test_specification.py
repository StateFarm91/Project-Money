"""What a Brambleloop design must state, and what a benchmark may leave out.

The owner's rule generalised: a construction fact that materially determines the finished
object belongs in the authoritative source, not in a photograph. The asymmetry between our
designs and our records of other people's is the load-bearing part.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir import benchmarks as B, specification as S
from brambleloop.cir.model import Material
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



# ---- a benchmark in our clothes: numeric containment ---------------------------------------


def test_the_benchmark_relabelled_as_brambleloop_is_refused_at_every_size():
    for size in B.SIZES:
        cardigan = B.cardigan(size)
        cardigan.authored = "brambleloop"
        cardigan.slug, cardigan.title = "our-new-cardigan", "Our New Cardigan"
        try:
            S.refuse_a_benchmark_in_our_clothes(cardigan)
        except S.BenchmarkDerived as e:
            assert size in str(e) and "never a source" in str(e)
        else:
            raise AssertionError(f"size {size} passed as Brambleloop's own")


def test_renaming_the_pieces_does_not_launder_the_counts():
    from brambleloop.cir.model import Provenance
    cardigan = B.cardigan("L")
    cardigan.authored = "brambleloop"
    cardigan.provenance = Provenance("fresh-idea", "x", ("grading",), ())
    for i, comp in enumerate(cardigan.components):
        comp.name = f"piece_{i}"
    cardigan.assembly = []
    assert S.benchmark_matches(cardigan)


def test_the_benchmark_itself_passes_because_it_is_what_it_says_it_is():
    S.refuse_a_benchmark_in_our_clothes(B.cardigan("M"))


def test_no_catalogue_product_matches_a_benchmark():
    for slug in sorted(CATALOGUE):
        assert S.benchmark_matches(for_slug(slug)) == [], slug


# ---- the firewall hardened (certification audit C-6) --------------------------------------


def _ours(cir):
    cir.authored, cir.slug, cir.title = "brambleloop", "meadow-cardigan", "Meadow Cardigan"
    return cir


def test_any_one_identifying_benchmark_piece_is_refused_on_its_own():
    """Keeping only some pieces of a benchmark is still carrying a benchmark's piece."""
    for keep in ("body", "sleeve", "pocket", "neck_ribbing"):
        cir = _ours(B.cardigan("M"))
        cir.components = [c for c in cir.components if c.name == keep]
        cir.assembly = []
        matches = S.benchmark_matches(cir)
        assert matches and any(keep in m["pieces"] for m in matches), keep
        try:
            S.refuse_a_benchmark_in_our_clothes(cir)
            raise AssertionError(f"{keep} alone was not refused")
        except S.BenchmarkDerived:
            pass


def test_trimming_or_padding_a_few_rows_does_not_evade_the_firewall():
    from brambleloop.cir.model import Row
    for size in ("XS", "M", "5XL"):
        for cut in (1, 2):
            trimmed = _ours(B.cardigan(size))
            for comp in trimmed.components:
                if len(comp.rows) > S.MIN_IDENTIFYING_ROWS:
                    comp.rows = comp.rows[:-cut]
            assert S.benchmark_matches(trimmed), (size, cut)
        # one row taken out of the middle of the body's longest run
        body = _ours(B.cardigan(size))
        rows = body.components[0].rows
        mid = len(rows) // 2
        body.components = [body.components[0]]
        body.components[0].rows = [Row(index=i + 1, ops=r.ops, declared_count=r.declared_count,
                                       turning_chain=r.turning_chain, skips=r.skips,
                                       allow_remainder=r.allow_remainder)
                                   for i, r in enumerate(rows[:mid] + rows[mid + 1:])]
        body.assembly = []
        assert any(m["tiers"].get("body") == "counts" for m in S.benchmark_matches(body)), size


def test_the_counts_tier_survives_relabelling_the_stitch():
    """A body re-worked in another stitch with the same per-row counts is still the body."""
    from brambleloop.cir.model import Op, Repeat
    cir = _ours(B.cardigan("L"))
    cir.components = [cir.components[0]]
    cir.assembly = []

    def swap(nodes):
        for n in nodes:
            if isinstance(n, Repeat):
                swap(n.ops)
            elif isinstance(n, Op) and n.stitch == "hdc":
                n.stitch = "sc"
    for row in cir.components[0].rows:
        swap(row.ops)
    assert any(m["tiers"].get("body") == "counts" for m in S.benchmark_matches(cir))


def test_a_plain_rectangle_of_the_benchmark_sleeves_width_is_not_a_match():
    """The sleeve is a 64-stitch rectangle: counts alone would refuse every 64-stitch
    rectangle anyone writes. Our own plain one is not the benchmark's worked rows."""
    from brambleloop.cir.model import CIR, Component, Gauge, Op, Row
    for stitch in ("sc", "hdc"):
        rows = [Row(index=i, ops=[Op(stitch, 64)], declared_count=64, turning_chain=1)
                for i in range(1, 60)]
        cir = CIR(slug="plain-64", title="Plain", version="1.0.0", construction="flat_rows",
                  components=[Component("panel", "flat_rows", rows, foundation=64)],
                  gauge=Gauge(16, 18))
        assert S.benchmark_matches(cir) == [], stitch
    # and a 94-wide rectangle is not the 94-wide body: the body's armhole rows are missing
    rows = [Row(index=i, ops=[Op("hdc", 94)], declared_count=94, turning_chain=1)
            for i in range(1, 140)]
    cir = CIR(slug="plain-94", title="Plain", version="1.0.0", construction="flat_rows",
              components=[Component("panel", "flat_rows", rows, foundation=94)],
              gauge=Gauge(16, 18))
    assert S.benchmark_matches(cir) == []


def test_the_firewall_thresholds_are_stated():
    assert S.MIN_IDENTIFYING_ROWS == 10
    assert S.RUN_TOLERANCE_ROWS >= 2 and 0 < S.RUN_TOLERANCE_FRACTION <= 0.2
    assert S.MIN_COUNT_CHANGES == 2


def test_no_genuine_brambleloop_design_is_a_false_positive():
    """Every catalogue product, every Launch-0 build, every size of both garment fixtures and
    of a spread of concept-designed garments: none matches any benchmark piece."""
    from brambleloop.creative import garment_design as GD
    from brambleloop.creative.concept import Concept
    from brambleloop.products import garments as G, launch0
    from brambleloop.products import nordic_forest, texture, vessels
    cirs = [for_slug(s) for s in sorted(CATALOGUE)]
    cirs += [launch0.cir_for(k) for k in sorted(launch0.BUILDERS)]
    cirs += list(nordic_forest.all_sizes().values())
    cirs += [texture.build_cable_throw(), texture.build_bobble_pillow(),
             texture.build_ribbed_scarf(), vessels.build()]
    for make in G.DESIGNS.values():
        cirs += list(make().build_all().values())
    for i, (cons, rec, lane, feeling, pal) in enumerate((
            ("top_down_yoke", "self", "LONG", "rugged", "moss and slate"),
            ("top_down_yoke", "child", "QUICK", "festive", "ember and soot"),
            ("side_to_side", "self", "SHORT", "serene", "sea glass"),
            ("flat_rows", "teen", "MEDIUM", "folkloric", "cream, spruce and gold"))):
        c = Concept(key=f"fp-{i}", title=f"Fp {i}", premise="a lattice of offset ridges that reads as woven bark from across a room",
                    pod="garments", form="fitted_garment", construction=cons, motif="field",
                    palette_story=pal, recipient=rec, occasion="everyday", feeling=feeling,
                    function="a layer", make_lane=lane, provenance="test")
        cirs += list(GD.design_for(c).build_all().values())
    hits = [(c.slug, S.benchmark_matches(c)) for c in cirs if S.benchmark_matches(c)]
    assert not hits, hits[:3]
    assert len(cirs) > 60, len(cirs)


# ---- a garment that cannot be worn (certification audit C-7) ------------------------------


def _wide_neck_raglan():
    """A top-down raglan whose yoke barely grows: the pre-fix construction's failure."""
    from brambleloop.cir.model import CIR, Component, Gauge, Hold, Op, Row
    f, s, b = 20, 20, 40
    rows = [Row(index=1, ops=[Op("dc", 2 * f + 2 * s + b)], declared_count=2 * f + 2 * s + b,
                turning_chain=3),
            Row(index=2, ops=[Op("dc", 2 * f + b)], declared_count=2 * f + b, skips=2 * s,
                turning_chain=3)]
    comp = Component("yoke_and_body", "flat_rows", rows, foundation=2 * f + 2 * s + b,
                     holds=[Hold("sleeve_left", 1, s, from_stitch=f),
                            Hold("sleeve_right", 1, s, from_stitch=f + s + b)])
    return CIR(slug="wide-neck", title="Wide", version="1.0.0", construction="flat_rows",
               components=[comp], gauge=Gauge(14, 8, stitch_type="dc"))


def test_a_raglan_whose_neck_is_most_of_its_chest_is_refused():
    cir = _wide_neck_raglan()
    geo = S.yoke_geometry(cir)
    assert geo["sections_at_neck"] == [20, 20, 40, 20, 20] and geo["back_neck"] == 40
    problems = S.garment_implausibilities(cir)
    assert any("neck edge" in p for p in problems) and any("back neck" in p for p in problems)
    try:
        S.refuse_an_underspecified_design(cir)
        raise AssertionError("implausible yoke passed the specification gate")
    except S.GarmentImplausible:
        pass
    # a benchmark record is allowed to be what it is
    cir.authored = "benchmark"
    S.refuse_an_implausible_garment(cir)


def test_certification_and_grading_refuse_a_template_that_ships_a_wide_neck():
    """A future template aimed at a neck three times the shoulders: the template runs, and
    both the grading (body known) and certification (CIR alone) refuse what it made."""
    from brambleloop.cir.graded import GradedDesign
    from brambleloop.cir.grading import GradingRefused
    from brambleloop.gates.certificate import certify
    from brambleloop.products import garments as G
    pebble = G.pebble_cardigan()
    fam, mat = G.StitchFamily("dc", "plain"), Material("dk cotton")

    def wide(g):
        return G.raglan_top_down(g, key="wide", title="Wide", family=fam, material=mat,
                                 neck_of_cross_back=3.0)
    cir = wide(pebble.graded_size("8"))
    cert = certify(cir)
    assert not cert.granted and any("cannot be worn" in r for r in cert.blocking_reasons), \
        cert.blocking_reasons
    d = GradedDesign(key="wide", title="Wide", table=pebble.table, fit=pebble.fit,
                     gauge=pebble.gauge, template=wide, requires=G.RAGLAN_REQUIRES)
    try:
        d.build("8")
        raise AssertionError("grading built an unwearable neck")
    except GradingRefused as exc:
        assert "cannot be worn" in str(exc)


def test_a_back_neck_wider_than_the_cross_back_is_refused_when_the_body_is_known():
    cir = _wide_neck_raglan()
    back_neck_cm = 40 / 1.4
    assert any("cross-back" in p for p in
               S.garment_implausibilities(cir, cross_back_cm=back_neck_cm - 1))
    assert not any("cross-back" in p for p in
                   S.garment_implausibilities(cir, cross_back_cm=back_neck_cm + 1))


def test_the_neck_derivation_walks_real_increases_back_to_the_neck():
    from brambleloop.products import garments as G
    d = G.pebble_cardigan()
    for size in ("2", "16"):
        cir = d.build(size)
        geo = S.yoke_geometry(cir)
        f, sl, b, sr, f2 = geo["sections_at_neck"]
        assert (f, sl) == (f2, sr) and sum(geo["sections_at_neck"]) == geo["neck_edge"]
        assert geo["neck_edge"] / geo["chest"] <= S.MAX_NECK_EDGE_OF_CHEST
        assert geo["back_neck"] <= S.MAX_BACK_NECK_OF_BACK * geo["back_at_underarm"]


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
