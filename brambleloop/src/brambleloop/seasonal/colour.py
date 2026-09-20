"""Dated palette intelligence, and the line between a colourway and a different product.

Requirement 280. Maintain seasonal palette intelligence from marketplace evidence, let a
concept receive multiple seasonally appropriate colourways, and treat a colour change as a
merchandising variant **only when the underlying pattern truth supports it** -- with imagery
and listing claims matching the actual colourway.

The evidence is free and already collected. Etsy publishes per-image hex, hue, saturation and
brightness, so every audited benchmark listing carries the colours its photographs actually
contain, with the date they were read. That is what "dated palette intelligence from current
marketplace evidence" means here: not a forecast somebody wrote, a count of what a proven
seller in this department is photographing, and when it was seen.

Two things this module refuses, and they are the requirement's own conditions.

**A palette read from nothing is not intelligence.** A department where no gallery has been
audited has no observed palette, and reporting an empty one as "neutral" or "unknown but
fine" would let a colourway decision rest on nothing. It reports unmeasurable with the count.

**A colour change is a variant only while the pattern is unchanged.** Same number of colours,
same roles, same structure. A two-colour pattern given a three-colour way is not a colourway,
it is a different pattern wearing one's name -- and shipping it as a variant is how a
catalogue's version accounting stops meaning anything. The check is on the CIR, because the
CIR is the only place the pattern truth lives.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Below this many audited listings a "seasonal palette" is one photographer's habit. Matched
# to the floor `commerce/intent.arena_language` uses for the same reason.
MIN_AUDITED = 5

# How many colours of a palette are worth reporting. Past this the tail is background.
TOP_COLOURS = 8

# Two colours closer than this in perceived lightness merge in a thumbnail and on a greyscale
# print. The same threshold the substitution guide and the value stack use, because it is the
# same failure in three places.
from ..publish.substitution import MIN_VALUE_SEPARATION, value_of  # noqa: E402


class ColourRefused(ValueError):
    """A colourway that changes the pattern, or a palette read from nothing."""


@dataclass(frozen=True)
class Swatch:
    hex: str
    seen_in_listings: int
    value: float          # perceived lightness, 0-100

    def to_dict(self) -> dict:
        return {"hex": self.hex, "seen_in_listings": self.seen_in_listings,
                "value": self.value}


def observed_palette(db, *, pod: str = "", benchmark_key: str = "",
                     seasonal: str = "") -> dict:
    """What this department is actually photographed in, and when that was seen.

    Dated on purpose. A palette with no observation window is a claim about taste; a palette
    with one is a measurement that can go stale and be seen to have gone stale.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = [r for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key))
            if (not pod or r.pod == pod) and (not seasonal or r.seasonal == seasonal)]

    audited = [r for r in rows if (r.detail or {}).get("palette")]
    if len(audited) < MIN_AUDITED:
        return {
            "measurable": False,
            "listings": len(rows),
            "audited": len(audited),
            "floor": MIN_AUDITED,
            "reason": (f"{len(audited)} of {len(rows)} listings have had a gallery read "
                       f"against a floor of {MIN_AUDITED}. A palette read from fewer is one "
                       f"photographer's habit, and an empty palette reported as neutral "
                       f"would let a colourway decision rest on nothing"),
        }

    counts: dict[str, int] = {}
    for row in audited:
        seen = set()
        for swatch in (row.detail or {}).get("palette") or []:
            code = str(swatch.get("hex") or "").strip().lstrip("#").upper()
            if len(code) == 6 and code not in seen:
                seen.add(code)
                counts[code] = counts.get(code, 0) + 1

    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_COLOURS]
    swatches = [Swatch(hex=f"#{code}", seen_in_listings=n, value=value_of(code))
                for code, n in ordered]
    dates = sorted(r.last_seen for r in audited if r.last_seen)
    return {
        "measurable": True,
        "pod": pod,
        "seasonal": seasonal,
        "listings": len(rows),
        "audited": len(audited),
        "observed_between": [dates[0].date().isoformat(), dates[-1].date().isoformat()]
        if dates else [],
        "swatches": [s.to_dict() for s in swatches],
        "note": ("Counted from the colours Etsy publishes for each photograph, so this is "
                 "what a proven seller in this department is actually shown in rather than a "
                 "forecast somebody wrote. Dated, because a palette with no observation "
                 "window is a claim about taste and one with a window is a measurement that "
                 "can be seen to have gone stale (#280)."),
    }


