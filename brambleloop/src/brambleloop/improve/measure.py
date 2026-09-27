"""One deterministic measurer per capability cell, reading the rows each cell names.

Requirements 90, 94, 193. The Improvement Department was built with twelve cells, each owning
a metric and each stating *in words* how that metric is produced from rows -- and then nothing
ever produced it. Production reported twelve of twelve cells UNMEASURED because
`cells.record_capability` had no caller outside a test. A department that can say how it would
measure itself and never does is describing a company rather than running one.

So every `Cell.measure` string here has the query it names, and the nightly sweep's INGEST
stage calls them. Three rules keep the measurement honest:

**A measurer that finds an empty source records nothing.** A first measurement is a baseline,
never a win, and a zero written into an empty table would be read by every downstream curve as
"defects: none" when the truth is "defects: unknowable". `None` with a stated reason is the
output, and the reason names the table that has to fill before the number exists.

**Data-gated cells say what would gate them open.** Pricing, customer experience, portfolio,
finance and growth need a sale, a support case, revenue attributed to a product, a forecast or
traffic. In shadow mode none of those exist, and the measurer says `data-gated: needs <table>`
rather than inventing a proxy that would look like progress on a graph.

**The same query every night.** Each measurer is a plain function of the database at the time
it runs, with no model, no randomness and no memory. Two people running it on the same rows get
the same number, which is what makes "this cell got better" checkable by somebody who does not
trust the cell.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .cells import BY_KEY, CELLS

SOURCE = "improve.measure"

# Words a keyword phrase carries that say nothing about which search it answers. A cluster is
# the phrase with these removed, so "crochet blanket pattern pdf" and "blanket crochet
# pattern" are one cluster and "crochet blanket" and "crochet cardigan" are two.
_KEYWORD_NOISE: frozenset[str] = frozenset({
    "crochet", "crocheted", "pattern", "patterns", "pdf", "digital", "download", "the", "a",
    "an", "for", "of", "and", "to", "in", "with", "easy", "beginner", "instant", "printable",
})


class MeasureRefused(ValueError):
    """A cell nobody declared, or a measurement with no sample behind it."""


@dataclass(frozen=True)
class Measurement:
    """One cell's number, the rows it was read from, and how."""

    cell: str
    value: float
    sample: int
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cell not in BY_KEY:
            raise MeasureRefused(f"unknown cell {self.cell!r}")
        if self.sample <= 0:
            raise MeasureRefused(
                f"{self.cell}: a measurement over zero rows is not a measurement. An empty "
                f"source returns None, and a zero here would be read as a clean result")


@dataclass(frozen=True)
class NotMeasured:
    """Why a cell produced no number tonight, stated rather than defaulted to zero."""

    cell: str
    reason: str
    read: int = 0


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The measurers. One per cell, each reading exactly the rows its Cell.measure names.


def measure_pattern_engineering(db, *, now: datetime | None = None):
    """certified PatternVersion rows against total compiled."""
    from sqlalchemy import select

    from ..core.models import PatternVersion

    with db.session() as s:
        rows = list(s.scalars(select(PatternVersion)))
    if not rows:
        return NotMeasured("pattern_engineering", "no PatternVersion has been compiled yet")
    certified = sum(1 for r in rows if r.certified)
    return Measurement("pattern_engineering", certified / len(rows), len(rows),
                       {"certified": certified, "compiled": len(rows)})


def measure_quality(db, *, now: datetime | None = None):
    """Incident rows whose product had already certified before the incident was raised."""
    from sqlalchemy import select

    from ..core.models import Incident, PatternVersion, Product

    with db.session() as s:
        certified = [(p.slug, _aware(v.created_at))
                     for v in s.scalars(select(PatternVersion).where(
                         PatternVersion.certified.is_(True)))
                     for p in [s.get(Product, v.product_id)] if p is not None]
        incidents = [(i.product_slug, _aware(i.at)) for i in s.scalars(select(Incident))
                     if i.product_slug]
    if not certified:
        return NotMeasured("quality",
                           "no product has certified, so nothing can have escaped a release")
    released_at: dict[str, datetime] = {}
    for slug, at in certified:
        if slug not in released_at or at < released_at[slug]:
            released_at[slug] = at
    escaped = sum(1 for slug, at in incidents
                  if slug in released_at and at >= released_at[slug])
    return Measurement("quality", float(escaped), len(released_at),
                       {"defects_after_release": escaped,
                        "released_products": len(released_at),
                        "incidents_with_product": len(incidents)})


