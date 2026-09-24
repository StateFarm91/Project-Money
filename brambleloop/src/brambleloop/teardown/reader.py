"""Reading a purchased pattern without keeping a word of it.

The owner's MJs protocol of 2026-09-21 is two instructions that pull in opposite directions,
and the whole design of this module is the reconciliation:

  *ingest the entire purchased pattern, every page*, and analyse materials, gauge, sizing,
  construction, shaping, assembly, finishing, charts and instructional structure —

  and *purchased competitor content is benchmark evidence, not generation source material.
  Do not copy protected expression, row sequences, stitch counts, charts, diagrams,
  photography or pattern text into Brambleloop products.*

A reader that returns the document's text satisfies the first and makes the second a matter
of everyone downstream being careful. Careful is not a mechanism, so this reader never returns
text at all.

**Nothing leaves here that this repository did not already contain.** The page text is held in
memory for the length of one function and is compared against closed vocabularies defined
below -- section cues, standard stitch abbreviations, piece names, size labels -- plus
numbers. Every string in the result is one of ours or a digit. There is no code path that
emits a substring of the document, which is a stronger guarantee than a filter: a filter has
to recognise expression to refuse it, and this cannot pass it on in the first place.

**Not found is not absent.** A PDF whose pages are scanned images yields no text, and a
section this reader did not see in a document it could not read is unmeasured. So the presence
answers this hands to the audit schedule are withheld for the unreadable rather than answered
false -- the same three-valued discipline the canonical-model floors needed, for the same
reason: a verdict computed from the absence of evidence is the one that reads as a pass.

**The reader is proven on a document this company made.** `self_test()` renders a real
Brambleloop pattern PDF, puts it in a temporary library root, reads it back through
`library.retrieve()` and checks that it found every page and the sections that document is
known to contain. That is the only end-to-end proof available before anything is purchased,
and it exercises the real path: the quarantine, the role refusal, the page loop, the cues.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .library import ANALYST_ROLES, retrieve

ANALYST_ROLE = "teardown_analyst"
assert ANALYST_ROLE in ANALYST_ROLES


class ReaderUnavailable(RuntimeError):
    """No PDF library is installed, so nothing in this environment can read a page."""


class PageRefused(Exception):
    """The file is not a PDF this reader can open at all."""


# ---------------------------------------------------------------------------
# The closed vocabularies. Everything the reader can say is in here.
#
# These are generic English headings and standard crochet abbreviations -- the words any
# pattern in the category uses. They are ours in the sense that matters: they were written
# here, they are matched against the document rather than taken from it, and a cue that fires
# reports its own name, never the line that matched it.

SECTION_CUES: dict[str, tuple[str, ...]] = {
    "table_of_contents": ("contents", "in this pattern", "what's inside", "what is inside"),
    "quick_start": ("quick start", "before you begin", "getting started", "start here",
                    "at a glance"),
    "materials": ("materials", "you will need", "supplies", "what you need", "yarn"),
    "gauge": ("gauge", "tension", "swatch"),
    "sizing": ("size", "sizes", "sizing", "finished measurements", "measurements",
               "dimensions"),
    # "us terms" and "uk terms" were cues here and they are not. A pattern that says which
    # terminology it is written in has stated a terminology, not published a key -- and this
    # company's own document proved it: its instructions heading reads "Instructions (US
    # terms)", so `self_test()` reported an `abbreviations` section in a PDF that contained
    # no abbreviations at all, and the same cue would have credited a competitor with a key
    # they had not written. A check that cannot fail on the document it is pointed at is not
    # measuring the document.
    "abbreviations": ("abbreviation", "stitch key", "terms used", "stitches used",
                      "key to the chart", "symbol key"),
    "technique_explanations": ("special stitches", "special stitch", "techniques",
                               "stitch guide", "how to work", "tutorial"),
    "construction_overview": ("construction", "pattern notes", "how it is made",
                              "how it's made", "overview", "notes"),
    "charts": ("chart", "diagram", "symbol key", "legend", "graph"),
    "assembly": ("assembly", "assemble", "seaming", "joining", "join the", "putting it "
                 "together"),
    "finishing": ("finishing", "weave in", "fasten off", "fastening off", "edging",
                  "border"),
    "blocking": ("blocking", "block the", "wet block", "steam block"),
    "troubleshooting": ("troubleshooting", "common mistakes", "if your", "problem solving",
                        "faq", "frequently asked"),
    "credits": ("designed by", "photography", "tester", "testers", "credits",
                "with thanks"),
    "rights_terms": ("copyright", "all rights reserved", "terms of use", "personal use",
                     "may not be resold", "redistribut", "licence", "license"),
    "support": ("contact", "questions", "get in touch", "message me", "support",
                "help@", "email"),
    "cross_sell": ("more patterns", "other patterns", "my shop", "etsy.com", "instagram",
                   "follow", "ravelry", "pinterest"),
}

# Elements of the PDF-architecture schedule a text reader cannot settle either way, listed
# rather than guessed at. A cover is a design judgement about a first page and the row
# instructions are found by shape below, not by a heading.
READER_CANNOT_SETTLE: frozenset[str] = frozenset({"cover"})

# Standard crochet abbreviations, US and UK. Matched as whole tokens: "dc" in "dc" and not in
# "abducted". What is reported is which of these appeared, which is the pattern's stitch
# vocabulary -- a fact about its difficulty and its house style, and not its instructions.
STITCH_VOCABULARY: tuple[str, ...] = (
    "ch", "sl st", "ss", "sc", "hdc", "dc", "tr", "dtr", "trtr", "htr", "ttr",
    "inc", "dec", "sk", "sp", "st", "sts", "yo", "yoh", "blo", "flo",
    "fpdc", "bpdc", "fpsc", "bpsc", "fptr", "bptr", "mc", "cc", "rep", "rs", "ws",
    "beg", "rem", "tog", "psc", "bobble", "popcorn", "puff", "cluster", "shell", "picot",
    "magic ring", "magic circle", "foundation chain", "turning chain",
)

# Piece names, for relating written construction to the advertised object. Same rule: the
# reader reports which of these it saw, never the sentence it saw them in.
PIECE_VOCABULARY: tuple[str, ...] = (
    "back", "front", "sleeve", "cuff", "collar", "yoke", "body", "panel", "square",
    "motif", "strap", "handle", "base", "side", "brim", "crown", "edging", "border",
    "pocket", "hood", "gusset", "button band", "tie", "tassel", "pompom", "lining",
    "ear", "leg", "arm", "head", "tail", "snout", "muzzle",
)

SIZE_LABELS: tuple[str, ...] = (
    "xxs", "xs", "s", "m", "l", "xl", "xxl", "2xl", "3xl", "4xl", "5xl", "6xl",
    "newborn", "baby", "toddler", "child", "adult", "preemie",
)

# What a shaped garment or vessel of each advertised form is expected to contain, so that
# "the construction corresponds to the object" is a check rather than an impression. Absent
# forms are unverifiable rather than failing: this company does not get to decide that a
# designer's cardigan is wrong because it is worked in one piece.
FORM_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    "cardigan": ("front", "back", "sleeve"),
    "sweater": ("front", "back", "sleeve"),
    "pullover": ("front", "back", "sleeve"),
    "beanie": ("crown", "brim"),
    "hat": ("crown", "brim"),
    "bag": ("base", "handle"),
    "basket": ("base", "side"),
    # Deliberately empty. A blanket is one piece and a border is a design choice, so
    # expecting one would report a discrepancy against every borderless blanket ever
    # published -- including this company's own, which is how the mistake was caught.
    "blanket": (),
    "amigurumi": ("head", "body"),
}

_ROW_LINE = re.compile(r"^\s*(?:row|rnd|round)s?\s*\d+", re.I | re.M)
_ROUND_LINE = re.compile(r"^\s*(?:rnd|round)s?\s*\d+", re.I | re.M)
_STITCH_COUNT = re.compile(r"[(\[—-]\s*\d+\s*(?:sts?|stitches|dc|sc|hdc|tr)\b", re.I)
_REPEAT_NOTATION = re.compile(r"(?:rep(?:eat)? from|\*\s*to\s*\*|\*\s*rep)", re.I)
_GAUGE_STATEMENT = re.compile(
    r"\d+\s*(?:sts?|stitches|dc|sc|hdc|rows?)\s*(?:x|by|and|×)\s*\d+\s*"
    r"(?:rows?|sts?|stitches)", re.I)
_HOOK_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.I)
_YARDAGE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(yds?|yards?|m|metres?|meters?)\b", re.I)
_LENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(?:in\b|inch|inches|\"|cm\b)", re.I)
_COLOUR_CHANGE = re.compile(r"(?:change to|switch to|with (?:mc|cc)|join .{0,12}colou?r)", re.I)
_TOKEN = re.compile(r"[a-z]+(?: st)?")

# How long a line can be and still be a heading. A piece is named by a heading -- "Back",
# "Sleeve (make 2)" -- and mentioned in prose everywhere else, so scanning whole pages for
# piece words finds "the wrong side", "back through a few stitches" and "the side seam" and
# concludes the document describes three pieces. It did: this module reported exactly that
# about a one-piece blanket, and then reported a discrepancy because a three-piece document
# had no assembly section.
_HEADING_MAX_CHARS = 40
_HEADING_LEADING_TOKENS = 4


def _headings_in(text: str) -> list[str]:
    """The heading-shaped lines of a page, lowercased.

    #152 asks whether each part of a pattern exists *as its own addressable section*, and a
    document that says the word "yarn" in a sentence about gauge has not got a materials
    section. Presence is therefore answered from headings; a cue that appears only in prose
    is recorded as a mention and handed to the analyst, who has the page in front of them.
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if line and len(line) <= _HEADING_MAX_CHARS:
            out.append(line.lower())
    return out


