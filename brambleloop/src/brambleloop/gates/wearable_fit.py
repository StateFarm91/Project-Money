"""ENG-GARMENT-2: the wearable gates, recomputed from each size's compiled rows and twin.

The family-generic checks, then the family's own (`products.wearables.Engine.gates`):

  GARMENT_STITCH_COUNT    every row declares the compiler's count; every step ends on it.
  GARMENT_SHAPING         flat shaping steps change the count by what they say
                          (`gates.garment_fit.shaping_problems`); a section round changes it by
                          exactly `sections` per round, over exactly the rounds it says.
  GARMENT_SEAM_MISMATCH   recorded seams meet (`gates.garment_fit.seam_problems`, including
                          the generic assembler on the built pieces).
  GARMENT_STEPS_DIFFER    every size is the same steps in the same order.
  GARMENT_SIZE_RUN        the family's built primary measure rises strictly, yarn rises.
  GARMENT_SIZE_CLAIM /
  GARMENT_YARDAGE_CLAIM   every figure the size chart prints is re-derived from the twin.
  GARMENT_DOCUMENT        the parenthesised document, read back per size with this module's
                          own grammar (rounds) or `garment_fit`'s (rows), equals the compiler.
"""
from __future__ import annotations

import re

from .garment_fit import (SAME_CM, GarmentFinding, GarmentVerdict, _f, expand, read_line,
                          seam_problems, shaping_problems, stitch_count_problems)


def section_problems(result, facts, size) -> list[GarmentFinding]:
    out: list[GarmentFinding] = []
    counts = {(r.component, r.index): r.stitch_count for r in result.rows}
    for piece, steps in facts.pieces.items():
        for k, s in enumerate(steps):
            if s.kind in ("spread_dec", "spread_inc"):
                by = s.get("dec" if s.kind == "spread_dec" else "inc")
                sign = -1 if s.kind == "spread_dec" else 1
                prev = counts.get((piece, s.first - 1), steps[k - 1].count if k else None)
                got = counts.get((piece, s.last))
                if prev is None or got is None or got - prev != sign * by:
                    _f(out, "GARMENT_SHAPING", size,
                       f"{piece} round {s.first}: {s.kind} by {by} goes {prev} -> {got}")
                continue
            if s.kind not in ("section_dec", "section_inc"):
                continue
            sections, rounds = s.get("sections"), s.get("rounds")
            start = counts.get((piece, s.first - 1), steps[k - 1].count if k else None)
            sign = -1 if s.kind == "section_dec" else 1
            if s.last - s.first + 1 != rounds:
                _f(out, "GARMENT_SHAPING", size, f"{piece}: {rounds} section rounds recorded "
                                                 f"over rounds {s.first}-{s.last}")
            for i in range(s.first, s.last + 1):
                got = counts.get((piece, i))
                prev = counts.get((piece, i - 1), start)
                if got is None or prev is None or got - prev != sign * sections:
                    _f(out, "GARMENT_SHAPING", size,
                       f"{piece} round {i}: {s.kind} in {sections} sections should change "
                       f"the count by {sign * sections}; it goes {prev} -> {got}")
                    break
    return out


def claim_problems(design, cirs: dict, claims: list[dict]) -> list[GarmentFinding]:
    from ..products.wearables import size_claims

    out: list[GarmentFinding] = []
    truth = {r["size"]: r for r in size_claims(design, cirs)}
    if [c["size"] for c in claims] != list(truth):
        _f(out, "GARMENT_SIZE_CLAIM", "*", f"the chart lists {[c['size'] for c in claims]}; "
                                           f"the design builds {list(truth)}")
    for c in claims:
        t = truth.get(c["size"])
        if t is None:
            continue
        for k, v in t.items():
            if k in ("size", "metres", "yards", "balls", "ball_m", "ball_g", "ball_yd"):
                continue
            if c.get(k) is None or abs(float(c[k]) - float(v)) > SAME_CM:
                _f(out, "GARMENT_SIZE_CLAIM", c["size"],
                   f"the chart prints {k} {c.get(k)}; the twin gives {v}")
        for k in ("metres", "yards", "balls"):
            if c.get(k) != t.get(k):
                _f(out, "GARMENT_YARDAGE_CLAIM", c["size"],
                   f"the chart prints {c.get(k)} {k}; the twin's yarn is {t.get(k)} {k}")
    return out


