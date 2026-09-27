"""Graded designs: a garment is a function of size, not one size with its numbers changed.

`cir/grading.py` resolves a *width* per size. That is enough for a blanket and nowhere near
enough for a garment, whose sleeve, yoke, neck and length each follow a different body
measurement and whose shaping rows change in number and placement between sizes. The way a
hand-written garment pattern goes wrong is exactly that: the medium is worked out properly and
the other sizes are the medium's numbers nudged. So here a design is a *template*, a function
from one resolved size to a whole CIR, and every size is built by running it -- the same
construction, recomputed from that size's own body.

Three rules.

**Bodies come from a published standard, never from us.** `BodyTable` holds the Craft Yarn
Council standard body measurements, transcribed with their source URL and the date they were
read. A measurement the source does not publish is `UNSOURCED`, and a design that needs it
refuses to grade to that size instead of inventing one. Wrist and neck circumference are
unsourced throughout: the CYC woman and child/youth charts do not give them.

**Ease is the design; the body is not.** `FitIntent` states the ease added to each
measurement. Finished size = body + ease. Nothing else in a template may move a body number.

**A graded template may not contain a fixed-times repeat.** `[...] x 12` in a template is a
number that was right for one size and is silently wrong for the others; widths are stated as
stitch counts computed from the size, or as to-end repeats that resolve against the width
they are given. `GradedDesign.build` refuses any other kind.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable

from .grading import GradingRefused
from .model import CIR, Gauge, Provenance, Repeat

# ---- the published standard ---------------------------------------------------------------

# Transcribed by hand from the pages below on the retrieval date, from the centimetre rows
# of each chart. Where the chart gives a range the range is kept and the midpoint is used.
CYC_WOMAN_URL = "https://www.craftyarncouncil.com/standards/woman-size"
CYC_CHILD_URL = "https://www.craftyarncouncil.com/standards/child-youth-sizes"
RETRIEVED = "2026-09-26"

# The sentinel for a measurement the source does not publish.
UNSOURCED = None

MEASUREMENTS: tuple[str, ...] = (
    "bust",            # CYC "Chest"
    "waist",           # CYC "Waist"
    "hip",             # CYC "Hips"
    "back_length",     # CYC "Back Waist Length" (nape to natural waist)
    "arm_length",      # CYC "Arm Length to Underarm"
    "upper_arm",       # CYC "Upper arm"
    "armhole_depth",   # CYC "Armhole depth"
    "cross_back",      # CYC "Cross Back (Shoulder to shoulder)" -- the shoulder measurement
    "neck_to_wrist",   # CYC "Center Back Neck-to-Wrist"
    "wrist",           # not published by CYC: UNSOURCED
    "neck",            # not published by CYC: UNSOURCED
)

Range = tuple[float, float]


def _cm(value: float | Range | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, tuple):
        lo, hi = value
        return round((lo + hi) / 2.0, 2)
    return float(value)


@dataclass(frozen=True)
class BodyMeasurements:
    """One standard size's body, in cm, as the source states it."""

    size: str
    published: dict[str, float | Range | None]

    def cm(self, measurement: str) -> float | None:
        if measurement not in MEASUREMENTS:
            raise KeyError(f"{measurement!r} is not a measurement this table knows")
        return _cm(self.published.get(measurement))

    def is_sourced(self, measurement: str) -> bool:
        return self.cm(measurement) is not None


@dataclass(frozen=True)
class BodyTable:
    name: str
    source_url: str
    retrieved: str
    sizes: tuple[BodyMeasurements, ...]

    def size(self, name: str) -> BodyMeasurements:
        for body in self.sizes:
            if body.size == name:
                return body
        raise KeyError(f"{self.name} has no size {name!r}: {[b.size for b in self.sizes]}")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(b.size for b in self.sizes)


