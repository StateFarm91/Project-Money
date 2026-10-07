"""Reverse compiler: customer-facing text -> CIR, then diff against canonical.

Master Plan section 3: "A separate Reverse Compiler sees only the customer pattern and must
reconstruct CIR."

This is the check that a PDF edit, a translation slip, a copy tweak or a bad merge cannot
quietly ship instructions that differ from the validated design. It parses the text with no
knowledge of the source CIR, then a comparator diffs the two structures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import stitches
from .compiler import ERROR, Finding
from .model import CIR, Op, OpNode, Repeat

_ROW_RE = re.compile(r"^(Row|Rnd)\s+(\d+)(?:\s*\(([^)]*)\))?:\s*(.+?)\s*$", re.I)
_COUNT_RE = re.compile(r"\((\d+)\s*sts?\)\s*$", re.I)
_TURN_RE = re.compile(r"^Ch\s+(\d+)(,\s*turn)?\.\s*", re.I)
_NOTE_RE = re.compile(r"\s+--\s+.*$")

_UK_TO_US = {
    "dc": "sc", "htr": "hdc", "tr": "dc", "dtr": "tr", "ss": "slst", "miss": "sk",
    "dc inc": "inc", "dc dec": "dec", "tr inc": "dc_inc", "tr dec": "dc_dec",
    # The post stitches, the half-treble increase and the named star stitches. Absent until
    # 2026-09-26, so a UK document of the cable throw raised an unknown-stitch crash instead
    # of either round-tripping or reporting a parse problem.
    "fptr": "fpdc", "bptr": "bpdc", "htr inc": "hdc_inc",
    "beg star st": "beg_star_st", "star st": "star_st", "end star st": "end_star_st",
    "3 htr in next st": "hdc3",
}


@dataclass
class ParsedRow:
    label: str
    index: int
    ops: list[OpNode]
    declared_count: int | None = None
    turning_chain: int = 0
    color: str | None = None
    # The piece this row belongs to, from the nearest "## name" heading above it. None for a
    # one-piece pattern the writer prints without a heading.
    component: str | None = None


# "## sleeve (make 2)". A heading starts a new piece, and row numbers restart with it, so
# nothing below one heading may be read as belonging to the piece above it.
_HEADING_RE = re.compile(r"^##\s+(.+?)(?:\s+\(make\s+(\d+)\))?\s*$", re.I)
# Headings that are sections of the document rather than pieces of the object.
_SECTION_HEADINGS = {"assembly", "finishing"}
_HOLD_RE = re.compile(r"(\d+)\s+sts\s+\(sts\s+(\d+)-(\d+)\)\s+for\s+([a-z0-9 _]+?)(?=,|\s+on\s+a)",
                      re.I)
_RESUME_RE = re.compile(r"^Rejoin yarn to the sts held for (.+?) and work", re.I)
# F-750: the piece's work direction, in this reader's own grammar.
_DIRECTION_RE = re.compile(r"^Worked from (the bottom up|the top down|side to side|"
                           r"the centre out)\.$", re.I)
_DIRECTIONS = {"the bottom up": "bottom_up", "the top down": "top_down",
               "side to side": "side_to_side", "the centre out": "centre_out"}


@dataclass
class ParsedPiece:
    """What the document says about one piece beyond its rows."""

    name: str
    make: int = 1
    holds: list[tuple[str, int, int, int]] = field(default_factory=list)  # name,row,count,from
    resumes: str | None = None
    direction: str | None = None


def parse_pieces(text: str) -> dict[str | None, ParsedPiece]:
    """Every piece the document names, with its make count, holds and resume, in order.

    Its own reading of the headings and the division sentences, sharing nothing with the
    writer. The hold sentence follows the row it belongs to, so the row number is the last
    row read above it in the same piece.
    """
    pieces: dict[str | None, ParsedPiece] = {None: ParsedPiece(name="")}
    current: str | None = None
    last_row: int | None = None
    for raw in text.splitlines():
        line = raw.strip()
        h = _HEADING_RE.match(line)
        if h:
            name = h.group(1).strip()
            if name.lower() in _SECTION_HEADINGS:
                current, last_row = "\x00section", None
                continue
            if name in pieces:
                raise ParseProblem(f"the piece {name!r} is headed twice", line)
            current, last_row = name, None
            pieces[name] = ParsedPiece(name=name, make=int(h.group(2) or 1))
            continue
        if current == "\x00section":
            continue
        m = _ROW_RE.match(_NOTE_RE.sub("", line))
        if m:
            last_row = int(m.group(2))
            continue
        dm = _DIRECTION_RE.match(line)
        if dm:
            pieces[current].direction = _DIRECTIONS[dm.group(1).lower()]
            continue
        r = _RESUME_RE.match(line)
        if r:
            pieces[current].resumes = " ".join(r.group(1).split())
            continue
        if line.lower().startswith("place ") and "stitch holder" in line.lower():
            if last_row is None:
                raise ParseProblem("stitches are placed on hold before any row", line)
            for count, a, b, name in _HOLD_RE.findall(line):
                count, a, b = int(count), int(a), int(b)
                if b - a + 1 != count:
                    raise ParseProblem(
                        f"the text holds {count} sts but numbers them {a}-{b}", line)
                pieces[current].holds.append((" ".join(name.split()), last_row, count, a - 1))
    return pieces


@dataclass
class ParseProblem(Exception):
    message: str
    line: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.message} in {self.line!r}"


def _norm_code(code: str, terminology: str) -> str:
    code = " ".join(code.strip().lower().split())
    if terminology.upper() == "UK":
        code = _UK_TO_US.get(code, code)
    try:
        stitches.get(code)
    except KeyError:
        # A stitch nobody defined is a document problem, reported like any other, rather
        # than an exception that takes the whole release chain down with it.
        raise ParseProblem(f"unknown stitch {code!r}") from None
    return code


# "hdc in back loop of next 12 sts", "dec in front loop over next 2 sts". Read with its own
# pattern rather than the writer's: the loop is count-neutral, so a document that lost it
# would pass every count check while describing a different fabric.
_LOOP_RE = re.compile(
    r"([a-z_0-9 ]+?)\s+in\s+(back|front)\s+loops?(?:\s+only)?\s+(of|over)\s+(next\s+.+)",
    re.I)


def _parse_op(text: str, terminology: str) -> Op:
    t = " ".join(text.split())

    m = _LOOP_RE.fullmatch(t)
    if m:
        code, loop, joiner, rest = m.group(1), m.group(2).lower(), m.group(3).lower(), m.group(4)
        # Re-read as the plain instruction, then carry the loop. "of next" is how a
        # one-for-one stitch is written; "over next" is a stitch consuming several.
        plain = _parse_op(f"{code} {'in' if joiner == 'of' else 'over'} {rest}", terminology)
        if plain.stitch in ("ch", "sk"):
            raise ParseProblem(f"a {plain.stitch} is not worked into a loop: {t!r}")
        plain.loop = loop
        return plain

    m = re.fullmatch(r"ch\s+(\d+)", t, re.I)
    if m:
        return Op("ch", int(m.group(1)))

    m = re.fullmatch(r"(?:sk|miss)\s+next\s+(\d+)\s+sts", t, re.I)
    if m:
        return Op("sk", int(m.group(1)))
    if re.fullmatch(r"(?:sk|miss)\s+next\s+st", t, re.I):
        return Op("sk", 1)

    # Anything that consumes more than one stitch: "dec over next 2 sts", "cable2x2 over
    # next 4 sts", optionally "x N". The consumed count is checked against the stitch's own
    # definition rather than trusted, because a document claiming a crossing over three
    # stitches describes a manoeuvre that does not exist.
    m = re.fullmatch(r"([a-z_0-9 ]+?)\s+over\s+next\s+(\d+)\s+sts(?:\s*x\s*(\d+))?",
                     t, re.I)
    if m:
        code = _norm_code(m.group(1), terminology)
        stated = int(m.group(2))
        try:
            declared = stitches.get(code).consumes
        except KeyError:
            raise ParseProblem(f"unknown stitch {code!r} in {t!r}") from None
        if stated != declared:
            raise ParseProblem(
                f"the text works {code} over {stated} stitches, but a {code} consumes "
                f"{declared}")
        return Op(code, int(m.group(3) or 1))

    m = re.fullmatch(r"([a-z_0-9 ]+?)\s+in\s+next\s+(\d+)\s+sts", t, re.I)
    if m:
        return Op(_norm_code(m.group(1), terminology), int(m.group(2)))

    m = re.fullmatch(r"([a-z_0-9 ]+?)\s+in\s+next\s+st", t, re.I)
    if m:
        return Op(_norm_code(m.group(1), terminology), 1)

    raise ParseProblem(f"unrecognised instruction {t!r}")


def _split_top_level(body: str) -> list[str]:
    """Split on commas that are not inside [] brackets."""
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _parse_body(body: str, terminology: str) -> list[OpNode]:
    body = body.strip().rstrip(".")
    nodes: list[OpNode] = []

    # Magic-ring opening round: "6 sc in magic ring" is structurally a run of 6 sc.
    m = re.fullmatch(r"(\d+)\s+([a-z_ ]+?)\s+in\s+magic\s+ring", body, re.I)
    if m:
        return [Op(_norm_code(m.group(2), terminology), int(m.group(1)))]
    if re.search(r"\bin\s+magic\s+ring\b", body, re.I):
        body = re.sub(r"\s+in\s+magic\s+ring\b", "", body, flags=re.I).strip()

    # To-end repeat: *inner; rep from * to end
    m = re.search(r"\*(.+?);\s*rep\s+from\s+\*\s+to\s+end", body, re.I)
    if m:
        before = body[: m.start()].strip().rstrip(",").strip()
        after = body[m.end():].strip().lstrip(",").strip()
        for chunk in _split_top_level(before):
            nodes.append(_parse_op(chunk, terminology))
        inner = [_parse_op(c, terminology) for c in _split_top_level(m.group(1))]
        nodes.append(Repeat(ops=inner, times=None))
        for chunk in _split_top_level(after):
            nodes.append(_parse_op(chunk, terminology))
        return nodes

    for chunk in _split_top_level(body):
        rm = re.fullmatch(r"\[(.+)\]\s*x\s*(\d+)", chunk, re.I)
        if rm:
            inner = [_parse_op(c, terminology) for c in _split_top_level(rm.group(1))]
            nodes.append(Repeat(ops=inner, times=int(rm.group(2))))
        else:
            nodes.append(_parse_op(chunk, terminology))
    return nodes


# "Repeat rows 25-48 3 more times" / "once more". The reader has to understand this or a
# collapsed pattern looks like a pattern missing ninety rows. Parsed here, in the reader, from
# the customer text alone -- the writer does not hand over the expansion, because then the two
# would no longer be independent and the whole check would be circular.
_ROW_REPEAT_RE = re.compile(
    r"repeat\s+rows?\s+(\d+)\s*[-\u2013to]+\s*(\d+)\s+"
    r"(?:(once)\s+more|(\d+)\s+more\s+times)", re.I)


def parse_row_repeat(line: str) -> tuple[int, int, int] | None:
    """(start, end, further_passes) from a repeat instruction, or None."""
    m = _ROW_REPEAT_RE.search(line)
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    times = 1 if m.group(3) else int(m.group(4))
    if end < start or times < 1:
        raise ParseProblem(
            f"nonsensical row repeat: rows {start}-{end} {times} more times")
    return start, end, times


_SPIRAL_RE = re.compile(r"\b(continuous\s+spiral|do\s+not\s+join)\b", re.I)
_JOIN_RE = re.compile(r"\bjoin\s+each\s+round\b", re.I)


class ProblemInPlacement(ParseProblem):
    """A placement clause that cannot describe a real join."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def parse_construction(text: str) -> str | None:
    """"spiral_rounds", "joined_rounds", or None when the text does not say.

    Read from the customer text alone, like everything else here. Joining leaves a seam and
    spiralling does not, so a document that tells a maker to do the opposite of what was
    validated produces a different object from the one on the listing.
    """
    spiral = bool(_SPIRAL_RE.search(text))
    joined = bool(_JOIN_RE.search(text))
    if spiral and joined:
        raise ParseProblem("the text says both to work in a continuous spiral and to join "
                           "each round; a maker cannot do both")
    if spiral:
        return "spiral_rounds"
    if joined:
        return "joined_rounds"
    return None


