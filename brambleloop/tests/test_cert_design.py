"""Adversarial certification: can Brambleloop autonomously design original products?

Tries to FALSIFY the claim. Fresh seeds (none reused from tests/test_garment_design.py), ten
materially different concepts across garments and non-garments, every one taken through
author -> compile -> write (US+UK) -> reverse -> certify -> release. Then the firewall: does
anything benchmark-derived leak in, and does the specification gate catch a benchmark in our
clothes -- including a partial one.

Failing checks here are findings, not flakes. Do not weaken them to get green.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.cir import assembly  # noqa: E402
from brambleloop.cir import benchmarks as B  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir import specification as S  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.creative import certification as CE  # noqa: E402
from brambleloop.creative import garment_design as GD  # noqa: E402
from brambleloop.creative import prototype as P  # noqa: E402
from brambleloop.creative.concept import Concept, ConceptRefused  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402


def K(key, form, construction, recipient="self", lane="MEDIUM", pod="home", *,
      motif="bark lattice", feeling="rugged", occasion="everyday",
      premise="a lattice of offset ridges that reads as woven bark from across a room",
      function="holds warmth where it is needed", palette="moss and slate", title=None):
    return Concept(key=key, title=title or key.replace("-", " ").title(), premise=premise,
                   pod=pod, form=form, construction=construction, motif=motif,
                   palette_story=palette, recipient=recipient, occasion=occasion,
                   feeling=feeling, function=function, make_lane=lane, provenance="cert-test")


# Ten fresh seeds. Garments: raglan (adult LONG, child QUICK), drop-shoulder via side_to_side
# (adult SHORT), bottom_up (teen FLAGSHIP), flat_rows (partner MEDIUM). Non-garments: throw,
# basket, hat, coaster, pillow, scarf.
GARMENTS = [
    K("fjord-raglan", "fitted_garment", "top_down_yoke", "partner", "LONG", "garments"),
    K("sprout-raglan", "fitted_garment", "top_down_yoke", "child", "QUICK", "garments"),
    K("quarry-drop", "fitted_garment", "side_to_side", "self", "SHORT", "garments"),
    K("acorn-drop", "fitted_garment", "bottom_up", "teen", "FLAGSHIP", "garments"),
    K("cairn-drop", "fitted_garment", "flat_rows", "grandparent", "MEDIUM", "garments"),
]
OTHERS = [
    K("heath-throw", "rectangle_throw", "flat_rows"),
    K("reed-basket", "basket", "in_the_round"),
    K("ember-hat", "hat", "in_the_round", pod="hats"),
    K("slate-coaster", "coaster", "flat_rows", lane="QUICK"),
    K("loch-pillow", "pillow", "corner_to_corner"),
    K("birch-scarf", "scarf", "side_to_side", lane="LONG"),
]
ALL = GARMENTS + OTHERS


def _db():
    from brambleloop.core.db import Database
    db = Database("sqlite://")
    db.create_all()
    return db


def _counts(cir) -> dict:
    r = compile_cir(cir)
    assert r.ok, [str(e) for e in r.errors][:2]
    return {c.name: (c.foundation,) + tuple(x.produced for x in r.rows if x.component == c.name)
            for c in cir.components}


# ---- A. autonomous design from fresh seeds -------------------------------------------------

def test_every_fresh_concept_compiles_writes_reverses_and_certifies():
    bad = []
    for c in ALL:
        cir = P.author(c)
        r = compile_cir(cir)
        if not r.ok:
            bad.append((c.key, "compile", [str(e) for e in r.errors][:1])); continue
        for term in ("US", "UK"):
            diffs = compare(cir, write_pattern(cir, r, term), term)
            if diffs:
                bad.append((c.key, term, [str(d) for d in diffs][:1]))
        cert = certify(cir)
        if not cert.granted:
            bad.append((c.key, "certify", cert.blocking_reasons[:1]))
    assert not bad, bad


def test_prototype_stage_passes_all_ten_and_kills_nothing():
    out = P.prototype(list(ALL))
    assert out["killed"] == {}, out["killed"]
    assert [c.key for c in out["survivors"]] == [c.key for c in ALL]


def test_release_chain_grants_all_ten():
    out = CE.release(_db(), list(ALL))
    assert not out["killed"], {k: out["detail"][k] for k in out["killed"]}
    for c in ALL:
        d = out["detail"][c.key]
        assert d["granted"] is True, (c.key, d)
        for stage in ("compile", "specification", "twin", "assembly", "reverse", "policy",
                      "asset_truth"):
            assert stage in d["stages_run"], (c.key, stage)


def test_fresh_raglan_survives_whole_release_chain_at_every_size():
    """Reproduce the headline claim from a seed unlike tide-raglan: adult, LONG, sc worsted."""
    c = GARMENTS[0]
    out = CE.release(_db(), [c])
    assert [x.key for x in out["survivors"]] == ["fjord-raglan"], out["detail"]
    design = GD.design_for(c)
    built = design.build_all()
    assert len(built) == 9, list(built)
    for size, cir in built.items():
        cert = certify(cir)
        assert cert.granted, (size, cert.blocking_reasons[:2])
        r = compile_cir(cir)
        for term in ("US", "UK"):
            assert not compare(cir, write_pattern(cir, r, term), term), (size, term)


def test_drop_shoulder_from_concept_assembles_at_every_size():
    for c in GARMENTS[2:]:
        design = GD.design_for(c)
        _vac_139 = 0
        for size, cir in design.build_all().items():
            _vac_139 += 1
            assert [x.name for x in cir.components] == ["body", "sleeve", "neckband"], size
            cert = certify(cir)
            assert cert.granted, (c.key, size, cert.blocking_reasons[:2])
            assert "assembly" in cert.stages_run
            assert not any(f.code.startswith("ASSEMBLY") and f.is_error
                           for f in cert.findings), (c.key, size)
            r = compile_cir(cir)
            geo = assembly.assemble(cir, {x.name: build_twin(cir, r, component=x.name)
                                          for x in cir.components})
            assert geo.verdict == "assembles", (c.key, size, geo.verdict, geo.why)
        assert _vac_139, "design.build_all().items() was empty: the loop proved nothing (F-123)"


def test_drop_shoulder_neckband_join_is_placed():
    """The specification gate accepts the neckband->body 'opening' join as placed; the
    compiler warns the same join is UNPLACED, in a message about 'ears'. One of them is wrong."""
    c = GARMENTS[2]
    cir = GD.design_for(c).build("M")
    warn = [str(f) for f in compile_cir(cir).findings if f.code == "ASSEMBLY_UNPLACED"]
    assert S.reconstructive_gaps(cir) == []
    assert not warn, warn


def test_garment_provenance_names_the_concept_and_no_benchmark():
    for c in GARMENTS:
        cir = P.author(c)
        assert cir.authored == "brambleloop"
        assert cir.provenance is not None and cir.provenance.concept_key == c.key, c.key
        assert tuple(cir.provenance.benchmarks_consulted) == (), c.key
        for size, one in GD.design_for(c).build_all().items():
            assert one.provenance.concept_key == c.key and not one.provenance.benchmarks_consulted
            assert S.benchmark_matches(one) == [], (c.key, size)


def test_routing_dimensions_produce_different_garments():
    """Construction, recipient and lane must change stitch family, gauge, table and counts."""
    base = K("x-a", "fitted_garment", "top_down_yoke", "self", "LONG", "garments")
    variants = {
        "construction": K("x-b", "fitted_garment", "flat_rows", "self", "LONG", "garments"),
        "recipient": K("x-c", "fitted_garment", "top_down_yoke", "child", "LONG", "garments"),
        "lane": K("x-d", "fitted_garment", "top_down_yoke", "self", "QUICK", "garments"),
    }
    d0 = GD.design_for(base)
    t0 = _counts(d0.build(GD.base_size(d0)))
    for dim, v in variants.items():
        d = GD.design_for(v)
        t = _counts(d.build(GD.base_size(d)))
        assert t != t0, f"changing {dim} did not change the stitch tables"
    assert GD.design_for(variants["lane"]).gauge.stitch_type != d0.gauge.stitch_type
    assert GD.design_for(variants["recipient"]).table is not d0.table
    assert [c.name for c in GD.design_for(variants["construction"]).build("M").components] \
        != [c.name for c in d0.build("M").components]


def test_non_routing_concept_fields_change_the_product():
    """ORIGINALITY PROBE. Two concepts that differ in motif, feeling, occasion, function,
    palette, premise and title -- distance() calls them distinct ideas -- must not become the
    same garment under two names. And a fresh child/quick raglan concept must not be the
    existing Pebble fixture's stitch tables."""
    from brambleloop.creative.concept import distance
    a = K("lantern-raglan", "fitted_garment", "top_down_yoke", "self", "LONG", "garments",
          motif="lantern windows", feeling="festive", occasion="christmas",
          premise="a yoke of glowing window panes that reads as a lit street at dusk",
          function="a party layer", palette="ember and soot")
    b = K("tidepool-raglan", "fitted_garment", "top_down_yoke", "self", "LONG", "garments",
          motif="tidepool ripples", feeling="serene", occasion="summer_travel",
          premise="concentric ripples spreading from the collar like a stone dropped in water",
          function="a beach cover-up", palette="sea glass")
    assert distance(a, b) >= 0.3, distance(a, b)
    ta = {s: list(_counts(c).values()) for s, c in GD.design_for(a).build_all().items()}
    tb = {s: list(_counts(c).values()) for s, c in GD.design_for(b).build_all().items()}
    same = [s for s in ta if ta[s] == tb[s]]
    pebble = G.pebble_cardigan().build_all()
    sprout = GD.design_for(GARMENTS[1]).build_all()
    pebble_same = [s for s in sprout
                   if list(_counts(sprout[s]).values()) == list(_counts(pebble[s]).values())]
    assert not same and not pebble_same, (
        f"distinct concepts (distance {distance(a, b)}) yield identical stitch tables at "
        f"{len(same)}/{len(ta)} sizes; fresh 'sprout-raglan' concept is the Pebble fixture's "
        f"tables at {len(pebble_same)}/{len(sprout)} sizes")


