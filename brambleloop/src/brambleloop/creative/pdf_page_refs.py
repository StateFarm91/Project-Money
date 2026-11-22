"""ENG-IMAGES-PDFREF: the certified pattern PDF's own pages as FLUX 3 reference images.

The owner's hand method, which has had no rejections: asked what they gave FLUX 3 when making
the basket images by hand, the owner answered "PDF pages as images". They uploaded pages of
the product's pattern PDF as the reference images, with a prompt. This module does the same
thing deterministically, from the release's CERTIFIED premium PDF (US-terms edition,
`publish.sale_pipeline.certified_premium_pdfs`), so the model sees the palette, the colour
bands and the repeats as the buyer's document draws them.

**Which pages.** Each page is classified by its own text (PDFium's text layer, the producer's
path), never by a model:

* `pdf_cover`       -- page 1, the cover with the finished-product render and "At a glance";
* `pdf_colour_key`  -- the materials / colour key page (COLOUR A, colourway, palette);
* `pdf_chart`       -- every chart, schematic or diagram page (the colour bands and repeats);
* `pdf_finished`    -- the finished-design gallery page;
* `pdf_chart_key`   -- the chart-symbols page;
* `pdf_instructions` -- the written rounds, which name every round's colour.

Pages are chosen in that priority order (page order within a kind) up to the number of
reference slots left in the request, and sent in that order. The same PDF bytes always give
the same pages in the same order with the same bytes: the classifier is pure, the raster is a
fixed long side at a fixed PDFium build, and the PNG is written without metadata.

**Cache.** Keyed by the PDF's sha256 and `RENDER_VERSION` (which names the PDFium build): a
second request for the same PDF reads the cached pages, verified against their recorded
hashes, rather than rendering again. A cache entry whose bytes do not match is discarded and
re-rendered. Rendering spends nothing; the paid call is still made once per input hash by
`gateway.images` (the page bytes are inside the request body, so the same PDF gives the same
request fingerprint).

Deterministic and local: no model, no provider and no network call.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import threading
from pathlib import Path

KINDS = ("pdf_cover", "pdf_colour_key", "pdf_chart", "pdf_finished", "pdf_chart_key",
         "pdf_instructions")
LABELS = {
    "pdf_cover": "page of the certified pattern PDF: the cover, with the finished product",
    "pdf_colour_key": "page of the certified pattern PDF: the materials and colour key "
                      "(the exact yarn colours)",
    "pdf_chart": "page of the certified pattern PDF: the chart / schematic (colour bands, "
                 "round and repeat counts)",
    "pdf_finished": "page of the certified pattern PDF: the finished design",
    "pdf_chart_key": "page of the certified pattern PDF: the chart key",
    "pdf_instructions": "page of the certified pattern PDF: the written rounds, each round's "
                        "colour named",
}
TERMINOLOGY = "US"
LONG_SIDE_PX = 1536            # 1188 x 1536 for US Letter: ~1.8 MP, legible chart labels
MAX_PAGES = 6                  # FLUX 3 Image takes 10; the four CIR references come first
MAX_CHART_PAGES = 3            # a many-chart PDF still leaves room for the finished/key pages
CACHE_ENV = "BRAMBLELOOP_PDF_PAGE_CACHE"
_MEMO: dict[str, dict] = {}
_MEMO_LOCK = threading.RLock()


class PdfPagesRefused(ValueError):
    """The PDF cannot be read as pages; nothing is sent."""


def _pdfium_version() -> str:
    try:
        import pypdfium2

        return str(getattr(pypdfium2, "PDFIUM_INFO", "") or getattr(pypdfium2, "__version__", ""))
    except Exception:  # noqa: BLE001
        return "unknown"


RENDER_VERSION = f"pdf-page-refs/1.0.0;long={LONG_SIDE_PX};pdfium={_pdfium_version()}"


# --------------------------------------------------------------------------- classification

HEADING_MAX_CHARS = 48


def _head(text: str) -> str:
    """The page's heading lines: the first few short lines, the running header dropped.
    Body sentences are long, so a word in a paragraph never decides a page's kind."""
    lines = [ln.strip() for ln in (text or "").replace("\r", "").split("\n") if ln.strip()]
    heads = [ln for ln in lines[:4] if len(ln) <= HEADING_MAX_CHARS
             and "brambleloop" not in ln.lower()]
    return " | ".join(heads).lower()


