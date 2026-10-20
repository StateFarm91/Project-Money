"""Launch-0 product readiness packet: per product, per gate, what remains and who owns it.

The opening collection is the eight Launch-0 products (CAP-1, owner-approved 2026-10-11 as a
catalogue configuration only: the products themselves, drafts and publication are separate
owner decisions). For every product and every release (a three-size basket is one product,
three releases) this reads seven gates from the code that enforces them:

=====================  =======================================================================
gate                   read from
=====================  =======================================================================
certification          `ops.publication_authority` certification section (the stored release)
product_truth          `products.launch0.product_truth` (compiled now, deterministic)
image_truth            `ops.publication_authority` listing_set (certified disclosed frames)
listing_readiness      stored draft listing bound to the release + `app.dashboard_truth`
                       launch clearance (certified, usable asset, creative survivor, gauge)
price_plan             `publish.release_gates.launch_price_check` (listing vs Launch-0 plan)
seo                    `ops.publication_authority` search section (search certificate)
disclosure             `ops.publication_authority` disclosure section
=====================  =======================================================================

Rules: every state is read at generation time; a gate that could not be read is UNKNOWN and
UNKNOWN is never PASS; a gate that is not PASS names what remains and who owns it --
`company` (work this system does on its own), `owner` (a decision, credential or spend), or
`external` (a party outside the company). Nothing here writes, renders, enqueues or calls out.
"""
from __future__ import annotations

from datetime import datetime, timezone

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
COMPANY, OWNER, EXTERNAL = "company", "owner", "external"
GATES: tuple[str, ...] = ("certification", "product_truth", "image_truth", "listing_readiness",
                          "price_plan", "seo", "disclosure")
_ORDER = {PASS: 0, UNKNOWN: 1, FAIL: 2}


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN and says why
        return {"state": UNKNOWN, "why": f"unreadable: {type(exc).__name__}: {str(exc)[:200]}"}


def _row(state: str, why: str, *, remaining: str = "", owner: str | None = None,
         **extra) -> dict:
    state = state if state in (PASS, FAIL, UNKNOWN) else UNKNOWN
    return {"state": state, "why": str(why)[:400],
            "remaining": "" if state == PASS else remaining,
            "owner": None if state == PASS else (owner or COMPANY), **extra}


def _certification(ev: dict, stored: dict) -> dict:
    sec = ev.get("certification") or {}
    if not stored["stored"]:
        return _row(FAIL, "no release of this version is stored",
                    remaining="run the release chain (gate.certify) for this release",
                    owner=COMPANY)
    if sec.get("state") == PASS:
        return _row(PASS, sec.get("why", "certificate granted"))
    return _row(sec.get("state", UNKNOWN), sec.get("why", "certification unread"),
                remaining="re-run gate.certify; a withheld certificate names its reason",
                owner=COMPANY)


def _product_truth(truth: dict, cir_slug: str) -> dict:
    row = next((v for v in truth.get("variants") or [] if v.get("slug") == cir_slug), None)
    if not isinstance(truth.get("gates"), dict):
        return _row(UNKNOWN, truth.get("why", "product truth unreadable"),
                    remaining="read products.launch0.product_truth", owner=COMPANY)
    failed = sorted(k for k, ok in truth["gates"].items() if ok is not True)
    calibrated = (truth.get("aspiration") or {}).get("physically_calibrated")
    if not failed:
        return _row(PASS, "compiles clean; title, assembly, fabric and size-label promises "
                          "backed", physically_calibrated=calibrated,
                    compiles=(row or {}).get("compiles"))
    return _row(FAIL, f"failing: {failed}", remaining="re-engineer the CIR or its promises",
                owner=COMPANY, physically_calibrated=calibrated)


