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

import hashlib
import io
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

from ..brand import bible, identity_system, pdf_fonts
from ..gates import platform_policy
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

# The brand's typefaces, embedded (brand.pdf_fonts). The document was set in Helvetica, which
# is not one of the identity's families and is not embedded: the page a buyer's reader drew
# was whichever sans-serif it had to hand.
FONT_DISPLAY = "BL-Display"            # Cormorant Garamond SemiBold: titles and sections
FONT_DISPLAY_BOLD = "BL-Display-Bold"
FONT_DISPLAY_ITALIC = "BL-Display-Italic"
FONT_BODY = "BL-Body"                  # Lora: everything a maker reads
FONT_BODY_ITALIC = "BL-Body-Italic"
FONT_BODY_BOLD = "BL-Body-SemiBold"
FONT_UI = "BL-UI"                      # Work Sans: labels, running heads, folios
FONT_UI_MEDIUM = "BL-UI-Medium"
FONT_UI_BOLD = "BL-UI-SemiBold"
# What a key/value row sets its label in, named for the layout checks that look for it.
FONT_LABEL = FONT_UI_MEDIUM

# The palette, read from the brand identity (`brand.identity_system`, D-FB-16/17) rather than
# restated here. It was read from `brand.bible`'s older palette, which the identity superseded
# for every customer surface except, until now, the one the customer keeps.
_ROLES = identity_system.ROLES
_IDP = identity_system.PALETTE
PAPER = colors.HexColor(_ROLES["background"])
SURFACE = colors.HexColor(_ROLES["surface"])
FOREST = colors.HexColor(_ROLES["text"])
ROSE = colors.HexColor(_ROLES["accent"])          # decoration only, never small text
SAGE_MIST = colors.HexColor(_IDP["sage_mist"])
LINE = colors.HexColor(_IDP["yarn_light"])
GOLD = colors.HexColor(_IDP["pollen"])            # decoration only

# Names the rest of the package (and its tests) read. INK is body text, PINE the heading
# colour, CREAM the paper.
INK = FOREST
PINE = FOREST
CREAM = PAPER

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

    The maths lives in `brand.bible` so that the chart renderer applies the same rule to the
    same palette; this is the reportlab wrapper around it. Every text colour below is the
    brand's own colour passed through this, measured on the darker of the two grounds the
    document sets text on (the paper; the panels are lighter still).
    """
    r, g, b = bible.legible((fg.red, fg.green, fg.blue), (bg.red, bg.green, bg.blue),
                            minimum=minimum)
    return colors.Color(r, g, b)


MUTED = _legible(colors.HexColor(_ROLES["text_muted"]), PAPER)
ACCENT = _legible(colors.HexColor(_ROLES["accent_text"]), PAPER)    # rose_deep: kickers, counts
TAUPE = _legible(colors.HexColor(_ROLES["descriptor"]), PAPER)      # small caps labels
# Text set on the forest ground (the cover's lower band).
GOLD_ON_PINE = _legible(colors.HexColor(_IDP["rose_light"]), FOREST)
PAPER_ON_FOREST = _legible(colors.HexColor(_ROLES["inverse_text"]), FOREST)

# Vertical rhythm.
HEADER_Y = PAGE_H - 11 * mm
CONTENT_TOP = PAGE_H - MARGIN - 3 * mm
FOOTER_Y = 9 * mm


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
    # Every picture the document places, in order: what it is and where it came from. A
    # reviewer checks the provenance of each image from here rather than by guessing.
    figures: list[dict] = field(default_factory=list)

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

    Every string is drawn through `text`, which checks it against the face it is set in
    (`brand.pdf_fonts.missing_glyphs`): an embedded TrueType face draws an empty box for a
    character it lacks, and the extracted text still reads correctly, so nothing downstream
    could see it.
    """

    def __init__(self, title: str, *, total_pages: int = 0, author: str = "",
                 subject: str = "", footer_left: str = "", header_right: str = "",
                 proof_banner: str = ""):
        pdf_fonts.register()
        self.buf = io.BytesIO()
        # `initialFontName` so the page streams never reference an unembedded base-14 face.
        self.c = rl_canvas.Canvas(self.buf, pagesize=LETTER, invariant=1,
                                  initialFontName=FONT_BODY, initialFontSize=10)
        self.c.setTitle(title)
        # Set because a PDF with no author and no subject is an untitled file in a downloads
        # folder six months later, and because assistive software reads them first.
        if author:
            self.c.setAuthor(author)
        if subject:
            self.c.setSubject(subject)
        # reportlab's default is the literal string "anonymous", which is what a buyer sees
        # under Application in any reader's document-properties panel.
        self.c.setCreator("Brambleloop Studio pattern compiler")
        # The document's natural language, in the catalogue where assistive software looks
        # for it; without it a screen reader guesses from the system locale.
        self.c.setCatalogEntry("Lang", "en-GB")
        # Known only on the second pass. "page 5 of 7" lets a buyer see that a download
        # stopped early, which "page 5" cannot.
        self.total_pages = total_pages
        self.pages = 0
        self.y = CONTENT_TOP
        self.footer_left = footer_left
        self.header_right = header_right
        # Every word this document sets, in the order it sets it -- what the checks read.
        self.prose: list[str] = []
        self.bookmarks: list[str] = []
        self.glyph_problems: list[str] = []
        self.figures: list[dict] = []
        self.running_head: str | None = None
        # F9: a proof is marked on every page, so a page printed or extracted on its own
        # still says it is not the product.
        self.proof_banner = proof_banner

    def _bookmark(self, title: str) -> None:
        key = f"section-{len(self.bookmarks) + 1}-{re.sub(r'[^a-z0-9]+', '-', title.lower())}"
        self.bookmarks.append(title)
        self.c.bookmarkPage(key)
        self.c.addOutlineEntry(title, key, level=0)

    # -- the one way text reaches the page -----------------------------------------------
    def text(self, x: float, y: float, s: str, font: str = FONT_BODY, size: float = 10,
             color=INK, *, align: str = "left", track: float = 0.0) -> float:
        """Draw one line; returns its width. Refuses nothing, records every missing glyph."""
        if size < MIN_BODY_PT:
            self.glyph_problems.append(
                f"PDF_TYPE_BELOW_BRAND_MINIMUM: {s[:40]!r} set at {size}pt")
        missing = pdf_fonts.missing_glyphs(font, s)
        if missing:
            self.glyph_problems.append(
                f"PDF_GLYPH_MISSING: {font} has no glyph for {list(missing)} in {s[:60]!r}")
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        width = self.width(s, font, size, track)
        if align == "right":
            x -= width
        elif align == "centre":
            x -= width / 2
        if track:
            self.c.drawString(x, y, s, charSpace=track)
        else:
            self.c.drawString(x, y, s)
        return width

    @staticmethod
    def width(s: str, font: str, size: float, track: float = 0.0) -> float:
        return stringWidth(s, font, size) + track * max(0, len(s) - 1)

    # -- pages ---------------------------------------------------------------------------
    def new_page(self, running_head: str | None = None) -> None:
        if self.pages:
            self._footer()
            self.c.showPage()
        self.pages += 1
        self.c.setFillColor(PAPER)
        self.c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        self.y = CONTENT_TOP
        self.running_head = running_head
        if self.proof_banner:
            self.text(PAGE_W / 2, PAGE_H - 4.6 * mm, self.proof_banner, FONT_UI_BOLD,
                      MIN_BODY_PT, ACCENT, align="centre", track=0.8)
        if running_head:
            self.text(MARGIN, HEADER_Y, running_head.upper(), FONT_UI_MEDIUM, MIN_BODY_PT,
                      TAUPE, track=0.9)
            if self.header_right:
                self.text(PAGE_W - MARGIN, HEADER_Y, self.header_right.upper(), FONT_UI,
                          MIN_BODY_PT, TAUPE, align="right", track=0.9)
            self.c.setStrokeColor(LINE)
            self.c.setLineWidth(0.6)
            self.c.line(MARGIN, HEADER_Y - 3 * mm, PAGE_W - MARGIN, HEADER_Y - 3 * mm)

    # Set by a page whose foot sits on a dark ground (the cover's forest band), so the folio
    # is drawn in the reversed ink rather than in a grey that measures 1.5:1 on it.
    reversed_footer_pages: set

    def _footer(self) -> None:
        dark = self.pages in getattr(self, "reversed_footer_pages", set())
        ink = PAPER_ON_FOREST if dark else MUTED
        if not dark:
            self.c.setStrokeColor(LINE)
            self.c.setLineWidth(0.6)
            self.c.line(MARGIN, FOOTER_Y + 5 * mm, PAGE_W - MARGIN, FOOTER_Y + 5 * mm)
        if self.footer_left:
            self.text(MARGIN, FOOTER_Y, self.footer_left, FONT_UI, MIN_BODY_PT, ink)
        self.text(PAGE_W - MARGIN, FOOTER_Y,
                  f"page {self.pages} of {self.total_pages or self.pages}",
                  FONT_UI_MEDIUM, MIN_BODY_PT, ink, align="right")

    def space(self, amount: float) -> None:
        self.y -= amount

    def need(self, amount: float, running_head: str | None = None) -> bool:
        """Start a new page if `amount` does not fit; True when it did."""
        if self.y - amount < MARGIN:
            self.new_page(running_head if running_head is not None else self.running_head)
            return True
        return False

    # Headings at or above this size are the document's sections, and each one becomes a
    # bookmark: a buyer works this pattern from a phone with the piece in their hands, and a
    # PDF with no outline is pages of scrolling every time they want the chart back.
    OUTLINE_HEADING_PT = 15

    def heading(self, text: str, size: int = 15, *, kicker: str = "") -> None:
        """A section title (size >= 15) or a subheading. `kicker` is the small label above."""
        self.prose.append(text)
        if size >= self.OUTLINE_HEADING_PT:
            self.need(26 * mm)
            self._bookmark(text)
            if kicker:
                self.text(MARGIN, self.y, kicker.upper(), FONT_UI_BOLD, MIN_BODY_PT, ACCENT,
                          track=1.2)
                self.y -= 9 * mm
            else:
                self.y -= 4 * mm
            self.text(MARGIN, self.y, text, FONT_DISPLAY, 27, FOREST)
            self.y -= 5 * mm
            self.c.setStrokeColor(ROSE)
            self.c.setLineWidth(1.4)
            self.c.line(MARGIN, self.y, MARGIN + 16 * mm, self.y)
            self.y -= 8 * mm
        else:
            self.need(16 * mm)
            self.y -= 2 * mm
            self.text(MARGIN, self.y, text, FONT_DISPLAY_BOLD, 16, FOREST)
            self.y -= 6.5 * mm

    def label(self, text: str, *, x: float | None = None, color=None) -> None:
        """A small tracked-caps label line (Work Sans), e.g. above a table."""
        self.prose.append(text)
        self.need(7 * mm)
        self.text(MARGIN if x is None else x, self.y, text.upper(), FONT_UI_BOLD,
                  MIN_BODY_PT, color or TAUPE, track=1.0)
        self.y -= 5.5 * mm

    def para(self, text: str, size: float = 10, color=INK, leading: float | None = None,
             running_head: str | None = None, *, font: str = FONT_BODY,
             x: float | None = None, width: float | None = None,
             keep: bool = False) -> None:
        self.prose.append(text)
        leading = leading or size * 1.42
        x = MARGIN if x is None else x
        usable = (PAGE_W - MARGIN - x) if width is None else width
        lines = _wrap(self.c, text, font, size, usable)
        # No widows or orphans: a short paragraph moves whole, a long one keeps at least two
        # lines at the foot of a page and carries at least two to the next.
        # `keep`: a caption is never split across a page (N5).
        if len(lines) <= 4 or keep:
            self.need(len(lines) * leading, running_head)
        else:
            self.need(2 * leading, running_head)
        for n, line in enumerate(lines):
            if len(lines) > 4 and not keep and n == len(lines) - 2:
                self.need(2 * leading, running_head)
            self.need(leading, running_head)
            if line:
                self.text(x, self.y, line, font, size, color)
            self.y -= leading
        self.y -= 1.2 * mm

    def para_height(self, text: str, size: float = 10, *, font: str = FONT_BODY,
                    width: float | None = None, leading: float | None = None) -> float:
        leading = leading or size * 1.42
        usable = PAGE_W - 2 * MARGIN if width is None else width
        return len(_wrap(self.c, text, font, size, usable)) * leading + 1.2 * mm

    def kv(self, key: str, value: str, *, upper: bool = True) -> None:
        """A label and its value. `upper` is off for anything the maker has to type-match.

        An abbreviation is a lowercase token in every crochet pattern ever printed, and a
        key that shouts "CH" at a beginner who is looking for "ch" in the instructions has
        made them do a translation the document was supposed to do for them.
        """
        self.prose.append(f"{key} {value}")
        key_font = FONT_LABEL if upper else FONT_BODY_BOLD
        key_size = MIN_BODY_PT if upper else 10
        key_lines = _wrap(self.c, key.upper() if upper else key, key_font, key_size, 39 * mm)
        value_lines = _wrap(self.c, value, FONT_BODY, 10, PAGE_W - 2 * MARGIN - 44 * mm)
        line_height = 5.0 * mm
        rows = max(len(key_lines), len(value_lines))
        self.need(min(rows, 3) * line_height + 2 * mm)
        for i in range(rows):
            self.need(line_height)
            if i < len(key_lines):
                self.text(MARGIN, self.y, key_lines[i], key_font, key_size,
                          TAUPE if upper else FOREST)
            if i < len(value_lines):
                self.text(MARGIN + 44 * mm, self.y, value_lines[i], FONT_BODY, 10, INK)
            self.y -= line_height
        self.c.setStrokeColor(LINE)
        self.c.setLineWidth(0.4)
        self.c.line(MARGIN, self.y + 2.6 * mm, PAGE_W - MARGIN, self.y + 2.6 * mm)
        self.y -= 1.6 * mm

    def panel(self, x: float, top: float, w: float, h: float, *, fill=SURFACE,
              stroke=LINE, radius: float = 2.5 * mm) -> None:
        self.c.setFillColor(fill)
        self.c.setStrokeColor(stroke)
        self.c.setLineWidth(0.6)
        self.c.roundRect(x, top - h, w, h, radius, fill=1, stroke=1 if stroke else 0)

    def place(self, img, x: float, top: float, w: float, h: float, *,
              figure: dict | None = None) -> tuple[float, float]:
        """Fit `img` inside the box (x, top, w, h), centred; returns the drawn size."""
        from reportlab.lib.utils import ImageReader

        scale = min(w / img.width, h / img.height)
        dw, dh = img.width * scale, img.height * scale
        self.c.drawImage(ImageReader(img), x + (w - dw) / 2, top - (h - dh) / 2 - dh,
                         width=dw, height=dh, preserveAspectRatio=True, mask="auto")
        if figure is not None:
            self.figures.append(dict(figure, page=self.pages))
        return dw, dh

    def image(self, img, running_head: str | None = None, *, max_height=None,
              figure: dict | None = None, embed=None) -> None:
        """Place `img` fitted to the column. `embed`, if given, is the same drawing at a
        higher pixel count: it is what is embedded, at exactly the size `img` was laid out
        and measured at."""
        from reportlab.lib.utils import ImageReader

        usable_w = PAGE_W - 2 * MARGIN
        scale = min(1.0, usable_w / img.width)
        w, h = img.width * scale, img.height * scale
        height_limit = PAGE_H - 2 * MARGIN if max_height is None else max_height
        if h > height_limit:
            scale *= height_limit / h
            w, h = img.width * scale, img.height * scale
        self.need(h + 4 * mm, running_head)
        self.c.drawImage(ImageReader(embed if embed is not None else img),
                         MARGIN + (usable_w - w) / 2, self.y - h,
                         width=w, height=h, preserveAspectRatio=True, mask="auto")
        if figure is not None:
            self.figures.append(dict(figure, page=self.pages))
        self.y -= h + 5 * mm

    def finish(self) -> bytes:
        self._footer()
        self.c.save()
        return self.buf.getvalue()


