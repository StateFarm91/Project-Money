"""ENG-PLUSH: the child-safety pattern-content gate (D-OWNER-CORE-FAMILIES section 3).

Stuffed animals, baby items and loveys are permanent core families, and the owner's rule is
that child and baby safety is more than embroidered eyes. This gate is that rule in code. It
reads the CIR (what the pattern instructs) and, when given, the customer's rendered text (what
the document says), and every check answers PASS, FAIL or UNKNOWN. **UNKNOWN is never PASS**:
the verdict is PASS only when every check passes, FAIL when any fails, and HELD when the only
thing missing is evidence nothing in this system can supply yet.

Construction checks (from the CIR):

  FEATURES_EMBROIDERED  no safety eye, button, bead, bell, pellet or other hard part is named
                        in any material, note or instruction; a toy with a face states the
                        face is embroidered with yarn. Embroidered eyes alone pass THIS check
                        only -- the verdict needs every other check too. ENG-PLUSH-FIX (review
                        M1) inverts the eye/nose rule: ANY eye or nose material, or any clause
                        that names an eye or nose, must say it is embroidered (with yarn), or
                        it FAILs -- a "9 mm animal eye", a "pom-pom nose" or "an eye back" need
                        not be on a list to be refused.
  MATERIALS_KNOWN       every material is one this gate knows to be safe on a child's item:
                        yarn, new polyester toy stuffing, or a tool that leaves with the maker
                        (hook, needle, marker, scissors). Anything else -- felt, leather
                        lacing, an unnamed notion -- is UNKNOWN and holds the item (an
                        allow-list, so an unlisted hard part is never a pass).
  ATTACHMENTS_KNOWN     every clause that attaches, sews on, fastens, glues or clips something
                        names a piece of this pattern, yarn or an embroidered feature; any
                        other attachment ("sew on the felt heart") is UNKNOWN and holds.
  JOINS_VALIDATED       every sewn-on piece is joined by a sewing method at a stated position
                        (round and stitches, or named edges), measured by `cir.assembly` with
                        no mismatch, sewn across its whole edge with the tail buried.
  NO_CORDS_OR_LOOPS     no threaded cord, no chain-only piece, no chain run longer than
                        MAX_CHAIN_RUN inside a row (consecutive chains summed across ops and
                        repeats, so `ch 6, ch 6, ch 6` is an 18-chain run), no
                        cord/string/ribbon/strap/tie/bow/lace/leash/loop words (stitch-loop
                        terms such as "both loops" excepted), no measured chain or length of
                        yarn, and nothing attached to a pram, crib or pacifier.
  STUFFING_GUIDANCE     a stuffed piece names new polyester toy stuffing (never beans,
                        pellets, rice, seeds or beads), states its stuffing point and closure,
                        and `cir.closed_forms` finds nothing wrong with them.
  SMALL_PARTS           `gates.small_parts.blocking` finds no sewn-on piece that fits or may
                        fit the 31.7 mm cylinder.
  AGE_SUITABILITY       the age band is read (review M4). An item assigned to a band this
                        gate does not know is UNKNOWN; an item for (or read as for) a child
                        under 3 with any sewn-on piece needs SMALL_PARTS to have PASSED, and
                        the printed age statement claims the small-parts geometry only when
                        it has (`section_lines(..., small_parts_clear=)`).
  PHYSICAL_EVIDENCE     a stuffed toy, a lovey, or any item with a sewn-on piece (seam pull,
                        closure, stuffing containment) needs a physical use-and-abuse test of
                        this exact content -- and so does EVERY such item assigned to a child
                        under 3. A flat, unstuffed, one-piece item (a baby blanket) has no seam
                        to pull and nothing to contain, so its checks are all computable; its
                        under-3 risks (cords, loops, hard parts, small parts) are the other
                        checks. No content-bound physical authority exists, so this is UNKNOWN
                        for every stuffed or sewn product today -- HELD.

Content checks (from the rendered text, when given):

  SAFETY_SECTION        every required statement of the product's profile is present
                        (age suitability, features, joins, stuffing, cords, safe sleep, the
                        not-a-toy-certification statement, and for a face or stuffed item
                        the eye options: embroidered is the default, and for a baby or a
                        child under 3 the only option).
  AGE_GUIDANCE_IN_TEXT  a document that gives eye options prints their age guidance.
  CITATIONS             every source a statement rests on is printed with its URL and the
                        date it was accessed.
  NO_CERTIFICATION_CLAIM the document claims no toy certification, test or standard -- we sell
                        patterns. A sentence that DENIES certification is ours and is exempt.
  NO_HARD_PARTS_IN_TEXT the instructions (the text outside the safety section) name no hard part.

Sources were read on ACCESSED (the dates are printed in the document): US regulation text via
the eCFR API and govinfo, Canada's Toys Regulations from laws-lois.justice.gc.ca (current to
2026-10-29), and the CPSC and Health Canada guidance pages. Two facts commonly assumed were NOT
confirmed and are not stated: Canada's Toys Regulations set no cord-length limit for toys for
children under 18 months, and CPSC's safe-sleep page states no age in months. The 12-inch
ASTM F963 cord figure was found only in a 2010 CPSC staff memo, so it is not printed either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
VERDICT_PASS, VERDICT_FAIL, VERDICT_HELD = "PASS", "FAIL", "HELD"
ACCESSED = "2026-11-20"
MAX_CHAIN_RUN = 6               # a longer chain inside a row is a loop a finger can enter


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    url: str
    quote: str                  # verbatim from the page read on ACCESSED
    # ENG-PLUSH-FIX (review L2): how the quote was re-read word for word against the source,
    # and when. Empty means nobody has, and CITATIONS is then UNKNOWN: an unread quote is never
    # printed as verbatim on a document that passes.
    verified: str = ""


SOURCES: dict[str, Source] = {s.key: s for s in (
    Source("cfr_1501", "US 16 CFR 1501 (small parts, children under 3)",
           "https://www.ecfr.gov/current/title-16/chapter-II/subchapter-C/part-1501",
           "any toy or other article intended for use by children under 3 years of age that "
           "presents a choking, aspiration, or ingestion hazard because of small parts",
           "2026-11-20 ENG-PLUSH-FIX: exact text in the eCFR renderer API for part 1501"),
    Source("cfr_1500_19", "US 16 CFR 1500.19(b)(1) (choking-hazard cautionary statement)",
           "https://www.ecfr.gov/current/title-16/chapter-II/subchapter-C/part-1500/"
           "section-1500.19",
           "WARNING: CHOKING HAZARD--Small parts Not for children under 3 yrs.",
           "2026-11-20 ENG-PLUSH-FIX: the 1500.19(b)(1) label as eCFR prints it (image "
           "ER27FE95.001); its line break is printed as a space"),
    Source("sor_2011_17", "Canada Toys Regulations SOR/2011-17 (s.7 small parts, s.29 "
                          "stuffing, s.31 eyes and noses)",
           "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2011-17/FullText.html",
           "it must be clean and free from vermin; (b) it must be free of hard or sharp "
           "foreign matter",
           "2026-11-20 ENG-PLUSH-FIX: exact text of s.29(a)-(b), laws-lois.justice.gc.ca "
           "full text"),
    Source("hc_toy_tips", "Health Canada: toy safety tips",
           "https://www.canada.ca/en/health-canada/services/toy-safety/toy-safety-tips.html",
           "Don't give toys with small parts or accessories to children under 3 years old.",
           "2026-11-20 ENG-PLUSH-FIX: exact on the page except its typographic apostrophe "
           "(U+2019), printed here as a straight one"),
    Source("cpsc_5100", "CPSC Publication 5100 (toys and cords)",
           "https://www.cpsc.gov/s3fs-public/5100.pdf",
           "Parents should never give young children toys with cords, strings, or straps "
           "that fit around the neck.",
           "2026-11-20 ENG-PLUSH-FIX: exact text extracted from the PDF"),
    Source("cpsc_safe_sleep", "CPSC: safe sleep",
           "https://www.cpsc.gov/SafeSleep",
           "The safest way for a baby to sleep is flat on their back without pillows, "
           "blankets, or toys in their sleep space.",
           "2026-11-20 ENG-PLUSH-FIX: exact on the page, where it is the caption of the "
           "page's safe-sleep video"),
    Source("hc_safe_sleep", "Health Canada: safe sleep tips",
           "https://www.canada.ca/en/health-canada/services/safe-sleep/safe-sleep-tips.html",
           "Provide a sleep space that is flat, firm and free of soft bedding, extra padding, "
           "bumper pads, stuffed toys or pillows.",
           "2026-11-20 ENG-PLUSH-FIX: exact on the page (\"flat, firm and free\" is bold "
           "there)"),
)}


EYE_OPTIONS_MARKER_ = "Eye options: embroidered with yarn is the default"


@dataclass(frozen=True)
class Statement:
    key: str
    heading: str
    text: str
    marker: str                 # a phrase the content check looks for in the rendered text
    sources: tuple[str, ...] = ()


def _cite(*keys: str) -> str:
    return " ".join(f"({SOURCES[k].title}: \"{SOURCES[k].quote}\" {SOURCES[k].url}, accessed "
                    f"{ACCESSED}.)" for k in keys)


STATEMENTS: dict[str, Statement] = {s.key: s for s in (
    Statement("pattern_not_toy", "We sell a pattern, not a toy",
              "Brambleloop Studio sells these instructions. We have not made, tested or "
              "certified the item you will make, and we make no claim that it meets any "
              "toy-safety standard. What you make is yours: its safety depends on your yarn, "
              "your tension and your finishing.",
              "We sell a pattern, not a toy"),
    Statement("age_suitability", "Age suitability",
              "This design follows the construction rules for toys for children under 3: no "
              "part is meant to come off, and by the pattern's own stitch counts every "
              "sewn-on piece is larger than the small-parts cylinder (31.7 mm across). That "
              "is geometry, not a use-and-abuse test, so it does not make the finished item "
              "suitable for any age; only a tested sample can show that. "
              + _cite("cfr_1501"),
              "the small-parts cylinder (31.7 mm across)",
              ("cfr_1501",)),
    Statement("features", "Embroidered features only",
              "Embroider the eyes, nose and any other feature with yarn. Do not use safety "
              "eyes, buttons, beads, bells or any other hard part on an item for a child "
              "under 3 or on any baby item: a hard eye or nose that is pulled off is a choking "
              "hazard. If you change this, the US cautionary statement then applies to what "
              "you make: \"WARNING: CHOKING HAZARD--Small parts / Not for children under 3 "
              "yrs.\" Embroidered features alone do not make an item safe; the joins, the "
              "stuffing and the no-cords rule below matter as much. "
              + _cite("hc_toy_tips", "cfr_1500_19"),
              "Embroider the eyes, nose and any other feature with yarn",
              ("hc_toy_tips", "cfr_1500_19")),
    Statement("eye_options", "Eye options",
              "", EYE_OPTIONS_MARKER_, ("hc_toy_tips", "cfr_1500_19")),
    Statement("joins", "Joins",
              "Sew every piece on across its whole edge, through both loops of every stitch "
              "and through the fabric it joins, across and back again, so no single stitch "
              "carries it. Knot the tail inside and bury it through at least 5 cm of "
              "stitches. Pull each sewn piece firmly when you finish; resew any that moves.",
              "Sew every piece on across its whole edge"),
    # ENG-AMIGURUMI-BREADTH: a crocheted-in (low-sew) piece is joined by the pattern's own
    # stitches, not sewn; this states how that join must be worked and checked.
    Statement("low_sew_joins", "Crocheted-in joins",
              "Every crocheted-in piece is joined as the pattern says: each joining stitch "
              "goes through both loops of the body stitch and through both layers of the "
              "piece's flattened edge, across the whole edge, so no part of the edge is left "
              "loose and no single stitch carries it. Pull each joined piece firmly when you "
              "finish; work again any edge stitch that is loose.",
              "Every crocheted-in piece is joined as the pattern says"),
    Statement("stuffing", "Stuffing",
              "Use only new, clean polyester toy stuffing. Never use beans, pellets, rice, "
              "seeds, beads or anything hard. Work at the stated gauge or tighter so stuffing "
              "cannot show between the stitches, stuff firmly at the round the pattern "
              "names, and close the last round tightly as written. " + _cite("sor_2011_17"),
              "Use only new, clean polyester toy stuffing",
              ("sor_2011_17",)),
    Statement("no_cords", "No cords or loops",
              "Add no cords, ribbons, strings, straps, ties or hanging loops, and do not "
              "attach the item to a pacifier clip, a crib or a pram. " + _cite("cpsc_5100"),
              "Add no cords, ribbons, strings, straps, ties or hanging loops",
              ("cpsc_5100",)),
    Statement("safe_sleep", "Keep it out of the sleep space",
              "Keep this out of a baby's crib, cot or bassinet: soft items do not belong in "
              "an infant's sleep space. " + _cite("cpsc_safe_sleep", "hc_safe_sleep"),
              "Keep this out of a baby's crib, cot or bassinet",
              ("cpsc_safe_sleep", "hc_safe_sleep")),
)}

# ENG-PLUSH-FIX (review M4): the age statement claims the small-parts geometry only when the
# SMALL_PARTS check has passed. A one-piece item has no sewn-on piece to claim about, and a
# HELD document (its small parts not yet shown clear) must not print a claim nobody proved.
AGE_TEXT_ONE_PIECE = (
    "This design is worked in one piece with no sewn-on part, so no part is meant to come "
    "off and there is no piece to fit the small-parts cylinder (31.7 mm across). That is "
    "construction, not a use-and-abuse test, so it does not make the finished item suitable "
    "for any age; only a tested sample can show that. " + _cite("cfr_1501"))
AGE_TEXT_UNPROVEN = (
    "This design has sewn-on pieces, and whether every one of them is larger than the "
    "small-parts cylinder (31.7 mm across) has NOT been shown for this document. Do not give "
    "the finished item to a child under 3. Nothing here is a use-and-abuse test, so it does "
    "not make the finished item suitable for any age; only a tested sample can show that. "
    + _cite("cfr_1501"))

# ENG-PLUSH-FIX: the eye-options reading. Embroidered with yarn is the default eye for every
# item in this gate, and for a baby or a child under 3 it is the only option the pattern gives.
# The age guidance is printed in the PDF text with it (D-ENG-PLUSH-FIX, eye options).
EYE_DEFAULT = "embroidered"
EYE_OPTIONS_MARKER = EYE_OPTIONS_MARKER_
AGE_GUIDANCE_MARKER = "Age guidance:"


def eye_options(age_band: str | None, profile: tuple[str, ...] = ()) -> dict:
    """The eye options this document gives for an item in `age_band` (None reads as under 3,
    the conservative reading). `default` is always embroidered; `allowed` is embroidered only
    (FEATURES_EMBROIDERED fails any hard eye on an item in this gate). `young` is a baby or a
    child under 3: a sleep-profile item, or the under-3 band."""
    from ..intel import childrens as _ch

    band = age_band or _ch.UNDER_3
    known = band in _ch.AGE_BANDS
    young = band == _ch.UNDER_3 or "sleep" in profile or not known
    label = _ch.AGE_BANDS[band].label if known else "an age this pattern does not know"
    if young:
        text = (f"{EYE_OPTIONS_MARKER}, and for a baby or a child under 3 it is the only "
                "option. Embroider the eyes and nose with yarn, worked flat and tight to the "
                "fabric. Do not fit safety eyes, craft eyes, buttons, beads or any hard eye "
                "or nose: a hard part that is pulled off is a choking hazard. "
                f"{AGE_GUIDANCE_MARKER} this pattern is written for a baby or a child under 3 "
                "(0 to 36 months) only with embroidered features; with any hard eye or nose "
                "the finished item is not for a child under 3. " + _cite("hc_toy_tips"))
    else:
        text = (f"{EYE_OPTIONS_MARKER} and the only option this pattern gives. Embroider the "
                "eyes and nose with yarn. This pattern does not give a safety-eye option; if "
                "you fit any hard eye or nose, the finished item is not for a child under 3 "
                "and the US cautionary statement applies: \"WARNING: CHOKING HAZARD--Small "
                f"parts / Not for children under 3 yrs.\" {AGE_GUIDANCE_MARKER} this design is "
                f"assigned to {label}. " + _cite("cfr_1500_19"))
    return {"band": band, "young": young, "default": EYE_DEFAULT,
            "allowed": (EYE_DEFAULT,), "text": text}


SECTION_HEADING = "Child safety: read before you make this"
SECTION_END = "End of child safety notes."

_HARD_PARTS = re.compile(
    r"\bsafety[- ]?eyes?\b|\bplastic (?:eyes?|nose|noses)\b|\bglass eyes?\b|\bgoogly\b|"
    r"\bbuttons?\b|\bbeads?\b|\bbeaded\b|\bbells?\b|\bjingle\b|\bsequins?\b|\bpellets?\b|"
    r"\bpoly[- ]?pellets?\b|\bbeans?\b|\brice\b|\bseeds?\b|\bsqueakers?\b|\brattle insert\b|"
    r"\bwire\b|\bwired\b|\bpipe[- ]cleaners?\b|\bmagnets?\b|\bjoint discs?\b|\bglue(?:d)?\b|"
    r"\bgrommets?\b|\bsnaps?\b|\bzip(?:per)?s?\b|\bvelcro\b|\bhook[- ]and[- ]loop\b|"
    # ENG-PLUSH-FIX (review M1): more named hard or detachable parts. The eye/nose rule below
    # (`_unembroidered_feature`) is the allow-list; these are the parts that are not features.
    r"\brhinestones?\b|\bdiamante\b|\bgems?\b|\bgemstones?\b|\bcrystals?\b|\bstuds?\b|"
    r"\bpress[- ]?studs?\b|\bpoppers?\b|\btoggles?\b|\bhook[- ]and[- ]eyes?\b|\bwashers?\b|"
    r"\beye[- ]?backs?\b|\bpom[- ]?poms?\b|\bpompoms?\b|\btassels?\b|\bcharms?\b|"
    r"\bpendants?\b|\bsafety pins?\b|\bbrooch(?:es)?\b|\bresin\b")
# Stitch-loop terminology that is not a loop a finger can enter; removed before the loop word
# is looked for. Everything else that says "loop" is a loop.
_STITCH_LOOP_TERMS = re.compile(
    r"\b(?:both|front|back|inner|outer|remaining|two|three|\d+)[\s-]+loops?\b|"
    r"\bloops?\s+(?:of (?:the|every|each|this) (?:st|sts|stitch|stitches)|on (?:the|your) hook|only)\b|\b(?:magic|adjustable|sliding)\s+(?:ring|loop)\b|"
    r"\b(?:flo|blo)\b|\bthrough (?:the|both|all|\d+) loops?\b")
_LACE_TERMS = re.compile(r"\blace[- ](?:weight|stitch|stitches|pattern|panel|edging|motif|"
                         r"border|repeat|chart|section)\b|\blacy\b")
_CORD_WORDS = re.compile(
    r"\bcords?\b|\bstrings?\b|\bribbons?\b|\bstraps?\b|\bties?\b|\btied\b|\btying\b|"
    r"\bbows?\b|\bdrawstrings?\b|\bloops?\b|\bpacifiers?\b|\bdummy clip\b|\bsoother clip\b|"
    r"\blanyards?\b|\blaces?\b|\blacing\b|\bleash(?:es)?\b|\bleads? for\b|\btethers?\b|"
    r"\bharness\b|\bnecklaces?\b|\bbracelets?\b|\bbraids?\b|\bplaits?\b|\bi-cords?\b|"
    # a measured chain or length of yarn is a cord, whatever it is for
    r"\b\d+(?:\.\d+)?\s*(?:cm|mm|in|inch|inches|\")\s+(?:long\s+)?(?:chain|cord|length|strand|"
    r"piece)\b|\blength of (?:yarn|thread|wool|cotton)\b|"
    r"\b(?:attach|fasten|clip|hang|hook|tie)\w*\b[^.;:]{0,40}\b(?:pram|crib|cot|stroller|"
    r"pushchair|car ?seat|bassinet|cradle|high ?chair|playpen|mobile)s?\b")
# A word that says the feature is embroidered; a clause naming an eye or nose without one is a
# hard or detachable feature, whatever it is called (M1: the eye/nose rule is an allow-list).
_FEATURE_WORDS = re.compile(r"\beyes?\b|\bnoses?\b|\bpupils?\b|\birises\b|\bnostrils?\b")
_EMBROIDERED = re.compile(r"\bembroider")
_MOUNTED_FEATURE = re.compile(
    r"\b\d+(?:\.\d+)?\s*mm\b[^.;:]{0,25}\b(?:eyes?|noses?)\b|"
    r"\b(?:insert|attach|glue|fix|fit|push|snap|screw|sew on|sew in)\w*\b[^.;:]{0,30}"
    r"\b(?:eyes?|noses?)\b")
# ENG-PLUSH-FIX (review M1): the material allow-list. A child's or stuffed item may list yarn,
# new polyester toy stuffing, and tools that leave with the maker. Anything else is UNKNOWN.
_MATERIAL_YARN = re.compile(
    r"\byarns?\b|\bacrylic\b|\bcotton\b|\bwool\b|\bmerino\b|\balpaca\b|\bbamboo\b|"
    r"\bchenille\b|\bworsted\b|\baran\b|\bdk\b|\bsport\b|\bfingering\b|\bbulky\b|"
    r"\bchunky\b|\bsuper bulky\b|\bjumbo\b|\blinen\b|\bembroidery floss\b|\bstranded "
    r"cotton\b")
_MATERIAL_TOOL = re.compile(
    r"^(?:an?\s+|one\s+|\d+\s*(?:x\s*)?)?(?:\d+(?:\.\d+)?\s*mm\s+)?(?:crochet\s+)?hooks?\b|"
    r"\b(?:tapestry|yarn|darning|blunt)\s+needles?\b|\bstitch markers?\b|\bscissors\b|"
    r"\bmeasuring tape\b|\btape measure\b|\brow counter\b")
_STUFFING_OK = re.compile(r"\bpolyester\b.*\b(?:fibrefill|fiberfill|stuffing|fill)\b|"
                          r"\btoy stuffing\b")
_CLAIMS = re.compile(
    r"\b(?:is|are|has been|have been|was|were)\s+(?:safety[- ])?(?:tested|certified|approved)\b|"
    r"\bsafety[- ]tested\b|\blab[- ]tested\b|\bcertified (?:safe|toy|to)\b|"
    r"\b(?:meets|complies with|compliant with|conforms to)\s+(?:astm|en ?71|cpsia|iso|the toy)|"
    r"\bastm[- ]compliant\b|\bcpsia[- ]compliant\b|\bce[- ]mark(?:ed)?\b|"
    r"\bsafe for (?:babies|infants|newborns|toddlers|all ages|children)\b|\bchild[- ]safe\b|"
    r"\bbaby[- ]safe\b|\bnon[- ]toxic\b")


@dataclass
class Check:
    code: str
    state: str
    detail: str


@dataclass
class Verdict:
    applies: bool
    profile: tuple[str, ...]
    checks: list[Check] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if not self.applies:
            return VERDICT_PASS
        states = {c.state for c in self.checks}
        if FAIL in states:
            return VERDICT_FAIL
        if UNKNOWN in states:
            return VERDICT_HELD
        return VERDICT_PASS

    def failing(self) -> list[Check]:
        return [c for c in self.checks if c.state == FAIL]

    def unknown(self) -> list[Check]:
        return [c for c in self.checks if c.state == UNKNOWN]

    def to_dict(self) -> dict:
        return {"applies": self.applies, "profile": list(self.profile),
                "verdict": self.verdict,
                "checks": [{"code": c.code, "state": c.state, "detail": c.detail}
                           for c in self.checks]}


# ---- profile -----------------------------------------------------------------------------

SLEEP_SUBCATEGORIES = frozenset({"lovey", "baby_blanket", "keepsake_blanket", "nursery_decor"})
_SLEEP_WORDS = re.compile(r"\b(?:baby|babies|infant|newborn|nursery|lovey|loveys|crib|cot|"
                          r"swaddle|receiving)\b")


def _fold(text: str) -> str:
    from ..products.text_fold import fold

    return fold(text or "")


def _instruction_texts(cir) -> list[str]:
    out = [str(getattr(cir, "designer_notes", "") or "")]
    out += [str(getattr(m, "name", "") or "") for m in cir.materials]
    out += [str(getattr(s, "note", "") or "") for s in cir.assembly]
    for c in cir.components:
        out.append(str(c.note or ""))
        out += [str(r.note or "") for r in c.rows]
    return out


def profile_for(cir, childrens: tuple[str, str] | None = None) -> tuple[str, ...]:
    """Which statement groups apply: always the base set; `stuffed`, `face`, `sewn`, `sleep`."""
    from ..products import launch0

    flags = {"base"}
    # Stuffed means stuffing evidence: a stated stuffing point or closure, a seam stuffed
    # before closing, or a stuffing material. A1-R's "unknown non-yarn material" reading is
    # answered by MATERIALS_KNOWN, which holds an unidentified material as UNKNOWN.
    if any(c.stuff_at_round is not None or c.closes for c in cir.components) \
            or any(getattr(s, "stuff_before_closing", False) for s in cir.assembly) \
            or any(re.search(r"\b(?:fibrefill|fiberfill|stuffing|polyfill|filling|stuffed)\b",
                             _fold(str(m.name or ""))) for m in cir.materials):
        flags.add("stuffed")
    text = _fold(" ".join(_instruction_texts(cir)))
    if re.search(r"\bembroider", text) or re.search(r"\beyes?\b|\bnose\b|\bface\b", text):
        flags.add("face")
    if any(s.piece_a != s.piece_b and s.method != "pick_up" for s in cir.assembly):
        flags.add("sewn")
    # ENG-AMIGURUMI-BREADTH: a piece crocheted in (low-sew) is still an attached piece: the
    # small-parts, age and physical-evidence rules read it exactly as a sewn one.
    from ..cir import low_sew as _low_sew

    if _low_sew.joined_pieces(cir):
        flags.add("joined_in")
    if garment_months(cir) is not None:
        flags.add("garment")
    title = _fold(f"{cir.title} {cir.slug}")
    if (childrens and childrens[0] in SLEEP_SUBCATEGORIES) or _SLEEP_WORDS.search(title):
        flags.add("sleep")
    return tuple(sorted(flags))


def applies(cir, childrens: tuple[str, str] | None = None) -> bool:
    """A closed stuffed form, a children's assignment, or a title that reads as a child's."""
    from ..products import launch0

    if childrens or launch0.child_words_in(cir.title, cir.slug) or launch0.stuffed_figure(cir):
        return True        # a stuffed figure is a toy whatever any decision says
    # ENG-GARMENT: a garment graded on the baby table, or on the child table at 12 or under,
    # is a child's garment whatever its title says.
    if garment_months(cir) is not None:
        return True
    # A stuffed closed piece in rounds (an amigurumi body, a ball) is toy-shaped whatever it
    # is called. A stuffed panel pair (a cushion) is not: whether it is for a child is the
    # owner's decision, which the A1-R gate (`publish.pdf`) already holds it for; once it is
    # assigned to a child, it is inside this gate.
    if any(c.closes or c.stuff_at_round is not None for c in cir.components):
        return True
    if launch0.closed_stuffed_form(cir):
        state, _why = launch0.childrens_decision_for(cir)
        return state == launch0.ASSIGNED
    return False


def required_statements(profile: tuple[str, ...]) -> tuple[str, ...]:
    keys = ["pattern_not_toy", "age_suitability", "no_cords"]
    if "face" in profile or "stuffed" in profile:
        keys.append("features")
        keys.append("eye_options")
    if "sewn" in profile:
        keys.append("joins")
    if "joined_in" in profile:
        keys.append("low_sew_joins")
    if "stuffed" in profile:
        keys.append("stuffing")
    if "sleep" in profile:
        keys.append("safe_sleep")
    return tuple(keys)


def age_text(profile: tuple[str, ...], small_parts_clear: bool | None) -> str:
    """The age statement this document may print (review M4): the small-parts claim only when
    the SMALL_PARTS check passed, none for a one-piece item, a do-not-give warning otherwise."""
    if "sewn" not in profile and "joined_in" not in profile:
        return AGE_TEXT_ONE_PIECE
    if small_parts_clear is True:
        return STATEMENTS["age_suitability"].text
    return AGE_TEXT_UNPROVEN


def section_lines(profile: tuple[str, ...], *, small_parts_clear: bool | None = None,
                  age_band: str | None = None) -> list[tuple[str, str]]:
    """(heading, text) pairs the PDF prints, in order, ending with the sources and the end mark.

    `small_parts_clear` is whether `SMALL_PARTS` PASSED for this content; anything else (None,
    False) prints the age statement without the small-parts claim. `age_band` is the
    assignment's band (None reads as under 3) and chooses the eye-options reading."""
    def _text(k: str) -> str:
        if k == "age_suitability":
            return age_text(profile, small_parts_clear)
        if k == "eye_options":
            return eye_options(age_band, profile)["text"]
        return STATEMENTS[k].text

    out = [(STATEMENTS[k].heading, _text(k)) for k in required_statements(profile)]
    used = sorted({s for k in required_statements(profile) for s in STATEMENTS[k].sources})
    out.append(("Sources", " ".join(f"{SOURCES[k].title}, {SOURCES[k].url}, accessed "
                                    f"{ACCESSED}." for k in used)))
    out.append(("", SECTION_END))
    return out


