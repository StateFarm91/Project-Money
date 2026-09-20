"""What a competitor's listing actually tells a buyer they will receive.

Requirement 2's last unmeasured weakness. The requirement asks this system to hunt demand
where the incumbents are weak, and names "poor PDFs" and confusing instructions alongside
thin thumbnails and missing video. The first three of those closed once the benchmark
credential was verified. This one did not, because the note on #2 said it needed "a field the
observation does not carry" -- and that was true of the *stored* row, not of the payload. The
catalogue listing already carries its own description; nothing was reading it.

**Only the facts are kept, never the text.** A competitor's description is their copy. This
module reads it once, in memory, during a scan, and stores a set of booleans: whether the
listing states its format, its delivery, its extent, what is inside it, which terms it is
written in, what it finishes at, and what the buyer has to supply. Those booleans are facts
about a category. The sentences that produced them are somebody's writing and are discarded
at the end of the function, exactly as a review's words are discarded after its complaint
theme is counted.

**Absence of a claim is not a claim of absence.** A listing that does not say "PDF" may still
say it in an image nobody here can read. So a fact is `stated` or `not stated`, and the
weakness reported is *silence*, which is what a buyer facing the listing also experiences.
A listing whose description has never been read reports unknown and is excluded, rather than
counted as unclear -- the same rule video follows, for the same reason: an unread backlog
must never be able to present itself as a competitor's weakness.
"""
from __future__ import annotations

import html
import re

# Each fact is one thing a buyer needs to know before paying for something they cannot hold,
# and each is the direct cause of a preventable refund when it is missing. The two groups
# answer the two different questions a pattern buyer asks: what arrives, and what do I need.
ARRIVES = ("format", "delivery", "extent", "contents", "terms", "finished_size")
REQUIRES = ("yarn", "hook")
FACTS: tuple[str, ...] = ARRIVES + REQUIRES

WHAT_EACH_FACT_ANSWERS: dict[str, str] = {
    "format": "is this a file or a finished object",
    "delivery": "when do I get it",
    "extent": "how much of it is there",
    "contents": "written, charted, photographed or filmed",
    "terms": "US or UK stitch names, which are not the same stitches",
    "finished_size": "how big the thing I make will be",
    "yarn": "what yarn and how much of it",
    "hook": "what hook",
}

# Deliberately literal. These are phrases sellers actually write, not an attempt to
# understand English: a pattern-matcher that guesses is worse here than one that under-reads,
# because under-reading only ever understates a competitor's weakness.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "format": re.compile(
        r"\b(pdf|digital (?:file|pattern|download)|downloadable (?:file|pattern)|e-?book)\b"),
    "delivery": re.compile(
        r"\b(instant(?:ly)? download|immediate(?:ly)? download|download(?:ed)? "
        r"(?:immediately|instantly|straight away)|available (?:to|for) download "
        r"(?:immediately|instantly)|auto(?:matic)?(?:ally)? deliver)"),
    "extent": re.compile(
        r"\b\d+\s*-?\s*(?:page|pages|pp)\b|\bpage count\b|\b\d+\s+patterns?\b"),
    "contents": re.compile(
        r"\b(written instructions?|row[- ]by[- ]row|stitch chart|charts?\b|"
        r"photo (?:tutorial|instructions?)|step[- ]by[- ]step|video tutorial|"
        r"schematic|diagram)"),
    "terms": re.compile(
        r"\b(u\.?s\.?[a]?\s+(?:crochet\s+)?terms?|uk\s+(?:crochet\s+)?terms?|"
        r"american\s+(?:crochet\s+)?terms?|british\s+(?:crochet\s+)?terms?|"
        r"us/uk|uk/us)"),
    "finished_size": re.compile(
        r"\b(finished (?:size|measurements?|dimensions?)|measures? approx|"
        r"approx(?:\.|imately)?\s*\d+\s*(?:\"|in\b|inch|cm\b)|"
        r"size(?:s)? (?:xs|s|m|l|xl|\d)|size chart|one size|\d+\s*x\s*\d+\s*(?:\"|in\b|cm\b))"),
    "yarn": re.compile(
        r"\b(yarn weight|worsted|aran\b|dk\b|chunky|bulky|fingering|sport weight|"
        r"\d+\s*(?:yards?|yds?|metres?|meters?|m\b|g\b|grams?|skeins?|balls?)|"
        r"weight yarn)"),
    "hook": re.compile(
        r"\b(\d+(?:\.\d+)?\s*mm\s*(?:crochet\s*)?hook|hook size|"
        r"(?:size\s*)?[b-s]/\d+\s*hook|hook:\s*)"),
}

# A physical item is not unclear for failing to say "PDF", and it is not unclear for failing
# to name a hook size either: nobody buying a finished blanket is going to crochet it. Etsy's
# own structured listing type answers whether a file arrives, so it is read from the field
# rather than inferred from the prose. What is left for a finished object is the two things
# its buyer actually needs -- how big it is and what it is made of.
DIGITAL_ONLY = ("format", "delivery", "extent", "contents", "terms", "hook")


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", html.unescape(text or "")).lower()


def is_digital(listing: dict) -> bool:
    """Whether Etsy itself says a file arrives, rather than us reading it out of the copy."""
    if listing.get("is_digital") is not None:
        return bool(listing.get("is_digital"))
    return str(listing.get("listing_type") or "").lower() in ("download", "both")


