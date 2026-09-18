"""Working backward from when the customer needs the finished object.

Requirements 283, 284, 285, 310, 311 and 297. The owner flagged this one as non-negotiable and
the reason is in the arithmetic: a crochet pattern is not the product the customer wants. The
product they want is a finished cardigan, on a person, on Christmas morning -- and between the
listing and that morning sit the marketplace's indexing lag, the buyer's own planning, and
forty to sixty hours of somebody's hands.

A shop that launches its Christmas blanket on December 1st has not launched a Christmas
blanket. It has launched a blanket nobody can finish, at the exact moment the search term
peaks, and the listing's own conversion data will report that Christmas blankets do not sell.

So every seasonal product carries two dates that are computed rather than chosen:

    latest effective launch = event
                            - customer completion buffer
                            - estimated make time
                            - purchase and planning buffer
                            - marketplace discovery and ramp

    preferred launch        = latest effective launch
                            - creative iteration
                            - advertising learning window

Everything in that chain is an assumption today, and this module says so. Each plan carries the
assumptions it used and whether each was *measured* or *assumed*, because a launch date derived
from six guesses and a launch date derived from six months of sales data are different objects
and must not look alike on a dashboard. `Assumptions.measured()` is how a figure graduates,
and nothing graduates itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Complexity lanes (#285)

QUICK = "QUICK"          # hours, or a day or two
SHORT = "SHORT"          # several days
MEDIUM = "MEDIUM"        # roughly one to two weeks
LONG = "LONG"            # multi-week
FLAGSHIP = "FLAGSHIP"    # potentially many weeks

LANES: tuple[str, ...] = (QUICK, SHORT, MEDIUM, LONG, FLAGSHIP)

# Upper bound of customer make-hours for each lane. Derived from the make-time evidence
# already in radar/market.py: small decor 1-4h, baby blanket 3-20h, throw 30-40h, full-size
# 60h+. The boundaries are assumptions and are labelled as such in every plan.
LANE_MAX_HOURS: dict[str, float] = {
    QUICK: 6.0,
    SHORT: 20.0,
    MEDIUM: 45.0,
    LONG: 90.0,
    FLAGSHIP: float("inf"),
}


def classify(make_hours: float) -> str:
    """Which lane a product's customer make-time puts it in."""
    if make_hours < 0:
        raise ValueError("make hours cannot be negative")
    for lane in LANES:
        if make_hours <= LANE_MAX_HOURS[lane]:
            return lane
    return FLAGSHIP


# ---------------------------------------------------------------------------
# Assumptions
#
# Every figure below is a guess with a reason. They are gathered in one place, carried in the
# plan, and each is tagged measured or assumed, because the difference is the difference
# between a schedule and a hope.


@dataclass(frozen=True)
class Assumptions:
    """The inputs to the backward chain, and the evidence behind each.

    `sources` maps a field name to "measured" or "assumed". A field with no entry is assumed:
    the default is the cautious one, so a figure cannot become measured by being forgotten.
    """

    # How much a real person actually crochets in a week. Not how much they intend to.
    hours_per_week: float = 7.0
    # Multiplier on stated make-time by the skill the pattern is written for. A beginner
    # working their first cardigan is not slow; they are learning, and the estimate has to be
    # the one that leaves them with a finished object.
    skill_factor: dict[str, float] = field(default_factory=lambda: {
        "beginner": 1.6, "adventurous_beginner": 1.3, "intermediate": 1.0, "experienced": 0.8,
    })
    # The object has to exist *before* the event, not on it. Gift-giving needs it earlier.
    completion_buffer_days: int = 10
    # Buyers do not purchase the moment they first see a listing, and the bigger the project
    # the longer they think about it.
    planning_buffer_days: dict[str, int] = field(default_factory=lambda: {
        QUICK: 3, SHORT: 5, MEDIUM: 7, LONG: 14, FLAGSHIP: 21,
    })
    # A new listing is not immediately findable. This is the ramp before it carries its own
    # traffic, and it is the buffer most seasonal plans forget entirely.
    marketplace_ramp_days: int = 21
    # Time to see the thumbnail is wrong and fix it, before the season rather than during.
    creative_iteration_days: int = 10
    # Paid acquisition needs data before the peak (#294).
    ad_learning_days: int = 14
    # Ours, not the customer's: a tester has to crochet the thing before it ships.
    tester_qa_days: int = 21

    # Make-time estimation, derived from the twin rather than guessed per product. An average
    # crocheter works several hundred stitches an hour on plain fabric; colourwork is slower
    # because of yarn management rather than because the stitches are harder.
    stitches_per_hour: float = 700.0
    # Weaving ends, blocking and seaming. Paid once per piece, and it is the part every
    # optimistic estimate forgets.
    finishing_hours_per_component: float = 0.6
    # Each colour change costs a moment now and an end to weave in later.
    hours_per_colour_change: float = 0.012

    sources: dict[str, str] = field(default_factory=dict)

    def source_of(self, name: str) -> str:
        return self.sources.get(name, "assumed")

    def measured(self, **values) -> "Assumptions":
        """Replace figures with observed ones, marking them measured.

        The only route from assumed to measured, so a number cannot graduate by being
        overwritten in place. #284 asks for exactly this: recompute as observed buyer
        behaviour improves the estimates.
        """
        unknown = [k for k in values if not hasattr(self, k)]
        if unknown:
            raise ValueError(f"not assumptions: {sorted(unknown)}")
        return replace(self, **values, sources={**self.sources,
                                                **{k: "measured" for k in values}})

    def evidence(self) -> dict[str, str]:
        return {name: self.source_of(name) for name in (
            "hours_per_week", "skill_factor", "completion_buffer_days",
            "planning_buffer_days", "marketplace_ramp_days", "creative_iteration_days",
            "ad_learning_days", "tester_qa_days", "stitches_per_hour",
            "finishing_hours_per_component", "hours_per_colour_change")}

    @property
    def fully_measured(self) -> bool:
        return all(v == "measured" for v in self.evidence().values())


DEFAULT = Assumptions()


# ---------------------------------------------------------------------------
# The compiler (#284)

ON_TRACK = "on_track"
AT_RISK = "at_risk"
PAST_PREFERRED = "past_preferred"
MISSED = "missed"

# What to do about a window that cannot be met (#297). Shipping anyway is not on the list.
PIVOT_EVERGREEN = "pivot_to_evergreen"
SIMPLIFY = "simplify_to_a_quick_make"
HOLD = "hold_for_next_cycle"
LAUNCH = "launch"


@dataclass(frozen=True)
class LaunchPlan:
    """When a seasonal product must be live, and how much of that is evidence."""

    event: str
    event_date: date
    lane: str
    make_hours: float
    skill: str
    effective_make_days: int
    completion_buffer_days: int
    planning_buffer_days: int
    marketplace_ramp_days: int
    latest_effective_launch: date
    preferred_launch: date
    work_must_start_by: date
    assumptions: Assumptions

    def days_to_preferred(self, today: date) -> int:
        return (self.preferred_launch - today).days

    def days_to_latest(self, today: date) -> int:
        return (self.latest_effective_launch - today).days

    def status(self, today: date) -> str:
        """#311's sentinel, in four words rather than a traffic light.

        `at_risk` is the interesting one: it is the period where the preferred date has gone
        but the latest has not, which is when reallocating agents still changes the outcome.
        """
        if today > self.latest_effective_launch:
            return MISSED
        if today > self.preferred_launch:
            return AT_RISK if (self.latest_effective_launch - today).days <= 21 \
                else PAST_PREFERRED
        return ON_TRACK

    def recommendation(self, today: date) -> tuple[str, str]:
        """What to do, and why. #297: never launch under a premise that is no longer true.

        A finished product that missed its window is not a reason to launch it anyway. The
        customer cannot make it in time, the listing says they can, and the shop learns the
        wrong lesson from the conversion data it gets back.
        """
        state = self.status(today)
        if state != MISSED:
            return LAUNCH, f"{self.days_to_latest(today)} days of runway remain"
        if self.lane in (QUICK, SHORT):
            return (PIVOT_EVERGREEN,
                    "too late for a customer to buy, receive and finish this before the "
                    "event; it is small enough to stand on its own without the seasonal "
                    "premise, so re-merchandise it as evergreen")
        if self.lane in (LONG, FLAGSHIP):
            return (SIMPLIFY,
                    "a customer cannot finish this before the event. A legitimate quick-make "
                    "derivative can still reach them in time; the full product holds for the "
                    "next cycle rather than shipping a promise it cannot keep")
        return (HOLD,
                "the window has closed. Holding for the next cycle keeps the seasonal claim "
                "true, and the work is not lost")

    def to_dict(self) -> dict:
        return {
            "event": self.event, "event_date": self.event_date.isoformat(),
            "lane": self.lane, "make_hours": self.make_hours, "skill": self.skill,
            "effective_make_days": self.effective_make_days,
            "buffers": {
                "customer_completion": self.completion_buffer_days,
                "purchase_and_planning": self.planning_buffer_days,
                "marketplace_ramp": self.marketplace_ramp_days,
            },
            "latest_effective_launch": self.latest_effective_launch.isoformat(),
            "preferred_launch": self.preferred_launch.isoformat(),
            "work_must_start_by": self.work_must_start_by.isoformat(),
            "assumption_evidence": self.assumptions.evidence(),
            "fully_measured": self.assumptions.fully_measured,
        }


def effective_make_days(make_hours: float, skill: str,
                        assumptions: Assumptions = DEFAULT) -> int:
    """Calendar days a real customer needs, not hours divided by an ideal week."""
    factor = assumptions.skill_factor.get(skill)
    if factor is None:
        raise ValueError(f"unknown skill {skill!r}: "
                         f"one of {sorted(assumptions.skill_factor)}")
    hours = make_hours * factor
    weekly = assumptions.hours_per_week
    if weekly <= 0:
        raise ValueError("hours per week must be positive")
    return max(1, int(round(hours / weekly * 7)))


def compile_launch(event: str, event_date: date, *, make_hours: float,
                   skill: str = "intermediate",
                   assumptions: Assumptions = DEFAULT) -> LaunchPlan:
    """The backward chain of #284, with every term named rather than folded into a constant."""
    lane = classify(make_hours)
    make_days = effective_make_days(make_hours, skill, assumptions)
    planning = assumptions.planning_buffer_days[lane]

    latest = (event_date
              - timedelta(days=assumptions.completion_buffer_days)
              - timedelta(days=make_days)
              - timedelta(days=planning)
              - timedelta(days=assumptions.marketplace_ramp_days))
    preferred = latest - timedelta(days=assumptions.creative_iteration_days
                                   + assumptions.ad_learning_days)
    # Ours: a tester has to crochet the sample before any of the above can happen.
    start_by = preferred - timedelta(days=assumptions.tester_qa_days)

    return LaunchPlan(
        event=event, event_date=event_date, lane=lane, make_hours=make_hours, skill=skill,
        effective_make_days=make_days,
        completion_buffer_days=assumptions.completion_buffer_days,
        planning_buffer_days=planning,
        marketplace_ramp_days=assumptions.marketplace_ramp_days,
        latest_effective_launch=latest, preferred_launch=preferred,
        work_must_start_by=start_by, assumptions=assumptions)


def plan_for_seasonal_event(event, *, make_hours: float, skill: str = "intermediate",
                            assumptions: Assumptions = DEFAULT) -> LaunchPlan:
    """Compile against a `radar.market.SeasonalEvent`, reusing the calendar that exists."""
    return compile_launch(event.name, event.event_date, make_hours=make_hours, skill=skill,
                          assumptions=assumptions)


# ---------------------------------------------------------------------------
# Make-time estimation (#283)
#
# Derived from the digital twin, not attached to a product by hand. The company already
# refuses to let a human type a finished size; typing a make time would be the same mistake in
# the field that decides whether a customer gets a finished object by Christmas.


@dataclass(frozen=True)
class MakeTimeEstimate:
    hours: float
    stitches: int
    colour_changes: int
    components: int
    lane: str
    basis: str
    evidence: str

    def to_dict(self) -> dict:
        return {"hours": self.hours, "stitches": self.stitches,
                "colour_changes": self.colour_changes, "components": self.components,
                "lane": self.lane, "basis": self.basis, "evidence": self.evidence}


def colour_changes(twin) -> int:
    """How many times the maker swaps yarn, read off the twin's own cells.

    Counted in working order within each row, because that is the order a person crochets in.
    Comparing a whole grid would count a two-colour stripe sequence as one change per cell.
    """
    total = 0
    rows = sorted({c.row for c in twin.cells})
    previous: str | None = None
    for row in rows:
        cells = sorted((c for c in twin.cells if c.row == row), key=lambda c: c.position)
        for cell in cells:
            if cell.color and cell.color != previous:
                if previous is not None:
                    total += 1
                previous = cell.color
    return total


def estimate_make_hours(twins, assumptions: Assumptions = DEFAULT) -> MakeTimeEstimate:
    """Estimate customer make-time from the twins of a pattern's components."""
    twins = list(twins)
    if not twins:
        raise ValueError("a pattern with no components has no make time")
    stitches = sum(t.stitch_total for t in twins)
    changes = sum(colour_changes(t) for t in twins)
    if assumptions.stitches_per_hour <= 0:
        raise ValueError("stitches per hour must be positive")

    hours = (stitches / assumptions.stitches_per_hour
             + changes * assumptions.hours_per_colour_change
             + len(twins) * assumptions.finishing_hours_per_component)
    hours = round(hours, 2)
    return MakeTimeEstimate(
        hours=hours, stitches=stitches, colour_changes=changes, components=len(twins),
        lane=classify(hours), basis="derived from the digital twin",
        evidence=assumptions.source_of("stitches_per_hour"))


def calibrate_from_samples(db, assumptions: Assumptions = DEFAULT) -> tuple[Assumptions, dict]:
    """Replace the assumed stitch rate with one a real person's hands produced.

    The physical test intake already asks testers for hours, and the twin knows the stitch
    count, so the rate is a division that nobody has performed yet. Returns the assumptions
    unchanged when there is nothing to calibrate from -- which is the honest outcome today,
    and the report says so rather than returning a number that looks measured.
    """
    from sqlalchemy import select

    from ..core.models import PatternVersion, PhysicalTest, Product

    samples: list[dict] = []
    with db.session() as s:
        tests = list(s.scalars(select(PhysicalTest).where(
            PhysicalTest.passed == True)))  # noqa: E712
        for test in tests:
            hours = (test.measured or {}).get("hours")
            if not hours:
                continue
            product = s.scalar(select(Product).where(Product.slug == test.product_slug))
            if product is None:
                continue
            version = s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id,
                PatternVersion.version == test.version))
            if version is None or not version.cir_json:
                continue
            samples.append({"slug": test.product_slug, "version": test.version,
                            "hours": float(hours), "cir": version.cir_json})

    rates: list[float] = []
    for sample in samples:
        try:
            from ..cir.compiler import compile_cir
            from ..cir.model import CIR
            from ..cir.twin import build_twin

            cir = CIR.from_dict(sample["cir"])
            compiled = compile_cir(cir)
            twins = [build_twin(cir, compiled, component=c.name) for c in cir.components]
            stitches = sum(t.stitch_total for t in twins)
        except Exception:  # noqa: BLE001 - one unreadable sample must not stop calibration
            continue
        if stitches and sample["hours"] > 0:
            rates.append(stitches / sample["hours"])

    report = {
        "samples_with_hours": len(samples),
        "samples_usable": len(rates),
        "assumed_rate": assumptions.stitches_per_hour,
        "measured_rate": round(sum(rates) / len(rates), 1) if rates else None,
    }
    if not rates:
        report["note"] = ("no completed physical test has reported hours, so the stitch rate "
                          "remains an assumption and every seasonal date derived from it is "
                          "labelled assumed")
        return assumptions, report
    return assumptions.measured(stitches_per_hour=report["measured_rate"]), report


def runway_order(plans: list[LaunchPlan]) -> list[LaunchPlan]:
    """#285: the longest makes get the earliest runway.

    Falls out of the arithmetic rather than being imposed -- a flagship's make time pushes its
    latest launch earlier by construction -- which is why this sorts on the computed date
    instead of on the lane.
    """
    return sorted(plans, key=lambda p: (p.preferred_launch, p.latest_effective_launch))


def sentinel(plans: list[LaunchPlan], today: date) -> dict:
    """#311: what is at risk, what has been missed, and what to do about each."""
    rows = []
    for plan in runway_order(plans):
        action, why = plan.recommendation(today)
        rows.append({
            **plan.to_dict(),
            "status": plan.status(today),
            "days_to_preferred": plan.days_to_preferred(today),
            "days_to_latest": plan.days_to_latest(today),
            "recommendation": action, "because": why,
        })
    return {
        "today": today.isoformat(),
        "counts": {state: sum(1 for r in rows if r["status"] == state)
                   for state in (ON_TRACK, PAST_PREFERRED, AT_RISK, MISSED)},
        "plans": rows,
        "note": ("Every date here is computed backward from when a customer needs the "
                 "finished object. Figures marked 'assumed' have not yet been measured "
                 "against real buyer behaviour."),
    }


def catalogue_plans(db, today: date | None = None,
                    assumptions: Assumptions | None = None) -> dict:
    """Every certified pattern against every seasonal event, as a war room (#296, #311).

    Computed from what the warehouse actually holds rather than from a plan: the make time
    comes from each product's own twin, and the launch dates fall out of the subtraction. A
    product with no certified pattern is not scheduled, because there is nothing to schedule.
    """
    from sqlalchemy import select

    from ..cir.compiler import compile_cir
    from ..cir.model import CIR
    from ..cir.twin import build_twin
    from ..core.models import PatternVersion, Product
    from ..radar.market import SEASONAL_EVENTS

    today = today or date.today()
    base, calibration = calibrate_from_samples(db, assumptions or DEFAULT)

    products: list[dict] = []
    with db.session() as s:
        versions = list(s.scalars(select(PatternVersion).where(
            PatternVersion.certified == True)))  # noqa: E712
        by_product = {p.id: p for p in s.scalars(select(Product))}
        for version in versions:
            product = by_product.get(version.product_id)
            if product is None or not version.cir_json:
                continue
            try:
                cir = CIR.from_dict(version.cir_json)
                compiled = compile_cir(cir)
                twins = [build_twin(cir, compiled, component=c.name) for c in cir.components]
                estimate = estimate_make_hours(twins, base)
            except Exception as e:  # noqa: BLE001 - one bad pattern must not empty the room
                products.append({"slug": product.slug, "error": f"{type(e).__name__}: {e}"})
                continue
            products.append({"slug": product.slug, "version": version.version,
                             "estimate": estimate.to_dict()})

    rows: list[dict] = []
    for entry in products:
        if "estimate" not in entry:
            continue
        for event in SEASONAL_EVENTS:
            if event.event_date < today:
                continue
            plan = compile_launch(event.name, event.event_date,
                                  make_hours=entry["estimate"]["hours"], assumptions=base)
            action, why = plan.recommendation(today)
            rows.append({"slug": entry["slug"], **plan.to_dict(),
                         "status": plan.status(today),
                         "days_to_preferred": plan.days_to_preferred(today),
                         "days_to_latest": plan.days_to_latest(today),
                         "recommendation": action, "because": why})

    rows.sort(key=lambda r: (r["event_date"], r["latest_effective_launch"]))
    return {
        "today": today.isoformat(),
        "calibration": calibration,
        "products_scheduled": sum(1 for p in products if "estimate" in p),
        "products_unreadable": [p for p in products if "error" in p],
        "counts": {state: sum(1 for r in rows if r["status"] == state)
                   for state in (ON_TRACK, PAST_PREFERRED, AT_RISK, MISSED)},
        "at_risk_or_missed": [r for r in rows if r["status"] in (AT_RISK, MISSED)][:40],
        "plans": rows[:200],
        "note": ("Dates are computed backward from when a customer needs the finished "
                 "object. Every figure marked 'assumed' has not yet been measured against a "
                 "real maker or a real buyer."),
    }
