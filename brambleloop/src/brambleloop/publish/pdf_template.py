"""The customer pattern PDF in the owner's master layout (D-OWNER-PDF-TEMPLATE; ENG-PDF-TEMPLATE).

`spec/07_Brambleloop_Master_Pattern_Template.pdf` is the owner's own 14-page brand design and
the master layout of every premium pattern PDF, US and UK. This module reproduces it:

* the same page sequence -- cover; 01 Meet the pattern; 02 Tools + yarn; 03 Sizing & finished
  fit; 04 Construction guide; 05 Stitches & abbreviations; 06 The pattern; 07 Finishing &
  assembly; 08 Gauge, care & helpful notes; 09 Gallery and continued gallery; 10 About
  Brambleloop; 11 Copyright + use;
* the same header (logo, BRAMBLELOOP / CROCHET PATTERNS, the pattern's name, terminology),
  numbered rose kicker and serif title, and footer (BRAMBLELOOP STUDIO / PATTERNS FOR A MORE
  HANDMADE LIFE, page number);
* the template's palette (forest bands, cream ground, sage and cream cards, rose kickers) and
  type (Lato and Noto Serif Display, embedded from `brand/fonts/pdf`, pinned by SHA256SUMS);
* its cards, forest bands, numbered sequences, two-column pattern and gallery grid.

**What it does not reproduce.** The template's bracketed placeholders and its "MASTER LAYOUT
- REQUIRES CERTIFIED PRODUCT DATA" marker are instructions to the factory, never customer
text. Its smallest labels (6.3-8.2 pt) are set at the brand minimum (`bible` min_body_pt,
9 pt) because the customer document has a type floor (`test_deliverable_qa`); and its rose is
darkened to the minimum that clears the brand contrast floor wherever it carries text.

**Content.** Nothing here decides what the pattern says. Every number comes from the compiler,
the twin, the writer's text or a certified release record, through `publish.pdf`'s certified
accessors (imported, never copied). A required fact that cannot be stated BLOCKS the build
with a named reason (`TemplateBlocked`); an optional section with nothing to say is omitted
entirely. No placeholder is ever printed.

**Pictures.** The cover hero and the seven gallery slots are the release's certified campaign
frames -- the same certified bytes as the listing, embedded as `publish.pdf_photos.rendition`
JPEGs so a checker can prove each one from the built file. Without a complete certified gallery
the build refuses with "awaiting gallery" (`GalleryAwaiting`); `proof=True` is the one
exception, an internal text-only proof marked NOT CUSTOMER-READY on every page. The owner's
canonical logo (D-FB-17, D-OWNER-PDF-LOGO) is on the cover, in every page header and in the
thank-you block, and the canonical banner on the About page, through the verified-path
loaders, resampled only.

Deterministic: the same CIR, terminology, release date and gallery bytes give the same bytes.
"""
from __future__ import annotations

import hashlib
import dataclasses
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

from ..brand import canonical_assets as _CA
from ..brand import pdf_fonts
from ..cir.compiler import compile_cir
from ..cir.model import CIR
from ..cir.twin import TwinModel, build_twin
from ..cir.writer import write_pattern
from ..core.resilience import PermanentError
from . import abbreviations, substitution
from . import pdf as P

LAYOUT = "template"
TEMPLATE_PATH = "spec/07_Brambleloop_Master_Pattern_Template.pdf"
TEMPLATE_DECISION = "D-OWNER-PDF-TEMPLATE"
PAGE_W, PAGE_H = LETTER

# ---- the template's type (brand.pdf_fonts registers these) -------------------------------
SERIF = "BL-T-Serif"
SERIF_SEMI = "BL-T-Serif-SemiBold"
SANS = "BL-T-Sans"
SANS_SEMI = "BL-T-Sans-Semibold"
SANS_BOLD = "BL-T-Sans-Bold"
MIN_PT = P.MIN_BODY_PT          # the brand floor; the template's 6.3-8.2 pt labels rise to it

# ---- the template's palette, read from the template's own fills -----------------------------
FOREST = colors.Color(0.184314, 0.243137, 0.2)
CREAM = colors.Color(0.952941, 0.933333, 0.905882)       # cover ground, header/footer bands
PAPER = colors.Color(0.996078, 0.988235, 0.976471)       # page ground
SAGE = colors.Color(0.898039, 0.905882, 0.87451)         # sage cards
SLOT = colors.Color(0.909804, 0.909804, 0.878431)        # image slots
RULE = colors.Color(0.847059, 0.815686, 0.768627)        # hairlines, card strokes
ROSE_RULE = colors.Color(0.65098, 0.45098, 0.447059)     # the rose rule (decoration)
_ROSE = colors.Color(0.65098, 0.45098, 0.447059)
_BROWN = colors.Color(0.498039, 0.407843, 0.317647)
_GREY = colors.Color(0.419608, 0.407843, 0.356863)
# Text colours, darkened only as far as the brand contrast floor requires on their ground.
ROSE = P._legible(_ROSE, PAPER)
ROSE_ON_CREAM = P._legible(_ROSE, CREAM)
BROWN = P._legible(_BROWN, PAPER)
BROWN_ON_CREAM = P._legible(_BROWN, CREAM)
GREY = P._legible(_GREY, CREAM)
INK = FOREST
ON_FOREST = PAPER

# ---- page geometry (points, measured from the template) ------------------------------------
HEADER_H = 94
FOOTER_TOP = 751
CONTENT_X = 47
CONTENT_W = 520
COL_W = 251
COL2_X = 314
CONTENT_BOTTOM = 728            # the lowest a card may reach (template cards end 694-700)

FOOTER_TEXT = "BRAMBLELOOP STUDIO  /  PATTERNS FOR A MORE HANDMADE LIFE"
COVER_TAGLINE = "A THOUGHTFUL PATTERN FOR A MORE HANDMADE LIFE"
TEMPLATE_MARKER = "MASTER LAYOUT • REQUIRES CERTIFIED PRODUCT DATA"
PROOF_MARKER = "TEXT-ONLY PROOF  ·  NOT CUSTOMER-READY  ·  AWAITING CERTIFIED GALLERY"
TEST_DOUBLE_MARKER = "PROOF WITH TEST-DOUBLE IMAGES  ·  NOT CUSTOMER-READY"

# The template's section sequence: (key, number, kicker, title). Keys are the names a checker
# reads (`SECTIONS`), aligned with publish.premium_standard where a counterpart exists
# (`CHECKER_SECTION_ALIASES`).
SECTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("cover", "", "", ""),
    ("meet_the_pattern", "01", "MEET THE PATTERN", "The project at a glance"),
    ("tools_and_yarn", "02", "TOOLS + YARN", "Gather your materials"),
    ("sizing", "03", "MAKE IT YOURS", "Sizing & finished fit"),
    ("construction", "04", "HOW IT IS MADE", "Construction guide"),
    ("abbreviations", "05", "LEARN THE LANGUAGE", "Stitches & abbreviations"),
    ("pattern", "06", "FOLLOW ALONG", "The pattern"),
    ("finishing", "07", "THE LAST STITCH", "Finishing & assembly"),
    ("notes", "08", "MAKE WITH CONFIDENCE", "Gauge, care & helpful notes"),
    ("gallery", "09", "THE FINISHED LOOK", "Gallery & visual references"),
    ("gallery_continued", "09", "CONTINUED GALLERY", "The details that matter"),
    ("about", "10", "THE STUDIO", "A little about Brambleloop"),
    ("copyright", "11", "COPYRIGHT + USE", "The small print, clearly"),
)
SECTION_ORDER = tuple(s[0] for s in SECTIONS)
_SECTION = {s[0]: s for s in SECTIONS}
# The ENG-SALE-PIPELINE checker (publish.pdf_standard, `MAJOR`) names sections after the
# engine layout; these are the same parts of the document in the owner's template.
CHECKER_SECTION_ALIASES: dict[str, str] = {
    "Overview": "The project at a glance",
    "Materials": "Gather your materials",
    "Sizes and fit": "Sizing & finished fit",
    "How it is made": "Construction guide",
    "Abbreviations": "Stitches & abbreviations",
    "Instructions": "The pattern",
    "Finishing": "Finishing & assembly",
    "Gauge, and why it matters here": "Gauge, care & helpful notes",
    "Gallery": "Gallery & visual references",
    "Terms and support": "The small print, clearly",
}

# The template's seven gallery slots, in the order D-OWNER-PDF-TEMPLATE fixes. Slot n is the
# certificate's frame at position n: the campaign's order IS the gallery's order.
GALLERY_SLOTS: tuple[tuple[str, str], ...] = (
    ("hero", "FULL PRODUCT / HERO"),
    ("stitch_detail", "STITCH DETAIL"),
    ("lifestyle", "LIFESTYLE"),
    ("back_alternate", "BACK / ALTERNATE VIEW"),
    ("scale_fit", "SCALE / FIT"),
    ("construction_materials", "CONSTRUCTION / MATERIALS"),
    ("download_facts", "DOWNLOAD FACTS"),
)
GALLERY_FRAMES = len(GALLERY_SLOTS)

# Families (D-OWNER-CORE-FAMILIES and the template's family-aware sections).
GARMENT, AMIGURUMI, BABY, PILLOW, BLANKET, COLOURWORK, HOME = (
    "garment", "amigurumi", "baby", "pillow", "blanket", "colourwork", "home_decor")
FAMILIES = (GARMENT, AMIGURUMI, BABY, PILLOW, BLANKET, COLOURWORK, HOME)
FAMILY_LABEL = {GARMENT: "GARMENT", AMIGURUMI: "AMIGURUMI", BABY: "BABY",
                PILLOW: "PILLOWS + CUSHIONS", BLANKET: "BLANKETS + THROWS",
                COLOURWORK: "COLOURWORK", HOME: "HOME DÉCOR"}
# The fit card's title per family: a garment has ease, a cushion a cover, a blanket a drape.
FIT_TITLE = {GARMENT: "FIT + EASE", AMIGURUMI: "FINISHED SIZE + HANDLING",
             BABY: "FINISHED SIZE + USE", PILLOW: "FINISHED COVER", BLANKET: "FINISHED SIZE + DRAPE",
             COLOURWORK: "FINISHED SIZE + COLOURWORK", HOME: "FINISHED SIZE + USE"}
CHILD_SAFETY_FAMILIES = frozenset({AMIGURUMI, BABY})
CHART_FAMILIES = frozenset({COLOURWORK, BLANKET})

# Craft Yarn Council hook-size standard (craftyarncouncil.com/standards/hooks), mm -> US.
# A published table, quoted; a hook with no US designation prints its millimetres only.
CYC_HOOK_US = {2.25: "B-1", 2.75: "C-2", 3.25: "D-3", 3.5: "E-4", 3.75: "F-5", 4.0: "G-6",
               4.5: "7", 5.0: "H-8", 5.5: "I-9", 6.0: "J-10", 6.5: "K-10½", 8.0: "L-11",
               9.0: "M/N-13", 10.0: "N/P-15", 15.0: "P/Q", 16.0: "Q", 19.0: "S"}
CYC_HOOK_SOURCE = "Craft Yarn Council hook-size standard"
# Craft Yarn Council yarn-weight system (craftyarncouncil.com/standards/yarn-weight-system).
CYC_WEIGHT = {"lace": 0, "fingering": 1, "sock": 1, "super_fine": 1, "sport": 2, "fine": 2,
              "baby": 2, "dk": 3, "light": 3, "light_worsted": 3, "worsted": 4, "aran": 4,
              "medium": 4, "afghan": 4, "chunky": 5, "bulky": 5, "super_bulky": 6, "jumbo": 7}

DOWNLOAD_INCLUDES = (
    "Two terminology-specific pattern PDFs (US and UK) are generated from one certified "
    "source. Each edition includes the exact sections required for the product family. "
    "Charts, measured schematics and safety notes appear only when supported by verified "
    "pattern data.")
STUDIO_BLURB = (
    "Brambleloop Studio is a modern pattern house devoted to thoughtful, accessible crochet "
    "designs. Each guide is built to make the creative process feel clear and beautiful, from "
    "the first loop to the last finishing detail. Our studio identity and this layout remain "
    "consistent across every collection.")
SUPPORT_TEXT = ("Questions about a purchased pattern? Contact Brambleloop Studio through Etsy "
                "Messages, using your original order. Etsy Messages is our only support "
                "channel.")
PLEASE_REMEMBER = (
    "This is a digital crochet pattern, not a finished item. Follow the specified gauge, "
    "instructions and safety notes. Generated examples are not proof that a physical object "
    "exists.")
THANK_YOU = "Thank you for choosing to make something with us."
RENDER_LABEL = "DIGITAL RENDERING  /  NOT A PHOTOGRAPH"
PHOTO_LABEL = "PHOTOGRAPH OF A WORKED SAMPLE"
TEST_DOUBLE_LABEL = "TEST DOUBLE  /  NOT A PRODUCT IMAGE"
GALLERY_DISCLOSURE = (
    "About the pictures: every image in this gallery is one of this listing's certified "
    "images. A generated image is a digital rendering of the finished design, checked against "
    "this pattern's certified data, and is labelled as one; it is not a photograph of a "
    "worked sample.")


class TemplateBlocked(PermanentError, ValueError):
    """A required fact is missing, so no customer document is produced. `reason` names it."""

    def __init__(self, reason: str, *, slug: str = "", section: str = ""):
        self.reason = reason
        self.slug = slug
        self.section = section
        where = f"{slug}: " if slug else ""
        sect = f" [{section}]" if section else ""
        super().__init__(f"template PDF blocked{sect}: {where}{reason}")


class GalleryAwaiting(TemplateBlocked):
    """No complete certified gallery: the release reports "awaiting gallery"."""


@dataclass
class TemplateDocument:
    """A rendered template PDF and what it asserts, for the checks to compare."""

    pdf_bytes: bytes
    pages: int
    terminology: str
    family: str
    status: str                       # customer_ready | proof_text_only | proof_test_double
    sections: list[tuple[int, str]] = field(default_factory=list)   # (page, section key)
    gallery: list[dict] = field(default_factory=list)  # slot, position, role, sha256s, page
    logo_pages: list[int] = field(default_factory=list)
    logo_sha256: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    prose: str = ""
    figures: list[dict] = field(default_factory=list)
    rows: int = 0                     # row/round instructions printed (each with its count)
    layout: str = LAYOUT
    # The facts publish.pdf.PatternDocument carries, so the release chain reads either layout.
    claims: list[str] = field(default_factory=list)
    finished_size_cm: tuple[float, float] | None = None
    yardage_by_color: dict = field(default_factory=dict)
    yardage_tolerance: float = 0.0
    calibrated: bool = False
    difficulty: str = ""
    released_on: date | None = None

    def size_label(self) -> str:
        if not self.finished_size_cm:
            return "size not stated"
        w, h = self.finished_size_cm
        return f"{w:.0f} x {h:.0f} cm"

    @property
    def customer_ready(self) -> bool:
        return self.status == "customer_ready" and not self.problems


