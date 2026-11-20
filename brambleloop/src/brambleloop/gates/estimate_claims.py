"""D-OWNER-ESTIMATE-CLAIMS: gauge and size claims stated truthfully as calculated estimates.

The owner's Master Pattern Template (spec 07, pages 3-4, as relayed in the ENG-ESTIMATE-CLAIMS
brief) sets the standard: "Gauge is specific to this pattern. Measure a swatch before
committing to a size. Where physical calibration is absent, the pattern must state estimates
truthfully" and "Every figure is calculated from certified gauge and stitch geometry."

So when no physical sample of this content exists, a gauge or size claim is publishable only
as what it is: a calculation. This module is the deterministic reading of that rule, applied
to every surface a buyer reads -- both PDFs, the listing copy, and the image alt text. Every
condition must hold, on every surface:

1. **Accuracy.** Every finished-size figure equals a twin figure within
   `risk_matrix.DIMENSION_TOLERANCE`, and every stated gauge equals the CIR's gauge.
2. **Labelling.** Every size claim carries estimate language ("approx.", "calculated", ...),
   and the PDFs and the listing copy carry `ESTIMATE_NOTE` verbatim.
3. **No physical implication.** No claim, and nothing in the listing copy or the alt text,
   says or implies the size was measured on a made piece ("measures", "tested", "as pictured").

It never weakens anything physical. A child-safety physical test (`gates.child_safety`) is not
a size claim and is never waived here: a product that needs one is not eligible for the
estimate path at all, and the first-customer area stays UNRESOLVED for it.

When real physical evidence is bound, this module is not consulted: the gate reads the sample
as before and measured values replace the estimates.
"""
from __future__ import annotations

import re

#: The sentence the PDF gauge section and the listing copy carry when no sample exists.
ESTIMATE_NOTE = ("Measured gauge not yet verified on a physical sample; finished size is "
                 "calculated from the stated gauge. Check your gauge.")

#: The rule's identifier, carried in every check detail it produces.
RULE = "gates.estimate_claims/1"

# Estimate language a size claim must carry. "about" is the yardage convention already in use
# and reads as an estimate to a buyer; "approx." is the template's own word.
_ESTIMATE = re.compile(
    r"\b(?:approx\.?|approximately|about|calculated|computed|estimated?|estimates)(?=\W|$)",
    re.IGNORECASE)

# Words that say or imply a physical measurement of a made piece. Read only after the
# negated phrases below are removed, so "not yet measured" is honest and "measures" is not.
_PHYSICAL = re.compile(
    r"\b(?:measures|measured|measuring\s+(?:at|in\s+at)|tested|tester[- ]?(?:made|tested|"
    r"approved|verified)|as\s+pictured|as\s+shown|true\s+to\s+size|actual\s+(?:size|"
    r"measurements?)|verified\s+(?:size|on\s+a|measurements?)|real[- ]life\s+size|"
    r"sample\s+(?:measures|measured|was\s+measured))\b",
    re.IGNORECASE)

# Phrases that deny a measurement. Removed before `_PHYSICAL` is read; they are the truthful
# disclosure this rule asks for, not a claim of one.
_NEGATED = (
    re.compile(re.escape(ESTIMATE_NOTE), re.IGNORECASE),
    re.compile(r"\bnot\s+yet\s+(?:been\s+)?(?:measured|verified|tested)\b[^.;)]*",
               re.IGNORECASE),
    re.compile(r"\bnot\s+(?:been\s+)?(?:measured|tested|verified)\b[^.;)]*", re.IGNORECASE),
    re.compile(r"\b(?:never|un)(?:measured|tested|verified)\b", re.IGNORECASE),
    re.compile(r"\brather\s+than\s+(?:being\s+)?(?:measured|tested)\b", re.IGNORECASE),
)

# A dimension: a number and a length unit. Inches convert to cm for the accuracy reading.
_DIM = re.compile(r"(\d+(?:\.\d+)?)\s*(cm|mm|in(?:ch(?:es)?)?\b|\")", re.IGNORECASE)
# A segment is a size claim when it states a dimension AND talks about the finished piece.
_SIZE_WORDS = re.compile(r"\b(?:finished|size|measures?|measured|dimensions?|block)\b",
                         re.IGNORECASE)
