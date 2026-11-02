"""OPUS2: a drawstring pouch drafted as a round vessel with eyelets and a threaded cord.

Bag concepts that were not totes were refused ("a closure, gusset, flap, drawstring or shaped
body"). A plain drawstring pouch is now drafted: a round base, straight walls, one eyelet round
("sc 4, ch 2, sk 2" around) a few rounds below the rim, and a slip-stitched chain cord woven
through the eyelets. `cir.assembly` measures the thread join -- the cord's girth against one
eyelet's inside -- which needed `assembly.openings_cm` to see a bridged chain inside a repeat.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_drawstring_pouch.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir import assembly, reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR, Component, Op, Repeat, Row  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import fallback_constructions as F  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _concept(title="Drawstring Pouch", category="bag"):
    seed = pipeline._seed_for("woodland-fox-amigurumi")
    geo = pipeline.concept_geometry(seed)
    return pipeline.Concept(slug="pouch-fixture", title=title, category=category,
                            stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
                            width_stitches=10, rows=4, colors=geo["colors"])


def test_only_a_plain_drawstring_pouch_routes():
    drafted = [("bag", "Drawstring Pouch"), ("bag", "Drawstring Project Bag"),
               ("accessory", "Simple Drawstring Gift Pouch"), ("bag", "Drawstring‑Bag")]
    refused = ["Drawstring Backpack", "Two Drawstring Pouches", "Lined Drawstring Pouch",
               "Large Drawstring Bag", "Drawstring Pouch Set", "Drawstring Pouch with Pocket",
               "Mosaic Drawstring Bag", "Drawstring Bucket Bag", "Pair of Drawstring Pouch",
               "\U0001f381 Drawstring Pouch", "\u041f\u043e\u0434\u0430\u0440\u043e\u043a Drawstring Pouch"]
    assert drafted and refused
    for category, title in drafted:
        assert F.plan(category=category, title=title)["family"] == F.POUCH, title
    for title in refused:
        got = F.plan(category="bag", title=title)
        assert got["family"] == F.REFUSED and got["needs"] and got["why"], (title, got)
    # ("Two ..." and "Pair of ..." are refused earlier, by the several-sizes count.)
    for title in ("Drawstring Pouch Set", "Drawstring Pouches", "Drawstring Duo Pouch"):
        assert "more than one pouch" in F.plan(category="bag", title=title)["why"], title
    # A bag with no drawstring keeps the existing rules (tote, or refused).
    assert F.plan(category="bag", title="Market Tote")["family"] == F.TOTE
    assert F.plan(category="bag", title="Crossbody Bag")["family"] == F.REFUSED


def test_the_pouch_compiles_reads_back_and_its_cord_passes_the_eyelets():
    cir = F.pouch(_concept())
    result = compile_cir(cir)
    assert result.ok and not result.findings, [f.code for f in result.findings]
    text = writer.write_pattern(cir, result, "US")
    assert reverse.compare(cir, text) == []
    assert CIR.from_dict(cir.to_dict()).to_dict() == cir.to_dict()
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    geo = assembly.assemble(cir, twins)
    assert geo.verdict == "assembles", geo.why
    join = geo.joins[0]
    assert join.verdict == "sound" and join.length_a_cm <= assembly.THREAD_ROOM * \
        join.length_b_cm, join
    # The eyelet round: every repeat bridges its skipped stitches, and the count is unchanged.
    body = next(c for c in cir.components if c.name == "pouch")
    eyelet = next(r for r in body.rows if any(isinstance(o, Repeat) and any(
        getattr(x, "spans", 0) for x in o.ops) for o in r.ops))
    counts = {r.stitch_count for r in result.rows if r.component == "pouch"
              and r.index >= eyelet.index - 1}
    assert len(counts) == 1, counts
    eyelets = eyelet.ops[0].times
    assert f"the {eyelets} eyelets of round {eyelet.index}" in cir.assembly[0].note
    assert body.rows[-1].index - eyelet.index == F.POUCH_RIM_ROUNDS
    # The cord goes once round the pouch and leaves a tie at each end.
    cord = next(c for c in cir.components if c.name == "cord")
    around = result.rows[-1].stitch_count if result.rows[-1].component == "pouch" else max(
        r.stitch_count for r in result.rows if r.component == "pouch")
    tie_sts = 2 * F.POUCH_TIE_CM * cir.gauge.stitches_per_10cm / 10.0
    assert abs(cord.foundation - (around + tie_sts)) <= 1, (cord.foundation, around, tie_sts)
    assert L.finished_objects(cir) == 1 and L.title_promise(cir)["backed"]
    assert "Computed, not yet measured" in cir.finished_size_note


def test_openings_inside_a_repeat_are_measured_and_a_tight_cord_is_refused():
    gauge = F.pouch(_concept()).gauge
    comp = Component("p", "joined_rounds", foundation=0, foundation_kind="magic_ring",
                     rows=[Row(1, [Repeat([Op("sc", 4), Op("ch", 2, spans=2), Op("sk", 2)],
                                          times=3)], declared_count=18, color="a")])
    found = assembly.openings_cm(comp, gauge)
    assert len(found) == 3 and len(set(found)) == 1, found
    # A cord as thick as the eyelet does not pass: the join is a mismatch, not a photograph.
    cir = F.pouch(_concept())
    thick = next(c for c in cir.components if c.name == "cord")
    thick.rows = [Row(i, [Op("sc", thick.foundation)], declared_count=thick.foundation,
                      color=thick.rows[0].color, turning_chain=1) for i in range(1, 5)]
    result = compile_cir(cir)
    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    assert assembly.assemble(cir, twins).joins[0].verdict == "mismatched"


def test_review_opus2p_even_eyelets_and_clear_wording():
    """OPUS2P-5: an even eyelet count (both ends exit neighbouring eyelets outside), at least
    six; OPUS2P-6: the next round says 2 sc in each ch-2 space; each yarn says what it is for."""
    for weight in ("dk", "worsted", "bulky"):
        concept = _concept()
        concept.yarn_weight = weight
        try:
            cir = F.pouch(concept)
        except ValueError as exc:
            assert "eyelets" in str(exc), (weight, exc)
            continue
        eyelet = next(r for r in cir.components[0].rows
                      if any(isinstance(o, Repeat) and any(getattr(x, "spans", 0) for x in o.ops)
                             for o in r.ops))
        n = eyelet.ops[0].times
        assert n % 2 == 0 and n >= F.POUCH_MIN_EYELETS, (weight, n)
        assert "neighbouring eyelets on the outside" in cir.assembly[0].note
        assert "2 sc into each ch-2 space" in eyelet.note, eyelet.note
        names = [m.name for m in cir.materials]
        assert len(set(names)) == len(names) and any("cord" in n for n in names), names
    jumbo = _concept()
    jumbo.yarn_weight = "jumbo"
    try:
        F.pouch(jumbo)
    except ValueError as exc:
        assert "eyelets" in str(exc)
    else:
        raise AssertionError("a pouch with too few eyelets to gather was drafted")


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
