"""Growing the elite panel from evidence: other category leaders, found and observed (#219, #268).

The registry was deliberately never pre-populated, and that was right: a panel of shops
nobody looked at reports a breadth of coverage that does not exist. What it lacked was the
other half -- a way for a shop to *join* from evidence. The C-60 audit found the requirement
parked on purchased benchmarks while other category leaders could be observed today with
the same sanctioned reader that reads MJs, so the purchased-products half is the only part
that genuinely waits on the owner.

**Who counts as a category leader.** A shop whose listings sit in the top `LEADER_TOP` of
the API search index (`intel.serp`, `api_index_score_sort`) for at least `MIN_QUERIES`
distinct target queries. One appearance is one listing doing well; two queries is a shop
that wins in a category. The ranking is the API index's and is directional, and that is
all this needs: it selects whom to *observe*, and observation is what the panel then learns
from. Nothing here scores a shop as good because it ranks.

**What joining means.** A `Benchmark` row (never mandatory, never the anchor) with the
evidence that put it there, its buyer market read from the shop's own Etsy location
(`getShop`), and a catalogue scan through `observe.scan` -- the same reader, the same
deep audit, the same no-copy rules. From that moment `mission_runtime.panel_members` counts
it and `sellers_showing` can find a mechanism in two sellers, which is what lets a standard
move (#220).

**#268.** Candidates outside a market the panel already covers are preferred, so the second
buyer market the cross-border lens needs is observed on the credential already held rather
than waited for. A shop whose location Etsy does not state is registered with an unstated
market -- never assumed American.

No network call happens here without a sanctioned reader; tests inject a recorded one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

LEADER_TOP = 10
MIN_QUERIES = 2
PER_RUN = 2
# Shops whose record is read to learn their market before choosing whom to add.
INSPECT_PER_RUN = 6
DEEP_AUDIT_LIMIT = 10
BACKFILL_LIMIT = 10
KEY_PREFIX = "panel_"

# Etsy's two-letter shop location, mapped onto `commerce.markets` keys.
_US, _CA = "US", "CA"

# Tests set this to a callable returning a recorded reader. Production builds one from the
# credential, or reports honestly that there is none.
READER_FACTORY: Callable | None = None


def market_for(country_iso: str | None) -> str:
    """The `commerce.markets` key for a shop location, or "" when Etsy states none."""
    iso = str(country_iso or "").strip().upper()
    if not iso:
        return ""
    if iso in (_US, _CA):
        return iso
    return "other"


def _key_for(shop_name: str) -> str:
    return (KEY_PREFIX + "".join(ch.lower() for ch in shop_name if ch.isalnum()))[:60]


def candidates(db) -> list[dict]:
    """Shops in the index's top results for two or more target queries, strongest first."""
    from sqlalchemy import select

    from ..core.models import SerpSnapshot
    from . import serp

    pod_of = {t["query"]: t.get("pod") for t in serp.target_queries()}
    newest: dict[str, SerpSnapshot] = {}
    with db.session() as s:
        for row in s.scalars(select(SerpSnapshot).order_by(SerpSnapshot.captured_at)):
            newest[row.query] = row
        by_shop: dict[str, dict] = {}
        for query, row in newest.items():
            for e in row.rank_list or []:
                shop = e.get("shop_id")
                if shop is None or int(e.get("rank") or 999) > LEADER_TOP:
                    continue
                c = by_shop.setdefault(str(shop), {"shop_id": shop, "queries": set(),
                                                   "pods": set(), "favourites": 0,
                                                   "best_rank": 999})
                c["queries"].add(query)
                if pod_of.get(query):
                    c["pods"].add(pod_of[query])
                c["favourites"] += int(e.get("favourites") or 0)
                c["best_rank"] = min(c["best_rank"], int(e.get("rank") or 999))
    out = [{**c, "queries": sorted(c["queries"]), "pods": sorted(c["pods"])}
           for c in by_shop.values() if len(c["queries"]) >= MIN_QUERIES]
    return sorted(out, key=lambda c: (-len(c["queries"]), -c["favourites"], c["best_rank"]))


def _known(db) -> tuple[set[str], set[str]]:
    """Registered shop names (lower-case) and shop ids already on the panel."""
    from sqlalchemy import select

    from ..core.models import Benchmark

    with db.session() as s:
        rows = list(s.scalars(select(Benchmark)))
        return ({r.shop_name.lower() for r in rows},
                {str((r.scan_health or {}).get("shop_id")) for r in rows
                 if (r.scan_health or {}).get("shop_id") is not None})


