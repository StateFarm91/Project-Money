"""ENG-GARMENT: the garment pattern PDF, every size in one document, US and UK editions.

Structure follows `research/benchmarks/PDF_STRUCTURE_STANDARD.md` (structure only -- no text,
number, schematic or layout is taken from the benchmark). Every figure on these pages comes
from the certified release: the instructions from `publish.garment_writer` (the recorded steps
of each size), the size chart from `gates.garment_fit.size_claims` (each size's twin), the
schematic from `publish.garment_schematic` (each size's rows), the finishing from the CIR's
seams and the recorded pick-ups. `build` refuses a release that is not granted, and re-reads
its own text before returning: the parenthesised pattern is read back per size
(`garment_fit.multi_size_problems`), the size chart is re-derived from the twin
(`garment_fit.claim_problems`), and a child's or baby's garment carries the child-safety
section, whose content checks (`gates.child_safety`) must pass on the rendered text.

Sections, in order: cover; at a glance (overview table); supplies (yarn, balls per size, hook,
notions, a gauge for every fabric); how it is made (construction narrative); size chart; the
schematic; tips; abbreviations and special stitches; the pattern; finishing; child safety
(where it applies); yarn and gauge; terms, licence and support; about Brambleloop Studio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..products import garment_families as GF
from . import garment_schematic as SCH
from . import garment_writer as W
from . import pdf as P

IN_PER_CM = 1 / 2.54
YARDAGE_TOLERANCE = 0.20          # B-007: an estimate within +/-20% until calibrated
US_HOOK = {2.25: "B-1", 2.75: "C-2", 3.25: "D-3", 3.5: "E-4", 3.75: "F-5", 4.0: "G-6",
           4.5: "7", 5.0: "H-8", 5.5: "I-9", 6.0: "J-10", 6.5: "K-10½", 8.0: "L-11"}
CONSTRUCTION_NAMES = {
    "raglan": "top-down raglan, worked flat in one piece from the neck",
    "one_piece": "a flat one-piece body with built-in sleeves",
    "side_to_side": "two panels worked side to side and seamed",
    "drop_shoulder": "drop-shoulder panels with seaming",
}
SECTIONS = ("At a glance", "Supplies", "How it is made", "Size chart", "Schematic", "Tips",
            "Abbreviations", "Pattern", "Finishing", "Yarn and gauge",
            "Terms, licence and support", "About Brambleloop Studio")


class GarmentPdfRefused(ValueError):
    pass


@dataclass
class GarmentDocument:
    pdf_bytes: bytes
    terminology: str
    text: str
    svg: str
    sections: list[str] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    pattern_lines: dict = field(default_factory=dict)
    piece_of: dict = field(default_factory=dict)


def _v(xs, unit: str = "") -> str:
    return W.values(xs) + unit


def _in(cm: float) -> str:
    return f"{cm * IN_PER_CM:.1f}"


def _weight(cir):
    from .substitution import WEIGHT_BY_KEY

    return WEIGHT_BY_KEY[cir.gauge.yarn_weight]


def narrative(kind: str, facts, design) -> str:
    buttons = bool(facts.buttons)
    if kind == "raglan":
        return ("You begin at the neck with a short chain and work the yoke flat, increasing at "
                "four markers so the fronts, sleeves and back all grow together. At the "
                "underarm the sleeve stitches go on hold and the fronts and back continue as "
                "one piece to the hem, finished with a back-loop band. Each sleeve is then "
                "worked from its held stitches down to the cuff, decreasing evenly, and its "
                "seam is closed. Last, a band is picked up along each front edge"
                + (", with buttonholes on the right band." if buttons else
                   "; the fronts meet edge to edge with nothing to fasten."))
    if kind == "one_piece":
        return ("The whole body, sleeves included, is one flat piece. You start at the front "
                "hem, work up to the underarm, chain on the sleeves at both sides and carry on "
                "to the shoulder line, where a chain bridges the slash neck. The back is the "
                "front in reverse: work down, leave the sleeve stitches unworked, and finish at "
                "the back hem. Fold at the shoulder line and seam the sides and the underside "
                "of each sleeve; then pick up and work the cuffs and the neckband.")
    if kind == "side_to_side":
        return ("The back and the front are each one panel worked side to side: the "
                "foundation chain runs from hem to shoulder, so the rows run up and down the "
                "finished vest and the hem band is worked into the start of every row. The "
                "panels are joined at the shoulders, leaving the neck open, and down the sides, "
                "leaving the armholes open.")
    return ("The body is one panel worked from the front hem up over the shoulders, with a "
            "chain bridging the slash neck, and down to the back hem. The sleeves are worked "
            "from the cuff up, increasing evenly, and sewn on centred on the shoulder line; "
            "the sides and sleeve seams are closed, and the neckband is picked up round the "
            "neck opening.")


TIPS = (
    "Read each piece through before you start it, and mark the size you are making on every "
    "line: the smallest size comes first and the others follow in parentheses, in the size "
    "chart's order.",
    "Swatch both fabrics: the main fabric and the back-loop band. If your swatch has more "
    "stitches than the gauge, use a larger hook; fewer, a smaller hook.",
    "Count your stitches at the end of every row that changes the count: every line ends "
    "with the count, for every size.",
    "Use locking stitch markers for the raglan lines and move them up as you go.",
    "Chain loosely wherever the pattern says so (the sleeves and the neck bridge): the next "
    "row works into those chains and they must be as wide as the fabric.",
    "Pick up stitches evenly: divide the edge into quarters with markers and pick up a "
    "quarter of the stitches in each.",
    "Weigh a finished ball's worth of fabric early to check your yardage against the size "
    "chart; tension changes yardage before it changes size.",
)


def _hook(mm: float) -> str:
    us = US_HOOK.get(mm)
    return f"{mm:g} mm" + (f" (US {us})" if us else "") + " or the size you need for gauge"


def build(release, terminology: str = "US") -> GarmentDocument:
    """The customer document for a granted garment release."""
    from ..cir.graded import FIT_EASE_BANDS_CM
    from ..gates import child_safety as CS
    from ..gates import garment_fit as GFIT

    if not release.granted:
        raise GarmentPdfRefused(f"{release.spec.key} is not granted: {release.reasons()[:3]}")
    terminology = terminology.upper()
    if terminology not in P.TERMINOLOGIES:
        raise GarmentPdfRefused(f"no {terminology!r} edition")
    t = W.Terms(terminology)
    sizes = list(release.cirs)
    cirs = release.cirs
    cir0 = cirs[sizes[0]]
    facts = [GF.facts_of(cirs[s]) for s in sizes]
    kind = GF.construction_of(cir0)
    spec, design = release.spec, release.design
    claims = release.claims or GFIT.size_claims(design, cirs)
    pattern = W.write(design, cirs, terminology)
    finishing = W.finishing_lines(design, cirs, terminology)
    sch = SCH.primitives(design, cirs)
    svg = SCH.to_svg(sch)
    weight = _weight(cir0)
    gauge = cir0.gauge
    safety = CS.evaluate(cir0)
    title = spec.title
    head = f"{title} · {terminology} terms"

    def render(total_pages: int):
        doc = P._Doc(title, total_pages=total_pages, author=P.COPYRIGHT_HOLDER,
                     subject=f"Crochet garment pattern, sizes {sizes[0]}-{sizes[-1]}, "
                             f"{terminology} terms",
                     footer_left=f"© {P.COPYRIGHT_HOLDER} · {title}", header_right="")
        # 1. cover
        doc.new_page(None)
        doc.y -= 40
        doc.text(P.MARGIN, doc.y, P.COPYRIGHT_HOLDER.upper(), P.FONT_UI_BOLD, 11, P.ACCENT,
                 track=1.4)
        doc.y -= 30
        doc.heading(title, kicker=f"{spec.category} · {terminology} terms")
        doc.para(f"Sizes {sizes[0]} to {sizes[-1]} ({len(sizes)} sizes), graded from the "
                 f"{design.table.name} body measurements. {narrative(kind, facts[0], design)}")
        doc.para(P.AI_DISCLOSURE, size=9.5)
        doc.para("No sample photograph is included: this pattern has not yet been made up as a "
                 "photographed sample. Every measurement in it is computed from the pattern's "
                 "own rows at the stated gauge.", size=9.5)
        # 2. at a glance
        doc.new_page(head)
        doc.heading("At a glance", kicker="Overview")
        lo, hi = FIT_EASE_BANDS_CM[design.fit.character]
        for k, v in (
                ("Skill level", "Easy: single crochet, working through the back loop, "
                                "increases and decreases, picking up stitches"),
                ("Sizes", ", ".join(sizes) + f" ({design.table.name}, {design.table.source_url},"
                                             f" read {design.table.retrieved})"),
                ("Fit", f"{design.fit.character}: {lo:g}-{hi:g} cm "
                        f"({_in(lo)}-{_in(hi)} in) of ease at the chest"),
                ("Yarn weight", f"{weight.also_called[0]} (CYC {weight.number}, {weight.key})"),
                ("Hook", _hook(gauge.hook_mm)),
                ("Construction", CONSTRUCTION_NAMES[kind]),
                ("Gauge", f"{gauge.stitches_per_10cm:g} sts and {gauge.rows_per_10cm:g} rows "
                          f"= 10 cm (4 in) in {t.sc}"),
                ("Editions", "US terms and UK terms, as two files")):
            doc.kv(k, v)
        # 3. supplies
        doc.heading("Supplies", kicker="What you need")
        ball = claims[0]
        doc.kv("Yarn", f"{spec.weight} weight {spec.fibre}, about {ball['ball_m']:g} m "
                       f"({ball['ball_yd']} yd) per {ball['ball_g']} g ball")
        doc.kv("Balls, by size", _v([c["balls"] for c in claims]) + " balls")
        doc.kv("Hook", _hook(gauge.hook_mm))
        notions = ["a tapestry needle"]
        if kind == "raglan":
            notions.insert(0, "4 locking stitch markers")
        if any(f.buttons for f in facts):
            notions.insert(0, f"{_v([f.buttons for f in facts])} buttons, {GF.BUTTON_MM} mm")
        doc.kv("Notions", "; ".join(notions))
        doc.kv("Gauge: main fabric", f"{gauge.stitches_per_10cm:g} sts and "
                                     f"{gauge.rows_per_10cm:g} rows = 10 cm (4 in) in {t.sc} "
                                     f"through both loops, with the hook above")
        doc.kv("Gauge: band fabric", f"{gauge.stitches_per_10cm:g} sts and "
                                     f"{gauge.rows_per_10cm:g} rows = 10 cm (4 in) in {t.sc} "
                                     f"through the back loop only, same hook. The pattern "
                                     f"computes the bands at this gauge: check a band swatch "
                                     f"to the same counts")
        # 4. construction
        doc.heading("How it is made", kicker="Construction")
        doc.para(narrative(kind, facts[0], design))
        # 5. size chart
        doc.new_page(head)
        doc.heading("Size chart", kicker="Body and finished measurements")
        doc.para(f"Choose your size by the body chest measurement. Finished measurements are "
                 f"the garment's own, computed from each size's rows at the stated gauge; ease "
                 f"is finished minus body. This design is {design.fit.character}: "
                 f"{lo:g}-{hi:g} cm ({_in(lo)}-{_in(hi)} in) of positive ease at the chest.")
        cols = ["Size", "To fit chest", "Finished chest", "Ease", "Length"]
        has_arm = all(c.get("upper_arm_cm") for c in claims)
        if has_arm:
            cols.append("Upper arm")
        cols += ["Yarn"]
        rows = []
        for c in claims:
            r = [c["size"], f"{c['body_chest_cm']:g} cm / {_in(c['body_chest_cm'])} in",
                 f"{c['finished_chest_cm']:g} cm / {_in(c['finished_chest_cm'])} in",
                 f"{c['ease_cm']:+g} cm", f"{c['length_cm']:g} cm / {_in(c['length_cm'])} in"]
            if has_arm:
                r.append(f"{c['upper_arm_cm']:g} cm")
            r.append(f"{c['balls']} balls, {c['yards']} yd ({c['metres']} m)")
            rows.append(r)
        _table(doc, cols, rows)
        doc.para(f"Yardage is the pattern's own estimate from every stitch of each size, within "
                 f"±{YARDAGE_TOLERANCE:.0%} for your yarn and tension: buy one ball more than "
                 f"the chart says.", size=9.5)
        # 6. schematic
        doc.new_page(head)
        doc.heading("Schematic", kicker="Measurements for every size")
        doc.para("Drawn from the pattern's rows, to scale at the middle size. Each letter is "
                 "a measurement listed below for every size, in cm, smallest size first, the "
                 "others in parentheses.", size=9.5)
        box_h = 95 * P.mm
        doc.need(box_h + 8 * P.mm)
        drawn = SCH.draw(doc, sch, x=P.MARGIN + 6 * P.mm, top=doc.y - 4 * P.mm,
                         width=P.PAGE_W - 2 * P.MARGIN - 12 * P.mm, height=box_h,
                         font=P.FONT_UI_BOLD, size=10)
        doc.prose.extend(drawn)
        doc.y -= box_h + 8 * P.mm
        for letter, name, label in sch["legend"]:
            doc.kv(letter or "–", f"{name}: {label}", upper=False)
        doc.figures.append({"kind": "schematic", "source": "publish.garment_schematic",
                            "page": doc.pages, "labels": len(drawn),
                            "legend": len(sch["legend"])})
        # 7. tips
        doc.new_page(head)
        doc.heading("Tips", kicker="Before you start")
        for tip in TIPS:
            doc.para(f"• {tip}")
        # 8. abbreviations
        doc.heading("Abbreviations", kicker=f"{terminology} terms")
        for code in ("ch", "sc", "inc", "dec", "sk"):
            doc.kv(P.abbreviations.token(code, terminology),
                   P.abbreviations.meaning(code, terminology), upper=False)
        doc.kv("st(s)", "stitch(es)", upper=False)
        doc.kv("pm", "place marker", upper=False)
        doc.label("Special stitches")
        doc.para(f"Through the back loop: insert the hook under the back loop of the stitch "
                 f"only (the loop furthest from you) and work the {t.sc} as usual. Worked on "
                 f"every row this makes the ridged band at the hems, cuffs and edges.")
        doc.para(f"Increase ({t.inc}): work 2 {t.sc} in the same stitch. Decrease ({t.dec}): "
                 f"insert the hook in the next stitch, yarn over and pull up a loop, insert in "
                 f"the following stitch, yarn over and pull up a loop, yarn over and draw "
                 f"through all 3 loops.")
        if kind == "raglan":
            doc.para(f"Raglan increase row: *{t.sc} to 1 st before the marker, {t.inc}, slip "
                     f"the marker, {t.inc}; repeat from * 3 more times, {t.sc} to the end (8 sts "
                     f"increased). Double raglan increase row: as the increase row, but {t.inc} "
                     f"twice before and twice after each marker (16 sts increased).")
        doc.para(f"Pick up and {t.sc}: insert the hook through the edge, yarn over, pull up a "
                 f"loop and complete a {t.sc}; space the stitches evenly at the rate given.")
        doc.para(f"The turning chain ({t.ch} 1) does not count as a stitch.")
        # 9. pattern
        doc.heading("Pattern", kicker=f"Instructions ({terminology} terms)")
        doc.para("Smallest size first; the other sizes follow in parentheses in the size "
                 "chart's order. Where one number is given it applies to every size. The "
                 "stitch count at the end of each line is the count after those rows.",
                 size=9.5)
        for piece_title, lines in pattern.items():
            doc.heading(piece_title, size=14)
            for ln in lines:
                doc.para(ln.text, size=9.8)
        # 10. finishing
        doc.heading("Finishing", kicker="Seams, bands and buttons"
                    if any(f.buttons for f in facts) else "Seams and bands")
        for ln in finishing:
            doc.para(ln)
        # 11. child safety
        if safety.applies:
            doc.heading(CS.SECTION_HEADING, kicker="Child safety")
            for h, body in CS.section_lines(safety.profile):
                if body == CS.SECTION_END:
                    doc.label("This garment")
                    doc.para("It is made with no buttons, ties, cords or anything sewn on: the "
                             "bands are picked up and worked into the edges.", size=9.5)
                if h:
                    doc.label(h)
                doc.para(body, size=9.5)
        # 12. yarn and gauge
        doc.heading("Yarn and gauge", kicker="Substitution and troubleshooting")
        lo_m, hi_m = weight.metres_per_100g
        doc.para(f"Any {weight.also_called[0]} weight yarn (CYC {weight.number}) that makes "
                 f"the gauge will work. Yarns of this weight run about {lo_m:g}-{hi_m:g} m per "
                 f"100 g ({lo_m * 1.0936 / 100 * 100:.0f}-{hi_m * 1.0936:.0f} yd per 100 g); "
                 f"if yours is outside that range, swatch before you buy. Buy by length, not "
                 f"by weight: a different fibre at the same weight has a different length per "
                 f"ball.")
        doc.para("If your swatch has more stitches per 10 cm than the gauge, your garment will "
                 "come out smaller: change to a larger hook. Fewer stitches: a smaller hook. "
                 "Check the band swatch too; a band worked tighter than the body pulls the "
                 "edges in.")
        # 13. licence
        doc.heading("Terms, licence and support", kicker="Our own licence")
        for para in P.licence_paragraphs():
            if para.strip():
                doc.para(para, size=9.5)
        doc.para("Support: message us through the shop where you bought this pattern. We "
                 "answer questions about the sizes, gauge and construction written here.",
                 size=9.5)
        # 14. about
        doc.heading("About Brambleloop Studio", kicker="Who we are")
        doc.para("Brambleloop Studio publishes crochet patterns whose every stitch count is "
                 "checked by our own pattern compiler before release, in US and UK editions.",
                 size=9.5)
        return doc

    first = render(0)
    first.finish()
    doc = render(first.pages)
    pdf_bytes = doc.finish()
    text = P.extracted_text(pdf_bytes)
    out = GarmentDocument(pdf_bytes=pdf_bytes, terminology=terminology, text=text, svg=svg,
                          sections=list(doc.bookmarks), figures=list(doc.figures),
                          pattern_lines={h: [ln.text for ln in ls] for h, ls in pattern.items()},
                          piece_of={h: ls[0].piece for h, ls in pattern.items()})
    out.problems = verify(release, out)
    if out.problems:
        raise GarmentPdfRefused(f"{spec.key} {terminology}: {out.problems[:5]}")
    return out


def _table(doc, cols, rows) -> None:
    """A simple ruled table, wrapped to the column width."""
    usable = P.PAGE_W - 2 * P.MARGIN
    widths = [0.08, 0.17, 0.17, 0.08, 0.16, 0.10, 0.24][:len(cols)]
    if len(cols) == 6:
        widths = [0.09, 0.19, 0.19, 0.09, 0.18, 0.26]
    scale = usable / sum(widths)
    xs, x = [], P.MARGIN
    for w in widths:
        xs.append(x)
        x += w * scale
    size = P.MIN_BODY_PT
    line_h = size * 1.35

    def draw_row(cells, font):
        wrapped = [P._wrap(doc.c, str(c), font, size, widths[i] * scale - 4) for i, c in
                   enumerate(cells)]
        h = max(len(w) for w in wrapped) * line_h + 3
        doc.need(h + 2)
        for i, lines in enumerate(wrapped):
            for k, ln in enumerate(lines):
                doc.text(xs[i], doc.y - k * line_h, ln, font, size, P.INK)
        doc.prose.append(" | ".join(str(c) for c in cells))
        doc.y -= h
        doc.c.setStrokeColor(P.LINE)
        doc.c.setLineWidth(0.4)
        doc.c.line(P.MARGIN, doc.y + line_h - 2, P.PAGE_W - P.MARGIN, doc.y + line_h - 2)

    draw_row(cols, P.FONT_UI_BOLD)
    for r in rows:
        draw_row(r, P.FONT_BODY)
    doc.y -= 2 * P.mm


def verify(release, out: GarmentDocument) -> list[str]:
    """The document re-read: sections, pattern, size chart, schematic, child safety, glyphs."""
    from ..gates import child_safety as CS
    from ..gates import garment_fit as GFIT

    problems: list[str] = []
    for s in SECTIONS:
        if s not in out.sections:
            problems.append(f"section {s!r} is missing")
    piece_of = out.piece_of
    problems += [str(p) for p in GFIT.multi_size_problems(out.pattern_lines, release.cirs,
                                                          piece_of)]
    flat = re.sub(r"\s+", " ", out.text)
    for lines in out.pattern_lines.values():
        for ln in lines:
            if re.sub(r"\s+", " ", ln) not in flat:
                problems.append(f"a pattern line is not in the document: {ln[:60]!r}")
                break
    problems += [str(p) for p in GFIT.claim_problems(release.design, release.cirs,
                                                     release.claims)]
    for c in release.claims:
        if f"{c['yards']} yd" not in flat or f"{c['finished_chest_cm']:g} cm" not in flat:
            problems.append(f"size {c['size']}: the size chart row is not in the document")
    if "<svg" not in out.svg or "</svg>" not in out.svg:
        problems.append("the schematic SVG is empty")
    if not any(f.get("kind") == "schematic" and f.get("labels") for f in out.figures):
        problems.append("no schematic was drawn")
    cir0 = next(iter(release.cirs.values()))
    v = CS.evaluate(cir0, text=out.text)
    if v.applies:
        bad = [f"{c.code}: {c.detail}" for c in v.checks
               if c.state != CS.PASS and c.code in ("SAFETY_SECTION", "CITATIONS",
                                                     "NO_CERTIFICATION_CLAIM",
                                                     "NO_HARD_PARTS_IN_TEXT")]
        problems += bad
    return problems
