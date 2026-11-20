"""Product Truth: the size a title asks for, the size family it belongs to, and the refusal
when the fallback cannot make it (S1 review 6958883678, H1/H2/M1).

Deterministic and closed: a table of size classes per object family, each with the standard it
comes from, and a parser for the size a title states (a class word such as "queen" or
"lumbar", or explicit dimensions such as "200 x 220 cm" / "26 x 26 inch").

Three callers read it:

* `radar.intake` refuses a proposal whose requested size the family cannot make (H2);
* `creative.fallback_constructions.plan` refuses a flat object with no size band and no
  correct template, instead of drafting the default panel under its name (M1), and
  `runtime.pipeline.concept_geometry` drafts at the requested size when the family supports it;
* `gates.certificate.object_size_findings` holds the twin to the size the title claims: the
  named class's band, and the stated dimensions within `TOLERANCE` (H1/H2).

Second review of e490fc6f (S1F-H1, S1F-M1): every size-bearing token in a title -- a class
word, a relative size word, stated dimensions -- is bound to the drafted twin and checked by
`claims`, which both the draft (`request`) and the certificate (`findings`) read. A token the
parser cannot bind (two different sizes, three dimensions, a dangling figure, a unitless size
whose unit is not determined by the band, a relative word with no family) is a refusal with
a reason, never a pass. D-S1-UNITLESS-DIMS and D-S1-RELATIVE-SIZE record the two rules.

Third review of a570aab7 (S1F2-H1, S1F2-M1, LOWs): the parser FAILS CLOSED
(D-S1-FAIL-CLOSED). Every title is tokenised; after the bound claims above are taken out, any
figure (digits, a fraction, a decimal, a number word such as "forty"), any size-class word from
`SIZE_CLASS_VOCAB` the object's family does not define, a size letter, a leftover "size" or a
unit with no figure is `unbound size token: <token>` -- refused at plan and at certification.
Only the cited entries of `ALLOWED_NON_SIZE` pass, each bound to a fact the CIR states (piece
count, colour count, garment grade) or shown not to be a size. Plan and certify read the same
function, and the plan also measures the size it would draft and runs the certificate's own
size check on it (`drafted_refusal`), so the two cannot disagree.

Nothing here estimates from prose. A title with no class word and no dimensions asks for the
family's default size, which the plain template makes and the family band checks.
"""
from __future__ import annotations

import re

INCH_CM = 2.54
# A stated dimension is met when the twin is within this of it: the larger of an absolute
# allowance (one stitch repeat at worsted is about 3.2 cm, so a template cannot land closer
# than half of that) and a relative one (a handmade piece blocks to within a few percent).
TOLERANCE_CM = 2.5
TOLERANCE_REL = 0.07

CYC_BLANKETS = ("Craft Yarn Council, Standard Blanket Sizes (craftyarncouncil.com/standards/"
                "blanket-sizes), inches converted at 2.54 cm")
PILLOW_FORMS = ("standard pillow-form sizes: square 12-26 in, lumbar 12 x 20 in to 14 x 24 in "
                "(the insert sizes cover patterns are written for)")

# ---- size classes ----------------------------------------------------------------------------
# Each class: the words that name it, its band (short side, long side, in cm), the most the
# sides may differ, its default drafted size (short, long) and the standard it comes from.
# A blanket class band spans its CYC sizes with room for blocking; the `baby` class spans
# preemie (18 x 24 in) to crib (45 x 60 in) because "baby blanket" names all of them.
# S1F-H1: the bed sizes are named by the bare word too ("Queen Linen Blanket"); the phrases in
# `NON_SIZE_PHRASES` (single crochet, full moon, Queen Anne's lace...) are removed first.
BLANKET_CLASSES: dict[str, dict] = {
    "preemie": {"words": ("preemie", "premie", "nicu"),
                "short": (42.0, 55.0), "long": (55.0, 70.0), "default": (46.0, 61.0),
                "basis": f"preemie 18 x 24 in ({CYC_BLANKETS})"},
    "baby": {"words": ("baby", "receiving", "stroller", "car seat", "carseat", "crib",
                       "cot", "nursery", "newborn", "infant"),
             "short": (42.0, 120.0), "long": (55.0, 160.0), "default": (80.0, 89.0),
             "basis": f"preemie 18 x 24 in to crib 45 x 60 in; stroller 30 x 35 in "
                      f"({CYC_BLANKETS})"},
    "lap": {"words": ("lap", "lapghan", "lap blanket", "lap throw"),
            "short": (80.0, 110.0), "long": (95.0, 135.0), "default": (91.0, 122.0),
            "basis": f"lapghan 36 x 48 in ({CYC_BLANKETS})"},
    "throw": {"words": ("throw", "sofa", "couch"),
              "short": (75.0, 145.0), "long": (90.0, 170.0), "default": (128.0, 152.0),
              "basis": f"lapghan 36 x 48 in to throw 50 x 60 in ({CYC_BLANKETS})"},
    # S1F-M1 (D-S1-RELATIVE-SIZE): the one relative size word with a defined family. A "large"
    # or "oversized" blanket is bigger than the CYC throw and no bigger than the CYC twin; it
    # is drafted at 60 x 80 in, the size large throws are sold in. Catalogue: Nordic Forest
    # Relief Large Blanket, 120 x 171 cm.
    "large": {"words": ("large", "extra large", "x-large", "xl", "oversized", "oversize",
                        "big", "giant", "jumbo", "huge"),
              "relative": True,
              "short": (110.0, 185.0), "long": (160.0, 245.0), "default": (152.0, 203.0),
              "basis": f"HOUSE FAMILY D-S1-RELATIVE-SIZE: longer than the CYC throw (50 x 60 "
                       f"in) up to the CYC twin (66 x 90 in); drafted at 60 x 80 in "
                       f"({CYC_BLANKETS})"},
    "twin": {"words": ("twin", "twin size", "twin sized", "twin bed", "single bed"),
             "short": (155.0, 185.0), "long": (215.0, 245.0), "default": (168.0, 229.0),
             "basis": f"twin 66 x 90 in ({CYC_BLANKETS})"},
    "full": {"words": ("full", "full size", "full sized", "full bed", "double bed",
                       "double size"),
             "short": (190.0, 215.0), "long": (215.0, 245.0), "default": (203.0, 229.0),
             "basis": f"full 80 x 90 in ({CYC_BLANKETS})"},
    "queen": {"words": ("queen", "queen size", "queen sized", "queen bed"),
              "short": (215.0, 245.0), "long": (240.0, 270.0), "default": (229.0, 254.0),
              "basis": f"queen 90 x 100 in ({CYC_BLANKETS})"},
    "king": {"words": ("king", "king size", "king sized", "king bed", "california king",
                       "cal king"),
             "short": (240.0, 280.0), "long": (260.0, 290.0), "default": (254.0, 274.0),
             "basis": f"king 108 x 100 in ({CYC_BLANKETS})"},
}
PILLOW_CLASSES: dict[str, dict] = {
    "lumbar": {"words": ("lumbar", "oblong", "rectangular", "rectangle", "bolster"),
               "short": (25.0, 40.0), "long": (45.0, 66.0), "min_aspect": 1.4,
               "default": (30.0, 50.0), "basis": PILLOW_FORMS},
}

