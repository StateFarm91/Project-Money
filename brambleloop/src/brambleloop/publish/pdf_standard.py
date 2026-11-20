"""The premium pattern-PDF standard, by product family, audited on the finished bytes.

ENG-PDF-PREMIUM (2026-11-20). `research/benchmarks/PDF_STRUCTURE_STANDARD.md` records what a
bestselling premium pattern PDF contains, as STRUCTURE ONLY. This module turns that
structure into rules a document must pass before it ships. The rules are family-aware
(owner, 2026-11-19): a coaster needs a concise but complete PDF, and a garment needs the
full manual. Neither may miss what its family needs.

Two properties make the rules worth having:

- **They read the document a buyer downloads.** Every rule runs on the text extracted from
  the finished PDF bytes (and, for the running header and footer, on each page separately),
  never on the template that produced it. `publish.pdf.licence_paragraphs` records what
  happens when a check compares a decision with itself.
- **Every rule can fail.** `tests/test_pdf_standard.py` deletes each rule's evidence from a
  real document and requires that rule, by id, to fail. A rule that no mutation can trip is
  decoration.

The content still comes only from the certified CIR, the compiler and the twin. This module
does not write anything into a PDF; it decides whether the PDF is complete.
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from typing import Callable

# ---- families ------------------------------------------------------------------------------

SMALL_HOME = "small_home_goods"     # coasters, placemats, runners, dishcloths, ornaments
BLANKET = "blanket"
BASKET = "basket"
GARMENT = "garment"
PILLOW = "pillow"
AMIGURUMI = "amigurumi"
FAMILIES: tuple[str, ...] = (SMALL_HOME, BLANKET, BASKET, GARMENT, PILLOW, AMIGURUMI)

# The product-type families `gates.first_customer` reads from the CIR's own title and
# component names, mapped onto the PDF families. Read in this order: a "basket blanket"
# does not exist, but a garment with a pillow-named component would still be a garment.
_FROM_PRODUCT_TYPE: tuple[tuple[str, str], ...] = (
    ("garment", GARMENT), ("toy", AMIGURUMI), ("pillow", PILLOW), ("blanket", BLANKET),
    ("basket", BASKET), ("bag", BASKET),
)


def family_of(cir) -> str:
    """The PDF family of a CIR, from what the CIR itself names (never from a listing).

    A graded design is a garment whatever it is called, because a graded design is the one
    that needs the size chart and the size-parenthesis convention. Anything the closed
    product-type vocabulary does not place is a small home good: the concise standard, which
    is still complete.
    """
    if getattr(cir, "grading", None) is not None:
        return GARMENT
    from ..gates.first_customer import product_type_words_in_cir

    words = product_type_words_in_cir(cir)
    for word, fam in _FROM_PRODUCT_TYPE:
        if word in words:
            return fam
    return SMALL_HOME


# ---- the US hook table ---------------------------------------------------------------------

# Craft Yarn Council hook-size table (metric to US letter/number). A size that is not on the
# table gets no US name rather than a guessed one.
US_HOOKS: dict[float, str] = {
    2.25: "B-1", 2.75: "C-2", 3.25: "D-3", 3.5: "E-4", 3.75: "F-5", 4.0: "G-6", 4.5: "7",
    5.0: "H-8", 5.5: "I-9", 6.0: "J-10", 6.5: "K-10½", 8.0: "L-11", 9.0: "M/N-13",
    10.0: "N/P-15", 15.0: "P/Q", 16.0: "Q", 19.0: "S",
}


def us_hook(mm: float | None) -> str | None:
    if mm is None:
        return None
    return US_HOOKS.get(round(float(mm), 2))


def hook_words(mm: float | None) -> str:
    """'5 mm (US H-8)', or '5.25 mm' when the US table has no name for that size."""
    if mm is None:
        return "see Materials"
    us = us_hook(mm)
    return f"{mm:g} mm (US {us})" if us else f"{mm:g} mm"


HOOK_GAUGE_PHRASE = "or size to obtain gauge"


# ---- yarn weight, balls and substitution ---------------------------------------------------

def cyc_weight(cir):
    """The CIR's Craft Yarn Council weight class (`publish.substitution.Weight`), or None."""
    from . import substitution

    names = [cir.gauge.yarn_weight] if cir.gauge is not None and cir.gauge.yarn_weight else []
    names += [m.yarn_weight for m in cir.materials if m.yarn_weight]
    for n in names:
        key = substitution.normalise(n)
        if key in substitution.WEIGHT_BY_KEY:
            return substitution.WEIGHT_BY_KEY[key]
    return None