def _pieces_in(text: str) -> set[str]:
    """Piece names, taken from heading-shaped lines only."""
    found: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line or len(line) > _HEADING_MAX_CHARS or _ROW_LINE.match(line):
            continue
        low = line.lower()
        leading = _TOKEN.findall(low)[:_HEADING_LEADING_TOKENS]
        head = " ".join(leading)
        for piece in PIECE_VOCABULARY:
            if " " in piece:
                if piece in head:
                    found.add(piece)
            elif piece in leading:
                found.add(piece)
    return found


def available() -> str:
    """Which PDF library this environment has, or an empty string."""
    import importlib.util

    for name in ("pypdf", "PyPDF2", "pdfplumber"):
        if importlib.util.find_spec(name) is not None:
            return name
    return ""


# ---------------------------------------------------------------------------


@dataclass
class Inventory:
    """What one purchased document contains, in this repository's own words.

    Every field is a count, a page number, a measured number or a key from a vocabulary
    above. There is no field that can hold a sentence from the document, which is the point.
    """

    pages: int = 0
    pages_with_text: int = 0
    pages_without_text: list[int] = field(default_factory=list)
    sections: dict[str, list[int]] = field(default_factory=dict)
    mentions: dict[str, list[int]] = field(default_factory=dict)
    stitch_vocabulary: list[str] = field(default_factory=list)
    pieces: list[str] = field(default_factory=list)
    size_labels: list[str] = field(default_factory=list)
    instruction_lines: int = 0
    round_lines: int = 0
    stitch_counts: int = 0
    repeat_notations: int = 0
    colour_changes: int = 0
    gauge_statements: int = 0
    hook_sizes_mm: list[float] = field(default_factory=list)
    yardage_figures: list[float] = field(default_factory=list)
    length_figures: int = 0
    images: int = 0
    pages_with_images: list[int] = field(default_factory=list)
    encrypted: bool = False

    @property
    def fully_readable(self) -> bool:
        """Every page gave up text. Only then is a missing section actually missing."""
        return self.pages > 0 and not self.pages_without_text

    def to_dict(self) -> dict:
        return {
            "pages": self.pages,
            "pages_with_text": self.pages_with_text,
            "pages_without_text": list(self.pages_without_text),
            "fully_readable": self.fully_readable,
            "every_page_examined": self.pages > 0,
            "sections": {k: list(v) for k, v in sorted(self.sections.items())},
            "mentions": {k: list(v) for k, v in sorted(self.mentions.items())
                         if k not in self.sections},
            "stitch_vocabulary": sorted(self.stitch_vocabulary),
            "pieces": sorted(self.pieces),
            "size_labels": sorted(self.size_labels),
            "instruction_lines": self.instruction_lines,
            "round_lines": self.round_lines,
            "stitch_counts": self.stitch_counts,
            "repeat_notations": self.repeat_notations,
            "colour_changes": self.colour_changes,
            "gauge_statements": self.gauge_statements,
            "hook_sizes_mm": sorted(self.hook_sizes_mm),
            "yardage_figures": sorted(self.yardage_figures),
            "length_figures": self.length_figures,
            "images": self.images,
            "pages_with_images": list(self.pages_with_images),
            "encrypted": self.encrypted,
            "holds_no_text": ("every value here is a count, a page number, a measured "
                              "number or a key from this module's own vocabularies"),
        }


