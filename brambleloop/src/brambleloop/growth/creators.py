"""The creator and tester roster: what may be asked for, and what may never be bought.

Requirements 9 and 21. A seeding roster records specialty, audience fit, reliability,
engagement and permissions, and it exists so this company can get the things it genuinely
cannot make for itself -- an independent physical proof, a photograph of the finished object
in somebody else's house, a colourway nobody here chose, a crochet-along, and an audience
that is not ours. #21 adds the discipline: start small, measure, and only then spend.

The whole category is one step away from the thing the owner's directive forbids outright,
so the line is drawn in the data structures rather than in a paragraph.

**A collaboration buys work. It can never buy an opinion.** The deliverable vocabulary is
closed and contains no opinion-shaped item: a tested sample, a finished photograph, a colour
variation, a crochet-along, a post. A review is not on the list and cannot be put on it by a
caller, because "never require or purchase dishonest reviews" survives contact with a
deadline only if requiring a review is unrepresentable. A creator who writes one unprompted
has written their own; that is theirs, and nothing here asked for it.

**An arrangement conditioned on sentiment is refused even when the deliverable is honest.**
"Photograph it and say something nice", "payment on a positive post", "we will send the next
one if this goes well" -- each buys the opinion through the side door, and the last one is
the commonest because nobody writes it down.

**A number nobody here observed is a number this module will not compute with.** A stated
follower count is a claim, kept as a claim with its source. There is no reach projection, no
expected-impressions arithmetic and no multiplication of an audience by a rate, and their
absence is asserted by a test that reads this source, because the fabricated-engagement
failure arrives as a spreadsheet far more often than as a lie.

**Permission is scoped or it is not permission.** A photograph licensed for the creator's own
channel is not licensed for our listing, and the difference is the entire question. Every use
names a scope and a reference somebody can go and check; an expired permission is refused
like an absent one.

**A paid or affiliate arrangement is disclosed in the post the audience reads** -- not in a
profile, not on a linked page, not in a hashtag after nine others. And money makes it
consequential spend, which the owner approves and this module refuses without.

What this leaves is the part that costs nothing: a digital pattern given to a maker whose
work is in the right department. That is the micro-seeding #21 asks to start with, and it is
available today. The scaling half is not: attributable traffic, conversion and support impact
need a live listing and customers, and this module refuses to call an unmeasured outcome a
zero, because a roster that scales on "no bad news" is the same defect this build keeps
finding in a friendlier costume.

**The portfolio (#249) has the same defect waiting in its other instruction.** "Scale
high-contribution relationships and stop weak ones" is correct and, applied to a roster where
most relationships are unmeasured, stops the ones nobody got round to measuring. An unmeasured
relationship is not a weak one; it is a relationship with no evidence, and the action it
calls for is a measurement rather than an ending. So `portfolio()` classifies only what has
been measured, and names the rest as unmeasured instead of sorting them to the bottom -- which
is where things get cut from.

**The tester who becomes an ambassador (#250) is where two honest programmes quietly merge
into one dishonest one.** A tester is paid, or given a sample, to find what is wrong. An
ambassador is given a relationship for saying what is good. Run those through one agreement
and the test fee becomes a review fee -- and worse, the testing stops working: a tester whose
ambassador status depends on enthusiasm reports fewer defects, and the physical sample is the
most expensive signal this company buys. So graduation requires a separate, recorded,
revocable consent, and an arrangement whose testing terms mention anything public is refused
by name. A tester who reports a defect must be able to do it without it costing them
anything, and that is stated as a term rather than assumed as a courtesy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from ..intel.pods import POD_KEYS
from ..quality.testers import RELIABLE_AT
from . import owned

# What a collaboration may ask for. Closed, and every entry is a piece of work somebody does
# rather than an opinion somebody holds.
DELIVERABLES: dict[str, str] = {
    "tested_sample": ("they make the thing from the pattern and report what happened, "
                      "including when it did not work"),
    "finished_photograph": "a photograph of the finished object, in their hands and setting",
    "colour_variation": "the same pattern in a colourway nobody here would have chosen",
    "crochet_along": "they run the pattern with their audience over a set period",
    "audience_post": "they show the work to people who have never heard of this company",
    "tutorial_segment": "they teach one technique the pattern uses, in their own way",
}

# Named so the refusal can say the word rather than "not in the list". Every one of these is
# an opinion, and an opinion is not purchasable here at any price including zero.
NEVER_A_DELIVERABLE: tuple[str, ...] = (
    "review", "rating", "star_rating", "testimonial", "endorsement", "positive_mention",
    "favourite", "five_star", "recommendation")

# Phrases that buy the opinion through the side door while the deliverable stays honest.
# Matched as meaning rather than as a blessed sentence: the last one is the commonest and is
# almost never written down, which is why it is written down here.
SENTIMENT_STRINGS: tuple[tuple[str, str], ...] = (
    ("say something nice", "an instruction about what to think, wearing a deliverable"),
    ("positive", "payment or continuation conditioned on the opinion being favourable"),
    ("favourable", "the same condition in a longer word"),
    ("only if you like", "a condition on sentiment is a condition on sentiment"),
    ("if it goes well", "the next collaboration as payment for this one's tone"),
    ("glowing", "an adjective nobody uses about work they were free to dislike"),
    ("5 star", "a rating is an opinion and is not for sale"),
    ("five star", "a rating is an opinion and is not for sale"),
)

# Where an asset may be used. A permission is one of these or it is not a permission.
SCOPES: tuple[str, ...] = (
    "creator_channel", "brambleloop_listing", "brambleloop_site", "brambleloop_email",
    "advertising")

# Disclosure, in the only place it counts.
DISCLOSURE_IN = ("the post the audience actually reads -- not a profile, not a linked page, "
                 "not a hashtag after nine others")
DISCLOSURE_MARKERS: tuple[str, ...] = ("paid partnership", "gifted", "affiliate", "ad",
                                       "sponsored", "commission")

# Quantities this module will not compute, listed so their absence is a decision rather than
# an oversight. A stated audience is a claim; multiplying a claim by a rate produces a number
# that looks measured and is not, which is how fabricated engagement usually arrives.
NEVER_PROJECTED: tuple[str, ...] = (
    "expected_reach", "projected_impressions", "estimated_views", "expected_clicks")

# #21's bar before creator spend scales. Three completed collaborations, because two is a
# coincidence, and every outcome measured rather than merely not bad.
MIN_COLLABORATIONS_BEFORE_SCALING = 3
# A pattern costs nothing to give, so seeding can start without spend. Anything above this is
# consequential and belongs to the owner.
FREE_SEEDING_CEILING_CAD = 0.0


def _says_what_it_is(disclosure: str) -> bool:
    """Whether a disclosure carries a word a reader would recognise as one.

    Whole words, because the first draft matched "ad" inside "made" and passed "made with a
    lovely pattern" as a disclosed partnership -- a substring check that quietly approves the
    exact copy it exists to catch.
    """
    text = disclosure.lower()
    return any(re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", text)
               for marker in DISCLOSURE_MARKERS)


# How a relationship is classified once there is evidence for it (#249).
SCALE = "scale"
HOLD = "hold"
STOP = "stop"
UNMEASURED = "unmeasured"

# One good collaboration is a good collaboration. A track record needs more than one.
MIN_COLLABORATIONS_FOR_A_RECORD = 2
# Contribution per dollar below this, with a record behind it, is a relationship to end.
WEAK_BELOW = 0.5
# And above this it is one to grow.
STRONG_ABOVE = 2.0

# Terms that turn a test into a review. Each is a phrase that makes a testing arrangement
# contingent on something public, which is where the fee stops being a fee for testing.
PUBLIC_IN_TESTING_TERMS: tuple[str, ...] = (
    "post", "share", "review", "tag us", "story", "publicly", "mention", "feature")


class CreatorRefused(ValueError):
    """An arrangement that buys an opinion, uses an asset it may not, or spends money."""


@dataclass(frozen=True)
class Permission:
    """One recorded permission to use one creator's asset, for one purpose, until a date."""

    ref: str                       # where the permission is recorded, so it can be checked
    asset_ref: str
    scope: str
    granted_on: date
    expires_on: date | None = None

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise CreatorRefused(f"{self.scope!r} is not a permission scope: {list(SCOPES)}")
        if not self.ref.strip():
            raise CreatorRefused(
                "a permission with no reference is an assertion. Somebody has to be able to "
                "go and look at what was agreed, months later, without asking us")


