"""F-357: children's-garment seasonal demand, measured rather than assumed.

The seasonal engine and lead-time planner cover events (baby showers among them) but nothing
tracked *when in the year* children's sub-categories are sought. This reads the sanctioned
Wikimedia pageview feed (`culture.feeds`: same source, user agent, courtesy spacing and
refusal rules; no credential, no spend) at **monthly** granularity for one reference article
per children's sub-category, records each series durably, and derives a demand window:

* `peak_months` -- months whose views are at least `PEAK_SHARE` of the series' own maximum,
  averaged across the years observed;
* `list_by` -- the next peak start minus the sub-category's lead time (the same quick/short/
  medium/long classes `seasonal.leadtime` uses, from typical make hours), so the planner knows
  when a children's listing must be live to meet the window.

Fewer than `MIN_MONTHS` months of data is `UNMEASURED`, never a guessed window. Reference
reading is not purchase intent; the output says so.
"""
from __future__ import annotations

import urllib.parse
from datetime import date, datetime, timedelta, timezone

ACTION = "seasonal.childrens_series"
MIN_MONTHS = 12
PEAK_SHARE = 0.85
LOOKBACK_MONTHS = 36

# sub-category -> (reference article, typical make hours used for the lead time)
SUBCATEGORIES: dict[str, tuple[str, float]] = {
    "baby_shower_gifts": ("Baby_shower", 6.0),
    "baby_blankets": ("Receiving_blanket", 15.0),
    "baby_garments": ("Infant_clothing", 10.0),
    "amigurumi_toys": ("Amigurumi", 4.0),
}


def _month_start(d: date) -> date:
    return d.replace(day=1)


def monthly_series(article: str, *, today: date | None = None, get=None) -> list[dict]:
    from ..culture import feeds

    end = _month_start(today or date.today()) - timedelta(days=1)   # last complete month
    start = _month_start(end)
    for _ in range(LOOKBACK_MONTHS - 1):
        start = _month_start(start - timedelta(days=1))
    quoted = urllib.parse.quote(article, safe="")
    url = (f"{feeds.BASE}/per-article/en.wikipedia/all-access/user/{quoted}/monthly/"
           f"{start.strftime('%Y%m%d')}00/{end.strftime('%Y%m%d')}00")
    body = (get or feeds._get)(url)
    items = body.get("items") or []
    if not items:
        raise feeds.FeedRefused(f"{article!r} returned no months; refused rather than zero")
    return [{"month": str(i.get("timestamp", ""))[:6], "views": int(i.get("views") or 0)}
            for i in items]


def sweep(db, *, today: date | None = None, get=None) -> dict:
    """Read each sub-category's monthly series and record it. Every failure is named."""
    import time

    from ..core.models import AuditLog
    from ..culture import feeds

    recorded, failures = [], []
    for i, (sub, (article, _hours)) in enumerate(sorted(SUBCATEGORIES.items())):
        if i and get is None:
            time.sleep(feeds.MIN_SECONDS_BETWEEN_CALLS)
        try:
            rows = monthly_series(article, today=today, get=get)
        except (feeds.FeedRefused, feeds.PermanentError, feeds.TransientError) as exc:
            failures.append({"subcategory": sub, "article": article, "why": str(exc)[:200]})
            continue
        with db.session() as s:
            s.add(AuditLog(actor="seasonal", action=ACTION, artifact=sub,
                           detail={"article": article, "months": rows,
                                   "source": f"{feeds.SOURCE_KEY}:monthly"}))
        recorded.append(sub)
    return {"recorded": recorded, "failures": failures}


def sweep_if_due(db, *, today: date | None = None, get=None) -> dict:
    """Monthly data changes once a month: re-read only when this month has no series yet."""
    from sqlalchemy import func, select

    from ..core.models import AuditLog

    today = today or date.today()
    start = datetime.combine(_month_start(today), datetime.min.time(), tzinfo=timezone.utc)
    with db.session() as s:
        done = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == ACTION, AuditLog.at >= start)) or 0
    if done:
        return {"recorded": [], "failures": [], "skipped": "already read this month"}
    return sweep(db, today=today, get=get)


def _latest_series(db) -> dict[str, dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[str, dict] = {}
    with db.session() as s:
        for r in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                           .order_by(AuditLog.id)):
            out[r.artifact or ""] = dict(r.detail or {})
    return out


def window_for(months: list[dict], make_hours: float, today: date) -> dict:
    from . import leadtime

    if len(months) < MIN_MONTHS:
        return {"state": "UNMEASURED",
                "why": f"{len(months)} month(s) of series, fewer than {MIN_MONTHS}"}
    by_month: dict[int, list[int]] = {}
    for m in months:
        if len(m["month"]) == 6:
            by_month.setdefault(int(m["month"][4:6]), []).append(m["views"])
    mean = {k: sum(v) / len(v) for k, v in by_month.items() if v}
    top = max(mean.values()) if mean else 0
    if not top:
        return {"state": "UNMEASURED", "why": "series has no views"}
    peaks = sorted(k for k, v in mean.items() if v >= PEAK_SHARE * top)
    seasonal = len(peaks) < 6
    lead_class = leadtime.classify(make_hours)
    lead_days = {leadtime.QUICK: 14, leadtime.SHORT: 21, leadtime.MEDIUM: 35,
                 leadtime.LONG: 56, leadtime.FLAGSHIP: 84}[lead_class]
    nxt = None
    for k in peaks:
        cand = date(today.year, k, 1)
        if cand < today:
            cand = date(today.year + 1, k, 1)
        nxt = cand if nxt is None or cand < nxt else nxt
    return {"state": "MEASURED", "peak_months": peaks, "seasonal": seasonal,
            "monthly_mean_views": {k: round(v) for k, v in sorted(mean.items())},
            "lead_class": lead_class, "lead_days": lead_days,
            "next_peak": nxt.isoformat() if nxt else None,
            "list_by": (nxt - timedelta(days=lead_days)).isoformat() if nxt and seasonal
            else None}


def windows(db, *, today: date | None = None) -> dict:
    today = today or date.today()
    series = _latest_series(db)
    out = {}
    for sub, (article, hours) in sorted(SUBCATEGORIES.items()):
        rec = series.get(sub)
        out[sub] = ({"state": "UNMEASURED", "why": "no monthly series recorded yet",
                     "article": article} if rec is None else
                    {"article": article, **window_for(rec.get("months") or [], hours, today)})
    return {"subcategories": out,
            "measures": "reference reading (Wikipedia pageviews), not purchase intent"}
