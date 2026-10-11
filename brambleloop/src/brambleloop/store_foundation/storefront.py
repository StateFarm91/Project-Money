"""Customer storefront preview (W4-STOREFRONT): what a buyer would meet, and nothing else.

The earlier previews (`preview.render_preview` variants standard / brand_face / v2 / compare)
are kept unchanged as the record of how the shop evolved. This module draws the owner's
2026-10-11 brief:

* a premium, mobile-first shop page for a crochet-pattern brand: readable product cards with
  clear titles and prices, an obvious "Digital download (PDF pattern)" label, only populated
  categories (D-FB-18 item 3, `navigation.public_nav`), concise descriptions, product sheets,
  About, policies, FAQ and support;
* imagery is the verified disclosed rendering only (`preview.hero_frame`, verified on its exact
  bytes at load). A withheld frame becomes a neutral placeholder that says a picture is coming;
  the unverified asset is never embedded (D-FB-7);
* material customer disclosures stay customer-facing and where Etsy expects them: the digital
  item, AI-assisted design and "rendering, not a photograph" lines on each product sheet, and
  the full disclosure text in "About these patterns" (Etsy: seller-prompted AI creations must
  disclose AI -- `integrations.etsy_constraints` key `ai_disclosure`);
* every internal item -- readiness checks, hashes, gate explanations, quality mechanics, where
  titles and prices come from, settings, Etsy field limits -- moves to one owner evidence
  panel at the foot of the page, folded, labelled as not part of the shop. Nothing is deleted;
* the page is clearly a preview (ribbon, title, footer) and never claims to be Etsy's page.
  `etsy_controls()` lists what Etsy actually lets a shop control, from the quoted constraints
  in `integrations.etsy_constraints`, and what this layout only approximates.

Customer words come from the COPY lane. Every customer string is looked up by key through
`copy_text(key)`: a COPY-lane module (`store_foundation.copy_w4`, dict `CUSTOMER_COPY`) wins when
it exists; otherwise lane C's `copy_v2.customer_copy()` supplies the same key; a key neither
has renders as a visible `[copy: key]` placeholder rather than invented text. Each element
carries `data-copy="<key>"` so the copy pass can be audited on the page.

Script-free, no external URL, every value escaped (`app.security.esc`), images as data: URIs.
Nothing here publishes, writes to Etsy, or contacts a network.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone

VARIANT = "storefront"
PREVIEW_LABEL = "Preview — not live"
NOT_ETSY = ("A preview of the Brambleloop Studio shop built from its own drafts. This is not "
            "the real Etsy storefront: nothing here is published, and Etsy draws the real page "
            "in its own layout.")
DIGITAL_LABEL = "Digital download (PDF pattern)"
COPY_LANE_MODULE = "copy_w4"

# Product words keyed for the COPY lane. Until it supplies them, the product's own plan title
# and the first sentence of its plan description are used (both customer-facing already).
PRODUCT_KEYS = ("product_name:{slug}", "product_summary:{slug}")


def _esc(v) -> str:
    from ..app.security import esc

    return str(esc(v))


# ---- copy -----------------------------------------------------------------------------------

_COPY_CACHE: dict | None = None


def _copy_sources() -> tuple[dict, str]:
    global _COPY_CACHE
    if _COPY_CACHE is None:
        lane, src = {}, "store_foundation.copy_v2.customer_copy (COPY lane not present)"
        try:
            import importlib

            mod = importlib.import_module(f"{__package__}.{COPY_LANE_MODULE}")
            lane = dict(getattr(mod, "CUSTOMER_COPY", {}) or {})
            if lane:
                src = f"store_foundation.{COPY_LANE_MODULE}.CUSTOMER_COPY"
        except ImportError:
            pass
        from . import copy_v2

        _COPY_CACHE = {"lane": lane, "v2": copy_v2.customer_copy(), "source": src}
    return _COPY_CACHE, _COPY_CACHE["source"]


def copy_text(key: str, fallback: str | None = None) -> tuple[str, str]:
    """(text, origin) for a customer copy key: COPY lane, then copy_v2, then fallback/placeholder."""
    c, _ = _copy_sources()
    if c["lane"].get(key):
        return str(c["lane"][key]), "copy_lane"
    if c["v2"].get(key):
        return str(c["v2"][key]), "copy_v2"
    if fallback:
        return str(fallback), "fallback"
    return f"[copy: {key}]", "placeholder"


def _c(key: str, tag: str = "span", cls: str = "", fallback: str | None = None) -> str:
    text, origin = copy_text(key, fallback)
    klass = f' class="{cls}"' if cls else ""
    return f'<{tag}{klass} data-copy="{_esc(key)}" data-copy-origin="{origin}">{_esc(text)}</{tag}>'


def _first_sentence(text: str, limit: int = 150) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    s = m.group(1) if m else t
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


# ---- the collection -------------------------------------------------------------------------

def collection(db=None, *, verify_images: bool = False) -> list[dict]:
    """The 8-product launch collection: the Launch-0 products plus the catalogue-floor proposal.

    The proposal (`launch0.PROPOSED_CANDIDATES`) is the owner's open decision D-FB-9
    (`CATALOGUE_FLOOR_APPROVED`); its products are listed with status PROPOSED and are never
    shown on the customer page until that decision is made.
    """
    from ..brand import storefront as bsf
    from ..commerce import seo
    from ..products import launch0 as l0
    from . import content as C

    rows = []
    for p in C.launch0_products(db):
        rows.append({**p, "launch_status": "LAUNCH_0",
                     "launch_status_note": "in the Launch-0 opening catalogue"})
    approved = bool(getattr(l0, "CATALOGUE_FLOOR_APPROVED", False))
    if not approved:
        for cand in getattr(l0, "PROPOSED_CANDIDATES", ()):
            variants = list(cand.variants)
            rep = variants[len(variants) // 2]
            cirs = [l0.cir_for(v.build) for v in variants]
            rep_cir = l0.cir_for(rep.build)
            ident = cand.listing
            try:
                plan = l0.price_plan(cand)
                price, pbasis = plan.get("price_cad"), (
                    f"products.launch0.price_plan({cand.slug}) (proposal, not in launch scope)")
            except Exception as exc:  # noqa: BLE001 - unknown is said, never invented
                price, pbasis = None, f"UNKNOWN: {type(exc).__name__}"
            rows.append({
                "candidate": cand.slug, "plan_title": cand.title,
                "title": seo.build_title(rep_cir.title, ident.etsy_category,
                                         list(ident.qualifiers), None, sizes=len(variants)),
                "title_basis": "derived: commerce.seo.build_title (proposal; no listing drafted)",
                "description": cand.what_it_is, "price_cad": price, "price_basis": pbasis,
                "sizes": [{"key": v.key, "label": v.label, "cir_slug": c.slug}
                          for v, c in zip(variants, cirs)],
                "variant_count": len(variants),
                "representative": {"build": rep.build, "cir_slug": rep_cir.slug,
                                   "cir_fingerprint": rep_cir.fingerprint},
                "kind": ident.kind, "qualifiers": list(ident.qualifiers),
                "etsy_category": ident.etsy_category,
                "section": bsf.section_for(ident.etsy_category), "audience": cand.audience,
                "launch_status": "PROPOSED",
                "launch_status_note": ("catalogue-floor proposal: owner decision D-FB-9 "
                                       "(launch0.CATALOGUE_FLOOR_APPROVED is False)")})
    for r in rows:
        r["slug"] = r["candidate"]
        r["name"] = copy_text(PRODUCT_KEYS[0].format(slug=r["slug"]), r["plan_title"])[0]
        r["summary"] = copy_text(PRODUCT_KEYS[1].format(slug=r["slug"]),
                                 _first_sentence(r["description"]))[0]
        r["digital_label"] = DIGITAL_LABEL
        r["image"] = {"status": "NOT_CHECKED", "build": r["representative"]["build"]}
    if verify_images:
        from .preview import hero_frame

        for r in rows:
            f = hero_frame(r["representative"]["build"])
            r["image"] = {k: v for k, v in f.items() if k != "png"}
    return rows


# ---- what Etsy lets a shop control ------------------------------------------------------------

#: Parts of this page that are an approximation only: Etsy draws them, the shop cannot style them.
LAYOUT_NOT_CONTROLLED = (
    ("Page layout, colours, fonts and card design",
     "Etsy draws the shop page in its own design; no Etsy source on file offers a shop custom "
     "colours, fonts, CSS or HTML. This preview's look is Brambleloop's own and only "
     "approximates where Etsy places each element."),
    ("Navigation and filters",
     "Etsy supplies the search box, filters and menus. A shop arranges listings only through "
     "its sections and featured listings."),
    ("Product-card text",
     "Etsy cards show the listing photo, the listing title (shortened) and price. The short "
     "product names on this preview are for reading on a phone; on Etsy the card shows the "
     "listing title."),
    ("Product sheets",
     "On Etsy a listing opens on its own page drawn by Etsy (photos, title, price, "
     "description, digital-file note). The sheets on this preview gather the same facts."),
)


def etsy_controls() -> dict:
    """What a shop actually controls on Etsy, from quoted constraints, grouped by surface."""
    from ..integrations import etsy_constraints as E

    groups: dict[str, list[dict]] = {}
    allc = E.CONSTRAINTS.values() if isinstance(getattr(E, "CONSTRAINTS", None), dict) else E._C
    for c in allc:
        groups.setdefault(c.surface, []).append(
            {"key": c.key, "what": c.what,
             "value": list(c.value) if isinstance(c.value, tuple) else c.value,
             "basis": c.basis, "source": c.source})
    return {"retrieved_on": E.RETRIEVED_ON, "surfaces": groups,
            "not_controlled": [{"element": a, "why": b} for a, b in LAYOUT_NOT_CONTROLLED],
            "note": ("VERIFIED rows quote an Etsy help-centre or Open API sentence on file; "
                     "UNKNOWN rows carry no number. The layout items are UNVERIFIED: no Etsy "
                     "source on file grants that control.")}


# ---- the page -------------------------------------------------------------------------------

_PLACEHOLDER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">'
    '<rect width="400" height="400" fill="#F3EEE7"/>'
    '<g fill="none" stroke="#C9B9A2" stroke-width="3">'
    '<circle cx="200" cy="178" r="64"/><path d="M146 150c30 10 78 10 108 0M140 182c34 12 86 12 '
    '120 0M150 214c28 9 72 9 100 0M176 118c-14 30-14 90 0 120M224 118c14 30 14 90 0 120"/>'
    '<path d="M258 214c28 18 40 40 44 70" stroke-linecap="round"/></g></svg>')


def _placeholder_uri() -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(_PLACEHOLDER.encode()).decode()


_CSS = """
:root{--paper:#FBF8F3;--cream:#F3EEE7;--linen:#E9E0D0;--line:#D9CDBA;--ink:#2F3E33;
--muted:#5B5A4E;--rose:#A67372;--berry:#86413D;--sage:#4B503F;
--display:'Cormorant Garamond','Libre Baskerville',Georgia,serif;
--body:'Work Sans',system-ui,-apple-system,'Segoe UI',sans-serif}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 var(--body)}
a{color:var(--berry)}img{max-width:100%;display:block}
.ribbon{background:var(--ink);color:#FBF8F3;padding:8px 16px;font-size:13px;line-height:1.4}
.ribbon strong{display:inline-block;background:#FBF8F3;color:var(--ink);border-radius:999px;
padding:1px 10px;margin-right:8px;font-size:13px;letter-spacing:.02em}
.chrome{display:flex;gap:6px;overflow-x:auto;padding:8px 16px;background:var(--cream);
font-size:13px;border-bottom:1px solid var(--line);scrollbar-width:none;white-space:nowrap}
.chrome a{padding:6px 10px;border-radius:999px;text-decoration:none;color:var(--muted);
border:1px solid var(--line);min-height:32px;display:inline-flex;align-items:center}
.chrome a.on{background:var(--ink);color:#FBF8F3;border-color:var(--ink)}
.shopwrap{max-width:1120px;margin:0 auto}
.banner{aspect-ratio:4/1;overflow:hidden;background:var(--cream)}
.banner img{width:100%;height:100%;object-fit:cover}
.head{display:grid;grid-template-columns:72px 1fr;gap:14px;align-items:center;padding:16px}
.head .icon{width:72px;height:72px;border-radius:12px;border:1px solid var(--line);background:#fff}
.head h1{font:600 30px/1.1 var(--display);margin:0}
.tagline{margin:4px 0 0;color:var(--muted);font-size:15px}
.meta{margin:6px 0 0;font-size:13px;color:var(--muted)}
.announce{margin:0 16px 8px;padding:12px 14px;background:var(--cream);border-radius:12px;font-size:15px}
.announce h2{margin:0 0 4px;font:600 13px/1.2 var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.announce p{margin:0}
.cats{display:flex;gap:8px;overflow-x:auto;padding:12px 16px;margin:0;list-style:none;scrollbar-width:none}
.cats a{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 16px;border-radius:999px;
border:1px solid var(--line);background:#fff;color:var(--ink);text-decoration:none;font-weight:600;font-size:15px;white-space:nowrap}
.cats a.on{background:var(--ink);color:#FBF8F3;border-color:var(--ink)}
.cats .n{font-weight:400;opacity:.75}
.sec{padding:8px 16px 4px}
.sec h2{font:600 26px/1.15 var(--display);margin:12px 0 4px}
.sec .blurb{margin:0 0 10px;color:var(--muted);font-size:15px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 12px;padding:0 16px 8px}
.card{display:flex;flex-direction:column;text-decoration:none;color:inherit;min-width:0;scroll-margin-top:12px}
.card .img{position:relative;aspect-ratio:1/1;border-radius:12px;overflow:hidden;background:var(--cream)}
.im{width:100%;height:100%;background:var(--cream) center/cover no-repeat}
.card .soon{position:absolute;left:8px;bottom:8px;right:8px;background:rgba(251,248,243,.92);
border-radius:8px;padding:4px 8px;font-size:12px;color:var(--muted);text-align:center}
.card .eyebrow{margin-top:8px;font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.card .eyebrow + h3{margin-top:2px}
.card h3{font:600 16px/1.3 var(--body);margin:8px 0 2px;overflow-wrap:anywhere}
.card .price{font-weight:700;font-size:17px}
.card .dl{display:inline-block;margin-top:4px;font-size:12px;font-weight:600;color:var(--sage);
background:#EEF0E8;border-radius:6px;padding:2px 6px;align-self:flex-start}
.card .sum{margin:6px 0 0;font-size:13.5px;color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;
-webkit-box-orient:vertical;overflow:hidden}
.promise{margin:16px;padding:16px;border-radius:14px;background:var(--cream)}
.promise h2{font:600 22px/1.2 var(--display);margin:0 0 8px}
.promise ul{margin:0;padding-left:18px}.promise li{margin:4px 0}
.sheet{margin:16px;padding:16px;border:1px solid var(--line);border-radius:14px;background:#fff;scroll-margin-top:12px}
.sheet .simg{border-radius:10px;overflow:hidden;background:var(--cream);aspect-ratio:1/1;max-width:420px}
.sheet h3{font:600 24px/1.2 var(--display);margin:12px 0 4px}
.sheet .price{font-weight:700;font-size:20px;margin:0}
.sheet .dl{font-weight:600;color:var(--sage);margin:6px 0}
.sheet dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:14.5px;margin:10px 0}
.sheet dt{color:var(--muted)}.sheet dd{margin:0;overflow-wrap:anywhere}.sheet dd ul{padding-left:18px;margin:4px 0}
.disc{font-size:13px;color:var(--muted);border-top:1px solid var(--line);margin-top:10px;padding-top:8px}
.disc p{margin:4px 0}
.btn{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:999px;
background:var(--ink);color:#FBF8F3;font-weight:600;text-decoration:none}
.btn[aria-disabled=true]{opacity:.75}
.block{margin:16px;padding:4px 0}
.block h2{font:600 26px/1.15 var(--display);margin:16px 0 8px}
.block p{margin:0 0 10px}
details.q{border-top:1px solid var(--line)}details.q:last-of-type{border-bottom:1px solid var(--line)}
details.q summary{min-height:48px;display:flex;align-items:center;cursor:pointer;font-weight:600;padding:6px 0}
details.q > div{padding:0 0 12px;font-size:15px}
.foot{padding:20px 16px 28px;text-align:center;font-size:13px;color:var(--muted)}
.owner{margin:24px 16px;border:2px dashed var(--muted);border-radius:12px;background:#fff;font-size:14px}
.owner > summary{padding:14px;min-height:48px;cursor:pointer;font-weight:700}
.owner .inner{padding:0 14px 14px;overflow-x:auto}
.owner table{border-collapse:collapse;width:100%;font-size:13px}
.owner th,.owner td{border-top:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
.owner code{font-size:12px;overflow-wrap:anywhere}
.owner .section-label{font-weight:700;margin:14px 0 4px}
.st{font-weight:700}
@media (min-width:720px){
.grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:22px 18px}
.head{grid-template-columns:96px 1fr;padding:20px 16px}.head .icon{width:96px;height:96px}
.head h1{font-size:38px}
.sheets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
}
"""


def _img(frame: dict | None, alt_fallback: str) -> tuple[str, bool]:
    """An image element. Verified frames are drawn from one stylesheet rule per frame (so a
    picture used on its card and its sheet is embedded once); anything else is the neutral
    placeholder, never the unverified asset."""
    if frame and frame.get("status") == "VERIFIED" and frame.get("png"):
        return (f'<div class="im im-{_esc(frame["build"])}" role="img" '
                f'aria-label="{_esc(frame.get("alt_text") or alt_fallback)}" '
                f'data-image="verified"></div>'), True
    return (f'<div class="im im-placeholder" role="img" aria-label="Picture coming soon: '
            f'{_esc(alt_fallback)}" data-image="placeholder"></div>'), False


def _image_css(frames: list[dict]) -> str:
    out = [f'.im-placeholder{{background-image:url("{_placeholder_uri()}")}}']
    for f in frames:
        if f.get("status") == "VERIFIED" and f.get("png") and re.fullmatch(r"[a-z0-9_]+", f["build"]):
            uri = "data:image/png;base64," + base64.b64encode(f["png"]).decode("ascii")
            out.append(f'.im-{f["build"]}{{background-image:url("{uri}")}}')
    return "".join(out)


def _sizes_line(p: dict) -> str:
    n = p["variant_count"]
    return f"{n} sizes in one pattern" if n > 1 else "One size"


def _card(p: dict, frame: dict | None, *, section: str | None = None,
          anchor: str | None = None) -> str:
    from .preview import _price

    img, real = _img(frame, p["name"])
    soon = "" if real else '<span class="soon">Picture coming soon</span>'
    idattr = f' id="{_esc(anchor)}"' if anchor else ""
    eyebrow = f'<span class="eyebrow">{_esc(section)}</span>' if section else ""
    return (f'<a class="card"{idattr} href="#p-{_esc(p["slug"])}" data-product="{_esc(p["slug"])}">'
            f'<div class="img">{img}{soon}</div>{eyebrow}'
            f'<h3 data-copy="{_esc(PRODUCT_KEYS[0].format(slug=p["slug"]))}">{_esc(p["name"])}</h3>'
            f'<div class="price">{_esc(_price(p["price_cad"]))}</div>'
            f'<span class="dl">{_esc(DIGITAL_LABEL)}</span>'
            f'<p class="sum" data-copy="{_esc(PRODUCT_KEYS[1].format(slug=p["slug"]))}">'
            f'{_esc(p["summary"])}</p></a>')


def _sheet(p: dict, frame: dict | None, disclosure_lines: list[str]) -> str:
    from .preview import _price

    img, real = _img(frame, p["name"])
    sizes = "".join(f"<li>{_esc(s['label'])}</li>" for s in p["sizes"])
    image_note = ("<p>The picture is a digital rendering of the finished design, not a "
                  "photograph.</p>" if real else
                  "<p>A picture of this design is not ready yet.</p>")
    disc = "".join(f"<p>{_esc(x)}</p>" for x in disclosure_lines)
    return (f'<article class="sheet" id="p-{_esc(p["slug"])}" data-sheet="{_esc(p["slug"])}">'
            f'<div class="simg">{img}</div>'
            f'<h3>{_esc(p["name"])}</h3><p class="price">{_esc(_price(p["price_cad"]))}</p>'
            f'<p class="dl">{_esc(DIGITAL_LABEL)} · US and UK terms, each a complete PDF</p>'
            f'<p>{_esc(p["description"])}</p>'
            f'<dl><dt>Format</dt><dd>Instant PDF download through Etsy; nothing is posted</dd>'
            f'<dt>Sizes</dt><dd>{_esc(_sizes_line(p))}<ul>{sizes}</ul></dd></dl>'
            f'<span class="btn" aria-disabled="true">Add to basket <small>&nbsp;(inactive in '
            f'preview)</small></span>'
            f'<div class="disc" data-disclosure="listing">{image_note}{disc}</div></article>')


def _disclosure_lines(text: str) -> list[str]:
    """The listing-level lines of the store disclosure (digital item, AI-assisted design)."""
    lines = [ln.strip() for ln in str(text or "").split("\n") if ln.strip()]
    keep = [ln for ln in lines if re.search(r"digital pattern|AI", ln)]
    return keep[:2]


def _owner_evidence(ctx: dict, now: datetime, viewport: str) -> str:
    from . import preview as V1

    panel = V1._owner_panel(ctx["rows"], ctx["roll"], ctx["surfaces"], ctx["frames"], now,
                            viewport)
    trust = "".join(
        f"<li>{_esc(t['text'])} — <i>{_esc(t.get('kind', ''))}</i>; evidence: "
        f"{_esc(', '.join(t.get('evidence') or []) or 'none recorded')}</li>"
        for t in ctx["surfaces"]["trust_signals"].value)
    ctl = etsy_controls()
    rows = []
    for surface, items in ctl["surfaces"].items():
        for it in items:
            val = it["value"] if it["value"] is not None else "UNKNOWN"
            rows.append(f"<tr><td>{_esc(surface)}</td><td>{_esc(it['what'])}</td>"
                        f"<td>{_esc(val)}</td><td>{_esc(it['basis'])}</td></tr>")
    nc = "".join(f"<li><b>{_esc(x['element'])}</b>: {_esc(x['why'])}</li>"
                 for x in ctl["not_controlled"])
    _, copy_src = _copy_sources()
    hidden = "".join(f"<li>{_esc(h['name'])}: {_esc(h['hidden_because'])}</li>"
                     for h in ctx["hidden_nav"])
    return (
        '<details class="owner" data-owner-evidence="1"><summary>Owner evidence — not part of '
        'the shop page (readiness, checks, sources, Etsy limits)</summary><div class="inner">'
        f'{panel}'
        f'<p class="section-label">How the trust lines are backed (quality mechanics)</p><ul>{trust}</ul>'
        f'<p class="section-label">Categories hidden until populated</p><ul>{hidden or "<li>None</li>"}</ul>'
        f'<p class="section-label">Customer copy source</p><p>{_esc(copy_src)}. Elements carry '
        f'data-copy keys; a key with no copy shows as a [copy: key] placeholder.</p>'
        f'<p class="section-label">What Etsy lets the shop control (retrieved '
        f'{_esc(ctl["retrieved_on"])})</p><p>{_esc(ctl["note"])}</p>'
        f'<table><thead><tr><th>Surface</th><th>Control</th><th>Value</th><th>Basis</th></tr>'
        f'</thead><tbody>{"".join(rows)}</tbody></table>'
        f'<p class="section-label">Approximated here, drawn by Etsy</p><ul>{nc}</ul>'
        '</div></details>')


def render(db, viewport: str = "mobile", *, now: datetime | None = None, today=None,
           variants: dict | None = None) -> str:
    from . import assets
    from . import navigation
    from . import preview as V1

    viewport = viewport if viewport in V1.VIEWPORTS else "mobile"
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    surfaces, rows, roll = V1._evaluate(db, today=today)
    products = [p for p in collection(db) if p["launch_status"] == "LAUNCH_0"]
    frames = [V1.hero_frame(p["representative"]["build"]) for p in products]
    by_build = {f["build"]: f for f in frames}
    nav = navigation.public_nav(db)
    ctx = {"surfaces": surfaces, "rows": rows, "roll": roll, "frames": frames,
           "hidden_nav": navigation.hidden(db)}

    name = surfaces["shop_name"].value["display"]
    banner = assets.data_uri(surfaces["banner"].value)
    icon = assets.data_uri(surfaces["icon"].value)
    variants = variants or V1.VARIANTS
    chrome = "".join(
        f'<a href="?viewport={_esc(viewport)}&amp;variant={_esc(k)}" '
        f'class="{"on" if k == VARIANT else ""}">{_esc(v)}</a>' for k, v in variants.items())
    widths = "".join(
        f'<a href="?viewport={k}&amp;variant={VARIANT}" class="{"on" if k == viewport else ""}">'
        f'{"Phone 390 px" if k == "mobile" else "Desktop 1280 px"}</a>' for k in ("mobile", "desktop"))

    cats = (f'<li><a class="on" href="#all">All items <span class="n">{len(products)}</span></a></li>'
            + "".join(f'<li><a href="#c-{_esc(s["slug"])}" data-copy="section:{_esc(s["slug"])}">'
                      f'{_esc(copy_text("section:" + s["slug"], s["name"])[0])} '
                      f'<span class="n">{_esc(s["listings"])}</span></a></li>' for s in nav))
    # One "All items" grid, ordered by the public sections (like a shop home page). Each
    # section chip jumps to that section's first card; each card names its section.
    sec_name = {x["slug"]: copy_text("section:" + x["slug"], x["name"])[0] for x in nav}
    order = {x["slug"]: i for i, x in enumerate(nav)}
    ordered = sorted(products, key=lambda p: (order.get(p["section"], 99), p["name"]))
    seen: set[str] = set()
    cards = []
    for p in ordered:
        anchor = None
        if p["section"] in order and p["section"] not in seen:
            seen.add(p["section"])
            anchor = f"c-{p['section']}"
        cards.append(_card(p, by_build.get(p["representative"]["build"]),
                           section=sec_name.get(p["section"]), anchor=anchor))
    groups = [f'<section class="sec" aria-labelledby="h-all"><h2 id="h-all">All patterns</h2>'
              f'<p class="blurb">{len(products)} patterns · instant PDF download</p></section>'
              f'<div class="grid">{"".join(cards)}</div>']
    disc_lines = _disclosure_lines(surfaces["disclosures"].value)
    sheets = "".join(_sheet(p, by_build.get(p["representative"]["build"]), disc_lines)
                     for p in products)
    trust = "".join(f'<li data-copy="trust:{_esc(t["key"])}">'
                    f'{_esc(copy_text("trust:" + t["key"], t["text"])[0])}</li>'
                    for t in surfaces["trust_signals"].value)
    policies = "".join(
        f'<details class="q"{" open" if k == "returns" else ""}><summary>{_esc(label)}</summary>'
        f'<div data-copy="{_esc(k)}">{V1._paras(copy_text(k, surfaces[sk].value)[0])}</div></details>'
        for k, sk, label in (("delivery", "policy_delivery", "Delivery"),
                             ("returns", "policy_returns", "Returns and corrections"),
                             ("privacy", "policy_privacy", "Privacy")))
    licence = (f'<details class="q"><summary>{_esc(surfaces["policy_licence"].label)}</summary>'
               f'<div>{V1._paras(surfaces["policy_licence"].value)}</div></details>')
    disclosures = (f'<details class="q" data-disclosure="shop"><summary>About these patterns: '
                   f'digital items, AI use and pictures</summary><div data-copy="store_disclosure">'
                   f'{V1._paras(copy_text("store_disclosure", surfaces["disclosures"].value)[0])}'
                   f'</div></details>')
    faq = "".join(f'<details class="q"><summary data-copy="faq_q:{_esc(f.get("key", ""))}">'
                  f'{_esc(f["question"])}</summary><div data-copy="faq_a:{_esc(f.get("key", ""))}">'
                  f'{V1._paras(f["answer"])}</div></details>' for f in surfaces["faq"].value)

    return f"""<!doctype html>
<html lang="en-CA"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{_esc(name)} — Storefront preview (not live)</title>
<style>{_CSS}{_image_css(frames)}</style></head>
<body class="vp-{_esc(viewport)}" data-variant="{VARIANT}">
<div class="ribbon" role="note"><strong>{_esc(PREVIEW_LABEL)}</strong>{_esc(NOT_ETSY)}</div>
<nav class="chrome" aria-label="Preview options">{widths}{chrome}</nav>
<div class="shopwrap" data-customer-view="1">
<div class="banner"><img src="{_esc(banner)}" alt="{_esc(name)} banner"></div>
<header class="head"><img class="icon" src="{_esc(icon)}" alt="{_esc(name)} shop icon">
<div><h1>{_esc(name)}</h1>{_c("tagline", "p", "tagline")}
<p class="meta">Canada · Digital crochet patterns · New shop, no reviews yet</p></div></header>
<section class="announce" aria-label="Announcement"><h2>Announcement</h2>{_c("announcement", "p")}</section>
<nav aria-label="Shop sections"><ul class="cats" id="all">{cats}</ul></nav>
<main aria-label="Patterns">{"".join(groups)}
<section class="promise" aria-labelledby="h-promise"><h2 id="h-promise" data-copy="trust_headline">{_esc(copy_text("trust_headline")[0])}</h2>
<ul>{trust}</ul></section>
<div class="sheets" aria-label="Pattern details">{sheets}</div></main>
<section class="block" aria-labelledby="h-about"><h2 id="h-about">About {_esc(name)}</h2>
<div data-copy="about">{V1._paras(copy_text("about", surfaces["about"].value)[0])}</div></section>
<section class="block" aria-labelledby="h-pol"><h2 id="h-pol">Shop policies</h2>{policies}{licence}{disclosures}</section>
<section class="block" aria-labelledby="h-faq"><h2 id="h-faq">Questions</h2>{faq}</section>
<section class="block" aria-labelledby="h-sup"><h2 id="h-sup">Support</h2>
<div data-copy="support_contact">{V1._paras(copy_text("support_contact", surfaces["support_contact"].value)[0])}</div>
<span class="btn" aria-disabled="true">Message {_esc(name)} <small>&nbsp;(inactive in preview)</small></span></section>
<div class="foot">{_esc(PREVIEW_LABEL)} · {_esc(name)} · prices in CAD · taxes are handled by
Etsy at checkout · not the Etsy storefront</div>
</div>
{_owner_evidence(ctx, now, viewport)}
</body></html>"""


def customer_html(html: str) -> str:
    """The customer part of a rendered page (everything before the owner evidence panel)."""
    start = html.find('data-customer-view="1"')
    end = html.find('<details class="owner"')
    return html[start:end] if start >= 0 and end > start else ""
