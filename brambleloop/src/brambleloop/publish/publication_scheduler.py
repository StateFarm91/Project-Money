"""ENG-ETSY-PUBLISH slice 2: certified packages flow into Etsy drafts with no button press,
under the owner's existing authority only.

Every hour (inside `store.draft_reconcile`, a free orchestrator cadence), for each release with
a stored listing that is not on Etsy:

1. The owner's publication grant is looked up with `publication_authority.resolve`. That is
   the sealed, content-bound, unexpired, unrevoked grant the owner signed with step-up. **No
   grant means nothing is queued.** This module never records, signs or seals a grant, and it
   imports no grant writer (a test pins that).
2. With a valid grant, `owner_execution.queue_publication` is called: exactly the owner's door.
   It re-checks the grant, the phase and the kill switch, and keeps one job per grant.
   `store.publish` then re-checks everything at its own boundary, including the duplicate
   check and adoption.
3. The one "Approve first public listing (step-up)" card is refreshed from the evidence.

Activation is not scheduled here. A verified draft already enqueues its `store.activate`,
which goes public only under the owner's activation grant, or a Stage A standing grant while
`STAGE_A_ENABLED` (False) is on. The CA$6 opening fee budget and the per-listing US$0.20 cap
are enforced in `finance.listing_costs.reserve`.
"""
from __future__ import annotations

from sqlalchemy import select

TICK_ACTION = "publication.scheduler_tick"
ACTOR = "publication_scheduler"


def tick(db) -> dict:
    """Queue store.publish for every release whose owner grant is valid now. Idempotent."""
    from ..core.models import Listing, PatternVersion, Product
    from ..ops import owner_execution as oe
    from ..ops import publication_authority as pa

    with db.session() as s:
        rows = list(s.execute(
            select(Listing.product_slug, Listing.version, Listing.etsy_listing_id,
                   PatternVersion.release_hash)
            .join(Product, Product.slug == Listing.product_slug)
            .join(PatternVersion, (PatternVersion.product_id == Product.id)
                  & (PatternVersion.version == Listing.version))
            .where(PatternVersion.certified == True)))  # noqa: E712
    from ..core.models import AuditLog

    # Cheap first: only releases the owner has ever recorded a publication grant for are
    # resolved (resolve computes the full evidence snapshot the grant binds).
    with db.session() as s:
        granted = {a for a in s.scalars(select(AuditLog.artifact).where(
            AuditLog.action == pa.APPROVED)) if a}
    queued, waiting, refused = [], [], []
    seen = set()
    for slug, version, etsy_id, release in rows:
        if (slug, version) in seen or etsy_id or not release:
            continue
        seen.add((slug, version))
        if f"{slug}@{version}" not in granted:
            waiting.append(f"{slug}@{version}")
            continue
        refusal, grant = pa.resolve(db, slug=slug, version=version, release=release)
        if refusal is not None or grant is None:
            waiting.append(f"{slug}@{version}")         # no owner grant: nothing to do
            continue
        try:
            out = oe.queue_publication(db, slug=slug, version=version, release=release,
                                       approval_id=grant, actor=ACTOR)
        except oe.ExecutionRefused as exc:
            refused.append({"release": f"{slug}@{version}", "why": str(exc)[:200]})
            continue
        if out.get("queued"):
            queued.append({"release": f"{slug}@{version}", "job_id": out["job_id"]})
    card = None
    try:
        from . import first_listing_card

        card = first_listing_card.refresh(db).get("state")
    except Exception as exc:  # noqa: BLE001 - the card never fails the tick
        card = f"refresh failed: {type(exc).__name__}"
    return {"queued": queued, "waiting_for_owner_grant": len(waiting),
            "refused": refused[:10], "card": card}
