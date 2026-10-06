"""Owner Store Preview v2 (wave 3, lane B): the storefront redesigned to lead with crochet.

The v1 preview (`preview.render_preview(..., variant="standard")`) was rejected by the owner
as generic and technical. v1 is kept, unchanged, as the baseline; this module draws the
proposed replacement and a side-by-side comparison against it.

Art direction (owner decision D-FB-17, 2026-10-06): the shop is rebuilt around the owner's two
canonical files (`brand.canonical_assets`) -- warm, premium, feminine, cosy, lifestyle-first:

* the banner IS the owner's canonical banner, shown as supplied (resampled to fit, never
  redrawn) with its honest state: `owner_banner.assess` names every publication gate that
  stops the exact file today, and the woman in it is not verified as Laura, so it carries the
  internal-preview label. The owner board shows what Etsy's 4:1 canvas and an assumed phone
  window would do to it, and the minimal reframes that are OWNER_REVIEW_REQUIRED;
* the hero lockup (About header) is the owner's logo artwork, exact; the shop icon is the
  owner's monogram where measured legible at every display size, otherwise the A3 micro-mark,
  labelled a small-size derivative with the measurement;
* Laura is shown only through her approved canonical portrait (`brand_face.image_for`, bytes
  verified), and every element that shows her carries "Internal preview -- canonical
  reference, not publication-approved" in its accessible name, with a visible tag on every
  large placement. The owner's concept image is not embedded: its woman is not verified as
  Laura;
* listing cards are product-first and use only the disclosed Launch-0 renders that verify on
  their exact bytes at load (`preview.hero_frame`); a frame that does not verify is withheld;
* the top fold carries no implementation vocabulary; how patterns are checked appears lower,
  in About, translated into what it means for the maker;
* nothing is a working control; every page is labelled "Preview -- not live"; no script, no
  external URL, every value escaped.

Brand tokens come from lane A, words from lane C, banner crop numbers from lane I, each via
`preview_sources` with labelled fallbacks.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from pathlib import Path

from . import preview_sources as S

VARIANT = "v2"
COMPARE = "compare"
MOBILE_SCREEN = (390, 844)       # iPhone 12-15 CSS viewport: the "first screen" we judge
DESKTOP_SCREEN = (1280, 800)

# Words that make a shop read like a software project. None may appear in the top fold.
JARGON = ("compiler", "compiled", "machine-readable", "machine readable", "machine",
          "row check", "row-check", "checked row by row", "row by row", "by code", "software",
          "algorithm", "verifier", "deterministic", "cir", "arithmetic", "program",
          "pipeline", "agent", "model", "formal", "validated", "validation", "automated",
          "release")
EVIDENCE_REL = "research/final_build/w3/evidence/B_metrics.json"


def _esc(v) -> str:
    from ..app.security import esc

    return str(esc(v))


def jargon_hits(text: str) -> list[str]:
    """Every technical term in `text` (case-insensitive, whole words/phrases)."""
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    hits = []
    for term in JARGON:
        n = len(re.findall(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low))
        hits.extend([term] * n)
    return hits


def visible_text(html: str) -> str:
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    import html as _h

    return re.sub(r"\s+", " ", _h.unescape(html)).strip()


# ---- colour ---------------------------------------------------------------------------------

def _lum(hexv: str) -> float:
    h = hexv.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(fg: str, bg: str) -> float:
    a, b = sorted((_lum(fg), _lum(bg)), reverse=True)
    return round((a + 0.05) / (b + 0.05), 2)


def text_pairs(p: dict) -> list[tuple[str, str, str, float]]:
    """Every (role, fg, bg, minimum) text pairing the v2 layout uses."""
    return [("body", p["ink"], p["paper"], 4.5), ("body on cream", p["ink"], p["cream"], 4.5),
            ("secondary", p["muted"], p["paper"], 4.5),
            ("secondary on cream", p["muted"], p["cream"], 4.5),
            ("heading", p["forest"], p["paper"], 4.5), ("wordmark", p["forest"], p["cream"], 4.5),
            ("accent text", p["sage_deep"], p["cream"], 4.5),
            ("price", p["berry"], p["paper"], 4.5),
            ("preview tag", p["paper"], p["berry"], 4.5),
            ("chip on", p["paper"], p["forest"], 4.5)]


# ---- CSS ------------------------------------------------------------------------------------

def _css(p: dict, t: dict) -> str:
    return f"""