BALL_GRAMS = 100
YD_PER_M = 1.0936


def balls(metres_high: float, weight) -> int | None:
    """How many 100 g balls cover the top of a range, at the SHORTEST typical ball length.

    The shortest length of the CYC band, so the count is the one that does not run out.
    """
    if weight is None or metres_high <= 0:
        return None
    return max(1, math.ceil(metres_high / weight.metres_per_100g[0]))


def yarn_amount(lo_m: float, hi_m: float, terminology: str) -> str:
    """A yarn range in the edition's unit: yards first in the US edition, metres in the UK."""
    if terminology.upper() == "UK":
        return f"about {lo_m:.0f}-{hi_m:.0f} m"
    return (f"about {lo_m * YD_PER_M:.0f}-{hi_m * YD_PER_M:.0f} yd "
            f"({lo_m:.0f}-{hi_m:.0f} m)")


def length_per_gram(weight, terminology: str) -> str:
    """The weight class's typical length per gram, in the edition's unit."""
    lo, hi = (x / BALL_GRAMS for x in weight.metres_per_100g)
    if terminology.upper() == "UK":
        return f"{lo:.1f}-{hi:.1f} m per gram"
    return f"{lo * YD_PER_M:.1f}-{hi * YD_PER_M:.1f} yd per gram"


# ---- the brand page ------------------------------------------------------------------------

ABOUT_HEADING = "About Brambleloop Studio"
DISCLAIMER_HEADING = "Disclaimer"
LICENCE_HEADING = "What you may do with this pattern"

# What the PDF says about the brand. About the STUDIO: no person, no invented designer, no
# signature (PDF_STRUCTURE_STANDARD, honest-only rules). `store_foundation.copy_v2` holds the
# shop's About page; its Laura paragraph is deliberately not here.
ABOUT_PARAGRAPHS: tuple[str, ...] = (
    "Brambleloop Studio is a crochet pattern brand. It publishes patterns for pieces you want "
    "around you: soft blankets, baskets that bring a little order to a shelf, small things "
    "for the table. Quiet colours, natural textures and practical projects you will use.",
    "Every Brambleloop pattern begins as a formal pattern file, and every row's stitch count "
    "is checked by the studio's pattern compiler before the pattern is released. The written "
    "instructions, the charts and the diagrams are all drawn from that one file, so they "
    "agree with each other. Every pattern comes as two complete PDFs, one in US terms and "
    "one in UK terms.",
    "Brambleloop Studio is a brand, not a person. The designs are created with AI "
    "assistance, and no individual designer is named in this pattern.",
)

DISCLAIMER = (
    "This pattern is provided as written, for making by hand. Brambleloop Studio has checked "
    "its stitch counts, but cannot control the yarn, hook, tension or care a finished item "
    "receives, and is not responsible for the result, for any loss or damage arising from "
    "its use, or for how a finished item is used. Follow the yarn's care label."
)
# No child-safety sentence here: the disclaimer prints on every document, and a kitchen
# basket must not mention babies (test_deliverable_qa). Child items carry the full safety
# section instead (rule `safety`).


# ---- the audit -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Context:
    cir: object
    twin: object
    result: object
    terminology: str
    family: str
    childrens: bool
    colourwork: bool
    multi_size: bool


@dataclass(frozen=True)
class Rule:
    id: str
    what: str
    families: tuple[str, ...]           # () = every family
    check: Callable[[str, Context], list[str]]
    applies: Callable[[Context], bool] = lambda ctx: True

    def required_for(self, ctx: Context) -> bool:
        return (not self.families or ctx.family in self.families) and self.applies(ctx)


@dataclass
class Audit:
    slug: str
    version: str
    terminology: str
    family: str
    required: list[str] = field(default_factory=list)
    failures: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {"slug": self.slug, "version": self.version, "terminology": self.terminology,
                "family": self.family, "required": list(self.required),
                "failures": {k: list(v) for k, v in self.failures.items()}, "ok": self.ok}


class PremiumStandardRefused(ValueError):
    """The finished PDF is missing what its family requires."""


