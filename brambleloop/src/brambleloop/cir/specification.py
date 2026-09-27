"""What a Brambleloop design must state to be reconstructible, and what it may leave out.

The owner's rule, generalised on 2026-09-24: if a construction fact materially determines the
finished object's geometry, placement, assembly, fit or visible appearance, it belongs in the
authoritative source rather than in a photograph or in the maker's intuition.

The benchmark garment is what made this concrete. It is a competently written, commercially
sold pattern, and it still leaves two things to a picture: where the pockets go, and how long
the neckline band is. A human reads the photograph and works it out. A deterministic
reconstruction cannot, and neither can a customer who is working from the text at two in the
morning -- so the gap is not only ours.

**This does not licence falsifying a benchmark.** A record of someone else's pattern is
allowed to be exactly as incomplete as its source; inventing a placement to make the record
look complete would destroy the thing that makes it a benchmark. The asymmetry is the whole
design: `benchmark` may be incomplete and is reported as such, `brambleloop` may not.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass


@dataclass(frozen=True)
class Gap:
    """One fact the design does not state, and what cannot be determined without it."""

    fact: str
    where: str
    consequence: str

    def to_dict(self) -> dict:
        return {"fact": self.fact, "where": self.where, "consequence": self.consequence}


class SpecificationIncomplete(ValueError):
    """A Brambleloop design that cannot be reconstructed from what it says."""


def reconstructive_gaps(cir) -> list[Gap]:
    """Facts missing from a design that its finished object's geometry depends on.

    Checked against the object rather than against a checklist of garment parts, so the same
    rule covers a basket's handle placement, a blanket's border attachment and a bag's gusset
    without naming any of them.
    """
    gaps: list[Gap] = []

    for comp in cir.components:
        if getattr(comp, "grain", None) not in ("up", "across"):
            gaps.append(Gap(
                "panel orientation", comp.name,
                "which way the rows run on the finished object is undetermined, so its "
                "proportions and the direction of its texture cannot be reconstructed"))

    for i, seam in enumerate(cir.assembly, start=1):
        if seam.is_self_seam:
            continue
        if not seam.names_its_edges:
            gaps.append(Gap(
                "join target", f"assembly step {i}: {seam.piece_a} to {seam.piece_b}",
                "which edges meet is undetermined, so the pieces cannot be placed relative "
                "to one another and no join length can be checked"))
        if seam.at_round is None and seam.stitches_from_centre is None \
                and not seam.names_its_edges:
            gaps.append(Gap(
                "component placement", f"{seam.piece_a} onto {seam.piece_b}",
                "where on the second piece the join happens is undetermined, so a maker "
                "can follow every row and still not know where it goes"))

    if cir.gauge is None:
        gaps.append(Gap("gauge", "design", "no stitch count converts to a measurement, so "
                                           "nothing about the finished size is determined"))
    elif any(getattr(o, "stitch", None) == "ch" and not getattr(o, "spans", 0)
             for c in cir.components for r in c.rows for o in r.ops) \
            and not cir.gauge.chains_per_10cm:
        gaps.append(Gap(
            "chain gauge", "gauge",
            "the design has chains that add fabric width, and chains are narrower than "
            "worked stitches, so every span they make is measured at the wrong gauge"))

    return gaps


def is_reconstructible(cir) -> dict:
    """Whether this design says enough to rebuild its finished object."""
    gaps = reconstructive_gaps(cir)
    authored = getattr(cir, "authored", "brambleloop")
    return {
        "slug": cir.slug,
        "authored": authored,
        "reconstructible": not gaps,
        "gaps": [g.to_dict() for g in gaps],
        "held_to_the_standard": authored == "brambleloop",
        "why": ("every fact needed to reconstruct the finished object is stated"
                if not gaps else
                f"{len(gaps)} reconstructive fact(s) are missing" +
                ("" if authored == "brambleloop" else
                 ". This is a record of someone else's pattern and is allowed to be as "
                 "incomplete as its source; the gaps are reported rather than invented")),
    }


def refuse_an_underspecified_design(cir) -> None:
    """The gate. A Brambleloop product may not be certified with reconstructive gaps.

    Benchmarks pass through untouched, because holding a record of someone else's work to
    our specification standard would mean either rejecting every real pattern we study or
    fabricating the facts they omit. Both would destroy the benchmark.
    """
    if getattr(cir, "authored", "brambleloop") != "brambleloop":
        return
    gaps = reconstructive_gaps(cir)
    if gaps:
        lines = "; ".join(f"{g.fact} ({g.where})" for g in gaps)
        raise SpecificationIncomplete(
            f"{cir.slug} cannot be reconstructed from what it states: {lines}. A Brambleloop "
            f"design must say everything its finished object's geometry depends on, because "
            f"we control its specification and a photograph is not a specification")
    refuse_an_implausible_garment(cir)


# ---- a garment that compiles and cannot be worn --------------------------------------------
#
# Certification audit C-7: a top-down raglan whose yoke could not grow from neck to chest
# shipped with a neck edge of 0.6-0.88 of its chest and, at the largest sizes, a back neck
# wider than the wearer's shoulders. Every count closed and every gate passed, because no
# gate asked whether the neck fits a body. This one does, for any top-down yoke -- a piece
# that starts at a foundation, puts stitches on hold for the sleeves and carries on as a
# body -- so no future template can ship that garment, whatever its arithmetic.
#
# The thresholds are design plausibility floors, stated rather than measured:
# - The whole neck edge (for an open front: both fronts, both sleeve tops and the back neck)
#   may be at most `MAX_NECK_EDGE_OF_CHEST` of the finished chest. Worked top-down raglans
#   sit at roughly 0.3-0.45; 0.55 already reads as an off-the-shoulder neckline.
# - The back neck may be at most `MAX_BACK_NECK_OF_BACK` of the back's finished width at the
#   underarm, which leaves each shoulder at least a quarter of the back.
# - When the wearer's body is known (a graded size), the back neck may not exceed the body's
#   cross-back (shoulder to shoulder) -- a neck wider than the shoulders falls off them.
MAX_NECK_EDGE_OF_CHEST = 0.55
MAX_BACK_NECK_OF_BACK = 0.5


class GarmentImplausible(SpecificationIncomplete):
    """A design whose counts close but whose finished object does not fit a body."""


def _flat(nodes) -> list | None:
    from .model import Op

    out = []
    for n in nodes:
        if not isinstance(n, Op):
            return None          # a repeat: not a yoke row this derivation reads
        out.append(n)
    return out


def _map_boundaries(row, out_bounds: list[int]) -> list[int] | None:
    """Where each output boundary of `row` falls in the row it is worked into."""
    from . import stitches as ST

    ops = _flat(row.ops)
    if ops is None:
        return None
    units: list[tuple[int, int]] = []
    for op in ops:
        try:
            st = ST.get(op.stitch)
        except (KeyError, ValueError):
            return None
        if getattr(op, "spans", 0):
            return None
        units += [(st.consumes, st.produces)] * op.count
    result, in_pos, out_pos = [], 0, 0
    targets = iter(sorted(out_bounds))
    q = next(targets, None)
    for c, p in units:
        while q is not None and q <= out_pos:
            result.append(in_pos)
            q = next(targets, None)
        in_pos, out_pos = in_pos + c, out_pos + p
    while q is not None:
        result.append(in_pos)
        q = next(targets, None)
    return result


def yoke_geometry(cir) -> dict | None:
    """Neck edge, sections at the neck and at the underarm of a top-down yoke, in stitches.

    Derived from the CIR's structure, not from anything the template says about itself: the
    holds fix the sections at the underarm, and each yoke row is walked back to the neck
    through its own increases (a flat row is worked into the previous one reversed).
    """
    for comp in cir.components:
        if len(comp.holds) < 2 or comp.foundation <= 0:
            continue
        at = {h.at_row for h in comp.holds}
        if len(at) != 1:
            continue
        at_row = at.pop()
        by_index = {r.index: r for r in comp.rows}
        division = by_index.get(at_row + 1)
        last = by_index.get(at_row)
        if division is None or last is None or not division.skips:
            continue
        width = last.declared_count
        holds = sorted(comp.holds, key=lambda h: h.from_stitch)
        bounds = sorted({0, width} | {h.from_stitch for h in holds}
                        | {h.from_stitch + h.count for h in holds})
        # The back: the stretch between the first hold's end and the second hold's start.
        back_lo, back_hi = holds[0].from_stitch + holds[0].count, holds[1].from_stitch
        back_at_underarm = back_hi - back_lo
        flat = comp.construction == "flat_rows"
        cur = bounds
        for index in range(at_row, 0, -1):
            row = by_index.get(index)
            if row is None:
                return None
            mapped = _map_boundaries(row, cur)
            if mapped is None:
                return None
            below = comp.foundation if index == 1 else by_index[index - 1].declared_count
            if flat:
                mapped = sorted(below - x for x in mapped)
            cur = mapped
        sections = [b - a for a, b in zip(cur, cur[1:])]
        i_back = bounds.index(back_lo)
        return {"piece": comp.name, "neck_edge": comp.foundation,
                "chest": division.declared_count, "back_at_underarm": back_at_underarm,
                "sections_at_neck": sections, "back_neck": sections[i_back]}
    return None


def garment_implausibilities(cir, *, cross_back_cm: float | None = None) -> list[str]:
    """Why this garment's neck cannot sit on a body, or [] (or [] when it is no yoke)."""
    geo = yoke_geometry(cir)
    if geo is None or cir.gauge is None:
        return []
    per_cm = cir.gauge.stitches_per_10cm / 10.0
    out = []
    ratio = geo["neck_edge"] / geo["chest"]
    if ratio > MAX_NECK_EDGE_OF_CHEST:
        out.append(f"neck edge {geo['neck_edge'] / per_cm:.0f} cm is {ratio:.2f} of the "
                   f"{geo['chest'] / per_cm:.0f} cm chest (at most {MAX_NECK_EDGE_OF_CHEST})")
    if geo["back_neck"] > MAX_BACK_NECK_OF_BACK * geo["back_at_underarm"]:
        out.append(f"back neck {geo['back_neck']} sts is more than {MAX_BACK_NECK_OF_BACK} of "
                   f"the {geo['back_at_underarm']}-st back at the underarm")
    if cross_back_cm is not None and geo["back_neck"] / per_cm > cross_back_cm:
        out.append(f"back neck {geo['back_neck'] / per_cm:.1f} cm is wider than the "
                   f"{cross_back_cm:g} cm cross-back it has to sit between")
    return out


