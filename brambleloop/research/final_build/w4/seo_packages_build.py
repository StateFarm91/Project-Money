"""W4-SEO: build the Etsy search package for every product in the catalogue, and report.

For every product with a CIR (`products.launch0.excluded_from_launch0()` enumerates all of
them: the flat catalogue, the nordic-forest sizes, the three market baskets and the hexagon
coaster set), this runs the REAL release chain -- gate.certify -> listing.draft ->
assets.build -> pricing.position -> listing.seo -- in a shadow worker on a scratch SQLite
database with every outbound socket refused. `listing.seo` persists each listing's search
package (`seo.packages`); this script reads the packages back and writes
SEO_PACKAGES.json / SEO_PACKAGES.md beside it.

The latest MJS findings (`MJS_FINDINGS.json`, lane W4-MJS: aggregated from the production
build's public read-only benchmark endpoints) are stored as the `mjs.findings` reading the
runtime writes, so each package's `competitive` block reads them through the same code path
as production (`intel.findings.latest`). PIPE's `PRODUCT_INVENTORY_BEFORE.json` (local file,
else `origin/claude/w4-PIPE`) is cross-referenced for each product's pipeline status.

No Etsy taxonomy snapshot is loaded: that is the company's real state (no keystring, the
tree has never been read), so every category is UNKNOWN and no taxonomy id is assumed.
No network, no Etsy write, no spend.

Run: cd brambleloop && PYTHONPATH=src python research/final_build/w4/seo_packages_build.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(__file__).resolve().parent
TMP = tempfile.mkdtemp(prefix="w4_seo_build_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(TMP, "artifacts")
for k in list(os.environ):
    if k.startswith(("ETSY", "ANTHROPIC_API", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(k)


def _closed(*_a, **_k):
    raise OSError("network closed for the W4-SEO package build")


socket.socket.connect = _closed            # type: ignore[assignment]
socket.create_connection = _closed         # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce import search_evidence as se  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Listing, Phase  # noqa: E402
from brambleloop.products import builder as flat  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.products import nordic_forest, texture, vessels  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.seo import packages as P  # noqa: E402
from brambleloop.seo import strategy  # noqa: E402

CHAIN = ("gate.certify", "listing.draft", "assets.build", "pricing.position", "listing.seo")


def _builders() -> dict:
    out = {}
    for slug in flat.CATALOGUE:
        out[slug] = (lambda s=slug: flat.for_slug(s))
    for size in nordic_forest.SIZES:
        out[f"nordic-forest-{size}"] = (lambda s=size: nordic_forest.build(s))
    for size in ("small", "medium", "large"):
        out[f"market-basket-{size}"] = (lambda s=size: vessels.build_basket(s))
    out["hexagon-coaster-set"] = vessels.build_hexagon_coaster
    # texture designs: outside products.launch0's inventory, listed by PIPE's inventory
    out["chunky-ribbed-scarf"] = texture.build_ribbed_scarf
    out["bobble-floor-pillow"] = texture.build_bobble_pillow
    out["heirloom-cable-blanket"] = texture.build_cable_throw
    return out


def _pipe_inventory() -> dict:
    import subprocess

    local = OUT / "PRODUCT_INVENTORY_BEFORE.json"
    try:
        text = local.read_text() if local.exists() else subprocess.run(
            ["git", "show", "origin/claude/w4-PIPE:brambleloop/research/final_build/w4/"
             "PRODUCT_INVENTORY_BEFORE.json"], capture_output=True, text=True, check=True,
            cwd=ROOT).stdout
        d = json.loads(text)
    except Exception:  # noqa: BLE001 - absent inventory is reported as absent
        return {}
    return {p["slug"]: {"status": p.get("status"),
                        "blockers": [f"{b.get('gate')} ({b.get('clearer')})"
                                     if isinstance(b, dict) else str(b)
                                     for b in (p.get("blockers") or [])][:8],
                        "inventory_generated_at": d.get("generated_at")}
            for p in d.get("products") or []}


def _seed_findings(db) -> dict | None:
    from brambleloop.core.models import OperatingReading
    from brambleloop.intel import findings as F

    path = OUT / "MJS_FINDINGS.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    with db.session() as s:
        s.add(OperatingReading(kind=F.KIND, period_key=str(payload.get("as_of")),
                               payload=payload))
    return {"file": "research/final_build/w4/MJS_FINDINGS.json", "as_of": payload.get("as_of"),
            "findings": len(payload.get("findings") or []),
            "evidence_source": (payload.get("evidence_source") or {}).get("kind")}


def main() -> dict:
    t0 = time.time()
    inventory = {r["key"]: r for r in L.excluded_from_launch0()}
    builders = _builders()
    db = Database(f"sqlite:///{TMP}/build.sqlite", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    findings_src = _seed_findings(db)
    pipe = _pipe_inventory()
    cirs = {}
    for key, make in sorted(builders.items()):
        cir = make()
        cirs[cir.slug] = key
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key=f"cert-{key}", priority=0)
    worker = Worker(db, "w4-seo-build", phase=Phase.SHADOW, job_types=list(CHAIN),
                    lease_seconds=1800)
    for _ in range(600):
        if not worker.run_once():
            break
    with db.session() as s:
        jobs = [{"type": j.job_type, "status": j.status.value,
                 "slug": (j.inputs or {}).get("slug") or ((j.inputs or {}).get("cir") or {})
                 .get("slug"), "error": (j.last_error or "")[-300:],
                 "result": j.outputs if j.job_type == "listing.seo" else None}
                for j in s.scalars(select(Job).where(Job.job_type.in_(CHAIN)))]
        blocked = {a.artifact.split("@")[0]: list((a.detail or {}).get("blocking") or [])[:6]
                   for a in s.scalars(select(AuditLog).where(
                       AuditLog.action == "listing.seo_blocked"))}
        listings = {r.product_slug: r.version for r in s.scalars(select(Listing))}
    products = []
    for cir_slug, key in sorted(cirs.items()):
        inv = inventory.get(key) or {}
        version = listings.get(cir_slug)
        pkg = P.current(db, cir_slug, version) if version else None
        if pkg is None and version is None:
            # listing.seo blocked or never ran: assemble whatever profile exists, for honesty
            from brambleloop.core.models import ListingSearchProfile

            with db.session() as s:
                prof = s.scalar(select(ListingSearchProfile).where(
                    ListingSearchProfile.product_slug == cir_slug))
                v = prof.version if prof else None
            pkg = P.assemble(db, cir_slug, v) if v else None
        stuck = [j for j in jobs if j["slug"] == cir_slug and j["status"] != "done"]
        pipe_row = pipe.get(cir_slug) or pipe.get(key) or next(
            (v for k2, v in sorted(pipe.items(), key=lambda kv: -len(kv[0]))
             if cir_slug.startswith(k2 + "-")), None)
        if not inv:   # not in products.launch0's inventory: viability is PIPE's verdict
            inv = {"gate_clean": False, "gate_reasons": [
                "not in products.launch0 inventory (no Product Truth gate run there); PIPE: "
                + "; ".join((pipe_row or {}).get("blockers") or ["no PIPE row"])]}
        products.append({
            "key": key, "slug": cir_slug, "title": inv.get("title"),
            "in_launch0": inv.get("in_launch0"),
            "product_truth_gate_clean": inv.get("gate_clean"),
            "product_truth_reasons": inv.get("gate_reasons") or [],
            "viable": bool(inv.get("gate_clean")),
            "listing_drafted": version is not None,
            "draft_blocking": blocked.get(cir_slug, []),
            "chain_not_done": [(j["type"], j["status"], j["error"][-160:]) for j in stuck],
            "pipeline": pipe_row,
            "package": pkg,
        })
    gate = se.supremacy_gate(db)
    viable = [p for p in products if p["viable"]]
    with_pkg = [p for p in products if p["package"]]
    counts = {
        "products_with_cir": len(products),
        "viable_product_truth_clean": len(viable),
        "not_viable_product_truth": len(products) - len(viable),
        "listings_drafted": sum(p["listing_drafted"] for p in products),
        "packages": len(with_pkg),
        "packages_for_viable": sum(1 for p in viable if p["package"]),
        "certificate_pass": sum(1 for p in with_pkg
                                if p["package"]["certificate"]["verdict"] == "PASS"),
        "certificate_fail": sum(1 for p in with_pkg
                                if p["package"]["certificate"]["verdict"] != "PASS"),
        "readiness": {},
    }
    for p in with_pkg:
        st = p["package"]["readiness"]["state"]
        counts["readiness"][st] = counts["readiness"].get(st, 0) + 1
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "research/final_build/w4/seo_packages_build.py (real release chain, "
                        "shadow worker, scratch SQLite, network closed, no Etsy taxonomy "
                        "snapshot)",
        "seconds": round(time.time() - t0, 1),
        "counts": counts,
        "competitor_findings_source": findings_src,
        "supremacy_gate": {k: gate[k] for k in ("cleared", "failed", "unmeasured", "why")},
        "product_level_plan": {
            "note": "seo.strategy.plan(): the Launch-0 product-level search decisions (the "
                    "baskets as ONE listing in three sizes). The release chain still drafts "
                    "one listing per basket size (open K1 wiring request: product.assemble).",
            "products": [{k: p.get(k) for k in ("slug", "title", "tags", "ok", "problems")}
                         for p in strategy.plan().get("products", [])],
        },
        "products": products,
    }
    (OUT / "SEO_PACKAGES.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
    (OUT / "SEO_PACKAGES.md").write_text(_markdown(report))
    return counts


def _markdown(r: dict) -> str:
    c = r["counts"]
    lines = [
        "# SEO packages: every catalogue product's Etsy search package (W4-SEO)",
        "",
        f"Generated {r['generated_at']} by `{r['generated_by']}`. The machine record is "
        "`SEO_PACKAGES.json`; packages are also persisted by `listing.seo` in "
        "`seo_search_packages` (`seo.packages`) and refreshed by every `seo.cycle`.",
        "",
        "## Counts",
        "",
        f"- Products with a CIR: **{c['products_with_cir']}**",
        f"- Viable (Product Truth clean: title, assembly and fabric promises backed): "
        f"**{c['viable_product_truth_clean']}**; not viable: {c['not_viable_product_truth']}",
        f"- Listings drafted by the real chain: **{c['listings_drafted']}**",
        f"- Search packages persisted: **{c['packages']}** "
        f"({c['packages_for_viable']} for viable products)",
        f"- Search certificate PASS: **{c['certificate_pass']}**; FAIL/REFUSED: "
        f"**{c['certificate_fail']}**",
        f"- Readiness: {c['readiness']}",
        f"- Supremacy gate cleared: {r['supremacy_gate']['cleared']} "
        f"(failed {r['supremacy_gate']['failed']}, unmeasured "
        f"{r['supremacy_gate']['unmeasured']})",
        "",
        "## Why the certificate fails",
        "",
        "The F-004 search certificate needs a category CHOSEN from a stored Etsy seller-taxonomy "
        "snapshot. None exists: there is no app keystring in this environment and the read-only "
        "endpoint answers 403 without one, so no taxonomy id is assumed and the `category` and "
        "`attributes` checks fail. For a package marked EXTERNAL_GATED every other check passes: "
        "copy, tags, description and the hero. The gate: " + P.TAXONOMY_GATE + ".",
        "",
        "Search volume: none. No Etsy search-volume figure is measured for any phrase. Tag "
        "bases are `observed` (dated buyer language) or `modelled` (query-model templates). "
        "The model's demand and competition constants are not copied into packages.",
        "",
        "## Per product",
        "",
        "Competitor context: " + (
            f"`{r['competitor_findings_source']['file']}` (as of "
            f"{r['competitor_findings_source']['as_of']}; one benchmark seller, production "
            "public read-only endpoints). Benchmark price IQR is `observed` for that seller; "
            "favourites are a demand `proxy`; seasonal pods are a seasonality `proxy`. It is "
            "not the Etsy market and no competitor copy is stored."
            if r.get("competitor_findings_source") else "no MJS findings file: UNKNOWN."),
        "",
        "| Product | Viable | PIPE status | Readiness | Certificate | Title (chars) | Tags (basis) | Price CAD | Benchmark pod: median (IQR) → position | Fav. proxy | Primary intent |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in r["products"]:
        k = p["package"]
        if k is None:
            why = "; ".join((p["draft_blocking"] or p["product_truth_reasons"]
                             or [str(p["chain_not_done"])])[:2])[:160]
            lines.append(f"| {p['slug']} | {p['viable']} | "
                         f"{(p.get('pipeline') or {}).get('status')} | no package | - | - | - "
                         f"| - | - | - | {why} |")
            continue
        tb = k["tags"]["basis_counts"]
        cp = k.get("competitive") or {}
        bp = cp.get("price") or {}
        bench = (f"{cp.get('pod')}: {bp.get('median_cad')} ({bp.get('p25_cad')}-"
                 f"{bp.get('p75_cad')}, n={bp.get('n')}) → {bp.get('position')}"
                 if bp else f"{cp.get('pod')}: UNKNOWN")
        fav = (cp.get("demand_proxy") or {}).get("median_favourites", "UNKNOWN")
        lines.append(
            f"| {p['slug']} | {p['viable']} | {(p.get('pipeline') or {}).get('status')} | "
            f"{k['readiness']['state']} | "
            f"{k['certificate']['verdict']} (failed {k['certificate']['failed']}) | "
            f"{(k['title']['text'] or '')[:70]}... ({k['title']['chars']}) | "
            f"{k['tags']['count']} (obs {tb['observed']}, mod {tb['modelled']}, "
            f"meas {tb['measured']}) | {k['pricing']['price_cad']} | {bench} | {fav} | "
            f"{(k['primary_intent'] or {}).get('phrase')} |")
    below = [p["slug"] for p in r["products"] if p["package"] and
             ((p["package"].get("competitive") or {}).get("price") or {}).get("position")
             == "below benchmark p25"]
    hero = [p["slug"] for p in r["products"] if p["viable"] and p["package"] and
            "hero" in (p["package"]["certificate"]["failed"] or [])]
    lines += ["", "## Findings for other departments", "",
              f"- Pricing: {len(below)} of {c['packages']} packaged products are priced below "
              "the benchmark seller's observed p25 for their pod (benchmark pattern medians "
              "CA$18-22). This is one seller's shelf, not the market, and price is decided by "
              "`pricing.position`; it is recorded as evidence for the pricing inbox, not acted "
              "on here.",
              f"- Viable but BLOCKED on the hero image (company imagery work): "
              f"{', '.join(hero) or 'none'}.",
              "- Every other viable product is EXTERNAL_GATED: only the Etsy taxonomy read "
              "remains."]
    lines += ["", "## Not viable: Product Truth findings", ""]
    for p in r["products"]:
        if not p["viable"]:
            lines.append(f"- `{p['slug']}`: " + "; ".join(p["product_truth_reasons"])[:300])
    lines += ["", "These products may still have a drafted listing and a package, because "
              "`listing.seo` blocks product-identity findings only for Launch-0. Their "
              "readiness is not a sale decision: a product whose title promises what its CIR "
              "does not make must be re-engineered or renamed before it is merchandised.",
              "", "## Post-launch update loop", "",
              "Owner listing-level Stats export → `commerce.listing_outcomes.submit_export` → "
              "`produce` (ListingOutcome rows, carts in detail) → next `seo.cycle` "
              "(`seo.jobs.run_cycle` → `seo.packages.refresh`) writes a new package version. "
              "Its `learning` block carries impressions, visits, favourites, carts, orders and "
              "the funnel diagnosis. Search-term export → `POST /api/attribution/stats` → "
              "`seo.evidence` → per-tag `measured` evidence with EARNING/VANITY learning. "
              "Proven with FIXTURE data in `tests/test_w4_seo_packages.py`. No real listing is "
              "live, so every real package's learning is UNKNOWN.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
