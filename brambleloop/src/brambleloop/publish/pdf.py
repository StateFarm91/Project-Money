"""The premium pattern PDF -- the thing the customer actually receives.

Everything on these pages is derived from the compiled CIR and its digital twin: the row
instructions come from the writer, the chart from the twin's cell grid, the finished size
from the gauge, the yardage from the stitch census. Nothing is typed in by hand and nothing
is described by a model, because the failure mode we are designing against is a PDF whose
front page promises 120 x 150 cm and whose rows produce something else.

Where a number is an estimate it says so on the page. Yarn quantities genuinely vary with
yarn, hook and tension, and printing an uncalibrated figure as though it were measured is
exactly the unsupported claim the Policy Gate exists to block -- including when we are the
ones making it.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

from ..brand import bible
from ..cir.compiler import compile_cir
from ..cir.model import CIR
from ..cir.twin import TwinModel, build_twin
from ..cir.writer import write_pattern
from ..intel import childrens as ch
from . import abbreviations, substitution, value_stack
from . import charts as chart_mod
from .charts import (
    COLOUR_CUE_NOTE_FLAT, COLOUR_CUE_NOTE_ROUND, ChartSpec, RoundBlock, cell_size,
    color_letters, crop_grids, detect_repeat, is_round, render_chart, render_legend,
    render_round_chart, round_block, round_chart_size, row_block, wedge_count,
)
from .difficulty import difficulty as _difficulty

PAGE_W, PAGE_H = LETTER
MARGIN = 18 * mm

# Read from the brand system rather than restated here. `brand/bible.py` says "anything that
# renders an asset reads from here", and this module held its own copy of the same six hex
# codes -- so the brand was locked everywhere except in the one artefact the customer keeps.
INK = colors.HexColor(bible.PALETTE["ink"])
PINE = colors.HexColor(bible.PALETTE["pine"])
CREAM = colors.HexColor(bible.PALETTE["cream"])
GOLD = colors.HexColor(bible.PALETTE["gold"])
LINE = colors.HexColor(bible.PALETTE["line"])

# The smallest type this document may set, taken from the brand's own declared minimum. The
# footer was at 8pt against a brand rule that says 9, which is the kind of drift a constant
# in two places produces.
MIN_BODY_PT = bible.TYPOGRAPHY["min_body_pt"]

# WCAG 2.1 AA for text below 18pt, and the arithmetic behind it, both read from the brand
# system. They were defined here, and the chart renderer -- whose images sit inside this same
# document -- had neither, so half the type in the file was checked and half was not.
MIN_CONTRAST = bible.MIN_TEXT_CONTRAST


def contrast(fg, bg) -> float:
    """Contrast ratio between two reportlab colours, 1.0 (invisible) to 21.0 (black on white)."""
    return bible.contrast_ratio((fg.red, fg.green, fg.blue), (bg.red, bg.green, bg.blue))


def _legible(fg, bg, *, minimum: float = MIN_CONTRAST):
    """The brand colour, darkened only as far as it has to be to be readable on this paper.

    The brand's `muted` grey measures 4.48:1 on the brand's cream -- a fraction under the AA
    floor, and it is the colour of the yarn-tolerance note, the substitution caveats, the
    chart instructions and the page numbers, which is most of the explanatory prose in the
    document. Rather than move a palette that the storefront and the chart renderer also
    read, the document darkens its own ink until it passes and leaves the brand alone.

    The maths lives in `brand.bible` so that the chart renderer applies the same rule to the
    same palette; this is the reportlab wrapper around it.
    """
    r, g, b = bible.legible((fg.red, fg.green, fg.blue), (bg.red, bg.green, bg.blue),
                            minimum=minimum)
    return colors.Color(r, g, b)


MUTED = _legible(colors.HexColor(bible.PALETTE["muted"]), CREAM)
# The cover's subtitle sits on the pine band, where the brand gold measures 3.65:1.
GOLD_ON_PINE = _legible(GOLD, PINE)


@dataclass
class PatternDocument:
    """The rendered PDF plus the facts it asserts, so a gate can check the two agree."""

    pdf_bytes: bytes
    pages: int
    finished_size_cm: tuple[float, float] | None
    yardage_by_color: dict[str, float]
    yardage_tolerance: float
    calibrated: bool
    terminology: str
    claims: list[str] = field(default_factory=list)
    difficulty: str = ""
    released_on: date | None = None
    # What is wrong with this document, measured on the document rather than on the plan
    # that produced it. Empty is the normal answer; a non-empty list is handed to the
    # release chain, which is where a finding can actually stop something.
    problems: list[str] = field(default_factory=list)
    # Every word the document sets, in order. Carried out of the render so a check can be run
    # against what the buyer reads rather than against the writer's instruction text, which
    # is one section of eight and the only one anything was ever measuring.
    prose: str = ""

    def size_label(self) -> str:
        if not self.finished_size_cm:
            return "size not stated"
        w, h = self.finished_size_cm
        return f"{w:.0f} x {h:.0f} cm"


class _Doc:
    """One customer PDF, rendered reproducibly.

    `invariant` is load-bearing rather than tidiness. Without it reportlab stamps the current
    time and a random document id into every render, so the same certified CIR produced a
    different file every time -- which was quietly visible in production, where two renders
    of one release minutes apart were audited under two different hashes.

    That matters because of what the hash is for. Artifact bytes are not durable until object
    storage exists, so a purchased file is re-rendered on demand; if each render differs, the
    stored hash proves only that *a* render happened, not that the file a customer downloads
    is the one that passed the gates. With the render fixed, the hash means what
    `assets.build` says it means.
    """

    def __init__(self, title: str, *, total_pages: int = 0, author: str = "",
                 subject: str = ""):
        self.buf = io.BytesIO()
        self.c = rl_canvas.Canvas(self.buf, pagesize=LETTER, invariant=1)
        self.c.setTitle(title)
        # Set because a PDF with no author and no subject is an untitled file in a downloads
        # folder six months later, and because assistive software reads them first.
        if author:
            self.c.setAuthor(author)
        if subject:
            self.c.setSubject(subject)
        # The document's natural language, in the catalogue where assistive software looks
        # for it. reportlab has no setter for this, so it is written to the catalogue
        # directly; without it a screen reader guesses the language from the system locale
        # and reads an English pattern in whatever voice that produces.
        self.c.setCatalogEntry("Lang", "en-GB")
        # Known only on the second pass. A footer that says "page 5" cannot tell a customer
        # whether their download stopped early; "page 5 of 7" can, which is the cheapest
        # download-integrity check a buyer can run without any software at all.
        self.total_pages = total_pages
        self.pages = 0
        self.y = PAGE_H - MARGIN
        # Every word this document sets, in the order it sets it.
        #
        # Kept because the checks that read the document were reading the *instruction text*
        # -- the writer's output, one section of eight -- and calling the answer a property of
        # the document. The cover, the gauge block, the materials, the key and the finishing
        # prose are all set here and none of them was measured. A UK render stated its gauge
        # "in sc" on page 1, in a document whose key defines `dc`, and every check passed.
        #
        # Accumulated rather than extracted from the finished PDF so the checks run on what
        # the module chose to say rather than on what a text extractor could recover from the
        # glyphs; the extraction is a separate proof, and the tests do it too.
        self.prose: list[str] = []

    # -- primitives --------------------------------------------------------
    def new_page(self, running_head: str | None = None) -> None:
        if self.pages:
            self._footer()
            self.c.showPage()
        self.pages += 1
        self.c.setFillColor(CREAM)
        self.c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        self.y = PAGE_H - MARGIN
        if running_head:
            self.c.setFillColor(MUTED)
            self.c.setFont("Helvetica", MIN_BODY_PT)
            self.c.drawString(MARGIN, PAGE_H - MARGIN + 6 * mm, running_head.upper())

    def _footer(self) -> None:
        self.c.setFillColor(MUTED)
        self.c.setFont("Helvetica", MIN_BODY_PT)
        self.c.drawRightString(PAGE_W - MARGIN, MARGIN - 8 * mm,
                               f"page {self.pages} of {self.total_pages or self.pages}")

    def space(self, amount: float) -> None:
        self.y -= amount

    def need(self, amount: float, running_head: str | None = None) -> None:
        if self.y - amount < MARGIN:
            self.new_page(running_head)

    def heading(self, text: str, size: int = 15) -> None:
        self.prose.append(text)
        self.need(size + 10 * mm)
        self.c.setFillColor(PINE)
        self.c.setFont("Helvetica-Bold", size)
        self.c.drawString(MARGIN, self.y, text)
        self.y -= size + 3
        self.c.setStrokeColor(GOLD)
        self.c.setLineWidth(1)
        self.c.line(MARGIN, self.y, MARGIN + 28 * mm, self.y)
        self.y -= 7 * mm

    def para(self, text: str, size: int = 10, color=INK, leading: float = 4.6 * mm,
             running_head: str | None = None) -> None:
        self.prose.append(text)
        self.c.setFont("Helvetica", size)
        self.c.setFillColor(color)
        usable = PAGE_W - 2 * MARGIN
        for line in _wrap(self.c, text, "Helvetica", size, usable):
            self.need(leading, running_head)
            self.c.setFont("Helvetica", size)
            self.c.setFillColor(color)
            self.c.drawString(MARGIN, self.y, line)
            self.y -= leading

    def kv(self, key: str, value: str, *, upper: bool = True) -> None:
        """A label and its value. `upper` is off for anything the maker has to type-match.

        An abbreviation is a lowercase token in every crochet pattern ever printed, and a
        key that shouts "CH" at a beginner who is looking for "ch" in the instructions has
        made them do a translation the document was supposed to do for them.
        """
        self.prose.append(f"{key} {value}")
        self.need(5 * mm)
        self.c.setFont("Helvetica-Bold", 9)
        self.c.setFillColor(MUTED)
        self.c.drawString(MARGIN, self.y, key.upper() if upper else key)
        self.c.setFont("Helvetica", 10)
        self.c.setFillColor(INK)
        self.c.drawString(MARGIN + 42 * mm, self.y, value)
        self.y -= 5.2 * mm

    def image(self, img, running_head: str | None = None) -> None:
        from reportlab.lib.utils import ImageReader

        usable_w = PAGE_W - 2 * MARGIN
        scale = min(1.0, usable_w / img.width)
        w, h = img.width * scale, img.height * scale
        if h > PAGE_H - 2 * MARGIN:
            scale *= (PAGE_H - 2 * MARGIN) / h
            w, h = img.width * scale, img.height * scale
        self.need(h + 4 * mm, running_head)
        self.c.drawImage(ImageReader(img), MARGIN, self.y - h, width=w, height=h,
                         preserveAspectRatio=True, mask="auto")
        self.y -= h + 5 * mm

    def finish(self) -> bytes:
        self._footer()
        self.c.save()
        return self.buf.getvalue()


def _wrap(c, text: str, font: str, size: int, width: float) -> list[str]:
    out: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            out.append("")
            continue
        line = ""
        for word in paragraph.split(" "):
            trial = f"{line} {word}".strip()
            if c.stringWidth(trial, font, size) <= width:
                line = trial
            else:
                if line:
                    out.append(line)
                line = word
        out.append(line)
    return out


# The terminologies the customer receives, and the filename each one is delivered under.
#
# Held here, in the module that renders the document, because the release chain and the store
# publisher each need both and neither should be the place that knows. They previously each
# held the literal `pattern-us.pdf`, which is how one of them would have gained a UK file and
# the other would not.
#
# US is first and stays first: it is the terminology the CIR is canonical in, the one every
# gauge and every measurement was validated against, and the file a listing's preview should
# open on.
TERMINOLOGIES: tuple[str, ...] = ("US", "UK")


def pattern_filename(terminology: str) -> str:
    """What the customer's file is called, for the terminology it is written in.

    Named so the buyer can tell the two apart in a downloads folder without opening them,
    which is the only place they will ever see these filenames.
    """
    if terminology.upper() not in TERMINOLOGIES:
        raise ValueError(
            f"{terminology!r} is not a terminology this company publishes: {TERMINOLOGIES}")
    return f"pattern-{terminology.lower()}.pdf"


def _gauge_stitch(cir: CIR, terminology: str) -> str:
    """The gauge swatch's stitch, named in the terminology this document is written in.

    `cir.gauge.stitch_type` is a canonical code, which is to say a US abbreviation, and it was
    printed raw in three places: the cover's "at a glance" gauge, the swatch/fabric
    reconciliation and the sentence that explains it. `cir.writer` localises the same gauge
    line correctly on the instructions page, so a UK document said `16 sts x 18 rows = 10 cm
    in sc` on page 1 and `10cm in dc` on page 4 -- one gauge, two stitches, in one file.

    The harm is not only the contradiction. `sc` is not a UK abbreviation at all, so it is a
    word the UK document's own key does not define; and if a UK maker resolves it against
    their own vocabulary, the stitch they swatch is a treble -- three times the height of the
    one the gauge was measured on, and every finished measurement wrong with it.

    Routed through `abbreviations.token`, which delegates to `cir.stitches.UK_TERMS`, so the
    cover and the instructions page cannot say different words about the same stitch.
    """
    return abbreviations.token(cir.gauge.stitch_type, terminology)


def licence_paragraphs() -> list[str]:
    """The buyer's licence, from the one place it is decided.

    **There is no licence text in this module any more.** There was, and it was the fourth
    copy. `commerce.terms` decided that finished items may be sold "by individual makers and
    small businesses, not manufactured at scale" and that the pattern is for the buyer's own
    use "and to teach from in a class where each participant has their own copy";
    `brand.storefront` said "sell the items you make from it" with no limit; `commerce.seo`
    said "Sell what you make"; and this module -- the only surface the customer actually
    keeps -- said "This pattern is for your personal use. You may sell finished items you make
    from it", which is simultaneously more permissive than the decision on selling and less
    permissive than it on teaching.

    Requirement 40's check exists for exactly this and could not see it.
    `terms.consistency(pdf_text, ...)` is called with `terms.render(terms, "pdf")` -- the
    decision rendered for the PDF surface, not the PDF. So the check compared the decision
    with itself on the one surface that had diverged, and reported the three surfaces
    consistent while the customer's own document granted an unlimited commercial licence. A
    check that cannot see the artefact it exists to measure.

    Now the document renders the decision. `tests/test_deliverable_qa.py` runs the
    consistency check on text extracted from the real PDF, which is the comparison that can
    fail.
    """
    from ..commerce import terms as customer_terms

    return customer_terms.render(customer_terms.BRAMBLELOOP_TERMS, "pdf").split("\n")


AI_DISCLOSURE = (
    "How this pattern was made: the design was developed with AI assistance and every stitch "
    "count in it was verified by an automated pattern compiler before release, row by row. "
    "The charts in this document are generated directly from the same verified data as the "
    "written instructions, so the two cannot disagree."
)


COPYRIGHT_HOLDER = "Brambleloop Studio"


# ---- the children's safety block -------------------------------------------
#
# Two of the three Launch-0 products are for children under three, `intel.childrens`
# computes what each of them must say, and until now nothing printed it. This is the part of
# the document that closes that -- and the part that refuses to produce a document when it
# cannot.
#
# The heading the block is set under. Plain rather than alarming on purpose: this is a
# premium pattern and a red warning box would be both out of voice and, for a blanket with
# no applied parts, out of proportion to the hazard. The words do the work.
CHILDRENS_HEADING = "Safety notes for a children's item"

CHILDRENS_INTRO = (
    "This pattern is written for a child, which changes what the pattern has to tell you. "
    "Each note below says where it comes from, so you can check it rather than take our "
    "word for it."
)


def childrens_assignment(cir: CIR) -> tuple[str, str] | None:
    """Which children's sub-category and age band this pattern is merchandised into.

    Measures: `products.launch0`'s own assignment of a CIR slug to a children's
    sub-category, which is where a merchandising fact about a product belongs.
    Why: the audience is not a property of the stitches. `cir.model.CIR` records nothing
    about who the finished object is for, and it should not -- the same fabric is a lap
    blanket or a baby blanket depending on how it is sold, and that is a decision somebody
    makes rather than a consequence of the arithmetic. So the renderer asks the catalogue.
    A CIR with no assignment gets no safety block, which is the other half of the
    requirement: a table runner must not acquire a safe-sleep note it has no reason to carry.

    Imported inside the function rather than at module scope because `products/**` is a
    catalogue and `publish/**` is a renderer; the renderer should not be unimportable
    without the catalogue.
    """
    from ..products import launch0

    return launch0.childrens_assignment(cir.slug)


def _refuse_an_undecided_childrens_title(cir: CIR, childrens) -> None:
    """A pattern whose own title says "child" cannot be rendered on nobody's decision.

    `childrens_assignment` answers None both for a product a candidate has deliberately
    placed outside the children's category and for a product no candidate mentions at all --
    one value for a decision and for an omission. On the second reading a document titled
    "(Baby)" renders with no safety block, silently, with every other gate passing. That was
    true of `nordic-forest-mosaic-throw-baby`, which did not ship only because an unrelated
    colourwork gate failed: luck standing in for a gate.

    So the renderer asks `childrens_decision`, which separates them, and refuses the
    undecided case. This does not decide the audience -- that is a merchandising call and the
    catalogue is where it belongs. It requires that somebody made it: an assignment in
    `EXTRA_CHILDRENS_ASSIGNMENTS`, or an exemption with a reason in
    `NOT_MERCHANDISED_TO_A_CHILD`.
    """
    if childrens is not None:
        return
    from ..products import launch0

    words = launch0.child_words_in(cir.title, cir.slug)
    if not words:
        return
    state, _why = launch0.childrens_decision(cir.slug)
    if state != launch0.UNDECIDED:
        return
    raise ValueError(
        f"{cir.slug}: the title {cir.title!r} reads as a children's product ({', '.join(words)}) "
        f"and nothing has decided whether it is one. Refusing to render a document that would "
        f"carry no safety statements on nobody's decision. Assign it in "
        f"products.launch0.EXTRA_CHILDRENS_ASSIGNMENTS, or record the exemption and its reason "
        f"in products.launch0.NOT_MERCHANDISED_TO_A_CHILD")


def fibres_named(cir: CIR) -> tuple[tuple[str, ...], str]:
    """The fibre this pattern is written for, read from the CIR's own materials.

    Returns the distinct fibres named, and a sentence saying where they were read from or
    why nothing could be.

    Measures: each `Material.name` against `substitution.FIBRE_CLASSES`, which is the
    vocabulary this package already uses to decide what a yarn is made of.

    Why this is a reading and not an invention, and where it stops being safe:

    `cir.model.Material` has `name`, `yarn_weight`, `colorway`, `metres_estimate` and
    `color_id`. **There is no fibre field**, and `cir.writer.finishing_lines` says so in as
    many words -- it cites the ball band because "nothing here claims anything about a fibre
    this schema does not record". That is still true of the schema. It is not true of the
    documents: every Launch-0 material is named "worsted acrylic", "worsted cotton" or "dk
    cotton", the materials page of this very PDF already prints that name to the buyer, and
    `publish/substitution.py` already reads a fibre class out of the same field to write the
    substitution guidance the customer reads two pages earlier. So the fibre fact is present,
    customer-facing, and read from this field by production code today.

    What it is *not* is a fibre content. "worsted acrylic" is a yarn description, not "100%
    acrylic", and this module must not upgrade one into the other. The rendered statement
    therefore names the fibre the pattern was written for and leaves the composition of the
    finished item to the ball band of the yarn the maker actually bought.

    A material whose name contains no fibre word yields nothing, on purpose. The failure
    direction has to be "this cannot be stated" rather than a plausible default, so a CIR
    with `Material(name="Bernat Blanket")` makes `fibre_and_care` unrenderable and blocks the
    product rather than shipping a guess.
    """
    if not cir.materials:
        return (), "the CIR names no materials, so there is no yarn to read a fibre from"

    # Whole words, matched against one vocabulary. Sorted so that a two-fibre pattern names
    # its fibres in the same order on every render -- the document's bytes are hashed and a
    # set's iteration order is not a property anybody should have to rely on.
    known = sorted({fibre for family in substitution.FIBRE_CLASSES.values()
                    for fibre in family})
    found: list[str] = []
    silent: list[str] = []
    for material in cir.materials:
        name = (material.name or "").lower()
        words = set(re.findall(r"[a-z]+", name))
        hits = [fibre for fibre in known if fibre in words]
        if not hits:
            silent.append(material.name or "(unnamed)")
            continue
        for fibre in hits:
            if fibre not in found:
                found.append(fibre)

    if silent:
        return (), (
            f"the yarn name(s) {sorted(set(silent))} name no fibre this module recognises, "
            f"and cir.model.Material has no fibre field to fall back on. Naming a fibre here "
            f"would be inventing one")
    return tuple(found), (
        "read from cir.model.Material.name, the free-text yarn name, against "
        "publish.substitution.FIBRE_CLASSES. The CIR schema records no fibre field and no "
        "fibre content")


def childrens_facts(cir: CIR, twin: TwinModel, audience: str) -> ch.StatementFacts:
    """The derived facts the statement texts are rendered from, for this product.

    Measures: the twin's computed finished size, the CIR's declared colours, and the fibre
    its materials name.
    Why: every one of these is already established somewhere else in this document -- the
    size is on the cover, the colours are in the colour key, the fibre is on the materials
    page -- so deriving them is what stops the safety block becoming a second, stale copy of
    the pattern's own facts. A hard-coded "79 x 97 cm" in a safety note is a number that goes
    wrong the first time somebody changes the stitch count.
    """
    fibres, read_from = fibres_named(cir)
    size = ((twin.width_cm, twin.height_cm)
            if twin.width_cm and twin.height_cm else None)
    return ch.StatementFacts(
        audience=audience,
        finished_size_cm=size,
        colours=tuple(sorted(c for c in (cir.colors or {}) if c)),
        fibres=fibres,
        fibre_read_from=read_from,
    )


def childrens_statements(cir: CIR, twin: TwinModel,
                         assignment: tuple[str, str]) -> ch.RenderedStatements:
    """Everything this children's pattern must say, rendered, or the reason it cannot be."""
    subcategory, audience = assignment
    return ch.render_statements(subcategory, audience,
                                childrens_facts(cir, twin, audience))


