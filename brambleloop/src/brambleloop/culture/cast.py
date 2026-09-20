"""Characters this company owns, and the difference between owning one and naming one.

Requirement 146. Use cultural observation as raw material for Brambleloop-owned recurring
characters, motifs, jokes, traditions and collection worlds. The long-term goal is stated in
the requirement itself and is the part worth encoding: *not permanent dependence on external
pop culture* -- recognisable original seasonal IP that customers return for.

`culture.translate` already makes the borrowed/owned split countable across nineteen
territories, and `culture.rights` already routes a protected token away from a product. What
neither does is hold the thing the requirement is actually asking for, and three properties
decide how it is held.

**Recurrence is the whole of it, and recurrence cannot be declared.** A character invented
once and used once is a motif with a name. "Customers return for it" is a claim about the
second time, so an element is `proposed` until it has appeared in enough releases across
enough seasons, and it becomes `recurring` by having recurred -- there is no argument, no
flag and no field that promotes it. An IP roster that can be populated by writing names in it
measures enthusiasm.

**Originality is checked on the primitives, never on the name.** The dangerous failure here
is not a product that borrows openly; that path exists, is routed by `culture.rights`, and is
recorded as borrowed. It is a character with an original name whose design is a recognisable
external one -- which looks like an asset, carries the full legal risk of the thing it
resembles, and cannot be defended precisely because nobody wrote down what it was derived
from. So an element records the cultural *primitives* it came from -- emotion, era, ritual,
colour language -- and never a property, and a proposal naming a protected token anywhere is
refused whatever the name on it.

**A collection world has to be able to accept something that did not exist when it was
made.** A "world" describing its own three products is a retrospective label for a bundle. So
a world declares what it is about before its second product, and `can_host` answers for a
product the world has never seen. A world that can only answer for what it already contains
is refused as a name rather than a place.

The number this produces is a *direction*, not a state: "not permanent dependence" is
something a catalogue moves toward, and `dependence()` reports the borrowed share over time
rather than at a moment, because a dependence nobody trends is one nobody notices growing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import rights, translate

# What an owned element can be. The requirement names five, and the vocabulary is closed
# because an IP roster that grows a category whenever something does not fit is a list of
# everything the company has ever made.
CHARACTER = "character"
MOTIF = "motif"
JOKE = "joke"
TRADITION = "tradition"
WORLD = "collection_world"

KINDS: dict[str, str] = {
    CHARACTER: "a recurring figure with a name, a role and a look of its own",
    MOTIF: "a visual element that reappears and is recognised without being explained",
    JOKE: "a repeated comic premise the catalogue returns to",
    TRADITION: "a thing this shop does every year that buyers come back for",
    WORLD: "a setting that can host products nobody has designed yet",
}

PROPOSED = "proposed"
RECURRING = "recurring"
RETIRED = "retired"

# What it takes to stop being a name and start being IP. Two appearances is a coincidence
# inside one season's work; the season count is what makes it something a customer could
# return *for*, because returning requires having gone away.
MIN_APPEARANCES = 3
MIN_SEASONS = 2


class CastRefused(ValueError):
    """An element owned in name only, or a world that is a label for a bundle."""


@dataclass(frozen=True)
class Appearance:
    """One release an element appeared in, which is the only way it accumulates standing."""

    product_slug: str
    season: str
    released_on: str

    def __post_init__(self) -> None:
        if not self.product_slug.strip():
            raise CastRefused("an appearance names the product it appeared in")
        if not self.season.strip():
            raise CastRefused(
                "an appearance names its season: recurrence across one season's work is a "
                "collection, and across several is IP")


@dataclass
class Element:
    """One owned character, motif, joke, tradition or world."""

    key: str
    kind: str
    name: str
    about: str
    derived_from: dict[str, str] = field(default_factory=dict)
    appearances: list[Appearance] = field(default_factory=list)
    retired_because: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise CastRefused(f"{self.kind!r} is not an owned-IP kind: {sorted(KINDS)}")
        if len(self.about.split()) < 5:
            raise CastRefused(
                f"{self.key}: say what this is, in a sentence. A name with no description is "
                f"a name, and the roster is supposed to hold more than names")
        unknown = sorted(set(self.derived_from) - set(translate.PRIMITIVE_KEYS))
        if unknown:
            raise CastRefused(
                f"{self.key}: {unknown} are not cultural primitives: "
                f"{list(translate.PRIMITIVE_KEYS)}. Culture is the raw material, so what was "
                f"taken from it is recorded as a primitive -- never as the property it came "
                f"from, which is the thing this company does not want to depend on")
        if not self.derived_from:
            raise CastRefused(
                f"{self.key}: nothing is derived from nothing. An element with no recorded "
                f"primitives cannot be shown later to have been original rather than "
                f"remembered")

    @property
    def seasons(self) -> set[str]:
        return {a.season for a in self.appearances}

    @property
    def status(self) -> str:
        if self.retired_because:
            return RETIRED
        if (len(self.appearances) >= MIN_APPEARANCES
                and len(self.seasons) >= MIN_SEASONS):
            return RECURRING
        return PROPOSED

    def to_dict(self) -> dict:
        return {
            "key": self.key, "kind": self.kind, "name": self.name, "about": self.about,
            "status": self.status,
            "derived_from": dict(self.derived_from),
            "appearances": len(self.appearances),
            "seasons": sorted(self.seasons),
            "needs": ({} if self.status != PROPOSED else
                      {"appearances": max(0, MIN_APPEARANCES - len(self.appearances)),
                       "seasons": max(0, MIN_SEASONS - len(self.seasons))}),
            "retired_because": self.retired_because,
        }


def propose(*, key: str, kind: str, name: str, about: str,
            derived_from: dict[str, str],
            declared_tokens: list[rights.ProtectedToken] | None = None) -> Element:
    """Open an owned element, refusing one that is only owned in name.

    The rights check runs over the name, the description *and* every derived primitive rather
    than over the name alone, because the failure being guarded is the one where the name is
    the only original part. It reuses `rights.check_free_of`, which does word-boundary
    matching on normalised text -- a second implementation here would be a second answer to
    "is this token present", and the more permissive one would get used.

    `declared_tokens` are the protected tokens the source signal declared at observation, per
    #133. Passing none means the signal declared none, which is a fact about the signal
    rather than a licence: an element derived from a signal with no declared tokens is as
    original as that declaration was honest, and the declaration is on the record.
    """
    tokens = list(declared_tokens or [])
    surface = " ".join([name, about, *derived_from.values()])
    try:
        rights.check_free_of(surface, tokens, what=f"owned element {key!r}")
    except rights.RightsRefused as exc:
        raise CastRefused(
            f"{key}: {exc}. An element that leans on a protected token is borrowed however "
            f"it is named, and naming it something else makes it harder to defend rather "
            f"than easier -- nobody can show what it was derived from. The borrowed path "
            f"exists and is routed by culture.rights; this roster is for what this company "
            f"owns") from exc
    return Element(key=key, kind=kind, name=name, about=about,
                   derived_from=dict(derived_from))


def record_appearance(element: Element, appearance: Appearance) -> dict:
    """Add a release, which is the only thing that moves an element toward `recurring`."""
    if element.retired_because:
        raise CastRefused(
            f"{element.key} was retired: {element.retired_because}. Bringing it back is a "
            f"new proposal rather than an appearance, because the roster should show that "
            f"somebody decided twice")
    if any(a.product_slug == appearance.product_slug for a in element.appearances):
        raise CastRefused(
            f"{element.key} already appears in {appearance.product_slug}. Counting one "
            f"product twice is how a roster reaches `recurring` without recurring")
    element.appearances.append(appearance)
    return element.to_dict()


def retire(element: Element, because: str) -> dict:
    """Stop using an element, which a roster that only grows never does."""
    if len(because.split()) < 5:
        raise CastRefused(
            f"{element.key}: retiring an element needs a reason somebody can argue with")
    element.retired_because = because
    return element.to_dict()


# ---- collection worlds ----------------------------------------------------

@dataclass(frozen=True)
class World:
    """A setting, declared before its second product, that can host one it has never seen."""

    key: str
    name: str
    premise: str
    admits: tuple[str, ...]        # object categories this world can hold
    excludes: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.premise.split()) < 6:
            raise CastRefused(
                f"{self.key}: a world needs a premise somebody could design against")
        if not self.admits:
            raise CastRefused(
                f"{self.key}: a world that admits nothing is a label for what already "
                f"exists. Say what it can hold, before the thing it holds is made")
        overlap = sorted(set(self.admits) & set(self.excludes))
        if overlap:
            raise CastRefused(
                f"{self.key}: {overlap} both admitted and excluded, which answers nothing")


def can_host(world: World, *, object_category: str) -> dict:
    """Whether this world can accept a product it has never seen.

    The test that separates a world from a bundle: a retrospective label can only answer for
    what it already contains, and this question is always about something new.
    """
    if object_category in world.excludes:
        return {"can_host": False, "world": world.key, "object_category": object_category,
                "why": f"{world.key} excludes {object_category} by its own premise"}
    if object_category in world.admits:
        return {"can_host": True, "world": world.key, "object_category": object_category,
                "why": f"{world.key} admits {object_category}: {world.premise}"}
    return {"can_host": False, "world": world.key, "object_category": object_category,
            "why": (f"{world.key} neither admits nor excludes {object_category}. An "
                    f"undecided answer is a decision to make rather than a yes, because a "
                    f"world that admits anything nobody has ruled out is not a setting")}


# ---- the direction, not the state -----------------------------------------

def roster(elements: list[Element]) -> dict:
    """Everything on the roster, with `recurring` counted apart from `proposed`."""
    rows = [e.to_dict() for e in elements]
    recurring = [r for r in rows if r["status"] == RECURRING]
    proposed = [r for r in rows if r["status"] == PROPOSED]
    retired = [r for r in rows if r["status"] == RETIRED]
    by_kind: dict[str, int] = {}
    for r in recurring:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    return {
        "elements": rows,
        "recurring": len(recurring), "proposed": len(proposed), "retired": len(retired),
        "recurring_by_kind": dict(sorted(by_kind.items())),
        "thresholds": {"appearances": MIN_APPEARANCES, "seasons": MIN_SEASONS},
        "note": ("`proposed` is the honest default and most of a young roster is in it. An "
                 "element becomes recurring by having recurred, never by being marked so: a "
                 "roster that can be populated by writing names in it measures enthusiasm"),
    }


def dependence(history: list[dict]) -> dict:
    """The borrowed share over time, because "not permanent dependence" is a direction.

    Each entry is {"period": str, "borrowed": int, "owned": int}. A single reading says
    nothing about whether the company is moving toward its own IP or away from it, and the
    requirement's goal is entirely about which way it is going.
    """
    if not history:
        return {"readable": False,
                "why": ("no periods supplied. A dependence figure at one moment cannot say "
                        "whether it is falling, and falling is the requirement")}
    points = []
    for entry in history:
        borrowed = int(entry.get("borrowed", 0))
        owned = int(entry.get("owned", 0))
        total = borrowed + owned
        points.append({
            "period": entry.get("period", ""),
            "borrowed": borrowed, "owned": owned,
            "borrowed_share": round(borrowed / total, 3) if total else None,
        })
    measured = [p for p in points if p["borrowed_share"] is not None]
    if len(measured) < 2:
        return {"readable": False, "points": points,
                "why": (f"{len(measured)} period(s) with any products in them. Two is the "
                        f"fewest that can have a direction")}
    first, last = measured[0]["borrowed_share"], measured[-1]["borrowed_share"]
    change = last - first
    if abs(change) < 0.05:
        direction = "flat"
        why = (f"borrowed share {first:.0%} to {last:.0%}: unchanged within noise. Flat is "
               f"not progress toward owning the catalogue's appeal")
    elif change < 0:
        direction = "toward_owned"
        why = f"borrowed share fell from {first:.0%} to {last:.0%}"
    else:
        direction = "toward_borrowed"
        why = (f"borrowed share rose from {first:.0%} to {last:.0%}. Each borrowed product "
               f"is rented: it can be withdrawn in January and nothing accumulates")
    return {"readable": True, "points": points, "direction": direction,
            "borrowed_share_now": last, "change": round(change, 3), "why": why}


def state() -> dict:
    """What the roster holds, and what it refuses to let anybody declare."""
    return {
        "requirement": 146,
        "kinds": dict(KINDS),
        "thresholds": {"appearances": MIN_APPEARANCES, "seasons": MIN_SEASONS},
        "builds_on": {
            "culture.translate": "the primitives an element may be derived from, and the "
                                 "nineteen owned territories",
            "culture.rights": "the protected tokens an owned element may not lean on",
        },
        "refuses": [
            "an element promoted to recurring by anything other than having recurred",
            "one product counted twice toward recurrence",
            "an element whose name, description or primitives carry a protected token",
            "an element with no recorded primitives, which cannot be shown to be original",
            "a world that admits nothing, which is a label for what already exists",
            "a dependence figure read from a single period",
        ],
        "today": ("the roster is empty. Nothing has been designed under it yet, and an empty "
                  "roster is the correct state for a company that has released nothing -- "
                  "the alternative is names somebody wrote down"),
        "note": ("the goal in the requirement is a direction: not permanent dependence. A "
                 "dependence nobody trends is one nobody notices growing, so dependence() "
                 "refuses to answer from one reading"),
    }
