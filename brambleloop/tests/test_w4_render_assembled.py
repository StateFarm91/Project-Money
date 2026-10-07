"""W4-RENDER: multi-piece products drawn assembled only as their CIR's structure places them.

`visual.assembled_render` composes pieces from named-edge joins (planar), wrong-sides-together
stacks (hidden back layer, proven to mirror the front), rings (front rows only), structured
folds and resumed holds. Anything else is not drawn and the manifest says so; a product whose
pieces cannot be placed is refused. Assembled frames stay structurally UNKNOWN (the verifier
does not yet measure them); the detail frame is the body piece and verifies PASS.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import moment_candidates as mc  # noqa: E402
from brambleloop.products import pipeline_board as pb  # noqa: E402
from brambleloop.visual import disclosed_render as D  # noqa: E402
from brambleloop.visual import render_verification as V  # noqa: E402

FAILED: list[str] = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {detail}" if not cond and detail else ""))
    if not cond:
        FAILED.append(name)


def _refused(cir, view="hero") -> str:
    try:
        D.render(cir, view)
    except D.RenderRefused as exc:
        return str(exc)
    return ""


def test_stocking():
    cir = pb.stocking_cir()
    frames = {v: D.render(cir, v) for v in ("hero", "scale", "detail")}
    assert frames, "no frames"
    a = frames["hero"].manifest["assembly"]
    check("stocking_front_pieces_drawn",
          set(a["drawn"]) == {"leg_front", "foot_front", "toe_front", "cuff"}, a["drawn"])
    check("stocking_back_layer_hidden_as_mirror",
          set(a["hidden"]) == {"leg_back", "foot_back", "toe_back"}, a["hidden"])
    check("stocking_loop_not_drawn_with_reason", "loop" in a["not_drawn"]
          and "fold" in a["not_drawn"]["loop"], a["not_drawn"])
    cuff = next(p for p in frames["hero"].manifest["layout"]["pieces"] if p["piece"] == "cuff")
    check("stocking_cuff_ring_shows_front_rows_only", cuff["rows_shown"] == [1, 26],
          cuff["rows_shown"])
    m = frames["hero"].manifest
    check("assembled_frame_is_disclosed_and_unqualified",
          m["disclosure"] == D.K.DISCLOSURE and m["renderer_version"].startswith(
              "disclosed-render-assembled/") and m["form"] == "assembled")
    for v in ("hero", "scale"):
        r = V.verify(frames[v].png, cir=cir, view=v)
        check(f"stocking_{v}_assembled_is_unknown_not_pass", r["status"] == "UNKNOWN",
              r["status"])
    r = V.verify(frames["detail"].png, cir=cir, view="detail")
    check("stocking_body_detail_verifies", r["status"] == "PASS", (r["failed"], r["unknown"]))
    from brambleloop.publish.disclosed_listing import caption_in_image
    check("stocking_hero_carries_disclosure",
          caption_in_image(frames["hero"].png, cir)["status"] == "PASS")
    # A back layer that does not mirror the front would show: refused, not hidden.
    comps = [replace(c, rows=c.rows[:-3]) if c.name == "toe_back" else c
             for c in cir.components]
    bad = replace(cir, components=comps)
    why = _refused(bad)
    check("stocking_mismatched_back_layer_refused", bool(why), why)


def test_cosy():
    cir = mc.mothers_day_heart_tea_cosy()
    hero = D.render(cir, "hero")
    a = hero.manifest["assembly"]
    check("cosy_skirts_hang_from_held_stitches", a["form"] == "vessel_skirts"
          and set(a["drawn"]) == {"cosy", "front", "back"}, a)
    check("cosy_opening_down_from_certified_title", hero.manifest["layout"]["opening"] == "down")
    detail = D.render(cir, "detail")
    r = V.verify(detail.png, cir=cir, view="detail")
    check("cosy_crown_detail_verifies", r["status"] == "PASS", (r["failed"], r["unknown"]))
    untitled = replace(cir, title="Heart Row Dome")
    why = _refused(untitled)
    check("vessel_orientation_not_guessed_without_title", "opening" in why, why)


def test_refusals():
    why = _refused(mc.snowfall_advent_garland())
    check("garland_refused_pieces_not_placeable", "round pieces" in why, why)
    why = _refused(pb.pencil_roll_cir())
    check("pencil_roll_refused_on_palette_contract", "palette" in why, why)
    cir = pb.stocking_cir()
    seams = [replace(s, edge_b="left") if (s.piece_a, s.piece_b) == ("leg_front", "foot_front")
             else s for s in cir.assembly]
    why = _refused(replace(cir, assembly=seams))
    check("join_off_the_plane_refused", bool(why), why)


if __name__ == "__main__":
    test_stocking()
    test_cosy()
    test_refusals()
    if FAILED:
        print(f"FAILED: {FAILED}")
        sys.exit(1)
    print("ALL PASSED")
