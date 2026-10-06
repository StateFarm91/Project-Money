"""The Visual R&D objective: the INTERSECTION, not a trade-off (owner D-FB-16 item 5).

    Product Truth  AND  Laura identity (laura-r2-a42aeac7; similar is not Laura)  AND
    photographic realism/anatomy  AND  every other hard gate
        -> only then ranked by:
    photographic quality + brand consistency + customer desirability + commercial performance

Two layers, never mixed:

1. **Hard gates** (`HARD_GATES` = every non-advisory gate of `pipeline.GATES`). Every one must
   be PASS or N/A; UNKNOWN blocks like FAIL. A candidate that fails one is *ineligible*: it gets
   no objective value at all, so no desirability, brand or sales number can buy it back. The
   gates named in `NON_TRADEABLE` (truth, structure, identity, anatomy, realism) are also
   refused as weight names -- they are not components of a score.
2. **Optimisation targets** among eligible candidates: a weighted mean of the components that
   were actually read. An UNKNOWN component is left out of the mean (never scored 0) and the
   result names what it rests on. Internal judge components are PROXY and scaled by their
   trust (lowered by marketplace overturns); a *measured* commercial component, once the slow
   loop has one, carries `MEASURED_COMMERCIAL_SHARE` of the decision on its own.
"""
from __future__ import annotations

from . import pipeline as P

# D-FB-17: roles the owner's canonical files hold. A candidate that declares one of these
# (`brand_role`) is a PROPOSAL: it may be ranked, never adopted, unless an owner decision
# names its bytes (`brand.canonical_assets.require_brand_change_authorised`).
CANONICAL_BRAND_ROLES: tuple[str, ...] = ("hero_logo", "storefront_banner")

OBJECTIVE_VERSION = "visual-objective/1"
HARD_GATES: tuple[str, ...] = tuple(g for g in P.GATES if g not in P.ADVISORY_GATES)
NON_TRADEABLE: tuple[str, ...] = ("product_truth", "structure", "laura_identity", "anatomy",
                                  "photorealism")
PASSING = ("PASS", "N/A")

WEIGHTS: dict[str, float] = {
    "desirability": 0.40,
    "brand_consistency": 0.30,
    "photographic_quality": 0.30,
    "commercial": 0.0,           # proxy commercial readings carry no weight; measured do
}
PROXY_COMPONENTS = ("desirability", "brand_consistency")
MEASURED_COMMERCIAL_SHARE = 0.7


class ObjectiveRefused(ValueError):
    """A weight that names a gate, the identity or a judge threshold."""


def weights(overrides: dict | None = None) -> dict[str, float]:
    """The component weights, optionally overridden -- never on a gate or protected name."""
    w = dict(WEIGHTS)
    for k, v in (overrides or {}).items():
        from ...improve import invariants

        key = invariants.canonical_key(k)
        if k in P.GATES or k in NON_TRADEABLE or any(x in key for x in P.VISUAL_PROTECTED) \
                or invariants.protected_invariant(k) is not None:
            raise ObjectiveRefused(f"{k!r} is a hard gate or protected name: gates are not "
                                   f"weights and cannot be traded for desirability")
        if k not in WEIGHTS:
            raise ObjectiveRefused(f"{k!r} is not an objective component: {sorted(WEIGHTS)}")
        if not isinstance(v, (int, float)) or v < 0:
            raise ObjectiveRefused(f"weight for {k} must be a non-negative number")
        w[k] = float(v)
    return w


def gate_failures(gates: dict | None) -> list[str]:
    out = []
    for name in HARD_GATES:
        st = ((gates or {}).get(name) or {}).get("status", "UNKNOWN")
        if st not in PASSING:
            out.append(f"{name.upper()}:{st}")
    return out


