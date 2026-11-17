"""Product Truth: the size a title asks for, the size family it belongs to, and the refusal
when the fallback cannot make it (S1 review 6958883678, H1/H2/M1).

Deterministic and closed: a table of size classes per object family, each with the standard it
comes from, and a parser for the size a title states (a class word such as "queen" or
"lumbar", or explicit dimensions such as "200 x 220 cm" / "26 x 26 inch").

Three callers read it:

* `radar.intake` refuses a proposal whose requested size the family cannot make (H2);
* `creative.fallback_constructions.plan` refuses a flat object with no size band and no
  correct template, instead of drafting the default panel under its name (M1), and
  `runtime.pipeline.concept_geometry` drafts at the requested size when the family supports it;
* `gates.certificate.object_size_findings` holds the twin to the size the title claims: the
  named class's band, and the stated dimensions within `TOLERANCE` (H1/H2).

Nothing here estimates from prose. A title with no class word and no dimensions asks for the
family's default size, which the plain template makes and the family band checks.
"""
from __future__ import annotations

import re

INCH_CM = 2.54
# A stated dimension is met when the twin is within this of it: the larger of an absolute
# allowance (one stitch repeat at worsted is about 3.2 cm, so a template cannot land closer
# than half of that) and a relative one (a handmade piece blocks to within a few percent).
TOLERANCE_CM = 2.5
TOLERANCE_REL = 0.07

CYC_BLANKETS = ("Craft Yarn Council, Standard Blanket Sizes (craftyarncouncil.com/standards/"
                "blanket-sizes), inches converted at 2.54 cm")
PILLOW_FORMS = ("standard pillow-form sizes: square 12-26 in, lumbar 12 x 20 in to 14 x 24 in "
                "(the insert sizes cover patterns are written for)")

# ---- size classes ----------------------------------------------------------------------------
# Each class: the words that name it, its band (short side, long side, in cm), the most the
# sides may differ, its default drafted size (short, long) and the standard it comes from.
# A blanket class band spans its CYC sizes with room for blocking; the `baby` class spans
# preemie (18 x 24 in) to crib (45 x 60 in) because "baby blanket" names all of them.
BLANKET_CLASSES: dict[str, dict] = {
    "preemie": {"words": ("preemie", "premie", "nicu"),
                "short": (42.0, 55.0), "long": (55.0, 70.0), "default": (46.0, 61.0),
                "basis": f"preemie 18 x 24 in ({CYC_BLANKETS})"},
    "baby": {"words": ("baby", "receiving", "stroller", "car seat", "carseat", "crib",
                       "cot", "nursery", "newborn", "infant"),
             "short": (42.0, 120.0), "long": (55.0, 160.0), "default": (80.0, 89.0),
             "basis": f"preemie 18 x 24 in to crib 45 x 60 in; stroller 30 x 35 in "
                      f"({CYC_BLANKETS})"},
    "lap": {"words": ("lap", "lapghan", "lap blanket", "lap throw"),
            "short": (80.0, 110.0), "long": (95.0, 135.0), "default": (91.0, 122.0),
            "basis": f"lapghan 36 x 48 in ({CYC_BLANKETS})"},
    "throw": {"words": ("throw", "sofa", "couch"),
              "short": (75.0, 145.0), "long": (90.0, 170.0), "default": (128.0, 152.0),
              "basis": f"lapghan 36 x 48 in to throw 50 x 60 in ({CYC_BLANKETS})"},
    "twin": {"words": ("twin size", "twin sized", "twin bed", "twin blanket", "single bed"),
             "short": (155.0, 185.0), "long": (215.0, 245.0), "default": (168.0, 229.0),
             "basis": f"twin 66 x 90 in ({CYC_BLANKETS})"},
    "full": {"words": ("full size", "full sized", "full bed", "double bed", "double size"),
             "short": (190.0, 215.0), "long": (215.0, 245.0), "default": (203.0, 229.0),
             "basis": f"full 80 x 90 in ({CYC_BLANKETS})"},
    "queen": {"words": ("queen size", "queen sized", "queen bed", "queen blanket"),
              "short": (215.0, 245.0), "long": (240.0, 270.0), "default": (229.0, 254.0),
              "basis": f"queen 90 x 100 in ({CYC_BLANKETS})"},
    "king": {"words": ("king size", "king sized", "king bed", "king blanket",
                       "california king", "cal king"),
             "short": (240.0, 280.0), "long": (260.0, 290.0), "default": (254.0, 274.0),
             "basis": f"king 108 x 100 in ({CYC_BLANKETS})"},
}
PILLOW_CLASSES: dict[str, dict] = {
    "lumbar": {"words": ("lumbar", "oblong", "rectangular", "rectangle", "bolster"),
               "short": (25.0, 40.0), "long": (45.0, 66.0), "min_aspect": 1.4,
               "default": (30.0, 50.0), "basis": PILLOW_FORMS},
}

