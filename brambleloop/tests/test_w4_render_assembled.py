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
          set(a["drawn"]) == {"leg_front", "foot_front", "toe_front", "cuff", "loop"},
          a["drawn"])
    check("stocking_back_layer_hidden_as_mirror",
          set(a["hidden"]) == {"leg_back", "foot_back", "toe_back"}, a["hidden"])
    check("stocking_nothing_left_undrawn", not a["not_drawn"], a["not_drawn"])
    pieces = {p["piece"]: p for p in frames["hero"].manifest["layout"]["pieces"]}
    cuff = pieces["cuff"]
    check("stocking_cuff_ring_shows_front_rows_only", cuff["rows_shown"] == [1, 26],
          cuff["rows_shown"])
    # W4-CAND: the loop's ends are a structured self-seam (a band along its stitches), so it
    # lies flat at half its chain, on the cuff's top edge over cuff rows 1-2 (the back seam).
    loop_c = next(c for c in cir.components if c.name == "loop")
    w_cm = 10.0 / cir.gauge.stitches_per_10cm
    loop = pieces["loop"]
    check("stocking_loop_ends_joined_by_structure",
          any(s.piece_a == s.piece_b == "loop" and {s.edge_a, s.edge_b} == {"top", "bottom"}
              for s in cir.assembly) and loop_c.foundation % 2 == 0)
    check("stocking_loop_lies_flat_at_half_its_chain",
          loop["band_flat"] == "stitches"
          and loop["stitches_shown"] == [0, loop_c.foundation // 2 - 1]
          and abs(loop["up_cm"] - loop_c.foundation // 2 * w_cm) < 1e-6, loop)
    check("stocking_loop_on_cuff_top_at_back_seam",
          abs(loop["y0_cm"] - (cuff["y0_cm"] + cuff["up_cm"])) < 1e-6
          and abs(loop["x0_cm"] - cuff["x0_cm"]) < 1e-6, (loop, cuff))
    check("stocking_no_join_note_folds_unstructured",
          not any("fold" in (s.note or "").lower() for s in cir.assembly
                  if "loop" in (s.piece_a, s.piece_b)))
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
    roll = pb.pencil_roll_cir()
    hero = D.render(roll, "hero")
    panel = next(p for p in hero.manifest["layout"]["pieces"] if p["piece"] == "panel")
    tops = __import__("brambleloop.cir.twin", fromlist=["build_twin"]).build_twin(
        roll, __import__("brambleloop.cir.compiler", fromlist=["compile_cir"]).compile_cir(roll),
        component="panel").row_top_cm
    k = panel["fold_rows"]
    seam_k = next(s.spans_rounds for s in roll.assembly
                  if s.piece_a == s.piece_b == "panel" and s.edge_a == "left")
    check("pencil_roll_pocket_fold_from_self_seams", k == seam_k
          and panel["drawn"]["fold"]["fold_rows"] == k
          and abs(tops[k] - pb.POCKET_CM) <= min(abs(tops[j] - pb.POCKET_CM) for j in tops),
          (panel["fold_rows"], tops.get(k)))
    check("pencil_roll_height_is_rows_above_the_fold",
          abs(panel["up_cm"] - (tops[max(tops)] - tops[k])) < 1e-6, panel["up_cm"])
    check("pencil_roll_holds_a_pencil_above_the_fold",
          panel["up_cm"] >= pb.PENCIL_CM + pb.ABOVE_PENCIL_CM, panel["up_cm"])
    # W4-CAND: the closure is a closed band laid flat by its seam, just above the pocket.
    band = next(p for p in hero.manifest["layout"]["pieces"] if p["piece"] == "band")
    btw = __import__("brambleloop.cir.twin", fromlist=["build_twin"]).build_twin(
        roll, __import__("brambleloop.cir.compiler", fromlist=["compile_cir"]).compile_cir(roll),
        component="band")
    m = len(next(c for c in roll.components if c.name == "band").rows)
    check("pencil_roll_band_placed_by_its_seam",
          hero.manifest["assembly"]["drawn"] == ["panel", "band"]
          and not hero.manifest["assembly"]["not_drawn"])
    check("pencil_roll_band_lies_flat_at_half_its_length",
          band["band_flat"] and band["rows_shown"] == [1, m // 2] and m % 2 == 0
          and abs(band["across_cm"] - btw.row_top_cm[m // 2]) < 1e-6, band)
    at = next(s.at_round for s in roll.assembly if (s.piece_a, s.piece_b) == ("band", "panel"))
    check("pencil_roll_band_above_the_pocket_as_its_note_says",
          at == 2 * k + 1 and abs(band["y0_cm"] - (tops[2 * k] - tops[k])) < 1e-3
          and f"rows {at}-" in next(s.note for s in roll.assembly
                                    if (s.piece_a, s.piece_b) == ("band", "panel")),
          (at, band["y0_cm"]))
    check("pencil_roll_flat_footprint_compact",
          hero.manifest["layout"]["width_cm"] < 1.5 * panel["across_cm"],
          hero.manifest["layout"]["width_cm"])
    from brambleloop.visual import render_contract as K
    pal = D._palette(roll)
    check("pencil_roll_palette_clears_contract_separation",
          K.separation(pal) >= K.MIN_SEPARATION
          and all(K._dist(v, K.relief(v)) >= K.MIN_SEPARATION for v in pal.values()),
          K.separation(pal))
    odd = replace(roll, components=[roll.components[0], replace(
        roll.components[1], rows=roll.components[1].rows[:-1])])
    why = _refused(odd)
    check("odd_row_band_not_drawn_flat", "band" in why and "inside a row" in why, why)
    cir = pb.stocking_cir()
    seams = [replace(s, edge_b="left") if (s.piece_a, s.piece_b) == ("leg_front", "foot_front")
             else s for s in cir.assembly]
    why = _refused(replace(cir, assembly=seams))
    check("join_off_the_plane_refused", bool(why), why)


def test_multi_piece_construction():
    """CONSTRUCTION for a multi-piece product: every piece's profile, two count paths, layout QA."""
    import copy
    import io

    from PIL import Image

    from brambleloop.publish import layout_qa
    from brambleloop.visual import gallery_frames as G

    cirs = [pb.stocking_cir(), pb.pencil_roll_cir(), mc.creative_cir("mothers-day-heart-tea-cosy"),
            mc.snowfall_advent_garland()]
    assert cirs
    for cir in cirs:
        check(f"construction_applies_{cir.slug}", "CONSTRUCTION" in G.applicable_jobs(cir))
        fr = G.render(cir, "CONSTRUCTION")
        f = fr.manifest["facts"]
        check(f"construction_every_piece_{cir.slug}",
              [p["piece"] for p in f["pieces"]] == [c.name for c in cir.components]
              and all(p["make"] == c.make for p, c in zip(f["pieces"], cir.components))
              and f["joins"] == len(cir.assembly), f)
        v = G.verify(fr.png, cir, fr.manifest)
        check(f"construction_verifies_{cir.slug}", v["status"] == "PASS", v)
        rep = layout_qa.inspect(Image.open(io.BytesIO(fr.png)).convert("RGB"), position=4,
                                expect_text=True)
        check(f"construction_layout_qa_{cir.slug}", not rep.problems, rep.problems)
        bad = copy.deepcopy(fr.manifest)
        bad["facts"]["pieces"][0]["profile"][-1]["stitches"] += 1
        check(f"construction_tampered_facts_fail_{cir.slug}",
              G.verify(G.draw(bad["facts"]), cir, bad)["status"] == "FAIL")
    # one piece is still the single-piece frame (rounds only), unchanged
    one = mc.housewarming_key_basket()
    check("single_piece_construction_unchanged",
          "pieces" not in G.facts(one, "CONSTRUCTION")
          and G.applicable_jobs(pb.stocking_cir(), siblings=[one]).count("CONSTRUCTION") == 0)


if __name__ == "__main__":
    test_stocking()
    test_cosy()
    test_refusals()
    test_multi_piece_construction()
    if FAILED:
        print(f"FAILED: {FAILED}")
        sys.exit(1)
    print("ALL PASSED")
