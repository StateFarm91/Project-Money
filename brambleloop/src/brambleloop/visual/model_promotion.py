"""F-738 Identity-Preserving Promotion (W4-AGENTS cluster C2).

"A proposed model upgrade is promoted only when evidence shows equal-or-better identity
retention plus improved realism/utility. Previous approved assets remain recoverable;
regressions trigger rollback."

`compare(incumbent, candidate)` reads two evidence summaries (`summarise` builds them from the
F-744 model ledger, per canonical version) and answers PROMOTE / REFUSE / UNKNOWN:
* identity retention (share of judged frames whose identity verdict passed) must be >= the
  incumbent's -- a realism win with any identity loss is REFUSED;
* realism must be strictly better;
* fewer than MIN_FRAMES judged frames on either side is UNKNOWN, which never promotes.
PROMOTE is only a recommendation for an owner card: identity changes stay owner decisions
(`visual.canonical.require_identity_change_authorised`, `model_registry.replace_canonical`
retires and never deletes, so earlier approved assets stay recoverable). `regression(after,
before)` says whether a promoted version lost identity or realism -- the rollback trigger.
Deterministic, read-only, CA$0.
"""
from __future__ import annotations

MIN_FRAMES = 5
PASSING = frozenset({"pass", "match", "PASS", "MATCH"})


def summarise(records: list[dict], version: str) -> dict:
    mine = [r for r in records if str(r.get("canonical_version")) == str(version)]
    idj = [r for r in mine if (r.get("identity") or {}).get("verdict") not in (None, "UNKNOWN",
                                                                              "unverifiable")]
    rlj = [r for r in mine if r.get("realism") not in (None, "UNKNOWN", "unverifiable")]
    return {"version": str(version), "frames": len(mine),
            "identity_judged": len(idj),
            "identity_retention": (sum(1 for r in idj if r["identity"]["verdict"] in PASSING)
                                   / len(idj)) if idj else None,
            "realism_judged": len(rlj),
            "realism": (sum(1 for r in rlj if r["realism"] in PASSING) / len(rlj))
            if rlj else None}


def compare(incumbent: dict, candidate: dict) -> dict:
    for side, s in (("incumbent", incumbent), ("candidate", candidate)):
        if (s.get("identity_retention") is None or s.get("realism") is None
                or min(s.get("identity_judged", 0), s.get("realism_judged", 0)) < MIN_FRAMES):
            return {"verdict": "UNKNOWN", "promote": False,
                    "why": f"{side} has fewer than {MIN_FRAMES} judged frames on identity or "
                           f"realism; UNKNOWN never promotes"}
    if candidate["identity_retention"] < incumbent["identity_retention"]:
        return {"verdict": "REFUSE", "promote": False,
                "why": (f"identity retention fell ({incumbent['identity_retention']:.0%} -> "
                        f"{candidate['identity_retention']:.0%}); realism cannot buy identity")}
    if candidate["realism"] <= incumbent["realism"]:
        return {"verdict": "REFUSE", "promote": False,
                "why": "identity held but realism did not improve: no reason to change her"}
    return {"verdict": "PROMOTE", "promote": True, "owner_decision_required": True,
            "why": (f"identity retention {incumbent['identity_retention']:.0%} -> "
                    f"{candidate['identity_retention']:.0%} (held or better) and realism "
                    f"{incumbent['realism']:.0%} -> {candidate['realism']:.0%}"),
            "how": "an owner card; the change itself is model_registry.replace_canonical"}


def regression(after: dict, before: dict) -> dict:
    """Rollback trigger: a promoted version that lost identity retention or realism."""
    if after.get("identity_retention") is None or before.get("identity_retention") is None:
        return {"rollback": False, "verdict": "UNKNOWN", "why": "not enough judged frames"}
    lost = []
    if after["identity_retention"] < before["identity_retention"]:
        lost.append("identity_retention")
    if (after.get("realism") is not None and before.get("realism") is not None
            and after["realism"] < before["realism"]):
        lost.append("realism")
    return {"rollback": bool(lost), "verdict": "REGRESSED" if lost else "HELD", "lost": lost,
            "how": "restore the retired predecessor (retired, never deleted) by owner decision"}