def evaluate(candidate: dict, *, trust: dict | None = None,
             weight_overrides: dict | None = None) -> dict:
    """`candidate`: {"gates": {...}, "components": {name: {"value", "basis"}}}.

    Returns eligible, failures, value (None when ineligible or nothing was read), components
    used and the basis ("market" when a measured commercial reading took part, else "proxy")."""
    failures = gate_failures(candidate.get("gates"))
    w = weights(weight_overrides)
    trust = trust or {}
    comps = candidate.get("components") or {}
    if failures:
        return {"eligible": False, "failures": failures, "value": None, "basis": "ineligible",
                "used": {}, "why": "a hard gate did not pass: no score can trade for it",
                "version": OBJECTIVE_VERSION}
    used, unknown = {}, []
    for name, wt in w.items():
        r = comps.get(name) or {}
        v = r.get("value")
        if v is None:
            unknown.append(name)
            continue
        if name == "commercial":
            continue
        t = float(trust.get(name, 1.0)) if name in PROXY_COMPONENTS else 1.0
        used[name] = {"value": float(v), "weight": wt * t, "basis": r.get("basis", "PROXY")}
    tot = sum(u["weight"] for u in used.values())
    internal = (sum(u["value"] * u["weight"] for u in used.values()) / tot) if tot else None
    com = comps.get("commercial") or {}
    measured = com.get("value") is not None and str(com.get("basis", "")).startswith("measured")
    if measured:
        value = (MEASURED_COMMERCIAL_SHARE * float(com["value"])
                 + (1 - MEASURED_COMMERCIAL_SHARE) * (internal if internal is not None
                                                      else float(com["value"])))
        used["commercial"] = {"value": float(com["value"]), "weight": MEASURED_COMMERCIAL_SHARE,
                              "basis": com.get("basis")}
        basis = "market"
    else:
        value, basis = internal, ("proxy" if internal is not None else "unknown")
    return {"eligible": True, "failures": [], "value": None if value is None else
            round(value, 4), "basis": basis, "used": used, "unknown": unknown,
            "version": OBJECTIVE_VERSION,
            "why": ("ranked on " + ", ".join(sorted(used)) if used else
                    "eligible but no component was read")}


def _brand_guard(c: dict) -> str | None:
    """None when the candidate may be adopted; else why it is only an owner-review proposal."""
    role = c.get("brand_role")
    if not role:
        return None
    from ...brand import canonical_assets as CA

    if role not in CA.ROLES:
        return f"unknown brand role {role!r}"
    try:
        CA.require_brand_change_authorised(role, str(c.get("sha256") or ""),
                                           c.get("approval"),
                                           action=f"visual challenger {c.get('id')!r}")
    except CA.BrandChangeRefused as exc:
        return str(exc)
    return None


def select(candidates: list[dict], *, trust: dict | None = None) -> dict:
    """The best ELIGIBLE candidate (highest value; ties keep input order) or None. Each
    candidate dict needs an `id`. Ineligible ones are listed with their failures.

    A candidate for a canonical brand role (D-FB-17: `brand_role` in CANONICAL_BRAND_ROLES)
    that is not the owner's file and carries no owner decision naming its bytes is ranked but
    never the winner: it is listed under `owner_review` (OWNER_REVIEW_REQUIRED), however high
    it scores."""
    scored, ineligible, review = [], [], []
    for i, c in enumerate(candidates):
        ev = evaluate(c, trust=trust)
        if not ev["eligible"]:
            ineligible.append({"id": c.get("id"), "failures": ev["failures"]})
            continue
        refusal = _brand_guard(c)
        if refusal is not None:
            review.append({"id": c.get("id"), "brand_role": c.get("brand_role"),
                           "value": ev["value"], "status": "OWNER_REVIEW_REQUIRED",
                           "why": refusal})
            continue
        if ev["value"] is not None:
            scored.append((-ev["value"], i, c, ev))
    scored.sort(key=lambda t: t[:2])
    best = scored[0] if scored else None
    return {"winner": None if best is None else best[2].get("id"),
            "value": None if best is None else best[3]["value"],
            "basis": None if best is None else best[3]["basis"],
            "ranking": [{"id": c.get("id"), "value": ev["value"], "basis": ev["basis"]}
                        for _, _, c, ev in scored],
            "ineligible": ineligible, "owner_review": review}


def brand_target(role: str) -> dict:
    """The canonical art target a reproduction or challenger for `role` is measured against
    (D-FB-17): the owner's file, verified by its bytes."""
    from ...brand import canonical_assets as CA

    rec = CA.current(role)
    v = CA.verify()
    return {**rec, "verified": v["ok"], "problems": v["problems"],
            "adoption": "owner decision only (canonical_assets.AUTHORISED_BRAND_CHANGES)"}


def describe() -> dict:
    return {"version": OBJECTIVE_VERSION, "hard_gates": list(HARD_GATES),
            "non_tradeable": list(NON_TRADEABLE), "weights": dict(WEIGHTS),
            "proxy_components": list(PROXY_COMPONENTS),
            "measured_commercial_share": MEASURED_COMMERCIAL_SHARE,
            "canonical_brand_roles": list(CANONICAL_BRAND_ROLES),
            "rule": "intersection: every hard gate first (UNKNOWN blocks); desirability, "
                    "brand and commercial only rank candidates that already passed"}