# Phrases whose words look like sizes and are not: crochet stitches, names, idioms. Removed
# from the title before any size word is read. A word left after this is a size word.
NON_SIZE_PHRASES = (
    r"\b(?:single|double|half double|treble|triple|extended single) crochet\b",
    r"\bqueen anne'?s?\b", r"\b(?:king|queen|twin)'s\b", r"\bfull (?:moon|bloom|of|colou?rs?)\b",
    r"\btwin (?:peaks|set)\b", r"\blong (?:stitch(?:es)?|weekend)\b", r"\bshort rows?\b",
    r"\bsmall batch\b",
    # S1F2-M1: "double" and "half" in these phrases name a construction, not a size.
    r"\bdouble[- ](?:sided|layer(?:ed)?|thick(?:ness)?|knit|faced?|weave|bobble|strand(?:ed)?)\b",
    r"\bhalf[- ](?:square|hexagon|hexie|circle|moon)s?(?: triangles?)?\b",
)

# ---- fail-closed tokenizer (D-S1-FAIL-CLOSED, S1F2-H1/M1) ------------------------------------
# Number words: a figure spelled out ("forty by fifty inches") is a size token like "40".
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fourty",
                "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "dozen")
_NUMBER_VALUE = {w: i for i, w in enumerate(NUMBER_WORDS[:21])}
_NUMBER_VALUE.update({"thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
                      "seventy": 70, "eighty": 80, "ninety": 90, "dozen": 12})
_NUMBER_WORD = r"(?:" + "|".join(NUMBER_WORDS) + r")"
_COUNT = rf"(\d+|{_NUMBER_WORD})"

# Words that name a size class. A word here is refused unless the object's family defines that
# class from a cited standard (BLANKET_CLASSES / PILLOW_CLASSES words are taken out first, so
# "Queen Linen Blanket" binds and "King Pillow Cover" is refused). Bed words that are also
# ordinary English ("full", "double", "single") are size words only on bedding (a blanket or
# a pillow), and the construction phrases in NON_SIZE_PHRASES are removed before this runs.
SIZE_CLASS_VOCAB = (
    r"\b(?:cal(?:ifornia)? )?king\b", r"\bqueen\b", r"\btwin\b", r"\btoddler\b", r"\byouth\b",
    r"\bjunior\b", r"\bteen\b", r"\badult\b", r"\bbody\b", r"\beuro\b", r"\bfloor\b",
    r"\bhalf\b", r"\bquarter\b", r"\bstandard\b", r"\bregular\b", r"\bpreemie\b",
    r"\bxx?s\b", r"\bx{2,3}l\b", r"\bxl\b", r"\bsize[sd]?\b", r"\bone[- ]size\b",
)
BEDDING_VOCAB = (r"\bfull\b", r"\bdouble\b", r"\bsingle\b",
                 # S1F3-M1: bed sizes with no CYC class ("superking" is the UK 6 ft bed) and
                 # bed, cot and occasion words that name a size the template does not keep:
                 # a bedspread or coverlet covers a bed (bound only with a named bed class,
                 # `BED_COVER`), a bassinet blanket is its own small size, a picnic, travel or
                 # beach blanket is sold in its own sizes, and a "grand" one is a size claim.
                 # None has a cited band here, so each is refused rather than drafted at the
                 # throw default.
                 r"\bsuperking\b", r"\bemperor\b", r"\bbedspreads?\b", r"\bcoverlets?\b",
                 r"\bbassinets?\b", r"\bmoses\b", r"\bcradle\b", r"\bpram\b", r"\bpicnic\b",
                 r"\btravel\b", r"\bbeach\b", r"\bstadium\b", r"\bcamping\b", r"\bgrand\b")
# A bed cover word is bound when the title names the bed class it covers ("Queen Coverlet").
BED_COVER = r"\b(?:bedspread|coverlet)s?\b"
BED_CLASSES = ("twin", "full", "queen", "king")
# S1F3-M1: compounds and variants of the bed-size words, normalised before any size word is
# read: "Kingsize" is "king size", "Calking" is "california king", "Super King" is the UK
# superking (refused above), never the CYC king.
SIZE_COMPOUNDS = ((r"\b(king|queen|twin|full|double)-?size(d?)\b", r"\1 size\2"),
                  (r"\bcal(?:ifornia)?-?king\b", "california king"),
                  (r"\bsuper[- ]?king\b", "superking"))
# A unit word left with no figure ("... by fifty inches") is a size the parser did not bind.
_STRAY_UNIT = (r"\b(?:cm|mm|centimet(?:er|re)s?|millimet(?:er|re)s?|inch(?:es)?|yards?|yds?|"
               r"met(?:er|re)s?)\b")

# The allow-list: the only figures and size-like words a title may carry that are not a size,
# each with its reason and its test (tests/test_s1_product_truth_3.py). Count, colour and grade
# entries are BOUND to what the CIR states (`facts_of`); a value the CIR does not state is
# unbound. Everything else that looks like a figure or a size word is refused.
def _table_grades() -> list[str]:
    from ..cir.graded import FOOT, HEAD

    names = {b.size.lower() for t in (HEAD, FOOT) for b in t.sizes}
    return [re.escape(n) for n in sorted(names, key=len, reverse=True)]


_TABLE_GRADES = _table_grades()