def _wrap(c, text: str, font: str, size: float, width: float) -> list[str]:
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
                # A URL or identifier may be wider than a complete line. Keep
                # every character, splitting only for display rather than clipping.
                line = ""
                for char in word:
                    if line and c.stringWidth(line + char, font, size) > width:
                        out.append(line)
                        line = ""
                    line += char
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
    "How this pattern was made: this design was created with AI assistance, and every row's "
    "stitch count was checked before release. The charts in this document are drawn from the "
    "same pattern as the written instructions, so the two agree."
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

    return launch0.childrens_assignment(cir.slug) or graded_childrens_assignment(cir)


def graded_childrens_assignment(cir: CIR) -> tuple[str, str] | None:
    """F-362: a graded garment on the child/youth body table is a children's garment.

    The catalogue only assigned Launch-0 slugs, so a graded child cardigan rendered with no
    safety block at all. The CYC child/youth sizes are named by age in years, which gives
    the age band; sizes 14 and 16 are over 12 and outside CPSC's children's-product
    definition (`intel.childrens.OVER_TWELVE`), so they carry no children's block.
    """
    from ..cir.graded import CHILD

    g = cir.grading
    if g is None or g.table != CHILD.name:
        return None
    try:
        months = int(float(g.size)) * 12
    except ValueError:
        return None
    band = ch.age_band_for_months(months)
    if band == ch.OVER_TWELVE:
        return None
    return ("childrens_garment", band)


# ---- a graded garment's sizes, fit, care and package (F-761, F-762, F-763, F-362) ---------

SIZES_HEADING = "Sizes and fit"
CARE_HEADING = "Care"
AGE_IS_A_GUIDE = ("Sizes are named by age because that is how the size standard names them. "
                  "Age does not decide fit: measure the child's chest and choose the size "
                  "whose to-fit chest is closest.")


def size_chart(cir: CIR) -> list[tuple[str, str]] | None:
    """The size chart a graded release prints: body vs finished vs ease, every size.

    Read from `cir.grading`, the size matrix certification recomputed (F-768). The finished
    chest is the BUILT one -- measured from that size's rows at the stated gauge -- because
    that is what the maker will measure; the ease printed is built minus body.
    """
    g = cir.grading
    if g is None or not g.sizes:
        return None
    rows = []
    for e in g.sizes:
        body = (e.get("body_cm") or {}).get("bust")
        built = e.get("built_cm") or {}
        chest = built.get("chest", (e.get("intended_cm") or {}).get("bust"))
        bits = [f"to fit chest {body:g} cm", f"finished chest {chest:g} cm"]
        if body is not None and chest is not None:
            bits.append(f"{chest - body:+.0f} cm ease")
        if built.get("length") is not None:
            bits.append(f"length {built['length']:g} cm")
        if built.get("upper_arm") is not None:
            bits.append(f"upper arm {built['upper_arm']:g} cm")
        if e.get("yarn_m"):
            bits.append(f"yarn about {e['yarn_m']:.0f} m")
        if e["size"] == g.size:
            bits.insert(0, "this document")
        rows.append((f"size {e['size']}", "; ".join(bits)))
    return rows


def fit_statement(cir: CIR) -> str | None:
    """The intended fit and how ease is meant, said in words the listing is checked against."""
    g = cir.grading
    if g is None:
        return None
    from ..cir.graded import FIT_EASE_BANDS_CM

    head = (f"This document is size {g.size} of {len(g.sizes)}, graded from the "
            f"{g.table} body measurements ({g.source_url}, read {g.retrieved}). ")
    if g.fit:
        lo, hi = FIT_EASE_BANDS_CM[g.fit]
        head += (f"Intended fit: {g.fit}, which this studio means as {lo:g} to {hi:g} cm of "
                 f"ease at the chest. ")
    else:
        head += "No intended fit is stated for this design. "
    head += ("Body measurements are the wearer's; finished measurements are the garment's own, "
             "computed from this pattern's rows at the stated gauge; ease is the difference. "
             "Choose your size by your body measurement, not by the size you usually buy.")
    return head


def care_note(cir: CIR) -> str | None:
    """Care and use for a garment, from the fibre the pattern is written for (F-761)."""
    fibres, _why = fibres_named(cir)
    if not fibres:
        return None
    return (f"This pattern is written for {' and '.join(fibres)} yarn. Wash and dry the "
            f"finished garment as the ball band of the yarn you used says — it, not this "
            f"pattern, decides temperature and drying. Dry it flat and ease it to the "
            f"finished measurements above: a crochet garment dried on a hanger stretches in "
            f"length.")


SUPPORT_SCOPE_LEAD = "What support covers:"


def support_scope(cir: CIR) -> str:
    """F-770: which modifications are inside support and which are not, from the CIR.

    Support checks a report against the compiler that validated this release, so it can only
    vouch for what that release states: its size(s), its gauge and yarn weight, its stitch
    pattern and construction. Anything else is the maker's own design change.
    """
    g = cir.gauge
    sizes = (f"size {cir.grading.size} as written, or any of the {len(cir.grading.sizes)} "
             f"sizes in the size chart from its own document" if cir.grading is not None
             else "the size this pattern states")
    weight = (f"{g.yarn_weight} weight yarn" if g is not None and g.yarn_weight
              else "the yarn weight in Materials")
    return (f"{SUPPORT_SCOPE_LEAD} {sizes}, worked in {weight} at the stated gauge, with the stitches, colour order and construction as written. "
            f"Outside support: a different yarn weight or gauge, resizing to a size not "
            f"listed, changing the stitch pattern, the construction or the number of pieces, "
            f"and adding or removing shaping. We will explain how the pattern works, but we "
            f"cannot check numbers this release did not validate.")


def package_requirements(cir: CIR) -> tuple[str, ...]:
    """The sections a complete pattern package must carry for this CIR (F-761).

    Every pattern: materials, yarn amounts, gauge, abbreviations, instructions, terms and
    support. A graded garment also: its size chart with fit and ease, a construction
    overview, a schematic, and care notes.
    """
    need = ["At a glance", "Materials", "How much yarn", "Gauge, and why it matters here",
            "Abbreviations", "Instructions", "Terms and support"]
    if cir.grading is not None:
        need += [SIZES_HEADING, "How it goes together", "Schematic", CARE_HEADING]
    return tuple(need)


def package_missing(cir: CIR, prose: str | list[str]) -> tuple[str, ...]:
    """Required sections absent from what the document actually set (headings in prose)."""
    lines = prose.split("\n") if isinstance(prose, str) else list(prose)
    return tuple(h for h in package_requirements(cir)
                 if not any(line == h or line.startswith(h + " (") for line in lines))


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
    from ..cir.twin import size_statement

    fibres, read_from = fibres_named(cir)
    size = ((twin.width_cm, twin.height_cm)
            if twin.width_cm and twin.height_cm else None)
    return ch.StatementFacts(
        audience=audience,
        finished_size_cm=size,
        colours=tuple(sorted(c for c in (cir.colors or {}) if c)),
        fibres=fibres,
        fibre_read_from=read_from,
        size_text=(size_statement(twin) or "") if twin.shape is not None else "",
    )


def childrens_statements(cir: CIR, twin: TwinModel,
                         assignment: tuple[str, str]) -> ch.RenderedStatements:
    """Everything this children's pattern must say, rendered, or the reason it cannot be."""
    subcategory, audience = assignment
    return ch.render_statements(subcategory, audience,
                                childrens_facts(cir, twin, audience))


_SEAM_WORDS = {"whipstitch": "whipstitch", "slst": "slip-stitch", "mattress": "mattress-stitch",
               "sew": "sew", "pick_up": "work", "thread": "thread"}


def _piece(name: str) -> str:
    return name.replace("_", " ")


def construction_overview(cir: CIR) -> list[str] | None:
    """A short construction explanation for a multi-piece or held/resumed design (F-765).

    Built only from `cir.components` (what is made, how many, in what construction, which
    piece continues from which) and `cir.assembly` (every join, in order, by which method,
    along which edges). None for a single piece worked start to finish with no joins, which
    is exactly the case where an overview would only repeat the instructions.
    """
    comps = cir.components
    # Several copies of one piece with nothing joining them (a set of coasters) is not a
    # construction; several different pieces, or any join, is.
    multi = len(comps) > 1
    structural = any(c.holds or c.resumes for c in comps)
    if not (multi or structural or cir.assembly):
        return None
    total = sum(c.make for c in comps)
    lines: list[str] = []
    parts = []
    for c in comps:
        count = f"{c.make} x " if c.make > 1 else ""
        how = c.construction.replace("_", " ")
        if c.work_direction:
            from ..cir.topology import DIRECTION_WORDS
            how += f", {DIRECTION_WORDS[c.work_direction]}"
        extra = f", continued from the {_piece(c.resumes)}" if c.resumes else ""
        parts.append(f"{count}{_piece(c.name)} ({how}{extra})")
    lines.append(f"This is made as {total} piece{'s' if total != 1 else ''}, worked in the "
                 f"order below: " + "; ".join(parts) + ".")
    for c in comps:
        for h in c.holds:
            lines.append(f"The {_piece(c.name)} sets {h.count} stitches aside at row "
                         f"{h.at_row} ({_piece(h.name)}); they are picked up again later.")
    for i, seam in enumerate(cir.assembly, start=1):
        method = _SEAM_WORDS.get(seam.method, seam.method)
        a, b = _piece(seam.piece_a), _piece(seam.piece_b)
        if seam.names_its_edges:
            from ..cir.model import SEAM_CONNECTOR

            what = (f"{method} the {a}'s {seam.edge_a} edge "
                    f"{SEAM_CONNECTOR.get(seam.method, 'to')} "
                    + (f"its own {seam.edge_b} edge" if seam.is_self_seam
                       else f"the {b}'s {seam.edge_b}"
                       + ("" if seam.edge_b == "opening" else " edge")))
        elif seam.is_self_seam:
            what = f"{method} the {a} to itself"
        else:
            from ..cir.model import SEAM_CONNECTOR

            what = f"{method} the {a} {SEAM_CONNECTOR.get(seam.method, 'to')} the {b}"
        if seam.at_round is not None:
            target = next((c for c in cir.components if c.name == seam.piece_b), None)
            unit = ("row" if target is not None and "rows" in target.construction
                    and "round" not in target.construction else "round")
            what += f", at {unit} {seam.at_round} of the {b}"
        if seam.stuff_before_closing:
            what += ", stuffing before you close it"
        lines.append(f"Join {i}: {what}.")
    return lines


def build_pattern_pdf(cir: CIR, *, terminology: str = "US",
                      twin: TwinModel | None = None,
                      designer: str = "Brambleloop Studio",
                      released_on: date | None = None,
                      childrens: tuple[str, str] | None = None,
                      lesson_links: list[dict] | None = None,
                      sample_photo_placeholders: bool = False) -> PatternDocument:
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
    # The legend keyed in this document's own terminology (the chart art is shared by both).
    art = dict(art, legend=render_legend(
        cir, twin, terminology=terminology, marks=art.get("marks"),
        colours=art.get("charted_colours"), lettered=bool(art.get("cues"))))

    # Laid out until the count it prints is the count it has. Printing "of 7" on a document
    # that turned out to be 8 pages long is worse than printing nothing, because a customer
    # would then believe a complete file was truncated. Two passes settle every document in
    # the catalogue; the loop exists so that one that does not is caught here rather than
    # sold, and its guarantee is asserted rather than assumed.
    childrens = childrens if childrens is not None else childrens_assignment(cir)
    _refuse_an_undecided_childrens_title(cir, childrens)
    if childrens is not None:
        _refuse_what_the_childrens_assessment_refuses(cir, childrens)

    # The pictures of the finished piece and of its construction, drawn once (after every
    # refusal) by the deterministic renderers and placed by every layout pass.
    views = _disclosed_views(cir)
    from .construction_diagrams import stages as _stages
    stages = _stages(cir)

    total = 0
    for _ in range(4):
        doc, claims, problems = _render(cir, twin, result, text=text, art=art,
                                        terminology=terminology, designer=designer,
                                        released_on=released_on, total_pages=total,
                                        childrens=childrens, lesson_links=lesson_links,
                                        views=views, stages=stages,
                                        sample_photo_placeholders=sample_photo_placeholders)
        if doc.pages == total:
            break
        total = doc.pages
    else:  # pragma: no cover - no document in the catalogue oscillates
        raise ValueError(
            f"{cir.slug}: the page count does not settle, so the footer would state a "
            f"length the document does not have")

    missing = package_missing(cir, doc.prose)
    if childrens is not None and childrens[0] == "childrens_garment" \
            and SIZES_HEADING not in doc.prose:
        # The children's garment statement sends the reader to "the size chart in this
        # document" (F-362); a document without one cannot carry that sentence truthfully.
        missing = missing + (SIZES_HEADING,)
    if missing:
        raise ValueError(
            f"refusing to render {cir.slug}: the pattern package is incomplete, missing "
            f"{list(missing)} (F-761). A graded garment ships with its size chart, fit and "
            f"ease, construction overview, schematic and care notes, or not at all")
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
        figures=list(doc.figures),
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
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    hit = _EXTRACTED.get(sha)
    if hit is not None:
        return hit
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    text = " ".join("\n".join(page.extract_text() or "" for page in reader.pages).split())
    # Keyed by the bytes' digest (the text is a pure function of them): the same certified
    # PDF read by the children's statement audit, the teardown self-test and the
    # first-customer gate in one process is extracted once. Only the digest is kept.
    if len(_EXTRACTED) >= 32:
        _EXTRACTED.pop(next(iter(_EXTRACTED)), None)
    _EXTRACTED[sha] = text
    return text


_EXTRACTED: dict[str, str] = {}


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


def _refuse_what_the_childrens_assessment_refuses(cir: CIR,
                                                  assignment: tuple[str, str]) -> None:
    """F-363: the parts and ties the *pattern* names, assessed before anything is rendered.

    `intel.childrens.assess` could only see what a Concept declared, and nothing declared the
    safety eyes a materials list asked for. Here the Concept is read off the CIR, and any
    REFUSE finding (a detachable part under three, a neck or hood tie, an unassessed part, a
    prohibited subject) stops the document. Missing statements are not judged here: the
    rendered-statement audit after layout owns those.
    """
    from ..intel import childrens as ch

    subcategory, audience = assignment
    concept = ch.concept_from_cir(
        cir, subcategory=subcategory, audience=audience,
        stated_statements=ch.required_statements(subcategory, audience))
    refused = [f for f in ch.assess(concept) if f.severity == ch.REFUSE]
    # A wearable is also held to physical plausibility: seams, closures, openings,
    # proportion and trim, read off the CIR (F-363).
    if getattr(cir, "grading", None) is not None or subcategory == "childrens_garment":
        implausible = ch.physical_plausibility(cir)
        if implausible:
            raise ValueError(
                f"refusing to render {cir.slug}: a children's wearable the pattern would make "
                f"impractical -- " + "; ".join(f"{p['code']}: {p['detail']}"
                                               for p in implausible))
    if refused:
        raise ValueError(
            f"refusing to render {cir.slug}: it is a {subcategory} product for children "
            f"{audience}, and the pattern itself names what intel.childrens refuses -- "
            + "; ".join(f"{f.code}: {f.detail}" for f in refused))


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


