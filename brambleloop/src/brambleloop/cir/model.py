"""Crochet Intermediate Representation (CIR) -- the canonical machine-readable pattern.

Master Plan section 2: every product begins as a formal CIR. A beauty image never drives
instructions. The CIR is the single source of truth; written patterns, charts, PDFs and
translations are all *generated downstream* of it, and the reverse compiler proves the
generated text still says what the CIR says.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Iterator, Literal

from . import stitches

Construction = Literal["flat_rows", "joined_rounds", "spiral_rounds"]


# Which loop of the stitch below the hook enters.
#
# Count-neutral by construction: working into the front loop, the back loop or both
# consumes one stitch and produces one either way, so none of the compiler's arithmetic
# changes. What changes is the fabric. A half double crochet worked in the back loop leaves
# the front loop lying on the surface as a horizontal bar, and alternating the two across a
# row and offsetting them between rows is how textured stitch patterns exist at all.
#
# Added 2026-09-24 after the benchmark cardigan: its entire visual identity is alternating
# BLO/FLO half doubles, and the CIR could represent every stitch count in the garment
# exactly while being unable to say the one thing that makes it look like itself. A
# representation that is count-perfect and texture-blind passes every gate and renders the
# wrong fabric -- which is the same defect as a name claiming what the pattern does not do.
LoopTarget = Literal["both", "front", "back"]


@dataclass
class Op:
    """One operation in a row: a stitch repeated `count` times in consecutive stitches."""

    stitch: str
    count: int = 1
    note: str | None = None
    loop: LoopTarget = "both"
    # How many stitches of the row below this op BRIDGES rather than adds to.
    #
    # A chain is the only stitch whose width depends on what it is doing. Chained across a
    # gap -- an armhole, a buttonhole, a lace space over skipped stitches -- it occupies the
    # width of the stitches it replaced and adds nothing of its own. Chained into open air at
    # the start of a row it creates new fabric. The CIR counted every chain as producing one
    # unit of width, so a bridged opening measured as if the chains had been added to the row
    # instead of laid across it.
    #
    # Measured on the benchmark garment before this existed: the body came out +1.11% too
    # wide at XS and +1.02% at 5XL, because a 27-chain armhole bridge was counted as 27 units
    # of width on top of the 64 worked stitches instead of spanning the 26 it replaced.
    #
    # `spans=0` means "this chain adds its own width", which is the honest default: a chain
    # that bridges nothing is a chain that makes fabric.
    spans: int = 0

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
    # How many of the previous row's stitches this row does not work, because they are on
    # hold. A yoke worked in rounds splits here: the sleeve stitches wait while the body
    # continues over the rest. Without it the compiler sees a row consuming 96 of 144 and
    # calls it an underrun, which is why no garment construction could be expressed.
    skips: int = 0

    def __post_init__(self) -> None:
        if not self.ops:
            raise ValueError(f"row {self.index} has no operations")
        if self.turning_chain < 0:
            raise ValueError(f"row {self.index} turning_chain must be >= 0")
        if self.skips < 0:
            raise ValueError(f"row {self.index} skips must be >= 0")


@dataclass
class Gauge:
    stitches_per_10cm: float
    rows_per_10cm: float
    stitch_type: str = "sc"
    hook_mm: float | None = None
    yarn_weight: str | None = None
    # Chains are narrower than the worked stitches they sit beside, so a run of chain spaces
    # measured at stitch gauge is measured at the wrong gauge. The benchmark garment's own
    # numbers imply 17.6-19.7 chains per 10cm against 14.5 for its worked fabric -- roughly
    # 20-35% narrower. Optional, because most patterns never state it; when it is absent,
    # anything that would have to assume it says so instead of guessing.
    chains_per_10cm: float | None = None
    # How well that chain gauge is known, as a relative figure. Zero means the designer
    # stated it and it is exact. A non-zero value means it was solved out of the pattern's
    # own numbers, which is evidence rather than measurement: the benchmark garment's nine
    # sizes imply 17.6-19.7 chains per 10cm around a midpoint of 18.4, about six percent
    # either way. Anything computed from an uncertain gauge inherits that uncertainty, and a
    # check whose result falls inside it cannot tell pass from fail -- so it must say so
    # instead of picking whichever it happens to land on.
    chain_gauge_uncertainty: float = 0.0

    def __post_init__(self) -> None:
        if self.stitches_per_10cm <= 0 or self.rows_per_10cm <= 0:
            raise ValueError("gauge must be positive")


# The closed vocabulary a fibre content may draw from.
#
# Closed for the reason every other vocabulary in this schema is closed: an open field
# accepts "soft yarn", and a composition statement whose fibre word nobody recognises cannot
# be checked, substituted against, or printed to a buyer who is choosing for a baby.
#
# **It is deliberately the same seventeen words `publish.substitution.FIBRE_CLASSES` already
# uses**, so that there is one definition in this company of what a fibre word is. The
# schema cannot import `publish` -- `publish` reads `cir`, and the arrow must not turn round
# -- so this is a second copy of one fact, which is the drift this repository keeps meeting.
# `tests/test_cir_fibre.py::test_the_two_fibre_vocabularies_are_the_same_seventeen_words` fails
# the moment they disagree, and the diff that deletes the copy (deriving `FIBRE_CLASSES`
# from here) is written out for the owner of `publish/substitution.py` in
# `research/VISUAL_GOVERNANCE.md`.
#
# `microfibre`/`microfiber` are one fibre under two spellings, and `merino` is a wool named
# as its own word. Both are how the existing table reads, and correcting the taxonomy here
# would silently put this field out of step with the module that already reads fibres for
# the substitution guidance.
FIBRES: tuple[str, ...] = (
    "acrylic", "alpaca", "bamboo", "cashmere", "cotton", "hemp", "linen", "merino",
    "microfiber", "microfibre", "mohair", "nylon", "polyester", "ramie", "silk", "wool",
    "yak",
)


@dataclass
class Material:
    """One yarn the pattern is written for.

    `fibre_content` is what the *source* states about this yarn's composition, as
    `(fibre, percent)` pairs summing to 100 -- `(("cotton", 55), ("linen", 45))`.

    **It defaults to empty and an empty value means "not stated", never "no fibre
    concerns".** That direction is the whole point of the field. `publish/substitution.py`
    reads a fibre *class* out of `name` ("worsted acrylic" -> synthetic) and
    `publish/pdf.fibres_named` reads a fibre *word* out of the same field, and both are
    honest readings of a yarn description -- but a yarn description is not a composition.
    "worsted acrylic" is not "100% acrylic", and nothing may upgrade one into the other.
    So this field is populated only where the fact is genuinely known from a source that
    states it, and a consumer that needs a composition refuses when it is empty rather than
    inferring one from the name.

    None of the eleven Launch-0 CIRs states it today, and none is given a value here: their
    materials are generic yarn descriptions (`"worsted acrylic"`, `"dk cotton"`) with no
    manufacturer, no product and no ball band behind them, so there is no source to read a
    composition from. Writing `(("acrylic", 100),)` because the word "acrylic" appears is
    exactly the inference this field exists to make unnecessary.
    """

    name: str
    yarn_weight: str | None = None
    colorway: str | None = None
    metres_estimate: float | None = None
    color_id: str | None = None
    fibre_content: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        # Normalised here rather than trusted, because this arrives three ways: typed by a
        # product module, round-tripped through `CIR.from_dict` (where JSON has turned every
        # tuple into a list), and read back off a document. A field validated in one of the
        # three is a field validated in none.
        raw = self.fibre_content or ()
        if isinstance(raw, dict):  # a mapping is an ordering nobody declared
            raise ValueError(
                f"material {self.name!r}: fibre_content must be a sequence of "
                f"(fibre, percent) pairs, not a mapping -- the order is what a buyer reads")
        pairs: list[tuple[str, int]] = []
        seen: set[str] = set()
        for item in raw:
            try:
                fibre, percent = item
            except (TypeError, ValueError):
                raise ValueError(
                    f"material {self.name!r}: {item!r} is not a (fibre, percent) pair"
                ) from None
            fibre = str(fibre).strip().lower()
            if fibre not in FIBRES:
                raise ValueError(
                    f"material {self.name!r}: {fibre!r} is not a fibre this schema knows. "
                    f"The vocabulary is closed on purpose: a composition nobody can check "
                    f"is not a composition. Known: {list(FIBRES)}")
            if fibre in seen:
                raise ValueError(
                    f"material {self.name!r}: {fibre!r} is stated twice. One fibre, one "
                    f"percentage, or the total is arithmetic nobody can follow")
            # `bool` is an `int` in Python and `True` would silently become 1%.
            if isinstance(percent, bool) or not isinstance(percent, int):
                raise ValueError(
                    f"material {self.name!r}: the percentage for {fibre!r} is "
                    f"{percent!r}; fibre content is stated in whole percent")
            if not 1 <= percent <= 100:
                raise ValueError(
                    f"material {self.name!r}: {fibre!r} at {percent}% is outside 1..100")
            seen.add(fibre)
            pairs.append((fibre, percent))
        if pairs and sum(p for _, p in pairs) != 100:
            raise ValueError(
                f"material {self.name!r}: fibre content sums to "
                f"{sum(p for _, p in pairs)}%, not 100%. A composition that does not "
                f"account for the whole yarn is a composition with something unstated in "
                f"it, and the unstated part is exactly what a buyer with an allergy needs")
        # Descending by percentage, ties broken alphabetically. Two reasons, both about one
        # fact having one representation. `CIR.fingerprint` hashes `to_dict` and is the
        # pipeline's idempotency key, so declaration order would give one design two
        # fingerprints and re-run certification for nothing. And descending order by weight
        # is how a composition is customarily written, so the document gets the customary
        # form without the writer deciding it in a second place.
        self.fibre_content = tuple(sorted(pairs, key=lambda p: (-p[1], p[0])))

    @property
    def states_fibre_content(self) -> bool:
        """True only when the source stated a composition. Empty is not a clean bill."""
        return bool(self.fibre_content)


@dataclass(frozen=True)
class Hold:
    """Stitches set aside at a row, for another component to resume.

    `at_row` is the row of *this* component whose stitches are held, and `count` is how many.
    Where they sit is recorded because a sleeve held from the centre back is a different
    garment from one held from the front, and a pattern that does not say produces a maker
    guessing -- the failure the Execution Directive forbids, arriving through assembly.
    """

    name: str
    at_row: int
    count: int
    from_stitch: int = 0
    note: str | None = None

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError(f"hold {self.name!r} must hold at least one stitch")
        if self.from_stitch < 0:
            raise ValueError(f"hold {self.name!r} from_stitch must be >= 0")

    @property
    def spans(self) -> tuple[int, int]:
        return (self.from_stitch, self.from_stitch + self.count)


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
    # Stitches this component sets aside for another component to pick up, and the hold this
    # component itself starts from. Together they are the armhole division, which is the one
    # primitive every garment construction needs and the CIR did not have.
    #
    # Declared rather than implied, because "place 24 sts on hold for the sleeve" is a
    # promise, and a promise nobody checks is how a pattern ships with stitches that are
    # never worked again. The compiler checks that every hold is resumed exactly once and
    # that the component resuming it starts on exactly that many stitches.
    holds: list[Hold] = field(default_factory=list)
    resumes: str | None = None
    # Which way this panel's rows run on the finished object.
    #
    # "up" means rows stack from hem to shoulder, the ordinary bottom-up panel. "across"
    # means the piece is worked side to side: the foundation chain runs the length of the
    # garment and the rows stack around the body. The stitch counts are identical either
    # way, which is why the CIR could describe a side-to-side cardigan perfectly and still
    # not know which way its fabric ran.
    #
    # It matters because texture has a direction. Row boundaries and any ridge that follows a
    # row are lines parallel to the rows, so a side-to-side panel shows them running
    # vertically on the worn garment and a bottom-up panel shows them running horizontally.
    # That is the single most visible property of a textured garment in a photograph, and
    # without this field nothing downstream may claim it in either direction.
    grain: Literal["up", "across"] = "up"

    @property
    def rows_run_vertically_on_the_body(self) -> bool:
        """True when this panel's rows appear as vertical lines on the worn garment."""
        return self.grain == "across"

    def __post_init__(self) -> None:
        if self.make < 1:
            raise ValueError(f"component {self.name!r} make must be >= 1")
        if self.foundation < 0:
            raise ValueError(f"component {self.name!r} foundation must be >= 0")
        names = [h.name for h in self.holds]
        if len(names) != len(set(names)):
            raise ValueError(f"component {self.name!r} has duplicate hold names: {names}")


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
    # Where on `piece_b` the join happens. A stuffed toy is not made by knowing that the ear
    # attaches to the head; it is made by knowing the ear attaches across rounds 4 to 6,
    # six stitches either side of the centre. Without that a multi-piece pattern is a set of
    # correct pieces and a photograph the maker has to reverse-engineer -- which is the
    # "beauty image and guess the instructions" failure the Execution Directive forbids,
    # arriving through the back door of an unspecified assembly step.
    at_round: int | None = None
    spans_rounds: int = 1
    stitches_from_centre: int | None = None
    mirrored: bool = False
    # WHICH EDGE of each piece the join runs along.
    #
    # `at_round` places a join on a piece worked in rounds; a flat piece has no rounds, so
    # until now nothing could say that a sleeve's top edge meets a body's side edge. Naming
    # the edges is what turns a set of correct rectangles into an object with a shape: it
    # gives every join a length on both sides, and two edges that are supposed to be sewn
    # together and are not the same length is a garment that cannot be assembled.
    #
    # Deliberately generic rather than garment vocabulary. A basket's side joins its base,
    # a blanket's border joins its centre, a bag's gusset joins its front: all of them are
    # one piece's edge meeting another's, and none of them needs a word like "armhole".
    # "opening" is a hole the construction makes -- an armhole, a buttonhole, the mouth of a
    # bag -- rather than one of the piece's outer edges. It exists because the first attempt
    # at this vocabulary could only name the four sides of a rectangle, and a sleeve does not
    # join the side of a body panel: it joins a slit inside it. A join targeting an outer
    # edge when it means an opening compares the wrong two lengths and reports a garment
    # that assembles perfectly well as impossible.
    edge_a: Literal["top", "bottom", "left", "right",
                    "fold", "perimeter", "opening"] | None = None
    edge_b: Literal["top", "bottom", "left", "right",
                    "fold", "perimeter", "opening"] | None = None

    @property
    def names_its_edges(self) -> bool:
        return self.edge_a is not None and self.edge_b is not None

    @property
    def is_self_seam(self) -> bool:
        return self.piece_a == self.piece_b

    @property
    def is_placed(self) -> bool:
        """True when this seam says where on the piece it happens."""
        return self.at_round is not None


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
    # Who wrote this design, which decides what it is allowed to leave unsaid.
    #
    # A `benchmark` CIR is Brambleloop's record of somebody else's pattern, and it must be
    # allowed to be as incomplete as its source: the purchased cardigan gives pocket
    # placement only in a photograph, and inventing a number to make the record look
    # complete would be falsifying the benchmark. A `brambleloop` design has no such excuse,
    # because we control its specification -- so it must state every fact needed to
    # reconstruct the finished object, and `specification.reconstructive_gaps` refuses it if
    # it does not.
    #
    # Defaults to `brambleloop`, so a new design is held to the standard unless it is
    # explicitly declared a record of someone else's work. Failing closed is the point: the
    # easy mistake is a product that quietly inherits a benchmark's permission to be vague.
    authored: Literal["brambleloop", "benchmark"] = "brambleloop"
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

    @property
    def fingerprint(self) -> str:
        """A short content hash of the whole design.

        Exists because a slug and a version are not enough to identify a design. The
        pipeline keyed its work as `draft:{slug}` -- once per slug, forever -- so when a
        product was re-engineered, the new design could never enter the chain: the draft job
        was already done, the compile key was taken, and certification never re-ran. Two
        products stayed in production under their old flat-panel designs and their old
        titles while the repository held the corrected ones.

        Putting the design's own hash in the key makes the work re-run exactly when the
        design changes and not otherwise, which is what idempotency was supposed to mean.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

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