# Objects the fallback has a correct flat template and a band for, by the family word in the
# title (`gates.first_customer.PRODUCT_TYPE_FAMILIES`) or, when the title names none, by the
# radar category. `None` for a category means the category's template is a strip with no
# object behind it: the title must name a supported object or the draft is refused.
CATEGORY_OBJECT: dict[str, str | None] = {
    "blanket": "blanket", "mosaic_blanket": "blanket", "graphghan": "blanket",
    "runner": "runner", "placemat": "placemat", "dishcloth": "dishcloth",
    "coaster": "coaster", "pillow": "pillow", "wedding": "pillow", "wall_decor": "wall_hanging",
    "pet": "pet_mat", "scarf": "scarf",
    "baby": None, "seasonal_decor": None, "flower": None, "ornament": None,
}
SUPPORTED_FLAT = frozenset({"blanket", "runner", "placemat", "dishcloth", "coaster", "pillow",
                            "wall_hanging", "pet_mat", "scarf", "burp_cloth"})

# M1: named flat objects with no size band and no correct template. Refused by name rather than
# drafted as the default 32 x 9.8 cm panel (or another object's template) under that name.
NO_TEMPLATE: dict[str, str] = {
    r"\blove?y(?:s|ies)?\b": "a lovey is a small security blanket with a stuffed head or toy "
                             "joined to it; the fallback makes neither the toy nor the join",
    r"\bbibs?\b": "a bib needs a shaped neck opening and a tie or fastening; a flat rectangle "
                  "is not a bib",
    r"\brugs?\b": "a rug needs its own size band, a firm fabric and a non-slip backing",
    r"\bbath ?mats?\b": "a bath mat needs its own size band and a dense, absorbent fabric",
    r"\b(?:table ?cloth|tablecloth)s?\b": "a tablecloth is sized to a table; there is no band "
                                          "or template for it",
    r"\bhot ?pads?\b|\bpot ?holders?\b|\btrivets?\b": (
        "a hot pad needs a double-thickness heat-safe fabric and its own band"),
    r"\bdoil(?:y|ies)\b": "a doily is a lace motif worked in the round, not a flat panel",
    r"\bpoufs?\b|\bpouffes?\b|\bottomans?\b": "a pouf is a stuffed three-dimensional form",
}

BURP_CLOTH = r"\bburp ?(?:cloth|rag)s?\b"
RELATIVE_SIZE = (r"\b(?:extra[- ]?large|x-?large|xl|xxl|oversized?|giant|jumbo|huge|large|big|"
                 r"small|mini|tiny|petite|short)\b")

_DIM2 = re.compile(r"(\d+(?:\.\d+)?)\s*(cm|centimet(?:er|re)s?|in(?:ch(?:es)?)?\b|\"|'')?\s*"
                   r"(?:x|×|by)\s*(\d+(?:\.\d+)?)\s*(cm|centimet(?:er|re)s?|in(?:ch(?:es)?)?\b"
                   r"|\"|'')")
_DIM1 = re.compile(r"(\d+(?:\.\d+)?)\s*(cm|centimet(?:er|re)s?|in(?:ch(?:es)?)?\b|\"|'')")


def _fold(title: str | None) -> str:
    from .fallback_constructions import fold_title

    return fold_title(title)


def _cm(value: str, unit: str | None) -> float:
    v = float(value)
    return round(v * INCH_CM, 1) if unit and not unit.startswith(("c",)) else v


