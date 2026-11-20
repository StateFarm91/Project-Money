"""Project tips from failure modes (F-766) -- W4-C14.

"Testing and support failures become concise project tips at the exact points customers are
likely to struggle: tension, markers, joins, symmetry, stitch counts, sizing, seaming and
finishing."

Input is failures already on record: support cases (`SupportCase`, read by
`failures_from_cases`) and tester failures (dicts with `source="test"`). Each is classified
into the eight failure modes by fixed patterns -- no model reads the text -- and grouped by
(product, component, row, mode). A group becomes a tip when it is evidenced:

* one tester failure is enough (a tester is working the released pattern under the programme);
* support needs `MIN_SUPPORT_REPORTERS` distinct customers: one buyer's trouble is that buyer's.

"The exact point" is the row the failure names. With the released CIR the row is checked
against the compiler (a row the pattern does not have refuses the tip) and a stitch-count tip
quotes the compiler's own count for that row. A group with no row is NEEDS_PLACEMENT: it is
real evidence of a struggle, but a tip placed nowhere is not "at the exact point".

Tips are PROPOSED. Support cannot amend a released pattern (`concierge.Concierge.amend`); a tip
reaches a document only through a new, re-validated version. No customer text or reference is
copied into a tip: the evidence is case ids and counts.
"""
from __future__ import annotations

import hashlib
import re

MODES = ("tension", "markers", "joins", "symmetry", "stitch_counts", "sizing", "seaming",
         "finishing")

# Order matters only for reading; a failure may show several modes and counts toward each.
_MODE_PATTERNS: dict[str, re.Pattern] = {
    "tension": re.compile(r"\b(tension|too tight|too loose|tight|loose|curl(s|ing|ed)?|"
                          r"ruffl\w*|wav(y|es)|cupp\w*|puckers?)\b", re.I),
    "markers": re.compile(r"\b(stitch markers?|markers?|lost (my )?place|first stitch of the "
                          r"(round|rnd)|beginning of (the )?(round|rnd))\b", re.I),
    "joins": re.compile(r"\b(join(s|ed|ing)?|jog|colou?r change|slip stitch to)\b", re.I),
    "symmetry": re.compile(r"\b(symmetr\w*|lopsided|mirror\w*|uneven sides?|not matching|"
                           r"doesn'?t match the other)\b", re.I),
    "stitch_counts": re.compile(r"\b(stitch count|count (is|was) (off|wrong)|extra stitch(es)?|"
                                r"missing (a )?stitch(es)?|lost (a )?stitch(es)?|"
                                r"how many stitches|ended up with \d+|have \d+ (stitches|sts))\b",
                                re.I),
    "sizing": re.compile(r"\b(too (big|small|wide|narrow|long|short)|doesn'?t fit|fit(s|ting)?|"
                         r"size|sizing|dimensions?)\b", re.I),
    "seaming": re.compile(r"\b(seam(s|ing)?|sew(ing|n)? (it |the )?(together|up|pieces)|"
                          r"whip ?stitch|mattress stitch|assembl\w*)\b", re.I),
    "finishing": re.compile(r"\b(block(ing|ed)?|weav(e|ing) (in )?(the )?ends|border|edging|"
                            r"finish(ing)?)\b", re.I),
}
_ROW = re.compile(r"\b(?:row|round|rnd)\s+(\d+)\b", re.I)

MIN_SUPPORT_REPORTERS = 2
MAX_TIP_CHARS = 220

# One concise instruction per mode. `{line}` is the pattern's own word (row/round) and `{n}` the
# placement; stitch counts and sizing add the compiler's figure when the CIR is supplied.
_TIP = {
    "tension": "Before {line} {n}: check your tension against the gauge; if the fabric curls "
               "or ruffles here, change hook size rather than stitch count.",
    "markers": "At {line} {n}: place a marker in the first stitch and move it up every {line} "
               "so the {line} start stays visible.",
    "joins": "At {line} {n}: join into the first stitch, not the turning chain, so the join "
             "does not drift.",
    "symmetry": "At {line} {n}: count each side separately before continuing; both halves "
                "should match.",
    "stitch_counts": "End of {line} {n}: count your stitches before moving on.",
    "sizing": "By {line} {n}: measure the piece; if it is off, recheck your gauge before "
              "continuing.",
    "seaming": "At {line} {n}: pin the pieces right sides together before seaming, matching "
               "{line} ends.",
    "finishing": "After {line} {n}: block the piece before adding the border so the edges lie "
                 "straight.",
}


