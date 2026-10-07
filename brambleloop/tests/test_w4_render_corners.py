"""W4-RENDER: `cir.geometry.corners` names a round (magic-ring) piece whose increases stagger.

Round 2 of a magic-ring disc is all increases, so every stitch round 3 can work into is an
increase's product and round 3's increases "stack" whatever the designer meant; the old
reading counted that as stacking, saw later rounds stagger, and returned None for every round
base -- the disclosed renderer then refused every staggered disc. Opening rounds (more than
half of the round below made by increases) are now set aside as evidence for neither shape;
a circle needs at least two judged rounds, all wholly unstacked. Polygons are unchanged and a
mixed shape is still refused.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.geometry import corners  # noqa: E402
from brambleloop.cir.model import Op, Repeat  # noqa: E402
from brambleloop.products import moment_candidates as mc  # noqa: E402

FAILED: list[str] = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {detail}" if not cond and detail else ""))
    if not cond:
        FAILED.append(name)


def _sides(cir) -> int | None:
    result = compile_cir(cir)
    assert result.ok, result.errors[:3]
    name = cir.components[0].name
    rows = [r for r in result.rows if r.component == name]
    assert rows, "no compiled rows"
    return corners(rows)


def _with_rows(base, rows):
    comp = replace(base.components[0], rows=rows)
    return replace(base, components=[comp])


def _mixed_rows(colour: str):
    """Staggered to 36 stitches, then stacked to 72: a shape nobody can name."""
    r = mc._Rows()
    mc._disc(r, 36, colour, stagger=True)
    count = 36
    while count < 72:
        per = count // 6
        count += 6
        r.add([Repeat([Op("sc", per - 1), Op("inc")], times=6)], count, colour)
    return r.rows


def test_corners():
    basket = mc.housewarming_key_basket()
    colour = basket.components[0].rows[0].color
    check("known_good_round_magic_ring_basket_is_a_circle", _sides(basket) == 0, _sides(basket))

    stag = mc._Rows()
    mc._disc(stag, 72, colour, stagger=True)
    check("staggered_disc_reads_circle", _sides(_with_rows(basket, stag.rows)) == 0)

    hexa = mc._Rows()
    mc._disc(hexa, 72, colour, stagger=False)
    check("stacked_disc_still_reads_hexagon", _sides(_with_rows(basket, hexa.rows)) == 6)

    mixed = _sides(_with_rows(basket, _mixed_rows(colour)))
    check("known_bad_mixed_shape_still_refused", mixed is None, mixed)

    from brambleloop.visual import disclosed_render as D
    frame = D.render(basket, "hero")
    check("renderer_draws_the_round_basket",
          frame.manifest["layout"]["sides"] == 0 and len(frame.png) > 1000)
    try:
        D.render(_with_rows(basket, _mixed_rows(colour)), "hero")
        check("renderer_refuses_mixed_shape", False, "rendered")
    except D.RenderRefused as exc:
        check("renderer_refuses_mixed_shape", "neither all stack" in str(exc), str(exc))


def test_round_vessel_verifies():
    """The round basket's frames pass the independent verifier against its CIR (relief walls
    drawn as tall as their stitches), and a frame drawn from a recoloured CIR fails."""
    from brambleloop.visual import disclosed_render as D
    from brambleloop.visual import render_verification as V

    basket = mc.housewarming_key_basket()
    views = ("hero", "scale", "detail", "angle")
    assert views, "no views"
    for v in views:
        r = V.verify(D.render(basket, v).png, cir=basket, view=v)
        check(f"round_basket_{v}_verifies", r["status"] == "PASS", (r["failed"], r["unknown"]))
    comp = basket.components[0]
    rows = list(comp.rows)
    i = len(rows) - 4
    other = next(c for c in basket.colors if c != rows[i].color)
    bad = replace(basket, components=[replace(comp, rows=rows[:i] + [replace(rows[i], color=other)]
                                              + rows[i + 1:])])
    r = V.verify(D.render(bad, "hero").png, cir=basket, view="hero")
    check("recoloured_wall_round_fails", r["status"] == "FAIL"
          and "colour_placement" in r["failed"], r["failed"])


if __name__ == "__main__":
    test_corners()
    test_round_vessel_verifies()
    if FAILED:
        print(f"FAILED: {FAILED}")
        sys.exit(1)
    print("ALL PASSED")