def _image_truth(ev: dict) -> dict:
    sec = ev.get("listing_set") or {}
    parity = ev.get("parity") or {}
    note = {"presentation_parity": parity.get("state", UNKNOWN),
            "presentation_parity_owner": (None if parity.get("state") == PASS else OWNER),
            "presentation_parity_why": str(parity.get("why", ""))[:200]}
    if sec.get("state") == PASS:
        return _row(PASS, sec.get("why", "listing set certified"), **note)
    return _row(sec.get("state", UNKNOWN), sec.get("why", "listing set unread"),
                remaining=("assets.build: render the disclosed frames, verify them on their "
                           "bytes and certify the listing set"), owner=COMPANY, **note)


def _listing_readiness(stored: dict, cleared: set[str], failing: dict, cir_slug: str) -> dict:
    listing = stored.get("listing")
    if listing is None:
        return _row(FAIL, "no drafted listing row for this release",
                    remaining="listing.draft in the release chain", owner=COMPANY)
    if not listing.get("bound_to_release"):
        return _row(FAIL, "the stored listing is not bound to this release",
                    remaining="re-draft the listing against the certified release",
                    owner=COMPANY)
    if cir_slug not in cleared:
        return _row(FAIL, f"not launch-cleared: failing {failing.get(cir_slug) or 'unknown'}",
                    remaining="clear the named launch criteria", owner=COMPANY,
                    listing_state=listing.get("state"))
    return _row(PASS, f"draft listing bound to the release; launch-cleared",
                listing_state=listing.get("state"), on_etsy=listing.get("on_etsy"))


def _price_plan(stored: dict, cir_slug: str) -> dict:
    from ..publish.release_gates import launch_price_check

    listing = stored.get("listing")
    chk = launch_price_check(cir_slug, None if listing is None else listing.get("price_cad"))
    st = chk["state"]
    if st == "MATCH":
        return _row(PASS, chk["why"], plan_cad=chk.get("plan_cad"))
    if st == "DRIFT":
        return _row(FAIL, chk["why"], remaining="re-run pricing.position for this release",
                    owner=COMPANY, plan_cad=chk.get("plan_cad"),
                    listing_cad=chk.get("listing_cad"))
    if st == "NO_LISTING":
        return _row(UNKNOWN, "no stored listing price to compare with the plan",
                    remaining="listing.draft then pricing.position", owner=COMPANY,
                    plan_cad=chk.get("plan_cad"))
    return _row(FAIL, chk["why"], remaining="the product has no Launch-0 price plan",
                owner=COMPANY)


def _seo(ev: dict) -> dict:
    sec = ev.get("search") or {}
    if sec.get("state") == PASS:
        return _row(PASS, sec.get("why", "search certificate current"))
    reasons = " ".join(str(r) for r in sec.get("reasons") or [])
    if "taxonomy" in reasons.lower() or "category UNKNOWN" in reasons:
        return _row(sec.get("state", UNKNOWN), sec.get("why", ""),
                    # W4-PRODREADY §8 / W4-FIRSTSALE: production reads Etsy's tree daily with
                    # the keystring already configured; the open work is the company's matcher.
                    remaining=("the category matcher: production reads Etsy's seller taxonomy "
                               "daily; the next refresh with W4-FIRSTSALE confirms crochet by "
                               "Etsy's own names or property values, then listing.seo re-runs"),
                    owner=COMPANY, reasons=list(sec.get("reasons") or [])[:4],
                    checks=dict(sec.get("checks") or {}),
                    category_status=sec.get("category_status"))
    return _row(sec.get("state", UNKNOWN), sec.get("why", "search certificate unread"),
                remaining="listing.seo for this release", owner=COMPANY,
                reasons=list(sec.get("reasons") or [])[:4],
                checks=dict(sec.get("checks") or {}),
                category_status=sec.get("category_status"))


def _disclosure(ev: dict) -> dict:
    sec = ev.get("disclosure") or {}
    if sec.get("state") == PASS:
        return _row(PASS, sec.get("why", "every owed disclosure present"))
    return _row(sec.get("state", UNKNOWN), sec.get("why", "disclosure unread"),
                remaining="re-draft the listing copy with every owed disclosure",
                owner=COMPANY, missing=list(sec.get("missing") or []))


def _worst(states) -> str:
    states = list(states)
    return max(states, key=lambda s: _ORDER.get(s, 1)) if states else UNKNOWN


