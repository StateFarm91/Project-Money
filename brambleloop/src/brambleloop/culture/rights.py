"""The rights router: what a cultural signal is allowed to become.

Requirements 135 and 139, and they are built before anything else in this package on purpose.
A culture radar is the single most dangerous thing a pattern company can own, because the
signals it finds are almost all somebody's property. "People are crocheting Baby Yoda" is a
true and commercially useful observation, and acting on it directly is trademark infringement
with a receipt attached.

The failure is not that somebody decides to infringe. It is that a pipeline optimising for
demand finds that the highest-scoring signals are all protected, and each step downstream
receives a slightly more abstract description of the same thing until the protected element
arrives at production having never been refused by anyone. Nobody chose it; the gradient did.

So three rules, and the first one is structural.

**A signal declares its protected tokens at the point it is recorded.** Not when it reaches
production, when the token has been paraphrased six times and nobody can see it any more. A
signal about a film names the film; a signal about a catchphrase names the catchphrase.

**Decomposition is checked, not trusted.** `check_free_of()` is what makes "decompose into
non-protected primitives" (#134) a property rather than an intention: the primitives are
scanned for the tokens the signal declared, and a primitive still carrying one is refused.

**Unclear rights route to the original lane, never to a block.** #135 is explicit about this
and it is the difference between a rights gate people route around and one they use. Refusing
the whole opportunity because the obvious execution is protected teaches the pipeline that the
gate is an obstacle. Sending it to the original-concept lane teaches it that the gate is a
turning, and the turning is where the durable product was anyway (#146).

The clearance lane records a *basis*, and what it records is a screen rather than an opinion.
This module does not give legal advice and says so: a public-domain screen checks a stated
publication year against a deliberately conservative cutoff, flags everything else for review,
and a basis is only ever as good as the evidence recorded with it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# The lanes. Two, not three: there is no "blocked" lane, because #135 requires that unclear
# rights become an original concept rather than a dead opportunity.
DIRECT = "direct_reference"     # the protected element itself, and only with a recorded basis
ORIGINAL = "original_concept"   # the emotional territory, expressed in our own language

LANES: tuple[str, ...] = (DIRECT, ORIGINAL)

# Rights-sensitive asset classes. #139 singles out dialogue, lyrics, slogans and catchphrases
# as their own class because they are the ones that feel free: a phrase is short, everybody
# says it, and putting it on a blanket is what the whole market appears to be doing.
CHARACTER_NAME = "character_name"
CHARACTER_LIKENESS = "character_likeness"
DIALOGUE = "dialogue"
LYRIC = "lyric"
SLOGAN = "slogan"
LOGO = "logo"
WORK_TITLE = "work_title"
DISTINCTIVE_MOTIF = "distinctive_motif"

PROTECTED_CLASSES: dict[str, str] = {
    CHARACTER_NAME: "a named character, which is a trade mark before it is anything else",
    CHARACTER_LIKENESS: "a recognisable character design, including a crocheted one",
    DIALOGUE: "a line of dialogue, however short and however often quoted",
    LYRIC: "song lyrics, which are licensed separately from everything else and rarely cheaply",
    SLOGAN: "a slogan or catchphrase, the class that feels most free and is not",
    LOGO: "a logo or wordmark",
    WORK_TITLE: "the title of a film, series, book, album or game",
    DISTINCTIVE_MOTIF: "a visual motif distinctive enough to identify its source",
}

# What can put something in the direct lane. Each carries what must be recorded with it, and
# none of them is "we looked and it seemed fine".
PUBLIC_DOMAIN = "public_domain"
LICENSED = "licensed"
PERMISSIONED = "permissioned"
BRAMBLELOOP_ORIGINAL = "brambleloop_original"
GENERIC = "generic"

CLEARANCE_BASES: dict[str, str] = {
    PUBLIC_DOMAIN: "the work's own publication year, jurisdiction and the screen's result",
    LICENSED: "the licence reference, its scope, its term and what it does not cover",
    PERMISSIONED: "who gave permission, when, in what form, and for which products",
    BRAMBLELOOP_ORIGINAL: "the Brambleloop work it originates from, so the claim is checkable",
    GENERIC: "why this phrase is ordinary language rather than a protected one, with the "
             "evidence that it is in common use outside the source",
}

# A deliberately conservative public-domain screen. The real rule varies by jurisdiction, work
# type, authorship and renewal, and a system that computed a date from a year would be giving
# legal advice while sounding like arithmetic. This refuses everything it is not sure about and
# says, every time, that passing the screen is not clearance.
PUBLIC_DOMAIN_SAFE_BEFORE = 1900

# Jurisdiction of record for this company.
JURISDICTION = "CA"


class RightsRefused(Exception):
    """A direct use with no basis, or a basis with nothing recorded behind it."""


@dataclass(frozen=True)
class ProtectedToken:
    """One thing a signal is about that somebody owns."""

    text: str
    asset_class: str
    source: str = ""

    def __post_init__(self) -> None:
        if self.asset_class not in PROTECTED_CLASSES:
            raise RightsRefused(
                f"{self.asset_class!r} is not a rights-sensitive class: "
                f"{sorted(PROTECTED_CLASSES)}. An unclassified protected token is one the "
                f"router cannot reason about, which is the same as one nobody declared")
        if not self.text.strip():
            raise RightsRefused("a protected token with no text cannot be checked for")

    def to_dict(self) -> dict:
        return {"text": self.text, "asset_class": self.asset_class, "source": self.source,
                "why_protected": PROTECTED_CLASSES[self.asset_class]}


@dataclass(frozen=True)
class Basis:
    """Why a direct reference is allowed, and the evidence that says so."""

    kind: str
    evidence: str
    recorded_by: str
    recorded_on: str = ""
    scope: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "evidence": self.evidence, "scope": self.scope,
                "recorded_by": self.recorded_by,
                "recorded_on": self.recorded_on or date.today().isoformat(),
                "requires": CLEARANCE_BASES[self.kind]}


def record_basis(kind: str, *, evidence: str, recorded_by: str, scope: str = "",
                 publication_year: int | None = None) -> Basis:
    """Record why a protected element may be used directly, refusing a basis that is a hope."""
    if kind not in CLEARANCE_BASES:
        raise RightsRefused(
            f"{kind!r} is not a clearance basis: {sorted(CLEARANCE_BASES)}. "
            f"'It seems fine' and 'everyone does it' are not bases; they are the two "
            f"sentences that precede every takedown")
    if len(evidence.strip()) < 20:
        raise RightsRefused(
            f"a {kind} basis records {CLEARANCE_BASES[kind]}. A basis with nothing behind it "
            f"is worse than none, because it looks like diligence in the record")
    if not recorded_by.strip():
        raise RightsRefused("a basis is recorded by somebody, so that somebody can be asked")

    if kind == PUBLIC_DOMAIN:
        if publication_year is None:
            raise RightsRefused(
                "a public-domain claim needs the work's publication year. Without it the "
                "claim is an assumption wearing a category name")
        if publication_year >= PUBLIC_DOMAIN_SAFE_BEFORE:
            raise RightsRefused(
                f"published {publication_year}: this screen only passes works published "
                f"before {PUBLIC_DOMAIN_SAFE_BEFORE}, deliberately far earlier than any "
                f"jurisdiction requires. Term depends on authorship, work type, renewal and "
                f"country, and a system that computed a date from a year would be giving "
                f"legal advice while sounding like arithmetic. Route it to the original "
                f"lane, or ask the owner for a reviewed opinion")
        evidence = (f"{evidence.strip()} [screen: published {publication_year}, before the "
                    f"{PUBLIC_DOMAIN_SAFE_BEFORE} conservative cutoff, jurisdiction "
                    f"{JURISDICTION}. Passing this screen is not clearance.]")

    return Basis(kind=kind, evidence=evidence.strip(), recorded_by=recorded_by.strip(),
                 recorded_on=date.today().isoformat(), scope=scope.strip())


# ---------------------------------------------------------------------------
# Routing (#135, #139)


@dataclass
class Routing:
    lane: str
    tokens: list[ProtectedToken] = field(default_factory=list)
    basis: Basis | None = None
    reason: str = ""
    may_reach_customers: bool = False

    def to_dict(self) -> dict:
        return {"lane": self.lane, "reason": self.reason,
                "may_reach_customers": self.may_reach_customers,
                "tokens": [t.to_dict() for t in self.tokens],
                "basis": self.basis.to_dict() if self.basis else None}


def route(tokens: list[ProtectedToken], *, basis: Basis | None = None,
          intended_use: str = "") -> Routing:
    """Decide what a cultural signal may become.

    Three outcomes and no fourth: nothing protected, so use it freely; protected with a
    recorded basis, so the direct lane; protected without one, so the original lane. The
    opportunity is never discarded, because a gate that kills opportunities is a gate that
    gets argued with until it loses.
    """
    if not tokens:
        return Routing(lane=DIRECT, tokens=[], basis=None, may_reach_customers=True,
                       reason=("nothing protected was declared, so there is nothing for this "
                               "router to hold back"))
    if basis is None:
        return Routing(
            lane=ORIGINAL, tokens=list(tokens), basis=None, may_reach_customers=False,
            reason=(f"{len(tokens)} protected element(s) with no recorded basis. This is not "
                    f"a refusal of the opportunity: the emotional territory is available and "
                    f"the original lane is where a product we own comes from (#135, #146). "
                    f"What may not happen is the protected element reaching a customer"))
    return Routing(
        lane=DIRECT, tokens=list(tokens), basis=basis, may_reach_customers=True,
        reason=(f"direct use permitted on a recorded {basis.kind} basis"
                f"{f' for {basis.scope}' if basis.scope else ''}. The basis is only as good "
                f"as its evidence, and the evidence is on the record"))


def check_direct_use(routing: Routing, *, product_or_copy: str) -> None:
    """The last gate before a customer sees it. Raises rather than reports.

    Called from the point where a cultural concept becomes customer-facing, so that a concept
    which quietly picked up a protected token somewhere in the middle of the pipeline is
    caught at the end as well as at the beginning.
    """
    if routing.lane == DIRECT and routing.may_reach_customers:
        return
    surviving = [t for t in routing.tokens if _contains(product_or_copy, t.text)]
    if surviving:
        raise RightsRefused(
            f"{[t.text for t in surviving]} reached customer-facing output through the "
            f"original-concept lane. The lane exists to express the same emotional territory "
            f"in our own language; carrying the protected element through it is the "
            f"infringement with an extra step, and the extra step is what makes it hard to "
            f"see in review")


# ---------------------------------------------------------------------------
# Checking a decomposition (#134, #139)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())


def _contains(haystack: str, needle: str) -> bool:
    """Word-boundary containment on normalised text.

    Substring matching would fire on 'art' inside 'heart' and teach everybody to work around
    the check, which is worse than not having it.
    """
    h = f" {' '.join(_normalise(haystack).split())} "
    n = " ".join(_normalise(needle).split())
    return bool(n) and f" {n} " in h


def check_free_of(text: str, tokens: list[ProtectedToken], *, what: str = "this") -> None:
    """Refuse text that still carries something the signal declared as protected.

    This is what turns #134's "decompose into non-protected primitives" from an instruction
    into a property. The primitives are derived from a protected source, so the only question
    that matters is whether the source survived the derivation — and a decomposition nobody
    checks is a paraphrase.
    """
    carried = [t for t in tokens if _contains(text, t.text)]
    if carried:
        first = carried[0]
        raise RightsRefused(
            f"{what} still carries {first.text!r} ({first.asset_class}: "
            f"{PROTECTED_CLASSES[first.asset_class]}). Decomposition means keeping the "
            f"emotion, era, humour and ritual and leaving the property behind; text that "
            f"still names it has been abbreviated rather than decomposed")


def describe() -> dict:
    """The rule, where somebody who is not reading the code can find it."""
    return {
        "lanes": {
            DIRECT: ("the protected element itself, permitted only with a basis recorded "
                     "before use"),
            ORIGINAL: ("the same emotional territory in Brambleloop's own language; where "
                       "unclear rights go, and where durable original IP comes from"),
        },
        "protected_classes": PROTECTED_CLASSES,
        "clearance_bases": CLEARANCE_BASES,
        "public_domain_screen": {
            "safe_before": PUBLIC_DOMAIN_SAFE_BEFORE,
            "jurisdiction": JURISDICTION,
            "note": ("A deliberately conservative screen, not a clearance. Copyright term "
                     "depends on authorship, work type, renewal and country; a system that "
                     "computed a date from a year would be giving legal advice while "
                     "sounding like arithmetic."),
        },
        "may_never": [
            "use a named character, likeness, quote, lyric, slogan, logo or title without a "
            "recorded basis",
            "treat 'everyone else is doing it' as a basis",
            "discard a cultural opportunity because its obvious execution is protected",
        ],
        "why": ("A pipeline optimising for demand finds that the strongest signals are all "
                "protected, and each step receives a slightly more abstract description of "
                "the same thing until it arrives at production having been refused by "
                "nobody. Nobody chose it; the gradient did."),
    }