# ---- the checks ----------------------------------------------------------------------------

_CLAUSE = re.compile(r"[.;!?\n]+")


def _unembroidered_feature(text: str) -> str | None:
    """The first clause that names an eye or nose without saying it is embroidered, or that
    names a mounted feature (a size in mm, inserted, glued, sewn on) -- None when there is none.
    M1: an allow-list, so a "craft eye", "doll eye", "crystal eye" or "pom-pom nose" is refused
    without being listed. Materials are one clause each."""
    for clause in _CLAUSE.split(_fold(text)):
        if not _FEATURE_WORDS.search(clause):
            continue
        mounted = _MOUNTED_FEATURE.search(clause)
        if mounted:
            return mounted.group(0).strip()
        if not _EMBROIDERED.search(clause):
            return clause.strip()[:80]
    return None


def _features(cir, profile) -> Check:
    texts = _fold(" ".join(_instruction_texts(cir)))
    hit = _HARD_PARTS.search(texts)
    if hit:
        return Check("FEATURES_EMBROIDERED", FAIL,
                     f"the pattern names {hit.group(0)!r}: only embroidered yarn features are "
                     f"allowed on a child's or stuffed item")
    for piece in _instruction_texts(cir):
        clause = _unembroidered_feature(piece)
        if clause:
            return Check("FEATURES_EMBROIDERED", FAIL,
                         f"an eye or nose is named without being embroidered with yarn "
                         f"({clause!r}): only embroidered yarn features are allowed")
    if "face" in profile and not re.search(r"\bembroider", texts):
        return Check("FEATURES_EMBROIDERED", FAIL,
                     "the item has a face but no instruction says it is embroidered with yarn")
    return Check("FEATURES_EMBROIDERED", PASS,
                 "no hard part named" + ("; the face is embroidered with yarn"
                                         if "face" in profile else ""))


