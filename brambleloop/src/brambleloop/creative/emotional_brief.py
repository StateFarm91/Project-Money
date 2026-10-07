"""The emotional design brief: who a product is for, the moment it belongs to, and what it does.

W4-CREATIVE (2026-10-06). The owner's dashboard read "11 products audited, 0 survived the
creative gate; dominant failure: emotional_appeal". The cause is not the gate. A builder
`Design` is a motif, a palette, a width and a repeat count; it has nowhere to say who the
product is for, the moment it belongs to, or what it does for its owner, so
`audit.concept_from_design` records `function=""` for every product and the
`emotional_appeal` critic rejects all eleven by construction. See
`research/final_build/w4/CREATIVE_DIAGNOSIS.md`.

This module is the missing step in the design process: a brief written moment first (person,
occasion, the scene, the gift, the senses, how it serves "Patterns for a More Handmade Life")
and reaching the object last. It feeds the creative gate the fields it reads. It does not
touch the gate: the jury's critics and thresholds are unchanged, and the best verdict a briefed
concept can reach without a vision model is still `needs_taste`.

**Briefs are design intent, never evidence.** A brief says what the product is designed to do
for a person; it never claims sales, reviews, popularity or anything a buyer did. Validation
refuses social-proof and listing-copy language, refuses imagery the fabric does not carry, and
HOLDS a product whose own title names imagery its motif does not depict: a story cannot clear
a creative gate for a product whose name misdescribes it (Product Truth).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from .concept import FEELINGS, GENERIC_TOKENS, OCCASIONS, RECIPIENTS, Concept, ConceptRefused

BRIEF_VERSION = "emotional-brief/1"
AUTHORED = "2026-10-06"
AUTHOR = "W4-CREATIVE design process (creative.emotional_brief)"
BRAND_LINE = "Patterns for a More Handmade Life"

# The default answer to every crochet brief (the critic's first branch), refused at authoring
# time so a brief cannot be the thing the gate exists to reject.
DEFAULT_FEELINGS = ("cosy", "serene")

MIN_FUNCTION_WORDS = 6
MIN_MOMENT_WORDS = 10
MIN_HANDMADE_WORDS = 6
MIN_SENSORY_HOOKS = 2

# Words that would make a brief a claim about buyers rather than a design decision. A brief
# carrying any of these is refused: fabricated social proof is never creative evidence.
SOCIAL_PROOF = ("bestseller", "best seller", "best-selling", "bestselling", "loved by",
                "review", "five star", "5 star", "5-star", "customers say", "customer favourite",
                "customer favorite", "award", "as seen", "viral", "trending", "#1",
                "number one", "limited time", "sale", "sold out", "thousands of")
# Listing copy (invention._COPY_LANGUAGE plus the obvious neighbours): describes a listing, not
# an object or a moment.
COPY_LANGUAGE = ("perfect for", "sure to", "will love", "adds a touch", "brings warmth",
                 "makes a great", "ideal gift", "cosy vibes", "cozy vibes", "must-have",
                 "must have")

# Depicted subjects. A brief may name one only if the product's motif carries it, and a
# product whose *title* names one its motif does not carry is held.
IMAGERY: frozenset[str] = frozenset({
    "oak", "acorn", "acorns", "leaf", "leaves", "flower", "flowers", "floral", "botanical",
    "petal", "petals", "rose", "roses", "daisy", "daisies", "star", "stars", "snowflake",
    "snowflakes", "snow", "village", "house", "houses", "pumpkin", "pumpkins", "gourd",
    "heart", "hearts", "fir", "tree", "trees", "ghost", "ghosts", "bat", "bats", "bird",
    "birds", "deer", "reindeer", "mushroom", "mushrooms", "bee", "bees", "cloud", "clouds",
})
MOTIF_IMAGERY: dict[str, frozenset[str]] = {
    "snowfall": frozenset({"snow", "snowfall", "snowflake", "snowflakes"}),
    "fir-and-star": frozenset({"fir", "star", "stars", "tree", "trees"}),
    "heart-row": frozenset({"heart", "hearts"}),
    "pumpkin-row": frozenset({"pumpkin", "pumpkins", "gourd"}),
}

_WORD = re.compile(r"[a-z]+")


class BriefRefused(ValueError):
    """A brief that is not a design decision the gate can honestly act on."""


@dataclass(frozen=True)
class EmotionalBrief:
    """One product's emotional design brief, written moment first."""

    key: str
    recipient: str          # who it is for (concept.RECIPIENTS)
    occasion: str           # the moment in the year (concept.OCCASIONS)
    feeling: str            # what the thumbnail should make a buyer feel (concept.FEELINGS)
    moment: str             # the scene: the story the product belongs to
    function: str           # what it does for the person who owns it
    gifting: str            # who receives it and when; required unless it is for oneself
    sensory: tuple[str, ...]  # what hand and eye meet: stitch, colour, weight
    handmade_life: str      # how making it serves "Patterns for a More Handmade Life"
    laura_scene: str        # art direction for Visual; never a product claim
    premise: str            # the one-sentence visual premise, naming the real motif
    title: str = ""         # for new concepts only; a catalogue product keeps its own title

    def to_dict(self) -> dict:
        out = asdict(self)
        out["sensory"] = list(self.sensory)
        return out


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _specific(text: str) -> list[str]:
    return [w for w in _words(text) if w not in GENERIC_TOKENS]


