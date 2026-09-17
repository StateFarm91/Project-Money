"""Digital Twin: execute canonical operations and render a structural model.

Master Plan section 3. The twin is what lets downstream gates answer questions about the
*actual* object rather than about marketing copy:

  - Asset Truth asks "does this listing image show a motif the pattern does not contain?"
  - Policy asks "is this 'fits a queen bed' claim supported by the gauge?"
  - Materials asks "how much yarn of each colour does this consume?"

Yardage is an explicit estimate with a stated tolerance, not false precision. Physical test
results feed `calibration` so the estimate improves with evidence (section 3: "Tester results
become calibration data for future patterns").
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import stitches
from .compiler import CompileResult, ResolvedRow
from .model import CIR

# Yarn length consumed per stitch, expressed as a multiple of one gauge stitch-width.
# Derived from the stitch's height: a dc eats far more yarn than a sc. These are starting
# constants with a wide tolerance; physical tests replace them per yarn/hook combination.
_YARN_FACTOR = {
    "ch": 1.0, "slst": 1.2, "sc": 2.9, "hdc": 3.8, "dc": 4.9, "tr": 6.1,
    "inc": 5.8, "dec": 4.4, "dc_inc": 9.8, "dc_dec": 8.2, "sk": 0.0,
}
YARDAGE_TOLERANCE = 0.20  # +/- 20% until calibrated by a physical test


@dataclass
class Cell:
    """One worked stitch in the fabric."""

    row: int
    position: int
    stitch: str
    color: str | None
    repeat_group: int | None = None


@dataclass
class TwinModel:
    component: str
    cells: list[Cell] = field(default_factory=list)
    row_widths: dict[int, int] = field(default_factory=dict)
    width_cm: float | None = None
    height_cm: float | None = None
    yarn_metres_by_color: dict[str, float] = field(default_factory=dict)
    yardage_tolerance: float = YARDAGE_TOLERANCE
    calibrated: bool = False

    @property
    def stitch_total(self) -> int:
        return len(self.cells)

    @property
    def colors_used(self) -> set[str]:
        return {c.color for c in self.cells if c.color}

    @property
    def stitch_types_used(self) -> set[str]:
        return {c.stitch for c in self.cells}

    def chart_grid(self) -> list[list[str]]:
        """Row-major grid of stitch codes, bottom row first. Feeds chart rendering."""
        rows = sorted({c.row for c in self.cells})
        grid: list[list[str]] = []
        for r in rows:
            cells = sorted((c for c in self.cells if c.row == r), key=lambda c: c.position)
            grid.append([c.stitch for c in cells])
        return grid

    def color_grid(self) -> list[list[str | None]]:
        rows = sorted({c.row for c in self.cells})
        out: list[list[str | None]] = []
        for r in rows:
            cells = sorted((c for c in self.cells if c.row == r), key=lambda c: c.position)
            out.append([c.color for c in cells])
        return out


def _dimensions(rows: list[ResolvedRow], cir: CIR) -> tuple[float | None, float | None]:
    if not cir.gauge or not rows:
        return None, None
    g = cir.gauge
    widest = max(r.stitch_count for r in rows)
    width_cm = widest / g.stitches_per_10cm * 10.0

    # Row height scales with stitch height relative to the gauge stitch.
    base = stitches.get(g.stitch_type).height or 1.0
    row_cm = 10.0 / g.rows_per_10cm
    height_cm = 0.0
    for r in rows:
        tallest = max((stitches.get(o.stitch).height for o in r.ops), default=base)
        height_cm += row_cm * (tallest / base)
    return round(width_cm, 1), round(height_cm, 1)


def _yardage(rows: list[ResolvedRow], cir: CIR, calibration: float) -> dict[str, float]:
    if not cir.gauge:
        return {}
    stitch_width_cm = 10.0 / cir.gauge.stitches_per_10cm
    totals: dict[str, float] = {}
    for r in rows:
        color = r.color or "main"
        cm = 0.0
        for op in r.ops:
            factor = _YARN_FACTOR.get(op.stitch, 3.0)
            cm += factor * stitch_width_cm * op.produces
        if r.turning_chain:
            cm += _YARN_FACTOR["ch"] * stitch_width_cm * r.turning_chain
        totals[color] = totals.get(color, 0.0) + cm
    return {k: round(v / 100.0 * calibration, 1) for k, v in totals.items()}


def build_twin(
    cir: CIR, result: CompileResult, component: str | None = None, calibration: float = 1.0
) -> TwinModel:
    """Execute a compiled component and return its structural model.

    Only compiles clean patterns: a twin built from failing arithmetic would be fiction.
    """
    if not result.ok:
        raise ValueError(
            "refusing to build a digital twin from a pattern that failed compilation: "
            + "; ".join(str(f) for f in result.errors)
        )

    name = component or cir.components[0].name
    rows = [r for r in result.rows if r.component == name]
    if not rows:
        raise KeyError(f"no compiled rows for component {name!r}")

    model = TwinModel(component=name, calibrated=calibration != 1.0)
    for r in rows:
        pos = 0
        for op in r.ops:
            st = stitches.get(op.stitch)
            for _ in range(op.count):
                for _ in range(st.produces):
                    model.cells.append(
                        Cell(row=r.index, position=pos, stitch=op.stitch,
                             color=r.color, repeat_group=op.repeat_group)
                    )
                    pos += 1
        model.row_widths[r.index] = pos

    model.width_cm, model.height_cm = _dimensions(rows, cir)
    model.yarn_metres_by_color = _yardage(rows, cir, calibration)
    return model
