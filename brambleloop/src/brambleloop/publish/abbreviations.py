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

That check is also what found the terminology defect: `write_op` localised sc, dc, tr and
their shaping variants into UK terms and left the post stitches, the bobble, the cable
crossings and `sk` alone. A UK document printing `fpdc` tells a UK maker "front post *double*
crochet", which in UK terms is the stitch a US pattern calls single crochet -- half the
height of the stitch the pattern was validated with. That root is now closed in the layer
that owns it: `cir.stitches.UK_TERMS` is the single terminology table, `cir.writer` delegates
to it, `TOKENS` above derives from it, and an unknown code is refused rather than passed
through. `unlocalised("UK")` is empty today, and `pdf.build_pattern_pdf` still refuses to
render a terminology it cannot name truthfully -- the guard is kept because it is what makes
the next gap fail loudly instead of shipping.

**A localised token is not a localised document.** `unlocalised()` renders ops through the
writer, so it sees tokens and nothing else. Two places in the customer's document name
stitches in prose rather than as tokens -- the special-stitch methods below, and the gauge
line `pdf` sets from `cir.gauge.stitch_type` -- and both were still in US terms in a UK
render, which is the same harm in a different string. `METHOD` and
`method_names_no_stitch_literally()` deal with the first; `pdf` localises the second and
`undefined_tokens` now measures the whole document rather than the instructions alone.
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

# Spellings the customer's document contains that `write_op` never emits.
#
# `TOKENS` is the vocabulary of the writer's *ops*, and the document is not made of ops
# alone. `cir.writer.JOINED_LINE` is a hand-written sentence -- "Join each round with a sl st
# to the first stitch, then ch 1 to begin the next round" -- so the slip stitch reaches the
# buyer spelled `sl st`, while `write_op(Op("slst", 1))` would print `slst`. Both this
# module's key and `undefined_tokens` looked for `slst`, found nothing, and agreed the key
# was complete.
#
# Measured on the rendered bytes: `sl st` is the only crochet abbreviation in any document
# this company can ship that its own key does not define, and it is in all eight round-worked
# documents -- the three nesting baskets and the hexagon coaster, in both terminologies --
# under a paragraph that says "Every abbreviation it uses is below; nothing in the
# instructions is left to be looked up elsewhere".
#
# It is also unlocalised: the UK document prints `sl st` where `cir.stitches.UK_TERMS` says
# the UK token is `ss`. That root is a literal in `cir/writer.py`, which this department does
# not edit; what this table does is make the key name the word the document actually uses, so
# the buyer can look it up either way, and make the completeness check able to see it.
EXTRA_SPELLINGS: dict[str, tuple[str, ...]] = {
    "slst": ("sl st", "sl sts"),
}


def spellings(code: str, terminology: str) -> tuple[str, ...]:
    """Every way this stitch may be spelled in a document rendered in this terminology.

    The declared token first, because that is what the key prefers to print, then any spelling
    the document's prose is known to use.
    """
    return (token(code, terminology),) + EXTRA_SPELLINGS.get(code, ())


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
#
# **No stitch is named in these strings.** Every stitch name arrives through `{code}`, which
# `method()` resolves out of the canonical registry for the terminology being rendered.
#
# That is not tidiness. Written out, every one of these paragraphs said "double crochet", and
# the strings are terminology-independent only if no terminology changes the words in them --
# which is exactly false here. UK "double crochet" is the stitch a US pattern calls single
# crochet, *half the height* of the stitch the pattern was compiled and measured against. So
# a UK document whose token had been correctly localised to `fptr` went on to tell the maker,
# in the paragraph that actually teaches the stitch, to finish it as a double crochet: every
# post stitch worked at half height, cables that do not stand up, a throw about half its
# stated length. The same defect as the 2026-09-24 terminology finding, arriving through prose
# instead of through a token -- and invisible to `unlocalised()`, which renders ops through
# the writer and never sees a method paragraph. The guard for this shape is
# `method_names_no_stitch_literally()`, checked on the source rather than on a render.
METHOD: dict[str, str] = {
    "fpdc": ("Yarn over, insert the hook from the front, around the post (the upright body) "
             "of the stitch below, and back out to the front. Finish as a {dc}. Do not work "
             "into the top of that stitch; the post stitch takes its place in the count."),
    "bpdc": ("Yarn over, insert the hook from the back, around the post of the stitch below, "
             "and back out to the back. Finish as a {dc}. Do not work into the top of that "
             "stitch; the post stitch takes its place in the count."),
    "bob": ("Five incomplete {dc}s worked into the same stitch and closed "
            "together: yarn over, insert the hook, pull up a loop and draw through two "
            "loops, five times into that one stitch, then yarn over and draw through all "
            "six loops on the hook. The bobble sits on the side of the fabric away from "
            "you, so it shows on the right side when the row is worked on the wrong side."),
    "cable2x2": ("Four stitches cross. Slip the next 2 stitches onto a cable needle, work a "
                 "{dc} in each of the following 2 stitches, then work a "
                 "{dc} in each of the 2 stitches waiting on the cable needle."),
    "cable1x1": ("Two stitches cross. Slip the next stitch onto a cable needle, work a "
                 "{dc} in the following stitch, then work a {dc} in the "
                 "stitch waiting on the cable needle."),
}

