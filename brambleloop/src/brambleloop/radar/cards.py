"""F-673: one opportunity card per concept, joining what four separate systems know about it.

The radar scores a concept, the market arbitrage scores its department, the culture/rights
router decides which lane it may use, and pre-production decides what experiment comes next.
Each was readable on its own route; nobody could see the four together for one concept, so a
high radar score on a concept whose department was unmeasured and whose title routed to the
original lane read the same as a clean one.

A card never fills a missing reading: arbitrage with no rankable market score is
`UNMEASURED`, and interest with no platform observation is `UNMEASURED`. Read-only.
"""
from __future__ import annotations

from datetime import date

UNMEASURED = "UNMEASURED"


def _feasibility(seed) -> dict:
    from ..culture import engine, rights

    filed = engine.file_topic(seed.title)
    tokens = list(filed.get("tokens") or []) if filed.get("filed") else []
    routing = rights.route(tokens, intended_use=seed.slug)
    blockers = []
    if routing.lane == rights.ORIGINAL:
        blockers.append("protected element without a recorded basis: original lane only")
    if seed.risk_class == "C":
        blockers.append("Class C: cannot be certified until physical testing exists")
    return {"lane": routing.lane, "may_reach_customers": routing.may_reach_customers,
            "protected": [t.text for t in tokens], "risk_class": seed.risk_class,
            # Unfiled means the cue table does not read the title as a cultural signal, so
            # nothing was declared protected by filing -- said so, not implied clean.
            "filed_as_cultural_signal": bool(filed.get("filed")),
            "blockers": blockers, "feasible": not blockers}


def _arbitrage(pod: str, steer: dict) -> dict:
    card = steer.get(pod)
    if card is None:
        return {"pod": pod, "state": UNMEASURED,
                "why": "no rankable observed market score for this department"}
    return {"pod": pod, "state": "MEASURED", "score": card["score"],
            "confidence": card["confidence"], "measured": card.get("measured")}


def _next_experiment(db, slug: str, gate: dict, feas: dict) -> dict:
    from ..commerce import preproduction_cycle as pc

    if not feas["feasible"]:
        return {"step": "resolve_blockers", "why": "; ".join(feas["blockers"])}
    obs = pc.observed_interest(db, slug)
    if obs:
        return {"step": "engineer", "interest": obs,
                "why": f"platform-reported interest ({obs['source']}) row {obs['row']}"}
    if not gate.get("open"):
        return {"step": "concept_post_waiting", "interest": UNMEASURED,
                "why": f"concept post waits on gate {gate.get('gate')}: {gate.get('how')}"}
    return {"step": "concept_post", "channels": list(pc.CHANNELS), "interest": UNMEASURED,
            "why": "gate open; post the concept and read interest before engineering"}


def cards(db, *, today: date | None = None, limit: int = 20) -> dict:
    from ..commerce import preproduction_cycle as pc
    from . import arbitrage, opportunity

    scored = opportunity.score_pool(today=today)
    try:
        steer = arbitrage.steering(db)
    except Exception:  # noqa: BLE001 - steering already degrades to {}; belt and braces
        steer = {}
    try:
        gate = pc.gate_open(db)
    except Exception as exc:  # noqa: BLE001 - an unreadable gate is closed, by name
        gate = {"gate": pc.GATE, "open": False, "how": f"unreadable: {type(exc).__name__}"}
    out = []
    for c in scored[:limit]:
        feas = _feasibility(c.seed)
        pod = arbitrage.pod_of_concept(c.seed.title, c.seed.category)
        out.append({"slug": c.seed.slug, "title": c.seed.title, "category": c.seed.category,
                    "radar": {"score": c.score, "components": c.components,
                              "notes": list(c.notes)},
                    "arbitrage": _arbitrage(pod, steer),
                    "feasibility": feas,
                    "next_experiment": _next_experiment(db, c.seed.slug, gate, feas)})
    return {"cards": out, "count": len(out), "pool": len(scored),
            "owned_surfaces_gate": gate,
            "unmeasured_arbitrage": sum(x["arbitrage"]["state"] == UNMEASURED for x in out),
            "note": "Missing readings are UNMEASURED by name, never a neutral number."}
