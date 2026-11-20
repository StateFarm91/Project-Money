"""`learning.knowledge_gaps` (analyst): what the studio cannot yet make, and what would teach it.

Weekly. Counts knowledge gaps across the owner's intended product lines from this database
(certified releases, construction refusals, failed compiles, library coverage) and raises at
most two owner-approval reference-purchase recommendations (`intel.knowledge_gaps`). Reads
rows only; no model, network or spend, and nothing is ever bought.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "learning.knowledge_gaps"


@handlers.register(JOB_TYPE)
def handle_knowledge_gaps(ctx: JobContext) -> dict:
    from ..intel import knowledge_gaps as KG

    out = KG.assess(ctx.db)
    ctx.audit(JOB_TYPE, detail={"as_of": out["as_of"], "gaps": len(out["gaps"]),
                                "top": [g["line"] for g in out["gaps"][:5]],
                                "raised": out["raised"], "held": len(out["held"])})
    return {"ran": True, "gaps": len(out["gaps"]),
            "top": [{"line": g["line"], "score": g["score"]} for g in out["gaps"][:5]],
            "raised": len(out["raised"]), "held": len(out["held"]),
            "unrecommended": len(out["unrecommended"]),
            # A reading recorded is work; a week with no evidence still records its gaps.
            "work_done": bool(out["gaps"]) or bool(out["raised"])}
