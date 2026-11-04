"""The small-parts cylinder, read with a stated tolerance (A1-R).

16 CFR 1501.4 and Canada SOR/2011-17 s.7: a separable part that fits entirely inside a
cylinder 31.7 mm across, with a slanted floor 25.4 to 57.1 mm deep, is a small part. A
pattern's pieces are known only from the stitch counts and a nominal gauge, and a maker
working tighter than the gauge makes them smaller. So a piece is:

    FITS     -- inside the cylinder by geometry: a small part;
    UNKNOWN  -- within SMALL_PARTS_TOLERANCE_MM of either bound: geometry cannot say, and only
                a measured physical sample can (never read as a pass);
    CLEAR    -- flat geometric estimate exceeds a bound by more than the tolerance.

The geometric CLEAR result is not a physical clearance: crocheted fabric may fold or
compress. Every separately sewn crochet piece remains blocked until physical fit under
force is assessed through an approved content-bound authority. No such authority is
implemented, so no registry value can clear a hold. This is not the 4.45 N test.
"""
from __future__ import annotations

import math

CYLINDER_MM = 31.7
DEPTH_MM = 57.1
SMALL_PARTS_TOLERANCE_MM = 4.0      # about one stitch at DK-to-worsted gauge, either way
FITS, UNKNOWN, CLEAR = "fits", "unknown", "clear"

# Legacy, unscoped registry retained for compatibility. Values are never authority:
# no accepted model binds physical evidence to the exact release and owner approval yet.
SMALL_PARTS_EVIDENCE: dict[str, str] = {}


def verdict(narrow_mm: float, long_mm: float, *, tolerance: float = SMALL_PARTS_TOLERANCE_MM
            ) -> str:
    """Classify the flat geometric estimate, not physical fit under force."""
    # NaN compares false against every threshold; treating it as clear would let
    # unknown geometry pass a child-safety gate. Infinity, zero, and negatives
    # likewise cannot describe a measured piece.
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or v <= 0 for v in (narrow_mm, long_mm)):
        return UNKNOWN
    if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance) or tolerance < 0):
        return UNKNOWN
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
    if gauge is None or any(
            isinstance(v, bool) or not isinstance(v, (int, float))
            or not math.isfinite(v) or v <= 0
            for v in (getattr(gauge, "stitches_per_10cm", None),
                      getattr(gauge, "rows_per_10cm", None))):
        return []          # blocking() reads every sewn-on piece missing here as UNKNOWN
    st_mm = 100.0 / gauge.stitches_per_10cm
    row_mm = 100.0 / gauge.rows_per_10cm
    # Seam orientation is arbitrary: either endpoint can be a detachable small part.
    sewn_on = set(_sewn_on(cir))
    out = []
    for comp in cir.components:
        if comp.name not in sewn_on or not comp.rows:
            continue
        widest = max(r.declared_count for r in comp.rows)
        height = len(comp.rows) * row_mm
        if comp.construction in ("joined_rounds", "spiral_rounds") and \
                getattr(comp, "foundation_kind", None) == "magic_ring":
            diameter = widest * st_mm / math.pi
            out.append((comp.name, diameter, diameter))
            continue
        rounds = comp.construction in ("joined_rounds", "spiral_rounds")
        width = widest * st_mm / (2.0 if rounds else 1.0)
        out.append((comp.name, min(width, height), max(width, height)))
    return out


def _sewn_on(cir) -> list[str]:
    return sorted({piece for s in (getattr(cir, "assembly", None) or [])
                   if s.piece_a != s.piece_b for piece in (s.piece_a, s.piece_b)})


def blocking(cir) -> list[str]:
    """Every sewn-on crochet piece remains blocked without physical fit authority.

    Unscoped slug-only registry values do not establish a physical test of this exact
    release. Unknown measurements also block. A separately approved, content-bound
    evidence authority is required before physical evidence can clear this hold.
    """
    try:
        pieces = separable_pieces(cir)
    except Exception as exc:  # noqa: BLE001 - unmeasurable is UNKNOWN
        return [f"sewn-on pieces unmeasurable ({type(exc).__name__}): {UNKNOWN}"]
    measured = {name for name, _n, _l in pieces}
    fits, uncertain = [], []
    for name, n, length in pieces:
        geometric = verdict(n, length)
        if geometric == CLEAR:
            uncertain.append(f"{name} (about {n:.0f} x {length:.0f} mm flat; geometric estimate "
                             f"exceeds a bound but folding/fit under force is {UNKNOWN})")
        elif geometric == FITS:
            fits.append(f"{name} (about {n:.0f} x {length:.0f} mm flat: {geometric})")
        else:
            uncertain.append(f"{name} (about {n:.0f} x {length:.0f} mm flat: {geometric})")
    out = fits + uncertain  # An identified fitting part precedes uncertain parts.
    out += [f"{name} (size not measurable from the pattern: {UNKNOWN})"
            for name in _sewn_on(cir) if name not in measured]
    return out