ALLOWED_NON_SIZE: dict[str, dict] = {
    "n_in_1": {"re": r"\b[2-4][- ]?in[- ]?1\b",
               "basis": "'2 in 1' is a product-versatility idiom (two uses), not 2 inches"},
    "count": {"re": (rf"\bset of {_COUNT}\b|\bpack of {_COUNT}\b|\(\s*{_COUNT}\s*\)|"
                     rf"\b{_COUNT}[- ]?(?:piece|pc)s?\b|\b{_COUNT}[- ]?pack\b|\bx ?(\d+)\b"),
              "bind": "pieces",
              "basis": "a set count ('Set of 4', '(6)') is the number of pieces the pattern "
                       "makes: bound to the CIR's single component's make count"},
    "colours": {"re": rf"\b{_COUNT}[- ]?(?:colou?r(?:s|ed|way)?|tone[sd]?)\b",
                "bind": "colours",
                "basis": "a colour count ('Two-Colour') is the number of yarn colours: bound "
                         "to the CIR's colour table"},
    # Bound first, before any other parser reads the title (`_bind_grades`): "XL" and "2X" in
    # "(size XL)" are the grade, not a relative word or a dangling "2 x".
    # ENG-GARMENT-2: the CYC head and foot charts name their sizes in words ("Preemie",
    # "Woman 7-9.5"); those exact names are grades too, bound the same way.
    "grade": {"re": r"\(?\bsize (" + "|".join(_TABLE_GRADES) + r"|[a-z0-9]{1,4})\b\)?",
              "bind": "grade", "prepass": True,
              "basis": "a garment size ('(size 2X)') is the CYC grade the CIR is graded to: "
                       "bound to CIR.grading.size"},
    # S1F3-H1: an EXACT, cited list. The earlier `[a-w][a-z]*\d+` shape let any letter-led
    # figure through as a "code", so the size tokens "L300", "W60 H60" and "sz60" certified
    # at the template size. Only these two kinds pass now; any other letter-led figure is a
    # lettered dimension (`_bind_lettered`) or an unbound size token.
    # Bound first (`_protect_codes`), before the lettered dimensions read the title: "L-11" is
    # the 8 mm hook, not a length of 11.
    "code": {"re": (r"(?<![a-z0-9])(?:c2c|"
                    r"(?:b-1|c-2|d-3|e-4|f-5|g-6|h-8|i-9|j-10|k-10(?:\.5| ?1[/\u2044]2)?|l-11|"
                    r"m-13|n-13|m/n-13|n-15|p-15|n/p-15)(?: hook)?)(?![a-z0-9.])"),
             "prepass": True,
             "basis": "'C2C' is corner-to-corner, a technique; the letter-number pairs are US "
                      "crochet hook sizes (B-1 2.25 mm ... K-10.5 6.5 mm, L-11 8 mm, M/N-13 9 mm, "
                      "N/P-15 10 mm), Craft Yarn Council, Hooks chart (craftyarncouncil.com/"
                      "standards/hooks): a tool size, not a dimension of the piece"},
    # S1F3-LOW: three non-size figures that were refused and cost sales.
    "percent": {"re": r"(?<![\d.])(?:100|[1-9]?\d)(?:\.\d+)? ?%",
                "basis": "a percentage ('100% Cotton') is fibre content, never a length"},
    "ply": {"re": r"\b(?:2|3|4|5|8|10|12|14)[- ]?ply\b",
            "basis": "'4ply', '8 ply' are the UK/AU/NZ names of yarn weights (Craft Yarn "
                     "Council, Standard Yarn Weight System, craftyarncouncil.com/standards/"
                     "yarn-weight-system): a yarn, not a dimension"},
    "number": {"re": (r"\bno\.? ?\d{1,3}\b(?![.,/⁄]\d)"
                      r"(?! ?(?:x\b|by\b|cm|mm|in\b|inch|ft|feet|foot|m\b|met|yd|yard|\"|'))"),
               "basis": "'No. 5' is a design number in a series (or a thread size), a name, not "
                        "a dimension; a 'no' followed by a unit or 'x' is not this"},
}

# What the fallback drafts, for binding at plan time: one piece of one component (a cushion is a
# front and a back, so it has no single piece count), no garment grade, and a palette from
# `runtime.pipeline._PALETTES` (S1F3-LOW: the colour count is bound at plan to the counts those
# palettes have, `fallback_colour_counts`, so the plan never drafts a "3 Colour" title that
# certification then refuses).
FALLBACK_FACTS = {"pieces": 1, "colours": None, "grade": None, "at_plan": True}


def fallback_colour_counts() -> frozenset[int]:
    """Every colour count a fallback draft can have: the sizes of the palettes
    `runtime.pipeline.concept_geometry` chooses from."""
    from ..runtime.pipeline import _DEFAULT_PALETTE, _PALETTES

    return frozenset(len(p) for p in (*_PALETTES.values(), _DEFAULT_PALETTE))


def facts_of(cir) -> dict:
    """The facts a title's counts bind to, read from the CIR."""
    comps = list(getattr(cir, "components", None) or [])
    pieces = int(getattr(comps[0], "make", 1) or 1) if len(comps) == 1 else None
    colours = getattr(cir, "colors", None)
    grading = getattr(cir, "grading", None)
    return {"pieces": pieces, "colours": len(colours) if colours else None,
            "grade": (str(grading.size).lower() if grading is not None
                      and getattr(grading, "size", None) else None),
            "at_plan": False}


def _count_value(text: str) -> int | None:
    if text is None:
        return None
    return int(text) if text.isdigit() else _NUMBER_VALUE.get(text)


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _bind_grades(sized: str, facts: dict | None) -> tuple[str, list[str]]:
    """The title with each "size <grade>" phrase blanked, and why for each one the CIR's
    grading does not state."""
    facts = facts or FALLBACK_FACTS
    entry = ALLOWED_NON_SIZE["grade"]
    out: list[str] = []
    for m in list(re.finditer(entry["re"], sized)):
        if m.group(1).lower() != facts.get("grade"):
            made = ("the fallback drafts no graded size" if facts.get("at_plan")
                    else f"the pattern's graded size is {facts.get('grade') or 'not stated'}")
            out.append(f"unbound size token: {m.group(0).strip()} (a graded size the pattern "
                       f"does not make: {made}; {entry['basis']})")
        sized = _blank(sized, m.start(), m.end())
    return sized, out


