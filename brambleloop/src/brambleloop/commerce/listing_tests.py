"""Listing tests with a memory, so a disproven idea is not proposed again every quarter.

Requirement 16. `growth.experiments` already holds the part that makes a result mean
anything: a hypothesis, a design, thresholds fixed before the run, and a refusal to call a
pre/post comparison causal. This module adds the four things a *listing* test needs on top of
that -- a pre-period, exposure, confounders and one primary variable at a time -- and the
memory that stops the company re-testing what it has already disproved.

Nothing here restates the pre-registration rules. The plan is an `Experiment` from that
module and the verdict is its verdict; what this adds is the context that decides whether
the verdict may be believed, and whether it may be written down as a thing now known.

**Exposure is the one that matters, and it is the defect this build keeps meeting.** A
listing nobody saw did not fail. It was not tested. A result with no exposure looks exactly
like a result with a bad outcome to anything that reads the number, and the consequence here
is worse than a wrong verdict: a disproof gets written into the memory, and an idea that was
never tried is blocked from being tried. So exposure is required before any verdict is
believed at all, and an unexposed test writes nothing.

**A pre-period is what the listing was doing before.** Without it, the treatment's number is
a number, and the direction people read into it is the direction they expected.

**A confounder is recorded during the window, not remembered afterwards.** A sale, a holiday,
a platform change, a competitor's launch -- each is a reason the result is about something
else, and each is invisible three weeks later when somebody reads the verdict and not the
notes.

**One primary variable at a time, and the honest handling of "where practical".** A test that
changes three things is allowed, because sometimes a listing is rebuilt. It simply cannot
attribute the outcome to any one of them, and its memory entry is about the bundle rather
than about a variable -- so a multi-variable win never writes a disproof that blocks a clean
single-variable test later.

**The memory has to be able to forget, or it becomes a way to stop learning.** An idea
disproved in a context is refused while that context holds and re-testable when it has
materially changed -- a different season, a different price band, a catalogue at a different
maturity -- and the caller has to name what changed. A memory that refuses forever is the
same failure as no memory at all, arriving from the other side.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..growth.experiments import CAUSAL_DESIGNS, Experiment
from ..intel.pods import POD_KEYS
from ..radar.market import SEASONAL_EVENTS
from .benchmarks import MATURITY, PRICE_BAND_KEYS

# The variables a listing test can change. Closed, because "we changed the listing" is not a
# variable and cannot be remembered as one.
VARIABLES: dict[str, str] = {
    "title": "the words a shopper reads in search results",
    "thumbnail": "the first image, at the size it is actually seen",
    "price": "what it costs",
    "tags": "the phrases the listing reaches for",
    "description": "what the page says the buyer receives",
    "hero_image": "the first image inside the listing",
    "video": "whether there is a video at all",
    "bundle": "what is included with the pattern",
}

# What decides whether the result is about the change or about the world it happened in.
CONFOUNDERS: dict[str, str] = {
    "shop_sale": "a discount ran across the shop during the window",
    "platform_change": "the marketplace changed ranking, layout or fees",
    "seasonal_peak": "the window contains the occasion the product is for",
    "competitor_launch": "a comparable listing appeared or was promoted",
    "stock_out": "something the listing depends on was unavailable",
    "press": "outside attention arrived from somewhere nobody arranged",
    "other_test": "another test on the same listing overlapped this window",
}

# A window shorter than this is a weekend, and a weekend is a weekday effect.
MIN_WINDOW_DAYS = 14
# The pre-period has to be long enough to be a baseline rather than a mood.
MIN_PRE_PERIOD_DAYS = 14
# Below this nobody saw it, whatever the outcome column says.
MIN_EXPOSURE = 200

# What a context is made of, for the memory. Named rather than free text, because a memory
# keyed on prose is a memory nobody can query -- and the vocabularies are the ones the rest
# of the system already uses, because a memory keyed on "under_10" while the benchmarks say
# "6_to_10" is a memory that silently matches nothing and lets every closed question be
# re-asked. That failure looks exactly like having no memory, and costs the work of having
# one.
CONTEXT_KEYS: tuple[str, ...] = ("pod", "price_band", "season", "shop_maturity")
SEASONS: tuple[str, ...] = tuple(e.name for e in SEASONAL_EVENTS) + ("none",)
CONTEXT_VOCABULARY: dict[str, tuple[str, ...]] = {
    "pod": POD_KEYS, "price_band": PRICE_BAND_KEYS, "season": SEASONS,
    "shop_maturity": MATURITY,
}

DISPROVED = "disproved"
SUPPORTED = "supported"
INCONCLUSIVE = "inconclusive"
NOT_TESTED = "not_tested"


class ListingTestRefused(ValueError):
    """A test that cannot be read, or an idea being re-tested for no new reason."""


@dataclass(frozen=True)
class Context:
    """Where a result applies. An idea disproved for CA$6 ornaments is not disproved."""

    pod: str
    price_band: str
    season: str
    shop_maturity: str

    def __post_init__(self) -> None:
        for name, allowed in CONTEXT_VOCABULARY.items():
            value = getattr(self, name)
            if value not in allowed:
                raise ListingTestRefused(
                    f"{value!r} is not a {name}: {list(allowed)}. A context keyed on a "
                    f"near-miss matches nothing, so every closed question quietly reopens "
                    f"and the memory reads as empty rather than as broken")

    def key(self) -> str:
        return "|".join((self.pod, self.price_band, self.season, self.shop_maturity))

    def differences(self, other: "Context") -> list[str]:
        return [k for k in CONTEXT_KEYS if getattr(self, k) != getattr(other, k)]


@dataclass
class ListingTest:
    """One listing test: the plan, the window it ran in, and what the world was doing."""

    key: str
    listing_ref: str
    plan: Experiment
    variables: tuple[str, ...]
    context: Context
    pre_period_days: int = 0
    pre_period_value: float | None = None
    window_days: int = 0
    exposure: int | None = None
    confounders: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.variables:
            raise ListingTestRefused(
                "a test that changes nothing is a period of time. Name the variable")
        unknown = [v for v in self.variables if v not in VARIABLES]
        if unknown:
            raise ListingTestRefused(
                f"{unknown} are not listing variables: {sorted(VARIABLES)}. 'We changed the "
                f"listing' cannot be remembered as a variable, which is the whole point of "
                f"remembering")
        bad = [c for c in self.confounders if c not in CONFOUNDERS]
        if bad:
            raise ListingTestRefused(f"{bad} are not confounders: {sorted(CONFOUNDERS)}")

    @property
    def primary(self) -> str | None:
        """The single variable this result can be about, or None when it changed several."""
        return self.variables[0] if len(self.variables) == 1 else None

    @property
    def idea(self) -> str:
        """What is being remembered: one variable, or the bundle as a bundle."""
        return self.primary or "+".join(sorted(self.variables))


def exposure_refusal(exposure: int | None) -> str | None:
    """Why a result on this much exposure may not be read, or None when it may.

    The one exposure rule, shared by a listing test here and by the runtime experiment
    conclusion step (`growth.experiments.conclude_all`, F-260), so the two paths cannot
    disagree about whether a listing was seen.
    """
    if exposure is None:
        return ("exposure was not recorded, so nobody knows whether this listing was seen. An "
                "unexposed test is not a failed test, and the two are indistinguishable to "
                "anything reading the outcome")
    if exposure < MIN_EXPOSURE:
        return (f"{exposure} impressions against a floor of {MIN_EXPOSURE}: a listing "
                f"nobody saw did not fail, it was not tested")
    return None


def check_design(test: ListingTest) -> dict:
    """Everything wrong with this test before it is read. Empty means it can be read."""
    problems: list[str] = []

    refusal = exposure_refusal(test.exposure)
    if refusal:
        problems.append(refusal)

    if test.pre_period_days < MIN_PRE_PERIOD_DAYS:
        problems.append(
            f"a pre-period of {test.pre_period_days} day(s) against {MIN_PRE_PERIOD_DAYS}. "
            f"Without a baseline the treatment's number is a number, and the direction "
            f"people read into it is the direction they expected")
    if test.pre_period_value is None:
        problems.append("no pre-period value recorded, which is the same gap wearing a "
                        "sufficient number of days")

    if test.window_days < MIN_WINDOW_DAYS:
        problems.append(f"a window of {test.window_days} day(s) against {MIN_WINDOW_DAYS}: "
                        f"shorter than this measures the weekday, not the change")

    return {"key": test.key, "readable": not problems, "problems": problems}


def read(test: ListingTest) -> dict:
    """The verdict, and what it is a verdict about.

    The plan's own verdict decides whether the numbers moved; this decides whether that
    reading means anything and what, precisely, may be written down afterwards.
    """
    design = check_design(test)
    plan_verdict = test.plan.verdict()

    if not design["readable"]:
        return {
            "key": test.key, "outcome": NOT_TESTED, "remember": False,
            "idea": test.idea, "context": test.context.key(),
            "problems": design["problems"], "plan_verdict": plan_verdict,
            "why": ("this test cannot be read, and an unreadable test writes nothing to "
                    "memory. Recording it as a disproof would block an idea nobody has "
                    "actually tried"),
        }

    outcome = {"success": SUPPORTED, "failure": DISPROVED}.get(
        plan_verdict.get("verdict"), INCONCLUSIVE)

    attributable = test.primary is not None
    causal = test.plan.design in CAUSAL_DESIGNS
    blockers: list[str] = []
    if test.confounders:
        blockers.append(
            f"confounded by {list(test.confounders)}: the window contains a reason the "
            f"number moved that is not the change")
    if not attributable:
        blockers.append(
            f"{len(test.variables)} variables changed together, so the outcome belongs to "
            f"the bundle and to none of them. Remembered as a bundle, which is why it will "
            f"not block a clean test of any one of them later")

    # A disproof is the only outcome that closes a door, so it is the only one held to the
    # full standard. A supported result that is merely associative is still worth keeping.
    remember = outcome in (SUPPORTED, DISPROVED) and not test.confounders
    if outcome == DISPROVED and not causal:
        blockers.append(
            f"a {test.plan.design} design cannot separate this from the season or the "
            f"weekday, and a disproof is the one verdict that stops future work. Kept as an "
            f"observation rather than as a closed question")
        remember = False

    return {
        "key": test.key, "outcome": outcome, "remember": remember,
        "idea": test.idea, "variables": list(test.variables),
        "attributable_to_one_variable": attributable,
        "causal": causal,
        "context": test.context.key(),
        "pre_period_value": test.pre_period_value,
        "observed": test.plan.observed,
        "exposure": test.exposure,
        "confounders": list(test.confounders),
        "qualifications": blockers,
        "plan_verdict": plan_verdict,
    }


@dataclass(frozen=True)
class Memory:
    """One thing this company has established, where it applies and what proved it."""

    idea: str
    context: str
    outcome: str
    test_key: str
    on: date
    exposure: int
    note: str = ""


def remember(memory: list[Memory], test: ListingTest, *, on: date | None = None) -> dict:
    """Write a result into the memory, when the result has earned a place in it."""
    verdict = read(test)
    if not verdict["remember"]:
        return {"written": False, "outcome": verdict["outcome"],
                "why": verdict.get("why") or "; ".join(verdict.get("qualifications", []))
                       or "an inconclusive result closes nothing and opens nothing"}
    entry = Memory(idea=verdict["idea"], context=verdict["context"],
                   outcome=verdict["outcome"], test_key=test.key,
                   on=on or date.today(), exposure=int(test.exposure or 0),
                   note="; ".join(verdict["qualifications"]))
    memory.append(entry)
    return {"written": True, "entry": entry.__dict__, "outcome": entry.outcome}


def may_test(memory: list[Memory], *, idea: str, context: Context,
             changed_since: tuple[str, ...] = ()) -> dict:
    """Whether this idea may be tested here, given what is already known.

    A disproof closes the question in the context that produced it and nowhere else, and it
    reopens when the caller names what has materially changed. Both halves are the
    requirement: a memory that never refuses is not a memory, and one that never forgets is
    a way to stop learning.
    """
    bad = [c for c in changed_since if c not in CONTEXT_KEYS]
    if bad:
        raise ListingTestRefused(
            f"{bad} are not parts of a context: {list(CONTEXT_KEYS)}. 'Things feel different "
            f"now' reopens every question ever closed")

    disproofs = [m for m in memory if m.idea == idea and m.outcome == DISPROVED]
    here = [m for m in disproofs if m.context == context.key()]
    if not here:
        elsewhere = [m.context for m in disproofs]
        return {
            "may_test": True, "idea": idea, "context": context.key(),
            "why": (f"disproved in {elsewhere}, which is a different context. An idea "
                    f"disproved for one department at one price band is not disproved"
                    if elsewhere else "nothing is known about this idea here"),
        }

    last = max(here, key=lambda m: m.on)
    if changed_since:
        return {
            "may_test": True, "idea": idea, "context": context.key(),
            "reopened_by": list(changed_since),
            "why": (f"disproved on {last.on.isoformat()} by {last.test_key}, and reopened "
                    f"because {list(changed_since)} changed. The result stands for the "
                    f"context it was measured in; this is no longer that context"),
        }
    return {
        "may_test": False, "idea": idea, "context": context.key(),
        "disproved_on": last.on.isoformat(), "by": last.test_key,
        "exposure": last.exposure,
        "why": (f"{idea} was disproved here on {last.on.isoformat()} ({last.test_key}, "
                f"{last.exposure} impressions). Re-running it without naming what has "
                f"changed spends the same month to learn the same thing"),
    }


def known(memory: list[Memory], *, context: Context | None = None) -> dict:
    """What this company has actually established, and where it applies."""
    rows = [m for m in memory
            if context is None or m.context == context.key()]
    return {
        "entries": [{"idea": m.idea, "outcome": m.outcome, "context": m.context,
                     "on": m.on.isoformat(), "by": m.test_key, "exposure": m.exposure}
                    for m in sorted(rows, key=lambda m: (m.idea, m.on))],
        "count": len(rows),
        "of": len(memory),
        "note": ("nothing has been established yet. An empty memory is an empty memory: no "
                 "idea has been disproved here, and none has been supported either"
                 if not rows else ""),
    }


def load(db) -> list[Memory]:
    """The memory as it stands, from the table that outlives the process.

    A memory held in a list is not a memory: "we tried that last year" is exactly the
    knowledge a restart loses, and losing it is how the same disproved idea gets funded
    again by people who were not being careless.
    """
    from sqlalchemy import select

    from ..core.models import ListingMemory

    return [Memory(idea=r.idea, context=r.context, outcome=r.outcome, test_key=r.test_key,
                   on=r.on.date(), exposure=r.exposure, note=r.note or "")
            for r in db.scalars(select(ListingMemory))]


def write(db, test: ListingTest, *, on: date | None = None) -> dict:
    """Write a result to the durable memory, when the result has earned a place in it."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import ListingMemory

    staged: list[Memory] = []
    out = remember(staged, test, on=on)
    if not out["written"]:
        return out
    entry = staged[0]
    # Idempotent: the same result recorded twice is a re-run rather than a second finding,
    # and a unique-constraint error is a poor way to say so.
    existing = db.scalar(select(ListingMemory)
                         .where(ListingMemory.test_key == entry.test_key)
                         .where(ListingMemory.idea == entry.idea))
    if existing is not None:
        return {"written": False, "outcome": entry.outcome,
                "why": f"{entry.test_key} is already recorded against {entry.idea!r}"}
    db.add(ListingMemory(
        idea=entry.idea, context=entry.context, outcome=entry.outcome,
        test_key=entry.test_key, exposure=entry.exposure, note=entry.note,
        on=datetime(entry.on.year, entry.on.month, entry.on.day, tzinfo=timezone.utc)))
    db.flush()
    return out


