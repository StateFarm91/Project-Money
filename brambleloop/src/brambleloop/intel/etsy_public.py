"""The sanctioned read-only route to the benchmark shop.

Requirements 206, 207, 208, 212, 221, 222, 303. The owner approved registering an Etsy
developer application for the MJsOffTheHookDesigns intelligence mission, at CA$0, with three
conditions: current v3 authentication, secrets that stay in the hosting environment, and the
**minimum access the read-only mission needs** — no write or private scopes bought early
because we might want them for our own shop one day.

Those conditions decide the shape of this module.

**Authentication.** Etsy v3 wants `x-api-key: <keystring>:<shared_secret>` on every request.
Not the keystring alone, which is what this codebase had. OAuth is additionally required for
private data and writes — which this module never touches, so it never asks for a token and
has no code path that could send one.

**Minimum scope, enforced rather than intended.** `ALLOWED` lists the exact endpoints the
mission needs, every one of them served by the API key alone according to Etsy's own OpenAPI
specification. A call to anything else raises before a request is built. An allowlist rather
than a policy, because "we only use the public endpoints" is a sentence, and a sentence does
not stop the commit that adds one more.

**Nothing secret leaves.** The credential is read from the environment, never logged, never
audited, never written to evidence, and `__repr__` hides it. Errors carry the endpoint and
the status, never the header.

What the sanctioned API turns out to give, which is more than expected: the full active
catalogue with title, description, price, tags, materials, style, favourites and timestamps;
every listing's gallery image URLs *with Etsy's own per-image hex, hue, saturation, brightness
and black-and-white flag*; videos; reviews; and the shop's own section structure. What it does
not give is the rendered page — badges, sale banners as presented, thumbnail-as-displayed,
cross-sell placement. That gap is reported, never papered over (#224).
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

BASE = "https://openapi.etsy.com"

# Read-only, public, API-key-only. Every path below is marked `api_key`-only in Etsy's
# published OpenAPI specification; none of them requires an OAuth scope.
ALLOWED: dict[str, str] = {
    "find_shops": "/v3/application/shops",
    "get_shop": "/v3/application/shops/{shop_id}",
    "shop_listings": "/v3/application/shops/{shop_id}/listings/active",
    "shop_sections": "/v3/application/shops/{shop_id}/sections",
    "shop_reviews": "/v3/application/shops/{shop_id}/reviews",
    "get_listing": "/v3/application/listings/{listing_id}",
    "listing_images": "/v3/application/listings/{listing_id}/images",
    "listing_videos": "/v3/application/listings/{listing_id}/videos",
    "ping": "/v3/application/openapi-ping",
}

KEYSTRING_VAR = "ETSY_API_KEY"
SECRET_VAR = "ETSY_SHARED_SECRET"

# Etsy's own page cap for the listings endpoint.
PAGE_MAX = 100


class NotConfigured(RuntimeError):
    """No read credential. Not an outage: there is nothing to call."""


class EndpointRefused(RuntimeError):
    """An endpoint outside the mission's minimum read-only scope."""


class ReadFailed(RuntimeError):
    """Etsy refused or could not answer. Carries the status, never the credential."""


class Transport(Protocol):
    def request(self, method: str, url: str, *, headers: dict[str, str],
                body: bytes | None = None, timeout: float = 20.0) -> Any: ...


@dataclass(frozen=True)
class ReadCredential:
    """The keystring and shared secret, from the environment and nowhere else."""

    keystring: str
    shared_secret: str

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "ReadCredential | None":
        e = env if env is not None else os.environ
        keystring = (e.get(KEYSTRING_VAR) or "").strip()
        secret = (e.get(SECRET_VAR) or "").strip()
        if not keystring:
            return None
        return ReadCredential(keystring=keystring, shared_secret=secret)

    def header(self) -> str:
        """`keystring:shared_secret`, per Etsy v3.

        A missing secret is sent as an empty half rather than silently dropped, so Etsy
        refuses it and the error names the real problem. Quietly falling back to the
        keystring alone produces a 401 whose cause is indistinguishable from six others.
        """
        return f"{self.keystring}:{self.shared_secret}"

    @property
    def complete(self) -> bool:
        return bool(self.keystring and self.shared_secret)

    def __repr__(self) -> str:  # pragma: no cover - keeps the secret out of tracebacks
        return "ReadCredential(keystring=***, shared_secret=***)"