# The finishing, read back out of the document. Its own grammar, its own vocabulary table:
# the writer's map from method to verb is not imported here, because a round trip through
# shared code proves nothing (B-005).
_STEP_RE = re.compile(r"^Step\s+(\d+):\s*(.+?)\s*$", re.I)
_SELF_SEAM_RE = re.compile(r"the two edges of the (.+?) together", re.I)
_TWO_PIECE_RE = re.compile(r"the (.+?) to the (.+?)(?:\s+across|[.,])", re.I)
# Placement, read back out of the sentence. Its own patterns, not the writer's: a round trip
# through shared code proves nothing (B-005).
_SPAN_RE = re.compile(r"across (?:rounds?|rows?)\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?", re.I)
_CENTRE_RE = re.compile(r"(\d+)\s+sts\s+either\s+side\s+of\s+centre", re.I)
_MIRRORED_RE = re.compile(r"\bmirrored\b", re.I)
_METHOD_WORDS = {
    "whipstitch": "whipstitch",
    "slip stitch": "slst",
    "mattress stitch": "mattress",
    "sew": "sew",
}


def parse_assembly(text: str) -> list[tuple]:
    """Finishing steps in the order the document gives them.

    Each step is (method, piece_a, piece_b, at_round, spans_rounds, stitches_from_centre,
    mirrored), with the placement fields None or defaulted when the sentence does not say.
    """
    steps: list[tuple] = []
    for raw in text.splitlines():
        m = _STEP_RE.match(raw.strip())
        if not m:
            continue
        body = m.group(2)
        method = None
        for phrase, code in _METHOD_WORDS.items():
            if body.lower().startswith(phrase):
                method = code
                break
        if method is None:
            raise ParseProblem(f"unrecognised finishing method in {body!r}")
        span = _SPAN_RE.search(body)
        at_round = int(span.group(1)) if span else None
        spans = 1
        if span and span.group(2):
            spans = int(span.group(2)) - int(span.group(1)) + 1
            if spans < 1:
                raise ProblemInPlacement(
                    f"finishing step spans rounds {span.group(1)} to {span.group(2)}, "
                    f"which is backwards")
        centre = _CENTRE_RE.search(body)
        from_centre = int(centre.group(1)) if centre else None
        mirrored = bool(_MIRRORED_RE.search(body))

        self_seam = _SELF_SEAM_RE.search(body)
        if self_seam:
            piece = self_seam.group(1).strip()
            steps.append((method, piece, piece, at_round, spans, from_centre, mirrored))
            continue
        pair = _TWO_PIECE_RE.search(body)
        if not pair:
            raise ParseProblem(f"finishing step does not say which pieces it joins: {body!r}")
        steps.append((method, pair.group(1).strip(), pair.group(2).strip(),
                      at_round, spans, from_centre, mirrored))
    return steps


