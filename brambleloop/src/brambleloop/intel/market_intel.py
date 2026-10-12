"""Market intelligence from sanctioned sources only, each figure labelled with what it is.

W4-MARKETINTEL, 2026-10-11. The owner does not want to collect search terms, screenshots or
competitor data by hand. This module is the company-side answer, and it starts from the
limit that shapes it:

**Etsy publishes no API for Marketplace Insights, search volume or shop statistics.** Etsy's
Open API v3 description (https://www.etsy.com/openapi/generated/oas/3.0.0.json, read
2026-10-11: 911,340 bytes, sha256 b993d52f..., 76 paths, 105 operations) contains the string
"insight" 0 times, "stats" 0, "statistic" 0, "traffic" 0, "visit" 0, "impression" 0,
"search volume" 0 and "trend" 0. Its only search operation is `findAllListingsActive`
(GET /v3/application/listings/active), whose `keywords` parameter searches active listings
and returns `{count, results}`. `views` exists only on `ShopListingWithAssociations`, "tabulated
once per day and only for active listings". Search-term volume is shown only on the rendered,
logged-in Shop Manager page, which software here does not automate (`intel.etsy_surfaces`,
marketplace_insights = UNSUPPORTED).

So what is computed here is a set of **proxies**, and every one says so:

=====================  ==============================================  =================
figure                 source                                          label
=====================  ==============================================  =================
competition            findAllListingsActive `count` (API index)       PROXY competition
competition_change     the same count, newest vs previous snapshot     PROXY competition
favourite_velocity     num_favorers growth/day of results present in   PROXY demand
                       both newest snapshots (a cumulative counter)    interest
recent_entrant_share   share of top results whose
                       original_creation_timestamp is < 90 days old    PROXY market entry
insights_search_count  Etsy Marketplace Insights, read by the owner    MEASURED (Etsy),
                       (InsightsSnapshot, owner_recorded_shop_manager) owner-recorded
=====================  ==============================================  =================

None of these is "search volume", and nothing here renames one. A figure with no observation
is `None` with the reason beside it -- UNKNOWN is never 0.

Routing (the existing consumers, nothing new invented):
  * SEO / Creative / Growth   -- subject `search_language`: listing.seo reads it through
    `improve.consume.matching('seo_search')`; briefs through `bus.brief_lessons`.
  * Crochet Engineer          -- subject `construction_preference` for the strongest
    proxy opportunities: the pipeline's radar.score reads it through
    `consume.matching('pattern_engineering')`.
  * Learning (experiments)    -- each opportunity is pre-registered as a growth experiment,
    gated on `live_listings`, so the proxy is tested against real listing outcomes.
  * Product Truth             -- `store_foundation.lint` TRUTH_MARKET_CLAIM refuses copy
    that asserts demand ("trending", "in demand", "high demand", "viral"): everything this
    company knows about demand is a proxy, and a proxy is not a claim.
"""
from __future__ import annotations

import hashlib
import re
import statistics
from datetime import date, datetime, timedelta, timezone

KIND = "market_intel"
ORIGIN_CELL = "market_radar"
LESSON_PREFIX = "market_intel:"
TOP = 24
RECENT_DAYS = 90
OPPORTUNITIES = 3

SEARCH_SOURCE = ("Etsy Open API v3 findAllListingsActive (GET /v3/application/listings/active, "
                 "keywords, sort_on=score): API search index, not the rendered etsy.com page")
INSIGHTS_SOURCE = "Etsy Marketplace Insights, read in Shop Manager and recorded by the owner"

PROXY = "PROXY"
MEASURED = "MEASURED"

