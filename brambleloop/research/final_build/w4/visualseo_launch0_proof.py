"""W4-VISUALSEO: measure every remaining visual / creative / SEO blocker of the Launch-0 releases.

Runs the REAL release chain (gate.certify -> listing.draft -> assets.build -> pricing.position ->
listing.seo) in a shadow worker on a scratch SQLite database with every outbound socket refused,
for the Launch-0 release CIRs that pass Product Truth (market-basket-small/medium/large,
cloudline-baby-blanket, hexagon-coaster-set). Then it reads, per release, what the publish path
reads: the listing-set certificate, the stored search certificate (F-004), the search hero,
the eight-part creative parity verdict (#75) with the readiness gate classification
(`launch.readiness._EXTERNAL_PARITY`), the search-evidence gallery and the hero thumbnail.

No network, no Etsy write, no paid provider call, no spend. No Etsy taxonomy snapshot is loaded
(the company's real state), so category/attributes stay UNKNOWN -- never assumed.

Run: cd brambleloop && PYTHONPATH=src python research/final_build/w4/visualseo_launch0_proof.py [out.json]
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
TMP = tempfile.mkdtemp(prefix="w4_visualseo_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for k in list(os.environ):
    if k.startswith(("ETSY", "ANTHROPIC_API", "OPENAI", "REPLICATE", "FAL_", "GEMINI", "BFL")):
        os.environ.pop(k)


def _closed(*_a, **_k):
    raise OSError("network closed for the W4-VISUALSEO proof")


socket.socket.connect = _closed            # type: ignore[assignment]
socket.create_connection = _closed         # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Job, ListingSearchProfile,  # noqa: E402
                                     Phase)
from brambleloop.products import builder as flat  # noqa: E402
from brambleloop.products import vessels  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

CHAIN = ("gate.certify", "listing.draft", "assets.build", "pricing.position", "listing.seo")
BUILDERS = {
    "market-basket-small": lambda: vessels.build_basket("small"),
    "market-basket-medium": lambda: vessels.build_basket("medium"),
    "market-basket-large": lambda: vessels.build_basket("large"),
    "cloudline-baby-blanket": lambda: flat.for_slug("cloudline-baby-blanket"),
    "hexagon-coaster-set": vessels.build_hexagon_coaster,
}


def measure(db, slug: str, version: str) -> dict:
    from brambleloop.commerce import ranking_readiness, search_evidence
    from brambleloop.creative import blind_review
    from brambleloop.launch.readiness import _EXTERNAL_PARITY
    from brambleloop.publish import listing_asset, release_gates
    from brambleloop.visual import parity
    from brambleloop.visual.gallery import gates_now

    set_verdict = release_gates.listing_set(db, slug=slug, version=version, issue=False)
    frames = listing_asset.frames_for(db, slug=slug)
    review = blind_review.current_review(db, slug=slug)
    verdict = parity.assess(frames, benchmark_quality=review)
    gates = gates_now(db, keys=("image_vision", "benchmark_observation"))
    dims = {}
    for d in parity.DIMENSIONS:
        r = verdict["dimensions"][d]
        closed = [g for g in _EXTERNAL_PARITY.get(d, ()) if not gates.get(g)]
        dims[d] = {"verdict": r["verdict"], "why": r["why"][:300],
                   "waits_on_closed_gates": closed if r["verdict"] == parity.UNJUDGED else []}
    with db.session() as s:
        prof = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug, ListingSearchProfile.version == version))
        cert = dict(prof.certificate or {}) if prof is not None else {}
        hero_audit = s.scalars(select(AuditLog).where(
            AuditLog.action == "listing.search_hero_judged", AuditLog.artifact == f"{slug}@{version}")
            .order_by(AuditLog.id.desc())).first()
    checks = {k: {"ok": v.get("ok"), "why": str(v.get("why") or "")[:240]}
              for k, v in (cert.get("checks") or {}).items() if isinstance(v, dict)}
    gal = search_evidence.gallery(db, slug, version)
    presentation = [parity.presentation_quality(f) for f in frames
                    if f.get("kind") == parity.DISCLOSED_RENDER]
    return {
        "version": version,
        "frames": len(frames),
        "frame_kinds": sorted({str(f.get("kind")) for f in frames}),
        "listing_set": {"blocks_release": set_verdict.get("blocks_release"),
                        "reasons": (set_verdict.get("reasons") or [])[:6],
                        "certificate_valid": (set_verdict.get("certificate") or {}).get("valid")},
        "search_certificate": {"verdict": cert.get("verdict"), "failed": cert.get("failed"),
                               "pending": cert.get("pending"), "checks": checks,
                               "standing": ranking_readiness.search_certificate(db, slug, version)},
        "search_hero_audit": (hero_audit.detail if hero_audit is not None else None),
        "parity": {"verdict": verdict["verdict"], "failed": verdict["failed"],
                   "unjudged": verdict["unjudged"], "dimensions": dims},
        "presentation_quality": [{k: p[k] for k in ("verdict", "failed", "unknown")}
                                 for p in presentation],
        "gallery": {k: gal.get(k) for k in ("status", "covered", "missing", "why")},
        "gates": gates,
    }


def main(out_path: str | None) -> dict:
    t0 = time.time()
    db = Database(f"sqlite:///{TMP}/proof.sqlite", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    versions = {}
    for slug, make in BUILDERS.items():
        cir = make()
        assert cir.slug == slug, (cir.slug, slug)
        versions[slug] = cir.version
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key=f"cert-{slug}", priority=0)
    worker = Worker(db, "w4-visualseo", phase=Phase.SHADOW, job_types=list(CHAIN),
                    lease_seconds=1800)
    for _ in range(300):
        if not worker.run_once():
            break
    with db.session() as s:
        jobs = [{"type": j.job_type, "status": j.status.value,
                 "slug": (j.inputs or {}).get("slug") or ((j.inputs or {}).get("cir") or {})
                 .get("slug"), "error": (j.last_error or "")[-200:]}
                for j in s.scalars(select(Job).where(Job.job_type.in_(CHAIN)))]
        seo_blocked = {a.artifact: list((a.detail or {}).get("blocking") or [])[:6]
                       for a in s.scalars(select(AuditLog).where(
                           AuditLog.action == "listing.seo_blocked"))}
    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "generated_by": "research/final_build/w4/visualseo_launch0_proof.py (real chain, "
                              "shadow, scratch SQLite, sockets refused, no taxonomy snapshot)",
              "chain_not_done": [j for j in jobs if j["status"] != "done"],
              "listing_seo_blocked": seo_blocked, "products": {}}
    for slug, version in versions.items():
        report["products"][slug] = measure(db, slug, version)
    from brambleloop.commerce import search_evidence
    from brambleloop.seo import packages as seo_packages

    gate = search_evidence.supremacy_gate(db)
    report["supremacy_gate"] = {k: gate[k] for k in ("cleared", "failed", "unmeasured", "why")}
    for row in gate["listings"]:
        if row["slug"] in report["products"]:
            report["products"][row["slug"]]["search_rungs"] = row["rungs"]
    for slug, version in versions.items():
        pkg = seo_packages.current(db, slug, version) or {}
        report["products"][slug]["search_package"] = {
            "readiness": pkg.get("readiness"),
            "title": (pkg.get("title") or {}).get("text") if isinstance(pkg.get("title"), dict)
            else pkg.get("title"),
            "tag_basis": (pkg.get("tags") or {}).get("basis_counts")}
    report["seconds"] = round(time.time() - t0, 1)
    text = json.dumps(report, indent=1, default=str)
    if out_path:
        Path(out_path).write_text(text + "\n")
    print(text)
    return report


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else None)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