# The fibre content, read back out of the document. Its own patterns and its own vocabulary
# check, because a round trip through the writer's formatting proves nothing (B-005). This
# file deliberately does not import `cir.writer.material_line`; it reads percent signs.
_MATERIALS_LINE_RE = re.compile(r"^Materials:\s*(.+?)\s*$", re.I | re.M)
_FIBRE_PCT_RE = re.compile(r"(\d{1,3})\s*%\s*([A-Za-z]+)")


def parse_fibre_content(text: str) -> tuple[tuple[tuple[str, int], ...], ...]:
    """Each material's stated composition, in document order. `()` when none is stated.

    Returns one entry per material the Materials line lists -- an empty tuple for a material
    that states no composition, so a document that states it for the first yarn and not the
    second is distinguishable from one that states it for neither. That distinction is the
    reason this returns a shape rather than a flat set: "unstated" and "stated as something
    else" need different fixes, and a reader that flattens them can tell you only that
    something is wrong.

    Read with no knowledge of the CIR and with no knowledge of how the writer spelled it.
    A percent sign followed by a word is the only thing this looks for, which is a grammar a
    human retyping the line would also satisfy, and it is the property that makes this a
    check rather than a comparison of one function with itself.

    `ParseProblem` on a percentage a composition cannot have. A document is allowed to be
    silent; it is not allowed to say something arithmetically impossible, because that is a
    document a buyer would read and act on.
    """
    match = _MATERIALS_LINE_RE.search(text or "")
    if not match:
        return ()
    out: list[tuple[tuple[str, int], ...]] = []
    for chunk in match.group(1).split(";"):
        pairs: list[tuple[str, int]] = []
        seen: set[str] = set()
        for raw_percent, raw_fibre in _FIBRE_PCT_RE.findall(chunk):
            fibre = raw_fibre.lower()
            percent = int(raw_percent)
            if not 1 <= percent <= 100:
                raise ParseProblem(
                    f"the materials line states {fibre!r} at {percent}%, which is not a "
                    f"share of a yarn", chunk.strip())
            if fibre in seen:
                raise ParseProblem(
                    f"the materials line states {fibre!r} twice for one yarn", chunk.strip())
            seen.add(fibre)
            pairs.append((fibre, percent))
        if pairs and sum(p for _, p in pairs) != 100:
            raise ParseProblem(
                f"the materials line states a fibre content summing to "
                f"{sum(p for _, p in pairs)}%, not 100%", chunk.strip())
        out.append(tuple(pairs))
    return tuple(out)