def health(env: dict[str, str] | None = None) -> dict:
    """Whether the mission can read, without revealing anything about the credential."""
    e = env if env is not None else os.environ
    keystring = (e.get(KEYSTRING_VAR) or "").strip()
    secret = (e.get(SECRET_VAR) or "").strip()
    return {
        "keystring_set": bool(keystring),
        "shared_secret_set": bool(secret),
        "usable": bool(keystring and secret),
        "variables": [KEYSTRING_VAR, SECRET_VAR],
        "reason": ("" if keystring and secret else
                   "neither variable is set" if not keystring and not secret else
                   f"{SECRET_VAR} is not set; Etsy v3 requires keystring:shared_secret"
                   if keystring else f"{KEYSTRING_VAR} is not set"),
        "scopes_requested": "none — every endpoint used is served by the API key alone",
    }


class PublicReader:
    """Read public marketplace data. Cannot write, cannot authenticate as anybody."""

    def __init__(self, transport: Transport, credential: ReadCredential | None = None,
                 env: dict[str, str] | None = None, base: str = BASE,
                 max_attempts: int = 4, backoff_cap: float = 60.0, sleep=None):
        self.transport = transport
        self.credential = credential or ReadCredential.from_env(env)
        self.base = base
        self.max_attempts = max_attempts
        self.backoff_cap = backoff_cap
        # Injected so a test can prove the backoff without waiting for it.
        self.sleep = sleep or time.sleep
        self.calls: list[str] = []
        self.throttled = 0

    def _headers(self) -> dict[str, str]:
        if self.credential is None:
            raise NotConfigured(
                f"{KEYSTRING_VAR} is not set. The benchmark mission reads public marketplace "
                f"data only and cannot run without it; it is set in the hosting environment, "
                f"never in this repository")
        return {"x-api-key": self.credential.header(), "Accept": "application/json"}

    def get(self, endpoint: str, *, path: dict | None = None,
            query: dict | None = None) -> dict:
        """One read, against one of the mission's allowed endpoints."""
        template = ALLOWED.get(endpoint)
        if template is None:
            raise EndpointRefused(
                f"{endpoint!r} is not in the mission's read-only scope. This client exists to "
                f"read public marketplace data; adding an endpoint is a deliberate change to "
                f"{sorted(ALLOWED)}, not something a call site does")

        url = self.base + template.format(**(path or {}))
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            url = f"{url}?{urllib.parse.urlencode(clean)}"

        # Recorded for the evidence trail: which endpoint, never which credential.
        self.calls.append(f"{endpoint} {template}")
        return self._request_with_retries(endpoint, url)

    def _request_with_retries(self, endpoint: str, url: str) -> dict:
        """One read, retried on rate limits and server faults, refused on our own mistakes.

        Etsy publishes a rate limit and a `Retry-After`; ignoring it is how a client turns a
        throttle into a ban, and a ban on the one shop the owner named is the worst available
        outcome for this mission. A 400 or a 404 is retried zero times, because the same
        request produces the same answer and hammering it is what gets noticed.
        """
        from ..core.resilience import TransientError, classify_http, retry_after_seconds

        last: Exception | None = None
        for attempt in range(self.max_attempts):
            response = self.transport.request("GET", url, headers=self._headers())
            status = getattr(response, "status", None)
            body = getattr(response, "body", None)
            headers = getattr(response, "headers", None) or {}
            if body is None and hasattr(response, "read"):  # pragma: no cover
                body = json.loads(response.read() or b"{}")

            if status is None or status < 400:
                return body or {}

            kind = classify_http(status)
            hint = (f" — Etsy v3 requires x-api-key as keystring:shared_secret; check "
                    f"{SECRET_VAR}" if status in (401, 403) else "")
            last = ReadFailed(f"{endpoint} returned HTTP {status}{hint}")
            if kind is not TransientError:
                raise last
            self.throttled += status == 429
            if attempt + 1 < self.max_attempts:
                self.sleep(retry_after_seconds(headers, attempt, cap=self.backoff_cap))
        raise ReadFailed(
            f"{endpoint} failed {self.max_attempts} times: {last}. Etsy was asked to wait "
            f"and kept refusing; the scan stops rather than continuing to knock")

    # -- the mission's reads ------------------------------------------------

    def resolve_shop(self, shop_name: str) -> dict:
        """Find the named shop, and refuse anything that is not it.

        `findShops` is a search, so it answers with near matches — which is the same hazard as
        following a redirect to a different seller (#206). The mandate names one shop, so an
        exact case-insensitive match is the only acceptable result.
        """
        found = self.get("find_shops", query={"shop_name": shop_name, "limit": 25})
        results = found.get("results") or []
        for shop in results:
            if str(shop.get("shop_name", "")).lower() == shop_name.lower():
                return shop
        raise ReadFailed(
            f"{shop_name!r} was not found exactly. Etsy returned "
            f"{[s.get('shop_name') for s in results][:5]}, and a near match is a different "
            f"seller: the mandate names one shop (#301)")

    def catalogue(self, shop_id: int | str, *, limit: int = PAGE_MAX,
                  max_pages: int = 20) -> list[dict]:
        """Every active listing, paginated. #207 asks for the complete catalogue, not a sample."""
        out: list[dict] = []
        offset = 0
        for _ in range(max_pages):
            page = self.get("shop_listings", path={"shop_id": shop_id},
                            query={"limit": min(limit, PAGE_MAX), "offset": offset})
            results = page.get("results") or []
            out.extend(results)
            count = page.get("count")
            offset += len(results)
            if not results or (count is not None and offset >= int(count)):
                break
        return out

    def listing(self, listing_id: int | str) -> dict:
        return self.get("get_listing", path={"listing_id": listing_id})

    def images(self, listing_id: int | str) -> list[dict]:
        return (self.get("listing_images",
                         path={"listing_id": listing_id}).get("results") or [])

    def videos(self, listing_id: int | str) -> list[dict]:
        return (self.get("listing_videos",
                         path={"listing_id": listing_id}).get("results") or [])

    def reviews(self, shop_id: int | str, *, limit: int = 100) -> list[dict]:
        """Buyer reviews of this shop. Already in the sanctioned endpoint allowlist.

        What this is for is the one thing #2 names that nothing could measure: recurring
        complaints. A review is a buyer describing a problem with a product in this category,
        which is demand intelligence of the most direct kind available -- and it is the only
        route to the `customer_pain` learning domain that does not involve having customers.

        What it is never for is reproducing anybody's words. `complaint_themes` below counts
        classifications, not quotations.
        """
        return (self.get("shop_reviews", path={"shop_id": shop_id},
                         query={"limit": limit}).get("results") or [])

    def sections(self, shop_id: int | str) -> list[dict]:
        return (self.get("shop_sections",
                         path={"shop_id": shop_id}).get("results") or [])


