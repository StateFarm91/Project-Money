"""The stitch key and notation key, in text the customer can actually read.

Audited 2026-09-24 as a buyer: the shipped PDF contained no abbreviation key at all. The
only key in the document was the rendered legend image on the chart page, and that legend is
built from `twin.stitch_types_used` -- the stitches that produced a *cell in the fabric*. A
turning chain produces no cell, and a skipped stitch produces no cell, so "Ch 1, turn" and
"sk next st" appeared in the instructions of a document whose only key could not contain
them. A key derived from the chart cannot define the notation of the written pattern, which
is a key measured on a sample that cannot hold the broken case.

It was invisible from the other side too. `teardown/reader.SECTION_CUES` counted the phrase
"us terms" as an abbreviations section, and this document's own instructions heading reads
"Instructions (US terms)" -- so `reader.self_test()` reported `abbreviations` present in a
document that had none, and the same cue would credit a competitor's listing with a key it
had not written. A terminology note is not a stitch key; that cue is corrected there.

**The meanings are not written here.** Every expansion comes from `cir.stitches`, the
canonical registry, so the key cannot disagree with the compiler about what a code means.
What this module holds is the one thing the registry does not: the *token as the writer
prints it*, per terminology. That duplication is deliberate and it is checked -- `printed()`
renders a real op through `cir.writer` and asks whether the declared token is what came out,
so the table cannot drift from the document, and a stitch added to the registry with no
entry here fails the completeness test rather than shipping undefined.

That check is also what found the terminology defect: `write_op` localises sc, dc, tr and
their shaping variants into UK terms and does not localise the post stitches, the bobble, the
cable crossings or `sk`. A UK document printing `fpdc` tells a UK maker "front post *double*
crochet", which in UK terms is the stitch a US pattern calls single crochet -- half the
height of the stitch the pattern was validated with. `unlocalised()` names exactly those
codes, and `pdf.build_pattern_pdf` refuses to render a document that would contain one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..cir import stitches

# How the writer prints each canonical code, per terminology.
#
# The canonical code IS the US token -- `writer.write_op` emits the code unchanged for US --
# and the UK column is what a correct UK render would print. Where the two differ and the
# writer does not yet make that substitution, `unlocalised()` reports it; this table states
# what the document should say, not what it currently says.
TOKENS: dict[str, tuple[str, str]] = {
    code: (code, stitches.term(code, "UK")) for code in stitches.UK_TERMS
}

class KeyIncomplete(ValueError):
    """A stitch reached the customer document that the key cannot define."""


def token(code: str, terminology: str) -> str:
    """The token this code should be printed as in this terminology."""
    try:
        us, uk = TOKENS[code]
    except KeyError:
        raise KeyIncomplete(
            f"no customer-facing token declared for stitch {code!r}; a stitch the key "
            f"cannot name must not reach a pattern") from None
    return uk if terminology.upper() == "UK" else us


def meaning(code: str, terminology: str) -> str:
    """What the token means, taken from the canonical registry rather than restated here."""
    st = stitches.get(code)
    return st.name_uk if terminology.upper() == "UK" else st.name_us


def printed(code: str, terminology: str) -> str:
    """What `cir.writer` actually emits for one of these stitches, rendered for real.

    Asking the writer rather than reading its source is the point: this is the only way the
    key can be checked against the document without the two sharing a table, which is the
    same reason the reverse compiler shares no parsing code with the writer.
    """
    from ..cir.model import Op
    from ..cir.writer import write_op

    return write_op(Op(code, 1), terminology)


def unlocalised(terminology: str = "UK") -> tuple[str, ...]:
    """Codes the writer prints unchanged where this terminology needs a different word.

    Not a list of known bugs typed out by hand -- it is measured against the writer on every
    call, so it shrinks by itself when the writer is fixed and grows by itself if a new
    stitch is added without a UK rendering.
    """
    out = []
    for code in sorted(TOKENS):
        want = token(code, terminology)
        if want == token(code, "US"):
            continue  # the terminology does not change this word, so nothing to check
        if not _contains(printed(code, terminology).lower(), want.lower()):
            out.append(code)
    return tuple(out)


def _contains(haystack: str, needle: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


# How a stitch that is not a plain post-into-the-top stitch is actually worked.
#
# Held here rather than left to the maker's experience because these are the stitches a buyer
# meets for the first time in a pattern that used them. Each is the standard method for the
# stitch the registry defines -- not a property of any one design -- which is why it can be
# stated deterministically at all.
METHOD: dict[str, str] = {
    "fpdc": ("Yarn over, insert the hook from the front, around the post (the upright body) "
             "of the stitch below, and back out to the front. Finish as a double crochet. "
             "Skip the top of that stitch; the post stitch takes its place in the count."),
    "bpdc": ("Yarn over, insert the hook from the back, around the post of the stitch below, "
             "and back out to the back. Finish as a double crochet. Skip the top of that "
             "stitch; the post stitch takes its place in the count."),
    "bob": ("Five incomplete double crochets worked into the same stitch and closed "
            "together: yarn over, insert the hook, pull up a loop and draw through two "
            "loops, five times into that one stitch, then yarn over and draw through all "
            "six loops on the hook. The bobble sits on the side of the fabric away from "
            "you, so it shows on the right side when the row is worked on the wrong side."),
    "cable2x2": ("Four stitches cross. Slip the next 2 stitches onto a cable needle, work a "
                 "double crochet in each of the following 2 stitches, then work a double "
                 "crochet in each of the 2 stitches waiting on the cable needle."),
    "cable1x1": ("Two stitches cross. Slip the next stitch onto a cable needle, work a "
                 "double crochet in the following stitch, then work a double crochet in the "
                 "stitch waiting on the cable needle."),
}

# Crossings whose direction the CIR cannot state.
#
# A cable held at the front and a cable held at the back are mirror images, and the canonical
# `Stitch` record carries no field for which side the held stitches wait on -- the taxonomy's
# own comment says the crossing direction "is a property of the stitch rather than prose
# nobody validated", and the dataclass has no such property. So the document says what is
# true (every crossing in a pattern is the same operation, so they all go the same way) and
# `DIRECTION_NOT_IN_CIR` is reported, rather than this module picking a side and printing a
# fact the compiler never checked.
CABLE_CODES: frozenset[str] = frozenset({"cable2x2", "cable1x1"})
CABLE_DIRECTION_NOTE = (
    "Every crossing in this pattern is the same crossing, so hold the cable needle to the "
    "same side each time and the cables will run one way up the fabric."
)

# Notation the written pattern uses, and the shape that proves it is in this document.
# Printed only when the pattern actually contains it: a key explaining bracket repeats to a
# reader of a pattern with no brackets is padding, and padding is how a key stops being read.
NOTATION: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("[ ... ] x 4",
     "work everything inside the brackets, in order, four times in a row",
     re.compile(r"\]\s*x\s*\d")),
    ("* ... ; rep from * to end",
     "repeat everything after the star until the row runs out of stitches",
     re.compile(r"rep from \*")),
    ("(120 sts)",
     "the stitch count that row should end on. Count it: this is the number every later "
     "row depends on",
     re.compile(r"\(\d+\s*sts\)")),
    ("st / sts",
     "stitch / stitches",
     re.compile(r"\bsts?\b")),
    ("turn",
     "turn the work to start the next row from the other end",
     re.compile(r"\bturn\b")),
    ("magic ring",
     "an adjustable loop of yarn worked into and then pulled tight, so the round closes "
     "with no hole at the centre",
     re.compile(r"magic ring")),
    ("Foundation",
     "the starting chain the first row is worked into",
     re.compile(r"^Foundation", re.M)),
    ("Rnd",
     "round -- worked continuously, not turned at the end like a row",
     re.compile(r"\bRnd\b")),
)


@dataclass(frozen=True)
class KeyEntry:
    token: str
    means: str
    method: str = ""


def stitch_key(text: str, terminology: str = "US") -> list[KeyEntry]:
    """Every stitch token the written pattern actually contains, defined.

    Driven by the rendered instruction text rather than by the twin's cells, because the
    document is what the customer reads: `ch` and `sk` produce no fabric cell and are printed
    on the page regardless.
    """
    low = text.lower()
    out: list[KeyEntry] = []
    for code in sorted(TOKENS, key=lambda c: token(c, terminology)):
        word = token(code, terminology)
        if not _contains(low, word.lower()):
            continue
        out.append(KeyEntry(token=word, means=meaning(code, terminology),
                            method=METHOD.get(code, "")))
    return out


def notation_key(text: str) -> list[KeyEntry]:
    """The notation conventions this document uses, and only those."""
    return [KeyEntry(token=label, means=means)
            for label, means, shape in NOTATION if shape.search(text)]


def codes_in(text: str, terminology: str = "US") -> set[str]:
    """Which canonical stitch codes this rendered text contains."""
    low = text.lower()
    return {code for code in TOKENS if _contains(low, token(code, terminology).lower())}


def undefined_tokens(text: str, terminology: str = "US") -> list[str]:
    """Stitch-shaped tokens in the document that the key would not define.

    The inverse check, and the one that matters: a key is only a key if nothing in the
    instructions is missing from it. Scoped to the canonical vocabulary plus the writer's own
    output, so it measures this document rather than guessing at English.
    """
    low = text.lower()
    defined = {e.token.lower() for e in stitch_key(text, terminology)}
    missing = []
    for code in sorted(stitches.known_codes()):
        if code not in TOKENS:
            # A stitch in the registry with no declared token. It cannot be looked up, so it
            # is reported whenever the document appears to contain it.
            if _contains(low, code):
                missing.append(code)
            continue
        word = token(code, terminology).lower()
        if _contains(low, word) and word not in defined:  # pragma: no cover - see the test
            missing.append(word)
    return missing