def refuse_an_implausible_garment(cir, *, cross_back_cm: float | None = None) -> None:
    """The gate: a Brambleloop yoke whose neck does not fit a body is refused."""
    if getattr(cir, "authored", "brambleloop") != "brambleloop":
        return
    problems = garment_implausibilities(cir, cross_back_cm=cross_back_cm)
    if problems:
        raise GarmentImplausible(
            f"{cir.slug} compiles but cannot be worn: {'; '.join(problems)}. A neck that "
            f"does not fit a body is a design defect, whatever the arithmetic says")


# ---- a benchmark in our clothes ------------------------------------------------------------
#
# Purchased and benchmark patterns are studied for demand and merchandising intelligence and
# are NEVER a source for a Brambleloop design (Execution Directive; CLAUDE.md). A declared
# `Provenance` records what a design was built from, but a declaration is only a claim. This
# is the numeric check behind it: a design that carries ANY identifying piece of a benchmark
# is a benchmark with our name on it, whatever its provenance says, and it is refused.
#
# Numeric rather than text similarity, because renaming a piece, rewording a note or
# retitling the pattern changes nothing a maker works -- the counts are the design.
#
# **Any piece, not every piece.** The first version required EVERY identifying piece of a
# benchmark size to be present, so keeping the body and sleeve and dropping the pocket and
# the neck ribbing escaped it (certification audit C-6). One identifying piece carried over
# stitch for stitch is already a copied piece.
#
# **Tolerant, not exact.** Exact containment was escaped by deleting the last row of each
# piece. A piece is compared by its SHAPE: its per-row sequence run-length encoded into
# (value, how many rows) runs. Ours matches when it contains the same sequence of values
# with every run length within `RUN_TOLERANCE` rows of the benchmark's -- so trimming,
# padding or re-counting a few rows of a run does not evade it, while the positions at which
# the counts CHANGE (the armhole rows, the shaping) must all be there, in order. The first
# and last runs may be longer in ours: containment, not equality.
#
# **Two tiers, because a rectangle's counts identify nothing.** Most benchmark pieces are
# rectangles: the sleeve is 64 stitches for 33 rows. A count-only comparison would refuse
# every 64-stitch rectangle anyone ever wrote, including ours. So:
#   1. counts tier -- per-row stitch counts only. Used for a piece whose counts change at
#      least `MIN_COUNT_CHANGES` times: a 94-stitch body with one-row 95-stitch bumps at two
#      stated rows is a structure, not arithmetic. Relabelling the stitch does not escape it.
#   2. worked tier -- per-row (count, the row as worked: stitches, loops, bridges, in order).
#      Used for every piece, and the only tier for a rectangle: a 64-stitch rectangle of
#      half-double crochet with a back-loop rib band at one edge and alternating front/back
#      loops across the field is that sleeve; a 64-stitch rectangle of plain sc is not.