# The owner's master template (D-OWNER-PDF-TEMPLATE, publish.pdf_template) prints the same
# parts of the document under its own headings. Each rule still requires the same content;
# only the heading that introduces it may be the template's. Exact strings, never fuzzy.
TEMPLATE_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "AT A GLANCE": ("PROJECT DETAILS",),
    "Materials": ("Gather your materials",),
    "How much yarn": ("YARN QUANTITIES",),
    "BEFORE YOU START": ("MAKER NOTE",),
    "Hook and notions": ("CROCHET HOOKS",),
    "TAPESTRY NEEDLE": ("Tapestry needle",),
    "Gauge, and why it matters here": ("GAUGE FIRST",),
    "How it is made": ("Construction guide",),
    "FINISHED MEASUREMENTS": ("SIZE & MATERIAL GUIDE",),
    "Sizes and fit": ("Sizing & finished fit",),
    "Abbreviations": ("Stitches & abbreviations",),
    "US CROCHET TERMS": ("COMMON TERMS / US TERMINOLOGY",),
    "UK CROCHET TERMS": ("COMMON TERMS / UK TERMINOLOGY",),
    "How to read a row": ("HOW TO READ A ROW",),
    "Special stitches": ("SPECIAL STITCHES",),
    "Instructions (US terms)": ("• US TERMINOLOGY",),
    "Instructions (UK terms)": ("• UK TERMINOLOGY",),
    "CHART AND KEYS": ("CHART KEY",),
    "ASSEMBLY AND FINISHING": ("Finishing & assembly",),
    "Substituting the yarn": ("YARN SUBSTITUTION",),
    "Tips and troubleshooting": ("HELPFUL NOTES",),
    "construction diagram": ("Diagram drawn from this pattern's stitch data",
                             "Drawn from the stitch data"),
    "BRAMBLELOOP ·": ("BRAMBLELOOP CROCHET PATTERNS",),
    "About Brambleloop Studio": ("A little about Brambleloop",),
    "Safety notes for a children's item": ("SAFETY / AGE / USE NOTES",),
}


def _find(text: str, needle: str, start: int = 0) -> int:
    hits = [k for k in (text.find(n, start) for n in (needle,) +
                        TEMPLATE_EQUIVALENTS.get(needle, ())) if k >= 0]
    return min(hits) if hits else -1


def _has(text: str, *needles: str) -> list[str]:
    return [f"missing {n!r}" for n in needles if _find(text, n) < 0]


def _section(text: str, start: str, ends: tuple[str, ...]) -> str:
    i = _find(text, start)
    if i < 0:
        return ""
    j = min([k for k in (_find(text, e, i + 1) for e in ends) if k > 0],
            default=len(text))
    return text[i:j]


# -- the rules' checks --

def _cover(text, ctx):
    head = text[:1500]
    out = _has(head, ctx.cir.title, "SKILL", "Crochet pattern")
    low = head.lower()
    if not any(w in low for w in ("digital rendering", "photograph of", "a rendering, not a "
                                                                      "photograph")):
        out.append("the cover hero is labelled neither as a rendering nor as a photograph")
    if "Brambleloop" not in text[:2500]:
        out.append("the cover does not carry the brand")
    return out


def _overview(text, ctx):
    out = _has(text, "AT A GLANCE", "DIFFICULTY", "FINISHED SIZE", "CONSTRUCTION", "SIZES")
    w = cyc_weight(ctx.cir)
    if w is None:
        out.append("the CIR names no CYC yarn weight")
    elif f"CYC {w.number}" not in text:
        out.append(f"the yarn weight is not given its CYC number ({w.number})")
    g = ctx.cir.gauge
    if g is not None and g.hook_mm:
        us = us_hook(g.hook_mm)
        if f"{g.hook_mm:g} mm" not in text:
            out.append("the hook is not given in mm")
        if us and f"US {us}" not in text:
            out.append(f"the hook is not given its US size ({us})")
    return out


def _supply_yarn(text, ctx):
    out = _has(text, "Materials", "How much yarn", "100 g ball")
    unit = " m" if ctx.terminology.upper() == "UK" else " yd"
    sec = _section(text, "How much yarn", ("Substituting the yarn", "BEFORE YOU START"))
    for colour in sorted(ctx.twin.yarn_metres_by_color):
        if colour.upper() not in sec and colour not in sec:
            out.append(f"no yarn amount for colour {colour!r}")
    if unit not in sec:
        out.append(f"the yarn amounts are not in{unit}")
    if ctx.terminology.upper() == "UK" and " yd" in sec:
        out.append("the UK edition gives the yarn amounts in yards")
    return out