# ---------------------------------------------------------------------------
# What the sanctioned route can and cannot do (#224)
#
# Written from Etsy's published OpenAPI specification rather than from hope, and reported as
# a capability inventory so that the part the API cannot satisfy is a named gap with a
# proposed alternative, never a quietly lowered requirement.

MANDATE_COVERAGE: dict[str, dict] = {
    "resolve_canonical_shop": {
        "requirement": 206, "available": True,
        "how": "findShops with an exact case-insensitive name match; a near match is refused",
    },
    "enumerate_full_catalogue": {
        "requirement": 207, "available": True,
        "how": "findAllActiveListingsByShop, paginated to the shop's own count",
    },
    "listing_text_and_commerce_metadata": {
        "requirement": 208, "available": True,
        "how": "getListing gives title, description, price, tags, materials, style, "
               "when_made, who_made, quantity, favourites and timestamps",
    },
    "gallery_asset_inventory": {
        "requirement": 209, "available": True,
        "how": "getListingImages gives every image URL at four sizes, plus Etsy's own "
               "per-image hex, hue, saturation, brightness and black-and-white flag — which "
               "answers palette and colour-architecture questions with no vision model at all",
    },
    "video_presence": {
        "requirement": 157, "available": True, "how": "getListingVideos"},
    "merchandising_structure": {
        "requirement": 303, "available": True,
        "how": "getShopSections gives the shop's own categorisation, which is stronger "
               "evidence of how they think about their catalogue than our inference is",
    },
    "reputation_context": {
        "requirement": 150, "available": True,
        "how": "getReviewsByShop and getReviewsByListing"},
    "change_detection": {
        "requirement": 212, "available": True,
        "how": "last_modified_timestamp per listing plus a content fingerprint, so unchanged "
               "listings are never reprocessed",
    },
    "image_level_visual_judgement": {
        "requirement": 209, "available": False,
        "gap": "the API gives image URLs and colour statistics, not an opinion about shot "
               "type, composition, styling or thumbnail legibility",
        "alternative": "fetch the public image URL and analyse it with the approved model "
                       "provider — no browser, no scraping, inside the authorised ceiling",
    },
    "rendered_page_presentation": {
        "requirement": 208, "available": False,
        "gap": "badges, sale banners as presented, thumbnail crop as displayed in search, "
               "and cross-sell placement exist only in the rendered page",
        "alternative": "an owner-approved managed cloud browser, roughly CA$40-70 per month. "
                       "Not requested: the API covers the mandate's substance, and this is "
                       "presentation detail. It is recorded as an unmet fraction rather than "
                       "claimed (#224)",
    },
}


