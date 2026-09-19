"""Where the unmet angle is, and why popularity is not an argument for imitation.

Requirements 117, 118, 120. Three machines that all answer one question from different
directions: given that the market is visible, what should this company make that is not
already there?

**Saturation is a reason to leave, not a reason to join (#117).** The instinct runs the other
way and it is nearly irresistible: forty pumpkin coasters on page one is evidence that pumpkin
coasters sell. It is also evidence that the forty-first will be invisible, and the second
reading is the one with the arithmetic behind it. Popularity alone does not justify imitation
— so an archetype above the crowding threshold requires a named unmet angle before anything is
built, and "ours will be nicer" is not an angle.

**White space is mined from complaints, not from gaps in a keyword list (#118).** The useful
signal is a buyer saying what went wrong: too much sewing, sizing that does not go far enough,
a variant nobody makes, a construction that fights the maker, styling that sells nothing. Each
of those is a product brief with a customer attached, and none of them appears in a search
volume report.

**Transfer the mechanism, never the design (#120).** If modular character pockets convert at
Halloween, the Christmas agent may explore *modular character pockets* — not the Halloween
product with a hat on it. The distinction is the whole requirement, and it is the one that
collapses first under a deadline, because the finished design is right there.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Above this many near-interchangeable listings for one archetype, being the next one is a
# distribution problem rather than a product decision.
CROWDED_AT = 25

# How different an angle must be to count as unmet: a different cell of the universe, not a
# different colourway.
ANGLE_KINDS: dict[str, str] = {
    "unserved_context": "the same object for a room or recipient nobody makes it for",
    "construction_fix": "the same object without the thing that makes it annoying to make",
    "sizing_extension": "the range the category stops short of",
    "personalization": "made specific in a way the category does not offer",
    "material_honesty": "stated yardage, gauge and substitutions where the category guesses",
    "giftability": "it arrives ready to give, which the category leaves to the buyer",
    "collection_scale": "it means more beside its siblings, where the category sells singles",
}

# What a complaint is about. #118's own list, closed so that mining produces comparable rows.
COMPLAINT_KINDS: dict[str, str] = {
    "excessive_sewing": "too many pieces to seam",
    "bad_sizing": "the range stops before the buyer does",
    "awkward_construction": "the build fights the maker",
    "missing_variant": "the obvious neighbouring version does not exist",
    "weak_personalization": "no way to make it theirs",
    "poor_styling": "photographed in a way that sells nothing",
    "low_giftability": "nothing about it is ready to give",
    "absent_combination": "two things that belong together are only sold apart",
}

# Mechanisms that can transfer between seasons. Abstract, because a design cannot transfer.
TRANSFERABLE: dict[str, str] = {
    "modular_character_pockets": "repeatable units that each read as a figure",
    "low_sew_construction": "assembled with as few seams as the object allows",
    "quick_make_late_season": "small fast products released inside the closing window",
    "collection_attach": "siblings bought together more often than alone",
    "personalization_slot": "a designed place for a name, date or initial",
    "dimensional_relief": "surface texture a photograph can sell",
    "nesting_storage": "the object stores itself",
}


class DiscoveryRefused(ValueError):
    """Imitation with no angle, or a design transferred as though it were a mechanism."""


@dataclass
class Archetype:
    key: str
    listings: int
    median_price_cad: float = 0.0
    note: str = ""

    @property
    def crowded(self) -> bool:
        return self.listings >= CROWDED_AT


def saturation(archetypes: list[Archetype]) -> dict:
    """Which archetypes are full, and which territory is still open (#117)."""
    crowded = [a for a in archetypes if a.crowded]
    open_ground = [a for a in archetypes if not a.crowded]
    return {
        "crowded": [{"archetype": a.key, "listings": a.listings} for a in crowded],
        "open": [{"archetype": a.key, "listings": a.listings} for a in open_ground],
        "threshold": CROWDED_AT,
        "note": ("Forty near-interchangeable listings is evidence the archetype sells and "
                 "evidence the forty-first is invisible. Only the second reading has "
                 "arithmetic behind it: popularity alone does not justify imitation (#117)."),
    }


def may_enter(archetype: Archetype, *, angle_kind: str | None = None,
              angle: str = "") -> dict:
    """May this company build into this archetype? (#117)

    A crowded archetype needs a named unmet angle first. "Ours will be nicer" is refused —
    not because it is never true, but because it is what everybody entering a crowded
    category believes, including the forty who are already there.
    """
    if not archetype.crowded:
        return {"may_enter": True, "archetype": archetype.key,
                "why": (f"{archetype.listings} listings is below the crowding threshold of "
                        f"{CROWDED_AT}; this is open ground")}

    if angle_kind is None:
        raise DiscoveryRefused(
            f"{archetype.key!r} has {archetype.listings} near-interchangeable listings. "
            f"Entering needs a named unmet angle: {sorted(ANGLE_KINDS)}. 'Ours will be "
            f"nicer' is what everybody entering a crowded category believes, including the "
            f"{archetype.listings} already there (#117)")
    if angle_kind not in ANGLE_KINDS:
        raise DiscoveryRefused(
            f"{angle_kind!r} is not an unmet angle: {sorted(ANGLE_KINDS)}")
    if len(angle.split()) < 6:
        raise DiscoveryRefused(
            "say what specifically is unmet and for whom; a category name is not an angle")
    return {
        "may_enter": True,
        "archetype": archetype.key,
        "angle_kind": angle_kind,
        "angle_meaning": ANGLE_KINDS[angle_kind],
        "angle": angle.strip(),
        "why": (f"crowded at {archetype.listings} listings, entered on a named unmet angle "
                f"rather than on the crowding itself"),
    }


# ---------------------------------------------------------------------------
# White space (#118)


@dataclass(frozen=True)
class Complaint:
    kind: str
    source: str
    statement: str

    def __post_init__(self) -> None:
        if self.kind not in COMPLAINT_KINDS:
            raise DiscoveryRefused(
                f"{self.kind!r} is not a complaint kind: {sorted(COMPLAINT_KINDS)}")
        if not self.source.strip():
            raise DiscoveryRefused(
                "a complaint with no source is a hypothesis somebody had in the shower")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "meaning": COMPLAINT_KINDS[self.kind],
                "source": self.source, "statement": self.statement}