@dataclass(frozen=True)
class Creator:
    """One person on the roster. Claims are kept as claims, with where they came from."""

    ref: str
    specialties: tuple[str, ...]
    # What they say their audience is, and where that number came from. Empty evidence means
    # self-reported, which is recorded rather than corrected.
    audience_stated: int | None = None
    audience_evidence: str = ""
    # Engagement we watched ourselves, and the day we watched it. Both or neither.
    engagement_observed: float | None = None
    observed_on: date | None = None
    invited: int = 0
    delivered: int = 0
    address_published: bool = False
    address_refuses_unsolicited: bool = False
    permissions: tuple[Permission, ...] = ()

    def __post_init__(self) -> None:
        bad = [s for s in self.specialties if s not in POD_KEYS]
        if bad:
            raise CreatorRefused(
                f"{bad} are not departments this company works in: {list(POD_KEYS)}. A "
                f"specialty nobody can match is a roster entry nobody will ever reach for")
        if (self.engagement_observed is None) != (self.observed_on is None):
            raise CreatorRefused(
                "an engagement figure and the day it was observed travel together. A rate "
                "with no date is a rate from whenever somebody last looked, which is the "
                "number people quote for years")

    @property
    def reliability(self) -> float:
        return (self.delivered / self.invited) if self.invited else 0.0

    @property
    def reliable(self) -> bool:
        # Never having been asked is not reliability, and it is not unreliability either.
        # The threshold is the tester roster's own, imported rather than chosen again.
        return self.invited >= 2 and self.reliability >= RELIABLE_AT

    def fits(self, pod: str) -> bool:
        return pod in self.specialties

    def to_dict(self) -> dict:
        return {
            "ref": self.ref, "specialties": list(self.specialties),
            "audience": ({"stated": self.audience_stated,
                          "evidence": self.audience_evidence or "self-reported",
                          "verified": bool(self.audience_evidence.strip())}
                         if self.audience_stated is not None else
                         {"stated": None, "why": "not recorded, which is not zero"}),
            "engagement": ({"observed": self.engagement_observed,
                            "observed_on": self.observed_on.isoformat()}
                           if self.engagement_observed is not None else
                           {"observed": None,
                            "why": "nobody here has watched it, and a stated rate is a "
                                   "claim about the thing most often bought"}),
            "invited": self.invited, "delivered": self.delivered,
            "reliability": round(self.reliability, 3), "reliable": self.reliable,
            "basis": ("too few invitations to say" if self.invited < 2
                      else "delivered against invited"),
            "permissions": [{"asset_ref": p.asset_ref, "scope": p.scope, "ref": p.ref}
                            for p in self.permissions],
        }


