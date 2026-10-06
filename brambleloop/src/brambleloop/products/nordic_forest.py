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

from dataclasses import dataclass, replace

from ..cir.model import CIR, Component, Material, Op, Repeat, Row
from ..creative.prototype import gauge_for
from ..gates.originality import catalogue_provenance

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

# The declared yarn. The gauge is derived from its published single-crochet band
# (`creative.prototype.gauge_for`), never typed: this module used to type 16 sc/18 rows per
# 10cm against worsted, a fabric worsted cannot make (band 11-14), so every size and yardage
# figure was arithmetic from a gauge its own yarn could not hold (F-112, F-116; D-FB-6).
YARN_WEIGHT = "worsted"
GAUGE = gauge_for(YARN_WEIGHT)

# name: intended finished (width, height) in cm. These are the sizes the original counts
# made (96/144/192 sts x 3/5/7 motif repeats, as the twin measured them at the old typed
# gauge), kept as the design intent. The counts are recomputed from the derived gauge in whole
# motif repeats -- a tree or a star is never cut -- so the size each pattern states is the
# size its own counts make at its own gauge, within one motif of the intent.
TARGET_CM: dict[str, tuple[float, float]] = {
    "baby": (60.0, 73.3),
    "throw": (90.0, 122.2),
    "large": (120.0, 171.1),
}


def _repeat_height_cm(gauge) -> float:
    """One motif repeat's height at `gauge`, measured as the twin measures it: each row by
    the stitch-weighted mean of the stitches in it (`cir.geometry.HEIGHT_RULE`, PT-08), so a
    single-crochet row carrying a few raised dc is a little taller than a sc row, not a full
    dc row. (Until 1.2.0 this used the tallest-stitch rule, and every size came out about
    40 % shorter than its stated length once the twin measured it truthfully.)"""
    from ..cir import stitches
    from ..cir.geometry import mix_height_units

    base = stitches.get("sc").row_height or 1.0
    return sum(mix_height_units((("dc", line.count("1")), ("sc", line.count("0"))), base)
               for line in MOTIF) * 10.0 / gauge.rows_per_10cm


def _nearest(target: float, unit: float) -> int:
    """Whole units closest to `target`, never fewer than one."""
    return max(1, int(target / unit + 0.5))


# Patterns are software releases: the D-FB-6 re-derivation changed every size's counts and
# gauge, so the released version moved 1.0.0 -> 1.1.0 (tests/data/release_fingerprints.tsv
# pins content against version so a content change cannot keep a released number).
# 1.2.0 / 1.1.0 (2026-10-06, PT-07/PT-08): the twin now counts each increase's yarn once and
# measures a row by the stitch-weighted height of the stitches in it, which moved this
# design's stated yardage and/or size; a customer-visible figure cannot change under a
# released version (tests/data/release_fingerprints.tsv pins content AND claims).
RELEASE_VERSION = "1.2.0"

SIZES: dict[str, tuple[int, int]] = {
    # name: (stitches wide, motif repeats tall), derived from TARGET_CM at GAUGE
    name: (_nearest(w, MOTIF_WIDTH * 10.0 / GAUGE.stitches_per_10cm) * MOTIF_WIDTH,
           _nearest(h, _repeat_height_cm(GAUGE)))
    for name, (w, h) in TARGET_CM.items()
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


def build(size: str = "throw", version: str = RELEASE_VERSION) -> CIR:
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
        gauge=replace(GAUGE),  # a copy, so mutating one CIR cannot move the module's gauge
        materials=[Material(name="worsted acrylic", yarn_weight=YARN_WEIGHT, color_id=c)
                   for c in PALETTE],
        components=[Component(name="blanket", construction="flat_rows", rows=rows,
                              foundation=width, foundation_kind="chain")],
        designer_notes=(
            f"Overlay mosaic on a {MOTIF_WIDTH}-stitch repeat, {spec.rows} rows "
            f"({repeats} motif repeats). Fir and star bands alternate. "
            + _colour_note(rows, width)),
        # F-783: the fir-and-star motif and the size table are this module's own.
        provenance=catalogue_provenance(
            "nordic-forest-mosaic-throw",
            {"builder": "products.nordic_forest.build", "size": size, "width": width,
             "repeats": repeats, "motif": list(MOTIF), "palette": dict(PALETTE)},
            ("products.nordic_forest", "products.nordic_forest.MOTIF", "overlay_mosaic")),
    )


def _colour_note(rows, width) -> str:
    """What the colour changes ask of the maker, read off the rows (PT-09).

    This note said "carry the resting colour up the side" on rows that change colour every
    turned row, where the resting colour is always at the far edge: impossible, and now
    refused by the certificate (COLOUR_CARRY_IMPOSSIBLE). It states what the rows require."""
    from ..cir.colour_changes import plan_component

    plan = plan_component(Component(name="blanket", construction="flat_rows", rows=rows,
                                     foundation=width, foundation_kind="chain"))
    if not plan.changes:
        return ""
    if plan.carry_is_possible:
        return ("Every colour change falls at the same side edge: carry the resting colour "
                "loosely up that edge.")
    return ("Colour changes every row. The rows turn, so the colour not in use is always "
            "resting at the far edge when it is next needed: cut it and rejoin at each "
            "change, and weave in the ends (see Finishing).")


def all_sizes(version: str = RELEASE_VERSION) -> dict[str, CIR]:
    return {name: build(name, version) for name in SIZES}
