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
PROMPT_NEGATIVE, REFERENCE_CHANGE, VERIFY_UNFOLDED = (
    "prompt_negative", "reference_change", "verify_on_product_only")

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
    FC.UNVERIFIABLE_COUNT: {
        "kind": VERIFY_UNFOLDED,
        "why": ("a count hidden by folds cannot be verified on a lifestyle image; it stays "
                "UNKNOWN and is verified only on the unfolded product-only image")},
}

EXPERIMENT_RECORD = (Path(__file__).resolve().parents[3] / "research" / "final_build" / "w4"
                     / "flux_experiments" / "2026-10-19_reading_nook_cable_wrap"
                     / "RECORD.json")


def _record() -> dict | None:
    try:
        return json.loads(EXPERIMENT_RECORD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def shared_codes() -> dict:
    """The shared failure-code set and where it was read from. Never redefined here."""
    return {"codes": tuple(sorted(FC.ALL_CODES)), "source": "creative.failure_codes.ALL_CODES"}


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


def seed_experiment(db) -> dict:
    """Import the owner's manual wrap experiment as the first learning example. It is
    idempotent on the output sha256. The method is `owner_manual`. Identity reads UNKNOWN,
    because the owner's visual approval is not an independent identity check."""
    from sqlalchemy import select

    from ..core import fx
    from .image_records import ImageCandidate, ensure_tables

    rec = _record()
    if rec is None:
        return {"seeded": False, "why": "experiment record not present in this deployment"}
    ensure_tables(db)
    out = rec["output"]
    with db.session() as s:
        if s.scalar(select(ImageCandidate).where(ImageCandidate.sha256 == out["sha256"],
                                                 ImageCandidate.method == "owner_manual")):
            return {"seeded": False, "why": "already seeded"}
        receipt = rec.get("receipt_as_shown_on_dashboard") or {}
        codes = [c["code"] for c in rec.get("failure_categories") or []]
        detail = {c["code"]: c.get("detail") for c in rec.get("failure_categories") or []}
        product = rec.get("product") or {}
        checks = {
            "product_truth": {"status": "FAIL", "codes": codes, "detail": detail,
                              "stays_unknown": [c for c in codes if c == UNVERIFIABLE_COUNT]},
            "identity": {"status": "UNKNOWN",
                         "why": "owner visual approval only; independent identity check not run"},
            "binding": {"status": "FAIL",
                        "why": product.get("certification_refusal") or "uncertified"},
            "quality": {"status": "FAIL", "why": f"{out.get('pixels')} px is below 2000 px"},
            "_routes": route(codes)}
        usd = receipt.get("cost_usd")
        row = ImageCandidate(
            sha256=out["sha256"], run_key="seed:" + rec["experiment_id"], method="owner_manual",
            provenance_kind="ai_generated_owner_manual", slug=product.get("slug", ""),
            version=product.get("version", ""), listing=product.get("slug", ""),
            role="lifestyle", stage="seed", provider="bfl-dashboard",
            model=str(receipt.get("model") or ""), prompt_version="MISSING",
            references=[{"sha256": r["sha256"], "kind": (
                "laura_canonical" if r["n"] <= 3 else "pattern_derived")}
                for r in rec.get("references") or []],
            laura_present=True, outfit_id="", width=(out.get("pixels") or [None, None])[0],
            height=(out.get("pixels") or [None, None])[1],
            cost_cad=(round(float(usd) / fx.ASSUMED_USD_PER_CAD, 4) if usd is not None
                      else None),
            cost_basis="owner dashboard receipt (USD), converted at core.fx",
            latency_s=receipt.get("latency_s"), binding={"certified": False},
            checks=checks, technical_status="FAIL", publishable=False, outcome="rejected",
            failure_categories=["product_fidelity"] + codes, owner_visual_approval=True,
            submitted_by="owner:manual-experiment")
        s.add(row)
        s.flush()
        return {"seeded": True, "candidate_id": row.id, "codes": codes}
