"""Benchmark refresh: when the market moves, recommend one strategic purchase (#165).

The library is not frozen at launch. #165 asks for a small number of new benchmarks when a
new category, an unusually strong competitor, a new product format or a major market shift
warrants one -- and for no indiscriminate spending and no duplicate information. The buying
is the owner's (consequential spend); *noticing that a purchase is warranted* is software,
and until C-60 none existed.

Four detectors, each read from rows the running system already writes, each compared with
the previous weekly reading so that "new" means new since last week rather than "present":

* **new category** -- a pod the elite panel now sells into with at least `MIN_LISTINGS`
  observed listings that the previous reading did not have;
* **strong competitor** -- a category leader (`panel_discovery.candidates`) in the index's
  top results for at least `STRONG_QUERIES` target queries whose products the library holds
  none of;
* **new format** -- a product form (`prospecting.arena_forms`) observed in a pod that the
  previous reading did not have;
* **market shift** -- a target query whose API index result count moved by `SHIFT_COUNT`
  or whose top results turned over by `SHIFT_TURNOVER` between its two newest snapshots.

A trigger whose pod, form or seller is already covered by a purchased `BenchmarkProduct`
is dropped as duplicate information. What survives becomes at most `MAX_OPEN` open owner
actions (never more, whatever fires), each naming the one listing `purchase_selection`
picks for it and its observed price as the maximum cost. The first reading is a baseline:
it records what exists and recommends nothing, because on day one everything is "new".
"""
from __future__ import annotations

from datetime import date, datetime, timezone

KIND = "benchmark.refresh"
ACTION_PREFIX = "benchmark_refresh:"
MIN_LISTINGS = 5
STRONG_QUERIES = 3
SHIFT_COUNT = 0.30
SHIFT_TURNOVER = 0.50
MAX_OPEN = 2


def _pods_and_forms(db) -> tuple[dict[str, int], dict[str, list[str]]]:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..creative import prospecting

    with db.session() as s:
        rows = [(r.benchmark_key, r.pod) for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.audit_state != "withdrawn")) if r.pod]
    counts: dict[str, int] = {}
    keys_by_pod: dict[str, set] = {}
    for key, pod in rows:
        counts[pod] = counts.get(pod, 0) + 1
        keys_by_pod.setdefault(pod, set()).add(key)
    forms: dict[str, list[str]] = {}
    for pod, keys in keys_by_pod.items():
        found: set[str] = set()
        for key in keys:
            found |= set((prospecting.arena_forms(db, pod, benchmark_key=key).get("forms")
                          or {}).keys())
        forms[pod] = sorted(found)
    return counts, forms


def _previous(db, today: date) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND,
            OperatingReading.period_key < today.isoformat())
            .order_by(desc(OperatingReading.period_key)).limit(1))
        return dict(row.payload or {}) if row is not None else None


def _library(db) -> tuple[set[str], set[str]]:
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkProduct)))
        return {r.pod for r in rows if r.pod}, {r.seller.lower() for r in rows if r.seller}


def _market_shifts(db) -> list[dict]:
    from . import serp

    out = []
    for query in serp.queries_captured(db):
        ch = serp.changes(db, query, top=10)
        if not ch.get("comparable"):
            continue
        before, after = ch.get("count_from"), ch.get("count_to")
        count_move = (abs(after - before) / before) if before and after is not None else None
        turnover = len(ch["entrants"]) / 10.0
        if (count_move is not None and count_move >= SHIFT_COUNT) or turnover >= SHIFT_TURNOVER:
            out.append({"query": query, "count_from": before, "count_to": after,
                        "count_move": round(count_move, 3) if count_move is not None else None,
                        "top10_turnover": round(turnover, 3)})
    return out


def _pick(db, pod: str) -> dict | None:
    """The one listing `purchase_selection` would buy to cover this pod, with its price."""
    from sqlalchemy import func, select

    from ..core.models import BenchmarkListing
    from . import purchase_selection

    with db.session() as s:
        key = s.scalar(select(BenchmarkListing.benchmark_key).where(
            BenchmarkListing.pod == pod).group_by(BenchmarkListing.benchmark_key)
            .order_by(func.count(BenchmarkListing.id).desc()).limit(1))
    if not key:
        return None
    try:
        chosen = purchase_selection.select(db, key, departments=[pod], target=1)
    except purchase_selection.SelectionRefused:
        return None
    if not chosen["selected"]:
        return None
    pick = chosen["selected"][0]
    return {"benchmark": key, "listing_ref": pick["listing_ref"], "title": pick["title"],
            "price_cad": pick["price_cad"], "answers": pick["answers"], "url": pick["url"]}


