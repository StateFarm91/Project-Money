"""`improve.commercial_lessons` (analyst): measured listing performance into product decisions.

Daily. Turns export-intake listing outcomes into routed lessons (`improve.commercial_lessons`)
that Market Radar reads where it scores concepts. Reads this database only; no model, network
or spend. With nothing measured it publishes nothing and reports why.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "improve.commercial_lessons"


@handlers.register(JOB_TYPE)
def handle_commercial_lessons(ctx: JobContext) -> dict:
    from ..improve import commercial_lessons as CL

    out = CL.record_lessons(ctx.db)
    # Fields named one by one: W-ADOPT's guard (SECREVIEW F-4) keeps the listing-state
    # literal out of tuples; these are lesson counts, not listing states.
    # Review 6954809399 (LOW): the official reading is audited too, not only the export one.
    ctx.audit(JOB_TYPE, detail={"measurable": out["measurable"], "why": out["why"],
                                "shop": out["shop"], "official": out["official"],
                                "lessons_published": out["published"],
                                "withdrawn": out["withdrawn"]})
    return {"ran": True, "measurable": out["measurable"], "why": out["why"][:300],
            "published": len(out["published"]), "withdrawn": len(out["withdrawn"]),
            "categories": {k: {"state": v["state"], "verdict": v["verdict"]}
                           for k, v in out["categories"].items()},
            "official": {k: out["official"].get(k) for k in (
                "measurable", "why", "denominator", "views_include",
                "attribution_unknown_orders")},
            "work_done": out["work_done"]}
