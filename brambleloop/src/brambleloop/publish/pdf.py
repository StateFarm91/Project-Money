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
from . import abbreviations, substitution, value_stack
from .charts import (
    ChartSpec, crop_grids, detect_repeat, is_round, render_chart, render_legend,
    render_round_chart,
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

# WCAG 2.1 AA for text below 18pt. Stated as the measurement it is: a ratio of relative
# luminance between the ink and the paper it sits on.
MIN_CONTRAST = 4.5


def _relative_luminance(colour) -> float:
    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = channel(colour.red), channel(colour.green), channel(colour.blue)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg) -> float:
    """Contrast ratio between two reportlab colours, 1.0 (invisible) to 21.0 (black on white)."""
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _legible(fg, bg, *, minimum: float = MIN_CONTRAST):
    """The brand colour, darkened only as far as it has to be to be readable on this paper.

    The brand's `muted` grey measures 4.48:1 on the brand's cream -- a fraction under the AA
    floor, and it is the colour of the yarn-tolerance note, the substitution caveats, the
    chart instructions and the page numbers, which is most of the explanatory prose in the
    document. Rather than move a palette that the storefront and the chart renderer also
    read, the document darkens its own ink until it passes and leaves the brand alone.

    Returns the original colour untouched when it already passes, so a future palette that
    is legible on its own is rendered exactly as the brand specifies it.
    """
    out = colors.Color(fg.red, fg.green, fg.blue)
    if contrast(out, bg) >= minimum:
        return out
    darker = _relative_luminance(out) < _relative_luminance(bg)
    for _ in range(64):
        if contrast(out, bg) >= minimum:
            return out
        factor = 0.97 if darker else 1.03
        out = colors.Color(min(1.0, max(0.0, out.red * factor)),
                           min(1.0, max(0.0, out.green * factor)),
                           min(1.0, max(0.0, out.blue * factor)))
    return out  # pragma: no cover - 64 steps reach black or white from any start


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


LICENCE = (
    "This pattern is for your personal use. You may sell finished items you make from it. "
    "You may not resell, share or redistribute the pattern file itself, and you may not "
    "reproduce the charts or written instructions elsewhere."
)

AI_DISCLOSURE = (
    "How this pattern was made: the design was developed with AI assistance and every stitch "
    "count in it was verified by an automated pattern compiler before release, row by row. "
    "The charts in this document are generated directly from the same verified data as the "
    "written instructions, so the two cannot disagree."
)


COPYRIGHT_HOLDER = "Brambleloop Studio"


def build_pattern_pdf(cir: CIR, *, terminology: str = "US",
                      twin: TwinModel | None = None,
                      designer: str = "Brambleloop Studio",
                      released_on: date | None = None) -> PatternDocument:
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
    total = 0
    for _ in range(4):
        doc, claims, problems = _render(cir, twin, result, text=text, art=art,
                                        terminology=terminology, designer=designer,
                                        released_on=released_on, total_pages=total)
        if doc.pages == total:
            break
        total = doc.pages
    else:  # pragma: no cover - no document in the catalogue oscillates
        raise ValueError(
            f"{cir.slug}: the page count does not settle, so the footer would state a "
            f"length the document does not have")
    return PatternDocument(
        pdf_bytes=doc.finish(),
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
    )


