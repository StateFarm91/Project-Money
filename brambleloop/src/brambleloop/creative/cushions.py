"""ENG-PLUSH slice 2: pillow and cushion covers (D-OWNER-CORE-FAMILIES), from modelled parts.

Two constructions, both built only from pieces the compiler, the twin and `cir.assembly`
model, and both with an ENVELOPE back (no buttons, zips or ties -- no hard part, so a cover can
be washed, and nothing a child could pull off):

* `envelope_cover` -- a front panel and two back panels that overlap by ENVELOPE_OVERLAP of the
  height. Every join is measured: the upper back's top edge against the front's top edge, its
  sides against exactly the rows of the front's sides it covers (`Seam.at_round` /
  `spans_rounds` on a flat piece), and the same for the lower back.
* `applique_cover` -- the same cover with a flat appliqué face sewn onto the front. Every
  appliqué piece is a flat shaped piece in plain sc (increases and decreases at the edges),
  placed on the front by a SURFACE join: centred on a stated row, a stated number of stitches
  from the centre line, mirrored where it is a pair. `cir.assembly` checks every piece lies
  inside the front with a one-stitch margin and that a mirrored pair does not overlap itself.
  Features (eyes, nostrils) are embroidered.

Sizes are the standard pillow-form sizes (`size_truth.PILLOW_FORMS`): the cover is made to
the form's size, which is how covers are written (crochet fabric eases over the form).

Appliqué faces are ORIGINAL Brambleloop geometry in `APPLIQUES`, never a competitor's chart or
photograph. The Highland cow face is a stylised head from plain pieces; a shaggy fringe would
be a loop-stitch texture no engine models, so the forelock is a flat shaped piece and the
title may not claim "shaggy", "fluffy" or "fringe" (`creative.fallback_constructions`'s
texture refusal reads the cover titles too).
"""
from __future__ import annotations

import math
import re

from ..cir.model import CIR, Component, Material, Op, Row, Seam

ENVELOPE_OVERLAP = 0.30          # of the height: each back panel is 0.65 of it
BACK_SHARE = 0.65
# Standard pillow-form sizes (in), the cover sizes this engine drafts (size_truth.PILLOW_FORMS).
FORMS_IN: dict[str, tuple[int, int]] = {
    "square": (16, 16), "large square": (18, 18), "euro": (26, 26), "lumbar": (12, 20),
}
CM_PER_IN = 2.54


def form_for(title: str) -> tuple[str, tuple[int, int]]:
    """The pillow form a title names: lumbar words -> lumbar, euro -> euro, else 16 in square."""
    t = (title or "").lower()
    if re.search(r"\b(?:lumbar|oblong|rectangular|rectangle)\b", t):
        return "lumbar", FORMS_IN["lumbar"]
    if re.search(r"\beuro\b", t):
        return "euro", FORMS_IN["euro"]
    return "square", FORMS_IN["square"]


def _flat_rows(widths: list[int], colour: str) -> list[Row]:
    """Rows of a flat piece from its row widths (bottom up). A row grows or shrinks by 2 (one
    increase or decrease at each end) or holds; anything else is refused."""
    rows = [Row(index=1, ops=[Op("sc", widths[0])], declared_count=widths[0], turning_chain=1,
                color=colour)]
    for i, (prev, w) in enumerate(zip(widths, widths[1:]), start=2):
        if w == prev:
            ops = [Op("sc", w)]
        elif w == prev + 2:
            ops = [Op("inc"), Op("sc", prev - 2), Op("inc")]
        elif w == prev - 2 and prev >= 6:
            ops = [Op("dec"), Op("sc", prev - 4), Op("dec")]
        else:
            raise ValueError(f"row {i}: {prev} -> {w} is not one edge stitch each side")
        rows.append(Row(index=i, ops=ops, declared_count=w, turning_chain=1, color=colour))
    return rows


def _panel(name: str, sts: int, n_rows: int, colour: str, note: str) -> Component:
    return Component(name=name, construction="flat_rows", foundation=sts,
                     foundation_kind="chain", note=note,
                     rows=[Row(index=i, ops=[Op("sc", sts)], declared_count=sts,
                               turning_chain=1, color=colour) for i in range(1, n_rows + 1)])


