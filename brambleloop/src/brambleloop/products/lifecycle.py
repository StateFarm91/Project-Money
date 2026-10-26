"""F-672: the product lifecycle -- an enumerated state per product, with the allowed moves.

DISCOVERED -> RESEARCHING -> SELECTED -> PATTERN -> QA -> VISUAL -> LISTING_READY -> LIVE ->
GROWING | MAINTAIN | RETIRED, plus REJECTED (from any pre-LIVE stage) and ROLLED_BACK (a LIVE
product withdrawn back to LISTING_READY by a rollback).

`derive(db, slug)` reads the stage from the rows the product already has -- never from a
free-text status: a certified pattern version, listing assets, a draft or published listing,
orders, a retired listing, and REJECTED/ROLLED_BACK records. `transition(db, slug, to, why)`
records a deliberate move in company memory and refuses any move `ALLOWED` does not list.
`board(db)` groups every product by its derived stage. The pipeline records its own moves:
`after_job` runs when a pipeline job completes (the worker's completion hook) and `observe`
writes the move the job's rows now show -- a forward move along the pre-live order (a job may
cross several stages) or an `ALLOWED` move is recorded with its history; anything else is
recorded as an anomaly (`product.lifecycle_anomaly`), never silently overwritten.
"""
from __future__ import annotations

STAGES = ("DISCOVERED", "RESEARCHING", "SELECTED", "PATTERN", "QA", "VISUAL", "LISTING_READY",
          "LIVE", "GROWING", "MAINTAIN", "RETIRED", "REJECTED", "ROLLED_BACK")
PRE_LIVE = ("DISCOVERED", "RESEARCHING", "SELECTED", "PATTERN", "QA", "VISUAL",
            "LISTING_READY")
ALLOWED: dict[str, tuple[str, ...]] = {
    "DISCOVERED": ("RESEARCHING", "REJECTED"),
    "RESEARCHING": ("SELECTED", "REJECTED"),
    "SELECTED": ("PATTERN", "REJECTED"),
    "PATTERN": ("QA", "REJECTED"),
    "QA": ("VISUAL", "PATTERN", "REJECTED"),
    "VISUAL": ("LISTING_READY", "QA", "REJECTED"),
    "LISTING_READY": ("LIVE", "VISUAL", "REJECTED"),
    "LIVE": ("GROWING", "MAINTAIN", "RETIRED", "ROLLED_BACK"),
    "GROWING": ("MAINTAIN", "RETIRED", "ROLLED_BACK"),
    "MAINTAIN": ("GROWING", "RETIRED", "ROLLED_BACK"),
    "ROLLED_BACK": ("LISTING_READY", "RETIRED"),
    "RETIRED": (),
    "REJECTED": (),
}
KEY = "product.lifecycle:"


class LifecycleRefused(ValueError):
    pass


def may_move(frm: str, to: str) -> bool:
    return to in ALLOWED.get(frm, ())


def derive(db, slug: str) -> dict:
    from sqlalchemy import func, select

    from ..autonomy import memory
    from ..core.models import Listing, ListingAsset, Order, PatternVersion, Product

    rec = memory.get(db, KEY + slug)
    if rec and rec["body"].get("stage") in ("REJECTED", "ROLLED_BACK", "RETIRED"):
        return {"slug": slug, "stage": rec["body"]["stage"], "basis": "recorded transition",
                "why": rec["body"].get("why")}
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        versions = list(s.scalars(select(PatternVersion).where(
            PatternVersion.product_id == product.id))) if product else []
        listings = list(s.scalars(select(Listing).where(Listing.product_slug == slug)))
        assets = s.scalar(select(func.count()).select_from(ListingAsset).where(
            ListingAsset.product_slug == slug)) or 0
        orders = s.scalar(select(func.count()).select_from(Order).where(
            Order.product_slug == slug)) or 0
    states = {x.state for x in listings}
    if listings and states <= {"retired", "withdrawn"} and "published" not in states:
        stage, why = "RETIRED", "every listing is retired or withdrawn"
    elif "published" in states:
        stage, why = ("GROWING", f"{orders} order(s) recorded") if orders else \
            ("LIVE", "a listing is published")
    elif listings:
        stage, why = (("LISTING_READY", "a draft listing with assets") if assets else
                      ("VISUAL", "a draft listing without assets"))
    elif any(v.certified for v in versions):
        stage, why = "QA", "a certified pattern version, no listing yet"
    elif versions:
        stage, why = "PATTERN", "a pattern version that is not certified"
    elif product is not None:
        stage, why = "SELECTED", "a product row, no pattern version"
    else:
        stage, why = (rec["body"]["stage"], "recorded transition") if rec else \
            ("DISCOVERED", "no product row")
    return {"slug": slug, "stage": stage, "basis": "derived from rows", "why": why}