def build(db, *, inventory: dict | None = None) -> dict:
    """The packet as a dict. Reads only."""
    from ..app.dashboard_truth import launch_inventory
    from ..ops import publication_authority as pa
    from ..products import launch0 as l0
    from .packet import _stored_release

    if inventory is None:
        inventory = _guard(lambda: launch_inventory(db))
    cleared = set(inventory.get("cleared_slugs") or [])
    failing = {r.get("slug"): r.get("failing") for r in inventory.get("products") or []}
    cap1 = set(l0.PROPOSED_SLUGS) if l0.CATALOGUE_FLOOR_APPROVED else set()
    products = []
    for cand_slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(cand_slug)
        truth = _guard(lambda: l0.product_truth(cand))
        releases = []
        for v in cand.variants:
            cir = l0.cir_for(v.build)
            stored = _guard(lambda: _stored_release(db, cir.slug, cir.version))
            if "stored" not in stored:
                stored = {"stored": False, "certified": False, "release": "",
                          "listing": None, "error": stored.get("why")}
            ev = _guard(lambda: pa.evidence(db, cir.slug, cir.version, stored["release"]))
            gates = {
                "certification": _certification(ev, stored),
                "product_truth": _product_truth(truth, cir.slug),
                "image_truth": _image_truth(ev),
                "listing_readiness": _listing_readiness(stored, cleared, failing, cir.slug),
                "price_plan": _price_plan(stored, cir.slug),
                "seo": _seo(ev),
                "disclosure": _disclosure(ev),
            }
            releases.append({"cir_slug": cir.slug, "version": cir.version,
                             "release": stored.get("release") or None, "gates": gates})
        summary = {g: _worst(r["gates"][g]["state"] for r in releases) for g in GATES}
        remaining = []
        for r in releases:
            for g in GATES:
                row = r["gates"][g]
                if row["state"] != PASS:
                    remaining.append({"release": r["cir_slug"], "gate": g,
                                      "state": row["state"], "remaining": row["remaining"],
                                      "owner": row["owner"]})
        products.append({
            "candidate": cand_slug, "title": cand.title,
            "scope": ("Launch-0 (CAP-1 addition; catalogue configuration approved, the "
                      "product itself not approved)" if cand_slug in cap1 else "Launch-0"),
            "releases": releases, "gates": summary,
            "ready_to_request_publication": all(s == PASS for s in summary.values()),
            "remaining": remaining,
            "owners": sorted({x["owner"] for x in remaining if x["owner"]}),
        })
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "gates": list(GATES), "products": products, "product_count": len(products),
            "publishes_anything": False,
            "rule": ("every state read at generation time; UNKNOWN is never PASS; publication "
                     "also needs policy, rollback, parity and a sealed owner grant per release "
                     "(ops.publication_authority), which this packet does not grant")}


def render_markdown(p: dict) -> str:
    head = "| product | " + " | ".join(p["gates"]) + " | owners of what remains |"
    sep = "|" + "---|" * (len(p["gates"]) + 2)
    lines = [f"# Launch-0 product readiness ({p['product_count']} products)", "",
             f"Generated {p['generated_at']} by `launch.product_readiness`. "
             f"Rule: {p['rule']}.", "",
             head, sep]
    for prod in p["products"]:
        lines.append(f"| {prod['candidate']} | "
                     + " | ".join(prod["gates"][g] for g in p["gates"])
                     + f" | {', '.join(prod['owners']) or '-'} |")
    lines += ["", "## What remains", ""]
    for prod in p["products"]:
        lines.append(f"### {prod['title']} (`{prod['candidate']}`) -- {prod['scope']}")
        seen = set()
        for x in prod["remaining"]:
            key = (x["gate"], x["remaining"], x["owner"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- **{x['gate']}** {x['state']} -> {x['remaining']} "
                         f"(owner: {x['owner']})")
        if not prod["remaining"]:
            lines.append("- nothing in these seven gates")
        lines.append("")
    return "\n".join(lines) + "\n"
