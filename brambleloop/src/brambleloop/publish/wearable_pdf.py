"""ENG-GARMENT-2: the wearable pattern PDF, every size in one document, US and UK editions.

The garment document's structure (`publish.garment_pdf`, after
`research/benchmarks/PDF_STRUCTURE_STANDARD.md`: smallest size first and the others in
parentheses, a stitch count after every row, a size chart and a schematic), for any family in
`products.wearables.ENGINES`. Every figure comes from the certified release: the instructions
from `publish.wearable_writer` (each size's recorded steps), the size chart from
`products.wearables.size_claims` (each size's twin), the schematic from the family's own
`schematic` over each size's measured build. `build` refuses an ungranted release and re-reads
its own text before returning (`gates.wearable_fit.document_problems`, `claim_problems`), and
a child's or baby's size run carries the child-safety section, whose content checks must pass
on the rendered text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import garment_pdf as GP
from . import garment_schematic as SCH
from . import pdf as P
from . import wearable_writer as WW
from .garment_writer import Terms, values

SECTIONS = GP.SECTIONS


class WearablePdfRefused(ValueError):
    pass


@dataclass
class WearableDocument:
    pdf_bytes: bytes
    terminology: str
    text: str
    svg: str
    sections: list[str] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    pattern_lines: dict = field(default_factory=dict)
    piece_of: dict = field(default_factory=dict)


def _in(cm: float) -> str:
    return f"{cm / 2.54:.1f}"


def _cm_in(v) -> str:
    return f"{v:g} cm / {_in(v)} in"


def chart_rows(eng, claims) -> tuple[list[str], list[list[str]]]:
    cols = ["Size"] + [h for _k, h in eng.chart] + ["Yarn"]
    rows = []
    for c in claims:
        r = [c["size"]]
        for k, _h in eng.chart:
            v = c[k]
            r.append(f"{v:+g} cm" if k == "ease_cm" else _cm_in(v))
        r.append(f"{c['balls']} balls, {c['yards']} yd ({c['metres']} m)")
        rows.append(r)
    return cols, rows


def skill_words(facts) -> str:
    kinds = {s.kind for f in facts for steps in f.pieces.values() for s in steps}
    parts = ["single crochet"]
    if any(f.rounds for f in facts):
        parts.append("working in joined rounds")
    if any(set(f.pieces) - set(f.rounds) for f in facts):
        parts.append("working in rows through the back loop")
    if kinds & {"dec", "section_dec", "spread_dec"}:
        parts.append("decreasing")
    if kinds & {"inc", "section_inc", "spread_inc", "raglan"}:
        parts.append("increasing")
    if "pick_up" in kinds:
        parts.append("picking up stitches")
    return "Easy: " + ", ".join(parts)


def build(release, terminology: str = "US") -> WearableDocument:
    from ..gates import child_safety as CS
    from ..products import wearables as WB

    if not release.granted:
        raise WearablePdfRefused(f"{release.spec.key} is not granted: {release.reasons()[:3]}")
    terminology = terminology.upper()
    if terminology not in P.TERMINOLOGIES:
        raise WearablePdfRefused(f"no {terminology!r} edition")
    t = Terms(terminology)
    eng = release.engine
    spec, design, cirs = release.spec, release.design, release.cirs
    sizes = list(cirs)
    cir0 = cirs[sizes[0]]
    facts = [WB.facts_of(cirs[s]) for s in sizes]
    claims = release.claims or WB.size_claims(design, cirs)
    titles = dict(eng.titles)
    pattern = WW.write(design, cirs, terminology, titles=titles)
    finishing = WW.finishing_lines(design, cirs, terminology, where=dict(eng.where),
                                   closing=eng.closing(facts) if eng.closing else None,
                                   titles=titles)
    sch = eng.schematic(sizes, [eng.measure(cirs[s]) for s in sizes])
    svg = SCH.to_svg(sch)
    weight = GP._weight(cir0)
    gauge = cir0.gauge
    safety = CS.evaluate(cir0)
    title = spec.title
    head = f"{title} · {terminology} terms"
    narrative = eng.narrative(spec, facts[0])
    table = design.table

    def render(total_pages: int):
        doc = P._Doc(title, total_pages=total_pages, author=P.COPYRIGHT_HOLDER,
                     subject=f"Crochet {eng.category_word or spec.category} pattern, sizes "
                             f"{sizes[0]}-{sizes[-1]}, {terminology} terms",
                     footer_left=f"© {P.COPYRIGHT_HOLDER} · {title}", header_right="")
        doc.new_page(None)
        doc.y -= 40
        doc.text(P.MARGIN, doc.y, P.COPYRIGHT_HOLDER.upper(), P.FONT_UI_BOLD, 11, P.ACCENT,
                 track=1.4)
        doc.y -= 30
        doc.heading(title, kicker=f"{spec.category} · {terminology} terms")
        doc.para(f"Sizes {sizes[0]} to {sizes[-1]} ({len(sizes)} sizes), graded from the "
                 f"{table.name} measurements. {narrative}")
        doc.para(P.AI_DISCLOSURE, size=9.5)
        doc.para("No sample photograph is included: this pattern has not yet been made up as a "
                 "photographed sample. Every measurement in it is computed from the pattern's "
                 "own rows and rounds at the stated gauge.", size=9.5)
        doc.new_page(head)
        doc.heading("At a glance", kicker="Overview")
        for k, v in (("Skill level", skill_words(facts)),
                     ("Sizes", ", ".join(sizes) + f" ({table.name}, {table.source_url}, read "
                                                  f"{table.retrieved})"),
                     ("Fit", eng.fit_note or "As the size chart states."),
                     ("Yarn weight", f"{weight.also_called[0]} (CYC {weight.number}, "
                                     f"{weight.key})"),
                     ("Hook", GP._hook(gauge.hook_mm)),
                     ("Construction", eng.title),
                     ("Gauge", f"{gauge.stitches_per_10cm:g} sts and {gauge.rows_per_10cm:g} "
                               f"rows = 10 cm (4 in) in {t.sc}"),
                     ("Editions", "US terms and UK terms, as two files")):
            doc.kv(k, v)
        doc.heading("Supplies", kicker="What you need")
        ball = claims[0]
        doc.kv("Yarn", f"{spec.weight} weight {spec.fibre}, about {ball['ball_m']:g} m "
                       f"({ball['ball_yd']} yd) per {ball['ball_g']} g ball")
        doc.kv("Balls, by size", values([c["balls"] for c in claims]) + " balls")
        doc.kv("Hook", GP._hook(gauge.hook_mm))
        notions = list(eng.notions)
        if any(f.buttons for f in facts):
            notions.insert(0, f"{values([f.buttons for f in facts])} buttons")
        doc.kv("Notions", "; ".join(notions))
        doc.kv("Gauge", f"{gauge.stitches_per_10cm:g} sts and {gauge.rows_per_10cm:g} rows = "
                        f"10 cm (4 in) in {t.sc}, with the hook above; the back-loop and "
                        f"round fabrics are computed at the same gauge, so check a swatch of "
                        f"each")
        doc.heading("How it is made", kicker="Construction")
        doc.para(narrative)
        doc.new_page(head)
        doc.heading("Size chart", kicker="Body and finished measurements")
        doc.para(f"Choose your size by the body measurement in the first column "
                 f"({table.name}). Finished measurements are the piece's own, computed from "
                 f"each size's rows at the stated gauge; ease is finished minus body. "
                 + (eng.fit_note or ""))
        cols, rows = chart_rows(eng, claims)
        _table(doc, cols, rows)
        doc.para(f"Yardage is the pattern's own estimate from every stitch of each size, within "
                 f"±{GP.YARDAGE_TOLERANCE:.0%} for your yarn and tension: buy one ball more "
                 f"than the chart says.", size=9.5)
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
        doc.figures.append({"kind": "schematic", "source": f"products.wearables:{eng.family}",
                            "page": doc.pages, "labels": len(drawn),
                            "legend": len(sch["legend"])})
        doc.new_page(head)
        doc.heading("Tips", kicker="Before you start")
        for tip in (GP.TIPS[0],) + tuple(eng.tips) + (GP.TIPS[-1],):
            doc.para(f"• {tip}")
        doc.heading("Abbreviations", kicker=f"{terminology} terms")
        for code in eng.abbreviations:
            doc.kv(P.abbreviations.token(code, terminology),
                   P.abbreviations.meaning(code, terminology), upper=False)
        doc.kv("st(s)", "stitch(es)", upper=False)
        doc.kv("rnd(s)", "round(s)", upper=False)
        doc.label("Special stitches")
        doc.para(f"Through the back loop: insert the hook under the back loop of the stitch "
                 f"only (the loop furthest from you) and work the {t.sc} as usual.")
        doc.para(f"Increase ({t.inc}): work 2 {t.sc} in the same stitch. Decrease ({t.dec}): "
                 f"insert the hook in the next stitch, yarn over and pull up a loop, insert in "
                 f"the following stitch, yarn over and pull up a loop, yarn over and draw "
                 f"through all 3 loops.")
        doc.para(f"Joined rounds: at the end of every round join with a {t.slst} to the first "
                 f"stitch, then {t.ch} 1 (it does not count as a stitch) and begin the next "
                 f"round in the same stitch as the join.")
        doc.para(f"The turning chain ({t.ch} 1) of a row does not count as a stitch.")
        doc.heading("Pattern", kicker=f"Instructions ({terminology} terms)")
        doc.para("Smallest size first; the other sizes follow in parentheses in the size "
                 "chart's order. Where one number is given it applies to every size. The "
                 "stitch count at the end of each line is the count after those rows or "
                 "rounds.", size=9.5)
        for piece_title, lines in pattern.items():
            doc.heading(piece_title, size=14)
            for ln in lines:
                doc.para(ln.text, size=9.8)
        doc.heading("Finishing", kicker="Seams and edges")
        for ln in finishing:
            doc.para(ln)
        if safety.applies:
            doc.heading(CS.SECTION_HEADING, kicker="Child safety")
            for h, body in CS.section_lines(safety.profile):
                if body == CS.SECTION_END:
                    doc.label(f"This {eng.category_word or 'piece'}")
                    doc.para(eng.safety_note, size=9.5)
                if h:
                    doc.label(h)
                doc.para(body, size=9.5)
        doc.heading("Yarn and gauge", kicker="Substitution and troubleshooting")
        lo_m, hi_m = weight.metres_per_100g
        doc.para(f"Any {weight.also_called[0]} weight yarn (CYC {weight.number}) that makes "
                 f"the gauge will work. Yarns of this weight run about {lo_m:g}-{hi_m:g} m per "
                 f"100 g; if yours is outside that range, swatch before you buy. Buy by "
                 f"length, not by weight.")
        doc.para("If your swatch has more stitches per 10 cm than the gauge, your piece will "
                 "come out smaller: change to a larger hook. Fewer stitches: a smaller hook.")
        doc.heading("Terms, licence and support", kicker="Our own licence")
        for para in P.licence_paragraphs():
            if para.strip():
                doc.para(para, size=9.5)
        doc.para("Support: message us through the shop where you bought this pattern. We "
                 "answer questions about the sizes, gauge and construction written here.",
                 size=9.5)
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
    names = {**WW.GW.PIECE_TITLES, **WW.PIECE_TITLES, **titles}
    inv = {}
    for piece in facts[0].pieces:
        inv[names.get(piece, piece.replace("_", " ").capitalize())] = piece
    out = WearableDocument(pdf_bytes=pdf_bytes, terminology=terminology, text=text, svg=svg,
                           sections=list(doc.bookmarks), figures=list(doc.figures),
                           pattern_lines={h: [ln.text for ln in ls]
                                          for h, ls in pattern.items()},
                           piece_of={h: inv[h] for h in pattern})
    out.problems = verify(release, out)
    if out.problems:
        raise WearablePdfRefused(f"{spec.key} {terminology}: {out.problems[:5]}")
    return out


def _table(doc, cols, rows) -> None:
    usable = P.PAGE_W - 2 * P.MARGIN
    n = len(cols)
    widths = [0.09] + [0.75 / (n - 2)] * (n - 2) + [0.22]
    scale = usable / sum(widths)
    xs, x = [], P.MARGIN
    for w in widths:
        xs.append(x)
        x += w * scale
    size = P.MIN_BODY_PT
    line_h = size * 1.35

    def draw_row(cells, font):
        wrapped = [P._wrap(doc.c, str(c), font, size, widths[i] * scale - 4)
                   for i, c in enumerate(cells)]
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


def verify(release, out: WearableDocument) -> list[str]:
    """The document re-read: sections, pattern per size, size chart, schematic, safety."""
    from ..gates import child_safety as CS
    from ..gates import wearable_fit as WF

    problems: list[str] = [f"section {s!r} is missing" for s in SECTIONS
                           if s not in out.sections]
    problems += [str(p) for p in WF.document_problems(out.pattern_lines, release.cirs,
                                                      out.piece_of)]
    flat = re.sub(r"\s+", " ", out.text)
    for lines in out.pattern_lines.values():
        for ln in lines:
            if re.sub(r"\s+", " ", ln) not in flat:
                problems.append(f"a pattern line is not in the document: {ln[:60]!r}")
                break
    problems += [str(p) for p in WF.claim_problems(release.design, release.cirs,
                                                   release.claims)]
    eng = release.engine
    for c in release.claims:
        if f"{c['yards']} yd" not in flat:
            problems.append(f"size {c['size']}: the size chart row is not in the document")
        for k, _h in eng.chart:
            if k != "ease_cm" and f"{c[k]:g} cm" not in flat:
                problems.append(f"size {c['size']}: {k} {c[k]:g} cm is not in the document")
    if "<svg" not in out.svg or "</svg>" not in out.svg:
        problems.append("the schematic SVG is empty")
    if not any(f.get("kind") == "schematic" and f.get("labels") for f in out.figures):
        problems.append("no schematic was drawn")
    v = CS.evaluate(next(iter(release.cirs.values())), text=out.text)
    if v.applies:
        problems += [f"{c.code}: {c.detail}" for c in v.checks
                     if c.state != CS.PASS and c.code in ("SAFETY_SECTION", "CITATIONS",
                                                          "NO_CERTIFICATION_CLAIM",
                                                          "NO_HARD_PARTS_IN_TEXT")]
    return problems
