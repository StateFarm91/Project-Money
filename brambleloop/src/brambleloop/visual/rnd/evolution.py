"""The "three-month evolution" report (owner D-FB-16 item 5): is Visual materially better?

So the owner never has to ask "make the pictures better", the department reports its own
evolution over a rolling window (default 90 days), per product class, from rows only:

* pipeline generations created / promoted in the window and the current generation;
* techniques promoted, rejected, rolled back, overturned (pipeline experiments + hero
  challengers), and paid challengers waiting on spend authority;
* the hero: current treatment, its basis (PROXY vs MARKET), proxy trust;
* the commercial trend: CTR and conversion per 30-day bucket from `ListingOutcome` rows
  credited to the class's hero styles -- MEASURED or UNKNOWN, never 0;
* a verdict: `materially_better` only when the marketplace says so (first vs last measured
  bucket CTR up by a significant margin); otherwise IMPROVING_INTERNALLY (proxy/gate evidence
  only) or UNKNOWN. Internal progress is never presented as commercial progress.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 90
BUCKET_DAYS = 30


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _unknown(why: str) -> dict:
    return {"value": None, "reading": "UNKNOWN", "why": why}


def report(db, *, now: datetime | None = None, days: int = WINDOW_DAYS) -> dict:
    """Never raises; UNKNOWN when the department has not run."""
    try:
        return _report(db, now=now, days=days)
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNKNOWN", "reason": f"evolution unreadable: {type(exc).__name__}: "
                                               f"{str(exc)[:200]}", "classes": {}}


def _report(db, *, now, days) -> dict:
    from sqlalchemy import select

    from . import commercial as C
    from . import hero as H
    from . import loop as L
    from . import models as M
    from . import pipeline as P

    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    if not M.tables_exist(db):
        return {"status": "UNKNOWN", "reason": "Visual R&D has not run yet", "classes": {},
                "window_days": days}
    with M.session(db) as s:
        versions = list(s.scalars(select(M.VisualPipelineVersion)))
        exps = list(s.scalars(select(M.VisualExperiment)))
    heroes_all = H.variants(db)
    classes = {}
    for cls in P.PRODUCT_CLASSES:
        vs = [v for v in versions if v.product_class == cls]
        inc = next((v for v in vs if v.state == P.INCUMBENT), None)
        ex = [e for e in exps if e.product_class == cls
              and _aware(e.decided_at or e.created_at) >= start]
        hv = [h for h in heroes_all if h["product_class"] == cls]
        hv_win = [h for h in hv if h["decided_at"] and
                  datetime.fromisoformat(h["decided_at"]) >= start]
        lessons = [les for les in L.lessons(db, cls, limit=500)
                   if datetime.fromisoformat(les["at"]) >= start]
        promoted = ([{"technique": e.varied, "kind": "pipeline", "experiment": e.id}
                     for e in ex if e.state == "PROMOTED"]
                    + [{"technique": (les["params"] or {}).get("treatment"), "kind": "hero",
                        "basis": (les["params"] or {}).get("basis", "proxy")}
                       for les in lessons if les["kind"] == "hero_promoted"])
        buckets = []
        for i in range(max(1, days // BUCKET_DAYS)):
            b0 = start + timedelta(days=i * BUCKET_DAYS)
            b1 = b0 + timedelta(days=BUCKET_DAYS)
            rows = C.outcome_rows(db, product_class=cls, since=b0.date().isoformat(),
                                  until=b1.date().isoformat())
            f = C.funnel(rows)
            buckets.append({"from": b0.date().isoformat(), "to": b1.date().isoformat(),
                            "ctr": f["ctr"], "conversion": f["conversion"],
                            "impressions": f["impressions"], "periods": f["periods"]})
        measured = [b for b in buckets if b["ctr"]["value"] is not None]
        if len(measured) >= 2:
            a, b = measured[0], measured[-1]
            z = L._z(b["ctr"]["numerator"], b["ctr"]["denominator"], a["ctr"]["numerator"],
                     a["ctr"]["denominator"])
            if z is not None and z >= L.MARKET_Z:
                verdict = "MATERIALLY_BETTER"
            elif z is not None and z <= -L.MARKET_Z:
                verdict = "WORSE"
            else:
                verdict = "NO_SIGNIFICANT_CHANGE"
            trend = {"first_ctr": a["ctr"]["value"], "last_ctr": b["ctr"]["value"],
                     "z": None if z is None else round(z, 3), "reading": "MEASURED"}
        else:
            internal = bool(promoted)
            verdict = "IMPROVING_INTERNALLY" if internal else "UNKNOWN"
            trend = _unknown("fewer than two 30-day buckets with measured CTR (no live "
                             "listings / exports credited to this class's heroes yet)")
        classes[cls] = {
            "pipeline_generation": inc.generation if inc is not None else None,
            "pipeline_versions_in_window": sum(1 for v in vs if _aware(v.created_at) >= start),
            "promoted_techniques": promoted,
            "rejected": sum(1 for e in ex if e.state == "REJECTED")
            + sum(1 for h in hv_win if h["state"] == H.REJECTED),
            "rolled_back": sum(1 for e in ex if e.state == "ROLLED_BACK"),
            "overturned": sum(1 for e in ex if e.state == "OVERTURNED")
            + sum(1 for h in hv_win if h["state"] == H.OVERTURNED),
            "hero": H.status(db, cls)["incumbent"],
            "hero_challengers_evaluated": sum(1 for h in hv if h["execution"] == P.DETERMINISTIC
                                              and h["objective"].get("value") is not None),
            "paid_challengers_waiting": [h["treatment"] for h in hv
                                         if h["state"] == H.GATED_SPEND],
            "proxy_trust": H.trust(db, cls, now=now)["desirability"],
            "ctr_conversion_by_month": buckets,
            "ctr_trend": trend,
            "verdict": verdict,
        }
    verdicts = [c["verdict"] for c in classes.values()]
    return {
        "status": ("MATERIALLY_BETTER" if "MATERIALLY_BETTER" in verdicts else
                   "IMPROVING_INTERNALLY" if "IMPROVING_INTERNALLY" in verdicts else "UNKNOWN"),
        "window_days": days, "from": start.isoformat(), "to": now.isoformat(),
        "classes": classes,
        "autonomy": "the loop challenges every class's pipeline and hero on its own cadence "
                    "(visual.rnd.next_work); the owner is only asked for spend authority on "
                    "queued paid challengers",
        "basis_rule": "MATERIALLY_BETTER needs measured marketplace CTR; internal gate/proxy "
                      "gains are reported as IMPROVING_INTERNALLY, never as sales progress",
    }
