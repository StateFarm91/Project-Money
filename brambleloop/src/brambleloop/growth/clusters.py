"""Search clusters built from questions makers actually asked, not questions we imagined.

Requirement 247. Owned search clusters around buyer and maker questions, each mapping
informational intent to a useful free thing and then to a paid product, with organic visits,
assisted conversion, email capture and revenue measured against them.

The decision that matters is where the questions come from. A keyword list produced by
asking a model "what do crocheters search for" is a list of things that sound like searches,
and it is indistinguishable from a good one until a year of writing has been spent on it.
This company already holds a list of questions makers demonstrably have: the complaint themes
counted from observed reviews. A complaint is an informational intent that arrived too late
-- "the stitch counts do not add up", "I ran out of yarn", "it did not fit" are the same
questions somebody would have typed into a search bar a week earlier, and they are counted
rather than imagined.

So a cluster is seeded from an observed theme, and a theme nobody has seen three times is
not a cluster. `intel.observe.RECURRING_AT` decides that, imported rather than restated,
because the word "recurring" is doing the same work in both places.

Three refusals follow.

**A cluster with no paid destination is a blog.** The requirement's own chain is
informational intent, then free content, then a product -- and the third link is the one
that goes missing first, because the first two are enjoyable to make. Every cluster names
the product it leads to and why somebody who has just had their question answered would want
it, on the same rule `growth.free_to_paid` applies to every free asset.

**Two clusters answering the same question compete with each other.** This is #240's
catalogue cannibalisation wearing a different hat: the fix for a thin cluster is depth, and
the natural instinct is to write a second article about the same thing.

**Every number this requirement asks for needs a site nobody has built.** Organic qualified
visits, assisted conversion, email capture and revenue contribution are reported as
unmeasurable with what they need, rather than as zeroes that would make an unbuilt funnel
look like a failed one.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..intel.observe import COMPLAINT_THEMES, RECURRING_AT
from .free_to_paid import FREE_KINDS

# What each observed complaint theme is, as the question somebody would have typed a week
# earlier, and what kind of free thing answers it. Every key here is a theme the observer
# already counts; a question with no theme behind it cannot be added, which is the point.
QUESTIONS: dict[str, dict] = {
    "instructions_unclear": {
        "question": "how do I read a crochet pattern's written instructions",
        "answers_with": "tutorial",
        "why_paid_next": ("somebody who has just learned to read a pattern properly wants "
                          "one written the way the tutorial taught them to read"),
    },
    "counts_wrong": {
        "question": "why do my stitch counts not add up",
        "answers_with": "tool",
        "why_paid_next": ("a counter that finds the row where it went wrong makes the case "
                          "for a pattern whose counts are checked by a compiler"),
    },
    "sizing_wrong": {
        "question": "how do I get crochet to come out the right size",
        "answers_with": "tutorial",
        "why_paid_next": ("gauge is the answer, and the next question is which pattern "
                          "states a finished size it can actually hold"),
    },
    "yarn_estimate_wrong": {
        "question": "how much yarn do I need for this project",
        "answers_with": "tool",
        "why_paid_next": ("a yardage calculator ends on a specific project, and the "
                          "specific project is a pattern"),
    },
    "photos_misleading": {
        "question": "what will this actually look like when I make it",
        "answers_with": "motif",
        "why_paid_next": ("a free motif in the same fabric shows what the yarn does, which "
                          "is the thing the photograph could not"),
    },
    "support_slow": {
        "question": "who do I ask when a pattern goes wrong",
        "answers_with": "tutorial",
        "why_paid_next": ("the answer is a designer who replies, which is a reason to buy "
                          "from one rather than a reason to read an article"),
    },
    "delivery_problem": {
        "question": "how do I download and open a pattern I bought",
        "answers_with": "tutorial",
        "why_paid_next": ("this one leads to a purchase least of all, and saying so is "
                          "better than pretending every article sells something"),
    },
}

# What can be measured about a cluster once there is somewhere to publish it.
METRICS: tuple[str, ...] = (
    "organic_qualified_visits", "assisted_conversion", "email_capture",
    "revenue_contribution")


class ClusterRefused(ValueError):
    """A question nobody asked, a cluster with no destination, or two answering the same."""


@dataclass(frozen=True)
class Cluster:
    """One search cluster: a question, the free thing that answers it, and where it leads."""

    theme: str
    pod: str
    leads_to: str = ""
    observed: int = 0

    def __post_init__(self) -> None:
        if self.theme not in QUESTIONS:
            raise ClusterRefused(
                f"{self.theme!r} is not an observed complaint theme: {sorted(QUESTIONS)}. A "
                f"question nobody has been seen to ask is a question that sounds like a "
                f"search, which is indistinguishable from a real one until a year of writing "
                f"has been spent on it")

    @property
    def question(self) -> str:
        return QUESTIONS[self.theme]["question"]

    @property
    def answers_with(self) -> str:
        return QUESTIONS[self.theme]["answers_with"]


def check(cluster: Cluster) -> dict:
    """Whether this cluster is worth building, and what is missing when it is not."""
    reasons: list[str] = []
    spec = QUESTIONS[cluster.theme]

    if cluster.observed < RECURRING_AT:
        reasons.append(
            f"seen {cluster.observed} time(s), below {RECURRING_AT}. A theme nobody has seen "
            f"recur is one customer's bad day, and a cluster built on it is a year of "
            f"writing about a problem that does not exist")
    if not cluster.leads_to.strip():
        reasons.append(
            "no paid product named. The chain is informational intent, then free content, "
            "then a product, and the third link is the one that goes missing first because "
            "the first two are enjoyable to make")
    if spec["answers_with"] not in FREE_KINDS:
        reasons.append(f"{spec['answers_with']!r} is not a kind of free work")

    return {
        "theme": cluster.theme, "pod": cluster.pod, "ok": not reasons, "reasons": reasons,
        "question": cluster.question,
        "answers_with": spec["answers_with"],
        "leads_to": cluster.leads_to,
        "why_paid_next": spec["why_paid_next"],
        "observed": cluster.observed,
    }


def overlap(clusters: list[Cluster]) -> dict:
    """Which clusters answer the same question, which is the same failure as a catalogue
    competing with itself: the fix for a thin cluster is depth, and the instinct is a second
    article about the same thing."""
    seen: dict[tuple[str, str], list[str]] = {}
    for cluster in clusters:
        seen.setdefault((cluster.pod, cluster.theme), []).append(cluster.leads_to or "?")
    competing = [{"pod": pod, "theme": theme, "destinations": dests}
                 for (pod, theme), dests in sorted(seen.items()) if len(dests) > 1]
    return {
        "competing": competing,
        "ok": not competing,
        "why": ("two clusters answering the same question in the same department rank "
                "against each other, and the one that loses was still written"
                if competing else "every question is answered once"),
    }


def plan(themes: dict[str, int], *, pod: str, destinations: dict[str, str] | None = None,
         ) -> dict:
    """The clusters worth building for one department, from counted themes.

    `themes` is `intel.observe.complaint_themes`' own counts: theme -> how many reviews
    mentioned it. Ranked by that count, because the question people have most often is the
    one worth answering first, and it is a measurement rather than a guess.
    """
    destinations = destinations or {}
    unknown = sorted(set(themes) - set(QUESTIONS))
    if unknown:
        raise ClusterRefused(f"{unknown} are not themes with questions behind them")

    rows = []
    for theme, count in sorted(themes.items(), key=lambda kv: -kv[1]):
        cluster = Cluster(theme=theme, pod=pod, leads_to=destinations.get(theme, ""),
                          observed=count)
        rows.append(check(cluster))

    buildable = [r for r in rows if r["ok"]]
    return {
        "pod": pod,
        "clusters": rows,
        "buildable": len(buildable), "of": len(rows),
        "ranked": [r["theme"] for r in buildable],
        "note": ("no theme in this department recurs often enough to build a cluster on, "
                 "which is a finding about the observation rather than about the department"
                 if not buildable else ""),
    }


def measurement() -> dict:
    """What the requirement asks to be measured, and why none of it can be yet."""
    return {
        "metrics": list(METRICS),
        "measurable": False,
        "why": ("every one of these needs a site with organic traffic. There is none, and "
                "reporting them as zeroes would make an unbuilt funnel look like a failed "
                "one -- which is how something nobody tried gets abandoned"),
        "needs": ["a published article with organic visits", "a consented email capture",
                  "an order attributable to a visit"],
    }


def state() -> dict:
    """Where the questions come from, and what a cluster must carry."""
    return {
        "questions": {k: dict(v) for k, v in QUESTIONS.items()},
        "seeded_from": ("intel.observe.COMPLAINT_THEMES -- counted from observed reviews. A "
                        "complaint is an informational intent that arrived too late, and it "
                        "is the one list of maker questions this company has evidence for"),
        "recurring_at": RECURRING_AT,
        "measurement": measurement(),
        "note": ("A keyword list produced by asking a model what crocheters search for is a "
                 "list of things that sound like searches, and it is indistinguishable from "
                 "a good one until a year of writing has been spent on it (#247)."),
    }