def assess(db, *, today: date | None = None) -> dict:
    """Detect, de-duplicate against the library, and raise at most `MAX_OPEN` owner actions."""
    from sqlalchemy import select

    from ..core.models import OperatingReading, OwnerAction
    from . import panel_discovery

    today = today or datetime.now(timezone.utc).date()
    counts, forms = _pods_and_forms(db)
    leaders = panel_discovery.candidates(db)
    shifts = _market_shifts(db)
    prev = _previous(db, today)
    lib_pods, lib_sellers = _library(db)

    triggers: list[dict] = []
    if prev is not None:
        old_pods = set(prev.get("pods") or {})
        old_forms = {p: set(v) for p, v in (prev.get("forms") or {}).items()}
        for pod, n in sorted(counts.items()):
            if n >= MIN_LISTINGS and pod not in old_pods:
                triggers.append({"trigger": "new_category", "subject": pod, "pod": pod,
                                 "evidence": f"{n} observed listings in a department the "
                                             f"panel did not sell into last reading"})
        for pod, now_forms in sorted(forms.items()):
            new = sorted(set(now_forms) - old_forms.get(pod, set()))
            if pod in old_pods and new:
                triggers.append({"trigger": "new_format", "subject": f"{pod}:{new[0]}",
                                 "pod": pod, "evidence": f"new form(s) {new} observed in "
                                                         f"{pod}"})
        for q in shifts:
            triggers.append({"trigger": "market_shift", "subject": q["query"],
                             "pod": _pod_of_query(q["query"]),
                             "evidence": (f"API index count {q['count_from']} -> "
                                          f"{q['count_to']}, top-10 turnover "
                                          f"{q['top10_turnover']:.0%}")})
    for c in leaders:
        if len(c["queries"]) >= STRONG_QUERIES:
            triggers.append({"trigger": "strong_competitor", "subject": str(c["shop_id"]),
                             "pod": (c["pods"] or [""])[0], "seller_id": c["shop_id"],
                             "evidence": f"top {panel_discovery.LEADER_TOP} for "
                                         f"{len(c['queries'])} target queries"})

    names_by_shop = _panel_names(db)
    recommendations, duplicates = [], []
    for t in triggers:
        pod = t.get("pod") or ""
        # Duplicate information: a category or a shifted market the library already covers,
        # or a competitor whose product the library already holds. A new *form* is new
        # information even in a covered department, so it is never dropped on the pod alone.
        if t["trigger"] in ("new_category", "market_shift") and pod in lib_pods:
            duplicates.append({**t, "why": f"the library already holds a {pod} benchmark"})
            continue
        seller = names_by_shop.get(str(t.get("seller_id")), "")
        if t["trigger"] == "strong_competitor" and seller and seller.lower() in lib_sellers:
            duplicates.append({**t, "why": f"the library already holds a {seller} product"})
            continue
        if not pod:
            duplicates.append({**t, "why": "no department to buy in"})
            continue
        pick = _pick(db, pod)
        if pick is None:
            duplicates.append({**t, "why": "no observed listing to recommend in " + pod})
            continue
        recommendations.append({**t, "pick": pick})

    raised, held = [], []
    with db.session() as s:
        open_rows = {r.requirement_key: r for r in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{ACTION_PREFIX}%"),
            OwnerAction.done == False))}  # noqa: E712
        # Review OPUS2D R2: one cap across every reference-purchase request, whichever job
        # raised it -- the knowledge-gap job counts these rows too.
        from . import knowledge_gaps as _kg

        gap_open = len(list(s.scalars(select(OwnerAction.id).where(
            OwnerAction.requirement_key.like(f"{_kg.ACTION_PREFIX}%"),
            OwnerAction.done == False))))  # noqa: E712
        for rec in recommendations:
            key = f"{ACTION_PREFIX}{rec['trigger']}:{rec['subject']}"[:200]
            if key in open_rows:
                held.append({"key": key, "why": "already asked; not asked twice"})
                continue
            if len(open_rows) + gap_open >= _kg.MAX_PURCHASE_REQUESTS_OPEN:
                held.append({"key": key, "why": (
                    f"{_kg.MAX_PURCHASE_REQUESTS_OPEN} reference-purchase requests are "
                    f"already open across benchmark refresh and knowledge gaps")})
                continue
            if len(open_rows) >= MAX_OPEN:
                held.append({"key": key, "why": f"{MAX_OPEN} refresh purchases already "
                                                f"open; no indiscriminate spending"})
                continue
            pick = rec["pick"]
            row = OwnerAction(
                requirement_key=key,
                action=(f"Buy one benchmark pattern: {pick['title'][:80]!r} "
                        f"({pick['url']}) for the teardown library"),
                reason=(f"#165 refresh: {rec['trigger'].replace('_', ' ')} -- "
                        f"{rec['evidence']}. It answers: {pick['answers']}"),
                max_cost_cad=round(float(pick["price_cad"] or 0.0), 2), minutes=10,
                consequence_of_delay=("the library keeps teaching last season's market; "
                                      "the recommendation is re-assessed weekly"),
                blocks="165")
            s.add(row)
            open_rows[key] = row
            raised.append({"key": key, "max_cost_cad": row.max_cost_cad,
                           "trigger": rec["trigger"]})

        payload = {"as_of": today.isoformat(), "baseline": prev is None,
                   "pods": counts, "forms": forms,
                   "leaders": [{k: c[k] for k in ("shop_id", "queries", "pods")}
                               for c in leaders[:10]],
                   "shifts": shifts,
                   "triggers": triggers, "duplicates": duplicates,
                   "raised": raised, "held": held}
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=today.isoformat(), payload=payload))
        else:
            row.payload = payload
    return payload


