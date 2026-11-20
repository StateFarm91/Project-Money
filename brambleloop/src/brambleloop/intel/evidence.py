"""F-407: one source hierarchy for every piece of outside evidence.

`intel.childrens.Source` recorded how a source was retrieved and its jurisdiction, for the
children's-safety sources only. Everything else -- `intel.learning` observations and the
platform-policy readings -- carried a URL and nothing that said whether it was the rule-maker
itself or somebody's summary of it. This module is the shared vocabulary:

* **retrieval class** -- how we came by it (`fetched`, `search_summary`, `rendered_image`,
  `repository`, `api`); the values are the ones `intel.childrens` already uses;
* **authority tier** -- `primary` (the rule-maker, regulator, platform or standard itself,
  or this company's own measured rows), `secondary` (reputable reporting, reproductions of
  primary text, industry guides) or `community` (forums, social, blogs);
* a URL whose tier cannot be determined is `unclassified`, never promoted to primary.

`rank` orders sources primary first, and `conflict` says which side wins when a primary and a
lower tier disagree (the primary, always). Pure functions; no network.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlparse

FETCHED = "fetched"
SEARCH_SUMMARY = "search_summary"
RENDERED_IMAGE = "rendered_image"
REPOSITORY = "repository"
API = "api"
INTERNAL = "internal"          # this company's own rows (intel.research)
RETRIEVAL_CLASSES = (FETCHED, SEARCH_SUMMARY, RENDERED_IMAGE, REPOSITORY, API, INTERNAL)

PRIMARY = "primary"
SECONDARY = "secondary"
COMMUNITY = "community"
UNCLASSIFIED = "unclassified"
TIER_ORDER = {PRIMARY: 0, SECONDARY: 1, COMMUNITY: 2, UNCLASSIFIED: 3}

# Host suffix -> tier. The longest matching suffix wins.
_HOSTS: dict[str, str] = {
    # regulators and law
    ".gov": PRIMARY, ".gc.ca": PRIMARY, "canada.ca": PRIMARY, "europa.eu": PRIMARY,
    "legislation.gov.uk": PRIMARY, "ecfr.gov": PRIMARY, "laws-lois.justice.gc.ca": PRIMARY,
    "crtc.gc.ca": PRIMARY, "fightspam.gc.ca": PRIMARY, "iso.org": PRIMARY, "astm.org": PRIMARY,
    # platforms and providers, on their own policy/developer pages
    "etsy.com": PRIMARY, "help.etsy.com": PRIMARY, "developers.etsy.com": PRIMARY,
    "openapi.etsy.com": PRIMARY, "anthropic.com": PRIMARY, "docs.anthropic.com": PRIMARY,
    "pinterest.com": PRIMARY, "policy.pinterest.com": PRIMARY,
    "wikimedia.org": PRIMARY,       # the pageview API is the measurement itself
    # reproductions and reputable secondary
    "law.cornell.edu": SECONDARY, "wikipedia.org": SECONDARY, "craftyarncouncil.com": SECONDARY,
    "ravelry.com": SECONDARY, "marketplace.etsy.com": SECONDARY,
    # community
    "reddit.com": COMMUNITY, "community.etsy.com": COMMUNITY, "facebook.com": COMMUNITY,
    "medium.com": COMMUNITY, "quora.com": COMMUNITY, "x.com": COMMUNITY,
    "twitter.com": COMMUNITY, "tiktok.com": COMMUNITY, "youtube.com": COMMUNITY,
}


class EvidenceRefused(ValueError):
    """An unknown retrieval class or tier."""


def tier_for(url_or_ref: str) -> str:
    ref = (url_or_ref or "").strip()
    if ref.startswith(("repo:", "db:", "audit_log", "company_memory:")):
        return PRIMARY          # this company's own recorded rows
    host = (urlparse(ref).hostname or "").lower()
    if not host:
        return UNCLASSIFIED
    best, tier = -1, UNCLASSIFIED
    for suffix, t in _HOSTS.items():
        s = suffix.lstrip(".")
        if (host == s or host.endswith("." + s) or (suffix.startswith(".")
                                                     and host.endswith(suffix))) \
                and len(suffix) > best:
            best, tier = len(suffix), t
    return tier


@dataclass(frozen=True)
class Source:
    ref: str
    retrieval: str
    tier: str = ""
    jurisdiction: str = ""
    read_on: str = ""

    def __post_init__(self) -> None:
        if self.retrieval not in RETRIEVAL_CLASSES:
            raise EvidenceRefused(f"retrieval {self.retrieval!r} not in {RETRIEVAL_CLASSES}")
        if not self.tier:
            object.__setattr__(self, "tier", tier_for(self.ref))
        if self.tier not in TIER_ORDER:
            raise EvidenceRefused(f"tier {self.tier!r} not in {sorted(TIER_ORDER)}")

    def to_dict(self) -> dict:
        return asdict(self)


def rank(sources: list[Source]) -> list[Source]:
    """Primary first; within a tier, fetched before summarised (a read page beats a quote)."""
    retr = {FETCHED: 0, API: 0, INTERNAL: 0, REPOSITORY: 1, RENDERED_IMAGE: 1, SEARCH_SUMMARY: 2}
    return sorted(sources, key=lambda s: (TIER_ORDER[s.tier], retr.get(s.retrieval, 3), s.ref))


def conflict(a: Source, b: Source) -> dict:
    """Which of two disagreeing sources governs. Equal tiers are an unresolved conflict."""
    if TIER_ORDER[a.tier] == TIER_ORDER[b.tier]:
        return {"governs": None, "why": f"both {a.tier}: unresolved, escalate to a primary read"}
    win = a if TIER_ORDER[a.tier] < TIER_ORDER[b.tier] else b
    return {"governs": win.ref, "why": f"{win.tier} outranks the other source"}
