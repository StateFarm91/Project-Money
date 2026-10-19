"""Product Truth failure codes, routed to targeted repairs, and the seeded learning example.

**Codes.** The one shared constant is `creative.failure_codes` (W-FLUXAPI). This module
imports it and does not redefine it.

**Routing.** `ROUTES` is this workflow's repair decision for each code: either prompt
negatives or a reference change, applied within the attempt cap
(`image_production.MAX_ATTEMPTS_PER_ROLE`).

* `UNVERIFIABLE_COUNT` is never repaired into a pass. It stays UNKNOWN and blocks. Its only
  route is to verify on the unfolded product-only image.
* A code with no route is not repaired at all, and the image stays blocked.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..creative import failure_codes as FC

UNVERIFIABLE_COUNT = FC.UNVERIFIABLE_COUNT
PROMPT_NEGATIVE, REFERENCE_CHANGE, VERIFY_UNFOLDED, REPICK_OUTFIT = (
    "prompt_negative", "reference_change", "verify_on_product_only", "repick_outfit")

# Keyed by the shared constant (creative.failure_codes); this table is only the routing.
ROUTES: dict[str, dict] = {
    FC.INVENTED_END_BAND_TREATMENT: {
        "kind": PROMPT_NEGATIVE,
        "negatives": ["no ribbing in the end bands", "no stripe in the end bands",
                      "end bands exactly as the pattern's plain rows"]},
    FC.INVENTED_EDGING: {
        "kind": PROMPT_NEGATIVE,
        "negatives": ["no edging", "no border", "plain row edges exactly as the pattern"]},
    FC.WRONG_CRAFT_TEXTURE: {
        "kind": REFERENCE_CHANGE,
        "reference": "stitch-texture reference rendered from the stitch definitions",
        "negatives": ["not knitting", "no knitted rope cables", "crochet fabric only"]},
    FC.REFERENCE_CLOTHING_CARRYOVER: {
        "kind": PROMPT_NEGATIVE, "replace_clothing": True,
        "negatives": ["REPLACE ALL clothing from the reference images with the reserved "
                      "outfit", "not the beige trousers from the reference images",
                      "not the ivory or cream top from the reference images",
                      "not the tan sandals from the reference images"]},
    FC.WARDROBE_REPETITION: {
        "kind": REPICK_OUTFIT,
        "why": "pick a distinct complete outfit (the current one excluded) and regenerate"},
    FC.UNVERIFIABLE_COUNT: {
        "kind": VERIFY_UNFOLDED,
        "why": ("a count hidden by folds cannot be verified on a lifestyle image; it stays "
                "UNKNOWN and is verified only on the unfolded product-only image")},
}

EXPERIMENTS_DIR = (Path(__file__).resolve().parents[3] / "research" / "final_build" / "w4"
                   / "flux_experiments")
EXPERIMENT_RECORD = EXPERIMENTS_DIR / "2026-10-19_reading_nook_cable_wrap" / "RECORD.json"


def _record(path: Path | None = None) -> dict | None:
    try:
        return json.loads((path or EXPERIMENT_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def experiment_records() -> list[Path]:
    """Every owner-manual experiment record on file, oldest first."""
    try:
        return sorted(EXPERIMENTS_DIR.glob("*/RECORD.json"))
    except OSError:
        return []


def shared_codes() -> dict:
    """The shared failure-code set and where it was read from. Never redefined here."""
    return {"codes": tuple(sorted(FC.EVERY_CODE)), "product_truth": tuple(sorted(FC.ALL_CODES)),
            "wardrobe": tuple(sorted(FC.WARDROBE_ALL_CODES)),
            "source": "creative.failure_codes.EVERY_CODE"}


def route(codes) -> dict:
    """Repair directives for these codes, plus what cannot be repaired."""
    directives, unrouted, unknown = [], [], []
    for code in codes or ():
        r = ROUTES.get(code)
        if r is None:
            unrouted.append(code)
        elif r["kind"] == VERIFY_UNFOLDED:
            unknown.append(code)
        else:
            directives.append({"code": code, **r})
    return {"directives": directives, "unrouted": unrouted, "stays_unknown": unknown,
            "repairable": bool(directives) and not unrouted}


def seed_experiments(db) -> list[dict]:
    """Seed every owner-manual experiment: a learning row each, plus its outfit as wardrobe
    history (so no later listing can reuse it). Idempotent."""
    return [{"record": p.parent.name, **seed_experiment(db, p),
             "wardrobe": seed_wardrobe_history(db, p)} for p in experiment_records()]


def seed_wardrobe_history(db, path: Path | None = None) -> dict:
    """The experiment's outfit, recorded against its product as owner-manual history."""
    from sqlalchemy.orm.attributes import flag_modified

    from . import outfits
    from .image_records import ensure_tables
    from .wardrobe import split_outfit_text

    rec = _record(path)
    if not rec or not rec.get("outfit"):
        return {"recorded": False, "why": "no outfit in the record"}
    slug = (rec.get("product") or {}).get("slug") or ""
    garments = (rec["outfit"] if isinstance(rec["outfit"], dict)
                else split_outfit_text(rec["outfit"]))
    oid = f"owner-manual-{slug}"[:80]
    ensure_tables(db)
    try:
        outfits.register(db, outfit_id=oid, garments=garments,
                         concept={"source": rec["experiment_id"], "owner_manual": True})
    except outfits.OutfitRefused as exc:
        return {"recorded": False, "why": str(exc)}
    sha = (rec.get("output") or {}).get("sha256")
    with db.session() as s:
        row = outfits._row(s, oid)
        row.approval_state, row.approved_by = "approved", "owner:manual-experiment"
        row.listing = row.listing or slug      # history: what was worn, recorded as fact
        uses = list(row.uses or [])
        entry = {"listing": slug, "product": f"{slug}@{(rec.get('product') or {}).get('version')}",
                 "image_sha256": sha, "at": rec.get("recorded_at"), "owner_manual": True,
                 "experiment_id": rec["experiment_id"]}
        if not any(u.get("experiment_id") == rec["experiment_id"] for u in uses):
            uses.append(entry)
            row.uses = uses
            flag_modified(row, "uses")
    return {"recorded": True, "outfit_id": oid, "listing": slug}


