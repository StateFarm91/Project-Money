"""Product inventory: every product the company has, what is real about it, and what blocks sale.

W4-PIPE. The owner's dashboard reads "16 drafted listings, several certified products, 166
deliveries, 0 live". Those are counts. This module answers the question behind them, per
product: what exists, whether Product Truth holds *today* (re-computed from the CIR, never read
from an old certificate), what blocks publication -- each blocker one gate with its evidence and
the party who can clear it -- and the shortest path from here to a live listing.

Three sources, never blended without a label:

* ``static``  -- computed here, now, from the repository: build the CIR, compile it, certify it,
  and run the name-versus-fabric gates (`launch0.title_promise`, `assembly_promise`,
  `fabric_truth`). Deterministic validation wins over any other source.
* ``chain``   -- read from a database the release chain ran on (a scratch shadow DB in tests and
  in the W4 evidence run): the stored release, the disclosed imagery record, the search
  certificate and the publication verdict (`publish.eligibility.product_publication`).
* ``production`` -- a read-only snapshot of production's public aggregate endpoints, passed in
  by the caller. Labelled as an observation of a deployed build (which may be older than this
  code), never as the state of this code.

Every blocker is classified by who can clear it: COMPANY (executable work), OWNER (KYC, legal,
banking, spend, a recorded owner decision), EXTERNAL (a provider/integration), DATA (market
evidence that cannot exist before launch), DEPLOY (needs a release of this code to production,
which is the integrator's/owner's step, not this module's). Company work is never reported as
owner-gated.
"""
from __future__ import annotations

from typing import Any

COMPANY = "COMPANY"
OWNER = "OWNER"
EXTERNAL = "EXTERNAL"
DATA = "DATA"
DEPLOY = "DEPLOY"
CLEARERS = (COMPANY, OWNER, EXTERNAL, DATA, DEPLOY)

# Gates that block *every* product equally. They are listed once per inventory, not repeated
# as per-product blockers, so a product's own list shows what is specific to it.
SHOP_WIDE_GATES: tuple[dict, ...] = (
    {"gate": "etsy_shop_kyc", "clearer": OWNER,
     "evidence": "launch.readiness etsy_shop: platform identity verification cannot be "
                 "automated (CLAUDE.md non-negotiable)"},
    {"gate": "payout_banking", "clearer": OWNER,
     "evidence": "launch.readiness payout: banking credentials are entered by the holder"},
    {"gate": "listing_fees_approval", "clearer": OWNER,
     "evidence": "launch.readiness listing_fees: first spend that leaves the account"},
    {"gate": "phase_shadow", "clearer": OWNER,
     "evidence": "core.phase: BRAMBLELOOP_PHASE=shadow; store.publish refuses in shadow"},
    {"gate": "publication_grant", "clearer": OWNER,
     "evidence": "D-FB-10: store.publish needs a sealed, scoped owner publication grant per "
                 "release; gates.first_customer.authorises_publication is constant False"},
    {"gate": "durable_artifact_storage", "clearer": OWNER,
     "evidence": "launch.readiness artifact_storage: ArtifactStore.durable is False; "
                 "first_customer fulfilment_and_download FAILs until storage is approved"},
    {"gate": "catalogue_depth_threshold", "clearer": OWNER,
     "evidence": "launch.readiness MIN_LISTINGS_TO_OPEN=8 products; D-FB-9 records the open "
                 "owner decision (keep 8 or set a Launch-0 depth). Launch-0 is capped at 5 "
                 "products by tests/test_launch0.py"},
    {"gate": "image_vision_hero", "clearer": OWNER,
     "evidence": "D-FB-9: Launch-0 parity HERO needs the image_vision gate (owner ruling)"},
    {"gate": "competitive_blind_review", "clearer": DATA,
     "evidence": "D-FB-9: COMPETITIVE parity needs a blind review over observed benchmark "
                 "galleries (data + image_vision)"},
)