def _table(name: str, url: str, sizes: tuple[str, ...],
           columns: dict[str, tuple]) -> BodyTable:
    bodies = []
    for i, size in enumerate(sizes):
        published = {m: columns[m][i] if m in columns else UNSOURCED for m in MEASUREMENTS}
        bodies.append(BodyMeasurements(size=size, published=published))
    return BodyTable(name=name, source_url=url, retrieved=RETRIEVED, sizes=tuple(bodies))


# Craft Yarn Council, Woman Size Charts (centimetre rows), read 2026-09-26.
WOMAN = _table("CYC woman", CYC_WOMAN_URL,
               ("XS", "S", "M", "L", "XL", "2X", "3X", "4X", "5X"), {
    "bust": ((71, 76), (81, 86), (91.5, 96.5), (101.5, 106.5), (111.5, 117),
             (122, 127), (132, 137), (142, 147), (152, 158)),
    "neck_to_wrist": ((66, 68.5), (68.5, 70), (71, 72.5), (73.5, 75), (73.5, 75),
                      (76.5, 77.5), (77.5, 79), (80, 81.5), (80, 81.5)),
    "back_length": (42, 43, 43.5, 44.5, 45, 45.5, 45.5, 47, 47),
    "cross_back": ((35.5, 37), (37, 38), (39.5, 40.5), (42, 43), 44.5,
                   45.5, 45.5, 47, 47),
    "arm_length": (42, 43, 43, 44.5, 44.5, 45.5, 45.5, 47, 47),
    "upper_arm": (25, 26, 28, 30.5, 34.5, 39.5, 43, 47, 49.5),
    "armhole_depth": ((15.5, 16.5), (16.5, 17.5), (17.5, 19), (19, 20.5), (20.5, 21.5),
                      (21.5, 23), (23, 24), (24, 25.5), (25.5, 26.5)),
    "waist": ((58.5, 61), (63.5, 67.5), (71, 76), (81.5, 86.5), (91.5, 96.5),
              (101.5, 106.5), (111.5, 114), (116.5, 119), (124, 127)),
    "hip": ((83.5, 86), (89, 91.5), (96.5, 101.5), (106.5, 111.5), (116.5, 122),
            (132, 134.5), (137, 139.5), (142, 144.5), (155, 157)),
})

# Craft Yarn Council, Child/Youth Size Charts (centimetre rows), read 2026-09-26.
# Child 2-10 and youth 12-16 are one run on the source's two charts.
CHILD = _table("CYC child/youth", CYC_CHILD_URL,
               ("2", "4", "6", "8", "10", "12", "14", "16"), {
    "bust": (53, 58.5, 63.5, 67, 71, 76, 80, 82.5),
    "neck_to_wrist": (45.5, 49.5, 52, 56, 61, 66, 68.5, 71),
    "back_length": (21.5, 24, 26.5, 31.5, 35.5, 38, 39.5, 40.5),
    "cross_back": (23.5, 25, 26, 27, 28.5, 30.5, 31, 33),
    "arm_length": (21.5, 26.5, 29, 31.5, 34.5, 38, 40.5, 42),
    "upper_arm": (17.5, 19, 20.5, 21.5, 22, 23, 23.5, 24),
    "armhole_depth": (10.5, 12, 12.5, 14, 15.5, 16.5, 17.5, 19),
    "waist": (53.5, 54.5, 57, 59.5, 62, 63.5, 67.5, 69.5),
    "hip": (56, 59.5, 63.5, 71, 75, 80, 83.5, 90),
})

TABLES: dict[str, BodyTable] = {"woman": WOMAN, "child": CHILD}


# ---- the design's intent ------------------------------------------------------------------


@dataclass(frozen=True)
class FitIntent:
    """Ease per measurement, in cm. Positive is room; negative ease is refused."""

    ease_cm: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for m, e in self.ease_cm.items():
            if m not in MEASUREMENTS:
                raise GradingRefused(f"ease given for unknown measurement {m!r}")
            if e < 0:
                raise GradingRefused(
                    f"negative ease on {m} means the garment is smaller than the body")

    def ease(self, measurement: str) -> float:
        return float(self.ease_cm.get(measurement, 0.0))


