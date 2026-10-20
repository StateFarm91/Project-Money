"""First-sale readiness: every gate between the eight Launch-0 products and a first paid
download, per release and shop-wide, with its evidence and who acts (W4-FIRSTSALE).

Built on `launch.product_readiness` (certification, Product Truth, certified listing images,
listing draft, price, search certificate, disclosure -- read from the code that enforces them)
and adds the first-sale gates that packet does not carry:

==========================  ==================================================  ===========
gate                        read from                                           who acts
==========================  ==================================================  ===========
etsy_category       (B2)    the stored search profile's category + the newest   company
                            taxonomy snapshot (`commerce.category`)
vision_review       (B3)    `runtime.release.frame_review_state`                owner (fund
                                                                                image_vision)
image_upload_payload (B4)   `integrations.etsy_image_readiness.for_release`     company
etsy_upload_confirmed (B4)  `gates.first_customer.check_etsy_remote_state`      owner
durable_delivery    (B5)    `commerce.deliverables.durable_state`               company
physical_sample     (B4)    a full physical make bound to this content          owner/tester
                            (`gates.first_customer.physical_binding`)
publication_grant           `ops.publication_authority.resolve`                 owner
==========================  ==================================================  ===========

Rules: read at generation time, read only (no write, render, enqueue or provider call); a gate
that could not be read is UNKNOWN; UNKNOWN is never PASS; a non-PASS gate names who acts.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .product_readiness import COMPANY, FAIL, OWNER, PASS, UNKNOWN, _worst

FIRST_SALE_GATES: tuple[str, ...] = (
    "certification", "product_truth", "image_truth", "listing_readiness", "price_plan",
    "disclosure", "etsy_category", "seo", "vision_review", "image_upload_payload",
    "durable_delivery", "physical_sample", "etsy_upload_confirmed", "publication_grant")
BLOCKER = {"etsy_category": "B2", "seo": "B2", "vision_review": "B3",
           "image_upload_payload": "B4", "etsy_upload_confirmed": "B4/B5",
           "physical_sample": "B4", "durable_delivery": "B5/B6"}


def _g(state: str, why: str, *, owner: str = COMPANY, action: str = "", evidence: str = ""):
    state = state if state in (PASS, FAIL, UNKNOWN) else UNKNOWN
    return {"state": state, "why": str(why)[:400], "evidence": evidence,
            "who_acts": None if state == PASS else owner,
            "action": "" if state == PASS else action}


def _safe(fn, *, owner: str = COMPANY, evidence: str = ""):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN with the reason
        return _g(UNKNOWN, f"unreadable: {type(exc).__name__}: {str(exc)[:200]}", owner=owner,
                  evidence=evidence, action="make the reading readable")


def _category(db, slug: str, version: str) -> dict:
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile
    from ..integrations import etsy_taxonomy

    ev = "listing_search_profiles.category_status + etsy_taxonomy_snapshots"
    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug, ListingSearchProfile.version == version))
        status = row.category_status if row is not None else None
        tid = row.taxonomy_id if row is not None else None
        path = list(row.taxonomy_path or []) if row is not None else []
    snap = etsy_taxonomy.latest(db)
    if status == "CHOSEN" and tid is not None and snap is not None:
        node = next((n for n in snap["nodes"] if int(n["id"]) == int(tid)), None)
        if node is None:
            return _g(FAIL, f"stored taxonomy {tid} is not in the newest Etsy snapshot",
                      evidence=ev, action="re-run listing.seo against the newest snapshot")
        return _g(PASS, f"{tid}: {' > '.join(path or node['path_names'])} (Etsy snapshot "
                        f"{snap['id']})", evidence=ev)
    if snap is None:
        return _g(UNKNOWN, "Etsy's taxonomy has never been read here, so no category can be "
                  "matched", evidence=ev,
                  action="listing.taxonomy_refresh (daily; needs the etsy_api gate)")
    return _g(FAIL, ("category UNKNOWN: the matcher found no crochet-pattern node confirmed "
                     "by Etsy's own names or property values" if row is not None else
                     "no search profile is stored for this release"), evidence=ev,
              action=("next daily refresh records the real names and schemas (W4-FIRSTSALE "
                      "matcher), then listing.seo re-runs"))


def _vision(db, slug: str, version: str) -> dict:
    from ..runtime.release import frame_review_state

    st = frame_review_state(db, slug, version)
    if st.get("reviewed"):
        return _g(PASS, "every frame independently reviewed clear", evidence="#61 review")
    return _g(FAIL, st.get("why") or "frames unreviewed", owner=OWNER, evidence="#61 review",
              action=("approve a funded image_vision run (consequential spend), then "
                      "assets.build reviews every frame"))


def _upload_payload(db, slug: str, version: str, release: str, store_root) -> dict:
    from ..integrations import etsy_image_readiness as R

    got = R.for_release(db, slug, version, release=release, store_root=store_root)
    ev = "integrations.etsy_image_readiness (uploadListingImage, no Etsy call)"
    if got["state"] == PASS:
        return {**_g(PASS, f"{len(got['images'])} uploadListingImage requests match Etsy's "
                     f"documented contract; {len(got['warnings'])} recommendation(s) noted",
                     evidence=ev), "warnings": got["warnings"][:6]}
    return _g(FAIL, "; ".join(got.get("failures") or [got.get("why", "")])[:400], evidence=ev,
              action="rebuild the certified image set (assets.build) so its bytes are readable")


def _durable(db, slug: str, version: str) -> dict:
    from ..commerce import deliverables

    st = deliverables.durable_state(db, slug, version)
    return _g(st["state"], st["why"], evidence="commerce.deliverables.durable_state",
              action="launch.readiness secures the release (keep or byte-identical re-render)")


def _physical(db, cir) -> dict:
    from ..gates.first_customer import physical_binding

    b = physical_binding(db, cir)
    if any(c == "full_physical_make" for c in (b.get("bound_classes") or {}).values()):
        return _g(PASS, "a full physical make is bound to this content", evidence="PhysicalTest")
    return _g(FAIL, "no full physical make is bound to this exact content: gauge and size "
              "claims are unresolved", owner=OWNER, evidence="PhysicalTest rows",
              action="a tester crochets the sample and records it (tester roster)")


def _remote() -> dict:
    from ..gates.first_customer import check_etsy_remote_state

    c = check_etsy_remote_state()
    state = PASS if c.state == "PASS" else UNKNOWN
    return _g(state, c.detail, owner=OWNER, evidence=c.measured_on,
              action=("grant the first draft publication (sealed owner grant); the first "
                      "upload is read back from Etsy"))


def _grant(db, slug: str, version: str, release: str) -> dict:
    from ..ops import publication_authority as pa

    if not release:
        return _g(UNKNOWN, "no stored release to grant", owner=OWNER,
                  evidence="ops.publication_authority", action="certify the release first")
    why, ident = pa.resolve(db, slug=slug, version=version, release=release)
    if why is None:
        return _g(PASS, f"valid sealed owner grant #{ident}", evidence="ops.publication_authority")
    return _g(FAIL, why, owner=OWNER, evidence="ops.publication_authority",
              action="owner reviews the packet and records a sealed draft grant")


def _from_readiness(row: dict) -> dict:
    owner = row.get("owner") or COMPANY
    return _g(row.get("state", UNKNOWN), row.get("why", ""), owner=owner,
              evidence="launch.product_readiness", action=row.get("remaining", ""))


def build(db, *, readiness: dict | None = None, store_root=None) -> dict:
    """The first-sale view as a dict. Reads only."""
    from ..products import launch0 as l0
    from . import product_readiness

    readiness = readiness or product_readiness.build(db)
    by_release = {r["cir_slug"]: r for p in readiness["products"] for r in p["releases"]}
    products = []
    for cand_slug in l0.LAUNCH0_SLUGS:
        cand = l0.candidate(cand_slug)
        releases = []
        for v in cand.variants:
            cir = l0.cir_for(v.build)
            pr = by_release.get(cir.slug) or {"gates": {}, "release": None}
            rel = pr.get("release") or ""
            g = {k: _from_readiness(pr["gates"][k]) if k in pr["gates"] else
                 _g(UNKNOWN, "not read", action="read it")
                 for k in ("certification", "product_truth", "image_truth",
                           "listing_readiness", "price_plan", "disclosure", "seo")}
            g["etsy_category"] = _safe(lambda: _category(db, cir.slug, cir.version))
            g["vision_review"] = _safe(lambda: _vision(db, cir.slug, cir.version), owner=OWNER)
            g["image_upload_payload"] = _safe(
                lambda: _upload_payload(db, cir.slug, cir.version, rel, store_root))
            g["durable_delivery"] = _safe(lambda: _durable(db, cir.slug, cir.version))
            g["physical_sample"] = _safe(lambda: _physical(db, cir), owner=OWNER)
            g["etsy_upload_confirmed"] = _safe(_remote, owner=OWNER)
            g["publication_grant"] = _safe(lambda: _grant(db, cir.slug, cir.version, rel),
                                           owner=OWNER)
            for k, b in BLOCKER.items():
                g[k]["blocker"] = b
            releases.append({"cir_slug": cir.slug, "version": cir.version,
                             "release": rel or None,
                             "gates": {k: g[k] for k in FIRST_SALE_GATES}})
        summary = {k: _worst(r["gates"][k]["state"] for r in releases)
                   for k in FIRST_SALE_GATES}
        acts = sorted({r["gates"][k]["who_acts"] for r in releases for k in FIRST_SALE_GATES
                       if r["gates"][k]["who_acts"]})
        products.append({"candidate": cand_slug, "title": cand.title, "releases": releases,
                         "gates": summary,
                         "first_sale_ready": all(s == PASS for s in summary.values()),
                         "who_acts": acts})
    shop = _shop(db, products)
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "gates": list(FIRST_SALE_GATES), "products": products, "shop": shop,
            "first_sale_possible": any(p["first_sale_ready"] for p in products)
            and all(v["state"] == PASS for v in shop.values()),
            "publishes_anything": False,
            "rule": ("read at generation time; UNKNOWN is never PASS; no gate here grants "
                     "publication")}


def _shop(db, products: list[dict]) -> dict:
    from ..core import phase as phase_mod
    from ..integrations import etsy_taxonomy

    out = {}

    def phase_gate():
        p = phase_mod.resolve(db) or {}
        name = str(getattr(p.get("phase"), "value", p.get("phase")) or "")
        live = name.lower() in ("production", "limited_production")
        return _g(PASS if live else FAIL, f"operating phase {name or 'unread'}", owner=OWNER,
                  evidence="core.phase.resolve",
                  action="owner go-live decision after the acceptance gates pass")

    def taxonomy_gate():
        snap = etsy_taxonomy.latest(db)
        if snap is None:
            return _g(UNKNOWN, "Etsy's taxonomy has never been read", evidence="snapshot",
                      action="listing.taxonomy_refresh")
        return _g(PASS, f"snapshot {snap['id']}: {len(snap['nodes'])} nodes read from Etsy "
                  f"({snap.get('confirmed_at')})", evidence="etsy_taxonomy_snapshots")

    def all_products(key, label, owner):
        states = [p["gates"][key] for p in products]
        worst = _worst(states)
        return _g(worst, f"{label}: " + ", ".join(f"{p['candidate']} {p['gates'][key]}"
                                                    for p in products)[:380], owner=owner,
                  evidence=f"per-product {key}", action=f"see each product's {key}")

    out["operating_phase"] = _safe(phase_gate, owner=OWNER)
    out["etsy_taxonomy_read"] = _safe(taxonomy_gate)
    out["category_matched"] = all_products("etsy_category", "category", COMPANY)
    out["durable_delivery"] = all_products("durable_delivery", "certified PDFs held", COMPANY)
    out["etsy_upload_confirmed"] = _safe(_remote, owner=OWNER)
    return out


def render_markdown(v: dict) -> str:
    lines = [f"# First-sale readiness ({len(v['products'])} products)", "",
             f"Generated {v['generated_at']} by `launch.first_sale`. {v['rule']}.", "",
             "| product | " + " | ".join(v["gates"]) + " | who acts |",
             "|" + "---|" * (len(v["gates"]) + 2)]
    for p in v["products"]:
        lines.append(f"| {p['candidate']} | " + " | ".join(p["gates"][g] for g in v["gates"])
                     + f" | {', '.join(p['who_acts']) or '-'} |")
    lines += ["", "## Shop-wide", "", "| gate | state | why | who acts |", "|---|---|---|---|"]
    for k, g in v["shop"].items():
        lines.append(f"| {k} | {g['state']} | {g['why'][:160]} | {g['who_acts'] or '-'} |")
    return "\n".join(lines) + "\n"