def _supply_hook_notions(text, ctx):
    return _has(text, "Hook and notions", HOOK_GAUGE_PHRASE, "TAPESTRY NEEDLE")


def _gauges_of(cir) -> list:
    seen, out = set(), []
    for g in [cir.gauge] + [c.gauge for c in cir.components]:
        if g is None:
            continue
        key = (g.stitches_per_10cm, g.rows_per_10cm, g.stitch_type, g.hook_mm)
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out


def _gauge(text, ctx):
    out = _has(text, "Gauge, and why it matters here", "larger hook", "smaller hook")
    for g in _gauges_of(ctx.cir):
        pat = (rf"{g.stitches_per_10cm:g}(?:\.0)? sts x {g.rows_per_10cm:g}(?:\.0)? rows "
               rf"= 10 ?cm")
        tpl = (rf"{g.stitches_per_10cm:g}(?:\.0)? sts and {g.rows_per_10cm:g}(?:\.0)? rows "
               rf"over 10 x 10 cm")
        if not re.search(pat, text) and not re.search(tpl, text):
            out.append(f"no gauge statement for the {g.stitch_type} fabric "
                       f"({g.stitches_per_10cm:g} sts x {g.rows_per_10cm:g} rows)")
    return out


def _construction(text, ctx):
    return _has(text, "How it is made")


def _schematic(text, ctx):
    return _has(text, "SCHEMATIC", "FINISHED MEASUREMENTS")


def _size_chart(text, ctx):
    out = _has(text, "Sizes and fit", "to fit chest", "finished chest", "ease", "yarn about")
    if ctx.cir.grading is not None:
        for s in ctx.cir.grading.sizes:
            name = str(s.get("size", s.get("name", "")))
            if name and f"SIZE {name.upper()}" not in text:
                out.append(f"the size chart has no row for size {name!r}")
    return out


_US_ONLY = ("sc", "hdc", "sk")


