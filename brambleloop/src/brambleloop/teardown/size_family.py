"""All-size parse before single-size render (F-755) and schematic cross-check (F-756).

Promoted from the research parser that read commercial benchmark 2 (`research/bench2/
product_truth.py`), without its document-specific regexes:

* **F-755.** A graded pattern writes every count as a size vector, `6(6,7,7,8,8,9,9,11,11)`.
  `all_size_parse` finds every vector on every page, settles the family's size count from the
  size labels (or the modal vector length when no labels were read), and reports each vector
  whose length is not that count (an indexing error: a size dropped or doubled), each page
  whose parentheses do not balance (a parenthetical error), and each vector that shrinks from
  one size to the next (a grading reversal to review: a neck can legitimately stay flat, but
  it rarely gets smaller as the child grows). `freeze_render_size` refuses to pick one size to
  render or benchmark until the family is consistent or every problem has a recorded
  resolution -- an ambiguity is resolved in writing, never silently.
* **F-756.** `schematic_cross_check` reconciles stated measurements (a schematic or a size
  chart) against the measurements counts x gauge imply, per size: AGREE within tolerance,
  CONFLICT outside it, UNKNOWN when either side is missing. It never chooses a side; the
  caller gets the disagreement. `benchmark1_cross_check` runs it over the encoded commercial
  benchmark 1 (`cir.benchmarks`) across all nine sizes.

Every value returned is a number, a page number or a key: no text from a purchased document.
"""
from __future__ import annotations

import re
from collections import Counter

AGREE, CONFLICT, UNKNOWN = "AGREE", "CONFLICT", "UNKNOWN"
_NUM = r"(?:\d+(?:\.\d+)?|-|x)"
SIZE_VECTOR = re.compile(rf"(?<![\w.])({_NUM})\s*\(\s*({_NUM}(?:\s*,\s*{_NUM})+)\s*\)")


class SizeFamilyRefused(ValueError):
    """A single size chosen before the whole family was parsed and found consistent."""


def _value(tok: str) -> float | None:
    tok = tok.strip()
    return None if tok in ("-", "x", "") else float(tok)


def size_vectors(text: str) -> list[list[float | None]]:
    """Every size vector in `text`, first value outside the parentheses. None = not this size."""
    return [[_value(m.group(1))] + [_value(t) for t in m.group(2).split(",")]
            for m in SIZE_VECTOR.finditer(text or "")]


def all_size_parse(pages: list[str], *, sizes: int | None = None) -> dict:
    """Parse and consistency-check the whole size family, page by page (F-755)."""
    found: list[tuple[int, list[float | None]]] = []
    unbalanced: list[int] = []
    for number, text in enumerate(pages, start=1):
        if (text or "").count("(") != (text or "").count(")"):
            unbalanced.append(number)
        found.extend((number, v) for v in size_vectors(text))
    if not found:
        return {"state": UNKNOWN, "sizes": sizes, "vectors": 0, "problems": [],
                "why": "no size vectors found: single-size, or unreadable"}
    lengths = Counter(len(v) for _p, v in found)
    n = sizes or lengths.most_common(1)[0][0]
    problems: list[dict] = []
    for i, (page, vec) in enumerate(found):
        if len(vec) != n:
            problems.append({"id": f"indexing:{i}", "kind": "indexing", "page": page,
                             "values": len(vec), "sizes": n})
            continue
        known = [x for x in vec if x is not None]
        drops = [j for j in range(1, len(known)) if known[j] < known[j - 1]]
        if drops:
            problems.append({"id": f"reversal:{i}", "kind": "grading_reversal", "page": page,
                             "at": drops, "values": known})
    problems += [{"id": f"parenthetical:{p}", "kind": "parenthetical", "page": p}
                 for p in unbalanced]
    blocking = [p for p in problems if p["kind"] in ("indexing", "parenthetical")]
    return {"state": CONFLICT if blocking else AGREE, "sizes": n, "vectors": len(found),
            "vector_lengths": dict(sorted(lengths.items())), "problems": problems,
            "blocking": [p["id"] for p in blocking]}


