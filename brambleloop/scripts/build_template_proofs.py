"""Build the ENG-PDF-TEMPLATE proofs: US and UK template PDFs for products in different
families, rendered to PNG and set beside the owner's master template.

Usage (from brambleloop/):  .venv/bin/python scripts/build_template_proofs.py [OUT_DIR]
                            [--sale-checker PATH_TO_sale-pipeline_pdf_standard.py]

Writes to OUT_DIR (default research/final_build/w6/pdf_template_proofs/):
  <slug>_<US|UK>_pages.png         every page of the edition, as a contact sheet
  compare_<slug>_US_pNN.png        template page NN beside the same section in our edition
  manifest.json                    per edition: pages, family, status, sha256, audit checks,
                                   the premium-standard and sale-pipeline checker findings

Gallery images are TEST DOUBLES (publish.pdf_template.test_double_gallery): every proof is
`proof_test_double`, marked NOT CUSTOMER-READY on every page. Nothing here is a customer PDF.
Deterministic: fixed release date, fixed stub images.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from brambleloop.publish import pdf_template as T  # noqa: E402

RELEASED = date(2026, 11, 20)
PRODUCTS = (
    ("hexagon_coasters", "home décor"),
    ("cloudline_blanket", "baby (child-safety)"),
    ("garment:harbour-drop-shoulder-pullover:M", "garment"),
    ("pillow", "pillow"),
    ("snowfall_throw", "blanket"),
)
# template page -> our section key (and which page of that section)
PAIRS = [(1, "cover", 0), (2, "meet_the_pattern", 0), (3, "tools_and_yarn", 0),
         (4, "sizing", 0), (5, "construction", 0), (6, "abbreviations", 0), (7, "pattern", 0),
         (8, "pattern", 1), (9, "finishing", 0), (10, "notes", 0), (11, "gallery", 0),
         (12, "gallery_continued", 0), (13, "about", 0), (14, "copyright", 0)]


def cir_for(key: str):
    if key.startswith("garment:"):
        from brambleloop.products import garments as G

        _g, design, size = key.split(":")
        return G.DESIGNS[design]().build_all()[size]
    if key == "pillow":
        from brambleloop.products import texture

        return texture.build_bobble_pillow()
    from brambleloop.products import launch0

    return launch0.cir_for(key)


def render_pages(pdf: bytes, dpi: int) -> list:
    from PIL import Image

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.pdf"
        src.write_bytes(pdf)
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(src), str(Path(d) / "p")],
                       check=True)
        out = []
        for f in sorted(Path(d).glob("p-*.png")):
            im = Image.open(f)
            im.load()
            out.append(im.convert("RGB"))
        return out


def save_png(img, path: Path) -> None:
    img.quantize(colors=96, method=2, dither=0).save(path, format="PNG", optimize=True)


def contact_sheet(pages: list, cols: int = 5):
    from PIL import Image

    w, h = pages[0].size
    rows = (len(pages) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 6, rows * h + (rows + 1) * 6),
                      (200, 200, 200))
    for i, p in enumerate(pages):
        sheet.paste(p, (6 + (i % cols) * (w + 6), 6 + (i // cols) * (h + 6)))
    return sheet


def pair(a, b):
    from PIL import Image, ImageDraw

    w, h = a.size
    b = b.resize((w, h))
    out = Image.new("RGB", (2 * w + 30, h + 28), (255, 255, 255))
    out.paste(a, (10, 24))
    out.paste(b, (w + 20, 24))
    d = ImageDraw.Draw(out)
    d.text((10, 6), "OWNER MASTER TEMPLATE (spec/07)", fill=(120, 60, 60))
    d.text((w + 20, 6), "ENG-PDF-TEMPLATE RENDER (test-double images)", fill=(47, 62, 51))
    return out


def load_sale_checker(path: str | None):
    if not path:
        return None
    spec = importlib.util.spec_from_file_location("brambleloop.publish._sale_pdf_standard",
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?",
                    default=str(ROOT / "research/final_build/w6/pdf_template_proofs"))
    ap.add_argument("--sale-checker", default=None)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sale = load_sale_checker(args.sale_checker)
    from brambleloop.publish import pdf_photos as PP
    from brambleloop.publish import pdf_standard as premium

    template_pages = render_pages((ROOT / T.TEMPLATE_PATH).read_bytes(), 50)
    gallery = T.test_double_gallery()
    manifest = {"released_on": RELEASED.isoformat(), "template": T.TEMPLATE_PATH,
                "gallery": "test_double (publish.pdf_template.test_double_gallery)",
                "editions": []}
    for key, fam_label in PRODUCTS:
        cir = cir_for(key)
        for term in ("US", "UK"):
            doc = T.build_template_pdf(cir, terminology=term, released_on=RELEASED,
                                       gallery=gallery)
            a = T.audit(doc.pdf_bytes, expected_gallery=doc.gallery)
            prem = premium.audit(doc.pdf_bytes, cir, terminology=term)
            entry = {"product": key, "slug": cir.slug, "version": cir.version,
                     "terminology": term, "family": doc.family, "family_label": fam_label,
                     "status": doc.status, "customer_ready": doc.customer_ready,
                     "pages": doc.pages, "rows_with_counts": doc.rows,
                     "pdf_sha256": hashlib.sha256(doc.pdf_bytes).hexdigest(),
                     "pdf_bytes": len(doc.pdf_bytes), "problems": doc.problems,
                     "audit": {"verdict": a["verdict"],
                               "checks": {c["check"]: c["status"] for c in a["checks"]}},
                     "premium_standard": {"family": prem.family, "ok": prem.ok,
                                          "failing_rules": sorted(prem.failures)}}
            if sale is not None:
                plan = PP.plan([{"sha256": f["sha256"], "role": f["role"],
                                 "position": f["position"], "data": f["data"]}
                                for f in gallery])
                res = sale.check(doc.pdf_bytes, cir=cir, terminology=term,
                                 expected=PP.expected(plan["slots"]))
                entry["sale_pipeline_standard"] = {"verdict": res["verdict"],
                                                   "failed": res["failed"],
                                                   "unknown": res["unknown"]}
            manifest["editions"].append(entry)
            pages = render_pages(doc.pdf_bytes, 36)
            save_png(contact_sheet(pages), out / f"{cir.slug}_{term}_pages.png")
            if key == "hexagon_coasters" and term == "US":
                big = render_pages(doc.pdf_bytes, 50)
                first = {}
                for i, (_p, k) in enumerate(doc.sections):
                    first.setdefault(k, []).append(i)
                for tp, k, n in PAIRS:
                    idx = first.get(k, [])
                    if len(idx) > n:
                        save_png(pair(template_pages[tp - 1], big[idx[n]]),
                                 out / f"compare_{cir.slug}_US_p{tp:02d}.png")
            print(f"{cir.slug} {term}: {doc.pages} pages, {doc.family}, {doc.status}, "
                  f"audit {a['verdict']}, premium {'ok' if prem.ok else sorted(prem.failures)}",
                  flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