# "Block the finished piece to 79 x 96 cm" tells the maker the target the calculation gives;
# it is an instruction, not a statement that a made piece measured that. Its figures must
# still be the twin's and it must not imply a measurement, but it needs no estimate word.
_INSTRUCTION = re.compile(r"^\s*block\b[^.;:]{0,40}?\bto\b", re.IGNORECASE)
# The gauge statement: "18 sts x 20 rows = 10 cm" (and its UK and long forms).
_GAUGE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:sts|stitches)\b[^.;=]{0,20}?(\d+(?:\.\d+)?)\s*rows?\s*"
    r"(?:=|to|per|in)\s*10\s*cm", re.IGNORECASE)
# A number that is the gauge's reference length, a body measurement, or a hook size is not a
# finished dimension of the piece.
_NOT_FINISHED = re.compile(
    r"(?:=|per|over|across|in|to)\s*10\s*cm|to\s+fit\b[^.;]*|\d+(?:\.\d+)?\s*mm\s+hook",
    re.IGNORECASE)


# Where one statement ends in text a PDF extractor has collapsed onto one line: a sentence end
# followed by a capital ("approx. 40" is not one), a page footer, or a run of capitals (a
# panel label: "FINISHED SIZE", "YARN") that follows lower-case text or a number.
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"])|\s*©[^\n]*?(?:page\s+\d+\s+of\s+\d+|$)\s*"
                    r"|(?<=[a-z0-9.)\]])\s+(?=[A-Z]{3,}\b)")


def _segments(text: str) -> list[str]:
    """Statements: lines, sentences, and the labelled panels of an extracted PDF."""
    parts: list[str] = []
    for line in (text or "").splitlines():
        parts += _SPLIT.split(line)
    return [p.strip() for p in parts if p and p.strip()]


def _clean(text: str) -> str:
    out = text or ""
    for rx in _NEGATED:
        out = rx.sub(" ", out)
    return out


def size_claims(text: str) -> list[str]:
    """Every segment of `text` that states a finished dimension of the piece."""
    out = []
    for seg in _segments(text):
        if _SIZE_WORDS.search(seg) and claim_figures_cm(seg):
            out.append(seg)
    return out


def claim_figures_cm(claim: str) -> list[float]:
    """The finished-dimension figures a claim states, in cm (gauge length and hooks removed)."""
    figures = []
    for m in _DIM.finditer(_NOT_FINISHED.sub(" ", claim)):
        value, unit = float(m.group(1)), m.group(2).lower()
        if unit == "mm":
            continue                          # a hook or a stitch detail, never a size
        figures.append(value * 2.54 if unit.startswith("in") or unit == '"' else value)
    return figures


def twin_figures(cir, twin) -> list[float]:
    """Every finished dimension the twin computes, the figures a claim may state."""
    figures: list[float] = []
    for name in ("width_cm", "height_cm", "circumference_cm", "across_points_cm",
                 "across_flats_cm", "diameter_cm", "length_cm", "depth_cm"):
        v = getattr(twin, name, None)
        if isinstance(v, (int, float)) and v:
            figures.append(float(v))
    try:
        from .risk_matrix import _is_wearable

        if _is_wearable(cir):
            from ..products.garments import built_measures

            figures += [float(v) for v in built_measures(cir).values()
                        if isinstance(v, (int, float)) and v]
    except Exception:  # noqa: BLE001 - not a generator garment: piece figures only
        pass
    return figures


def _accuracy(where: str, claim: str, figures: list[float], tolerance: float) -> list[str]:
    out = []
    for value in claim_figures_cm(claim):
        if not figures:
            out.append(f"{where}: states {value:g} cm and the twin computes no dimension")
            continue
        best = min(figures, key=lambda f: abs(f - value))
        drift = abs(best - value) / max(value, 1e-9)
        if drift > tolerance:
            out.append(f"{where}: states {value:g} cm; nearest twin figure {best:.1f} cm "
                       f"({drift:.0%} out, tolerance {tolerance:.0%})")
    return out


def _gauge_accuracy(where: str, text: str, cir) -> list[str]:
    g = getattr(cir, "gauge", None)
    out = []
    for m in _GAUGE.finditer(text or ""):
        if g is None:
            out.append(f"{where}: states a gauge and the CIR has none")
            continue
        sts, rows = float(m.group(1)), float(m.group(2))
        if abs(sts - g.stitches_per_10cm) > 1e-6 or abs(rows - g.rows_per_10cm) > 1e-6:
            out.append(f"{where}: states gauge {sts:g} sts x {rows:g} rows = 10 cm; the "
                       f"certified gauge is {g.stitches_per_10cm:g} x {g.rows_per_10cm:g}")
    return out


def _has_note(text: str) -> bool:
    flat = re.sub(r"\s+", " ", text or "").lower()
    return re.sub(r"\s+", " ", ESTIMATE_NOTE).lower() in flat