@dataclass(frozen=True)
class Brief:
    """What one collaboration asks for, and what it pays."""

    creator_ref: str
    pod: str
    deliverables: tuple[str, ...]
    fee_cad: float = 0.0
    affiliate: bool = False
    disclosure_in_post: str = ""
    terms: str = ""


def check_brief(brief: Brief) -> dict:
    """Every reason this collaboration may not be offered. Empty means it may."""
    reasons: list[str] = []

    if not brief.deliverables:
        reasons.append("a collaboration that asks for nothing is a gift with an expectation "
                       "attached, which is the arrangement hardest to keep honest")
    for item in brief.deliverables:
        if item in NEVER_A_DELIVERABLE:
            reasons.append(
                f"{item!r} is an opinion, not work. Never require or purchase dishonest "
                f"reviews means requiring a review cannot be expressible here -- and a "
                f"review somebody chooses to write afterwards is theirs, not ours")
        elif item not in DELIVERABLES:
            reasons.append(f"{item!r} is not a deliverable: {sorted(DELIVERABLES)}")

    haystack = f"{brief.terms} {brief.disclosure_in_post}".lower()
    for needle, why in SENTIMENT_STRINGS:
        if needle in haystack:
            reasons.append(f"terms contain {needle!r}: {why}")

    if brief.pod not in POD_KEYS:
        reasons.append(f"{brief.pod!r} is not a department: {list(POD_KEYS)}")

    if brief.fee_cad > FREE_SEEDING_CEILING_CAD:
        reasons.append(
            f"CA${brief.fee_cad:.2f} is consequential spend and belongs to the owner. "
            f"Seeding starts at zero because a digital pattern costs nothing to give, which "
            f"is exactly why small legitimate collaborations can begin before any budget "
            f"exists")

    paid_or_affiliate = brief.affiliate or brief.fee_cad > 0
    if paid_or_affiliate and not brief.disclosure_in_post.strip():
        reasons.append(f"a paid or affiliate arrangement carries its disclosure in "
                       f"{DISCLOSURE_IN}")
    elif paid_or_affiliate and not _says_what_it_is(brief.disclosure_in_post):
        reasons.append(
            f"the disclosure does not say what it is. A reader has to be able to tell this "
            f"is a commercial arrangement from the words in front of them: "
            f"{list(DISCLOSURE_MARKERS)}")

    return {
        "creator_ref": brief.creator_ref, "ok": not reasons, "reasons": reasons,
        "asks_for": list(brief.deliverables),
        "never_asks_for": list(NEVER_A_DELIVERABLE),
        "disclosure_goes_in": DISCLOSURE_IN,
        "note": ("this collaboration buys work and nothing else" if not reasons else
                 f"{len(reasons)} reason(s) this may not be offered as written"),
    }