def _residual_unbound(rest: str, obj: str | None, facts: dict | None) -> list[str]:
    """Every size token left in `rest` (the title with its bound claims blanked out): the
    allow-list is bound or refused, then any figure, number word or size word left is
    `unbound size token: <token>`."""
    facts = facts or FALLBACK_FACTS
    out: list[str] = []
    for key, entry in ALLOWED_NON_SIZE.items():
        if entry.get("prepass"):
            continue
        for m in list(re.finditer(entry["re"], rest)):
            bind = entry.get("bind")
            token = m.group(0).strip()
            if bind:
                raw = next((g for g in m.groups() if g is not None), None)
                if bind == "grade":
                    want, have = (raw or "").lower(), facts.get("grade")
                else:
                    want, have = _count_value(raw), facts.get(bind)
                if bind == "colours" and facts.get("at_plan"):
                    counts = fallback_colour_counts()
                    if want not in counts:
                        out.append(f"unbound size token: {token} (a colour count the fallback "
                                   f"does not draft: its palettes have "
                                   f"{' or '.join(str(n) for n in sorted(counts))} colours; "
                                   f"{entry['basis']})")
                elif want is None or have is None or want != have:
                    what = {"pieces": "piece count", "colours": "colour count",
                            "grade": "graded size"}[bind]
                    made = ("the fallback drafts one piece and no graded size"
                            if facts.get("at_plan") and bind != "colours"
                            else f"the pattern's {what} is {have if have is not None else 'not stated'}")
                    out.append(f"unbound size token: {token} (a {what} the pattern does not "
                               f"make: {made}; {entry['basis']})")
            rest = _blank(rest, m.start(), m.end())
    tokens: list[tuple[int, str, str]] = []
    for m in re.finditer(r"[a-z]*\d+(?:[.,/\u2044]\d+)*[a-z]*|[\u00bc-\u00be\u2150-\u215e]",
                         rest):
        tokens.append((m.start(), m.group(0), "a figure with no unit and no claim it binds to"))
    for m in re.finditer(rf"\b{_NUMBER_WORD}\b", rest):
        tokens.append((m.start(), m.group(0), "a number word"))
    vocab = SIZE_CLASS_VOCAB + (BEDDING_VOCAB if obj in ("blanket", "pillow") else ())
    for pat in vocab:
        for m in re.finditer(pat, rest):
            tokens.append((m.start(), m.group(0),
                           f"a size-class word the {(obj or 'object').replace('_', ' ')} "
                           f"family does not define from a cited standard"))
    for m in re.finditer(_STRAY_UNIT, rest):
        tokens.append((m.start(), m.group(0), "a unit with no figure the parser could bind"))
    seen: set[int] = set()
    for pos, tok, why in sorted(tokens):
        if pos in seen:
            continue
        seen.add(pos)
        out.append(f"unbound size token: {tok} ({why}; D-S1-FAIL-CLOSED)")
    return out

# Objects the fallback has a correct flat template and a band for, by the family word in the
# title (`gates.first_customer.PRODUCT_TYPE_FAMILIES`) or, when the title names none, by the
# radar category. `None` for a category means the category's template is a strip with no
# object behind it: the title must name a supported object or the draft is refused.
CATEGORY_OBJECT: dict[str, str | None] = {
    "blanket": "blanket", "mosaic_blanket": "blanket", "graphghan": "blanket",
    "runner": "runner", "placemat": "placemat", "dishcloth": "dishcloth",
    "coaster": "coaster", "pillow": "pillow", "wedding": "pillow", "wall_decor": "wall_hanging",
    "pet": "pet_mat", "scarf": "scarf",
    "baby": None, "seasonal_decor": None, "flower": None, "ornament": None,
}
SUPPORTED_FLAT = frozenset({"blanket", "runner", "placemat", "dishcloth", "coaster", "pillow",
                            "wall_hanging", "pet_mat", "scarf", "burp_cloth"})

# M1: named flat objects with no size band and no correct template. Refused by name rather than
# drafted as the default 32 x 9.8 cm panel (or another object's template) under that name.
NO_TEMPLATE: dict[str, str] = {
    # ENG-PLUSH slice 3: a lovey is no longer here -- `creative.baby.lovey` makes the stuffed
    # head, the square (LOVEY_SQUARE_CM, a stated design size) and the join between them.
    r"\bbibs?\b": "a bib needs a shaped neck opening and a tie or fastening; a flat rectangle "
                  "is not a bib",
    r"\brugs?\b": "a rug needs its own size band, a firm fabric and a non-slip backing",
    r"\bbath ?mats?\b": "a bath mat needs its own size band and a dense, absorbent fabric",
    r"\b(?:table ?cloth|tablecloth)s?\b": "a tablecloth is sized to a table; there is no band "
                                          "or template for it",
    r"\bhot ?pads?\b|\bpot ?holders?\b|\btrivets?\b": (
        "a hot pad needs a double-thickness heat-safe fabric and its own band"),
    r"\bdoil(?:y|ies)\b": "a doily is a lace motif worked in the round, not a flat panel",
    r"\bpoufs?\b|\bpouffes?\b|\bottomans?\b": "a pouf is a stuffed three-dimensional form",
}

BURP_CLOTH = r"\bburp ?(?:cloth|rag)s?\b"
# S1F-LOW: a pet mat and a tapestry are read from the title too, so their bands apply at
# certification (where there is no radar category). "Tapestry crochet" is a technique.
PET_MAT = r"\b(?:pet|dog|cat|puppy|kitten|crate)\b(?:\s+[a-z']+){0,2}?\s+mats?\b"
TAPESTRY = r"\btapestr(?:y|ies)\b(?!\s+(?:crochet|stitch))|\bwall (?:art|decor)\b"

# S1F-M1 (D-S1-RELATIVE-SIZE): every relative size word. One rule for all of them: bound by
# stated dimensions, or by a defined size family for the object (a class whose words include
# it: only the large blanket), or refused. A length word binds a single figure to the length,
# a width word to the width.
# S1F2-M1: "medium" is a relative size word too (between small and large): it is bound by
# stated dimensions or a defined family exactly as "small" and "large" are.
RELATIVE_SIZE = (r"\b(?:extra[- ]?large|x-?large|xxl|xl|extra[- ]?long|oversized?|giant|jumbo|"
                 r"huge|large|big|medium|small|mini|tiny|petite|short|long|skinny|slim|wide|"
                 r"narrow)\b")
LENGTH_WORDS = ("short", "long", "extra long", "extra-long", "extralong")
WIDTH_WORDS = ("skinny", "slim", "wide", "narrow")

# ---- stated dimensions -----------------------------------------------------------------------
# A unit is cm, mm, m, inches ("in" only when no figure follows it: "2 in 1" is not 2 inches),
# feet. `''` and `"` are inches, a single `'` is feet.
# S1F2-H1: yards ("3 yards", "60 yd") are a unit too (1 yd = 36 in = 91.44 cm).
# S1F3-LOW: only a bare "in" refuses a following figure ("2 in 1"); "inches" never does
# ("50 x 60 inches 2 in 1" is 50 x 60 in and the idiom).
_UNIT = (r"(cm|centimet(?:er|re)s?|mm|millimet(?:er|re)s?|inch(?:es)?(?![a-z])|in(?![a-z])(?!\s*\d)"
         r"|\"|''|ft|feet|foot|'|y(?:ar)?ds?(?![a-z])|m(?:et(?:er|re)s?)?(?![a-z]))")
