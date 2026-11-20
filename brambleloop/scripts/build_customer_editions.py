"""Build the customer editions of certified patterns, with a provenance manifest.

    PYTHONPATH=src python scripts/build_customer_editions.py \
        --released 2026-10-27 hexagon_coasters basket_small

For each Launch-0 build key: builds the CIR at its released version, certifies it
(`gates.certificate.certify`), renders the US and UK customer PDFs with the premium layout
(`publish.pdf.build_pattern_pdf`), renders each a second time and requires identical bytes,
and writes

    research/final_build/w4/customer_editions/<slug>-<version>/
        <slug>-<version>.pdf            the sale edition, US terms
        <slug>-<version>-uk.pdf         the sale edition, UK terms
        NOT-FOR-SALE-<slug>-<version>-photo-placeholder-proof.pdf
                                        a proof with marked placeholders for sample photos
        MANIFEST.json                   what each file was built from, and its hashes

Nothing is published. `--released` fixes the release date printed in the document, so the
same inputs give the same bytes; without it the build refuses rather than reading the clock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "research" / "final_build" / "w4" / "customer_editions"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False).stdout.strip()


def build(key: str, released: date, out_root: Path) -> dict:
    from brambleloop.brand import pdf_fonts
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.gates.certificate import certify
    from brambleloop.products import launch0
    from brambleloop.publish import pdf

    cir = launch0.cir_for(key)
    result = compile_cir(cir)
    cert = certify(cir)
    if not result.ok or not getattr(cert, "granted", False):
        raise SystemExit(f"{cir.slug}@{cir.version}: not certified; refusing to build an "
                         f"edition of an uncertified release")
    folder = out_root / f"{cir.slug}-{cir.version}"
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, kwargs in (
            (f"{cir.slug}-{cir.version}.pdf", {"terminology": "US"}),
            (f"{cir.slug}-{cir.version}-uk.pdf", {"terminology": "UK"}),
            (f"NOT-FOR-SALE-{cir.slug}-{cir.version}-photo-placeholder-proof.pdf",
             {"terminology": "US", "sample_photo_placeholders": True})):
        doc = pdf.build_pattern_pdf(cir, released_on=released, **kwargs)
        again = pdf.build_pattern_pdf(cir, released_on=released, **kwargs)
        if doc.pdf_bytes != again.pdf_bytes:
            raise SystemExit(f"{name}: two renders of the same inputs differ")
        if doc.problems:
            raise SystemExit(f"{name}: the renderer reports {doc.problems}")
        (folder / name).write_bytes(doc.pdf_bytes)
        files[name] = {
            "edition": ("proof, NOT FOR SALE: marked placeholders for sample photographs"
                        if kwargs.get("sample_photo_placeholders") else "sale"),
            "terminology": kwargs["terminology"],
            "sha256": hashlib.sha256(doc.pdf_bytes).hexdigest(),
            "bytes": len(doc.pdf_bytes),
            "pages": doc.pages,
            "reproducible": True,
            "problems": doc.problems,
            "claims": doc.claims,
            "difficulty": doc.difficulty,
            "figures": doc.figures,
        }
    fonts = {f: hashlib.sha256((pdf_fonts.FONT_DIR / f).read_bytes()).hexdigest()
             for f in sorted(pdf_fonts.FACES.values())}
    manifest = {
        "slug": cir.slug,
        "version": cir.version,
        "title": cir.title,
        "build_key": key,
        "builder": f"brambleloop.products.launch0.cir_for({key!r})",
        "cir_fingerprint": cir.fingerprint,
        "release_hash": cert.release_hash,
        "certificate_granted": bool(cert.granted),
        "compiles": bool(result.ok),
        "released_on": released.isoformat(),
        "engine_commit": _git("rev-parse", "HEAD"),
        "engine_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "engine_source_clean": _git("status", "--porcelain", "--", "src") == "",
        "generation_command": (f"cd brambleloop && PYTHONPATH=src python "
                               f"scripts/build_customer_editions.py --released "
                               f"{released.isoformat()} {key}"),
        "reproducibility": ("each file rendered twice in one process with identical bytes; "
                            "reportlab invariant mode, fixed release date, pinned fonts, "
                            "deterministic PNG/JPEG encodes"),
        "fonts_sha256": fonts,
        "files": files,
        "physical_sample": "none recorded; twin.calibrated=False, so every size and yarn "
                           "amount in the document is computed and labelled as such",
        "images": "every product picture is a disclosed deterministic render "
                  "(visual.disclosed_render) or a construction diagram "
                  "(publish.construction_diagrams); no photograph and no generated image",
    }
    (folder / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--released", required=True, help="release date printed, YYYY-MM-DD")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("keys", nargs="+", help="products.launch0 build keys")
    a = ap.parse_args(argv)
    released = date.fromisoformat(a.released)
    for key in a.keys:
        m = build(key, released, Path(a.out))
        for name, f in m["files"].items():
            print(f"{name}  {f['pages']} pages  {f['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