# ENG-PLUSH-FIX: attachments are an allow-list too. A clause that attaches, sews on, fastens,
# glues or clips something must name a piece this CIR builds, yarn, or an embroidered feature;
# anything else ("sew on the felt heart", "clip on the charm holder") is an attachment this
# gate does not know, and it is UNKNOWN, which holds the item.
_ATTACH_VERB = re.compile(
    r"\b(?:attach\w*|sew(?:s|n|ing)? (?:on|in)|sew(?:s|n|ing)? (?:the|a|an|it|them|each|both)\b"
    r"|fasten\w*|glue\w*|clip\w*|pin(?:s|ned|ning)? (?:on|to)|fix(?:es|ed|ing)? (?:on|to)|"
    r"stitch(?:es|ed|ing)? on|add(?:s|ed|ing)? (?:a|an|the|two|\d+) \w+ (?:to|on)|mount\w*)\b")
_KNOWN_ATTACHED = re.compile(
    r"\b(?:yarn|tail|tails|embroider\w*|piece|pieces|ear|ears|head|body|arm|arms|leg|legs|"
    r"tail|muzzle|snout|paw|paws|foot|feet|wing|wings|horn|horns|nose|eye|eyes|panel|panels|"
    r"front|back|patch|appliqu\w*|motif|motifs|edge|edging|border|square|squares|seam|"
    r"blanket|lovey|cushion|cover|round|rounds|row|rows|stitch|stitches|st|sts)\b")


