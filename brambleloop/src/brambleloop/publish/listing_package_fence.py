"""Withdraw package review requests when their ORM release sources change.

This is a narrow safeguard: bulk SQL and other evidence (gallery, PDFs, policy
and physical tests) require their own contracts.
"""
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session


@event.listens_for(Session, "before_flush")
def _withdraw_changed_release_requests(session, _context, _instances):
    from ..core.models import Listing, PatternVersion, Product
    from ..ops.owner_queue_guard import _lock
    from .listing_package import _invalidate_locked

    listing_fields = {"product_slug", "version", "title", "description", "tags",
                      "price_cad", "state", "seo_score", "chain_version", "release_hash",
                      "etsy_listing_id"}
    version_fields = {"product_id", "version", "cir_json", "certified", "release_hash",
                      "certificate"}
    changed = []
    for obj in session.new.union(session.dirty).union(session.deleted):
        fields = listing_fields if isinstance(obj, Listing) else (
            version_fields if isinstance(obj, PatternVersion) else None)
        if fields is None:
            continue
        state = inspect(obj)
        if obj in session.new or obj in session.deleted or any(
                state.attrs[name].history.has_changes() for name in fields):
            changed.append(obj)
    if not changed:
        return

    # Cooperating package writers acquire this lock before source-row locks.
    _lock(session)
    keys = set()
    with session.no_autoflush:
        for obj in changed:
            state = inspect(obj)
            versions = {obj.version, *state.attrs.version.history.deleted}
            if isinstance(obj, Listing):
                slugs = {obj.product_slug, *state.attrs.product_slug.history.deleted}
                # Attribute history omits the previous value when it was deferred or
                # expired at assignment. Read the persisted identity before flush.
                if state.persistent:
                    previous = session.execute(select(Listing.__table__.c.product_slug,
                                                      Listing.__table__.c.version).where(
                        Listing.__table__.c.id == state.identity[0])).first()
                    if previous:
                        slugs.add(previous.product_slug)
                        versions.add(previous.version)
            else:
                ids = {obj.product_id, *state.attrs.product_id.history.deleted} - {None}
                if state.persistent:
                    previous = session.execute(select(PatternVersion.__table__.c.product_id,
                                                      PatternVersion.__table__.c.version).where(
                        PatternVersion.__table__.c.id == state.identity[0])).first()
                    if previous:
                        ids.add(previous.product_id)
                        versions.add(previous.version)
                slugs = set(session.scalars(select(Product.slug).where(Product.id.in_(ids))))
            keys.update((slug, version) for slug in slugs for version in versions
                        if slug and version)
        for slug, version in sorted(keys):
            _invalidate_locked(session, slug, version,
                               "listing or certified release changed after package review")
