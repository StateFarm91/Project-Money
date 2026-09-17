"""Crochet Intermediate Representation (CIR) -- the canonical machine-readable pattern.

Master Plan section 2: every product begins as a formal CIR. A beauty image never drives
instructions. The CIR is the single source of truth; written patterns, charts, PDFs and
translations are all *generated downstream* of it, and the reverse compiler proves the
generated text still says what the CIR says.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Iterator, Literal

from . import stitches

Construction = Literal["flat_rows", "joined_rounds", "spiral_rounds"]


@dataclass
class Op:
    """One operation in a row: a stitch repeated `count` times in consecutive stitches."""

    stitch: str
    count: int = 1
    note: str | None = None

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError(f"op count must be >= 1, got {self.count}")
        stitches.get(self.stitch)  # validate eagerly

    @property
    def consumes(self) -> int:
        return stitches.get(self.stitch).consumes * self.count

    @property
    def produces(self) -> int:
        return stitches.get(self.stitch).produces * self.count


@dataclass
class Repeat:
    """A bracketed repeat: [ops] x times, or [ops] to end.

    `times=None` means "repeat to end of row", which the compiler resolves against the
    available stitch count. A to-end repeat that does not divide evenly is an error unless
    the row explicitly declares a remainder.
    """

    ops: list["OpNode"]
    times: int | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.times is not None and self.times < 1:
            raise ValueError(f"repeat times must be >= 1 or None, got {self.times}")
        if not self.ops:
            raise ValueError("repeat must contain at least one op")

    @property
    def unit_consumes(self) -> int:
        return sum(o.consumes for o in self.ops)

    @property
    def unit_produces(self) -> int:
        return sum(o.produces for o in self.ops)

    @property
    def consumes(self) -> int:
        if self.times is None:
            raise UnresolvedRepeat("to-end repeat has no fixed consumption until compiled")
        return self.unit_consumes * self.times

    @property
    def produces(self) -> int:
        if self.times is None:
            raise UnresolvedRepeat("to-end repeat has no fixed production until compiled")
        return self.unit_produces * self.times


class UnresolvedRepeat(RuntimeError):
    pass


OpNode = Op | Repeat


@dataclass
class Row:
    """One row or round.

    `declared_count` is what the designer says the stitch count is. The compiler computes it
    independently and fails on mismatch -- that disagreement is the single most valuable
    error signal in the whole system, because it is exactly the bug a maker hits at row 40.
    """

    index: int
    ops: list[OpNode]
    declared_count: int | None = None
    turning_chain: int = 0
    turning_chain_counts: bool = False
    color: str | None = None
    into: int | None = None  # row index worked into; default = previous row
    allow_remainder: bool = False
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.ops:
            raise ValueError(f"row {self.index} has no operations")
        if self.turning_chain < 0:
            raise ValueError(f"row {self.index} turning_chain must be >= 0")


@dataclass
class Gauge:
    stitches_per_10cm: float
    rows_per_10cm: float
    stitch_type: str = "sc"
    hook_mm: float | None = None
    yarn_weight: str | None = None

    def __post_init__(self) -> None:
        if self.stitches_per_10cm <= 0 or self.rows_per_10cm <= 0:
            raise ValueError("gauge must be positive")


@dataclass
class Material:
    name: str
    yarn_weight: str | None = None
    colorway: str | None = None
    metres_estimate: float | None = None
    color_id: str | None = None


@dataclass
class Component:
    """A separately-worked piece (a sleeve, a motif, a granny square).

    `foundation_kind` distinguishes a foundation chain from a magic ring so the writer emits
    "6 sc in magic ring" rather than the nonsensical "sc in next 6 sts" for a round that has
    no previous fabric to work into.
    """

    name: str
    construction: Construction
    rows: list[Row]
    foundation: int = 0
    foundation_kind: Literal["chain", "magic_ring", "none"] = "chain"
    make: int = 1
    note: str | None = None

    def __post_init__(self) -> None:
        if self.make < 1:
            raise ValueError(f"component {self.name!r} make must be >= 1")
        if self.foundation < 0:
            raise ValueError(f"component {self.name!r} foundation must be >= 0")


SeamMethod = Literal["whipstitch", "slst", "mattress", "sew"]


@dataclass
class Seam:
    """One join in the finishing: which pieces, by what method, in what order.

    Without this a multi-piece pattern is a bag of rectangles and a wish. The catalogue
    shipped exactly that once -- a "Market Basket Trio" whose CIR was one flat panel, with a
    designer note saying it was "the side panel, seamed into the basket" and no seaming
    instruction anywhere in the document (B-059).

    `piece_a == piece_b` is a self-seam: the two edges of one panel joined to each other,
    which is how a flat rectangle legitimately becomes a tube.
    """

    method: SeamMethod
    piece_a: str
    piece_b: str
    note: str | None = None
    stuff_before_closing: bool = False

    @property
    def is_self_seam(self) -> bool:
        return self.piece_a == self.piece_b


@dataclass
class CIR:
    """The canonical pattern object."""

    slug: str
    title: str
    version: str
    construction: Construction
    components: list[Component]
    gauge: Gauge | None = None
    materials: list[Material] = field(default_factory=list)
    colors: dict[str, str] = field(default_factory=dict)
    risk_class: Literal["A", "B", "C"] = "A"
    designer_notes: str | None = None
    finished_size_note: str | None = None
    assembly: list[Seam] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.components:
            raise ValueError("CIR must have at least one component")
        names = [c.name for c in self.components]
        if len(names) != len(set(names)):
            raise ValueError(f"component names must be unique, got {names}")

    @property
    def makes_a_closed_form(self) -> bool:
        """True when the finishing turns the pieces into one three-dimensional object.

        A flat panel is a flat panel until something joins it. This is what a name like
        "basket" or "bag" has to be able to point at.
        """
        return bool(self.assembly)

    def iter_rows(self) -> Iterator[tuple[Component, Row]]:
        for comp in self.components:
            for row in comp.rows:
                yield comp, row

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, **kw: Any) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, **kw)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "CIR":
        def node(x: dict[str, Any]) -> OpNode:
            if "stitch" in x:
                return Op(stitch=x["stitch"], count=x.get("count", 1), note=x.get("note"))
            return Repeat(
                ops=[node(o) for o in x["ops"]], times=x.get("times"), note=x.get("note")
            )

        comps = [
            Component(
                name=c["name"],
                construction=c["construction"],
                foundation=c.get("foundation", 0),
                foundation_kind=c.get("foundation_kind", "chain"),
                make=c.get("make", 1),
                note=c.get("note"),
                rows=[
                    Row(
                        index=r["index"],
                        ops=[node(o) for o in r["ops"]],
                        declared_count=r.get("declared_count"),
                        turning_chain=r.get("turning_chain", 0),
                        turning_chain_counts=r.get("turning_chain_counts", False),
                        color=r.get("color"),
                        into=r.get("into"),
                        allow_remainder=r.get("allow_remainder", False),
                        note=r.get("note"),
                    )
                    for r in c["rows"]
                ],
            )
            for c in d["components"]
        ]
        return CIR(
            slug=d["slug"],
            title=d["title"],
            version=d["version"],
            construction=d["construction"],
            components=comps,
            gauge=Gauge(**d["gauge"]) if d.get("gauge") else None,
            materials=[Material(**m) for m in d.get("materials", [])],
            colors=d.get("colors", {}),
            risk_class=d.get("risk_class", "A"),
            designer_notes=d.get("designer_notes"),
            finished_size_note=d.get("finished_size_note"),
            assembly=[Seam(**seam) for seam in d.get("assembly", [])],
        )

    @staticmethod
    def from_json(s: str) -> "CIR":
        return CIR.from_dict(json.loads(s))