def _render(cir: CIR, twin: TwinModel, result, *, text: str, art: dict,
            terminology: str, designer: str, released_on: date,
            total_pages: int) -> tuple["_Doc", list[str], list[str]]:
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
                        f"= 10 cm in {cir.gauge.stitch_type}")
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
    instructed = "\n".join([text] + [abbreviations.METHOD.get(code, "")
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
                                       f"{cir.gauge.stitch_type}")
            doc.kv("this fabric", f"about {fabric:.0f} rows = 10 cm")
            doc.para(
                f"Those two numbers are both right and they are not the same number. The "
                f"swatch gauge is measured over plain {cir.gauge.stitch_type}; this pattern "
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
        doc.para(
            f"Printing in black and white: two of these colours are close in lightness and "
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
    missing = abbreviations.undefined_tokens(text, terminology)
    if missing:
        # Reported rather than silently omitted: a key that is quietly short is worse than
        # no key, because the maker stops expecting to find things in it.
        problems.append(
            f"PDF_ABBREVIATION_UNDEFINED: {sorted(missing)} appear in the instructions and "
            f"the stitch key cannot define them, so a maker meets a word the document never "
            f"explains")

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
    doc.space(2 * mm)
    # The legend is a picture, so nothing in it is searchable, selectable or readable by a
    # screen reader. The same key exists in text on the Abbreviations page; this line says so
    # rather than leaving a maker who cannot see the image with no route to it.
    doc.para("The stitch key in the image above is also written out under Abbreviations, "
             "earlier in this document.", size=9, color=MUTED)

    # -- licence -----------------------------------------------------------
    doc.new_page(head)
    doc.heading("Terms and support")
    doc.para(LICENCE)
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


def _chart_art(cir: CIR, twin: TwinModel) -> dict:
    """The chart, its legend and the sentence that explains them, rendered once.

    Lifted out of the page loop because the document is now laid out twice -- once to learn
    how many pages it has, once to print that number in the footer -- and a two-thousand-pixel
    chart must not be drawn twice to find that out.
    """
    if is_round(cir, twin):
        # A ragged grid is not a chart of a disc, and "read odd rows right to left" is
        # flat-fabric advice: every round is worked in the same direction.
        return {
            "chart": render_round_chart(cir, twin, ChartSpec(cell_px=22)),
            "legend": render_legend(cir, twin),
            "caption": ("This piece is worked in the round, so the chart is drawn as rounds: "
                        "round 1 at the centre, each ring outward one round. Count the "
                        "wedges in a ring and you get the stitch count in the written line "
                        "for that round, because both come from the same verified data. V "
                        "marks an increase and A a decrease."),
        }

    grid, colour_grid = twin.chart_grid(), twin.color_grid()
    full_cols = max((len(r) for r in grid), default=0)
    full_rows = len(grid)
    rep_cols, rep_rows = detect_repeat(grid, colour_grid)
    across, up = (full_cols // rep_cols if rep_cols else 1,
                  full_rows // rep_rows if rep_rows else 1)

    # A whole-blanket chart on one page gives each stitch about a pixel. Where the fabric is
    # genuinely built from a repeat, chart the repeat and say how to place it -- which is
    # both readable and how mosaic patterns are actually published.
    if (across > 1 or up > 1) and full_cols > 48:
        grids = crop_grids(grid, colour_grid, rep_cols, rep_rows)
        return {
            "chart": render_chart(cir, twin, ChartSpec(cell_px=20), grids=grids,
                                  caption=f"{cir.title} - one repeat "
                                          f"({rep_cols} sts x {rep_rows} rows)"),
            "legend": render_legend(cir, twin),
            "caption": (f"This chart shows one repeat: {rep_cols} stitches wide and "
                        f"{rep_rows} rows tall. Work it {_times(across)} across and "
                        f"{_times(up)} up for the finished size. The full piece is "
                        f"{full_cols} stitches by {full_rows} rows. The chart is generated "
                        f"from the same verified data as the written instructions, so the "
                        f"two cannot disagree. Read odd rows right to left and even rows "
                        f"left to right."),
        }
    return {
        "chart": render_chart(cir, twin, ChartSpec(cell_px=22)),
        "legend": render_legend(cir, twin),
        "caption": ("The chart below is generated from the same verified data as the written "
                    "instructions above. Read odd rows right to left and even rows left to "
                    "right."),
    }


def _times(n: int) -> str:
    """'once', not '1 times'. The shipped document said the second one."""
    return "once" if n == 1 else f"{n} times"