def may_use(creator: Creator, *, asset_ref: str, scope: str,
            today: date | None = None) -> dict:
    """Whether an asset may be used for this purpose today, from a recorded permission."""
    if scope not in SCOPES:
        raise CreatorRefused(f"{scope!r} is not a permission scope: {list(SCOPES)}")
    today = today or date.today()

    matching = [p for p in creator.permissions
                if p.asset_ref == asset_ref and p.scope == scope]
    # A live permission wins over an expired one for the same asset and scope. Returning
    # whichever was recorded first would refuse a use somebody has actually been granted,
    # because a renewal is a second row rather than an edit to the first.
    live = [p for p in matching
            if p.expires_on is None or today < p.expires_on]
    if live:
        chosen = max(live, key=lambda p: (p.expires_on is None, p.expires_on or p.granted_on))
        return {"may_use": True, "ref": chosen.ref, "scope": scope,
                "why": f"recorded permission {chosen.ref} covers {scope}"}
    if matching:
        last = max(matching, key=lambda p: p.expires_on)
        return {"may_use": False, "ref": last.ref,
                "why": (f"permission expired on {last.expires_on.isoformat()}. An expired "
                        f"permission is refused like an absent one, because the asset does "
                        f"not become ours by being old")}

    other = sorted({p.scope for p in creator.permissions if p.asset_ref == asset_ref})
    return {
        "may_use": False, "ref": None,
        "why": (f"no recorded permission for {scope}"
                + (f"; this asset is permitted for {other}, which is a different question. "
                   f"A photograph licensed for somebody's own channel is not licensed for "
                   f"our listing" if other else
                   ". Absent permission is not implied permission")),
    }


def outreach_gate(creator: Creator, message: dict, *, relevant_to_their_business: bool,
                  today: date | None = None) -> dict:
    """Whether this company may write to a creator it has no relationship with.

    An approach to a creator is a commercial electronic message, so CASL decides it. The
    basis is the conspicuously-published business address, and its two conditions are facts
    about the creator rather than about our list -- which is why they are checked here, where
    those facts are recorded, and the message requirements are delegated to `growth.owned`
    rather than restated.
    """
    blocks: list[str] = []
    if not creator.address_published:
        blocks.append("no conspicuously published business address, so there is no implied "
                      "consent to rely on and nothing else has been given")
    if creator.address_refuses_unsolicited:
        blocks.append("the published address carries a statement refusing unsolicited "
                      "messages, which removes the basis entirely")
    if not relevant_to_their_business:
        blocks.append("the message is not relevant to the business capacity the address was "
                      "published in, and relevance is a condition rather than a courtesy")

    missing = owned.check_message(message)
    return {
        "creator_ref": creator.ref,
        "sendable": not blocks and not missing,
        "basis": owned.IMPLIED_PUBLISHED,
        "means": owned.BASES[owned.IMPLIED_PUBLISHED],
        "blocked_by": blocks,
        "missing_from_message": missing,
        "screen_not_clearance": (
            "these are the rules a careful sender follows, encoded so a send cannot skip "
            "them. Passing this screen is not legal advice and is not clearance"),
    }


