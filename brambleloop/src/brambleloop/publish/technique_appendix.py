"""The "Techniques used in this pattern" appendix, generated from the CIR (ENG-PDF-DIAGRAMS).

What a maker needs explained is read from the certified CIR itself, never from a document's
prose and never from a competitor's pattern:

- every stitch code the CIR's rows work (repeats flattened), and the chain a chain
  foundation is made of;
- which loop the hook enters, when any op works a front or back loop only;
- how each piece starts (a magic ring or a foundation chain) and how it is worked (joined
  rounds, a continuous spiral, flat rows turned at each end);
- changing colour, when one piece is worked in more than one colour;
- stuffing, when a round's note or a seam says to stuff;
- every seam method the assembly uses;
- fastening off and weaving in, which every pattern ends with.

The words are Brambleloop's own. Every stitch name in them is resolved through the canonical
registry for the edition's terminology (`publish.abbreviations.meaning`), so a UK appendix
never names a US stitch: no template here spells a terminology-sensitive stitch name out
(`literal_stitch_names` is the guard, and a test holds it at empty).

A technique the CIR needs and this module cannot explain is never skipped: `entries` raises
`AppendixIncomplete`, the build refuses, and the premium checker fails the document. An
appendix that silently omits what it cannot explain is the failure this exists to prevent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..cir import stitches
from . import abbreviations

HEADING = "Techniques used in this pattern"
KICKER = "APPENDIX"
INTRO = ("Every technique this pattern asks for, in the order you meet it. The list is "
         "generated from the pattern's own stitch file, so nothing here is padding and "
         "nothing the pattern uses is missing.")


class AppendixIncomplete(ValueError):
    """The CIR needs a technique the appendix has no explanation for."""


@dataclass(frozen=True)
class Technique:
    key: str        # stable id, e.g. "stitch:sc", "start:magic_ring", "seam:whipstitch"
    name: str       # the printed title, in the edition's terms
    how: str        # how it is worked, in our own words, in the edition's terms
    why: str        # what in the CIR asks for it


# How each plain stitch is worked. Stitch names arrive only through `{code}` references.
STITCH_HOW: dict[str, str] = {
    "ch": ("Yarn over and draw the yarn through the loop on the hook. The loop on the hook is "
           "never counted as a stitch."),
    "slst": ("Insert the hook into the stitch, yarn over, and draw the loop through the stitch "
             "and the loop on the hook in one movement. It adds almost no height."),
    "sc": ("Insert the hook into the stitch, yarn over and pull up a loop (2 loops on the "
           "hook), then yarn over and draw through both loops. The shortest full stitch."),
    "hdc": ("Yarn over, insert the hook into the stitch, yarn over and pull up a loop (3 loops "
            "on the hook), then yarn over and draw through all 3 loops at once."),
    "dc": ("Yarn over, insert the hook into the stitch, yarn over and pull up a loop (3 loops "
           "on the hook). Yarn over and draw through 2 loops, then yarn over and draw through "
           "the last 2."),
    "tr": ("Yarn over twice, insert the hook into the stitch, yarn over and pull up a loop (4 "
           "loops on the hook). Then [yarn over and draw through 2 loops] three times."),
    "inc": ("Work 2 {sc}s into the same stitch: one stitch in, two stitches out. Increases "
            "are what make a round or a row wider."),
    "dec": ("Pull up a loop in each of the next 2 stitches (3 loops on the hook), then yarn "
            "over and draw through all 3: two stitches in, one stitch out. For a less "
            "visible decrease, insert the hook under the front loops only of both stitches."),
    "dc_inc": "Work 2 {dc}s into the same stitch: one stitch in, two stitches out.",
    "dc_dec": ("Work a {dc} into each of the next 2 stitches, stopping each one before its "
               "last yarn over (3 loops on the hook), then yarn over and draw through all 3."),
    "sk": ("Leave the next stitch unworked and work the following instruction into the stitch "
           "after it. A skipped stitch is never counted."),
}

LOOP_HOW: dict[str, tuple[str, str]] = {
    "back": ("Back loop only",
             "Each stitch has two loops along its top: the front loop, nearer you, and the "
             "back loop, farther away. Insert the hook under the back loop only and work the "
             "stitch as usual; the front loop stays on the surface as a ridge."),
    "front": ("Front loop only",
              "Insert the hook under the front loop of the stitch, the one nearer you, and "
              "work the stitch as usual. The back loop is left as a line on the far side of "
              "the fabric."),
}

START_HOW: dict[str, tuple[str, str]] = {
    "magic_ring": ("Starting in a magic ring",
                   "Wrap the yarn twice around two fingers, insert the hook under both "
                   "strands and draw up a loop, then make 1 {ch}. Work the first round into "
                   "the ring, over both strands and the tail, and pull the tail firmly to "
                   "close the centre. Weave the tail in later, not now."),
    "chain": ("Making a foundation chain",
              "Make a slip knot on the hook and work the {ch}s the pattern gives, keeping "
              "them loose and even. Count the chains from the one nearest the hook, never "
              "counting the loop on the hook."),
}

WORKED_HOW: dict[str, tuple[str, str]] = {
    "joined_rounds": ("Working in joined rounds",
                      "At the end of each round, join with a {slst} into the first stitch of "
                      "the round, then begin the next round without turning. A stitch "
                      "marker in the first stitch makes the join easy to find."),
    "spiral_rounds": ("Working in a continuous spiral",
                      "Do not join at the end of a round: work the first stitch of the next "
                      "round straight into the first stitch of this one. Move a stitch "
                      "marker up into the first stitch of each round so you can count them."),
    "flat_rows": ("Working in rows and turning",
                  "At the end of each row, turn the work so the last stitch made is the "
                  "first one you work into. Work any turning chain the row names before its "
                  "first stitch."),
}

COLOUR_HOW = ("Changing colour",
              "Work the last stitch in the old colour until its final yarn over, then make "
              "that yarn over with the new colour. Carry or cut the old colour as the "
              "pattern says, and leave a tail of about 10 cm to weave in.")

STUFF_HOW = ("Stuffing",
             "Pull the fibrefill into small pieces and add it a little at a time, pushing it "
             "out to the edges, until the piece is firm and holds its shape. Stuff where the "
             "pattern says, while the opening is still wide enough for your fingers.")

SEAM_HOW: dict[str, tuple[str, str]] = {
    "whipstitch": ("Whipstitch",
                   "Thread the tail on a tapestry needle. Hold the two edges together and "
                   "pass the needle through a stitch on each, always from the same side, so "
                   "each stitch wraps over the edge. Keep the stitches small and even."),
    "mattress": ("Mattress stitch",
                 "With both pieces right side up, side by side, pass the needle under one "
                 "bar on one piece, then under the matching bar on the other, and draw the "
                 "yarn up every few stitches: the seam closes flat and almost disappears."),
    "slst": ("Joining with slip stitches",
             "Hold the two edges together and work a {slst} through a stitch of each edge at "
             "a time, keeping the joining stitches as loose as the fabric."),
    "sew": ("Sewing a piece on",
            "Pin the piece in place first. With the tail on a tapestry needle, sew through "
            "the edge of the piece and a stitch of the piece below, all the way around, and "
            "knot the ends inside."),
    "pick_up": ("Picking up stitches",
                "Insert the hook into the edge where the pattern says, yarn over and pull up "
                "a loop, then work the stitch named. Spread the picked-up stitches evenly "
                "along the edge."),
    "thread": ("Threading through and drawing closed",
               "Thread the tail on a tapestry needle and weave it through the front loop of "
               "each stitch of the last round, then pull gently to draw the opening closed."),
}

FASTEN_HOW = ("Fastening off",
              "Cut the yarn, leaving a tail of about 15 cm (longer if the pattern sews the "
              "piece on with it), yarn over and draw the tail all the way through the loop "
              "on the hook.")

WEAVE_HOW = ("Weaving in ends",
             "Thread each tail on a tapestry needle and weave it through the backs of the "
             "stitches for about 5 cm, change direction once, then trim it close.")


def _ops(nodes):
    from ..cir.model import Op

    for node in nodes:
        if isinstance(node, Op):
            yield node
        else:
            yield from _ops(node.ops)


# LEARN-PROOF-2 (benchmark MM-L2): joining as you go, in our own words. Added to the
# appendix only when the stored lesson is on and the CIR crochets a piece into a stated round.
JOIN_AS_YOU_GO_HOW = (
    "Joining as you go",
    "Where a piece is joined as you go, it is not sewn on: with the piece held closed against "
    "the round and stitches the assembly step names, work each joining stitch through both "
    "pieces at once, so the join is crocheted. The joining stitches count in that round's "
    "stated stitch count, so count them as you would any other.")


def required(cir, lessons=None) -> list[tuple[str, str]]:
    """(technique key, what in the CIR asks for it), in the order a maker meets them."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def need(key: str, why: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append((key, why))

    for comp in cir.components:
        kind = getattr(comp, "foundation_kind", "chain")
        if kind == "magic_ring":
            need("start:magic_ring", f"the {comp.name} starts in a magic ring")
        elif kind == "chain" and (comp.foundation or 0) > 0:
            need("start:chain", f"the {comp.name} starts on a foundation chain")
            need("stitch:ch", f"the {comp.name}'s foundation chain")
        need(f"worked:{comp.construction}", f"the {comp.name} is worked in "
             f"{comp.construction.replace('_', ' ')}")
        if comp.construction == "joined_rounds":
            need("stitch:slst", f"the {comp.name}'s rounds are joined")
        colours = set()
        for row in comp.rows:
            if row.color:
                colours.add(row.color)
            if (row.turning_chain or 0) > 0:
                need("stitch:ch", f"the {comp.name}'s turning chains")
            for op in _ops(row.ops):
                need(f"stitch:{op.stitch}", f"the {comp.name} works {op.stitch}")
                if getattr(op, "loop", "both") in LOOP_HOW:
                    need(f"loop:{op.loop}", f"the {comp.name} works into the {op.loop} loop")
                if getattr(op, "color", None):
                    colours.add(op.color)
        if len(colours) > 1:
            need("colour_change", f"the {comp.name} is worked in {len(colours)} colours")
        if any(r.note and "stuff" in r.note.lower() for r in comp.rows):
            need("stuffing", f"a round of the {comp.name} says to stuff")
    for seam in cir.assembly or []:
        if seam.stuff_before_closing:
            need("stuffing", f"the {seam.piece_a} is stuffed before it is closed")
        need(f"seam:{seam.method}", f"the {seam.piece_a} is joined to the {seam.piece_b} "
             f"by {seam.method}")
    if lessons is None:
        from ..learning import benchmark_lessons as _bench

        lessons = _bench.pdf_lessons()
    if "pdf_join_as_you_go" in lessons:
        from ..learning.benchmark_lessons import join_as_you_go_seams

        for seam in join_as_you_go_seams(cir):
            need("join_as_you_go", f"the {seam.piece_a} is crocheted into round "
                 f"{seam.at_round} of the {seam.piece_b}")
    need("finish:fasten_off", "every piece ends by fastening off")
    need("finish:weave_in", "every piece leaves tails to weave in")
    return out