def _attachment_names(cir) -> set[str]:
    names = set()
    for c in cir.components:
        for w in re.findall(r"[a-z]+", _fold(str(getattr(c, "name", "") or ""))):
            if len(w) > 2:
                names.add(w)
    return names


def _attachments(cir) -> Check:
    names = _attachment_names(cir)
    texts = [str(getattr(cir, "designer_notes", "") or "")]
    texts += [str(getattr(s, "note", "") or "") for s in cir.assembly]
    for c in cir.components:
        texts.append(str(c.note or ""))
        texts += [str(r.note or "") for r in c.rows]
    unknown = []
    for text in texts:
        for clause in _CLAUSE.split(_fold(text)):
            m = _ATTACH_VERB.search(clause)
            if not m:
                continue
            words = set(re.findall(r"[a-z]+", clause))
            if _KNOWN_ATTACHED.search(clause) or words & names:
                continue
            unknown.append(clause.strip()[:80])
    if unknown:
        return Check("ATTACHMENTS_KNOWN", UNKNOWN,
                     f"attachments this gate does not know to be a piece of this pattern, yarn "
                     f"or an embroidered feature: {unknown}: UNKNOWN is not a pass")
    return Check("ATTACHMENTS_KNOWN", PASS,
                 "every attachment is a piece of this pattern, yarn or embroidery")


