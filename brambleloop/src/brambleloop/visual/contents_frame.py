"""The CONTENTS gallery frame: a preview of the certified pattern PDF a buyer downloads.

F-030 / F-254 make CONTENTS ("what arrives when they pay") a job every listing answers. A
drawing of the object cannot answer it; only the document can. So this frame is built from
the *released* PDF itself -- the US-terms file whose sha256 `assets.build` recorded for this
release (`runtime.pipeline._certified_pdf_hashes`) -- with its first pages rasterised by
PDFium at a fixed scale and laid out on the contract canvas, lettered with the page count and
the terminology editions on record, and labelled `eligibility.PREVIEW_LABEL` in its pixels
and alt text. Nothing in it is drawn, summarised or invented: every page pixel is the PDF's.

Verification (`verify`) takes a different path to the same facts: the page count is read by
pypdf (the producer counts with PDFium), the PDF's bytes must hash to the hash on record, the
document's own first-page text must name the certified CIR's title and version (so the file is
this release's pattern, not another product's), and the frame is redrawn from the verifier's
facts -- PASS only when the bytes are identical. A frame from another PDF, another release, a
recoloured page or a changed count is FAIL; an unavailable PDF is UNKNOWN, never PASS.

Deterministic and local: no model, provider or network call.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import render_contract as K

KIND = "pattern_contents_preview"
VERSION = "contents-frame/1.0.0"
JOB = "CONTENTS"
TERMINOLOGY = "US"            # the edition previewed; the others are listed, not shown
MAX_PAGES_SHOWN = 4           # a 2 x 2 grid: legible at listing scale, honest about the rest
TITLE_PX = 64
BODY_PX = 46
SMALL_PX = 36
PAGE_BORDER = (88, 70, 44)    # K.GAP: the page edge reads as a sheet on the sage canvas


class ContentsRefused(ValueError):
    """No certified PDF, or one that is not this release's document; nothing is drawn."""


@dataclass(frozen=True)
class ContentsFrame:
    png: bytes
    manifest: dict


def preview_label() -> str:
    from ..publish.eligibility import PREVIEW_LABEL

    return PREVIEW_LABEL


def alt_text(title: str) -> str:
    """The certified alt text: the preview label first, then what the frame shows."""
    from ..publish.disclosed_listing import ALT_TEXT_MAX

    return (f"{preview_label()}. {title}: the first pages of the PDF pattern you download, "
            f"shown at reduced size.")[:ALT_TEXT_MAX]


# --------------------------------------------------------------------------- the PDF

def released_pdf(db, slug: str, version: str, *, store=None, release: str = "") -> dict:
    """The PDF files `assets.build` certified for slug@version: {"US": (sha, bytes), ...}.

    Read from the assets.built record (the hash) and the artifact store (the bytes); a
    stored file whose bytes do not hash to the record is refused, never previewed."""
    from ..core.artifacts import ArtifactMissing, ArtifactStore
    from ..runtime.pipeline import _certified_pdf_hashes

    if db is None:
        raise ContentsRefused("no database: the certified PDF hash cannot be read")
    hashes = _certified_pdf_hashes(db, slug, version, release) or {}
    if TERMINOLOGY not in hashes:
        raise ContentsRefused(f"{slug}@{version}: no certified {TERMINOLOGY}-terms PDF on record")
    store = store if store is not None else ArtifactStore()
    out = {}
    for term, sha in sorted(hashes.items()):
        try:
            data = store.get(sha, db=db)
        except ArtifactMissing as exc:
            raise ContentsRefused(f"{slug}@{version} {term} PDF bytes: {exc}"[:300]) from exc
        if hashlib.sha256(data).hexdigest() != sha:
            raise ContentsRefused(f"{slug}@{version} {term} PDF bytes are not the certified file")
        out[term] = (sha, data)
    return out


def _pages_pdfium(pdf: bytes) -> int:
    import pypdfium2 as pdfium

    return len(pdfium.PdfDocument(pdf))


def _pages_pypdf(pdf: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(pdf)).pages)


def facts(pdf: bytes, *, slug: str, version: str, title: str, editions) -> dict:
    """What the frame states, counted by PDFium (the producer's path)."""
    return _facts(pdf, _pages_pdfium(pdf), slug=slug, version=version, title=title,
                  editions=editions)


def independent_facts(pdf: bytes, *, slug: str, version: str, title: str, editions) -> dict:
    """The same facts by another path (pypdf's page tree), for `verify` to redraw from."""
    return _facts(pdf, _pages_pypdf(pdf), slug=slug, version=version, title=title,
                  editions=editions)


def _facts(pdf: bytes, pages: int, *, slug, version, title, editions) -> dict:
    if pages < 1:
        raise ContentsRefused(f"{slug}: the PDF has no pages")
    return {"job": JOB, "slug": slug, "version": version, "title": title,
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(), "pages": pages,
            "pages_shown": min(pages, MAX_PAGES_SHOWN), "terminology": TERMINOLOGY,
            "editions": sorted(set(editions or [TERMINOLOGY]))}


