"""Lane A: build the identity contact sheets (HTML) and shoot them with Chromium.

    cd brambleloop && PYTHONPATH=src <venv python> research/final_build/w3/A_build_sheets.py

Writes research/final_build/w3/evidence/A_*.png (<= 6 files, each <= 300 KB) and
research/final_build/w3/evidence/A_judge_verdict.json. HTML is built in a temp dir and
deleted. Every mark is shown via <img> data URIs of the shipped SVG, so Chromium -- not our
own rasteriser -- draws what a customer's browser would draw.
"""
from __future__ import annotations

import base64
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import directions as D  # noqa: E402
from brambleloop.brand import identity_system as I  # noqa: E402
from brambleloop.brand import iterations as IT  # noqa: E402
from brambleloop.brand import judge  # noqa: E402
from brambleloop.brand.vector import to_svg  # noqa: E402

EVID = HERE / "evidence"
FONTS = ROOT / "src" / "brambleloop" / "brand" / "fonts"
LAURA = ROOT / "src" / "brambleloop" / "visual" / "assets" / "identity_portrait.jpg"
P = I.PALETTE


def uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def img(svg: str, w: float | None = None, h: float | None = None, extra: str = "") -> str:
    size = (f' width="{w:g}"' if w else "") + (f' height="{h:g}"' if h else "")
    return f'<img src="{uri(svg)}"{size} {extra} alt="">'


def dsvg(d: D.Direction, mark, variant="colour", transparent=False) -> str:
    return to_svg(mark, d.colours(variant), None if transparent else d.ground(variant),
                  id_prefix=f"{d.id[:2]}{variant[:2]}{mark.name[-6:]}")


def page(title: str, body: str, w: int, h: int = 600) -> str:
    css = I.font_face_css(base_url=FONTS.parent.as_uri() + "/")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="shoot" content="{w}x{h}"><title>{html.escape(title)}</title>
