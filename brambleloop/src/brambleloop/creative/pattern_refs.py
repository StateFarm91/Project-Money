"""Deterministic product references from the certified pattern (W4-FLUXAPI; D-W4-LAURA-FLUX3 rule 2).

FLUX takes images, not PDFs. So each certified release is turned into three PNG references,
rendered from the exact compiled CIR. No model is involved and they are free:

  (4) `layout`  the complete product: every component, each drawn `make` times, at one shared
                scale in its true finished proportion (the digital twin's centimetres), in its
                own colours. Flat pieces come from `charts.render_fabric`, round-worked pieces
                from `charts.render_round_fabric`. No text: words in a reference are words the
                model may copy into the photograph.
  (5) `detail`  stitch and construction detail. Per distinct component, an enlarged chart
                (flat: two horizontal repeats by up to 24 rows, with glyphs and row numbers;
                round: the round chart), plus the stitch/colour legend.
  (6) `rules`   the technical rules a render must not contradict: identity, version and
                release, components and piece count, finished size (and garment measures where
                the CIR is graded), gauge, yarns and exact colours, stitches, repeat, assembly,
                and the prohibited additions.

Category adapts from the data rather than from a label. A multi-piece product shows every
component. A graded garment adds its size and built measures; front and back are shown
separately only where the CIR models them as separate components (the data must support it).

Every file is fingerprinted (sha256) and the set is bound to the release hash
(`runtime.release._content_hash_of`, the hash `gates.certificate.certify` names). A release
hash or version for different content is refused. Each reference is kept inside FLUX 3's
documented input bounds (at least 256 x 256, at most 16 MP). The same CIR always gives the same
bytes.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

VERSION = "pattern-refs/3.0.0"
# Texture before the symbolic chart: it has priority (owner directive after the reading-nook
# test); the chart is kept for stitch placement.
ROLES: tuple[str, ...] = ("layout", "texture", "detail", "rules")
MIN_SIDE_PX = 256                      # FLUX 3: smaller than 256 x 256 is HTTP 422
MAX_PIXELS = 16 * 1_048_576            # FLUX 3: larger than 16 MP is HTTP 400
CANVAS_PX = 1800
MAX_COPIES_DRAWN = 6
BACKGROUND = (232, 232, 232)

# What no render of a certified product may add. Applies to every product; a component, colour
# or motif the CIR has is never in this list because the CIR is what is allowed.
PROHIBITED_ADDITIONS: tuple[str, ...] = (
    "colours not in the certified palette", "motifs, appliques or embroidery",
    "borders, edgings, fringe, tassels or pom-poms not in the pattern",
    "extra or missing pieces", "a different stitch, texture or construction",
    "knit, woven or printed fabric", "text, logos, labels or watermarks",
)


class PatternRefsRefused(ValueError):
    """The references cannot be built honestly for this CIR and release."""


@dataclass(frozen=True)
class PatternRef:
    role: str
    path: str
    sha256: str
    width: int
    height: int

    def to_dict(self) -> dict:
        return {"role": self.role, "path": self.path, "sha256": self.sha256,
                "width": self.width, "height": self.height}


def release_hash_of(cir) -> str:
    """The content hash certification names for this CIR (US text, F-078)."""
    from ..runtime.release import _content_hash_of

    return _content_hash_of(cir)


def _png_bytes(image) -> bytes:
    """PNG with no metadata, so equal pixels give equal bytes."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _within_bounds(image):
    """Scale an image down until it is at most 16 MP. Refuse one whose short side is under 256."""
    from PIL import Image

    w, h = image.size
    if w * h > MAX_PIXELS:
        f = (MAX_PIXELS / float(w * h)) ** 0.5
        image = image.resize((max(1, int(w * f)), max(1, int(h * f))), Image.LANCZOS)
    if min(image.size) < MIN_SIDE_PX:
        f = MIN_SIDE_PX / float(min(image.size))
        image = image.resize((int(round(image.size[0] * f)), int(round(image.size[1] * f))),
                             Image.NEAREST)
    return image


