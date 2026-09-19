"""Size grading: one design, a run of sizes, and a refusal where the arithmetic will not close.

The primitive Build 2's creativity needs most. Every garment concept in the v1.4.3 spec — the
cropped cardigan it uses as its worked example, most of the garments pod — is a design that
must exist in a run of sizes, and a run of sizes is where hand-written patterns most often go
wrong: the medium is checked, the extra-large is arithmetic nobody re-did.

Three rules, each against a specific way graded patterns fail.

**A size that cannot be produced is refused, never rounded.** If a motif repeats every twelve
stitches and a size needs 146, the honest answers are 144 or 156. Rounding to 146 produces a
garment with half a motif at one edge — which compiles, passes every count check, and is a
visible defect on the finished object. This is the same rule the motif builder already
enforces for width, applied to a whole size run.

**Ease is a design decision, applied per size rather than scaled with it.** A 5 cm ease on a
small is generous and on a 3XL is negligible, so ease is declared per size and checked for
monotonicity rather than multiplied.

**Grading is monotonic or it is a mistake.** Every graded dimension must increase with size.
The check exists because the failure is so easy: one transposed number in a size table, and a
2XL has narrower shoulders than an XL. It compiles, and a customer discovers it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# A standard run. Sizes are names rather than numbers because "2XL" is what a buyer chooses
# and the bust measurement is what the pattern needs; keeping both prevents the confusion
# where a size table and a pattern disagree about what "large" means.
DEFAULT_RUN: tuple[str, ...] = ("XS", "S", "M", "L", "XL", "2XL", "3XL")


class GradingRefused(ValueError):
    """A size run whose arithmetic does not close, or which is not monotonic."""


@dataclass(frozen=True)
class SizeSpec:
    """One size: what body it fits, how much room it leaves, and what that costs in stitches."""

    name: str
    bust_cm: float
    ease_cm: float
    length_cm: float

    @property
    def finished_bust_cm(self) -> float:
        return round(self.bust_cm + self.ease_cm, 1)

    def to_dict(self) -> dict:
        return {"size": self.name, "bust_cm": self.bust_cm, "ease_cm": self.ease_cm,
                "finished_bust_cm": self.finished_bust_cm, "length_cm": self.length_cm}


@dataclass(frozen=True)
class GradedSize:
    """A size resolved into stitch and row counts the compiler can work with."""

    spec: SizeSpec
    stitches: int
    rows: int
    motif_repeats: int

    def to_dict(self) -> dict:
        return {**self.spec.to_dict(), "stitches": self.stitches, "rows": self.rows,
                "motif_repeats": self.motif_repeats}


def check_monotonic(sizes: list[SizeSpec]) -> None:
    """Every graded dimension rises with size, or somebody transposed a number.

    The failure this catches compiles perfectly: a 2XL with narrower shoulders than an XL
    passes every stitch-count check in the system and is discovered by a customer.
    """
    for field_name in ("bust_cm", "length_cm"):
        values = [getattr(s, field_name) for s in sizes]
        for i in range(1, len(values)):
            if values[i] <= values[i - 1]:
                raise GradingRefused(
                    f"{field_name} does not increase from {sizes[i - 1].name} "
                    f"({values[i - 1]}) to {sizes[i].name} ({values[i]}). A size run that "
                    f"goes backwards compiles perfectly and is found by a customer")

    eases = [s.ease_cm for s in sizes]
    if min(eases) < 0:
        raise GradingRefused("negative ease means the garment is smaller than the body")


def grade(sizes: list[SizeSpec], *, stitches_per_10cm: float, rows_per_10cm: float,
          motif_width: int = 1, allow_partial_motif: bool = False) -> list[GradedSize]:
    """Resolve a size run into stitch counts, refusing any size the motif cannot tile.

    `allow_partial_motif` exists for designs with no repeating motif — plain stocking stitch,
    a solid panel — where any stitch count is legitimate. It defaults off, because a design
    *with* a motif that silently allows a partial one is the defect this function exists to
    prevent.
    """
    if not sizes:
        raise GradingRefused("a size run with no sizes is not a size run")
    if stitches_per_10cm <= 0 or rows_per_10cm <= 0:
        raise GradingRefused("gauge must be positive in both directions")
    if motif_width < 1:
        raise GradingRefused("a motif cannot be narrower than one stitch")

    check_monotonic(sizes)

    graded: list[GradedSize] = []
    problems: list[str] = []
    for spec in sizes:
        raw = spec.finished_bust_cm / 10.0 * stitches_per_10cm
        rows = max(1, round(spec.length_cm / 10.0 * rows_per_10cm))

        if motif_width == 1 or allow_partial_motif:
            stitches = max(1, round(raw))
            repeats = stitches // motif_width if motif_width else 0
        else:
            repeats = round(raw / motif_width)
            if repeats < 1:
                problems.append(
                    f"{spec.name}: {spec.finished_bust_cm}cm is narrower than one "
                    f"{motif_width}-stitch motif repeat")
                continue
            stitches = repeats * motif_width
            drift_cm = abs(stitches - raw) / stitches_per_10cm * 10.0
            # A size forced more than 2 cm from its target to fit the motif is not that size.
            if drift_cm > 2.0:
                problems.append(
                    f"{spec.name}: the nearest whole motif count gives "
                    f"{stitches} stitches, {drift_cm:.1f}cm from the target "
                    f"{spec.finished_bust_cm}cm. Rounding here produces a garment that is "
                    f"not the size it claims")
                continue

        graded.append(GradedSize(spec=spec, stitches=stitches, rows=rows,
                                 motif_repeats=repeats))

    if problems:
        raise GradingRefused(
            "the size run does not close: " + "; ".join(problems)
            + ". The honest fixes are a narrower motif, a different gauge or fewer sizes — "
              "never a rounded stitch count, which produces half a motif at one edge and "
              "compiles perfectly")
    return graded


def grade_component(component, graded: GradedSize, *, motif_width: int = 1):
    """Rebuild one component at a graded size.

    Only the foundation and declared counts move; the row *structure* is the design and is
    not regenerated per size, because a design whose construction changes between sizes is
    several designs sharing a name.
    """
    from .model import Row

    rows = []
    for row in component.rows:
        rows.append(replace(row, declared_count=graded.stitches)
                    if row.declared_count else row)
    return replace(component, foundation=graded.stitches, rows=rows)


def size_table(graded: list[GradedSize]) -> dict:
    """The table a customer reads before buying, and a maker reads before starting."""
    return {
        "sizes": [g.to_dict() for g in graded],
        "gauge_note": ("Stitch counts follow the gauge. A maker whose gauge differs will "
                       "produce a different finished size, which is why the gauge swatch is "
                       "not optional."),
        "motif_note": ("Every size is a whole number of motif repeats. No size was rounded "
                       "to fit, because a rounded count produces half a motif at one edge."),
    }