def measure_market_radar(db, *, now: datetime | None = None):
    """age of the most recent BenchmarkObservation, in hours."""
    from sqlalchemy import func, select

    from ..core.models import BenchmarkObservation

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        newest = s.scalar(select(func.max(BenchmarkObservation.at)))
        count = s.scalar(select(func.count()).select_from(BenchmarkObservation)) or 0
    if newest is None or not count:
        return NotMeasured("market_radar", "no BenchmarkObservation has been recorded yet")
    hours = max(0.0, (now - _aware(newest)).total_seconds() / 3600.0)
    return Measurement("market_radar", round(hours, 3), int(count),
                       {"newest_at": _aware(newest).isoformat()})


def measure_creative_assets(db, *, now: datetime | None = None):
    """ListingAsset rows not approved against total."""
    from sqlalchemy import select

    from ..core.models import ListingAsset

    with db.session() as s:
        rows = list(s.scalars(select(ListingAsset)))
    if not rows:
        return NotMeasured("creative_assets", "no ListingAsset has been built yet")
    blocked = sum(1 for r in rows if not r.approved)
    return Measurement("creative_assets", blocked / len(rows), len(rows),
                       {"blocked": blocked, "assets": len(rows)})


def keyword_cluster(phrase: str) -> str:
    """The search a phrase answers, with the words that say nothing about it removed."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", (phrase or "").lower())
              if t not in _KEYWORD_NOISE]
    return " ".join(sorted(set(tokens))) or "generic"


def measure_seo_search(db, *, now: datetime | None = None):
    """Keyword rows grouped by cluster."""
    from sqlalchemy import select

    from ..core.models import Keyword

    with db.session() as s:
        phrases = [k.phrase for k in s.scalars(select(Keyword))]
    if not phrases:
        return NotMeasured("seo_search", "no Keyword row exists yet")
    clusters = {keyword_cluster(p) for p in phrases}
    return Measurement("seo_search", float(len(clusters)), len(phrases),
                       {"clusters": len(clusters), "keywords": len(phrases)})


def measure_runtime(db, *, now: datetime | None = None):
    """Job rows in the dead state per day, over the days the job table spans."""
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        total = s.scalar(select(func.count()).select_from(Job)) or 0
        dead = s.scalar(select(func.count()).select_from(Job)
                        .where(Job.status == JobStatus.DEAD)) or 0
        first = s.scalar(select(func.min(Job.created_at)))
    if not total or first is None:
        return NotMeasured("runtime", "no Job has been queued yet")
    days = max(1.0, (now - _aware(first)).total_seconds() / 86400.0)
    return Measurement("runtime", round(dead / days, 4), int(total),
                       {"dead": int(dead), "jobs": int(total), "days": round(days, 2)})


def measure_product_creativity(db, *, now: datetime | None = None):
    """creative/tournament.scorecard over recorded tournaments, read off the audit rows.

    Survival alone would reward a lenient jury (#94), so the number is the survival rate and
    the detail carries the research kill rate beside it: a rising survival rate with a
    falling kill rate is a jury going soft, not a company getting better.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = [a.detail or {} for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "creative.tournament").order_by(AuditLog.id))]
    judged = []
    for detail in rows:
        generated = int(((detail.get("field") or {}).get("generated")) or 0)
        if generated <= 0:
            continue
        survivors = detail.get("survivors")
        survived = len(survivors) if isinstance(survivors, list) else 0
        judged.append((survived / generated, detail.get("research_kill_rate")))
    if not judged:
        return NotMeasured("product_creativity",
                           "no creative tournament has generated a field yet")
    rates = [r for r, _ in judged]
    kills = [k for _, k in judged if isinstance(k, (int, float))]
    return Measurement("product_creativity", round(sum(rates) / len(rates), 4), len(judged),
                       {"tournaments": len(judged),
                        "latest_survival_rate": round(rates[-1], 4),
                        "mean_research_kill_rate": (round(sum(kills) / len(kills), 4)
                                                    if kills else None)})