def seed_experiment(db, path: Path | None = None) -> dict:
    """Import one owner-manual experiment as a learning example. It is idempotent on the
    experiment id. The method is `owner_manual`. Identity reads UNKNOWN, because the owner's
    visual approval is not an independent identity check. Without image bytes nothing is
    measured: only the facts the record states."""
    from sqlalchemy import select

    from ..core import fx
    from .image_records import ImageCandidate, ensure_tables

    rec = _record(path)
    if rec is None:
        return {"seeded": False, "why": "experiment record not present in this deployment"}
    ensure_tables(db)
    out = rec.get("output") or {}
    run = "seed:" + rec["experiment_id"]
    with db.session() as s:
        if s.scalar(select(ImageCandidate).where(ImageCandidate.run_key == run)):
            return {"seeded": False, "why": "already seeded"}
        receipt = rec.get("receipt_as_shown_on_dashboard") or {}
        codes = [c["code"] for c in rec.get("failure_categories") or []]
        detail = {c["code"]: c.get("detail") for c in rec.get("failure_categories") or []}
        product = rec.get("product") or {}
        pixels = out.get("pixels") or [None, None]
        has_bytes = bool(out.get("sha256"))
        pt_status = "FAIL" if codes else "UNKNOWN"
        checks = {
            "product_truth": {"status": pt_status, "codes": codes, "detail": detail,
                              "stays_unknown": [c for c in codes if c == UNVERIFIABLE_COUNT]},
            "identity": {"status": "UNKNOWN",
                         "why": "owner visual approval only; independent identity check not run"},
            "binding": {"status": "FAIL",
                        "why": product.get("certification_refusal") or "uncertified"},
            "quality": ({"status": "FAIL" if min(pixels) < 2000 else "UNKNOWN",
                         "why": f"{pixels} px"} if has_bytes and pixels[0] else
                        {"status": "UNKNOWN", "why": "no image bytes supplied"}),
            "_routes": route(codes)}
        usd = receipt.get("cost_usd")
        row = ImageCandidate(
            sha256=out.get("sha256") or "", run_key=run, method="owner_manual",
            provenance_kind="ai_generated_owner_manual", slug=product.get("slug", ""),
            version=str(product.get("version") or ""), listing=product.get("slug", ""),
            role="lifestyle", stage="seed", provider="bfl-dashboard",
            model=str(receipt.get("model") or ""), prompt_version="MISSING",
            references=[{"sha256": r["sha256"], "kind": (
                "laura_canonical" if r["n"] <= 3 else "pattern_derived")}
                for r in rec.get("references") or []],
            laura_present=True, outfit_id=f"owner-manual-{product.get('slug', '')}"[:80],
            width=pixels[0], height=pixels[1],
            cost_cad=(round(float(usd) / fx.ASSUMED_USD_PER_CAD, 4) if usd is not None
                      else None),
            cost_basis="owner dashboard receipt (USD), converted at core.fx",
            latency_s=receipt.get("latency_s"), binding={"certified": False},
            checks=checks, technical_status="FAIL", publishable=False,
            outcome="rejected" if codes else "unverified",
            failure_categories=(["product_fidelity"] if codes else []) + codes,
            owner_visual_approval=True, submitted_by="owner:manual-experiment")
        s.add(row)
        s.flush()
        return {"seeded": True, "candidate_id": row.id, "codes": codes}