def _pages(data: bytes) -> tuple[list[str], list[int], bool]:
    """Page text, per-page image counts, and whether the file was encrypted."""
    import io

    name = available()
    if not name:
        raise ReaderUnavailable(
            "no PDF library is installed, so no page can be read. The teardown protocol "
            "requires every page ingested; add `pypdf` to requirements.txt")
    if name in ("pypdf", "PyPDF2"):
        module = __import__(name)
        try:
            doc = module.PdfReader(io.BytesIO(data))
        except Exception as e:  # noqa: BLE001 - a malformed file is a refusal, not a crash
            raise PageRefused(f"this file could not be opened as a PDF: {e}") from e
        encrypted = bool(getattr(doc, "is_encrypted", False))
        if encrypted:
            try:
                doc.decrypt("")
            except Exception:  # noqa: BLE001
                pass
        texts: list[str] = []
        images: list[int] = []
        for page in doc.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one bad page must not lose the other forty
                texts.append("")
            try:
                images.append(len(page.images))
            except Exception:  # noqa: BLE001
                images.append(0)
        return texts, images, encrypted

    import pdfplumber  # pragma: no cover - only if pypdf is ever dropped

    with pdfplumber.open(io.BytesIO(data)) as doc:  # pragma: no cover
        texts = [(p.extract_text() or "") for p in doc.pages]
        images = [len(p.images or []) for p in doc.pages]
    return texts, images, False  # pragma: no cover