# A figure is a whole number token: never the "2" of "1/2", "1,5" or "1.5.3" (S1F2-H1).
_NUM = r"(?<![\d.,/\u2044])(\d+(?:\.\d+)?)(?![\d,/\u2044]|\.\d)"
_BY = r"\s*(?:x|×|by)\s*"
_DIMS = re.compile(rf"{_NUM}\s*{_UNIT}?{_BY}{_NUM}\s*{_UNIT}?(?:{_BY}{_NUM}\s*{_UNIT}?)?")
_DIM1 = re.compile(rf"{_NUM}\s*{_UNIT}")
_DANGLING = re.compile(r"\d\s*(?:x|×)(?![a-z])|(?<![a-z])(?:x|×)\s*\d")
# S1F3-H1: a lettered dimension is a size claim. L and H are the length (on a flat piece its
# height is its length), W the width, D / Dia a diameter and Sz a size: "L300", "W60 H60",
# "W130cm L170cm", "d50", "sz60". The hook sizes in ALLOWED_NON_SIZE["code"] ("L-11", "H-8")
# are taken out first.
_LETTERED = re.compile(rf"(?<![a-z0-9])(sz|dia|[lwhd])\s*[:=-]?\s*{_NUM}\s*{_UNIT}?(?![a-z0-9])")


def _protect_codes(sized: str) -> str:
    """The title with the cited codes (C2C, hook sizes) blanked: they are not sizes."""
    for m in list(re.finditer(ALLOWED_NON_SIZE["code"]["re"], sized)):
        sized = _blank(sized, m.start(), m.end())
    return sized


def _bind_lettered(sized: str) -> tuple[str, list[str]]:
    """The title with its lettered dimensions rewritten as the stated dimensions they are
    ("W130cm L170cm" -> "130cm x 170cm"; "L300cm" -> "long 300cm"), so the one dimension
    parser binds them (a unitless pair under D-S1-UNITLESS-DIMS, a unitless single figure is
    unbound); and why for each one that cannot be bound (a diameter, a size code, two widths
    or two lengths)."""
    found = list(_LETTERED.finditer(sized))
    if not found:
        return sized, []
    out: list[str] = []
    widths = [m for m in found if m.group(1) == "w"]
    lengths = [m for m in found if m.group(1) in ("l", "h")]
    for m in found:
        if m.group(1) in ("d", "dia"):
            out.append(f"unbound size token: {m.group(0).strip()} (a diameter; the fallback "
                       f"drafts no round piece, so it cannot be bound; D-S1-FAIL-CLOSED)")
        elif m.group(1) == "sz":
            out.append(f"unbound size token: {m.group(0).strip()} (a size code with no unit "
                       f"and no size class it binds to; D-S1-FAIL-CLOSED)")
    if len(widths) + len(lengths) == 1 and not (widths + lengths)[0].group(3):
        m = (widths + lengths)[0]
        out.append(f"unbound size token: {m.group(0).strip()} (a lettered "
                   f"{'width' if widths else 'length'} with no unit: a single figure's unit "
                   f"cannot be determined; D-S1-FAIL-CLOSED)")
        widths, lengths = [], []
    if len(widths) > 1 or len(lengths) > 1:
        out.append(f"unbound size token: {' '.join(m.group(0).strip() for m in widths + lengths)}"
                   f" (the title states {len(widths)} widths and {len(lengths)} lengths; a flat "
                   f"piece has one of each; D-S1-FAIL-CLOSED)")
        widths, lengths = [], []
    for m in found:
        sized = _blank(sized, m.start(), m.end())
    fig = lambda m: f"{m.group(2)}{m.group(3) or ''}"  # noqa: E731
    if widths and lengths:
        sized += f" {fig(widths[0])} x {fig(lengths[0])}"
    elif widths:
        sized += f" wide {fig(widths[0])}"
    elif lengths:
        sized += f" long {fig(lengths[0])}"
    return sized, out


def _unit_cm(unit: str) -> float:
    if unit in ("''", '"'):
        return INCH_CM
    if unit == "'":
        return 30.48
    if unit.startswith("mm") or unit.startswith("mil"):
        return 0.1
    if unit.startswith("me") or unit == "m":
        return 100.0
    if unit.startswith(("ft", "fe", "fo")):
        return 30.48
    if unit.startswith("y"):
        return 91.44
    if unit.startswith("i"):
        return INCH_CM
    return 1.0


def _cm(value: str, unit: str | None) -> float:
    return round(float(value) * _unit_cm(unit), 1) if unit else float(value)


def _tokens(title: str | None) -> tuple[list[dict], list[str]]:
    """The size-bearing figures in a title, and the ones that cannot be read.

    Each token: {"values": raw figures, "units": unit per figure (None when unstated)}. A unit
    stated on one figure of a pair applies to the other ("12 x 24 in", '18" x 12').
    """
    text = (title or "").lower().replace("×", "x")
    toks: list[dict] = []
    unread: list[str] = []
    rest = text
    for m in _DIMS.finditer(text):
        values = [g for g in (m.group(1), m.group(3), m.group(5)) if g is not None]
        units = [m.group(2), m.group(4), m.group(6)][:len(values)]
        known = [u for u in units if u]
        units = [u or (known[-1] if known else None) for u in units]
        toks.append({"text": m.group(0).strip(), "values": values, "units": units})
        rest = rest.replace(m.group(0), " " * len(m.group(0)), 1)
    for m in _DIM1.finditer(rest):
        toks.append({"text": m.group(0).strip(), "values": [m.group(1)], "units": [m.group(2)]})
        rest = rest.replace(m.group(0), " " * len(m.group(0)), 1)
    for m in _DANGLING.finditer(rest):
        unread.append(m.group(0).strip())
    return toks, unread


def stated_dimensions(title: str | None) -> tuple[float, ...]:
    """The dimensions a title states with a unit, in cm: (short, long), (one,) or ()."""
    toks, _ = _tokens(_fold(title))
    for t in toks:
        if all(t["units"]) and len(t["values"]) <= 2:
            cm = [_cm(v, u) for v, u in zip(t["values"], t["units"])]
            return tuple(sorted(cm))
    return ()


# S1F2-LOW: typographic quotes and primes are the inch and foot marks they stand for
# ('Linen Throw 50”x60”' is 50 x 60 in). NFKC (fold_title) turns a double prime into two
# primes, so the doubles are mapped first.
_QUOTES = {"\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
           "\u2036": '"', "\u3003": '"', "\uff02": '"', "\u2018": "'", "\u2019": "'",
           "\u201a": "'", "\u201b": "'", "\u2032": "'", "\u2035": "'", "\u00b4": "'",
           "\uff07": "'",
           # S1F3-LOW: the modifier-letter primes ("60\u02ba") are inch and foot marks too.
           "\u02ba": '"', "\u02ee": '"', "\u02b9": "'", "\u02bc": "'"}


def _fold(title: str | None) -> str:
    from .fallback_constructions import fold_title

    text = "".join(_QUOTES.get(ch, ch) for ch in (title or ""))
    return fold_title(text)


def _sized_text(title: str | None) -> str:
    """The folded title with the non-size phrases removed: what size words are read from."""
    folded = _fold(title)
    for p in NON_SIZE_PHRASES:
        folded = re.sub(p, " ", folded)
    for p, repl in SIZE_COMPOUNDS:
        folded = re.sub(p, repl, folded)
    return re.sub(r"\s+", " ", folded).strip()


