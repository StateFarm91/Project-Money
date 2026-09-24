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
from .compiler import CompileResult, Finding, ResolvedRow
from .geometry import Revolution, measure
from .model import CIR, Component

# Yarn length consumed per stitch, expressed as a multiple of one gauge stitch-width.
# Derived from the stitch's height: a dc eats far more yarn than a sc. These are starting
# constants with a wide tolerance; physical tests replace them per yarn/hook combination.
# Anchored on a checkable reference rather than picked to look plausible: a worsted-weight
# 120 x 150 cm throw at 16 sts / 18 rows per 10 cm is about 51,800 stitches and is widely
# reported to take 1,800-2,000 m of yarn, which is roughly 3.9 cm of yarn per single crochet,
# or 6.2 stitch-widths at that gauge. The first version of this table was set by feel and came
# out at less than half of that -- it would have told a customer a throw needed 190 m. An
# estimate can be wrong by its stated tolerance; being wrong by a factor of two is a refund.
_YARN_FACTOR = {
    "ch": 2.2, "slst": 2.6, "sc": 6.2, "hdc": 8.2, "dc": 10.5, "tr": 13.1,
    "inc": 12.4, "dec": 9.5, "dc_inc": 21.0, "dc_dec": 17.6, "sk": 0.0,
    # Texture stitches. A post stitch is a dc worked around the post: the same yarn plus a
    # little, because the hook travels further. A bobble is five incomplete dc closed
    # together, so it is five dc of yarn in one stitch's width -- falling back to the
    # default of 3.0 would understate a bobble pillow by more than a third, which is the
    # kind of error that sends a buyer back to the shop for another ball.
    "fpdc": 11.5, "bpdc": 11.5, "bob": 48.0,
    # A crossing is four dc that travel around each other.
    "cable2x2": 46.0, "cable1x1": 23.0,
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
    # Carried from the op so the fabric grid knows its own texture. Without it the twin is a
    # grid of identical cells and every textured pattern renders as plain fabric.
    loop: str = "both"
    # Where this stitch sits in the *fabric*, as opposed to the order it was worked in.
    #
    # Flat rows are worked back and forth: you turn at the end of every row, so the stitch
    # you make first in row 3 is at the opposite edge from the stitch you made first in row
    # 2. `position` is working order, which is what the writer needs; `fabric_position` is
    # where the stitch actually is, which is what anything looking at the surface needs.
    #
    # Found 2026-09-24 by the benchmark cardigan, whose hem ribbing is worked into the body
    # as nine back-loop stitches at one edge of every row. In working order those nine sat
    # at positions 0-8 on odd rows and 80-88 on even ones, so the twin described a rib that
    # zig-zagged from edge to edge instead of the continuous band the garment has. The same
    # error mirrors every other row of `color_grid`, which feeds chart rendering -- so a flat
    # two-colour chart has been drawn with alternate rows reversed.
    fabric_position: int = 0


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
    # Round-worked pieces only. `shape` and `circumference_cm` are facts of stitch count and
    # gauge; `size_refusal` is set when the geometry cannot support a width and a height, in
    # which case both are None on purpose and no downstream claim may invent them.
    shape: str | None = None
    circumference_cm: float | None = None
    size_refusal: str | None = None
    geometry: Revolution | None = None
    # Flat pieces only: "rectangle" or "shaped_flat", derived from the row widths.
    outline: str | None = None
    # Set when a width had to be computed with an assumed chain gauge. A measurement that
    # rests on an assumption must say so wherever it is read, or it gets quoted as measured.
    width_caveat: str = ""

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
        """Row-major grid of stitch codes, bottom row first, in FABRIC order.

        A chart is a picture of the fabric, so it is indexed by where stitches are rather
        than by the order they were made in. See `Cell.fabric_position`.
        """
        return self._grid(lambda c: c.stitch)

    def color_grid(self) -> list[list[str | None]]:
        return self._grid(lambda c: c.color)

    def loop_grid(self) -> list[list[str]]:
        """Which loop each stitch entered. This is what makes a texture a texture."""
        return self._grid(lambda c: getattr(c, "loop", "both"))

    def _grid(self, pick):
        rows = sorted({c.row for c in self.cells})
        out = []
        for r in rows:
            cells = sorted((c for c in self.cells if c.row == r),
                           key=lambda c: c.fabric_position)
            out.append([pick(c) for c in cells])
        return out


def row_width_cm(row: ResolvedRow, gauge) -> tuple[float, str]:
    """How wide one row's fabric actually is, and what had to be assumed to say so.

    Not simply `stitch_count / gauge`, because a chain's width depends on what it is doing:

      * a worked stitch is one stitch-width;
      * a chain BRIDGING a gap (`spans > 0`) occupies the width of the stitches it replaced
        and contributes nothing of its own -- laid across the fabric, not added to it;
      * a chain adding fabric (`spans == 0`) is a chain-width, which is narrower than a
        stitch-width and is only knowable when the gauge states it.

    Returns (width_cm, caveat). The caveat is empty when nothing was assumed; otherwise it
    names what is unknown, so a size claim built on an assumed chain gauge can never be
    presented as a measured one.
    """
    st_cm = 10.0 / gauge.stitches_per_10cm
    ch_cm = (10.0 / gauge.chains_per_10cm) if gauge.chains_per_10cm else None
    width, assumed_chains = 0.0, 0
    for op in row.ops:
        if op.stitch != "ch":
            width += op.produces * st_cm
            continue
        spans = getattr(op, "spans", 0)
        if spans:
            width += spans * st_cm          # bridges existing width, adds none of its own
        elif ch_cm is not None:
            width += op.count * ch_cm
        else:
            width += op.count * st_cm       # the old behaviour, now declared rather than silent
            assumed_chains += op.count
    caveat = ("" if not assumed_chains else
              f"{assumed_chains} chain(s) add fabric width but the gauge states no chain "
              f"gauge, so they were measured at stitch gauge; chains are typically 20-35% "
              f"narrower, so this width is an over-estimate")
    return width, caveat


def _flat_dimensions(rows: list[ResolvedRow], cir: CIR) -> tuple[float | None, float | None]:
    """Finished size of a piece worked in flat rows: stitches across, rows up.

    Only ever correct for flat fabric. A piece worked in the round has a *circumference*
    where this reads a width, and `geometry.measure` handles it instead.
    """
    if not cir.gauge or not rows:
        return None, None
    g = cir.gauge
    width_cm = max(row_width_cm(r, g)[0] for r in rows)

    # Row height scales with stitch height relative to the gauge stitch.
    base = stitches.get(g.stitch_type).row_height or 1.0
    row_cm = 10.0 / g.rows_per_10cm
    height_cm = 0.0
    for r in rows:
        tallest = max((stitches.get(o.stitch).row_height for o in r.ops), default=base)
        height_cm += row_cm * (tallest / base)
    return round(width_cm, 1), round(height_cm, 1)


def _yardage(rows: list[ResolvedRow], cir: CIR, calibration: float,
             make: int = 1) -> dict[str, float]:
    """Yarn per colour for the whole pattern, which means all `make` copies of the piece.

    A coaster set of four needs four coasters' worth of yarn. Reporting one piece's estimate
    for a pattern that asks for four understates it by a factor of four, and a buyer who
    orders one ball short of a set finds out at coaster three.
    """
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
    return {k: round(v / 100.0 * calibration * make, 1) for k, v in totals.items()}


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
    comp_early = next(c for c in cir.components if c.name == name)
    # Only flat work turns. Rounds keep going the same way, so working order already is
    # fabric order and mirroring them would invent a reversal the fabric does not have.
    turns = comp_early.construction == "flat_rows"
    for r in rows:
        pos = 0
        for op in r.ops:
            st = stitches.get(op.stitch)
            for _ in range(op.count):
                for _ in range(st.produces):
                    model.cells.append(
                        Cell(row=r.index, position=pos, stitch=op.stitch,
                             color=r.color, repeat_group=op.repeat_group,
                             loop=getattr(op, "loop", "both"))
                    )
                    pos += 1
        model.row_widths[r.index] = pos
        if turns and r.index % 2 == 0:
            # This row was worked in the opposite direction, so its fabric coordinates run
            # the other way. Mirrored against this row's own width: a short row sits where
            # it was worked, not padded to the widest row.
            for c in model.cells[-pos:]:
                c.fabric_position = pos - 1 - c.position
        else:
            for c in model.cells[-pos:]:
                c.fabric_position = c.position

    comp = next(c for c in cir.components if c.name == name)
    if comp.construction == "flat_rows":
        model.width_cm, model.height_cm = _flat_dimensions(rows, cir)
        if cir.gauge:
            caveats = {row_width_cm(r, cir.gauge)[1] for r in rows}
            model.width_caveat = next((c for c in sorted(caveats) if c), "")
        # The outline is the piece's silhouette, derived from the row widths rather than
        # declared. A flat piece whose every row has the same stitch count is a rectangle,
        # whatever the listing calls it, and a hexagon coaster that is really a rectangle is
        # a product sold as one shape and delivered as another.
        widths = set(model.row_widths.values())
        model.outline = "rectangle" if len(widths) <= 1 else "shaped_flat"
    else:
        # Worked in the round. Stitches around are a circumference, not a width, and the
        # flat arithmetic would advertise a 5 cm bauble as a 15 cm one.
        rev = measure(comp, result, cir)
        model.geometry = rev
        model.shape = rev.shape
        model.circumference_cm = round(rev.max_circumference_cm, 1) or None
        model.size_refusal = rev.refusal()
        model.width_cm, model.height_cm = rev.footprint_cm()

    model.yarn_metres_by_color = _yardage(rows, cir, calibration, comp.make)
    return model