# A piece shorter than this is too generic to identify anything: a 7-stitch band worked for a
# dozen rows exists in half the patterns ever written, and refusing on it would refuse our own
# designs for coinciding with arithmetic nobody owns.
MIN_IDENTIFYING_ROWS = 10
# How far one run of rows may differ in length between ours and the benchmark's and still be
# the same run: the larger of 2 rows and 10% of the run. Big enough that dropping or adding a
# row or two per piece (the trimming evasion) does not escape; small enough that two designs
# whose counts change at genuinely different heights do not collide.
RUN_TOLERANCE_ROWS = 2
RUN_TOLERANCE_FRACTION = 0.10
# A piece's counts identify it on their own only when they change at least this often: two
# changes (up and back down, e.g. a bridged armhole row) make a located structure.
MIN_COUNT_CHANGES = 2


class BenchmarkDerived(ValueError):
    """A Brambleloop-authored design that carries a benchmark's piece."""


def _worked(nodes) -> tuple:
    """A row as a maker works it, independent of colour and notes."""
    from .model import Op, Repeat

    out = []
    for n in nodes:
        if isinstance(n, Repeat):
            out.append(("repeat", n.times, _worked(n.ops)))
        elif isinstance(n, Op):
            out.append((n.stitch, n.count, n.loop, bool(getattr(n, "spans", 0))))
    return tuple(out)