def inventory(data: bytes) -> Inventory:
    """Read every page and record only what the vocabularies above can name."""
    texts, image_counts, encrypted = _pages(data)
    inv = Inventory(pages=len(texts), encrypted=encrypted)

    stitches: set[str] = set()
    pieces: set[str] = set()
    sizes: set[str] = set()
    for number, (raw, image_count) in enumerate(zip(texts, image_counts), start=1):
        if image_count:
            inv.images += image_count
            inv.pages_with_images.append(number)
        text = raw.strip()
        if not text:
            inv.pages_without_text.append(number)
            continue
        inv.pages_with_text += 1
        low = text.lower()

        headings = _headings_in(text)
        for key, cues in SECTION_CUES.items():
            if any(any(cue in h for cue in cues) for h in headings):
                inv.sections.setdefault(key, []).append(number)
            elif any(cue in low for cue in cues):
                inv.mentions.setdefault(key, []).append(number)

        inv.instruction_lines += len(_ROW_LINE.findall(text))
        inv.round_lines += len(_ROUND_LINE.findall(text))
        inv.stitch_counts += len(_STITCH_COUNT.findall(text))
        inv.repeat_notations += len(_REPEAT_NOTATION.findall(text))
        inv.colour_changes += len(_COLOUR_CHANGE.findall(text))
        inv.gauge_statements += len(_GAUGE_STATEMENT.findall(text))
        inv.length_figures += len(_LENGTH.findall(text))

        for value in _HOOK_MM.findall(text):
            try:
                mm = round(float(value), 2)
            except ValueError:  # pragma: no cover
                continue
            if 1.0 <= mm <= 25.0 and mm not in inv.hook_sizes_mm:
                inv.hook_sizes_mm.append(mm)
        for value, unit in _YARDAGE.findall(text):
            try:
                amount = float(value.replace(",", ""))
            except ValueError:  # pragma: no cover
                continue
            if unit.lower().startswith("m") and amount < 25:
                # "3 m" beside a hook size is a measurement, not a yardage. Skipping it is
                # better than recording a skein of three metres.
                continue
            if amount >= 25 and amount not in inv.yardage_figures:
                inv.yardage_figures.append(amount)

        tokens = set(_TOKEN.findall(low))
        for abbrev in STITCH_VOCABULARY:
            if abbrev in tokens or (" " in abbrev and abbrev in low):
                stitches.add(abbrev)
        pieces |= _pieces_in(text)
        for label in SIZE_LABELS:
            if label in tokens:
                sizes.add(label)

        if inv.instruction_lines and "row_round_instructions" not in inv.sections:
            inv.sections.setdefault("row_round_instructions", []).append(number)

    inv.stitch_vocabulary = sorted(stitches)
    inv.pieces = sorted(pieces)
    inv.size_labels = sorted(sizes)
    return inv


def read(relative_path: str, *, role: str = ANALYST_ROLE, env: dict[str, str] | None = None,
         ref: str = "") -> dict:
    """Ingest one purchased file, every page, through the quarantine's only reader.

    This is the call `readiness.retrieve_callers()` looks for, and it is the whole reason
    that check reported not-ready: `retrieve()` existed and nothing in the system used it,
    so the laboratory could file a purchase and never open it.
    """
    data = retrieve(relative_path, role, env=env)
    inv = inventory(data)
    return {"ref": ref, "file": relative_path, "read_by": available(),
            "role": role, **inv.to_dict()}


# ---------------------------------------------------------------------------
# What the reader hands to the audit schedules


