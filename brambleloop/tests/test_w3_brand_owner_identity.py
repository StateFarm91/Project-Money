"""Wave-3 lane A3: the owner-concept production identity (O1 "Bramble B", owner decision D-FB-16).

What must stay true:
  * every O1 mark and every committed SVG master is valid, self-contained SVG (no <text>, no
    scripts, no images, no external references; internal masks only) and deterministic;
  * the micro-mark is the SAME B as the monogram (same Playfair design, heavier cut) and, at
    40 px, measured with the existing brand.comparison procedure, at least 62% of its ink
    reaches 3:1 against the cream ground with a median of at least 4.5:1 (the raw concept:
    42% and 2.44:1); it improves at 48 and 70 px; it passes the judge's small-size gates;
  * the palette is faithful to the owner's concept (CIE76 dE within the declared tolerance of
    the colour re-sampled from the owner's own files, when those files are present);
  * lane B's interface (icon_svg, lockup_stacked_svg, PALETTE, ROLES, font_face_css,
    css_variables, preview_sources.identity/lockup_svg) still works; D1 stays available;
  * only open-licence fonts with licence files; Playfair (RFN) never shipped as a web font;
  * evidence images are few and small.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import comparison as C  # noqa: E402
from brambleloop.brand import identity_system as I  # noqa: E402
from brambleloop.brand import judge  # noqa: E402
from brambleloop.brand import owner_identity as O  # noqa: E402
from brambleloop.brand import owner_proofs as PR  # noqa: E402
from brambleloop.brand import typeset as T  # noqa: E402

KINDS = ("icon", "emblem", "wordmark", "lockup_horizontal", "lockup_stacked", "motif")
SVG_NS = "{http://www.w3.org/2000/svg}"
EVIDENCE = ROOT / "research" / "final_build" / "w3" / "evidence"
O1C = C.Candidate("O1", "O1 micro-mark", "vector", O.DIRECTION_ID)


def _check_svg(svg: str, tag: str) -> None:
    root = ET.fromstring(svg)
    assert root.tag == SVG_NS + "svg", tag
    assert re.fullmatch(r"0 0 [\d.]+ [\d.]+", root.get("viewBox")), tag
    low = svg.lower()
    for bad in ("<text", "<script", "<image", "<foreignobject", "@import", "font-family",
                "href", "javascript:", "<style", "data:"):
        assert bad not in low, (tag, bad)
    assert re.findall(r"https?://[^\"' )]+", svg) == ["http://www.w3.org/2000/svg"], tag
    for ref in re.findall(r"url\(([^)]*)\)", svg):
        assert ref.startswith("#") and f'id="{ref[1:]}"' in svg, (tag, ref)
    assert set(re.findall(r'fill-rule="([^"]+)"', svg)) <= {"evenodd", "nonzero"}, tag
    assert svg.count("<title>") == 1, tag


def test_primary_is_owner_concept():
    assert I.DIRECTION_ID == O.DIRECTION_ID == "O1-owner-bramble-b"
    assert I.STATUS["decision"] == "D-FB-16"
    # D-FB-17: the owner's exact artwork is the hero; this vector system supports it
    assert I.STATUS["state"] == "SUPPORTING_PRODUCTION_SYSTEM"
    assert I.STATUS["superseded_by"] == "D-FB-17"
    assert I.RESEARCH_DIRECTION_ID == "D1-briar-monogram"
    assert I.direction() is O.O1
    d = I.to_dict()
    json.dumps(d)
    assert d["tagline"] == "Patterns for a More Handmade Life"
    assert d["descriptor"] == "CROCHET PATTERNS"
    assert set(d["clear_space"]) >= {"hero_lockup", "lockup_horizontal", "monogram",
                                     "micro_mark"}
    assert I.MIN_SIZE["micro_mark"]["min_px"] == 40 and I.MIN_SIZE["monogram"]["min_px"] >= 160
    print("OK primary_is_owner_concept")


def test_svgs_valid_self_contained_deterministic():
    svgs = []
    for kind in KINDS:
        for v in I.VARIANTS:
            svgs.append((f"{kind}/{v}", I.mark_svg(kind, v)))
    svgs += list(I.master_svgs().items())
    assert len(svgs) >= 30
    for tag, svg in svgs:
        _check_svg(svg, tag)
    for kind in KINDS:
        assert I.mark_svg(kind) == I.mark_svg(kind)
    assert I.icon_svg() == I.micro_mark_svg() and I.emblem_svg() == I.monogram_svg()
    assert I.lockup_stacked_svg() == I.hero_lockup_svg()
    print("OK svgs_valid_self_contained_deterministic", len(svgs))


def test_committed_masters_match_code():
    masters = I.master_svgs()
    assert masters
    for name, svg in masters.items():
        f = I.MASTERS_DIR / name
        assert f.exists(), f
        assert f.read_text() == svg + "\n", f"stale master {name}: run identity_system." \
                                             "export_masters()"
    assert len(masters) == len(I.MASTER_KINDS) * (len(I.VARIANTS) + 1)
    print("OK committed_masters_match_code", len(masters))


def test_micro_mark_is_the_same_B():
    fm, fi = (O.TYPOGRAPHY["monogram"]["font"], O.TYPOGRAPHY["micro_monogram"]["font"])
    assert T.font_metrics(fm)["file"].startswith("PlayfairDisplay-")
    assert T.font_metrics(fi)["file"].startswith("PlayfairDisplay-")
    a, b = T._glyph_ops(fm, "B"), T._glyph_ops(fi, "B")
    assert a and [op[0] for op in a] == [op[0] for op in b]   # same contours, same structure
    # heavier: more ink in the micro cut than the monogram cut at the same cap height
    from brambleloop.brand.vector import Fill, Mark, rasterize

    def ink(font):
        m = Mark("b", 120, 120)
        m.add(Fill(O._B(font, 100, 10, 110), "ink", "nonzero"))
        return float(rasterize(m, {"ink": "#000000"}, 120)[..., 3].mean())
    assert ink(fi) > ink(fm) * 1.08, (ink(fi), ink(fm))
    print("OK micro_mark_is_the_same_B")


def test_micro_mark_contrast_and_ink_at_small_sizes():
    m = {px: PR.small_metrics(O1C, px) for px in (40, 48, 70)}
    assert m[40]["ink_at_3to1_share"] >= 0.62, m[40]
    assert m[40]["contrast_median"] >= 4.5, m[40]
    assert 0.15 <= m[40]["ink_coverage"] <= 0.5, m[40]
    for px in (48, 70):
        assert m[px]["ink_at_3to1_share"] >= m[40]["ink_at_3to1_share"], (px, m[px])
        assert m[px]["contrast_median"] >= 4.5, (px, m[px])
    owner = [c for c in C.candidates() if c.key == "OWNER"]
    if owner:
        raw = PR.small_metrics(owner[0], 40)
        # the board's numbers for the raw concept, reproduced by the same procedure
        assert abs(raw["ink_at_3to1_share"] - 0.422) < 0.02 and abs(raw["contrast_median"]
                                                                    - 2.44) < 0.1, raw
        assert m[40]["ink_at_3to1_share"] >= raw["ink_at_3to1_share"] + 0.2
        assert m[40]["contrast_median"] >= raw["contrast_median"] * 1.8
        print("OK micro_mark_vs_raw_concept", m[40], raw)
    else:
        print("OK note: owner concept raster not present; raw comparison skipped")
    print("OK micro_mark_contrast_and_ink_at_small_sizes", m)


def test_micro_mark_passes_judge_gates_and_roles():
    mt = judge.measure_direction(O.O1)
    assert mt["stroke_survival_40"] >= 0.5, mt
    assert mt["thinnest_stroke_px_40"] is None or mt["thinnest_stroke_px_40"] >= 1.5, mt
    assert mt["ink_outside_circle"] < 0.01, mt
    assert mt["mono_edge_correlation"] >= 0.8, mt
    assert mt["header_letter_px"] >= 11, mt
    assert mt["reversed_non_blank"] and all(mt["non_blank"].values())
    roles = O.O1.icon().roles()
    assert roles
    for r in roles:
        assert judge.contrast(O.O1.colours()[r], O.O1.ground()) >= 3.0, r
        assert judge.contrast(O.O1.colours("reversed")[r], O.O1.ground("reversed")) >= 3.0, r
    mono = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", I.icon_svg("mono"))}
    assert mono and mono <= {O.PALETTE["forest"], O.PALETTE["paper"]}, mono
    print("OK micro_mark_passes_judge_gates_and_roles")


def test_micro_mark_distinct():
    refs = {k: judge._centred(judge._ref_mask(m, 40))
            for k, m in judge.generic_references().items()}
    assert len(refs) >= 5
    from brambleloop.brand import directions as D
    from brambleloop.brand.vector import rasterize

    def mask(d):
        return judge._centred(judge.ink_mask(rasterize(d.icon(), d.colours(), 40,
                                                       ground=d.ground()), d.ground()))
    mine = mask(O.O1)
    for k, r in refs.items():
        assert judge._iou(mine, r) < 0.55, (k, judge._iou(mine, r))
    assert D.DIRECTIONS
    for did, d in D.DIRECTIONS.items():
        assert judge._iou(mine, mask(d)) < 0.6, did
    print("OK micro_mark_distinct")


def test_palette_fidelity_to_concept():
    assert O.CONCEPT_SAMPLES
    for name, (_src, _box, _m, hexv, tol) in O.CONCEPT_SAMPLES.items():
        de = O.delta_e(O.PALETTE[name], hexv)
        assert de <= tol, (name, O.PALETTE[name], hexv, de)
    paths = O.concept_paths()
    if paths:
        for name, (src, _box, _m, hexv, _tol) in O.CONCEPT_SAMPLES.items():
            if src not in paths:
                continue
            got = O.sample_concept(name)
            assert O.delta_e(got, hexv) <= 2.0, (name, got, hexv)
        print("OK palette re-sampled from owner files:", sorted(paths))
    else:
        print("OK note: owner concept files not present; recorded samples used")
    for name, v in O.PALETTE.items():
        assert re.fullmatch(r"#[0-9A-F]{6}", v), name
    print("OK palette_fidelity_to_concept")


def test_text_roles_and_reversed_contrast():
    bg, surface = I.ROLES["background"], I.ROLES["surface"]
    for role in ("text", "text_muted", "accent_text", "descriptor", "focus"):
        for ground in (bg, surface):
            assert judge.contrast(I.ROLES[role], ground) >= 4.5, (role, ground)
    assert judge.contrast(I.ROLES["inverse_text"], I.ROLES["inverse_background"]) >= 4.5
    rev = O.O1.colours("reversed")
    for role in ("ink", "script", "accent_text", "loop", "leaf"):
        assert judge.contrast(rev[role], O.O1.ground("reversed")) >= 3.0, role
    print("OK text_roles_and_reversed_contrast")


def test_interface_compatible_with_lane_b():
    for k in ("paper", "petal", "sage", "sage_mist", "forest", "rose", "berry", "rose_deep"):
        assert k in I.PALETTE, k
    assert I.icon_svg().startswith("<svg")
    lock = I.lockup_stacked_svg(tagline="Patterns for a More Handmade Life", transparent=True)
    assert lock.startswith("<svg") and "<rect" not in lock.split("</defs>")[-1][:200]
    # a tagline the outlined script cannot set falls back to the owner's tagline
    assert I.lockup_stacked_svg(tagline="Crochet ♥ #1") == I.lockup_stacked_svg()
    css = I.font_face_css("/static/brand/")
    assert css.count("@font-face") == 4 and "http" not in css
    assert I.font_face_css("/x/", extra=("script",)).count("@font-face") == 5
    v = I.css_variables()
    assert "--bl-text:" in v and "--bl-font-display:" in v and "--bl-font-script:" in v
    png = I.icon_png(70)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    from brambleloop.store_foundation import preview_sources as S

    ident = S.identity()
    assert ident.value["mark_source"] == S.PEER and ident.value["direction"] == O.DIRECTION_ID
    assert S.lockup_svg("Patterns for a More Handmade Life").startswith("<svg")
    print("OK interface_compatible_with_lane_b")


def test_research_directions_still_available():
    alts = I.alternatives()
    assert alts
    ids = {a["id"] for a in alts}
    assert "D1-briar-monogram" in ids and O.DIRECTION_ID not in ids
    for a in alts:
        assert a["why_not"] and a["icon_svg"].startswith("<svg")
    _check_svg(I.mark_svg("emblem", direction_id=I.RESEARCH_DIRECTION_ID), "D1 emblem")
    print("OK research_directions_still_available")


def test_fonts_open_licence():
    fonts_dir = ROOT / "src" / "brambleloop" / "brand" / "fonts"
    data = json.loads(T.OWNER_DATA.read_text())["fonts"]
    assert set(data) == {"playfair_bold", "playfair_black", "cormorant_semibold", "allison"}
    for key, rec in data.items():
        lic = fonts_dir / f"{rec['file'].split('-')[0]}-OFL.txt"
        assert lic.exists() and "SIL Open Font License" in lic.read_text(), lic
    for key in ("display", "script"):
        f = fonts_dir.parent / I.TYPOGRAPHY[key]["file"]
        assert f.exists() and f.stat().st_size < 60_000, f
        assert I.TYPOGRAPHY[key]["licence"] == "OFL-1.1"
    assert not list(fonts_dir.glob("Playfair*.woff*")), "Playfair (RFN) must not ship as a font"
    assert T.has_glyphs("allison", O.TAGLINE) and T.has_glyphs("cormorant_semibold",
                                                                 "BRAMBLELOOP")
    print("OK fonts_open_licence")


def test_evidence_small():
    pngs = sorted(EVIDENCE.glob("A3_*.png"))
    assert 1 <= len(pngs) <= 6, pngs
    for p in pngs:
        assert p.stat().st_size <= 300_000, p
    meas = json.loads((EVIDENCE / "A3_measurements.json").read_text())
    assert meas["candidates"]["O1"]["sizes"]["40"]["ink_at_3to1_share"] >= 0.62
    print("OK evidence_small", len(pngs))


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("FAILS", fails)
    sys.exit(1 if fails else 0)
