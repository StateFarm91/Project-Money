"""ENG-LOWSEW-CHENILLE: eye options as a construction feature.

The benchmark toys offer hard safety eyes, sometimes with an embroidered alternative and never
with age guidance. Ours always carry an embroidered-eye variant, placed by structure
(`Component.eye_round` / `eye_gap_sts`, validated by `cir.joins.check_eyes`, read back by the
reverse compiler), and print an "Eye options" block inside the child-safety section, using
that gate's age reading (`child_safety._age_band`: an unassigned toy reads as for a child
under 3, the conservative reading).

The owner's rule for child and baby items is embroidered features only (D-OWNER-CORE-FAMILIES
s.3), and every stuffed toy is inside the child-safety gate whatever it is called, so the
embroidered variant is the only one Brambleloop certifies. The block says so, and for a baby
or a child under 3 says plainly that no other eye may be used. The block lives inside the
child-safety section, where naming a hard part in order to rule it out is allowed
(`child_safety._text_checks` reads the instructions outside it).
"""
from __future__ import annotations

from dataclasses import dataclass

HEADING = "Eye options"
EMBROIDERED = "embroidered"
HARD_EYES = "hard_eyes"


@dataclass(frozen=True)
class EyeOption:
    key: str
    available: bool
    default: bool
    text: str


def _placement(cir) -> tuple[str, int, int] | None:
    for comp in cir.components:
        if comp.eye_round is not None and comp.eye_gap_sts is not None:
            return comp.name, comp.eye_round, comp.eye_gap_sts
    return None


def options(cir, childrens: tuple[str, str] | None = None) -> list[EyeOption]:
    from ..intel import childrens as _ch
    from . import child_safety as _cs

    band = _cs._age_band(cir, childrens)
    young = band == _ch.UNDER_3 or bool(childrens and childrens[0] in _cs.SLEEP_SUBCATEGORIES)
    where = _placement(cir)
    if where:
        piece, rnd, gap = where
        place = (f"on Rnd {rnd} of the {piece.replace('_', ' ')}, {gap} sts apart, centred on "
                 f"the front")
    else:
        place = "where the pattern's face instructions place them"
    embroidered = EyeOption(
        EMBROIDERED, available=True, default=True,
        text=(f"Embroidered eyes (this pattern's default, always available): {place}. Use a "
              f"smooth worsted-weight yarn so the eye shows on the chenille pile: bring it up "
              f"from inside the piece, work 4 or 5 straight stitches over one stitch, and take "
              f"every knot back inside. Embroider after stuffing so the eyes sit flat."))
    if young:
        hard = EyeOption(
            HARD_EYES, available=False, default=False,
            text=("For a baby or a child under 3, embroidered eyes are the only option. Do not "
                  "use safety eyes, buttons or beads: a hard eye that is pulled off is a "
                  "choking hazard."))
    else:
        hard = EyeOption(
            HARD_EYES, available=False, default=False,
            text=("This pattern offers embroidered eyes only. A toy is a child's item, and "
                  "Brambleloop's rule for child and baby items is embroidered features with no "
                  "hard parts, whoever it is made for."))
    return [embroidered, hard]


def block_lines(cir, childrens: tuple[str, str] | None = None) -> list[tuple[str, str]]:
    """(heading, text) pairs for the PDF, printed inside the child-safety section."""
    out = [(HEADING, "")]
    out += [("", o.text) for o in options(cir, childrens)]
    return out


def applies(cir) -> bool:
    """A design with a structural eye placement carries the block."""
    return _placement(cir) is not None
