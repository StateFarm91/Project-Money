"""Marketing and the content ecosystem (Master Plan section 11).

Section 11: every strong product becomes a content ecosystem — Etsy listing, website article,
Pinterest variants, tutorial or video, short clips, email, a teaser or free motif where
useful, collection cross-sell, and a crochet-along candidate.

Everything here is drafted and held. There is no Pinterest, email, YouTube or social
integration in this system, and shadow mode means nothing is scheduled to publish itself. A
plan that cannot post is the point, not a limitation: it means the catalogue's marketing can
be built and reviewed before a single account exists.

Two constraints run through all of it. Copy may only assert what the compiled pattern
supports, which is why the pieces below are built from twin facts rather than adjectives. And
the free teaser is a real, working, validated motif — section 11 allows a free motif "where
useful", and a teaser that does not work is a worse advertisement than no teaser.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

CHANNELS = ("article", "pinterest", "video", "email", "teaser", "cross_sell", "cal")

# Pinterest's practical limits.
PIN_TITLE_MAX = 100
PIN_DESCRIPTION_MAX = 500
PINS_PER_PRODUCT = 4


@dataclass
class Piece:
    channel: str
    title: str
    body: str
    scheduled_for: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"channel": self.channel, "title": self.title, "body": self.body,
                "scheduled_for": self.scheduled_for, "detail": dict(self.detail)}


@dataclass
class ProductFacts:
    """Only things the compiled pattern knows. Nothing here can be an adjective."""

    slug: str
    title: str
    category: str
    size_label: str | None
    difficulty: str
    stitches: list[str]
    colors: list[str]
    yardage_line: str
    maker_hours: tuple[float, float]
    season: str | None
    price_cad: float
    siblings: list[str] = field(default_factory=list)


def _article(f: ProductFacts) -> Piece:
    """The long-form piece. Its job is to rank and to answer, not to sell hard."""
    body = f"""# {f.title}

A {f.category.replace('_', ' ')} pattern, worked in {len(f.colors)} colours
({', '.join(f.colors)}) using {', '.join(f.stitches)}.

## What you are making
{f.size_label or 'See the pattern for finished measurements'}, at the gauge given in the
pattern. Difficulty: {f.difficulty}.

## How long it takes
Between {f.maker_hours[0]:g} and {f.maker_hours[1]:g} hours depending on how fast you work.
That range is the honest one: a confident maker at the fast end, someone fitting it around a
week at the slow end.

## What you will need
{f.yardage_line}

## Why the counts in this pattern are right
Every row in this pattern was checked by a compiler before release — stitch by stitch, count
by count, and again by a second program that reads only the finished customer pattern and
reconstructs it from scratch. If the two disagreed anywhere, it would not have been published.
That is not marketing; it is the reason we can tell you the row counts are correct without
having crocheted every size ourselves.

## Common questions
**Can I make it bigger or smaller?** The stitch counts hold at any gauge — only the
measurements change. Work a swatch first.

