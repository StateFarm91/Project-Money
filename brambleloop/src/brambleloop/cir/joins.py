"""ENG-LOWSEW-CHENILLE: join-as-you-go ("low-sew") construction, checked rather than trusted.

A low-sew toy is not a sewn toy with fewer seams. Its limbs are worked as tubes, flattened and
closed ("fold and close": a stated number of sc through both layers), and then crocheted INTO
a named round of the body: the body round is worked as usual, and where a limb sits each
stitch is worked through the body stitch and the limb's closed edge together. A head can be
joined the same way, by working its last round through the body's open last round.

That is three promises a maker cannot check with a tape measure, so this module checks them
from the compiled rounds (`Op.through`, `Row.fold`, the CIR's own counts):

  JOIN_UNKNOWN_PIECE     a stitch is worked through a piece the pattern does not contain
  JOIN_SELF              a piece is worked through itself
  JOIN_ORDER             the piece worked through is made after the round that joins it
  JOIN_STITCH            a joining stitch that is not sc or sl st (one stitch, one edge stitch)
  JOIN_TARGET_CLOSED     the piece was gathered shut, so it has no edge to work through
  JOIN_WIDTH_MISMATCH    a joined run is not exactly the piece's join width (a fold-closed
                         limb's closing count, or an open piece's last-round count)
  JOIN_INSTANCES         the number of joined runs is not the piece's `make`
  JOIN_UNATTACHED        a fold-closed piece is neither crocheted in nor sewn on
  JOIN_RUNS_TOUCH        two joined runs on one round have no stitch between them
  JOIN_PAIR_SPLIT        a pair (make 2) is joined on two different rounds: it cannot mirror
  JOIN_ASYMMETRIC        the pieces on one host do not share one mirror line (left and right
                         limbs mirrored about the same front-to-back line as every other
                         pair, and a single piece -- a tail -- centred on it)
  JOIN_DRIFT_UNSTATED    a spiral host with a joined round states no drift allowance
  JOIN_DRIFT_TOO_WIDE    the drift allowance is over JOIN_DRIFT_MAX, or would let one run
                         slide into the next (more than half the narrowest gap)
  JOIN_STUFFED_OPEN      a stuffed piece whose last round is open and that no full-width
                         join closes: stuffing with a hole in it
  JOIN_STUFF_AFTER_JOIN  a piece is stuffed after the round that joins it shut
  FOLD_AND_GATHER        a piece is both fold-closed and gathered shut
  EYE_*                  the embroidered eye placement does not fit the piece

Every finding is an ERROR. Positions are 1-based stitches of the joined round, counted from
the round's first stitch (the marker), and are what the writer prints and the reverse
compiler recomputes from the document alone.

`sewing_required` is the construction reading listing copy may lean on: "no sew" and "low
sew" are high-intent search words and are claims, so `sewing_claim_findings` allows them only
when this reading, computed from a CIR that compiles, says so. UNKNOWN is never PASS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .model import CIR, Component

JOIN_DRIFT_MAX = 3                  # stitches; more than this and placement is guesswork
JOIN_STITCHES = ("sc", "slst")      # one stitch made per stitch below, one edge stitch each
# How many pieces may be sewn on with a needle and the construction still read "low sew".
LOW_SEW_MAX_SEWN_JOINS = 1
SEWING_NONE, SEWING_LOW, SEWING_STANDARD, SEWING_UNKNOWN = "none", "low", "standard", "UNKNOWN"
SEWN_METHODS = ("whipstitch", "mattress", "sew")


def _finding(code: str, message: str, where: str | None = None, row: int | None = None):
    from .compiler import ERROR, Finding

    return Finding(ERROR, code, message, where, row)


def _ops_through(nodes) -> bool:
    from .model import Op

    for n in nodes:
        if isinstance(n, Op):
            if getattr(n, "through", None):
                return True
        elif _ops_through(n.ops):
            return True
    return False


def uses_joins(cir: CIR) -> bool:
    """True when the design states any join-as-you-go structure at all."""
    for comp in cir.components:
        if comp.join_drift_sts is not None or comp.eye_round is not None \
                or comp.eye_gap_sts is not None:
            return True
        for row in comp.rows:
            if getattr(row, "fold", False) or _ops_through(row.ops):
                return True
    return False


@dataclass(frozen=True)
class JoinRun:
    """One piece's edge crocheted into one round: `start` is the 1-based first stitch."""

    host: str
    round: int
    target: str
    start: int
    width: int
    round_count: int

    @property
    def end(self) -> int:
        return self.start + self.width - 1

    @property
    def centre(self) -> float:
        """Centre, in stitch positions (0-based), of the run on its round."""
        return (self.start - 1) + (self.width - 1) / 2.0

    @property
    def full_round(self) -> bool:
        return self.width == self.round_count

    def to_dict(self) -> dict:
        return {"host": self.host, "round": self.round, "piece": self.target,
                "sts": [self.start, self.end], "width": self.width,
                "of": self.round_count}