# ---- the premium layout: facts, pictures and pieces of page furniture ---------------------
#
# Everything below decides *where* things go and what they look like. None of it decides what
# the pattern says: every number is read from the twin, the compiler or the writer's text, and
# every picture is drawn by the deterministic renderers (`visual.disclosed_render`,
# `publish.construction_diagrams`, `publish.charts`) or is the owner's canonical artwork.

_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
_SHAPE_ADJ = {3: "triangular", 4: "square", 5: "pentagonal", 6: "hexagonal", 8: "octagonal"}

# The sentence every picture of the finished piece carries, from the render contract the
# pictures themselves letter (`visual.render_contract.DISCLOSURE`).
IMAGE_DISCLOSURE = (
    "About the pictures: every image of the finished piece in this document is a digital "
    "rendering of the pattern's finished design, not a photograph. Each one is drawn stitch "
    "by stitch from this pattern's own data at the stated gauge, and the construction "
    "diagrams beside the instructions are drawn the same way.")


def physical_status(twin: TwinModel) -> str:
    """What this edition's numbers rest on, stated as a fact about the edition.

    Read from the twin's calibration, which is the only physical evidence a render can see:
    it says whether the measurements in *this file* were calibrated on a worked sample. It
    deliberately says nothing about whether a sample exists somewhere else -- a fixed "no
    sample has been made" sentence would become false the day one is, without this document
    changing.
    """
    if twin.calibrated:
        return ("Physical testing: the yarn amounts in this edition were calibrated against "
                "a physically worked sample.")
    return ("Physical testing: unverified in this edition. Its finished size and yarn amounts "
            "are computed from the gauge, not calibrated on a worked sample, and are marked as "
            "estimates wherever they appear. The stitch counts are checked by the pattern "
            "compiler and do not depend on a sample.")


def _rows_by_index(twin: TwinModel) -> dict[int, list]:
    rows: dict[int, list] = {}
    for c in twin.cells:
        rows.setdefault(c.row, []).append(c)
    return dict(sorted(rows.items()))


def _colour_runs(twin: TwinModel) -> list[tuple[str, int, int]]:
    runs: list[tuple[str, int, int]] = []
    for index, cells in _rows_by_index(twin).items():
        colour = cells[0].color
        if runs and runs[-1][0] == colour and runs[-1][2] == index - 1:
            runs[-1] = (colour, runs[-1][1], index)
        else:
            runs.append((colour, index, index))
    return runs


def _rings(twin: TwinModel):
    rings = list(getattr(getattr(twin, "geometry", None), "rings", []) or [])
    return [r for r in rings if r.rise_cm <= 0], [r for r in rings if r.rise_cm > 0]


class FoldDisclosureRefused(ValueError):
    """The soft-fold truth disclosure could not be composed, so the document is not built."""


def _fold(cir: CIR, twin: TwinModel) -> dict | None:
    """`value_stack.soft_fold`: a vessel whose base turns into its wall in a curve.

    L1 (SECREVIEW-PDF1): this fails **closed**. `soft_fold` already answers None for a piece
    with no wall; anything it raises means the height range, the "turning upward" wording and
    the idealised-render disclosure cannot be derived, and printing "rise straight up" and the
    exact twin height instead would be the untrue document. So the build is refused."""
    try:
        return value_stack.soft_fold(cir, twin)
    except Exception as exc:  # noqa: BLE001 - re-raised as a refusal, never swallowed
        raise FoldDisclosureRefused(
            f"{cir.slug}: the base-to-wall disclosure could not be composed "
            f"({type(exc).__name__}: {exc}); refusing to print a document without it") from exc


def _tall(cir: CIR, twin: TwinModel) -> str:
    """The height in words that do not overstate it (W4-CONSTRUCTREVIEW-basket F4).

    The twin's height assumes a sharp fold between base and wall. Where the pattern makes a
    soft one, that number is an upper bound, so the height is given as a range."""
    fold = _fold(cir, twin)
    if fold:
        return f"{value_stack.height_words(fold['low_cm'], fold['high_cm'])} tall"
    return f"{twin.height_cm:.1f} cm tall"


def _sized(cir: CIR, twin: TwinModel, statement: str | None) -> str | None:
    """`size_statement` with its height replaced by `_tall` where the fold is soft."""
    if not statement or not twin.height_cm or not _fold(cir, twin):
        return statement
    return statement.replace(f"{twin.height_cm:.1f} cm tall", _tall(cir, twin))


def _wall_rise_words(cir: CIR, twin: TwinModel, unit: str, lead: str) -> str:
    """How the wall leaves the base (F2): straight up only where the pattern makes a crease.

    `lead` is the verb phrase before it ("rise straight up from it" / "keep that count and"),
    so the sentence reads whole either way."""
    if _fold(cir, twin):
        return (f"{lead} make the wall, turning upward over the first few {unit}s and then "
                f"rising straight")
    return f"{lead} rise straight up to make the wall"


def _idealised(cir: CIR, twin: TwinModel) -> str | None:
    """What the renders draw that the pattern does not make (W4-CONSTRUCTREVIEW-basket F3).

    The renderer draws the twin's shape: a sharp fold from base to wall and corners running
    straight up it. Worked through both loops, the base turns up in a curve and the corners
    soften toward the rim. The geometry is not corrected in this edition (the renderer and
    its independent verifier are shared with the listing images), so each picture says so."""
    gap = _render_gap(cir, twin)
    return gap["long"] if gap else None


def _render_gap(cir: CIR, twin: TwinModel) -> dict | None:
    """The long and the short (cover) statement of what the renders idealise, or None.

    Soft fold (both-loops first wall round): the sharp base edge *and* the straight corners
    are idealised. Defined fold (back-loop first wall round, basket 1.3.0): the base edge is
    what the pattern makes, but no wall round has a stitch at the corner columns, so the
    corners running straight up the wall are still idealised -- the construction review
    (§1.3) expects the rim to relax toward a rounded hexagon. A flat piece, or a round vessel
    with no corners, has no gap."""
    fold = _fold(cir, twin)
    if fold:
        return {
            "long": (f"These pictures are idealised: they draw a sharp edge where the base "
                     f"meets the wall and corners running straight up it. Worked as written, "
                     f"the base turns up in a gentle curve over Rnds {fold['first_wall']} to "
                     f"{fold['settled']} and the corners soften toward the rim."),
            "short": (f"Worked as written, the base edge curves up over Rnds "
                      f"{fold['first_wall']} to {fold['settled']} and the corners are softer "
                      f"than drawn.")}
    base, wall = _rings(twin)
    from ..visual import render_contract as _K
    if base and wall and (twin.sides or 0) >= 3 and _K.rim_softening(cir) > 0:
        # The renders draw this wall as the pattern makes it -- the defined fold, corners
        # crisp at the base and softening to a rounded rim -- so there is no gap to caption.
        return None
    if base and wall and (twin.sides or 0) >= 3:
        return {
            "long": ("These pictures are idealised in one respect: they draw the corners "
                     "running straight up the wall. Worked as written, the base turns into "
                     "the wall at a defined edge, as drawn, but no wall round has a stitch "
                     "that keeps the corners, so they soften toward the rim."),
            "short": ("Worked as written, the base edge is defined as drawn; the wall's "
                      "corners soften toward the rim.")}
    return None


def _sides(cir: CIR, result) -> int | None:
    from ..cir.geometry import corners

    if len(cir.components) != 1:
        return None
    name = cir.components[0].name
    try:
        return corners([r for r in result.rows if r.component == name])
    except Exception:  # a flat piece has no corners to report
        return None


def _short_size(twin: TwinModel, cir: CIR | None = None) -> str:
    """The finished size in the fewest words that still name their convention (cover strip)."""
    if not twin.width_cm:
        return "see inside"
    if twin.sides and twin.across_points_cm:
        if twin.shape not in (None, "disc") and twin.height_cm:
            return (f"{twin.across_points_cm:.1f} cm across the points, "
                    f"{_tall(cir, twin) if cir is not None else f'{twin.height_cm:.1f} cm tall'}")
        return (f"{twin.across_points_cm:.1f} cm across the points, "
                f"{twin.across_flats_cm:.1f} cm across the flats")
    if twin.shape is not None:
        return (f"{twin.width_cm:.1f} cm across" + (f", {twin.height_cm:.1f} cm tall"
                if twin.shape != "disc" and twin.height_cm else ""))
    return f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm" if twin.height_cm else \
        f"{twin.width_cm:.0f} cm wide"


def _yarn_weight_label(cir: CIR) -> str:
    weights = sorted({m.yarn_weight for m in cir.materials if m.yarn_weight})
    named = ", ".join(w.upper() if len(w) <= 3 else w.capitalize() for w in weights)
    cyc = cir.gauge.yarn_weight if cir.gauge and cir.gauge.yarn_weight else ""
    if cyc and cyc.lower() not in {w.lower() for w in weights}:
        return f"{named} weight ({cyc.replace('_', ' ')})"
    return f"{named} weight" if named else "see Materials"


def _metres(m: float, tol: float) -> tuple[float, float]:
    return m * (1 - tol), m * (1 + tol)


def _span_words(first: int, last: int) -> str:
    return f"{first}" if first == last else f"{first} to {last}"


def overview_paragraphs(cir: CIR, result, twin: TwinModel, text: str,
                        terminology: str) -> list[str]:
    """What this pattern makes and how, in sentences built from the compiled pattern."""
    from ..cir.twin import size_statement

    comp = cir.components[0]
    make = sum(c.make for c in cir.components)
    piece = comp.name.replace("_", " ")
    sides = _sides(cir, result)
    shape = _SHAPE_ADJ.get(sides or 0, "")
    count = _NUMBER_WORDS.get(make, str(make))
    noun = piece + ("s" if make != 1 and not piece.endswith("s") else "")
    rows = _rows_by_index(twin)
    unit = "round" if "round" in comp.construction else "row"
    out = []
    first = (f"This pattern makes {count} {shape + ' ' if shape else ''}{noun}"
             if len(cir.components) == 1 else
             f"This pattern makes {cir.title.lower()}, from {make} pieces")
    size = _sized(cir, twin, size_statement(twin)) if twin.width_cm else None
    if size and shape:
        # "hexagonal coasters: hexagon, 9.7 cm ..." says the shape twice.
        size = re.sub(r"^[a-z]+(,| base)\s*", lambda m: "base " if "base" in m.group(0) else "",
                      size)
    if size:
        first += f", {'each ' if make > 1 else ''}{size} at the stated gauge"
        first += "." if not twin.calibrated else ", measured on a worked sample."
        if not twin.calibrated:
            first = first[:-1] + ", computed rather than measured."
    else:
        first += "."
    out.append(first)

    if len(cir.components) == 1 and rows:
        used = sorted(twin.stitch_types_used)
        base_codes = [c for c in used if c not in ("inc", "dec")]
        named = [abbreviations.meaning(c, terminology) for c in base_codes]
        names = (", ".join(named[:-1]) + " and " + named[-1]) if len(named) > 1 else \
            "".join(named)
        worked = {"joined_rounds": "joined rounds", "spiral_rounds": "spiral rounds",
                  "flat_rows": "rows"}.get(comp.construction,
                                           comp.construction.replace("_", " "))
        how = f"{'Each' if make > 1 else 'It'} is worked in {len(rows)} {worked} of {names}"
        if "magic ring" in text:
            how += ", starting from a magic ring"
        base, wall = _rings(twin)
        if base and wall:
            how += (f". {unit.capitalize()}s {_span_words(base[0].index, base[-1].index)} "
                    f"grow a flat base, and {unit}s "
                    f"{_span_words(wall[0].index, wall[-1].index)} "
                    + (_wall_rise_words(cir, twin, unit, "")[1:] if _fold(cir, twin) else
                       "rise straight up from it to make the wall"))
        elif sides:
            how += f", with the increases stacked so that they build {sides} corners"
        out.append(how + ".")

        runs = _colour_runs(twin)
        totals: dict[str, int] = {}
        for c in twin.cells:
            totals[c.color] = totals.get(c.color, 0) + 1
        if len(totals) > 1:
            main = max(sorted(totals), key=lambda k: totals[k])
            others = []
            for colour in sorted(k for k in totals if k != main):
                spans = [_span_words(a, b) for name, a, b in runs if name == colour]
                label = unit + ("s" if len(spans) > 1 or "to" in spans[0] else "")
                others.append(f"{colour} in {label} {' and '.join(spans)}")
            out.append(f"The main colour is {main}, with {'; '.join(others)}.")

    close = f"It is written in {terminology.upper()} crochet terms."
    if "sts)" in text:
        close += f" Every {unit} is written out with its stitch count,"
        close += " and the pattern includes construction diagrams, a chart, a schematic, and "
        close += "tips and troubleshooting."
    out.append(close)
    return out


# -- small vector icons for the project-details panel ----------------------------------------
#
# Drawn, not imported: a line icon in the brand's accent, the same weight everywhere. Each is
# an illustration of a category (a hook, a ball of yarn), never of this product.

def _icon(c, kind: str, cx: float, cy: float, r: float, *, level: int = 0,
          of: int = 3, fill=None) -> None:
    c.saveState()
    c.setFillColor(SURFACE)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.circle(cx, cy, r, fill=1, stroke=1)
    c.setStrokeColor(ACCENT)
    c.setFillColor(ACCENT)
    c.setLineWidth(0.9)
    c.setLineCap(1)
    s = r * 0.55
    if kind == "skill":
        for i in range(of):
            x = cx + (i - (of - 1) / 2) * s * 0.75
            c.circle(x, cy, s * 0.26, fill=1 if i < level else 0, stroke=1)
    elif kind == "size":
        c.rect(cx - s, cy - s * 0.32, 2 * s, s * 0.64, fill=0, stroke=1)
        for i in range(1, 6):
            x = cx - s + i * 2 * s / 6
            c.line(x, cy + s * 0.32, x, cy + s * (0.02 if i % 2 else -0.12))
    elif kind == "yarn":
        c.circle(cx, cy, s * 0.8, fill=0, stroke=1)
        for k in (-0.45, 0, 0.45):
            p = c.beginPath()
            p.moveTo(cx - s * 0.62, cy + k * s - s * 0.2)
            p.curveTo(cx - s * 0.2, cy + k * s + s * 0.25, cx + s * 0.2, cy + k * s + s * 0.25,
                      cx + s * 0.62, cy + k * s - s * 0.2)
            c.drawPath(p, fill=0, stroke=1)
    elif kind == "hook":
        c.line(cx - s * 0.7, cy - s * 0.8, cx + s * 0.45, cy + s * 0.55)
        p = c.beginPath()
        p.moveTo(cx + s * 0.45, cy + s * 0.55)
        p.curveTo(cx + s * 0.7, cy + s * 0.85, cx + s * 0.95, cy + s * 0.55, cx + s * 0.7,
                  cy + s * 0.4)
        c.drawPath(p, fill=0, stroke=1)
    elif kind == "gauge":
        c.rect(cx - s * 0.75, cy - s * 0.75, 1.5 * s, 1.5 * s, fill=0, stroke=1)
        for k in (-0.25, 0.25):
            c.line(cx - s * 0.75, cy + k * s, cx + s * 0.75, cy + k * s)
            c.line(cx + k * s, cy - s * 0.75, cx + k * s, cy + s * 0.75)
    elif kind == "rounds":
        for f in (0.85, 0.5):
            pts = [(cx + s * f * math.cos(math.pi / 3 * k), cy + s * f * math.sin(math.pi / 3 * k))
                   for k in range(7)]
            p = c.beginPath()
            p.moveTo(*pts[0])
            for pt in pts[1:]:
                p.lineTo(*pt)
            c.drawPath(p, fill=0, stroke=1)
        c.circle(cx, cy, s * 0.12, fill=1, stroke=0)
    elif kind == "time":
        c.circle(cx, cy, s * 0.8, fill=0, stroke=1)
        c.line(cx, cy, cx, cy + s * 0.55)
        c.line(cx, cy, cx + s * 0.38, cy - s * 0.1)
    elif kind == "colours":
        for i, col in enumerate(fill or []):
            x = cx + (i - (len(fill) - 1) / 2) * s * 0.7
            c.setFillColor(col)
            c.setStrokeColor(FOREST)
            c.setLineWidth(0.4)
            c.circle(x, cy, s * 0.36, fill=1, stroke=1)
    elif kind == "pieces":
        for k in (-0.3, 0.3):
            c.roundRect(cx - s * 0.55 + k * s, cy - s * 0.55 - k * s * 0.6, s * 0.9, s * 0.9,
                        s * 0.12, fill=0, stroke=1)
    elif kind == "needle":
        c.line(cx - s * 0.8, cy - s * 0.8, cx + s * 0.8, cy + s * 0.8)
        c.ellipse(cx + s * 0.45, cy + s * 0.35, cx + s * 0.75, cy + s * 0.75, fill=0, stroke=1)
    elif kind == "marker":
        p = c.beginPath()
        p.moveTo(cx - s * 0.2, cy - s * 0.8)
        p.lineTo(cx - s * 0.2, cy + s * 0.3)
        p.curveTo(cx - s * 0.2, cy + s * 0.9, cx + s * 0.6, cy + s * 0.9, cx + s * 0.6, cy + s * 0.3)
        p.lineTo(cx + s * 0.6, cy - s * 0.1)
        c.drawPath(p, fill=0, stroke=1)
    elif kind == "pins":
        for k in (-0.35, 0.35):
            c.line(cx + k * s, cy - s * 0.8, cx + k * s, cy + s * 0.4)
            c.circle(cx + k * s, cy + s * 0.55, s * 0.18, fill=1, stroke=0)
    elif kind == "info":
        c.circle(cx, cy + s * 0.45, s * 0.12, fill=1, stroke=0)
        c.line(cx, cy - s * 0.6, cx, cy + s * 0.15)
    c.restoreState()


