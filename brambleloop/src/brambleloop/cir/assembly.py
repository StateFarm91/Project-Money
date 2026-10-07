"""The finished object's spatial relationships, derived from the pieces and their joins.

A compiled CIR gives correct pieces. It does not, by itself, give an object: a sleeve and a
body are two rectangles until something says which edge of one meets which edge of the other
and how long each of those edges is. That is what this module computes, deterministically,
from the stitch counts and gauge already certified -- never from a photograph and never from
a model's opinion about how cardigans usually go together.

Two things it is careful about.

**Grain decides which way a panel lies.** A panel's stitch direction and row direction are
fixed by how it was worked, and which of those runs up the finished object depends on the
panel's grain. A side-to-side body 90 stitches by 81 rows is 62cm tall and 85cm around; the
same counts worked bottom-up would be 62cm around and 85cm tall, which is a different
garment. Reading the counts without the grain gets the object's proportions transposed.

**A join has a length on both sides, and they have to agree.** Two edges sewn together must
be the same length or the pieces do not go together, however correct each piece is alone.
This is the general form of the sleeve-into-armhole check: it applies equally to a basket's
side meeting its base and a blanket's border meeting its centre, and it is the cheapest
structural falsification available -- it needs no render and no judgement.

Nothing here is garment vocabulary. Pieces, edges, joins and footprints describe a blanket,
a basket, a bag or a bear as readily as a cardigan, which is the point: the benchmark is a
cardigan but the architecture must not be.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# How close two joined edges must be in length before the join is called sound.
#
# Six percent, matching the tolerance the benchmark's own sleeve-into-armhole check uses.
# Crochet fabric eases: a slightly shorter edge stretches to meet a slightly longer one and
# the seam is invisible. Ten percent does not ease, it gathers, and a gathered seam that was
# meant to be flat is a visible defect in a photograph.
EDGE_TOLERANCE = 0.06


@dataclass(frozen=True)
class Footprint:
    """One piece's finished extent, in the object's own axes rather than the fabric's."""

    piece: str
    across_cm: float          # horizontally on the finished object
    up_cm: float              # vertically on the finished object
    grain: str
    copies: int = 1
    # Openings the construction makes inside this piece, by span length in cm. An armhole is
    # a slit, so what another piece sews into is its PERIMETER: twice the span.
    openings: tuple[float, ...] = ()
    # The height of one row of this piece, in cm, when it is worked in flat rows. A join
    # PLACED across rows a-b of a piece (a sleeve sewn to the body's side across the rows
    # around the shoulder line) is as long as those rows, not as the whole edge.
    row_cm: float | None = None

    def placed_edge_cm(self, edge: str, spans_rows: int) -> float | None:
        """The length of `spans_rows` rows of a side edge, or None where that has no meaning.

        Rows stack along the edges that run across them: left/right on a piece whose grain
        is "up", top/bottom on one worked "across". A placement on any other edge, or on a
        piece not worked in flat rows, is not a length this can state.
        """
        if self.row_cm is None:
            return None
        along = ("left", "right") if self.grain == "up" else ("top", "bottom")
        if edge not in along:
            return None
        return spans_rows * self.row_cm

    def edge_cm(self, edge: str) -> float | None:
        """The length of one named edge. `fold` is the across-axis; `perimeter` the whole."""
        return {
            "top": self.across_cm, "bottom": self.across_cm, "fold": self.across_cm,
            "left": self.up_cm, "right": self.up_cm,
            "perimeter": 2 * (self.across_cm + self.up_cm),
            # A slit's two sides both take stitches, so the length sewn is twice the span.
            "opening": (2 * self.openings[0]) if self.openings else None,
        }.get(edge)


@dataclass
class Join:
    method: str
    piece_a: str
    piece_b: str
    edge_a: str | None
    edge_b: str | None
    length_a_cm: float | None = None
    length_b_cm: float | None = None
    # sound | mismatched | indeterminate | unchecked
    #
    # `indeterminate` is the one that stops this being a coin flip. When an edge length was
    # derived from an uncertain gauge, a discrepancy smaller than that uncertainty is not
    # evidence of a bad join -- and calling it either way would be a verdict the measurement
    # cannot support, which is the defect this codebase has spent its whole life catching.
    verdict: str = "unchecked"
    why: str = ""