def parse_pattern(text: str, terminology: str = "US") -> list[ParsedRow]:
    """Parse customer-facing text with no knowledge of the source CIR.

    Expands row-level repeats as it goes, so the caller always sees the full row sequence a
    maker would work. A reader that skipped the expansion would report a collapsed pattern as
    ninety rows short, which is worse than not supporting it at all.
    """
    rows: list[ParsedRow] = []
    carried_color: str | None = None
    # Row numbers restart with every piece, so a repeat instruction refers to the rows of the
    # piece it is written in. Reading "repeat rows 3-8" against every row above it -- the
    # body's rows 3-8 *and* the sleeve's -- found twelve rows where six were meant and
    # refused every multi-piece pattern with a row cycle.
    current: str | None = None
    for raw in text.splitlines():
        heading = _HEADING_RE.match(raw.strip())
        if heading:
            name = heading.group(1).strip()
            current = None if name.lower() in _SECTION_HEADINGS else name
            carried_color = None
            continue
        repeat = parse_row_repeat(raw)
        if repeat is not None:
            start, end, times = repeat
            scope = [r for r in rows if r.component == current]
            block = [r for r in scope if start <= r.index <= end]
            if len(block) != end - start + 1:
                raise ParseProblem(
                    f"the text says to repeat rows {start}-{end}, but only "
                    f"{len(block)} of those rows appear above it")
            next_index = scope[-1].index + 1 if scope else 1
            for _ in range(times):
                for r in block:
                    rows.append(ParsedRow(r.label, next_index, list(r.ops),
                                          r.declared_count, r.turning_chain, r.color,
                                          current))
                    next_index += 1
            continue

        line = _NOTE_RE.sub("", raw).strip()
        m = _ROW_RE.match(line)
        if not m:
            continue
        label, index, stated_color, rest = (
            m.group(1), int(m.group(2)), m.group(3), m.group(4))
        # A colour is named when it changes and carried forward until it changes again,
        # which is how patterns are written and how a maker reads them.
        if stated_color:
            carried_color = stated_color.strip() or None

        count = None
        cm = _COUNT_RE.search(rest)
        if cm:
            count = int(cm.group(1))
            rest = rest[: cm.start()].strip()

        tc = 0
        tm = _TURN_RE.match(rest)
        if tm:
            tc = int(tm.group(1))
            rest = rest[tm.end():].strip()

        try:
            ops = _parse_body(rest, terminology)
        except ParseProblem as e:
            e.line = raw
            raise

        rows.append(ParsedRow(label, index, ops, count, tc, carried_color, current))
    return rows


