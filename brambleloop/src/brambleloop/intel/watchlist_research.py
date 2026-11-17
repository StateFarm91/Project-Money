"""Research M2 (reviews 6954809399, 6957516781): a watchlist gap's research question answered
from evidence this system observed, so gap -> research -> fact -> proposal -> concept_intake
runs unattended.

The question `watchlist._research_question` opens is "is buyer demand in this arena durable
across the watchlist shops, or a passing trend?". This answers it from the shops' own
observations, and only from observations that are current:

* A shop counts only when its latest scan succeeded within `FRESH_HOURS` (state `ok`). The
  comparison carries stored rows forward for a shop whose reads stopped; those are STALE.
* A listing counts only while it is not withdrawn (`BenchmarkListing.audit_state`), in the
  arena's pod. The comparison counts every stored row, withdrawn or not.
* Durability is the number of DISTINCT observation dates (a shop's own successful scan dates,
  read from the daily comparison readings) on which a shop corroborated the arena -- never the
  number of comparison runs, which repeat a stale shop's last figures every day.

What it writes, and nothing more:

* an `internal` source per corroborating shop, read at that shop's last successful scan, whose
  citation names the shop alias, the scan time and the live listing ids it counted;
* a `fact`: N fresh shops each list >= MIN_LISTINGS_FOR_ARENA live items in the pod, resting on
  those per-shop sources;
* a `fact`: per shop, its distinct observation dates corroborating the arena in the window;
* an `unresolved` finding: whether the listings sell is UNKNOWN;
* the answer, `medium` only when at least MIN_SHOPS_FOR_ARENA shops each corroborated the arena
  on at least `DURABLE_DAYS` distinct observation dates, else `low`.

When fewer than MIN_SHOPS_FOR_ARENA shops are fresh with enough live listings -- a stale or
withdrawn majority -- nothing is a fact: the task is left open and the reason is returned
(UNKNOWN, never a fact). Only aliases, listing ids, counts and dates are written: no competitor
title, URL or text. A task that is not OPEN is never touched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

DURABILITY_WINDOW_DAYS = 14
DURABLE_DAYS = 3
FRESH_HOURS = 48
ACTION = "research.answered_from_watchlist"


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _readings(db, kind: str, *, until: date) -> list[tuple[str, dict]]:
    """(day, payload) of every reading of `kind` in the window ending `until`, newest first."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    since = (until - timedelta(days=DURABILITY_WINDOW_DAYS - 1)).isoformat()
    with db.session() as s:
        rows = list(s.scalars(select(OperatingReading).where(
            OperatingReading.kind == kind, OperatingReading.period_key >= since,
            OperatingReading.period_key <= until.isoformat()).order_by(
            OperatingReading.period_key.desc())))
        return [(r.period_key, dict(r.payload or {})) for r in rows]


