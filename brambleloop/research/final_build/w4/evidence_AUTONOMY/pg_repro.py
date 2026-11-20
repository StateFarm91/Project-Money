"""Reproduce the production ops.sentinel dead letter on a real Postgres (VARCHAR(200))."""
import sys
from sqlalchemy import select, text
from brambleloop.core.db import Database
from brambleloop.core.models import Job
from brambleloop.ops import artefacts as A, rebuild_graph as G
from brambleloop.queue.durable import JobQueue

db = Database(sys.argv[1]); db.create_all()
with db.session() as s:
    s.execute(text("TRUNCATE jobs, artefact_provenance RESTART IDENTITY CASCADE"))
slugs = ["autumn-oak-mosaic-throw", "cloudline-baby-blanket", "harvest-table-runner",
         "hexie-coaster-set", "market-basket-trio", "mosaic-placemat-pair",
         "nordic-forest-mosaic-throw", "nordic-star-ornaments", "pet-snuggle-mat",
         "pressed-flower-motifs", "pumpkin-cluster-set", "spooky-garland",
         "valentine-heart-garland", "winter-village-graphghan"]
with db.session() as s:
    for slug in slugs:
        A.record(s, artefact_class="pdf", artefact_key=f"{slug}.pdf", product_slug=slug,
                 inputs={"chain:release": A.fingerprint("v1"), f"cir:{slug}": A.fingerprint(slug)})
changed = {"chain:release": A.fingerprint("v2")}
changed.update({f"cir:{s_}": A.fingerprint(s_ + "2") for s_ in slugs})
try:
    with db.session() as s:
        r = G.enqueue(s, JobQueue(db), changed=changed, per="product", reason="chain moved")
        r2 = G.enqueue(s, JobQueue(db), changed=changed, per="product", reason="chain moved")
    with db.session() as s:
        keys = list(s.scalars(select(Job.idempotency_key)))
    print("OK enqueued", len(r["enqueued"]), "artefacts; re-run already_queued",
          len(r2["already_queued"]), "; jobs", len(keys), "; max key len", max(map(len, keys)))
except Exception as e:
    print("FAILED", type(e).__name__, str(e).splitlines()[0][:160])