def _has(words, folded: str) -> list[str]:
    return [w for w in words if re.search(rf"\b{re.escape(w)}\b", folded)]


def object_of(category: str | None, title: str | None) -> str | None:
    """The banded flat object a title (else its category) names, or None."""
    from ..gates.first_customer import _family_hits

    folded = _fold(title)
    if re.search(BURP_CLOTH, folded):
        return "burp_cloth"
    hits = set(_family_hits(title or ""))
    # A cushion, mat or scarf first: "Throw Pillow" is a pillow, not a throw.
    for family, obj in (("pillow", "pillow"), ("runner", "runner"), ("placemat", "placemat"),
                        ("dishcloth", "dishcloth"), ("coaster", "coaster"), ("scarf", "scarf"),
                        ("wall_hanging", "wall_hanging"), ("blanket", "blanket")):
        if family in hits:
            return obj
    if not hits and re.search(PET_MAT, folded):
        return "pet_mat"
    if not hits and re.search(TAPESTRY, folded):
        return "wall_hanging"
    if not hits and re.search(BED_COVER, folded):
        # S1F3-M1: a bedspread or coverlet is a blanket for a bed, held to its bed class.
        return "blanket"
    return CATEGORY_OBJECT.get(category or "")


def named_classes(obj: str | None, title: str | None) -> dict[str, dict]:
    """The size classes the title names for `obj` (blanket / pillow), or {}."""
    folded = _sized_text(title)
    table = BLANKET_CLASSES if obj == "blanket" else PILLOW_CLASSES if obj == "pillow" else {}
    return {k: c for k, c in table.items() if _has(c["words"], folded)}


def band(obj: str | None) -> dict | None:
    """The family band (`gates.certificate.OBJECT_SIZE_BANDS` shape) for `obj`, or None."""
    from ..gates.certificate import OBJECT_SIZE_BANDS

    return OBJECT_SIZE_BANDS.get(obj or "")


def _in_band(b: dict, short: float, long_: float) -> bool:
    if "side_cm" in b:
        lo, hi = b["side_cm"]
        return lo <= short and long_ <= hi and long_ / max(short, 1e-9) <= b["max_aspect"]
    (slo, shi), (llo, lhi) = b["short_cm"], b["long_cm"]
    return slo <= short <= shi and llo <= long_ <= lhi


def _in_class(c: dict, short: float, long_: float) -> bool:
    aspect = long_ / max(short, 1e-9)
    return (c["short"][0] <= short <= c["short"][1] and c["long"][0] <= long_ <= c["long"][1]
            and aspect >= c.get("min_aspect", 0.0))


def _met(stated: float, made: float) -> bool:
    return abs(stated - made) <= max(TOLERANCE_CM, TOLERANCE_REL * stated)


def _fits(obj: str | None, classes: dict, short: float, long_: float) -> bool:
    """Inside every named class and the object's family band."""
    b = band(obj)
    return (b is not None and _in_band(b, short, long_)
            and all(_in_class(c, short, long_) for c in classes.values()))


def _class_target(obj: str | None, classes: dict) -> tuple[tuple[float, float] | None, str]:
    """The size drafted for the named classes: the first class's default where every class
    holds it, else the middle of their common band; None and why when they share no size."""
    s_lo = max(c["short"][0] for c in classes.values())
    s_hi = min(c["short"][1] for c in classes.values())
    l_lo = max(c["long"][0] for c in classes.values())
    l_hi = min(c["long"][1] for c in classes.values())
    if s_lo > s_hi or l_lo > l_hi:
        bases = "; ".join(f"{k}: {c['short'][0]:g}-{c['short'][1]:g} x "
                          f"{c['long'][0]:g}-{c['long'][1]:g} cm" for k, c in classes.items())
        return None, (f"the title names {' and '.join(classes)}, and no size is all of them "
                      f"({bases}); one pattern makes one size")
    table = BLANKET_CLASSES if obj == "blanket" else PILLOW_CLASSES
    first = next(k for k in table if k in classes)
    ds, dl = table[first]["default"]
    pick = lambda d, lo, hi: d if lo <= d <= hi else round((lo + hi) / 2, 1)  # noqa: E731
    return (pick(ds, s_lo, s_hi), pick(dl, l_lo, l_hi)), ""


# S1F2-LOW: a blanket for a pet is not a person's blanket. The CYC classes (and the large
# family built on them) are human bed and throw sizes, and no cited pet-blanket band exists, so
# a size word on a pet blanket is unbound ("XL Dog Blanket" was drafted 153.6 x 202.9 cm).
PET_BLANKET = r"\b(?:pet|dog|doggy|doggie|cat|kitty|puppy|kitten|crate|kennel)s?\b"