def build_pattern_pdf(cir: CIR, *, terminology: str = "US",
                      twin: TwinModel | None = None,
                      designer: str = "Brambleloop Studio",
                      released_on: date | None = None,
                      childrens: tuple[str, str] | None = None) -> PatternDocument:
    """Render the full pattern document.

    Refuses outright if the CIR does not compile. A PDF built on failed arithmetic is a
    defect we would be charging money for, and the release chain is supposed to make that
    impossible rather than merely unlikely.

    Refuses a terminology it cannot render truthfully, for the same reason. `cir.writer`
    localises sc, dc, tr and the shaping stitches into UK terms and leaves the post stitches,
    the bobble and the cable crossings as their canonical codes -- and `fpdc` read as UK
    terms names a stitch half the height of the one the pattern was compiled against. A
    document that quietly instructs the wrong stitch is worse than one that does not exist.

    `released_on` is an argument rather than a reading of the clock wherever the caller knows
    the release date. Left to default it takes today's date, which is a wall-clock input to a
    render whose whole point is to be a pure function of the certified CIR -- see
    `_Doc`'s note on the hash.

    **Refuses a children's document that does not carry its full statement set**, for the
    third time and the same reason. `intel.childrens.required_statements` computes what a
    pattern for this audience must say; the block is rendered above; and then the finished
    PDF is read back and every required statement looked for in the extracted text. A
    document that is missing one is not shipped, because the object it describes is going to
    a child and "the safety page did not render" is not a defect a buyer can see. The check
    is run on the extracted bytes rather than on the template on purpose -- see
    `licence_paragraphs` for the last time a check compared a decision with itself and
    reported three surfaces consistent while the customer's document said something else.

    `childrens` names the sub-category and age band, and defaults to whatever
    `childrens_assignment` says about this CIR's slug. Passing it explicitly is for tests and
    for a caller that knows better than the catalogue; passing `("", "")` is not a way to
    turn the check off, because `render_statements` would reject the sub-category.
    """
    result = compile_cir(cir)
    if not result.ok:
        raise ValueError(
            f"refusing to render a PDF for a pattern that fails compilation: "
            f"{[str(f) for f in result.errors][:3]}"
        )
    twin = twin or build_twin(cir, result)
    released_on = released_on or date.today()

    stalled = sorted(set(abbreviations.unlocalised(terminology))
                     & set(twin.stitch_types_used))
    if stalled:
        raise ValueError(
            f"refusing to render a {terminology.upper()}-terms PDF containing "
            f"{stalled}: cir.writer prints those stitches as their canonical US codes, and "
            f"a {terminology.upper()} maker reading them would work a different stitch from "
            f"the one this pattern was compiled against"
        )

    text = write_pattern(cir, result, terminology=terminology,
                         width_cm=twin.width_cm, height_cm=twin.height_cm)

    # Rendered once and reused by both passes. The page count is not knowable until the
    # document has been laid out, and laying it out twice must not mean drawing a
    # two-thousand-pixel chart twice.
    art = _chart_art(cir, twin)

    # Laid out until the count it prints is the count it has. Printing "of 7" on a document
    # that turned out to be 8 pages long is worse than printing nothing, because a customer
    # would then believe a complete file was truncated. Two passes settle every document in
    # the catalogue; the loop exists so that one that does not is caught here rather than
    # sold, and its guarantee is asserted rather than assumed.
    childrens = childrens if childrens is not None else childrens_assignment(cir)
    _refuse_an_undecided_childrens_title(cir, childrens)

    total = 0
    for _ in range(4):
        doc, claims, problems = _render(cir, twin, result, text=text, art=art,
                                        terminology=terminology, designer=designer,
                                        released_on=released_on, total_pages=total,
                                        childrens=childrens)
        if doc.pages == total:
            break
        total = doc.pages
    else:  # pragma: no cover - no document in the catalogue oscillates
        raise ValueError(
            f"{cir.slug}: the page count does not settle, so the footer would state a "
            f"length the document does not have")

    pdf_bytes = doc.finish()
    if childrens is not None:
        _refuse_an_incomplete_childrens_document(cir, twin, pdf_bytes, childrens, terminology)

    return PatternDocument(
        pdf_bytes=pdf_bytes,
        pages=doc.pages,
        finished_size_cm=((twin.width_cm, twin.height_cm)
                          if twin.width_cm and twin.height_cm else None),
        yardage_by_color=dict(twin.yarn_metres_by_color),
        yardage_tolerance=twin.yardage_tolerance,
        calibrated=twin.calibrated,
        terminology=terminology,
        claims=claims,
        difficulty=_difficulty(cir, twin),
        released_on=released_on,
        problems=problems,
        prose="\n".join(doc.prose),
    )