def capability_report(env: dict[str, str] | None = None) -> dict:
    available = [k for k, v in MANDATE_COVERAGE.items() if v["available"]]
    gaps = {k: v for k, v in MANDATE_COVERAGE.items() if not v["available"]}
    return {
        "credential": health(env),
        "endpoints_in_scope": sorted(ALLOWED),
        "oauth_scopes_requested": [],
        "covered_by_the_sanctioned_api": available,
        "not_covered": gaps,
        "statement": (
            "Etsy's own OpenAPI specification marks every endpoint above as served by the API "
            "key alone. The mission requests no OAuth scope and has no code path that could "
            "send a token. Two parts of the mandate are not covered by the API: one is "
            "answered by the approved model provider reading public image URLs, and one "
            "needs a browser and is recorded as unmet rather than approximated."),
    }


# ---------------------------------------------------------------------------
# Demonstrated capability
#
# The owner's condition on these credentials: the gate opens from a successful read, not from
# the variables being present. That is the same lesson the model provider taught on the same
# day -- a key that authenticates against an account which cannot serve a request would have
# opened a gate and un-parked work nothing could start. Here the failure mode is narrower and
# real: Etsy v3 refuses the keystring alone with "Shared secret is required in x-api-key
# header", so a half-configured credential is indistinguishable from a working one until
# something actually asks.

PROBE_ENDPOINT = "ping"


def probe(db, *, transport=None, env: dict[str, str] | None = None) -> dict:
    """Make the smallest sanctioned read and record whether it worked.

    The ping endpoint returns an application id and nothing about anybody's shop, so this
    demonstrates capability without reading data the mission has not decided to read yet.
    Nothing about the credential is recorded, in the row or in the failure.
    """
    from ..core.models import AuditLog

    record: dict = {"at": datetime.now(timezone.utc).isoformat(),
                    "endpoint": PROBE_ENDPOINT, "ok": False, "reason": ""}

    credential = ReadCredential.from_env(env)
    if credential is None:
        record["reason"] = f"{KEYSTRING_VAR} is not set"
    elif not credential.complete:
        record["reason"] = (f"{SECRET_VAR} is not set; Etsy v3 refuses the keystring alone "
                            f"with 'Shared secret is required in x-api-key header'")
    else:
        from ..integrations.http import UrllibTransport

        reader = PublicReader(transport or UrllibTransport(), env=env)
        try:
            body = reader.get(PROBE_ENDPOINT)
        except Exception as exc:  # noqa: BLE001 - the reason is the point, whatever it is
            record["reason"] = f"{type(exc).__name__}: {exc}"[:400]
        else:
            record["ok"] = True
            # The application id identifies the developer application, not the credential,
            # and having it in the row is what makes "this worked" checkable later.
            record["application_id"] = body.get("application_id")

    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe",
                       artifact=PROBE_ENDPOINT, detail=record))
    return record


def last_probe(db) -> dict | None:
    """The most recent probe result, or None if nobody has ever tried."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == "etsy.probe")
                              .order_by(desc(AuditLog.id)).limit(1)))
    return dict(rows[0].detail or {}) if rows else None


def usable(db) -> bool:
    """Whether a real sanctioned read has actually succeeded. The gate's condition."""
    state = last_probe(db)
    return bool(state and state.get("ok"))


def capability(db, env: dict[str, str] | None = None) -> dict:
    """What this company can currently read from Etsy, and what that rests on."""
    state = last_probe(db)
    return {
        **health(env),
        "last_probe": state,
        "demonstrated": bool(state and state.get("ok")),
        "note": ("no probe has been run, so whether these credentials can serve a request is "
                 "unknown -- which is not the same as unavailable"
                 if state is None else
                 "a real sanctioned read succeeded, so the mission can observe"
                 if state.get("ok") else
                 f"the last read failed: {str(state.get('reason', ''))[:200]}"),
    }