def read(listing: dict) -> dict | None:
    """The facts this listing states, or None when there is no description to read.

    None is the important return. It means unknown, and unknown is excluded everywhere
    downstream. Returning an all-false fact set for a listing nobody read would manufacture a
    competitor weakness out of our own missing data, which is the failure this whole module
    is arranged to avoid.
    """
    raw = listing.get("description")
    if raw is None or not str(raw).strip():
        return None

    text = _clean(str(raw))
    digital = is_digital(listing)
    applicable = [f for f in FACTS if digital or f not in DIGITAL_ONLY]
    stated = {f: bool(_PATTERNS[f].search(text)) for f in applicable}
    missing = sorted(f for f, found in stated.items() if not found)
    return {
        "digital": digital,
        "applicable": applicable,
        "stated": stated,
        "missing": missing,
        "clarity": round(sum(stated.values()) / len(applicable), 3) if applicable else None,
    }


# A listing stating fewer than this share of the facts that apply to it is one a buyer cannot
# tell what they are buying from. Set where it separates the two readable groups rather than
# at a round number: a listing that names its format and its yarn and nothing else is the
# case this is meant to catch.
UNCLEAR_BELOW = 0.60


# ---------------------------------------------------------------------------
# Size range (#2: "limited sizes")
#
# A size range is the one weakness in the requirement's list that is both purely textual and
# commercially decisive: a garment pattern graded to two sizes excludes most of the people
# who wanted it, and a buyer who does not fit it never comes back. Counted only where size is
# a real variable -- a blanket has dimensions, not sizes, and counting it as "one size" would
# manufacture a weakness out of a category that has none.
SIZED_PODS = ("garments", "hats")

_SIZE_TOKENS = re.compile(
    r"\b(xxs|xs|s|m|l|xl|2xl|3xl|4xl|5xl|xxl|xxxl|"
    r"(?:extra[- ])?small|medium|(?:extra[- ])?large|plus size)\b")
_ONE_SIZE = re.compile(r"\bone size\b|\bsingle size\b|\bfits (?:all|most)\b")

# Size letters are read only from a clause that says "size", never from the description at
# large. A bare `s`, `m` or `l` is one of the commonest characters in a pattern listing --
# "1200 m" of yarn, a "large hook", a lone "L" in a colour code -- and a matcher that counted
# them anywhere would report a well-graded pattern as a one-size one about as often as it got
# it right. The clause is where a seller actually writes the range.
_SIZE_CLAUSE = re.compile(r"\bsizes?\b[^.;!?\n]{0,160}")
SIZE_CLAUSE_CHARS = 160

# Two or fewer graded sizes is a garment most of the people who wanted it cannot make. Set
# here rather than at "fewer than average", because the average is itself the weakness being
# hunted and a floor measured against it would move whenever the market got worse.
LIMITED_SIZES_AT_OR_BELOW = 2


def size_range(listing: dict, *, pod: str = "") -> dict | None:
    """How many sizes this listing says it is graded to. None where size does not apply.

    `stated: False` is the honest reading of a listing that never mentions size. It is not
    "one size" and it is not zero sizes -- it is a listing whose range a buyer cannot find,
    which is its own finding and is reported separately from a narrow stated range.
    """
    if pod and pod not in SIZED_PODS:
        return None
    raw = listing.get("description")
    if raw is None or not str(raw).strip():
        return None
    text = _clean(str(raw))
    if _ONE_SIZE.search(text):
        return {"sizes": 1, "stated": True, "limited": True}
    found: set[str] = set()
    for clause in _SIZE_CLAUSE.findall(text):
        found.update(_SIZE_TOKENS.findall(clause))
    if not found:
        return {"sizes": 0, "stated": False, "limited": None}
    return {"sizes": len(found), "stated": True,
            "limited": len(found) <= LIMITED_SIZES_AT_OR_BELOW}


def unclear(facts: dict | None) -> bool | None:
    """Whether this listing leaves a buyer guessing. None where nobody has read it."""
    if not facts or facts.get("clarity") is None:
        return None
    return facts["clarity"] < UNCLEAR_BELOW


def summarise(rows: list[dict | None]) -> dict:
    """Count the silence across a set of listings, excluding the ones nobody has read."""
    read_rows = [r for r in rows if r and r.get("clarity") is not None]
    if not read_rows:
        return {
            "measurable": False,
            "read": 0,
            "facts": WHAT_EACH_FACT_ANSWERS,
            "reason": ("no competitor description has been read, so whether these listings "
                       "say what arrives is unknown -- which is not the same as saying they "
                       "do not"),
        }
    silent: dict[str, int] = {}
    for fact in FACTS:
        applicable = [r for r in read_rows if fact in r["applicable"]]
        if applicable:
            silent[fact] = sum(1 for r in applicable if not r["stated"].get(fact))
    unclear_rows = [r for r in read_rows if r["clarity"] < UNCLEAR_BELOW]
    return {
        "measurable": True,
        "read": len(read_rows),
        "unclear": len(unclear_rows),
        "unclear_share": round(len(unclear_rows) / len(read_rows), 3),
        "mean_clarity": round(sum(r["clarity"] for r in read_rows) / len(read_rows), 3),
        "silent_on": dict(sorted(silent.items(), key=lambda kv: -kv[1])),
        "threshold": UNCLEAR_BELOW,
        "facts": WHAT_EACH_FACT_ANSWERS,
    }