def physical_implications(text: str) -> list[str]:
    """Words in `text` that imply a physical measurement, once honest negations are removed."""
    return sorted({m.group(0).lower() for m in _PHYSICAL.finditer(_clean(text))})


def surface_findings(where: str, text: str, cir, twin, *, require_note: bool,
                     require_claim: bool, scan_all: bool) -> list[str]:
    """Every way one surface breaks the rule. Empty means it states estimates truthfully.

    `scan_all` reads the whole surface for measurement language (the listing copy and alt
    text, which are short and entirely ours); otherwise only its size claims are read (a PDF,
    whose instructions legitimately tell the maker to measure their own swatch).
    """
    from .risk_matrix import DIMENSION_TOLERANCE

    findings: list[str] = []
    if require_note and not _has_note(text):
        findings.append(f"{where}: the estimate note is missing ({ESTIMATE_NOTE!r})")
    claims = size_claims(text)
    if require_claim and not claims:
        # A surface where nothing was found is a surface nothing was checked on. The twin has
        # a size, so the document states one; not finding it is a reading failure, not a pass.
        findings.append(f"{where}: no finished-size claim could be read, so none was checked")
    figures = twin_figures(cir, twin)
    for claim in claims:
        short = claim[:90]
        if not _ESTIMATE.search(claim) and not _INSTRUCTION.search(claim):
            findings.append(f"{where}: size claim without estimate language: {short!r}")
        words = physical_implications(claim)
        if words:
            findings.append(f"{where}: size claim implies a physical measurement {words}: "
                            f"{short!r}")
        findings += _accuracy(where, claim, figures, DIMENSION_TOLERANCE)
    findings += _gauge_accuracy(where, text, cir)
    if scan_all:
        claim_words = {w for c in claims for w in physical_implications(c)}
        rest = [w for w in physical_implications(text) if w not in claim_words]
        if rest:
            findings.append(f"{where}: implies a physical measurement {rest}")
    return findings


def child_safety_physical_needed(cir, result=None) -> str | None:
    """Why this product needs a child-safety physical test, or None when it does not.

    A stuffed toy, lovey, sewn-on piece or anything assigned to a child under 3 needs a
    use-and-abuse test of this exact content (`gates.child_safety`). That is never waived, and
    a product that needs it does not take the estimate path: its gauge area stays UNRESOLVED.
    Unreadable is treated as needed.
    """
    try:
        from ..products import launch0 as l0
        from . import child_safety

        verdict = child_safety.evaluate(cir, result,
                                        childrens=l0.childrens_assignment(cir.slug))
        if not verdict.applies:
            return None
        phys = next((c for c in verdict.checks if c.code == "PHYSICAL_EVIDENCE"), None)
        if phys is None or phys.state != child_safety.PASS:
            return (phys.detail if phys is not None
                    else "child-safety physical evidence could not be read")
        return None
    except Exception as exc:  # noqa: BLE001 - an unreadable safety reading is a held one
        return f"child-safety reading failed ({type(exc).__name__}); treated as required"


def evaluate(cir, twin, *, pdf_texts: dict[str, str] | None, listing_text: str | None,
             alt_texts: list[str] | None = None) -> dict:
    """The estimate-claims reading for one product with no physical sample.

    Returns {"applies": bool, "ok": bool, "findings": [...], "why": str}. `applies` False means
    the estimate path cannot decide (no documents, no listing, or child-safety physical
    evidence is required) and the caller keeps its UNRESOLVED state.
    """
    if not pdf_texts:
        return {"applies": False, "ok": False, "findings": [],
                "why": "no rendered document to read the estimate wording off"}
    if listing_text is None:
        return {"applies": False, "ok": False, "findings": [],
                "why": "no listing copy to read the estimate wording off"}
    sized = bool(twin_figures(cir, twin))
    findings: list[str] = []
    for terminology, text in sorted(pdf_texts.items()):
        findings += surface_findings(f"PDF {terminology}", text, cir, twin, require_note=True,
                                     require_claim=sized, scan_all=False)
    findings += surface_findings("listing copy", listing_text, cir, twin, require_note=True,
                                 require_claim=sized, scan_all=True)
    for n, alt in enumerate(alt_texts or [], 1):
        findings += surface_findings(f"alt text {n}", alt or "", cir, twin,
                                     require_note=False, require_claim=False, scan_all=True)
    return {"applies": True, "ok": not findings, "findings": findings,
            "why": ("every gauge and size claim is a labelled calculation from the certified "
                    "gauge, within tolerance of the twin, and none implies a measurement"
                    if not findings else "; ".join(findings[:4]))}