def transition(db, slug: str, to: str, *, why: str, by: str = "orchestrator") -> dict:
    from ..autonomy import memory

    if to not in STAGES:
        raise LifecycleRefused(f"{to!r} is not a lifecycle stage")
    if not str(why).strip():
        raise LifecycleRefused("a transition records why")
    frm = derive(db, slug)["stage"]
    if not may_move(frm, to):
        raise LifecycleRefused(f"{slug}: {frm} -> {to} is not an allowed move "
                               f"(allowed: {list(ALLOWED.get(frm, ()))})")
    rec = memory.get(db, KEY + slug)
    history = list(((rec or {}).get("body") or {}).get("history") or [])[-(HISTORY_MAX - 1):]
    history.append({"from": frm, "to": to, "by": by, "why": why[:300], "legal": True})
    memory.remember(db, KEY + slug, kind="product.lifecycle", department="product_design",
                    subject=f"{slug} lifecycle", state=to.lower(),
                    body={"stage": to, "from": frm, "why": why[:300], "by": by,
                          "history": history},
                    sources=["products", "listings", "orders"])
    return {"slug": slug, "from": frm, "to": to}


def board(db) -> dict:
    from sqlalchemy import select

    from ..core.models import Listing, Product

    with db.session() as s:
        slugs = {p.slug for p in s.scalars(select(Product))} | {
            x.product_slug for x in s.scalars(select(Listing))}
    cols: dict[str, list[str]] = {st: [] for st in STAGES}
    for slug in sorted(slugs):
        cols[derive(db, slug)["stage"]].append(slug)
    return {"columns": cols, "products": len(slugs),
            "note": "stages are derived from rows; REJECTED/ROLLED_BACK/RETIRED can be recorded"}


# Pipeline job types that can move a product, and where each names its product.
PIPELINE_JOBS = ("cir.draft", "cir.revise", "gate.certify", "assets.build",
                 "assets.owned_photography", "assets.model_photography", "listing.draft",
                 "listing.seo", "store.publish", "store.update", "commerce.orders_ingest")
ANOMALY_ACTION = "product.lifecycle_anomaly"
HISTORY_MAX = 50


def _order(stage: str) -> int:
    seq = (*PRE_LIVE, "LIVE", "GROWING")
    return seq.index(stage) if stage in seq else -1


def observe(db, slug: str, *, by: str) -> dict | None:
    """Record the stage the product's rows now show, if it moved since the last record."""
    from ..autonomy import memory
    from ..core.models import AuditLog

    rec = memory.get(db, KEY + slug)
    last = (rec or {}).get("body", {}).get("stage")
    now = derive(db, slug)
    stage = now["stage"]
    if stage == last:
        return None
    legal = (last is None or may_move(last, stage)
             or (_order(last) >= 0 and _order(stage) > _order(last)))
    history = list(((rec or {}).get("body") or {}).get("history") or [])[-(HISTORY_MAX - 1):]
    history.append({"from": last, "to": stage, "by": by, "why": now["why"],
                    "legal": legal})
    memory.remember(db, KEY + slug, kind="product.lifecycle", department="product_design",
                    subject=f"{slug} lifecycle", state=stage.lower(),
                    body={"stage": stage, "from": last, "why": now["why"], "by": by,
                          "observed": True, "history": history},
                    sources=["products", "listings", "orders"])
    if not legal:
        with db.session() as s:
            s.add(AuditLog(actor="lifecycle", action=ANOMALY_ACTION, artifact=slug,
                           detail={"from": last, "to": stage, "by": by, "why": now["why"]}))
    return {"slug": slug, "from": last, "to": stage, "legal": legal}


def _slugs(inputs: dict, outputs: dict) -> list[str]:
    out = []
    for d in (inputs, outputs):
        for k in ("slug", "product_slug"):
            v = d.get(k)
            if isinstance(v, str) and v:
                out.append(v)
        for v in d.get("slugs") or []:
            if isinstance(v, str):
                out.append(v)
    return sorted(set(out))


def after_job(db, job_type: str, inputs: dict, outputs: dict) -> list[dict]:
    if job_type not in PIPELINE_JOBS:
        return []
    return [r for r in (observe(db, slug, by=job_type) for slug in _slugs(inputs, outputs))
            if r is not None]

