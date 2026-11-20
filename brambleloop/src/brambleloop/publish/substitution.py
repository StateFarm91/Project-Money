"""Yarn substitution and colourway guidance, computed from the pattern rather than written.

Requirement 7's buildable half. A flagship competes as a complete project system, and the
part of that system a buyer hits first is the one nobody else answers: *I cannot get that
yarn. What can I use, and how much of it?*

The answer is normally a paragraph of confident prose. Here it is arithmetic on the CIR, and
it refuses in three places rather than guessing.

**Gauge decides, not the weight name.** Yarn weight names are a marketing category and their
gauge ranges overlap heavily; a "worsted" from one mill works to a different fabric than a
"worsted" from another. So a substitute qualifies when the *pattern's own gauge* falls inside
that weight's published band, and a pattern with no gauge gets no substitution guidance at
all -- a guide without a gauge is a guess with a table around it.

**Across fibres, a direction and never a number.** Cotton and acrylic at the same weight do
not use the same length of yarn per stitch. `quality/physical.calibration_key` learned this
the expensive way -- keying a measured factor on weight alone would have let a firm cotton
basket rewrite the yardage on an acrylic throw. So a cross-fibre substitution says which way
the yardage moves and declines to say how far, because how far is measured, not derived.

**Buy-more, never buy-exactly.** Every figure here carries a margin, and the number a buyer
is given is the one with the margin in it. A pattern that tells somebody to buy exactly
enough is a pattern that runs them out in the last row, in a dye lot that has gone.

And the arithmetic is deliberately not the obvious one. Scaling a pattern's yardage by the
ratio of two weights' lengths per 100g looks right and is wrong: that ratio is about *mass*,
not about length used. At the same gauge and finished size the stitch count is identical and
each stitch's yarn path is the same size, so the metres barely move -- what moves is how many
balls those metres arrive in, and how heavy the finished object is. That is also the question
somebody standing in a shop is actually asking.
"""
from __future__ import annotations

from dataclasses import dataclass

# Craft Yarn Council standard weights. `sc_per_10cm` is the published single-crochet gauge
# band; `metres_per_100g` is the typical length of a 100g ball at that weight. Both are bands
# rather than points, because both vary by mill and pretending otherwise is the whole error
# this module exists to avoid.
@dataclass(frozen=True)
class Weight:
    key: str
    number: int
    also_called: tuple[str, ...]
    sc_per_10cm: tuple[float, float]
    metres_per_100g: tuple[float, float]


WEIGHTS: tuple[Weight, ...] = (
    Weight("lace", 0, ("thread", "cobweb", "2-ply"), (32.0, 42.0), (600.0, 1000.0)),
    Weight("super_fine", 1, ("fingering", "sock", "4-ply"), (21.0, 32.0), (350.0, 500.0)),
    Weight("fine", 2, ("sport", "baby", "5-ply"), (16.0, 20.0), (250.0, 350.0)),
    Weight("light", 3, ("dk", "light worsted", "8-ply"), (12.0, 17.0), (200.0, 260.0)),
    Weight("medium", 4, ("worsted", "aran", "afghan", "10-ply"), (11.0, 14.0), (140.0, 200.0)),
    Weight("bulky", 5, ("chunky", "craft", "rug", "12-ply"), (8.0, 11.0), (100.0, 140.0)),
    Weight("super_bulky", 6, ("super chunky", "roving"), (5.0, 9.0), (60.0, 100.0)),
    Weight("jumbo", 7, ("arm knitting",), (1.0, 6.0), (20.0, 60.0)),
)

WEIGHT_BY_KEY: dict[str, Weight] = {w.key: w for w in WEIGHTS}
_ALIAS: dict[str, str] = {alias: w.key for w in WEIGHTS for alias in (w.key,) + w.also_called}

# Fibre classes that do not substitute for each other by arithmetic. Not a ban -- makers do
# it constantly and it is often the point -- but the yardage change is measured, not derived,
# so this module gives a direction and stops.
FIBRE_CLASSES: dict[str, tuple[str, ...]] = {
    "plant": ("cotton", "linen", "hemp", "bamboo", "ramie"),
    "protein": ("wool", "merino", "alpaca", "mohair", "cashmere", "silk", "yak"),
    "synthetic": ("acrylic", "polyester", "nylon", "microfibre", "microfiber"),
}

# How much more than the estimate a buyer is told to get. The estimate already carries the
# twin's own uncertainty; this is the substitution's, and it is the difference between a
# project finished and a project abandoned one row short in a discontinued dye lot.
BUY_MARGIN = 0.15

# Below this separation in perceived lightness, a two-colour motif stops reading. Set on
# value rather than hue because a photograph at mobile-grid scale is very nearly greyscale:
# two colours of equal lightness merge there however different they look in the hand.
MIN_VALUE_SEPARATION = 25.0