def _revenue(db) -> list[tuple[str, float, float, float, str]]:
    from sqlalchemy import select

    from ..core.models import LedgerEntry

    with db.session() as s:
        return [(r.category, float(r.gross_cad or 0.0), float(r.fees_cad or 0.0),
                 float(r.refunds_cad or 0.0), r.evidence_ref or "")
                for r in s.scalars(select(LedgerEntry)) if (r.gross_cad or 0.0) > 0]


def measure_pricing(db, *, now: datetime | None = None):
    """LedgerEntry net against gross."""
    sales = _revenue(db)
    if not sales:
        return NotMeasured("pricing", "data-gated: needs LedgerEntry revenue rows (a sale)")
    gross = sum(g for _, g, _, _, _ in sales)
    net = sum(g - f - r for _, g, f, r, _ in sales)
    return Measurement("pricing", round(net / gross, 4), len(sales),
                       {"gross_cad": round(gross, 2), "net_cad": round(net, 2)})


def measure_customer_experience(db, *, now: datetime | None = None):
    """SupportCase rows against orders, where an order is a revenue-bearing ledger row."""
    from sqlalchemy import func, select

    from ..core.models import SupportCase

    sales = _revenue(db)
    if not sales:
        return NotMeasured("customer_experience",
                           "data-gated: needs LedgerEntry revenue rows (an order)")
    with db.session() as s:
        cases = s.scalar(select(func.count()).select_from(SupportCase)) or 0
    return Measurement("customer_experience", round(cases / len(sales), 4), len(sales),
                       {"support_cases": int(cases), "orders": len(sales)})


def measure_portfolio(db, *, now: datetime | None = None):
    """LedgerEntry revenue grouped by product, via the evidence reference each row carries."""
    sales = [(g, ref) for _, g, _, _, ref in _revenue(db)]
    if not sales:
        return NotMeasured("portfolio", "data-gated: needs LedgerEntry revenue rows")
    attributed = [(g, ref) for g, ref in sales if ref]
    if not attributed:
        return NotMeasured("portfolio",
                           "data-gated: needs LedgerEntry revenue attributed to a product "
                           "through evidence_ref", read=len(sales))
    by_product: dict[str, float] = {}
    for g, ref in attributed:
        by_product[ref] = by_product.get(ref, 0.0) + g
    total = sum(by_product.values())
    top = max(by_product.values())
    return Measurement("portfolio", round(top / total, 4), len(attributed),
                       {"products": len(by_product), "total_cad": round(total, 2)})


def measure_finance(db, *, now: datetime | None = None):
    """forecast against LedgerEntry by month: absent a recorded forecast, unmeasurable."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    sales = _revenue(db)
    if not sales:
        return NotMeasured("finance", "data-gated: needs LedgerEntry revenue rows")
    with db.session() as s:
        forecasts = [a.detail or {} for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "finance.forecast"))]
    forecast_total = sum(float(f.get("forecast_cad") or 0.0) for f in forecasts)
    if not forecasts or forecast_total <= 0:
        return NotMeasured("finance",
                           "data-gated: needs a recorded finance.forecast to compare "
                           "revenue against", read=len(sales))
    actual = sum(g for _, g, _, _, _ in sales)
    return Measurement("finance", round(abs(actual - forecast_total) / forecast_total, 4),
                       len(sales), {"forecast_cad": round(forecast_total, 2),
                                    "actual_cad": round(actual, 2)})


def measure_growth(db, *, now: datetime | None = None):
    """growth loop registry entries carrying measured traffic."""
    from sqlalchemy import select

    from ..core.models import GrowthLoop

    with db.session() as s:
        loops = [(l.key, int(l.visits or 0), int(l.orders or 0))
                 for l in s.scalars(select(GrowthLoop))]
    if not loops:
        return NotMeasured("growth", "data-gated: needs GrowthLoop rows")
    with_evidence = [k for k, v, o in loops if v > 0 or o > 0]
    if not with_evidence:
        return NotMeasured("growth",
                           "data-gated: needs GrowthLoop traffic evidence (visits or orders)",
                           read=len(loops))
    return Measurement("growth", float(len(with_evidence)), len(loops),
                       {"loops": len(loops), "with_evidence": with_evidence})


MEASURERS: dict[str, Callable] = {
    "product_creativity": measure_product_creativity,
    "pattern_engineering": measure_pattern_engineering,
    "quality": measure_quality,
    "market_radar": measure_market_radar,
    "pricing": measure_pricing,
    "creative_assets": measure_creative_assets,
    "seo_search": measure_seo_search,
    "growth": measure_growth,
    "customer_experience": measure_customer_experience,
    "portfolio": measure_portfolio,
    "finance": measure_finance,
    "runtime": measure_runtime,
}

assert set(MEASURERS) == {c.key for c in CELLS}, "every cell has exactly one measurer"


# ---------------------------------------------------------------------------
# Running them


def measure_cell(db, cell: str, *, now: datetime | None = None):
    """One cell's measurement, or the stated reason there is none."""
    if cell not in MEASURERS:
        raise MeasureRefused(f"unknown cell {cell!r}: {sorted(MEASURERS)}")
    return MEASURERS[cell](db, now=now)


