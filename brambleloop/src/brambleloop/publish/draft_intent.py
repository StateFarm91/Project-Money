"""Durable remote-draft creation intent; uncertainty never authorizes another create.

Unique product/version is intentionally stronger than release identity: mutating a version
cannot buy another irreversible attempt. An unknown external result needs reconciliation,
not a lease timeout or retry. This is at-most-one automatic create attempt, not exactly-once
remote execution. SQLite/Postgres uniqueness serializes competing inserts.
"""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime
from sqlalchemy import JSON, String, DateTime, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from ..core.db import Base
from ..core.models import Listing, Incident, utcnow
from ..core.resilience import PermanentError


class DraftIntent(Base):
    __tablename__ = "draft_creation_intents"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(20))
    release: Mapped[str] = mapped_column(String(128))
    content_digest: Mapped[str] = mapped_column(String(64))
    token: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), default="CREATING")
    remote_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconciliationRequired(PermanentError):
    pass


def key_for(slug, version):
    return hashlib.sha256(json.dumps([slug,version],separators=(",",":")).encode()).hexdigest()


def reconcile(db, slug, version, why):
    signature="draft-create:"+key_for(slug,version)
    with db.session() as s:
        incident=s.scalar(select(Incident).where(Incident.signature==signature,Incident.resolved.is_(False)))
        if incident is None:
            s.add(Incident(product_slug=slug,severity="P1",signature=signature,
                           summary="Draft creation needs reconciliation; automatic create refused",
                           halts_publication=True,detail={"version":version,"reason":why}))


def claim(db, *, slug, version, release, content_digest):
    key=key_for(slug,version);token=uuid.uuid4().hex
    try:
        with db.session() as s:
            s.add(DraftIntent(key=key,slug=slug,version=version,release=release,
                              content_digest=content_digest,token=token,state="CREATING",detail={}))
    except IntegrityError:
        reconcile(db,slug,version,"A durable creation intent already exists; its remote outcome must be reconciled")
        raise ReconciliationRequired("DRAFT_CREATE_RECONCILIATION: existing intent; never blindly create again") from None
    return key,token


def checkpoint(db, key, token, remote_id):
    if not remote_id:
        raise ValueError("remote listing ID required before upload")
    with db.session() as s:
        intent=s.scalar(select(DraftIntent).where(DraftIntent.key==key).with_for_update())
        if intent is None or intent.token!=token:
            raise ReconciliationRequired("draft intent ownership mismatch")
        if intent.remote_id:
            if intent.remote_id!=str(remote_id):
                raise ReconciliationRequired("draft intent already records a different remote listing")
            return
        listing=s.scalar(select(Listing).where(Listing.product_slug==intent.slug,Listing.version==intent.version))
        if listing is None:
            raise ReconciliationRequired("local listing disappeared before remote checkpoint")
        if listing.etsy_listing_id and str(listing.etsy_listing_id)!=str(remote_id):
            raise ReconciliationRequired("local listing already has a different remote ID")
        intent.remote_id=str(remote_id)
        intent.state="CREATED"
        listing.etsy_listing_id=str(remote_id)
        listing.state="incomplete_on_etsy"


def uncertain(db, key, token):
    with db.session() as s:
        intent=s.get(DraftIntent,key)
        if intent is None or intent.token!=token:
            return
        if not intent.remote_id:
            intent.state="RECONCILE_REQUIRED"
        intent.detail={"automatic_retry_create":False,"outcome":"remote ID recorded" if intent.remote_id else "unknown"}
        slug,version=intent.slug,intent.version
    reconcile(db,slug,version,"Creation/upload interrupted; use recorded remote ID or reconcile unknown outcome")


def release_unsent(db, key, token):
    """Drop an intent whose create request provably never left this process.

    Only the claim's own owner (token match) may release, and only while no remote ID has
    been recorded and the intent is still CREATING. Anything else is left untouched for
    reconciliation: an unknown outcome is never released.
    """
    with db.session() as s:
        intent=s.get(DraftIntent,key)
        if (intent is None or intent.token!=token or intent.remote_id
                or intent.state!="CREATING"):
            return False
        s.delete(intent)
    return True


def refuse_if_existing(db, slug, version):
    """Raise ReconciliationRequired (with its incident) when an intent already exists.

    Checked before any pre-create evidence so an outstanding unknown remote outcome is always
    reported as what it is, whatever the current evidence says. `claim` remains the
    authoritative, race-safe check; this is only the early answer.
    """
    with db.session() as s:
        present=s.get(DraftIntent,key_for(slug,version)) is not None
    if present:
        reconcile(db,slug,version,"A durable creation intent already exists; its remote outcome must be reconciled")
        raise ReconciliationRequired("DRAFT_CREATE_RECONCILIATION: existing intent; never blindly create again")
