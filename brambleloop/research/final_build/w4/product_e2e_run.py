"""W4-PRODUCT: the Launch-0 chain end to end, trend -> ... -> owner approval, on a scratch DB.

    PYTHONPATH=src python research/final_build/w4/product_e2e_run.py <dir> [--as-of 2026-10-11]

Starts where the company starts: a `radar.scan` of the real opportunity pool (trend evidence
discount, arbitrage steering, section-33 portfolio), then the REAL handlers in a SHADOW worker
on `<dir>/run.sqlite` -- radar.score -> cir.draft (retired aliases routed to Launch-0, PT-11)
-> cir.compile -> gate.certify -> listing.draft -> assets.build -> pricing.position ->
listing.seo -> launch.plan -> store.publish. Every outbound socket is refused, no Etsy/model
credential is present, nothing is spent. store.publish refuses in shadow; the owner-approval
boundary is read from `ops.publication_authority.evidence` and `release_gates.for_publish`.

A Launch-0 concept the 10-slot scan did not select is scored on demand (`radar.score` enqueued
directly, as the operator would) and reported as such, never as "selected".

Then `launch.readiness` runs once on the same DB, and per Launch-0 release this writes
`<dir>/e2e.json`: every link of the chain with the row or audit that evidences it, UNKNOWN
where nothing does.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(__file__).resolve().parent
UNKNOWN = "UNKNOWN"

CHAIN = ["radar.scan", "radar.score", "cir.draft", "cir.compile", "gate.certify",
         "listing.draft", "assets.build", "pricing.position", "listing.seo", "launch.plan",
         "store.publish"]


def _closed(*_a, **_k):
    raise OSError("network closed for the W4-PRODUCT e2e run")


def _audits(db, action, artifact=None):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        q = select(AuditLog).where(AuditLog.action == action)
        if artifact is not None:
            q = q.where(AuditLog.artifact == artifact)
        return [{"artifact": a.artifact, "detail": a.detail} for a in s.scalars(q)]


def main(argv: list[str]) -> dict:
    d = Path(argv[0]).resolve()
    as_of = argv[argv.index("--as-of") + 1] if "--as-of" in argv else "2026-10-11"
    d.mkdir(parents=True, exist_ok=True)
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(d / "art")
    for k in list(os.environ):
        if k.startswith(("ETSY", "ANTHROPIC_API", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
            os.environ.pop(k)
    socket.socket.connect = _closed            # type: ignore[assignment]
    socket.create_connection = _closed         # type: ignore[assignment]

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import (Job, JobStatus, Listing, OperatingReading,
                                         PatternVersion, Phase, Product)
    from brambleloop.intel import findings as F
    from brambleloop.ops import publication_authority as pa
    from brambleloop.products import launch0 as l0
    from brambleloop.publish import release_gates as rg
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline, release  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    t0 = time.time()
    db = Database(f"sqlite:///{d}/run.sqlite", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    mjs = OUT / "MJS_FINDINGS.json"
    if mjs.exists():
        payload = json.loads(mjs.read_text())
        with db.session() as s:
            s.add(OperatingReading(kind=F.KIND, period_key=str(payload.get("as_of")),
                                   payload=payload))
    q = JobQueue(db)
    q.enqueue("market_radar", "radar.scan", {"as_of": as_of, "target": 10},
              idempotency_key=f"scan:{as_of}", priority=0)
    worker = Worker(db, "w4-product-e2e", phase=Phase.SHADOW, job_types=["radar.scan"],
                    lease_seconds=1800)
    worker.run_once()
    scanned = _audits(db, "radar.scanned")
    with db.session() as s:
        scored = {j.inputs.get("slug") for j in s.scalars(
            select(Job).where(Job.job_type == "radar.score"))}
    # Concepts behind Launch-0 the scan did not select: scored on demand, reported as such.
    concepts = {}
    for rel in _releases(l0):
        concepts[rel["slug"]] = (pipeline.product_seed(rel["slug"]).slug
                                 if pipeline.product_seed(rel["slug"]) else None)
    on_demand = sorted({c for c in concepts.values() if c and c not in scored})
    for slug in on_demand:
        seed = pipeline._seed_for(slug)
        from brambleloop.radar.opportunity import score_concept
        q.enqueue("market_radar", "radar.score",
                  score_concept(seed, date.fromisoformat(as_of)).to_dict() | {"as_of": as_of},
                  idempotency_key=f"score:{slug}:{as_of}:on-demand", priority=0)
    # Only the Launch-0 concepts' scores go further: the rest of the selected wave is not the
    # subject of this run (and engineering every one would only cost time).
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "radar.score")):
            if (j.status == JobStatus.PENDING
                    and j.inputs.get("slug") not in set(concepts.values())):
                j.status = JobStatus.CANCELLED
                j.last_error = "W4-PRODUCT e2e: not a Launch-0 concept (out of this run's scope)"
    worker = Worker(db, "w4-product-e2e", phase=Phase.SHADOW, job_types=CHAIN[1:],
                    lease_seconds=1800)
    for _ in range(4000):
        if not worker.run_once():
            break
    # The daily readiness job, as production cadence would run it.
    q.enqueue("orchestrator", "launch.readiness", {}, idempotency_key="readiness:e2e", priority=0)
    Worker(db, "w4-product-e2e-ready", phase=Phase.SHADOW,
           job_types=["launch.readiness"], lease_seconds=1800).run_once()

    with db.session() as s:
        jobs: dict[str, int] = {}
        for j in s.scalars(select(Job)):
            k = f"{j.job_type}:{j.status.value}"
            jobs[k] = jobs.get(k, 0) + 1

    # Stale artefacts (#173): every derived artefact of a Launch-0 release against the
    # fingerprints its upstreams hold now; unproven is reported, never read as fresh.
    from brambleloop.ops import artefacts as prov

    with db.session() as s:
        verdicts = prov.check(s, current=prov.current_from_db(s),
                              expected=prov.expected_from_db(s))
    scope = l0.launch_scope_slugs()
    stale: dict[str, dict[str, int]] = {}
    stale_rows = []
    for v in verdicts:
        if v.product_slug not in scope:
            continue
        stale.setdefault(v.product_slug, {})
        stale[v.product_slug][v.state] = stale[v.product_slug].get(v.state, 0) + 1
        if v.state != "fresh":
            stale_rows.append(v.to_dict())

    rows = []
    for rel in _releases(l0):
        slug, version = rel["slug"], rel["version"]
        concept = concepts[slug]
        sc = [a["detail"] for a in _audits(db, "radar.scored", concept)] if concept else []
        ev = [a["detail"] for a in _audits(db, "radar.evidence_discount", concept)] if concept \
            else []
        routed = [a["detail"] for a in _audits(db, "cir.draft_routed", concept)] if concept \
            else []
        with db.session() as s:
            prod = s.scalar(select(Product).where(Product.slug == slug))
            pv = None if prod is None else s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == prod.id, PatternVersion.version == version))
            lst = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version)
                           .order_by(Listing.id.desc()).limit(1))
            cert = dict(pv.certificate or {}) if pv is not None else {}
            pv_row = None if pv is None else {
                "certified": bool(pv.certified), "release_hash": pv.release_hash or "",
                "certificate_granted": cert.get("granted"), "withheld": cert.get("withheld")}
            lst_row = None if lst is None else {
                "state": lst.state, "title_chars": len(lst.title or ""),
                "tags": len(lst.tags or []), "price_cad": lst.price_cad,
                "etsy_listing_id": lst.etsy_listing_id or ""}
        truth = l0.product_truth(l0.candidate(rel["candidate"]))
        release_hash = (pv_row or {}).get("release_hash", "")
        try:
            evid = pa.evidence(db, slug, version, release_hash)
            sections = {k: evid[k].get("state") for k in pa.GATED_SECTIONS + ("economics",)
                        if isinstance(evid.get(k), dict)}
        except Exception as exc:  # noqa: BLE001
            sections = {"state": UNKNOWN, "error": f"{type(exc).__name__}: {exc}"[:300]}
        try:
            g = rg.for_publish(db, slug=slug, version=version, store_root=str(d / "art"),
                               read_only=True)
            gates = {"blocks_release": g["blocks_release"], "reasons": g["reasons"]}
        except Exception as exc:  # noqa: BLE001
            gates = {"state": UNKNOWN, "error": f"{type(exc).__name__}: {exc}"[:300]}
        publish = [a["detail"] for a in _audits(db, "store.publish_refused", slug)][-1:] or \
            [a["detail"] for a in _audits(db, "store.publish_blocked", slug)][-1:]
        grants = _audits(db, pa.APPROVED, slug)
        rows.append({
            **rel,
            "trend": (ev[-1] if ev else UNKNOWN),
            "opportunity": {"concept": concept, "selected_by_scan": concept in scored,
                            "scored_on_demand": concept in on_demand,
                            "scored": (sc[-1] if sc else UNKNOWN)},
            "routed_alias": routed[-1] if routed else None,
            "product_row": prod is not None,
            "cir_release": pv_row or UNKNOWN,
            "product_truth": {"passes": truth["passes_gates"], "gates": truth["gates"]},
            "listing": lst_row or UNKNOWN,
            "publication_authority": sections,
            "release_gates": gates,
            "store_publish": publish[0] if publish else UNKNOWN,
            "owner_grants": len(grants),
            "artefacts": stale.get(slug, UNKNOWN),
        })

    with db.session() as s:
        rj = s.scalar(select(Job).where(Job.job_type == "launch.readiness"))
        readiness = [] if rj is None else [{"status": rj.status.value,
                                            "outputs": rj.outputs, "error": rj.last_error}]
    doc = {"dir": str(d), "as_of": as_of, "seconds": round(time.time() - t0, 1),
           "scan": scanned[-1]["detail"] if scanned else UNKNOWN,
           "on_demand": on_demand, "jobs": jobs, "releases": rows,
           "artefacts_not_fresh": stale_rows[:200],
           "readiness_audit": readiness[0] if readiness else UNKNOWN}
    (d / "e2e.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
    return {"wrote": str(d / "e2e.json"), "seconds": doc["seconds"], "jobs": jobs}


def _releases(l0):
    from brambleloop.launch import packet

    return packet.launch0_releases()


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), indent=1))
