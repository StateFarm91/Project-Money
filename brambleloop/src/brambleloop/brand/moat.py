"""What a competitor would have to copy, and how long each one would take them.

Requirement 44. The recurring fictional model is one brand asset and it is the most copyable
one in the list — a competitor with an image generator has an equivalent by Friday. Treating
it as the brand is the mistake this requirement names, and it is an easy mistake because the
model is the most *visible* asset, which feels like the same thing as the most valuable.

So the moat is an inventory, and every entry carries the only number that matters: how long a
determined competitor would need to reproduce it. That reframes the whole list. A photography
style is weeks. A naming architecture is an afternoon. A support experience answered from the
exact pattern version somebody bought requires building the version map first, and the version
map cannot be backfilled — so it is years, or never, depending on when they start.

Two rules keep the inventory honest.

**An asset nobody has built is not a moat.** A planned signature is a plan, and listing it
alongside real ones produces a page that says the company is defensible when it is aspiring.
Every entry states whether it exists today.

**Replication time is measured in what it would cost *them*, not what it cost us.** Those
differ wildly and only one of them is a moat: an expensive thing that is easy to copy is a
sunk cost, and a cheap thing that is hard to copy is the whole game.
"""
from __future__ import annotations

from dataclasses import dataclass

# Roughly how long a determined competitor needs. The bands are coarse on purpose: the
# difference between four and six weeks is noise, and the difference between weeks and never
# is the entire strategy.
DAYS = "days"
WEEKS = "weeks"
MONTHS = "months"
STRUCTURAL = "structural"     # needs a decision made early, or data accumulated since then

REPLICATION: tuple[str, ...] = (DAYS, WEEKS, MONTHS, STRUCTURAL)

REPLICATION_MEANING: dict[str, str] = {
    DAYS: "a competent competitor has an equivalent this week",
    WEEKS: "requires sustained effort and a person who cares",
    MONTHS: "requires a programme, and they would have to decide to start",
    STRUCTURAL: ("cannot be bought later at any speed: it needed a decision taken early or "
                 "data accumulated since then"),
}


class MoatRefused(ValueError):
    """An asset counted as a moat that does not exist, or has no replication estimate."""


@dataclass(frozen=True)
class Signature:
    key: str
    what: str
    replication: str
    why: str
    exists: bool

    def __post_init__(self) -> None:
        if self.replication not in REPLICATION:
            raise MoatRefused(
                f"{self.key}: {self.replication!r} is not a replication band: {REPLICATION}")
        if len(self.why.split()) < 6:
            raise MoatRefused(
                f"{self.key}: say why it would take that long for somebody else. Without "
                f"that the band is a feeling about how proud we are of it")

    def to_dict(self) -> dict:
        return {"key": self.key, "what": self.what, "exists": self.exists,
                "replication": self.replication,
                "replication_meaning": REPLICATION_MEANING[self.replication],
                "why": self.why}


SIGNATURES: tuple[Signature, ...] = (
    Signature("canonical_model", "a recurring fictional model across the gallery", DAYS,
              "any competitor with an image generator has an equivalent by Friday, which is "
              "why this is one asset and not the brand", exists=False),
    Signature("naming_architecture", "how products and collections are named", DAYS,
              "a naming scheme is an afternoon's work to imitate once it is visible",
              exists=True),
    Signature("editorial_layout", "the document's typography, hierarchy and rhythm", WEEKS,
              "copying a layout is easy and copying the judgement that produced it is not, "
              "so an imitation reads as an imitation", exists=True),
    Signature("photography_language", "how finished objects are lit, styled and cropped",
              WEEKS,
              "a style is learnable from the gallery, and doing it consistently across a "
              "growing catalogue is the part that takes a person who cares", exists=False),
    Signature("chart_style", "colour-independent charts with a per-yarn letter in every cell",
              MONTHS,
              "the style is visible and reproducing it means rebuilding chart generation "
              "around accessibility rather than adding it afterwards", exists=True),
    Signature("tutorial_voice", "how a difficult step is explained", MONTHS,
              "a voice is the accumulation of decisions about what to leave out, and a "
              "competitor starts from zero on every one of them", exists=False),
    Signature("collection_families", "products that mean more beside their siblings", MONTHS,
              "requires a catalogue designed as families rather than a catalogue with "
              "families found in it afterwards", exists=False),
    Signature("deterministic_validation",
              "every count, repeat and dimension machine-checked and reverse-compiled",
              STRUCTURAL,
              "a competitor would have to rebuild their pattern production around a formal "
              "representation, which is a different company rather than a feature",
              exists=True),
    Signature("version_aware_support",
              "answers given from the exact pattern version the customer bought", STRUCTURAL,
              "needs an order-to-version map written at sale time, and it cannot be "
              "backfilled: whoever did not record it has lost those orders permanently",
              exists=True),
    Signature("measured_yardage",
              "yardage computed from the twin and calibrated against physical samples",
              STRUCTURAL,
              "the calibration is accumulated evidence, so a competitor starting today is "
              "as many samples behind as we have taken", exists=False),
)

BY_KEY: dict[str, Signature] = {s.key: s for s in SIGNATURES}


def inventory() -> dict:
    """The moat as it actually stands, separating what exists from what is planned.

    An asset nobody has built is not a moat, and listing it beside the real ones produces a
    page saying the company is defensible when it is aspiring.
    """
    built = [s for s in SIGNATURES if s.exists]
    planned = [s for s in SIGNATURES if not s.exists]

    by_band: dict[str, list[str]] = {}
    for s in built:
        by_band.setdefault(s.replication, []).append(s.key)

    structural = [s.key for s in built if s.replication == STRUCTURAL]
    return {
        "signatures": [s.to_dict() for s in SIGNATURES],
        "built": [s.key for s in built],
        "planned": [s.key for s in planned],
        "built_by_replication": {band: by_band.get(band, []) for band in REPLICATION},
        "structural_advantages": structural,
        "model_is_one_asset_of": len(SIGNATURES),
        "note": (f"{len(structural)} structural advantage(s) exist today and the canonical "
                 f"model is not among them -- it is the most visible asset, which feels like "
                 f"the most valuable and is the most copyable (#44)."),
    }


def without(key: str) -> dict:
    """What the brand still has if one signature is lost or copied.

    Asked of the model specifically, because the requirement's whole point is that the answer
    should not be "not much".
    """
    if key not in BY_KEY:
        raise MoatRefused(f"{key!r} is not a brand signature: {sorted(BY_KEY)}")
    remaining = [s for s in SIGNATURES if s.key != key and s.exists]
    structural = [s.key for s in remaining if s.replication == STRUCTURAL]
    return {
        "lost": key,
        "remaining_built": [s.key for s in remaining],
        "remaining_structural": structural,
        "brand_survives": bool(structural),
        "note": (f"losing {key} leaves {len(structural)} structural advantage(s) intact"
                 if structural else
                 f"losing {key} leaves nothing a competitor could not reproduce in weeks"),
    }
