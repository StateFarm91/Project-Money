"""Visual R&D status for the Owner Command Center (Visual Learn) and the executive.

Two read-only functions:

* `summary(db)` -- the provider (cross-lane contract: `status`, `as_of`, `basis`, `items`,
  `sources`, never raises). Per product class: pipeline generation/version, experiments by
  state, techniques promoted / rejected / rolled back / overturned, structural rejection trend,
  photorealism trend, Laura identity consistency, accepted-image yield, cost per accepted
  image, latency, benchmark gap, hero CTR, listing conversion, refund rate, and the paid
  challengers queued behind spend authority. UNKNOWN is `None` with a `reading` of
  "UNKNOWN" and the reason -- never 0, never CA$0.00 unless a measured zero.
* `next_work(db)` -- internal, GREEN-only work items for the executive (no spend, no external
  effect). Paid challengers are never work items: they wait for an owner decision.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone

SOURCES = ["visual_rnd_pipelines", "visual_rnd_experiments", "visual_rnd_judgements",
           "visual_rnd_market", "visual_rnd_lessons",
           "src/brambleloop/visual/rnd/loop.py", "src/brambleloop/visual/rnd/gates.py",
           "src/brambleloop/visual/rnd/pipeline.py",
           "src/brambleloop/visual/render_verification.py",
           "src/brambleloop/publish/layout_qa.py", "src/brambleloop/visual/canonical.py",
           "src/brambleloop/improve/invariants.py", "src/brambleloop/improve/league.py"]


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _unknown(why: str) -> dict:
    return {"value": None, "reading": "UNKNOWN", "why": why}


def _measured(value, basis: str = "measured", **extra) -> dict:
    return {"value": value, "reading": "MEASURED", "basis": basis, **extra}


def summary(db) -> dict:
    """The Visual R&D provider. Never raises."""
    try:
        return _summary(db)
    except Exception as exc:  # noqa: BLE001 - a provider reports, it does not crash a page
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": SOURCES,
                "reason": f"visual R&D status unreadable: {type(exc).__name__}: "
                          f"{str(exc)[:200]}"}


def _share(rows, gate: str, ok=("PASS",), skip=("N/A",)):
    vals = [((r.gates or {}).get(gate) or {}).get("status", "UNKNOWN") for r in rows]
    vals = [v for v in vals if v not in skip]
    if not vals:
        return None, 0
    return round(sum(v in ok for v in vals) / len(vals), 4), len(vals)


def _class_item(cls: str, spec: dict, versions, experiments, judgements, market, now) -> dict:
    from . import pipeline as P

    vs = [v for v in versions if v.product_class == cls]
    inc = next((v for v in vs if v.state == P.INCUMBENT), None)
    ex = [e for e in experiments if e.product_class == cls]
    js = [j for j in judgements if j.product_class == cls]
    frames = [j for j in js if not j.subject.endswith(":gallery")]
    prod = [j for j in frames if j.arm == "production"]
    galleries = [j for j in js if j.subject.endswith(":gallery") and j.arm == "production"]
    by_state = dict(Counter(e.state for e in ex))
    labels = {v.id: v.label for v in vs}

    def techniques(state):
        return [{"experiment": e.id, "varied": e.varied, "stage": e.stage,
                 "challenger": labels.get(e.challenger_id), "decided_at":
                 _aware(e.decided_at).isoformat() if e.decided_at else None,
                 "why": ("; ".join((e.result or {}).get("blockers") or [])
                         or (e.result or {}).get("refusals") or "")}
                for e in ex if e.state == state]

    # Structural rejection trend: per version in creation order, share of judged frames
    # (any arm) whose structure gate did not pass.
    trend = []
    for v in vs:
        vf = [j for j in frames if j.pipeline_id == v.id]
        share, n = _share(vf, "structure")
        if n:
            trend.append({"version": v.label, "frames": n,
                          "structural_rejection_share": round(1 - share, 4)})
    photo, photo_n = _share(frames, "photorealism")
    laura, laura_n = _share(frames, "laura_identity")
    yield_ = (round(sum(j.accepted for j in prod) / len(prod), 4) if prod else None)
    accepted = [j for j in prod if j.accepted]
    costs = [j for j in prod]
    if prod and all(j.cost_cad is not None and str(j.cost_basis).startswith("measured")
                    for j in costs):
        total = sum(j.cost_cad for j in costs)
        cpa = (_measured(round(total / len(accepted), 4),
                         basis="measured (" + sorted({j.cost_basis for j in costs})[0] + ")",
                         currency="CAD", accepted_images=len(accepted))
               if accepted else _unknown("no accepted image yet"))
    else:
        cpa = _unknown("no production image with a measured cost" if not prod else
                       "some production costs are estimated or unknown")
    lat = [j.latency_s for j in prod if j.latency_s is not None]
    mk = [m for m in market if inc is not None and m.pipeline_id == inc.id]

    def _rate(num, den, label):
        n = [getattr(m, num) for m in mk if getattr(m, num) is not None]
        d = [getattr(m, den) for m in mk if getattr(m, den) is not None]
        if not n or not d or not sum(d):
            return _unknown(f"no marketplace {label} reading for the incumbent version yet "
                            f"(slow loop waiting for real listings)")
        return _measured(round(sum(n) / sum(d), 4), basis="measured (marketplace export)",
                         numerator=sum(n), denominator=sum(d))

    paid = [{"experiment": e.id, "varied": e.varied, "stage": e.stage,
             "estimated_cost_cad": e.estimated_cost_cad,
             "cost_basis": (e.result or {}).get("cost_basis"),
             "waiting_on": "owner spend authority for Visual R&D (paid generation)"}
            for e in ex if e.state == "GATED_SPEND"]
    promotions = [v for v in vs if v.promoted_at is not None and v.parent_id is not None]
    return {
        "product_class": cls, "title": spec["title"],
        "pipeline": (None if inc is None else
                     {"version_id": inc.id, "label": inc.label, "generation": inc.generation,
                      "params": inc.params, "since": _aware(inc.promoted_at).isoformat()
                      if inc.promoted_at else None}),
        "versions_total": len(vs), "promotions_total": len(promotions),
        "experiments_by_state": by_state, "experiments_total": len(ex),
        "promoted": techniques("PROMOTED"), "rejected": techniques("REJECTED"),
        "rolled_back": techniques("ROLLED_BACK"), "overturned": techniques("OVERTURNED"),
        "refused": techniques("REFUSED"),
        "structural_rejection_trend": trend or _unknown("no frame judged yet"),
        "photorealism_trend": (_measured(photo, frames=photo_n) if photo is not None else
                               _unknown("no photographic/generated frame judged: disclosed "
                                        "renders are not judged for realism (D-FB-9); the "
                                        "generated path is queued behind spend authority")),
        "laura_identity_consistency": (_measured(laura, frames=laura_n) if laura is not None
                                       else _unknown("no Laura-bearing frame judged")),
        "accepted_image_yield": (_measured(yield_, frames=len(prod)) if yield_ is not None
                                 else _unknown("no production frame judged")),
        "cost_per_accepted_image": cpa,
        "latency_s_median": (_measured(round(statistics.median(lat), 4), frames=len(lat))
                             if lat else _unknown("no production latency measured")),
        "task_score_mean": (_measured(round(sum(g.score or 0 for g in galleries)
                                            / len(galleries), 4), galleries=len(galleries))
                            if galleries else _unknown("no production gallery judged")),
        "benchmark_gap": _unknown("blind benchmark needs observed competitor galleries and a "
                                  "blind vision review (data + image_vision gated)"),
        "hero_ctr": _rate("clicks", "impressions", "CTR"),
        "listing_conversion": _rate("purchases", "clicks", "conversion"),
        "refund_rate": _rate("refunds", "purchases", "refund"),
        "paid_challengers_gated": paid,
    }


def _summary(db) -> dict:
    from sqlalchemy import select

    from . import models as M
    from . import pipeline as P

    if not M.tables_exist(db):
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": SOURCES,
                "reason": "Visual R&D has not run yet: its tables do not exist (first "
                          "visual.rnd cycle creates them)"}
    now = datetime.now(timezone.utc)
    with M.session(db) as s:
        versions = list(s.scalars(select(M.VisualPipelineVersion)))
        experiments = list(s.scalars(select(M.VisualExperiment)))
        judgements = list(s.scalars(select(M.VisualJudgement)))
        market = list(s.scalars(select(M.VisualMarketEvidence)))
        lessons_n = len(list(s.scalars(select(M.VisualLesson.id))))
        items = [_class_item(cls, spec, versions, experiments, judgements, market, now)
                 for cls, spec in P.PRODUCT_CLASSES.items()]
    stamps = [_aware(x) for x in ([v.created_at for v in versions]
                                  + [e.decided_at or e.created_at for e in experiments]
                                  + [j.at for j in judgements] + [m.at for m in market])
              if x is not None]
    if not judgements and not experiments:
        status, reason = "UNKNOWN", "no image has been judged and no experiment run yet"
    else:
        unmeasured = [i["product_class"] for i in items
                      if i["accepted_image_yield"]["reading"] == "UNKNOWN"]
        no_market = not market
        status = "DEGRADED" if (unmeasured or no_market) else "OK"
        bits = []
        if unmeasured:
            bits.append(f"{len(unmeasured)} of {len(items)} classes have no judged production "
                        f"image (no free producer; generated path gated on spend)")
        if no_market:
            bits.append("slow loop has no marketplace evidence yet (no live listings)")
        reason = "; ".join(bits) or "every class judged and marketplace evidence present"
    by_state = Counter(e.state for e in experiments)
    from .loop import lessons, paid_execution_gate
    return {
        "status": status, "reason": reason,
        "as_of": max(stamps).isoformat() if stamps else None,
        "basis": "measured" if judgements else "unknown",
        "items": items,
        "totals": {
            "pipeline_versions": len(versions),
            "promotions": sum(i["promotions_total"] for i in items),
            "experiments": len(experiments), "experiments_by_state": dict(by_state),
            "judged_images": sum(1 for j in judgements if not j.subject.endswith(":gallery")),
            "marketplace_readings": len(market), "lessons": lessons_n,
            "paid_challengers_gated": by_state.get("GATED_SPEND", 0),
        },
        "loop": ["GENERATE", "PRODUCT TRUTH", "STRUCTURAL/IDENTITY VALIDATION", "PHOTOREALISM",
                 "COMMERCIAL/BLIND BENCHMARK", "FAILURE DIAGNOSIS", "CHALLENGER",
                 "CONTROLLED TEST", "PROMOTE/REJECT", "MONITOR", "ROLLBACK IF WORSE",
                 "PERSIST LESSON", "AFFECT FUTURE GENERATION"],
        "gates": list(P.GATES), "advisory_gates": sorted(P.ADVISORY_GATES),
        "tunables": [t.to_dict() for t in P.TUNABLES.values()],
        "lessons": lessons(db, limit=10),
        "spend": {"paid_execution": paid_execution_gate()},
        "commercial": _commercial(db),
        "evolution": _evolution(db),
        "sources": SOURCES + COMMERCIAL_SOURCES,
    }


COMMERCIAL_SOURCES = ["visual_rnd_hero_variants", "listing_outcomes",
                      "src/brambleloop/visual/rnd/sequence.py",
                      "src/brambleloop/visual/rnd/objective.py",
                      "src/brambleloop/visual/rnd/judges.py",
                      "src/brambleloop/visual/rnd/hero.py",
                      "src/brambleloop/visual/rnd/commercial.py",
                      "src/brambleloop/visual/rnd/evolution.py"]


def _commercial(db) -> dict:
    """The commercial merchandising objective: sequence policy, objective, PROXY judges and
    each class's hero (incumbent, basis, trust, funnel). Never raises."""
    try:
        from . import hero as H
        from . import judges as J
        from . import objective as O
        from . import pipeline as P
        from . import sequence as Q

        return {"objective": O.describe(), "sequence_policy": Q.describe(),
                "judges": J.describe(),
                "heroes": {c: H.status(db, c) for c in P.PRODUCT_CLASSES}}
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNKNOWN", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _evolution(db) -> dict:
    from .evolution import report

    return report(db)


