"""W4-PIPE: a fresh shadow release-chain run for the product inventory.

    PYTHONPATH=src python research/final_build/w4/pipe_chain_run.py <dir> [slug ...]

Builds every engineered product (`products.inventory.universe`, retired duplicates skipped; or
just the named slugs) from its registered design (`runtime.pipeline._engineered_cir`) and runs
the REAL release chain -- gate.certify -> listing.draft -> assets.build -> pricing.position ->
listing.seo -> launch.plan (window decision, #297 pivot, mobile QA) -> store.publish -- in a SHADOW worker on `<dir>/run.sqlite`, artifacts in
`<dir>/art`, every outbound socket refused. store.publish refuses in shadow; its verdict is
what the inventory reads. No network, no Etsy write, no spend.

Run it again on the same <dir> with further slugs to add them (bounded batches): the DB and
the artifact store are reused, each product enqueued once. `--drain` works only the queue.

Then: product_inventory_run.py --chain-db <dir>/run.sqlite
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(__file__).resolve().parent


def _closed(*_a, **_k):
    raise OSError("network closed for the W4-PIPE chain run")


def main(argv: list[str]) -> dict:
    d = Path(argv[0]).resolve()
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
    from brambleloop.core.models import Job, OperatingReading, Phase
    from brambleloop.intel import findings as F
    from brambleloop.products import inventory, launch0
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline, release  # noqa: F401 - registers handlers
    from brambleloop.runtime.pipeline import _engineered_cir
    from brambleloop.runtime.worker import Worker

    t0 = time.time()
    drain = argv[1:] == ["--drain"]          # only work what is already queued
    slugs = [] if drain else (argv[1:] or [s for s in inventory.universe()
                                           if s not in launch0.LEGACY_DUPLICATES])
    fresh = not (d / "run.sqlite").exists()
    db = Database(f"sqlite:///{d}/run.sqlite", scratch=True)
    db.create_all()
    if fresh:
        Registry(db).seed_defaults()
    mjs = OUT / "MJS_FINDINGS.json"
    if fresh and mjs.exists():
        payload = json.loads(mjs.read_text())
        with db.session() as s:
            s.add(OperatingReading(kind=F.KIND, period_key=str(payload.get("as_of")),
                                   payload=payload))
    built = {}
    for slug in slugs:
        try:
            cir = _engineered_cir(slug)
        except Exception as exc:  # noqa: BLE001 - an unbuildable slug is reported
            built[slug] = f"unbuildable: {type(exc).__name__}: {exc}"[:200]
            continue
        if cir is None:
            built[slug] = "no design"
            continue
        built[slug] = cir.version
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key=f"cert-{slug}", priority=0)
    chain = ["gate.certify", "listing.draft", "assets.build", "pricing.position",
             "listing.seo", "launch.plan", "store.publish"]
    worker = Worker(db, "w4-pipe-chain", phase=Phase.SHADOW, job_types=chain,
                    lease_seconds=1800)
    for _ in range(2000):
        if not worker.run_once():
            break
    with db.session() as s:
        jobs: dict[str, int] = {}
        for j in s.scalars(select(Job)):
            k = f"{j.job_type}:{j.status.value}"
            jobs[k] = jobs.get(k, 0) + 1
    prev = d / "chain_run.json"
    if prev.exists():
        built = {**json.loads(prev.read_text()).get("built", {}), **built}
    res = {"dir": str(d), "built": built, "jobs": jobs, "seconds": round(time.time() - t0, 1)}
    (d / "chain_run.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), indent=1))
