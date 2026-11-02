"""The small-parts cylinder, read with a stated tolerance (A1-R).

16 CFR 1501.4 and Canada SOR/2011-17 s.7: a separable part that fits entirely inside a
cylinder 31.7 mm across, with a slanted floor 25.4 to 57.1 mm deep, is a small part. A
pattern's pieces are known only from the stitch counts and a nominal gauge, and a maker
working tighter than the gauge makes them smaller. So a piece is:

    FITS     -- inside the cylinder by geometry: a small part;
    UNKNOWN  -- within SMALL_PARTS_TOLERANCE_MM of either bound: geometry cannot say, and only
                a measured physical sample can (never read as a pass);
    CLEAR    -- larger than both bounds by more than the tolerance.

UNKNOWN and FITS both block a children's assignment until physical evidence is recorded
(`SMALL_PARTS_EVIDENCE`). This is geometry, not the 4.45 N use-and-abuse test.
"""
from __future__ import annotations

import math

CYLINDER_MM = 31.7
DEPTH_MM = 57.1
SMALL_PARTS_TOLERANCE_MM = 4.0      # about one stitch at DK-to-worsted gauge, either way
FITS, UNKNOWN, CLEAR = "fits", "unknown", "clear"

# slug -> the recorded physical evidence (a passed small-parts test of a made sample). Empty:
# no physical small-parts evidence exists for any product today.
SMALL_PARTS_EVIDENCE: dict[str, str] = {}


def verdict(narrow_mm: float, long_mm: float, *, tolerance: float = SMALL_PARTS_TOLERANCE_MM
            ) -> str:
    if narrow_mm <= CYLINDER_MM and long_mm <= DEPTH_MM:
        return FITS
    if narrow_mm <= CYLINDER_MM + tolerance and long_mm <= DEPTH_MM + tolerance:
        return UNKNOWN
    return CLEAR


def separable_pieces(cir) -> list[tuple[str, float, float]]:
    """(piece, narrow mm, long mm) for every component sewn onto another, flat, from its own
    stitch counts and the CIR's gauge. A piece worked out from a magic ring is a disc (or a
    cup flattened to one): its diameter both ways. A tube in rounds flattens to half its
    circumference by its height; a flat piece is its width by its height."""
    gauge = getattr(cir, "gauge", None)
    if gauge is None:
        return []
    st_mm = 100.0 / gauge.stitches_per_10cm
    row_mm = 100.0 / gauge.rows_per_10cm
    sewn_on = {s.piece_a for s in (cir.assembly or []) if s.piece_a != s.piece_b}
    out = []
    for comp in cir.components:
        if comp.name not in sewn_on or not comp.rows:
            continue
        widest = max(r.declared_count for r in comp.rows)
        height = len(comp.rows) * row_mm
        if comp.construction == "joined_rounds" and \
                getattr(comp, "foundation_kind", None) == "magic_ring":
            diameter = widest * st_mm / math.pi
            out.append((comp.name, diameter, diameter))
            continue
        rounds = comp.construction == "joined_rounds"
        width = widest * st_mm / (2.0 if rounds else 1.0)
        out.append((comp.name, min(width, height), max(width, height)))
    return out


def blocking(cir) -> list[str]:
    """Every sewn-on piece that fits or may fit the cylinder, unless physical evidence is on
    record for this product."""
    if SMALL_PARTS_EVIDENCE.get(getattr(cir, "slug", "")):
        return []
    return [f"{name} (about {n:.0f} x {l:.0f} mm flat: {verdict(n, l)})"
            for name, n, l in separable_pieces(cir) if verdict(n, l) != CLEAR]