@dataclass(frozen=True)
class GradedSize:
    """One size, resolved: its body, the design's ease, and the gauge that converts both."""

    size: str
    body: BodyMeasurements
    fit: FitIntent
    gauge: Gauge

    def body_cm(self, measurement: str) -> float:
        value = self.body.cm(measurement)
        if value is None:
            raise GradingRefused(
                f"size {self.size}: {measurement} is UNSOURCED in the standard this design "
                f"grades from. A measurement nobody published is not one we may invent")
        return value

    def finished_cm(self, measurement: str) -> float:
        return round(self.body_cm(measurement) + self.fit.ease(measurement), 2)

    def stitches(self, cm: float, *, multiple: int = 1, minimum: int = 1) -> int:
        """The nearest whole number of stitches (in whole `multiple`s) to `cm` at gauge."""
        raw = cm / 10.0 * self.gauge.stitches_per_10cm
        n = max(minimum, int(round(raw / multiple)) * multiple)
        return max(n, multiple)

    def rows(self, cm: float, *, minimum: int = 1) -> int:
        return max(minimum, int(round(cm / 10.0 * self.gauge.rows_per_10cm)))

    def cm_of_stitches(self, n: int) -> float:
        return round(n / self.gauge.stitches_per_10cm * 10.0, 1)

    def cm_of_rows(self, n: int) -> float:
        return round(n / self.gauge.rows_per_10cm * 10.0, 1)


Template = Callable[[GradedSize], CIR]


def _fixed_repeats(cir: CIR) -> list[str]:
    found = []

    def walk(nodes, where):
        for n in nodes:
            if isinstance(n, Repeat):
                if n.times is not None:
                    found.append(where)
                walk(n.ops, where)
    for comp in cir.components:
        for row in comp.rows:
            walk(row.ops, f"{comp.name} row {row.index}")
    return found


