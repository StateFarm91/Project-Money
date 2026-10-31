"""OPUS2-P0: P0-DRAFT-CONSTRUCTIONS -- a fallback draft is the construction its name promises.

W-CONCEPT's finding: the radar fallback (`concept_to_cir`) drafted every concept as one flat
striped panel. Every seed still reaching it is a shaped object, so a basket is now worked in
the round from the concept's own repeat and palette, and a form no fallback rule makes is
refused by name instead of drafted as a panel under its name.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_draft_constructions.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import dataclasses
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Repeat  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import PatternVersion, Product  # noqa: E402
from brambleloop.creative import fallback_constructions as F  # noqa: E402
from brambleloop.gates import originality as O  # noqa: E402
from brambleloop.radar.opportunity import POOL  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402

FALLBACK = [s for s in POOL if pipeline._engineered_cir(s.slug) is None]


def _db(slug):
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_dc_')}/d.sqlite")
    db.create_all()
    seed = pipeline._seed_for(slug)
    with db.session() as s:
        # An established earlier version: the real handler takes the fallback (as
        # test_fallback_draft_provenance sets it up).
        p = Product(slug=slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    return db, seed


def _payload(seed):
    out = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    out.update(pipeline.concept_geometry(seed))
    return out


def _draft(db, inputs):
    emitted, audits = [], []
    ctx = SimpleNamespace(db=db, job=SimpleNamespace(inputs=inputs),
                          audit=lambda action, **kw: audits.append((action, kw)),
                          enqueue=lambda role, kind, data, **kw: emitted.append((kind, data)))
    return pipeline.handle_cir_draft(ctx), emitted, audits


def test_every_fallback_seed_is_routed_and_none_is_a_shaped_object_on_a_panel():
    assert FALLBACK
    for seed in FALLBACK:
        route = F.plan(category=seed.category, title=seed.title, is_bundle=seed.is_bundle)
        assert route["family"] in (F.VESSEL, F.PANEL_PAIR, F.TRIANGLE, F.TOTE, F.REFUSED), \
            (seed.slug, route)
        if route["family"] == F.REFUSED:
            assert route["needs"] and route["why"], seed.slug
    assert F.plan(category="basket", title="Storage Basket")["family"] == F.VESSEL
    # Review OPUS2C N3.2: a granny square is a motif assembly, not one panel.
    assert F.plan(category="blanket", title="Granny Throw")["family"] == F.REFUSED
    assert F.plan(category="blanket", title="Everyday Throw")["family"] == F.FLAT_PANEL
    assert F.plan(category="blanket", title="Baby Hat")["family"] == F.REFUSED
    assert F.plan(category="pillow", title="Bobble Cushion")["family"] == F.PANEL_PAIR
    assert F.plan(category="wedding", title="Wedding Ring Cushion")["family"] == F.PANEL_PAIR
    # A cushion word never rescues a closed shape the panel pair does not make.
    assert F.plan(category="seasonal_decor", title="Egg Cosy Cushion")["family"] == F.REFUSED


def test_a_basket_concept_drafts_a_vessel_that_compiles_and_carries_the_concept():
    db, seed = _db("nordic-forest-basket")
    inputs = _payload(seed)
    result, emitted, audits = _draft(db, inputs)
    assert result["drafted"] is True and result["construction"] == F.VESSEL, result
    assert emitted[0][0] == "cir.compile"
    cir = CIR.from_dict(emitted[0][1]["cir"])
    assert cir.construction == "joined_rounds" and cir.components[0].foundation_kind == \
        "magic_ring"
    result = compile_cir(cir)
    assert result.ok
    # Review OPUS2C test gap: the vessel also twins and reverses cleanly.
    from brambleloop.cir import reverse
    from brambleloop.cir.twin import build_twin
    from brambleloop.cir.writer import write_pattern

    assert build_twin(cir, result) is not None
    assert reverse.compare(cir, write_pattern(cir, result, "US")) == []
    # The concept's own palette and stitch repeat are in the fabric, not a fixed table's.
    assert set(cir.colors) == set(inputs["colors"])
    used = {r.color for r in cir.components[0].rows}
    assert used == set(inputs["colors"]), used
    wanted = [tuple(x) for x in inputs["stitch_repeat"]]
    walls = [r for r in cir.components[0].rows
             if r.ops and isinstance(r.ops[0], Repeat)
             and [(o.stitch, o.count) for o in r.ops[0].ops] == wanted]
    assert walls, "the concept's repeat is worked in the walls"
    # Provenance names the producer that actually made it, and still binds the concept.
    prov = cir.provenance
    assert prov is not None and prov.concept_key == seed.slug
    assert set(F.VESSEL_PRIMITIVES) <= set(prov.primitives_used)
    assert f"runtime.pipeline.concept_geometry:{seed.category}" in prov.primitives_used
    codes = {f.code for f in O.provenance_findings(cir)}
    assert not codes & {"PROVENANCE_MISSING", "PROVENANCE_INCOMPLETE", "PROVENANCE_NOT_OURS"}
    drafted = [kw for a, kw in audits if a == "cir.drafted"]
    assert drafted[0]["detail"]["construction"] == F.VESSEL
    # Its title says "Mosaic" and one colour per round is relief, so publication's name-truth
    # rule will refuse it; the draft records that rather than hiding it.
    assert any("mosaic" in p for p in drafted[0]["detail"]["name_truth"]), drafted[0]
    assert drafted[0]["detail"]["provenance"] == "recorded"


def test_a_shaped_concept_is_refused_by_name_and_nothing_is_compiled():
    for slug in ("woodland-fox-amigurumi", "alpine-slouch-beanie",
                 "easter-egg-cosies", "lattice-triangle-shawl"):
        db, seed = _db(slug)
        result, emitted, audits = _draft(db, _payload(seed))
        assert result["drafted"] is False and emitted == [], (slug, result)
        refused = [kw for a, kw in audits if a == "cir.draft_refused"]
        assert refused and refused[0]["detail"]["gate"] == "construction", (slug, audits)
        assert refused[0]["detail"]["needs"], slug
    # A bundle never reaches the fallback: the handler turns it away earlier, unchanged.
    db, seed = _db("nordic-forest-bundle")
    result, emitted, _ = _draft(db, _payload(seed))
    assert result["drafted"] is False and result.get("is_bundle")
    assert [k for k, _ in emitted] == ["collection.assemble"]   # assembled, never drafted


def test_unknown_lineage_basket_is_still_drafted_without_provenance():
    """The route never invents lineage: geometry the table did not produce stays unknown."""
    db, seed = _db("nordic-forest-basket")
    inputs = _payload(seed)
    inputs["rows"] += 2
    result, emitted, audits = _draft(db, inputs)
    assert result["drafted"] is True
    cir = CIR.from_dict(emitted[0][1]["cir"])
    assert cir.provenance is None
    drafted = [kw for a, kw in audits if a == "cir.drafted"]
    assert drafted[0]["detail"]["provenance"].startswith("UNKNOWN")


def test_a_cushion_concept_drafts_two_seamed_panels_that_back_its_name():
    from brambleloop.products import launch0
    from brambleloop.publish import eligibility as E

    db, seed = _db("wedding-ring-cushion")
    inputs = _payload(seed)
    result, emitted, audits = _draft(db, inputs)
    assert result["drafted"] is True and result["construction"] == F.PANEL_PAIR, result
    cir = CIR.from_dict(emitted[0][1]["cir"])
    assert [c.name for c in cir.components] == ["front", "back"]
    assert compile_cir(cir).ok
    # Four seams, the last closed over the pad; every seam joins the front to the back.
    assert len(cir.assembly) == 4 and cir.assembly[-1].stuff_before_closing
    assert {(s.piece_a, s.piece_b) for s in cir.assembly} == {("front", "back")}
    assert {s.edge_a for s in cir.assembly} == {"left", "top", "right", "bottom"}
    # Both panels carry the concept's own repeat: the cover is the concept, twice.
    wanted = [tuple(x) for x in inputs["stitch_repeat"]]
    for comp in cir.components:
        assert any(isinstance(r.ops[0], Repeat)
                   and [(o.stitch, o.count) for o in r.ops[0].ops] == wanted
                   for r in comp.rows), comp.name
    # Name truth: "cushion" is an assembled form, and real seams back it.
    assert launch0.title_promise(cir)["backed"] is True
    assert E.name_truth(cir, None) == []
    drafted = [kw for a, kw in audits if a == "cir.drafted"]
    assert drafted[0]["detail"]["name_truth"] == []
    assert "cushion" in launch0.ASSEMBLED_FORMS and E.NAME_OUTRUNS_PATTERN
    prov = cir.provenance
    assert prov is not None and set(F.PANEL_PAIR_PRIMITIVES) <= set(prov.primitives_used)
    codes = {f.code for f in O.provenance_findings(cir)}
    assert not codes & {"PROVENANCE_MISSING", "PROVENANCE_INCOMPLETE", "PROVENANCE_NOT_OURS"}


def test_a_plain_triangle_shawl_drafts_and_a_named_stitch_pattern_is_refused():
    from brambleloop.gates.certificate import certify
    from brambleloop.publish import eligibility as E

    assert F.plan(category="shawl", title="Everyday Triangle Shawl")["family"] == F.TRIANGLE
    for title, word in (("Lattice Triangle Shawl", "lattice"),
                        ("Mother's Day Lace Shawlette", "lace"),
                        ("Cable Kerchief", "cable")):
        route = F.plan(category="shawl", title=title)
        assert route["family"] == F.REFUSED and word in route["needs"], (title, route)
    # Through the real handler: the radar's lattice shawl is refused by name, nothing compiled.
    db, seed = _db("lattice-triangle-shawl")
    result, emitted, audits = _draft(db, _payload(seed))
    assert result["drafted"] is False and result["gate"] == "construction" and emitted == []
    refused = [kw for a, kw in audits if a == "cir.draft_refused"]
    assert "lattice" in refused[0]["detail"]["needs"]
    # The construction itself, from a concept whose title names no stitch pattern.
    geo = pipeline.concept_geometry(seed)
    concept = pipeline.Concept(
        slug="everyday-triangle-shawl", title="Everyday Triangle Shawl", category="shawl",
        stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
        width_stitches=geo["width_stitches"], rows=geo["rows"], colors=geo["colors"],
        risk_class=seed.risk_class)
    cir = F.triangle(concept)
    assert compile_cir(cir).ok
    rows = cir.components[0].rows
    assert rows[0].declared_count == 3
    assert all(b.declared_count - a.declared_count == 2 for a, b in zip(rows, rows[1:]))
    assert {r.color for r in rows} == set(concept.colors)
    assert E.name_truth(cir, None) == []
    codes = {f.code for f in certify(cir).errors}
    assert codes <= {"PROVENANCE_MISSING"}, codes      # this unit build carries no lineage
    gauge = cir.gauge
    wingspan = rows[-1].declared_count * 10.0 / gauge.stitches_per_10cm
    assert abs(wingspan - F.SHAWL_WINGSPAN_CM) < 2.0, wingspan
    assert f"{wingspan:.0f} cm along the top edge" in cir.finished_size_note


def test_review_opus2c_n31_n32_several_sizes_and_shaped_categories_are_refused():
    # N3.1: the trio's premise is "in three sizes"; one draft is one size. Through the real
    # handler the radar's trio is a retired alias that drafts nothing itself: it routes to the
    # three engineered sizes, one release each. The fallback rule refuses it on its own too.
    db, seed = _db("market-basket-trio")
    result, emitted, audits = _draft(db, _payload(seed))
    assert result["drafted"] is False and result.get("retired_alias") is True, result
    assert len(result["routed_to"]) == 3, result
    assert not any(kind == "cir.compile" and data["cir"]["slug"] == seed.slug
                   for kind, data in emitted), emitted       # nothing drafted under "trio"
    route = F.plan(category=seed.category, title=seed.title, slug=seed.slug,
                   rationale=seed.rationale)
    assert route["family"] == F.REFUSED and "one certified release per size" in route["needs"]
    assert F.plan(category="basket", title="Market Basket Trio")["family"] == F.REFUSED
    assert F.plan(category="basket", title="Storage Basket",
                  rationale="Worked in three sizes")["family"] == F.REFUSED
    assert F.plan(category="basket", title="Storage Basket", slug="storage-basket-trio",
                  rationale="")["family"] == F.REFUSED
    assert F.plan(category="basket", title="Storage Basket")["family"] == F.VESSEL
    # N3.2: shaped or charted categories and titles never take the flat route.
    for category, title in (("ornament", "Star Ornament"), ("flower", "Daisy"),
                            ("blanket", "Hexagon Granny Blanket"), ("pet", "Cat Bed")):
        assert F.plan(category=category, title=title)["family"] == F.REFUSED, title
    assert F.plan(category="blanket", title="Everyday Throw")["family"] == F.FLAT_PANEL


def test_review_opus2c_n33_a_construction_that_cannot_be_built_is_a_named_refusal():
    db, seed = _db("nordic-forest-basket")
    inputs = {**_payload(seed), "colors": {}}          # a vessel needs a colour
    result, emitted, audits = _draft(db, inputs)
    assert result["drafted"] is False and result["gate"] == "construction", result
    assert emitted == [] and "colour" in result["reasons"][0]
    refused = [kw for a, kw in audits if a == "cir.draft_refused"]
    assert refused and refused[0]["detail"]["gate"] == "construction"


def test_a_tote_concept_drafts_a_vessel_with_two_measured_sewn_straps():
    from brambleloop.cir import reverse
    from brambleloop.cir.twin import build_twin
    from brambleloop.cir.writer import write_pattern
    from brambleloop.publish import eligibility as E

    db, seed = _db("everyday-market-tote")
    inputs = _payload(seed)
    result, emitted, audits = _draft(db, inputs)
    assert result["drafted"] is True and result["construction"] == F.TOTE, result
    cir = CIR.from_dict(emitted[0][1]["cir"])
    assert [c.name for c in cir.components] == ["basket", "strap"]
    strap = cir.components[1]
    assert strap.make == 2 and strap.rows[0].declared_count == F.STRAP_STITCHES
    res = compile_cir(cir)
    assert res.ok
    assert reverse.compare(cir, write_pattern(cir, res, "US")) == []
    assert build_twin(cir, res) is not None
    # Every strap end is measured against the rim span it is sewn across, and is sound:
    # certification refuses a join that does not sew together (ASSEMBLY_MISMATCH).
    from brambleloop.gates.certificate import certify

    codes = {f.code for f in certify(cir, db=db).errors}
    assert "ASSEMBLY_MISMATCH" not in codes and not codes & {
        "PROVENANCE_MISSING", "PROVENANCE_INCOMPLETE", "PROVENANCE_NOT_OURS"}, codes
    assert E.name_truth(cir, None) == []
    assert set(F.TOTE_PRIMITIVES) <= set(cir.provenance.primitives_used)
    text = write_pattern(cir, res, "US")
    n = cir.components[0].rows[-1].declared_count
    assert f"over stitch {n // 8} " in text and f"over stitch {3 * n // 8} " in text


def test_the_round_span_measures_only_the_written_clause_on_a_round_piece():
    from brambleloop.cir.assembly import _placed_on_round_cm
    from brambleloop.cir.model import Seam

    db, seed = _db("everyday-market-tote")
    concept = pipeline.Concept(
        slug=seed.slug, title=seed.title, category=seed.category,
        stitch_repeat=[tuple(x) for x in pipeline.concept_geometry(seed)["stitch_repeat"]],
        width_stitches=10, rows=4, colors=pipeline.concept_geometry(seed)["colors"])
    cir = F.tote(concept)
    top = cir.components[0].rows[-1].index
    st_cm = 10.0 / cir.gauge.stitches_per_10cm
    on_round = Seam("whipstitch", "strap", "basket", edge_a="bottom", edge_b="top",
                    at_round=top, stitches_from_centre=3)
    assert abs(_placed_on_round_cm(cir, on_round) - 6 * st_cm) < 1e-9
    # Not placed by stitches, or on a flat piece, or on a side edge: not this measurement.
    for seam in (Seam("whipstitch", "strap", "basket", edge_a="bottom", edge_b="top",
                      at_round=top),
                 Seam("whipstitch", "basket", "strap", edge_a="top", edge_b="top", at_round=1,
                      stitches_from_centre=3),
                 Seam("whipstitch", "strap", "basket", edge_a="bottom", edge_b="left",
                      at_round=top, stitches_from_centre=3)):
        assert _placed_on_round_cm(cir, seam) is None
    # A strap wider than the span it is sewn across does not assemble.
    from brambleloop.gates.certificate import certify

    import dataclasses
    wide = dataclasses.replace(cir, assembly=[dataclasses.replace(cir.assembly[0],
                                                                  stitches_from_centre=1)])
    assert "ASSEMBLY_MISMATCH" in {f.code for f in certify(wide).errors}


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