def carried_imagery(motif: str) -> frozenset[str]:
    """The depicted subjects a motif actually puts in the fabric."""
    return MOTIF_IMAGERY.get(motif, frozenset(w for w in _words(motif) if w in IMAGERY))


def title_conflicts(title: str, motif: str) -> list[str]:
    """Imagery a product's title promises that its motif does not depict."""
    carried = carried_imagery(motif)
    return sorted({w for w in _words(title) if w in IMAGERY and w not in carried})


def _text_fields(brief: EmotionalBrief) -> dict[str, str]:
    return {"moment": brief.moment, "function": brief.function, "gifting": brief.gifting,
            "handmade_life": brief.handmade_life, "premise": brief.premise,
            "title": brief.title, **{f"sensory[{i}]": s for i, s in enumerate(brief.sensory)}}


def validate(brief: EmotionalBrief, *, motif: str, title: str,
             declared: dict[str, str] | None = None) -> list[str]:
    """Every reason this brief cannot be applied. Empty means it is a usable design decision.

    Deterministic. `declared` is what the product's own name already fixes (occasion,
    recipient); a brief may not contradict it.
    """
    problems: list[str] = []
    for name, allowed in (("recipient", RECIPIENTS), ("occasion", OCCASIONS),
                          ("feeling", FEELINGS)):
        if getattr(brief, name) not in allowed:
            problems.append(f"{name}={getattr(brief, name)!r} is not in the closed vocabulary")
    if brief.recipient == "self" and brief.occasion == "everyday" \
            and brief.feeling in DEFAULT_FEELINGS:
        problems.append("self / everyday / cosy-or-serene is the default answer the gate "
                        "exists to reject; the brief has not chosen a person or a moment")
    if len(_words(brief.function)) < MIN_FUNCTION_WORDS or len(_specific(brief.function)) < 3:
        problems.append(f"function must say what it does for its owner in at least "
                        f"{MIN_FUNCTION_WORDS} words, three of them specific")
    if len(_words(brief.moment)) < MIN_MOMENT_WORDS:
        problems.append(f"moment must be a scene of at least {MIN_MOMENT_WORDS} words")
    if brief.recipient != "self" and len(_words(brief.gifting)) < MIN_FUNCTION_WORDS:
        problems.append("a product for someone else needs its gifting moment: who receives "
                        "it, and when")
    if len(brief.sensory) < MIN_SENSORY_HOOKS or any(len(_specific(s)) < 3
                                                     for s in brief.sensory):
        problems.append(f"at least {MIN_SENSORY_HOOKS} sensory hooks, each naming something "
                        f"hand or eye meets")
    if len(_words(brief.handmade_life)) < MIN_HANDMADE_WORDS:
        problems.append("handmade_life must say how making it serves the brand line "
                        f"{BRAND_LINE!r}")
    if not brief.laura_scene.strip():
        problems.append("laura_scene (art direction) is required, even if it says the "
                        "product photographs better without her")

    carried = carried_imagery(motif)
    for field, text in _text_fields(brief).items():
        low = (text or "").lower()
        for phrase in SOCIAL_PROOF:
            if phrase in low:
                problems.append(f"{field} carries social-proof language {phrase!r}; a brief "
                                f"is design intent, never a claim about buyers")
        for phrase in COPY_LANGUAGE:
            if phrase in low:
                problems.append(f"{field} carries listing copy {phrase!r}, not a moment")
        # Depiction is claimed by the visual premise (and the title, checked below). The
        # scene, gifting and handmade-life prose describe people and places, where "the
        # children of the house" is not a claim about the fabric.
        if field != "premise":
            continue
        foreign = sorted({w for w in _words(text) if w in IMAGERY and w not in carried})
        if foreign:
            problems.append(f"{field} names imagery {foreign} that the {motif!r} motif does "
                            f"not depict (Product Truth)")
    motif_words = [w for w in _words(motif.replace("-", " ")) if w not in ("and", "row")]
    premise_words = _words(brief.premise)
    if motif_words and not any(p == w or p == w + "s" for w in motif_words
                               for p in premise_words):
        problems.append(f"the premise must name the real motif ({motif!r}); a premise about "
                        f"something else is a different product")
    conflicts = title_conflicts(title, motif)
    if conflicts:
        problems.append(f"HELD: the title {title!r} promises {conflicts}, which the "
                        f"{motif!r} motif does not depict; retitle or redesign before any "
                        f"story is told about it")
    for name, value in (declared or {}).items():
        if value and getattr(brief, name) != value:
            problems.append(f"{name}={getattr(brief, name)!r} contradicts the product's own "
                            f"name, which declares {value!r}")
    return problems