def runs_from_ops(host: str, index: int, ops) -> list[JoinRun]:
    """The joined runs of one round, from its stitches in working order.

    Shared by the compiler (resolved ops) and the reverse compiler (ops parsed from the
    document): it is arithmetic over a sequence, not a reading of either source, so the two
    sides still meet only in their inputs."""
    from . import stitches

    out: list[JoinRun] = []
    pos = 0
    current: list | None = None   # [target, start, width]
    total = sum(stitches.get(o.stitch).produces * o.count for o in ops)
    for op in ops:
        made = stitches.get(op.stitch).produces * op.count
        target = getattr(op, "through", None)
        if target and current is not None and current[0] == target \
                and current[1] + current[2] - 1 == pos:
            current[2] += made
        elif target:
            if current is not None:
                out.append(JoinRun(host, index, current[0], current[1] + 1, current[2], total))
            current = [target, pos, made]
        elif current is not None:
            out.append(JoinRun(host, index, current[0], current[1] + 1, current[2], total))
            current = None
        pos += made
    if current is not None:
        out.append(JoinRun(host, index, current[0], current[1] + 1, current[2], total))
    return out


def runs(cir: CIR, result) -> list[JoinRun]:
    """Every joined run in the design, from the compiled rounds."""
    out: list[JoinRun] = []
    for row in result.rows:
        if any(getattr(o, "through", None) for o in row.ops):
            out += runs_from_ops(row.component, row.index, row.ops)
    return out


def join_edge(comp: Component, result) -> tuple[str, int | None]:
    """("fold", width) for a fold-closed piece, ("open", width) for an open last round,
    ("closed", None) for a gathered closure, ("none", None) when it has no rounds."""
    rows = [r for r in result.rows if r.component == comp.name]
    if not rows:
        return "none", None
    last = rows[-1]
    if getattr(last, "fold", False):
        return "fold", last.stitch_count
    if comp.closes:
        return "closed", None
    return "open", last.stitch_count


def _circular_gap(a: JoinRun, b: JoinRun) -> int:
    """Stitches strictly between two runs on one round, the shorter way round."""
    n = a.round_count
    after_a = (b.start - a.end - 1) % n
    after_b = (a.start - b.end - 1) % n
    return min(after_a, after_b)


def _axis(fraction: float) -> float:
    """A mirror LINE through the round, as a fraction of the round in [0, 0.5)."""
    return fraction % 0.5


def _axis_distance(a: float, b: float) -> float:
    d = abs(a - b) % 0.5
    return min(d, 0.5 - d)


def axes(cir: CIR, result) -> dict[str, list[tuple[str, int, float, float]]]:
    """Per host: (piece, round, mirror-line fraction, tolerance fraction) for every pair and
    every single centred piece. A full-round join (a head) has no line and is not listed."""
    by_host: dict[str, list] = {}
    all_runs = runs(cir, result)
    by_name = {c.name: c for c in cir.components}
    for (host, target), group in _group(all_runs).items():
        group = [r for r in group if not r.full_round]
        if not group:
            continue
        comp = by_name.get(target)
        make = comp.make if comp is not None else len(group)
        n = group[0].round_count
        tol = 0.5 / n                      # half a stitch of that round
        if len(group) == 2 and make == 2 and group[0].round == group[1].round:
            a, b = group
            ca, cb = a.centre / n, b.centre / n
            # The mirror line passes through the midpoint of the two centres.
            mid = (ca + cb) / 2.0
            by_host.setdefault(host, []).append((target, a.round, _axis(mid), tol))
        elif len(group) == 1 and make == 1:
            r = group[0]
            by_host.setdefault(host, []).append((target, r.round, _axis(r.centre / n), tol))
    return by_host


def _group(all_runs: list[JoinRun]) -> dict[tuple[str, str], list[JoinRun]]:
    out: dict[tuple[str, str], list[JoinRun]] = {}
    for r in all_runs:
        out.setdefault((r.host, r.target), []).append(r)
    return out


