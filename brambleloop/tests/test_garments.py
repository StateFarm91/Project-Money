"""products/garments.py: two generic constructions, every sourced size, the whole chain.

Not one cardigan. Two constructions (a flat drop-shoulder pullover with a bridged neck, and a
top-down raglan with held sleeves), each run over a full published size run, plus a third
design from the drop-shoulder template on a different body table, gauge and stitch to show
the template is a template. And the firewall: nothing here is read from a benchmark.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import assembly, specification  # noqa: E402
from brambleloop.cir import graded as GR  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import Gauge, Material  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402


def _third_design() -> GR.GradedDesign:
    """The drop-shoulder template again: child sizes, double crochet, a different gauge."""
    family = G.StitchFamily("dc", "plain")
    key, title = "test-child-drop-shoulder", "Test Child Drop Shoulder"
    return GR.GradedDesign(
        key=key, title=title, table=GR.CHILD, gauge=Gauge(14, 8, stitch_type="dc"),
        fit=GR.FitIntent({"bust": 12, "back_length": 8, "armhole_depth": 3,
                          "upper_arm": 6}),
        requires=G.DROP_SHOULDER_REQUIRES,
        template=lambda g: G.drop_shoulder_flat(g, key=key, title=title, family=family,
                                                material=Material("dk cotton")))


def _designs():
    return [G.harbour_pullover(), G.pebble_cardigan(), _third_design()]


def _twins(cir, result):
    return {c.name: build_twin(cir, result, component=c.name) for c in cir.components}


# ---- the firewall -------------------------------------------------------------------------


def test_garments_does_not_import_the_benchmarks():
    tree = ast.parse(Path(G.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.module or "") + ":" + ",".join(a.name for a in node.names))
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not [i for i in imported if "benchmark" in i or "research" in i], imported
    # And at runtime: importing and building every garment never loads the module.
    code = ("import sys; sys.path.insert(0, 'src');"
            "from brambleloop.products import garments as G;"
            "[d().build_all() for d in G.DESIGNS.values()];"
            "print('brambleloop.cir.benchmarks' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                         text=True, check=True)
    assert out.stdout.strip() == "False", out.stdout + out.stderr


def test_no_garment_matches_a_benchmark_and_each_states_its_provenance():
    for design in _designs():
        for size, cir in design.build_all().items():
            assert specification.benchmark_matches(cir) == [], (cir.slug)
            assert cir.authored == "brambleloop"
            assert cir.provenance.concept_key == design.key
            assert cir.provenance.benchmarks_consulted == ()


# ---- the full chain, every sourced size ----------------------------------------------------


def test_every_size_of_every_design_passes_the_whole_chain():
    for design in _designs():
        sizes = design.sourced_sizes()
        assert sizes == design.table.names, (design.key, sizes)
        for size, cir in design.build_all().items():
            result = compile_cir(cir)
            assert result.ok, (cir.slug, [str(f) for f in result.errors])
            for term in ("US", "UK"):
                text = write_pattern(cir, result, term)
                assert compare(cir, text, term) == [], (cir.slug, term)
            assert specification.reconstructive_gaps(cir) == [], cir.slug
            geo = assembly.assemble(cir, _twins(cir, result))
            assert geo.verdict == "assembles", (cir.slug, geo.why)
            cert = certify(cir)
            assert cert.granted, (cir.slug, cert.blocking_reasons)
            assert {"specification", "assembly"} <= set(cert.stages_run)


def test_sizes_grow_monotonically_and_hit_their_intended_chest():
    for design in _designs():
        design.check_monotonic()
        chests = []
        for size, cir in design.build_all().items():
            g = design.graded_size(size)
            first = cir.components[0]
            if design.key.startswith("pebble"):
                # Back plus two fronts after the division is the whole chest.
                body_row = next(r for r in first.rows if r.skips)
                sts = body_row.declared_count
            else:
                sts = 2 * first.foundation
            chest_cm = sts / g.gauge.stitches_per_10cm * 10
            want = g.finished_cm("bust")
            assert abs(chest_cm - want) / want < 0.03, (cir.slug, chest_cm, want)
            chests.append(chest_cm)
        assert chests == sorted(chests), (design.key, chests)


def test_the_two_constructions_are_different_garments():
    pullover = G.harbour_pullover().build("M")
    cardigan = G.pebble_cardigan().build("6")
    assert {c.name for c in pullover.components} == {"body", "sleeve", "neckband"}
    assert {c.name for c in cardigan.components} == {"yoke_and_body", "sleeve_left",
                                                      "sleeve_right"}
    assert any(c.holds for c in cardigan.components)
    assert not any(c.holds for c in pullover.components)
    assert any(getattr(o, "spans", 0) for r in pullover.components[0].rows for o in r.ops)
    assert any(o.loop == "back" for r in pullover.components[0].rows for o in r.ops)


def test_the_sleeve_top_meets_the_body_side_it_is_sewn_to():
    for size, cir in G.harbour_pullover().build_all().items():
        geo = assembly.assemble(cir, _twins(cir, compile_cir(cir)))
        join = next(j for j in geo.joins if j.piece_a == "sleeve" and j.piece_b == "body")
        assert join.verdict == "sound", (size, join.why)


def test_a_fitted_version_is_class_c_and_waits_for_a_physical_sample():
    """Relaxed ease is what lets these ship on computation; take it away and they cannot."""
    fitted = GR.GradedDesign(
        key="fitted", title="Fitted", table=GR.WOMAN, gauge=Gauge(16, 18),
        fit=GR.FitIntent({"bust": 4, "back_length": 10, "armhole_depth": 3, "upper_arm": 4}),
        requires=G.DROP_SHOULDER_REQUIRES,
        template=lambda g: G.drop_shoulder_flat(g, key="fitted", title="Fitted Pullover",
                                                family=G.StitchFamily(),
                                                material=Material("worsted wool")))
    cir = fitted.build("M")
    assert cir.risk_class == "C"
    cert = certify(cir)
    assert not cert.granted
    assert "PHYSICAL_TEST_REQUIRED" in {f.code for f in cert.errors}


def test_the_round_trip_fixture_list_includes_the_garments():
    from tests.test_cir_roundtrip import every_design
    names = {n for n, _ in every_design()}
    assert "garment-harbour-drop-shoulder-pullover-5x" in names
    assert "garment-pebble-raglan-cardigan-2" in names


# ---- certification audit repairs ----------------------------------------------------------


def _raglan_matrix():
    """Pebble plus the raglan template over both tables, both fabrics, relaxed and close."""
    out = [G.pebble_cardigan()]
    for table in (GR.WOMAN, GR.CHILD):
        for stitch, gauge in (("sc", Gauge(16, 18, stitch_type="sc")),
                              ("dc", Gauge(14, 8, stitch_type="dc"))):
            for ease in ({"bust": 4, "back_length": 4, "armhole_depth": 2, "upper_arm": 3},
                         {"bust": 32, "back_length": 12, "armhole_depth": 6,
                          "upper_arm": 12}):
                fam = G.StitchFamily(stitch, "plain")
                key = f"t-{table.name[:5]}-{stitch}-{ease['bust']}".replace(" ", "")
                out.append(GR.GradedDesign(
                    key=key, title=key, table=table, gauge=gauge, fit=GR.FitIntent(ease),
                    requires=G.RAGLAN_REQUIRES, measure=G.built_measures,
                    template=lambda g, fam=fam, key=key: G.raglan_top_down(
                        g, key=key, title=key, family=fam, material=Material("yarn"))))
    return out


def test_raglan_neck_fits_the_body_at_every_size():
    """C-7: the neck edge is a stated ratio of the cross-back, the yoke grows to the chest by
    as many increases per raglan line per row as it needs, and the neck lands inside the
    plausibility floor at every size of every combination."""
    worst = 0.0
    for d in _raglan_matrix():
        for size, cir in d.build_all().items():
            g = d.graded_size(size)
            geo = specification.yoke_geometry(cir)
            ratio = geo["neck_edge"] / geo["chest"]
            worst = max(worst, ratio)
            assert ratio <= specification.MAX_NECK_EDGE_OF_CHEST, (d.key, size, ratio)
            back_neck_cm = geo["back_neck"] / g.gauge.stitches_per_10cm * 10
            assert back_neck_cm <= g.body_cm("cross_back"), (d.key, size, back_neck_cm)
            f, sl, b, sr, f2 = geo["sections_at_neck"]
            assert f == f2 and sl == sr >= G.MIN_SLEEVE_AT_NECK and b == 2 * f, (d.key, size)
    print(f"     raglan neck edge / chest, worst {worst:.2f}")


def test_raglan_increases_follow_the_standard_eight_per_unit():
    """Each increase unit is one either side of each of the four lines (8 stitches); tall
    rows get more than one unit per row rather than a yoke that cannot grow."""
    d = G.pebble_cardigan()
    for size, cir in d.build_all().items():
        r = compile_cir(cir)
        yoke = cir.components[0]
        counts = [yoke.foundation] + [x.produced for x in r.rows if x.component == yoke.name]
        first_body = next(row.index for row in yoke.rows if row.skips)
        steps = [b - a for a, b in zip(counts, counts[1:first_body])]
        assert all(step % 8 == 0 and step >= 0 for step in steps), (size, steps)
        assert max(steps) >= 16, (size, steps)       # dc rows are tall: doubled increases


def test_built_length_never_falls_between_sizes():
    """C-10: the whole length is rounded once, so a longer requested length never builds
    shorter; and the graded check measures what was BUILT."""
    for d in _raglan_matrix() + [G.harbour_pullover()]:
        d.check_monotonic()
        lengths = [G.built_measures(c)["length"] for c in d.build_all().values()]
        assert lengths == sorted(lengths), (d.key, lengths)


def test_built_monotonic_check_catches_a_built_regression():
    """A template that builds a shorter garment at a larger size is refused by the graded
    check even though every requested figure rises."""
    d = G.pebble_cardigan()
    real = d.template

    def shrinking(g):
        cir = real(g)
        if g.size == "16":
            yoke = cir.components[0]
            yoke.rows = yoke.rows[:-6]
        return cir
    bad = GR.GradedDesign(key=d.key, title=d.title, table=d.table, fit=d.fit, gauge=d.gauge,
                          template=shrinking, requires=d.requires, measure=G.built_measures)
    bad.check_monotonic(built=False)
    try:
        bad.check_monotonic()
        raise AssertionError("a built regression passed")
    except GR.GradingRefused as exc:
        assert "built length" in str(exc)


def test_the_neckband_join_is_placed_at_the_neck_row_and_the_gates_agree():
    """C-9: the specification gate and the compiler agree the neckband's join is placed."""
    for d in (G.harbour_pullover(), _third_design()):
        for size, cir in d.build_all().items():
            seam = next(s for s in cir.assembly if s.piece_a == "neckband"
                        and s.piece_b == "body")
            bridge = [r.index for r in cir.components[0].rows
                      if any(getattr(o, "spans", 0) for o in r.ops)]
            assert seam.at_round == bridge[0] and seam.spans_rounds == 1, (d.key, size)
            codes = {f.code for f in compile_cir(cir).findings}
            assert "ASSEMBLY_UNPLACED" not in codes, (d.key, size)
            assert specification.reconstructive_gaps(cir) == []


