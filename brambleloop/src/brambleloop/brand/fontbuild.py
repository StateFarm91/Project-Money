"""Build-time tool: outline the identity's open-licence fonts into `data/glyphs.json`.

Run only when the typography changes (needs fontTools, which the runtime does not):

    PYTHONPATH=src python -m brambleloop.brand.fontbuild /path/to/ttf/dir

Why outlines rather than <text>: an SVG that names a font renders in whatever the viewer's
machine substitutes, so the wordmark would differ between the owner's phone, Etsy's
thumbnailer and a browser. Outlined glyphs render identically everywhere and need no font
file, no CDN and no licence question at view time. Every font used here is SIL Open Font
Licence 1.1 (licence texts in `brand/fonts/`); OFL permits outlining glyphs into artwork such
as a logo. The web-font subsets in `brand/fonts/*.woff` are for page text set by lane B.
"""
from __future__ import annotations

import json
import string
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "glyphs.json"
FONT_DIR = HERE / "fonts"

FONTS = {
    "gloock": "Gloock-Regular.ttf",
    "baskerville": "LibreBaskerville-Regular.ttf",
    "worksans": "WorkSans-Regular.ttf",
    "lora": "Lora-Regular.ttf",
    "lora_italic": "Lora-Italic.ttf",
    "outfit": "Outfit-Regular.ttf",
    "youngserif": "YoungSerif-Regular.ttf",
    "arsenal": "ArsenalSC-Regular.ttf",
}
# Directions that are not the house typography only need letters for their wordmarks.
FULL_CHARSET = ("gloock", "baskerville", "worksans", "lora_italic")
LETTERS = string.ascii_letters + " \u00b7"
# Web-font subsets shipped for page text (only the families a storefront page sets live).
WEB_SUBSET = ("baskerville", "worksans", "lora", "lora_italic")
CHARSET = (string.ascii_letters + string.digits + " .,:;!?'&-()/+%" + "·’—–"
           "é")


def _ops_pen(glyphset):
    from fontTools.pens.basePen import BasePen

    class OpsPen(BasePen):
        def __init__(self, gs):
            super().__init__(gs)
            self.ops: list = []

        def _moveTo(self, p):
            self.ops.append(["M", round(p[0]), round(p[1])])

        def _lineTo(self, p):
            self.ops.append(["L", round(p[0]), round(p[1])])

        def _qCurveToOne(self, p1, p2):
            self.ops.append(["Q", round(p1[0]), round(p1[1]), round(p2[0]), round(p2[1])])

        def _curveToOne(self, p1, p2, p3):
            self.ops.append(["C", round(p1[0]), round(p1[1]), round(p2[0]), round(p2[1]),
                             round(p3[0]), round(p3[1])])

        def _closePath(self):
            self.ops.append(["Z"])

        _endPath = _closePath

    return OpsPen(glyphset)


def build(src_dir: Path) -> dict:
    from fontTools.ttLib import TTFont

    out: dict = {"_licence": "SIL Open Font License 1.1 (see brand/fonts/*-OFL.txt)",
                 "fonts": {}}
    for key, fname in FONTS.items():
        tt = TTFont(str(src_dir / fname))
        cmap = tt.getBestCmap()
        gs = tt.getGlyphSet()
        hmtx = tt["hmtx"]
        os2 = tt["OS/2"]
        rec = {"file": fname, "upm": tt["head"].unitsPerEm,
               "ascender": tt["hhea"].ascent, "descender": tt["hhea"].descent,
               "cap_height": getattr(os2, "sCapHeight", 0) or 0,
               "x_height": getattr(os2, "sxHeight", 0) or 0, "glyphs": {}}
        for ch in (CHARSET if key in FULL_CHARSET else LETTERS):
            gname = cmap.get(ord(ch))
            if gname is None:
                continue
            pen = _ops_pen(gs)
            gs[gname].draw(pen)
            rec["glyphs"][ch] = {"adv": hmtx[gname][0],
                                 "d": "".join(o[0] + " ".join(map(str, o[1:])) + " "
                                              for o in pen.ops).strip()}
        out["fonts"][key] = rec
    return out


def subset_web(src_dir: Path) -> list[str]:
    from fontTools import subset

    made = []
    for key in WEB_SUBSET:
        fname = FONTS[key]
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga", "onum", "lnum"]
        font = subset.load_font(str(src_dir / fname), opts)
        sub = subset.Subsetter(opts)
        sub.populate(text=CHARSET + string.punctuation + "“”‘… ")
        sub.subset(font)
        dest = FONT_DIR / fname.replace(".ttf", ".subset.woff")
        subset.save_font(font, str(dest), opts)
        made.append(dest.name)
    return made


