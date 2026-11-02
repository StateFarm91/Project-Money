"""OPUS2: tapestry crochet baskets, the first colourwork product generator (P0 breadth 3A).

The CIR carries per-stitch colour (`Op.color`, P0-CIR-COLOURWORK), but no product generator
used it: every basket titled "Tapestry ..." was drafted as the striped vessel and refused at
publication. A tapestry basket is now a hexagon base and a wall whose middle rounds carry an
original six-stitch two-colour chart, worked in single crochet with the colour not in use
carried inside the stitches. Its name is backed by `launch0.fabric_truth`'s own tapestry rule,
the carried strand is in the yardage, and every other colourwork technique, a second basket, a
motif or a size the charts do not make is refused by name.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_tapestry_basket.py
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

from brambleloop.cir import colour_changes, reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, op_colours  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import fallback_constructions as F  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _concept(title="Diamond Tapestry Basket", category="basket", colors=None):
    seed = pipeline._seed_for("nordic-forest-basket")
    geo = pipeline.concept_geometry(seed)
    return pipeline.Concept(slug="tapestry-fixture", title=title, category=category,
                            stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
                            width_stitches=10, rows=4,
                            colors=colors if colors is not None else geo["colors"])


def _built(title="Diamond Tapestry Basket"):
    cir = F.tapestry_basket(_concept(title))
    result = compile_cir(cir)
    return cir, result, build_twin(cir, result)


def test_tapestry_titles_route_and_other_claims_are_refused_by_name():
    drafted = ["Tapestry Basket", "Diamond Tapestry Basket", "Two-Colour Tapestry Basket",
               "Two‑Tone Check Storage Basket", "Large Geometric Tapestry Basket",
               "Small Checkerboard Colourwork Basket", "  Tapestry   Crochet Basket "]
    refused = {
        "Mosaic Tapestry Basket": "reach past", "Fair Isle Tapestry Basket": "floated",
        "Intarsia Two-Colour Basket": "bobbins", "Two Colour Tapestry Baskets": "one certified", "Tapestry C2C Basket": "graphghan",
        "Three-Colour Tapestry Basket": "two-colour", "Tapestry Baskets": "one certified",
        "Set of Two Tapestry Basket": "one certified", "Two Tapestry Basket": "one certified",
        "Fox Tapestry Basket": "fox", "Lined Tapestry Basket": "lined",
        "Jumbo Tapestry Basket": "jumbo", "Tapestry Basket Liner": "head noun",
        "Tapestry Tote": "head noun", "Argyle Tapestry Basket": "argyle",
    }
    assert drafted and refused
    for title in drafted:
        assert F.plan(category="basket", title=title)["family"] == F.TAPESTRY, title
    for title, why in refused.items():
        got = F.plan(category="basket", title=title)
        assert got["family"] == F.REFUSED, (title, got)
        assert why in (got["needs"] + got["why"]), (title, got)
    # Unchanged: a basket with no tapestry claim is the plain vessel, and a mosaic basket keeps
    # the existing flow (drafted, then refused at publication by fabric_truth).
    assert F.plan(category="basket", title="Storage Basket")["family"] == F.VESSEL
    assert F.plan(category="basket",
                  title="Nordic Forest Mosaic Storage Basket")["family"] == F.VESSEL
    # Outside the basket category the route does not apply.
    assert F.plan(category="pillow", title="Tapestry Cushion")["family"] != F.TAPESTRY


def test_the_basket_compiles_and_the_chart_is_worked_in_two_colours():
    cir, result, twin = _built()
    errors = [f for f in result.findings if f.severity == "ERROR"]
    assert not errors and result.ok, errors
    rows = cir.components[0].rows
    band = [r for r in rows if op_colours(r.ops) - {r.color}]
    assert len(band) >= 6 and len(band) % len(F.TAPESTRY_CHARTS["diamond"]) == 0, len(band)
    # Every wall round has the base's stitch count: colour is count-neutral.
    counts = {result.row("basket", r.index).stitch_count for r in rows[-len(band) - 4:]}
    assert len(counts) == 1, counts
    # The band rows are consecutive, plain rounds sit below it and at the rim.
    idx = [r.index for r in band]
    assert idx == list(range(idx[0], idx[0] + len(idx))), idx
    assert rows[-1].index - idx[-1] == F.TAPESTRY_PLAIN_RIM
    # Each band round paints exactly the chart line, repeated all the way round.
    grid = twin.color_grid()
    main, contrast = list(cir.colors)[:2]
    chart = F.TAPESTRY_CHARTS["diamond"]
    # The charts are a pinned design: a changed chart is a new design, not a refactor.
    assert F.TAPESTRY_CHARTS == {
        "diamond": ("..XX..", ".XXXX.", "XX..XX", "XX..XX", ".XXXX.", "..XX.."),
        "check": ("XXX...", "XXX...", "XXX...", "...XXX", "...XXX", "...XXX")}
    checked = 0
    for k, r in enumerate(band):
        cells = [c for c in grid[r.index - 1] if c]
        want = "".join("X" if c == contrast else "." for c in cells)
        assert want == chart[k % len(chart)] * (len(cells) // 6), (r.index, want[:12])
        checked += 1
    assert checked == len(band) > 0


def test_the_name_is_backed_by_the_tapestry_rule_and_the_strand_is_in_the_yarn():
    for title in ("Diamond Tapestry Basket", "Check Tapestry Basket"):
        cir, result, twin = _built(title)
        truth = L.fabric_truth(cir, twin)
        assert truth["colourwork_claims"] and truth["backed"], truth
        assert truth["max_colours_in_one_row"] == 2, truth
        motif = truth["colourwork_motif"]
        assert motif["min_contrast_run"] >= L.COLOURWORK_MIN_RUN, motif
        # The same fabric under a mosaic name is refused: the gate, not the route, judges.
        mosaic = dataclasses.replace(cir, title="Mosaic Basket")
        assert not L.fabric_truth(mosaic, twin)["backed"]
        # Yardage: both yarns, and the contrast is charged for the strand it carries.
        metres = twin.yarn_metres_by_color
        main, contrast = list(cir.colors)[:2]
        assert set(metres) == {main, contrast} and metres[contrast] > 0, metres
    # Carried, not cut: joined rounds never turn, so nothing is cut and rejoined.
    plan = colour_changes.analyse(cir)["basket"]
    assert plan.tapestry_rows and plan.cut == 0 and plan.tapestry_cuts == 0, plan


def test_the_written_pattern_names_the_contrast_and_reads_back():
    cir, result, _twin = _built()
    text = writer.write_pattern(cir, result, "US")
    contrast = list(cir.colors)[1]
    assert f"with {contrast}" in text, text[:400]
    assert "work over the colour not in use" in text, text[-600:]
    # OPUS2N-3: the contrast-only yarn is told when to join and when to cut.
    band = [r.index for r in cir.components[0].rows if op_colours(r.ops) - {r.color}]
    assert f"Join {contrast} at the start of Rnd {band[0]}" in text, text[-900:]
    assert f"cut {contrast} after Rnd {band[-1]} and fasten it off" in text, text[-900:]
    note = cir.components[0].note
    assert "work over it" in note and "leans" in note, note
    assert [f for f in reverse.compare(cir, text) if f.severity == "ERROR"] == []
    assert "Computed, not yet measured" in cir.finished_size_note
    assert CIR.from_dict(cir.to_dict()).to_dict() == cir.to_dict()


def test_size_words_pick_a_vessel_size_and_one_colour_is_refused():
    sizes = {}
    for word in ("Small", "Medium", "Large"):
        cir, _r, twin = _built(f"{word} Tapestry Basket")
        sizes[word] = twin.width_cm
    assert sizes["Small"] < sizes["Medium"] < sizes["Large"], sizes
    try:
        F.tapestry_basket(_concept(colors={"natural": "#EFE6D2"}))
    except ValueError as exc:
        assert "two distinct colours" in str(exc)
    else:
        raise AssertionError("a one-colour tapestry basket was drafted")


def test_the_handler_drafts_a_tapestry_basket_and_refuses_one_colour():
    from brambleloop.core.db import Database
    from brambleloop.core.models import PatternVersion, Product

    seed = pipeline._seed_for("nordic-forest-basket")
    outcomes = {}
    for label, colors in (("two", None), ("one", {"natural": "#EFE6D2"})):
        db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_tap_')}/d.sqlite")
        db.create_all()
        with db.session() as s:
            p = Product(slug=seed.slug, title=seed.title)
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json={}, certified=True))
        inputs = {k: v for k, v in dataclasses.asdict(seed).items() if not isinstance(v, tuple)}
        inputs.update(pipeline.concept_geometry(seed))
        inputs["title"] = "Diamond Tapestry Basket"
        if colors is not None:
            inputs["colors"] = colors
        emitted, audits = [], []
        ctx = SimpleNamespace(db=db, job=SimpleNamespace(inputs=inputs),
                              audit=lambda action, **kw: audits.append((action, kw)),
                              enqueue=lambda role, kind, data, **kw: emitted.append((kind, data)))
        outcomes[label] = (pipeline.handle_cir_draft(ctx), emitted, audits)
    result, emitted, _ = outcomes["two"]
    assert result["drafted"] is True and result["construction"] == F.TAPESTRY, result
    cir = CIR.from_dict(emitted[0][1]["cir"])
    assert any(op_colours(r.ops) - {r.color} for r in cir.components[0].rows)
    assert set(F.TAPESTRY_PRIMITIVES) <= set(cir.provenance.primitives_used)
    result, emitted, audits = outcomes["one"]
    assert result["drafted"] is False and result["gate"] == "construction", result
    assert emitted == [] and any(a == "cir.draft_refused" for a, _ in audits)


def test_review_opus2n_the_allowlist_is_total_and_one_chart_one_size():
    """OPUS2N-1: an emoji or a word in another script is not a free pass. OPUS2N-2: the base
    is a hexagon, so "Round" is refused. OPUS2N-4: two charts or two sizes are refused, not
    reduced to one. OPUS2N-6 (T8): the colour-count rename keeps a plural vessel noun's count."""
    refused = ("\U0001f98a Tapestry Basket", "\u041b\u0438\u0441\u0430 Tapestry Basket",
               "\u72d0 Tapestry Basket", "Tapestry \u2605 Basket", "Round Tapestry Basket",
               "Check Diamond Tapestry Basket", "Two-Colour Diamond Check Basket",
               "Large Small Tapestry Basket", "Medium Large Tapestry Basket")
    assert refused
    for title in refused:
        got = F.plan(category="basket", title=title)
        assert got["family"] == F.REFUSED and got["needs"], (title, got)
    assert F.plan(category="basket", title="Hexagonal Diamond Tapestry Basket")["family"] == \
        F.TAPESTRY
    for text in ("Two Colour Bowls", "Two-Tone Totes", "Two Colour Baskets"):
        assert F._colour_count_free(text) == text, text
    assert F._colour_count_free("Two-Colour Basket") == "bicolour Basket"


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