def _piece_tables(cir) -> dict[str, tuple[tuple, tuple]]:
    """Per piece: (counts, worked) -- the foundation then every row, as two sequences."""
    from .compiler import compile_cir

    result = compile_cir(cir)
    out: dict[str, tuple[tuple, tuple]] = {}
    for comp in cir.components:
        produced = {r.index: r.produced for r in result.rows if r.component == comp.name}
        counts = [comp.foundation]
        worked = [(comp.foundation, "foundation")]
        for row in comp.rows:
            n = produced.get(row.index, row.declared_count)
            counts.append(n)
            worked.append((n, _worked(row.ops)))
        out[comp.name] = (tuple(counts), tuple(worked))
    return out


def _count_tables(cir) -> dict[str, tuple[int, ...]]:
    """Per piece: (foundation, stitch count of every row), the numbers a maker works."""
    return {name: t[0] for name, t in _piece_tables(cir).items()}


def _runs(seq) -> list[tuple[object, int]]:
    runs: list[list] = []
    for v in seq:
        if runs and runs[-1][0] == v:
            runs[-1][1] += 1
        else:
            runs.append([v, 1])
    return [(v, n) for v, n in runs]


def _tolerance(n: int) -> int:
    return max(RUN_TOLERANCE_ROWS, int(round(n * RUN_TOLERANCE_FRACTION)))