class SubstitutionRefused(ValueError):
    """A substitution guide asked for where the pattern does not support one."""


def normalise(name: str | None) -> str:
    """A ball band's word for its weight, mapped to the standard class. "" when unknown."""
    text = (name or "").strip().lower().replace("-", " ")
    if text in _ALIAS:
        return _ALIAS[text]
    for alias, key in _ALIAS.items():
        if alias in text:
            return key
    return ""


def fibre_class(name: str | None) -> str:
    """Which fibre family a yarn description belongs to, or "" when it does not say."""
    text = (name or "").lower()
    for family, fibres in FIBRE_CLASSES.items():
        if any(fibre in text for fibre in fibres):
            return family
    return ""


def holds_gauge(weight: Weight, sc_per_10cm: float) -> bool:
    low, high = weight.sc_per_10cm
    return low <= sc_per_10cm <= high


def substitutes(sc_per_10cm: float, *, declared: str = "") -> dict:
    """Which standard weights can be worked to this pattern's gauge.

    The declared weight is reported alongside rather than assumed: a pattern whose stated
    weight does not hold its own gauge is worth knowing about, and it is usually a gauge
    somebody typed rather than swatched.
    """
    if sc_per_10cm <= 0:
        raise SubstitutionRefused("gauge must be positive to substitute against")
    holding = [w for w in WEIGHTS if holds_gauge(w, sc_per_10cm)]
    declared_key = normalise(declared)
    return {
        "gauge_sc_per_10cm": sc_per_10cm,
        "declared": declared_key,
        "declared_holds_gauge": (bool(declared_key)
                                 and holds_gauge(WEIGHT_BY_KEY[declared_key], sc_per_10cm)),
        "weights": [{"weight": w.key, "number": w.number,
                     "also_called": list(w.also_called),
                     "sc_per_10cm": list(w.sc_per_10cm),
                     "metres_per_100g": list(w.metres_per_100g)} for w in holding],
        "note": ("Gauge decides, not the name on the band. Any of these can be worked to "
                 "this fabric; swatch and change hook until the gauge matches, because the "
                 "gauge is what makes the finished size come out"
                 if holding else
                 "no standard weight's published band contains this gauge, which usually "
                 "means the gauge was typed rather than swatched"),
    }


def how_much(estimate_metres: float, *, from_weight: str, to_weight: str,
             from_fibre: str = "", to_fibre: str = "") -> dict:
    """How much of the substitute to buy, and in how many balls.

    The arithmetic here is not the obvious one, and the obvious one is wrong. It is tempting
    to scale the yardage by the ratio of the two weights' lengths per 100g -- and that
    produces a confidently wrong number, because *length per 100g is about mass, not about
    length used*. At the same gauge and the same finished size the stitch count is identical
    and each stitch's yarn path is the same size, so the **metres are approximately
    unchanged**. What changes is how many balls those metres come in, and how heavy the
    finished object is.

    So the metres come through as the pattern's own estimate plus the buy margin, and the
    substitution's real answer is the ball count -- which is the question somebody standing
    in a shop is actually asking.

    Across fibre classes it returns a direction and no number, because the per-stitch
    difference between cotton and acrylic is measured on a sample and this module has not
    seen one.
    """
    a, b = normalise(from_weight), normalise(to_weight)
    if not a or not b:
        raise SubstitutionRefused(
            f"{from_weight!r} -> {to_weight!r}: a substitution needs two weights this can "
            f"place on the standard scale")
    if estimate_metres <= 0:
        raise SubstitutionRefused("there is no yardage estimate to adjust")

    across = fibre_class(from_fibre), fibre_class(to_fibre)
    if all(across) and across[0] != across[1]:
        return {
            "measurable": False,
            "from": a, "to": b,
            "fibre_change": f"{across[0]} to {across[1]}",
            "why": ("cotton and acrylic at the same weight do not use the same length of "
                    "yarn per stitch, and how much they differ is measured on a sample "
                    "rather than derived from a table. Swatch, weigh the swatch, and scale "
                    "the pattern's estimate by what you measure"),
        }

    buy = round(estimate_metres * (1.0 + BUY_MARGIN), 1)
    low_per_ball, high_per_ball = WEIGHT_BY_KEY[b].metres_per_100g
    balls = sorted((_ceil(buy / high_per_ball), _ceil(buy / low_per_ball)))
    heavier = WEIGHT_BY_KEY[b].number - WEIGHT_BY_KEY[a].number
    return {
        "measurable": True,
        "from": a, "to": b,
        "estimate_metres": round(estimate_metres, 1),
        "buy_metres": buy,
        "buy_margin": BUY_MARGIN,
        "balls_100g": list(balls),
        "fabric_changes": (
            "the finished piece will be heavier and denser" if heavier > 0 else
            "the finished piece will be lighter and more open" if heavier < 0 else
            "the fabric should come out close to the original"),
        "why": (f"at this gauge the stitch count and each stitch's yarn path are unchanged, "
                f"so the metres are the pattern's own estimate plus {BUY_MARGIN:.0%} -- a "
                f"pattern that tells somebody to buy exactly enough runs them out in the "
                f"last row in a dye lot that has gone. What the substitution actually "
                f"changes is how many balls those metres arrive in, and how the fabric "
                f"feels. Scaling the yardage by length-per-100g is the obvious arithmetic "
                f"and it is wrong: that ratio is about mass, not about length used"),
    }


