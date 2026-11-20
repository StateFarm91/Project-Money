"""The premium pattern-PDF standard, checked deterministically from the BUILT bytes
(D-OWNER-PDF-STANDARD; ENG-SALE-PIPELINE).

"Listings aren't ready without beautiful PDFs like the one I shared. That's the standard."
`research/benchmarks/PDF_STRUCTURE_STANDARD.md` is the standard (structure only; nothing of
the benchmark's text, numbers, art or layout is used). This module reads a finished PDF with
pypdf -- the file a buyer downloads, never the template or the layout's own report of itself
-- and checks, per edition (US and UK):

* **sections** (family-aware): every pattern carries the package `publish.pdf`
  requires for its CIR (`package_requirements`: a graded garment adds its size chart and fit,
  construction overview, schematic and care), plus the parts the standard asks of every
  family: the cover, the overview, the finished size, finishing, the picture disclosure and
  the licence;
* **photo slots**: the count of embedded raster images per slot. An image counts only if its
  decoded stream is exactly the deterministic rendition (`publish.pdf_photos.rendition`) of a
  frame of the release's certified campaign gallery. The cover hero must be full bleed, the
  overview page carries the lifestyle image, the construction page the progress image, and
  the gallery page 5 to 6 certified images;
* **schematic and diagrams**: the schematic heading, with a raster drawing on its page that
  is not a campaign image, and inline construction mini-diagrams on the instruction pages;
* **page range**: plausible for the family;
* **a stitch count on every row**: every row or round label in the instructions is followed
  by its count before the next label;
* **the licence page**: every paragraph `commerce.terms` decides for the PDF appears, in the
  edition's own text, on the "Terms and support" pages.

Each check is PASS, FAIL or UNKNOWN. The verdict is PASS only when every check PASSes;
UNKNOWN is never PASS. `images="pending"` checks everything except the photo slots, which
read PENDING: that is the pre-image readiness reading (D-OWNER-SPEND-ORDER: the text,
schematics and diagrams must already pass before a gallery is paid for). A pending reading is
never a certificate.

No model, network or spend. Deterministic: same bytes, same expectation, same verdict.
"""
from __future__ import annotations

import hashlib
import io
import re

PASS, FAIL, UNKNOWN, PENDING = "PASS", "FAIL", "UNKNOWN", "PENDING"
STANDARD_PATH = "research/benchmarks/PDF_STRUCTURE_STANDARD.md"
CHECKER_VERSION = "pdf_standard/1"
TERMINOLOGIES = ("US", "UK")

# Major sections start on a page of their own (`publish.pdf._render` calls new_page for
# each); a page belongs to the last major heading set on or before it.
MAJOR = ("Overview", "How it is made", "Materials", "Gauge, and why it matters here",
         "Abbreviations", "Instructions", "Chart", "Gallery", "Technique help",
         "Terms and support", "Safety notes for a children's item")
# Page range by family. A coaster's concise PDF and a graded garment's manual differ.
PAGE_RANGE = {"home": (6, 48), "garment": (10, 80)}
FULL_BLEED_MIN = 0.98    # of the page width
_ROW_LABEL = re.compile(r"(?m)^(?:Rnds?|Rows?|Rounds?)\s+\d+[^:\n]{0,60}:")
_COUNT = re.compile(r"\(\s*\d+\s+(?:sts?|stitches|ch|chs)\b[^)]*\)")


def standard_sha256(root=None) -> str | None:
    """The hash of the standard document the checker was run against (None if unreadable)."""
    from pathlib import Path

    base = Path(root) if root else Path(__file__).resolve().parents[3]
    try:
        return hashlib.sha256((base / STANDARD_PATH).read_bytes()).hexdigest()
    except OSError:
        return None


