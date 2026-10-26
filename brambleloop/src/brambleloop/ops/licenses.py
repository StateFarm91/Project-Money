"""F-415: the licence and attribution register for everything this company ships or depends on.

Python packages (every `requirements.lock` entry), bundled fonts, model providers and outside
data sources each have a row: licence, whether commercial use is permitted, what it obliges,
and the basis for the row. `verified` is true only where the licence was read from something
this build can point at -- installed package metadata, or the licence text committed beside
the font. Provider and data-source terms were not read by this build: those rows say
`UNVERIFIED` and appear in `review_queue()`, never as permitted.

`check()` fails when something is shipped or called without a row, so the next dependency has
to come here before it lands.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # brambleloop/
FONTS = ROOT / "src" / "brambleloop" / "brand" / "fonts"
UNVERIFIED = "UNVERIFIED"
_PKG_BASIS = "installed package metadata (License-Expression/License), suite venv 2026-10-26"
_PERMISSIVE = "permitted (permissive licence)"


def _pkg(lic: str, obligations: str = "keep the copyright and licence notice") -> dict:
    return {"kind": "package", "licence": lic, "commercial_use": _PERMISSIVE,
            "obligations": obligations, "basis": _PKG_BASIS, "verified": True}


PACKAGES: dict[str, dict] = {
    "annotated-doc": _pkg("MIT"), "annotated-types": _pkg("MIT"), "anyio": _pkg("MIT"),
    "cffi": _pkg("MIT-0", "none"), "charset-normalizer": _pkg("MIT"),
    "click": _pkg("BSD-3-Clause"), "cryptography": _pkg("Apache-2.0 OR BSD-3-Clause"),
    "fastapi": _pkg("MIT"), "greenlet": _pkg("MIT AND PSF-2.0"), "h11": _pkg("MIT"),
    "httptools": _pkg("MIT"), "idna": _pkg("BSD-3-Clause"), "jinja2": _pkg("BSD-3-Clause"),
    "markupsafe": _pkg("BSD-3-Clause"),
    "numpy": _pkg("BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"),
    "pillow": _pkg("MIT-CMU"),
    "psycopg2-binary": {"kind": "package", "licence": "LGPL-3.0 with exceptions",
                        "commercial_use": "permitted when used unmodified as a library",
                        "obligations": "LGPL: modifications to psycopg2 itself must be "
                                       "released; using it as a dependency imposes nothing "
                                       "on this code", "basis": _PKG_BASIS, "verified": True},
    "pycparser": _pkg("BSD-3-Clause"), "pydantic": _pkg("MIT"), "pydantic-core": _pkg("MIT"),
    "pypdf": _pkg("BSD-3-Clause"),
    "pypdfium2": _pkg("BSD-3-Clause, Apache-2.0 (PDFium) and bundled dependency licences",
                      "keep notices for pypdfium2 and the bundled PDFium binaries"),
    "python-dotenv": _pkg("BSD-3-Clause"), "python-multipart": _pkg("Apache-2.0"),
    "pyyaml": _pkg("MIT"), "reportlab": _pkg("BSD-3-Clause (ReportLab open-source)"),
    "scipy": _pkg("BSD-3-Clause"), "sqlalchemy": _pkg("MIT"), "starlette": _pkg("BSD-3-Clause"),
    "typing-extensions": _pkg("PSF-2.0"), "typing-inspection": _pkg("MIT"),
    "uvicorn": _pkg("BSD-3-Clause"), "uvloop": _pkg("MIT OR Apache-2.0"),
    "watchfiles": _pkg("MIT"), "websockets": _pkg("BSD-3-Clause"),
}

_FONT_FAMILIES = ("Allison", "ArsenalSC", "CormorantGaramond", "Gloock", "LibreBaskerville",
                  "Lora", "Outfit", "PlayfairDisplay", "WorkSans", "YoungSerif")
FONTS_REGISTER: dict[str, dict] = {
    f: {"kind": "font", "licence": "SIL Open Font License 1.1",
        "commercial_use": "permitted, including embedding in sold PDFs and images",
        "obligations": ("the font may not be sold by itself; redistribute with the OFL text; "
                        "subset (.subset.woff) files keep the original name -- whether a "
                        "Reserved Font Name applies to a subset is " + UNVERIFIED),
        "basis": f"brand/fonts/{f}-OFL.txt committed beside the font", "verified": True}
    for f in _FONT_FAMILIES
}


def _terms(what: str, reversibility: str) -> dict:
    # F-441: how hard it is to leave (read from this codebase) and who maintains it (not read).
    return {"kind": "service", "licence": f"{what} terms of service / API terms",
            "commercial_use": UNVERIFIED, "obligations": UNVERIFIED,
            "basis": "terms not read by this build; owner or counsel review required",
            "verified": False, "reversibility": reversibility, "maintenance": UNVERIFIED}


_IMAGE_SWAP = ("swappable: one row in gateway.images.PROVIDERS; generation is benchmarked "
               "per provider (image_bench) and the incumbent is chosen by measured trial")


SERVICES: dict[str, dict] = {
    "anthropic": _terms("Anthropic API (text and vision models)",
                        "replaceable at the vendor boundary: gateway.providers.register_vendor "
                        "(F-091); prompts and budgets are vendor-neutral"),
    "bfl": _terms("Black Forest Labs API (FLUX image models)", _IMAGE_SWAP),
    "openai": _terms("OpenAI API (image model)", _IMAGE_SWAP),
    "google": _terms("Google Gemini API (image model)", _IMAGE_SWAP),
    "volcengine": _terms("Volcengine API (Seedream image model)", _IMAGE_SWAP),
    "wikimedia_pageviews": _terms("Wikimedia REST API (pageview data)",
                                  "one module (culture.feeds); readings are stored rows, so "
                                  "history survives leaving"),
    "etsy_open_api": _terms("Etsy Open API v3",
                            "not reversible while Etsy is the storefront: the shop is the "
                            "channel, not an interchangeable supplier"),
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_packages() -> list[str]:
    text = (ROOT / "requirements.lock").read_text()
    return sorted({_norm(m.group(1)) for m in re.finditer(r"^([A-Za-z0-9_.\-]+)==", text, re.M)})


def font_families_on_disk() -> list[str]:
    fams = set()
    for p in FONTS.iterdir():
        m = re.match(r"([A-Za-z]+)-", p.name)
        if m and p.suffix in (".woff", ".woff2", ".ttf", ".otf", ".txt"):
            fams.add(m.group(1))
    return sorted(fams)


def called_services() -> list[str]:
    from ..gateway import images, providers

    return sorted(set(providers._VENDORS) | {p.account for p in images.PROVIDERS}
                  | {"wikimedia_pageviews", "etsy_open_api"})


def check() -> list[str]:
    problems = []
    for pkg in locked_packages():
        if pkg not in PACKAGES:
            problems.append(f"package {pkg} is locked with no licence row")
    for fam in font_families_on_disk():
        if fam not in FONTS_REGISTER:
            problems.append(f"font {fam} is bundled with no licence row")
        elif not (FONTS / f"{fam}-OFL.txt").exists():
            problems.append(f"font {fam} has no OFL text beside it")
    for svc in called_services():
        if svc not in SERVICES:
            problems.append(f"service {svc} is called with no terms row")
    return problems


def review_queue() -> list[dict]:
    """Rows whose commercial-use answer is not verified: the owner/counsel reading list."""
    every = {**PACKAGES, **FONTS_REGISTER, **SERVICES}
    return [{"name": k, **v} for k, v in sorted(every.items()) if not v["verified"]]


def register() -> dict:
    return {"packages": PACKAGES, "fonts": FONTS_REGISTER, "services": SERVICES,
            "problems": check(), "review_queue": [r["name"] for r in review_queue()]}
