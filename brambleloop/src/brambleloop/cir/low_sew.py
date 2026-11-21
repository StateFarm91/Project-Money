"""ENG-AMIGURUMI-BREADTH: low-sew ("join-as-you-go") joins, validated as structure.

The technique class (teardown lessons, `research/benchmarks/TEARDOWN_*.md` L2): an appendage --
a leg, an arm, an ear, a tail, a fin -- is worked in rounds from a magic ring, its last round
is flattened so its two layers line up, and it is NOT sewn on. Instead, when the body reaches
the round it belongs to, the body's stitches at the stated positions are worked through the
body AND both layers of the flattened edge at once. The appendage is crocheted into the body;
nothing is sewn, and the joined stitch counts are arithmetic the compiler can check.

The CIR carries it as `Op.joins` on the body's round: `Op("sc", 5, joins="leg")` is five sc
worked through the next five body stitches and both layers of a leg's 10-st last round. That
op is count-neutral for the body (one stitch made per stitch consumed). This module checks:

  LOW_SEW_UNKNOWN_PIECE   `joins` names no piece of the pattern, or the piece itself
  LOW_SEW_NOT_ROUNDS      the host or the joined piece is not worked in rounds
  LOW_SEW_EDGE_NOT_FLAT   the joined piece's last round is odd (two layers cannot line up), or
                          the piece is gathered closed (`closes`) so it has no edge to join
  LOW_SEW_STITCH          the joining stitch is not a plain sc through both loops
  LOW_SEW_EDGE_MISMATCH   a joined run is not exactly the flattened edge (last round / 2): too
                          few stitches leaves part of the edge loose, too many has nothing to go
                          through (measured on the twin's cells, so the twin and the compiler
                          read one definition)
  LOW_SEW_JOIN_COUNT      a piece made N times is joined in a number of places other than N
  LOW_SEW_ALSO_SEWN       a crocheted-in piece is also given a sewn assembly step (it would be
                          attached twice, or the document contradicts itself)
  LOW_SEW_UNMEASURED      the twin could not be built, so no join could be measured (UNKNOWN is
                          never a pass)

Every finding is an ERROR: a limb that does not meet its round is not a pattern.

`sites(twin)` reads the joined runs off a built `TwinModel` (cell by cell), and
`cir.assembly.assemble` records each as a measured join, so the object geometry the
child-safety gate reads sees every crocheted-in piece exactly as it sees a sewn one.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import CIR, Op, Repeat

METHOD = "join_in"       # the join's method name in `cir.assembly` geometry
JOIN_STITCHES = frozenset({"sc"})


@dataclass(frozen=True)
class Site:
    piece: str          # the joined piece (a leg)
    host: str           # the piece it is crocheted into (the body)
    round: int          # the host round
    start: int          # 1-based stitch of the host round where the joined run begins
    width: int          # stitches worked through both pieces


def _ops(nodes):
    for n in nodes:
        if isinstance(n, Op):
            yield n
        elif isinstance(n, Repeat):
            yield from _ops(n.ops)


def joined_pieces(cir: CIR) -> list[str]:
    """Every piece some round crochets in, in first-joined order."""
    out: list[str] = []
    for comp in cir.components:
        for row in comp.rows:
            for op in _ops(row.ops):
                j = getattr(op, "joins", None)
                if j and j not in out:
                    out.append(j)
    return out


def edge_of(comp) -> int | None:
    """The stitches across a piece's flattened last round (each layer), or None when the last
    round cannot be flattened into two equal layers."""
    if not comp.rows:
        return None
    last = comp.rows[-1].declared_count
    if not last or last % 2:
        return None
    return last // 2


def sites(twin, host: str) -> list[Site]:
    """The joined runs on a built twin: contiguous cells of one row naming one piece."""
    out: list[Site] = []
    by_row: dict[int, list] = {}
    for c in twin.cells:
        by_row.setdefault(c.row, []).append(c)
    for row, cells in sorted(by_row.items()):
        cells = sorted(cells, key=lambda c: c.position)
        run_piece, run_start, run_len = None, 0, 0
        for c in cells + [None]:
            j = getattr(c, "joins", None) if c is not None else None
            if j is not None and j == run_piece and c.position == run_start + run_len:
                run_len += 1
                continue
            if run_piece is not None:
                out.append(Site(run_piece, host, row, run_start + 1, run_len))
            run_piece, run_start, run_len = (j, c.position, 1) if j is not None else (None, 0, 0)
    return out


def all_sites(cir: CIR, result) -> list[Site] | None:
    """Every joined run in the pattern, read from each host's twin; None when no twin builds."""
    from .twin import build_twin

    hosts = [c.name for c in cir.components
             if any(getattr(op, "joins", None) for r in c.rows for op in _ops(r.ops))]
    out: list[Site] = []
    for h in hosts:
        try:
            out.extend(sites(build_twin(cir, result, h), h))
        except (ValueError, KeyError):
            return None
    return out


