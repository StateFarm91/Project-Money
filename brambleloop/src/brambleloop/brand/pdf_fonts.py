"""The brand's typefaces, embedded in the customer pattern PDF.

The identity (`brand.identity_system.TYPOGRAPHY`) names three open-licence families --
Cormorant Garamond for display, Lora for reading, Work Sans for labels -- and until now the
document the customer actually keeps was set in Helvetica, which is not one of them and is not
embedded at all: a reader without it substitutes whatever it has, so the page a buyer printed
was not the page the gates measured.

The faces here are static TrueType instances (``fonts/pdf/*.ttf``, OFL-1.1, pinned by
SHA256SUMS). reportlab subsets and embeds each one, and with the canvas's ``invariant`` flag
the subset tags are deterministic, so the document's hash is still a pure function of the
certified CIR.

`missing_glyphs` is the check that keeps the move honest: a TrueType face silently draws an
empty box for a character it does not have, which is a defect no text extractor can see
because the ToUnicode map still says the right letter. Every string the PDF draws is checked
against the face it is drawn in.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts" / "pdf"

# Registered name -> file. The names are what the PDF engine calls a face; the files are the
# brand families, one static weight each.
FACES: dict[str, str] = {
    "BL-Display": "CormorantGaramond-SemiBold.ttf",
    "BL-Display-Bold": "CormorantGaramond-Bold.ttf",
    "BL-Display-Italic": "CormorantGaramond-MediumItalic.ttf",
    "BL-Body": "Lora-Regular.ttf",
    "BL-Body-Italic": "Lora-Italic.ttf",
    "BL-Body-SemiBold": "Lora-SemiBold.ttf",
    "BL-Body-Bold": "Lora-Bold.ttf",
    "BL-UI": "WorkSans-Regular.ttf",
    "BL-UI-Medium": "WorkSans-Medium.ttf",
    "BL-UI-SemiBold": "WorkSans-SemiBold.ttf",
}

LICENCE = "SIL Open Font License 1.1 (see brand/fonts/*-OFL.txt)"


class FontIntegrityError(RuntimeError):
    """A bundled face is missing or its bytes are not the pinned bytes."""


def _pinned() -> dict[str, str]:
    sums = {}
    for line in (FONT_DIR / "SHA256SUMS").read_text().splitlines():
        if line.strip():
            digest, name = line.split()
            sums[name.lstrip("*")] = digest
    return sums


@lru_cache(maxsize=1)
def register() -> tuple[str, ...]:
    """Register every face with reportlab once per process, after checking its bytes.

    A face whose bytes differ from SHA256SUMS is refused rather than embedded: a different
    font file is a different document, and the PDF's hash would no longer mean what the
    release chain says it means.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pinned = _pinned()
    for name, file in FACES.items():
        path = FONT_DIR / file
        if not path.exists():
            raise FontIntegrityError(f"{file} is not bundled in {FONT_DIR}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if pinned.get(file) != digest:
            raise FontIntegrityError(f"{file}: sha256 {digest} is not the pinned "
                                     f"{pinned.get(file)}")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    return tuple(FACES)


@lru_cache(maxsize=None)
def verified_path(file: str) -> Path:
    """The bundled face `file`, after checking its bytes against SHA256SUMS (SECREVIEW L2).

    For callers that load a face by path rather than through reportlab -- the PIL chart
    renderer -- so a swapped file is refused there exactly as `register` refuses it here."""
    path = FONT_DIR / file
    if not path.exists():
        raise FontIntegrityError(f"{file} is not bundled in {FONT_DIR}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if _pinned().get(file) != digest:
        raise FontIntegrityError(f"{file}: sha256 {digest} is not the pinned "
                                 f"{_pinned().get(file)}")
    return path


@lru_cache(maxsize=None)
def _cmap(name: str) -> frozenset[int]:
    from reportlab.pdfbase import pdfmetrics

    register()
    return frozenset(pdfmetrics.getFont(name).face.charToGlyph)


def missing_glyphs(name: str, text: str) -> tuple[str, ...]:
    """Characters in `text` the face `name` cannot draw (whitespace aside)."""
    have = _cmap(name)
    return tuple(sorted({ch for ch in text if not ch.isspace() and ord(ch) not in have}))