def shortlist(creators: list[Creator], *, pod: str, limit: int = 5) -> dict:
    """Who on the roster fits this department, ordered by what they have actually done.

    Ordered by delivery rather than by audience, which is the whole argument of the roster:
    the largest following on the list has delivered nothing until it has.
    """
    if pod not in POD_KEYS:
        raise CreatorRefused(f"{pod!r} is not a department: {list(POD_KEYS)}")
    fits = [c for c in creators if c.fits(pod)]
    ranked = sorted(fits, key=lambda c: (-c.delivered, -c.reliability, c.ref))
    untested = [c.ref for c in fits if c.invited < 2]
    return {
        "pod": pod,
        "shortlist": [c.to_dict() for c in ranked[:limit]],
        "fits": len(fits), "on_roster": len(creators),
        "not_yet_demonstrated": untested,
        "ordered_by": ("delivered work, then reliability. Not audience: the largest "
                       "following on a roster has delivered nothing until it has"),
        "note": ("no creator on this roster works in this department, which is a gap in the "
                 "roster rather than a property of the department"
                 if not fits else ""),
    }


@dataclass
class Outcome:
    """What one completed collaboration produced. `None` is unmeasured, never zero."""

    creator_ref: str
    usable_assets: int = 0
    attributable_sessions: int | None = None
    conversions: int | None = None
    support_cases: int | None = None
    spend_cad: float = 0.0
    measured_on: date | None = None

    def unmeasured(self) -> list[str]:
        out = [name for name, value in (("attributable_sessions", self.attributable_sessions),
                                        ("conversions", self.conversions),
                                        ("support_cases", self.support_cases))
               if value is None]
        if self.measured_on is None:
            out.append("measured_on")
        return out


def may_scale(outcomes: list[Outcome]) -> dict:
    """#21's gate: measure attributable traffic, conversion, proof and support first.

    The refusal that matters is the quiet one. An outcome nobody measured reads as a zero to
    any arithmetic that averages it, and a roster scaled on "no bad news" is the same defect
    as a release passed by the absence of a complaint. Unmeasured is named and blocks.
    """
    reasons: list[str] = []
    if len(outcomes) < MIN_COLLABORATIONS_BEFORE_SCALING:
        reasons.append(
            f"{len(outcomes)} completed collaboration(s) against a floor of "
            f"{MIN_COLLABORATIONS_BEFORE_SCALING}: two is a coincidence")

    unmeasured = {o.creator_ref: o.unmeasured() for o in outcomes if o.unmeasured()}
    for ref, fields in unmeasured.items():
        reasons.append(
            f"{ref} has {fields} unmeasured. An unmeasured outcome is not a zero, and "
            f"averaging it as one is how creator spend scales on no bad news")

    assets = sum(o.usable_assets for o in outcomes)
    spend = round(sum(o.spend_cad for o in outcomes), 2)
    return {
        "may_scale": not reasons,
        "reasons": reasons,
        "completed": len(outcomes),
        "usable_proof_assets": assets,
        "spend_so_far_cad": spend,
        "unmeasured": unmeasured,
        "floor": MIN_COLLABORATIONS_BEFORE_SCALING,
        "note": ("measured, and the arrangement can grow" if not reasons else
                 "creator spend does not scale on this evidence"),
    }


@dataclass(frozen=True)
class Relationship:
    """One creator relationship, as a portfolio position rather than an outreach event."""

    creator_ref: str
    collaborations: int = 0
    spend_cad: float = 0.0
    contribution_cad: float | None = None      # None is unmeasured, never zero
    usable_assets: int = 0
    support_cases: int | None = None

    def measured(self) -> bool:
        return self.contribution_cad is not None and self.support_cases is not None