def classify(index: int, text: str) -> str | None:
    """The kind of page `index` (0-based) from its own text, or None if it adds nothing."""
    if index == 0:
        return "pdf_cover"
    head = _head(text)
    if "chart symbols" in head or "chart key" in head or "symbol key" in head:
        return "pdf_chart_key"
    if any(k in head for k in ("chart", "schematic", "diagram", "colour bands",
                               "color bands", "stripe sequence", "colour sequence")):
        return "pdf_chart"
    if any(k in head for k in ("colour key", "color key", "palette", "colour a",
                               "color a", "materials", "what you need")):
        return "pdf_colour_key"
    if "gallery" in head or "finished design" in head:
        return "pdf_finished"
    if "instructions" in head or "step by step" in head:
        return "pdf_instructions"
    return None


def select(page_texts: list[str], limit: int = MAX_PAGES) -> list[dict]:
    """[{index, kind}] chosen from the pages' texts: by kind priority, then page order.
    One cover, colour-key, finished and chart-key page each, up to MAX_CHART_PAGES chart
    pages and one instructions page; pure and stable."""
    limit = max(0, int(limit))
    by_kind: dict[str, list[int]] = {k: [] for k in KINDS}
    for i, t in enumerate(page_texts):
        k = classify(i, t)
        if k:
            by_kind[k].append(i)
    out: list[dict] = []
    for k in KINDS:
        for i in by_kind[k][:MAX_CHART_PAGES if k == "pdf_chart" else 1]:
            if len(out) < limit:
                out.append({"index": i, "kind": k})
    return out


# --------------------------------------------------------------------------- rendering

def _page_texts(doc) -> list[str]:
    out = []
    for i in range(len(doc)):
        page = doc[i]
        tp = page.get_textpage()
        try:
            out.append(tp.get_text_range() or "")
        finally:
            tp.close()
            page.close()
    return out


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _render(pdf: bytes) -> dict:
    from ..visual.contents_frame import PDFIUM_LOCK, _pdfium

    pdfium = _pdfium()
    with PDFIUM_LOCK:
        try:
            doc = pdfium.PdfDocument(pdf)
        except Exception as exc:  # noqa: BLE001
            raise PdfPagesRefused(f"the PDF cannot be opened: {exc}"[:300]) from exc
        try:
            texts = _page_texts(doc)
            chosen = select(texts, MAX_PAGES)
            pages = []
            for c in chosen:
                page = doc[c["index"]]
                try:
                    pw, ph = page.get_size()
                    bitmap = page.render(scale=LONG_SIDE_PX / max(pw, ph))
                    try:
                        img = bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                raw = _png(img)
                pages.append({**c, "page": c["index"] + 1, "px": [img.width, img.height],
                              "sha256": hashlib.sha256(raw).hexdigest(), "data": raw})
            count = len(texts)
        finally:
            doc.close()
    return {"pages": pages, "page_count": count}


def _cache_root() -> Path:
    return Path(os.environ.get(CACHE_ENV) or Path(tempfile.gettempdir()) /
                "brambleloop-pdf-page-refs")


def _entry_dir(pdf_sha: str) -> Path:
    v = hashlib.sha256(RENDER_VERSION.encode()).hexdigest()[:16]
    return _cache_root() / pdf_sha / v