def _resolve(template: str, terminology: str) -> str:
    names: dict[str, str] = {}
    for ref in sorted(set(re.findall(r"\{([A-Za-z0-9_]+)\}", template))):
        lookup = ref.lower()
        if lookup not in stitches.known_codes():
            raise AppendixIncomplete(f"{ref!r} is not a stitch in the canonical registry")
        word = abbreviations.meaning(lookup, terminology)
        names[ref] = (word[:1].upper() + word[1:]) if ref[:1].isupper() else word
    return template.format(**names)


def _stitch_entry(code: str, terminology: str, why: str) -> Technique:
    name = abbreviations.meaning(code, terminology)
    # The spelling the document itself prints (`sl st` comes from the writer's own joining
    # sentence, in both editions), so the title cross-references the key's own entry.
    token = (abbreviations.EXTRA_SPELLINGS.get(code) or (abbreviations.token(code, terminology),))[0]
    title = name[:1].upper() + name[1:] + (f" ({token})" if token != name else "")
    if code in STITCH_HOW:
        how = _resolve(STITCH_HOW[code], terminology)
    else:
        how = abbreviations.method(code, terminology)
    if not how:
        raise AppendixIncomplete(
            f"the CIR works {code!r} and the appendix has no explanation of how to work it")
    return Technique(key=f"stitch:{code}", name=title, how=how, why=why)


