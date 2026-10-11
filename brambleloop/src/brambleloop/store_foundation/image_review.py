"""Owner-only internal image review (W4-IMAGES): every candidate listing image, shown with
its status and limitations, whether or not it may be published.

The customer storefront preview (`preview.py`) shows a product image only when it verifies, and
otherwise withholds it. This page answers a different question for the owner: *what image
exists for each product, what is it, and why is it (not) usable?* It shows the actual pixels,
including frames that failed verification, and labels each one prominently. It is never a
customer surface:
* it is served only at `REVIEW_PATH`, an owner-session page (`app.security.OWNER_SESSION_PAGES`),
  with no-store and noindex headers;
* nothing here grants publication. `customer_approved` is computed, and it is False unless a
  valid listing-set certificate exists for the exact release *and* parity has no unjudged
  dimension *and* an owner publication grant resolves (D-FB-10). None of those is assumed;
* the customer preview's rule is not changed: a withheld frame stays withheld there.

Every image is a deterministic disclosed render produced here, now, from the product's current
CIR (`visual.disclosed_render`). It is verified on its exact bytes (`visual.render_verification`)
and checked for its disclosure caption in the pixels. No generated or photographed image of a
physical object exists for any of these products, so none is shown, and none is fabricated as
a stand-in. Local and deterministic: no model, provider or network call. Spend is CA$0.
"""
from __future__ import annotations

import base64
import hashlib
import io
from datetime import datetime, timezone

REVIEW_PATH = "/cc/image-review"
PAGE_TITLE = "Image review: owner only, internal"
THUMB_PX = 640

# Review statuses. Each is a reading, not a decision.
VERIFIED_NOT_APPROVED = "VERIFIED, NOT APPROVED FOR CUSTOMERS"
FAILED_VERIFICATION = "FAILED VERIFICATION: INACCURATE, DO NOT USE"
UNVERIFIED = "NOT VERIFIED: UNKNOWN, DO NOT USE"
NOT_RENDERED = "NO IMAGE: THE RENDERER REFUSED"
INCOMPLETE = "SHOWS FEWER PIECES THAN THE PATTERN MAKES: MISLEADING HERO, DO NOT USE"
APPROVED = "APPROVED FOR CUSTOMER USE"

PROVENANCE = ("deterministic disclosed render, drawn from the certified CIR by "
              "visual.disclosed_render. Not a photograph and not AI-generated")

# Image material in the repository that is NOT a candidate for any listing, and why. Listed
# so that nobody mistakes it for an alternative. Never shown as a product image.
NOT_CANDIDATES = (
    {"where": "research/e1, e3, e4, e5, bench1, bench2, v1grad (out/gen*)",
     "what": "AI-generated images (flux-2-pro, gpt-image, Gemini, BFL) from visual R&D",
     "why": ("generated pictures of objects that were never made. They fail Product Truth "
             "by construction (F-852: the generative product redraw is refused), so they are "
             "evidence of model behaviour only and are forbidden as listing images")},
    {"where": "visual/assets/canonical/laura-*",
     "what": "Laura canonical reference pack (D-FB-11..14)",
     "why": ("brand-face references. None is publication_approved, and photorealism "
             "failures (B-657) stand. They are not product images")},
    {"where": "research/final_build/waves/h2_samples/*_hero_640_downscaled.png",
     "what": "H2 downscaled hero samples (baskets M, blanket, coasters)",
     "why": ("historical evidence copies of earlier renderer output. The live candidate is the "
             "frame re-rendered and re-verified from the current CIR (below), never a stored "
             "copy")},
)