# ---- the canonical owner artwork, through the verified-path loaders --------------------------

HEADER_LOGO_PX = 300     # ~66 pt wide: over 300 dpi
THANKS_LOGO_PX = 320
BANNER_PX = 1200         # 520 pt wide: about 166 dpi


@lru_cache(maxsize=None)
def _owner_art(role: str, px: int):
    """The owner's canonical artwork resampled (LANCZOS) to `px` wide, as an RGB image.

    `canonical_assets.display_bytes` re-hashes the source against SHA256SUMS before reading
    it (D-FB-17: used exactly as supplied, resampled only to fit). Embedded losslessly
    (Flate), never as JPEG: brand artwork is not a photograph, and the sale-pipeline checker
    treats every DCT image as one that must be a certified frame."""
    from PIL import Image

    img = Image.open(io.BytesIO(_CA.display_bytes(role, px, fmt="PNG"))).convert("RGB")
    img.load()
    return img


def _art_sha(role: str, px: int) -> str:
    """sha256 of the decoded image stream the PDF carries for this rendition."""
    return hashlib.sha256(_owner_art(role, px).tobytes()).hexdigest()


def _logo_cover():
    """The cover's logo: `publish.pdf._cover_logo`, the one canonical cover loader."""
    return P._cover_logo()


def logo_fingerprints() -> dict:
    """The sha256 of every logo rendition this layout embeds, by use."""
    return {"header": _art_sha(_CA.HERO_LOGO, HEADER_LOGO_PX),
            "thanks": _art_sha(_CA.HERO_LOGO, THANKS_LOGO_PX),
            "cover": hashlib.sha256(_logo_cover().convert("RGB").tobytes()).hexdigest(),
            "cover_px": list(_logo_cover().size)}


# ---- family ----------------------------------------------------------------------------------

def template_family(cir: CIR, childrens: tuple[str, str] | None = None) -> str:
    """The product family whose section variant this document takes.

    From certified facts only: a graded release is a garment; the catalogue's children's
    assignment makes a baby product (an amigurumi toy when the assignment says so); a pillow,
    a blanket or colourwork is read from the CIR's own name and its measured colour grid."""
    if cir.grading is not None:
        return GARMENT
    words = f"{cir.slug} {cir.title}".lower()
    if (childrens and childrens[0] == "amigurumi_toy") or any(
            w in words for w in ("amigurumi", "plush", "stuffed")):
        return AMIGURUMI
    if childrens:
        return BABY
    if any(w in words for w in ("pillow", "cushion")):
        return PILLOW
    if _is_colourwork(cir):
        return COLOURWORK
    if any(w in words for w in ("blanket", "throw", "afghan", "graphghan")):
        return BLANKET
    return HOME


def _is_colourwork(cir: CIR) -> bool:
    from ..products import launch0 as L

    try:
        twin = build_twin(cir, compile_cir(cir))
        motif = L.colourwork_motif(twin.color_grid or [])
    except Exception:  # noqa: BLE001 - an unmeasurable grid is not colourwork
        return False
    return (motif["two_colour_rows"] >= L.COLOURWORK_MIN_ROWS
            and motif["two_colour_row_share"] >= L.COLOURWORK_MIN_ROW_SHARE)


# ---- small text helpers ----------------------------------------------------------------------

def hook_label(mm: float | None) -> str:
    if not mm:
        return ""
    us = CYC_HOOK_US.get(round(float(mm), 2))
    return f"US {us} / {mm:g} mm" if us else f"{mm:g} mm (no US letter size)"


AMIGURUMI_HOOK_STEP_MM = 0.5   # how far below the stated hook an amigurumi maker may go


def hook_range(mm: float) -> tuple[float, float]:
    """The amigurumi hook range: the stated hook and the standard sizes up to 0.5 mm below
    it. Stuffed fabric is worked tighter than the ball band's hook so the fibrefill cannot
    show (TEARDOWN_MADELINEMAECO_CAPYBARA D1: "stitches too tight with the stated hook" is a
    gauge complaint a stated range prevents). Never above the stated hook: the gauge is
    measured at it."""
    sizes = sorted(CYC_HOOK_US)
    lower = [s for s in sizes if mm - AMIGURUMI_HOOK_STEP_MM - 1e-9 <= s < mm]
    return (min(lower) if lower else float(mm), float(mm))


def _pattern_yardage(cir: CIR, result, twin: TwinModel) -> dict[str, float]:
    """Yarn per colour for the whole pattern: every component, each times its `make`.

    `cir.twin.build_twin` models one component (the first unless told otherwise), so its
    yardage is that piece's only; a pullover's body is 584 m of an 808 m pattern. The
    buyer's quantity is the sum over every piece, at the twin's own calibration."""
    if len(cir.components) == 1:
        return dict(twin.yarn_metres_by_color)
    first = build_twin(cir, result, component=twin.component).yarn_metres_by_color
    base, given = sum(first.values()), sum(twin.yarn_metres_by_color.values())
    scale = (given / base) if base else 1.0
    total: dict[str, float] = {}
    for comp in cir.components:
        part = build_twin(cir, result, component=comp.name).yarn_metres_by_color
        for colour, metres in part.items():
            total[colour] = total.get(colour, 0.0) + metres * scale
    return {k: round(v, 1) for k, v in total.items()}


PROFILE_PX = 420


def _round_rows(comp) -> list:
    return [r for r in comp.rows if r.declared_count]


def stuff_round(comp) -> int | None:
    """The round whose own note says to stuff (the CIR's words, not an inference)."""
    return next((r.index for r in comp.rows if r.note and "stuff" in r.note.lower()), None)


def profile_scale(cir: CIR) -> float:
    """Pixels per cm, one scale for every piece of the pattern so they compare truly."""
    g = cir.gauge
    st, rw = 10.0 / g.stitches_per_10cm, 10.0 / g.rows_per_10cm
    w = max(max(r.declared_count for r in _round_rows(c)) * st / math.pi
            for c in cir.components if _round_rows(c))
    h = max(len(_round_rows(c)) * rw for c in cir.components if _round_rows(c))
    return 0.88 * PROFILE_PX / max(w, h)