def entries(cir, terminology: str = "US", *, lessons=None) -> list[Technique]:
    """The appendix for this CIR in this terminology. Raises AppendixIncomplete when any
    technique the CIR needs cannot be explained; it never returns a partial appendix.
    `lessons`: benchmark-lesson effects (None = those this process loaded)."""
    term = terminology.upper()
    out: list[Technique] = []
    for key, why in required(cir, lessons):
        kind, _, arg = key.partition(":")
        if kind == "stitch":
            out.append(_stitch_entry(arg, term, why))
            continue
        table = {"loop": LOOP_HOW, "start": START_HOW, "worked": WORKED_HOW,
                 "seam": SEAM_HOW}.get(kind)
        if table is not None:
            if arg not in table:
                raise AppendixIncomplete(f"the CIR needs {key!r} and the appendix has no "
                                         f"explanation of it")
            name, how = table[arg]
        elif key == "colour_change":
            name, how = COLOUR_HOW
        elif key == "stuffing":
            name, how = STUFF_HOW
        elif key == "finish:fasten_off":
            name, how = FASTEN_HOW
        elif key == "finish:weave_in":
            name, how = WEAVE_HOW
        elif key == "join_as_you_go":
            name, how = JOIN_AS_YOU_GO_HOW
        else:  # pragma: no cover - `required` emits only the kinds above
            raise AppendixIncomplete(f"unknown technique {key!r}")
        out.append(Technique(key=key, name=_resolve(name, term), how=_resolve(how, term),
                             why=why))
    return out


def all_templates() -> list[tuple[str, str]]:
    """Every template this module can print, for the literal-name guard."""
    out = list(STITCH_HOW.items())
    for table in (LOOP_HOW, START_HOW, WORKED_HOW, SEAM_HOW):
        out += [(f"{k}", f"{n} {h}") for k, (n, h) in table.items()]
    out += [(n, f"{n} {h}") for n, h in (COLOUR_HOW, STUFF_HOW, FASTEN_HOW, WEAVE_HOW)]
    return out


def literal_stitch_names() -> tuple[str, ...]:
    """Templates that spell a terminology-sensitive stitch name out in full (must be empty):
    "double crochet" is the US `dc` and the UK `sc`, so only the registry may name one."""
    ambiguous = abbreviations._AMBIGUOUS_NAMES
    return tuple(k for k, t in all_templates()
                 if any(re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", t.lower())
                        for n in ambiguous))