def to_concept(brief: EmotionalBrief, *, key: str, title: str, pod: str, form: str,
               construction: str, motif: str, palette_story: str, make_lane: str,
               provenance: str) -> Concept:
    """The concept the gate judges: the brief's fields, nothing invented beyond them."""
    return Concept(key=key, title=title, premise=brief.premise, pod=pod, form=form,
                   construction=construction, motif=motif, palette_story=palette_story,
                   recipient=brief.recipient, occasion=brief.occasion,
                   feeling=brief.feeling, function=brief.function, make_lane=make_lane,
                   provenance=provenance,
                   notes=f"{BRIEF_VERSION}: {brief.moment}"[:300])


def promise_problems(concept: Concept) -> list[str]:
    """#109: the feeling must be executed by the object (reuses the pre-engineering check)."""
    from .invention import InventionRefused
    from .preengineering import promise_for

    try:
        promise_for(concept)
    except InventionRefused as exc:
        return [f"emotional promise not executed in the object: {exc}"]
    return []


# ---------------------------------------------------------------------------
# Briefs for the existing catalogue. Each is a design decision about a product that already
# compiles and certifies; none changes its fabric. A product whose title names imagery its
# motif does not depict gets no brief here -- validation would hold it anyway -- and is listed
# in HELD with the retitle Product should decide.