def fresh_shops(db, pod: str, *, now: datetime) -> dict[str, dict]:
    """alias -> {"observed_at", "listing_ids"} for every watchlist shop whose latest scan
    succeeded within FRESH_HOURS and which lists >= MIN_LISTINGS_FOR_ARENA live (not withdrawn)
    items in `pod`. Everything else is left out."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..runtime.intel_ops import benchmark_alias
    from . import watchlist as W

    out: dict[str, dict] = {}
    for m in W.WATCHLIST:
        st = W._state(db, m.key)
        ok_at = _parse(st.get("last_ok_at"))
        if st.get("state") != "ok" or ok_at is None or \
                now - ok_at > timedelta(hours=FRESH_HOURS) or ok_at > now:
            continue
        with db.session() as s:
            ids = sorted(str(r) for r in s.scalars(select(BenchmarkListing.listing_ref).where(
                BenchmarkListing.benchmark_key == m.key, BenchmarkListing.pod == pod,
                BenchmarkListing.audit_state != "withdrawn")))
        if len(ids) >= W.MIN_LISTINGS_FOR_ARENA:
            out[benchmark_alias(m.key)] = {"observed_at": ok_at.isoformat(),
                                           "listing_ids": ids}
    return out


def observation_dates(db, pod: str, *, now: datetime) -> dict[str, list[str]]:
    """alias -> the distinct dates of that shop's own successful scans on which a daily
    comparison counted it as corroborating `pod`, in the window. A stale shop repeated by later
    comparisons contributes its one scan date once."""
    from .watchlist import COMPARE_READING

    dates: dict[str, set[str]] = {}
    for _day, payload in _readings(db, COMPARE_READING, until=now.date()):
        corroborating = set()
        for a in payload.get("validated_arenas") or []:
            if a.get("pod") == pod:
                corroborating = {str(x) for x in a.get("corroborated_by") or []}
        for shop in payload.get("shops") or []:
            alias = shop.get("alias")
            obs = shop.get("observation") or {}
            ok_at = _parse(obs.get("last_ok_at"))
            if alias in corroborating and obs.get("state") == "ok" and ok_at is not None:
                dates.setdefault(alias, set()).add(ok_at.date().isoformat())
    return {a: sorted(d) for a, d in dates.items()}


def answer(db, *, gap_id: int, task_id: int, pod: str, now: datetime | None = None,
           audit=None) -> dict:
    """Answer the gap's OPEN research task from current observations, or say why not."""
    from . import research
    from .watchlist import MIN_LISTINGS_FOR_ARENA, MIN_SHOPS_FOR_ARENA

    now = now or datetime.now(timezone.utc)
    research._ensure(db)
    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        state = t.state if t is not None else None
    if state != research.OPEN:
        return {"answered": False, "task": task_id, "why": f"task is {state}, not open"}
    fresh = fresh_shops(db, pod, now=now)
    if len(fresh) < MIN_SHOPS_FOR_ARENA:
        return {"answered": False, "task": task_id, "fresh_shops": sorted(fresh),
                "why": (f"UNKNOWN: only {len(fresh)} watchlist shop(s) were observed in the "
                        f"last {FRESH_HOURS} h with >= {MIN_LISTINGS_FOR_ARENA} live listings "
                        f"in {pod}; stale shops and withdrawn listings are not evidence")}
    dates = observation_dates(db, pod, now=now)
    refs = {}
    for alias, rec in sorted(fresh.items()):
        refs[alias] = "S%d" % research.add_source(
            db, task_id, source="intel.watchlist_scan",
            citation=(f"watchlist shop {alias} scanned {rec['observed_at']}; live {pod} "
                      f"listings: {', '.join(rec['listing_ids'][:40])}"),
            retrieval="internal", read_on=_parse(rec["observed_at"]).date())
    f_now = research.add_finding(
        db, task_id, claim_class="fact", rests_on=sorted(refs.values()), confidence="high",
        statement=(f"{len(fresh)} watchlist shops we do not cover, each scanned within "
                   f"{FRESH_HOURS} h, list at least {MIN_LISTINGS_FOR_ARENA} live (not "
                   f"withdrawn) items in the {pod} arena: " + "; ".join(
                       f"{a} ({len(r['listing_ids'])} live, scanned {r['observed_at'][:16]})"
                       for a, r in sorted(fresh.items()))))
    per_shop = {a: dates.get(a, []) for a in sorted(fresh)}
    durable_shops = [a for a, d in per_shop.items() if len(d) >= DURABLE_DAYS]
    f_durable = research.add_finding(
        db, task_id, claim_class="fact", rests_on=sorted(refs.values()), confidence="high",
        statement=(f"Distinct observation dates on which each shop corroborated {pod} in the "
                   f"last {DURABILITY_WINDOW_DAYS} days: " + "; ".join(
                       f"{a}: {len(d)} ({', '.join(d) or 'none recorded'})"
                       for a, d in per_shop.items())))
    f_unknown = research.add_finding(
        db, task_id, claim_class="unresolved",
        statement=(f"Whether the {pod} listings sell is UNKNOWN: the scans record live "
                   f"listings and dates, not per-listing sales."))
    durable = len(durable_shops) >= MIN_SHOPS_FOR_ARENA
    confidence = "medium" if durable else "low"
    out = research.answer(
        db, task_id, outcome=("durable" if durable else "not yet shown durable"),
        confidence=confidence, now=now,
        effect={"kind": "constraint_established",
                "statement": (f"{pod}: {len(durable_shops)} of {len(fresh)} fresh shops "
                              f"corroborated it on >= {DURABLE_DAYS} distinct observation "
                              f"dates ({f_now}, {f_durable})")},
        conclusion={"alternatives": [], "constraints": [
                        f"{len(fresh)} fresh watchlist shops list >= {MIN_LISTINGS_FOR_ARENA} "
                        f"live {pod} items",
                        f"{len(durable_shops)} shops corroborated it on >= {DURABLE_DAYS} "
                        f"distinct observation dates"],
                    "unresolved": [f_unknown], "next_test": {},
                    "applicability": {"pod": pod, "gap": gap_id}})
    detail = {"gap": gap_id, "task": task_id, "pod": pod, "fresh_shops": sorted(fresh),
              "durable_shops": durable_shops, "confidence": confidence,
              "findings": [f_now, f_durable, f_unknown]}
    if audit is not None:
        audit(ACTION, artifact=f"research_task:{task_id}", detail=detail)
    return {"answered": True, **detail, "result": out}