def _components(cir):
    """(component, twin, is_round) for every component, compiled once."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..publish import charts

    result = compile_cir(cir)
    if not result.ok:
        raise PatternRefsRefused("the CIR does not compile; no references from a broken pattern")
    out = []
    for comp in cir.components:
        twin = build_twin(cir, result, component=comp.name)
        if not twin.chart_grid():
            raise PatternRefsRefused(f"{comp.name}: the twin has no cells to draw")
        out.append((comp, twin, charts.is_round(cir, twin)))
    return out


def _grid_dims(twin) -> tuple[int, int]:
    g = twin.chart_grid()
    return max((len(r) for r in g), default=0), len(g)


def _rows_of(twin) -> list[list]:
    by: dict[int, list] = {}
    for c in twin.cells:
        by.setdefault(c.row, []).append(c)
    return [sorted(by[r], key=lambda c: c.fabric_position) for r in sorted(by)]


def _sig(row) -> tuple:
    return (frozenset(c.stitch for c in row), frozenset(c.color for c in row),
            frozenset(getattr(c, "loop", "both") for c in row))


def _runs(seq) -> list[tuple[object, int]]:
    out: list[tuple[object, int]] = []
    for x in seq:
        if out and out[-1][0] == x:
            out[-1] = (x, out[-1][1] + 1)
        else:
            out.append((x, 1))
    return out


def fabric_facts(cir, parts=None) -> dict:
    """What the fabric is, read from the twin's cells, and what a render therefore must not add.

    Derived, never declared by hand: end bands, edging, ribbing, cable/motif count and spacing,
    and the rows where colour changes. Each fact yields an explicit negative for the prompt
    (D-W4-LAURA-FLUX3 owner directive after the reading-nook-cable-wrap test)."""
    from ..cir import stitches as taxonomy

    parts = parts if parts is not None else _components(cir)
    comp, twin, is_round = max(parts, key=lambda p: _grid_dims(p[1])[0] * _grid_dims(p[1])[1])
    rows = _rows_of(twin)
    unit = "round" if is_round else "row"
    colours = dict(cir.colors)
    loops = {getattr(c, "loop", "both") for c in twin.cells}
    used = {c.stitch for c in twin.cells}
    ribbing = bool(loops - {"both"}) or {"fpdc", "bpdc"} <= used
    named = " ".join([c.name for c in cir.components]
                     + [str(a) for a in (cir.to_dict().get("assembly") or [])]).lower()
    edging = any(w in named for w in ("edging", "border", "trim", "fringe"))

    def band(seq, from_top: bool):
        if len(seq) < 3 or is_round:
            return None
        first = _sig(seq[0])
        n = next((i for i, r in enumerate(seq) if _sig(r) != first), len(seq))
        stitches_, colours_, _ = first
        if n >= len(seq) or len(stitches_) != 1 or len(colours_) != 1:
            return None
        total = len(seq)
        lo, hi = (total - n + 1, total) if from_top else (1, n)
        st, col = next(iter(stitches_)), next(iter(colours_))
        return {"rows": [lo, hi], "stitch": st, "colour": col, "hex": colours.get(col),
                "plain": True}

    bands = [b for b in (band(rows, False), band(list(reversed(rows)), True)) if b]
    cables = None
    cable_rows = [i + 1 for i, r in enumerate(rows)
                  if any(c.stitch.startswith(taxonomy.CABLE_PREFIX) for c in r)]
    if cable_rows:
        row = rows[cable_rows[0] - 1]
        runs = _runs([c.stitch for c in row])
        code = next(c.stitch for c in row if c.stitch.startswith(taxonomy.CABLE_PREFIX))
        st = taxonomy.get(code)
        groups = sum(n // max(1, st.consumes) for x, n in runs if x == code)
        between = sorted({n for i, (x, n) in enumerate(runs)
                          if x != code and 0 < i < len(runs) - 1})
        sep_stitch = sorted({x for x, _ in runs if x != code})
        gaps = sorted({b - a for a, b in zip(cable_rows, cable_rows[1:])})
        cables = {"stitch": code, "columns": groups, "crossing_over": st.consumes // 2,
                  "crossing_side": st.crossing, "separated_by": between,
                  "separator_stitch": sep_stitch,
                  "edge_stitches": [runs[0][1] if runs[0][0] != code else 0,
                                    runs[-1][1] if runs[-1][0] != code else 0],
                  "every_n_rows": gaps, "first_row": cable_rows[0],
                  "last_row": cable_rows[-1], "rows_with_crossings": len(cable_rows)}
    changes = [i + 1 for i in range(1, len(rows))
               if {c.color for c in rows[i]} != {c.color for c in rows[i - 1]}]
    return {"component": comp.name, "unit": unit, "rows": len(rows), "craft": "crochet",
            "stitches": sorted(used), "ribbing_declared": ribbing,
            "edging_declared": edging, "end_bands": bands, "cables": cables,
            "colour_change_rows": changes}


def negatives(facts: dict) -> list[str]:
    """The explicit prohibitions a render of this fabric needs, from its facts."""
    out = ["knitting of any kind: this is crochet (no knit V-columns, no stockinette, no "
           "purl ridges, no knitted rope cables)"]
    if not facts["ribbing_declared"]:
        out.append("ribbing anywhere (the pattern has none)")
    if not facts["edging_declared"]:
        out.append("an edging, border, rib, fringe or trim along any edge; "
                   + ("the outer edge is the last round exactly as charted"
                      if facts["unit"] == "round" else
                      "the edges are the plain ends of the rows"))
    for b in facts["end_bands"]:
        out.append(f"any end-band treatment other than exactly {facts['unit']}s "
                   f"{b['rows'][0]}-{b['rows'][1]}: plain {b['colour']}"
                   f"{(' ' + b['hex']) if b['hex'] else ''} {b['stitch']}, solid, no stripe, "
                   f"no ribbing, no contrast {facts['unit']}")
    c = facts.get("cables")
    if c:
        sep = "/".join(str(n) for n in c["separated_by"]) or "0"
        every = "/".join(str(n) for n in c["every_n_rows"]) or "1"
        out.append(f"any cable count or spacing other than exactly {c['columns']} cable "
                   f"columns, each a {c['crossing_over']}-over-{c['crossing_over']} crochet "
                   f"crossing of {', '.join(c['separator_stitch']) or 'post'} stitches, "
                   f"separated by {sep} {', '.join(c['separator_stitch'])}, with "
                   f"{c['edge_stitches'][0]} and {c['edge_stitches'][1]} stitches at the "
                   f"edges, crossing every {every} {facts['unit']}s")
    ch = facts["colour_change_rows"]
    if ch:
        gaps = {b - a for a, b in zip(ch, ch[1:])}
        where = (f"every {gaps.pop()} {facts['unit']}s from {facts['unit']} {ch[0]} to "
                 f"{ch[-1]}" if len(ch) > 3 and len(gaps) == 1 else
                 f"{facts['unit']}s " + ", ".join(str(r) for r in ch))
        out.append(f"colour changes anywhere except {where}")
    return out


def technical_rules(cir, parts=None, *, release_hash: str) -> dict:
    """The certified facts, structured. They go on the rules sheet and into the prompt."""
    from ..publish import charts

    parts = parts if parts is not None else _components(cir)
    letters = charts.color_letters(cir)
    stitches: set[str] = set()
    components = []
    for comp, twin, is_round in parts:
        across, rows = _grid_dims(twin)
        stitches |= set(twin.stitch_types_used)
        components.append({
            "name": comp.name, "make": int(getattr(comp, "make", 1) or 1),
            "construction": comp.construction or cir.construction,
            "worked": "in rounds" if is_round else "in flat rows",
            "stitches_across": across, "rows": rows,
            "width_cm": round(twin.width_cm, 1) if twin.width_cm else None,
            "height_cm": round(twin.height_cm, 1) if twin.height_cm else None,
            "shape": twin.shape or twin.outline})
    main = max(parts, key=lambda p: _grid_dims(p[1])[0] * _grid_dims(p[1])[1])
    grid, colors = main[1].chart_grid(), main[1].color_grid()
    col_p, row_p = charts.detect_repeat(grid, colors)
    yarn_m: dict[str, float] = {}
    for comp, twin, _ in parts:
        make = int(getattr(comp, "make", 1) or 1)
        for k, v in twin.yarn_metres_by_color.items():
            yarn_m[k] = yarn_m.get(k, 0.0) + v * make
    colours = []
    for cid, hexval in cir.colors.items():
        mat = next((m for m in cir.materials if m.color_id == cid), None)
        colours.append({"id": cid, "hex": hexval, "letter": letters.get(cid, "?"),
                        "yarn": mat.name if mat else "", "weight": (mat.yarn_weight
                                                                     if mat else None),
                        "metres": round(yarn_m[cid]) if cid in yarn_m else None})
    if not cir.colors:
        mat = cir.materials[0] if cir.materials else None
        colours.append({"id": "main", "hex": None, "letter": "A",
                        "yarn": mat.name if mat else "", "weight": mat.yarn_weight
                        if mat else None, "metres": None})
    g = cir.gauge
    garment = None
    if getattr(cir, "grading", None):
        try:
            from ..products.garments import built_measures

            garment = {"size": (cir.grading.size if hasattr(cir.grading, "size")
                                else cir.to_dict()["grading"].get("size")),
                       "measures_cm": built_measures(cir)}
        except Exception:  # noqa: BLE001 - measures unavailable: say so, never invent
            garment = {"size": None, "measures_cm": None}
    assembly = []
    for step in cir.to_dict().get("assembly") or []:
        assembly.append(f"{step.get('method')}: {step.get('piece_a')} to "
                        f"{step.get('piece_b')} - {step.get('note') or ''}".strip(" -"))
    return {
        "slug": cir.slug, "version": cir.version, "title": cir.title,
        "release_hash": release_hash, "construction": cir.construction,
        "components": components, "piece_count": sum(c["make"] for c in components),
        "gauge": {"stitches_per_10cm": g.stitches_per_10cm, "rows_per_10cm": g.rows_per_10cm,
                  "stitch": g.stitch_type, "hook_mm": g.hook_mm},
        "colours": colours, "stitches": sorted(stitches),
        "repeat": {"component": main[0].name, "stitches": col_p, "rows": row_p},
        "finished_size_note": cir.finished_size_note, "garment": garment,
        "assembly": assembly, "prohibited_additions": list(PROHIBITED_ADDITIONS),
        "fabric": (facts := fabric_facts(cir, parts)), "negatives": negatives(facts),
    }


def _render_layout(cir, parts):
    """Every component, drawn `make` times, at one px-per-cm, on a plain ground. No text."""
    from PIL import Image

    from ..publish import charts

    drawn = []
    for comp, twin, is_round in parts:
        img = (charts.render_round_fabric(cir, twin) if is_round
               else charts.render_fabric(cir, twin, cell_px=12))
        copies = min(int(getattr(comp, "make", 1) or 1), MAX_COPIES_DRAWN)
        drawn.append((img, twin, copies, is_round))
    gap = 40
    have_cm = all(t.width_cm and t.height_cm for _, t, _, _ in drawn)

    def target(img, t, rnd, ppc):
        # A round piece is drawn as a schematic of concentric rounds; its "width x height" is
        # across-points x across-flats for a polygon, not a bounding box, so it is scaled
        # uniformly to its width rather than stretched into an ellipse.
        w = max(1, round(float(t.width_cm) * ppc))
        if rnd:
            return w, max(1, round(img.size[1] * w / float(img.size[0])))
        return w, max(1, round(float(t.height_cm) * ppc))

    if have_cm:
        total_w = sum(float(t.width_cm) * n for _, t, n, _ in drawn)
        tall = max(float(t.height_cm) for _, t, _, _ in drawn)
        gaps = gap * (sum(n for _, _, n, _ in drawn) + 1)
        ppc = min((CANVAS_PX - gaps) / total_w, (CANVAS_PX - 2 * gap) / tall)
        sized = [(img.resize(target(img, t, rnd, ppc), Image.NEAREST), n)
                 for img, t, n, rnd in drawn]
        basis = "digital twin centimetres, one shared scale"
    else:
        sized = [(img, n) for img, _, n, _ in drawn]
        basis = "chart cells (the twin gives no finished size)"
    width = gap + sum((im.size[0] + gap) * n for im, n in sized)
    height = 2 * gap + max(im.size[1] for im, _ in sized)
    canvas = Image.new("RGB", (width, height), BACKGROUND)
    x = gap
    for im, n in sized:
        for _ in range(n):
            canvas.paste(im.convert("RGB"), (x, gap + (height - 2 * gap - im.size[1]) // 2))
            x += im.size[0] + gap
    return canvas, basis


def _stack(images, *, pad: int = 24):
    from PIL import Image

    width = max(im.size[0] for im in images) + 2 * pad
    height = sum(im.size[1] for im in images) + pad * (len(images) + 1)
    out = Image.new("RGB", (width, height), (255, 255, 255))
    y = pad
    for im in images:
        out.paste(im.convert("RGB"), ((width - im.size[0]) // 2, y))
        y += im.size[1] + pad
    return out


def _render_detail(cir, parts):
    """Enlarged stitch placement per distinct component, then the legend."""
    from ..publish import charts

    tiles = []
    for comp, twin, is_round in parts:
        if is_round:
            tiles.append(charts.render_round_chart(
                cir, twin, charts.ChartSpec(max_width_px=1400),
                caption=f"{comp.name}: worked in rounds; full chart"))
            continue
        grid, colors = twin.chart_grid(), twin.color_grid()
        cp, rp = charts.detect_repeat(grid, colors)
        across, rows = _grid_dims(twin)
        mc = max(1, min(across, max(cp * 2, min(across, 12))))
        mr = max(1, min(rows, rp if rp < rows else 24, 30))
        tiles.append(charts.render_chart(
            cir, twin, charts.ChartSpec(cell_px=44, margin_px=56, max_width_px=1800),
            grids=charts.crop_grids(grid, colors, mc, mr),
            caption=(f"{comp.name}: {mc} stitches x {mr} rows from the bottom-left corner "
                     f"(repeat {cp} sts); enlarged")))
    main = max(parts, key=lambda p: _grid_dims(p[1])[0] * _grid_dims(p[1])[1])
    tiles.append(charts.render_legend(cir, main[1]))
    return _stack(tiles)


def _render_rules(rules: dict):
    from PIL import Image, ImageDraw

    from ..publish import charts

    width = 1500
    title_f, head_f, body_f = charts._font(40), charts._font(26), charts._font(22)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines: list[tuple[str, object, tuple | None]] = []

    def text(t, font=body_f, swatch=None):
        for i, part in enumerate(charts._wrap(probe, t, font, width - 160) or [""]):
            lines.append((part, font, swatch if i == 0 else None))

    text(rules["title"], title_f)
    text(f"{rules['slug']}@{rules['version']}   release {rules['release_hash'][:16]}")
    text("")
    text("PIECES (left to right in the layout reference)", head_f)
    for c in rules["components"]:
        size = (f"{c['width_cm']} x {c['height_cm']} cm" if c["width_cm"] and c["height_cm"]
                else "size UNKNOWN")
        text(f"{c['name']} x{c['make']}: worked {c['worked']}, {c['stitches_across']} sts "
             f"x {c['rows']} rows, {size}" + (f", {c['shape']}" if c["shape"] else ""))
    text(f"Total pieces: {rules['piece_count']}")
    if rules.get("garment"):
        gm = rules["garment"]
        text(f"Garment size {gm.get('size') or 'UNKNOWN'}; built measures (cm): "
             f"{gm.get('measures_cm') or 'UNKNOWN'}")
    if rules.get("finished_size_note"):
        text(rules["finished_size_note"])
    g = rules["gauge"]
    text(f"Gauge: {g['stitches_per_10cm']} sts x {g['rows_per_10cm']} rows per 10 cm in "
         f"{g['stitch']}; hook {g['hook_mm']} mm")
    r = rules["repeat"]
    main = next(c for c in rules["components"] if c["name"] == r["component"])
    if r["stitches"] >= main["stitches_across"] and r["rows"] >= main["rows"]:
        text(f"Repeat ({r['component']}): none; the whole piece is one pattern")
    else:
        text(f"Repeat ({r['component']}): {r['stitches']} sts x {r['rows']} rows")
    text(f"Stitches used: {', '.join(rules['stitches'])}")
    text("")
    text("COLOURS AND YARN (exact)", head_f)
    for c in rules["colours"]:
        text(f"{c['letter']}  {c['id']}  {c['hex'] or ''}  {c['yarn']}, {c['weight']}  "
             f"{('~' + str(c['metres']) + ' m') if c['metres'] else 'metres UNKNOWN'}",
             swatch=charts._hex_to_rgb(c["hex"]) if c["hex"] else None)
    if rules["assembly"]:
        text("")
        text("ASSEMBLY", head_f)
        for a in rules["assembly"]:
            text("- " + a)
    text("")
    text("NEVER ADD", head_f)
    for p in rules["prohibited_additions"]:
        text("- " + p)
    text("")
    text("THIS FABRIC: NEVER", head_f)
    for n in rules.get("negatives") or []:
        text("- " + n)
    height = 80 + 38 * len(lines)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 40
    for t, font, swatch in lines:
        x = 48
        if swatch is not None:
            draw.rectangle((48, y + 2, 92, y + 30), fill=swatch, outline=(0, 0, 0))
            x = 108
        draw.text((x, y), t, fill=(20, 20, 20), font=font)
        y += 38
    return img


def build(cir, *, release_hash: str, out_dir: str | Path, version: str | None = None) -> dict:
    """Render, bound-check and fingerprint references 4/5/6 for `cir`, bound to `release_hash`.

    Refused when `release_hash` is not this CIR's content hash, when `version` is given and is
    not the CIR's version, or when the pattern does not compile."""
    if not release_hash:
        raise PatternRefsRefused("a release hash is required: references bind to a release")
    if version is not None and str(version) != str(cir.version):
        raise PatternRefsRefused(f"version {version} was asked for, but this CIR is "
                                 f"{cir.slug}@{cir.version}; references come only from the "
                                 f"exact certified version")
    actual = release_hash_of(cir)
    if actual != release_hash:
        raise PatternRefsRefused(
            f"release {release_hash[:16]} is not this CIR's content ({actual[:16]}); "
            f"references for different content would condition a render on another product")
    parts = _components(cir)
    rules = technical_rules(cir, parts, release_hash=release_hash)
    layout, basis = _render_layout(cir, parts)
    from . import stitch_texture

    main = max(parts, key=lambda p: _grid_dims(p[1])[0] * _grid_dims(p[1])[1])
    texture, region = stitch_texture.render(cir, main[1])
    detail = _render_detail(cir, parts)
    sheet = _render_rules(rules)

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    refs: list[PatternRef] = []
    for role, image in (("layout", layout), ("texture", texture), ("detail", detail),
                        ("rules", sheet)):
        image = _within_bounds(image)
        raw = _png_bytes(image)
        path = root / f"{cir.slug}-{release_hash[:12]}-{role}.png"
        path.write_bytes(raw)
        refs.append(PatternRef(role, str(path), hashlib.sha256(raw).hexdigest(),
                               image.size[0], image.size[1]))
    texture_info = {"component": region.component,
                    "rows": [region.first_row, region.last_row],
                    "columns": [region.first_col, region.last_col],
                    "stitches_drawn": list(region.stitches),
                    "crossing_side": region.crossing_side or None,
                    "basis": "drawn from cir.stitches definitions and the twin's cells"}
    main = rules["components"][0] if len(rules["components"]) == 1 else None
    category = ("garment" if rules.get("garment") else
                "multi_piece" if len(rules["components"]) > 1 or rules["piece_count"] > 1
                else "round" if parts[0][2] else "flat")
    manifest = {
        "version": VERSION, "slug": cir.slug, "cir_version": cir.version,
        "release_hash": release_hash, "category": category,
        "layout_aspect_basis": basis,
        "grid": ({"stitches_across": main["stitches_across"], "rows": main["rows"],
                  "repeat": [rules["repeat"]["stitches"], rules["repeat"]["rows"]]}
                 if main else None),
        "technical_rules": rules, "texture": texture_info,
        "references": [r.to_dict() for r in refs],
        "cost_cad": 0.0, "basis": "deterministic render of the compiled CIR; no model",
    }
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(
        {k: v for k, v in manifest.items() if k != "references"}
        | {"references": [{"role": r.role, "sha256": r.sha256} for r in refs]},
        sort_keys=True, default=str).encode()).hexdigest()
    (root / f"{cir.slug}-{release_hash[:12]}-pattern-refs.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True, default=str) + "\n")
    return manifest


def verify(manifest: dict) -> dict:
    """Recheck every reference file's bytes against the manifest. Offline."""
    problems = []
    for r in manifest.get("references") or []:
        p = Path(str(r.get("path") or ""))
        if not p.is_file():
            problems.append(f"{r.get('role')}: missing")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != r.get("sha256"):
            problems.append(f"{r.get('role')}: bytes changed")
    if sorted(r.get("role") for r in manifest.get("references") or []) != sorted(ROLES):
        problems.append("roles incomplete")
    return {"ok": not problems, "problems": problems}
