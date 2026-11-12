"""`policy.issuer_shadow` (publishing): the standing-policy issuer in SHADOW (WS4-5), and
`policy.stop_watch`: the standing policy's automatic stops (design §5.1).

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
    # WS4 §4.2: hold cards close on evidence (published, or a newer release replaced it).
    out["hold_cards_closed"] = len(standing_issuer.close_settled_holds(ctx.db)["closed"])
    # WS4 Stage D: the G-SHADOW reading (records itself; authorises nothing).
    from ..ops import standing_shadow_gate

    out["g_shadow"] = standing_shadow_gate.g_shadow(ctx.db)["verdict"]
    ctx.audit(JOB_TYPE, detail=out)
    return {**out, "ran": True, "work_done": out["recorded"] + out["hold_cards_closed"]}


STOP_WATCH = "policy.stop_watch"


@handlers.register(STOP_WATCH)
def handle_stop_watch(ctx: JobContext) -> dict:
    """`policy.stop_watch` (publishing, OBSERVE, every 5 min; design §5.1): reads every stop
    condition for each watched standing policy, records one reading per policy, and suspends
    an ACTIVATED policy on any holding condition (sticky, deny-direction only). It signs
    nothing and can only take authority away."""
    from ..ops import standing_stop

    out = standing_stop.run(ctx.db)
    return {**out, "ran": True, "work_done": out["policies"]}
