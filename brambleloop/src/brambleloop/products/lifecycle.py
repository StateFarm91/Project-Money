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


def _complete_gallery(s, slug: str) -> bool:
    """Whether a valid listing-set certificate for `slug` names the whole campaign gallery
    (at least CAMPAIGN_MIN_FRAMES frames). Unreadable is never complete."""
    from sqlalchemy import desc, select

    from ..core.models import ListingSetCertificateRecord
    from ..visual.shot_plans import CAMPAIGN_MIN_FRAMES

    try:
        rec = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        frames = (rec.certificate or {}).get("frames") if rec is not None else None
        return isinstance(frames, list) and len(frames) >= CAMPAIGN_MIN_FRAMES
    except Exception:  # noqa: BLE001 - unreadable is never complete
        return False


def _ready_for_sale(db, slug: str, version: str | None) -> dict:
    """The sale pipeline's ready-for-sale reading. Unreadable is never ready."""
    if not version:
        return {"ready": False, "reasons": ["no certified version with a listing"]}
    try:
        from ..publish import sale_pipeline

        return sale_pipeline.ready_for_sale(db, slug, version)
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "reasons": [f"unreadable ({type(exc).__name__})"]}


def derive(db, slug: str) -> dict:
    """The product's lifecycle stage. eng/evidence-perf: inside a request memo
    (`core.request_memo.scope`, the readback evidence) each slug is derived once; everywhere
    else this reads live rows on every call, as before."""
    from ..core import request_memo

    return request_memo.memo(("lifecycle.derive", id(db), slug), lambda: _derive(db, slug))


def _derive(db, slug: str) -> dict:
    from sqlalchemy import func, select

    from ..autonomy import memory
    from ..core.models import Listing, ListingAsset, Order, PatternVersion, Product

    rec = memory.get(db, KEY + slug)
    # NEXT-FIXES: only a DELIBERATE transition (`transition()`) is terminal. A record written
    # by `observe()` (`observed: True`) is a cache of what the rows derived at that time; the
    # rows stay the source of truth. Before this, a RETIRED observed under the pre-19i14 rule
    # ("withdrawn and never on Etsy" read as retired) was replayed forever, so sale admission
    # kept refusing four products as "product is RETIRED" after the rule was fixed.
    if (rec and rec["body"].get("stage") in ("REJECTED", "ROLLED_BACK", "RETIRED")
            and not rec["body"].get("observed")):
        return {"slug": slug, "stage": rec["body"]["stage"], "basis": "recorded transition",
                "why": rec["body"].get("why")}
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        # eng/evidence-perf: only the columns read here; loading whole rows pulled every
        # release's CIR and certificate JSON. BATCH19F: the sale pipeline's version choice
        # also reads id and version.
        versions = list(s.execute(select(PatternVersion.id, PatternVersion.version,
                                         PatternVersion.certified).where(
            PatternVersion.product_id == product.id))) if product else []
        listings = list(s.scalars(select(Listing).where(Listing.product_slug == slug)))
        assets = s.scalar(select(func.count()).select_from(ListingAsset).where(
            ListingAsset.product_slug == slug)) or 0
        orders = s.scalar(select(func.count()).select_from(Order).where(
            Order.product_slug == slug)) or 0
        gallery = _complete_gallery(s, slug)
        certified = sorted(((v.id, v.version) for v in versions if v.certified), reverse=True)
        listed = {x.version for x in listings}
        sale_version = next((ver for _id, ver in certified if ver in listed), None)
    from ..core.listing_state import LIVE_ON_ETSY

    states = {x.state for x in listings}
    live = bool(states & set(LIVE_ON_ETSY))
    # GALLERY-START: a listing withdrawn before it ever reached Etsy (a refused certification
    # withdraws the draft) is a draft to re-make, not a retired product. Only a listing that
    # was on Etsy, or one recorded retired, retires the product.
    never_on_etsy = bool(listings) and all(
        x.state == "withdrawn" and not (x.etsy_listing_id or "").strip() for x in listings)
    if listings and states <= {"retired", "withdrawn"} and not live and not never_on_etsy:
        stage, why = "RETIRED", "every listing is retired or withdrawn"
    elif live:
        stage, why = ("GROWING", f"{orders} order(s) recorded") if orders else \
            ("LIVE", "a listing is published")
    elif listings:
        # D-OWNER-GALLERY-COMPLETE: a listing is not ready until every listing photo is.
        # D-OWNER-SALE-PIPELINE: and not until both premium PDFs are certified for the release
        # and every listing gate passes (`publish.sale_pipeline.ready_for_sale`).
        sale = _ready_for_sale(db, slug, sale_version) if (assets and gallery) else None
        if sale and sale["ready"]:
            waits = sale.get("publication_blockers") or []
            stage, why = ("LISTING_READY", "ready for sale: certified pattern, complete "
                          "certified gallery, both premium PDFs certified, every gate PASS"
                          + (f"; publication waits on {', '.join(waits)} (private draft "
                             f"only, D-OWNER-PRIVATE-DRAFT-BEFORE-SAMPLE)" if waits else ""))
        elif assets and gallery:
            stage, why = "VISUAL", ("a draft listing with its gallery, not yet ready for sale: "
                                    + "; ".join((sale or {}).get("reasons") or ["unreadable"]))
        elif assets:
            stage, why = "VISUAL", "a draft listing whose certified gallery is incomplete"
        else:
            stage, why = "VISUAL", "a draft listing without assets"
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

