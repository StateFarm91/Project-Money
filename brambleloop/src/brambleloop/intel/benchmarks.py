"""The elite benchmark registry, and the one shop the owner named.

Requirements 205, 206, 219, 301. The owner's mandate is unusually specific and unusually
emphatic: *"Do not generalize this requirement into 'watch proven sellers.'"* So the anchor is
stored as a literal, the owner-supplied URL is kept verbatim beside the short canonical route
because #301 requires it in the registry and in acceptance evidence, and the registry is a
table rather than a constant because a benchmark has state -- scan health, coverage freshness,
which pods answer for it.

The part worth being careful about is resolution. #206 says to validate URL health and, if
Etsy changes its routing, resolve the shop's current canonical location **without silently
substituting a different seller**. That is the failure this module is built around: a shop URL
that 404s and a redirect that lands somewhere plausible are the same event to a naive
follower, and the second one quietly re-points the entire mission at a stranger. So resolution
succeeds only when the destination still identifies the same shop, and anything else is a
reported problem rather than a new benchmark.

Nothing here reaches the network by itself. The fetcher is injected, exactly as the Etsy
client's transport is, so the rules are testable and so that an absent capability produces
`unverified` rather than an invented `healthy`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

MJS_KEY = "mjs_off_the_hook_designs"
MJS_SHOP = "MJsOffTheHookDesigns"

# The short canonical route, and the exact URL the owner supplied. Both are stored; #301 says
# the owner-supplied one must remain in the registry and in acceptance evidence, and an
# acceptance test that quotes a tidied-up URL is not quoting the owner's.
MJS_CANONICAL_URL = "https://www.etsy.com/ca/shop/MJsOffTheHookDesigns"
MJS_OWNER_SUPPLIED_URL = (
    "https://www.etsy.com/ca/shop/MJsOffTheHookDesigns?ref=shop_profile&listing;_id=1825269747")

# The categories the mandate names for this shop (#210, #312). Pods are permanent for these
# and are added as catalogue evidence requires -- never removed because a quarter was quiet.
MJS_CATEGORIES = (
    "garments", "blankets", "stockings", "ornaments", "home_decor",
    "bags", "hats", "seasonal_gift",
)

# What a URL has to contain to still be this shop. Matching on the whole URL would fail on
# every legitimate routing change Etsy has ever made; matching on the shop segment is what
# actually identifies the seller.
_SHOP_SEGMENT = re.compile(r"/shop/([A-Za-z0-9_.-]+)")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def shop_segment(url: str) -> str | None:
    m = _SHOP_SEGMENT.search(url or "")
    return m.group(1) if m else None


@dataclass(frozen=True)
class BenchmarkSpec:
    """A benchmark as code declares it. The database row carries its observed state."""

    key: str
    shop_name: str
    canonical_url: str
    owner_supplied_url: str = ""
    mandatory: bool = False
    reason_for_inclusion: str = ""
    categories: tuple[str, ...] = ()
    platform: str = "etsy"

    def to_dict(self) -> dict:
        return {
            "key": self.key, "shop_name": self.shop_name, "platform": self.platform,
            "canonical_url": self.canonical_url,
            "owner_supplied_url": self.owner_supplied_url,
            "mandatory": self.mandatory,
            "reason_for_inclusion": self.reason_for_inclusion,
            "categories": list(self.categories),
        }


MJS = BenchmarkSpec(
    key=MJS_KEY,
    shop_name=MJS_SHOP,
    canonical_url=MJS_CANONICAL_URL,
    owner_supplied_url=MJS_OWNER_SUPPLIED_URL,
    mandatory=True,
    reason_for_inclusion=(
        "Named by the owner as the primary quality and commercial reference, non-negotiable "
        "and top priority (v1.4.3 #301). Not a stand-in for 'proven sellers': this specific "
        "shop, by name."),
    categories=MJS_CATEGORIES,
)

# #219: the anchor is not the only teacher. The panel is deliberately empty of invented
# entries -- a registry pre-populated with shops nobody has looked at would report a breadth
# of coverage that does not exist. Entries join it from evidence.
REGISTRY: tuple[BenchmarkSpec, ...] = (MJS,)


def mandatory() -> list[BenchmarkSpec]:
    return [b for b in REGISTRY if b.mandatory]


# ---------------------------------------------------------------------------
# Resolution and health


UNVERIFIED = "unverified"
HEALTHY = "healthy"
MOVED = "moved"
UNREACHABLE = "unreachable"
WRONG_SHOP = "wrong_shop"


@dataclass(frozen=True)
class Resolution:
    """Where a benchmark actually lives now, or why that could not be established."""

    key: str
    state: str
    url: str
    checked_at: datetime | None = None
    problem: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Whether the mission may point at this URL. `moved` is usable; `wrong_shop` never."""
        return self.state in (HEALTHY, MOVED)

    def to_dict(self) -> dict:
        return {"key": self.key, "state": self.state, "url": self.url,
                "usable": self.usable, "problem": self.problem,
                "checked_at": self.checked_at.isoformat() if self.checked_at else None,
                **({"detail": self.detail} if self.detail else {})}