def stated_dimensions(title: str | None) -> tuple[float, ...]:
    """The dimensions a title states, in cm: (short, long), (one,) or ()."""
    text = (title or "").lower().replace("×", "x")
    m = _DIM2.search(text)
    if m:
        unit = m.group(4)
        a, b = _cm(m.group(1), m.group(2) or unit), _cm(m.group(3), unit)
        return (min(a, b), max(a, b))
    m = _DIM1.search(text)
    return (_cm(m.group(1), m.group(2)),) if m else ()


def _has(words, folded: str) -> list[str]:
    return [w for w in words if re.search(rf"\b{re.escape(w)}\b", folded)]


def object_of(category: str | None, title: str | None) -> str | None:
    """The banded flat object a title (else its category) names, or None."""
    from ..gates.first_customer import _family_hits

    folded = _fold(title)
    if re.search(BURP_CLOTH, folded):
        return "burp_cloth"
    hits = set(_family_hits(title or ""))
    # A cushion, mat or scarf first: "Throw Pillow" is a pillow, not a throw.
    for family, obj in (("pillow", "pillow"), ("runner", "runner"), ("placemat", "placemat"),
                        ("dishcloth", "dishcloth"), ("coaster", "coaster"), ("scarf", "scarf"),
                        ("wall_hanging", "wall_hanging"), ("blanket", "blanket")):
        if family in hits:
            return obj
    if re.search(r"\btapestr(?:y|ies)\b|\bwall (?:art|decor)\b", folded) and \
            category == "wall_decor":
        return "wall_hanging"
    return CATEGORY_OBJECT.get(category or "")


def named_classes(obj: str | None, title: str | None) -> dict[str, dict]:
    """The size classes the title names for `obj` (blanket / pillow), or {}."""
    folded = _fold(title)
    table = BLANKET_CLASSES if obj == "blanket" else PILLOW_CLASSES if obj == "pillow" else {}
    return {k: c for k, c in table.items() if _has(c["words"], folded)}


def band(obj: str | None) -> dict | None:
    """The family band (`gates.certificate.OBJECT_SIZE_BANDS` shape) for `obj`, or None."""
    from ..gates.certificate import OBJECT_SIZE_BANDS

    return OBJECT_SIZE_BANDS.get(obj or "")


def _in_band(b: dict, short: float, long_: float) -> bool:
    if "side_cm" in b:
        lo, hi = b["side_cm"]
        return lo <= short and long_ <= hi and long_ / max(short, 1e-9) <= b["max_aspect"]
    (slo, shi), (llo, lhi) = b["short_cm"], b["long_cm"]
    return slo <= short <= shi and llo <= long_ <= lhi


def _in_class(c: dict, short: float, long_: float) -> bool:
    aspect = long_ / max(short, 1e-9)
    return (c["short"][0] <= short <= c["short"][1] and c["long"][0] <= long_ <= c["long"][1]
            and aspect >= c.get("min_aspect", 0.0))


def _met(stated: float, made: float) -> bool:
    return abs(stated - made) <= max(TOLERANCE_CM, TOLERANCE_REL * stated)


def applies(category: str | None, title: str | None) -> bool:
    """Whether the title or category is a flat object this module decides the size of."""
    folded = _fold(title)
    return ((category or "") in CATEGORY_OBJECT or object_of(category, title) is not None
            or any(re.search(p, folded) for p in NO_TEMPLATE))


