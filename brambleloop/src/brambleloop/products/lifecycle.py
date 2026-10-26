"""F-672: the product lifecycle -- an enumerated state per product, with the allowed moves.

DISCOVERED -> RESEARCHING -> SELECTED -> PATTERN -> QA -> VISUAL -> LISTING_READY -> LIVE ->
GROWING | MAINTAIN | RETIRED, plus REJECTED (from any pre-LIVE stage) and ROLLED_BACK (a LIVE
product withdrawn back to LISTING_READY by a rollback).

`derive(db, slug)` reads the stage from the rows the product already has -- never from a
free-text status: a certified pattern version, listing assets, a draft or published listing,
orders, a retired listing, and REJECTED/ROLLED_BACK records. `transition(db, slug, to, why)`
records a deliberate move in company memory and refuses any move `ALLOWED` does not list.
`board(db)` groups every product by its derived stage. Writing transitions from the product
pipeline itself is the product-engine lane's change; the board reads truth either way.
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
    memory.remember(db, KEY + slug, kind="product.lifecycle", department="product_design",
                    subject=f"{slug} lifecycle", state=to.lower(),
                    body={"stage": to, "from": frm, "why": why[:300], "by": by},
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