def family(cir) -> str:
    return "garment" if getattr(cir, "grading", None) is not None else "home"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _page_images(page) -> list[dict]:
    """Every image XObject drawn on the page: its decoded-stream sha256, filter and the drawn
    width/height in points (from the `cm` in force at its `Do`)."""
    from pypdf.generic import ContentStream

    res = page.get("/Resources") or {}
    xobjs = res.get("/XObject") or {}
    xobjs = xobjs.get_object() if hasattr(xobjs, "get_object") else xobjs
    info: dict[str, dict] = {}
    for name, ref in (xobjs or {}).items():
        obj = ref.get_object()
        if obj.get("/Subtype") != "/Image":
            continue
        filters = obj.get("/Filter")
        filters = [str(f) for f in (filters if isinstance(filters, list) else [filters])
                   if f is not None]
        try:
            data = obj.get_data()
            sha = hashlib.sha256(data).hexdigest()
        except Exception:  # noqa: BLE001 - an unreadable image is never a match
            sha = None
        info[str(name)] = {"sha256": sha, "dct": "/DCTDecode" in filters,
                           "px": (int(obj.get("/Width") or 0), int(obj.get("/Height") or 0))}
    out = []
    contents = page.get_contents()
    if contents is None:
        return out
    try:
        ops = ContentStream(contents, page.pdf).operations
    except Exception:  # noqa: BLE001
        return [dict(v, name=k, drawn=None) for k, v in info.items()]
    stack, ctm = [], [1, 0, 0, 1, 0, 0]

    def mul(m, n):
        a, b, c, d, e, f = m
        a2, b2, c2, d2, e2, f2 = n
        return [a * a2 + b * c2, a * b2 + b * d2, c * a2 + d * c2, c * b2 + d * d2,
                e * a2 + f * c2 + e2, e * b2 + f * d2 + f2]

    for operands, op in ops:
        if op == b"q":
            stack.append(list(ctm))
        elif op == b"Q":
            ctm = stack.pop() if stack else [1, 0, 0, 1, 0, 0]
        elif op == b"cm":
            ctm = mul([float(x) for x in operands], ctm)
        elif op == b"Do":
            name = str(operands[0])
            if name in info:
                w = (ctm[0] ** 2 + ctm[1] ** 2) ** 0.5
                h = (ctm[2] ** 2 + ctm[3] ** 2) ** 0.5
                out.append(dict(info[name], name=name, drawn=(w, h)))
    return out


def read(pdf_bytes: bytes) -> dict:
    """The parts of a built PDF the standard is checked against."""
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    section = "Cover"
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        lines = [ln.strip() for ln in text.split("\n")]
        heads = [h for h in MAJOR if any(ln == h or ln.startswith(h + " (") for ln in lines)]
        if i > 0 and heads:
            # the first major heading set on the page, in reading order
            section = min(heads, key=lambda h: next(j for j, ln in enumerate(lines)
                                                    if ln == h or ln.startswith(h + " (")))
        box = page.mediabox
        pages.append({"index": i + 1, "text": text, "lines": lines,
                      "section": "Cover" if i == 0 else section,
                      "width": float(box.width), "height": float(box.height),
                      "images": _page_images(page)})
    return {"pages": pages, "page_count": len(pages)}


def _has_line(doc: dict, heading: str) -> bool:
    """A heading or label set as its own line (labels are set in capitals, so the match
    ignores case)."""
    h = heading.casefold()
    return any(ln.casefold() == h or ln.casefold().startswith(h + " (")
               for p in doc["pages"] for ln in p["lines"])


def _check(name: str, status: str, why: str = "", **detail) -> dict:
    return {"check": name, "status": status, "why": why, **detail}


def _sections(doc: dict, cir, terminology: str) -> list[dict]:
    from . import pdf as P

    need = list(P.package_requirements(cir))
    need += ["Overview", "Finishing", "Terms and support"]
    missing = [h for h in dict.fromkeys(need) if not _has_line(doc, h)]
    out = [_check("sections", FAIL if missing else PASS,
                  f"missing {missing}" if missing else "", required=list(dict.fromkeys(need)))]
    t = terminology.upper()
    cover = _norm(doc["pages"][0]["text"]) if doc["pages"] else ""
    out.append(_check("cover", PASS if (cir.title in cover and f"{t} terms" in cover) else FAIL,
                      "" if (cir.title in cover and f"{t} terms" in cover) else
                      f"cover does not name the pattern and its {t} terms"))
    allt = _norm("\n".join(p["text"] for p in doc["pages"]))
    out.append(_check("terminology", PASS if f"Instructions ({t} terms)" in allt else FAIL,
                      "" if f"Instructions ({t} terms)" in allt else
                      f"no 'Instructions ({t} terms)' section"))
    size_ok = "finished size" in allt.casefold()
    out.append(_check("finished_size", PASS if size_ok else FAIL,
                      "" if size_ok else "no finished size stated"))
    disc = "About the pictures" in allt
    out.append(_check("disclosure", PASS if disc else FAIL,
                      "" if disc else "no picture disclosure"))
    return out