@dataclass
class ObjectGeometry:
    footprints: dict[str, Footprint] = field(default_factory=dict)
    joins: list[Join] = field(default_factory=list)
    silhouette_across_cm: float | None = None
    silhouette_up_cm: float | None = None
    verdict: str = "unassembled"
    why: str = ""

    @property
    def unchecked_joins(self) -> list[Join]:
        return [j for j in self.joins if j.verdict == "unchecked"]

    @property
    def mismatched_joins(self) -> list[Join]:
        return [j for j in self.joins if j.verdict == "mismatched"]

    @property
    def indeterminate_joins(self) -> list[Join]:
        return [j for j in self.joins if j.verdict == "indeterminate"]

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict, "why": self.why,
            "silhouette_across_cm": self.silhouette_across_cm,
            "silhouette_up_cm": self.silhouette_up_cm,
            "pieces": {n: {"across_cm": round(f.across_cm, 1), "up_cm": round(f.up_cm, 1),
                           "grain": f.grain, "copies": f.copies}
                       for n, f in sorted(self.footprints.items())},
            "joins": [{"a": f"{j.piece_a}.{j.edge_a or '?'}",
                       "b": f"{j.piece_b}.{j.edge_b or '?'}",
                       "length_a_cm": None if j.length_a_cm is None else round(j.length_a_cm, 1),
                       "length_b_cm": None if j.length_b_cm is None else round(j.length_b_cm, 1),
                       "verdict": j.verdict, "why": j.why} for j in self.joins],
        }


def openings_cm(component, gauge) -> tuple[float, ...]:
    """Spans of the openings this piece's construction makes, from its bridge chains.

    A bridged opening's length is the length of the chains laid across it, and chains are
    measured at chain gauge -- the primitive that exists because measuring them at stitch
    gauge is what made bridged openings wrong in the first place. When the gauge states no
    chain gauge the span falls back to the stitches the chains replaced, which is the right
    answer to within the difference between the two gauges rather than a guess.
    """
    out: list[float] = []
    for row in component.rows:
        for op in row.ops:
            spans = getattr(op, "spans", 0)
            if getattr(op, "stitch", None) != "ch" or not spans:
                continue
            if gauge and gauge.chains_per_10cm:
                out.append(op.count / gauge.chains_per_10cm * 10.0)
            elif gauge:
                out.append(spans / gauge.stitches_per_10cm * 10.0)
    return tuple(out)


def footprint(component, twin, gauge=None) -> Footprint:
    """One piece's extent on the finished object, from its fabric size and its grain.

    The twin measures fabric: `width_cm` along the stitch direction, `height_cm` along the
    rows. Which of those runs up the object is exactly what grain records, so this is the
    one place the two coordinate systems meet.
    """
    w, h = twin.width_cm, twin.height_cm
    if w is None or h is None:
        raise ValueError(f"{component.name}: no finished size, so it cannot be placed")
    across, up = (w, h) if component.grain == "up" else (h, w)
    row_cm = None
    if component.construction == "flat_rows" and component.rows:
        row_cm = h / len(component.rows)
    return Footprint(piece=component.name, across_cm=across, up_cm=up,
                     grain=component.grain, copies=component.make,
                     openings=openings_cm(component, gauge), row_cm=row_cm)


# The two edges a closed band's self-seam joins, by grain: its rows' ends (a band along its
# rows) or its stitch columns' ends (a band along its stitches). W4-CAND.
BAND_EDGES = {("up", "rows"): {"bottom", "top"}, ("up", "stitches"): {"left", "right"},
              ("across", "rows"): {"left", "right"}, ("across", "stitches"): {"bottom", "top"}}
# A threaded piece passes through when its girth is at most this share of the inside it goes
# through: room to pull it, not a press fit.
THREAD_ROOM = 0.5


def band_axis(cir, comp) -> str | None:
    """"rows" or "stitches" when this flat piece's two ends along that axis are sewn to each
    other (a self-seam of those two opposite edges): a closed band. Else None."""
    if comp.construction != "flat_rows":
        return None
    for s in cir.assembly:
        if s.piece_a == s.piece_b == comp.name:
            for (grain, axis), edges in BAND_EDGES.items():
                if grain == comp.grain and {s.edge_a, s.edge_b} == edges:
                    return axis
    return None


def band_length_cm(comp, twin, axis: str) -> float | None:
    """A closed band's length around (its inside), from its twin."""
    if twin.width_cm is None or twin.height_cm is None:
        return None
    return twin.height_cm if axis == "rows" else twin.width_cm


