"""W4-PRODREADY: customer readiness of the eight named products, measured locally.

    PYTHONPATH=src python research/final_build/w4/prodready_run.py <dir> [--chain]

`--chain` first runs the REAL release chain (gate.certify -> listing.draft -> assets.build ->
pricing.position -> listing.seo -> launch.plan -> store.publish) for every release of every
product, in a SHADOW worker on `<dir>/run.sqlite` (`pipe_chain_run.main`). Every outbound
socket is refused, no credential is present, no model is called and nothing is spent; in
SHADOW `store.publish` refuses.

Then, per release, it reads from the code that enforces each requirement (UNKNOWN is never
PASS):

  certification      `ops.publication_authority` certification section
  product_truth      `products.launch0.product_truth`, compiled now
  pdfs               US and UK pattern PDFs re-rendered from a fresh CIR build, pinned to the
                     release date; every package statement and the AI disclosure in each
  recovery           the fresh build's content hash equals the certified one and both
                     re-rendered PDFs are byte-identical to the hashes `assets.build`
                     certified (`pipeline._certified_pdf_hashes`)
  listing_images     the certified listing set (`publication_authority` listing_set) and the
                     bytes `store.publish` would upload (`etsy_ops.certified_images`)
  legibility         essential text at its actual display size (D-W4-VISROLE-LEGIBILITY):
                     the listing frames' recorded layout (`frame_role.legibility`), and the
                     fixed type sizes of the uploaded disclosed renders and supplements
  hero_thumbnail     the search certificate's hero check (`publication_authority` search)
  visual_roles       the deterministic role checks on every non-photo frame
                     (`frame_role.role_checks`), the independent review
                     (`release.frame_review_state`) and presentation parity
  price              the stored listing price against the Launch-0 plan
                     (`release_gates.launch_price_check`) and `launch0.price_plan`
  copy               the disclosure section, the AI and render disclosures verbatim in the
                     stored description, and the AI disclosure in both PDFs
  publish_gate       every reason `release_gates.for_publish` refuses on (read-only)

READY only when every one of those is PASS. Writes `<dir>/prodready.json`.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

# The eight products the owner named (2026-10-19), in that order.
NAMED = ("nursery-nesting-baskets", "cloudline-baby-blanket", "hexagon-coaster-set",
         "nordic-star-ornaments", "winter-village-graphghan", "harvest-table-runner",
         "housewarming-key-basket", "mosaic-placemat-pair")
CHECKS = ("certification", "product_truth", "pdfs", "recovery", "listing_images",
          "legibility", "hero_thumbnail", "visual_roles", "price", "copy", "publish_gate")


def _closed(*_a, **_k):
    raise OSError("network closed for the W4-PRODREADY run")


def _row(state, why, **extra):
    return {"state": state if state in (PASS, FAIL, UNKNOWN) else UNKNOWN,
            "why": str(why)[:600], **extra}


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN and says why
        return _row(UNKNOWN, f"unreadable: {type(exc).__name__}: {str(exc)[:300]}")


def _norm(text: str) -> str:
    return " ".join(str(text or "").replace("­", "").split())


def products() -> list[dict]:
    from brambleloop.products import launch0 as l0

    out = []
    for slug in NAMED + tuple(s for s in l0.LAUNCH0_SLUGS if s not in NAMED):
        cand = l0.candidate(slug)
        out.append({
            "candidate": slug, "title": cand.title, "named_by_owner": slug in NAMED,
            "in_launch0_scope": slug in l0.LAUNCH0_SLUGS,
            "releases": [{"build": v.build, "slug": l0.cir_for(v.build).slug,
                          "version": l0.cir_for(v.build).version, "label": v.label}
                         for v in cand.variants]})
    return out


# Fixed type sizes of the frames the Launch-0 listing actually uploads (the disclosed render
# set and its verified supplements), classified with the same rule as the listing frames:
# a disclosure, a dimension or scale label, or a frame headline is essential.
def uploaded_type_sizes() -> list[dict]:
    from brambleloop.commerce.thumbnail import MIN_LEGIBLE_TEXT_PX
    from brambleloop.visual import contents_frame as CF
    from brambleloop.visual import frame_role as FR
    from brambleloop.visual import gallery_frames as GF
    from brambleloop.visual import render_contract as K

    rows = [("disclosed render", "disclosure caption", K.CAPTION_PX, "disclosure"),
            ("disclosed render", "scale-bar label / dimension annotations", K.LABEL_PX,
             "size_label"),
            ("gallery supplement", "title", GF.TITLE_PX, "headline"),
            ("gallery supplement", "body", GF.BODY_PX, "row_value"),
            ("gallery supplement", "small", GF.SMALL_PX, "row_label"),
            ("contents supplement", "title", CF.TITLE_PX, "headline"),
            ("contents supplement", "body", CF.BODY_PX, "row_value"),
            ("contents supplement", "small", CF.SMALL_PX, "row_label")]
    out = []
    for renderer, line, pt, slot in rows:
        tier = FR.text_tier("", slot)
        px = round(pt * tier["display_px"] / K.CANVAS_PX, 1)
        out.append({"renderer": renderer, "line": line, "pt_on_2000": pt, "slot": slot,
                    "display_px": tier["display_px"], "px": px,
                    "legible": px >= MIN_LEGIBLE_TEXT_PX})
    return out


def _pdfs(db, build, slug, version, release, cert):
    """Re-render US and UK from a fresh CIR build, pinned to the release date."""
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.learn.service import pdf_help_links
    from brambleloop.products import launch0 as l0
    from brambleloop.publish import pdf as P
    from brambleloop.runtime import pipeline, release as R
    from brambleloop.quality.physical import calibration_from_db

    cir = l0.cir_for(build)
    res = compile_cir(cir)
    twin = build_twin(cir, res, calibration=calibration_from_db(db, cir))
    released_on = R._released_on(types.SimpleNamespace(db=db), slug, version)
    links = pdf_help_links(db, cir.to_dict())
    certified = pipeline._certified_pdf_hashes(db, slug, version, release) or {}
    docs, per = {}, {}
    for t in P.TERMINOLOGIES:
        doc = P.build_pattern_pdf(cir, twin=twin, terminology=t, released_on=released_on,
                                  lesson_links=links)
        docs[t] = doc
        text = _norm(P.extracted_text(doc.pdf_bytes))
        sha = hashlib.sha256(doc.pdf_bytes).hexdigest()
        # The headings the document actually set (`doc.prose`), as assets.build checks them.
        missing = list(P.package_missing(cir, doc.prose))
        per[t] = {"bytes": len(doc.pdf_bytes), "sha256": sha,
                  "certified_sha256": certified.get(t),
                  "byte_identical_to_certified": certified.get(t) == sha,
                  "package_statements_missing": missing,
                  "ai_disclosure_in_pdf": _norm(P.AI_DISCLOSURE) in text,
                  "statement_audit": _guard(lambda: l0.rendered_statement_audit(build, t))}
    content_hash = R._content_hash_of(cir)
    stored_hash = (cert or {}).get("content_hash")
    both = set(per) == {"US", "UK"}
    pdf_ok = both and all(not v["package_statements_missing"] and v["ai_disclosure_in_pdf"]
                          and v["bytes"] > 0 for v in per.values())
    rec_ok = (both and bool(certified) and all(v["byte_identical_to_certified"]
                                               for v in per.values())
              and stored_hash is not None and stored_hash == content_hash)
    pdfs = _row(PASS if pdf_ok else FAIL,
                "US and UK rendered; every package statement and the AI disclosure in each"
                if pdf_ok else "a terminology is missing, or a package statement / the AI "
                               "disclosure is absent from the rendered text", per=per)
    recovery = _row(
        PASS if rec_ok else (UNKNOWN if not certified else FAIL),
        ("fresh CIR build matches the certified content hash and both re-rendered PDFs are "
         "byte-identical to the certified files" if rec_ok else
         "assets.build recorded no PDF hash for this release" if not certified else
         f"drift: content hash {content_hash[:12]} vs certified {str(stored_hash)[:12]}; "
         f"identical {[t for t, v in per.items() if v['byte_identical_to_certified']]}"),
        content_hash=content_hash, certified_content_hash=stored_hash)
    return pdfs, recovery


def _listing_frames(db, build):
    """The assets.build listing frames rebuilt locally: plan, legibility, role checks."""
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.cir.writer import write_pattern
    from brambleloop.products import launch0 as l0
    from brambleloop.publish.listing_assets import build_frames, check_frame_plan
    from brambleloop.runtime import release as R
    from brambleloop.visual import frame_role as FR

    cir = l0.cir_for(build)
    res = compile_cir(cir)
    twin = build_twin(cir, res)
    frames = build_frames(cir, twin, pattern_text=write_pattern(cir, res),
                          difficulty=R._difficulty(twin, cir), pages=8,
                          siblings=R._collection_siblings(cir.slug))
    plan = check_frame_plan(frames)
    labels = FR.expected_labels(frames, cir, twin)
    legs, roles = {}, {}
    for f in frames:
        leg = FR.legibility(f)
        legs[f.position] = {"role": f.role, "ok": None if leg is None else leg["ok"],
                            "smallest_essential_px": (leg or {}).get("smallest_essential_px"),
                            "essential_failing": (leg or {}).get("essential_failing"),
                            "secondary_below_floor": [
                                {k: x[k] for k in ("text", "slot", "px")}
                                for x in (leg or {}).get("secondary_below_floor") or []]}
        vr = FR.classify(f)
        if vr in FR.NON_PHOTO:
            checks = FR.role_checks(f, slug=cir.slug, visual_role=vr, description=None,
                                    plan_findings=plan, labels=labels.get(f.position))
            roles[f.position] = {"role": f.role, "visual_role": vr,
                                 "checks": {k: v["passed"] for k, v in checks.items()}}
    return plan, legs, roles


def _release(db, prod, rel, art, type_sizes):
    from sqlalchemy import select

    from brambleloop.core.models import Listing
    from brambleloop.gates.platform_policy import DISCLOSURES
    from brambleloop.launch import product_readiness as PRD
    from brambleloop.launch.packet import _stored_release
    from brambleloop.ops import publication_authority as pa
    from brambleloop.products import launch0 as l0
    from brambleloop.publish import release_gates as rg
    from brambleloop.runtime import etsy_ops
    from brambleloop.runtime.release import frame_review_state

    slug, version = rel["slug"], rel["version"]
    stored = _guard(lambda: _stored_release(db, slug, version))
    release = stored.get("release") or ""
    ev = _guard(lambda: pa.evidence(db, slug, version, release))
    out: dict = {"slug": slug, "version": version, "release": release or None,
                 "label": rel["label"]}

    cert_sec = ev.get("certification") or {}
    out["certification"] = _row(cert_sec.get("state", UNKNOWN), cert_sec.get("why", ""),
                                blocking=cert_sec.get("blocking_finding_codes"),
                                physical_proof=cert_sec.get("physical_proof"))
    truth = _guard(lambda: l0.product_truth(l0.candidate(prod["candidate"])))
    out["product_truth"] = (
        _row(PASS if truth.get("passes_gates") else FAIL,
             f"gates {truth.get('gates')}; physically calibrated: "
             f"{(truth.get('aspiration') or {}).get('physically_calibrated')}")
        if "gates" in truth else truth)

    with db.session() as s:
        lst = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version)
                       .order_by(Listing.id.desc()).limit(1))
        listing = None if lst is None else {"title": lst.title, "description": lst.description,
                                            "price_cad": lst.price_cad, "state": lst.state,
                                            "tags": list(lst.tags or [])}
    pv_cert = None
    if stored.get("stored"):
        from brambleloop.ops.publication_authority import _release_row

        pv, _l = _release_row(db, slug, version)
        pv_cert = (pv or {}).get("certificate")
    pdfs_rec = _guard(lambda: _pdfs(db, rel["build"], slug, version, release, pv_cert))
    if isinstance(pdfs_rec, tuple):
        out["pdfs"], out["recovery"] = pdfs_rec
    else:
        out["pdfs"] = out["recovery"] = pdfs_rec

    ls_sec = ev.get("listing_set") or {}
    imgs = _guard(lambda: etsy_ops.certified_images(db, slug, version, release=release,
                                                   store_root=str(art)))
    n_imgs = len(imgs.get("images") or []) if isinstance(imgs, dict) else 0
    img_ok = ls_sec.get("state") == PASS and n_imgs > 0 and not (imgs.get("problems") or [])
    out["listing_images"] = _row(
        PASS if img_ok else FAIL if ls_sec.get("state") == FAIL else UNKNOWN,
        f"listing set {ls_sec.get('state')}: {ls_sec.get('why')}; {n_imgs} certified image(s) "
        f"store.publish would upload; problems {(imgs.get('problems') or [])[:3]}",
        reasons=ls_sec.get("reasons"),
        uploaded=[name for name, _d in (imgs.get("images") or [])][:12])

    frames = _guard(lambda: _listing_frames(db, rel["build"]))
    if isinstance(frames, tuple):
        plan, legs, roles = frames
    else:
        plan, legs, roles = [f"unreadable: {frames.get('why')}"], {}, {}
    upl_bad = [t for t in type_sizes if not t["legible"]]
    frames_bad = {p: v for p, v in legs.items() if v["ok"] is not True}
    out["legibility"] = _row(
        PASS if not frames_bad and not upl_bad and legs else FAIL,
        ("every essential line clears 11 px at its display size on the listing frames and "
         "on the uploaded set" if not frames_bad and not upl_bad and legs else
         f"listing frames failing: {sorted(frames_bad)}; uploaded-set type below the floor: "
         + "; ".join(f"{t['renderer']} {t['line']} {t['px']}px at {t['display_px']}px"
                     for t in upl_bad)),
        listing_frames=legs, uploaded_type=type_sizes, frame_plan_problems=plan)

    search = ev.get("search") or {}
    out["hero_thumbnail"] = _row(search.get("state", UNKNOWN), search.get("why", ""),
                                 reasons=(search.get("reasons") or [])[:6])

    review = _guard(lambda: frame_review_state(db, slug, version))
    parity = ev.get("parity") or {}
    det_fail = {p: [k for k, v in r["checks"].items() if v is False] for p, r in roles.items()}
    det_fail = {p: v for p, v in det_fail.items() if v}
    unans = sorted({k for r in roles.values() for k, v in r["checks"].items() if v is None})
    vr_ok = (not det_fail and bool(review.get("reviewed")) and parity.get("state") == PASS
             and bool(roles))
    out["visual_roles"] = _row(
        PASS if vr_ok else FAIL if det_fail else UNKNOWN,
        (f"deterministic role checks failing {det_fail}; " if det_fail else
         "deterministic role checks pass on every non-photo frame; ")
        + (f"unanswered without a vision run: {unans}; " if unans else "")
        + f"independent frame review: {'reviewed' if review.get('reviewed') else 'NOT reviewed'}"
          f" ({str(review.get('why') or '')[:160]}); parity {parity.get('state')}: "
          f"{str(parity.get('why') or '')[:160]}",
        role_checks=roles)

    price = _guard(lambda: PRD._price_plan(stored, slug))
    plan_price = _guard(lambda: l0.price_plan(l0.candidate(prod["candidate"])))
    econ = ev.get("economics") or {}
    stored_price = (listing or {}).get("price_cad")
    plan_cad = plan_price.get("price_cad") if isinstance(plan_price, dict) else None
    price_ok = price.get("state") == PASS and stored_price is not None and plan_cad is not None
    out["price"] = _row(
        price.get("state", UNKNOWN) if price.get("state") != PASS or price_ok else UNKNOWN,
        f"{price.get('why')}; stored listing CA${stored_price}; launch0.price_plan "
        f"CA${plan_cad} (proposed CA${(plan_price or {}).get('proposed_cad')}); net after "
        f"fees CA${econ.get('net_per_sale_cad')} (modelled)",
        listing_cad=stored_price, plan_cad=plan_cad)

    disc = ev.get("disclosure") or {}
    desc = _norm((listing or {}).get("description"))
    need = {k: _norm(DISCLOSURES[k]) in desc for k in ("ai_assisted_design",
                                                       "disclosed_render")}
    pdf_ai = all(v.get("ai_disclosure_in_pdf") for v in
                 ((out["pdfs"].get("per") or {}).values()))
    copy_ok = disc.get("state") == PASS and all(need.values()) and pdf_ai and listing
    out["copy"] = _row(
        PASS if copy_ok else FAIL if listing else UNKNOWN,
        f"disclosure section {disc.get('state')} (missing {disc.get('missing')}); verbatim in "
        f"the description: {need}; AI disclosure in both PDFs: {pdf_ai}",
        title=(listing or {}).get("title"), title_chars=len((listing or {}).get("title") or ""),
        tags=len((listing or {}).get("tags") or []))

    g = _guard(lambda: rg.for_publish(db, slug=slug, version=version, store_root=str(art),
                                      read_only=True))
    if "blocks_release" in g:
        out["publish_gate"] = _row(FAIL if g["blocks_release"] else PASS,
                                   "; ".join(str(r) for r in g["reasons"][:8]) or "no refusal",
                                   reasons=[str(r)[:400] for r in g["reasons"]])
    else:
        out["publish_gate"] = g
    out["ready"] = all(out[c]["state"] == PASS for c in CHECKS)
    out["blockers"] = [{"check": c, "state": out[c]["state"], "why": out[c]["why"]}
                       for c in CHECKS if out[c]["state"] != PASS]
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
    prods = products()
    chain = None
    if "--chain" in argv:
        import pipe_chain_run

        chain = pipe_chain_run.main([str(d)] + [r["slug"] for p in prods for r in p["releases"]])

    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{d}/run.sqlite", scratch=True)
    db.create_all()
    type_sizes = uploaded_type_sizes()
    rows = []
    for p in prods:
        rels = [_release(db, p, r, d / "art", type_sizes) for r in p["releases"]]
        rows.append({**{k: p[k] for k in ("candidate", "title", "named_by_owner",
                                          "in_launch0_scope")},
                     "ready": all(r["ready"] for r in rels), "releases": rels})
    doc = {"generated_seconds": round(time.time() - t0, 1), "chain": chain,
           "checks": list(CHECKS), "uploaded_type_sizes": type_sizes, "products": rows,
           "publishes_anything": False}
    (d / "prodready.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
    return {"wrote": str(d / "prodready.json"), "seconds": doc["generated_seconds"],
            "ready": {r["candidate"]: r["ready"] for r in rows}}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), indent=1))
