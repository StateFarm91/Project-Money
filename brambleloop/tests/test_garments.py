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