CATALOGUE_BRIEFS: dict[str, EmotionalBrief] = {
    "cloudline-baby-blanket": EmotionalBrief(
        key="cloudline-baby-blanket", recipient="new_parent", occasion="new_baby",
        feeling="tender",
        moment=("A maker counts down to a friend's due date, working one lattice repeat each "
                "evening so the blanket is folded and ready for the first visit home."),
        function=("wraps the baby for the first visits home, then stays folded at the foot "
                  "of the cot as the first thing made for them"),
        gifting=("Given to the new parents at the shower or on the first visit home, made by "
                 "a friend or grandparent rather than bought."),
        sensory=("raised diamond lattice ridges under the fingertips",
                 "quiet cream and ink contrast suited to a nursery"),
        handmade_life=("Turns the long wait for a baby into evenings of making something "
                       "the family will keep."),
        laura_scene=("Laura folding the finished blanket over a nursery chair in morning "
                     "window light; the blanket is the subject."),
        premise=("A raised diamond lattice in cream and ink that small fingers can trace "
                 "across the whole blanket.")),
    "harvest-table-runner": EmotionalBrief(
        key="harvest-table-runner", recipient="self", occasion="thanksgiving",
        feeling="nostalgic",
        moment=("The morning of the harvest dinner the runner comes out of the linen drawer, "
                "and the long table finally starts to look like the holiday."),
        function=("dresses the family table for the one dinner a year when everybody "
                  "sits down together"),
        gifting="",
        sensory=("wine and gold chevron band running under the serving dishes",
                 "firm flat stitch fabric that lies straight along the table"),
        handmade_life=("A piece made once and brought out every autumn, so the holiday table "
                       "carries the maker's own work."),
        laura_scene=("Laura laying the runner along a set harvest table before guests "
                     "arrive; product-first, Laura's hands in frame."),
        premise=("A marching chevron band in wine and gold runs the full length of the "
                 "harvest table under the serving dishes.")),
    "mosaic-placemat-pair": EmotionalBrief(
        key="mosaic-placemat-pair", recipient="host", occasion="housewarming",
        feeling="heirloom",
        moment=("Two people eat their first dinner in a new home on a box-strewn kitchen "
                "table, and the one finished thing in the room is a laid table for two."),
        function=("sets two places for the first dinner in a new home before the boxes "
                  "are unpacked"),
        gifting=("Brought to a housewarming in place of a bottle, so the first meal in the "
                 "new kitchen has a laid table."),
        sensory=("diamond lattice texture under the plate rim",
                 "cream and wine pairing that reads as a matched set"),
        handmade_life=("A small, finishable make that marks a new home with something made "
                       "rather than bought."),
        laura_scene=("Two placemats set on a bare wooden table with mismatched new-home "
                     "crockery; Laura optional, setting the second place."),
        premise=("A matched diamond lattice pair in cream and wine sets two places at a "
                 "small kitchen table.")),
    "spooky-garland": EmotionalBrief(
        key="spooky-garland", recipient="child", occasion="halloween", feeling="playful",
        moment=("On the first of October the children help hang the pumpkin flags across "
                "the front window, and the countdown to trick-or-treat night begins."),
        function=("turns the front window into a countdown to trick-or-treat night for "
                  "the children of the house"),
        gifting=("Made with or for the children of the house, hung on the first of October "
                 "and packed away on the first of November for next year."),
        sensory=("round pumpkin row flags swinging along the window frame",
                 "warm wine and gold colours against the dark October glass"),
        handmade_life=("A family ritual the maker can repeat every autumn, with flags small "
                       "enough to finish in an evening."),
        laura_scene=("Laura and a child's hands pinning the garland across a window at "
                     "dusk; the garland reads first."),
        premise=("A string of pumpkin row flags in wine and gold swings across the front "
                 "window for the whole of October.")),
    "valentine-heart-garland": EmotionalBrief(
        key="valentine-heart-garland", recipient="partner", occasion="valentines",
        feeling="romantic",
        moment=("The garland goes up across the bedroom doorway the night before, so the "
                "first thing a partner sees on Valentine's morning is a row of hearts."),
        function=("says what a card says but stays strung across the doorway for the whole "
                  "of February"),
        gifting=("Hung before a partner wakes on Valentine's morning, a surprise that took "
                 "several quiet evenings to make."),
        sensory=("solid heart row shapes swinging in a doorway draught",
                 "cream and wine colour pairing that reads from across the room"),
        handmade_life=("A love note that is made rather than bought, and kept for next year "
                       "instead of thrown away."),
        laura_scene=("Laura stringing the garland across a sunlit bedroom doorway; hearts "
                     "in sharp focus, Laura soft behind."),
        premise=("A row of solid hearts in cream and wine is strung across the bedroom "
                 "doorway for Valentine's morning.")),
    "pet-snuggle-mat": EmotionalBrief(
        key="pet-snuggle-mat", recipient="pet_owner", occasion="winter_nesting",
        feeling="tender",
        moment=("A rescue dog comes home in December, and the first evening there is "
                "already a mat by the fire that is unmistakably theirs."),
        function=("gives a pet a warm spot of its own beside the family on long winter "
                  "evenings"),
        gifting=("Made for a friend bringing home a new dog or cat, so the new arrival has a "
                 "place that is already theirs."),
        sensory=("dense basketweave blocks with a firm padded hand",
                 "pine and gold colours that hide paw prints between washes"),
        handmade_life=("Making for the whole household, animals included, is part of a "
                       "handmade home."),
        laura_scene=("A dog asleep on the mat by a hearth, Laura reading in the chair "
                     "behind; the mat is the subject."),
        premise=("A dense basketweave mat in pine and gold marks out the dog's own spot "
                 "beside the fire.")),
}