def test_impossible_inputs_refuse_with_a_named_reason():
    cases = [
        (K("bb", "fitted_garment", "top_down_yoke", "new_parent", pod="garments"), "babywear"),
        (K("gs", "fitted_garment", "granny_square", pod="garments"), "engine gap"),
        (K("ms", "fitted_garment", "motif_join", "child", pod="garments"), "engine gap"),
        (K("sh", "draped_garment", "flat_rows"), "no finished size"),
        (K("ty", "toy", "amigurumi_shaping"), "no finished size"),
        (K("wr", "wreath", "in_the_round"), "no finished size"),
    ]
    for c, word in cases:
        try:
            P.author(c)
            raise AssertionError(f"{c.key} was authored, not refused")
        except P.PrototypeRefused as exc:
            assert word in str(exc), (c.key, str(exc))
    out = P.prototype([c for c, _ in cases])
    assert set(out["killed"]) == {c.key for c, _ in cases}
    assert all(v == "unverifiable" for v in out["killed"].values())
    # Garment refusal also reaches GD.design_for directly, and non-garment forms are not graded.
    try:
        GD.design_for(OTHERS[0]); raise AssertionError("throw was graded")
    except GD.GarmentDesignRefused as exc:
        assert "not a garment form" in str(exc)
    # Closed vocabulary.
    try:
        K("nice", "fitted_garment", "top_down_yoke", feeling="nice")
        raise AssertionError("open vocabulary accepted")
    except ConceptRefused:
        pass