def classify(relationship: Relationship) -> dict:
    """Where this relationship stands, or that nothing is known about it.

    The requirement's instruction is to scale the high-contribution relationships and stop
    the weak ones, and the trap is in the second half: applied to a roster where most
    relationships are unmeasured, it stops the ones nobody got round to measuring. An
    unmeasured relationship is not a weak one.
    """
    if not relationship.measured():
        missing = [name for name, value in
                   (("contribution_cad", relationship.contribution_cad),
                    ("support_cases", relationship.support_cases)) if value is None]
        return {
            "creator_ref": relationship.creator_ref, "state": UNMEASURED,
            "missing": missing,
            "why": (f"{missing} unmeasured. An unmeasured relationship is not a weak one -- "
                    f"it is a relationship with no evidence, and what it calls for is a "
                    f"measurement rather than an ending"),
            "action": "measure it",
        }
    if relationship.collaborations < MIN_COLLABORATIONS_FOR_A_RECORD:
        return {
            "creator_ref": relationship.creator_ref, "state": HOLD,
            "why": (f"{relationship.collaborations} collaboration(s): one good collaboration "
                    f"is a good collaboration, and a track record needs more than one"),
            "action": "work together again before deciding",
        }

    spend = relationship.spend_cad
    per_dollar = (relationship.contribution_cad / spend) if spend else None
    if per_dollar is None:
        # Free seeding: there is no spend to divide by, so the question is whether it
        # produced anything at all rather than what it returned.
        state = SCALE if relationship.usable_assets else STOP
        why = (f"{relationship.usable_assets} usable proof asset(s) at no cost"
               if relationship.usable_assets else
               "no spend and nothing produced, over a track record")
    elif per_dollar >= STRONG_ABOVE:
        state, why = SCALE, f"CA${per_dollar:.2f} of contribution per dollar spent"
    elif per_dollar < WEAK_BELOW:
        state, why = STOP, (f"CA${per_dollar:.2f} per dollar over "
                            f"{relationship.collaborations} collaborations, below "
                            f"CA${WEAK_BELOW:.2f}")
    else:
        state, why = HOLD, f"CA${per_dollar:.2f} per dollar: neither a win nor a loss yet"

    return {"creator_ref": relationship.creator_ref, "state": state, "why": why,
            "contribution_per_dollar": None if per_dollar is None else round(per_dollar, 3),
            "action": {SCALE: "do more of this", HOLD: "one more, then decide",
                       STOP: "end it kindly"}[state]}


def portfolio(relationships: list[Relationship]) -> dict:
    """The roster as a portfolio, with the unmeasured named rather than sorted to the bottom.

    Sorting unmeasured relationships to the bottom of a contribution ranking is how they get
    cut: the bottom of the list is where things are cut from, and a null sorts there.
    """
    cards = [classify(r) for r in relationships]
    by_state: dict[str, list[str]] = {}
    for card in cards:
        by_state.setdefault(card["state"], []).append(card["creator_ref"])
    return {
        "positions": cards,
        "by_state": {k: sorted(v) for k, v in sorted(by_state.items())},
        "measured": sum(1 for c in cards if c["state"] != UNMEASURED),
        "of": len(cards),
        "note": ("nothing on this roster has been measured, so nothing is scaled and nothing "
                 "is stopped. That is the correct output, not an empty one: the instruction "
                 "to stop weak relationships would otherwise stop the unmeasured ones"
                 if cards and all(c["state"] == UNMEASURED for c in cards) else ""),
    }


@dataclass(frozen=True)
class Graduation:
    """A tester being offered a different relationship, and the terms of both (#250)."""

    tester_ref: str
    invited: int
    delivered: int
    testing_terms: str
    ambassador_terms: str
    consent_ref: str = ""              # recorded, separate, revocable
    same_agreement: bool = False