def measure_all(db, *, now: datetime | None = None) -> dict:
    """Every cell, read but not recorded."""
    measured, skipped = [], {}
    for cell in CELLS:
        out = measure_cell(db, cell.key, now=now)
        if isinstance(out, Measurement):
            measured.append(out)
        else:
            skipped[cell.key] = {"reason": out.reason, "read": out.read}
    return {"measured": measured, "skipped": skipped}


def _last_readings(db) -> dict[str, tuple[float, int]]:
    """The newest point this measurer wrote for each cell, as (value, sample)."""
    from sqlalchemy import select

    from ..core.models import CapabilityPoint

    out: dict[str, tuple[float, int]] = {}
    with db.session() as s:
        for p in s.scalars(select(CapabilityPoint).order_by(CapabilityPoint.id)):
            if (p.detail or {}).get("from") == SOURCE:
                out[p.cell] = (round(float(p.value), 9), int(p.sample))
    return out


def record_all(db, *, now: datetime | None = None) -> dict:
    """Measure every cell and write a CapabilityPoint for each that has a number.

    Returns what was read and what was recorded, in the shape the nightly INGEST stage
    reports: `read` is the rows every measurer looked at, `found` is the points written. A
    night with twelve empty sources reads zero and is `did_not_run`, which is the honest
    reading of a shadow-mode company and the one this replaces.
    """
    from .cells import record_capability

    out = measure_all(db, now=now)
    previous = _last_readings(db)
    recorded, repeated = [], []
    for m in out["measured"]:
        # The same number over the same rows is the same reading, not a new one. Written
        # again it would fill the history with copies, and three copies of one number is
        # exactly what the plateau detector reads as a flat capability (#104) -- a defect
        # manufactured by the measuring schedule rather than by the company.
        if previous.get(m.cell) == (round(m.value, 9), m.sample):
            repeated.append(m.cell)
            continue
        point_id = record_capability(
            db, m.cell, m.value, sample=m.sample,
            detail={"from": SOURCE, "sample": m.sample, **m.detail})
        recorded.append({"cell": m.cell, "value": m.value, "sample": m.sample,
                         "point_id": point_id})
    read = sum(m.sample for m in out["measured"]) + sum(
        v["read"] for v in out["skipped"].values())
    return {
        "recorded": recorded,
        "repeated": repeated,
        "skipped": out["skipped"],
        "read": read,
        "found": len(recorded),
        "cells": len(CELLS),
        "note": (f"{len(recorded)} of {len(CELLS)} cells produced a new reading and "
                 f"{len(repeated)} repeated their last one unchanged; the rest name the table "
                 f"that has to fill first. A first measurement is a baseline, never a win"),
    }


def state() -> dict:
    return {
        "source": SOURCE,
        "measurers": {c.key: c.measure for c in CELLS},
        "rules": [
            "an empty source records nothing: a first measurement is a baseline, never a win",
            "a data-gated cell names the table that has to fill before its number exists",
            "the same query every night, with no model, no randomness and no memory",
        ],
    }
