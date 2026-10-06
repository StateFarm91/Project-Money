"""Owner Store Preview (F-926) and the Command Center provider for store readiness.

`render_preview(db, viewport)` draws the whole shop the way a buyer would meet it -- banner,
icon, title, announcement, trust strip, sections, the Launch-0 grid with prices and images,
About, policies, FAQ, support -- as one self-contained HTML document at phone (390 px) or
desktop (1280 px) width, followed by an owner-only readiness panel.

Rules the renderer keeps, each tested:
* every value enters the page through `app.security.esc`; no inline script, no external URL
  (images are `data:` URIs, which the app CSP's `img-src 'self' data:` allows);
* every page says "Preview -- not live" at the top, and nothing on it is a working control;
* the layout is Brambleloop's own approximation of a marketplace shop page -- no Etsy CSS,
  logo or trademark;
* listing images are disclosed deterministic renders produced *at preview time* from the
  current CIR and shown only when `visual.render_verification.verify` PASSes on those exact
  bytes (D-FB-7: a disclosure never makes an inaccurate image acceptable). A frame that does
  not verify is withheld and the tile says so;
* the shop shows no review, sales or favourite figures, because there are none: it says
  "New shop -- no reviews yet".
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

from . import content as C
from . import readiness as R

PREVIEW_PATH = "/cc/store-preview"
VIEWPORTS = {"mobile": 390, "desktop": 1280}
PREVIEW_LABEL = "Preview — not live"

_FRAMES: dict[tuple[str, str], dict] = {}


def _now(now: datetime | None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


# ---- listing images: rendered and verified now, or withheld ------------------------------

def hero_frame(build_key: str) -> dict:
    """The hero frame of one Launch-0 variant, rendered from its CIR and verified on its bytes.

    Cached per (build, CIR fingerprint) for the life of the process, so the 2000 px render runs
    once per design change rather than once per page view.
    """
    from ..products import launch0 as l0

    cir = l0.cir_for(build_key)
    key = (build_key, cir.fingerprint)
    if key in _FRAMES:
        return _FRAMES[key]
    try:
        from ..publish import disclosed_listing
        from ..visual import disclosed_render, render_verification

        frame = disclosed_render.render(cir, "hero")
        verdict = render_verification.verify(frame.png, cir=cir, view="hero")
        caption = disclosed_listing.caption_in_image(frame.png, cir)
        ok = verdict.get("status") == "PASS" and caption.get("status") == "PASS"
        out = {"build": build_key, "cir_slug": cir.slug, "cir_fingerprint": cir.fingerprint,
               "status": "VERIFIED" if ok else "WITHHELD",
               "verifier_status": verdict.get("status"),
               "verifier_version": verdict.get("verifier_version"),
               "failed": list(verdict.get("failed") or [])[:6],
               "caption_status": caption.get("status"),
               "sha256": hashlib.sha256(frame.png).hexdigest(),
               "alt_text": disclosed_listing.alt_text(frame.manifest, cir),
               "png": frame.png if ok else None}
    except Exception as exc:  # noqa: BLE001 - a refusal is a withheld image, not a crash
        out = {"build": build_key, "cir_slug": cir.slug, "cir_fingerprint": cir.fingerprint,
               "status": "WITHHELD", "verifier_status": "NOT_RUN",
               "why": f"{type(exc).__name__}: {str(exc)[:200]}", "png": None}
    _FRAMES[key] = out
    return out


def _image_rows(products: list[dict]) -> list[dict]:
    return [hero_frame(p["representative"]["build"]) for p in products]


# ---- the provider ------------------------------------------------------------------------

def _evaluate(db, today=None) -> tuple[dict, list[dict], dict]:
    surfaces = C.build(db, today=today)
    rows = R.evaluate(surfaces)
    return surfaces, rows, R.rollup(rows)


def summary(db, *, verify_images: bool = False, now: datetime | None = None) -> dict:
    """Store-surface readiness for the Owner Command Center (lane contract, provider F).

    `verify_images=True` also renders and verifies the Launch-0 hero frames (seconds, once
    per process); by default the image item says it was not verified in this call rather
    than reporting a result it did not compute.
    """
    as_of = _now(now).isoformat()
    try:
        surfaces, rows, roll = _evaluate(db)
    except Exception as exc:  # noqa: BLE001 - the provider never raises
        return {"status": "UNKNOWN", "as_of": as_of, "basis": "unknown", "items": [],
                "sources": [], "reason": f"{type(exc).__name__}: {str(exc)[:200]}",
                "preview_path": PREVIEW_PATH}
    items = []
    for r in rows:
        worst = [f for f in r["findings"]
                 if R._SEV_STATUS.get(f["severity"]) == r["status"]][:3]
        items.append({"key": r["key"], "label": r["label"], "group": r["group"],
                      "status": r["status"], "findings": len(r["findings"]),
                      "top_findings": [f"{f['code']}: {f['detail']}" for f in worst],
                      "entry": r["entry"], "etsy_location": r["etsy_location"],
                      "source": r["source"], "entered_on_etsy": r["entered_on_etsy"],
                      "basis": "measured"})
    status = roll["status"]
    products = surfaces["opening_grid"].value
    if verify_images:
        frames = _image_rows(products)
        bad = [f for f in frames if f["status"] != "VERIFIED"]
        items.append({"key": "listing_images", "label": "Listing hero images (disclosed "
                      "renders)", "group": "merch",
                      "status": R.FAIL if bad else R.READY, "findings": len(bad),
                      "top_findings": [f"{f['cir_slug']}: {f['verifier_status']}" for f in bad],
                      "entry": "listing upload", "etsy_location": "listing images",
                      "source": "visual.disclosed_render + visual.render_verification",
                      "entered_on_etsy": C.UNKNOWN, "basis": "measured",
                      "frames": [{k: v for k, v in f.items() if k != "png"} for f in frames]})
        if bad:
            status = "BLOCKED"
    else:
        items.append({"key": "listing_images", "label": "Listing hero images (disclosed "
                      "renders)", "group": "merch", "status": "UNKNOWN", "findings": 0,
                      "top_findings": ["not verified in this call; the preview renders and "
                                       "verifies them on load"],
                      "entry": "listing upload", "etsy_location": "listing images",
                      "source": "visual.disclosed_render + visual.render_verification",
                      "entered_on_etsy": C.UNKNOWN, "basis": "unknown"})
    return {
        "status": status, "as_of": as_of, "basis": "measured", "items": items,
        "sources": sorted({r["source"] for r in rows} | {"products.launch0",
                                                         "listings (table, read-only)"}),
        "counts": roll["counts"], "owner_actions": roll["owner_actions"],
        "products": len(products), "sizes_counted_as_products": False,
        "preview_path": PREVIEW_PATH, "preview_viewports": sorted(VIEWPORTS),
        "live": False, "published": False,
        "note": ("Readiness of prepared drafts, measured by deterministic checks. Nothing is "
                 "entered on Etsy by this system; the live shop's state is UNKNOWN here."),
    }


# ---- the page ----------------------------------------------------------------------------

def _esc(v) -> str:
    from ..app.security import esc

    return str(esc(v))


def _paras(text: str) -> str:
    blocks = [b.strip() for b in str(text or "").split("\n\n") if b.strip()]
    out = []
    for b in blocks:
        lines = [ln.strip() for ln in b.split("\n") if ln.strip()]
        if lines and all(ln.startswith("- ") for ln in lines[1:]) and len(lines) > 1:
            items = "".join(f"<li>{_esc(ln[2:])}</li>" for ln in lines[1:])
            out.append(f"<p>{_esc(lines[0])}</p><ul>{items}</ul>")
        elif all(ln.startswith("- ") for ln in lines):
            out.append("<ul>" + "".join(f"<li>{_esc(ln[2:])}</li>" for ln in lines) + "</ul>")
        else:
            out.append("<p>" + " ".join(_esc(ln) for ln in lines) + "</p>")
    return "".join(out)


def _price(v) -> str:
    return "Price UNKNOWN" if v is None else f"CA${float(v):.2f}"


_CSS = """
:root{--pine:#244A3A;--cream:#FAF6EB;--ink:#1A2B3C;--gold:#C49545;--wine:#6E1F2A;
--line:#D6CEBC;--muted:#5C6370;--paper:#FFFFFF;--soft:#F3EEE1}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:#EAE5D8;color:var(--ink);font:15px/1.55 "Helvetica Neue",Helvetica,Arial,
sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--pine)}
.ribbon{background:var(--wine);color:var(--cream);padding:10px 16px;font-size:13px;
line-height:1.4}
.ribbon strong{letter-spacing:.04em;text-transform:uppercase;margin-right:6px}
.chrome{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:8px 16px;
font-size:12px;color:var(--muted);background:#F6F2E8;border-bottom:1px solid var(--line)}
.chrome a{padding:3px 10px;border:1px solid var(--line);border-radius:999px;
text-decoration:none;color:var(--ink);background:var(--paper)}
.chrome a.on{background:var(--pine);color:var(--cream);border-color:var(--pine)}
.frame{background:var(--paper);margin:0 auto;width:100%;overflow:hidden}
.vp-mobile .frame{max-width:390px}
.vp-desktop .frame{max-width:1280px}
.banner{background:var(--cream);aspect-ratio:2/1;overflow:hidden}
.banner img{width:100%;height:100%;object-fit:cover;object-position:center;display:block}
.head{display:flex;flex-wrap:wrap;gap:0 14px;align-items:flex-start;padding:0 16px 14px;
border-bottom:1px solid var(--line)}
.icon{width:72px;height:72px;border-radius:10px;border:3px solid var(--paper);
margin-top:-30px;background:var(--cream);box-shadow:0 1px 4px rgba(26,43,60,.18);
flex:none}
.head h1{font-size:22px;line-height:1.2;margin:12px 0 2px;color:var(--ink);
letter-spacing:.01em}
.tagline{margin:0 0 6px;font-size:14px}
.meta{margin:0;font-size:12.5px;color:var(--muted)}
.meta b{color:var(--ink);font-weight:600}
.head > div{flex:1 1 0;min-width:0}
.head .btn{flex:1 0 100%;text-align:center}
.btn{display:inline-block;margin-top:12px;padding:7px 14px;border:1.5px solid var(--ink);
border-radius:999px;font-size:13px;font-weight:600;color:var(--ink);background:var(--paper)}
.btn small{font-weight:400;color:var(--muted)}
.trust{display:flex;gap:8px;overflow-x:auto;padding:12px 16px;margin:0;list-style:none;
border-bottom:1px solid var(--line);scrollbar-width:none}
.trust li{flex:none;font-size:12.5px;padding:6px 10px 6px 26px;border-radius:8px;
background:var(--soft);position:relative;white-space:nowrap}
.trust li:before{content:"";position:absolute;left:10px;top:50%;width:6px;height:10px;
margin-top:-7px;border:solid var(--pine);border-width:0 2px 2px 0;transform:rotate(45deg)}
.announce{margin:14px 16px;padding:12px 14px;background:var(--cream);border-left:3px solid
var(--gold);border-radius:4px}
.announce h2{margin:0 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted)}
.announce p{margin:0}
.shop{padding:4px 16px 8px}
.sections{display:flex;gap:6px;overflow-x:auto;padding:8px 0 12px;margin:0;list-style:none;
scrollbar-width:none}
.sections li{flex:none;padding:6px 12px;border:1px solid var(--line);border-radius:999px;
font-size:13px;white-space:nowrap}
.sections li.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.sections .n{color:var(--muted);margin-left:4px}
.sections li.on .n{color:var(--line)}
.side-extra{display:none}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 12px}
.tile{min-width:0}
.tile .img{aspect-ratio:1/1;background:var(--soft);border-radius:8px;overflow:hidden}
.tile img{width:100%;height:100%;object-fit:cover;display:block}
.tile .withheld{display:flex;align-items:center;justify-content:center;text-align:center;
height:100%;padding:12px;font-size:12px;color:var(--wine);border:1px dashed var(--wine);
border-radius:8px}
.tile h3{font-size:13.5px;font-weight:400;line-height:1.35;margin:8px 0 2px;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tile .price{font-weight:700;font-size:15px}
.tile .tags{font-size:11.5px;color:var(--muted);margin-top:2px}
.tile .disc{font-size:11px;color:var(--muted);margin-top:3px;font-style:italic}
.about{padding:20px 16px;background:var(--cream);border-top:1px solid var(--line)}
.about h2,.policies h2,.support h2{font-size:18px;margin:0 0 10px}
.about p{margin:0 0 12px}
.glance{list-style:none;padding:12px 14px;margin:14px 0 0;align-self:start;background:var(--paper);
border:1px solid var(--line);border-radius:8px;font-size:13.5px}
.glance li{padding:4px 0;border-bottom:1px solid var(--soft)}
.glance li:last-child{border-bottom:0}
.glance b{display:inline-block;min-width:118px;color:var(--muted);font-weight:600}
.policies,.support{padding:20px 16px;border-top:1px solid var(--line)}
details{border-bottom:1px solid var(--line);padding:10px 0}
summary{cursor:pointer;font-weight:600;list-style:none}
summary::-webkit-details-marker{display:none}
summary:after{content:"+";float:right;color:var(--muted);font-weight:400}
details[open] summary:after{content:"\\2013"}
details p,details ul{margin:8px 0 0;font-size:14px}
details ul{padding-left:20px}
.foot{padding:16px;font-size:12px;color:var(--muted);text-align:center;
border-top:1px solid var(--line);background:var(--soft)}
.owner{margin:18px auto 30px;width:100%;background:#FBFAF7;border:2px dashed var(--muted);
padding:16px;font-size:13px}
.vp-mobile .owner{max-width:390px}
.vp-desktop .owner{max-width:1280px}
.owner h2{font-size:16px;margin:0 0 6px}
.owner h3{font-size:14px;margin:16px 0 6px}
.owner table{width:100%;border-collapse:collapse;font-size:12.5px}
.owner th,.owner td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line);
vertical-align:top;overflow-wrap:anywhere}
.st{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:700;
color:var(--paper);background:var(--muted);white-space:nowrap}
.st-READY{background:var(--pine)}.st-FAIL{background:var(--wine)}
.st-NEEDS_OWNER{background:#7A5A1E}.st-GATED{background:#4B5563}
.st-UNVERIFIED{background:#5C6370}
.owner ol,.owner ul{padding-left:18px;margin:4px 0}
.owner thead{display:none}
.owner tr{display:block;padding:8px 0;border-bottom:1px solid var(--line)}
.owner td{display:block;border:0;padding:2px 0}
.owner td:first-child{font-weight:700}
.owner code{font-size:11.5px;overflow-wrap:anywhere}
@media (min-width:900px){
.vp-desktop .banner{aspect-ratio:4/1}
.vp-desktop .head{padding:0 32px 18px;gap:20px}
.vp-desktop .icon{width:112px;height:112px;margin-top:-44px;border-radius:14px}
.vp-desktop .head h1{font-size:28px;margin-top:16px}
.vp-desktop .tagline{font-size:15.5px}
.vp-desktop .head .btn{margin-left:auto;margin-top:18px;flex:none}
.vp-desktop .head{flex-wrap:nowrap}
.vp-desktop .trust{padding:12px 32px;flex-wrap:wrap;overflow:visible}
.vp-desktop .announce{margin:18px 32px}
.vp-desktop .shop{display:grid;grid-template-columns:220px 1fr;gap:28px;padding:6px 32px 28px}
.vp-desktop .sections{flex-direction:column;overflow:visible;padding-top:0}
.vp-desktop .sections li{border:0;border-radius:6px;padding:7px 10px;display:flex;
justify-content:space-between}
.vp-desktop .side-extra{display:block;font-size:13px;color:var(--muted);margin-top:16px;
padding-top:14px;border-top:1px solid var(--line)}
.vp-desktop .grid{grid-template-columns:repeat(3,1fr);gap:22px 20px}
.vp-desktop .tile h3{font-size:14.5px}
.vp-desktop .about{display:grid;grid-template-columns:1.6fr 1fr;gap:36px;padding:32px}
.vp-desktop .about .glance{margin-top:34px}
.vp-desktop .policies,.vp-desktop .support{padding:28px 32px}
.vp-desktop .owner{padding:20px 28px}
.vp-desktop .owner thead{display:table-header-group}
.vp-desktop .owner tr{display:table-row;padding:0}
.vp-desktop .owner td{display:table-cell;padding:5px 6px;border-bottom:1px solid var(--line)}
.vp-desktop .owner td:first-child{width:24%}
.vp-desktop .owner td:nth-child(2){width:12%}
}
"""


def _tile(p: dict, frame: dict | None) -> str:
    if frame is None:
        img = '<div class="withheld">Image not rendered</div>'
    elif frame["status"] == "VERIFIED" and frame.get("png"):
        uri = "data:image/png;base64," + base64.b64encode(frame["png"]).decode("ascii")
        img = f'<img src="{_esc(uri)}" alt="{_esc(frame.get("alt_text", ""))}">'
    else:
        img = ('<div class="withheld">Image withheld: the render did not pass verification, '
               'and a disclosure cannot make an inaccurate image acceptable (D-FB-7).</div>')
    sizes = (f"{p['variant_count']} sizes in one pattern" if p["variant_count"] > 1
             else "One pattern")
    return (f'<article class="tile"><div class="img">{img}</div>'
            f'<h3>{_esc(p["title"])}</h3>'
            f'<div class="price">{_esc(_price(p["price_cad"]))}</div>'
            f'<div class="tags">Digital download · {_esc(sizes)}</div>'
            f'<div class="disc">Digital rendering, not a photograph</div></article>')


def _owner_panel(rows, roll, surfaces, frames, now, viewport) -> str:
    status_rows = []
    for r in rows:
        worst = [f for f in r["findings"]
                 if R._SEV_STATUS.get(f["severity"]) == r["status"]][:2]
        why = "<br>".join(_esc(f"{f['code']}: {f['detail']}") for f in worst) or "—"
        status_rows.append(f'<tr><td>{_esc(r["label"])}</td><td><span class="st '
                           f'st-{_esc(r["status"])}">{_esc(r["status"])}</span></td>'
                           f'<td>{why}</td></tr>')
    actions = "".join(f"<li><b>{_esc(a['surface'])}</b>: {_esc(a['detail'])}</li>"
                      for a in roll["owner_actions"])
    settings = "".join(f"<li>{_esc(s['what'])} — <i>{_esc(s['where'])}</i> "
                       f"(~{_esc(s['minutes_estimated'])} min, estimated; live state "
                       f"UNKNOWN)</li>" for s in surfaces["settings_checklist"].value)
    imgs = "".join(
        f"<li><code>{_esc(f['cir_slug'])}</code>: {_esc(f['status'])} (verifier "
        f"{_esc(f.get('verifier_status'))}, caption {_esc(f.get('caption_status'))}); "
        f"sha256 <code>{_esc(str(f.get('sha256', ''))[:16])}</code></li>" for f in frames)
    titles = "".join(f"<li>{_esc(p['candidate'])}: {_esc(p['title_basis'])}; price "
                     f"{_esc(p['price_basis'])}</li>"
                     for p in surfaces["opening_grid"].value)
    return (
        f'<section class="owner" aria-label="Owner readiness panel">'
        f'<h2>Owner readiness — not part of the shop page</h2>'
        f'<p>Overall: <span class="st st-{_esc(roll["status"])}">{_esc(roll["status"])}</span> '
        f'· {_esc(", ".join(f"{k} {v}" for k, v in roll["counts"].items()))}. Generated '
        f'{_esc(now.isoformat())} ({_esc(viewport)}, {VIEWPORTS[viewport]} px). Nothing on '
        f'this page has been entered on Etsy by this system.</p>'
        f'<h3>Surfaces</h3><table><thead><tr><th>Surface</th><th>Status</th><th>Why'
        f'</th></tr></thead><tbody>{"".join(status_rows)}</tbody></table>'
        f'<h3>Owner decisions and actions</h3><ol>{actions}</ol>'
        f'<h3>Settings that need the owner signed in</h3><ol>{settings}</ol>'
        f'<h3>Listing images (rendered and verified at load)</h3><ul>{imgs}</ul>'
        f'<h3>Where titles and prices come from</h3><ul>{titles}</ul>'
        f'</section>')


def render_preview(db, viewport: str = "mobile", *, now: datetime | None = None,
                   today=None) -> str:
    """The Owner Store Preview as one escaped, script-free HTML document."""
    viewport = viewport if viewport in VIEWPORTS else "mobile"
    now = _now(now)
    from . import assets

    surfaces, rows, roll = _evaluate(db, today=today)
    products = surfaces["opening_grid"].value
    frames = _image_rows(products)
    by_build = {f["build"]: f for f in frames}

    name = surfaces["shop_name"].value["display"]
    banner = assets.data_uri(surfaces["banner"].value)
    icon = assets.data_uri(surfaces["icon"].value)
    trust = "".join(f"<li>{_esc(t['text'])}</li>" for t in surfaces["trust_signals"].value)
    shown_sections = [s for s in surfaces["sections"].value if s["shown"]]
    sections = (f'<li class="on">All items<span class="n">{len(products)}</span></li>'
                + "".join(f'<li>{_esc(s["name"])}<span class="n">{_esc(s["listings"])}'
                          f'</span></li>' for s in shown_sections))
    tiles = "".join(_tile(p, by_build.get(p["representative"]["build"])) for p in products)
    pol = surfaces
    # The two answers a first-time buyer most needs are open by default: what happens if
    # something is wrong (returns), and what they may do with what they make (first FAQ).
    policy_blocks = "".join(
        f"<details{' open' if k == 'policy_returns' else ''}><summary>{_esc(pol[k].label)}"
        f"</summary>{_paras(pol[k].value)}</details>"
        for k in ("policy_delivery", "policy_returns", "policy_licence", "policy_privacy",
                  "disclosures"))
    faq = "".join(f"<details{' open' if i == 0 else ''}><summary>{_esc(f['question'])}"
                  f"</summary>{_paras(f['answer'])}</details>"
                  for i, f in enumerate(surfaces["faq"].value))
    glance = "".join(
        f"<li><b>{_esc(k)}</b>{_esc(v)}</li>" for k, v in (
            ("Based in", "Canada"), ("Sells", "Digital crochet patterns (PDF)"),
            ("Terms", "US and UK, as separate files"), ("Delivery", "Instant, through Etsy"),
            ("Support", "Etsy Messages"), ("Shop opened", "September 2026"),
            ("Reviews", "None yet — new shop")))
    body = f"""<!doctype html>
<html lang="en-CA"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{_esc(name)} — Owner Store Preview (not live)</title>
<style>{_CSS}</style></head>
<body class="vp-{_esc(viewport)}">
<div class="ribbon" role="note"><strong>{_esc(PREVIEW_LABEL)}</strong>Owner Store Preview —
a mock-up built from Brambleloop's own drafts. Nothing here is published on Etsy, and the
layout is Brambleloop's approximation of a shop page, not Etsy's.</div>
<nav class="chrome" aria-label="Preview width">Preview width:
<a href="?viewport=mobile" class="{'on' if viewport == 'mobile' else ''}">Phone 390 px</a>
<a href="?viewport=desktop" class="{'on' if viewport == 'desktop' else ''}">Desktop 1280 px</a>
</nav>
<div class="frame">
<div class="banner"><img src="{_esc(banner)}" alt="{_esc(name)} banner"></div>
<header class="head"><img class="icon" src="{_esc(icon)}" alt="{_esc(name)} shop icon">
<div><h1>{_esc(name)}</h1><p class="tagline">{_esc(surfaces['shop_title'].value)}</p>
<p class="meta">Canada · Digital crochet patterns · <b>New shop — no reviews
yet</b></p></div>
<span class="btn" aria-disabled="true">Message {_esc(name)} <small>(inactive in
preview)</small></span></header>
<ul class="trust" aria-label="How every pattern is made">{trust}</ul>
<section class="announce"><h2>Announcement</h2><p>{_esc(surfaces['announcement'].value)}</p>
</section>
<div class="shop"><aside><ul class="sections" aria-label="Shop sections">{sections}</ul>
<div class="side-extra">{_esc(C.SUPPORT_CONTACT.split(':')[0])}.</div></aside>
<main class="grid" aria-label="Items">{tiles}</main></div>
<section class="about"><div><h2>About {_esc(name)}</h2>{_paras(surfaces['about'].value)}
</div><ul class="glance" aria-label="Shop at a glance">{glance}</ul></section>
<section class="policies"><h2>Shop policies</h2>{policy_blocks}</section>
<section class="policies"><h2>Frequently asked questions</h2>{faq}</section>
<section class="support"><h2>Questions and support</h2>{_paras(C.SUPPORT_CONTACT)}</section>
<div class="foot">{_esc(PREVIEW_LABEL)} · {_esc(name)} · prices in CAD ·
taxes are handled by Etsy at checkout</div>
</div>
{_owner_panel(rows, roll, surfaces, frames, now, viewport)}
</body></html>"""
    return body