def _engineered(slug: str, version: str | None = None):
    from ..runtime.pipeline import _engineered_cir

    return _engineered_cir(slug, version)


def universe(extra: tuple[str, ...] | list[str] = ()) -> list[str]:
    """Every product slug the repository can build or has ever listed, sorted.

    Measures: the flat catalogue, the engineered map (Launch-0 variants included), the
    retired concept slugs, the collection bundle, and any slug the caller saw elsewhere
    (production's catalogue). A slug listed in production that this code cannot build is
    still inventoried -- that mismatch is itself a finding.
    """
    from ..products import builder, launch0
    from ..runtime.pipeline import ENGINEERED

    slugs = set(builder.CATALOGUE) | set(ENGINEERED) | set(launch0.LEGACY_DUPLICATES)
    slugs |= set(extra or ())
    return sorted(s for s in slugs if s)


def static_truth(slug: str) -> dict:
    """Product Truth for `slug` computed now from its CIR. Never reads a stored certificate."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..gates.certificate import certify
    from ..products import launch0

    out: dict[str, Any] = {"slug": slug, "source": "static"}
    retired = launch0.LEGACY_DUPLICATES.get(slug)
    if retired is not None:
        out.update({"exists": False, "retired": dict(retired),
                    "why": "a retired concept slug: its pattern is a Launch-0 variant"})
        return out
    try:
        cir = _engineered(slug)
    except Exception as exc:  # noqa: BLE001 - a design that cannot be built is a finding
        out.update({"exists": False, "why": f"build raised {type(exc).__name__}: {exc}"[:300]})
        return out
    if cir is None:
        out.update({"exists": False,
                    "why": "no CIR route: not in the catalogue, the engineered map or Launch-0"})
        return out
    result = compile_cir(cir)
    cert = certify(cir)
    errors = [f for f in cert.findings if str(getattr(f, "severity", "")).upper().endswith("ERROR")]
    out.update({
        "exists": True, "title": cir.title, "version": cir.version,
        "construction": cir.construction, "risk_class": cir.risk_class,
        "components": [{"name": c.name, "make": c.make} for c in cir.components],
        "compiles": result.ok, "compile_warnings": len(result.warnings),
        "certified": bool(cert.granted),
        "release_hash": (cert.release_hash or "")[:12] or None,
        "certificate_errors": [str(f)[:260] for f in errors],
        "title_promise": launch0.title_promise(cir),
        "assembly_promise": launch0.assembly_promise(cir),
    })
    if result.ok:
        twin = build_twin(cir, result)
        out.update({
            "fabric_truth": launch0.fabric_truth(cir, twin),
            "width_cm": round(twin.width_cm, 1) if twin.width_cm else None,
            "height_cm": round(twin.height_cm, 1) if twin.height_cm else None,
            "shape": twin.shape, "calibrated": bool(twin.calibrated),
        })
    out["launch_scope"] = slug in launch0.launch_scope_slugs()
    cand = launch0.candidate_for_cir(slug)
    out["launch0_candidate"] = cand.slug if cand else None
    out["product_truth_ok"] = bool(
        out["compiles"] and out["certified"] and out["title_promise"].get("backed")
        and out["assembly_promise"].get("backed")
        and out.get("fabric_truth", {}).get("backed"))
    return out


def chain_evidence(db, slug: str, version: str | None = None, *, today=None) -> dict:
    """What the release chain left in `db` for this product: release, imagery, publish verdict.

    `for_publish` records the verdicts it computes (listing-set certificate, hero), so `db`
    must be a scratch shadow database, never production's."""
    from sqlalchemy import select

    from ..core.models import AuditLog, Job, JobStatus, Listing, PatternVersion, Product

    out: dict[str, Any] = {"slug": slug, "source": "chain"}
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            out["release"] = None
            jobs = [j for j in s.scalars(select(Job)) if (j.inputs or {}).get("slug") == slug]
            out["jobs"] = sorted({f"{j.job_type}:{j.status.value if hasattr(j.status, 'value') else j.status}"
                                  for j in jobs})
            return out
        q = select(PatternVersion).where(PatternVersion.product_id == product.id)
        if version:
            q = q.where(PatternVersion.version == version)
        pv = s.scalar(q.order_by(PatternVersion.id.desc()).limit(1))
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug)
                           .order_by(Listing.id.desc()).limit(1))
        out["release"] = None if pv is None else {
            "version": pv.version, "certified": bool(pv.certified),
            "release_hash": (pv.release_hash or "")[:12]}
        out["listing"] = None if listing is None else {
            "id": listing.id, "version": listing.version, "state": listing.state,
            "title": listing.title, "tags": len(listing.tags or []),
            "price_cad": listing.price_cad, "on_etsy": bool(listing.etsy_listing_id)}
        publishes = [j for j in s.scalars(select(Job).where(Job.job_type == "store.publish"))
                     if (j.inputs or {}).get("slug") == slug]
        last = publishes[-1] if publishes else None
        out["store_publish"] = None if last is None else {
            "status": last.status.value if hasattr(last.status, "value") else str(last.status),
            "error": (last.last_error or "")[:400],
            "outputs": {k: (v if len(str(v)) < 400 else str(v)[:400])
                        for k, v in (last.outputs or {}).items()}}
        refusals = [r.detail for r in s.scalars(
            select(AuditLog).where(AuditLog.action == "store.publish_refused")
            .order_by(AuditLog.id.desc())) if (r.artifact or "").startswith(slug + "@")]
        out["publish_refusal"] = (None if not refusals else
                                  {k: str(v)[:300] for k, v in refusals[0].items()})
    version = (out["release"] or {}).get("version") or version
    # Imagery: the record the listing would export.
    try:
        from ..publish import listing_asset

        rec = listing_asset.last(db, slug=slug)
        out["imagery"] = None if rec is None else {
            "kind": rec.get("kind") or "photograph", "made": bool(rec.get("made")),
            "usable": listing_asset.usable(rec), "version": rec.get("version"),
            "frames": len(rec.get("frames") or ([rec] if rec.get("made") else [])),
            "launch_blocked": (rec.get("launch_blocked") or [])[:5]}
    except Exception as exc:  # noqa: BLE001
        out["imagery"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    if version:
        # The verdict store.publish itself computes (release_gates.for_publish): staleness,
        # window, listing set, search certificate, standards, withholding and the product
        # scope (legacy quarantine, name truth, first-customer gate) -- every reason.
        try:
            from datetime import date as _date

            from ..publish.release_gates import for_publish

            verdict = for_publish(db, slug=slug, version=version, today=today or _date.today())
            out["publish_verdict"] = {"blocks_release": verdict["blocks_release"],
                                      "reasons": [str(r)[:300] for r in verdict["reasons"]],
                                      "search": (verdict.get("search") or {}).get("verdict")}
        except Exception as exc:  # noqa: BLE001 - an uncomputable verdict is a finding
            out["publish_verdict"] = {"error": f"{type(exc).__name__}: {exc}"[:300],
                                      "blocks_release": True, "reasons": []}
    return out


def _blockers(st: dict, ch: dict | None, prod: dict | None) -> list[dict]:
    """Per-product blockers, each one gate with evidence and who can clear it."""
    out: list[dict] = []

    def add(gate, clearer, evidence, action=""):
        out.append({"gate": gate, "clearer": clearer, "evidence": evidence, "action": action})

    if st.get("retired"):
        add("retired_duplicate", COMPANY, st["retired"]["why"],
            f"never publish; withdraw the production draft and publish "
            f"{', '.join(st['retired']['superseded_by'])} instead")
        return out
    if not st.get("exists"):
        add("no_cir", COMPANY, st.get("why", ""), "design the product or drop the listing")
        return out
    for err in st.get("certificate_errors") or []:
        if "UNCALIBRATED_PRIMITIVE" in err:
            add("physical_calibration", OWNER, err,
                "a pattern tester works one sample of the new stitch (tester_roster outreach); "
                "owner parked self-crocheting on 2026-09-20")
        elif "GAUGE_OUTSIDE_DECLARED_YARN_BAND" in err:
            add("gauge_truth", COMPANY, err,
                "re-engineer from the declared yarn band (builder._derive_from_yarn) under a "
                "new version, or retire the design")
        else:
            add("certificate", COMPANY, err, "fix the CIR so it certifies")
    for key, gate in (("title_promise", "name_count_truth"),
                      ("assembly_promise", "name_assembly_truth"),
                      ("fabric_truth", "name_fabric_truth")):
        v = st.get(key) or {}
        if v and not v.get("backed"):
            add(gate, COMPANY, v.get("why", ""),
                "rename to what the fabric makes, or change the CIR so it makes what the name "
                "says (merchandising decision, company-side)")
    if not st.get("launch_scope"):
        add("outside_launch_scope", COMPANY,
            "not a Launch-0 slug: no disclosed imagery (D-FB-7 is scoped to Launch-0) and no "
            "first-customer review; counts toward catalogue depth only if re-certified under "
            "the current gauge standard",
            "promote into Launch-0 (cap 5 products) or wait for a qualified photograph")
    if ch:
        img = ch.get("imagery")
        if st.get("launch_scope") and not (img and img.get("usable")):
            add("listing_imagery", COMPANY,
                f"no usable listing imagery on the chain DB: {img}", "re-run assets.build")
        if ch.get("release") is None:
            add("not_built_by_planner", COMPANY,
                f"the shadow plan.cycle never drafted this product (jobs: {ch.get('jobs')})",
                "enqueue cir.draft for it (products.pipeline_board feeds every Launch-0 slug)")
        for r in (ch.get("publish_verdict") or {}).get("reasons", []):
            gate, clearer, action = classify_reason(r)
            add(gate, clearer, r, action)
        if (ch.get("publish_verdict") or {}).get("error"):
            add("publish_verdict_error", COMPANY, ch["publish_verdict"]["error"], "fix the crash")
    if prod:
        if prod.get("version") and st.get("version") and prod["version"] != st["version"]:
            add("production_stale", DEPLOY,
                f"production lists {prod['version']} (chain_version "
                f"{prod.get('chain_version')}); this code releases {st['version']}",
                "deploy this build, then chain.rebuild re-certifies and redrafts")
        if prod.get("photography") in ("no_asset", "unusable"):
            add("production_imagery", DEPLOY if st.get("launch_scope") else COMPANY,
                f"production asset-coverage: {prod['photography']}",
                "deploy (Launch-0 disclosed renders exist in this code)"
                if st.get("launch_scope") else "no imagery route outside Launch-0")
    return out


# store.publish reason text -> (gate, clearer, action). First match wins; the default is
# company work, so an unrecognised reason can never be reported as somebody else's job.
REASON_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("category UNKNOWN", "etsy_taxonomy_snapshot", EXTERNAL,
     "listing.taxonomy_refresh against Etsy's read-only taxonomy (needs the deployed app's "
     "Etsy credentials); no node is assumed"),
    ("no category, so no property schema", "etsy_taxonomy_snapshot", EXTERNAL,
     "follows the taxonomy snapshot"),
    ("gauge_and_size_claims", "physical_sample", OWNER,
     "a pattern tester works this content (tester_roster); owner parked self-crocheting"),
    ("etsy_remote_state", "etsy_remote_confirmation", EXTERNAL,
     "first authorised Etsy draft confirms image upload / remote state"),
    ("fulfilment_and_download", "durable_artifact_storage", OWNER,
     "owner approves object storage (CA$1-5/month, existing ceiling)"),
    ("NAME_OUTRUNS_PATTERN", "name_truth", COMPANY,
     "rename to what the pattern makes or change the CIR (new version)"),
    ("RETIRED_DUPLICATE", "retired_duplicate", COMPANY, "withdraw; publish the successor"),
    ("LEGACY_PRE_CALIBRATION", "release_on_file", COMPANY, "re-certify under current standard"),
    ("NOT_CERTIFIED", "release_on_file", COMPANY, "certify"),
    ("image_vision", "image_vision_hero", OWNER, "owner ruling on the vision gate"),
    ("missed window", "seasonal_window", COMPANY, "reschedule to the next buying window"),
    ("owner veto", "owner_veto", OWNER, "owner rules on the veto"),
    ("mobile QA", "listing_imagery_qa", COMPANY, "repair the frames the mobile QA flags"),
    ("listing-set certificate", "listing_set_certificate", COMPANY,
     "issue the listing-set certificate once the frame gates pass"),
    ("hero", "search_hero", COMPANY, "frame 1 must pass all four gates"),
    ("search certificate", "search_certificate", COMPANY, "re-run listing.seo"),
)


