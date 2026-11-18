"""WS4-4: the pure in/out decision for the standing publication policy (design §4.1, §3.3).

`classify(policy_content, facts, *, action)` decides whether one exact release is inside an
effective standing policy. It has NO I/O: the facts are read elsewhere (the issuer's guarded
readers, a later increment), each as ``{"state": PASS|FAIL|UNKNOWN, "value": ..., "why": ...}``.

Rules, all fail-closed:

* any reason at all means OUT; the result carries every reason (for the hold card);
* every required fact must be present and read PASS. A missing fact, an unknown state, or a
  reader that raised (UNKNOWN) is a reason. UNKNOWN never passes;
* the policy is an allow-list. A category the policy does not list, a category listed by more
  than one class, an excluded category or slug, a Launch-0 or held slug, and an action the
  policy does not name are all out;
* the risk class is computed HERE as max(declared, derived), never taken from one field, so a
  CIR that declares a low class cannot lower it;
* the physical evidence must satisfy both the risk class's own requirement
  (`risk_matrix.REQUIRED_PHYSICAL`) and the class's stricter `physical_required`;
* the price is compared exactly to the cent, inclusive at both ends;
* frequency counts consumed AND outstanding grants, so unconsumed grants cannot be stockpiled;
* content failing the code ceilings (`standing_policy.ceiling_refusals`) is out.

Nothing here can widen authority: it only answers in/out, and only an issuer (later
increments) acts on IN, after its own re-checks.
"""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

# Facts every classification needs (§3.3 checks 1-16). Each must read PASS; the value-carrying
# ones are then compared with the policy below.
GATE_FACTS = (
    "kill_switch",                # 1: kill_switch_refusal() is clear
    "policy_enabled",             # 1: BRAMBLELOOP_STANDING_POLICY_ENABLED=1
    "mode_t",                     # 1: deployment is Mode T
    "phase_may_publish",          # 2
    "stop_conditions_clear",      # 4
    "stop_watch_fresh",           # 4
    "not_experiment",             # 5
    "taxonomy_agrees",            # 6: CIR category agrees with the listing taxonomy id
    "publication_evidence",       # 7: every gated section passes
    "release_gates",              # 8: for_publish does not block the release
    "deterministic_reverify",     # 9: recompiled content and release hash match
    "owner_attested_physical",    # 10: every bound physical test is owner-attested
    "independent_vision_review",  # 11
    "no_fake_discount",           # 12
    "not_on_etsy",                # 16
    "no_publish_incomplete",      # 16
)
VALUE_FACTS = (
    "slug",                 # str
    "category",             # str: the CIR's eligibility family
    "risk_declared",        # "A" | "B" | "C"
    "risk_derived",         # "A" | "B" | "C"
    "physical_held",        # list of evidence-class keys bound to this exact release
    "price_cad",            # number: Listing.price_cad
    "sizes",                # int: number of sizes the release offers
    "colourwork",           # bool
    "wearable",             # bool
    "grants_today",         # {"consumed": int, "outstanding": int} (UTC day)
    "grants_7d",            # {"consumed": int, "outstanding": int}
    "outstanding",          # int: unconsumed, unexpired grants of this policy
    "minutes_since_last",   # number or None (no earlier grant)
    "ads_jobs_queued",      # int: ads jobs under this policy's lineage
    "shop_id",              # str: bound shop id (binding AND worker-reported, already equal)
    "shop_name",            # str
)
REQUIRED_FACTS = GATE_FACTS + VALUE_FACTS
RISK_RANK = {"A": 0, "B": 1, "C": 2}


def _fact(facts: dict, name: str, reasons: list[str]):
    """The fact's value when it reads PASS; otherwise records the reason and returns None."""
    f = facts.get(name) if isinstance(facts, dict) else None
    if not isinstance(f, dict):
        reasons.append(f"{name}: not read (UNKNOWN)")
        return None
    state = f.get("state")
    if state != PASS:
        why = f.get("why") or ""
        reasons.append(f"{name}: {state if state in (FAIL, UNKNOWN) else 'UNKNOWN'}"
                       + (f" ({why})" if why else ""))
        return None
    return f.get("value")


def _cents(value) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite():
        return None
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if d == d.quantize(
        Decimal("0.01")) else None   # a price finer than a cent is not a listed price


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 \
        else None


