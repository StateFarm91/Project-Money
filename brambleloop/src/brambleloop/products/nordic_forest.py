"""The Nordic Forest throw: the first product engineered rather than templated.

The pipeline's generic concept-to-CIR builder makes a striped panel. That is enough to prove
the machinery works and it is not a product anyone would buy. This module is what a real
Brambleloop design looks like: a motif defined as a grid, turned into rows by code, and
verified by the same compiler as everything else.

Two things are deliberate.

The motif is data, not prose. A 12-stitch by 24-row grid of ones and zeros is something a
human can look at, a chart can render, and a compiler can check. Section 2 forbids handing a
model a picture and asking it to write instructions; this is the inverse -- the instructions
and the picture are the same object.

Every size is generated from that one motif. The competitors we profiled ship one finished
size per pattern, because grading by hand is work and grading by hand is where mistakes come
from. Generating each size from the motif means the 96-stitch baby blanket and the 192-stitch
full throw are the same verified design, and each one gets its own compile.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row

# 12-stitch repeat, read bottom row first. 1 = the raised contrast stitch (dc), 0 = the
# background stitch (sc). Two alternating bands: a stylised fir tree and a nordic star.
MOTIF: list[str] = [
    "000000000000",
    "000001100000",
    "000011110000",
    "000111111000",
    "000001100000",
    "000011110000",
    "000111111000",
    "001111111100",
    "000001100000",
    "000001100000",
    "000000000000",
    "000010000100",
    "000001001000",
    "010000110000",
    "001001111001",
    "000111111100",
    "011111111110",
    "000111111100",
    "001001111001",
    "010000110000",
    "000001001000",
    "000010000100",
    "000000000000",
    "000000000000",
]

MOTIF_WIDTH = 12
PALETTE = {"forest": "#244A3A", "cream": "#FAF6EB"}

SIZES: dict[str, tuple[int, int]] = {
    # name: (stitches wide, motif repeats tall)
    "baby": (96, 3),
    "throw": (144, 5),
    "large": (192, 7),
}


@dataclass(frozen=True)
class SizeSpec:
    name: str
    width_stitches: int
    motif_repeats: int

    @property
    def rows(self) -> int:
        return len(MOTIF) * self.motif_repeats


def _validate_motif() -> None:
    """A malformed motif must fail here, loudly, not three steps downstream in a chart."""
    for i, line in enumerate(MOTIF):
        if len(line) != MOTIF_WIDTH:
            raise ValueError(f"motif row {i} is {len(line)} wide, expected {MOTIF_WIDTH}")
        if set(line) - {"0", "1"}:
            raise ValueError(f"motif row {i} contains something other than 0 and 1")


def _runs(pattern: str) -> list[Op]:
    """One motif row as run-length ops: '0000011000' -> sc 5, dc 2, sc 3."""
    ops: list[Op] = []
    run_code = "dc" if pattern[0] == "1" else "sc"
    run_len = 0
    for ch in pattern:
        code = "dc" if ch == "1" else "sc"
        if code == run_code:
            run_len += 1
        else:
            ops.append(Op(run_code, run_len))
            run_code, run_len = code, 1
    ops.append(Op(run_code, run_len))
    return ops


def _row_ops(pattern: str, width: int) -> list[Repeat]:
    """One motif row across the full width, expressed as a repeat rather than flattened.

    This is a readability decision with teeth. Flattening 12 repeats of a 12-stitch motif
    produces a row instruction that is eleven lines of prose and physically unusable -- a
    maker following it loses their place, miscounts, and blames the pattern. Emitting

        *sc 2, dc 1, sc 4, dc 1, sc 4* repeat 12 times

    is both what a human can follow and what the compiler can check for divisibility, so the
    readable form and the verifiable form are the same form.
    """
    return [Repeat(_runs(pattern), times=width // MOTIF_WIDTH)]


def build(size: str = "throw", version: str = "1.0.0") -> CIR:
    """Build the CIR for one finished size.

    Colour alternates every row, which is how overlay mosaic is actually worked: you carry
    one colour at a time and the previous colour shows through where you did not cover it.
    """
    _validate_motif()
    if size not in SIZES:
        raise ValueError(f"unknown size {size!r}; have {sorted(SIZES)}")
    width, repeats = SIZES[size]
    if width % MOTIF_WIDTH:
        raise ValueError(f"{size}: {width} stitches is not a multiple of the {MOTIF_WIDTH}-"
                         f"stitch repeat, so the motif would be cut off mid-tree")
    spec = SizeSpec(size, width, repeats)

    rows: list[Row] = []
    index = 0
    for _ in range(repeats):
        for line in MOTIF:
            index += 1
            color = "forest" if index % 2 == 1 else "cream"
            if index == 1:
                ops = [Op("sc", width)]     # foundation row is plain
            else:
                ops = _row_ops(line, width)
            rows.append(Row(index=index, ops=ops, declared_count=width,
                            turning_chain=1, color=color))

    return CIR(
        slug=f"nordic-forest-mosaic-throw-{size}",
        # The throw is the headline product, so it carries the plain name; the other sizes
        # qualify it. A title reading "... Throw (Throw)" is the kind of small wrongness that
        # makes a premium shop look automated.
        title=("Nordic Forest Overlay Mosaic Throw" if size == "throw"
               else f"Nordic Forest Overlay Mosaic Blanket ({size.title()})"),
        version=version,
        construction="flat_rows",
        risk_class="A",
        colors=dict(PALETTE),
        gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.0),
        materials=[Material(name="worsted acrylic", yarn_weight="worsted", color_id=c)
                   for c in PALETTE],
        components=[Component(name="blanket", construction="flat_rows", rows=rows,
                              foundation=width, foundation_kind="chain")],
        designer_notes=(
            f"Overlay mosaic on a {MOTIF_WIDTH}-stitch repeat, {spec.rows} rows "
            f"({repeats} motif repeats). Fir and star bands alternate. Colour changes every "
            f"row; carry the resting colour up the side."),
    )


def all_sizes(version: str = "1.0.0") -> dict[str, CIR]:
    return {name: build(name, version) for name in SIZES}
