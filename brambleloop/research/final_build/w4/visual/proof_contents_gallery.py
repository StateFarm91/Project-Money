"""W4-VISUAL2 runtime proof: the certified gallery INCLUDING the CONTENTS frame (pages of the
release's assets.built PDF) through the real gate.certify + assets.build handlers,
release_gates.listing_set, the upload path (etsy_ops.certified_images), the first-customer
imagery check and commerce.search_evidence.gallery. Sockets refused; shadow; no spend.
Usage: proof_contents_gallery.py slug[,slug...] [out.json]"""
import json, os, sys, tempfile, socket, time
tmp = tempfile.mkdtemp(prefix="w4v_proof_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(tmp, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
def _refuse(*a, **k): raise OSError("network refused")
socket.socket.connect = _refuse; socket.create_connection = _refuse
from sqlalchemy import select
from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import Job, JobStatus, Listing, Phase
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline, release  # noqa
from brambleloop.runtime.worker import Worker
from brambleloop.publish import disclosed_listing, release_gates, listing_asset
from brambleloop.runtime import etsy_ops

out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "products": {}}
db = Database(f"sqlite:///{tmp}/proof.sqlite"); db.create_all(); Registry(db).seed_defaults()
slugs = sys.argv[1].split(",")
for slug in slugs:
    cir = pipeline._engineered_cir(slug)
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                         idempotency_key=f"cert-{slug}", priority=0)
    Worker(db, "c", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
    job = JobQueue(db).enqueue("publishing", "assets.build", {"slug": slug, "version": cir.version,
                               "release": "", "rebuild": "disclosed"}, idempotency_key=f"d-{slug}", priority=0)
    Worker(db, "b", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()
    with db.session() as s:
        st = s.get(Job, job.id).status.value
        s.add(Listing(product_slug=slug, version=cir.version, title=cir.title,
                      description="A crochet pattern.\n\n" + disclosed_listing.COPY_DISCLOSURE,
                      price_cad=9.5, state="draft"))
    rec = disclosed_listing.last_asset(db, slug=slug) or {}
    v = release_gates.listing_set(db, slug=slug, version=cir.version, issue=True) \
        if rec else {}
    served = etsy_ops.certified_images(db, slug, cir.version) if rec else {}
    from brambleloop.gates import first_customer
    from brambleloop.commerce import search_evidence
    fc = first_customer.disclosed_imagery(db, slug, cir.version) if rec else None
    gal = search_evidence.gallery(db, slug, cir.version)
    cert_frames = []
    with db.session() as s:
        from brambleloop.core.models import ListingSetCertificateRecord
        r = s.scalars(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.state == "valid")).all()
        if r:
            cert_frames = [{k: f.get(k) for k in ("position", "job", "medium", "honesty_label",
                                                   "sha256", "alt_text")}
                           for f in (r[-1].certificate or {}).get("frames") or []]
    out["products"][slug] = {
        "version": cir.version, "assets_build": st,
        "disclosed_made": bool(rec), "usable": rec.get("usable_as_listing_asset"),
        "launch_blocked": (rec.get("launch_blocked") or [])[:5],
        "frames": [{"view": f["view"], "job": (f.get("disclosed_render") or {}).get("job"),
                    "sha256": f["image"]["sha256"], "structural_truth": f["structural_truth"]["status"]}
                   for f in rec.get("frames") or []],
        "listing_set": {"blocks_release": v.get("blocks_release"), "reasons": (v.get("reasons") or [])[:4],
                        "supplements": v.get("supplements"),
                        "certificate_valid": (v.get("certificate") or {}).get("valid")},
        "upload_path": {"images": len(served.get("images") or []), "problems": (served.get("problems") or [])[:3],
                        "jobs": [o.get("job") for o in served.get("order") or []]},
        "first_customer_imagery": fc,
        "search_evidence_gallery": {k: gal.get(k) for k in ("status", "covered", "missing",
                                                             "sizes", "colours", "why")},
        "certificate_frames": cert_frames,
    }
print(json.dumps(out, indent=1))
if len(sys.argv) > 2:
    open(sys.argv[2], "w").write(json.dumps(out, indent=1) + "\n")
import shutil; shutil.rmtree(tmp, ignore_errors=True)