def extracted_text(pdf_bytes: bytes) -> str:
    """Every word a text extractor can recover from the finished PDF, whitespace collapsed.

    Collapsed because a sentence in the document is wrapped to the column, so looking for one
    in the raw extraction is looking for a string the file does not contain in that form.
    This is what a reader sees rather than what the layout did.

    `_Doc.prose` is the other reading of the same document and it is not a substitute for
    this one: it is what the module *chose to say*, accumulated as it drew. If a draw call
    were wrong, if a page were dropped, if the section were laid out off the bottom of the
    last page, `prose` would still be complete and the file would not. The children's gate
    reads the bytes for that reason.
    """
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return " ".join("\n".join(page.extract_text() or "" for page in reader.pages).split())


def childrens_statements_in(pdf_bytes: bytes, assignment: tuple[str, str]) -> dict:
    """Which required statements the rendered document actually carries.

    Measures: each required statement's `marker` -- a phrase from its text that carries no
    placeholder -- against the text extracted from the PDF bytes.
    Why: this is the instrument `launch0.statement_rendering_gap` should have had from the
    start. A grep over `publish/*.py` for the word "choking" answers "does some source file
    mention the topic", which is a different question from "does the customer's PDF carry
    this statement" and can be satisfied by a comment. This can only be satisfied by the
    document.
    """
    subcategory, audience = assignment
    text = extracted_text(pdf_bytes)
    required = ch.required_statements(subcategory, audience)
    present = [k for k in required if ch.STATEMENT_SET[k].marker in text]
    return {
        "subcategory": subcategory,
        "audience": audience,
        "required": required,
        "present": tuple(present),
        "missing": tuple(k for k in required if k not in present),
        "complete": len(present) == len(required),
    }