# --------------------------------------------------------------------------- drawing

def _text(d, xy, text: str, px: int) -> int:
    d.text(xy, text, fill=K.CAPTION, font=K.font(px))
    return int(round(px * 1.35))


def draw(f: dict, pdf: bytes) -> bytes:
    """Pixels from facts and the PDF's own pages. Producer and verifier both call this."""
    import pypdfium2 as pdfium

    img = Image.new("RGB", (K.CANVAS_PX, K.CANVAS_PX), K.BACKGROUND)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    x0, y0, x1, y1 = K.zone_px(K.PRODUCT_ZONE)
    y = y0
    y += _text(d, (x0, y), f"What you download: a {f['pages']}-page PDF pattern", TITLE_PX)
    others = [e for e in f["editions"] if e != f["terminology"]]
    sub = (f"Shown: the {f['terminology']}-terms edition"
           + (f"; also included: {', '.join(others)}-terms edition" if others else ""))
    y += _text(d, (x0, y), sub, SMALL_PX) + 24
    doc = pdfium.PdfDocument(pdf)
    n = f["pages_shown"]
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols
    gap = 48
    label_h = int(SMALL_PX * 1.35) + 8
    cell_w = (x1 - x0 - gap * (cols - 1)) / cols
    cell_h = (y1 - y - gap * (rows - 1)) / rows - label_h
    for i in range(n):
        page = doc[i]
        pw, ph = page.get_size()
        scale = min(cell_w / pw, cell_h / ph)
        bmp = page.render(scale=scale).to_pil().convert("RGB")
        r, c = divmod(i, cols)
        cx = x0 + c * (cell_w + gap) + (cell_w - bmp.width) / 2
        cy = y + r * (cell_h + label_h + gap)
        px, py = round(cx), round(cy)
        img.paste(bmp, (px, py))
        d.rectangle([px - 3, py - 3, px + bmp.width + 2, py + bmp.height + 2],
                    outline=PAGE_BORDER, width=3)
        _text(d, (px, py + bmp.height + 8), f"Page {i + 1} of {f['pages']}", SMALL_PX)
    label = preview_label()
    lf = K.font(K.CAPTION_PX)
    w = d.textlength(label, font=lf)
    d.text((round((K.CANVAS_PX - w) / 2), round(K.CAPTION_TOP * K.CANVAS_PX)), label,
           fill=K.CAPTION, font=lf)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


# --------------------------------------------------------------------------- public API

def render(pdf: bytes, *, slug: str, version: str, title: str, editions=()) -> ContentsFrame:
    f = facts(pdf, slug=slug, version=version, title=title, editions=editions)
    png = draw(f, pdf)
    return ContentsFrame(png=png, manifest={
        "kind": KIND, "version": VERSION, "job": JOB, "facts": f,
        "label": preview_label(), "image_sha256": hashlib.sha256(png).hexdigest(),
        "generated": False, "photograph": False, "model_in_path": False})


def _names_release(pdf: bytes, cir) -> bool:
    """The document's own first page names this CIR's title and version."""
    from pypdf import PdfReader

    first = " ".join((PdfReader(io.BytesIO(pdf)).pages[0].extract_text() or "").split())
    return bool(cir.title) and cir.title in first and f"version {cir.version}" in first


def verify(png: bytes, pdf: bytes, cir, manifest: dict, *, certified_sha256: str,
           editions=()) -> dict:
    """PASS only when the bytes are exactly the redraw of independently read facts from the
    certified PDF, and that PDF is this release's own document."""
    if manifest.get("kind") != KIND or manifest.get("job") != JOB:
        return {"status": "FAIL", "failed": ["not_a_contents_frame"], "checks": {}}
    checks = {}
    sha = hashlib.sha256(png).hexdigest()
    checks["bound"] = sha == manifest.get("image_sha256")
    checks["pdf_is_certified_file"] = hashlib.sha256(pdf).hexdigest() == certified_sha256
    try:
        checks["pdf_names_release"] = _names_release(pdf, cir)
        mine = independent_facts(pdf, slug=cir.slug, version=cir.version,
                                 title=cir.title or cir.slug, editions=editions)
    except Exception as exc:  # noqa: BLE001 - an unreadable PDF is not a verified one
        return {"status": "UNKNOWN", "failed": [], "unknown": [f"{type(exc).__name__}: {exc}"[:200]],
                "checks": checks}
    checks["facts_agree"] = mine == manifest.get("facts")
    checks["pixels_are_the_pages"] = hashlib.sha256(draw(mine, pdf)).hexdigest() == sha
    failed = [k for k, ok in checks.items() if not ok]
    return {"status": "PASS" if not failed else "FAIL", "failed": failed, "unknown": [],
            "checks": checks, "verifier": VERSION}