def _finding(code: str, message: str, where: str, row: int | None = None):
    from .compiler import ERROR, Finding

    return Finding(ERROR, code, message, where, row)


def check(cir: CIR, result, findings: list) -> None:
    """Append a finding for every low-sew join that is not exactly what its pieces make."""
    comps = {c.name: c for c in cir.components}
    structural = len(findings)
    for host in cir.components:
        for row in host.rows:
            for op in _ops(row.ops):
                piece = getattr(op, "joins", None)
                if not piece:
                    continue
                where = host.name
                if piece not in comps or piece == host.name:
                    findings.append(_finding(
                        "LOW_SEW_UNKNOWN_PIECE",
                        f"round {row.index} is worked through {piece!r}, which is not another "
                        f"piece of this pattern", where, row.index))
                    continue
                joined = comps[piece]
                if host.construction == "flat_rows" or joined.construction == "flat_rows":
                    findings.append(_finding(
                        "LOW_SEW_NOT_ROUNDS",
                        f"{piece} is crocheted into {host.name} round {row.index}, but a "
                        f"join-as-you-go here joins a piece in rounds into a piece in rounds",
                        where, row.index))
                if op.stitch not in JOIN_STITCHES or getattr(op, "loop", "both") != "both":
                    findings.append(_finding(
                        "LOW_SEW_STITCH",
                        f"the {piece} is joined with {op.stitch} ({op.loop} loops); a "
                        f"crocheted-in join is sc through both loops of the body and both "
                        f"layers of the edge", where, row.index))
    for name in joined_pieces(cir):
        comp = comps.get(name)
        if comp is None:
            continue
        if comp.closes or edge_of(comp) is None:
            last = comp.rows[-1].declared_count if comp.rows else None
            findings.append(_finding(
                "LOW_SEW_EDGE_NOT_FLAT",
                f"the {name} is crocheted in by its flattened last round, but that round "
                + ("is gathered closed" if comp.closes else
                   f"has {last} sts, which do not fold into two equal layers"), name))
        sewn = [s for s in cir.assembly if name in (s.piece_a, s.piece_b)
                and s.piece_a != s.piece_b]
        if sewn:
            findings.append(_finding(
                "LOW_SEW_ALSO_SEWN",
                f"the {name} is crocheted into its round and also given {len(sewn)} sewn "
                f"assembly step(s); a piece is attached once", name))
    if len(findings) > structural or not result.ok:
        return          # the twin is built only from clean arithmetic and sound structure
    got = all_sites(cir, result)
    if got is None:
        findings.append(_finding("LOW_SEW_UNMEASURED",
                                 "the twin could not be built, so no crocheted-in join was "
                                 "measured (UNKNOWN is not a pass)", cir.components[0].name))
        return
    for name in joined_pieces(cir):
        comp = comps[name]
        edge = edge_of(comp)
        mine = [s for s in got if s.piece == name]
        for s in mine:
            if s.width != edge:
                findings.append(_finding(
                    "LOW_SEW_EDGE_MISMATCH",
                    f"{s.host} round {s.round} works {s.width} sts through the {name} from st "
                    f"{s.start}, but the {name}'s flattened edge is {edge} sts "
                    f"({comp.rows[-1].declared_count} / 2): "
                    + ("part of the edge is left loose" if s.width < edge
                       else "some stitches have no edge to go through"), s.host, s.round))
        if len(mine) != comp.make:
            findings.append(_finding(
                "LOW_SEW_JOIN_COUNT",
                f"{comp.make} {name}(s) are made but {len(mine)} are crocheted in", name))


def summary(cir: CIR, result) -> list[dict]:
    """Per joined run, for the PDF's assembly diagram and the child-safety evidence."""
    got = all_sites(cir, result) or []
    comps = {c.name: c for c in cir.components}
    return [{"piece": s.piece, "host": s.host, "round": s.round, "start": s.start,
             "width": s.width, "edge": edge_of(comps[s.piece]) if s.piece in comps else None}
            for s in got]