def _refuse_an_incomplete_childrens_document(cir: CIR, twin: TwinModel, pdf_bytes: bytes,
                                             assignment: tuple[str, str],
                                             terminology: str) -> None:
    """Stop a children's pattern that does not say what it has to say.

    Refusal rather than a `problems` entry, and the difference is deliberate. `problems` is
    for a defect in a document that is still the right document -- a chart cell below the
    brand's minimum, a cable whose crossing direction the CIR cannot state. A children's
    pattern with no safe-sleep statement is not a slightly worse document; it is the document
    `intel.childrens.assess` returns "not ready to ship" for, and `assets.build` records
    problems without blocking on them, so a finding here would have been audited and shipped.
    """
    audit = childrens_statements_in(pdf_bytes, assignment)
    if audit["complete"]:
        return
    rendered = childrens_statements(cir, twin, assignment)
    reasons = [f"{key}: {why}" for key, why in sorted(rendered.unrenderable.items())]
    for key in audit["missing"]:
        if key not in rendered.unrenderable:
            reasons.append(
                f"{key}: rendered but not found in the finished document, so the section "
                f"did not reach the page")
    raise ValueError(
        f"refusing to render a {terminology.upper()}-terms PDF for {cir.slug}: it is a "
        f"{assignment[0]} product stated for children {assignment[1]}, "
        f"intel.childrens requires {list(audit['required'])}, and the rendered document "
        f"carries {list(audit['present'])}. " + " | ".join(reasons))