def _licence(doc: dict) -> dict:
    from . import pdf as P

    pages = [p for p in doc["pages"] if p["section"] == "Terms and support"]
    if not pages:
        return _check("licence_page", FAIL, "no 'Terms and support' page")
    text = _norm("\n".join(p["text"] for p in pages))
    paras = [_norm(ln[2:] if ln.startswith("- ") else ln) for ln in P.licence_paragraphs()]
    missing = [p[:60] for p in paras if p and p[:60] not in text]
    return _check("licence_page", FAIL if missing else PASS,
                  f"licence paragraphs missing: {missing[:3]}" if missing else "",
                  pages=[p["index"] for p in pages])


def _stitch_counts(doc: dict) -> dict:
    pages = [p for p in doc["pages"] if p["section"] == "Instructions"]
    if not pages:
        return _check("stitch_counts", FAIL, "no instruction pages")
    text = "\n".join("\n".join(p["lines"]) for p in pages)
    labels = list(_ROW_LABEL.finditer(text))
    if not labels:
        return _check("stitch_counts", FAIL, "no row or round labels found in the instructions")
    missing = []
    for k, m in enumerate(labels):
        end = labels[k + 1].start() if k + 1 < len(labels) else len(text)
        seg = text[m.end():end]
        cut = re.search(r"(?m)^(?:after (?:Rnd|Row|Round)\b|©)", seg)
        if cut:
            seg = seg[:cut.start()]
        if not _COUNT.search(seg):
            missing.append(_norm(m.group(0)))
    return _check("stitch_counts", FAIL if missing else PASS,
                  f"{len(missing)} of {len(labels)} rows lack a stitch count, e.g. "
                  f"{missing[:3]}" if missing else "", rows=len(labels))


def _non_campaign(images, renditions) -> list[dict]:
    return [im for im in images if im.get("sha256") not in renditions]


def _schematic_and_diagrams(doc: dict, renditions: set) -> list[dict]:
    out = []
    sch_pages = [p for p in doc["pages"] if any(ln == "Schematic" or ln.startswith(
        "Schematic with") for ln in p["lines"]) or "SCHEMATIC WITH FINISHED" in p["text"]]
    drawn = [p for p in sch_pages if _non_campaign(p["images"], renditions)]
    out.append(_check("schematic", PASS if drawn else FAIL,
                      "" if drawn else ("no schematic section" if not sch_pages else
                                        "the schematic section has no drawing"),
                      pages=[p["index"] for p in sch_pages]))
    ins = [p for p in doc["pages"] if p["section"] == "Instructions"]
    diagrams = sum(len(_non_campaign(p["images"], renditions)) for p in ins)
    out.append(_check("diagrams", PASS if diagrams else FAIL,
                      "" if diagrams else "no inline construction diagram on the instruction "
                                          "pages", count=diagrams))
    return out


def _page_range(doc: dict, fam: str) -> dict:
    lo, hi = PAGE_RANGE[fam]
    n = doc["page_count"]
    ok = lo <= n <= hi
    return _check("page_range", PASS if ok else FAIL,
                  "" if ok else f"{n} pages is outside the plausible {lo}-{hi} for a {fam} "
                                f"pattern", pages=n, range=[lo, hi])