def component_profile(cir: CIR, comp, *, highlight: tuple[int, int] | None = None):
    """A side profile of a piece worked in rounds, drawn from its stitch counts.

    Each band is one round, `rows_per_10cm` tall, as wide as the round's diameter at gauge
    (stitches x stitch width / pi), in the round's yarn colour, on one scale shared by every
    piece of the pattern. `highlight` outlines rounds a..b in rose (a placement). It is a
    diagram of the stitch data; it is never presented as a photograph."""
    from PIL import Image, ImageDraw

    g = cir.gauge
    st, rw = 10.0 / g.stitches_per_10cm, 10.0 / g.rows_per_10cm
    px = profile_scale(cir)
    rows = _round_rows(comp)
    img = Image.new("RGB", (PROFILE_PX, PROFILE_PX), (243, 238, 231))
    d = ImageDraw.Draw(img)
    band = rw * px
    top = (PROFILE_PX - band * len(rows)) / 2
    cx = PROFILE_PX / 2
    for i, r in enumerate(rows):
        half = r.declared_count * st / math.pi * px / 2
        hexv = (cir.colors or {}).get(r.color or "", "#B9AE9C")
        fill = tuple(int(hexv.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
        y0, y1 = top + i * band, top + (i + 1) * band
        d.rectangle([cx - half, y0, cx + half, y1], fill=fill, outline=(47, 62, 51), width=1)
    if highlight is not None:
        a, b = highlight
        sel = [i for i, r in enumerate(rows) if a <= r.index <= b]
        if sel:
            half = max(rows[i].declared_count for i in sel) * st / math.pi * px / 2
            d.rectangle([cx - half - 6, top + sel[0] * band - 3, cx + half + 6,
                         top + (sel[-1] + 1) * band + 3], outline=(142, 90, 89), width=5)
    stuffed = stuff_round(comp)
    if stuffed is not None:
        i = next(k for k, r in enumerate(rows) if r.index == stuffed)
        y = top + (i + 0.5) * band
        d.polygon([(18, y - 9), (34, y), (18, y + 9)], fill=(142, 90, 89))
    return img


def cyc_label(cir: CIR) -> str:
    weights = sorted({(m.yarn_weight or "").lower() for m in cir.materials if m.yarn_weight})
    if cir.gauge and cir.gauge.yarn_weight:
        weights = sorted(set(weights) | {cir.gauge.yarn_weight.lower()})
    nums = sorted({CYC_WEIGHT[w] for w in weights if w in CYC_WEIGHT})
    label = P._yarn_weight_label(cir)
    if len(nums) == 1:
        return f"{label}, CYC {nums[0]}"
    return label


def _one_line(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return m.group(1) if m else text.strip()


def _caps(s: str) -> str:
    return s.upper()


# ---- the canvas ------------------------------------------------------------------------------

class _T:
    """One template document being drawn. Coordinates are measured from the page top, as the
    template's geometry was measured, and converted on the way to reportlab."""

    def __init__(self, cir: CIR, terminology: str, *, marker: str, header_right: str,
                 designer: str):
        pdf_fonts.register()
        self.buf = io.BytesIO()
        self.c = rl_canvas.Canvas(self.buf, pagesize=LETTER, invariant=1,
                                  initialFontName=SANS, initialFontSize=10)
        self.c.setTitle(f"{cir.title} - {designer}")
        self.c.setAuthor(designer)
        self.c.setSubject(f"Crochet pattern, {terminology.upper()} terms, version {cir.version}")
        self.c.setCreator("Brambleloop Studio pattern compiler (master template)")
        self.c.setCatalogEntry("Lang", "en-GB")
        self.terminology = terminology.upper()
        self.marker = marker
        self.header_right = header_right
        self.pages = 0
        self.top = 0.0
        self.prose: list[str] = []
        self.figures: list[dict] = []
        self.problems: list[str] = []
        self.sections: list[tuple[int, str]] = []
        self.logo_pages: list[int] = []
        self.section_key = ""
        self.total_pages = 0
        self.release_id = f"{cir.slug}@{cir.version}"
        self._open = False

    # -- text ---------------------------------------------------------------------------
    def y(self, top: float) -> float:
        return PAGE_H - top

    def text(self, x: float, baseline_top: float, s: str, font: str = SANS,
             size: float = 10, color=INK, *, align: str = "left", track: float = 0.0,
             record: bool = True) -> float:
        if not s:
            return 0.0
        if size < MIN_PT - 1e-6:
            self.problems.append(f"PDF_TYPE_BELOW_BRAND_MINIMUM: {s[:40]!r} set at {size}pt")
        missing = pdf_fonts.missing_glyphs(font, s)
        if missing:
            self.problems.append(f"PDF_GLYPH_MISSING: {font} has no glyph for {list(missing)} "
                                 f"in {s[:60]!r}")
        w = self.width(s, font, size, track)
        if align == "right":
            x -= w
        elif align == "centre":
            x -= w / 2
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        if track:
            self.c.drawString(x, self.y(baseline_top), s, charSpace=track)
        else:
            self.c.drawString(x, self.y(baseline_top), s)
        if record:
            self.prose.append(s)
        return w

    @staticmethod
    def width(s: str, font: str, size: float, track: float = 0.0) -> float:
        return stringWidth(s, font, size) + track * max(0, len(s) - 1)

    def wrap(self, text: str, font: str, size: float, width: float) -> list[str]:
        return P._wrap(self.c, text, font, size, width)

    def para(self, x: float, top: float, width: float, text: str, *, font: str = SANS,
             size: float = 10, color=INK, leading: float | None = None) -> float:
        """Set a wrapped paragraph whose first line's cap-top is at `top`; returns the top
        below its last line."""
        leading = leading or size * 1.5
        y = top + size * 0.78
        for line in self.wrap(text, font, size, width):
            if line:
                self.text(x, y, line, font, size, color, record=False)
            y += leading
        self.prose.append(text)
        return top + len(self.wrap(text, font, size, width)) * leading

    def para_h(self, text: str, width: float, *, font: str = SANS, size: float = 10,
               leading: float | None = None) -> float:
        leading = leading or size * 1.5
        return len(self.wrap(text, font, size, width)) * leading

    def label(self, x: float, top: float, s: str, color=BROWN, *, size: float = MIN_PT,
              font: str = SANS_BOLD, track: float = 1.6) -> None:
        self.text(x, top + size * 0.78, _caps(s), font, size, color, track=track)

    # -- shapes -------------------------------------------------------------------------
    def card(self, x: float, top: float, w: float, h: float, *, fill=CREAM, stroke=None,
             radius: float = 9.0, lw: float = 0.7) -> None:
        c = self.c
        c.saveState()
        c.setFillColor(fill)
        if stroke is not None:
            c.setStrokeColor(stroke)
            c.setLineWidth(lw)
        c.roundRect(x, self.y(top + h), w, h, radius, fill=1, stroke=1 if stroke else 0)
        c.restoreState()

    def rule(self, x0: float, x1: float, top: float, color=RULE, lw: float = 0.7) -> None:
        self.c.saveState()
        self.c.setStrokeColor(color)
        self.c.setLineWidth(lw)
        self.c.line(x0, self.y(top), x1, self.y(top))
        self.c.restoreState()

    def image(self, src, x: float, top: float, w: float, h: float, *, fit: str = "contain",
              radius: float = 0.0, figure: dict | None = None) -> tuple[float, float]:
        """Place an image (PIL image or encoded bytes) in the box. `cover` fills and clips;
        `contain` fits whole. Encoded JPEG bytes pass through unchanged (DCTDecode)."""
        if isinstance(src, (bytes, bytearray)):
            reader = ImageReader(io.BytesIO(bytes(src)))
        else:
            reader = ImageReader(src)
        iw, ih = reader.getSize()
        scale = (max if fit == "cover" else min)(w / iw, h / ih)
        dw, dh = iw * scale, ih * scale
        dx, dtop = x + (w - dw) / 2, top + (h - dh) / 2
        c = self.c
        c.saveState()
        if fit == "cover" or radius:
            p = c.beginPath()
            if radius:
                p.roundRect(x, self.y(top + h), w, h, radius)
            else:
                p.rect(x, self.y(top + h), w, h)
            c.clipPath(p, stroke=0, fill=0)
        c.drawImage(reader, dx, self.y(dtop + dh), width=dw, height=dh, mask="auto")
        c.restoreState()
        if figure is not None:
            self.figures.append(dict(figure, page=self.pages))
        return dw, dh

    # -- pages --------------------------------------------------------------------------
    def _end_page(self) -> None:
        if self._open:
            self.c.showPage()
            self._open = False

    def cover_page(self) -> None:
        self._end_page()
        self.pages += 1
        self._open = True
        self.sections.append((self.pages, "cover"))
        self.section_key = "cover"
        c = self.c
        c.setFillColor(CREAM)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(FOREST)
        c.rect(0, self.y(11), PAGE_W, 11, fill=1, stroke=0)
        self._marker()

    def section_page(self, key: str, *, continued: bool = False) -> None:
        """A body page: ground, header band with the logo, the numbered kicker and title,
        the footer band. `continued` repeats the title, as the template's page 8 does."""
        self._end_page()
        self.pages += 1
        self._open = True
        self.section_key = key
        self.sections.append((self.pages, key))
        c = self.c
        c.setFillColor(PAPER)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(CREAM)
        c.rect(0, self.y(HEADER_H), PAGE_W, HEADER_H, fill=1, stroke=0)
        c.rect(0, 0, PAGE_W, PAGE_H - FOOTER_TOP, fill=1, stroke=0)
        # header: the canonical logo, resampled only, then the wordmark lines
        self.image(_owner_art(_CA.HERO_LOGO, HEADER_LOGO_PX), 40, 22, 66, 60,
                   figure={"kind": "owner_logo", "use": "header",
                           "source": "brand/owner_source/brambleloop_owner_logo_canonical.png",
                           "sha256": _art_sha(_CA.HERO_LOGO, HEADER_LOGO_PX)})
        self.logo_pages.append(self.pages)
        self.text(112, 43, "BRAMBLELOOP", SANS_BOLD, 10.3, INK, track=3.0)
        self.text(113, 60, "CROCHET PATTERNS", SANS_BOLD, MIN_PT, BROWN_ON_CREAM, track=1.8)
        right = self.header_right
        size = MIN_PT
        while self.width(right, SANS_SEMI, size, 0.4) > 250 and len(right) > 12:
            right = right[:-2].rstrip() + "…" if not right.endswith("…") else right[:-3] + "…"
        self.text(567, 45, right, SANS_SEMI, size, INK, align="right", track=0.4)
        self.text(567, 60, f"{self.terminology} TERMINOLOGY", SANS_SEMI, size, BROWN_ON_CREAM,
                  align="right", track=0.6)
        self.rule(45, 567, 91, RULE, 0.8)
        # footer
        self.text(47, 771, FOOTER_TEXT, SANS, MIN_PT, INK, track=0.5)
        self.text(567, 774, f"{self.pages:02d}", SANS_SEMI, MIN_PT, INK, align="right")
        self._folio()
        self._marker()
        # kicker and title
        _k, num, kicker, title = _SECTION[key]
        self.text(47, 115, f"{num}  /  {kicker}", SANS_BOLD, MIN_PT, ROSE, track=1.8)
        self.text(45, 160, title, SERIF, 30, INK)
        self.rule(47, 567, 179, RULE, 0.7)
        self.top = 200

    def _folio(self) -> None:
        """The release id and "page N of M" (a buyer can see a truncated download), in the
        footer band between the template's footer line and its page number."""
        total = self.total_pages or self.pages
        self.text(47, 787, f"{self.release_id}  ·  page {self.pages} of {total}", SANS,
                  MIN_PT, GREY)

    def _marker(self) -> None:
        if self.marker:
            self.text(PAGE_W / 2, 746 if self.section_key != "cover" else 775, self.marker,
                      SANS_BOLD, MIN_PT, P.ACCENT, align="centre", track=0.6)

    def need(self, h: float, key: str | None = None) -> bool:
        if self.top + h > CONTENT_BOTTOM:
            self.section_page(key or self.section_key, continued=True)
            return True
        return False

    def finish(self) -> bytes:
        self._end_page()
        self.c.save()
        return self.buf.getvalue()


# ---- gallery ---------------------------------------------------------------------------------

def plan_gallery(frames: list[dict] | None) -> dict:
    """The seven slots from certified frames, or what is missing. Each frame:
    {"position", "role", "sha256", "data": bytes, "kind"?, "test_double"?}.

    A frame whose bytes do not hash to its certified sha256 is refused. Slot n takes the
    frame at certificate position n."""
    from . import pdf_photos as PP

    problems: list[str] = []
    by_pos: dict[int, dict] = {}
    for f in frames or []:
        data = f.get("data")
        pos = int(f.get("position") or 0)
        if not isinstance(data, (bytes, bytearray)) or \
                hashlib.sha256(bytes(data)).hexdigest() != f.get("sha256"):
            problems.append(f"frame {pos} ({f.get('role')}): bytes do not match the certified "
                            f"sha256")
            continue
        by_pos.setdefault(pos, f)
    slots = []
    for n, (slot, label) in enumerate(GALLERY_SLOTS, start=1):
        f = by_pos.get(n)
        if f is None:
            problems.append(f"no certified frame at position {n} for the {slot} slot")
            continue
        jpeg = PP.rendition(bytes(f["data"]))
        kind = str(f.get("kind") or "generated")
        slots.append({"slot": slot, "label": label, "position": n,
                      "role": str(f.get("role") or ""), "frame_sha256": f["sha256"],
                      "rendition_sha256": hashlib.sha256(jpeg).hexdigest(), "jpeg": jpeg,
                      "kind": kind, "test_double": bool(f.get("test_double")),
                      "chip": (TEST_DOUBLE_LABEL if f.get("test_double") else
                               PHOTO_LABEL if kind == "photo" else RENDER_LABEL)})
    return {"slots": slots, "problems": problems,
            "complete": len(slots) == GALLERY_FRAMES and not problems}


def gallery_from_release(db, slug: str, version: str, *, release: str = "",
                         store_root=None) -> list[dict]:
    """The release's valid listing-set certificate frames with their certified bytes (the
    same bytes the listing uploads). Raises GalleryAwaiting when there is no complete
    certified gallery."""
    from ..runtime import etsy_ops

    cert = etsy_ops.certified_frames(db, slug, version, release=release)
    if cert["problems"] or len(cert["frames"]) < GALLERY_FRAMES:
        raise GalleryAwaiting("awaiting gallery: " + "; ".join(
            cert["problems"] or [f"{len(cert['frames'])} of {GALLERY_FRAMES} frames"]),
            slug=slug, section="gallery")
    images = etsy_ops.certified_images(db, slug, version, release=release,
                                       store_root=store_root)
    if images.get("problems"):
        raise GalleryAwaiting("awaiting gallery: " + "; ".join(images["problems"]), slug=slug,
                              section="gallery")
    out = []
    for f, entry in zip(cert["frames"], images.get("images") or []):
        _name, data = entry
        out.append({"position": int(f.get("position") or 0), "role": f.get("role") or "",
                    "sha256": f.get("sha256") or hashlib.sha256(data).hexdigest(),
                    "data": data, "kind": f.get("kind") or "generated"})
    return out


# ---- the document ----------------------------------------------------------------------------

def build_template_pdf(cir: CIR, *, terminology: str = "US", twin: TwinModel | None = None,
                       released_on: date | None = None, gallery: list[dict] | None = None,
                       proof: bool = False, designer: str = P.COPYRIGHT_HOLDER,
                       childrens: tuple[str, str] | None = None,
                       family: str | None = None) -> TemplateDocument:
    """Render `cir` in the owner's master template.

    Refuses (TemplateBlocked) whatever `publish.pdf.build_pattern_pdf` refuses -- a CIR that
    does not compile, a terminology it cannot name truthfully, an undecided or refused
    children's title, an incomplete children's statement set -- and also any required fact
    the template needs and the certified data cannot state. Without a complete certified
    gallery it refuses with GalleryAwaiting unless `proof=True`, which produces an internal
    text-only proof marked NOT CUSTOMER-READY on every page."""
    terminology = terminology.upper()
    if terminology not in P.TERMINOLOGIES:
        raise TemplateBlocked(f"{terminology!r} is not a published terminology", slug=cir.slug)
    result = compile_cir(cir)
    if not result.ok:
        raise TemplateBlocked(f"the CIR fails compilation: {[str(f) for f in result.errors][:3]}",
                              slug=cir.slug)
    twin = twin or build_twin(cir, result)
    released_on = released_on or date.today()
    stalled = sorted(set(abbreviations.unlocalised(terminology)) & set(twin.stitch_types_used))
    if stalled:
        raise TemplateBlocked(f"{terminology} terms cannot name {stalled} truthfully",
                              slug=cir.slug)
    childrens = childrens if childrens is not None else P.childrens_assignment(cir)
    P._refuse_an_undecided_childrens_title(cir, childrens)
    if childrens is not None:
        P._refuse_what_the_childrens_assessment_refuses(cir, childrens)
    fam = family or template_family(cir, childrens)
    if fam not in FAMILIES:
        raise TemplateBlocked(f"unknown family {fam!r}", slug=cir.slug)
    if fam in CHILD_SAFETY_FAMILIES and childrens is None:
        raise TemplateBlocked(
            f"a {fam} pattern needs the child-safety gate's statements and this release has "
            f"no children's assignment to render them from", slug=cir.slug, section="notes")

    plan = plan_gallery(gallery)
    test_double = any(s["test_double"] for s in plan["slots"])
    if not plan["complete"]:
        if not proof:
            raise GalleryAwaiting("awaiting gallery: " + "; ".join(plan["problems"][:3]),
                                  slug=cir.slug, section="gallery")
        status, marker = "proof_text_only", PROOF_MARKER
        plan = {"slots": [], "problems": plan["problems"], "complete": False}
    elif test_double:
        status, marker = "proof_test_double", TEST_DOUBLE_MARKER
    else:
        status, marker = "customer_ready", ""

    text = write_pattern(cir, result, terminology=terminology,
                         width_cm=twin.width_cm, height_cm=twin.height_cm)
    # the buyer's yarn is every piece's, not the twin's one component (_pattern_yardage)
    twin = dataclasses.replace(twin, yarn_metres_by_color=_pattern_yardage(cir, result, twin))
    facts = _Facts(cir, result, twin, text, terminology, released_on, fam, childrens)
    facts.has_gallery = bool(plan["slots"])
    slots = plan["slots"]
    total = 0
    for _ in range(4):
        # Laid out until the length the licence page states is the length it has.
        t = _T(cir, terminology, marker=marker, header_right=cir.title.upper(),
               designer=designer)
        t.total_pages = total
        _cover(t, facts, slots)
        _meet(t, facts)
        _tools(t, facts)
        _sizing(t, facts)
        _construction(t, facts)
        _abbreviations(t, facts)
        rows = _pattern(t, facts, slots)
        _finishing(t, facts)
        _notes(t, facts)
        gallery_out = _gallery(t, facts, slots)
        _about(t, facts)
        _copyright(t, facts, designer)
        if t.pages == total:
            break
        total = t.pages
    else:  # pragma: no cover
        raise TemplateBlocked("the page count does not settle", slug=cir.slug)

    problems = list(t.problems)
    missing = abbreviations.undefined_tokens("\n".join(t.prose), terminology,
                                             defined={e.token for e in facts.key})
    if missing:
        problems.append(f"PDF_ABBREVIATION_UNDEFINED: {sorted(set(missing))}")
    pdf_bytes = t.finish()
    if childrens is not None:
        try:
            P._refuse_an_incomplete_childrens_document(cir, twin, pdf_bytes, childrens,
                                                       terminology)
        except ValueError as e:
            raise TemplateBlocked(str(e), slug=cir.slug, section="notes") from e
    # D-OWNER-PDF-STANDARD, audited on the bytes exactly as the engine does: a customer
    # document that fails it is refused; a proof records the failures in `problems`.
    standard = P._std.audit(pdf_bytes, cir, terminology=terminology, result=result,
                            childrens=childrens is not None)
    if status == "customer_ready":
        P._std.refuse_if_incomplete(standard)
    problems += [f"PREMIUM_STANDARD {k}: {v[0]}" for k, v in sorted(standard.failures.items())]
    return TemplateDocument(
        pdf_bytes=pdf_bytes, pages=t.pages, terminology=terminology, family=fam,
        status=status, sections=list(t.sections), gallery=gallery_out,
        logo_pages=sorted(set(t.logo_pages)), logo_sha256=logo_fingerprints(),
        problems=sorted(set(problems)), prose="\n".join(t.prose), figures=list(t.figures),
        rows=rows,
        claims=[f"{facts.size_text()} at the stated gauge"],
        finished_size_cm=((twin.width_cm, twin.height_cm)
                          if twin.width_cm and twin.height_cm else None),
        yardage_by_color=dict(twin.yarn_metres_by_color),
        yardage_tolerance=twin.yardage_tolerance, calibrated=twin.calibrated,
        difficulty=facts.difficulty, released_on=released_on)


class _Facts:
    """Everything the pages state, computed once from certified data. A required fact that
    cannot be computed raises TemplateBlocked naming it."""

    def __init__(self, cir, result, twin, text, terminology, released_on, family, childrens):
        self.cir, self.result, self.twin, self.text = cir, result, twin, text
        self.terminology, self.released_on = terminology, released_on
        self.family, self.childrens = family, childrens
        self.parsed = P._parse_writer(text)
        self.key = abbreviations.stitch_key(text, terminology)
        self.difficulty = P._difficulty(cir, twin)
        if not cir.gauge or not cir.gauge.hook_mm:
            self.block("the certified CIR states no gauge and hook", "tools_and_yarn")
        if not cir.materials:
            self.block("the certified CIR names no yarn", "tools_and_yarn")
        if not twin.yarn_metres_by_color:
            self.block("the twin computes no yarn quantity", "tools_and_yarn")
        self.circumferences = self._circumferences() if family == AMIGURUMI else []
        if not twin.width_cm and not self.circumferences:
            self.block("the twin computes no finished size", "sizing")
        self.make_total = sum(c.make for c in cir.components)
        self.piece = cir.components[0].name.replace("_", " ")
        self.colours = {n: colors.HexColor(v) for n, v in (cir.colors or {}).items() if v}
        self._memo: dict = {}
        self.has_gallery = False

    def memo(self, key: str, fn):
        """Computed once per document, reused by every layout pass."""
        if key not in self._memo:
            self._memo[key] = fn()
        return self._memo[key]

    def block(self, reason: str, section: str):
        raise TemplateBlocked(reason, slug=self.cir.slug, section=section)

    def _circumferences(self) -> list[tuple[str, float]]:
        """(piece, cm around its widest round) for each stuffed piece of a toy: the size the
        twin can state for a closed shaped piece (its own size_refusal says so). Its other
        dimensions come from stuffing and tension, which gauge cannot predict."""
        out = []
        for comp in self.cir.components:
            if comp.construction not in ("joined_rounds", "spiral_rounds"):
                continue
            tw = build_twin(self.cir, self.result, component=comp.name)
            if tw.circumference_cm:
                out.append((comp.name.replace("_", " "), tw.circumference_cm))
        return out

    def pieces_phrase(self) -> str:
        """'4 coasters' for one piece made four times; '1 body, 2 sleeves, 1 neckband' for a
        pattern of several pieces (never '4 bodys')."""
        def name(c):
            n = c.name.replace("_", " ")
            return f"{c.make} {n}" + ("s" if c.make > 1 and not n.endswith("s") else "")
        return ", ".join(name(c) for c in self.cir.components)

    def size_text(self) -> str:
        """The finished size as the certified data can state it."""
        if self.twin.width_cm or not self.circumferences:
            return P._short_size(self.twin, self.cir)
        return ", ".join(f"{n} {c:.1f} cm around" for n, c in self.circumferences)

    # -- statements ----------------------------------------------------------------------
    def sizes_line(self) -> str:
        g = self.cir.grading
        if g is not None:
            names = g.size_names
            return f"{len(names)} sizes, {names[0]} to {names[-1]} (this edition: size {g.size})"
        return self.size_text()

    def overview(self) -> list[str]:
        """publish.pdf's overview, without its closing sentence about the engine layout's
        contents; this edition states its own (`includes_line`)."""
        paras = P.overview_paragraphs(self.cir, self.result, self.twin, self.text,
                                      self.terminology)
        body = [p for p in paras if not p.startswith("It is written in ")]
        return body[:2] + [self.includes_line()]

    def chart_art(self) -> dict:
        from .charts import render_legend

        def build():
            art = P._chart_art(self.cir, self.twin)
            return dict(art, legend=render_legend(
                self.cir, self.twin, terminology=self.terminology, marks=art.get("marks"),
                colours=art.get("charted_colours"), lettered=bool(art.get("cues"))))

        return self.memo("chart", build)

    def chart_included(self) -> bool:
        # colourwork (more than one colour in the fabric) always carries its chart and key
        # (D-OWNER-PDF-STANDARD colourwork_chart), whatever its family
        return (self.family in CHART_FAMILIES or P._std.colourwork(self.twin)
                or not self.chart_art().get("tiles"))

    def includes_line(self) -> str:
        from .construction_diagrams import stages as _stages

        unit = "round" if "round" in self.cir.components[0].construction else "row"
        parts = ["a schematic"] + (["a chart"] if self.chart_included() else [])
        if self.memo("stages", lambda: _stages(self.cir)) or _tricky_rows(self, []):
            parts.append("inline diagrams at the key steps")
        if self.has_gallery:
            parts.append("the certified gallery")
        listed = ", ".join(parts[:-1]) + " and " + parts[-1]
        return (f"It is written in {self.terminology} crochet terms. Every {unit} is written "
                f"out with its stitch count, and this edition includes {listed}.")

    def how_it_comes_together(self) -> str:
        lines = P.construction_overview(self.cir)
        if lines:
            return " ".join(lines)
        twin, cir = self.twin, self.cir
        rows = P._rows_by_index(twin)
        comp = cir.components[0]
        unit = "round" if "round" in comp.construction else "row"
        if not rows:
            self.block("the twin has no rows to describe the construction from", "meet")
        first, last = min(rows), max(rows)
        how = {"joined_rounds": "in joined rounds, without turning",
               "spiral_rounds": "in continuous spiral rounds",
               "flat_rows": "flat, in rows, turning at the end of each row"}.get(
            comp.construction, comp.construction.replace("_", " "))
        each = "Each" if self.make_total > 1 else "The"
        s = (f"{each} {self.piece} is one piece, worked {how}: {unit}s {first} to {last}, "
             f"ending with {len(rows[last])} stitches.")
        base, wall = P._rings(twin)
        if base and wall:
            s += (f" {unit.capitalize()}s {base[0].index} to {base[-1].index} grow a flat base "
                  f"of {len(rows[base[-1].index])} stitches; {unit}s {wall[0].index} to "
                  f"{wall[-1].index} keep that count and rise into the wall.")
        if len(self.colours) > 1:
            s += f" It is worked in {len(self.colours)} colours, changed where the instructions say."
        s += " There are no seams to sew." if not cir.assembly else ""
        return s

    def yarn_amount(self, metres: float) -> str:
        """The range in the edition's unit (yd in US, m in UK) with 100 g balls
        (publish.pdf._amount, the premium standard's one formatter)."""
        lo, hi = P._metres(metres, self.twin.yardage_tolerance)
        return P._amount(lo, hi, self.terminology, P._std.cyc_weight(self.cir))

    def total_yarn(self) -> str:
        return self.yarn_amount(sum(self.twin.yarn_metres_by_color.values()))

    def gauge_line(self) -> str:
        g = self.cir.gauge
        return (f"{g.stitches_per_10cm:g} sts and {g.rows_per_10cm:g} rows over 10 x 10 cm "
                f"(4 x 4 in) in {P._gauge_stitch(self.cir, self.terminology)}, with a "
                f"{hook_label(g.hook_mm)} hook.")

    def calibration(self) -> str:
        return ("Every measurement here is computed from the stated gauge and this pattern's "
                "stitches; it has not yet been measured on a worked sample, so treat it as an "
                "estimate." if not self.twin.calibrated else
                "These measurements were calibrated against a physically worked sample.")

    def tolerance_note(self) -> str:
        tol = self.twin.yardage_tolerance
        ball = P._ball_note(P._std.cyc_weight(self.cir), self.terminology)
        return ((ball + " ") if ball else "") + (f"Yarn quantities are estimates with a ±{tol * 100:.0f}% range, not "
                f"measurements: consumption varies with yarn, hook and tension, so buy a little "
                f"more than the top of the range if your dye lot matters to you."
                if not self.twin.calibrated else
                "Yarn quantities were calibrated against a physically worked sample.")

    def size_rows(self) -> list[tuple[str, str, str, str]]:
        """(size, finished size, yarn, notes) per size, from the release's own records."""
        g = self.cir.grading
        if g is not None:
            out = []
            for e in g.sizes:
                built = e.get("built_cm") or {}
                body = e.get("body_cm") or {}

                def pick(d):
                    keys = [k for k in ("chest", "bust", "hip", "length", "body_length")
                            if k in d] or sorted(d)
                    return keys[:2]

                fin = ", ".join(f"{'finished ' if k == 'chest' else ''}"
                                f"{k.replace('_', ' ')} {built[k]:g} cm" for k in pick(built))
                yarn = (f"yarn about {e['yarn_m']:.0f} m / {e['yarn_m'] * 1.094:.0f} yd"
                        if e.get("yarn_m") else "")
                if not fin or not yarn:
                    self.block(f"size {e.get('size')} has no built measurement or yarn figure",
                               "sizing")
                # the body table's bust is the chest the garment is fitted to (publish.pdf)
                note = ", ".join(f"to fit {'chest' if k in ('bust', 'chest') else k.replace('_', ' ')}"
                                 f" {body[k]:g} cm" for k in pick(body)[:1])
                if built.get("chest") is not None and body.get("bust") is not None:
                    note += f", {built['chest'] - body['bust']:+.0f} cm ease"
                if str(e.get("size")) == str(g.size):
                    note = (note + "; this edition" if note else "this edition")
                out.append((f"SIZE {str(e.get('size')).upper()}", fin, yarn, note))
            return out
        size = self.size_text()
        yarn = self.total_yarn()
        note = (f"makes {self.pieces_phrase()}" if self.make_total > 1
                else "one size, as written")
        return [("One size", size, yarn, note)]

    def fit_text(self) -> str:
        fam, cir, twin = self.family, self.cir, self.twin
        if fam == GARMENT:
            fit = P.fit_statement(cir)
            if not fit:
                self.block("a garment's fit and ease are missing from the grading record",
                           "sizing")
            from ..cir.graded import CHILD
            if cir.grading.table == CHILD.name:
                fit += " " + P.AGE_IS_A_GUIDE
            return fit
        size = self.size_text()
        if fam == PILLOW:
            return (f"The finished cover measures {size} at the stated gauge. Its measurements "
                    f"are the cover's own, from this pattern's stitches; choose a pad to suit.")
        if fam == BLANKET:
            return (f"The finished blanket measures {size} after blocking, at the stated gauge. "
                    f"Its drape comes from the stitch pattern and your tension; a looser "
                    f"gauge makes a larger, softer blanket.")
        if fam == COLOURWORK:
            return (f"The finished piece measures {size} at the stated gauge. The colour motif "
                    f"is set by stitch counts, so it keeps its proportions at any gauge; only "
                    f"the measurements change.")
        if fam == AMIGURUMI and not twin.width_cm:
            return (f"At the stated gauge the stuffed pieces measure {size} at their widest "
                    f"rounds. Their height and fullness come from how firmly you stuff, which "
                    f"gauge cannot predict, so measure your own pieces. Read the safety notes "
                    f"in section 08 before you start: this pattern is for a children's item.")
        if fam in (BABY, AMIGURUMI):
            return (f"The finished piece measures {size} at the stated gauge. Read the safety "
                    f"notes in section 08 before you start: this pattern is for a children's "
                    f"item.")
        each = "Each piece" if self.make_total > 1 else "The finished piece"
        return f"{each} measures {size} at the stated gauge, after blocking."

    def measurement_note(self) -> str:
        return (self.calibration() + " Figures are given in metric with imperial "
                "equivalents (1 in = 2.54 cm; 1 m = 1.094 yd).")

    def making_sequence(self) -> list[str]:
        cir, twin = self.cir, self.twin
        steps: list[str] = []
        rows = P._rows_by_index(twin)
        for title, lines in self.parsed["blocks"]:
            if title.lower().startswith("finishing"):
                continue
            labels = [ln for ln in lines if P._STEP.match(ln)]
            if not labels:
                continue
            first = P._STEP.match(labels[0]).group("label").rstrip(":")
            last = P._STEP.match(labels[-1]).group("label").rstrip(":")
            cm = P._COUNT.search(labels[-1])
            count = cm.group("count").strip("()") if cm else ""
            name = title[:1].upper() + title[1:]
            steps.append(f"{name}: {first} to {last}" + (f", ending with {count}." if count
                                                           else "."))
        for i, seam in enumerate(cir.assembly, start=1):
            lines = P.construction_overview(cir) or []
            join = next((ln for ln in lines if ln.startswith(f"Join {i}:")), None)
            if join:
                steps.append(join)
        fin = self.finishing_lines()
        if fin:
            steps.append("Finish: " + _one_line(fin[0]))
        if not steps:
            self.block("no making sequence can be read from the compiled pattern",
                       "construction")
        return steps

    def hook_range_line(self) -> str:
        lo, hi = hook_range(self.cir.gauge.hook_mm)
        if lo == hi:
            return (f"Hook range: {hook_label(hi)} only; there is no standard size within "
                    f"{AMIGURUMI_HOOK_STEP_MM:g} mm below it.")
        return (f"Hook range: {hook_label(lo)} to {hook_label(hi)}. Toy fabric should be "
                f"firm, with no stuffing showing between stitches: if it shows, go down "
                f"within this range and check the gauge again.")

    def eye_options(self) -> list[str]:
        """Embroidered or safety eyes, from the CIR's own materials and the head's rounds.

        Safety eyes are offered only when the certified materials list them; they are a
        small part, so an embroidered face is the only option for a child under 3."""
        mats = [m.name.lower() for m in self.cir.materials]
        head = next((c for c in self.cir.components if "head" in c.name.lower()), None)
        if head is None and len(self.cir.components) == 1:
            head = self.cir.components[0]
        if head is None or not _round_rows(head):
            self.block("an amigurumi pattern needs a head (or single piece) to place eyes on",
                       "notes")
        rows = _round_rows(head)
        widest = max(r.declared_count for r in rows)
        at = [r.index for r in rows if r.declared_count == widest]
        floss = next((m for m in self.cir.materials if "floss" in m.name.lower()
                      or "embroider" in m.name.lower()), None)
        out = [f"Embroidered eyes (as written): with "
               f"{floss.name if floss else 'embroidery thread'}, work a few straight stitches "
               f"over one stitch for each eye, between rounds {at[0]} and {at[-1]} of the "
               f"{head.name.replace('_', ' ')} (its widest rounds), before the piece is "
               f"closed, and knot the ends inside. Nothing can be pulled off, so this is the "
               f"option for any child, and the only one for a child under 3."]
        safety = [m for m in self.cir.materials if "safety eye" in m.name.lower()]
        if safety:
            out.append(f"Safety eyes: {safety[0].name}. Fit the washer before the piece is "
                       f"closed. Safety eyes are a small part: never use them on a toy for a "
                       f"child under 3.")
        else:
            out.append("Safety eyes are not part of this pattern: they are a small part, and "
                       "the materials, safety notes and age guidance here are for the "
                       "embroidered face only.")
        return out

    def assembly_lines(self) -> list[str]:
        """The writer's Assembly steps, with the "Step N:" label dropped (07 numbers them)."""
        for title, lines in self.parsed["blocks"]:
            if title.lower().startswith("assembly"):
                return [re.sub(r"^Step \d+:\s*", "", ln) for ln in lines if ln.strip()]
        return []

    def component_for(self, block_key: str):
        for c in self.cir.components:
            if c.name.replace("_", " ").lower() == block_key and _round_rows(c) and \
                    c.construction in ("joined_rounds", "spiral_rounds"):
                return c
        return None

    def component_caption(self, comp) -> str:
        rows = _round_rows(comp)
        widest = max(r.declared_count for r in rows)
        at = [r.index for r in rows if r.declared_count == widest]
        span = f"round {at[0]}" if len(at) == 1 else f"rounds {at[0]} to {at[-1]}"
        cap = (f"Diagram of the {comp.name.replace('_', ' ')}: one band per round, as wide as "
               f"that round at gauge. Widest at {span} ({widest} sts).")
        stuffed = stuff_round(comp)
        if stuffed is not None:
            cap += f" The arrow marks round {stuffed}: stuff here."
        return cap + " Drawn from the stitch data, not a photograph."

    def finishing_lines(self) -> list[str]:
        for title, lines in self.parsed["blocks"]:
            if title.lower().startswith("finishing"):
                return [ln for ln in lines if ln.strip()]
        return []

    def check_construction(self) -> str:
        twin, cir = self.twin, self.cir
        rows = P._rows_by_index(twin)
        comp = cir.components[0]
        unit = "round" if "round" in comp.construction else "row"
        bits = [f"Finished size: {self.size_text()}."]
        if rows:
            bits.append(f"The last {unit} has {len(rows[max(rows)])} stitches, and there are "
                        f"{len(rows)} {unit}s in all.")
        bits.append("The schematic is drawn from the pattern's own geometry, so it agrees "
                    "with the written instructions; check your piece against both.")
        return " ".join(bits)

    def quality_checks(self) -> str:
        cir = self.cir
        out = ([f"Measure the piece: it should be {self.size_text()} after blocking."]
               if self.twin.width_cm else
               [f"Measure each stuffed piece around its widest round: {self.size_text()}."])
        rows = P._rows_by_index(self.twin)
        if rows:
            out.append(f"Count the last {'round' if 'round' in cir.components[0].construction else 'row'}: "
                       f"{len(rows[max(rows)])} stitches.")
        if cir.assembly:
            out.append("Tug every seam gently; none should open.")
        out.append("Every end is woven in on the wrong side.")
        if self.childrens:
            out.append("Re-read the safety notes in section 08 and check the finished item "
                       "against each of them before it is used.")
        return " ".join(out)


# ---- pages -----------------------------------------------------------------------------------

def _cover(t: _T, f: _Facts, slots: list[dict]) -> None:
    cir = f.cir
    t.cover_page()
    logo = _logo_cover()
    box_w, box_h = 368, 245
    t.image(logo, 122, 27, box_w, box_h,
            figure={"kind": "owner_logo", "use": "cover",
                    "source": "publish.pdf._cover_logo (canonical owner logo, resampled)"})
    t.logo_pages.append(t.pages)
    t.rule(58, 554, 277, ROSE_RULE, 0.8)
    t.text(58, 300, f"{FAMILY_LABEL[f.family]}  /  DIGITAL DOWNLOAD", SANS_BOLD, MIN_PT,
           ROSE_ON_CREAM, track=1.6)
    title = cir.title.upper()
    size = 31.0
    lines = [title]
    while t.width(title, SERIF_SEMI, size) > 496 and size > 24:
        size -= 1
    if t.width(title, SERIF_SEMI, size) > 496:
        lines = t.wrap(title, SERIF_SEMI, size, 496)[:2]
    y = 321 + size * 0.85
    for ln in lines:
        t.text(58, y, ln, SERIF_SEMI, size, INK)
        y += size * 1.05
    story = _one_line(f.overview()[0]) if f.overview() else ""
    if not story:
        f.block("no one-line product description can be stated", "cover")
    line_top = y - size * 0.85 + 14
    line_top = t.para(58, line_top, 496, story, font=SANS, size=10.2, color=GREY, leading=14)
    ident = (f"{cir.title}  ·  Crochet pattern by Brambleloop Studio  ·  {f.terminology} terms  ·  "
             f"version {cir.version}")
    if line_top + 4 < 420:
        t.text(58, line_top + 10, ident, SANS_SEMI, MIN_PT, GREY)
    # the hero slot: the certified hero (slot 1)
    x, top, w, h = 62, 429, 488, 232
    t.card(x - 4, top - 4, w + 8, h + 8, fill=PAPER, radius=12)
    if slots:
        hero = slots[0]
        t.image(hero["jpeg"], x, top, w, h, fit="cover", radius=9,
                figure={"kind": "certified_frame", "slot": "cover_hero",
                        "frame_sha256": hero["frame_sha256"],
                        "rendition_sha256": hero["rendition_sha256"]})
        _chip(t, x + 12, top + h - 30, hero["chip"])
    else:
        t.card(x, top, w, h, fill=SLOT, radius=9)
        t.text(x + w / 2, top + h / 2, "AWAITING CERTIFIED GALLERY", SANS_BOLD, MIN_PT, INK,
               align="centre", track=1.2)
    # the forest band
    c = t.c
    c.setFillColor(FOREST)
    c.rect(0, t.y(686 + 52), PAGE_W, 52, fill=1, stroke=0)
    skill = f"SKILL  {f.difficulty.upper()}"
    term = f"{f.terminology} TERMINOLOGY"
    sk_w = t.width(skill, SANS_SEMI, MIN_PT, 0.6)
    te_w = t.width(term, SANS_SEMI, MIN_PT, 0.6)
    t.text(55, 715, skill, SANS_SEMI, MIN_PT, ON_FOREST, track=0.6)
    t.text(557, 715, term, SANS_SEMI, MIN_PT, ON_FOREST, track=0.6, align="right")
    lo, hi = 55 + sk_w + 24, 557 - te_w - 24
    sizes = t.wrap(f"SIZES  {_caps(f.sizes_line())}", SANS_SEMI, MIN_PT, hi - lo)
    if len(sizes) > 2:
        t.problems.append("PDF_TEXT_DOES_NOT_FIT: the cover's sizes need more than two lines")
    yy = 715 - (len(sizes[:2]) - 1) * 6.5
    for ln in sizes[:2]:
        t.text((lo + hi) / 2, yy, ln, SANS_SEMI, MIN_PT, ON_FOREST, align="centre", track=0.6)
        yy += 13
    t.prose.append(f"{f.terminology} terms")
    t.text(PAGE_W / 2, 760, COVER_TAGLINE, SANS, MIN_PT, BROWN_ON_CREAM, align="centre",
           track=1.2)
    t.text(PAGE_W / 2, 788, f"{t.release_id}  ·  page 1 of {t.total_pages or 1}", SANS,
           MIN_PT, GREY, align="centre")


def _chip(t: _T, x: float, top: float, s: str) -> None:
    w = t.width(s, SANS_BOLD, MIN_PT, 0.6) + 20
    t.card(x, top, w, 20, fill=PAPER, radius=6)
    t.text(x + 10, top + 13.5, s, SANS_BOLD, MIN_PT, INK, track=0.6)


def _card_with(t: _T, x: float, top: float, w: float, title: str, body: list[str], *,
               fill=CREAM, stroke=None, title_color=None, body_color=INK, size: float = 10,
               pad: float = 15, min_h: float = 0.0, gap: float = 6,
               leading: float | None = None) -> float:
    """A card with a tracked label and paragraphs; returns its height (drawn at `top`)."""
    inner = w - 2 * pad
    h = _card_height(t, w, body, size=size, pad=pad, gap=gap, leading=leading)
    h = max(h, min_h)
    t.card(x, top, w, h, fill=fill, stroke=stroke)
    t.label(x + pad, top + pad, title, title_color or (BROWN if fill is not FOREST else
                                                        ON_FOREST))
    y = top + pad + 20
    for b in body:
        y = t.para(x + pad, y, inner, b, size=size, color=body_color, leading=leading) + gap
    return h


def _card_height(t: _T, w: float, body: list[str], *, size: float = 10, pad: float = 15,
                 gap: float = 6, leading: float | None = None) -> float:
    inner = w - 2 * pad
    return (pad + 18 + sum(t.para_h(b, inner, size=size, leading=leading) + gap for b in body)
            + pad - gap)


def _flow_card(t: _T, title: str, body: list[str], **kw) -> None:
    """A full-width card placed at the cursor, starting a continuation page if needed. A card
    taller than a page is split by paragraph."""
    w = CONTENT_W
    room = CONTENT_BOTTOM - 200
    hk = {k: kw[k] for k in ("size", "gap", "leading") if k in kw}
    chunks: list[list[str]] = [[]]
    for b in body:
        if chunks[-1] and _card_height(t, w, chunks[-1] + [b], **hk) > room:
            chunks.append([])
        chunks[-1].append(b)
    for n, chunk in enumerate(chunks):
        h = _card_height(t, w, chunk, **hk)
        t.need(h)
        _card_with(t, CONTENT_X, t.top, w, title if n == 0 else f"{title} (continued)", chunk,
                   **kw)
        t.top += h + 14


def _meet(t: _T, f: _Facts) -> None:
    t.section_page("meet_the_pattern")
    about = f.memo("overview", f.overview)
    if not about:
        f.block("no project introduction can be built from the design record",
                "meet_the_pattern")
    how = f.how_it_comes_together()
    left_body_h = (sum(t.para_h(p, 280, size=10.6, leading=16) + 6 for p in about) + 34 +
                   t.para_h(how, 280, size=10) + 50)
    details = [("DIFFICULTY", f.difficulty.capitalize()),
               ("CATEGORY", FAMILY_LABEL[f.family]),
               ("SIZES", f.sizes_line()),
               ("YARN WEIGHT", cyc_label(f.cir)),
               ("HOOK", hook_label(f.cir.gauge.hook_mm)),
               ("CONSTRUCTION", f.cir.construction.replace("_", " ").capitalize())]
    right_h = 46 + sum(14 + 6 + t.para_h(v, 166, size=MIN_PT + 0.2, font=SANS_SEMI) for _k, v
                       in details) + 8
    h = max(260, left_body_h, right_h)
    top = 206
    t.card(47, top, 310, h, fill=CREAM)
    t.card(371, top, 196, h, fill=SAGE)
    t.label(62, top + 14, "ABOUT THIS DESIGN")
    y = top + 42
    for p in about:
        y = t.para(62, y, 280, p, size=10.6, leading=16) + 6
    y += 8
    t.label(62, y, "HOW IT COMES TOGETHER")
    y = t.para(62, y + 26, 280, how, size=10, leading=15)
    t.label(389, top + 14, "PROJECT DETAILS", INK)
    y = top + 43
    for k, v in details:
        t.label(389, y, k, BROWN, track=1.2)
        y = t.para(389, y + 14, 166, v, font=SANS_SEMI, size=MIN_PT + 0.2, leading=13) + 8
    t.top = top + h + 22
    if t.top + 180 > CONTENT_BOTTOM:
        t.section_page("meet_the_pattern", continued=True)
    t.rule(47, 567, t.top, ROSE_RULE, 0.75)
    t.label(47, t.top + 14, "YOUR DOWNLOAD INCLUDES", BROWN, track=1.8)
    top = t.top + 43
    body_h = t.para_h(DOWNLOAD_INCLUDES, 484, size=10.8, leading=16)
    h = 30 + body_h + 60
    t.card(47, top, 520, h, fill=PAPER, stroke=RULE)
    y = t.para(65, top + 20, 484, DOWNLOAD_INCLUDES, size=10.8, leading=16)
    t.label(65, y + 22, "DIGITAL FILES  /  NOT A PHYSICAL PRODUCT", ROSE, track=1.8)
    t.top = top + h + 14


def _tools(t: _T, f: _Facts) -> None:
    cir, twin = f.cir, f.twin
    t.section_page("tools_and_yarn")
    letters = P.color_letters(cir)
    yarn = []
    for m in cir.materials:
        fibres = ""
        letter = letters.get(m.color_id) if m.color_id else None
        name = f"{m.name} ({m.yarn_weight})"
        if m.colorway:
            name += f", colourway {m.colorway}"
        if letter:
            name = f"Colour {letter}: " + name
        metres = twin.yarn_metres_by_color.get(m.color_id or "", None)
        if metres:
            name += f"; {f.yarn_amount(metres)}"
        yarn.append(name + fibres + ".")
    hooks = [f"{hook_label(cir.gauge.hook_mm)}, {P._std.HOOK_GAUGE_PHRASE}."]
    if f.family == AMIGURUMI:
        hooks.append(f.hook_range_line())
    instructed = "\n".join([f.text] + [abbreviations.method(code, f.terminology)
                                       for code in sorted(twin.stitch_types_used)])
    notions = [f"{n.capitalize()}: {w}." for n, w in P._tools_required(cir, instructed)]
    if "sts)" in f.text and not any(n.lower().startswith("stitch marker") for n in notions):
        notions.append("Stitch marker: optional, to mark the first stitch of each round.")
    notions.insert(0, "Scissors.")
    left = [("YARN", yarn), ("CROCHET HOOKS", hooks), ("NOTIONS + TOOLS", notions)]
    gauge = [f.gauge_line()]
    important = [("Gauge is specific to this pattern. Work a swatch before you start: the "
                  "finished size is computed from this gauge, and a different gauge changes "
                  "it in proportion. ") + f.calibration()]
    qty = [f"{name}: {f.yarn_amount(m)}." for name, m in
           sorted(twin.yarn_metres_by_color.items())]
    if f.make_total > 1:
        qty.append(f"Totals are for every piece: {f.pieces_phrase()}.")
    right = [("GAUGE", gauge), ("IMPORTANT", important), ("YARN QUANTITIES", qty)]
    top = 207
    lh = [_card_height(t, COL_W, b, size=10) for _k, b in left]
    rh = [_card_height(t, 253, b, size=10) for _k, b in right]
    left_total = sum(lh) + 11 * (len(lh) - 1)
    right_total = sum(rh) + 8
    maker = [f.tolerance_note()]
    maker_h = _card_height(t, CONTENT_W, maker, size=10)
    if top + max(left_total, right_total) + 12 + maker_h > CONTENT_BOTTOM:
        # Too much for one page: the yarn column flows card by card.
        for k, b in left + right + [("MAKER NOTE", maker)]:
            _flow_card(t, k, b, fill=FOREST if k == "MAKER NOTE" else CREAM,
                       body_color=ON_FOREST if k == "MAKER NOTE" else INK)
        return
    y = top
    for (k, b), h in zip(left, lh):
        _card_with(t, 47, y, COL_W, k, b)
        y += h + 11
    # the right column is one stroked card holding three blocks, as the template draws it
    t.card(314, top, 253, right_total, fill=PAPER, stroke=RULE)
    y2 = top
    for i, ((k, b), h) in enumerate(zip(right, rh)):
        t.label(328, y2 + 15, k, ROSE)
        yy = y2 + 35
        for para in b:
            yy = t.para(328, yy, 225, para, size=10) + 6
        y2 += h
        if i < len(right) - 1:
            t.rule(328, 553, y2 - 4, RULE, 0.6)
    bottom = max(y - 11, top + right_total) + 12
    _card_with(t, 47, bottom, CONTENT_W, "MAKER NOTE", maker, fill=FOREST, body_color=ON_FOREST)
    t.top = bottom + maker_h + 14


def _sizing(t: _T, f: _Facts) -> None:
    t.section_page("sizing")
    t.label(47, 203, "SIZE & MATERIAL GUIDE", BROWN, track=1.8)
    rows = f.size_rows()
    cols = [(58, "SIZE", 60), (113, "FINISHED SIZE", 150), (275, "YARN", 110),
            (387, "NOTES", 170)]
    top = 218
    t.card(47, top, 520, 30, fill=FOREST, radius=5)
    for x, head, _w in cols:
        t.text(x, top + 19, head, SANS_BOLD, MIN_PT, ON_FOREST, track=1.0)
    y = top + 30
    for i, row in enumerate(rows):
        lines = [t.wrap(v, SANS, MIN_PT, w) for (x, _h, w), v in zip(cols, row)]
        h = max(28, 12 + max(len(ls) for ls in lines) * 12.5)
        if y + h > CONTENT_BOTTOM - 120:
            t.section_page("sizing", continued=True)
            y = 200
        if i % 2 == 0:
            t.c.setFillColor(CREAM)
            t.c.rect(47, t.y(y + h), 520, h, fill=1, stroke=0)
        for (x, _h, _w), ls in zip(cols, lines):
            yy = y + 17
            for ln in ls:
                t.text(x, yy, ln, SANS, MIN_PT, INK)
                yy += 12.5
        y += h
    t.prose.append("Sizes and fit" if f.family == GARMENT else "Finished size")
    t.top = max(y + 30, 452 if len(rows) <= 3 else y + 30)
    fit = [f.fit_text()]
    if f.family == GARMENT:
        care = P.care_note(f.cir)
        if not care:
            f.block("a garment's care note is missing", "sizing")
    h = _card_height(t, CONTENT_W, fit, size=10)
    t.need(h + 106)
    _card_with(t, 47, t.top, CONTENT_W, FIT_TITLE[f.family], fit, fill=SAGE,
               min_h=min(130, h + 40))
    t.top += max(h, min(130, h + 40)) + 13
    note = [f.measurement_note()]
    h = _card_height(t, CONTENT_W, note)
    t.need(h)
    _card_with(t, 47, t.top, CONTENT_W, "A NOTE ON MEASUREMENTS", note, fill=PAPER,
               stroke=RULE, title_color=ROSE)
    t.top += h + 14


def _schematic_image(f: _Facts):
    return f.memo("schematic", lambda: _schematic_image_uncached(f))


def _schematic_image_uncached(f: _Facts):
    from .construction_diagrams import stages
    from .schematic import schematic_for

    sch = schematic_for(f.cir, f.result)
    if sch is not None:
        return sch.image, "publish.schematic.schematic_for"
    if f.family == AMIGURUMI and not f.twin.width_cm:
        # a closed stuffed piece has no width the twin will state; its profile is the
        # schematic (one band per round at gauge), not a disclosed render that needs one
        return (component_profile(f.cir, f.cir.components[0]),
                "publish.pdf_template.component_profile")
    views = P._disclosed_views(f.cir)
    if "scale" in views:
        return views["scale"][0], "visual.disclosed_render (scale view, from the twin)"
    st = stages(f.cir)
    if st:
        return st[-1].image(), "publish.construction_diagrams.stages"
    grid = _mini_grid(f, 1, max(P._rows_by_index(f.twin) or {1: []}), cols=None, px=480)
    if grid is not None:
        return grid, "publish.pdf_template._mini_grid (twin colour and stitch grid)"
    return None, ""


def _construction(t: _T, f: _Facts) -> None:
    t.section_page("construction")
    t.label(47, 203, "THE MAKING SEQUENCE", BROWN, track=1.8)
    steps = f.making_sequence()
    img, source = _schematic_image(f)
    if img is None:
        f.block("no schematic can be drawn from the certified geometry", "construction")
    # the schematic card first, beside the sequence on the section's first page
    sx, stop, sw, sh = 379, 240, 188, 309
    first_page = t.pages
    t.card(sx, stop, sw, sh, fill=SAGE)
    t.label(sx + 12, stop + 14, "SCHEMATIC", INK)
    t.prose.append("Schematic")
    t.image(img, sx + 10, stop + 36, sw - 20, sh - 80, fit="contain",
            figure={"kind": "schematic", "source": source, "label": "Schematic"})
    t.label(sx + 12, stop + sh - 26, "DIAGRAM FROM CERTIFIED DATA", BROWN, track=1.0)
    y = 240
    fills = [CREAM, PAPER]
    for i, s in enumerate(steps, start=1):
        lines = t.wrap(s, SANS, 10, 250)
        h = max(51, 22 + len(lines) * 14)
        if y + h > CONTENT_BOTTOM - 130:
            t.section_page("construction", continued=True)
            y = 200
        t.card(47, y, 315, h, fill=fills[(i - 1) % 2],
               stroke=None if fills[(i - 1) % 2] is CREAM else RULE)
        t.text(62, y + 33, f"{i:02d}", SERIF, 22, ROSE)
        yy = y + 18 + 10 * 0.78
        for ln in lines:
            t.text(100, yy, ln, SANS, 10, INK, record=False)
            yy += 14
        t.prose.append(s)
        y += h + 11
    if t.pages != first_page:
        stop, sh = 0, 0
    t.top = max(y, stop + sh + 17)
    body = [f.check_construction()]
    h = _card_height(t, CONTENT_W, body)
    t.need(h)
    _card_with(t, 47, t.top, CONTENT_W, "CHECK THE CONSTRUCTION", body, fill=PAPER,
               stroke=RULE, title_color=ROSE)
    t.top += h + 14


def _abbreviations(t: _T, f: _Facts) -> None:
    t.section_page("abbreviations")
    t.label(47, 203, f"COMMON TERMS  /  {f.terminology} TERMINOLOGY", BROWN, track=1.8)
    key = f.key
    if not key:
        f.block("the instructions use no stitch the key can define", "abbreviations")
    half = (len(key) + 1) // 2
    colsets = [key[:half], key[half:]]

    def entry_h(e):
        return max(18, len(t.wrap(e.means, SANS, MIN_PT + 0.5, 160)) * 12.5 + 6)

    h = 22 + max(sum(entry_h(e) for e in cs) for cs in colsets) + 16
    top = 226
    if top + h > CONTENT_BOTTOM:
        h = CONTENT_BOTTOM - top
    for ci, cs in enumerate(colsets):
        x = 47 if ci == 0 else 314
        t.card(x, top, 253, h, fill=CREAM)
        y = top + 22
        for e in cs:
            eh = entry_h(e)
            if y + eh > top + h - 8:
                break
            t.text(x + 12, y + 8, e.token, SANS_BOLD, MIN_PT + 0.5, INK)
            yy = y + 8
            for ln in t.wrap(e.means, SANS, MIN_PT + 0.5, 160):
                t.text(x + 80, yy, ln, SANS, MIN_PT + 0.5, INK, record=False)
                yy += 12.5
            t.prose.append(f"{e.token} {e.means}")
            t.rule(x + 12, x + 241, y + eh - 2, RULE, 0.5)
            y += eh
    t.top = top + h + 26
    notation = abbreviations.notation_key(f.text)
    if notation:
        _flow_card(t, "HOW TO READ A ROW", [f"{e.token}  {e.means}" for e in notation],
                   fill=PAPER, stroke=RULE, title_color=ROSE)
    methods = [e for e in key if e.method]
    if methods:
        t.need(60)
        t.label(47, t.top, "SPECIAL STITCHES", ROSE, track=1.8)
        t.top += 26
        for e in methods:
            _flow_card(t, f"{e.token}  /  {e.means}", [e.method], fill=PAPER, stroke=RULE,
                       title_color=INK)
    cables = abbreviations.CABLE_CODES & set(f.twin.stitch_types_used)
    if cables:
        _flow_card(t, "CABLE NOTE", [abbreviations.CABLE_DIRECTION_NOTE], fill=PAPER,
                   stroke=RULE, title_color=ROSE)
    techniques = abbreviations.techniques(f.text, f.terminology)
    if techniques:
        _flow_card(t, "TECHNIQUES USED",
                   [f"{e.token.capitalize()}: {e.means}" for e in techniques],
                   fill=PAPER, stroke=RULE, title_color=ROSE)


# -- the pattern ----------------------------------------------------------------------------

def _mini_grid(f: _Facts, first: int, last: int, *, cols: int | None = 24, px: int = 360):
    """A deterministic diagram of rows `first`..`last` (first `cols` stitches) from the twin's
    own colour and stitch grid: each cell is one stitch, filled with its yarn's colour, taller
    stitches drawn taller. Drawn from certified data; never a picture of a product."""
    from PIL import Image, ImageDraw

    twin = f.twin
    cells = [c for c in twin.cells if first <= c.row <= last]
    if not cells:
        return None
    rows = sorted({c.row for c in cells})
    width = max(c.position for c in cells) + 1
    n = width if cols is None else min(cols, width)
    cell = max(4, min(28, px // max(n, 1)))
    w, h = n * cell + 8, len(rows) * cell + 8
    img = Image.new("RGB", (w, h), (254, 252, 249))
    d = ImageDraw.Draw(img)
    tall = {"dc", "tr", "dtr", "fpdc", "bpdc", "bob", "pop", "cl", "hdc", "fptr", "bptr"}
    for c in cells:
        if c.position >= n:
            continue
        ri = rows.index(c.row)
        x0 = 4 + c.position * cell
        y1 = h - 4 - ri * cell
        hex_ = (f.cir.colors or {}).get(c.color or "", "") or "#888888"
        try:
            rgb = tuple(int(hex_.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            rgb = (136, 136, 136)
        inset = 1 if c.stitch in tall else max(1, cell // 4)
        d.rectangle([x0 + 1, y1 - cell + inset, x0 + cell - 1, y1 - 1], fill=rgb,
                    outline=(47, 62, 51))
    return img


_ANY_COUNT = re.compile(r"\(\d+ sts?\)")


def _tricky_rows(f: _Facts, labels: list[tuple[int, str]]) -> set[int]:
    """The step numbers where the standard asks for a picture: the first row whose stitch
    sequence differs from the row below it, and the first colour change."""
    out: set[int] = set()
    rows = P._rows_by_index(f.twin)
    prev_seq, prev_col = None, None
    first_change = first_colour = None
    for r in sorted(rows):
        seq = tuple(c.stitch for c in rows[r])
        col = tuple(c.color for c in rows[r])
        if prev_seq is not None and seq != prev_seq and first_change is None:
            first_change = r
        if prev_col is not None and col != prev_col and first_colour is None:
            first_colour = r
        prev_seq, prev_col = seq, col
    for r in (first_change, first_colour):
        if r is not None:
            out.add(r)
    return out


def _pattern(t: _T, f: _Facts, slots: list[dict]) -> int:
    """Section 06: two columns, component bars, Row/Round labels, a stitch count on every
    row, inline mini-diagrams and the progress-photo slot at the tricky steps."""
    from .construction_diagrams import stages as _stages

    t.section_page("pattern")
    sub = f"{f.cir.title.upper()}  •  {f.terminology} TERMINOLOGY"
    t.text(47, 207, sub, SANS_BOLD, MIN_PT, ROSE, track=1.0)
    t.prose.append(f"Instructions ({f.terminology} terms)")
    header = [h for h in f.parsed["header"] if h != f.cir.title]
    stages = f.memo("stages", lambda: _stages(f.cir))
    stage_at = {st.round: st for st in stages}
    progress = next((s for s in slots if s["slot"] == "construction_materials"), None)
    progress_used = False
    rows_printed = 0
    col = 0
    x = CONTENT_X
    y = 228
    page_top = 200

    def next_col(h: float) -> None:
        nonlocal col, x, y
        if y + h <= CONTENT_BOTTOM:
            return
        if col == 0:
            col, x, y = 1, COL2_X, (228 if t.pages == first_page else page_top)
        else:
            t.section_page("pattern", continued=True)
            col, x, y = 0, CONTENT_X, page_top

    first_page = t.pages
    # the writer's header (gauge, materials, terminology) as the column's opening note
    for h_line in header:
        lines = t.wrap(h_line, SANS, MIN_PT + 0.5, COL_W - 6)
        hh = len(lines) * 13 + 4
        next_col(hh)
        yy = y + 10
        for ln in lines:
            t.text(x + 2, yy, ln, SANS, MIN_PT + 0.5, INK, record=False)
            yy += 13
        t.prose.append(h_line)
        y += hh
    y += 8
    tricky = _tricky_rows(f, [])
    unit_word = "Rnd" if "round" in f.cir.components[0].construction else "Row"
    for title, lines in f.parsed["blocks"]:
        if title.lower().startswith("finishing"):
            continue
        if f.family == AMIGURUMI and title.lower().startswith("assembly"):
            continue   # section 07 carries it as numbered, placed steps (_assembly_steps)
        # The twin (and so every inline diagram drawn from it) describes one component; a
        # diagram is placed only in that component's block, never under another piece.
        block_key = title.lower().split(" (")[0].replace("_", " ").strip()
        twin_key = str(f.twin.component or f.cir.components[0].name).replace("_", " ").lower()
        draws = block_key == twin_key
        sided = P._sides_for(f.cir, title)
        if sided:
            # RS/WS from the CIR's own turns (publish.pdf._sides_for), the note stated once.
            lines = [P.RS_NOTE] + [P._with_side(ln, sided) for ln in lines]
        next_col(29 + 40)
        t.card(x, y, COL_W + 2, 29, fill=FOREST, radius=5)
        t.text(x + 12, y + 18.5, title.upper(), SANS_BOLD, MIN_PT, ON_FOREST, track=1.0)
        t.prose.append(title[:1].upper() + title[1:])
        y += 29 + 12
        comp = f.component_for(block_key) if f.family == AMIGURUMI else None
        if comp is not None:
            ih = 118
            next_col(ih + 10)
            t.card(x, y, COL_W, ih, fill=CREAM, radius=6)
            t.image(component_profile(f.cir, comp), x + 6, y + 6, ih - 12, ih - 12,
                    figure={"kind": "component_diagram", "component": comp.name,
                            "source": "publish.pdf_template.component_profile"})
            cap = f.component_caption(comp)
            yy = y + 16
            for b in t.wrap(cap, SANS, MIN_PT, COL_W - ih - 8):
                t.text(x + ih + 2, yy, b, SANS, MIN_PT, INK, record=False)
                yy += 11.5
            t.prose.append(cap)
            y += ih + 10
        for ln in lines:
            if not ln.strip():
                continue
            m = P._STEP.match(ln)
            if not m:
                body = t.wrap(ln, SANS, MIN_PT + 0.5, COL_W - 6)
                hh = len(body) * 13.5 + 8
                next_col(hh)
                yy = y + 10
                for b in body:
                    t.text(x + 3, yy, b, SANS, MIN_PT + 0.5, INK, record=False)
                    yy += 13.5
                t.prose.append(ln)
                y += hh
                continue
            label = m.group("label")
            body = m.group("body")
            counts = list(_ANY_COUNT.finditer(body))
            if not counts:
                f.block(f"{label.rstrip(':')} has no stitch count in the compiled pattern",
                        "pattern")
            cm = counts[-1]
            count = cm.group(0)
            trailing = body[cm.end():].strip().lstrip("-– ").strip()
            body = body[:cm.start()].rstrip()
            blines = t.wrap(body, SANS, MIN_PT + 0.5, COL_W - 8)
            tlines = t.wrap(trailing, SANS, MIN_PT, COL_W - 8) if trailing else []
            hh = 16 + len(blines) * 13 + 15 + 9 + len(tlines) * 12
            next_col(hh)
            colour = None
            c2 = re.search(r"\(([^)]+)\):$", label)
            if c2 and c2.group(1) in f.colours:
                colour = f.colours[c2.group(1)]
            lx = x + 1
            if colour is not None:
                t.c.saveState()
                t.c.setFillColor(colour)
                t.c.setStrokeColor(FOREST)
                t.c.setLineWidth(0.5)
                t.c.circle(x + 4, t.y(y + 8), 3.2, fill=1, stroke=1)
                t.c.restoreState()
                lx = x + 11
            t.text(lx, y + 11, label, SANS_BOLD, MIN_PT + 0.5, INK, record=False)
            yy = y + 16 + 9
            for b in blines:
                t.text(x + 2, yy, b, SANS, MIN_PT + 0.5, INK, record=False)
                yy += 13
            t.text(x + 2, yy + 1, count, SANS_SEMI, MIN_PT, ROSE, record=False)
            for b in tlines:
                yy += 12
                t.text(x + 2, yy + 1, b, SANS, MIN_PT, BROWN, record=False)
            t.prose.append(ln)
            rows_printed += 1
            y += hh
            t.rule(x, x + COL_W, y - 5, RULE, 0.6)
            # inline pictures at this step
            num = P._STEP_NUMBER.match(ln)
            n = int(num.group(1)) if num else None
            st = stage_at.get(n) if (n is not None and draws) else None
            if st is not None:
                ih = 96
                next_col(ih + 10)
                t.card(x, y, COL_W, ih, fill=CREAM, radius=6)
                t.image(st.image(), x + 6, y + 6, ih - 12, ih - 12,
                        figure={"kind": "construction_diagram", "round": st.round,
                                "source": "publish.construction_diagrams.stages",
                                "png_sha256": hashlib.sha256(st.png).hexdigest()})
                # "round"/"row" in words: a "Rnd N:" label here would read as a pattern row
                cap = (f"After {'round' if unit_word == 'Rnd' else 'row'} {st.round}: "
                       f"{st.stitches} stitches. Diagram drawn "
                       f"from this pattern's stitch data, not a photograph.")
                yy = y + 18
                for b in t.wrap(cap, SANS, MIN_PT, COL_W - ih - 8):
                    t.text(x + ih + 2, yy, b, SANS, MIN_PT, INK, record=False)
                    yy += 12
                t.prose.append(cap)
                y += ih + 10
            elif draws and n is not None and n in tricky and not stages:
                grid = _mini_grid(f, max(1, n - 2), n + 3)
                if grid is not None:
                    ih = 84
                    next_col(ih + 10)
                    t.card(x, y, COL_W, ih, fill=CREAM, radius=6)
                    gw = min(COL_W - 12, (ih - 12) * grid.width / grid.height)
                    t.image(grid, x + 6, y + 6, gw, ih - 30,
                            figure={"kind": "mini_diagram", "rows": [max(1, n - 2), n + 3],
                                    "source": "publish.pdf_template._mini_grid"})
                    cap = (f"{unit_word.lower()}s {max(1, n - 2)} to {n + 3}, first stitches, "
                           f"one cell per stitch in its yarn colour. Diagram drawn from this "
                           f"pattern's stitch data, not a photograph.")
                    t.para(x + 8, y + ih - 22, COL_W - 16, cap, size=MIN_PT, leading=11)
                    y += ih + 10
            if draws and n is not None and n in tricky and progress is not None \
                    and not progress_used:
                ih = 150
                next_col(ih + 10)
                t.image(progress["jpeg"], x, y, COL_W, ih - 24, fit="cover", radius=6,
                        figure={"kind": "certified_frame", "slot": "progress",
                                "frame_sha256": progress["frame_sha256"],
                                "rendition_sha256": progress["rendition_sha256"]})
                cap = ("Progress: construction and materials. " +
                       ("Test double, not a product image." if progress["test_double"] else
                        "Digital rendering, not a photograph." if progress["kind"] != "photo"
                        else "Photograph of a worked sample."))
                t.para(x + 2, y + ih - 18, COL_W - 4, cap, size=MIN_PT, leading=11,
                       color=BROWN)
                progress_used = True
                y += ih + 10
        y += 10
    # The colourwork and blanket variants always carry the chart; any other family carries it
    # when it is one page (a 36-tile chart of plain stitches is not help, it is paper).
    if f.chart_included():
        _chart_block(t, f)
    return rows_printed


def _chart_block(t: _T, f: _Facts) -> None:
    """The chart and its legend, from the twin (publish.charts, via publish.pdf)."""
    art = f.chart_art()
    charts = [tile["chart"] for tile in art.get("tiles") or []] or [art["chart"]]
    caption = art["caption"]
    if len(charts) > 1 and f.family not in CHART_FAMILIES:
        # Colourwork outside the chart families (stripes on a baby blanket) gets its chart as
        # a one-page overview: every row and its colour is already written out in 06, and
        # page after page of tiles would be paper, not help.
        charts = [art["chart"]]
        caption = ("Full chart at reduced scale, one cell per stitch in its colour, as an "
                   "overview: every row, with its colour, is written out in the pattern above.")
    for n, chart in enumerate(charts, start=1):
        t.section_page("pattern", continued=True)
        label = ("CHART AND KEYS" if len(charts) == 1
                 else f"CHART AND KEYS, TILE {n} OF {len(charts)}")
        t.label(47, 203, label, ROSE, track=1.8)
        t.prose.append("Chart")
        t.image(chart, 47, 222, CONTENT_W, CONTENT_BOTTOM - 222 - 150, fit="contain",
                figure={"kind": "chart", "source": "publish.charts (twin cell grid)"})
    t.top = CONTENT_BOTTOM - 140
    t.image(art["legend"], 47, t.top, CONTENT_W, 90, fit="contain",
            figure={"kind": "chart_legend", "source": "publish.charts.render_legend"})
    key = "Colour key: " + "; ".join(f"{name} ({hexv.upper()})" for name, hexv in
                                     sorted((f.cir.colors or {}).items()) if hexv) + "."
    t.para(47, t.top + 96, CONTENT_W, caption + " " + key, size=MIN_PT, color=BROWN,
           leading=12)
    t.prose.append(key)


def _assembly_steps(t: _T, f: _Facts, y: float) -> float:
    """Numbered assembly, one step per CIR seam, each with its placement cue in round
    numbers (the writer's own Assembly sentence) and a placement diagram: the host piece's
    profile with the rounds the join spans outlined (TEARDOWN_HIGHLAND_COW_AMIGURUMI)."""
    t.label(47, y - 8, "ASSEMBLY", ROSE, track=1.8)
    y += 6
    steps = f.assembly_lines()
    if len(steps) != len(f.cir.assembly):
        f.block("the compiled pattern's assembly does not state every join", "finishing")
    ih = 104
    for i, (seam, line) in enumerate(zip(f.cir.assembly, steps), start=1):
        host = next((c for c in f.cir.components if c.name == seam.piece_b), None)
        if seam.at_round is None or host is None:
            f.block(f"join {i} ({seam.piece_a} to {seam.piece_b}) has no round placement",
                    "finishing")
        lines = t.wrap(line, SANS, 10, 520 - 60 - ih - 12)
        h = max(ih + 12, 20 + len(lines) * 14)
        if y + h > CONTENT_BOTTOM:
            t.section_page("finishing", continued=True)
            y = 200
        t.card(47, y, 520, h, fill=SAGE if i % 2 else CREAM)
        t.text(62, y + 32, f"A{i}", SERIF, 20, ROSE)
        yy = y + 18 + 10 * 0.78
        for ln in lines:
            t.text(108, yy, ln, SANS, 10, INK, record=False)
            yy += 14
        last = seam.at_round + max(1, seam.spans_rounds) - 1
        t.image(component_profile(f.cir, host, highlight=(seam.at_round, last)),
                567 - ih - 6, y + 6, ih, ih,
                figure={"kind": "placement_diagram", "join": i, "host": host.name,
                        "rounds": [seam.at_round, last],
                        "source": "publish.pdf_template.component_profile"})
        t.prose.append(line)
        y += h + 12
    cap = ("Placement diagrams show the piece each join is sewn onto, drawn from its stitch "
           "counts, with the rounds of the join outlined. They are diagrams, not photographs.")
    t.para(47, y, 520, cap, size=MIN_PT, color=BROWN, leading=12)
    t.prose.append(cap)
    return y + 34


def _finishing(t: _T, f: _Facts) -> None:
    t.section_page("finishing")
    steps = f.finishing_lines()
    if not steps:
        f.block("the compiled pattern has no finishing block", "finishing")
    y = 230
    if f.family == AMIGURUMI and f.cir.assembly:
        y = _assembly_steps(t, f, y)
    for i, s in enumerate(steps, start=1):
        lines = t.wrap(s, SANS, 10, 440)
        h = max(48, 20 + len(lines) * 14)
        if y + h > CONTENT_BOTTOM:
            t.section_page("finishing", continued=True)
            y = 200
        t.card(47, y, 520, h, fill=SAGE if i % 2 else CREAM)
        t.text(62, y + 32, f"{i:02d}", SERIF, 22, ROSE)
        yy = y + 18 + 10 * 0.78
        for ln in lines:
            t.text(108, yy, ln, SANS, 10, INK, record=False)
            yy += 14
        t.prose.append(s)
        y += h + 12
    t.prose.append("Finishing")
    t.top = max(y + 20, 609 if y + 20 < 609 and 609 + 78 <= CONTENT_BOTTOM else y + 20)
    body = [f.quality_checks()]
    h = _card_height(t, CONTENT_W, body)
    t.need(h)
    _card_with(t, 47, t.top, CONTENT_W, "FINAL QUALITY CHECK", body, fill=PAPER, stroke=RULE,
               title_color=ROSE)
    t.top += h + 14


def _notes(t: _T, f: _Facts) -> None:
    from . import tips as tips_mod
    from . import value_stack

    cir, twin = f.cir, f.twin
    t.section_page("notes")
    t.top = 216
    g = cir.gauge
    stitch = P._gauge_stitch(cir, f.terminology)
    gauge = [f.gauge_line(),
             f"With the {g.hook_mm:g} mm hook and your yarn, work a square of {stitch} a little "
             f"over 12 cm wide and tall. Lay it flat without stretching it.",
             "More stitches than the gauge means your stitches are smaller: change to a larger "
             "hook. Fewer means they are larger: change to a smaller hook. Swatch again until "
             "it matches. The stitch counts are right at any gauge; only the measurements "
             "change."]
    note = P._round_gauge_note(cir, twin, f.terminology)
    if note:
        gauge.append(note)
    _flow_card(t, "GAUGE FIRST", gauge, fill=CREAM)
    try:
        guide = substitution.guidance(cir, twin)
    except substitution.SubstitutionRefused:
        guide = None
    if guide and guide["substitutes"]["weights"]:
        names = ", ".join(f"{w['weight'].replace('_', ' ')} (also called {w['also_called'][0]})"
                          for w in guide["substitutes"]["weights"])
        sub = [f"Gauge decides this, not the name on the band. Any of these can be worked to "
               f"this fabric: {names}. Swatch and change hook until your gauge matches."]
        for row in guide["how_much"]:
            if row.get("measurable"):
                lo_b, hi_b = row["balls_100g"]
                balls = (f"{lo_b} x 100g ball{'s' if lo_b != 1 else ''}" if lo_b == hi_b
                         else f"{lo_b}-{hi_b} x 100g balls")
                sub.append(f"If you use {row['to'].replace('_', ' ')}: about "
                           f"{row['buy_metres']:.0f} m in total ({balls}); "
                           f"{row['fabric_changes']}")
        weight = P._std.cyc_weight(cir)
        if weight is not None:
            sub.append(f"On the ball band, look for CYC {weight.number} and about "
                       f"{P._std.length_per_gram(weight, f.terminology)}.")
        sub.append("Changing fibre as well changes how much yarn each stitch takes by an "
                   "amount that has to be measured on a swatch.")
        _flow_card(t, "YARN SUBSTITUTION", sub, fill=SAGE)
    # publish.pdf.care_note is written for a garment ("the finished garment"); every other
    # family's care line is the writer's own finishing advice.
    care = P.care_note(cir) if f.family == GARMENT else None
    if not care:
        ball = [ln for ln in f.finishing_lines() if "ball band" in ln.lower()]
        care = ball[0] if ball else None
    if care:
        _flow_card(t, "CARE + FINISHING", [care], fill=CREAM)
    try:
        progress = value_stack.milestones(cir, twin)
    except value_stack.ValueStackRefused:
        progress = None
    helpful = []
    if progress and len(progress["milestones"]) > 2:
        helpful.append("Checking your progress: " + "; ".join(
            f"{m['unit']} {m['row']} of {progress['rows_total']}: {m['measured']}"
            for m in progress["milestones"]) + ".")
    for tip in tips_mod.tips(cir, f.result, twin, f.text, f.terminology):
        helpful.append(f"{tip.title}. {tip.text}")
    if helpful:
        _flow_card(t, "HELPFUL NOTES", helpful, fill=SAGE)
    if f.family == AMIGURUMI:
        _flow_card(t, "EYE OPTIONS", f.eye_options(), fill=CREAM)
    if f.childrens is not None:
        rendered = P.childrens_statements(cir, twin, f.childrens)
        if rendered.unrenderable:
            f.block("child-safety statements cannot be rendered: " + "; ".join(
                f"{k}: {v}" for k, v in sorted(rendered.unrenderable.items())), "notes")
        body = [P.CHILDRENS_INTRO]
        for key in rendered.required:
            if key not in rendered.text:
                continue
            body.append(rendered.headings[key] + ".")
            body.extend(b for b in rendered.text[key].split("\n") if b.strip())
            cite = rendered.citations.get(key)
            body.append(cite if cite else "Source: none. This is Brambleloop Studio's own "
                                          "practice rather than a published rule.")
        t.prose.append(P.CHILDRENS_HEADING)
        _flow_card(t, "SAFETY / AGE / USE NOTES", body, fill=PAPER, stroke=RULE,
                   title_color=ROSE, size=MIN_PT + 0.5)


def _gallery_cell(t: _T, x: float, top: float, slot: dict | None, n: int, label: str) -> None:
    t.card(x, top, 253, 205, fill=CREAM)
    if slot is not None:
        t.image(slot["jpeg"], x + 7, top + 8, 239, 160, fit="cover", radius=7,
                figure={"kind": "certified_frame", "slot": slot["slot"],
                        "position": slot["position"], "frame_sha256": slot["frame_sha256"],
                        "rendition_sha256": slot["rendition_sha256"]})
        _chip(t, x + 15, top + 143, slot["chip"])
    else:
        t.card(x + 7, top + 8, 239, 160, fill=SLOT, radius=7)
        t.text(x + 126, top + 90, "AWAITING CERTIFIED GALLERY", SANS_BOLD, MIN_PT, INK,
               align="centre", track=1.0)
    t.text(x + 11, top + 192, f"{n:02d}  {label}", SANS_BOLD, MIN_PT, INK, track=0.8)


def _gallery(t: _T, f: _Facts, slots: list[dict]) -> list[dict]:
    t.section_page("gallery")
    t.para(47, 194, CONTENT_W, GALLERY_DISCLOSURE, size=MIN_PT, color=BROWN, leading=12)
    by = {s["slot"]: s for s in slots}
    placed = []
    pos = [(47, 254), (314, 254), (47, 476), (314, 476)]
    for i, (slot, label) in enumerate(GALLERY_SLOTS[:4]):
        _gallery_cell(t, *pos[i], by.get(slot), i + 1, label)
        if slot in by:
            placed.append(dict({k: v for k, v in by[slot].items() if k != "jpeg"},
                               page=t.pages))
    t.text(48, 700, "MORE IMAGES  /  FILED IN THE DIGITAL LISTING GALLERY", SANS_BOLD, MIN_PT,
           ROSE, track=1.4)
    t.section_page("gallery_continued")
    pos = [(47, 250), (314, 250), (47, 469)]
    for i, (slot, label) in enumerate(GALLERY_SLOTS[4:]):
        _gallery_cell(t, *pos[i], by.get(slot), i + 5, label)
        if slot in by:
            placed.append(dict({k: v for k, v in by[slot].items() if k != "jpeg"},
                               page=t.pages))
    return placed


def _about(t: _T, f: _Facts) -> None:
    t.section_page("about")
    banner = _owner_art(_CA.STOREFRONT_BANNER, BANNER_PX)
    t.image(banner, 47, 200, 520, 208, fit="contain", radius=0,
            figure={"kind": "owner_banner",
                    "source": "brand/owner_source/brambleloop_owner_banner_canonical.png",
                    "sha256": _art_sha(_CA.STOREFRONT_BANNER, BANNER_PX)})
    t.top = 422
    # The owner's studio blurb, then the premium standard's brand paragraphs: a brand, never
    # a person (PDF_STRUCTURE_STANDARD honest-only rules; the banner's model is not a designer).
    _flow_card(t, "PATTERNS FOR A MORE HANDMADE LIFE",
               [STUDIO_BLURB] + list(P._std.ABOUT_PARAGRAPHS), fill=CREAM, title_color=ROSE,
               size=MIN_PT + 0.5, gap=4, leading=13.5)
    _flow_card(t, "QUESTIONS ABOUT YOUR PATTERN?", [SUPPORT_TEXT, P.support_scope(f.cir)],
               fill=PAPER, stroke=RULE, title_color=ROSE)


def _copyright(t: _T, f: _Facts, designer: str) -> None:
    cir = f.cir
    t.section_page("copyright")
    t.top = 223
    lines = [ln for ln in P.licence_paragraphs() if ln.strip()]
    body = []
    for i, line in enumerate(lines):
        body.append(("• " + line[2:]) if line.startswith("- ") else line)
    body += [f"{P._std.DISCLAIMER_HEADING}.", P._std.DISCLAIMER]
    _flow_card(t, "YOUR PATTERN LICENCE", body, fill=CREAM, size=MIN_PT + 0.5, gap=3,
               leading=13.5)
    year = f.released_on.year
    credit = "" if designer == P.COPYRIGHT_HOLDER else f" Designed by {designer}."
    remember = [PLEASE_REMEMBER, P.AI_DISCLOSURE, P.physical_status(f.twin),
                f"© {year} {P.COPYRIGHT_HOLDER}. All rights reserved.{credit} "
                f"Pattern {cir.slug}@{cir.version}, released {f.released_on.isoformat()}, "
                f"{f.terminology} terms; this edition is {{pages}} pages. Typefaces: Lato and "
                f"Noto Serif Display (SIL Open Font License 1.1)."]
    remember[-1] = remember[-1].replace("{pages}", str(t.total_pages or t.pages))
    _flow_card(t, "PLEASE REMEMBER", remember, fill=PAPER, stroke=RULE, title_color=ROSE,
               size=MIN_PT, gap=3, leading=12.5)
    h = 105
    t.need(h)
    t.card(47, t.top, 520, h, fill=FOREST)
    t.card(57, t.top + 22, 66, 59, fill=CREAM, radius=4)
    t.image(_owner_art(_CA.HERO_LOGO, THANKS_LOGO_PX), 58, t.top + 23, 64, 57,
            figure={"kind": "owner_logo", "use": "thank_you",
                    "sha256": _art_sha(_CA.HERO_LOGO, THANKS_LOGO_PX)})
    t.text(143, t.top + 37, "BRAMBLELOOP STUDIO", SANS_BOLD, MIN_PT, ON_FOREST, track=1.8)
    t.text(143, t.top + 66, THANK_YOU, SERIF, 11.5, ON_FOREST)
    t.top += h + 14


# ---- the deterministic audit of a built template PDF --------------------------------------

_ROW_LABEL = re.compile(r"(?m)^\s*(?:Rnds?|Rows?|Rounds?)\s+\d+[^:\n]{0,60}:")
_CAPS_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z0-9 /&+.,'-]{2,}\]")


@lru_cache(maxsize=1)
def template_placeholders(root=None) -> tuple[str, ...]:
    """Every bracketed placeholder the owner's template prints, read from the template
    itself (e.g. "[Skill level]", "[X sts]"). None of them may reach a customer PDF."""
    from pathlib import Path

    import pypdf

    base = Path(root) if root else Path(__file__).resolve().parents[3]
    reader = pypdf.PdfReader(str(base / TEMPLATE_PATH))
    found = set()
    for page in reader.pages:
        text = re.sub(r"\s+", " ", page.extract_text() or "")
        found.update(m.group(0) for m in re.finditer(r"\[[^\[\]]{1,80}\]", text))
    return tuple(sorted(found))


def _page_titles() -> dict[str, str]:
    return {k: f"{num} / {kicker}" for k, num, kicker, _t in SECTIONS if num}


def audit(pdf_bytes: bytes, *, expected_gallery: list[dict] | None = None) -> dict:
    """Deterministic checks of a built template PDF, from its bytes (never from the layout's
    report of itself). Each check is PASS / FAIL / UNKNOWN; the verdict is PASS only when all
    PASS. UNKNOWN is never PASS.

    * page_order: the template's section sequence, every section present, in order;
    * logo_cover / logo_headers: the canonical logo's renditions embedded on the cover and
      on every body page's header;
    * gallery: the seven certified renditions on the gallery pages (with `expected_gallery`,
      the exact sha256s, in slot order);
    * no_placeholders: none of the template's own bracketed placeholders, and no all-caps
      bracket placeholder (crochet repeat brackets such as "[sc, inc] x 6" are notation);
    * no_template_marker: the template's MASTER LAYOUT marker is absent;
    * stitch_counts: every Row/Round label is followed by its count before the next label."""
    import pypdf

    checks: list[dict] = []

    def check(name, ok, why="", **kw):
        status = "PASS" if ok is True else "FAIL" if ok is False else "UNKNOWN"
        checks.append({"check": name, "status": status, "why": "" if ok is True else why, **kw})

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            imgs = []
            xobjs = ((page.get("/Resources") or {}).get("/XObject") or {})
            xobjs = xobjs.get_object() if hasattr(xobjs, "get_object") else xobjs
            for _name, ref in (xobjs or {}).items():
                obj = ref.get_object()
                if obj.get("/Subtype") != "/Image":
                    continue
                try:
                    data = obj.get_data()
                except Exception:  # noqa: BLE001
                    data = b""
                filters = obj.get("/Filter")
                filters = [str(x) for x in (filters if isinstance(filters, list) else [filters])
                           if x is not None]
                imgs.append({"sha256": hashlib.sha256(data).hexdigest(),
                             "dct": "/DCTDecode" in filters,
                             "px": (int(obj.get("/Width") or 0), int(obj.get("/Height") or 0))})
            pages.append({"text": text, "flat": re.sub(r"\s+", " ", text), "images": imgs})
    except Exception as exc:  # noqa: BLE001 - unreadable is never a pass
        return {"verdict": "UNKNOWN", "checks": [{"check": "readable", "status": "UNKNOWN",
                                                   "why": f"{type(exc).__name__}: {exc}"}]}
    # page order
    titles = _page_titles()
    seq = []
    for p in pages[1:]:
        key = next((k for k, v in titles.items() if p["flat"].find(v) != -1
                    and (k != "gallery" or "CONTINUED GALLERY" not in p["flat"])), None)
        seq.append(key)
    order = [k for k in SECTION_ORDER if k != "cover"]
    collapsed = [k for i, k in enumerate(seq) if i == 0 or k != seq[i - 1]]
    check("page_order", collapsed == order,
          f"sections read {collapsed}, template order is {order}", read=collapsed)
    # logo
    fp = logo_fingerprints()
    cover_ok = bool(pages) and any(im["sha256"] == fp["cover"] for im in pages[0]["images"])
    check("logo_cover", cover_ok, "the cover does not embed the canonical logo rendition")
    missing = [i + 2 for i, p in enumerate(pages[1:])
               if not any(im["sha256"] == fp["header"] for im in p["images"])]
    check("logo_headers", not missing and len(pages) > 1,
          f"pages without the header logo: {missing}", pages=len(pages) - 1)
    thanks = any(im["sha256"] == fp["thanks"] for im in pages[-1]["images"]) if pages else False
    check("logo_thank_you", thanks, "the thank-you block does not embed the logo")
    # gallery
    gal_pages = [p for p, k in zip(pages[1:], seq) if k in ("gallery", "gallery_continued")]
    found = [im["sha256"] for p in gal_pages for im in p["images"]
             if im["sha256"] not in (fp["header"], fp["thanks"], fp["cover"])]
    if expected_gallery is not None:
        want = [g["rendition_sha256"] for g in expected_gallery]
        got = [w for w in want if w in found]
        check("gallery", len(want) == GALLERY_FRAMES and got == want,
              f"{len(got)} of {GALLERY_FRAMES} certified gallery images found", count=len(got))
    else:
        check("gallery", len(set(found)) == GALLERY_FRAMES,
              f"{len(set(found))} gallery images, {GALLERY_FRAMES} required",
              count=len(set(found)))
    # photographs: every JPEG in the document is a certified gallery rendition
    if expected_gallery is not None:
        allowed = {g["rendition_sha256"] for g in expected_gallery}
        strays = sorted({i + 1 for i, p in enumerate(pages) for im in p["images"]
                         if im["dct"] and im["sha256"] not in allowed})
        check("no_uncertified_photos", not strays,
              f"JPEG images that are not certified renditions on pages {strays}")
    # placeholders and marker
    alltext = "\n".join(p["flat"] for p in pages)
    bad = [ph for ph in template_placeholders() if ph in alltext]
    bad += [m.group(0) for m in _CAPS_PLACEHOLDER.finditer(alltext)]
    check("no_placeholders", not bad, f"placeholders printed: {sorted(set(bad))[:5]}")
    marker = re.sub(r"\s+", " ", TEMPLATE_MARKER)
    check("no_template_marker", marker not in alltext and "MASTER LAYOUT" not in alltext,
          "the template marker is printed")
    # stitch counts
    body = "\n".join(p["text"] for p, k in zip(pages[1:], seq) if k == "pattern")
    labels = list(_ROW_LABEL.finditer(body))
    lacking = []
    for i, m in enumerate(labels):
        end = labels[i + 1].start() if i + 1 < len(labels) else len(body)
        if not _ANY_COUNT.search(body[m.end():end]):
            lacking.append(m.group(0).strip())
    check("stitch_counts", bool(labels) and not lacking,
          f"{len(lacking)} of {len(labels)} rows lack a count, e.g. {lacking[:3]}"
          if labels else "no row labels found", rows=len(labels))
    statuses = [c["status"] for c in checks]
    verdict = "FAIL" if "FAIL" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
    return {"verdict": verdict, "pages": len(pages), "sections": seq, "checks": checks,
            "failed": [c["check"] for c in checks if c["status"] == "FAIL"]}


# ---- the build switch ------------------------------------------------------------------------

def build_customer_pdf(cir: CIR, *, layout: str | None = None, db=None, **kw):
    """The one entry point that honours the layout switch (`runtime.release.PDF_LAYOUT`).

    Under the template a release's gallery is read from its valid listing-set certificate
    (`gallery_from_release`) when the caller has a database and passed none; no complete
    certified gallery is GalleryAwaiting ("awaiting gallery"), never a PDF with empty slots."""
    if layout is None:
        from ..runtime.release import PDF_LAYOUT as layout  # noqa: N811
    if layout == "template":
        allowed = {"terminology", "twin", "released_on", "gallery", "proof", "designer",
                   "childrens", "family"}
        if kw.get("gallery") is None and db is not None and not kw.get("proof"):
            kw["gallery"] = gallery_from_release(db, cir.slug, cir.version)
        return build_template_pdf(cir, **{k: v for k, v in kw.items() if k in allowed})
    if layout != "engine":
        raise ValueError(f"unknown PDF layout {layout!r}")
    kw.pop("gallery", None)
    kw.pop("proof", None)
    kw.pop("family", None)
    return P.build_pattern_pdf(cir, **kw)


# ---- test doubles (proof builds only) --------------------------------------------------------

def test_double_gallery(label: str = "") -> list[dict]:
    """Seven deterministic stub frames, every one flagged `test_double`. A document built with
    them is `proof_test_double` -- marked NOT CUSTOMER-READY on every page and labelled TEST
    DOUBLE on every image -- and is never a customer PDF. For layout proofs and tests only."""
    from PIL import Image, ImageDraw, ImageFont

    out = []
    tints = [(198, 207, 191), (226, 214, 201), (214, 200, 196), (205, 214, 214),
             (222, 222, 205), (210, 202, 214), (232, 226, 214)]
    font_path = pdf_fonts.verified_path("Lato-Bold.ttf")
    for n, (slot, name) in enumerate(GALLERY_SLOTS, start=1):
        img = Image.new("RGB", (1200, 900), tints[n - 1])
        d = ImageDraw.Draw(img)
        for k in range(0, 1200, 60):
            d.line([(k, 0), (k + 300, 900)], fill=tuple(max(0, c - 14) for c in tints[n - 1]),
                   width=6)
        big = ImageFont.truetype(str(font_path), 44)
        small = ImageFont.truetype(str(font_path), 34)
        d.rectangle([200, 340, 1000, 560], fill=(254, 252, 249))
        d.text((230, 370), f"TEST DOUBLE {n}", font=big, fill=(47, 62, 51))
        d.text((230, 440), f"{name.lower()}, not a product image {label}".strip(), font=small,
               fill=(127, 104, 81))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=False)
        data = buf.getvalue()
        out.append({"position": n, "role": slot, "sha256": hashlib.sha256(data).hexdigest(),
                    "data": data, "kind": "test_double", "test_double": True})
    return out