def _panel_names(db) -> dict[str, str]:
    from sqlalchemy import select

    from ..core.models import Benchmark

    with db.session() as s:
        return {str((r.scan_health or {}).get("shop_id")): r.shop_name
                for r in s.scalars(select(Benchmark))
                if (r.scan_health or {}).get("shop_id") is not None}


def _pod_of_query(query: str) -> str:
    from . import serp

    return next((t.get("pod") or "" for t in serp.target_queries() if t["query"] == query), "")


# ---- ENG-BENCHBUY: the daily benchmark shopping list ----------------------------------------
#
# Weekly `assess` above notices that the market moved. This is the daily, standing counterpart:
# after the shop scans it rebuilds the owner's shopping list across all nine watchlist shops
# (`purchase_selection.shopping_list`), stores it as one dated reading, and keeps ONE
# consolidated owner card, "Buy N benchmark patterns, <= CA$X". It reads rows only: no request,
# no purchase, no spend. Buying and the upload of a purchased PDF stay with the owner, and the
# PDF goes through the quarantined teardown intake only (B-117).
SHOPPING_ACTION_KEY = "benchmark_shopping:set"


def _pick_refs(listing: dict) -> list[str]:
    return sorted(str(p["listing_ref"]) for p in listing.get("to_buy") or [])


def refresh_shopping(db, *, today: date | None = None) -> dict:
    """Rebuild the shopping list, store today's reading, keep one owner card in step."""
    from sqlalchemy import select

    from ..core.models import OperatingReading, OwnerAction
    from ..ops import owner_queue
    from . import purchase_selection as ps

    today = today or datetime.now(timezone.utc).date()
    prior = ps.previous_ledger(db)
    listing = ps.shopping_list(db, ledger=prior)
    before = sorted(str(p["listing_ref"]) for p in prior if p.get("status") == "to buy")
    changed = before != _pick_refs(listing)

    n = listing["to_buy_count"]
    cost = listing["total_with_contingency_cad"]
    card = {"state": "none", "key": SHOPPING_ACTION_KEY}
    with db.session() as s:
        open_row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == SHOPPING_ACTION_KEY,
            OwnerAction.done == False))  # noqa: E712
        if n > 0 and listing["status"] == "OK":
            title = f"Buy {n} benchmark patterns, ≤ CA${cost:.2f}"
            shops = listing["shops_with_picks"]
            fields = dict(
                reason=(f"Benchmark shopping list: {n} pattern PDFs across {shops} of "
                        f"{listing['shops_total']} watchlist shops, chosen for the capability "
                        f"gaps and owner-demand families they teach. CA${cost:.2f} includes the "
                        f"x1.158 FX/tax contingency; CA${listing['budget']['remaining_cad']:.2f} "
                        f"of the benchmark budget remains. Open Mission Control > Insights > "
                        f"Benchmark shopping list for each title, URL, price and reason. "
                        f"Upload each purchased PDF only through the teardown intake"),
                max_cost_cad=cost, minutes=max(10, 3 * n),
                consequence_of_delay=("the benchmark library keeps its current gaps (capability "
                                      "and owner-demand families); the list is rebuilt daily"),
                blocks="165,166",
                why_software_cannot=("buying is consequential spend and a payment step; software "
                                     "only prepares the list and never purchases"))
            if open_row is None:
                row = owner_queue.ensure(s, SHOPPING_ACTION_KEY, action=title, **fields)
                card = {"state": "raised", "id": row.id, "action": title}
            else:
                # Our own derived card: restated exactly, the ceiling following the list down
                # as well as up (the guard's never-lower rule is for owner-set ceilings).
                open_row.action = title
                for k, v in fields.items():
                    setattr(open_row, k, v)
                card = {"state": "restated", "id": open_row.id, "action": title}
        elif open_row is not None:
            owner_queue.close(open_row, owner_queue.WITHDRAWN,
                              "no pattern is left to buy on the benchmark shopping list"
                              if listing["status"] == "OK" else
                              "scan data is missing, so the list is UNKNOWN")
            card = {"state": "closed", "id": open_row.id}

        payload = {"as_of": today.isoformat(), **listing, "changed": changed, "card": card}
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == ps.SHOPPING_KIND,
            OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=ps.SHOPPING_KIND, period_key=today.isoformat(),
                                   payload=payload))
        else:
            row.payload = payload
    return payload