def architecture_answers(inv: Inventory | dict) -> dict:
    """Presence answers for the #152 schedule, with the unreadable withheld.

    Returns the answers it can defend and names the rest. A found section is a found section
    however incomplete the reading was; a section not found in a document with unreadable
    pages is unmeasured, and answering it `false` would report an absence this reader never
    established.
    """
    from . import audits

    data = inv.to_dict() if isinstance(inv, Inventory) else dict(inv)
    sections = data.get("sections") or {}
    mentions = data.get("mentions") or {}
    fully = bool(data.get("fully_readable"))

    answers: dict[str, dict] = {}
    withheld: list[str] = []
    mentioned_not_headed: list[str] = []
    for element in audits.PDF_ARCHITECTURE.element_keys:
        if element in READER_CANNOT_SETTLE:
            withheld.append(element)
        elif element in sections:
            answers[element] = {"score": True, "pages": list(sections[element]),
                                "source": "reader"}
        elif element in mentions:
            # The topic is in the document and not as a heading. #152 asks whether it exists
            # as its own addressable section, and a licence paragraph inside the support
            # page is a different answer from a rights section -- so the analyst decides,
            # with the pages named.
            withheld.append(element)
            mentioned_not_headed.append(element)
        elif fully:
            answers[element] = {"score": False, "source": "reader"}
        else:
            withheld.append(element)

    return {
        "answers": answers,
        "withheld": sorted(withheld),
        "mentioned_but_not_a_heading": {k: list(mentions[k])
                                        for k in sorted(mentioned_not_headed)},
        "why_withheld": (
            "a section this reader did not find in a document it could not fully read is "
            "unmeasured, not absent, and a topic that appears only in prose is not a "
            "section. The analyst answers these from the page"),
        "complete": not withheld,
    }


def analysis(inv: Inventory | dict) -> dict:
    """The owner's enumerated analysis dimensions, each measured or explicitly not.

    Three verdicts, never two: `observed` when the document evidences it, `absent` only when
    every page was read and it is not there, and `unmeasurable` when the reading itself was
    incomplete. The third is the one that keeps this honest.
    """
    data = inv.to_dict() if isinstance(inv, Inventory) else dict(inv)
    fully = bool(data.get("fully_readable"))
    # Analysis asks whether the information is in the document; the architecture schedule
    # asks whether it is a section. A materials list inside the gauge page is bad
    # architecture and perfectly good materials information, and conflating the two
    # questions is how a document gets marked down twice for one thing.
    sections = {**(data.get("mentions") or {}), **(data.get("sections") or {})}

    def verdict(present: bool, evidence: dict) -> dict:
        if present:
            return {"verdict": "observed", **evidence}
        if fully:
            return {"verdict": "absent", **evidence}
        return {"verdict": "unmeasurable",
                "why": (f"{len(data.get('pages_without_text') or [])} of {data.get('pages')} "
                        f"pages yielded no text, so this was not established either way"),
                **evidence}

    dimensions = {
        "materials": verdict("materials" in sections,
                             {"pages": sections.get("materials", [])}),
        "yarn": verdict(bool(data.get("yardage_figures")),
                        {"yardage_figures": data.get("yardage_figures")}),
        "hook": verdict(bool(data.get("hook_sizes_mm")),
                        {"hook_sizes_mm": data.get("hook_sizes_mm")}),
        "gauge": verdict(bool(data.get("gauge_statements")) or "gauge" in sections,
                         {"gauge_statements": data.get("gauge_statements")}),
        "sizing": verdict(bool(data.get("size_labels")) or "sizing" in sections,
                          {"size_labels": data.get("size_labels")}),
        "finished_measurements": verdict(bool(data.get("length_figures")),
                                         {"measurements_stated": data.get("length_figures")}),
        "yardage": verdict(bool(data.get("yardage_figures")),
                           {"figures": len(data.get("yardage_figures") or [])}),
        "stitch_vocabulary": verdict(bool(data.get("stitch_vocabulary")),
                                     {"stitches": data.get("stitch_vocabulary")}),
        "construction": verdict("construction_overview" in sections,
                                {"pages": sections.get("construction_overview", [])}),
        "shaping": verdict(any(s in (data.get("stitch_vocabulary") or [])
                               for s in ("inc", "dec", "tog")),
                           {"shaping_vocabulary": [s for s in ("inc", "dec", "tog")
                                                   if s in (data.get("stitch_vocabulary") or [])]}),
        "row_round_logic": verdict(bool(data.get("instruction_lines")),
                                   {"instruction_lines": data.get("instruction_lines"),
                                    "round_lines": data.get("round_lines"),
                                    "stitch_counts": data.get("stitch_counts"),
                                    "repeat_notations": data.get("repeat_notations")}),
        "assembly": verdict("assembly" in sections, {"pages": sections.get("assembly", [])}),
        "finishing": verdict("finishing" in sections,
                             {"pages": sections.get("finishing", [])}),
        "charts": verdict("charts" in sections, {"pages": sections.get("charts", [])}),
        "diagrams": verdict("charts" in sections and bool(data.get("pages_with_images")),
                            {"pages_with_images": data.get("pages_with_images")}),
        "progress_photos": verdict(bool(data.get("images")),
                                   {"images": data.get("images"),
                                    "caveat": ("an image on a page is an image; whether it "
                                               "is a progress photograph, a chart or a "
                                               "logo is a judgement this reader does not "
                                               "make")}),
        "troubleshooting": verdict("troubleshooting" in sections,
                                   {"pages": sections.get("troubleshooting", [])}),
        "instructional_structure": verdict(
            len(sections) >= 5,
            {"sections_found": sorted(sections), "section_count": len(sections)}),
    }

    measured = [k for k, v in dimensions.items() if v["verdict"] != "unmeasurable"]
    return {
        "dimensions": dimensions,
        "measured": len(measured),
        "of": len(dimensions),
        "unmeasurable": sorted(k for k, v in dimensions.items()
                               if v["verdict"] == "unmeasurable"),
        "pages": data.get("pages"),
        "note": ("presence and structure, measured. What is good about any of it is the "
                 "analyst's judgement, recorded through audits.observe() -- this reader "
                 "does not score"),
    }