@dataclass
class Hypothesis:
    complaint_kind: str
    proposal: str
    evidence: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"complaint_kind": self.complaint_kind,
                "meaning": COMPLAINT_KINDS[self.complaint_kind],
                "proposal": self.proposal,
                "evidence": list(self.evidence),
                "support": len(self.evidence)}


def white_space(complaints: list[Complaint]) -> dict:
    """Turn what buyers said went wrong into briefs (#118).

    Each complaint kind is a product brief with a customer attached, which is what a search
    volume report cannot be. With none recorded the agent says it has nothing to mine rather
    than proposing from the category, because proposing from the category is how a white-space
    agent rediscovers the commodity.
    """
    if not complaints:
        return {"minable": False,
                "reason": ("no complaint has been recorded, so there is nothing to mine. "
                           "Proposing from the category instead is how a white-space agent "
                           "rediscovers the commodity"),
                "hypotheses": [], "complaint_kinds": COMPLAINT_KINDS}

    grouped: dict[str, list[Complaint]] = {}
    for c in complaints:
        grouped.setdefault(c.kind, []).append(c)

    hypotheses = []
    for kind, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        hypotheses.append(Hypothesis(
            complaint_kind=kind,
            proposal=(f"a product where {COMPLAINT_KINDS[kind]} is designed out rather than "
                      f"tolerated"),
            evidence=[c.to_dict() for c in items]).to_dict())
    return {
        "minable": True,
        "complaints": len(complaints),
        "hypotheses": hypotheses,
        "strongest": hypotheses[0]["complaint_kind"],
        "note": ("Ranked by how many buyers said the same thing. A complaint repeated is a "
                 "brief with a customer attached, which no search volume report is (#118)."),
    }


# ---------------------------------------------------------------------------
# Learning transfer (#120)


def transfer(mechanism: str, *, from_season: str, to_season: str,
             original_theme: str) -> dict:
    """Carry a mechanism between seasons, never a design (#120).

    The distinction is the whole requirement and it is the one that collapses first under a
    deadline, because the finished design is right there and the mechanism needs inventing
    again.
    """
    if mechanism not in TRANSFERABLE:
        raise DiscoveryRefused(
            f"{mechanism!r} is not a transferable mechanism: {sorted(TRANSFERABLE)}. A "
            f"design cannot transfer -- only the relationship that made it work can (#120)")
    if from_season == to_season:
        raise DiscoveryRefused("transferring a mechanism to its own season is reuse, not "
                               "transfer")
    if len(original_theme.split()) < 4:
        raise DiscoveryRefused(
            f"the {to_season} version needs its own theme. Carrying the {from_season} theme "
            f"across is the design travelling with the mechanism, which is the thing #120 "
            f"forbids")
    return {
        "mechanism": mechanism,
        "meaning": TRANSFERABLE[mechanism],
        "from_season": from_season,
        "to_season": to_season,
        "original_theme": original_theme.strip(),
        "note": ("The mechanism transfers and the theme is new. If modular character pockets "
                 "convert at Halloween, Christmas explores modular character pockets -- not "
                 "the Halloween product with a hat on it (#120)."),
    }