def _materials(cir) -> Check:
    """Every material is yarn, new polyester toy stuffing, or a tool (review M1: an allow-list,
    so an unknown hard part, notion or attachment is UNKNOWN and holds the item)."""
    unknown = []
    for m in cir.materials:
        name = _fold(str(getattr(m, "name", "") or "")).strip()
        if not name:
            unknown.append("(an unnamed material)")
        elif _STUFFING_OK.search(name) or _MATERIAL_TOOL.search(name):
            continue
        elif _MATERIAL_YARN.search(name) or getattr(m, "yarn_weight", None):
            continue
        else:
            unknown.append(name)
    if unknown:
        return Check("MATERIALS_KNOWN", UNKNOWN,
                     f"materials this gate does not know to be safe on a child's or stuffed "
                     f"item: {unknown}; only yarn, new polyester toy stuffing and tools are "
                     f"known: UNKNOWN is not a pass")
    return Check("MATERIALS_KNOWN", PASS,
                 f"all {len(cir.materials)} materials are yarn, toy stuffing or tools")


def _age_band(cir, childrens) -> str | None:
    """The age band the item is for: the assignment's, else UNDER_3 (a stuffed or child-titled
    item with no assignment is read as for the youngest child, the conservative reading)."""
    if childrens:
        return childrens[1]
    from ..intel import childrens as _ch

    return _ch.UNDER_3