def _yarn_ball(c, cx: float, cy: float, r: float, rgb) -> None:
    """A drawn ball of yarn in one of the pattern's colours (an illustration of the colour)."""
    c.saveState()
    c.setFillColor(rgb)
    c.setStrokeColor(FOREST)
    c.setLineWidth(0.7)
    c.circle(cx, cy, r, fill=1, stroke=1)
    shade = colors.Color(rgb.red * 0.72, rgb.green * 0.72, rgb.blue * 0.72)
    lum = bible.relative_luminance((rgb.red, rgb.green, rgb.blue))
    c.setStrokeColor(shade if lum > 0.2 else colors.Color(min(1, rgb.red * 1.6 + 0.15),
                                                          min(1, rgb.green * 1.6 + 0.12),
                                                          min(1, rgb.blue * 1.6 + 0.12)))
    c.setLineWidth(0.8)
    p = c.beginPath()
    p.circle(cx, cy, r)
    c.clipPath(p, stroke=0, fill=0)
    for k in range(-3, 4):
        q = c.beginPath()
        q.moveTo(cx - r, cy + k * r * 0.3 - r * 0.25)
        q.curveTo(cx - r * 0.3, cy + k * r * 0.3 + r * 0.35, cx + r * 0.3,
                  cy + k * r * 0.3 + r * 0.35, cx + r, cy + k * r * 0.3 - r * 0.25)
        c.drawPath(q, fill=0, stroke=1)
    c.restoreState()
    c.saveState()
    c.setStrokeColor(FOREST)
    c.setLineWidth(0.7)
    q = c.beginPath()
    q.moveTo(cx + r * 0.7, cy - r * 0.7)
    q.curveTo(cx + r * 1.1, cy - r * 1.05, cx + r * 1.3, cy - r * 0.8, cx + r * 1.5, cy - r * 1.0)
    c.drawPath(q, fill=0, stroke=1)
    c.restoreState()


def _rounded_image(doc: "_Doc", img, x: float, top: float, w: float, h: float, *,
                   figure: dict) -> tuple[float, float]:
    """An image fitted into a rounded frame, centred; returns the frame's drawn size."""
    from reportlab.lib.utils import ImageReader

    scale = min(w / img.width, h / img.height)
    dw, dh = img.width * scale, img.height * scale
    x0, y0 = x + (w - dw) / 2, top - (h - dh) / 2 - dh
    c = doc.c
    c.saveState()
    p = c.beginPath()
    p.roundRect(x0, y0, dw, dh, 3 * mm)
    c.clipPath(p, stroke=0, fill=0)
    c.drawImage(ImageReader(img), x0, y0, width=dw, height=dh, mask="auto")
    c.restoreState()
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.roundRect(x0, y0, dw, dh, 3 * mm, fill=0, stroke=1)
    doc.figures.append(dict(figure, page=doc.pages))
    return dw, dh