def check(cir: CIR, result, findings: list) -> None:
    """Append a finding for every joined round, fold or eye placement that does not hold."""
    by_name = {c.name: c for c in cir.components}
    order = {c.name: i for i, c in enumerate(cir.components)}
    all_runs = runs(cir, result)

    # Stitches worked through another piece.
    for row in result.rows:
        for op in row.ops:
            target = getattr(op, "through", None)
            if not target:
                continue
            if op.stitch not in JOIN_STITCHES:
                findings.append(_finding(
                    "JOIN_STITCH",
                    f"{op.stitch} worked through the {target}: a joining stitch is sc or sl st, "
                    f"one stitch made for each stitch below and each edge stitch",
                    row.component, row.index))
    for run in all_runs:
        target = by_name.get(run.target)
        if target is None:
            findings.append(_finding(
                "JOIN_UNKNOWN_PIECE",
                f"round {run.round} is worked through {run.target!r}, which is not a piece of "
                f"this pattern (have: {sorted(by_name)})", run.host, run.round))
            continue
        if run.target == run.host:
            findings.append(_finding("JOIN_SELF", "a piece cannot be worked through itself",
                                     run.host, run.round))
            continue
        if order[run.target] > order[run.host]:
            findings.append(_finding(
                "JOIN_ORDER",
                f"round {run.round} works through the {run.target}, which the pattern makes "
                f"afterwards: a piece is finished before it is crocheted in",
                run.host, run.round))
        kind, width = join_edge(target, result)
        if kind == "closed":
            findings.append(_finding(
                "JOIN_TARGET_CLOSED",
                f"the {run.target} is gathered shut, so it has no edge to work through",
                run.host, run.round))
        elif kind in ("fold", "open") and run.width != width:
            what = ("its fold-and-close row" if kind == "fold" else "its open last round")
            findings.append(_finding(
                "JOIN_WIDTH_MISMATCH",
                f"sts {run.start}-{run.end} of round {run.round} ({run.width} sts) are worked "
                f"through the {run.target}, whose join edge is {width} sts ({what}); every "
                f"edge stitch must be worked through exactly once",
                run.host, run.round))

    grouped = _group(all_runs)
    for comp in cir.components:
        mine = [r for (h, t), g in grouped.items() if t == comp.name for r in g]
        kind, _width = join_edge(comp, result)
        if mine and len(mine) != comp.make:
            findings.append(_finding(
                "JOIN_INSTANCES",
                f"the pattern makes {comp.make} {comp.name}, but {len(mine)} "
                f"{'is' if len(mine) == 1 else 'are'} crocheted in", comp.name))
        if kind == "fold" and not mine:
            sewn = any(comp.name in (s.piece_a, s.piece_b) for s in cir.assembly
                       if s.piece_a != s.piece_b)
            if not sewn:
                findings.append(_finding(
                    "JOIN_UNATTACHED",
                    f"the {comp.name} is folded and closed but never crocheted in or sewn on",
                    comp.name))

    # Per host round: no two runs touch, and a pair is on one round.
    for (host, target), group in grouped.items():
        comp = by_name.get(target)
        if comp is not None and comp.make == 2 and len(group) == 2 \
                and group[0].round != group[1].round:
            findings.append(_finding(
                "JOIN_PAIR_SPLIT",
                f"the two {target} are joined on rounds {group[0].round} and "
                f"{group[1].round}; a pair is joined on one round so it can mirror", host))
    rounds: dict[tuple[str, int], list[JoinRun]] = {}
    for r in all_runs:
        rounds.setdefault((r.host, r.round), []).append(r)
    min_gap: dict[str, int] = {}
    for (host, index), group in rounds.items():
        group = sorted(group, key=lambda r: r.start)
        for a, b in zip(group, group[1:] + group[:1]):
            if a is b:
                continue
            gap = _circular_gap(a, b)
            min_gap[host] = min(min_gap.get(host, gap), gap)
            if gap < 1:
                findings.append(_finding(
                    "JOIN_RUNS_TOUCH",
                    f"on round {index} the {a.target} (sts {a.start}-{a.end}) and the "
                    f"{b.target} (sts {b.start}-{b.end}) have no stitch between them",
                    host, index))

    # One mirror line per host.
    for host, lines in axes(cir, result).items():
        ref_piece, ref_round, ref, ref_tol = lines[0]
        for piece, index, line, tol in lines[1:]:
            if _axis_distance(ref, line) > max(ref_tol, tol) + 1e-9:
                findings.append(_finding(
                    "JOIN_ASYMMETRIC",
                    f"the {piece} on round {index} mirror about a line at "
                    f"{line * 360:.0f} deg of the round, the {ref_piece} on round {ref_round} "
                    f"about {ref * 360:.0f} deg: left and right are not mirrored about one "
                    f"front-to-back line", host, index))

    # Drift allowance on spiral hosts.
    hosts = {r.host for r in all_runs}
    for host in sorted(hosts):
        comp = by_name.get(host)
        if comp is None or comp.construction != "spiral_rounds":
            continue
        drift = comp.join_drift_sts
        if drift is None:
            findings.append(_finding(
                "JOIN_DRIFT_UNSTATED",
                "pieces are crocheted into a spiral round, whose start drifts as it is worked; "
                "the pattern must state how many stitches the joining positions may shift",
                host))
            continue
        limit = JOIN_DRIFT_MAX
        if host in min_gap:
            limit = min(limit, min_gap[host] // 2)
        if drift < 0 or drift > limit:
            findings.append(_finding(
                "JOIN_DRIFT_TOO_WIDE",
                f"a drift allowance of {drift} sts; at most {limit} keeps every joined piece "
                f"clear of the next (limit {JOIN_DRIFT_MAX}, half the narrowest gap)", host))

    # Stuffed pieces with an open last round are closed by a full-width join, before stuffing.
    closing = {}
    for r in all_runs:
        if r.full_round:
            closing.setdefault(r.target, r)        # its open edge is worked through
            closing.setdefault(r.host, r)          # its own last round joins it shut
    for comp in cir.components:
        if comp.stuff_at_round is None or comp.closes:
            continue
        kind, _ = join_edge(comp, result)
        if kind == "fold":
            continue
        joined = closing.get(comp.name)
        rows = [r for r in result.rows if r.component == comp.name]
        if joined is None or not rows:
            findings.append(_finding(
                "JOIN_STUFFED_OPEN",
                "the piece is stuffed but its last round is open and no full-width join "
                "closes it", comp.name))
            continue
        if joined.host == comp.name and comp.stuff_at_round >= joined.round:
            findings.append(_finding(
                "JOIN_STUFF_AFTER_JOIN",
                f"stuffed after round {comp.stuff_at_round}, but round {joined.round} joins it "
                f"shut", comp.name))
    for comp in cir.components:
        kind, _ = join_edge(comp, result)
        rows = [r for r in result.rows if r.component == comp.name]
        if kind == "fold" and comp.stuff_at_round is not None and rows \
                and comp.stuff_at_round >= rows[-1].index:
            findings.append(_finding(
                "JOIN_STUFF_AFTER_JOIN",
                f"stuffed after round {comp.stuff_at_round}, the fold-and-close row", comp.name))
        if kind == "fold" and comp.closes:
            findings.append(_finding(
                "FOLD_AND_GATHER",
                "a fold-and-close piece cannot also be gathered shut", comp.name))
    check_eyes(cir, result, findings)


def check_eyes(cir: CIR, result, findings: list) -> None:
    for comp in cir.components:
        r, gap = comp.eye_round, comp.eye_gap_sts
        if r is None and gap is None:
            continue
        if r is None or gap is None:
            findings.append(_finding("EYE_PLACEMENT_INCOMPLETE",
                                     "an eye placement needs both its round and the stitches "
                                     "between the eyes", comp.name))
            continue
        counts = {row.index: row.stitch_count for row in result.rows
                  if row.component == comp.name}
        if r not in counts:
            findings.append(_finding("EYE_ROUND_UNKNOWN",
                                     f"the eyes are placed on round {r}, which the piece does "
                                     f"not have", comp.name))
            continue
        if gap < 1 or gap > counts[r] // 2 - 1:
            findings.append(_finding(
                "EYE_GAP",
                f"{gap} sts between the eyes on a round of {counts[r]}: the eyes must be "
                f"apart and both on the front half", comp.name, r))


def placement_line(run_group: list[JoinRun]) -> str:
    """The joining positions of one round, in a fixed grammar the reverse compiler reads."""
    parts = []
    seen: dict[str, int] = {}
    for run in sorted(run_group, key=lambda r: r.start):
        seen[run.target] = seen.get(run.target, 0) + 1
        piece = run.target.replace("_", " ")
        parts.append(f"{piece} {seen[run.target]} through sts {run.start}-{run.end}")
    n = run_group[0].round_count
    return (f"Joining Rnd {run_group[0].round} of {n} sts: " + "; ".join(parts) + ".")


def drift_line(comp: Component) -> str:
    return (f"Spiral drift: the start of a spiral round moves as you work. If your marker has "
            f"drifted, shift every joining position on that round by up to "
            f"{comp.join_drift_sts} sts, all together, so the gaps between pieces stay the "
            f"same.")


def eye_line(comp: Component) -> str:
    return (f"Eyes on Rnd {comp.eye_round}, {comp.eye_gap_sts} sts apart: embroider each eye "
            f"with yarn only, after stuffing, knots pulled inside the piece.")


def fold_prefix() -> str:
    return "Flatten the opening and work through both layers:"


# ---- the construction reading ------------------------------------------------------------


def sewing_required(cir: CIR, result=None) -> dict:
    """How much needle-and-thread work assembling this design takes, from the CIR alone.

    none      no piece is sewn to another and no feature is embroidered: every join is
              crocheted (fastening off and weaving in ends are not counted -- every pattern
              has them).
    low       no more than LOW_SEW_MAX_SEWN_JOINS piece is sewn on; embroidered features
              and gathered closures are allowed.
    standard  anything more.
    UNKNOWN   the design does not compile, so nothing about it is read (never a pass).
    """
    if result is None:
        from .compiler import compile_cir

        result = compile_cir(cir)
    if not result.ok:
        return {"sewing_required": SEWING_UNKNOWN, "why": "the design does not compile",
                "sewn_joins": None, "crochet_joins": None, "needle_work": []}
    sewn = [s for s in cir.assembly if s.method in SEWN_METHODS]
    crochet = runs(cir, result)
    needle = []
    if sewn:
        needle.append(f"{len(sewn)} sewn join(s)")
    texts = " ".join([cir.designer_notes or ""] + [c.note or "" for c in cir.components]
                     + [r.note or "" for c in cir.components for r in c.rows]
                     + [s.note or "" for s in cir.assembly]).lower()
    embroidered = any(c.eye_round is not None for c in cir.components) \
        or bool(re.search(r"\bembroider", texts))
    if embroidered:
        needle.append("embroidered features")
    gathered = [c.name for c in cir.components if c.closes]
    if gathered:
        needle.append(f"gathered closure ({', '.join(gathered)})")
    if not sewn and not embroidered and not gathered:
        level = SEWING_NONE
    elif len(sewn) <= LOW_SEW_MAX_SEWN_JOINS:
        level = SEWING_LOW
    else:
        level = SEWING_STANDARD
    return {"sewing_required": level, "sewn_joins": len(sewn),
            "crochet_joins": len(crochet), "needle_work": needle,
            "why": ("; ".join(needle) or "every join is crocheted")}


_NO_SEW = re.compile(r"\bno[\s-]*sew(?:ing)?\b|\bnosew\b|\bsew[\s-]*free\b|"
                     r"\bwithout\s+sewing\b|\bzero[\s-]*sew(?:ing)?\b", re.I)
_LOW_SEW = re.compile(r"\blow[\s-]*sew(?:ing)?\b|\bminimal\s+sewing\b|\blittle\s+sewing\b|"
                      r"\bless\s+sewing\b|\bbarely\s+any\s+sewing\b", re.I)


def sewing_claims(text: str) -> list[str]:
    """The sewing claims a title or tag makes: "none" for no-sew wording, "low" for low-sew."""
    out = []
    if _NO_SEW.search(text or ""):
        out.append(SEWING_NONE)
    if _LOW_SEW.search(text or ""):
        out.append(SEWING_LOW)
    return out


def sewing_claim_findings(text: str, reading: str | None, where: str = "title") -> list[str]:
    """Why `text` may not make the sewing claim it makes, given the certified reading.

    "no sew" needs the reading `none`; "low sew" needs `none` or `low`. Any other reading,
    including UNKNOWN or no reading at all, refuses the claim."""
    out = []
    for claim in sewing_claims(text):
        allowed = (SEWING_NONE,) if claim == SEWING_NONE else (SEWING_NONE, SEWING_LOW)
        if reading not in allowed:
            word = "no sew" if claim == SEWING_NONE else "low sew"
            out.append(f"SEW_CLAIM_UNCERTIFIED: {where} {text!r} says {word!r}, but the "
                       f"certified construction.sewing_required reading is {reading!r}")
    return out


def closed_by_join(cir: CIR, result, name: str) -> bool:
    """True when `name`'s last round is shut by a fold-and-close row or a full-width join."""
    comp = next((c for c in cir.components if c.name == name), None)
    if comp is None:
        return False
    kind, _ = join_edge(comp, result)
    if kind == "fold":
        return True
    return any(r.full_round and name in (r.host, r.target) for r in runs(cir, result))
