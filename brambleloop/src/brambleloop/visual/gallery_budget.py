"""The per-gallery spend cap, which the owner can lower and code never raises
(D-OWNER-FLUX-GALLERY, ENG-VIS-GALLERY).

Three ceilings hold every generated gallery, all in code:

* **per agent / monthly**: the paid-provider gate (`gateway.paid_provider_gate`) reserves every
  image call against the publishing agent's daily ceiling and the company's monthly budget
  before it is sent; nothing here touches those;
* **per gallery (code)**: `image_production.MAX_SPEND_CAD_PER_GALLERY`, the hard maximum;
* **per gallery (owner)**: an owner setting recorded here. The effective cap is the lower of
  the two. A setting above the code maximum is refused, never stored: the owner lowers the
  cap from code, and raising the code maximum is a reviewed code change.

The setting is an append-only audit row (`ACTION`); the newest one wins. Clearing it
(`amount_cad=None`) returns to the code maximum.
"""
from __future__ import annotations

ACTION = "owner.gallery_spend_cap_set"


class CapRefused(ValueError):
    """A cap the owner may not set: above the code maximum, negative or not a number."""


def code_cap() -> float:
    from .image_production import MAX_SPEND_CAD_PER_GALLERY

    return float(MAX_SPEND_CAD_PER_GALLERY)


def owner_cap(db) -> float | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    if db is None:
        return None
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return None
        v = (row.detail or {}).get("amount_cad")
    return None if v is None else float(v)


def effective_cap(db) -> float:
    own = owner_cap(db)
    return code_cap() if own is None else min(code_cap(), own)


def set_owner_cap(db, amount_cad: float | None, *, by: str) -> dict:
    """Record the owner's per-gallery cap. Only `owner:` actors; never above the code cap."""
    from ..core.models import AuditLog

    if not str(by).startswith("owner"):
        raise CapRefused("only the owner sets the per-gallery spend cap")
    if amount_cad is not None:
        try:
            amount = round(float(amount_cad), 2)
        except (TypeError, ValueError):
            raise CapRefused(f"{amount_cad!r} is not an amount") from None
        if amount < 0:
            raise CapRefused("a spend cap cannot be negative")
        if amount > code_cap():
            raise CapRefused(f"CA${amount:.2f} is above the code maximum CA${code_cap():.2f}; "
                             f"the owner can lower the cap, never raise it here")
    else:
        amount = None
    with db.session() as s:
        s.add(AuditLog(actor=str(by)[:64], action=ACTION, artifact="visual.gallery",
                       detail={"amount_cad": amount, "code_cap_cad": code_cap()}))
    return {"owner_cap_cad": amount, "effective_cap_cad": effective_cap(db)}