:root{{--paper:{p['paper']};--cream:{p['cream']};--linen:{p['linen']};--line:{p['line']};
--sage:{p['sage']};--sage-deep:{p['sage_deep']};--forest:{p['forest']};--rose:{p['rose']};
--berry:{p['berry']};--ink:{p['ink']};--muted:{p['muted']};--night:{p['night']};
--display:{t['display']};--body:{t['body']};--story:{t.get('story', t['body'])}}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0}}
body{{background:#E9E4DA;color:var(--ink);font:15px/1.55 var(--body);
-webkit-text-size-adjust:100%}}
.pbar{{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;padding:4px 16px;
background:var(--night);color:#F4EEE3;font-size:12.5px;line-height:1.3}}
.pbar strong{{letter-spacing:.06em;text-transform:uppercase;font-size:11.5px;margin-right:auto}}
.pbar nav{{display:flex;flex-wrap:wrap;gap:2px}}
.pbar a{{display:inline-flex;align-items:center;min-height:44px;padding:0 10px;color:#F4EEE3;
text-decoration:none;border-radius:6px}}
.pbar a.on{{background:#3A463E;text-decoration:underline;text-underline-offset:4px}}
.pnote{{flex-basis:100%;font-size:11.5px;color:#D9D2C4;padding-bottom:6px}}
.frame{{background:var(--paper);margin:0 auto;width:100%;max-width:390px;overflow:hidden}}
.vp-desktop .frame{{max-width:1280px}}
.serif{{font-family:var(--display)}}
/* owner canonical banner (D-FB-17), shown as supplied */
.obn{{background:var(--cream)}}
.obn .art{{width:100%;aspect-ratio:1983/793;background-image:var(--owner-banner);
background-size:cover;background-position:center}}
.herologo{{display:block;width:100%;max-width:520px;height:auto;margin:0 0 18px;border-radius:12px}}
.board .ob{{background-image:var(--owner-banner);background-repeat:no-repeat;border-radius:6px;
background-color:var(--linen)}}
.board .mono img{{display:block}}
.board .cand img{{display:block;width:100%;height:auto;border-radius:6px}}
/* banner: one canvas, cropped by the box it sits in */
.bn{{position:relative;overflow:hidden;background:var(--cream)}}
.bn .canvas{{position:absolute;top:0;height:100%;container-type:inline-size;
background:radial-gradient(120% 90% at 50% 40%,var(--paper) 0,var(--cream) 55%,var(--linen) 100%)}}
.bn .canvas:before{{content:"";position:absolute;inset:0;opacity:.35;
background:repeating-linear-gradient(90deg,transparent 0 3px,rgba(142,155,130,.08) 3px 4px),
repeating-linear-gradient(0deg,transparent 0 3px,rgba(142,155,130,.06) 3px 4px)}}
.bn .el{{position:absolute;top:0;height:100%}}
.bn .who{{background-image:var(--laura);background-size:cover;background-position:50% 18%;
-webkit-mask-image:linear-gradient(90deg,transparent 0,#000 14%,#000 66%,transparent 100%);
mask-image:linear-gradient(90deg,transparent 0,#000 14%,#000 66%,transparent 100%)}}
.vp-mobile .bn .who,.bn.ph .who{{-webkit-mask-image:linear-gradient(90deg,#000 66%,transparent);
mask-image:linear-gradient(90deg,#000 66%,transparent)}}
.pvs{{background:var(--berry);color:var(--paper);font:600 10.5px/1.3 var(--body);padding:4px 16px}}
.bn .pv{{font-size:9px;padding:2px 5px}}
.bn .lock{{display:flex;flex-direction:column;align-items:center;justify-content:center;
text-align:center;color:var(--forest)}}
.bn .lockimg{{width:100%;aspect-ratio:1400/870;max-height:86%;background-size:contain;
background-repeat:no-repeat;background-position:center}}
.bn .lock img{{width:8.2cqw;height:8.2cqw;border-radius:50%;display:block;margin-bottom:.9cqw}}
.bn .word{{font-family:var(--display);font-size:2.9cqw;letter-spacing:.14em;line-height:1;
font-weight:600;margin-right:-.14em}}
.bn .sub{{display:flex;align-items:center;gap:.8cqw;font-size:.95cqw;letter-spacing:.32em;
color:var(--sage-deep);margin:.8cqw 0 .7cqw;text-transform:uppercase}}
.bn .sub:before,.bn .sub:after{{content:"";width:3.4cqw;border-top:1px solid var(--sage)}}
.bn .tag{{font-family:var(--display);font-style:italic;font-size:1.6cqw;color:var(--ink);
line-height:1.2}}
.bn .wing{{display:flex;align-items:center;justify-content:center}}
.bn .arch{{position:relative;width:64%;aspect-ratio:4/5;border-radius:999px 999px 14px 14px;
overflow:hidden;border:.35cqw solid var(--paper);box-shadow:0 .4cqw 1.6cqw rgba(46,64,52,.16);
background-size:150%;background-position:50% 36%;background-color:var(--sage)}}
.pv{{position:absolute;left:6px;top:6px;z-index:3;background:var(--berry);color:var(--paper);
font:600 9.5px/1.25 var(--body);padding:3px 6px;border-radius:4px;max-width:calc(100% - 12px)}}
.portrait .pv{{font-size:11px;top:10px;left:10px}}
.rtag{{position:absolute;left:50%;transform:translateX(-50%);bottom:6%;white-space:nowrap;
background:rgba(251,248,242,.94);color:var(--ink);font:500 .8cqw/1.2 var(--body);
padding:.25cqw .6cqw;border-radius:99px}}
/* header */
.sh{{padding:0 16px 14px;position:relative}}
.sh .icon{{width:68px;height:68px;border-radius:14px;border:3px solid var(--paper);
margin-top:-26px;background:var(--cream);box-shadow:0 2px 8px rgba(42,39,36,.16);display:block;
position:relative;z-index:2}}
.sh h1{{font-family:var(--display);font-weight:600;font-size:28px;line-height:1.1;
color:var(--forest);margin:10px 0 4px;letter-spacing:.01em}}
.sh .title{{margin:0 0 6px;font-size:15px;color:var(--ink)}}
.sh .meta{{margin:0;font-size:13px;color:var(--muted)}}
.sh .acts{{display:flex;gap:10px;margin-top:12px}}
.btn{{display:inline-flex;align-items:center;justify-content:center;min-height:44px;
padding:0 18px;border-radius:999px;font-size:14px;font-weight:600;border:1.5px solid var(--forest);
color:var(--forest);background:var(--paper)}}
.btn.solid{{background:var(--forest);color:var(--paper)}}
.sh .acts .btn{{flex:1}}
.owner-card{{display:none}}
.ann{{margin:4px 16px 14px;padding:12px 14px;background:var(--cream);border-radius:12px;
font-size:14px;line-height:1.5}}
.ann b{{display:block;font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;
color:var(--sage-deep);margin-bottom:3px}}
.secs{{display:flex;gap:8px;overflow-x:auto;padding:2px 16px 12px;margin:0;list-style:none;
scrollbar-width:none}}
.secs li{{flex:none;display:inline-flex;align-items:center;min-height:44px;padding:0 16px;
border:1px solid var(--line);border-radius:999px;font-size:14px;white-space:nowrap;
background:var(--paper)}}
.secs li.on{{background:var(--forest);border-color:var(--forest);color:var(--paper)}}
.secs .n{{margin-left:6px;opacity:.75;font-size:13px}}
.side{{display:none}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px 12px;padding:0 16px 22px}}
.card{{min-width:0}}
.card .ph{{position:relative;aspect-ratio:1/1;border-radius:12px;overflow:hidden;
background-color:var(--linen);background-size:cover;background-position:center}}
.card .ph .badge{{position:absolute;left:8px;top:8px;background:rgba(251,248,242,.94);
color:var(--forest);font-size:11.5px;font-weight:600;padding:3px 8px;border-radius:99px}}
.card .ph.lead{{background-color:var(--cream);background-image:var(--owner-mono);
background-repeat:no-repeat;background-position:50% 30%;background-size:34%}}
.card .ph-note{{position:absolute;left:8px;right:44%;bottom:10px;font-size:11.5px;
line-height:1.3;color:var(--muted)}}
.card .ev{{position:absolute;right:8px;bottom:8px;width:40%;aspect-ratio:1/1;border-radius:8px;
border:2px solid var(--paper);background-size:cover;background-position:center;
box-shadow:0 1px 4px rgba(42,39,36,.18)}}
.card .evl{{position:absolute;left:0;right:0;bottom:0;background:rgba(251,248,242,.94);
color:var(--ink);font-size:10px;text-align:center;padding:1px 0;border-radius:0 0 6px 6px}}
.card .withheld{{display:flex;align-items:center;justify-content:center;text-align:center;
height:100%;padding:12px;font-size:12px;color:var(--berry);border:1px dashed var(--berry);
border-radius:12px}}
.card h3{{font-size:14px;font-weight:400;line-height:1.35;margin:8px 0 3px;color:var(--ink);
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card .price{{font-weight:700;font-size:15.5px;color:var(--ink)}}
.card .dl{{font-size:13px;color:var(--muted)}}
.card .disc{{font-size:11.5px;color:var(--muted);font-style:italic;margin-top:2px}}
.trust{{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:20px 16px;margin:0;
list-style:none;background:var(--cream)}}
.trust li{{background:var(--paper);border-radius:12px;padding:12px}}
.trust svg{{width:26px;height:26px;display:block;margin-bottom:6px}}
.trust b{{display:block;font-size:14px;color:var(--forest)}}
.trust span{{font-size:12.5px;color:var(--muted);line-height:1.4;display:block}}
.about{{padding:28px 16px}}
.kicker{{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--sage-deep);
margin:0 0 6px}}
.about h2,.help h2{{font-family:var(--display);font-weight:600;font-size:26px;line-height:1.15;
color:var(--forest);margin:0 0 14px}}
.portrait{{position:relative;aspect-ratio:4/5;border-radius:18px;overflow:hidden;
background-image:var(--laura);background-size:cover;background-position:50% 25%;
margin:0 0 12px;background-color:var(--linen)}}
.byline{{display:flex;flex-direction:column;margin:0 0 14px}}
.byline b{{font-family:var(--display);font-size:20px;color:var(--forest);font-weight:600}}
.byline span{{font-size:13px;color:var(--muted)}}
.about p{{margin:0 0 12px;font-family:var(--story);font-size:16px;line-height:1.6}}
.proof{{margin:18px 0 0;padding:16px;border:1px solid var(--line);border-radius:14px}}
.proof h3{{font-family:var(--display);font-size:20px;font-weight:600;color:var(--forest);
margin:0 0 8px}}
.proof ul{{list-style:none;margin:0;padding:0}}
.proof li{{position:relative;padding:6px 0 6px 26px;font-size:14px}}
.proof li:before{{content:"";position:absolute;left:4px;top:11px;width:6px;height:11px;
border:solid var(--sage-deep);border-width:0 2px 2px 0;transform:rotate(45deg)}}
.help{{padding:26px 16px;border-top:1px solid var(--line)}}
.help h3{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--sage-deep);
margin:18px 0 4px}}
details{{border-bottom:1px solid var(--line)}}
summary{{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:48px;
cursor:pointer;font-weight:600;font-size:15px;list-style:none}}
summary::-webkit-details-marker{{display:none}}
summary:after{{content:"+";color:var(--sage-deep);font-weight:400;font-size:20px}}
details[open] summary:after{{content:"\\2013"}}
details .a{{padding:0 0 14px;font-size:14px}}
details .a p{{margin:0 0 8px}}
details .a ul{{margin:0 0 8px;padding-left:20px}}
.support{{margin:20px 0 0;padding:16px;background:var(--cream);border-radius:14px;font-size:14px}}
.foot{{padding:18px 16px 26px;font-size:12px;color:var(--muted);text-align:center;
background:var(--cream)}}
.foot .fw{{font-family:var(--display);font-size:18px;letter-spacing:.16em;color:var(--forest);
display:block;margin-bottom:4px}}
@media (min-width:900px){{
.vp-desktop .sh{{display:grid;grid-template-columns:auto 1fr auto;gap:0 22px;padding:0 40px 22px;
align-items:start}}
.vp-desktop .sh .icon{{width:124px;height:124px;margin-top:-46px;border-radius:20px}}
.vp-desktop .sh h1{{font-size:36px;margin-top:18px}}
.vp-desktop .sh .acts{{grid-column:2}}
.vp-desktop .sh .acts .btn{{flex:none}}
.vp-desktop .owner-card{{display:flex;gap:12px;align-items:center;margin-top:18px;
grid-column:3;grid-row:1 / span 2;padding:12px 14px;border:1px solid var(--line);
border-radius:14px;background:var(--paper)}}
.vp-desktop .owner-card .av{{width:56px;height:56px;border-radius:50%;flex:none;
background-image:var(--laura);background-size:cover;background-position:50% 22%}}
.vp-desktop .owner-card b{{display:block;font-family:var(--display);font-size:18px;color:var(--forest)}}
.vp-desktop .owner-card span{{display:block;font-size:12.5px;color:var(--muted)}}
.vp-desktop .owner-card small{{display:block;font-size:10.5px;color:var(--berry);max-width:210px}}
.vp-desktop .ann{{margin:0 40px 22px;max-width:820px}}
.vp-desktop .shop{{display:grid;grid-template-columns:230px 1fr;gap:32px;padding:0 40px 34px}}
.vp-desktop .secs{{flex-direction:column;padding:0;overflow:visible;gap:4px}}
.vp-desktop .secs li{{justify-content:space-between;border:0;border-radius:10px}}
.vp-desktop .secs li:not(.on):hover{{background:var(--cream)}}
.vp-desktop .side{{display:block;margin-top:18px;padding-top:16px;border-top:1px solid var(--line);
font-size:13px;color:var(--muted)}}
.vp-desktop .grid{{grid-template-columns:repeat(3,1fr);gap:28px 22px;padding:0}}
.vp-desktop .card h3{{font-size:14.5px}}
.vp-desktop .trust{{grid-template-columns:repeat(4,1fr);gap:16px;padding:28px 40px}}
.vp-desktop .about{{display:grid;grid-template-columns:5fr 7fr;gap:48px;padding:56px 40px;
align-items:start}}
.vp-desktop .about h2,.vp-desktop .help h2{{font-size:34px}}
.vp-desktop .help{{display:grid;grid-template-columns:1fr 1fr;gap:48px;padding:44px 40px}}
}}
/* owner review board -- not part of the shop */
.board{{margin:22px auto 34px;max-width:390px;background:#FFFDF9;border:2px dashed var(--muted);
padding:16px;font-size:13px;overflow:hidden}}
.vp-desktop .board{{max-width:1280px}}
.board h2{{font-size:17px;margin:0 0 6px;font-family:var(--body)}}
.board h3{{font-size:14px;margin:18px 0 6px}}
.board .row{{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin:6px 0}}
.board figure{{margin:0;font-size:11.5px;color:var(--muted);max-width:100%}}
.board .dark{{background:var(--night);padding:10px;border-radius:8px;color:#E9E4DA}}
.board .dark figure{{color:#D9D2C4}}
.board .ic img{{display:block;border-radius:22%}}
.board .bnwrap{{max-width:100%}}
.board table{{width:100%;border-collapse:collapse;font-size:12.5px}}
.board th,.board td{{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line);
vertical-align:top;overflow-wrap:anywhere}}
.board .ok{{color:var(--sage-deep);font-weight:700}}.board .bad{{color:var(--berry);font-weight:700}}
.board .crop{{position:relative;overflow:hidden;border-radius:8px;background-size:cover;
background-position:center;background-color:var(--linen)}}
.board .card{{width:171px}}
.board .card.w300{{width:300px;max-width:100%}}
"""


# ---- pieces -------------------------------------------------------------------------------

def _svg_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


_ICONS = {
    "download": '<path d="M13 4v11m-5-5 5 5 5-5M5 19h16" />',
    "terms": '<path d="M5 5h16v16H5zM9 10h8M9 14h8M9 18h5" />',
    "fix": '<path d="M5 13l5 5L21 7" />',
    "heart": '<path d="M13 21s-8-5-8-11a4.5 4.5 0 0 1 8-3 4.5 4.5 0 0 1 8 3c0 6-8 11-8 11z" />',
}


def _icon(name: str, colour: str) -> str:
    return (f'<svg viewBox="0 0 26 26" aria-hidden="true" fill="none" stroke="{colour}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            f'{_ICONS[name]}</svg>')


def _geometry(spec: dict) -> dict:
    """Canvas fractions for every banner element, so that the phone crop keeps Laura and the
    lockup and the desktop-only wings hold the product renders."""
    w, h = spec["canvas"]
    aspect = w / h
    phone = min(float(spec["phone_aspect"]), aspect)
    win = phone / aspect                       # phone window width as a canvas fraction
    l, r = 0.5 - win / 2, 0.5 + win / 2
    return {"aspect": aspect, "phone": phone, "win": (l, r),
            "who": (l + 0.0 * win, l + 0.40 * win),
            "lock": (l + 0.40 * win, r - 0.02 * win),
            "wing_l": (0.0, l), "wing_r": (r, 1.0),
            "inner_pct": aspect / phone * 100, "left_pct": -(aspect / phone - 1) / 2 * 100}


def _pos(a: float, b: float) -> str:
    return f"left:{a * 100:.3f}%;width:{(b - a) * 100:.3f}%"


def _banner(ctx: dict, *, mode: str, season: str = "evergreen", width: str | None = None,
            caption: bool = False) -> str:
    """The banner at `mode` "desktop" (whole canvas) or "phone" (centre crop of the canvas).

    `mode="auto"` is the in-page banner: phone crop by default, the whole canvas from 900 px on
    the desktop preview (the class `bn-auto` switches it in CSS)."""
    g, p, cp = ctx["geo"], ctx["p"], ctx["copy"]
    label = ctx["laura_label"]
    if mode == "phone":
        box = f"aspect-ratio:{g['phone']:.4f}"
        canvas = f"width:{g['inner_pct']:.3f}%;left:{g['left_pct']:.3f}%"
    else:
        box = f"aspect-ratio:{g['aspect']:.4f}"
        canvas = "width:100%;left:0"
    style = box + (f";width:{width}" if width else "")
    winter = season == "winter"
    sub = "Crochet patterns"
    tag = cp["tagline"] if not winter else cp["seasonal"]["title"]
    who = ""
    if ctx["laura"]:
        who = (f'<div class="el who laura" style="{_pos(*g["who"])}" role="img" '
               f'aria-label="{_esc("Laura in the banner. " + label)}">'
               f'<span class="pv">Internal preview</span></div>')
    renders = ctx["renders"]
    wing = ""
    if g["wing_r"][1] - g["wing_r"][0] > 0.08:
        right = renders.get("basket_medium") or next(iter(renders.values()), None)
        left = renders.get("hexagon_coasters")
        if right:
            wing += (f'<div class="el wing" style="{_pos(*g["wing_r"])}"><div class="arch" '
                     f'style="background-image:var(--r-{right})" role="img" aria-label="Digital '
                     f'rendering of a Brambleloop pattern design, not a photograph"><span '
                     f'class="rtag">Digital rendering</span></div></div>')
        if left:
            wing += (f'<div class="el wing" style="{_pos(*g["wing_l"])}"><div class="arch" '
                     f'style="background-image:var(--r-{left})" role="img" aria-label="Digital '
                     f'rendering of a Brambleloop pattern design, not a photograph"><span '
                     f'class="rtag">Digital rendering</span></div></div>')
    bg = (";background:radial-gradient(120% 90% at 50% 40%,#F6F1EA 0,#E8E3DA 60%,#D9D3C7 100%)"
          if winter else "")
    if ctx["lockups"].get(season):
        lock = (f'<div class="el lock" style="{_pos(*g["lock"])}"><div class="lockimg" '
                f'role="img" aria-label="{_esc("Brambleloop, crochet patterns. " + tag)}" '
                f'style="background-image:var(--lockup-{season})"></div></div>')
    else:
        lock = (f'<div class="el lock" style="{_pos(*g["lock"])}"><img src="{_esc(ctx["mark_uri"])}" '
                f'alt=""><span class="word">BRAMBLELOOP</span><span class="sub">{_esc(sub)}</span>'
                f'<span class="tag">{_esc(tag)}</span></div>')
    aria = f"{'Winter' if winter else 'Shop'} banner, {mode} view"
    strip = (f'<div class="pvs" role="note">Banner photo of Laura: {_esc(label)}</div>'
             if ctx["laura"] and caption else "")
    out = (f'<div class="bn{" ph" if mode == "phone" else ""}" style="{style}" role="group" '
            f'aria-label="{_esc(aria)}"><div class="canvas" style="{canvas}{bg}">{wing}{who}'
            f'{lock}</div></div>')
    return strip + out if strip else out


_OWNER_CACHE: dict = {}


def _owner_assets() -> dict:
    """The owner's canonical files for the page (D-FB-17), verified by their bytes, plus the
    banner's gate assessment, the measured icon choice and the owner-review candidates.
    Cached for the process (the files are immutable; a failed verification is not cached)."""
    if _OWNER_CACHE:
        return _OWNER_CACHE
    from ..brand import canonical_assets as CA
    from . import owner_banner as OB

    def uri(data: bytes, kind: str) -> str:
        return f"data:image/{kind};base64," + base64.b64encode(data).decode("ascii")

    try:
        CA.require_verified()
        out = {
            "ok": True,
            "banner_uri": uri(CA.display_bytes(CA.STOREFRONT_BANNER, 1600, quality=82),
                              "jpeg"),
            "logo_uri": uri(CA.display_bytes(CA.HERO_LOGO, 900, quality=84), "jpeg"),
            "mono_uri": uri(CA.monogram_square_png(140), "png"),
            "icon": CA.shop_icon_choice(),
            "assessment": OB.assess(),
            "hierarchy": [dict(h) for h in CA.HIERARCHY],
            "logo": CA.ASSETS[CA.HERO_LOGO].to_dict(),
            "banner": CA.ASSETS[CA.STOREFRONT_BANNER].to_dict(),
        }
        import io

        cands = []
        for c in OB.candidates():
            img = c.pop("image")
            w, h = img.size
            buf = io.BytesIO()
            img.resize((640, round(h * 640 / w))).save(buf, "JPEG", quality=80)
            cands.append({**c, "uri": uri(buf.getvalue(), "jpeg")})
        out["candidates"] = cands
    except Exception as exc:  # noqa: BLE001 - shown as an honest missing state
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    _OWNER_CACHE.update(out)
    return out


def _owner_banner(ctx: dict, *, mode: str) -> str:
    """The shop banner: the owner's canonical file as supplied, with its honest state."""
    o = ctx["owner"]
    if not o.get("ok"):
        return (f'<div class="pvs" role="note">Owner banner unavailable: {_esc(o.get("error"))}'
                f'</div><div class="bn obn" role="group" aria-label="Shop banner, {mode} view">'
                f'</div>')
    a = o["assessment"]
    label = (f"Canonical owner banner (D-FB-17), as supplied. {ctx['laura_label']}: the woman "
             f"shown is not verified as Laura.")
    strip = (f'<div class="pvs" role="note">Owner banner, as supplied (D-FB-17). Internal '
             f'preview, not yet publishable: {len(a["failed"])} checks fail and '
             f'{len(a["unknown"])} await review (owner board). The woman shown is not '
             f'verified as Laura.</div>')
    return (strip + f'<div class="bn obn" role="group" aria-label="{_esc(f"Shop banner, {mode} view")}">'
            f'<div class="art" role="img" aria-label="{_esc(label)}"></div></div>')


def _card(ctx: dict, prod: dict, frame: dict | None, cls: str = "card") -> str:
    from .preview import _price

    # Lifestyle-first (D-FB-16 item 4, D-FB-17 item 5): the lead tile is the finished piece in
    # use. None has been made for any pattern, so the lead is an honest placeholder -- never a
    # generated or borrowed picture -- and the verified rendering sits in it as the evidence
    # frame it is.
    lead = '<div class="ph lead"><span class="ph-note">No picture of the finished piece yet</span>'
    if frame is not None and frame["status"] == "VERIFIED" and frame.get("png"):
        img = (lead + f'<div class="ev" style="background-image:var(--r-{_esc(frame["build"])})" '
               f'role="img" aria-label="{_esc(frame.get("alt_text", ""))}"><span class="evl">'
               f'Rendering</span></div>')
    else:
        img = ('<div class="ph"><div class="withheld">Image withheld: the rendering did not pass '
               'its checks, and a label cannot make an inaccurate image acceptable (D-FB-7).'
               '</div>')
    badge = (f'<span class="badge">{_esc(prod["variant_count"])} sizes</span>'
             if prod["variant_count"] > 1 else "")
    return (f'<article class="{cls}">{img}{badge}</div><h3>{_esc(prod["title"])}</h3>'
            f'<div class="price">{_esc(_price(prod["price_cad"]))}</div>'
            f'<div class="dl">Digital download · PDF</div>'
            f'<div class="disc">Digital rendering, not a photograph</div></article>')


def _paras(text) -> str:
    from .preview import _paras as p

    return p(text)


def _context(db, today, viewport):
    from . import preview as V1

    surfaces, rows, roll = V1._evaluate(db, today=today)
    products = surfaces["opening_grid"].value
    frames = V1._image_rows(products)
    ident, cp, bspec = S.identity(), S.copy(), S.banner_spec()
    p, t = ident.value["palette"], ident.value["type"]
    laura, laura_err = None, None
    try:
        from . import brand_face

        laura = brand_face.image_for("owner_store_preview", for_customers=False)
    except Exception as exc:  # noqa: BLE001 - a refused portrait is shown as refused
        laura_err = f"{type(exc).__name__}: {str(exc)[:160]}"
    from .brand_face import PREVIEW_IMAGE_LABEL

    lockups = {}
    for season, line in (("evergreen", cp.value["tagline"]),
                         ("winter", cp.value["seasonal"]["title"])):
        svg = S.lockup_svg(line)
        if svg:
            lockups[season] = svg
    renders = {f["build"]: f["build"] for f in frames
               if f["status"] == "VERIFIED" and f.get("png")}
    owner = _owner_assets()
    return {"surfaces": surfaces, "rows": rows, "roll": roll, "products": products,
            "frames": frames, "by_build": {f["build"]: f for f in frames},
            "ident": ident, "copy_src": cp, "spec_src": bspec, "p": p, "t": t,
            "copy": cp.value, "geo": _geometry(bspec.value), "laura": laura,
            "laura_err": laura_err, "laura_label": PREVIEW_IMAGE_LABEL, "renders": renders,
            "mark_uri": _svg_uri(ident.value["mark_svg"]), "viewport": viewport,
            "lockups": lockups, "owner": owner,
            "icon_uri": (owner["mono_uri"] if owner.get("icon", {}).get("asset")
                         == "owner_monogram_crop" else _svg_uri(ident.value["mark_svg"]))}


def _vars_css(ctx: dict) -> str:
    """Each image exactly once, as a custom property the layout reuses."""
    out = []
    if ctx["laura"]:
        out.append(f'--laura:url("{ctx["laura"]["data_uri"]}")')
    if ctx.get("owner", {}).get("banner_uri"):
        out.append(f'--owner-banner:url("{ctx["owner"]["banner_uri"]}")')
        out.append(f'--owner-mono:url("{ctx["owner"]["mono_uri"]}")')
    for f in ctx["frames"]:
        if f["build"] in ctx["renders"]:
            uri = "data:image/png;base64," + base64.b64encode(f["png"]).decode("ascii")
            out.append(f'--r-{f["build"]}:url("{uri}")')
    for season, svg in ctx["lockups"].items():
        out.append(f'--lockup-{season}:url("{_svg_uri(svg)}")')
    return ":root{" + ";".join(out) + "}" if out else ""


def _pbar(viewport: str, variant: str) -> str:
    from .brand_face import PREVIEW_IMAGE_LABEL
    from .preview import PREVIEW_LABEL

    links = []
    for vp, lab in (("mobile", "Phone 390"), ("desktop", "Desktop 1280")):
        on = "on" if (vp == viewport and variant == VARIANT) else ""
        links.append(f'<a class="{on}" href="?viewport={vp}&amp;variant={VARIANT}">{lab}</a>')
    links.append(f'<a class="{"on" if variant == COMPARE else ""}" href="?viewport={_esc(viewport)}'
                 f'&amp;variant={COMPARE}">Compare with v1</a>')
    links.append(f'<a href="?viewport={_esc(viewport)}&amp;variant=standard">v1 (rejected)</a>')
    return (f'<div class="pbar" role="note"><strong>{_esc(PREVIEW_LABEL)}</strong>'
            f'<nav aria-label="Preview options">{"".join(links)}</nav>'
            f'<span class="pnote">Owner Store Preview v2 — a proposal, never publishable. Laura '
            f'images: {_esc(PREVIEW_IMAGE_LABEL)}. Layout approximates a shop page; it is not '
            f'Etsy\'s.</span></div>')


def _policies(ctx: dict) -> list[tuple[str, str]]:
    """(label, text) for each policy block: lane C's words where it supplies them, else the
    drafted surfaces in `content`."""
    s, cp = ctx["surfaces"], ctx["copy"]
    pol = cp.get("policies") or {}
    out = [(s["policy_delivery"].label, pol.get("delivery") or s["policy_delivery"].value),
           (s["policy_returns"].label, pol.get("returns") or s["policy_returns"].value),
           (s["policy_licence"].label, s["policy_licence"].value),
           (s["policy_privacy"].label, "\n\n".join(x for x in (pol.get("privacy"),
                                                               pol.get("privacy_addendum")) if x)
            or s["policy_privacy"].value),
           (s["disclosures"].label, cp.get("disclosure") or s["disclosures"].value)]
    return out


def _shop(ctx: dict) -> str:
    """The shop page itself. The `fold` wrapper is the designed first screen."""
    s, cp, p = ctx["surfaces"], ctx["copy"], ctx["p"]
    name = s["shop_name"].value["display"]
    label = ctx["laura_label"]
    heads = cp.get("headings") or {}
    products = ctx["products"]
    shown = [x for x in s["sections"].value if x["shown"]]
    names = cp.get("sections") or {}
    secs = (f'<li class="on">All<span class="n">{len(products)}</span></li>'
            + "".join(f'<li>{_esc(names.get(x["slug"], x["name"]))}<span class="n">'
                      f'{_esc(x["listings"])}</span></li>' for x in shown))
    cards = "".join(_card(ctx, pr, ctx["by_build"].get(pr["representative"]["build"]))
                    for pr in products)
    caption = cp.get("seller_caption") or "Laura · Brambleloop's AI founder"
    role = caption.split("·", 1)[1].strip() if "·" in caption else "Brambleloop's AI founder"
    ic = ctx["owner"].get("icon") or {}
    icon_note = (" (small-size derivative of the owner artwork)" if ic.get("derivative")
                 else " (owner artwork)")
    owner = ""
    if ctx["laura"]:
        owner = (f'<div class="owner-card"><div class="av laura" role="img" aria-label="'
                 f'{_esc("Laura, brand-face card. " + label)}"></div><div><b>Laura</b>'
                 f'<span>{_esc(role)}</span><small>{_esc(label)}</small></div></div>')
    fold = (
        f'<div class="fold" data-fold="first-screen">'
        f'{_owner_banner(ctx, mode="phone" if ctx["viewport"] == "mobile" else "desktop")}'
        f'<header class="sh"><img class="icon" src="{_esc(ctx["icon_uri"])}" alt="{_esc(name)} '
        f'shop icon{_esc(icon_note)}"><div><h1>{_esc(name)}</h1><p class="title">{_esc(cp["shop_title"])}</p>'
        f'<p class="meta">Canada · Digital crochet patterns · New shop, no reviews yet</p></div>'
        f'<div class="acts"><span class="btn solid" aria-disabled="true">Follow shop</span>'
        f'<span class="btn" aria-disabled="true">Message</span></div>{owner}</header>'
        f'<div class="ann"><b>Announcement</b>{_esc(cp["announcement"])}</div>'
        f'<div class="shop"><aside><ul class="secs" aria-label="Shop sections">{secs}</ul>'
        f'<div class="side">Questions? Message us on Etsy.</div></aside>'
        f'<main class="grid" aria-label="Items">{cards}</main></div>'
        f'</div>')
    icons = ("download", "terms", "fix", "heart")
    trust = "".join(f'<li>{_icon(icons[i % 4], p["sage_deep"])}<b>{_esc(tr["title"])}</b>'
                    f'<span>{_esc(tr["text"])}</span></li>' for i, tr in enumerate(cp["trust"]))
    if ctx["laura"]:
        portrait = (f'<div class="portrait laura" role="img" aria-label="'
                    f'{_esc("Laura, Brambleloop founder portrait. " + label)}">'
                    f'<span class="pv">{_esc(label)}</span></div>'
                    f'<div class="byline"><b>Laura</b><span>{_esc(role)}</span></div>')
    else:
        portrait = (f'<div class="portrait"><span class="pv">Laura portrait unavailable: '
                    f'{_esc(ctx["laura_err"])}</span></div>')
    intro = f'<p>{_esc(cp["laura_intro"])}</p>' if cp.get("laura_intro") else ""
    about_p = "".join(f"<p>{_esc(x)}</p>" for x in cp["about"])
    proof = ""
    if cp.get("proof"):
        proof = (f'<div class="proof"><h3>{_esc(cp["proof_title"])}</h3><ul>'
                 + "".join(f"<li>{_esc(x)}</li>" for x in cp["proof"]) + "</ul></div>")
    faqs = cp.get("faqs") or [{"question": f["question"], "answer": f["answer"]}
                              for f in s["faq"].value]
    faq = "".join(f'<details{" open" if i == 0 else ""}><summary>{_esc(f["question"])}</summary>'
                  f'<div class="a">{_paras(f["answer"])}</div></details>'
                  for i, f in enumerate(faqs))
    pol = "".join(f'<details><summary>{_esc(lab)}</summary><div class="a">{_paras(txt)}</div>'
                  f'</details>' for lab, txt in _policies(ctx))
    from .content import SUPPORT_CONTACT

    support = cp.get("support") or SUPPORT_CONTACT
    about_h = heads.get("about") or f"About {name}"
    hero = ""
    if ctx["owner"].get("ok"):
        hero = (f'<img class="herologo" src="{_esc(ctx["owner"]["logo_uri"])}" alt="Brambleloop, '
                f'crochet patterns: Patterns for a More Handmade Life (the owner\'s logo '
                f'artwork, as supplied)">')
    return (
        f'<div class="frame">{fold}'
        f'<ul class="trust" aria-label="Why makers choose Brambleloop">{trust}</ul>'
        f'<section class="about"><div>{portrait}</div><div>{hero}<p class="kicker">'
        f'{_esc(heads.get("laura") or "About the shop")}</p>'
        f'<h2>{_esc(about_h)}</h2>{intro}{about_p}{proof}'
        f'<p class="dl" style="margin-top:12px;font-size:12.5px;color:var(--muted)">'
        f'{_esc(cp["image_note"])}</p></div></section>'
        f'<section class="help"><div><h2>{_esc(heads.get("faq") or "Questions")}</h2>{faq}</div>'
        f'<div><h2>{_esc(heads.get("policies") or "Shop policies")}</h2>{pol}'
        f'<div class="support"><b>{_esc(heads.get("support") or "Questions and support")}.</b> '
        f'{_esc(support)}</div></div></section>'
        f'<div class="foot"><span class="fw">BRAMBLELOOP</span>Preview — not live · prices in CAD '
        f'· taxes handled by Etsy at checkout</div></div>')


def _board(ctx: dict, now: datetime) -> str:
    from . import brand_face
    from .preview import VIEWPORTS

    p, g, label = ctx["p"], ctx["geo"], ctx["laura_label"]
    mark = ctx["mark_uri"]
    srcs = "".join(
        f'<tr><td>{_esc(k)}</td><td class="{"ok" if v.source == S.PEER else "bad"}">'
        f'{_esc(v.source)}</td><td><code>{_esc(v.origin)}</code> {_esc("; ".join(v.notes))}</td></tr>'
        for k, v in (("Brand system (lane A)", ctx["ident"]), ("Copy (lane C)", ctx["copy_src"]),
                     ("Banner crop numbers (lane I)", ctx["spec_src"])))
    o = ctx["owner"]
    icon_uri = ctx["icon_uri"]
    icons = "".join(f'<figure class="ic"><img src="{_esc(icon_uri)}" alt="shop icon at {n} px" '
                    f'width="{n}" height="{n}">{n} px</figure>' for n in (16, 32, 40, 48, 70))
    gw = ctx["spec_src"].value["canvas"]
    owner_board = _owner_board(ctx) if o.get("ok") else (
        f'<p class="bad">Owner canonical files unavailable: {_esc(o.get("error"))}</p>')

    def ob(width: int, aspect: float, size: str, pos: str, cap: str) -> str:
        return (f'<figure class="bnwrap" style="width:{width}px"><div class="ob" role="img" '
                f'aria-label="{_esc("Owner banner, " + cap + ". " + label)}" style="aspect-ratio:'
                f'{aspect:.4f};background-size:{size};background-position:{pos}"></div>'
                f'{_esc(cap)}</figure>')

    banners = (
        ob(640, 1983 / 793, "100% 100%", "center", "As supplied: 1983×793 (2.50:1), "
           "the canonical owner banner")
        + ob(640, gw[0] / gw[1], "100% auto", "center", f"Desktop: whole canvas {gw[0]}×"
             f"{gw[1]} — the exact file centre-cropped to 4:1 (one possible Etsy fit; Etsy "
             f"does not publish its rule)")
        + ob(390, g["phone"], f"{gw[0] / gw[1] / g['phone'] * 100:.1f}% auto", "center",
             f"Phone 390 px: centre crop {g['phone']:.2f}:1 of that canvas (UNVERIFIED "
             f"assumption)")
        + ob(320, g["phone"], f"{gw[0] / gw[1] / g['phone'] * 100:.1f}% auto", "center",
             "Small phone 320 px (awkward crop check)"))
    seasonal = (
        f'<p>{_esc(ctx["copy"]["seasonal"]["text"])} A seasonal banner would replace the '
        f'canonical owner banner, which needs a new owner decision (D-FB-17); until then the '
        f'season changes the announcement, not the banner.</p><div class="row">'
        + ob(640, 1983 / 793, "100% 100%", "center", "Winter, desktop: canonical banner "
             "unchanged")
        + ob(390, 1983 / 793, "100% 100%", "center", "Winter, phone crop: canonical banner "
             "unchanged") + '</div>')
    seller = ""
    if ctx["laura"]:
        seller = "".join(
            f'<figure><div class="crop laura" style="width:{n}px;height:{n}px;border-radius:'
            f'{"50%" if c else "8px"};background-image:var(--laura);background-position:50% 22%" '
            f'role="img" aria-label="{_esc(f"Laura {n} px. " + label)}"></div>{n} px '
            f'{"circle" if c else "square"}</figure>'
            for n, c in ((120, False), (72, True), (40, True)))
    cards = []
    for prod in ctx["products"][:2]:
        fr = ctx["by_build"].get(prod["representative"]["build"])
        cards.append(_card(ctx, prod, fr, "card"))
    dark_cards = "".join(cards)
    first = next(iter(ctx["renders"]), None)
    crops = ""
    if first:
        crops = "".join(
            f'<figure><div class="crop" style="width:{w}px;height:{h}px;background-image:'
            f'var(--r-{first})" role="img" aria-label="Digital rendering, {r} crop"></div>{r} '
            f'({why})</figure>'
            for w, h, r, why in ((140, 140, "square", "shop grid"),
                                 (140, 105, "landscape 4:3", "ratio UNVERIFIED assumption: Etsy does not publish it"),
                                 (112, 140, "portrait 4:5", "ratio UNVERIFIED assumption: Etsy does not publish it")))
    gates = "".join(f'<tr><td>{_esc(x["gate"])}</td><td class="{"ok" if x["status"] == "PASS" else "bad"}">'
                    f'{_esc(x["status"])}</td><td>{_esc(x["why"])}</td></tr>'
                    for x in brand_face.gate_chain())
    places = "".join(f"<tr><td>{_esc(x['where'])}</td><td>{_esc(x['laura'])}</td>"
                     f"<td>{_esc(x['why'])}</td></tr>" for x in brand_face.PLACEMENTS)
    facts = "".join(f"<li>{_esc(x)}</li>" for x in S.etsy_notes()) or (
        "<li>lane I constraints not available</li>")
    facts += ("<li>The desktop card shows Laura as the shop's brand face. Etsy's own profile "
              "photo belongs to the signed-in account holder, so Laura is not proposed for it; "
              "where she may appear on Etsy is an owner decision (lane I checklist B3).</li>")
    pairs = "".join(
        f'<tr><td>{_esc(r)}</td><td>{_esc(fg)} on {_esc(bg)}</td><td class="'
        f'{"ok" if contrast(fg, bg) >= m else "bad"}">{contrast(fg, bg):.2f}:1 (min {m})</td></tr>'
        for r, fg, bg, m in text_pairs(p))
    return (
        f'<section class="board" aria-label="Owner review board">'
        f'<h2>Owner review board — not part of the shop page</h2>'
        f'<p>Generated {_esc(now.isoformat())} · {_esc(ctx["viewport"])} '
        f'{VIEWPORTS[ctx["viewport"]]} px · never publishable. Every Laura image is her approved '
        f'canonical portrait, verified by its bytes: <b>{_esc(label)}</b>. The owner\'s '
        f'canonical banner (D-FB-17) is shown as supplied; its woman is not verified as Laura, '
        f'so it carries the same internal label.</p>'
        f'<h3>Sources</h3><table><tbody>{srcs}</tbody></table>'
        f'{owner_board}'
        f'<h3>Shop icon at real sizes</h3><p>Upload: a 500×500 square PNG (Etsy: logo at least 500×500, recommended 500×500; VERIFIED by lane I). Shown: {_esc((o.get("icon") or {}).get("label", "A3 mark"))}.</p><div class="row">{icons}</div>'
        f'<div class="row dark">{icons}<span>Dark surround (app dark mode)</span></div>'
        f'<h3>Banner: as supplied, Etsy canvas and phone crops</h3><div class="row">{banners}</div>'
        f'<p>{_esc(ctx["spec_src"].value["basis"])}. The measured identity block is '
        f'{_esc((o.get("assessment") or {}).get("identity_block"))} in the 1983×793 file.</p>'
        f'<h3>Laura brand-face crops (banner/About). Not proposed for Etsy\'s profile photo, which belongs to the account holder (lane I checklist B3)</h3><div class="row">{seller}</div>'
        f'<h3>Listing cards at grid size, light and dark</h3><div class="row">{dark_cards}</div>'
        f'<div class="row dark">{dark_cards}</div>'
        f'<h3>Awkward crops of a listing image</h3><div class="row">{crops}</div>'
        f'<h3>Seasonal extension</h3>{seasonal}'
        f'<h3>Text contrast (WCAG)</h3><table><tbody>{pairs}</tbody></table>'
        f'<h3>Etsy facts that shape this layout (lane I)</h3><ul>{facts}</ul>'
        f'<h3>Customer-facing gates for Laura imagery</h3><table><tbody>{gates}</tbody></table>'
        f'<h3>Where Laura appears</h3><table><tbody>{places}</tbody></table>'
        f'</section>')


LISTING_ORDER = (
    ("1", "Lifestyle: the finished piece in use, in a home", None,
     "no qualified lifestyle frame exists for any pattern; nothing is generated or borrowed "
     "to fill it (Product Truth, F-852)"),
    ("2", "Finished object (disclosed render, hero)", "hero",
     "the lead image today: a digital rendering of the finished design, verified on its bytes"),
    ("3", "Scale (disclosed render)", "scale", "evidence frame: size with a centimetre scale"),
    ("4", "Detail (disclosed render)", "detail", "evidence frame: the stitch up close"),
    ("5", "Chart, yarn, construction, what's in the download", None,
     "evidence frames after the desire frames; the checks behind them stay deeper down"),
)


def _owner_board(ctx: dict) -> str:
    """Owner board sections for the D-FB-17 assets: hierarchy, measured icon choice, the
    banner's publication gates, the owner-review candidates and the truth findings."""
    o, label = ctx["owner"], ctx["laura_label"]
    a = o["assessment"]
    hier = "".join(f"<tr><td>{_esc(h['use'])}</td><td>{_esc(h['kind'])}</td>"
                   f"<td>{_esc(h['where'])}</td><td>{_esc(h['label'])}</td></tr>"
                   for h in o["hierarchy"])
    ic = o["icon"]
    rep = ic["report"]["measurements"]
    irows = "".join(
        f'<tr><td>{_esc(view)}</td><td>{px} px</td><td>{m["contrast"]:.2f}:1</td>'
        f'<td>{m["coverage"]:.0%}</td><td class="{"ok" if m["ok"] else "bad"}">'
        f'{"legible" if m["ok"] else "illegible: " + _esc("; ".join(m["problems"]))}</td></tr>'
        for view, sizes in rep.items() for px, m in sorted(sizes.items()) if px <= 160)
    pair = "".join(
        f'<figure class="mono"><img src="{_esc(o["mono_uri"])}" alt="owner monogram at {n} px" '
        f'width="{n}" height="{n}">owner {n} px</figure>'
        f'<figure class="mono"><img src="{_esc(ctx["mark_uri"])}" alt="A3 micro-mark at {n} px" '
        f'width="{n}" height="{n}">A3 micro-mark {n} px</figure>' for n in (40, 70))
    gates = "".join(
        f'<tr><td>{_esc(g["gate"])}</td><td class="{"ok" if g["status"] == "PASS" else "bad"}">'
        f'{_esc(g["status"])}</td><td>{_esc(g["why"])}'
        + (f' <i>Review: {_esc(g["review"])}</i>' if g.get("review") else "")
        + f'</td></tr>' for g in a["gates"])
    cands = "".join(
        f'<figure class="cand bnwrap" style="width:640px"><img src="{_esc(c["uri"])}" alt="'
        f'{_esc("Candidate " + c["id"] + ", owner review required. " + label)}">'
        f'<b>{_esc(c["id"])}</b> — {_esc(c["status"])}, adopted: {_esc(c["adopted"])}. '
        f'{_esc(c["note"])} Fixes: {_esc(", ".join(c["fixes"]))}. Does not fix: '
        f'{_esc(", ".join(c["does_not_fix"]))}.</figure>' for c in o["candidates"])
    from . import owner_banner as OB

    nav = next((g for g in a["gates"] if g["gate"] == "nav_categories_truth"), None)
    findings = ""
    if nav is not None:
        findings += (f"<li>Banner category line names {_esc(', '.join(nav['evidence']['empty']) or 'nothing empty')}"
                     f": {_esc(nav['why'])}.</li>")
    try:
        footer = OB._nav_truth(OB.LOGO_FOOTER_NAV, OB._catalogue(None))
        findings += (f"<li>Logo footer (HOME · BABY · GIFTS · SEASONAL) names "
                     f"{_esc(', '.join(footer['empty']) or 'no empty category')}, which hold "
                     f"no pattern today.</li>")
    except Exception as exc:  # noqa: BLE001
        findings += f"<li>Logo footer check unavailable: {_esc(type(exc).__name__)}</li>"
    findings += ("<li>These are the owner's pixels: this preview does not edit them. Options "
                 "are the owner's: list patterns in those sections before publishing, or "
                 "decide on the wording.</li>")
    order = "".join(
        f"<tr><td>{n}</td><td>{_esc(what)}</td><td class=\"{'ok' if view == 'hero' else 'bad' if view is None and n == '1' else ''}\">"
        f"{'AVAILABLE' if view == 'hero' else 'NOT MADE' if n == '1' else 'LATER'}</td>"
        f"<td>{_esc(why)}</td></tr>" for n, what, view, why in LISTING_ORDER)
    return (
        f'<h3>Canonical owner assets (D-FB-17)</h3><p>The owner\'s logo artwork, exact '
        f'({_esc(o["logo"]["sha256"][:12])}, {o["logo"]["size"][0]}×{o["logo"]["size"][1]}), is '
        f'the hero identity. Lane A3\'s vectors are a supporting production system, labelled '
        f'wherever they appear.</p><div class="row"><figure style="width:300px;max-width:100%">'
        f'<img src="{_esc(o["logo_uri"])}" alt="Owner logo artwork, as supplied" '
        f'style="width:100%;height:auto">Hero lockup: owner artwork, as supplied</figure></div>'
        f'<table><thead><tr><th>Use</th><th>Asset</th><th>Where</th><th>Label</th></tr></thead>'
        f'<tbody>{hier}</tbody></table>'
        f'<h3>Shop icon: exact artwork first, measured</h3><p>{_esc(ic["label"])}. '
        f'{_esc(ic["why"])}.</p><div class="row">{pair}</div>'
        f'<table><thead><tr><th>Artwork</th><th>Size</th><th>Contrast</th><th>Coverage</th>'
        f'<th>Result</th></tr></thead><tbody>{irows}</tbody></table>'
        f'<h3>Owner banner: every publication gate on the exact file</h3><p>Status '
        f'<b>{_esc(a["status"])}</b>: {len(a["passed"])} pass, {len(a["failed"])} fail, '
        f'{len(a["unknown"])} unknown (UNKNOWN blocks like FAIL). Visible words: '
        f'{_esc(a["visible_text_source"])}.</p>'
        f'<table><thead><tr><th>Gate</th><th>Status</th><th>Evidence</th></tr></thead>'
        f'<tbody>{gates}</tbody></table>'
        f'<h3>Minimal reframes for the 4:1 canvas — OWNER_REVIEW_REQUIRED, none adopted</h3>'
        f'<p>Deterministic, no owner pixel changed. They answer only the size gates; the '
        f'others still stop the file.</p><div class="row">{cands}</div>'
        f'<h3>Truth findings for the owner</h3><ul>{findings}</ul>'
        f'<h3>Listing image order (lifestyle first)</h3><table><tbody>{order}</tbody></table>')


def _doc(title: str, viewport: str, css: str, body: str) -> str:
    return (f'<!doctype html>\n<html lang="en-CA"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<meta name="robots" content="noindex,nofollow">\n<title>{_esc(title)}</title>\n'
            f'<style>{css}</style></head>\n<body class="vp-{_esc(viewport)}">\n{body}\n</body></html>')


def render(db, viewport: str, *, now: datetime, today=None) -> str:
    """The v2 Owner Store Preview page."""
    from .preview import _owner_panel

    ctx = _context(db, today, viewport)
    css = _vars_css(ctx) + _css(ctx["p"], ctx["t"])
    name = ctx["surfaces"]["shop_name"].value["display"]
    readiness = _owner_panel(ctx["rows"], ctx["roll"], ctx["surfaces"], ctx["frames"], now,
                             viewport).replace('class="owner"', 'class="board"', 1)
    body = (_pbar(viewport, VARIANT) + _shop(ctx) + _board(ctx, now) + readiness)
    return _doc(f"{name} — Owner Store Preview v2 (not live)", viewport, css, body)


# ---- comparison against the rejected v1 ---------------------------------------------------

def fold_v1(html: str) -> str:
    """v1's designed top region: banner, header, trust strip and announcement."""
    frame = html.split('<div class="frame">', 1)[1]
    return frame.split('<div class="shop">', 1)[0]


def fold_v2(html: str) -> str:
    """v2's top region with the same scope as `fold_v1`: banner, header and announcement
    (the sections and first cards below them are what replaced v1's trust strip)."""
    frame = html.split('data-fold="first-screen">', 1)[1]
    return frame.split('<div class="shop">', 1)[0]


def static_metrics(v1_html: str, v2_html: str) -> dict:
    """Deterministic comparison over the designed top region of each page."""
    out = {}
    for key, html, fold in (("v1", v1_html, fold_v1), ("v2", v2_html, fold_v2)):
        text = visible_text(fold(html))
        words = re.findall(r"[A-Za-z][A-Za-z'’-]*", text)
        hits = jargon_hits(text)
        out[key] = {"top_words": len(words), "top_jargon": len(hits),
                    "top_jargon_terms": sorted(set(hits)),
                    "page_jargon": len(jargon_hits(visible_text(
                        html.split('<section class="owner"', 1)[0].split(
                            '<section class="board"', 1)[0])))}
    return out


V1_PAIRS = (("body", "#1A2B3C", "#FFFFFF"), ("secondary", "#5C6370", "#FFFFFF"),
            ("secondary on chrome", "#5C6370", "#F6F2E8"), ("ribbon", "#FAF6EB", "#6E1F2A"),
            ("tile tags", "#5C6370", "#FFFFFF"), ("announce heading", "#5C6370", "#FAF6EB"))


def measured(root: Path | None = None) -> dict | None:
    """Browser-measured metrics committed as evidence (Chromium via Playwright), or None."""
    root = root or Path(__file__).resolve().parents[3]
    path = root / EVIDENCE_REL
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 - absent evidence is reported as not measured
        return None


def _scope_css(css: str, scope: str) -> str:
    """Prefix every selector of a flat stylesheet (plus one level of @media) with `scope`."""
    def fix_sel(sel: str) -> str:
        parts = []
        for x in sel.split(","):
            x = x.strip()
            if not x:
                continue
            if x in (":root", "html", "body"):
                parts.append(scope)
            elif x.startswith((".vp-mobile ", ".vp-desktop ")):
                vp, rest = x.split(" ", 1)
                parts.append(f"{scope}{vp} {rest}")
            else:
                parts.append(f"{scope} {x}")
        return ",".join(parts)

    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        head = css[i:j].strip()
        if head.startswith("@media"):
            depth, k = 1, j + 1
            while k < n and depth:
                depth += {"{": 1, "}": -1}.get(css[k], 0)
                k += 1
            out.append(head + "{" + _scope_css(css[j + 1:k - 1], scope) + "}")
            i = k
            continue
        k = css.find("}", j)
        out.append(fix_sel(head) + css[j:k + 1])
        i = k + 1
    return "\n".join(out)


def render_compare(db, viewport: str, *, now: datetime, today=None) -> str:
    """v2 beside the rejected v1: both first screens at 390 x 844, with the measured change."""
    from . import preview as V1

    v1 = V1.render_preview(db, "mobile", now=now, today=today, variant="standard")
    v2 = render(db, "mobile", now=now, today=today)
    ctx = _context(db, today, "mobile")
    sm = static_metrics(v1, v2)
    v1_css = v1.split("<style>", 1)[1].split("</style>", 1)[0]
    v2_css = v2.split("<style>", 1)[1].split("</style>", 1)[0]
    v1_frame = ('<div class="frame">' + v1.split('<div class="frame">', 1)[1]
                .split('<section class="about">', 1)[0] + "</div>")
    v2_frame = '<div class="frame">' + v2.split('<div class="frame">', 1)[1].split(
        '<ul class="trust"', 1)[0] + "</div>"
    m = measured()
    rows = [("Technical terms in the top region", sm["v1"]["top_jargon"], sm["v2"]["top_jargon"],
             "static: JARGON list over banner, header, announcement (+ v1 trust strip)"),
            ("Words in the top region", sm["v1"]["top_words"], sm["v2"]["top_words"],
             "static: same region"),
            ("Technical terms on the whole shop page", sm["v1"]["page_jargon"],
             sm["v2"]["page_jargon"], "static: shop page, owner panel excluded"),
            ("Lowest text contrast in the palette",
             f"{min(contrast(f, b) for _, f, b in V1_PAIRS):.2f}:1",
             f"{min(contrast(f, b) for _, f, b, _ in text_pairs(ctx['p'])):.2f}:1",
             "static: declared text/background pairs (WCAG AA body = 4.5)")]
    if m:
        mv1, mv2 = m.get("v1_mobile", {}), m.get("v2_mobile", {})
        for key, lab in (("image_share_pct", "Image share of the first screen (%)"),
                         ("words_first_screen", "Words on the first screen"),
                         ("jargon_first_screen", "Technical terms on the first screen"),
                         ("tap_targets_under_44", "Tap targets under 44 px"),
                         ("distinct_font_sizes", "Distinct text sizes on the first screen"),
                         ("headline_to_body_ratio", "Shop name size / body size"),
                         ("min_contrast_first_screen", "Lowest text contrast, first screen"),
                         ("horizontal_overflow_px", "Horizontal overflow at 390 px")):
            rows.append((lab, mv1.get(key, "UNKNOWN"), mv2.get(key, "UNKNOWN"),
                         f"measured: {m.get('basis', 'Chromium')} at {m.get('as_of', '?')}"))
    else:
        rows.append(("Browser-measured metrics", "UNKNOWN", "UNKNOWN",
                     f"not measured: {EVIDENCE_REL} absent"))
    table = "".join(f"<tr><td>{_esc(a)}</td><td>{_esc(b)}</td><td>{_esc(c)}</td>"
                    f"<td>{_esc(d)}</td></tr>" for a, b, c, d in rows)
    css = (_vars_css(ctx) + _css(ctx["p"], ctx["t"]).split("/* banner:", 1)[0]
           + "\n" + _scope_css(v1_css, ".s-v1") + "\n"
           + _scope_css(v2_css.split("}", 1)[1] if v2_css.startswith(":root{--laura") else v2_css,
                        ".s-v2")
           + """
.cmp{display:flex;flex-wrap:wrap;gap:24px;justify-content:center;padding:18px 12px}
.cmp figure{margin:0;width:390px;max-width:100%}
.cmp figcaption{font-weight:700;margin:0 0 6px}
.screen{width:390px;max-width:100%;height:844px;overflow:hidden;border:1px solid #BDB5A6;
border-radius:18px;background:#fff;position:relative}
.screen .frame{max-width:390px !important}
.mt{max-width:900px;margin:0 auto 30px;padding:0 16px}
.mt table{width:100%;border-collapse:collapse;font-size:13px;background:#FFFDF9}
.mt th,.mt td{text-align:left;padding:6px;border-bottom:1px solid #D6CEBC;vertical-align:top;
overflow-wrap:anywhere}
""")
    body = (_pbar(viewport, COMPARE)
            + '<div class="mt"><h1 style="font-size:22px">v2 proposal beside the rejected v1</h1>'
            '<p>Both shops as a phone shows them: the first 390 × 844 px, preview bars excluded. '
            'Static figures are computed from the pages on every load; measured figures come '
            'from the committed browser evidence and say when they were taken.</p></div>'
            f'<div class="cmp"><figure><figcaption>v1 — rejected</figcaption><div class="screen '
            f's-v1 vp-mobile">{v1_frame}</div></figure><figure><figcaption>v2 — proposed'
            f'</figcaption><div class="screen s-v2 vp-mobile">{v2_frame}</div></figure></div>'
            f'<div class="mt"><table><thead><tr><th>Metric</th><th>v1</th><th>v2</th>'
            f'<th>Basis</th></tr></thead><tbody>{table}</tbody></table></div>')
    return _doc("Brambleloop Studio — v2 vs v1 store preview (not live)", viewport, css, body)
