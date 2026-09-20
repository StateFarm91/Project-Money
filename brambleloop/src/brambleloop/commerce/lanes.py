"""Two production queues, and the floor that stops one of them eating the other.

Requirement 5. The catalogue is built by two standing queues with different jobs. The FAST
LANE makes lower-complexity products -- ornaments, coasters, mug rugs, selected hats, simple
decor, suitable simple amigurumi -- and what it buys is learning rate and search coverage:
many small honest products, each teaching the system something about what sells and each
occupying a search phrase nobody here has occupied before. The FLAGSHIP LANE makes premium
blankets, major collections, selected garments and sophisticated seasonal products, and what
it buys is authority, content depth and average order value. Both keep every applicable
quality gate.

Three things make this a module rather than a policy document.

The first is that the fast lane eats the flagship lane if nothing stops it, and it does so
without anybody deciding to. A fast product is cheaper, finishes sooner, and is individually
the better use of this week; so every week picks fast, and a year later the catalogue is
forty coasters with no authority, no depth and no order value -- a slide that was never
decided, made of defensible steps. The reverse ruins the company more slowly and just as
surely: a catalogue of four magnificent blankets learns almost nothing, because it has had
four chances to find out what sells. So both lanes have a capacity floor, and a mix that
starves either is refused with the number it starved.

The second is routing. A product belongs to a lane because of what it is, not because of
what the calendar wants this week. The commonest way a fast lane goes wrong is a garment
shoved down it against a deadline, so a flagship-shaped product cannot enter the fast lane
by having its numbers argued down: the pods the fast lane serves are named, and a blanket is
not among them however few components somebody claims it has.

The third is that "both retain all applicable quality gates" is exactly the kind of sentence
that stays true in the README and stops being true in the code. It is kept true structurally:
the gate list is the release chain's own, imported rather than retyped, and the function that
computes it takes the *product* and does not take the lane at all. There is no argument to
this module by which a lane can shorten a list. A test asserts that by signature, not by
example, because an example only proves the case somebody thought of.

Two vocabulary notes, because both have already caused a confusion worth naming.

A make lane (QUICK, SHORT, MEDIUM, LONG, FLAGSHIP in `seasonal.calendar`) is *how long a
thing takes to build*. A production lane here is *what the thing is for*. They are not the
same axis and the coincident word is unfortunate: a three-pattern ebook can be QUICK to make
and belong in the flagship queue, because its authority is in the set rather than in the
hours. Make lane is evidence about which queue fits; it is not the queue.

And this module's mix is a share of *making capacity*, never a count of products. A flagship
costs several fast products' worth of engineering, so a 60/40 capacity split does not make
six fast products for every four flagships -- it makes many more. Counting products would
let the floor be satisfied by one ornament per blanket, which is not what either floor is
for. Christmas compression (#6) cuts across both queues rather than competing with this
split: an ornament is fast-lane work and a Christmas blanket is flagship work, and the
occasion takes its share of each.

This queue pair is the standing structure. The fast *response* lane (#291) is a different
thing wearing a similar name: a bounded trend-capture path with a tighter bar. It is tighter
on purpose, and a test here asserts it stays a subset -- a trend product that could not also
travel the ordinary fast lane would be an exemption in a second costume.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..gates.certificate import CANONICAL_STAGES, CONDITIONAL_STAGES
from ..intel.deliverable import SIZED_PODS
from ..intel.pods import POD_KEYS
from ..quality.testers import NEEDS_SAMPLE
from ..seasonal.calendar import LANE_ORDER
from ..seasonal.fastlane import LANE_CEILING as FAST_MAKE_CEILING

FAST = "fast"
FLAGSHIP = "flagship"
LANES: tuple[str, str] = (FAST, FLAGSHIP)

# What each queue is actually bought for. Written down because a lane whose purpose is
# forgotten becomes a lane whose floor looks like bureaucracy.
PURPOSE: dict[str, str] = {
    FAST: ("learning rate and search coverage: many small honest products, each one a "
           "phrase this shop did not occupy and a result it did not have"),
    FLAGSHIP: ("authority, content depth and order value: the products a buyer cites when "
               "they say who this shop is, and the ones that pay for a day of work"),
}

# The pods each queue serves, in the requirement's own words. A pod is a necessary condition
# and never a sufficient one: it says which queue a product may be considered for, and the
# product's own measurements decide whether it qualifies. This is the half that cannot be
# argued down under deadline -- a garment is not fast-lane work at any component count.
#
# Seasonal gift products appear in both lists, and that is the requirement's own wording
# rather than a hedge: the flagship half says "sophisticated seasonal products", which means
# the pod alone does not decide -- a gift-tag set is fast-lane work and an advent calendar
# with twenty-four pieces is not. The make lane does the deciding, below.
FAST_PODS: tuple[str, ...] = ("ornaments", "kitchen_bath", "home_decor", "hats", "amigurumi",
                              "seasonal_gift")
FLAGSHIP_PODS: tuple[str, ...] = ("blankets", "collections", "garments", "seasonal_gift")

# What "lower-complexity" means here, in numbers rather than in judgement.
#
# Class A and B both, as the requirement names them: amigurumi and graded hats are not
# Class A, and excluding them would empty half the lane the requirement describes. C is
# excluded because the compiler cannot verify it completely, and a queue whose argument is
# "there is less to check" cannot be fed the products where checking is hardest.
#
# Class B carries a consequence the lane has to say out loud rather than discover: a B needs
# a physical sample before release (`quality.testers.NEEDS_SAMPLE`, imported below), and a
# sample is the one part of this company nobody can hurry. So a Class B fast-lane product is
# fast in engineering and not in wall clock -- the sample sets the date. That is also why the
# trend lane (#291) takes Class A only: a trend window closes while a sample is in the post,
# and a queue that promises a deadline the sample cannot meet is a queue that will be asked
# to skip the sample.
FAST_RISK_CLASSES: tuple[str, ...] = ("A", "B")
# Four components is one body and three attachments -- an amigurumi with ears and arms. Past
# that the work is assembly, and assembly is where a quick make stops being quick.
FAST_MAX_COMPONENTS = 4
FAST_MAX_COLOURS = 4
# A technique the catalogue has never used needs a physical sample, and a sample is the one
# part of this company nobody can hurry. This is zero in both lanes for the same reason; it
# is not a fast-lane concession.
FAST_MAX_NEW_TECHNIQUES = 0
# Two sizes: a hat in adult and child. Grading multiplies every check in the chain by the
# number of sizes, which is precisely the cost the fast lane exists not to pay.
FAST_MAX_SIZES = 2

# What "premium" and "major" mean, positively. Flagship is never merely "not fast": a product
# that failed the fast bar for being awkward has not thereby earned authority.
FLAGSHIP_MIN_MAKE_LANE = "MEDIUM"
# Three patterns is the smallest set that holds together as a collection rather than reading
# as two patterns sold at once.
FLAGSHIP_MIN_PATTERNS = 3
# Depth, where depth is measurable: a flagship in a pod whose buyers are a range of bodies
# owes that range. Elsewhere depth is content rather than a count, and is not faked with one.
FLAGSHIP_MIN_SIZES = 2

# The floors, as shares of making capacity. Neither is a target; both are the point below
# which the company has stopped doing one of the two things it is for.
FLAGSHIP_FLOOR = 0.30
FAST_FLOOR = 0.30
DEFAULT_SPLIT: dict[str, float] = {FAST: 0.60, FLAGSHIP: 0.40}
MIX_IS_OF = "making capacity, never a count of products"

# Core QA has to be stable before two queues are worth running: two queues with an unstable
# chain is two ways to ship the same defect. Stability is demonstrated, never assumed -- an
# unread signal is not a passing one.
MIN_REGRESSION_FIXTURES = 5
MIN_CERTIFIED_RELEASES = 3

# The gates, imported rather than retyped. A second copy of this list is how "both retain all
# applicable quality gates" would quietly stop being true.
NON_NEGOTIABLE_GATES: tuple[str, ...] = tuple(
    stage for stage in CANONICAL_STAGES if stage not in CONDITIONAL_STAGES)
CONDITIONAL_GATES: tuple[str, ...] = CONDITIONAL_STAGES


class LaneRefused(ValueError):
    """A product routed to a queue it does not belong in, or released without a gate."""


@dataclass(frozen=True)
class Profile:
    """What a product is, in the terms both queues are decided on."""

    slug: str
    pod: str
    make_lane: str
    risk_class: str
    components: int = 1
    colours: int = 1
    new_techniques: int = 0
    sizes: int = 1
    pattern_count: int = 1
    closed_form: bool = False
    has_listing: bool = False


@dataclass(frozen=True)
class QaEvidence:
    """Evidence that core QA has stabilised. `None` means unread, which is not stable."""

    regression_fixtures: int | None = None
    regression_passed: bool | None = None
    certified_releases: int | None = None
    open_halting_incidents: int | None = None


@dataclass(frozen=True)
class GateRun:
    """A gate that actually ran, and what it said. Absent is not passing."""

    stage: str
    passed: bool


def _check_pod(pod: str) -> None:
    if pod not in POD_KEYS:
        raise LaneRefused(
            f"{pod!r} is not a pod: {list(POD_KEYS)}. A product whose pod is invented is a "
            f"product routed by whoever typed it")


def qa_stable(evidence: QaEvidence) -> dict:
    """Whether the two queues may open at all, from evidence rather than from a flag.

    The requirement opens with "after core QA stabilizes", and the tempting implementation
    reads a boolean somebody set. The failure that implementation has is the one this build
    keeps meeting: a verdict computed from the absence of bad news passes a chain that was
    never asked. So every signal is read positively, and an unread signal is its own refusal.
    """
    reasons: list[str] = []

    if evidence.regression_passed is None:
        reasons.append("the regression suite has not been run: unmeasured is not passing")
    elif not evidence.regression_passed:
        reasons.append("the regression suite is failing, so the chain is still moving under "
                       "the queues that would be built on it")

    if evidence.regression_fixtures is None:
        reasons.append("the regression corpus has not been counted")
    elif evidence.regression_fixtures < MIN_REGRESSION_FIXTURES:
        reasons.append(
            f"{evidence.regression_fixtures} regression fixture(s) against a floor of "
            f"{MIN_REGRESSION_FIXTURES}. A suite that has caught almost nothing is not "
            f"evidence of a chain that stopped breaking; it is evidence of a short suite")

    if evidence.certified_releases is None:
        reasons.append("no count of certified releases: the chain's end-to-end record is "
                       "unread, and an unrun chain looks exactly like a clean one")
    elif evidence.certified_releases < MIN_CERTIFIED_RELEASES:
        reasons.append(
            f"{evidence.certified_releases} certified release(s) against a floor of "
            f"{MIN_CERTIFIED_RELEASES}: the chain has not yet been asked enough times to "
            f"know whether it is steady")

    if evidence.open_halting_incidents is None:
        reasons.append("the incident record has not been read")
    elif evidence.open_halting_incidents:
        reasons.append(
            f"{evidence.open_halting_incidents} unresolved incident(s) halting publication. "
            f"Splitting production while the chain is halting is two ways to ship it")

    return {
        "stable": not reasons,
        "reasons": reasons,
        "floors": {"regression_fixtures": MIN_REGRESSION_FIXTURES,
                   "certified_releases": MIN_CERTIFIED_RELEASES},
        "note": ("two queues may open" if not reasons else
                 "one queue until core QA is stable, and that queue runs the full gate list "
                 "-- which every queue here does anyway"),
    }


@lru_cache(maxsize=1)
def _regression_state() -> tuple[int, bool | None]:
    """How many fixtures there are and whether they still all fail as they should.

    Cached because the corpus is a build-time artifact and running it compiles every
    captured defect. Without this, an HTTP request for the lane rules re-runs the whole
    regression suite, which is a strange amount of work for a page describing two queues.
    """
    from ..gates import regression

    fixtures = regression.load_all()
    if not fixtures:
        return 0, None
    run = regression.run()
    # `RegressionRun.ok` is true for a run that checked nothing, which is the same defect
    # this module is guarding against elsewhere: a verdict from the absence of failures
    # passes a suite that never ran. The count decides whether there is a verdict at all.
    return len(fixtures), (run.ok if run.checked else None)


def observe(db) -> QaEvidence:
    """Fill the evidence from the records that hold it, leaving unread signals unread."""
    from sqlalchemy import func, select

    from ..core.models import Incident, PatternVersion

    certified = db.execute(
        select(func.count()).select_from(PatternVersion)
        .where(PatternVersion.certified.is_(True))).scalar_one()
    halting = db.execute(
        select(func.count()).select_from(Incident)
        .where(Incident.halts_publication.is_(True))
        .where(Incident.resolved.is_(False))).scalar_one()
    fixtures, passed = _regression_state()
    return QaEvidence(
        regression_fixtures=fixtures,
        regression_passed=passed,
        certified_releases=int(certified),
        open_halting_incidents=int(halting),
    )


def _fast_reasons(p: Profile) -> list[str]:
    reasons: list[str] = []
    if p.pod not in FAST_PODS:
        reasons.append(
            f"{p.pod} is not a fast-lane pod ({list(FAST_PODS)}). This is the half that "
            f"cannot be argued down under a deadline: a garment or a blanket is flagship "
            f"work at any component count somebody types")
    if p.make_lane not in LANE_ORDER:
        reasons.append(f"{p.make_lane!r} is not a make lane: {list(LANE_ORDER)}")
    elif LANE_ORDER.index(p.make_lane) > LANE_ORDER.index(FAST_MAKE_CEILING):
        reasons.append(
            f"a {p.make_lane} build is not fast work; the lane carries "
            f"{FAST_MAKE_CEILING} and below")
    if p.risk_class not in FAST_RISK_CLASSES:
        reasons.append(
            f"risk class {p.risk_class} is not one the compiler verifies completely, and "
            f"this queue's whole argument is that there is less to check rather than that "
            f"checking is skipped")
    if p.pattern_count > 1:
        reasons.append(f"{p.pattern_count} patterns: a set is a collection, and a "
                       f"collection's value is authority rather than speed")
    if p.components > FAST_MAX_COMPONENTS:
        reasons.append(f"{p.components} components against a ceiling of "
                       f"{FAST_MAX_COMPONENTS}: past this the work is assembly")
    if p.colours > FAST_MAX_COLOURS:
        reasons.append(f"{p.colours} colours against a ceiling of {FAST_MAX_COLOURS}: colour "
                       f"changes are the commonest source of a chart that disagrees with its "
                       f"written instructions")
    if p.new_techniques > FAST_MAX_NEW_TECHNIQUES:
        reasons.append(f"{p.new_techniques} technique(s) the catalogue has never used: a new "
                       f"technique needs a physical sample, and a sample cannot be hurried")
    if p.sizes > FAST_MAX_SIZES:
        reasons.append(f"{p.sizes} sizes against a ceiling of {FAST_MAX_SIZES}: grading "
                       f"multiplies every check in the chain by the number of sizes")
    return reasons


def _flagship_reasons(p: Profile) -> list[str]:
    """Why this is *not* flagship. Substance is proved, never inferred from failing fast."""
    reasons: list[str] = []
    collection = p.pattern_count >= FLAGSHIP_MIN_PATTERNS
    if p.make_lane not in LANE_ORDER:
        reasons.append(f"{p.make_lane!r} is not a make lane: {list(LANE_ORDER)}")
        return reasons
    heavy = LANE_ORDER.index(p.make_lane) >= LANE_ORDER.index(FLAGSHIP_MIN_MAKE_LANE)

    if p.pod not in FLAGSHIP_PODS and not collection:
        reasons.append(
            f"{p.pod} is not a flagship pod ({list(FLAGSHIP_PODS)}) and this is a single "
            f"pattern. Authority comes from the premium forms or from a set that holds "
            f"together, and a hard coaster is neither")
    if not heavy and not collection:
        reasons.append(
            f"a {p.make_lane} single pattern is not a premium product. Flagship is never "
            f"merely 'not fast': a product that failed the fast bar for being awkward has "
            f"not thereby earned authority")
    if p.pod in SIZED_PODS and p.sizes < FLAGSHIP_MIN_SIZES:
        reasons.append(
            f"a flagship {p.pod} product in {p.sizes} size: this pod's buyers are a range of "
            f"bodies, and a premium claim over one size is a claim about somebody else's")
    if p.new_techniques > 0 and not heavy:
        reasons.append(
            f"{p.new_techniques} new technique(s) on a {p.make_lane} build: a technique "
            f"nobody here has sampled is not a short job, whatever the plan says")
    return reasons


def assign(profile: Profile, *, qa: dict) -> dict:
    """Route a product to the queue it belongs in, and say why when it belongs in neither.

    `qa` is the verdict from `qa_stable` rather than a flag, because the requirement's "after
    core QA stabilizes" is a condition about evidence and a boolean parameter is a place for
    that evidence to be lost.
    """
    _check_pod(profile.pod)
    if not isinstance(qa, dict) or "stable" not in qa:
        raise LaneRefused(
            "assign() needs the verdict from qa_stable(), not a flag: the requirement opens "
            "with 'after core QA stabilizes', and a boolean is where that evidence goes to "
            "die")

    fast = _fast_reasons(profile)
    flagship = _flagship_reasons(profile)
    gates = applicable_gates(profile)
    paced_by = ("a physical sample, which sets the wall clock whatever the queue does: a "
                f"class {profile.risk_class} product is fast in engineering only"
                if profile.risk_class in NEEDS_SAMPLE else "")

    if not qa["stable"]:
        return {
            "slug": profile.slug, "lane": None, "two_queues_open": False,
            "why": qa["reasons"],
            "fast_refusals": fast, "flagship_refusals": flagship,
            "gates": list(gates), "paced_by": paced_by,
            "note": ("one queue until core QA is stable. Nothing about the checking changes: "
                     "the single queue runs exactly the gates both queues run"),
        }

    lane = FAST if not fast else (FLAGSHIP if not flagship else None)
    if lane is None:
        note = ("neither queue. This product is not simple enough to buy learning rate and "
                "not substantial enough to buy authority, so it is paying for nothing the "
                "catalogue is short of. Make it smaller or make it matter")
    else:
        note = (f"{lane} lane: {PURPOSE[lane]}. The queue is shorter; the gate list is the "
                f"same list every product passes")

    return {
        "slug": profile.slug, "lane": lane, "two_queues_open": True,
        "purpose": PURPOSE.get(lane, ""),
        "fast_refusals": fast, "flagship_refusals": flagship,
        "gates": list(gates), "paced_by": paced_by,
        "note": note,
    }


def applicable_gates(profile: Profile) -> tuple[str, ...]:
    """Every gate this product is owed, in chain order.

    Deliberately takes the product and not the lane. That is the structural form of "both
    retain all applicable quality gates": there is no argument here through which a queue
    could shorten a list, so the guarantee cannot be weakened by a caller, only by an edit
    to this signature -- which a test watches.
    """
    owed = set()
    if profile.closed_form:
        owed.add("geometry")
    if profile.has_listing:
        owed.update(("asset_truth", "policy"))
    return tuple(stage for stage in CANONICAL_STAGES
                 if stage not in CONDITIONAL_GATES or stage in owed)


def check_release(profile: Profile, *, runs: tuple[GateRun, ...], lane: str) -> dict:
    """Refuse a release that skipped or failed a gate, in either queue, by name.

    Takes gate *runs* rather than a set of names that passed. The difference is the defect
    this build keeps finding: a verdict computed from the absence of failures will always
    pass a chain that never ran. A stage nobody reached is absent, and absent is not passing.
    """
    if lane not in LANES:
        raise LaneRefused(f"{lane!r} is not a production lane: {list(LANES)}")
    unknown = sorted({r.stage for r in runs} - set(CANONICAL_STAGES))
    if unknown:
        raise LaneRefused(
            f"{unknown} are not stages of the release chain: {list(CANONICAL_STAGES)}")

    required = applicable_gates(profile)
    by_stage = {r.stage: r for r in runs}
    missing = [stage for stage in required if stage not in by_stage]
    failed = [stage for stage in required if stage in by_stage and not by_stage[stage].passed]
    if missing or failed:
        detail = []
        if missing:
            detail.append(f"never ran {missing}")
        if failed:
            detail.append(f"failed {failed}")
        raise LaneRefused(
            f"{profile.slug} was released down the {lane} lane having {' and '.join(detail)}. "
            f"The lane shortens the queue and never the gate list: both queues pass exactly "
            f"what the chain would run for this product")
    return {"slug": profile.slug, "lane": lane, "gates": list(required), "ok": True,
            "note": "every gate this product was owed ran, and passed"}


def check_mix(shares: dict[str, float]) -> dict:
    """Refuse a capacity split that starves either purpose, with the number it starved."""
    unknown = sorted(set(shares) - set(LANES))
    if unknown:
        raise LaneRefused(f"{unknown} are not production lanes: {list(LANES)}")
    total = sum(shares.get(lane, 0.0) for lane in LANES)
    reasons: list[str] = []
    if abs(total - 1.0) > 1e-9:
        reasons.append(f"the shares total {total:.2f} rather than 1.00, so this is not a "
                       f"split of capacity")
    fast, flagship = shares.get(FAST, 0.0), shares.get(FLAGSHIP, 0.0)
    if flagship < FLAGSHIP_FLOOR:
        reasons.append(
            f"flagship at {flagship:.0%} against a floor of {FLAGSHIP_FLOOR:.0%}. This is "
            f"the slide: every week the fast product is the better use of the week, and a "
            f"year of defensible weeks is a catalogue with no authority and no order value")
    if fast < FAST_FLOOR:
        reasons.append(
            f"fast at {fast:.0%} against a floor of {FAST_FLOOR:.0%}. A catalogue of four "
            f"magnificent blankets has had four chances to learn what sells, and holds four "
            f"search phrases")
    return {"shares": {lane: round(shares.get(lane, 0.0), 4) for lane in LANES},
            "ok": not reasons, "reasons": reasons,
            "floors": {FAST: FAST_FLOOR, FLAGSHIP: FLAGSHIP_FLOOR},
            "of": MIX_IS_OF}


def allocate(capacity_units: float, shares: dict[str, float] | None = None) -> dict:
    """Split making capacity between the queues, refusing a split that starves one."""
    if capacity_units < 0:
        raise LaneRefused("capacity cannot be negative")
    shares = dict(shares or DEFAULT_SPLIT)
    verdict = check_mix(shares)
    if not verdict["ok"]:
        raise LaneRefused("; ".join(verdict["reasons"]))
    return {
        "capacity_units": capacity_units,
        "units": {lane: round(capacity_units * shares[lane], 4) for lane in LANES},
        "shares": verdict["shares"],
        "of": MIX_IS_OF,
        "note": ("capacity, not products. A flagship costs several fast products' worth of "
                 "engineering, so this split makes many more fast products than flagships -- "
                 "which is the point of both floors"),
    }


def balance(assignments: list[dict]) -> dict:
    """What the queues are actually doing, from assignments already made.

    Counts, and says so: a count of products is not the capacity share the floors are about,
    and reporting one as the other is how a floor is satisfied with an ornament.
    """
    counts = {lane: 0 for lane in LANES}
    counts["neither"] = 0
    for card in assignments:
        lane = card.get("lane")
        counts[lane if lane in LANES else "neither"] += 1
    placed = counts[FAST] + counts[FLAGSHIP]
    return {
        "counts": counts,
        "placed": placed,
        "note": ("product counts, which are not the capacity shares the floors govern. A "
                 "flagship costs several fast products, so a count that looks balanced is a "
                 "capacity split that is not"
                 if placed else
                 "nothing has been routed yet, and an empty catalogue starves both purposes "
                 "equally"),
    }


def state() -> dict:
    """Both queues, their purposes, their bars and the list neither may shorten."""
    return {
        "lanes": list(LANES),
        "purpose": dict(PURPOSE),
        "fast": {"pods": list(FAST_PODS), "make_lane_ceiling": FAST_MAKE_CEILING,
                 "risk_classes": list(FAST_RISK_CLASSES),
                 "max_components": FAST_MAX_COMPONENTS, "max_colours": FAST_MAX_COLOURS,
                 "max_new_techniques": FAST_MAX_NEW_TECHNIQUES, "max_sizes": FAST_MAX_SIZES,
                 "risk_classes_needing_a_sample": [c for c in FAST_RISK_CLASSES
                                                   if c in NEEDS_SAMPLE]},
        "flagship": {"pods": list(FLAGSHIP_PODS),
                     "min_make_lane": FLAGSHIP_MIN_MAKE_LANE,
                     "min_patterns_for_a_collection": FLAGSHIP_MIN_PATTERNS,
                     "min_sizes_in_sized_pods": FLAGSHIP_MIN_SIZES,
                     "sized_pods": list(SIZED_PODS)},
        "gates": list(NON_NEGOTIABLE_GATES),
        "conditional_gates": list(CONDITIONAL_GATES),
        "mix": {"default": dict(DEFAULT_SPLIT), "floors": {FAST: FAST_FLOOR,
                                                           FLAGSHIP: FLAGSHIP_FLOOR},
                "of": MIX_IS_OF},
        "qa_floors": {"regression_fixtures": MIN_REGRESSION_FIXTURES,
                      "certified_releases": MIN_CERTIFIED_RELEASES},
        "note": ("Two queues with different jobs and one gate list. The fast lane buys "
                 "learning rate and search coverage; the flagship lane buys authority, depth "
                 "and order value; the floors exist because the first eats the second one "
                 "defensible week at a time (#5)."),
    }