# ---- appliqué faces: original geometry -------------------------------------------------------
#
# Each piece: row widths bottom-up, the palette slot it is worked in, where it sits on the
# front (centre row as a fraction of the front's rows, offset from the centre line in
# stitches), whether it is a mirrored pair, and the order it is sewn (earlier pieces sit under
# later ones). Features are embroidered after the pieces are sewn.
APPLIQUES: dict[str, dict] = {
    "highland cow": {
        "words": r"\bhighland\s+cow\b",
        "colours": ("background", "coat", "muzzle and horns"),
        "pieces": [
            # name, widths, slot, centre row fraction, offset sts, mirrored
            ("horn", [10, 8, 6], 2, 0.64, 14, True),
            ("ear", [4, 6, 6, 4], 1, 0.56, 12, True),
            ("face", [12, 14, 16, 16, 16, 16, 18, 18, 18, 18, 18, 18, 18, 18, 16, 14], 1,
             0.48, 0, False),
            ("forelock", [16, 18, 18, 16, 14], 1, 0.59, 0, False),
            ("muzzle", [10, 12, 14, 14, 14, 14, 12, 10], 2, 0.38, 0, False),
        ],
        "features": ("Embroider two eyes with dark yarn, 3 straight stitches over 1 st each, "
                     "on the face just below the forelock and 4 sts either side of the centre "
                     "line; embroider two nostrils on the muzzle, 2 sts either side of the "
                     "centre line"),
    },
}


def applique_for(title: str) -> str | None:
    t = (title or "").lower()
    for key, spec in APPLIQUES.items():
        if re.search(spec["words"], t):
            return key
    return None


def _materials(concept, palette, form_in) -> list[Material]:
    w, h = form_in
    return ([Material(name=f"{concept.yarn_weight} acrylic", yarn_weight=concept.yarn_weight,
                      color_id=c) for c in palette]
            + [Material(name=f"pillow form insert {w} x {h} in "
                             f"({w * CM_PER_IN:.0f} x {h * CM_PER_IN:.0f} cm), not included")])