def cross_reference(promises: dict, inv: Inventory | dict) -> dict:
    """Listing promises against the purchased instructions (not against filenames).

    `intake.deliverable_audit` answers what a filename can settle. This answers what only the
    document can: whether the chart the listing promised is inside it, whether the sizes are
    carried, whether the format is what was sold. Same three verdicts, and `unverifiable`
    still never collapses into `kept`.
    """
    data = inv.to_dict() if isinstance(inv, Inventory) else dict(inv)
    sections = {**(data.get("mentions") or {}), **(data.get("sections") or {})}
    fully = bool(data.get("fully_readable"))
    promises = promises or {}

    kept: list[dict] = []
    missing: list[dict] = []
    unverifiable: list[dict] = []

    def settle(claim: str, promised, found: bool, why_unverifiable: str) -> None:
        if promised is None:
            unverifiable.append({"claim": claim, "found_in_document": found,
                                 "why": "the listing never promised this, so there is "
                                        "nothing to compare against"})
        elif promised and found:
            kept.append({"claim": claim})
        elif promised and not found and fully:
            missing.append({"claim": claim,
                            "why": "promised by the listing and not found in a document "
                                   "every page of which was read"})
        elif promised:
            unverifiable.append({"claim": claim, "why": why_unverifiable})
        elif found:
            kept.append({"claim": claim, "note": "delivered although not promised"})
        else:
            kept.append({"claim": claim, "note": "not promised and not delivered"})

    unread = len(data.get("pages_without_text") or [])
    partial = f"{unread} pages could not be read, so its absence is not established"

    settle("has_chart", promises.get("has_chart"), "charts" in sections, partial)
    settle("format", (promises.get("format") or "").lower() in ("pdf", "") or None,
           bool(data.get("pages")), partial)

    if promises.get("has_video") is not None:
        unverifiable.append({
            "claim": "has_video",
            "why": ("a PDF cannot settle whether a video was delivered. "
                    "intake.deliverable_audit answers this one from the manifest")})

    return {
        "kept": kept, "missing": missing, "unverifiable": unverifiable,
        "complete": not unverifiable,
        "source": "the purchased document, read page by page",
        "and_also": ("this extends intake.deliverable_audit rather than replacing it: that "
                     "one answers what arrived, this one answers what is inside it"),
    }


