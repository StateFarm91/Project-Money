"""W4-LAUNCHREADY: per-product Launch-0 readiness, read from the repository's own gate code.

    PYTHONPATH=src python research/final_build/w4/launch_readiness_run.py <chain_dir> [--out FILE]

`<chain_dir>` is a directory produced by `pipe_chain_run.py <chain_dir> <launch-0 CIR slugs>`:
a scratch SQLite DB (`run.sqlite`) on which the REAL release chain ran in SHADOW, and its
artifact store (`art/`). This script only reads that DB and store (the gate functions it calls
may write their own verdict rows into the scratch DB, never anywhere else). No network (every
outbound socket is refused), no model, no Etsy, no spend.

For each Launch-0 release it records: CIR compile/certification, Product Truth gates, the
pattern PDF / download state, the first-customer nine-area gate, the eight-part creative parity
verdict, the publication-authority sections, the store.publish release-gate reasons, the stored
listing fields, the price and its basis, and bundle/family membership. Every value is computed
here; anything that could not be read is UNKNOWN, never PASS and never 0.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

UNKNOWN = "UNKNOWN"


def _closed(*_a, **_k):
    raise OSError("network closed for the W4-LAUNCHREADY readiness read")


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN and says why
        return {"state": UNKNOWN, "error": f"{type(exc).__name__}: {str(exc)[:400]}"}


def _listing_row(db, slug, version):
    from sqlalchemy import select

    from brambleloop.core.models import Listing

    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version)
                       .order_by(Listing.id.desc()).limit(1))
        if row is None:
            return None
        return {"id": row.id, "state": row.state, "title": row.title,
                "title_chars": len(row.title or ""),
                "description_chars": len(row.description or ""),
                "_description": row.description or "",
                "tags": list(row.tags or []), "tag_count": len(row.tags or []),
                "price_cad": row.price_cad, "release_hash": row.release_hash,
                "etsy_listing_id": row.etsy_listing_id or ""}


def _search_profile(db, slug, version):
    from sqlalchemy import inspect, text

    eng = db.engine
    if "listing_search_profiles" not in inspect(eng).get_table_names():
        return None
    with eng.connect() as c:
        cols = [col["name"] for col in inspect(eng).get_columns("listing_search_profiles")]
        rows = c.execute(text("SELECT * FROM listing_search_profiles WHERE product_slug=:s "
                              "ORDER BY id DESC LIMIT 1"), {"s": slug}).mappings().all()
    if not rows:
        return None
    r = dict(rows[0])
    keep = {k: r[k] for k in cols if k in ("verdict", "version", "taxonomy_id", "category",
                                            "failed", "checks", "attributes", "reasons")}
    return {k: (json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v)
            for k, v in keep.items()}


def _pdfs(db, slug, version):
    from sqlalchemy import select

    from brambleloop.core.models import PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = None if product is None else s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version))
        if pv is None:
            return {"stored": False}
        cert = dict(pv.certificate or {})
        return {"stored": True, "certified": bool(pv.certified),
                "release_hash": pv.release_hash or "",
                "certificate_keys": sorted(cert.keys())[:60],
                "documents": {k: cert[k] for k in ("documents", "pdfs", "pdf", "downloads",
                                                   "deliverables") if k in cert},
                "physical_test_required": cert.get("physical_test_required"),
                "physical_test_passed": cert.get("physical_test_passed")}


def _bundle(slug):
    from brambleloop.radar.opportunity import POOL

    seed = next((m for m in POOL if m.slug == slug), None)
    if seed is None:
        return {"in_pool": False, "family": None, "bundles_with_family": []}
    fam = seed.family
    bundles = [m.slug for m in POOL if fam and m.is_bundle and m.family == fam]
    return {"in_pool": True, "family": fam, "is_bundle": bool(seed.is_bundle),
            "bundles_with_family": bundles}


def product(db, store_root, rel) -> dict:
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.gates import first_customer as fc
    from brambleloop.ops import publication_authority as pa
    from brambleloop.products import launch0 as l0
    from brambleloop.publish import release_gates as rg

    slug, version, cand_slug = rel["slug"], rel["version"], rel["candidate"]
    cand = l0.candidate(cand_slug)
    v = next(v for v in cand.variants if l0.cir_for(v.build).slug == slug)
    cir = l0.cir_for(v.build)
    res = compile_cir(cir)
    pdfs = _guard(lambda: _pdfs(db, slug, version))
    listing = _guard(lambda: _listing_row(db, slug, version))
    truth = _guard(lambda: l0.product_truth(cand))
    price = _guard(lambda: l0.price_plan(cand))
    launch_price = _guard(lambda: l0.launch_price(slug))
    fcg = _guard(lambda: fc.gate_product(
        cir, listing=(None if not isinstance(listing, dict) or "title" not in listing else
                      {"title": listing["title"], "tags": listing["tags"],
                       "description": listing.pop("_description"),
                       "price_cad": listing["price_cad"]}),
        db=db, version=version).to_dict())
    release = pdfs.get("release_hash", "") if isinstance(pdfs, dict) else ""
    ev = _guard(lambda: pa.evidence(db, slug, version, release))
    gates = _guard(lambda: rg.for_publish(db, slug=slug, version=version,
                                          store_root=store_root, read_only=True))
    search = _guard(lambda: _search_profile(db, slug, version))
    bundle = _guard(lambda: _bundle(cir.slug))
    sections = ({k: {"state": ev[k].get("state"), "why": str(ev[k].get("why", ""))[:600]}
                 for k in pa.GATED_SECTIONS + ("economics",)}
                if isinstance(ev, dict) and "certification" in ev else ev)
    return {
        **rel,
        "cir": {"compiles": res.ok, "errors": len(res.errors), "warnings": len(res.warnings)},
        "release": pdfs,
        "product_truth": (None if not isinstance(truth, dict) or "gates" not in truth else
                          {"gates": truth["gates"], "passes": truth["passes_gates"],
                           "calibrated": truth["aspiration"]["physically_calibrated"]}),
        "first_customer": fcg,
        "publication_authority": sections,
        "release_gates": (gates if not isinstance(gates, dict) or "reasons" not in gates else
                          {"blocks_release": gates["blocks_release"],
                           "reasons": gates["reasons"],
                           "originality": {k: gates["originality"].get(k) for k in
                                           ("passes", "state", "reasons")
                                           if k in gates["originality"]},
                           "window": {k: gates["window"].get(k) for k in
                                      ("may_launch_seasonally", "action", "why")}}),
        "listing": listing,
        "search_profile": search,
        "price_plan": price,
        "launch_price": launch_price,
        "bundle": bundle,
    }


def main(argv: list[str]) -> int:
    d = Path(argv[0]).resolve()
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else d / "readiness.json"
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(d / "art")
    for k in list(os.environ):
        if k.startswith(("ETSY", "ANTHROPIC_API", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
            os.environ.pop(k)
    socket.socket.connect = _closed            # type: ignore[assignment]
    socket.create_connection = _closed         # type: ignore[assignment]

    from brambleloop.core.db import Database
    from brambleloop.launch import packet

    db = Database(f"sqlite:///{d}/run.sqlite", scratch=True)
    rels = packet.launch0_releases()
    rows = [product(db, str(d / "art"), r) for r in rels]
    pkt = _guard(lambda: packet.build(db, sha=os.environ.get("LR_SHA", "unknown"),
                                      repo_root=ROOT, artifact_dir=str(d / "art")))
    doc = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "chain_dir": str(d), "products": rows,
           "packet": ({k: pkt.get(k) for k in ("verdict", "verdict_rule", "products_blocked", "products_with_unknowns",
                                                "owner_queue", "phase")}
                      if isinstance(pkt, dict) and "verdict" in pkt else pkt)}
    out.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