# ---- next_work -------------------------------------------------------------------------------

def _item(kind: str, key: str, priority: int, reason: str, evidence: dict) -> dict:
    return {"kind": kind, "key": key, "priority": int(priority), "reason": reason,
            "evidence": evidence, "department": "visual", "job_type": "visual.rnd.cycle",
            "green": True}


def next_work(db) -> list[dict]:
    """Internal GREEN work for the Visual department, most urgent first. Read-only.

    Contract (same shape as `learn.improvement_status.next_work`): kind, key (stable
    idempotency key), priority 1..100, reason, evidence, department "visual", job_type
    ("visual.rnd.cycle" -- one handler runs the whole cycle for the named class), green True.
    Kinds: visual.rnd.monitor (75), visual.rnd.hero_calibrate (72), visual.rnd.calibrate (70),
    visual.rnd.judge_production (60), visual.rnd.hero_challenge (55), visual.rnd.experiment
    (50), visual.rnd.bootstrap (40). Paid challengers never appear.
    """
    try:
        return _next_work(db)
    except Exception as exc:  # noqa: BLE001
        return [_item("visual.rnd.provider_error", "visual.rnd.provider_error", 10,
                      f"visual R&D unreadable: {type(exc).__name__}", {"error": str(exc)[:200]})]


def _classes_with_products() -> dict[str, list[str]]:
    from ...products import launch0
    from . import pipeline as P

    out: dict[str, list[str]] = {}
    for b in sorted(launch0.BUILDERS):
        out.setdefault(P.classify(b.replace("_", " ")), []).append(b)
    return out