def _png_sha(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()


GALLERY_CELL = 70 * mm
LOGO_EMBED_PX = 1016    # 86 mm at 300 dpi
LOCKUP_EMBED_PX = 1323  # 112 mm at 300 dpi


@lru_cache(maxsize=1)
def _cover_lockup():
    """The tagline-free horizontal lockup, rasterised from its vector at 300 dpi."""
    from PIL import Image

    from ..brand.vector import rasterize, to_png_bytes

    d = identity_system.direction()
    mark = identity_system._mark(identity_system.DIRECTION_ID, "lockup_horizontal")
    png = to_png_bytes(rasterize(mark, d.colours("colour"), LOCKUP_EMBED_PX,
                                 ground=d.ground("colour")))
    img = Image.open(io.BytesIO(png))
    img.load()
    return img


@lru_cache(maxsize=1)
def _cover_logo():
    """The owner's canonical artwork, resampled to 300 dpi at the size the cover places it.

    D-FB-17 allows the hero artwork to be "resampled only to fit the space". Embedded at its
    native 1536 px it was 2.5 MB of a 3.7 MB coaster pattern; at the placed size it is the
    same picture at print resolution. Encoded as a high-quality baseline JPEG (deterministic in
    Pillow for identical input), so the PDF's bytes stay a pure function of the inputs.
    """
    from PIL import Image

    src = Image.open(identity_system.owner_logo_path()).convert("RGB")
    img = src.resize((LOGO_EMBED_PX, round(src.height * LOGO_EMBED_PX / src.width)),
                     Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, subsampling=0, optimize=False)
    out = Image.open(io.BytesIO(buf.getvalue()))
    out.load()
    return out


def _disclosed_views(cir: CIR) -> dict:
    """The disclosed renders this product has: view -> (PIL image, png sha256)."""
    from PIL import Image

    from ..visual import disclosed_render as D

    out = {}
    for view in ("hero", "angle", "detail", "scale"):
        try:
            frame = D.render(cir, view)
        except D.RenderRefused:
            continue
        img = Image.open(io.BytesIO(frame.png))
        img.load()
        out[view] = (img, hashlib.sha256(frame.png).hexdigest())
    return out


_STEP = re.compile(r"^(?P<label>(?:Rnds?|Rows?|Rounds?)\s+\d[^:]*:)\s*(?P<body>.*)$")
_COUNT = re.compile(r"(?P<count>\(\d+ sts?\))\s*$")
_STEP_NUMBER = re.compile(r"^(?:Rnds?|Rows?|Rounds?)\s+(\d+)")


def _rich_lines(c, segments: list[tuple[str, str, object]], width: float,
                size: float) -> list[list[tuple[str, str, object]]]:
    """Greedy wrap of styled segments into lines of (text, font, colour) runs."""
    words: list[tuple[str, str, object]] = []
    for text, font, color in segments:
        if _COUNT.fullmatch(text):
            # "(42 sts)" is one unit; split across two lines it reads as a stray "sts)".
            words.append((text, font, color))
            continue
        for w in text.split(" "):
            if w:
                words.append((w, font, color))
    lines: list[list[tuple[str, str, object]]] = [[]]
    used = 0.0
    space = stringWidth(" ", FONT_BODY, size)
    for w, font, color in words:
        ww = stringWidth(w, font, size)
        extra = ww + (space if lines[-1] else 0)
        if lines[-1] and used + extra > width:
            lines.append([])
            used = 0.0
            extra = ww
        lines[-1].append((w, font, color))
        used += extra
    return lines


def _draw_rich(doc: "_Doc", lines, x: float, y: float, size: float, leading: float) -> float:
    space = stringWidth(" ", FONT_BODY, size)
    for line in lines:
        cx = x
        # Runs of one style are drawn as one string so a text extractor reads them as words.
        runs: list[list] = []
        for w, font, color in line:
            if runs and runs[-1][1] == font and runs[-1][2] == color:
                runs[-1][0] += " " + w
            else:
                runs.append([w, font, color])
        for text, font, color in runs:
            cx += doc.text(cx, y, text, font, size, color) + space
        y -= leading
    return y


def _step_segments(line: str, colours: dict) -> tuple[list, object | None]:
    """A written instruction line split into label / body / count runs, unchanged in words."""
    m = _STEP.match(line)
    if not m:
        return [(line, FONT_BODY, INK)], None
    body = m.group("body")
    count = ""
    cm = _COUNT.search(body)
    if cm:
        count = cm.group("count")
        body = body[:cm.start()].rstrip()
    segs = [(m.group("label"), FONT_BODY_BOLD, FOREST)]
    if body:
        segs.append((body, FONT_BODY, INK))
    if count:
        segs.append((count, FONT_BODY_BOLD, ACCENT))
    colour = None
    cm2 = re.search(r"\(([^)]+)\):$", m.group("label"))
    if cm2 and cm2.group(1) in colours:
        colour = colours[cm2.group(1)]
    return segs, colour


def _parse_writer(text: str) -> dict:
    """The writer's text cut into its header, its component blocks and its finishing block.

    Cut, not changed: every line comes back exactly as the writer wrote it.
    """
    header: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.startswith("#") or (line.endswith(":") and not _STEP.match(line)
                                    and blocks is not None and line and len(line) < 60):
            blocks.append((line.lstrip("# ").strip().rstrip(":"), []))
            continue
        if not blocks:
            header.append(line)
        else:
            blocks[-1][1].append(line)
    return {"header": [h for h in header if h.strip()], "blocks": blocks}


def _render(cir: CIR, twin: TwinModel, result, *, text: str, art: dict,
            terminology: str, designer: str, released_on: date,
            total_pages: int,
            childrens: tuple[str, str] | None = None,
            lesson_links: list[dict] | None = None,
            views: dict | None = None, stages: list | None = None,
            sample_photo_placeholders: bool = False) -> tuple["_Doc", list[str], list[str]]:
    """Lay the document out. Called until the page count it prints is the count it has."""
    from ..cir.twin import size_statement
    from ..visual import render_contract as K
    from . import tips as tips_mod

    views = views or {}
    stages = stages or []
    year = released_on.year
    doc = _Doc(f"{cir.title} - {designer}", total_pages=total_pages, author=designer,
               proof_banner=("PROOF COPY WITH PHOTO PLACEHOLDERS · NOT FOR SALE"
                             if sample_photo_placeholders else ""),
               subject=f"Crochet pattern, {terminology.upper()} terms, version {cir.version}",
               footer_left=f"© {year} {COPYRIGHT_HOLDER} · all rights reserved · "
                           f"{cir.slug}@{cir.version}",
               header_right=f"{terminology.upper()} terms · version {cir.version}")
    head = f"Brambleloop · {cir.title}"
    problems: list[str] = []
    usable = PAGE_W - 2 * MARGIN
    comp = cir.components[0]
    make_total = sum(c.make for c in cir.components)
    piece = comp.name.replace("_", " ")
    letters = color_letters(cir)
    yarn_rgb = {name: colors.HexColor(value) for name, value in (cir.colors or {}).items()
                if value}
    difficulty_word = _difficulty(cir, twin)
    from .difficulty import LADDER

    # ---------------------------------------------------------------- 1. the cover --------
    doc.new_page()
    doc.reversed_footer_pages = {1}
    band_h = 40 * mm
    c = doc.c
    c.setFillColor(FOREST)
    c.rect(0, 0, PAGE_W, band_h, fill=1, stroke=0)
    from PIL import Image as _PIL

    # N1 (2026-10-31, integrator decision): a product PDF carries the tagline-free lockup --
    # micro-mark, wordmark and "CROCHET PATTERNS" -- from the brand's supporting vector system
    # (`brand.identity_system.lockup_horizontal`). The owner's hero raster carries the shop's
    # category line ("HOME · BABY · GIFTS · SEASONAL"), which on a kitchen product's cover
    # reads as a product claim. The owner artwork itself is untouched (D-FB-17); it is simply
    # not the asset this use takes.
    logo = _cover_lockup()
    logo_w = 112 * mm
    logo_h = logo_w * logo.height / logo.width
    doc.place(logo, (PAGE_W - logo_w) / 2, PAGE_H - 14 * mm, logo_w, logo_h,
              figure={"kind": "brand_artwork", "source": "brand.identity_system "
                      "lockup_horizontal (supporting vector lockup, tagline-free; N1)",
                      "label": "Brambleloop crochet patterns"})
    title_y = PAGE_H - 14 * mm - logo_h - 20 * mm
    title_size = 34
    while doc.width(cir.title, FONT_DISPLAY_BOLD, title_size) > usable and title_size > 20:
        title_size -= 1
    doc.prose.append(cir.title)
    doc.text(PAGE_W / 2, title_y, cir.title, FONT_DISPLAY_BOLD, title_size, FOREST,
             align="centre")
    kicker = f"Crochet pattern · {terminology} terms · version {cir.version}"
    doc.prose.append(kicker)
    # Set as written, not in capitals: the cover is where a reader (and
    # `visual.contents_frame`) looks for the words "version 1.2.0".
    doc.text(PAGE_W / 2, title_y - 8.5 * mm, kicker, FONT_UI_MEDIUM, 10.5, TAUPE,
             align="centre", track=0.5)
    if make_total > 1:
        # The CIR makes several pieces; the cover says how many (Component.make).
        makes = f"Makes {make_total} {piece}s"
        doc.prose.append(makes)
        doc.text(PAGE_W / 2, title_y - 15 * mm, makes, FONT_DISPLAY_ITALIC, 15, ACCENT,
                 align="centre")
        title_y -= 7 * mm
    cover_view = "angle" if "angle" in views else ("hero" if "hero" in views else None)
    caption_y = band_h + 7 * mm
    if cover_view:
        img, sha = views[cover_view]
        box_top = title_y - 15 * mm
        box_h = box_top - (caption_y + 6 * mm)
        _rounded_image(doc, img, MARGIN, box_top, usable, box_h,
                       figure={"kind": "disclosed_render", "view": cover_view,
                               "source": "visual.disclosed_render.render", "png_sha256": sha,
                               "label": K.DISCLOSURE})
        cap = ("Digital rendering of the finished design, drawn stitch by stitch from this "
               "pattern — not a photograph.")
        if _render_gap(cir, twin):
            # F3: two lines, the second saying what the picture idealises.
            cap = ("Idealised digital rendering, drawn stitch by stitch from this pattern — "
                   "not a photograph.")
            cap2 = _render_gap(cir, twin)["short"]
            doc.prose.append(cap)
            doc.prose.append(cap2)
            doc.text(PAGE_W / 2, caption_y + 2.2 * mm, cap, FONT_BODY_ITALIC, 9.5, MUTED,
                     align="centre")
            doc.text(PAGE_W / 2, caption_y - 2.2 * mm, cap2, FONT_BODY_ITALIC, 9.5, MUTED,
                     align="centre")
        else:
            doc.prose.append(cap)
            doc.text(PAGE_W / 2, caption_y, cap, FONT_BODY_ITALIC, 9.5, MUTED, align="centre")
    # The facts strip in the forest band.
    strip = [("Skill", difficulty_word.capitalize()),
             ("Finished size", _short_size(twin, cir)),
             ("Yarn", _yarn_weight_label(cir)),
             ("Hook", f"{cir.gauge.hook_mm:g} mm" if cir.gauge else "see Materials")]
    col_w = usable / len(strip)
    for i, (k, v) in enumerate(strip):
        x = MARGIN + i * col_w
        doc.prose.append(f"{k} {v}")
        doc.text(x, 29 * mm, k.upper(), FONT_UI_BOLD, MIN_BODY_PT, GOLD_ON_PINE, track=1.0)
        lines = _wrap(c, v, FONT_BODY, 10, col_w - 4 * mm)
        if len(lines) > 3:
            problems.append(f"PDF_TEXT_DOES_NOT_FIT: cover {k!r} needs {len(lines)} lines")
        for j, line in enumerate(lines):
            doc.text(x, 23.5 * mm - j * 4.6 * mm, line, FONT_BODY, 10, PAPER_ON_FOREST)
    claims: list[str] = []

    # ---------------------------------------------------------------- 2. overview ----------
    doc.new_page(head)
    doc.heading("Overview", kicker="About this pattern")
    for p in overview_paragraphs(cir, result, twin, text, terminology):
        doc.para(p, size=10.5)
    doc.space(3 * mm)

    # At a glance: the project-details panel.
    rows: list[tuple[str, str, str, dict]] = []
    if twin.width_cm and twin.height_cm:
        if twin.shape is not None and size_statement(twin):
            size = f"{_sized(cir, twin, size_statement(twin))} at the stated gauge"
        else:
            size = f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm at the stated gauge"
        if not twin.calibrated:
            size += " (computed, not yet measured on a worked sample)"
        claims.append(size)
        rows.append(("size", "finished size", size, {}))
    level = LADDER.index(difficulty_word) + 1 if difficulty_word in LADDER else len(LADDER)
    rows.insert(0, ("skill", "difficulty", difficulty_word,
                    {"level": level, "of": len(LADDER)}))
    if make_total > 1:
        rows.append(("pieces", "pieces", f"{make_total} {piece}s", {}))
    construction = cir.construction.replace("_", " ")
    if "magic ring" in text:
        construction += ", from a magic ring"
    rows.append(("rounds", "construction", construction, {}))
    fibres, _why = fibres_named(cir)
    yarn = _yarn_weight_label(cir)
    if fibres:
        yarn += f", {' and '.join(fibres)}"
    rows.append(("yarn", "yarn", yarn, {}))
    if twin.yarn_metres_by_color:
        total = sum(twin.yarn_metres_by_color.values())
        lo, hi = _metres(total, twin.yardage_tolerance)
        rows.append(("yarn", "yarn amount",
                     f"about {lo:.0f}-{hi:.0f} m in total ({lo * 1.094:.0f}-{hi * 1.094:.0f} yd), "
                     f"estimated", {}))
    if cir.gauge:
        rows.append(("hook", "hook", f"{cir.gauge.hook_mm:g} mm", {}))
        rows.append(("gauge", "gauge", f"{cir.gauge.stitches_per_10cm} sts x "
                     f"{cir.gauge.rows_per_10cm} rows = 10 cm in {_gauge_stitch(cir, terminology)}",
                     {}))
    rows.append(("colours", "colours", ", ".join(sorted(cir.colors)) or "one colour",
                 {"fill": [yarn_rgb[k] for k in sorted(yarn_rgb)]}))
    try:
        from ..products import launch0 as _l0

        hours = _l0.make_hours(cir.slug)
    except Exception:  # a product outside the Launch-0 catalogue has no estimate
        hours = None
    if hours:
        rows.append(("time", "making time",
                     f"about {hours:.1f} hours{' for the set' if make_total > 1 else ''} "
                     f"(estimated from the stitch count, not timed)", {}))
    rows.append(("info", "released", f"{released_on.isoformat()} · version {cir.version}", {}))

    doc.prose.append("At a glance")
    col_gap = 6 * mm
    col_w = (usable - col_gap) / 2
    val_w = col_w - 14 * mm
    heights = []
    for icon, key, value, _kw in rows:
        n = len(_wrap(c, value, FONT_BODY, 9.5, val_w))
        heights.append(max(11 * mm, 5 * mm + n * 4.4 * mm) + 1.5 * mm)
    half = (len(rows) + 1) // 2
    panel_h = 14 * mm + max(sum(heights[:half]), sum(heights[half:])) + 2 * mm
    doc.need(panel_h + 4 * mm)
    top = doc.y + 2 * mm
    doc.panel(MARGIN, top, usable, panel_h)
    doc.text(MARGIN + 5 * mm, top - 8 * mm, "AT A GLANCE", FONT_UI_BOLD, 9.5, ACCENT,
             track=1.2)
    for col in (0, 1):
        y = top - 15 * mm
        x = MARGIN + 5 * mm + col * (col_w + col_gap - 3 * mm)
        for (icon, key, value, kw), h in list(zip(rows, heights))[col * half:(col + 1) * half]:
            _icon(c, icon, x + 4.5 * mm, y - 2.5 * mm, 4.3 * mm, **kw)
            doc.prose.append(f"{key} {value}")
            doc.text(x + 11.5 * mm, y, key.upper(), FONT_UI_BOLD, MIN_BODY_PT, TAUPE, track=0.6)
            yy = y - 4.6 * mm
            for line in _wrap(c, value, FONT_BODY, 9.5, val_w):
                doc.text(x + 11.5 * mm, yy, line, FONT_BODY, 9.5, INK)
                yy -= 4.4 * mm
            y -= h
    doc.y = top - panel_h - 7 * mm

    # About this pattern: how it was made, what the pictures are, what has been tested.
    notes = [("How this pattern was made.", AI_DISCLOSURE.split(": ", 1)[1]),
             ("About the pictures.", IMAGE_DISCLOSURE.split(": ", 1)[1]
              + (" " + _idealised(cir, twin) if _idealised(cir, twin) else "")),
             ("Physical testing:", physical_status(twin).split(": ", 1)[1])]
    inner = usable - 10 * mm
    laid = []
    notes = [(k, t[:1].upper() + t[1:]) for k, t in notes]
    for k, t in notes:
        doc.prose.append(f"{k} {t}")
        laid.append(_rich_lines(c, [(k, FONT_BODY_BOLD, ACCENT), (t, FONT_BODY, INK)], inner,
                                9.5))
    leading = 13.0
    h = 9 * mm + sum(len(ls) * leading + 2 * mm for ls in laid)
    doc.need(h + 3 * mm)
    top = doc.y + 2 * mm
    doc.panel(MARGIN, top, usable, h, fill=PAPER, stroke=ROSE)
    y = top - 7 * mm
    for ls in laid:
        y = _draw_rich(doc, ls, MARGIN + 5 * mm, y, 9.5, leading) - 2 * mm
    doc.y = top - h - 4 * mm

    # -- sizes and fit (graded garments: F-761, F-762, F-763, F-362) -------
    size_rows = size_chart(cir)
    if size_rows:
        doc.new_page(head)
        doc.heading(SIZES_HEADING, kicker="Choosing your size")
        doc.para(fit_statement(cir) or "", size=10, running_head=head)
        from ..cir.graded import CHILD
        if cir.grading.table == CHILD.name:
            doc.para(AGE_IS_A_GUIDE, size=10, running_head=head)
        doc.space(2 * mm)
        for label, value in size_rows:
            doc.kv(label, value)
        note = care_note(cir)
        if note:
            doc.heading(CARE_HEADING, size=12)
            doc.para(note, size=10, running_head=head)

    # ---------------------------------------------------------------- 3. construction
    # Before the materials (as the schematic always was): what you are making, and its
    # measurements, before what to buy for it. ------
    from .schematic import schematic_for
    schematic = schematic_for(cir, result)
    overview = construction_overview(cir)
    scale_view = views.get("scale")
    if schematic is not None or scale_view is not None or overview:
        doc.new_page(head)
        doc.heading("How it is made", kicker="Construction and schematic")
        # F-765: how the pieces become the object, before any row-level instruction.
        if overview:
            doc.heading("How it goes together", size=12)
            for line in overview:
                doc.para(line, size=10, running_head=head)
            doc.space(2 * mm)
        else:
            base, wall = _rings(twin)
            rows_ix = _rows_by_index(twin)
            unit = "round" if "round" in comp.construction else "row"
            if base and wall:
                doc.para(f"The {piece} is one piece, worked in joined {unit}s without turning. "
                         f"{unit.capitalize()}s {_span_words(base[0].index, base[-1].index)} "
                         f"increase to grow a flat base of {len(rows_ix[base[-1].index])} "
                         f"stitches; {unit}s {_span_words(wall[0].index, wall[-1].index)} keep "
                         f"that count and "
                         f"{_wall_rise_words(cir, twin, unit, '')[1:]}. There are no "
                         f"seams to sew.", size=10)
            elif base:
                doc.para(f"Each {piece} is one piece, worked outward from the centre in joined "
                         f"{unit}s without turning, growing to {len(rows_ix[base[-1].index])} "
                         f"stitches at {('Rnd' if unit == 'round' else 'Row')} "
                         f"{base[-1].index}. There are no seams to sew.", size=10)
        if schematic is not None:
            doc.heading("Schematic", size=12)
            doc.para("Every piece as worked, to scale, with the joins that make it one object. "
                     "Measurements are computed from the stated gauge.", size=9.5, color=MUTED)
            doc.image(schematic.image, running_head=head,
                      figure={"kind": "schematic", "source": "publish.schematic.schematic_for",
                              "label": "Schematic"})
        elif scale_view is not None:
            img, sha = scale_view
            doc.prose.append("Schematic")
            doc.label("Schematic with finished measurements")
            base_view = views.get("detail") if _rings(twin)[1] else None
            box = (95 * mm if base_view is not None
                   else max(100 * mm, min(125 * mm, doc.y - MARGIN - 22 * mm)))
            doc.need(box + 12 * mm)
            top = doc.y
            _rounded_image(doc, img, MARGIN, top, box, box,
                           figure={"kind": "disclosed_render", "view": "scale",
                                   "source": "visual.disclosed_render.render", "png_sha256": sha,
                                   "label": "Schematic: " + K.DISCLOSURE})
            # The measurements in text beside the picture, from the twin.
            tx = MARGIN + box + 7 * mm
            tw = usable - box - 7 * mm
            facts = []
            if twin.across_points_cm:
                facts.append(("across the points", f"{twin.across_points_cm:.1f} cm"))
                facts.append(("across the flats", f"{twin.across_flats_cm:.1f} cm"))
            elif twin.width_cm:
                facts.append(("across" if twin.shape else "width", f"{twin.width_cm:.1f} cm"))
            if twin.shape not in (None, "disc") and twin.height_cm:
                facts.append(("height", _tall(cir, twin)[:-len(" tall")]))
            elif twin.shape is None and twin.height_cm:
                facts.append(("length", f"{twin.height_cm:.1f} cm"))
            rows_ix = _rows_by_index(twin)
            if rows_ix:
                facts.append(("stitches in the last round" if "round" in comp.construction
                              else "stitches in the last row",
                              f"{len(rows_ix[max(rows_ix)])}"))
                facts.append(("rounds" if "round" in comp.construction else "rows",
                              f"{len(rows_ix)}"))
            yy = top - 4 * mm
            doc.text(tx, yy, "FINISHED MEASUREMENTS", FONT_UI_BOLD, 9.5, ACCENT, track=1.0)
            doc.prose.append("Finished measurements")
            yy -= 8 * mm
            for k, v in facts:
                doc.prose.append(f"{k} {v}")
                doc.text(tx, yy, k.upper(), FONT_LABEL, MIN_BODY_PT, TAUPE)
                doc.text(tx, yy - 6 * mm, v, FONT_DISPLAY_BOLD, 18, FOREST)
                yy -= 14 * mm
            note = ("Computed from the pattern's stitches at the stated gauge; not measured on "
                    "a worked sample." if not twin.calibrated else
                    "Calibrated against a worked sample.")
            doc.prose.append(note)
            for line in _wrap(c, note, FONT_BODY_ITALIC, 9.5, tw):
                doc.text(tx, yy, line, FONT_BODY_ITALIC, 9.5, MUTED)
                yy -= 4.4 * mm
            doc.y = min(top - box - 4 * mm, yy - 2 * mm)
            cap = ("The schematic is a digital rendering drawn from the pattern's data, not a "
                   "photograph. The scale bar is in centimetres.")
            fold = _fold(cir, twin)
            if fold:
                # F4: the drawing letters the twin's height, which is an upper bound here.
                cap += (f" The {fold['high_cm']:.1f} cm height lettered on the drawing assumes "
                        f"a sharp fold at the base; the curve the base makes as it turns up "
                        f"takes some of it, so expect "
                        f"{value_stack.height_words(fold['low_cm'], fold['high_cm'])}. "
                        + _idealised(cir, twin))
            elif _idealised(cir, twin):
                cap += " " + _idealised(cir, twin)
            doc.para(cap, size=9.5, color=MUTED, font=FONT_BODY_ITALIC, keep=True)
            if base_view is not None:
                # A vessel's schematic needs its base as well as its wall: the elevation shows
                # the height, the plan the base the wall stands on.
                base, wall = _rings(twin)
                rows_ix = _rows_by_index(twin)
                bimg, bsha = base_view
                side = min(70 * mm, doc.y - MARGIN - 8 * mm)
                doc.need(side + 4 * mm)
                top = doc.y - 2 * mm
                _rounded_image(doc, bimg, MARGIN, top, side, side,
                               figure={"kind": "disclosed_render", "view": "detail",
                                       "source": "visual.disclosed_render.render",
                                       "png_sha256": bsha,
                                       "label": "Schematic, base: " + K.DISCLOSURE})
                bx = MARGIN + side + 7 * mm
                doc.prose.append("The base, from above")
                doc.text(bx, top - 4 * mm, "THE BASE, FROM ABOVE", FONT_UI_BOLD, 9.5, ACCENT,
                         track=1.0)
                lab = "Rnd" if "round" in comp.construction else "Row"
                lines_ = [f"{lab}s {base[0].index} to {base[-1].index}: a flat base of "
                          f"{len(rows_ix[base[-1].index])} stitches"
                          if len(base) > 1 else f"{lab} {base[0].index}",
                          f"{twin.across_points_cm:.1f} cm across the points and "
                          f"{twin.across_flats_cm:.1f} cm across the flats"
                          if twin.across_points_cm else "",
                          f"The wall ({lab}s {wall[0].index} to {wall[-1].index}) rises from "
                          f"its edge."]
                yy = top - 11 * mm
                for ln in [x for x in lines_ if x]:
                    doc.prose.append(ln)
                    for w in _wrap(c, ln, FONT_BODY, 10, usable - side - 7 * mm):
                        doc.text(bx, yy, w, FONT_BODY, 10, INK)
                        yy -= 5 * mm
                    yy -= 1.5 * mm
                doc.y = top - side - 4 * mm

    # ---------------------------------------------------------------- 4. materials ---------
    doc.new_page(head)
    doc.heading("Materials", kicker="What you need")
    # Yarn cards: one per yarn, with the colour drawn, the yarn named as the CIR names it, and
    # the amount per piece and in total from the twin's census.
    mats = list(cir.materials)
    per_row = 2 if len(mats) <= 4 else 3
    card_gap = 5 * mm
    card_w = (usable - card_gap * (per_row - 1)) / per_row
    card_h = 33 * mm
    tol = twin.yardage_tolerance
    for i, m in enumerate(mats):
        col = i % per_row
        if col == 0:
            doc.need(card_h + 4 * mm)
            row_top = doc.y + 2 * mm
        x = MARGIN + col * (card_w + card_gap)
        doc.panel(x, row_top, card_w, card_h)
        rgb = yarn_rgb.get(m.color_id or m.colorway or "", None)
        if rgb is not None:
            _yarn_ball(c, x + 12 * mm, row_top - card_h / 2, 7.5 * mm, rgb)
        tx = x + 26 * mm
        letter = letters.get(m.color_id) if m.color_id else None
        tag = f"Colour {letter}" if letter else "Yarn"
        described = f"{m.name} ({m.yarn_weight})"
        if m.colorway:
            # The colourway was in the CIR and in the written instructions, and the materials
            # list -- the page a buyer takes to the yarn shop -- once dropped it.
            described += f", colourway {m.colorway}"
        doc.prose.append(f"{m.color_id or m.name} {described}")
        doc.text(tx, row_top - 7 * mm, tag.upper(), FONT_UI_BOLD, MIN_BODY_PT, ACCENT, track=1.0)
        doc.text(tx, row_top - 12.5 * mm, (m.colorway or m.name).capitalize(), FONT_DISPLAY_BOLD,
                 15, FOREST)
        yy = row_top - 17.5 * mm
        card_lines = _wrap(c, described, FONT_BODY, 9.5, card_w - 29 * mm)
        for line in card_lines:
            doc.text(tx, yy, line, FONT_BODY, 9.5, INK)
            yy -= 4.3 * mm
        metres = twin.yarn_metres_by_color.get(m.color_id or "", None)
        if metres:
            lo, hi = _metres(metres, tol)
            amount = f"about {lo:.0f}-{hi:.0f} m ({lo * 1.094:.0f}-{hi * 1.094:.0f} yd)"
            if make_total > 1:
                amount += f" for all {make_total}"
            doc.prose.append(amount)
            for line in _wrap(c, amount, FONT_BODY_BOLD, 9.5, card_w - 29 * mm):
                doc.text(tx, yy, line, FONT_BODY_BOLD, 9.5, FOREST)
                yy -= 4.3 * mm
        if yy < row_top - card_h + 2 * mm:
            problems.append(f"PDF_TEXT_DOES_NOT_FIT: the yarn card for {m.color_id or m.name} "
                            f"overflows its panel")
        if col == per_row - 1 or i == len(mats) - 1:
            doc.y = row_top - card_h - 6 * mm

    doc.heading("Hook and notions", size=12)
    notions: list[tuple[str, str, str]] = []
    if cir.gauge and cir.gauge.hook_mm:
        notions.append(("hook", "hook", f"{cir.gauge.hook_mm:g} mm, or whatever hook gets you "
                                        f"the gauge below"))
    # The special-stitch methods are part of what this document asks the maker to do, so the
    # tools they require belong on the shopping list too.
    instructed = "\n".join([text] + [abbreviations.method(code, terminology)
                                     for code in sorted(twin.stitch_types_used)])
    icon_for = {"tapestry needle": "needle", "blocking pins and a surface": "pins",
                "stitch marker": "marker"}
    for name, what in _tools_required(cir, instructed):
        notions.append((icon_for.get(name, "info"), name, what))
    if "sts)" in text and not any(n[1] == "stitch marker" for n in notions):
        # The tips page asks for a marker in the first stitch of every round.
        notions.append(("marker", "stitch marker", "optional, to mark the first stitch of each "
                                                   "round"))
    for icon, name, what in notions:
        doc.need(11.5 * mm)
        _icon(c, icon, MARGIN + 4 * mm, doc.y + 0.2 * mm, 3.8 * mm)
        doc.prose.append(f"{name} {what}")
        doc.text(MARGIN + 11 * mm, doc.y + 2.2 * mm, name.upper(), FONT_LABEL, MIN_BODY_PT,
                 TAUPE)
        doc.text(MARGIN + 11 * mm, doc.y - 2.6 * mm, what, FONT_BODY, 9.5, INK)
        doc.y -= 11.5 * mm

    doc.space(1 * mm)
    doc.heading("How much yarn", size=12)
    if twin.yarn_metres_by_color:
        for name, metres in sorted(twin.yarn_metres_by_color.items()):
            low, high = _metres(metres, tol)
            value = f"about {low:.0f}-{high:.0f} m ({low * 1.094:.0f}-{high * 1.094:.0f} yd)"
            if make_total > 1:
                plo, phi = low / make_total, high / make_total
                value += (f" for all {make_total} {piece}s; about {plo:.1f}-{phi:.1f} m "
                          f"for each one")
            doc.kv(name, value)
    tolerance_note = (
        f"These quantities are estimates with a ±{tol * 100:.0f}% range, not measurements. "
        "Yarn consumption genuinely varies with yarn, hook and tension, so buy a little more "
        "than the top of the range if your dye lot matters to you."
        if not twin.calibrated else
        "These quantities were calibrated against a physically worked sample.")
    doc.para(tolerance_note, size=9.5, color=MUTED)

    # -- substituting the yarn (#7) ----------------------------------------
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
            f"this fabric: {names}. Swatch and change hook until your gauge matches — the "
            f"gauge is what makes the finished size come out.", size=10)
        printed_rows = 0
        for row in guide["how_much"]:
            if not row.get("measurable"):
                continue
            lo_b, hi_b = row["balls_100g"]
            # N3: a range that collapses is one number ("1 x 100g ball", not "1-1 ... balls").
            balls = (f"{lo_b} x 100g ball{'s' if lo_b != 1 else ''}" if lo_b == hi_b
                     else f"{lo_b}-{hi_b} x 100g balls")
            doc.kv(f"if you use {row['to'].replace('_', ' ')}",
                   f"about {row['buy_metres']:.0f} m in total ({balls}); "
                   f"{row['fabric_changes']}")
            printed_rows += 1
        if guide["declared_weight"] and not guide["substitutes"]["declared_holds_gauge"]:
            # F-112: a statement of fact about a released pattern, not a compensation.
            doc.para(
                f"Note: the gauge above sits outside the published band for "
                f"{guide['declared_weight'].replace('_', ' ')} yarn. It is this pattern's "
                f"tested gauge rather than the band's; match it with your own swatch.",
                size=9.5, color=MUTED)
        # F1: the margin sentence describes the substitution metres, so it appears only
        # under one; with none printed it would read as a margin on the Materials figures.
        margin = (f"Those metres are this pattern's own estimate plus "
                  f"{substitution.BUY_MARGIN:.0%}. Buying exactly enough is how a project ends "
                  f"one row short in a dye lot that has gone. " if printed_rows else "")
        doc.para(
            f"{margin}Changing fibre as well — cotton for acrylic, say — changes how much "
            f"yarn each stitch takes by an amount that has to be measured on a swatch, not "
            f"read off a table.", size=9.5, color=MUTED)

    # ---------------------------------------------------------------- 5. gauge -------------
    if doc.y < 150 * mm:
        doc.new_page(head)
    else:
        doc.space(6 * mm)
    doc.heading("Gauge, and why it matters here", kicker="Before you start")
    doc.para(
        "Work a swatch before you start. The finished size above is computed from the gauge "
        "above; if your gauge differs, your finished piece will differ by the same "
        "proportion. The stitch counts in this pattern are correct at any gauge — only the "
        "measurements change.", size=10)
    if cir.gauge:
        stitch = _gauge_stitch(cir, terminology)
        g = cir.gauge
        steps = [
            f"With the {g.hook_mm:g} mm hook and the yarn you will use, work a square of {stitch} "
            f"a little over 12 cm wide and 12 cm tall.",
            f"Lay it flat without stretching it. Across 10 cm in the middle you are aiming for "
            f"{g.stitches_per_10cm:g} stitches, and up 10 cm for {g.rows_per_10cm:g} rows.",
            "More stitches than that means your stitches are smaller than the pattern's: change "
            "to a larger hook. Fewer stitches means they are larger: change to a smaller hook. "
            "Swatch again until it matches.",
        ]
        try:
            ms = value_stack.milestones(cir, twin)
        except value_stack.ValueStackRefused:
            ms = None
        if ms and len(ms["milestones"]) > 1 and ms["unit"] == "round":
            mark = ms["milestones"][1]
            steps.append(f"On a piece worked in the round you can also check as you go: after "
                         f"round {mark['row']} it should be {mark['measured']}.")
        doc.label("How to check your gauge")
        for n, s in enumerate(steps, 1):
            doc.need(10 * mm)
            doc.c.setFillColor(ACCENT)
            doc.c.circle(MARGIN + 2.6 * mm, doc.y + 1.2 * mm, 2.6 * mm, fill=1, stroke=0)
            doc.text(MARGIN + 2.6 * mm, doc.y - 0.1 * mm, str(n), FONT_UI_BOLD, MIN_BODY_PT,
                     colors.white, align="centre")
            doc.para(s, size=10, x=MARGIN + 8 * mm)

    # -- the row gauge the fabric actually has -----------------------------
    #
    # The width is the stitch gauge multiplied by the stitch count; the length is accumulated
    # row by row using each row's own stitch height, so a pattern whose gauge is stated in sc
    # and whose fabric is mostly dc is *twice* as long as the stated row gauge implies. The
    # document prints the number that reconciles them (Cloudline, 2026-09).
    fabric = _fabric_row_gauge(twin)
    taller = _taller_than_gauge(cir, twin)
    if fabric and cir.gauge and taller:
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
                f"fabric's own.", size=9.5, color=MUTED)
    else:
        round_note = _round_gauge_note(cir, twin, terminology)
        if round_note:
            doc.space(1 * mm)
            doc.para(round_note, size=9.5, color=MUTED)

    # -- how to know it is going right (#7) --------------------------------
    try:
        progress = value_stack.milestones(cir, twin)
    except value_stack.ValueStackRefused:
        progress = None
    if progress and len(progress["milestones"]) > 2:
        unit = progress["unit"]
        doc.heading("Checking your progress", size=12)
        fold = _fold(cir, twin)
        if fold:
            # F2: the first wall rounds are still turning; their height is the fold, not gauge.
            doc.para(
                f"At these {unit}s the piece should measure roughly this much. If the width "
                f"across the points does not match, the difference is gauge, and it is easier "
                f"to fix now than at {unit} {progress['rows_total']}. The height of the first "
                f"few wall {unit}s depends on how the edge of the base turns up, not on gauge, "
                f"so judge the height from {unit} {fold['settled']} on.", size=10)
        else:
            doc.para(
                f"At these {unit}s the piece should measure roughly this much. If it does not, "
                f"the difference is gauge, and it is easier to fix now than at {unit} "
                f"{progress['rows_total']}.", size=10)
        for mark in progress["milestones"]:
            doc.kv(f"{mark['unit']} {mark['row']} of {progress['rows_total']}",
                   mark["measured"])

    # -- printing it (#7) ---------------------------------------------------
    printing = value_stack.print_safety(cir)
    if printing.get("measurable") and printing.get("prints") is False:
        merging = printing.get("merging_pairs", [])
        pairs = " and ".join(" / ".join(p["between"]) for p in merging) or "two of these"
        doc.para(
            f"Printing in black and white: {pairs} are close in lightness and "
            f"will merge on a greyscale printer. The chart carries a letter for each colour, "
            f"so follow the letters rather than the shading.", size=9.5, color=MUTED)

    # ---------------------------------------------------------------- 6. abbreviations -----
    doc.new_page(head)
    doc.heading("Abbreviations", kicker=f"{terminology.upper()} crochet terms")
    doc.para(f"This pattern is written in {terminology.upper()} terms. Every abbreviation it "
             f"uses is below; nothing in the instructions is left to be looked up "
             f"elsewhere.", size=10)
    doc.space(1 * mm)
    key = abbreviations.stitch_key(text, terminology)
    for entry in key:
        doc.kv(entry.token, entry.means, upper=False)

    notation = abbreviations.notation_key(text)
    if notation:
        doc.heading("How to read a row", size=12)
        for entry in notation:
            doc.kv(entry.token, entry.means, upper=False)

    methods = [e for e in key if e.method]
    if methods:
        doc.heading("Special stitches", size=12)
        doc.para("These are the stitches in this pattern that are not simply worked into the "
                 "top of the stitch below. Work one of each before you start the piece.",
                 size=10)
        for entry in methods:
            doc.space(1 * mm)
            doc.kv(entry.token, entry.means, upper=False)
            doc.para(entry.method, size=9.5, color=MUTED)
    cables = abbreviations.CABLE_CODES & set(twin.stitch_types_used)
    if cables:
        doc.para(abbreviations.CABLE_DIRECTION_NOTE, size=9.5, color=MUTED)
        # The canonical `Stitch` record has no field for which side the held stitches wait
        # on; naming a side would print a fact the compiler never verified.
        problems.append(
            f"PDF_CABLE_DIRECTION_UNSPECIFIED: {sorted(cables)} cross four stitches over "
            f"each other and the CIR records no crossing direction, so the document cannot "
            f"tell a maker whether the held stitches wait at the front or the back. The "
            f"piece is makeable and its cables may mirror the product photography. Needs a "
            f"field on cir.stitches.Stitch before the document can state it")
    techniques = abbreviations.techniques(text, terminology)
    if techniques:
        doc.heading("Techniques used", size=12)
        for entry in techniques:
            doc.need(14 * mm)
            doc.prose.append(entry.token)
            doc.text(MARGIN, doc.y, entry.token.capitalize(), FONT_BODY_BOLD, 10, FOREST)
            doc.y -= 4.8 * mm
            doc.para(entry.means, size=9.5, color=INK)
            doc.space(1 * mm)

    # ---------------------------------------------------------------- 7. instructions ------
    doc.new_page(head)
    doc.heading(f"Instructions ({terminology} terms)", kicker="Step by step")
    parsed = _parse_writer(text)
    # The writer's own header (title, version, gauge, materials, terminology) as a strip.
    hdr = [h for h in parsed["header"]]
    if hdr:
        # The writer's own header lines, set in full (never cut to fit): the short ones
        # (version, terminology) share a row, the long ones (gauge, materials) get a row each.
        h_lines = [h for h in hdr if h != cir.title]
        short = [h for h in h_lines if len(h) <= 28]
        long_ = [h for h in h_lines if len(h) > 28]
        rows_: list[list[list[str]]] = []
        if short:
            rows_.append([[h] for h in short[:2]])
            for h in short[2:]:
                rows_.append([[h]])
        for h in long_:
            rows_.append([_wrap(c, h, FONT_BODY, 9.5, usable - 8 * mm)])
        hh = 5 * mm + sum(max(len(cell) for cell in row) for row in rows_) * 4.8 * mm
        doc.need(hh + 4 * mm)
        top = doc.y + 2 * mm
        doc.panel(MARGIN, top, usable, hh, fill=SURFACE)
        if cir.title in hdr:
            doc.prose.append(cir.title)
        yy = top - 5.8 * mm
        for row in rows_:
            for col_i, cell in enumerate(row):
                doc.prose.append(" ".join(cell))
                y2 = yy
                for line in cell:
                    doc.text(MARGIN + 4 * mm + col_i * usable / 2, y2, line, FONT_BODY, 9.5,
                             INK)
                    y2 -= 4.8 * mm
            yy -= max(len(cell) for cell in row) * 4.8 * mm
        doc.y = top - hh - 6 * mm
    if stages:
        doc.para("Each card shows the piece after its last round: a construction diagram drawn "
                 "from this pattern's stitch data, not a photograph. The rose outline is the "
                 "round just worked; early rounds are shown enlarged.", size=9.5, color=MUTED,
                 font=FONT_BODY_ITALIC)
        doc.space(1 * mm)
    stage_for = {}
    for st in stages:
        for k in range(st.first, st.round + 1):
            stage_for[k] = st
    finishing: list[str] = []
    for title, lines in parsed["blocks"]:
        if title.lower().startswith("finishing"):
            finishing = lines
            continue
        shown = title[:1].upper() + title[1:]
        doc.heading(shown, size=12)
        steps = [ln for ln in lines if _STEP.match(ln)]
        notes_ = [ln for ln in lines if ln.strip() and not _STEP.match(ln)]
        for ln in notes_:
            doc.need(10 * mm)
            doc.para(ln, size=10, color=FOREST, font=FONT_BODY_ITALIC)
        groups: list[tuple[object, list[str]]] = []
        for ln in steps:
            m = _STEP_NUMBER.match(ln)
            st = stage_for.get(int(m.group(1))) if m else None
            if groups and groups[-1][0] is st:
                groups[-1][1].append(ln)
            else:
                groups.append((st, [ln]))
        if stages and all(g[0] is not None for g in groups):
            _step_cards(doc, groups, yarn_rgb, comp, head)
        else:
            for _st, group in groups:
                for ln in group:
                    _step_line(doc, ln, yarn_rgb, MARGIN, usable, head)
        doc.space(3 * mm)

    if finishing:
        doc.need(60 * mm)
        doc.heading("Finishing", kicker="Assembly and finishing")
        for ln in finishing:
            if not ln.strip():
                continue
            doc.need(9 * mm)
            doc.c.setFillColor(ROSE)
            doc.c.circle(MARGIN + 1.6 * mm, doc.y + 1.2 * mm, 1.1 * mm, fill=1, stroke=0)
            doc.para(ln, size=10, x=MARGIN + 6 * mm, running_head=head)

    # ---------------------------------------------------------------- 8. tips --------------
    tip_list = tips_mod.tips(cir, result, twin, text, terminology)
    if tip_list:
        if doc.y < 150 * mm:
            doc.new_page(head)
        else:
            doc.space(8 * mm)
        doc.heading("Tips and troubleshooting", kicker="If something looks wrong")
        gap = 6 * mm
        cw = (usable - gap) / 2
        inner = cw - 9 * mm
        for i in range(0, len(tip_list), 2):
            pair = tip_list[i:i + 2]
            hs = [9 * mm + doc.para_height(t.text, 9.5, width=inner) + 5 * mm for t in pair]
            h = max(hs)
            doc.need(h + 4 * mm)
            top = doc.y + 2 * mm
            for j, t in enumerate(pair):
                x = MARGIN + j * (cw + gap)
                doc.panel(x, top, cw, h)
                c.setFillColor(ROSE)
                c.rect(x, top - h + 2.5 * mm, 1.4 * mm, h - 5 * mm, fill=1, stroke=0)
                doc.prose.append(t.title)
                doc.text(x + 5 * mm, top - 7 * mm, t.title, FONT_DISPLAY_BOLD, 14, FOREST)
                doc.y = top - 12.5 * mm
                doc.para(t.text, size=9.5, x=x + 5 * mm, width=inner)
            doc.y = top - h - 5 * mm

    # ---------------------------------------------------------------- 9. chart -------------
    doc.new_page(head)
    doc.heading("Chart", kicker="Chart and keys")
    # The caption goes above the chart when both fit; otherwise below it, because the chart
    # is placed at the size its legibility floor was measured at and cannot shrink to make room.
    full_scale = min(1.0, (PAGE_W - 2 * MARGIN) / art["chart"].width)
    caption_first = art.get("tiles") or (
        doc.y - MARGIN >= art["chart"].height * full_scale + 4 * mm
        + doc.para_height(art["caption"], 9.5) + 2 * mm)
    if caption_first:
        doc.para(art["caption"], size=9.5, color=MUTED, keep=True)
        doc.space(1 * mm)
    chart_fig = {"kind": "chart", "source": "publish.charts (twin cell grid)", "label": "Chart"}
    if art.get("tiles"):
        doc.heading("Tile placement index", size=12)
        for start in dict.fromkeys(t["row_start"] for t in art["tiles"]):
            band = [(n, t) for n, t in enumerate(art["tiles"], 1) if t["row_start"] == start]
            doc.para(f"Rows {start}-{band[0][1]['row_end']}: " + "; ".join(
                f"tile {n}, columns {t['column_start']}-{t['column_end']}" for n, t in band),
                size=9.5)
        for number, tile in enumerate(art["tiles"], 1):
            doc.new_page(head)
            doc.heading("Chart continued")
            doc.para(f"Tile {number} of {len(art['tiles'])}: rows {tile['row_start']}-"
                     f"{tile['row_end']}, columns {tile['column_start']}-{tile['column_end']} "
                     f"(left to right).", size=9.5)
            doc.image(tile["chart"], running_head=head, max_height=CHART_TILE_HEIGHT,
                      figure=dict(chart_fig, label=f"Chart tile {number}"))
        doc.new_page(head)
        doc.heading("Chart key")
    else:
        doc.image(art["chart"], running_head=head, figure=chart_fig,
                  max_height=_chart_height_with_legend(doc, art, round_=is_round(cir, twin)),
                  embed=art.get("chart_hi"))
    if not caption_first:
        doc.para(art["caption"], size=9.5, color=MUTED, keep=True)
        doc.space(1 * mm)
    doc.image(art["legend"], running_head=head, max_height=70 * mm,
              figure={"kind": "chart_legend", "source": "publish.charts.render_legend",
                      "label": "Chart legend"})
    problems.extend(art.get("problems", ()))
    # The chart's symbols, in text, because the chart cannot be read without them: the legend
    # is a picture, invisible to a screen reader and to a search, and the Abbreviations page
    # defines abbreviations, not marks.
    symbols = _chart_symbols(cir, twin, terminology)
    if symbols:
        doc.heading("Chart symbols", size=12)
        doc.para(_CHART_SYMBOL_NOTE_ROUND if is_round(cir, twin) else _CHART_SYMBOL_NOTE_FLAT,
                 size=9.5, color=MUTED)
        for symbol, means in symbols:
            doc.kv(symbol, means, upper=False)
        doc.para("The same key is drawn in the image above, and every stitch in it is also "
                 "defined under Abbreviations, earlier in this document.", size=9.5,
                 color=MUTED)

    # The colour key, in text, printed only when the chart that was rendered carries letters
    # (`charts.color_letters` is the one source of the mapping).
    cues = art.get("cues") or {}
    colours = [name for name in cir.colors if name]
    if cues:
        doc.heading("Colour key", size=12)
        doc.para(COLOUR_CUE_NOTE_ROUND if is_round(cir, twin) else COLOUR_CUE_NOTE_FLAT,
                 size=9.5, color=MUTED)
        for name, cue in sorted(cues.items(), key=lambda kv: kv[1]):
            doc.kv(cue, f"{name}  {cir.colors.get(name, '')}".strip(), upper=False)
    elif len(colours) > 1:
        doc.heading("Colours", size=12)
        doc.para("Every round this chart shows is worked in one colour, so no number on it "
                 "carries a colour letter. The written instructions name the yarn for every "
                 "row and round in the pattern.", size=9.5, color=MUTED)
        for name in colours:
            doc.kv(name, cir.colors.get(name, ""), upper=False)

    # ---------------------------------------------------------------- 10. gallery ----------
    gallery = [(v, views[v]) for v in ("hero", "angle", "detail") if v in views]
    if gallery or sample_photo_placeholders:
        doc.new_page(head)
        doc.heading("Gallery", kicker="The finished design")
        doc.para(IMAGE_DISCLOSURE, size=9.5, color=MUTED)
        if _idealised(cir, twin):
            doc.para(_idealised(cir, twin), size=9.5, color=MUTED)
        if not sample_photo_placeholders:
            doc.para("This edition contains no photographs: every picture in it is a rendering "
                     "or a diagram drawn from the pattern.", size=9.5, color=MUTED)
        doc.space(1 * mm)
        captions = {"hero": "The finished design, front view",
                    "angle": "Seen from above, showing the inside and the base",
                    "detail": "Close view: every stitch of the " +
                              ("base" if _rings(twin)[1] else piece)}
        if comp.make > 1:
            captions["hero"] = f"The set of {comp.make}, as the pattern makes them"
        big, rest = (gallery[0], gallery[1:]) if gallery else (None, [])
        pair = len(gallery) == 2 and not sample_photo_placeholders
        if pair:
            # Two pictures read better side by side, at equal size, than one small under one
            # large.
            big, rest = None, gallery
        if big:
            v, (img, sha) = big
            rest_w = min((usable - 5 * mm) / 2, GALLERY_CELL)
            rest_h = (rest_w + 26 * mm) if (rest or sample_photo_placeholders) else 0
            side = min(usable, doc.y - MARGIN - 14 * mm - rest_h)
            doc.need(side + 10 * mm)
            top = doc.y
            dw, dh = _rounded_image(doc, img, MARGIN, top, usable, side,
                                    figure={"kind": "disclosed_render", "view": v,
                                            "source": "visual.disclosed_render.render",
                                            "png_sha256": sha, "label": K.DISCLOSURE})
            doc.y = top - side - 5 * mm
            doc.para(captions[v] + ". Digital rendering, not a photograph.", size=9.5,
                     color=MUTED, font=FONT_BODY_ITALIC)
        if rest or sample_photo_placeholders:
            cells = [("view", v, data) for v, data in rest]
            if sample_photo_placeholders:
                cells += [("placeholder", "sample", None)] * max(1, 2 - len(cells))
            per = 2
            cw = (usable - 5 * mm) / per if pair else min((usable - 5 * mm) / per, GALLERY_CELL)
            for i in range(0, len(cells), per):
                doc.need(cw + 14 * mm)
                top = doc.y
                row = cells[i:i + per]
                x0 = MARGIN + (usable - (len(row) * cw + (len(row) - 1) * 5 * mm)) / 2
                for j, (kind, v, data) in enumerate(row):
                    x = x0 + j * (cw + 5 * mm)
                    if kind == "view":
                        img, sha = data
                        _rounded_image(doc, img, x, top, cw, cw,
                                       figure={"kind": "disclosed_render", "view": v,
                                               "source": "visual.disclosed_render.render",
                                               "png_sha256": sha, "label": K.DISCLOSURE})
                        cap = captions[v] + ". Digital rendering, not a photograph."
                    else:
                        c.saveState()
                        c.setDash(4, 3)
                        c.setStrokeColor(ACCENT)
                        c.setFillColor(SURFACE)
                        c.roundRect(x, top - cw, cw, cw, 3 * mm, fill=1, stroke=1)
                        c.restoreState()
                        doc.text(x + cw / 2, top - cw / 2 + 3 * mm, "PLACEHOLDER",
                                 FONT_UI_BOLD, 11, ACCENT, align="centre", track=1.5)
                        doc.text(x + cw / 2, top - cw / 2 - 3 * mm,
                                 "for a photograph of a worked sample", FONT_BODY_ITALIC,
                                 9.5, MUTED, align="centre")
                        cap = "Placeholder for a photograph of a tester's sample. Not for sale."
                        doc.figures.append({"kind": "photo_placeholder", "page": doc.pages,
                                            "label": cap})
                    doc.prose.append(cap)
                    yy = top - cw - 4.5 * mm
                    for line in _wrap(c, cap, FONT_BODY_ITALIC, 9.5, cw):
                        doc.text(x, yy, line, FONT_BODY_ITALIC, 9.5, MUTED)
                        yy -= 4.3 * mm
                doc.y = top - cw - 14 * mm

    # ---------------------------------------------------------------- 11. children's safety -
    # Its own page, before the terms, rendered only when the catalogue says this product is
    # merchandised to a child. A statement whose facts are missing goes onto `problems` and
    # `build_pattern_pdf` refuses the document.
    if childrens is not None:
        rendered = childrens_statements(cir, twin, childrens)
        doc.new_page(head)
        doc.heading(CHILDRENS_HEADING, kicker="Please read before you start")
        doc.para(CHILDRENS_INTRO, size=9.5)
        doc.space(1 * mm)
        for statement_key in rendered.required:
            if statement_key not in rendered.text:
                continue
            doc.heading(rendered.headings[statement_key], size=12)
            for block in rendered.text[statement_key].split("\n"):
                doc.para(block, size=9.5, running_head=head)
            citation = rendered.citations.get(statement_key)
            if citation:
                doc.para(citation, size=9, color=MUTED, running_head=head)
            else:
                doc.para("Source: none. This is Brambleloop Studio's own practice rather "
                         "than a published rule.", size=9, color=MUTED, running_head=head)
        for statement_key, why in sorted(rendered.unrenderable.items()):
            problems.append(
                f"PDF_CHILDRENS_STATEMENT_UNRENDERABLE: {statement_key} is required for a "
                f"{childrens[0]} product stated for {childrens[1]} and this document cannot "
                f"state it: {why}")

    # Approved contextual links supplied by assets.build, bound to lesson revisions.
    if lesson_links:
        from urllib.parse import urlsplit
        doc.heading("Technique help")
        for lesson_link in lesson_links:
            target = lesson_link["url"]
            parsed_url = urlsplit(target)
            revision = lesson_link["revision"]
            if (parsed_url.scheme != "https" or parsed_url.username or parsed_url.password
                    or parsed_url.query != "revision=" + revision
                    or not parsed_url.path.startswith("/learn/") or parsed_url.fragment):
                raise ValueError("unsafe or unversioned lesson link")
            label = ", ".join(lesson_link["topics"])
            doc.para(label, size=10)
            doc.need(6 * mm)
            doc.c.linkURL(target, (MARGIN, doc.y, PAGE_W - MARGIN, doc.y + 5 * mm),
                          relative=0, thickness=0)
            doc.para(target, size=MIN_BODY_PT)

    # ---------------------------------------------------------------- 12. terms ------------
    doc.new_page(head)
    doc.heading("Terms and support", kicker="Support and credits")
    # Rendered from `commerce.terms`, which is where these were decided.
    for i, line in enumerate(licence_paragraphs()):
        if not line.strip():
            doc.space(2 * mm)
        elif i == 0:
            doc.heading(line, size=12)
        elif line.startswith("- "):
            doc.need(6 * mm)
            doc.c.setFillColor(ROSE)
            doc.c.circle(MARGIN + 1.6 * mm, doc.y + 1.2 * mm, 1.1 * mm, fill=1, stroke=0)
            doc.para(line[2:], size=10, x=MARGIN + 6 * mm)
        else:
            doc.para(line, size=9.5, color=MUTED)
    doc.heading("Customer support", size=12)
    doc.para("If anything in this pattern does not add up, tell us through the shop you "
             "bought it from and we will fix the pattern itself, not just answer your "
             "question. Every report is checked against the compiler that validated this "
             "release.", size=10)
    doc.para(support_scope(cir), size=10)
    doc.heading("About this document", size=12)
    doc.para(AI_DISCLOSURE, size=9.5, color=MUTED)
    doc.para(platform_policy.DISCLOSURES["deterministic_render"], size=9.5, color=MUTED)
    doc.para(physical_status(twin), size=9.5, color=MUTED)
    doc.para(f"Typefaces: Cormorant Garamond, Lora and Work Sans, used under the "
             f"{pdf_fonts.LICENCE.split(' (')[0]}.", size=9.5, color=MUTED)
    doc.space(1 * mm)
    credit = "" if designer == COPYRIGHT_HOLDER else f" Designed by {designer}."
    doc.para(f"© {released_on.year} {COPYRIGHT_HOLDER}. All rights reserved.{credit}",
             size=9.5, color=MUTED)
    doc.space(1 * mm)
    doc.kv("release version", cir.version)
    doc.kv("released", released_on.isoformat())
    doc.kv("terminology", f"{terminology} terms")
    doc.kv("pattern id", f"{cir.slug}@{cir.version}")
    doc.para(f"This document is {doc.total_pages or doc.pages} pages. If your copy is "
             f"shorter than that, the download did not finish; ask for it again rather than "
             f"working from a partial pattern.", size=9.5, color=MUTED)

    # -- is the key a key? -------------------------------------------------
    # Measured on everything the document says, against the key it actually printed.
    missing = abbreviations.undefined_tokens(
        "\n".join(doc.prose), terminology,
        defined={entry.token for entry in key})
    if missing:
        problems.append(
            f"PDF_ABBREVIATION_UNDEFINED: {sorted(set(missing))} appear in this document and "
            f"the stitch key printed in it does not define them, so a maker meets a word the "
            f"document never explains")
    # -- every glyph drawn, in a face that has it -----------------------------
    problems.extend(sorted(set(doc.glyph_problems)))

    return doc, claims, problems


