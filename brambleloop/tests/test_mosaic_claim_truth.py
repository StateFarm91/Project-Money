"""D2 (catalogue unblock, 2026-11-22): a 'mosaic' claim is judged on drop-down structure.

The listing gate refused every 'mosaic' title with "the fabric puts at most 1 colour(s) in any
one row". Overlay mosaic IS worked one colour per row; it is defined by drop-down stitches
worked over earlier rows into a row of their own colour. The CIR now expresses that
(`Op.below`) and `launch0.mosaic_structure` measures it. Tapestry and fair isle keep the
colours-per-row test.

Without the fix: `Op` has no `below` field (the CIR below cannot be built), and a mosaic claim
is refused on any CIR whatever its structure.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates import first_customer as FC  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402


def _relief():
    """The placemat as released: rows alternate colour, raised dc stand in sc rows (no drop)."""
    return L.cir_for("placemat_pair")


def _mosaic():
    """The same rows with every dc dropped 2 rows down over the other colour (row 3 on)."""
    d = _relief().to_dict()
    for row in d["components"][0]["rows"]:
        if row["index"] < 3:
            continue

        def walk(nodes):
            for n in nodes:
                if "stitch" in n:
                    if n["stitch"] == "dc":
                        n["below"] = 2
                else:
                    walk(n["ops"])
        walk(row["ops"])
    return CIR.from_dict({**d, "version": "9.9.9-test"})


def _twin(cir):
    result = compile_cir(cir)
    assert result.ok, [f for f in result.findings if f.severity == "error"]
    return build_twin(cir, result)


def _findings(cir, title):
    return FC.colourwork_findings(cir, _twin(cir), title=title, tags=())


def test_mosaic_with_drop_down_structure_is_truthful():
    cir = _mosaic()
    m = L.mosaic_structure(cir)
    assert m["backed"], m
    assert _findings(cir, "Mosaic Placemat Pair | Crochet Pattern PDF") == []
    assert _findings(cir, "Overlay Mosaic Placemat Pair") == []
    # one colour per row is still what the grid measures: mosaic passes on structure.
    assert max(len(set(r)) for r in _twin(cir).color_grid()) == 1


def test_mosaic_claim_without_the_structure_is_still_refused():
    cir = _relief()
    out = _findings(cir, "Mosaic Placemat Pair | Crochet Pattern PDF")
    assert len(out) == 1 and out[0].startswith("LISTING_COLOURWORK_UNSUPPORTED"), out
    # The reason is the missing drop-downs, not the (irrelevant) colours-per-row count.
    assert "drop-down" in out[0] and "colour(s) in any one row" not in out[0], out


def test_tapestry_and_fair_isle_keep_the_colours_per_row_check():
    for cir in (_relief(), _mosaic()):
        for title in ("Tapestry Placemat Pair", "Fair Isle Placemat Pair"):
            out = _findings(cir, title)
            assert out and "at most 1 colour(s) in any one row" in out[0], (title, out)


def test_drop_down_over_own_colour_is_a_relief_not_mosaic():
    d = _mosaic().to_dict()
    for row in d["components"][0]["rows"]:
        row["color"] = "cream"
    cir = CIR.from_dict(d)
    m = L.mosaic_structure(cir)
    assert not m["backed"] and m["drop_down_rows"] == 0, m
    assert _findings(cir, "Mosaic Placemat")


def test_drop_down_round_trips_and_is_validated():
    cir = _mosaic()
    text = write_pattern(cir, compile_cir(cir), "US")
    assert "dropped 2 rows down" in text
    assert compare(cir, text) == []
    # Serialisation: present when set, absent (no digest change) when not.
    assert CIR.from_dict(cir.to_dict()).to_dict() == cir.to_dict()
    assert "below" not in str(_relief().to_dict())
    # A drop below the first row is a compile error.
    d = _relief().to_dict()
    d["components"][0]["rows"][1]["ops"][0]["ops"][1]["below"] = 2
    codes = {f.code for f in compile_cir(CIR.from_dict(d)).findings}
    assert "DROP_BELOW_FABRIC" in codes, codes


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