def test_fitted_premise_is_class_c_and_blocked_without_physical_test():
    c = K("sheath-raglan", "fitted_garment", "top_down_yoke", "self", "LONG", "garments",
          premise="a fitted cropped yoke that sits close through the shoulders")
    cir = P.author(c)
    assert cir.risk_class == "C"
    cert = certify(cir)
    assert not cert.granted and any(f.code == "PHYSICAL_TEST_REQUIRED" for f in cert.findings)


# ---- B. benchmark leakage -----------------------------------------------------------------

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mod = ("." * node.level) + (node.module or "")
            out.add(mod)
            out |= {f"{mod}.{a.name}" for a in node.names}
    return out


def test_garment_modules_import_nothing_from_benchmarks_or_research():
    for rel in ("src/brambleloop/products/garments.py",
                "src/brambleloop/creative/garment_design.py"):
        imps = _imports(ROOT / rel)
        bad = [i for i in imps if "benchmark" in i or "research" in i]
        assert not bad, (rel, bad)
    code = ("import sys; sys.path.insert(0, 'src');"
            "import brambleloop.products.garments, brambleloop.creative.garment_design as g;"
            "from brambleloop.creative.concept import Concept;"
            "c=Concept(key='k',title='T',premise='a boxy striped yoke that reads as seaside',"
            "pod='garments',form='fitted_garment',construction='top_down_yoke',motif='m',"
            "palette_story='p',recipient='self',occasion='everyday',feeling='bold',"
            "function='f',make_lane='LONG');"
            "g.design_for(c).build_all();"
            "print('\\n'.join(sorted(m for m in sys.modules if 'benchmark' in m "
            "or 'research' in m)))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "", f"loaded after import+build: {out.stdout.split()}"


def test_benchmark_relabelled_as_ours_is_refused():
    cir = B.cardigan("M")
    assert S.benchmark_matches(cir)          # a record matches itself
    S.refuse_a_benchmark_in_our_clothes(cir)  # but a benchmark itself passes
    cir.authored = "brambleloop"
    cir.slug, cir.title = "meadow-cardigan-m", "Meadow Cardigan"
    try:
        S.refuse_a_benchmark_in_our_clothes(cir)
        raise AssertionError("relabelled benchmark not refused")
    except S.BenchmarkDerived:
        pass
    cert = certify(cir)
    assert not cert.granted and any(f.code == "BENCHMARK_DERIVED" for f in cert.findings)


def test_partial_benchmark_relabelled_as_ours_is_refused():
    """FIREWALL PROBE. The benchmark's body and sleeve, stitch-for-stitch, relabelled as ours
    with the pocket and neck ribbing left out; and separately the whole benchmark with its last
    row of each identifying piece removed. Either is a benchmark in our clothes."""
    partial = B.cardigan("M")
    partial.authored, partial.slug, partial.title = ("brambleloop", "meadow-cardigan-m",
                                                     "Meadow Cardigan")
    partial.components = [c for c in partial.components if c.name in ("body", "sleeve")]
    partial.assembly = [s for s in partial.assembly if s.piece_a in ("body", "sleeve")]
    trimmed = B.cardigan("M")
    trimmed.authored = "brambleloop"
    for comp in trimmed.components:
        if len(comp.rows) > S.MIN_IDENTIFYING_ROWS:
            comp.rows = comp.rows[:-1]
    problems = []
    if not S.benchmark_matches(partial):
        cert = certify(partial)
        problems.append(f"body+sleeve only: benchmark_matches=[] and certify granted="
                        f"{cert.granted}")
    if not S.benchmark_matches(trimmed):
        problems.append("last row of each piece dropped: benchmark_matches=[]")
    assert not problems, problems


# ---- runner -------------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items(), key=lambda kv: 0)
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}  -- {type(exc).__name__}: {str(exc)[:600]}")
            if os.environ.get("CERT_TRACE"):
                traceback.print_exc()
    print(f"\n  {len(tests) - failed} passing, {failed} failing")
    sys.exit(1 if failed else 0)
