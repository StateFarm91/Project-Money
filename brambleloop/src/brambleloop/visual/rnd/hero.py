"""Autonomous hero-image challengers per product class (owner D-FB-16 items 4-5).

The hero is listing frame one (`sequence.HERO`): the finished dream. This module keeps one
INCUMBENT hero treatment per class and keeps challenging it, so nobody has to ask for "better
pictures":

* **Free deterministic challengers run now.** Each is rendered by the deterministic disclosed
  renderer from the certified CIR, judged by every hard gate (`gates.judge_frame`) and then by
  the PROXY judges (`judges`); `objective.select` ranks only the gate-passing ones. A
  challenger whose objective beats the incumbent by the (trust-scaled) margin is promoted with
  `basis="proxy"` -- provisional by construction.
* **Paid challengers are queued, never executed** (`GATED_SPEND`, with an estimated cost and
  `loop.paid_execution_gate()` closed): lifestyle scene, styled flat-lay, Laura-on-model
  lifestyle, seasonal scene. A Laura treatment conditions on the canonical references only;
  the identity gate (laura-r2-a42aeac7, "similar is not Laura") is computed when judged and
  cannot be supplied by a caller.
* **The slow loop decides.** `calibrate` reads lane K3's `ListingOutcome` rows for the
  incumbent's style and for the hero it replaced; a significantly worse CTR, conversion or
  favourite rate OVERTURNS the proxy promotion (rollback + lesson + lower proxy trust). A
  marketplace-overturned treatment is not re-promoted on proxy evidence for
  `loop.OVERTURN_MEMORY_DAYS`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import commercial as C
from . import gates as G
from . import judges as J
from . import models as M
from . import objective as O
from . import pipeline as P

INCUMBENT, CANDIDATE, REJECTED, RETIRED = "incumbent", "candidate", "rejected", "retired"
OVERTURNED, GATED_SPEND, UNAVAILABLE = "overturned", "gated_spend", "unavailable"
HERO_STATES = (INCUMBENT, CANDIDATE, REJECTED, RETIRED, OVERTURNED, GATED_SPEND, UNAVAILABLE)

# Objective points a proxy challenger must beat the incumbent by (divided by proxy trust, so
# every marketplace overturn makes the internal judges' word count for less).
PROXY_MARGIN = 0.02
MIN_TRUST = 0.125
MIN_FAVOURITE_VISITS = 100

_DET, _PAID = P.DETERMINISTIC, P.PAID
_WEARABLE = ("fitted_garments", "loose_garments", "accessories", "laura_on_model")

TREATMENTS: dict[str, dict] = {
    "disclosed_finished_render": {
        "execution": _DET, "classes": P.DISCLOSED_CLASSES, "kind": "finished_product",
        "params": {}, "why": "the certified finished-product render (disclosed), incumbent "
                             "pipeline parameters"},
    "disclosed_finished_render_close": {
        "execution": _DET, "classes": ("coasters_tabletop",), "kind": "finished_product",
        "params": {"hero_gap_ratio": 0.06}, "why": "pieces gathered: larger in the thumbnail"},
    "disclosed_finished_render_airy": {
        "execution": _DET, "classes": ("coasters_tabletop",), "kind": "finished_product",
        "params": {"hero_gap_ratio": 0.24}, "why": "more air between pieces: calmer, premium"},
    "owned_photo_hero": {
        "execution": _DET, "classes": tuple(c for c in P.PRODUCT_CLASSES
                                            if c != "laura_on_model"),
        "kind": "finished_product", "params": {}, "requires": "owned photograph",
        "why": "a photograph of a made sample: free once the photograph exists"},
    "lifestyle_scene": {
        "execution": _PAID, "classes": tuple(c for c in P.PRODUCT_CLASSES
                                             if c != "laura_on_model"),
        "kind": "lifestyle_scene",
        "params": {"composition_preset": "in_use_lifestyle",
                   "lighting_preset": "north_window_soft"},
        "why": "the finished piece in a warm lived-in home scene (owner art direction)"},
    "styled_flatlay": {
        "execution": _PAID, "classes": ("coasters_tabletop", "blankets_home_textiles",
                                        "baskets_storage", "accessories", "seasonal"),
        "kind": "styled_flatlay",
        "params": {"composition_preset": "flatlay_overhead",
                   "lighting_preset": "overcast_daylight"},
        "why": "styled overhead flat-lay with yarn and props in the brand palette"},
    "laura_on_model_lifestyle": {
        "execution": _PAID, "classes": _WEARABLE, "kind": "on_model",
        "params": {"composition_preset": "in_use_lifestyle",
                   "laura_reproduction": "canonical_reference_pack"},
        "why": "Laura (canonical identity only) wearing/using the piece; identity gate hard"},
    "seasonal_scene": {
        "execution": _PAID, "classes": ("seasonal",), "kind": "seasonal_scene",
        "params": {"composition_preset": "in_use_lifestyle",
                   "lighting_preset": "warm_lamp_evening"},
        "why": "seasonal lifestyle scene"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def style_key(product_class: str, treatment: str, params: dict) -> str:
    d = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()
    return f"{product_class}:{treatment}:{d[:8]}"


def applicable(product_class: str) -> list[str]:
    return [k for k, t in TREATMENTS.items() if product_class in t["classes"]]


def _row(r) -> dict:
    return {"id": r.id, "product_class": r.product_class, "treatment": r.treatment,
            "style_key": r.style_key, "execution": r.execution, "params": dict(r.params or {}),
            "parent_id": r.parent_id, "state": r.state, "basis": r.basis,
            "gates": dict(r.gates or {}), "accepted": r.accepted,
            "objective": dict(r.objective or {}), "estimated_cost_cad": r.estimated_cost_cad,
            "why": r.why, "kind": TREATMENTS.get(r.treatment, {}).get("kind"),
            "created_at": _aware(r.created_at).isoformat() if r.created_at else None,
            "promoted_at": _aware(r.promoted_at).isoformat() if r.promoted_at else None,
            "decided_at": _aware(r.decided_at).isoformat() if r.decided_at else None}


def variants(db, product_class: str | None = None) -> list[dict]:
    from sqlalchemy import select

    if not M.table_exists(db, M.VisualHeroVariant):
        return []
    with M.session(db) as s:
        q = select(M.VisualHeroVariant).order_by(M.VisualHeroVariant.id)
        if product_class:
            q = q.where(M.VisualHeroVariant.product_class == product_class)
        return [_row(r) for r in s.scalars(q)]


def incumbent(db, product_class: str) -> dict | None:
    return next((v for v in reversed(variants(db, product_class)) if v["state"] == INCUMBENT),
                None)


def _add(db, **kw) -> dict:
    with M.session(db) as s:
        r = M.VisualHeroVariant(**kw)
        s.add(r)
        s.flush()
        return _row(r)


def _update(db, vid: int, **kw) -> None:
    with M.session(db) as s:
        r = s.get(M.VisualHeroVariant, vid)
        for k, v in kw.items():
            setattr(r, k, v)


def _lesson(db, product_class, kind, params, statement, ref):
    with M.session(db) as s:
        s.add(M.VisualLesson(product_class=product_class, kind=kind, params=params,
                             statement=statement[:4000], ref=ref[:160]))


def _lessons(db, product_class: str, kind: str, *, now=None, days=None) -> list[dict]:
    from . import loop as L

    now = now or _now()
    days = days if days is not None else L.OVERTURN_MEMORY_DAYS
    return [les for les in L.lessons(db, product_class, limit=500) if les["kind"] == kind
            and now - datetime.fromisoformat(les["at"]) <= timedelta(days=days)]


def trust(db, product_class: str, *, now=None) -> dict:
    """Trust in the PROXY judges for this class: halved by every marketplace overturn."""
    n = len(_lessons(db, product_class, "hero_overturned", now=now))
    f = max(MIN_TRUST, 0.5 ** n)
    return {"desirability": f, "brand_consistency": f, "overturns": n,
            "required_margin": round(PROXY_MARGIN / f, 4)}


def overturned_treatments(db, product_class: str, *, now=None) -> set[str]:
    return {(les["params"] or {}).get("treatment")
            for les in _lessons(db, product_class, "hero_overturned", now=now)}


def ensure_incumbent(db, product_class: str) -> dict | None:
    """The class's running hero treatment. Disclosed classes start on the certified
    finished-product render; other classes have no free producer, so no incumbent exists
    until a (gated) challenger is judged -- reported UNKNOWN, never invented."""
    M.ensure_tables(db)
    inc = incumbent(db, product_class)
    if inc is not None or product_class not in P.DISCLOSED_CLASSES:
        return inc
    t = TREATMENTS["disclosed_finished_render"]
    return _add(db, product_class=product_class, treatment="disclosed_finished_render",
                style_key=style_key(product_class, "disclosed_finished_render", t["params"]),
                execution=_DET, params=dict(t["params"]), state=INCUMBENT, basis="proxy",
                why="generation 1 hero: the certified finished-product render",
                promoted_at=_now())


_WORST = {"FAIL": 3, "UNKNOWN": 2, "PASS": 1, "N/A": 0}


def evaluate(db, product_class: str, treatment: str, params: dict, cirs) -> dict:
    """Render the hero of every product in the class with this treatment, judge each by every
    hard gate, then by the proxy judges. Gates are aggregated worst-case across products."""
    from . import loop as L

    base = dict(P.ensure_incumbent(db, product_class)["params"])
    run = {**base, **params}
    gates: dict[str, dict] = {}
    comps: dict[str, list] = {}
    heroes = []
    for cir in cirs:
        frame = G.produce(cir, run)[0]
        j = G.judge_frame(cir, frame, 1, product_class)
        for name, g in j["gates"].items():
            cur = gates.get(name)
            if cur is None or _WORST.get(g["status"], 2) > _WORST.get(cur["status"], 2):
                gates[name] = {"status": g["status"], "why": g.get("why", "")}
        for name, r in J.judge_all(frame["png"], medium="DIGITAL_TWIN_RENDER").items():
            comps.setdefault(name, []).append(r)
        heroes.append({"subject": f"{cir.slug}@{cir.version}", "sha256": frame["sha256"],
                       "accepted": j["accepted"], "failures": j["failures"]})
    components = {}
    for name, rs in comps.items():
        vals = [r["value"] for r in rs]
        components[name] = ({"value": round(sum(vals) / len(vals), 4), "basis": "PROXY",
                             "label": J.PROXY_LABEL}
                            if vals and all(v is not None for v in vals) else
                            {"value": None, "basis": "unknown", "why": rs[0]["why"]})
    rows = C.outcome_rows(db, style_key=style_key(product_class, treatment, params))
    components["commercial"] = C.commercial_component(rows)
    accepted = bool(cirs) and all(h["accepted"] for h in heroes)
    ev = O.evaluate({"gates": gates, "components": components})
    return {"gates": gates, "accepted": accepted and ev["eligible"], "components": components,
            "objective": {**ev, "components": components,
                          "catalogue_fp": L.catalogue_fp(cirs) if cirs else "",
                          "heroes": heroes}}


def challenge(db, product_class: str, *, cirs=None, now=None,
              owned_photos: dict | None = None) -> dict:
    """One autonomous hero R&D round for a class. Free work runs; paid work is queued."""
    from . import loop as L

    M.ensure_tables(db)
    now = now or _now()
    if cirs is None:
        cirs = L.catalogue().get(product_class, [])
    fp = L.catalogue_fp(cirs) if cirs else ""
    out = {"product_class": product_class, "evaluated": [], "queued": [], "unavailable": [],
           "refused": [], "promotion": None}
    inc = ensure_incumbent(db, product_class)
    banned = overturned_treatments(db, product_class, now=now)
    existing = {v["style_key"]: v for v in variants(db, product_class)}
    if inc is not None and cirs and inc["objective"].get("catalogue_fp") != fp:
        ev = evaluate(db, product_class, inc["treatment"], inc["params"], cirs)
        _update(db, inc["id"], gates=ev["gates"], accepted=ev["accepted"],
                objective=ev["objective"])
        inc = incumbent(db, product_class)
    for name in applicable(product_class):
        t = TREATMENTS[name]
        key = style_key(product_class, name, t["params"])
        if inc is not None and key == inc["style_key"]:
            continue
        if t.get("requires"):
            if not (owned_photos or {}).get(product_class) and key not in existing:
                _add(db, product_class=product_class, treatment=name, style_key=key,
                     execution=t["execution"], params=dict(t["params"]), state=UNAVAILABLE,
                     why=f"needs an {t['requires']} for this class; none exists yet")
            out["unavailable"].append(name)
            continue
        if t["params"]:
            refusals = P.check_change(product_class, t["params"])
            if refusals:
                out["refused"].append({"treatment": name,
                                       "refusals": [r.to_dict() for r in refusals]})
                continue
        if t["execution"] == _PAID:
            if key not in existing:
                est, basis = L._estimate_cost(t["params"])
                _add(db, product_class=product_class, treatment=name, style_key=key,
                     execution=_PAID, params=dict(t["params"]), state=GATED_SPEND,
                     estimated_cost_cad=est,
                     why=f"paid hero challenger queued ({basis}); "
                         f"{L.paid_execution_gate()['why']}")
            out["queued"].append(name)
            continue
        if name in banned:
            out["refused"].append({"treatment": name, "refusals": [
                {"reason": "overturned by marketplace evidence; proxy judges not trusted on "
                           "it for this class"}]})
            continue
        if not cirs:
            continue
        prev = existing.get(key)
        if prev is not None and prev["objective"].get("catalogue_fp") == fp:
            out["evaluated"].append({"treatment": name, "reused": True,
                                     "value": prev["objective"].get("value"),
                                     "accepted": prev["accepted"]})
            continue
        ev = evaluate(db, product_class, name, t["params"], cirs)
        if prev is None:
            _add(db, product_class=product_class, treatment=name, style_key=key,
                 execution=_DET, params=dict(t["params"]), parent_id=(inc or {}).get("id"),
                 state=CANDIDATE, gates=ev["gates"], accepted=ev["accepted"],
                 objective=ev["objective"], why=t["why"])
        else:
            _update(db, prev["id"], gates=ev["gates"], accepted=ev["accepted"],
                    objective=ev["objective"],
                    state=CANDIDATE if prev["state"] in (REJECTED, CANDIDATE)
                    else prev["state"])
        out["evaluated"].append({"treatment": name, "value": ev["objective"].get("value"),
                                 "accepted": ev["accepted"],
                                 "failures": ev["objective"].get("failures")})
    out["promotion"] = _select(db, product_class, now=now)
    return out


def _select(db, product_class: str, *, now) -> dict | None:
    inc = incumbent(db, product_class)
    cands = [v for v in variants(db, product_class) if v["state"] == CANDIDATE]
    if not cands:
        return None
    tr = trust(db, product_class, now=now)
    pool = ([inc] if inc is not None else []) + cands
    sel = O.select([{"id": v["id"], "gates": v["gates"],
                     "components": v["objective"].get("components") or {}} for v in pool],
                   trust=tr)
    inc_val = None
    if inc is not None:
        inc_val = next((r["value"] for r in sel["ranking"] if r["id"] == inc["id"]), None)
    win = sel["winner"]
    decision = {"winner": win, "ranking": sel["ranking"], "ineligible": sel["ineligible"],
                "incumbent_value": inc_val, "required_margin": tr["required_margin"],
                "promoted": False}
    if win is not None and (inc is None or win != inc["id"]) and \
            (inc_val is None or sel["value"] - inc_val > tr["required_margin"]):
        w = next(v for v in cands if v["id"] == win)
        with M.session(db) as s:
            for v in pool:
                r = s.get(M.VisualHeroVariant, v["id"])
                if v["id"] == win:
                    r.state, r.basis, r.promoted_at, r.decided_at = INCUMBENT, "proxy", now, now
                    r.parent_id = inc["id"] if inc else None
                elif inc is not None and v["id"] == inc["id"]:
                    r.state, r.decided_at = RETIRED, now
                else:
                    r.state, r.decided_at = REJECTED, now
        _lesson(db, product_class, "hero_promoted",
                {"treatment": w["treatment"], "style_key": w["style_key"], "basis": "proxy"},
                f"hero {w['treatment']} promoted on PROXY judges ({sel['value']} vs "
                f"{inc_val}, margin {tr['required_margin']}); provisional until marketplace "
                f"evidence confirms it", f"hero:{win}")
        decision["promoted"] = True
        decision["basis"] = "proxy"
    else:
        with M.session(db) as s:
            for v in cands:
                r = s.get(M.VisualHeroVariant, v["id"])
                r.state, r.decided_at = REJECTED, now
                failures = O.gate_failures(v["gates"])
                r.why = (r.why + " | rejected: " + (", ".join(failures) if failures else
                         f"objective did not beat the incumbent by {tr['required_margin']}"))[
                             :4000]
    return decision


# ---------------------------------------------------------------------------- slow loop

def calibrate(db, product_class: str, *, now=None) -> dict:
    """Marketplace evidence (ListingOutcome) confirms or OVERTURNS a proxy hero promotion."""
    from . import loop as L

    now = now or _now()
    inc = incumbent(db, product_class)
    if inc is None or inc["parent_id"] is None:
        return {"product_class": product_class, "verdict": "no_comparison",
                "why": "no promoted hero with a predecessor to compare against"}
    parent = next((v for v in variants(db, product_class) if v["id"] == inc["parent_id"]),
                  None)
    a = C.funnel(C.outcome_rows(db, style_key=parent["style_key"]))
    b = C.funnel(C.outcome_rows(db, style_key=inc["style_key"]))
    checks, worse, better = [], [], []

    def n(f, k):
        return f[k]["value"]

    def test(metric, num, den, floor, worse_if_lower=True):
        if (n(a, den) or 0) < floor or (n(b, den) or 0) < floor or \
                n(a, num) is None or n(b, num) is None:
            return
        z = L._z(n(b, num), n(b, den), n(a, num), n(a, den))
        checks.append({"metric": metric, "replaced": round(n(a, num) / n(a, den), 4),
                       "incumbent": round(n(b, num) / n(b, den), 4),
                       "z": None if z is None else round(z, 3)})
        if z is None:
            return
        bad = z <= -L.MARKET_Z if worse_if_lower else z >= L.MARKET_Z
        good = z >= L.MARKET_Z if worse_if_lower else z <= -L.MARKET_Z
        if bad:
            worse.append(f"{metric} {checks[-1]['incumbent']} vs {checks[-1]['replaced']} "
                         f"(z={z:.2f})")
        elif good:
            better.append(metric)

    test("ctr", "visits", "impressions", L.MARKET_MIN_IMPRESSIONS)
    test("favourite_rate", "favourites", "visits", MIN_FAVOURITE_VISITS)
    test("conversion", "purchases", "visits", L.MARKET_MIN_CLICKS)
    test("refund_rate", "refunds", "purchases", L.MARKET_MIN_PURCHASES, worse_if_lower=False)
    if not checks:
        return {"product_class": product_class, "verdict": "insufficient_evidence",
                "replaced": a, "incumbent": b,
                "why": f"needs >= {L.MARKET_MIN_IMPRESSIONS} impressions credited to both "
                       f"heroes (UNKNOWN until then; never 0)"}
    if not worse:
        verdict = "confirmed" if better else "inconclusive"
        if better:
            _update(db, inc["id"], basis="market", decided_at=now)
            _lesson(db, product_class, "hero_confirmed",
                    {"treatment": inc["treatment"], "checks": checks},
                    f"hero {inc['treatment']} confirmed by the marketplace: {better}",
                    f"hero:{inc['id']}")
        return {"product_class": product_class, "verdict": verdict, "checks": checks}
    why = ("marketplace evidence overturned the proxy hero promotion: " + "; ".join(worse)
           + ". Basis: sequential before/after per hero style, not a randomised test")
    with M.session(db) as s:
        cur = s.get(M.VisualHeroVariant, inc["id"])
        cur.state, cur.basis, cur.decided_at = OVERTURNED, "market", now
        cur.why = (cur.why + " | " + why)[:4000]
        prev = s.get(M.VisualHeroVariant, parent["id"])
        prev.state, prev.basis, prev.decided_at = INCUMBENT, "market", now
    _lesson(db, product_class, "hero_overturned",
            {"treatment": inc["treatment"], "style_key": inc["style_key"], "checks": checks},
            f"hero {inc['treatment']} overturned and rolled back to {parent['treatment']}: "
            f"{'; '.join(worse)}. Proxy judges' trust for {product_class} halved; the "
            f"treatment is not re-promoted on proxy evidence for {L.OVERTURN_MEMORY_DAYS} days",
            f"hero:{inc['id']}")
    return {"product_class": product_class, "verdict": "overturned", "checks": checks,
            "restored": parent["treatment"], "why": why}


# ---------------------------------------------------------------------------- status

def status(db, product_class: str) -> dict:
    vs = variants(db, product_class)
    inc = next((v for v in reversed(vs) if v["state"] == INCUMBENT), None)
    tr = trust(db, product_class)
    rows = C.outcome_rows(db, style_key=inc["style_key"]) if inc else []
    return {
        "incumbent": (None if inc is None else
                      {"id": inc["id"], "treatment": inc["treatment"],
                       "style_key": inc["style_key"], "kind": inc["kind"],
                       "basis": inc["basis"], "accepted": inc["accepted"],
                       "objective_value": inc["objective"].get("value"),
                       "since": inc["promoted_at"]}),
        "incumbent_reading": ("UNKNOWN: no free hero producer for this class; hero "
                              "challengers queued" if inc is None else
                              ("PROXY (provisional until marketplace evidence)"
                               if inc["basis"] == "proxy" else "MARKET-CONFIRMED")),
        "variants_by_state": {s: sum(1 for v in vs if v["state"] == s) for s in HERO_STATES
                              if any(v["state"] == s for v in vs)},
        "gated_spend": [{"treatment": v["treatment"], "estimated_cost_cad":
                         v["estimated_cost_cad"], "why": v["why"][:200]}
                        for v in vs if v["state"] == GATED_SPEND],
        "proxy_trust": tr,
        "incumbent_funnel": C.funnel(rows),
    }