def _next_work(db) -> list[dict]:
    from sqlalchemy import select

    from . import models as M
    from . import pipeline as P

    stocked = {c: b for c, b in _classes_with_products().items() if c in P.PRODUCT_CLASSES}
    if not M.tables_exist(db):
        return [_item("visual.rnd.bootstrap", "visual.rnd.bootstrap", 40,
                      "Visual R&D has no state yet; run the first cycle (deterministic, free)",
                      {"classes_with_products": sorted(stocked)})]
    now = datetime.now(timezone.utc)
    items = []
    with M.session(db) as s:
        versions = list(s.scalars(select(M.VisualPipelineVersion)))
        experiments = list(s.scalars(select(M.VisualExperiment)))
        judgements = list(s.scalars(select(M.VisualJudgement)))
        market = list(s.scalars(select(M.VisualMarketEvidence)))
    from . import commercial as C
    from . import hero as H

    hero_rows = H.variants(db)
    for cls in P.PRODUCT_CLASSES:
        hinc = next((h for h in reversed(hero_rows) if h["product_class"] == cls
                     and h["state"] == H.INCUMBENT), None)
        if hinc is not None and hinc["parent_id"] is not None and hinc["basis"] == "proxy":
            par = next((h for h in hero_rows if h["id"] == hinc["parent_id"]), None)
            ra = C.outcome_rows(db, style_key=hinc["style_key"])
            rb = C.outcome_rows(db, style_key=par["style_key"]) if par else []
            if ra and rb:
                items.append(_item("visual.rnd.hero_calibrate",
                                   f"visual.rnd.hero_calibrate:{hinc['id']}:"
                                   f"{len(ra) + len(rb)}", 72,
                                   f"{cls}: marketplace outcomes exist for the proxy-promoted "
                                   f"hero and the hero it replaced; confirm or overturn",
                                   {"product_class": cls, "hero": hinc["id"]}))
        inc = next((v for v in versions if v.product_class == cls and v.state == P.INCUMBENT),
                   None)
        prod = [j for j in judgements if inc is not None and j.pipeline_id == inc.id
                and j.arm == "production"]
        if inc is not None and inc.parent_id is not None and inc.promoted_on:
            exp = next((e for e in experiments if e.challenger_id == inc.id), None)
            mark = ((exp.result or {}).get("monitored_through") if exp is not None else None) or 0
            since = [j for j in prod if _aware(j.at) >= _aware(inc.promoted_at) and j.id > mark]
            if since:
                items.append(_item("visual.rnd.monitor", f"visual.rnd.monitor:{inc.id}:"
                                   f"{len(since)}", 75,
                                   f"{cls}: {len(since)} production judgement(s) since "
                                   f"{inc.label} was promoted; retain or roll back",
                                   {"product_class": cls, "version": inc.id}))
            ids = {inc.id, inc.parent_id}
            readings = [m for m in market if m.pipeline_id in ids]
            if {m.pipeline_id for m in readings} == ids:
                items.append(_item("visual.rnd.calibrate", f"visual.rnd.calibrate:{inc.id}:"
                                   f"{len(readings)}", 70,
                                   f"{cls}: marketplace evidence exists for {inc.label} and "
                                   f"the version it replaced; confirm or overturn",
                                   {"product_class": cls, "readings": len(readings)}))
        if cls in stocked:
            if not prod:
                items.append(_item("visual.rnd.judge_production",
                                   f"visual.rnd.judge_production:{cls}:"
                                   f"{inc.id if inc else 0}", 60,
                                   f"{cls}: the incumbent pipeline has no judged production "
                                   f"image", {"product_class": cls, "builds": stocked[cls]}))
            recent = [e for e in experiments if e.product_class == cls
                      and e.execution == P.DETERMINISTIC
                      and now - _aware(e.created_at) < timedelta(hours=24)]
            heroes = [h for h in hero_rows if h["product_class"] == cls
                      and h["execution"] == P.DETERMINISTIC and h["decided_at"]
                      and now - datetime.fromisoformat(h["decided_at"]) < timedelta(hours=24)]
            if not heroes and cls in P.DISCLOSED_CLASSES:
                items.append(_item("visual.rnd.hero_challenge",
                                   f"visual.rnd.hero_challenge:{cls}:{now.date().isoformat()}",
                                   55, f"{cls}: no hero challenger decided in 24 h",
                                   {"product_class": cls}))
            if not recent:
                items.append(_item("visual.rnd.experiment",
                                   f"visual.rnd.experiment:{cls}:{now.date().isoformat()}", 50,
                                   f"{cls}: no deterministic challenger tested in 24 h",
                                   {"product_class": cls}))
    return sorted(items, key=lambda i: (-i["priority"], i["key"]))