def test_a_join_onto_a_flat_pieces_single_opening_is_located_by_the_opening():
    """The compiler agrees with the specification gate even when the seam states no row:
    a flat piece with exactly one bridged opening says where its opening join goes. A
    genuinely unplaced join between two pieces still warns, in words about pieces."""
    cir = G.harbour_pullover().build("M")
    seam = next(s for s in cir.assembly if s.edge_b == "opening")
    seam.at_round = None
    assert "ASSEMBLY_UNPLACED" not in {f.code for f in compile_cir(cir).findings}
    seam.edge_b = "left"
    warn = [f for f in compile_cir(cir).findings if f.code == "ASSEMBLY_UNPLACED"]
    assert warn and "ears" not in str(warn[0]) and "one piece goes on the other" in str(warn[0])


def test_textures_are_loop_patterns_the_writer_round_trips():
    for texture in G.TEXTURES:
        fam = G.StitchFamily("sc", texture)
        loops = {fam.loop(i) for i in range(1, 5)}
        assert loops <= {"both", "back", "front"}
    assert G.StitchFamily("sc", "ridged").loop(2) == "back"      # Harbour's fabric unchanged
    assert G.StitchFamily("sc", "ridged").loop(1) == "both"
    try:
        G.StitchFamily("sc", "bobbled")
        raise AssertionError("an invented texture was accepted")
    except G.ShapingRefused:
        pass


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