def evaluate(design, cirs: dict | None = None, *, claims: list[dict] | None = None,
             facts_by_size: dict | None = None) -> GarmentVerdict:
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..products import wearables as WB

    v = GarmentVerdict()
    eng = WB.ENGINES[design.spec.family]
    if cirs is None:
        cirs = {s: design.build(s) for s in design.sourced_sizes()}
    signatures, primaries, yarns = {}, [], []
    for size, cir in cirs.items():
        facts = (facts_by_size or {}).get(size) or WB.facts_of(cir)
        if facts is None:
            _f(v.findings, "GARMENT_STEPS_DIFFER", size, "the size records no steps")
            continue
        result = compile_cir(cir)
        if not result.ok:
            _f(v.findings, "GARMENT_STITCH_COUNT", size,
               f"does not compile: {[str(e) for e in result.errors][:2]}")
            continue
        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        g = design.graded_size(size)
        measured = eng.measure(cir)
        v.findings += stitch_count_problems(cir, result, facts, size)
        v.findings += shaping_problems(cir, result, facts, size)
        v.findings += section_problems(result, facts, size)
        v.findings += seam_problems(cir, result, twins, facts, size)
        v.findings += eng.gates({"design": design, "g": g, "cir": cir, "result": result,
                                 "twins": twins, "facts": facts, "measured": measured,
                                 "size": size})
        signatures[size] = WB.step_signature(cir)
        primaries.append((size, measured.get(eng.built_primary) or 0.0))
        yarns.append((size, sum(sum(t.yarn_metres_by_color.values()) * c.make
                                for c, t in ((c, twins[c.name]) for c in cir.components))))
    if len(set(signatures.values())) > 1:
        first = next(iter(signatures))
        odd = [s for s, sig in signatures.items() if sig != signatures[first]]
        _f(v.findings, "GARMENT_STEPS_DIFFER", ",".join(odd),
           f"sizes {odd} are worked in different steps from size {first}")
    for (a, pa), (b, pb) in zip(primaries, primaries[1:]):
        if not pb > pa:
            _f(v.findings, "GARMENT_SIZE_RUN", b, f"built {eng.built_primary} {pa:.1f} -> "
                                                  f"{pb:.1f} cm from {a} to {b} does not rise")
    for (a, ya), (b, yb) in zip(yarns, yarns[1:]):
        if not yb > ya:
            _f(v.findings, "GARMENT_SIZE_RUN", b, f"yarn {ya:.0f} -> {yb:.0f} m from {a} to "
                                                  f"{b} does not rise")
    if claims is not None:
        v.findings += claim_problems(design, cirs, claims)
    return v


# ---- the document, read back (rounds in this grammar; rows in garment_fit's) ---------------

_NUM = r"\d+(?:-\d+)?"
_VAL = rf"{_NUM}(?: \({_NUM}(?:, {_NUM})*\))?"


def _vals(text: str, n: int) -> list[str]:
    m = re.fullmatch(rf"({_NUM})(?: \(([^()]*)\))?", text.strip())
    if not m:
        raise ValueError(f"not a size value: {text!r}")
    if m.group(2) is None:
        return [m.group(1)] * n
    out = [m.group(1)] + [x.strip() for x in m.group(2).split(",")]
    if len(out) != n:
        raise ValueError(f"{text!r} gives {len(out)} sizes, not {n}")
    return out


def _ints(text, n):
    return [int(x) for x in _vals(text, n)]