<style>{css}
body{{margin:0;padding:20px;background:#fff;color:{P['forest']};font:13px 'Work Sans',sans-serif}}
h1{{font:400 22px 'Libre Baskerville',serif;margin:0 0 4px}} h2{{font:400 15px 'Libre Baskerville',serif;margin:14px 0 6px}}
.note{{color:#5B5A4E;font-size:12px;max-width:1100px}} .row{{display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin:6px 0}}
.cell{{display:flex;flex-direction:column;align-items:center;gap:4px;font-size:11px;color:#5B5A4E}}
.tag{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#7E4A3E}}
.internal{{position:absolute;left:4px;bottom:4px;background:#7A2E3A;color:#fff;font-size:9px;padding:2px 4px;line-height:1.2}}
table{{border-collapse:collapse;font-size:11px}} td,th{{border-bottom:1px solid #e5dfd3;padding:3px 8px;text-align:left}}
</style></head><body>{body}</body></html>"""


def sheet_directions() -> str:
    rows = []
    for d in D.DIRECTIONS.values():
        ic = d.icon()
        cells = "".join(f'<div class="cell">{img(dsvg(d, ic), px, px)}{px}px</div>'
                        for px in (40, 70, 120))
        cells += f'<div class="cell">{img(dsvg(d, ic, "mono"), 70, 70)}mono</div>'
        cells += f'<div class="cell">{img(dsvg(d, ic, "reversed"), 70, 70)}reversed</div>'
        lk = d.lockup_horizontal()
        cells += f'<div class="cell">{img(dsvg(d, lk), None, 40)}phone header, 40px tall</div>'
        st = d.lockup_stacked()
        cells += f'<div class="cell">{img(dsvg(d, st), 260)}stacked</div>'
        sw = "".join(f'<span title="{k}" style="display:inline-block;width:22px;height:22px;'
                     f'background:{v};border:1px solid #0002"></span>' for k, v in d.palette.items())
        rows.append(f'<h2>{html.escape(d.id)} &mdash; {html.escape(d.name)}</h2>'
                    f'<div class="note">{html.escape(d.concept)}</div>'
                    f'<div class="row">{cells}<div class="cell"><div>{sw}</div>palette</div></div>')
    body = ("<h1>Brambleloop identity &mdash; four directions at real sizes</h1>"
            '<div class="note">Every mark is deterministic SVG (geometry + outlined OFL type), drawn '
            "here by Chromium at 1x device pixels. 40 and 70 px are the Etsy icon sizes tested.</div>"
            + "".join(rows))
    return page("A directions", body, 1400)


def sheet_small(verdict: dict) -> str:
    from brambleloop.store_foundation import assets as old

    blind = list(D.DIRECTIONS.values())
    labels = "PQRS"
    tiles = ""
    for lab, d in zip(labels, blind):
        ic = d.icon()
        tiles += (f'<div class="cell"><div class="row" style="background:#fff;padding:8px">'
                  f'{img(dsvg(d, ic), 40, 40)}{img(dsvg(d, ic), 70, 70)}</div>'
                  f'<div class="row" style="background:#222;padding:8px">{img(dsvg(d, ic), 40, 40)}'
                  f'{img(dsvg(d, ic, "reversed"), 40, 40)}</div>blind {lab}</div>')
    oldicon = old.icon_svg()
    tiles += (f'<div class="cell"><div class="row" style="background:#fff;padding:8px">'
              f'{img(oldicon, 40, 40)}{img(oldicon, 70, 70)}</div>'
              f'<div class="row" style="background:#222;padding:8px">{img(oldicon, 40, 40)}</div>'
              f'REJECTED v1 mark</div>')
    refs = "".join(
        f'<div class="cell">{img(to_svg(m, {"ink": "#333", "g": "#fff"}, "#fff"), 40, 40)}'
        f'{k.replace("_", " ")}</div>' for k, m in judge.generic_references().items())
    trs = ""
    for did in verdict["ranking"]:
        mt, ds, sc = verdict["metrics"][did], verdict["distinctness"][did], verdict["scores"][did]
        trs += (f"<tr><td>{did}</td><td>{mt['primary_contrast']}</td>"
                f"<td>{mt['ink_coverage']['40']}</td><td>{mt['crispness_40']}</td>"
                f"<td>{mt['stroke_survival_40']}</td><td>{mt['thinnest_stroke_px_40']}</td>"
                f"<td>{max(ds['iou_vs_generic'].values())}</td><td>{ds['distinctness']}</td>"
                f"<td>{mt['header_letter_px']}</td><td>{sc['measured']}</td><td>{sc['judged']}</td>"
                f"<td><b>{sc['total']}</b></td></tr>")
    body = ("<h1>Tiny-size test &mdash; blind labels, white and dark grounds</h1>"
            '<div class="note">Labels P&ndash;S hide the direction for a first-glance read '
            "(P=D1, Q=D2, R=D3, S=D4 &mdash; revealed below). The rejected v1 mark is shown at the "
            "same sizes.</div>"
            f'<div class="row">{tiles}</div><h2>Generic craft clip-art references (what not to '
            f'be), 40 px</h2><div class="row">{refs}</div>'
            "<h2>Measured (raster of the shipped geometry) + judged</h2><table><tr><th>direction"
            "</th><th>contrast</th><th>ink@40</th><th>crisp@40</th><th>stroke survival@40</th>"
            "<th>thinnest stroke px@40</th><th>max IoU vs generic</th><th>distinctness</th>"
            "<th>header letter px</th><th>measured</th><th>judged</th><th>total</th></tr>"
            f"{trs}</table>")
    return page("A small sizes", body, 1200)


def sheet_system() -> str:
    d = I.direction()
    sw = ""
    from brambleloop.brand.judge import contrast
    for k, v in I.ROLES.items():
        c = contrast(v, I.ROLES["background"])
        sw += (f'<div class="cell"><span style="display:block;width:64px;height:40px;background:{v};'
               f'border:1px solid #0002"></span>{k}<br>{v} &middot; {c:.1f}:1</div>')
    tag = "Patterns for a More Handmade Life"
    body = (f"<h1>Winner: {html.escape(d.id)} &mdash; {html.escape(d.name)} "
            "(recommended, pending owner approval)</h1>"
            f'<div class="note">{html.escape(d.concept)} Source: {html.escape(d.source)}</div>'
            f'<div class="row" style="background:{P["paper"]};padding:16px;gap:40px">'
            f'{img(I.lockup_stacked_svg(tagline=tag), 520)}'
            f'<div class="cell">{img(I.emblem_svg(), 220)}emblem (banner/About, &ge;160px)</div>'
            f'<div class="cell">{img(I.lockup_stacked_svg("reversed", tagline=tag), 300)}reversed</div>'
            f'<div class="cell">{img(I.lockup_stacked_svg("mono"), 240)}one colour</div></div>'
            '<div class="row">'
            + "".join(f'<div class="cell">{img(I.icon_svg(v), px, px)}{v} {px}px</div>'
                      for v in ("colour", "mono", "reversed") for px in (40, 70, 160))
            + f'</div><div class="row"><div class="cell">{img(I.lockup_horizontal_svg(), None, 36)}'
            "horizontal lockup, 36px (phone header)</div>"
            f'<div class="cell">{img(I.wordmark_svg(transparent=True), 300)}wordmark</div>'
            f'<div class="cell" style="background:{P["paper"]};padding:6px">'
            f'<div style="width:360px;height:120px;background:url({uri(I.motif_svg())}) 0 0/120px"></div>'
            "bramble motif tile</div></div>"
            f'<h2>Colour roles (contrast vs background)</h2><div class="row">{sw}</div>'
            "<h2>Type (all SIL OFL, bundled; marks are outlined)</h2>"
            f'<div style="background:{P["paper"]};padding:12px">'
            "<div style=\"font:400 30px 'Libre Baskerville';letter-spacing:.08em\">Libre Baskerville "
            "&mdash; display</div><div style=\"font:400 17px Lora;max-width:760px\">Lora &mdash; body. "
            "Clear, dependable instructions you can follow with confidence, row after row.</div>"
            "<div style=\"font:italic 20px Lora\">Lora Italic &mdash; tagline</div>"
            "<div style=\"font:400 12px 'Work Sans';letter-spacing:.28em\">WORK SANS &mdash; UI &middot; "
            "DESCRIPTOR &middot; NAV</div></div>")
    return page("A system", body, 1300)


def _laura_img(w: int, h: int, round_: bool = False) -> str:
    if not LAURA.exists():
        return f'<div style="width:{w}px;height:{h}px;background:#ccc">Laura n/a</div>'
    from PIL import Image
    import io

    im = Image.open(LAURA).convert("RGB")
    im.thumbnail((w * 2, h * 2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    src = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    rad = "border-radius:50%;" if round_ else ""
    return (f'<div style="position:relative;width:{w}px;height:{h}px;flex:none">'
            f'<img src="{src}" style="width:{w}px;height:{h}px;object-fit:cover;{rad}">'
            f'<span class="internal">INTERNAL &middot; canonical ref, not publication-approved</span></div>')


def sheet_context() -> str:
    motif = uri(I.motif_svg())
    phone = (f'<div style="width:390px;border:1px solid #ddd;background:{P["paper"]}">'
             f'<div style="height:56px;display:flex;align-items:center;padding:0 16px;'
             f'background:#fff;border-bottom:1px solid #eee">{img(I.lockup_horizontal_svg(transparent=True), None, 30)}</div>'
             f'<div style="height:195px;display:flex;align-items:center;justify-content:center;'
             f'background:{P["paper"]} url({motif}) 0 0/140px">'
             f'<div style="background:{P["paper"]};padding:10px 18px">'
             f'{img(I.lockup_stacked_svg(transparent=True), 230)}</div></div>'
             f'<div style="display:flex;gap:12px;align-items:center;padding:14px 16px">'
             f'{img(I.icon_svg(), 70, 70)}<div><div style="font:400 19px \'Libre Baskerville\'">'
             f'Brambleloop Studio</div><div style="font:italic 14px Lora;color:#5B5A4E">'
             f'(tagline from lane C)</div></div></div>'
             f'<div style="display:flex;gap:10px;padding:0 16px 16px">'
             + "".join(f'<div style="flex:1;background:#fff;padding:6px"><div style="height:150px;'
                       f'background:{P["paper"]} url({motif}) 0 0/90px"></div><div style="font:13px Lora;'
                       f'padding-top:6px">Listing card</div><div style="font:12px \'Work Sans\';'
                       f'color:{P["rose_deep"]}">CA$ &mdash;</div></div>' for _ in range(2))
             + "</div></div>")
    banner = (f'<div style="width:1000px;height:250px;display:flex;align-items:center;'
              f'background:{P["paper"]};overflow:hidden;border:1px solid #ddd">'
              f'{_laura_img(250, 250)}'
              f'<div style="flex:1;display:flex;justify-content:center">'
              f'{img(I.lockup_stacked_svg(transparent=True, tagline="Patterns for a More Handmade Life"), 330)}</div>'
              f'<div style="width:250px;height:250px;background:url({motif}) 0 0/125px"></div></div>')
    seller = (f'<div class="row">{_laura_img(96, 96, True)}<div class="note">Seller portrait: '
              f"Laura, no logo overlay. Shop icon: the mark (it reads at 40 px; a face does not).</div></div>")
    body = ("<h1>Identity in store context (composition check, not lane B's store preview)</h1>"
            '<div class="note">Phone top fold at 390px and a desktop banner composition, '
            "showing how the mark and Laura share a surface: she is the face, the mark is the "
            "signature. The Laura image is the canonical internal reference and is NOT "
            "publication-approved. Listing images are placeholders (motif), not products.</div>"
            f'<div class="row" style="align-items:flex-start;gap:28px">{phone}<div>{banner}'
            f"{seller}</div></div>")
    return page("A context", body, 1460)


def sheet_iteration() -> str:
    from brambleloop.store_foundation import assets as old

    d = D.D1
    cells = ""
    for name, fn, why in IT.ITERATIONS:
        m = fn() if fn else d.icon()
        cells += (f'<div class="cell" style="max-width:220px">'
                  f'<div class="row">{img(dsvg(d, m), 40, 40)}{img(dsvg(d, m), 70, 70)}'
                  f'{img(dsvg(d, m, "mono"), 70, 70)}</div><b>{html.escape(name)}</b>'
                  f'{html.escape(why)}</div>')
    oldc = (f'<div class="cell" style="max-width:260px"><div class="row">'
            f'{img(old.icon_svg(), 40, 40)}{img(old.icon_svg(), 70, 70)}{img(old.icon_svg(), 160, 160)}'
            "</div><b>rejected store-preview mark</b>ring + V + sprig: thin gold V and sprig "
            "dissolve at 40 px; reads as a generic badge</div>"
            f'<div class="cell" style="max-width:260px"><div class="row">'
            f'{img(I.icon_svg(), 40, 40)}{img(I.icon_svg(), 70, 70)}{img(I.icon_svg(), 160, 160)}'
            "</div><b>new mark (D1 v3)</b>monogram B held in a yarn loop: letterform carries "
            "recognition at 40 px; the loop, ball and leaf carry the name</div>")
    body = ("<h1>Iteration of the winner's icon, and the rejected mark it replaces</h1>"
            f'<div class="row" style="gap:30px">{cells}</div>'
            f'<h2>Old vs new at the same sizes</h2><div class="row" style="gap:40px">{oldc}</div>')
    return page("A iteration", body, 1200)


def main() -> int:
    verdict = judge.verdict()
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "A_judge_verdict.json").write_text(json.dumps(verdict, indent=1, sort_keys=True,
                                                          default=str))
    tmp = Path(tempfile.mkdtemp(prefix="w3A-"))
    try:
        v_json = json.loads(json.dumps(verdict, default=str))
        sheets = {"A_1_directions": sheet_directions(), "A_2_small_sizes_blind": sheet_small(v_json),
                  "A_3_winner_system": sheet_system(), "A_4_store_context": sheet_context(),
                  "A_5_iteration_vs_rejected": sheet_iteration()}
        for k, v in sheets.items():
            (tmp / f"{k}.html").write_text(v)
        env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH="/opt/pw-browsers")
        r = subprocess.run(["node", str(HERE / "A_shoot.mjs"), str(tmp), str(tmp / "out")],
                           env=env, capture_output=True, text=True, timeout=180)
        print(r.stdout, r.stderr[-2000:])
        if r.returncode:
            return r.returncode
        from PIL import Image
        for png in sorted((tmp / "out").glob("*.png")):
            dest = EVID / png.name
            im = Image.open(png).convert("RGB")
            if png.stat().st_size <= 300_000:
                shutil.copyfile(png, dest)
                print("wrote", dest.name, dest.stat().st_size, im.size)
                continue
            # keep each sheet <= 300 KB: palette-quantise (flat vector art survives it)
            q = im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            q.save(dest, optimize=True)
            if dest.stat().st_size > 300_000:
                scale = (300_000 / dest.stat().st_size) ** 0.5 * 0.95
                im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
                im.quantize(colors=128, dither=Image.Dither.NONE).save(dest, optimize=True)
            print("wrote", dest.name, dest.stat().st_size, im.size)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