def _reader(env: dict | None):
    if READER_FACTORY is not None:
        return READER_FACTORY()
    from . import etsy_public

    credential = etsy_public.ReadCredential.from_env(env)
    if credential is None or not credential.complete:
        return None
    from ..integrations.http import UrllibTransport

    return etsy_public.PublicReader(UrllibTransport(), env=env)


def discover(db, *, reader=None, env: dict | None = None, limit: int = PER_RUN,
             now: datetime | None = None) -> dict:
    """Register and scan up to `limit` new category leaders; rescan those already joined."""
    from sqlalchemy import select

    from ..core.models import Benchmark
    from . import benchmarks, observe

    now = now or datetime.now(timezone.utc)
    reader = reader if reader is not None else _reader(env)
    found = candidates(db)
    if reader is None:
        return {"ran": False, "candidates": len(found),
                "reason": ("no sanctioned Etsy read credential, so no category leader can be "
                           "observed; candidates are listed, none is registered unseen")}

    # D-W4-GATESB-1: the company's chosen second-market shops join first, each only after
    # the reader verifies its name and stated location (intel.second_market).
    from . import second_market

    chosen = second_market.ensure_selected(db, reader, now=now)

    names, ids = _known(db)
    covered = set(benchmarks.markets_observed(db))
    inspected: list[dict] = []
    for c in found:
        if len(inspected) >= INSPECT_PER_RUN:
            break
        if str(c["shop_id"]) in ids:
            continue
        try:
            shop = reader.shop(c["shop_id"])
        except Exception as exc:  # noqa: BLE001 - one unreadable shop is skipped, not guessed
            inspected.append({**c, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        name = str(shop.get("shop_name") or "").strip()
        if not name or name.lower() in names:
            continue
        inspected.append({**c, "shop_name": name,
                          "market": market_for(shop.get("shop_location_country_iso"))})
    usable = [c for c in inspected if c.get("shop_name")]
    # #268: a market the panel does not yet cover goes first.
    usable.sort(key=lambda c: (0 if c["market"] and c["market"] not in covered else 1))

    joined: list[dict] = []
    for c in usable[:max(0, limit)]:
        key = _key_for(c["shop_name"])
        with db.session() as s:
            if s.scalar(select(Benchmark).where(Benchmark.key == key)) is None:
                s.add(Benchmark(
                    key=key, shop_name=c["shop_name"], platform="etsy",
                    canonical_url=f"https://www.etsy.com/shop/{c['shop_name']}",
                    mandatory=False, market=c["market"],
                    reason_for_inclusion=(
                        f"category leader discovered from the API search index "
                        f"({'api_index_score_sort'}): top {LEADER_TOP} for "
                        f"{len(c['queries'])} target queries ({', '.join(c['queries'][:4])}); "
                        f"best index rank {c['best_rank']}. Joined to observe, not to copy"),
                    categories=c["pods"], responsible_pods=c["pods"],
                    scan_health={"state": "discovered", "shop_id": c["shop_id"],
                                 "discovered_at": now.isoformat()}))
        joined.append({"key": key, "shop_name": c["shop_name"], "market": c["market"],
                       "queries": c["queries"], "pods": c["pods"]})

    # Scan every discovered member -- the ones joined now and the ones joined before -- so a
    # panel member is observed on a cadence rather than once.
    with db.session() as s:
        members = [(r.key, r.shop_name) for r in s.scalars(select(Benchmark).where(
            Benchmark.mandatory == False, Benchmark.key.like(f"{KEY_PREFIX}%")))]  # noqa: E712
    scanned: list[dict] = []
    for key, name in members:
        try:
            result = observe.scan(db, reader, benchmark_key=key, shop_name=name,
                                  deep_audit_limit=DEEP_AUDIT_LIMIT,
                                  backfill_limit=BACKFILL_LIMIT, env=env)
        except Exception as exc:  # noqa: BLE001 - one member's failure does not end the run
            scanned.append({"key": key, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        scanned.append({"key": key, "listings_known": result.listings_known,
                        "new": len(result.new_listings), "audited": len(result.deep_audited)})

    return {"ran": True, "candidates": len(found), "inspected": len(inspected),
            "joined": joined, "scanned": scanned, "second_market": chosen,
            "markets_observed": benchmarks.markets_observed(db),
            "note": ("category leaders from the API index's top results, observed with the "
                     "same sanctioned reader as the anchor; rank is directional and selects "
                     "whom to observe, never what to copy")}
