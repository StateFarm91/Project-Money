"""A repeated customer defect on one row acts: incident, re-verification, withholding (W6).

P0-SUPPORT-DEFECT-INCIDENT. Spec §10: "repeated questions about the same row create a
potential defect incident"; §32: "a repeated customer defect simulation ... creates a
correlated incident". `CustomerExperience.mine_cases` already finds the hotspot (three or
more support cases citing the same product row) and `support.triage` wrote one
`support.defect_candidate` audit row for it -- nothing else. Buyers kept being sold the release
the cases were about.

`escalate` (called by `support.triage` for every hotspot at the threshold) does three things,
once per release+row:

1. **Correlated incident** `support.defect:<slug>:<version>:row<N>`, P1, scoped to the product,
   `halts_publication` False -- the hold is per release (below), so no other product and no
   other version of this one is touched.
2. **Deterministic re-verification** of that release through the existing quality path: one
   `cir.twin` and one `cir.reverse` job (validator), the same handlers `gate.quality` queues
   daily, keyed `support.defect:<check>:<slug>@<version>:row<N>` so a repeat enqueues nothing.
   Confirmation runs through the compiler, not through a vote of customers.
3. **Withholding** of that release's publication through `publish.withholding` -- the existing
   `quality_reverify` kind, under the per-check entry `support.defect:row<N>`. Publish
   (`release_gates.for_publish`) already refuses on it, it is durable on the stored release, and
   it survives re-certification (`carry_reverification`), exactly like a failed daily check.

**How the hold clears (follows the existing re-verification rule: it clears on a pass).**
`quality_ops._run_check` calls `on_reverified` after each check. When every check this hold
waits for (`cir.twin`, `cir.reverse`) has passed on that release since the hold was placed,
the support entry is cleared from the withholding record and the incident is resolved with
that evidence. A failing check leaves the hold in place, and the existing re-verification
path additionally withholds and opens its own incident. Resolving the support incident by
any other means (the owner) also releases the hold on the next triage (`release_resolved`).

Idempotent: a release+row that has been escalated once (open or resolved incident) is never
re-escalated; a fourth case only refreshes the open incident's mention count in place.
"""
from __future__ import annotations

from datetime import datetime, timezone

THRESHOLD = 3
SIGNATURE = "support.defect:"
CHECKS: tuple[str, ...] = ("cir.twin", "cir.reverse")


def signature(slug: str, version: str, row: int) -> str:
    return f"{SIGNATURE}{slug}:{version}:row{int(row)}"[:200]


def hold_check(row: int) -> str:
    """The per-check entry this hold occupies in the release's re-verification record."""
    return f"support.defect:row{int(row)}"


def _release_for(db, slug: str, row: int) -> dict | None:
    """The release the cases are about: the version most cases citing this row name, else
    the newest certified release of the product. None when nothing is stored."""
    from collections import Counter

    from sqlalchemy import select

    from ..core.models import SupportCase
    from ..runtime.quality_ops import certified_releases

    with db.session() as s:
        versions = Counter(
            c.version for c in s.scalars(select(SupportCase).where(
                SupportCase.product_slug == slug))
            if c.version and int(row) in [int(r) for r in
                                          (c.detail or {}).get("cited_rows") or []])
    certified = {r["slug"]: r for r in certified_releases(db)}
    if versions:
        version = versions.most_common(1)[0][0]
        rh = certified.get(slug, {}).get("release_hash", "") \
            if certified.get(slug, {}).get("version") == version else ""
        return {"slug": slug, "version": version, "release_hash": rh}
    return dict(certified[slug]) if slug in certified else None


