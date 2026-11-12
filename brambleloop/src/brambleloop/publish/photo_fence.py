"""Review A3 U5 F4: every ORM writer of photo evidence is fenced against the photo review.

`photo_asset_review._lock` holds the photo review's write lock for the whole of a review, a
certificate issue (`release_gates.certificate_step` / `_record_certificate`) and a consumer
re-check (`etsy_ops.certified_frames`). On SQLite that lock is `BEGIN IMMEDIATE`, which already
excludes every other writer of the database. On PostgreSQL it is an advisory transaction lock,
and before this module only the photo and physical-test ROWS a review names were row-locked: a
writer of any other evidence source -- `PatternVersion.certified` / `cir_json`, a new
`ArtefactProvenance` for the photo's bytes (which disqualifies it as generated), a sibling
`ListingAsset` claiming `leads_gallery`, `physical_upgrade.plan_upgrade`'s renumbering,
`visual.gallery_persist`'s inserts, a disclosed render set -- committed while the lock was held
(reproduced on PostgreSQL 16 by the review), so an issue could record a certificate from a
stale snapshot.

The fence is taken where every ORM write passes, the session flush (the pattern of
`ops.owner_queue_guard`): a flush on PostgreSQL that inserts, changes or deletes a row of a
FENCED source first takes the same advisory key in SHARED mode. The review, issue and consumer
re-check take it EXCLUSIVELY (`_lock`). So:

- an evidence writer waits while a review/issue is in flight, and a review waits for in-flight
  writers to commit -- the snapshot a certificate is issued from cannot move under it;
- writers never wait for each other (shared + shared does not conflict), so the worker pool's
  ordinary parallelism is unchanged outside a review;
- a session that holds the exclusive lock may write freely (Postgres: a session's own advisory
  locks never conflict with each other).

Scope, stated honestly:
- ORM flushes only. Core `insert()`/`update()` and raw SQL bypass session events; no current
  writer of these tables uses them.
- The shared lock is taken at the first fenced flush, possibly after the transaction already
  holds row locks on unfenced tables. An inversion with a review is broken by Postgres's
  deadlock detector (one transaction errors and its job retries); it does not hang.
- One global key, as `_lock` already uses: a review of one release briefly holds evidence
  writers of every release. Reviews are short and CA$0; a per-release key would need every
  writer to name its release, which an `ArtefactProvenance` row cannot.
"""
from __future__ import annotations

from sqlalchemy import event, text
from sqlalchemy.orm import Session

# Every table `photo_asset_review._checks`, `photo_snapshot_current`,
# `photo_certificate_current`, `sample_photo.qualifying_photos` or the certificate itself reads.
FENCED = frozenset({"ListingAsset", "PhysicalPhoto", "PhysicalTest", "PatternVersion",
                    "ArtefactProvenance", "ListingSetCertificateRecord"})
DISCLOSED_ACTION = "assets.disclosed_render"       # publish.disclosed_listing.ACTION
STATS = {"fenced_flushes": 0}


def touches_photo_evidence(session: Session) -> bool:
    for obj in (*session.new, *session.dirty, *session.deleted):
        name = type(obj).__name__
        if name in FENCED:
            return True
        if name == "AuditLog" and getattr(obj, "action", None) == DISCLOSED_ACTION:
            return True
    return False


@event.listens_for(Session, "before_flush")
def _fence_photo_evidence(session: Session, _flush_context, _instances) -> None:
    try:
        bind = session.get_bind()
    except Exception:  # noqa: BLE001 - an unbound session writes nothing we fence
        return
    if bind.dialect.name != "postgresql" or not touches_photo_evidence(session):
        return
    from .photo_asset_review import _LOCK_KEY

    session.connection().execute(text("SELECT pg_advisory_xact_lock_shared(:k)"),
                                 {"k": _LOCK_KEY})
    STATS["fenced_flushes"] += 1
