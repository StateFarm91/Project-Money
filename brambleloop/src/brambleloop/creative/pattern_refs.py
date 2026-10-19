"""Deterministic pattern-derived conditioning references (W4-FLUXAPI, autonomous step 2).

An image model asked to draw "the Cloudline blanket" draws *a* blanket. What makes a render
show *this* product is conditioning it on pictures of the product's own truth, and those
pictures need no model at all: the CIR already says, stitch by stitch, what the fabric is.
So this renders three PNGs from a certified CIR, deterministically, for free:

  (a) `layout`        the full stitch/colour layout, one cell per stitch (99 x 100 for
                      Cloudline), drawn by `publish.charts.render_fabric`;
  (b) `motif`         the smallest repeating block, enlarged, with stitch glyphs and row
                      numbers -- stitch placement a model can read (`render_chart`);
  (c) `construction`  a sheet of the facts a render must not contradict: finished size,
                      stitch and row counts, gauge, hook, yarns with their exact colours,
                      the repeat, and the constraints.

Every file is fingerprinted (sha256) and the set is bound to the release hash -- the content
hash `gates.certificate.certify` names (`runtime.release._content_hash_of`). A caller that
passes a release hash for different content is refused: a reference pack that drifted from
the certified pattern would condition a render on a product that is not for sale.

No generation, no network, no spend. The same CIR always yields the same bytes.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

VERSION = "pattern-refs/1.0.0"
ROLES: tuple[str, ...] = ("layout", "motif", "construction")


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
    """PNG with no metadata, so equal pixels are equal bytes."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _motif_block(grid, colors, col_period: int, row_period: int) -> tuple[int, int]:
    """How much of the chart the enlargement shows: two horizontal repeats (so the join is
    visible) and enough rows to show the vertical motif, capped so cells stay large."""
    cols = max((len(r) for r in grid), default=0)
    rows = len(grid)
    want_cols = min(cols, max(col_period * 2, min(cols, 12)))
    want_rows = min(rows, row_period if row_period < rows else 24)
    return max(1, want_cols), max(1, min(want_rows, 30))


def _construction_sheet(cir, twin, *, release_hash: str, col_period: int, row_period: int,
                        stitches_across: int, rows_total: int):
    from PIL import Image, ImageDraw

    from ..publish import charts

    width = 1400
    title_f, head_f, body_f = charts._font(40), charts._font(26), charts._font(22)
    lines: list[tuple[str, object]] = []
    g = cir.gauge
    size = (f"{twin.width_cm:.1f} x {twin.height_cm:.1f} cm"
            if twin.width_cm and twin.height_cm else "UNKNOWN (twin gives no size)")
    lines += [("CONSTRUCTION", head_f),
              (f"{cir.construction}; {len(cir.components)} component(s): "
               f"{', '.join(c.name for c in cir.components)}", body_f),
              (f"Finished size (digital twin): {size}", body_f),
              (f"Stitches across: {stitches_across}    Rows: {rows_total}", body_f),
              (f"Gauge: {g.stitches_per_10cm} sts x {g.rows_per_10cm} rows per 10 cm in "
               f"{g.stitch_type}; hook {g.hook_mm} mm", body_f),
              (f"Repeat: {col_period} stitch(es) x {row_period} row(s)"
               + ("  (no vertical repeat: the motif runs the full height)"
                  if row_period >= rows_total else ""), body_f),
              ("", body_f), ("COLOURS AND YARN", head_f)]
    letters = charts.color_letters(cir)
    swatch_rows = []
    for color_id, hexval in cir.colors.items():
        mat = next((m for m in cir.materials if m.color_id == color_id), None)
        metres = twin.yarn_metres_by_color.get(color_id)
        swatch_rows.append((color_id, hexval, letters.get(color_id, "?"),
                            f"{letters.get(color_id, '?')}  {color_id}  {hexval}  "
                            f"{(mat.name + ', ' + str(mat.yarn_weight)) if mat else ''}  "
                            f"{f'~{metres:.0f} m' if metres else 'metres UNKNOWN'}"))
    constraints = [
        "Render exactly this colour layout: no added colours, motifs, borders or fringe.",
        f"Proportion: {stitches_across} stitches across to {rows_total} rows"
        + (f" ({twin.width_cm:.1f} cm by {twin.height_cm:.1f} cm)" if twin.width_cm and
           twin.height_cm else "") + "; do not stretch.",
        f"Fabric is {g.stitch_type} crochet texture; not knit, not woven, not printed.",
        "This sheet, the layout and the motif are the product truth; the prompt is not.",
    ]
    header = [(cir.title, title_f),
              (f"{cir.slug}@{cir.version}   release {release_hash[:16]}", body_f), ("", body_f)]
    height = 90 + 40 * (len(header) + len(lines) + len(swatch_rows) + len(constraints) + 3)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 40
    for text, font in header + lines:
        draw.text((48, y), text, fill=(20, 20, 20), font=font)
        y += 40
    for color_id, hexval, _letter, text in swatch_rows:
        rgb = charts._hex_to_rgb(hexval)
        draw.rectangle((48, y + 2, 96, y + 32), fill=rgb, outline=(0, 0, 0))
        draw.text((112, y + 2), text, fill=(20, 20, 20), font=body_f)
        y += 40
    y += 20
    draw.text((48, y), "CONSTRAINTS", fill=(20, 20, 20), font=head_f)
    y += 40
    for c in constraints:
        draw.text((48, y), "- " + c, fill=(20, 20, 20), font=body_f)
        y += 40
    return img


