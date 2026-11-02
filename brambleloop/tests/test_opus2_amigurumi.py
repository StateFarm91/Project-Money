"""OPUS2: a ball-body amigurumi bear or bunny, drafted as shaped pieces (P0 breadth 3C).

Every amigurumi concept was refused by the radar fallback ("shaped pieces worked in the round,
stuffed and joined"). A plain ball-body bear or bunny is now drafted: a body worked from the
top of the head down in single crochet (staggered increases to a circle, plain rounds,
staggered decreases), a flat base disc whipstitched on after stuffing so it sits, and two ears
flattened and sewn across a stated number of stitches of a stated round. Eyes and nose are
embroidered; the pattern makes no toy-safety claim. A stuffed closed form is risk class C and
states only the circumference its stitch counts make. Any other animal, character, feature,
size or count is refused by name.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_amigurumi.py
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

from brambleloop.cir import geometry, reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import fallback_constructions as F  # noqa: E402
from brambleloop.gates import risk_matrix  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _concept(title="Ball Bear Amigurumi"):
    seed = pipeline._seed_for("woodland-fox-amigurumi")
    geo = pipeline.concept_geometry(seed)
    return pipeline.Concept(slug="ami-fixture", title=title, category="amigurumi",
                            stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
                            width_stitches=10, rows=4, colors=geo["colors"])


def test_only_a_plain_ball_body_bear_or_bunny_routes():
    drafted = {"Ball Bear Amigurumi": "bear", "Teddy Bear": "bear", "Bunny Amigurumi": "bunny",
               "Cosy Rabbit": "bunny", "Simple Crochet Bear": "bear",
               "Amigurumi Bunny": "bunny", "Round‑Ball Bunny Plush": "bunny"}
    refused = ["Woodland Fox Amigurumi", "No-Sew Reindeer Amigurumi", "Bear and Bunny",
               "Two Bears", "Bunny Set", "Bear Family", "Giant Bear", "Mini Bunny",
               "Bear with Scarf", "Sleepy Bear Amigurumi", "Bunny Rattle", "Teddy Bunny",
               "Bear Keychain", "Panda Amigurumi", "Unicorn Bunny", "Amigurumi",
               # OPUS2N-1: an emoji or another script is not a free pass.
               "\U0001f98a Bear", "\u041b\u0438\u0441\u0430 Bunny", "\u72d0 Bear Amigurumi",
               "Bear \u2605"]
    assert drafted and refused
    for title, kind in drafted.items():
        got = F.plan(category="amigurumi", title=title)
        assert got["family"] == F.AMIGURUMI and got["kind"] == kind, (title, got)
    for title in refused:
        got = F.plan(category="amigurumi", title=title)
        assert got["family"] == F.REFUSED and got["needs"] and got["why"], (title, got)
    for title in ("Two Bears", "Bear Family", "Bunny Set", "Pair of Bunny"):
        assert "more than one toy" in F.plan(category="amigurumi", title=title)["why"], title
    # Outside the amigurumi category a toy word is still a shaped refusal, never a panel.
    assert F.plan(category="blanket", title="Bear Amigurumi")["family"] == F.REFUSED


def test_both_toys_compile_clean_and_read_back():
    for title in ("Ball Bear Amigurumi", "Bunny Amigurumi"):
        cir = F.amigurumi(_concept(title))
        result = compile_cir(cir)
        assert result.ok and not result.findings, [f.code for f in result.findings]
        text = writer.write_pattern(cir, result, "US")
        assert reverse.compare(cir, text) == [], reverse.compare(cir, text)[:3]
        assert CIR.from_dict(cir.to_dict()).to_dict() == cir.to_dict()
        # The stuffed piece is never blocked; vessel advice never reaches a toy.
        assert "stuffed and closed, so it is not blocked" in text
        assert "standing up" not in text and "towel" not in text
        assert "Embroider the eyes and nose" in text and "fibrefill" in text
        assert "safety" not in text.lower() and "safe" not in text.lower()


def test_the_shape_is_round_and_every_count_meets_its_join():
    cir = F.amigurumi(_concept())
    result = compile_cir(cir)
    body = [r for r in result.rows if r.component == "body"]
    base = [r for r in result.rows if r.component == "base"]
    # The design is pinned: a changed count is a new design, not a refactor.
    assert (F.AMI_BODY_STITCHES, F.AMI_PLAIN_ROUNDS, F.AMI_BASE_STITCHES,
            F.AMI_EAR_ROUND) == (36, 7, 18, 5)
    assert max(r.stitch_count for r in body) == F.AMI_BODY_STITCHES
    # The opening and the base close stitch for stitch.
    assert body[-1].stitch_count == base[-1].stitch_count == F.AMI_BASE_STITCHES
    # Staggered, never stacked: the body is round, not a hexagon.
    revs = geometry.measure_all(cir, result)
    assert revs["body"].shape != geometry.DISC
    from brambleloop.cir.twin import build_twin as bt

    assert not bt(cir, result, component="body").sides, "the body must not be a polygon"
    # The ear seam's arithmetic is the round's own count: ear, gap, ear, back.
    ear_seam = next(s for s in cir.assembly if s.piece_a == "ear")
    count = next(r.stitch_count for r in body if r.index == F.AMI_EAR_ROUND)
    flat = 2 * ear_seam.stitches_from_centre
    assert f"across {flat} sts of round {F.AMI_EAR_ROUND} ({count} sts)" in ear_seam.note
    back = count - 3 * flat
    assert back > 0 and f"then {back} sts at the back" in ear_seam.note, ear_seam.note
    ear_last = [r for r in result.rows if r.component == "ear"][-1].stitch_count
    assert ear_last == 2 * flat, (ear_last, flat)     # a flattened ear is half its round
    assert next(c for c in cir.components if c.name == "ear").make == 2
    assert L.finished_objects(cir) == 1 and L.title_promise(cir)["backed"]


def test_risk_class_c_and_only_the_circumference_is_stated():
    cir = F.amigurumi(_concept())
    assert cir.risk_class == "C"
    feats = {f.key for f in risk_matrix.features(cir, None)}
    assert "closed_3d_form" in feats, feats
    result = compile_cir(cir)
    twin = build_twin(cir, result, component="body")
    assert twin.size_refusal, "a stuffed closed shape must refuse a height"
    around = F.AMI_BODY_STITCHES / cir.gauge.stitches_per_10cm * 10.0
    assert f"about {around:.0f} cm around" in cir.finished_size_note
    assert "Computed" in cir.finished_size_note and "measured on the sample" in \
        cir.finished_size_note
    assert any(m.name == "polyester fibrefill" for m in cir.materials)


def test_the_handler_drafts_the_toy_with_its_provenance():
    from brambleloop.core.db import Database
    from brambleloop.core.models import PatternVersion, Product

    seed = pipeline._seed_for("woodland-fox-amigurumi")
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_ami_')}/d.sqlite")
    db.create_all()
    with db.session() as s:
        p = Product(slug=seed.slug, title=seed.title)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
    inputs = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
    inputs.update(pipeline.concept_geometry(seed))
    emitted, audits = [], []
    ctx = SimpleNamespace(db=db, job=SimpleNamespace(inputs=dict(inputs)),
                          audit=lambda action, **kw: audits.append((action, kw)),
                          enqueue=lambda role, kind, data, **kw: emitted.append((kind, data)))
    refused = pipeline.handle_cir_draft(ctx)          # "Woodland Fox": not a bear or bunny
    assert refused["drafted"] is False and refused["gate"] == "construction", refused
    inputs["title"] = "Ball Bear Amigurumi"
    ctx.job = SimpleNamespace(inputs=inputs)
    result = pipeline.handle_cir_draft(ctx)
    assert result["drafted"] is True and result["construction"] == F.AMIGURUMI, result
    cir = CIR.from_dict(emitted[-1][1]["cir"])
    assert {c.name for c in cir.components} == {"body", "base", "ear"}
    assert set(F.AMIGURUMI_PRIMITIVES) <= set(cir.provenance.primitives_used)


def test_review_opus2p_p1_every_drafted_toy_needs_a_childrens_decision_to_render():
    """OPUS2P-1 (HIGH): the PDF renderer refuses an undecided children's product only when a
    child word is in the title or slug. Every title the route drafts now carries one, so a
    drafted toy cannot render a pattern with no children's safety block on nobody's decision."""
    from brambleloop.publish import pdf

    drafted = ("Ball Bear Amigurumi", "Teddy Bear", "Bunny Amigurumi", "Cosy Rabbit",
               "Simple Crochet Bear", "Amigurumi Bunny", "Round\u2011Ball Bunny Plush")
    assert drafted
    refused = 0
    for title in drafted:
        assert F.plan(category="amigurumi", title=title)["family"] == F.AMIGURUMI, title
        concept = _concept(title)
        concept.slug = "neutral-slug-x"                   # nothing child-like in the slug
        cir = F.amigurumi(concept)
        assert L.child_words_in(cir.title, cir.slug), title
        assert L.childrens_decision(cir.slug)[0] == L.UNDECIDED
        try:
            pdf.build_pattern_pdf(cir)
        except Exception as exc:  # noqa: BLE001 - the renderer's refusal is the outcome
            assert "child" in str(exc).lower(), (title, exc)
            refused += 1
        else:
            raise AssertionError(f"{title!r} rendered with no children's decision")
    assert refused == len(drafted)


def test_review_opus2p_joins_are_counted_size_has_a_floor_and_words_do_not_repeat():
    """OPUS2P-2: the toy's joins are measured by stitch count, so a wrong base is a mismatch,
    not an UNKNOWN warning. OPUS2P-3: the body has a stated size floor. OPUS2P-4: a repeated
    word, two kinds and a misplaced head noun are refused. OPUS2P-7: each ear leaves a tail.
    OPUS2P-8: a stuffed piece is not told to check the band "before blocking"."""
    import dataclasses

    from brambleloop.cir import assembly
    from brambleloop.gates.certificate import assembly_findings

    cir = F.amigurumi(_concept())
    result = compile_cir(cir)
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    geo = assembly.assemble(cir, twins)
    assert geo.verdict == "assembles" and len(geo.joins) == 2, (geo.verdict, geo.why)
    assert all(j.verdict == "sound" for j in geo.joins), [j.why for j in geo.joins]
    # A 30-st base sewn onto the 18-st opening does not sew together.
    from brambleloop.products.moment_candidates import _disc, _Rows

    wrong = _Rows()
    _disc(wrong, 30, cir.components[1].rows[0].color)
    bad = dataclasses.replace(cir, components=[cir.components[0], dataclasses.replace(
        cir.components[1], rows=wrong.rows), cir.components[2]])
    r2 = compile_cir(bad)
    geo2 = assembly.assemble(bad, {c.name: build_twin(bad, r2, component=c.name)
                                   for c in bad.components})
    assert geo2.verdict == "does_not_assemble", (geo2.verdict, geo2.why)
    assert [f.code for f in assembly_findings(bad, geo2)] == ["ASSEMBLY_MISMATCH"]
    # Size floor: a lace toy is refused; worsted is drafted.
    lace = _concept()
    lace.yarn_weight = "lace"
    try:
        F.amigurumi(lace)
    except ValueError as exc:
        assert "floor" in str(exc)
    else:
        raise AssertionError("a lace-weight toy under the size floor was drafted")
    # Words.
    for title in ("Bear Bear", "Bunny Bunny Bunny", "Teddy Teddy Bear", "Cosy Cosy Bear",
                  "Bear Bunny", "Rabbit Bunny", "Bear Crochet", "Bunny Simple", "Bear Ball"):
        assert F.plan(category="amigurumi", title=title)["family"] == F.REFUSED, title
    text = writer.write_pattern(cir, result, "US")
    assert "leaving a 25 cm tail for sewing the ear on" in text
    assert "before blocking" not in text


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}")
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