def _chart_height_with_legend(doc: "_Doc", art: dict, *, round_: bool) -> float | None:
    """How tall the chart may be so its legend fits under it -- never below the floor.

    `art["cell_mm"]` is the readable unit (cell or ring) measured at the full-width fit
    `_on_page_cell_mm` assumes. A smaller placement shrinks it in proportion, so the chart is
    only reduced while the measured unit stays at or above the brand floor; otherwise it keeps
    the full size the legibility check certified (None = the default fit).
    """
    img, legend = art["chart"], art["legend"]
    usable_w = PAGE_W - 2 * MARGIN
    full = min(1.0, usable_w / img.width)
    if img.height * full > PAGE_H - 2 * MARGIN:
        full *= (PAGE_H - 2 * MARGIN) / (img.height * full)
    leg_scale = min(1.0, usable_w / legend.width, (70 * mm) / legend.height)
    room = doc.y - MARGIN - legend.height * leg_scale - 12 * mm
    if room <= 0 or img.height * full <= room:
        return None
    floor = CHART_MIN_RING_MM if round_ else CHART_MIN_CELL_MM
    shrunk = room / (img.height * full)
    if art.get("cell_mm") is None or art["cell_mm"] * shrunk < floor:
        return None
    return room


def _step_line(doc: "_Doc", ln: str, yarn_rgb: dict, x: float, width: float,
               head: str) -> None:
    """One written line, full width, with its colour dot and its count emphasised."""
    segs, colour = _step_segments(ln, yarn_rgb)
    doc.prose.append(ln)
    lines = _rich_lines(doc.c, segs, width - 6 * mm, 10)
    leading = 14.2
    doc.need(len(lines) * leading + 1 * mm, head)
    if colour is not None:
        _dot(doc.c, x + 1.8 * mm, doc.y + 1.2 * mm, colour)
    doc.y = _draw_rich(doc, lines, x + 6 * mm, doc.y, 10, leading) - 1.5 * mm


