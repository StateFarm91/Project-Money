"""eng/evidence-perf: a production-sized database for the readback-evidence timing test.

Production (2026-11) carries about 600 provenance rows, 200 incidents, 16 products and
thousands of jobs and audit rows; `GET /api/readback/evidence` took 45-91 s on it. This
seeds a database of that shape (deterministically: same seed, same rows) so the timing
bound and the identical-output check run against the real scale, not a toy one.

Nothing seeded here is private text the evidence may echo: the PRIVATE marker strings are
planted in the fields the evidence must never emit (inputs, outputs, error text, incident
summaries), so a caller can also assert none of them leaks.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

PRIVATE_MARK = "PRIVATE-SEED-TEXT-7f3a"

CLASSES = ("twin", "geometry_proof", "reverse_result", "certificate", "pdf", "chart",
           "visual_truth", "marketing_asset", "listing_copy")


def seed(db, *, now: datetime, products: int = 16, artefacts: int = 600,
         incidents: int = 200, jobs: int = 6000, audits: int = 6000,
         parked: int = 40, cir_kb: int = 120, cert_kb: int = 40,
         old_versions: int = 5, rng_seed: int = 380) -> dict:
    from brambleloop.core.models import (
        ArtefactProvenance, AuditLog, ContentPiece, Incident, Job, JobStatus, Listing,
        ListingAsset, OperatingReading, PatternVersion, PhysicalPhoto, Product)
    from brambleloop.ops import artefacts as provenance
    from brambleloop.ops.incident_lifecycle import SYSTEMIC_SIGNATURE
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun, \
        ensure_tables

    ensure_tables(db)
    rng = random.Random(rng_seed)
    classes = [c for c in CLASSES if c in provenance.ARTEFACT_CLASSES]
    slugs = [f"seed-product-{i:02d}" for i in range(products)]
    versions = ("1.0.0", "1.1.0", "1.2.0")
    pad = "x" * 1000
    with db.session() as s:
        pids = {}
        for slug in slugs:
            p = Product(slug=slug, title=f"{slug} title")
            s.add(p)
            s.flush()
            pids[slug] = p.id
            history = [f"0.{n}.0" for n in range(old_versions)] + list(versions)
            for k, v in enumerate(history):
                k = k - old_versions  # the three current-era releases keep k = 0, 1, 2
                cir = {"slug": slug, "version": v,
                       "rows": [{"n": r, "stitches": pad[: 40 + r % 50], "private": None}
                                for r in range(cir_kb * 10)]}
                s.add(PatternVersion(product_id=p.id, version=v, cir_json=cir,
                                     release_hash=f"{k % 100:02d}{i_hash(slug)}" * 4,
                                     certified=k < 2 or rng.random() < 0.5,
                                     certificate={"gates": [{"gate": g, "detail": pad[:100]}
                                                            for g in range(cert_kb * 8)]}))
            s.add(Listing(product_slug=slug, version="1.1.0", title="t",
                          description="d", state="draft"))
            for pos in range(12):
                s.add(ListingAsset(product_slug=slug, version="1.1.0", position=pos,
                                   asset_class="image", role="gallery"))
            for c in range(10):
                s.add(ContentPiece(product_slug=slug, channel="pinterest",
                                   title=f"{slug} piece {c}", body=PRIVATE_MARK,
                                   state="superseded" if c % 3 == 0 else "draft"))
            for v in versions:
                s.add(OperatingReading(kind="listing.package", period_key=f"{slug}@{v}",
                                       payload={"release_hash": f"01{i_hash(slug)}" * 4,
                                                "blockers": [
                                                    {"source": "pricing", "why":
                                                     "PricingNotPass " + PRIVATE_MARK},
                                                    {"source": "images", "image": True,
                                                     "why": "no hero"}]}))
            for ph in range(3):
                s.add(PhysicalPhoto(product_slug=slug, sha256=hashlib_hex(f"{slug}{ph}")))
        s.flush()
        for k in range(artefacts):
            slug = slugs[k % products]
            cls = classes[k % len(classes)]
            v = versions[k % 3]
            key = f"{slug}@{v}#{k}" if cls == "visual_truth" else f"{slug}@{v}:{k}"
            inputs = {f"cir:{slug}": f"{rng.getrandbits(64):016x}",
                      f"release:{slug}": f"{rng.getrandbits(64):016x}",
                      "chain:release": f"{rng.getrandbits(64):016x}"}
            if cls == "visual_truth":
                inputs[f"asset:image_candidate_{k}"] = "ab" * 32
            s.add(ArtefactProvenance(artefact_class=cls, artefact_key=key, product_slug=slug,
                                     inputs=inputs, created_by="seed", source="recorded"))
        for k in range(incidents):
            slug = slugs[k % products]
            kind = k % 10
            if kind < 6:
                cls = classes[k % len(classes)]
                sig = f"{provenance.SENTINEL_SIGNATURE}:{cls}:{slug}@{versions[k % 3]}:{k}"
            elif kind < 8:
                sig = f"rebuild-incomplete:{slug}"
            elif kind == 8:
                sig = SYSTEMIC_SIGNATURE if k < 20 else f"publication-halt:{slug}"
            else:
                sig = f"provider-error:{k}"
            s.add(Incident(at=now - timedelta(hours=k % 300), product_slug=slug,
                           signature=sig, summary=PRIVATE_MARK, report_count=k % 7,
                           halts_publication=kind < 8, resolved=k % 5 == 0,
                           detail={"note": PRIVATE_MARK}))
        job_types = ("listing.package", "visual.image_production", "chain.rebuild",
                     "improve.weekly", "laura.executive_tick", "cir.draft", "gate.certify",
                     "radar.scan", "listing.draft", "learn.scan", "ops.health",
                     "ops.sentinel", "intel.scan_evidence", "etsy.shop_snapshot")
        statuses = (JobStatus.DONE, JobStatus.DONE, JobStatus.DONE, JobStatus.DEAD,
                    JobStatus.PENDING, JobStatus.FAILED)
        for k in range(jobs):
            jt = job_types[k % len(job_types)]
            st = statuses[k % len(statuses)]
            at = now - timedelta(minutes=17 * (k % 1200))
            s.add(Job(agent="seed", job_type=jt, status=st,
                      inputs={"product_slug": slugs[k % products], "note": PRIVATE_MARK},
                      outputs={"degraded": k % 11 == 0, "work": k % 2, "note": PRIVATE_MARK},
                      last_error=(f"RuntimeError: {PRIVATE_MARK}" if st == JobStatus.DEAD
                                  else None),
                      created_at=at, finished_at=at + timedelta(minutes=3)))
        actions = ("ops.truth.sweep", "ops.sentinel", "chain.rebuild_completed",
                   "chain.rebuild_unbound", "chain.rebuild_refused", "gate.certified",
                   "gate.halted", "listing.package_release_failed", "job.done",
                   "ops.rebuild_propagated", "paid_call.replayed", "job.enqueued")
        for k in range(audits):
            act = actions[k % len(actions)]
            detail = {"note": PRIVATE_MARK, "why": "x"}
            if act == "ops.truth.sweep":
                detail = {"systemic": {"systemic": False}}
            elif act == "ops.sentinel":
                detail = {"stale": 3, "checked": artefacts}
            elif act == "chain.rebuild_completed":
                detail = {"already_fresh": k % 2 == 0}
            s.add(AuditLog(at=now - timedelta(minutes=7 * (k % 2000)), actor="seed",
                           action=act, artifact=f"{slugs[k % products]}@1.1.0",
                           detail=detail))
        for k in range(parked):
            slug = slugs[k % products]
            s.add(ImageProductionRun(run_key=f"seed-run-{k}", slug=slug, version="1.1.0",
                                     release=f"01{i_hash(slug)}" * 4,
                                     status=IP.SALE_WAITING,
                                     stages={"note": PRIVATE_MARK}))
        for k in range(artefacts):
            s.add(ImageCandidate(sha256=f"{k:064x}", method="flux", provenance_kind="generated",
                                 slug=slugs[k % products], prompt=PRIVATE_MARK))
    return {"slugs": slugs}


def i_hash(slug: str) -> str:
    import hashlib

    return hashlib.sha256(slug.encode()).hexdigest()[:6]


def hashlib_hex(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()