def propose_colourway(cir, palette: dict, *, exclude: tuple[str, ...] = ()) -> dict:
    """Pick a colourway for this pattern from an observed palette.

    Same number of colours the pattern already has -- that is the condition, not a
    preference -- and every pair separated enough in lightness to survive a thumbnail and a
    greyscale print.
    """
    if not palette.get("measurable"):
        raise ColourRefused(
            "there is no observed palette to choose from: "
            + palette.get("reason", "nothing has been audited"))

    wanted = len(cir.colors or {})
    if wanted < 1:
        raise ColourRefused("this pattern declares no colours, so it has no colourway")

    available = [s for s in palette["swatches"]
                 if s["hex"].upper() not in {e.upper() for e in exclude}]
    chosen: list[dict] = []
    for swatch in available:
        if all(abs(swatch["value"] - kept["value"]) >= MIN_VALUE_SEPARATION
               for kept in chosen):
            chosen.append(swatch)
        if len(chosen) == wanted:
            break

    if len(chosen) < wanted:
        raise ColourRefused(
            f"this pattern needs {wanted} colours and the observed palette offers "
            f"{len(chosen)} that separate by at least {MIN_VALUE_SEPARATION} in lightness. "
            f"Filling the rest from somewhere else would put colours in a listing that this "
            f"market has not been seen using, which is the opposite of what the evidence is "
            f"for")

    roles = list(cir.colors)
    return {
        "colourway": {role: swatch["hex"] for role, swatch in zip(roles, chosen)},
        "from_palette": {"pod": palette.get("pod"), "seasonal": palette.get("seasonal"),
                         "observed_between": palette.get("observed_between")},
        "separations": [
            {"between": [roles[i], roles[j]],
             "value_gap": round(abs(chosen[i]["value"] - chosen[j]["value"]), 1)}
            for i in range(len(chosen)) for j in range(i + 1, len(chosen))],
        "why": (f"{wanted} colours taken in order of how often this department is "
                f"photographed in them, skipping any that would merge with one already "
                f"chosen"),
    }


def is_variant(cir, colourway: dict) -> dict:
    """Is this a colourway of the same product, or a different product?

    The requirement's own condition: a colour change is a merchandising variant only when the
    underlying pattern truth supports it. Same colour count and the same roles means the
    stitches, the rows and the structure are untouched and only the yarn changed. Anything
    else is a different pattern wearing this one's name, and shipping it as a variant is how
    a catalogue's version accounting stops meaning anything.
    """
    have = set(cir.colors or {})
    offered = set(colourway or {})
    same_roles = have == offered
    reasons = []
    if len(offered) != len(have):
        reasons.append(
            f"the pattern uses {len(have)} colours and this offers {len(offered)}. Changing "
            f"how many colours a pattern uses changes the pattern")
    elif not same_roles:
        reasons.append(
            f"the roles differ: the pattern names {sorted(have)} and this names "
            f"{sorted(offered)}. A colour role is where a colour goes, and moving it is a "
            f"structural change rather than a recolour")
    unreadable = [code for code in offered
                  if len(str(colourway[code]).lstrip('#')) != 6]
    if unreadable:
        reasons.append(f"{unreadable} are not six-digit hex colours, and a colourway stated "
                       f"in words cannot be checked against what a photograph shows")

    return {
        "is_variant": not reasons,
        "same_colour_count": len(offered) == len(have),
        "same_roles": same_roles,
        "why": ("the structure is untouched and only the yarn changed, so this is a "
                "merchandising variant of the same product"
                if not reasons else "; ".join(reasons)),
        "otherwise": ("a new product with its own version, its own tournament and its own "
                      "physical test -- not a variant"),
    }


def forecast(db, *, pod: str = "", benchmark_key: str = "", today: date | None = None) -> dict:
    """The dated palette layer, with the two sources this company does not have named.

    Marketplace evidence is here and free. Fashion and home signals are an external feed
    nobody has granted, and Brambleloop's own colour performance needs sales -- both named
    rather than filled with something plausible, because a forecast resting on one source
    presented as resting on three is the most confident kind of wrong.
    """
    palette = observed_palette(db, pod=pod, benchmark_key=benchmark_key)
    return {
        "as_of": (today or date.today()).isoformat(),
        "marketplace_evidence": palette,
        "fashion_and_home_signals": {
            "measurable": False,
            "reason": ("no external trend feed is connected. A colour forecast invented "
                       "from nothing is indistinguishable from one drawn from a source, and "
                       "only one of those can be wrong in a way anybody notices"),
        },
        "brambleloop_performance": {
            "measurable": False,
            "reason": ("no colourway of ours has sold, so which of our colours performs is "
                       "unknown. Parked on the customers gate"),
        },
        "note": ("One of the three sources the requirement names is available, and the other "
                 "two say so. A forecast resting on one source presented as resting on three "
                 "is the most confident kind of wrong (#280)."),
    }