**US or UK terms?** Both, as two files. Every pattern is delivered as two PDFs -- one
written throughout in US terms and one written throughout in UK terms, each with its own
stitch key. Nothing is left to be translated in your head.
"""
    return Piece("article", f"{f.title} — pattern notes", body,
                 detail={"intent": "search and reassurance, not a sales page"})


def _pins(f: ProductFacts) -> list[Piece]:
    """Four pins with genuinely different angles, not one pin four times."""
    angles = [
        ("the finished object", f"{f.title}", f"A crochet {f.category.replace('_', ' ')} "
         f"pattern in {', '.join(f.colors)}. {f.size_label or ''}".strip()),
        ("the technique", f"How the {f.category.replace('_', ' ')} is built",
         f"Worked with {', '.join(f.stitches)}. Chart and written instructions, US and UK "
         f"terms."),
        ("the time", f"About {f.maker_hours[0]:g}–{f.maker_hours[1]:g} hours",
         f"An honest estimate of how long {f.title} takes, so you can decide before you "
         f"start rather than after."),
        ("the materials", "What you need",
         f"{f.yardage_line} Difficulty: {f.difficulty}."),
    ]
    out = []
    for i, (angle, title, description) in enumerate(angles[:PINS_PER_PRODUCT], start=1):
        out.append(Piece("pinterest", title[:PIN_TITLE_MAX],
                         description[:PIN_DESCRIPTION_MAX],
                         detail={"variant": i, "angle": angle}))
    return out


def _video(f: ProductFacts) -> Piece:
    """A tutorial outline. Section 11 asks for video; the competitors treat it as table stakes."""
    body = "\n".join([
        "0:00  What we are making, and the finished size",
        "0:30  Yarn, hook and gauge — work the swatch first, it decides your finished size",
        "1:30  Reading the chart alongside the written instructions",
        f"2:30  The foundation and row 1",
        "4:00  The repeat, worked slowly once, then at speed",
        "7:00  Changing colour at the end of a row and carrying the resting colour",
        "9:00  The most common place people lose their count, and how to get back",
        "10:30 Finishing and blocking",
    ])
    return Piece("video", f"{f.title} — full tutorial", body,
                 detail={"format": "long-form tutorial",
                         "shorts": ["the colour change", "reading the chart",
                                    "the count-recovery trick"]})


def _email(f: ProductFacts) -> Piece:
    subject = (f"{f.title} — and how long it actually takes"
               if f.maker_hours[1] >= 20 else f"New: {f.title}")
    body = (f"{f.title} is out.\n\n"
            f"{f.size_label or ''} · {f.difficulty} · about {f.maker_hours[0]:g}–"
            f"{f.maker_hours[1]:g} hours · CA${f.price_cad:.2f}\n\n"
            f"{f.yardage_line}\n\n"
            f"Every row was compiler-checked before release, and the chart is generated from "
            f"the same data as the words, so the two cannot disagree.\n\n"
            f"You are getting this because you asked to hear when we release something. "
            f"Unsubscribe any time — one click, no questions.")
    return Piece("email", subject, body,
                 detail={"casl": "express consent required before this is ever sent; "
                                 "unsubscribe in every message; sender identified"})


def _teaser(f: ProductFacts) -> Piece:
    body = (f"A free motif from the {f.title} chart, as a one-page PDF. It is a real, "
            f"compiled, validated piece of the pattern — not a sample image. Work it once and "
            f"you will know whether the full pattern suits how you crochet.")
    return Piece("teaser", f"Free motif from {f.title}", body,
                 detail={"must_be_validated": True,
                         "reason": "a teaser that does not work is worse than no teaser"})


def _cross_sell(f: ProductFacts) -> Piece | None:
    if not f.siblings:
        return None
    return Piece("cross_sell", f"{f.title} is part of a collection",
                 "Also in this collection: " + ", ".join(f.siblings)
                 + ". The collection is sold together at a real saving against buying each "
                   "pattern separately.",
                 detail={"siblings": list(f.siblings)})


def _cal(f: ProductFacts) -> Piece | None:
    """A crochet-along only makes sense for something big enough to need company."""
    if f.maker_hours[1] < 20:
        return None
    weeks = max(4, int(f.maker_hours[1] / 7) + 1)
    return Piece("cal", f"{f.title} crochet-along",
                 f"A {weeks}-week crochet-along: a section a week, with a check-in and a "
                 f"count checkpoint at the end of each. Built for the people who would "
                 f"otherwise stall at week two.",
                 detail={"weeks": weeks, "candidate": True})


def build_ecosystem(f: ProductFacts, *, launch_on: date) -> list[Piece]:
    """The full content plan for one product, scheduled backwards from launch.

    Timing follows section 5's flagship timeline: the article and the listing go out early
    because search indexing takes weeks, teasers land close to launch, and the tutorial
    follows the launch rather than preceding it.
    """
    pieces: list[Piece] = []

    article = _article(f)
    article.scheduled_for = (launch_on - timedelta(days=21)).isoformat()
    pieces.append(article)

    for i, pin in enumerate(_pins(f)):
        pin.scheduled_for = (launch_on - timedelta(days=21 - i * 5)).isoformat()
        pieces.append(pin)

    teaser = _teaser(f)
    teaser.scheduled_for = (launch_on - timedelta(days=10)).isoformat()
    pieces.append(teaser)

    email = _email(f)
    email.scheduled_for = (launch_on - timedelta(days=3)).isoformat()
    pieces.append(email)

    video = _video(f)
    video.scheduled_for = (launch_on + timedelta(days=7)).isoformat()
    pieces.append(video)

    cross = _cross_sell(f)
    if cross:
        cross.scheduled_for = (launch_on + timedelta(days=1)).isoformat()
        pieces.append(cross)

    cal = _cal(f)
    if cal:
        cal.scheduled_for = (launch_on + timedelta(days=14)).isoformat()
        pieces.append(cal)

    return pieces


# ---- checks ----------------------------------------------------------------

_DIMENSION_RE = re.compile(r"\b(\d{2,3}\s*[x×]\s*\d{2,3}\s*cm)\b", re.I)


def _normalise_size(text: str) -> str:
    """Compare sizes by their numbers, so 90 x 122 cm and 90×122cm are the same claim."""
    return re.sub(r"[^0-9]", "", text.split(" at ")[0])


_ENGAGEMENT_BAIT = (
    "follow for follow", "like and share to win", "comment to enter", "tag five friends",
    "free pattern if you follow", "review for a discount",
)


def check_ecosystem(pieces: list[Piece], facts: ProductFacts) -> list[str]:
    """Nothing may promise what the pattern does not deliver, or buy engagement."""
    problems: list[str] = []
    if not pieces:
        return ["CONTENT_EMPTY: a product with no content plan has no way to be found"]

    channels = {p.channel for p in pieces}
    for required in ("article", "pinterest", "email"):
        if required not in channels:
            problems.append(f"CONTENT_MISSING_CHANNEL: {required}")

    pins = [p for p in pieces if p.channel == "pinterest"]
    if len({p.detail.get("angle") for p in pins}) < len(pins):
        problems.append("CONTENT_PINS_NOT_DISTINCT: four pins saying the same thing is one pin")
    for p in pins:
        if len(p.title) > PIN_TITLE_MAX:
            problems.append(f"CONTENT_PIN_TITLE_LONG: {len(p.title)}")
        if len(p.body) > PIN_DESCRIPTION_MAX:
            problems.append(f"CONTENT_PIN_BODY_LONG: {len(p.body)}")

    for p in pieces:
        low = (p.title + " " + p.body).lower()
        for bait in _ENGAGEMENT_BAIT:
            if bait in low:
                problems.append(f"CONTENT_ENGAGEMENT_BAIT: {p.channel} uses {bait!r}")
        # Every dimension pair stated anywhere in the content must be the pattern's own.
        # Checking only that the right size appears is not enough: the failure mode is copy
        # that quotes the correct size in one paragraph and an invented one in another.
        for stated in _DIMENSION_RE.findall(p.title + " " + p.body):
            if not facts.size_label or _normalise_size(stated) != _normalise_size(
                    facts.size_label):
                problems.append(
                    f"CONTENT_SIZE_DRIFT: {p.channel} states {stated!r}, which is not the "
                    f"pattern's computed size "
                    f"{facts.size_label or '(none computed)'!r}")

    email = next((p for p in pieces if p.channel == "email"), None)
    if email and "unsubscribe" not in email.body.lower():
        problems.append("CONTENT_CASL: a commercial email without an unsubscribe is illegal "
                        "in Canada, not merely rude")

    teaser = next((p for p in pieces if p.channel == "teaser"), None)
    if teaser and not teaser.detail.get("must_be_validated"):
        problems.append("CONTENT_TEASER_UNVALIDATED: a free motif that does not work is a "
                        "worse advertisement than none")
    return problems
