"""W4-FIRSTSALE: first-sale rehearsal of the eight Launch-0 products, locally, in SHADOW.

    PYTHONPATH=src python research/final_build/w4/firstsale_run.py <dir> [--chain]

`--chain` first runs the REAL release chain for every release (`pipe_chain_run.main`, as
W4-PRODREADY did): SHADOW worker, fresh SQLite, every outbound socket refused, no credential,
no model call, no spend; `store.publish` refuses in SHADOW. Then, on that database:

1. durable delivery (B5): every certified PDF is held in the database by sha256;
2. the redeploy: the artifact directory is moved away, so nothing is on disk;
3. purchase -> download (shadow): a simulated Etsy-shaped paid receipt per release, its
   delivery links, the bytes fetched, sha256 compared with the certified PDF;
4. re-render fallback: on a COPY of the database with every held PDF row deleted, the PDFs are
   re-rendered from the certified CIR and accepted only when byte-identical;
5. the rollback drill's `deliverables_restorable` per release;
6. image-upload readiness (B4): the exact uploadListingImage requests for each certified set;
7. the first-sale view (`launch.first_sale.build`).

Writes `<dir>/firstsale.json` and `<dir>/first_sale.md`. Nothing here calls Etsy.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _closed(*_a, **_k):
    raise OSError("network refused by firstsale_run (no Etsy, no provider)")


def releases() -> list[tuple[str, str, str]]:
    from brambleloop.products import launch0 as l0

    out = []
    for cand in l0.LAUNCH0_SLUGS:
        for v in l0.candidate(cand).variants:
            cir = l0.cir_for(v.build)
            out.append((cand, cir.slug, cir.version))
    return out


def main(argv: list[str]) -> dict:
    d = Path(argv[0]).resolve()
    d.mkdir(parents=True, exist_ok=True)
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(d / "art")
    os.environ["BRAMBLELOOP_PHASE"] = "shadow"
    for k in list(os.environ):
        if k.startswith(("ETSY", "ANTHROPIC_API", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
            os.environ.pop(k)
    socket.socket.connect = _closed            # type: ignore[assignment]
    socket.create_connection = _closed         # type: ignore[assignment]
    t0 = time.time()
    rels = releases()
    chain = None
    if "--chain" in argv:
        import pipe_chain_run

        chain = pipe_chain_run.main([str(d)] + [slug for _, slug, _ in rels])

    from brambleloop.commerce import deliverables as D
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.core.db import Database
    from brambleloop.core.models import DurableArtifact
    from brambleloop.integrations import etsy_image_readiness as R
    from brambleloop.launch import first_sale, rollback
    from brambleloop.launch.packet import _stored_release

    db = Database(f"sqlite:///{d}/run.sqlite", scratch=True)
    db.create_all()
    doc: dict = {"chain_seconds": (chain or {}).get("seconds"), "releases": {}}

    # 1. held before the redeploy
    for cand, slug, ver in rels:
        doc["releases"][f"{slug}@{ver}"] = {"candidate": cand,
                                            "durable_before": D.durable_state(db, slug, ver)}
    # 2. the redeploy
    art = d / "art"
    moved = d / "art.before-redeploy"
    if moved.exists():
        shutil.rmtree(moved)
    if art.exists():
        art.rename(moved)
    store = ArtifactStore(art)

    # 3. purchase -> download, from the database alone
    listing_ids = {}
    for i, (cand, slug, ver) in enumerate(rels, start=1):
        lid = str(880000 + i)                  # a fixture Etsy listing id, never sent anywhere
        listing_ids[lid] = (slug, ver)
        receipt = {"receipt_id": 770000 + i, "status": "Paid", "is_paid": True,
                   "transactions": [{"transaction_id": 660000 + i, "listing_id": int(lid),
                                     "is_digital": True}]}
        out = D.rehearse_purchase(db, receipt, {lid: (slug, ver)}, store=store,
                                  render=lambda *_a: (_ for _ in ()).throw(
                                      AssertionError("re-render used where bytes were held")))
        doc["releases"][f"{slug}@{ver}"]["purchase"] = out

    # 4. the re-render fallback, on a copy with every held PDF row deleted
    copy = d / "rerender.sqlite"
    shutil.copyfile(d / "run.sqlite", copy)
    db2 = Database(f"sqlite:///{copy}", scratch=True)
    for cand, slug, ver in rels:
        pdfs = D.certified(db2, slug, ver)["pdfs"]
        with db2.session() as s:
            for sha in pdfs.values():
                row = s.get(DurableArtifact, sha)
                if row is not None:
                    s.delete(row)
        before = D.durable_state(db2, slug, ver)
        sec = D.secure_release(db2, slug, ver, store=ArtifactStore(d / "art-empty"))
        doc["releases"][f"{slug}@{ver}"]["rerender"] = {
            "before": before["state"], "after": D.durable_state(db2, slug, ver)["state"],
            "pdfs": sec["pdfs"]}

    # 5. the rollback drill
    for cand, slug, ver in rels:
        drill = rollback.rehearse(db, slug=slug, version=ver, store=store)
        doc["releases"][f"{slug}@{ver}"]["deliverables_restorable"] = next(
            s for s in drill["steps"] if s["step"] == "deliverables_restorable")

    # 6. image upload readiness on the bytes store.publish would upload
    for cand, slug, ver in rels:
        rel = (_stored_release(db, slug, ver) or {}).get("release") or ""
        got = R.for_release(db, slug, ver, release=rel, store_root=str(art))
        doc["releases"][f"{slug}@{ver}"]["image_upload"] = {
            k: got.get(k) for k in ("state", "failures", "warnings", "images", "why")}

    # 7. the first-sale view
    view = first_sale.build(db, store_root=str(art))
    doc["first_sale"] = view
    doc["seconds"] = round(time.time() - t0, 1)
    doc["etsy_called"] = False
    (d / "firstsale.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
    (d / "first_sale.md").write_text(first_sale.render_markdown(view))
    summary = {}
    for k, r in doc["releases"].items():
        summary[k] = {"durable_before": r["durable_before"]["state"],
                      "purchase": r["purchase"]["state"],
                      "rerender": f"{r['rerender']['before']}->{r['rerender']['after']}",
                      "restorable": r["deliverables_restorable"]["ok"],
                      "image_upload": r["image_upload"]["state"],
                      "images": len(r["image_upload"].get("images") or [])}
    return {"wrote": str(d / "firstsale.json"), "seconds": doc["seconds"], "summary": summary}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), indent=1, default=str))
