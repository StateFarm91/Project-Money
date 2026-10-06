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
    # Star stitch (Bench2): five loops pulled up over two stitch widths and closed with a chain,
    # about two and a half hdc of yarn; the beginning star pulls up loops over three stitches,
    # the end star one; two or three hdc in one stitch are that many hdc. Estimates until a
    # physical test calibrates them (YARDAGE_TOLERANCE applies).
    "beg_star_st": 26.0, "star_st": 20.5, "end_star_st": 14.0, "hdc_inc": 16.4, "hdc3": 24.6,
}
# Each factor is the yarn for ONE instance of the op as written -- one `inc` is two sc worked
# into one stitch (12.4 = 2 x 6.2), one `cable2x2` is four dc crossing (46.0), one `hdc3` is
# three hdc (24.6). So the yarn for an op is factor x op.count, never factor x op.produces:
# multiplying by what the op produces counted every increase's second stitch twice (and a
# 2x2 cable four times over). That was PT-07 (2026-10-06): the hexagon coaster set was
# stated at 41.0 m when its own model gives 28.8 m, 43 % over and well outside the +/-20 %
# the document promises.
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
    # Flat pieces only: the fabric height at the top of each row, cumulative, keyed by row
    # index. Each row contributes its own height (`geometry._row_height_cm`: a dc row is
    # taller than an sc row), so progress milestones read the twin rather than dividing the
    # total evenly across rows.
    row_top_cm: dict[int, float] = field(default_factory=dict)
    # Set when a width had to be computed with an assumed chain gauge. A measurement that
    # rests on an assumption must say so wherever it is read, or it gets quoted as measured.
    width_caveat: str = ""
    # Round pieces whose increases all stack (`geometry.corners` = n >= 3) are n-sided
    # polygons, and a polygon has two "across" measurements. Both are computed from the
    # perimeter the stitch count makes; `width_cm` is the across-the-points figure (the
    # largest extent) and `size_statement` names the convention wherever a size is printed.
    sides: int | None = None
    across_points_cm: float | None = None
    across_flats_cm: float | None = None
    # The rule row heights were computed by (`geometry.HEIGHT_RULE`).
    height_rule: str = ""

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

    # Each row contributes its own height by the stitches it actually contains
    # (`geometry.row_height_cm`, the stitch-weighted rule -- PT-08).
    from .geometry import row_height_cm

    height_cm = sum(row_height_cm(r, cir) for r in rows)
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
            cm += factor * stitch_width_cm * op.count     # per instance: see _YARN_FACTOR
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
        if cir.gauge:
            from .geometry import _row_height_cm

            top = 0.0
            for r in rows:
                top += _row_height_cm(r, cir)
                model.row_top_cm[r.index] = round(top, 3)
    else:
        # Worked in the round. Stitches around are a circumference, not a width, and the
        # flat arithmetic would advertise a 5 cm bauble as a 15 cm one.
        rev = measure(comp, result, cir)
        model.geometry = rev
        model.shape = rev.shape
        model.circumference_cm = round(rev.max_circumference_cm, 1) or None
        model.size_refusal = rev.refusal()
        model.width_cm, model.height_cm = rev.footprint_cm()
        from .geometry import corners, polygon_spans_cm

        sides = corners(rows)
        model.sides = sides
        if sides and sides >= 3 and model.width_cm is not None and rev.rings:
            # The widest round's perimeter is stitch count x stitch width; a polygon with
            # that perimeter has these two spans. A disc is points one way, flats the other;
            # a vessel keeps its axial height.
            base_ring = max(rev.rings, key=lambda r: r.circumference_cm)
            points, flats = polygon_spans_cm(base_ring.circumference_cm, sides)
            model.across_points_cm = round(points, 1)
            model.across_flats_cm = round(flats, 1)
            model.width_cm = model.across_points_cm
            if rev.shape == "disc":
                model.height_cm = model.across_flats_cm
    if cir.gauge:
        from .geometry import HEIGHT_RULE

        model.height_rule = HEIGHT_RULE

    model.yarn_metres_by_color = _yardage(rows, cir, calibration, comp.make)
    return model


_POLYGON_NAMES = {3: "triangle", 4: "square", 5: "pentagon", 6: "hexagon", 8: "octagon"}


def size_statement(twin: TwinModel, *, places: int = 1) -> str | None:
    """The finished size in words that name their own convention (PT-10).

    A flat piece is width x length. A stacked-increase round piece is a polygon and is
    quoted across the points AND across the flats, with its shape named; a circle is quoted
    across. A vessel adds its height. None when the twin refuses a size.
    """
    if not twin.width_cm:
        return None
    f = f"{{:.{places}f}}"
    if twin.sides and twin.sides >= 3 and twin.across_points_cm:
        name = _POLYGON_NAMES.get(twin.sides, f"{twin.sides}-sided polygon")
        spans = (f"{f.format(twin.across_points_cm)} cm across the points, "
                 f"{f.format(twin.across_flats_cm)} cm across the flats")
        if twin.shape != "disc" and twin.height_cm:
            return f"{name} base {spans}; {f.format(twin.height_cm)} cm tall"
        return f"{name}, {spans}"
    if twin.shape is not None:
        if twin.shape == "disc" or not twin.height_cm:
            return f"{f.format(twin.width_cm)} cm across"
        return f"{f.format(twin.width_cm)} cm across, {f.format(twin.height_cm)} cm tall"
    if twin.height_cm:
        return f"{f.format(twin.width_cm)} x {f.format(twin.height_cm)} cm"
    return f"{f.format(twin.width_cm)} cm wide"