def escalate(ctx, hotspot: dict) -> dict:
    """Incident + re-verification + withholding for one hotspot, once per release+row."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops import incident_lifecycle
    from ..publish import withholding

    slug, row, mentions = str(hotspot["product"]), int(hotspot["row"]), int(hotspot["mentions"])
    if mentions < THRESHOLD or slug == "?":
        return {"escalated": False, "why": "below threshold or no product"}
    release = _release_for(ctx.db, slug, row)
    if release is None:
        return {"escalated": False, "slug": slug, "row": row,
                "why": "no stored release of this product to re-verify or withhold"}
    version = release["version"]
    sig = signature(slug, version, row)
    with ctx.db.session() as s:
        seen = list(s.scalars(select(Incident).where(Incident.signature == sig)))
        open_row = next((i for i in seen if not i.resolved), None)
        if open_row is not None:
            if (open_row.detail or {}).get("mentions") != mentions:
                open_row.detail = {**(open_row.detail or {}), "mentions": mentions,
                                   "last_seen": datetime.now(timezone.utc).isoformat()}
            return {"escalated": False, "signature": sig, "why": "already open",
                    "mentions": mentions}
        if seen:
            return {"escalated": False, "signature": sig, "mentions": mentions,
                    "why": "this release+row was escalated before and resolved"}
        check = hold_check(row)
        incident_lifecycle.open_or_restate(
            s, signature=sig, severity="P1", product_slug=slug, halts_publication=False,
            summary=(f"{mentions} support cases cite row {row} of {slug}@{version}: "
                     f"publication withheld pending deterministic re-verification"),
            detail={"slug": slug, "version": version, "row": row, "mentions": mentions,
                    "withholding_check": check, "pending_checks": list(CHECKS),
                    "passed_checks": [], "held_at": datetime.now(timezone.utc).isoformat(),
                    "source": "support.triage",
                    "clears": ("when cir.twin and cir.reverse both pass on this release, "
                               "or when this incident is resolved by the owner")})
    held = withholding.record_reverification(
        ctx.db, slug, version, check=check,
        problem=(f"{mentions} support cases cite row {row}; held until re-verification "
                 f"passes"))
    inputs = {"slug": slug, "version": version, "release_hash": release.get("release_hash", ""),
              "support_defect": sig, "row": row}
    key = f"{slug}@{version}:row{row}"
    # Literal job types, so the autonomy map sees each wake edge (AST, literals only).
    jobs = (ctx.enqueue("validator", "cir.twin", dict(inputs),
                        idempotency_key=f"support.defect:cir.twin:{key}"),
            ctx.enqueue("validator", "cir.reverse", dict(inputs),
                        idempotency_key=f"support.defect:cir.reverse:{key}"))
    return {"escalated": True, "signature": sig, "slug": slug, "version": version,
            "row": row, "mentions": mentions, "withheld": bool(held.get("recorded")),
            "reverify_jobs": [j.id for j in jobs if j is not None]}


def _resolve(s, incident, resolution: str) -> None:
    d = dict(incident.detail or {})
    d["resolution"] = resolution
    d["resolved_at"] = datetime.now(timezone.utc).isoformat()
    incident.detail = d
    incident.resolved = True
    s.flush()


def on_reverified(db, slug: str, version: str, check: str, ok: bool | None) -> list[str]:
    """After one re-verification check of slug@version: clear the holds it completes."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..publish import withholding

    if check not in CHECKS or ok is not True:
        return []
    prefix = f"{SIGNATURE}{slug}:{version}:row"
    cleared: list[tuple[str, str]] = []
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(
                Incident.signature.like(f"{prefix}%"), Incident.resolved == False)):  # noqa: E712
            if not inc.signature.startswith(prefix):
                continue
            d = dict(inc.detail or {})
            passed = sorted(set(d.get("passed_checks") or []) | {check})
            d["passed_checks"] = passed
            inc.detail = d
            if set(d.get("pending_checks") or CHECKS) <= set(passed):
                _resolve(s, inc, (f"deterministic re-verification passed on {slug}@{version}"
                                    f" ({', '.join(passed)}); publication hold released"))
                cleared.append((inc.signature, d.get("withholding_check") or ""))
    for _sig, hold in cleared:
        if hold:
            withholding.record_reverification(db, slug, version, check=hold, problem=None)
    return [sig for sig, _ in cleared]


def release_resolved(db) -> list[str]:
    """A support-defect incident resolved by anyone (the owner) releases its hold too."""
    from sqlalchemy import select

    from ..core.models import Incident, PatternVersion
    from ..publish import withholding

    released = []
    with db.session() as s:
        rows = [(i.signature, dict(i.detail or {})) for i in s.scalars(select(Incident).where(
            Incident.signature.like(f"{SIGNATURE}%"), Incident.resolved == True))  # noqa: E712
            if i.signature.startswith(SIGNATURE)]
        open_sigs = {i.signature for i in s.scalars(select(Incident).where(
            Incident.signature.like(f"{SIGNATURE}%"), Incident.resolved == False))}  # noqa: E712
    for sig, d in rows:
        slug, version, hold = d.get("slug"), d.get("version"), d.get("withholding_check")
        if not (slug and version and hold) or sig in open_sigs:
            continue
        with db.session() as s:
            pv = withholding._release(s, slug, version)
            failed = dict((pv.certificate or {}).get(withholding.REVERIFY_FAILED) or {}) \
                if isinstance(pv, PatternVersion) else {}
        if hold in failed:
            withholding.record_reverification(db, slug, version, check=hold, problem=None)
            released.append(sig)
    return released
