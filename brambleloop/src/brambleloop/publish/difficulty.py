"""How hard this pattern is to make, decided in one place.

Audited 2026-09-24. The same four lines of difficulty arithmetic existed in three files --
`publish/pdf.py` (what the PDF's cover says), `runtime/release.py` (what the listing claims)
and `gates/asset_truth.py` (the gate that blocks an unsupported difficulty claim) -- each
with its own copy of the literal set `{"tr", "dc_inc", "dc_dec"}`. All three were written
before the texture stitches existed and none of them was updated when post stitches, bobbles
and cable crossings entered the registry in B-080.

The consequence was live on a shipping product. The Heirloom Cable Throw is worked in front
and back post double crochet with a 2-over-2 cable crossing on every fourth row, and its PDF
cover said **beginner** -- because a cable is not `tr`. The listing said beginner for the
same reason, and Asset Truth's `CLAIM_DIFFICULTY_UNSUPPORTED`, whose whole job is to catch
"claims beginner difficulty for something complex", could not see the cable either. A gate,
a document and a listing agreeing with each other is not corroboration when all three are
reading the same stale list.

So the ladder is keyed on the canonical registry and `test_every_registered_stitch_has_a_difficulty`
fails if a stitch is added without a rung. A new stitch can no longer arrive as "beginner" by
being unlisted, which is the way the last three did.
"""
from __future__ import annotations

from ..cir import stitches

# The rungs, in order. Strings rather than an enum because they are printed on the PDF cover
# and claimed on the listing, and those two must be the same words.
BEGINNER = "beginner"
CONFIDENT_BEGINNER = "confident beginner"
INTERMEDIATE = "intermediate"

LADDER: tuple[str, ...] = (BEGINNER, CONFIDENT_BEGINNER, INTERMEDIATE)

# What each stitch asks of the person holding the hook.
#
# 0 -- the first stitches anyone learns.
# 1 -- still ordinary, but a taller stitch or a shaping stitch to count carefully.
# 2 -- a technique a maker meets for the first time in a pattern that uses it: working
#      around a post, closing a bobble, crossing stitches over each other.
STITCH_LEVEL: dict[str, int] = {
    "ch": 0, "slst": 0, "sc": 0, "hdc": 0, "dc": 0, "sk": 0, "inc": 0, "dec": 0,
    "tr": 2, "dc_inc": 2, "dc_dec": 2,
    "fpdc": 2, "bpdc": 2, "bob": 2,
    "cable2x2": 2, "cable1x1": 2,
}

# Kept for the gate that asks "does this pattern contain anything a beginner cannot do".
# Derived from the ladder above rather than restated, so the gate and the cover cannot
# disagree about what counts as advanced.
ADVANCED_STITCHES: frozenset[str] = frozenset(
    code for code, level in STITCH_LEVEL.items() if level >= 2)


def unrated() -> tuple[str, ...]:
    """Registered stitches with no rung. Empty is the only acceptable answer."""
    return tuple(sorted(set(stitches.known_codes()) - set(STITCH_LEVEL)))


def difficulty(cir, twin) -> str:
    """The rung this pattern sits on, from what it contains rather than how it is sold.

    Understating is the expensive direction: a buyer who is told "beginner" and meets a cable
    crossing forty hours in does not come back, and says so in public. Overstating turns away
    the buyer the design was made for, which Asset Truth blocks from the other side.
    """
    used = set(twin.stitch_types_used)
    unknown = used - set(STITCH_LEVEL)
    if unknown:
        # A stitch nobody rated cannot be assumed easy. Refusing outright would stop a
        # release over a rung; claiming beginner would sell it to the wrong person.
        return INTERMEDIATE
    level = max((STITCH_LEVEL[code] for code in used), default=0)

    colors_used = len([c for c in twin.colors_used if c])
    if colors_used > 3:
        level = max(level, 2)
    elif colors_used > 1 or cir.construction != "flat_rows":
        level = max(level, 1)
    return LADDER[level]