def _age(cir, profile, childrens, small: Check) -> Check:
    from ..intel import childrens as _ch

    band = _age_band(cir, childrens)
    if band not in _ch.AGE_BANDS:
        return Check("AGE_SUITABILITY", UNKNOWN,
                     f"age band {band!r} is not one this gate knows: UNKNOWN is not a pass")
    attached = "sewn" in profile or "joined_in" in profile
    if band == _ch.UNDER_3 and attached and small.state != PASS:
        return Check("AGE_SUITABILITY", small.state,
                     f"for a child under 3 every sewn-on piece must be shown clear of the "
                     f"small-parts cylinder, and SMALL_PARTS is {small.state}")
    return Check("AGE_SUITABILITY", PASS,
                 f"age band {band}: "
                 + ("every sewn-on piece is clear of the small-parts cylinder"
                    if attached else "one piece, nothing sewn on"))


def _joins(cir, result) -> Check:
    # ENG-AMIGURUMI-BREADTH: crocheted-in pieces are checked first and never skipped: a toy
    # with no sewn seam is not "nothing joined" when its limbs are crocheted into its rounds.
    from ..cir import low_sew as _low_sew

    if _low_sew.joined_pieces(cir):
        low = _low_sew_joins(cir, result)
        if low.state != PASS:
            return low
        rest = _sewn_joins(cir, result)
        if rest.detail == "no piece is sewn onto another":
            return low
        return rest if rest.state != PASS else Check(
            "JOINS_VALIDATED", PASS, f"{low.detail}; {rest.detail}")
    return _sewn_joins(cir, result)


def _low_sew_joins(cir, result) -> Check:
    from ..cir import low_sew as _low_sew

    if result is None or not result.ok:
        return Check("JOINS_VALIDATED", UNKNOWN, "the pattern did not compile, so no "
                                                 "crocheted-in join is measured")
    own = [f for f in result.findings if f.code.startswith("LOW_SEW")]
    if own:
        return Check("JOINS_VALIDATED", FAIL, "; ".join(f"{f.code}: {f.message}" for f in own))
    try:
        from ..cir import assembly as _assembly
        from ..cir.twin import build_twin

        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        geo = _assembly.assemble(cir, twins)
    except Exception as exc:  # noqa: BLE001 - an unmeasurable join is UNKNOWN, never a pass
        return Check("JOINS_VALIDATED", UNKNOWN, f"crocheted-in joins could not be measured "
                                                 f"({exc})")
    joins = [j for j in geo.joins if j.method == _low_sew.METHOD]
    bad = [j for j in joins if j.verdict == "mismatched"]
    if bad:
        return Check("JOINS_VALIDATED", FAIL, "; ".join(j.why for j in bad))
    unsure = [j for j in joins if j.verdict != "sound"]
    expected = sum(c.make for c in cir.components if c.name in _low_sew.joined_pieces(cir))
    if unsure or len(joins) != expected:
        return Check("JOINS_VALIDATED", UNKNOWN,
                     f"crocheted-in joins not all measured ({len(joins)} of {expected}): "
                     f"UNKNOWN is not a pass")
    return Check("JOINS_VALIDATED", PASS,
                 f"{len(joins)} crocheted-in join(s), each worked through both loops and both "
                 f"layers of a flattened edge and measured stitch for stitch on the twin")


def _sewn_joins(cir, result) -> Check:
    sewn = [s for s in cir.assembly if s.piece_a != s.piece_b and s.method != "pick_up"]
    picked = [s for s in cir.assembly if s.piece_a != s.piece_b and s.method == "pick_up"]
    if not sewn and picked:
        # ENG-GARMENT: a band picked up and worked into an edge is crocheted fabric, not a
        # piece sewn on; it still has to meet its edge, measured like any join.
        return _picked_up_joins(cir, result, picked)
    if not sewn:
        return Check("JOINS_VALIDATED", PASS, "no piece is sewn onto another")
    bad = [f"{s.piece_a}->{s.piece_b} by {s.method}" for s in sewn
           if s.method not in ("whipstitch", "sew", "mattress", "slst")]
    if bad:
        return Check("JOINS_VALIDATED", FAIL, f"not a sewn join: {bad}")
    unplaced = [f"{s.piece_a}->{s.piece_b}" for s in sewn
                if not s.is_placed and not s.names_its_edges]
    if unplaced:
        return Check("JOINS_VALIDATED", FAIL, f"joins with no stated position: {unplaced}")
    if result is None or not result.ok:
        return Check("JOINS_VALIDATED", UNKNOWN, "the pattern did not compile, so no join is "
                                                 "measured")
    assembly_errors = [f for f in result.findings
                       if f.code.startswith("ASSEMBLY") and f.is_error]
    try:
        from ..cir import assembly as _assembly
        from ..cir.twin import build_twin

        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        geo = _assembly.assemble(cir, twins)
    except Exception as exc:  # noqa: BLE001 - an unmeasurable join is UNKNOWN, never a pass
        return Check("JOINS_VALIDATED", UNKNOWN, f"joins could not be measured ({exc})")
    if assembly_errors or geo.verdict == "does_not_assemble":
        return Check("JOINS_VALIDATED", FAIL,
                     "; ".join([f"{f.code}: {f.message}" for f in assembly_errors]
                               + ([f"does not assemble: {geo.why}"]
                                  if geo.verdict == "does_not_assemble" else [])))
    if geo.verdict != "assembles":
        return Check("JOINS_VALIDATED", UNKNOWN,
                     f"joins not all measured ({geo.verdict}: {geo.why}): UNKNOWN is not a pass")
    notes = _fold(" ".join(str(s.note or "") for s in sewn))
    if not (re.search(r"both loops", notes) and re.search(r"\bbury\b|\bburied\b", notes)):
        return Check("JOINS_VALIDATED", FAIL,
                     "a sewn join does not say it is sewn through both loops with the tail "
                     "buried")
    return Check("JOINS_VALIDATED", PASS,
                 f"{len(sewn)} sewn join(s), each placed and measured, sewn through both loops")