def _render(cir: CIR, twin: TwinModel, result, *, text: str, art: dict,
            terminology: str, designer: str, released_on: date,
            total_pages: int,
            childrens: tuple[str, str] | None = None) -> tuple["_Doc", list[str], list[str]]:
    """Lay the document out. Called twice: once to count the pages, once to print them."""
    doc = _Doc(f"{cir.title} - {designer}", total_pages=total_pages, author=designer,
               subject=f"Crochet pattern, {terminology.upper()} terms, version {cir.version}")
    head = f"{cir.title} - v{cir.version}"
    problems: list[str] = []

    # -- cover -------------------------------------------------------------
    doc.new_page()
    doc.c.setFillColor(PINE)
    doc.c.rect(0, PAGE_H - 62 * mm, PAGE_W, 62 * mm, fill=1, stroke=0)
    doc.c.setFillColor(CREAM)
    doc.c.setFont("Helvetica-Bold", 11)
    doc.c.drawString(MARGIN, PAGE_H - 22 * mm, designer.upper())
    doc.c.setFont("Helvetica-Bold", 26)
    doc.c.drawString(MARGIN, PAGE_H - 38 * mm, cir.title)
    doc.c.setFont("Helvetica", 11)
    doc.c.setFillColor(GOLD_ON_PINE)
    doc.c.drawString(MARGIN, PAGE_H - 48 * mm,
                     f"Crochet pattern - {terminology} terms - version {cir.version}")
    doc.y = PAGE_H - 78 * mm

    claims: list[str] = []
    doc.heading("At a glance")
    if twin.width_cm and twin.height_cm:
        size = f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm at the stated gauge"
        doc.kv("finished size", size)
        claims.append(size)
    doc.kv("difficulty", _difficulty(cir, twin))
    doc.kv("construction", cir.construction.replace("_", " "))
    if cir.gauge:
        doc.kv("gauge", f"{cir.gauge.stitches_per_10cm} sts x {cir.gauge.rows_per_10cm} rows "
                        f"= 10 cm in {_gauge_stitch(cir, terminology)}")
        doc.kv("hook", f"{cir.gauge.hook_mm:g} mm")
    doc.kv("colours", ", ".join(sorted(cir.colors)) or "one colour")
    doc.kv("released", released_on.isoformat())
    doc.space(4 * mm)
    doc.para(AI_DISCLOSURE, size=9, color=MUTED)

    # -- materials ---------------------------------------------------------
    doc.new_page(head)
    doc.heading("Materials")
    for m in cir.materials:
        described = f"{m.name} ({m.yarn_weight})"
        if m.colorway:
            # The colourway was in the CIR and in the written instructions, and the
            # materials list -- the page a buyer takes to the yarn shop -- dropped it.
            described += f", colourway {m.colorway}"
        doc.kv(m.color_id or m.name, described)
    if cir.gauge and cir.gauge.hook_mm:
        doc.kv("hook", f"{cir.gauge.hook_mm:g} mm, or whatever hook gets you the gauge below")
    # The special-stitch methods are part of what this document asks the maker to do, so the
    # tools they require belong on the shopping list too: without this the pattern told a
    # maker to slip stitches onto a cable needle on page 3 and listed only yarn on page 2.
    instructed = "\n".join([text] + [abbreviations.method(code, terminology)
                                     for code in sorted(twin.stitch_types_used)])
    for tool in _tools_required(cir, instructed):
        doc.kv(tool[0], tool[1])
    doc.space(3 * mm)
    doc.heading("How much yarn", size=12)
    if twin.yarn_metres_by_color:
        for name, metres in sorted(twin.yarn_metres_by_color.items()):
            low = metres * (1 - twin.yardage_tolerance)
            high = metres * (1 + twin.yardage_tolerance)
            doc.kv(name, f"about {low:.0f}-{high:.0f} m ({low * 1.094:.0f}-"
                         f"{high * 1.094:.0f} yd)")
    tolerance_note = (
        f"These quantities are estimates with a +/-{twin.yardage_tolerance * 100:.0f}% range, "
        "not measurements. Yarn consumption genuinely varies with yarn, hook and tension, so "
        "buy a little more than the top of the range if your dye lot matters to you."
        if not twin.calibrated else
        "These quantities were calibrated against a physically worked sample."
    )
    doc.para(tolerance_note, size=9, color=MUTED)
    doc.space(4 * mm)
    doc.heading("Gauge, and why it matters here", size=12)
    doc.para(
        "Work a swatch before you start. The finished size above is computed from the gauge "
        "above; if your gauge differs, your finished piece will differ by the same "
        "proportion. The stitch counts in this pattern are correct at any gauge -- only the "
        "measurements change.", size=10)

    # -- the row gauge the fabric actually has -----------------------------
    #
    # The sentence above is true of the width and only half true of the length. The width is
    # the stitch gauge multiplied by the stitch count; the length is accumulated row by row
    # using each row's own stitch height, so a pattern whose gauge is stated in sc and whose
    # fabric is mostly dc is *twice* as long as the stated row gauge implies.
    #
    # Found by reading the shipped document as a buyer: the Cloudline blanket states 18 rows
    # = 10 cm, and its own progress table says 88 rows come to 97 cm, which is 9 rows to 10
    # cm. A maker who checks their work against the stated gauge at row 22 finds the fabric
    # apparently twice as long as it should be and rips out a correct blanket. Both numbers
    # were right; the document simply never printed the one that reconciles them.
    fabric = _fabric_row_gauge(twin)
    if fabric and cir.gauge:
        drift = abs(fabric - cir.gauge.rows_per_10cm) / cir.gauge.rows_per_10cm
        if drift >= ROW_GAUGE_DRIFT:
            doc.space(2 * mm)
            doc.kv("swatch row gauge", f"{cir.gauge.rows_per_10cm} rows = 10 cm in "
                                       f"{_gauge_stitch(cir, terminology)}")
            doc.kv("this fabric", f"about {fabric:.0f} rows = 10 cm")
            doc.para(
                f"Those two numbers are both right and they are not the same number. The "
                f"swatch gauge is measured over plain {_gauge_stitch(cir, terminology)}; this pattern "
                f"is worked in taller stitches as well, so its rows stack up faster. Check "
                f"your stitches across against the swatch gauge, and check your rows against "
                f"the measurements in 'Checking your progress' below, which are the "
                f"fabric's own.", size=9, color=MUTED)

    # -- how to know it is going right (#7) --------------------------------
    #
    # A maker halfway up a blanket is asking one question: is what is on my hook what should
    # be on my hook. A progress picture they can only agree with does not answer it; a stitch
    # count and a measurement do.
    try:
        progress = value_stack.milestones(cir, twin)
    except value_stack.ValueStackRefused:
        progress = None
    if progress and len(progress["milestones"]) > 2:
        doc.heading("Checking your progress", size=12)
        doc.para(
            f"At these rows the fabric should measure roughly this much. If it does not, the "
            f"difference is gauge, and it is easier to fix now than at row "
            f"{progress['rows_total']}.", size=10)
        for mark in progress["milestones"]:
            doc.kv(f"row {mark['row']} of {progress['rows_total']}",
                   f"{mark['stitches_in_this_row']} stitches across, "
                   f"about {mark['height_so_far_cm']:.0f} cm made")

    # -- printing it (#7) ---------------------------------------------------
    #
    # Most home printers are greyscale, and a chart whose colours differ in hue but not in
    # lightness prints as one flat block. Said in the document, because the person it affects
    # is holding the document.
    printing = value_stack.print_safety(cir)
    if printing.get("measurable") and printing.get("prints") is False:
        # Named, not counted. This said "two of these colours are close in lightness"
        # regardless of how many pairs actually merge, and the measurement that decided to
        # print it already knows which ones -- `print_safety` returns `weakest_pair`, and every
        # pair that fails is in `pairs`. On a four-colour pattern where three merge, "two"
        # sends a maker looking for a pair that is not the problem.
        #
        # It has never been printed. No pattern in the catalogue fails this check, so the one
        # sentence in the document nobody has ever read was the one with the arithmetic
        # wrong in it -- a claim whose only sample could not contain the broken case.
        merging = printing.get("merging_pairs", [])
        pairs = " and ".join(" / ".join(p["between"]) for p in merging) or "two of these"
        doc.para(
            f"Printing in black and white: {pairs} are close in lightness and "
            f"will merge on a greyscale printer. The chart carries a letter for each colour, "
            f"so follow the letters rather than the shading.", size=9, color=MUTED)

    # -- substituting the yarn (#7) ----------------------------------------
    #
    # The first question a buyer asks about a pattern is the one nobody answers: I cannot get
    # that yarn, what can I use. It is answered here from this pattern's own gauge and
    # yardage rather than from a paragraph somebody wrote, and where it cannot be answered it
    # says so instead of offering a plausible number.
    try:
        guide = substitution.guidance(cir, twin)
    except substitution.SubstitutionRefused:
        guide = None
    if guide and guide["substitutes"]["weights"]:
        doc.heading("Substituting the yarn", size=12)
        names = ", ".join(
            f"{w['weight'].replace('_', ' ')} (also called {w['also_called'][0]})"
            for w in guide["substitutes"]["weights"])
        doc.para(
            f"Gauge decides this, not the name on the band. Any of these can be worked to "
            f"this fabric: {names}. Swatch and change hook until your gauge matches -- the "
            f"gauge is what makes the finished size come out.", size=10)
        for row in guide["how_much"]:
            if not row.get("measurable"):
                continue
            doc.kv(f"if you use {row['to'].replace('_', ' ')}",
                   f"about {row['buy_metres']:.0f} m in total "
                   f"({row['balls_100g'][0]}-{row['balls_100g'][1]} x 100g balls); "
                   f"{row['fabric_changes']}")
        if guide["declared_weight"] and not guide["substitutes"]["declared_holds_gauge"]:
            # Said out loud rather than quietly corrected. Which number is wrong -- the gauge
            # or the weight on the band -- is decided by a swatch, and this document has not
            # seen one. Picking a side here would be inventing a measurement.
            doc.para(
                f"Note: the gauge above sits outside the published band for "
                f"{guide['declared_weight'].replace('_', ' ')} yarn. Swatch before you buy: "
                f"either this fabric wants a different weight than the one named, or it wants "
                f"a different hook.", size=9, color=MUTED)
        doc.para(
            f"Those metres are this pattern's own estimate plus {substitution.BUY_MARGIN:.0%}. "
            f"Buying exactly enough is how a project ends one row short in a dye lot that has "
            f"gone. Changing fibre as well -- cotton for acrylic, say -- changes how much "
            f"yarn each stitch takes by an amount that has to be measured on a swatch, not "
            f"read off a table.", size=9, color=MUTED)

    # -- abbreviations ------------------------------------------------------
    #
    # The section this document did not have. Everything below is the document's own
    # vocabulary: each entry is a token that appears in the instructions overleaf, and the
    # meanings come from the canonical stitch registry rather than being restated here, so
    # the key cannot disagree with the compiler about what a code means. See
    # `publish/abbreviations.py` for why a key derived from the chart could not do this.
    doc.new_page(head)
    doc.heading("Abbreviations")
    doc.para(f"This pattern is written in {terminology.upper()} terms. Every abbreviation it "
             f"uses is below; nothing in the instructions is left to be looked up "
             f"elsewhere.", size=10)
    doc.space(2 * mm)
    key = abbreviations.stitch_key(text, terminology)
    for entry in key:
        doc.kv(entry.token, entry.means, upper=False)

    notation = abbreviations.notation_key(text)
    if notation:
        doc.space(3 * mm)
        doc.heading("How to read a row", size=12)
        for entry in notation:
            doc.kv(entry.token, entry.means, upper=False)

    methods = [e for e in key if e.method]
    if methods:
        doc.space(3 * mm)
        doc.heading("Special stitches", size=12)
        doc.para("These are the stitches in this pattern that are not simply worked into the "
                 "top of the stitch below. Work one of each before you start the piece.",
                 size=10)
        for entry in methods:
            doc.space(1 * mm)
            doc.kv(entry.token, entry.means, upper=False)
            doc.para(entry.method, size=9, color=MUTED)
    cables = abbreviations.CABLE_CODES & set(twin.stitch_types_used)
    if cables:
        doc.para(abbreviations.CABLE_DIRECTION_NOTE, size=9, color=MUTED)
        # Honest about what the document cannot say. The canonical `Stitch` record has no
        # field for which side the held stitches wait on, so a cable held at the front and
        # one held at the back are the same op to every check in this system -- and they are
        # mirror images in the fabric. Naming a side here would print a fact the compiler
        # never verified, which is the failure this company exists not to have.
        problems.append(
            f"PDF_CABLE_DIRECTION_UNSPECIFIED: {sorted(cables)} cross four stitches over "
            f"each other and the CIR records no crossing direction, so the document cannot "
            f"tell a maker whether the held stitches wait at the front or the back. The "
            f"piece is makeable and its cables may mirror the product photography. Needs a "
            f"field on cir.stitches.Stitch before the document can state it")

    # -- instructions ------------------------------------------------------
    doc.new_page(head)
    doc.heading(f"Instructions ({terminology} terms)")
    for block in text.split("\n"):
        if not block.strip():
            doc.space(2 * mm)
            continue
        if block.rstrip().endswith(":") or block.startswith("#"):
            doc.need(8 * mm, head)
            doc.c.setFont("Helvetica-Bold", 11)
            doc.c.setFillColor(PINE)
            doc.c.drawString(MARGIN, doc.y, block.lstrip("# ").strip())
            doc.y -= 6 * mm
        else:
            doc.para(block, size=10, running_head=head)

    # -- charts ------------------------------------------------------------
    doc.new_page(head)
    doc.heading("Chart")
    doc.para(art["caption"], size=9, color=MUTED)
    doc.space(2 * mm)
    doc.image(art["chart"], running_head=head)
    doc.image(art["legend"], running_head=head)
    # What is wrong with the chart, measured on the chart as it lands on the page. Carried onto
    # the document's problems so the release chain sees it, like every other finding here.
    problems.extend(art.get("problems", ()))
    doc.space(2 * mm)
    # The chart's symbols, in text, because the chart cannot be read without them.
    #
    # The legend is a picture: nothing in it is searchable, selectable or readable by a screen
    # reader, and it is gone entirely on a reader that dropped the images. The document used to
    # answer that with one sentence -- "the stitch key in the image above is also written out
    # under Abbreviations" -- and **that sentence was not true in the way that mattered**. The
    # Abbreviations page writes out the *abbreviations*: `cable2x2` means a cable worked over
    # four stitches. It has never contained a symbol. A maker who sees an X on the chart and
    # follows that pointer arrives at a page with no X on it, and the mapping from mark to
    # stitch existed in exactly one place in the whole deliverable: the rendered legend image.
    #
    # This is the same defect the colour key had on 2026-09-24 and the same fix, from the same
    # sources: `charts.GLYPHS` for the mark, `cir.stitches` through `abbreviations` for the
    # name, so the picture and the paragraph cannot disagree and neither can name a stitch in
    # the wrong terminology.
    symbols = _chart_symbols(cir, twin, terminology)
    if symbols:
        doc.space(2 * mm)
        doc.heading("Chart symbols", size=12)
        doc.para(_CHART_SYMBOL_NOTE_ROUND if is_round(cir, twin) else _CHART_SYMBOL_NOTE_FLAT,
                 size=9, color=MUTED)
        # Ordered by symbol, which is the direction this key is read in: a maker sees a mark
        # on the chart and looks it up. The legend image orders by stitch because it is a
        # stitch list; the mapping is the same mapping either way.
        for symbol, means in symbols:
            doc.kv(symbol, means, upper=False)
        doc.space(1 * mm)
        doc.para("The same key is drawn in the image above, and every stitch in it is also "
                 "defined under Abbreviations, earlier in this document.", size=9,
                 color=MUTED)

    # The colour key, in text, because the document tells the maker to rely on it.
    #
    # The chart marks every square with its yarn's letter, and the printing note above says in
    # so many words "follow the letters rather than the shading". The letter-to-yarn mapping
    # existed in one place: the rendered legend image. So the document instructed a maker to
    # use a key it had only drawn -- unsearchable, unselectable, invisible to a screen reader,
    # and gone entirely if the images fail to render on a reader that dropped them.
    #
    # `charts.color_letters` is the single source of the mapping; this prints it rather than
    # numbering the colours again, so the page and the picture cannot disagree.
    #
    # Printed only when the chart that was actually rendered carries letters, which is a
    # narrower question than "does this pattern use more than one yarn". A cropped round chart
    # of a basket shows rounds 1 to 24, and a basket's contrast bands are up the wall, in the
    # straight rounds the chart no longer draws -- so every round on the picture is cream and
    # not one of them carries a letter, while the document went on saying "each round number
    # on the chart carries its yarn's letter". That is the 2026-09-24 finding about squares on
    # a round chart arriving by a different route: a key describing a picture that is not in
    # front of the reader.
    cues = art.get("cues") or {}
    colours = [name for name in cir.colors if name]
    if cues:
        doc.space(2 * mm)
        doc.heading("Colour key", size=12)
        doc.para(COLOUR_CUE_NOTE_ROUND if is_round(cir, twin) else COLOUR_CUE_NOTE_FLAT,
                 size=9, color=MUTED)
        # Ordered by letter, which is the direction this key is read in: a maker sees a mark on
        # the chart and looks it up. The legend image orders by colour name because it is a
        # swatch list; the mapping is the same mapping either way.
        for name, cue in sorted(cues.items(), key=lambda kv: kv[1]):
            doc.kv(cue, f"{name}  {cir.colors.get(name, '')}".strip(), upper=False)
    elif len(colours) > 1:
        # More than one yarn and a chart that says nothing about which is which. The colours
        # still have to be listed -- they are on the materials page and in every written line
        # -- but not under a heading promising a key the picture does not carry.
        doc.space(2 * mm)
        doc.heading("Colours", size=12)
        doc.para("Every round this chart shows is worked in one colour, so no number on it "
                 "carries a colour letter. The written instructions name the yarn for every "
                 "row and round in the pattern.", size=9, color=MUTED)
        for name in colours:
            doc.kv(name, cir.colors.get(name, ""), upper=False)

    # -- the children's safety block ---------------------------------------
    #
    # Its own page, before the terms, because it is the section a buyer choosing a gift is
    # looking for and the one a maker has to have read before they start. Rendered only when
    # the catalogue says this product is merchandised to a child: a table runner acquiring a
    # safe-sleep note would be noise, and noise is how a real warning stops being read.
    #
    # A statement whose facts are missing is NOT printed with a hole in it and NOT quietly
    # dropped: it goes onto `problems` here and `build_pattern_pdf` then refuses to return
    # the document at all, because a children's deliverable missing a safety statement looks
    # finished.
    if childrens is not None:
        rendered = childrens_statements(cir, twin, childrens)
        doc.new_page(head)
        doc.heading(CHILDRENS_HEADING)
        doc.para(CHILDRENS_INTRO, size=10)
        doc.space(2 * mm)
        for statement_key in rendered.required:
            if statement_key not in rendered.text:
                continue
            doc.space(1 * mm)
            doc.heading(rendered.headings[statement_key], size=12)
            for block in rendered.text[statement_key].split("\n"):
                doc.para(block, size=10, running_head=head)
            citation = rendered.citations.get(statement_key)
            if citation:
                doc.para(citation, size=9, color=MUTED, running_head=head)
            else:
                # Said on the page, not only in the code. Three of these ten sentences are
                # this company's own practice rather than somebody's published rule, and a
                # reader who sees a source under seven of them is entitled to know that the
                # other three have none rather than assume the citation fell off.
                doc.para("Source: none. This is Brambleloop Studio's own practice rather "
                         "than a published rule.", size=9, color=MUTED, running_head=head)
        for statement_key, why in sorted(rendered.unrenderable.items()):
            problems.append(
                f"PDF_CHILDRENS_STATEMENT_UNRENDERABLE: {statement_key} is required for a "
                f"{childrens[0]} product stated for {childrens[1]} and this document cannot "
                f"state it: {why}")

    # -- licence -----------------------------------------------------------
    doc.new_page(head)
    doc.heading("Terms and support")
    # Rendered from `commerce.terms`, which is where these were decided. See
    # `licence_paragraphs` for why this module no longer holds a licence of its own.
    for i, line in enumerate(licence_paragraphs()):
        if not line.strip():
            doc.space(2 * mm)
        elif i == 0:
            # The decision's own heading for this surface, kept rather than paraphrased.
            doc.heading(line, size=12)
        elif line.startswith("- "):
            doc.para(line, size=10)
        else:
            doc.para(line, size=10, color=MUTED)
    doc.space(3 * mm)
    doc.para("If anything in this pattern does not add up, tell us through the shop you "
             "bought it from and we will fix the pattern itself, not just answer your "
             "question. Every report is checked against the compiler that validated this "
             "release.", size=10)
    doc.space(3 * mm)
    # A licence with no owner and no date is a paragraph of good intentions, and a support
    # promise with no pattern id is one nobody can act on. Neither line was in the document.
    #
    # Set as prose rather than as a labelled row on purpose: a labelled row is a
    # heading-shaped line, and the teardown reader's architecture schedule would then read
    # the licence as its own addressable section. It is a paragraph on the support page, and
    # the reader is right to report it as a mention and let the analyst decide.
    credit = "" if designer == COPYRIGHT_HOLDER else f" Designed by {designer}."
    doc.para(f"(c) {released_on.year} {COPYRIGHT_HOLDER}. All rights reserved.{credit}",
             size=9, color=MUTED)
    doc.space(2 * mm)
    doc.kv("release version", cir.version)
    doc.kv("released", released_on.isoformat())
    doc.kv("terminology", f"{terminology} terms")
    doc.kv("pattern id", f"{cir.slug}@{cir.version}")
    doc.space(3 * mm)
    doc.para(f"This document is {doc.total_pages or doc.pages} pages. If your copy is "
             f"shorter than that, the download did not finish; ask for it again rather than "
             f"working from a partial pattern.", size=9, color=MUTED)

    # -- is the key a key? -------------------------------------------------
    #
    # Run here, last, because it is a property of the finished document and not of any one
    # section. It was run on the writer's instruction text against a key derived from that
    # same text, which is a comparison that cannot come out badly: every token in the string
    # is in the key by construction. The check carried a `pragma: no cover` admitting the
    # branch was unreachable, under a docstring calling itself "the inverse check, and the one
    # that matters".
    #
    # Measured now on everything the document says, against the key it actually printed. That
    # comparison can fail, and did: the cover's gauge line named `sc` in a UK document whose
    # key defines `dc`.
    missing = abbreviations.undefined_tokens(
        "\n".join(doc.prose), terminology,
        defined={entry.token for entry in key})
    if missing:
        # Reported rather than silently omitted: a key that is quietly short is worse than
        # no key, because the maker stops expecting to find things in it.
        problems.append(
            f"PDF_ABBREVIATION_UNDEFINED: {sorted(set(missing))} appear in this document and "
            f"the stitch key printed in it does not define them, so a maker meets a word the "
            f"document never explains")

    return doc, claims, problems