def envelope_cover(concept, *, version: str = "1.0.0", provenance=None,
                   applique: str | None = None) -> CIR:
    """A front and an envelope back (two overlapping panels) for a standard pillow form,
    optionally with an appliqué face from `APPLIQUES`."""
    from ..creative.prototype import gauge_for

    palette = list(dict.fromkeys(concept.colors))
    if not palette:
        raise ValueError(f"{concept.slug}: a cover needs at least one colour")
    gauge = gauge_for(concept.yarn_weight)
    form_key, form_in = form_for(concept.title)
    # Lumbar is wider than tall: the long side runs across.
    across_in, up_in = (max(form_in), min(form_in)) if form_key == "lumbar" else form_in
    sts = int(round(across_in * CM_PER_IN * gauge.stitches_per_10cm / 10.0))
    n_rows = int(round(up_in * CM_PER_IN * gauge.rows_per_10cm / 10.0))
    back_rows = int(math.ceil(n_rows * BACK_SHARE))
    overlap_rows = 2 * back_rows - n_rows
    bg = palette[0]
    # Every colour the concept names is worked, never listed and unused: a plain cover works a
    # second colour as its back; an appliqué cover works its face's colours.
    wanted = len(APPLIQUES[applique]["colours"]) if applique else 2
    if len(palette) > wanted:
        raise ValueError(f"{concept.slug}: this cover works {wanted} colours; the concept names "
                         f"{len(palette)}")
    back = palette[1] if (not applique and len(palette) > 1) else bg
    components = [
        _panel("front", sts, n_rows, bg, "Worked flat from the bottom edge up."),
        _panel("upper back", sts, back_rows, back,
               "Worked flat; its foundation edge is the envelope opening, so keep that edge "
               "neat."),
        _panel("lower back", sts, back_rows, back,
               "Worked flat; its last row is the envelope opening, so finish it neatly."),
    ]
    first_upper = n_rows - back_rows + 1
    assembly: list[Seam] = []
    pieces_note = ""
    if applique:
        spec = APPLIQUES[applique]
        if len(palette) < 2:
            raise ValueError(f"{concept.slug}: the {applique} face needs at least a background "
                             f"and a coat colour ({', '.join(spec['colours'])}); the concept "
                             f"names {len(palette)}")
        for name, widths, slot, row_frac, offset, mirrored in spec["pieces"]:
            # A two-colour palette works the third slot (muzzle, horns) in the background
            # colour; every colour listed is worked.
            colour = palette[slot] if slot < len(palette) else palette[0]
            comp = Component(name=name, construction="flat_rows", foundation=widths[0],
                             foundation_kind="chain", make=2 if mirrored else 1,
                             note=(f"Appliqué piece{' (make 2)' if mirrored else ''}: fasten "
                                   f"off leaving a 40 cm tail for sewing it on."),
                             rows=_flat_rows(widths, colour))
            components.append(comp)
            centre = max(1, int(round(n_rows * row_frac)))
            assembly.append(Seam(
                "sew", name, "front", edge_a="perimeter", edge_b="surface",
                at_round=centre, spans_rounds=1, stitches_from_centre=offset,
                mirrored=mirrored,
                note=(f"Pin the {name} flat on the front, centred on row {centre}"
                      + (f" and {offset} sts from the centre line" if offset else
                         " on the centre line")
                      + (", the second one mirrored on the far side" if mirrored else "")
                      + "; sew all round its edge through both loops and the front fabric, "
                        "knot on the wrong side and bury the tail")))
        pieces_note = f" {spec['features']}."
        last = assembly[-1]
        assembly[-1] = Seam(last.method, last.piece_a, last.piece_b, edge_a=last.edge_a,
                            edge_b=last.edge_b, at_round=last.at_round,
                            spans_rounds=last.spans_rounds,
                            stitches_from_centre=last.stitches_from_centre,
                            mirrored=last.mirrored,
                            note=f"{last.note}. Then {spec['features'][0].lower()}"
                                 f"{spec['features'][1:]}")
    assembly += [
        Seam("whipstitch", "upper back", "front", edge_a="top", edge_b="top",
             note="Hold the upper back on the front, wrong sides together, top edges level, "
                  "and whipstitch the top edges"),
        Seam("whipstitch", "upper back", "front", edge_a="left", edge_b="left",
             at_round=first_upper, spans_rounds=back_rows,
             note="Whipstitch the left edges together"),
        Seam("whipstitch", "upper back", "front", edge_a="right", edge_b="right",
             at_round=first_upper, spans_rounds=back_rows,
             note="Whipstitch the right edges together"),
        Seam("whipstitch", "lower back", "front", edge_a="bottom", edge_b="bottom",
             note=(f"Lay the lower back over the upper back so they overlap by {overlap_rows} "
                   f"rows, bottom edges level with the front, and whipstitch the bottom edges")),
        Seam("whipstitch", "lower back", "front", edge_a="left", edge_b="left",
             at_round=1, spans_rounds=back_rows,
             note="Whipstitch the left edges, through all three layers where the backs overlap"),
        Seam("whipstitch", "lower back", "front", edge_a="right", edge_b="right",
             at_round=1, spans_rounds=back_rows,
             note="Whipstitch the right edges, through all three layers where the backs overlap; "
                  "turn right side out and slip the pillow form in through the envelope"),
    ]
    across_cm = sts * 10.0 / gauge.stitches_per_10cm
    up_cm = n_rows * 10.0 / gauge.rows_per_10cm
    overlap_cm = overlap_rows * 10.0 / gauge.rows_per_10cm
    kind = f"{applique} appliqué" if applique else "envelope"
    return CIR(
        slug=concept.slug, title=concept.title, version=version, construction="flat_rows",
        risk_class=getattr(concept, "risk_class", "A") or "A",
        colors=dict(concept.colors), gauge=gauge,
        materials=_materials(concept, palette, form_in),
        components=components, assembly=assembly,
        designer_notes=(f"{concept.category} concept drafted as a {kind} cushion cover for a "
                        f"{form_in[0]} x {form_in[1]} in pillow form: a {sts}-st x {n_rows}-row "
                        f"front and an envelope back of two {back_rows}-row panels overlapping "
                        f"by {overlap_rows} rows (about {overlap_cm:.0f} cm); no buttons or "
                        f"zip." + pieces_note),
        finished_size_note=(
            f"About {across_cm:.0f} x {up_cm:.0f} cm at the stated gauge, made to fit a "
            f"{form_in[0]} x {form_in[1]} in pillow form; the envelope back overlaps by "
            f"{overlap_rows} rows. Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )
