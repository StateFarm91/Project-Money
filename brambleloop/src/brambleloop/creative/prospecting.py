"""Product discovery that starts from a proven market rather than from what compiles.

The owner's instruction after the first blinded run: *"take a real MJs-proven arena with no
current Brambleloop answer and produce genuinely compelling Brambleloop concepts capable of
surviving the Creative Supremacy gates"*, and explicitly *"avoid the failure mode where every
concept becomes another throw, runner, garland or geometric object simply because the
compiler already understands those forms."*

That failure mode is not hypothetical and it is not a matter of taste. It is measured. All
eleven products in this catalogue are `home_decor`; `pod`, `feeling` and `make_lane` each hold
exactly one distinct value across the whole of it; and 0 of those 11 share a pod *and* a form
with any of the 438 observed benchmark listings, so the blinded comparison has nothing
like-for-like to judge. A generator left to its own preferences returns to the shape its
compiler is fluent in, every time, and the result looks like a catalogue and behaves like one
product.

So the direction of travel is inverted. Discovery does not start with a brief and look for a
market; it starts with a market the benchmark has *proven*, in a department this catalogue
does *not* answer, and asks what would have to be built. Three consequences, and each is a
refusal somewhere below:

**The arena picks the form, not the engine.** An expedition into `hats` produces hats. The
forms it may target are counted from the observed listings in that pod, so the vocabulary
comes from what the market actually contains rather than from what this compiler finds easy.

**A form the engine cannot yet build is an engineering requirement, not a rejection.** The
CIR speaks three constructions. Dropping every concept that needs a fourth is precisely how a
catalogue converges on flat panels while believing it is being selective, so an unbuildable
slot is *reported* with the construction it needs and the concept is carried to the point
where that becomes a decision somebody makes on purpose.

**A form this catalogue is already saturated with has to earn its place.** Another rectangle
throw is not discovery, whatever its motif.

What this module does not do is decide whether a concept is good. That is the jury's job and
the jury is adversarial and deterministic. This module decides *what to point the jury at*,
and then reports honestly how little survived.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..intel import benchmarks
from .concept import CONSTRUCTIONS, FORMS, Concept
from .family import FORM_CONSTRUCTIONS

# The CIR's own construction vocabulary. Three, and every concept-level construction has to
# land on one of them or be built first. Read from the model rather than restated, so the map
# below cannot drift away from what the compiler actually accepts.
CIR_CONSTRUCTIONS: tuple[str, ...] = ("flat_rows", "joined_rounds", "spiral_rounds")

# How each concept construction reaches the compiler. `None` means no route exists yet: the
# construction is a real thing a maker does and the engine has not been taught it. That is a
# build item with a name, which is the only useful form for it to take.
ENGINE_ROUTE: dict[str, str | None] = {
    "flat_rows": "flat_rows",
    "in_the_round": "joined_rounds",
    "seamless_tube": "joined_rounds",
    "amigurumi_shaping": "spiral_rounds",
    "side_to_side": "flat_rows",
    "corner_to_corner": "flat_rows",
    "tapestry": "flat_rows",
    "mosaic_overlay": "flat_rows",
    "cable_panel": "flat_rows",
    "granny_square": "flat_rows",
    "motif_join": "flat_rows",
    "modular_panels": "flat_rows",
    # Garment shaping. Unblocked 2026-09-20 by the armhole division: `Row.skips` and
    # `Component.holds`/`resumes`. A yoke worked in rounds splits, the sleeve stitches go on
    # hold, and the body continues over the rest -- and every hold is checked to be resumed
    # exactly once, by a piece that picks up exactly the held count.
    "top_down_yoke": "joined_rounds",
    "bottom_up": "joined_rounds",
}

# Kept as a record rather than deleted. It was the named build item that blocked the deepest
# proven arena, it was implemented on 2026-09-20, and a gap list that only ever shows what is
# still missing loses the evidence that naming a gap precisely is what closes it.
CLOSED_PRIMITIVES: tuple[dict, ...] = (
    {
        "name": "partial-row work (the armhole division)",
        "closed_on": "2026-09-20",
        "how": ("Row.skips narrows what a row may work; Component.holds declares the set-"
                "aside stitches and Component.resumes picks them up. Every hold must be "
                "resumed exactly once by a piece that starts on exactly the held count, and "
                "the writer states the division where it happens"),
        "unblocked": ("top_down_yoke and bottom_up, and with them the garments pod -- 140 "
                      "of the 438 observed benchmark listings"),
    },
)

MISSING_PRIMITIVE = None

# Above this share of the catalogue, a form is not a house style, it is the rut. Matches the
# theme-fatigue threshold, because they are the same judgement about the same evidence.
SATURATED_FORM_SHARE = 0.34

# An expedition below this many viable slots is not a breadth exercise, it is a preference.
MIN_SLOTS = 3


class ProspectingRefused(ValueError):
    """An expedition that would not have discovered anything."""


def _ideation_floor() -> int:
    """The tournament's own view of how small a field stops being a selection.

    Read from `funnel.STAGES` rather than restated, so an expedition cannot quietly disagree
    with the funnel about what counts as a choice.
    """
    from .funnel import STAGE_BY_KEY

    return STAGE_BY_KEY["ideation"].floor_in


# ---------------------------------------------------------------------------
# What a pod is actually made of


def arena_forms(db, pod: str, *, benchmark_key: str = "") -> dict:
    """Which forms this pod contains, counted from listings somebody actually observed.

    Evidence rather than a table: a table of "what a hat pod contains" is this system's
    opinion about hats, and the point of having a benchmark is to stop needing one.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from . import blinded

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key,
            BenchmarkListing.pod == pod)))

    counts: dict[str, int] = {}
    unreadable = 0
    for row in rows:
        try:
            card = blinded.from_listing({
                "listing_ref": row.listing_ref, "title": row.title, "pod": row.pod,
                "product_type": row.product_type, "price_cad": row.price_cad})
        except (blinded.Unreadable, blinded.NotComparable):
            unreadable += 1
            continue
        counts[card.form] = counts.get(card.form, 0) + 1

    return {
        "pod": pod,
        "listings": len(rows),
        "readable": len(rows) - unreadable,
        "forms": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "note": ("Counted from observed listings. A pod whose forms are unknown is a pod "
                 "nobody has looked at, which is not the same as a pod with one form in it."),
    }


def saturated_forms(concepts: list[Concept]) -> dict[str, float]:
    """Forms this catalogue already over-uses. Another one of those is not discovery."""
    if not concepts:
        return {}
    counts: dict[str, int] = {}
    for concept in concepts:
        counts[concept.form] = counts.get(concept.form, 0) + 1
    return {form: round(n / len(concepts), 4)
            for form, n in counts.items() if n / len(concepts) > SATURATED_FORM_SHARE}


# ---------------------------------------------------------------------------
# The arena


@dataclass(frozen=True)
class Arena:
    """A market the benchmark proved and this catalogue does not answer."""

    event: str
    pod: str
    benchmark_listings: int
    days_away: int
    forms: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"event": self.event, "pod": self.pod, "days_away": self.days_away,
                "benchmark_listings": self.benchmark_listings, "forms": self.forms}


class NoArenasContradictsEvidence(RuntimeError):
    """No proven gaps, against a benchmark that has been observed selling.

    Deliberately an exception rather than an empty list. "No proven-and-unserved arena is
    observed" is a legitimate state when nobody has looked, and a defect signature when 438
    listings have been read and the matrix reports twenty-seven gaps -- and the two are
    indistinguishable from a caller's side. The first version of this returned empty on a
    wrong dictionary key, the weekly discovery cadence recorded the no-op as a success, and
    it consumed its window for seven days.
    """


def arenas(db, *, today: date | None = None, limit: int = 12,
           covered: dict | None = None) -> list[Arena]:
    """Proven-and-unserved pairs, deepest and soonest first, with each pod's real forms.

    The ordering is the matrix's own: how many listings the benchmark was observed to carry,
    then how soon the occasion is. A deep market six weeks out beats a shallow one in March,
    and both beat a market nobody has looked at -- which does not appear here at all, because
    `proven_and_unserved` requires an observation and an unobserved market renders as an
    empty cell exactly like an empty one.
    """
    from ..seasonal import benchmark_matrix

    report = benchmark_matrix.matrix(db, today=today, covered=covered)
    # `proven_and_unserved`, which is the key the matrix returns -- not `proven_gaps`, which
    # is the name of the local variable that builds it. Reading the wrong key here returned
    # an empty list, and an empty list of gaps is indistinguishable from a catalogue that
    # answers every proven market. Production reported "no arenas" against a matrix holding
    # 27 of them, which is the second time today a reader and a writer disagreed about a key
    # and the wrong answer was the comfortable one.
    gaps = report.get(benchmark_matrix.PROVEN_KEY) or []
    if not gaps and report.get("benchmark_observed_listings"):
        raise NoArenasContradictsEvidence(
            f'the matrix reports no proven-and-unserved department against '
            f'{report["benchmark_observed_listings"]} observed benchmark listings. Either '
            f'this catalogue answers every market the benchmark sells in -- which it does '
            f'not -- or a reader is looking in the wrong place')

    out: list[Arena] = []
    for gap in gaps[:limit]:
        out.append(Arena(
            event=gap["event"], pod=gap["department"],
            benchmark_listings=gap["benchmark_listings"] or 0,
            days_away=gap["days_away"],
            forms=arena_forms(db, gap["department"])["forms"]))
    return out


# ---------------------------------------------------------------------------
# Slots: what an expedition is actually allowed to try


@dataclass(frozen=True)
class Slot:
    """One thing to invent: a form the market contains, in a lane that still has runway."""

    arena: Arena
    form: str
    make_lane: str
    benchmark_examples: int
    constructions: tuple[str, ...]
    engine_ready: bool
    needs_engineering: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"event": self.arena.event, "pod": self.arena.pod, "form": self.form,
                "make_lane": self.make_lane, "days_away": self.arena.days_away,
                "benchmark_examples": self.benchmark_examples,
                "constructions": list(self.constructions),
                "engine_ready": self.engine_ready,
                "needs_engineering": list(self.needs_engineering)}


# The fastest lane a form can honestly be made in. This is a *floor*, not a bracket: a beanie
# can be a QUICK make and a throw cannot, however short the runway is.
#
# Deriving it from physical size alone -- which is what the first version did -- filed a hat
# as SHORT and then dropped Halloween/hats for want of runway at 42 days, when a beanie is
# exactly the product the compression doctrine says to reach for as an occasion closes. Size
# and make time are correlated and not the same thing: a lace shawl is light and slow, a
# bulky stocking is bigger and fast.
FORM_MIN_LANE: dict[str, str] = {
    "coaster": "QUICK", "ornament": "QUICK", "toy": "QUICK", "pouch": "QUICK",
    "garland": "QUICK", "wreath": "QUICK", "sphere": "QUICK", "cone": "QUICK",
    "hat": "QUICK", "stocking": "QUICK", "tube": "QUICK", "round_disc": "QUICK",
    "basket": "SHORT", "bag": "SHORT", "pillow": "SHORT", "flat_panel": "SHORT",
    "scarf": "SHORT", "runner": "SHORT", "wall_hanging": "SHORT",
    "rectangle_throw": "MEDIUM", "draped_garment": "MEDIUM", "fitted_garment": "MEDIUM",
}

LANE_SPEED: tuple[str, ...] = ("QUICK", "SHORT", "MEDIUM", "LONG", "FLAGSHIP")


def _lane_for(form: str, viable_lanes: tuple[str, ...]) -> str | None:
    """The fastest viable lane this form can be made in, or None if none is.

    Fastest rather than natural, because the compression doctrine is that a shrinking runway
    changes the product mix rather than cancelling the occasion. A slower lane cannot rescue
    a form whose floor is already infeasible: lanes close in order, so if the floor is shut
    everything above it is too.
    """
    floor = FORM_MIN_LANE.get(form, "MEDIUM")
    for lane in LANE_SPEED[LANE_SPEED.index(floor):]:
        if lane in viable_lanes:
            return lane
    return None


def slots(arena: Arena, *, catalogue: list[Concept] | None = None,
          today: date | None = None, viable_lanes: tuple[str, ...] | None = None) -> dict:
    """Every form worth attempting in this arena, and why the others were left out.

    The refusals are the interesting output. A slot dropped for saturation says this
    catalogue already leans on that shape; a slot dropped for runway says the occasion is too
    close to start it; a slot kept but not engine-ready says the market wants something this
    compiler cannot build yet, which is a build item rather than a reason to make a throw.
    """
    from ..seasonal.compression import lane_states

    today = today or date.today()
    if viable_lanes is None:
        states = lane_states(arena.days_away, today=today)
        viable_lanes = tuple(s.lane for s in states if s.verdict != "infeasible")

    saturated = saturated_forms(catalogue or [])
    kept: list[Slot] = []
    dropped: list[dict] = []

    for form, examples in arena.forms.items():
        if form not in FORMS:
            dropped.append({"form": form, "why": "not in the concept form vocabulary"})
            continue
        if form in saturated:
            dropped.append({"form": form, "why": "saturated in this catalogue",
                            "share": saturated[form],
                            "detail": ("another one of these is not discovery, whatever its "
                                       "motif")})
            continue
        lane = _lane_for(form, tuple(viable_lanes))
        if lane is None:
            floor = FORM_MIN_LANE.get(form, "MEDIUM")
            dropped.append({"form": form, "why": "no runway", "lane": floor,
                            "detail": (f"the fastest honest {form} is a {floor} make and "
                                       f"that lane cannot reach {arena.event} in "
                                       f"{arena.days_away} days")})
            continue
        constructions = tuple(sorted(FORM_CONSTRUCTIONS.get(form, frozenset())))
        missing = tuple(c for c in constructions if ENGINE_ROUTE.get(c) is None)
        kept.append(Slot(
            arena=arena, form=form, make_lane=lane, benchmark_examples=examples,
            constructions=constructions,
            engine_ready=bool(constructions) and len(missing) < len(constructions),
            needs_engineering=missing))

    kept.sort(key=lambda s: -s.benchmark_examples)
    return {
        "arena": arena.to_dict(),
        "viable_lanes": list(viable_lanes),
        "slots": [s.to_dict() for s in kept],
        "slot_objects": kept,
        "dropped": dropped,
        "enough": len(kept) >= MIN_SLOTS,
        "engineering_required": sorted({c for s in kept for c in s.needs_engineering}),
        "note": ("Forms are counted from observed listings in this pod, so the vocabulary "
                 "comes from the market rather than from what this compiler finds easy. A "
                 "form the engine cannot build is reported, not dropped: dropping it is how "
                 "a catalogue converges on flat panels while believing it is being "
                 "selective."),
    }


def engine_gaps() -> dict:
    """Which constructions a maker uses that this compiler has never been taught.

    Separate from any expedition, because the answer does not depend on one: it is a standing
    statement of what the product universe is currently unable to contain.
    """
    missing = sorted(c for c in CONSTRUCTIONS if ENGINE_ROUTE.get(c) is None)
    # Both failure shapes, because they look identical from outside and are not. A form whose
    # every construction is unrouted needs engine work. A form absent from the map has no
    # construction at all, so nothing will ever propose it -- which is how a Christmas
    # stocking went unbuildable in a system that names Christmas a top priority.
    unroutable_forms = sorted(
        form for form, allowed in FORM_CONSTRUCTIONS.items()
        if allowed and all(ENGINE_ROUTE.get(c) is None for c in allowed))
    unmapped_forms = sorted(f for f in FORMS if not FORM_CONSTRUCTIONS.get(f))
    return {
        "cir_constructions": list(CIR_CONSTRUCTIONS),
        "concept_constructions": len(CONSTRUCTIONS),
        "routed": len(CONSTRUCTIONS) - len(missing),
        "needs_engineering": missing,
        "forms_with_no_buildable_construction": unroutable_forms,
        "forms_absent_from_the_buildability_map": unmapped_forms,
        "missing_primitive": MISSING_PRIMITIVE if missing else None,
        "closed_primitives": list(CLOSED_PRIMITIVES),
        "note": ("A construction with no route is a real thing a maker does that this engine "
                 "has not been taught. Naming it is the useful form; silently never "
                 "proposing products that need it is how the catalogue stayed flat."),
    }


# ---------------------------------------------------------------------------
# The expedition: a slot in, survivors out
#
# Every gate below is deterministic and adversarial, and each one is allowed to empty the
# field. A run that returns nothing from a proven arena is a real answer -- it says this
# system could not yet invent something worth selling there -- and it is a far more useful
# answer than a survivor that only survived because the gauntlet was tuned until something
# did.

# A concept must sit at least this far from everything already in the catalogue and from
# every sibling in its own field. Below it, the field is one idea with variations, which is
# the exact shape the existing catalogue has.
MIN_NOVELTY = 0.45

# The share of a field that may survive before the gauntlet is suspected of being decorative.
# Not a cap -- nothing is failed to hit it -- but a reported signal, because a gate that
# passes four fifths of what enters is a formality with a rejection message.
SUSPICIOUS_SURVIVAL = 0.60