def request(category: str | None, title: str | None) -> dict:
    """What size the title asks for, and whether the fallback can make it.

    Returns {"object", "classes", "dims", "target": (short, long) | None, "refused": why | None}.
    `target` is None when the template's own size is the answer (no class word, no dimensions).
    """
    folded = _fold(title)
    obj = object_of(category, title)
    out = {"object": obj, "classes": [], "dims": stated_dimensions(title), "target": None,
           "refused": None}
    for pattern, why in NO_TEMPLATE.items():
        if re.search(pattern, folded):
            out["refused"] = f"{why}: there is no size band and no correct template for it"
            return out
    if obj is None:
        out["refused"] = (f"the title names no object with a size band and a correct flat "
                          f"template (category {category!r} has none of its own), so the "
                          f"fallback would draft the default panel under that name")
        return out
    classes = named_classes(obj, title)
    out["classes"] = sorted(classes)
    dims = out["dims"]
    if dims:
        b = band(obj)
        if len(dims) == 1 and b is not None and "side_cm" in b:
            # One figure on a square object is its side ("Pillow Cover 18 inch").
            dims = (dims[0], dims[0])
        if len(dims) == 1:
            if b is None:
                out["refused"] = (f"the title states one dimension ({dims[0]:g} cm) for a "
                                  f"{obj.replace('_', ' ')}, which has no size band")
                return out
            # A single figure on an oblong object is its length ("Table Runner 72 in").
            (slo, shi), (llo, lhi) = b["short_cm"], b["long_cm"]
            if not llo <= dims[0] <= lhi:
                out["refused"] = (f"the title asks for a {obj.replace('_', ' ')} {dims[0]:g} cm "
                                  f"long; the {obj.replace('_', ' ')} band is {llo:g}-{lhi:g} cm "
                                  f"long ({b['basis']})")
                return out
            out["target"] = (round((slo + shi) / 2 if obj != "runner" else 35.0, 1), dims[0])
            return out
        short, long_ = dims
        fits = [k for k, c in classes.items() if _in_class(c, short, long_)]
        if classes and not fits:
            out["refused"] = (f"the title asks for {short:g} x {long_:g} cm and names "
                              f"{', '.join(sorted(classes))}, whose band does not hold it")
            return out
        if b is None or not _in_band(b, short, long_):
            where = f" ({b['basis']})" if b else ""
            out["refused"] = (f"the title asks for a {obj.replace('_', ' ')} of {short:g} x "
                              f"{long_:g} cm, outside the size the family is made in{where}")
            return out
        out["target"] = (short, long_)
        return out
    rel = re.search(RELATIVE_SIZE, folded)
    if rel and not classes:
        out["refused"] = (f"the title names a size ({rel.group(0)!r}) with no dimensions; the "
                          f"template makes one size and cannot back a relative size word")
        return out
    if classes:
        # The first named class in table order decides the draft size ("Baby Throw": baby).
        table = BLANKET_CLASSES if obj == "blanket" else PILLOW_CLASSES
        first = next(k for k in table if k in classes)
        out["target"] = table[first]["default"]
    elif obj == "burp_cloth":
        out["target"] = BURP_CLOTH_SIZE
    return out


# A burp cloth: about 25 x 50 cm (10 x 20 in), the size sold and written for.
BURP_CLOTH_SIZE = (25.0, 50.0)


def findings(title: str | None, width_cm: float, height_cm: float,
             category: str | None = None) -> list[str]:
    """Why a finished size does not match the size the title claims, or [] when it does."""
    if not width_cm or not height_cm:
        return []
    short, long_ = sorted((float(width_cm), float(height_cm)))
    obj = object_of(category, title)
    out: list[str] = []
    classes = named_classes(obj, title)
    if classes and not any(_in_class(c, short, long_) for c in classes.values()):
        names = ", ".join(sorted(classes))
        bases = "; ".join(f"{k}: {c['short'][0]:g}-{c['short'][1]:g} x "
                          f"{c['long'][0]:g}-{c['long'][1]:g} cm ({c['basis']})"
                          for k, c in sorted(classes.items()))
        out.append(f"the title names a {names} {obj}, and the pattern's finished size "
                   f"{short:.1f} x {long_:.1f} cm is outside that size class ({bases})")
    dims = stated_dimensions(title)
    if len(dims) == 2 and not (_met(dims[0], short) and _met(dims[1], long_)):
        out.append(f"the title states {dims[0]:g} x {dims[1]:g} cm, and the pattern makes "
                   f"{short:.1f} x {long_:.1f} cm")
    elif len(dims) == 1 and not (_met(dims[0], long_) or _met(dims[0], short)):
        out.append(f"the title states {dims[0]:g} cm, and neither side of the pattern's "
                   f"{short:.1f} x {long_:.1f} cm is that")
    return out