def _read_disk(pdf_sha: str) -> dict | None:
    d = _entry_dir(pdf_sha)
    try:
        man = json.loads((d / "manifest.json").read_text())
        if man.get("pdf_sha256") != pdf_sha or man.get("render_version") != RENDER_VERSION:
            return None
        pages = []
        for p in man["pages"]:
            raw = (d / f"page-{p['page']:03d}.png").read_bytes()
            if hashlib.sha256(raw).hexdigest() != p["sha256"]:
                return None                       # tampered or torn: re-render
            pages.append({**p, "data": raw})
        return {**man, "pages": pages}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_disk(entry: dict) -> None:
    d = _entry_dir(entry["pdf_sha256"])
    try:
        d.mkdir(parents=True, exist_ok=True)
        for p in entry["pages"]:
            tmp = d / f".page-{p['page']:03d}.png.{os.getpid()}"
            tmp.write_bytes(p["data"])
            os.replace(tmp, d / f"page-{p['page']:03d}.png")
        man = {k: v for k, v in entry.items() if k != "pages"}
        man["pages"] = [{k: v for k, v in p.items() if k != "data"} for p in entry["pages"]]
        tmp = d / f".manifest.json.{os.getpid()}"
        tmp.write_text(json.dumps(man, sort_keys=True))
        os.replace(tmp, d / "manifest.json")
    except OSError:
        pass                                      # a cache that cannot be written is no cache


def pages_for(pdf: bytes) -> dict:
    """The chosen pages of `pdf`, rendered once per PDF hash.

    {"pdf_sha256", "render_version", "page_count", "cached": bool,
     "pages": [{"index", "page", "kind", "sha256", "px", "data"}]}"""
    if not pdf:
        raise PdfPagesRefused("no PDF bytes")
    sha = hashlib.sha256(pdf).hexdigest()
    with _MEMO_LOCK:
        hit = _MEMO.get(sha)
        if hit is not None:
            return {**hit, "cached": True}
        disk = _read_disk(sha)
        if disk is not None:
            _MEMO[sha] = {**disk, "cached": False}
            return {**disk, "cached": True}
        got = _render(pdf)
        entry = {"pdf_sha256": sha, "render_version": RENDER_VERSION,
                 "terminology": TERMINOLOGY, "page_count": got["page_count"],
                 "pages": got["pages"]}
        _write_disk(entry)
        _MEMO[sha] = {**entry, "cached": False}
        return {**entry, "cached": False}


def clear_memo() -> None:
    """Tests: forget the in-process cache (the disk cache is keyed separately)."""
    with _MEMO_LOCK:
        _MEMO.clear()


def write_pages(entry: dict, out_dir: str | Path) -> list[dict]:
    """The pages as files under `out_dir`, named by hash: [{kind, page, sha256, path}]."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for p in entry["pages"]:
        path = root / f"pdf-p{p['page']:03d}-{p['sha256'][:16]}.png"
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != p["sha256"]:
            path.write_bytes(p["data"])
        out.append({"kind": p["kind"], "page": p["page"], "sha256": p["sha256"],
                    "path": str(path)})
    return out


def certified_pdf(db, slug: str, version: str, release: str) -> bytes | None:
    """The release's certified premium US-terms PDF bytes (re-hashed on read), or None."""
    if db is None:
        return None
    from ..publish import sale_pipeline

    try:
        pdfs = sale_pipeline.certified_premium_pdfs(db, slug, version, release)
    except Exception:  # noqa: BLE001 - unreadable is absent, and recorded as such
        return None
    return (pdfs or {}).get(TERMINOLOGY)


# --------------------------------------------------------------------------- provenance

SOURCE = "certified_pdf_page"
LABEL_PREFIX = "pdf_"


def is_page_ref(ref) -> bool:
    """A prepared or recorded reference that is a certified-PDF page (kind pattern_derived,
    source certified_pdf_page). The CIR-reference gate counts the four CIR renders only."""
    if not isinstance(ref, dict):
        return False
    return (ref.get("source") == SOURCE
            or str(ref.get("label") or "").startswith(LABEL_PREFIX))