def _abbreviations(text, ctx):
    from . import abbreviations
    term = ctx.terminology.upper()
    out = _has(text, "Abbreviations", f"{term} CROCHET TERMS")
    key = _section(text, f"{term} CROCHET TERMS", ("How to read a row", "STEP BY STEP"))
    for code in sorted(ctx.twin.stitch_types_used):
        words = abbreviations.spellings(code, term)
        if not any(re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", key) for w in words):
            out.append(f"the {term} key does not define {words[0]!r} ({code})")
    if term == "UK":
        body = _instructions(text, ctx)
        for us in _US_ONLY:
            if re.search(rf"(?<![\w-]){re.escape(us)}(?![\w-])", body):
                out.append(f"the UK instructions use the US-only term {us!r}")
    return out


def _specials(ctx) -> list[str]:
    from . import abbreviations
    return [c for c in sorted(ctx.twin.stitch_types_used)
            if abbreviations.method(c, ctx.terminology)]


def _special_stitches(text, ctx):
    out = _has(text, "Special stitches")
    from . import abbreviations
    for c in _specials(ctx):
        if abbreviations.method(c, ctx.terminology)[:40] not in text:
            out.append(f"no written definition for the special stitch {c!r}")
    return out


# ENG-PLUSH x pdf-premium: "Stuff after Rnd 16:" / "Close after Rnd 18:" are steps between
# rounds, not round labels; reading them as labels reported a round with "no stitch count".
_LABEL = re.compile(r"(?<![Aa]fter )\b(Rows?|Rnds?)\s+(\d+)(?:\s*[-–]\s*\d+)?((?:\s*\([^()]*\))*)\s*:")
_COUNT = re.compile(r"\((\d+) sts?\)")
_INSTR_ENDS = ("IF SOMETHING LOOKS WRONG", "CHART AND KEYS", "ASSEMBLY AND FINISHING",
               "FINAL STEPS")


def _instructions(text, ctx) -> str:
    return _section(text, f"Instructions ({ctx.terminology.upper()} terms)", _INSTR_ENDS)


def row_counts(text: str, terminology: str) -> list[tuple[str, int, int | None]]:
    """Every row/round label in the instructions with the count printed after it (or None)."""
    body = _section(text, f"Instructions ({terminology.upper()} terms)", _INSTR_ENDS)
    labels = list(_LABEL.finditer(body))
    out = []
    for i, m in enumerate(labels):
        end = labels[i + 1].start() if i + 1 < len(labels) else len(body)
        seg = body[m.end():end]
        cm = _COUNT.search(seg)
        out.append((m.group(1), int(m.group(2)), int(cm.group(1)) if cm else None))
    return out


def _counts(text, ctx):
    out = []
    rows = row_counts(text, ctx.terminology)
    if not rows:
        return ["no row or round in the instructions could be read"]
    valid: dict[int, set[int]] = {}
    for r in ctx.result.rows:
        valid.setdefault(r.index, set()).add(r.stitch_count)
    for kind, idx, count in rows:
        if count is None:
            out.append(f"{kind} {idx} has no stitch count")
        elif count not in valid.get(idx, ()):
            out.append(f"{kind} {idx} prints ({count} sts), which the compiler does not "
                       f"certify for that row ({sorted(valid.get(idx, ()))})")
    return out


def _rs_ws(text, ctx):
    flat = any(c.construction == "flat_rows" for c in ctx.cir.components)
    if not flat:
        return []
    body = _instructions(text, ctx)
    if not re.search(r"\bRow 1 \((?:[^()]*, )?RS\)", body) and "(RS)" not in body:
        return ["the flat rows carry no RS/WS label"]
    rows = [m for m in _LABEL.finditer(body) if m.group(1).startswith("Row")]
    bad = [m.group(0) for m in rows if "RS" not in m.group(3) and "WS" not in m.group(3)]
    return [f"{len(bad)} rows have no RS/WS label, e.g. {bad[0]!r}"] if bad else []


def _diagrams(text, ctx):
    return [] if _find(text, "construction diagram") >= 0 else ["no inline construction diagram"]


def _chart(text, ctx):
    out = _has(text, "CHART AND KEYS")
    if "Colour key" not in text and not re.search(r"\bColours\b[^#]{0,400}#[0-9A-Fa-f]{6}", text):
        out.append("no colour key")
    return out


def _finishing(text, ctx):
    return _has(text, "Finishing", "weave in")


def _seams(text, ctx):
    if not ctx.cir.assembly:
        return []
    return _has(text, "ASSEMBLY AND FINISHING")


def _substitution(text, ctx):
    out = _has(text, "Substituting the yarn")
    w = cyc_weight(ctx.cir)
    if w is not None:
        per = length_per_gram(w, ctx.terminology)
        if per not in text:
            out.append(f"the substitution guide gives no length per gram ({per})")
    return out


def _tips(text, ctx):
    return _has(text, "Tips and troubleshooting")


def _licence(text, ctx):
    from ..commerce import terms
    out = _has(text, LICENCE_HEADING, "own use", "credit to Brambleloop Studio",
               "may not be shared, resold", DISCLAIMER_HEADING, DISCLAIMER[:60])
    if terms.BRAMBLELOOP_TERMS.sentence(terms.FINISHED_ITEM_SALE) not in text:
        out.append("the finished-item licence is not the canonical commerce.terms sentence")
    return out


def _about(text, ctx):
    out = _has(text, ABOUT_HEADING, ABOUT_PARAGRAPHS[2][:50])
    if re.search(r"\bLaura\b", text):
        out.append("the document names Laura; Laura is never presented as a designer or person")
    return out


def _rendering(text, ctx):
    out = []
    if "not a photograph" not in text and "Photograph" not in text:
        out.append("no rendering/photograph label on the pictures")
    from .pdf import IMAGE_DISCLOSURE
    if IMAGE_DISCLOSURE.split(".")[0] not in text and "digital rendering" not in text:
        out.append("no rendering disclosure")
    return out


def _safety(text, ctx):
    from .pdf import CHILDRENS_HEADING
    return _has(text, CHILDRENS_HEADING)


RULES: tuple[Rule, ...] = (
    Rule("cover", "Cover: product name, brand, labelled hero, skill level", (), _cover),
    Rule("overview_table", "Overview table: skill, sizes, finished size, CYC yarn weight, "
         "hook in US and mm, construction", (), _overview),
    Rule("supply_yarn", "Yarn per colour in balls and the edition's unit", (), _supply_yarn),
    Rule("supply_hook_notions", "Hook 'or size to obtain gauge', and notions", (),
         _supply_hook_notions),
    Rule("gauge_every_fabric", "Gauge for every fabric, with troubleshooting", (), _gauge),
    Rule("construction_narrative", "Construction narrative", (), _construction),
    Rule("schematic", "Schematic with finished measurements", (), _schematic,
         lambda ctx: bool(getattr(ctx.twin, "width_cm", None))),
    Rule("size_chart", "Size chart: body vs finished, ease, yarn per size", (GARMENT,),
         _size_chart),
    Rule("abbreviations", "Abbreviations correct for the edition", (), _abbreviations),
    Rule("special_stitches", "Special-stitch definitions", (), _special_stitches,
         lambda ctx: _specials(ctx)),
    Rule("row_counts", "A certified stitch count after every row or round", (), _counts),
    Rule("rs_ws", "RS/WS labels on flat rows", (), _rs_ws),
    Rule("inline_diagrams", "Inline construction diagrams at the tricky steps",
         (BASKET, AMIGURUMI, PILLOW), _diagrams),
    Rule("colourwork_chart", "Chart and colour key for colourwork", (), _chart,
         lambda ctx: ctx.colourwork),
    Rule("finishing", "Finishing", (), _finishing),
    Rule("assembly", "Assembly with seams", (), _seams, lambda ctx: bool(ctx.cir.assembly)),
    Rule("substitution", "Yarn substitution by CYC class and length per gram", (),
         _substitution, lambda ctx: cyc_weight(ctx.cir) is not None),
    Rule("tips", "Tips", (), _tips),
    Rule("licence", "Our own licence and a disclaimer", (), _licence),
    Rule("about_brand", "About Brambleloop Studio, never Laura", (), _about),
    Rule("rendering_disclosure", "Generated images labelled as renderings", (), _rendering),
    Rule("safety", "Safety section for baby and child items", (), _safety,
         lambda ctx: ctx.childrens or ctx.family == AMIGURUMI),
)

RULE_IDS: tuple[str, ...] = tuple(r.id for r in RULES) + ("running_header_footer",)


def colourwork(twin) -> bool:
    """More than one colour in the fabric."""
    return len(getattr(twin, "yarn_metres_by_color", {}) or {}) > 1


def context(cir, twin, result, terminology: str, *, childrens: bool | None = None) -> Context:
    from .pdf import childrens_assignment

    fam = family_of(cir)
    kids = (childrens_assignment(cir) is not None) if childrens is None else childrens
    return Context(cir=cir, twin=twin, result=result, terminology=terminology.upper(),
                   family=fam, childrens=kids, colourwork=colourwork(twin),
                   multi_size=cir.grading is not None and len(cir.grading.sizes) > 1)


def pages_text(pdf_bytes: bytes) -> list[str]:
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return [" ".join((p.extract_text() or "").split()) for p in reader.pages]


def header_footer_failures(pages: list[str], cir) -> list[str]:
    out = []
    n = len(pages)
    for i, t in enumerate(pages, start=1):
        if f"page {i} of {n}" not in t:
            out.append(f"page {i} has no 'page {i} of {n}' folio")
        if f"{cir.slug}@{cir.version}" not in t:
            out.append(f"page {i} has no release footer")
        if i > 1 and _find(t, "BRAMBLELOOP ·") < 0:
            out.append(f"page {i} has no running header")
    return out


def audit_text(text: str, ctx: Context, pages: list[str] | None = None) -> Audit:
    a = Audit(slug=ctx.cir.slug, version=ctx.cir.version, terminology=ctx.terminology,
              family=ctx.family)
    for rule in RULES:
        if not rule.required_for(ctx):
            continue
        a.required.append(rule.id)
        found = rule.check(text, ctx)
        if found:
            a.failures[rule.id] = found
    if pages is not None:
        a.required.append("running_header_footer")
        hf = header_footer_failures(pages, ctx.cir)
        if hf:
            a.failures["running_header_footer"] = hf
    return a


def audit(pdf_bytes: bytes, cir, *, terminology: str, twin=None, result=None,
          childrens: bool | None = None) -> Audit:
    """Audit one finished PDF against its family's standard."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from .pdf import extracted_text

    result = result or compile_cir(cir)
    twin = twin or build_twin(cir, result)
    ctx = context(cir, twin, result, terminology, childrens=childrens)
    return audit_text(extracted_text(pdf_bytes), ctx, pages_text(pdf_bytes))


def refuse_if_incomplete(a: Audit) -> None:
    if not a.ok:
        raise PremiumStandardRefused(
            f"refusing to ship {a.slug}@{a.version} ({a.terminology}, {a.family}): the PDF "
            f"is missing what its family requires: "
            + "; ".join(f"{k}: {v[0]}" + (f" (+{len(v) - 1})" if len(v) > 1 else "")
                        for k, v in sorted(a.failures.items())))