def _slots(doc: dict, expected: dict | None) -> list[dict]:
    from . import pdf_photos as PP

    if not expected or not isinstance(expected.get("slots"), dict):
        return [_check(f"slot:{s}", UNKNOWN, "no certified gallery expectation") for s in PP.SLOTS]
    want = {s: set(expected["slots"].get(s) or []) for s in PP.SLOTS}
    allowed = set(expected.get("renditions") or {})

    def found(pages, slot):
        return [im for p in pages for im in p["images"]
                if im.get("dct") and im.get("sha256") in want[slot]]

    out = []
    cover = doc["pages"][:1]
    hero = found(cover, "cover_hero")
    bleed = [im for im in hero if im.get("drawn") and
             im["drawn"][0] >= FULL_BLEED_MIN * cover[0]["width"]] if cover else []
    out.append(_check("slot:cover_hero", PASS if bleed else FAIL,
                      "" if bleed else ("the certified hero is not on the cover" if not hero
                                        else "the cover hero is not full bleed"),
                      count=len(hero)))
    for slot, section, minimum in (("overview_lifestyle", "Overview", 1),
                                   ("progress", "How it is made", 1)):
        pages = [p for p in doc["pages"] if p["section"] == section]
        got = found(pages, slot)
        out.append(_check(f"slot:{slot}", PASS if len(got) >= minimum and want[slot] else FAIL,
                          "" if len(got) >= minimum and want[slot] else
                          f"{len(got)} certified image(s) in the {section} section, "
                          f"{minimum} required", count=len(got)))
    pages = [p for p in doc["pages"] if p["section"] == "Gallery"]
    got = found(pages, "gallery")
    distinct = len({im["sha256"] for im in got})
    ok = PP.GALLERY_MIN <= distinct <= PP.GALLERY_MAX
    out.append(_check("slot:gallery", PASS if ok else FAIL,
                      "" if ok else f"gallery page has {distinct} certified images; "
                                    f"{PP.GALLERY_MIN}-{PP.GALLERY_MAX} required",
                      count=distinct))
    # A photo-style image that is not a certified frame is not allowed anywhere.
    strays = [p["index"] for p in doc["pages"] for im in p["images"]
              if im.get("dct") and im.get("sha256") not in allowed]
    out.append(_check("no_uncertified_photos", FAIL if strays else PASS,
                      f"uncertified JPEG images on pages {sorted(set(strays))}" if strays
                      else ""))
    return out


def check(pdf_bytes: bytes, *, cir, terminology: str, expected: dict | None,
          images: str = "required") -> dict:
    """Check one edition. `expected` is `pdf_photos.expected(slots)` (what certified images
    the slots must hold). `images="pending"` is the pre-image reading: every check but the
    photo slots, which read PENDING."""
    sha = hashlib.sha256(pdf_bytes or b"").hexdigest()
    base = {"terminology": terminology.upper(), "pdf_sha256": sha,
            "checker": CHECKER_VERSION, "family": family(cir)}
    try:
        doc = read(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 - an unreadable PDF is never a pass
        return {**base, "verdict": UNKNOWN, "checks": [_check(
            "readable", UNKNOWN, f"{type(exc).__name__}: {str(exc)[:200]}")]}
    renditions = set((expected or {}).get("renditions") or {})
    checks = [_check("readable", PASS, pages=doc["page_count"])]
    for fn in (lambda: _sections(doc, cir, terminology), lambda: [_licence(doc)],
               lambda: [_stitch_counts(doc)],
               lambda: _schematic_and_diagrams(doc, renditions),
               lambda: [_page_range(doc, family(cir))]):
        try:
            checks += fn()
        except Exception as exc:  # noqa: BLE001 - a check that cannot answer is UNKNOWN
            checks.append(_check("internal", UNKNOWN, f"{type(exc).__name__}: {str(exc)[:200]}"))
    if images == "pending":
        from . import pdf_photos as PP

        checks += [_check(f"slot:{s}", PENDING, "image slots pending (pre-image reading)")
                   for s in PP.SLOTS]
    else:
        try:
            checks += _slots(doc, expected)
        except Exception as exc:  # noqa: BLE001
            checks.append(_check("slots", UNKNOWN, f"{type(exc).__name__}: {str(exc)[:200]}"))
    statuses = [c["status"] for c in checks if c["status"] != PENDING]
    verdict = (FAIL if FAIL in statuses else UNKNOWN if UNKNOWN in statuses else PASS)
    if images == "pending":
        verdict = verdict if verdict != PASS else "PASS_PENDING_IMAGES"
    return {**base, "verdict": verdict, "pages": doc["page_count"],
            "failed": [c["check"] for c in checks if c["status"] == FAIL],
            "unknown": [c["check"] for c in checks if c["status"] == UNKNOWN],
            "checks": checks}
