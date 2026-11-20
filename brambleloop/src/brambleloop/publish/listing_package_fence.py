"""Withdraw package review requests when their ORM release sources change.

This is a narrow safeguard: bulk SQL and other evidence (gallery, PDFs, policy
and physical tests) require their own contracts.
"""
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session


def _new_listing_materially_differs(session, listing) -> bool:
    """Only supersede a parked decision when an existing snapshot proves a change."""
    import re
    from types import SimpleNamespace
    from ..core.models import OperatingReading
    from .listing_package import KIND, _listing_material_digest

    if not listing.product_slug or not listing.version:
        return False
    reading = session.scalar(select(OperatingReading).where(
        OperatingReading.kind == KIND,
        OperatingReading.period_key == f"{listing.product_slug}@{listing.version}"))
    expected = (reading.payload or {}).get("listing_material_sha256") if reading else None
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        return False
    defaults = {"tags": [], "price_cad": 0.0, "state": "draft", "seo_score": 0.0,
                "chain_version": "1", "release_hash": "", "etsy_listing_id": ""}
    names = ("product_slug", "version", "title", "description", "tags", "price_cad",
             "chain_version", "release_hash")
    values = {name: (getattr(listing, name) if getattr(listing, name) is not None
                     else defaults.get(name)) for name in names}
    actual = _listing_material_digest(SimpleNamespace(**values))
    return bool(actual and actual != expected)


@event.listens_for(Session, "before_flush", insert=True)
def _withdraw_changed_release_requests(session, _context, _instances):
    from ..core.models import Listing, PatternVersion, Product
    from ..ops.owner_queue_guard import _lock
    from .listing_package import _invalidate_locked

    listing_fields = {"product_slug", "version", "title", "description", "tags",
                      "price_cad", "state", "seo_score", "chain_version", "release_hash",
                      "etsy_listing_id"}
    version_fields = {"product_id", "version", "cir_json", "certified", "release_hash",
                      "certificate", "product"}
    product_fields = {"slug", "title", "risk_class", "status"}
    changed = []
    for obj in session.new.union(session.dirty).union(session.deleted):
        fields = listing_fields if isinstance(obj, Listing) else (
            version_fields if isinstance(obj, PatternVersion) else (
                product_fields if isinstance(obj, Product) else None))
        if fields is None:
            continue
        state = inspect(obj)
        if obj in session.new or obj in session.deleted or any(
                state.attrs[name].history.has_changes() for name in fields):
            changed.append(obj)
    if not changed:
        return

    # A writer may already hold a source row lock. Waiting for the queue lock
    # then would invert record()'s queue->source order and deadlock. Refuse the
    # transaction so its caller can retry instead of blocking in PostgreSQL.
    conn = session.connection()
    if conn.dialect.name == "postgresql":
        from ..core.resilience import TransientError
        from ..runtime.release import OWNER_QUEUE_LOCK

        if not conn.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"),
                           {"k": OWNER_QUEUE_LOCK}):
            raise TransientError("listing review fence busy; retry the source transaction")
    else:
        _lock(session)
    keys = {}
    with session.no_autoflush:
        for obj in changed:
            state = inspect(obj)
            # A content change is a new question even when the owner parked
            # the old one. A temporary status/evidence block is not.
            if isinstance(obj, Listing):
                content_fields = {"product_slug", "version", "title", "description",
                                  "tags", "price_cad", "chain_version", "release_hash"}
            elif isinstance(obj, PatternVersion):
                content_fields = {"product_id", "version", "cir_json", "release_hash", "product"}
            else:
                content_fields = {"slug", "title"}
            fields = listing_fields if isinstance(obj, Listing) else (
                version_fields if isinstance(obj, PatternVersion) else product_fields)
            # Disappearance alone is a temporary block, not proof the owner
            # has a different question. A replacement is compared with the
            # recorded snapshot where possible.
            actual_changed = obj in session.new or obj in session.deleted
            content_changed = (isinstance(obj, Listing) and obj in session.new
                               and _new_listing_materially_differs(session, obj))
            if state.persistent and not actual_changed:
                candidates = {name for name in fields if state.attrs[name].history.has_changes()}
                columns = sorted(name for name in candidates if name != "product")
                if "product" in candidates and "product_id" not in columns:
                    columns.append("product_id")
                table = type(obj).__table__
                prior = (session.execute(select(*(table.c[name] for name in columns)).where(
                    table.c.id == state.identity[0])).first() if columns else None)
                if columns and prior is None:
                    actual_changed = content_changed = True
                elif prior is not None:
                    for name in candidates - {"product"}:
                        if getattr(obj, name) != getattr(prior, name):
                            actual_changed = True
                            content_changed |= name in content_fields
                    if "product" in candidates:
                        added = state.attrs.product.history.added
                        related_id = getattr(added[0], "id", None) if added else None
                        if related_id != prior.product_id:
                            actual_changed = content_changed = True
            if not actual_changed:
                continue

            def add_keys(items):
                for key in items:
                    keys[key] = keys.get(key, False) or content_changed

            if isinstance(obj, Product):
                if not state.persistent:
                    continue
                previous_slug = session.scalar(select(Product.__table__.c.slug).where(
                    Product.__table__.c.id == state.identity[0]))
                versions = session.scalars(select(PatternVersion.__table__.c.version).where(
                    PatternVersion.__table__.c.product_id == state.identity[0]))
                add_keys((slug, version) for version in versions
                         for slug in (previous_slug, obj.slug) if slug and version)
                continue
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
                slugs.update(p.slug for p in state.attrs.product.history.added if p is not None)
            add_keys((slug, version) for slug in slugs for version in versions
                     if slug and version)
        for slug, version in sorted(keys):
            _invalidate_locked(session, slug, version,
                               "listing or certified release changed after package review",
                               supersede_parked=keys[(slug, version)])