def _cord_word(text: str):
    """The first cord/loop/tie word in this text, after stitch-loop and lace-stitch terms (which
    are not cords) are removed."""
    folded = _LACE_TERMS.sub(" ", _STITCH_LOOP_TERMS.sub(" ", _fold(text)))
    return _CORD_WORDS.search(folded)


def _picked_up_joins(cir, result, picked) -> Check:
    if result is None or not result.ok:
        return Check("JOINS_VALIDATED", UNKNOWN, "the pattern did not compile, so no "
                                                 "picked-up edge is measured")
    try:
        from ..cir import assembly as _assembly
        from ..cir.twin import build_twin

        twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
        geo = _assembly.assemble(cir, twins)
    except Exception as exc:  # noqa: BLE001 - an unmeasurable join is UNKNOWN, never a pass
        return Check("JOINS_VALIDATED", UNKNOWN, f"picked-up edges could not be measured "
                                                 f"({exc})")
    joins = [j for j in geo.joins if j.method == "pick_up"]
    bad = [j for j in joins if j.verdict == "mismatched"]
    if bad:
        return Check("JOINS_VALIDATED", FAIL, "; ".join(j.why for j in bad))
    unsure = [j for j in joins if j.verdict != "sound"]
    if unsure:
        return Check("JOINS_VALIDATED", UNKNOWN,
                     f"picked-up edges not all measured: {[j.why for j in unsure]}")
    return Check("JOINS_VALIDATED", PASS,
                 f"no piece is sewn on; {len(joins)} band(s) picked up and worked into "
                 f"their edges, each measured")


def garment_months(cir) -> int | None:
    """The age in months a graded child's or baby's garment size is for (12 years or under),
    or None when the CIR is not such a garment."""
    g = getattr(cir, "grading", None)
    if g is None:
        return None
    from ..cir.graded import months_of

    months = months_of(g.table, g.size)
    return months if months is not None and months <= 144 else None


UNDER_THREE_MONTHS = 36


def _buttonholes(cir) -> int:
    from ..cir.model import Op

    n = 0
    for c in cir.components:
        for r in c.rows:
            n += sum(1 for o in r.ops if isinstance(o, Op) and o.stitch == "ch"
                     and getattr(o, "spans", 0) and getattr(c, "feature", None) == "button_band")
    return n


def _garment_closures(cir, profile) -> Check:
    """ENG-GARMENT (owner brief): no loose ties or cords for under-3s, and secure buttons or
    no buttons for babies. Buttons are hard parts (FEATURES_EMBROIDERED refuses the word);
    this check reads the structure: a buttonhole is a bridged chain in a button band."""
    if "garment" not in profile:
        return Check("GARMENT_CLOSURES", PASS, "not a child's garment")
    months = garment_months(cir)
    holes = _buttonholes(cir)
    if months is not None and months < UNDER_THREE_MONTHS:
        if holes:
            return Check("GARMENT_CLOSURES", FAIL,
                         f"size for {months} months has {holes} buttonhole(s): a garment for "
                         f"a child under 3 is made with no buttons")
        return Check("GARMENT_CLOSURES", PASS,
                     f"size for {months} months: no buttonholes, no ties, no cords")
    if holes:
        return Check("GARMENT_CLOSURES", UNKNOWN,
                     f"{holes} buttonhole(s) on a child's garment: whether a sewn button is "
                     f"secure is a physical pull test nothing can bind yet: held")
    return Check("GARMENT_CLOSURES", PASS, "no buttonholes, no ties, no cords")


def _cords(cir) -> Check:
    from ..cir.model import Op, Repeat

    if any(s.method == "thread" for s in cir.assembly):
        return Check("NO_CORDS_OR_LOOPS", FAIL, "a cord is threaded through the item")

    UNBOUNDED = 10 ** 6

    def tokens(nodes):
        """The row as a run of (is_chain, count) tokens, repeats expanded (review M2): two
        consecutive chain ops, or a repeat of chains, are one chain run."""
        for n in nodes:
            if isinstance(n, Op):
                yield (n.stitch == "ch", n.count)
            elif isinstance(n, Repeat):
                body = list(tokens(n.ops))
                if not body:
                    continue
                times = n.times
                if times is None:            # "repeat to end": unbounded for a pure chain
                    if all(is_ch for is_ch, _ in body):
                        yield (True, UNBOUNDED)
                        continue
                    times = 2                # two copies show any run across the boundary
                for _ in range(min(times, 64)):
                    yield from body
                if times > 64 and all(is_ch for is_ch, _ in body):
                    yield (True, UNBOUNDED)
            else:
                yield (False, 1)             # an unknown node ends a run, never extends one

    def chain_runs(row):
        run = 0
        for is_ch, count in tokens(row.ops):
            if is_ch:
                run += count
            else:
                if run:
                    yield run
                run = 0
        if run:
            yield run

    for c in cir.components:
        if c.rows and all(all(isinstance(n, Op) and n.stitch == "ch" for n in r.ops)
                          for r in c.rows):
            return Check("NO_CORDS_OR_LOOPS", FAIL, f"{c.name!r} is a chain cord")
        for k, r in enumerate(c.rows):
            longest = max(chain_runs(r), default=0)
            # ENG-GARMENT: a chain the next row works into (sleeves chained on, a neck
            # bridged) is the foundation of fabric, not a loop. A chain in the last row, or
            # one the next row leaves unworked, is still a loop a finger can enter.
            nxt = c.rows[k + 1] if k + 1 < len(c.rows) else None
            if longest > MAX_CHAIN_RUN and nxt is not None and not nxt.skips \
                    and nxt.into is None and not r.allow_remainder:
                continue
            if longest > MAX_CHAIN_RUN:
                return Check("NO_CORDS_OR_LOOPS", FAIL,
                             f"{c.name!r} round/row {r.index} works a {longest}-chain loop "
                             f"(limit {MAX_CHAIN_RUN})")
    hit = _cord_word(" ".join(_instruction_texts(cir)))
    if hit:
        return Check("NO_CORDS_OR_LOOPS", FAIL, f"the pattern names {hit.group(0)!r}")
    return Check("NO_CORDS_OR_LOOPS", PASS, f"no cord, and no chain loop over {MAX_CHAIN_RUN}")


