"""Geometry of a piece worked in the round, treated as a surface of revolution.

A flat panel's finished size is straightforward: stitches across divided by gauge is the
width, rows up divided by gauge is the length. Apply that arithmetic to something worked in
the round and every number it produces is wrong. Thirty stitches around a hemisphere is a
*circumference* of 15 cm, not a width of 15 cm -- the piece is under 5 cm across. A listing
built on that mistake advertises a three-inch bauble as a six-inch one, which is a size
claim, therefore a refund, therefore exactly the class of defect that made `Stitch.row_height`
necessary (B-016).

The model here is the one the fabric actually obeys. Each round is a circle of radius r at
some distance s measured *along the surface* of the fabric from where the piece started.
Between two consecutive rounds the fabric travels its own row height, and that travel is
split between growing outward and rising upward:

    (row height)^2 = (change in radius)^2 + (axial rise)^2

Everything falls out of that one relationship, and nothing has to be declared:

- A flat disc is the case where the radius grows at exactly the row height. Which is why the
  familiar "+6 sc per round" rule makes a circle that lies flat: six stitches of
  circumference is 6/(2*pi) = 0.95 of a stitch-width of radius, and a single crochet row is
  about 1.05 stitch-widths tall, so the two match within a few percent. The rule is not a
  coincidence and it is not universal either -- it holds for single crochet at the row-to-
  stitch ratio single crochet actually has.
- A tube is the case where the radius does not grow at all, so the whole row height becomes
  axial rise.
- A cone, a dome, a ball and a tapered bag are the cases in between, and their height is the
  sum of the rises rather than the sum of the row heights.
- And a round whose radius grows *faster* than its own row height is asking the fabric to
  cover more surface than it has, so it gathers. That is a frill. It may well be deliberate,
  but it is not a smooth surface any more, and a smooth surface is what a diameter describes.

So this module reports dimensions where the geometry supports them and refuses where it does
not, rather than returning a confident number for a shape it cannot model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import stitches
from .compiler import ERROR, WARNING, CompileResult, Finding, ResolvedRow
from .model import CIR, Component

# A disc's radius grows at exactly its row height, so real patterns sit right on the
# boundary and gauge measured flat is never quite gauge worked in the round. Below this
# ratio the fabric is treated as smooth; above it, it has to gather.
SMOOTH_TOLERANCE = 1.15

# Past this the gathering is not a rounding artefact, it is a frill: a round growing at
# twice its own height has half again as much fabric as the surface can hold.
FRILL_RATIO = 1.5

# A round this small closes by pulling the tail through. Anything larger has to be sewn or
# drawn up, which is a finishing instruction, not an assumption.
CLOSEABLE_STITCHES = 8

DISC = "disc"
TUBE = "tube"
CONE = "cone"
DOME = "dome"
VESSEL = "vessel"
SHAPED = "shaped"
GATHERED = "gathered"


@dataclass(frozen=True)
class Ring:
    """One round, as a circle of fabric."""

    index: int
    count: int
    circumference_cm: float
    radius_cm: float
    row_height_cm: float
    radius_delta_cm: float
    rise_cm: float
    arc_cm: float
    axial_cm: float

    @property
    def diameter_cm(self) -> float:
        return self.radius_cm * 2.0

    @property
    def growth_ratio(self) -> float:
        """How hard this round pushes outward, relative to what its height allows.

        At 1.0 the fabric lies flat, below 1.0 it rises, above 1.0 it has to gather.
        """
        if self.row_height_cm <= 0:
            return 0.0
        return abs(self.radius_delta_cm) / self.row_height_cm


@dataclass
class Revolution:
    """A round-worked component's geometry, and what may honestly be claimed about it."""

    component: str
    rings: list[Ring] = field(default_factory=list)
    shape: str = SHAPED
    findings: list[Finding] = field(default_factory=list)

    @property
    def max_diameter_cm(self) -> float:
        return max((r.diameter_cm for r in self.rings), default=0.0)

    @property
    def axial_height_cm(self) -> float:
        """How tall the piece stands, summing each round's rise.

        Measured from the first round to the last, so it is the distance between the centres
        of those rounds rather than the outer edge of the fabric: a twenty-round tube worked
        from a ring reads as nineteen row heights. The missing half-row at each end is inside
        gauge variance and always errs low, which is the right direction for a size claim. A
        piece worked base-first -- the shape this actually ships on, a basket -- has no such
        gap, because its first wall round rises from the base.
        """
        return sum(r.rise_cm for r in self.rings)

    @property
    def max_circumference_cm(self) -> float:
        """The widest round, measured around.

        This is the most robust number the model produces, because it is stitch count
        divided by gauge and nothing else -- no assumption about what shape the fabric
        settles into. It is also the number that actually matters commercially: a hat is
        sold by head circumference, a basket by how much it holds around.
        """
        return max((r.circumference_cm for r in self.rings), default=0.0)

    @property
    def smooth(self) -> bool:
        """True when every round's growth is within what its own height can cover."""
        return all(r.growth_ratio <= SMOOTH_TOLERANCE for r in self.rings)

    @property
    def closes(self) -> bool:
        """True when the last round is small enough to close by pulling the tail through."""
        return bool(self.rings) and self.rings[-1].count <= CLOSEABLE_STITCHES

    def refusal(self) -> str | None:
        """Why no finished width and height may be stated, or None when they may be.

        The surface model is exact for fabric that lies where the stitches put it: a disc, a
        tube, a straight-sided cone. It is *not* exact for a closed three-dimensional piece.
        The giveaway is in the numbers above -- rounds 2 to 5 of every amigurumi grow at
        almost exactly their own row height, which is the flat case, so the surface model
        says a hemisphere is a 0.5 cm pancake. It is not lying: worked loose and unstuffed it
        really would lie almost flat. The ball is made by the stuffing and the maker's
        tension, and neither of those is in the gauge. So the honest output for a shaped
        piece is a circumference, which is arithmetic, plus a refusal to state a height,
        which is what a physical sample is for (section 3).
        """
        if not self.rings:
            return "no rounds to measure"
        if self.shape == GATHERED:
            return ("the fabric gathers, so no diameter describes it; a physical sample has "
                    "to be measured")
        if self.shape in (DOME, SHAPED):
            return ("a closed shaped piece takes its finished form from stuffing and "
                    "tension, which gauge cannot predict; state the circumference and "
                    "measure a physical sample for the rest")
        return None

    def footprint_cm(self) -> tuple[float | None, float | None]:
        """(across, tall) as a listing may state them, or (None, None) to refuse.

        A disc is measured across twice, because that is the only number anyone means by the
        size of a coaster.
        """
        if self.refusal() is not None:
            return None, None
        across = round(self.max_diameter_cm, 1)
        if self.shape == DISC:
            return across, across
        return across, round(self.axial_height_cm, 1)