ETSY_LIMIT = ("Etsy Open API v3 (oas 3.0.0, read 2026-10-11) has no Marketplace Insights, "
              "search-volume or shop-statistics operation: 'insight' 0, 'stats' 0, "
              "'statistic' 0, 'traffic' 0, 'impression' 0, 'search volume' 0 occurrences. "
              "Search-term volume exists only on the logged-in Shop Manager page.")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _metric(value, *, label: str, kind: str, source: str, at: str, why: str = "") -> dict:
    out = {"value": value, "label": label, "kind": kind, "source": source, "observed_at": at}
    if value is None:
        out["unknown_because"] = why or "not observed"
    return out


def _snapshots(db, query: str, n: int = 2) -> list:
    from . import serp

    return serp.latest(db, query, n=n)


def _favourites(row) -> dict:
    return {e["listing_id"]: e.get("favourites") for e in (row.rank_list or [])
            if e.get("listing_id") is not None and (e.get("rank") or 0) <= TOP}


def _insights_for(db, query: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import InsightsSnapshot

    words = " ".join(query.lower().split())
    with db.session() as s:
        row = s.scalar(select(InsightsSnapshot).where(InsightsSnapshot.keyword == words)
                       .order_by(desc(InsightsSnapshot.observed_on)).limit(1))
        if row is None:
            return None
        return {"id": row.id, "search_count": row.search_count,
                "listing_count": row.listing_count, "trend": row.trend_direction,
                "observed_on": _aware(row.observed_on).date().isoformat(),
                "recorded_by": row.recorded_by}


def query_signals(db, query: str, *, pod: str = "") -> dict:
    """Every figure for one query, each with its label, source and timestamp."""
    rows = _snapshots(db, query, 2)
    out: dict = {"query": query, "pod": pod, "snapshots": len(rows), "metrics": {}}
    m = out["metrics"]
    if not rows:
        why = "no API search snapshot of this query exists yet"
        for k in ("competition", "competition_change", "favourite_velocity",
                  "recent_entrant_share"):
            m[k] = _metric(None, label=k, kind=PROXY, source=SEARCH_SOURCE, at="", why=why)
    else:
        new = rows[0]
        at = _aware(new.captured_at).isoformat()
        m["competition"] = _metric(
            int(new.total_count) if new.total_count is not None else None,
            label="active listings matching the query (competition proxy)", kind=PROXY,
            source=SEARCH_SOURCE, at=at, why="the API returned no count")
        if len(rows) > 1 and rows[1].total_count is not None and new.total_count is not None:
            m["competition_change"] = _metric(
                int(new.total_count) - int(rows[1].total_count),
                label="change in matching active listings since the previous snapshot",
                kind=PROXY, source=SEARCH_SOURCE, at=at)
        else:
            m["competition_change"] = _metric(None, label="competition change", kind=PROXY,
                                              source=SEARCH_SOURCE, at=at,
                                              why="one snapshot: nothing to compare")
        if len(rows) > 1:
            old = rows[1]
            days = (_aware(new.captured_at) - _aware(old.captured_at)).total_seconds() / 86400
            now_f, then_f = _favourites(new), _favourites(old)
            per = [(now_f[k] - then_f[k]) / days for k in now_f
                   if k in then_f and now_f[k] is not None and then_f[k] is not None]
            if days >= 0.5 and per:
                m["favourite_velocity"] = _metric(
                    round(statistics.median(per), 3),
                    label=("median favourites gained per day by top results present in both "
                           "snapshots (demand-interest proxy; favourites are neither searches "
                           "nor sales)"),
                    kind=PROXY, source=SEARCH_SOURCE + " -- num_favorers", at=at)
                m["favourite_velocity"]["sample"] = len(per)
                m["favourite_velocity"]["window_days"] = round(days, 2)
            else:
                m["favourite_velocity"] = _metric(
                    None, label="favourite velocity", kind=PROXY, source=SEARCH_SOURCE, at=at,
                    why=("snapshots under half a day apart" if days < 0.5 else
                         "no result appears in both snapshots with a favourites count"))
        else:
            m["favourite_velocity"] = _metric(None, label="favourite velocity", kind=PROXY,
                                              source=SEARCH_SOURCE, at=at,
                                              why="velocity needs two snapshots")
        created = [e.get("created_ts") for e in (new.rank_list or [])
                   if (e.get("rank") or 0) <= TOP]
        known = [c for c in created if isinstance(c, int)]
        if known:
            cutoff = _aware(new.captured_at).timestamp() - RECENT_DAYS * 86400
            m["recent_entrant_share"] = _metric(
                round(sum(1 for c in known if c >= cutoff) / len(known), 3),
                label=f"share of top results first created in the last {RECENT_DAYS} days "
                      f"(market-entry proxy)", kind=PROXY,
                source=SEARCH_SOURCE + " -- original_creation_timestamp", at=at)
            m["recent_entrant_share"]["sample"] = len(known)
        else:
            m["recent_entrant_share"] = _metric(
                None, label="recent entrant share", kind=PROXY, source=SEARCH_SOURCE, at=at,
                why="this snapshot predates creation-time capture")
    ins = _insights_for(db, query)
    m["insights_search_count"] = _metric(
        ins["search_count"] if ins else None,
        label="Etsy Marketplace Insights searches (Etsy's own figure, owner-recorded)",
        kind=MEASURED, source=INSIGHTS_SOURCE + (f" (insights_snapshots:{ins['id']}, "
                                                 f"by {ins['recorded_by']})" if ins else ""),
        at=ins["observed_on"] if ins else "",
        why="no owner-recorded Insights reading for this keyword")
    vel, comp = m["favourite_velocity"]["value"], m["competition"]["value"]
    out["opportunity"] = (_metric(round(vel / max(comp, 1) * 1000, 4),
                                  label="favourite velocity per 1,000 matching listings "
                                        "(proxy ratio)", kind=PROXY, source="derived",
                                  at=m["competition"]["observed_at"])
                          if vel is not None and comp is not None else
                          _metric(None, label="opportunity", kind=PROXY, source="derived",
                                  at="", why="needs both competition and favourite velocity"))
    return out


def signals(db) -> dict:
    from . import serp

    targets = {t["query"]: t.get("pod", "") for t in serp.target_queries()}
    for q in serp.queries_captured(db):
        targets.setdefault(q, "")
    rows = [query_signals(db, q, pod=p) for q, p in sorted(targets.items())]
    # The words a consumer matches on: the pod and every target keyword of the same pod, so a
    # blanket lesson reaches a listing whose candidate queries say "throw" as well as
    # "blanket" (improve.consume.matching needs two shared content words).
    keywords: dict[str, set[str]] = {}
    for t in serp.target_queries():
        keywords.setdefault(t.get("pod", ""), set()).add(str(t.get("keyword") or ""))
    for r in rows:
        r["vocabulary"] = sorted({w for w in keywords.get(r["pod"], set()) if w}
                                 | ({r["pod"]} if r["pod"] else set()))
    ranked = sorted((r for r in rows if r["opportunity"]["value"] is not None),
                    key=lambda r: -r["opportunity"]["value"])
    return {"etsy_limit": ETSY_LIMIT, "queries": rows,
            "measured_queries": sum(1 for r in rows if r["snapshots"]),
            "opportunities": [r["query"] for r in ranked[:OPPORTUNITIES]]}


def _digest(obj) -> str:
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:12]