# How far the fabric's own row gauge may sit from the swatch gauge before the document has to
# reconcile the two out loud. Set at a tenth because a maker checking their work cannot tell
# a 10% difference from their own tension, and can tell a 50% one -- which is what a pattern
# stated in sc and worked in dc actually produces.
ROW_GAUGE_DRIFT = 0.10


def _fabric_row_gauge(twin: TwinModel) -> float | None:
    """How many rows of *this pattern's fabric* make 10 cm, from the twin's own height.

    Read off the twin rather than re-derived from the stitch heights, so it cannot become a
    second opinion about a measurement the twin has already made.
    """
    rows = len(twin.row_widths)
    if not rows or not twin.height_cm:
        return None
    return rows / twin.height_cm * 10.0


def _tools_required(cir: CIR, text: str) -> list[tuple[str, str]]:
    """Everything other than yarn and a hook that the instructions in *this* document ask for.

    A materials list is the page a buyer takes to the shop, and this one listed yarn and
    nothing else while the finishing section told them to weave in the ends and pin the piece
    out to size. Each entry is here because a line of this document requires it, so the list
    cannot drift into a generic "you will need" block promising tools the pattern never uses.
    """
    low = text.lower()
    out: list[tuple[str, str]] = []
    if "weave in" in low or "fasten off" in low:
        out.append(("tapestry needle",
                    "blunt, with an eye big enough for your yarn, for weaving in the ends"))
    if "pin it out" in low or "block the finished" in low:
        out.append(("blocking pins and a surface",
                    "for pinning the piece out damp to the finished measurements"))
    if "marker" in low:
        out.append(("stitch marker", "to mark the first stitch of each round"))
    if "cable needle" in low:
        out.append(("cable needle",
                    "or a short double-pointed needle, to hold the crossing stitches"))
    if "stitch holder" in low or "waste yarn" in low:
        out.append(("stitch holder or waste yarn",
                    "for the stitches set aside and worked later"))
    return out


