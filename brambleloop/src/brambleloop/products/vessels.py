"""Pieces worked in the round: baskets, bowls and flat polygons (sections 2, 16).

Two products in the catalogue were named for shapes their patterns did not make. "Market
Basket Trio" was a single flat rectangle whose own designer note admitted it was "the side
panel, seamed into the basket" -- with no seaming instructions anywhere in the document. A
buyer would have paid for three baskets and received one panel. "Hexagon Coaster Set" was a
rectangle with a colourwork motif on it.

Both are now generated here, worked in the round, from arithmetic that the compiler checks
and `cir.geometry` measures. A basket is a disc of base rounds and then straight walls, which
is a shape the surface model measures exactly: the base sets how wide it is, the walls set
how tall. A hexagon is six columns of stacked increases, which `geometry.corners` can see in
the stitch positions rather than take on trust.

Sizes are derived from the finished size wanted, not chosen to look tidy: a target
circumference becomes a stitch count the motif and the gauge both allow, and the stitch count
becomes the diameter that goes on the listing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row

# Cotton at a firm gauge, because a basket that flops is not a basket. These are the same
# family of constants the flat catalogue uses, at the tighter end.
COTTON_GAUGE = Gauge(stitches_per_10cm=18, rows_per_10cm=20, stitch_type="sc", hook_mm=4.0)
COASTER_GAUGE = Gauge(stitches_per_10cm=20, rows_per_10cm=22, stitch_type="sc", hook_mm=3.5)

PALETTE = {"cream": "#FAF6EB", "wine": "#6E1F2A"}


@dataclass(frozen=True)
class BasketSize:
    """A basket described by the object, not by its row count."""

    key: str
    label: str
    across_cm: float
    tall_cm: float


BASKET_SIZES = (
    BasketSize("small", "bread basket", across_cm=15.0, tall_cm=9.0),
    BasketSize("medium", "storage basket", across_cm=20.0, tall_cm=16.0),
    BasketSize("large", "market basket", across_cm=25.0, tall_cm=23.0),
)


def diameter_cm(stitches: int, gauge: Gauge) -> float:
    """The diameter a round of `stitches` actually makes at this gauge.

    The inverse of `base_stitches_for`, and the reason it exists: that function rounds the
    wanted size to a multiple of `wedges` and floors it at two rounds' worth, so the size
    asked for and the size made are two different numbers. This module's own docstring says
    "the stitch count becomes the diameter that goes on the listing" -- that is this, and the
    listings are built from it rather than from the request.
    """
    return (stitches / gauge.stitches_per_10cm * 10.0) / math.pi


def base_stitches_for(across_cm: float, gauge: Gauge, wedges: int = 6) -> int:
    """The base stitch count that lands nearest the wanted diameter.

    A flat disc's circumference is its diameter times pi, and one round of the standard
    increase adds `wedges` stitches, so the count has to be a multiple of `wedges` -- an
    off-multiple base leaves one wedge short and the disc cups on one side.

    The count that comes back is therefore not the size asked for: it is rounded to a whole
    number of wedges, and floored at `wedges * 2` because one increase round is not a disc.
    Feed it back through `diameter_cm` to find out what was actually made. The floor is the
    one that matters -- below about 7 cm at a coaster gauge it discards the request entirely
    and the piece comes out nearly twice the size asked for.
    """
    circumference = across_cm * math.pi
    stitches = circumference * gauge.stitches_per_10cm / 10.0
    return max(wedges * 2, int(round(stitches / wedges)) * wedges)


def _disc_rounds(base_count: int, color: str, wedges: int = 6,
                 start: int = 1) -> list[Row]:
    """Increase rounds from a magic ring to `base_count`, keeping the increases stacked.

    The increase falls at the end of every wedge, which puts it into the stitch the previous
    round's increase made. Stacked increases turn a corner in the same places each round,
    which is what makes a hexagon rather than a circle -- and `geometry.corners` reads that
    back out of the stitch positions.
    """
    if base_count % wedges:
        raise ValueError(f"{base_count} stitches is not a multiple of {wedges} wedges")
    rows = [Row(index=start, ops=[Op("sc", wedges)], declared_count=wedges, color=color)]
    index = start
    count = wedges
    while count < base_count:
        index += 1
        per_wedge = count // wedges
        body: list = [Op("sc", per_wedge - 1), Op("inc")] if per_wedge > 1 else [Op("inc")]
        count += wedges
        rows.append(Row(index=index, ops=[Repeat(body, times=wedges)],
                        declared_count=count, color=color))
    return rows


def build_basket(size: str = "medium", version: str = "1.0.0") -> CIR:
    """A basket: a flat disc base, then straight walls at the base's stitch count."""
    spec = next((s for s in BASKET_SIZES if s.key == size), None)
    if spec is None:
        raise KeyError(f"unknown basket size {size!r}; have "
                       f"{[s.key for s in BASKET_SIZES]}")

    base_count = base_stitches_for(spec.across_cm, COTTON_GAUGE)
    rows = _disc_rounds(base_count, "cream")
    row_cm = 10.0 / COTTON_GAUGE.rows_per_10cm
    wall_rounds = max(6, int(round(spec.tall_cm / row_cm)))

    # Two contrast bands up the wall, placed by thirds so they read as deliberate at any
    # size rather than landing wherever the loop happened to stop.
    band_rounds = {int(wall_rounds * 0.45), int(wall_rounds * 0.45) + 1,
                   int(wall_rounds * 0.7), int(wall_rounds * 0.7) + 1}
    index = rows[-1].index
    for w in range(1, wall_rounds + 1):
        index += 1
        # No per-round turning chain: the component's construction line already tells the
        # maker to ch 1 after joining, and saying it twice in two places is how the two end
        # up disagreeing.
        rows.append(Row(index=index, ops=[Op("sc", base_count)], declared_count=base_count,
                        color="wine" if w in band_rounds else "cream"))

    return CIR(
        slug=f"market-basket-{spec.key}",
        title=f"Crochet {spec.label.title()}",
        version=version,
        construction="joined_rounds",
        risk_class="B",
        colors=dict(PALETTE),
        gauge=COTTON_GAUGE,
        materials=[
            Material(name="worsted cotton", yarn_weight="worsted", colorway="cream",
                     color_id="cream"),
            Material(name="worsted cotton", yarn_weight="worsted", colorway="wine",
                     color_id="wine"),
        ],
        components=[Component(name="basket", construction="joined_rounds", rows=rows,
                              foundation=0, foundation_kind="magic_ring",
                              note="Worked in one piece from the centre of the base.")],
        designer_notes=(
            "Class B: the arithmetic is verifiable and the geometry is measurable, but how "
            "firmly it stands up depends on the yarn and the maker's tension, so nothing is "
            "claimed about that until a physical sample says so."),
        finished_size_note=(
            f"About {diameter_cm(base_count, COTTON_GAUGE):.0f} cm across and "
            f"{wall_rounds * row_cm:.0f} cm tall at the stated gauge, measured from the "
            f"base."),
    )


