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

from .compiler import ERROR, Finding
from .model import CIR, Op, OpNode, Repeat

_ROW_RE = re.compile(r"^(Row|Rnd)\s+(\d+):\s*(.+?)\s*$", re.I)
_COUNT_RE = re.compile(r"\((\d+)\s*sts?\)\s*$", re.I)
_TURN_RE = re.compile(r"^Ch\s+(\d+)(,\s*turn)?\.\s*", re.I)
_NOTE_RE = re.compile(r"\s+--\s+.*$")

_UK_TO_US = {
    "dc": "sc", "htr": "hdc", "tr": "dc", "dtr": "tr", "ss": "slst", "miss": "sk",
    "dc inc": "inc", "dc dec": "dec", "tr inc": "dc_inc", "tr dec": "dc_dec",
}


@dataclass
class ParsedRow:
    label: str
    index: int
    ops: list[OpNode]
    declared_count: int | None = None
    turning_chain: int = 0


@dataclass
class ParseProblem(Exception):
    message: str
    line: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.message} in {self.line!r}"


def _norm_code(code: str, terminology: str) -> str:
    code = code.strip().lower()
    if terminology.upper() == "UK":
        return _UK_TO_US.get(code, code)
    return code


def _parse_op(text: str, terminology: str) -> Op:
    t = " ".join(text.split())

    m = re.fullmatch(r"ch\s+(\d+)", t, re.I)
    if m:
        return Op("ch", int(m.group(1)))

    m = re.fullmatch(r"(?:sk|miss)\s+next\s+(\d+)\s+sts", t, re.I)
    if m:
        return Op("sk", int(m.group(1)))
    if re.fullmatch(r"(?:sk|miss)\s+next\s+st", t, re.I):
        return Op("sk", 1)

    # decreases: "dec over next 2 sts" optionally "x N"
    m = re.fullmatch(r"([a-z_ ]+?)\s+over\s+next\s+2\s+sts(?:\s*x\s*(\d+))?", t, re.I)
    if m:
        return Op(_norm_code(m.group(1), terminology), int(m.group(2) or 1))

    m = re.fullmatch(r"([a-z_ ]+?)\s+in\s+next\s+(\d+)\s+sts", t, re.I)
    if m:
        return Op(_norm_code(m.group(1), terminology), int(m.group(2)))

    m = re.fullmatch(r"([a-z_ ]+?)\s+in\s+next\s+st", t, re.I)
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


def parse_pattern(text: str, terminology: str = "US") -> list[ParsedRow]:
    """Parse customer-facing text with no knowledge of the source CIR.

    Expands row-level repeats as it goes, so the caller always sees the full row sequence a
    maker would work. A reader that skipped the expansion would report a collapsed pattern as
    ninety rows short, which is worse than not supporting it at all.
    """
    rows: list[ParsedRow] = []
    for raw in text.splitlines():
        repeat = parse_row_repeat(raw)
        if repeat is not None:
            start, end, times = repeat
            block = [r for r in rows if start <= r.index <= end]
            if len(block) != end - start + 1:
                raise ParseProblem(
                    f"the text says to repeat rows {start}-{end}, but only "
                    f"{len(block)} of those rows appear above it")
            next_index = rows[-1].index + 1 if rows else 1
            for _ in range(times):
                for r in block:
                    rows.append(ParsedRow(r.label, next_index, list(r.ops),
                                          r.declared_count, r.turning_chain))
                    next_index += 1
            continue

        line = _NOTE_RE.sub("", raw).strip()
        m = _ROW_RE.match(line)
        if not m:
            continue
        label, index, rest = m.group(1), int(m.group(2)), m.group(3)

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

        rows.append(ParsedRow(label, index, ops, count, tc))
    return rows


# ---- structural comparison -------------------------------------------------


def _shape(node: OpNode) -> tuple:
    if isinstance(node, Op):
        return ("op", node.stitch, node.count)
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

    canonical = [(c, r) for c, r in cir.iter_rows()]
    by_index: dict[int, ParsedRow] = {}
    for p in parsed:
        if p.index in by_index and len(canonical) > len(parsed):
            pass
        by_index.setdefault(p.index, p)

    if len(parsed) != len(canonical):
        findings.append(
            Finding(
                ERROR,
                "REVERSE_ROW_COUNT",
                f"customer text has {len(parsed)} rows but the CIR has {len(canonical)}",
            )
        )

    for (comp, row), p in zip(canonical, parsed):
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
