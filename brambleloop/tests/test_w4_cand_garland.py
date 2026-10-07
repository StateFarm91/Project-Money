"""W4-CAND: the advent garland's thumbs and cord are structure, so it is drawn truthfully.

0.1.0 carried the afterthought thumb's placement and the cord's threading only in notes, so
the assembled renderer refused the garland. 0.2.0 states them as joins `cir.assembly` measures
(a `pick_up` join: round 1 of the thumb into the mitten's chain-bridged opening, both lengths
compared; a `thread` join: the cord through each closed loop, with room) and the renderer
draws every pocket laid flat from that structure. Nothing here relaxes a gate: the 340 px
legibility gate, Product Truth and the reverse compile are run as they are.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.assembly import assemble  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import Op, Seam  # noqa: E402
from brambleloop.cir.reverse import parse_assembly  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.products import moment_candidates as mc  # noqa: E402
from brambleloop.visual import disclosed_render as D  # noqa: E402
from brambleloop.visual import render_verification as V  # noqa: E402

FAILED: list[str] = []


def check(name, cond, detail=""):
    print(("OK " if cond else "FAIL ") + name + (f" -- {detail}" if not cond and detail else ""))
    if not cond:
        FAILED.append(name)


def _geo(cir):
    r = compile_cir(cir)
    return assemble(cir, {c.name: build_twin(cir, r, component=c.name) for c in cir.components})


def test_structure():
    cir = mc.snowfall_advent_garland()
    check("garland_version_bumped", cir.version == "0.2.0", cir.version)
    geo = _geo(cir)
    joins = {(j.piece_a, j.piece_b, j.method): j for j in geo.joins}
    assert joins, "no joins"
    check("garland_assembles", geo.verdict == "assembles", (geo.verdict, geo.why))
    thumb = joins[("thumb", "mitten", "pick_up")]
    check("thumb_picked_up_into_opening_lengths_agree",
          thumb.verdict == "sound" and thumb.length_a_cm and thumb.length_b_cm
          and abs(thumb.length_a_cm - thumb.length_b_cm) < 1e-6, vars(thumb))
    cord = joins[("cord", "loop_tab", "thread")]
    check("cord_threads_through_closed_loop_with_room",
          cord.verdict == "sound" and cord.length_a_cm <= 0.5 * cord.length_b_cm, vars(cord))
    check("loop_is_a_closed_band_even_rows",
          any(s.piece_a == s.piece_b == "loop_tab" and {s.edge_a, s.edge_b} == {"top", "bottom"}
              for s in cir.assembly)
          and len(next(c for c in cir.components if c.name == "loop_tab").rows) % 2 == 0)
    check("no_assembly_step_is_note_only",
          not any("fold" in (s.note or "").lower() for s in cir.assembly))
    # A cord too thick for the loop, and a thumb that does not fit its opening, are refused
    # by measurement, not by wording.
    fat = replace(cir, components=[
        replace(c, rows=[replace(c.rows[0], ops=[Op("dc", c.rows[0].ops[0].count)])])
        if c.name == "cord" else c for c in cir.components])
    v = {(j.piece_a, j.method): j.verdict for j in _geo(fat).joins}
    check("cord_that_does_not_fit_is_mismatched", v[("cord", "thread")] == "mismatched", v)
    from brambleloop.cir.model import Repeat

    small = [replace(c, foundation=6, rows=[
        replace(r, ops=[Op("sc", 6)], declared_count=6) for r in c.rows[:-1]] + [
        replace(c.rows[-1], ops=[Repeat([Op("dec")], times=3)], declared_count=3)])
        if c.name == "thumb" else c for c in cir.components]
    six = replace(cir, components=small)
    check("six_stitch_thumb_compiles", compile_cir(six).ok)
    v2 = {(j.piece_a, j.method): j.verdict for j in _geo(six).joins}
    check("thumb_short_of_opening_is_mismatched", v2[("thumb", "pick_up")] == "mismatched", v2)


def test_written_and_read_back():
    cir = mc.snowfall_advent_garland()
    r = compile_cir(cir)
    text = write_pattern(cir, r, "US")
    steps = parse_assembly(text)
    expected = [(s.method, s.piece_a, s.piece_b, s.at_round, s.spans_rounds,
                 s.stitches_from_centre, s.mirrored) for s in cir.assembly]
    check("assembly_round_trips_through_text", steps == expected and len(steps) == 3,
          (steps, expected))
    check("pick_up_reads_as_worked_into", "Work the thumb into the mitten" in text)
    check("thread_reads_as_threaded_through", "Thread the cord through the loop_tab" in text)
    from brambleloop.gates.certificate import certify

    cert = certify(cir)
    errors = [f.code for f in cert.findings if f.severity == "ERROR"]
    check("garland_certified", cert.granted and not errors, errors)
    check("garland_no_assembly_warnings",
          not [f.code for f in cert.findings if f.code.startswith("ASSEMBLY")],
          [f.code for f in cert.findings])
    # The vocabulary does not leak: an existing whipstitch join still writes "to".
    w = Seam("whipstitch", "a", "b")
    from brambleloop.cir.writer import write_seam

    check("whipstitch_still_to", "Whipstitch the a to the b" in write_seam(w, 1))


def test_drawn():
    cir = mc.snowfall_advent_garland()
    frames = {v: D.render(cir, v) for v in ("hero", "scale", "detail")}
    assert frames, "no frames"
    a = frames["hero"].manifest["assembly"]
    check("garland_pockets_drawn", a["form"] == "pockets"
          and a["drawn"] == ["mitten", "thumb", "loop_tab"], a)
    check("cord_not_drawn_with_reason", "cord" in a["not_drawn"]
          and "thread" in a["not_drawn"]["cord"], a["not_drawn"])
    lay = frames["hero"].manifest["layout"]
    mitten = next(c for c in cir.components if c.name == "mitten")
    check("hero_shows_every_pocket", lay["objects"] == mitten.make == lay["copies"]
          and lay["tiles_drawn"] == mitten.make * lay["tiles_per_unit"], lay["objects"])
    u = lay["unit"]
    w = 10.0 / cir.gauge.stitches_per_10cm
    n = max(r.declared_count for r in mitten.rows)
    check("pocket_laid_flat_half_its_round", abs(u["body_width_cm"] - n / 2 * w) < 1e-6, u)
    check("every_round_shows_half_its_stitches",
          all(abs(r["front"] - r["of"] / 2) < 1e-6 for r in u["rounds"]
              + u["thumb_rounds"]), u["rounds"][:3])
    tab = next(c for c in cir.components if c.name == "loop_tab")
    check("loop_lies_flat_half_its_rows", u["loop_rows_shown"] == [1, len(tab.rows) // 2])
    pitch = float(cir.assembly[-1].note.split("about ")[1].split(" cm")[0])
    check("cord_spacing_clears_a_flat_pocket", pitch >= u["width_cm"], (pitch, u["width_cm"]))
    for v in ("hero", "scale", "detail"):
        r = V.verify(frames[v].png, cir=cir, view=v)
        check(f"garland_{v}_unqualified_is_unknown_not_pass", r["status"] == "UNKNOWN",
              r["status"])
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import disclosed_listing as DL
    import tempfile

    store = ArtifactStore(root=Path(tempfile.mkdtemp()) / "a")
    listing = DL.build(cir, store=store)
    check("garland_listing_made", listing["made"], listing.get("launch_blocked"))
    qa = listing["qa"]
    leg = {v: x["legibility_340"] for v, x in qa["frames"].items()}
    check("garland_340px_legibility_passes_unrelaxed",
          all(x["ok"] for x in leg.values()) and leg["hero"]["expected_pieces"] == 24
          and leg["hero"]["pieces"] == 24, {v: x.get("problems") for v, x in leg.items()})
    check("garland_layout_and_asset_truth", qa["layout_qa"]["ok"] and qa["asset_truth"]["ok"],
          (qa["layout_qa"], qa["asset_truth"]))
    check("garland_alt_text_says_cord_not_drawn",
          "cord is not drawn" in listing["frames"][0]["alt_text"], listing["frames"][0]["alt_text"])


if __name__ == "__main__":
    test_structure()
    test_written_and_read_back()
    test_drawn()
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("ALL PASSED")