def classify_reason(reason: str) -> tuple[str, str, str]:
    for needle, gate, clearer, action in REASON_RULES:
        if needle in reason:
            return gate, clearer, action
    return "publish_gate", COMPANY, "clear the named gate"


def shortest_path(st: dict, blockers: list[dict]) -> list[str]:
    company = [b for b in blockers if b["clearer"] == COMPANY]
    steps = []
    for b in company:
        steps.append(f"[company] {b['gate']}: {b['action'] or 'fix'}")
    for b in blockers:
        if b["clearer"] in (DEPLOY,):
            steps.append(f"[deploy] {b['gate']}: {b['action']}")
    for b in blockers:
        if b["clearer"] in (OWNER, EXTERNAL, DATA):
            steps.append(f"[{b['clearer'].lower()}] {b['gate']}: {b['action'] or b['evidence'][:120]}")
    steps.append("[owner, shop-wide] Etsy shop + KYC, payout, listing fees, phase, publication "
                 "grant per release (see shop_wide_gates)")
    return steps


def classify(st: dict, blockers: list[dict]) -> str:
    """One word for where the product stands, worst first."""
    gates = {b["gate"] for b in blockers}
    if st.get("retired"):
        return "RETIRE"
    if not st.get("exists"):
        return "NO_CIR"
    if any(b["clearer"] == COMPANY and b["gate"] != "outside_launch_scope" for b in blockers):
        return "COMPANY_WORK"
    if "physical_calibration" in gates:
        return "OWNER_GATED_PHYSICAL"
    if "outside_launch_scope" in gates:
        return "TRUTHFUL_RESERVE"
    return "OWNER_AND_DEPLOY_GATED"


def inventory(*, db=None, production: dict | None = None, extra_slugs=(), today=None) -> dict:
    """The full product inventory. `production` maps slug -> observed production listing."""
    production = production or {}
    items = []
    for slug in universe(tuple(extra_slugs) + tuple(production)):
        st = static_truth(slug)
        ch = (chain_evidence(db, slug, st.get("version"), today=today)
              if (db is not None and st.get("exists")) else None)
        prod = production.get(slug)
        blockers = _blockers(st, ch, prod)
        items.append({"slug": slug, "status": classify(st, blockers), "static": st,
                      "chain": ch, "production": prod, "blockers": blockers,
                      "owner_action_required": sorted({b["gate"] for b in blockers
                                                       if b["clearer"] == OWNER}),
                      "shortest_path": shortest_path(st, blockers)})
    counts: dict[str, int] = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    return {"products": items, "counts": counts, "shop_wide_gates": list(SHOP_WIDE_GATES),
            "clearers": list(CLEARERS)}