def state() -> dict:
    """The discipline, for a reader asking what a listing test has to carry."""
    return {
        "variables": dict(VARIABLES),
        "confounders": dict(CONFOUNDERS),
        "floors": {"pre_period_days": MIN_PRE_PERIOD_DAYS, "window_days": MIN_WINDOW_DAYS,
                   "exposure": MIN_EXPOSURE},
        "context_keys": list(CONTEXT_KEYS),
        "outcomes": [SUPPORTED, DISPROVED, INCONCLUSIVE, NOT_TESTED],
        "note": ("A listing nobody saw did not fail; it was not tested, and an unreadable "
                 "test writes nothing to memory -- because recording it as a disproof would "
                 "block an idea nobody has tried. A disproof closes a question only in the "
                 "context that produced it, and reopens when the caller names what changed "
                 "(#16)."),
    }


# ---- variant content and activation (F-779) -----------------------------------------------
#
# Conversion work may change the words, the order, the first image and the price. It may not
# change what the buyer receives or what the design is. A variant is the treatment arm's
# content, and `activate_variant` is the one step it passes before it is shown to anybody:
# the full listing policy check against the CIR (fit, size coverage, untraceable claims,
# difficulty/proof claims), and a truth diff against the certified control copy so that no
# product fact appears in the variant that the certified listing does not already carry.

