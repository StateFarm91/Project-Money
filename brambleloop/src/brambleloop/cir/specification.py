"""What a Brambleloop design must state to be reconstructible, and what it may leave out.

The owner's rule, generalised on 2026-09-24: if a construction fact materially determines the
finished object's geometry, placement, assembly, fit or visible appearance, it belongs in the
authoritative source rather than in a photograph or in the maker's intuition.

The benchmark garment is what made this concrete. It is a competently written, commercially
sold pattern, and it still leaves two things to a picture: where the pockets go, and how long
the neckline band is. A human reads the photograph and works it out. A deterministic
reconstruction cannot, and neither can a customer who is working from the text at two in the
morning -- so the gap is not only ours.

**This does not licence falsifying a benchmark.** A record of someone else's pattern is
allowed to be exactly as incomplete as its source; inventing a placement to make the record
look complete would destroy the thing that makes it a benchmark. The asymmetry is the whole
design: `benchmark` may be incomplete and is reported as such, `brambleloop` may not.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gap:
    """One fact the design does not state, and what cannot be determined without it."""

    fact: str
    where: str
    consequence: str

    def to_dict(self) -> dict:
        return {"fact": self.fact, "where": self.where, "consequence": self.consequence}


class SpecificationIncomplete(ValueError):
    """A Brambleloop design that cannot be reconstructed from what it says."""


def reconstructive_gaps(cir) -> list[Gap]:
    """Facts missing from a design that its finished object's geometry depends on.

    Checked against the object rather than against a checklist of garment parts, so the same
    rule covers a basket's handle placement, a blanket's border attachment and a bag's gusset
    without naming any of them.
    """
    gaps: list[Gap] = []

    for comp in cir.components:
        if getattr(comp, "grain", None) not in ("up", "across"):
            gaps.append(Gap(
                "panel orientation", comp.name,
                "which way the rows run on the finished object is undetermined, so its "
                "proportions and the direction of its texture cannot be reconstructed"))

    for i, seam in enumerate(cir.assembly, start=1):
        if seam.is_self_seam:
            continue
        if not seam.names_its_edges:
            gaps.append(Gap(
                "join target", f"assembly step {i}: {seam.piece_a} to {seam.piece_b}",
                "which edges meet is undetermined, so the pieces cannot be placed relative "
                "to one another and no join length can be checked"))
        if seam.at_round is None and seam.stitches_from_centre is None \
                and not seam.names_its_edges:
            gaps.append(Gap(
                "component placement", f"{seam.piece_a} onto {seam.piece_b}",
                "where on the second piece the join happens is undetermined, so a maker "
                "can follow every row and still not know where it goes"))

    if cir.gauge is None:
        gaps.append(Gap("gauge", "design", "no stitch count converts to a measurement, so "
                                           "nothing about the finished size is determined"))
    elif any(getattr(o, "stitch", None) == "ch" and not getattr(o, "spans", 0)
             for c in cir.components for r in c.rows for o in r.ops) \
            and not cir.gauge.chains_per_10cm:
        gaps.append(Gap(
            "chain gauge", "gauge",
            "the design has chains that add fabric width, and chains are narrower than "
            "worked stitches, so every span they make is measured at the wrong gauge"))

    return gaps


def is_reconstructible(cir) -> dict:
    """Whether this design says enough to rebuild its finished object."""
    gaps = reconstructive_gaps(cir)
    authored = getattr(cir, "authored", "brambleloop")
    return {
        "slug": cir.slug,
        "authored": authored,
        "reconstructible": not gaps,
        "gaps": [g.to_dict() for g in gaps],
        "held_to_the_standard": authored == "brambleloop",
        "why": ("every fact needed to reconstruct the finished object is stated"
                if not gaps else
                f"{len(gaps)} reconstructive fact(s) are missing" +
                ("" if authored == "brambleloop" else
                 ". This is a record of someone else's pattern and is allowed to be as "
                 "incomplete as its source; the gaps are reported rather than invented")),
    }


def refuse_an_underspecified_design(cir) -> None:
    """The gate. A Brambleloop product may not be certified with reconstructive gaps.

    Benchmarks pass through untouched, because holding a record of someone else's work to
    our specification standard would mean either rejecting every real pattern we study or
    fabricating the facts they omit. Both would destroy the benchmark.
    """
    if getattr(cir, "authored", "brambleloop") != "brambleloop":
        return
    gaps = reconstructive_gaps(cir)
    if gaps:
        lines = "; ".join(f"{g.fact} ({g.where})" for g in gaps)
        raise SpecificationIncomplete(
            f"{cir.slug} cannot be reconstructed from what it states: {lines}. A Brambleloop "
            f"design must say everything its finished object's geometry depends on, because "
            f"we control its specification and a photograph is not a specification")