def _dot(c, cx: float, cy: float, rgb) -> None:
    c.saveState()
    c.setFillColor(rgb)
    c.setStrokeColor(FOREST)
    c.setLineWidth(0.5)
    c.circle(cx, cy, 1.7 * mm, fill=1, stroke=1)
    c.restoreState()


def _step_cards(doc: "_Doc", groups: list, yarn_rgb: dict, comp, head: str) -> None:
    """Instruction groups as cards, two to a row: the diagram of the piece after the group's
    last round, beside the written lines of that group."""
    usable = PAGE_W - 2 * MARGIN
    gap = 5 * mm
    cw = (usable - gap) / 2
    pic = 27 * mm
    tx_off = pic + 6 * mm
    tw = cw - tx_off - 4 * mm
    size = 9.5
    leading = 13.2
    label_word = "Rnd" if "round" in comp.construction else "Row"
    laid = []
    for st, lines in groups:
        rich = []
        for ln in lines:
            segs, colour = _step_segments(ln, yarn_rgb)
            rich.append((ln, colour, _rich_lines(doc.c, segs, tw - 4.5 * mm, size)))
        text_h = sum(len(r[2]) * leading + 1.6 * mm for r in rich)
        h = max(pic + 11 * mm, text_h + 8 * mm)
        laid.append((st, rich, h))
    for i in range(0, len(laid), 2):
        pair = laid[i:i + 2]
        h = max(p[2] for p in pair)
        doc.need(h + 1 * mm, head)
        top = doc.y + 1 * mm
        for j, (st, rich, _h) in enumerate(pair):
            x = MARGIN + j * (cw + gap)
            doc.panel(x, top, cw, h)
            doc.place(st.image(), x + 3 * mm, top - 3 * mm, pic, pic,
                      figure={"kind": "construction_diagram", "round": st.round,
                              "source": "publish.construction_diagrams.stages",
                              "png_sha256": hashlib.sha256(st.png).hexdigest(),
                              "label": f"after {label_word} {st.round}"})
            lab = f"after {label_word} {st.round}"
            doc.prose.append(lab)
            doc.text(x + 3 * mm + pic / 2, top - pic - 7 * mm, lab, FONT_UI_MEDIUM, MIN_BODY_PT,
                     MUTED, align="centre")
            y = top - 7 * mm
            for ln, colour, lines in rich:
                doc.prose.append(ln)
                if colour is not None:
                    _dot(doc.c, x + tx_off + 1.6 * mm, y + 1.1 * mm, colour)
                y = _draw_rich(doc, lines, x + tx_off + 4.5 * mm, y, size, leading) - 1.6 * mm
        doc.y = top - h - 3.5 * mm


