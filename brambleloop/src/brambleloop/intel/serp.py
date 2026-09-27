"""The SERP laboratory: ranked reads of the API's marketplace search, kept over time (#15).

Requirement 15 asks what wins in search for the queries this company targets: which listings
rank, at what price, with what media, and what their thumbnails do. The sanctioned route is
`findAllListingsActive` (`intel.etsy_public`, endpoint `search_listings`), which answers a
keyword query with the API index's `sort_on=score` ordering and a result `count`.

What that is, stated once and carried on every row as `basis = api_index_score_sort`:

  * the ranking of Etsy's **API search index**, not the rendered etsy.com search page. Etsy
    does not say the two are the same (`intel.etsy_surfaces`, search_visibility). Rank is
    therefore **directional**: a listing that climbs thirty places in the API order is
    evidence of something; a listing at 4 rather than 5 is not.
  * `total_count` is the index's result count for the query -- the listing-density figure #2
    reads, labelled `api_index_count` -- and never a claim about what a buyer sees.

Thumbnail composition is judged by the same closed-vocabulary vision path the benchmark
gallery drain uses (`intel.vision`): the same system prompt, the same parser, the same budget
check and the same ledger. It refuses outright when the `image_vision` capability has not
been demonstrated, and says so, rather than inferring composition from a title.

Nothing here scrapes, renders or evades anything (B-268): one sanctioned JSON endpoint on the
API key alone, rate-limited by the reader's own Retry-After handling.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BASIS = "api_index_score_sort"
DENSITY_BASIS = "api_index_count"
SOURCE = "serp_laboratory"

# How deep one snapshot reads. Roughly one results page; beyond it the API order is noise
# for a question about what wins.
RANK_DEPTH = 48
# Listings per query whose gallery is read for an image count and a thumbnail URL. The rest
# of the ranked list carries `image_count: None` -- unmeasured, not zero.
DETAIL_TOP = 10
# Keywords taken from each pod's form vocabulary, most specific first.
QUERIES_PER_POD = 2
# A query captured more recently than this is not captured again: the API order does not
# move hourly, and re-reading it would spend rate limit on the same answer.
RECAPTURE_AFTER_HOURS = 20
# Thumbnails judged per snapshot when a vision run is asked for.
THUMBNAIL_TOP = 5

# The observation fields that describe a thumbnail's composition, read from the closed
# vision vocabulary rather than asked for separately.
COMPOSITION_FIELDS = ("shot_type", "composition", "product_visibility",
                      "thumbnail_readability", "setting", "palette_role")


class SerpRefused(RuntimeError):
    """A capture or a judgement this module cannot honestly make."""


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def query_for(keyword: str) -> str:
    """The buyer-shaped search for a pod keyword: "crochet <keyword> pattern"."""
    return f"crochet {keyword}" if "pattern" in keyword else f"crochet {keyword} pattern"


def target_queries() -> list[dict]:
    """The queries the laboratory watches, derived from the market map's pod vocabulary.

    `intel.market_map` routes every observed listing through `intel.pods`, whose keyword
    tables are only allowed to grow from words that appear in observed titles. The first
    keywords of each pod are its most specific form words, so the queries are the micro-
    markets the map already has departments for -- not a list somebody imagined.
    """
    from . import pods

    out: list[dict] = []
    seen: set[str] = set()
    for pod in pods.PODS:
        taken = 0
        for keyword in pod.keywords:
            # "guidebook" and "guide book" are one query to a search index.
            squashed = keyword.replace(" ", "")
            if taken >= QUERIES_PER_POD or squashed in seen:
                continue
            seen.add(squashed)
            taken += 1
            out.append({"query": query_for(keyword), "pod": pod.key,
                        "keyword": keyword})
    # #33: one query per seasonal event, so the 365-day engine's competitive-weakness factor
    # has a measured source (the index's listing count for that occasion) rather than none.
    from ..radar.market import SEASONAL_EVENTS

    for event in SEASONAL_EVENTS:
        word = event_word(event.name)
        if word and word not in seen:
            seen.add(word)
            out.append({"query": query_for(word), "pod": EVENT_POD, "keyword": word,
                        "event": event.name})
    return out


EVENT_POD = "seasonal_event"


def event_word(name: str) -> str:
    """The word a buyer types for an occasion: "Valentine's" -> "valentine"."""
    return name.split(" ")[0].split("'")[0].lower()


def _price(listing: dict) -> tuple[float | None, str]:
    price = listing.get("price")
    if isinstance(price, dict):
        try:
            divisor = float(price.get("divisor") or 1) or 1.0
            return round(float(price.get("amount")) / divisor, 2), str(
                price.get("currency_code") or "")
        except (TypeError, ValueError):
            return None, ""
    return None, ""


def _has_sale(listing: dict) -> bool | None:
    """Whether the API marks the listing as discounted. None when it says nothing.

    The search endpoint does not always carry a sale indicator; absent is unmeasured rather
    than "not on sale", which would read as a market with no discounting.
    """
    for key in ("is_sale", "on_sale", "has_sale"):
        if key in listing and listing[key] is not None:
            return bool(listing[key])
    return None


def capture(db, reader, query: str, *, taxonomy_id: int | None = None,
            depth: int = RANK_DEPTH, detail_top: int = DETAIL_TOP,
            now: datetime | None = None) -> dict:
    """One ranked snapshot of one query, stored as a `SerpSnapshot`."""
    from ..core.models import SerpSnapshot

    body = reader.search(query, taxonomy_id=taxonomy_id, sort_on="score", limit=depth)
    results = list(body.get("results") or [])[:depth]
    count = body.get("count")

    from . import deliverable, pods

    ranks: list[dict] = []
    for position, listing in enumerate(results, start=1):
        price, currency = _price(listing)
        favourites = listing.get("num_favorers")
        title = str(listing.get("title") or "")
        pod = pods.route(title, str(listing.get("taxonomy_id") or "")) if title else None
        # Facts, never copy (the deliverable reader's rule): what the result states, read
        # from the description the search payload already carries, then discarded.
        facts = deliverable.read(listing)
        sizes = deliverable.size_range(listing, pod=pod or "") if pod else None
        entry = {"rank": position, "listing_id": listing.get("listing_id"),
                 "shop_id": listing.get("shop_id"),
                 "price": price, "currency": currency,
                 "has_sale": _has_sale(listing),
                 "image_count": None, "thumbnail_url": "",
                 "favourites": int(favourites) if favourites is not None else None,
                 "taxonomy_id": listing.get("taxonomy_id"),
                 "pod": pod,
                 "is_pattern": (deliverable.is_digital(listing)
                                or "pattern" in title.lower()) if (
                     title or listing.get("is_digital") is not None) else None,
                 "clarity": (facts or {}).get("clarity"),
                 "terms_stated": ((facts or {}).get("stated") or {}).get("terms"),
                 "sizes": (sizes or {}).get("sizes") if (sizes or {}).get("stated") else (
                     0 if sizes is not None else None),
                 "has_video": None}
        if position <= detail_top and listing.get("listing_id") is not None:
            try:
                images = reader.images(listing["listing_id"])
            except Exception:  # noqa: BLE001 - one unreadable gallery stays unmeasured
                images = None
            if images is not None:
                entry["image_count"] = len(images)
                first = sorted(images, key=lambda i: int(i.get("rank") or 0))[:1]
                if first:
                    entry["thumbnail_url"] = str(first[0].get("url_570xN")
                                                 or first[0].get("url_fullxfull") or "")
            # Pattern + video positioning (#15): the sanctioned listing_videos read, taken
            # for the same top results whose gallery is read. Unreadable stays None.
            if hasattr(reader, "videos"):
                try:
                    entry["has_video"] = bool(reader.videos(listing["listing_id"]))
                except Exception:  # noqa: BLE001 - unmeasured, not "no video"
                    entry["has_video"] = None
        ranks.append(entry)

    at = _now(now)
    with db.session() as s:
        row = SerpSnapshot(query=query, taxonomy_id=taxonomy_id, captured_at=at,
                           rank_list=ranks,
                           total_count=int(count) if count is not None else None,
                           basis=BASIS, detail={"depth": depth, "detail_top": detail_top,
                                                "positioning": positioning(ranks,
                                                                           top=detail_top)})
        s.add(row)
        s.flush()
        snapshot_id = row.id
    return {"id": snapshot_id, "query": query, "taxonomy_id": taxonomy_id,
            "captured_at": at.isoformat(), "ranked": len(ranks),
            "total_count": int(count) if count is not None else None, "basis": BASIS}


# ---------------------------------------------------------------------------
# Scoring the result set (#15): pattern+video positioning, category diversity, price/sale
# and social-proof presentation, and where a Brambleloop listing would differ.

# What every Brambleloop release ships, by construction rather than by aspiration: two PDFs
# (US and UK terms, `commerce.seo`), a graded run compiled and verified across this many
# sizes (`cir.benchmarks.SIZES`) where size is a variable, and a listing that states what
# arrives. A result is "differentiable" when it falls short of one of these on facts it
# states itself; a result whose description was never read counts toward nothing.
CLEAR_STATEMENT = 0.75


def _gradable_sizes() -> int:
    from ..cir.benchmarks import SIZES

    return len(SIZES)


def positioning(ranks: list[dict], *, top: int = DETAIL_TOP) -> dict:
    """Score one ranked result set on the dimensions #15 names that the index can answer.

    Thumbnail composition is not here: it needs a model to look at the image and is scored by
    `score_thumbnails` when `image_vision` is open. Rank is directional throughout.
    """
    from .deliverable import SIZED_PODS

    head = [e for e in ranks if int(e.get("rank") or 0) <= top]
    n = len(head)
    if not n:
        return {"measurable": False, "top": top,
                "reason": "no ranked results in this snapshot"}

    def share(xs: list[bool]) -> float | None:
        return round(sum(1 for x in xs if x) / len(xs), 3) if xs else None

    patterns = [e for e in head if e.get("is_pattern") is not None]
    is_pattern = [bool(e["is_pattern"]) for e in patterns]
    video_known = [e for e in head if e.get("has_video") is not None]
    pattern_video = [e for e in video_known if e.get("is_pattern") and e["has_video"]]
    first_pv = min((int(e["rank"]) for e in pattern_video), default=None)

    pods_seen = [e["pod"] for e in head if e.get("pod")]
    shops = [str(e["shop_id"]) for e in head if e.get("shop_id") is not None]
    top_shop = max((shops.count(sh) for sh in set(shops)), default=0)
    taxonomies = {e["taxonomy_id"] for e in head if e.get("taxonomy_id") is not None}

    priced = [float(e["price"]) for e in head if e.get("price") is not None]
    sale_known = [bool(e["has_sale"]) for e in head if e.get("has_sale") is not None]
    favs = sorted(int(e["favourites"]) for e in head if e.get("favourites") is not None)

    gradable = _gradable_sizes()
    judged, beaten, reasons = 0, 0, {"terms_unstated": 0, "fewer_sizes": 0,
                                     "unclear_deliverable": 0}
    for e in head:
        if e.get("clarity") is None:
            continue
        judged += 1
        hit = False
        if e.get("terms_stated") is False:
            reasons["terms_unstated"] += 1
            hit = True
        if e.get("pod") in SIZED_PODS and e.get("sizes") is not None and \
                int(e["sizes"]) < gradable:
            reasons["fewer_sizes"] += 1
            hit = True
        if float(e["clarity"]) < CLEAR_STATEMENT:
            reasons["unclear_deliverable"] += 1
            hit = True
        beaten += hit

    return {
        "measurable": True, "top": top, "results": n, "basis": BASIS,
        "pattern_video": {
            "pattern_share": share(is_pattern), "patterns_measured": len(patterns),
            "video_measured": len(video_known),
            "pattern_with_video": len(pattern_video),
            "pattern_with_video_share": share([bool(e.get("is_pattern") and e["has_video"])
                                               for e in video_known]),
            "first_pattern_with_video_rank": first_pv,
            "opening": (len(video_known) > 0 and not pattern_video),
        },
        "category_diversity": {
            "distinct_pods": len(set(pods_seen)), "pods_measured": len(pods_seen),
            "pod_diversity": (round(len(set(pods_seen)) / len(pods_seen), 3)
                              if pods_seen else None),
            "distinct_taxonomies": len(taxonomies),
            "top_shop_share": round(top_shop / len(shops), 3) if shops else None,
            "distinct_shops": len(set(shops)),
        },
        "price_and_sale": {
            "median_price": (sorted(priced)[len(priced) // 2] if priced else None),
            "on_sale_share": share(sale_known), "sale_measured": len(sale_known),
        },
        "social_proof": {"median_favourites": favs[len(favs) // 2] if favs else None,
                         "measured": len(favs)},
        "brambleloop_differentiation": {
            "value": round(beaten / judged, 3) if judged else None,
            "judged": judged, "differentiable": beaten, "by": reasons,
            "against": (f"two PDFs (US and UK terms), a graded run verified across "
                        f"{gradable} sizes where size varies, and a stated deliverable -- "
                        f"what every Brambleloop release ships"),
            "reason": "" if judged else ("no result's description was read, so how a "
                                         "Brambleloop listing would differ is unmeasured"),
        },
        "note": ("the API index's top results; rank is directional. Thumbnail composition "
                 "is judged separately and only where image_vision is open"),
    }


def differentiation_by_pod(db) -> dict[str, dict]:
    """The newest snapshot's differentiation per pod query, averaged per pod (feeds #2)."""
    out: dict[str, list[float]] = {}
    pod_of = {t["query"]: t.get("pod") for t in target_queries()}
    for query in queries_captured(db):
        pod = pod_of.get(query)
        rows = latest(db, query, n=1)
        if not pod or not rows:
            continue
        pos = (rows[0].detail or {}).get("positioning") or positioning(rows[0].rank_list or [])
        value = ((pos.get("brambleloop_differentiation") or {}).get("value"))
        if value is not None:
            out.setdefault(pod, []).append(float(value))
    return {pod: {"value": round(sum(v) / len(v), 4), "queries": len(v),
                  "basis": "serp_positioning"} for pod, v in out.items()}


