"""The company's choice of second-market benchmark shops (#268; gate second_market_benchmark).

DECISION_LOG B-482/B-508 make this a choice of shop -- "no credential, no capability, no
spend" -- and nothing in the Final Master reserves it to the owner, so the company chose
(D-W4-GATESB-1). The choice is evidence-ranked and still verified before it counts:

* each candidate carries the public evidence it was chosen on (stated location, lifetime
  sales, years on Etsy, catalogue type), dated and labelled as a search-index reading -- a
  claim about the shop, not an observation by this system;
* `ensure_selected` joins a candidate to the panel only after the sanctioned Etsy reader
  resolves the exact shop name and its own `getShop` record states a location in a market
  the panel does not yet cover. A candidate whose record says otherwise is refused and the
  reason recorded; nothing is registered on the search snippet alone;
* the gate still opens only on observed listings (`executor._second_market_observed`), which
  the panel scan writes on the existing credential. A registered shop nobody has read is not
  a market observed.

Competitor research is demand and merchandising intelligence only: listings are observed
through the same sanctioned reader as the anchor, never copied.
"""
from __future__ import annotations

from datetime import datetime, timezone

DECISION_ID = "D-W4-GATESB-1"

# Ranked. Evidence read 2026-10-07 from search-engine index snippets of the shops' public
# Etsy pages (Etsy itself answers 403 to automated page readers; B-268).
CANDIDATES: tuple[dict, ...] = (
    {"shop_name": "LakesideLoops", "expected_market": "CA",
     "evidence": {"stated_location": "Fredericton, New Brunswick, Canada",
                  "lifetime_sales": 86500, "years_on_etsy": 12,
                  "catalogue": "modern crochet patterns (digital PDF)",
                  "source": "web search index snippet of etsy.com/shop/LakesideLoops",
                  "read_on": "2026-10-07", "basis": "search_index_snippet"},
     "why": ("the strongest Canadian crochet-pattern shop found (~86.5k sales, ~19x the next "
             "Canadian candidate). Canada is this company's home market and the one #268 "
             "most needs separated from the US anchor: same US stitch terms, different "
             "holidays (Thanksgiving six weeks apart), CAD pricing")},
    {"shop_name": "HanJanCrochet", "expected_market": "other",
     "evidence": {"stated_location": "United Kingdom",
                  "lifetime_sales": 103768, "years_on_etsy": 14,
                  "catalogue": "crochet patterns by designer Hannah Cross (digital PDF)",
                  "source": "web search index snippet of etsy.com/shop/HanJanCrochet; also "
                            "already cited as a price-band source in radar/market.py",
                  "read_on": "2026-10-07", "basis": "search_index_snippet"},
     "why": ("the strongest UK crochet-pattern shop found (~104k sales); covers the 'other' "
             "market #268 names, where UK stitch terms make the same words a different "
             "fabric. Second because the home market is the larger blind spot")},
)
# Ranked alternates kept for the record (smaller evidence; not registered).
ALTERNATES: tuple[dict, ...] = (
    {"shop_name": "PippaPatternsCrochet", "market": "other", "lifetime_sales": 84107},
    {"shop_name": "NikByDesign", "market": "CA", "lifetime_sales": 4500},
    {"shop_name": "CrochetPatternHouse", "market": "CA", "lifetime_sales": 2700},
)


def ensure_selected(db, reader, *, now: datetime | None = None) -> list[dict]:
    """Verify and join the chosen shops to the panel; idempotent. Returns one record each."""
    from sqlalchemy import select

    from ..core.models import Benchmark
    from . import benchmarks, panel_discovery

    now = now or datetime.now(timezone.utc)
    out: list[dict] = []
    covered = set(benchmarks.markets_observed(db))
    for cand in CANDIDATES:
        name = cand["shop_name"]
        key = panel_discovery._key_for(name)
        with db.session() as s:
            if s.scalar(select(Benchmark).where(Benchmark.key == key)) is not None:
                out.append({"shop_name": name, "key": key, "state": "already_joined"})
                continue
        try:
            found = reader.resolve_shop(name)
            record = reader.shop(found["shop_id"])
        except Exception as exc:  # noqa: BLE001 - unverified is not joined
            out.append({"shop_name": name, "state": "unverified",
                        "why": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        if str(record.get("shop_name") or "").lower() != name.lower():
            out.append({"shop_name": name, "state": "refused",
                        "why": "Etsy's record names a different shop; not re-pointed"})
            continue
        market = panel_discovery.market_for(record.get("shop_location_country_iso"))
        if not market or market in covered or market != cand["expected_market"]:
            out.append({"shop_name": name, "state": "refused", "observed_market": market,
                        "why": (f"Etsy states market {market or 'none'!r}; chosen for "
                                f"{cand['expected_market']!r} outside the covered "
                                f"{sorted(covered)} -- the record wins over the snippet")})
            continue
        with db.session() as s:
            s.add(Benchmark(
                key=key, shop_name=name, platform="etsy",
                canonical_url=f"https://www.etsy.com/shop/{name}", mandatory=False,
                market=market,
                reason_for_inclusion=(f"{DECISION_ID}: second-market benchmark chosen by the "
                                      f"company for #268. {cand['why']}. Evidence: "
                                      f"{cand['evidence']['source']} "
                                      f"({cand['evidence']['read_on']}); location verified "
                                      f"by getShop. Joined to observe, not to copy"),
                categories=[], responsible_pods=[],
                scan_health={"state": "discovered", "shop_id": found["shop_id"],
                             "discovered_at": now.isoformat(), "decision": DECISION_ID}))
        out.append({"shop_name": name, "key": key, "state": "joined", "market": market})
    return out


def state() -> dict:
    return {"decision": DECISION_ID, "candidates": list(CANDIDATES),
            "alternates": list(ALTERNATES),
            "opens_gate_when": "observed listings exist for two or more distinct markets"}