def _now(now=None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


# ---- what is reviewed ---------------------------------------------------------------------

def candidates() -> list[dict]:
    """Every Launch-0 variant build plus every proposed catalogue-floor build.

    Includes the 5 products the customer preview shows (their representative build is marked
    `in_customer_preview`), and the sibling sizes and proposed products the CATALOG lane may
    add."""
    from ..products import launch0 as L

    from . import content as C

    try:
        shown = {p["representative"]["build"]
                 for p in (C.build(None)["opening_grid"].value or [])}
    except Exception:  # noqa: BLE001 - an unreadable grid marks nothing as shown
        shown = set()
    out, seen = [], set()
    groups = [("launch0", c) for c in L._BASE_CANDIDATES if c.slug in L.LAUNCH0_SLUGS]
    groups += [("proposed", c) for c in L.PROPOSED_CANDIDATES]
    for group, cand in groups:
        for v in cand.variants:
            if v.build in seen:
                continue
            seen.add(v.build)
            out.append({"slug": cand.slug, "title": cand.title, "build": v.build,
                        "variant": v.key if hasattr(v, "key") else getattr(v, "name", ""),
                        "group": group, "in_customer_preview": v.build in shown})
    return out


def _cir(build_key: str):
    from ..products import launch0 as L

    builder = L.BUILDERS.get(build_key) or getattr(L, "PROPOSED_BUILDERS", {}).get(build_key)
    if builder is None:
        raise KeyError(f"no builder for {build_key!r}")
    return builder()


_TRUTH: dict[str, dict] = {}
# Render + verification per (build, CIR fingerprint): a pure function of the CIR, so computed
# once per design change rather than once per page view (as `preview.hero_frame`).
_RENDERS: dict[tuple[str, str], dict] = {}


def _product_truth(slug: str) -> dict:
    from ..products import launch0 as L

    if slug not in _TRUTH:
        try:
            cand = next((c for c in tuple(L._BASE_CANDIDATES) + tuple(L.PROPOSED_CANDIDATES)
                         if c.slug == slug))
            pt = L.product_truth(cand)
            gates = pt.get("gates") or {}
            _TRUTH[slug] = {"passes": bool(pt.get("passes_gates")),
                            "failed": sorted(k for k, v in gates.items() if v is not True),
                            "calibrated": False}
        except Exception as exc:  # noqa: BLE001 - unknown, never passed
            _TRUTH[slug] = {"passes": None, "failed": [f"{type(exc).__name__}: {exc}"[:200]],
                            "calibrated": False}
    return dict(_TRUTH[slug])


def environment() -> dict:
    """The rendering environment, so a WITHHELD frame in production names its cause.

    Disclosed renders are byte-exact drawings with a fixed contract font. A host without that
    font, or with a different rasteriser, refuses or fails verification, and a withheld frame
    otherwise gives no reason a reader can act on."""
    import os

    out: dict = {}
    try:
        import PIL
        from PIL import features

        out["pillow"] = PIL.__version__
        out["freetype"] = features.version("freetype2")
    except Exception as exc:  # noqa: BLE001
        out["pillow"] = f"unavailable: {type(exc).__name__}"
    try:
        import numpy

        out["numpy"] = numpy.__version__
    except Exception:  # noqa: BLE001
        out["numpy"] = "unavailable"
    from ..visual import render_contract as K

    configured = os.environ.get("BRAMBLELOOP_FONT_PATH", "").strip()
    paths = ((configured,) if configured else ()) + tuple(K.FONT_PATHS)
    out["contract_font"] = next((p for p in paths if p and os.path.exists(p)), None)
    out["contract_font_ok"] = out["contract_font"] is not None
    return out


def pieces_finding(manifest: dict, cir) -> str | None:
    """A hero that shows fewer pieces than a single-component CIR makes, or None.

    The verifier measures the piece it is given; it does not ask whether the hero shows the
    *set* the title sells. A flat "Set (6)" drawn as one piece, with alt text saying "the whole
    piece", tells a buyer they get one object (found W4-IMAGES 2026-10-11: the rounds form
    draws `make` copies, the flat form does not)."""
    try:
        if manifest.get("view") != "hero" or len(cir.components) != 1:
            return None
        make = int(manifest.get("pieces") or cir.components[0].make or 1)
        layout = manifest.get("layout") or {}
        shown = int(layout.get("objects") or layout.get("copies") or 1)
    except Exception:  # noqa: BLE001 - unreadable is a finding, never a pass
        return "the hero's piece count could not be read"
    if shown < make:
        return (f"the hero shows {shown} of the {make} pieces the pattern makes, and its alt "
                f"text calls it the whole piece")
    return None


def _approval(db, cir, verified: bool) -> dict:
    """Customer approval, computed. False unless every condition holds; each missing one is named."""
    reasons: list[str] = []
    cert = None
    if db is not None:
        try:
            from sqlalchemy import select

            from ..core.models import ListingSetCertificateRecord

            with db.session() as s:
                cert = s.scalars(select(ListingSetCertificateRecord).where(
                    ListingSetCertificateRecord.product_slug == cir.slug,
                    ListingSetCertificateRecord.version == cir.version,
                    ListingSetCertificateRecord.state == "valid")).first()
                cert = None if cert is None else cert.id
        except Exception:  # noqa: BLE001 - unreadable is absent
            cert = None
    if not verified:
        reasons.append("the frame does not verify against the CIR on its exact bytes")
    if cert is None:
        reasons.append(f"no valid listing-set certificate for {cir.slug}@{cir.version} in this "
                       "database (#70)")
    reasons.append("parity HERO and COMPETITIVE are unjudged: gate image_vision is closed and "
                   "benchmark galleries are unobserved (D-FB-9). Unjudged is not a pass")
    reasons.append("no owner publication grant (D-FB-10) is resolved for this release here")
    return {"customer_approved": False, "listing_set_certificate": cert, "why_not": reasons}


def _remediation(row: dict) -> list[str]:
    steps: list[str] = []
    if row["status"] == NOT_RENDERED:
        steps.append(f"Company: fix the CIR/renderer refusal ({row.get('error')}); no image may "
                     "substitute for it")
    elif row["status"] == INCOMPLETE:
        steps.append("Company (VISUAL): draw a flat single-component hero with `make` copies, "
                     "as the rounds form already does, and extend render_verification's flat "
                     "hero to count and verify every copy. Until then the hero stays withheld")
    elif row["status"] in (FAILED_VERIFICATION, UNVERIFIED):
        if not row["environment"].get("contract_font_ok"):
            steps.append("Deploy: the contract font is missing on this host (Dockerfile installs "
                         "fonts-dejavu-core); redeploy the image that has it")
        steps.append(f"Company: re-engineer the frame until render_verification PASSes "
                     f"(failed {row['verifier']['failed'] or row['verifier']['unknown']}); never "
                     "relabel or loosen the verifier")
    else:
        steps.append("None for the frame itself: it verifies on its bytes and is the qualified "
                     "deterministic disclosed render")
    if row["product_truth"]["passes"] is not True:
        steps.append(f"PRODUCT: Product Truth gates fail {row['product_truth']['failed']}")
    steps.append("Release chain: certify the release and issue its listing-set certificate "
                 "(gate.certify -> assets.build -> listing.seo) in production")
    steps.append("Owner gate: fund_model opens image_vision for the HERO description; "
                 "benchmark_purchase/benchmark_observation for the COMPETITIVE blind review")
    steps.append("Owner: publication grant per release (D-FB-10), after the steps above")
    steps.append("Optional, for LIFESTYLE: VB-1 P2 or photographs of a physically made sample. "
                 "Never a generated picture of an object nobody made")
    return steps


def assess(build_key: str, *, db=None, env: dict | None = None) -> dict:
    """One candidate image: what it is, what it shows, how it was made, and whether it may be used."""
    from ..products import launch0 as L

    env = env if env is not None else environment()
    meta = next((c for c in candidates() if c["build"] == build_key),
                {"slug": build_key, "title": build_key, "group": "unknown",
                 "in_customer_preview": False})
    row: dict = {**meta, "environment": env, "provenance": PROVENANCE,
                 "generated": False, "photograph": False, "png": None, "thumb": None}
    try:
        cir = _cir(build_key)
    except Exception as exc:  # noqa: BLE001
        row.update(status=NOT_RENDERED, error=f"{type(exc).__name__}: {exc}"[:200],
                   verifier={"status": "NOT_RUN", "failed": [], "unknown": [], "checks": []},
                   product_truth=_product_truth(meta["slug"]),
                   approval={"customer_approved": False, "why_not": ["no CIR"]})
        row["remediation"] = _remediation(row)
        return row
    row.update(cir_slug=cir.slug, cir_version=cir.version, cir_fingerprint=cir.fingerprint)
    row["product_truth"] = _product_truth(meta["slug"])
    try:
        from ..publish import disclosed_listing
        from ..visual import disclosed_render, render_verification

        key = (build_key, cir.fingerprint)
        hit = _RENDERS.get(key)
        if hit is None:
            frame = disclosed_render.render(cir, "hero")
            hit = {"frame": frame,
                   "verdict": render_verification.verify(frame.png, cir=cir, view="hero"),
                   "caption": disclosed_listing.caption_in_image(frame.png, cir),
                   "alt": disclosed_listing.alt_text(frame.manifest, cir)}
            if len(_RENDERS) >= 64:
                _RENDERS.pop(next(iter(_RENDERS)), None)
            _RENDERS[key] = hit
        frame, verdict, caption, alt = hit["frame"], hit["verdict"], hit["caption"], hit["alt"]
        row.update(
            png=frame.png, sha256=hashlib.sha256(frame.png).hexdigest(),
            renderer=getattr(disclosed_render, "RENDERER_VERSION", ""),
            verifier={"status": verdict.get("status"),
                      "version": verdict.get("verifier_version"),
                      "failed": list(verdict.get("failed") or []),
                      "unknown": list(verdict.get("unknown") or []),
                      "checks": [{"check": c.get("check"), "status": c.get("status"),
                                  "why": str(c.get("why") or "")[:160]}
                                 for c in verdict.get("checks") or []]},
            disclosure={"in_image": caption.get("status") == "PASS",
                        "in_alt_text": disclosed_listing._phrase_in(alt)
                        and len(alt) <= disclosed_listing.ALT_TEXT_MAX,
                        "alt_text": alt})
        ok = verdict.get("status") == "PASS" and row["disclosure"]["in_image"]
        row["pieces_finding"] = pieces_finding(frame.manifest, cir)
        row["status"] = (INCOMPLETE if ok and row["pieces_finding"] else
                         VERIFIED_NOT_APPROVED if ok else
                         FAILED_VERIFICATION if verdict.get("status") == "FAIL"
                         or not row["disclosure"]["in_image"] else UNVERIFIED)
    except Exception as exc:  # noqa: BLE001 - a refusal is reported, never replaced
        row.update(status=NOT_RENDERED, error=f"{type(exc).__name__}: {exc}"[:200],
                   verifier={"status": "NOT_RUN", "failed": [], "unknown": [], "checks": []})
    verified = row["status"] == VERIFIED_NOT_APPROVED
    row["approval"] = _approval(db, cir, verified)
    if row["approval"]["customer_approved"]:  # never true today; kept for completeness
        row["status"] = APPROVED
    row["finished_object"] = (
        "Shows the finished object's geometry, colours and stitch pattern as the CIR computes "
        "them. Sizes are arithmetic from the stated gauge; no sample has been made "
        "(twin.calibrated False), so drape, texture and real colour are not shown")
    row["limitations"] = [
        "Digital rendering, not a photograph: the disclosure is in the pixels and alt text",
        "Not approved for customers: " + "; ".join(row["approval"]["why_not"][:2]),
        "No lifestyle or in-use picture exists; none may be generated in its place",
    ]
    if row["status"] == INCOMPLETE:
        row["limitations"].insert(0, "Misleading as a hero: " + row["pieces_finding"]
                                  + ". Each piece verifies, but the set is not shown")
    elif row["status"] != VERIFIED_NOT_APPROVED:
        row["limitations"].insert(0, "This frame does NOT match its pattern on the verifier's "
                                     "measurements. It is shown here only so the owner can see "
                                     "why it is withheld")
    if row["png"]:
        from PIL import Image

        im = Image.open(io.BytesIO(row["png"])).convert("RGB")
        im.thumbnail((THUMB_PX, THUMB_PX))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        row["thumb"] = buf.getvalue()
    row["remediation"] = _remediation(row)
    return row


def review(db=None, *, builds: list[str] | None = None) -> dict:
    env = environment()
    rows = [assess(c["build"], db=db, env=env) for c in candidates()
            if builds is None or c["build"] in builds]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"rows": rows, "counts": counts, "environment": env,
            "customer_approved": sum(1 for r in rows if r["approval"]["customer_approved"])}