def classify(policy_content: dict, facts: dict, *, action: str = "store.publish",
             now: datetime | None = None) -> dict:
    """{"in_policy": bool, "reasons": [str], "class_id": str | None, "effective_risk": str
    | None}. `in_policy` is True only when there are no reasons at all."""
    from ..gates import risk_matrix
    from ..products import launch0
    from . import standing_policy as sp

    reasons: list[str] = []
    content = policy_content if isinstance(policy_content, dict) else {}
    ceiling = sp.ceiling_refusals(content)
    if ceiling:
        return {"in_policy": False, "class_id": None, "effective_risk": None,
                "reasons": ["policy fails the code ceilings: " + "; ".join(ceiling)]}
    if action not in content["actions"]:
        reasons.append(f"action {action!r} is not in the policy")

    for name in GATE_FACTS:
        _fact(facts, name, reasons)
    v = {name: _fact(facts, name, reasons) for name in VALUE_FACTS}

    # ---- scope exclusions (§1.4, §3.3 check 5)
    slug = v["slug"]
    if slug is not None:
        if not isinstance(slug, str) or not slug:
            reasons.append("slug: unreadable")
        else:
            if slug in launch0.LAUNCH0_SLUGS or slug in launch0.HELD_FOR_VERIFICATION:
                reasons.append(f"{slug} is a Launch-0 or held product: always out of policy")
            if slug in content["exclusions"]["slugs"]:
                reasons.append(f"{slug} is excluded by the policy")

    # ---- classification (§3.3 check 6): exactly one class lists the category
    cls = None
    category = v["category"]
    if category is not None:
        if not isinstance(category, str) or not category:
            reasons.append("category: unreadable")
        elif category in content["exclusions"]["categories"]:
            reasons.append(f"category {category} is excluded by the policy")
        else:
            matches = [pc for pc in content["product_classes"] if category in pc["categories"]]
            if len(matches) != 1:
                reasons.append(f"category {category} matches {len(matches)} policy classes "
                               f"(exactly one is required)")
            else:
                cls = matches[0]

    # ---- risk class: max(declared, derived), computed here (§3.3 check 6, M12)
    effective = None
    rd, rv = v["risk_declared"], v["risk_derived"]
    if rd is not None and rv is not None:
        if rd not in RISK_RANK or rv not in RISK_RANK:
            reasons.append(f"risk class unreadable (declared {rd!r}, derived {rv!r})")
        else:
            effective = max(rd, rv, key=RISK_RANK.__getitem__)
            if cls is not None and RISK_RANK[effective] > RISK_RANK[
                    cls["max_effective_risk_class"]]:
                reasons.append(f"effective risk class {effective} exceeds the class's "
                               f"{cls['max_effective_risk_class']}")
            if RISK_RANK[effective] > RISK_RANK[sp.MAX_RISK_CLASS]:
                reasons.append(f"effective risk class {effective} exceeds the code ceiling "
                               f"{sp.MAX_RISK_CLASS}")

    # ---- physical evidence (§3.3 check 10, M23): both requirements
    held = v["physical_held"]
    if held is not None and effective is not None and cls is not None:
        if not isinstance(held, (list, tuple)) or not all(isinstance(h, str) for h in held):
            reasons.append("physical evidence: unreadable")
        else:
            needed = [r for r in (risk_matrix.REQUIRED_PHYSICAL.get(effective),
                                  cls["physical_required"]) if r and r != "none"]
            for req in needed:
                try:
                    ok = any(risk_matrix.satisfies(h, req) for h in held)
                except ValueError:
                    ok = False
                if not ok:
                    reasons.append(f"physical evidence {req} is required and not held "
                                   f"(held: {sorted(held) or 'none'})")

    # ---- class constraints
    if cls is not None:
        price = _cents(v["price_cad"]) if v["price_cad"] is not None else None
        if v["price_cad"] is not None:
            lo, hi = (_cents(cls["price_band_cad"][0]), _cents(cls["price_band_cad"][1]))
            if price is None or lo is None or hi is None:
                reasons.append(f"price {v['price_cad']!r}: not an exact price in cents")
            elif not (lo <= price <= hi):
                reasons.append(f"price CA${price} is outside the class band CA${lo}-CA${hi}")
        sizes = v["sizes"]
        if sizes is not None and (_count(sizes) is None or sizes < 1
                                  or sizes > cls["max_sizes"]):
            reasons.append(f"{sizes!r} sizes; the class allows at most {cls['max_sizes']}")
        for flag, allowed in (("colourwork", "colourwork_allowed"),
                              ("wearable", "wearable_allowed")):
            val = v[flag]
            if val is not None and not isinstance(val, bool):
                reasons.append(f"{flag}: unreadable")
            elif val is True and not cls[allowed]:
                reasons.append(f"{flag} is not allowed in class {cls['class_id']}")

    # ---- frequency (§3.3 check 13, M20): consumed AND outstanding both count
    fr = content["frequency"]
    for name, cap in (("grants_today", fr["max_per_day"]), ("grants_7d", fr["max_per_7d"])):
        g = v[name]
        if g is None:
            continue
        used = (_count(g.get("consumed")), _count(g.get("outstanding"))) \
            if isinstance(g, dict) else (None, None)
        if None in used:
            reasons.append(f"{name}: unreadable")
        elif sum(used) >= cap:
            reasons.append(f"{name}: {sum(used)} issued (consumed {used[0]}, outstanding "
                           f"{used[1]}); the policy allows {cap}")
    out = v["outstanding"]
    if out is not None:
        if _count(out) is None:
            reasons.append("outstanding: unreadable")
        elif out >= fr["max_outstanding_unconsumed_grants"]:
            reasons.append(f"{out} unconsumed grant(s) outstanding; the policy allows "
                           f"{fr['max_outstanding_unconsumed_grants']}")
    m = v["minutes_since_last"]   # None (read PASS) means there is no earlier grant
    if m is not None:
        if isinstance(m, bool) or not isinstance(m, (int, float)) or m != m or m < 0:
            reasons.append("minutes_since_last: unreadable")
        elif m < fr["min_spacing_minutes"]:
            reasons.append(f"only {m:g} minutes since the last grant; the policy needs "
                           f"{fr['min_spacing_minutes']}")

    # ---- spend (§3.3 check 14)
    ads = v["ads_jobs_queued"]
    if ads is not None and (_count(ads) is None or ads != 0):
        reasons.append(f"{ads!r} ads job(s) queued under this policy; ads must be NONE")

    # ---- Etsy account (§3.3 check 15)
    if v["shop_id"] is not None and v["shop_id"] != content["etsy"]["shop_id"]:
        reasons.append(f"bound shop {v['shop_id']!r} is not the policy's shop "
                       f"{content['etsy']['shop_id']!r}")
    if v["shop_name"] is not None and v["shop_name"] != content["etsy"]["shop_name"]:
        reasons.append(f"shop name {v['shop_name']!r} is not the policy's "
                       f"{content['etsy']['shop_name']!r}")

    return {"in_policy": not reasons, "reasons": reasons,
            "class_id": cls["class_id"] if cls is not None and not reasons else None,
            "effective_risk": effective}