# Every stitch name that one terminology spells differently from the other, in both
# spellings. Derived from the registry rather than typed, so a stitch whose names diverge
# cannot be added without the guard below noticing it.
#
# "double crochet" is in here twice over: it is the US name of `dc` and the UK name of `sc`.
# That collision is the whole reason a rendered document cannot be checked for this defect by
# looking for wrong words in it -- the wrong word and the right word are the same word. The
# check has to be that no method paragraph contains a stitch name at all.
_AMBIGUOUS_NAMES: frozenset[str] = frozenset(
    name.lower()
    for st in (stitches.get(c) for c in stitches.known_codes())
    if st.name_us.lower() != st.name_uk.lower()
    for name in (st.name_us, st.name_uk)
)


def method(code: str, terminology: str = "US") -> str:
    """How this stitch is worked, with every stitch name resolved for this terminology.

    Reads the names out of `cir.stitches` rather than holding a second copy, for the same
    reason `meaning()` does: the registry is the authority on what a stitch is called, and a
    method paragraph that disagreed with the key about the name of the stitch it teaches
    would be worse than no paragraph.
    """
    template = METHOD.get(code, "")
    if not template:
        return ""
    names: dict[str, str] = {}
    for ref in sorted(set(re.findall(r"\{([A-Za-z0-9_]+)\}", template))):
        # `{Dc}` would be `{dc}` at the start of a sentence. Capitalisation is handled here
        # rather than by writing a second template, because two templates for one method is
        # the shape this module exists to avoid.
        lookup = ref.lower()
        if lookup not in stitches.known_codes():
            raise KeyIncomplete(
                f"the method for {code!r} refers to {ref!r}, which is not a stitch in the "
                f"canonical registry, so its name cannot be resolved for a terminology")
        word = meaning(lookup, terminology)
        names[ref] = (word[:1].upper() + word[1:]) if ref[:1].isupper() else word
    return template.format(**names)