def may_graduate(graduation: Graduation) -> dict:
    """Whether a tester may become an ambassador, and what must stay separate if they do.

    This is where two honest programmes quietly merge into one dishonest one. A tester is
    paid, or given a sample, to find what is wrong; an ambassador is given a relationship for
    saying what is good. Under one agreement the test fee becomes a review fee -- and the
    testing stops working, because a tester whose standing depends on enthusiasm reports
    fewer defects, and the physical sample is the most expensive signal this company buys.
    """
    reasons: list[str] = []

    reliability = (graduation.delivered / graduation.invited) if graduation.invited else 0.0
    if graduation.invited < 2 or reliability < RELIABLE_AT:
        reasons.append(
            f"{graduation.delivered} of {graduation.invited} tests delivered. A tester who "
            f"has not demonstrated reliability is not a high-performing one, and never "
            f"having been asked is neither")

    if graduation.same_agreement:
        reasons.append(
            "one agreement covers both. Testing compensation and public advocacy have to be "
            "separate documents, because under one the test fee is a review fee")

    lowered = graduation.testing_terms.lower()
    found = sorted({w for w in PUBLIC_IN_TESTING_TERMS if w in lowered})
    if found:
        reasons.append(
            f"the testing terms mention {found}. Testing terms that reach for anything "
            f"public make the fee contingent on it, whatever the sentence around it says")

    if not graduation.consent_ref.strip():
        reasons.append(
            "no recorded consent to the second relationship. Consent to test is not consent "
            "to advocate, and a tester who is simply moved across was never asked")

    return {
        "tester_ref": graduation.tester_ref, "may_graduate": not reasons,
        "reasons": reasons,
        "terms": {
            "separate_agreements": True,
            "reporting_a_defect_costs_nothing": (
                "a tester who reports a defect keeps their standing and their fee. This is a "
                "term rather than a courtesy, because a testing programme whose participants "
                "are rewarded for enthusiasm stops finding defects"),
            "revocable": "consent to advocate can be withdrawn without affecting testing work",
        },
        "note": ("graduation is allowed, and the two relationships stay two"
                 if not reasons else f"{len(reasons)} reason(s) this graduation is refused"),
    }


def roster(db) -> dict:
    """The roster as it actually stands, which today is empty and says so."""
    from sqlalchemy import select

    from ..core.models import CreatorProfile

    rows = list(db.scalars(select(CreatorProfile)))
    return {
        "on_roster": len(rows),
        "creators": [{"ref": r.ref, "specialties": list(r.specialties or []),
                      "invited": r.invited, "delivered": r.delivered,
                      "audience_evidence": r.audience_evidence or "self-reported"}
                     for r in rows],
        "note": ("no creator has been recorded. An empty roster is an empty roster: it is "
                 "not a network whose reliability is zero, and nothing here will treat it "
                 "as one" if not rows else ""),
    }


def state() -> dict:
    """What a collaboration may ask for, and what it may never buy."""
    return {
        "deliverables": dict(DELIVERABLES),
        "never_a_deliverable": list(NEVER_A_DELIVERABLE),
        "sentiment_conditions_refused": [s for s, _ in SENTIMENT_STRINGS],
        "permission_scopes": list(SCOPES),
        "disclosure_goes_in": DISCLOSURE_IN,
        "disclosure_markers": list(DISCLOSURE_MARKERS),
        "never_projected": list(NEVER_PROJECTED),
        "outreach_basis": {"basis": owned.IMPLIED_PUBLISHED,
                           "means": owned.BASES[owned.IMPLIED_PUBLISHED]},
        "scaling_floor": MIN_COLLABORATIONS_BEFORE_SCALING,
        "free_seeding_ceiling_cad": FREE_SEEDING_CEILING_CAD,
        "portfolio_states": [SCALE, HOLD, STOP, UNMEASURED],
        "record_needs_collaborations": MIN_COLLABORATIONS_FOR_A_RECORD,
        "public_words_refused_in_testing_terms": list(PUBLIC_IN_TESTING_TERMS),
        "note": ("A collaboration buys work and never an opinion. The deliverable vocabulary "
                 "has no review in it and no caller can add one, a stated audience stays a "
                 "claim with its source, and a permission is scoped or it is not a "
                 "permission (#9, #21)."),
    }