# A fetcher takes a URL and returns (status, final_url). Injected so this module never opens a
# socket on its own and so the interesting cases -- a redirect to a different seller, a 404,
# a transport that raises -- are all reachable in a test.
Fetcher = Callable[[str], "tuple[int, str]"]


def resolve(spec: BenchmarkSpec, fetch: Fetcher | None = None) -> Resolution:
    """Confirm the benchmark still resolves to the shop the owner named.

    Without a fetcher the answer is `unverified`, which is the honest state for a system that
    has no browser capability yet (#224). It is deliberately not `healthy`: a registry that
    reports health it never checked is worse than one that reports nothing, because the
    mission dashboard is believed.
    """
    if fetch is None:
        return Resolution(spec.key, UNVERIFIED, spec.canonical_url,
                          problem="no observation capability is configured, so the URL has "
                                  "not been checked")
    try:
        status, final_url = fetch(spec.canonical_url)
    except Exception as e:  # noqa: BLE001 - a transport failure is a health result, not a crash
        return Resolution(spec.key, UNREACHABLE, spec.canonical_url, _utcnow(),
                          problem=f"{type(e).__name__}: {e}")

    if status >= 400:
        return Resolution(spec.key, UNREACHABLE, spec.canonical_url, _utcnow(),
                          problem=f"HTTP {status}", detail={"status": status})

    landed = shop_segment(final_url)
    if landed is None:
        # A redirect to a search page, a category or the marketplace home. Plausible-looking
        # and not this shop, which is exactly the substitution #206 forbids.
        return Resolution(spec.key, WRONG_SHOP, spec.canonical_url, _utcnow(),
                          problem=f"resolved to {final_url!r}, which does not identify a shop",
                          detail={"final_url": final_url})
    if landed.lower() != spec.shop_name.lower():
        return Resolution(spec.key, WRONG_SHOP, spec.canonical_url, _utcnow(),
                          problem=(f"resolved to shop {landed!r}, which is not "
                                   f"{spec.shop_name!r}. The benchmark is not re-pointed: a "
                                   f"different seller is a different benchmark and needs the "
                                   f"owner, not a redirect"),
                          detail={"final_url": final_url, "landed_shop": landed})

    if final_url.rstrip("/") != spec.canonical_url.rstrip("/"):
        return Resolution(spec.key, MOVED, final_url, _utcnow(),
                          problem="", detail={"was": spec.canonical_url})
    return Resolution(spec.key, HEALTHY, final_url, _utcnow())


# ---------------------------------------------------------------------------
# Persistence


def seed(db) -> list[str]:
    """Write the declared benchmarks into the registry, reconciling what code owns.

    Same discipline as the agent registry: the code is the source of truth for identity, URLs
    and mandate, and observed state -- scan health, freshness timestamps -- belongs to the
    running system and is never overwritten by a deploy.
    """
    from sqlalchemy import select

    from ..core.models import Benchmark

    changes: list[str] = []
    declared = ("shop_name", "platform", "canonical_url", "owner_supplied_url",
                "mandatory", "reason_for_inclusion")
    with db.session() as s:
        for spec in REGISTRY:
            row = s.scalar(select(Benchmark).where(Benchmark.key == spec.key))
            if row is None:
                s.add(Benchmark(key=spec.key, shop_name=spec.shop_name,
                                platform=spec.platform,
                                canonical_url=spec.canonical_url,
                                owner_supplied_url=spec.owner_supplied_url,
                                mandatory=spec.mandatory,
                                reason_for_inclusion=spec.reason_for_inclusion,
                                categories=list(spec.categories),
                                responsible_pods=list(spec.categories),
                                scan_health={"state": UNVERIFIED}))
                changes.append(f"created {spec.key}")
                continue
            for field_name in declared:
                current, want = getattr(row, field_name), getattr(spec, field_name)
                if current != want:
                    setattr(row, field_name, want)
                    changes.append(f"{spec.key}.{field_name} updated")
            if list(row.categories or []) != list(spec.categories):
                row.categories = list(spec.categories)
                changes.append(f"{spec.key}.categories updated")
    return changes


def record_resolution(db, resolution: Resolution) -> None:
    from sqlalchemy import select

    from ..core.models import Benchmark

    with db.session() as s:
        row = s.scalar(select(Benchmark).where(Benchmark.key == resolution.key))
        if row is None:
            return
        row.scan_health = resolution.to_dict()
        if resolution.checked_at is not None:
            row.last_scan_at = resolution.checked_at
        # A `moved` result updates where we look. A `wrong_shop` result never does.
        if resolution.state == MOVED:
            row.canonical_url = resolution.url
