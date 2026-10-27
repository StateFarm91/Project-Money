"""F-601 / F-454 / F-656: the company's departments as records, and their work classes.

**F-601 departments.** The requirement names twelve departments, each owning a mandate,
backlog, KPIs, evidence and an improvement loop. The runtime holds eleven charters
(`autonomy.charters`) and thirteen improvement cells (`improve.cells`). `COMPANY` maps each
named department onto what actually runs -- its charter (mandate, agents, KPIs, evidence
requirement, generatable backlog) and its improvement cells -- and `coverage()` reports,
per department and per element, PRESENT or MISSING with what is missing. A department with no
charter is reported as such; nothing here invents a mandate for it.

**F-454 domains.** The requirement's list of focused domains (Research, Pattern/CIR
Engineering, Visuals, QA, Etsy/Commerce, SEO/Marketing, Catalogue, Analytics, Customer
Experience, Finance/Cost, Reliability, Integration) mapped onto the agents that do the work.

**F-656 work classes.** Every generatable job type is RUN (operations), GROW (growth) or
IMPROVE (self-improvement). `autonomy.orchestrator.tick` pulls RUN first, then GROW, then
IMPROVE, and a department with nothing runnable enters WATCHING -- no job, no tokens -- with
the span recorded in company memory.
"""
from __future__ import annotations

RUN, GROW, IMPROVE, WATCHING = "RUN", "GROW", "IMPROVE", "WATCHING"
PULL_ORDER: tuple[str, ...] = (RUN, GROW, IMPROVE)

# Closed table for every generatable job type (tests/test_w4_fmbatch1_departments.py fails
# on a generatable job type missing here, so a new one is classified deliberately).
WORK_CLASS: dict[str, str] = {
    # GROW: finds or wins demand.
    "radar.score": GROW, "intel.benchmark_refresh": GROW, "scale.trajectory": GROW,
    "seasonal.remerchandising": GROW, "seo.cycle": GROW, "growth.journey": GROW,
    "growth.distribution": GROW, "growth.conclude": GROW, "marketing.ads_readiness": GROW,
    # IMPROVE: changes how the department itself works.
    "autonomy.department_review": IMPROVE, "intel.pod_learning": IMPROVE,
    "creative.outcome_learning": IMPROVE, "visual.rnd.cycle": IMPROVE,
    "improve.mine": IMPROVE, "improve.retrospective": IMPROVE, "improve.measure": IMPROVE,
    "improve.sandbox": IMPROVE, "improve.monitor": IMPROVE, "learn.scan": IMPROVE,
    "physical.upgrade_impact": IMPROVE,
    # RUN: keeps the business operating.
    "autonomy.morning_handoff": RUN, "seasonal.sentinel": RUN, "ops.sentinel": RUN,
    "visual.identity_drift": RUN, "support.triage": RUN, "finance.reconcile": RUN,
    "commerce.order_readings": RUN, "commerce.readings": RUN,
    "finance.escalation_check": RUN, "finance.accounting.cycle": RUN,
    "finance.accounting.period_pack": RUN, "ops.queue_check": RUN,
    "ops.maturity_disagreements": RUN, "ops.slo": RUN,
    # INTEG7 (W4-AGENTS x FMBATCH1): AGENTS' generatable job types, classified on their charters.
    "creative.family_engine": GROW,       # new product families for demand (Product Design)
    "creative.photo_principles": IMPROVE, # F-224: photographic standards from judged galleries
    "research.sweep": IMPROVE,            # the Research Agent's self-trigger (F-401/F-404)
    "gate.quality": RUN,                  # re-verification of certified releases (quality_ops)
    "storefront.review": GROW,            # storefront content proposals (content.draft); no write
}


def work_class(job_type: str) -> str:
    """The class of a job type; an unlisted one is RUN (operations is the safe default --
    it is never deprioritised behind growth or self-improvement by omission)."""
    if job_type in WORK_CLASS:
        return WORK_CLASS[job_type]
    if job_type.startswith(("improve.", "learn.")):
        return IMPROVE
    if job_type.startswith(("growth.", "seo.", "marketing.")):
        return GROW
    return RUN


def pull_rank(job_type: str) -> int:
    return PULL_ORDER.index(work_class(job_type))


# ---- F-601: the twelve named departments ------------------------------------------------

