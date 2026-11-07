"""V5 / audit P1-c: product scale against the CIR's finished size, from known-size anchors.

No generated-image check measured how big the product looks. A 16 cm basket drawn at the
size of a laundry hamper passed every gate: the palette, the construction and the identity
were right, and only the scale was wrong. Point 5 of the audit says so.

**Who does what.** The vision judge only *points*: it names one known-size anchor object it
can see and gives two boxes, the anchor's and the product's, as fractions of the frame. Code
does the measuring:
- ratio = product box's long side / anchor box's long side, in pixels;
- implied size = ratio × the anchor's known size (`ANCHORS`, centimetres);
- that is compared with the twin's longest finished dimension.

The judge is never told the product's size, so it cannot steer the result.

**Verdicts.**
- PASS: within `TOLERANCE` (±40 %; perspective and foreshortening are real).
- FAIL `product_scale`: outside it.
- UNKNOWN, never PASS:
  - no judge, or no answer;
  - no listed anchor visible;
  - a box that is malformed or degenerate;
  - a CIR whose twin states no finished size.

**Blind spots.** Strong perspective (an anchor much nearer the camera than the product);
anchors that are themselves an unusual size; a product partly out of frame.
"""
from __future__ import annotations

import io

CHECK = "product_scale"
TOLERANCE = 0.40
MIN_BOX_FRAC = 0.01           # a box side under 1 % of the frame is too small to measure

# Everyday objects of near-standard size, by their longest visible dimension in centimetres.
# Only these may anchor a measurement; anything else the judge names is "no anchor".
ANCHORS: dict[str, float] = {
    "coffee mug": 9.5,              # height
    "dinner plate": 27.0,           # diameter
    "standard paperback book": 18.0,
    "tea towel folded in thirds": 25.0,
    "a4 or letter sheet of paper": 29.0,
    "apple": 8.0,
    "kitchen chair seat": 42.0,     # width
    "pillow": 66.0,                 # standard bed pillow, long side
}


def expected_cm(cir) -> float | None:
    """The product's longest finished dimension, from the twin (the CIR's own figures)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    try:
        twin = build_twin(cir, compile_cir(cir))
    except Exception:  # noqa: BLE001 - no twin, no expectation
        return None
    dims = [d for d in (twin.width_cm, twin.height_cm,
                        getattr(twin, "across_points_cm", None)) if d]
    return float(max(dims)) if dims else None


def prompt() -> str:
    names = "; ".join(sorted(ANCHORS))
    return ("Find the handmade crochet item in this photograph, and one of these everyday "
            f"objects if one is clearly visible: {names}. Give each as a box in fractions of "
            "the image width and height. Do not estimate any size. Answer as JSON: "
            '{"anchor": "<one name from the list, or none>", "anchor_box": [x0, y0, x1, y1], '
            '"product_box": [x0, y0, x1, y1]}')


def _box(v, w: int, h: int):
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(t) for t in v)
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    pw, ph = (x1 - x0) * w, (y1 - y0) * h
    if min(x1 - x0, y1 - y0) < MIN_BOX_FRAC:
        return None
    return max(pw, ph)


def measure(reading: dict, size: tuple[int, int], expected: float | None) -> dict:
    """The deterministic half: the judge's boxes -> implied centimetres -> verdict."""
    from .vision_judges import FAIL, PASS, UNKNOWN, _c

    if not expected:
        return _c(CHECK, UNKNOWN, "the CIR states no finished size to compare with")
    name = str(reading.get("anchor") or "").strip().lower()
    if name not in ANCHORS:
        return _c(CHECK, UNKNOWN, f"no known-size anchor in frame ({name or 'none'})",
                  needs="a listed anchor object in the scene")
    w, h = size
    a, p = _box(reading.get("anchor_box"), w, h), _box(reading.get("product_box"), w, h)
    if a is None or p is None:
        return _c(CHECK, UNKNOWN, "a box is missing, malformed or too small to measure")
    implied = p / a * ANCHORS[name]
    rel = implied / expected - 1.0
    measured = {"anchor": name, "anchor_cm": ANCHORS[name], "implied_cm": round(implied, 1),
                "expected_cm": round(expected, 1), "relative": round(rel, 3)}
    if abs(rel) <= TOLERANCE:
        return _c(CHECK, PASS, f"reads about {implied:.0f} cm against the CIR's "
                               f"{expected:.0f} cm (beside a {name})", **measured)
    return _c(CHECK, FAIL, f"reads about {implied:.0f} cm against the CIR's {expected:.0f} cm "
                           f"({rel:+.0%}, beside a {name})", code=CHECK, **measured)


def verify(judge, data: bytes, cir) -> dict:
    """The scale verdict for one generated frame."""
    from PIL import Image

    from . import vision_judges as VJ

    expected = expected_cm(cir)
    if not expected:
        return VJ._c(CHECK, VJ.UNKNOWN, "the CIR states no finished size to compare with")
    got = VJ.ask(judge, "product_scale", prompt(), [data], max_tokens=300)
    if not got["answered"]:
        return VJ._c(CHECK, VJ.UNKNOWN, f"not judged: {got['why']}", needs="vision judge")
    try:
        size = Image.open(io.BytesIO(data)).size
    except Exception as exc:  # noqa: BLE001
        return VJ._c(CHECK, VJ.UNKNOWN, f"undecodable image ({type(exc).__name__})")
    return {**measure(got["reading"], size, expected), "judge": got["judge"]}