def build_hexagon_coaster(across_cm: float = 10.0, make: int = 4,
                          version: str = "1.0.0") -> CIR:
    """A six-sided coaster, worked in joined rounds with the increases stacked at the corners."""
    count = base_stitches_for(across_cm, COASTER_GAUGE)
    # The size on the listing is the size the stitch count makes, not the size that was
    # asked for. `base_stitches_for` rounds to a whole wedge and floors at twelve stitches,
    # so `across_cm` is a request and `diameter_cm(count, ...)` is the answer -- and the
    # listing has to carry the answer. Printing the request made the note independent of
    # every number under it: `build_hexagon_coaster(across_cm=1.0)` produced a 1.9 cm coaster
    # and told the buyer it was 1 cm, and no test could see it because the only round pieces
    # anything measures are the three BASKET_SIZES, whose rounding is under half a
    # centimetre.
    rows = _disc_rounds(count, "cream")
    # A contrast round one in from the edge reads as a border without a second yarn join on
    # every round.
    rows[-2].color = "wine"

    return CIR(
        slug="hexagon-coaster-set",
        title="Hexagon Coaster Set",
        version=version,
        construction="joined_rounds",
        risk_class="A",
        colors=dict(PALETTE),
        gauge=COASTER_GAUGE,
        materials=[
            Material(name="dk cotton", yarn_weight="dk", colorway="cream", color_id="cream"),
            Material(name="dk cotton", yarn_weight="dk", colorway="wine", color_id="wine"),
        ],
        components=[Component(name="coaster", construction="joined_rounds", rows=rows,
                              foundation=0, foundation_kind="magic_ring", make=make,
                              note="Six wedges, with the increase stacked at each corner.")],
        finished_size_note=(
            f"About {diameter_cm(count, COASTER_GAUGE):.1f} cm across the points at the "
            f"stated gauge. Lies flat: the radius grows at one row height per round, which "
            f"is what makes a flat disc."),
    )


def build(version: str = "1.0.0") -> CIR:
    """The headline basket, for the engineered-design registry."""
    return build_basket("medium", version=version)