def construction_correspondence(inv: Inventory | dict, *, advertised_form: str = "",
                                advertised_sizes: list[str] | None = None) -> dict:
    """How the written construction relates to the advertised finished object.

    The owner's dimension, and the one with the most room to lie: a pattern that advertises a
    cardigan and instructs a rectangle is the single most expensive thing a buyer can
    discover after paying. So the check is mechanical where it can be -- the pieces the form
    needs, found or not -- and says `unverifiable` everywhere else rather than implying a
    correspondence nobody established.
    """
    data = inv.to_dict() if isinstance(inv, Inventory) else dict(inv)
    fully = bool(data.get("fully_readable"))
    pieces = set(data.get("pieces") or [])
    sections = data.get("sections") or {}
    form = (advertised_form or "").strip().lower()
    expected = FORM_EXPECTATIONS.get(form)

    worked_in_rounds = bool(data.get("round_lines"))
    multi_piece = len(pieces) > 1
    assembly = "assembly" in sections

    findings: list[dict] = []
    if expected is None:
        verdict = "unverifiable"
        findings.append({
            "check": "expected_pieces",
            "result": "unverifiable",
            "why": (f"{advertised_form or 'no form'!r} is not a form this module has an "
                    f"expectation for: {sorted(FORM_EXPECTATIONS)}. A designer's "
                    f"construction is not wrong because this list is short")})
    else:
        found = sorted(p for p in expected if p in pieces)
        absent = sorted(p for p in expected if p not in pieces)
        seamless = worked_in_rounds and not pieces
        if not absent:
            verdict, why = "corresponds", ""
        elif seamless:
            # A basket worked from the centre out in one piece names no base and no side,
            # and it is still a basket. This module said otherwise about this company's own
            # basket pattern, which is how the rule got written: a construction that needs
            # no pieces cannot be missing them.
            verdict = "unverifiable"
            why = ("worked in one piece in the round. A seamless construction names no "
                   "pieces, so the pieces it does not name are not missing")
        elif not fully:
            verdict = "unverifiable"
            why = "some pages could not be read, so this is unestablished"
        else:
            verdict = "discrepancy"
            why = ("every page was read and these were never named, in a document that "
                   "names other pieces or is not worked in the round")
        findings.append({"check": "expected_pieces", "result": verdict,
                         "expected": list(expected), "found": found, "not_found": absent,
                         "seamless": seamless, "why": why})

    if multi_piece and not assembly:
        findings.append({
            "check": "assembly_present",
            "result": "discrepancy" if fully else "unverifiable",
            "why": ("more than one piece is named and no assembly section was found. A "
                    "buyer with pieces and no seaming instructions has an unfinished "
                    "object")})
    else:
        findings.append({"check": "assembly_present",
                         "result": "corresponds" if assembly or not multi_piece else "unverifiable",
                         "pieces_named": sorted(pieces)})

    wanted = [s.strip().lower() for s in (advertised_sizes or []) if s.strip()]
    if wanted:
        have = set(data.get("size_labels") or [])
        carried = sorted(s for s in wanted if s in have)
        uncarried = sorted(s for s in wanted if s not in have)
        findings.append({
            "check": "sizes_carried",
            "result": ("corresponds" if not uncarried else
                       "discrepancy" if fully else "unverifiable"),
            "advertised": wanted, "found": carried, "not_found": uncarried,
            "why": ("" if not uncarried else
                    "a size the listing advertises and the document never labels is the "
                    "grading a buyer paid for")})
    else:
        findings.append({"check": "sizes_carried", "result": "unverifiable",
                         "why": "the listing's advertised sizes were not supplied"})

    results = {f["result"] for f in findings}
    overall = ("discrepancy" if "discrepancy" in results else
               "unverifiable" if "unverifiable" in results else "corresponds")
    return {
        "advertised_form": form or None,
        "verdict": overall,
        "findings": findings,
        "worked_in_rounds": worked_in_rounds,
        "pieces_named": sorted(pieces),
        "never_a_pass_by_default": ("an unreadable page produces `unverifiable`, never "
                                    "`corresponds`"),
    }


# ---------------------------------------------------------------------------
# Proof


SELF_TEST_SLUG = "cloudline-baby-blanket"

# What a Brambleloop pattern PDF is known to contain, and therefore what a reader that works
# must find in it. Deliberately not the full schedule: this proves the path, not that our own
# document is excellent.
SELF_TEST_SECTIONS: tuple[str, ...] = (
    "materials", "gauge", "sizing", "abbreviations", "construction_overview",
    "row_round_instructions", "finishing", "charts",
)

# Topics our own document carries in prose rather than as a heading. Listed because the
# self-test should prove the distinction exists, not paper over it: the licence sits inside
# the support page, so `rights_terms` is a mention and the analyst decides whether that
# counts as a section.
SELF_TEST_MENTIONS: tuple[str, ...] = ("rights_terms",)


# One proof per process, keyed on the thing that can make it come out differently. A
# readiness endpoint and a launch assessment both ask, and rendering a PDF twice a second to
# answer the same question is waste -- but a cache keyed on nothing is how a check becomes a
# label, so the key holds the library the answer depends on.
_PROOF: dict[str, dict] = {}


