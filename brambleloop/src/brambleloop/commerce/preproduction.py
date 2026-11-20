"""Testing a concept before engineering it, without ever implying it can be bought.

Requirement 4. Test truthful concepts and aesthetics on owned and social channels *before*
expensive engineering -- clearly identified as concepts -- and never with fake listings, fake
purchases or fake engagement.

The value is obvious and so is the hazard, and they are the same act. A picture of a thing
that does not exist, posted where people buy things, is a pre-order somebody will try to
place. So the control is not a guideline about tone; it is a refusal, and it runs on the text
that will actually be posted.

**A concept post says it is a concept.** In the words a scroller reads, not in a hashtag at
the end. A post that omits it is refused here rather than corrected after somebody asks where
to buy.

**Nothing may imply availability.** "Get yours", "shop now", "link in bio", a price, an
add-to-cart -- each is a promise about a thing that does not exist, and the requirement's own
sentence forbids implying an unavailable item is a finished purchasable product.

**No metric is ever written by this system.** Interest comes from the platform or it does not
exist. There is no code path here that can author an engagement number, and a test asserts
that by reading the source, because "we would never" is not a control and the whole category
does this.

What this module cannot do is post. No social credential has been granted, so the artefact is
prepared and the publishing step reports gated -- which is the honest state and also the safe
one, since a refusal that runs before an unpublishable post is a refusal that has been tested.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# The phrase a concept post must carry, in the reader's own language. Checked as meaning
# rather than as an exact string, because a rule satisfied by one blessed sentence is a rule
# somebody routes around by writing a different one.
CONCEPT_MARKERS: tuple[str, ...] = (
    "concept", "not yet available", "not for sale", "in development",
    "would you make this", "thinking about making",
)

# Language that promises a purchase. Each is a promise about a thing that does not exist.
IMPLIES_AVAILABILITY: tuple[tuple[str, str], ...] = (
    (r"\bshop now\b", "sends a reader to buy something that does not exist"),
    (r"\bget yours\b", "implies there are some"),
    (r"\bbuy (it|now|here)\b", "an instruction to purchase"),
    (r"\border (now|here|yours)\b", "an instruction to purchase"),
    (r"\bavailable now\b", "states availability directly"),
    (r"\bin stock\b", "states availability directly"),
    (r"\blink in bio\b", "a purchase route by convention, whatever it points at"),
    (r"\badd to cart\b", "a purchase action"),
    (r"\bpre-?order\b", "takes money for an unengineered pattern"),
    (r"\$\s?\d", "a price is an offer"),
    (r"\bca\$\s?\d", "a price is an offer"),
)

# Metrics this system may never author. Listed so the prohibition is visible in the module
# rather than only in a commit message.
NEVER_FABRICATED: tuple[str, ...] = (
    "likes", "saves", "shares", "comments", "followers", "impressions", "clicks",
    "purchases", "reviews", "favourites",
)


class PreProductionRefused(ValueError):
    """A concept post that implies a purchase, or a metric this system tried to invent."""


@dataclass(frozen=True)
class ConceptPost:
    """One concept, prepared for an owned or social channel and not yet posted."""

    concept_key: str
    channel: str
    body: str
    prepared_on: date
    image_source: str = "twin"      # what the picture is; never a competitor's photograph
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"concept": self.concept_key, "channel": self.channel, "body": self.body,
                "prepared_on": self.prepared_on.isoformat(),
                "image_source": self.image_source, "detail": dict(self.detail)}


def _says_it_is_a_concept(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in CONCEPT_MARKERS)


def check_post(body: str) -> list[dict]:
    """Everything wrong with this post before it may be prepared. Empty means nothing is."""
    problems: list[dict] = []
    low = (body or "").lower()

    if not _says_it_is_a_concept(low):
        problems.append({
            "problem": "does not say it is a concept",
            "why": (f"a picture of a thing that does not exist, posted where people buy "
                    f"things, is a pre-order somebody will try to place. It has to say so in "
                    f"the words a scroller reads -- one of {list(CONCEPT_MARKERS)[:3]} or "
                    f"their like -- not in a hashtag at the end"),
        })
    for pattern, why in IMPLIES_AVAILABILITY:
        match = re.search(pattern, low)
        if match:
            problems.append({
                "problem": f"implies availability: {match.group(0)!r}",
                "why": (f"{why}. The requirement forbids implying an unavailable item is a "
                        f"finished purchasable product"),
            })
    return problems


def prepare(concept, *, channel: str, body: str, today: date | None = None,
            image_source: str = "twin") -> ConceptPost:
    """Build a concept post, or refuse it and say exactly which rule it broke."""
    if image_source not in ("twin", "photograph_of_our_own_sample"):
        raise PreProductionRefused(
            f"{image_source!r} is not an image this company may post. A concept shown with "
            f"somebody else's photograph is a competitor's work presented as a plan, which "
            f"the asset rules refuse at every other door too")
    problems = check_post(body)
    if problems:
        raise PreProductionRefused("; ".join(p["problem"] for p in problems))
    return ConceptPost(concept_key=getattr(concept, "key", str(concept)), channel=channel,
                       body=body, prepared_on=today or date.today(),
                       image_source=image_source,
                       detail={"stage": "pre-production",
                               "engineered": False,
                               "why_now": ("tested before expensive engineering, which is "
                                           "the point of the stage")})


def record_interest(post: ConceptPost, *, observed: dict | None,
                    source: str) -> dict:
    """Attach interest to a concept post -- only ever from the platform that measured it.

    There is no path here that can author a number. `observed` is what a platform reported
    and `source` is where it came from; with neither, this returns unmeasured with the
    reason, because the one thing worse than no signal is a signal this company wrote for
    itself.
    """
    if not observed:
        return {
            "concept": post.concept_key, "measurable": False, "source": "",
            "why": ("no platform has reported anything about this post, so interest in it is "
                    "unknown. Writing a number here would be fabricated engagement, which "
                    "is forbidden outright rather than discouraged"),
        }
    if not source.strip():
        raise PreProductionRefused(
            "interest with no named source cannot be told apart from interest this company "
            "invented, which is the whole reason the prohibition exists")
    unknown = [k for k in observed if k not in NEVER_FABRICATED]
    return {
        "concept": post.concept_key,
        "measurable": True,
        "source": source,
        "observed": {k: v for k, v in observed.items()},
        "unrecognised_metrics": unknown,
        "why": (f"reported by {source}. Every number here came from the platform that "
                f"measured it; this system has no code path that can author one"),
    }


def validate(concepts: list, *, channel: str = "pinterest",
             today: date | None = None) -> dict:
    """Prepare concept posts for a set of survivors, and report what cannot be done yet.

    Publishing is gated: no social credential has been granted. That is the honest state and
    also the safe one -- the refusals run before an unpublishable post, so they have been
    exercised by the time posting becomes possible.
    """
    prepared, refused = [], []
    for concept in concepts:
        body = _body_for(concept)
        try:
            prepared.append(prepare(concept, channel=channel, body=body, today=today))
        except PreProductionRefused as e:
            refused.append({"concept": getattr(concept, "key", str(concept)),
                            "why": str(e)})
    return {
        "prepared": [p.to_dict() for p in prepared],
        "refused": refused,
        "publishing": {
            "state": "gated",
            "gated_on": "social_credentials",
            "why": ("no social or Pinterest credential has been granted, so nothing here is "
                    "posted. The refusals run anyway, which means they are tested before "
                    "the day they matter"),
        },
        "never": {
            "fake_listings": "a listing for a pattern that does not exist is a fake listing",
            "fake_purchases": "forbidden outright",
            "fake_engagement": ("no code path in this module can author a metric, and a test "
                                "asserts it by reading the source, because 'we would never' "
                                "is not a control"),
        },
    }


def _body_for(concept) -> str:
    """Post copy assembled from the concept, saying plainly that it is a concept."""
    premise = getattr(concept, "premise", "")
    return (f"A concept we are thinking about making: {premise} "
            f"It is not yet available and may never be — we are asking before we engineer "
            f"it, not selling it. Would you make this?")