def summary(db=None, *, builds: list[str] | None = None) -> dict:
    """The review without image bytes (JSON-safe), for reports and tests."""
    out = review(db, builds=builds)
    out["rows"] = [{k: v for k, v in r.items() if k not in ("png", "thumb")} for r in out["rows"]]
    return out


# ---- the page -----------------------------------------------------------------------------

def _esc(v) -> str:
    from ..app.security import esc

    return str(esc(v))


_CSS = """
:root{--bg:#f6f3ee;--fg:#1f1d1a;--card:#fff;--line:#d9d2c6;--warn:#8a1c1c;--ok:#1d5a2c;
--amber:#7a4b00}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece7df;--card:#22201d;
--line:#3a3631;--warn:#ff8f8f;--ok:#8fd19e;--amber:#f0c070}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:12px 16px}
.banner{border:2px solid var(--warn);color:var(--warn);padding:10px 12px;border-radius:8px;
font-weight:700;margin-bottom:12px}
.grid{display:grid;grid-template-columns:1fr;gap:14px}
@media (min-width:760px){.grid{grid-template-columns:1fr 1fr}}
@media (min-width:1200px){.grid{grid-template-columns:1fr 1fr 1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;
min-width:0}
.card h2{font-size:16px;margin:0 0 4px}.meta{font-size:12px;opacity:.8;word-break:break-all}
.imgwrap{position:relative;margin:8px 0}.imgwrap img{width:100%;height:auto;display:block;
border-radius:6px;border:1px solid var(--line)}
.stamp{position:absolute;left:0;right:0;top:0;padding:6px 8px;font-weight:800;font-size:13px;
color:#fff;background:rgba(138,28,28,.92);border-radius:6px 6px 0 0}
.stamp.v{background:rgba(122,75,0,.92)}
.status{font-weight:800;margin:6px 0}.status.bad{color:var(--warn)}.status.v{color:var(--amber)}
ul{padding-left:18px;margin:6px 0}li{margin:2px 0}
table{width:100%;border-collapse:collapse;font-size:12px}td{border-top:1px solid var(--line);
padding:3px 4px;vertical-align:top;word-break:break-word}
details{margin-top:6px}summary{cursor:pointer;font-weight:600}
.none{padding:30px 10px;text-align:center;border:1px dashed var(--line);border-radius:6px}
"""