COMPANY: tuple[dict, ...] = (
    {"key": "executive", "name": "Executive", "charter": "executive", "cells": ()},
    {"key": "product_catalogue", "name": "Product / Catalogue", "charter": "product_design",
     "cells": ("product_creativity", "pattern_engineering", "portfolio")},
    {"key": "visual_creative", "name": "Visual / Creative", "charter": "visual",
     "cells": ("creative_assets",)},
    {"key": "etsy_marketplace", "name": "Etsy / Marketplace", "charter": "store_commerce",
     "cells": ("seo_search", "pricing")},
    {"key": "marketing_growth", "name": "Marketing / Growth", "charter": "growth",
     "cells": ("growth",)},
    {"key": "customer_experience", "name": "Customer Experience", "charter": "support",
     "cells": ("customer_experience",)},
    {"key": "finance_accounting", "name": "Finance / Accounting", "charter": "finance",
     "cells": ("finance",)},
    {"key": "analytics_intelligence", "name": "Analytics / Intelligence",
     "charter": None, "cells": (),
     "note": "no analytics charter: measurement is spread across learn (improve.measure) "
             "and the reporting providers; nothing owns an analytics backlog"},
    {"key": "compliance_policy", "name": "Compliance / Policy", "charter": None, "cells": (),
     "note": "the `policy` agent sits inside Product Truth / QA; no charter owns a "
             "compliance mandate, backlog or KPI"},
    {"key": "reliability_engineering", "name": "Reliability / Engineering",
     "charter": "platform", "cells": ("runtime",)},
    {"key": "qa_product_truth", "name": "QA / Product Truth", "charter": "product_truth",
     "cells": ("quality",)},
    {"key": "market_radar_research", "name": "Market Radar / Research",
     "charter": "intelligence", "cells": ("market_radar",)},
)

# ---- F-454: the focused domains and the agents that do the work -------------------------

DOMAINS: dict[str, tuple[str, ...]] = {
    "research": ("market_radar",),
    "pattern_cir_engineering": ("crochet_engineer", "validator"),
    "visuals": ("publishing", "creative_director"),
    "qa": ("quality_director", "asset_truth"),
    "etsy_commerce": ("listing", "store_operator"),
    "seo_marketing": ("growth", "ads"),
    "catalogue": ("creative_director",),
    "analytics": (),
    "customer_experience": ("support",),
    "finance_cost": ("accountant", "cfo", "cost_optimiser"),
    "reliability": ("reliability_engineer", "orchestrator"),
    "integration": (),
}


def coverage(db=None) -> dict:
    """Per named department: mandate, backlog, KPIs, evidence and improvement loop, each
    PRESENT (with where it lives) or MISSING. Read from the running tables, never assumed."""
    from ..improve import cells as cells_mod
    from . import charters

    cell_keys = {c.key for c in cells_mod.CELLS}
    agent_names = None
    if db is not None:
        from ..agents.registry import Registry

        agent_names = {a.name for a in Registry(db).all()}
    rows = []
    for d in COMPANY:
        ch = charters.BY_KEY.get(d["charter"]) if d["charter"] else None
        cells = [c for c in d["cells"] if c in cell_keys]
        el = {
            "mandate": ({"state": "PRESENT", "where": f"charter:{ch.key}", "value": ch.mission}
                        if ch else {"state": "MISSING"}),
            "backlog": ({"state": "PRESENT", "where": f"charter:{ch.key}.generatable",
                         "value": {jt: work_class(jt) for jt in ch.generatable}}
                        if ch and ch.generatable else {"state": "MISSING"}),
            "kpis": ({"state": "PRESENT", "where": f"charter:{ch.key}.kpis",
                      "value": [k.key for k in ch.kpis]
                      + [f"cell:{c}" for c in cells]} if ch and ch.kpis else
                     {"state": "MISSING"}),
            "evidence": ({"state": "PRESENT", "where": f"charter:{ch.key}",
                          "value": ch.evidence_requirement}
                         if ch and ch.evidence_requirement else {"state": "MISSING"}),
            "improvement_loop": ({"state": "PRESENT", "where": "improve.cells",
                                  "value": cells} if cells else {"state": "MISSING"}),
        }
        agents = list(ch.agents) if ch else []
        missing = sorted(k for k, v in el.items() if v["state"] == "MISSING")
        rows.append({"key": d["key"], "name": d["name"], "charter": d["charter"],
                     "agents": agents,
                     "agents_unregistered": (sorted(set(agents) - agent_names)
                                             if agent_names is not None else None),
                     "elements": el, "missing": missing, "complete": not missing,
                     "note": d.get("note")})
    domains = {k: {"agents": list(v), "state": "PRESENT" if v else "MISSING"}
               for k, v in DOMAINS.items()}
    return {"departments": rows,
            "complete": sum(1 for r in rows if r["complete"]), "total": len(rows),
            "incomplete": {r["key"]: r["missing"] for r in rows if not r["complete"]},
            "domains": domains,
            "domains_missing": sorted(k for k, v in domains.items() if not v["agents"]),
            "pull_order": list(PULL_ORDER) + [WATCHING]}