def _after(pattern: str, line: str, n: int) -> list[int]:
    m = re.search(pattern.replace("V", f"({_VAL})"), line)
    if not m:
        raise ValueError(f"expected {pattern!r} in {line!r}")
    return _ints(m.group(1), n)


def read_flat_line(line: str, n: int) -> dict:
    """A flat row in the garment grammar, plus the wearable split row (the stitches worked
    are the count after it; the rest are held or left as an edge) and the V-neck yoke."""
    if "increase 1 st at each neck edge" in line:
        m = re.match(rf"^Rows? ({_VAL})", line)
        counts = re.search(rf"\(({_VAL}) sts\)$", line)
        if not m or not counts:
            raise ValueError(f"a yoke line with no rows or count: {line!r}")
        spans = []
        for v in _vals(m.group(1), n):
            a, _, b = v.partition("-")
            spans.append((int(a), int(b or a)))
        return {"text": line, "kind": "vraglan", "rows": spans, "then": None,
                "counts": _ints(counts.group(1), n),
                "doubles": _after(r"work V double raglan", line, n),
                "every": _after(r"on the next row and on every V row", line, n),
                "times": _after(r"after it, V times in all; at the same", line, n),
                "neck_every": _after(r"on the first row and on every V row", line, n),
                "neck": _after(r"after it, V times in all; work every", line, n)}
    out = read_line(line, n)
    if "are held for the" in line and "sts only" in line:
        keep = _after(r"in the first V sts only", line, n)
        out.update(kind="divide", front=[0] * n, back=keep, sleeve=[0] * n)
    return out


def read_round_line(line: str, n: int) -> dict:
    """A round instruction -> {"kind", per-size numbers, "rows", "counts"}."""
    if line.startswith("Pick up") or re.match(r"^Ch \d", line) or line.startswith("Rejoin"):
        return read_line(line, n)
    m = re.match(rf"^Rnds? ({_VAL})", line)
    counts = re.search(rf"\(({_VAL}) sts\)$", line)
    if not m or not counts:
        raise ValueError(f"a round with no rounds or no stitch count: {line!r}")
    spans = []
    for v in _vals(m.group(1), n):
        a, _, b = v.partition("-")
        spans.append((int(a), int(b or a)))
    out = {"text": line, "rows": spans, "counts": _ints(counts.group(1), n), "then": None}
    if "make a magic ring" in line:
        out["kind"] = "ring"
        out["ring"] = _after(r"make a magic ring and work V ", line, n)
    elif re.search(r"(?:de|in)creasing \S", line) and "evenly spaced" in line:
        out["kind"] = "spread"
        out["by"] = _after(r"creasing V sts evenly", line, n)
        out["sign"] = -1 if "decreasing" in line else 1
    elif "fewer in every section" in line or "more in every section" in line:
        out["kind"] = "section"
        out["sections"] = _after(r"in V equal sections", line, n)
        out["sign"] = -1 if "fewer in every section" in line else 1
    else:
        out["kind"] = "even"
    return out


def expand_rounds(parsed: list[dict], size: int) -> tuple[dict[int, int], list[str]]:
    rows: dict[int, int] = {}
    problems: list[str] = []
    count, expect = None, 1
    for p in parsed:
        if p["kind"] in ("pick_up", "resume", "chain"):
            count = p["n"][size] - (1 if p["kind"] == "chain" else 0)
            continue
        a, b = p["rows"][size]
        if a != expect:
            problems.append(f"rounds jump from {expect - 1} to {a} at {p['text'][:50]!r}")
        expect = b + 1
        if p["kind"] == "ring":
            count = p["ring"][size]
            rows[a] = count
            if count != p["counts"][size]:
                problems.append(f"the ring round works {count} sts; the line prints "
                                f"{p['counts'][size]}")
            continue
        if count is None:
            problems.append(f"{p['text'][:40]!r} has no stitches to work into")
            count = p["counts"][size]
        for r in range(a, b + 1):
            if p["kind"] == "section":
                count += p["sign"] * p["sections"][size]
            elif p["kind"] == "spread":
                count += p["sign"] * p["by"][size]
            rows[r] = count
        if rows[b] != p["counts"][size]:
            problems.append(f"{p['text'][:50]!r}: the rounds end on {rows[b]} sts; the line "
                            f"prints {p['counts'][size]}")
    return rows, problems