def claims(category: str | None, title: str | None, facts: dict | None = None) -> dict:
    """Every size-bearing token in the title, bound to what the twin must be, or unbound.

    Returns {"object", "classes": {name: class}, "dims": (short, long) | None,
    "single": (cm, "short" | "long" | "square") | None, "relative": [words],
    "unbound": [why...], "inferred": note | ""}. `unbound` is non-empty when any token cannot
    be bound to one size of the twin; callers refuse on it, never pass.
    """
    obj = object_of(category, title)
    sized, graded = _bind_grades(_sized_text(title), facts)
    sized, lettered = _bind_lettered(_protect_codes(sized))
    graded += lettered
    classes = named_classes(obj, title)
    pet = obj == "blanket" and bool(re.search(PET_BLANKET, sized))
    if pet:
        classes = {}
    out = {"object": obj, "classes": classes, "dims": None, "single": None, "relative": [],
           "unbound": list(graded), "relative_unbound": [], "inferred": ""}
    noun = (obj or "object").replace("_", " ")
    toks, unread = _tokens(sized)
    for u in unread:
        out["unbound"].append(f"the title has a figure the size parser cannot read ({u!r})")
    b = band(obj)
    bound: list[tuple[float, ...]] = []
    for t in toks:
        if len(t["values"]) == 3:
            out["unbound"].append(f"the title states three dimensions ({t['text']!r}); a flat "
                                  f"{noun} has two")
            continue
        if all(t["units"]):
            bound.append(tuple(sorted(_cm(v, u) for v, u in zip(t["values"], t["units"]))))
            continue
        # D-S1-UNITLESS-DIMS: a unitless pair is read in the one unit (cm or inches) that puts
        # it inside the object's band and every named class; both or neither -> refused.
        fits = []
        for unit, label in (("cm", "cm"), ("in", "in")):
            s_, l_ = sorted(_cm(v, unit) for v in t["values"])
            if _fits(obj, classes, s_, l_):
                fits.append((label, (s_, l_)))
        if len(fits) == 1:
            bound.append(fits[0][1])
            out["inferred"] = (f"{t['text']!r} read as {fits[0][0]} (D-S1-UNITLESS-DIMS: the "
                               f"only unit that puts it inside the {noun} band)")
        else:
            which = ("both cm and in fit" if fits else "neither cm nor in fits")
            out["unbound"].append(
                f"the title states {t['text']!r} with no unit, and the unit cannot be "
                f"determined: {which} the {noun} band{' (' + b['basis'] + ')' if b else ''} "
                f"(D-S1-UNITLESS-DIMS)")
    distinct: list[tuple[float, ...]] = []
    for d in bound:
        if not any(len(d) == len(e) and all(_met(x, y) for x, y in zip(d, e))
                   for e in distinct):
            distinct.append(d)
    if len(distinct) > 1:
        out["unbound"].append(f"the title states {len(distinct)} different sizes "
                              f"({', '.join(' x '.join(f'{v:g}' for v in d) for d in distinct)} "
                              f"cm); one pattern makes one size")
    elif distinct:
        d = distinct[0]
        if len(d) == 2:
            out["dims"] = (d[0], d[1])
        else:
            role = ("long" if _has(LENGTH_WORDS, sized) else
                    "short" if _has(WIDTH_WORDS, sized) else "")
            out["single"] = (d[0], role)
    # D-S1-FAIL-CLOSED: stated dimensions bind only to an object this module holds to a band.
    if (out["dims"] or out["single"]) and obj not in SUPPORTED_FLAT and not classes:
        stated = out["dims"] or (out["single"][0],)
        out["unbound"].append(
            f"the title states {' x '.join(f'{v:g}' for v in stated)} cm for "
            f"{'a ' + noun if obj else 'an object'} with no size band here, so the size cannot "
            f"be checked (D-S1-FAIL-CLOSED)")
        out["dims"] = out["single"] = None
    rel = [m.group(0) for m in re.finditer(RELATIVE_SIZE, sized)]
    out["relative"] = rel
    class_words = {w for c in classes.values() for w in c["words"]}
    for word in rel:
        if word in class_words or out["dims"] or out["single"]:
            continue
        family = ("a pet blanket has no cited size band (the CYC classes are human sizes)"
                  if pet else f"a {noun} has no defined size family for it")
        why = (f"the title names a relative size ({word!r}) with no dimensions, and {family} "
               f"(D-S1-RELATIVE-SIZE); the template makes one size and cannot back a relative "
               f"size word")
        out["unbound"].append(why)
        out["relative_unbound"].append(why)
    # D-S1-FAIL-CLOSED: everything the claims above did not bind is refused by token.
    rest = sized
    for t in toks:
        i = rest.find(t["text"])
        if i >= 0:
            rest = _blank(rest, i, i + len(t["text"]))
    for u in unread:
        i = rest.find(u)
        if i >= 0:
            rest = _blank(rest, i, i + len(u))
    for w in sorted(class_words, key=len, reverse=True):
        for m in list(re.finditer(rf"\b{re.escape(w)}\b", rest)):
            rest = _blank(rest, m.start(), m.end())
    for m in list(re.finditer(RELATIVE_SIZE, rest)):
        rest = _blank(rest, m.start(), m.end())
    if set(classes) & set(BED_CLASSES):
        # S1F3-M1: "Queen Coverlet" -- the bed cover is bound by the bed class it names.
        for m in list(re.finditer(BED_COVER, rest)):
            rest = _blank(rest, m.start(), m.end())
    out["unbound"].extend(_residual_unbound(rest, obj, facts))
    return out


def applies(category: str | None, title: str | None) -> bool:
    """Whether the title or category is a flat object this module decides the size of."""
    folded = _fold(title)
    return ((category or "") in CATEGORY_OBJECT or object_of(category, title) is not None
            or any(re.search(p, folded) for p in NO_TEMPLATE))


def _single_target(obj: str, b: dict, value: float, role: str) -> tuple[tuple | None, str]:
    """One figure: a square object's side; an oblong object's length or width -- the side a
    length/width word names, else the one side whose band holds it."""
    noun = obj.replace("_", " ")
    if "side_cm" in b:
        lo, hi = b["side_cm"]
        if not lo <= value <= hi:
            return None, (f"the title asks for a {noun} {value:g} cm a side; the {noun} band "
                          f"is {lo:g}-{hi:g} cm ({b['basis']})")
        return (value, value), ""
    (slo, shi), (llo, lhi) = b["short_cm"], b["long_cm"]
    as_long, as_short = llo <= value <= lhi, slo <= value <= shi
    if role == "long" or (not role and as_long and not as_short):
        if not as_long:
            return None, (f"the title asks for a {noun} {value:g} cm long; the {noun} band is "
                          f"{llo:g}-{lhi:g} cm long ({b['basis']})")
        return (round((slo + shi) / 2 if obj != "runner" else 35.0, 1), value), ""
    if role == "short" or (not role and as_short and not as_long):
        if not as_short:
            return None, (f"the title asks for a {noun} {value:g} cm wide; the {noun} band is "
                          f"{slo:g}-{shi:g} cm wide ({b['basis']})")
        return (value, round((llo + lhi) / 2, 1)), ""
    which = ("both the width ({w}) and the length ({l})" if as_long and as_short
             else "neither the width ({w}) nor the length ({l})")
    which = which.format(w=f"{slo:g}-{shi:g} cm", l=f"{llo:g}-{lhi:g} cm")
    return None, (f"the title states one dimension ({value:g} cm), which is {which} of a "
                  f"{noun}, so it cannot be bound to one side ({b['basis']})")


