"""W4-PIPE3 runtime proof: the non-viable catalogue products through the REAL release chain.

For each product this lane owns (SEO_PACKAGES.json marked it not viable), build its current
release, run gate.certify -> listing.draft -> assets.build -> pricing.position -> listing.seo
in a shadow worker on a scratch SQLite database (every outbound socket refused, no Etsy
taxonomy snapshot -- the company's real state), then read back:

* static Product Truth now (`products.inventory.static_truth`: compile, certify, title,
  assembly and fabric promises), and
* the publish-time name truth of the drafted listing (`publish.eligibility.name_truth` over the
  CIR *and* the listing's title and tags), which is what `product_publication` refuses on.

Writes evidence_PIPE3/pipe3_run.json. No network, no Etsy write, no spend.

Run: cd brambleloop && PYTHONPATH=src python research/final_build/w4/pipe3_run.py [slug ...]
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
OUT = Path(__file__).resolve().parent / "evidence_PIPE3"
TMP = tempfile.mkdtemp(prefix="w4_pipe3_run_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(TMP, "artifacts")
for k in list(os.environ):
    if k.startswith(("ETSY", "ANTHROPIC_API", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(k)


def _closed(*_a, **_k):
    raise OSError("network closed for the W4-PIPE3 run")


socket.socket.connect = _closed            # type: ignore[assignment]
socket.create_connection = _closed         # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, Listing, Phase  # noqa: E402
from brambleloop.products import builder as flat  # noqa: E402
from brambleloop.products import inventory, nordic_forest, texture  # noqa: E402
from brambleloop.publish.eligibility import name_truth  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

CHAIN = ("gate.certify", "listing.draft", "assets.build", "pricing.position", "listing.seo")

# The 14 products SEO_PACKAGES.json (2026-10-07T02:05) marked not viable, minus the two
# W4-PIPE promoted into Launch-0 (nordic-star-ornaments, winter-village-graphghan: PIPE's).
OWNED = {
    "autumn-oak-mosaic-throw": lambda: flat.for_slug("autumn-oak-mosaic-throw"),
    "cottage-wall-hanging": lambda: flat.for_slug("cottage-wall-hanging"),
    "mosaic-placemat-pair": lambda: flat.for_slug("mosaic-placemat-pair"),
    "pressed-flower-motifs": lambda: flat.for_slug("pressed-flower-motifs"),
    "spooky-garland": lambda: flat.for_slug("spooky-garland"),
    "valentine-heart-garland": lambda: flat.for_slug("valentine-heart-garland"),
    "nordic-forest-mosaic-throw-baby": lambda: nordic_forest.build("baby"),
    "nordic-forest-mosaic-throw-throw": lambda: nordic_forest.build("throw"),
    "nordic-forest-mosaic-throw-large": lambda: nordic_forest.build("large"),
    "chunky-ribbed-scarf": texture.build_ribbed_scarf,
    "bobble-floor-pillow": texture.build_bobble_pillow,
    "heirloom-cable-blanket": texture.build_cable_throw,
}


def _static(cir) -> dict:
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.gates.certificate import certify
    from brambleloop.products import launch0 as l0

    result = compile_cir(cir)
    cert = certify(cir)
    twin = build_twin(cir, result) if result.ok else None
    return {
        "title": cir.title, "version": cir.version, "risk_class": cir.risk_class,
        "compiles": result.ok, "certified": bool(cert.granted),
        "certificate_errors": [f"{f.code}: {f.message}"[:240] for f in cert.errors],
        "title_promise": l0.title_promise(cir)["backed"],
        "assembly_promise": l0.assembly_promise(cir)["backed"],
        "fabric_truth": (l0.fabric_truth(cir, twin)["backed"] if twin else None),
        "name_truth_cir": name_truth(cir),
    }


def main(only: list[str]) -> dict:
    t0 = time.time()
    db = Database(f"sqlite:///{TMP}/run.sqlite", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    chosen = {k: v for k, v in OWNED.items() if not only or k in only}
    cirs = {}
    for key, make in sorted(chosen.items()):
        cir = make()
        cirs[key] = cir
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key=f"cert-{key}", priority=0)
    worker = Worker(db, "w4-pipe3", phase=Phase.SHADOW, job_types=list(CHAIN),
                    lease_seconds=1800)
    for _ in range(400):
        if not worker.run_once():
            break
    rows = {}
    with db.session() as s:
        listings = {r.product_slug: {"title": r.title, "tags": list(r.tags or []),
                                     "version": r.version}
                    for r in s.scalars(select(Listing).order_by(Listing.id))}
        blocked = {a.artifact.split("@")[0]: list((a.detail or {}).get("blocking") or [])[:6]
                   for a in s.scalars(select(AuditLog).where(
                       AuditLog.action == "listing.seo_blocked"))}
        jobs = [(j.job_type, j.status.value,
                 (j.inputs or {}).get("slug") or ((j.inputs or {}).get("cir") or {}).get("slug"),
                 (j.last_error or "")[-200:]) for j in s.scalars(select(Job))]
    for key, cir in sorted(cirs.items()):
        row = _static(cir)
        listing = listings.get(cir.slug)
        row["listing"] = listing
        row["name_truth_listing"] = name_truth(cir, listing) if listing else None
        row["seo_blocked"] = blocked.get(cir.slug, [])
        row["chain_jobs"] = sorted({f"{t}:{st}" for t, st, sl, _ in jobs if sl == cir.slug})
        row["product_truth_ok"] = bool(row["compiles"] and row["certified"]
                                       and row["title_promise"] and row["assembly_promise"]
                                       and row["fabric_truth"] and not row["name_truth_cir"])
        row["listing_truth_ok"] = (None if listing is None
                                   else not row["name_truth_listing"])
        rows[key] = row
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generated_by": "research/final_build/w4/pipe3_run.py (real release chain, shadow "
                            "worker, scratch SQLite, network closed, no taxonomy snapshot)",
            "seconds": round(time.time() - t0, 1), "products": rows}


if __name__ == "__main__":
    report = main(sys.argv[1:])
    OUT.mkdir(exist_ok=True)
    name = "pipe3_run.json" if len(sys.argv) == 1 else "pipe3_run_partial.json"
    (OUT / name).write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n")
    for k, r in report["products"].items():
        print(("OK  " if r["product_truth_ok"] and r["listing_truth_ok"] else "NO  ") + k,
              r["version"], r["title"], "| cert", r["certified"], "| listing",
              (r["listing"] or {}).get("title"), "| nt", r["name_truth_listing"],
              "| errs", [e[:60] for e in r["certificate_errors"]])
    print("seconds", report["seconds"])