# How far the fabric's own row gauge may sit from the swatch gauge before the document has to
# reconcile the two out loud. Set at a tenth because a maker checking their work cannot tell
# a 10% difference from their own tension, and can tell a 50% one -- which is what a pattern
# stated in sc and worked in dc actually produces.
ROW_GAUGE_DRIFT = 0.10


def _fabric_row_gauge(twin: TwinModel) -> float | None:
    """How many rows of *this pattern's fabric* make 10 cm, from the twin's own height.

    Read off the twin rather than re-derived from the stitch heights, so it cannot become a
    second opinion about a measurement the twin has already made.

    **Only the rows that stack.** `len(row_widths) / height_cm` is a row gauge for a flat
    piece and an arithmetic accident for a round one, because a round-worked piece spends
    some of its rounds growing outward instead of upward. On `market-basket-large` it
    divided seventy rounds -- twenty-four of them a flat base -- by the height of the
    forty-six-round wall and reported "about 30 rows = 10 cm" against a stated 20, on a
    basket whose wall is worked at exactly the stated 20. The twin's own geometry already
    separates the two: a ring that rises has `rise_cm > 0` and a ring that only widens does
    not. A piece with no rising ring at all -- the hexagon coaster, a flat disc -- has no
    vertical row gauge to state, and `None` is the answer rather than a number.
    """
    rev = getattr(twin, "geometry", None)
    rings = list(getattr(rev, "rings", []) or [])
    if rings:
        risers = [r for r in rings if r.rise_cm > 0]
        axial = sum(r.rise_cm for r in rings)
        if not risers or axial <= 0:
            return None
        return len(risers) / axial * 10.0
    rows = len(twin.row_widths)
    if not rows or not twin.height_cm:
        return None
    return rows / twin.height_cm * 10.0


def _taller_than_gauge(cir: CIR, twin: TwinModel) -> tuple[str, ...]:
    """Stitches in this fabric taller than the one the gauge was swatched over.

    The premise of the reconciliation paragraph below, measured instead of asserted. That
    paragraph explains a swatch/fabric difference by saying the pattern "is worked in taller
    stitches as well" -- and it was printed on every document whose two row gauges differed
    by a tenth, including four worked entirely in single crochet. All three nesting baskets
    and the hexagon coaster said it, which is two of the three Launch-0 products telling a
    buyer something measurably untrue about their own fabric on the page headed "Gauge, and
    why it matters here".

    Heights come from `cir.stitches`, which is where a stitch's height is defined, so this
    cannot drift from the geometry that produced the difference it is explaining.
    """
    from ..cir import stitches as _stitches

    if not cir.gauge or not cir.gauge.stitch_type:
        return ()
    try:
        base = _stitches.get(cir.gauge.stitch_type).height
    except Exception:  # an unknown gauge stitch is not this function's to diagnose
        return ()
    out = []
    for code in sorted(twin.stitch_types_used):
        try:
            height = _stitches.get(code).height
        except Exception:
            continue
        if height > base:
            out.append(code)
    return tuple(out)


def _round_gauge_note(cir: CIR, twin: TwinModel, terminology: str) -> str:
    """What the gauge means on a piece worked in the round, when no stitch is taller.

    The reconciliation paragraph does not apply here and printing it anyway was the defect.
    Saying nothing would leave a real question unanswered, because a round-worked maker still
    has to know what to check their rounds against -- so this says which gauge governs which
    dimension, in the piece's own numbers.
    """
    rev = getattr(twin, "geometry", None)
    rings = list(getattr(rev, "rings", []) or [])
    if not rings or _taller_than_gauge(cir, twin) or not cir.gauge:
        return ""
    risers = [r for r in rings if r.rise_cm > 0]
    stitch = _gauge_stitch(cir, terminology)
    flat = len(rings) - len(risers)
    if not risers:
        # F7: the swatch does have a row gauge, and the swatch steps above use it. What the
        # piece lacks is a dimension that row gauge governs.
        return (f"This piece is worked in the round and every round grows it outward rather "
                f"than upward, so the {cir.gauge.rows_per_10cm:g} rows to 10 cm is only a "
                f"check on your swatch: no measurement of the piece depends on it. The "
                f"{cir.gauge.stitches_per_10cm:g} stitches to 10 cm in {stitch} is what sets "
                f"how wide it comes out. Check the measurement across against 'Checking "
                f"your progress' below.")
    return (f"This piece is worked in the round, and its two gauges do different jobs. "
            f"Rounds 1 to {flat} grow the base outward without adding height, so the "
            f"{cir.gauge.stitches_per_10cm} stitches to 10 cm in {stitch} is what decides "
            f"how wide the base comes out. The {cir.gauge.rows_per_10cm} rows to 10 cm is "
            f"the gauge of the {len(risers)} straight rounds above it, which is where the "
            f"height comes from. Check both against 'Checking your progress' below, which "
            f"gives each round's measurement across and up.")


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

    shown = [c for c in twin.cells if rounds is None or rounds[0] <= c.row <= rounds[1]]
    return {
        "chart": chart,
        "legend": render_legend(cir, twin),
        "caption": caption,
        "cell_mm": measured,
        "cues": cues,
        "problems": problems,
        # What the printed chart draws, for the key printed under it (F4 / N2).
        "marks": sorted({c.stitch for c in shown if c.stitch in chart_mod.ROUND_MARKED_CODES}),
        "charted_colours": sorted({c.color for c in shown if c.color}),
        # The same rung at three times the pixels, embedded at the measured rung's size
        # (F5 / F6): every legibility number above is measured on `chart`, and the page shows
        # the identical drawing at print resolution.
        "chart_hi": _hi_res_round(cir, twin, rounds, w),
    }


HI_RES = 3


def _hi_res_round(cir: CIR, twin: TwinModel, rounds, wedges):
    """The round chart drawn at HI_RES times the pixels of the measured 22-px rung."""
    spec = ChartSpec(cell_px=22 * HI_RES, margin_px=ChartSpec().margin_px * HI_RES,
                     max_width_px=ChartSpec().max_width_px * HI_RES)
    return render_round_chart(cir, twin, spec, rounds=rounds, wedges=wedges)


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
        tiled = _tiled_chart_art(cir, twin, grid, colour_grid)
        if tiled is not None:
            return tiled

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
        "marks": sorted(twin.stitch_types_used),
        "charted_colours": sorted({c for row in charted_colors for c in row if c}),
        # What the picture actually says about colour, asked of the function that drew it. A
        # chart cropped to one repeat can be single-colour in a two-colour design, and a key
        # for letters the picture does not carry is a key to nothing.
        "cues": chart_mod.flat_cue_letters(cir, charted_colors, charted_cell),
        "problems": problems,
    }


# Reserve the measured area for heading, explanatory caption and tile range.
CHART_TILE_HEIGHT = PAGE_H - 2 * MARGIN - 55 * mm


def _tiled_chart_art(cir, twin, grid, colors):
    """Partition the full authoritative fabric; no omitted borders or inferred repeats."""
    full_rows, full_cols = len(grid), max(map(len, grid))
    spec = ChartSpec(cell_px=32, margin_px=64)
    cols, rows = min(24, full_cols), min(28, full_rows)
    def scale_for(image):
        return min(1.0, (PAGE_W - 2 * MARGIN) / image.width, CHART_TILE_HEIGHT / image.height)
    while True:
        sample = ( [r[:cols] for r in grid[:rows]], [r[:cols] for r in colors[:rows]] )
        chart = render_chart(cir, twin, spec, grids=sample, caption="Chart tile",
                             show_columns=True)
        scale = scale_for(chart)
        if (spec.cell_px * scale / mm >= CHART_MIN_CELL_MM
                and min(chart_mod.flat_type_px(spec.cell_px).values()) * scale >= MIN_BODY_PT):
            break
        if rows >= cols and rows > 1: rows -= 1
        elif cols > 1: cols -= 1
        else: return None  # Caller retains measured, structured refusal; never PASS.
    tiles = []
    for row in range(0, full_rows, rows):
        for col in range(0, full_cols, cols):
            grids = ([r[col:col+cols] for r in grid[row:row+rows]],
                     [r[col:col+cols] for r in colors[row:row+rows]])
            if not any(grids[0]):
                # A shaped piece's rows are ragged: past the widest row of this band there
                # is no fabric, so there is no tile to print (every stitch is still in one).
                continue
            image = render_chart(cir, twin, spec, grids=grids, caption="Chart tile",
                                 row_offset=row, column_offset=col, show_columns=True)
            scale = scale_for(image)
            tiles.append({"row_start": row+1, "row_end": min(row+rows, full_rows),
                          "column_start": col+1, "column_end": min(col+cols, full_cols),
                          "grids": grids, "chart": image,
                          "cell_mm": spec.cell_px*scale/mm,
                          "minimum_type_pt": min(chart_mod.flat_type_px(spec.cell_px).values())*scale})
    problems = []
    if any(t["cell_mm"] < CHART_MIN_CELL_MM or t["minimum_type_pt"] < MIN_BODY_PT for t in tiles):
        problems.append("PDF_CHART_CELL_BELOW_BRAND_MINIMUM: tiled chart below existing minimum")
    return {"chart": tiles[0]["chart"], "tiles": tiles, "legend": render_legend(cir, twin),
            "caption": f"Full chart: {full_cols} columns by {full_rows} rows, split into {len(tiles)} tiles. "
                       "Columns are numbered left to right. Complete each entire row across its tiles: "
                       "odd rows right to left; even rows left to right. Then advance one row. "
                       "Do not work a tile as a separate piece. Every border and stitch is included once.",
            "cell_mm": min(t["cell_mm"] for t in tiles),
            "cues": chart_mod.flat_cue_letters(cir, colors, spec.cell_px), "problems": problems}


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