def _ceil(value: float) -> int:
    import math

    return int(math.ceil(value))


def value_of(hex_code: str) -> float:
    """Perceived lightness 0-100 from a hex colour. Rec. 709 luma, which is what a camera sees."""
    text = (hex_code or "").lstrip("#")
    if len(text) != 6:
        raise SubstitutionRefused(f"{hex_code!r} is not a six-digit hex colour")
    r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    return round((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0 * 100.0, 1)


def colourway(colours: list[dict]) -> dict:
    """Whether a proposed colourway keeps the motif readable, and which pair does not.

    Checked on lightness rather than hue. A photograph at mobile-grid scale is very nearly
    greyscale, and two colours of equal lightness merge there however different they look in
    the hand -- which is the difference between a motif and a smudge in the thumbnail a buyer
    actually decides from.
    """
    named = [c for c in colours if c.get("hex")]
    if len(named) < 2:
        return {"measurable": False, "colours": len(named),
                "why": ("a one-colour pattern has no contrast to check, and a colourway "
                        "nobody has stated in hex cannot be measured -- a colour name is "
                        "somebody's word for it")}
    values = {c.get("role") or c["hex"]: value_of(c["hex"]) for c in named}
    pairs = []
    keys = list(values)
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            gap = round(abs(values[left] - values[right]), 1)
            pairs.append({"between": [left, right], "value_gap": gap,
                          "reads": gap >= MIN_VALUE_SEPARATION})
    weakest = min(pairs, key=lambda p: p["value_gap"])
    return {
        "measurable": True,
        "colours": len(named),
        "values": values,
        "pairs": sorted(pairs, key=lambda p: p["value_gap"]),
        "reads": all(p["reads"] for p in pairs),
        "weakest_pair": weakest,
        "minimum_value_separation": MIN_VALUE_SEPARATION,
        "why": ("every pair separates enough in lightness to survive a thumbnail"
                if all(p["reads"] for p in pairs) else
                f"{weakest['between']} are {weakest['value_gap']} apart in lightness, under "
                f"{MIN_VALUE_SEPARATION}. They will merge in the grid however different they "
                f"look in the hand"),
    }


def guidance(cir, twin=None, *, colours: list[dict] | None = None) -> dict:
    """The complete substitution block for one pattern, or the reason there is not one."""
    if cir.gauge is None:
        raise SubstitutionRefused(
            "this pattern states no gauge, so it gets no substitution guidance. A guide "
            "without a gauge is a guess with a table around it")

    declared = cir.gauge.yarn_weight or next(
        (m.yarn_weight for m in cir.materials if m.yarn_weight), None)
    fibre = next((m.name for m in cir.materials if m.name), "")
    options = substitutes(cir.gauge.stitches_per_10cm, declared=declared or "")

    estimate = 0.0
    if twin is not None:
        estimate = round(sum((twin.yarn_metres_by_color or {}).values()), 1)

    per_weight = []
    for option in options["weights"]:
        if not declared or normalise(declared) == option["weight"]:
            continue
        if estimate <= 0:
            per_weight.append({"weight": option["weight"], "measurable": False,
                               "why": "this pattern carries no yardage estimate to adjust"})
            continue
        per_weight.append(how_much(estimate, from_weight=declared,
                                   to_weight=option["weight"],
                                   from_fibre=fibre, to_fibre=fibre))

    return {
        "gauge": {"stitches_per_10cm": cir.gauge.stitches_per_10cm,
                  "rows_per_10cm": cir.gauge.rows_per_10cm,
                  "stitch_type": cir.gauge.stitch_type,
                  "hook_mm": cir.gauge.hook_mm},
        "declared_weight": normalise(declared or ""),
        "declared_fibre_class": fibre_class(fibre),
        "substitutes": options,
        "estimate_metres": estimate,
        "how_much": per_weight,
        "colourway": colourway(colours or []),
        "note": ("Computed from this pattern's own gauge and yardage, not written about it. "
                 "Swatch before buying: the gauge is what makes the finished size come out, "
                 "and every figure here is a band with the buy number at the top of it."),
    }
