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

from ..cir.compiler import compile_cir
from ..cir.model import CIR
from ..cir.twin import TwinModel, build_twin
from ..cir.writer import write_pattern
from . import substitution, value_stack
from .charts import (
    ChartSpec, crop_grids, detect_repeat, is_round, render_chart, render_legend,
    render_round_chart,
)

PAGE_W, PAGE_H = LETTER
MARGIN = 18 * mm

INK = colors.HexColor("#1A2B3C")
PINE = colors.HexColor("#244A3A")
CREAM = colors.HexColor("#FAF6EB")
GOLD = colors.HexColor("#C49545")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#D6CEBC")


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

    def __init__(self, title: str):
        self.buf = io.BytesIO()
        self.c = rl_canvas.Canvas(self.buf, pagesize=LETTER, invariant=1)
        self.c.setTitle(title)
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
            self.c.setFont("Helvetica", 8)
            self.c.drawString(MARGIN, PAGE_H - MARGIN + 6 * mm, running_head.upper())

    def _footer(self) -> None:
        self.c.setFillColor(MUTED)
        self.c.setFont("Helvetica", 8)
        self.c.drawRightString(PAGE_W - MARGIN, MARGIN - 8 * mm, f"page {self.pages}")

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

    def kv(self, key: str, value: str) -> None:
        self.need(5 * mm)
        self.c.setFont("Helvetica-Bold", 9)
        self.c.setFillColor(MUTED)
        self.c.drawString(MARGIN, self.y, key.upper())
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


def build_pattern_pdf(cir: CIR, *, terminology: str = "US",
                      twin: TwinModel | None = None,
                      designer: str = "Brambleloop Studio",
                      released_on: date | None = None) -> PatternDocument:
    """Render the full pattern document.

    Refuses outright if the CIR does not compile. A PDF built on failed arithmetic is a
    defect we would be charging money for, and the release chain is supposed to make that
    impossible rather than merely unlikely.
    """
    result = compile_cir(cir)
    if not result.ok:
        raise ValueError(
            f"refusing to render a PDF for a pattern that fails compilation: "
            f"{[str(f) for f in result.errors][:3]}"
        )
    twin = twin or build_twin(cir, result)
    released_on = released_on or date.today()

    doc = _Doc(f"{cir.title} - {designer}")
    head = f"{cir.title} - v{cir.version}"

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
    doc.c.setFillColor(GOLD)
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
        doc.kv(m.color_id or m.name, f"{m.name} ({m.yarn_weight})")
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

    # -- instructions ------------------------------------------------------
    doc.new_page(head)
    doc.heading(f"Instructions ({terminology} terms)")
    text = write_pattern(cir, result, terminology=terminology,
                         width_cm=twin.width_cm, height_cm=twin.height_cm)
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
    if is_round(cir, twin):
        # A ragged grid is not a chart of a disc, and "read odd rows right to left" is
        # flat-fabric advice: every round is worked in the same direction.
        doc.para("This piece is worked in the round, so the chart is drawn as rounds: round "
                 "1 at the centre, each ring outward one round. Count the wedges in a ring "
                 "and you get the stitch count in the written line for that round, because "
                 "both come from the same verified data. V marks an increase and A a "
                 "decrease.", size=9, color=MUTED)
        doc.space(2 * mm)
        doc.image(render_round_chart(cir, twin, ChartSpec(cell_px=22)), running_head=head)
        rep_cols = rep_rows = 0
        show_repeat = False
    else:
        grid, colour_grid = twin.chart_grid(), twin.color_grid()
        full_cols = max((len(r) for r in grid), default=0)
        full_rows = len(grid)
        rep_cols, rep_rows = detect_repeat(grid, colour_grid)
        across, up = (full_cols // rep_cols if rep_cols else 1,
                      full_rows // rep_rows if rep_rows else 1)

        # A whole-blanket chart on one page gives each stitch about a pixel. Where the
        # fabric is genuinely built from a repeat, chart the repeat and say how to place it
        # -- which is both readable and how mosaic patterns are actually published.
        show_repeat = (across > 1 or up > 1) and full_cols > 48
    if show_repeat:
        doc.para(f"This chart shows one repeat: {rep_cols} stitches wide and {rep_rows} rows "
                 f"tall. Work it {across} times across and {up} times up for the finished "
                 f"size. The full piece is {full_cols} stitches by {full_rows} rows. The "
                 f"chart is generated from the same verified data as the written "
                 f"instructions, so the two cannot disagree. Read odd rows right to left and "
                 f"even rows left to right.", size=9, color=MUTED)
        doc.space(2 * mm)
        grids = crop_grids(grid, colour_grid, rep_cols, rep_rows)
        caption = f"{cir.title} - one repeat ({rep_cols} sts x {rep_rows} rows)"
        doc.image(render_chart(cir, twin, ChartSpec(cell_px=20), grids=grids,
                               caption=caption), running_head=head)
    else:
        doc.para("The chart below is generated from the same verified data as the written "
                 "instructions above. Read odd rows right to left and even rows left to "
                 "right.", size=9, color=MUTED)
        doc.space(2 * mm)
        doc.image(render_chart(cir, twin, ChartSpec(cell_px=22)), running_head=head)
    doc.image(render_legend(cir, twin), running_head=head)

    # -- licence -----------------------------------------------------------
    doc.new_page(head)
    doc.heading("Terms and support")
    doc.para(LICENCE)
    doc.space(3 * mm)
    doc.para("If anything in this pattern does not add up, tell us and we will fix the "
             "pattern itself, not just answer your question. Every report is checked against "
             "the compiler that validated this release.", size=10)
    doc.space(3 * mm)
    doc.kv("release version", cir.version)
    doc.kv("terminology", f"{terminology} terms")

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
    )


def _difficulty(cir: CIR, twin: TwinModel) -> str:
    """Stated from what the pattern actually contains, not from marketing instinct."""
    advanced = {"tr", "dc_inc", "dc_dec"}
    used = twin.stitch_types_used
    colors_used = len([c for c in twin.colors_used if c])
    if used & advanced or colors_used > 3:
        return "intermediate"
    if colors_used > 1 or cir.construction != "flat_rows":
        return "confident beginner"
    return "beginner"
