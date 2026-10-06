"""Wave-3 lane A: the Brambleloop identity system (brand.identity_system and its directions).

What must stay true however the marks are redrawn:
  * every mark is valid, self-contained SVG: no <text>, no scripts, no external references,
    no font dependency (glyphs are outlined), deterministic bytes;
  * the shop icon renders non-blank and distinct at the real Etsy sizes (40 and 70 px), its
    strokes survive at 40 px, it sits inside a circular crop, and it holds in one colour;
  * every text colour role passes WCAG 4.5:1 on its ground; every icon role passes 3:1;
  * the interface lane B/C read has the documented shape; the judge's winner among the research
    directions is D1 (RESEARCH_DIRECTION_ID); the exported PRIMARY is the owner's concept
    (owner decision D-FB-16), which must pass the same small-size gates (measured here);
  * only open-licence fonts, each with its licence file, no CDN.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import directions as D  # noqa: E402
from brambleloop.brand import identity_system as I  # noqa: E402
from brambleloop.brand import judge  # noqa: E402
from brambleloop.brand import typeset as T  # noqa: E402
from brambleloop.brand.vector import rasterize, to_svg  # noqa: E402

KINDS = ("icon", "emblem", "wordmark", "lockup_horizontal", "lockup_stacked", "motif")
SVG_NS = "{http://www.w3.org/2000/svg}"


def _all_svgs():
    out = []
    for did in D.DIRECTIONS:
        for kind in KINDS:
            for variant in I.VARIANTS:
                out.append((did, kind, variant, I.mark_svg(kind, variant, direction_id=did)))
    assert out
    return out


def test_interface_shape():
    assert I.DIRECTION_ID in I.ALL_DIRECTIONS and I.RESEARCH_DIRECTION_ID in D.DIRECTIONS
    d = I.to_dict()
    json.dumps(d)  # JSON-serialisable
    for key in ("direction_id", "palette", "roles", "typography", "usage_rules", "svgs",
                "alternatives", "status", "descriptor"):
        assert key in d, key
    # D-FB-16: the owner chose their own concept; it is the primary, not a recommendation
    assert d["status"]["state"] == "OWNER_DIRECTED_PRIMARY"
    assert d["status"]["decision"] == "D-FB-16"
    assert len(d["usage_rules"]) >= 8
    assert d["palette"]
    for name, hexv in d["palette"].items():
        assert re.fullmatch(r"#[0-9A-F]{6}", hexv), (name, hexv)
    for k in ("icon", "emblem", "wordmark", "lockup_horizontal", "lockup_stacked", "motif",
              "icon_mono", "icon_reversed"):
        assert d["svgs"][k].startswith("<svg"), k
    alts = I.alternatives()
    assert 2 <= len(alts) <= 4
    for a in alts:
        assert a["id"] != I.DIRECTION_ID and a["icon_svg"].startswith("<svg") and a["why_not"]


def test_three_to_five_distinct_directions():
    assert 3 <= len(D.DIRECTIONS) <= 5
    palettes = {tuple(sorted(d.palette.values())) for d in D.DIRECTIONS.values()}
    fonts = {d.typography["wordmark"]["font"] for d in D.DIRECTIONS.values()}
    assert len(palettes) == len(D.DIRECTIONS) and len(fonts) == len(D.DIRECTIONS)


def test_svgs_valid_and_self_contained():
    svgs = _all_svgs()
    assert len(svgs) == len(D.DIRECTIONS) * len(KINDS) * len(I.VARIANTS)
    for did, kind, variant, svg in svgs:
        root = ET.fromstring(svg)
        assert root.tag == SVG_NS + "svg", (did, kind)
        assert re.fullmatch(r"0 0 [\d.]+ [\d.]+", root.get("viewBox")), (did, kind)
        low = svg.lower()
        for bad in ("<text", "<script", "<image", "<foreignobject", "@import", "font-family",
                    "href", "javascript:", "<style"):
            assert bad not in low, (did, kind, variant, bad)
        # the only URL is the SVG namespace; url() references are internal masks only
        assert re.findall(r"https?://[^\"' )]+", svg) == ["http://www.w3.org/2000/svg"]
        for ref in re.findall(r"url\(([^)]*)\)", svg):
            assert ref.startswith("#"), (did, kind, ref)
            assert f'id="{ref[1:]}"' in svg, (did, kind, ref)
        assert svg.count("<title>") == 1


def test_svgs_deterministic():
    for kind in KINDS:
        assert I.mark_svg(kind) == I.mark_svg(kind)
    a = hashlib.sha256(I.icon_png(70)).hexdigest()
    b = hashlib.sha256(I.icon_png(70)).hexdigest()
    assert a == b


def test_text_roles_pass_wcag_aa():
    bg, surface = I.ROLES["background"], I.ROLES["surface"]
    for role in ("text", "text_muted", "accent_text", "focus"):
        for ground in (bg, surface):
            c = judge.contrast(I.ROLES[role], ground)
            assert c >= 4.5, (role, ground, c)
    assert judge.contrast(I.ROLES["inverse_text"], I.ROLES["inverse_background"]) >= 4.5


def test_icon_roles_pass_non_text_contrast():
    for d in D.DIRECTIONS.values():
        assert judge.contrast(d.colours()["ink"], d.ground()) >= 3.0, d.id
    win = I.direction()
    roles = win.icon().roles()
    assert roles
    for r in roles:
        c = judge.contrast(win.colours()[r], win.ground())
        assert c >= 3.0, (r, c)
        cr = judge.contrast(win.colours("reversed")[r], win.ground("reversed"))
        assert cr >= 3.0, ("reversed", r, cr)


def test_icons_render_non_blank_at_40_and_70():
    for d in D.DIRECTIONS.values():
        for px in (40, 70):
            for variant in I.VARIANTS:
                arr = rasterize(d.icon(), d.colours(variant), px, ground=d.ground(variant))
                assert arr.shape == (px, px, 4)
                cov = float(judge.ink_mask(arr, d.ground(variant)).mean())
                assert 0.08 < cov < 0.6, (d.id, px, variant, cov)


def test_icons_distinct_from_each_other_and_from_clip_art():
    v = judge.cached_verdict()
    dist = v["distinctness"]
    assert dist
    for did, rec in dist.items():
        assert rec["iou_vs_other_directions"], did
        for other, iou in rec["iou_vs_other_directions"].items():
            assert iou < 0.6, (did, other, iou)
    # the judge covers the research directions; its winner is D1 (the primary owner-concept
    # mark gets the same distinctness gates in tests/test_w3_brand_owner_identity.py)
    win = dist[I.RESEARCH_DIRECTION_ID]
    assert len(win["iou_vs_generic"]) >= 5
    for ref, iou in win["iou_vs_generic"].items():
        assert iou < 0.55, (ref, iou)
    # and the 40 px rasters are not pixel-identical between any two directions
    rasters = {d.id: rasterize(d.icon(), d.colours(), 40, ground=d.ground()).tobytes()
               for d in D.DIRECTIONS.values()}
    assert len(set(rasters.values())) == len(rasters)


def test_winner_survives_tiny_sizes():
    # the exported primary (owner concept, D-FB-16), measured by the judge's own procedure
    m = judge.measure_direction(I.direction())
    assert m["stroke_survival_40"] >= 0.5, m
    assert m["thinnest_stroke_px_40"] is None or m["thinnest_stroke_px_40"] >= 1.5, m
    assert m["ink_outside_circle"] < 0.01, m
    assert m["mono_edge_correlation"] >= 0.8, m
    assert m["header_letter_px"] >= 11, m
    assert m["reversed_non_blank"] and all(m["non_blank"].values())


def test_mono_variant_is_one_ink():
    win = I.direction()
    svg = I.icon_svg("mono")
    used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", svg)}
    assert used, svg[:80]
    assert used <= {win.palette["forest"].upper(), win.palette["paper"].upper()}, used


def test_judge_winner_matches_interface():
    v = judge.verdict()
    # the judge ranks research directions; the owner (not the judge) chose the primary
    assert v["winner"] == I.RESEARCH_DIRECTION_ID, v["ranking"]
    assert I.DIRECTION_ID not in v["scores"] and I.STATUS["decision"] == "D-FB-16"
    assert set(v["scores"]) == set(D.DIRECTIONS)
    for did, s in v["scores"].items():
        assert 0 <= s["measured"] <= 100 and 0 <= s["judged"] <= 100, (did, s)
    assert v["basis"]["judged"] and "opinion" in v["basis"]["judged"]
    assert v["benchmarks"]
    for b in v["benchmarks"]:
        assert "http" not in json.dumps(b)  # descriptions only, nothing fetched


def test_fonts_open_licence_and_bundled():
    fonts_dir = ROOT / "src" / "brambleloop" / "brand" / "fonts"
    for key in ("display", "body", "italic", "ui"):
        f = fonts_dir.parent / I.TYPOGRAPHY[key]["file"]
        assert f.exists() and f.stat().st_size < 60_000, f
        assert I.TYPOGRAPHY[key]["licence"] == "OFL-1.1"
    data = json.loads(T.DATA.read_text())["fonts"]
    assert data
    for key, rec in data.items():
        family = rec["file"].split("-")[0]
        lic = fonts_dir / f"{family}-OFL.txt"
        assert lic.exists(), lic
        assert "SIL Open Font License" in lic.read_text()
    css = I.font_face_css("/static/brand/")
    assert "http" not in css and css.count("@font-face") == 4


def test_typeset_outlines():
    assert T.has_glyphs("baskerville", "BRAMBLELOOP")
    w1 = T.measure("baskerville", "BRAMBLELOOP", 100)
    w2 = T.measure("baskerville", "BRAMBLELOOP", 100, tracking=0.1)
    assert w2 > w1 > 0
    p = T.set_text("gloock", "B", 100, 0, 100)
    x0, y0, x1, y1 = p.bbox()
    assert 0 <= x0 < x1 and y0 < y1 <= 100.5


def test_old_store_mark_still_renders():
    """The rejected v1 mark is replaced via this interface (wiring by lane B), not deleted."""
    from brambleloop.store_foundation import assets

    assert "<svg" in assets.icon_svg()
    assert "<svg" in to_svg(I.direction().icon(), I.direction().colours(), None)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
