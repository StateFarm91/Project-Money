"""Free lead magnets (F-810) -- W4-C11.

"Agents may build original high-value downloadable guides/checklists/calculators to earn email
subscribers. Every lead magnet has a measurable acquisition goal, provenance, version and
downstream attribution."

`register(db, magnet)` refuses a magnet that lacks any of the four, and records it as a Learn
graph node (kind `lead_magnet`, key `lead_magnet:<slug>@<version>`; editor-only like the
rest of the graph). A new version is a new record; an old one is never rewritten.

* goal -- `{"signups": int > 0, "by": ISO date}`;
* provenance -- `{"rights": "brambleloop_original" | "licensed", "sha256", "sources"}`, a
  licensed one needing its `license_ref` (the same rule as lesson assets);
* version -- a non-empty string;
* attribution -- `attribute(db, slug, version, signups=...)` over recorded signups (each
  `{subscriber, purchases: [cad, ...]}`): progress against the goal, the share who bought, and
  the revenue they brought. With no signup record it is UNMEASURED, not 0. Recording signups
  needs CASL-compliant consent, which is the email system's job, not this one's: a signup
  without `consent=True` is not counted.
"""
from __future__ import annotations

import re
from datetime import date

KINDS = ("guide", "checklist", "calculator")


class MagnetRefused(ValueError):
    pass


def _key(slug, version):
    return f"lead_magnet:{slug}@{version}"


def register(db, magnet: dict) -> str:
    from .models import LearnNode

    errs = []
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(magnet.get("slug") or "")):
        errs.append("slug")
    if magnet.get("kind") not in KINDS:
        errs.append(f"kind must be one of {KINDS}")
    if not str(magnet.get("version") or "").strip():
        errs.append("version")
    goal = magnet.get("goal") or {}
    if type(goal.get("signups")) is not int or goal["signups"] <= 0:
        errs.append("goal.signups must be a positive whole number")
    try:
        date.fromisoformat(str(goal.get("by")))
    except ValueError:
        errs.append("goal.by must be an ISO date")
    prov = magnet.get("provenance") or {}
    if prov.get("rights") not in ("brambleloop_original", "licensed"):
        errs.append("provenance.rights")
    if prov.get("rights") == "licensed" and not prov.get("license_ref"):
        errs.append("a licensed magnet needs provenance.license_ref")
    if not re.fullmatch(r"[a-f0-9]{64}", str(prov.get("sha256") or "")):
        errs.append("provenance.sha256")
    if not isinstance(prov.get("sources"), list):
        errs.append("provenance.sources must list what it was built from")
    if errs:
        raise MagnetRefused("; ".join(errs))
    key = _key(magnet["slug"], magnet["version"])
    with db.session() as s:
        if s.get(LearnNode, key) is not None:
            raise MagnetRefused(f"{key} exists; a change is a new version")
        s.add(LearnNode(key=key, kind="lead_magnet", detail=dict(magnet)))
    return key


def attribute(db, slug: str, version: str, *, signups=None, today: date | None = None) -> dict:
    from .models import LearnNode

    with db.session() as s:
        node = s.get(LearnNode, _key(slug, version))
        if node is None:
            raise MagnetRefused(f"no lead magnet {slug}@{version}")
        magnet = dict(node.detail)
    goal = magnet["goal"]
    by = date.fromisoformat(goal["by"])
    if signups is None:
        return {"slug": slug, "version": version, "state": "UNMEASURED", "signups": None,
                "why": "no signup record; not 0"}
    counted = [x for x in signups if x.get("consent") is True]
    n = len({x["subscriber"] for x in counted})
    buyers = [x for x in counted if x.get("purchases")]
    revenue = round(sum(float(p) for x in buyers for p in x["purchases"]), 2)
    today = today or date.today()
    state = ("MET" if n >= goal["signups"] else
             "MISSED" if today > by else "IN_PROGRESS")
    return {"slug": slug, "version": version, "state": state, "signups": n,
            "goal": goal["signups"], "progress": round(n / goal["signups"], 3),
            "excluded_without_consent": len(signups) - len(counted),
            "buyer_share": round(len(buyers) / n, 3) if n else None,
            "attributed_revenue_cad": revenue}