_CHART_SYMBOL_NOTE_FLAT = (
    "The symbol in the middle of each square on the chart is its stitch. Every symbol the "
    "chart uses is below.")
_CHART_SYMBOL_NOTE_ROUND = (
    "A round chart marks where the stitch count changes rather than every stitch, so these "
    "are the marks it carries. Every other stitch in the round is the plain stitch the "
    "written line names.")


def _chart_symbols(cir: CIR, twin: TwinModel, terminology: str) -> list[tuple[str, str]]:
    """(symbol, what it means) for every mark the chart actually draws, in this terminology.

    A round chart draws a mark only where the count changes, so listing every stitch's symbol
    beside one would describe marks that are not on the page -- the same mistake as telling a
    round chart's reader that "each square carries its yarn's letter" when a round chart has
    no squares.

    The name arrives through `publish.abbreviations`, which reads `cir.stitches`. Nothing here
    spells a stitch out, so a UK document cannot acquire a US name by way of a chart key.
    """
    codes = sorted(twin.stitch_types_used)
    if is_round(cir, twin):
        codes = [c for c in codes if c in chart_mod.ROUND_MARKED_CODES]
    rows = [(chart_mod.GLYPHS.get(code, code[:1]),
             f"{abbreviations.token(code, terminology)}   "
             f"{abbreviations.meaning(code, terminology)}")
            for code in codes]
    return sorted(rows)


def chart_image(cir: CIR, twin: TwinModel):
    """The chart this product's document prints, for a caller that wants it on its own.

    Public because `runtime/release.py` stores a standalone `chart.png` beside the PDF and
    renders it with `render_any_chart` at the default spec -- which for a seventy-round basket
    is the whole disc at 1.2 mm per ring, the chart the document itself no longer prints. One
    release, two charts, and the illegible one is the one with a URL. The release chain is not
    this lane's file; this is the one call it needs.
    """
    return _chart_art(cir, twin)["chart"]


def _round_span(first: int, last: int, *, dash: bool = False) -> str:
    """'44' for one round, '44-45' or '25 to 70' for a run."""
    if first == last:
        return f"{first}"
    return f"{first}-{last}" if dash else f"{first} to {last}"


def _straight_tail_sentence(block: RoundBlock) -> str:
    """What the chart leaves out, in the numbers the written instructions use.

    A chart that shows part of a piece and does not say so is a new defect rather than a fix,
    which is the rule the flat chart's caption already follows. Every number here is read back
    out of the twin, so the sentence cannot drift from the fabric it describes.
    """
    out = (f"Rounds {_round_span(block.tail[0], block.tail[-1])} are then worked straight at "
           f"{block.tail_stitches} stitches with no increases. Drawing them would add "
           f"{len(block.tail)} identical rings and shrink every ring in this chart, so the "
           f"chart stops at round {block.last}.")
    if block.tail_color and not block.tail_other_colors:
        out += (f" They are all worked in {block.tail_color}, and the written instructions "
                f"give the colour of every round.")
    elif block.tail_color:
        by_colour: dict[str, list[str]] = {}
        for name, a, b in block.tail_other_colors:
            by_colour.setdefault(name, []).append(_round_span(a, b, dash=True))
        runs = "; ".join(f"rounds {' and '.join(spans)} in {name}"
                         for name, spans in by_colour.items())
        out += (f" They are worked in {block.tail_color} except {runs}, and the written "
                f"instructions give the colour of every round.")
    else:
        out += " The written instructions give the colour of every round."
    return out


def _round_chart_art(cir: CIR, twin: TwinModel) -> dict:
    """The chart for a piece worked in the round, chosen on the size a ring lands at.

    A round chart's readable unit is the width of a ring, and until now nothing measured it:
    `_chart_art` reported `cell_mm: None`, so the legibility check below read this chart as
    *not applicable* rather than as *checked*. Measured, the Launch-0 nesting baskets drew
    rings **1.2 mm** wide carrying round numbers of about **2pt** -- three times worse than the
    1.9 mm flat chart that was the worst thing in the previous audit, on the flagship product,
    and invisible because the one number that would have shown it was `None`.

    The ladder is the round counterpart of what the flat chart already does, and each rung is
    the answer to a different reason the chart is too small:

    1. the whole disc, which is what a piece with few rounds should get and what the hexagon
       coaster still gets;
    2. the rounds that shape the piece, when the rest is worked straight -- a basket is a flat
       base with a cylinder standing on it, and drawing forty-six wall rounds as forty-six
       concentric rings is both illegible and a picture of a disc the basket is not;
    3. one of the identical wedges every round repeats around, which puts the chart's radius
       across the page instead of its diameter;
    4. one wedge of the whole piece, for a piece with no straight tail to leave out.

    A rung is only rendered if its geometry could clear the floor, because a rung that cannot
    is a 2400-pixel square drawn to be thrown away. The number reported is measured on the
    image that was actually produced, never on the prediction.
    """
    spec = ChartSpec(cell_px=22)
    block = round_block(twin)
    wedges = wedge_count(twin)
    span = (block.first, block.last) if block else None
    ladder: list[tuple[tuple[int, int] | None, int | None]] = [(None, None)]
    if block is not None:
        ladder.append((span, None))
    if wedges > 1:
        if block is not None:
            ladder.append((span, wedges))
        ladder.append((None, wedges))

    predicted = []
    for rounds, w in ladder:
        ring, disc_w, disc_h = round_chart_size(twin, spec, rounds=rounds, wedges=w)
        predicted.append((_on_page_cell_mm(disc_w, disc_h, ring), rounds, w, ring))

    chart = None
    for ring_mm, rounds, w, ring in predicted:
        if ring_mm < CHART_MIN_RING_MM:
            continue
        chart = render_round_chart(cir, twin, spec, rounds=rounds, wedges=w)
        measured = _on_page_cell_mm(chart.width, chart.height, ring)
        if measured >= CHART_MIN_RING_MM:
            break
    else:
        # Nothing clears the floor. Print the largest ring available and say the number.
        ring_mm, rounds, w, ring = max(predicted, key=lambda p: p[0])
        chart = render_round_chart(cir, twin, spec, rounds=rounds, wedges=w)
        measured = _on_page_cell_mm(chart.width, chart.height, ring)

    first_shown = rounds[0] if rounds else min(c.row for c in twin.cells)
    caption = ("This piece is worked in the round, so the chart is drawn as rounds: "
               f"round {first_shown} at the centre, each ring outward one round. ")
    if w and w > 1:
        caption += (f"The {w} wedges of every round are identical, so the chart shows one of "
                    f"them: count the wedges in a ring and multiply by {w} to get the stitch "
                    f"count in the written line for that round, because both come from the "
                    f"same verified data. ")
    else:
        caption += ("Count the wedges in a ring and you get the stitch count in the written "
                    "line for that round, because both come from the same verified data. ")
    if rounds and block is not None:
        caption += (f"It shows rounds {_round_span(block.first, block.last)}, which are the "
                    f"rounds that shape the piece. "
                    f"{_straight_tail_sentence(block)} ")
    # Named from the marks this chart draws rather than written out: `GLYPHS` draws a double
    # crochet increase as W, and a caption saying "V marks an increase" on a disc worked in
    # double crochet would name a mark that is not on the page. Read from the rounds that were
    # drawn, not from the whole piece, for the same reason.
    caption += chart_mod.round_mark_note(
        {c.stitch for c in twin.cells
         if rounds is None or rounds[0] <= c.row <= rounds[1]})
    caption = caption.strip()

    problems: list[str] = []
    if measured < CHART_MIN_RING_MM:
        problems.append(
            f"PDF_CHART_CELL_BELOW_BRAND_MINIMUM: each chart ring renders at "
            f"{measured:.1f} mm on the page, carrying a round number of about "
            f"{measured * mm * chart_mod.ROUND_TYPE_RATIO:.0f}pt against the brand minimum "
            f"of {MIN_BODY_PT}pt, so the chart is present and not readable")

    # Which colours the picture actually labels, asked of the function the renderer used.
    labelled = chart_mod.round_cue_labels(cir, twin, ring_px=ring, rounds=rounds)
    letters = color_letters(cir)
    cues = {name: letter for name, letter in letters.items()
            if letter in set(labelled.values())}

    return {
        "chart": chart,
        "legend": render_legend(cir, twin),
        "caption": caption,
        "cell_mm": measured,
        "cues": cues,
        "problems": problems,
    }