# ---- structural comparison -------------------------------------------------


def _shape(node: OpNode) -> tuple:
    # The loop is part of the instruction: a back-loop row and a both-loops row have the
    # same counts and different fabric, and a comparison blind to it passes the wrong one.
    if isinstance(node, Op):
        return ("op", node.stitch, node.count, node.loop)
    return ("rep", node.times, tuple(_shape(o) for o in node.ops))


def _shape_all(nodes: list[OpNode]) -> tuple:
    return tuple(_shape(n) for n in nodes)


def compare(cir: CIR, text: str, terminology: str = "US") -> list[Finding]:
    """Diff canonical CIR against an independent parse of the customer-facing text."""
    findings: list[Finding] = []
    try:
        parsed = parse_pattern(text, terminology)
    except ParseProblem as e:
        return [
            Finding(ERROR, "REVERSE_PARSE", f"customer text could not be parsed: {e}")
        ]

    # How the rounds are worked is part of the pattern, not presentation. A round-worked CIR
    # whose document says nothing is missing an instruction a maker needs; one whose document
    # says the opposite is describing a different fabric.
    round_components = [c for c in cir.components if c.construction != "flat_rows"]
    if round_components:
        try:
            stated = parse_construction(text)
        except ParseProblem as e:
            return [Finding(ERROR, "REVERSE_PARSE",
                            f"customer text could not be parsed: {e}")]
        expected = {c.construction for c in round_components}
        if stated is None:
            findings.append(Finding(
                ERROR, "REVERSE_CONSTRUCTION_MISSING",
                "the pattern is worked in the round but the customer text never says whether "
                "to join each round or work in a continuous spiral"))
        elif stated not in expected:
            findings.append(Finding(
                ERROR, "REVERSE_CONSTRUCTION_MISMATCH",
                f"customer text describes {stated} but the validated pattern is "
                f"{'/'.join(sorted(expected))}; joining leaves a seam and spiralling does not"))

    # Fibre content is a product fact a buyer acts on -- an allergy, a child's skin, a wash
    # cycle -- so a document that has lost it, gained one nobody validated, or attached it to
    # the wrong yarn is describing a different product. Checked here rather than left to the
    # PDF gate because this is the only reader in the chain that sees the customer's own
    # words without the structure that produced them.
    #
    # Silence on both sides is not a finding. Every CIR in this repository states no
    # composition today and every document prints none, which is the honest pair; making
    # that a finding would report a known gap as a defect eleven times over and bury the
    # real ones. The moment either side says something, they must say the same thing.
    try:
        printed_fibres = parse_fibre_content(text)
    except ParseProblem as e:
        return [Finding(ERROR, "REVERSE_PARSE", f"customer text could not be parsed: {e}")]
    expected_fibres = tuple(tuple(m.fibre_content) for m in cir.materials)
    if (any(expected_fibres) or any(printed_fibres)) and printed_fibres != expected_fibres:
        findings.append(Finding(
            ERROR, "REVERSE_FIBRE_CONTENT",
            f"fibre content differs from the validated design: CIR states "
            f"{[list(f) for f in expected_fibres]}, customer text states "
            f"{[list(f) for f in printed_fibres]}. A composition a buyer reads and acts on "
            f"is a product fact, not presentation"))

    # The finishing is part of the pattern too. A document that has lost its assembly steps
    # leaves a maker with pieces and no object.
    try:
        steps = parse_assembly(text)
    except ParseProblem as e:
        return [Finding(ERROR, "REVERSE_PARSE", f"customer text could not be parsed: {e}")]
    expected_steps = [(s.method, s.piece_a, s.piece_b, s.at_round, s.spans_rounds,
                       s.stitches_from_centre, s.mirrored) for s in cir.assembly]
    if steps != expected_steps:
        findings.append(Finding(
            ERROR, "REVERSE_ASSEMBLY",
            f"finishing differs from the validated design: CIR has {expected_steps}, "
            f"customer text has {steps}"))

    # Piece by piece. Row numbers restart with each piece, so rows are compared within the
    # piece the document heads them under; zipping every row of the pattern against every
    # row of the CIR compared the sleeve's row 1 against whatever happened to sit at that
    # position and could not tell a missing piece from a short one.
    try:
        pieces = parse_pieces(text)
    except ParseProblem as e:
        return [Finding(ERROR, "REVERSE_PARSE", f"customer text could not be parsed: {e}")]
    headed = len(cir.components) > 1 or cir.components[0].name != "body"
    named = [n for n in pieces if n is not None]
    if headed:
        expected_names = [c.name for c in cir.components]
        if named != expected_names:
            findings.append(Finding(
                ERROR, "REVERSE_COMPONENTS",
                f"the document names the pieces {named}, but the validated design has "
                f"{expected_names}"))
        stray = [p for p in parsed if p.component is None]
        if stray:
            findings.append(Finding(
                ERROR, "REVERSE_ROW_COUNT",
                f"customer text has {len(stray)} rows outside any piece"))
    pairs: list[tuple] = []
    total_parsed = 0
    for comp in cir.components:
        key = comp.name if headed else None
        mine = [p for p in parsed if p.component == key]
        total_parsed += len(mine)
        if len(mine) != len(comp.rows):
            findings.append(Finding(
                ERROR, "REVERSE_ROW_COUNT",
                f"customer text has {len(mine)} rows for {comp.name} but the CIR has "
                f"{len(comp.rows)}", comp.name))
        pairs.extend(((comp, row), p) for row, p in zip(comp.rows, mine))
        piece = pieces.get(key)
        if piece is None:
            continue
        if headed and piece.make != comp.make:
            findings.append(Finding(
                ERROR, "REVERSE_MAKE",
                f"the document says to make {piece.make} of {comp.name}; the validated "
                f"design makes {comp.make}", comp.name))
        want_holds = sorted((" ".join(h.name.replace("_", " ").split()), h.at_row, h.count,
                             h.from_stitch) for h in comp.holds)
        if sorted(piece.holds) != want_holds:
            findings.append(Finding(
                ERROR, "REVERSE_HOLD",
                f"stitches held differ from the validated design: CIR holds {want_holds}, "
                f"customer text holds {sorted(piece.holds)}", comp.name))
        if piece.direction != comp.work_direction:
            findings.append(Finding(
                ERROR, "REVERSE_DIRECTION",
                f"the document works {comp.name} {piece.direction!r}; the validated design "
                f"works it {comp.work_direction!r}", comp.name))
        want_resume = comp.resumes.replace("_", " ") if comp.resumes else None
        if piece.resumes != want_resume:
            findings.append(Finding(
                ERROR, "REVERSE_HOLD",
                f"the document resumes {piece.resumes!r}; the validated design resumes "
                f"{want_resume!r}", comp.name))

    for (comp, row), p in pairs:
        if p.index != row.index:
            findings.append(
                Finding(
                    ERROR,
                    "REVERSE_ROW_INDEX",
                    f"customer text row {p.index} does not align with CIR row {row.index}",
                    comp.name,
                    row.index,
                )
            )
            continue

        want, got = _shape_all(row.ops), _shape_all(p.ops)
        if want != got:
            findings.append(
                Finding(
                    ERROR,
                    "REVERSE_MISMATCH",
                    f"instructions differ from the validated design: CIR says {want}, "
                    f"customer text says {got}",
                    comp.name,
                    row.index,
                )
            )

        if row.declared_count is not None and p.declared_count is not None:
            if row.declared_count != p.declared_count:
                findings.append(
                    Finding(
                        ERROR,
                        "REVERSE_COUNT",
                        f"stitch count differs: CIR {row.declared_count}, "
                        f"customer text {p.declared_count}",
                        comp.name,
                        row.index,
                    )
                )

        # Colour is structure, not decoration: in overlay mosaic the colour *is* the motif,
        # so a document that names the wrong yarn produces a different object. Only checked
        # where the text states colours at all, so a single-colour pattern is unaffected.
        if row.color and p.color and row.color != p.color:
            findings.append(
                Finding(
                    ERROR,
                    "REVERSE_COLOR",
                    f"colour differs: CIR works this row in {row.color!r}, customer text "
                    f"says {p.color!r}",
                    comp.name,
                    row.index,
                )
            )

        if row.turning_chain != p.turning_chain:
            findings.append(
                Finding(
                    ERROR,
                    "REVERSE_TURNING_CHAIN",
                    f"turning chain differs: CIR {row.turning_chain}, "
                    f"customer text {p.turning_chain}",
                    comp.name,
                    row.index,
                )
            )

    return findings