def _recent_queries(db, since: datetime) -> set[str]:
    from sqlalchemy import select

    from ..core.models import SerpSnapshot

    with db.session() as s:
        return {r.query for r in s.scalars(select(SerpSnapshot))
                if _aware(r.captured_at) >= since}


def capture_targets(db, *, reader=None, transport=None, env: dict | None = None,
                    queries: list[dict] | None = None, now: datetime | None = None) -> dict:
    """Capture every target query not already captured recently. The cadence's body."""
    from . import etsy_public

    now = _now(now)
    queries = queries if queries is not None else target_queries()
    if reader is None:
        credential = etsy_public.ReadCredential.from_env(env)
        if credential is None or not credential.complete:
            return {"ran": False, "captured": [], "queries": len(queries),
                    "reason": (f"{etsy_public.KEYSTRING_VAR} and {etsy_public.SECRET_VAR} "
                               f"are not both set, so the API search index cannot be read; "
                               f"no snapshot is recorded and none is guessed")}
        if transport is None:
            from ..integrations.http import UrllibTransport

            transport = UrllibTransport()
        reader = etsy_public.PublicReader(transport, env=env)

    fresh = _recent_queries(db, now - timedelta(hours=RECAPTURE_AFTER_HOURS))
    captured, skipped, failures = [], [], []
    for target in queries:
        if target["query"] in fresh:
            skipped.append(target["query"])
            continue
        try:
            captured.append(capture(db, reader, target["query"],
                                    taxonomy_id=target.get("taxonomy_id"), now=now))
        except etsy_public.NotConfigured as exc:
            return {"ran": False, "captured": captured, "queries": len(queries),
                    "reason": str(exc)[:300]}
        except Exception as exc:  # noqa: BLE001 - one failed query does not end the run
            failures.append({"query": target["query"], "why": f"{type(exc).__name__}: "
                                                              f"{str(exc)[:200]}"})
    return {"ran": True, "captured": captured, "skipped_recent": skipped,
            "failures": failures, "queries": len(queries), "basis": BASIS,
            "note": ("rank is the API index's sort_on=score order and is directional; "
                     "counts are the API index's result counts, not the rendered page")}