def build(cir, *, release_hash: str, out_dir: str | Path) -> dict:
    """Render and fingerprint the three references for `cir`, bound to `release_hash`.

    Refuses when `release_hash` is not this CIR's content hash, or the pattern does not compile
    (a twin of failing arithmetic would be fiction, `cir.twin.build_twin`)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..publish import charts

    if not release_hash:
        raise PatternRefsRefused("a release hash is required: references bind to a release")
    actual = release_hash_of(cir)
    if actual != release_hash:
        raise PatternRefsRefused(
            f"release {release_hash[:16]} is not this CIR's content ({actual[:16]}); "
            f"references for different content would condition a render on another product")
    result = compile_cir(cir)
    if not result.ok:
        raise PatternRefsRefused("the CIR does not compile; no references from a broken pattern")
    twin = build_twin(cir, result)
    grid, colors = twin.chart_grid(), twin.color_grid()
    rows_total = len(grid)
    stitches_across = max((len(r) for r in grid), default=0)
    if not rows_total or not stitches_across:
        raise PatternRefsRefused("the twin has no cells to draw")
    col_period, row_period = charts.detect_repeat(grid, colors)

    layout = charts.render_fabric(cir, twin, cell_px=12)
    aspect_basis = "render_fabric row heights"
    if twin.width_cm and twin.height_cm:
        # The fabric render's row heights are a drawing convention; the twin's finished size
        # is the product truth. A proportion reference in the wrong aspect teaches the model
        # the wrong shape, so the layout is rescaled (nearest neighbour: hard stitch edges,
        # no invented colours) to the twin's width:height.
        from PIL import Image

        w = layout.size[0]
        h = max(1, round(w * float(twin.height_cm) / float(twin.width_cm)))
        layout = layout.resize((w, h), Image.NEAREST)
        aspect_basis = f"digital twin {twin.width_cm:.1f} x {twin.height_cm:.1f} cm"
    mc, mr = _motif_block(grid, colors, col_period, row_period)
    motif = charts.render_chart(
        cir, twin, charts.ChartSpec(cell_px=44, margin_px=56, max_width_px=1800),
        grids=charts.crop_grids(grid, colors, mc, mr),
        caption=(f"{cir.title}: {mc} stitches x {mr} rows from the bottom-left corner "
                 f"(repeat {col_period} sts); enlarged"))
    sheet = _construction_sheet(cir, twin, release_hash=release_hash, col_period=col_period,
                                row_period=row_period, stitches_across=stitches_across,
                                rows_total=rows_total)

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    refs: list[PatternRef] = []
    for role, image in (("layout", layout), ("motif", motif), ("construction", sheet)):
        raw = _png_bytes(image)
        path = root / f"{cir.slug}-{release_hash[:12]}-{role}.png"
        path.write_bytes(raw)
        refs.append(PatternRef(role, str(path), hashlib.sha256(raw).hexdigest(),
                               image.size[0], image.size[1]))
    manifest = {
        "version": VERSION, "slug": cir.slug, "cir_version": cir.version,
        "release_hash": release_hash,
        "layout_aspect_basis": aspect_basis,
        "grid": {"stitches_across": stitches_across, "rows": rows_total,
                 "repeat": [col_period, row_period], "motif_block": [mc, mr]},
        "references": [r.to_dict() for r in refs],
        "cost_cad": 0.0, "basis": "deterministic render of the compiled CIR; no model",
    }
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(
        {k: v for k, v in manifest.items() if k != "references"}
        | {"references": [{"role": r.role, "sha256": r.sha256} for r in refs]},
        sort_keys=True).encode()).hexdigest()
    (root / f"{cir.slug}-{release_hash[:12]}-pattern-refs.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n")
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
