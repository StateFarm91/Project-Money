"""OPUS2: a Christmas stocking drafted as two L-shaped panels, seamed (construction breadth).

The radar fallback refused every stocking ("a closed tube with a heel and toe"), and the
culture engine translates signals into stockings (`TRANSLATION_FAMILIES`). A plain stocking is
now two identical panels worked flat from the cuff down: the last leg row chains across for the
foot, the last rows decrease at both ends to round the sole, and the panels are whipstitched
round everything but the cuff, with a hanging loop. Colourwork, names, second objects, other
sizes and sets are refused by name.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_stocking.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir import reverse, writer  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.creative import fallback_constructions as F  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _concept(title="Classic Christmas Stocking", category="stocking"):
    seed = pipeline._seed_for("pet-snuggle-mat")
    geo = pipeline.concept_geometry(seed)
    return pipeline.Concept(slug="stocking-fixture", title=title, category=category,
                            stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
                            width_stitches=10, rows=4, colors=geo["colors"])


def test_plain_stockings_route_and_unbacked_titles_are_refused_by_name():
    plain = (("stocking", "Classic Christmas Stocking"), ("seasonal", "Fireside Stocking"),
             ("stocking", "Stripe Cuff Holiday Stocking"))
    assert plain
    for category, title in plain:
        assert F.plan(category=category, title=title)["family"] == F.STOCKING, title
    refused = ("Nordic Forest Mosaic Stocking", "Fair Isle Stocking", "Personalized Stocking",
               "Monogram Stocking", "Stocking with Pom Pom", "Stocking & Ornament",
               "Cable Knit Look Stocking", "Mini Stocking", "Giant Stocking", "Stocking Set",
               "3 Stockings", "Faux Fur Cuff Stocking")
    assert refused
    for title in refused:
        route = F.plan(category="stocking", title=title)
        assert route["family"] == F.REFUSED and route["needs"], title


def test_the_stocking_compiles_and_its_heel_chain_makes_the_foot():
    cir = F.stocking(_concept())
    result = compile_cir(cir)
    assert result.ok and not result.findings, [str(f) for f in result.findings]
    front = cir.components[0]
    counts = [r.declared_count for r in front.rows]
    leg = counts[0]
    foot = max(counts)
    assert foot > leg and counts[-1] < foot                 # extended, then rounded
    assert [c.name for c in cir.components] == ["front", "back", "hanging loop"]
    assert all(seam.is_placed for seam in cir.assembly)
    assert "Computed, not yet measured" in cir.finished_size_note


def test_the_written_pattern_reads_back_and_the_name_is_backed():
    cir = F.stocking(_concept())
    result = compile_cir(cir)
    text = writer.write_pattern(cir, result)
    assert not [f for f in reverse.compare(cir, text) if f.severity == "ERROR"]
    assert "chain across for the foot" in text
    assert L.assembly_promise(cir)["backed"] is True
    assert L.finished_objects(cir) == 1 and L.title_promise(cir)["backed"] is True


def test_review_opus2j_j13_j14_only_a_titled_plain_stocking_is_drafted():
    # J-13: "stocking" must be the head noun; the category alone makes nothing a stocking.
    not_stockings = (("blanket", "Stocking Stitch Blanket"), ("blanket", "Stocking Stitch Throw"),
                     ("home_decor", "Stocking Garland"), ("home_decor", "Stocking Holder"),
                     ("home_decor", "Stocking Hanger"), ("home_decor", "Stocking Cuff"),
                     ("home_decor", "Stocking Stuffer Coasters"), ("bag", "Stocking Tote"),
                     ("accessory", "Stocking Cap"), ("stocking", "Snowflake Coaster"),
                     ("stocking", "Holiday Ornament"), ("stocking", "Advent Garland"))
    assert not_stockings
    for category, title in not_stockings:
        assert F.plan(category=category, title=title)["family"] != F.STOCKING, (category, title)
    for title in ("Snowflake Coaster", "Holiday Ornament"):
        assert F.plan(category="stocking", title=title)["family"] == F.REFUSED, title
    # J-14: plurals, motifs and the remaining size word are refused.
    for title in ("Fireplace Stockings", "Nylon Stockings", "Nordic Snowflake Stocking",
                  "Reindeer Stocking", "Medium Stocking"):
        route = F.plan(category="stocking", title=title)
        assert route["family"] == F.REFUSED and route["needs"], (title, route)


def test_review_opus2j_j15_j16_assembly_matches_two_identical_panels_and_size_is_pinned():
    cir = F.stocking(_concept())
    note = cir.assembly[0].note
    assert "same side facing up" in note and "wrong sides together" not in note
    assert (F.STOCKING_LEG_W_CM, F.STOCKING_LEG_L_CM, F.STOCKING_FOOT_L_CM,
            F.STOCKING_FOOT_H_CM) == (14.0, 26.0, 22.0, 10.0)
    assert ("about 14 cm wide at the cuff, 36 cm from cuff to sole and 22 cm from heel to toe"
            in cir.finished_size_note), cir.finished_size_note


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