# Products the design process cannot honestly brief until Product resolves a title/fabric
# conflict. The proposed titles are suggestions for the product owner, not changes made here.
HELD: dict[str, dict[str, str]] = {
    "winter-village-graphghan": {"conflict": "title promises a village; the snowfall motif "
                                             "depicts snowflakes only",
                                 "proposed_title": "Winter Snowfall Graphghan"},
    "autumn-oak-mosaic-throw": {"conflict": "title promises oak; the fir-and-star motif "
                                            "depicts firs and stars",
                                "proposed_title": "Fir and Star Mosaic Throw"},
    "nordic-star-ornaments": {"conflict": "title promises stars; the snowfall motif depicts "
                                          "snowflakes",
                              "proposed_title": "Nordic Snowflake Ornament Set (6)"},
    "pressed-flower-motifs": {"conflict": "title promises flowers; the heart-row motif "
                                          "depicts hearts",
                              "proposed_title": "Heart Appliqué Motif Library (12)"},
    "cottage-wall-hanging": {"conflict": "title promises botanical imagery; the chevron-band "
                                         "motif depicts chevrons",
                             "proposed_title": "Cottage Chevron Wall Hanging"},
}


def declared_by_slug(slug: str) -> dict[str, str]:
    """What the product's own name already fixes, read with the audit's own hints."""
    from .audit import _OCCASION_HINTS, _RECIPIENT_HINTS, _match

    return {"occasion": _match(slug, _OCCASION_HINTS, ""),
            "recipient": _match(slug, _RECIPIENT_HINTS, "")}


def brief_for_design(design) -> tuple[EmotionalBrief | None, list[str]]:
    """The design's brief and the reasons it cannot be applied (empty when it can)."""
    brief = CATALOGUE_BRIEFS.get(design.slug)
    if brief is None:
        held = HELD.get(design.slug)
        conflicts = title_conflicts(design.title, design.motif)
        why = [f"HELD: {held['conflict']} (proposed: {held['proposed_title']!r})"] if held \
            else ["no emotional brief has been written for this design"]
        if conflicts and not held:
            why.append(f"HELD: title promises {conflicts} the motif does not depict")
        return None, why
    return brief, validate(brief, motif=design.motif, title=design.title,
                           declared=declared_by_slug(design.slug))