def first_round_cm(twin, gauge) -> float | None:
    """The circumference of a round piece's first round: what is worked into an opening."""
    if not twin.row_widths or gauge is None:
        return None
    return twin.row_widths[min(twin.row_widths)] * 10.0 / gauge.stitches_per_10cm


def _picked_up_only(cir, comp) -> bool:
    """A round piece begun inside another (foundation 'none') and joined only by pick-up: its
    finished shape may be refused (a closed tip is shaped by tension), but its first round is
    still a length, so the joins it takes part in can be measured."""
    joins = [s for s in cir.assembly if comp.name in (s.piece_a, s.piece_b)]
    return (comp.construction != "flat_rows" and comp.foundation_kind == "none" and bool(joins)
            and all(s.method == "pick_up" and s.piece_a == comp.name for s in joins))


def assemble(cir, twins: dict) -> ObjectGeometry:
    """Place every piece and check every join. Renders nothing and calls no model.

    `twins` maps component name to its built `TwinModel`.
    """
    geo = ObjectGeometry()
    for comp in cir.components:
        t = twins.get(comp.name)
        if t is None:
            continue
        try:
            geo.footprints[comp.name] = footprint(comp, t, cir.gauge)
        except ValueError as exc:
            if _picked_up_only(cir, comp) and first_round_cm(t, cir.gauge):
                continue        # measured by its first round in the join below
            geo.verdict, geo.why = "unmeasurable", str(exc)
            return geo

    for seam in cir.assembly:
        fa, fb = geo.footprints.get(seam.piece_a), geo.footprints.get(seam.piece_b)
        join = Join(method=seam.method, piece_a=seam.piece_a, piece_b=seam.piece_b,
                    edge_a=seam.edge_a, edge_b=seam.edge_b)
        if seam.is_self_seam:
            # A piece joined to itself is a fold, not a mismatch: its two edges are the same
            # edge and comparing them to each other proves nothing.
            join.verdict, join.why = "sound", "self-seam: one piece folded and closed"
        elif seam.method == "thread":
            _thread_join(cir, seam, join, fa, fb, twins)
        elif not seam.names_its_edges:
            join.why = ("this join does not say which edges meet, so no length can be "
                        "compared and the pieces cannot be placed relative to each other")
        elif (seam.method == "pick_up" and fb is not None and seam.piece_a in twins
              and next(c for c in cir.components if c.name == seam.piece_a).construction
              != "flat_rows"):
            # Round 1 of a round piece is worked into the edge: its circumference is the
            # length that meets it, whatever the finished piece's own span.
            _measure(cir, seam, join, first_round_cm(twins[seam.piece_a], cir.gauge),
                     fb.edge_cm(seam.edge_b))
        elif fa is None or fb is None:
            join.why = "one of the pieces has no measured footprint"
        else:
            la, lb = fa.edge_cm(seam.edge_a), fb.edge_cm(seam.edge_b)
            # A join placed across particular rows of piece_b runs along those rows only.
            if seam.at_round is not None:
                placed = fb.placed_edge_cm(seam.edge_b, seam.spans_rounds)
                if placed is not None:
                    lb = placed
            join.length_a_cm, join.length_b_cm = la, lb
            if la is None or lb is None:
                join.why = "an edge name has no length on its piece"
            else:
                drift = abs(la - lb) / max(la, lb)
                # An opening's length comes from the chain gauge, so it carries whatever
                # uncertainty that gauge has.
                unsure = 0.0
                if "opening" in (seam.edge_a, seam.edge_b) and cir.gauge:
                    unsure = getattr(cir.gauge, "chain_gauge_uncertainty", 0.0) or 0.0
                if drift <= EDGE_TOLERANCE:
                    join.verdict = "sound"
                    join.why = f"edges agree within {drift:.1%}"
                elif drift <= EDGE_TOLERANCE + unsure:
                    join.verdict = "indeterminate"
                    join.why = (f"{la:.1f}cm against {lb:.1f}cm is a {drift:.1%} difference, "
                                f"but the opening was derived from a chain gauge known only "
                                f"to ±{unsure:.0%}, so this cannot tell a real mismatch from "
                                f"the gauge being off. It needs a stated chain gauge, not a "
                                f"verdict")
                else:
                    join.verdict = "mismatched"
                    join.why = (f"{seam.piece_a}.{seam.edge_a} is {la:.1f}cm and "
                                f"{seam.piece_b}.{seam.edge_b} is {lb:.1f}cm, a "
                                f"{drift:.1%} difference: these do not sew together")
        geo.joins.append(join)

    _silhouette(cir, geo)
    if geo.mismatched_joins:
        geo.verdict = "does_not_assemble"
        geo.why = geo.mismatched_joins[0].why
    elif geo.indeterminate_joins:
        geo.verdict = "partially_placed"
        geo.why = geo.indeterminate_joins[0].why
    elif geo.unchecked_joins:
        geo.verdict = "partially_placed"
        geo.why = (f"{len(geo.unchecked_joins)} of {len(geo.joins)} joins do not name their "
                   f"edges, so the object's shape is only partly determined")
    elif not geo.joins:
        geo.verdict = "unassembled"
        geo.why = "no joins, so these pieces are not yet one object"
    else:
        geo.verdict = "assembles"
        geo.why = "every join names its edges and every pair of edges agrees in length"
    return geo


