"""The five business tiers and the permission matrix (spec/07 item 5; D-FB-13).

            read                                  write
owner       all tiers                             all tiers (canonical: owner only)
laura       all tiers                             brand, operational, experience,
                                                  relationship (department/ and context/ keys)
department  canonical, brand, operational,        operational, experience
            experience, relationship (policy/,    (its own entries only)
            preference/, and its own department/)
public      nothing                               nothing
customer    nothing                               nothing

Relationship keys are namespaced: `policy/...` and `preference/...` are owner-approved
policies and preferences (owner writes only); `department/<key>/...` is context about a
department; `context/...` is other business relationship context.
"""
from __future__ import annotations

from .errors import TierRefused

TIERS: tuple[str, ...] = ("canonical", "brand", "operational", "experience", "relationship")

_READ = {
    "owner": set(TIERS),
    "laura": set(TIERS),
    "department": {"canonical", "brand", "operational", "experience", "relationship"},
    "public": set(),
    "customer": set(),
}
_WRITE = {
    "owner": set(TIERS),
    "laura": {"brand", "operational", "experience", "relationship"},
    "department": {"operational", "experience"},
    "public": set(),
    "customer": set(),
}
OWNER_APPROVED_PREFIXES = ("policy/", "preference/")
RELATIONSHIP_PREFIXES = OWNER_APPROVED_PREFIXES + ("department/", "context/")


def check_tier(tier: str) -> str:
    if tier not in TIERS:
        raise TierRefused(f"unknown memory tier {tier!r}; tiers are {TIERS}")
    return tier


def can_read(principal_kind: str, tier: str) -> bool:
    return tier in _READ.get(principal_kind, set())


def can_write(principal_kind: str, tier: str) -> bool:
    return tier in _WRITE.get(principal_kind, set())


def category(tier: str, key: str) -> str:
    if tier != "relationship":
        return tier
    for p in RELATIONSHIP_PREFIXES:
        if key.startswith(p):
            return p.rstrip("/")
    return ""


def relationship_visible_to_department(key: str, department: str) -> bool:
    return key.startswith(OWNER_APPROVED_PREFIXES) or key.startswith(f"department/{department}/")