def _fmt(metric: dict) -> str:
    return "UNKNOWN" if metric["value"] is None else str(metric["value"])


def _statement(r: dict) -> str:
    m = r["metrics"]
    day = (m["competition"]["observed_at"] or "")[:10]
    s = (f"Market proxy for '{r['query']}' (Etsy API search index, {day}): "
         f"{_fmt(m['competition'])} matching active listings (competition proxy); "
         f"top results gained {_fmt(m['favourite_velocity'])} favourites per day "
         f"(demand-interest proxy, not searches or sales); recent-entrant share "
         f"{_fmt(m['recent_entrant_share'])}.")
    if m["insights_search_count"]["value"] is not None:
        # W4-SECFIX (review e3747c5 LOW-2): lesson statements are served publicly by
        # /api/improve, so the owner's Insights figure stays out of the text; consumers that
        # need it read `query_signals` (and the operator reads /api/market-intel).
        s += (f" An Etsy Marketplace Insights reading is on record (owner-recorded "
              f"{m['insights_search_count']['observed_at']}; the figure is operator-only).")
    vocab = r.get("vocabulary") or []
    if vocab:
        s += f" Pod {r['pod'] or 'unrouted'} vocabulary: {', '.join(vocab)}."
    return s + " Tag/title candidate evidence; never quote as search volume."