def shape_contains(ours, theirs) -> bool:
    """Whether `ours` contains `theirs` up to a few rows per run (see the tiers above)."""
    t, o = _runs(theirs), _runs(ours)
    k = len(t)
    for start in range(len(o) - k + 1):
        ok = True
        for j, (value, n) in enumerate(t):
            v2, m = o[start + j]
            if v2 != value:
                ok = False
                break
            tol = _tolerance(n)
            edge = j == 0 or j == k - 1
            if (m < n - tol) if edge else (abs(m - n) > tol):
                ok = False
                break
        if ok:
            return True
    return False


@functools.lru_cache(maxsize=1)
def _benchmark_tables() -> tuple[tuple[str, dict[str, tuple[tuple, tuple]]], ...]:
    """Every benchmark size's tables, computed once: the benchmarks are fixed records."""
    from . import benchmarks  # read-only: the comparison set, never a source

    return tuple((size, _piece_tables(benchmarks.cardigan(size)))
                 for size in benchmarks.SIZES)


def _identifying(counts: tuple) -> bool:
    return len(counts) - 1 >= MIN_IDENTIFYING_ROWS


def benchmark_matches(cir) -> list[dict]:
    """Every benchmark size ANY of whose identifying pieces appears in `cir`.

    A piece is identifying when it has at least `MIN_IDENTIFYING_ROWS` rows. It appears in
    ours when some piece of ours contains its shape within the run tolerance, by counts
    alone (a piece with at least `MIN_COUNT_CHANGES` count changes) or by counts and the
    rows as worked (every piece). Each match names the pieces found and the tier.
    """
    ours = list(_piece_tables(cir).values())
    matches: list[dict] = []
    for size, theirs in _benchmark_tables():
        found: dict[str, str] = {}
        for name, (counts, worked) in theirs.items():
            if not _identifying(counts):
                continue
            changes = len(_runs(counts)) - 1
            if changes >= MIN_COUNT_CHANGES and \
                    any(shape_contains(oc, counts) for oc, _ in ours):
                found[name] = "counts"
            elif any(shape_contains(ow, worked) for _, ow in ours):
                found[name] = "worked"
        if found:
            matches.append({"benchmark": "cardigan", "size": size,
                            "pieces": sorted(found), "tiers": dict(sorted(found.items()))})
    return matches


def refuse_a_benchmark_in_our_clothes(cir) -> None:
    """The gate. A `brambleloop` design may not carry a benchmark's stitch tables.

    Benchmarks themselves pass: they are allowed to be exactly what they are.
    """
    if getattr(cir, "authored", "brambleloop") != "brambleloop":
        return
    matches = benchmark_matches(cir)
    if matches:
        where = "; ".join(f"{m['benchmark']} size {m['size']} ({', '.join(m['pieces'])})"
                          for m in matches)
        raise BenchmarkDerived(
            f"{cir.slug} is authored as Brambleloop's own but its stitch tables contain a "
            f"purchased benchmark's: {where}. Benchmarks are for demand and merchandising "
            f"intelligence only and are never a source for a Brambleloop design")