def _chart_art(cir: CIR, twin: TwinModel) -> dict:
    """The chart, its legend and the sentence that explains them, rendered once.

    Lifted out of the page loop because the document is now laid out twice -- once to learn
    how many pages it has, once to print that number in the footer -- and a two-thousand-pixel
    chart must not be drawn twice to find that out.
    """
    if is_round(cir, twin):
        # A ragged grid is not a chart of a disc, and "read odd rows right to left" is
        # flat-fabric advice: every round is worked in the same direction.
        return _round_chart_art(cir, twin)

    grid, colour_grid = twin.chart_grid(), twin.color_grid()
    full_cols = max((len(r) for r in grid), default=0)
    full_rows = len(grid)
    rep_cols, rep_rows = detect_repeat(grid, colour_grid)
    across = full_cols // rep_cols if rep_cols else 1

    # How many rows the chart has to show, from the detector the written pattern already uses.
    #
    # `detect_repeat` looks for a row period that divides the row count and starts at row 1.
    # Eight of the sixteen shippable designs satisfy neither -- they open with setup rows and
    # then repeat a block whose period is not a divisor of the total -- so it answered "the
    # repeat is the whole fabric", and the chart page printed 121 rows of a cabled throw under
    # the words "this chart shows one repeat: 8 stitches wide and 121 rows tall", three pages
    # after written instructions saying "Repeat rows 2-5 29 more times".
    #
    # `charts.row_block` asks `cir.rowcycle`, which is the canonical answer: the written pattern
    # collapses to it and the reverse compiler expands it back again.
    block = row_block(cir, twin)
    block_rows = min(rep_rows, block[1]) if block else rep_rows

    full = render_chart(cir, twin, ChartSpec(cell_px=22))
    problems: list[str] = []

    # Decided on the size a cell ends up on the page, not on a column count.
    #
    # The old gate was `full_cols > 48`, a proxy for "this will be too small to read", and it is
    # wrong for a tall pattern: the harvest table runner is 48 stitches wide, failed the gate by
    # one, and printed its whole 48 x 112 fabric at 2.1 mm per cell. Measure the thing that
    # matters instead.
    if _on_page_cell_mm(full.width, full.height,
                        cell_size(twin, ChartSpec(cell_px=22))) < CHART_MIN_CELL_MM \
            and (rep_cols < full_cols or block_rows < full_rows):
        grids = crop_grids(grid, colour_grid, rep_cols, block_rows)
        chart = render_chart(cir, twin, ChartSpec(cell_px=20), grids=grids,
                             caption=f"{cir.title} - rows 1-{block_rows}, "
                                     f"{rep_cols} sts wide")
        charted_cell = cell_size(twin, ChartSpec(cell_px=20), grids)
        charted_colors = grids[1]
        cell_mm = _on_page_cell_mm(chart.width, chart.height, charted_cell)
        if block and block[1] == block_rows:
            start, end, repeats = block
            placement = (f"It shows rows 1 to {end}: work rows 1 to {end} once, then work "
                         f"rows {start} to {end} {_times(repeats)} more, exactly as the "
                         f"written instructions say. ")
        else:
            up = full_rows // block_rows if block_rows else 1
            placement = (f"It shows one repeat, {block_rows} rows tall. Work it "
                         f"{_times(up)} up the piece. ")
        caption = (f"This chart shows {rep_cols} of the {full_cols} stitches across: the "
                   f"pattern repeats every {rep_cols} stitches, so work the chart "
                   f"{_times(across)} across the row. {placement}The full piece is "
                   f"{full_cols} stitches by {full_rows} rows. The chart is generated from "
                   f"the same verified data as the written instructions, so the two cannot "
                   f"disagree. Read odd rows right to left and even rows left to right.")
    else:
        chart = full
        charted_cell = cell_size(twin, ChartSpec(cell_px=22))
        charted_colors = colour_grid
        cell_mm = _on_page_cell_mm(full.width, full.height, charted_cell)
        caption = ("The chart below is generated from the same verified data as the written "
                   "instructions above. Read odd rows right to left and even rows left to "
                   "right.")

    if cell_mm < CHART_MIN_CELL_MM:
        # Reported with the measurement in it, because "the chart is small" is an opinion and
        # "each cell is 2.1 mm on the printed page, carrying a 4pt glyph" is a fact somebody can
        # act on. Nothing measured this before: the chart's type is pixels inside an image, so
        # the source-level check that holds the rest of the document to the brand's 9pt minimum
        # never saw it.
        problems.append(
            f"PDF_CHART_CELL_BELOW_BRAND_MINIMUM: each chart cell renders at "
            f"{cell_mm:.1f} mm on the page, carrying a glyph of about "
            f"{cell_mm * mm * CHART_GLYPH_RATIO:.0f}pt against the brand minimum of "
            f"{MIN_BODY_PT}pt, so the chart is present and not readable")

    return {
        "chart": chart,
        "legend": render_legend(cir, twin),
        "caption": caption,
        "cell_mm": cell_mm,
        # What the picture actually says about colour, asked of the function that drew it. A
        # chart cropped to one repeat can be single-colour in a two-colour design, and a key
        # for letters the picture does not carry is a key to nothing.
        "cues": chart_mod.flat_cue_letters(cir, charted_colors, charted_cell),
        "problems": problems,
    }


def _times(n: int) -> str:
    """'once', not '1 times'. The shipped document said the second one."""
    return "once" if n == 1 else f"{n} times"


# Chart type is a fraction of the chart's readable unit -- the cell on a flat chart, the ring
# on a round one -- and those fractions are stated once, in the module that sets the type.
#
# The ratio used here was a copy of `0.62` written out in this file, and it was the *largest*
# piece of type in the picture. A floor derived from the largest type certifies the one thing
# that was never in danger: at a cell sized so the stitch glyph reaches 9pt, the row numbers
# land at 7.9pt and the colour cue at 6.6pt, both under the brand's own minimum, in the same
# image, measured on the same page. The floor is derived from the smallest type each kind of
# chart sets, which is the only version of it that means what it says.
CHART_GLYPH_RATIO = chart_mod.FLAT_TYPE_RATIO
CHART_MIN_CELL_MM = MIN_BODY_PT / chart_mod.FLAT_TYPE_RATIO / mm
CHART_MIN_RING_MM = MIN_BODY_PT / chart_mod.ROUND_TYPE_RATIO / mm


def _on_page_cell_mm(width: float, height: float, cell_px: float) -> float:
    """How big one chart cell is once `_Doc.image` has fitted the picture to the page.

    The chart is rendered in pixels and then scaled to fit, so nothing about the rendered image
    says how large a cell will be where the customer reads it. This is the same arithmetic
    `_Doc.image` does, which is why it is the number to check against a legibility floor -- and
    it is why the sliver was invisible: every check upstream was measuring the image.

    Takes a size rather than an image so that the same arithmetic can answer "how large would a
    ring be if this chart were drawn that way" without drawing it. A seventy-round basket's
    chart is a 2384-pixel square; choosing between four of them by rendering all four is a
    price the document should not pay to ask a question about geometry.
    """
    usable_w = PAGE_W - 2 * MARGIN
    usable_h = PAGE_H - 2 * MARGIN
    scale = min(1.0, usable_w / width)
    if height * scale > usable_h:
        scale *= usable_h / (height * scale)
    return cell_px * scale / mm