@dataclass
class GradedDesign:
    """A design as a function of size.

    `requires` names every body measurement the template reads; a size whose standard does
    not publish one of them is refused before the template runs, so the refusal names the
    missing measurement instead of surfacing as an arithmetic error somewhere in a sleeve.
    """

    key: str
    title: str
    table: BodyTable
    fit: FitIntent
    gauge: Gauge
    template: Template
    requires: tuple[str, ...]
    sizes: tuple[str, ...] | None = None
    primitives: tuple[str, ...] = ("cir.graded",)

    def __post_init__(self) -> None:
        unknown = [m for m in self.requires if m not in MEASUREMENTS]
        if unknown:
            raise GradingRefused(f"{self.key} requires unknown measurements {unknown}")
        if "bust" not in self.requires:
            raise GradingRefused(f"{self.key}: a garment is graded by its chest at least")

    @property
    def size_names(self) -> tuple[str, ...]:
        return self.sizes or self.table.names

    def graded_size(self, size: str) -> GradedSize:
        body = self.table.size(size)
        missing = [m for m in self.requires if not body.is_sourced(m)]
        if missing:
            raise GradingRefused(
                f"{self.key} cannot be graded to size {size}: {missing} UNSOURCED in "
                f"{self.table.name} ({self.table.source_url}). Refused rather than invented")
        return GradedSize(size=size, body=body, fit=self.fit, gauge=self.gauge)

    def sourced_sizes(self) -> tuple[str, ...]:
        """The sizes this design can honestly be graded to."""
        out = []
        for size in self.size_names:
            try:
                self.graded_size(size)
            except GradingRefused:
                continue
            out.append(size)
        return tuple(out)

    def brief_digest(self) -> str:
        brief = {"key": self.key, "table": self.table.source_url,
                 "retrieved": self.table.retrieved, "ease": sorted(self.fit.ease_cm.items()),
                 "gauge": [self.gauge.stitches_per_10cm, self.gauge.rows_per_10cm,
                           self.gauge.stitch_type], "requires": list(self.requires)}
        return hashlib.sha256(json.dumps(brief, sort_keys=True).encode()).hexdigest()[:16]

    def build(self, size: str) -> CIR:
        graded = self.graded_size(size)
        cir = self.template(graded)
        fixed = _fixed_repeats(cir)
        if fixed:
            raise GradingRefused(
                f"{self.key} size {size}: fixed-times repeats in a graded template at "
                f"{fixed}. A repeat count that is right for one size is wrong for the others; "
                f"state the width as a computed stitch count or a to-end repeat")
        if cir.authored != "brambleloop":
            raise GradingRefused(f"{self.key}: a graded Brambleloop design must be authored "
                                 f"as Brambleloop's own")
        if cir.provenance is None:
            cir.provenance = Provenance(
                concept_key=self.key, brief_digest=self.brief_digest(),
                primitives_used=self.primitives, benchmarks_consulted=(),
                generated_by="brambleloop")
        return cir

    def build_all(self) -> dict[str, CIR]:
        return {size: self.build(size) for size in self.sourced_sizes()}

    def size_table(self) -> list[dict]:
        """Per size: each required measurement, body and finished, in cm."""
        rows = []
        for size in self.sourced_sizes():
            g = self.graded_size(size)
            rows.append({"size": size, "measurements": {
                m: {"body_cm": g.body_cm(m), "finished_cm": g.finished_cm(m)}
                for m in self.requires}})
        return rows

    def check_monotonic(self) -> None:
        """Finished chest rises strictly with size; every other measure never falls."""
        table = self.size_table()
        for m in self.requires:
            values = [r["measurements"][m]["finished_cm"] for r in table]
            for i in range(1, len(values)):
                if values[i] < values[i - 1] or (m == "bust" and values[i] == values[i - 1]):
                    raise GradingRefused(
                        f"{self.key}: finished {m} goes from {values[i - 1]} at "
                        f"{table[i - 1]['size']} to {values[i]} at {table[i]['size']}")


# ---- the size table, as a document states it and a reader reads it -----------------------

_LABELS = {m: m.replace("_", " ") for m in MEASUREMENTS}


def write_size_table(design: GradedDesign) -> str:
    """The customer-facing size table. One line per size, in a regular grammar."""
    lines = [f"Sizes ({design.table.name}, {design.table.source_url}, "
             f"read {design.table.retrieved}):"]
    for row in design.size_table():
        parts = [f"{_LABELS[m]} {v['body_cm']:g} cm to fit, {v['finished_cm']:g} cm finished"
                 for m, v in row["measurements"].items()]
        lines.append(f"Size {row['size']}: " + "; ".join(parts) + ".")
    return "\n".join(lines) + "\n"


_SIZE_LINE = re.compile(r"^Size\s+(\S+):\s*(.+?)\.\s*$")
_MEASURE = re.compile(r"([a-z ]+?)\s+([\d.]+)\s+cm\s+to\s+fit,\s+([\d.]+)\s+cm\s+finished")


def parse_size_table(text: str) -> list[dict]:
    """Read a size table back from text alone. Its own grammar; shares nothing with the writer."""
    names = {v: k for k, v in _LABELS.items()}
    out = []
    for raw in text.splitlines():
        m = _SIZE_LINE.match(raw.strip())
        if not m:
            continue
        measures = {}
        for label, body, finished in _MEASURE.findall(m.group(2)):
            key = names.get(label.strip())
            if key is None:
                raise GradingRefused(f"unknown measurement {label!r} in {raw!r}")
            measures[key] = {"body_cm": float(body), "finished_cm": float(finished)}
        out.append({"size": m.group(1), "measurements": measures})
    return out
