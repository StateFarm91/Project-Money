"""The motif library (Master Plan section 5).

Section 5 asks for "reusable original validated motif/component libraries". This is that
library, and it is the mechanism by which the catalogue grows without the defect rate growing
with it: a motif that has compiled inside one product does not have to re-earn its arithmetic
in the next one.

A motif is a grid of ones and zeros — one means the raised contrast stitch, zero the
background. That representation is doing real work. It is something a person can look at, a
chart can render, a compiler can check and a hash can identify, which means the design and the
instructions are the same object rather than two descriptions of one hoped-for object.

Every motif here is original. They are built from geometry — fir shapes, stars, diamonds,
chevrons, cables — which is not copyrightable subject matter, and none of them is traced from,
derived from, or measured against another designer's chart. Section 4 is explicit that
competitor research is demand intelligence only.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


class MalformedMotif(ValueError):
    """A motif grid that is not rectangular, or not made of ones and zeros."""


@dataclass(frozen=True)
class Motif:
    slug: str
    name: str
    grid: tuple[str, ...]
    note: str = ""

    @property
    def width(self) -> int:
        return len(self.grid[0])

    @property
    def height(self) -> int:
        return len(self.grid)

    @property
    def sha256(self) -> str:
        return hashlib.sha256("\n".join(self.grid).encode()).hexdigest()

    @property
    def density(self) -> float:
        """Fraction of raised stitches. Extremes make bad fabric, not just bad pictures."""
        cells = sum(len(r) for r in self.grid)
        return sum(r.count("1") for r in self.grid) / cells if cells else 0.0

    def validate(self) -> None:
        if not self.grid:
            raise MalformedMotif(f"{self.slug}: empty motif")
        w = len(self.grid[0])
        for i, row in enumerate(self.grid):
            if len(row) != w:
                raise MalformedMotif(
                    f"{self.slug}: row {i} is {len(row)} wide, expected {w}. A ragged grid "
                    f"produces a pattern whose rows do not agree on how many stitches exist.")
            bad = set(row) - {"0", "1"}
            if bad:
                raise MalformedMotif(f"{self.slug}: row {i} contains {sorted(bad)}")


def _m(slug: str, name: str, rows: list[str], note: str = "") -> Motif:
    motif = Motif(slug=slug, name=name, grid=tuple(rows), note=note)
    motif.validate()
    return motif


# ---- the library -----------------------------------------------------------

FIR_AND_STAR = _m(
    "fir-and-star", "Fir and Star",
    [
        "000000000000", "000001100000", "000011110000", "000111111000",
        "000001100000", "000011110000", "000111111000", "001111111100",
        "000001100000", "000001100000", "000000000000", "000010000100",
        "000001001000", "010000110000", "001001111001", "000111111100",
        "011111111110", "000111111100", "001001111001", "010000110000",
        "000001001000", "000010000100", "000000000000", "000000000000",
    ],
    "alternating bands: a stylised fir, then a nordic star")

SNOWFALL = _m(
    "snowfall", "Snowfall",
    [
        "000000000000", "000100000010", "001110000111", "000100000010",
        "000000000000", "000000010000", "000000111000", "000000010000",
        "000000000000", "010000001000", "111000011100", "010000001000",
    ],
    "scattered flakes on a twelve-stitch repeat; sparse, so it reads at blanket scale")

DIAMOND_LATTICE = _m(
    "diamond-lattice", "Diamond Lattice",
    [
        "000010000", "000111000", "001101100", "011000110",
        "110000011", "011000110", "001101100", "000111000",
    ],
    "a continuous lattice; every raised stitch touches another, so the fabric holds together")

CHEVRON_BAND = _m(
    "chevron-band", "Chevron Band",
    [
        "00001000", "00011100", "00110110", "01100011",
        "11000001", "01100011", "00110110", "00011100",
    ],
    "a marching chevron for borders and runners")

BASKETWEAVE = _m(
    "basketweave", "Basketweave",
    [
        "11110000", "11110000", "11110000", "11110000",
        "00001111", "00001111", "00001111", "00001111",
    ],
    "alternating blocks; dense and structural, suited to baskets and pillows")

HEART_ROW = _m(
    "heart-row", "Heart Row",
    [
        "0000000000", "0110001100", "1111011110", "1111111110",
        "0111111100", "0011111000", "0001110000", "0000100000",
        "0000000000", "0000000000",
    ],
    "a single heart on a ten-stitch repeat")

PUMPKIN_ROW = _m(
    "pumpkin-row", "Pumpkin Row",
    [
        "0000000000", "0000110000", "0001111000", "0011111100",
        "0111111110", "0111111110", "0111111110", "0011111100",
        "0001111000", "0000000000",
    ],
    "a rounded autumn gourd")

CABLE_TWIST = _m(
    "cable-twist", "Cable Twist",
    [
        "011000110", "001101100", "000111000", "001101100",
        "011000110", "110000011", "111000111", "110000011",
    ],
    "a crossing twist that reads as a cable in texture rather than colour")

LIBRARY: dict[str, Motif] = {
    m.slug: m for m in (FIR_AND_STAR, SNOWFALL, DIAMOND_LATTICE, CHEVRON_BAND,
                        BASKETWEAVE, HEART_ROW, PUMPKIN_ROW, CABLE_TWIST)
}

# Density outside this band makes fabric that either looks like nothing or eats yarn and goes
# stiff. Checked rather than eyeballed, because "looks fine in the chart" is not the test.
MIN_DENSITY, MAX_DENSITY = 0.08, 0.72


def check_library() -> list[str]:
    problems: list[str] = []
    seen: dict[str, str] = {}
    for slug, motif in LIBRARY.items():
        motif.validate()
        if not (MIN_DENSITY <= motif.density <= MAX_DENSITY):
            problems.append(
                f"MOTIF_DENSITY: {slug} is {motif.density:.0%} raised stitches, outside "
                f"{MIN_DENSITY:.0%}-{MAX_DENSITY:.0%}; that is fabric that reads as nothing "
                f"or goes stiff")
        if motif.sha256 in seen:
            problems.append(f"MOTIF_DUPLICATE: {slug} is identical to {seen[motif.sha256]}")
        seen[motif.sha256] = slug
    return problems


def get(slug: str) -> Motif:
    if slug not in LIBRARY:
        raise KeyError(f"no motif {slug!r}; have {sorted(LIBRARY)}")
    return LIBRARY[slug]