def _publish(db, subject: str, key: str, statement: str, digest: str) -> int:
    from sqlalchemy import select

    from ..core.models import Lesson
    from ..improve import bus

    ref = f"{LESSON_PREFIX}{key}:{digest}"
    lesson_id = bus.publish(db, origin_cell=ORIGIN_CELL, subject=subject,
                            statement=statement, evidence_ref=ref, confidence="observed")
    with db.session() as s:
        for old in s.scalars(select(Lesson).where(
                Lesson.evidence_ref.like(f"{LESSON_PREFIX}{key}:%"), Lesson.evidence_ref != ref,
                Lesson.superseded_by.is_(None))):
            old.superseded_by = lesson_id
    return lesson_id


def _register_experiment(db, r: dict, today: date) -> dict:
    from ..growth import experiments as X

    vel = float(r["metrics"]["favourite_velocity"]["value"] or 0.0)
    slug = re.sub(r"[^a-z0-9]+", "-", r["query"].lower()).strip("-")
    exp = X.Experiment(
        key=f"market_intel:{slug}",
        hypothesis=(f"A Brambleloop pattern listed for '{r['query']}' gains favourites per day "
                    f"at least at the median rate of the query's current top results, as the "
                    f"API-search proxy suggests"),
        metric="favourites_per_day", design=X.NO_CONTROL,
        success_threshold=max(vel, 0.05), failure_threshold=max(vel, 0.05) / 4,
        minimum_sample=14, stop_on=today + timedelta(days=60), owner="market_radar",
        decision=f"whether to build a second pattern for '{r['query']}'",
        on_success="commission a second concept for this query's pod",
        on_failure="drop the query from the proxy opportunity list",
        gated_on="live_listings")
    return X.persist(db, exp, gate_open=False)