def _card(r: dict) -> str:
    verified = r["status"] == VERIFIED_NOT_APPROVED
    cls = "v" if verified else "bad"
    if r.get("thumb"):
        uri = "data:image/png;base64," + base64.b64encode(r["thumb"]).decode("ascii")
        alt = (r.get("disclosure") or {}).get("alt_text", "")
        img = (f'<div class="imgwrap"><img src="{_esc(uri)}" alt="{_esc(alt)}">'
               f'<div class="stamp {cls}">INTERNAL · {_esc(r["status"])}</div></div>')
    else:
        img = f'<div class="none">No image: {_esc(r.get("error") or r["status"])}</div>'
    checks = "".join(f"<tr><td>{_esc(c['check'])}</td><td>{_esc(c['status'])}</td>"
                     f"<td>{_esc(c['why'])}</td></tr>"
                     for c in (r.get("verifier") or {}).get("checks") or [])
    pt = r["product_truth"]
    flags = (f"Product Truth: {'PASS' if pt['passes'] else 'FAIL' if pt['passes'] is False else 'UNKNOWN'}"
             + (f" (failed {', '.join(pt['failed'])})" if pt["failed"] else ""))
    disc = r.get("disclosure") or {}
    return (
        f'<article class="card"><h2>{_esc(r["title"])}</h2>'
        f'<div class="meta">{_esc(r.get("cir_slug", r["slug"]))}@{_esc(r.get("cir_version", "?"))}'
        f' · build {_esc(r["build"])} · {_esc(r["group"])}'
        f'{" · shown in customer preview" if r.get("in_customer_preview") else ""}<br>'
        f'sha256 {_esc(r.get("sha256", "none"))}</div>'
        f'{img}<div class="status {cls}">{_esc(r["status"])}</div>'
        f'<div><b>Limitations</b><ul>'
        + "".join(f"<li>{_esc(x)}</li>" for x in r.get("limitations") or [])
        + f'</ul></div><div class="meta">How made: {_esc(r["provenance"])}. Verifier '
        f'{_esc((r.get("verifier") or {}).get("status"))} '
        f'({_esc((r.get("verifier") or {}).get("version", ""))}). Disclosure in image: '
        f'{_esc(disc.get("in_image"))}; in alt text: {_esc(disc.get("in_alt_text"))}. '
        f'{_esc(flags)}.</div>'
        f'<details><summary>Remediation path</summary><ol>'
        + "".join(f"<li>{_esc(s)}</li>" for s in r["remediation"])
        + f'</ol></details><details><summary>Verifier checks ({len((r.get("verifier") or {}).get("checks") or [])})'
        f'</summary><table>{checks}</table></details></article>')