if __name__ == "__main__":  # pragma: no cover - build tool
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else FONT_DIR
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(src), separators=(",", ":"), sort_keys=True))
    print("wrote", OUT, OUT.stat().st_size, "bytes")
    if "--web" in sys.argv:
        print("web subsets:", subset_web(src))


# ---- owner-concept identity (D-FB-16): separate data file so the research directions'
# outlines stay byte-identical ------------------------------------------------------------------

OWNER_OUT = HERE / "data" / "glyphs_owner.json"
# key -> (source file in src_dir, variable-axis location or None, charset, published file name)
# The published name is what the outline record cites; its family prefix names the licence
# file in brand/fonts/ ("PlayfairDisplay-Bold.ttf" -> PlayfairDisplay-OFL.txt).
OWNER_FONTS = {
    # the monogram B: one design, two weights (the micro-mark is the heavier cut of the SAME B)
    "playfair_bold": ("PlayfairDisplay.ttf", {"wght": 700}, "B", "PlayfairDisplay-Bold.ttf"),
    "playfair_black": ("PlayfairDisplay.ttf", {"wght": 900}, "B", "PlayfairDisplay-Black.ttf"),
    # the spaced serif wordmark
    "cormorant_semibold": ("CormorantGaramond.ttf", {"wght": 600},
                           string.ascii_uppercase + " ", "CormorantGaramond-SemiBold.ttf"),
    # the script tagline
    "allison": ("Allison-Regular.ttf", None, string.ascii_letters + " .,'&-",
                "Allison-Regular.ttf"),
}
# Web subsets for live page text (lane B). Playfair Display carries a Reserved Font Name, so it
# is used ONLY as outlined artwork (the B) and never shipped as a modified (subset) font.
OWNER_WEB = {"cormorant_semibold": "CormorantGaramond-SemiBold.subset.woff",
             "allison": "Allison-Regular.subset.woff"}


def _owner_font(src_dir: Path, key: str):
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    fname, loc, _cs, _pub = OWNER_FONTS[key]
    tt = TTFont(str(src_dir / fname))
    if loc:
        tt = instancer.instantiateVariableFont(tt, loc)
    return tt


def build_owner(src_dir: Path) -> dict:
    out: dict = {"_licence": "SIL Open Font License 1.1 (see brand/fonts/*-OFL.txt)",
                 "_note": "owner-concept identity (D-FB-16); outlines only, nonzero winding",
                 "fonts": {}}
    for key, (_f, loc, charset, pub) in OWNER_FONTS.items():
        tt = _owner_font(src_dir, key)
        cmap = tt.getBestCmap()
        gs = tt.getGlyphSet()
        hmtx = tt["hmtx"]
        os2 = tt["OS/2"]
        rec = {"file": pub, "upm": tt["head"].unitsPerEm, "instance": loc or {},
               "ascender": tt["hhea"].ascent, "descender": tt["hhea"].descent,
               "cap_height": getattr(os2, "sCapHeight", 0) or 0,
               "x_height": getattr(os2, "sxHeight", 0) or 0, "glyphs": {}}
        for ch in charset:
            gname = cmap.get(ord(ch))
            if gname is None:
                continue
            pen = _ops_pen(gs)
            gs[gname].draw(pen)
            rec["glyphs"][ch] = {"adv": hmtx[gname][0],
                                 "d": "".join(o[0] + " ".join(map(str, o[1:])) + " "
                                              for o in pen.ops).strip()}
        out["fonts"][key] = rec
    return out


def subset_owner_web(src_dir: Path) -> list[str]:
    from fontTools import subset

    made = []
    for key, dest_name in OWNER_WEB.items():
        tt = _owner_font(src_dir, key)
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga", "calt", "onum", "lnum"]
        sub = subset.Subsetter(opts)
        sub.populate(text=CHARSET + string.punctuation + "“”‘… ")
        sub.subset(tt)
        dest = FONT_DIR / dest_name
        subset.save_font(tt, str(dest), opts)
        made.append(dest.name)
    return made


def main_owner(src: Path) -> None:  # pragma: no cover - build tool
    """PYTHONPATH=src python -c 'from brambleloop.brand import fontbuild as f; \
    f.main_owner(__import__("pathlib").Path("/dir/with/ttfs"))'"""
    OWNER_OUT.write_text(json.dumps(build_owner(src), separators=(",", ":"), sort_keys=True))
    print("wrote", OWNER_OUT, OWNER_OUT.stat().st_size, "bytes")
    print("web subsets:", subset_owner_web(src))