def refresh(db, *, today: date | None = None) -> dict:
    """Compute, store the day's reading, route what changed to the existing consumers."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    today = today or datetime.now(timezone.utc).date()
    sig = signals(db)
    published, engineering, experiments = [], [], []
    for r in sig["queries"]:
        if not r["snapshots"] and r["metrics"]["insights_search_count"]["value"] is None:
            continue
        values = {k: v["value"] for k, v in r["metrics"].items()}
        published.append(_publish(db, "search_language", f"query:{r['query']}",
                                   _statement(r), _digest(values)))
    by_query = {r["query"]: r for r in sig["queries"]}
    for q in sig["opportunities"]:
        r = by_query[q]
        pod = r["pod"] or "unrouted"
        vocab = ", ".join(r.get("vocabulary") or [])
        stmt = (f"Proxy opportunity for the {pod} pod ({vocab}): '{q}' pattern -- "
                f"{_fmt(r['opportunity'])} favourites per day per 1,000 matching listings "
                f"(Etsy API search index; favourites and listing counts are proxies, not "
                f"searches or sales). Candidate for a {pod} crochet pattern concept and CIR; "
                f"the concept still passes the tournament, jury and CIR validation.")
        engineering.append(_publish(db, "construction_preference", f"opportunity:{q}", stmt,
                                    _digest(r["opportunity"]["value"])))
        experiments.append(_register_experiment(db, r, today))
    payload = {**sig, "lessons": sorted(set(published)), "engineering_lessons": engineering,
               "experiments": experiments, "generated_at": datetime.now(timezone.utc).isoformat()}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=today.isoformat(), payload=payload))
        else:
            row.payload = payload
    return {"queries": len(sig["queries"]), "measured_queries": sig["measured_queries"],
            "lessons": sorted(set(published)), "engineering_lessons": engineering,
            "opportunities": sig["opportunities"], "experiments": experiments,
            "etsy_limit": ETSY_LIMIT}


def latest(db) -> dict | None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND)
                       .order_by(OperatingReading.id.desc()).limit(1))
        return dict(row.payload or {}) if row is not None else None


# ---------------------------------------------------------------------------
# The owner's one step: paste what Marketplace Insights shows, parsed deterministically

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kKmM])?(?![\w])")
_KEY = re.compile(r"^\s*(?:search(?:ed)? (?:term|for)|keyword|term)\s*[:\-]\s*(.+?)\s*$", re.I)


def _count(text: str) -> int | None:
    m = _NUM.search(text)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    mult = {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return int(round(n * mult))


def parse_insights(text: str) -> dict:
    """Turn a pasted Marketplace Insights view into readings, or say which lines it could not.

    Deterministic, and conservative on purpose: a line is used only when it matches one of
    the shapes below; every other non-empty line is returned under `unparsed` rather than
    guessed at. Shapes:
      `Search term: <keyword>` (or `Keyword:`) starts a block;
      a line containing `search` and a number -> that block's search_count;
      a line containing `listing` or `competition` and a number -> listing_count;
      a line containing `trend` and up/down/flat -> trend_direction;
      after a `Related` line, `<term>  <number>` lines -> related terms.
    """
    blocks: list[dict] = []
    unparsed: list[str] = []
    cur: dict | None = None
    related = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        km = _KEY.match(line)
        if km:
            cur = {"keyword": km.group(1).strip().strip('"').lower(), "search_count": None,
                   "listing_count": None, "trend_direction": "unknown", "related_terms": []}
            blocks.append(cur)
            related = False
            continue
        if cur is None:
            unparsed.append(line)
            continue
        if low.startswith("related"):
            related = True
            continue
        n = _count(line)
        if "trend" in low:
            for word in ("up", "down", "flat"):
                if re.search(rf"\b{word}\b", low):
                    cur["trend_direction"] = word
            continue
        if related and n is not None:
            term = _NUM.sub("", line).strip(" -:\t").lower()
            if term:
                cur["related_terms"].append(term)
                continue
        if n is not None and "search" in low:
            cur["search_count"] = n
        elif n is not None and ("listing" in low or "competition" in low):
            cur["listing_count"] = n
        else:
            unparsed.append(line)
    readings = [b for b in blocks if b["search_count"] is not None
                or b["listing_count"] is not None or b["related_terms"]]
    return {"readings": readings, "unparsed": unparsed,
            "digest": hashlib.sha256((text or "").encode()).hexdigest(),
            "empty_blocks": [b["keyword"] for b in blocks if b not in readings]}


def record_paste(db, text: str, *, recorded_by: str, observed_on: str = "",
                 confirm: bool = False) -> dict:
    """Parse; and only when `confirm` is true, record each reading as an InsightsSnapshot."""
    from . import insights

    parsed = parse_insights(text)
    if not confirm:
        return {**parsed, "recorded": [], "confirmed": False}
    recorded = []
    for r in parsed["readings"]:
        recorded.append(insights.record(
            db, keyword=r["keyword"], search_count=r["search_count"],
            listing_count=r["listing_count"], related_terms=r["related_terms"],
            trend_direction=r["trend_direction"], observed_on=observed_on or None,
            recorded_by=recorded_by))
    return {**parsed, "recorded": recorded, "confirmed": True}