def classify(text: str) -> list[str]:
    """The failure modes a failure's text names, in `MODES` order; empty when none does."""
    return [m for m in MODES if _MODE_PATTERNS[m].search(str(text or ""))]


def _ref_digest(customer_ref: str) -> str:
    return hashlib.sha256(str(customer_ref or "").encode()).hexdigest()[:16]


def failures_from_cases(db, *, product_slug: str | None = None) -> list[dict]:
    """Support cases as failures: row from `detail.cited_rows` or the question's own words."""
    from sqlalchemy import select

    from ..core.models import SupportCase

    out = []
    with db.session() as s:
        q = select(SupportCase)
        if product_slug:
            q = q.where(SupportCase.product_slug == product_slug)
        for c in s.scalars(q.order_by(SupportCase.id)):
            detail = dict(c.detail or {})
            rows = [int(r) for r in detail.get("cited_rows", [])]
            if not rows:
                rows = [int(m) for m in _ROW.findall(c.question or "")]
            out.append({"source": "support", "ref": f"support:{c.id}",
                        "reporter": _ref_digest(c.customer_ref),
                        "product_slug": c.product_slug, "version": c.version,
                        "component": detail.get("component"),
                        "row": rows[0] if rows else None, "text": c.question})
    return out


def _line_word(cir, component: str | None) -> str:
    if cir is None:
        return "row"
    for comp in cir.components:
        if component in (None, comp.name):
            return "round" if str(comp.construction).endswith("rounds") else "row"
    return "row"


def tips(failures, *, cir=None) -> dict:
    """Group failures into evidenced, placed tips. Pure: reads nothing and writes nothing."""
    result = None
    if cir is not None:
        from ..cir.compiler import compile_cir

        result = compile_cir(cir)
    groups: dict[tuple, dict] = {}
    unclassified = []
    for f in failures:
        modes = classify(f.get("text", ""))
        if not modes:
            unclassified.append(f.get("ref"))
            continue
        for mode in modes:
            key = (f.get("product_slug"), f.get("component"), f.get("row"), mode)
            g = groups.setdefault(key, {"tests": [], "support": [], "reporters": set()})
            if f.get("source") == "test":
                g["tests"].append(f.get("ref"))
            else:
                g["support"].append(f.get("ref"))
                g["reporters"].add(f.get("reporter") or f.get("ref"))
    proposed, below, unplaced, refused = [], [], [], []
    for (slug, component, row, mode), g in sorted(
            groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        evidence = {"tests": sorted(g["tests"]), "support_cases": sorted(g["support"]),
                    "distinct_customers": len(g["reporters"])}
        entry = {"product_slug": slug, "component": component, "row": row, "mode": mode,
                 "evidence": evidence}
        if not g["tests"] and len(g["reporters"]) < MIN_SUPPORT_REPORTERS:
            below.append({**entry, "state": "BELOW_EVIDENCE",
                          "why": f"{len(g['reporters'])} customer(s) and no tester failure; "
                                 f"a tip needs a tester failure or {MIN_SUPPORT_REPORTERS} "
                                 f"customers"})
            continue
        if row is None:
            unplaced.append({**entry, "state": "NEEDS_PLACEMENT",
                             "why": "no row is named, so there is no exact point to place a "
                                    "tip at"})
            continue
        comp = component or (cir.components[0].name if cir is not None else None)
        line = _line_word(cir, comp)
        text = _TIP[mode].format(line=line, n=row)
        if result is not None:
            counts = result.counts(comp)
            if not 1 <= int(row) <= len(counts):
                refused.append({**entry, "state": "REFUSED",
                                "why": f"{line} {row} is not in the released pattern "
                                       f"({len(counts)} {line}s in {comp})"})
                continue
            if mode == "stitch_counts":
                text = (f"End of {line} {row}: you should have {counts[int(row) - 1]} "
                        f"stitches; count before moving on.")
        proposed.append({**entry, "component": comp, "state": "PROPOSED", "tip": text,
                         "placement": f"{line} {row}",
                         "checked_against_compiler": result is not None})
    assert all(len(t["tip"]) <= MAX_TIP_CHARS for t in proposed)
    return {"proposed": proposed, "below_evidence": below, "needs_placement": unplaced,
            "refused": refused, "unclassified": [r for r in unclassified if r],
            "note": ("proposals: support cannot amend a released pattern; a tip ships only in "
                     "a re-validated version")}