def _stuffing(cir, result, profile) -> Check:
    if "stuffed" not in profile:
        return Check("STUFFING_GUIDANCE", PASS, "not stuffed")
    materials = _fold(" ".join(str(m.name or "") for m in cir.materials))
    if not _STUFFING_OK.search(materials):
        return Check("STUFFING_GUIDANCE", FAIL, "no new polyester toy stuffing is named in the "
                                                "materials")
    closed = [c for c in cir.components if c.closes or c.stuff_at_round is not None]
    if not closed:
        return Check("STUFFING_GUIDANCE", FAIL,
                     "a stuffed item states no stuffing point or closure for any piece")
    missing = [c.name for c in closed if c.stuff_at_round is None or not c.closes]
    if missing:
        return Check("STUFFING_GUIDANCE", FAIL,
                     f"{missing}: a stuffed closed piece must state both its stuffing point "
                     f"and its closure")
    if result is None:
        return Check("STUFFING_GUIDANCE", UNKNOWN, "not compiled")
    from ..cir import closed_forms

    found: list = []
    closed_forms.check(cir, result, found)
    if found:
        return Check("STUFFING_GUIDANCE", FAIL, "; ".join(f"{f.code}: {f.message}"
                                                          for f in found))
    return Check("STUFFING_GUIDANCE", PASS,
                 "; ".join(f"{c.name}: stuffed after round {c.stuff_at_round}, closed"
                           for c in closed))


def _small_parts(cir) -> Check:
    from . import small_parts

    blocks = small_parts.blocking(cir)
    if blocks:
        state = UNKNOWN if all(small_parts.UNKNOWN in b and small_parts.FITS not in b
                               for b in blocks) else FAIL
        return Check("SMALL_PARTS", state, "; ".join(blocks))
    return Check("SMALL_PARTS", PASS, "every sewn-on piece is clear of the 31.7 mm cylinder")


def _physical(cir, profile, childrens) -> Check:
    # Required where the construction can fail in a child's hands: a stuffed piece (closure,
    # stuffing containment) or a sewn-on piece (seam pull). A flat, unstuffed, one-piece
    # blanket has neither, and its other checks are computable.
    needs = ("stuffed" in profile or "sewn" in profile or "joined_in" in profile
             or bool(childrens and childrens[0] in ("lovey", "amigurumi_toy")))
    # Review M4: the age band is read. For a child under 3 the physical test is required for
    # anything with a seam or a closure -- the cases above -- and ALSO for any toy or lovey
    # sub-category whatever its construction; a flat one-piece item has no seam to pull.
    if not needs:
        return Check("PHYSICAL_EVIDENCE", PASS, "no physical evidence is required for this "
                                                "flat, unstuffed construction")
    return Check("PHYSICAL_EVIDENCE", UNKNOWN,
                 "a physical use-and-abuse test of this exact content (seam pull on every "
                 "sewn piece, closure, stuffing containment) is required, and no content-bound "
                 "physical-evidence authority exists yet: held")


def _text_checks(text: str, profile, instructions: str | None = None) -> list[Check]:
    folded = _fold(text)
    out = []
    required = required_statements(profile)
    missing = [k for k in required if _fold(STATEMENTS[k].marker) not in folded]
    out.append(Check("SAFETY_SECTION", FAIL if missing else PASS,
                     f"missing statements: {missing}" if missing else
                     f"all {len(required)} statements present"))
    if "eye_options" in required:
        guided = _fold(AGE_GUIDANCE_MARKER) in folded
        out.append(Check("AGE_GUIDANCE_IN_TEXT", PASS if guided else FAIL,
                         "the eye options and their age guidance are printed" if guided else
                         "the document gives no age guidance with its eye options"))
    sources = sorted({s for k in required for s in STATEMENTS[k].sources})
    uncited = [k for k in sources if SOURCES[k].url.lower() not in folded.replace(" ", "")
               and SOURCES[k].url.lower() not in folded]
    if f"accessed {ACCESSED}" not in folded:
        uncited.append("access date")
    unread = [k for k in sources if not SOURCES[k].verified]
    if uncited:
        out.append(Check("CITATIONS", FAIL, f"not cited with an access date: {uncited}"))
    elif unread:
        out.append(Check("CITATIONS", UNKNOWN,
                         f"quotes not yet re-read word for word against their source: "
                         f"{unread}: UNKNOWN is not a pass"))
    else:
        out.append(Check("CITATIONS", PASS,
                         f"{len(sources)} sources cited, accessed {ACCESSED}, each quote "
                         f"re-read word for word"))
    claim = _CLAIMS.search(folded)
    out.append(Check("NO_CERTIFICATION_CLAIM", FAIL if claim else PASS,
                     f"the document claims {claim.group(0)!r}; we sell patterns and claim no "
                     f"toy certification" if claim else "no certification or test claimed"))
    # The instructions (the writer's pattern text) when given; otherwise the document with
    # this section cut out. Safety pages name hard parts in order to forbid them.
    if instructions is not None:
        outside = _fold(instructions)
    else:
        head, end = _fold(SECTION_HEADING), _fold(SECTION_END)
        outside = folded
        if head in folded and end in folded:
            a, b = folded.index(head), folded.index(end) + len(end)
            outside = folded[:a] + " " + folded[b:]
    if instructions is not None and ("face" in profile) \
            and not re.search(r"\bembroider", outside):
        out.append(Check("FEATURES_INSTRUCTED", FAIL,
                         "the item has a face but the printed instructions never tell the "
                         "maker to embroider it"))
    hard = _HARD_PARTS.search(outside)
    named = hard.group(0) if hard else _unembroidered_feature(outside)
    out.append(Check("NO_HARD_PARTS_IN_TEXT", FAIL if named else PASS,
                     f"the instructions name {named!r}" if named else
                     "the instructions name no hard part"))
    return out


def evaluate(cir, result=None, *, text: str | None = None, instructions: str | None = None,
             childrens: tuple[str, str] | None = None) -> Verdict:
    """The gate. `result` is the compile result (compiled here when None); `text` is the
    customer's rendered text, checked for the safety section when given."""
    if not applies(cir, childrens):
        return Verdict(applies=False, profile=())
    if result is None:
        from ..cir.compiler import compile_cir

        result = compile_cir(cir)
    profile = profile_for(cir, childrens)
    v = Verdict(applies=True, profile=profile)
    small = _small_parts(cir)
    v.checks += [_features(cir, profile), _materials(cir), _attachments(cir),
                 _joins(cir, result), _cords(cir),
                 _stuffing(cir, result, profile), small, _age(cir, profile, childrens, small),
                 _physical(cir, profile, childrens)]
    if "garment" in profile:
        v.checks.append(_garment_closures(cir, profile))
    if text is not None:
        v.checks += _text_checks(text, profile, instructions)
    return v