def _measure(cir, seam, join: Join, la: float | None, lb: float | None) -> None:
    """Two edge lengths compared as `assemble` compares every join."""
    join.length_a_cm, join.length_b_cm = la, lb
    if la is None or lb is None:
        join.why = "an edge name has no length on its piece"
        return
    drift = abs(la - lb) / max(la, lb)
    unsure = 0.0
    if "opening" in (seam.edge_a, seam.edge_b) and cir.gauge:
        unsure = getattr(cir.gauge, "chain_gauge_uncertainty", 0.0) or 0.0
    if drift <= EDGE_TOLERANCE:
        join.verdict, join.why = "sound", f"edges agree within {drift:.1%}"
    elif drift <= EDGE_TOLERANCE + unsure:
        join.verdict = "indeterminate"
        join.why = (f"{la:.1f}cm against {lb:.1f}cm is a {drift:.1%} difference inside the "
                    f"chain gauge's ±{unsure:.0%}")
    else:
        join.verdict = "mismatched"
        join.why = (f"{seam.piece_a}.{seam.edge_a} is {la:.1f}cm and {seam.piece_b}."
                    f"{seam.edge_b} is {lb:.1f}cm, a {drift:.1%} difference: these do not "
                    f"join")


def _thread_join(cir, seam, join: Join, fa, fb, twins) -> None:
    """A piece passed through a closed band or an opening: it must fit, with room.

    The threaded piece's girth is twice the edge that leads it through (a flat strip's two
    faces); the inside is a closed band's length around, or an opening's perimeter."""
    comps = {c.name: c for c in cir.components}
    if fa is None or fb is None or seam.edge_a not in ("left", "right", "top", "bottom"):
        join.why = "a threaded join needs the threaded piece's leading edge and a measured inside"
        return
    girth = 2 * fa.edge_cm(seam.edge_a)
    axis = band_axis(cir, comps[seam.piece_b])
    inside = (band_length_cm(comps[seam.piece_b], twins[seam.piece_b], axis) if axis
              else fb.edge_cm("opening"))
    join.length_a_cm, join.length_b_cm = girth, inside
    if inside is None:
        join.why = (f"{seam.piece_b} is neither a closed band nor a piece with an opening, so "
                    f"there is nothing to thread {seam.piece_a} through")
    elif girth <= THREAD_ROOM * inside:
        join.verdict = "sound"
        join.why = (f"{seam.piece_a} ({girth:.1f}cm around) passes through {seam.piece_b} "
                    f"({inside:.1f}cm inside)")
    else:
        join.verdict = "mismatched"
        join.why = (f"{seam.piece_a} is {girth:.1f}cm around and {seam.piece_b} is "
                    f"{inside:.1f}cm inside: it does not pass through with room")


def _silhouette(cir, geo: ObjectGeometry) -> None:
    """The finished object's overall extent.

    Taken from the piece that carries the object's body rather than summed over every piece,
    because pieces sewn ONTO a body (pockets, bands, appliqué) sit within its outline and do
    not enlarge it. The body piece is the largest by area, which is a structural fact rather
    than a name: a cardigan's body, a basket's sides, a blanket's centre.
    """
    if not geo.footprints:
        return
    body = max(geo.footprints.values(), key=lambda f: f.across_cm * f.up_cm)
    geo.silhouette_across_cm = round(body.across_cm, 1)
    geo.silhouette_up_cm = round(body.up_cm, 1)