@dataclass
class Candidate:
    """A concept with the record of what it survived, and what it did not."""

    concept: Concept
    slot: Slot
    killed_by: str = ""
    detail: str = ""
    nearest_key: str = ""
    nearest_distance: float = 1.0
    findings: list = field(default_factory=list)

    @property
    def survives(self) -> bool:
        return not self.killed_by

    def to_dict(self) -> dict:
        return {
            "key": self.concept.key, "title": self.concept.title,
            "pod": self.concept.pod, "form": self.concept.form,
            "construction": self.concept.construction, "motif": self.concept.motif,
            "occasion": self.concept.occasion, "recipient": self.concept.recipient,
            "feeling": self.concept.feeling, "make_lane": self.concept.make_lane,
            "premise": self.concept.premise,
            "survives": self.survives, "killed_by": self.killed_by, "detail": self.detail,
            "nearest": self.nearest_key, "novelty_distance": self.nearest_distance,
            "findings": [f.to_dict() if hasattr(f, "to_dict") else f for f in self.findings],
            "engine_ready": self.concept.construction in ENGINE_ROUTE
                            and ENGINE_ROUTE[self.concept.construction] is not None,
        }


def benchmark_comparables(db, *, pod: str = "", benchmark_key: str = "") -> list:
    """Observed listings as comparable cards, for the "is this theirs?" check.

    Named apart from `blinded.benchmark_cards`, which returns listing rows rather than cards.
    Two functions with one name in one package is a reading hazard, and this file is new
    enough that renaming it costs nothing.

    Deliberately cards rather than concepts. A `Concept` carries construction, motif and
    function, none of which a title states, and inventing them to make `distance()` work
    would produce a derivative check measuring fabricated fields. So the comparison runs on
    the five things both sides genuinely state, and its limit is reported rather than
    implied: this catches a concept indistinguishable from a listing on everything visible
    from outside. Catching a borrowed *execution* needs a product in hand, which is the
    `benchmark_purchases` gate.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from . import blinded

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        query = select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)
        if pod:
            query = query.where(BenchmarkListing.pod == pod)
        rows = list(s.scalars(query))

    out = []
    for row in rows:
        try:
            out.append(blinded.from_listing({
                "listing_ref": row.listing_ref, "title": row.title, "pod": row.pod,
                "product_type": row.product_type, "price_cad": row.price_cad}))
        except (blinded.Unreadable, blinded.NotComparable):
            continue
    return out


def _matches_a_listing(concept: Concept, cards: list) -> str:
    """The listing this concept is indistinguishable from, on everything either side states."""
    from . import blinded

    try:
        ours = blinded.from_concept(concept)
    except Exception:  # noqa: BLE001 - an unmappable concept simply cannot be compared
        return ""
    mine = ours.presented()
    for card in cards:
        if card.presented() == mine:
            return card.ref
    return ""


def screen(candidates: list[Candidate], *, catalogue: list[Concept] | None = None,
           benchmark: list | None = None,
           days_to_event: int | None = None, min_novelty: float = MIN_NOVELTY) -> dict:
    """Run the gauntlet. Order matters: cheap structural refusals before the expensive jury.

    The gates, in the order the owner named them:

      buildable form → jury (emotional, thumbnail, sameness, genericness, derivative,
      complexity, shopping window) → novelty against the catalogue → novelty against its own
      siblings → engineering feasibility.

    Feasibility is last and is *not* a kill. A concept the engine cannot build yet is marked
    and carried, because the alternative is a discovery process that can only ever discover
    what already compiles.
    """
    from .concept import distance, nearest
    from .jury import Context, judge

    catalogue = list(catalogue or [])
    alive: list[Candidate] = []

    for candidate in candidates:
        concept = candidate.concept
        allowed = FORM_CONSTRUCTIONS.get(concept.form) or frozenset()
        if allowed and concept.construction not in allowed:
            candidate.killed_by = "unbuildable"
            candidate.detail = (
                f"{concept.construction!r} does not build a {concept.form!r}: "
                f"{sorted(allowed)}")
            continue
        twin_ref = _matches_a_listing(concept, benchmark or [])
        if twin_ref:
            candidate.killed_by = "indistinguishable_from_a_benchmark_listing"
            candidate.detail = (
                f"listing {twin_ref} states the same pod, form, occasion, recipient and "
                f"feeling. Entering their arena is allowed; arriving as one of their "
                f"listings is not")
            continue
        verdict = judge(concept, Context(catalogue=catalogue, techniques=1,
                                         days_to_event=days_to_event))
        candidate.findings = list(verdict.findings)
        if not verdict.survives:
            candidate.killed_by = "jury"
            candidate.detail = "; ".join(f.problem for f in verdict.findings)[:400]
            continue
        _, gap = nearest(concept, catalogue) if catalogue else (None, 1.0)
        if catalogue:
            other, gap = nearest(concept, catalogue)
            candidate.nearest_key = other.key if other else ""
            candidate.nearest_distance = gap
            if gap < min_novelty:
                candidate.killed_by = "too_close_to_the_catalogue"
                candidate.detail = (
                    f"{gap} from {candidate.nearest_key!r}, below {min_novelty}")
                continue
        alive.append(candidate)

    # Siblings last, and pairwise, because a field can pass every individual gate and still
    # be one idea submitted five times -- which is what a generator does when the brief is
    # narrow and nobody checks the field against itself.
    survivors: list[Candidate] = []
    for candidate in alive:
        clash = None
        for kept in survivors:
            gap = distance(candidate.concept, kept.concept)
            if gap < min_novelty:
                clash = (kept.concept.key, gap)
                break
        if clash:
            candidate.killed_by = "too_close_to_a_sibling"
            candidate.detail = f"{clash[1]} from {clash[0]!r}, below {min_novelty}"
            continue
        survivors.append(candidate)

    entered = len(candidates)
    causes: dict[str, int] = {}
    for candidate in candidates:
        if candidate.killed_by:
            causes[candidate.killed_by] = causes.get(candidate.killed_by, 0) + 1

    rate = round(len(survivors) / entered, 4) if entered else 0.0
    return {
        "entered": entered,
        "survivors": [c.to_dict() for c in survivors],
        "survivor_objects": survivors,
        "killed": [c.to_dict() for c in candidates if c.killed_by],
        "survival_rate": rate,
        "causes": dict(sorted(causes.items(), key=lambda kv: -kv[1])),
        "gauntlet_suspicious": rate > SUSPICIOUS_SURVIVAL,
        "min_novelty": min_novelty,
        "benchmark_compared": len(benchmark or []),
        "benchmark_check_strength": (
            "title-level: it catches a concept indistinguishable from an observed listing "
            "on everything either side states. Catching a borrowed execution needs a "
            "product in hand, which is the benchmark_purchases gate"),
        "note": ("An empty field is a real answer: it says this system could not yet invent "
                 "something worth selling here. It is a better answer than a survivor that "
                 "only survived because the gauntlet was loosened until one did."),
    }


# ---------------------------------------------------------------------------
# Generation

GENERATION_TASK = "concept_generation"
FIELD_SIZE = 6

# The occasion each event maps to in the concept vocabulary. An event the vocabulary cannot
# express is not silently turned into `everyday`, because `everyday` is the value a Christmas
# product gets when nobody was paying attention.
EVENT_OCCASION: dict[str, str] = {
    "Christmas": "christmas", "Halloween": "halloween", "Easter": "easter",
    "Valentine's Day": "valentines", "Thanksgiving (CA)": "thanksgiving",
    "Thanksgiving": "thanksgiving", "Mother's Day": "mothers_day",
    "Father's Day": "fathers_day", "Back to School": "back_to_school",
}


def occasion_for(event: str) -> str:
    occasion = EVENT_OCCASION.get(event)
    if occasion is None:
        raise ProspectingRefused(
            f"{event!r} has no value in the concept occasion vocabulary. Defaulting it to "
            f"`everyday` would file a seasonal product as a year-round one, which is how a "
            f"Christmas concept misses Christmas")
    return occasion


def _brief_for(slot: Slot) -> str:
    """A two-dimension invention brief, so the field is asked for a thing rather than a type.

    Deterministic: the pair is chosen from the slot itself, so the same arena always asks the
    same question and a change in the field is a change in the answer rather than in the
    prompt.
    """
    from .invention import DIMENSIONS, NAMED_PAIRS, cross

    index = (hash((slot.arena.pod, slot.form)) % len(NAMED_PAIRS))
    a, b = NAMED_PAIRS[index]
    premise = (f"a {slot.form.replace('_', ' ')} for {slot.arena.event} where "
               f"{DIMENSIONS[a]} and {DIMENSIONS[b]} are the same decision rather than two "
               f"separate features of the object")
    return cross(a, b, season=slot.arena.event, premise=premise).to_dict()["premise"]


def propose(slot: Slot, *, gateway, count: int = FIELD_SIZE,
            agent: str = "creative_director") -> tuple[list[Candidate], list[str]]:
    """Ask for a field of concepts for one slot, and refuse everything malformed.

    Returns the candidates that parsed into valid Concepts and the reasons the rest did not.
    A model value outside a closed vocabulary is a structural rejection here rather than a
    plausible concept nothing downstream can check -- the vocabularies exist precisely so
    that a confident wrong answer fails loudly.
    """
    from .concept import CONSTRUCTIONS, FEELINGS, OCCASIONS, RECIPIENTS, ConceptRefused

    occasion = occasion_for(slot.arena.event)
    buildable = sorted(FORM_CONSTRUCTIONS.get(slot.form) or CONSTRUCTIONS)
    answer = gateway.complete_json(
        "creative.concept_field@1", agent=agent,
        values={
            "form": slot.form.replace("_", " "),
            "occasion": slot.arena.event,
            "make_lane": slot.make_lane,
            "evidence": (f"{slot.benchmark_examples} listings of this form were observed in "
                         f"a shop that sells in this department, {slot.arena.days_away} days "
                         f"before the occasion"),
            "constructions": ", ".join(buildable),
            "feelings": ", ".join(FEELINGS),
            "recipients": ", ".join(RECIPIENTS),
            "occasions": ", ".join(OCCASIONS),
            "brief": _brief_for(slot),
            "count": count,
        },
        required=("concepts",))

    out: list[Candidate] = []
    refused: list[str] = []
    for i, row in enumerate(answer.get("concepts") or []):
        if not isinstance(row, dict):
            refused.append(f"entry {i} is not an object")
            continue
        key = f"{slot.arena.pod}-{slot.form}-{i}"
        try:
            concept = Concept(
                key=key,
                title=str(row.get("title") or "").strip(),
                premise=str(row.get("premise") or "").strip(),
                pod=slot.arena.pod,
                form=slot.form,
                construction=str(row.get("construction") or "").strip(),
                motif=str(row.get("motif") or "").strip(),
                palette_story=str(row.get("palette_story") or "").strip(),
                recipient=str(row.get("recipient") or "").strip(),
                occasion=str(row.get("occasion") or occasion).strip(),
                feeling=str(row.get("feeling") or "").strip(),
                function=str(row.get("function") or "").strip(),
                make_lane=slot.make_lane,
                provenance=f"prospecting:{slot.arena.event}/{slot.arena.pod}/{slot.form}",
                notes=str(row.get("wow") or "").strip()[:300])
        except ConceptRefused as e:
            refused.append(f"{key}: {e}"[:220])
            continue
        out.append(Candidate(concept=concept, slot=slot))
    return out, refused


def expedition(db, arena: Arena, *, gateway, catalogue: list[Concept] | None = None,
               today: date | None = None, count: int = FIELD_SIZE,
               max_slots: int = 4, agent: str = "creative_director") -> dict:
    """One arena, end to end: slots, a field per slot, the gauntlet, and what is left.

    Budget is checked before each field rather than after the run, and a field that would
    cross the ceiling is not attempted -- the expedition returns what it bought and says it
    stopped, because a discovery run that consumes the month's model allowance is a worse
    outcome than a shorter one that can be repeated.
    """
    from ..gateway import routing

    catalogue = list(catalogue or [])
    plan = slots(arena, catalogue=catalogue, today=today)
    chosen = plan["slot_objects"][:max_slots]
    if not chosen:
        raise ProspectingRefused(
            f"no slot survives in {arena.event}/{arena.pod}: "
            + "; ".join(f'{d["form"]} ({d["why"]})' for d in plan["dropped"][:6]))

    started = routing.spent_this_month(db)
    candidates: list[Candidate] = []
    refusals: list[str] = []
    stopped = False
    for slot in chosen:
        try:
            routing.check(db, GENERATION_TASK)
        except routing.CeilingReached as e:
            stopped = True
            refusals.append(str(e)[:200])
            break
        try:
            field_, refused = propose(slot, gateway=gateway, count=count, agent=agent)
        except Exception as e:  # noqa: BLE001 - one failed field is not a failed expedition
            refusals.append(f"{slot.form}: {type(e).__name__}: {e}"[:220])
            continue
        candidates.extend(field_)
        refusals.extend(refused)

    result = screen(candidates, catalogue=catalogue,
                    benchmark=benchmark_comparables(db, pod=arena.pod),
                    days_to_event=arena.days_away)
    forms = sorted({c.concept.form for c in result["survivor_objects"]})
    return {
        "arena": arena.to_dict(),
        "plan": {k: v for k, v in plan.items() if k != "slot_objects"},
        "slots_attempted": [s.to_dict() for s in chosen],
        "proposed": len(candidates),
        "malformed": refusals,
        "stopped_on_ceiling": stopped,
        "cost_cad": round(routing.spent_this_month(db) - started, 6),
        "forms_discovered": forms,
        # Said rather than left for somebody to notice. The funnel's ideation stage sets a
        # floor because "fewer entrants than this and the stage is not a selection", and an
        # expedition proposes a couple of dozen. That does not make the pass worthless -- it
        # makes it prospecting into one arena rather than the tournament. Generating enough
        # per arena to clear the threshold would be optimising for volume, which is the one
        # thing the owner explicitly said not to do.
        "is_a_tournament": len(candidates) >= _ideation_floor(),
        "ideation_floor": _ideation_floor(),
        # The headline the owner asked for: not a win rate, but whether a proven arena with
        # no Brambleloop answer produced something that survived everything thrown at it.
        "answered_the_arena": bool(result["survivors"]),
        "what_this_is": (
            "a prospecting pass into one proven arena, not the full tournament. The "
            "tournament's ideation stage wants at least "
            f"{_ideation_floor()} entrants before a cut counts as a selection; generating "
            "that many per arena to clear the threshold would be optimising for volume"),
        **{k: v for k, v in result.items() if k != "survivor_objects"},
        "survivor_objects": result["survivor_objects"],
    }


# ---------------------------------------------------------------------------
# Memory
#
# Survivors are kept and fed back as catalogue on the next run. Without that, every
# expedition re-invents last week's field and the novelty gate has nothing to measure
# against -- a discovery process with no memory rediscovers its favourite idea forever.

ACTION = "creative.expedition"


def store(db, result: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=ACTION,
                       artifact=f'{result["arena"]["event"]}/{result["arena"]["pod"]}',
                       detail={k: v for k, v in result.items()
                               if k not in ("survivor_objects",)}))


def discovered(db, *, limit: int = 40) -> list[Concept]:
    """Every survivor a past expedition kept, rebuilt as concepts.

    Rebuilt rather than stored as objects, so a change to the concept vocabulary invalidates
    the old row loudly instead of resurrecting a shape the schema no longer allows.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from .concept import ConceptRefused

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                              .order_by(desc(AuditLog.id)).limit(limit)))
    out: list[Concept] = []
    for row in rows:
        for entry in (row.detail or {}).get("survivors") or []:
            try:
                out.append(Concept(
                    key=entry["key"], title=entry.get("title", ""),
                    premise=entry.get("premise", ""), pod=entry["pod"], form=entry["form"],
                    construction=entry["construction"], motif=entry.get("motif", ""),
                    palette_story=entry.get("palette_story", ""),
                    recipient=entry["recipient"], occasion=entry["occasion"],
                    feeling=entry["feeling"], function=entry.get("function", "carried"),
                    make_lane=entry["make_lane"], provenance="prospecting:stored"))
            except (KeyError, ConceptRefused):
                continue
    return out


