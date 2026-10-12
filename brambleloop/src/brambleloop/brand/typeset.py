"""Set text as outlined paths from the bundled open-licence glyph data (`data/glyphs.json`).

The identity never ships an SVG <text> element: outlines render the same on every device
(see `fontbuild`). Spacing is the font's advance widths plus explicit tracking plus an optional
per-pair optical kerning table that a wordmark carries as data -- the hand-kerning a designer
would do, written down so it is reproducible.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path as _FsPath

from .vector import Path

DATA = _FsPath(__file__).resolve().parent / "data" / "glyphs.json"
# The owner-concept identity's fonts (D-FB-16) live in their own file so the research
# directions' outlines stay byte-identical; both are merged into one font table.
OWNER_DATA = DATA.parent / "glyphs_owner.json"
_TOK = re.compile(r"[MLQCZ]|-?\d+")


@lru_cache(maxsize=1)
def _fonts() -> dict:
    fonts = dict(json.loads(DATA.read_text())["fonts"])
    if OWNER_DATA.exists():
        fonts.update(json.loads(OWNER_DATA.read_text())["fonts"])
    return fonts


def font_metrics(font: str) -> dict:
    rec = _fonts()[font]
    return {k: rec[k] for k in ("upm", "ascender", "descender", "cap_height", "x_height", "file")}


def has_glyphs(font: str, text: str) -> bool:
    g = _fonts()[font]["glyphs"]
    return all(ch in g for ch in text)


@lru_cache(maxsize=4096)
def _glyph_ops(font: str, ch: str) -> tuple:
    d = _fonts()[font]["glyphs"][ch]["d"]
    toks = _TOK.findall(d)
    ops: list[tuple] = []
    i = 0
    arity = {"M": 2, "L": 2, "Q": 4, "C": 6, "Z": 0}
    while i < len(toks):
        k = toks[i]
        n = arity[k]
        nums = [int(t) for t in toks[i + 1:i + 1 + n]]
        ops.append((k, *[(nums[j], nums[j + 1]) for j in range(0, n, 2)]))
        i += 1 + n
    return tuple(ops)


def advance(font: str, ch: str) -> int:
    return _fonts()[font]["glyphs"][ch]["adv"]


def measure(font: str, text: str, size: float, tracking: float = 0.0,
            kern: dict[str, float] | None = None) -> float:
    """Advance width of `text` in output units. `tracking` is in em; `kern` maps pairs to em."""
    upm = _fonts()[font]["upm"]
    s = size / upm
    w = 0.0
    for i, ch in enumerate(text):
        w += advance(font, ch) * s
        if i < len(text) - 1:
            w += tracking * size
            if kern:
                w += kern.get(text[i:i + 2], 0.0) * size
    return w


def set_text(font: str, text: str, size: float, x: float, baseline: float, *,
             tracking: float = 0.0, anchor: str = "start",
             kern: dict[str, float] | None = None,
             substitute: dict[int, Path] | None = None) -> Path:
    """Outlined text as one Path. `size` = em size in output units, y grows downward.

    `substitute` maps character index -> a replacement Path drawn in that glyph's slot (in
    output units, positioned by the caller relative to the slot origin returned by
    `glyph_slots`); used by wordmarks that swap one letter for a drawn form.
    """
    upm = _fonts()[font]["upm"]
    s = size / upm
    width = measure(font, text, size, tracking, kern)
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    out = Path()
    pen = x
    for i, ch in enumerate(text):
        if substitute and i in substitute:
            out.extend(substitute[i].transformed(tx=pen, ty=baseline))
        else:
            ox = pen
            for op in _glyph_ops(font, ch):
                out.ops.append((op[0],) + tuple((ox + px * s, baseline - py * s)
                                               for px, py in op[1:]))
        pen += advance(font, ch) * s
        if i < len(text) - 1:
            pen += tracking * size + (kern.get(text[i:i + 2], 0.0) * size if kern else 0.0)
    return out


def glyph_slots(font: str, text: str, size: float, x: float, *, tracking: float = 0.0,
                anchor: str = "start", kern: dict[str, float] | None = None
                ) -> list[tuple[float, float]]:
    """(left, advance) of each character as `set_text` would place it."""
    upm = _fonts()[font]["upm"]
    s = size / upm
    width = measure(font, text, size, tracking, kern)
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    out = []
    pen = x
    for i, ch in enumerate(text):
        adv = advance(font, ch) * s
        out.append((pen, adv))
        pen += adv
        if i < len(text) - 1:
            pen += tracking * size + (kern.get(text[i:i + 2], 0.0) * size if kern else 0.0)
    return out


def glyph(font: str, ch: str, size: float, x: float = 0.0, baseline: float = 0.0) -> Path:
    return set_text(font, ch, size, x, baseline)
