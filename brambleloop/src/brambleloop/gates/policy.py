"""Policy and Platform Compliance Gate (Master Plan sections 9, 14, 29).

Holds a veto. Nothing publishes past a policy failure, including on an agent's own say-so --
"no single model can bypass release gates".

The rules here are the ones the owner's directive makes non-negotiable: no deceptive pricing,
no fabricated engagement, no unsupported claims, no protected IP, and no automating away a
human identity check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..cir.compiler import ERROR, WARNING, Finding
from ..cir.model import CIR

POLICY_VERSION = "v1.2"

# Phrases that assert an outcome the shop cannot guarantee, or that manufacture urgency.
_UNSUPPORTED_CLAIM_PATTERNS = [
    (r"\bguarantee[ds]?\b.{0,30}\b(fit|size|result)", "guarantees a fit or result"),
    (r"\bnever\s+fails?\b", "absolute reliability claim"),
    (r"\bbest\s+(?:crochet\s+)?pattern\s+(?:on|in)\b", "unverifiable superlative"),
    (r"\b(?:only|last)\s+\d+\s+left\b", "false scarcity for a digital product"),
    (r"\bsale\s+ends\s+(?:today|tonight|in\s+\d+\s*(?:min|hour))", "manufactured urgency"),
    (r"\bprofessional(?:ly)?\s+tested\b", "testing claim requiring evidence"),
    (r"\bbeginner\s+proof\b", "absolute difficulty claim"),
]

# Protected-IP tripwires. Deliberately blunt: a near-miss here is worth a human look.
_IP_TERMS = [
    "disney", "pixar", "marvel", "pokemon", "pokémon", "hello kitty", "sanrio",
    "nintendo", "mario", "bluey", "peppa pig", "harry potter", "star wars", "grinch",
    "winnie the pooh", "mickey mouse", "baby yoda", "stitch (disney)", "squishmallow",
    "nfl", "nhl", "nba", "taylor swift", "barbie",
]

_DECEPTIVE_PRICING = [
    (r"\b(?:always|permanent(?:ly)?)\s+\d+%\s+off", "perpetual discount"),
    (r"\bwas\s+CA?\$\s?\d+(?:\.\d{2})?\b.{0,20}\bnever\b", "fabricated reference price"),
]


@dataclass
class ListingDraft:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    price_cad: float = 0.0
    compare_at_cad: float | None = None
    is_on_sale: bool = False
    sale_days_running: int = 0


def check_text(text: str, where: str) -> list[Finding]:
    out: list[Finding] = []
    low = text.lower()

    for pattern, why in _UNSUPPORTED_CLAIM_PATTERNS:
        if re.search(pattern, low):
            out.append(Finding(ERROR, "POLICY_UNSUPPORTED_CLAIM",
                               f"{why}: matched {pattern!r}", where))

    for term in _IP_TERMS:
        if term in low:
            out.append(Finding(ERROR, "POLICY_IP_RISK",
                               f"references potentially protected property {term!r}", where))

    for pattern, why in _DECEPTIVE_PRICING:
        if re.search(pattern, low):
            out.append(Finding(ERROR, "POLICY_DECEPTIVE_PRICING", why, where))

    return out


def check_proof_claims(text: str, where: str, proof_states: dict | None) -> list[Finding]:
    """Refuse listing language that claims more proof than the pattern has earned (#8).

    Separate from `_UNSUPPORTED_CLAIM_PATTERNS` because the two answer different questions.
    Those patterns refuse a sentence that is never sayable -- "guaranteed to fit". This
    refuses a sentence that is perfectly sayable *later*: "maker tested" is true the day a
    tester finishes one and false the day before, and no fixed list can tell those apart.

    With no proof position supplied this checks nothing and says nothing, because a listing
    whose pattern nobody looked up is not thereby proved modest.
    """
    if proof_states is None:
        return []
    from ..quality.proof import check_claim

    return [Finding(ERROR, "POLICY_PROOF_OVERCLAIM", refusal["why"], where)
            for refusal in check_claim(text, proof_states)]


# The disclosures `platform_policy.classify` can owe that are about AI. When classify says one
# is owed, the listing must carry that exact sentence -- not a paraphrase, not a keyword.
AI_DISCLOSURE_KEYS: tuple[str, ...] = ("ai_assisted_design", "generated_imagery")


def _ai_disclosure_rule() -> dict:
    """Etsy's Seller Policy rule, with the reading it came from (read_on, basis, url)."""
    from .policy_knowledge import READINGS

    reading = READINGS["seller_policy"]
    for c in reading.conclusions:
        if c.get("rule") == "ai_disclosure_required":
            return {"rule": c["rule"], "text": c["text"], "read_on": reading.read_on,
                    "basis": reading.basis, "url": reading.urls[0]}
    raise KeyError("gates.policy_knowledge seller_policy has no ai_disclosure_required rule")


def check_ai_disclosure(description: str, classification) -> list[Finding]:
    """ERROR for every AI disclosure `classify` owes that the description does not carry.

    `classification` is a `platform_policy.Classification` or its `to_dict()`. The rule is
    sourced: Etsy's Seller Policy as read into `policy_knowledge.READINGS["seller_policy"]`,
    and the finding cites that reading's date and basis so it can be re-examined when the
    reading changes.
    """
    from .platform_policy import DISCLOSURES

    owed = (classification.get("disclosures") if isinstance(classification, dict)
            else getattr(classification, "disclosures", None)) or []
    rule = _ai_disclosure_rule()
    out: list[Finding] = []
    for key in AI_DISCLOSURE_KEYS:
        sentence = DISCLOSURES[key]
        if sentence in owed and sentence not in (description or ""):
            out.append(Finding(
                ERROR, "POLICY_AI_DISCLOSURE_MISSING",
                f"the listing owes the {key} disclosure and does not carry it verbatim: "
                f"{sentence!r}. Source: Etsy Seller Policy ({rule['url']}), "
                f"{rule['rule']} -- \"{rule['text']}\" -- read {rule['read_on']} on basis "
                f"{rule['basis']}", "listing.description"))
    return out


def check_listing(draft: ListingDraft, cir: CIR | None = None,
                  proof_states: dict | None = None,
                  classification=None) -> list[Finding]:
    """Listing-level policy findings.

    `classification` is what `platform_policy.classify` returned for this release. When it
    is supplied and owes an AI disclosure, a description without that exact sentence is an
    ERROR (`check_ai_disclosure`). Without it the older keyword WARNING below still applies,
    because a listing nobody classified is not thereby free of disclosure duties.
    """
    out: list[Finding] = []
    if classification is not None:
        out += check_ai_disclosure(draft.description, classification)
    out += check_text(draft.title, "listing.title")
    out += check_text(draft.description, "listing.description")
    out += check_proof_claims(draft.title, "listing.title", proof_states)
    out += check_proof_claims(draft.description, "listing.description", proof_states)
    for t in draft.tags:
        out += check_text(t, f"listing.tag:{t}")
        out += check_proof_claims(t, f"listing.tag:{t}", proof_states)

    if len(draft.title) > 140:
        out.append(Finding(ERROR, "POLICY_TITLE_LENGTH",
                           f"title is {len(draft.title)} characters; Etsy allows 140",
                           "listing.title"))
    if len(draft.tags) > 13:
        out.append(Finding(ERROR, "POLICY_TAG_COUNT",
                           f"{len(draft.tags)} tags; Etsy allows 13", "listing.tags"))
    for t in draft.tags:
        if len(t) > 20:
            out.append(Finding(ERROR, "POLICY_TAG_LENGTH",
                               f"tag {t!r} exceeds 20 characters", "listing.tags"))

    # A "sale" that never ends is not a sale (section 9: maintain genuine regular prices).
    if draft.is_on_sale and draft.sale_days_running > 45:
        out.append(Finding(ERROR, "POLICY_PERPETUAL_SALE",
                           f"listing has been on sale for {draft.sale_days_running} days; "
                           "this is a regular price, not a promotion", "listing.price"))
    if draft.compare_at_cad is not None and draft.compare_at_cad <= draft.price_cad:
        out.append(Finding(ERROR, "POLICY_BAD_COMPARE_AT",
                           "compare-at price is not above the selling price", "listing.price"))
    if draft.price_cad <= 0:
        out.append(Finding(ERROR, "POLICY_NO_PRICE", "listing has no price", "listing.price"))

    if cir is not None:
        if not cir.gauge:
            out.append(Finding(WARNING, "POLICY_NO_GAUGE",
                               "pattern ships without a gauge; sizing complaints are likely",
                               "pattern"))
        disclosure = "ai" in draft.description.lower() or "assist" in draft.description.lower()
        if not disclosure:
            out.append(Finding(WARNING, "POLICY_NO_AI_DISCLOSURE",
                               "description does not disclose AI assistance in production",
                               "listing.description"))

    return out


def check_originality(name: str, cleared_names: set[str] | None = None) -> list[Finding]:
    """Section 29: do not assume a name is clear because it sounds good."""
    out: list[Finding] = []
    out += check_text(name, "brand.name")
    if cleared_names is not None and name.lower() not in {n.lower() for n in cleared_names}:
        out.append(Finding(
            WARNING, "POLICY_NAME_UNCLEARED",
            f"{name!r} has not been through marketplace/domain/trademark screening",
            "brand.name"))
    return out