def _row_height_cm(row: ResolvedRow, cir: CIR) -> float:
    """The physical height of one round, in cm, from the gauge's own stitch."""
    assert cir.gauge is not None
    base = stitches.get(cir.gauge.stitch_type).row_height or 1.0
    tallest = max((stitches.get(o.stitch).row_height for o in row.ops), default=base)
    return (10.0 / cir.gauge.rows_per_10cm) * (tallest / base)


def _classify(rings: list[Ring]) -> str:
    """Name the shape from the radii alone.

    The line that matters is whether the radius ever comes back *in*. A piece that only ever
    grows or holds steady is open: a coaster, a tube, a cone, a basket. Where the fabric goes
    is where the stitches put it, and the surface model measures it exactly. A piece that
    closes again is a three-dimensional form whose finished shape is set by stuffing and
    tension, and no arithmetic on gauge will tell you how tall it ends up.
    """
    if not rings:
        return SHAPED
    if any(r.growth_ratio > SMOOTH_TOLERANCE for r in rings):
        return GATHERED

    # Round 1 is the start of the fabric, not a change in it: a magic ring jumps from nothing
    # to its own circumference and would classify every piece as gathered.
    shaping = rings[1:]
    if not shaping:
        return DISC

    grew = [r for r in shaping if r.radius_delta_cm > 1e-9]
    shrank = [r for r in shaping if r.radius_delta_cm < -1e-9]

    if shrank:
        return SHAPED if grew else DOME
    if not grew:
        return TUBE

    flat_rate = all(r.growth_ratio >= 2.0 - SMOOTH_TOLERANCE for r in grew)
    if len(grew) == len(shaping):
        if flat_rate:
            # Growing at the full row height is the flat case. A cone cannot, because some
            # of its height has to go into rising.
            return DISC
        ratios = [r.growth_ratio for r in grew]
        return CONE if max(ratios) - min(ratios) <= 0.15 else VESSEL
    # Growth that starts and then stops: a base and then walls. A basket, a bag, a bowl.
    return VESSEL