def render_page(db=None, *, now=None, builds: list[str] | None = None) -> str:
    data = review(db, builds=builds)
    env = data["environment"]
    counts = " · ".join(f"{_esc(k)}: {v}" for k, v in sorted(data["counts"].items()))
    nots = "".join(f"<li><b>{_esc(n['what'])}</b> ({_esc(n['where'])}): {_esc(n['why'])}</li>"
                   for n in NOT_CANDIDATES)
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex,nofollow\">"
        f"<title>{_esc(PAGE_TITLE)}</title><style>{_CSS}</style></head><body>"
        "<div class=\"banner\" role=\"note\">OWNER ONLY, INTERNAL REVIEW. Not a customer page. "
        "No image here is approved for customer use. A frame marked FAILED or NOT VERIFIED is "
        "inaccurate or unproven, and stays withheld from the customer preview.</div>"
        f"<h1 style=\"font-size:19px;margin:4px 0\">Candidate listing images</h1>"
        f"<p class=\"meta\">As of {_esc(_now(now).isoformat(timespec='seconds'))} · {counts} · "
        f"customer-approved: {data['customer_approved']} · renderer host: Pillow "
        f"{_esc(env.get('pillow'))}, FreeType {_esc(env.get('freetype'))}, contract font "
        f"{_esc(env.get('contract_font') or 'MISSING')}</p>"
        "<div class=\"grid\">" + "".join(_card(r) for r in data["rows"]) + "</div>"
        "<h2 style=\"font-size:16px;margin-top:18px\">Image material that is not a candidate</h2>"
        f"<ul>{nots}</ul></body></html>")