def expand_flat(parsed: list[dict], size: int) -> tuple[dict[int, int], list[str]]:
    """`garment_fit.expand`, with the V-neck yoke expanded here first (its per-row counts
    replace it as single-row entries the garment grammar's expander already reads)."""
    out: list[dict] = []
    count = None
    for p in parsed:
        k = p["kind"]
        if k == "chain":
            count = p["n"][size] - 1
        elif k in ("pick_up", "resume"):
            count = p["n"][size]
        if k != "vraglan":
            out.append(p)
            if k in ("even",) and count is None:
                count = p["counts"][size]
            elif "counts" in p and k != "setup":
                count = (p["then"] or p["counts"])[size] if p.get("then") else \
                    p["counts"][size]
            continue
        a, b = p["rows"][size]
        d, every, times = p["doubles"][size], p["every"][size], p["times"][size]
        nev, nt = p["neck_every"][size], p["neck"][size]
        for i, r in enumerate(range(a, b + 1)):
            if i < d:
                count += 16
            elif (i - d) % every == 0 and (i - d) // every < times:
                count += 8
            if i % nev == 0 and i // nev < nt:
                count += 2
            n = len(p["counts"])
            vals = [0] * n
            vals[size] = count
            spans = list(p["rows"])
            spans[size] = (r, r)
            out.append({"text": p["text"], "kind": "divide", "rows": spans, "then": None,
                        "counts": [count if j == size else p["counts"][j] for j in range(n)]
                        if r == b else [count] * n,
                        "front": [0] * n, "back": [count] * n, "sleeve": [0] * n})
    return expand(out, size)


def document_problems(pieces_text: dict[str, list[str]], cirs: dict,
                      piece_of: dict[str, str]) -> list[GarmentFinding]:
    """Read the document back per size and compare every row and round with the compiler."""
    from ..cir.compiler import compile_cir

    out: list[GarmentFinding] = []
    sizes = list(cirs)
    n = len(sizes)
    results = {s: compile_cir(c) for s, c in cirs.items()}
    for heading, lines in pieces_text.items():
        comp_name = piece_of.get(heading)
        comp = next((c for c in next(iter(cirs.values())).components
                     if c.name == comp_name), None)
        if comp is None:
            _f(out, "GARMENT_DOCUMENT", "*", f"heading {heading!r} names no piece")
            continue
        rounds = comp.construction != "flat_rows"
        try:
            parsed = [(read_round_line if rounds else read_flat_line)(ln, n) for ln in lines]
        except ValueError as exc:
            _f(out, "GARMENT_DOCUMENT", "*", f"{heading}: {exc}")
            continue
        for i, size in enumerate(sizes):
            rows, problems = (expand_rounds if rounds else expand_flat)(parsed, i)
            for p in problems:
                _f(out, "GARMENT_DOCUMENT", size, f"{heading}: {p}")
            built = {r.index: r.stitch_count for r in results[size].rows
                     if r.component == comp_name}
            if set(rows) != set(built):
                _f(out, "GARMENT_DOCUMENT", size,
                   f"{heading}: the text covers {min(rows, default=0)}-{max(rows, default=0)}; "
                   f"the piece has 1-{max(built, default=0)}")
            for r, c in sorted(rows.items()):
                if built.get(r) != c:
                    _f(out, "GARMENT_DOCUMENT", size,
                       f"{heading} {'round' if rounds else 'row'} {r}: the text gives {c} "
                       f"sts, the compiler {built.get(r)}")
                    break
    return out
