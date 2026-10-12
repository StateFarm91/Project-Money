"""Who is asking. A principal is checked on every call; nothing is cached on it.

Owner authority is not a flag a caller can set: `Principal.owner(session_public_id)` names an
owner Command Center session, and every read/write re-verifies that the session exists in
`cc_owner_sessions`, is not revoked and has not expired. Without a live session the owner
principal is refused like any other. (In-process code can always open the database directly;
this layer is the permission boundary every surface is required to go through, and the leak
tests below prove the public/customer surfaces never call it with anything but a public or
customer principal.)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .errors import PermissionRefused

KINDS = ("owner", "laura", "department", "public", "customer")


def _departments() -> frozenset[str]:
    try:
        from ...autonomy.charters import CHARTERS
        return frozenset(c.key for c in CHARTERS)
    except Exception:  # noqa: BLE001 - autonomy absent: departments are refused, not trusted
        return frozenset()


@dataclass(frozen=True)
class Principal:
    kind: str
    id: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise PermissionRefused(f"unknown principal kind {self.kind!r}")

    @classmethod
    def owner(cls, session_public_id: str) -> "Principal":
        if not session_public_id:
            raise PermissionRefused("an owner principal names its owner session")
        return cls("owner", str(session_public_id))

    @classmethod
    def laura(cls) -> "Principal":
        return cls("laura", "laura")

    @classmethod
    def department(cls, key: str) -> "Principal":
        if key not in _departments():
            raise PermissionRefused(f"{key!r} is not a chartered department")
        if key == "laura":
            raise PermissionRefused("Laura is not a department")
        return cls("department", key)

    @classmethod
    def public(cls, surface: str = "public") -> "Principal":
        return cls("public", surface or "public")

    @classmethod
    def customer(cls, ref: str = "customer") -> "Principal":
        return cls("customer", ref or "customer")

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.id}" if self.id else self.kind


# Every surface that renders for someone other than the owner. They map to principals that
# can read nothing from Laura's memory. Unknown surfaces are public (default deny).
SURFACES: dict[str, str] = {
    "store_preview": "public",
    "store_foundation": "public",
    "storefront": "public",
    "listing": "public",
    "public_api": "public",
    "ask_company_non_owner": "public",
    "social": "public",
    "ads": "public",
    "support_draft": "customer",
    "etsy_message": "customer",
    "customer_email": "customer",
}


def principal_for_surface(name: str) -> Principal:
    kind = SURFACES.get(name, "public")
    return Principal.customer(name) if kind == "customer" else Principal.public(name)


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def verify(db, principal: Principal, *, now: datetime | None = None) -> None:
    """Raise PermissionRefused unless the principal is presently genuine."""
    if not isinstance(principal, Principal):
        raise PermissionRefused("a Principal is required (none means no access)")
    if principal.kind == "department" and principal.id not in _departments():
        raise PermissionRefused(f"{principal.id!r} is not a chartered department")
    if principal.kind != "owner":
        return
    from sqlalchemy import inspect, select

    from ...app.command_center.models import OwnerSession

    if not inspect(db.engine).has_table(OwnerSession.__tablename__):
        raise PermissionRefused("no owner session store: owner authority cannot be verified")
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(OwnerSession).where(OwnerSession.public_id == principal.id))
        if row is None:
            raise PermissionRefused("owner session not found")
        if row.revoked_at is not None:
            raise PermissionRefused("owner session revoked")
        if _aware(row.expires_at) is None or _aware(row.expires_at) <= now:
            raise PermissionRefused("owner session expired")