def method_names_no_stitch_literally() -> tuple[str, ...]:
    """Method templates that spell a terminology-sensitive stitch name out in full.

    The guard for the defect the templates were written to remove, measured on the templates
    themselves. A rendered UK document cannot be checked for it -- "double crochet" is a
    correct UK rendering of `sc` and a wrong one of `dc`, the same eleven characters either
    way -- so the property that can actually be checked is the stronger one: a method
    paragraph names no stitch except through the registry.
    """
    return tuple(code for code, template in sorted(METHOD.items())
                 if any(_contains(template.lower(), name) for name in _AMBIGUOUS_NAMES))


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
    # **The gloss says nothing about joining.** It used to read "round -- worked
    # continuously, not turned at the end like a row", which is one of the two ways a round
    # can be worked and is the *wrong* one for every round-worked pattern this company ships:
    # all four -- the three nesting baskets and the hexagon coaster, which is two of the three
    # Launch-0 products -- carry `CONSTRUCTION: joined rounds` on the cover and
    # "Join each round with a sl st to the first stitch" at the head of the instructions.
    # So the key contradicted both of them, fifteen lines apart in the same document.
    #
    # `cir.writer.construction_lines`' own docstring says why that matters: "a maker who does
    # not know whether to join has a different fabric from the one the pattern was validated
    # as: joining leaves a seam up the side, spiralling does not". It states that once, at the
    # top of the component, and the reverse compiler reads it back and checks it. A gloss in
    # the key is a second copy of a decision that already has a single source, so it points at
    # the source instead of answering.
    ("Rnd",
     "round -- worked around the piece rather than in turned rows. How each round is "
     "started and finished is stated once, at the top of the instructions",
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
        # The entry is printed under the spelling the document actually uses. A key that says
        # `ss` over a document that says `sl st` is a key the buyer cannot look a word up in,
        # which is the failure the key exists to prevent rather than a tidier version of it.
        present = [word for word in spellings(code, terminology)
                   if _contains(low, word.lower())]
        if not present:
            continue
        out.append(KeyEntry(token=present[0], means=meaning(code, terminology),
                            method=method(code, terminology)))
    return out


def notation_key(text: str) -> list[KeyEntry]:
    """The notation conventions this document uses, and only those."""
    return [KeyEntry(token=label, means=means)
            for label, means, shape in NOTATION if shape.search(text)]


def codes_in(text: str, terminology: str = "US") -> set[str]:
    """Which canonical stitch codes this rendered text contains."""
    low = text.lower()
    return {code for code in TOKENS if _contains(low, token(code, terminology).lower())}


def undefined_tokens(text: str, terminology: str = "US", *,
                     defined: set[str] | None = None) -> list[str]:
    """Stitch-shaped tokens in `text` that the printed key does not define.

    The inverse check, and the one that matters: a key is only a key if nothing the buyer
    reads is missing from it. Scoped to the canonical vocabulary, so it measures this document
    rather than guessing at English.

    **`defined` is the key that was actually printed, and passing it is the point.** Left to
    default it is derived from `text` by `stitch_key`, and that makes the check vacuous: the
    key is then a function of the same string, so every token in the string is in the key by
    construction and the second branch below is unreachable. It carried a
    `pragma: no cover` saying so, under a docstring claiming to be the check that matters.

    It cannot be made to fail on the instruction text alone, and it was only ever run on the
    instruction text -- so it could not see the defect it exists to catch. The key is built
    from the writer's output; the document also sets the gauge line, the materials, the
    finishing prose and the cover, and a stitch named in any of those is a word the buyer
    meets and the key has never heard of. `pdf` now passes the document's whole prose as
    `text` and the key it rendered as `defined`, which is a comparison that can come out
    either way.

    **Both vocabularies are searched, not this document's one.** Scoping the search to
    `terminology` is what let the real defect through: the cover of a UK document stated its
    gauge "in sc", and `sc` is not a UK token for anything -- no code renders to it in UK terms
    -- so a UK-only scan had nothing to look for and reported the key complete. A stitch
    abbreviation from the other terminology is exactly the word this check exists to catch,
    because it is a word the buyer meets and the key has never heard of, and reading it against
    their own vocabulary is how a maker works the wrong stitch.
    """
    low = text.lower()
    if defined is None:
        defined = {e.token.lower() for e in stitch_key(text, terminology)}
    else:
        defined = {word.lower() for word in defined}
    # What is left of the document once every token the key *does* define is struck out.
    #
    # Some tokens contain others: the UK rendering of `inc` is "dc inc", and the US rendering
    # is "inc", so a hexagon coaster written in UK terms was reported as using an undefined
    # "inc" on the strength of the six defined "dc inc" instructions it actually contains.
    # Longest first, or striking "dc" would leave the "inc" behind and produce the same false
    # reading. A token that survives this is one the document uses on its own account.
    scan = low
    for word in sorted(defined, key=len, reverse=True):
        scan = re.sub(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9])", " ", scan)
    missing = []
    for code in sorted(stitches.known_codes()):
        if code not in TOKENS:
            # A stitch in the registry with no declared token. It cannot be looked up, so it
            # is reported whenever the document appears to contain it.
            if _contains(scan, code):
                missing.append(code)
            continue
        # Every spelling, in both vocabularies, not only the token `write_op` emits. The
        # document's prose spells the slip stitch `sl st` and the writer's op spells it
        # `slst`, so a scan built from the op vocabulary alone reported the key complete on
        # every round-worked document this company ships. See `EXTRA_SPELLINGS`.
        words = {word.lower() for t in ("US", "UK") for word in spellings(code, t)}
        for word in sorted(words):
            if word not in defined and _contains(scan, word):
                missing.append(word)
    return missing