def self_test() -> dict:
    """Render a real pattern PDF, file it, and read it back through the quarantine.

    The only end-to-end proof available before a benchmark is purchased, and it is a real
    one: a genuine multi-page document, the real `library.retrieve()` with its role refusal,
    the real page loop. If this fails, the laboratory is not ready to receive CA$292 of
    somebody else's work, whatever a status table says.
    """
    import tempfile
    from pathlib import Path

    from ..products.builder import for_slug
    from ..publish.pdf import build_pattern_pdf
    from .library import LIBRARY_ENV, LibraryRefused

    library = available()
    cached = _PROOF.get(library)
    if cached is not None:
        return dict(cached)
    if not library:
        answer = {"ran": False, "ready": False,
                  "why": "no PDF library is installed in this environment"}
        _PROOF[library] = answer
        return dict(answer)

    cir = for_slug(SELF_TEST_SLUG)
    if cir is None:  # pragma: no cover - the catalogue is a constant
        return {"ran": False, "ready": False, "why": f"no CIR for {SELF_TEST_SLUG}"}
    doc = build_pattern_pdf(cir)

    with tempfile.TemporaryDirectory(prefix="reader-selftest-") as tmp:
        root = Path(tmp)
        (root / "selftest").mkdir()
        target = root / "selftest" / "pattern.pdf"
        target.write_bytes(doc.pdf_bytes)
        env = {LIBRARY_ENV: str(root)}

        result = read("selftest/pattern.pdf", env=env, ref="reader-self-test")

        # The quarantine must still refuse the roles it exists to refuse, on the same call
        # path. A reader that works by having been given a role nobody checks is not a
        # quarantine with a reader; it is a hole with a docstring.
        refused = False
        try:
            read("selftest/pattern.pdf", role="crochet_engineer", env=env)
        except LibraryRefused:
            refused = True

        escaped = False
        try:
            read("../escape.pdf", env=env)
        except LibraryRefused:
            escaped = False
        except Exception:  # noqa: BLE001 # pragma: no cover
            escaped = True

    found = [s for s in SELF_TEST_SECTIONS if s in (result.get("sections") or {})]
    absent = [s for s in SELF_TEST_SECTIONS if s not in (result.get("sections") or {})]
    every_page = result.get("pages_with_text") == result.get("pages") and result["pages"] > 1

    # The rest of the path, on the same document, because a reader that reads and hands its
    # inventory to nothing is the defect one layer along: the purchase would be ingested and
    # then not analysed, which is the same folder of unopened files with an extra step.
    measured = analysis(result)
    architecture = architecture_answers(result)
    promises = {"has_chart": True, "format": "PDF", "has_video": True}
    promised = cross_reference(promises, result)
    correspondence = construction_correspondence(
        result, advertised_form="blanket", advertised_sizes=[])

    analysed = (measured["measured"] == measured["of"])
    # The chart promise is kept because this document contains one, and the video promise is
    # unverifiable because a PDF cannot settle it. Both are the right answer, and the second
    # is the one that proves the three verdicts are real rather than decorative.
    promise_path = ([c["claim"] for c in promised["kept"]].count("has_chart") == 1
                    and any(c["claim"] == "has_video" for c in promised["unverifiable"]))
    pieces_check = [f for f in correspondence["findings"]
                    if f["check"] == "expected_pieces"]
    construction_path = (correspondence["verdict"] in ("corresponds", "discrepancy",
                                                       "unverifiable")
                         and bool(pieces_check)
                         and pieces_check[0]["result"] != "discrepancy")

    mention_tier = all(m in architecture["mentioned_but_not_a_heading"]
                       for m in SELF_TEST_MENTIONS)
    ready = bool(every_page and not absent and mention_tier and refused and not escaped
                 and result.get("instruction_lines") and analysed and promise_path
                 and construction_path and architecture["answers"])
    answer = {
        "ran": True,
        "ready": ready,
        "pages": result.get("pages"),
        "pages_with_text": result.get("pages_with_text"),
        "every_page_read": every_page,
        "sections_found": found,
        "sections_not_found": absent,
        "instruction_lines": result.get("instruction_lines"),
        "stitch_vocabulary": result.get("stitch_vocabulary"),
        "quarantine_still_refuses_generation": refused,
        "quarantine_still_refuses_path_escape": not escaped,
        "analysis_dimensions_measured": measured["measured"],
        "analysis_dimensions": measured["of"],
        "analysis_unmeasurable": measured["unmeasurable"],
        "architecture_answers": len(architecture["answers"]),
        "architecture_withheld": architecture["withheld"],
        "mentioned_but_not_a_heading": sorted(
            architecture["mentioned_but_not_a_heading"]),
        "cross_reference": {"kept": [c["claim"] for c in promised["kept"]],
                            "missing": [c["claim"] for c in promised["missing"]],
                            "unverifiable": [c["claim"] for c in promised["unverifiable"]]},
        "construction_verdict": correspondence["verdict"],
        "document": f"a Brambleloop {SELF_TEST_SLUG} pattern, rendered for this test",
        "why_our_own_document": (
            "nothing has been purchased yet, and a readiness claim proved on a file that "
            "does not exist is the claim this check exists to refuse. Our own PDF is an "
            "independent document with a known structure: it was written by the publishing "
            "module, not by this one"),
    }
    _PROOF[library] = answer
    return dict(answer)