def numeric_summary(family: dict) -> dict:
    """The parse as numbers and booleans only, for a reading that may hold no strings."""
    def pages(kind: str) -> list[int]:
        return sorted({p["page"] for p in family.get("problems", []) if p["kind"] == kind})

    return {"parsed": family.get("state") != UNKNOWN,
            "consistent": None if family.get("state") == UNKNOWN
            else family.get("state") == AGREE,
            "sizes": family.get("sizes"), "vectors": family.get("vectors", 0),
            "indexing_error_pages": pages("indexing"),
            "parenthetical_error_pages": pages("parenthetical"),
            "grading_reversal_pages": pages("grading_reversal")}


def freeze_render_size(family: dict, size_index: int, *,
                       resolutions: dict[str, str] | None = None) -> dict:
    """Choose one size to render/benchmark, only after the whole family checks (F-755)."""
    resolutions = dict(resolutions or {})
    if family.get("state") == UNKNOWN:
        raise SizeFamilyRefused("the size family was never parsed; a single-size render "
                                "would hide indexing and grading errors (F-755)")
    unresolved = [b for b in family.get("blocking", []) if not resolutions.get(b)]
    if unresolved:
        raise SizeFamilyRefused(f"the size family has unresolved problems {unresolved}; "
                                f"record a resolution for each before freezing a size")
    n = int(family.get("sizes") or 0)
    if not 0 <= size_index < n:
        raise SizeFamilyRefused(f"size {size_index} is not in a {n}-size family")
    return {"size_index": size_index, "of": n, "resolved": sorted(resolutions),
            "reviewed_reversals": [p["id"] for p in family.get("problems", [])
                                   if p["kind"] == "grading_reversal"]}


def schematic_cross_check(stated: dict[str, list], derived: dict[str, list], *,
                          tolerance: float = 0.06, absolute: float = 0.0) -> dict:
    """Stated measurements vs counts x gauge, per measure and size (F-756). Never picks one."""
    per: dict[str, list[dict]] = {}
    for name in sorted(set(stated) | set(derived)):
        s, d = list(stated.get(name) or []), list(derived.get(name) or [])
        rows = []
        for i in range(max(len(s), len(d))):
            a = s[i] if i < len(s) else None
            b = d[i] if i < len(d) else None
            if a is None or b is None:
                verdict = UNKNOWN
            else:
                gap = abs(float(a) - float(b))
                verdict = AGREE if (gap <= absolute or
                                    (float(a) and gap / abs(float(a)) <= tolerance)) else CONFLICT
            rows.append({"size": i, "stated": a, "derived": b, "verdict": verdict})
        per[name] = rows
    conflicts = [(k, r["size"]) for k, rows in per.items() for r in rows
                 if r["verdict"] == CONFLICT]
    unknown = [(k, r["size"]) for k, rows in per.items() for r in rows
               if r["verdict"] == UNKNOWN]
    state = CONFLICT if conflicts else (UNKNOWN if unknown else AGREE)
    return {"state": state, "per_measure": per, "conflicts": conflicts, "unknown": unknown,
            "tolerance": tolerance}


def benchmark1_cross_check() -> dict:
    """Commercial benchmark 1's stated schematic against its own counts x gauge, all sizes."""
    from ..cir import benchmarks as B

    derived = {"length_cm": [], "back_width_cm": [], "armhole_cm": []}
    for size in B.SIZES:
        r = B.reconcile(size)
        derived["length_cm"].append(r["length_cm"])
        derived["back_width_cm"].append(r["back_width_cm"])
        # The armhole is bridged by chains whose gauge the pattern never states: the
        # derivation needs a number nobody gave, so it is UNKNOWN, not the stitch-gauge guess.
        derived["armhole_cm"].append(None)
    stated = {"length_cm": list(B.STATED_LENGTH), "back_width_cm": list(B.STATED_BACK_W),
              "armhole_cm": list(B.STATED_ARMHOLE)}
    return {"sizes": list(B.SIZES), **schematic_cross_check(stated, derived)}