# The product facts conversion copy may not distort, each as phrases a reader takes as a
# statement about the product. A fact in the variant and not in the control is a new product
# claim made for conversion, which is exactly what F-779 forbids.
TRUTH_FACTS: dict[str, tuple[str, ...]] = {
    "difficulty": (r"\bbeginner\b", r"\beasy\b", r"\bconfident beginner\b",
                   r"\bintermediate\b", r"\badvanced\b", r"\bexpert\b", r"\bsimple\b"),
    "materials": (r"\blace weight\b", r"\bfingering\b", r"\bsport weight\b", r"\bdk\b",
                  r"\bworsted\b", r"\baran\b", r"\bsuper bulky\b", r"\bbulky\b",
                  r"\bchunky\b", r"\bjumbo\b", r"\bcotton\b", r"\bwool\b", r"\bacrylic\b",
                  r"\bmerino\b", r"\balpaca\b", r"\bbamboo\b"),
    "construction": (r"\btop[- ]down\b", r"\bbottom[- ]up\b", r"\bseamless\b",
                     r"\bno[- ]sew\b", r"\braglan\b", r"\bdrop[- ]shoulder\b",
                     r"\bin the round\b", r"\bside[- ]to[- ]side\b", r"\bone[- ]piece\b",
                     r"\bjoin[- ]as[- ]you[- ]go\b"),
    "stitch_appearance": (r"\bcables?\b", r"\bbobbles?\b", r"\bpopcorn\b", r"\bpuff\b",
                          r"\bstar stitch\b", r"\bwaffle\b", r"\bmoss stitch\b",
                          r"\blinen stitch\b", r"\bshells?\b", r"\bribbed\b",
                          r"\bpost stitch\b", r"\bmosaic\b", r"\bgranny\b", r"\bc2c\b",
                          r"\bcorner[- ]to[- ]corner\b", r"\btapestry\b", r"\blace\b"),
    "deliverables": (r"\bkit\b", r"\byarn included\b", r"\bphysical\b", r"\bfinished item\b",
                     r"\bready[- ]made\b", r"\bprinted\b", r"\bshipped\b", r"\bvideo\b",
                     r"\bcharts?\b", r"\bwritten instructions\b", r"\bphoto tutorial\b",
                     r"\bsvg\b", r"\bhook included\b", r"\bpdf\b"),
}
# Which listing fields each variable may change. A variant that changes anything else changes
# a variable the test did not declare, and its result could not be attributed.
VARIABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("title",), "description": ("description",), "tags": ("tags",),
    "price": ("price_cad",), "thumbnail": ("thumbnail",), "hero_image": ("hero_image",),
    "video": ("video",), "bundle": ("bundle",),
}
_VARIANT_FIELDS = ("title", "description", "tags", "price_cad", "thumbnail", "hero_image",
                   "video", "bundle")