# ---------------------------------------------------------------------------
# Reading snapshots back


def latest(db, query: str, *, n: int = 2) -> list:
    from sqlalchemy import desc, select

    from ..core.models import SerpSnapshot

    with db.session() as s:
        rows = list(s.scalars(select(SerpSnapshot).where(SerpSnapshot.query == query)
                              .order_by(desc(SerpSnapshot.captured_at),
                                        desc(SerpSnapshot.id)).limit(n)))
        s.expunge_all()
    return rows


def queries_captured(db) -> list[str]:
    from sqlalchemy import select

    from ..core.models import SerpSnapshot

    with db.session() as s:
        return sorted({q for q in s.scalars(select(SerpSnapshot.query))})


def changes(db, query: str, *, top: int = 24) -> dict:
    """Entrants, exits and rank movement between the two newest snapshots of a query.

    Directional by construction: movement is reported, and nothing here claims a listing
    "ranks" anywhere on the rendered page.
    """
    rows = latest(db, query, n=2)
    if len(rows) < 2:
        return {"query": query, "comparable": False, "snapshots": len(rows),
                "reason": "fewer than two snapshots of this query exist, so nothing has "
                          "moved yet -- which is not the same as a stable ranking"}
    new, old = rows[0], rows[1]

    def ranks(row) -> dict:
        return {e["listing_id"]: e["rank"] for e in (row.rank_list or [])
                if e.get("listing_id") is not None and e["rank"] <= top}

    now_r, then_r = ranks(new), ranks(old)
    entrants = sorted((lid for lid in now_r if lid not in then_r), key=lambda l: now_r[l])
    exits = sorted((lid for lid in then_r if lid not in now_r), key=lambda l: then_r[l])
    moved = {lid: then_r[lid] - now_r[lid] for lid in now_r if lid in then_r}
    movement = [abs(v) for v in moved.values()]
    return {
        "query": query, "comparable": True, "top": top, "basis": BASIS,
        "from": _aware(old.captured_at).isoformat(), "to": _aware(new.captured_at).isoformat(),
        "entrants": entrants, "exits": exits,
        "moved": {str(k): v for k, v in moved.items() if v},
        "mean_abs_movement": round(sum(movement) / len(movement), 2) if movement else 0.0,
        "count_from": old.total_count, "count_to": new.total_count,
    }