def request(category: str | None, title: str | None) -> dict:
    """What size the title asks for, and whether the fallback can make it.

    Returns {"object", "classes", "dims", "target": (short, long) | None, "refused": why | None}.
    `target` is None when the template's own size is the answer (no size token at all).
    """
    folded = _fold(title)
    obj = object_of(category, title)
    out = {"object": obj, "classes": [], "dims": stated_dimensions(title), "target": None,
           "refused": None}
    for pattern, why in NO_TEMPLATE.items():
        if re.search(pattern, folded):
            out["refused"] = f"{why}: there is no size band and no correct template for it"
            return out
    if obj is None:
        out["refused"] = (f"the title names no object with a size band and a correct flat "
                          f"template (category {category!r} has none of its own), so the "
                          f"fallback would draft the default panel under that name")
        return out
    c = claims(category, title)
    classes = c["classes"]
    out["classes"] = sorted(classes)
    if c["unbound"]:
        out["refused"] = c["unbound"][0]
        return out
    b = band(obj)
    if classes:
        target, why = _class_target(obj, classes)
        if target is None:
            out["refused"] = why
            return out
        out["target"] = target
    if c["single"] is not None:
        if b is None:
            out["refused"] = (f"the title states one dimension ({c['single'][0]:g} cm) for a "
                              f"{obj.replace('_', ' ')}, which has no size band")
            return out
        target, why = _single_target(obj, b, *c["single"])
        if target is None:
            out["refused"] = why
            return out
        out["dims"] = (c["single"][0],)
        out["target"] = target
    elif c["dims"] is not None:
        short, long_ = c["dims"]
        out["dims"] = c["dims"]
        fits = [k for k, cl in classes.items() if not _in_class(cl, short, long_)]
        if fits:
            out["refused"] = (f"the title asks for {short:g} x {long_:g} cm and names "
                              f"{', '.join(sorted(classes))}, whose band does not hold it "
                              f"({', '.join(fits)})")
            return out
        if b is None or not _in_band(b, short, long_):
            where = f" ({b['basis']})" if b else ""
            out["refused"] = (f"the title asks for a {obj.replace('_', ' ')} of {short:g} x "
                              f"{long_:g} cm, outside the size the family is made in{where}")
            return out
        out["target"] = (short, long_)
    elif not classes and obj == "burp_cloth":
        out["target"] = BURP_CLOTH_SIZE
    return out


# A burp cloth: about 25 x 50 cm (10 x 20 in), the size sold and written for.
BURP_CLOTH_SIZE = (25.0, 50.0)

UNBOUND = "OBJECT_SIZE_UNBOUND"
NOT_AS_TITLED = "OBJECT_SIZE_NOT_AS_TITLED"
OUT_OF_BAND = "OBJECT_SIZE_OUT_OF_BAND"
# Objects whose band `gates.certificate.object_size_findings` cannot reach by a product-type
# family word, so this module checks it (S1F-LOW).
_TITLE_ONLY_BANDS = ("pet_mat", "burp_cloth", "wall_hanging")


def coded_findings(title: str | None, width_cm: float, height_cm: float,
                   category: str | None = None, facts: dict | None = None
                   ) -> list[tuple[str, str]]:
    """(code, why) for each way the finished size does not match the size the title claims:
    OBJECT_SIZE_UNBOUND for a size token that cannot be bound, OBJECT_SIZE_NOT_AS_TITLED for a
    bound claim the twin does not meet, OBJECT_SIZE_OUT_OF_BAND for a title-only band."""
    if not width_cm or not height_cm:
        return []
    from ..gates.first_customer import _family_hits

    short, long_ = sorted((float(width_cm), float(height_cm)))
    c = claims(category, title, facts)
    obj, classes = c["object"], c["classes"]
    out: list[tuple[str, str]] = []
    # D-S1-FAIL-CLOSED: every unbound token is reported for every title. Relative words alone
    # stay with the objects this module sizes: a vessel's small / medium / large is bound by
    # the vessel route (`fallback_constructions._basket_size`, products.vessels.BASKET_SIZES).
    flat = obj in SUPPORTED_FLAT or bool(classes)
    for why in c["unbound"]:
        if why in c["relative_unbound"] and not flat:
            continue
        out.append((UNBOUND, f"{why}; the size the title claims cannot be checked against "
                             f"the pattern's {short:.1f} x {long_:.1f} cm"))
    missed = {k: cl for k, cl in classes.items() if not _in_class(cl, short, long_)}
    if missed:
        names = ", ".join(sorted(missed))
        bases = "; ".join(f"{k}: {cl['short'][0]:g}-{cl['short'][1]:g} x "
                          f"{cl['long'][0]:g}-{cl['long'][1]:g} cm ({cl['basis']})"
                          for k, cl in sorted(missed.items()))
        out.append((NOT_AS_TITLED, f"the title names a {names} {obj}, and the pattern's "
                                   f"finished size {short:.1f} x {long_:.1f} cm is outside "
                                   f"that size class ({bases})"))
    if c["dims"] is not None:
        ds, dl = c["dims"]
        if not (_met(ds, short) and _met(dl, long_)):
            note = f" ({c['inferred']})" if c["inferred"] else ""
            out.append((NOT_AS_TITLED, f"the title states {ds:g} x {dl:g} cm{note}, and the "
                                       f"pattern makes {short:.1f} x {long_:.1f} cm"))
    elif c["single"] is not None:
        value, role = c["single"]
        b = band(obj)
        if b is not None and "side_cm" in b:
            ok, side = _met(value, short) and _met(value, long_), "each side"
        elif role == "long":
            ok, side = _met(value, long_), "the length"
        elif role == "short":
            ok, side = _met(value, short), "the width"
        else:
            ok, side = _met(value, long_) or _met(value, short), "either side"
        if not ok:
            out.append((NOT_AS_TITLED, f"the title states {value:g} cm for {side}, and the "
                                       f"pattern makes {short:.1f} x {long_:.1f} cm"))
    if obj in _TITLE_ONLY_BANDS and obj not in _family_hits(title or ""):
        b = band(obj)
        if b is not None and not _in_band(b, short, long_):
            out.append((OUT_OF_BAND, f"the title names a {obj.replace('_', ' ')}, and the "
                                     f"pattern's finished size {short:.1f} x {long_:.1f} cm is "
                                     f"outside its band ({b['basis']})"))
    return out


def findings(title: str | None, width_cm: float, height_cm: float,
             category: str | None = None, facts: dict | None = None) -> list[str]:
    """Why a finished size does not match the size the title claims, or [] when it does."""
    return [why for _, why in coded_findings(title, width_cm, height_cm, category, facts)]


def plan_refusal(category: str | None, title: str | None) -> str | None:
    """The first unbound size token of any title, at plan time (FALLBACK_FACTS), or None.

    `fallback_constructions.plan` runs this on every route it would draft, so a title the
    certificate would refuse for an unbound token is refused before drafting (S1F2-LOW)."""
    c = claims(category, title, FALLBACK_FACTS)
    flat = c["object"] in SUPPORTED_FLAT or bool(c["classes"])
    for why in c["unbound"]:
        if why in c["relative_unbound"] and not flat:
            continue
        return why
    return None


def drafted_refusal(category: str | None, title: str | None) -> str | None:
    """Why the certificate would refuse the size of what the fallback drafts for this title,
    or None. The size is measured from the template the pipeline drafts
    (`runtime.pipeline.drafted_size`) and checked by the certificate's own
    `object_size_findings`, so plan and certify cannot disagree (S1F2-LOW)."""
    from ..gates.certificate import size_findings_for
    from ..runtime.pipeline import drafted_size

    w, h = drafted_size(category, title)
    # Category None, as at certification: the certificate reads the title alone.
    found = size_findings_for(title, w, h, FALLBACK_FACTS)
    return found[0][1] if found else None