def measure(comp: Component, result: CompileResult, cir: CIR) -> Revolution:
    """Measure a round-worked component. Findings describe the fabric, not the designer.

    A gathered round is reported as what it is -- fabric that must ruffle -- at WARNING,
    because a frilled edge is a legitimate design. What is *not* legitimate is stating a
    diameter for it, and `footprint_cm` refuses that separately.
    """
    rev = Revolution(component=comp.name)
    if comp.construction == "flat_rows":
        rev.findings.append(Finding(
            ERROR, "ROUND_GEOMETRY_MISAPPLIED",
            "component is worked in flat rows; its size comes from the flat model, not from "
            "a surface of revolution", comp.name))
        return rev
    if cir.gauge is None:
        rev.findings.append(Finding(
            WARNING, "ROUND_NO_GAUGE",
            "no gauge, so nothing about the finished size can be computed", comp.name))
        return rev

    rows = [r for r in result.rows if r.component == comp.name]
    if not rows:
        rev.findings.append(Finding(
            ERROR, "ROUND_NO_ROWS", "no compiled rounds to measure", comp.name))
        return rev

    sts_per_cm = cir.gauge.stitches_per_10cm / 10.0
    arc = 0.0
    axial = 0.0
    previous_radius: float | None = None

    for row in rows:
        circumference = row.stitch_count / sts_per_cm
        radius = circumference / (2.0 * math.pi)
        height = _row_height_cm(row, cir)

        if previous_radius is None:
            # The first round is where the fabric begins. A magic ring starts at its own
            # radius with no fabric travelled, so it contributes no rise and no growth.
            delta, rise = 0.0, 0.0
        else:
            delta = radius - previous_radius
            rise = math.sqrt(max(height * height - delta * delta, 0.0))
            arc += height
            axial += rise

        rev.rings.append(Ring(
            index=row.index, count=row.stitch_count,
            circumference_cm=round(circumference, 2), radius_cm=round(radius, 3),
            row_height_cm=round(height, 3), radius_delta_cm=round(delta, 3),
            rise_cm=round(rise, 3), arc_cm=round(arc, 2), axial_cm=round(axial, 2)))
        previous_radius = radius

    rev.shape = _classify(rev.rings)

    for ring in rev.rings[1:]:
        ratio = ring.growth_ratio
        if ratio <= SMOOTH_TOLERANCE:
            continue
        direction = "outward" if ring.radius_delta_cm > 0 else "inward"
        severity = WARNING
        code = "ROUND_FRILL" if ratio > FRILL_RATIO else "ROUND_GATHERS"
        rev.findings.append(Finding(
            severity, code,
            f"round moves {abs(ring.radius_delta_cm):.2f} cm {direction} in a round only "
            f"{ring.row_height_cm:.2f} cm tall ({ratio:.2f}x). The fabric cannot lie smooth "
            f"here, so it gathers. Deliberate for a frill; otherwise the shaping is too fast "
            f"and no diameter describes the result",
            comp.name, ring.index))

    return rev


def _increase_and_parentage(row: ResolvedRow) -> tuple[list[int], list[bool]]:
    """(stitches this round's increases consume, was-an-increase per produced stitch).

    Two rounds of six increases each can make two completely different objects. Stack the
    increases on top of each other and the fabric turns a corner in the same six places
    every round, which is a hexagon. Stagger them and the corners never form, which is a
    circle. Both have identical stitch counts, so counting alone cannot tell them apart --
    the difference is *which stitch* each increase is worked into.
    """
    consumed_by_increase: list[int] = []
    produced_from_increase: list[bool] = []
    consumed_index = 0
    for op in row.ops:
        st = stitches.get(op.stitch)
        increases = st.produces > st.consumes
        for _ in range(op.count):
            if increases:
                consumed_by_increase.append(consumed_index)
            consumed_index += st.consumes
            produced_from_increase.extend([increases] * st.produces)
    return consumed_by_increase, produced_from_increase


def corners(rows: list[ResolvedRow]) -> int | None:
    """How many corner columns the shaping makes: 0 for a circle, n for an n-sided polygon.

    None when there is nothing to judge -- fewer than two increase rounds, or increases that
    stack in some places and not others -- because a single increase round is as consistent
    with a hexagon as with a circle and guessing would make the answer worse than admitting
    there isn't one.

    Used as *evidence for* a polygon claim, never as grounds to reject one. Circle patterns
    stagger their increases by convention and the conventions vary; a staggered increase can
    still land on a leg of the previous round's increase, so a "not a polygon" verdict from
    this function would not be reliable enough to block a release on. A fully stacked result
    is unambiguous, and that is the only direction it is trusted in.
    """
    increase_rounds = []
    parentage: dict[int, list[bool]] = {}
    for row in rows:
        consumed, produced = _increase_and_parentage(row)
        parentage[row.index] = produced
        if consumed:
            increase_rounds.append((row.index, consumed))

    if len(increase_rounds) < 2:
        return None

    stacked_rounds = 0
    for position, (index, consumed) in enumerate(increase_rounds):
        if position == 0:
            continue
        previous = parentage.get(index - 1)
        if previous is None:
            return None
        stacked = sum(1 for c in consumed if c < len(previous) and previous[c])
        if stacked == len(consumed):
            stacked_rounds += 1
        elif stacked:
            # Some increases stack and some do not. That is not a polygon and not a circle;
            # it is a shape nobody can name from the numbers, so no claim is supported.
            return None

    if stacked_rounds == len(increase_rounds) - 1:
        return len(increase_rounds[-1][1])
    if stacked_rounds == 0:
        return 0
    return None


def measure_all(cir: CIR, result: CompileResult) -> dict[str, Revolution]:
    """Measure every round-worked component. Flat components are absent, not empty."""
    return {c.name: measure(c, result, cir)
            for c in cir.components if c.construction != "flat_rows"}