def density(db) -> dict[str, dict]:
    """The newest API index result count per captured query, with its date (#2)."""
    out: dict[str, dict] = {}
    for query in queries_captured(db):
        rows = latest(db, query, n=1)
        if rows and rows[0].total_count is not None:
            out[query] = {"count": int(rows[0].total_count), "basis": DENSITY_BASIS,
                          "observed_on": _aware(rows[0].captured_at).date().isoformat()}
    return out


# ---------------------------------------------------------------------------
# Thumbnail composition, through the existing vision path


def score_thumbnails(db, snapshot_id: int, *, top_n: int = THUMBNAIL_TOP, provider=None,
                     job_id: int | None = None) -> dict:
    """Judge the top-N thumbnails of one snapshot with the gallery vision path.

    Refuses, and says so, when `image_vision` has not been demonstrated: a composition
    score nobody looked at is the silent downgrade #224 forbids. Every call is checked
    against the monthly ceiling and the market_radar agent's daily ceiling before it is
    made, and billed to the ledger afterwards, exactly as the gallery drain is.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.models import SerpSnapshot
    from ..core.resilience import PermanentError, TransientError
    from ..gateway import anthropic as gw
    from . import vision

    if not gw.vision_usable(db):
        return {"snapshot": snapshot_id, "judged": 0, "refused": True,
                "reason": ("image_vision is unavailable: no real image has been looked at by "
                           "the model provider, so no thumbnail composition is scored and "
                           "none is inferred from a title")}

    with db.session() as s:
        row = s.get(SerpSnapshot, snapshot_id)
        if row is None:
            raise SerpRefused(f"no SERP snapshot {snapshot_id}")
        entries = [dict(e) for e in (row.rank_list or [])]
        done = dict((row.detail or {}).get("thumbnails") or {})

    todo = [e for e in entries if e["rank"] <= top_n and e.get("thumbnail_url")
            and str(e.get("listing_id")) not in done]
    provider = provider or gw.provider_for(vision.TASK)
    judged, failures, spent, reserved = 0, [], 0.0, 0.0
    tokens_in = tokens_out = 0
    stopped_by = ""
    for entry in todo:
        held = None
        try:
            reservation = gw.check_budget(
                db, model=provider.model,
                input_tokens=len(vision.analysis_prompt()) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
                max_tokens=vision.ANALYSIS_MAX_TOKENS,
                uncommitted_cad=max(spent, reserved),
                agent=vision.AGENT, purpose=vision.TASK, job_id=job_id)
            held = reservation["reservation_id"]
            estimate = reservation["estimate_cad"]
            response = provider.see(vision.ANALYSIS_SYSTEM, vision.analysis_prompt(),
                                    [entry["thumbnail_url"]],
                                    max_tokens=vision.ANALYSIS_MAX_TOKENS)
        except gw.AgentCeilingExceeded as exc:
            gw.release_reservation(db, held)
            stopped_by = "agent_daily_ceiling"
            failures.append({"listing_id": entry["listing_id"], "why": str(exc)[:200]})
            break
        except gw.BudgetExceeded as exc:
            gw.release_reservation(db, held)
            stopped_by = "monthly_model_ceiling"
            failures.append({"listing_id": entry["listing_id"], "why": str(exc)[:200]})
            break
        except (PermanentError, TransientError) as exc:
            gw.release_reservation(db, held)
            failures.append({"listing_id": entry["listing_id"], "why": str(exc)[:200]})
            continue
        cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                     + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        gw.release_reservation(db, held, actual_cad=cost)
        spent += cost
        reserved += estimate
        tokens_in += response.input_tokens
        tokens_out += response.output_tokens
        try:
            observation = vision.parse_observation(response.text)
        except vision.AnalysisRefused as exc:
            failures.append({"listing_id": entry["listing_id"], "why": str(exc)[:200]})
            continue
        done[str(entry["listing_id"])] = {
            "rank": entry["rank"],
            "composition": {k: observation[k] for k in COMPOSITION_FIELDS
                            if k in observation},
            "observation": observation,
            "judged_at": datetime.now(timezone.utc).isoformat()}
        judged += 1

    vision._bill(db, spent, judged, job_id, provider=provider, reserved=reserved,
                 tokens_in=tokens_in, tokens_out=tokens_out)
    with db.session() as s:
        row = s.get(SerpSnapshot, snapshot_id)
        detail = dict(row.detail or {})
        detail["thumbnails"] = done
        row.detail = detail
        flag_modified(row, "detail")

    shots: dict[str, int] = {}
    for item in done.values():
        shot = (item.get("composition") or {}).get("shot_type")
        if shot:
            shots[shot] = shots.get(shot, 0) + 1
    return {"snapshot": snapshot_id, "refused": False, "judged": judged,
            "attempted": len(todo), "failures": failures, "stopped_by": stopped_by,
            "cost_cad": round(spent, 8), "shot_types_in_top": shots,
            "note": ("thumbnail composition from the closed vision vocabulary, for the API "
                     "index's top results; rank is directional")}


def state(db) -> dict:
    """What the laboratory has captured and how fresh it is."""
    from sqlalchemy import func, select

    from ..core.models import SerpSnapshot

    with db.session() as s:
        total = s.scalar(select(func.count(SerpSnapshot.id))) or 0
        newest = s.scalar(select(func.max(SerpSnapshot.captured_at)))
    return {"snapshots": int(total), "queries": queries_captured(db),
            "targets": target_queries(),
            "newest": _aware(newest).isoformat() if newest else None,
            "basis": BASIS, "density_basis": DENSITY_BASIS,
            "note": ("the API index's sort_on=score order, captured per target query; it is "
                     "a directional proxy for search placement, not the rendered etsy.com "
                     "search page" if total else
                     "no SERP snapshot has been captured, so what wins in search for the "
                     "target queries is unknown -- which is not the same as nothing winning")}
