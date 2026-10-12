"""Real-chain check: placemat listing forced to 9.50, then chain.rebuild -> pricing -> listing.seo."""
import json, os, socket, sys
from pathlib import Path
d = Path(sys.argv[1]).resolve()
sys.path.insert(0, "src"); sys.path.insert(0, "research/final_build/w4")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(d / "art")
def c(*a, **k): raise OSError("closed")
socket.socket.connect = c; socket.create_connection = c
import pipe_chain_run
print(json.dumps(pipe_chain_run.main([str(d), "mosaic-placemat-pair"])["jobs"]))
from sqlalchemy import select
from brambleloop.core.db import Database
from brambleloop.core.models import Listing, Phase, Job
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker
db = Database(f"sqlite:///{d}/run.sqlite", scratch=True)
with db.session() as s:
    row = s.scalar(select(Listing).where(Listing.product_slug == "mosaic-placemat-pair"))
    print("listing after chain:", row.version, row.price_cad, row.state)
    row.price_cad = 9.50                       # reproduce production's pre-CAP-1 draft price
JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="reprice-check")
w = Worker(db, "reprice", phase=Phase.SHADOW, job_types=["chain.rebuild", "pricing.position",
           "listing.seo"], lease_seconds=1800)
for _ in range(50):
    if not w.run_once():
        break
with db.session() as s:
    row = s.scalar(select(Listing).where(Listing.product_slug == "mosaic-placemat-pair"))
    rb = s.scalar(select(Job).where(Job.idempotency_key == "reprice-check"))
    out = {"repriced": (rb.outputs or {}).get("repriced"), "listing_price_after": row.price_cad,
           "listing_state": row.state, "etsy_listing_id": row.etsy_listing_id or ""}
print(json.dumps(out))
(d / "reprice_result.json").write_text(json.dumps(out, indent=1))