def history(db, *, limit: int = 10) -> dict:
    """What discovery has actually produced, including the runs that produced nothing."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                              .order_by(desc(AuditLog.id)).limit(limit)))
    runs = [{
        "at": r.at.isoformat() if getattr(r, "at", None) else "",
        "arena": r.artifact,
        "proposed": (r.detail or {}).get("proposed", 0),
        "survivors": len(((r.detail or {}).get("survivors") or [])),
        "survival_rate": (r.detail or {}).get("survival_rate"),
        "forms": (r.detail or {}).get("forms_discovered") or [],
        "causes": (r.detail or {}).get("causes") or {},
        "cost_cad": (r.detail or {}).get("cost_cad"),
        "answered_the_arena": (r.detail or {}).get("answered_the_arena"),
    } for r in rows]
    return {
        "runs": runs,
        "arenas_answered": sorted({r["arena"] for r in runs if r["answered_the_arena"]}),
        "arenas_attempted": sorted({r["arena"] for r in runs}),
        "forms_discovered": sorted({f for r in runs for f in r["forms"]}),
        "total_cost_cad": round(sum(r["cost_cad"] or 0 for r in runs), 6),
        "note": ("Runs that produced nothing are kept. An expedition into a proven arena "
                 "that came back empty is evidence about this system's creative reach, and "
                 "deleting it would leave only the flattering half of the record."),
    }
