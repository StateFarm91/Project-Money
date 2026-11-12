"""`policy.issuer_shadow` (publishing): the standing-policy issuer in SHADOW (WS4-5).

Every 6 h. Evaluates each certified release with no Etsy listing against the owner's newest
approved standing policy and records what the issuer WOULD do (`standing_policy.shadow_decision`).
It signs nothing, issues nothing and writes no listing; with no approved policy it records
nothing. Read-only over this database apart from those decision rows; no network, model or
spend.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "policy.issuer_shadow"


@handlers.register(JOB_TYPE)
def handle_issuer_shadow(ctx: JobContext) -> dict:
    from ..ops import standing_issuer

    out = standing_issuer.shadow_run(ctx.db)
    ctx.audit(JOB_TYPE, detail=out)
    return {**out, "ran": True, "work_done": out["recorded"]}