@dataclass(frozen=True)
class ListingVariant:
    """The treatment arm's content: the control listing with the tested variables changed."""

    test_key: str
    title: str
    description: str
    tags: tuple[str, ...] = ()
    price_cad: float = 0.0
    thumbnail: str | None = None
    hero_image: str | None = None
    video: str | None = None
    bundle: str | None = None


def _facts(text: str) -> dict[str, set[str]]:
    import re

    low = (text or "").lower()
    out: dict[str, set[str]] = {}
    for family, patterns in TRUTH_FACTS.items():
        found = {m.group(0).replace("-", " ") for p in patterns for m in re.finditer(p, low)}
        out[family] = found
    return out


def truth_drift(control_text: str, variant_text: str) -> dict[str, list[str]]:
    """Product facts the variant states that the certified control copy does not."""
    before, after = _facts(control_text), _facts(variant_text)
    return {fam: sorted(after[fam] - before[fam]) for fam in TRUTH_FACTS
            if after[fam] - before[fam]}


def variant_findings(test: ListingTest, variant: ListingVariant, *, control: ListingVariant,
                     cir=None, certified_assets: frozenset[str] | set[str] = frozenset(),
                     proof_states: dict | None = None, classification=None) -> list[str]:
    """Every reason this variant may not be shown. Empty means it may be activated."""
    from ..gates.policy import ListingDraft, check_listing

    problems: list[str] = []
    if variant.test_key != test.key:
        problems.append(f"variant belongs to {variant.test_key!r}, not test {test.key!r}")
    allowed = {f for v in test.variables for f in VARIABLE_FIELDS[v]}
    changed = [f for f in _VARIANT_FIELDS if getattr(variant, f) != getattr(control, f)]
    undeclared = [f for f in changed if f not in allowed]
    if undeclared:
        problems.append(f"VARIANT_UNDECLARED_CHANGE: {undeclared} changed, but the test "
                        f"declares only {list(test.variables)}")
    if cir is None:
        problems.append("VARIANT_NO_PRODUCT_TRUTH: no certified CIR to check the copy against; "
                        "an unchecked variant is not activated")
    else:
        draft = ListingDraft(title=variant.title, description=variant.description,
                             tags=list(variant.tags), price_cad=variant.price_cad)
        for f in check_listing(draft, cir, proof_states=proof_states,
                               classification=classification):
            if f.is_error:
                problems.append(f"{f.code}: {f.message}")
    control_text = " ".join([control.title, control.description, *control.tags])
    variant_text = " ".join([variant.title, variant.description, *variant.tags])
    for family, words in truth_drift(control_text, variant_text).items():
        problems.append(f"VARIANT_TRUTH_DRIFT: {family} {words} stated by the variant and not "
                        f"by the certified listing (F-779: conversion may not distort "
                        f"{family.replace('_', ' ')})")
    for field_name in ("thumbnail", "hero_image"):
        ref = getattr(variant, field_name)
        if field_name in changed and ref not in certified_assets:
            problems.append(f"VARIANT_IMAGE_UNCERTIFIED: {field_name} {ref!r} is not one of "
                            f"this release's certified listing assets")
    return problems


def activate_variant(test: ListingTest, variant: ListingVariant, *, control: ListingVariant,
                     cir=None, certified_assets: frozenset[str] | set[str] = frozenset(),
                     proof_states: dict | None = None, classification=None) -> dict:
    """The one door a listing-test variant passes before anybody sees it (F-779)."""
    problems = variant_findings(test, variant, control=control, cir=cir,
                                certified_assets=certified_assets, proof_states=proof_states,
                                classification=classification)
    return {"test_key": test.key, "activated": not problems, "problems": problems,
            "changed": [f for f in _VARIANT_FIELDS
                        if getattr(variant, f) != getattr(control, f)]}
