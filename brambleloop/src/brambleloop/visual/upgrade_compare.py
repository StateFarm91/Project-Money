"""F-738: identity-preserving promotion of a canonical-model improvement (and the F-737 cell).

A realism improvement to Laura's visual system (a new provider, prompt, pack procedure or
repaired portrait) may be proposed to the owner only when it is at least as much Laura as
what it would replace, and more real. This module is the comparator. It decides whether a
challenger may be *proposed*; it never adopts one. Replacing or re-freezing Laura still
needs an owner decision listed in `canonical.AUTHORISED_IDENTITY_CHANGES` (D-FB-11/D-FB-14),
and nothing here writes to the registry, the pack or the canonical files.

Inputs are readings already made by the existing judges, never a fresh opinion:
* identity: per-dimension verdicts against the canonical pack (`identity.drift_check`'s
  `dimensions`, match / drift / unmeasurable);
* realism: `photoreal.gate` output (checks True/False; unmade = unjudged).

A challenger is refused when any of these holds:
* it is not Laura (`canonical.laura_verdict`: any drift, or a locked face dimension
  unread);
* its identity retention (matched share of the drift dimensions) is below the incumbent's;
* its realism is not strictly better (more checks sound), or it fails a check the incumbent
  passed;
* either reading is missing.
Otherwise it is proposed, and `file_owner_card` raises one owner card for the decision.
"""
from __future__ import annotations

ACTION = "visual.canonical_upgrade_compared"
CARD_KEY = "canonical_model_upgrade"


def retention(dimensions: dict) -> float | None:
    """Share of the drift dimensions read as a match; None when nothing was readable."""
    from . import identity

    dims = [str((dimensions or {}).get(d) or identity.UNMEASURABLE) for d in
            identity.DRIFT_DIMENSIONS]
    if not any(v in (identity.MATCH, identity.DRIFT) for v in dims):
        return None
    return round(sum(1 for v in dims if v == identity.MATCH) / len(dims), 4)


def _realism(gate: dict | None) -> dict:
    checks = dict((gate or {}).get("checks") or {})
    return {"sound": sorted(k for k, v in checks.items() if v is True),
            "failed": sorted(k for k, v in checks.items() if v is False),
            "verdict": (gate or {}).get("verdict")}


def compare(incumbent: dict, challenger: dict) -> dict:
    """{verdict: propose|refuse, reasons, ...} for a challenger against the incumbent.

    Each side is {"label", "identity": {dimension: verdict}, "realism": photoreal.gate(...)}.
    """
    from . import canonical

    reasons: list[str] = []
    ch_id, inc_id = challenger.get("identity"), incumbent.get("identity")
    if not ch_id or not inc_id:
        reasons.append("an identity reading is missing; unmeasured is not retained")
    laura = canonical.laura_verdict(ch_id or {})
    if laura["verdict"] != "laura":
        reasons.append(f"the challenger is not Laura ({laura['verdict']}): {laura['why']}")
    r_ch, r_inc = retention(ch_id or {}), retention(inc_id or {})
    if r_ch is None or r_inc is None:
        reasons.append("identity retention could not be measured on both sides")
    elif r_ch < r_inc:
        reasons.append(f"identity retention fell from {r_inc} to {r_ch}; a realism win never "
                       f"buys identity loss")
    real_ch, real_inc = _realism(challenger.get("realism")), _realism(incumbent.get("realism"))
    if challenger.get("realism") is None or incumbent.get("realism") is None:
        reasons.append("a realism reading is missing")
    else:
        lost = sorted(set(real_inc["sound"]) & set(real_ch["failed"]))
        if lost:
            reasons.append(f"the challenger fails realism checks the incumbent passed: {lost}")
        if len(real_ch["sound"]) <= len(real_inc["sound"]):
            reasons.append(f"realism did not improve ({len(real_inc['sound'])} -> "
                           f"{len(real_ch['sound'])} sound checks)")
    verdict = "refuse" if reasons else "propose"
    return {"verdict": verdict, "reasons": reasons,
            "incumbent": incumbent.get("label"), "challenger": challenger.get("label"),
            "retention": {"incumbent": r_inc, "challenger": r_ch},
            "realism_sound": {"incumbent": len(real_inc["sound"]),
                              "challenger": len(real_ch["sound"])},
            "laura": laura["verdict"],
            "adopts_nothing": ("a proposal is a card for the owner. Replacing or re-freezing "
                               "Laura needs an owner decision in "
                               "canonical.AUTHORISED_IDENTITY_CHANGES")}


def file_owner_card(db, comparison: dict) -> dict:
    """Record the comparison; raise one owner card when (and only when) it is a proposal."""
    from sqlalchemy import select

    from ..core.models import AuditLog, OwnerAction

    with db.session() as s:
        s.add(AuditLog(actor="quality_director", action=ACTION,
                       artifact=str(comparison.get("challenger") or ""), detail=comparison))
        if comparison.get("verdict") != "propose":
            return {"card": False, "why": "refused: " + "; ".join(comparison["reasons"])[:300]}
        open_card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == CARD_KEY, OwnerAction.done == False))  # noqa: E712
        if open_card is not None:
            return {"card": False, "why": "an upgrade card is already open", "id": open_card.id}
        s.add(OwnerAction(
            requirement_key=CARD_KEY,
            action=(f"Review a proposed improvement to Laura's visual system: "
                    f"{comparison.get('challenger')} over {comparison.get('incumbent')} "
                    f"(identity retention {comparison['retention']['incumbent']} -> "
                    f"{comparison['retention']['challenger']}, realism "
                    f"{comparison['realism_sound']['incumbent']} -> "
                    f"{comparison['realism_sound']['challenger']} sound checks). Adopting it "
                    f"needs your recorded decision (AUTHORISED_IDENTITY_CHANGES)"),
            reason=("F-738: identity retention is equal or better and realism improved, judged "
                    "on recorded readings; nothing has been adopted"),
            max_cost_cad=0.0, minutes=10,
            consequence_of_delay="the incumbent stays canonical; nothing degrades",
            blocks="F-737/F-738 canonical model improvement"))
    return {"card": True}