def briefs_fingerprint() -> str:
    payload = {"v": BRIEF_VERSION,
               "briefs": {k: b.to_dict() for k, b in sorted(CATALOGUE_BRIEFS.items())},
               "candidates": [c["brief"].to_dict() for c in NEW_CANDIDATES]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# New candidates, designed moment first. Concept stage only: none has a CIR, a pattern, a
# listing or a photograph. Each starts from a person and a moment from the brand's HOME /
# BABY / GIFTS / SEASONAL architecture and reaches form, construction and motif last. Motifs
# are from Brambleloop's own library; no competitor product informed any of them.

def _candidate(key, *, pod, form, construction, motif, palette_story, make_lane,
               brief: EmotionalBrief) -> dict:
    return {"key": key, "pod": pod, "form": form, "construction": construction,
            "motif": motif, "palette_story": palette_story, "make_lane": make_lane,
            "brief": brief}


NEW_CANDIDATES: list[dict] = [
    _candidate(
        "housewarming-key-basket", pod="home_decor", form="basket",
        construction="in_the_round", motif="basketweave", palette_story="pine and cream",
        make_lane="SHORT", brief=EmotionalBrief(
            key="housewarming-key-basket", recipient="host", occasion="housewarming",
            feeling="heirloom", title="Housewarming Key Basket",
            moment=("The first week in a new home the keys keep going missing, until a round "
                    "basket on the hall table becomes the place everything lands."),
            function=("keeps the keys, letters and dog lead of a first home together in one "
                      "place by the door"),
            gifting=("Carried to a housewarming as the first useful thing in the new hall, "
                     "made by a friend who helped with the move."),
            sensory=("dense basketweave walls that stand up on their own",
                     "pine and cream blocks that read from the doorway"),
            handmade_life=("A first-home ritual: something made by hand is the first thing "
                           "set on the hall table."),
            laura_scene=("Laura dropping keys into the basket on a hall table, coat still "
                         "on; basket in sharp focus."),
            premise=("A round basketweave catch-all in pine and cream sits on the hall table "
                     "to hold the keys of a first home."))),
    _candidate(
        "reading-nook-cable-wrap", pod="wearables", form="draped_garment",
        construction="side_to_side", motif="cable-twist", palette_story="forest and cream",
        make_lane="LONG", brief=EmotionalBrief(
            key="reading-nook-cable-wrap", recipient="self", occasion="winter_nesting",
            feeling="quietly_luxurious", title="Reading Nook Cable Wrap",
            moment=("The first properly cold evening of the year, the reader takes the "
                    "window seat with a pot of tea and pulls a long wrap across both "
                    "shoulders."),
            function=("stays across the shoulders through a long evening of reading in the "
                      "coldest room of the house"),
            gifting="",
            sensory=("cable twist ridges running the length of the wrap",
                     "deep forest weight that settles over the shoulders"),
            handmade_life=("A long winter make for the maker herself, worked a few rows each "
                           "evening in the same chair it will be worn in."),
            laura_scene=("Laura in a window seat with a book and the wrap over her "
                         "shoulders, snow-light outside; a wearable, so Laura leads."),
            premise=("A long cable twist wrap in forest and cream lies across the shoulders "
                     "like a heavier shawl."))),
    _candidate(
        "first-christmas-stocking", pod="seasonal", form="stocking",
        construction="in_the_round", motif="fir-and-star", palette_story="forest and cream",
        make_lane="MEDIUM", brief=EmotionalBrief(
            key="first-christmas-stocking", recipient="new_parent", occasion="christmas",
            feeling="heirloom", title="First Christmas Fir and Star Stocking",
            moment=("A baby's first December: the stocking is hung on the mantel beside the "
                    "parents' own, and comes out of the decorations box every year after."),
            function=("marks a baby's first Christmas and hangs on the mantel every December "
                      "of their childhood"),
            gifting=("Given to new parents in November so it is hung in time for the baby's "
                     "first Christmas morning."),
            sensory=("fir and star bands circling the leg of the stocking",
                     "plain cream cuff band left open for an embroidered initial"),
            handmade_life=("An heirloom started in the baby's first year, made by the hands "
                           "of someone who loves them."),
            laura_scene=("Three stockings on a mantel, the smallest in front; Laura hanging "
                         "it, out of focus. Product-first."),
            premise=("A fir and star stocking in forest and cream with a plain cuff band "
                     "waiting for the baby's initial."))),
    _candidate(
        "mothers-day-heart-tea-cosy", pod="gifts", form="tube",
        construction="seamless_tube", motif="heart-row", palette_story="cream and wine",
        make_lane="SHORT", brief=EmotionalBrief(
            key="mothers-day-heart-tea-cosy", recipient="grandparent",
            occasion="mothers_day", feeling="tender", title="Heart Row Tea Cosy",
            moment=("On Mother's Day the family gathers at grandmother's kitchen table, and "
                    "the round teapot comes out dressed in something one of them made."),
            function=("keeps the Sunday teapot hot through a long conversation at the "
                      "kitchen table"),
            gifting=("Given to a mother or grandmother on Mother's Day, made by a child or "
                     "grandchild."),
            sensory=("heart row band circling the belly of the teapot",
                     "thick stitch walls that hold warmth around the pot"),
            handmade_life=("Small enough to finish in a weekend, and used every week rather "
                           "than kept in a drawer."),
            laura_scene=("A teapot in the cosy on a set kitchen table, two cups poured, "
                         "Laura's hands passing a cup; no face needed."),
            premise=("A heart row tea cosy in cream and wine fits the round teapot that "
                     "comes out when the family visits."))),
    _candidate(
        "teacher-chevron-pencil-roll", pod="gifts", form="pouch",
        construction="flat_rows", motif="chevron-band", palette_story="wine and gold",
        make_lane="QUICK", brief=EmotionalBrief(
            key="teacher-chevron-pencil-roll", recipient="teacher",
            occasion="back_to_school", feeling="playful", title="Chevron Pencil Roll",
            moment=("On the first day back a child hands their teacher a rolled-up chevron "
                    "bundle, and inside is a full row of new pencils."),
            function=("carries a full set of pencils between classroom and home and unrolls "
                      "flat across the desk"),
            gifting=("Given to a teacher on the first day of the school year, from a family "
                     "that made it together."),
            sensory=("bold chevron band stripes across the rolled bundle",
                     "single tie cord wrapped twice around the roll"),
            handmade_life=("A quick evening make a parent and child can finish together "
                           "before term starts."),
            laura_scene=("The roll open on a classroom desk with pencils fanned out; no "
                         "person in frame. Product-first."),
            premise=("A chevron band pencil roll in wine and gold ties shut with a single "
                     "crocheted cord."))),
    _candidate(
        "heart-row-ring-pillow", pod="gifts", form="pillow",
        construction="in_the_round", motif="heart-row", palette_story="cream and wine",
        make_lane="SHORT", brief=EmotionalBrief(
            key="heart-row-ring-pillow", recipient="newlyweds", occasion="wedding",
            feeling="romantic", title="Heart Row Ring Pillow",
            moment=("A small hand carries the ring pillow down the aisle, and afterwards it "
                    "sits on the couple's bedroom shelf as the first keepsake of the "
                    "marriage."),
            function=("carries the rings down the aisle and then keeps them safe on the "
                      "shelf as a wedding keepsake"),
            gifting=("Made by a sister, friend or grandmother and given to the couple in the "
                     "weeks before the wedding."),
            sensory=("heart row border framing a centre loop for the rings",
                     "cream ground with wine hearts that photographs cleanly"),
            handmade_life=("A wedding object made by family hands instead of ordered from a "
                           "catalogue."),
            laura_scene=("The pillow held in two hands with the rings tied on, soft "
                         "ceremony light; Laura's hands only."),
            premise=("A round heart row ring pillow in cream and wine with a centre loop to "
                     "tie the two rings."))),
    _candidate(
        "snowfall-advent-garland", pod="seasonal", form="garland",
        construction="motif_join", motif="snowfall", palette_story="forest and cream",
        make_lane="MEDIUM", brief=EmotionalBrief(
            key="snowfall-advent-garland", recipient="child", occasion="christmas",
            feeling="festive", title="Snowfall Advent Garland",
            moment=("Every December morning the children race to the stairs to find the "
                    "next numbered snowfall pocket and the note waiting inside."),
            function=("holds a note or small treat for each morning of December so the "
                      "children count down together"),
            gifting=("Made for the children of the house and hung on the last day of "
                     "November, refilled every year."),
            sensory=("twenty-four snowfall pockets strung along the banister",
                     "forest and cream colours against the dark wood of the stairs"),
            handmade_life=("A family tradition built from twenty-four small pieces, made "
                           "over the autumn evenings."),
            laura_scene=("The garland along a staircase banister, one pocket open with a "
                         "folded note; Laura seated on the stairs, secondary."),
            premise=("Twenty-four numbered snowfall pockets in forest and cream hang along "
                     "the stairs for the December countdown."))),
    _candidate(
        "spring-garden-kneeler", pod="home_decor", form="pillow",
        construction="modular_panels", motif="diamond-lattice", palette_story="pine and gold",
        make_lane="SHORT", brief=EmotionalBrief(
            key="spring-garden-kneeler", recipient="self", occasion="spring_refresh",
            feeling="rugged", title="Spring Garden Kneeler",
            moment=("The first warm Saturday of spring, the gardener carries a thick kneeling "
                    "pad out to the beds and spends the whole morning planting."),
            function=("cushions the knees through a full morning of planting out the spring "
                      "garden beds"),
            gifting="",
            sensory=("dense diamond lattice panels with a thick firm hand",
                     "pine and gold colours that stay cheerful against wet soil"),
            handmade_life=("A practical make for the season the maker spends outdoors, used "
                           "every weekend from April to June."),
            laura_scene=("Laura kneeling on the pad at a raised bed with a trowel, morning "
                         "light; product and use both visible."),
            premise=("A dense diamond lattice kneeling pad in pine and gold saves the knees "
                     "on the first spring weekend outdoors."))),
]


def candidate_concepts() -> tuple[list[Concept], dict[str, list[str]]]:
    """The new candidates as concepts, and every candidate refused with its reasons."""
    out: list[Concept] = []
    refused: dict[str, list[str]] = {}
    for c in NEW_CANDIDATES:
        brief: EmotionalBrief = c["brief"]
        problems = validate(brief, motif=c["motif"], title=brief.title)
        if problems:
            refused[c["key"]] = problems
            continue
        try:
            concept = to_concept(
                brief, key=c["key"], title=brief.title, pod=c["pod"], form=c["form"],
                construction=c["construction"], motif=c["motif"],
                palette_story=c["palette_story"], make_lane=c["make_lane"],
                provenance=f"{AUTHOR}, {AUTHORED}: moment-first concept candidate; no CIR")
        except ConceptRefused as exc:
            refused[c["key"]] = [str(exc)]
            continue
        problems = promise_problems(concept)
        if problems:
            refused[c["key"]] = problems
            continue
        out.append(concept)
    return out, refused


def audit_candidates(catalogue: list[Concept]) -> dict:
    """Judge the new candidates against the catalogue and each other, with the unchanged jury."""
    from .jury import Context, judge

    concepts, refused = candidate_concepts()
    verdicts = []
    for concept in concepts:
        others = list(catalogue) + [c for c in concepts if c.key != concept.key]
        verdicts.append(judge(concept, Context(catalogue=others, techniques=1)))
    deaths: dict[str, int] = {}
    for v in verdicts:
        for f in v.findings:
            deaths[f.critic] = deaths.get(f.critic, 0) + 1
    return {"cohort": "w4_moment_first_candidates",
            "stage": "concept only: no CIR, pattern, listing or photograph exists",
            "proposed": len(NEW_CANDIDATES), "refused_at_brief": refused,
            "judged": len(verdicts),
            "survivors": [v.concept for v in verdicts if v.survives],
            "decisions": {v.concept: v.decision for v in verdicts},
            "deaths_by_critic": deaths,
            "verdicts": [v.to_dict() for v in verdicts],
            "briefs": {c["key"]: c["brief"].to_dict() for c in NEW_CANDIDATES}}
